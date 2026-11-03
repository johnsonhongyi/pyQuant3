# -*- coding: utf-8 -*-
"""两类早盘启动和 ATS 主线程通知链的无未来数据/防重测试。"""
import json
import time
from types import SimpleNamespace

from ats.fusion.launch_signal import classify_launch
from ats.fusion.launch_alerts import LaunchAlertPoller, eligible_launch_alert
from ats.fusion.adapter import today_str


def quote(**changes):
    values = dict(
        ts=time.mktime((2026, 11, 3, 10, 0, 0, 0, 0, -1)),
        price=10.2, vwap=10.05, vwap_10d=10.0,
        day_low=9.1, freshness_s=2.0, pct=3.0, ret5d=-4.0, ret20d=-8.0,
        sector_resonance=65.0, vol_ratio=2.2, velocity_pct=0.4,
        extra={"missing": [], "vwap_slope_5m_pct": 0.05},
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_b_v_reclaim_requires_historical_decline_and_sector_volume():
    result = classify_launch(quote(), day_open=9.4)
    assert result["type"] == "B"
    assert result["status"] == "CONFIRMED"
    assert result["permission"] == "WATCH"  # 尚未经梯度风控许可
    assert not classify_launch(quote(ret20d=0.0), day_open=9.4)
    assert classify_launch(quote(sector_resonance=20), day_open=9.4)["status"] == "WATCH"
    assert classify_launch(quote(vol_ratio=1.8), day_open=9.4)["status"] == "WATCH"
    assert not classify_launch(quote(price=9.9), day_open=9.4)  # 未突破 10 日 VWAP 不算收复
    assert classify_launch(quote(extra={"missing": []}), day_open=9.4)["status"] == "WATCH"
    assert classify_launch(quote(extra={"missing": [], "vwap_slope_5m_pct": -0.02}), day_open=9.4)["status"] == "WATCH"
    afternoon = quote(ts=time.mktime((2026, 11, 3, 13, 30, 0, 0, 0, -1)))
    assert not classify_launch(afternoon, day_open=9.4)


def test_a_needs_real_prior_low_and_structure_confirmation():
    ev = quote(day_low=10.02, ret20d=1.0, price=10.2)
    args = dict(day_open=10.05, prev_low=9.80, prev_high=10.1,
                prejudged=True, struct_status="CONFIRMED")
    result = classify_launch(ev, **args)
    assert result["type"] == "A" and result["status"] == "CONFIRMED"
    assert classify_launch(ev, **dict(args, prev_high=11.0))["type"] == "A"
    assert not classify_launch(ev, **dict(args, prev_low=0))
    assert not classify_launch(ev, **dict(args, struct_status="BROKEN"))
    assert not classify_launch(quote(day_low=9.5, ret20d=1), **args)


def test_live_vwap_slope_uses_only_prior_observations():
    from ats.fusion.shadow import FusionShadow
    shadow = object.__new__(FusionShadow)
    import threading
    shadow._launch_vwap_lock = threading.Lock()
    shadow._launch_vwap_samples = {}
    assert shadow._record_launch_vwap_slope("300059", 1000.0, 10.0) is None
    assert shadow._record_launch_vwap_slope("300059", 1300.0, 10.1) is not None
    slope = shadow._record_launch_vwap_slope("300059", 1600.0, 10.2)
    assert slope > 0
    # 10 分钟后的样本会淘汰旧基准，不会把过期斜率当作当前趋势。
    assert shadow._record_launch_vwap_slope("300059", 2300.0, 10.3) is None


def test_replay_slope_is_asof_and_follow_through_is_post_hoc_only():
    from ats.fusion.replay import intraday_vwap_slope_pct, _forward_close_outcome
    values = [10.0, 10.02, 10.04, 10.08, 50.0]
    before = intraday_vwap_slope_pct(values, 3)
    values[-1] = 1.0
    assert intraday_vwap_slope_pct(values, 3) == before

    closes = [10.0] * 22
    closes[2] = 10.25
    outcome = _forward_close_outcome(closes, 1, 10.0, horizon=20)
    assert outcome["known"] and outcome["follow_through"]
    # 未满 20 根未来 bar 时只标注未知，不拿不完整窗口作为误报。
    assert not _forward_close_outcome(closes, 2, 10.0, horizon=20)["known"]


def test_no_chasing_or_stale_snapshot_and_missing_vwap():
    assert classify_launch(quote(price=10.5), day_open=9.4)["status"] == "WATCH"
    assert not classify_launch(quote(freshness_s=35), day_open=9.4)
    assert not classify_launch(quote(extra={"missing": ["vwap"]}), day_open=9.4)


def valid_record(ts):
    return {
        "ts": ts, "day": today_str(ts), "trade_date": today_str(ts),
        "source": "live_strategy", "code": "300059", "name": "测试标的",
        "pct": 3.0, "missing": [],
        "launch_signal": {"type": "B", "status": "CONFIRMED", "permission": "MANUAL_CONFIRM"},
        "fusion": {"tier": 2, "coverage": .8, "provisional": False, "veto_reason": ""},
        "legacy": {"vetoed": False},
    }


def test_alert_guard_rejects_replay_veto_stale_and_weak_coverage():
    now = time.time()
    row = valid_record(now)
    assert eligible_launch_alert(row, now)
    assert not eligible_launch_alert(dict(row, source="replay"), now)
    assert not eligible_launch_alert(dict(row, ts=now-50), now)
    assert not eligible_launch_alert(dict(row, fusion=dict(row["fusion"], veto_reason="stale")), now)
    assert not eligible_launch_alert(dict(row, legacy={"vetoed": True}), now)
    assert not eligible_launch_alert(dict(row, fusion=dict(row["fusion"], coverage=.3)), now)


def test_alert_poller_only_new_data_and_same_code_type_dedup(tmp_path, monkeypatch):
    import ats.fusion.launch_alerts as a
    monkeypatch.setattr(a, "in_trading_session", lambda _: True)
    now = time.time()
    logfile = tmp_path / (today_str(now) + ".jsonl")
    old = valid_record(now - 120)
    logfile.write_text(json.dumps(old) + "\n", encoding="utf-8")
    received = []
    poller = LaunchAlertPoller(received.append, log_dir=str(tmp_path))
    assert poller.poll(now) == 0  # 启动不补播旧记录
    row = valid_record(now)
    with logfile.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    assert poller.poll(now) == 1
    with logfile.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    assert poller.poll(now) == 0
    assert len(received) == 1


def test_real_process_shards_and_multiple_writers(tmp_path, monkeypatch):
    import ats.fusion.launch_alerts as a
    monkeypatch.setattr(a, "in_trading_session", lambda _: True)
    now = time.time()
    day = today_str(now)
    old = valid_record(now - 120)
    new = valid_record(now)
    f1 = tmp_path / (day + "_1001.jsonl")
    f2 = tmp_path / (day + "_1002.jsonl")
    f1.write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n", encoding="utf-8")
    f2.write_text(json.dumps(new) + "\n", encoding="utf-8")
    got = []
    poller = LaunchAlertPoller(got.append, log_dir=str(tmp_path))
    assert len(poller._paths(day)) == 2
    assert poller.poll(now) == 1
    assert len(got) == 1
    assert poller.poll(now) == 0


def test_reentry_context_does_not_depend_on_past_pnl():
    from ats.reentry_tracker import ReentryTracker
    tracker = object.__new__(ReentryTracker)
    tracker._last_db_load_time = time.time()
    tracker._db_load_interval = 60.0
    tracker._closed_trades = {"300059": {
        "reentry_active": True, "sell_date": "2026-10-30",
        "sell_price": 12.5, "pnl_pct": 30.0,
    }}
    first = tracker.prior_exit_context("300059")
    assert first["previous_exit"] and not first["position_verified"]
    tracker._closed_trades["300059"]["pnl_pct"] = -20
    tracker._closed_trades["300059"]["sell_price"] = 9.0
    second = tracker.prior_exit_context("300059")
    assert second["previous_exit"] and not second["position_verified"]
    assert not tracker.prior_exit_context("300333")
    tracker._closed_trades["300059"]["reentry_active"] = False
    assert not tracker.prior_exit_context("300059")


def test_live_shadow_records_reentry_and_keeps_risk_gate(tmp_path, monkeypatch):
    from ats.fusion.shadow import FusionShadow
    from ats.fusion.contract import FusionDecision
    import ats.reentry_tracker as rt
    monkeypatch.setattr(rt, "get_reentry_tracker", lambda: SimpleNamespace(
        prior_exit_context=lambda _: {"previous_exit": True, "sell_date": "2026-10-30", "position_verified": False}
    ))
    from ats.fusion.config import DEFAULTS
    cfg = dict(DEFAULTS, sample_interval_s=0, log_dir="shadow-test", session_gate=False)
    shadow = FusionShadow(config=cfg, root=str(tmp_path))
    shadow.engine.evaluate = lambda event, regime=None, now=None, **kw: FusionDecision(
        code=event.code, ts=now, tier=3, coverage=.9, provisional=False,
        tier_name="L3", evidence=[], veto_reason="",
    )
    import pandas as pd
    row = pd.Series({
        "trade": 10.2, "vwap": 10.05, "ma10dcum": 10.0,
        "open": 9.4, "low": 9.1, "high": 10.2,
        "lastp1d": 9.9, "per5d": -4.0, "per20d": -8.0, "percent": 3.0,
        "amount": 300000000.0, "volume": 300000.0, "ratio": 2.2,
        "sector_resonance": 65.0, "velocity_pct": 0.4,
    })
    now = time.mktime((2026, 11, 3, 10, 0, 0, 0, 0, -1))
    shadow._record_launch_vwap_slope("300059", now - 300.0, 10.0)
    try:
        rec = shadow.observe("300059", row=row, name="测试", now=now, force=True)
        assert rec is not None
        launch = rec["launch_signal"]
        assert launch["type"] == "B"
        assert launch["permission"] == "MANUAL_CONFIRM"
        assert launch["reentry_permission"] == "MANUAL_CONFIRM"
        assert "重新介入许可" in " ".join(rec["fusion"]["evidence"])
    finally:
        shadow.close()
