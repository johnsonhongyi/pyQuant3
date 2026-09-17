# -*- coding: utf-8 -*-
"""
SBC 统一 ATS 内部原生打开与恢复专项测试
验证目标:
1. restore_all_open_sbc_windows 彻底使用 ATS 内部原生 open_sbc_chart_dialog 方式恢复;
2. 即使传入 as_subprocess=True，也绝不调用外部子进程 launch_sbc_process，彻底根除双分组混乱;
3. 重启恢复后的窗口与手动打开的窗口完全同源，rearrange_all_sbc_windows 可 100% 统一精准识别与规范重排.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, mock_open
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

from ats.ui.intraday_strategy_dialog import (
    restore_all_open_sbc_windows,
    rearrange_all_sbc_windows,
    _SBCWindowProxy,
    _get_sbc_layout_cfg_path,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestSBCInProcessUnifiedRestore:

    def test_restore_all_open_sbc_windows_strictly_in_process(self, qapp):
        """测试 restore_all_open_sbc_windows 严格在当前进程内恢复，绝不调起外部子进程"""
        mock_data = {
            "sbc_open_windows": [
                {"code": "600733", "x": 100, "y": 100, "width": 800, "height": 500, "period_mode": "10d"},
                {"code": "688826", "x": 920, "y": 100, "width": 800, "height": 500, "period_mode": "5m"}
            ]
        }
        json_str = json.dumps(mock_data)

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json_str)), \
             patch("ats.ui.intraday_strategy_dialog.open_sbc_chart_dialog") as mock_open_dlg, \
             patch("ats.ui.sbc_launcher.launch_sbc_process") as mock_launch_subproc:

            mock_dlg1 = MagicMock()
            mock_dlg2 = MagicMock()
            mock_open_dlg.side_effect = [mock_dlg1, mock_dlg2]

            # 1. 显式传入 as_subprocess=True 测试
            res = restore_all_open_sbc_windows(parent_win=None, as_subprocess=True)

            # 严格断言: 绝对没有调起外部子进程 launch_sbc_process
            mock_launch_subproc.assert_not_called()

            # 严格断言: 必须在进程内通过 open_sbc_chart_dialog 恢复
            assert mock_open_dlg.call_count == 2
            assert len(res) == 2

    def test_restore_dialogs_unified_with_manual_dialogs_for_rearrange(self, qapp):
        """测试恢复的窗口与手动打开的窗口同源同组，重排统一识别且执行正常限制"""
        dlg1 = MagicMock()
        dlg1.isVisible.return_value = True
        dlg1.isMaximized.return_value = False
        dlg1.isMinimized.return_value = False
        dlg1.isFullScreen.return_value = False
        dlg1.width.return_value = 800
        dlg1.height.return_value = 600
        dlg1.code = "600733"

        applied = []
        dlg1.apply_geometry = lambda x, y, w, h, activate=False: applied.append((x, y, w, h))

        pxy1 = _SBCWindowProxy(dlg=dlg1)
        pxy1.apply_geometry = dlg1.apply_geometry
        pxy1.get_geometry = MagicMock(return_value=QRect(100, 100, 800, 600))
        pxy1.is_maximized_or_minimized = MagicMock(return_value=False)
        pxy1.show_normal = MagicMock()

        mock_parent = MagicMock()
        mock_parent._sbc_dialogs = {"600733": dlg1}

        with patch("ats.ui.intraday_strategy_dialog._SBCWindowProxy", return_value=pxy1), \
             patch("ats.ui.intraday_strategy_dialog.save_all_open_sbc_windows"):
            rearrange_all_sbc_windows(parent_win=mock_parent)

        assert len(applied) > 0
        x, y, w, h = applied[-1]
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            # 单窗口重排严格受限在半屏宽与 65% 高度内，绝不全屏霸屏
            assert w <= int(sg.width() * 0.6)
            assert h <= int(sg.height() * 0.65)
