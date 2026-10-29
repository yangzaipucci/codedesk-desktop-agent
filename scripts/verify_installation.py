"""Install/start/uninstall an already signed build in an isolated test directory."""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

try:
    from .sign_windows import SigningError, find_signtool, run_tool, sha256, signature, verify_release
except ImportError:
    from sign_windows import SigningError, find_signtool, run_tool, sha256, signature, verify_release

ROOT = Path(__file__).resolve().parents[1]
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{7F648483-55EC-49C4-9DFA-DC8447AD9DB7}_is1"


def require_no_installation():
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | view):
                    raise SigningError("已有CodeDesk安装记录；请在干净的Windows测试账户/虚拟机验收，避免覆盖现有安装。")
            except FileNotFoundError:
                pass


def verify_installed(directory, bundle, fingerprint):
    for original in bundle.rglob("*"):
        if original.is_file():
            installed = directory / original.relative_to(bundle)
            if not installed.is_file() or sha256(installed) != sha256(original):
                raise SigningError("安装后的应用文件与签名构建不一致。")
    uninstaller = directory / "unins000.exe"
    run_tool([find_signtool(), "verify", "/pa", "/all", uninstaller])
    info = signature(uninstaller)
    if info.get("status") != "Valid" or not info.get("timestamped") or str(info.get("thumbprint", "")).lower() != fingerprint.lower():
        raise SigningError("安装后的卸载器签名或时间戳无效。")
    return uninstaller


def probe_application(directory, state, log, command=None):
    # Reserve a free local port briefly. Startup failure is caught, never hidden.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, CODEDESK_DATA_DIR=str(state))
    opener = build_opener(ProxyHandler({}))
    base = f"http://127.0.0.1:{port}"
    with log.open("wb") as output:
        process = subprocess.Popen([*(command or [str(directory / "CodeDesk.exe")]), "--headless", "--port", str(port)], env=env, stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 45
            while True:
                if process.poll() is not None:
                    raise SigningError("安装后的应用提前退出。请检查本地验收日志和Windows应用程序控制日志。")
                try:
                    with opener.open(base, timeout=2) as response:
                        html = response.read().decode("utf-8")
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise SigningError("安装后的应用启动超时。")
                    time.sleep(0.25)
            match = re.search(r'<meta name="session-token" content="([^"]+)"', html)
            if not match:
                raise SigningError("安装后界面资源无效。")
            headers = {"Authorization": "Bearer " + match[1]}

            def request(path, post=False):
                req = Request(base + path, headers=headers, data=b"{}" if post else None)
                if post:
                    req.add_header("Content-Type", "application/json")
                with opener.open(req, timeout=90) as response:
                    return json.load(response)

            request("/api/settings")
            if not request("/api/files").get("files"):
                raise SigningError("安装后默认示例项目缺失。")
            request("/api/mcp/demo", post=True)
            result = request("/api/mcp/test", post=True)
            if not result.get("demo_call", {}).get("ok"):
                raise SigningError("安装后独立MCP程序调用失败。")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def accept(bundle, installer, report):
    data = verify_release(bundle, installer, report)
    require_no_installation()
    trial = ROOT / ".build-temp" / ("acceptance-" + uuid4().hex)
    trial.mkdir(parents=True)
    directory = trial / "application"
    receipt_path = report.parent / "installation-acceptance.json"
    # Clear any stale successful receipt before invoking the installer.
    receipt = {"status": "running", "installer_sha256": sha256(installer), "created_utc": datetime.now(timezone.utc).isoformat(), "checks": []}
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    env = dict(os.environ, TEMP=str(trial), TMP=str(trial))
    uninstaller = None
    try:
        subprocess.run([str(installer.resolve()), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS", "/TASKS=", f"/DIR={directory}", f"/LOG={trial / 'install.log'}"], env=env, check=True, timeout=180)
        uninstaller = verify_installed(directory, bundle, data["certificate_thumbprint"])
        receipt["checks"].extend(["install", "installed_files", "signed_uninstaller"])
        probe_application(directory, trial / "state", trial / "application.log")
        receipt["checks"].extend(["startup", "ui_resources", "sample_workspace", "mcp_process"])
    except BaseException as error:
        receipt.update(status="failed", reason=str(error)[:1000])
        raise
    finally:
        try:
            # Only run an uninstaller after its signature has passed validation.
            if uninstaller is not None:
                subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={trial / 'uninstall.log'}"], env=env, check=True, timeout=180)
                deadline = time.monotonic() + 30
                while (directory / "CodeDesk.exe").exists() and time.monotonic() < deadline:
                    time.sleep(0.25)
                if (directory / "CodeDesk.exe").exists():
                    raise SigningError("卸载后仍残留应用入口。")
                require_no_installation()
                receipt["checks"].append("uninstall")
            if receipt["status"] == "running":
                receipt["status"] = "passed"
        except BaseException as error:
            receipt.update(status="failed", reason="卸载验收失败：" + str(error)[:800])
            raise
        finally:
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print("安装验收记录：" + str(accept(args.directory.resolve(), args.installer.resolve(), args.report.resolve())))


if __name__ == "__main__":
    try:
        main()
    except (SigningError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
