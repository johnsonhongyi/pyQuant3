"""Detached Agent Hub batch supervisor for session-independent execution."""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

def discover_plan_tasks(root: Path) -> dict[str, str]:
    """Discover task IDs/titles from the newest executable plan, not code constants."""
    candidates = sorted((root/'docs').glob('*EXECUTION*PLAN*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
    tasks = {}
    for plan in candidates:
        try: text = plan.read_text(encoding='utf-8')
        except OSError: continue
        for match in re.finditer(r'(?m)^##.*?Task\s+(\d{3})(?:/(\d{3}))?\s*[:：]?\s*(.*?)\s*$', text):
            task_id, second_id, title = match.group(1), match.group(2), match.group(3)
            title = re.sub(r'[（(]\s*P\d\s*[）)]\s*$', '', title).strip()
            slug = re.sub(r'[^a-z0-9]+','_',title.lower()).strip('_')[:48] or 'plan_task'
            tasks.setdefault(task_id, slug)
            if second_id: tasks.setdefault(second_id, slug)
    return tasks

def ensure_plan_tasks(root: Path, task_ids=None) -> dict:
    """Self-heal missing task registrations from the current execution plan."""
    plan_tasks = discover_plan_tasks(root)
    ids = task_ids or list(plan_tasks)
    inbox = root/'.agent_hub'/'inbox'; created=[]; existing=[]; errors=[]
    template = root/'.agent_hub'/'task_template.md'
    for tid in ids:
        slug = plan_tasks.get(tid, f'plan_task_{tid}')
        path = inbox/f'{tid}_{slug}.md'
        if path.exists(): existing.append(tid); continue
        try:
            text = (template.read_text(encoding='utf-8') if template.exists() else '# Task\n')
            text = text.replace('Task-ID: 000',f'Task-ID: {tid}').replace('P1','P0',1)
            text = text.replace('一句话说明唯一交付目标。',f'执行当前计划 Task {tid}: {slug.replace("_", " ")}。')
            path.write_text(text, encoding='utf-8'); created.append(tid)
        except OSError as exc: errors.append(f'{tid}: {exc}')
    return {'created':created,'existing':existing,'errors':errors,'registered':not errors}

def _now(): return datetime.now(timezone.utc).isoformat()
def start(root: Path, tasks=None, workers=None) -> dict:
    registration = ensure_plan_tasks(root, tasks)
    if registration['errors']:
        return {'status':'BLOCKED_REGISTRATION','registration':registration,
                'message':'无法写入 Agent Hub inbox，未启动任何 Worker'}
    run_dir = root / '.agent_hub_runtime'; run_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = f'run_{stamp}'
    manifest = {'run_id':run_id,'started_at':_now(),'status':'RUNNING','tasks':tasks or [],'pid':None}
    mpath = run_dir / f'{run_id}.json'; mpath.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    log = run_dir / f'{run_id}.log'
    cmd=[sys.executable,'-m','tools.agent_orchestrator','--root',str(root),'run-batch','--execute']
    if workers: cmd += ['--max-workers',str(workers)]
    if tasks: cmd += ['--tasks',*tasks]
    # CREATE_NEW_PROCESS_GROUP keeps the worker independent without the
    # Windows DETACHED_PROCESS handle invalidation seen in GUI-launched shells.
    flags = getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
    with log.open('a',encoding='utf-8') as out:
        proc=subprocess.Popen(cmd,cwd=str(root),stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,
                              creationflags=flags,close_fds=True)
    manifest['pid']=proc.pid; mpath.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    monitor_log = run_dir / f'{run_id}_supervisor.log'
    with monitor_log.open('a',encoding='utf-8') as out:
        subprocess.Popen([sys.executable,'-m','tools.agenthub_supervisor','--root',str(root),
                          '--run-id',run_id,'--supervise'], cwd=str(root), stdout=out,
                         stderr=subprocess.STDOUT, creationflags=flags, close_fds=True)
    return {'run_id':run_id,'pid':proc.pid,'manifest':str(mpath),'log':str(log),
            'supervisor_log':str(monitor_log),'status':'RUNNING'}

def supervise(root: Path, run_id: str, pid: int|None=None):
    run_dir=root/'.agent_hub_runtime'; mpath=run_dir/f'{run_id}.json'; log=run_dir/f'{run_id}.log'
    manifest=json.loads(mpath.read_text(encoding='utf-8')); started=time.time()
    while True:
        alive=False
        if manifest.get('pid'):
            try:
                os.kill(int(manifest['pid']),0); alive=True
            except (OSError, SystemError, ValueError): alive=False
        manifest['heartbeat_at']=_now(); manifest['log_bytes']=log.stat().st_size if log.exists() else 0
        if not alive:
            manifest['status']='FINISHED'; manifest['finished_at']=_now(); break
        mpath.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        time.sleep(5)
        if time.time()-started > 7*24*3600:
            manifest['status']='TIMEOUT'; manifest['finished_at']=_now(); break
    mpath.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    report=run_dir/f'{run_id}_report.md'
    report.write_text(f"# Agent Hub 执行报告\n\n- Run-ID: {run_id}\n- Status: {manifest['status']}\n- Started: {manifest.get('started_at')}\n- Finished: {manifest.get('finished_at')}\n- PID: {manifest.get('pid')}\n- Log: `{log}`\n- Manifest: `{mpath}`\n",encoding='utf-8')
    return report

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); p.add_argument('--run-id'); p.add_argument('--tasks',nargs='*'); p.add_argument('--workers',type=int); p.add_argument('--supervise',action='store_true'); a=p.parse_args(argv)
    if a.supervise: print(supervise(a.root,a.run_id)); return 0
    print(json.dumps(start(a.root,a.tasks,a.workers),ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
