"""Bounded, process-shared normalized history cache; use tmpfs in Docker."""
import logging
import os
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from io import BytesIO

import numpy as np
import pandas as pd

_memory = OrderedDict()
_lock = threading.RLock()
_priority_codes = None


def set_priority_codes(codes):
    global _priority_codes
    _priority_codes = {str(code).split('.')[0].zfill(6) for code in codes}


def load_history(path, loader):
    stat = os.stat(path)
    version = '%s:%s:%s' % (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    key = os.path.abspath(path)
    budget = max(0, int(os.environ.get('INSTOCK_HISTORY_CACHE_MB', '32'))) * 1024 * 1024
    if not budget:
        return loader()
    digits = re.findall(r'\d{6}', os.path.basename(path))
    if _priority_codes is not None and (not digits or digits[-1] not in _priority_codes):
        return loader()
    with _lock:
        entry = _memory.get(key)
        if entry and entry[0] == version:
            _memory.move_to_end(key)
            return entry[1].copy(deep=True)
    frame = None
    cache_dir = os.environ.get('INSTOCK_HISTORY_CACHE_DIR')
    if cache_dir:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with sqlite3.connect(os.path.join(cache_dir, 'history-v2.sqlite'), timeout=0.2) as db:
                db.execute('CREATE TABLE IF NOT EXISTS cache (path TEXT PRIMARY KEY, version TEXT, payload BLOB, bytes INTEGER, touched REAL)')
                row = db.execute('SELECT payload FROM cache WHERE path=? AND version=?', (key, version)).fetchone()
                if row:
                    with np.load(BytesIO(row[0]), allow_pickle=False) as arrays:
                        frame = pd.DataFrame({name: arrays['c%s' % index]
                                              for index, name in enumerate(arrays['columns'])},
                                             index=arrays['index'])
                    db.execute('UPDATE cache SET touched=? WHERE path=?', (time.time(), key))
                else:
                    frame = loader()
                    buffer = BytesIO()
                    np.savez(buffer, columns=np.asarray(frame.columns, dtype='U'),
                             index=frame.index.to_numpy(),
                             **{'c%s' % index: frame[name].to_numpy()
                                for index, name in enumerate(frame.columns)})
                    payload = buffer.getvalue()
                    size = len(payload)
                    if size <= budget:
                        db.execute('DELETE FROM cache WHERE path=?', (key,))
                        total = db.execute('SELECT COALESCE(SUM(bytes),0) FROM cache').fetchone()[0]
                        for old_key, old_size in db.execute('SELECT path,bytes FROM cache ORDER BY touched').fetchall():
                            if total + size <= budget:
                                break
                            db.execute('DELETE FROM cache WHERE path=?', (old_key,))
                            total -= old_size
                        db.execute('INSERT INTO cache VALUES (?,?,?,?,?)', (key, version, payload, size, time.time()))
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            logging.debug('history shared cache unavailable: %s', exc)
            frame = None
    if frame is None:
        frame = loader()
    # Never retain data read across a concurrent TDX replacement/append.
    after = os.stat(path)
    if (after.st_mtime_ns, after.st_size, after.st_ino) != (stat.st_mtime_ns, stat.st_size, stat.st_ino):
        return loader()
    size = int(frame.memory_usage(index=True, deep=True).sum())
    with _lock:
        _memory.pop(key, None)
        total = sum(entry[2] for entry in _memory.values())
        while _memory and total + size > budget:
            total -= _memory.popitem(last=False)[1][2]
        if size <= budget:
            _memory[key] = (version, frame.copy(deep=True), size)
    return frame.copy(deep=True)
