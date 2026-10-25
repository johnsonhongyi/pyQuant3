# -*- coding: utf-8 -*-
"""市场上下文（冰点天数/饥饿度）与 df 全量行情桥接 —— 自检。"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.fusion.market_ctx import (
    DayContext,
    MarketHistory,
    hunger_of,
)


class TestHunger(unittest.TestCase):
    def test_no_ice_is_neutral(self):
        self.assertEqual(hunger_of(0, 0), 1.0)

    def test_more_ice_more_hungry(self):
        vals = [hunger_of(i, i) for i in range(0, 5)]
        self.assertEqual(vals, sorted(vals), "冰点越久，饥饿度应单调上升")

    def test_capped(self):
        self.assertLessEqual(hunger_of(30, 30), 1.5)


class TestMarketHistory(unittest.TestCase):
    def _hist(self):
        path = os.path.join(tempfile.mkdtemp(), "mh.json")
        h = MarketHistory(path)
        # 连续 3 天冰点（宽度 10%），再看第 4 天
        for d in ("2026-10-20", "2026-10-21", "2026-10-22"):
            h.record(DayContext(day=d, temp_open=10, temp_close=10, temp_min=10, temp_max=10, breadth=0.10))
        return h

    def test_ice_days_counted_from_history(self):
        h = self._hist()
        ctx = h.context_for("2026-10-23")
        self.assertEqual(ctx.ice_days, 3, "连续冰点应累加")
        self.assertGreater(ctx.hunger, 1.2)
        self.assertIn("冰点", ctx.label())

    def test_no_lookahead(self):
        """当天自己的数据不能影响自己的冰点天数。"""
        h = self._hist()
        h.record(DayContext(day="2026-10-23", temp_open=80, temp_close=80, temp_min=80, temp_max=80, breadth=0.9))
        ctx = h.context_for("2026-10-23")
        self.assertEqual(ctx.ice_days, 3, "不能把当天算进'此前连续冰点'")

    def test_break_resets_streak(self):
        h = self._hist()
        h.record(DayContext(day="2026-10-23", temp_open=60, temp_close=60, temp_min=60, temp_max=60, breadth=0.6))
        ctx = h.context_for("2026-10-26")
        self.assertEqual(ctx.ice_days, 0, "冰点中断后应归零")

    def test_save_load(self):
        h = self._hist()
        path = h.path
        self.assertGreaterEqual(h.save(), 3)
        h2 = MarketHistory(path)
        self.assertGreaterEqual(len(h2.days), 3)
        self.assertEqual(h2.context_for("2026-10-23").ice_days, 3)

    def test_context_uses_stored_breadth(self):
        h = self._hist()
        ctx = h.context_for("2026-10-22")
        self.assertAlmostEqual(ctx.breadth, 0.10, places=3)


class TestLiveBridgeDf(unittest.TestCase):
    def test_on_df_rising_stock_enters(self):
        import pandas as pd

        from ats.fusion.live_bridge import FusionLiveBridge

        b = FusionLiveBridge(state_path=os.path.join(tempfile.mkdtemp(), "s.json"),
                             vwap10_provider=lambda c: 9.9)
        base = 1792700000.0
        entered = False
        for i in range(10):
            px = 10.0 + i * 0.08
            df = pd.DataFrame(
                [{"trade": px, "percent": 0.6 + i * 0.8, "open": 10.0, "high": px + 0.02,
                  "low": 9.98, "pre_close": 9.95, "vol_ratio": 1.8, "vwap": 9.95 + i * 0.03,
                  "name": "测试"}],
                index=["399999"],   # 日线表里没有，跨日风险为 0，避免被"昨日大涨"挡掉
            )
            b.on_df(df, now=base + i * 180, day="2026-10-23")
            st = b.tracker.get("399999")
            if st is not None and st.stage == "入局":
                entered = True
        self.assertTrue(entered, "持续放量上行应触发入局")
        self.assertEqual(b.stats["errors"], 0)

    def test_high_gap_risk_blocks_entry(self):
        """昨日大涨+5日透支的票，盘中即使放量上行也不应入局（实测 gap_risk=94）。"""
        import pandas as pd

        from ats.fusion.live_bridge import FusionLiveBridge

        b = FusionLiveBridge(state_path=os.path.join(tempfile.mkdtemp(), "s.json"),
                             vwap10_provider=lambda c: 9.9)
        base = 1792700000.0
        for i in range(8):
            px = 10.0 + i * 0.06
            df = pd.DataFrame(
                [{"trade": px, "percent": 0.5 + i * 0.6, "open": 10.0, "high": px + 0.02,
                  "low": 9.98, "pre_close": 9.95, "vol_ratio": 1.8, "vwap": 9.95 + i * 0.02}],
                index=["300296"],   # 真实日线：昨日 +8.3%、5日 +31.7%
            )
            b.on_df(df, now=base + i * 180, day="2026-10-23")
        st = b.tracker.get("300296")
        self.assertIsNotNone(st)
        self.assertNotEqual(st.stage, "入局", "跨日风险过高不应入局")

    def test_on_df_handles_garbage(self):
        from ats.fusion.live_bridge import FusionLiveBridge

        b = FusionLiveBridge(state_path=os.path.join(tempfile.mkdtemp(), "s.json"))
        for bad in (None, "x", 123, []):
            b.on_df(bad)
        self.assertEqual(b.stats["errors"], 0)

    def test_on_df_accepts_alternate_columns(self):
        import pandas as pd

        from ats.fusion.live_bridge import FusionLiveBridge

        b = FusionLiveBridge(state_path=os.path.join(tempfile.mkdtemp(), "s.json"))
        df = pd.DataFrame([{"price": 10.2, "pct": 2.0, "vol_ratio": 1.5}], index=["600000.SH"])
        self.assertEqual(b.on_df(df, day="2026-10-23"), 1)
        self.assertIsNotNone(b.tracker.get("600000"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
