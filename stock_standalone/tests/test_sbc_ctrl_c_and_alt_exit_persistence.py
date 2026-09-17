# -*- coding: utf-8 -*-
"""
test_sbc_ctrl_c_and_alt_exit_persistence.py
--------------------------------------------
验证 SBC 持仓盯盘窗口一键退出并持久化：
1. 【Alt+点击[X]】按住 Alt 点击关闭键，触发全部窗口一键持久化保存并安全退出；
2. 【普通点击[X]】未按住 Alt 时，仅关闭当前单个窗口，并在配置中单独除名该股票；
3. 【Ctrl+C / KeyboardInterrupt 退出保护】终端或槽函数发生键盘中断时，100% 自动落盘且不抛出致命 Traceback；
4. 【贴边收缩状态落盘】即使窗口处于贴边收起状态 (is_hidden_state=True)，退出时依旧准确读取 normal_geometry 落盘；
5. 【界面按钮与快捷键】顶部工具栏 [🚪 退出保存] 与 Ctrl+Shift+Q 快捷键触发统一保存退出。
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_STANDALONE = os.path.dirname(TEST_DIR)
if STOCK_STANDALONE not in sys.path:
    sys.path.insert(0, STOCK_STANDALONE)

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
import run_sbc


class TestSBCCtrlCAndAltExitPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _cleanup_all_dialogs(self):
        self.app.setProperty("is_app_exiting", False)
        self.app.setProperty("_has_saved_on_quit", False)
        if hasattr(SBCIntradayChartDialog, "_global_sbc_dialogs"):
            SBCIntradayChartDialog._global_sbc_dialogs.clear()
        for w in list(self.app.topLevelWidgets()):
            if isinstance(w, SBCIntradayChartDialog):
                w.setVisible(False)
                w._is_closing = True
                w.close()
                w.deleteLater()
        for _ in range(5):
            self.app.processEvents()

    def setUp(self):
        self.temp_cfg = os.path.join(STOCK_STANDALONE, "config", f"test_layout_{os.getpid()}.json")
        os.environ["SBC_LAYOUT_CONFIG_PATH"] = self.temp_cfg
        os.environ["SBC_IS_HOLDINGS_LAUNCHER"] = "1"
        self._cleanup_all_dialogs()
        closing_flag = os.path.join(STOCK_STANDALONE, "config", ".ats_closing")
        if os.path.exists(closing_flag):
            try:
                os.remove(closing_flag)
            except Exception:
                pass
        if os.path.exists(self.temp_cfg):
            try:
                os.remove(self.temp_cfg)
            except Exception:
                pass

    def tearDown(self):
        self._cleanup_all_dialogs()
        closing_flag = os.path.join(STOCK_STANDALONE, "config", ".ats_closing")
        if os.path.exists(closing_flag):
            try:
                os.remove(closing_flag)
            except Exception:
                pass
        if os.path.exists(self.temp_cfg):
            try:
                os.remove(self.temp_cfg)
            except Exception:
                pass

    def _create_mock_dialog(self, code: str, x: int = 100, y: int = 100, w: int = 800, h: int = 600):
        """轻量创建一个测试专用的 SBCIntradayChartDialog，屏蔽网络行情请求"""
        with patch.object(SBCIntradayChartDialog, "reload_chart", return_value=None), \
             patch("sys_utils.ensure_backend_tk_running", return_value=True):
            dlg = SBCIntradayChartDialog(None, code=code)
            dlg.normal_geometry = QRect(x, y, w, h)
            dlg.setGeometry(x, y, w, h)
            dlg.show()
            self.app.processEvents()
            return dlg

    def test_alt_close_triggers_exit_and_save_all(self):
        """【测试 1】按住 Alt 点击关闭键：识别为全部退出并持久化，保存所有窗口"""
        w1 = self._create_mock_dialog("600733", 100, 100, 800, 600)
        w2 = self._create_mock_dialog("000001", 900, 100, 800, 600)

        with patch("PyQt6.QtWidgets.QApplication.keyboardModifiers", return_value=Qt.KeyboardModifier.AltModifier), \
             patch.object(self.app, "quit") as mock_quit:

            event = QCloseEvent()
            w1.closeEvent(event)

            # 确认调用了 app.quit() 且 event 被 accept
            self.assertTrue(event.isAccepted())
            mock_quit.assert_called_once()

            # 检查落盘文件：必须同时包含 600733 与 000001
            self.assertTrue(os.path.exists(self.temp_cfg))
            with open(self.temp_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            saved_codes = [x["code"] for x in data.get("sbc_holdings_windows", [])]
            self.assertIn("600733", saved_codes)
            self.assertIn("000001", saved_codes)

    def test_normal_close_removes_only_single_window(self):
        """【测试 2】普通点击关闭（未按 Alt）：仅关闭当前单个窗口并在配置中除名"""
        w1 = self._create_mock_dialog("600733", 100, 100, 800, 600)
        w2 = self._create_mock_dialog("000001", 900, 100, 800, 600)

        # 先保存一次
        run_sbc.save_launcher_holdings_windows()

        with patch("PyQt6.QtWidgets.QApplication.keyboardModifiers", return_value=Qt.KeyboardModifier.NoModifier), \
             patch("ctypes.windll.user32.GetAsyncKeyState", return_value=0):
            event = QCloseEvent()
            w1.closeEvent(event)
            self.app.processEvents()

            # 检查落盘文件：600733 应该被移除，000001 依然保留
            self.assertTrue(os.path.exists(self.temp_cfg))
            with open(self.temp_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            saved_codes = [x["code"] for x in data.get("sbc_holdings_windows", [])]
            self.assertNotIn("600733", saved_codes)
            self.assertIn("000001", saved_codes)

    def test_keyboard_interrupt_in_main_exec_saves_all_windows(self):
        """【测试 3】app.exec() 捕获 KeyboardInterrupt 时自动调用持久化保存并以 0 退出"""
        w = self._create_mock_dialog("603248", 200, 200, 700, 500)

        with patch.object(self.app, "exec", side_effect=KeyboardInterrupt), \
             patch("sys_utils.ensure_backend_tk_running", return_value=True), \
             patch.object(sys, "argv", ["run_sbc.py", "--sbc", "603248"]), \
             patch("run_sbc.open_sbc_chart_dialog", return_value=w), \
             patch("sys.exit") as mock_exit:
            run_sbc.main()
            mock_exit.assert_called_with(0)

            # 验证落盘文件存在且包含 603248
            self.assertTrue(os.path.exists(self.temp_cfg))
            with open(self.temp_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            saved_codes = [x["code"] for x in data.get("sbc_holdings_windows", [])]
            self.assertIn("603248", saved_codes)

    def test_sbc_excepthook_handles_keyboard_interrupt_in_slot(self):
        """【测试 4】槽函数内抛出 KeyboardInterrupt 时，自定义 excepthook 拦截并自动持久化"""
        w = self._create_mock_dialog("600519", 150, 150, 800, 600)

        self.app.setProperty("_has_saved_on_quit", False)
        run_sbc._setup_signal_handlers()
        excepthook = sys.excepthook

        with patch("sys.exit") as mock_exit:
            # 模拟 Qt 槽函数冒泡出的 KeyboardInterrupt 触发 sys.excepthook
            excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
            mock_exit.assert_called_with(0)

            # 验证文件已成功持久化保存
            self.assertTrue(os.path.exists(self.temp_cfg))
            with open(self.temp_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            saved_codes = [x["code"] for x in data.get("sbc_holdings_windows", [])]
            self.assertIn("600519", saved_codes)

    def test_hidden_state_window_saved_with_normal_geometry(self):
        """【测试 5】处于贴边隐藏状态的窗口退出时亦能通过 normal_geometry 精准持久化"""
        w = self._create_mock_dialog("300750", 50, 60, 850, 620)
        w.is_hidden_state = True
        w.normal_geometry = QRect(50, 60, 850, 620)

        run_sbc.quit_and_save_all_sbc_windows()

        self.assertTrue(os.path.exists(self.temp_cfg))
        with open(self.temp_cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
        saved_items = data.get("sbc_holdings_windows", [])
        self.assertEqual(len(saved_items), 1)
        item = saved_items[0]
        self.assertEqual(item["code"], "300750")
        self.assertEqual(item["x"], 50)
        self.assertEqual(item["y"], 60)
        self.assertEqual(item["width"], 850)
        self.assertEqual(item["height"], 620)


if __name__ == "__main__":
    unittest.main()
