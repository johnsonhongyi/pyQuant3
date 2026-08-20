# -*- coding: utf-8 -*-
"""
tests/test_sbc_rearrange.py — SBC 窗口网格平铺重排与 ATS 顶层 CornerWidget 按钮专项测试
"""

import sys
import os
import pytest
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import Qt

# 确保项目根路径
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, rearrange_all_sbc_windows
from ats.ui.main_window import ATSMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_top_tabs_corner_widget_structure(qapp):
    """测试 ATS 主窗口 top_tabs 的 CornerWidget 包含 SBC 重排按钮与刷新状态按钮"""
    win = ATSMainWindow()
    try:
        # 1. 断言 top_tabs 存在
        assert hasattr(win, "top_tabs")
        corner_widget = win.top_tabs.cornerWidget(Qt.Corner.TopRightCorner)
        assert corner_widget is not None
        
        # 2. 检查内部按钮
        buttons = corner_widget.findChildren(QPushButton)
        btn_texts = [b.text() for b in buttons]
        
        # 验证包含 [🪟 SBC 重排] 与 [🔄 刷新状态]，且 SBC 重排在前
        assert any("SBC" in t and "重排" in t for t in btn_texts), f"Buttons found: {btn_texts}"
        assert any("刷新状态" in t for t in btn_texts), f"Buttons found: {btn_texts}"
        
        # 检查顺序：SBC 重排按钮在刷新状态按钮之前
        sbc_idx = next(i for i, t in enumerate(btn_texts) if "SBC" in t and "重排" in t)
        refresh_idx = next(i for i, t in enumerate(btn_texts) if "刷新状态" in t)
        assert sbc_idx < refresh_idx, f"Expected SBC rearrange button before refresh button, got indices {sbc_idx}, {refresh_idx}"
        
        # 3. 检查按钮属性与实例绑定
        assert hasattr(win, "btn_rearrange_sbc")
        assert win.btn_rearrange_sbc is not None
        assert "重排" in win.btn_rearrange_sbc.toolTip()

        # 4. 检查主窗口的 rearrange_all_sbc_windows 成员方法可正常调用
        assert hasattr(win, "rearrange_all_sbc_windows")
        assert callable(win.rearrange_all_sbc_windows)
        win.rearrange_all_sbc_windows()
    finally:
        win.close()


def test_rearrange_all_sbc_windows_with_multiple_dialogs(qapp):
    """测试多个 SBC 窗口调用 rearrange_all_sbc_windows 时的网格平铺与磁吸重置"""
    dlg1 = SBCIntradayChartDialog(code="688826")
    dlg2 = SBCIntradayChartDialog(code="002189")
    dlg3 = SBCIntradayChartDialog(code="300570")

    try:
        # 显示窗口
        dlg1.show()
        dlg2.show()
        dlg3.show()
        qapp.processEvents()

        # 模拟设置某些窗口处于磁吸/半隐藏状态
        dlg2.anchor_edge = "right"
        dlg2.is_hidden_state = True
        dlg2.setWindowOpacity(0.5)

        # 执行重排
        rearrange_all_sbc_windows(parent_win=None)
        qapp.processEvents()

        # 验证所有窗口均已重置磁吸半隐藏状态并完全展开
        for dlg in [dlg1, dlg2, dlg3]:
            assert dlg.anchor_edge is None
            assert dlg.is_hidden_state is False
            assert dlg.windowOpacity() == 1.0
            assert dlg.isVisible()

        # 验证所有窗口坐标已成功重排（坐标唯一不重叠）
        positions = [(dlg.x(), dlg.y()) for dlg in [dlg1, dlg2, dlg3]]
        assert len(set(positions)) == 3, f"Expected 3 distinct positions, got {positions}"

    finally:
        dlg1.close()
        dlg2.close()
        dlg3.close()


def test_rearrange_no_active_dialogs_safe(qapp):
    """测试在无可见 SBC 窗口时调用 rearrange_all_sbc_windows 安全返回不抛异常"""
    # 保证没有抛出任何未捕获异常
    rearrange_all_sbc_windows(parent_win=None)
