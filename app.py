"""Native Windows launcher, with a headless backend mode for curl."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import shutil
import socket
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    from agent.settings import Settings
    from server.app import create_app, resources
    import uvicorn

    settings = Settings()
    if not settings.value["workspace"]:
        sample = settings.directory / "sample-workspace"
        if not sample.exists():
            shutil.copytree(resources() / "sample_workspace", sample)
        settings.save({"workspace": str(sample)})
    app = create_app(settings)
    # Bind the socket once so no process can race the chosen ephemeral port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_config=None, log_level="error", loop="asyncio")
    server = uvicorn.Server(config)
    if args.headless:
        print(f"CodeDesk backend: http://127.0.0.1:{port}", flush=True)
        # A boot token is not an API key. Never print the model credential.
        print(f"Local session token: {app.state.token}", flush=True)
        server.run(sockets=[sock])
        return

    import webview

    class Bridge:
        def choose_folder(self):
            selected = window.create_file_dialog(webview.FileDialog.FOLDER)
            return selected[0] if selected else None

    def backend():
        # ProactorEventLoop on Windows supports cancellable subprocess pipes.
        asyncio.set_event_loop(asyncio.new_event_loop())
        server.run(sockets=[sock])

    thread = threading.Thread(target=backend, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("本地服务启动失败，请重新打开应用。")
        time.sleep(0.05)
    window = webview.create_window("CodeDesk · 桌面智能体", f"http://127.0.0.1:{port}", js_api=Bridge(), width=1440, height=920, min_size=(1120, 720), background_color="#101416", text_select=True)
    try:
        webview.start(debug=False, gui="edgechromium")
    finally:
        if app.state.runtime.active and not app.state.runtime.active.done():
            # Set exit flag; uvicorn shutdown cancels in-flight agent tasks.
            server.should_exit = True
        server.should_exit = True
        thread.join(timeout=8)
        sock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if sys.stderr is not None:
            print(str(error), file=sys.stderr)
        if os.name == "nt" and "--headless" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, "CodeDesk 无法启动。请确认已安装 Microsoft Edge WebView2 运行时。\n\n" + str(error)[:600], "启动失败", 0x10)
        raise
