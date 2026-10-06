"""Small persistent run history, independent of browser polling."""
import contextlib
import datetime
import json
import logging
import os
import sqlite3
import time
import uuid


def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _path():
    return os.environ.get('INSTOCK_RUN_STATS_PATH',
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache', 'run_statistics.sqlite'))


@contextlib.contextmanager
def database():
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with sqlite3.connect(path, timeout=0.5) as db:
        db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, mode TEXT, created REAL, payload TEXT)')
        yield db


def save(run_id, mode, **fields):
    try:
        with database() as db:
            row = db.execute('SELECT payload FROM runs WHERE id=?', (run_id,)).fetchone()
            data = json.loads(row[0]) if row else {'id': run_id, 'mode': mode}
            data.update(fields)
            data.setdefault('started_at', data.get('job_started_at'))
            db.execute('INSERT INTO runs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (run_id, mode, time.time(), json.dumps(data, ensure_ascii=False)))
            db.execute('DELETE FROM runs WHERE mode=? AND id NOT IN (SELECT id FROM runs WHERE mode=? ORDER BY created DESC LIMIT 10)', (mode, mode))
            return data
    except (OSError, sqlite3.Error, ValueError) as exc:
        logging.error('Run statistics unavailable: %s', exc)
        return {'id': run_id, 'mode': mode, **fields}


def history():
    result = {'small': [], 'all': [], 'selected': []}
    try:
        with database() as db:
            rows = db.execute('SELECT mode,payload FROM runs ORDER BY created DESC').fetchall()
        for mode, payload in rows:
            data = json.loads(payload)
            if data.get('state') == 'running' and os.path.isdir('/proc') and data.get('pid'):
                if not os.path.exists('/proc/%s' % data['pid']):
                    data = save(data['id'], mode, state='interrupted', detected_at=now(),
                                error='Process disappeared before recording completion; inspect OOM/restart logs')
            if mode in result:
                result[mode].append(data)
    except (OSError, sqlite3.Error, ValueError) as exc:
        logging.error('Run history unavailable: %s', exc)
    return result


def resources():
    result = {}
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result.update(cpu_seconds=usage.ru_utime + usage.ru_stime,
                      peak_rss_mb=round(usage.ru_maxrss / 1024, 2),
                      major_faults=usage.ru_majflt, minor_faults=usage.ru_minflt)
        with open('/proc/self/io') as stream:
            result['io'] = {key: int(value) for key, value in
                            (line.strip().split(':') for line in stream)}
        result['load'] = list(os.getloadavg())
        for name, path in [('memory_current', '/sys/fs/cgroup/memory.current'),
                           ('memory_max', '/sys/fs/cgroup/memory.max'),
                           ('cpu_max', '/sys/fs/cgroup/cpu.max'),
                           ('cpu_stat', '/sys/fs/cgroup/cpu.stat'),
                           ('memory_events', '/sys/fs/cgroup/memory.events'),
                           ('io_pressure', '/proc/pressure/io'),
                           ('memory_pressure', '/proc/pressure/memory')]:
            try:
                with open(path) as stream:
                    result[name] = stream.read(2048).strip()
            except OSError:
                pass
    except (ImportError, OSError, ValueError):
        pass
    return result


class RunStatistics:
    def __init__(self, small, entrypoint='realtime', mode=None):
        self.mode = mode or ('small' if small else 'all')
        self.id = os.environ.get('INSTOCK_RUN_ID') or uuid.uuid4().hex
        self.started = time.perf_counter()
        self.before = resources()
        from JSONData.history_cache import cache_statistics
        self.cache_before = cache_statistics()
        self.stages = []
        self.config = {key: os.environ.get(key) for key in
                       ('INSTOCK_HISTORY_CACHE_MB', 'INSTOCK_CACHE_HOT_STOCKS',
                        'INSTOCK_PREFILTER_ACTIVE_ONLY', 'OPENBLAS_NUM_THREADS',
                        'OMP_NUM_THREADS', 'INSTOCK_HISTORY_CACHE_DIR', 'INSTOCK_PERF_VERSION')}
        self.config['entrypoint'] = entrypoint
        self.config['selected_strategies'] = os.environ.get('INSTOCK_SELECTED_STRATEGIES')
        save(self.id, self.mode, state='running', job_started_at=now(),
             pid=os.getpid(), config=self.config, resources_before=self.before)

    def stage(self, name, started, **details):
        self.stages.append(dict(name=name, seconds=round(time.perf_counter() - started, 3), **details))
        save(self.id, self.mode, stages=self.stages,
             duration_seconds=round(time.perf_counter() - self.started, 3))

    def finish(self, error=None, return_code=None):
        after = resources()
        from JSONData.history_cache import cache_statistics
        cache = cache_statistics()
        for key in ('memory_hits', 'shared_hits', 'source_reads', 'cache_errors', 'evictions', 'bypasses'):
            cache[key] -= self.cache_before.get(key, 0)
        cpu = max(0, after.get('cpu_seconds', 0) - self.before.get('cpu_seconds', 0))
        io = {key: value - self.before.get('io', {}).get(key, 0)
              for key, value in after.get('io', {}).items()}
        save(self.id, self.mode, state='failed' if error else 'success',
             finished_at=now(),
             duration_seconds=round(time.perf_counter() - self.started, 3),
             cpu_seconds=round(cpu, 3), peak_rss_mb=after.get('peak_rss_mb'),
             io_delta=io, resources_after=after, stages=self.stages,
             cache=cache, return_code=(1 if error else 0) if return_code is None else return_code,
             error=str(error)[:500] if error else None)
