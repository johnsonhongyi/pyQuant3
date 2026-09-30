from datetime import datetime as RealDateTime
import json
from pathlib import Path
from types import SimpleNamespace

from tools import generate_matured_labels as labels
from tools import run_ipo_data_acquisition as acquisition


class _FixedDateTime(RealDateTime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 27, 15, 40, tzinfo=tz)


def test_recent_ipo_cohort_is_bounded_and_review_only(tmp_path, monkeypatch):
    monkeypatch.setattr(labels, "datetime", _FixedDateTime)
    evidence_dir = tmp_path / "data" / "ipo_learning" / "outcome_evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "000004.json").write_text(json.dumps({
        "ticker": "000004", "status": "MATURED_PENDING_REVIEW",
        "evidence_id": "outcome:verified", "training_eligible": False,
    }), encoding="utf-8")
    (evidence_dir / "000008.json").write_text("{}", encoding="utf-8")
    state_path = tmp_path / "data" / "ipo_learning" / "labels.cohort_state.json"
    state_path.write_text(json.dumps({"retry_after": {"000005": "2026-09-28"}}), encoding="utf-8")
    monkeypatch.setattr(labels, "_ats_calendar", lambda _root: {
        code: {"code": code, "listing_date": day, "issue_price": price}
        for code, day, price in (
            ("000001", "2026-08-01", 10.0), ("000002", "2026-09-24", 10.0),
            ("000003", "2026-09-01", 10.0), ("000004", "2026-09-02", 10.0),
            ("000005", "2026-09-03", 10.0), ("000006", "2026-09-04", True),
            ("000007", "2026-09-05", 11.0), ("000008", "2026-09-06", "12.5"),
        )
    })
    calls = []

    def collect(ticker, *, calendar, root):
        calls.append((ticker, calendar[ticker]["listing_date"], Path(root)))
        status = "MATURED_PENDING_REVIEW" if ticker == "000003" else "UNREADY"
        return {"ticker": ticker, "status": status}

    monkeypatch.setattr(labels, "collect_for_ticker", collect)
    reports = labels.collect_recent_ipo_cohort(tmp_path, batch_size=3)

    assert [ticker for ticker, _, _ in calls] == ["000003", "000007", "000008"]
    assert all(root == tmp_path for _, _, root in calls)
    assert reports[-1]["selected"] == 3
    assert reports[-1]["matured_pending_review"] == 1
    assert reports[-1]["training_authorized"] is False
    assert reports[-1]["retry_after"]["000007"] == "2026-09-28"
    assert json.loads((tmp_path / "data/ipo_learning/labels.cohort.latest.json").read_text(encoding="utf-8"))["training_authorized"] is False


def test_recent_ipo_cohort_does_not_fetch_before_close(tmp_path, monkeypatch):
    class BeforeCloseDateTime(_FixedDateTime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 27, 15, 29, tzinfo=tz)

    monkeypatch.setattr(labels, "datetime", BeforeCloseDateTime)
    monkeypatch.setattr(labels, "_ats_calendar", lambda _root: (_ for _ in ()).throw(AssertionError()))

    reports = labels.collect_recent_ipo_cohort(tmp_path)

    assert reports == [{"status": "NOT_DUE", "reason": "全体新股D1-D3标签从15:30起采集"}]


def test_acquisition_cycle_runs_snapshot_and_full_cohort_scans(tmp_path, monkeypatch):
    for name in (
        "collect_issue_prices_from_ats_cache", "collect_ipo_facts",
        "collect_listing_day_anchors", "collect_listing_supply_pace",
        "collect_market_breadth_and_industry", "collect_limit_up_break_rate",
        "collect_live_metrics", "collect_market_pulse_fields",
        "collect_financing_balance_change", "collect_tdx_market_history_fields",
        "collect_tdx_market_snapshot_fields",
    ):
        monkeypatch.setattr(acquisition, name, lambda *_args, **_kwargs: {"status": "UNREADY"})
    monkeypatch.setattr(
        acquisition.IPODecisionConfigSnapshot, "from_yaml", lambda _path: SimpleNamespace()
    )
    monkeypatch.setattr(acquisition, "collect_source_readiness", lambda *_args: {
        "status": "UNREADY", "ready_count": 0, "required_count": 41,
        "next_actions": [], "observations": [], "configuration_hash": "c", "data_contract_hash": "d",
    })

    from tools import generate_matured_labels

    monkeypatch.setattr(generate_matured_labels, "collect_for_waiting_snapshots", lambda *_args, **_kwargs: [
        {"status": "NO_PENDING"}
    ])
    monkeypatch.setattr(generate_matured_labels, "collect_recent_ipo_cohort", lambda *_args, **_kwargs: [
        {"status": "COHORT_SCAN_COMPLETE", "training_authorized": False}
    ])

    report = acquisition.run_cycle("301689", collect_labels=True, root=tmp_path)

    assert [item["status"] for item in report["label_reports"]] == [
        "NO_PENDING", "COHORT_SCAN_COMPLETE"
    ]
    assert report["runtime_authorized"] is False
    assert report["llm_invocation_performed"] is False


def test_ats_learning_cycle_reuses_new_stock_module_without_separate_collectors(tmp_path, monkeypatch):
    import pandas as pd
    from ats.new_stock_fetcher import NewStockFetcher
    from ats.strategy.ipo_vwap_detector_engine import IPOVWAPDetectorEngine

    calls = []
    monkeypatch.setattr(NewStockFetcher, "get_instance", lambda: SimpleNamespace(
        get_combined_new_stocks=lambda: (calls.append("ats_stock") or pd.DataFrame([{
            "code": "920202", "listing_date": "2026-09-29", "status": "首日(N)",
            "issue_price": 7.55,
        }]))
    ))
    monkeypatch.setattr(IPOVWAPDetectorEngine, "get_instance", lambda: SimpleNamespace(
        analyze_stock=lambda code: (calls.append("ats_detector") or SimpleNamespace(
            price=0.0, signal_type="WATCH", signal_tier="WATCH", vwap=0.0,
            vwap_diff_pct=0.0, horse_race_score=0.0,
        ))
    ))
    monkeypatch.setattr(acquisition, "collect_issue_prices_from_ats_cache", lambda _root, **_kwargs: {
        "status": "READY", "saved_count": 1,
    })
    monkeypatch.setattr(acquisition, "collect_source_readiness", lambda *_args: {
        "ready_count": 1, "required_count": 41, "observations": [], "next_actions": [],
        "configuration_hash": "c", "data_contract_hash": "d",
    })
    monkeypatch.setattr(acquisition.IPODecisionConfigSnapshot, "from_yaml", lambda _path: SimpleNamespace())
    report = acquisition.run_ats_learning_cycle("920202", root=tmp_path)

    assert calls == ["ats_stock", "ats_detector"]
    assert report["operating_mode"] == "ATS_SIGNAL_SHADOW"
    assert report["entry_authorized"] is False


def test_ats_cadence_prevents_repeat_detector_reads(tmp_path, monkeypatch):
    import pandas as pd
    from ats.new_stock_fetcher import NewStockFetcher
    from ats.strategy.ipo_vwap_detector_engine import IPOVWAPDetectorEngine

    calls = []
    frame = pd.DataFrame([{"code": "920202", "listing_date": "2026-09-29",
                           "status": "次新", "issue_price": 7.55}])
    monkeypatch.setattr(acquisition, "_ats_market_session_active", lambda: True)
    monkeypatch.setattr(NewStockFetcher, "get_instance", lambda: SimpleNamespace(
        get_combined_new_stocks=lambda: (calls.append("table") or frame)))
    monkeypatch.setattr(acquisition, "get_cached_ats_stock_table", lambda _fetcher: frame)
    monkeypatch.setattr(IPOVWAPDetectorEngine, "get_instance", lambda: SimpleNamespace(
        analyze_stock=lambda _code: (calls.append("detector") or SimpleNamespace(
            price=0.0, signal_type="WATCH", signal_tier="WATCH", vwap=0.0,
            vwap_diff_pct=0.0, horse_race_score=0.0))))
    monkeypatch.setattr(acquisition, "collect_issue_prices_from_ats_cache", lambda *a, **k: {})
    monkeypatch.setattr(acquisition.IPODecisionConfigSnapshot, "from_yaml", lambda _path: SimpleNamespace())
    monkeypatch.setattr(acquisition, "collect_source_readiness", lambda *a: {
        "ready_count": 0, "required_count": 41, "observations": [], "next_actions": [],
        "configuration_hash": "c", "data_contract_hash": "d"})
    acquisition.run_ats_learning_cycle("920202", root=tmp_path)
    second = acquisition.run_ats_learning_cycle("920202", root=tmp_path)
    assert calls == ["table", "detector"]
    assert second["source_collection"]["mode"] == "CADENCE_THROTTLED"
    assert second["ats_signal_capture"]["state"] == "UNREADY"
    assert second["entry_authorized"] is False
