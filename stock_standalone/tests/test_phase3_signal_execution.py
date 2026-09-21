import time

from ats.strategy.ipo_trading_center import IPOOrderDirective, IPOTradingCenter


def _directive(action="BUY", **kwargs):
    base = dict(
        action=action,
        code="688826",
        name="测试标的",
        price=100.0,
        size_pct=10.0,
        timestamp=time.time(),
        reason="phase3-test",
    )
    base.update(kwargs)
    return IPOOrderDirective(**base)


def test_signal_state_layering():
    assert _directive("BUY").signal_state == "ACTIONABLE"
    assert _directive("EXIT_ALL").signal_state == "EXIT"
    assert _directive("FULL_ROTATION_SWAP").signal_state == "CANDIDATE"
    assert _directive("WATCH").signal_state == "OBSERVE"


def test_time_window_duplicate_retains_existing_pending():
    center = IPOTradingCenter()
    first = _directive()
    assert len(center._publish_converged_directives([first])) == 1
    second = _directive()
    pending = center._publish_converged_directives([second])
    assert len(pending) == 1
    assert pending[0] is first
    summary = center.get_signal_convergence_summary()
    assert summary["time_window_suppressed_count"] == 1


def test_time_window_dedupe_allows_risk_budget_change():
    center = IPOTradingCenter()
    first = _directive(size_pct=10.0)
    center._publish_converged_directives([first])
    second = _directive(size_pct=5.0)
    pending = center._publish_converged_directives([second])
    assert len(pending) == 1
    assert pending[0].size_pct == 5.0


def test_quality_stats_are_split_by_action():
    center = IPOTradingCenter()
    today = time.strftime("%Y-%m-%d")
    center._signal_iteration_log = [
        {"time_str": f"{today} 10:00:00", "action": "BUY", "execution_status": "EXECUTED"},
        {"time_str": f"{today} 10:01:00", "action": "BUY", "execution_status": "REJECTED"},
        {"time_str": f"{today} 10:02:00", "action": "REDUCE_30", "execution_status": "FILTERED"},
        {"time_str": f"{today} 10:03:00", "action": "EXIT_ALL", "execution_status": "EXECUTED"},
    ]
    stats = center.get_directive_quality_stats()["actions"]
    assert stats["BUY"] == {"total": 2, "executed": 1, "rejected": 1, "filtered": 0}
    assert stats["REDUCE"]["filtered"] == 1
    assert stats["SELL"]["executed"] == 1


def test_structured_reject_marks_directive_and_history(monkeypatch):
    center = IPOTradingCenter()
    monkeypatch.setattr(center, "_save_persisted_ledger", lambda: None)
    directive = _directive()
    assert center._reject_directive(directive, "TEST_BLOCK", "测试拒绝") is False
    assert directive.signal_state == "BLOCKED"
    assert directive.reject_code == "TEST_BLOCK"
    item = center.get_signal_iteration_log()[0]
    assert item["execution_status"] == "REJECTED"
    assert item["reject_code"] == "TEST_BLOCK"
    assert item["reject_reason"] == "测试拒绝"



def test_daily_quality_report_contains_reject_reasons():
    center = IPOTradingCenter()
    today = time.strftime("%Y-%m-%d")
    center._signal_iteration_log = [
        {
            "time_str": f"{today} 10:00:00",
            "action": "BUY",
            "execution_status": "REJECTED",
            "reject_code": "PRICE_DRIFT_EXCEEDED",
        },
        {
            "time_str": f"{today} 10:01:00",
            "action": "BUY",
            "execution_status": "REJECTED",
            "reject_code": "PRICE_DRIFT_EXCEEDED",
        },
    ]
    report = center.get_buy_sell_quality_daily_report()
    assert report["action_stats"]["BUY"]["rejected"] == 2
    assert report["top_reject_reasons"]["PRICE_DRIFT_EXCEEDED"] == 2
