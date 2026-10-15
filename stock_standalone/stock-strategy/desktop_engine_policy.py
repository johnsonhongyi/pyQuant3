"""Daily durable model catalog and idle-boundary engine handover."""
from datetime import datetime,timedelta,timezone
import json
import queue
import sqlite3
from pathlib import Path

HK=timezone(timedelta(hours=8))


def engine_identity(path):
    stat=Path(path).stat()
    return {'path':str(Path(path).absolute()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}


class EngineCatalog:
    def __init__(self,db,initial,discover,probe,identity=engine_identity):
        self.db,self.discover,self.probe,self.identity=db,discover,probe,identity
        self.engine=initial;self.models=[];self.fetched_at=0;self.day=''
        self.fingerprint=None;self.checked_at=0;self.retry_at=0;self.last_error=None
        row=db.execute("SELECT value FROM runtime WHERE key='engine_catalog'").fetchone()
        if row:
            try:
                saved=json.loads(row[0]);fingerprint=identity(saved['engine'])
                if saved['fingerprint']==fingerprint and saved['models']:
                    self.engine=saved['engine'];self.models=saved['models'];self.fingerprint=fingerprint
                    self.fetched_at=float(saved['fetched_at']);self.day=saved['day']
            except (OSError,ValueError,KeyError,TypeError):pass

    def refresh_idle(self,now):
        """Called only before claiming work; never replace an in-flight process."""
        if self.models and now-self.checked_at<60:return False
        self.checked_at=now
        day=datetime.fromtimestamp(now,HK).date().isoformat()
        try:
            candidate=self.discover() or self.engine
            fingerprint=self.identity(candidate)
            changed=fingerprint!=self.fingerprint
            if self.models and not changed and day==self.day:return False
            if now<self.retry_at:return False
            models=self.probe(candidate)
            if not models:raise ValueError('empty model catalog')
            saved={'engine':candidate,'fingerprint':fingerprint,'models':models,'fetched_at':now,'day':day}
            # Commit the validated replacement before advertising or using it.
            self.db.execute("INSERT OR REPLACE INTO runtime VALUES('engine_catalog',?)",(json.dumps(saved),))
            self.db.commit()
            self.engine,self.fingerprint,self.models=candidate,fingerprint,models
            self.fetched_at,self.day,self.last_error=now,day,None
            self.retry_at=0
            return True
        except (OSError,ValueError,KeyError,TypeError,TimeoutError,queue.Empty,sqlite3.Error) as exc:
            self.last_error=type(exc).__name__;self.retry_at=now+300
            return False

    def status(self):
        return {'catalog_refresh':'daily_HK','engine_switch':'idle_validated',
                'engine_update_error':self.last_error,'catalog_day':self.day}
