# -*- coding: utf-8 -*-
"""
tests/test_time_slice_persistence_and_sbc_two_line.py
测试：
1. SBC 分时图画布左侧边距设置为 58，并且包含 channel_info 字段
2. 每日涨停天梯 (DailyLimitUpDialog) combo_time_slice 自动持久化与恢复
3. 强势板块龙头突击 (HotSectorLeaderboardDialog) combo_time_slice 自动持久化与恢复
"""

import os
import sys
import unittest
import pandas as pd
from PyQt6.QtWidgets import QApplication

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.ui.styles import save_config_node, load_config_node
from ats.ui.intraday_strategy_dialog import SBCChartCanvas
from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog
from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog

app = QApplication.instance() or QApplication(sys.argv)


class TestTimeSlicePersistenceAndSBCTwoLine(unittest.TestCase):

    def test_sbc_two_line_left_axis_canvas(self):
        canvas = SBCChartCanvas(None)
        self.assertEqual(canvas.MARGIN_LEFT, 62)
        self.assertIsInstance(canvas.channel_info, dict)
        canvas.close()

    def test_sbc_log_rich_text_highlight(self):
        """测试 SBC 实时数据日志富文本 HTML 高对比及价格涨红跌绿高亮"""
        from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
        dlg = SBCIntradayChartDialog(code="600630")
        try:
            # 模拟触发一次日志更新 (现价 8.29, 今开 8.00 -> 涨)
            dlg._update_unified_realtime_log(
                df_bars=pd.DataFrame({"close": [8.00, 8.29]}),
                op=8.00,
                p=8.29,
                vw=8.25,
                hi=8.29,
                lo=7.99,
                to_rate=9.09,
                amt=3.19e8,
                sigs=[],
                mode="10d"
            )
            html_txt = dlg.txt_log.toHtml()
            # 断言包含红色涨幅和绿色极值
            self.assertIn("#ff4444", html_txt)
            self.assertIn("#00ff88", html_txt)
            # 断言纯文本解析仍然保留指标完整性
            plain_txt = dlg.txt_log.toPlainText()
            self.assertIn("【实时量价基准】", plain_txt)
            self.assertIn("8.29元", plain_txt)
        finally:
            dlg.close()

    def test_sbc_log_panel_s_shortcut_and_ad_period_switch(self):
        """测试 SBC 日志面板 S 快捷键展开/收起，以及 A/D 键切换上一个/下一个周期"""
        from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
        dlg = SBCIntradayChartDialog(code="600630")
        try:
            # 1. 验证默认不开启日志（收起隐藏）
            self.assertTrue(dlg.log_box.isHidden())
            self.assertEqual(dlg.btn_toggle_log.text(), "📋 日志 (关)")
            self.assertIn("快捷键: S 键", dlg.btn_toggle_log.toolTip())

            # 2. 验证 _shortcut_s, _shortcut_a, _shortcut_d 存在
            self.assertIsNotNone(dlg._shortcut_s)
            self.assertIsNotNone(dlg._shortcut_a)
            self.assertIsNotNone(dlg._shortcut_d)

            # 3. 模拟调用 _toggle_log_panel (展开与收起)
            dlg._toggle_log_panel()
            self.assertFalse(dlg.log_box.isHidden())
            self.assertEqual(dlg.btn_toggle_log.text(), "📋 日志 (开)")

            dlg._toggle_log_panel()
            self.assertTrue(dlg.log_box.isHidden())
            self.assertEqual(dlg.btn_toggle_log.text(), "📋 日志 (关)")

            # 4. 测试 A 键切上一周期，D 键切下一周期
            dlg.set_period_mode("1m", reload=False, save=False)
            self.assertEqual(dlg._current_period_mode, "1m")

            # 按 D 切换下一个周期 -> 5d
            dlg._on_shortcut_d_activated()
            self.assertEqual(dlg._current_period_mode, "5d")

            # 再按 D 切换下一个周期 -> 10d
            dlg._on_shortcut_d_activated()
            self.assertEqual(dlg._current_period_mode, "10d")

            # 按 A 切换上一个周期 -> 5d
            dlg._on_shortcut_a_activated()
            self.assertEqual(dlg._current_period_mode, "5d")

            # 再按 A 切换上一个周期 -> 1m
            dlg._on_shortcut_a_activated()
            self.assertEqual(dlg._current_period_mode, "1m")
        finally:
            dlg.close()

    def test_sbc_escape_key_does_not_close_window(self):
        """测试 SBC 窗口与画布取消 Esc 退出窗口功能"""
        from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent, Qt
        from unittest.mock import MagicMock

        dlg = SBCIntradayChartDialog(code="600630")
        try:
            close_mock = MagicMock()
            dlg.close = close_mock

            # 模拟在对话框上按 Esc 键
            esc_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
            dlg.keyPressEvent(esc_event)
            close_mock.assert_not_called()

            # 模拟在画布上按 Esc 键
            dlg.canvas.keyPressEvent(esc_event)
            close_mock.assert_not_called()
        finally:
            del dlg.close
            dlg.close()

    def test_daily_limit_up_time_slice_persistence(self):
        target_slice = "⏱️ 全天全时段"
        save_config_node("daily_limitup_time_slice", target_slice)

        dlg = DailyLimitUpDialog(parent=None)
        try:
            self.assertEqual(dlg.combo_time_slice.currentText(), target_slice)

            new_target = "🚀 早盘进攻 (09:30-10:00)"
            idx = dlg.combo_time_slice.findText(new_target)
            self.assertGreaterEqual(idx, 0)
            dlg.combo_time_slice.setCurrentIndex(idx)

            saved = load_config_node("daily_limitup_time_slice", "")
            self.assertEqual(saved, new_target)
        finally:
            save_config_node("daily_limitup_time_slice", "⏱️ 全天全时段")
            dlg.close()

    def test_hot_sector_leaderboard_time_slice_persistence(self):
        target_slice = "⏱️ 全天全时段"
        save_config_node("hot_leaderboard_time_slice", target_slice)

        dlg = HotSectorLeaderboardDialog(parent=None)
        try:
            self.assertEqual(dlg.combo_time_slice.currentText(), target_slice)

            new_target = "👑 09:30~10:00 黄金定龙"
            idx = dlg.combo_time_slice.findText(new_target)
            self.assertGreaterEqual(idx, 0)
            dlg.combo_time_slice.setCurrentIndex(idx)

            saved = load_config_node("hot_leaderboard_time_slice", "")
            self.assertEqual(saved, new_target)
        finally:
            save_config_node("hot_leaderboard_time_slice", "⏱️ 全天全时段")
            dlg.close()


if __name__ == '__main__':
    unittest.main()
