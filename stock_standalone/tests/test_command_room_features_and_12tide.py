# -*- coding: utf-8 -*-
"""
tests/test_command_room_features_and_12tide.py
-----------------------------------------------
专项单元测试：
1. 集中交易指挥室历史信号日志完整时间格式与今日/历史隔离；
2. 历史日志清理功能 (保留今日 / 清空全部) 及原子持久化；
3. 标的归集与连续持久力 (Persistence) 统计模型与时间线展示；
4. 动能评分与外部质量评估深度适配底层 12 级潮汐状态机 (T0~T11)。
"""

import os
import sys
import time
import unittest

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from PyQt6.QtWidgets import QApplication
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from ats.strategy.ipo_trading_center import IPOTradingCenter
from ats.strategy.ipo_vwap_detector_engine import (
    VWAPDetectorSignal,
    batch_evaluate_horse_race_ranking
)
from ats.ui.ipo_command_room_dialog import (
    IPOCommandRoomDialog,
    IPOSignalTimelineDialog
)


class TestCommandRoomFeaturesAnd12Tide(unittest.TestCase):
    def setUp(self):
        self.tc = IPOTradingCenter(total_capital=1000000.0, auto_load_ledger=False)

    def tearDown(self):
        pass

    def test_01_clear_signal_logs_and_date_distinction(self):
        """测试 1: 验证日志清理功能 (清除陈旧历史保留今日 / 清空全部)"""
        now = time.time()
        today_str = time.strftime("%Y-%m-%d")
        yesterday_str = "2026-09-20"

        # 模拟注入今日日志与历史旧日志
        self.tc._signal_iteration_log = [
            {
                "timestamp": now,
                "time_str": f"{today_str} 10:30:00",
                "action": "BUY_SCOUT",
                "code": "688826",
                "name": "腾景激光",
                "signal_tier": "S",
                "reason": "测试今日信号"
            },
            {
                "timestamp": now - 86400,
                "time_str": f"{yesterday_str} 14:20:00",
                "action": "SIGNAL_INJECT",
                "code": "601091",
                "name": "沈波集团",
                "signal_tier": "SSS",
                "reason": "测试昨日旧信号"
            },
            {
                "timestamp": now - 172800,
                "time_str": f"2026-09-19 09:45:00",
                "action": "SIGNAL_INJECT",
                "code": "301689",
                "name": "电科思仪",
                "signal_tier": "A",
                "reason": "测试前日旧信号"
            }
        ]

        self.assertEqual(len(self.tc.get_signal_iteration_log()), 3)

        # 1. 测试“仅清理陈旧历史 (保留今日)”
        removed = self.tc.clear_signal_iteration_logs(keep_today=True)
        self.assertEqual(removed, 2, "应清理 2 条昨日/前日陈旧日志")
        remaining = self.tc.get_signal_iteration_log()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["code"], "688826")
        self.assertTrue(remaining[0]["time_str"].startswith(today_str))

        # 2. 测试“彻底清空全部历史日志”
        removed_all = self.tc.clear_signal_iteration_logs(keep_today=False)
        self.assertEqual(removed_all, 1)
        self.assertEqual(len(self.tc.get_signal_iteration_log()), 0)

    def test_02_dialog_aggregation_and_persistence_tags(self):
        """测试 2: 验证指挥室标的归集视图与连续持久力模型计算"""
        dlg = IPOCommandRoomDialog(parent_detector_dialog=None)
        dlg.trading_center = self.tc

        now = time.time()
        today_str = time.strftime("%Y-%m-%d")

        # 构造同一个标的 688826 在全天的多次异动
        logs = [
            {
                "timestamp": now - 3600,
                "time_str": f"{today_str} 09:32:00",
                "action": "SIGNAL_INJECT",
                "code": "688826",
                "name": "腾景激光",
                "signal_tier": "S",
                "reason": "早盘首次感知"
            },
            {
                "timestamp": now - 1800,
                "time_str": f"{today_str} 10:02:00",
                "action": "BUY_SCOUT",
                "code": "688826",
                "name": "腾景激光",
                "signal_tier": "SS",
                "reason": "次级买点确认"
            },
            {
                "timestamp": now - 300,
                "time_str": f"{today_str} 10:27:00",
                "action": "BUY_CONFIRM",
                "code": "688826",
                "name": "腾景激光",
                "signal_tier": "SSS",
                "reason": "放量加仓共振"
            },
            # 单次脉冲标的
            {
                "timestamp": now - 600,
                "time_str": f"{today_str} 10:22:00",
                "action": "SIGNAL_INJECT",
                "code": "920071",
                "name": "金钛股份",
                "signal_tier": "A",
                "reason": "偶发脉冲"
            }
        ]
        self.tc._signal_iteration_log = logs

        # 切换为 HISTORY 模式并切换为 AGGREGATED (标的归集) 视图
        dlg._set_orders_view_mode("HISTORY")
        dlg._set_history_sub_mode("AGGREGATED")
        dlg.refresh_data()

        # 验证归集结果：4条流水日志归集为 2 只标的
        self.assertEqual(len(dlg._current_aggregated_logs_list), 2)
        
        # 验证 688826 归集统计
        item_688826 = next((x for x in dlg._current_aggregated_logs_list if x["code"] == "688826"), None)
        self.assertIsNotNone(item_688826)
        self.assertEqual(item_688826["count"], 3, "688826 应有 3 次异动记录")
        self.assertEqual(item_688826["max_tier"], "SSS", "最高战术级别应为 SSS")
        self.assertEqual(item_688826["last_action"], "BUY_CONFIRM")

        # 验证时间跨度
        span_min = int((item_688826["last_ts"] - item_688826["first_ts"]) // 60)
        self.assertGreaterEqual(span_min, 50, "跨度应为约 55 分钟")

        dlg.close()

    def test_03_signal_timeline_dialog_popup(self):
        """测试 3: 验证标的异动时间线弹窗 (IPOSignalTimelineDialog) 构建与时序"""
        records = [
            {"timestamp": 1000.0, "time_str": "2026-09-21 09:30:00", "action": "SIGNAL_INJECT", "signal_tier": "A", "price": 10.0, "reason": "首次发现"},
            {"timestamp": 2000.0, "time_str": "2026-09-21 09:46:40", "action": "BUY_SCOUT", "signal_tier": "S", "price": 10.5, "reason": "突破试探买入"},
            {"timestamp": 3000.0, "time_str": "2026-09-21 10:03:20", "action": "BUY_CONFIRM", "signal_tier": "SSS", "price": 11.2, "reason": "主升浪确认加仓"}
        ]
        dlg = IPOSignalTimelineDialog(code="688826", name="腾景激光", records=records)
        self.assertEqual(dlg.table.rowCount(), 3)
        # 表格为最新在顶部展示，动作统一使用中文展示
        self.assertEqual(dlg.table.item(0, 3).text(), "🎯 确认加仓")
        self.assertEqual(dlg.table.item(2, 3).text(), "📡 雷达入池")
        dlg.close()

    def test_04_12_stage_tide_momentum_scoring(self):
        """测试 4: 验证 12 级潮汐状态机与动能评分适配 (消除涨了就全 99/100 分的高分失真)"""
        # 标的 A: 日涨幅 18%、偏离 VWAP 22% (高位天量狂热追高股)
        sig_surge = VWAPDetectorSignal(
            code="601091", name="沈波集团", price=50.0, change_pct=18.0,
            vwap=41.0, is_above_vwap=True, vwap_diff_pct=22.0
        )
        # 标的 B: 次级买点 (守住 Higher Low，回踩企稳确认)
        sig_sec_buy = VWAPDetectorSignal(
            code="688826", name="腾景激光", price=25.0, change_pct=3.5,
            vwap=24.5, is_above_vwap=True, vwap_diff_pct=2.0,
            signal_type="SECONDARY_BUY", channel_stage="SECONDARY_BUY",
            quality_grade="S"
        )

        # 1. 模拟在【高潮派发期 T1_CLIMAX_DISTRIBUTION 或 T11_OVERHEATED】
        # 此时高位天量狂热标的必须被折减，绝不给 99 分高分
        ranked_t1 = batch_evaluate_horse_race_ranking(
            [sig_surge, sig_sec_buy],
            tide_state="T1_CLIMAX_DISTRIBUTION"
        )
        score_surge_t1 = next(s.horse_race_score for s in ranked_t1 if s.code == "601091")
        self.assertLess(score_surge_t1, 80.0, "高潮派发期严重追高偏离股应被折减，不能给 90+ 高分")

        # 2. 模拟在【冰点与背离期 T5_ICE 或 T6_ICE_DIVERGENCE】
        # 此时次级买点获得逆周期赋权 (+4~5分)，稳居领头羊前列
        ranked_t6 = batch_evaluate_horse_race_ranking(
            [sig_surge, sig_sec_buy],
            tide_state="T6_ICE_DIVERGENCE"
        )
        sec_buy_ranked = next(s for s in ranked_t6 if s.code == "688826")
        self.assertGreaterEqual(sec_buy_ranked.horse_race_score, 90.0, "冰点背离期次级买点应获得潮汐逆转先锋赋权")
        self.assertEqual(sec_buy_ranked.horse_race_tier, "👑 次级买点")

    def test_05_external_signal_quality_12_tide_adaptation(self):
        """测试 5: 验证外部信号质量评估与 12 级潮汐联动，杜绝无脑打 100 满分"""
        # 外部传入 95 分的高分信号
        res_normal = self.tc.evaluate_external_signal_quality(
            source="每日天梯",
            code="688826",
            name="腾景激光",
            reason="贴线放量突破",
            score=95.0
        )
        # 验证最终打分在 80~95 分的合理区间，绝不是死板的 100.0 分
        self.assertLessEqual(res_normal["quality_score"], 95.0, "质量分应有上限约束，杜绝无脑100分")
        self.assertGreaterEqual(res_normal["quality_score"], 80.0)

    def test_06_friendly_time_and_price_and_position_display(self):
        """测试 6: 验证触发时间友好显示到分、价格市价跟踪与观察信号仓位不误导100%"""
        from ats.ui.ipo_arbitration_detail_dialog import IPOArbitrationDetailDialog, format_time_to_minute

        # 1. 验证时间格式化：浮点时间戳 -> YYYY-MM-DD HH:MM
        ts_raw = 1789965577.1566353
        formatted_time = format_time_to_minute(ts_raw)
        self.assertRegex(formatted_time, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", "时间戳必须精确友好显示到分钟")

        # 2. 验证弹窗渲染：SIGNAL_INJECT 且价格为 0 时
        log_item = {
            "code": "688112",
            "name": "鼎阳科技",
            "action": "SIGNAL_INJECT",
            "price": 0.0,
            "size_pct": 100.0,  # 模拟历史遗留的 100%
            "signal_tier": "SSS",
            "reason": "【🚀 龙头突击·95分】质量策略评估通过，转入新股次新检查中心",
            "timestamp": ts_raw
        }
        dlg = IPOArbitrationDetailDialog.get_instance()
        dlg.update_content("688112", log_item=log_item)

        # 验证价格不显示冷冰冰的 ¥0.00
        self.assertNotIn("¥0.00", dlg.txt_arbitration_desc.toHtml())
        self.assertIn("市价跟踪", dlg.txt_arbitration_desc.toHtml())
        self.assertEqual(dlg.lbl_vwap_line.text(), "参考价格: 市价跟踪")

        # 验证仓位不显示误导性的 100%，而是雷达锁定/入池监控
        self.assertIn("雷达锁定", dlg.lbl_race_info.text())
        self.assertIn("雷达锁定", dlg.txt_arbitration_desc.toHtml())
        self.assertNotIn("100% 仓位", dlg.lbl_action_badge.text())
        self.assertEqual(dlg.lbl_vwap_bias.text(), "建议仓位: 待触发买点")

        # 验证时间友好显示到分
        self.assertIn(formatted_time, dlg.lbl_race_info.text())
        self.assertIn(formatted_time, dlg.lbl_launch_time.text())
        self.assertNotIn("1789965577", dlg.lbl_race_info.text())

    def test_07_action_chinese_mapping_and_multi_mode_persistence(self):
        """测试 7: 验证动作全链路标准中文映射与表格多模式专属持久化"""
        from ats.ui.ipo_command_room_dialog import (
            get_action_display_name, IPOCommandRoomTableWidget,
            ORDER_TABLE_CFG_PENDING, ORDER_TABLE_CFG_STREAM, ORDER_TABLE_CFG_AGG,
            ORDER_TABLE_DEFAULT_WIDTHS
        )

        # 1. 验证动作全量中文映射
        self.assertEqual(get_action_display_name("SIGNAL_INJECT"), "📡 雷达入池")
        self.assertEqual(get_action_display_name("BUY"), "🟢 主动买入")
        self.assertEqual(get_action_display_name("BUY_SCOUT"), "🔭 试仓买入")
        self.assertEqual(get_action_display_name("BUY_CONFIRM"), "🎯 确认加仓")
        self.assertEqual(get_action_display_name("SELL"), "🔴 卖出平仓")
        self.assertEqual(get_action_display_name("FULL_ROTATION_SWAP"), "🔄 全仓轮动")
        self.assertEqual(get_action_display_name("STOP_LOSS"), "🛑 止损平仓")

        # 2. 验证多模式表格配置切换与隔离
        table = IPOCommandRoomTableWidget()
        table.register_persistence_mode("PENDING", ORDER_TABLE_CFG_PENDING, ORDER_TABLE_DEFAULT_WIDTHS["PENDING"])
        table.register_persistence_mode("STREAM", ORDER_TABLE_CFG_STREAM, ORDER_TABLE_DEFAULT_WIDTHS["STREAM"])
        table.register_persistence_mode("AGGREGATED", ORDER_TABLE_CFG_AGG, ORDER_TABLE_DEFAULT_WIDTHS["AGGREGATED"])

        # 切换到 PENDING
        table.setColumnCount(6)
        table.switch_persistence_mode("PENDING")
        self.assertEqual(table._current_mode, "PENDING")
        self.assertEqual(table._config_key, ORDER_TABLE_CFG_PENDING)

        # 手动调整第 0 列宽度
        table.setColumnWidth(0, 120)
        table.save_column_widths()

        # 切换到 STREAM
        table.setColumnCount(6)
        table.switch_persistence_mode("STREAM")
        self.assertEqual(table._current_mode, "STREAM")
        self.assertEqual(table._config_key, ORDER_TABLE_CFG_STREAM)

        # 切换回 PENDING，验证恢复之前的列宽
        table.switch_persistence_mode("PENDING")
        self.assertEqual(table.columnWidth(0), 120)

        # 切换到 AGGREGATED (8列)
        table.setColumnCount(8)
        table.switch_persistence_mode("AGGREGATED")
        self.assertEqual(table._current_mode, "AGGREGATED")
        self.assertEqual(table._config_key, ORDER_TABLE_CFG_AGG)
        self.assertEqual(table.columnCount(), 8)


if __name__ == "__main__":
    unittest.main()

