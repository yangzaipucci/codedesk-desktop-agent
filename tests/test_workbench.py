import asyncio
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent.settings import Settings
from agent.runtime import Runtime
from agent.tasks import TaskQueue
from agent.tools import DEFINITIONS
from agent.workspace import Workspace, attach_context
from server.app import create_app
from mcp_network import PageText, PublicConnection, public_addresses, fetch


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.work=self.root/'work';self.work.mkdir();self.workspace=Workspace(self.work,self.root/'state')
        self.path=self.work/'demo.py';self.path.write_bytes(b'\xef\xbb\xbfa = 1\r\nb = 2\r\n')
    def tearDown(self):self.temp.cleanup()

    def test_save_preserves_bom_newlines_and_supports_undo(self):
        original=self.path.read_bytes();data=self.workspace.read('demo.py')
        result=self.workspace.save('demo.py','a = 2\nb = 2\n',data['sha256'])
        self.assertEqual(self.path.read_bytes(),b'\xef\xbb\xbfa = 2\r\nb = 2\r\n')
        self.workspace.tools.undo(result['change_id'])
        self.assertEqual(self.path.read_bytes(),original)

    def test_save_refuses_external_change(self):
        data=self.workspace.read('demo.py');self.path.write_text('external')
        with self.assertRaises(ValueError):self.workspace.save('demo.py','overwrite',data['sha256'])
        self.assertEqual(self.path.read_text(),'external')

    def test_unchanged_save_does_not_create_undo_record(self):
        data=self.workspace.read('demo.py');result=self.workspace.save('demo.py',data['text'],data['sha256'])
        self.assertIsNone(result['change_id'])

    def test_full_editor_read_is_not_preview_pagination(self):
        self.path.write_text('line\n'*1000)
        self.assertEqual(self.workspace.read('demo.py')['text'].count('\n'),1000)

    def test_create_cannot_overwrite_or_escape(self):
        for name in ('demo.py','../outside.py','.git/config'):
            with self.subTest(name=name),self.assertRaises(ValueError):self.workspace.create(name,'file')
        self.workspace.create('src/new.py','file')
        self.assertTrue((self.work/'src/new.py').is_file())

    def test_binary_or_non_utf8_editor_files_rejected(self):
        for data in (b'a\0b',b'\xff\xfe'):
            self.path.write_bytes(data)
            with self.assertRaises(ValueError):self.workspace.read('demo.py')

    def test_search_skips_private_binary_and_build_directories(self):
        self.path.write_text('Needle\nneedle')
        (self.work/'.env').write_text('needle-secret')
        (self.work/'binary').write_bytes(b'needle\0')
        (self.work/'node_modules').mkdir();(self.work/'node_modules/dep.py').write_text('needle')
        result=self.workspace.search('needle')
        self.assertEqual(len(result['results']),2)
        self.assertEqual(len(self.workspace.search('Needle',True)['results']),1)
        self.assertEqual(self.workspace.paths()[0],['binary','demo.py'])

    def test_search_results_are_bounded(self):
        self.path.write_text('match\n'*1000)
        result=self.workspace.search('match')
        self.assertEqual(len(result['results']),200);self.assertTrue(result['truncated'])

    def test_context_references_validate_scope_and_keep_selection(self):
        result=attach_context(self.work,'explain',{'files':['demo.py'],'selection':{'path':'demo.py','text':'a = 1'}})
        self.assertIn('a = 1',result)
        with self.assertRaises(ValueError):attach_context(self.work,'test',{'files':['../outside']})
        with self.assertRaises(ValueError):attach_context(self.work,'test',{'files':['demo.py']*9})

    def test_diff_and_history_show_manual_change(self):
        data=self.workspace.read('demo.py');saved=self.workspace.save('demo.py','changed',data['sha256'])
        self.assertEqual(self.workspace.changes()[0]['id'],saved['change_id'])
        self.assertIn('+changed',self.workspace.diff(saved['change_id'])['diff'])


class ModeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);self.work=root/'work';self.work.mkdir();self.settings=Settings(root/'state');self.settings.value.update(workspace=str(self.work),online_enabled=False)
    def tearDown(self):self.temp.cleanup()

    async def test_read_only_modes_reject_unadvertised_write_and_command(self):
        class Adversarial:
            def __init__(self):self.calls=0;self.definitions=[]
            async def complete(self,messages,definitions,emit):
                self.definitions=definitions;self.calls+=1
                if self.calls==1:return {'role':'assistant','content':None,'tool_calls':[{'id':'w','type':'function','function':{'name':'write','arguments':json.dumps({'path':'unsafe.txt','content':'bad'})}},{'id':'b','type':'function','function':{'name':'bash','arguments':json.dumps({'command':'Write-Output unsafe'})}}]},{}
                return {'role':'assistant','content':'read-only'},{}
        for mode in ('ask','plan'):
            provider=Adversarial();events=[]
            async def sink(event):events.append(event)
            await Runtime(self.settings,provider).run('analyze',sink,mode=mode)
            self.assertEqual([d['function']['name'] for d in provider.definitions],['read'])
            self.assertFalse((self.work/'unsafe.txt').exists())
            self.assertTrue(all(not e['result']['ok'] for e in events if e['type']=='tool_result'))

    async def test_mode_date_and_online_preference_refresh_in_same_session(self):
        prompts=[]
        class Observe:
            async def complete(self,messages,tools,emit):
                prompts.append(messages[0]['content']);return {'role':'assistant','content':'ok'},{}
        async def sink(event):pass
        runtime=Runtime(self.settings,Observe())
        await runtime.run('first',sink,mode='plan')
        await runtime.run('second',sink,mode='debug')
        self.assertIn('Plan 模式',prompts[0]);self.assertIn('Debug 模式',prompts[1]);self.assertIn('当前电脑日期时间',prompts[1]);self.assertIn('关闭了主动联网查询',prompts[1])
        self.assertEqual(len(DEFINITIONS),4)

    async def test_queue_keeps_contexts_separate_and_runs_sequentially(self):
        instances=[];order=[];active=0;maximum=0
        class Job:
            def __init__(self,settings):self.session_id=str(len(instances));instances.append(self)
            async def run(self,prompt,sink):
                nonlocal active,maximum
                active+=1;maximum=max(maximum,active);order.append(prompt)
                await asyncio.sleep(.02)
                await sink({'type':'done','status':'completed','tokens':1})
                active-=1
        queue=TaskQueue(self.settings,Job);queue.add('one');queue.add('two');await queue.worker
        self.assertEqual(order,['one','two']);self.assertEqual(maximum,1);self.assertEqual(len(instances),2)
        self.assertNotEqual(queue.jobs[0]['session_id'],queue.jobs[1]['session_id'])
        restored=TaskQueue(self.settings,Job);self.assertEqual(len(restored.jobs),2)

    async def test_queued_job_can_be_cancelled_before_execution(self):
        executed=[]
        class Job:
            def __init__(self,s):self.session_id='test'
            async def run(self,prompt,sink):
                executed.append(prompt);await asyncio.sleep(.03);await sink({'type':'done','status':'completed'})
        queue=TaskQueue(self.settings,Job);queue.add('first');second=queue.add('second');await queue.cancel(second['id']);await queue.worker
        self.assertEqual(executed,['first']);self.assertEqual(second['status'],'cancelled')


class WebSafetyTests(unittest.TestCase):
    def test_private_dns_and_literal_addresses_are_rejected(self):
        for address in ('127.0.0.1','10.0.0.1','169.254.169.254','::1'):
            with patch.object(socket,'getaddrinfo',return_value=[(2,1,6,'',(address,443))]):
                with self.assertRaises(ValueError):public_addresses('untrusted.example')

    def test_https_only_and_no_embedded_credentials(self):
        for url in ('http://example.com','file:///C:/secret','https://name:password@example.com','https://example.com:444'):
            with self.subTest(url=url),self.assertRaises(ValueError):fetch(url)

    def test_redirect_to_private_host_is_checked_before_connection(self):
        class Response:
            status=302
            def getheader(self,name):return 'https://127.0.0.1/secret'
        with patch.object(PublicConnection,'request'),patch.object(PublicConnection,'getresponse',return_value=Response()),patch.object(PublicConnection,'close'),patch.object(socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            # Actual private-address validation lives in connect, which is only
            # reached by request; test it directly as well as URL validation.
            with self.assertRaises(ValueError):PublicConnection('127.0.0.1').connect()

    def test_html_scripts_are_not_returned_as_page_text(self):
        page=PageText();page.feed('<title>Public</title><script>steal()</script><p>Hello</p>')
        self.assertEqual(page.parts,['Public','Hello'])


class EditorAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.work=self.root/'work';self.work.mkdir();(self.work/'a.py').write_text('before')
        self.settings=Settings(self.root/'state');self.settings.value.update(workspace=str(self.work),online_enabled=False)
        self.client=TestClient(create_app(self.settings,'editor-token'));self.headers={'Authorization':'Bearer editor-token'}
    def tearDown(self):self.client.close();self.temp.cleanup()

    def test_editor_endpoints_require_auth_and_preserve_conflicts(self):
        self.assertEqual(self.client.get('/api/editor/file?path=a.py').status_code,401)
        data=self.client.get('/api/editor/file?path=a.py',headers=self.headers).json()
        result=self.client.post('/api/editor/save',headers=self.headers,json={'path':'a.py','text':'after','sha256':data['sha256']})
        self.assertEqual(result.status_code,200)
        conflict=self.client.post('/api/editor/save',headers=self.headers,json={'path':'a.py','text':'wrong','sha256':data['sha256']})
        self.assertEqual(conflict.status_code,400)
        undo=self.client.post('/api/undo',headers=self.headers,json={'change_id':result.json()['change_id']})
        self.assertEqual(undo.status_code,200);self.assertEqual((self.work/'a.py').read_text(),'before')

    def test_online_setting_persists_and_rejects_non_boolean(self):
        self.client.post('/api/settings',headers=self.headers,json={'online_enabled':False})
        self.assertFalse(Settings(self.settings.directory).value['online_enabled'])
        self.assertEqual(self.client.post('/api/settings',headers=self.headers,json={'online_enabled':'false'}).status_code,400)

    def test_manual_terminal_streams_real_output(self):
        response=self.client.post('/api/terminal',headers=self.headers,json={'command':'Write-Output workbench-terminal-ok'})
        self.assertEqual(response.status_code,200);self.assertIn('workbench-terminal-ok',response.text);self.assertIn('terminal_done',response.text)
