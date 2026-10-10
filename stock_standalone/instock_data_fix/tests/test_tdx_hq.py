import os
import tempfile
import unittest

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / 'core' / 'tdx_hq.py'
_SPEC = importlib.util.spec_from_file_location('instock_tdx_hq_under_test', _MODULE_PATH)
_TDX = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_TDX)
TDXHqClient = _TDX.TDXHqClient
TDXUnavailable = _TDX.TDXUnavailable
daily_bar_to_line = _TDX.daily_bar_to_line
market_code = _TDX.market_code
parse_daily_line = _TDX.parse_daily_line
quote_to_snapshot = _TDX.quote_to_snapshot
read_tdx_tail_bars = _TDX.read_tdx_tail_bars
read_tdx_local_calendar = _TDX.read_tdx_local_calendar


class FakeApi:
    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows

    def connect(self, host, port, time_out=5.0):
        return True

    def disconnect(self):
        return None

    def get_security_bars(self, category, market, code, offset, count):
        self.calls.append((category, market, code, offset, count))
        if offset:
            return []
        if self.rows is not None:
            return self.rows
        return [{
            'datetime': '2026-10-09', 'open': 10.0, 'high': 11.0,
            'low': 9.5, 'close': 10.5, 'vol': 12, 'amount': 12600.0,
        }]


class TdxHqTests(unittest.TestCase):
    def test_quote_classifies_no_trade_and_converts_lots_to_shares(self):
        no_trade = {
            'code': '000001', 'price': 0, 'last_close': 0, 'open': 0,
            'high': 0, 'low': 0, 'vol': 0, 'amount': 0,
        }
        self.assertEqual(quote_to_snapshot('000001', no_trade, '2026-10-09')[0], 'no_trade')

        quote = {
            'code': '000001', 'name': '平安银行', 'price': 11.0, 'last_close': 10.0,
            'open': 10.2, 'high': 11.1, 'low': 10.0, 'vol': 120, 'amount': 130000.0,
        }
        status, row = quote_to_snapshot('000001', quote, '2026-10-09')
        self.assertEqual(status, 'valid')
        self.assertEqual(row['volume'], 12000)
        self.assertEqual(row['change_rate'], 10.0)

    def test_daily_history_uses_tdx_market_and_share_units(self):
        api = FakeApi()
        client = TDXHqClient(api_factory=lambda: api, hosts=[('fake', '127.0.0.1', 7709)])
        bars = client.fetch_daily_bars('000001', '2026-10-09', '2026-10-09')
        self.assertEqual(api.calls[0], (4, 0, '000001', 0, 800))
        self.assertEqual(bars[0]['volume'], 1200)
        self.assertEqual(daily_bar_to_line(bars[0]), '2026-10-09,10,11,9.5,10.5,1200,12600\n')

    def test_daily_history_uses_go_tdx_api_and_keeps_share_units(self):
        import json
        from urllib.parse import parse_qs, urlparse

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return json.dumps({
                    'implementation': 'go-native-tdx',
                    'data': [
                        {'time': '2026-10-08T15:00:00+08:00', 'open': 9, 'high': 11,
                         'low': 8, 'close': 10, 'volume': 10000, 'amount': 100000,
                         'meta': {'source': 'tdx'}},
                        {'time': '2026-10-09T15:00:00+08:00', 'open': 10, 'high': 11,
                         'low': 9, 'close': 10.5, 'volume': 12000, 'amount': 126000,
                         'meta': {'source': 'tdx'}},
                    ],
                }).encode('utf-8')

        requests = []

        def open_url(request, timeout):
            requests.append((request, timeout))
            return Response()

        client = TDXHqClient(
            daily_api_url='http://tdx.local/api/v1/quotes/tdx/bars',
            urlopen=open_url,
            api_factory=lambda: self.fail('raw HQ fallback must not run'),
        )
        bars = client.fetch_daily_bars('600733', '2026-10-09', '2026-10-09')
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]['date'], '2026-10-09')
        self.assertEqual(bars[0]['volume'], 12000)
        query = parse_qs(urlparse(requests[0][0].full_url).query)
        self.assertEqual(query['symbol'], ['600733.SH'])
        self.assertEqual(query['period'], ['day'])
        self.assertEqual(query['limit'], ['300'])
        self.assertEqual(requests[0][1], 20)

    def test_daily_api_routes_beijing_symbols(self):
        import json
        from urllib.parse import parse_qs, urlparse

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return json.dumps({
                    'implementation': 'go-native-tdx',
                    'data': [{'time': '2026-10-09T15:00:00+08:00', 'open': 10,
                              'high': 11, 'low': 9, 'close': 10.5, 'volume': 12000,
                              'amount': 126000, 'meta': {'source': 'tdx'}}],
                }).encode('utf-8')

        requests = []
        client = TDXHqClient(
            daily_api_url='http://tdx.local/api/v1/quotes/tdx/bars',
            urlopen=lambda request, timeout: (requests.append(request) or Response()),
        )
        bars = client.fetch_daily_bars('920305', '2026-10-09', '2026-10-09')
        query = parse_qs(urlparse(requests[0].full_url).query)
        self.assertEqual(query['symbol'], ['920305.BJ'])
        self.assertEqual(len(bars), 1)

    def test_daily_api_empty_series_is_a_valid_no_bar_result(self):
        import json

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return json.dumps({
                    'implementation': 'go-native-tdx',
                    'data': [],
                }).encode('utf-8')

        client = TDXHqClient(
            daily_api_url='http://tdx.local/api/v1/quotes/tdx/bars',
            urlopen=lambda request, timeout: Response(),
        )
        self.assertEqual(client.fetch_daily_bars('920305', '2026-10-09', '2026-10-09'), [])

    def test_daily_api_rejects_non_tdx_provenance(self):
        import json

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return json.dumps({
                    'implementation': 'go-native-tdx',
                    'data': [{'time': '2026-10-09T15:00:00+08:00', 'open': 10,
                              'high': 11, 'low': 9, 'close': 10.5, 'volume': 12000,
                              'amount': 126000, 'meta': {'source': 'sina'}}],
                }).encode('utf-8')

        client = TDXHqClient(
            daily_api_url='http://tdx.local/api/v1/quotes/tdx/bars',
            urlopen=lambda request, timeout: Response(),
        )
        with self.assertRaises(TDXUnavailable):
            client.fetch_daily_bars('600733', '2026-10-09', '2026-10-09')

    def test_empty_tdx_node_fails_over_to_next_node(self):
        empty = FakeApi(rows=[])
        working = FakeApi()
        apis = iter((empty, working))
        client = TDXHqClient(
            api_factory=lambda: next(apis),
            hosts=[('empty', '127.0.0.1', 7709), ('working', '127.0.0.2', 7709)],
        )
        bars = client.fetch_daily_bars('000001', '2026-10-09', '2026-10-09')
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]['date'], '2026-10-09')
        self.assertEqual(len(empty.calls), 1)
        self.assertEqual(len(working.calls), 1)

    def test_protocol_errors_are_not_reported_as_no_bar(self):
        class BrokenApi(FakeApi):
            def get_security_bars(self, category, market, code, offset, count):
                raise ValueError('malformed TDX response')

        apis = iter((BrokenApi(), BrokenApi(), BrokenApi()))
        client = TDXHqClient(
            api_factory=lambda: next(apis),
            hosts=[('one', '127.0.0.1', 7709), ('two', '127.0.0.2', 7709),
                   ('three', '127.0.0.3', 7709)],
        )
        with self.assertLogs(_TDX.__name__, level='WARNING'):
            with self.assertRaises(TDXUnavailable):
                client.fetch_daily_bars('000001', '2026-10-09', '2026-10-09')

    def test_tail_parser_reports_bad_rows_without_hiding_valid_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'SZ000001.txt')
            with open(path, 'wb') as stream:
                stream.write(b'2026-10-08,9,10,8,9.5,100,950\n')
                stream.write(b'2026-10-09,bad,row\n')
                stream.write(b'2026-10-09,10,11,9.5,10.5,1200,12600\n')
            bars, invalid = read_tdx_tail_bars(path, '2026-10-09', max_bytes=4096)
        self.assertEqual(invalid, 1)
        self.assertEqual([bar['date'] for bar in bars], ['2026-10-08', '2026-10-09'])
        self.assertEqual(parse_daily_line(b'bad row'), None)

    def test_local_calendar_unions_current_tdx_anchors_and_skips_stale_files(self):
        with tempfile.TemporaryDirectory() as directory:
            stale = os.path.join(directory, 'SH999999.TXT')
            shanghai = os.path.join(directory, 'SH600000.TXT')
            shenzhen = os.path.join(directory, 'SZ000001.TXT')
            rows = {
                stale: [{'date': '2026-09-30', 'open': 10, 'high': 11, 'low': 9,
                         'close': 10, 'volume': 100, 'amount': 1000}],
                shanghai: [{'date': '2026-10-08', 'open': 10, 'high': 11, 'low': 9,
                            'close': 10, 'volume': 100, 'amount': 1000},
                           {'date': '2026-10-09', 'open': 10, 'high': 11, 'low': 9,
                            'close': 10, 'volume': 100, 'amount': 1000}],
                shenzhen: [{'date': '2026-10-07', 'open': 10, 'high': 11, 'low': 9,
                            'close': 10, 'volume': 100, 'amount': 1000},
                           {'date': '2026-10-09', 'open': 10, 'high': 11, 'low': 9,
                            'close': 10, 'volume': 100, 'amount': 1000}],
            }
            for path, bars in rows.items():
                with open(path, 'wb') as stream:
                    stream.writelines(daily_bar_to_line(bar).encode('ascii') for bar in bars)
            dates = read_tdx_local_calendar(
                [stale, shanghai, shenzhen], target_date='2026-10-09', max_bytes=4096)
        self.assertEqual(dates, ['2026-10-07', '2026-10-08', '2026-10-09'])
        self.assertIsNone(read_tdx_local_calendar([stale], target_date='2026-10-09'))

    def test_market_mapping_includes_beijing(self):
        self.assertEqual(market_code('920305'), 2)
        self.assertEqual(market_code('688001'), 1)


if __name__ == '__main__':
    unittest.main()
