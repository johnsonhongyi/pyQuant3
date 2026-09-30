"""Archive only during market hours, plus one changed closing snapshot per day."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache

ARCHIVE_INTERVAL = 30 * 60.0


@lru_cache(maxsize=8)
def _trading_day(day):
    try:
        import a_trade_calendar
        return bool(a_trade_calendar.is_trade_date(day))
    except Exception:
        return False


def archive_window(now=None):
    now = now or datetime.now(timezone(timedelta(hours=8)))
    day = now.strftime('%Y-%m-%d')
    if not _trading_day(day):
        return None, day
    minute = now.hour * 60 + now.minute
    if 570 <= minute < 690 or 780 <= minute < 900:
        return 'market', day
    if minute >= 900:
        return 'close', day
    return None, day
