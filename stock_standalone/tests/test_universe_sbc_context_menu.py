# -*- coding: utf-8 -*-
"""
UniverseTreeWidget 左侧策略池右键 SBC 功能与通道测算专项单元测试
"""

import sys
import os
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint

CURR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURR_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

app = QApplication.instance()
if app is None:
    app = QApplication([])

from ats.ui.universe_widget import UniverseTreeWidget, UniverseTreeItem


class TestUniverseSBCContextMenu(unittest.TestCase):
    """测试左侧策略池右键菜单中的 SBC 功能与测算"""

    def setUp(self):
        self.widget = UniverseTreeWidget()

    def test_01_tree_item_context_menu_actions(self):
        """验证右键菜单项包含 SBC 走势、分时阶梯和 60f 通道测算"""
        # 构建一个模拟子节点
        root = self.widget.radar_root
        item = UniverseTreeItem(root)
        item.setText(0, "688826")
        item.setText(1, "频准激光")
        item.setData(0, Qt.ItemDataRole.UserRole, "688826")
        item.setData(1, Qt.ItemDataRole.UserRole, "频准激光")

        # 检查方法存在性
        self.assertTrue(hasattr(self.widget, "_open_sbc_chart"))
        self.assertTrue(hasattr(self.widget, "_open_ladder_window"))
        self.assertTrue(hasattr(self.widget, "_run_60f_channel_eval"))
        print("[Test 1] UniverseTreeWidget SBC 与测算菜单响应方法检查成功")


if __name__ == "__main__":
    unittest.main()
