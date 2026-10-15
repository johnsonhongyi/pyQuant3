"""Desktop evidence/registration preparation tests without model/network calls."""
import configparser
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from desktop_strategy_agent import DesktopPeer,ats_evidence


class DesktopAgentTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
