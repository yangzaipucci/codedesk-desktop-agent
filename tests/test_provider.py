import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from agent.provider import Provider, ProviderError
from agent.settings import Settings


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(Path(self.temp.name))
        self.settings.memory_keys[self.settings._account()] = "unit-test-credential"
        self.events = []

    def tearDown(self):
        self.temp.cleanup()

    async def emit(self, event):
        self.events.append(event)

    async def test_streaming_tool_argument_fragments(self):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            chunks = [
                {"choices": [{"delta": {"content": "先读取文件。"}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call1", "function": {"name": "read", "arguments": '{"path":'}}]}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"demo.py"}'}}]}}]},
                {"choices": [], "usage": {"total_tokens": 42}},
            ]
            text = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
            return httpx.Response(200, text=text)
        client_type = httpx.AsyncClient
        with patch("agent.provider.httpx.AsyncClient", side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw)):
            message, usage = await Provider(self.settings).complete([{"role": "user", "content": "test"}], [], self.emit)
        call = message["tool_calls"][0]
        self.assertEqual(call["id"], "call1")
        self.assertEqual(json.loads(call["function"]["arguments"]), {"path": "demo.py"})
        self.assertEqual(usage["total_tokens"], 42)
        self.assertNotIn("unit-test-credential", json.dumps(requests))

    async def test_authentication_error_does_not_echo_server_body(self):
        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(401, text="unit-test-credential"))
        with patch("agent.provider.httpx.AsyncClient", side_effect=lambda **kw: client_type(transport=transport, **kw)):
            with self.assertRaises(ProviderError) as raised:
                await Provider(self.settings).complete([], [], self.emit)
        self.assertNotIn("unit-test-credential", str(raised.exception))

    async def test_provider_specific_parameters(self):
        provider = Provider(self.settings)
        self.assertEqual(provider.payload([], [])["thinking"], {"type": "disabled"})
        self.settings.value["provider"] = "openai"
        payload = provider.payload([], [])
        self.assertIn("max_completion_tokens", payload)
        self.assertNotIn("thinking", payload)
        self.settings.value["provider"] = "qwen"
        self.assertFalse(provider.payload([], [])["enable_thinking"])

    async def invoke_stream(self, chunks, done=False):
        body = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
        if done:
            body += "data: [DONE]\n\n"
        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
        with patch("agent.provider.httpx.AsyncClient", side_effect=lambda **kw: client_type(transport=transport, **kw)):
            return await Provider(self.settings).complete([], [], self.emit)

    async def test_partial_stream_is_not_reported_as_success(self):
        with self.assertRaisesRegex(ProviderError, "提前结束"):
            await self.invoke_stream([{"choices": [{"delta": {"content": "unfinished"}}]}])

    async def test_finish_reason_without_done_is_accepted(self):
        message, _ = await self.invoke_stream([
            {"choices": [{"delta": {"content": "finished"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ])
        self.assertEqual(message["content"], "finished")

    async def test_length_limited_tool_call_is_not_executed(self):
        with self.assertRaisesRegex(ProviderError, "长度限制"):
            await self.invoke_stream([{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "unfinished", "function": {"name": "edit", "arguments": '{"path":'}}]}, "finish_reason": "length"}]}], done=True)

    async def test_duplicate_tool_ids_are_rejected(self):
        calls = [{"index": i, "id": "duplicate", "function": {"name": "read", "arguments": "{}"}} for i in range(2)]
        with self.assertRaisesRegex(ProviderError, "重复标识"):
            await self.invoke_stream([{"choices": [{"delta": {"tool_calls": calls}, "finish_reason": "tool_calls"}]}], done=True)
