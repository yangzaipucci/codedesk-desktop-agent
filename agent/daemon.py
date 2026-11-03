"""Opt-in durable step jobs: crash recovery, timer polling and completion notices."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from agent.capabilities import atomic_json, enabled, read_json
from agent.runtime import Runtime
from agent.tools import Tools


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


class JobLock:
    """Kernel-owned locks are released even after a forced process termination."""
    def __init__(self, path):
        self.path = path
    def __enter__(self):
        self.stream = self.path.open('a+b')
        self.stream.seek(0, 2)
        if not self.stream.tell():
            self.stream.write(b'0'); self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise ValueError('该后台任务正在其他进程运行。') from None
        return self
    def __exit__(self, *args):
        self.stream.close()


class Daemon:
    def __init__(self, settings):
        self.settings = settings
        self.directory = settings.directory / 'daemon'
        self.directory.mkdir(parents=True, exist_ok=True)

    def require_enabled(self):
        if not enabled('daemon', self.settings.directory):
            raise ValueError('常驻任务已关闭；启用 ENABLE_DAEMON 或桌面设置中的常驻能力。')

    def path(self, identity):
        import re
        if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity):
            raise ValueError('后台任务 ID 无效。')
        return self.directory / (identity + '.json')

    def create(self, plan):
        self.require_enabled()
        if not isinstance(plan, dict) or len(json.dumps(plan).encode()) > 2*1024*1024:
            raise ValueError('后台计划应为不超过 2 MiB 的 JSON 对象。')
        workspace = plan.get('workspace', self.settings.value['workspace'])
        if not isinstance(workspace,str) or not workspace:
            raise ValueError('后台计划需要有效 workspace。')
        root = Path(workspace).resolve()
        if not root.is_dir():
            raise ValueError('后台任务需要有效的项目目录。')
        steps = plan.get('steps')
        if not isinstance(steps, list) or not 1 <= len(steps) <= 100:
            raise ValueError('后台计划需要 1–100 个步骤。')
        tools = Tools(root, self.settings.directory)
        normalized = []
        for index, item in enumerate(steps):
            if not isinstance(item, dict) or item.get('kind') not in {'write', 'read', 'agent'}:
                raise ValueError('后台步骤支持 write、read、agent。')
            step = {k: item[k] for k in ('kind', 'path', 'content', 'prompt', 'expected_sha256') if k in item}
            path = tools.resolve(step.get('path', ''))
            if path == root:
                raise ValueError('步骤必须指定项目内的目标文件。')
            if step['kind'] == 'write':
                if not isinstance(step.get('content'), str) or len(step['content'].encode()) > 8*1024*1024:
                    raise ValueError('write 步骤内容无效。')
                tools.hooks.before('write', step)
                step['expected_sha256'] = hashlib.sha256(step['content'].encode('utf-8')).hexdigest()
            if step['kind'] == 'agent':
                import re
                if not isinstance(step.get('prompt'), str) or not re.fullmatch(r'[a-f0-9]{64}', str(step.get('expected_sha256', ''))):
                    raise ValueError('agent 步骤需要 prompt 及目标文件 expected_sha256，便于核对重入完成条件。')
            normalized.append({**step, 'number': index+1, 'status': 'pending', 'attempts': 0})
        job = {'id': uuid.uuid4().hex, 'name': str(plan.get('name', '后台任务'))[:120], 'workspace': str(root), 'status': 'pending', 'steps': normalized, 'created_at': datetime.now(timezone.utc).isoformat()}
        atomic_json(self.path(job['id']), job)
        return job

    def get(self, identity):
        return read_json(self.path(identity))

    def summaries(self):
        records = []
        for path in sorted(self.directory.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[:100]:
            value = read_json(path)
            records.append({k:value[k] for k in ('id','name','workspace','status') } | {'completed': sum(s['status']=='completed' for s in value['steps']), 'total': len(value['steps'])})
        notices = []
        for path in sorted((self.directory / 'notifications').glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[:50]:
            notices.append(read_json(path))
        return {'enabled': enabled('daemon', self.settings.directory), 'jobs': records, 'notifications': notices}

    async def run(self, identity, step_delay=0):
        self.require_enabled()
        self.path(identity)
        with JobLock(self.directory / (identity + '.lock')):
            job = self.get(identity)
            if job['status'] == 'completed':
                return job
            root = Path(job['workspace'])
            tools = Tools(root, self.settings.directory)
            job['status'] = 'running'
            for step in job['steps']:
                if step['status'] == 'completed':
                    continue
                target = tools.resolve(step['path'])
                expected = step.get('expected_sha256')
                current = digest(target)
                if expected and current == expected:
                    step.update(status='completed', recovered=True)
                    atomic_json(self.path(identity), job)
                    continue
                if step['status'] == 'running' and 'before_sha256' in step and current != step['before_sha256']:
                    job['status'] = 'conflict'
                    atomic_json(self.path(identity), job)
                    raise ValueError('任务中断后目标文件被其他操作改变，拒绝覆盖。')
                step.update(status='running', before_sha256=current, attempts=step['attempts']+1)
                atomic_json(self.path(identity), job)
                try:
                    if step['kind'] == 'write':
                        result = await tools.execute('write', {'path': step['path'], 'content': step['content']})
                    elif step['kind'] == 'read':
                        result = await tools.execute('read', {'path': step['path']})
                    else:
                        from agent.settings import Settings
                        isolated = Settings(self.settings.directory)
                        isolated.value = dict(self.settings.value, workspace=str(root))
                        isolated.memory_keys = dict(self.settings.memory_keys)
                        runtime = Runtime(isolated)
                        runtime.persistence_group = 'daemon'
                        async def sink(event):
                            pass
                        await runtime.run(step['prompt'], sink)
                        result = {'ok': digest(target) == expected}
                    if not result.get('ok') or expected and digest(target) != expected:
                        raise ValueError(result.get('error', '步骤完成条件未满足。'))
                    step.update(status='completed', completed_at=datetime.now(timezone.utc).isoformat())
                    atomic_json(self.path(identity), job)
                    if step_delay:
                        await asyncio.sleep(step_delay)
                except asyncio.CancelledError:
                    job['status'] = 'interrupted'
                    atomic_json(self.path(identity), job)
                    raise
                except Exception:
                    job['status'] = 'failed'
                    atomic_json(self.path(identity), job)
                    raise
            job['status'] = 'completed'
            atomic_json(self.path(identity), job)
            notice = self.directory / 'notifications' / (identity + '.json')
            if not notice.exists():
                atomic_json(notice, {'id': identity, 'name': job['name'], 'status': 'completed', 'time': datetime.now(timezone.utc).isoformat()})
            return job

    async def watch(self, interval=5, once=False):
        self.require_enabled()
        if not 1 <= interval <= 3600:
            raise ValueError('轮询间隔需要 1–3600 秒。')
        while True:
            for item in self.summaries()['jobs']:
                if item['status'] in {'pending', 'running', 'interrupted'}:
                    try:
                        await self.run(item['id'])
                    except ValueError:
                        continue
            if once:
                return
            await asyncio.sleep(interval)
