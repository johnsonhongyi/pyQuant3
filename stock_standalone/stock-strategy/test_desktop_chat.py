import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from desktop_chat import run_chat

THREAD='01a13f4b-5f5a-7fb0-990c-a22bdbe42f68'


class App:
    def __init__(self,*args,**kwargs):self.calls=[];self.active_thread=None;self.tool_audit=[];self.closed=False
    def request(self,method,params,**kwargs):
        self.calls.append((method,params))
        if method in ('thread/start','thread/resume'):return {'thread':{'id':THREAD},'model':'gpt-6-luna','reasoningEffort':'low'}
        if method=='turn/start':return {'turn':{'id':'turn'}}
        return {}
    def event(self,timeout):return {'method':'turn/completed','params':{'threadId':THREAD,'turn':{'id':'turn','status':'completed'}}}
    def close(self):self.closed=True


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close)
        self.job={'id':'a'*32,'lease_token':'lease','context':{'model':'gpt-6-luna','reasoning_effort':'low','prompt':'hello','messages':[],'thread_id':THREAD}}
        self.peer=Mock();self.sidebar=Mock();self.app=App()
        self.model=[{'id':'gpt-6-luna','efforts':['low'],'default_effort':'low'}]

    def run_chat(self):
        with tempfile.TemporaryDirectory() as directory,patch('desktop_strategy_agent.AppServer',return_value=self.app),patch('muse_research_threads.ensure_project',return_value='project'):
            run_chat(self.peer,self.job,'installed-engine',Path(directory),self.model,self.sidebar,self.db,Mock())

    def test_cancelled_lease_interrupts_native_turn_and_closes(self):
        self.peer.post.side_effect=OSError('cancelled lease')
        self.run_chat()
        self.assertTrue(self.app.closed)
        self.assertIn('turn/interrupt',[m for m,_ in self.app.calls])
        self.assertIn('thread/resume',[m for m,_ in self.app.calls])

    def test_completed_result_is_cached_before_return_and_replayed_without_model(self):
        self.db.execute('CREATE TABLE chat_results(id TEXT PRIMARY KEY,result TEXT NOT NULL)')
        result={'content':'cached answer','thread_id':THREAD}
        self.db.execute('INSERT INTO chat_results VALUES(?,?)',(self.job['id'],json.dumps(result)));self.db.commit()
        self.run_chat();self.assertEqual(self.app.calls,[])
        self.assertEqual(self.peer.post.call_args.args[1]['result']['content'],'cached answer')

    def test_context_model_is_validated_before_native_start(self):
        self.job['context']['model']='not-installed';self.run_chat()
        self.assertEqual(self.app.calls,[])
        self.assertEqual(self.peer.post.call_args.args[1]['status'],'failed')


if __name__=='__main__':unittest.main()
