"""Compatibility of the original desktop workspace and the integrated WeCom panel."""
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from agent.settings import Settings
from server.app import create_app


class WorkbenchContinuityTests(unittest.TestCase):
    def test_existing_settings_and_untagged_desktop_history_survive_new_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            stored = {"workspace": str(project), "enable_reviewer": False,
                      "online_enabled": True, "mcp_servers": {"my-tool": {"enabled": False}}}
            settings_file = root / "settings.json"
            settings_file.write_text(json.dumps(stored), encoding="utf-8")
            original_settings = settings_file.read_bytes()
            sessions = root / "sessions"
            sessions.mkdir()
            session_id = "a" * 32
            record = {"workspace": str(project), "session_id": session_id, "mode": "plan",
                      "events": [{"type": "user", "text": "接着原来的项目做"}]}
            history_file = sessions / (session_id + ".json")
            history_file.write_text(json.dumps(record), encoding="utf-8")
            original_history = history_file.read_bytes()
            settings = Settings(root)
            settings.memory_keys[settings._account()] = ""
            app = create_app(settings, token="fixture")
            with TestClient(app, headers={"Authorization": "Bearer fixture"}) as client:
                self.assertEqual(client.get("/remote").status_code, 200)
                self.assertEqual(client.get("/api/remote").status_code, 200)
                saved = client.get("/api/settings").json()
                for key, value in stored.items():
                    self.assertEqual(saved[key], value)
                history = client.get("/api/history").json()
                self.assertEqual(history["session_id"], session_id)
                self.assertEqual(history["events"], record["events"])
                self.assertEqual(history["mode"], "plan")
            self.assertEqual(settings_file.read_bytes(), original_settings)
            self.assertEqual(history_file.read_bytes(), original_history)

    def test_desktop_allows_only_its_own_remote_panel_to_be_embedded(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory))
            settings.memory_keys[settings._account()] = ""
            with TestClient(create_app(settings)) as client:
                home = client.get("/")
                self.assertIn('id="openRemote"', home.text)
                self.assertIn('id="remoteFrame"', home.text)
                self.assertIn("frame-ancestors 'none'", home.headers["Content-Security-Policy"])
                panel = client.get("/remote")
                self.assertIn("frame-ancestors 'self'", panel.headers["Content-Security-Policy"])
                self.assertEqual(client.get("/api/remote").status_code, 401)

