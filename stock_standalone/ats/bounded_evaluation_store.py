"""Bound diagnostic checkpoints and coalesce noncritical evaluation writes."""
import copy
import gzip
import json
import os
import threading
import time
from collections import OrderedDict
from ats.archive_policy import ARCHIVE_INTERVAL, archive_window

CHECKPOINT_LIMIT = 64
WRITE_INTERVAL = ARCHIVE_INTERVAL


def compact_checkpoints(evaluation):
    removed = 0
    for item in evaluation.get("candidates", {}).values():
        points = item.get("checkpoints", [])
        if not points:
            continue
        evidence_times = set()
        for event in item.get('events', []):
            evidence_times.add(event.get('observed_at'))
            evidence_times.add((event.get('evidence') or {}).get('first_observed_at'))
        anchors, critical, daily_last, seen = set(), set(), {}, set()
        for index, point in enumerate(points):
            stamp = str(point.get('observed_at', ''))
            day = stamp[:10]
            if day not in daily_last:
                anchors.add(index)
            daily_last[day] = index
            if stamp in evidence_times or point.get('kind'):
                critical.add(index)
            for proof in ('sustained_high', 'verified_vwap_rise'):
                if point.get(proof) and (day, proof) not in seen:
                    anchors.add(index)
                    seen.add((day, proof))
        anchors.update(daily_last.values())
        # Evidence referenced by an event must survive; never fill the remainder with ticks.
        anchors = critical | set(sorted(anchors - critical)[-max(0, CHECKPOINT_LIMIT - len(critical)):]
                                 if len(critical) < CHECKPOINT_LIMIT else [])
        kept = [points[index] for index in sorted(anchors)]
        if len(kept) == len(points):
            continue
        summary = item.setdefault("checkpoint_summary", {})
        summary["compacted_count"] = int(summary.get("compacted_count", 0)) + len(points) - len(kept)
        summary["first_observed_at"] = summary.get("first_observed_at") or points[0].get("observed_at")
        summary["last_observed_at"] = points[-1].get("observed_at")
        summary["has_vwap_observation"] = (bool(summary.get("has_vwap_observation"))
                                           or any(p.get("vwap") is not None for p in points))
        highs = [float(p["high"]) for p in points if isinstance(p.get("high"), (int, float))]
        if highs:
            previous_high = summary.get('max_high')
            summary["max_high"] = max(highs + ([float(previous_high)] if isinstance(previous_high, (int, float)) else []))
        item["checkpoints"] = kept
        removed += len(points) - len(kept)
    return removed


def _version(path):
    try:
        actual = path + '.gz' if os.path.exists(path + '.gz') else path
        stat = os.stat(actual)
        return actual, stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def merge_evaluations(previous, value):
    """Merge concurrent archive batches without losing events or delivery receipts."""
    if not isinstance(previous, dict) or previous.get('config_hash') != value.get('config_hash'):
        return value
    for code, older in previous.get('candidates', {}).items():
        if code not in value.setdefault('candidates', {}):
            value['candidates'][code] = copy.deepcopy(older)
            continue
        current = value['candidates'][code]
        old_points, new_points = older.get('checkpoints', []), current.get('checkpoints', [])
        if old_points and (not new_points or str(old_points[-1].get('observed_at')) > str(new_points[-1].get('observed_at'))):
            current['candidate'] = copy.deepcopy(older.get('candidate', {}))
        points = {str(p.get('observed_at', '')): p for p in old_points + new_points}
        current['checkpoints'] = [points[key] for key in sorted(points)]
        events = {}
        for event in older.get('events', []) + current.get('events', []):
            key = event.get('event_id') or json.dumps({k: v for k, v in event.items() if k != 'delivered'}, sort_keys=True)
            prior = events.get(key, {})
            events[key] = dict(event, delivered=True) if prior.get('delivered') or event.get('delivered') else event
        current['events'] = list(events.values())
        old_summary = older.get('checkpoint_summary', {})
        summary = current.setdefault('checkpoint_summary', {})
        summary['has_vwap_observation'] = bool(summary.get('has_vwap_observation') or old_summary.get('has_vwap_observation'))
        summary['compacted_count'] = max(summary.get('compacted_count', 0), old_summary.get('compacted_count', 0))
        if old_summary.get('max_high') is not None:
            summary['max_high'] = max(summary.get('max_high') or old_summary['max_high'], old_summary['max_high'])
    compact_checkpoints(value)
    return value


class EvaluationStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._cache = OrderedDict()
        self._started = False
        self._flush_lock = threading.Lock()

    @staticmethod
    def _latest_write_ts(path):
        try:
            actual = _version(path)
            stamp = actual[1] / 1e9 if actual else 0
            if os.path.isdir(path + '.parts'):
                with os.scandir(path + '.parts') as files:
                    latest = max((item.path for item in files if item.name.endswith('.jsonl.gz')), default=None)
                if latest:
                    stamp = max(stamp, os.stat(latest).st_mtime)
            return stamp
        except OSError:
            return 0

    @classmethod
    def _saved_close_day(cls, path):
        from datetime import datetime, timedelta, timezone
        try:
            stamp = cls._latest_write_ts(path)
            if not stamp:
                return None
            saved = datetime.fromtimestamp(stamp, timezone(timedelta(hours=8)))
            return saved.strftime('%Y-%m-%d') if saved.hour >= 15 else None
        except OSError:
            return None

    def _remember(self, path, entry):
        if path not in self._cache and len(self._cache) >= 128:
            clean = next((key for key, value in self._cache.items() if not value['dirty']), None)
            if clean is None:
                clean = None  # Pending archives stay in memory until the permitted checkpoint.
            if clean is not None:
                del self._cache[clean]
        self._cache[path] = entry
        self._cache.move_to_end(path)

    def read(self, path, default):
        path = os.path.abspath(path)
        with self._lock:
            entry = self._cache.get(path)
            if entry and (entry.get('dirty') or time.monotonic() < entry.get('next_check', 0)):
                self._cache.move_to_end(path)
                return copy.deepcopy(default if entry.get('missing') else entry['value'])
            version = _version(path)
            if entry and entry["version"] == version:
                entry['next_check'] = time.monotonic() + WRITE_INTERVAL
                return copy.deepcopy(default if entry.get('missing') else entry['value'])
            try:
                actual = version[0] if version else path
                opener = gzip.open if actual.endswith('.gz') else open
                with opener(actual, "rt", encoding="utf-8") as stream:
                    value = json.load(stream)
                is_eval = os.path.basename(path).startswith('next_day_anomaly_eval_')
                compacted = compact_checkpoints(value) if is_eval else 0
            except (OSError, ValueError, TypeError):
                self._remember(path, dict(version=version, value=None, missing=True,
                    last_write=time.monotonic(), dirty=False, close_date=None,
                    next_check=time.monotonic() + WRITE_INTERVAL))
                return copy.deepcopy(default)
            entry = dict(version=version, value=value,
                last_write=time.monotonic(), dirty=bool(compacted), close_date=self._saved_close_day(path),
                next_check=time.monotonic() + WRITE_INTERVAL)
            if compacted:
                # Queue old tick removal through the existing timed archive gate.
                from next_day_anomaly_watch import _persist_archive
                entry['writer'] = _persist_archive
            self._remember(path, entry)
            if compacted and not self._started:
                self._started = True
                threading.Thread(target=self._flush_loop, daemon=True, name='ATS-ArchiveCache').start()
            return copy.deepcopy(value)

    def peek(self, path, default=None):
        """Read only this process's memory; safe for GUI callers."""
        with self._lock:
            entry = self._cache.get(os.path.abspath(path))
            return copy.deepcopy(default if not entry or entry.get('missing') else entry['value'])

    def put(self, path, value, writer, on_commit=None):
        path = os.path.abspath(path)
        with self._lock:
            if os.path.basename(path).startswith('next_day_anomaly_eval_'):
                compact_checkpoints(value)
            entry = self._cache.get(path)
            if entry is None:
                entry = dict(version=_version(path), last_write=time.monotonic(), close_date=self._saved_close_day(path))
            if entry.pop('missing', False) or entry.get('value') != value:
                entry.update(value=copy.deepcopy(value), dirty=True)
            entry['writer'] = writer
            if on_commit is not None:
                entry['on_commit'] = on_commit
            self._remember(path, entry)
            if not self._started:
                self._started = True
                threading.Thread(target=self._flush_loop, daemon=True, name='ATS-ArchiveCache').start()
            already_saved = (on_commit is not None and not entry.get('dirty')
                             and entry.get('version') is not None)
        if already_saved:
            on_commit(copy.deepcopy(value))

    def append(self, path, value, writer, coalesce_key=None):
        path = os.path.abspath(path)
        with self._lock:
            entry = self._cache.get(path)
            if entry is None:
                entry = dict(version=_version(path), value=[], last_write=time.monotonic(), close_date=self._saved_close_day(path))
            records = entry.setdefault('value', [])
            indices = entry.setdefault('coalesced', {})
            if coalesce_key is not None and coalesce_key in indices:
                records[indices[coalesce_key]] = copy.deepcopy(value)
            else:
                if coalesce_key is not None:
                    indices[coalesce_key] = len(records)
                records.append(copy.deepcopy(value))
            entry.update(dirty=True, writer=writer, kind='append')
            self._remember(path, entry)
            if not self._started:
                self._started = True
                threading.Thread(target=self._flush_loop, daemon=True, name='ATS-ArchiveCache').start()

    def buffered_records(self, path):
        with self._lock:
            return copy.deepcopy(self._cache.get(os.path.abspath(path), {}).get('value', []))

    def _flush_loop(self):
        while True:
            time.sleep(30)
            self.flush()

    def flush(self):
        if not self._flush_lock.acquire(blocking=False):
            return
        try:
            self._flush_pending()
        finally:
            self._flush_lock.release()

    def _flush_pending(self):
        for path, value in self.pending():
            if archive_window()[0] is None:
                break
            with self._lock:
                entry = self._cache.get(path, {})
                writer = entry.get('writer')
                on_commit = entry.get('on_commit')
            if writer is None:
                continue
            try:
                from ats.persistence_lock import directory_write_lock
                with directory_write_lock(os.path.join(os.path.dirname(path), '.archive-checkpoint')):
                    window, day = archive_window()
                    if window is None:
                        break
                    if window == 'close' and self._saved_close_day(path) == day:
                        with self._lock:
                            self._cache[path]['close_date'] = day
                        continue
                    if window == 'market':
                        stamp = self._latest_write_ts(path)
                        elapsed = max(0.0, time.time() - stamp)
                        if stamp and elapsed < WRITE_INTERVAL:
                            with self._lock:
                                self._cache[path]['last_write'] = time.monotonic() - elapsed
                            continue
                    original = copy.deepcopy(value) if os.path.basename(path).startswith('next_day_anomaly_eval_') else None
                    written = writer(path, value)
                    self.committed(path, value, written is not False, original=original)
                if on_commit is not None and written is not False:
                    on_commit(value)
            except Exception:
                import logging
                logging.getLogger('ATS.ArchiveCache').exception('Archive deferred: %s', path)

    def committed(self, path, value, written=True, original=None):
        path = os.path.abspath(path)
        with self._lock:
            entry = self._cache.get(path)
            if entry is not None:
                if entry.get('kind') == 'append':
                    records = entry['value']
                    kept = [index for index, record in enumerate(records)
                            if index >= len(value) or record != value[index]]
                    remap = {old: new for new, old in enumerate(kept)}
                    entry['coalesced'] = {key: remap[index] for key, index in entry.get('coalesced', {}).items()
                                          if index in remap}
                    entry['value'] = [records[index] for index in kept]
                    value = []
                elif original is not None:
                    if entry['value'] == original:
                        entry['value'] = copy.deepcopy(value)
                    else:
                        merge_evaluations(value, entry['value'])
                entry.update(version=_version(path), last_write=time.monotonic(), next_check=time.monotonic() + WRITE_INTERVAL,
                             dirty=entry['value'] != value)
                window, day = archive_window()
                if window == 'close' and written:
                    entry['close_date'] = day

    def pending(self):
        with self._lock:
            pending = []
            window, day = archive_window()
            if window is None:
                return pending
            for path, entry in self._cache.items():
                due = (window == 'market' and time.monotonic() - entry['last_write'] >= WRITE_INTERVAL
                       or window == 'close' and entry.get('close_date') != day)
                if entry.get("dirty") and due:
                    pending.append((path, copy.deepcopy(entry["value"])))
            return pending

    def paths(self, pattern):
        import fnmatch
        import glob
        paths = {os.path.abspath(p[:-3] if p.endswith('.gz') else p)
                 for p in glob.glob(pattern) + glob.glob(pattern + '.gz')}
        with self._lock:
            paths.update(p for p in self._cache if fnmatch.fnmatch(p, os.path.abspath(pattern)))
        return sorted(paths)


evaluation_store = EvaluationStore()

import atexit
atexit.register(evaluation_store.flush)
