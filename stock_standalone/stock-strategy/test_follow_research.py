import unittest
from unittest.mock import patch
from datetime import timedelta

import auto_follow as af
from follow_research import stock_plan, rotation_snapshot, refresh_research
from test_auto_follow import NOW, CFG, Calendar, quote


class ResearchTests(unittest.TestCase):
    def test_go_nanoseconds_keep_timezone_and_freshness(self):
        q = quote()
        q['meta']['fetched_at'] = '2026-10-14T10:30:00.036671110+08:00'
        self.assertEqual(af.stamp(q['meta']['fetched_at']).microsecond, 36671)
        af.fresh(q['meta'], NOW + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            af.fresh(q['meta'], NOW + timedelta(seconds=121))
        self.assertEqual(af.stamp('2026-10-14T02:30:00.1Z').hour, 10)

    def test_plan_reuses_gate_and_does_not_mutate_account(self):
        state = af.initial()
        before = af.json.dumps(state)
        with patch.object(af, 'entry_ok', side_effect=ValueError('P8 VWAP gate')) as gate:
            p = stock_plan({'symbol': '600001.SH'}, quote(), [], [], CFG, NOW, '2026-10-13', state)
        gate.assert_called_once()
        self.assertFalse(p['structure_ready'])
        self.assertEqual(p['blocker'], 'P8 VWAP gate')
        self.assertEqual(p['reference_shares'], 9800)
        self.assertNotIn('intraday_vwap', p['metrics'])
        self.assertEqual(before, af.json.dumps(state))

    def test_local_daily_shares_contract_and_mixed_units(self):
        bar = {'amount': 10000, 'volume': 1000, 'low': 9.9, 'high': 10.1,
               'meta': {'source': 'instock-tdx-daily'}}
        self.assertEqual(af.exact_vwap([bar]), 10)
        bar['volume'] = 10
        with self.assertRaises(ValueError):
            af.exact_vwap([bar])

    def test_expired_quote_is_reference_even_when_mocked_structure_ready(self):
        q = quote()
        q['trade_time'] = (NOW - timedelta(days=1)).isoformat()
        p = stock_plan({'symbol': '600001.SH'}, q, [], [], CFG, NOW, '2026-10-13', af.initial())
        self.assertFalse(p['fresh_quote'])
        self.assertFalse(p['structure_ready'])

    def payload(self, at=NOW, date='2026-10-14', flow=100):
        meta = {'source': 'test', 'stale': False, 'fetched_at': at.isoformat(),
                'available_fields': ['net_inflow'], 'trade_date': date}
        return {'meta': meta, 'data': [{'code': 'A', 'name': 'sample', 'net_inflow': flow,
                 'main_net_inflow': 0, 'change_percent': 1, 'meta': meta}]}

    def test_supported_flow_field_avoids_default_main_zero(self):
        p = rotation_snapshot(self.payload(), {}, NOW)
        self.assertEqual(p['rows'][0]['flow_field'], 'net_inflow')
        self.assertEqual(p['rows'][0]['net_flow'], 100)
        self.assertIsNone(p['rows'][0]['change_percent'])
        bad = self.payload()
        bad['data'][0]['meta'] = dict(bad['meta'], stale=True)
        stale = rotation_snapshot(bad, p, NOW)
        self.assertTrue(stale['error'])
        self.assertNotIn('flow_change', stale['rows'][0])

    def test_rotation_requires_trade_date_and_changed_snapshot(self):
        first = rotation_snapshot(self.payload(), {}, NOW)
        repeated = rotation_snapshot(self.payload(), first, NOW)
        self.assertNotIn('flow_change', repeated['rows'][0])
        later = NOW + timedelta(minutes=5)
        second = rotation_snapshot(self.payload(later, flow=140), first, later)
        self.assertEqual(second['rows'][0]['flow_change'], 40)
        unknown = rotation_snapshot(self.payload(later, date=None), first, later)
        self.assertTrue(unknown['error'])
        self.assertNotIn('flow_change', unknown['rows'][0])
        next_day = rotation_snapshot(self.payload(later, date='2026-10-15'), first, later)
        self.assertNotIn('flow_change', next_day['rows'][0])

    def test_data_error_never_creates_trade_and_keeps_reference_identity(self):
        state = af.initial()
        state['candidates'] = [{'symbol': '600001.SH', 'route': 'theme_trend'}]
        def fail(path):
            raise OSError('unavailable')
        refresh_research(state, CFG, fail, NOW, Calendar)
        self.assertEqual(state['cash'], 500000)
        self.assertEqual(state['positions'], [])
        self.assertEqual(state['research']['pool_mode'], 'retained_reference')
        self.assertTrue(state['candidates'][0]['plan']['errors'])


if __name__ == '__main__':
    unittest.main()
