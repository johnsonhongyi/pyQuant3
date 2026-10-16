"""No real model calls: burst delivery, slow network, deadlines and engine reuse."""
import json
import io
import hashlib
import hmac
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from desktop_bridge_runtime import EventInbox, AppServerPool, ProgressPublisher, ResultOutbox
from desktop_chat import run_chat


class RuntimeTests(unittest.TestCase):
    def test_publisher_shutdown_cancels_blocked_network_request(self):
        entered,released=threading.Event(),threading.Event()
        peer=Mock()
        def blocked(*args,**kwargs):entered.set();released.wait(5);raise OSError('cancelled request')
        peer.post.side_effect=blocked
        peer.cancel_request.side_effect=lambda thread_id:released.set()
        publisher=ProgressPublisher(peer,{'id':'job','lease_token':'token'},Mock())
        publisher.publish({'content':'pending'})
        self.assertTrue(entered.wait(1))
        publisher.close()
        self.assertFalse(publisher.thread.is_alive())
        peer.cancel_request.assert_called_once_with(publisher.thread.ident)

    def test_http_keepalive_preserves_hmac_and_conflict_reason(self):
        from desktop_strategy_agent import DesktopPeer,_error_details
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'key').write_bytes(b'k'*32)
            (root/'bridge.ini').write_bytes(b'[bridge]\nstock_strategy_base_url=http://127.0.0.1:20084\nipc_node_id=node\nipc_workspace_id=workspace\nipc_key_file=key\n')
            peer=DesktopPeer(root/'bridge.ini')
            good=Mock(status=200,reason='OK',headers={});good.read.return_value=b'{"status":"stored"}'
            conflict=Mock(status=409,reason='Conflict',headers={});conflict.read.return_value=b'{"code":"CHAT_CANCELLED"}'
            connection=Mock();connection.getresponse.side_effect=[good,conflict]
            with patch('desktop_strategy_agent.http.client.HTTPConnection',return_value=connection) as factory:
                peer.post('heartbeat',{'status':'ready'})
                with self.assertRaises(HTTPError) as raised:peer.post('chat_result',{'id':'job'})
                self.assertEqual(factory.call_count,1)
                self.assertEqual(_error_details(raised.exception)['reason_code'],'CHAT_CANCELLED')
                self.assertIsNone(peer.connections.http)
                method,path=connection.request.call_args_list[0].args
                body=connection.request.call_args_list[0].kwargs['body'];headers=connection.request.call_args_list[0].kwargs['headers']
                canonical='\n'.join((method,path,hashlib.sha256(body).hexdigest(),headers['X-Linkage-Timestamp'],headers['X-Linkage-Nonce'],'node','workspace'))
                self.assertEqual(headers['X-Linkage-Signature'],hmac.new(b'k'*32,canonical.encode(),hashlib.sha256).hexdigest())
                connection.close.assert_called_once()

    def test_rpc_reply_is_routed_without_consuming_burst_notifications(self):
        from desktop_strategy_agent import AppServer
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fake_engine.py'
            path.write_bytes(('import json,sys\nfor line in sys.stdin:\n m=json.loads(line)\n if "id" not in m:continue\n if m["method"]!="initialize":\n  for _ in range(2000):print(json.dumps({"method":"item/agentMessage/delta","params":{"threadId":"test","delta":"x"}}))\n  print(json.dumps({"method":"turn/completed","params":{"threadId":"test"}}))\n print(json.dumps({"id":m["id"],"result":{"ok":True}}),flush=True)\n').encode('utf-8'))
            spawn=subprocess.Popen
            with patch('desktop_strategy_agent.subprocess.Popen',side_effect=lambda *a,**kw:spawn([sys.executable,'-u',str(path)],**kw)):
                app=AppServer('fake',Path(directory))
                try:
                    self.assertEqual(app.request('test',{}),{'ok':True})
                    text=''
                    while True:
                        event=app.event(1)
                        if event.get('method')=='turn/completed':break
                        text+=event.get('params',{}).get('delta','')
                    self.assertEqual(text,'x'*2000)
                finally:app.close()

    def test_burst_deltas_are_coalesced_without_losing_terminal_event(self):
        inbox = EventInbox(max_events=8)
        for _ in range(2000):
            inbox.put({'method':'item/agentMessage/delta','params':{'threadId':'thread','delta':'中'}})
        inbox.put({'method':'turn/completed','params':{'turn':{'id':'turn','status':'completed'}}})
        self.assertEqual(inbox.get(0)['params']['delta'],'中'*2000)
        self.assertEqual(inbox.get(0)['method'],'turn/completed')
        with self.assertRaises(queue.Empty):inbox.get(0)

    def test_overflow_fails_explicitly_and_closed_transport_wakes_consumer(self):
        inbox = EventInbox(max_events=1)
        inbox.put({'method':'one'})
        with self.assertRaises(BufferError):inbox.put({'method':'turn/completed'})
        inbox.get(0);inbox.close()
        with self.assertRaises(OSError):inbox.get(10)

    def test_slow_network_does_not_block_publishing_and_progress_is_bounded(self):
        entered,release=threading.Event(),threading.Event()
        def post(*args,**kwargs):entered.set();release.wait(2)
        peer=Mock();peer.post.side_effect=post
        publisher=ProgressPublisher(peer,{'id':'job','lease_token':'lease'},Mock())
        try:
            publisher.publish({'content':'first'})
            self.assertTrue(entered.wait(1))
            started=time.monotonic()
            for i in range(2000):publisher.publish({'content':str(i)})
            self.assertLess(time.monotonic()-started,1)
            self.assertEqual(publisher.latest['content'],'1999')
        finally:release.set();publisher.close()

    def test_cancelled_lease_is_delivered_to_event_consumer(self):
        error=HTTPError('http://localhost',409,'Conflict',{},io.BytesIO(b'{}'));error.peer_code='CHAT_CANCELLED'
        peer=Mock();peer.post.side_effect=error
        publisher=ProgressPublisher(peer,{'id':'job','lease_token':'lease'},Mock())
        try:
            publisher.publish({'content':''});publisher.thread.join(1)
            with self.assertRaises(HTTPError):publisher.check()
        finally:publisher.close()

    def test_pool_reuses_healthy_engine_and_restarts_after_same_path_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=Path(directory)/'engine.exe';engine.write_bytes(b'first')
            def factory(*args,**kwargs):
                app=Mock();app.process.poll.return_value=None;app.error=None;app.messages=EventInbox();app.tool_audit=[]
                return app
            make=Mock(side_effect=factory);pool=AppServerPool(make,Path(directory))
            first=pool.acquire(str(engine));pool.release(True)
            self.assertIs(pool.acquire(str(engine)),first)
            engine.write_bytes(b'upgraded engine')
            second=pool.acquire(str(engine));self.assertIsNot(second,first)
            first.close.assert_called_once();pool.release(False)
            second.close.assert_called_once();self.assertEqual(make.call_count,2)

    def test_expired_remaining_budget_does_not_start_model(self):
        with tempfile.TemporaryDirectory() as directory,sqlite3.connect(':memory:') as db,patch('desktop_strategy_agent.AppServer') as factory:
            job={'id':'job','lease_token':'lease','remaining_seconds':1,'context':{'model':'luna','reasoning_effort':'low','prompt':'test'}}
            peer=Mock()
            run_chat(peer,job,'unused',Path(directory),[{'id':'luna','efforts':['low']}],Mock(),db,Mock())
            factory.assert_not_called()
            self.assertEqual(peer.post.call_args.args[1]['result']['error_code'],'MODEL_TIMEOUT')

    def test_unknown_prior_turn_is_not_reexecuted_after_reclaim(self):
        with tempfile.TemporaryDirectory() as directory,sqlite3.connect(':memory:') as db,patch('desktop_strategy_agent.AppServer') as factory:
            db.execute('CREATE TABLE chat_attempts(id TEXT PRIMARY KEY,thread_id TEXT,turn_id TEXT,state TEXT,updated_at REAL)')
            db.execute("INSERT INTO chat_attempts VALUES('job','thread',NULL,'starting',0)")
            job={'id':'job','lease_token':'new-lease','context':{'model':'luna','reasoning_effort':'low','prompt':'test'}}
            peer=Mock()
            run_chat(peer,job,'unused',Path(directory),[{'id':'luna','efforts':['low']}],Mock(),db,Mock())
            factory.assert_not_called()
            self.assertEqual(peer.post.call_args.args[1]['result']['error_code'],'CHAT_INTERRUPTED_RETRY_REQUIRED')

    def test_outbox_replays_persisted_result_without_an_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'agent.db'
            db=sqlite3.connect(path)
            try:
                ResultOutbox.prepare(db)
                job={'id':'job','lease_token':'lease'};result={'content':'persisted'}
                ResultOutbox.stage(db,'chat_result',job,result)
                db.execute('UPDATE result_outbox SET next_retry=0');db.commit()
                sent=threading.Event();peer=Mock();peer.post.side_effect=lambda *a,**kw:sent.set()
                worker=ResultOutbox(peer,path)
                try:self.assertTrue(sent.wait(2))
                finally:worker.close()
                self.assertEqual(peer.post.call_args.args[1]['result'],result)
                self.assertIsNotNone(db.execute('SELECT delivered_at FROM result_outbox').fetchone()[0])
            finally:db.close()

    def test_retention_keeps_unacknowledged_results(self):
        with sqlite3.connect(':memory:') as db:
            ResultOutbox.prepare(db)
            db.execute('CREATE TABLE chat_results(id TEXT PRIMARY KEY,result TEXT)')
            for identity in ('pending','confirmed'):
                db.execute('INSERT INTO chat_results VALUES(?,?)',(identity,'result'))
                ResultOutbox.stage(db,'chat_result',{'id':identity,'lease_token':'lease'},{'content':identity})
            db.execute("UPDATE result_outbox SET delivered_at=1 WHERE id='confirmed'");db.commit()
            ResultOutbox.prune(db,now=40*86400)
            self.assertEqual(db.execute('SELECT id FROM chat_results').fetchall(),[('pending',)])
