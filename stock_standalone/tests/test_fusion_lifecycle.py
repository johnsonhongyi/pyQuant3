# -*- coding: utf-8 -*-
"""领先度（排头兵/冲锋队/夺旗/跟风）与战役生命周期 —— 自检。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.fusion.lifecycle import (
    PHASE_ADVANCE,
    PHASE_ATTACK,
    PHASE_ICE,
    PHASE_RETREAT,
    PHASE_VANGUARD_DYING,
    CapitalGauge,
    MarketLifecycle,
    VanguardWatch,
)
from ats.fusion.vanguard import (
    LABEL_FLAG,
    LABEL_FOLLOW,
    LABEL_LONE,
    LABEL_STRIKE,
    LABEL_VANGUARD,
    SectorClock,
    classify,
)

T0 = 1792700000.0
BAR = 180.0


class TestSectorClock(unittest.TestCase):
    def test_first_mover_is_vanguard(self):
        """板块内第一个启动的是排头兵。"""
        c = SectorClock()
        for i, code in enumerate(("300001", "300002", "300003", "300004", "300005")):
            c.observe(code, "电子-光学", T0 + i * BAR, pct=1.5)
        info = c.observe("300001", "电子-光学", T0 + 5 * BAR, pct=3.0)
        self.assertEqual(info.rank, 1)
        self.assertEqual(info.lead_gap_min, 0.0)
        self.assertIn(info.label, (LABEL_VANGUARD, LABEL_FLAG))

    def test_late_mover_is_follower(self):
        """板块首动 40 分钟之后才启动 -> 跟风。"""
        c = SectorClock()
        for i in range(6):
            c.observe("30010{}".format(i), "机械", T0 + i * BAR, pct=2.0)
        info = c.observe("300999", "机械", T0 + 40 * 60, pct=2.5)
        self.assertEqual(info.label, LABEL_FOLLOW)
        self.assertGreaterEqual(info.lead_gap_min, 30.0)

    def test_flag_capture(self):
        """板块内第一个突破的是旗手。"""
        c = SectorClock()
        c.observe("300201", "医药", T0, pct=2.0)
        c.observe("300202", "医药", T0 + BAR, pct=2.0)
        c.observe("300203", "医药", T0 + 2 * BAR, pct=2.0)
        info = c.observe("300202", "医药", T0 + 2 * BAR, pct=3.0, breakout=True)
        self.assertTrue(info.is_flag)
        self.assertEqual(info.label, LABEL_FLAG)

    def test_lone_wolf_when_sector_thin(self):
        """板块只有 1~2 家在动：无导向，不是排头兵。"""
        c = SectorClock()
        c.observe("300301", "小众", T0, pct=2.0)
        info = c.observe("300301", "小众", T0 + BAR, pct=3.0)
        self.assertEqual(info.label, LABEL_LONE)

    def test_classify_bounds(self):
        self.assertEqual(classify(1, 0.0, 10, False)[0], LABEL_VANGUARD)
        self.assertEqual(classify(4, 10.0, 10, False)[0], LABEL_STRIKE)
        self.assertEqual(classify(9, 45.0, 12, False)[0], LABEL_FOLLOW)
        self.assertEqual(classify(1, 0.0, 2, False)[0], LABEL_LONE)


class TestVanguardWatch(unittest.TestCase):
    def test_survival_drops_when_break_vwap10(self):
        w = VanguardWatch()
        for i, code in enumerate(("300401", "300402", "300403", "300404")):
            w.register(code, "板块A", T0 + i * BAR, 10.0, 9.5)
        alive, total, rate = w.survival()
        self.assertEqual((alive, total), (4, 4))
        # 两只跌破 10 日 VWAP
        w.update("300401", 9.3, 9.5, T0 + 10 * BAR)
        w.update("300402", 9.2, 9.5, T0 + 10 * BAR)
        alive, total, rate = w.survival()
        self.assertEqual(alive, 2)
        self.assertAlmostEqual(rate, 0.5, places=3)
        self.assertEqual(len(w.dead_recent(T0 + 11 * BAR)), 2)

    def test_sector_survival_isolated(self):
        w = VanguardWatch()
        w.register("300501", "板块A", T0, 10.0, 9.5)
        w.register("300502", "板块B", T0, 10.0, 9.5)
        w.update("300501", 9.0, 9.5, T0 + BAR)
        self.assertEqual(w.survival("板块A")[0], 0)
        self.assertEqual(w.survival("板块B")[0], 1)


class TestCapitalGauge(unittest.TestCase):
    def test_attack_signal_on_volume_expansion(self):
        g = CapitalGauge()
        for v in (10, 10, 10, 10, 10):
            g.update(v)
        for v in (15, 15, 15, 15, 15):
            g.update(v)
        self.assertGreater(g.ratio(), 1.15)
        self.assertEqual(g.label(), "冲锋号")

    def test_retreat_signal_on_volume_shrink(self):
        g = CapitalGauge()
        for v in (20, 20, 20, 20, 20):
            g.update(v)
        for v in (10, 10, 10, 10, 10):
            g.update(v)
        self.assertLess(g.ratio(), 0.85)
        self.assertEqual(g.label(), "退避三舍")

    def test_neutral_early(self):
        g = CapitalGauge()
        self.assertEqual(g.ratio(), 1.0)


class TestLifecycle(unittest.TestCase):
    def test_ice_when_cold_and_narrow(self):
        st = MarketLifecycle().update(temp=30, breadth=0.15, survival=1.0, survival_n=5, capital=0.9)
        self.assertEqual(st.phase, PHASE_ICE)
        self.assertIn("等第一枪", st.action)

    def test_retreat_when_vanguards_dead(self):
        """先锋几乎全灭 -> 退守，哪怕温度还高。"""
        st = MarketLifecycle().update(temp=55, breadth=0.5, survival=0.2, survival_n=10, capital=1.0)
        self.assertEqual(st.phase, PHASE_RETREAT)
        self.assertFalse(st.allow_entry)

    def test_dying_when_half_dead(self):
        st = MarketLifecycle().update(temp=50, breadth=0.5, survival=0.45, survival_n=10, capital=1.0)
        self.assertEqual(st.phase, PHASE_VANGUARD_DYING)
        self.assertFalse(st.allow_entry, "先锋阵亡过半应禁止开新仓")

    def test_attack_on_volume_and_low_temp(self):
        st = MarketLifecycle().update(temp=40, breadth=0.45, survival=0.9, survival_n=10, capital=1.3)
        self.assertEqual(st.phase, PHASE_ATTACK)
        self.assertTrue(st.allow_entry)

    def test_advance_default(self):
        st = MarketLifecycle().update(temp=52, breadth=0.55, survival=0.9, survival_n=10, capital=1.0)
        self.assertEqual(st.phase, PHASE_ADVANCE)

    def test_retreat_on_volume_shrink(self):
        st = MarketLifecycle().update(temp=45, breadth=0.30, survival=0.9, survival_n=10, capital=0.7)
        self.assertEqual(st.phase, PHASE_RETREAT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
