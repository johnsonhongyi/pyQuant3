# -*- coding: utf-8 -*-
import gzip
import json
import os
import time

import numpy as np
import pytest

from ats.fusion.history_events import HistoricalEvents
from ats.fusion.iteration import run_iterations
from ats.fusion.replay import DayReplay, ReplayConfig, ReplayResult


def _ts(day, hm):
    return time.mktime(time.strptime(day + " " + hm, "%Y-%m-%d %H:%M"))


def test_history_is_visible_only_after_observation_and_excludes_backfill(tmp_path):
    day = "2026-10-29"
    folder = tmp_path / "logs" / "fusion_shadow"
    folder.mkdir(parents=True)
    rows = [
        {"ts": _ts(day, "10:00"), "code": "000568", "writer_pid": 10,
         "fusion": {"tier": 2, "rar": 70}},
        {"ts": _ts(day, "09:35"), "code": "002281", "writer_pid": 0,
         "writer_exe": "REPLAY_BACKFILL", "fusion": {"tier": 4}},
        {"ts": _ts(day, "09:36"), "code": "002282", "writer_pid": 12,
         "source": "backfill", "fusion": {"tier": 4}},
    ]
    (folder / (day + ".jsonl")).write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
    events = HistoricalEvents(str(tmp_path), day)
    assert events.advance(_ts(day, "09:59")) == []
    assert events.advance(_ts(day, "10:00"))[0][0] == "000568"
    assert events.stats["excluded_backfill"] == 2


def test_ledger_snapshot_cannot_be_used_before_snapshot_time(tmp_path):
    day = "2026-10-29"
    folder = tmp_path / "logs" / "signal_snapshots"
    folder.mkdir(parents=True)
    snapshot = {"date": day, "timestamp": day + "T14:00:00",
                "entries": {"000568": {"tier": "WATCH", "first_seen_ts": _ts(day, "09:40")}}}
    (folder / "signal_ledger_latest.json").write_text(json.dumps(snapshot), encoding="utf-8")
    events = HistoricalEvents(str(tmp_path), day)
    assert events.advance(_ts(day, "13:59")) == []
    assert events.advance(_ts(day, "14:00"))[0][1] == "ledger"


def test_replay_adds_historical_candidate_only_after_event(tmp_path, monkeypatch):
    day = "2026-10-27"
    folder = tmp_path / "logs" / "fusion_shadow"
    folder.mkdir(parents=True)
    row = {"ts": _ts(day, "10:00"), "code": "000002", "writer_pid": 10,
           "fusion": {"tier": 2, "rar": 70}}
    (folder / (day + ".jsonl")).write_text(json.dumps(row), encoding="utf-8")
    dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
             ("close", "f8"), ("volume", "f8"), ("cum_vol_start", "f8")]
    def bars(volume, falling=False):
        rows = []
        for d in ("2026-10-26", day):
            for i in range(40):
                p = 10.0 - i * 0.005 if falling and d == day else 10.0 + i * 0.002
                rows.append((_ts(d, "09:30") + i * 180, p, p * 1.001, p * 0.999, p, volume, 0))
        return np.array(rows, dtype=dtype)
    monkeypatch.setattr("ats.fusion.replay.get_daily_context", lambda: type("Ctx", (), {"ok": False})())
    monkeypatch.setattr("ats.fusion.replay.MarketHistory", lambda *args: type(
        "Hist", (), {"days": {str(i): i for i in range(5)}, "context_for": lambda *a, **k: None})())
    cfg = ReplayConfig(top_n=1, structure_seed_n=0, history_root=str(tmp_path),
                       track=False, cuts_mode="fixed", record_tier_min=4)
    result = DayReplay(cache={"000001": bars(2000), "000002": bars(1000, True)}, config=cfg).run_day(day)
    target = [r for r in result.records if r["code"] == "000002"]
    assert target and min(r["ts"] for r in target) >= row["ts"]
    assert target[0]["production_history"]["gradient"]["observed_ts"] == row["ts"]


def test_independent_replay_never_loads_production_events(tmp_path, monkeypatch):
    day = "2026-10-27"
    dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
             ("close", "f8"), ("volume", "f8"), ("cum_vol_start", "f8")]
    bars = np.array([(_ts(d, "09:30") + i * 180, 10, 10.1, 9.9, 10, 1000, 0)
                     for d in ("2026-10-26", day) for i in range(8)], dtype=dtype)
    monkeypatch.setattr("ats.fusion.history_events.HistoricalEvents", lambda *args: (_ for _ in ()).throw(AssertionError("生产事件不应被读取")))
    monkeypatch.setattr("ats.fusion.replay.get_daily_context", lambda: type("Ctx", (), {"ok": False})())
    monkeypatch.setattr("ats.fusion.replay.MarketHistory", lambda *args: type(
        "Hist", (), {"days": {str(i): i for i in range(5)}, "context_for": lambda *a, **k: None})())
    cfg = ReplayConfig(top_n=1, structure_seed_n=0, track=False, cuts_mode="fixed",
                       use_production_history=False, history_root=str(tmp_path))
    result = DayReplay(cache={"000001": bars}, config=cfg).run_day(day)
    assert result.meta["production_history"] == {"enabled": False}


def test_iteration_rejects_production_history_input(tmp_path):
    replay = type("Replay", (), {"cache": {"000001": [1]},
                  "cfg": ReplayConfig(persist_context=False, use_production_history=True)})()
    with pytest.raises(ValueError, match="禁用生产历史"):
        run_iterations(replay=replay, history_root=str(tmp_path), output_root=str(tmp_path / "runs"))
    assert not (tmp_path / "runs").exists()


def test_iteration_persists_isolated_and_carries_prior_observation(tmp_path, monkeypatch):
    days = ["2026-10-26", "2026-10-27", "2026-10-28"]
    from ats.fusion.liquidity_history import DailyLiquidityHistory
    import pandas as pd
    feature_path = tmp_path / "features.h5"
    pd.DataFrame([{"code": "000568", "date": "2026-10-27", "ratio": 5.5, "vol_ratio": 1.3},
                  {"code": "000568", "date": "2026-10-28", "ratio": 99.0, "vol_ratio": 9.9}]).to_hdf(
                      feature_path, key="daily_multiday_ratio", format="table")
    monkeypatch.setattr("ats.fusion.liquidity_history.DailyLiquidityHistory", lambda: DailyLiquidityHistory(feature_path))

    class FakeReplay:
        def __init__(self):
            self.cfg = ReplayConfig(persist_context=False, track=True, use_production_history=False)
            self.cache = {"000568": np.array(
                    [(_ts(d, hm) - 60, p) for d in days for hm, p in
                     (("09:57", 10.0), ("10:00", 10.0), ("14:57", 10.5), ("15:00", 10.5))],
                dtype=[("time", "i8"), ("close", "f8")])}
            self.tracker = None
            self.carried = []

        def days(self):
            return days

        def _prev_close(self, code, day):
            return 10.0

        def run_day(self, day, focus=(), carry_codes=(), progress=None):
            self.carried.append(list(carry_codes))
            row = {"code": "000568", "ts": _ts(day, "10:00"), "time": "10:00", "entry": 10.0,
                   "pct": 0.1, "tier": 1, "veto": "", "patterns": [] if day == days[1] else ["逆势收复启动"],
                   "reclaim_detail": {"vol_ratio": 1.1, "vwap": 9.9, "vwap3": 9.9, "vwap5": 9.9}}
            meta = {"initial_candidate_codes": ["000568"], "candidate_activation": {},
                    "focus_trace": {}, "market_codes": 1, "records_truncated": 0}
            return ReplayResult(day=day, records=[row], meta=meta)

    rp = FakeReplay()
    out = run_iterations(days=days, replay=rp, history_root=str(tmp_path), output_root=str(tmp_path / "runs"))
    assert rp.carried == [[], ["000568"], ["000568"]]
    assert out["manifest"]["status"] == "complete"
    assert len(out["manifest"]["engine_fingerprint"]) == 16
    assert not os.path.exists(tmp_path / "logs" / "fusion_state")
    with gzip.open(os.path.join(out["run_dir"], days[0] + ".json.gz"), "rt", encoding="utf-8") as f:
        artifact = json.load(f)
    assert artifact["summary"]["outcome_samples"] == 1
    assert artifact["summary"]["production_compare"]["available"] is False
    assert out["last_result"].meta["focus_selection"]["first_selected"][0]["ts"] == _ts(days[-1], "10:00")
    prior = out["last_result"].meta["liquidity_history"]["000568"]["history"][0]
    assert prior["date"] == "2026-10-27" and prior["turnover_pct"] == 5.5
    gap_replay = FakeReplay()
    gap_output = run_iterations(days=[days[0], days[2]], replay=gap_replay,
                                history_root=str(tmp_path), output_root=str(tmp_path / "runs_gap"))
    assert gap_replay.carried == [[], ["000568"]]
    assert "未连续回放" in gap_output["manifest"]["completed"][-1]["summary"]["previous_observations"]["gap"]
