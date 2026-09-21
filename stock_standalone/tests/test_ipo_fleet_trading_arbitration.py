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
        # 实例化交易中心并清理缓存
        self.center = IPOTradingCenter(total_capital=1000000.0)
        self.center._positions.clear()
        self.center._reports_cache.clear()
        self.center._order_history.clear()
        self.center._pending_directives.clear()
        self.center.available_cash = 1000000.0
        # 重置市场情绪引擎单例缓存，确保测试隔离
        engine = IPOMarketSentimentEngine.get_instance()
        engine._cached_snapshot = None
        engine._last_calc_ts = 0.0

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

        # 注入合法潮汐市场快照以通过风控闸门
        from ats.strategy.ipo_market_sentiment_engine import MarketSentimentSnapshot
        snap = MarketSentimentSnapshot(
            tide_state="T6_ICE_DIVERGENCE",
            tide_position_cap=0.8,
            risk_multiplier=1.0,
            generated_at=time.time(),
            trading_day=time.strftime("%Y%m%d")
        )
        self.center.sentiment_engine._cached_snapshot = snap
        self.center._last_market_context = snap

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

    def test_command_room_dialog_linkage_to_detector(self):
        """测试 5: 集中交易指挥室点击行与切行直接联动主检测工具聚焦 code"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
        detector = IPOSubnewDetectorDialog()
        detector.monitored_codes = ["601091", "688826", "001365"]
        detector._rebuild_table_rows()

        from ats.ui.ipo_command_room_dialog import IPOCommandRoomDialog
        cmd_room = IPOCommandRoomDialog(parent_detector_dialog=detector)
        
        # 验证 select_and_focus_code 接口精确定位
        res = detector.select_and_focus_code("688826", trigger_linkage=False)
        self.assertTrue(res)
        cur_row = detector.table.currentRow()
        self.assertGreaterEqual(cur_row, 0)
        it_code = detector.table.item(cur_row, 0)
        self.assertIn("688826", it_code.text())

        cmd_room.close()
        detector.close()

    def test_command_room_table_column_persistence_and_no_truncation(self):
        """测试 6: 集中交易指挥室表格列宽持久化能力与防文字截断"""
        from PyQt6.QtWidgets import QApplication, QHeaderView
        app = QApplication.instance() or QApplication([])

        from ats.ui.ipo_command_room_dialog import IPOCommandRoomDialog
        dlg = IPOCommandRoomDialog()

        # 1. 验证天梯表、持仓表、指令清单表均具备标准持久化方法
        for tbl in (dlg.tbl_rank, dlg.tbl_pos, dlg.tbl_orders):
            self.assertTrue(hasattr(tbl, "save_column_widths"))
            self.assertTrue(hasattr(tbl, "restore_column_widths"))
            self.assertTrue(hasattr(tbl, "reset_default_widths"))
            self.assertTrue(hasattr(tbl, "auto_fit_columns"))

        # 2. 验证 tbl_rank 默认列宽：动能分 >= 68px，启动时点 >= 76px，彻底消灭省略号截断
        hv_rank = dlg.tbl_rank.horizontalHeader()
        w_score = dlg.tbl_rank.columnWidth(4)  # 动能分
        w_time = dlg.tbl_rank.columnWidth(5)   # 启动时点
        self.assertGreaterEqual(w_score, 68, f"动能分列宽 {w_score} 必须 >= 68px 防止文字截断")
        self.assertGreaterEqual(w_time, 76, f"启动时点列宽 {w_time} 必须 >= 76px 防止文字截断")

        # 3. 验证所有列均设为 Interactive 自由拖拽模式
        for c in range(dlg.tbl_rank.columnCount()):
            self.assertEqual(
                hv_rank.sectionResizeMode(c),
                QHeaderView.ResizeMode.Interactive,
                f"天梯表第 {c} 列必须为 Interactive 拖拽模式"
            )

        # 4. 模拟操盘手手动拖拽调整列宽并持久化
        dlg.tbl_rank.setColumnWidth(4, 95)
        dlg.tbl_rank.setColumnWidth(5, 105)
        dlg.tbl_rank.save_column_widths()

        # 模拟关闭窗口时的集中落盘
        dlg._save_dialog_state()

        # 验证恢复能够读取保存的宽度
        dlg.tbl_rank.setColumnWidth(4, 30)  # 扰乱
        dlg.tbl_rank.restore_column_widths()
        self.assertEqual(dlg.tbl_rank.columnWidth(4), 95)
        self.assertEqual(dlg.tbl_rank.columnWidth(5), 105)

        # 5. 验证重置默认列宽能够正常还原
        dlg.tbl_rank.reset_default_widths()
        self.assertGreaterEqual(dlg.tbl_rank.columnWidth(4), 68)
        self.assertGreaterEqual(dlg.tbl_rank.columnWidth(5), 76)

        dlg.close()

    def test_command_room_chinese_role_and_sorting_support_and_narrow_mode(self):
        """测试 7: 角色中文映射、表头数值精确排序与极窄模式分割线规范"""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        app = QApplication.instance() or QApplication([])

        from ats.ui.ipo_command_room_dialog import IPOCommandRoomDialog, ROLE_CN_MAP
        from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal

        dlg = IPOCommandRoomDialog()

        # 1. 验证极窄模式样式表、垂直右边框与极窄滚动条设置
        ss = dlg.styleSheet()
        self.assertIn("QScrollBar:vertical", ss, "必须配置极窄模式垂直滚动条")
        self.assertIn("QScrollBar:horizontal", ss, "必须配置极窄模式水平滚动条")
        self.assertIn("border-right", ss, "表头必须具备明确的列间分隔线")
        self.assertTrue(dlg.tbl_rank.showGrid(), "天梯表格必须启用网格线")

        # 2. 验证三个表格全面支持排序
        self.assertTrue(dlg.tbl_rank.isSortingEnabled(), "天梯表格必须启用排序")
        self.assertTrue(dlg.tbl_pos.isSortingEnabled(), "持仓表格必须启用排序")
        self.assertTrue(dlg.tbl_orders.isSortingEnabled(), "指令表格必须启用排序")
        self.assertTrue(dlg.tbl_rank.horizontalHeader().isSortIndicatorShown())

        # 3. 注入测试信号并刷新数据
        sig1 = VWAPDetectorSignal(
            code="601091", name="沈鼓集团", price=50.0, horse_race_score=95.0,
            global_fleet_role="LEADER", horse_race_rank=1, is_above_vwap=True
        )
        sig2 = VWAPDetectorSignal(
            code="688826", name="频准激光", price=200.0, horse_race_score=80.0,
            global_fleet_role="VANGUARD", horse_race_rank=2, is_above_vwap=True
        )
        sig3 = VWAPDetectorSignal(
            code="001365", name="鼎佳科技", price=25.0, horse_race_score=60.0,
            global_fleet_role="FOLLOWER", horse_race_rank=3, is_above_vwap=True
        )
        dlg.trading_center._ranked_cache = [sig1, sig2, sig3]
        dlg.refresh_data()

        # 验证角色已 100% 映射为中文
        role_txt_row0 = dlg.tbl_rank.item(0, 6).text()
        role_txt_row1 = dlg.tbl_rank.item(1, 6).text()
        role_txt_row2 = dlg.tbl_rank.item(2, 6).text()
        self.assertEqual(role_txt_row0, "🥇 领头羊")
        self.assertEqual(role_txt_row1, "🥈 梯队前锋")
        self.assertEqual(role_txt_row2, "🥉 后排跟风")

        # 4. 测试点击表头执行数值排序 (以现价升序排序测试)
        # 当前价格：Row 0 是 50.0, Row 1 是 200.0, Row 2 是 25.0
        # 现价位于第 3 列，按升序排序后，第 0 行应该是 25.0 (001365)，最后一行是 200.0 (688826)
        dlg.tbl_rank.sortItems(3, Qt.SortOrder.AscendingOrder)
        self.assertIn("25.00", dlg.tbl_rank.item(0, 3).text())
        self.assertIn("200.00", dlg.tbl_rank.item(2, 3).text())

        # 按现价降序排序后，第 0 行应该是 200.0 (688826)
        dlg.tbl_rank.sortItems(3, Qt.SortOrder.DescendingOrder)
        self.assertIn("200.00", dlg.tbl_rank.item(0, 3).text())
        self.assertIn("25.00", dlg.tbl_rank.item(2, 3).text())

        dlg.close()

    def test_arbitration_detail_dialog_fast_reusable_mode(self):
        """测试 8: 集中仲裁与操作建议透视详情窗的极速复用模式 (Reusable Singleton)"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ats.ui.ipo_arbitration_detail_dialog import IPOArbitrationDetailDialog

        # 1. 验证单例模式与极速复用 (保证多次调用返回同一实例)
        dlg1 = IPOArbitrationDetailDialog.get_instance()
        dlg2 = IPOArbitrationDetailDialog.get_instance()
        self.assertIs(dlg1, dlg2)

        # 2. 构造测试信号与指令
        sig_test = VWAPDetectorSignal(
            code="601091",
            name="沈鼓集团",
            price=56.80,
            vwap=52.00,
            vwap_diff_pct=9.23,
            structure_tag="突破走强",
            launch_time_str="09:31",
            stop_loss_price=51.68,
            horse_race_score=98.0,
            horse_race_rank=1,
            global_fleet_role="LEADER",
            global_arbitration_desc="【高潮领头羊 15%仓】全市情绪总龙头，高潮吸筹，买错跌破 VWAP 0.6% 铁律出局"
        )

        # 3. 极速更新并展示
        dlg_shown = IPOArbitrationDetailDialog.show_or_update("601091", signal_obj=sig_test)
        self.assertIs(dlg_shown, dlg1)
        self.assertTrue(dlg_shown.isVisible())

        # 验证界面关键文本已秒级就地刷新
        self.assertIn("601091", dlg_shown.lbl_code_name.text())
        self.assertIn("沈鼓集团", dlg_shown.lbl_code_name.text())
        self.assertIn("56.80", dlg_shown.lbl_price.text())
        self.assertIn("🥇 领头羊", dlg_shown.lbl_role_tag.text())
        self.assertIn("第 1 名", dlg_shown.lbl_race_info.text())
        self.assertIn("98", dlg_shown.lbl_race_info.text())
        self.assertIn("52.00", dlg_shown.lbl_vwap_line.text())
        self.assertIn("+9.23%", dlg_shown.lbl_vwap_bias.text())
        self.assertIn("51.68", dlg_shown.lbl_stop_loss.text())
        self.assertIn("高潮领头羊", dlg_shown.txt_arbitration_desc.toPlainText())

        # 4. 验证关闭拦截为隐藏 (不销毁，保证常驻内存 0 毫秒极速唤醒)
        dlg_shown.close()
        self.assertFalse(dlg_shown.isVisible())

        # 5. 验证指挥室的双击触发分发
        from ats.ui.ipo_command_room_dialog import IPOCommandRoomDialog
        cmd_room = IPOCommandRoomDialog(parent_detector_dialog=None)
        cmd_room.trading_center._ranked_cache = [sig_test]
        cmd_room.refresh_data()

        # 模拟双击第 7 列 (集中仲裁列) -> 应当唤起复用详情窗
        cmd_room._on_table_double_clicked(cmd_room.tbl_rank, 0, col=7)
        self.assertTrue(dlg_shown.isVisible())
        self.assertIn("601091", dlg_shown.lbl_code_name.text())

        cmd_room.close()
        dlg_shown.hide()


if __name__ == "__main__":
    unittest.main()

