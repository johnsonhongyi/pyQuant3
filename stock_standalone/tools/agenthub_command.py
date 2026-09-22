"""Explicit Agent Hub command gate.

This is the safe entry point for chat/UI integrations: planning is always
allowed, execution requires an explicit ``/confirm agenthub`` token.
"""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from tools.agenthub_supervisor import start as start_supervisor

CONFIRM = re.compile(r"(?:^|\s)(?:/confirm\s+agenthub|@agenthub\s+confirm)(?:\s|$)", re.I)
TRIGGER = re.compile(r"(?:^|\s)(?:@agenthub|/agenthub)(?:\s|$)", re.I)

def parse_request(text: str) -> dict:
    text = str(text or '').strip()
    return {
        'triggered': bool(TRIGGER.search(text)),
        'confirmed': bool(CONFIRM.search(text)),
        'mode': 'run' if (re.search(r"(?:^|[\s/])run(?:\s|$)", text, re.I) or re.search(r"@agenthub\s+confirm", text, re.I)) else 'plan',
        'text': text,
    }

def gate(root: Path, text: str, start_background: bool = False) -> dict:
    req = parse_request(text)
    state_dir = root / '.agent_hub' / 'events'
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    decision = 'EXECUTE_ALLOWED' if req['triggered'] and req['confirmed'] and req['mode'] == 'run' else 'PLAN_ONLY'
    result = {**req, 'decision': decision, 'timestamp': stamp}
    if decision == 'EXECUTE_ALLOWED' and start_background:
        result['background_run'] = start_supervisor(root)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    try:
        (state_dir / 'command_gate.json').write_text(payload, encoding='utf-8')
    except OSError:
        # Some managed workspaces expose .agent_hub as a protected junction.
        # Keep an auditable sidecar rather than failing open or losing the gate.
        (root / '.agent_hub_command_gate.json').write_text(payload, encoding='utf-8')
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description='Agent Hub explicit trigger/confirmation gate')
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('text', nargs='+')
    p.add_argument('--start-background', action='store_true')
    a=p.parse_args(argv); result=gate(a.root, ' '.join(a.text), a.start_background); print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['decision']=='EXECUTE_ALLOWED' else 10
if __name__ == '__main__': raise SystemExit(main())
