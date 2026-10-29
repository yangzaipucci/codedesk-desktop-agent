import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.mcp_client import MCP, demo_config
from agent.runtime import Runtime
from agent.settings import Settings


class SequenceProvider:
    def __init__(self, sequence):
        self.sequence = iter(sequence)
    async def complete(self, messages, tools, emit):
        message = next(self.sequence)
        if message.get("content"):
            await emit({"type": "assistant_delta", "text": message["content"]})
        return {"role": "assistant", **message}, {"total_tokens": 20}


def call(identity, name, arguments):
    return {"content": None, "tool_calls": [{"id": identity, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.settings = Settings(self.root / "state")
        self.settings.value["workspace"] = str(self.work)
        self.events = []

    def tearDown(self):
        self.temp.cleanup()

    async def sink(self, event):
        self.events.append(event)

    async def test_failure_recovery_and_trace(self):
        (self.work / "demo.py").write_text("a = 1\nb = 1\n")
        provider = SequenceProvider([
            call("1", "read", {"path": "demo.py"}),
            call("2", "edit", {"path": "demo.py", "old": "1", "new": "2"}),
            call("3", "edit", {"path": "demo.py", "old": "b = 1", "new": "b = 2"}),
            {"content": "已修复。"},
        ])
        runtime = Runtime(self.settings, provider)
        await runtime.run("test", self.sink)
        results = [e["result"] for e in self.events if e["type"] == "tool_result"]
        self.assertEqual([r["ok"] for r in results], [True, False, True])
        self.assertEqual((self.work / "demo.py").read_text(), "a = 1\nb = 2\n")
        self.assertEqual(self.events[-1]["status"], "completed")
        self.assertTrue((self.settings.directory / "sessions" / f"{runtime.session_id}.json").exists())

    async def test_repeated_calls_stop(self):
        provider = SequenceProvider([call(str(i), "read", {"path": "missing"}) for i in range(10)])
        await Runtime(self.settings, provider).run("test", self.sink)
        self.assertEqual(len([e for e in self.events if e["type"] == "tool_start"]), 4)
        self.assertEqual(self.events[-1]["status"], "error")

    async def test_interrupt_model_request(self):
        class WaitingProvider:
            async def complete(self, *args):
                await asyncio.sleep(30)
        runtime = Runtime(self.settings, WaitingProvider())
        task = asyncio.create_task(runtime.run("test", self.sink))
        await asyncio.sleep(0.1)
        task.cancel()
        await asyncio.wait_for(task, 2)
        self.assertEqual(self.events[-1]["status"], "cancelled")

    async def test_real_external_mcp(self):
        client = MCP(demo_config(), self.work)
        definitions = await client.discover(self.sink)
        self.assertEqual(len(definitions), 1, self.events)
        result = await client.call(definitions[0]["function"]["name"], {})
        self.assertTrue(result["ok"], result)
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["workspace"], str(self.work))
        self.assertEqual(data["process"], "external MCP server")

    async def test_new_session_keeps_system_prompt_in_same_workspace(self):
        provider = SequenceProvider([{"content": "first"}, {"content": "second"}])
        runtime = Runtime(self.settings, provider)
        await runtime.run("first request", self.sink)
        runtime.reset()
        await runtime.run("second request", self.sink)
        self.assertEqual(runtime.messages[0]["role"], "system")
        self.assertIn(str(self.work), runtime.messages[0]["content"])
        self.assertNotIn("first request", json.dumps(runtime.messages))

    def test_compaction_drops_whole_tool_turns(self):
        runtime = Runtime(self.settings)
        runtime.reset_context(str(self.work))
        runtime.messages += [
            {"role": "user", "content": "old " * 1000},
            {"role": "assistant", **call("old-tool", "read", {"path": "a"})},
            {"role": "tool", "tool_call_id": "old-tool", "content": "old observation"},
            {"role": "user", "content": "new request"},
            {"role": "assistant", **call("new-tool", "read", {"path": "b"})},
            {"role": "tool", "tool_call_id": "new-tool", "content": "new observation"},
        ]
        self.assertTrue(runtime.compact_context(max_chars=2500))
        self.assertEqual(runtime.messages[0]["role"], "system")
        self.assertEqual(runtime.messages[1]["content"], "new request")
        self.assertEqual(runtime.messages[-1]["tool_call_id"], "new-tool")
        self.assertNotIn("old-tool", json.dumps(runtime.messages))

    async def test_budget_stops_before_request(self):
        class MustNotCall:
            async def complete(self, *args):
                raise AssertionError("budget must prevent this request")
        self.settings.value["budget_tokens"] = 1000
        await Runtime(self.settings, MustNotCall()).run("test", self.sink)
        self.assertEqual(self.events[-1]["status"], "error")
        self.assertTrue(any("预算" in e.get("text", "") for e in self.events))

    async def test_failed_mcp_pagination_leaves_no_routes(self):
        class BrokenListing:
            async def list_tools(self, cursor=None):
                if cursor:
                    raise ValueError("broken second page")
                return SimpleNamespace(tools=[SimpleNamespace(name="partly-listed", description="test", inputSchema={"type": "object"})], nextCursor="second")

        @asynccontextmanager
        async def broken_session(name):
            yield BrokenListing()

        client = MCP({"broken": {"enabled": True}}, self.work)
        client.session = broken_session
        definitions = await client.discover(self.sink)
        self.assertEqual(definitions, [])
        self.assertEqual(client.routes, {})
        self.assertFalse(self.events[-1]["ok"])
