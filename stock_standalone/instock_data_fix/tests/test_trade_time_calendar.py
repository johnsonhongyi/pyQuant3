import datetime
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).parents[1] / 'lib' / 'trade_time.py'


def load_trade_time_module():
    instock = types.ModuleType('instock')
    core = types.ModuleType('instock.core')
    singleton = types.ModuleType('instock.core.singleton_trade_date')
    singleton.stock_trade_date = object()
    with patch.dict(sys.modules, {
        'instock': instock,
        'instock.core': core,
        'instock.core.singleton_trade_date': singleton,
    }):
        spec = importlib.util.spec_from_file_location('trade_time_under_test', MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class _Calendar:
    def __init__(self, values):
        self.values = values

    def get_data(self):
        return self.values


class TradeTimeCalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trade_time = load_trade_time_module()

    def setUp(self):
        self.trade_time.stock_trade_date = lambda: _Calendar([
            '2026-10-08', '2026-10-09', '20261012',
        ])

    def test_iso_calendar_matches_date_and_finds_previous_trade_date(self):
        self.assertTrue(self.trade_time.is_trade_date(datetime.date(2026, 10, 9)))
        self.assertEqual(
            self.trade_time.get_previous_trade_date(datetime.date(2026, 10, 11)),
            datetime.date(2026, 10, 9),
        )

    def test_compact_calendar_date_is_normalized(self):
        self.assertTrue(self.trade_time.is_trade_date(datetime.date(2026, 10, 12)))
        self.assertEqual(
            self.trade_time.get_next_trade_date(datetime.date(2026, 10, 9)),
            datetime.date(2026, 10, 12),
        )

    def test_datetime_input_keeps_datetime_return_type(self):
        value = datetime.datetime(2026, 10, 11, 9, 30)
        self.assertEqual(
            self.trade_time.get_previous_trade_date(value),
            datetime.datetime(2026, 10, 9, 9, 30),
        )

    def test_missing_previous_date_fails_without_underflow(self):
        self.trade_time.stock_trade_date = lambda: _Calendar(['2026-10-09'])
        with self.assertRaises(LookupError):
            self.trade_time.get_previous_trade_date(datetime.date.min)

    def test_unavailable_calendar_preserves_existing_fallback(self):
        value = datetime.date(2026, 10, 11)
        self.trade_time.stock_trade_date = lambda: _Calendar(None)
        self.assertEqual(self.trade_time.get_previous_trade_date(value), value)


if __name__ == '__main__':
    unittest.main()
