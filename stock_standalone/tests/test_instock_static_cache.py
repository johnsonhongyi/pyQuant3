import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / 'instock_data_fix'
spec = importlib.util.spec_from_file_location('static_strategy_cache', ROOT / 'job/static_strategy_cache.py')
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


class StaticCacheTests(unittest.TestCase):
    def test_order_independent_results_subset_and_dependency_invalidation(self):
        results = [('day', '600002', 'b'), ('day', '600001', 'a')]
        self.assertEqual(cache.result_digest(results), cache.result_digest(results[::-1]))
        entry = dict(results=results, scan=dict(errors=0, result_sha256=cache.result_digest(results)))
        with tempfile.TemporaryDirectory() as directory:
            store = cache.StaticResults(directory)
            key = 'a' * 64
            store.save(key, {'small': entry, 'external': dict(entry, dependency='top-v1')}, 100, 100, 7)
            self.assertEqual(store.load(key, ['small'])['gaps'], 7)
            self.assertIsNotNone(store.load(key, ['external'], {'external': 'top-v1'}))
            self.assertIsNone(store.load(key, ['external'], {'external': 'top-v2'}))
            self.assertIsNone(store.load(key, ['missing']))
            payload = json.loads((Path(directory) / (key + '.json')).read_text())
            payload['strategies']['small']['results'][0][1] = 'tampered'
            (Path(directory) / (key + '.json')).write_text(json.dumps(payload))
            self.assertIsNone(store.load(key, ['small']))

    def test_all_input_changes_invalidate_manifest(self):
        stocks = [('2026-09-30', '600001', 'name')]
        quotes = pd.DataFrame({'code': ['600001'], 'price': [10.]})
        source = [1]
        with tempfile.TemporaryDirectory() as directory:
            def key(**changes):
                args = dict(directory=directory, stocks=stocks, quotes=quotes, date='2026-09-30',
                            rows=150, epoch='2026-09-30', revision='code-v1', source_signature=lambda code: source)
                args.update(changes)
                return cache.manifest(**args)
            before = key()
            self.assertEqual(before, key())
            for changes in ({'rows': 310}, {'epoch': 'next'}, {'revision': 'code-v2'},
                            {'date': '2026-09-29'}, {'quotes': quotes.assign(price=11.)}):
                self.assertNotEqual(before, key(**changes))
            source.append(2)
            self.assertNotEqual(before, key())
            before = key()
            (Path(directory) / '600001-qfq-150.npy').write_bytes(b'array-version')
            self.assertNotEqual(before, key())

    def test_errors_and_low_coverage_are_not_reused(self):
        entry = dict(results=[], scan=dict(errors=1, result_sha256=cache.result_digest([])))
        with tempfile.TemporaryDirectory() as directory:
            store = cache.StaticResults(directory)
            key = 'b' * 64
            store.save(key, {'a': entry}, 100, 100, 0)
            self.assertFalse((Path(directory) / (key + '.json')).exists())
            entry['scan']['errors'] = 0
            store.save(key, {'a': entry}, 1, 100, 0)
            self.assertIsNone(store.load(key, ['a']))


    def test_callable_rows_determinism_and_manifest_json_acceleration(self):
        stocks = [('2026-09-30', '600001', 'name')]
        quotes = pd.DataFrame({'code': ['600001'], 'price': [10.]})
        # 两个独立的闭包函数，内存地址完全不同
        fn1 = lambda name: {'cn_stock_strategy_keep_increasing': 600}.get(name, 150)
        fn2 = lambda name: {'cn_stock_strategy_keep_increasing': 600}.get(name, 150)
        self.assertNotEqual(id(fn1), id(fn2))

        with tempfile.TemporaryDirectory() as directory:
            key1 = cache.manifest(directory, stocks, quotes, '2026-09-30', fn1, 'epoch1', 'rev1', lambda c: [1])
            key2 = cache.manifest(directory, stocks, quotes, '2026-09-30', fn2, 'epoch1', 'rev1', lambda c: [1])
            self.assertEqual(key1, key2)

            # 写入 manifest.json，测试零 I/O 加速指纹分支
            manifest_file = Path(directory) / 'manifest.json'
            manifest_file.write_text('{"600001": {}}')
            key_manifest1 = cache.manifest(directory, stocks, quotes, '2026-09-30', fn1, 'epoch1', 'rev1', lambda c: [1])
            self.assertNotEqual(key1, key_manifest1)

            # 更新 manifest.json 触发失效
            manifest_file.write_text('{"600001": {}, "600002": {}}')
            key_manifest2 = cache.manifest(directory, stocks, quotes, '2026-09-30', fn1, 'epoch1', 'rev1', lambda c: [1])
            self.assertNotEqual(key_manifest1, key_manifest2)


if __name__ == '__main__':
    unittest.main()
