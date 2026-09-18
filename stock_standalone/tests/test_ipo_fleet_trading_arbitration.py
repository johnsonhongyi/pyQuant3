# -*- coding: utf-8 -*-
"""
tests/test_ipo_fleet_trading_arbitration.py
-------------------------------------------
新股次新股自动轮询后台测评与集中交易中心全局统筹（山外有山）全流程集成测试
覆盖点：
1. 守护者测评感知报告汇交；
2. 掌握全数据横向赛马与“山外有山”仲裁（消除单股局部盲区）；
3. 领头羊重仓配资（35%）与后排跟风 0 额度拦截；
4. 买错立斩（跌破 VWAP 0.6%）与极端高潮天量清仓；
5. 持续交易闭环：弃弱换马调仓（SWITCH_SWAP）与订单撮合资金持仓追踪；
6. 集中交易指挥室弹窗正常实例化。
"""

import unittest
import os
import sys
import time
from typing import List

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_DIR = os.path.dirname(_CUR_DIR)
if _PROJ_DIR not in sys.path:
    sys.path.insert(0, _PROJ_DIR)

from ats.strategy.ipo_vwap_detector_engine import (

    VWAPDetectorSignal,
    batch_evaluate_horse_race_ranking
)
from ats.strategy.ipo_trading_center import (
    IPOTradingCenter,
    IPOOrderDirective,
    IPOTradingPosition
)
from ats.strategy.ipo_market_sentiment_engine import IPOMarketSentimentEngine


class TestIPOFleetTradingArbitration(unittest.TestCase):

    def setUp(self):
        # 实例化交易中心
        self.center = IPOTradingCenter(total_capital=1000000.0)
        self.center._positions.clear()
        self.center._reports_cache.clear()
        self.center._order_history.clear()
        self.center._pending_directives.clear()
        self.center.available_cash = 1000000.0

    def test_guardian_report_submission_and_horse_race(self):
        """测试 1: 守护者报告汇交与横向赛马冒泡排位"""
        # 标的 A: 沈鼓集团 (首日上市，贴线惜售，9:31 拔地)
        sig_a = VWAPDetectorSignal(
            code="601091",
            name="沈鼓集团",
            price=12.50,
            change_pct=13.6,
            vwap=12.30,
            vwap_diff_pct=1.6,
            structure_tag="贴线微涨(首日惜售)",
            launch_time_str="09:31",
            launch_slope_deg=48.0,
            vwap_adhesion_ratio=95.0,
            sbc_activity_pct=320.0,
            is_ipo_first_day=True,
            is_above_vwap=True,
            signal_type="IPO_FIRST_BUY",
            signal_level="🔥 首发吸筹",
            stop_loss_price=12.20
        )

        # 标的 B: 频准激光 (早鸟梯队前锋，9:36 拔地)
        sig_b = VWAPDetectorSignal(
            code="688826",
            name="频准激光",
            price=45.0,
            change_pct=8.5,
            vwap=43.5,
            vwap_diff_pct=3.4,
            structure_tag="放量突破",
            launch_time_str="09:36",
            launch_slope_deg=38.0,
            vwap_adhesion_ratio=85.0,
            sbc_activity_pct=150.0,
            is_above_vwap=True,
            pullback_no_touch=True,
            signal_type="PULLBACK_BUY",
            signal_level="🚀 回踩启动",
            stop_loss_price=43.0
        )

        # 标的 C: 迟滞跟风标的 (10:15 启动，动能弱)
        sig_c = VWAPDetectorSignal(
            code="001365",
            name="天海电子",
            price=25.0,
            change_pct=2.1,
            vwap=24.8,
            vwap_diff_pct=0.8,
            structure_tag="常规震荡",
            launch_time_str="10:15",
            launch_slope_deg=18.0,
            vwap_adhesion_ratio=60.0,
            sbc_activity_pct=45.0,
            is_above_vwap=True,
            signal_type="PULLBACK_BUY",  # 单股自己以为是回踩买点
            signal_level="⚪ 观察",
            stop_loss_price=24.5
        )

        # 标的 D/E: 模拟梯队中微调的次新股，使红盘率保持在 60% 梯队升温合理区间
        sig_d = VWAPDetectorSignal(
            code="688835", name="微调次新1", price=18.0, change_pct=-1.2,
            vwap=18.2, vwap_diff_pct=-1.1, is_above_vwap=False
        )
        sig_e = VWAPDetectorSignal(
            code="688837", name="微调次新2", price=30.0, change_pct=-0.8,
            vwap=30.1, vwap_diff_pct=-0.3, is_above_vwap=False
        )

        # 汇交体检报告
        self.center.submit_stock_perception_report(sig_a)
        self.center.submit_stock_perception_report(sig_b)
        self.center.submit_stock_perception_report(sig_c)
        self.center.submit_stock_perception_report(sig_d)
        self.center.submit_stock_perception_report(sig_e)


        self.assertEqual(len(self.center._reports_cache), 5)

        # 交易中心执行全数据统筹裁决
        directives = self.center.evaluate_fleet_and_generate_orders()

        # 断言赛马排位: A > B > C
        self.assertEqual(sig_a.horse_race_rank, 1)
        self.assertEqual(sig_b.horse_race_rank, 2)
        self.assertGreater(sig_a.horse_race_score, sig_b.horse_race_score)
        self.assertGreater(sig_b.horse_race_score, sig_c.horse_race_score)

        # 验证“山外有山”仲裁反哺回写到信号对象
        self.assertEqual(sig_a.global_fleet_role, "LEADER")
        self.assertIn("首发吸筹 35%仓", sig_a.global_arbitration_desc)

        self.assertEqual(sig_b.global_fleet_role, "VANGUARD")
        self.assertIn("梯队前锋 15%仓", sig_b.global_arbitration_desc)

        # 核心断言：标的 C 虽然自己单股指标是回踩，但全局裁决判定为 FOLLOWER (山外有山·观望)
        self.assertEqual(sig_c.global_fleet_role, "FOLLOWER")
        self.assertIn("山外有山·观望 0%仓", sig_c.global_arbitration_desc)
        self.assertIn("落后领头羊", sig_c.global_arbitration_desc)
        self.assertIn("沈鼓集团", sig_c.global_arbitration_desc)

        # 断言只向 Top 1 和 Top 2 发出了买入指令，跟风标的 C 坚决 0 额度拦截
        buy_codes = [d.code for d in directives if d.action == "BUY"]
        self.assertIn("601091", buy_codes)
        self.assertIn("688826", buy_codes)
        self.assertNotIn("001365", buy_codes)

    def test_stop_loss_and_climax_exit_arbitration(self):
        """测试 2: 买错立斩与极端高潮平仓"""
        # 破位标的 D: 跌破 VWAP 0.8%
        sig_d = VWAPDetectorSignal(
            code="688835",
            name="破位标的",
            price=20.0,
            change_pct=-3.5,
            vwap=20.2,
            vwap_diff_pct=-1.0,
            is_above_vwap=False,
            signal_type="WEAK_EXIT",
            stop_loss_price=20.1
        )

        # 极端高潮标的 E: 偏离 VWAP 45% 且天量滞涨
        sig_e = VWAPDetectorSignal(
            code="688801",
            name="高潮标的",
            price=80.0,
            change_pct=19.8,
            vwap=55.0,
            vwap_diff_pct=45.5,
            is_above_vwap=True,
            is_climax_exit=True,
            signal_type="CLIMAX_EXIT"
        )

        # 模拟账户此前持有了 D 和 E
        self.center._positions["688835"] = IPOTradingPosition(
            code="688835", name="破位标的", shares=1000, cost_price=20.5
        )
        self.center._positions["688801"] = IPOTradingPosition(
            code="688801", name="高潮标的", shares=500, cost_price=50.0
        )

        self.center.submit_stock_perception_report(sig_d)
        self.center.submit_stock_perception_report(sig_e)

        directives = self.center.evaluate_fleet_and_generate_orders()

        # 验证全局仲裁
        self.assertEqual(sig_d.global_fleet_role, "STOP_LOSS")
        self.assertIn("买错立斩", sig_d.global_arbitration_desc)

        self.assertEqual(sig_e.global_fleet_role, "CLIMAX_EXIT")
        self.assertIn("高潮平仓", sig_e.global_arbitration_desc)

        # 验证卖出清仓指令
        sell_codes = [d.code for d in directives if d.action == "SELL"]
        self.assertIn("688835", sell_codes)
        self.assertIn("688801", sell_codes)

    def test_switch_swap_continuous_trading(self):
        """测试 3: 持续交易与弃弱换马调仓 (SWITCH_SWAP)"""
        # 账户当前持有了弱势标的 C (动能仅 55 分)
        self.center._positions["001365"] = IPOTradingPosition(
            code="001365", name="天海电子", shares=2000, cost_price=25.0
        )
        sig_c = VWAPDetectorSignal(
            code="001365",
            name="天海电子",
            price=25.2,
            change_pct=0.8,
            vwap=25.0,
            vwap_diff_pct=0.8,
            launch_time_str="10:30",
            launch_slope_deg=10.0,
            is_above_vwap=True,
            signal_type="WATCH"
        )

        # 全池轮询中杀出新的超级领头羊 A (96分，首日贴线惜售)
        sig_a = VWAPDetectorSignal(
            code="601091",
            name="沈鼓集团",
            price=12.50,
            change_pct=13.6,
            vwap=12.30,
            vwap_diff_pct=1.6,
            structure_tag="贴线微涨(首日惜售)",
            launch_time_str="09:31",
            launch_slope_deg=48.0,
            vwap_adhesion_ratio=95.0,
            sbc_activity_pct=320.0,
            is_ipo_first_day=True,
            is_above_vwap=True,
            signal_type="IPO_FIRST_BUY",
            signal_level="🔥 首发吸筹",
            stop_loss_price=12.20
        )

        self.center.submit_stock_perception_report(sig_c)
        self.center.submit_stock_perception_report(sig_a)

        directives = self.center.evaluate_fleet_and_generate_orders()

        # 断言生成了 SWITCH_SWAP 换马调仓指令
        swap_dirs = [d for d in directives if d.action == "SWITCH_SWAP"]
        self.assertEqual(len(swap_dirs), 1)
        self.assertEqual(swap_dirs[0].code, "001365")
        self.assertIn("弃弱换强·换马调仓", swap_dirs[0].reason)
        self.assertIn("沈鼓集团", swap_dirs[0].reason)

        # 测试一键批量执行决议
        executed_cnt = self.center.execute_all_pending_directives()
        self.assertGreater(executed_cnt, 0)

        # 验证弱势标的 C 被平仓
        pos_c = self.center._positions["001365"]
        self.assertEqual(pos_c.shares, 0)
        self.assertEqual(pos_c.status, "CLOSED")

        # 验证新超级领头羊 A 成功买入开仓
        self.assertIn("601091", self.center._positions)
        pos_a = self.center._positions["601091"]
        self.assertGreater(pos_a.shares, 0)
        self.assertEqual(pos_a.status, "HOLDING")

    def test_command_room_dialog_init(self):
        """测试 4: 集中交易指挥室弹窗正常实例化"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ats.ui.ipo_command_room_dialog import IPOCommandRoomDialog
        dlg = IPOCommandRoomDialog()
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.windowTitle(), "🚢 新股次新集中交易指挥室 (山外有山·全局统筹调度中心)")
        dlg.close()


if __name__ == "__main__":
    unittest.main()
