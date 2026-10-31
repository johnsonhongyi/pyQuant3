from ats.fusion.shadow import FusionShadow
from ats.fusion.tracker import RaceTracker


def test_live_sources_merge_latest_state_and_exclude_future_days(tmp_path):
    older = RaceTracker()
    older_state = older.update(
        code="600000", ts=1_800_000_000.0, price=10.5, pct=2.0,
        tier=2, rar=70.0, anomaly=True, day="2026-10-30",
    )
    older_state.evidence.extend(
        {"ts": float(i), "kind": f"evidence-{i}", "tier": 2, "rar": 70.0, "src": "test"}
        for i in range(7)
    )
    older_state.prev_price = 10.25
    older_state.hi_ts = 1_800_000_050.0
    older_path = tmp_path / "tracker_state_live_strategy_100.json"
    assert older.save(str(older_path), metadata={
        "day": "2026-10-30", "counter_reclaim_first": {"600000": 1_800_000_040.0},
    }) == 1

    newer = RaceTracker()
    newer_state = newer.update(
        code="600000", ts=1_800_000_100.0, price=10.7, pct=3.0,
        tier=3, rar=75.0, anomaly=True, day="2026-10-30",
    )
    newer_state.prev_price = 10.6
    newer_state.hi_ts = 1_800_000_100.0
    newer_state.evidence.extend(
        {"ts": float(i), "kind": f"counter-reclaim-{i}", "tier": 3, "rar": 75.0, "src": "counter_reclaim"}
        for i in range(7)
    )
    newer_path = tmp_path / "tracker_state_live_strategy_200.json"
    assert newer.save(str(newer_path), metadata={
        "day": "2026-10-30",
        "counter_reclaim_first": {"600000": 1_800_000_030.0},
    }) == 1
    future = RaceTracker()
    future.update(
        code="000001", ts=1_800_000_200.0, price=12.0, pct=2.0,
        tier=2, rar=65.0, anomaly=True, day="2026-10-31",
    )
    future_path = tmp_path / "tracker_state_live_strategy_300.json"
    assert future.save(str(future_path), metadata={
        "day": "2026-10-31", "counter_reclaim_first": {"000001": 1_800_000_200.0},
    }) == 1

    shadow = FusionShadow.__new__(FusionShadow)
    shadow._log_dir = str(tmp_path)
    shadow.tracker = RaceTracker()
    shadow._counter_reclaim_first = {}
    assert shadow._tracks_source("live_strategy")
    assert shadow._tracks_source("counter_reclaim")
    assert shadow._tracks_source("vanguard_funnel")
    assert not shadow._tracks_source("replay")
    assert shadow._load_tracker_states("2026-10-30") == 1
    assert shadow._counter_reclaim_first == {"600000": 1_800_000_030.0}

    merged = shadow.tracker.get("600000")
    assert merged is not None
    assert merged.last_ts == newer_state.last_ts
    assert merged.prev_price == newer_state.prev_price
    assert merged.hi_ts == newer_state.hi_ts
    assert merged.evidence == newer_state.evidence
    assert any(item["src"] == "counter_reclaim" for item in merged.evidence)
    assert shadow.tracker.get("000001") is None
    assert not list(tmp_path.glob("tracker_state_live_strategy_*.tmp"))
