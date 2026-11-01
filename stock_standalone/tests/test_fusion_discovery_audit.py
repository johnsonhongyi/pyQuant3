from types import SimpleNamespace

import numpy as np

from ats.fusion.anomaly import PATTERN_COUNTER_RECLAIM
from ats.fusion.discovery_audit import summarize_result
from ats.fusion.replay import day_bounds


def test_cache_wide_misses_include_opportunities_outside_candidate_pool():
    day, next_day = "2026-10-29", "2026-10-30"
    dtype = [("time", "i8"), ("close", "f8")]
    start, _ = day_bounds(day)
    following, _ = day_bounds(next_day)
    rows = [(start + 10 * 3600 - 240, 10.0), (start + 10 * 3600 - 60, 10.0),
            (start + 15 * 3600 - 240, 10.1), (start + 15 * 3600 - 60, 10.1),
            (following + 15 * 3600 - 240, 10.5), (following + 15 * 3600 - 60, 10.5)]
    cache = {code: np.array(rows, dtype=dtype) for code in ("000001", "000002")}
    replay = SimpleNamespace(cache=cache, _prev_close=lambda code, date: 10.0)
    result = SimpleNamespace(day=day, meta={"initial_candidate_codes": ["000001"]}, records=[
        {"code": "000001", "time": "10:01", "entry": 10.0,
         "patterns": [PATTERN_COUNTER_RECLAIM]}
    ])

    summary = summarize_result(replay, result, next_day)

    assert summary["miss_rate"] == 0.0
    assert summary["cache_universe_audit"]["opportunity_count"] == 2
    assert summary["cache_universe_audit"]["outside_candidate_opportunities"] == 1
    assert summary["cache_universe_audit"]["miss_rate"] == 0.5


def test_cache_wide_outcomes_remain_unknown_without_next_session():
    result = SimpleNamespace(day="2026-10-30", meta={}, records=[])
    summary = summarize_result(SimpleNamespace(cache={}), result, None)
    assert summary["cache_universe_audit"]["miss_rate"] is None
