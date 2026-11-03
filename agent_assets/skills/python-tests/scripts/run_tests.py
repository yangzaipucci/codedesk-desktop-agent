"""Focused unittest helper, invoked explicitly through the existing bash tool."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--workspace', type=Path, required=True)
parser.add_argument('--pattern', default='test_*.py')
args = parser.parse_args()
if not args.workspace.is_dir() or not re.fullmatch(r'[a-zA-Z0-9_*.-]+\.py', args.pattern):
    parser.error('Provide an existing workspace and a filename pattern ending in .py')
executable = Path(sys.executable)
if executable.name.lower() == 'pythonw.exe':
    executable = executable.with_name('python.exe')
env = dict(os.environ, CODEDESK_PROJECT_PYTHON='1')
result = subprocess.run([str(executable), '-m', 'unittest', 'discover', '-s', '.', '-p', args.pattern, '-v'], cwd=args.workspace.resolve(), env=env, timeout=60)
raise SystemExit(result.returncode)
