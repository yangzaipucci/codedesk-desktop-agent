import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent.capabilities import enabled,project_guidance,token_bound
from agent.daemon import Daemon,JobLock,digest
from agent.inspection import ReviewFixture
from agent.reviewer import Reviewer
from agent.runtime import Runtime
from agent.settings import Settings
from agent.skills import Skills
from agent.tools import Tools,DEFINITIONS
from server.app import create_app


class PatchesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.work=self.root/'project';self.work.mkdir()
        self.settings=Settings(self.root/'state')
        self.settings.save({'workspace':str(self.work),'online_enabled':False,'enable_daemon':True})
        self.tools=Tools(self.work,self.settings.directory)
    def tearDown(self):self.temp.cleanup()

    def test_skill_catalog_is_metadata_only_and_disclosure_is_measured(self):
        registry=Skills(self.work,self.settings.directory)
        self.assertGreaterEqual(len(registry.entries),3)
        self.assertGreaterEqual(registry.metrics()['disclosure_ratio'],5)
        self.assertNotIn('Follow data from input to output',registry.catalog())
        result=registry.read('skill://code-review/SKILL.md')
        self.assertIn('Follow data from input to output',result['text'])
        self.assertEqual(registry.loaded,['code-review'])

    def test_skill_path_traversal_and_disabled_loading(self):
        with self.assertRaises(ValueError):self.tools.read('skill://code-review/../../../../README.md')
        with patch.dict(os.environ,{'ENABLE_SKILLS':'0'}):
            self.assertEqual(Skills(self.work,self.settings.directory).catalog(),'')
            with self.assertRaises(ValueError):Tools(self.work,self.settings.directory).read('skill://code-review/SKILL.md')

    def test_skill_trigger_negative_and_explicit_cases(self):
        registry=Skills(self.work,self.settings.directory)
        self.assertEqual(registry.select('不要运行测试，只解释'),[])
        self.assertEqual(registry.select('今天多少号'),[])
        self.assertEqual(registry.select('/skill web-research 查找 DOI'),['web-research'])

    def test_global_and_project_injection_bounded(self):
        (self.settings.directory/'AGENTS.md').write_text('GLOBAL_SENTINEL\n')
        (self.work/'AGENTS.md').write_text('PROJECT_SENTINEL\n')
        text,sources=project_guidance(self.work,self.settings.directory)
        self.assertIn('GLOBAL_SENTINEL',text);self.assertIn('PROJECT_SENTINEL',text)
        self.assertEqual(len(sources),2)
        (self.work/'AGENTS.md').write_text('中'*10000,encoding='utf-8')
        self.assertLessEqual(token_bound(project_guidance(self.work,self.settings.directory,budget=350)[0]),350)

    def test_feature_settings_persist_and_environment_takes_precedence(self):
        self.settings.save({'enable_skills':False,'enable_custom':False})
        loaded=Settings(self.settings.directory)
        self.assertFalse(loaded.value['enable_skills']);self.assertFalse(enabled('reviewer',loaded.directory))
        with patch.dict(os.environ,{'ENABLE_SKILLS':'1'}):self.assertTrue(enabled('skills',loaded.directory))
        with self.assertRaises(ValueError):loaded.save({'enable_hooks':'yes'})

    async def test_dangerous_calls_denied_before_effect_and_alternatives_present(self):
        for command in ['rm -rf scratch','rm -r -f scratch','Remove-Item scratch -Recurse -Force','cmd /c rd /s /q scratch','Set-Content .env x']:
            with self.subTest(command=command):
                result=await self.tools.execute('bash',{'command':command})
                self.assertTrue(result.get('denied'));self.assertIn('替代方案',result['error'])
        result=await self.tools.execute('write',{'path':'.env','content':'PLACEHOLDER'})
        self.assertTrue(result['denied']);self.assertFalse((self.work/'.env').exists())
        self.assertTrue((await self.tools.execute('write',{'path':'.env.example','content':'PLACEHOLDER'}))['ok'])

    async def test_related_tests_are_really_executed_and_failures_preserved(self):
        (self.work/'maths.py').write_text('def twice(x):\n    return x * 2\n')
        (self.work/'test_maths.py').write_text('import unittest\nfrom maths import twice\nclass T(unittest.TestCase):\n    def test_twice(self): self.assertEqual(twice(3),6)\n')
        passed=await self.tools.hooks.after_edit('maths.py',self.tools)
        self.assertEqual(passed['status'],'passed');self.assertEqual(passed['tests_run'],1)
        self.assertEqual(len(passed['summary'].splitlines()),3)
        self.assertNotIn('stderr',passed)
        (self.work/'maths.py').write_text('def twice(x):\n    return 0\n')
        failed=await self.tools.hooks.after_edit('maths.py',self.tools)
        self.assertEqual(failed['status'],'failed');self.assertNotEqual(failed['exit_code'],0)

    async def test_reviewer_isolated_and_cannot_write_even_if_requested(self):
        (self.work/'maths.py').write_text('def twice(x): return x*2\n')
        result=await Reviewer(self.settings,ReviewFixture()).review('Review twice.',['maths.py'],self.tools)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['denied_writes'],1)
        self.assertEqual(result['allowed_tools'],['read','bash:git diff']);self.assertFalse((self.work/'review-probe.txt').exists())

    async def test_legacy_switch_keeps_exact_four_tool_interface(self):
        class Provider:
            async def complete(inner,messages,definitions,emit):
                self.assertEqual({d['function']['name'] for d in definitions},{'read','write','edit','bash'})
                self.assertNotIn('Skill catalog',messages[0]['content'])
                self.assertNotIn('AGENTS.md',messages[0]['content'])
                return {'role':'assistant','content':'ok'},{'total_tokens':1}
        with patch.dict(os.environ,{'CODEDESK_LEGACY':'1'}):
            runtime=Runtime(self.settings,Provider())
            events=[]
            async def sink(event):events.append(event)
            await runtime.run('hello',sink)
        self.assertEqual(events[-1]['status'],'completed')
        self.assertEqual(len(DEFINITIONS),4)

    async def test_reviewer_refuses_credential_reads(self):
        (self.work/'.env').write_text('FIXTURE_VALUE=not-a-real-key')
        outer=self
        class Fixture:
            turn=0
            async def complete(inner,messages,definitions,emit):
                inner.turn+=1
                if inner.turn==1:
                    return {'role':'assistant','content':None,'tool_calls':[{'id':'r','type':'function','function':{'name':'read','arguments':'{"path":".env"}'}}]},{'total_tokens':10}
                outer.assertFalse(json.loads(messages[-1]['content'])['ok'])
                outer.assertNotIn('FIXTURE_VALUE',messages[-1]['content'])
                return {'role':'assistant','content':'not read'},{'total_tokens':10}
        result=await Reviewer(self.settings,Fixture()).review('review',['x.py'],self.tools)
        self.assertEqual(result['status'],'completed')

    async def test_checkpoint_rerun_does_not_repeat_completed_steps_or_notices(self):
        worker=Daemon(self.settings)
        job=worker.create({'steps':[{'kind':'write','path':'output.txt','content':'result'}]})
        await worker.run(job['id']);modified=(self.work/'output.txt').stat().st_mtime_ns
        await worker.run(job['id'])
        self.assertEqual((self.work/'output.txt').stat().st_mtime_ns,modified)
        self.assertEqual(len(worker.summaries()['notifications']),1)

    async def test_main_runtime_runs_post_edit_hook_and_bounded_reviewer(self):
        (self.work/'test_maths.py').write_text('import unittest\nfrom maths import twice\nclass T(unittest.TestCase):\n    def test_value(self): self.assertEqual(twice(3),6)\n')
        class MainFixture:
            def __init__(inner):inner.turn=0
            async def complete(inner,messages,definitions,emit):
                inner.turn+=1
                if inner.turn==1:
                    return {'role':'assistant','content':None,'tool_calls':[{'id':'w','type':'function','function':{'name':'write','arguments':json.dumps({'path':'maths.py','content':'def twice(x): return x*2\n'})}}]},{'total_tokens':10}
                observation=json.loads(messages[-1]['content'])
                self.assertEqual(observation['autotest']['status'],'passed')
                return {'role':'assistant','content':'done'},{'total_tokens':10}
        runtime=Runtime(self.settings,MainFixture(),reviewer_provider=ReviewFixture())
        events=[]
        async def sink(event):events.append(event)
        await runtime.run('实现 twice 并验证',sink)
        self.assertEqual(events[-1]['status'],'completed')
        self.assertLessEqual(runtime.reviewer_context_tokens,500)
        self.assertFalse((self.work/'review-probe.txt').exists())

    async def test_inflight_write_recovered_without_duplicate_application(self):
        worker=Daemon(self.settings)
        job=worker.create({'steps':[{'kind':'write','path':'output.txt','content':'result'}]})
        step=job['steps'][0];step.update(status='running',attempts=1,before_sha256=None)
        from agent.capabilities import atomic_json
        atomic_json(worker.path(job['id']),job)
        (self.work/'output.txt').write_text('result',encoding='utf-8')
        modified=(self.work/'output.txt').stat().st_mtime_ns
        result=await worker.run(job['id'])
        self.assertTrue(result['steps'][0]['recovered']);self.assertEqual(result['steps'][0]['attempts'],1)
        self.assertEqual((self.work/'output.txt').stat().st_mtime_ns,modified)

    async def test_daemon_conflicting_external_change_is_not_overwritten(self):
        worker=Daemon(self.settings)
        job=worker.create({'steps':[{'kind':'write','path':'output.txt','content':'result'}]})
        job['steps'][0].update(status='running',attempts=1,before_sha256=None)
        from agent.capabilities import atomic_json
        atomic_json(worker.path(job['id']),job)
        (self.work/'output.txt').write_text('manual change')
        with self.assertRaises(ValueError):await worker.run(job['id'])
        self.assertEqual((self.work/'output.txt').read_text(),'manual change')

    def test_daemon_paths_and_kernel_lock(self):
        worker=Daemon(self.settings)
        with self.assertRaises(ValueError):worker.create({'steps':[{'kind':'write','path':'../outside','content':'x'}]})
        with JobLock(worker.directory/'test.lock'):
            with self.assertRaises(ValueError):
                with JobLock(worker.directory/'test.lock'):pass

    def test_authenticated_capabilities_and_notification_api(self):
        with TestClient(create_app(self.settings,token='local-test-token')) as client:
            self.assertEqual(client.get('/api/capabilities').status_code,401)
            client.headers['Authorization']='Bearer local-test-token'
            self.assertEqual(client.get('/api/capabilities').json()['mcp']['default_port'],8001)
            self.assertEqual(client.get('/api/daemon').json()['notifications'],[])
