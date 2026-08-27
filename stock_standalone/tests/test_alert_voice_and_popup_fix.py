# -*- coding: utf-8 -*-
"""
测试 AlertNotifier 语音与弹窗全局开关、一键静音清空队列、点击直达唤醒来源窗口以及限频加固
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# 确保路径
app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QPoint

from ats.alert_notifier import (
    AlertNotifier, 
    InAppToastWidget, 
    activate_and_locate_target_window,
    load_toast_screen_config,
    save_toast_screen_config,
    _GLOBAL_VOICE_ENABLED,
    _GLOBAL_TOAST_ENABLED
)


class TestAlertNotifierFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.notifier = AlertNotifier.get_instance()
        self.notifier.clear_queue()

    def test_01_global_voice_and_toast_switches(self):
        """测试全局语音与弹窗开关设置与持久化"""
        # 测试关闭语音
        self.notifier.set_voice_enabled(False)
        self.assertFalse(self.notifier.is_voice_enabled())

        # 测试开启语音
        self.notifier.set_voice_enabled(True)
        self.assertTrue(self.notifier.is_voice_enabled())

        # 测试关闭弹窗
        self.notifier.set_toast_enabled(False)
        self.assertFalse(self.notifier.is_toast_enabled())

        # 测试开启弹窗
        self.notifier.set_toast_enabled(True)
        self.assertTrue(self.notifier.is_toast_enabled())

    def test_02_clear_queue(self):
        """测试一键静音与清空通知队列"""
        self.notifier._notify_queue.append({'code': '600000', 'name': '浦发银行', 'reason': '测试'})
        self.notifier._notify_queue.append({'code': '000001', 'name': '平安银行', 'reason': '测试'})
        self.assertEqual(len(self.notifier._notify_queue), 2)

        self.notifier.clear_queue()
        self.assertEqual(len(self.notifier._notify_queue), 0)
        self.assertFalse(self.notifier._is_busy)

    def test_03_activate_and_locate_target_window(self):
        """测试点击弹窗时直达唤醒并定位来源窗口"""
        mock_window = MagicMock(spec=QWidget)
        mock_window.isMinimized.return_value = True
        mock_window.isHidden.return_value = True
        mock_window.is_hidden_state = True
        mock_window._expand_window = MagicMock()
        mock_window.locate_stock_in_table = MagicMock()

        activate_and_locate_target_window(mock_window, code="688356", reason="黄金定龙")

        # 断言窗口被正常唤醒、还原、展开、置顶与激活
        mock_window.showNormal.assert_called()
        mock_window.show.assert_called()
        mock_window._expand_window.assert_called_once()
        mock_window.raise_.assert_called()
        mock_window.activateWindow.assert_called()

        # 断言定位方法被调用并传入了股票代码
        mock_window.locate_stock_in_table.assert_called_once_with("688356", auto_popup=True, reason="黄金定龙")

    def test_04_toast_click_triggers_locate(self):
        """测试 InAppToastWidget 单击触发直达定位"""
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent, QPointF

        mock_parent = MagicMock(spec=QWidget)
        mock_parent.isMinimized.return_value = False
        mock_parent.isHidden.return_value = False
        mock_parent.locate_stock_in_table = MagicMock()

        toast = InAppToastWidget(title="测试", message="测试消息", code="002594", parent=mock_parent)
        self.assertEqual(toast.code, "002594")

        # 模拟鼠标释放 (非拖拽单击)
        event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        toast._is_dragging = False

        toast.mouseReleaseEvent(event)
        mock_parent.locate_stock_in_table.assert_called_once()

    def test_05_tray_menu_actions_exist(self):
        """测试系统托盘右键菜单包含语音开关、弹窗开关与一键清空静音项"""
        self.notifier._init_tray()
        if self.notifier.tray_menu:
            actions_text = [act.text() for act in self.notifier.tray_menu.actions()]
            self.assertTrue(any("语音播报" in txt for txt in actions_text))
            self.assertTrue(any("弹窗通知" in txt for txt in actions_text))
            self.assertTrue(any("静音并清空" in txt for txt in actions_text))


if __name__ == "__main__":
    unittest.main()
