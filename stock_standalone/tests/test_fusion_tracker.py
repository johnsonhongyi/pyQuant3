# -*- coding: utf-8 -*-
"""赛马跟踪器自检：验证"带旧信号 / 第一波入局 / 入局后才剔除"。"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.fusion.tracker import (
    RaceTracker,
    TrackConfig,
    STAGE_WATCH,
    STAGE_ENTER,
    STAGE_EVICT,
    STAGE_HOLD,
)

T0 = time.mktime((2026, 10, 23, 9, 30, 0, 0, 0, -1))
BAR = 180.0   # 3 分钟


def _feed(tracker, code, prices, pcts, vols, vwap10, tier=2, patterns=None, day="2026-10-23"):
    """按 bar 喂入，返回每根之后的 state。"""
    out = []
    for i, (p, pc, v) in enumerate(zip(prices, pcts, vols)):
        pats = patterns[i] if isinstance(patterns, list) and patterns and isinstance(patterns[0], list) else (patterns or [])
        out.append(
            tracker.update(
                code=code, ts=T0 + i * BAR, price=p, pct=pc,
                vwap10=vwap10, vol_ratio=v, tier=tier, rar=60.0 + i,
                patterns=pats, day=day, anomaly=(i == 0),
            )
        )
    return out


class TestRaceTracker(unittest.TestCase):
    def setUp(self):
        self.cfg = TrackConfig()

    def test_strong_stock_enters_first_wave(self):
        """量能持续 + 想的多回踩的少 -> 应在第一波（自首异动 <5%）入局。"""
        tr = RaceTracker(self.cfg)
        prices = [10.00, 10.06, 10.12, 10.18, 10.26, 10.34, 10.42]
        pcts = [0.6, 1.2, 1.8, 2.4, 3.2, 4.0, 4.8]
        vols = [1.6, 1.8, 1.7, 1.9, 2.0, 1.8, 1.7]
        states = _feed(tr, "300111", prices, pcts, vols, vwap10=9.95,
                       patterns=[["逆势带头"], ["缩量转放量"], ["两阳加速"], [], [], [], []])
        entered = [s for s in states if s.stage == STAGE_ENTER]
        self.assertTrue(entered, "强势持续票应入局")
        e = entered[0]
        self.assertLessEqual(e.since_first_pct, 5.0, "第一波入局不应追高")
        self.assertGreaterEqual(e.evidence_count(), 2, "入局必须带上至少两条旧证据")
        self.assertTrue(e.chain(), "证据链不应为空")

    def test_choppy_stock_never_enters(self):
        """来回震荡、回踩与上涨相当 -> 不入局（想的多回踩的少 不成立）。"""
        tr = RaceTracker(self.cfg)
        prices = [10.00, 10.10, 9.98, 10.09, 9.97, 10.08, 9.96, 10.07]
        pcts = [0.0, 1.0, -0.2, 0.9, -0.3, 0.8, -0.4, 0.7]
        vols = [1.3] * 8
        states = _feed(tr, "300222", prices, pcts, vols, vwap10=10.5,
                       patterns=[["逆势带头"]] + [[]] * 7)
        self.assertFalse([s for s in states if s.stage == STAGE_ENTER], "震荡票不应入局")

    def test_evict_only_after_entry(self):
        """入局后跌破 10 日 VWAP -> 剔除；入局前不因下跌剔除。"""
        tr = RaceTracker(self.cfg)
        up = _feed(tr, "300333",
                   prices=[10.0, 10.1, 10.2, 10.3, 10.4, 10.5],
                   pcts=[0.5, 1.2, 2.0, 2.8, 3.6, 4.4],
                   vols=[1.7, 1.8, 1.9, 1.8, 1.7, 1.6],
                   vwap10=9.9, patterns=[["逆势带头"], ["缩量转放量"], ["两阳加速"], [], [], []])
        self.assertEqual(up[-1].stage, STAGE_ENTER, "先要入局")
        enter_price = up[-1].enter_price
        # 入局后连跌，跌破 vwap10*0.985
        st = None
        for i, (p, pc) in enumerate([(10.35, 3.0), (10.12, 1.0), (9.90, -1.2)]):
            st = tr.update(code="300333", ts=T0 + (6 + i) * BAR, price=p, pct=pc,
                           vwap10=10.1, vol_ratio=0.8, tier=1, rar=40.0, patterns=[], day="2026-10-23")
        self.assertEqual(st.stage, STAGE_EVICT, "跌破10日VWAP应剔除")
        self.assertLess(enter_price, 10.6)
        ev = [e for e in tr.events() if e["kind"] == STAGE_EVICT]
        self.assertTrue(ev and "VWAP" in ev[-1]["reason"])

    def test_pre_entry_not_evicted_by_low_score(self):
        """入局前即使持续分很低也不剔除（这是"入局以后才开始剔除"）。"""
        tr = RaceTracker(self.cfg)
        st = None
        for i in range(10):
            st = tr.update(code="300444", ts=T0 + i * BAR, price=10.0 + (0.01 if i % 2 else -0.01),
                           pct=0.3, vwap10=10.6, vol_ratio=1.0, tier=0, rar=20.0,
                           patterns=["逆势带头"] if i == 0 else [], day="2026-10-23")
        self.assertEqual(st.stage, STAGE_WATCH, "入局前不应被剔除")
        self.assertLess(st.persist, 60.0)

    def test_evidence_accumulates_and_dedups(self):
        """同一形态重复出现只记一次；不同形态累积。"""
        tr = RaceTracker(self.cfg)
        st = _feed(tr, "300555",
                   prices=[10.0 + i * 0.05 for i in range(8)],
                   pcts=[0.5 + i * 0.5 for i in range(8)],
                   vols=[1.6] * 8, vwap10=9.9,
                   patterns=[["逆势带头"]] * 4 + [["缩量转放量"]] * 4)[-1]
        self.assertEqual(st.patterns_seen.get("逆势带头"), 1)
        self.assertIn("缩量转放量", st.patterns_seen)

    def test_cross_day_carry(self):
        """昨日入局未剔除 -> 今日以持有开局（多日连续性）。"""
        tr = RaceTracker(self.cfg)
        _feed(tr, "300666",
              prices=[10.0, 10.1, 10.2, 10.3, 10.4, 10.5],
              pcts=[0.5, 1.2, 2.0, 2.8, 3.6, 4.4],
              vols=[1.7, 1.8, 1.9, 1.8, 1.7, 1.6],
              vwap10=9.9, patterns=[["逆势带头"], ["缩量转放量"], ["两阳加速"], [], [], []],
              day="2026-10-23")
        self.assertEqual(tr.get("300666").stage, STAGE_ENTER)
        st = tr.update(code="300666", ts=T0 + 86400, price=10.6, pct=1.0,
                       vwap10=10.2, vol_ratio=1.5, tier=2, rar=60.0,
                       patterns=["两阳加速"], day="2026-10-26")
        self.assertEqual(st.stage, STAGE_HOLD, "跨日应携带昨日入局状态")
        self.assertTrue(st.day_summaries)


class TestDeployRule(unittest.TestCase):
    """可下单闸门：赛道强 + 第一波 + 想的多回踩的少 + 量能持续。"""

    def _entry(self, **kw):
        base = dict(stage=STAGE_ENTER, theme_rank=0.8, first_pct=2.0,
                    efficiency=0.9, persist=65.0, patterns={"两阳加速": 1},
                    consensus=0.30, lead_value=0.70)
        base.update(kw)
        return base

    def test_pass(self):
        from ats.fusion.tracker import is_deployable
        self.assertTrue(is_deployable(self._entry()))

    def test_reject_chase(self):
        from ats.fusion.tracker import is_deployable
        self.assertFalse(is_deployable(self._entry(first_pct=6.0)), "首异动已涨6%属追高")

    def test_reject_weak_theme(self):
        from ats.fusion.tracker import is_deployable
        self.assertFalse(is_deployable(self._entry(theme_rank=0.3)), "赛道弱不应下单")

    def test_reject_choppy(self):
        from ats.fusion.tracker import is_deployable
        self.assertFalse(is_deployable(self._entry(efficiency=0.5)), "回踩过多不应下单")

    def test_reject_no_pattern(self):
        from ats.fusion.tracker import is_deployable
        self.assertFalse(is_deployable(self._entry(patterns={})), "无形态不应下单")

    def test_reject_consensus(self):
        from ats.fusion.tracker import is_deployable
        self.assertFalse(is_deployable(self._entry(consensus=0.75)),
                         "趋同>=0.6 时不下单（大家都涨了，跟单容易被埋）")

    def test_reject_low_lead_value(self):
        from ats.fusion.tracker import is_deployable
        self.assertFalse(is_deployable(self._entry(lead_value=0.40)),
                         "带头价值<0.5（高温高趋同）不下单")


class TestPhaseGate(unittest.TestCase):
    """战役阶段闸门：退守期不再一刀切，放排头兵/夺旗（否则永远没样本）。"""

    PRICES = [10.0, 10.06, 10.12, 10.18, 10.26, 10.34, 10.42]
    PCTS = [0.6, 1.2, 1.8, 2.4, 3.2, 4.0, 4.8]
    VOLS = [1.6, 1.8, 1.7, 1.9, 2.0, 1.8, 1.7]
    PATS = [["逆势带头"], ["缩量转放量"], ["两阳加速"], [], [], [], []]

    def _entries(self, phase, label, allow=True):
        tr = RaceTracker(TrackConfig(retreat_allow_vanguard=allow))
        states = []
        for i, (p, pc, v) in enumerate(zip(self.PRICES, self.PCTS, self.VOLS)):
            states.append(tr.update(
                code="300444", ts=T0 + i * BAR, price=p, pct=pc, vwap10=9.95,
                vol_ratio=v, tier=2, rar=60.0 + i, patterns=self.PATS[i],
                day="2026-10-23", anomaly=(i == 0),
                phase=phase, lead_label=label,
            ))
        return [s for s in states if s.stage == STAGE_ENTER]

    def test_retreat_allows_vanguard(self):
        self.assertTrue(self._entries("退守", "排头兵"), "退守期应放排头兵")

    def test_retreat_allows_flag(self):
        self.assertTrue(self._entries("退守", "夺旗"), "退守期应放夺旗")

    def test_retreat_blocks_followers(self):
        self.assertFalse(self._entries("退守", "跟风"), "退守期不碰跟风")
        self.assertFalse(self._entries("退守", "冲锋队"), "退守期不碰冲锋队")

    def test_retreat_switch_can_turn_off(self):
        self.assertFalse(self._entries("退守", "排头兵", allow=False),
                         "开关关闭时回到旧口径：退守一律不入局")

    def test_vanguard_death_allows_vanguard_only(self):
        self.assertTrue(self._entries("先锋阵亡", "夺旗"))
        self.assertFalse(self._entries("先锋阵亡", "冲锋队"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
