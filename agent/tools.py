"""Exactly four built-in tools, with deterministic file operations."""
from __future__ import annotations

import asyncio
import base64
import difflib
import json
import mimetypes
import os
from pathlib import Path
import signal
import subprocess
import tempfile

from agent.changes import ChangeStore

MAX_OUTPUT = 24000
MAX_FILE = 8 * 1024 * 1024


def definition(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


DEFINITIONS = [
    definition("read", "Read a workspace file. Text returns numbered lines (offset is 1-based), pagination and remaining lines. Images return image content blocks, never base64 in text.", {"path": {"type": "string"}, "offset": {"type": "integer", "minimum": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, ["path"]),
    definition("write", "Atomically write UTF-8 content, creating parents. Overwrite reports old/new line counts and diff. Read an existing file before changing it.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    definition("edit", "Replace exactly one occurrence of old with new. Zero or multiple matches fail without modifying the file. Supply more context on failure. Never rewrite the whole file for a small edit.", {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, ["path", "old", "new"]),
    definition("bash", "Run a command in the workspace. On Windows the shell is PowerShell, not Bash: use PowerShell syntax. Returns bounded stdout, stderr, exit_code, timed_out. Nonzero exits are normal tool results. Use for search, git, packages and tests. Timeout max 120 seconds.", {"command": {"type": "string"}, "timeout": {"type": "number", "minimum": 0.1, "maximum": 120}}, ["command"]),
]


class ToolError(ValueError):
    pass


def atomic_write(path: Path, content: str):
    if len(content.encode("utf-8")) > MAX_FILE:
        raise ToolError("文件超过 8 MiB 写入上限。")
    path.parent.mkdir(parents=True, exist_ok=True)
    file_id, temporary = tempfile.mkstemp(prefix=".codedesk-", dir=path.parent)
    try:
        with os.fdopen(file_id, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Tools:
    def __init__(self, workspace: Path, state_directory: Path | None = None):
        self.workspace = workspace.resolve()
        self.changes = ChangeStore(self.workspace, state_directory)

    def undo(self, change_id: str) -> dict:
        return self.changes.undo(change_id)

    def resolve(self, name: str) -> Path:
        path = (self.workspace / name).resolve()
        if not path.is_relative_to(self.workspace):
            raise ToolError("文件路径超出所选工作目录。")
        if any(part == ".git" for part in path.relative_to(self.workspace).parts):
            raise ToolError("不直接操作 .git 内部文件，请使用 git 命令。")
        return path

    def _text(self, path: Path) -> str:
        if path.stat().st_size > MAX_FILE:
            raise ToolError("文件超过 8 MiB。请用 bash 分段处理。")
        return path.read_bytes().decode("utf-8-sig")

    def read(self, path: str, offset: int = 1, limit: int = 200) -> dict:
        target = self.resolve(path)
        if not target.is_file():
            raise ToolError(f"找不到文件：{path}")
        mime = mimetypes.guess_type(target.name)[0] or ""
        if mime in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            if target.stat().st_size > MAX_FILE:
                raise ToolError("图片超过 8 MiB，请先缩小。")
            return {"ok": True, "path": path, "content": [{"type": "image", "mimeType": mime, "data": base64.b64encode(target.read_bytes()).decode()}]}
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 1:
            raise ToolError("offset 从 1 开始。")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ToolError("limit 必须为 1–500。")
        selected, used, total, page_full, line_truncated = [], 0, 0, False, False
        # Keep only a bounded prefix of each line, including for multi-GiB lines.
        # Scan the rest without retaining it so remaining_lines is exact.
        with target.open("r", encoding="utf-8-sig", newline=None) as handle:
            while True:
                fragment = handle.readline(MAX_OUTPUT + 2)
                if not fragment:
                    break
                total += 1
                ended = fragment.endswith("\n")
                prefix = fragment.rstrip("\n")
                truncated = len(prefix) > MAX_OUTPUT
                if not ended:
                    while remainder := handle.readline(MAX_OUTPUT + 2):
                        truncated = True
                        if remainder.endswith("\n"):
                            break
                if total < offset or page_full:
                    continue
                if len(selected) >= limit:
                    page_full = True
                    continue
                numbered = f"{total:>5}  {prefix}"
                available = MAX_OUTPUT - used - (1 if selected else 0)
                if len(numbered) > available:
                    if selected:
                        page_full = True
                        continue
                    suffix = " [该行过长，已截断；请用 bash 处理]"
                    numbered = numbered[:max(0, available - len(suffix))] + suffix
                    truncated = True
                    page_full = True
                selected.append(numbered)
                used += len(numbered) + (1 if len(selected) > 1 else 0)
                line_truncated = line_truncated or truncated
        end = min(total, offset - 1 + len(selected))
        return {"ok": True, "path": path, "total_lines": total, "remaining_lines": max(0, total - end), "next_offset": end + 1 if end < total else None, "text": "\n".join(selected), "truncated": line_truncated}

    def _changed(self, target: Path, path: str, before: str, after: str) -> dict:
        diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}"))
        if len(after.encode("utf-8")) > MAX_FILE:
            raise ToolError("文件超过 8 MiB 写入上限。")
        change_id = self.changes.record(target, after.encode("utf-8"))
        atomic_write(target, after)
        return {"ok": True, "path": path, "old_lines": len(before.splitlines()), "new_lines": len(after.splitlines()), "diff": diff[:MAX_OUTPUT], "diff_truncated": len(diff) > MAX_OUTPUT, "change_id": change_id}

    def write(self, path: str, content: str) -> dict:
        target = self.resolve(path)
        before = self._text(target) if target.exists() else ""
        return self._changed(target, path, before, content)

    def edit(self, path: str, old: str, new: str) -> dict:
        if not old:
            raise ToolError("old 不能为空。")
        target = self.resolve(path)
        before = self._text(target)
        count = before.count(old)
        if count != 1:
            raise ToolError(f"old 出现 {count} 次，要求恰好 1 次。文件未修改，请先 read 并补充上下文。")
        return self._changed(target, path, before, before.replace(old, new, 1))

    async def bash(self, command: str, timeout: float = 30, emit=None) -> dict:
        timeout = float(timeout)
        if not 0.1 <= timeout <= 120:
            raise ToolError("命令超时必须在 0.1–120 秒之间。")
        if os.name == "nt":
            args = ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); " + command]
            options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            args, options = ["/bin/bash", "-c", command], {"start_new_session": True}
        env = {k: v for k, v in os.environ.items() if not any(term in k.upper() for term in ("API_KEY", "APIKEY", "CODEDESK_TOKEN"))}
        process = await asyncio.create_subprocess_exec(*args, cwd=self.workspace, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **options)

        async def collect(stream, channel):
            kept, length, total = [], 0, 0
            while chunk := await stream.read(4096):
                part = chunk.decode("utf-8", errors="replace")
                total += len(part)
                if length < MAX_OUTPUT:
                    fragment = part[:MAX_OUTPUT - length]
                    kept.append(fragment)
                    length += len(fragment)
                    if emit:
                        await emit({"type": "command_output", "channel": channel, "text": fragment})
            return "".join(kept), total > MAX_OUTPUT

        async def stop_tree():
            if os.name == "nt":
                killer = await asyncio.create_subprocess_exec("taskkill", "/PID", str(process.pid), "/T", "/F", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                await killer.wait()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await process.wait()

        stdout_task = asyncio.create_task(collect(process.stdout, "stdout"))
        stderr_task = asyncio.create_task(collect(process.stderr, "stderr"))
        timed_out = False
        try:
            await asyncio.wait_for(asyncio.shield(process.wait()), timeout)
            results = await asyncio.wait_for(asyncio.gather(stdout_task, stderr_task), max(0.1, timeout))
        except asyncio.TimeoutError:
            timed_out = True
            await stop_tree()
            results = await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        except asyncio.CancelledError:
            await stop_tree()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise
        clean = [item if isinstance(item, tuple) else ("", True) for item in results]
        return {"ok": process.returncode == 0 and not timed_out, "stdout": clean[0][0], "stderr": clean[1][0], "exit_code": process.returncode, "timed_out": timed_out, "truncated": clean[0][1] or clean[1][1]}

    async def execute(self, name: str, arguments: dict, emit=None) -> dict:
        try:
            if name == "bash":
                return await self.bash(**arguments, emit=emit)
            if name not in {"read", "write", "edit"}:
                raise ToolError(f"未知工具：{name}")
            return getattr(self, name)(**arguments)
        except (ValueError, OSError, TypeError) as error:
            return {"ok": False, "error": str(error)[:4000]}


def model_result(result: dict) -> str:
    return json.dumps({k: v for k, v in result.items() if k != "content"}, ensure_ascii=False)
