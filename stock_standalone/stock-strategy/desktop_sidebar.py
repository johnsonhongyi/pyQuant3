"""Bounded, recoverable sidebar placement through installed Codex App Tools MCP."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid

SECTION_NAME='Muse 模拟策略'
TOOLS={'list_threads','create_sidebar_section','move_thread_to_sidebar_section'}


def installed_runtime():
    home=Path(os.environ.get('USERPROFILE',Path.home()))
    plugins=list((home/'.codex/plugins/cache/openai-bundled/codex-app-tools').glob('*/server.mjs'))
    nodes=[Path(os.environ[k]) for k in ('CODEX_MCP_NODE_PATH','CODEX_BROWSER_USE_NODE_PATH') if os.environ.get(k)]
    nodes+=sorted((Path(os.environ.get('LOCALAPPDATA',''))/'OpenAI/Codex/runtimes/cua_node').glob('*/bin/node.exe'),key=lambda p:p.stat().st_mtime_ns,reverse=True)
    nodes.append(home/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
    node=next((p for p in nodes if p.is_file()),None)
    if not plugins or node is None:raise OSError('APP_TOOLS_RUNTIME_UNAVAILABLE')
    return node,max(plugins,key=lambda p:p.stat().st_mtime_ns)


def pipe_candidates(hint=None):
    values=[os.environ.get('CODEX_APP_TOOLS_PIPE_PATH'),hint]
    if os.name=='nt':
        values+=['\\\\.\\pipe\\'+p for p in os.listdir('\\\\.\\pipe\\') if p.startswith('codex-browser-use-')]
    return list(dict.fromkeys(v for v in values if v))


class AppTools:
    def __init__(self,pipe,thread_id,timeout=6,stop=None):
        node,server=installed_runtime()
        env={**os.environ,'CODEX_APP_TOOLS_PIPE_PATH':pipe}
        self.thread_id,self.timeout,self.counter=thread_id,timeout,0
        self.stop=stop
        self.messages=queue.Queue(maxsize=128)
        self.process=subprocess.Popen([str(node),str(server)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def read():
            try:
                for line in self.process.stdout:
                    if len(line)>8*1024*1024:break
                    self.messages.put(json.loads(line),timeout=1)
            except (OSError,ValueError,queue.Full):pass
            finally:
                try:self.messages.put_nowait({'closed':True})
                except queue.Full:pass
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
        try:
            self.request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'muse-sidebar','version':'1'}})
            self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
            catalog=self.request('tools/list',{})['tools']
            self.schemas={t['name']:t['inputSchema'] for t in catalog if t['name'] in TOOLS}
            if set(self.schemas)!=TOOLS:raise ValueError('APP_TOOLS_CAPABILITY_CHANGED')
            for name,fields in {'list_threads':{'limit'},'create_sidebar_section':{'name'},'move_thread_to_sidebar_section':{'threadId','sectionId'}}.items():
                if not fields<=set(self.schemas[name].get('properties',{})):raise ValueError('APP_TOOLS_SCHEMA_CHANGED')
        except (OSError,ValueError,KeyError,TypeError,TimeoutError):self.close();raise

    def send(self,value):
        self.process.stdin.write((json.dumps(value,ensure_ascii=False)+'\n').encode('utf-8'));self.process.stdin.flush()

    def request(self,method,params):
        self.counter+=1;identity=self.counter
        self.send({'jsonrpc':'2.0','id':identity,'method':method,'params':params})
        deadline=time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            if self.stop and self.stop.is_set():raise OSError('APP_TOOLS_STOPPED')
            try:message=self.messages.get(timeout=min(.1,max(.01,deadline-time.monotonic())))
            except queue.Empty:continue
            if message.get('closed'):raise OSError('APP_TOOLS_DISCONNECTED')
            if message.get('id')!=identity:continue
            if 'error' in message:raise ValueError('APP_TOOLS_RPC_REJECTED')
            return message['result']
        raise TimeoutError('APP_TOOLS_TIMEOUT')

    def call(self,name,arguments):
        if name not in TOOLS:raise ValueError('APP_TOOLS_NOT_ALLOWED')
        schema=self.schemas[name]
        arguments={k:v for k,v in arguments.items() if k in schema.get('properties',{})}
        if not set(schema.get('required',[]))<=set(arguments):raise ValueError('APP_TOOLS_SCHEMA_CHANGED')
        response=self.request('tools/call',{'name':name,'arguments':arguments,'_meta':{'threadId':self.thread_id}})
        if response.get('isError'):raise ValueError('APP_TOOLS_CALL_REJECTED')
        contents=response.get('content',[])
        value=json.loads(next(c['text'] for c in contents if c.get('type')=='text'))
        if not isinstance(value,dict):raise ValueError('APP_TOOLS_INVALID_RESULT')
        return value

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
        for stream in (self.process.stdin,self.process.stdout):
            if stream:stream.close()
        self.reader.join(timeout=1)


def section(snapshot):
    matches=[s for s in snapshot.get('sections',[]) if s.get('name')==SECTION_NAME]
    if len(matches)>1:raise ValueError('APP_TOOLS_AMBIGUOUS_SECTION')
    return matches[0] if matches else None


class SidebarOrganizer:
    def __init__(self,ledger,client=AppTools,discover=pipe_candidates,clock=time.time,stop=None):
        self.db,self.client,self.discover,self.clock=ledger,client,discover,clock
        self.pipe=None;self.probe_cursor=0
        self.stop=stop
        ledger.execute('CREATE TABLE IF NOT EXISTS sidebar_threads(thread_id TEXT PRIMARY KEY,job_id TEXT,status TEXT,error TEXT,attempts INTEGER,next_retry REAL,section_id TEXT,updated_at REAL)')
        ledger.commit()

    def enqueue(self,thread_id,job_id):
        uuid.UUID(thread_id)
        self.db.execute("INSERT OR IGNORE INTO sidebar_threads VALUES(?,?,'pending','',0,0,'',?)",(thread_id,job_id,self.clock()));self.db.commit()

    def drain(self):
        row=self.db.execute("SELECT thread_id,attempts FROM sidebar_threads WHERE status='pending' AND next_retry<=? ORDER BY updated_at LIMIT 1",(self.clock(),)).fetchone()
        if not row:return
        thread_id,attempts=row;client=None
        try:
            candidates=self.discover(self.pipe)
            if not candidates:raise OSError('APP_TOOLS_DESKTOP_OFFLINE')
            # One endpoint per attempt bounds delays even with many desktop windows.
            pipe=self.pipe if self.pipe in candidates else candidates[self.probe_cursor%len(candidates)]
            client=self.client(pipe,thread_id,stop=self.stop) if self.client is AppTools else self.client(pipe,thread_id)
            def call(name,args):
                if self.stop and self.stop.is_set():raise OSError('APP_TOOLS_STOPPED')
                return client.call(name,args)
            snapshot=call('list_threads',{'limit':1});target=section(snapshot)
            if target is None:
                created=call('create_sidebar_section',{'name':SECTION_NAME})
                target={'sectionId':created['sectionId'],'itemKeys':[]}
            key='codex:thread:local:'+thread_id
            if key not in target.get('itemKeys',[]):
                call('move_thread_to_sidebar_section',{'threadId':thread_id,'sectionId':target['sectionId'],'hostId':'local'})
            confirmed=section(call('list_threads',{'limit':1}))
            if not confirmed or confirmed['sectionId']!=target['sectionId'] or key not in confirmed.get('itemKeys',[]):raise ValueError('APP_TOOLS_PLACEMENT_UNCONFIRMED')
            self.pipe=pipe
            self.db.execute("UPDATE sidebar_threads SET status='grouped',error='',section_id=?,updated_at=? WHERE thread_id=?",(target['sectionId'],self.clock(),thread_id))
        except (OSError,ValueError,KeyError,TypeError,TimeoutError,StopIteration) as exc:
            self.pipe=None;self.probe_cursor+=1
            self.db.execute("UPDATE sidebar_threads SET error=?,attempts=attempts+1,next_retry=?,updated_at=? WHERE thread_id=?",(str(exc) if str(exc).startswith('APP_TOOLS_') else type(exc).__name__,self.clock()+min(300,10*2**min(attempts,5)),self.clock(),thread_id))
        finally:
            if client:client.close()
            self.db.commit()

    def status(self):
        pending=self.db.execute("SELECT count(*) FROM sidebar_threads WHERE status='pending'").fetchone()[0]
        last=self.db.execute("SELECT error FROM sidebar_threads WHERE status='pending' ORDER BY updated_at DESC LIMIT 1").fetchone()
        return {'sidebar_pending':pending,'sidebar_error':last[0] if last else '', 'sidebar_group':SECTION_NAME}


class SidebarWorker:
    """UI presentation has its own SQLite connection and never blocks dispatch."""
    def __init__(self, ledger, path):
        self.organizer = SidebarOrganizer(ledger)
        self.path = path
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self._run, name='stock-codex-sidebar', daemon=True)
        self.thread.start()

    def enqueue(self, thread_id, job_id):
        self.organizer.enqueue(thread_id, job_id)
        self.wake.set()

    def status(self):
        return self.organizer.status()

    def _run(self):
        import sqlite3
        from contextlib import closing
        from desktop_strategy_agent import _emit_log
        with closing(sqlite3.connect(self.path, timeout=1)) as db:
            organizer = SidebarOrganizer(db,stop=self.stop)
            while not self.stop.is_set():
                try:organizer.drain()
                except sqlite3.Error as exc:
                    db.rollback()
                    _emit_log({'status':'degraded','stage':'sidebar','error_code':type(exc).__name__})
                self.wake.wait(2)
                self.wake.clear()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=8)
