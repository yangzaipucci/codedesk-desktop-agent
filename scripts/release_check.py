"""Validate release artifacts and refresh checksums before GitHub mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from zipfile import BadZipFile, ZipFile

try:
    from .sign_windows import SigningError, sha256, verify_release
except ImportError:
    from sign_windows import SigningError, sha256, verify_release

REQUIRED_CHECKS = {"install", "installed_files", "signed_uninstaller", "startup", "ui_resources", "sample_workspace", "mcp_process", "uninstall"}


def verify_acceptance(receipt, installer):
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("status") != "passed" or data.get("installer_sha256") != sha256(installer) or not isinstance(data.get("checks"), list) or not REQUIRED_CHECKS.issubset(data["checks"]):
        raise SigningError("缺少此安装包完整通过的安装/启动/MCP/卸载验收记录。")


def verify_portable(archive, bundle):
    expected = {p.relative_to(bundle.parent).as_posix(): p for p in bundle.rglob("*") if p.is_file()}
    with ZipFile(archive) as zipped:
        members = [i for i in zipped.infolist() if not i.is_dir()]
        if len(members) != len(expected) or {i.filename for i in members} != set(expected):
            raise SigningError("便携包文件清单与已签名目录不一致。")
        for member in members:
            with zipped.open(member) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != sha256(expected[member.filename]):
                    raise SigningError("便携包文件与已签名目录不一致。")


def check(bundle, output, version):
    installer = output / f"CodeDesk-Setup-{version}.exe"
    manifest = output / "signing-manifest.json"
    archive = output / f"CodeDesk-Portable-{version}-win64.zip"
    receipt = output / "installation-acceptance.json"
    data = verify_release(bundle, installer, manifest)
    if data.get("version") != version:
        raise SigningError("构建版本不一致。")
    verify_acceptance(receipt, installer)
    verify_portable(archive, bundle)
    artifacts = [installer, archive, manifest, receipt]
    # The acceptance record is created after the build; refresh checksums only
    # after all signed-release and installation checks have succeeded.
    (output / "SHA256SUMS.txt").write_text("\n".join(f"{sha256(p)}  {p.name}" for p in artifacts) + "\n", encoding="utf-8")
    return artifacts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    try:
        check(args.directory, args.output, args.version)
        print("发布前检查通过。")
    except (SigningError, OSError, ValueError, BadZipFile) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
