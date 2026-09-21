import time

from ats.strategy.ipo_trading_center import IPOOrderDirective, IPOTradingCenter
from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal


def test_signal_state_defaults_by_action():
    assert IPOOrderDirective(action="BUY", code="1", name="x").signal_state == "ACTIONABLE"
    assert IPOOrderDirective(action="EXIT_ALL", code="1", name="x").signal_state == "EXIT"
    assert IPOOrderDirective(action="WATCH", code="1", name="x").signal_state == "OBSERVE"


def test_time_window_dedupe_retains_previous_pending():
    center = IPOTradingCenter(total_capital=100000.0)
    d1 = IPOOrderDirective(
        action="BUY", code="688001", name="x", price=10.0,
        size_pct=10.0, reason="same", timestamp=time.time(),
    )
    first = center._publish_converged_directives([d1])
    d2 = IPOOrderDirective(
        action="BUY", code="688001", name="x", price=10.0,
        size_pct=10.0, reason="same", timestamp=time.time(),
    )
    second = center._publish_converged_directives([d2])
    assert len(first) == len(second) == 1
    assert second[0] is d1
    assert center.get_signal_convergence_summary()["time_window_suppressed_count"] == 1



def test_persistent_guard_rejects_stale_buy_before_kernel():
    center = IPOTradingCenter(total_capital=100000.0)
    center._auto_load_ledger = True
    center._reports_cache["688001"] = VWAPDetectorSignal(
        code="688001", name="x", price=10.0, update_time=time.strftime("%H:%M:%S")
    )
    directive = IPOOrderDirective(
        action="BUY", code="688001", name="x", price=10.0,
        size_pct=10.0, timestamp=time.time() - 181,
    )
    assert center.record_order_execution(directive) is False
    assert directive.reject_code == "STALE_DIRECTIVE"
    assert center.get_signal_iteration_log()[0]["execution_status"] == "REJECTED"


def test_daily_quality_stats_are_separated():
    center = IPOTradingCenter(total_capital=100000.0)
    buy = IPOOrderDirective(action="BUY", code="688001", name="x")
    sell = IPOOrderDirective(action="EXIT_ALL", code="688002", name="y")
    center._log_directive_event(buy, status="REJECTED", reject_code="X", reject_reason="x")
    center._log_directive_event(sell, status="EXECUTED")
    report = center.get_buy_sell_quality_daily_report()
    assert report["action_stats"]["BUY"]["rejected"] == 1
    assert report["action_stats"]["SELL"]["executed"] == 1
    assert report["top_reject_reasons"]["X"] == 1
