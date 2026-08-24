# -*- coding: utf-8 -*-
import os
import sys
import unittest
import pandas as pd

app_root = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone"
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from global_favorites import GlobalFavoriteManager

class TestFavoritesAndStyles(unittest.TestCase):
    def setUp(self):
        self.fav_mgr = GlobalFavoriteManager()

    def test_toggle_favorite_consistency(self):
        test_code = "688826"
        initial_is_fav = test_code in self.fav_mgr.get_favorite_stocks()
        
        # Toggle
        action1 = self.fav_mgr.toggle_favorite_stock(test_code)
        if initial_is_fav:
            self.assertEqual(action1, "removed")
            self.assertNotIn(test_code, self.fav_mgr.get_favorite_stocks())
        else:
            self.assertEqual(action1, "added")
            self.assertIn(test_code, self.fav_mgr.get_favorite_stocks())

        # Toggle back to original state
        action2 = self.fav_mgr.toggle_favorite_stock(test_code)
        if initial_is_fav:
            self.assertEqual(action2, "added")
            self.assertIn(test_code, self.fav_mgr.get_favorite_stocks())
        else:
            self.assertEqual(action2, "removed")
            self.assertNotIn(test_code, self.fav_mgr.get_favorite_stocks())

    def test_qss_no_selection_color_green(self):
        from ats.ui.styles import DARK_THEME_QSS
        # 确保全局 QSS 不包含强制将文本变绿的 selection-color: #00ff88
        self.assertNotIn("selection-color: #00ff88", DARK_THEME_QSS)
        self.assertIn("selection-background-color: #1e334d;", DARK_THEME_QSS)

    def test_color_preserving_item_delegate(self):
        from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QStyleOptionViewItem, QStyle, QAbstractItemView
        from PyQt6.QtGui import QColor, QPalette
        from PyQt6.QtCore import Qt
        from ats.ui.styles import ColorPreservingItemDelegate
        from ats.ui.base_table import BaseATSTableWidget

        app = QApplication.instance() or QApplication(sys.argv)
        table = BaseATSTableWidget()
        table.setRowCount(2)
        table.setColumnCount(3)

        # 验证 BaseATSTableWidget 默认装载了 ColorPreservingItemDelegate
        self.assertIsInstance(table.itemDelegate(), ColorPreservingItemDelegate)

        # 模拟设置上涨红与下跌绿 Item
        item_up = QTableWidgetItem("+3.81%")
        item_up.setForeground(QColor("#FF4444"))
        table.setItem(0, 0, item_up)

        item_down = QTableWidgetItem("-1.43%")
        item_down.setForeground(QColor("#33CC5A"))
        table.setItem(1, 0, item_down)

        # 1. 选中第 0 行 (上涨红)
        table.selectRow(0)
        opt0 = QStyleOptionViewItem()
        table.itemDelegate().initStyleOption(opt0, table.model().index(0, 0))
        ht0 = opt0.palette.color(QPalette.ColorRole.HighlightedText).name().lower()
        self.assertEqual(ht0, "#ff4444", "选中的上涨红单元格必须100%保留红色前景色")

        # 2. 选中第 1 行 (下跌绿)
        table.selectRow(1)
        opt1 = QStyleOptionViewItem()
        table.itemDelegate().initStyleOption(opt1, table.model().index(1, 0))
        ht1 = opt1.palette.color(QPalette.ColorRole.HighlightedText).name().lower()
        self.assertEqual(ht1, "#33cc5a", "选中的下跌绿单元格必须100%保留绿色前景色")

    def test_main_window_link_stock_no_name_error(self):
        """验证 ATS 主窗口 link_stock 方法在调用外部终端联动时不会抛出 is_ths 未定义异常"""
        from unittest.mock import MagicMock
        from ats.ui.main_window import ATSMainWindow
        
        # 使用 MagicMock 绑定 link_stock 方法测试内部逻辑
        mock_mw = MagicMock()
        mock_mw._last_linked_code = None
        mock_mw._last_linked_time = 0
        mock_mw.status_bar = MagicMock()
        mock_mw.cb_vis = MagicMock(isChecked=MagicMock(return_value=False))
        mock_mw.cb_tdx = MagicMock(isChecked=MagicMock(return_value=True))
        mock_mw.cb_ths = MagicMock(isChecked=MagicMock(return_value=True))
        mock_mw.get_stock_name = MagicMock(return_value="光库科技")

        try:
            ATSMainWindow.link_stock(mock_mw, "300620", "光库科技")
        except NameError as e:
            self.fail(f"link_stock 抛出 NameError 异常: {e}")

if __name__ == '__main__':
    unittest.main()
