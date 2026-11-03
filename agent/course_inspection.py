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
