# -*- coding: utf-8 -*-
"""tests/test_fusion_ladder_search.py — 融合梯度监视器搜索与右键黏贴模糊查询专项测试。"""

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["fusion-ladder-search-test"])
    return app


@pytest.fixture(autouse=True)
def clean_config():
    from ats.ui.styles import save_config_node

    save_config_node("fusion_ladder_stays_on_top", False)
    save_config_node("fusion_ladder_anchor_edge", None)
    save_config_node("fusion_ladder_is_hidden", False)
    yield
    save_config_node("fusion_ladder_stays_on_top", False)
    save_config_node("fusion_ladder_anchor_edge", None)
    save_config_node("fusion_ladder_is_hidden", False)


def _setup_mock_table_data(tbl):
    """为测试表格填充 4 行模拟股票数据。"""
    from ats.ui.styles import NumericTableWidgetItem

    tbl.setSortingEnabled(False)
    tbl.setRowCount(0)
    data = [
        ("600688", "上海石化", 2.94, 5.00),
        ("688128", "中国电研", 22.53, 8.21),
        ("600928", "西安银行", 3.74, 4.18),
        ("601919", "中远海控", 17.33, 3.96),
    ]
    for row_idx, (cd, nm, p, pct) in enumerate(data):
        tbl.insertRow(row_idx)
        tbl.setItem(row_idx, 0, NumericTableWidgetItem("L3", 3))
        tbl.setItem(row_idx, 1, NumericTableWidgetItem(cd, cd))
        tbl.setItem(row_idx, 2, NumericTableWidgetItem(nm, nm))
        tbl.setItem(row_idx, 3, NumericTableWidgetItem(f"{p:.2f}", p))
        tbl.setItem(row_idx, 4, NumericTableWidgetItem(f"{pct:+.2f}%", pct))
    tbl.setSortingEnabled(True)


def test_fusion_ladder_search_ui_components(qapp):
    """验证搜索栏及计数标签成功挂载在 QTabWidget 右上角 cornerWidget。"""
    from PyQt6.QtCore import Qt
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, FusionSearchLineEdit

    dlg = FusionLadderDialog()
    try:
        assert hasattr(dlg, "ed_search")
        assert isinstance(dlg.ed_search, FusionSearchLineEdit)
        assert hasattr(dlg, "lbl_search_count")

        corner = dlg.tabs.cornerWidget(Qt.Corner.TopRightCorner)
        assert corner is not None
        assert dlg.ed_search.parent() is corner or dlg.ed_search.parent().parent() is corner
        assert dlg.ed_search.placeholderText() == "🔍 搜索代码/名称..."
        assert dlg.ed_search.isClearButtonEnabled() is True
    finally:
        dlg.close()


def test_fusion_ladder_search_by_code(qapp):
    """验证按股票代码精确与模糊过滤。"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        _setup_mock_table_data(dlg.tbl_live)
        dlg.tabs.setCurrentIndex(0)
        assert dlg.tbl_live.rowCount() == 4

        # 1. 精确代码过滤 "600688"
        dlg.ed_search.setText("600688")
        assert not dlg.tbl_live.isRowHidden(0)  # 600688 上海石化
        assert dlg.tbl_live.isRowHidden(1)
        assert dlg.tbl_live.isRowHidden(2)
        assert dlg.tbl_live.isRowHidden(3)
        assert dlg.lbl_search_count.text() == "1/4"

        # 2. 模糊代码过滤 "688" (应匹配 688128 中国电研，以及包含 688 的 600688 上海石化)
        dlg.ed_search.setText("688")
        assert not dlg.tbl_live.isRowHidden(0)  # 600688
        assert not dlg.tbl_live.isRowHidden(1)  # 688128
        assert dlg.tbl_live.isRowHidden(2)
        assert dlg.tbl_live.isRowHidden(3)
        assert dlg.lbl_search_count.text() == "2/4"

        # 3. 清空过滤
        dlg.ed_search.clear()
        for r in range(4):
            assert not dlg.tbl_live.isRowHidden(r)
        assert dlg.lbl_search_count.isHidden()
    finally:
        dlg.close()


def test_fusion_ladder_search_by_name(qapp):
    """验证按股票名称模糊过滤（中文子串匹配）。"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        _setup_mock_table_data(dlg.tbl_live)
        dlg.tabs.setCurrentIndex(0)

        # 1. 搜 "电研" -> 仅匹配 "中国电研"
        dlg.ed_search.setText("电研")
        assert dlg.tbl_live.isRowHidden(0)
        assert not dlg.tbl_live.isRowHidden(1)  # 中国电研
        assert dlg.tbl_live.isRowHidden(2)
        assert dlg.tbl_live.isRowHidden(3)
        assert dlg.lbl_search_count.text() == "1/4"

        # 2. 搜 "银行" -> 仅匹配 "西安银行"
        dlg.ed_search.setText("银行")
        assert dlg.tbl_live.isRowHidden(0)
        assert dlg.tbl_live.isRowHidden(1)
        assert not dlg.tbl_live.isRowHidden(2)  # 西安银行
        assert dlg.tbl_live.isRowHidden(3)
        assert dlg.lbl_search_count.text() == "1/4"

        # 3. 搜不存在的名称 -> 4 行全隐藏，提示 0/4
        dlg.ed_search.setText("茅台")
        for r in range(4):
            assert dlg.tbl_live.isRowHidden(r)
        assert dlg.lbl_search_count.text() == "0/4"
    finally:
        dlg.close()


def test_fusion_ladder_search_with_market_prefix(qapp):
    """验证用户复制带市场前缀（如 sh600688 / sz...）能够智能清洗并精准命中。"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        _setup_mock_table_data(dlg.tbl_live)
        dlg.tabs.setCurrentIndex(0)

        # 输入带有市场前缀的代码 "sh600688"
        dlg.ed_search.setText("sh600688")
        assert not dlg.tbl_live.isRowHidden(0)
        assert dlg.tbl_live.isRowHidden(1)
        assert dlg.tbl_live.isRowHidden(2)
        assert dlg.tbl_live.isRowHidden(3)
        assert dlg.lbl_search_count.text() == "1/4"
    finally:
        dlg.close()


def test_fusion_ladder_search_clipboard_paste_and_return_link(qapp):
    """验证剪贴板一键粘贴及回车键自动选中第一条匹配项并联动主图。"""
    from PyQt6.QtWidgets import QApplication
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    linked_stocks = []
    dlg._link_main_stock = lambda c, n: linked_stocks.append((c, n))

    try:
        _setup_mock_table_data(dlg.tbl_live)
        dlg.tabs.setCurrentIndex(0)

        # 1. 模拟向系统剪贴板存入 "中远海控" 并触发粘贴
        clipboard = QApplication.clipboard()
        clipboard.setText("中远海控")

        dlg.ed_search.setText(clipboard.text())
        assert not dlg.tbl_live.isRowHidden(3)  # 中远海控
        assert dlg.lbl_search_count.text() == "1/4"

        # 2. 模拟按回车键响应
        dlg._on_search_return_pressed()
        assert dlg.tbl_live.currentRow() == 3
        assert len(linked_stocks) >= 1
        assert linked_stocks[-1] == ("601919", "中远海控")
    finally:
        dlg.close()


def test_fusion_ladder_search_tab_switch_persistence(qapp):
    """验证切换选项卡时当前搜索过滤条件自动应用。"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        _setup_mock_table_data(dlg.tbl_live)
        _setup_mock_table_data(dlg.tbl_replay)

        # 在 Tab 0 设置搜索 "西安银行"
        dlg.tabs.setCurrentIndex(0)
        dlg.ed_search.setText("西安银行")
        assert not dlg.tbl_live.isRowHidden(2)
        assert dlg.tbl_live.isRowHidden(0)

        # 切换到 Tab 1 (按日回放表格)
        dlg.tabs.setCurrentIndex(1)
        assert not dlg.tbl_replay.isRowHidden(2)
        assert dlg.tbl_replay.isRowHidden(0)
        assert dlg.tbl_replay.isRowHidden(1)
        assert dlg.tbl_replay.isRowHidden(3)
        assert dlg.lbl_search_count.text() == "1/4"
    finally:
        dlg.close()
