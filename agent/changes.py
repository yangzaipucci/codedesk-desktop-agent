"""Persistent file snapshots for user-initiated undo, outside model tools."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from agent.settings import data_directory


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def atomic_bytes(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".codedesk-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class ChangeStore:
    def __init__(self, workspace: Path, directory: Path | None = None):
        self.workspace = workspace.resolve()
        identifier = digest(str(self.workspace).encode("utf-8"))[:24]
        self.directory = (directory or data_directory()) / "changes" / identifier

    def record(self, path: Path, after: bytes) -> str:
        identity = uuid.uuid4().hex
        before = path.read_bytes() if path.exists() else None
        self.directory.mkdir(parents=True, exist_ok=True)
        if before is not None:
            atomic_bytes(self.directory / f"{identity}.before", before)
        metadata = {"id": identity, "workspace": str(self.workspace), "path": str(path.relative_to(self.workspace)), "existed": before is not None, "before_sha256": digest(before) if before is not None else None, "after_sha256": digest(after), "created_at": datetime.now(timezone.utc).isoformat(), "undone": False}
        atomic_bytes(self.directory / f"{identity}.json", json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
        return identity

    def undo(self, identity: str) -> dict:
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise ValueError("无效的修改记录编号。")
        record_path = self.directory / f"{identity}.json"
        if not record_path.is_file():
            raise ValueError("找不到此工作目录的修改记录。")
        metadata = json.loads(record_path.read_text(encoding="utf-8"))
        if metadata.get("workspace") != str(self.workspace):
            raise ValueError("修改记录不属于当前工作目录。")
        if metadata.get("undone"):
            raise ValueError("此修改已经撤销。")
        target = (self.workspace / metadata["path"]).resolve()
        if not target.is_relative_to(self.workspace) or ".git" in target.relative_to(self.workspace).parts:
            raise ValueError("撤销路径超出允许范围。")
        if not target.is_file() or digest(target.read_bytes()) != metadata["after_sha256"]:
            raise ValueError("文件在这次修改后又发生变化，已拒绝覆盖。请先检查差异，或按相反顺序撤销较新的修改。")
        if metadata["existed"]:
            before = (self.directory / f"{identity}.before").read_bytes()
            if digest(before) != metadata["before_sha256"]:
                raise ValueError("文件快照校验失败，未执行撤销。")
            atomic_bytes(target, before)
        else:
            target.unlink()
        metadata["undone"] = True
        metadata["undone_at"] = datetime.now(timezone.utc).isoformat()
        atomic_bytes(record_path, json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
        return {"ok": True, "path": metadata["path"], "change_id": identity, "restored": metadata["existed"], "message": "已恢复修改前的文件。" if metadata["existed"] else "已撤销新建文件。"}
