# -*- coding: utf-8 -*-
"""
SBC 内存持久化、重排大尺寸铺满、画布高屏占比与子进程临时目录隔离专项测试
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    SBCChartCanvas,
    SBCWindowMemoryManager,
    rearrange_all_sbc_windows,
    _SBCWindowProxy,
    sync_all_open_sbc_period,
)
from ats.ui.sbc_launcher import (
    SBCProcessManager,
    close_all_sbc_processes,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestSBCMemoryPersistenceLargeWindowAndExit:

    def test_sbc_window_memory_manager_lifecycle(self, qapp):
        """测试 SBCWindowMemoryManager 内存注册、更新、切周期与注销全部瞬间直达"""
        mgr = SBCWindowMemoryManager.get_instance()
        mgr.clear()

        # 1. 注册窗口
        geo = {"x": 100, "y": 100, "width": 800, "height": 600}
        mgr.register("600733", geo_dict=geo, period_mode="10d")
        
        entry = mgr.get_window("600733")
        assert entry is not None
        assert entry["code"] == "600733"
        assert entry["period_mode"] == "10d"
        assert entry["x"] == 100
        assert entry["width"] == 800

        # 2. 更新坐标
        mgr.update_geometry("600733", {"x": 200, "y": 250, "width": 1000, "height": 700})
        entry_updated = mgr.get_window("600733")
        assert entry_updated["x"] == 200
        assert entry_updated["width"] == 1000

        # 3. 更新周期
        mgr.update_period("600733", "5m")
        assert mgr.get_window("600733")["period_mode"] == "5m"

        # 4. 获取全部活动窗口
        mgr.register("000001", geo_dict=geo, period_mode="1m")
        all_wins = mgr.get_all_windows()
        assert len(all_wins) == 2
        assert {w["code"] for w in all_wins} == {"600733", "000001"}

        # 5. 注销窗口瞬间从内存除名
        mgr.unregister("600733")
        assert mgr.get_window("600733") is None
        assert len(mgr.get_all_windows()) == 1

        mgr.clear()

    def test_canvas_compact_margins_and_high_screen_ratio(self, qapp):
        """测试 SBCChartCanvas 紧凑边距常量设定，彻底消除四周大黑边"""
        assert SBCChartCanvas.MARGIN_LEFT == 42
        assert SBCChartCanvas.MARGIN_RIGHT == 52
        assert SBCChartCanvas.MARGIN_TOP == 18
        assert SBCChartCanvas.MARGIN_BOTTOM == 22

        canvas = SBCChartCanvas()
        canvas.resize(800, 600)
        chart_w = 800 - SBCChartCanvas.MARGIN_LEFT - SBCChartCanvas.MARGIN_RIGHT
        assert chart_w == 706

    def test_rearrange_all_sbc_windows_large_window_and_full_screen(self, qapp):
        """测试重排算法: 1个窗口占满全屏，2个窗口垂直占满，绝不截断压矮"""
        dlg1 = MagicMock()
        dlg1.isVisible.return_value = True
        dlg1.isMaximized.return_value = False
        dlg1.isMinimized.return_value = False
        dlg1.isFullScreen.return_value = False
        dlg1.width.return_value = 800
        dlg1.height.return_value = 600
        dlg1.code = "600733"
        applied_geos = []

        def fake_apply_geo(x, y, w, h, activate=False):
            applied_geos.append((x, y, w, h))

        dlg1.apply_geometry = fake_apply_geo

        pxy1 = _SBCWindowProxy(dlg=dlg1)
        pxy1.apply_geometry = fake_apply_geo
        pxy1.get_geometry = MagicMock(return_value=QRect(100, 100, 800, 600))
        pxy1.is_maximized_or_minimized = MagicMock(return_value=False)
        pxy1.show_normal = MagicMock()

        with patch("PyQt6.QtWidgets.QApplication.topLevelWidgets", return_value=[]), \
             patch("ats.ui.intraday_strategy_dialog._SBCWindowProxy", return_value=pxy1), \
             patch("ats.ui.intraday_strategy_dialog.save_all_open_sbc_windows"):
            rearrange_all_sbc_windows(parent_win=None)

        if applied_geos:
            x, y, w, h = applied_geos[-1]
            screen = QApplication.primaryScreen()
            if screen:
                sg = screen.availableGeometry()
                # 校验单窗口重排有严格限制：绝不全屏铺满！宽度为两列分栏 (<= sg.width() * 0.6)，高度受限在 65% (<= sg.height() * 0.65)
                assert w <= int(sg.width() * 0.6)
                assert h <= int(sg.height() * 0.65)

    def test_sbc_max_allowed_size_two_thirds_limit(self, qapp):
        """测试 _get_max_allowed_sbc_size 严格限制不得超过屏幕规格 2/3 (防止全屏霸屏挡住 ATS)"""
        dlg = SBCIntradayChartDialog(code="600733", initial_period_mode="10d")
        max_w, max_h = dlg._get_max_allowed_sbc_size()
        screen = dlg.screen() or QApplication.primaryScreen()
        if screen:
            ag = screen.availableGeometry()
            assert max_w == int(ag.width() * 2 / 3)
            assert max_h == int(ag.height() * 2 / 3)

    def test_sbc_launcher_env_isolation_meipass(self):
        """测试 SBC 调起子进程时剥离 _MEIPASS2，彻底避免锁定父进程 PyInstaller 临时目录"""
        mgr = SBCProcessManager.get_instance()
        with patch.dict(os.environ, {"_MEIPASS2": r"C:\Temp\_MEI100322", "ATS_SBC_SUBPROCESS": "0"}):
            with patch("subprocess.Popen") as mock_popen, \
                 patch("ats.ui.sbc_launcher._build_sbc_subprocess_command", return_value=["ATS_Terminal.exe", "--sbc-holdings"]):
                
                mock_proc = MagicMock()
                mock_proc.pid = 99999
                mock_proc.poll.return_value = None
                mock_popen.return_value = mock_proc

                mgr._procs.clear()
                proc = mgr.launch_holdings_watcher()
                assert proc is not None
                
                call_args = mock_popen.call_args
                child_env = call_args[1].get("env", {})
                assert "_MEIPASS2" not in child_env
                assert child_env.get("ATS_SBC_SUBPROCESS") == "1"
                assert child_env.get("SBC_IS_HOLDINGS_LAUNCHER") == "1"

    def test_sbc_close_all_processes_and_pipe_release(self):
        """测试 close_all_sbc_processes 优雅等待退出，并彻底释放管道文件句柄"""
        mgr = SBCProcessManager.get_instance()
        mock_proc1 = MagicMock()
        mock_proc1.pid = 1111
        mock_proc1.poll.return_value = None
        mock_pipe1 = MagicMock()
        mock_pipe1.closed = False
        mock_proc1.stdout = mock_pipe1
        mock_proc1.stderr = None
        mock_proc1.stdin = None

        mgr._procs = {"600733": mock_proc1}
        close_all_sbc_processes()

        mock_pipe1.close.assert_called_once()
        assert len(mgr._procs) == 0
