"""Patch acceptance, durable jobs and external MCP entry points."""
import argparse
import asyncio
import json
from pathlib import Path


def main(argv=None):
    parser=argparse.ArgumentParser(prog='CodeDesk')
    sub=parser.add_subparsers(dest='command',required=True)
    inspect=sub.add_parser('inspect',help='Run actual patch acceptance and print JSON')
    inspect.add_argument('--output',type=Path,default=Path('reports'))
    inspect.add_argument('--skip-http',action='store_true')
    mcp=sub.add_parser('mcp',help='Run the external MCP service')
    mcp.add_argument('--workspace',type=Path,default=Path.cwd())
    mcp.add_argument('--port',type=int,default=8001)
    mcp.add_argument('--transport',choices=['stdio','streamable-http'],default='streamable-http')
    daemon=sub.add_parser('daemon',help='Durable background jobs')
    daemon.add_argument('--state-dir',type=Path)
    actions=daemon.add_subparsers(dest='action',required=True)
    create=actions.add_parser('create');create.add_argument('--plan',type=Path,required=True)
    run=actions.add_parser('run');run.add_argument('id');run.add_argument('--step-delay',type=float,default=0)
    actions.add_parser('list')
    watch=actions.add_parser('watch');watch.add_argument('--interval',type=float,default=5);watch.add_argument('--once',action='store_true')
    args=parser.parse_args(argv)
    if args.command=='mcp':
        from agent.mcp_service import serve
        return serve(args.workspace,args.transport,args.port)
    if args.command=='inspect':
        from agent.inspection import inspect_patches
        try:
            result=asyncio.run(inspect_patches(args.output,not args.skip_http))
        except (ValueError,OSError,RuntimeError) as error:
            result={'passed':False,'error':str(error)[:500]}
        # ASCII escapes keep valid JSON on redirected legacy Windows consoles.
        print(json.dumps(result,ensure_ascii=True,indent=2))
        if not result['passed']:raise SystemExit(1)
        return result
    from agent.daemon import Daemon
    from agent.settings import Settings
    worker=Daemon(Settings(args.state_dir))
    if args.action=='create':result=worker.create(json.loads(args.plan.read_text(encoding='utf-8-sig')))
    elif args.action=='list':result=worker.summaries()
    elif args.action=='run':result=asyncio.run(worker.run(args.id,args.step_delay))
    else:result=asyncio.run(worker.watch(args.interval,args.once))
    # No model keys are printed. Job details may contain private project data.
    if result is not None:print(json.dumps(result,ensure_ascii=True,indent=2))
