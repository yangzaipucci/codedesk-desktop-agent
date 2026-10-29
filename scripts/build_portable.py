"""Bundle application sources with the official, isolated Windows Python runtime."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import argparse
from zipfile import ZipFile

import httpx

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = '3.13.17'
EXCLUDE = {'altgraph','iniconfig','pefile','pluggy','pygments','pyinstaller','pyinstaller-hooks-contrib','pytest'}


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def download(url, path):
    with httpx.stream('GET',url,timeout=90,follow_redirects=True) as response:
        response.raise_for_status()
        with path.open('wb') as handle:
            for chunk in response.iter_bytes():handle.write(chunk)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--installer',action='store_true',help='Also compile an explicit unsigned preview installer')
    parser.add_argument('--iscc',type=Path)
    options=parser.parse_args()
    version=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    cache=ROOT/'.build-temp'/('python-'+PYTHON_VERSION)
    cache.mkdir(parents=True,exist_ok=True)
    os.environ['TEMP']=os.environ['TMP']=str(ROOT/'.build-temp')
    manifest_url=f'https://www.python.org/ftp/python/{PYTHON_VERSION}/windows-{PYTHON_VERSION}.json'
    metadata=httpx.get(manifest_url,timeout=30).json()
    distribution=next(item for item in metadata['versions'] if item['id']=='pythonembed-3.13-64')
    url=distribution['url']
    if not url.startswith(f'https://www.python.org/ftp/python/{PYTHON_VERSION}/'):
        raise RuntimeError('Unexpected Python distribution source')
    archive=cache/'python.zip'
    if not archive.is_file() or sha(archive)!=distribution['hash']['sha256']:
        download(url,archive)
    if sha(archive)!=distribution['hash']['sha256']:
        raise RuntimeError('Python archive checksum mismatch')
    runtime=cache/'runtime'
    if not (runtime/'python.exe').exists():
        with ZipFile(archive) as zipped:
            for name in zipped.namelist():
                if not (runtime/name).resolve().is_relative_to(runtime.resolve()):
                    raise RuntimeError('Unsafe Python archive path')
            zipped.extractall(runtime)
    (runtime/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../app\nimport site\n',encoding='utf-8')
    # Only user-entered project commands add their current directory to imports.
    (runtime/'sitecustomize.py').write_text("import os,sys\nif os.environ.get('CODEDESK_PROJECT_PYTHON')=='1':\n    sys.path[:0]=[os.getcwd(),os.path.join(os.getcwd(),'.codedesk-deps')]\n",encoding='utf-8')
    lines=[line for line in (ROOT/'requirements-lock.txt').read_text().splitlines() if line.split('==')[0].lower() not in EXCLUDE]
    requirements=cache/'requirements-runtime.txt'
    requirements.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    target=runtime/'Lib/site-packages'
    marker=cache/'dependencies.sha256'
    required=sha(requirements)
    if not marker.exists() or marker.read_text()!=required:
        wheels=cache/'wheels'
        wheels.mkdir(exist_ok=True)
        subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--wheel-dir',str(wheels),'proxy-tools==0.1.0'],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-deps','--find-links',str(wheels),'--only-binary=:all:','--platform','win_amd64','--python-version','313','--implementation','cp','--abi','cp313','--target',str(target),'--upgrade','-r',str(requirements)],cwd=ROOT,check=True)
        marker.write_text(required)
    destination=ROOT/'build/portable'/version/'CodeDesk'
    destination.mkdir(parents=True,exist_ok=True)
    for item in runtime.rglob('*'):
        if item.is_file() and '__pycache__' not in item.parts:
            target_file=destination/'runtime'/item.relative_to(runtime)
            if not target_file.exists() or sha(item)!=sha(target_file):
                target_file.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(item,target_file)
    application=destination/'app'
    # This is generated application staging, never a user workspace.
    if application.exists():
        if not application.resolve().is_relative_to((ROOT/'build/portable').resolve()):
            raise RuntimeError('Refusing to replace a non-build directory')
        for child in application.iterdir():
            if child.is_dir():shutil.rmtree(child)
            else:child.unlink()
    application.mkdir(exist_ok=True)
    for name in ['agent','server','ui','sample_workspace']:
        shutil.copytree(ROOT/name,application/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['app.py','mcp_demo.py','mcp_network.py','LICENSE']:
        shutil.copy2(ROOT/name,application/name)
    (destination/'Start-CodeDesk.cmd').write_text('@echo off\nsetlocal\ncd /d "%~dp0"\nstart "" "%~dp0runtime\\pythonw.exe" "%~dp0app\\app.py"\n',encoding='ascii')
    (destination/'使用说明.txt').write_text('双击 Start-CodeDesk.cmd 打开 CodeDesk。\n完整保留 app 和 runtime 文件夹。\n在桌面设置中选择模型服务并填写自己的 API Key。\n支持浅深主题、多标签编辑、项目搜索、文件上下文、终端和五种助手模式。\n',encoding='utf-8-sig')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report={'version':version,'source_commit':revision,'python_version':PYTHON_VERSION,'python_source':url,'python_archive_sha256':sha(archive),'created_utc':datetime.now(timezone.utc).isoformat(),'files':[{ 'path':p.relative_to(destination).as_posix(),'sha256':sha(p)} for p in sorted(destination.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]}
    (destination/'portable-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    output=ROOT/'release/portable'/version
    output.mkdir(parents=True,exist_ok=True)
    zipped=output/f'CodeDesk-Portable-{version}-win64.zip'
    from zipfile import ZIP_DEFLATED
    with ZipFile(zipped,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive_out:
        for item in sorted(destination.rglob('*')):
            if item.is_file() and '__pycache__' not in item.parts:
                archive_out.write(item,item.relative_to(destination.parent).as_posix())
    (output/'SHA256SUMS.txt').write_text(sha(zipped)+'  '+zipped.name+'\n',encoding='utf-8')
    if options.installer:
        compiler=options.iscc or next((p for p in [ROOT/'.build-temp/inno/ISCC.exe',Path(r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'),Path(r'C:\Program Files\Inno Setup 6\ISCC.exe')] if p.is_file()),None)
        if compiler is None:raise RuntimeError('Use --iscc to specify the Inno Setup compiler.')
        subprocess.run([str(compiler),f'/DAppVersion={version}',f'/DSourceRoot={destination}',f'/DOutputRoot={output}','/DUnsignedDevelopment=1','/DRuntimeBundle=1',str(ROOT/'scripts/installer.iss')],cwd=ROOT,check=True)
        installer=output/f'CodeDesk-Setup-{version}-unsigned.exe'
        with (output/'SHA256SUMS.txt').open('a',encoding='utf-8') as sums:sums.write(sha(installer)+'  '+installer.name+'\n')
    print(json.dumps({'folder':str(destination),'zip':str(zipped),'bytes':zipped.stat().st_size},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
