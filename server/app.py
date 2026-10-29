"""Authenticated localhost transport: REST, WebSocket, SSE."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import secrets
import sys

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from agent.mcp_client import MCP, demo_config
from agent.provider import Provider
from agent.runtime import Runtime
from agent.settings import Settings
from agent.tools import Tools
from agent.workspace import Workspace, attach_context
from agent.tasks import TaskQueue
from agent.modes import validate_mode


def resources() -> Path:
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def create_app(settings=None, token=None, runtime=None):
    settings = settings or Settings()
    token = token or secrets.token_urlsafe(32)
    runtime = runtime or Runtime(settings,restore=True)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.state.token, app.state.settings, app.state.runtime = token, settings, runtime
    app.state.terminal = None
    app.state.jobs = TaskQueue(settings)
    style_nonce = secrets.token_urlsafe(24)

    async def shutdown():
        await app.state.jobs.close()
        for task in (app.state.terminal,runtime.active):
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
    app.add_event_handler('shutdown',shutdown)

    @app.middleware("http")
    async def secure(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
                return JSONResponse({"error": "未授权"}, status_code=401)
        try:
            response = await call_next(request)
        except (ValueError, OSError) as error:
            return JSONResponse({"error": settings.redact(str(error))}, status_code=400)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = f"default-src 'self'; script-src 'self'; style-src 'self' 'nonce-{style_nonce}'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:*; frame-ancestors 'none'; base-uri 'none'"
        return response

    def idle():
        if runtime.active and not runtime.active.done():
            raise HTTPException(409, "任务进行中，请先中断再修改设置。")
        if app.state.terminal and not app.state.terminal.done():
            raise HTTPException(409, '终端命令正在运行，请先等待或中断。')
        if app.state.jobs.busy:
            raise HTTPException(409, '任务队列正在运行，请等待完成或取消任务。')

    @app.get('/api/tasks')
    async def tasks():
        return {'tasks': app.state.jobs.summaries()}

    @app.post('/api/tasks')
    async def add_task(request: Request):
        if (runtime.active and not runtime.active.done()) or (app.state.terminal and not app.state.terminal.done()):
            raise HTTPException(409, '请先完成对话或终端命令。')
        data = await request.json()
        raw = data.get('prompt')
        if not isinstance(raw, str) or not raw.strip() or len(raw)>30000:
            raise ValueError('请输入有效任务。')
        root = workspace().root
        prompt = attach_context(root, raw, data.get('context'))
        return {k:v for k,v in app.state.jobs.add(prompt).items() if k!='events'}

    @app.get('/api/tasks/detail')
    async def task_detail(id: str, after: int = 0):
        job = app.state.jobs.get(id)
        return {**{k:v for k,v in job.items() if k!='events'}, 'events':job['events'][max(0,after):], 'cursor':len(job['events'])}

    @app.post('/api/tasks/cancel')
    async def cancel_task(request: Request):
        data = await request.json()
        job = await app.state.jobs.cancel(data.get('id'))
        return {'id':job['id'],'status':job['status']}

    def workspace():
        root = settings.value['workspace']
        if not root or not Path(root).is_dir():
            raise ValueError('请先选择工作目录。')
        return Workspace(root, settings.directory)

    @app.get('/api/editor/file')
    async def editor_file(path: str):
        return workspace().read(path)

    @app.post('/api/editor/save')
    async def editor_save(request: Request):
        idle()
        data = await request.json()
        result = workspace().save(data.get('path'), data.get('text'), data.get('sha256'))
        if runtime.messages and result.get('change_id'):
            runtime.messages.append({'role': 'user', 'content': '用户手动编辑了 ' + result['path'] + '；继续修改前请重新 read。'})
        return result

    @app.post('/api/editor/create')
    async def editor_create(request: Request):
        idle()
        data = await request.json()
        return workspace().create(data.get('path'), data.get('kind', 'file'))

    @app.get('/api/paths')
    async def paths():
        values, truncated = workspace().paths()
        return {'paths': values, 'truncated': truncated}

    @app.get('/api/search')
    async def search(q: str, case_sensitive: bool = False):
        return await asyncio.to_thread(workspace().search, q, case_sensitive)

    @app.get('/api/changes')
    async def changes():
        return {'changes': workspace().changes()}

    @app.get('/api/changes/diff')
    async def change_diff(id: str):
        return workspace().diff(id)

    @app.get("/")
    async def index():
        html = (resources() / "ui" / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("__BOOT_TOKEN__", token).replace('__STYLE_NONCE__', style_nonce))

    @app.post('/api/terminal')
    async def terminal(request: Request):
        idle()
        payload = await request.json()
        command = payload.get('command')
        if not isinstance(command, str) or not command.strip() or len(command) > 6000:
            raise ValueError('请输入有效命令，最长 6000 字。')
        root = workspace().root
        queue = asyncio.Queue()

        async def runner():
            async def emit(event):
                clean = json.loads(settings.redact(json.dumps(event, ensure_ascii=False)))
                await queue.put(clean)
            try:
                result = await Tools(root, settings.directory).bash(command, timeout=120, emit=emit)
                await emit({'type': 'terminal_done', 'result': result})
            except asyncio.CancelledError:
                await emit({'type': 'terminal_done', 'result': {'ok': False, 'cancelled': True}})
            except Exception:
                await emit({'type': 'terminal_done', 'result': {'ok': False, 'error': '命令启动失败。'}})

        task = app.state.terminal = asyncio.create_task(runner())

        async def stream():
            try:
                while True:
                    event = await queue.get()
                    yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
                    if event['type'] == 'terminal_done':
                        break
            finally:
                if not task.done():
                    task.cancel()
                    await task
        return StreamingResponse(stream(), media_type='text/event-stream')

    @app.post('/api/terminal/stop')
    async def stop_terminal():
        task = app.state.terminal
        if task and not task.done():
            task.cancel()
            await task
        return {'ok': True}

    @app.get("/app.js")
    async def script():
        return Response((resources() / "ui" / "app.js").read_text(encoding="utf-8"), media_type="text/javascript")

    @app.get("/style.css")
    async def style():
        return Response((resources() / "ui" / "style.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/api/settings")
    async def get_settings():
        return settings.public()

    @app.post("/api/settings")
    async def save_settings(request: Request):
        idle()
        return settings.save(await request.json())

    @app.post("/api/test")
    async def test_connection():
        idle()
        try:
            return await Provider(settings).test()
        except TimeoutError:
            return JSONResponse({"error": "连接测试超时。"}, 400)
        except ValueError as error:
            return JSONResponse({"error": settings.redact(str(error))}, 400)

    @app.get("/api/models")
    async def get_models():
        return {"models": await Provider(settings).models()}

    @app.get("/api/files")
    async def get_files(path: str = "."):
        if not settings.value["workspace"]:
            return {"files": []}
        tools = Tools(Path(settings.value["workspace"]))
        directory = tools.resolve(path)
        if not directory.is_dir():
            raise ValueError("目录不存在。")
        hidden = {".git", ".venv", "node_modules", "__pycache__", ".build-temp", ".local-state", ".pytest_cache"}
        files = []
        for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if item.name in hidden or item.name.startswith(".env") or item.is_symlink():
                continue
            files.append({"name": item.name, "path": str(item.relative_to(tools.workspace)).replace("\\", "/"), "directory": item.is_dir()})
            if len(files) >= 300:
                break
        return {"files": files}

    @app.get("/api/file")
    async def get_file(path: str):
        return Tools(Path(settings.value["workspace"])).read(path, limit=500)

    @app.get("/api/history")
    async def history():
        return {"events": runtime.events, "session_id": runtime.session_id,'mode':runtime.mode}

    @app.post("/api/undo")
    async def undo_change(request: Request):
        idle()
        payload = await request.json()
        change_id = payload.get("change_id")
        if not isinstance(change_id, str) or not change_id:
            raise ValueError("缺少修改记录编号。")
        result = Tools(Path(settings.value["workspace"]), settings.directory).undo(change_id)
        if not result.get("ok"):
            return JSONResponse(result, status_code=409)
        # Subsequent model requests must observe actual file state after undo.
        if runtime.messages:
            runtime.messages.append({"role": "user", "content": f"用户已撤销对 {result.get('path', '')} 的修改。继续任务前请重新 read 文件，不要假定之前的修改仍存在。"})
        return result

    @app.post("/api/new")
    async def new_session():
        idle()
        runtime.reset()
        runtime.reset_context(settings.value['workspace'])
        runtime.persist()
        return {"ok": True}

    @app.post("/api/stop")
    async def stop():
        if runtime.active and not runtime.active.done():
            runtime.active.cancel()
            await runtime.active
        return {"ok": True}

    @app.post("/api/mcp/demo")
    async def enable_demo():
        idle()
        return settings.save({"mcp_servers": {**settings.value["mcp_servers"], **demo_config()}})

    @app.post("/api/mcp/test")
    async def mcp_test():
        idle()
        workspace = settings.value["workspace"]
        if not workspace:
            raise ValueError("请先选择工作目录。")
        client = MCP(settings.value["mcp_servers"], Path(workspace))
        statuses = []

        async def collect(event):
            statuses.append(event)

        definitions = await client.discover(collect)
        result = {"statuses": statuses, "tools": definitions}
        for alias, (name, tool) in client.routes.items():
            if name == "workspace-demo" and tool == "workspace_info":
                result["demo_call"] = await client.call(alias, {})
        return result

    @app.get("/api/trace")
    async def trace():
        lines = ["# CodeDesk 运行记录", "", f"会话：{runtime.session_id}", f"工作目录：{runtime.workspace}", ""]
        lines.extend("```json\n" + json.dumps(e, ensure_ascii=False, indent=2) + "\n```\n" for e in runtime.events)
        return Response(settings.redact("\n".join(lines)), media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="trace.md"'})

    async def start_run(prompt, sink, context=None, mode='agent'):
        idle()
        validate_mode(mode)
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 30000:
            raise ValueError("请输入任务，最长 30000 字。")
        display = prompt.strip()
        prompt = attach_context(settings.value['workspace'], display, context)
        runtime.active = asyncio.create_task(runtime.run(prompt, sink, display_prompt=display, mode=mode))
        return runtime.active

    @app.post("/api/run")
    async def sse_run(request: Request):
        payload = await request.json()
        queue = asyncio.Queue()

        async def sink(event):
            await queue.put(event)

        task = await start_run(payload.get("prompt"), sink, payload.get('context'), payload.get('mode','agent'))

        async def stream():
            try:
                while True:
                    event = await queue.get()
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                    if event["type"] == "done":
                        break
            finally:
                if not task.done():
                    task.cancel()
                    await task

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.websocket("/ws")
    async def socket(websocket: WebSocket):
        await websocket.accept()
        task = None
        try:
            auth = await asyncio.wait_for(websocket.receive_json(), 5)
            if not secrets.compare_digest(str(auth.get("token", "")), token):
                await websocket.close(1008)
                return
            payload = await websocket.receive_json()

            async def sink(event):
                try:
                    await websocket.send_json(event)
                except (WebSocketDisconnect, RuntimeError):
                    # Let the receive loop cancel the task and its subprocesses.
                    pass

            task = await start_run(payload.get("prompt"), sink, payload.get('context'), payload.get('mode','agent'))
            receive = asyncio.create_task(websocket.receive())
            try:
                done, _ = await asyncio.wait([task, receive], return_when=asyncio.FIRST_COMPLETED)
                if receive in done and not task.done():
                    task.cancel()
                    await task
            finally:
                receive.cancel()
                await asyncio.gather(receive, return_exceptions=True)
            await websocket.close()
        except (WebSocketDisconnect, TimeoutError):
            pass
        except (ValueError, HTTPException) as error:
            try:
                await websocket.send_json({"type": "error", "text": str(error)})
                await websocket.close()
            except RuntimeError:
                pass
        finally:
            if task and not task.done():
                task.cancel()
                await task

    return app
