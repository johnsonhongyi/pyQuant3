"""Trading-session gates shared by scanners and deterministic replay."""
from datetime import datetime, time, timedelta, timezone
from enum import Enum


MARKET_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


class SessionPhase(str, Enum):
    PREOPEN = 'PREOPEN'
    AUCTION = 'AUCTION'
    OPEN_CONFIRM = 'OPEN_CONFIRM'
    MORNING = 'MORNING'
    LUNCH = 'LUNCH'
    AFTERNOON = 'AFTERNOON'
    CLOSE = 'CLOSE'
    CLOSED = 'CLOSED'


def market_now() -> datetime:
    """Return China market wall time without a machine-local timezone dependency."""
    return datetime.now(MARKET_TIMEZONE).replace(tzinfo=None)


def market_datetime(value: datetime) -> datetime:
    """Normalize aware instants to China market time; keep naive replay values as-is."""
    if value.tzinfo is None:
        return value
    return value.astimezone(MARKET_TIMEZONE).replace(tzinfo=None)


def phase_at(value=None):
    value = market_now() if value is None else value
    if isinstance(value, datetime):
        current_time = market_datetime(value).time()
    else:
        current_time = value
    if current_time < time(8, 45) or current_time >= time(15):
        return SessionPhase.CLOSED
    if current_time < time(9, 15):
        return SessionPhase.PREOPEN
    if current_time < time(9, 30):
        return SessionPhase.AUCTION
    if current_time < time(9, 45):
        return SessionPhase.OPEN_CONFIRM
    if current_time < time(11, 30):
        return SessionPhase.MORNING
    if current_time < time(13):
        return SessionPhase.LUNCH
    if current_time < time(14, 30):
        return SessionPhase.AFTERNOON
    return SessionPhase.CLOSE


def is_fresh_signal_allowed(phase):
    return SessionPhase(phase) in {
        SessionPhase.OPEN_CONFIRM, SessionPhase.MORNING,
        SessionPhase.AFTERNOON, SessionPhase.CLOSE,
    }


def is_seed_only(phase):
    return SessionPhase(phase) in {
        SessionPhase.PREOPEN, SessionPhase.AUCTION,
        SessionPhase.LUNCH, SessionPhase.CLOSED,
    }
