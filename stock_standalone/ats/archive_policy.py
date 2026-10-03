"""Archive only during market hours, plus one changed closing snapshot per day."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache

ARCHIVE_INTERVAL = 30 * 60.0


@lru_cache(maxsize=8)
def _effective_trade_date(day):
    try:
        from JohnsonUtil import commonTips as cct
        if cct.get_day_istrade_date(day):
            return day
        last_trade_day = cct.get_last_trade_date(day)
        if hasattr(last_trade_day, 'strftime'):
            last_trade_day = last_trade_day.strftime('%Y-%m-%d')
        last_trade_day = str(last_trade_day).strip()[:10]
        return datetime.strptime(last_trade_day, '%Y-%m-%d').strftime('%Y-%m-%d')
    except Exception:
        return None


def archive_window(now=None):
    now = now or datetime.now(timezone(timedelta(hours=8)))
    calendar_day = now.strftime('%Y-%m-%d')
    day = _effective_trade_date(calendar_day)
    if day is None:
        return None, calendar_day
    if day != calendar_day:
        return None, day
    minute = now.hour * 60 + now.minute
    if 570 <= minute < 690 or 780 <= minute < 900:
        return 'market', day
    if minute >= 900:
        return 'close', day
    return None, day
