"""Default to a signed release; unsigned builds require an explicit flag."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib

try:
    from .sign_windows import Signer, SigningError, installer_sign_command, sha256, verify_release
except ImportError:
    from sign_windows import Signer, SigningError, installer_sign_command, sha256, verify_release

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def compile_arguments(compiler, bundle, output, cache, version, signed):
    args = [str(compiler), f"/DAppVersion={version}", f"/DSourceRoot={bundle}", f"/DOutputRoot={output}"]
    if signed:
        command = installer_sign_command(Path(sys.executable), ROOT / "scripts/sign_windows.py")
        args += ["/DSignedBuild=1", f"/DSigningCache={cache}", f"/Scodedesk={command}"]
    else:
        args += ["/DUnsignedDevelopment=1"]
    return [*args, str(ROOT / "scripts/installer.iss")]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--iscc", type=Path, help="Path to Inno Setup ISCC.exe")
    parser.add_argument("--unsigned", action="store_true", help="Development only; never eligible for normal publication")
    parser.add_argument("--check-signing", action="store_true", help="Validate signing prerequisites without building")
    args = parser.parse_args(argv)
    if args.unsigned and args.check_signing:
        parser.error("--unsigned and --check-signing cannot be combined")
    # Fail before touching old builds if a release cannot be signed.
    signer = None if args.unsigned else Signer()
    if args.check_signing:
        print("签名证书、证书链和工具检查通过。")
        return
    mode = "unsigned" if args.unsigned else "signed"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if signer and subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise SigningError("正式签名构建要求工作区干净，请先提交要发布的源码和文档。")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8-sig"))["project"]["version"]
    temp = ROOT / ".build-temp"
    compiler = args.iscc or next((p for p in [Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"), temp / "inno/ISCC.exe"] if p.is_file()), None)
    if compiler is None or not compiler.is_file():
        raise SigningError("未找到Inno Setup编译器。请使用--iscc指定ISCC.exe。")
    stage = ROOT / "build" / mode
    output = ROOT / "release" / mode / version
    temp.mkdir(exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = str(temp)
    common = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--specpath", stage, "--workpath", stage / "work"]
    # A directory helper exposes every loaded DLL/PYD to the signing pass.
    # A signed one-file wrapper could otherwise conceal unsigned native modules.
    run(*common, "--onedir", "--console", "--name", "WorkspaceMCP", "--distpath", stage / "helper", "mcp_demo.py")
    run(*common, '--onedir', '--console', '--name', 'OnlineMCP', '--distpath', stage / 'online', 'mcp_network.py')
    helper = stage / "helper/WorkspaceMCP"
    online = stage / 'online/OnlineMCP'
    run(*common, "--onedir", "--windowed", "--name", "CodeDesk", "--distpath", stage / "application", "--add-data", f"{ROOT / 'ui'};ui", "--add-data", f"{ROOT / 'sample_workspace'};sample_workspace", "--add-data", f"{helper};mcp/WorkspaceMCP", "--add-data", f"{online};mcp/OnlineMCP", "--hidden-import", "keyring.backends.Windows", "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.asyncio", "--hidden-import", "uvicorn.protocols.http.h11_impl", "--hidden-import", "uvicorn.protocols.websockets.websockets_impl", "--hidden-import", "uvicorn.lifespan.on", "--exclude-module", "PyQt5", "--exclude-module", "PyQt6", "--exclude-module", "PySide6", "app.py")
    bundle = stage / "application/CodeDesk"
    binaries = signer.bundle(bundle) if signer else []
    cache = stage / "signed-uninstallers"
    if signer:
        cache.mkdir(parents=True, exist_ok=True)
        for existing in cache.iterdir():
            if existing.is_file() and existing.suffix.lower() in {".exe", ".e32"}:
                signer.verify(existing, own=True)
    run(*compile_arguments(compiler, bundle, output, cache, version, signer is not None))
    suffix = "" if signer else "-unsigned"
    installer = output / f"CodeDesk-Setup-{version}{suffix}.exe"
    if signer:
        signer.verify(installer, own=True)
    files = [{"path": p.relative_to(bundle).as_posix(), "sha256": sha256(p)} for p in sorted(bundle.rglob("*")) if p.is_file()]
    report = {"mode": mode, "version": version, "source_commit": revision, "created_utc": datetime.now(timezone.utc).isoformat(), "certificate_thumbprint": signer.info["thumbprint"] if signer else None, "signed_uninstaller": signer is not None, "installer": installer.name, "installer_sha256": sha256(installer), "binaries": binaries, "files": files}
    report_path = output / "signing-manifest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if signer:
        verify_release(bundle, installer, report_path)
    archive = output / f"CodeDesk-Portable-{version}-win64{suffix}"
    archive_path = Path(shutil.make_archive(str(archive), "zip", root_dir=bundle.parent, base_dir=bundle.name))
    artifacts = [installer, report_path, archive_path]
    (output / "SHA256SUMS.txt").write_text("\n".join(f"{sha256(p)}  {p.name}" for p in artifacts) + "\n", encoding="utf-8")
    print(f"输出目录：{output}")
    print("完整签名检查通过，下一步执行安装验收。" if signer else "未签名开发包：不得作为已验证正式安装版发布。")


if __name__ == "__main__":
    try:
        main()
    except (SigningError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
