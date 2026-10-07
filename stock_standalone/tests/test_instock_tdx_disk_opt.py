import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / 'instock_data_fix'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


if 'JSONData' not in sys.modules:
    pkg = types.ModuleType('JSONData')
    pkg.__path__ = [str(ROOT / 'JSONData')]
    sys.modules['JSONData'] = pkg

sys.modules['JSONData.history_cache'] = module('history_cache', ROOT / 'JSONData/history_cache.py')
tdx = module('tdx_data_Day', ROOT / 'JSONData/tdx_data_Day.py')


class TestTdxDiskOptimization(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.forward_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_tdx_file_path_index(self):
        sh_file = os.path.join(self.forward_dir, 'SH600000.TXT')
        sz_file = os.path.join(self.forward_dir, '000001.txt')
        with open(sh_file, 'w', encoding='gb18030') as f:
            f.write('dummy')
        with open(sz_file, 'w', encoding='gb18030') as f:
            f.write('dummy')

        p1 = tdx.get_tdx_file_path(self.forward_dir, 'SH', '600000')
        self.assertIsNotNone(p1)
        self.assertTrue(os.path.samefile(p1, sh_file))

        p2 = tdx.get_tdx_file_path(self.forward_dir, 'SZ', '000001')
        self.assertIsNotNone(p2)
        self.assertTrue(os.path.samefile(p2, sz_file))

        p3 = tdx.get_tdx_file_path(self.forward_dir, 'SH', '999999')
        self.assertIsNone(p3)

    def test_read_tdx_csv_tail_seek_equivalence(self):
        dates = pd.date_range('2018-01-01', periods=1200, freq='B')
        lines = []
        for d in dates:
            d_str = d.strftime('%Y-%m-%d')
            lines.append(f"{d_str},10.0,10.5,9.8,10.2,100000,1020000.0\n")

        file_path = os.path.join(self.forward_dir, 'SH600001.TXT')
        with open(file_path, 'w', encoding='gb18030') as f:
            f.writelines(lines)

        full_df = pd.read_csv(
            file_path, header=None, names=['date', 'open', 'high', 'low', 'close', 'vol', 'amount'],
            usecols=range(7), dtype={'date': str}, encoding='gb18030'
        )

        tail_df = tdx._read_tdx_csv(file_path, min_rows=600)
        self.assertGreaterEqual(len(tail_df), 600)
        self.assertTrue(tail_df.tail(600).reset_index(drop=True).equals(full_df.tail(600).reset_index(drop=True)))

    def test_read_tdx_csv_small_file_fallback(self):
        dates = pd.date_range('2026-01-01', periods=50, freq='B')
        lines = [f"{d.strftime('%Y-%m-%d')},20.0,21.0,19.5,20.5,50000,1025000.0\n" for d in dates]

        file_path = os.path.join(self.forward_dir, 'SZ300001.TXT')
        with open(file_path, 'w', encoding='gb18030') as f:
            f.writelines(lines)

        tail_df = tdx._read_tdx_csv(file_path, min_rows=600)
        self.assertEqual(len(tail_df), 50)


if __name__ == '__main__':
    unittest.main()
