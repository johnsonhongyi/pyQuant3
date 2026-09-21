# -*- coding: utf-8 -*-
"""Execution-time freshness and price guards for converged directives."""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from typing import Any


ENTRY_ACTIONS = frozenset({"BUY", "BUY_SCOUT", "BUY_CONFIRM"})
EXIT_ACTIONS = frozenset({"SELL", "EXIT_ALL", "REDUCE", "REDUCE_30", "REDUCE_HALF"})


@dataclass(frozen=True)
class DirectiveValidation:
    allowed: bool
    code: str = ""
    reason: str = ""
    live_price: float = 0.0
    age_seconds: float = 0.0


def _parse_expire_today(expire_at: str, now_ts: float) -> float:
    text = str(expire_at or "").strip()
    if not text:
        return 0.0
    try:
        today = datetime.datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d")
        return time.mktime(time.strptime(f"{today} {text}", "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0.0



def validate_directive(
    directive: Any,
    report: Any,
    *,
    now_ts: float | None = None,
    max_entry_age_seconds: float = 180.0,
    max_price_deviation_pct: float = 1.5,
) -> DirectiveValidation:
    now_ts = float(now_ts or time.time())
    action = str(getattr(directive, "action", "") or "").upper()
    dir_ts = float(getattr(directive, "timestamp", 0.0) or 0.0)
    age = max(0.0, now_ts - dir_ts) if dir_ts > 0 else 0.0

    expire_ts = _parse_expire_today(getattr(directive, "expire_at", ""), now_ts)
    if expire_ts > 0 and now_ts > expire_ts:
        return DirectiveValidation(False, "DIRECTIVE_EXPIRED", "指令已超过当日失效时间", age_seconds=age)

    if action in ENTRY_ACTIONS and (dir_ts <= 0 or age > max_entry_age_seconds):
        return DirectiveValidation(False, "STALE_DIRECTIVE", "买入指令时间戳缺失或已过期", age_seconds=age)

    if report is None:
        if action in ENTRY_ACTIONS:
            return DirectiveValidation(False, "MISSING_LIVE_SNAPSHOT", "缺少最新个股实时快照", age_seconds=age)
        return DirectiveValidation(True, live_price=float(getattr(directive, "price", 0.0) or 0.0), age_seconds=age)

    update_text = str(getattr(report, "update_time", "") or "").strip()
    if action in ENTRY_ACTIONS and update_text:
        snapshot_ts = 0.0
        for fmt in ("%Y-%m-%d %H:%M:%S", "%H:%M:%S"):
            try:
                parsed = time.strptime(update_text, fmt)
                if fmt == "%H:%M:%S":
                    day = datetime.datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d")
                    parsed = time.strptime(f"{day} {update_text}", "%Y-%m-%d %H:%M:%S")
                snapshot_ts = time.mktime(parsed)
                break
            except Exception:
                continue
        if snapshot_ts > 0 and now_ts - snapshot_ts > max_entry_age_seconds:
            return DirectiveValidation(
                False, "STALE_LIVE_SNAPSHOT", "个股实时快照已过期",
                age_seconds=max(0.0, now_ts - snapshot_ts),
            )

    live_price = float(getattr(report, "price", 0.0) or 0.0)
    if live_price <= 0:
        if action in ENTRY_ACTIONS:
            return DirectiveValidation(False, "INVALID_LIVE_PRICE", "最新快照价格无效", age_seconds=age)
        return DirectiveValidation(True, live_price=float(getattr(directive, "price", 0.0) or 0.0), age_seconds=age)

    trigger_price = float(getattr(directive, "price", 0.0) or 0.0)
    if action in ENTRY_ACTIONS and trigger_price > 0:
        deviation = abs(live_price - trigger_price) / trigger_price * 100.0
        if deviation > max_price_deviation_pct:
            return DirectiveValidation(
                False,
                "PRICE_DRIFT_EXCEEDED",
                f"现价相对触发价偏离 {deviation:.2f}% > {max_price_deviation_pct:.2f}%",
                live_price=live_price,
                age_seconds=age,
            )

    stop_price = float(getattr(directive, "stop_loss_price", 0.0) or 0.0)
    if action in ENTRY_ACTIONS and stop_price > 0 and live_price <= stop_price:
        return DirectiveValidation(
            False, "STRUCTURE_INVALIDATED", "现价已跌破止损/结构失效价",
            live_price=live_price, age_seconds=age,
        )

    return DirectiveValidation(True, live_price=live_price, age_seconds=age)
