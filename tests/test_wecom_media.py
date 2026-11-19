import asyncio
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from agent.remote import RemoteHub
from agent.settings import Settings
from agent.wecom import WeComConnection
from agent.wecom_media import CHUNK, decrypt, download_attachment, upload_file


class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        settings = Settings(self.root/'state')
        settings.memory_keys[settings._account()] = ''
        self.hub = RemoteHub(settings)
        self.addAsyncCleanup(self.hub.close)
        self.hub.configure({'users': ['owner']})
        self.hub.project('A', str(self.root))
        self.conn = WeComConnection(self.hub)
        self.conn.request = AsyncMock(return_value={'errcode': 0})

    async def test_file_redelivery_keeps_one_copy_and_one_draft(self):
        frame = {'headers': {'req_id': 'r'}, 'body': {'from': {'userid': 'owner'}, 'chattype': 'single',
                 'msgtype': 'file', 'msgid': 'f', 'file': {'url': 'unused'}}}
        with patch('agent.wecom.download_attachment', new_callable=AsyncMock, return_value=('a.csv', b'a,b')) as fetch:
            await self.conn.handle(frame)
            await self.conn.handle(frame)
            fetch.assert_awaited_once()
        job = await self.hub.receive('wecom', 'owner', 'm', '开始')
        self.assertEqual(len(self.hub.owned(job['job_id'])['attachments']), 1)
        self.assertEqual(len(list((self.root/'.codedesk/inbox').iterdir())), 1)

    async def test_encrypted_download_and_redirect_validation(self):
        key = bytes(range(32))
        payload = b'item,value\na,2\n'
        padding = 32 - len(payload) % 32
        enc = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
        encrypted = enc.update(payload + bytes([padding])*padding) + enc.finalize()
        encoded = base64.b64encode(key).decode().rstrip('=')
        def server(req):
            if req.url.path == '/redirect':
                return httpx.Response(302, headers={'Location': 'https://localhost/media'})
            return httpx.Response(200, content=encrypted, headers={'Content-Disposition': 'attachment; filename="data.csv"'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
            name, data = await download_attachment('file', {'url': 'https://work.weixin.qq.com/media','aeskey':encoded}, client)
            self.assertEqual((name, data), ('data.csv', payload))
            with self.assertRaisesRegex(ValueError,'域名'):
                await download_attachment('file', {'url':'https://work.weixin.qq.com/redirect'}, client)
        with self.assertRaises(ValueError):decrypt(encrypted[:-1], encoded)

    async def test_upload_splits_exact_bytes_and_checks_ids(self):
        data = b'A' * (CHUNK+3)
        parts = []
        async def request(command, body):
            if command.endswith('init'):
                self.assertEqual(body['total_chunks'],2)
                return {'body':{'upload_id':'u'}}
            if command.endswith('chunk'):
                self.assertEqual(body['chunk_index'],len(parts))
                parts.append(base64.b64decode(body['base64_data']))
                return {}
            return {'body':{'media_id':'media'}}
        self.assertEqual(await upload_file(request,'table.csv',data),'media')
        self.assertEqual(b''.join(parts),data)

    async def test_pickup_dedupe_hash_owner_scope_and_delivery(self):
        self.hub.data['config']['bot_id'] = 'bot-a'
        created = await self.hub.receive('wecom','owner','create','生成报告')
        job = self.hub.owned(created['job_id'])
        folder = self.root/'.codedesk/outputs'/job['id']
        folder.mkdir(parents=True)
        (folder/'result.csv').write_bytes(b'a,b')
        job.update(status='completed',artifacts=self.hub.artifacts(job))
        cmd = f"取件 {job['id']} 1"
        await self.hub.receive('wecom','owner','pick',cmd)
        await self.hub.receive('wecom','owner','pick',cmd)
        self.assertEqual(len(self.hub.data['outbox']),1)
        self.hub.file_sender = AsyncMock()
        self.hub.transport_state = 'connected'
        await self.hub.deliver()
        self.hub.file_sender.assert_awaited_once_with('owner',folder/'result.csv')
        self.assertEqual(self.hub.data['outbox'][0]['status'],'sent')
        (folder/'result.csv').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'修改'):
            await self.hub.receive('wecom','owner','new-pick',cmd)
        self.hub.data['config']['bot_id'] = 'bot-b'
        with self.assertRaisesRegex(ValueError,'当前会话'):
            await self.hub.receive('wecom','owner','different-bot',cmd)

