# -*- coding: utf-8 -*-
"""tests/test_fusion_adapter.py — 适配层：真实行/快照 -> SignalEvent。

重点验证"缺字段不崩、不伪造"：
- 正常行能取到价格/均价/涨幅/量能；
- NaN、pd.NA、'-'、空串一律退化为中性值并记账到 missing；
- vwap 缺失时用 amount/(volume*100) 回退；
- 先手时间只在真正启动时打点，且单日重置。
"""

import time
import unittest

import pandas as pd

from ats.fusion.adapter import LaunchTracker, build_event, today_str

_NOW = time.mktime((2026, 10, 23, 10, 30, 0, 0, 0, -1))


class TestBuildEvent(unittest.TestCase):
    def test_full_row_mapping(self):
        row = pd.Series(
            {
                "trade": 12.9,
                "vwap": 12.8,
                "percent": 4.2,
                "high": 13.2,
                "low": 12.3,
                "amount": 900000000.0,
                "volume": 70000.0,
                "ratio": 2.3,
                "turnover": 9.0,
                "vwap_cum_5d": 12.5,
            }
        )
        snap = {
            "name": "测试股",
            "taker_buy_ratio": 73.0,
            "bid_pressure": 69.0,
            "slope_score": 86.0,
            "intent_score": 90.0,
            "structure_clarity_score": 82.0,
            "sbc_supp_price": 12.55,
            "is_leader": True,
            "minutes_above_vwap": 28.0,
            "has_rs": True,
            "rs5": 2.5,
            "mkt_ret5": 1.2,
        }
        ev = build_event(row, snap, code="300111", now=_NOW, launch_ts=_NOW - 300, trade_date="2026-10-23")

        self.assertEqual(ev.code, "300111")
        self.assertAlmostEqual(ev.price, 12.9)
        self.assertAlmostEqual(ev.vwap, 12.8)
        self.assertAlmostEqual(ev.pct, 4.2)
        self.assertAlmostEqual(ev.amount_wan, 90000.0, places=1)
        self.assertAlmostEqual(ev.taker_buy_ratio, 73.0)
        self.assertTrue(ev.is_leader)
        self.assertEqual(ev.base_support, 12.55)
        self.assertEqual(ev.trade_date, "2026-10-23")
        self.assertLess(ev.bias_pct(), 1.0)
        self.assertEqual(ev.extra.get("missing"), [])

    def test_nan_and_dirty_values_fall_back(self):
        row = pd.Series(
            {
                "trade": 12.9,
                "vwap": float("nan"),
                "percent": "-",
                "high": None,
                "low": pd.NA,
                "amount": 0,
                "volume": 0,
            }
        )
        ev = build_event(row, {}, code="300222", now=_NOW)
        self.assertEqual(ev.price, 12.9)
        self.assertEqual(ev.vwap, 0.0)
        self.assertEqual(ev.pct, 0.0)
        self.assertEqual(ev.taker_buy_ratio, 50.0)
        self.assertEqual(ev.slope_score, 40.0)
        self.assertIn("vwap", ev.extra["missing"])
        self.assertIn("taker_buy_ratio", ev.extra["missing"])

    def test_vwap_computed_from_amount_volume(self):
        row = pd.Series({"trade": 10.0, "amount": 100000000.0, "volume": 100000.0})
        ev = build_event(row, {}, code="300333", now=_NOW)
        self.assertAlmostEqual(ev.vwap, 10.0, places=4)

    def test_missing_vwap_does_not_crash(self):
        ev = build_event(pd.Series({"trade": 10.0}), None, code="300444", now=_NOW)
        self.assertEqual(ev.vwap, 0.0)
        self.assertIn("vwap", ev.extra["missing"])

    def test_default_trade_date_is_today(self):
        ev = build_event(pd.Series({"trade": 10.0, "vwap": 9.9}), {}, code="300555", now=_NOW)
        self.assertEqual(ev.trade_date, today_str(_NOW))


class TestLaunchTracker(unittest.TestCase):
    def test_marks_on_launch(self):
        tr = LaunchTracker()
        self.assertEqual(tr.note("A", _NOW, pct=0.3, price=10.0, vwap=10.0), 0.0)
        first = tr.note("A", _NOW + 60, pct=1.6, price=10.2, vwap=10.0)
        self.assertAlmostEqual(first, _NOW + 60)
        # 已打点后不再更新
        self.assertAlmostEqual(tr.note("A", _NOW + 600, pct=5.0, price=10.6, vwap=10.0), _NOW + 60)

    def test_marks_on_bias(self):
        tr = LaunchTracker()
        ts = tr.note("B", _NOW, pct=0.2, price=10.10, vwap=10.0)
        self.assertAlmostEqual(ts, _NOW)

    def test_reset_daily(self):
        tr = LaunchTracker()
        tr.note("C", _NOW, pct=2.0, price=10.0, vwap=10.0)
        nxt = tr.note("C", _NOW + 86400, pct=0.1, price=10.0, vwap=10.0)
        self.assertEqual(nxt, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
