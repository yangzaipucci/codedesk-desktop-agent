import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.remote import RemoteHub
from agent.runtime import Runtime
from agent.settings import Settings
from agent.wecom import WeComConnection


class FileProvider:
    """Controlled model; actual Runtime/read/write tools and files are used."""
    def __init__(self):
        self.step=0

    async def complete(self,messages,tools,emit):
        self.step+=1
        await asyncio.sleep(.03)
        prompt='\n'.join(m['content'] for m in messages if m['role']=='user' and isinstance(m.get('content'),str))
        if self.step==1:
            call={'id':'read1','type':'function','function':{'name':'read','arguments':json.dumps({'path':'input.txt'})}}
            return {'role':'assistant','content':None,'tool_calls':[call]}, {'total_tokens':20}
        if self.step==2 and any(t['function']['name']=='write' for t in tools):
            import re
            output=re.search(r'\.codedesk/outputs/[a-f0-9]+/',prompt)[0]+'result.txt'
            call={'id':'write1','type':'function','function':{'name':'write','arguments':json.dumps({'path':output,'content':'verified output'})}}
            return {'role':'assistant','content':None,'tool_calls':[call]}, {'total_tokens':20}
        observed='\n'.join(m['content'] for m in messages if m['role']=='tool')
        text='已读取实际文件。'+('包含追加要求' if '追加验证' in prompt else '')+'\n'+observed[:500]
        await emit({'type':'assistant_delta','text':text})
        return {'role':'assistant','content':text},{'total_tokens':20}


class RemoteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.a=self.root/'A';self.a.mkdir();(self.a/'input.txt').write_text('project A',encoding='utf-8')
        self.b=self.root/'B';self.b.mkdir();(self.b/'input.txt').write_text('project B',encoding='utf-8')
        self.settings=Settings(self.root/'state')
        self.settings.memory_keys[self.settings._account()] = ''  # Isolate tests from the Windows credential store.
        self.settings.value.update(workspace=str(self.a),online_enabled=False,mcp_servers={})
        self.hub=RemoteHub(self.settings,runtime_factory=lambda s:Runtime(s,FileProvider()))
        self.hub.configure({'users':['owner']})
        self.hub.project('A',str(self.a))
        self.hub.project('B',str(self.b))

    async def asyncTearDown(self):
        await self.hub.close()
        self.tmp.cleanup()

    async def message(self,text,id='m1',channel='local'):
        return await self.hub.receive(channel,'owner',id,text)

    async def finish(self,job_id):
        self.hub.start()
        for _ in range(150):
            if self.hub.owned(job_id)['status'] in {'completed','error','cancelled','timeout'}:
                await asyncio.sleep(.05)
                return self.hub.owned(job_id)
            await asyncio.sleep(.03)
        self.fail('Task did not finish')

    async def test_duplicate_message_persists_without_reexecution(self):
        first=await self.message('读取 input.txt')
        second=await self.message('读取 input.txt')
        self.assertTrue(second['duplicate']);self.assertEqual(first['job_id'],second['job_id'])
        await self.hub.close()
        self.hub=RemoteHub(self.settings)
        third=await self.message('读取 input.txt')
        self.assertTrue(third['duplicate']);self.assertEqual(len(self.hub.data['jobs']),1)

    async def test_unknown_identity_and_channel_ownership(self):
        with self.assertRaises(ValueError):await self.hub.receive('wecom','stranger','m','读取文件')
        task=await self.message('读取 input.txt')
        with self.assertRaises(ValueError):await self.message('取消 '+task['job_id'],'w1','wecom')

    async def test_workspace_snapshot_ignores_later_global_changes(self):
        task=await self.message('读取 input.txt')
        self.settings.value['workspace']=str(self.b)
        await self.message('切换 B','switch')
        result=await self.finish(task['job_id'])
        self.assertEqual(result['status'],'completed');self.assertIn('project A',result['result'])
        self.assertNotIn('project B',result['result'])

    async def test_draft_merge_and_attachment_association(self):
        await self.message('暂存 读取附件','d1')
        entry=self.hub.attach('local','owner','notes.txt',b'notes')
        with self.assertRaises(ValueError):await self.message('切换 B','s1')
        await self.message('暂存 用中文整理','d2')
        response=await self.message('开始','d3');job=self.hub.owned(response['job_id'])
        self.assertEqual(job['prompt'],'读取附件\n用中文整理');self.assertEqual(job['attachments'][0]['sha256'],entry['sha256'])

    async def test_approval_and_output_tamper_detection(self):
        self.hub.project('A',str(self.a),'agent')
        response=await self.message('读文件后生成结果')
        job=self.hub.owned(response['job_id']);self.assertEqual(job['status'],'awaiting_approval')
        self.hub.action(job['id'],'approve');job=await self.finish(job['id'])
        self.assertEqual(job['status'],'completed');self.assertEqual(len(job['artifacts']),1)
        path=self.hub.artifact_path(job['id'],0);self.assertEqual(path.read_text(),'verified output')
        path.write_text('changed')
        with self.assertRaises(ValueError):self.hub.artifact_path(job['id'],0)

    async def test_paused_queue_and_append_are_honored(self):
        result=await self.message('读取 input.txt');id=result['job_id']
        self.hub.action(id,'pause');self.hub.start();await asyncio.sleep(.3)
        self.assertEqual(self.hub.owned(id)['status'],'paused')
        self.hub.action(id,'append','追加验证');self.hub.action(id,'resume')
        job=await self.finish(id);self.assertIn('包含追加要求',job['result']);self.assertTrue(job['updates'][0]['applied'])

    async def test_agent_append_invalidates_prior_approval(self):
        self.hub.project('A',str(self.a),'agent')
        result=await self.message('读取 input.txt');id=result['job_id']
        self.hub.action(id,'approve');self.hub.action(id,'append','增加输出')
        self.assertEqual(self.hub.owned(id)['status'],'awaiting_approval')

    async def test_cancel_and_accepting_switch(self):
        response=await self.message('读取 input.txt');id=response['job_id']
        self.hub.action(id,'cancel');self.assertEqual(self.hub.owned(id)['status'],'cancelled')
        self.hub.configure({'accepting':False})
        with self.assertRaises(ValueError):await self.message('新任务','new')
        self.assertIn('cancelled',(await self.message('状态 '+id,'status'))['reply'])

    async def test_restart_marks_active_interrupted(self):
        result=await self.message('读取 input.txt');id=result['job_id']
        self.hub.owned(id)['status']='running';self.hub.save();await self.hub.close()
        self.hub=RemoteHub(self.settings)
        self.assertEqual(self.hub.owned(id)['status'],'interrupted')
        with self.assertRaises(ValueError):self.hub.action(id,'resume')

    async def test_delivery_failure_does_not_reexecute_job(self):
        response=await self.message('读取 input.txt',channel='wecom')
        job=await self.finish(response['job_id'])
        async def fail(*args):raise TimeoutError('ack not received')
        self.hub.sender=fail;self.hub.transport_state='connected';await self.hub.deliver()
        self.assertEqual(self.hub.data['outbox'][-1]['status'],'uncertain')
        self.assertEqual(job['status'],'completed');self.assertEqual(len(self.hub.data['jobs']),1)

    async def test_attachment_limits_and_project_rules(self):
        with self.assertRaises(ValueError):self.hub.attach('local','owner','bad.exe',b'1')
        await self.message('记住 中文答复')
        result=await self.message('读取 input.txt','r2')
        await self.message('忘记规则','r3')
        self.assertEqual(self.hub.owned(result['job_id'])['rules'],'中文答复')
        self.assertEqual(self.hub.data['projects']['A']['rules'],'')

    async def test_external_execution_lock_prevents_overlap(self):
        self.hub.external_busy=lambda:True
        result=await self.message('读取 input.txt');self.hub.start();await asyncio.sleep(.35)
        self.assertEqual(self.hub.owned(result['job_id'])['status'],'queued')
        self.hub.external_busy=lambda:False
        self.assertEqual((await self.finish(result['job_id']))['status'],'completed')

    async def test_wecom_frames_and_unauthorized_groups(self):
        conn=WeComConnection(self.hub)
        sent=[]
        async def request(cmd,body,request_id=None):sent.append((cmd,body,request_id));return {'errcode':0}
        conn.request=request
        frame={'cmd':'aibot_msg_callback','headers':{'req_id':'request1'},'body':{'msgid':'wecom1','chattype':'single','from':{'userid':'owner'},'msgtype':'text','text':{'content':'读取 input.txt'}}}
        await conn.handle(frame);await conn.handle(frame)
        self.assertEqual(len(self.hub.data['jobs']),1);self.assertEqual(sent[-1][0],'aibot_respond_msg')
        self.assertTrue(sent[-1][1]['stream']['finish'])
        frame['body']['msgid']='group1';frame['body']['chattype']='group';await conn.handle(frame)
        self.assertEqual(len(self.hub.data['jobs']),1)

    async def test_wecom_request_requires_ack_and_surfaces_rejection(self):
        conn=WeComConnection(self.hub)
        class Wire:
            async def send(inner,raw):
                frame=json.loads(raw)
                conn.pending[frame['headers']['req_id']].set_result({'errcode':40014})
        conn.ws=Wire()
        with self.assertRaisesRegex(ValueError,'40014'):await conn.request('aibot_subscribe',{'bot_id':'dummy','secret':'dummy'})
        self.assertEqual(conn.pending,{})


if __name__=='__main__':unittest.main()
