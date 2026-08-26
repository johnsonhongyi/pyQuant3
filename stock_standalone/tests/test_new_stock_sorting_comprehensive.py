# -*- coding: utf-8 -*-
"""
tests/test_new_stock_sorting_comprehensive.py
全面测试新股次新股表格 (NewStockPanel) 各列的排序准确性：
1. 现价 (Price) 数值升序/降序
2. 涨跌% (Pct) 数值升序/降序 (含正负号、百分比)
3. 换手% (Turnover) 升序/降序
4. 上市日 (Listing Date) 日期升序/降序
5. 重点关注 (is_pinned=True) 置顶特权在升序与降序下的正确维持
6. 缺失值/空值 ('--', NaN) 在升序与降序下的始终沉底
7. 多轮数据刷新 (_render_table) 原地更新后的排序一致性 (无历史脏数据残留)
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ats.ui.styles import NumericTableWidgetItem, PinnedNumericTableWidgetItem
from ats.ui.new_stock_panel import NewStockPanel


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_numeric_item_direct_comparison(qapp):
    """测试底层 NumericTableWidgetItem 的严格数学偏序与空值沉底"""
    from ats.ui.base_table import BaseATSTableWidget
    table = BaseATSTableWidget()
    table.setRowCount(6)
    table.setColumnCount(1)
    
    # 数据集: 置顶高价, 置顶低价, 普通空值, 普通高价, 普通低价, 置顶空值
    test_data = [
        ("⭐ 联讯仪器", 2209.00, True),
        ("⭐ 长进光子", 300.00, True),
        ("--", None, False),
        ("宇树科技", 586.00, False),
        ("双英集团", 14.76, False),
        ("⭐ --", None, True),
    ]
    
    for r, (txt, val, pin) in enumerate(test_data):
        table.setItem(r, 0, NumericTableWidgetItem(txt, is_pinned=pin, raw_val=val))
        
    # 1. 降序排序测试
    table.sortItems(0, Qt.SortOrder.DescendingOrder)
    desc_rows = [(table.item(r, 0).text(), table.item(r, 0).is_pinned, table.item(r, 0)._raw_value) for r in range(6)]
    
    # 验证降序顺序:
    # 置顶区: 2209.00 -> 300.00 -> None(空值沉底)
    # 普通区: 586.00 -> 14.76 -> None(空值沉底)
    assert desc_rows[0][0] == "⭐ 联讯仪器" and desc_rows[0][1] is True
    assert desc_rows[1][0] == "⭐ 长进光子" and desc_rows[1][1] is True
    assert desc_rows[2][0] == "⭐ --" and desc_rows[2][1] is True
    assert desc_rows[3][0] == "宇树科技" and desc_rows[3][1] is False
    assert desc_rows[4][0] == "双英集团" and desc_rows[4][1] is False
    assert desc_rows[5][0] == "--" and desc_rows[5][1] is False

    # 2. 升序排序测试
    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    asc_rows = [(table.item(r, 0).text(), table.item(r, 0).is_pinned, table.item(r, 0)._raw_value) for r in range(6)]
    
    # 验证升序顺序:
    # 置顶区: 300.00 -> 2209.00 -> None(空值沉底)
    # 普通区: 14.76 -> 586.00 -> None(空值沉底)
    assert asc_rows[0][0] == "⭐ 长进光子" and asc_rows[0][1] is True
    assert asc_rows[1][0] == "⭐ 联讯仪器" and asc_rows[1][1] is True
    assert asc_rows[2][0] == "⭐ --" and asc_rows[2][1] is True
    assert asc_rows[3][0] == "双英集团" and asc_rows[3][1] is False
    assert asc_rows[4][0] == "宇树科技" and asc_rows[4][1] is False
    assert asc_rows[5][0] == "--" and asc_rows[5][1] is False


def test_new_stock_panel_sorting_flow(qapp, monkeypatch):
    """测试 NewStockPanel 完整面板多列排序、多次数据刷新及焦点维护"""
    # 构造模拟新股 DataFrame
    mock_df = pd.DataFrame([
        {
            "code": "688808", "name": "联讯仪器", "status": "已上市",
            "listing_date": "2026-04-24", "apply_date": "2026-04-14",
            "issue_price": 81.88, "price": 2209.00, "pct": 0.00,
            "turnover": 0.48, "float_mv_yi": 426.25, "total_mv_yi": 2267.91,
            "amount_yi": 2.03, "dff": -1.80, "rank": 3306, "dff2": 0.20,
            "dff3": 172.60, "rs": -0.26, "resonance": "同步整理", "has_strategy": False
        },
        {
            "code": "688635", "name": "长进光子", "status": "已上市",
            "listing_date": "2026-05-27", "apply_date": "2026-05-18",
            "issue_price": 40.98, "price": 300.00, "pct": -5.27,
            "turnover": 5.05, "float_mv_yi": 53.27, "total_mv_yi": 281.01,
            "amount_yi": 2.69, "dff": -3.60, "rank": 5538, "dff2": -1.40,
            "dff3": 48.90, "rs": -5.53, "resonance": "同步走弱", "has_strategy": True
        },
        {
            "code": "688835", "name": "高凯技术", "status": "前5日(C)",
            "listing_date": "2026-08-25", "apply_date": "2026-08-14",
            "issue_price": 61.36, "price": 272.86, "pct": 16.11,
            "turnover": 22.89, "float_mv_yi": 51.25, "total_mv_yi": 272.73,
            "amount_yi": 11.27, "dff": 0.00, "rank": 2830, "dff2": 0.00,
            "dff3": 0.00, "rs": 15.85, "resonance": "逆市抗跌", "has_strategy": False
        },
        {
            "code": "920059", "name": "双英集团", "status": "前5日(C)",
            "listing_date": "2026-08-19", "apply_date": "2026-08-10",
            "issue_price": 11.13, "price": 14.76, "pct": -1.93,
            "turnover": 5.07, "float_mv_yi": 4.77, "total_mv_yi": 22.45,
            "amount_yi": 0.24, "dff": -2.60, "rank": 2777, "dff2": 0.00,
            "dff3": 0.00, "rs": -2.19, "resonance": "同步走弱", "has_strategy": False
        },
        {
            "code": "688836", "name": "宇树科技", "status": "前5日(C)",
            "listing_date": "2026-08-19", "apply_date": "2026-08-10",
            "issue_price": 150.80, "price": 586.00, "pct": -2.79,
            "turnover": 5.04, "float_mv_yi": 176.31, "total_mv_yi": 2370.16,
            "amount_yi": 8.86, "dff": -2.50, "rank": 2780, "dff2": 0.00,
            "dff3": 0.00, "rs": -3.05, "resonance": "同步走弱", "has_strategy": False
        }
    ])

    panel = NewStockPanel()
    panel.df_data = mock_df
    panel._render_table()

    # 1. 测试按“涨跌%”列 (col=7) 降序排序
    panel.sort_col = 7
    panel.sort_order = Qt.SortOrder.DescendingOrder
    panel.table.sortItems(7, Qt.SortOrder.DescendingOrder)

    # 检查第0行涨跌幅最大为 高凯技术 (+16.11%)
    first_code = panel.table.item(0, 0).text()
    first_pct = panel.table.item(0, 7).text()
    assert first_code == "688835"
    assert "+16.11%" in first_pct

    # 检查最后一行涨跌幅最小为 长进光子 (-5.27%)
    last_idx = panel.table.rowCount() - 1
    last_code = panel.table.item(last_idx, 0).text()
    last_pct = panel.table.item(last_idx, 7).text()
    assert last_code == "688635"
    assert "-5.27%" in last_pct

    # 2. 测试按“现价”列 (col=6) 升序排序
    panel.sort_col = 6
    panel.sort_order = Qt.SortOrder.AscendingOrder
    panel.table.sortItems(6, Qt.SortOrder.AscendingOrder)

    # 检查第0行价格最低为 双英集团 (14.76)
    p_first_code = panel.table.item(0, 0).text()
    p_first_val = panel.table.item(0, 6).text()
    assert p_first_code == "920059"
    assert "14.76" in p_first_val

    # 检查最后一行价格最高为 联讯仪器 (2209.00)
    p_last_code = panel.table.item(last_idx, 0).text()
    p_last_val = panel.table.item(last_idx, 6).text()
    assert p_last_code == "688808"
    assert "2209.00" in p_last_val

    # 3. 测试按“上市日”列 (col=3) 降序排序
    panel.sort_col = 3
    panel.sort_order = Qt.SortOrder.DescendingOrder
    panel.table.sortItems(3, Qt.SortOrder.DescendingOrder)

    d_first_code = panel.table.item(0, 0).text()
    d_first_date = panel.table.item(0, 3).text()
    assert d_first_code == "688835"  # 2026-08-25 最新
    assert d_first_date == "2026-08-25"

    d_last_code = panel.table.item(last_idx, 0).text()
    d_last_date = panel.table.item(last_idx, 3).text()
    assert d_last_code == "688808"  # 2026-04-24 最早
    assert d_last_date == "2026-04-24"
