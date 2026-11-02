"""WAL bounding, retention and state slimming; no network, no account changes."""
import json
import sqlite3
import unittest
from datetime import timedelta
from pathlib import Path
import tempfile

import auto_follow as af
import housekeeping as hk
from test_auto_follow import NOW


class HousekeepingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "account.db"
        self.db = af.connect(self.path)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_state_slimming_keeps_the_history_the_console_shows(self):
        state = {"events": [{"at": NOW.isoformat(), "action": "CONTROL", "index": index} for index in range(900)],
                 "command_receipts": [["id%d" % index, "applied", NOW.isoformat(), "ok"] for index in range(400)]}
        hk.slim_state(state)
        self.assertEqual(len(state["events"]), hk.EVENT_LIMIT)
        self.assertEqual(state["events"][-1]["index"], 899)
        self.assertEqual(len(state["command_receipts"]), hk.RECEIPT_LIMIT)

    def test_checkpoint_keeps_the_wal_file_small(self):
        payload = "x" * 400000
        for index in range(30):
            self.db.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps({"n": index, "payload": payload}),))
            self.db.commit()
            hk.checkpoint(self.db, self.path)
        # 12 MB written; a WAL that is never reused would hold all of it.
        self.assertLess(hk.wal_bytes(self.path), 8 * 1024 * 1024)

    def test_retention_deletes_only_rows_past_the_window(self):
        self.db.close()
        control_path = self.path.with_name("control.db")
        control = af.connect_control(self.path)
        control.execute("CREATE TABLE IF NOT EXISTS ai_jobs(id TEXT PRIMARY KEY,created_at TEXT NOT NULL)")
        control.execute("CREATE TABLE IF NOT EXISTS automatic_research_runs(job_id TEXT PRIMARY KEY,day TEXT NOT NULL,"
                        "started_at TEXT NOT NULL,token_budget INTEGER NOT NULL,total_tokens INTEGER,usage_known INTEGER NOT NULL DEFAULT 0)")
        control.execute("CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,action TEXT NOT NULL,payload TEXT NOT NULL,"
                        "created_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',applied_at TEXT,result TEXT)")
        old = (NOW - timedelta(days=40)).isoformat()
        recent = (NOW - timedelta(days=1)).isoformat()
        control.execute("INSERT INTO ai_jobs VALUES('old',?)", (old,))
        control.execute("INSERT INTO ai_jobs VALUES('recent',?)", (recent,))
        control.execute("INSERT INTO commands(id,action,payload,created_at,status) VALUES('c1','pause','{}',?,'applied')", (old,))
        control.execute("INSERT INTO commands(id,action,payload,created_at,status) VALUES('c2','pause','{}',?,'pending')", (old,))
        control.execute("INSERT INTO automatic_research_runs VALUES('j1','2026-01-01',?,1000,0,1)", (old,))
        journal = sqlite3.connect(str(self.path.with_name("loop.db")), isolation_level=None)
        journal.executescript("CREATE TABLE IF NOT EXISTS decisions(trade_date TEXT NOT NULL, symbol TEXT NOT NULL);"
                              "CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, body TEXT);")
        journal.execute("INSERT INTO decisions VALUES('2025-01-01','600001.SH')")
        journal.execute("INSERT INTO decisions VALUES(?,'600002.SH')", (NOW.date().isoformat(),))
        removed = hk.prune(control, journal, NOW)
        self.assertEqual(removed["ai_jobs"], 1)
        self.assertEqual(removed["commands"], 1)
        self.assertEqual(removed["decisions"], 1)
        self.assertEqual(control.execute("SELECT count(*) FROM ai_jobs").fetchone()[0], 1)
        self.assertEqual(control.execute("SELECT id FROM commands").fetchone()[0], 'c2')
        self.assertEqual(journal.execute("SELECT count(*) FROM decisions").fetchone()[0], 1)
        journal.close()
        control.close()

    def test_missing_tables_never_break_a_cycle(self):
        self.assertEqual(hk.prune(self.db, self.db, NOW), {})


if __name__ == "__main__":
    unittest.main()
