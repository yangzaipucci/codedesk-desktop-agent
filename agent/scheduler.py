"""routines.yaml -> durable claimed queue -> isolated skill Runtime."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time

from agent.capabilities import atomic_json,enabled,read_json
from agent.runtime import Runtime
from agent.skills import Skills


class Scheduler:
    def __init__(self,settings,provider_factory=None):
        self.settings,self.provider_factory=settings,provider_factory
        self.directory=settings.directory/'scheduler'
        self.directory.mkdir(parents=True,exist_ok=True)

    def load(self,path):
        import yaml
        path=Path(path).resolve()
        root=Path(self.settings.value['workspace']).resolve()
        if not path.is_relative_to(root) or path.is_symlink() or not path.is_file() or path.stat().st_size>65536:
            raise ValueError('routines.yaml 必须位于当前项目内且不超过64 KiB。')
        try:
            data=yaml.safe_load(path.read_text(encoding='utf-8-sig'))
        except yaml.YAMLError as error:
            raise ValueError('routines.yaml 格式有误，请检查缩进与字段。') from error
        routines=data.get('routines') if isinstance(data,dict) else None
        if not isinstance(routines,list) or len(routines)>20:
            raise ValueError('routines.yaml 需要最多20条 routines。')
        import re
        names=set()
        for item in routines:
            if not isinstance(item,dict) or not re.fullmatch(r'[a-z0-9-]{1,64}',str(item.get('id',''))) or item['id'] in names:
                raise ValueError('定时任务 id 必须是唯一的小写字母数字短横线。')
            names.add(item['id'])
            if not isinstance(item.get('skill'),str) or not isinstance(item.get('prompt'),str) or len(item['prompt'])>10000:
                raise ValueError('定时任务需要 skill 和 prompt。')
            if ('at' in item)==('every_seconds' in item):
                raise ValueError('定时任务只能选择 at 或 every_seconds 一种时间。')
            if 'at' in item:self.when(item['at'])
            elif type(item['every_seconds']) is not int or not 60<=item['every_seconds']<=31536000:
                raise ValueError('every_seconds 范围是60秒至一年。')
        return routines

    @staticmethod
    def when(value):
        at=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if at.tzinfo is None:raise ValueError('at 必须包含时区，例如 +08:00。')
        return at.timestamp()

    async def tick(self,path,now=None):
        if not enabled('scheduler',self.settings.directory):
            return {'triggers_fired':0,'status':'disabled','runs':[]}
        now=time.time() if now is None else now
        routines=self.load(path)
        registry=Skills(self.settings.value['workspace'],self.settings.directory)
        from agent.daemon import JobLock
        records=[]
        with JobLock(self.directory/'scheduler.lock'):
            for item in routines:
                if item.get('enabled',True) is not True:continue
                if item['skill'] not in registry.entries:
                    raise ValueError('定时任务引用了未启用的技能：'+item['skill'])
                if 'at' in item:
                    when=self.when(item['at'])
                    if now<when:continue
                    slot=str(when)
                else:slot=str(int(now//item['every_seconds']))
                # Include workspace and schedule; repeated ticks cannot enqueue twice.
                identity=hashlib.sha256((str(Path(path).resolve())+'|'+item['id']+'|'+slot).encode()).hexdigest()
                target=self.directory/(identity+'.json')
                if target.exists():continue
                record={'id':identity,'routine':item['id'],'skill':item['skill'],'status':'running','slot':slot,'started_at':datetime.now(timezone.utc).isoformat()}
                atomic_json(target,record)
                events=[]
                async def sink(event):events.append(event)
                try:
                    runtime=Runtime(self.settings,self.provider_factory(item) if self.provider_factory else None)
                    runtime.persistence_group='scheduler'
                    await runtime.run('/skill '+item['skill']+' '+item['prompt'],sink)
                    completed=bool(events) and events[-1].get('status')=='completed'
                    record['status']='completed' if completed else 'failed'
                    record['tool_calls']=sum(e['type']=='tool_start' for e in events)
                    record['skill_loaded']=any(e['type']=='tool_result' and e['result'].get('skill_loaded')==item['skill'] for e in events)
                except BaseException:
                    record['status']='interrupted'
                    raise
                finally:
                    atomic_json(target,record)
                if record['status']=='completed':
                    notice={'id':identity,'name':item['id'],'status':'completed','time':datetime.now(timezone.utc).isoformat()}
                    if enabled('notifications',self.settings.directory):
                        from agent.notifications import notify_completion
                        notice['system_notification']=await notify_completion(item['id'])
                    atomic_json(self.settings.directory/'daemon/notifications'/(identity+'.json'),notice)
                records.append(record)
        return {'triggers_fired':len(records),'runs':records,'status':'completed'}
