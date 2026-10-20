"""Automatic research admission; independent of paper execution/risk policy."""
import json
import sqlite3
from datetime import datetime

DEFAULT = {"enabled": False, "interval_seconds": 900, "daily_max_runs": 3, "daily_token_budget": 300000}


def selection(db, now):
    """Fail closed for old installations, unavailable models, and legacy settings."""
    try:
        row = db.execute('SELECT body FROM automatic_research_policy WHERE id=1').fetchone()
        policy = {**DEFAULT, **(json.loads(row[0]) if row else {})}
        if policy['enabled'] is not True:
            return None, 'disabled'
        raw = db.execute('SELECT body FROM desktop_chat_config WHERE id=1').fetchone()
        runtime = json.loads(raw[0]) if raw else {}
        if not isinstance(runtime, dict):
            return None, 'runtime_unavailable'
        if runtime.get('provider') not in ('codex_desktop', 'antigravity_desktop'):
            return None, 'runtime_unavailable'
        node, workspace = runtime.get('node_id'), runtime.get('workspace_id')
        row = db.execute('SELECT status,heartbeat,detail FROM ai_desktop WHERE node_id=? AND workspace_id=?',
                         (node, workspace)).fetchone()
        if not row or row[0] not in ('ready', 'analyzing'):
            return None, 'model_unavailable'
        age = (now - datetime.fromisoformat(row[1].replace('Z', '+00:00'))).total_seconds()
        detail = json.loads(row[2])
        if not isinstance(detail, dict) or not isinstance(detail.get('models'), list):
            return None, 'model_unavailable'
        valid = any(isinstance(m, dict) and isinstance(m.get('efforts'), list)
                    and m.get('id') == runtime.get('model') and runtime.get('reasoning_effort') in m['efforts']
                    for m in detail['models'])
        if not 0 <= age <= 90 or 'strategy_research' not in detail.get('capabilities', []) or not valid:
            return None, 'model_unavailable'
        return {**policy, **{key: runtime[key] for key in
                ('provider', 'node_id', 'workspace_id', 'model', 'reasoning_effort')}}, 'ready'
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        return None, 'policy_unavailable'
