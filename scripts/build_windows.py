"""Run from the repository root using the dedicated virtual environment."""
from pathlib import Path
import argparse
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iscc", help="Path to Inno Setup ISCC.exe")
    args = parser.parse_args()
    temp = ROOT / ".build-temp"
    temp.mkdir(exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = str(temp)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console", "--name", "WorkspaceMCP", "--specpath", "build", "mcp_demo.py")
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed", "--name", "CodeDesk", "--specpath", "build", "--add-data", f"{ROOT / 'ui'};ui", "--add-data", f"{ROOT / 'sample_workspace'};sample_workspace", "--add-data", f"{ROOT / 'dist/WorkspaceMCP.exe'};.", "--hidden-import", "keyring.backends.Windows", "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.asyncio", "--hidden-import", "uvicorn.protocols.http.h11_impl", "--hidden-import", "uvicorn.protocols.websockets.websockets_impl", "--hidden-import", "uvicorn.lifespan.on", "--exclude-module", "PyQt5", "--exclude-module", "PyQt6", "--exclude-module", "PySide6", "app.py")
    compiler = args.iscc
    if not compiler:
        candidates = [Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"), temp / "inno" / "ISCC.exe"]
        compiler = next((str(p) for p in candidates if p.exists()), None)
    if compiler:
        run(compiler, ROOT / "scripts/installer.iss")
        print("Installer: release/CodeDesk-Setup-1.0.0.exe")
    else:
        print("Portable application built: dist/CodeDesk/CodeDesk.exe")
        print("Install Inno Setup and compile scripts/installer.iss to create Setup.exe.")


if __name__ == "__main__":
    main()
