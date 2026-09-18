# -*- coding: utf-8 -*-
"""
tests/test_sbc_tooltip_styling.py
---------------------------------
验证 SBC 走势窗口 (SBCIntradayChartDialog) 及独立启动器 (run_sbc)
鼠标悬浮周期切换按钮及各控件时，QToolTip 配色符合暗黑金融质感高对比规范，
彻底消除白底白字、背景刺眼不可读缺陷。
"""

import sys
import os
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, AllCodesStrategyEvalDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestSBCToolTipStyling:
    """SBC 窗口鼠标悬停 ToolTip 样式与调色板高对比度测试集"""

    def test_sbc_dialog_tooltip_stylesheet(self, qapp):
        """测试 SBC 走势窗口自身样式表中包含 QToolTip 高对比暗黑规则"""
        dialog = SBCIntradayChartDialog(code="600733")
        ss = dialog.styleSheet()

        assert "QToolTip" in ss, "SBCIntradayChartDialog 样式表中必须显式定义 QToolTip 样式规则"
        assert "#14141f" in ss or "background-color" in ss
        assert "#f1f5f9" in ss
        assert "#38bdf8" in ss

        pal = dialog.palette()
        base_color = pal.color(QPalette.ColorRole.ToolTipBase)
        text_color = pal.color(QPalette.ColorRole.ToolTipText)
        assert base_color.name() == "#14141f", f"ToolTipBase 应为暗黑科技深底 #14141f，实际为 {base_color.name()}"
        assert text_color.name() == "#f1f5f9", f"ToolTipText 应为高亮文本 #f1f5f9，实际为 {text_color.name()}"

        dialog.close()

    def test_period_buttons_have_tooltip_text(self, qapp):
        """测试所有周期切换按钮均已配置语义清晰的 ToolTip 提示"""
        dialog = SBCIntradayChartDialog(code="600733")
        buttons = dialog.btn_group_period.buttons()
        assert len(buttons) >= 10, f"周期按钮数量应不少于 10 个，实际: {len(buttons)}"

        modes_found = []
        for btn in buttons:
            mode = btn.property("period_mode")
            modes_found.append(mode)
            tip = btn.toolTip()
            assert tip, f"周期按钮 [{btn.text()}] 未配置 ToolTip"
            assert btn.text() in tip or mode in tip, f"Tooltip 文本应包含周期信息: {tip}"

        for expected in ["1m", "5d", "10d", "3d", "day"]:
            assert expected in modes_found, f"必须包含 {expected} 周期按钮"

        dialog.close()

    def test_all_codes_eval_dialog_tooltip_stylesheet(self, qapp):
        """测试全量策略评估报告窗口包含 QToolTip 样式规则"""
        from PyQt6.QtWidgets import QWidget
        fake_parent = QWidget()
        fake_parent.engine = None
        dialog = AllCodesStrategyEvalDialog(fake_parent)
        ss = dialog.styleSheet()

        assert "QToolTip" in ss, "AllCodesStrategyEvalDialog 样式表中必须定义 QToolTip"
        assert "#14141f" in ss
        assert "#f1f5f9" in ss

        dialog.close()

    def test_app_palette_tooltip_roles(self, qapp):
        """测试全局 QApplication 调色板已配置暗黑 ToolTip 角色"""
        pal = qapp.palette()
        base_color = pal.color(QPalette.ColorRole.ToolTipBase)
        text_color = pal.color(QPalette.ColorRole.ToolTipText)
        assert base_color.name() == "#14141f", f"app ToolTipBase 应为 #14141f，实际为 {base_color.name()}"
        assert text_color.name() == "#f1f5f9", f"app ToolTipText 应为 #f1f5f9，实际为 {text_color.name()}"
