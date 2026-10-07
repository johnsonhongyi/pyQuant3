import ast
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'instock_data_fix'
spec = importlib.util.spec_from_file_location('run_statistics', ROOT / 'job/run_statistics.py')
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)
tree = ast.parse((ROOT / 'job/strategy_selection.py').read_text(encoding='utf-8'))
tree.body = [item for item in tree.body if not isinstance(item, ast.ImportFrom)]
namespace = {'database': stats.database}
exec(compile(tree, 'strategy_selection.py', 'exec'), namespace)
validate = namespace['validate_selection']
selection = namespace['selection']
registry = [{'name': name} for name in ['volume', 'averages', 'turtle', 'atr']]


class SelectionTests(unittest.TestCase):
    def test_registry_validation_and_order(self):
        self.assertEqual(validate(['atr', 'turtle', 'atr'], registry), ['turtle', 'atr'])
        for invalid in ([], None, 'atr', ['volume'], ['averages'], ['unknown'], [1]):
            with self.assertRaises(ValueError):
                validate(invalid, registry)

    def test_persistence_clear_and_statistics_independence(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'INSTOCK_RUN_STATS_PATH': os.path.join(directory, 'runs.sqlite')}):
                self.assertEqual(selection(registry), [])
                selection(registry, ['atr'])
                self.assertEqual(selection(registry), ['atr'])
                for index in range(12):
                    stats.save('pick%s' % index, 'selected', state='success')
                self.assertEqual(len(stats.history()['selected']), 10)
                self.assertEqual(stats.history()['small'], [])
                self.assertEqual(selection(registry), ['atr'])
                selection(registry, [])
                self.assertEqual(selection(registry), [])

    def test_selected_dispatch_does_not_run_other_strategies_or_backtest(self):
        source = ast.parse((ROOT / 'job/strategy_enter-edit.py').read_text(encoding='utf-8'))
        function = next(item for item in source.body if isinstance(item, ast.FunctionDef)
                        and item.name == '_strategy_enter')
        import datetime
        import logging
        import time
        import types
        runs, backtests = [], []
        data = {'stock': 'frame'}
        context = dict(os=os, time=time, logging=logging, _strategy_run_dates=lambda: [datetime.date(2026, 9, 30)],
                       build_strategy_snapshot=lambda date: data, tbs=types.SimpleNamespace(
                           TABLE_CN_STOCK_STRATEGIES=[dict(item, cn=item['name']) for item in registry]),
                       prepareRealtime=lambda date, strategy, **kwargs: runs.append(strategy['name']),
                       bk_job_edit=types.SimpleNamespace(prepareRealTime=lambda **kwargs: backtests.append(1)),
                       _last_scan={})
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'entry.py', 'exec'), context)
        with patch.dict(os.environ, {'INSTOCK_STREAM_STRATEGIES': '0'}):
            context['_strategy_enter'](False, types.SimpleNamespace(stage=lambda *args, **kwargs: None), ['atr'])
        self.assertEqual(runs, ['atr'])
        self.assertEqual(backtests, [])


if __name__ == '__main__':
    unittest.main()
