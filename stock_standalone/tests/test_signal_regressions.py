# -*- coding: utf-8 -*-
"""tests/test_signal_regressions.py — 逆向路径回归测试。

对应 `docs/tasks/2026-10-21_1235_时序信号引擎P0审核与后续任务评审.md`
中已复现的 5 个缺陷（D1~D5）与 1 个隐患（H1）。

这些用例全部是"主路径之外"的边界：跳空、代码不一致、无账本、僵死、减仓口径。
"""

import time
import unittest

from ats.premarket_profile import PreMarketProfile
from ats.signal_state_machine import (
    PositionLedger,
    SignalContext,
    SignalParams,
    SignalState,
    SignalStateMachine,
)
from ats.signal_timeline import BarClock, Structure, TimelineHub

_DAY = time.mktime((2026, 10, 20, 0, 0, 0, 0, 0, -1))
_CLK = BarClock(15)


def _ts(bid: int) -> float:
    return _CLK.bar_start_ts(bid, _DAY)


def ctx(bid: int, price: float, **kw) -> SignalContext:
    return SignalContext(
        code=kw.pop("code", "600000"),
        bar_id=bid,
        ts=_ts(bid),
        price=price,
        pct=kw.pop("pct", 3.0),
        high=kw.pop("high", price),
        low=kw.pop("low", price),
        vwap=kw.pop("vwap", price * 0.995),
        market_temp=56.0,
        trigger_line=kw.pop("trigger", 11.0),
        defend_line=kw.pop("defend", 10.5),
        structure=kw.pop("struct", Structure.HH_HL),
        slope_3=kw.pop("s3", 0.8),
        slope_12=kw.pop("s12", 0.4),
        vol_confirm=kw.pop("vol", 1.4),
        alpha_today=kw.pop("alpha", 1.5),
        above_ratio=kw.pop("above", 0.8),
        tradable=kw.pop("tradable", True),
        untradable_reason=kw.pop("why", ""),
        temp_regime=kw.pop("regime", ""),
    )


def params(**over):
    base = dict(confirm_bars=2, min_dwell_bars=2, max_hold_bars=50, cooldown_bars=3,
                trail_start_pct=2.5, trail_gap_pct=1.2, max_positions=8,
                gap_max_pct=3.0, arm_stale_multiple=3.0)
    base.update(over)
    return SignalParams(**base)


# ---------------------------------------------------------------------------
# D1 跳空高开：ARMED 不可达时的直通进场
# ---------------------------------------------------------------------------
class GapBreakoutTest(unittest.TestCase):
    def test_gap_above_trigger_enters_via_gap_path(self):
        """价格始终在触发线上方时，必须能通过 GAP_BREAK_TRIGGER 进场。"""
        led = PositionLedger(8)
        m = SignalStateMachine("600000", params(), led)
        for b in range(3):
            m.step(ctx(b, 11.20, trigger=11.0, pct=6.0))
        self.assertIn(m.state, (SignalState.TRIGGERED.value, SignalState.HOLDING.value))
        self.assertTrue(led.is_open("600000"))
        codes = [e["reason_code"] for e in m.events(50)]
        self.assertIn("GAP_BREAK_TRIGGER", codes)

    def test_gap_too_far_is_rejected(self):
        """追高超过 gap_max_pct 不进场，避免在情绪最高点接盘。"""
        led = PositionLedger(8)
        m = SignalStateMachine("600000", params(gap_max_pct=3.0), led)
        for b in range(4):
            m.step(ctx(b, 11.50, trigger=11.0, pct=10.0))   # 高于触发线 4.5%
        self.assertEqual(m.state, SignalState.DORMANT.value)
        self.assertFalse(led.is_open("600000"))

    def test_gap_requires_volume_and_alpha(self):
        """跳空直通同样要过量能与超额门槛，不是"高开就买"。"""
        led = PositionLedger(8)
        m = SignalStateMachine("600000", params(), led)
        for b in range(4):
            m.step(ctx(b, 11.20, trigger=11.0, vol=0.8, alpha=-1.0))
        self.assertEqual(m.state, SignalState.DORMANT.value)
        self.assertFalse(led.is_open("600000"))


# ---------------------------------------------------------------------------
# D2 持仓泄漏：code 不一致与孤儿对账
# ---------------------------------------------------------------------------
class CodeMismatchTest(unittest.TestCase):
    def test_mismatched_ctx_code_is_rejected(self):
        """ctx.code 与 machine.code 不一致时必须拒绝推进，不得开仓。"""
        led = PositionLedger(8)
        m = SignalStateMachine("600006", params(), led)
        for b in range(4):
            m.step(ctx(b, 11.20, trigger=11.0, code="600099"))
        self.assertEqual(m.state, SignalState.DORMANT.value)
        self.assertEqual(len(led.open_positions()), 0)
        self.assertTrue(any(d["type"] == "CODE_MISMATCH" for d in m.diagnostics()))

    def test_open_uses_explicit_code_not_ctx(self):
        """ledger.open 的键由调用方显式传入，不再从 ctx 取。"""
        led = PositionLedger(8)
        led.open("600006", ctx(0, 10.0, code="600099"), "T")
        self.assertTrue(led.is_open("600006"))
        self.assertFalse(led.is_open("600099"))

    def test_reconcile_clears_orphans(self):
        """孤儿仓位对账：清掉不属于活跃集合的仓位，释放名额。"""
        led = PositionLedger(8)
        led.open("600099", ctx(0, 10.0, code="600099"), "T")
        led.mark(ctx(1, 10.5, code="600099", high=10.5))
        removed = led.reconcile({"600006"})
        self.assertEqual(removed, ["600099"])
        self.assertEqual(len(led.open_positions()), 0)
        closed = led.closed_positions()
        self.assertEqual(closed[-1].exit_reason, "ORPHAN_RECONCILE")

    def test_orphan_does_not_permanently_block_capacity(self):
        """泄漏不得让系统伪装成"仓位已满"。"""
        led = PositionLedger(2)
        led.open("600099", ctx(0, 10.0, code="600099"), "T")
        led.open("600098", ctx(0, 10.0, code="600098"), "T")
        self.assertFalse(led.can_open())
        led.reconcile({"600006"})
        self.assertTrue(led.can_open())


# ---------------------------------------------------------------------------
# D3 无账本 -> 不得只进不出
# ---------------------------------------------------------------------------
class LedgerMandatoryTest(unittest.TestCase):
    def test_machine_without_ledger_still_exits(self):
        """不传 ledger 时自动建账本，止损必须生效。"""
        m = SignalStateMachine("600000", params())   # 故意不传 ledger
        self.assertIsNotNone(m._ledger)

        for b in range(2):
            m.step(ctx(b, 10.90, trigger=11.0))       # -> ARMED
        for b in range(2, 4):
            m.step(ctx(b, 11.05, trigger=11.0))       # -> TRIGGERED
        m.step(ctx(4, 11.06, trigger=11.0))           # -> HOLDING
        self.assertEqual(m.state, SignalState.HOLDING.value)
        self.assertIsNotNone(m.position)

        # 一路跌破止损
        for b in range(5, 9):
            m.step(ctx(b, 9.00, trigger=11.0, pct=-18.0, struct=Structure.LH_LL))
        self.assertIn(m.state, (SignalState.EXITING.value, SignalState.EXITED.value))


# ---------------------------------------------------------------------------
# D4 ARMED 僵死
# ---------------------------------------------------------------------------
class ArmStaleTest(unittest.TestCase):
    def test_arm_returns_to_dormant_when_price_drifts_away(self):
        led = PositionLedger(8)
        m = SignalStateMachine("600000", params(), led)
        for b in range(2):
            m.step(ctx(b, 10.90, trigger=11.0))       # 距 0.9% -> ARMED
        self.assertEqual(m.state, SignalState.ARMED.value)

        # 跌到 10.55：距触发线 4.09% > 1.2% * 3，且仍在防守线 10.5 之上
        for b in range(2, 5):
            m.step(ctx(b, 10.55, trigger=11.0, defend=10.5, struct=Structure.HH_HL))
        self.assertEqual(m.state, SignalState.DORMANT.value)
        codes = [e["reason_code"] for e in m.events(50)]
        self.assertIn("ARM_STALE", codes)

    def test_arm_keeps_when_still_near(self):
        """仍在逼近区间内不得误判为僵死。"""
        led = PositionLedger(8)
        m = SignalStateMachine("600000", params(), led)
        for b in range(4):
            m.step(ctx(b, 10.95, trigger=11.0))       # 距 0.45%
        self.assertEqual(m.state, SignalState.ARMED.value)


# ---------------------------------------------------------------------------
# D5 减仓口径
# ---------------------------------------------------------------------------
class WeightedRealizedTest(unittest.TestCase):
    def test_weighted_reflects_partial_trim(self):
        """半仓在高位减、剩余在原价平，加权收益必须体现减仓贡献。"""
        led = PositionLedger(8)
        pos = led.open("600000", ctx(0, 10.0), "T")
        led.trim("600000", ctx(1, 11.0), 0.5, "TRAIL_ARM")
        led.close("600000", ctx(2, 10.0), "STOP_LOSS")

        self.assertAlmostEqual(pos.realized_pct, 0.0, places=2)          # 全仓单一价口径
        self.assertAlmostEqual(pos.realized_pct_weighted, 5.0, places=2)  # 0.5*10% + 0.5*0%
        self.assertEqual(len(pos.trims), 1)

    def test_weighted_equals_plain_without_trims(self):
        led = PositionLedger(8)
        pos = led.open("600000", ctx(0, 10.0), "T")
        led.close("600000", ctx(1, 10.5), "TRAIL_STOP")
        self.assertAlmostEqual(pos.realized_pct, 5.0, places=2)
        self.assertAlmostEqual(pos.realized_pct_weighted, 5.0, places=2)

    def test_summary_uses_weighted(self):
        led = PositionLedger(8)
        led.open("600000", ctx(0, 10.0), "T")
        led.trim("600000", ctx(1, 11.0), 0.5, "TRAIL_ARM")
        led.close("600000", ctx(2, 10.0), "STOP_LOSS")
        s = led.summary()
        self.assertAlmostEqual(s["avg_realized_pct"], 5.0, places=2)
        self.assertEqual(s["win_rate"], 100.0)


# ---------------------------------------------------------------------------
# H1 bar_seconds 热改
# ---------------------------------------------------------------------------
class BarSecondsChangeTest(unittest.TestCase):
    def test_apply_bar_seconds_resets_timeline(self):
        hub = TimelineHub(15, capacity=240)
        hub.ingest("600000", _ts(5), 10.5)
        s = hub.get("600000")
        self.assertAlmostEqual(s.last_price(5), 10.5, places=3)

        changed = hub.apply_bar_seconds(10)
        self.assertTrue(changed)
        self.assertEqual(hub.clock.bar_seconds, 10)
        # 时间轴被清空，避免旧 bar_id 错位后静默取到错位的 bar
        self.assertEqual(s.last_price(5), 0.0)
        self.assertEqual(s.bar_seconds, 10)

        self.assertFalse(hub.apply_bar_seconds(10))   # 同值不重复重置


# ---------------------------------------------------------------------------
# D1-B 触发线不得低于当前价
# ---------------------------------------------------------------------------
class TriggerLineFloorTest(unittest.TestCase):
    def _row(self, **over):
        base = {
            "code": "600000", "name": "T", "trade": 10.50,
            "nhigh": 10.40, "nlow": 10.10,
            "resist_today": 10.20,          # 阻力已在现价下方
            "support_today": 10.10, "ptop": 11.50,
            "dff2": 6.0, "dff3": 4.0, "ch_slope_deg": 7.0,
            "ch_supp_slope": 0.3, "ch_supp_pos": 0.7, "TrendS": 2.0,
            "structure_base_score": 75.0, "win": 3.0, "power_idx": 2.0,
            "lasth1d": 10.70, "lastl1d": 10.20, "lastp1d": 10.45,
        }
        base.update(over)
        return base

    def test_trigger_line_never_below_close(self):
        p = PreMarketProfile.from_row(self._row())
        self.assertGreater(p.trigger_line, 10.50)
        self.assertAlmostEqual(p.trigger_line, 10.50 * 1.002, places=3)

    def test_trigger_line_keeps_resistance_when_above(self):
        p = PreMarketProfile.from_row(self._row(resist_today=10.90))
        self.assertAlmostEqual(p.trigger_line, 10.90, places=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
