# -*- coding: utf-8 -*-
"""
专项自动化测试：验证四大 Tab 看板 (资金主线 CapitalDragonPanel, 重点关注 FavoritePanel, 
MA20d回调 SwingStateTable, 新股次新 NewStockPanel) 双击直通 SBC 走势图与统一调度的完整闭环。
"""

import sys
import os
from pathlib import Path

# 将项目根目录加入 sys.path
root_dir = str(Path(__file__).resolve().parents[1])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QTableWidgetItem
from PyQt6.QtCore import Qt

# 确保 QApplication 初始化
app = QApplication.instance() or QApplication(sys.argv)


def test_favorite_panel_double_click_sbc():
    """测试 FavoritePanel (重点关注) 双击行时调用 open_sbc_chart 并发射 stock_double_clicked 信号"""
    from ats.ui.favorite_panel import FavoritePanel
    panel = FavoritePanel()
    
    # 构造假数据行
    panel.table.setRowCount(1)
    panel.table.setItem(0, 0, QTableWidgetItem("600030"))
    panel.table.setItem(0, 1, QTableWidgetItem("⭐ 中信证券"))

    received_signals = []
    panel.stock_double_clicked.connect(lambda code, name: received_signals.append((code, name)))

    with patch.object(panel, "open_sbc_chart") as mock_open_sbc:
        item = panel.table.item(0, 0)
        panel._on_double_clicked(item)

        # 断言 open_sbc_chart 被调用且代码清洗干净
        mock_open_sbc.assert_called_once_with("600030", "中信证券")
        # 断言 stock_double_clicked 信号发射
        assert len(received_signals) == 1
        assert received_signals[0] == ("600030", "中信证券")


def test_swing_table_double_click_sbc():
    """测试 SwingStateTable (MA20d 回调跟踪器) 双击单元格时调用 open_sbc_chart 并发射 stock_double_clicked 信号"""
    from ats.ui.swing_table import SwingStateTable
    panel = SwingStateTable()

    panel.table.setRowCount(1)
    panel.table.setItem(0, 0, QTableWidgetItem("000001"))
    panel.table.setItem(0, 1, QTableWidgetItem("⭐ 平安银行"))

    received_signals = []
    panel.stock_double_clicked.connect(lambda code, name, ctx: received_signals.append((code, name, ctx)))

    with patch.object(panel, "open_sbc_chart") as mock_open_sbc:
        panel._on_cell_double_clicked(0, 0)

        # 断言 open_sbc_chart 被调用
        mock_open_sbc.assert_called_once_with("000001", "平安银行")
        # 断言 stock_double_clicked 信号发射
        assert len(received_signals) == 1
        assert received_signals[0][0] == "000001"
        assert received_signals[0][1] == "平安银行"


def test_new_stock_panel_double_click_sbc():
    """测试 NewStockPanel (新股次新股) 双击单元格时调用 open_sbc_chart 并发射 stock_double_clicked 信号"""
    from ats.ui.new_stock_panel import NewStockPanel
    mock_mw = MagicMock()
    panel = NewStockPanel(main_window=mock_mw)

    panel.table.setRowCount(1)
    c_code = panel._get_col_by_header("代码")
    c_name = panel._get_col_by_header("名称")
    panel.table.setItem(0, c_code, QTableWidgetItem("301550"))
    panel.table.setItem(0, c_name, QTableWidgetItem("⭐ 斯菱股份"))

    received_signals = []
    panel.stock_double_clicked.connect(lambda code, name: received_signals.append((code, name)))

    with patch.object(panel, "open_sbc_chart") as mock_open_sbc:
        panel._on_cell_double_clicked(0, c_code)

        # 断言 open_sbc_chart 被调用
        mock_open_sbc.assert_called_once_with("301550", "斯菱股份")
        # 断言 stock_double_clicked 信号发射
        assert len(received_signals) == 1
        assert received_signals[0] == ("301550", "斯菱股份")


def test_main_window_open_sbc_for_stock_dispatch():
    """测试主窗口 open_sbc_for_stock 方法正确调度 open_sbc_chart_dialog"""
    from ats.ui.main_window import ATSMainWindow
    with patch("ats.ui.intraday_strategy_dialog.open_sbc_chart_dialog") as mock_sbc_func:
        dummy_mw = MagicMock(spec=ATSMainWindow)
        dummy_mw.status_bar = MagicMock()
        ATSMainWindow.open_sbc_for_stock(dummy_mw, "001212", "中旗新材")
        mock_sbc_func.assert_called_once_with(parent_win=dummy_mw, code="001212", period_mode="10d")
