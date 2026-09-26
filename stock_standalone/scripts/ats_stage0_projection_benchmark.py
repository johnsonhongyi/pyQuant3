"""Synthetic Stage 0 benchmark for repeated full-table lookup vs one projection."""

import json
import platform
import statistics
import os
import sys
import time

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from next_day_anomaly_watch import (
    _FEATURES,
    _build_market_projection,
    _candidate_row_lookup,
    _row_dict,
    _source_with_code,
)


def _make_frame(row_count, filler_count=64):
    codes = ["%06d" % (i + 1) for i in range(row_count)]
    payload = {
        "code": codes,
        "name": ["stock-%d" % i for i in range(row_count)],
        "high": [10.0 + i % 100 / 100 for i in range(row_count)],
        "trade": [9.0 + i % 100 / 100 for i in range(row_count)],
        "close": [9.0 + i % 100 / 100 for i in range(row_count)],
        "percent": [i % 100 / 10 for i in range(row_count)],
        "dff": [i % 50 / 10 for i in range(row_count)],
        "category": ["sector-%d" % (i % 30) for i in range(row_count)],
        "vol": [1000 + i for i in range(row_count)],
        "amount": [10000.0 + i for i in range(row_count)],
    }
    for field in _FEATURES:
        payload.setdefault(field, [float(i % 17) for i in range(row_count)])
    for col in range(filler_count):
        payload["unused_%02d" % col] = [i + col for i in range(row_count)]
    return pd.DataFrame(payload)


def _legacy_lookup(frame, codes):
    source = _source_with_code(frame)
    result = {}
    for code in codes:
        normalized = source["code"].astype(str).str.strip().str.zfill(6)
        matches = source.loc[normalized == code].copy()
        if not matches.empty:
            result[code] = _row_dict(matches.iloc[-1].to_dict())
    return result


def _projected_lookup(frame, codes):
    projection = _build_market_projection(frame, None, candidate_codes=codes)
    candidates = [{"code": code} for code in codes]
    return _candidate_row_lookup(projection, candidates)


def _percentile(samples, percentile):
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int(round((percentile / 100) * (len(ordered) - 1)))))
    return round(ordered[index], 3)


def _measure(fn, repeats=7):
    samples = []
    for _ in range(repeats + 1):
        started = time.perf_counter()
        fn()
        elapsed_ms = (time.perf_counter() - started) * 1000
        samples.append(elapsed_ms)
    samples = samples[1:]  # one warm-up, then measured samples
    return {
        "samples": len(samples),
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": _percentile(samples, 95),
        "p99_ms": _percentile(samples, 99),
        "max_ms": round(max(samples), 3),
    }


def run():
    report = {
        "benchmark": "ATS one-pass market projection vs repeated full-table candidate lookup",
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "warmup": 1,
        "measured_repeats": 7,
        "rows": [],
    }
    for row_count in (1000, 5000, 10000):
        frame = _make_frame(row_count)
        for candidate_count in (10, 30):
            codes = ["%06d" % (i + 1) for i in range(candidate_count)]
            legacy = _legacy_lookup(frame, codes)
            projected = _projected_lookup(frame, codes)
            assert set(legacy) == set(projected) == set(codes)
            assert all(legacy[code].get("trade") == projected[code].get("trade") for code in codes)
            legacy_ms = _measure(lambda: _legacy_lookup(frame, codes))
            projected_ms = _measure(lambda: _projected_lookup(frame, codes))
            report["rows"].append({
                "market_rows": row_count,
                "candidate_count": candidate_count,
                "legacy_repeated_scan": legacy_ms,
                "one_pass_projection": projected_ms,
                "observed_speedup_x": round(legacy_ms["p50_ms"] / max(projected_ms["p50_ms"], 0.001), 2),
            })
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
