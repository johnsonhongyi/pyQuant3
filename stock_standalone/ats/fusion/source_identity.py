# -*- coding: utf-8 -*-
"""影子记录的实时与回放来源判定。"""
from datetime import datetime


def record_matches_day(row, day):
    try:
        ts = float(row.get("ts") or 0)
        return (ts > 0 and datetime.fromtimestamp(ts).strftime("%Y-%m-%d") == day
                and all(not row.get(key) or str(row[key])[:10] == day for key in ("day", "trade_date")))
    except (TypeError, ValueError, OverflowError, OSError, AttributeError):
        return False


def is_replay_record(row):
    origin = str(row.get("writer_exe") or "").lower()
    source = str(row.get("source") or "").lower()
    return ("replay" in origin or "backfill" in origin or
            "replay" in source or "backfill" in source or row.get("writer_pid") == 0)
