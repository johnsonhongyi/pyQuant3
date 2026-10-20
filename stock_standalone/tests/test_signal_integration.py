# -*- coding: utf-8 -*-
"""tests/test_signal_integration.py — L0→L1→L2 端到端联调测试。

证明"时间轴真的能驱动状态机"：
盘前身份(Profile) → 逐 bar 灌入轨迹(Hub/TrackSeries) → 从轨迹派生结构/斜率/站线比例
→ 组装 SignalContext → 状态机迁移 → 持仓账本落账。

纯合成价格序列，不触碰行情源。
"""

import time
import unittest

from ats.premarket_profile import PreMarketProfile
from ats.signal_state_machine import (
    PositionLedger,
    SignalContext,
    SignalState,
    SignalStateMachine,
)
from ats.signal_timeline import BarClock, TimelineHub

_DAY = time.mktime((2026, 10, 20, 0, 0, 0, 0, 0, -1))
_CLK = BarClock(15)

_PROFILE_ROW = {
    "code": "600000", "name": "测试股", "trade": 10.88,
    "nhigh": 11.00, "nlow": 10.40,
    "resist_today": 11.00, "support_today": 10.50, "ptop": 11.90,
    "dff2": 6.0, "dff3": 4.0, "ch_slope_deg": 7.0,
    "ch_supp_slope": 0.3, "ch_supp_pos": 0.7, "TrendS": 2.0,
    "structure_base_score": 75.0, "win": 3.0, "power_idx": 2.0, "obs_d": 0.0,
    "lasth1d": 11.10, "lastl1d": 10.60, "lastp1d": 10.85,
    "lasth2d": 11.00, "lastl2d": 10.55, "lastp2d": 10.80,
    "lasth3d": 10.95, "lastl3d": 10.50, "lastp3d": 10.75,
}

_BASE_PRICE = 10.40   # 用于计算当日涨幅


def _build_ctx(hub: TimelineHub, prof: PreMarketProfile, code: str,
               bid: int, price: float, high: float, low: float,
               vol_confirm: float = 1.35, alpha: float = 1.2) -> SignalContext:
    s = hub.series(code)
    return SignalContext(
        code=code,
        bar_id=bid,
        ts=_CLK.bar_start_ts(bid, _DAY),
        price=price,
        pct=(price / _BASE_PRICE - 1.0) * 100.0,
        high=high,
        low=low,
        vwap=price * 0.998,
        market_temp=56.0,
        trigger_line=prof.trigger_line,
        defend_line=prof.defend_line,
        structure=s.structure(12, 2, bid),
        slope_3=s.slope(3, bid),
        slope_12=s.slope(12, bid),
        vol_confirm=vol_confirm,
        alpha_today=alpha,
        above_ratio=s.above_ratio(prof.trigger_line, 4, bid),
        tradable=True,
        temp_regime="",
    )


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.prof = PreMarketProfile.from_row(_PROFILE_ROW)
        self.hub = TimelineHub(15, capacity=240)
        self.led = PositionLedger(8)
        self.m = SignalStateMachine(
            "600000",
            self.prof.trigger_params.derive_for(self.prof.vol_budget_pct, 10.0),
            self.led,
        )

    def test_profile_gate_passes(self):
        self.assertNotEqual(self.prof.gate, "REJECT")
        self.assertAlmostEqual(self.prof.trigger_line, 11.00, places=3)
        self.assertAlmostEqual(self.prof.defend_line, 10.50, places=3)

    def test_rising_sequence_reaches_accel_then_exits(self):
        # 上行序列：逼近 -> 突破 -> 加速 -> 破位
        prices = [
            10.88, 10.90, 10.92, 10.95, 10.98,
            11.02, 11.06, 11.10, 11.15, 11.20, 11.26, 11.32,
        ]
        seen = []
        for i, p in enumerate(prices):
            hi, lo = p * 1.002, p * 0.998
            self.hub.ingest("600000", _CLK.bar_start_ts(i, _DAY), p, high=hi, low=lo)
            ctx = _build_ctx(self.hub, self.prof, "600000", i, p, hi, lo)
            self.m.step(ctx)
            if self.m.state not in seen:
                seen.append(self.m.state)

        self.assertIn(SignalState.ARMED.value, seen)
        self.assertIn(SignalState.TRIGGERED.value, seen)
        self.assertIn(SignalState.HOLDING.value, seen)
        self.assertTrue(self.led.is_open("600000"))
        self.assertIsNotNone(self.m.position)
        # 加速：涨幅已超阈值且斜率同向为正
        self.assertIn(self.m.state, (SignalState.ACCEL.value, SignalState.TRAILING.value,
                                     SignalState.HOLDING.value))

        # 破位下杀：必须进入退场流程，原因可追溯
        b = len(prices)
        crash = 10.30
        for j in range(3):
            bid = b + j
            self.hub.ingest("600000", _CLK.bar_start_ts(bid, _DAY), crash,
                            high=crash * 1.001, low=crash * 0.995)
            ctx = _build_ctx(self.hub, self.prof, "600000", bid, crash,
                             crash * 1.001, crash * 0.995)
            self.m.step(ctx)
        self.assertIn(self.m.state, (SignalState.EXITING.value, SignalState.EXITED.value))

        # 再推一根确保收敛到 EXITED 并落账
        bid = b + 3
        ctx = _build_ctx(self.hub, self.prof, "600000", bid, crash,
                         crash * 1.001, crash * 0.995)
        self.m.step(ctx)
        self.assertEqual(self.m.state, SignalState.EXITED.value)
        closed = self.led.closed_positions()
        self.assertEqual(len(closed), 1)
        self.assertLess(closed[0].realized_pct, 0.0)
        self.assertIn(closed[0].exit_reason,
                      ("STOP_LOSS", "ACCEL_STOP", "TRAIL_STOP", "STRUCT_BREAK"))

    def test_state_level_is_monotonic_before_exit(self):
        prices = [10.88, 10.90, 10.92, 10.96, 11.02, 11.08, 11.14, 11.20]
        levels = []
        for i, p in enumerate(prices):
            hi, lo = p * 1.002, p * 0.998
            self.hub.ingest("600000", _CLK.bar_start_ts(i, _DAY), p, high=hi, low=lo)
            self.m.step(_build_ctx(self.hub, self.prof, "600000", i, p, hi, lo))
            levels.append(self.m.level)
        # 退场前层级不得下降
        for a, b in zip(levels, levels[1:]):
            self.assertLessEqual(a, b)

    def test_events_are_recorded_with_bar_and_reason(self):
        prices = [10.88, 10.90, 10.92, 10.96, 11.02, 11.08, 11.14]
        for i, p in enumerate(prices):
            hi, lo = p * 1.002, p * 0.998
            self.hub.ingest("600000", _CLK.bar_start_ts(i, _DAY), p, high=hi, low=lo)
            self.m.step(_build_ctx(self.hub, self.prof, "600000", i, p, hi, lo))
        evs = self.m.events(limit=50)
        self.assertGreater(len(evs), 0)
        for e in evs:
            self.assertGreaterEqual(e["bar_id"], 0)
            self.assertTrue(e["reason_code"])
            self.assertTrue(e["reason_text"])
            self.assertIn("evidence", e)


if __name__ == "__main__":
    unittest.main(verbosity=2)
