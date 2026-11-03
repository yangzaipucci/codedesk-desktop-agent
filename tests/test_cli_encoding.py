import contextlib
import io
import json
import unittest
from unittest.mock import AsyncMock, patch

import app
from agent.cli import main


class CLIEncodingTests(unittest.TestCase):
    def test_chinese_reports_round_trip_on_legacy_windows_output(self):
        report = {'passed': True, 'prompt': '请检索文献', 'path': '项目/结果.json'}
        for entry in (lambda: main(['inspect']), app.inspect):
            with self.subTest(entry=entry):
                raw = io.BytesIO()
                stream = io.TextIOWrapper(raw, encoding='cp1252', errors='strict')
                with patch('agent.inspection.inspect_patches', AsyncMock(return_value=report)):
                    with contextlib.redirect_stdout(stream):
                        self.assertEqual(entry(), report)
                stream.flush()
                self.assertEqual(json.loads(raw.getvalue().decode('cp1252')), report)
                stream.detach()
