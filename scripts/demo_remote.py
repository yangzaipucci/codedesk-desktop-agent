"""Explicit, isolated controlled demonstration; never uses a real model key."""
import argparse
import asyncio
import csv
import io
import json
import re
import sys
import shutil
import socket
import tempfile
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent.runtime import Runtime
from agent.settings import Settings
from server.app import create_app


class DemoProvider:
    def __init__(self):self.step=0
    async def complete(self,messages,tools,emit):
        self.step+=1
        await asyncio.sleep(2)
        prompt='\n'.join(m['content'] for m in messages if m['role']=='user' and isinstance(m.get('content'),str))
        if self.step == 1:
            uploaded = re.search(r'^([.]codedesk/inbox/[^\n]+[.]csv)$', prompt, re.MULTILINE)
            self.source = uploaded.group(1) if uploaded else 'experiment.csv'
            call={'id':'read'+str(self.step),'type':'function','function':{'name':'read','arguments':json.dumps({'path':self.source})}}
            return {'role':'assistant','content':None,'tool_calls':[call]}, {'total_tokens':30}
        observation=next((json.loads(m['content']) for m in messages if m['role']=='tool' and '"text"' in m['content']),{})
        raw='\n'.join(re.sub(r'^\s*\d+  ','',line) for line in observation.get('text','').splitlines())
        rows=list(csv.DictReader(io.StringIO(raw)))
        deltas=[float(row['baseline_tv'])-float(row['method_tv']) for row in rows]
        summary='# 实验数据检查\n\n这是受控演示数据，不是论文实测结果。\n\n'
        summary+='读取 %d 个题项；平均 TV 改善 %.4f。\n\n'%(len(rows),sum(deltas)/len(deltas))
        summary+='| 题项 | 基线 TV | 方法 TV | 改善值 |\n|---|---:|---:|---:|\n'
        summary+='\n'.join('| %s | %s | %s | %.4f |'%(r['item'],r['baseline_tv'],r['method_tv'],d) for r,d in zip(rows,deltas))
        if '中文' in prompt:summary+='\n\n已按要求使用中文说明。'
        if self.step==2 and any(t['function']['name']=='write' for t in tools):
            folder = re.search(r'\.codedesk/outputs/[a-f0-9]+/',prompt)
            output = (folder[0] if folder else '') + '实验检查报告.md'
            call={'id':'write-report','type':'function','function':{'name':'write','arguments':json.dumps({'path':output,'content':summary},ensure_ascii=False)}}
            return {'role':'assistant','content':None,'tool_calls':[call]}, {'total_tokens':30}
        await emit({'type':'assistant_delta','text':summary})
        return {'role':'assistant','content':summary},{'total_tokens':30}


def make_demo(directory):
    settings=Settings(directory/'state')
    settings.memory_keys[settings._account()] = ''  # Demonstrations never consult desktop credentials.
    work=directory/'demo-project';work.mkdir(parents=True,exist_ok=True)
    for sample in (ROOT/'sample_workspace').iterdir():
        if sample.is_file() and not (work/sample.name).exists():
            shutil.copy2(sample,work/sample.name)
    (work/'experiment.csv').write_text('item,baseline_tv,method_tv\na33,0.21,0.08\na36,0.19,0.07\na17,0.16,0.06\n',encoding='utf-8')
    settings.value.update(workspace=str(work),online_enabled=False,mcp_servers={})
    factory=lambda s:Runtime(s,DemoProvider())
    app=create_app(settings, runtime=factory(settings),remote_runtime_factory=factory)
    hub=app.state.remote
    hub.demonstration=True
    hub.configure({'users':['owner']})
    hub.project('演示项目',str(work),'agent','演示数据仅用于验证功能；中文回复。')
    return app


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8876)
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--restricted-host',action='store_true')
    args=parser.parse_args()
    if args.restricted_host:
        from offline_validation import configure
        configure()
    import uvicorn
    directory = args.directory or Path(tempfile.mkdtemp(prefix='CodeDesk-Demo-'))
    app = make_demo(directory.resolve())
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', args.port))
        port = listener.getsockname()[1]
        url = f'http://127.0.0.1:{port}/'
        print('Controlled demo:', url, flush=True)
        if args.open:
            async def show_demo():
                asyncio.get_running_loop().call_later(0.8, webbrowser.open, url)
            app.add_event_handler('startup', show_demo)
        config = uvicorn.Config(app, host='127.0.0.1', port=port, loop='none', log_level='warning')
        uvicorn.Server(config).run(sockets=[listener])
