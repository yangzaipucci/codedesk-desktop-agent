"""Loopback-only MCP endpoint, separate from the desktop's HTTP API."""
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets


def serve(workspace, transport='streamable-http', port=8001):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    root = Path(workspace).resolve()
    if not root.is_dir() or not 1 <= port <= 65535:
        raise ValueError('MCP 需要有效工作目录及 1–65535 的端口。')
    service = FastMCP('CodeDesk Workspace', host='127.0.0.1', port=port, stateless_http=True, json_response=True, log_level='ERROR')

    @service.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def workspace_info() -> dict:
        """Read the configured workspace's immediate filenames and current UTC time."""
        return {'workspace': root.name, 'files': sorted(p.name for p in root.iterdir() if not p.name.startswith('.'))[:80], 'utc': datetime.now(timezone.utc).isoformat(), 'source': 'CodeDesk external MCP', 'transport': transport}

    if transport == 'stdio':
        service.run(transport='stdio')
        return
    token = os.environ.get('CODEDESK_MCP_TOKEN', '')
    if len(token) < 16:
        raise ValueError('请先设置至少 16 字符的 CODEDESK_MCP_TOKEN（本机 MCP 连接令牌，不是模型 API Key）。')
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    import uvicorn
    app = service.streamable_http_app()

    class Authenticate(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if not secrets.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token):
                return JSONResponse({'error': 'MCP token required'}, status_code=401, headers={'WWW-Authenticate': 'Bearer'})
            return await call_next(request)
    app.add_middleware(Authenticate)
    print(f'CodeDesk MCP: http://127.0.0.1:{port}/mcp', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='error', access_log=False)
