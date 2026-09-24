# -*- coding: utf-8 -*-
"""Deterministic T+1 position facts derived inside the TradingKernel boundary."""

from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any, Dict, Iterable, List, Optional


def _number(value: Any) -> float:
    try:
        number = float(value)
        return max(0.0, number) if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _normalize_code(value: Any) -> str:
    raw = str(value or "").strip()
    return raw.zfill(6) if raw.isdigit() and len(raw) <= 6 else raw


def _date_from_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except Exception:
        return ""


def build_t1_position_facts(
    positions: Dict[str, Dict[str, Any]],
    orders: Iterable[Dict[str, Any]],
    *,
    trading_day: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return native total/sellable/today-buy/lot facts for each current position.

    Unknown legacy quantity is never promoted to sellable unless a reliable
    position entry date proves it predates the current trading day.
    """

    day = str(trading_day or date.today().isoformat())
    lots_by_code: Dict[str, List[Dict[str, Any]]] = {}

    for order in sorted(
        [dict(item) for item in (orders or []) if isinstance(item, dict)],
        key=lambda item: str(item.get("timestamp") or ""),
    ):
        code = _normalize_code(order.get("code"))
        action = str(order.get("action") or "").upper()
        qty = _number(order.get("volume"))
        if not code or qty <= 0:
            continue
        timestamp = str(order.get("timestamp") or "")
        order_day = _date_from_timestamp(timestamp)
        price = _number(order.get("price"))

        if action in {"BUY", "ADD"}:
            lots_by_code.setdefault(code, []).append({
                "qty": qty,
                "price": price,
                "buy_date": order_day,
                "timestamp": timestamp,
                "source": "ORDER_LEDGER",
            })
            continue

        if action not in {"SELL", "REDUCE"}:
            continue

        remaining = qty
        code_lots = lots_by_code.setdefault(code, [])
        while remaining > 1e-9 and code_lots:
            lot = code_lots[0]
            matched = min(remaining, _number(lot.get("qty")))
            lot["qty"] = _number(lot.get("qty")) - matched
            remaining -= matched
            if lot["qty"] <= 1e-9:
                code_lots.pop(0)

    result: Dict[str, Dict[str, Any]] = {}
    for raw_code, raw_position in (positions or {}).items():
        if not isinstance(raw_position, dict):
            continue
        code = _normalize_code(raw_code)
        position = dict(raw_position)
        total_qty = _number(position.get("total_qty", position.get("volume", position.get("shares", 0.0))))
        derived_lots = [dict(item) for item in lots_by_code.get(code, []) if _number(item.get("qty")) > 1e-9]
        derived_qty = sum(_number(item.get("qty")) for item in derived_lots)

        status = "COMPLETE"
        if derived_qty < total_qty - 1e-9:
            missing = total_qty - derived_qty
            entry_day = _date_from_timestamp(position.get("entry_time"))
            derived_lots.append({
                "qty": missing,
                "price": _number(position.get("entry_price")),
                # Position-level entry_time cannot establish the acquisition
                # date of an unexplained quantity delta.
                "buy_date": "",
                "timestamp": str(position.get("entry_time") or ""),
                "source": "POSITION_FALLBACK",
            })
            status = "POSITION_FALLBACK_FAIL_CLOSED" if entry_day else "INCOMPLETE_FAIL_CLOSED"
        elif derived_qty > total_qty + 1e-9:
            # The missing sell/update record makes the surviving lot ages
            # ambiguous. Do not guess which lots remain or unlock T+1 shares.
            derived_lots = [{
                "qty": total_qty,
                "price": 0.0,
                "buy_date": "",
                "timestamp": "",
                "source": "RECONCILIATION_MISMATCH",
            }]
            status = "LEDGER_POSITION_MISMATCH_FAIL_CLOSED"

        sellable_qty = 0.0
        today_buy_qty = 0.0
        rendered_lots: List[Dict[str, Any]] = []
        for lot in derived_lots:
            qty = min(total_qty, _number(lot.get("qty")))
            buy_day = str(lot.get("buy_date") or "")
            is_today = buy_day == day
            is_sellable = bool(buy_day and buy_day < day)
            if is_today:
                today_buy_qty += qty
            if is_sellable:
                sellable_qty += qty
            rendered = dict(lot)
            rendered["qty"] = round(qty, 4)
            rendered["sellable"] = is_sellable
            rendered["today_buy"] = is_today
            rendered_lots.append(rendered)

        sellable_qty = min(total_qty, sellable_qty)
        today_buy_qty = min(total_qty, today_buy_qty)
        unresolved_qty = max(0.0, total_qty - sellable_qty - today_buy_qty)
        result[code] = {
            "code": code,
            "trade_date": day,
            "snapshot_version": "2.0",
            "total_qty": round(total_qty, 4),
            "sellable_qty": round(sellable_qty, 4),
            "today_buy_qty": round(today_buy_qty, 4),
            "unresolved_qty": round(unresolved_qty, 4),
            "lots": rendered_lots,
            "t1_fact_status": status,
            "trading_day": day,
        }

    return result
