# -*- coding: utf-8 -*-
"""
tests/test_channel_secondary_buy_ui_and_engine.py
---------------------------------------------------
长期通道后企稳与底部结构次级买点 P1 界面呈现与交易指挥室卡片升级自动化测试
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

# 确保导入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ats.strategy.channel_secondary_buy_strategy import (
    SecondaryBuyStage,
    IPOTradePlan,
    evaluate_channel_secondary_buy,
    TAG_CHANNEL_SECONDARY_BUY,
)
from ats.strategy.ipo_vwap_detector_engine import (
    IPOVWAPDetectorEngine,
    VWAPDetectorSignal,
    batch_evaluate_horse_race_ranking,
)
from ats.ui.ipo_subnew_detector_dialog import (
    IPOSubnewDetectorDialog,
    IPODetectorTableWidget,
)
from ats.ui.ipo_command_room_dialog import (
    IPOCommandRoomDialog,
    ROLE_CN_MAP,
)
from ats.strategy.ipo_trading_center import (
    IPOTradingCenter,
    IPOOrderDirective,
)

# 确保 QApplication 单例
app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestChannelSecondaryBuyUIAndEngine(unittest.TestCase):
    """P1 阶段自动化集成测试"""

    def _build_secondary_buy_day_kline(self):
        """构造典型的下降通道 -> 筑底 -> 首阳试盘 -> 回踩抬高 -> 次级突破的日K线"""
        # 1. 20根长期下行通道 (20 -> 10)
        ch_down = [20.0 - i * 0.5 for i in range(20)]
        # 2. 6根底部平底箱体 (10.0 附近微幅波动)
        base = [10.0, 9.9, 10.1, 10.0, 9.95, 10.05]
        # 3. 3根首阳试盘冲高 (10.0 -> 11.5 -> 11.0)
        first_break = [10.6, 11.5, 11.0]
        # 4. 4根缩量回踩抬高底 (10.6, 10.4, 10.5, 10.45, 均高于 base_low 9.9)
        pullback = [10.6, 10.4, 10.5, 10.45]
        # 5. 1根放量上翘突破首阳试盘位次级买点 (11.6 > 11.5)
        sec_buy = [11.6]

        prices = ch_down + base + first_break + pullback + sec_buy
        n = len(prices)
        vols = [1000.0] * 20 + [300.0] * 6 + [2500.0] * 3 + [400.0] * 4 + [3500.0] * 1
        highs = [p * 1.01 for p in prices]
        lows = [p * 0.99 for p in prices]
        opens = [p * 0.995 for p in prices]

        df = pd.DataFrame({
            "close": prices,
            "high": highs,
            "low": lows,
            "open": opens,
            "vol": vols,
            "date": [f"2026-08-{i+1:02d}" for i in range(n)]
        })
        return df

    def test_01_engine_secondary_buy_detection(self):
        """验证检测引擎正确接入通道次级买点并生成 TradePlan"""
        engine = IPOVWAPDetectorEngine.get_instance()
        df_day = self._build_secondary_buy_day_kline()
        clean_code = "688826"

        sig = VWAPDetectorSignal(code=clean_code, name="复洁科技", price=11.6, vwap=10.8)
        engine._evaluate_channel_secondary_buy_structure(clean_code, sig, df_day)

        self.assertEqual(sig.channel_stage, SecondaryBuyStage.SECONDARY_BUY)
        self.assertEqual(sig.channel_stage_cn, "👑 次级买点")
        self.assertTrue(sig.higher_low_stop > 0)
        self.assertTrue(sig.base_low_invalid > 0)
        self.assertIsNotNone(sig.trade_plan)
        self.assertIsInstance(sig.trade_plan, IPOTradePlan)
        self.assertEqual(sig.trade_plan.strategy_tag, TAG_CHANNEL_SECONDARY_BUY)

        # 综合决议
        engine._synthesize_final_decision(sig)
        self.assertEqual(sig.signal_type, "SECONDARY_BUY")
        self.assertIn("次级买点", sig.signal_level)
        self.assertIn(sig.quality_grade, ("A", "S", "SS"))
        self.assertIn("通道次级买点", sig.structure_tag)
        self.assertIn("回踩抬高底", sig.signal_desc)

    def test_02_horse_race_ranking_for_secondary_buy(self):
        """验证赛马天梯为通道次级买点赋予高分与专属徽章"""
        sig1 = VWAPDetectorSignal(code="688826", name="复洁科技", price=11.6, vwap=10.8)
        sig1.signal_type = "SECONDARY_BUY"
        sig1.channel_stage = "SECONDARY_BUY"
        sig1.quality_grade = "SS"

        sig2 = VWAPDetectorSignal(code="000001", name="平安银行", price=10.0, vwap=10.2)
        sig2.signal_type = "WATCH"

        ranked = batch_evaluate_horse_race_ranking([sig2, sig1])
        # sig1 应排在前面且拥有 88+ 高动能分
        self.assertEqual(ranked[0].code, "688826")
        self.assertGreaterEqual(ranked[0].horse_race_score, 88.0)
        self.assertEqual(ranked[0].horse_race_tier, "👑 次级买点")

    def test_03_detector_dialog_table_rendering(self):
        """验证检测工具表格第 6、8、9、10 列对形态阶段、评级、止损和 TradePlan 的渲染"""
        dlg = IPOSubnewDetectorDialog()
        dlg.monitored_codes = ["688826"]
        dlg._rebuild_table_rows()
        sig = VWAPDetectorSignal(code="688826", name="复洁科技", price=11.6, vwap=10.8)
        sig.channel_stage = "SECONDARY_BUY"
        sig.channel_stage_cn = "👑 次级买点"
        sig.quality_grade = "SS"
        sig.signal_level = "👑 次级买点"
        sig.signal_type = "SECONDARY_BUY"
        sig.higher_low_stop = 10.35
        sig.base_low_invalid = 9.90
        sig.trade_plan = IPOTradePlan(
            code="688826",
            name="复洁科技",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            trigger_price=11.6,
            buy_zone_min=11.45,
            buy_zone_max=11.65,
            higher_low_stop=10.35,
            base_low_invalid=9.90,
            target_1_channel_mid=13.50,
            target_2_swing_high=15.20,
            position_pct=15.0,
            suggested_action="BUY_SCOUT"
        )
        sig.signal_desc = "长期下降通道企稳，回踩抬高底放量确认次级买点!"

        dlg.signals_map["688826"] = sig
        dlg._update_table_row_data(sig, target_row=0, manage_sorting=False)

        # 检查第 6 列 (VWAP结构形态)
        it_struct = dlg.table.item(0, 6)
        self.assertIsNotNone(it_struct)
        self.assertIn("👑 次级买点", it_struct.text())
        self.assertIn("通道阶段", it_struct.toolTip())

        # 检查第 8 列 (信号评级)
        it_level = dlg.table.item(0, 8)
        self.assertIsNotNone(it_level)
        self.assertIn("SS", it_level.text())
        self.assertIn("次级买点", it_level.text())

        # 检查第 9 列 (极窄止损位)
        it_sl = dlg.table.item(0, 9)
        self.assertIsNotNone(it_sl)
        self.assertEqual(it_sl.text(), "10.35")
        self.assertIn("抬高底次级防守位", it_sl.toolTip())
        self.assertIn("大底报废失效位: 9.90", it_sl.toolTip())

        # 检查第 10 + n_extra 列 (操作建议与 TradePlan Tooltip)
        desc_col = 10 + len(dlg.extra_cols)
        it_desc = dlg.table.item(0, desc_col)
        self.assertIsNotNone(it_desc)
        self.assertIn("TradePlan 不可变交易计划", it_desc.toolTip())
        self.assertIn("买入网格: 11.45 ~ 11.65", it_desc.toolTip())
        self.assertIn("BUY_SCOUT", it_desc.toolTip())

    def test_04_command_room_directives_tradeplan_display(self):
        """验证集中交易指挥室待执行指令卡片呈现 TradePlan 网格与动作"""
        center = IPOTradingCenter.get_instance()
        cmd_room = IPOCommandRoomDialog()
        cmd_room.trading_center = center

        # 角色映射验证
        self.assertIn("SECONDARY_BUY", ROLE_CN_MAP)
        self.assertEqual(ROLE_CN_MAP["SECONDARY_BUY"], "👑 次级买点")

        # 构造带 TradePlan 的指令
        plan = IPOTradePlan(
            code="688826",
            name="复洁科技",
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            trigger_price=11.6,
            buy_zone_min=11.45,
            buy_zone_max=11.65,
            higher_low_stop=10.35,
            base_low_invalid=9.90,
            target_1_channel_mid=13.50,
            target_2_swing_high=15.20,
            position_pct=15.0,
            suggested_action="BUY_SCOUT"
        )
        directive = IPOOrderDirective(
            action="BUY",
            code="688826",
            name="复洁科技",
            price=11.6,
            shares=1000,
            size_pct=15.0,
            urgency="HIGH",
            reason="次级买点确认放量试仓",
            signal_level="S4",
            quality_grade="SS",
            trade_plan=plan
        )
        center._pending_directives = [directive]

        # 刷新指令表
        cmd_room._orders_view_mode = "PENDING"
        cmd_room.refresh_data()

        self.assertEqual(cmd_room.tbl_orders.rowCount(), 1)
        it_act = cmd_room.tbl_orders.item(0, 0)
        self.assertIsNotNone(it_act)
        # 动作显示为 BUY_SCOUT
        self.assertEqual(it_act.text(), "BUY_SCOUT")

        # 理由列包含网格与防守线
        it_reason = cmd_room.tbl_orders.item(0, 5)
        self.assertIsNotNone(it_reason)
        self.assertIn("11.45~11.65", it_reason.text())
        self.assertIn("TradePlan 不可变交易计划", it_reason.toolTip())
        self.assertIn("目标1(中轨): 13.50", it_reason.toolTip())


if __name__ == "__main__":
    unittest.main()
