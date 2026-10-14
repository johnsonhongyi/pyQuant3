"""Regression checks for quarantined replay and reconciliation inputs."""

import pytest

from ats.llm.production_vwap_trade_replay import (
    persist_replay_report, reconcile_trade_records, simulate_signal_replay,
)


DAYS = ["2026-10-09", "2026-10-12", "2026-10-13"]
BAR = {"open": 10, "high": 11, "low": 9, "close": 10, "vol": 1000, "vwap": 10}


def replay(rows):
    return simulate_signal_replay(
        rows, completed_sessions=DAYS, calendar_sessions=DAYS,
        bars_by_code={"000001": {day: dict(BAR) for day in DAYS}},
    )


def test_invalid_exit_does_not_close_position():
    result = replay([
        {"code": "000001", "date": DAYS[0], "action": "买入", "price": 10},
        {"code": "000001", "date": DAYS[1], "action": "卖出", "price": 99},
    ])
    assert not result["trades"]
    assert len(result["open_positions"]) == 1
    assert any(e["event_status"] == "SIGNAL_QUARANTINED_DATA" for e in result["events"])


def test_same_day_conflicting_signals_are_order_independent():
    rows = [
        {"code": "000001", "date": DAYS[0], "action": action, "price": 10}
        for action in ("买入", "卖出")
    ]
    for inputs in (rows, rows[::-1]):
        result = replay(inputs)
        assert result["summary"]["buy_filled_count"] == 0
        assert any(e["detail"] == "AMBIGUOUS_SAME_DAY_SIGNALS" for e in result["events"])


@pytest.mark.parametrize("fee", [None, "bad", float("nan"), float("inf"), -1, True])
def test_invalid_fee_cannot_reconcile(fee):
    result = reconcile_trade_records([{
        "code": "000001", "status": "CLOSED", "buy_price": 10,
        "sell_price": 11, "buy_amount": 100, "fee": fee, "profit": 100,
    }], bars_by_code={})
    record = result["records"][0]
    assert not record["pnl_formula_input_valid"]
    assert record["recomputed_profit"] is None


def test_explicit_zero_fee_can_reconcile():
    result = reconcile_trade_records([{
        "code": "000001", "status": "CLOSED", "buy_price": 10,
        "sell_price": 11, "buy_amount": 100, "fee": 0, "profit": 100,
    }], bars_by_code={})
    assert result["records"][0]["profit_reconciled"] is True


@pytest.mark.parametrize("status,buy_date", [("CANCELLED", DAYS[0]), ("OPEN", "2026-10-14")])
def test_invalid_open_mark_is_not_valued(status, buy_date):
    result = reconcile_trade_records([{
        "code": "000001", "status": status, "buy_date": buy_date,
        "buy_price": 10, "buy_amount": 100, "fee": 0,
    }], bars_by_code={"000001": {DAYS[-1]: BAR}})
    assert result["records"][0]["unrealized_profit_at_mark"] is None


@pytest.mark.parametrize("name", ["../outside.csv", "..\\outside.csv", "C:\\outside.csv"])
def test_artifact_path_escape_rejected_before_mutation(tmp_path, name):
    report = {"artifacts": {"paper_trades_csv": name}, "_paper_trades": [{"code": "000001"}]}
    with pytest.raises(ValueError, match="INVALID_REPORT_ARTIFACT_NAME"):
        persist_replay_report(tmp_path, "reports", report)
    assert "_paper_trades" in report
    assert not (tmp_path / "reports").exists()
