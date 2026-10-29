"""Sequential workspace jobs with independent agent contexts."""
import asyncio
from datetime import datetime, timezone
import json
import uuid

from agent.runtime import Runtime


class TaskQueue:
    def __init__(self, settings, runtime_factory=Runtime):
        self.settings, self.factory = settings, runtime_factory
        self.jobs = []
        self.worker = self.current = None
        self.directory = settings.directory / 'tasks'
        self.directory.mkdir(exist_ok=True)
        for path in self.directory.glob('*.json'):
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
                if job.get('status') in {'queued', 'running'}:
                    job['status'] = 'interrupted'
                self.jobs.append(job)
            except (OSError, ValueError):
                continue
        self.jobs.sort(key=lambda j:j['created_at'])
        self.jobs = self.jobs[-100:]

    @property
    def busy(self):
        return self.worker is not None and not self.worker.done()

    def persist(self, job):
        text = self.settings.redact(json.dumps(job, ensure_ascii=False, indent=2))
        temporary = self.directory / (job['id'] + '.tmp')
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(temporary.with_suffix('.json'))

    def add(self, prompt):
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 30000:
            raise ValueError('请输入任务，最长 30000 字。')
        if len([j for j in self.jobs if j['status'] in {'running','queued'}]) >= 10:
            raise ValueError('最多同时保留 10 个待处理任务。')
        job = {'id':uuid.uuid4().hex,'prompt':prompt.strip(),'workspace':self.settings.value['workspace'],'created_at':datetime.now(timezone.utc).isoformat(),'status':'queued','events':[]}
        self.jobs.append(job)
        self.persist(job)
        if not self.busy:
            self.worker = asyncio.create_task(self.work())
        return job

    async def work(self):
        while queued := next((j for j in self.jobs if j['status']=='queued'), None):
            job = queued
            job['status'] = 'running'
            runtime = self.factory(self.settings)
            runtime.persistence_group = 'task'
            job['session_id'] = runtime.session_id
            self.persist(job)

            async def sink(event):
                job['events'].append(event)
                if event['type']=='done':
                    job['status'] = event['status']
                    job['tokens'] = event.get('tokens', 0)
                # Persist on meaningful progress rather than every token.
                if event['type'] in {'done','tool_result','error'}:
                    self.persist(job)
            self.current = asyncio.create_task(runtime.run(job['prompt'], sink))
            try:
                await self.current
            except asyncio.CancelledError:
                job['status'] = 'cancelled'
            except Exception:
                job['status'] = 'error'
            finally:
                if job['status']=='running':
                    job['status'] = 'error'
                self.persist(job)
                self.current = None

    def get(self, identity):
        job = next((j for j in self.jobs if j['id']==identity), None)
        if job is None:
            raise ValueError('找不到任务。')
        return job

    async def cancel(self, identity):
        job = self.get(identity)
        if job['status']=='queued':
            job['status'] = 'cancelled'
            self.persist(job)
        elif job['status']=='running' and self.current:
            self.current.cancel()
            await asyncio.gather(self.current, return_exceptions=True)
        return job

    def summaries(self):
        return [{k:v for k,v in j.items() if k!='events'} for j in reversed(self.jobs[-100:])]

    async def close(self):
        for job in self.jobs:
            if job['status']=='queued':
                job['status']='interrupted'
                self.persist(job)
        if self.current and not self.current.done():
            self.current.cancel()
            await asyncio.gather(self.current,return_exceptions=True)
        if self.worker and not self.worker.done():
            self.worker.cancel()
            await asyncio.gather(self.worker,return_exceptions=True)
