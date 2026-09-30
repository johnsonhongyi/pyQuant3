"""Bound diagnostic checkpoints and coalesce noncritical evaluation writes."""
import copy
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict

CHECKPOINT_LIMIT = 64
WRITE_INTERVAL = 30.0


def compact_checkpoints(evaluation):
    removed = 0
    for item in evaluation.get("candidates", {}).values():
        points = item.get("checkpoints", [])
        if len(points) <= CHECKPOINT_LIMIT:
            continue
        daily_last = {}
        for index, point in enumerate(points):
            daily_last[str(point.get("observed_at", ""))[:10]] = index
        anchors = {0, len(points) - 2, len(points) - 1}
        anchors.update(sorted(daily_last.values())[-(CHECKPOINT_LIMIT - 3):])
        for index in range(len(points) - 1, -1, -1):
            if len(anchors) >= CHECKPOINT_LIMIT:
                break
            anchors.add(index)
        kept = [points[index] for index in sorted(anchors)]
        summary = item.setdefault("checkpoint_summary", {})
        summary["compacted_count"] = int(summary.get("compacted_count", 0)) + len(points) - len(kept)
        summary["first_observed_at"] = summary.get("first_observed_at") or points[0].get("observed_at")
        summary["last_observed_at"] = points[-1].get("observed_at")
        highs = [float(p["high"]) for p in points if isinstance(p.get("high"), (int, float))]
        if highs:
            summary["max_high"] = max(highs + [float(summary.get("max_high", highs[0]))])
        item["checkpoints"] = kept
        removed += len(points) - len(kept)
    return removed


def _version(path):
    try:
        stat = os.stat(path)
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _critical_digest(value):
    # Confirmation, delivery receipts, phases and outcomes remain immediately durable.
    projection = {k: v for k, v in value.items() if k not in {"candidates", "updated_at"}}
    projection["candidates"] = {
        code: {k: v for k, v in item.items() if k not in {"checkpoints", "checkpoint_summary"}}
        for code, item in value.get("candidates", {}).items()}
    return hashlib.sha256(json.dumps(projection, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).digest()


class EvaluationStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._cache = OrderedDict()

    def read(self, path, default):
        path = os.path.abspath(path)
        with self._lock:
            entry = self._cache.get(path)
            version = _version(path)
            if entry and entry["version"] == version:
                self._cache.move_to_end(path)
                return copy.deepcopy(entry["value"])
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    value = json.load(stream)
                if not isinstance(value, dict) or not isinstance(value.get("candidates", {}), dict):
                    return default
                removed = compact_checkpoints(value)
            except (OSError, ValueError, TypeError):
                return default
            self._cache[path] = dict(version=version, value=value,
                critical=_critical_digest(value), last_write=0.0, dirty=bool(removed))
            # Evict only clean entries; dirty entries are small and must survive until flushed.
            for key in list(self._cache):
                if len(self._cache) <= 8:
                    break
                if not self._cache[key]["dirty"]:
                    del self._cache[key]
            return copy.deepcopy(value)

    def should_write(self, path, value):
        path = os.path.abspath(path)
        with self._lock:
            compact_checkpoints(value)
            critical = _critical_digest(value)
            entry = self._cache.get(path)
            if (entry and entry["version"] == _version(path)
                    and entry["critical"] == critical
                    and time.monotonic() - entry["last_write"] < WRITE_INTERVAL):
                entry["value"] = copy.deepcopy(value)
                entry["dirty"] = True
                return False
            return True

    def committed(self, path, value):
        with self._lock:
            self._cache[os.path.abspath(path)] = dict(version=_version(path),
                value=copy.deepcopy(value), critical=_critical_digest(value),
                last_write=time.monotonic(), dirty=False)

    def pending(self):
        with self._lock:
            pending = []
            for path, entry in self._cache.items():
                if entry["dirty"] and entry["version"] == _version(path):
                    entry["last_write"] = 0.0
                    pending.append((path, copy.deepcopy(entry["value"])))
            return pending


evaluation_store = EvaluationStore()
