# -*- coding: utf-8 -*-
"""
专项自动化测试：
1. 验证新股次新超短检测工具 (NewStockDetectorDialog) 输入框右键菜单支持粘贴股票代码、一键粘贴并添加等功能；
2. 验证在 ATS 模式下打开的 SBC 窗口按住 Alt 键点击关闭 [X] 或按 Alt+X 快捷键时，严格忽略 --sbc-holdings 模式的全部退出持久化，仅安全关闭当前单个窗口。
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# 项目根目录
root_dir = str(Path(__file__).resolve().parents[1])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import pytest
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QCloseEvent, QKeyEvent

app = QApplication.instance() or QApplication(sys.argv)


def test_detector_txt_code_context_menu_and_paste():
    """测试新股次新超短检测工具输入框右键菜单与粘贴功能"""
    from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
    dlg = IPOSubnewDetectorDialog()

    # 1. 验证输入框已启用自定义右键菜单策略
    assert dlg.txt_code.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    # 2. 模拟剪贴板中有代码 "301171"
    QApplication.clipboard().setText("关注 301171 德石股份 强势股")

    # 3. 验证 _paste_code_to_input 方法
    dlg._paste_code_to_input("301171")
    assert dlg.txt_code.text() == "301171"

    # 4. 验证 _paste_and_add_code 方法
    with patch.object(dlg, "add_stock") as mock_add:
        dlg._paste_and_add_code("301171")
        mock_add.assert_called_once_with("301171")
        # 添加后输入框被清空
        assert dlg.txt_code.text() == ""


def test_sbc_ats_mode_ignores_alt_exit():
    """测试在 ATS 打开的 SBC 模式下，按住 Alt 点击关闭键严格忽略全部退出，仅关闭当前窗口"""
    from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
    
    # 模拟 ATS 主窗口环境
    mock_main = MagicMock(spec=QWidget)
    mock_main.__class__.__name__ = "ATSMainWindow"
    
    # 确保清除 --sbc-holdings 标记
    if "SBC_IS_HOLDINGS_LAUNCHER" in os.environ:
        del os.environ["SBC_IS_HOLDINGS_LAUNCHER"]

    sbc_win = SBCIntradayChartDialog(parent=mock_main, code="001212")
    assert sbc_win.is_ats_sbc_mode() is True

    # 模拟 Alt 按下时触发 closeEvent
    with patch("PyQt6.QtWidgets.QApplication.keyboardModifiers", return_value=Qt.KeyboardModifier.AltModifier):
        with patch("run_sbc.quit_and_save_all_sbc_windows") as mock_quit_all:
            with patch.object(app, "quit") as mock_app_quit:
                ev = QCloseEvent()
                sbc_win.closeEvent(ev)
                
                # 核心断言：绝不能调用 quit_and_save_all_sbc_windows，绝不能 app.quit()
                mock_quit_all.assert_not_called()
                mock_app_quit.assert_not_called()
                assert ev.isAccepted() is True


def test_sbc_ats_mode_alt_x_shortcut_guard():
    """测试在 ATS 打开的 SBC 模式下，按 Alt+X 快捷键严格忽略全部退出，仅单窗口关闭"""
    from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
    mock_main = MagicMock(spec=QWidget)
    mock_main.__class__.__name__ = "ATSMainWindow"

    if "SBC_IS_HOLDINGS_LAUNCHER" in os.environ:
        del os.environ["SBC_IS_HOLDINGS_LAUNCHER"]

    sbc_win = SBCIntradayChartDialog(parent=mock_main, code="600030")
    assert sbc_win.is_ats_sbc_mode() is True

    with patch("run_sbc.quit_and_save_all_sbc_windows") as mock_quit_all:
        with patch.object(app, "quit") as mock_app_quit:
            with patch.object(sbc_win, "close") as mock_single_close:
                # 触发 Alt+X
                key_ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.AltModifier)
                sbc_win.keyPressEvent(key_ev)

                # 断言：单窗口关闭被调用，全局退出未被调用
                mock_single_close.assert_called_once()
                mock_quit_all.assert_not_called()
                mock_app_quit.assert_not_called()


def test_sbc_holdings_launcher_mode_allows_alt_exit():
    """测试在真正的 --sbc-holdings 启动器模式下，按住 Alt 点击关闭键依然支持全部退出持久化"""
    from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog

    os.environ["SBC_IS_HOLDINGS_LAUNCHER"] = "1"
    try:
        sbc_win = SBCIntradayChartDialog(parent=None, code="000001")
        sbc_win._is_ats_mode = False

        with patch("PyQt6.QtWidgets.QApplication.keyboardModifiers", return_value=Qt.KeyboardModifier.AltModifier):
            with patch("run_sbc.quit_and_save_all_sbc_windows") as mock_quit_all:
                with patch.object(app, "quit") as mock_app_quit:
                    ev = QCloseEvent()
                    sbc_win.closeEvent(ev)

                    # 断言：在 holdings 模式下，Alt 关闭会调用全部退出
                    mock_quit_all.assert_called_once()
                    assert ev.isAccepted() is True
    finally:
        if "SBC_IS_HOLDINGS_LAUNCHER" in os.environ:
            del os.environ["SBC_IS_HOLDINGS_LAUNCHER"]
