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
        assert [d['function']['name'] for d in definitions] == ['read','bash']
        self.turn += 1
        function = ('write', {'path':'review-probe.txt','content':'must not be created'}) if self.turn == 1 else ('read', {'path':'maths.py'})
        if self.turn <= 2:
            return {'role':'assistant','content':None,'tool_calls':[{'id':str(self.turn),'type':'function','function':{'name':function[0],'arguments':json.dumps(function[1])}}]}, {'total_tokens':10}
        return {'role':'assistant','content':'Read-only review completed; focused tests passed.'}, {'total_tokens':10}


async def inspect_patches(output,include_http=True):
    from agent.course_inspection import inspect_section
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    reports={}
    for section,filename in [('skills','skill_report'),('custom','custom_report'),('daemon','daemon_report')]:
        reports[filename]=await inspect_section(section,output/(filename+'.json'))
    if include_http:
        with tempfile.TemporaryDirectory(prefix='http-proof-',dir=output) as folder:
            root=Path(folder);work=root/'workspace';work.mkdir()
            options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            reports['mcp_report']=await inspect_http(work,root,options)
        atomic_json(output/'mcp_report.json',reports['mcp_report'])
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
