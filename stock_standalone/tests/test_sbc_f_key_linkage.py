# -*- coding: utf-8 -*-
"""
tests/test_sbc_f_key_linkage.py
---------------------------------
专项验证：SBC 窗口 F 键快捷键联动功能
1. 【F 键按键触发】：在 SBC 对话框中按下 F 键，成功触发 _trigger_linkage；
2. 【物理通达信推送】：独立进程与全模式下，F 联动均成功向 linkage_service.get_link_manager().push 投递物理联动任务；
3. 【画布按键联动】：在走势图画布 (Canvas) 上按下 F 键，同样联动当前标的；
4. 【工具栏按钮与提示】：顶部工具栏新增 “🔗 联动 (F)” 按钮，点击即可触发全链路联动并给予动画反馈；
5. 【文本编辑防误触】：处于 QLineEdit 文本编辑输入代码状态下按 F 键，不触发外部物理联动。
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_STANDALONE = os.path.dirname(TEST_DIR)
if STOCK_STANDALONE not in sys.path:
    sys.path.insert(0, STOCK_STANDALONE)

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLineEdit
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog

_app = QApplication.instance() or QApplication(sys.argv)


class TestSBCFKeyLinkage(unittest.TestCase):

    def setUp(self):
        self.code = "600733"
        # 屏蔽网络与行情服务拉取
        with patch.object(SBCIntradayChartDialog, "reload_chart", return_value=None), \
             patch("sys_utils.ensure_backend_tk_running", return_value=True):
            self.dialog = SBCIntradayChartDialog(None, code=self.code)
            self.dialog.show()
            _app.processEvents()

    def tearDown(self):
        if self.dialog:
            self.dialog._is_closing = True
            self.dialog.close()
            self.dialog.deleteLater()
            _app.processEvents()

    def test_f_key_in_dialog_triggers_linkage(self):
        """【测试 1】在 SBC 窗口按下 F 键，触发物理直连通达信与状态栏反馈"""
        mock_link_mgr = MagicMock()
        with patch("linkage_service.get_link_manager", return_value=mock_link_mgr):
            # 模拟按下 F 键
            key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F, Qt.KeyboardModifier.NoModifier)
            self.dialog.keyPressEvent(key_event)
            _app.processEvents()

            # 断言向 linkage_service 投递了物理联动指令
            mock_link_mgr.push.assert_called_once_with(
                "600733",
                flags={'tdx': True, 'ths': True, 'dfcf': False},
                auto=False
            )

            # 断言状态信息更新
            info_text = self.dialog.lbl_info.text()
            self.assertIn("600733", info_text)
            self.assertIn("F联动", info_text)

    def test_f_key_in_canvas_triggers_linkage(self):
        """【测试 2】在 SBC 画布上按下 F 键，触发物理直连通达信"""
        mock_link_mgr = MagicMock()
        with patch("linkage_service.get_link_manager", return_value=mock_link_mgr):
            key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F, Qt.KeyboardModifier.NoModifier)
            self.dialog.canvas.keyPressEvent(key_event)
            _app.processEvents()

            mock_link_mgr.push.assert_called_once_with(
                "600733",
                flags={'tdx': True, 'ths': True, 'dfcf': False},
                auto=False
            )

    def test_btn_linkage_exists_and_triggers_linkage(self):
        """【测试 3】顶部工具栏存在 '🔗 联动 (F)' 按钮，点击即可触发全链路联动"""
        self.assertTrue(hasattr(self.dialog, "btn_linkage"))
        btn_text = self.dialog.btn_linkage.text()
        self.assertIn("F", btn_text)
        self.assertIn("联动", btn_text)

        mock_link_mgr = MagicMock()
        with patch("linkage_service.get_link_manager", return_value=mock_link_mgr):
            self.dialog.btn_linkage.click()
            _app.processEvents()

            mock_link_mgr.push.assert_called_once_with(
                "600733",
                flags={'tdx': True, 'ths': True, 'dfcf': False},
                auto=False
            )

    def test_f_key_in_text_editing_mode_does_not_trigger_linkage(self):
        """【测试 4】处于代码搜索或文本框编辑状态时按 F 键，不触发外部行情联动"""
        mock_link_mgr = MagicMock()
        with patch("linkage_service.get_link_manager", return_value=mock_link_mgr), \
             patch("ats.ui.styles.is_editing_text", return_value=True):

            key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F, Qt.KeyboardModifier.NoModifier)
            self.dialog.keyPressEvent(key_event)
            _app.processEvents()

            # 断言由于正处于文本输入编辑中，物理联动绝不触发
            mock_link_mgr.push.assert_not_called()


if __name__ == "__main__":
    unittest.main()
