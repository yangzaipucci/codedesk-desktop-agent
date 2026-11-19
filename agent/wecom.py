"""WeCom intelligent bot WebSocket transport (official long-connection frames).

Protocol reference: https://github.com/WecomTeam/aibot-node-sdk
No personal-WeChat client hooks, credentials on disk, or public desktop ports.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from agent.wecom_media import download_attachment, upload_file

ENDPOINT = 'wss://openws.work.weixin.qq.com'


class WeComConnection:
    def __init__(self, hub, connector=None):
        self.hub = hub
        self.connector = connector
        self.task = None
        self.ws = None
        self.pending = {}
        self.bot_id = self.secret = ''
        self.send_lock = asyncio.Lock()
        self.messages = asyncio.Queue(maxsize=100)
        self.hub.sender = self.send_message
        self.hub.file_sender = self.send_file

    async def start(self, bot_id, secret):
        if not isinstance(bot_id, str) or not bot_id.strip() or not isinstance(secret, str) or not secret.strip():
            raise ValueError('请在电脑端填写 BotID 和 Secret。')
        if not self.hub.data['config']['users']:
            raise ValueError('请先绑定允许访问的企业微信 UserID。')
        await self.stop()
        previous = self.hub.data['config'].get('bot_id')
        if previous and previous != bot_id.strip():
            for job in self.hub.data['jobs'].values():
                if job['channel'] == 'wecom' and job['status'] in {'running','queued','paused','pausing','awaiting_approval'}:
                    self.hub.action(job['id'], 'cancel')
        self.bot_id, self.secret = bot_id.strip(), secret.strip()
        self.hub.data['config']['bot_id'] = self.bot_id
        self.hub.save()
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
        self.ws = None
        self.secret = ''
        self.hub.transport_state = 'disconnected'

    async def request(self, cmd, body, request_id=None):
        if self.ws is None:
            raise ValueError('企业微信未连接。')
        req_id = request_id or uuid.uuid4().hex
        if req_id in self.pending:
            raise ValueError('同一消息回复尚在等待回执。')
        future = asyncio.get_running_loop().create_future()
        self.pending[req_id] = future
        try:
            async with self.send_lock:
                await self.ws.send(json.dumps({'cmd':cmd, 'headers':{'req_id':req_id}, 'body':body}, ensure_ascii=False))
            result = await asyncio.wait_for(future, 10)
            if result.get('errcode') != 0:
                raise ValueError('企业微信返回错误代码 ' + str(result.get('errcode', 'unknown')))
            return result
        finally:
            self.pending.pop(req_id, None)

    async def send_message(self, user, text):
        return await self.request('aibot_send_msg', {'chatid':user, 'msgtype':'markdown', 'markdown':{'content':text.encode('utf-8')[:4000].decode('utf-8', errors='ignore')}})

    async def send_file(self, user, path):
        media_id = await upload_file(self.request, path.name, path.read_bytes())
        self.hub.authorize(user)
        return await self.request('aibot_send_msg', {'chatid': user, 'msgtype': 'file', 'file': {'media_id': media_id}})

    async def reader(self):
        async for raw in self.ws:
            frame = json.loads(raw)
            if not isinstance(frame, dict):
                continue
            req_id = frame.get('headers', {}).get('req_id')
            cmd = frame.get('cmd')
            if cmd == 'aibot_msg_callback':
                self.messages.put_nowait(frame)
            elif cmd == 'aibot_event_callback':
                if frame.get('body', {}).get('event', {}).get('eventtype') == 'disconnected_event':
                    raise ValueError('机器人连接被其他实例接管。')
            elif req_id in self.pending and not self.pending[req_id].done():
                self.pending[req_id].set_result(frame)
        raise ConnectionError('企业微信连接已关闭。')

    async def handle(self, frame):
        body = frame.get('body', {})
        user = body.get('from', {}).get('userid', '')
        if body.get('chattype') != 'single' or user not in self.hub.data['config']['users']:
            return  # Group and unknown identities can never create tasks.
        req_id = frame.get('headers', {}).get('req_id')
        msg_id = body.get('msgid')
        if not req_id or not msg_id:
            return
        msgtype = body.get('msgtype')
        if msgtype == 'text':
            text = body.get('text', {}).get('content', '')
        elif msgtype == 'voice':
            text = body.get('voice', {}).get('content', '')
        elif msgtype == 'mixed':
            # Do not silently drop image/file instructions from a mixed message.
            text = ''
        else:
            text = ''
        try:
            if msgtype in {'file', 'image'}:
                key = self.hub.message_key('wecom', user, msg_id)
                previous = self.hub.data['inbox'].get(key)
                if previous:
                    reply = previous['reply']
                else:
                    project = self.hub.session('wecom', user)['project']
                    destination = self.hub.data['projects'].get(project, {}).get('path')
                    if not project:
                        raise ValueError('请先在桌面登记项目。')
                    name, content = await download_attachment(msgtype, body.get(msgtype, {}))
                    if self.hub.data['projects'].get(project, {}).get('path') != destination:
                        raise ValueError('下载期间项目目录已变更，请重发附件。')
                    self.hub.attach('wecom', user, name, content, msg_id)
                    reply = self.hub.data['inbox'][key]['reply']
            elif text:
                result = await self.hub.receive('wecom', user, msg_id, text)
                reply = result['reply']
            else:
                reply = '请将文字和附件分条发送。支持文字、已转写的语音、单独的图片和文件。'
        except ValueError as error:
            reply = str(error)
        await self.request('aibot_respond_msg', {'msgtype':'stream', 'stream':{'id':'reply_'+str(msg_id), 'finish':True, 'content':reply}}, req_id)

    async def consume(self):
        while True:
            frame = await self.messages.get()
            try:
                await self.handle(frame)
            except Exception as error:
                self.hub.last_error = '消息回复失败：' + type(error).__name__
            finally:
                self.messages.task_done()

    async def heartbeat(self):
        while True:
            await asyncio.sleep(30)
            await self.request('ping', {})

    async def run(self):
        if self.connector is None:
            from websockets.asyncio.client import connect
            self.connector = connect
        delay = 1
        while True:
            children = []
            try:
                self.hub.transport_state = 'connecting'
                async with self.connector(ENDPOINT, open_timeout=10, max_size=1024*1024, ping_interval=None) as ws:
                    self.ws = ws
                    reader = asyncio.create_task(self.reader())
                    children.append(reader)
                    await self.request('aibot_subscribe', {'bot_id':self.bot_id, 'secret':self.secret})
                    self.hub.transport_state = 'connected'
                    self.hub.last_error = ''
                    delay = 1
                    children.extend([asyncio.create_task(self.heartbeat()), asyncio.create_task(self.consume())])
                    done, _ = await asyncio.wait(children, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
            except asyncio.CancelledError:
                raise
            except ValueError as error:
                self.hub.transport_state = 'error'
                self.hub.last_error = str(error).replace(self.secret, '[已隐藏]') if self.secret else str(error)
                return  # Authentication rejection/takeover needs user intervention.
            except Exception as error:
                self.hub.transport_state = 'reconnecting'
                self.hub.last_error = '连接中断：' + type(error).__name__
            finally:
                self.ws = None
                for child in children:
                    child.cancel()
                await asyncio.gather(*children, return_exceptions=True)
                for pending in list(self.pending.values()):
                    if not pending.done():
                        pending.set_exception(ConnectionError('连接中断，发送结果待核对。'))
                while not self.messages.empty():
                    self.messages.get_nowait()
                    self.messages.task_done()
            await asyncio.sleep(delay)
            delay = min(delay*2,30)
