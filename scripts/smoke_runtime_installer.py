"""Functional unsigned-installer smoke test on a disposable Windows CI runner.

This is deliberately separate from the trusted-signature release gate.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from sign_windows import sha256
from verify_installation import require_no_installation,probe_application


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--installer',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('This unsigned functional smoke test is only for disposable CI. Use the signed installation acceptance script on release machines.')
    require_no_installation()
    with tempfile.TemporaryDirectory(prefix='CodeDesk install smoke ') as folder:
        root=Path(folder);installed=root/'application'
        subprocess.run([str(args.installer.resolve()),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/TASKS=',f'/DIR={installed}',f'/LOG={root / "install.log"}'],check=True,timeout=180)
        uninstaller=installed/'unins000.exe'
        try:
            manifest=json.loads((args.bundle/'portable-manifest.json').read_text(encoding='utf-8'))
            for record in manifest['files']:
                path=(installed/record['path']).resolve()
                if not path.is_relative_to(installed.resolve()) or not path.is_file() or sha256(path)!=record['sha256']:
                    raise RuntimeError('Installed-file mismatch: '+record['path'])
            command=[str(installed/'runtime/python.exe'),str(installed/'app/app.py')]
            probe_application(installed,root/'state',root/'application.log',command)
        finally:
            if uninstaller.is_file():
                subprocess.run([str(uninstaller),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],check=True,timeout=180)
                for _ in range(60):
                    if not (installed/'app/app.py').exists():break
                    time.sleep(.25)
        if (installed/'app/app.py').exists():raise RuntimeError('Uninstall left application files')
        require_no_installation()
        receipt={'status':'passed','scope':'functional_on_disposable_windows_runner','installer_sha256':sha256(args.installer),'checks':['install','installed_files','startup','ui_resources','sample_workspace','mcp_process','uninstall'],'trusted_signature_verified':False}
        output=args.installer.parent/'functional-installation.json'
        output.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps(receipt))


if __name__=='__main__':main()
