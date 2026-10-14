from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from ats.llm.production_ingest_audit import (
    _readonly_connection,
    classify_daily_bar,
    classify_price_in_bar,
    collect_production_ingest_report,
    latest_completed_session,
    normalize_code,
)


def test_code_and_raw_ohlc_validation_quarantines_bad_values():
    assert normalize_code("123") == "000123"
    assert normalize_code("000001.SZ") == "000001"
    assert normalize_code(True) is None
    assert classify_daily_bar({"open": 10, "high": 12, "low": 9, "close": 11}) == "VALID"
    assert classify_daily_bar({"open": 10, "high": 9, "low": 8, "close": 11}) == "INVALID_DAILY_BAR"
    assert classify_price_in_bar(11, {"open": 10, "high": 12, "low": 9, "close": 11}) == "VALID"
    assert classify_price_in_bar(12.1, {"open": 10, "high": 12, "low": 9, "close": 11}) == "PRICE_OUTSIDE_DAILY_RANGE"
    assert classify_price_in_bar(float("nan"), {"open": 10, "high": 12, "low": 9, "close": 11}) == "INVALID_PRICE"


def test_source_sqlite_connection_is_read_only(tmp_path):
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (value INTEGER)")
    connection_ro = _readonly_connection(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection_ro.execute("INSERT INTO sample VALUES (1)")
    finally:
        connection_ro.close()


def test_partial_current_session_is_excluded_from_completed_window():
    from zoneinfo import ZoneInfo

    values = [date(2026, 10, 13), date(2026, 10, 14)]
    now = datetime(2026, 10, 14, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert latest_completed_session(
        "2026-10-14", now=now,
        calendar_reader=lambda _start, _end: values,
    ) == "2026-10-13"


def test_30_session_ingest_joins_trade_signal_and_raw_daily_prices(tmp_path, monkeypatch):
    sessions = [(date(2026, 7, 1) + timedelta(days=index)).isoformat() for index in range(60)]
    trade_day = sessions[-10]
    sell_day = sessions[-8]
    trade_db = tmp_path / "trading_signals.db"
    with sqlite3.connect(trade_db) as connection:
        connection.execute("CREATE TABLE signal_history (code TEXT, date TEXT, price REAL, action TEXT)")
        connection.execute("CREATE TABLE trade_records (code TEXT, buy_date TEXT, buy_price REAL, sell_date TEXT, sell_price REAL, status TEXT, profit REAL, pnl_pct REAL)")
        connection.execute("INSERT INTO signal_history VALUES ('1', ?, 10.5, 'BUY')", (trade_day,))
        connection.execute("INSERT INTO trade_records VALUES ('1', ?, 10.5, ?, 11.0, 'CLOSED', 50.0, 4.76)",
                           (trade_day + " 10:00:00", sell_day + " 14:00:00"))

    signal_db = tmp_path / "signal_strategy.db"
    with sqlite3.connect(signal_db) as connection:
        connection.execute("CREATE TABLE signal_message (code TEXT, event_key TEXT, signal_type TEXT)")
        connection.execute("CREATE TABLE follow_queue (code TEXT, detected_date TEXT)")
        connection.execute("CREATE TABLE mock_trade_log (code TEXT, date TEXT)")
        connection.execute("INSERT INTO signal_message VALUES ('1', ?, 'BUY')",
                           (f"{trade_day}|000001|breakout|live_strategy",))
        connection.execute("INSERT INTO follow_queue VALUES ('1', ?)", (trade_day,))
        connection.execute("INSERT INTO mock_trade_log VALUES ('1', ?)", (trade_day,))

    pulse_db = tmp_path / "market_pulse.db"
    with sqlite3.connect(pulse_db) as connection:
        connection.execute("CREATE TABLE daily_stocks (date TEXT, code TEXT)")
        connection.execute("CREATE TABLE daily_sentiment (date TEXT)")
        connection.execute("INSERT INTO daily_stocks VALUES (?, '000001')", (trade_day,))
        connection.execute("INSERT INTO daily_sentiment VALUES (?)", (trade_day,))

    tdx_root = tmp_path / "tdx"
    raw_file = tdx_root / "Vipdoc" / "sz" / "lday" / "sz000001.day"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"fixture")
    bars = pd.DataFrame(
        [{"open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0} for _ in sessions],
        index=sessions,
    )

    from JohnsonUtil import commonTips as cct
    from JSONData import tdx_data_Day as tdd

    monkeypatch.setattr(cct, "get_trade_days", lambda _start, end: [day for day in sessions if day <= end])
    monkeypatch.setattr(cct, "code_to_symbol", lambda _code: "sz000001")
    monkeypatch.setattr(tdd, "get_tdx_dir", lambda: str(tdx_root))
    monkeypatch.setattr(tdd, "read_tdx_day_fast", lambda _path, _limit: bars)

    before = trade_db.stat().st_mtime_ns
    report = collect_production_ingest_report(tmp_path)
    assert report["windows"]["latest_closed_trade_30_sessions"]["calendar_session_count"] == 30
    trade_result = report["windows"]["latest_closed_trade_30_sessions"]["trade_records"]
    assert trade_result["closed_count"] == 1
    assert trade_result["fully_validated_closed_count"] == 1
    assert trade_result["same_day_signal_history_matches"] == 1
    assert trade_result["same_day_signal_message_matches"] == 1
    assert trade_result["buy_price_bar_matches"] == 1
    assert trade_result["sell_price_bar_matches"] == 1
    assert trade_db.stat().st_mtime_ns == before
