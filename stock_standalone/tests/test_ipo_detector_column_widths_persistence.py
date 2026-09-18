# -*- coding: utf-8 -*-
import sys
import os
import json
import pytest
from PyQt6.QtWidgets import QApplication, QHeaderView

cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from ats.ui.base_table import BaseATSTableWidget
from ats.ui.ipo_subnew_detector_dialog import (
    IPOSubnewDetectorDialog,
    IPODetectorTableWidget,
    get_ipo_detector_default_widths,
    get_ipo_detector_layout_file
)

app = QApplication.instance() or QApplication(sys.argv)
TEST_TMP_CFG = os.path.join(cur_dir, "_tmp_ipo_layout_test.json")


def teardown_module():
    if os.path.exists(TEST_TMP_CFG):
        try:
            os.remove(TEST_TMP_CFG)
        except Exception:
            pass


def test_table_inherits_base_ats_table_and_narrow_mode():
    """验证表格继承 BaseATSTableWidget 且默认列宽采用与其它 Tab 一致的极窄模式"""
    assert issubclass(IPODetectorTableWidget, BaseATSTableWidget)

    widths = get_ipo_detector_default_widths([])
    assert len(widths) == 13
    # 验证基础列全为极窄尺寸 (<= 85px)
    assert widths[0] == 55  # 代码
    assert widths[1] == 78  # 名称
    assert widths[2] == 52  # 现价
    assert widths[3] == 50  # 涨跌%
    assert widths[4] == 52  # 10d VWAP
    assert widths[5] == 52  # VWAP偏离
    assert widths[9] == 52  # 止损位


def test_columns_are_interactive_and_resizable(monkeypatch):
    """验证表格所有列均设为 Interactive，操盘手可自由拖拽，与其它 Tab 全面对齐"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        table = dlg.table
        hv = table.horizontalHeader()
        total_cols = table.columnCount()
        assert total_cols > 10

        for c in range(total_cols):
            mode = hv.sectionResizeMode(c)
            assert mode == QHeaderView.ResizeMode.Interactive, (
                f"列 {c} 的 ResizeMode 必须是 Interactive，实际为: {mode}"
            )
    finally:
        dlg.close()


def test_setup_persistence_standard_methods_available(monkeypatch):
    """验证统一采用全系统标准 setup_persistence，拥有原生一体化拖拽与保存接口"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        table = dlg.table
        assert hasattr(table, "save_header_state")
        assert hasattr(table, "restore_header_state")
        assert callable(table.save_header_state)
        assert callable(table.restore_header_state)

        # 模拟执行保存与恢复
        table.save_header_state()
        table.restore_header_state()
    finally:
        dlg.close()


def test_auto_fit_columns_retains_interactive_and_saves(monkeypatch):
    """验证一键自适应全列宽后，依然保持 Interactive 自由拖拽并持久化列宽"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        table = dlg.table
        # 执行一键自适应
        dlg._auto_fit_columns()

        hv = table.horizontalHeader()
        for c in range(table.columnCount()):
            assert hv.sectionResizeMode(c) == QHeaderView.ResizeMode.Interactive
    finally:
        dlg.close()


def test_extended_selection_and_dark_corner_styles(monkeypatch):
    """验证表格启用 ExtendedSelection (支持 Ctrl/Shift 多选) 且配置了深色 CornerButton 与滚动条样式"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        from PyQt6.QtWidgets import QAbstractItemView
        table = dlg.table
        assert table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection

        style = dlg.styleSheet()
        # 验证彻底消灭右上角白块与滚动条白块
        assert "QTableCornerButton::section" in style
        assert "background-color: #1a1a26" in style
        assert "QScrollBar:vertical" in style
        assert "background-color: #121214" in style
    finally:
        dlg.close()


def test_tile_sbc_prioritizes_selected_stocks(monkeypatch):
    """验证【一键平铺 SBC】优先平铺操盘手在表格中选中的标的 (单选/Ctrl/Shift)，未选中时回退默认前4只"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        dlg.monitored_codes = ["601091", "920298", "688837", "301689", "301699", "920065"]
        dlg._rebuild_table_rows()

        opened_codes = []
        rearranged = []

        def mock_open_sbc(code, period_mode="10d", parent_win=None):
            opened_codes.append(code)
            return None

        def mock_rearrange():
            rearranged.append(True)

        monkeypatch.setattr("ats.ui.intraday_strategy_dialog.open_sbc_chart_dialog", mock_open_sbc)
        monkeypatch.setattr("ats.ui.intraday_strategy_dialog.rearrange_all_sbc_windows", mock_rearrange)

        # 场景 1: 未选中任何行 -> 默认取前 4 只平铺
        dlg.table.clearSelection()
        opened_codes.clear()
        dlg._on_tile_sbc_clicked()
        assert opened_codes == ["601091", "920298", "688837", "301689"]

        # 场景 2: 操盘手按住 Ctrl 选了第 1 行 (920298) 和第 2 行 (688837)
        dlg.table.clearSelection()
        dlg.table.selectRow(1)
        dlg.table.selectRow(2)
        opened_codes.clear()
        dlg._on_tile_sbc_clicked()
        assert opened_codes == ["920298", "688837"]
        assert "选中的 2 只标的" in dlg.lbl_status.text()
    finally:
        dlg.close()

