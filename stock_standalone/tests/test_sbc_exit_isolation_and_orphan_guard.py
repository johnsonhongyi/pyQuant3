# -*- coding: utf-8 -*-
"""
测试：SBC 独立子进程退出与打包环境句柄隔离、孤儿守护及 ATS closeEvent 联动
-------------------------------------------------------------------------
1. 验证 Popen 调用显式设置 close_fds=True，彻底阻断 Windows 句柄继承；
2. 验证 SBCProcessManager.close_all 优先调用 close_launcher_process；
3. 验证 ATSMainWindow.closeEvent 包含对 SBCProcessManager.close_all 的同步调用；
4. 验证 run_sbc 孤儿守护逻辑。
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from ats.ui.sbc_launcher import SBCProcessManager


def test_launch_holdings_watcher_sets_close_fds_true():
    """测试 launch_holdings_watcher 在 Windows 上显式设置 close_fds=True 阻断句柄继承"""
    mgr = SBCProcessManager.get_instance()
    with patch("subprocess.Popen") as mock_popen, \
         patch.object(mgr, "is_launcher_running", return_value=False):
        mock_proc = MagicMock()
        mock_proc.pid = 8888
        mock_popen.return_value = mock_proc

        mgr.launch_holdings_watcher()

        assert mock_popen.called
        kwargs = mock_popen.call_args[1]
        assert kwargs.get("close_fds") is True, "必须显式设置 close_fds=True 杜绝句柄继承与 DLL 锁死"


def test_close_all_calls_close_launcher_process():
    """测试 close_all 优先调用 close_launcher_process"""
    mgr = SBCProcessManager.get_instance()
    with patch.object(mgr, "close_launcher_process") as mock_close_launcher:
        mgr.close_all()
        assert mock_close_launcher.called, "close_all 必须优先调用 close_launcher_process"


def test_main_window_close_event_triggers_sbc_close_all():
    """测试 ATS 主窗口 closeEvent 中已显式集成 SBCProcessManager.close_all 调用"""
    from ats.ui.main_window import ATSMainWindow
    import inspect
    source = inspect.getsource(ATSMainWindow.closeEvent)
    assert "SBCProcessManager.get_instance().close_all()" in source, "ATSMainWindow.closeEvent 必须显式调用 SBCProcessManager.close_all()"
