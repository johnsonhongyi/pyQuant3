# -*- coding: utf-8 -*-
"""诱多陷阱、跨日风险、T+1 持仓决策、状态落盘、IPC 桥接 —— 自检。"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.fusion.tracker import RaceTracker, TrackConfig, STAGE_ENTER, STAGE_EVICT, STAGE_HOLD
from ats.fusion.trap import (
    ACT_ADD,
    ACT_CLEAR,
    ACT_HALF,
    ACT_HOLD,
    TRAP_GAP_FADE,
    TRAP_PREV_DUMP,
    TRAP_SPIKE_FADE,
    TRAP_VOL_STALL,
    cross_day_risk,
    detect_traps,
    position_decision,
)

T0 = 1792700000.0
BAR = 180.0


class TestTraps(unittest.TestCase):
    def test_spike_fade(self):
        """冲高 5% 后回落 3% 并跌破均价 -> 冲高回落。"""
        t = detect_traps(price=10.2, prev_close=10.0, day_open=10.1, day_high=10.5,
                         vwap=10.35, pct=2.0, prev_pct=1.0, vol_ratio=1.8)
        self.assertIn(TRAP_SPIKE_FADE, t)

    def test_no_spike_fade_when_above_vwap(self):
        """回落但仍在均价上方：不算诱多（可能只是震荡）。"""
        t = detect_traps(price=10.3, prev_close=10.0, day_open=10.1, day_high=10.5,
                         vwap=10.2, pct=3.0, prev_pct=1.0, vol_ratio=1.8)
        self.assertNotIn(TRAP_SPIKE_FADE, t)

    def test_gap_fade(self):
        t = detect_traps(price=10.2, prev_close=10.0, day_open=10.5, day_high=10.6,
                         vwap=10.25, pct=2.0, prev_pct=1.0, vol_ratio=1.6)
        self.assertIn(TRAP_GAP_FADE, t)

    def test_prev_surge_dump(self):
        """昨日大涨 +8%，今日 -3% 放量 -> 最差信号。"""
        t = detect_traps(price=9.7, prev_close=10.0, day_open=9.9, day_high=10.0,
                         vwap=9.9, pct=-3.0, prev_pct=8.0, vol_ratio=1.6)
        self.assertIn(TRAP_PREV_DUMP, t)

    def test_vol_stall(self):
        t = detect_traps(price=9.9, prev_close=10.0, day_open=10.0, day_high=10.05,
                         vwap=10.0, pct=0.3, prev_pct=1.0, vol_ratio=2.5)
        self.assertIn(TRAP_VOL_STALL, t)

    def test_clean_stock_no_trap(self):
        t = detect_traps(price=10.6, prev_close=10.0, day_open=10.1, day_high=10.65,
                         vwap=10.3, pct=6.0, prev_pct=2.0, vol_ratio=1.9)
        self.assertEqual(t, [])

    def test_cross_day_risk_high_after_limit_up_with_shadow(self):
        score, notes = cross_day_risk(prev_pct=9.8, prev_close_pos=0.3,
                                      prev_upper_shadow=0.6, ret5d=20.0, prev_amp=11.0)
        self.assertGreaterEqual(score, 80.0)
        self.assertTrue(any("涨停" in n for n in notes))

    def test_cross_day_risk_low_for_quiet(self):
        score, _ = cross_day_risk(prev_pct=1.0, prev_close_pos=0.8,
                                  prev_upper_shadow=0.1, ret5d=3.0, prev_amp=3.0)
        self.assertLess(score, 20.0)


class TestPositionDecision(unittest.TestCase):
    def test_clear_on_prev_surge_dump(self):
        act, why = position_decision(70.0, [TRAP_PREV_DUMP], 60.0, 1.0)
        self.assertEqual(act, ACT_CLEAR)
        self.assertIn("昨日大涨", why)

    def test_half_on_gap_fade(self):
        act, _ = position_decision(65.0, [TRAP_GAP_FADE], 40.0, 1.5)
        self.assertEqual(act, ACT_HALF)

    def test_add_on_persist_no_trap(self):
        act, _ = position_decision(80.0, [], 10.0, 0.0)
        self.assertEqual(act, ACT_ADD)

    def test_hold_normal(self):
        act, _ = position_decision(60.0, [], 10.0, 1.0)
        self.assertEqual(act, ACT_HOLD)

    def test_half_on_weak_persist(self):
        act, _ = position_decision(40.0, [], 10.0, 1.0)
        self.assertEqual(act, ACT_HALF)


class TestTrackerWithTraps(unittest.TestCase):
    def _feed(self, tr, code, n, day, gap_risk=0.0, traps=None, start=10.0):
        st = None
        for i in range(n):
            st = tr.update(
                code=code, ts=T0 + i * BAR, price=start + i * 0.1, pct=0.5 + i * 0.6,
                vwap10=9.9, vwap=9.95, vol_ratio=1.7, tier=2, rar=60.0,
                patterns=["两阳加速"] if i == 1 else [], day=day,
                anomaly=(i == 0), traps=traps or [], gap_risk=gap_risk,
            )
        return st

    def test_high_gap_risk_blocks_entry(self):
        tr = RaceTracker()
        st = self._feed(tr, "300001", 8, "2026-10-23", gap_risk=90.0)
        self.assertNotEqual(st.stage, STAGE_ENTER, "跨日风险>=80 不应入局")

    def test_trap_blocks_entry(self):
        tr = RaceTracker()
        st = self._feed(tr, "300002", 8, "2026-10-23", traps=[TRAP_SPIKE_FADE])
        self.assertNotEqual(st.stage, STAGE_ENTER, "正在冲高回落不应入局")

    def test_carried_position_cleared_on_prev_dump(self):
        """昨日入局，今日"前日大涨今日杀跌" -> 清仓。"""
        tr = RaceTracker()
        self._feed(tr, "300003", 6, "2026-10-23")
        self.assertEqual(tr.get("300003").stage, STAGE_ENTER)
        st = None
        for i in range(4):
            st = tr.update(code="300003", ts=T0 + 86400 + i * BAR, price=10.0 - i * 0.1,
                           pct=-2.5, vwap10=10.2, vwap=10.1, vol_ratio=1.8, tier=0,
                           rar=20.0, patterns=[], day="2026-10-26",
                           traps=[TRAP_PREV_DUMP], gap_risk=70.0)
        self.assertEqual(st.stage, STAGE_EVICT, "T+1 昨日大涨今日杀跌应清仓")
        t1 = [e for e in tr.events() if e["kind"] == "T1"]
        self.assertTrue(t1 and t1[0]["action"] == ACT_CLEAR)

    def test_state_save_load_roundtrip(self):
        tr = RaceTracker()
        self._feed(tr, "300004", 6, "2026-10-23")
        path = os.path.join(tempfile.mkdtemp(), "state.json")
        self.assertEqual(tr.save(path), 1)
        tr2 = RaceTracker()
        self.assertEqual(tr2.load(path), 1)
        a, b = tr.get("300004"), tr2.get("300004")
        self.assertEqual(a.stage, b.stage)
        self.assertAlmostEqual(a.persist, b.persist, places=3)
        self.assertEqual(a.enter_price, b.enter_price)


class TestLiveBridge(unittest.TestCase):
    def test_field_tolerance_and_no_raise(self):
        from ats.fusion.live_bridge import FusionLiveBridge

        b = FusionLiveBridge(state_path=os.path.join(tempfile.mkdtemp(), "s.json"),
                             vwap10_provider=lambda c: 9.95)
        # 各种字段命名
        for payload in (
            {"secid": "300296", "last": 10.1, "change_pct": 1.0, "vol_ratio": 1.7, "level": 2},
            {"stock_code": "300296", "price": 10.2, "pct": 2.0, "tags": "两阳加速"},
            {"ts_code": "300296.SZ", "now": 10.3, "percent": 3.0},
            {}, None, "garbage", 123,
        ):
            b.on_signal(payload)   # 不应抛异常
        self.assertGreaterEqual(b.stats["signals"], 3)
        self.assertEqual(b.stats["errors"], 0)
        self.assertIsNotNone(b.tracker.get("300296"))

    def test_callback_batch(self):
        from ats.fusion.live_bridge import FusionLiveBridge

        b = FusionLiveBridge(state_path=os.path.join(tempfile.mkdtemp(), "s.json"))
        cb = b.make_callback()
        cb([{"code": "600000", "price": 10, "pct": 1}, {"code": "600001", "price": 20, "pct": 2}])
        self.assertEqual(len(b.tracker.states()), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
