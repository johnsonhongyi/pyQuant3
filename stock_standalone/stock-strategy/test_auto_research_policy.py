"""No network or inference; legacy switches cannot bypass automatic admission."""
import json
import sqlite3
import unittest
import auto_follow as af
import follow_ai as ai
from auto_research_policy import DEFAULT
from test_auto_follow import NOW


class AutomaticResearchPolicyTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        ai.init_ai(self.db)
        self.db.executescript('CREATE TABLE automatic_research_policy(id INTEGER PRIMARY KEY,body TEXT);CREATE TABLE desktop_chat_config(id INTEGER PRIMARY KEY,body TEXT);')
        self.state=af.initial()
        self.state['ai_settings']={**ai.DEFAULT_AI,'enabled':True,'node_id':'legacy','workspace_id':'old','model':'expensive','reasoning_effort':'high'}
        self.state['candidates']=[{'symbol':'600001.SH'}]
        self.runtime={'provider':'codex_desktop','node_id':'chosen','workspace_id':'ws','model':'gpt-6-luna','reasoning_effort':'low'}
        self.db.execute('INSERT INTO desktop_chat_config VALUES(1,?)',(json.dumps(self.runtime),))
        self.db.execute('INSERT INTO ai_desktop VALUES(?,?,?,?,?)',('chosen','ws',NOW.isoformat(),'ready',json.dumps({'capabilities':['strategy_research'],'models':[{'id':'gpt-6-luna','efforts':['low']}]})))

    def tearDown(self): self.db.close()

    def enable(self):
        self.db.execute('INSERT INTO automatic_research_policy VALUES(1,?)',(json.dumps({**DEFAULT,'enabled':True,'revision':4}),))

    def test_old_enabled_configuration_stays_off_until_explicit_opt_in(self):
        self.assertIsNone(ai.enqueue(self.db,self.state,NOW,force=True))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ai_jobs').fetchone()[0],0)

    def test_new_job_inherits_exact_system_model_and_keeps_account_unchanged(self):
        self.enable()
        cash=self.state['cash'];identity=ai.enqueue(self.db,self.state,NOW)
        node,ws,raw=self.db.execute('SELECT node_id,workspace_id,context FROM ai_jobs WHERE id=?',(identity,)).fetchone()
        self.assertEqual((node,ws),('chosen','ws'))
        self.assertEqual(json.loads(raw)['ai_runtime'],{'model':'gpt-6-luna','reasoning_effort':'low'})
        self.assertEqual(self.state['cash'],cash)
        self.assertEqual(json.loads(raw)['auto_research_revision'],4)

    def test_model_missing_does_not_fall_back_to_another_online_bridge(self):
        self.enable();self.db.execute("UPDATE ai_desktop SET status='degraded'")
        self.db.execute('INSERT INTO ai_desktop VALUES(?,?,?,?,?)',('other','ws',NOW.isoformat(),'ready',json.dumps({'capabilities':['strategy_research'],'models':[{'id':'other','efforts':['high']}]})))
        self.assertIsNone(ai.enqueue(self.db,self.state,NOW))
        self.assertEqual(self.state['auto_research_status'],'model_unavailable')

    def test_force_does_not_bypass_interval(self):
        self.enable();self.state['ai_last_requested_at']=NOW.isoformat()
        self.assertIsNone(ai.enqueue(self.db,self.state,NOW,force=True,stage='execution_review'))

    def test_corrupt_catalog_pauses_instead_of_crashing_worker(self):
        self.enable()
        for detail in ([], {'models':['unexpected']}, {'models':None}, {'models':[{'id':'gpt-6-luna','efforts':'low'}]}):
            self.db.execute('UPDATE ai_desktop SET detail=?',(json.dumps(detail),))
            self.assertIsNone(ai.enqueue(self.db,self.state,NOW))
            self.assertEqual(self.state['auto_research_status'],'model_unavailable')

    def test_nanosecond_heartbeat_parsed_successfully(self):
        self.enable()
        self.db.execute("UPDATE ai_desktop SET heartbeat='2026-10-21T03:53:57.128216038Z'")
        from datetime import datetime
        test_now = datetime.fromisoformat('2026-10-21T03:54:10+00:00')
        identity = ai.enqueue(self.db, self.state, test_now)
        self.assertIsNotNone(identity)
        self.assertEqual(self.state['auto_research_status'], 'ready')
