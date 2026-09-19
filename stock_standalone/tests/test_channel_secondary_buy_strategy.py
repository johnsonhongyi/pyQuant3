# -*- coding: utf-8 -*-
"""
tests/test_channel_secondary_buy_strategy.py
---------------------------------------------
长期通道后企稳与底部结构次级买点策略 P0 最小可跑闭环自动化测试
覆盖：
1. 状态机与纯函数形态识别 (通道减速、首阳试盘不买、回踩抬高、次级确认、破位失效)
2. 规范化 signal_level (S0~S5) 与 quality_grade (A/S/SS)
3. 不可变 IPOTradePlan 数据结构与 4 大 Tag 正交隔离
4. IPOTradingCenter 生成 TradePlan 与指令动作收敛 (BUY_SCOUT / BUY_CONFIRM / EXIT_ALL，自动轮动拦截)
5. ProactiveExitEngine 结构止损 (higher_low_stop) 与通道中轴保本推移联动
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

# 确保路径可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ats.strategy.channel_secondary_buy_strategy import (
    SecondaryBuyStage,
    IPOTradePlan,
    evaluate_channel_secondary_buy,
    TAG_CHANNEL_SECONDARY_BUY,
    TAG_SUBNEW_PULLBACK_REENTRY,
    TAG_IPO_VWAP_STABLE,
    TAG_IPO_BID_SURGE,
)
from ats.strategy.ipo_trading_center import (
    IPOTradingCenter,
    IPOOrderDirective,
    IPOTradingPosition,
)
from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal
from ats.proactive_exit_engine import ProactiveExitEngine, PositionWatchItem


class TestChannelSecondaryBuyStrategy(unittest.TestCase):
    """长期通道次级买点核心策略与状态机测试"""

    def _build_dummy_kline(self, prices, vols=None):
        """构造简易测试 K 线数据"""
        n = len(prices)
        if vols is None:
            vols = [1000.0] * n
        highs = [p * 1.01 for p in prices]
        lows = [p * 0.99 for p in prices]
        opens = [p * 0.995 for p in prices]
        df = pd.DataFrame({
            "close": prices,
            "high": highs,
            "low": lows,
            "open": opens,
            "vol": vols,
            "time": [f"2026-09-19 {i:02d}:00" for i in range(n)]
        })
        return df

    def test_01_descending_and_breakout_and_secondary_buy(self):
        """测试标准下降通道企稳 -> 首阳试盘 -> 缩量回踩抬高 -> 次级买点确认全流转"""
        # 1. 长期下降走平 (100 -> 80)
        p_desc = np.linspace(100.0, 80.0, 30).tolist()
        # 2. 底部平底箱体 (80 附近企稳)
        p_base = [80.0, 80.5, 79.8, 80.2, 80.1]
        # 3. 首次试盘突破 (拉到 85.0)
        p_first_break = [82.0, 85.0]
        # 4. 缩量回踩，守住 Higher Low (回落到 82.0，高于 79.8)
        p_pullback = [84.0, 83.0, 82.2, 82.0]
        # 5. 次级放量突破确认 (放量拉起到 85.5，突破次回踩小箱体高点)
        p_secondary = [83.0, 85.5]

        all_prices = p_desc + p_base + p_first_break + p_pullback + p_secondary
        vols = [1000.0] * len(all_prices)
        # 首次突破放量
        vols[len(p_desc) + len(p_base) + 1] = 3000.0
        # 回踩缩量
        for idx in range(len(p_desc) + len(p_base) + 2, len(p_desc) + len(p_base) + 2 + len(p_pullback)):
            vols[idx] = 400.0
        # 次级突破再次放量
        vols[-1] = 2000.0

        df_60m = self._build_dummy_kline(all_prices, vols)
        res = evaluate_channel_secondary_buy(df_60m, code="688826", name="测试标的")

        # 校验状态机与评级
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["stage"], SecondaryBuyStage.SECONDARY_BUY)
        self.assertEqual(res["signal_level"], "S4")
        self.assertIn(res["quality_grade"], ("A", "S", "SS"))
        self.assertGreater(res["higher_low"], res["base_low"])
        self.assertIsNotNone(res["trade_plan"])
        self.assertIsInstance(res["trade_plan"], IPOTradePlan)
        self.assertEqual(res["trade_plan"].code, "688826")
        self.assertEqual(res["trade_plan"].strategy_tag, TAG_CHANNEL_SECONDARY_BUY)
        self.assertGreater(res["trade_plan"].higher_low_stop, 0.0)

    def test_02_first_breakout_do_not_chase_buy(self):
        """测试操盘手实战铁律：首次大阳试盘冲高【严禁追高开仓】，只标记观察"""
        p_desc = np.linspace(50.0, 30.0, 25).tolist()
        p_base = [30.0, 30.1, 29.9, 30.0]
        p_break = [33.0] # 刚突破第一根大阳
        df_60m = self._build_dummy_kline(p_desc + p_base + p_break)
        res = evaluate_channel_secondary_buy(df_60m, code="300058", name="蓝色光标")

        self.assertEqual(res["stage"], SecondaryBuyStage.FIRST_BREAKOUT)
        self.assertEqual(res["signal_level"], "S2")
        self.assertFalse(res["is_valid"])
        self.assertIn("严禁冲高追买", res["reason"])

    def test_03_breakdown_base_low_invalidated(self):
        """测试破位跌破 Base Low 立即失效淘汰"""
        p_desc = np.linspace(40.0, 25.0, 25).tolist()
        p_base = [25.0, 25.2, 24.8, 25.0]
        p_breakdown = [24.0, 23.5] # 跌破 24.8 最低点
        df_60m = self._build_dummy_kline(p_desc + p_base + p_breakdown)
        res = evaluate_channel_secondary_buy(df_60m, code="688001", name="破位标的")

        self.assertEqual(res["stage"], SecondaryBuyStage.INVALIDATED)
        self.assertEqual(res["signal_level"], "S0")
        self.assertFalse(res["is_valid"])
        self.assertIn("跌破底部箱体最低点", res["reason"])


class TestIPOTradingCenterTradePlanIntegration(unittest.TestCase):
    """交易决策中心 TradePlan 规范与指令收敛闭环测试"""

    def setUp(self):
        self.center = IPOTradingCenter(total_capital=1000000.0, auto_load_ledger=False)

    def test_04_create_trade_plan_from_signal(self):
        """测试从各类前置信号生成标准不可变 TradePlan 且 Tag 正交分离"""
        # 1. 通道突破标的
        sig_swing = VWAPDetectorSignal(
            code="688826", name="实战次新", price=82.50, vwap=80.0,
            is_swing_channel_breakout=True, horse_race_score=92.0, horse_race_rank=1,
            stop_loss_price=81.0, multi_day_base_support=78.5
        )
        plan_swing = self.center.create_trade_plan_from_signal(sig_swing)
        self.assertIsNotNone(plan_swing)
        self.assertEqual(plan_swing.strategy_tag, TAG_CHANNEL_SECONDARY_BUY)
        self.assertEqual(plan_swing.signal_level, "S4")
        self.assertEqual(plan_swing.quality_grade, "SS")
        self.assertEqual(plan_swing.higher_low_stop, 81.0)
        self.assertEqual(plan_swing.base_low_invalid, 78.5)

        # 2. 首发首日标的
        sig_ipo = VWAPDetectorSignal(
            code="301666", name="首发新股", price=35.0, vwap=34.8,
            is_ipo_first_day=True, signal_type="IPO_FIRST_BUY",
            launch_time_str="09:32", launch_slope_deg=50.0, horse_race_rank=1
        )
        plan_ipo = self.center.create_trade_plan_from_signal(sig_ipo)
        self.assertIsNotNone(plan_ipo)
        self.assertEqual(plan_ipo.strategy_tag, TAG_IPO_BID_SURGE)
        self.assertEqual(plan_ipo.signal_level, "S5")
        self.assertEqual(plan_ipo.quality_grade, "SS")

    def test_05_auto_execute_blocks_full_rotation_swap(self):
        """测试操盘手实战修正：FULL_ROTATION_SWAP 仅作战术建议展示，严禁自动执行"""
        self.center.auto_follow_trading = True
        swap_dir = IPOOrderDirective(
            action="FULL_ROTATION_SWAP",
            code="688826",
            name="新龙头",
            price=80.0,
            shares=1000,
            target_swap_code="600000",
            target_swap_name="老股票"
        )
        # 触发自动撮合
        self.center._auto_execute_if_enabled([swap_dir])
        # 验证：新股票未被自动建仓！
        self.assertNotIn("688826", self.center._positions)

    def test_06_record_order_execution_scout_and_exit(self):
        """测试 BUY_SCOUT 建仓与 EXIT_ALL 平仓全生命周期流转"""
        sig = VWAPDetectorSignal(
            code="688826", name="测试标的", price=100.0, vwap=98.0,
            has_bottom_base=True, stop_loss_price=97.0, base_support_level=95.0
        )
        plan = self.center.create_trade_plan_from_signal(sig)
        
        buy_dir = IPOOrderDirective(
            action="BUY_SCOUT",
            code="688826",
            name="测试标的",
            price=100.0,
            shares=1000,
            size_pct=30.0,
            signal_level="S4",
            quality_grade="S",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            trade_plan=plan
        )
        self.center.record_order_execution(buy_dir)
        pos = self.center.get_position("688826")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.shares, 1000)
        self.assertEqual(pos.cost_price, 100.0)
        self.assertEqual(pos.strategy_tag, TAG_CHANNEL_SECONDARY_BUY)
        self.assertEqual(pos.signal_level, "S4")

        # 触发 EXIT_ALL 平仓
        exit_dir = IPOOrderDirective(
            action="EXIT_ALL",
            code="688826",
            name="测试标的",
            price=105.0,
            shares=1000,
            reason="到达通道第一目标位主动兑现"
        )
        self.center.record_order_execution(exit_dir)
        self.assertEqual(pos.shares, 0)
        self.assertEqual(pos.status, "CLOSED")
        self.assertEqual(pos.realized_pnl_pct, 5.0)


class TestProactiveExitLinkage(unittest.TestCase):
    """ProactiveExitEngine 挂接 TradePlan 结构防守联动测试"""

    def setUp(self):
        self.exit_engine = ProactiveExitEngine()

    def test_07_higher_low_stop_triggers_exit_all(self):
        """测试跌破 TradePlan 中的 higher_low_stop 时触发清仓止损"""
        pos = self.exit_engine.register_position(
            code="688826",
            entry_price=80.0,
            shares=1000,
            entry_time=1000.0
        )
        plan = IPOTradePlan(
            plan_id="TP_TEST",
            code="688826",
            name="测试",
            higher_low_stop=78.5, # 次低点防守线
            base_low_invalid=76.0,
            target_1_channel_mid=86.0
        )

        # 第一次评估：现价 79.5 (守在 78.5 之上，正常持有)
        action_normal = self.exit_engine.evaluate_tick(
            code="688826",
            price=79.5,
            vwap_today=79.8,
            volume=500,
            current_time=1005.0,
            extra_ctx={"trade_plan": plan}
        )
        self.assertIsNone(action_normal)
        self.assertTrue(pos.is_reversal_protected)
        self.assertEqual(pos.higher_low_stop, 78.5)

        # 第二次评估：突发跳水跌破 78.5 (现价 77.5)
        action_exit = self.exit_engine.evaluate_tick(
            code="688826",
            price=77.5,
            vwap_today=79.0,
            volume=800,
            current_time=1010.0,
            extra_ctx={"trade_plan": plan}
        )
        self.assertIsNotNone(action_exit)
        self.assertEqual(action_exit.action_type, "EXIT_ALL")
        self.assertEqual(action_exit.rule_id, "exit_higher_low_broken")
        self.assertIn("跌破底抬高关键防守线", action_exit.reason)

    def test_08_target_1_trailing_stop_protection(self):
        """测试价格触及通道中轴 Target 1 后自动将防守线保本推移"""
        pos = self.exit_engine.register_position(
            code="688826",
            entry_price=80.0,
            shares=1000,
            entry_time=1000.0
        )
        plan = IPOTradePlan(
            plan_id="TP_TEST2",
            code="688826",
            name="测试",
            higher_low_stop=78.0,
            target_1_channel_mid=86.0
        )
        # 价格冲到 86.5 (达到第一目标位)
        self.exit_engine.evaluate_tick(
            code="688826",
            price=86.5,
            vwap_today=85.0,
            volume=2000,
            current_time=1020.0,
            extra_ctx={"trade_plan": plan}
        )
        # 验证防守线已被自动上移至成本线之上 (保本锁定)
        self.assertGreater(pos.higher_low_stop, 80.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
