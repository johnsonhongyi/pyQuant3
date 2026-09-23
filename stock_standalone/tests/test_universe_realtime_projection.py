from types import SimpleNamespace

import pandas as pd

from ats.universe_manager import UniverseManager


class _Ledger:
    RADAR_DISPLAY_LIMIT = 30
    WATCH_DISPLAY_LIMIT = 15

    def __init__(self, entry):
        self.entry = entry
        self.entries = {entry.code: entry}

    def get_sorted_pool(self, tier, limit=None):
        rows = [self.entry] if tier == self.entry.tier else []
        return rows[:limit] if limit else rows


def _entry():
    return SimpleNamespace(
        code="688146",
        name="中船特气",
        tier="WATCH",
        latest_price=317.67,
        latest_pct=-9.8,
        latest_deviation=0.0,
        priority_score=200.0,
        first_seen_phase="CONTINUOUS",
        first_seen_ts=1_790_000_000.0,
        first_seen_pct=-9.8,
        peak_pct=-9.8,
        weak_since_ts=0.0,
        signal_tag="",
        state_history=[],
    )


def test_watch_pool_prefers_current_ipc_percent_over_stale_ledger_snapshot():
    manager = UniverseManager()
    ledger = _Ledger(_entry())
    df = pd.DataFrame(
        [{"code": "688146", "trade": 320.12, "percent": 0.53, "name": "中船特气"}]
    ).set_index("code")

    manager.sync_from_ledger(ledger, df_realtime=df)

    assert manager.watch_pool["688146"]["price"] == 320.12
    assert manager.watch_pool["688146"]["pct"] == 0.53
    _, watch_list, _ = manager.get_pools()
    row = next(item for item in watch_list if item[0] == "688146")
    assert row[2] == "320.12"
    assert row[3] == "+0.53%"
