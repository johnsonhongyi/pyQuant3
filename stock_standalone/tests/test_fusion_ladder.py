# -*- coding: utf-8 -*-
"""tests/test_fusion_ladder.py — 融合层核心不变量测试。

覆盖本次设计的五条硬约束：
1. 追高/破位/过期是"否决"，不是"扣分"；
2. 同样涨幅，位置不同 -> 可参与度不同（这是与现状最大的差别）；
3. 级别是时间的函数（先手衰减），启动 40 分钟后不给 L4；
4. 温度阶段决定级别上限与仓位系数，过热期非龙头被压到 L2；
5. 跨来源收敛为一条决策，不重复播报。
"""

import time
import unittest

from ats.fusion import (
    FLIP_ARMED,
    FLIP_CONFIRMED,
    FLIP_FADING,
    FusionEngine,
    MarketRegime,
    MarketRegimeTracker,
    RegimeSample,
    STAGE_COLD,
    STAGE_OVERHEAT,
    STAGE_WARMING,
    SignalEvent,
)
from ats.fusion.engine import FusionBus, score_position

_NOW = time.mktime((2026, 10, 23, 10, 30, 0, 0, 0, -1))
_TODAY = "2026-10-23"


def _regime(temp=52.0, stage=STAGE_WARMING, flip=FLIP_CONFIRMED):
    return MarketRegime(temp=temp, stage=stage, slope_5m=2.0, flip_state=flip, updated_ts=_NOW)


def _good_event(**kw):
    """一个"结构好、承接好、意愿强、位置不高"的标准样本。"""
    base = dict(
        code="300001",
        ts=_NOW,
        source="TEST",
        price=12.90,
        vwap=12.80,
        vwap_5d=12.50,
        base_support=12.55,
        resistance=13.40,
        day_high=13.20,
        day_low=12.30,
        pct=4.0,
        vol_ratio=2.2,
        turnover=8.0,
        amount_wan=80000.0,
        taker_buy_ratio=72.0,
        bid_pressure=68.0,
        structure_clarity=80.0,
        minutes_above_vwap=60.0,
        slope_score=85.0,
        intent_score=88.0,
        velocity_pct=1.2,
        sector_resonance=75.0,
        is_leader=True,
        launch_ts=_NOW - 300.0,
        freshness_s=1.0,
        trade_date=_TODAY,
    )
    base.update(kw)
    return SignalEvent(**base)


class TestVeto(unittest.TestCase):
    def setUp(self):
        self.engine = FusionEngine(today=_TODAY)

    def test_chase_is_veto_not_deduction(self):
        ev = _good_event(price=13.72)   # 偏离均价 7.2%
        d = self.engine.evaluate(ev, _regime())
        self.assertEqual(d.tier, 0)
        self.assertIn("追高透支", d.veto_reason)
        self.assertEqual(d.size_pct, 0.0)

    def test_structure_broken_is_veto(self):
        ev = _good_event(price=12.40, base_support=12.55)
        d = self.engine.evaluate(ev, _regime())
        self.assertEqual(d.tier, 0)
        self.assertIn("跌破底台", d.veto_reason)

    def test_stale_and_cross_day_are_veto(self):
        d1 = self.engine.evaluate(_good_event(freshness_s=60.0), _regime())
        self.assertIn("数据过期", d1.veto_reason)
        d2 = self.engine.evaluate(_good_event(trade_date="2026-10-22"), _regime())
        self.assertIn("跨交易日", d2.veto_reason)

    def test_ebb_non_leader_is_veto(self):
        d = self.engine.evaluate(
            _good_event(is_leader=False),
            MarketRegime(temp=50.0, stage="COOLING_EBB", flip_state=FLIP_FADING),
        )
        self.assertEqual(d.tier, 0)
        self.assertIn("退潮", d.veto_reason)


class TestPositionMatters(unittest.TestCase):
    """本次需求的核心：涨幅相同，位置不同，结论必须不同。"""

    def test_near_vwap_beats_high_position(self):
        near = _good_event(price=12.90, day_high=13.20)
        high = _good_event(price=13.50, day_high=13.50, resistance=13.60)

        s_near, _ = score_position(near)
        s_high, _ = score_position(high)
        self.assertGreater(s_near, s_high + 20.0)

        engine = FusionEngine(today=_TODAY)
        d_near = engine.evaluate(near, _regime())
        d_high = engine.evaluate(high, _regime())
        self.assertGreater(d_near.tier, d_high.tier)

    def test_same_pct_different_grade(self):
        """同样 +4%，贴均价与已在日内高位，梯度必须拉开。"""
        a = _good_event(code="300002", price=12.90, pct=4.0, day_high=13.20)
        b = _good_event(code="300003", price=13.31, pct=4.0, day_high=13.31, resistance=13.35)
        engine = FusionEngine(today=_TODAY)
        da = engine.evaluate(a, _regime())
        db = engine.evaluate(b, _regime())
        self.assertGreater(da.rar, db.rar)
        self.assertGreater(da.tier, db.tier)


class TestTimeDecay(unittest.TestCase):
    def setUp(self):
        self.engine = FusionEngine(today=_TODAY)

    def test_early_gets_full_size(self):
        d = self.engine.evaluate(_good_event(launch_ts=_NOW - 120.0), _regime())
        self.assertEqual(d.tier, 4)
        self.assertAlmostEqual(d.age_coef, 1.0, places=2)
        self.assertAlmostEqual(d.size_pct, 30.0, places=1)

    def test_40min_late_cannot_be_l4(self):
        d = self.engine.evaluate(_good_event(launch_ts=_NOW - 40 * 60.0), _regime())
        self.assertLessEqual(d.tier, 2)
        self.assertLess(d.age_coef, 0.8)

    def test_very_late_is_zero(self):
        d = self.engine.evaluate(_good_event(launch_ts=_NOW - 120 * 60.0), _regime())
        self.assertEqual(d.tier, 0)
        self.assertEqual(d.size_pct, 0.0)


class TestRegimeMatrix(unittest.TestCase):
    def setUp(self):
        self.engine = FusionEngine(today=_TODAY)

    def test_overheat_non_leader_capped(self):
        d = self.engine.evaluate(
            _good_event(is_leader=False, sector_resonance=40.0),
            _regime(temp=66.0, stage=STAGE_OVERHEAT, flip=FLIP_CONFIRMED),
        )
        self.assertLessEqual(d.tier, 2)
        self.assertLess(d.temp_coef, 0.8)

    def test_armed_raises_cap_in_cold(self):
        cold = MarketRegime(temp=44.0, stage=STAGE_COLD, flip_state="IDLE")
        armed = MarketRegime(temp=44.0, stage=STAGE_COLD, flip_state=FLIP_ARMED)
        d_cold = self.engine.evaluate(_good_event(), cold)
        d_armed = self.engine.evaluate(_good_event(), armed)
        self.assertGreaterEqual(d_armed.tier, d_cold.tier)
        self.assertGreater(d_armed.temp_coef, d_cold.temp_coef)

    def test_l4_requires_leader_or_resonance(self):
        d = self.engine.evaluate(
            _good_event(is_leader=False, sector_resonance=30.0), _regime()
        )
        self.assertLessEqual(d.tier, 3)


class TestRegimeTracker(unittest.TestCase):
    def test_armed_on_low_level_turn(self):
        tr = MarketRegimeTracker()
        t0 = _NOW
        tr.update(RegimeSample(ts=t0, up_ratio=0.38, limit_up=8, limit_down=6, seal_rate=0.7, temp=40.0))
        r = tr.update(RegimeSample(ts=t0 + 300, up_ratio=0.58, limit_up=20, limit_down=2, seal_rate=0.85, temp=45.0))
        self.assertEqual(r.flip_state, FLIP_ARMED)
        self.assertGreater(r.slope_5m, 1.5)

    def test_fading_on_cooling(self):
        tr = MarketRegimeTracker()
        t0 = _NOW
        tr.update(RegimeSample(ts=t0, up_ratio=0.75, limit_up=60, limit_down=2, seal_rate=0.9, temp=62.0))
        r = tr.update(RegimeSample(ts=t0 + 300, up_ratio=0.50, limit_up=40, limit_down=8, seal_rate=0.55, temp=52.0))
        self.assertEqual(r.flip_state, FLIP_FADING)
        self.assertEqual(r.stage, "COOLING_EBB")


class TestBusConvergence(unittest.TestCase):
    def test_one_decision_per_code(self):
        bus = FusionBus(FusionEngine(today=_TODAY))
        bus.update(_good_event(source="天梯"), _regime())
        bus.update(_good_event(source="龙头突击"), _regime())
        top = bus.top(10)
        self.assertEqual(len(top), 1)
        self.assertEqual(set(top[0].sources), {"天梯", "龙头突击"})

    def test_ordering_and_one_line(self):
        bus = FusionBus(FusionEngine(today=_TODAY))
        bus.update(_good_event(code="300001"), _regime())
        bus.update(_good_event(code="300002", price=13.31, day_high=13.31, resistance=13.35), _regime())
        top = bus.top(10)
        self.assertEqual(top[0].tier >= top[-1].tier, True)
        line = top[0].one_line()
        self.assertIn("RAR", line)
        self.assertIn("仓", line)


class TestPortfolioCap(unittest.TestCase):
    """组合级配额：单票评分独立，温度一翻转可能同时冒出多只 L4。"""

    def test_l4_count_capped(self):
        bus = FusionBus(FusionEngine(today=_TODAY), max_l4=1, max_total_pct=200.0)
        for code in ("300001", "300002", "300003"):
            bus.update(_good_event(code=code), _regime())
        pf = bus.rebalance()
        self.assertEqual(sum(1 for d in pf if d.tier == 4), 1)
        self.assertEqual(pf[0].tier, 4)   # 最强的保留 L4
        self.assertTrue(all(d.tier <= 4 for d in pf))

    def test_total_budget_enforced(self):
        bus = FusionBus(FusionEngine(today=_TODAY), max_l4=5, max_total_pct=40.0)
        for code in ("300001", "300002", "300003"):
            bus.update(_good_event(code=code), _regime())
        pf = bus.rebalance()
        self.assertLessEqual(bus.total_size_pct(), 40.0)
        self.assertGreaterEqual(pf[0].tier, pf[-1].tier)

    def test_rebalance_keeps_ranking(self):
        bus = FusionBus(FusionEngine(today=_TODAY), max_l4=2, max_total_pct=85.0)
        bus.update(_good_event(code="300001"), _regime())
        bus.update(_good_event(code="300009", price=13.31, day_high=13.31, resistance=13.35), _regime())
        pf = bus.rebalance()
        self.assertGreaterEqual(pf[0].rar, pf[-1].rar)


if __name__ == "__main__":
    unittest.main(verbosity=2)
