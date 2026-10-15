"""Isolated contract tests; never calls Codex, the network, or real execution."""
import copy
import json
import sqlite3
import unittest
from datetime import timedelta

import auto_follow as af
import follow_ai as ai
from test_auto_follow import NOW


class AIFollowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        ai.init_ai(self.db)
        self.state = af.initial()
        self.state["ai_settings"] = {**ai.DEFAULT_AI, "enabled": True, "node_id": "desktop-test", "workspace_id": "workspace-test"}
        self.state["candidates"] = [{"symbol": "600001.SH", "name": "synthetic", "route": "theme_trend"}]
        self.context = ai.evidence_context(self.state, NOW)
        self.proposal = {"market_view": "synthetic", "rotation_view": "missing", "answer": "test only",
            "plans": [{"symbol": "600001.SH", "action": "follow", "thesis": "synthetic", "entry_low": 10,
                "entry_high": 11, "invalidation": "below range", "exit_response": "original risk gate",
                "evidence_refs": ["stock:600001.SH"], "missing_data": []}]}

    def tearDown(self):
        self.db.close()

    def test_disabled_default_does_not_enqueue(self):
        self.state.pop("ai_settings")
        self.assertIsNone(ai.enqueue(self.db, self.state, NOW))

    def test_automatic_jobs_deduplicate_and_preserve_account(self):
        identity = ai.enqueue(self.db, self.state, NOW)
        self.assertEqual(ai.enqueue(self.db, self.state, NOW + timedelta(seconds=60)), identity)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM ai_jobs").fetchone()[0], 1)
        self.assertEqual(self.state["cash"], 500000)
        self.assertEqual(self.state["positions"], [])

    def test_follow_requires_known_stock_evidence_and_valid_range(self):
        ai.validate_result(self.proposal, self.context)
        for change in ({"symbol": "600002.SH"}, {"evidence_refs": ["invented"]},
                       {"entry_low": True}, {"entry_low": 12}, {"entry_high": None}):
            bad = copy.deepcopy(self.proposal)
            bad["plans"][0].update(change)
            with self.assertRaises(ValueError):
                ai.validate_result(bad, self.context)

    def test_shadow_preserves_existing_admission(self):
        self.assertEqual(ai.ai_entry_gate(self.state, "600001.SH", 10.2, NOW)["mode"], "shadow")

    def test_enforce_requires_current_proposal_and_price_range(self):
        self.state["ai_settings"]["mode"] = "enforce"
        with self.assertRaises(ValueError):
            ai.ai_entry_gate(self.state, "600001.SH", 10.2, NOW)
        self.state["ai_latest"] = {"id": "test-job", "trade_date": NOW.date().isoformat(), "as_of": NOW.isoformat(),
            "evidence_hash": ai.digest(self.context), "result": {"proposal": self.proposal, "thread_id": "test-thread"}}
        self.assertEqual(ai.ai_entry_gate(self.state, "600001.SH", 10.2, NOW)["status"], "admitted")
        for price, at in ((12, NOW), (10.2, NOW + timedelta(seconds=301))):
            with self.assertRaises(ValueError):
                ai.ai_entry_gate(self.state, "600001.SH", price, at)

    def test_sync_rejects_invalid_result_and_expires_pending_job(self):
        identity = ai.enqueue(self.db, self.state, NOW)
        self.db.execute("UPDATE ai_jobs SET status='completed',result=? WHERE id=?", (json.dumps({"proposal": {}}), identity))
        ai.sync_ai(self.db, self.state, NOW)
        self.assertNotIn("ai_latest", self.state)
        self.assertEqual(self.state["ai"]["jobs"][0]["status"], "invalid_result")
        another = ai.enqueue(self.db, self.state, NOW, question="synthetic", force=True)
        ai.sync_ai(self.db, self.state, NOW + timedelta(minutes=11))
        self.assertEqual(self.db.execute("SELECT status FROM ai_jobs WHERE id=?", (another,)).fetchone()[0], "expired")


if __name__ == "__main__":
    unittest.main()
