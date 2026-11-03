"""Headless baseline smoke usable in both source and portable installation."""
import asyncio
import base64
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile


async def selftest():
    from agent.tools import Tools,DEFINITIONS
    from agent.course_inspection import overrides
    from server.app import resources
    checks={}
    with tempfile.TemporaryDirectory(prefix='codedesk-selftest-') as folder:
        root=Path(folder)
        with overrides(CODEDESK_LEGACY=1):
            tools=Tools(root,root/'state')
            written=await tools.execute('write',{'path':'nested/source.py','content':'value = 1\nvalue = 2\n'})
            checks['atomic_write_creates_parents']=written.get('ok') and written.get('new_lines')==2
            read=await tools.execute('read',{'path':'nested/source.py','offset':2,'limit':1})
            checks['read_pagination']=read.get('ok') and 'value = 2' in read.get('text','')
            edited=await tools.execute('edit',{'path':'nested/source.py','old':'value = 1','new':'value = 3'})
            checks['unique_edit']=edited.get('ok') and 'value = 3' in (root/'nested/source.py').read_text()
            duplicate=await tools.execute('edit',{'path':'nested/source.py','old':'value','new':'other'})
            checks['ambiguous_edit_denied']=not duplicate.get('ok')
            (root/'pixel.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1cAAAAASUVORK5CYII='))
            image=await tools.execute('read',{'path':'pixel.png'})
            checks['image_multimodal']=any(c.get('type')=='image' for c in image.get('content',[]))
            quote=(lambda s: "'"+str(s).replace("'","''")+"'") if os.name=='nt' else shlex.quote
            command=('& ' if os.name=='nt' else '')+quote(sys.executable)+' -c '+quote("print('baseline-ok')")
            result=await tools.execute('bash',{'command':command,'timeout':10})
            checks['bash_real_subprocess']=result.get('ok') and 'baseline-ok' in result.get('stdout','')
            checks['exact_four_builtins']={d['function']['name'] for d in DEFINITIONS}=={'read','write','edit','bash'}
            checks['ui_packaged']=(resources()/'ui/index.html').is_file()
    return {'passed':all(checks.values()),'checks':checks,'test_tier':'actual tools with optional increments disabled'}


if __name__=='__main__':
    report=asyncio.run(selftest())
    print(json.dumps(report,ensure_ascii=True,indent=2))
    raise SystemExit(0 if report['passed'] else 1)
