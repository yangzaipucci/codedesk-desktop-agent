import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from agent.mcp_client import demo_config
from scripts import build_windows as build
from scripts import release_check as release
from scripts import sign_windows as signing
from scripts import verify_installation as acceptance

FINGERPRINT = "A" * 40
VALID = {"status": "Valid", "thumbprint": FINGERPRINT, "timestamped": True}


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle = self.root / "CodeDesk"
        self.bundle.mkdir()
        self.binary = self.bundle / "CodeDesk.exe"
        self.binary.write_bytes(b"application-fixture")
        self.installer = self.root / "CodeDesk-Setup-1.0.1.exe"
        self.installer.write_bytes(b"installer-fixture")
        self.report = self.root / "signing-manifest.json"
        self.data = {"mode": "signed", "version": "1.0.1", "signed_uninstaller": True,
                     "installer": self.installer.name, "installer_sha256": signing.sha256(self.installer),
                     "certificate_thumbprint": FINGERPRINT,
                     "binaries": [{"path": "CodeDesk.exe", "sha256": signing.sha256(self.binary)}],
                     "files": [{"path": "CodeDesk.exe", "sha256": signing.sha256(self.binary)}]}
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.report.write_text(json.dumps(self.data), encoding="utf-8")

    def verify(self):
        with patch.object(signing, "find_signtool", return_value=Path("signtool.exe")), patch.object(signing, "run_tool"), patch.object(signing, "signature", return_value=VALID):
            return signing.verify_release(self.bundle, self.installer, self.report)

    def signer(self):
        signer = object.__new__(signing.Signer)
        signer.thumbprint, signer.tool = FINGERPRINT, Path("signtool.exe")
        return signer

    def test_no_certificate_stops_before_process_or_build(self):
        with patch.dict(os.environ, {"CODEDESK_SIGN_CERT_SHA1": ""}), patch.object(signing, "powershell") as process, patch.object(build, "run") as build_process:
            with self.assertRaises(signing.SigningError):
                build.main([])
            process.assert_not_called()
            build_process.assert_not_called()

    def test_certificate_fingerprint_rejects_shell_text(self):
        with patch.object(signing, "powershell") as process:
            with self.assertRaises(signing.SigningError):
                signing.certificate("bad; command")
            process.assert_not_called()

    def test_certificate_requires_private_key_eku_dates_and_chain(self):
        good = dict(private_key=True, code_signing=True, valid_now=True, trusted=True, self_signed=False)
        for field in ("private_key", "code_signing", "valid_now", "trusted"):
            with self.subTest(field=field), patch.object(signing, "powershell", return_value={**good, field: False}):
                with self.assertRaises(signing.SigningError):
                    signing.certificate(FINGERPRINT)
        with patch.object(signing, "powershell", return_value={**good, "self_signed": True}):
            with self.assertRaises(signing.SigningError):
                signing.certificate(FINGERPRINT)

    def test_warning_exit_code_is_release_failure(self):
        result = subprocess.CompletedProcess([], 2, "timestamp warning", "")
        with patch.object(signing.subprocess, "run", return_value=result):
            with self.assertRaises(signing.SigningError):
                signing.run_tool(["signtool.exe"])

    def test_own_signature_requires_timestamp_and_expected_publisher(self):
        for info in ({**VALID, "timestamped": False}, {**VALID, "thumbprint": "B" * 40}):
            with self.subTest(info=info), patch.object(signing, "run_tool"), patch.object(signing, "signature", return_value=info):
                with self.assertRaises(signing.SigningError):
                    self.signer().verify(self.binary, own=True)

    def test_bundle_signs_unsigned_and_preserves_vendor_signature(self):
        vendor = self.bundle / "vendor.dll"
        vendor.write_bytes(b"vendor-fixture")
        signer = self.signer()
        signer.sign, signer.verify = Mock(return_value=VALID), Mock(return_value=VALID)
        with patch.object(signing, "signature", side_effect=lambda p: {"status": "NotSigned"} if p == self.binary else VALID):
            records = signer.bundle(self.bundle)
        signer.sign.assert_called_once_with(self.binary)
        signer.verify.assert_called_once_with(vendor)
        self.assertEqual({r["path"] for r in records}, {"CodeDesk.exe", "vendor.dll"})

    def test_bundle_rejects_tampered_vendor_binary(self):
        with patch.object(signing, "signature", return_value={"status": "HashMismatch"}):
            with self.assertRaises(signing.SigningError):
                self.signer().bundle(self.bundle)

    def test_complete_manifest_verifies(self):
        self.assertEqual(self.verify()["version"], "1.0.1")

    def test_unsigned_or_empty_manifest_cannot_publish(self):
        for update in ({"mode": "unsigned"}, {"signed_uninstaller": False}, {"binaries": []}, {"certificate_thumbprint": ""}):
            original = dict(self.data)
            self.data.update(update)
            self.save()
            with self.subTest(update=update), self.assertRaises(signing.SigningError):
                self.verify()
            self.data = original

    def test_changed_installer_cannot_publish(self):
        self.installer.write_bytes(b"modified")
        with self.assertRaises(signing.SigningError):
            self.verify()

    def test_modified_non_binary_resource_cannot_publish(self):
        resource = self.bundle / "index.html"
        resource.write_text("original")
        self.data["files"].append({"path": "index.html", "sha256": signing.sha256(resource)})
        self.save()
        self.verify()
        resource.write_text("tampered")
        with self.assertRaises(signing.SigningError):
            self.verify()

    def test_changed_or_extra_binary_cannot_publish(self):
        self.binary.write_bytes(b"modified")
        with self.assertRaises(signing.SigningError):
            self.verify()
        self.data["binaries"][0]["sha256"] = signing.sha256(self.binary)
        self.data["files"][0]["sha256"] = signing.sha256(self.binary)
        self.save()
        (self.bundle / "unlisted.pyd").write_bytes(b"unlisted")
        with self.assertRaises(signing.SigningError):
            self.verify()

    def test_manifest_path_escape_and_duplicates_rejected(self):
        self.data["binaries"] = [{"path": "../outside.dll", "sha256": "x"}]
        self.save()
        with self.assertRaises(signing.SigningError):
            self.verify()
        self.data["binaries"] = [{"path": "CodeDesk.exe", "sha256": signing.sha256(self.binary)}] * 2
        self.save()
        with self.assertRaises(signing.SigningError):
            self.verify()

    def test_verification_rechecks_signatures_and_timestamp(self):
        for info in ({**VALID, "status": "HashMismatch"}, {**VALID, "timestamped": False}):
            with patch.object(signing, "find_signtool", return_value=Path("signtool.exe")), patch.object(signing, "run_tool"), patch.object(signing, "signature", return_value=info):
                with self.assertRaises(signing.SigningError):
                    signing.verify_release(self.bundle, self.installer, self.report)

    def test_inno_sign_callback_handles_spaces_and_dollars(self):
        command = signing.installer_sign_command(Path("C:/Python path/python.exe"), Path("E:/course $1/sign.py"))
        self.assertIn("$qC:", command)
        self.assertIn("$$1", command)
        self.assertTrue(command.endswith(" sign $f"))
        signed = build.compile_arguments("ISCC.exe", self.bundle, self.root, self.root, "1.0.1", True)
        self.assertIn("/DSignedBuild=1", signed)
        self.assertTrue(any(arg.startswith("/Scodedesk=") for arg in signed))
        unsigned = build.compile_arguments("ISCC.exe", self.bundle, self.root, self.root, "1.0.1", False)
        self.assertIn("/DUnsignedDevelopment=1", unsigned)
        self.assertFalse(any(arg.startswith("/Scodedesk=") for arg in unsigned))

    def test_acceptance_requires_all_checks_and_matching_installer(self):
        receipt = self.root / "acceptance.json"
        data = {"status": "passed", "installer_sha256": signing.sha256(self.installer), "checks": sorted(release.REQUIRED_CHECKS)}
        receipt.write_text(json.dumps(data))
        release.verify_acceptance(receipt, self.installer)
        for update in ({"status": "failed"}, {"installer_sha256": "other"}, {"checks": ["install"]}):
            receipt.write_text(json.dumps({**data, **update}))
            with self.assertRaises(signing.SigningError):
                release.verify_acceptance(receipt, self.installer)

    def test_portable_must_match_all_resources(self):
        (self.bundle / "index.html").write_text("original")
        archive = Path(shutil.make_archive(str(self.root / "portable"), "zip", self.root, "CodeDesk"))
        release.verify_portable(archive, self.bundle)
        (self.bundle / "index.html").write_text("changed")
        with self.assertRaises(signing.SigningError):
            release.verify_portable(archive, self.bundle)

    def test_portable_rejects_duplicate_and_extra_zip_members(self):
        archive = self.root / "portable.zip"
        with ZipFile(archive, "w") as zipped:
            zipped.writestr("CodeDesk/CodeDesk.exe", b"application-fixture")
            zipped.writestr("../extra.exe", b"extra")
        with self.assertRaises(signing.SigningError):
            release.verify_portable(archive, self.bundle)

    def test_unsigned_acceptance_never_launches_installer(self):
        self.data["mode"] = "unsigned"
        self.save()
        with patch.object(acceptance.subprocess, "run") as run:
            with self.assertRaises(signing.SigningError):
                acceptance.accept(self.bundle, self.installer, self.report)
            run.assert_not_called()

    def test_installed_files_and_signed_uninstaller_are_verified(self):
        installed = self.root / "installed"
        shutil.copytree(self.bundle, installed)
        (installed / "unins000.exe").write_bytes(b"uninstaller-fixture")
        with patch.object(acceptance, "find_signtool", return_value=Path("signtool.exe")), patch.object(acceptance, "run_tool"), patch.object(acceptance, "signature", return_value=VALID):
            self.assertEqual(acceptance.verify_installed(installed, self.bundle, FINGERPRINT).name, "unins000.exe")
            (installed / "CodeDesk.exe").write_bytes(b"modified")
            with self.assertRaises(signing.SigningError):
                acceptance.verify_installed(installed, self.bundle, FINGERPRINT)

    def test_frozen_mcp_uses_signable_directory_layout_and_legacy_fallback(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", str(self.root), create=True):
            self.assertEqual(Path(demo_config()["workspace-demo"]["command"]), self.root / "WorkspaceMCP.exe")
            helper = self.root / "mcp/WorkspaceMCP/WorkspaceMCP.exe"
            helper.parent.mkdir(parents=True)
            helper.write_bytes(b"helper-fixture")
            self.assertEqual(Path(demo_config()["workspace-demo"]["command"]), helper)
