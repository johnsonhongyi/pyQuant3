# -*- coding: utf-8 -*-
"""tests/test_signal_timeline.py — 时间轴层（Bar 时钟 + 轨迹环 + 结构轴）单元测试。

纯合成数据，不触碰任何行情源/业务文件。验证文档 §5/§10 的关键不变量。
"""

import time
import unittest

import numpy as np

from ats.signal_timeline import (
    BarClock,
    Structure,
    TimelineHub,
    TrackSeries,
)

_DAY = time.mktime((2026, 10, 20, 0, 0, 0, 0, 0, -1))


def _ts(bar_id: int, clock: BarClock) -> float:
    return clock.bar_start_ts(bar_id, _DAY)


class BarClockTest(unittest.TestCase):
    def setUp(self):
        self.clk = BarClock(15)

    def test_open_maps_to_zero(self):
        self.assertEqual(self.clk.bar_id(_ts(0, self.clk)), 0)

    def test_15s_resolution(self):
        self.assertEqual(self.clk.bar_id(_ts(1, self.clk)), 1)
        self.assertEqual(self.clk.bar_id(_ts(0, self.clk) + 14), 0)
        self.assertEqual(self.clk.bar_id(_ts(0, self.clk) + 15), 1)

    def test_lunch_skipped(self):
        lunch = time.mktime((2026, 10, 20, 11, 35, 0, 0, 0, -1))
        self.assertEqual(self.clk.bar_id(lunch), -1)
        pm0 = time.mktime((2026, 10, 20, 13, 0, 0, 0, 0, -1))
        self.assertEqual(self.clk.bar_id(pm0), 480)

    def test_bars_per_day(self):
        self.assertEqual(self.clk.bars_per_day, 960)


class TrackSeriesTest(unittest.TestCase):
    def setUp(self):
        self.clk = BarClock(15)
        self.s = TrackSeries("600000", 15, capacity=240)

    def test_same_bar_merges_not_duplicates(self):
        bid = 10
        new1 = self.s.update(bid, 10.0, high=10.2, low=9.9, vol=100, pct=1.0, vwap=10.05, temp=55)
        new2 = self.s.update(bid, 11.0, high=11.3, low=10.8, vol=120, pct=2.0, vwap=10.6, temp=56)
        self.assertTrue(new1)
        self.assertFalse(new2)

        self.assertAlmostEqual(float(self.s.window("close", 1, bid)[0]), 11.0, places=3)
        self.assertAlmostEqual(float(self.s.window("high", 1, bid)[0]), 11.3, places=3)
        self.assertAlmostEqual(float(self.s.window("low", 1, bid)[0]), 9.9, places=3)

        rows = self.s.to_rows(bid, 1)
        self.assertEqual(rows[0]["n_samples"], 2)

    def test_gap_is_explicit_nan(self):
        self.s.update(5, 10.0)
        self.s.update(7, 10.5)
        w = self.s.window("close", 3, 7)   # 覆盖 bar5 / bar6 / bar7
        self.assertFalse(np.isnan(w[0]))   # bar5 有数据
        self.assertTrue(np.isnan(w[1]))    # bar6 空洞
        self.assertFalse(np.isnan(w[2]))   # bar7 有数据
        self.assertAlmostEqual(self.s.gap_ratio(7, 3), 1.0 / 3.0, places=3)

    def test_slope_positive_trend(self):
        for b in range(20):
            self.s.update(b, 10.0 + b * 0.05)
        self.assertGreater(self.s.slope(12, 19), 0.0)

    def test_slope_insufficient_samples_is_zero(self):
        self.s.update(0, 10.0)
        self.assertEqual(self.s.slope(12, 0), 0.0)

    def test_structure_hh_hl(self):
        for i in range(12):
            base = 10.0 + i * 0.1
            self.s.update(i, base, high=base + 0.03, low=base - 0.03)
        self.assertEqual(self.s.structure(12, 2, 11), Structure.HH_HL)

    def test_structure_lh_ll(self):
        for i in range(12):
            base = 12.0 - i * 0.1
            self.s.update(i, base, high=base + 0.03, low=base - 0.03)
        self.assertEqual(self.s.structure(12, 2, 11), Structure.LH_LL)

    def test_above_ratio(self):
        for b in range(10):
            self.s.update(b, 11.0 if b >= 5 else 10.0)
        ratio = self.s.above_ratio(10.5, 8, 9)
        self.assertAlmostEqual(ratio, 5.0 / 8.0, places=3)

    def test_extremes(self):
        self.s.update(0, 10.0, high=10.4, low=9.8)
        self.s.update(1, 10.2, high=10.9, low=10.0)
        hi, lo = self.s.extremes(0, 1)
        self.assertAlmostEqual(hi, 10.9, places=3)
        self.assertAlmostEqual(lo, 9.8, places=3)

    def test_reset_clears(self):
        self.s.update(3, 10.0)
        self.s.reset()
        self.assertTrue(np.isnan(self.s.window("close", 1, 3)[0]))

    def test_rejects_nonpositive_price(self):
        self.assertFalse(self.s.update(1, 0.0))
        self.assertFalse(self.s.update(1, -1.0))


class TimelineHubTest(unittest.TestCase):
    def test_ingest_uses_clock(self):
        hub = TimelineHub(15, capacity=240)
        bid = hub.ingest("600000", _ts(20, hub.clock), 10.5)
        self.assertEqual(bid, 20)
        s = hub.get("600000")
        self.assertIsNotNone(s)
        self.assertAlmostEqual(float(s.window("close", 1, 20)[0]), 10.5, places=3)

    def test_out_of_session_returns_minus_one(self):
        hub = TimelineHub(15, capacity=240)
        lunch = time.mktime((2026, 10, 20, 11, 35, 0, 0, 0, -1))
        self.assertEqual(hub.ingest("600000", lunch, 10.0), -1)
        self.assertIsNone(hub.get("600000"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
