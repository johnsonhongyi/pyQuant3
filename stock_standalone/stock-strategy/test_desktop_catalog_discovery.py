"""Catalog discovery regression tests; no network, inference or trading."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop_strategy_agent import AppServer, discover_models


class CatalogDiscoveryTests(unittest.TestCase):
    def row(self, model):
        return {'model':model,'supportedReasoningEfforts':[{'reasoningEffort':'low'}]}

    def test_reads_all_pages_before_selecting_latest_family(self):
        app=Mock()
        app.request.side_effect=[
            {'data':[self.row('gpt-6-luna')],'nextCursor':'page2'},
            {'data':[self.row('gpt-6.1-sol'),self.row('future-model')],'nextCursor':None}]
        self.assertEqual({r['id'] for r in discover_models(app)},
                         {'gpt-6-luna','gpt-6.1-sol','future-model'})
        self.assertEqual(app.request.call_args_list[1].args[1]['cursor'],'page2')

    def test_repeated_cursor_and_invalid_page_fail_without_partial_catalog(self):
        for pages in ([{'data':[],'nextCursor':'same'}]*2,[{'data':None}]):
            app=Mock();app.request.side_effect=pages
            with self.assertRaises(ValueError):discover_models(app)

    def test_entire_pagination_has_one_timeout_budget(self):
        app=Mock();app.request.return_value={'data':[],'nextCursor':'page2'}
        with patch('desktop_strategy_agent.time.monotonic',side_effect=[0,1,31]):
            with self.assertRaises(TimeoutError):discover_models(app)
        self.assertEqual(app.request.call_count,1)

    def test_stalled_startup_reaps_owned_child(self):
        spawn=subprocess.Popen
        children=[]
        def child(*args,**kwargs):
            process=spawn([sys.executable,'-c','import time; time.sleep(60)'],**kwargs)
            children.append(process)
            return process
        with tempfile.TemporaryDirectory() as directory, \
             patch('desktop_strategy_agent.subprocess.Popen',side_effect=child), \
             patch.object(AppServer,'request',side_effect=TimeoutError('startup')):
            with self.assertRaises(TimeoutError):AppServer('fixture',Path(directory))
        self.assertIsNotNone(children[0].poll())


if __name__=='__main__':unittest.main()
