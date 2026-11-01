from datetime import datetime
import json
import pytest

from ats.fusion.observation import build_observation_evidence

DAY = "2026-10-27"
NOW = datetime(2026, 10, 27, 10).timestamp()


def snapshot():
    values = {"vwap1_prev_session": 10, "vwap3": 10, "vwap5": 10, "vwap10": 10}
    for n in (2, 4, 9):
        values["vwap_prev{}_volume".format(n)] = n
        values["vwap_prev{}_value".format(n)] = 10 * n
    return {"_observation_daily_context": {"asof_day": DAY, "values": values}}


def test_current_vwap_stack_and_early_signals_are_observation_only():
    evidence = build_observation_evidence({"server_ts": NOW, "vwap": 12, "_observation_preprocess_ts": NOW, "_observation_preprocess_asof": DAY, "ch_bc2": 45, "ch_tc2": 3,
                                          "ch_period": "daily", "sig_launch": 1, "sig_start": 0},
                                         snapshot(), NOW, DAY, "live_strategy", 12, 1)
    assert evidence["role"] == "observation_only"
    assert evidence["anchors"]["ch_bc2"]["value"] == 45
    assert evidence["anchors"]["ch_tc2"]["value"] == 3
    assert evidence["early_signals"]["sig_start"]["value"] == 0
    assert evidence["vwap"]["including_current"]["10"] == pytest.approx(10.2)
    assert evidence["vwap"]["ordered_1_3_5_10"] is True
    assert all(evidence["vwap"]["above_previous_session"].values())
    json.dumps(evidence, allow_nan=False)


@pytest.mark.parametrize("timestamp,status", [(NOW + 1, "future"), (NOW - 121, "stale"),
                                              (NOW - 86400, "cross_day"), (None, "unverified_time")])
def test_unknown_or_bad_time_never_becomes_valid_structure(timestamp, status):
    evidence = build_observation_evidence({"ts": timestamp}, snapshot(), NOW, DAY, "live_strategy", 12, 1)
    assert evidence["freshness"] == status
    assert evidence["vwap"]["ordered_1_3_5_10"] is None
    assert evidence["anchors"]["ch_bc2"]["value"] is None


def test_current_ipc_vwap_does_not_masquerade_as_historical_context():
    evidence = build_observation_evidence({"ts": NOW, "vwap3": 8, "vwap5": 7, "vwap10": 6},
                                         {}, NOW, DAY, "live_strategy", 12, 1)
    assert evidence["vwap"]["including_current"]["10"] is None
    assert evidence["vwap"]["previous_session"]["3"] is None


def test_adapter_shadow_and_cross_day_preserve_received_evidence(tmp_path, monkeypatch):
    from ats.fusion.adapter import build_event
    from ats.fusion.shadow import FusionShadow
    from ats.fusion.cross_day import build_cross_day
    monkeypatch.setattr("ats.fusion.shadow_writer.ram_directory", lambda directory: None)
    row = {"trade": 12, "vwap": 12, "percent": 1, "volume": 100, "amount": 120000,
           "server_ts": NOW, "_observation_preprocess_ts": NOW, "_observation_preprocess_asof": DAY, "ch_bc2": 45, "ch_tc2": 3, "sig_launch": 1, "ch_period": "daily"}
    event = build_event(row, snapshot(), code="301079", now=NOW)
    assert event.extra["observation_evidence"]["anchors"]["ch_bc2"]["value"] == 45
    shadow = FusionShadow(config={"enabled": True}, root=str(tmp_path))
    try:
        record = shadow.observe(code="301079", row=row, snap=snapshot(), now=NOW, force=True)
        assert record["observation_evidence"]["early_signals"]["sig_launch"]["value"] == 1
        # 只验证展示投影；保持实际评分不受观察证据驱动。
        projected = dict(record, fusion={"tier": 2})
        state = build_cross_day({DAY: {"301079": [projected]}}, DAY)[0]
        assert state["timeline"][0]["observation_evidence"] == record["observation_evidence"]
    finally:
        shadow.close()


def test_strategy_observation_can_be_followed_without_promoting_l0():
    from ats.fusion.cross_day import build_cross_day
    evidence = build_observation_evidence({"ts": NOW, "_observation_preprocess_ts": NOW, "_observation_preprocess_asof": DAY, "sig_launch": 1}, snapshot(), NOW, DAY, "live_strategy", 12, 1)
    row = {"code": "301079", "ts": NOW, "price": 12, "trade_date": DAY,
           "fusion": {"tier": 0, "veto_reason": "existing veto"}, "observation_evidence": evidence}
    result = build_cross_day({DAY: {"301079": [row]}}, DAY)
    assert result[0]["tier"] == 0
    assert "观察" in result[0]["signal_status"]
    assert "否决" in result[0]["signal_status"]
    assert row["fusion"]["veto_reason"] == "existing veto"
    stale = dict(evidence, freshness="stale")
    assert build_cross_day({DAY: {"301079": [dict(row, observation_evidence=stale)]}}, DAY) == []


def test_strategy_observation_is_carried_to_next_replay_day(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import numpy as np
    from ats.fusion.iteration import run_iterations
    from ats.fusion.replay import ReplayConfig, ReplayResult
    days = ["2026-10-26", "2026-10-27"]
    monkeypatch.setattr("ats.fusion.liquidity_history.DailyLiquidityHistory", lambda: SimpleNamespace(
        status="unavailable", path="", error="test", asof=lambda *args: {}))
    class Replay:
        cfg = ReplayConfig(persist_context=False, use_production_history=False)
        cache = {"301079": np.zeros(0, dtype=[("time", "i8"), ("close", "f8")])}
        tracker = None
        def __init__(self):
            self.carried = []
        def days(self):
            return days
        def _prev_close(self, *args):
            return 10
        def run_day(self, day, focus=(), carry_codes=(), progress=None):
            self.carried.append(list(carry_codes))
            now = datetime.fromisoformat(day + "T10:00:00").timestamp()
            evidence = build_observation_evidence({"ts": now, "_observation_preprocess_ts": now, "_observation_preprocess_asof": day, "sig_launch": 1}, {}, now, day, "replay_minute_proxy", 12, 1)
            return ReplayResult(day=day, records=[{"code": "301079", "ts": now, "time": "10:00", "entry": 12,
                "pct": 1, "tier": 0, "patterns": [], "observation_evidence": evidence}],
                meta={"initial_candidate_codes": ["301079"], "records_truncated": 0})
    replay = Replay()
    run_iterations(days=days, replay=replay, history_root=str(tmp_path), output_root=str(tmp_path / "runs"))
    assert replay.carried == [[], ["301079"]]


def test_mixed_row_and_snapshot_do_not_refresh_stale_signal():
    from ats.fusion.observation import observation_reason
    evidence = build_observation_evidence({"server_ts": NOW}, {"ts": NOW - 86400, "sig_launch": 1},
                                         NOW, DAY, "live_strategy", 12, 1)
    assert evidence["freshness"] == "same_day"
    assert evidence["early_signals"]["sig_launch"]["freshness"] == "cross_day"
    assert not observation_reason(evidence)


def test_preprocess_clock_is_independent_of_realtime_quote_updates():
    from ats.fusion.observation import observation_reason
    row = {"server_ts": NOW, "sig_start": 1, "_observation_preprocess_ts": NOW - 86400,
           "_observation_preprocess_asof": "2026-10-26"}
    evidence = build_observation_evidence(row, {}, NOW, DAY, "live_strategy", 12, 1)
    assert not observation_reason(evidence)
    row["_observation_preprocess_ts"] = NOW - 3600
    row["_observation_preprocess_asof"] = DAY
    evidence = build_observation_evidence(row, {}, NOW, DAY, "live_strategy", 12, 1)
    assert observation_reason(evidence)
    row["_observation_preprocess_asof"] = "2026-10-28"
    assert not observation_reason(build_observation_evidence(row, {}, NOW, DAY, "live_strategy", 12, 1))


def test_real_day_replay_keeps_new_l0_vwap_observation(monkeypatch):
    import os
    import numpy as np
    from types import SimpleNamespace
    from ats.fusion import replay as module
    from ats.fusion.contract import FusionDecision
    from ats.fusion.observation import observation_reason
    dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("volume", "f8")]
    bars = np.array([(NOW + i * 180, 12, 12.1, 11.9, 12, 100) for i in range(6)], dtype=dtype)
    history = snapshot()["_observation_daily_context"]["values"]
    history["close_pre1"] = 10
    monkeypatch.setattr(module, "get_daily_context", lambda: SimpleNamespace(ok=True, asof=lambda *args: history))
    replay = module.DayReplay(cache={"301079": bars}, config=module.ReplayConfig(
        persist_context=False, use_production_history=False, track=False, cuts_mode="fixed", market_path=os.devnull,
        struct_floor=False, pattern_floor=False, record_tier_min=1))
    monkeypatch.setattr(replay, "_universe", lambda *args, **kwargs: ["301079"])
    monkeypatch.setattr(replay.engine, "evaluate", lambda event, *args, **kwargs: FusionDecision(
        code=event.code, ts=event.ts, tier=0, veto_reason="existing veto"))
    result = replay.run_day(DAY)
    assert result.records
    assert all(row["tier"] == 0 and row["veto"] == "existing veto" for row in result.records)
    assert any(observation_reason(row["observation_evidence"]) for row in result.records)
    assert not result.orders


def test_preprocessed_dataframe_survives_ipc_full_and_price_diff(monkeypatch):
    import pandas as pd
    import numpy as np
    from JSONData import tdx_data_Day as tdx
    from JSONData import multiday_feature_store
    from ipc_sync_manager import IPCSyncManager
    from ats.fusion.observation import observation_reason
    monkeypatch.setattr(multiday_feature_store, "get_multiday_features_dict", lambda *args, **kwargs: {})
    dates = pd.bdate_range(end=DAY, periods=60)
    close = np.linspace(10, 12, 60)
    frame = pd.DataFrame({"close": close, "high": close + .2, "low": close - .2, "vol": 1000}, index=dates)
    with monkeypatch.context() as scoped:
        scoped.setattr(tdx.time, "time", lambda: NOW)
        prepared = tdx.calc_trend_channel(frame)
    assert "_observation_preprocess_ts" in prepared
    assert "ch_bc2" in prepared and "ch_tc2" in prepared and "sig_start" in prepared
    outgoing = prepared.tail(1).copy()
    outgoing.index = ["301079"]
    outgoing["server_ts"] = NOW
    outgoing["sig_start"] = 1  # 固定触发值验证传输，不把合成行情当作策略有效性证据。
    mgr = IPCSyncManager(port=29996, service_name="observation_test")
    monkeypatch.setattr(mgr, "_send_received_feedback", lambda *args: None)
    mgr._process_data_package({"type": "UPDATE_DF_ALL", "data": outgoing})
    mgr._process_data_package({"type": "UPDATE_DF_DIFF", "data": pd.DataFrame({"trade": [12.2]}, index=["301079"])})
    row = mgr.get_current_df().loc["301079"].to_dict()
    assert row["_observation_preprocess_ts"] == NOW
    assert row["ch_bc2"] == outgoing.iloc[0]["ch_bc2"]
    evidence = build_observation_evidence(row, {}, NOW, DAY, "live_strategy", 12, 1)
    assert observation_reason(evidence)
    assert evidence["early_signals"]["sig_start"]["time_basis"] == "preprocess"


def test_observation_registry_survives_restart_without_entry(tmp_path, monkeypatch):
    from ats.fusion.shadow import FusionShadow
    monkeypatch.setattr("ats.fusion.shadow_writer.ram_directory", lambda directory: None)
    observer = FusionShadow(config={"enabled": True}, root=str(tmp_path))
    try:
        row = {"trade": 12, "percent": 0, "vwap": 12, "server_ts": NOW, "_observation_preprocess_ts": NOW, "_observation_preprocess_asof": DAY, "sig_start": 1}
        assert observer.observe("301079", row, now=NOW, force=True) is not None
    finally:
        observer.close()
    restarted = FusionShadow(config={"enabled": True}, root=str(tmp_path))
    try:
        assert "301079" in restarted.observation_codes("2026-10-28")
        assert "301079" not in restarted.observation_codes("2026-11-10")
    finally:
        restarted.close()


def test_real_scan_entry_routes_df_signals_before_price_and_volume_funnel():
    import ast
    import logging
    import time
    from types import SimpleNamespace
    from typing import Optional, Dict, Any
    from pathlib import Path
    import pandas as pd
    tree = ast.parse((Path(__file__).resolve().parents[1] / "stock_live_strategy.py").read_text(encoding="utf-8"))
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                  and node.name == "_fusion_scan_market_vanguards")
    namespace = {"pd": pd, "Optional": Optional, "Dict": Dict, "Any": Any,
                 "time": time, "logger": logging.getLogger("observation_test")}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "stock_live_strategy.py", "exec"), namespace)
    calls = []
    fusion = SimpleNamespace(enabled=True, observation_codes=lambda day: {"301080"},
                             observe=lambda **kwargs: calls.append(kwargs) or {})
    def stop_old_funnel(*args):
        raise RuntimeError("old funnel reached")
    namespace["_fusion_percent_series"] = stop_old_funnel
    owner = SimpleNamespace(_fusion_shadow=fusion, _fusion_cross_map={"existing": {}},
                            _fusion_enrich_snap=lambda *args, **kwargs: {},
                            _fusion_update_cross_section=stop_old_funnel)
    frame = pd.DataFrame({"percent": [-5, -3, 0], "ratio": [.2, .1, .1], "sig_start": [1, 0, 1]},
                         index=["301079", "301080", "000001"])
    with pytest.raises(RuntimeError, match="old funnel reached"):
        namespace[method.name](owner, frame, ["000001_d"], None, NOW)
    assert [call["code"] for call in calls] == ["301079", "301080"]
    assert all(call["source"] == "strategy_observation" for call in calls)
    assert all(call["decision"]["action"] == "HOLD" for call in calls)


def test_new_quote_does_not_validate_old_vwap_or_unstamped_strategy():
    from ats.fusion.observation import observation_reason
    evidence = build_observation_evidence({"server_ts": NOW, "sig_start": 1},
        {**snapshot(), "server_ts": NOW - 86400, "vwap": 12}, NOW, DAY, "live_strategy", 12, 1)
    assert evidence["vwap"]["ordered_1_3_5_10"] is None
    assert evidence["early_signals"]["sig_start"]["freshness"] == "unverified_feature_time"
    assert not observation_reason(evidence)


def test_recalculating_old_bar_does_not_make_old_signal_current():
    from ats.fusion.observation import observation_reason
    row = {"server_ts": NOW, "sig_launch": 1, "_observation_preprocess_ts": NOW,
           "_observation_preprocess_asof": "2026-10-23"}
    evidence = build_observation_evidence(row, {}, NOW, DAY, "live_strategy", 12, 1)
    assert evidence["early_signals"]["sig_launch"]["freshness"] == "historical_context"
    assert not observation_reason(evidence)
