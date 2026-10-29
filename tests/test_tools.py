import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

from agent.tools import Tools, ToolError, MAX_OUTPUT


class ToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.tools = Tools(self.root, state_directory=self.root / "state")

    def tearDown(self):
        self.temp.cleanup()

    def test_pagination(self):
        self.tools.write("large.txt", "\n".join(str(i) for i in range(1000)))
        result = self.tools.read("large.txt", offset=101, limit=3)
        self.assertEqual(result["total_lines"], 1000)
        self.assertEqual(result["remaining_lines"], 897)
        self.assertEqual(result["next_offset"], 104)
        self.assertIn("101  100", result["text"])

    def test_atomic_write_and_parent(self):
        result = self.tools.write("a/b/file.py", "x = 1\n")
        self.assertEqual(result["old_lines"], 0)
        self.assertEqual(result["new_lines"], 1)
        result = self.tools.write("a/b/file.py", "x = 2\ny = 3\n")
        self.assertEqual(result["old_lines"], 1)
        self.assertEqual(result["new_lines"], 2)
        self.assertFalse(list((self.root / "a/b").glob(".codedesk-*")))

    def test_edit_nonunique_and_missing_leave_file_unchanged(self):
        self.tools.write("f.py", "x = 1\ny = 1\n")
        for old in ("1", "not-present", ""):
            with self.assertRaises(ToolError):
                self.tools.edit("f.py", old, "2")
            self.assertEqual((self.root / "f.py").read_text(), "x = 1\ny = 1\n")
        result = self.tools.edit("f.py", "y = 1", "y = 2")
        self.assertIn("-y = 1", result["diff"])
        self.assertIn("+y = 2", result["diff"])

    def test_edit_preserves_crlf(self):
        (self.root / "f.py").write_bytes(b"x = 1\r\ny = 2\r\n")
        self.tools.edit("f.py", "x = 1", "x = 3")
        self.assertEqual((self.root / "f.py").read_bytes(), b"x = 3\r\ny = 2\r\n")

    def test_image_block_is_not_text(self):
        (self.root / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        result = self.tools.read("a.png")
        self.assertEqual(result["content"][0]["type"], "image")
        self.assertNotIn("text", result)

    def test_large_file_streaming_pagination(self):
        target = self.root / "huge.txt"
        with target.open("w", encoding="utf-8") as handle:
            for _ in range(10000):
                handle.write("x" * 1000 + "\n")
        self.assertGreater(target.stat().st_size, 8 * 1024 * 1024)
        result = self.tools.read("huge.txt", offset=9998, limit=2)
        self.assertEqual(result["total_lines"], 10000)
        self.assertEqual(result["remaining_lines"], 1)
        self.assertEqual(result["next_offset"], 10000)

    def test_single_huge_line_is_bounded(self):
        (self.root / "line.txt").write_text("x" * 200000 + "\nlast\n", encoding="utf-8")
        result = self.tools.read("line.txt")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["total_lines"], 2)
        self.assertLessEqual(len(result["text"]), MAX_OUTPUT)
        self.assertEqual(result["next_offset"], 2)

    def test_undo_restores_exact_bytes_across_instances(self):
        target = self.root / "file.py"
        original = b"\xef\xbb\xbfx = 1\r\n"
        target.write_bytes(original)
        result = self.tools.edit("file.py", "x = 1", "x = 2")
        other = Tools(self.root, state_directory=self.root / "state")
        response = other.undo(result["change_id"])
        self.assertTrue(response["restored"])
        self.assertEqual(target.read_bytes(), original)
        with self.assertRaises(ValueError):
            other.undo(result["change_id"])

    def test_undo_new_file_and_conflict_detection(self):
        result = self.tools.write("new.txt", "first")
        (self.root / "new.txt").write_text("user modification", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.tools.undo(result["change_id"])
        self.assertEqual((self.root / "new.txt").read_text(), "user modification")
        (self.root / "new.txt").write_text("first", encoding="utf-8")
        self.tools.undo(result["change_id"])
        self.assertFalse((self.root / "new.txt").exists())

    def test_undo_reverse_order_and_path_boundary(self):
        first = self.tools.write("new.txt", "first")
        second = self.tools.write("new.txt", "second")
        with self.assertRaises(ValueError):
            self.tools.undo(first["change_id"])
        self.tools.undo(second["change_id"])
        self.tools.undo(first["change_id"])
        self.assertFalse((self.root / "new.txt").exists())
        with self.assertRaises(ValueError):
            self.tools.undo("../settings.json")

    def test_workspace_boundary(self):
        with self.assertRaises(ToolError):
            self.tools.write("../outside.txt", "no")
        with self.assertRaises(ToolError):
            self.tools.write(".git/config", "no")

    async def test_nonzero_exit_preserves_stderr(self):
        command = "[Console]::Error.WriteLine('failed'); exit 7" if os.name == "nt" else "echo failed >&2; exit 7"
        result = await self.tools.execute("bash", {"command": command})
        self.assertEqual(result["exit_code"], 7)
        self.assertIn("failed", result["stderr"])
        self.assertFalse(result["ok"])

    async def test_timeout_is_finite(self):
        command = "Start-Sleep -Seconds 20" if os.name == "nt" else "sleep 20"
        result = await asyncio.wait_for(self.tools.execute("bash", {"command": command, "timeout": 0.3}), 8)
        self.assertTrue(result["timed_out"])

    async def test_output_is_bounded_and_drained(self):
        command = "[Console]::Write('x' * 100000)" if os.name == "nt" else "python -c \"print('x'*100000)\""
        result = await self.tools.execute("bash", {"command": command})
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["stdout"]), MAX_OUTPUT)

    async def test_cancel_kills_command(self):
        command = "Start-Sleep -Seconds 3; Set-Content -Path 'should-not-exist.txt' -Value 'bad'" if os.name == "nt" else "sleep 3; echo bad > should-not-exist.txt"
        task = asyncio.create_task(self.tools.bash(command))
        await asyncio.sleep(0.5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        await asyncio.sleep(3)
        self.assertFalse((self.root / "should-not-exist.txt").exists())


if __name__ == "__main__":
    unittest.main()
