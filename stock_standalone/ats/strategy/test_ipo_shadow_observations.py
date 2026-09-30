"""Point-in-time shadow capture must reject information available after cutoff."""

import json
import hashlib
import sqlite3
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
from ats.strategy.ipo_shadow_observations import (
    ats_signal_paper_outcomes, capture_ats_signal_observation,
    capture_shadow_observation, learn_ats_signal_quality, train_shadow_candidate,
)


def test_ats_signal_capture_requires_fresh_source_time_and_commits(tmp_path):
    computed = datetime(2026, 9, 29, 2, 0, tzinfo=timezone.utc)
    signal = {
        "ticker": "920202", "status": "OBSERVED", "source_time_verified": True,
        "source_as_of": (computed - timedelta(seconds=10)).isoformat(),
        "bar_as_of": (computed - timedelta(seconds=60)).isoformat(),
        "computed_at": computed.isoformat(), "signal_type": "PULLBACK_BUY",
        "signal_tier": "S", "price": 26.16, "vwap": 25.8,
        "vwap_diff_pct": 1.4, "horse_race_score": 75.0,
    }
    result = capture_ats_signal_observation(
        tmp_path, signal, configuration_hash="a" * 64, data_contract_hash="b" * 64,
    )
    assert result["state"] == "CAPTURED"
    assert result["training_eligible"] is False
    with sqlite3.connect(tmp_path / "data/ipo_learning/shadow_observations.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM ats_signal_observations").fetchone()[0] == 1
    signal["signal_type"] = "WATCH"
    assert capture_ats_signal_observation(
        tmp_path, signal, configuration_hash="a" * 64, data_contract_hash="b" * 64,
    )["reason"] == "ATS_SIGNAL_NOT_ACTIONABLE"
    signal["signal_type"] = "PULLBACK_BUY"
    assert capture_ats_signal_observation(
        tmp_path, signal, configuration_hash=None, data_contract_hash="b" * 64,
    )["state"] == "UNREADY"
    signal["source_as_of"] = (computed - timedelta(seconds=121)).isoformat()
    assert capture_ats_signal_observation(
        tmp_path, signal, configuration_hash="a" * 64, data_contract_hash="b" * 64,
    )["state"] == "UNREADY"
    signal["source_as_of"] = (computed - timedelta(seconds=10)).isoformat()
    signal["bar_as_of"] = (computed - timedelta(seconds=301)).isoformat()
    assert capture_ats_signal_observation(
        tmp_path, signal, configuration_hash="a" * 64, data_contract_hash="b" * 64,
    )["state"] == "UNREADY"


@pytest.mark.parametrize("partial, final_shares, expected_closed", [(False, 100, 1), (True, 60, 1), (True, 50, 0), (True, 70, 0)])
def test_signal_outcome_uses_complete_paper_exit_and_both_side_fees(tmp_path, partial, final_shares, expected_closed):
    observed = datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc)
    signal = {
        "ticker": "920202", "status": "OBSERVED", "source_time_verified": True,
        "source_as_of": (observed - timedelta(seconds=10)).isoformat(),
        "bar_as_of": (observed - timedelta(seconds=60)).isoformat(),
        "computed_at": observed.isoformat(), "signal_type": "PULLBACK_BUY",
        "signal_tier": "S", "price": 10.0, "vwap": 9.9,
        "vwap_diff_pct": 1.0, "horse_race_score": 70.0,
    }
    assert capture_ats_signal_observation(
        tmp_path, signal, configuration_hash="a" * 64, data_contract_hash="b" * 64,
    )["state"] == "CAPTURED"
    ledger = tmp_path / "ats/config/ipo_trading_ledger.json"
    ledger.parent.mkdir(parents=True)
    buy_time = observed.timestamp() + 20
    sell_time = buy_time + 86400
    fills = [
        {"code": "920202", "action": "BUY", "execution_status": "EXECUTED",
         "timestamp": buy_time, "price": 10.0, "shares": 100, "directive_id": "buy"},
        {"code": "920202", "action": "SELL", "execution_status": "EXECUTED",
         "timestamp": sell_time + 60, "price": 10.1, "shares": final_shares, "directive_id": "sell"},
    ]
    if partial:
        fills.append({"code": "920202", "action": "REDUCE_HALF", "execution_status": "EXECUTED",
                      "timestamp": sell_time, "price": 10.1, "shares": 40, "directive_id": "partial"})
    ledger.write_text(json.dumps({"signal_iteration_log": fills}), encoding="utf-8")
    result = ats_signal_paper_outcomes(tmp_path)
    assert result["closed_count"] == expected_closed
    if not expected_closed:
        assert result["pending_count"] == 1
        return
    assert result["outcomes"][0]["fees"] == (10.15 if partial else 5.15)
    assert result["outcomes"][0]["net_pnl"] == (-0.15 if partial else 4.85)
    assert result["outcomes"][0]["label_candidate"] == ("LOSS_OR_FLAT" if partial else "PROFIT")
    assert result["training_eligible"] is False
    learned = learn_ats_signal_quality(tmp_path, result)
    assert learned["state"] == "WAITING_MORE_PAPER_OUTCOMES"
    assert learned["groups"][0]["state"] == "INSUFFICIENT_SAMPLES"
    assert learned["entry_authorized"] is False


def test_signal_quality_requires_forward_positive_paper_returns(tmp_path):
    outcomes = [
        {"signal_type": "PULLBACK_BUY", "signal_tier": "S", "as_of_time": f"2026-09-{day:02d}",
         "observation_hash": str(day), "net_return_pct": 1.0 if day < 9 else -1.0}
        for day in range(1, 11)
    ]
    result = learn_ats_signal_quality(tmp_path, {"outcomes": outcomes})
    assert result["state"] == "SHADOW_CANDIDATES"
    assert result["groups"][0]["state"] == "PAPER_NONPOSITIVE_CANDIDATE"
    assert result["entry_authorized"] is False


def test_shadow_capture_excludes_future_available_fields(tmp_path):
    cutoff = datetime(2026, 9, 29, 2, 0, tzinfo=timezone.utc)
    context = {
        "configuration_hash": "a" * 64,
        "data_contract_hash": "b" * 64,
        "observation_checks": {"ret_pct": "OBSERVED", "turnover_pct": "OBSERVED"},
        "data_observations": {
            "ret_pct": {
                "status": "OBSERVED", "value": 4.5,
                "source_id": "test", "source_version": "v1",
                "as_of_time": cutoff.isoformat(), "available_at": cutoff.isoformat(),
            },
            "turnover_pct": {
                "status": "OBSERVED", "value": 12.0,
                "source_id": "test", "source_version": "v1",
                "as_of_time": cutoff.isoformat(),
                "available_at": (cutoff + timedelta(seconds=1)).isoformat(),
            },
        },
        "lrrm": SimpleNamespace(liquidity_regime="NORMAL"),
    }
    result = capture_shadow_observation(tmp_path, "301689", context, cutoff=cutoff)
    assert result["state"] == "CAPTURED"
    assert result["observed_field_count"] == 1
    with sqlite3.connect(tmp_path / "data/ipo_learning/shadow_observations.sqlite") as db:
        payload = json.loads(db.execute(
            "SELECT payload_json FROM shadow_observations"
        ).fetchone()[0])
    assert set(payload["fields"]) == {"ret_pct"}
    assert payload["sentiment"]["lrrm"] == "NORMAL"


def test_candidate_training_uses_reviewed_labels_and_stays_inactive(tmp_path):
    source = Path(__file__).resolve().parents[2] / "config/ipo_sentiment.yaml"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "ipo_sentiment.yaml").write_bytes(source.read_bytes())
    config = IPODecisionConfigSnapshot.from_yaml(str(config_dir / "ipo_sentiment.yaml"))
    evidence_dir = tmp_path / "data/ipo_learning/outcome_evidence"
    evidence_dir.mkdir(parents=True)
    review_db = tmp_path / "data/ipo_learning/outcome_reviews.sqlite"
    with sqlite3.connect(review_db) as connection:
        connection.execute("""CREATE TABLE outcome_reviews (
            evidence_id TEXT, evidence_hash TEXT, decision TEXT, reviewer TEXT,
            reason TEXT, reviewed_at_utc TEXT
        )""")
        for index in range(10):
            listing = datetime(2026, 9, 1 + index, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
            ticker = f"30{index:04d}"
            label = bool(index % 2)
            context = {
                "configuration_hash": config.config_hash,
                "data_contract_hash": config.data_contract.config_hash,
                "observation_checks": {"ret_pct": "OBSERVED", "turnover_pct": "OBSERVED"},
                "data_observations": {
                    name: {
                        "status": "OBSERVED", "value": value,
                        "source_id": "test", "source_version": "v1",
                        "as_of_time": listing.isoformat(), "available_at": listing.isoformat(),
                    }
                    for name, value in (("ret_pct", 3.0 if label else -3.0),
                                        ("turnover_pct", float(index + 1)))
                },
            }
            assert capture_shadow_observation(tmp_path, ticker, context, cutoff=listing)["state"] == "CAPTURED"
            evidence = {
                "schema_version": "ipo-outcome-evidence.v1",
                "status": "MATURED_PENDING_REVIEW",
                "review_status": "PENDING_HUMAN_REVIEW",
                "labels_mature": True, "training_eligible": False,
                "ticker": ticker, "listing_date": listing.date().isoformat(),
                "d1_positive": label,
            }
            hashed = {key: value for key, value in evidence.items() if key != "status"}
            digest = hashlib.sha256(json.dumps(
                hashed, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")).hexdigest()
            evidence["evidence_id"] = "outcome:" + digest[:48]
            evidence["evidence_hash"] = digest
            (evidence_dir / f"{ticker}.json").write_text(json.dumps(evidence), encoding="utf-8")
            connection.execute(
                "INSERT INTO outcome_reviews VALUES (?, ?, 'ACCEPTED', 'tester', 'checked', ?)",
                (evidence["evidence_id"], digest, (listing + timedelta(days=4)).isoformat()),
            )
        connection.commit()
    result = train_shadow_candidate(tmp_path)
    assert result["state"] in {"CANDIDATE_READY", "CANDIDATE_BELOW_BASELINE"}
    assert result["sample_count"] == 10
    artifact = json.loads((tmp_path / "data/ipo_learning/shadow_models" /
                           f"{result['model_hash']}.json").read_text(encoding="utf-8"))
    assert artifact["activated"] is False
    assert artifact["train_count"] + artifact["test_count"] == 10


def test_future_intraday_bars_are_excluded_from_source_and_cached_detector_frames():
    import pandas as pd
    from ats.tdx_realtime_fetcher import filter_available_intraday_bars

    cutoff = datetime(2026, 9, 30, 11, 29, tzinfo=ZoneInfo("Asia/Shanghai"))
    frame = pd.DataFrame({"datetime": ["2026-09-29 15:00", "2026-09-30 11:29",
                                        "2026-09-30 13:00", "bad"], "close": [10, 11, 99, 99]})
    original = frame.copy(deep=True)
    assert filter_available_intraday_bars(frame, cutoff)["close"].tolist() == [10, 11]
    pd.testing.assert_frame_equal(frame, original)
    cached = pd.DataFrame({"date": ["2026-09-30"] * 2, "time_only": ["11:29", "13:00"],
                           "close": [11, 99]})
    assert filter_available_intraday_bars(cached, cutoff)["close"].tolist() == [11]
    assert filter_available_intraday_bars(cached, cutoff.astimezone(timezone.utc))["close"].tolist() == [11]


def test_paper_exit_log_records_actual_quantity_when_directive_is_zero_or_oversized(tmp_path):
    from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOTradingPosition, IPOOrderDirective

    for requested in (0, 200):
        center = IPOTradingCenter(total_capital=100000, auto_load_ledger=False,
                                  ledger_file=str(tmp_path / f"ledger-{requested}.json"))
        center._positions["301689"] = IPOTradingPosition(
            code="301689", name="sample", shares=100, available_shares=100,
            cost_price=10, current_price=11, entry_date="2026-09-28", status="HOLDING")
        directive = IPOOrderDirective(action="EXIT_ALL", code="301689", name="sample", price=11,
                                       shares=requested)
        assert center.record_order_execution(directive) is True
        assert center.get_signal_iteration_log()[0]["shares"] == 100
        assert center.get_position("301689") is None


def test_detector_filters_future_cached_bars_before_evaluation(monkeypatch):
    import pandas as pd
    from ats.strategy import ipo_vwap_detector_engine as detector

    engine = detector.IPOVWAPDetectorEngine.__new__(detector.IPOVWAPDetectorEngine)
    engine._eval_cache = {}
    engine.enable_intraday_volume_normalization = False
    engine.fetcher = SimpleNamespace(fetch_stock_snapshot=lambda _code: {})
    frame = pd.DataFrame({"date": ["2026-09-30"] * 2, "time_only": ["11:29", "13:00"],
                           "close": [11, 99]})
    monkeypatch.setattr(detector, "resolve_fast_ipo_name", lambda _code: "sample")
    engine._fetch_multi_day_bars_fast = lambda *args, **kwargs: (frame, 0)
    seen = []
    def evaluate(available, signal, **kwargs):
        seen.extend(available["close"].tolist())
        signal.price = float(available.iloc[-1]["close"])
    engine._evaluate_vwap_structure = evaluate
    engine._evaluate_bottom_base_structure = lambda *args, **kwargs: None
    engine._compute_ipo_intraday_metrics = lambda *args, **kwargs: None
    engine._evaluate_kline_trend = lambda *args, **kwargs: None
    engine._synthesize_final_decision = lambda *args, **kwargs: None
    result = engine.analyze_stock("301689", eval_time=datetime(2026, 9, 30, 11, 29,
                                                              tzinfo=ZoneInfo("Asia/Shanghai")))
    assert seen == [11]
    assert result.price == 11
    assert result.extra_data["ipo_source_bar_as_of"] == "2026-09-30T11:29"
    assert "分析提示" not in result.signal_desc


def test_source_refresh_cadence_survives_restart_and_is_per_symbol(tmp_path):
    from tools.run_ipo_data_acquisition import _reserve_ats_source_refresh
    now = datetime(2026, 9, 30, 2, 0, tzinfo=timezone.utc)
    assert _reserve_ats_source_refresh(tmp_path, "301689", now)
    assert not _reserve_ats_source_refresh(tmp_path, "301689", now + timedelta(seconds=299))
    assert _reserve_ats_source_refresh(tmp_path, "920202", now)
    assert _reserve_ats_source_refresh(tmp_path, "301689", now + timedelta(seconds=300))
    assert not _reserve_ats_source_refresh(tmp_path, "../bad", now)


def test_source_refresh_reservation_serializes_concurrent_callers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from tools.run_ipo_data_acquisition import _reserve_ats_source_refresh
    now = datetime(2026, 9, 30, 2, 0, tzinfo=timezone.utc)
    with ThreadPoolExecutor(max_workers=4) as executor:
        for trial in range(10):
            ticker = f"{301689 + trial:06d}"
            results = list(executor.map(lambda _: _reserve_ats_source_refresh(tmp_path, ticker, now), range(4)))
            assert results.count(True) == 1
