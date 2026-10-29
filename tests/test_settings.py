import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.settings import Settings, validate_endpoint


class Vault:
    def __init__(self):
        self.store = {}
    def get_password(self, service, account):
        return self.store.get((service, account))
    def set_password(self, service, account, key):
        self.store[service, account] = key
    def delete_password(self, service, account):
        self.store.pop((service, account), None)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = Vault()
        self.mock = patch.object(Settings, "_vault", return_value=self.vault)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.temp.cleanup()

    def test_session_key_never_persisted(self):
        settings = Settings(self.root)
        settings.save({"api_key": "unit-test-only-secret"})
        self.assertEqual(settings.key(), "unit-test-only-secret")
        self.assertNotIn("unit-test-only-secret", settings.path.read_text())
        self.assertNotIn("unit-test-only-secret", json.dumps(settings.public()))
        self.assertEqual(Settings(self.root).key(), "")

    def test_remembered_keys_are_scoped_by_endpoint(self):
        settings = Settings(self.root)
        settings.save({"api_key": "first-test-key", "remember_key": True})
        self.assertEqual(Settings(self.root).key(), "first-test-key")
        settings.save({"base_url": "https://example.com/v1", "api_key": "second-test-key", "remember_key": True})
        self.assertEqual(settings.key(), "second-test-key")
        settings.save({"base_url": "https://api.deepseek.com"})
        self.assertEqual(settings.key(), "first-test-key")
        settings.save({"forget_key": True})
        self.assertEqual(settings.key(), "")

    def test_redaction(self):
        settings = Settings(self.root)
        settings.save({"api_key": "test-secret"})
        self.assertNotIn("test-secret", settings.redact("prefix test-secret suffix"))

    def test_plain_http_remote_is_rejected(self):
        for endpoint in ("http://example.com/v1", "https://user:pass@example.com", "https://example.com?key=secret"):
            with self.assertRaises(ValueError):
                validate_endpoint(endpoint)
        self.assertEqual(validate_endpoint("http://127.0.0.1:1234/v1"), "http://127.0.0.1:1234/v1")

    def test_failed_credential_removal_is_reported(self):
        settings = Settings(self.root)
        settings.save({"api_key": "remembered-test-key", "remember_key": True})
        with patch.object(self.vault, "delete_password", side_effect=OSError("denied")):
            with self.assertRaisesRegex(ValueError, "未能删除"):
                settings.save({"forget_key": True})
        self.assertEqual(settings.key(), "remembered-test-key")
