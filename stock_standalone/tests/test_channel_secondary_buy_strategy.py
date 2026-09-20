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
import tempfile
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
from ats.proactive_exit_engine import ProactiveExitEngine, PositionWatchItem, ExitAction


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

        # 隔日触发 EXIT_ALL 平仓；当天新仓由 T+1 硬锁保护。
        pos.entry_date = "2026-09-19"
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

    def test_09_secondary_buy_decision_scout_and_confirm_orders(self):
        """测试 09: 次级买点 S4 生成 BUY_SCOUT 试探仓指令，S5 生成 BUY_CONFIRM 确认仓指令，且仓位受控不得满仓"""
        # 1. 构造 S4 信号与标准不可变 TradePlan
        plan_s4 = IPOTradePlan(
            plan_id="TP_688826_S4",
            code="688826",
            name="实战标的",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            signal_level="S4",
            quality_grade="SS",
            trigger_price=80.0,
            buy_zone_min=79.0,
            buy_zone_max=81.0,
            higher_low_stop=77.5,
            base_low_invalid=75.0,
            position_pct=25.0,
            suggested_action="BUY_SCOUT"
        )
        sig_s4 = VWAPDetectorSignal(
            code="688826",
            name="实战标的",
            price=80.0,
            vwap=79.5,
            is_above_vwap=True,
            signal_type="SECONDARY_BUY",
            channel_stage=SecondaryBuyStage.SECONDARY_BUY,
            quality_grade="SS",
            signal_level="S4",
            trade_plan=plan_s4
        )

        self.center.submit_stock_perception_report(sig_s4)
        directives_s4 = self.center.evaluate_fleet_and_generate_orders()

        # 校验生成的买入指令
        buy_dirs_s4 = [d for d in directives_s4 if d.code == "688826" and d.action in ("BUY_SCOUT", "BUY_CONFIRM", "BUY")]
        self.assertEqual(len(buy_dirs_s4), 1)
        dir_s4 = buy_dirs_s4[0]
        self.assertEqual(dir_s4.action, "BUY_SCOUT")
        self.assertEqual(dir_s4.signal_level, "S4")
        self.assertEqual(dir_s4.quality_grade, "SS")
        self.assertEqual(dir_s4.strategy_tag, TAG_CHANNEL_SECONDARY_BUY)
        self.assertIs(dir_s4.trade_plan, plan_s4)
        self.assertEqual(dir_s4.size_pct, 25.0)  # 受 TradePlan 约束
        self.assertGreater(dir_s4.shares, 0)

        # 2. 构造 S5 信号，校验生成 BUY_CONFIRM 且仓位受限不直接满仓
        self.center._positions.clear()
        self.center._reports_cache.clear()
        self.center._emitted_plan_ids.clear()
        self.center.set_trading_mode("ROTATION_FULL_CAPITAL")  # 即使在全仓轮动模式下

        plan_s5 = IPOTradePlan(
            plan_id="TP_300058_S5",
            code="300058",
            name="确认标的",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            signal_level="S5",
            quality_grade="S",
            trigger_price=30.0,
            buy_zone_min=29.5,
            buy_zone_max=30.5,
            higher_low_stop=28.8,
            base_low_invalid=27.5,
            position_pct=30.0,
            suggested_action="BUY_CONFIRM"
        )
        sig_s5 = VWAPDetectorSignal(
            code="300058",
            name="确认标的",
            price=30.0,
            vwap=30.2,
            is_above_vwap=False,
            signal_type="SECONDARY_BUY",
            channel_stage=SecondaryBuyStage.SECONDARY_BUY,
            quality_grade="S",
            signal_level="S5",
            trade_plan=plan_s5
        )

        self.center.submit_stock_perception_report(sig_s5)
        directives_s5 = self.center.evaluate_fleet_and_generate_orders()

        buy_dirs_s5 = [d for d in directives_s5 if d.code == "300058"]
        self.assertEqual(len(buy_dirs_s5), 1)
        dir_s5 = buy_dirs_s5[0]
        self.assertEqual(dir_s5.action, "BUY_CONFIRM")
        self.assertEqual(dir_s5.signal_level, "S5")
        self.assertLessEqual(dir_s5.size_pct, 35.0)  # 严格受控，绝不给 100% 满仓！
        self.assertIs(dir_s5.trade_plan, plan_s5)

    def test_10_secondary_buy_rejection_conditions(self):
        """测试 10: 超过 buy_zone_max、缺失 TradePlan、低于 S4 时明确拒绝生成指令"""
        # 条件 A: 现价 82.5 超过买入区上沿 buy_zone_max 81.0 -> 拒绝开仓追高
        plan_over = IPOTradePlan(
            plan_id="TP_OVER",
            code="688826",
            name="超买标的",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            signal_level="S4",
            trigger_price=80.0,
            buy_zone_min=79.0,
            buy_zone_max=81.0,
            higher_low_stop=77.5,
            base_low_invalid=75.0
        )
        sig_over = VWAPDetectorSignal(
            code="688826",
            name="超买标的",
            price=82.5,  # 82.5 > 81.0 超过买入上限
            vwap=80.0,
            signal_type="SECONDARY_BUY",
            channel_stage=SecondaryBuyStage.SECONDARY_BUY,
            trade_plan=plan_over
        )
        self.center.submit_stock_perception_report(sig_over)
        dirs_over = self.center.evaluate_fleet_and_generate_orders()
        buy_over = [d for d in dirs_over if d.code == "688826" and d.action in ("BUY", "BUY_SCOUT", "BUY_CONFIRM")]
        self.assertEqual(len(buy_over), 0)

        # 条件 B: 缺失 TradePlan (trade_plan is None) -> 拒绝
        self.center._reports_cache.clear()
        sig_noplan = VWAPDetectorSignal(
            code="688827",
            name="无计划标的",
            price=50.0,
            vwap=50.0,
            signal_type="SECONDARY_BUY",
            channel_stage=SecondaryBuyStage.SECONDARY_BUY,
            trade_plan=None  # 缺失 TradePlan
        )
        self.center.submit_stock_perception_report(sig_noplan)
        dirs_noplan = self.center.evaluate_fleet_and_generate_orders()
        buy_noplan = [d for d in dirs_noplan if d.code == "688827" and d.action in ("BUY", "BUY_SCOUT", "BUY_CONFIRM")]
        self.assertEqual(len(buy_noplan), 0)

        # 条件 C: 等级低于 S4 (如 S3/S2/S0) -> 拒绝
        self.center._reports_cache.clear()
        plan_s3 = IPOTradePlan(
            plan_id="TP_S3",
            code="688828",
            name="回踩中标的",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            signal_level="S3",  # 低于 S4 门槛
            trigger_price=40.0,
            buy_zone_min=39.0,
            buy_zone_max=41.0,
            higher_low_stop=38.0
        )
        sig_s3 = VWAPDetectorSignal(
            code="688828",
            name="回踩中标的",
            price=40.0,
            vwap=40.0,
            signal_type="SECONDARY_BUY",
            channel_stage=SecondaryBuyStage.SECONDARY_BUY,
            signal_level="S3",
            trade_plan=plan_s3
        )
        self.center.submit_stock_perception_report(sig_s3)
        dirs_s3 = self.center.evaluate_fleet_and_generate_orders()
        buy_s3 = [d for d in dirs_s3 if d.code == "688828" and d.action in ("BUY", "BUY_SCOUT", "BUY_CONFIRM")]
        self.assertEqual(len(buy_s3), 0)

    def test_11_secondary_buy_not_misjudged_as_follower_or_stop_loss(self):
        """测试 11: 全局仲裁独立战术角色，不被普通 FOLLOWER 或 VWAP 破位分支误杀"""
        self.center._reports_cache.clear()
        # 1. 现价在 VWAP 下方较多 (-2.5%) 的次级买点标的，止损位仍安全守在 higher_low_stop 之上
        plan_deep = IPOTradePlan(
            plan_id="TP_DEEP",
            code="688826",
            name="底抬高标的",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            signal_level="S4",
            quality_grade="S",
            trigger_price=78.0,
            buy_zone_min=77.0,
            buy_zone_max=79.0,
            higher_low_stop=75.5,
            base_low_invalid=73.0,
            position_pct=20.0
        )
        sig_deep = VWAPDetectorSignal(
            code="688826",
            name="底抬高标的",
            price=78.0,
            vwap=80.0,
            vwap_diff_pct=-2.5,  # 偏离 VWAP -2.5% (若按普通分支会被当成 STOP_LOSS 误杀)
            is_above_vwap=False,
            signal_type="SECONDARY_BUY",
            channel_stage=SecondaryBuyStage.SECONDARY_BUY,
            quality_grade="S",
            signal_level="S4",
            stop_loss_price=75.5,
            trade_plan=plan_deep
        )

        # 2. 同时池中存在更强的领头羊 (动能 95 分) 和梯队前锋，使次级买点排名在第 4 名之后
        sig_leader = VWAPDetectorSignal(
            code="600001", name="大龙头", price=10.0, vwap=9.8,
            is_above_vwap=True, horse_race_score=95.0, horse_race_rank=1,
            signal_type="IPO_FIRST_BUY", is_ipo_first_day=True, launch_time_str="09:31"
        )
        sig_vanguard1 = VWAPDetectorSignal(
            code="600002", name="前锋一", price=15.0, vwap=14.5,
            is_above_vwap=True, horse_race_score=85.0, horse_race_rank=2
        )
        sig_vanguard2 = VWAPDetectorSignal(
            code="600003", name="前锋二", price=20.0, vwap=19.5,
            is_above_vwap=True, horse_race_score=80.0, horse_race_rank=3
        )
        sig_deep.horse_race_score = 75.0
        sig_deep.horse_race_rank = 4

        self.center.submit_stock_perception_report(sig_leader)
        self.center.submit_stock_perception_report(sig_vanguard1)
        self.center.submit_stock_perception_report(sig_vanguard2)
        self.center.submit_stock_perception_report(sig_deep)

        directives = self.center.evaluate_fleet_and_generate_orders()

        # 核心断言 1: 全局仲裁确认为 SECONDARY_BUY 独立角色，绝不被判为 STOP_LOSS 或 FOLLOWER
        self.assertEqual(sig_deep.global_fleet_role, "SECONDARY_BUY")
        self.assertIn("次级买点", sig_deep.global_arbitration_desc)
        self.assertNotIn("买错立斩", sig_deep.global_arbitration_desc)
        self.assertNotIn("山外有山·观望", sig_deep.global_arbitration_desc)

        # 核心断言 2: 虽然排名第 4 且在 VWAP 之下，但次级买点独立战术角色允许生成受控买入指令
        sec_dirs = [d for d in directives if d.code == "688826" and d.action == "BUY_SCOUT"]
        self.assertEqual(len(sec_dirs), 1)

    def test_12_secondary_buy_idempotent_refresh_loop(self):
        """测试 12: 刷新循环幂等守卫，同一 plan_id 不重复生成买入指令"""
        self.center._reports_cache.clear()
        self.center._emitted_plan_ids.clear()

        plan = IPOTradePlan(
            plan_id="TP_IDEMPOTENT_001",
            code="688826",
            name="幂等标的",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            signal_level="S4",
            quality_grade="SS",
            trigger_price=50.0,
            buy_zone_min=49.0,
            buy_zone_max=51.0,
            higher_low_stop=47.5,
            base_low_invalid=45.0,
            position_pct=20.0
        )
        sig = VWAPDetectorSignal(
            code="688826",
            name="幂等标的",
            price=50.0,
            vwap=49.8,
            is_above_vwap=True,
            signal_type="SECONDARY_BUY",
            channel_stage=SecondaryBuyStage.SECONDARY_BUY,
            quality_grade="SS",
            signal_level="S4",
            trade_plan=plan
        )

        self.center.submit_stock_perception_report(sig)

        # 第一次评估：生成买入指令
        dirs_1 = self.center.evaluate_fleet_and_generate_orders()
        buy_1 = [d for d in dirs_1 if d.code == "688826" and d.action == "BUY_SCOUT"]
        self.assertEqual(len(buy_1), 1)
        self.assertIn("TP_IDEMPOTENT_001", self.center._emitted_plan_ids)

        # 第二次刷新循环评估 (同一 plan_id 未改变)：不得重复生成新的买入指令
        dirs_2 = self.center.evaluate_fleet_and_generate_orders()
        buy_2 = [d for d in dirs_2 if d.code == "688826" and d.action == "BUY_SCOUT"]
        self.assertEqual(len(buy_2), 0)


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


class TestTradingCenterProactiveExitWiring(unittest.TestCase):
    def setUp(self):
        self.exit_engine = ProactiveExitEngine()
        self.center = IPOTradingCenter(total_capital=100000.0, exit_engine=self.exit_engine)
        self.plan = IPOTradePlan(
            plan_id="TP_EXIT_001", code="688826", name="碳脉冲",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY, signal_level="S4",
            quality_grade="S", higher_low_stop=78.0,
            target_1_channel_mid=86.0,
        )
        self.buy = IPOOrderDirective(
            action="BUY_SCOUT", code="688826", name="碳脉冲",
            price=80.0, shares=1000, size_pct=20.0,
            timestamp=1000.0, trade_plan=self.plan,
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
        )

    def test_13_buy_registers_exit_watch_and_trade_plan(self):
        self.assertTrue(self.center.record_order_execution(self.buy))
        watch = self.exit_engine.get_position("688826")
        self.assertIsNotNone(watch)
        self.assertEqual(watch.shares, 1000)
        self.assertEqual(watch.higher_low_stop, 78.0)
        self.assertIs(self.center.get_position("688826").trade_plan, self.plan)

    def test_14_t1_blocks_normal_reduce_at_generation_and_execution(self):
        self.center.record_order_execution(self.buy)
        self.exit_engine.evaluate_tick = lambda **kwargs: ExitAction(
            code="688826", rule_id="exit_time_decay", rule_name="时间衰减",
            layer=1, action_type="REDUCE_HALF", size_pct=0.5,
            trigger_price=79.5, reason="normal reduce", timestamp=1100.0,
        )
        self.assertIsNone(self.center.evaluate_position_exit("688826", 79.5, 80.0, 100.0))
        self.assertEqual(self.exit_engine.get_position("688826").reduce_count, 0)
        direct = IPOOrderDirective(
            action="REDUCE_HALF", code="688826", name="碳脉冲",
            price=79.5, shares=500, exit_rule_id="exit_time_decay",
        )
        self.assertFalse(self.center.record_order_execution(direct))
        self.assertEqual(self.center.get_position("688826").shares, 1000)

    def test_15_catastrophic_exit_bypasses_t1_and_archives_plan(self):
        self.center.record_order_execution(self.buy)
        self.exit_engine.evaluate_tick = lambda **kwargs: ExitAction(
            code="688826", rule_id="exit_higher_low_broken", rule_name="结构破坏",
            layer=8, action_type="EXIT_ALL", size_pct=1.0,
            trigger_price=77.0, reason="hard stop", timestamp=1100.0,
        )
        directive = self.center.evaluate_position_exit("688826", 77.0, 78.0, 500.0)
        self.assertIsNotNone(directive)
        self.assertTrue(directive.bypass_t1_lock)
        self.assertTrue(self.center.record_order_execution(directive))
        self.assertEqual(self.center.get_position("688826").shares, 0)
        closed = self.center._closed_positions[0]
        self.assertEqual(closed.shares, 1000)
        self.assertEqual(closed.trade_plan, self.plan)
        self.assertEqual(closed.exit_rule_id, "exit_higher_low_broken")
        self.assertEqual(closed.exit_rule_layer, 8)

    def test_16_t1_eligible_partial_reduce_updates_remaining_shares(self):
        self.center.record_order_execution(self.buy)
        pos = self.center.get_position("688826")
        pos.entry_date = "2026-09-19"
        directive = IPOOrderDirective(
            action="REDUCE_30", code="688826", name="碳脉冲",
            price=82.0, shares=300, exit_rule_id="exit_distribution",
            exit_rule_layer=4, trade_plan=self.plan,
        )
        self.assertTrue(self.center.record_order_execution(directive))
        self.assertEqual(pos.shares, 700)
        self.assertEqual(pos.available_shares, 700)
        self.assertEqual(self.exit_engine.get_position("688826").shares, 700)

    def test_17_t1_blocks_full_rotation_without_creating_target_position(self):
        self.center.record_order_execution(self.buy)
        rotation = IPOOrderDirective(
            action="FULL_ROTATION_SWAP", code="688999", name="新目标",
            price=50.0, target_swap_code="688826", target_swap_name="碳脉冲",
        )
        self.assertFalse(self.center.record_order_execution(rotation))
        self.assertEqual(self.center.get_position("688826").shares, 1000)
        self.assertIsNone(self.center.get_position("688999"))

    def test_18_ledger_reload_restores_trade_plan_and_exit_watch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger = os.path.join(tmp_dir, "ledger.json")
            center = IPOTradingCenter(
                total_capital=100000.0, ledger_file=ledger,
                exit_engine=ProactiveExitEngine(),
            )
            center.record_order_execution(self.buy)

            restored = IPOTradingCenter(
                total_capital=100000.0, auto_load_ledger=True,
                ledger_file=ledger, exit_engine=ProactiveExitEngine(),
            )
            pos = restored.get_position("688826")
            self.assertIsNotNone(pos)
            self.assertIsInstance(pos.trade_plan, IPOTradePlan)
            self.assertEqual(pos.trade_plan.plan_id, "TP_EXIT_001")
            watch = restored.exit_engine.get_position("688826")
            self.assertIsNotNone(watch)
            self.assertEqual(watch.shares, 1000)
            self.assertEqual(watch.higher_low_stop, 78.0)

    def test_19_t1_bypass_flag_requires_catastrophic_rule(self):
        self.center.record_order_execution(self.buy)
        forged = IPOOrderDirective(
            action="EXIT_ALL", code="688826", name="碳脉冲",
            price=79.0, shares=1000, bypass_t1_lock=True,
            exit_rule_id="exit_time_decay",
        )
        self.assertFalse(self.center.record_order_execution(forged))
        self.assertEqual(self.center.get_position("688826").shares, 1000)

    def test_20_pending_exit_prevents_repeated_engine_evaluation(self):
        self.center.record_order_execution(self.buy)
        pos = self.center.get_position("688826")
        pos.entry_date = "2026-09-19"
        calls = []

        def evaluate(**kwargs):
            calls.append(kwargs)
            return ExitAction(
                code="688826", rule_id="exit_time_decay", rule_name="时间衰减",
                layer=1, action_type="REDUCE_HALF", size_pct=0.5,
                trigger_price=79.5, reason="normal reduce", timestamp=1100.0,
            )

        self.exit_engine.evaluate_tick = evaluate
        self.assertIsNotNone(self.center.evaluate_position_exit("688826", 79.5, 80.0, 100.0))
        self.assertIsNone(self.center.evaluate_position_exit("688826", 79.4, 80.0, 100.0))
        self.assertEqual(len(calls), 1)

    def test_21_fleet_weight_budget_truncation_10_plus_10_limited_to_15(self):
        """【回归测试】常规买入多标的累加严格截断，10%+10%绝不突破15%潮汐上限"""
        from unittest.mock import patch
        from ats.strategy.ipo_market_sentiment_engine import MarketSentimentSnapshot

        center = IPOTradingCenter(total_capital=100000.0)
        # 构造3只符合条件的买入标的，常规跟风默认请求 10%
        sig1 = VWAPDetectorSignal(
            code="688001", name="标的1", price=10.0, vwap=9.8, is_above_vwap=True,
            pullback_no_touch=True, stop_loss_price=9.5, horse_race_rank=2, horse_race_score=80.0
        )
        sig2 = VWAPDetectorSignal(
            code="688002", name="标的2", price=10.0, vwap=9.8, is_above_vwap=True,
            pullback_no_touch=True, stop_loss_price=9.5, horse_race_rank=3, horse_race_score=75.0
        )
        sig3 = VWAPDetectorSignal(
            code="688003", name="标的3", price=10.0, vwap=9.8, is_above_vwap=True,
            pullback_no_touch=True, stop_loss_price=9.5, horse_race_rank=3, horse_race_score=70.0
        )
        center.submit_batch_reports([sig1, sig2, sig3])

        # 模拟 T6_ICE_DIVERGENCE 潮汐上限 15%
        context = MarketSentimentSnapshot(
            heat_stage="🔥 梯队升温", index_phase="温和放量",
            tide_state="T6_ICE_DIVERGENCE", tide_position_cap_pct=15.0,
            risk_mode="NORMAL", position_multiplier=1.0,
        ).finalize()

        with patch.object(center.sentiment_engine, "get_market_sentiment", return_value=context):
            orders = center.evaluate_fleet_and_generate_orders()

        buy_orders = [o for o in orders if o.action in ("BUY", "BUY_SCOUT", "BUY_CONFIRM")]
        # 标的1分配 10%，标的2截断为 15% - 10% = 5%，标的3无法分配
        self.assertEqual(len(buy_orders), 2)
        self.assertEqual(buy_orders[0].size_pct, 10.0)
        self.assertEqual(buy_orders[1].size_pct, 5.0)
        total_assigned = sum(o.size_pct for o in buy_orders)
        self.assertEqual(total_assigned, 15.0)
        self.assertLessEqual(total_assigned, 15.0)

    def test_22_full_rotation_swap_generation_under_t4_and_t5(self):
        """【回归测试】全仓轮动换马生成端：T4禁止生成换入，T5最多5%"""
        from unittest.mock import patch
        from ats.strategy.ipo_market_sentiment_engine import MarketSentimentSnapshot

        center = IPOTradingCenter(total_capital=100000.0)
        center.set_trading_mode("ROTATION_FULL_CAPITAL")
        # 老股票持仓
        center._positions["600001"] = IPOTradingPosition(
            code="600001", name="老滞涨", shares=1000, cost_price=10.0,
            current_price=10.0, entry_date="2026-09-19", status="HOLDING"
        )

        sig_leader = VWAPDetectorSignal(
            code="688999", name="超级龙头", price=50.0, vwap=48.0,
            is_above_vwap=True, signal_type="BREAKOUT", horse_race_rank=1,
            horse_race_score=95.0, launch_time_str="09:35", launch_slope_deg=45.0
        )
        sig_old = VWAPDetectorSignal(
            code="600001", name="老滞涨", price=10.0, vwap=10.5,
            is_above_vwap=False, signal_type="PULLBACK_BUY", horse_race_rank=8,
            horse_race_score=40.0, relative_to_leader_gap=55.0
        )
        center.submit_batch_reports([sig_leader, sig_old])

        # Case A: T4 状态 (panic accel, 0% cap) -> 绝不生成 FULL_ROTATION_SWAP
        ctx_t4 = MarketSentimentSnapshot(
            heat_stage="❄️ 冰点极寒", index_phase="绝望地量",
            tide_state="T4_PANIC_ACCEL", tide_position_cap_pct=0.0,
            risk_mode="BLOCK_NEW_BUYS", position_multiplier=0.0,
        ).finalize()
        with patch.object(center.sentiment_engine, "get_market_sentiment", return_value=ctx_t4):
            orders_t4 = center.evaluate_fleet_and_generate_orders()
        rotations_t4 = [o for o in orders_t4 if o.action == "FULL_ROTATION_SWAP"]
        self.assertEqual(len(rotations_t4), 0)

        # Case B: T5 状态 (ice, 5% cap) -> FULL_ROTATION_SWAP 受限最多 5%
        center._pending_directives.clear()
        ctx_t5 = MarketSentimentSnapshot(
            heat_stage="🌱 绝望孕育", index_phase="绝望地量",
            tide_state="T5_ICE", tide_position_cap_pct=5.0,
            risk_mode="NORMAL", position_multiplier=1.0,
        ).finalize()
        with patch.object(center.sentiment_engine, "get_market_sentiment", return_value=ctx_t5):
            orders_t5 = center.evaluate_fleet_and_generate_orders()
        rotations_t5 = [o for o in orders_t5 if o.action == "FULL_ROTATION_SWAP"]
        self.assertEqual(len(rotations_t5), 1)
        self.assertEqual(rotations_t5[0].size_pct, 5.0)
        self.assertEqual(rotations_t5[0].shares, 100)  # 100000 * 5% / 50 = 100 股

    def test_23_full_rotation_swap_execution_budget_enforcement_and_anti_bypass(self):
        """【回归测试】全仓轮动执行端：受限指令不扩大为100%，手工伪造100%指令被可信风控拦截"""
        from ats.strategy.ipo_market_sentiment_engine import MarketSentimentSnapshot

        center = IPOTradingCenter(total_capital=100000.0)
        center.set_trading_mode("ROTATION_FULL_CAPITAL")
        center._positions["600001"] = IPOTradingPosition(
            code="600001", name="老股票", shares=1000, cost_price=10.0,
            current_price=10.0, entry_date="2026-09-19", status="HOLDING"
        )
        center.available_cash = 90000.0  # 90% 闲置现金

        # Case A: 合法 5% 受限换马指令（携带有效时间戳并与新鲜快照同日关联），执行端仅买入 5% (100股 @ 50元 = 5000元)，绝不把剩余 9.5 万全额打入
        import time as pytime
        now_ts = pytime.time()
        snap_t5 = MarketSentimentSnapshot(
            tide_state="T5_ICE", tide_position_cap_pct=5.0,
            risk_mode="NORMAL", position_multiplier=1.0,
        ).finalize()
        snap_t5.generated_at = now_ts
        center._last_market_context = snap_t5

        dir_t5 = IPOOrderDirective(
            action="FULL_ROTATION_SWAP", code="688999", name="新龙头",
            price=50.0, shares=100, size_pct=5.0, timestamp=now_ts,
            target_swap_code="600001", target_swap_name="老股票"
        )

        self.assertTrue(center.record_order_execution(dir_t5))
        self.assertNotIn("600001", center._positions)
        self.assertIn("688999", center._positions)
        new_pos = center._positions["688999"]
        self.assertEqual(new_pos.shares, 100)  # 仅 5000 元，占 5%
        self.assertEqual(center.available_cash, 95000.0)  # 90000 + 10000(平老仓) - 5000(买新仓)

        # Case B: 攻击尝试：手工构造 size_pct=100% 指令试图穿透 T5 风控（带当前时间戳）
        center._positions["688999"].entry_date = "2026-09-19"  # 解除次日硬锁
        attack_dir = IPOOrderDirective(
            action="FULL_ROTATION_SWAP", code="688888", name="伪造标的",
            price=20.0, shares=5000, size_pct=100.0, timestamp=now_ts,
            target_swap_code="688999", target_swap_name="新龙头"
        )
        # 潮汐上限依然为 5%
        center._last_market_context = snap_t5

        self.assertTrue(center.record_order_execution(attack_dir))
        self.assertNotIn("688999", center._positions)
        self.assertIn("688888", center._positions)
        forged_pos = center._positions["688888"]
        # 执行端拦截伪造：强制截断至 5% 预算 (5000 元 / 20 元 = 200 股)，绝不买入 5000 股
        self.assertEqual(forged_pos.shares, 200)

        # Case B2: 攻击尝试：无时间戳指令（timestamp=0.0）试图利用系统新鲜快照扩大仓位
        center._positions["688888"].entry_date = "2026-09-19"
        # 构造零时间戳指令，size_pct=50%
        zero_ts_dir = IPOOrderDirective(
            action="FULL_ROTATION_SWAP", code="688889", name="零时间戳渗透",
            price=20.0, shares=2500, size_pct=50.0, timestamp=0.0,
            target_swap_code="688888", target_swap_name="伪造标的"
        )
        # 虽有 5% 的新鲜快照，但因无关联时间戳，快照不可信，只能降级为老仓位 (200股*20元=4000元，占4%)
        self.assertTrue(center.record_order_execution(zero_ts_dir))
        self.assertNotIn("688888", center._positions)
        self.assertIn("688889", center._positions)
        pos_zero_ts = center._positions["688889"]
        self.assertEqual(pos_zero_ts.shares, 200)  # 仅 4000 元，占 4%，未扩大仓位

        # Case C: 攻击尝试：在丢失快照时试图满仓扩大仓位，执行端按原持仓拒绝扩大
        center._positions["688889"].entry_date = "2026-09-19"
        center._last_market_context = None
        center.sentiment_engine._cached_snapshot = None
        bypass_dir = IPOOrderDirective(
            action="FULL_ROTATION_SWAP", code="688777", name="无快照渗透",
            price=10.0, shares=10000, size_pct=100.0,
            target_swap_code="688889", target_swap_name="零时间戳渗透"
        )
        self.assertTrue(center.record_order_execution(bypass_dir))
        pos_nobudget = center._positions["688777"]
        # 原老仓位为 4000 元 (200股 * 20元 = 4000元，占 4%)，无快照时拒绝扩大仓位，最多按老仓位 4% (400股 @ 10元 = 4000元)
        self.assertLessEqual(pos_nobudget.shares * 10.0, 5000.0)
        self.assertNotEqual(pos_nobudget.shares, 10000)

        # Case D: 攻击尝试：在持有陈旧快照(>300s)时试图满仓扩大仓位，执行端拒绝扩大
        center._positions["688777"].entry_date = "2026-09-19"
        old_snap = MarketSentimentSnapshot(
            tide_state="T5_ICE", tide_position_cap_pct=5.0,
            risk_mode="NORMAL", position_multiplier=1.0,
        ).finalize()
        old_snap.generated_at = pytime.time() - 600.0  # 10 分钟前陈旧快照
        center._last_market_context = old_snap
        stale_dir = IPOOrderDirective(
            action="FULL_ROTATION_SWAP", code="688666", name="陈旧快照渗透",
            price=10.0, shares=10000, size_pct=100.0,
            target_swap_code="688777", target_swap_name="无快照渗透"
        )
        self.assertTrue(center.record_order_execution(stale_dir))
        pos_stale = center._positions["688666"]
        # 原老仓位为 4000 元 (400股 * 10元 = 4000元，占 4%)，陈旧快照拒绝扩大仓位
        self.assertLessEqual(pos_stale.shares * 10.0, 5000.0)
        self.assertNotEqual(pos_stale.shares, 10000)

        # Case E: 攻击尝试：T0_INSUFFICIENT/NORMAL 快照试图手工满仓，执行端检测T0不足拒绝扩大
        center._positions["688666"].entry_date = "2026-09-19"
        t0_snap = MarketSentimentSnapshot(
            tide_state="T0_INSUFFICIENT", tide_position_cap_pct=100.0,
            risk_mode="NORMAL", position_multiplier=1.0,
        ).finalize()
        center._last_market_context = t0_snap
        t0_dir = IPOOrderDirective(
            action="FULL_ROTATION_SWAP", code="688555", name="T0渗透",
            price=10.0, shares=10000, size_pct=100.0,
            target_swap_code="688666", target_swap_name="陈旧快照渗透"
        )
        self.assertTrue(center.record_order_execution(t0_dir))
        pos_t0 = center._positions["688555"]
        self.assertLessEqual(pos_t0.shares * 10.0, 5000.0)
        self.assertNotEqual(pos_t0.shares, 10000)

        # Case F: 【防幽灵持仓专项验证】风控拒绝或失败分支绝不遗留空持仓对象
        center._positions["688555"].entry_date = "2026-09-19"
        # F1: T4 状态下换马指令被执行端预算拒绝（allowed_pct=0%）
        t4_snap = MarketSentimentSnapshot(
            tide_state="T4_PANIC_ACCEL", tide_position_cap_pct=0.0,
            risk_mode="BLOCK_NEW_BUYS", position_multiplier=0.0,
        ).finalize()
        t4_snap.generated_at = pytime.time()
        center._last_market_context = t4_snap
        rejected_dir = IPOOrderDirective(
            action="FULL_ROTATION_SWAP", code="688000", name="被拒标的",
            price=10.0, shares=1000, size_pct=10.0, timestamp=t4_snap.generated_at,
            target_swap_code="688555", target_swap_name="T0渗透"
        )
        self.assertFalse(center.record_order_execution(rejected_dir))
        self.assertNotIn("688000", center._positions, "风控拒绝换马绝不得留下幽灵持仓！")

        # F2: 对未持有标的执行 SELL，校验不通过返回 False，绝不得产生空持仓
        unheld_sell = IPOOrderDirective(
            action="SELL", code="688001", name="从未持有标的", price=10.0, shares=500
        )
        self.assertFalse(center.record_order_execution(unheld_sell))
        self.assertNotIn("688001", center._positions, "卖出不存在标的绝不得留下幽灵持仓！")

        # F3: 当日买入标的 T+1 硬锁拦截卖出，原持仓状态完整保持，不产生多余持仓
        center._positions["688555"].entry_date = pytime.strftime("%Y-%m-%d")
        t1_sell = IPOOrderDirective(
            action="SELL", code="688555", name="T0渗透", price=10.0, shares=100
        )
        self.assertFalse(center.record_order_execution(t1_sell))
        self.assertEqual(center._positions["688555"].shares, pos_t0.shares)


if __name__ == "__main__":
    unittest.main(verbosity=2)

