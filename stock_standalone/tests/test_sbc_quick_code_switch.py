# -*- coding: utf-8 -*-
"""
tests/test_sbc_quick_code_switch.py
-----------------------------------
SBC 独立走势窗口底部快速切换股票代码与右键自动粘贴 6 位代码单元测试套件
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

CURR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURR_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent

# 保证 QApplication 单例存在
app = QApplication.instance()
if app is None:
    app = QApplication([])

from ats.ui.intraday_strategy_dialog import SBCQuickCodeLineEdit, SBCIntradayChartDialog


class TestSBCQuickCodeSwitch(unittest.TestCase):
    """SBC 底部代码输入与右键自动粘贴切换测试套件"""

    def setUp(self):
        self.line_edit = SBCQuickCodeLineEdit()
        self.submitted_codes = []
        self.line_edit.code_submitted.connect(lambda c: self.submitted_codes.append(c))

    def tearDown(self):
        self.line_edit.deleteLater()

    def test_01_clipboard_extraction_patterns(self):
        """测试不同格式文本下的 6 位代码智能提取能力 (extract_code)"""
        test_cases = [
            ("600519", "600519"),
            ("sh688635", "688635"),
            ("SZ000001", "000001"),
            ("天智航(688277)", "688277"),
            ("长进光子 688635 实盘走势", "688635"),
            ("300750\t宁德时代\t215.30", "300750"),
            ("代码：002594，请关注", "002594"),
            ("长进光子", "688635"),
        ]

        for raw_text, expected_code in test_cases:
            extracted = SBCQuickCodeLineEdit.extract_code(raw_text)
            self.assertEqual(extracted, expected_code, f"未能从 '{raw_text}' 中正确提取 6 位代码，预期: {expected_code}, 实际: {extracted}")

    def test_02_clipboard_empty_or_invalid(self):
        """测试文本为空或不包含合法 6 位数字时的安全防护"""
        invalid_cases = [
            "",
            "   ",
            "没有数字的文本",
            None,
        ]

        for text in invalid_cases:
            extracted = SBCQuickCodeLineEdit.extract_code(text)
            self.assertIsNone(extracted, f"空或纯中文文本不应提取出代码: {text}")

    def test_03_return_pressed_submission(self):
        """测试手动在输入框输入代码并按回车提交"""
        self.line_edit.setText("601398")
        self.line_edit._on_return_pressed()
        self.assertEqual(self.submitted_codes, ["601398"])

        # 测试输入少于 6 位时自动补齐
        self.submitted_codes.clear()
        self.line_edit.setText("733")
        self.line_edit._on_return_pressed()
        self.assertEqual(self.submitted_codes, ["000733"])

    def test_04_mouse_right_click_auto_paste(self):
        """测试鼠标右键点击自动读取剪贴板 6 位代码并直接触发提交切换"""
        from PyQt6.QtCore import QPointF

        # 构造鼠标右键点击事件
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(10.0, 10.0),
            QPointF(10.0, 10.0),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier
        )

        with patch.object(self.line_edit, '_extract_code_from_clipboard', return_value="688635"):
            self.line_edit.mousePressEvent(event)
            self.assertEqual(self.line_edit.text(), "688635", "右键应自动将 6 位代码填入输入框")
            self.assertEqual(self.submitted_codes, ["688635"], "右键应自动发射 code_submitted 信号")

    def test_05_dialog_switch_code_integration(self):
        """测试 SBCIntradayChartDialog 调用 switch_code 后的状态更新与安全重载"""
        dialog = SBCIntradayChartDialog(code="600733")
        self.assertEqual(dialog.code, "600733")
        self.assertIsNotNone(dialog.txt_switch_code)
        # 输入框直观显示 '代码 股票名称'
        self.assertIn("600733", dialog.txt_switch_code.text())
        self.assertEqual(dialog.txt_switch_code.text(), dialog._format_code_with_name("600733"))

        # Mock reload_chart 避免网络请求
        with patch.object(dialog, 'reload_chart') as mock_reload:
            dialog.switch_code("688635")

            self.assertEqual(dialog.code, "688635")
            self.assertEqual(dialog.canvas.code, "688635")
            self.assertIn("688635", dialog.windowTitle())
            self.assertEqual(dialog.txt_switch_code.text(), dialog._format_code_with_name("688635"))
        # 测试下拉框组件存在且包含当前标的
        self.assertIsNotNone(dialog.combo_switch_code)
        self.assertGreaterEqual(dialog.combo_switch_code.count(), 1)
        first_item_text = dialog.combo_switch_code.itemText(0)
        self.assertIn("688635", first_item_text)

        dialog.deleteLater()

    def test_06_recent_codes_persistence_and_lru(self):
        """测试 _save_sbc_recent_code 与 _load_sbc_recent_codes 的 LRU 10 个容量与新项置顶逻辑"""
        from ats.ui.intraday_strategy_dialog import _save_sbc_recent_code, _load_sbc_recent_codes
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_cfg = os.path.join(tmp_dir, "test_ui_layout.json")
            with patch('ats.ui.intraday_strategy_dialog._get_sbc_layout_cfg_path', return_value=test_cfg):
                # 连续插入 12 个不同 6 位股票代码 (600000 ~ 600011)
                test_codes = [f"{600000 + i:06d}" for i in range(12)]
                for c in test_codes:
                    _save_sbc_recent_code(c)

                loaded = _load_sbc_recent_codes()
                # 必须严格限制在 10 个
                self.assertEqual(len(loaded), 10, f"最近代码列表应限制在 10 个以内，实际: {len(loaded)}")
                # 最新插入的应排在首位
                self.assertEqual(loaded[0], "600011")
                self.assertEqual(loaded[1], "600010")

                # 重复插入已存在的代码 (例如 600005)，应将其提至首位而不会重复累加
                _save_sbc_recent_code("600005")
                loaded_after_dup = _load_sbc_recent_codes()
                self.assertEqual(len(loaded_after_dup), 10)
                self.assertEqual(loaded_after_dup[0], "600005")

    def test_07_combo_recent_codes_display_and_activation(self):
        """测试 SBCIntradayChartDialog 下拉选择最近标的并切换，且显示股票名称"""
        from sys_utils import resolve_stock_name

        dialog = SBCIntradayChartDialog(code="600519")
        dialog.show()

        # 检查下拉列表中是否包含股票名称
        combo = dialog.combo_switch_code
        self.assertIsNotNone(combo)
        self.assertGreaterEqual(combo.count(), 1)
        first_text = combo.itemText(0)
        self.assertTrue("600519" in first_text)
        expected_name = resolve_stock_name("600519")
        if expected_name and expected_name != "600519":
            self.assertTrue(expected_name in first_text, f"下拉列表显示应包含股票名称: {expected_name} in {first_text}")

        # 模拟用户从下拉框中选择第 0 项或其它项
        with patch.object(dialog, 'switch_code') as mock_switch:
            dialog._on_combo_code_activated(0)
            mock_switch.assert_called_with("600519")

        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
