"""Isolated contract tests; never calls Codex, the network, or real execution."""
import copy
import json
import sqlite3
import unittest
from datetime import timedelta

import auto_follow as af
import follow_ai as ai
from test_auto_follow import NOW, Calendar


class AIFollowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        ai.init_ai(self.db)
        self.state = af.initial()
        self.state["ai_settings"] = {**ai.DEFAULT_AI, "enabled": True, "node_id": "desktop-test", "workspace_id": "workspace-test"}
        self.db.executescript('CREATE TABLE automatic_research_policy(id INTEGER PRIMARY KEY,body TEXT); CREATE TABLE desktop_chat_config(id INTEGER PRIMARY KEY,body TEXT);')
        from auto_research_policy import DEFAULT
        self.db.execute('INSERT INTO automatic_research_policy VALUES(1,?)', (json.dumps({**DEFAULT, 'enabled': True}),))
        self.db.execute('INSERT INTO desktop_chat_config VALUES(1,?)', (json.dumps({'provider':'codex_desktop','node_id':'desktop-test','workspace_id':'workspace-test','model':'gpt-6-luna','reasoning_effort':'low'}),))
        self.db.execute('INSERT INTO ai_desktop VALUES(?,?,?,?,?)', ('desktop-test','workspace-test',NOW.isoformat(),'ready',json.dumps({'capabilities':['strategy_research'],'models':[{'id':'gpt-6-luna','efforts':['low']}]})))
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
        self.db.execute('DELETE FROM automatic_research_policy')
        self.assertIsNone(ai.enqueue(self.db, self.state, NOW))

    def test_bridge_settings_preserve_cadence_and_frozen_jobs(self):
        import tempfile
        from pathlib import Path
        self.state["ai_settings"].update(interval_seconds=720, mode="enforce", model="gpt-6-luna", reasoning_effort="max")
        job = ai.enqueue(self.db, self.state, NOW, force=True)
        frozen = self.db.execute("SELECT context FROM ai_jobs WHERE id=?", (job,)).fetchone()[0]
        before = (self.state["cash"], self.state["positions"], self.state["enabled"], self.state["kill"])
        with tempfile.TemporaryDirectory() as folder:
            control = af.connect_control(Path(folder) / "account.db")
            try:
                payload = {"enabled": True, "mode": "enforce", "node_id": "active-bridge", "workspace_id": "active-workspace", "model": "gpt-6-luna", "reasoning_effort": "max"}
                control.execute("INSERT INTO commands(id,action,payload,created_at) VALUES('auto-bridge-test','ai_settings',?,?)", (json.dumps(payload), NOW.isoformat()))
                af.apply_commands(control, self.state, NOW)
            finally:
                control.close()
        self.assertEqual(self.state["ai_settings"]["node_id"], "active-bridge")
        self.assertEqual(self.state["ai_settings"]["interval_seconds"], 720)
        self.assertEqual(before, (self.state["cash"], self.state["positions"], self.state["enabled"], self.state["kill"]))
        self.assertEqual(self.db.execute("SELECT context FROM ai_jobs WHERE id=?", (job,)).fetchone()[0], frozen)

    def test_model_and_effort_are_frozen_per_job(self):
        self.state['ai_settings'].update(model='gpt-6-luna',reasoning_effort='low')
        job=ai.enqueue(self.db,self.state,NOW,force=True)
        self.state['ai_settings'].update(model='gpt-6-sol',reasoning_effort='high')
        context=json.loads(self.db.execute('SELECT context FROM ai_jobs WHERE id=?',(job,)).fetchone()[0])
        self.assertEqual(context['ai_runtime'],{'model':'gpt-6-luna','reasoning_effort':'low'})

    def test_automatic_jobs_deduplicate_and_preserve_account(self):
        identity = ai.enqueue(self.db, self.state, NOW)
        self.assertEqual(ai.enqueue(self.db, self.state, NOW + timedelta(seconds=60)), identity)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM ai_jobs").fetchone()[0], 1)
        self.assertEqual(self.state["cash"], 500000)
        self.assertEqual(self.state["positions"], [])

    def test_large_optional_evidence_is_marked_and_bounded(self):
        self.state['events'] = [{'detail': '测' * 2000} for _ in range(30)]
        job = ai.enqueue(self.db, self.state, NOW)
        raw, evidence_hash = self.db.execute('SELECT context,evidence_hash FROM ai_jobs WHERE id=?', (job,)).fetchone()
        context = json.loads(raw)
        self.assertIn('recent_decisions', context['omitted_evidence'])
        self.assertEqual(context['stocks'][0]['symbol'], '600001.SH')
        self.assertEqual(ai.digest(context), evidence_hash)

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
        self.state.pop('ai_last_requested_at', None)
        another = ai.enqueue(self.db, self.state, NOW, question="synthetic", force=True)
        ai.sync_ai(self.db, self.state, NOW + timedelta(minutes=11))
        self.assertEqual(self.db.execute("SELECT status FROM ai_jobs WHERE id=?", (another,)).fetchone()[0], "expired")

    def test_execution_review_cannot_bypass_configured_interval(self):
        self.state['ai_last_requested_at'] = NOW.isoformat()
        self.state['closed'] = [{'symbol':'600001.SH','pnl':10}]
        ai.schedule_workflow(self.db,self.state,NOW,Calendar)
        rows=self.db.execute('SELECT context FROM ai_jobs').fetchall()
        self.assertEqual(len(rows),0)
        ai.schedule_workflow(self.db,self.state,NOW+timedelta(seconds=60),Calendar)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ai_jobs').fetchone()[0],0)

    def test_completed_review_never_overwrites_entry_admission(self):
        self.state['ai_latest']={'id':'entry-job','created_at':NOW.isoformat()}
        identity=ai.enqueue(self.db,self.state,NOW,force=True,stage='execution_review')
        self.db.execute('UPDATE ai_jobs SET status=?,result=? WHERE id=?',('completed',json.dumps({'proposal':self.proposal,'thread_id':'fixture'}),identity))
        ai.sync_ai(self.db,self.state,NOW)
        self.assertEqual(self.state['ai_latest']['id'],'entry-job')
        self.assertEqual(self.state['ai_review']['id'],identity)

    def test_sync_shows_jobs_after_switching_bridges(self):
        identity = ai.enqueue(self.db, self.state, NOW)
        self.state['ai_settings']['node_id'] = 'old-bridge'
        self.db.execute("UPDATE ai_jobs SET status='expired' WHERE id=?", (identity,))
        ai.sync_ai(self.db, self.state, NOW)
        self.assertEqual(self.state['ai']['jobs'][0]['id'], identity)
        self.assertEqual(self.state['ai']['jobs'][0]['error'], '等待桌面领取超时')
        self.assertTrue(self.state['ai']['desktop_online'])

    def test_corrupt_completed_result_is_observable_and_does_not_crash(self):
        identity=ai.enqueue(self.db,self.state,NOW)
        self.db.execute('UPDATE ai_jobs SET status=?,result=? WHERE id=?',('completed','not-json',identity))
        ai.sync_ai(self.db,self.state,NOW)
        self.assertEqual(self.state['ai']['jobs'][0]['status'],'invalid_result')

    def test_valid_entry_waiting_for_ai_triggers_one_fresh_research_job(self):
        self.state['ai_last_requested_at']=(NOW-timedelta(minutes=16)).isoformat()
        self.state['events']=[{'at':NOW.isoformat(),'action':'AI_DECISION','decision':{'reason':'AI proposal missing or expired'}}]
        ai.schedule_workflow(self.db,self.state,NOW,Calendar)
        row=self.db.execute('SELECT context FROM ai_jobs').fetchone()
        self.assertEqual(json.loads(row[0])['workflow_stage'],'intraday_refresh')
        ai.schedule_workflow(self.db,self.state,NOW+timedelta(seconds=120),Calendar)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ai_jobs').fetchone()[0],1)

    def _runs(self, rows):
        self.db.executescript('CREATE TABLE IF NOT EXISTS automatic_research_runs(job_id TEXT PRIMARY KEY,day TEXT NOT NULL,'
                              'started_at TEXT NOT NULL,token_budget INTEGER NOT NULL,total_tokens INTEGER,usage_known INTEGER NOT NULL DEFAULT 0);')
        for index, (day, tokens, known) in enumerate(rows):
            self.db.execute('INSERT INTO automatic_research_runs VALUES(?,?,?,?,?,?)',
                            ('run-%d' % index, day, NOW.isoformat(), 1000, tokens, known))

    def test_exhausted_daily_runs_never_queue_a_job_the_server_refuses(self):
        self._runs([(NOW.date().isoformat(), 1000, 1)] * 3)
        self.assertIsNone(ai.enqueue(self.db, self.state, NOW, force=True, stage='post_close_review'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ai_jobs').fetchone()[0], 0)
        self.assertEqual(self.state['auto_research_status'], 'budget_exhausted')
        self.assertEqual(self.state['auto_research_admission']['max_runs'], 3)

    def test_unsettled_usage_pauses_queueing(self):
        self._runs([(NOW.date().isoformat(), 0, 0)])
        self.assertIsNone(ai.enqueue(self.db, self.state, NOW, force=True))
        self.assertEqual(self.state['auto_research_status'], 'usage_unsettled')

    def test_cleared_usage_stops_counting_against_the_daily_limit(self):
        self._runs([(NOW.date().isoformat(), 1000, 1)] * 3)
        self.db.execute('ALTER TABLE automatic_research_runs ADD COLUMN cleared INTEGER NOT NULL DEFAULT 0')
        self.assertIsNone(ai.enqueue(self.db, self.state, NOW, force=True))
        self.assertEqual(self.state['auto_research_status'], 'budget_exhausted')
        # The console button clears the day; the rows stay for audit.
        self.db.execute('UPDATE automatic_research_runs SET cleared=1')
        identity = ai.enqueue(self.db, self.state, NOW, force=True)
        self.assertIsNotNone(identity)
        self.assertEqual(self.state['auto_research_admission']['status'], 'ready')

    def test_unclaimed_expiry_reports_server_budget_not_desktop(self):
        identity = ai.enqueue(self.db, self.state, NOW)
        self.state['auto_research_admission'] = {'status': 'budget_exhausted', 'runs': 20, 'max_runs': 12}
        self.db.execute("UPDATE ai_jobs SET status='expired' WHERE id=?", (identity,))
        ai.sync_ai(self.db, self.state, NOW)
        self.assertIn('额度', self.state['ai']['jobs'][0]['error'])

    def test_expired_review_is_retried_instead_of_losing_the_day(self):
        after_close = NOW.replace(hour=15, minute=40)
        self.db.execute('UPDATE ai_desktop SET heartbeat=?', (after_close.isoformat(),))
        identity = ai.enqueue(self.db, self.state, after_close, question='review', force=True, stage='post_close_review')
        self.db.execute("UPDATE ai_jobs SET status='expired' WHERE id=?", (identity,))
        self.state['ai_review_day'] = after_close.date().isoformat()
        self.state['ai_last_requested_at'] = (after_close - timedelta(minutes=61)).isoformat()
        ai.schedule_workflow(self.db, self.state, after_close + timedelta(minutes=1), Calendar)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ai_jobs').fetchone()[0], 2)
        self.assertEqual(ai.review_state(self.db, after_close.date().isoformat()), (False, 2))

    def test_generic_post_close_snapshot_never_overwrites_the_review(self):
        after_close = NOW.replace(hour=16, minute=5)
        self.db.execute('UPDATE ai_desktop SET heartbeat=?', (after_close.isoformat(),))
        identity = ai.enqueue(self.db, self.state, after_close, force=True)
        self.db.execute('UPDATE ai_jobs SET status=?,result=? WHERE id=?',
                        ('completed', json.dumps({'proposal': self.proposal, 'thread_id': 'fixture'}), identity))
        ai.sync_ai(self.db, self.state, after_close)
        self.assertNotIn('ai_review', self.state)
        self.assertEqual(self.state['ai_latest']['id'], identity)



if __name__ == "__main__":
    unittest.main()
