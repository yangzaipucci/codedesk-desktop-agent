"""Portable read-only diff collector; no shell interpolation."""
import argparse
import json
from pathlib import Path
import subprocess

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args()
    root=args.workspace.resolve()
    result={}
    for key,command in [('stat',['git','diff','--stat']),('diff',['git','diff','--no-ext-diff','--no-textconv','--unified=3'])]:
        value=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        result[key]={'exit_code':value.returncode,'stdout':value.stdout[:18000],'stderr':value.stderr[:2000]}
    print(json.dumps(result,ensure_ascii=True))
    return max(item['exit_code'] for item in result.values())
if __name__=='__main__':raise SystemExit(main())
