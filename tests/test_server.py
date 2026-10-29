import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.runtime import Runtime
from agent.settings import Settings
from agent.tools import Tools
from server.app import create_app


class Echo:
    async def complete(self, messages, tools, emit):
        await emit({"type": "assistant_delta", "text": "测试完成"})
        return {"role": "assistant", "content": "测试完成"}, {"total_tokens": 5}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(root / "state")
        self.settings.value["workspace"] = str(root)
        self.runtime = Runtime(self.settings, Echo())
        self.app = create_app(self.settings, "local-test-token", self.runtime)
        self.client = TestClient(self.app)
        self.headers = {"Authorization": "Bearer local-test-token"}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_api_requires_boot_token(self):
        self.assertEqual(self.client.get("/api/settings").status_code, 401)
        self.assertEqual(self.client.get("/api/settings", headers=self.headers).status_code, 200)

    def test_key_not_returned_or_written_to_json(self):
        with patch.object(Settings, "_vault", side_effect=ValueError("test vault disabled")):
            response = self.client.post("/api/settings", headers=self.headers, json={"api_key": "not-a-real-model-key"})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("not-a-real-model-key", response.text)
            self.assertNotIn("not-a-real-model-key", self.settings.path.read_text())

    def test_sse_is_independent_of_ui(self):
        response = self.client.post("/api/run", headers=self.headers, json={"prompt": "测试"})
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1]["status"], "completed")
        self.assertTrue(any(e["type"] == "assistant_delta" for e in events))

    def test_local_ui_and_static_files(self):
        response = self.client.get("/")
        self.assertIn("local-test-token", response.text)
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertEqual(self.client.get("/app.js").status_code, 200)
        self.assertEqual(self.client.get("/style.css").status_code, 200)

    def test_invalid_edit_path_does_not_escape_workspace(self):
        response = self.client.get("/api/file?path=../outside.txt", headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_undo_api_restores_file_and_informs_model(self):
        root = self.settings.directory.parent
        with patch.dict(os.environ, {"CODEDESK_DATA_DIR": str(self.settings.directory)}):
            tools = Tools(root)
            tools.write("undo.txt", "before")
            change = tools.edit("undo.txt", "before", "after")
            self.runtime.reset_context(str(root))
            response = self.client.post("/api/undo", headers=self.headers, json={"change_id": change["change_id"]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual((root / "undo.txt").read_text(), "before")
            self.assertIn("撤销", self.runtime.messages[-1]["content"])

    def test_undo_api_rejects_concurrent_changes(self):
        root = self.settings.directory.parent
        with patch.dict(os.environ, {"CODEDESK_DATA_DIR": str(self.settings.directory)}):
            tools = Tools(root)
            change = tools.write("undo.txt", "after")
            (root / "undo.txt").write_text("manual change")
            response = self.client.post("/api/undo", headers=self.headers, json={"change_id": change["change_id"]})
            self.assertGreaterEqual(response.status_code, 400)
            self.assertEqual((root / "undo.txt").read_text(), "manual change")
