import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from desktop_sidebar import SidebarOrganizer,SECTION_NAME,installed_runtime,AppTools

THREAD='01a13ec2-559c-70e3-9361-e6ebfc33a427'


class FakeApp:
    def __init__(self):self.sections=[];self.moves=0;self.creates=0;self.fail=False;self.unconfirmed=False
    def __call__(self,pipe,thread):self.pipe=pipe;return self
    def call(self,name,args):
        if self.fail:raise OSError('APP_TOOLS_DISCONNECTED')
        if name=='list_threads':return {'sections':self.sections}
        if name=='create_sidebar_section':
            self.creates+=1;self.sections=[{'name':SECTION_NAME,'sectionId':'section','itemKeys':[]}];return self.sections[0]
        if name=='move_thread_to_sidebar_section':
            self.moves+=1
            if not self.unconfirmed:self.sections[0]['itemKeys'].append('codex:thread:local:'+args['threadId'])
            return {}
    def close(self):pass


class SidebarTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close)
        self.now=100;self.app=FakeApp();self.organizer=SidebarOrganizer(self.db,self.app,lambda hint:['pipe-new'],lambda:self.now)

    def test_group_creation_placement_confirmation_and_idempotency(self):
        self.organizer.enqueue(THREAD,'job');self.organizer.drain();self.organizer.enqueue(THREAD,'job');self.organizer.drain()
        self.assertEqual((self.app.creates,self.app.moves),(1,1));self.assertEqual(self.organizer.status()['sidebar_pending'],0)

    def test_disconnect_survives_restart_and_rediscovery(self):
        self.app.fail=True;self.organizer.enqueue(THREAD,'job');self.organizer.drain()
        self.assertEqual(self.organizer.status()['sidebar_pending'],1)
        restarted=SidebarOrganizer(self.db,self.app,lambda hint:['upgraded-pipe'],lambda:self.now)
        self.now=111;self.app.fail=False;restarted.drain()
        self.assertEqual(self.app.pipe,'upgraded-pipe');self.assertEqual(restarted.status()['sidebar_pending'],0)

    def test_no_desktop_keeps_pending_with_backoff(self):
        self.organizer.discover=lambda hint:[];self.organizer.enqueue(THREAD,'job');self.organizer.drain();self.organizer.drain()
        self.assertEqual(self.db.execute('SELECT attempts FROM sidebar_threads').fetchone()[0],1)
        self.assertEqual(self.organizer.status()['sidebar_error'],'APP_TOOLS_DESKTOP_OFFLINE')

    def test_ambiguous_names_are_not_modified(self):
        self.app.sections=[{'name':SECTION_NAME,'sectionId':x} for x in ('one','two')]
        self.organizer.enqueue(THREAD,'job');self.organizer.drain()
        self.assertEqual(self.app.moves,0);self.assertEqual(self.organizer.status()['sidebar_pending'],1)

    def test_missing_confirmation_never_reports_grouped(self):
        self.app.unconfirmed=True;self.organizer.enqueue(THREAD,'job');self.organizer.drain()
        self.assertEqual(self.organizer.status()['sidebar_error'],'APP_TOOLS_PLACEMENT_UNCONFIRMED')

    def test_already_grouped_replay_does_not_move(self):
        self.app.sections=[{'name':SECTION_NAME,'sectionId':'existing','itemKeys':['codex:thread:local:'+THREAD]}]
        self.organizer.enqueue(THREAD,'job');self.organizer.drain();self.assertEqual(self.app.moves,0)

    def test_runtime_discovery_follows_installed_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plugins=root/'.codex/plugins/cache/openai-bundled/codex-app-tools'
            old=plugins/'old/server.mjs';old.parent.mkdir(parents=True);old.touch()
            node=root/'node.exe';node.touch()
            env={'USERPROFILE':str(root),'LOCALAPPDATA':str(root),'CODEX_MCP_NODE_PATH':str(node)}
            with patch.dict('os.environ',env,clear=True):
                self.assertEqual(installed_runtime(),(node,old))
                new=plugins/'new/server.mjs';new.parent.mkdir();new.touch()
                import os
                os.utime(new,ns=(old.stat().st_mtime_ns+1000000000,old.stat().st_mtime_ns+1000000000))
                self.assertEqual(installed_runtime(),(node,new))

    def test_upgraded_schema_missing_required_field_fails_before_call(self):
        client=AppTools.__new__(AppTools)
        client.schemas={'move_thread_to_sidebar_section':{'properties':{'threadId':{},'sectionId':{},'newRequired':{}},'required':['newRequired']}}
        client.request=lambda *args:self.fail('incompatible mutation must not be sent')
        with self.assertRaisesRegex(ValueError,'APP_TOOLS_SCHEMA_CHANGED'):
            client.call('move_thread_to_sidebar_section',{'threadId':THREAD,'sectionId':'section'})

    def test_unrelated_tools_cannot_be_called(self):
        with self.assertRaisesRegex(ValueError,'APP_TOOLS_NOT_ALLOWED'):
            AppTools.__new__(AppTools).call('send_message_to_thread',{})


if __name__=='__main__':unittest.main()
