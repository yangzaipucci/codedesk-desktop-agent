from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.course_fixtures import ScheduledTestProvider
from agent.course_inspection import prepare_repair
from agent.scheduler import Scheduler
from agent.settings import Settings
from fastapi.testclient import TestClient
from server.app import create_app


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_due_skill_executes_once_with_real_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);work=root/'project';work.mkdir()
            prepare_repair(work)
            code=work/'stats.py';code.write_text(code.read_text(encoding='utf-8').replace('return sum(nums) / len(nums)','return sum(nums) / len(nums) if nums else 0'),encoding='utf-8')
            state=Settings(root/'state');state.save({'workspace':str(work),'online_enabled':False})
            now=datetime.now(timezone.utc).timestamp()
            routine=work/'routines.yaml';routine.write_text(json.dumps({'routines':[{'id':'verify','skill':'run-tests','at':datetime.fromtimestamp(now+10,timezone.utc).isoformat(),'prompt':'跑测试'}]}),encoding='utf-8')
            scheduler=Scheduler(state,lambda item:ScheduledTestProvider())
            with patch.dict(os.environ,{'ENABLE_NOTIFICATIONS':'0'}):
                self.assertEqual((await scheduler.tick(routine,now))['triggers_fired'],0)
                first=await scheduler.tick(routine,now+11)
                self.assertEqual(first['triggers_fired'],1)
                self.assertTrue(first['runs'][0]['skill_loaded'])
                self.assertEqual(first['runs'][0]['status'],'completed')
                self.assertEqual((await scheduler.tick(routine,now+12))['triggers_fired'],0)
                with patch.dict(os.environ,{'ENABLE_SCHEDULER':'0'}):
                    self.assertEqual((await scheduler.tick(routine,now+13))['status'],'disabled')

    def test_invalid_or_external_routines_never_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);work=root/'project';work.mkdir();state=Settings(root/'state');state.save({'workspace':str(work)})
            scheduler=Scheduler(state)
            outside=root/'routines.yaml';outside.write_text('routines: []',encoding='utf-8')
            with self.assertRaises(ValueError):scheduler.load(outside)
            target=work/'routines.yaml';target.write_text('routines: [!!python/object/apply:os.system [echo nope]]',encoding='utf-8')
            with self.assertRaises(ValueError):scheduler.load(target)


class SchedulerAPITests(unittest.TestCase):
    def test_scheduler_configuration_and_start_stop_require_authentication(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);work=root/'project';work.mkdir();state=Settings(root/'state');state.save({'workspace':str(work),'online_enabled':False})
            with TestClient(create_app(state,token='test-scheduler-token')) as client:
                self.assertEqual(client.post('/api/daemon/scheduler/start').status_code,401)
                client.headers['Authorization']='Bearer test-scheduler-token'
                self.assertEqual(client.post('/api/daemon/scheduler/start').status_code,400)
                (work/'routines.yaml').write_text('routines: []\n',encoding='utf-8')
                self.assertEqual(client.post('/api/daemon/scheduler/start').json()['status'],'started')
                self.assertTrue(client.get('/api/daemon').json()['scheduler_running'])
                self.assertEqual(client.post('/api/daemon/scheduler/stop').json()['status'],'stopped')
