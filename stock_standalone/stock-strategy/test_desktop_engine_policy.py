import sqlite3
import unittest
from datetime import datetime,timezone
from desktop_engine_policy import EngineCatalog


class EngineCatalogTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE runtime(key TEXT PRIMARY KEY,value TEXT)')
        self.now=datetime(2026,10,15,8,tzinfo=timezone.utc).timestamp()
        self.candidate='old';self.calls=[];self.broken=False;self.revision=1
        self.models=[{'id':'gpt-6-luna','efforts':['low'],'default_effort':'low'}]
        self.catalog=self.make()

    def tearDown(self):self.db.close()

    def make(self):
        def probe(path):
            self.calls.append(path)
            if self.broken:raise TimeoutError('failed upgrade')
            return self.models
        return EngineCatalog(self.db,'old',lambda:self.candidate,probe,
                             identity=lambda path:{'path':path,'revision':self.revision})

    def test_periodic_refresh_and_restart_revalidates_saved_catalog(self):
        self.assertTrue(self.catalog.refresh_idle(self.now))
        self.assertFalse(self.catalog.refresh_idle(self.now+61))
        self.models=self.models+[{'id':'new-family','efforts':['high'],'default_effort':'high'}]
        self.assertTrue(self.catalog.refresh_idle(self.now+301))
        self.assertEqual(len(self.catalog.models),2)
        restarted=self.make()
        self.assertTrue(restarted.status()['catalog_stale'])
        self.assertTrue(restarted.refresh_idle(self.now+302))
        self.assertFalse(restarted.status()['catalog_stale'])
        self.assertEqual(self.calls,['old','old','old'])

    def test_midnight_is_hong_kong_not_utc(self):
        self.catalog.refresh_idle(self.now)
        self.assertTrue(self.catalog.refresh_idle(datetime(2026,10,15,16,tzinfo=timezone.utc).timestamp()))
        self.assertEqual(self.catalog.day,'2026-10-16')

    def test_job_keeps_captured_engine_until_next_idle_boundary(self):
        self.catalog.refresh_idle(self.now)
        job_engine=self.catalog.engine
        self.candidate='new'
        self.assertEqual(job_engine,'old')
        self.assertEqual(self.catalog.engine,'old')
        self.assertTrue(self.catalog.refresh_idle(self.now+61))
        self.assertEqual(self.catalog.engine,'new')
        self.assertEqual(job_engine,'old')

    def test_bad_upgrade_keeps_working_engine_and_retries_with_backoff(self):
        self.catalog.refresh_idle(self.now)
        self.candidate='new';self.broken=True
        self.assertFalse(self.catalog.refresh_idle(self.now+61))
        self.assertEqual(self.catalog.engine,'old')
        self.assertFalse(self.catalog.refresh_idle(self.now+122))
        self.assertEqual(self.calls,['old','new'])
        self.broken=False
        self.assertTrue(self.catalog.refresh_idle(self.now+362))
        self.assertEqual(self.catalog.engine,'new')

    def test_same_path_replacement_is_detected_and_empty_catalog_rejected(self):
        self.catalog.refresh_idle(self.now)
        self.revision=2;self.models=[]
        self.assertFalse(self.catalog.refresh_idle(self.now+61))
        self.assertEqual(self.catalog.fingerprint['revision'],1)

    def test_initial_catalog_failure_remains_unavailable_during_backoff(self):
        self.broken=True
        self.assertFalse(self.catalog.refresh_idle(self.now))
        self.assertFalse(self.catalog.refresh_idle(self.now+61))
        self.assertEqual(self.catalog.models,[])
        self.assertEqual(self.calls,['old'])

    def test_manual_refresh_bypasses_cache_and_error_backoff(self):
        self.catalog.refresh_idle(self.now)
        self.broken=True
        self.assertFalse(self.catalog.refresh_idle(self.now+1,force=True))
        self.assertTrue(self.catalog.status()['catalog_stale'])
        self.broken=False
        self.assertTrue(self.catalog.refresh_idle(self.now+2,force=True))
        self.assertFalse(self.catalog.status()['catalog_stale'])


if __name__=='__main__':unittest.main()
