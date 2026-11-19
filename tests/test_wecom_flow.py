"""End-to-end in-memory platform fixture. No Tencent account or model service."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from agent.wecom import WeComConnection
from scripts.demo_remote import make_demo


class Platform:
    def __init__(self):
        self.frames = asyncio.Queue()
        self.sent = []
        self.chunks = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        return json.dumps(await self.frames.get())

    async def send(self, raw):
        frame = json.loads(raw)
        self.sent.append(frame)
        cmd = frame['cmd']
        body = {}
        if cmd == 'aibot_upload_media_init':
            body = {'upload_id': 'upload-test'}
        if cmd == 'aibot_upload_media_chunk':
            import base64
            self.chunks.append(base64.b64decode(frame['body']['base64_data']))
        if cmd == 'aibot_upload_media_finish':
            body = {'media_id': 'media-test'}
        await self.frames.put({'headers': frame['headers'], 'errcode': 0, 'body': body})

    async def push(self, identity, kind, content):
        await self.frames.put({'cmd': 'aibot_msg_callback','headers': {'req_id': 'callback-'+identity},
                       'body': {'from': {'userid':'owner'},'chattype':'single', 'msgid':identity,
                                'msgtype':kind,kind:content}})


class WeComFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscribe_receive_approve_complete_and_pick_up_same_bytes(self):
        async def until(check):
            async with asyncio.timeout(18):
                while not check():
                    await asyncio.sleep(.04)
        with tempfile.TemporaryDirectory() as directory:
            app=make_demo(Path(directory))
            hub=app.state.remote
            fixture=Platform()
            conn=WeComConnection(hub, connector=lambda *a,**k:fixture)
            hub.start()
            try:
                await conn.start('fixture-bot','fixture-secret')
                await until(lambda:hub.transport_state=='connected')
                self.assertEqual(fixture.sent[0]['cmd'],'aibot_subscribe')
                csv=b'item,baseline_tv,method_tv\nfixture,0.54,0.12\n'
                with patch('agent.wecom.download_attachment',new_callable=AsyncMock,return_value=('fixture.csv',csv)):
                    await fixture.push('attachment','file',{'url':'fixture'})
                    await until(lambda:bool(hub.session('wecom','owner')['attachments']))
                await fixture.push('create','text',{'content':'读取附件生成中文报告'})
                await until(lambda:len(hub.data['jobs'])==1)
                job=next(iter(hub.data['jobs'].values()))
                self.assertEqual(job['status'],'awaiting_approval')
                await fixture.push('approve','text',{'content':'批准 '+job['id']})
                await until(lambda:bool(hub.data['outbox']) and hub.data['outbox'][0]['status']=='sent')
                self.assertEqual(job['status'],'completed')
                self.assertIn('0.4200',job['result'])
                await fixture.push('take','text',{'content':'取件 '+job['id']+' 1'})
                await until(lambda:len(hub.data['outbox'])==2 and hub.data['outbox'][1]['status']=='sent')
                self.assertEqual(b''.join(fixture.chunks),hub.artifact_path(job['id'],0).read_bytes())
                file_message=next(f for f in fixture.sent if f['cmd']=='aibot_send_msg' and f['body']['msgtype']=='file')
                self.assertEqual(file_message['body']['file']['media_id'],'media-test')
                self.assertEqual(len(hub.data['jobs']),1)
            finally:
                await conn.stop()
                await hub.close()

