"""OpenAI-compatible streaming adapter. Secrets never enter the UI response."""
from __future__ import annotations

import asyncio
import json

import httpx


class ProviderError(ValueError):
    pass


class Provider:
    def __init__(self, settings):
        self.settings = settings

    def payload(self, messages, tools, stream=True):
        config = self.settings.value
        result = {"model": config["model"], "messages": messages, "stream": stream}
        if tools:
            result["tools"] = tools
            result["tool_choice"] = "auto"
        result["max_completion_tokens" if config["provider"] == "openai" else "max_tokens"] = 4096
        if config["provider"] == "deepseek":
            result["thinking"] = {"type": "disabled"}
        elif config["provider"] == "qwen":
            result["enable_thinking"] = False
        return result

    async def complete(self, messages, tools, emit):
        if not self.settings.value["model"].strip():
            raise ProviderError("请先填写模型名称，或点击模型框旁的刷新按钮读取模型列表。")
        key = self.settings.key()
        if not key:
            raise ProviderError("请先在设置中填写 API Key。")
        url = self.settings.value["base_url"].rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        payload = self.payload(messages, tools)
        for attempt in range(3):
            content, reasoning, calls, usage = [], [], {}, {}
            received, ended, finish_reason = False, False, None
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15), follow_redirects=False) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                            await emit({"type": "status", "text": f"接口暂时繁忙，正在重试（{attempt + 1}/2）…"})
                            await asyncio.sleep(1 + attempt * 2)
                            continue
                        if response.status_code != 200:
                            messages_by_status = {401: "API Key 无效或已过期。", 402: "账户余额不足。", 403: "此 Key 没有调用权限。", 404: "模型或接口地址不存在，请检查设置。", 429: "请求频率过高，请稍后重试。", 400: "接口拒绝请求，请确认模型支持 Chat Completions 和工具调用。"}
                            raise ProviderError(messages_by_status.get(response.status_code, f"模型接口返回 HTTP {response.status_code}。"))
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                ended = True
                                break
                            if not data:
                                continue
                            chunk = json.loads(data)
                            if chunk.get("error"):
                                raise ProviderError("模型在生成过程中返回错误，请重试或检查模型设置。")
                            usage = chunk.get("usage") or usage
                            choices = chunk.get("choices", [])
                            if not choices:
                                continue
                            finish_reason = choices[0].get("finish_reason") or finish_reason
                            delta = choices[0].get("delta", {})
                            if text := delta.get("content"):
                                received = True
                                content.append(text)
                                await emit({"type": "assistant_delta", "text": text})
                            if thought := delta.get("reasoning_content"):
                                received = True
                                reasoning.append(thought)
                            for call in delta.get("tool_calls", []):
                                received = True
                                index = call.get("index", 0)
                                target = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                target["id"] += call.get("id") or ""
                                function = call.get("function", {})
                                target["function"]["name"] += function.get("name") or ""
                                target["function"]["arguments"] += function.get("arguments") or ""
                if not ended and finish_reason is None:
                    raise ProviderError("模型事件流提前结束，回复尚未完成。本次未执行未完成的工具调用，请重试。")
                if finish_reason in {"length", "content_filter"}:
                    raise ProviderError("模型输出达到长度限制或内容过滤限制，回复未完成。本次未执行工具调用，请缩小任务后重试。")
                if calls:
                    identities = set()
                    for call in calls.values():
                        if not call["id"] or not call["function"]["name"] or call["id"] in identities:
                            raise ProviderError("模型返回的工具调用缺少标识或存在重复标识，未执行。")
                        identities.add(call["id"])
                message = {"role": "assistant", "content": "".join(content) or None}
                if calls:
                    message["tool_calls"] = [calls[i] for i in sorted(calls)]
                if reasoning:
                    message["reasoning_content"] = "".join(reasoning)
                if not calls and not message["content"]:
                    raise ProviderError("接口未返回可用内容，请确认模型兼容此接口。")
                return message, usage
            except httpx.TransportError as error:
                if not received and attempt < 2:
                    await emit({"type": "status", "text": "网络连接中断，正在重试…"})
                    await asyncio.sleep(1 + attempt)
                    continue
                raise ProviderError("连接模型超时或网络不可用，请检查服务地址和网络。") from error
            except (ValueError, KeyError) as error:
                if isinstance(error, ProviderError):
                    raise
                raise ProviderError("模型返回的数据格式不兼容。") from error

    async def test(self):
        events = []

        async def collect(event):
            events.append(event)

        async with asyncio.timeout(35):
            message, _ = await self.complete([{"role": "user", "content": "只回复 OK"}], [], collect)
        return {"ok": True, "message": "连接成功", "reply": (message.get("content") or "")[:300]}

    async def models(self):
        key = self.settings.key()
        if not key:
            raise ProviderError("请先填写并保存 API Key。")
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(self.settings.value["base_url"].rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
        if response.status_code != 200:
            raise ProviderError("该接口无法获取模型列表，请手动填写模型名称。")
        return sorted(item["id"] for item in response.json().get("data", []) if isinstance(item.get("id"), str))
