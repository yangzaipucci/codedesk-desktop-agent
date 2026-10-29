"""A real external stdio MCP server. No model, no mock tool responses."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


def main():
    for raw in sys.stdin.buffer:
        try:
            request = json.loads(raw)
            method, identity = request.get("method"), request.get("id")
            if identity is None:
                continue
            if method == "initialize":
                result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "workspace-demo", "version": "1.0.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [{"name": "workspace_info", "description": "Return the real current workspace directory, its immediate filenames and UTC time. This runs in an external MCP server process.", "inputSchema": {"type": "object", "properties": {}}}]}
            elif method == "tools/call" and request.get("params", {}).get("name") == "workspace_info":
                info = {"workspace": str(Path.cwd()), "files": sorted(p.name for p in Path.cwd().iterdir() if not p.name.startswith("."))[:80], "utc": datetime.now(timezone.utc).isoformat(), "process": "external MCP server"}
                result = {"content": [{"type": "text", "text": json.dumps(info, ensure_ascii=False)}], "isError": False}
            else:
                sys.stdout.buffer.write((json.dumps({"jsonrpc": "2.0", "id": identity, "error": {"code": -32601, "message": "Method not found"}}) + "\n").encode())
                sys.stdout.buffer.flush()
                continue
            sys.stdout.buffer.write((json.dumps({"jsonrpc": "2.0", "id": identity, "result": result}, ensure_ascii=False) + "\n").encode())
            sys.stdout.buffer.flush()
        except (ValueError, OSError):
            continue


if __name__ == "__main__":
    main()
