"""Authenticated local UI/API for the remote task hub."""
import base64
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, Response, FileResponse

from agent.remote import RemoteHub
from agent.wecom import WeComConnection


def install_remote(app, settings, token, resource_root, runtime_factory=None):
    def external_busy():
        state = app.state
        return (state.jobs.busy or state.scheduler_busy or
                any(t is not None and not t.done() for t in (state.runtime.active, state.terminal, state.daemon_task)))
    kwargs = {'runtime_factory':runtime_factory} if runtime_factory else {}
    hub = RemoteHub(settings, external_busy=external_busy, **kwargs)
    transport = WeComConnection(hub)
    app.state.remote = hub
    app.state.wecom = transport

    async def startup():
        hub.start()
    async def shutdown():
        await transport.stop()
        await hub.close()
    app.add_event_handler('startup', startup)
    app.add_event_handler('shutdown', shutdown)

    @app.get('/remote')
    async def page():
        return HTMLResponse((resource_root/'ui/remote.html').read_text(encoding='utf-8').replace('__BOOT_TOKEN__',token))

    @app.get('/remote.js')
    async def script():
        return Response((resource_root/'ui/remote.js').read_text(encoding='utf-8'),media_type='text/javascript')

    @app.get('/remote.css')
    async def style():
        return Response((resource_root/'ui/remote.css').read_text(encoding='utf-8'),media_type='text/css')

    @app.get('/api/remote')
    async def status(user: str = ''):
        return {**hub.snapshot(), 'current_project': hub.current_project(user)}

    @app.post('/api/remote/config')
    async def config(request: Request):
        hub.configure(await request.json())
        return hub.snapshot()

    @app.post('/api/remote/project')
    async def project(request: Request):
        value=await request.json()
        return hub.project(value.get('name',''),value.get('path',''),value.get('mode','ask'),value.get('rules',''))

    @app.post('/api/remote/message')
    async def message(request: Request):
        value=await request.json()
        result=await hub.receive('local',value.get('user',''),value.get('message_id',''),value.get('text',''))
        hub.start()
        return result

    @app.post('/api/remote/action')
    async def action(request: Request):
        value=await request.json()
        return {'reply':hub.action(value.get('id'),value.get('action'),value.get('text',''))}

    @app.get('/api/remote/job')
    async def job(id: str):
        value=hub.owned(id)
        return {**hub.summary(value),'events':value['events']}

    @app.post('/api/remote/attachment')
    async def attachment(request: Request):
        if int(request.headers.get('content-length','0'))>12*1024*1024:
            raise ValueError('附件请求过大。')
        value=await request.json()
        try:
            content=base64.b64decode(value.get('data',''),validate=True)
        except (ValueError,TypeError):
            raise ValueError('附件编码无效。') from None
        return hub.attach('local',value.get('user',''),value.get('name',''),content)

    @app.get('/api/remote/artifact')
    async def artifact(id: str, index: int):
        path=hub.artifact_path(id,index)
        return FileResponse(path,filename=path.name,media_type='application/octet-stream')

    @app.post('/api/remote/connect')
    async def connect(request: Request):
        value=await request.json()
        if getattr(hub, 'demonstration', False):
            raise ValueError('独立演示使用样例数据，连接真实账号请打开正式工作台。')
        await transport.start(value.get('bot_id'),value.get('secret'))
        return {'status':'connecting'}

    @app.post('/api/remote/disconnect')
    async def disconnect():
        await transport.stop()
        return {'status':'disconnected'}

    @app.post('/api/remote/retry-delivery')
    async def retry(request: Request):
        value=await request.json()
        item=next((m for m in hub.data['outbox'] if m['id']==value.get('id')),None)
        if item is None or item['status'] not in {'failed','uncertain'}:
            raise ValueError('只有失败或回执不确定的消息可重发。')
        item['status']='pending'
        hub.save()
        return {'status':'pending'}
