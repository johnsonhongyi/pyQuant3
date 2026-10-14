"""Read-only production-data VWAP paper replay and transaction reconciliation."""

from __future__ import annotations

from sys_utils import safe_resolve_path

import csv
import hashlib
import json
import math
import os
import sqlite3
from contextlib import closing
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from ats.llm.production_ingest_audit import (
    MAX_CODES,
    MAX_SOURCE_ROWS,
    _readonly_connection,
    classify_daily_bar,
    classify_price_in_bar,
    latest_completed_session,
    normalize_code,
)


SESSION_COUNT = 30
TDX_BAR_LIMIT = 1200
MAX_TDX_FILE_BYTES = 16 * 1024 * 1024
BUY_ACTION = "买入"
EXIT_ACTIONS = frozenset({
    "卖出", "强制清仓", "回撤止损", "预警止损", "止损", "目标止盈", "趋势崩塌", "趋势止损",
})
PARTIAL_EXIT_ACTIONS = frozenset({"振幅减仓"})


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def daily_vwap(bar: Mapping[str, Any]) -> tuple[float | None, str]:
    """TDX raw daily amount is yuan and daily volume is shares: amount / volume."""
    state = classify_daily_bar(bar)
    if state != "VALID":
        return None, state
    amount = _finite_number(bar.get("amount"))
    volume = _finite_number(bar.get("vol", bar.get("volume")))
    if amount is None or volume is None or amount <= 0 or volume <= 0:
        return None, "INVALID_AMOUNT_OR_VOLUME"
    value = amount / volume
    if not math.isfinite(value) or not (float(bar["low"]) - 0.01 <= value <= float(bar["high"]) + 0.01):
        return None, "VWAP_OUTSIDE_DAILY_RANGE"
    return value, "VALID"


def _default_bar_loader(
    code: str, tdx_root: Path, start_day: str, end_day: str,
) -> tuple[dict[str, dict[str, Any]], str]:
    from JohnsonUtil import commonTips as cct
    from JSONData import tdx_data_Day as tdd
    import numpy as np

    symbol = cct.code_to_symbol(code)
    path = tdx_root / "Vipdoc" / symbol[:2] / "lday" / f"{symbol}.day"
    for attempt in range(2):
        try:
            before = path.stat()
            if before.st_size <= 0 or before.st_size > MAX_TDX_FILE_BYTES or before.st_size % 32:
                return {}, "RAW_FILE_SIZE_INVALID"
            records = np.fromfile(path, dtype=tdd.DAY_DTYPE)[-TDX_BAR_LIMIT:]
            after = path.stat()
            if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                if attempt == 0:
                    continue
                return {}, "SOURCE_CHANGED_DURING_READ"
            if records.size == 0:
                return {}, "EMPTY_RAW_FILE"
            result: dict[str, dict[str, Any]] = {}
            start_int = int(start_day.replace("-", ""))
            end_int = int(end_day.replace("-", ""))
            for row in records:
                raw_day = int(row["date"])
                if raw_day < start_int or raw_day > end_int:
                    continue
                day = f"{raw_day // 10000:04d}-{raw_day // 100 % 100:02d}-{raw_day % 100:02d}"
                bar = {
                    "open": int(row["open"]) / 100.0,
                    "high": int(row["high"]) / 100.0,
                    "low": int(row["low"]) / 100.0,
                    "close": int(row["close"]) / 100.0,
                    "amount": float(row["amount"]),
                    "vol": int(row["vol"]),
                }
                vwap, vwap_state = daily_vwap(bar)
                bar["vwap"] = vwap
                bar["vwap_state"] = vwap_state
                result[day] = bar
            return result, "READ"
        except FileNotFoundError:
            return {}, "RAW_FILE_MISSING"
        except (OSError, ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
            if attempt == 0:
                continue
            return {}, "RAW_READ_ERROR:" + type(exc).__name__
    return {}, "RAW_READ_ERROR"


def _session_strings(values: Sequence[Any]) -> list[str]:
    sessions: set[str] = set()
    for value in values:
        if isinstance(value, datetime):
            day = value.date()
        elif isinstance(value, date):
            day = value
        else:
            day = date.fromisoformat(str(value)[:10])
        sessions.add(day.isoformat())
    return sorted(sessions)


def _signal_message_map(connection: sqlite3.Connection, start: str, end: str) -> dict[tuple[str, str], dict[str, Any]]:
    rows = connection.execute(
        "SELECT code, substr(event_key,1,10), signal_type FROM signal_message "
        "WHERE substr(event_key,1,10) BETWEEN ? AND ? LIMIT ?",
        (start, end, MAX_SOURCE_ROWS + 1),
    ).fetchall()
    if len(rows) > MAX_SOURCE_ROWS:
        raise ValueError("SIGNAL_MESSAGE_ROW_LIMIT_EXCEEDED")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for code_raw, day_raw, signal_type in rows:
        code = normalize_code(code_raw)
        day = str(day_raw or "")[:10]
        if not code or not day:
            continue
        item = result.setdefault((code, day), {"count": 0, "types": set()})
        item["count"] += 1
        if signal_type:
            item["types"].add(str(signal_type))
    return result


def _signal_quality(row: Mapping[str, Any], bar: Mapping[str, Any] | None) -> str:
    if bar is None:
        return "MISSING_DAILY_BAR"
    return classify_price_in_bar(row.get("price"), bar)


def _lot_size(code: str) -> int:
    return 200 if code.startswith(("688", "689")) else 100


def _recorded_time_in_session(value: Any) -> bool | None:
    text = str(value or "")
    if len(text) < 19 or text[10] not in {" ", "T"}:
        return None
    try:
        hour, minute, second = (int(part) for part in text[11:19].split(":", 2))
        recorded = (hour, minute, second)
    except (ValueError, TypeError):
        return None
    return (9, 30, 0) <= recorded <= (11, 30, 0) or (13, 0, 0) <= recorded <= (15, 0, 0)


def simulate_signal_replay(
    signal_rows: Sequence[Mapping[str, Any]], *,
    completed_sessions: Sequence[str], calendar_sessions: Sequence[str],
    bars_by_code: Mapping[str, Mapping[str, Mapping[str, Any]]],
    signal_messages: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay date-only signals at next-session opens; orders remain paper-only."""
    completed = sorted(set(completed_sessions))
    all_sessions = sorted(set(calendar_sessions))
    next_session = {day: all_sessions[index + 1] for index, day in enumerate(all_sessions[:-1])}
    index_by_day = {day: index for index, day in enumerate(completed)}
    grouped: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    quality_by_key: dict[tuple[str, str], str] = {}
    quality_counts: Counter[str] = Counter()
    pre_events: list[dict[str, Any]] = []
    for row in signal_rows:
        code = normalize_code(row.get("code"))
        day = str(row.get("date") or "")[:10]
        if not code:
            quality_counts["INVALID_CODE"] += 1
            pre_events.append({
                "date": day, "code": "", "action": row.get("action", ""),
                "signal_price": row.get("price"), "signal_quality": "INVALID_CODE",
                "event_status": "SIGNAL_QUARANTINED_INVALID_CODE", "side": "",
                "related_signal_date": "", "execution_price": None,
                "signal_message_count": 0, "signal_message_types": "", "detail": "code normalization failed",
            })
            continue
        if day not in index_by_day:
            quality_counts["NON_SESSION_SIGNAL_DATE"] += 1
            message = (signal_messages or {}).get((code, day), {})
            pre_events.append({
                "date": day, "code": code, "action": row.get("action", ""),
                "signal_price": row.get("price"), "signal_quality": "NON_SESSION_SIGNAL_DATE",
                "event_status": "SIGNAL_QUARANTINED_NON_SESSION_DATE", "side": "",
                "related_signal_date": "", "execution_price": None,
                "signal_message_count": message.get("count", 0),
                "signal_message_types": ",".join(sorted(message.get("types", ()))),
                "detail": "date is outside the completed exchange-session calendar",
            })
            continue
        bar = bars_by_code.get(code, {}).get(day)
        quality = _signal_quality(row, bar)
        quality_counts[quality] += 1
        if day in grouped[code]:
            quality_by_key[(code, day)] = "AMBIGUOUS_SAME_DAY_SIGNALS"
            continue
        quality_by_key[(code, day)] = quality
        grouped[code][day] = row

    events: list[dict[str, Any]] = pre_events
    trades: list[dict[str, Any]] = []
    open_positions: list[dict[str, Any]] = []
    replay_counts: Counter[str] = Counter()

    def emit(code: str, day: str, row: Mapping[str, Any] | None, status: str,
             *, source_day: str | None = None, side: str = "", price: Any = None,
             detail: str = "") -> None:
        source = row or {}
        message = (signal_messages or {}).get((code, day), {})
        events.append({
            "date": day, "code": code, "action": source.get("action", ""),
            "signal_price": source.get("price"), "signal_quality": quality_by_key.get((code, day), ""),
            "event_status": status, "side": side, "related_signal_date": source_day or "",
            "execution_price": price, "signal_message_count": message.get("count", 0),
            "signal_message_types": ",".join(sorted(message.get("types", ()))), "detail": detail,
        })
        replay_counts[status] += 1

    for code in sorted(grouped):
        code_bars = bars_by_code.get(code, {})
        current: dict[str, Any] | None = None
        pending: dict[str, Any] | None = None
        last_bar: Mapping[str, Any] | None = None
        last_bar_day = ""
        for day in completed:
            bar = code_bars.get(day)
            signal = grouped[code].get(day)
            if bar is not None:
                last_bar, last_bar_day = bar, day

            # Fill an entry only on the next exchange session. A missed open expires.
            if pending and pending["side"] == "BUY" and day == pending.get("target_day"):
                open_price = _finite_number((bar or {}).get("open"))
                volume = _finite_number((bar or {}).get("vol", (bar or {}).get("volume")))
                if classify_daily_bar(bar) == "VALID" and open_price and volume and volume > 0:
                    current = {
                        "code": code, "shares": _lot_size(code), "buy_signal_day": pending["signal_day"],
                        "buy_signal_action": pending["action"], "buy_signal_price": pending["signal_price"],
                        "buy_signal_quality": quality_by_key.get((code, pending["signal_day"]), ""),
                        "buy_signal_close": pending["signal_close"], "buy_signal_vwap": pending["signal_vwap"],
                        "buy_date": day, "buy_price": open_price, "buy_vwap": (bar or {}).get("vwap"),
                        "buy_open_gap_pct": round((open_price / pending["signal_close"] - 1.0) * 100.0, 6)
                        if pending["signal_close"] else None,
                    }
                    emit(code, day, None, "BUY_FILLED_NEXT_OPEN", source_day=pending["signal_day"],
                         side="BUY", price=open_price, detail="DAILY_OPEN_PROXY; paper only")
                else:
                    emit(code, day, None, "BUY_UNFILLED_NEXT_OPEN", source_day=pending["signal_day"],
                         side="BUY", detail="missing/invalid/zero-volume execution bar")
                pending = None

            # A sell order retries while the stock has no tradable daily bar; T+1 is enforced.
            if pending and pending["side"] == "SELL" and day >= pending.get("target_day", day):
                open_price = _finite_number((bar or {}).get("open"))
                volume = _finite_number((bar or {}).get("vol", (bar or {}).get("volume")))
                if current and day > current["buy_date"] and classify_daily_bar(bar) == "VALID" and open_price and volume and volume > 0:
                    trade = dict(current)
                    trade.update({
                        "status": "CLOSED", "sell_signal_day": pending["signal_day"],
                        "sell_signal_action": pending["action"], "sell_signal_close": pending["signal_close"],
                        "sell_signal_price": pending["signal_price"],
                        "sell_signal_quality": quality_by_key.get((code, pending["signal_day"]), ""),
                        "sell_signal_vwap": pending["signal_vwap"], "sell_date": day, "sell_price": open_price,
                        "sell_vwap": (bar or {}).get("vwap"), "gross_pnl": round((open_price - current["buy_price"]) * current["shares"], 4),
                        "gross_return_pct": round((open_price / current["buy_price"] - 1.0) * 100.0, 6),
                        "sell_open_gap_pct": round((open_price / pending["signal_close"] - 1.0) * 100.0, 6)
                        if pending["signal_close"] else None,
                        "signal_day_close_change_pct": round(
                            (pending["signal_close"] / current["buy_signal_close"] - 1.0) * 100.0, 6
                        ) if pending["signal_close"] and current["buy_signal_close"] else None,
                        "holding_sessions": index_by_day[day] - index_by_day[current["buy_date"]],
                        "t_plus_one_valid": True, "fee_mode": "EXCLUDED_UNCONFIGURED",
                    })
                    trades.append(trade)
                    from trading_kernel.execution.paper_fees import paper_fee
                    trade["buy_fee"] = paper_fee(current["buy_price"] * current["shares"], "BUY")
                    trade["sell_fee"] = paper_fee(open_price * current["shares"], "SELL")
                    trade["total_fee"] = round(trade["buy_fee"] + trade["sell_fee"], 2)
                    trade["net_pnl"] = round(trade["gross_pnl"] - trade["total_fee"], 4)
                    trade["fee_mode"] = "BOTH_SIDES_0.0000754_SELL_PLUS_5_PER_FILL"
                    emit(code, day, None, "SELL_FILLED_NEXT_OPEN", source_day=pending["signal_day"],
                         side="SELL", price=open_price, detail="DAILY_OPEN_PROXY; paper only")
                    current = None
                    pending = None
                elif current:
                    emit(code, day, None, "SELL_DEFERRED_NO_TRADABLE_BAR", source_day=pending["signal_day"],
                         side="SELL", detail="exit remains pending; no tradable OHLCV")

            if signal is not None:
                action = str(signal.get("action") or "").strip()
                quality = quality_by_key.get((code, day), "")
                vwap = (bar or {}).get("vwap")
                close = _finite_number((bar or {}).get("close"))
                if quality != "VALID":
                    emit(code, day, signal,
                         "BUY_REJECTED_SIGNAL_DATA" if action == BUY_ACTION else "SIGNAL_QUARANTINED_DATA",
                         side="BUY" if action == BUY_ACTION else "", detail=quality)
                elif pending and pending["side"] == "SELL":
                    emit(code, day, signal, "SIGNAL_WAITING_FOR_EXIT_FILL", side="SELL")
                elif action == BUY_ACTION:
                    if current:
                        emit(code, day, signal, "BUY_IGNORED_ALREADY_LONG", side="BUY")
                    elif quality != "VALID":
                        emit(code, day, signal, "BUY_REJECTED_SIGNAL_DATA", side="BUY", detail=quality)
                    elif close is None or vwap is None:
                        emit(code, day, signal, "BUY_REJECTED_VWAP_UNAVAILABLE", side="BUY",
                             detail=str((bar or {}).get("vwap_state", "NO_VALID_VWAP")))
                    elif close < float(vwap):
                        emit(code, day, signal, "BUY_REJECTED_CLOSE_BELOW_VWAP", side="BUY")
                    else:
                        target = next_session.get(day)
                        pending = {
                            "side": "BUY", "target_day": target, "signal_day": day, "action": action,
                            "signal_price": signal.get("price"), "signal_close": close, "signal_vwap": vwap,
                        }
                        emit(code, day, signal, "BUY_QUEUED_NEXT_OPEN", side="BUY",
                             detail=f"target={target or 'NEXT_SESSION_AFTER_WINDOW'}")
                elif action in EXIT_ACTIONS:
                    if current and not pending:
                        target = next_session.get(day)
                        pending = {
                            "side": "SELL", "target_day": target, "signal_day": day, "action": action,
                            "signal_price": signal.get("price"), "signal_close": close, "signal_vwap": vwap,
                        }
                        emit(code, day, signal, "SELL_QUEUED_NEXT_OPEN", side="SELL",
                             detail=f"target={target or 'NEXT_SESSION_AFTER_WINDOW'}")
                    elif current:
                        emit(code, day, signal, "SELL_ALREADY_PENDING", side="SELL")
                    else:
                        emit(code, day, signal, "SELL_ORPHAN_NO_POSITION", side="SELL")
                elif action in PARTIAL_EXIT_ACTIONS:
                    emit(code, day, signal, "PARTIAL_EXIT_NOT_MODELED", side="SELL",
                         detail="partial quantity is unavailable; no synthetic full exit")
                else:
                    emit(code, day, signal, "OBSERVED_NONTRADE_ACTION")

            if current and not pending and bar is not None:
                vwap = _finite_number(bar.get("vwap"))
                close = _finite_number(bar.get("close"))
                if vwap is not None and close is not None and close < vwap:
                    target = next_session.get(day)
                    pending = {
                        "side": "SELL", "target_day": target, "signal_day": day,
                        "action": "VWAP_BREAK", "signal_price": close, "signal_close": close,
                        "signal_vwap": vwap,
                    }
                    emit(code, day, None, "VWAP_EXIT_QUEUED_NEXT_OPEN", side="SELL",
                         detail=f"close={close};vwap={vwap};target={target or 'NEXT_SESSION_AFTER_WINDOW'}")

        if pending and pending["side"] == "BUY":
            emit(code, pending["signal_day"], grouped[code].get(pending["signal_day"]),
                 "BUY_PENDING_AFTER_WINDOW", side="BUY", detail=f"target={pending.get('target_day') or 'UNKNOWN'}")
        if current:
            mark = _finite_number((last_bar or {}).get("close"))
            unrealized = ((mark - current["buy_price"]) * current["shares"] - 0.0) if mark is not None else None
            open_row = dict(current)
            open_row.update({
                "status": "OPEN_EXIT_PENDING" if pending and pending["side"] == "SELL" else "OPEN",
                "as_of_date": last_bar_day, "mark_price": mark,
                "unrealized_gross_pnl": round(unrealized, 4) if unrealized is not None else None,
                "pending_exit_signal_day": pending.get("signal_day") if pending and pending["side"] == "SELL" else "",
                "fee_mode": "BOTH_SIDES_0.0000754_SELL_PLUS_5_PER_FILL",
            })
            open_positions.append(open_row)

    buy_signals = sum(
        1 for row in signal_rows if str(row.get("action") or "").strip() == BUY_ACTION
        and str(row.get("date") or "")[:10] in index_by_day
    )
    exit_signals = sum(
        1 for row in signal_rows if str(row.get("action") or "").strip() in EXIT_ACTIONS
        and str(row.get("date") or "")[:10] in index_by_day
    )
    vwap_breaks = replay_counts["VWAP_EXIT_QUEUED_NEXT_OPEN"]
    summary = {
        "signal_rows": len(signal_rows),
        "exchange_session_signal_rows": len(signal_rows) - quality_counts["NON_SESSION_SIGNAL_DATE"] - quality_counts["INVALID_CODE"],
        "non_session_signal_rows": quality_counts["NON_SESSION_SIGNAL_DATE"],
        "valid_signal_price_rows": quality_counts["VALID"],
        "quarantined_signal_rows": sum(count for state, count in quality_counts.items() if state != "VALID"),
        "signal_quality_counts": dict(sorted(quality_counts.items())),
        "ambiguous_signal_day_count": sum(
            state == "AMBIGUOUS_SAME_DAY_SIGNALS" for state in quality_by_key.values()
        ),
        "buy_signal_count": buy_signals, "exit_signal_count": exit_signals,
        "buy_queued_count": replay_counts["BUY_QUEUED_NEXT_OPEN"],
        "buy_filled_count": replay_counts["BUY_FILLED_NEXT_OPEN"],
        "buy_vwap_rejected_count": replay_counts["BUY_REJECTED_CLOSE_BELOW_VWAP"],
        "buy_data_rejected_count": replay_counts["BUY_REJECTED_SIGNAL_DATA"] + replay_counts["BUY_REJECTED_VWAP_UNAVAILABLE"],
        "buy_pending_after_window_count": replay_counts["BUY_PENDING_AFTER_WINDOW"],
        "exit_queued_count": replay_counts["SELL_QUEUED_NEXT_OPEN"] + vwap_breaks,
        "explicit_exit_signal_queued_count": replay_counts["SELL_QUEUED_NEXT_OPEN"],
        "exit_filled_count": replay_counts["SELL_FILLED_NEXT_OPEN"],
        "orphan_exit_signal_count": replay_counts["SELL_ORPHAN_NO_POSITION"],
        "partial_exit_not_modeled_count": replay_counts["PARTIAL_EXIT_NOT_MODELED"],
        "vwap_exit_count": vwap_breaks, "closed_round_trip_count": len(trades),
        "open_position_count": len(open_positions),
        "exit_pending_position_count": sum(1 for row in open_positions if row["status"] == "OPEN_EXIT_PENDING"),
        "gross_pnl_sum": round(sum(float(trade["gross_pnl"]) for trade in trades), 4),
        "winning_trade_count": sum(1 for trade in trades if trade["gross_pnl"] > 0),
        "losing_trade_count": sum(1 for trade in trades if trade["gross_pnl"] < 0),
        "gross_positive_pnl_sum": round(sum(max(float(trade["gross_pnl"]), 0.0) for trade in trades), 4),
        "gross_negative_pnl_sum": round(sum(min(float(trade["gross_pnl"]), 0.0) for trade in trades), 4),
        "average_gross_pnl_per_closed_trade": round(
            sum(float(trade["gross_pnl"]) for trade in trades) / len(trades), 4
        ) if trades else 0.0,
        "win_rate_pct": round(sum(1 for trade in trades if trade["gross_pnl"] > 0) / len(trades) * 100.0, 4)
        if trades else 0.0,
        "fees_included": True, "portfolio_capital_limit_modeled": False,
        "total_fees": round(sum(trade["total_fee"] for trade in trades), 2),
        "net_pnl_sum": round(sum(trade["net_pnl"] for trade in trades), 4),
        "order_submitted": False,
        "event_status_counts": dict(sorted(replay_counts.items())),
    }
    return {"summary": summary, "trades": trades, "open_positions": open_positions, "events": events}


def reconcile_trade_records(
    trade_rows: Sequence[Mapping[str, Any]], *,
    bars_by_code: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in trade_rows:
        code = normalize_code(row.get("code")) or ""
        buy_date = str(row.get("buy_date") or "")[:10]
        sell_date = str(row.get("sell_date") or "")[:10]
        buy_bar = bars_by_code.get(code, {}).get(buy_date)
        sell_bar = bars_by_code.get(code, {}).get(sell_date) if sell_date else None
        buy_price = _finite_number(row.get("buy_price"))
        sell_price = _finite_number(row.get("sell_price"))
        shares = _finite_number(row.get("buy_amount"))
        fee = _finite_number(row.get("fee"))
        status = str(row.get("status") or "").upper()
        buy_time_in_session = _recorded_time_in_session(row.get("buy_date"))
        sell_time_in_session = _recorded_time_in_session(row.get("sell_date"))
        buy_state = classify_price_in_bar(buy_price, buy_bar)
        sell_state = classify_price_in_bar(sell_price, sell_bar) if status == "CLOSED" else "NOT_CLOSED"
        expected_profit = None
        profit_delta = None
        expected_pct = None
        profit_match = None
        pct_match = None
        formula_inputs_valid = bool(
            status == "CLOSED" and buy_price is not None and buy_price > 0
            and sell_price is not None and sell_price > 0
            and shares is not None and shares > 0
            and fee is not None and fee >= 0
        )
        if formula_inputs_valid:
            expected_profit = (sell_price - buy_price) * shares - fee
            stored_profit = _finite_number(row.get("profit"))
            profit_delta = stored_profit - expected_profit if stored_profit is not None else None
            denominator = buy_price * shares
            expected_pct = expected_profit / denominator if denominator > 0 else None
            stored_pct = _finite_number(row.get("pnl_pct"))
            profit_match = profit_delta is not None and abs(profit_delta) <= 0.01
            pct_match = expected_pct is not None and stored_pct is not None and abs(expected_pct - stored_pct) <= 0.0001
        trade_price_return = ((sell_price / buy_price) - 1.0) * 100.0 if formula_inputs_valid else None
        market_close_change = None
        if buy_bar and sell_bar and _finite_number(buy_bar.get("close")) and _finite_number(sell_bar.get("close")):
            market_close_change = (float(sell_bar["close"]) / float(buy_bar["close"]) - 1.0) * 100.0
        mark_day = ""
        mark_price = None
        unrealized_profit = None
        if status == "OPEN" and bars_by_code.get(code):
            mark_day, mark_bar = max(bars_by_code[code].items(), key=lambda item: item[0])
            mark_price = _finite_number(mark_bar.get("close"))
            if (classify_daily_bar(mark_bar) == "VALID" and mark_day >= buy_date
                    and mark_price is not None and buy_price is not None and buy_price > 0
                    and shares is not None and shares > 0 and fee is not None and fee >= 0):
                unrealized_profit = (mark_price - buy_price) * shares - fee
        record = {
            "trade_id": row.get("id"), "code": code, "status": status, "action": row.get("action"),
            "buy_reason": row.get("buy_reason"), "sell_reason": row.get("sell_reason"),
            "buy_date": row.get("buy_date"), "buy_price": buy_price, "shares_from_buy_amount": shares,
            "buy_time_in_session": buy_time_in_session,
            "buy_open": (buy_bar or {}).get("open"), "buy_high": (buy_bar or {}).get("high"),
            "buy_low": (buy_bar or {}).get("low"), "buy_close": (buy_bar or {}).get("close"),
            "buy_vwap": (buy_bar or {}).get("vwap"), "buy_price_state": buy_state,
            "sell_date": row.get("sell_date"), "sell_price": sell_price,
            "sell_time_in_session": sell_time_in_session,
            "sell_open": (sell_bar or {}).get("open"), "sell_high": (sell_bar or {}).get("high"),
            "sell_low": (sell_bar or {}).get("low"), "sell_close": (sell_bar or {}).get("close"),
            "sell_vwap": (sell_bar or {}).get("vwap"), "sell_price_state": sell_state,
            "trade_price_return_pct": round(trade_price_return, 6) if trade_price_return is not None else None,
            "daily_close_change_pct": round(market_close_change, 6) if market_close_change is not None else None,
            "fee": fee, "source_profit": row.get("profit"),
            "fee_input_valid": fee is not None and fee >= 0,
            "recomputed_profit": round(expected_profit, 6) if expected_profit is not None else None,
            "profit_delta": round(profit_delta, 8) if profit_delta is not None else None,
            "profit_reconciled": profit_match, "source_pnl_pct_ratio": row.get("pnl_pct"),
            "recomputed_pnl_pct_ratio": round(expected_pct, 8) if expected_pct is not None else None,
            "pnl_pct_reconciled": pct_match,
            "pnl_formula_input_valid": formula_inputs_valid,
            "mark_date": mark_day, "mark_price": mark_price,
            "unrealized_profit_at_mark": round(unrealized_profit, 6) if unrealized_profit is not None else None,
        }
        records.append(record)
        counts["record_count"] += 1
        if status == "CLOSED":
            counts["closed_count"] += 1
            if formula_inputs_valid:
                counts["valid_pnl_input_count"] += 1
            else:
                counts["pnl_input_quarantine_count"] += 1
            if shares is None or shares <= 0:
                counts["invalid_share_count"] += 1
            if sell_price is None or sell_price <= 0:
                counts["nonpositive_sell_price_count"] += 1
            if buy_price is None or buy_price <= 0:
                counts["nonpositive_buy_price_count"] += 1
            if buy_state == "VALID":
                counts["closed_buy_price_valid_count"] += 1
            if sell_state == "VALID":
                counts["closed_sell_price_valid_count"] += 1
            if profit_match:
                counts["profit_reconciled_count"] += 1
            if pct_match:
                counts["pnl_pct_reconciled_count"] += 1
        else:
            counts["open_or_other_count"] += 1
            if mark_price is not None:
                counts["open_position_marked_count"] += 1
        if buy_state != "VALID":
            counts["buy_price_quarantine_count"] += 1
            counts[f"buy_price_state_{buy_state.lower()}"] += 1
        if status == "CLOSED" and sell_state != "VALID":
            counts["sell_price_quarantine_count"] += 1
            counts[f"sell_price_state_{sell_state.lower()}"] += 1
        if buy_time_in_session is False:
            counts["buy_timestamp_outside_session_count"] += 1
        if status == "CLOSED" and sell_time_in_session is False:
            counts["sell_timestamp_outside_session_count"] += 1
    summary = dict(counts)
    summary.update({
        "price_pair_valid_count": sum(
            1 for row in records if row["status"] == "CLOSED"
            and row["buy_price_state"] == "VALID" and row["sell_price_state"] == "VALID"
        ),
        "profit_formula": "(sell_price - buy_price) * shares_from_buy_amount - fee",
        "shares_field_interpretation": "buy_amount behaves as share count; formula matches source profit",
        "broker_fill_proof_available": False,
        "time_check_window": "09:30-11:30, 13:00-15:00 local exchange time",
        "stored_profit_sum_all_closed_including_quarantined": round(sum(
            float(row["source_profit"]) for row in records
            if row["status"] == "CLOSED" and _finite_number(row["source_profit"]) is not None
        ), 6),
        "stored_profit_sum_on_valid_price_pairs": round(sum(
            float(row["source_profit"]) for row in records
            if row["status"] == "CLOSED" and row["buy_price_state"] == "VALID"
            and row["sell_price_state"] == "VALID" and _finite_number(row["source_profit"]) is not None
        ), 6),
        "valid_pair_source_profit_sum": round(sum(
            float(row["source_profit"]) for row in records
            if row["status"] == "CLOSED" and row["buy_price_state"] == "VALID"
            and row["sell_price_state"] == "VALID" and row["pnl_formula_input_valid"]
            and _finite_number(row["source_profit"]) is not None
        ), 6),
        "open_unrealized_profit_at_mark_sum": round(sum(
            float(row["unrealized_profit_at_mark"]) for row in records
            if _finite_number(row["unrealized_profit_at_mark"]) is not None
        ), 6),
    })
    return {"summary": summary, "records": records}


def collect_production_vwap_trade_replay(
    root: str | Path, *, now: datetime | None = None,
    calendar_reader: Callable[[str, str], Sequence[Any]] | None = None,
    bar_loader: Callable[[str, Path, str, str], tuple[dict[str, dict[str, Any]], str]] | None = None,
) -> dict[str, Any]:
    """Read production DBs and raw TDX day files without modifying any source."""
    from JohnsonUtil import commonTips as cct
    from JSONData import tdx_data_Day as tdd

    base = safe_resolve_path(Path(root))
    calendar_reader = calendar_reader or cct.get_trade_days
    bar_loader = bar_loader or _default_bar_loader
    trade_path = base / "trading_signals.db"
    signal_path = base / "signal_strategy.db"
    tdx_root = safe_resolve_path(Path(tdd.get_tdx_dir()))
    with closing(_readonly_connection(trade_path)) as trade_db, closing(_readonly_connection(signal_path)) as signal_db:
        max_day = trade_db.execute("SELECT MAX(date) FROM signal_history WHERE date IS NOT NULL").fetchone()[0]
        if not max_day:
            raise ValueError("PRODUCTION_SIGNAL_HISTORY_EMPTY")
        max_day = str(max_day)[:10]
        as_of = latest_completed_session(max_day, now=now, calendar_reader=calendar_reader)
        signal_rows_raw = trade_db.execute(
            "SELECT date, code, price, action, position, reason FROM signal_history "
            "WHERE date IS NOT NULL AND date <= ? ORDER BY date, code LIMIT ?",
            (as_of, MAX_SOURCE_ROWS + 1),
        ).fetchall()
        trade_rows_raw = trade_db.execute(
            "SELECT id, code, buy_date, buy_price, buy_amount, sell_date, sell_price, fee, profit, pnl_pct, status, "
            "action, buy_reason, sell_reason "
            "FROM trade_records ORDER BY buy_date, id LIMIT ?", (MAX_SOURCE_ROWS + 1,),
        ).fetchall()
        if len(signal_rows_raw) > MAX_SOURCE_ROWS or len(trade_rows_raw) > MAX_SOURCE_ROWS:
            raise ValueError("PRODUCTION_ROW_LIMIT_EXCEEDED")
        signal_columns = ("date", "code", "price", "action", "position", "reason")
        trade_columns = (
            "id", "code", "buy_date", "buy_price", "buy_amount", "sell_date", "sell_price",
            "fee", "profit", "pnl_pct", "status", "action", "buy_reason", "sell_reason",
        )
        signal_rows = [dict(zip(signal_columns, row)) for row in signal_rows_raw]
        trade_rows = [dict(zip(trade_columns, row)) for row in trade_rows_raw]

        first_signal_day = min(str(row["date"])[:10] for row in signal_rows if row.get("date"))
        calendar_end = (date.fromisoformat(as_of) + timedelta(days=14)).isoformat()
        calendar = _session_strings(calendar_reader(first_signal_day, calendar_end))
        completed_sessions = [day for day in calendar if first_signal_day <= day <= as_of]
        if len(completed_sessions) < SESSION_COUNT:
            raise ValueError("TRADING_CALENDAR_HAS_TOO_FEW_SESSIONS")
        recent_sessions = completed_sessions[-SESSION_COUNT:]
        start_day, end_day = completed_sessions[0], completed_sessions[-1]
        message_map = _signal_message_map(signal_db, start_day, end_day)

        codes = {
            code for row in signal_rows + trade_rows
            if (code := normalize_code(row.get("code")))
        }
        if len(codes) > MAX_CODES:
            raise ValueError("PRODUCTION_CODE_LIMIT_EXCEEDED")
        bars_by_code: dict[str, dict[str, dict[str, Any]]] = {}
        file_states: Counter[str] = Counter()
        for code in sorted(codes):
            bars, state = bar_loader(code, tdx_root, first_signal_day, as_of)
            file_states[state] += 1
            bars_by_code[code] = {
                day: bar for day, bar in bars.items()
                if start_day <= day <= as_of
            }

    replay = simulate_signal_replay(
        signal_rows, completed_sessions=completed_sessions, calendar_sessions=calendar,
        bars_by_code=bars_by_code, signal_messages=message_map,
    )
    reconciliation = reconcile_trade_records(trade_rows, bars_by_code=bars_by_code)
    signal_message_matches = sum(
        1 for row in signal_rows
        if (normalize_code(row.get("code")), str(row.get("date") or "")[:10]) in message_map
    )
    recent_start = recent_sessions[0]
    recent_rows = [row for row in signal_rows if recent_start <= str(row.get("date") or "")[:10] <= as_of]
    recent_session_set = set(recent_sessions)
    recent_exchange_rows = [row for row in recent_rows if str(row.get("date") or "")[:10] in recent_session_set]
    recent_session_message_matches = sum(
        1 for row in recent_exchange_rows
        if (normalize_code(row.get("code")), str(row.get("date") or "")[:10]) in message_map
    )
    recent_codes = {normalize_code(row.get("code")) for row in recent_rows}
    recent_bars = {code: bars_by_code.get(code or "", {}) for code in recent_codes if code}
    recent_message_map = {key: value for key, value in message_map.items() if key[1] >= recent_start}
    recent_replay = simulate_signal_replay(
        recent_rows, completed_sessions=recent_sessions, calendar_sessions=calendar,
        bars_by_code=recent_bars, signal_messages=recent_message_map,
    )
    total_events = len(replay["events"])
    return {
        "schema_version": "ipo.production-vwap-trade-replay.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "COMPLETED_WITH_QUARANTINES" if (
            replay["summary"]["quarantined_signal_rows"]
            or reconciliation["summary"].get("buy_price_quarantine_count", 0)
            or reconciliation["summary"].get("sell_price_quarantine_count", 0)
        ) else "COMPLETED",
        "source_access": "READ_ONLY",
        "production_database_modified": False,
        "learning_database_modified": False,
        "training_performed": False,
        "model_promoted": False,
        "order_submitted": False,
        "replay_policy": {
            "signal_source": "trading_signals.db:signal_history; matched by date/code to signal_strategy.db:signal_message",
            "as_of_date": as_of,
            "latest_30_sessions": {"start": recent_start, "end": as_of, "count": len(recent_sessions)},
            "full_history_sessions": {"start": start_day, "end": end_day, "count": len(completed_sessions)},
            "signal_time_assumption": "signal_history is date-only; action is treated as close-confirmed and fills at next session open",
            "initial_positions": "flat; no holdings before the first signal are imported",
            "fill_assumption": "daily open proxy; order-book queue, limit-lock fill, slippage and partial fills are unavailable",
            "buy_gate": "signal action=买入; same-day signal price must be inside raw OHLC; daily close >= daily VWAP",
            "exit_gate": "full exit action or daily close < daily VWAP; fill at next tradable session open; T+1 enforced",
            "vwap_formula": "raw TDX daily amount (yuan) / raw daily volume (shares); no *100",
            "paper_size": "one 100-share lot; STAR market codes 688/689 use 200 shares",
            "paper_fees": "both sides notional * 0.0000754; sell +5 yuan per fill; half-up cents",
            "portfolio_capital_limit": "not modeled; summary is per-trade paper replay, not account return",
            "partial_exit_actions": sorted(PARTIAL_EXIT_ACTIONS),
        },
        "sources": {
            "trading_database": trade_path.name,
            "signal_database": signal_path.name,
            "tdx_raw_daily_root": str(tdx_root),
            "signal_rows": len(signal_rows),
            "trade_records": len(trade_rows),
            "signal_strategy_matches": signal_message_matches,
            "signal_strategy_match_coverage_pct": round(signal_message_matches / len(signal_rows) * 100.0, 4) if signal_rows else 0.0,
            "latest_30_session_source_signal_rows": len(recent_rows),
            "latest_30_session_exchange_signal_rows": len(recent_exchange_rows),
            "latest_30_session_signal_strategy_matches": recent_session_message_matches,
            "latest_30_session_signal_strategy_match_coverage_pct": round(
                recent_session_message_matches / len(recent_exchange_rows) * 100.0, 4
            ) if recent_exchange_rows else 0.0,
            "unique_codes_loaded": len(codes),
            "tdx_file_states": dict(sorted(file_states.items())),
        },
        "full_history_replay": replay["summary"],
        "latest_30_session_replay": recent_replay["summary"],
        "production_trade_reconciliation": reconciliation["summary"],
        "data_gaps": [
            reason for condition, reason in (
                (replay["summary"]["non_session_signal_rows"] > 0,
                 "signal_history 含非交易日记录，已隔离，不参与成交回放"),
                (replay["summary"]["quarantined_signal_rows"] > replay["summary"]["non_session_signal_rows"],
                 "部分交易日信号缺少原始日线或价格超出当日日线区间，已隔离"),
                (reconciliation["summary"].get("sell_price_quarantine_count", 0) > 0,
                 "部分应用交易记录缺卖出日线或卖出价格不在 OHLC 区间，逐笔对账文件保留原因"),
                (reconciliation["summary"].get("pnl_input_quarantine_count", 0) > 0,
                 "部分平仓记录股数或价格无效，未把零股数对应的零利润计为有效盈亏对账"),
                (replay["summary"]["partial_exit_not_modeled_count"] > 0,
                 "减仓信号缺少可审计数量，本次不伪造为全仓平仓"),
                (not reconciliation["summary"].get("broker_fill_proof_available", False),
                 "交易表没有券商成交回报字段；该表只可核对应用记账公式，不足以证明实盘成交"),
                (recent_replay["summary"]["closed_round_trip_count"] == 0,
                 "最新 30 个交易日没有可由买入信号闭合的 VWAP 纸面往返交易"),
                (recent_session_message_matches < len(recent_exchange_rows),
                 "signal_history 与 signal_message 仅按交易日和代码关联；未匹配事件保留为空，不推断因果"),
            ) if condition
        ],
        "artifacts": {
            "paper_trades_csv": "ipo_vwap_paper_trades.latest.csv",
            "open_positions_csv": "ipo_vwap_open_positions.latest.csv",
            "signal_events_csv": "ipo_vwap_signal_events.latest.csv",
            "production_trade_reconciliation_csv": "ipo_vwap_production_trade_reconciliation.latest.csv",
            "signal_event_count": total_events,
        },
        "_paper_trades": replay["trades"],
        "_open_positions": replay["open_positions"],
        "_signal_events": replay["events"],
        "_production_trade_records": reconciliation["records"],
    }


def _hash_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        {key: value for key, value in payload.items() if key != "report_hash" and not key.startswith("_" )},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields and path.name == "ipo_vwap_open_positions.latest.csv":
        fields = [
            "code", "status", "shares", "buy_signal_day", "buy_signal_price", "buy_signal_close",
            "buy_signal_vwap", "buy_date", "buy_price", "buy_vwap", "as_of_date", "mark_price",
            "unrealized_gross_pnl", "pending_exit_signal_day", "fee_mode",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            if fields:
                writer.writeheader()
                writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def persist_replay_report(root: str | Path, report_dir: str | Path, report: dict[str, Any]) -> dict[str, Any]:
    base = safe_resolve_path(Path(root))
    destination_dir = Path(report_dir)
    if not destination_dir.is_absolute():
        destination_dir = base / destination_dir
    destination_dir = destination_dir.resolve()
    try:
        destination_dir.relative_to(base)
    except ValueError as exc:
        raise ValueError("REPORT_PATH_MUST_STAY_INSIDE_PROJECT_ROOT") from exc
    artifacts = report.get("artifacts", {})
    for key in ("paper_trades_csv", "open_positions_csv", "signal_events_csv",
                "production_trade_reconciliation_csv"):
        name = artifacts.get(key)
        if name is not None and (
            not isinstance(name, str) or not name or Path(name).name != name
            or "/" in name or "\\" in name or ":" in name or name in {".", ".."}
        ):
            raise ValueError("INVALID_REPORT_ARTIFACT_NAME")
    files = {
        artifacts.get("paper_trades_csv", "ipo_vwap_paper_trades.latest.csv"): report.pop("_paper_trades", []),
        artifacts.get("open_positions_csv", "ipo_vwap_open_positions.latest.csv"): report.pop("_open_positions", []),
        artifacts.get("signal_events_csv", "ipo_vwap_signal_events.latest.csv"): report.pop("_signal_events", []),
        artifacts.get("production_trade_reconciliation_csv", "ipo_vwap_production_trade_reconciliation.latest.csv"): report.pop("_production_trade_records", []),
    }
    for name, rows in files.items():
        _write_csv(destination_dir / name, rows)
    report["artifacts"]["sha256"] = {
        name: hashlib.sha256((destination_dir / name).read_bytes()).hexdigest() for name in files
    }
    report["report_path"] = (destination_dir / "ipo_vwap_trade_replay.latest.json").relative_to(base).as_posix()
    report["report_persisted"] = True
    report["report_hash"] = _hash_json(report)
    _atomic_write_text(destination_dir / "ipo_vwap_trade_replay.latest.json",
                       json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return report
