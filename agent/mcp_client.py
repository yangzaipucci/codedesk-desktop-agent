"""MCP discovery and calls through the official SDK, separate from built-ins."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import os
from pathlib import Path
import re
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


def demo_config() -> dict:
    if getattr(sys, "frozen", False):
        command, args = str(Path(sys._MEIPASS) / "WorkspaceMCP.exe"), []
    else:
        command = sys.executable
        args = [str(Path(__file__).resolve().parents[1] / "mcp_demo.py")]
    return {"workspace-demo": {"transport": "stdio", "command": command, "args": args, "enabled": True}}


class MCP:
    def __init__(self, configs: dict, workspace: Path):
        self.configs = configs
        self.workspace = workspace
        self.routes: dict[str, tuple[str, str]] = {}

    @asynccontextmanager
    async def session(self, name):
        config = self.configs[name]
        async with asyncio.timeout(30):
            if config.get("transport", "stdio") == "stdio":
                command = config.get("command")
                args = config.get("args", [])
                if not isinstance(command, str) or not command or not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                    raise ValueError("MCP command 应为字符串，args 应为字符串数组。")
                # API keys are not inherited. Explicit server-specific env is opt-in.
                env = {k: v for k, v in os.environ.items() if not any(t in k.upper() for t in ("API_KEY", "APIKEY", "CODEDESK_TOKEN"))}
                env.update(config.get("env", {}))
                params = StdioServerParameters(command=command, args=args, env=env, cwd=str(self.workspace))
                with open(os.devnull, "w") as error_log:
                    async with stdio_client(params, errlog=error_log) as (read, write):
                        async with ClientSession(read, write) as client:
                            await client.initialize()
                            yield client
            elif config.get("transport") == "streamable-http":
                from agent.settings import validate_endpoint
                url = validate_endpoint(config["url"])
                async with streamablehttp_client(url) as (read, write, _):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        yield client
            else:
                raise ValueError("MCP 支持 stdio 和 streamable-http。")

    async def discover(self, emit=None) -> list[dict]:
        definitions = []
        self.routes.clear()
        for index, (name, config) in enumerate(self.configs.items()):
            if not isinstance(config, dict) or not config.get("enabled", True):
                continue
            try:
                server_routes = {}
                server_definitions = []
                async with self.session(name) as client:
                    cursor = None
                    for _ in range(10):
                        listing = await client.list_tools(cursor=cursor)
                        for tool in listing.tools:
                            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', tool.name)
                            suffix = hashlib.sha256(tool.name.encode()).hexdigest()[:7]
                            alias = f"mcp_{index}_{clean_name[:36]}_{suffix}"
                            if alias in server_routes:
                                raise ValueError("MCP 工具名称重复。")
                            server_routes[alias] = (name, tool.name)
                            server_definitions.append({"type": "function", "function": {"name": alias, "description": f"[MCP · {name}] {tool.description or tool.name}", "parameters": tool.inputSchema}})
                        cursor = listing.nextCursor
                        if not cursor:
                            break
                    else:
                        raise ValueError("MCP 工具列表分页超过限制。")
                # Commit only after every page and clean shutdown succeed.
                self.routes.update(server_routes)
                definitions.extend(server_definitions)
                if emit:
                    await emit({"type": "mcp_status", "server": name, "ok": True, "tools": [tool for server, tool in self.routes.values() if server == name]})
            except asyncio.CancelledError:
                raise
            except Exception:
                if emit:
                    await emit({"type": "mcp_status", "server": name, "ok": False, "error": "连接失败，请检查命令、依赖、服务地址及网络。"})
        return definitions

    async def call(self, alias, arguments) -> dict:
        if alias not in self.routes:
            return {"ok": False, "error": "未找到已连接的 MCP 工具，请重新连接服务。"}
        name, tool_name = self.routes[alias]
        try:
            async with self.session(name) as client:
                response = await client.call_tool(tool_name, arguments)
            result = response.model_dump(mode="json", by_alias=True)
            return {"ok": not response.isError, "server": name, "tool": tool_name, "content": result.get("content", []), "structuredContent": result.get("structuredContent")}
        except asyncio.CancelledError:
            raise
        except Exception:
            return {"ok": False, "server": name, "error": "MCP 调用失败或超时，请检查外部服务。"}
