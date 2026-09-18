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
