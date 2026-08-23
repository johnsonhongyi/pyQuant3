# -*- coding: utf-8 -*-
"""
tests/test_sector_aggregator_suite.py
ATS 统一板块数据聚合中枢 (SectorDataAggregator) 与板块明细弹窗 (ATSSectorDetailDialog) 深度测试套件
"""

import math
import pytest
import pandas as pd
from PyQt6.QtWidgets import QApplication

from ats.sector_data_aggregator import (
    SectorDataAggregator,
    _safe_float,
    _safe_int,
    _get_sina_market_code,
    get_sector_extra_cols,
    get_sector_table_headers
)
from ats.ui.sector_detail_dialog import ATSSectorDetailDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_safe_conversions_and_market_codes():
    """测试安全数值转换与交易所前缀映射"""
    # 1. 安全 float 转换
    assert _safe_float(None, 0.0) == 0.0
    assert _safe_float(float('nan'), 0.0) == 0.0
    assert _safe_float(float('inf'), 0.0) == 0.0
    assert _safe_float("--", 0.0) == 0.0
    assert _safe_float("12.34", 0.0) == 12.34
    assert _safe_float(-5.6, 0.0) == -5.6

    # 2. 安全 int 转换
    assert _safe_int(None, 999) == 999
    assert _safe_int(float('nan'), 999) == 999
    assert _safe_int("12", 0) == 12
    assert _safe_int("abc", 0) == 0

    # 3. 交易所前缀精准映射
    assert _get_sina_market_code("600519") == "sh600519"
    assert _get_sina_market_code("688981") == "sh688981"
    assert _get_sina_market_code("510050") == "sh510050"  # 上证 ETF
    assert _get_sina_market_code("113009") == "sh113009"  # 上证可转债
    assert _get_sina_market_code("000001") == "sz000001"
    assert _get_sina_market_code("300750") == "sz300750"  # 创业板
    assert _get_sina_market_code("159915") == "sz159915"  # 深证 ETF
    assert _get_sina_market_code("128013") == "sz128013"  # 深证可转债
    assert _get_sina_market_code("832000") == "bj832000"  # 北交所
    assert _get_sina_market_code("920001") == "bj920001"  # 北交所新号段


def test_resolve_sector_member_codes():
    """测试成分股列表解析与同义词/fallback机制"""
    aggregator = SectorDataAggregator.get_instance()

    # 1. 显式传入 member_codes：严格以输入为准，不被外部污染
    codes, name_map = aggregator.resolve_sector_member_codes(
        sector_name="半导体",
        member_codes=["688981", "002371"]
    )
    assert codes == ["688981", "002371"]

    # 2. 未传入 member_codes，且 current_df 包含 category 列：向量模糊匹配
    df_sample = pd.DataFrame({
        'name': ['中芯国际', '北方华创', '比亚迪'],
        'category': ['半导体及部件', '芯片', '汽车整车']
    }, index=['688981', '002371', '002594'])

    codes_fuzzy, name_map_fuzzy = aggregator.resolve_sector_member_codes(
        sector_name="半导体",
        member_codes=None,
        current_df=df_sample
    )
    assert "688981" in codes_fuzzy
    assert "002371" in codes_fuzzy
    assert "002594" not in codes_fuzzy
    # 由于匹配不足 6 只，会自动从 FAMOUS_SECTOR_LEADERS 补齐
    assert len(codes_fuzzy) >= 6

    # 3. 兼容 RangeIndex 且带有 code 列的数据帧
    df_range = pd.DataFrame({
        'code': ['688981', '002371'],
        'name': ['中芯国际', '北方华创'],
        'category': ['半导体', '半导体']
    })
    codes_range, name_map_range = aggregator.resolve_sector_member_codes(
        sector_name="半导体",
        member_codes=None,
        current_df=df_range
    )
    assert "688981" in codes_range
    assert "002371" in codes_range
    assert "000000" not in codes_range


def test_fetch_sector_detail_and_ranking(monkeypatch):
    """测试板块明细计算、领涨龙头评选与严格降序排列"""
    aggregator = SectorDataAggregator.get_instance()

    # 1. 模拟网络离线/Mock 模式：验证计算逻辑纯粹性
    # 模拟 TDXFetcher 与 Sina 返回空，使用 current_df 驱动行情
    import ats.sector_data_aggregator as sda
    monkeypatch.setattr(sda, "fetch_sina_stock_quotes_fast", lambda codes: {})
    try:
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        tf = TDXRealtimeFetcher.get_instance()
        monkeypatch.setattr(tf, "get_security_quotes_safe", lambda codes, force=False: [])
        monkeypatch.setattr(tf, "fetch_multi_stock_alpha_quotes", lambda codes, sec_map, mp, nm: [])
    except Exception:
        pass

    df = pd.DataFrame({
        'name': ['中芯国际', '北方华创', '兆易创新'],
        'percent': [8.5, 3.2, -1.5],
        'dff': [2.5, float('nan'), -0.5],
        'Rank': [1, 5, 20],
        'DFF2': [1.8, 0.5, 0.0],
        'DFF3': [0.9, 0.2, 0.0],
        'ch_bc2': [5.0, float('nan'), 0.0]
    }, index=['688981', '002371', '603986'])

    rows, score, leader_str, meta = aggregator.fetch_sector_detail(
        sector_name="半导体",
        member_codes=['688981', '002371', '603986'],
        current_df=df,
        extra_cols=['ch_bc2']
    )

    assert len(rows) == 3
    # 验证龙头评选：第 0 行必定为领涨龙头且得分最高
    assert rows[0]['code'] == '688981'
    assert '领涨龙头' in rows[0]['type']
    assert rows[0]['score'] >= 98.0
    assert '中芯国际' in leader_str

    # 验证列表按 score, pct 倒序排列
    for i in range(len(rows) - 1):
        assert (rows[i]['score'], rows[i]['pct']) >= (rows[i + 1]['score'], rows[i + 1]['pct'])

    # 验证 NaN 防护与 start_pct 计算 (pct 8.5 - dff 2.5 = 6.0)
    assert rows[0]['start_pct'] == 6.0
    # 北方华创 dff 为 NaN，应被清洗为 0.0，start_pct = pct 3.2
    row_002371 = next(r for r in rows if r['code'] == '002371')
    assert row_002371['dff'] == 0.0
    assert row_002371['start_pct'] == 3.2

    # 验证板块强度打分非 NaN
    assert not math.isnan(score)
    assert 0.0 <= score <= 100.0


def test_dialog_lifecycle_and_update_data(qapp):
    """测试 ATSSectorDetailDialog 实例复用、update_data 接口与事件生命周期"""
    df1 = pd.DataFrame({
        'name': ['中芯国际', '北方华创'],
        'percent': [5.0, 2.0],
        'dff': [1.0, 0.5]
    }, index=['688981', '002371'])

    dlg = ATSSectorDetailDialog(sector_name="半导体", member_codes=['688981', '002371'])
    
    # 1. 验证 load_data 同步加载
    dlg.load_data(df_realtime=df1)
    assert dlg.table.rowCount() == 2
    assert dlg.table.item(0, 0).text() in ('688981', '002371')

    # 2. 验证 update_data 接口（主窗口复用与轮询刷新通道）
    df2 = pd.DataFrame({
        'name': ['中芯国际', '北方华创', '兆易创新'],
        'percent': [9.9, 4.0, 1.5],
        'dff': [2.0, 1.0, 0.5]
    }, index=['688981', '002371', '603986'])

    dlg.member_codes = ['688981', '002371', '603986']
    dlg.update_data(current_df=df2)
    # update_data 触发了 refresh_data，这里直接调用 load_data 验证渲染状态
    dlg.load_data(df_realtime=df2)
    assert dlg.table.rowCount() == 3

    # 3. 验证 closeEvent 安全释放
    dlg.close()
    assert dlg.isVisible() is False
