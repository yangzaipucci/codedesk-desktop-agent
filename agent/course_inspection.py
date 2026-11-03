"""Reproducible assignment evidence with explicit test tiers and real tool effects."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from agent.capabilities import atomic_json, assets, enabled
from agent.settings import Settings
from agent.skills import Skills
from agent.tokens import TOKEN_MEASURE


@contextmanager
def overrides(**values):
    old = {key: os.environ.get(key) for key in values}
    os.environ.update({key: str(value) for key,value in values.items()})
    try:
        yield
    finally:
        for key,value in old.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value


def setup(root):
    work = root/'project';work.mkdir()
    state = Settings(root/'state')
    state.save({'workspace': str(work), 'online_enabled': False})
    return work,state


async def skills_report(root):
    from agent.runtime import Runtime
    from agent.course_fixtures import DiffProvider
    work,state = setup(root)
    registry = Skills(work,state.directory)
    queries = [('帮我跑测试','run-tests'),('帮我审一遍diff','review-diff'),('查询Issue 的状态','fetch-issue'),('请检查代码','code-review'),('请运行测试','python-tests'),('检索文献并列出 DOI','web-research'),('你好',None),('今天几号',None),('不要跑测试，只解释语法',None)]
    trials = []
    for query,expected in queries:
        selected = registry.select(query)
        hit = selected[0] if len(selected)==1 else selected or None
        trials.append({'query':query,'expected':expected,'hit':hit,'ok':hit==expected})
    no_bodies = all(item['body'].strip() not in registry.catalog() for item in registry.entries.values())
    registry.use_skill('review-diff')
    (work/'README.md').write_text('Use git diff --stat and git diff to inspect changes.\n',encoding='utf-8')
    (work/'AGENTS.md').write_text('Build and test: python -m unittest discover -q.\n',encoding='utf-8')
    (work/'example.py').write_text('value = 1\n',encoding='utf-8')
    for command in (['git','init','-q'],['git','add','README.md','AGENTS.md','example.py']):
        subprocess.run(command,cwd=work,check=True,capture_output=True)
    (work/'example.py').write_text('value = 2\n',encoding='utf-8')
    runs=[]
    query='帮我审一遍diff，列出改动统计和完整差异，不修改文件。'
    for flag in (0,1):
        events=[]
        async def sink(event): events.append(event)
        with overrides(ENABLE_SKILLS=flag,ENABLE_CUSTOM=0):
            runtime=Runtime(state,DiffProvider())
            await runtime.run(query,sink)
        calls=[e for e in events if e['type']=='tool_start']
        results=[e for e in events if e['type']=='tool_result']
        runs.append({'enable_skills':flag,'query':query,'tool_calls':len(calls),'tool_rounds':len(calls),'completed':events[-1].get('status')=='completed','all_tools_ok':all(e['result'].get('ok') for e in results),'tool_names':[e['name'] for e in calls]})
    report={**registry.metrics(),'trials':trials,'false_positive':sum(t['hit'] is not None for t in trials if t['expected'] is None),'catalog_has_no_bodies':no_bodies,'loaded_on_demand':registry.loaded,'before_after':{'test_tier':'controlled_provider_with_real_git_and_script','same_code':True,'runs':runs,'saved_tool_calls':runs[0]['tool_calls']-runs[1]['tool_calls']},'token_measure':TOKEN_MEASURE}
    # Real MCP IPC is separately verified, rather than mistaking description text for a call.
    from agent.mcp_client import MCP
    import sys
    helper=Path(__file__).resolve().parents[1]/'mcp_demo.py'
    mcp=MCP({'skills-proof':{'command':sys.executable,'args':[str(helper)]}},work)
    definitions=await mcp.discover()
    result=await mcp.call(definitions[0]['function']['name'],{}) if definitions else {}
    report['mcp_execution']={'transport':'stdio','actual_call_ok':result.get('ok',False),'tools_found':len(definitions)}
    report['false_positives']=report['false_positive']
    report['passed']=len(registry.entries)>=3 and report['disclosure_ratio']>=5 and no_bodies and all(t['ok'] for t in trials) and report['false_positive']==0 and all(r['completed'] and r['all_tools_ok'] and r['tool_calls']>0 for r in runs) and report['before_after']['saved_tool_calls']>0 and result.get('ok',False)
    return report


async def inspect_section(section,out):
    if not enabled(section if section!='custom' else 'custom', Path(out).parent):
        report={'passed':False,'status':'disabled','section':section}
        atomic_json(out,report)
        return report
    out=Path(out).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='course-'+section+'-',dir=out.parent) as folder:
        root=Path(folder)
        if section=='skills':report=await skills_report(root)
        elif section=='custom':report=await custom_report(root)
        else:report=await daemon_report(root)
    atomic_json(out,report)
    return report


def prepare_repair(work):
    source=Path(__file__).resolve().parents[1]/'sample_workspace'
    for name in ('stats.py','test_stats.py'):
        shutil.copy2(source/name,work/name)
    shutil.copy2(assets()/'project-AGENTS.md',work/'AGENTS.md')
    subprocess.run(['git','init','-q'],cwd=work,check=True,capture_output=True)
    subprocess.run(['git','add','stats.py','test_stats.py','AGENTS.md'],cwd=work,check=True,capture_output=True)


async def custom_report(root):
    from agent.capabilities import project_guidance
    from agent.course_fixtures import RepairProvider,ReviewProvider
    from agent.reviewer import Reviewer
    from agent.runtime import Runtime
    from agent.tools import Tools
    from agent.tokens import count_tokens
    work,state=setup(root)
    prepare_repair(work)
    shutil.copy2(assets()/'AGENTS.md',state.directory/'AGENTS.md')
    nested=work/'nested';nested.mkdir()
    guidance,sources=project_guidance(nested,state.directory)
    rule_report={'found':{s['layer'] for s in sources}=={'global','project'},'bytes':sum(s['bytes'] for s in sources),'layers':[s['layer'] for s in sources],'injected_bytes':len(guidance.encode('utf-8')),'parent_search':any(s['layer']=='project' for s in sources),'truncated':any(s['truncated'] for s in sources)}
    tools=Tools(work,state.directory)
    denied=[]
    for name,args in [('write',{'path':'.env','content':'PLACEHOLDER'}),('write',{'path':'secret.pem','content':'PLACEHOLDER'}),('bash',{'command':'rm -rf build/'}),('bash',{'command':'git push --force'}),('bash',{'command':'git reset --hard'})]:
        # Test the pre-tool policy only; rejected commands are never executed.
        from agent.hooks import PolicyDenied
        try:
            tools.hooks.before(name,args)
            denied.append({'tool':name,**{k:v for k,v in args.items() if k!='content'},'reason':'','denied':False})
        except PolicyDenied as error:
            denied.append({'tool':name,**{k:v for k,v in args.items() if k!='content'},'reason':str(error),'denied':True})
    tests=[];runs=[]
    for index in range(2):
        # Restore an independent scenario; only the controlled agent applies fixes.
        shutil.copy2(Path(__file__).resolve().parents[1]/'sample_workspace/stats.py',work/'stats.py')
        provider=RepairProvider();runtime=Runtime(state,provider)
        events=[]
        async def sink(event):events.append(event)
        await runtime.run('修复 mean([]) 应返回 0 的问题，依据自动测试结果修正，保持正常输入行为。',sink)
        observations=[e['result']['autotest'] for e in events if e['type']=='tool_result' and 'autotest' in e['result']]
        tests.extend(observations)
        runs.append({'completed':events[-1].get('status')=='completed','agent_observed_red':provider.red_seen,'statuses':[x['status'] for x in observations]})
    red=sum(t['status']=='failed' for t in tests);green=sum(t['status']=='passed' for t in tests)
    red_to_green=sum(r['agent_observed_red'] and r['statuses']==['failed','passed'] for r in runs)
    (work/'stats.py').write_text((work/'stats.py').read_text(encoding='utf-8')+'\n# TODO: remove debug residue\n',encoding='utf-8')
    review=await Reviewer(state,ReviewProvider()).review('审查 mean 空输入修复，检查五项清单。',['stats.py'],tools)
    report={'agents_md':rule_report,'denied':denied,'autotest':{'runs':len(tests),'red':red,'green':green,'red_to_green':red_to_green,'injected_lines':max((t.get('injected_lines',0) for t in tests),default=0),'transitions':runs,'observations':tests},'reviewer':{'runs':1,'issues_found':int('新增差异包含' in review.get('summary','')),'main_context_delta':review.get('main_context_delta',0),'subagent_tokens':review.get('subagent_tokens',0),'context_isolated':review.get('context_isolated',False),'denied_writes':review.get('denied_writes',0),'diff_calls':review.get('diff_calls',0),'checklist':review.get('checklist',[]),'summary':review.get('summary','')},'test_tier':'controlled_provider; real Runtime, file edits, unittest subprocess and git diff; not live model quality','token_measure':TOKEN_MEASURE}
    report['passed']=rule_report['found'] and rule_report['parent_search'] and rule_report['bytes']<=12000 and not rule_report['truncated'] and all(d['denied'] and d['reason'] and '替代方案' in d['reason'] for d in denied) and red_to_green>=1 and green>=1 and report['autotest']['injected_lines']<=3 and review.get('status')=='completed' and review.get('diff_calls',0)>=1 and report['reviewer']['issues_found']>=1 and review.get('denied_writes',0)>=1 and not (work/'review-probe.txt').exists() and 0<report['reviewer']['main_context_delta']<=500
    return report


async def daemon_report(root):
    from datetime import datetime,timezone,timedelta
    import sys,time
    from agent.daemon import Daemon
    from agent.inspection import child_command,child_environment
    from agent.scheduler import Scheduler
    from agent.course_fixtures import ScheduledTestProvider
    work,state=setup(root)
    worker=Daemon(state)
    job=worker.create({'name':'CodeDesk 增量验收：断点恢复','steps':[{'kind':'write','path':f'out/step-{i}.txt','content':f'step {i}\n'} for i in range(1,5)]})
    options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    process=subprocess.Popen(child_command()+['daemon','--state-dir',str(state.directory),'run',job['id'],'--step-delay','1'],env=child_environment(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**options)
    try:
        deadline=time.monotonic()+25
        while True:
            checkpoint=worker.get(job['id'])
            completed=[s for s in checkpoint['steps'] if s['status']=='completed']
            if len(completed)==3:break
            if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('无法在第3步后捕获断点，拒绝伪报恢复成功。')
            await asyncio.sleep(.05)
        before={p.name:(p.read_bytes().hex(),p.stat().st_mtime_ns) for p in (work/'out').glob('*.txt')}
        process.kill();process.wait(timeout=8)
        resume_from_step=next(s['number'] for s in checkpoint['steps'] if s['status']!='completed')
        recovered=await worker.run(job['id'])
        after={p.name:(p.read_bytes().hex(),p.stat().st_mtime_ns) for p in (work/'out').glob('*.txt') if p.name in before}
        await worker.run(job['id'])
        notices=worker.summaries()['notifications']
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=8)
    prepare_repair(work)
    path=work/'stats.py'
    path.write_text(path.read_text(encoding='utf-8').replace('    return sum(nums) / len(nums)','    return sum(nums) / len(nums) if nums else 0'),encoding='utf-8')
    at=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
    import yaml
    plan={'routines':[{'id':f'focused-test-{i}','skill':'run-tests','at':at,'prompt':'跑测试，只验证 test_stats.py，不修改代码。'} for i in range(1,4)]}
    routines=work/'routines.yaml';routines.write_text(yaml.safe_dump(plan,allow_unicode=True),encoding='utf-8')
    scheduler=Scheduler(state,provider_factory=lambda item:ScheduledTestProvider())
    early=await scheduler.tick(routines)
    await asyncio.sleep(1.1)
    # The crash-recovery task above exercises the actual OS notification once;
    # scheduled test tasks need not generate three redundant balloons.
    with overrides(ENABLE_NOTIFICATIONS=0):
        fired=await scheduler.tick(routines)
    again=await scheduler.tick(routines)
    native=notices[0].get('system_notification',{}) if notices else {}
    report={'triggers_fired':fired['triggers_fired'],'resume_from_step':resume_from_step,'notify_fired':native.get('accepted',False),'idempotent':before==after and all(s['attempts']==1 for s in recovered['steps']) and again['triggers_fired']==0 and len(notices)==1,'resume_step':resume_from_step,'steps_total':len(recovered['steps']),'hard_kill':True,'completed_before_kill':3,'completed':recovered['status']=='completed','notification_count':len(notices),'system_notification':native,'schedule':{'before_due':early['triggers_fired'],'after_due':fired,'repeat_tick':again['triggers_fired'],'test_tier':'controlled model; actual skill loading, unittest processes and durable queue'},'capabilities':['crash_resume','scheduled_skill','system_completion_notification'],'token_measure':TOKEN_MEASURE}
    report['passed']=resume_from_step==4 and report['completed'] and report['idempotent'] and early['triggers_fired']==0 and fired['triggers_fired']==3 and all(r['status']=='completed' and r['skill_loaded'] and r['tool_calls']>=2 for r in fired['runs'])
    report['qualified_capabilities']=['crash_resume','scheduled_skill']+(['system_completion_notification'] if report['notify_fired'] else [])
    return report
