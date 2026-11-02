"""Bounded WAL, retention and state slimming for the paper worker.

The whole state row is rewritten every cycle, so a WAL that is never truncated
grows without limit: `account.db-wal` reached 872 MB in two days while
`account.db` itself stayed at 1.2 MB.  Everything here is best effort - a
maintenance failure must never abort a trading cycle or touch the account.
"""
import os
import re
import sqlite3
from datetime import datetime, timedelta

WAL_TRUNCATE_BYTES = 64 * 1024 * 1024
EVENT_LIMIT = 300
RECEIPT_LIMIT = 200
# table -> (timestamp column, days, extra predicate)
RETENTION = {"ai_jobs": ("created_at", 14, None),
             "automatic_research_runs": ("started_at", 90, None),
             "commands": ("created_at", 30, "status!='pending'")}


def _epoch(value):
    """Parse the two timestamp shapes this project writes: Python isoformat with
    an offset and Go RFC3339Nano in UTC."""
    text = str(value).replace("Z", "+00:00")
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    return datetime.fromisoformat(text).timestamp()


def wal_bytes(path):
    try:
        return os.path.getsize(str(path) + "-wal")
    except OSError:
        return 0


def checkpoint(db, path):
    """Checkpoint passively every cycle and truncate only when the file is large.

    Truncation needs the exclusive checkpoint lock, so it is size triggered: the
    writer must never wait on it every three minutes.
    """
    try:
        if wal_bytes(path) >= WAL_TRUNCATE_BYTES:
            return db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        return db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    except sqlite3.Error:
        return None


def slim_state(state):
    """Keep the history the console shows; drop what only inflates each write.

    The UI labels its decision log "最近 300 条" and the AI task list shows the
    newest twenty jobs, so a larger payload is pure write amplification.
    """
    events = state.get("events")
    if isinstance(events, list) and len(events) > EVENT_LIMIT:
        state["events"] = events[-EVENT_LIMIT:]
    receipts = state.get("command_receipts")
    if isinstance(receipts, list) and len(receipts) > RECEIPT_LIMIT:
        state["command_receipts"] = receipts[-RECEIPT_LIMIT:]


def _prune_table(db, table, column, days, now, where=None):
    query = "SELECT rowid,%s FROM %s" % (column, table)
    if where:
        query += " WHERE " + where
    try:
        rows = db.execute(query).fetchall()
    except sqlite3.Error:
        return 0
    cutoff = now.timestamp() - days * 86400
    stale = []
    for rowid, value in rows:
        try:
            if _epoch(value) < cutoff:
                stale.append(rowid)
        except (ValueError, TypeError, OverflowError):
            continue
    for offset in range(0, len(stale), 500):
        chunk = stale[offset:offset + 500]
        try:
            db.execute("DELETE FROM %s WHERE rowid IN (%s)" % (table, ",".join("?" * len(chunk))), chunk)
        except sqlite3.Error:
            return offset
    return len(stale)


def prune(control, journal, now):
    """Delete audit rows past retention; positions, trades and decisions in the
    attribution window are never touched."""
    removed = {}
    for table, (column, days, where) in RETENTION.items():
        count = _prune_table(control, table, column, days, now, where)
        if count:
            removed[table] = count
    try:
        cursor = journal.execute("DELETE FROM decisions WHERE trade_date < ?",
                                 ((now.date() - timedelta(days=180)).isoformat(),))
        if cursor.rowcount > 0:
            removed["decisions"] = cursor.rowcount
        cursor = journal.execute("DELETE FROM runs WHERE at < ?", ((now - timedelta(days=30)).isoformat(),))
        if cursor.rowcount > 0:
            removed["runs"] = cursor.rowcount
    except sqlite3.Error:
        pass
    return removed
