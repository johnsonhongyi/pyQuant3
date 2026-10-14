from __future__ import annotations

import struct

import pytest

from ats.llm.production_vwap_trade_replay import (
    _recorded_time_in_session,
    daily_vwap,
    reconcile_trade_records,
    simulate_signal_replay,
)


def _bar(open_price, high, low, close, amount, volume):
    vwap, state = daily_vwap({
        "open": open_price, "high": high, "low": low, "close": close,
        "amount": amount, "vol": volume,
    })
    assert state == "VALID"
    return {
        "open": open_price, "high": high, "low": low, "close": close,
        "amount": amount, "vol": volume, "vwap": vwap, "vwap_state": state,
    }


def test_daily_vwap_uses_raw_yuan_and_share_units():
    value, state = daily_vwap({
        "open": 9.67, "high": 9.70, "low": 9.57, "close": 9.59,
        "amount": 654402304.0, "vol": 68029000,
    })
    assert state == "VALID"
    assert value == pytest.approx(9.61946, abs=1e-5)


def test_signal_replay_fills_next_open_and_enforces_t_plus_one():
    days = ["2026-10-01", "2026-10-02", "2026-10-05"]
    signals = [
        {"date": days[0], "code": "600000", "price": 10.2, "action": "买入"},
        {"date": days[1], "code": "600000", "price": 10.6, "action": "卖出"},
    ]
    bars = {"600000": {
        days[0]: _bar(10.0, 10.3, 9.9, 10.2, 100000, 10000),
        days[1]: _bar(10.5, 10.8, 10.4, 10.6, 106000, 10000),
        days[2]: _bar(11.0, 11.2, 10.9, 11.1, 111000, 10000),
    }}
    result = simulate_signal_replay(
        signals, completed_sessions=days, calendar_sessions=days, bars_by_code=bars,
    )
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["buy_date"] == days[1]
    assert trade["sell_date"] == days[2]
    assert trade["t_plus_one_valid"] is True
    assert trade["gross_pnl"] == pytest.approx(50.0)


def test_vwap_break_exits_at_following_open_and_bad_entry_is_quarantined():
    days = ["2026-10-01", "2026-10-02", "2026-10-05"]
    signals = [
        {"date": days[0], "code": "600000", "price": 10.2, "action": "买入"},
        {"date": days[2], "code": "000001", "price": 20.0, "action": "买入"},
    ]
    bars = {
        "600000": {
            days[0]: _bar(10.0, 10.3, 9.9, 10.2, 100000, 10000),
            days[1]: _bar(10.5, 10.7, 10.2, 10.3, 105000, 10000),
            days[2]: _bar(10.1, 10.2, 9.9, 10.0, 99000, 10000),
        },
        "000001": {
            days[2]: _bar(19.0, 19.5, 18.8, 19.2, 192000, 10000),
        },
    }
    result = simulate_signal_replay(
        signals, completed_sessions=days, calendar_sessions=days, bars_by_code=bars,
    )
    assert result["trades"][0]["sell_signal_action"] == "VWAP_BREAK"
    assert result["trades"][0]["sell_date"] == days[2]
    assert any(row["event_status"] == "BUY_REJECTED_SIGNAL_DATA" for row in result["events"])


def test_production_trade_reconciliation_recomputes_net_profit_and_quarantines_price():
    rows = [{
        "id": 1, "code": "600000", "buy_date": "2026-10-01 10:00:00", "buy_price": 10.0,
        "buy_amount": 100, "sell_date": "2026-10-02 14:00:00", "sell_price": 11.0,
        "fee": 1.5, "profit": 98.5, "pnl_pct": 0.0985, "status": "CLOSED",
    }]
    bars = {"600000": {
        "2026-10-01": _bar(10.0, 10.2, 9.9, 10.1, 101000, 10000),
        "2026-10-02": _bar(10.8, 11.1, 10.7, 11.0, 110000, 10000),
    }}
    result = reconcile_trade_records(rows, bars_by_code=bars)
    record = result["records"][0]
    assert record["profit_reconciled"] is True
    assert record["pnl_pct_reconciled"] is True
    assert record["buy_price_state"] == "VALID"
    assert record["sell_price_state"] == "VALID"
    assert record["buy_time_in_session"] is True
    assert record["sell_time_in_session"] is True


def test_non_session_signal_is_quarantined_and_not_replayed():
    sessions = ["2026-10-01", "2026-10-02"]
    signals = [{"date": "2026-10-03", "code": "600000", "price": 10.0, "action": "买入"}]
    result = simulate_signal_replay(
        signals, completed_sessions=sessions, calendar_sessions=sessions,
        bars_by_code={"600000": {}},
    )
    assert result["summary"]["non_session_signal_rows"] == 1
    assert result["summary"]["buy_signal_count"] == 0
    assert result["events"][0]["event_status"] == "SIGNAL_QUARANTINED_NON_SESSION_DATE"


def test_recorded_trade_time_flags_out_of_session_events():
    assert _recorded_time_in_session("2026-10-14 09:15:00") is False
    assert _recorded_time_in_session("2026-10-14 13:33:00") is True
    assert _recorded_time_in_session("") is None


def test_zero_share_ledger_row_is_not_counted_as_reconciled_pnl():
    result = reconcile_trade_records([{
        "id": 2, "code": "600000", "buy_date": "2026-10-01 10:00:00", "buy_price": 10.0,
        "buy_amount": 0, "sell_date": "2026-10-02 14:00:00", "sell_price": 11.0,
        "fee": 0.0, "profit": 0.0, "pnl_pct": 0.0, "status": "CLOSED",
    }], bars_by_code={"600000": {
        "2026-10-01": _bar(10.0, 10.2, 9.9, 10.1, 101000, 10000),
        "2026-10-02": _bar(10.8, 11.1, 10.7, 11.0, 110000, 10000),
    }})
    assert result["summary"]["invalid_share_count"] == 1
    assert result["summary"]["pnl_input_quarantine_count"] == 1
    assert result["summary"].get("profit_reconciled_count", 0) == 0


def test_fast_tdx_day_reader_decodes_amount_as_float(tmp_path):
    from JSONData.tdx_data_Day import read_tdx_day_fast

    source = tmp_path / "fixture.day"
    source.write_bytes(struct.pack("<IIIIIfII", 20261013, 1000, 1100, 900, 1050, 100000.0, 10000, 0))
    frame = read_tdx_day_fast(str(source), 1)
    assert float(frame.iloc[0]["amount"]) == pytest.approx(100000.0)
    assert float(frame.iloc[0]["amount"]) / float(frame.iloc[0]["vol"]) == pytest.approx(10.0)
