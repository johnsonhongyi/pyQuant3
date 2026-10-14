"""Read-only production SQLite/TDX ingestion audit for bounded 30-session IPO tests."""

from __future__ import annotations

from sys_utils import safe_resolve_path

import math
import sqlite3
import time
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SESSION_COUNT = 30
MAX_SOURCE_ROWS = 200_000
MAX_CODES = 8_000
TDX_BAR_LIMIT = 1_200


def normalize_code(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().split(".", 1)[0]
    if not text.isdigit() or not 1 <= len(text) <= 6:
        return None
    return text.zfill(6)


def classify_daily_bar(bar: Mapping[str, Any] | None) -> str:
    if not isinstance(bar, Mapping):
        return "MISSING_DAILY_BAR"
    values: dict[str, float] = {}
    for key in ("open", "high", "low", "close"):
        value = bar.get(key)
        if isinstance(value, bool):
            return "INVALID_DAILY_BAR"
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return "INVALID_DAILY_BAR"
        if not math.isfinite(number) or number <= 0:
            return "INVALID_DAILY_BAR"
        values[key] = number
    if not (values["low"] <= min(values["open"], values["close"])
            <= max(values["open"], values["close"]) <= values["high"]):
        return "INVALID_DAILY_BAR"
    return "VALID"


def classify_price_in_bar(price: Any, bar: Mapping[str, Any] | None) -> str:
    state = classify_daily_bar(bar)
    if state != "VALID":
        return state
    if isinstance(price, bool):
        return "INVALID_PRICE"
    try:
        value = float(price)
    except (TypeError, ValueError, OverflowError):
        return "INVALID_PRICE"
    if not math.isfinite(value) or value <= 0:
        return "INVALID_PRICE"
    if float(bar["low"]) <= value <= float(bar["high"]):
        return "VALID"
    return "PRICE_OUTSIDE_DAILY_RANGE"


def last_trading_sessions(end_day: str, *, count: int = SESSION_COUNT,
                          calendar_reader: Callable[[str, str], Sequence[Any]] | None = None) -> list[str]:
    """Select exact exchange sessions from the local authoritative trading calendar."""
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 250:
        raise ValueError("SESSION_COUNT_INVALID")
    end = date.fromisoformat(str(end_day)[:10])
    start = (end - timedelta(days=max(180, count * 4))).isoformat()
    if calendar_reader is None:
        from JohnsonUtil import commonTips as cct
        calendar_reader = cct.get_trade_days
    values = calendar_reader(start, end.isoformat())
    sessions = sorted({
        (value.date() if isinstance(value, datetime) else value).isoformat()
        if isinstance(value, (date, datetime)) else date.fromisoformat(str(value)[:10]).isoformat()
        for value in values
    })
    sessions = [value for value in sessions if value <= end.isoformat()]
    if len(sessions) < count:
        raise ValueError("TRADING_CALENDAR_HAS_TOO_FEW_SESSIONS")
    return sessions[-count:]


def latest_completed_session(source_day: str, *, now: datetime | None = None,
                             calendar_reader: Callable[[str, str], Sequence[Any]] | None = None) -> str:
    """Clamp a source's last date to the latest session that could have closed."""
    source = date.fromisoformat(str(source_day)[:10])
    from zoneinfo import ZoneInfo

    shanghai = ZoneInfo("Asia/Shanghai")
    if now is None:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
    elif now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("CURRENT_TIME_MUST_BE_TIMEZONE_AWARE")
    else:
        now = now.astimezone(shanghai)
    today = now.date()
    cutoff = today if now.timetz().replace(tzinfo=None) >= time(15, 0) else today - timedelta(days=1)
    if calendar_reader is None:
        from JohnsonUtil import commonTips as cct
        calendar_reader = cct.get_trade_days
    start = (cutoff - timedelta(days=180)).isoformat()
    values = calendar_reader(start, cutoff.isoformat())
    sessions = []
    for value in values:
        if isinstance(value, datetime):
            day = value.date()
        elif isinstance(value, date):
            day = value
        else:
            day = date.fromisoformat(str(value)[:10])
        if day <= cutoff:
            sessions.append(day)
    if not sessions:
        raise ValueError("NO_COMPLETED_TRADING_SESSION")
    return min(source, max(sessions)).isoformat()


def _readonly_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path.name)
    if path.stat().st_size > 1024 * 1024 * 1024:
        raise ValueError("SOURCE_DATABASE_TOO_LARGE")
    connection = sqlite3.connect(safe_resolve_path(path).as_uri() + "?mode=ro", uri=True, timeout=1.0)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _require_columns(connection: sqlite3.Connection, table: str,
                     required: set[str]) -> None:
    found = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
    if not required.issubset(found):
        raise ValueError("SOURCE_SCHEMA_INCOMPLETE:" + table)


def _session_query(connection: sqlite3.Connection, query: str,
                   sessions: Sequence[str]) -> list[tuple[Any, ...]]:
    if not sessions:
        return []
    placeholders = ",".join("?" for _ in sessions)
    rows = connection.execute(query.format(placeholders=placeholders), tuple(sessions)).fetchall()
    if len(rows) > MAX_SOURCE_ROWS:
        raise ValueError("SOURCE_ROW_LIMIT_EXCEEDED")
    return rows


def _read_tdx_bars(code: str, tdx_root: Path, reader: Callable[[str, int], Any],
                   needed_dates: set[str]) -> tuple[dict[str, dict[str, Any]], str]:
    from JohnsonUtil import commonTips as cct

    symbol = cct.code_to_symbol(code)
    if not isinstance(symbol, str) or len(symbol) != 8 or symbol[:2] not in {"sh", "sz", "bj"}:
        return {}, "INVALID_TDX_SYMBOL"
    path = tdx_root / "Vipdoc" / symbol[:2] / "lday" / f"{symbol}.day"
    try:
        path.stat()
    except OSError:
        return {}, "MISSING_RAW_FILE"
    for attempt in range(2):
        try:
            before = path.stat()
            frame = reader(str(path), TDX_BAR_LIMIT)
            after = path.stat()
            if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                if attempt == 0:
                    time.sleep(0.025)
                    continue
                return {}, "SOURCE_CHANGED_DURING_READ"
            if frame is None or frame.empty:
                return {}, "EMPTY_RAW_FILE"
            result: dict[str, dict[str, Any]] = {}
            for raw_day, row in frame.iterrows():
                day = str(raw_day)[:10]
                if day in needed_dates:
                    result[day] = {key: row.get(key) for key in ("open", "high", "low", "close")}
            return result, "READ"
        except (OSError, ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
            if attempt == 0:
                time.sleep(0.025)
                continue
            return {}, "RAW_READ_ERROR:" + type(exc).__name__
    return {}, "RAW_READ_ERROR"


def _audit_window(
    *, name: str, sessions: list[str], trade_db: sqlite3.Connection,
    signal_db: sqlite3.Connection, pulse_db: sqlite3.Connection | None,
    tdx_root: Path, bar_reader: Callable[[str, int], Any],
) -> dict[str, Any]:
    placeholders = ",".join("?" for _ in sessions)
    signal_rows = _session_query(
        trade_db,
        "SELECT code, date, price, action FROM signal_history WHERE date IN ({placeholders})",
        sessions,
    )
    trade_rows = _session_query(
        trade_db,
        "SELECT code, substr(buy_date,1,10), buy_price, substr(COALESCE(sell_date,''),1,10), "
        "sell_price, status, profit, pnl_pct FROM trade_records "
        "WHERE substr(buy_date,1,10) IN ({placeholders})",
        sessions,
    )
    signal_messages = _session_query(
        signal_db,
        "SELECT code, substr(event_key,1,10) FROM signal_message "
        "WHERE substr(event_key,1,10) IN ({placeholders})",
        sessions,
    )
    follow_queue = _session_query(
        signal_db,
        "SELECT code, substr(detected_date,1,10) FROM follow_queue "
        "WHERE substr(detected_date,1,10) IN ({placeholders})",
        sessions,
    )
    mock_trades = _session_query(
        signal_db,
        "SELECT code, date FROM mock_trade_log WHERE date IN ({placeholders})",
        sessions,
    )

    signal_keys: set[tuple[str, str]] = set()
    codes: set[str] = set()
    signal_reasons: dict[str, int] = {}
    normalized_signals: list[tuple[str | None, str, Any]] = []
    for code_raw, day_raw, price, _action in signal_rows:
        code = normalize_code(code_raw)
        day = str(day_raw or "")[:10]
        normalized_signals.append((code, day, price))
        if code:
            codes.add(code)
            if day:
                signal_keys.add((code, day))

    normalized_trades: list[tuple[str | None, str, Any, str, Any, str, Any, Any]] = []
    for code_raw, buy_day, buy_price, sell_day, sell_price, status, profit, pnl_pct in trade_rows:
        code = normalize_code(code_raw)
        normalized_trades.append((code, str(buy_day or "")[:10], buy_price,
                                  str(sell_day or "")[:10], sell_price,
                                  str(status or "").upper(), profit, pnl_pct))
        if code:
            codes.add(code)

    signal_message_keys = {
        (code, day) for code_raw, day_raw in signal_messages
        if (code := normalize_code(code_raw)) and (day := str(day_raw or "")[:10])
    }
    for source_rows in (follow_queue, mock_trades):
        for code_raw, _day in source_rows:
            code = normalize_code(code_raw)
            if code:
                codes.add(code)
    if len(codes) > MAX_CODES:
        raise ValueError("SOURCE_CODE_LIMIT_EXCEEDED")

    latest_sell_day = max((row[3] for row in normalized_trades if row[3]), default="")
    needed_dates = set(sessions)
    needed_dates.update(row[3] for row in normalized_trades if row[3])
    tdx_bars: dict[str, dict[str, dict[str, Any]]] = {}
    file_states: dict[str, int] = {}
    for code in sorted(codes):
        bars, state = _read_tdx_bars(code, tdx_root, bar_reader, needed_dates)
        tdx_bars[code] = bars
        file_states[state] = file_states.get(state, 0) + 1

    for code, day, price in normalized_signals:
        if not code:
            reason = "INVALID_CODE"
        elif not math.isfinite(_as_number(price)) or _as_number(price) <= 0:
            reason = "INVALID_PRICE"
        else:
            reason = classify_price_in_bar(price, tdx_bars.get(code, {}).get(day))
        if reason != "VALID":
            signal_reasons[reason] = signal_reasons.get(reason, 0) + 1

    closed = 0
    valid_closed = 0
    trade_issues: dict[str, int] = {}
    signal_history_matches = 0
    signal_message_matches = 0
    buy_bar_matches = 0
    sell_bar_matches = 0
    for code, buy_day, buy_price, sell_day, sell_price, status, profit, pnl_pct in normalized_trades:
        if status != "CLOSED":
            continue
        closed += 1
        issues: set[str] = set()
        if not code:
            issues.add("INVALID_CODE")
        if not buy_day or not math.isfinite(_as_number(buy_price)) or _as_number(buy_price) <= 0:
            issues.add("INVALID_BUY_FIELDS")
        if not sell_day or not math.isfinite(_as_number(sell_price)) or _as_number(sell_price) <= 0:
            issues.add("INVALID_SELL_FIELDS")
        if not math.isfinite(_as_number(profit)) or not math.isfinite(_as_number(pnl_pct)):
            issues.add("INVALID_PNL_FIELDS")
        if code and (code, buy_day) in signal_keys:
            signal_history_matches += 1
        else:
            issues.add("NO_SAME_DAY_SIGNAL_HISTORY")
        if code and (code, buy_day) in signal_message_keys:
            signal_message_matches += 1
        buy_bar = tdx_bars.get(code or "", {}).get(buy_day)
        buy_state = classify_price_in_bar(buy_price, buy_bar)
        if buy_state == "VALID":
            buy_bar_matches += 1
        else:
            issues.add("BUY_" + buy_state)
        sell_bar = tdx_bars.get(code or "", {}).get(sell_day)
        sell_state = classify_price_in_bar(sell_price, sell_bar)
        if sell_state == "VALID":
            sell_bar_matches += 1
        else:
            issues.add("SELL_" + sell_state)
        if not issues:
            valid_closed += 1
        for issue in issues:
            trade_issues[issue] = trade_issues.get(issue, 0) + 1

    pulse = {"daily_stocks_rows": 0, "daily_stocks_days": 0,
             "daily_sentiment_rows": 0, "daily_sentiment_days": 0}
    if pulse_db is not None:
        pulse["daily_stocks_rows"], pulse["daily_stocks_days"] = pulse_db.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT date) FROM daily_stocks WHERE date IN ({placeholders})",
            sessions,
        ).fetchone()
        pulse["daily_sentiment_rows"], pulse["daily_sentiment_days"] = pulse_db.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT date) FROM daily_sentiment WHERE date IN ({placeholders})",
            sessions,
        ).fetchone()
    bar_rows = sum(sum(day in bars for day in sessions) for bars in tdx_bars.values())
    signal_count = len(normalized_signals)
    trade_status_counts: dict[str, int] = {}
    for row in normalized_trades:
        trade_status_counts[row[5]] = trade_status_counts.get(row[5], 0) + 1
    return {
        "name": name, "start_date": sessions[0], "end_date": sessions[-1],
        "calendar_session_count": len(sessions),
        "signal_history": {
            "row_count": signal_count,
            "valid_same_day_bar_count": signal_count - sum(signal_reasons.values()),
            "quarantined_count": sum(signal_reasons.values()),
            "quarantine_reasons": signal_reasons,
        },
        "signal_strategy": {
            "signal_message_count": len(signal_messages),
            "signal_message_days": len({str(row[1])[:10] for row in signal_messages}),
            "follow_queue_count": len(follow_queue), "mock_trade_count": len(mock_trades),
        },
        "trade_records": {
            "row_count": len(normalized_trades), "status_counts": trade_status_counts,
            "closed_count": closed, "fully_validated_closed_count": valid_closed,
            "same_day_signal_history_matches": signal_history_matches,
            "same_day_signal_message_matches": signal_message_matches,
            "buy_price_bar_matches": buy_bar_matches, "sell_price_bar_matches": sell_bar_matches,
            "issues": trade_issues,
        },
        "daily_bars": {
            "code_count": len(codes), "file_states": file_states,
            "bar_rows_on_test_sessions": bar_rows,
            "expected_code_session_slots": len(codes) * len(sessions),
            "sell_bar_check_end_date": latest_sell_day or None,
            "source": "local TDX raw Vipdoc .day files",
        },
        "market_pulse": pulse,
    }


def _as_number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return math.nan


def collect_production_ingest_report(root: str | Path) -> dict[str, Any]:
    """Audit recent signal sessions and the latest 30-session closed-trade cohort."""
    base = safe_resolve_path(Path(root))
    trade_path = base / "trading_signals.db"
    signal_path = base / "signal_strategy.db"
    pulse_path = base / "market_pulse.db"
    from JohnsonUtil import commonTips as cct
    from JSONData import tdx_data_Day as tdd

    report: dict[str, Any] = {
        "schema_version": "ipo.production-ingest-test.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "UNREADY", "source_access": "READ_ONLY",
        "production_database_modified": False, "learning_database_modified": False,
        "training_performed": False, "model_promoted": False, "order_submitted": False,
        "windows": {}, "data_gaps": [],
    }
    with ExitStack() as stack:
        trade_db = stack.enter_context(_connection_context(trade_path))
        signal_db = stack.enter_context(_connection_context(signal_path))
        pulse_db = stack.enter_context(_connection_context(pulse_path)) if pulse_path.is_file() else None
        _require_columns(trade_db, "signal_history", {"code", "date", "price", "action"})
        _require_columns(trade_db, "trade_records", {
            "code", "buy_date", "buy_price", "sell_date", "sell_price", "status", "profit", "pnl_pct",
        })
        _require_columns(signal_db, "signal_message", {"code", "event_key", "signal_type"})
        _require_columns(signal_db, "follow_queue", {"code", "detected_date"})
        _require_columns(signal_db, "mock_trade_log", {"code", "date"})
        if pulse_db is not None:
            _require_columns(pulse_db, "daily_stocks", {"date", "code"})
            _require_columns(pulse_db, "daily_sentiment", {"date"})

        latest_signal_day = trade_db.execute(
            "SELECT MAX(date) FROM signal_history WHERE date IS NOT NULL"
        ).fetchone()[0]
        latest_trade_day = trade_db.execute(
            "SELECT MAX(substr(buy_date,1,10)) FROM trade_records WHERE status='CLOSED' AND buy_date IS NOT NULL"
        ).fetchone()[0]
        if not latest_signal_day or not latest_trade_day:
            raise ValueError("PRODUCTION_SOURCE_HAS_NO_SIGNAL_OR_CLOSED_TRADE_DATE")
        recent_anchor = latest_completed_session(str(latest_signal_day), calendar_reader=cct.get_trade_days)
        trade_anchor = latest_completed_session(str(latest_trade_day), calendar_reader=cct.get_trade_days)
        recent_sessions = last_trading_sessions(recent_anchor, calendar_reader=cct.get_trade_days)
        trade_sessions = last_trading_sessions(trade_anchor, calendar_reader=cct.get_trade_days)
        reader = tdd.read_tdx_day_fast
        tdx_root = safe_resolve_path(Path(tdd.get_tdx_dir()))
        report["windows"] = {
            "latest_signal_30_sessions": _audit_window(
                name="latest_signal_30_sessions", sessions=recent_sessions,
                trade_db=trade_db, signal_db=signal_db, pulse_db=pulse_db,
                tdx_root=tdx_root, bar_reader=reader,
            ),
            "latest_closed_trade_30_sessions": _audit_window(
                name="latest_closed_trade_30_sessions", sessions=trade_sessions,
                trade_db=trade_db, signal_db=signal_db, pulse_db=pulse_db,
                tdx_root=tdx_root, bar_reader=reader,
            ),
        }

    recent = report["windows"]["latest_signal_30_sessions"]
    history = report["windows"]["latest_closed_trade_30_sessions"]
    history_trades = history["trade_records"]
    history_pass = (
        history["calendar_session_count"] == SESSION_COUNT
        and history_trades["closed_count"] > 0
        and history_trades["fully_validated_closed_count"] == history_trades["closed_count"]
    )
    recent_pass = recent["calendar_session_count"] == SESSION_COUNT and recent["signal_history"]["row_count"] > 0
    if not history_pass or not recent_pass:
        report["status"] = "INCOMPLETE"
    elif (recent["trade_records"]["closed_count"] == 0
          or recent["signal_history"]["quarantined_count"]
          or history["signal_history"]["quarantined_count"]):
        report["status"] = "PASS_WITH_DATA_GAPS"
    else:
        report["status"] = "PASS"
    if recent["trade_records"]["closed_count"] == 0:
        report["data_gaps"].append("最近30个完整交易日没有平仓成交记录；实际成交闭环由最近可用的成交历史30日窗口验证")
    if recent["signal_history"]["quarantined_count"] or history["signal_history"]["quarantined_count"]:
        report["data_gaps"].append("部分信号价格缺失原始日线或不在当日OHLC区间；已隔离计数，不进入有效接入样本")
    if pulse_db is None or recent["market_pulse"]["daily_stocks_days"] < SESSION_COUNT:
        report["data_gaps"].append("market_pulse日线横截面覆盖不足30个交易日；原始个股日线另由TDX .day验证")
    if history_trades["same_day_signal_message_matches"] < history_trades["closed_count"]:
        report["data_gaps"].append("部分交易在 signal_strategy.signal_message 中无同日代码事件；以 trading_signals.signal_history 独立校验，不伪造事件关联")
    report["learning_effect_evaluation"] = "NOT_RUN_MISSING_POINT_IN_TIME_41_FIELD_SNAPSHOTS_AND_REVIEWED_MODEL_RESPONSES"
    return report


@contextmanager
def _connection_context(path: Path):
    connection = _readonly_connection(path)
    try:
        yield connection
    finally:
        connection.close()
