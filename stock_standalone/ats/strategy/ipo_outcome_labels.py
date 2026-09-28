# -*- coding: utf-8 -*-
"""Deterministic D1-D3 IPO outcome evidence; evidence is never training approval."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time, timezone
from typing import Any, Dict, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


def build_matured_outcome(
    *,
    ticker: str,
    listing_date: str,
    issue_price: float,
    daily_bars: Iterable[Mapping[str, Any]],
    source_id: str,
    source_version: str,
    source_timezone: str,
    as_of_time: datetime,
    available_at: datetime,
    anchors: Optional[Mapping[str, Any]] = None,
    trading_sessions: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Build D1-D3 evidence only after three complete post-listing sessions."""
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        raise ValueError("ticker must be six digits")
    listing_day = date.fromisoformat(listing_date)
    if not isinstance(issue_price, (int, float)) or isinstance(issue_price, bool):
        raise ValueError("issue_price must be numeric")
    issue_price = float(issue_price)
    if not math.isfinite(issue_price) or issue_price <= 0:
        raise ValueError("issue_price must be positive and finite")
    if source_timezone != "Asia/Shanghai" or source_id.strip() == "" or source_version.strip() == "":
        raise ValueError("outcome source provenance is incomplete")
    if as_of_time.tzinfo is None or available_at.tzinfo is None:
        raise ValueError("source timestamps must be timezone-aware")
    as_of_utc = as_of_time.astimezone(timezone.utc)
    available_utc = available_at.astimezone(timezone.utc)
    if as_of_utc > available_utc or available_utc > datetime.now(timezone.utc):
        raise ValueError("source timestamps are inconsistent or future-dated")

    now_shanghai = datetime.now(SHANGHAI)
    calendar_dates = set()
    if trading_sessions is not None:
        for raw_day in trading_sessions:
            if isinstance(raw_day, datetime):
                calendar_dates.add(raw_day.date())
            elif isinstance(raw_day, date):
                calendar_dates.add(raw_day)
            else:
                calendar_dates.add(date.fromisoformat(str(raw_day)[:10]))
    expected_sessions = sorted(day for day in calendar_dates if day > listing_day)[:3]
    by_date: Dict[date, Dict[str, float]] = {}
    for raw in daily_bars:
        day = date.fromisoformat(str(raw.get("date", ""))[:10])
        if day <= listing_day:
            continue
        if day == now_shanghai.date() and now_shanghai.time() < time(15, 0):
            continue
        values: Dict[str, float] = {}
        for key in ("open", "high", "low", "close"):
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"bar {day} missing numeric {key}")
            values[key] = float(value)
            if not math.isfinite(values[key]) or values[key] <= 0:
                raise ValueError(f"bar {day} contains invalid {key}")
        if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
            raise ValueError(f"bar {day} violates OHLC bounds")
        if day in by_date:
            raise ValueError(f"duplicate daily bar: {day}")
        by_date[day] = values
    observed_sessions = [day for day in expected_sessions if day in by_date]
    if len(expected_sessions) < 3 or len(observed_sessions) < 3:
        return {
            "status": "PENDING_D3", "ticker": ticker, "listing_date": listing_day.isoformat(),
            "observed_sessions": [item.isoformat() for item in observed_sessions],
            "expected_sessions": [item.isoformat() for item in expected_sessions],
            "required_sessions": 3,
            "reason": "交易日历未就绪或D1-D3交易日日线证据不完整",
        }
    # The daily history includes the listing session (D0); maturity starts at D1.
    earliest_bar_sessions = sorted(day for day in by_date if day > listing_day)[:3]
    if earliest_bar_sessions != expected_sessions[:3]:
        return {
            "status": "PENDING_D3", "ticker": ticker, "listing_date": listing_day.isoformat(),
            "observed_sessions": [item.isoformat() for item in observed_sessions],
            "expected_sessions": [item.isoformat() for item in expected_sessions[:3]],
            "earliest_bar_sessions": [item.isoformat() for item in earliest_bar_sessions],
            "required_sessions": 3,
            "reason": "交易日历首三日与历史K线首三日不一致，拒绝错位成熟标签",
        }
    sessions = expected_sessions
    d3_close = datetime.combine(sessions[2], time(15, 0), SHANGHAI)
    if as_of_utc < d3_close.astimezone(timezone.utc):
        return {
            "status": "PENDING_D3", "ticker": ticker, "listing_date": listing_day.isoformat(),
            "observed_sessions": [item.isoformat() for item in observed_sessions],
            "expected_sessions": [item.isoformat() for item in expected_sessions],
            "required_sessions": 3, "reason": "as_of_time早于D3交易日收盘，标签尚未成熟",
        }
    bars = [by_date[day] for day in sessions]
    closes = [row["close"] for row in bars]
    returns = [(close / issue_price - 1.0) * 100.0 for close in closes]
    equity = [issue_price] + closes
    peak = equity[0]
    drawdowns = []
    for close in closes:
        peak = max(peak, close)
        drawdowns.append((close / peak - 1.0) * 100.0)
    lows = [row["low"] for row in bars]
    anchor_break = None
    if isinstance(anchors, Mapping):
        anchor_values = [anchors.get("listing_low"), anchors.get("listing_anchored_vwap")]
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0 for value in anchor_values):
            anchor_break = min(lows) < min(float(anchor_values[0]), float(anchor_values[1]))
    payload: Dict[str, Any] = {
        "schema_version": "ipo-outcome-evidence.v1",
        "ticker": ticker, "listing_date": listing_day.isoformat(),
        "reference": {"kind": "issue_price", "price": issue_price, "unit": "CNY/share"},
        "sessions": [
            {"date": day.isoformat(), **by_date[day], "return_vs_issue_pct": returns[index]}
            for index, day in enumerate(sessions)
        ],
        "d1_positive": returns[0] > 0,
        "d1_return_pct": returns[0],
        "d2_return_pct": returns[1],
        "d3_positive": returns[2] > 0,
        "d3_return_pct": returns[2],
        "d1_d3_close_max_drawdown_pct": min(drawdowns),
        "broke_issue_price": min(lows) < issue_price,
        "broke_both_listing_anchors": anchor_break,
        "anchor_break_status": "CHECKED" if anchor_break is not None else "UNREADY_NO_FROZEN_ANCHORS",
        "source": {"source_id": source_id, "source_version": source_version,
                   "source_timezone": source_timezone,
                   "as_of_time": as_of_time.astimezone(SHANGHAI).isoformat(),
                   "available_at": available_at.astimezone(SHANGHAI).isoformat()},
        "matured_at": d3_close.isoformat(),
        "labels_mature": True,
        "review_status": "PENDING_HUMAN_REVIEW",
        "training_eligible": False,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    payload["evidence_id"] = "outcome:" + digest[:48]
    payload["evidence_hash"] = digest
    payload["status"] = "MATURED_PENDING_REVIEW"
    return payload
