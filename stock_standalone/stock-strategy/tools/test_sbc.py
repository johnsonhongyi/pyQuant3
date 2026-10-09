"""Isolated parity/validation tests; no market access or trading imports."""
import ast
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'tools/sbc_reference'


def module(name, source):
    result = types.ModuleType(name)
    sys.modules[name] = result
    exec(source, result.__dict__)
    return result


class SBCTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = module('sbc_test', (ENGINE/'engine.py').read_text(encoding='utf-8'))
        exec((ENGINE/'adapter.py').read_text(encoding='utf-8'), cls.engine.__dict__)
        original = ROOT.parent / 'JSONData/tdx_channel_factory.py'
        cls.factory = module('sbc_original_factory', original.read_text(encoding='utf-8-sig'))
        cls.strategy = types.ModuleType('sbc_original_strategy')
        cls.strategy.__dict__.update(cls.engine.__dict__)
        tree = ast.parse((ROOT.parent/'ats/channel_bottom_reversal_strategy.py').read_text(encoding='utf-8-sig'))
        pure = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[])
        exec(compile(pure, 'ats-original', 'exec'), cls.strategy.__dict__)

    def bars(self, kind='random', count=150):
        rng = np.random.RandomState(42)
        close = 10 + np.cumsum(rng.normal(0, .1, count))
        if kind == 'ascending': close = np.linspace(10, 20, count)
        if kind == 'descending': close = np.linspace(20, 10, count)
        if kind == 'flat': close = np.full(count, 10.)
        return [dict(symbol='600733.SH', time=(dt.datetime(2025, 1, 1)+dt.timedelta(days=i)).isoformat()+'Z',
                     open=float(c), high=float(c+.3), low=float(c-.3), close=float(c),
                     volume=int(rng.randint(1000, 100000)), amount=100000,
                     meta={'source':'isolated-test', 'stale':True, 'trade_date':'2025-05-30'})
                for i,c in enumerate(close)]

    def test_parity(self):
        for kind in ('random', 'ascending', 'descending', 'flat'):
            with self.subTest(kind=kind):
                bars = self.bars(kind)
                frame = pd.DataFrame(bars)
                frame['vol'] = frame.volume
                old = self.factory.TDXChannelFactory.calculate(frame, max_days=9)
                new = self.engine.TDXChannelFactory.calculate(frame, max_days=9)
                for field in ('upper','mid','lower','kx_series'):
                    np.testing.assert_allclose(getattr(old,field),getattr(new,field),equal_nan=True)
                result = self.engine.analyze(dict(symbol='600733.SH',period='day',bars=bars))
                expected = self.strategy.evaluate_channel_strategy(self.engine.calc_trend_channel(frame))
                self.assertEqual(result['strategy'],expected)
                self.assertEqual(len(result['points']),len(bars))
                self.assertTrue(result['market_meta']['stale'])
                json.dumps(result,allow_nan=False)

    def test_td_reset(self):
        frame = pd.DataFrame({'close': np.arange(1,25,dtype=float)})
        counts = self.engine.td_sequential_fast(frame).td_sell_count.tolist()
        self.assertEqual(counts[4:15], list(range(1,10))+[1,2])

    def test_invalid_bars(self):
        for kind in ('duplicate','negative','nan','bounds','short'):
            bars = self.bars()
            if kind == 'duplicate': bars[1]['time'] = bars[0]['time']
            if kind == 'negative': bars[0]['volume'] = -1
            if kind == 'nan': bars[0]['close'] = float('nan')
            if kind == 'bounds': bars[0]['high'] = bars[0]['low']
            if kind == 'short': bars = bars[:9]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.engine.analyze(dict(symbol='600733.SH',period='day',bars=bars))

    def test_windows_stdin_runtime(self):
        payload = {'source': (ENGINE/'engine.py').read_text(encoding='utf-8')+'\n'+(ENGINE/'adapter.py').read_text(encoding='utf-8'),
                   'input':dict(symbol='600733.SH',period='day',bars=self.bars())}
        bootstrap = "import json,sys; p=json.load(sys.stdin); scope={'__name__':'sbc_runtime'}; exec(p['source'],scope); print(json.dumps(scope['analyze'](p['input']),allow_nan=False))"
        result = subprocess.run([sys.executable,'-X','utf8','-c',bootstrap],input=json.dumps(payload),
                                capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['schema_version'],1)


if __name__ == '__main__':
    unittest.main()
