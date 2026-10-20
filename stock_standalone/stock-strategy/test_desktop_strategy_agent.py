"""Desktop evidence/registration preparation tests without model/network calls."""
import configparser
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from desktop_strategy_agent import DesktopPeer,ats_evidence,research_schema
from follow_ai import RESPONSE_SCHEMA


class DesktopAgentTests(unittest.TestCase):
    def test_strategy_usage_is_recorded_and_budget_interrupts_without_model_call(self):
        from desktop_strategy_agent import AppServer
        from follow_ai import digest
        context={'stocks':[], 'trade_date':'2026-10-20'}
        proposal={'market_view':'fixture','rotation_view':'fixture','answer':'fixture','plans':[]}
        for budget, expected_error in ((1000, True),(2000, False)):
            app=AppServer.__new__(AppServer);app.tool_audit=[]
            calls=[]
            def request(method, arguments, **kwargs):
                calls.append(method)
                if method=='thread/start': return {'thread':{'id':'thread'},'model':'gpt-6-luna','reasoningEffort':'low'}
                if method=='turn/start': return {'turn':{'id':'turn'}}
                return {}
            app.request=request
            events=iter([
                {'method':'thread/tokenUsage/updated','params':{'threadId':'thread','tokenUsage':{'last':{'totalTokens':1200,'inputTokens':1100,'outputTokens':100}}}},
                {'method':'item/completed','params':{'threadId':'thread','item':{'type':'agentMessage','text':json.dumps(proposal)}}},
                {'method':'turn/completed','params':{'threadId':'thread','turn':{'id':'turn','status':'completed'}}},
            ])
            app.event=lambda timeout: next(events)
            job={'id':'fixture','context':context,'evidence_hash':digest(context),'token_budget':budget}
            with patch.object(app,'readonly_overrides',return_value={}), \
                 patch('muse_research_threads.ensure_project',return_value='project'), \
                 patch('muse_research_threads.thread_title',return_value='fixture'), \
                 patch('muse_research_threads.research_prompt',return_value='fixture'), \
                 patch('muse_research_threads.publish_summary'):
                if expected_error:
                    with self.assertRaisesRegex(ValueError,'CLI_TOKEN_BUDGET_EXCEEDED'):
                        app.analyze(job,model='gpt-6-luna',effort='low')
                    self.assertIn('turn/interrupt',calls)
                else:
                    result=app.analyze(job,model='gpt-6-luna',effort='low')
                    self.assertEqual(result['token_usage']['totalTokens'],1200)

    def test_per_job_schema_restricts_exact_symbols_without_mutating_global(self):
        first=research_schema({'stocks':[{'symbol':'002343.SZ','name':'慈文传媒'}]})
        second=research_schema({'stocks':[{'symbol':'603533.SH'}]})
        self.assertEqual(first['properties']['plans']['items']['properties']['symbol']['enum'],['002343.SZ'])
        self.assertEqual(second['properties']['plans']['items']['properties']['symbol']['enum'],['603533.SH'])
        self.assertNotIn('enum',RESPONSE_SCHEMA['properties']['plans']['items']['properties']['symbol'])
        self.assertIn('stock:002343.SZ',first['properties']['plans']['items']['properties']['evidence_refs']['items']['enum'])

    def test_ats_evidence_is_readonly_and_has_original_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'trading_signals.db'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE signal_history(date TEXT,code TEXT,name TEXT,price REAL,action TEXT,reason TEXT,resample TEXT)')
                db.execute('INSERT INTO signal_history VALUES(?,?,?,?,?,?,?)',('2026-10-13','600001','synthetic',10,'OBSERVE','historical','5'))
                db.commit()
            before=path.read_bytes();e=ats_evidence(root,['600001.SH'])
            self.assertEqual(e['signals'][0]['date'],'2026-10-13')
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse(e['shared_context'])

    def test_prepare_does_not_change_existing_identity_or_key(self):
        spec=importlib.util.spec_from_file_location('bridge_runner',Path(__file__).parent/'tools/run_desktop_strategy_bridge.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory);config,cfg=runner.prepare(runtime,'http://127.0.0.1:20084')
            first=DesktopPeer(config);key=(runtime/'peer.key').read_bytes()
            runner.prepare(runtime,'http://127.0.0.1:20084')
            second=DesktopPeer(config)
            self.assertEqual(first.node,second.node);self.assertEqual(first.workspace,second.workspace)
            self.assertEqual((runtime/'peer.key').read_bytes(),key)
            self.assertFalse((runtime/'gateway.db').exists())

    def test_bridge_lock_is_exclusive_across_processes(self):
        spec=importlib.util.spec_from_file_location('bridge_runner',Path(__file__).parent/'tools/run_desktop_strategy_bridge.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory)
            first=runner.acquire_bridge_lock(runtime)
            self.assertIsNotNone(first)
            code=("import importlib.util,sys;from pathlib import Path;"
                  "p=Path(sys.argv[1]);s=importlib.util.spec_from_file_location('bridge_runner',p);"
                  "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                  "print('locked' if m.acquire_bridge_lock(Path(sys.argv[2])) is None else 'acquired')")
            result=subprocess.run([sys.executable,'-c',code,str(Path(__file__).parent/'tools/run_desktop_strategy_bridge.py'),str(runtime)],
                capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),'locked')
            first.close()

if __name__=='__main__':unittest.main()
