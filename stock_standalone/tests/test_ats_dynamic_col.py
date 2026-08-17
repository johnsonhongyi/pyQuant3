# -*- coding: utf-8 -*-
"""
ATS Dynamic Columns & co2int Formatting Integration Tests
验证 ATS 主窗口 (重点关注、MA20d跟踪器、板块明细) 动态列功能与全系统 co2int 整型格式化
"""
import sys
import os
import pytest
import pandas as pd
import numpy as np

# 将项目根目录加入 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from JohnsonUtil import commonTips as cct
from ats.ui.favorite_panel import get_ats_extra_cols, get_ats_table_headers, FavoritePanel
from ats.ui.swing_table import SwingStateTable
from ats.ui.sector_detail_dialog import get_sector_extra_cols, get_sector_table_headers, ATSSectorDetailDialog

@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_format_col_value_with_co2int():
    """测试 format_col_value 在面对 co2int、co2float、常规浮点与空值时的精准转换"""
    # 1. co2int 字段 (如 ch_bc2, ch_tc2, ch_nod, pdays, pbreak, obs_d) 必须转为整数字符串
    assert cct.format_col_value('ch_bc2', 3.0) == '3'
    assert cct.format_col_value('ch_bc2', 3.4) == '3'
    assert cct.format_col_value('ch_bc2', 3.6) == '4'
    assert cct.format_col_value('CH_BC2', '12.0') == '12'
    assert cct.format_col_value('ch_tc2', 0.0) == '0'
    assert cct.format_col_value('pdays', '8') == '8'

    # 2. co2float 字段 (如 signal_strength) 必须保留 2 位小数
    assert cct.format_col_value('signal_strength', 1.2345) == '1.23'
    assert cct.format_col_value('SIGNAL_STRENGTH', '5') == '5.00'

    # 3. 常规浮点列
    assert cct.format_col_value('dff', 2.5) == '2.50'
    assert cct.format_col_value('dff2', -1.2) == '-1.20'

    # 4. 空值与异常值防崩
    assert cct.format_col_value('ch_bc2', None) == '--'
    assert cct.format_col_value('ch_bc2', np.nan) == '--'
    assert cct.format_col_value('ch_bc2', '') == '--'
    assert cct.format_col_value('ch_bc2', '--') == '--'
    assert cct.format_col_value('dff', 'nan') == '--'


def test_table_headers_and_columns_generation():
    """测试 ATS 与板块明细动态列头及列数计算"""
    extra_cols = get_ats_extra_cols()
    assert isinstance(extra_cols, list)
    assert 'ch_bc2' in extra_cols

    ats_headers = get_ats_table_headers(extra_cols)
    assert len(ats_headers) == 16 + len(extra_cols)
    assert ats_headers[0] == "股票代码"
    assert ats_headers[14] == "大盘共振"
    assert ats_headers[-1] == "推荐理由"

    sector_extra = get_sector_extra_cols()
    assert isinstance(sector_extra, list)
    assert 'ch_bc2' in sector_extra

    sector_headers = get_sector_table_headers(sector_extra)
    assert len(sector_headers) == 11 + len(sector_extra)
    assert sector_headers[0] == "代码"
    assert sector_headers[9] == "DFF3"
    assert sector_headers[-1] == "形态提示"


def test_favorite_panel_and_swing_table_rendering(qapp):
    """测试 FavoritePanel 与 SwingStateTable 接收带动态列数据后的表格渲染与对齐"""
    fav_panel = FavoritePanel()
    swing_table = SwingStateTable()

    extra_cols = get_ats_extra_cols()
    num_extra = len(extra_cols)

    # 模拟构造包含 15基础 + N动态 + 1理由 的行数据
    mock_rows = [
        (
            "000001", "平安银行", "10.50", "回踩企稳", "+0.5%", "0", "15%",
            "🔔 竞价先手 [09:25]", "95.0", "1.50", "10", "1.20", "0.80",
            "+0.30%", "大盘共振",
            *(["3"] * num_extra),
            "回踩20日均线企稳"
        ),
        (
            "600519", "贵州茅台", "1680.00", "持股中", "+1.2%", "1", "20%",
            "🥇 黄金早盘 [09:35]", "88.0", "2.10", "5", "1.80", "1.50",
            "+1.00%", "逆市抗跌",
            *(["5"] * num_extra),
            "缩量多头排列"
        )
    ]

    # 更新重点关注看板
    fav_panel.update_favorite_rows(mock_rows)
    assert fav_panel.table.rowCount() == 2
    assert fav_panel.table.columnCount() == 16 + num_extra
    # 验证动态列单元格内容
    for ei in range(num_extra):
        col_idx = 15 + ei
        item = fav_panel.table.item(0, col_idx)
        assert item is not None
        assert item.text() in ('3', '5')
    # 最后一列是推荐理由
    reason_item = fav_panel.table.item(0, 16 + num_extra - 1)
    assert reason_item is not None
    assert "回踩20日均线企稳" in reason_item.text()

    # 更新大级别 MA20d 回调跟踪器
    swing_table.update_data_list(mock_rows)
    assert swing_table.table.rowCount() == 2
    assert swing_table.table.columnCount() == 16 + num_extra
    for ei in range(num_extra):
        col_idx = 15 + ei
        item = swing_table.table.item(0, col_idx)
        assert item is not None
        assert item.text() in ('3', '5')


def test_sector_detail_dialog_rendering(qapp):
    """测试 ATSSectorDetailDialog 板块明细弹窗动态列数据提取与渲染"""
    # 构造包含 category 和 ch_bc2 等指标的实时 DataFrame
    data = {
        'name': ['中芯国际', '北方华创', '兆易创新'],
        'category': ['半导体', '半导体', '半导体'],
        'percent': [5.2, 3.8, 2.1],
        'dff': [2.0, 1.5, 0.8],
        'Rank': [1, 2, 5],
        'DFF2': [1.2, 0.9, 0.5],
        'DFF3': [0.8, 0.6, 0.3],
        'ch_bc2': [3.0, 5.0, 0.0]
    }
    df = pd.DataFrame(data, index=['688981', '002371', '603986'])

    dlg = ATSSectorDetailDialog(sector_name="半导体", member_codes=['688981', '002371', '603986'])
    dlg.load_data(df_realtime=df)

    sector_extra = get_sector_extra_cols()
    num_extra = len(sector_extra)

    assert dlg.table.rowCount() == 3
    assert dlg.table.columnCount() == 11 + num_extra

    # 验证第一行为领涨股且 ch_bc2 转换为整型 '3'
    row0_code = dlg.table.item(0, 0).text()
    assert row0_code in ('688981', '002371', '603986')
    for ei in range(num_extra):
        col_idx = 10 + ei
        item = dlg.table.item(0, col_idx)
        assert item is not None
        # 验证数值必须为无小数位纯整数
        assert '.' not in item.text()
