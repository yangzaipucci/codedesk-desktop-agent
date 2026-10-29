"""Windows Authenticode signing using a certificate already in the OS store.

Private keys/passwords are never accepted as command arguments or written to disk.
This module changes no trust stores, application-control rules or system policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse

PE_SUFFIXES = {".exe", ".dll", ".pyd", ".e32"}


class SigningError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def powershell(script: str, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    result = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    if result.returncode:
        raise SigningError("无法读取Windows签名或证书信息；请在有权限的Windows账户中运行。")
    try:
        return json.loads(result.stdout.lstrip("\ufeff"))
    except ValueError as error:
        raise SigningError("Windows没有返回有效的签名信息。") from error


def signature(path: Path) -> dict:
    script = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$sig=Get-AuthenticodeSignature -LiteralPath $env:CODEDESK_SIGN_FILE
[ordered]@{status=$sig.Status.ToString();subject=$sig.SignerCertificate.Subject;thumbprint=$sig.SignerCertificate.Thumbprint;timestamped=($null -ne $sig.TimeStamperCertificate)} | ConvertTo-Json -Compress
'''
    return powershell(script, {"CODEDESK_SIGN_FILE": str(path.resolve())})


def certificate(thumbprint: str) -> dict:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", thumbprint):
        raise SigningError("证书指纹必须是40位十六进制SHA1值。")
    script = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$location=if($env:CODEDESK_SIGN_STORE -eq 'machine'){'Cert:\LocalMachine\My'}else{'Cert:\CurrentUser\My'}
$cert=Get-Item -LiteralPath (Join-Path $location $env:CODEDESK_SIGN_CERT_SHA1) -ErrorAction Stop
$codeSigning=@($cert.EnhancedKeyUsageList | Where-Object {$_.ObjectId -eq '1.3.6.1.5.5.7.3.3'}).Count -gt 0
$chain=[Security.Cryptography.X509Certificates.X509Chain]::new()
$chain.ChainPolicy.RevocationMode=[Security.Cryptography.X509Certificates.X509RevocationMode]::Online
$chain.ChainPolicy.UrlRetrievalTimeout=[TimeSpan]::FromSeconds(20)
$trusted=$chain.Build($cert)
[ordered]@{subject=$cert.Subject;thumbprint=$cert.Thumbprint;private_key=$cert.HasPrivateKey;code_signing=$codeSigning;valid_now=($cert.NotBefore -le (Get-Date) -and $cert.NotAfter -gt (Get-Date));self_signed=($cert.Subject -eq $cert.Issuer);trusted=$trusted;chain_errors=@($chain.ChainStatus | ForEach-Object {$_.Status.ToString()})} | ConvertTo-Json -Compress
'''
    result = powershell(script, {"CODEDESK_SIGN_CERT_SHA1": thumbprint})
    for field, message in [("private_key", "证书没有可用私钥。"), ("code_signing", "证书用途不是代码签名。"), ("valid_now", "证书尚未生效或已经过期。"), ("trusted", "证书链/吊销检查未通过，不能作为正式发布证书。")]:
        if not result.get(field):
            raise SigningError(message)
    if result.get("self_signed"):
        raise SigningError("不接受自签名证书作为正式发布者证书。")
    return result


def find_signtool() -> Path:
    value = os.environ.get("CODEDESK_SIGNTOOL")
    if value:
        path = Path(value).resolve()
        if not path.is_file():
            raise SigningError("CODEDESK_SIGNTOOL 指定的文件不存在。")
        return path
    if value := shutil.which("signtool.exe"):
        return Path(value)
    root = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits/10/bin"
    candidates = sorted(root.glob("*/x64/signtool.exe"), reverse=True)
    if not candidates:
        raise SigningError("未找到Windows SDK的signtool.exe；请安装SDK签名工具，或设置CODEDESK_SIGNTOOL。")
    return candidates[0]


def run_tool(arguments):
    result = subprocess.run([str(part) for part in arguments], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode != 0:
        # Code 2 is a timestamp/verification warning, not a successful release.
        raise SigningError("签名或校验工具未成功完成：" + (result.stderr or result.stdout)[-1600:])


class Signer:
    def __init__(self):
        thumbprint = os.environ.get("CODEDESK_SIGN_CERT_SHA1", "").replace(" ", "")
        if not thumbprint:
            raise SigningError("未配置受信任的代码签名证书：请设置CODEDESK_SIGN_CERT_SHA1；没有证书时只能构建--unsigned开发包。")
        self.info = certificate(thumbprint)
        self.thumbprint = thumbprint
        self.tool = find_signtool()
        self.timestamp = os.environ.get("CODEDESK_TIMESTAMP_URL", "http://timestamp.digicert.com")
        endpoint = urlparse(self.timestamp)
        if endpoint.scheme not in {"http", "https"} or not endpoint.hostname or endpoint.username or endpoint.password:
            raise SigningError("时间戳服务地址无效。")

    def verify(self, path: Path, own=False) -> dict:
        run_tool([self.tool, "verify", "/pa", "/all", path])
        info = signature(path)
        if info.get("status") != "Valid":
            raise SigningError(f"文件签名不受本机信任：{path.name}")
        if own and (str(info.get("thumbprint", "")).lower() != self.thumbprint.lower() or not info.get("timestamped")):
            raise SigningError(f"本项目文件没有使用指定证书和可信时间戳：{path.name}")
        return info

    def sign(self, path: Path):
        path = Path(path).resolve()
        if not path.is_file():
            raise SigningError(f"找不到待签名文件：{path}")
        args = [self.tool, "sign", "/s", "My", "/sha1", self.thumbprint, "/fd", "SHA256", "/tr", self.timestamp, "/td", "SHA256", "/d", "CodeDesk"]
        if os.environ.get("CODEDESK_SIGN_STORE") == "machine":
            args.append("/sm")
        run_tool([*args, path])
        return self.verify(path, own=True)

    def bundle(self, directory: Path):
        records = []
        files = sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in PE_SUFFIXES)
        if not files:
            raise SigningError("没有找到应用二进制。")
        for path in files:
            info = signature(path)
            if info.get("status") == "NotSigned":
                info = self.sign(path)
            elif info.get("status") == "Valid":
                info = self.verify(path)
            else:
                raise SigningError(f"第三方文件签名异常，先检查依赖来源：{path.name}")
            records.append({"path": path.relative_to(directory).as_posix(), "sha256": sha256(path), **info})
        return records


def installer_sign_command(python: Path, script: Path) -> str:
    def quote(path):
        return "$q" + str(path).replace("$", "$$") + "$q"
    return f"{quote(python)} {quote(script)} sign $f"


def verify_release(directory: Path, installer: Path, report: Path):
    data = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("mode") != "signed" or data.get("signed_uninstaller") is not True:
        raise SigningError("不是完整签名构建，禁止正式发布。")
    records = data.get("binaries")
    fingerprint = str(data.get("certificate_thumbprint", ""))
    if not re.fullmatch(r"[0-9a-fA-F]{40}", fingerprint) or not isinstance(records, list) or not records:
        raise SigningError("签名报告缺少证书或应用二进制记录。")
    if data.get("installer") != installer.name or not directory.is_dir():
        raise SigningError("签名报告与待发布目录/安装包不一致。")
    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise SigningError("缺少完整应用资源清单。")
    resources = set()
    for record in files:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str) or record["path"] in resources:
            raise SigningError("应用资源清单无效。")
        resources.add(record["path"])
        path = (directory / record["path"]).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file() or sha256(path) != record.get("sha256"):
            raise SigningError("应用资源与签名构建报告不一致。")
    if resources != {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}:
        raise SigningError("存在未登记或缺失的应用资源。")
    if sha256(installer) != data.get("installer_sha256"):
        raise SigningError("安装包与签名构建报告不一致。")
    tool = find_signtool()
    names = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str) or record["path"] in names:
            raise SigningError("应用二进制清单无效或存在重复项。")
        names.add(record["path"])
        path = (directory / record["path"]).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file() or path.suffix.lower() not in PE_SUFFIXES or sha256(path) != record.get("sha256"):
            raise SigningError("应用二进制与构建报告不一致。")
        run_tool([tool, "verify", "/pa", "/all", path])
        info = signature(path)
        if info.get("status") != "Valid":
            raise SigningError("应用二进制签名校验失败。")
        if str(info.get("thumbprint", "")).lower() == fingerprint.lower() and not info.get("timestamped"):
            raise SigningError("项目二进制缺少可信时间戳。")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in PE_SUFFIXES}
    if actual != names:
        raise SigningError("存在未登记的应用二进制。")
    run_tool([tool, "verify", "/pa", "/all", installer])
    setup = signature(installer)
    if setup.get("status") != "Valid" or not setup.get("timestamped") or str(setup.get("thumbprint", "")).lower() != fingerprint.lower():
        raise SigningError("安装包签名或时间戳校验失败。")
    return data


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("check")
    sign = sub.add_parser("sign"); sign.add_argument("file", type=Path)
    verify = sub.add_parser("verify-release")
    verify.add_argument("--directory", type=Path, required=True)
    verify.add_argument("--installer", type=Path, required=True)
    verify.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "verify-release":
        verify_release(args.directory, args.installer, args.report)
        print("签名发布检查通过；仍须在目标Windows策略下完成安装验收。")
    else:
        signer = Signer()
        if args.mode == "sign":
            signer.sign(args.file)
        else:
            print("证书和签名工具检查通过。")


if __name__ == "__main__":
    try:
        main()
    except (SigningError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
