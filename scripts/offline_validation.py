"""Optional restricted-host harness: asyncio IOCP without its TCP wakeup pair.

This does NOT grant network access. The proactor is polled every 50 ms so thread
callbacks can wake the loop without making a localhost socket connection.
Production launchers do not import this file. Network tests remain restricted.
"""
import asyncio
import os
import runpy
import sys
from pathlib import Path


def configure():
    if os.name != 'nt':
        return
    class OfflineLoop(asyncio.ProactorEventLoop):
        def _make_self_pipe(self):
            from types import SimpleNamespace
            self._csock = SimpleNamespace(fileno=lambda: -1)
        def _close_self_pipe(self):
            pass
        def _write_to_self(self):
            pass
        def _loop_self_reading(self, f=None):
            pass
        def __init__(self):
            super().__init__()
            original=self._proactor.select
            self._proactor.select=lambda timeout=None: original(.05 if timeout is None else min(timeout,.05))
    class Policy(asyncio.WindowsProactorEventLoopPolicy):
        _loop_factory=OfflineLoop
    asyncio.set_event_loop_policy(Policy())


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    configure()
    module=sys.argv[1]
    sys.argv=sys.argv[1:]
    runpy.run_module(module,run_name='__main__')
