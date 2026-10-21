# -*- coding: utf-8 -*-
"""tests/test_signal_state_machine.py — 状态机 + 持仓账本单元测试。

验证文档 §6/§10 的核心不变量：
- 加速不可回退（单调前进）
- 确认 bar 过滤单帧假突破
- 时间纪律 / 止损纪律 / 结构纪律各自可触发
- 不可交易不产生开仓
- MFE 用进场后极值（不受进场前高点污染）
- 退场原因透传不丢
"""

import time
import unittest

from ats.signal_timeline import BarClock, Structure
from ats.signal_state_machine import (
    PositionLedger,
    SignalContext,
    SignalParams,
    SignalState,
    SignalStateMachine,
    WeakStrongRanker,
)

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
        pct=kw.pop("pct", 0.0),
        high=kw.pop("high", price),
        low=kw.pop("low", price),
        vwap=kw.pop("vwap", price),
        market_temp=kw.pop("temp", 55.0),
        trigger_line=kw.pop("trigger", 11.0),
        defend_line=kw.pop("defend", 10.5),
        structure=kw.pop("struct", Structure.HH_HL),
        slope_3=kw.pop("s3", 0.5),
        slope_12=kw.pop("s12", 0.3),
        vol_confirm=kw.pop("vol", 1.3),
        alpha_today=kw.pop("alpha", 1.0),
        above_ratio=kw.pop("above", 0.7),
        tradable=kw.pop("tradable", True),
        untradable_reason=kw.pop("why", ""),
        temp_regime=kw.pop("regime", ""),
    )


def _params(**over):
    base = dict(
        bar_seconds=15, confirm_bars=2, min_dwell_bars=2, arm_dist_pct=1.2,
        trail_start_pct=2.5, trail_gap_pct=1.2, max_hold_bars=50,
        min_progress_pct=1.0, cooldown_bars=3, max_positions=8,
    )
    base.update(over)
    return SignalParams(**base)


def _arm(m: SignalStateMachine, b: int):
    """把机器推进到 ARMED（两根确认 bar）。"""
    m.step(ctx(b, 10.90))
    m.step(ctx(b + 1, 10.90))
    return b + 2


def _hold(m: SignalStateMachine, b: int):
    """把机器推进到 HOLDING。"""
    b = _arm(m, b)
    m.step(ctx(b, 11.05, pct=3.0))
    m.step(ctx(b + 1, 11.06, pct=3.1))
    m.step(ctx(b + 2, 11.06, pct=3.1))
    return b + 3


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.led = PositionLedger(8)
        self.m = SignalStateMachine("600000", _params(), self.led)

    def test_arm_requires_two_bars(self):
        self.m.step(ctx(0, 10.90))
        self.assertEqual(self.m.state, SignalState.DORMANT.value)
        self.m.step(ctx(1, 10.90))
        self.assertEqual(self.m.state, SignalState.ARMED.value)

    def test_trigger_opens_position(self):
        b = _arm(self.m, 0)
        self.m.step(ctx(b, 11.05, pct=3.0))
        self.assertEqual(self.m.state, SignalState.ARMED.value)   # 仅 1 根确认，不触发
        self.m.step(ctx(b + 1, 11.06, pct=3.1))
        self.assertEqual(self.m.state, SignalState.TRIGGERED.value)
        self.assertTrue(self.led.is_open("600000"))

    def test_triggered_rolls_to_holding(self):
        b = _hold(self.m, 0)
        self.assertEqual(self.m.state, SignalState.HOLDING.value)

    def test_accel_locks(self):
        b = _hold(self.m, 0)
        accel_ctx = dict(pct=6.0, s3=1.0, s12=0.5, vwap=10.90)
        self.m.step(ctx(b, 11.20, **accel_ctx))
        self.m.step(ctx(b + 1, 11.22, **accel_ctx))
        self.assertEqual(self.m.state, SignalState.ACCEL.value)

    def test_accel_never_degrades_on_pullback(self):
        """核心回归：加速后回踩不得退回低级状态（修掉旧引擎"加速事实被抹掉"）。"""
        b = _hold(self.m, 0)
        accel_ctx = dict(pct=6.0, s3=1.0, s12=0.5, vwap=10.90)
        self.m.step(ctx(b, 11.20, **accel_ctx))
        self.m.step(ctx(b + 1, 11.22, **accel_ctx))
        self.assertEqual(self.m.state, SignalState.ACCEL.value)

        # 回踩：涨幅掉到 3%，斜率转负，结构回到震荡——旧引擎会判"蓄势"
        pull = dict(pct=3.0, s3=-2.0, s12=0.1, struct=Structure.RANGE, vwap=11.0)
        for i in range(2, 12):
            self.m.step(ctx(b + i, 11.00, **pull))
        self.assertEqual(self.m.state, SignalState.ACCEL.value)
        self.assertTrue(self.led.is_open("600000"))

    def test_monotonic_guard_blocks_direct_downgrade(self):
        """守卫级测试：直接把 ACCEL 降级到 DORMANT 必须被拒绝并留诊断。"""
        self.m.state = SignalState.ACCEL.value
        ev = self.m._apply(ctx(5, 11.0), SignalState.DORMANT.value, "TEST", "test")
        self.assertIsNone(ev)
        self.assertEqual(self.m.state, SignalState.ACCEL.value)
        self.assertTrue(any(d["type"] == "MONOTONIC_BLOCK" for d in self.m.diagnostics()))

    def test_stop_loss_exits_and_reason_preserved(self):
        b = _hold(self.m, 0)
        # 进场时 stop = max(defend 10.5, vwap 11.05*0.985=10.884) = 10.884
        ev = self.m.step(ctx(b, 10.80, pct=-1.0, struct=Structure.LH_LL))
        self.assertIsNotNone(ev)
        self.assertEqual(self.m.state, SignalState.EXITING.value)
        self.assertEqual(ev.reason_code, "STOP_LOSS")

        ev2 = self.m.step(ctx(b + 1, 10.80, pct=-1.0, struct=Structure.LH_LL))
        self.assertEqual(self.m.state, SignalState.EXITED.value)
        closed = self.led.closed_positions()
        self.assertEqual(len(closed), 1)
        # 退场原因必须透传，不能被 EXIT_DONE 覆盖
        self.assertEqual(closed[0].exit_reason, "STOP_LOSS")
        self.assertLess(closed[0].realized_pct, 0.0)

    def test_exit_completes_in_one_bar(self):
        """EXITING 不得自我循环，下一根必须收敛到 EXITED。"""
        b = _hold(self.m, 0)
        self.m.step(ctx(b, 10.80, pct=-1.0))
        self.assertEqual(self.m.state, SignalState.EXITING.value)
        self.m.step(ctx(b + 1, 10.80, pct=-1.0))
        self.assertEqual(self.m.state, SignalState.EXITED.value)
        self.assertFalse(self.led.is_open("600000"))


class ConfirmFilterTest(unittest.TestCase):
    def test_single_bar_false_breakout_rejected(self):
        led = PositionLedger(8)
        m = SignalStateMachine("600000", _params(), led)
        b = _arm(m, 0)
        # 一根假突破后立刻回落
        m.step(ctx(b, 11.05))
        m.step(ctx(b + 1, 10.95))
        m.step(ctx(b + 2, 11.05))
        m.step(ctx(b + 3, 10.95))
        self.assertEqual(m.state, SignalState.ARMED.value)
        self.assertFalse(led.is_open("600000"))


class TimeStopTest(unittest.TestCase):
    def test_time_stop_when_no_progress(self):
        led = PositionLedger(8)
        m = SignalStateMachine("600000", _params(max_hold_bars=5, min_progress_pct=1.0), led)
        b = _hold(m, 0)
        entry_bar = m.position.entry_bar
        # 横盘：进场后最高价等于进场价，MFE≈0
        i = 0
        while m.state not in (SignalState.EXITING.value, SignalState.EXITED.value) and i < 20:
            m.step(ctx(b + i, 11.06, pct=3.1, high=11.06, low=11.05, vwap=10.90))
            i += 1
        self.assertIn(m.state, (SignalState.EXITING.value, SignalState.EXITED.value))
        # 时间止损必须在持有超预算后触发
        self.assertGreaterEqual(m.position.holding_bars if m.position else (b + i - 1 - entry_bar), 5)
        # 推进到 EXITED 验证原因
        m.step(ctx(b + i + 1, 11.06, pct=3.1, high=11.06, low=11.05, vwap=10.90))
        self.assertEqual(m.state, SignalState.EXITED.value)
        self.assertEqual(led.closed_positions()[-1].exit_reason, "TIME_STOP")


class UntradableTest(unittest.TestCase):
    def test_one_word_limit_board_no_position(self):
        led = PositionLedger(8)
        m = SignalStateMachine("600000", _params(), led)
        b = _arm(m, 0)
        # 一字板：high==low==close 且不可交易
        for i in range(4):
            m.step(ctx(b + i, 11.06, high=11.06, low=11.06, pct=10.0,
                       tradable=False, why="一字涨停不可执行"))
        self.assertEqual(m.state, SignalState.ARMED.value)
        self.assertFalse(led.is_open("600000"))


class LedgerTest(unittest.TestCase):
    def test_mfe_uses_entry_bar_high(self):
        led = PositionLedger(8)
        pos = led.open("600000", ctx(0, 10.0, high=10.3, low=9.9), "TEST")
        self.assertIsNotNone(pos)
        self.assertAlmostEqual(pos.mfe_pct, 3.0, places=2)
        self.assertAlmostEqual(pos.mae_pct, -1.0, places=2)

    def test_mfe_not_polluted_by_pre_entry_high(self):
        """进场前的高点不得计入 MFE：账本从开仓那一刻起算。"""
        led = PositionLedger(8)
        pos = led.open("600000", ctx(0, 10.0, high=10.1, low=9.9), "TEST")
        led.mark(ctx(1, 10.2, high=10.4, low=10.0))
        self.assertAlmostEqual(pos.mfe_pct, 4.0, places=2)   # (10.4-10)/10

    def test_ledger_full_blocks_new_position(self):
        led = PositionLedger(1)
        m1 = SignalStateMachine("600000", _params(max_positions=1), led)
        b = _hold(m1, 0)
        self.assertTrue(led.is_open("600000"))

        m2 = SignalStateMachine("000001", _params(max_positions=1), led)
        # 注意：ctx.code 必须与 machine.code 一致，否则会被 CODE_MISMATCH 守卫拒绝
        m2.step(ctx(0, 10.90, code="000001"))
        m2.step(ctx(1, 10.90, code="000001"))
        self.assertEqual(m2.state, SignalState.ARMED.value)
        m2.step(ctx(2, 11.05, pct=3.0, code="000001"))
        m2.step(ctx(3, 11.06, pct=3.1, code="000001"))
        self.assertEqual(m2.state, SignalState.ARMED.value)   # 账本满，不进场
        self.assertFalse(led.is_open("000001"))
        self.assertTrue(any(d["type"] == "LEDGER_FULL" for d in m2.diagnostics()))

    def test_summary(self):
        led = PositionLedger(8)
        led.open("600000", ctx(0, 10.0), "T")
        led.close("600000", ctx(5, 11.0), "TRAIL_STOP")
        s = led.summary()
        self.assertEqual(s["n_open"], 0)
        self.assertEqual(s["n_closed"], 1)
        self.assertEqual(s["win_rate"], 100.0)


class WeakStrongTest(unittest.TestCase):
    def test_ranker_prefers_fast_mfe_growth(self):
        led = PositionLedger(8)
        a = led.open("600000", ctx(0, 10.0, code="600000"), "T")
        a.mfe_pct = 6.0
        a.last_bar = 10          # 10 bar 涨 6% -> 0.6/bar
        b = led.open("000001", ctx(0, 20.0, code="000001"), "T")
        b.mfe_pct = 2.0
        b.last_bar = 40          # 40 bar 涨 2% -> 0.05/bar
        ranked = WeakStrongRanker.rank([a, b])
        self.assertEqual(ranked[0][0], "600000")
        self.assertGreater(ranked[0][1], ranked[1][1])

    def test_suggest_swap_returns_weakest(self):
        led = PositionLedger(8)
        a = led.open("600000", ctx(0, 10.0, code="600000"), "T")
        a.mfe_pct = 6.0
        a.last_bar = 10
        b = led.open("000001", ctx(0, 20.0, code="000001"), "T")
        b.mfe_pct = 0.5
        b.last_bar = 40
        weakest = WeakStrongRanker.suggest_swap([a, b], incoming_score=99.0)
        self.assertEqual(weakest, "000001")


class IdempotentStepTest(unittest.TestCase):
    def test_same_bar_repeat_does_not_retrigger(self):
        led = PositionLedger(8)
        m = SignalStateMachine("600000", _params(), led)
        b = _arm(m, 0)
        m.step(ctx(b, 11.05, pct=3.0))
        m.step(ctx(b + 1, 11.06, pct=3.1))     # 第 2 根确认 -> TRIGGERED
        self.assertEqual(m.state, SignalState.TRIGGERED.value)
        n_events = len(m.events(limit=100))
        # 同一 bar 反复调用不得产生新事件
        for _ in range(5):
            m.step(ctx(b + 1, 11.06, pct=3.1))
        self.assertEqual(m.state, SignalState.TRIGGERED.value)
        self.assertEqual(len(m.events(limit=100)), n_events)


if __name__ == "__main__":
    unittest.main(verbosity=2)
