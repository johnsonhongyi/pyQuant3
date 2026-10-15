"""Discover running packaged TK/ATS and their shared persisted IPC directory."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import hashlib
import sqlite3
import time
from contextlib import closing


def desktop_cli():
    """Prefer an already-installed desktop engine over the standalone CLI shim."""
    base=Path(os.environ.get('LOCALAPPDATA',''))/'OpenAI'/'Codex'/'bin'
    candidates=[p for p in base.glob('*/codex.exe') if p.is_file()]
    if candidates:return str(max(candidates,key=lambda p:p.stat().st_mtime_ns))
    from ats.llm.cli_paths import resolve_cli_path
    return resolve_cli_path('','codex')


def live_store(root,name):
    """Resolve the existing RAMDisk contract without initializing or copying stores."""
    local=Path(os.path.abspath(Path(root)/name))
    from JohnsonUtil import LoggerFactory
    identity=hashlib.sha256(str(local).casefold().encode('utf-8')).hexdigest()[:16]
    for drive in LoggerFactory.ramdisk_rootList:
        if not drive:continue
        base=str(drive)
        if len(base)==2 and base[1]==':':base+='/'
        candidate=Path(base)/'instock_runtime'/identity/name
        if candidate.is_file():return candidate
    return local


def discover_runtime():
    if os.name!='nt':return {'status':'unavailable','error':'Windows desktop required'}
    script="""$p=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('ATS_Terminal.exe','instock_MonitorTK_Nuita.exe','instock_MonitorTK.exe') } | Select-Object ProcessId,Name,ExecutablePath); $c=@(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(26670,26676) } | Select-Object LocalAddress,LocalPort,OwningProcess); @{processes=$p;listeners=$c} | ConvertTo-Json -Depth 4 -Compress"""
    try:
        process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if process.returncode:raise ValueError('desktop discovery failed')
        data=json.loads(process.stdout.decode('utf-8-sig'))
        processes=data.get('processes') or []
        roots={str(Path(p['ExecutablePath']).parent) for p in processes if p.get('ExecutablePath') and (Path(p['ExecutablePath']).parent/'global.ini').is_file() and (Path(p['ExecutablePath']).parent/'trading_signals.db').is_file()}
        if len(roots)!=1:raise ValueError('ambiguous or missing packaged desktop data root')
        root=next(iter(roots));listeners=data.get('listeners') or []
        names={p['ProcessId']:p['Name'] for p in processes}
        ats=next((c for c in listeners if c['LocalPort']==26670 and names.get(c['OwningProcess'])=='ATS_Terminal.exe'),None)
        tk=next((c for c in listeners if c['LocalPort']==26676 and names.get(c['OwningProcess'],'').startswith('instock_MonitorTK')),None)
        health=None
        if tk:
            url='http://'+tk['LocalAddress']+':26676/bridge/v1/health'
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=3) as response:health=json.load(response)
        store=live_store(root,'system_linkage.sqlite3');ipc_health=[]
        if store.is_file():
            with closing(sqlite3.connect(store.as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
                db.row_factory=sqlite3.Row
                ipc_health=[dict(r)|{'age_seconds':max(0,int(time.time()-r['last_seen']))} for r in db.execute('SELECT consumer,last_seen,favorites_revision,quote_status FROM linkage_consumer_health')]
        consumers_online=all(any(r['consumer']==name and r['age_seconds']<=30 for r in ipc_health) for name in ('TK','ATS'))
        return {'status':'connected' if ats and tk and health and health.get('status')=='ok' and consumers_online else 'degraded',
                'data_root':root,'ats_pid':ats['OwningProcess'] if ats else None,'tk_pid':tk['OwningProcess'] if tk else None,
                'ats_port':26670 if ats else None,'tk_port':26676 if tk else None,'tk_health':health,
                'linkage_db':str(store),'ipc_health':ipc_health}
    except (OSError,ValueError,KeyError,sqlite3.Error,subprocess.TimeoutExpired) as exc:
        return {'status':'unavailable','error':type(exc).__name__}
