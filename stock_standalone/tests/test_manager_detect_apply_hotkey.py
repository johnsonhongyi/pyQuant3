# -*- coding: utf-8 -*-
"""
测试窗口布局管理器：
1. 默认快捷键 alt+shift+f 的探测并应用推荐布局功能
2. 快捷键输入框录入、编辑与绑定功能
3. 启用/停用开关功能与配置持久化
4. 全局热键与探测推荐热键冲突检测
"""

import sys
import os
import json
import tempfile
import unittest
from unittest.mock import patch

app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)
webtools_dir = os.path.join(app_root, "webTools")
if webtools_dir not in sys.path:
    sys.path.insert(0, webtools_dir)

from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QApplication

from window_manager.ui import WindowPosManagerUI
from window_manager.core import ConfigManager

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


class FakeHotkeyThread:
    """仿真的全局热键线程，避免真实注册 Windows API 与线程挂起"""
    def __init__(self, callback, hotkey_id=0xAFC0):
        self._callback = callback
        self.HOTKEY_ID = hotkey_id
        self._registered = True
        self._running = True

    def set_hotkey(self, modifiers, vk):
        self._modifiers = modifiers
        self._vk = vk

    def start(self):
        self._registered = True

    def stop(self):
        self._registered = False
        self._running = False

    def is_alive(self):
        return False

    def join(self, timeout=None):
        pass


class TestManagerDetectApplyHotkey(unittest.TestCase):
    """测试探测并应用推荐布局的快捷键与开关功能"""

    @classmethod
    def setUpClass(cls):
        # 禁用后台守护线程启动，防止测试时线程挂起
        cls.patch_sync = patch('window_manager.sync_engine.RamDiskSyncWorker.start', lambda self: None)
        cls.patch_sync.start()
        cls.patch_single = patch.object(WindowPosManagerUI, 'setup_single_instance_server', lambda self: None)
        cls.patch_single.start()
        cls.patch_acer = patch('window_manager.core.AcerPerformanceController.is_supported', lambda self: False)
        cls.patch_acer.start()
        cls.patch_thread = patch('window_manager.ui.ManagerHotkeyThread', FakeHotkeyThread)
        cls.patch_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch_thread.stop()
        cls.patch_acer.stop()
        cls.patch_single.stop()
        cls.patch_sync.stop()

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config_path = os.path.join(self.temp_dir, "test_window_layout_config.json")
        sample_config = {
            "single_display": {
                "test_scheme": {
                    "通达信": "100,100,500,400"
                }
            },
            "global_hotkey": "ctrl+alt+w",
            "detect_apply_hotkey": "alt+shift+f",
            "detect_apply_hotkey_enabled": True
        }
        with open(self.temp_config_path, "w", encoding="utf-8") as f:
            json.dump(sample_config, f, ensure_ascii=False, indent=4)

        self.cfg_mgr = ConfigManager(self.temp_config_path)

    def tearDown(self):
        try:
            if os.path.exists(self.temp_config_path):
                os.remove(self.temp_config_path)
            if os.path.exists(self.temp_dir):
                os.rmdir(self.temp_dir)
        except Exception:
            pass

    def _cleanup_win(self, win):
        if not win:
            return
        try:
            if hasattr(win, 'tray_icon') and win.tray_icon:
                win.tray_icon.hide()
            if getattr(win, '_hotkey_thread', None):
                win._hotkey_thread.stop()
                win._hotkey_thread = None
            if getattr(win, '_detect_apply_hotkey_thread', None):
                win._detect_apply_hotkey_thread.stop()
                win._detect_apply_hotkey_thread = None
            if hasattr(win, '_topology_debounce_timer') and win._topology_debounce_timer:
                win._topology_debounce_timer.stop()
        except Exception:
            pass
        win.close()

    def test_default_hotkey_and_ui_elements(self):
        """验证默认快捷键设置与 UI 控件初始化"""
        win = WindowPosManagerUI(config_manager=self.cfg_mgr)
        try:
            self.assertEqual(win.current_bound_detect_apply_hotkey, "alt+shift+f")
            self.assertTrue(win.detect_apply_hotkey_enabled)

            # 验证控件存在且属性正确
            self.assertTrue(hasattr(win, 'lbl_detect_apply_hotkey'))
            self.assertEqual(win.lbl_detect_apply_hotkey.text(), "探测推荐:")

            self.assertTrue(hasattr(win, 'le_detect_apply_hotkey'))
            self.assertEqual(win.le_detect_apply_hotkey.text(), "alt+shift+f")

            self.assertTrue(hasattr(win, 'btn_bind_detect_apply'))
            self.assertEqual(win.btn_bind_detect_apply.text(), "绑定")

            self.assertTrue(hasattr(win, 'chk_detect_apply'))
            self.assertEqual(win.chk_detect_apply.text(), "启用")
            self.assertTrue(win.chk_detect_apply.isChecked())
        finally:
            self._cleanup_win(win)

    def test_hotkey_switch_toggle(self):
        """测试开关切换：启用与停用"""
        win = WindowPosManagerUI(config_manager=self.cfg_mgr)
        try:
            # 模拟用户取消勾选开关
            win.chk_detect_apply.setChecked(False)
            self.assertFalse(win.detect_apply_hotkey_enabled)
            self.assertFalse(win.config_manager.config_data.get("detect_apply_hotkey_enabled"))

            # 模拟用户重新勾选开关
            win.chk_detect_apply.setChecked(True)
            self.assertTrue(win.detect_apply_hotkey_enabled)
            self.assertTrue(win.config_manager.config_data.get("detect_apply_hotkey_enabled"))
        finally:
            self._cleanup_win(win)

    def test_hotkey_edit_and_bind(self):
        """测试快捷键编辑与绑定新按键"""
        win = WindowPosManagerUI(config_manager=self.cfg_mgr)
        try:
            with patch.object(QtWidgets.QMessageBox, 'information') as mock_info:
                win.le_detect_apply_hotkey.setText("ctrl+shift+f1")
                win.on_bind_detect_apply_clicked()

                self.assertEqual(win.current_bound_detect_apply_hotkey, "ctrl+shift+f1")
                self.assertEqual(win.config_manager.config_data.get("detect_apply_hotkey"), "ctrl+shift+f1")
                mock_info.assert_called_once()
        finally:
            self._cleanup_win(win)

    def test_hotkey_conflict_detection(self):
        """测试热键冲突检测"""
        win = WindowPosManagerUI(config_manager=self.cfg_mgr)
        try:
            with patch.object(QtWidgets.QMessageBox, 'warning') as mock_warn:
                # 尝试将探测推荐快捷键改成与全局呼出快捷键相同
                win.le_detect_apply_hotkey.setText("ctrl+alt+w")
                win.on_bind_detect_apply_clicked()
                mock_warn.assert_called_once()
                self.assertIn("冲突", mock_warn.call_args[0][1])

                mock_warn.reset_mock()
                # 尝试将全局呼出快捷键改成与探测推荐快捷键相同
                win.le_hotkey.setText("alt+shift+f")
                win.on_bind_hotkey_clicked()
                mock_warn.assert_called_once()
                self.assertIn("冲突", mock_warn.call_args[0][1])
        finally:
            self._cleanup_win(win)

    def test_save_all_config_persistence(self):
        """测试 save_all_config 能够完整持久化快捷键及开关"""
        win = WindowPosManagerUI(config_manager=self.cfg_mgr)
        try:
            win.le_detect_apply_hotkey.setText("alt+shift+d")
            win.chk_detect_apply.setChecked(False)
            
            with patch.object(QtWidgets.QMessageBox, 'information'):
                win.save_all_config()

            # 重新读取磁盘文件
            with open(self.temp_config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(saved.get("detect_apply_hotkey"), "alt+shift+d")
            self.assertFalse(saved.get("detect_apply_hotkey_enabled"))
        finally:
            self._cleanup_win(win)

    def test_signal_triggers_detect_and_apply(self):
        """测试热键触发信号能够调用探测并应用布局逻辑"""
        win = WindowPosManagerUI(config_manager=self.cfg_mgr)
        try:
            with patch.object(win, 'detect_and_apply_recommended_layout') as mock_apply:
                win.detect_apply_signal.emit()
                mock_apply.assert_called_once_with(source="全局热键", show_tray_message=True)
        finally:
            self._cleanup_win(win)


if __name__ == "__main__":
    unittest.main()
