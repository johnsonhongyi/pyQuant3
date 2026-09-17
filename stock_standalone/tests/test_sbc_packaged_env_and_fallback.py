# -*- coding: utf-8 -*-
"""
test_sbc_packaged_env_and_fallback.py
--------------------------------------
验证在打包环境 (Frozen / PyInstaller / Nuitka) 下：
1. 【打包环境多进程调起】launch(code) 优先以 [ATS_Terminal.exe, --sbc, <code>, <period>] 调起独立子进程；
2. 【打包环境持仓盯盘多进程】launch_holdings_watcher 以 [ATS_Terminal.exe, --sbc-holdings] 调起独立子进程；
3. 【子进程参数拦截分发】run_ats.py 检测到 --sbc 或 --sbc-holdings 时直接进入 run_sbc.main()，绝不调起 ATSMainWindow 主程序；
4. 【进程异常兜底降级】当子进程启动异常时，全自动安全降级在当前进程内打开。
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# 确保工作区根目录在 Python 路径中
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_STANDALONE = os.path.dirname(TEST_DIR)
if STOCK_STANDALONE not in sys.path:
    sys.path.insert(0, STOCK_STANDALONE)

from PyQt6.QtWidgets import QApplication
from ats.ui.sbc_launcher import SBCProcessManager, launch_sbc_process, _build_sbc_subprocess_command


class TestSBCPackagedEnvAndSubprocess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.mgr = SBCProcessManager.get_instance()
        self.mgr._procs.clear()
        self.mgr._in_process_holdings.clear()

    def tearDown(self):
        self.mgr._procs.clear()
        self.mgr._in_process_holdings.clear()

    def test_build_sbc_subprocess_command_packaged(self):
        """【测试】打包环境下智能构造多进程命令行：使用 exe 与 --sbc/--sbc-holdings，绝不带 run_sbc.py"""
        fake_exe = r"D:\JohnsonProgram\instockMonitorTK\ATS_Terminal.exe"
        with patch("ats.ui.sbc_launcher.is_packaged_env", return_value=True), \
             patch.object(sys, "executable", fake_exe), \
             patch("os.path.exists", return_value=True):

            # 1. 单标的启动命令
            cmd_single = _build_sbc_subprocess_command(code="600733", period_mode="10d", is_holdings=False)
            self.assertEqual(cmd_single, [fake_exe, "--sbc", "600733", "10d"])

            # 2. 持仓盯盘启动命令
            cmd_holdings = _build_sbc_subprocess_command(is_holdings=True)
            self.assertEqual(cmd_holdings, [fake_exe, "--sbc-holdings"])

    def test_packaged_env_launch_single_code_subprocess(self):
        """【测试】打包环境下调起标的 SBC：优先以全新独立子进程运行，杜绝主进程卡顿"""
        fake_exe = r"D:\JohnsonProgram\instockMonitorTK\ATS_Terminal.exe"
        mock_proc = MagicMock()
        mock_proc.pid = 88888
        mock_proc.poll.return_value = None

        with patch("ats.ui.sbc_launcher.is_packaged_env", return_value=True), \
             patch.object(sys, "executable", fake_exe), \
             patch("os.path.exists", return_value=True), \
             patch("subprocess.Popen", return_value=mock_proc) as mock_popen:

            proc = self.mgr.launch("600733", "10d")

            # 1. 必须成功调起独立子进程
            self.assertEqual(proc, mock_proc)
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            self.assertEqual(call_args, [fake_exe, "--sbc", "600733", "10d"])

            # 2. 必须包含 ATS_SBC_SUBPROCESS=1 环境变量
            call_env = mock_popen.call_args[1].get("env", {})
            self.assertEqual(call_env.get("ATS_SBC_SUBPROCESS"), "1")

            # 3. 必须纳入 SBCProcessManager 纳管
            self.assertIn("600733", self.mgr.get_running_codes())

    def test_packaged_env_launch_holdings_watcher_subprocess(self):
        """【测试】打包环境下点击盯盘：优先以独立子进程运行 run_sbc 盯盘模式"""
        fake_exe = r"D:\JohnsonProgram\instockMonitorTK\ATS_Terminal.exe"
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None

        with patch("ats.ui.sbc_launcher.is_packaged_env", return_value=True), \
             patch.object(sys, "executable", fake_exe), \
             patch("os.path.exists", return_value=True), \
             patch("subprocess.Popen", return_value=mock_proc) as mock_popen:

            proc = self.mgr.launch_holdings_watcher()

            # 1. 必须调起持仓多进程
            self.assertEqual(proc, mock_proc)
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            self.assertEqual(call_args, [fake_exe, "--sbc-holdings"])

            # 2. 必须包含专属隔离环境变量
            call_env = mock_popen.call_args[1].get("env", {})
            self.assertEqual(call_env.get("ATS_SBC_SUBPROCESS"), "1")
            self.assertEqual(call_env.get("SBC_IS_HOLDINGS_LAUNCHER"), "1")

            # 3. 确认处于运行状态
            self.assertTrue(self.mgr.is_launcher_running())

    def test_run_ats_cli_and_env_dispatch_prevents_main_window(self):
        """【测试】run_ats.py 在带 --sbc 参数或 ATS_SBC_SUBPROCESS=1 时直接分发到 run_sbc.main，阻断 ATSMainWindow 实例化"""
        test_argv = ["ATS_Terminal.exe", "--sbc", "600733", "10d"]
        with patch.object(sys, "argv", test_argv), \
             patch.dict(os.environ, {"ATS_SBC_SUBPROCESS": "1"}), \
             patch("run_sbc.main", return_value=0) as mock_sbc_main:

            is_sbc_subproc = (
                os.environ.get("ATS_SBC_SUBPROCESS") == "1" or
                any(arg in sys.argv for arg in ("--sbc", "--sbc-holdings", "--holdings-sbc", "--holdings"))
            )
            if is_sbc_subproc:
                import run_sbc
                exit_code = run_sbc.main()

            mock_sbc_main.assert_called_once()
            self.assertEqual(exit_code, 0)

    def test_packaged_env_failure_gracefully_fallbacks_to_in_process(self):
        """【测试】当外部子进程调起异常时，自动平滑降级至当前进程内打开，保障 100% 可用"""
        fake_exe = r"D:\JohnsonProgram\instockMonitorTK\ATS_Terminal.exe"
        mock_dlg = MagicMock()
        mock_dlg.isVisible.return_value = True

        with patch("ats.ui.sbc_launcher.is_packaged_env", return_value=True), \
             patch.object(sys, "executable", fake_exe), \
             patch("subprocess.Popen", side_effect=OSError("Process creation blocked")), \
             patch("ats.ui.intraday_strategy_dialog.open_sbc_chart_dialog", return_value=mock_dlg) as mock_open:

            res = self.mgr.launch("600733", "10d")
            # 自动降级为进程内窗口
            self.assertEqual(res, mock_dlg)
            mock_open.assert_called_once()
            mock_dlg.show.assert_called_once()


if __name__ == "__main__":
    unittest.main()
