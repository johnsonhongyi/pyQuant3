"""ats/strategy/subnew_trading_clock.py

Atomic Trading Clock and TTL Evaluation for Subnew Secondary Buy Strategy.
Only models intraday Chinese A-share trading hours:
- Morning session: 09:30 ~ 11:30 (120 minutes)
- Afternoon session: 13:00 ~ 15:00 (120 minutes)
- Lunch break: 11:30 ~ 13:00 is excluded (0 trading minutes).
- Pre-market and post-market are stably clipped, non-negative.
- Single-day contract: cross natural/trading day plans expire immediately.
- Pure functions without network, quote or calendar dependencies, zero side-effects.
"""

import datetime
import re
from typing import Any, Dict, NamedTuple, Optional, Tuple, Union

# Expiration reason constants
REASON_TTL_TRADING_15M = "TTL_TRADING_15M"
REASON_TTL_CROSS_DAY = "TTL_CROSS_DAY"
TTL_TRADING_15M = "TTL_TRADING_15M"
TTL_CROSS_DAY = "TTL_CROSS_DAY"

# Standard A-share intraday session boundaries in seconds from midnight
MORNING_START_SEC = 9 * 3600 + 30 * 60       # 09:30:00 -> 34200.0s
MORNING_END_SEC = 11 * 3600 + 30 * 60        # 11:30:00 -> 41400.0s
AFTERNOON_START_SEC = 13 * 3600              # 13:00:00 -> 46800.0s
AFTERNOON_END_SEC = 15 * 3600                # 15:00:00 -> 54000.0s

MORNING_DURATION_SEC = MORNING_END_SEC - MORNING_START_SEC          # 7200.0s (120 mins)
AFTERNOON_DURATION_SEC = AFTERNOON_END_SEC - AFTERNOON_START_SEC    # 7200.0s (120 mins)
TOTAL_DAY_TRADING_SEC = MORNING_DURATION_SEC + AFTERNOON_DURATION_SEC  # 14400.0s (240 mins)

DEFAULT_TTL_MINUTES = 15.0


def _parse_time_or_datetime(val: Any) -> Tuple[Optional[datetime.date], float]:
    """Parse various timestamp/time representations into (optional_date, seconds_from_midnight).

    Supported types:
    - datetime.datetime
    - datetime.time
    - datetime.date
    - float / int (unix epoch timestamp)
    - str (ISO formats, 'YYYY-MM-DD HH:MM:SS', 'HH:MM:SS', 'HH:MM', etc.)

    Returns:
        Tuple[Optional[datetime.date], float]: (date or None, seconds_from_midnight)
    """
    if isinstance(val, datetime.datetime):
        d = val.date()
        sec = val.hour * 3600.0 + val.minute * 60.0 + val.second + val.microsecond / 1_000_000.0
        return d, sec
    elif isinstance(val, datetime.time):
        sec = val.hour * 3600.0 + val.minute * 60.0 + val.second + val.microsecond / 1_000_000.0
        return None, sec
    elif isinstance(val, datetime.date):
        return val, 0.0
    elif isinstance(val, (int, float)):
        ts = float(val)
        if ts > 1e11:  # Milliseconds timestamp
            ts /= 1000.0
        dt = datetime.datetime.fromtimestamp(ts)
        sec = dt.hour * 3600.0 + dt.minute * 60.0 + dt.second + dt.microsecond / 1_000_000.0
        return dt.date(), sec
    elif isinstance(val, str):
        val_str = val.strip()
        # Time-only: HH:MM or HH:MM:SS(.ffffff)
        if re.match(r"^\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?$", val_str):
            parts = val_str.split(":")
            h = int(parts[0])
            m = int(parts[1])
            s = float(parts[2]) if len(parts) > 2 else 0.0
            return None, h * 3600.0 + m * 60.0 + s

        clean_str = val_str.replace("/", "-")
        try:
            dt = datetime.datetime.fromisoformat(clean_str)
            sec = dt.hour * 3600.0 + dt.minute * 60.0 + dt.second + dt.microsecond / 1_000_000.0
            return dt.date(), sec
        except Exception:
            pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%Y%m%d %H:%M:%S",
            "%Y%m%d%H%M%S",
            "%Y%m%d",
        ):
            try:
                dt = datetime.datetime.strptime(clean_str, fmt)
                sec = dt.hour * 3600.0 + dt.minute * 60.0 + dt.second + dt.microsecond / 1_000_000.0
                return dt.date(), sec
            except ValueError:
                continue
        raise ValueError(f"Unable to parse timestamp/time string: {val!r}")
    else:
        if hasattr(val, "hour") and hasattr(val, "minute"):
            h = getattr(val, "hour")
            m = getattr(val, "minute")
            s = getattr(val, "second", 0)
            us = getattr(val, "microsecond", 0)
            d_attr = getattr(val, "date", None)
            parsed_date = d_attr() if callable(d_attr) else None
            return parsed_date, h * 3600.0 + m * 60.0 + s + us / 1_000_000.0
        raise TypeError(f"Unsupported time type: {type(val)} ({val!r})")


def _trading_seconds_from_midnight(sec: float) -> float:
    """Map seconds from midnight into cumulative trading seconds from start of day.

    Mapping:
    - <= 09:30:00 -> 0.0
    - 09:30:00 ~ 11:30:00 -> sec - 09:30:00
    - 11:30:00 ~ 13:00:00 -> 7200.0 (120 mins)
    - 13:00:00 ~ 15:00:00 -> 7200.0 + (sec - 13:00:00)
    - >= 15:00:00 -> 14400.0 (240 mins)
    """
    if sec <= MORNING_START_SEC:
        return 0.0
    elif sec <= MORNING_END_SEC:
        return sec - MORNING_START_SEC
    elif sec <= AFTERNOON_START_SEC:
        return MORNING_DURATION_SEC
    elif sec <= AFTERNOON_END_SEC:
        return MORNING_DURATION_SEC + (sec - AFTERNOON_START_SEC)
    else:
        return TOTAL_DAY_TRADING_SEC


def trading_minutes_elapsed(start: Any, end: Any) -> float:
    """Calculate elapsed trading minutes between start and end.

    Trading rules:
    - Only counts 09:30~11:30 and 13:00~15:00; lunch break (11:30~13:00) is excluded.
    - Pre-market (<09:30) and post-market (>15:00) times are stably clipped.
    - Negative elapsed minutes are never returned (returns 0.0 if end < start).
    - Single-day contract: across natural days, returns cross-day elapsed trading minutes.

    Returns:
        float: Elapsed trading minutes (rounded to 6 decimal places).
    """
    d1, s1 = _parse_time_or_datetime(start)
    d2, s2 = _parse_time_or_datetime(end)

    if d1 is not None and d2 is not None:
        if d2 < d1:
            return 0.0
        elif d2 == d1:
            if s2 <= s1:
                return 0.0
            elapsed_sec = _trading_seconds_from_midnight(s2) - _trading_seconds_from_midnight(s1)
            return max(0.0, round(elapsed_sec / 60.0, 6))
        else:
            # d2 > d1 (cross natural/trading days)
            day_diff = (d2 - d1).days
            day1_rem_sec = max(0.0, TOTAL_DAY_TRADING_SEC - _trading_seconds_from_midnight(s1))
            day2_elap_sec = max(0.0, _trading_seconds_from_midnight(s2))
            intervening_sec = max(0, day_diff - 1) * TOTAL_DAY_TRADING_SEC
            total_sec = day1_rem_sec + intervening_sec + day2_elap_sec
            return max(0.0, round(total_sec / 60.0, 6))
    else:
        if s2 <= s1:
            return 0.0
        elapsed_sec = _trading_seconds_from_midnight(s2) - _trading_seconds_from_midnight(s1)
        return max(0.0, round(elapsed_sec / 60.0, 6))


class TradePlanTTLResult(NamedTuple):
    """Result of evaluate_trade_plan_ttl evaluation."""

    elapsed_trading_minutes: float
    is_expired: bool
    expired_reason: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "elapsed_trading_minutes": self.elapsed_trading_minutes,
            "is_expired": self.is_expired,
            "expired_reason": self.expired_reason,
        }

    def __getitem__(self, item: Any) -> Any:
        """Allow both tuple indexing and dictionary-like string key access."""
        if isinstance(item, str):
            if item in ("elapsed_trading_minutes", "elapsed"):
                return self.elapsed_trading_minutes
            elif item == "is_expired":
                return self.is_expired
            elif item in ("expired_reason", "reason"):
                return self.expired_reason
            raise KeyError(f"Invalid key for TradePlanTTLResult: {item!r}")
        return tuple.__getitem__(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        """Safe dict-like lookup."""
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


def evaluate_trade_plan_ttl(
    created_time: Any,
    now: Any,
    ttl_minutes: float = DEFAULT_TTL_MINUTES,
) -> TradePlanTTLResult:
    """Evaluate TradePlan TTL against current time in trading minutes.

    Requirements:
    - Pure function: no business state modified.
    - Counts trading minutes (09:30~11:30, 13:00~15:00), excluding lunch break.
    - Reaching or exceeding ttl_minutes (default 15) expires with reason 'TTL_TRADING_15M'.
    - Plans from a previous calendar/trading day expire immediately with reason 'TTL_CROSS_DAY'.
    - If now is before created_time (clock skew / inversion), returns not expired with 0.0 elapsed.

    Returns:
        TradePlanTTLResult(elapsed_trading_minutes, is_expired, expired_reason)
    """
    d1, s1 = _parse_time_or_datetime(created_time)
    d2, s2 = _parse_time_or_datetime(now)

    # Cross day check
    if d1 is not None and d2 is not None:
        if d2 < d1 or (d2 == d1 and s2 < s1):
            return TradePlanTTLResult(
                elapsed_trading_minutes=0.0,
                is_expired=False,
                expired_reason=None,
            )
        elif d2 > d1:
            elapsed = trading_minutes_elapsed(created_time, now)
            return TradePlanTTLResult(
                elapsed_trading_minutes=elapsed,
                is_expired=True,
                expired_reason=REASON_TTL_CROSS_DAY,
            )

    elapsed = trading_minutes_elapsed(created_time, now)
    if elapsed >= ttl_minutes:
        return TradePlanTTLResult(
            elapsed_trading_minutes=elapsed,
            is_expired=True,
            expired_reason=REASON_TTL_TRADING_15M,
        )
    else:
        return TradePlanTTLResult(
            elapsed_trading_minutes=elapsed,
            is_expired=False,
            expired_reason=None,
        )


def is_trading_time(t: Any) -> bool:
    """Check whether given time is inside regular A-share trading sessions.

    Trading sessions:
    09:30:00 <= t <= 11:30:00 or 13:00:00 <= t <= 15:00:00
    """
    _, sec = _parse_time_or_datetime(t)
    return (MORNING_START_SEC <= sec <= MORNING_END_SEC) or (AFTERNOON_START_SEC <= sec <= AFTERNOON_END_SEC)


def remaining_trading_minutes_in_day(t: Any) -> float:
    """Calculate remaining trading minutes left in the trading day from time t."""
    _, sec = _parse_time_or_datetime(t)
    rem_sec = max(0.0, TOTAL_DAY_TRADING_SEC - _trading_seconds_from_midnight(sec))
    return round(rem_sec / 60.0, 6)


__all__ = [
    "trading_minutes_elapsed",
    "evaluate_trade_plan_ttl",
    "TradePlanTTLResult",
    "REASON_TTL_TRADING_15M",
    "REASON_TTL_CROSS_DAY",
    "TTL_TRADING_15M",
    "TTL_CROSS_DAY",
    "MORNING_START_SEC",
    "MORNING_END_SEC",
    "AFTERNOON_START_SEC",
    "AFTERNOON_END_SEC",
    "DEFAULT_TTL_MINUTES",
    "is_trading_time",
    "remaining_trading_minutes_in_day",
]
