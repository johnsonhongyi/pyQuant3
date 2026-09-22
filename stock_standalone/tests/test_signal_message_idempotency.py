# -*- coding: utf-8 -*-
import sqlite3

from db_utils import SQLiteConnectionManager
from signal_message_queue import SignalMessage, SignalMessageQueue


def _queue_for_path(path):
    q = object.__new__(SignalMessageQueue)
    q.db_manager = SQLiteConnectionManager.get_instance(str(path))
    q._init_db()
    return q


def test_event_key_is_stable_and_code_is_canonicalized():
    key1 = SignalMessageQueue._build_event_key(
        "2026-09-22", "1", "S4", "ATS"
    )
    key2 = SignalMessageQueue._build_event_key(
        "2026-09-22", "000001", "S4", "ATS"
    )
    assert key1 == key2 == "2026-09-22|000001|S4|ATS"


def test_atomic_upsert_keeps_one_row_and_increments_count(tmp_path, monkeypatch):
    from JohnsonUtil import commonTips as cct

    monkeypatch.setattr(cct, "get_trade_date_status", lambda: True)
    monkeypatch.setattr(cct, "get_now_time_int", lambda: 1000)

    db_path = tmp_path / "signals.db"
    q = _queue_for_path(db_path)
    first = SignalMessage(
        priority=20,
        timestamp="2026-09-22 10:00:00",
        code="1",
        name="test",
        signal_type="S4",
        source="ATS",
        reason="first",
        score=80.0,
    )
    second = SignalMessage(
        priority=10,
        timestamp="2026-09-22 10:00:02",
        code="000001",
        name="test-new",
        signal_type="S4",
        source="ATS",
        reason="second",
        score=90.0,
    )
    q._persist_signal(first)
    q._persist_signal(second)

    conn = q.db_manager.get_connection()
    rows = conn.execute(
        "SELECT event_key, count, priority, score, reason "
        "FROM signal_message ORDER BY id"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "2026-09-22|000001|S4|ATS"
    assert rows[0][1] == 2
    assert rows[0][2] == 10
    assert rows[0][3] == 90.0
    assert rows[0][4] == "second"
    q.db_manager.close_thread_connection()


def test_legacy_duplicates_migrate_without_losing_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE signal_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            signal_type TEXT NOT NULL,
            source TEXT,
            priority INTEGER DEFAULT 50,
            score REAL,
            reason TEXT,
            evaluated INTEGER DEFAULT 0,
            created_date TEXT,
            count INTEGER DEFAULT 1,
            consecutive_days INTEGER DEFAULT 1,
            rank INTEGER DEFAULT 0,
            grade TEXT
        )
        """
    )
    for ts in ("2026-09-22 10:00:00", "2026-09-22 10:00:01"):
        conn.execute(
            "INSERT INTO signal_message "
            "(timestamp, code, signal_type, source, created_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (ts, "000001", "S4", "ATS", "2026-09-22"),
        )
    conn.commit()
    conn.close()

    q = _queue_for_path(db_path)
    conn = q.db_manager.get_connection()
    rows = conn.execute(
        "SELECT event_key FROM signal_message ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "2026-09-22|000001|S4|ATS"
    assert rows[1][0].startswith(
        "2026-09-22|000001|S4|ATS|legacy|"
    )
    indexes = conn.execute(
        "PRAGMA index_list(signal_message)"
    ).fetchall()
    unique_index = {
        row[1]: row[2] for row in indexes
    }
    assert unique_index["uq_signal_message_event_key"] == 1
    q.db_manager.close_thread_connection()
