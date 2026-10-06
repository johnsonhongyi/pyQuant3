"""Validate the selectable registry and persist the last selection."""
import json
from instock.job.run_statistics import database


def validate_selection(names, registry):
    available = [item['name'] for item in registry[2:]]
    if (not isinstance(names, list) or not names or
            any(not isinstance(name, str) or name not in available for name in names)):
        raise ValueError('请选择有效策略；放量上涨和均线多头请使用原刷新功能')
    return [name for name in available if name in names]


def selection(registry, names=None):
    with database() as db:
        db.execute('CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT)')
        if names is not None:
            names = [] if names == [] else validate_selection(names, registry)
            db.execute('INSERT INTO preferences VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       ('selected_strategies', json.dumps(names)))
            return names
        row = db.execute('SELECT value FROM preferences WHERE key=?', ('selected_strategies',)).fetchone()
        saved = json.loads(row[0]) if row else []
        return [item['name'] for item in registry[2:] if item['name'] in saved]
