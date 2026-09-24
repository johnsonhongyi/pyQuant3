"""Detached Agent Hub batch supervisor for session-independent execution."""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

def discover_plan_specs(root: Path) -> dict[str, dict]:
    """Read the newest execution plan and preserve its task IDs, scopes and dependencies."""
    candidates = sorted((root/'docs').glob('*EXECUTION*PLAN*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return {}
    try:
        lines = candidates[0].read_text(encoding='utf-8').splitlines()
    except OSError:
        return {}
    specs: dict[str, dict] = {}
    for line in lines:
        cells = [part.strip() for part in line.strip().strip('|').split('|')]
        if len(cells) < 3:
            continue
        match = re.match(r'\*\*(G\d{2})\s+(.+?)\*\*\s*(.*?)\s*$', cells[0], re.I)
        if not match:
            continue
        task_id = match.group(1).upper()
        title_and_priority = match.group(2)
        title = re.sub(r'[\uFF0C,]\s*P\d\s*$', '', title_and_priority).strip()
        dep_text = match.group(3).strip().lstrip('\uFF1B;').strip()
        deps: list[str] = []
        for first, last in re.findall(r'(G\d{2})\s*[\u2013-]\s*(G\d{2})', dep_text, re.I):
            deps.extend(f'G{n:02d}' for n in range(int(first[1:]), int(last[1:]) + 1))
        dep_text = re.sub(r'G\d{2}\s*[\u2013-]\s*G\d{2}', ' ', dep_text, flags=re.I)
        deps.extend(x.upper() for x in re.findall(r'G\d{2}', dep_text, re.I))
        deps = list(dict.fromkeys(deps))
        files = re.findall(r'`([^`]+)`', cells[1])
        requirement = cells[2]
        if task_id not in {'G00', 'G12', 'G13', 'G14', 'G15'}:
            files.append(f'tests/ats_closed_loop/test_{task_id.lower()}.py')
        priority_match = re.search(r'\b(P[01])\b', title_and_priority)
        specs[task_id] = {'title': title, 'priority': priority_match.group(1) if priority_match else 'P1', 'deps': deps, 'files': list(dict.fromkeys(files)), 'requirement': requirement}
    if specs:
        return specs
    legacy = {}
    content = '\n'.join(lines)
    for match in re.finditer(r'(?m)^##.*?Task\s+(\d{3})(?:/(\d{3}))?\s*[:\uFF1A]?\s*(.*?)\s*$', content):
        task_id, second_id, title = match.group(1), match.group(2), match.group(3)
        legacy[task_id] = {'title': title, 'priority': 'P1', 'deps': [], 'files': ['ats/', 'tests/'], 'requirement': title}
        if second_id:
            legacy[second_id] = legacy[task_id]
    return legacy


def discover_plan_tasks(root: Path) -> dict[str, str]:
    return {task_id: re.sub(r'[^a-z0-9]+', '_', spec['title'].lower()).strip('_')[:48] or task_id.lower() for task_id, spec in discover_plan_specs(root).items()}


def ensure_plan_tasks(root: Path, task_ids=None) -> dict:
    """Register exact task cards from the newest execution plan."""
    specs = discover_plan_specs(root)
    ids = task_ids or list(specs)
    inbox = root/'.agent_hub'/'inbox'; created=[]; existing=[]; errors=[]
    for tid in ids:
        spec = specs.get(tid)
        if not spec:
            errors.append(f'{tid}: task ID is absent from the newest execution plan')
            continue
        slug = re.sub(r'[^a-z0-9]+', '_', spec['title'].lower()).strip('_')[:48] or tid.lower()
        path = inbox/f'{tid}_{slug}.md'
        prior = list(inbox.glob(f'{tid}_*.md'))
        if prior:
            card_path = prior[0]
            prior_text = card_path.read_text(encoding='utf-8')
            if prior_text.startswith('# Task\n\nImplement planned work for '):
                prior_text = prior_text.replace('# Task\n\n', f'# {tid}: {spec["title"]}\n\n## Task\n\n', 1)
                with card_path.open('w', encoding='utf-8', newline='\n') as handle:
                    handle.write(prior_text)
            existing.append(tid); continue
        tests = [x for x in spec['files'] if x.startswith('tests/')]
        verification = f'python -m pytest {tests[0]} -q' if tests else 'python -m compileall -q tools'
        profile = 'P1_DOCS_SAFE' if tid == 'G00' else ('P0_READONLY' if tid == 'G15' else ('P4_RELEASE_GATE' if tid == 'G14' else 'P3_CODE_MEDIUM'))
        risk = 'LOW' if tid in {'G00', 'G15'} else ('HIGH' if tid == 'G14' else 'MEDIUM')
        deps = ' '.join(spec['deps']) or 'none'
        allowed = '\n'.join(f'- `{item}`' for item in spec['files']) or '- `docs/ats_closed_loop/`'
        card = f"""# Task

Implement planned work for {tid}: {spec['title']}.

## Metadata

- Task-ID: {tid}
- Owner: unassigned
- Priority: {spec['priority']}
- Risk: {risk}
- Permission-Profile: {profile}
- Depends-On: {deps}
- Created-By: agenthub
- Created-At: {time.strftime('%Y-%m-%d')}

## Context

Follow `docs/ATS_SIGNAL_T1_PAPER_CLOSED_LOOP_EXECUTION_PLAN_2026-09-24.md`, including its interface contracts, file ownership, PAPER-only boundary, and read-only production-data rule. {spec['requirement']}

## Files Allowed

{allowed}

## Files Forbidden

- `trade_gateway.py`
- Broker APIs, credentials, production database writes, and real-trading switches

## Requirements

- {spec['requirement']}
- Record verification evidence, risks, and rollback point; do not modify files outside this task's allowlist.

## Definition of Done

- [ ] Planned deliverable is complete and interfaces remain compatible
- [ ] Verification result is recorded
- [ ] No out-of-scope files were modified
- [ ] Risks, rollback point, and evidence are recorded

## Verification

```powershell
{verification}
```

## Rollback

Revert only changes made by this task. Preserve production data and other task artifacts. Stop and report account discrepancies or any real-trading risk.

## Output Contract

Write walkthrough, verification result, changed-file list, and `agent_report.json` under `.agent_hub/artifacts/{tid}/`.
"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', encoding='utf-8', newline='\n') as handle:
                handle.write(card)
            created.append(tid)
        except OSError as exc:
            errors.append(f'{tid}: {exc}')
    return {'created': created, 'existing': existing, 'errors': errors, 'registered': not errors}

def _now(): return datetime.now(timezone.utc).isoformat()
def start(root: Path, tasks=None, workers=None) -> dict:
    registration = ensure_plan_tasks(root, tasks)
    if registration['errors']:
        return {'status':'BLOCKED_REGISTRATION','registration':registration,
                'message':'无法写入 Agent Hub inbox，未启动任何 Worker'}
    # Never fall back to an unrelated legacy inbox: execute exactly the
    # dynamically discovered plan tasks that were just registered/validated.
    selected_tasks = list(tasks or discover_plan_tasks(root))
    run_dir = root / '.agent_hub_runtime'; run_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = f'run_{stamp}'
    manifest = {'run_id':run_id,'started_at':_now(),'status':'RUNNING','tasks':selected_tasks,'pid':None}
    mpath = run_dir / f'{run_id}.json'; mpath.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    log = run_dir / f'{run_id}.log'
    cmd=[sys.executable,'-m','tools.agent_orchestrator','--root',str(root),'run-batch','--execute']
    if workers: cmd += ['--max-workers',str(workers)]
    if selected_tasks: cmd += ['--tasks',*selected_tasks]
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
