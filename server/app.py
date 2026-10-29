"""Authenticated localhost transport: REST, WebSocket, SSE."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import secrets
import sys

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from agent.mcp_client import MCP, demo_config
from agent.provider import Provider
from agent.runtime import Runtime
from agent.settings import Settings
from agent.tools import Tools


def resources() -> Path:
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def create_app(settings=None, token=None, runtime=None):
    settings = settings or Settings()
    token = token or secrets.token_urlsafe(32)
    runtime = runtime or Runtime(settings)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.state.token, app.state.settings, app.state.runtime = token, settings, runtime

    @app.middleware("http")
    async def secure(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
                return JSONResponse({"error": "未授权"}, status_code=401)
        try:
            response = await call_next(request)
        except (ValueError, OSError) as error:
            return JSONResponse({"error": settings.redact(str(error))}, status_code=400)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:*; frame-ancestors 'none'; base-uri 'none'"
        return response

    def idle():
        if runtime.active and not runtime.active.done():
            raise HTTPException(409, "任务进行中，请先中断再修改设置。")

    @app.get("/")
    async def index():
        html = (resources() / "ui" / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("__BOOT_TOKEN__", token))

    @app.get("/app.js")
    async def script():
        return Response((resources() / "ui" / "app.js").read_text(encoding="utf-8"), media_type="text/javascript")

    @app.get("/style.css")
    async def style():
        return Response((resources() / "ui" / "style.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/api/settings")
    async def get_settings():
        return settings.public()

    @app.post("/api/settings")
    async def save_settings(request: Request):
        idle()
        return settings.save(await request.json())

    @app.post("/api/test")
    async def test_connection():
        idle()
        try:
            return await Provider(settings).test()
        except TimeoutError:
            return JSONResponse({"error": "连接测试超时。"}, 400)
        except ValueError as error:
            return JSONResponse({"error": settings.redact(str(error))}, 400)

    @app.get("/api/models")
    async def get_models():
        return {"models": await Provider(settings).models()}

    @app.get("/api/files")
    async def get_files(path: str = "."):
        if not settings.value["workspace"]:
            return {"files": []}
        tools = Tools(Path(settings.value["workspace"]))
        directory = tools.resolve(path)
        if not directory.is_dir():
            raise ValueError("目录不存在。")
        hidden = {".git", ".venv", "node_modules", "__pycache__", ".build-temp", ".local-state", ".pytest_cache"}
        files = []
        for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if item.name in hidden or item.name.startswith(".env") or item.is_symlink():
                continue
            files.append({"name": item.name, "path": str(item.relative_to(tools.workspace)).replace("\\", "/"), "directory": item.is_dir()})
            if len(files) >= 300:
                break
        return {"files": files}

    @app.get("/api/file")
    async def get_file(path: str):
        return Tools(Path(settings.value["workspace"])).read(path, limit=500)

    @app.get("/api/history")
    async def history():
        return {"events": runtime.events, "session_id": runtime.session_id}

    @app.post("/api/undo")
    async def undo_change(request: Request):
        idle()
        payload = await request.json()
        change_id = payload.get("change_id")
        if not isinstance(change_id, str) or not change_id:
            raise ValueError("缺少修改记录编号。")
        result = Tools(Path(settings.value["workspace"])).undo(change_id)
        if not result.get("ok"):
            return JSONResponse(result, status_code=409)
        # Subsequent model requests must observe actual file state after undo.
        if runtime.messages:
            runtime.messages.append({"role": "user", "content": f"用户已撤销对 {result.get('path', '')} 的修改。继续任务前请重新 read 文件，不要假定之前的修改仍存在。"})
        return result

    @app.post("/api/new")
    async def new_session():
        idle()
        runtime.reset()
        return {"ok": True}

    @app.post("/api/stop")
    async def stop():
        if runtime.active and not runtime.active.done():
            runtime.active.cancel()
            await runtime.active
        return {"ok": True}

    @app.post("/api/mcp/demo")
    async def enable_demo():
        idle()
        return settings.save({"mcp_servers": {**settings.value["mcp_servers"], **demo_config()}})

    @app.post("/api/mcp/test")
    async def mcp_test():
        idle()
        workspace = settings.value["workspace"]
        if not workspace:
            raise ValueError("请先选择工作目录。")
        client = MCP(settings.value["mcp_servers"], Path(workspace))
        statuses = []

        async def collect(event):
            statuses.append(event)

        definitions = await client.discover(collect)
        result = {"statuses": statuses, "tools": definitions}
        for alias, (name, tool) in client.routes.items():
            if name == "workspace-demo" and tool == "workspace_info":
                result["demo_call"] = await client.call(alias, {})
        return result

    @app.get("/api/trace")
    async def trace():
        lines = ["# CodeDesk 运行记录", "", f"会话：{runtime.session_id}", f"工作目录：{runtime.workspace}", ""]
        lines.extend("```json\n" + json.dumps(e, ensure_ascii=False, indent=2) + "\n```\n" for e in runtime.events)
        return Response(settings.redact("\n".join(lines)), media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="trace.md"'})

    async def start_run(prompt, sink):
        idle()
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 30000:
            raise ValueError("请输入任务，最长 30000 字。")
        runtime.active = asyncio.create_task(runtime.run(prompt.strip(), sink))
        return runtime.active

    @app.post("/api/run")
    async def sse_run(request: Request):
        payload = await request.json()
        queue = asyncio.Queue()

        async def sink(event):
            await queue.put(event)

        task = await start_run(payload.get("prompt"), sink)

        async def stream():
            try:
                while True:
                    event = await queue.get()
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                    if event["type"] == "done":
                        break
            finally:
                if not task.done():
                    task.cancel()
                    await task

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.websocket("/ws")
    async def socket(websocket: WebSocket):
        await websocket.accept()
        task = None
        try:
            auth = await asyncio.wait_for(websocket.receive_json(), 5)
            if not secrets.compare_digest(str(auth.get("token", "")), token):
                await websocket.close(1008)
                return
            payload = await websocket.receive_json()

            async def sink(event):
                try:
                    await websocket.send_json(event)
                except (WebSocketDisconnect, RuntimeError):
                    # Let the receive loop cancel the task and its subprocesses.
                    pass

            task = await start_run(payload.get("prompt"), sink)
            receive = asyncio.create_task(websocket.receive())
            try:
                done, _ = await asyncio.wait([task, receive], return_when=asyncio.FIRST_COMPLETED)
                if receive in done and not task.done():
                    task.cancel()
                    await task
            finally:
                receive.cancel()
                await asyncio.gather(receive, return_exceptions=True)
            await websocket.close()
        except (WebSocketDisconnect, TimeoutError):
            pass
        except (ValueError, HTTPException) as error:
            try:
                await websocket.send_json({"type": "error", "text": str(error)})
                await websocket.close()
            except RuntimeError:
                pass
        finally:
            if task and not task.done():
                task.cancel()
                await task

    return app
