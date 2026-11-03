"""Executable course acceptance checks, not hand-written score claims."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import httpx

from agent.capabilities import atomic_json, project_guidance, token_bound, truncate, assets
from agent.daemon import Daemon
from agent.mcp_client import MCP
from agent.reviewer import Reviewer
from agent.settings import Settings
from agent.skills import Skills
from agent.tools import Tools


def child_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    # Windows venv launchers may create a second process. Use the base
    # interpreter plus explicit import paths so the hard-kill test kills the worker.
    executable = getattr(sys, '_base_executable', sys.executable)
    return [executable, str(Path(__file__).resolve().parents[1] / 'app.py')]


def child_environment():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path), PYTHONUTF8='1')
    for name in ('SKILLS', 'CUSTOM', 'HOOKS', 'AUTOTEST', 'REVIEWER', 'DAEMON'):
        env['ENABLE_' + name] = '1'
    env['CODEDESK_LEGACY'] = '0'
    return env


class ReviewFixture:
    """Explicit controlled-provider tier; filesystem operations are real."""
    def __init__(self):
        self.turn = 0
    async def complete(self, messages, definitions, emit):
        assert [d['function']['name'] for d in definitions] == ['read']
        self.turn += 1
        function = ('write', {'path':'review-probe.txt','content':'must not be created'}) if self.turn == 1 else ('read', {'path':'maths.py'})
        if self.turn <= 2:
            return {'role':'assistant','content':None,'tool_calls':[{'id':str(self.turn),'type':'function','function':{'name':function[0],'arguments':json.dumps(function[1])}}]}, {'total_tokens':10}
        return {'role':'assistant','content':'Read-only review completed; focused tests passed.'}, {'total_tokens':10}


async def inspect_patches(output, include_http=True):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('skill_report','custom_report','daemon_report','mcp_report'):
        atomic_json(output/(name+'.json'),{'status':'running','passed':False})
    with tempfile.TemporaryDirectory(prefix='acceptance-', dir=output) as folder:
        root = Path(folder); work = root/'project'; work.mkdir()
        settings = Settings(root/'state')
        settings.save({'workspace':str(work),'online_enabled':False})
        (settings.directory/'AGENTS.md').write_text('Global: keep changes small.\n',encoding='utf-8')
        (work/'AGENTS.md').write_text((assets()/'project-AGENTS.md').read_text(encoding='utf-8'),encoding='utf-8')
        registry = Skills(work,settings.directory)
        trials = [('请做代码审查并指出实际问题',['code-review']),('请运行测试验证 Python 函数',['python-tests']),('请检索文献并列出 DOI',['web-research']),('你好',[]),('今天几号',[]),('不要运行测试，只解释字典推导式',[])]
        trial_results = [{'prompt':p,'expected':e,'selected':registry.select(p),'passed':registry.select(p)==e} for p,e in trials]
        catalog = registry.catalog()
        body_absent = all(item['body'].strip() not in catalog for item in registry.entries.values())
        for name in registry.entries:
            registry.read('skill://'+name+'/SKILL.md')
        skill = {**registry.metrics(),'trials':trial_results,'false_positives':sum(bool(r['selected']) for r in trial_results if not r['expected']),'catalog_has_no_bodies':body_absent,'loaded_on_demand':list(dict.fromkeys(registry.loaded))}
        skill['passed'] = skill['skill_count']>=3 and skill['disclosure_ratio']>=5 and all(r['passed'] for r in trial_results) and body_absent

        tools = Tools(work,settings.directory)
        denied = []
        for name,arguments in [('bash',{'command':'rm -rf scratch'}),('write',{'path':'.env','content':'PLACEHOLDER=not-a-secret'})]:
            result = await tools.execute(name,arguments)
            denied.append({'tool':name,'denied':result.get('denied',False),'has_alternative':'替代方案' in result.get('error','')})
        (work/'maths.py').write_text('def twice(x):\n    return x * 2\n',encoding='utf-8')
        (work/'test_maths.py').write_text('import unittest\nfrom maths import twice\nclass T(unittest.TestCase):\n    def test_twice(self): self.assertEqual(twice(3),6)\n',encoding='utf-8')
        autotest = await tools.hooks.after_edit('maths.py',tools)
        review = await Reviewer(settings,ReviewFixture()).review('Review twice.', ['maths.py'],tools)
        custom, sources = project_guidance(work, settings.directory)
        summary = truncate('[CodeDesk review]'+review.get('summary',''),500-token_bound(custom))
        custom_report = {'agents_md':sources,'denied':denied,'autotest':{k:v for k,v in autotest.items() if k in {'status','syntax_ok','test','exit_code','timed_out'}},'reviewer':{k:v for k,v in review.items() if k in {'status','allowed_tools','denied_writes','reads','context_isolated'}},'reviewer_test_tier':'controlled_provider_with_real_file_tools','parent_context_tokens':token_bound(custom+summary),'token_measure':'UTF-8 byte upper bound; not billing'}
        if autotest['status'] != 'passed':
            # Only our generated acceptance fixture is run here, never user code.
            custom_report['autotest']['diagnostic'] = {k:str(autotest[k])[:2000] for k in ('stdout','stderr','reason','error') if k in autotest}
        custom_report['passed'] = len(sources)==2 and all(d['denied'] and d['has_alternative'] for d in denied) and autotest['status']=='passed' and review.get('denied_writes')==1 and not (work/'review-probe.txt').exists() and custom_report['parent_context_tokens']<=500
        atomic_json(output/'skill_report.json',skill)
        atomic_json(output/'custom_report.json',custom_report)

        daemon = Daemon(settings)
        job = daemon.create({'name':'acceptance checkpoint job','steps':[{'kind':'write','path':f'out/step-{i}.txt','content':f'step {i}\n'} for i in range(1,5)]})
        options = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        process = subprocess.Popen(child_command()+['daemon','--state-dir',str(settings.directory),'run',job['id'],'--step-delay','1'],env=child_environment(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**options)
        try:
            deadline=time.monotonic()+30
            while True:
                if process.poll() is not None:raise RuntimeError('Checkpoint worker exited before hard-kill test')
                checkpoint=daemon.get(job['id'])
                completed=sum(s['status']=='completed' for s in checkpoint['steps'])
                if completed==3:break
                if time.monotonic()>deadline:raise RuntimeError('Checkpoint test timed out')
                await asyncio.sleep(.03)
            process.kill();process.wait(timeout=10)
            resume_step=next(s['number'] for s in checkpoint['steps'] if s['status']!='completed')
            before=[(work/f'out/step-{i}.txt').stat().st_mtime_ns for i in range(1,4)]
            resumed=await daemon.run(job['id'])
            after=[(work/f'out/step-{i}.txt').stat().st_mtime_ns for i in range(1,4)]
            await daemon.run(job['id'])
            notices=daemon.summaries()['notifications']
            daemon_report={'resume_step':resume_step,'steps_total':len(resumed['steps']),'completed_before_kill':completed,'hard_kill':True,'idempotent':before==after and all(s['attempts']==1 for s in resumed['steps']),'notification_count':len(notices),'completed':resumed['status']=='completed','capabilities':['crash_resume','timer_poll','completion_notification']}
            daemon_report['passed']=resume_step==4 and daemon_report['completed'] and daemon_report['idempotent'] and len(notices)==1
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=10)

        reports={'skill_report':skill,'custom_report':custom_report,'daemon_report':daemon_report}
        if include_http:
            reports['mcp_report']=await inspect_http(work,root,options)
        for name,value in reports.items():atomic_json(output/(name+'.json'),value)
        reports['passed']=all(value.get('passed') for value in reports.values())
        return reports


async def inspect_http(work,root,options):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    token=secrets.token_urlsafe(24)
    env=child_environment();env['CODEDESK_MCP_TOKEN']=token
    process=subprocess.Popen(child_command()+['mcp','--workspace',str(work),'--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**options)
    try:
        async with httpx.AsyncClient(trust_env=False,timeout=2) as client:
            deadline=time.monotonic()+20
            while True:
                try:
                    response=await client.post(f'http://127.0.0.1:{port}/mcp',json={})
                    if response.status_code==401:break
                except httpx.HTTPError:
                    pass
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('MCP HTTP service failed to start')
                await asyncio.sleep(.1)
            bad_origin=await client.post(f'http://127.0.0.1:{port}/mcp',headers={'Authorization':'Bearer '+token,'Origin':'https://untrusted.invalid'},json={})
        config={'local':{'transport':'streamable-http','url':f'http://127.0.0.1:{port}/mcp','headers':{'Authorization':'Bearer '+token}}}
        mcp=MCP(config,work)
        definitions=await mcp.discover()
        result=await mcp.call(definitions[0]['function']['name'],{}) if definitions else {}
        return {'default_port':8001,'tested_port':port,'endpoint':'/mcp','transport':'streamable-http','unauthenticated_status':response.status_code,'bad_origin_status':bad_origin.status_code,'tools':len(definitions),'actual_call_ok':result.get('ok',False),'passed':response.status_code==401 and bad_origin.status_code==403 and result.get('ok',False)}
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=10)
