"""Opt-in bounded stage timings; no disk I/O on the measured threads."""
import math
import os
import threading
import time
from collections import deque
from contextlib import contextmanager

ENABLED = os.environ.get("ATS_PERF", "0") == "1"
_samples = deque(maxlen=10000)
_lock = threading.Lock()


def record(stage, elapsed_ms, frame=None, **values):
    if not ENABLED:
        return
    attrs = getattr(frame, "attrs", {})
    sample = dict(stage=stage, elapsed_ms=elapsed_ms, mono_ns=time.monotonic_ns(),
                  session=attrs.get("sync_session"), version=attrs.get("source_version"), **values)
    with _lock:
        _samples.append(sample)


@contextmanager
def measure(stage, frame=None, **values):
    if not ENABLED:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        record(stage, (time.perf_counter() - started) * 1000, frame, **values)


def snapshot():
    with _lock:
        samples = list(_samples)
    grouped = {}
    for sample in samples:
        grouped.setdefault(sample["stage"], []).append(sample["elapsed_ms"])
    summary = {}
    for stage, values in grouped.items():
        values.sort()
        summary[stage] = dict(count=len(values), **{
            f"p{p}_ms": values[math.ceil(len(values) * p / 100) - 1] for p in (50, 95, 99)})
    return {"enabled": ENABLED, "capacity": _samples.maxlen, "summary": summary, "samples": samples}
