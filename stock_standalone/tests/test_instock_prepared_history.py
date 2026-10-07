import importlib.util
import ast
import datetime
import os
from pathlib import Path
import sys
import tempfile
import types
from threading import RLock
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / 'instock_data_fix'
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
store = module('prepared_history', ROOT / 'JSONData/prepared_history.py')
scan = module('streaming_scan', ROOT / 'job/streaming_scan.py')


class PreparedHistoryTests(unittest.TestCase):
    def test_smaller_windows_derive_without_source_reads_and_keep_frozen_version(self):
        counter = types.ModuleType('JSONData.history_cache'); counter._count = lambda name: None
        package = types.ModuleType('JSONData'); package.__path__ = []
        frame = pd.DataFrame({'date': pd.date_range('2025-01-01', periods=400).strftime('%Y-%m-%d'),
                              'close': [10. + index / 100 for index in range(400)]})
        signature = ('start', 'end', 'qfq', ('date', 'close'), 'source', (1, 2))
        calls = []
        def loader():
            calls.append(1); return frame.copy()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
            {'INSTOCK_HISTORY_CACHE_EPOCH': '2026-09-30', 'INSTOCK_HIST_LOOKBACK_ROWS': '1000'}), patch.dict(
                sys.modules, {'JSONData': package, 'JSONData.history_cache': counter}):
            path = os.path.join(directory, '600001-qfq.pkl')
            store.prepared_history(path, signature, loader)
            os.environ['INSTOCK_HIST_LOOKBACK_ROWS'] = '150'
            actual = store.prepared_history(path, signature, loader)
            pd.testing.assert_frame_equal(actual, frame.tail(150).reset_index(drop=True))
            self.assertEqual(len(calls), 1)
            changed = signature[:-1] + ((2, 3),)
            os.environ['INSTOCK_HIST_LOOKBACK_ROWS'] = '310'
            store.prepared_history(path, changed, loader)
            self.assertEqual(len(calls), 1)
            os.environ['INSTOCK_HISTORY_CACHE_EPOCH'] = '2026-10-08'
            store.prepared_history(path, changed, loader)
            self.assertEqual(len(calls), 2)

    def test_premarket_reads_largest_profile_once_and_derives_smaller_cache(self):
        source = ROOT / 'job/prewarm_history.py'
        function = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                        if isinstance(node, ast.FunctionDef) and node.name == 'warm_stock')
        calls, derived = [], []
        frame = pd.DataFrame({'date': ['2026-09-29'], 'close': [10.]})
        def fetch(*args):
            calls.append(os.environ['INSTOCK_HIST_LOOKBACK_ROWS'])
            return frame
        scope = dict(os=os, Path=Path, stf=types.SimpleNamespace(fetch_stock_hist=fetch,
            _tdx_history_source=lambda code: ('600001', 'source', (1, 2))),
            tbs=types.SimpleNamespace(CN_STOCK_HIST_DATA={'columns': ('date', 'close')}),
            prepared_history=lambda path, fingerprint, loader: derived.append(
                (os.environ['INSTOCK_HIST_LOOKBACK_ROWS'], loader().equals(frame))))
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            Path(directory, '600001-qfq-600.npy').touch()
            self.assertTrue(scope['warm_stock'](('day', '600001', 'name'), 'day', 'start', True, directory))
        self.assertEqual(calls, ['600'])
        self.assertEqual(derived, [('600', True)])



    def test_streaming_appends_missing_last_trading_bar(self):
        source = ROOT / 'job/strategy_enter-edit.py'
        function = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                        if isinstance(node, ast.FunctionDef) and node.name == '_stream_strategy_enter')
        day = datetime.date(2026, 9, 30)
        frame = pd.DataFrame({'date': pd.to_datetime(['2026-09-29']), 'close': [10.]})
        quotes = pd.DataFrame([{'date': str(day), 'code': '600001', 'name': 'stock'}])
        calls = []
        def merge(date, frames, subset):
            calls.append((date, len(frames), len(subset)))
            return {stock: pd.concat([data, pd.DataFrame({'date': [pd.Timestamp(date)], 'close': [11.]})])
                    for stock, data in frames.items()}
        def batches(stocks, strategies, load, *args):
            loaded = load(stocks)
            self.assertEqual(next(iter(loaded.values())).iloc[-1]['date'], pd.Timestamp(day))
        scope = dict(os=os, datetime=datetime, pd=pd, strategy_history_rows=scan.history_rows,
                     tbs=types.SimpleNamespace(TABLE_CN_STOCK_STRATEGIES=[{'name': 'cn_stock_strategy_enter'}],
                         TABLE_CN_STOCK_FOREIGN_KEY={'columns': ('date', 'code', 'name')}),
                     trd=types.SimpleNamespace(get_trade_date_last=lambda: (day, None),
                         get_trade_hist_interval=lambda date: ('start', True), is_trade_date=lambda date: date.weekday() < 5),
                     _strategy_run_dates=lambda: [day], stock_data=lambda date: types.SimpleNamespace(
                         get_data=lambda *args, **kwargs: quotes), fetch_stock_hist=lambda *args: frame.copy(),
                     stocks_data_to_realtime=merge, scan_batches=batches, _publish_results=lambda *args: None)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
        with patch.dict(os.environ, {'INSTOCK_HIST_LOOKBACK_ROWS': '150', 'INSTOCK_HISTORY_CACHE_EPOCH': str(day),
                                    'INSTOCK_STATIC_RESULT_CACHE': '0'}):
            scope['_stream_strategy_enter'](True, types.SimpleNamespace(config={'entrypoint': 'realtime'},
                progress=lambda **kwargs: None), None)
        self.assertEqual(calls, [(day, 1, 1)])

    def test_strategy_windows_cover_year_and_month_indicators(self):
        self.assertEqual(scan.history_rows('cn_stock_strategy_enter'), 150)
        self.assertEqual(scan.history_rows('cn_stock_strategy_backtrace_ma250'), 310)
        self.assertEqual(scan.history_rows('cn_stock_strategy_keep_increasing'), 600)

    def test_daily_releases_snapshot_and_restores_entrypoint_on_failure(self):
        source = ROOT / 'perf_hotfix_20261006/job/strategy_data_daily_job.py'
        function = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                        if isinstance(node, ast.FunctionDef) and node.name == '_streaming_daily')
        instance = types.SimpleNamespace(_lock=RLock(), data={'old': object()}, _loaded=True, _loaded_key='old')
        stock_class = type('Stock', (), {'_instance': instance})
        calls = []
        def run(**kwargs):
            calls.append((kwargs, os.environ['INSTOCK_STRATEGY_ENTRYPOINT']))
            raise RuntimeError('scan failed')
        fake = types.ModuleType('runpy')
        fake.run_path = lambda *args, **kwargs: {'strategy_enter': run}
        scope = dict(stock_hist_data=stock_class, os=os, cpath_current='/job')
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
        with patch.dict(os.environ, {'INSTOCK_STRATEGY_ENTRYPOINT': 'original'}), patch.dict(sys.modules, {'runpy': fake}):
            with self.assertRaises(RuntimeError):
                scope['_streaming_daily']()
            self.assertEqual(os.environ['INSTOCK_STRATEGY_ENTRYPOINT'], 'original')
        self.assertIsNone(instance.data)
        self.assertFalse(instance._loaded)
        self.assertEqual(calls, [({'small_strategies_only': False}, 'daily')])

    def test_persistent_hit_epoch_refresh_and_compact_exact_values(self):
        counter = types.ModuleType('JSONData.history_cache')
        counter._count = lambda name: None
        package = types.ModuleType('JSONData'); package.__path__ = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'INSTOCK_HIST_LOOKBACK_ROWS': '150', 'INSTOCK_HISTORY_CACHE_EPOCH': '2026-09-30'}), patch.dict(sys.modules,
                {'JSONData': package, 'JSONData.history_cache': counter}):
                path = os.path.join(directory, '600001.pkl')
                frame = pd.DataFrame({'date': pd.date_range('2025-01-01', periods=400).strftime('%Y-%m-%d'),
                    'code': '600001', 'close': [10.123456789 + index / 100 for index in range(400)], 'turnover': 0.})
                calls = []
                def loader():
                    calls.append(1); return frame.copy()
                signature = ('start', 'end', 'qfq', ('date', 'code', 'close', 'turnover'), 'source', (1, 2))
                expected = frame.tail(150).reset_index(drop=True)
                first = store.prepared_history(path, signature, loader)
                first.loc[0, 'close'] = 999
                actual = store.prepared_history(path, signature, loader)
                pd.testing.assert_frame_equal(actual, expected)
                self.assertEqual(len(calls), 1)
                self.assertLess(os.path.getsize(os.path.join(directory, f'600001-{store.UNIFIED_BASE_ROWS}.npy')), 8000)

                os.environ['INSTOCK_HISTORY_CACHE_EPOCH'] = '2026-10-08'
                store.prepared_history(path, signature, loader)
                self.assertEqual(len(calls), 1)
                changed = signature[:-1] + ((2, 3),)
                store.prepared_history(path, changed, loader)
                self.assertEqual(len(calls), 1)
                os.environ['INSTOCK_HISTORY_CACHE_EPOCH'] = '2026-10-09'
                store.prepared_history(path, changed, loader)
                self.assertEqual(len(calls), 2)

    def test_batches_preserve_results_and_delay_publication(self):
        strategies = [{'name': 'a'}, {'name': 'b'}]
        published, sizes = [], []
        stats = types.SimpleNamespace(stages=[], progress=lambda **kwargs: None)
        def load(batch):
            sizes.append(len(batch)); return {stock: stock for stock in batch}
        def check(strategy, frames):
            matches = [stock for stock in frames if stock % 2 == 0]
            return matches, dict(checked=len(frames), matched=len(matches), errors=0, seconds=1)
        scan.scan_batches(range(201), strategies, load, check,
            lambda date, strategy, results: published.append(list(results)), 'date', stats, 64)
        self.assertEqual(max(sizes), 64)
        self.assertEqual(published, [list(range(0, 201, 2))] * 2)
        published.clear()
        with self.assertRaises(RuntimeError):
            scan.scan_batches(range(201), strategies, lambda batch: {}, check,
                lambda *args: published.append(1), 'date', stats, 64)
        self.assertEqual(published, [])

    def test_manifest_zero_io_metadata_hit(self):
        counter = types.ModuleType('JSONData.history_cache')
        counter._count = lambda name: None
        package = types.ModuleType('JSONData'); package.__path__ = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'INSTOCK_HISTORY_CACHE_EPOCH': '2026-09-30', 'INSTOCK_HIST_LOOKBACK_ROWS': '150'}), patch.dict(sys.modules,
                {'JSONData': package, 'JSONData.history_cache': counter}):
                path = os.path.join(directory, '000001-qfq.pkl')
                frame = pd.DataFrame({'date': pd.date_range('2025-01-01', periods=200).strftime('%Y-%m-%d'),
                                      'code': '000001', 'close': [10. + i for i in range(200)]})
                signature = ('start', 'end', 'qfq', ('date', 'code', 'close'), 'source', (1, 2))
                # 1. 首次写入（底层加厚）
                store.prepared_history(path, signature, lambda: frame.copy())
                meta_file = Path(directory) / f'000001-qfq-{store.UNIFIED_BASE_ROWS}.meta.json'
                self.assertTrue(meta_file.exists())

                # 2. 生成 manifest.json 集中清单
                manifest_path = store.save_manifest(directory)
                self.assertIsNotNone(manifest_path)
                self.assertTrue(Path(manifest_path).exists())

                # 3. 抹除单个 meta.json，模拟零小文件 I/O
                meta_file.unlink()
                self.assertFalse(meta_file.exists())
                store._METADATA_CACHE.clear()

                # 4. 从 manifest.json 直接命中元数据并零拷贝裁切
                actual = store.prepared_history(path, signature, lambda: None, _allow_loader=False)
                self.assertIsNotNone(actual)
                pd.testing.assert_frame_equal(actual, frame.tail(150).reset_index(drop=True))


if __name__ == '__main__':
    unittest.main()
