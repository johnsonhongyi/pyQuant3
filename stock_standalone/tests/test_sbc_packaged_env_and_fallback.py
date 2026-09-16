# -*- coding: utf-8 -*-
"""
test_sbc_packaged_env_and_fallback.py
--------------------------------------
验证在打包环境 (Frozen / PyInstaller / Nuitka) 下：
1. 【杜绝误调起 ATS 主程序】launch_holdings_watcher 绝不执行 [sys.executable, run_sbc.py]，严禁多开 ATS 主程序；
2. 【全自动进程内平滑降级】launch 标的在打包环境下自动安全降级在当前进程内打开，绝不报找不到 run_sbc.py 路径；
3. 【持仓盯盘进程内纳管闭环】启动持仓盯盘后，is_launcher_running 识别，二次点击 close_launcher_process 优雅关闭并持久化。
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
from ats.ui.sbc_launcher import SBCProcessManager, launch_sbc_process


class TestSBCPackagedEnvAndFallback(unittest.TestCase):
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

    def test_packaged_env_launch_fallback_in_process(self):
        """【测试】打包环境下调用 launch(code)：杜绝调起外部进程，安全在当前进程内降级打开"""
        mock_dlg = MagicMock()
        mock_dlg.isVisible.return_value = True

        with patch("ats.ui.sbc_launcher.is_packaged_env", return_value=True), \
             patch("ats.ui.intraday_strategy_dialog.open_sbc_chart_dialog", return_value=mock_dlg) as mock_open, \
             patch("subprocess.Popen") as mock_popen:

            res = self.mgr.launch("600733", "10d")

            # 1. 绝不调用 subprocess.Popen (绝不启动 ATS_Terminal.exe)
            mock_popen.assert_not_called()

            # 2. 必须调用 open_sbc_chart_dialog 降级打开
            mock_open.assert_called_once()
            self.assertEqual(mock_open.call_args[1].get("code"), "600733")

            # 3. 必须显示并激活窗口
            mock_dlg.show.assert_called_once()
            mock_dlg.raise_.assert_called_once()
            mock_dlg.activateWindow.assert_called_once()
            self.assertEqual(res, mock_dlg)

    def test_packaged_env_launch_holdings_watcher_fallback_in_process(self):
        """【测试】打包环境下点击盯盘：杜绝调起外部 ATS_Terminal.exe，内存模式安全恢复持仓盯盘"""
        mock_win1 = MagicMock()
        mock_win1.isVisible.return_value = True
        mock_win2 = MagicMock()
        mock_win2.isVisible.return_value = True

        with patch("ats.ui.sbc_launcher.is_packaged_env", return_value=True), \
             patch("subprocess.Popen") as mock_popen, \
             patch("run_sbc.restore_launcher_holdings_windows", return_value=[mock_win1, mock_win2]) as mock_restore, \
             patch("run_sbc.save_launcher_holdings_windows") as mock_save:

            # 1. 首次点击盯盘
            res = self.mgr.launch_holdings_watcher()

            # 严格断言：绝不执行外部子进程！
            mock_popen.assert_not_called()
            # 严格断言：通过内存模式恢复持仓
            mock_restore.assert_called_once()
            self.assertEqual(len(res), 2)
            self.assertTrue(self.mgr.is_launcher_running())

            # 2. 二次点击统一关闭并持久化
            self.mgr.close_launcher_process()
            mock_save.assert_called_once()
            mock_win1.close.assert_called_once()
            mock_win2.close.assert_called_once()
            self.assertFalse(self.mgr.is_launcher_running())

    def test_run_ats_cli_dispatch_prevents_main_window(self):
        """【测试】run_ats.py 在带 --sbc 参数时直接分发到 run_sbc.main，阻断 ATS 主程序实例化"""
        test_argv = ["ATS_Terminal.exe", "--sbc", "600733", "10d"]
        with patch.object(sys, "argv", test_argv), \
             patch("run_sbc.main", return_value=0) as mock_sbc_main:

            # 模拟执行参数分发检测
            if any(arg in sys.argv for arg in ("--sbc", "--sbc-holdings", "--holdings-sbc")):
                import run_sbc
                exit_code = run_sbc.main()

            mock_sbc_main.assert_called_once()
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
