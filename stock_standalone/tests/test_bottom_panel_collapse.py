# -*- coding: utf-8 -*-
"""
tests/test_bottom_panel_collapse.py — 底部面板自动折叠与状态持久化单元测试
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QSplitter, QTabWidget, QPushButton, QWidget
from PyQt6.QtCore import Qt

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication([])

from ats.ui.main_window import ATSMainWindow
from ats.ui.styles import save_config_node, load_config_node


class TestBottomPanelCollapse(unittest.TestCase):

    def setUp(self):
        # 确保配置初始化为展开状态
        save_config_node("ats_bottom_panel_collapsed", False)
        save_config_node("ats_bottom_panel_last_height", 350)

        # 构建轻量 mock 主窗口
        self.mock_win = MagicMock()
        self.mock_win.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.mock_win.top_tabs = QTabWidget()
        self.mock_win.center_tabs = QTabWidget()
        self.mock_win.btn_toggle_bottom_panel = QPushButton("▼ 折叠")

        self.mock_win.center_splitter.addWidget(self.mock_win.top_tabs)
        self.mock_win.center_splitter.addWidget(self.mock_win.center_tabs)

        self.mock_win._is_bottom_panel_collapsed = False
        self.mock_win._last_bottom_panel_height = 350
        self.mock_win._is_restoring_sizes = False

        # 绑定方法
        self.mock_win.toggle_bottom_panel = ATSMainWindow.toggle_bottom_panel.__get__(self.mock_win, ATSMainWindow)
        self.mock_win.set_bottom_panel_collapsed = ATSMainWindow.set_bottom_panel_collapsed.__get__(self.mock_win, ATSMainWindow)
        self.mock_win._on_bottom_tab_clicked = ATSMainWindow._on_bottom_tab_clicked.__get__(self.mock_win, ATSMainWindow)

    def tearDown(self):
        save_config_node("ats_bottom_panel_collapsed", False)
        save_config_node("ats_bottom_panel_last_height", 350)

    def test_01_initial_button_and_state(self):
        """测试初始状态为展开，按钮文本为 ▼ 折叠"""
        self.assertFalse(self.mock_win._is_bottom_panel_collapsed)
        self.assertEqual(self.mock_win.btn_toggle_bottom_panel.text(), "▼ 折叠")

    def test_02_toggle_collapse_and_expand(self):
        """测试点击折叠与展开功能"""
        # 1. 触发折叠
        self.mock_win.toggle_bottom_panel()
        self.assertTrue(self.mock_win._is_bottom_panel_collapsed)
        self.assertEqual(self.mock_win.btn_toggle_bottom_panel.text(), "▲ 展开")
        self.assertGreater(self.mock_win._last_bottom_panel_height, 0)

        # 验证高度限制
        tab_bar_h = self.mock_win.center_tabs.tabBar().sizeHint().height() or 32
        self.assertEqual(self.mock_win.center_tabs.maximumHeight(), tab_bar_h)

        # 2. 触发展开
        self.mock_win.toggle_bottom_panel()
        self.assertFalse(self.mock_win._is_bottom_panel_collapsed)
        self.assertEqual(self.mock_win.btn_toggle_bottom_panel.text(), "▼ 折叠")
        self.assertEqual(self.mock_win.center_tabs.maximumHeight(), 16777215) # QWIDGETSIZE_MAX

    def test_03_tab_click_auto_expands_when_collapsed(self):
        """测试在折叠状态下点击任意 Tab 标签栏自动恢复展开"""
        # 先折叠
        self.mock_win.set_bottom_panel_collapsed(True, save=False)
        self.assertTrue(self.mock_win._is_bottom_panel_collapsed)

        # 模拟用户点击 Tab 1 (如“交易流水”)
        self.mock_win._on_bottom_tab_clicked(1)
        self.assertFalse(self.mock_win._is_bottom_panel_collapsed)
        self.assertEqual(self.mock_win.btn_toggle_bottom_panel.text(), "▼ 折叠")

    def test_04_persistence_save_and_restore(self):
        """测试折叠状态与高度的持久化保存与恢复"""
        # 1. 折叠并保存
        self.mock_win.set_bottom_panel_collapsed(True, save=True)
        saved_collapsed = load_config_node("ats_bottom_panel_collapsed", False)
        saved_height = load_config_node("ats_bottom_panel_last_height", 0)
        self.assertTrue(saved_collapsed)
        self.assertGreater(saved_height, 0)

        # 2. 模拟恢复逻辑
        new_mock_win = MagicMock()
        new_mock_win.center_splitter = QSplitter(Qt.Orientation.Vertical)
        new_mock_win.center_tabs = QTabWidget()
        new_mock_win.btn_toggle_bottom_panel = QPushButton()
        new_mock_win.set_bottom_panel_collapsed = ATSMainWindow.set_bottom_panel_collapsed.__get__(new_mock_win, ATSMainWindow)
        
        # 模拟从持久化恢复
        restored_collapsed = load_config_node("ats_bottom_panel_collapsed", False)
        restored_height = load_config_node("ats_bottom_panel_last_height", 350)
        new_mock_win._last_bottom_panel_height = restored_height
        if restored_collapsed:
            new_mock_win.set_bottom_panel_collapsed(True, save=False)

        self.assertTrue(new_mock_win._is_bottom_panel_collapsed)
        self.assertEqual(new_mock_win.btn_toggle_bottom_panel.text(), "▲ 展开")


if __name__ == "__main__":
    unittest.main()
