import datetime
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


IN_STOCK_ROOT = Path(__file__).resolve().parents[1]
TDX_PATH = IN_STOCK_ROOT / 'core' / 'tdx_hq.py'
JOB_PATH = IN_STOCK_ROOT / 'job' / 'basic_data_daily_job.py'


def _load_tdx_module():
    spec = importlib.util.spec_from_file_location('index_test_tdx_hq', TDX_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_job_module():
    packages = {
        'instock': types.ModuleType('instock'),
        'instock.lib': types.ModuleType('instock.lib'),
        'instock.core': types.ModuleType('instock.core'),
    }
    for package in packages.values():
        package.__path__ = []
    modules = {
        'instock.lib.run_template': types.ModuleType('instock.lib.run_template'),
        'instock.core.tablestructure': types.ModuleType('instock.core.tablestructure'),
        'instock.lib.database': types.ModuleType('instock.lib.database'),
        'instock.lib.trade_time': types.ModuleType('instock.lib.trade_time'),
        'instock.core.stockfetch': types.ModuleType('instock.core.stockfetch'),
        'instock.core.tdx_hq': types.ModuleType('instock.core.tdx_hq'),
        'instock.core.singleton_stock': types.ModuleType('instock.core.singleton_stock'),
    }
    modules['instock.core.singleton_stock'].stock_data = lambda date: None
    packages['instock'].lib = packages['instock.lib']
    packages['instock'].core = packages['instock.core']
    packages['instock.lib'].run_template = modules['instock.lib.run_template']
    packages['instock.lib'].database = modules['instock.lib.database']
    packages['instock.lib'].trade_time = modules['instock.lib.trade_time']
    packages['instock.core'].tablestructure = modules['instock.core.tablestructure']
    packages['instock.core'].stockfetch = modules['instock.core.stockfetch']
    packages['instock.core'].tdx_hq = modules['instock.core.tdx_hq']
    packages['instock.core'].singleton_stock = modules['instock.core.singleton_stock']
    modules.update(packages)
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location('index_test_daily_job', JOB_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


_TDX = _load_tdx_module()
_JOB = _load_job_module()


class FakeTDXClient:
    def __init__(self, bars=None, failure=None):
        self.bars = bars or []
        self.failure = failure

    def fetch_daily_bars(self, code, start_date, end_date):
        if self.failure:
            raise self.failure
        return self.bars


class FakeStockFetch:
    def __init__(self, calendar, client):
        self.calendar = set(calendar)
        self.client = client
        self.parse_daily_line = _TDX.parse_daily_line
        self.daily_bar_to_line = _TDX.daily_bar_to_line

    def fetch_stocks_trade_date(self):
        return set(self.calendar)

    def get_tdx_client(self):
        return self.client


class BasicDataDailyIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.forward_dir = Path(self.temp.name) / 'forwardp'
        self.forward_dir.mkdir()
        cache_dir = Path(self.temp.name) / 'cache'
        cache_dir.mkdir()
        self.previous_cache = _JOB._CACHE_DIR
        self.previous_stf = _JOB.stf
        self.previous_tdx_hq = _JOB.tdx_hq
        _JOB._CACHE_DIR = str(cache_dir)
        self.target = (datetime.datetime.now(_JOB._TIMEZONE).date()
                       - datetime.timedelta(days=1)).isoformat()
        target = datetime.date.fromisoformat(self.target)
        self.calendar = [
            (target - datetime.timedelta(days=2)).isoformat(),
            (target - datetime.timedelta(days=1)).isoformat(),
            self.target,
        ]
        self.env = mock.patch.dict(os.environ, {'TDX_FORWARDP_DIR': str(self.forward_dir)})
        self.env.start()
        self.client = FakeTDXClient(failure=RuntimeError('TDX HQ unavailable'))
        _JOB.stf = FakeStockFetch(self.calendar, self.client)
        _JOB.tdx_hq = types.SimpleNamespace(
            parse_daily_line=_TDX.parse_daily_line,
            daily_bar_to_line=_TDX.daily_bar_to_line,
            get_tdx_client=lambda: self.client,
        )

    def tearDown(self):
        _JOB.stf = self.previous_stf
        _JOB.tdx_hq = self.previous_tdx_hq
        _JOB._CACHE_DIR = self.previous_cache
        self.env.stop()
        self.temp.cleanup()

    def _fallback_lines(self, code, start_date, end_date):
        rows = []
        for offset, day in enumerate(self.calendar):
            if start_date <= day <= end_date:
                close = 2800.0 + offset
                rows.append(_TDX.daily_bar_to_line({
                    'date': day, 'open': close - 2, 'high': close + 3,
                    'low': close - 4, 'close': close, 'volume': 1000 + offset,
                    'amount': 100000 + offset,
                }))
        return rows

    def test_cold_start_and_retry_create_an_idempotent_chinext_file(self):
        fallback = mock.Mock(side_effect=self._fallback_lines)
        with mock.patch.object(_JOB, '_fetch_tencent_tdx_index_history', fallback):
            first = _JOB.backfill_tdx_index_history(self.target, codes=['399006'])
            path = self.forward_dir / 'SZ399006.TXT'
            self.assertTrue(first['complete'], first)
            self.assertTrue(path.is_file())
            first_rows = path.read_text(encoding='ascii').splitlines()
            self.assertEqual(len(first_rows), 3)
            self.assertEqual(first_rows[-1].split(',')[0], self.target)

            second = _JOB.backfill_tdx_index_history(self.target, codes=['399006'])
            second_rows = path.read_text(encoding='ascii').splitlines()
            self.assertTrue(second['complete'], second)
            self.assertEqual(second['written'], 0)
            self.assertEqual(first_rows, second_rows)
            self.assertEqual(fallback.call_count, 2)

    def test_finalize_writes_all_backend_benchmark_files_and_marker(self):
        with mock.patch.object(_JOB, '_fetch_tencent_tdx_index_history',
                               side_effect=self._fallback_lines):
            _JOB.save_tdx_index_history(self.target, before=False, force_finalize=True)
        for filename in ('SZ399001.TXT', 'SZ399006.TXT', 'SH000001.TXT'):
            path = self.forward_dir / filename
            self.assertTrue(path.is_file(), filename)
            self.assertIn(self.target, [line.split(',')[0]
                                        for line in path.read_text(encoding='ascii').splitlines()])
        self.assertTrue(_JOB._final_marker_is_current(
            'tdx-index', self.target, _JOB._TDX_INDEX_FINAL_SOURCE))

    def test_main_schedules_index_backfill_even_in_stock_only_mode(self):
        with mock.patch.object(_JOB.trd, 'is_trade_date', return_value=True, create=True), \
                mock.patch.object(_JOB.runt, 'run_with_args', create=True) as run, \
                mock.patch.object(_JOB, 'save_tdx_index_history') as index_run:
            with mock.patch.dict(os.environ, {'INSTOCK_STOCK_SPOT_ONLY': '1'}), \
                    mock.patch.object(sys, 'argv', ['basic_data_daily_job.py']):
                _JOB.main()
        scheduled = [call.args[0] for call in run.call_args_list]
        self.assertEqual(scheduled, [_JOB.save_nph_stock_spot_data])
        index_run.assert_called_once()
        self.assertEqual(index_run.call_args.kwargs, {'before': False})
        self.assertEqual(index_run.call_args.args[0],
                         _JOB.datetime.datetime.now(_JOB._TIMEZONE).date())
    def test_new_index_file_is_world_readable_for_web_container(self):
        path = self.forward_dir / 'SZ399006.TXT'
        bar = {'date': self.target, 'open': 100, 'high': 102, 'low': 99,
               'close': 101, 'volume': 1000, 'amount': 100000}
        with mock.patch.object(_JOB.os, 'chmod') as chmod:
            _JOB._write_tdx_index_file(str(path), {self.target: bar})
        chmod.assert_called_once()
        self.assertEqual(chmod.call_args.args[1], 0o644)
        self.assertTrue(path.is_file())
    def test_old_calendar_gaps_do_not_block_recent_web_window(self):
        target = datetime.date.fromisoformat(self.target)
        calendar = [(target - datetime.timedelta(days=offset)).isoformat()
                    for offset in reversed(range(301))]
        old_gap = calendar[0]
        client_bars = []
        rows = []
        for index, day in enumerate(calendar[1:]):
            close = 100.0 + index / 100.0
            bar = {'date': day, 'open': close, 'high': close + 1,
                   'low': close - 1, 'close': close, 'volume': 1000, 'amount': 100000}
            rows.append(_TDX.daily_bar_to_line(bar))
            if day in calendar[-3:]:
                client_bars.append(bar)
        path = self.forward_dir / 'SZ399006.TXT'
        path.write_text(''.join(rows), encoding='ascii')
        client = FakeTDXClient(bars=client_bars)
        _JOB.stf = FakeStockFetch(calendar, client)
        _JOB.tdx_hq = types.SimpleNamespace(
            parse_daily_line=_TDX.parse_daily_line,
            daily_bar_to_line=_TDX.daily_bar_to_line,
            get_tdx_client=lambda: client,
        )
        with mock.patch.object(_JOB, '_fetch_tencent_tdx_index_history') as fallback:
            stats = _JOB.backfill_tdx_index_history(self.target, codes=['399006'])
        self.assertTrue(stats['complete'], stats)
        self.assertEqual(stats['missing_dates'], 1)
        self.assertEqual(stats['missing_recent_dates'], 0)
        fallback.assert_not_called()
        self.assertNotIn(old_gap, [line.split(',')[0] for line in path.read_text().splitlines()])
    def test_tencent_history_conversion_uses_exchange_and_tdx_units(self):
        target = self.target
        year = int(target[:4])
        payload = {'data': {'sh000001': {'day': [[
            target, '100', '101', '102', '99', '123', '0', '0', '45.6',
        ]]}}}
        response = types.SimpleNamespace(
            text='var kline_day%s=%s;' % (year, json.dumps(payload)),
            raise_for_status=lambda: None,
        )
        with mock.patch.object(_JOB.requests, 'get', return_value=response) as get:
            lines = _JOB._fetch_tencent_tdx_index_history('000001', target, target)
        get.assert_called_once()
        self.assertIn('sh000001', get.call_args.kwargs['params']['param'])
        parsed = _TDX.parse_daily_line(lines[0].encode('ascii'))
        self.assertEqual(parsed['date'], target)
        self.assertEqual(parsed['volume'], 12300)
        self.assertEqual(parsed['amount'], 456000)


    def test_tencent_history_skips_failed_older_year_and_keeps_target(self):
        target = self.target
        earlier_year = int(target[:4]) - 1
        payload = {'data': {'sz399006': {'day': [[
            target, '100', '101', '102', '99', '123', '0', '0', '45.6',
        ]]}}}
        response = types.SimpleNamespace(
            text='var kline_day%s=%s;' % (target[:4], json.dumps(payload)),
            raise_for_status=lambda: None,
        )
        with mock.patch.object(_JOB.requests, 'get',
                               side_effect=[RuntimeError('old-year timeout'), response]) as get:
            lines = _JOB._fetch_tencent_tdx_index_history(
                '399006', '%s-01-01' % earlier_year, target)
        self.assertEqual(get.call_count, 2)
        parsed = _TDX.parse_daily_line(lines[0].encode('ascii'))
        self.assertEqual(parsed['date'], target)
if __name__ == '__main__':
    unittest.main()