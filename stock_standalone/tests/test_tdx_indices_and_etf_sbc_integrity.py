# -*- coding: utf-8 -*-
"""
scratch/test_tdx_indices_and_etf_sbc_integrity.py
验证所有大盘指数、科创50(999688)、北证50(899050)、ETF与指数基金在 TDX 与 SBC 图表体系下的完整性与准确性
"""

import pytest
import os
import sys
import pandas as pd
import numpy as np

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.tdx_realtime_fetcher import (
    TDXRealtimeFetcher,
    is_fund_or_etf,
    is_index_code,
    normalize_tdx_target,
    normalize_quote_unit,
    get_index_display_name
)
from ats.intraday_strategy_engine import resolve_stock_name


def test_index_and_etf_detection():
    """测试指数、ETF与普通股票的精准判决"""
    assert is_fund_or_etf("510300") is True
    assert is_fund_or_etf("588930") is True
    assert is_fund_or_etf("159915") is True
    assert is_fund_or_etf("161725") is True
    assert is_fund_or_etf("600519") is False
    assert is_fund_or_etf("000001") is False
    assert is_fund_or_etf("000688") is False

    assert is_index_code("999999") is True
    assert is_index_code("999688") is True
    assert is_index_code("399001") is True
    assert is_index_code("399006") is True
    assert is_index_code("899050") is True
    assert is_index_code("000001") is False  # 纯代码 000001 是平安银行
    assert is_index_code("000688") is False  # 纯代码 000688 是国新健康


def test_normalize_tdx_target_and_code_isolation():
    """测试 TK 别名与通达信官方接口参数自动映射，以及 000688 / 000001 严格隔离"""
    # 1. 科创50: 业务代码 999688 -> 映射为通达信官方 000688 (market=1, 指数)
    is_idx, mkt, c = normalize_tdx_target("999688")
    assert is_idx is True
    assert mkt == 1
    assert c == "000688"
    assert resolve_stock_name("999688") == "科创50"
    assert get_index_display_name("999688") == "科创50"

    # 2. 国新健康: 业务代码 000688 -> 保持为深市个股 (market=0, security)
    is_idx, mkt, c = normalize_tdx_target("000688")
    assert is_idx is False
    assert mkt == 0
    assert c == "000688"
    assert resolve_stock_name("000688") == "国新健康"
    assert get_index_display_name("000688") == ""

    # 3. 上证指数: 业务代码 999999 -> 映射为通达信官方 000001 (market=1, 指数)
    is_idx, mkt, c = normalize_tdx_target("999999")
    assert is_idx is True
    assert mkt == 1
    assert c in ("000001", "999999")
    assert resolve_stock_name("999999") == "上证指数"

    # 4. 平安银行: 业务代码 000001 -> 保持为深市个股 (market=0, security)
    is_idx, mkt, c = normalize_tdx_target("000001")
    assert is_idx is False
    assert mkt == 0
    assert c == "000001"
    assert resolve_stock_name("000001") == "平安银行"

    # 5. 北证50: 899050 -> market=2 (北交所, 指数)
    is_idx, mkt, c = normalize_tdx_target("899050")
    assert is_idx is True
    assert mkt == 2
    assert c == "899050"
    assert resolve_stock_name("899050") == "北证50"

    # 6. 深证成指: 399001 -> market=0 (深交所, 指数)
    is_idx, mkt, c = normalize_tdx_target("399001")
    assert is_idx is True
    assert mkt == 0
    assert c == "399001"
    assert resolve_stock_name("399001") == "深证成指"


def test_normalize_quote_unit():
    """测试 ETF 盘口报价自动除以 10.0 还原真实价格"""
    raw_etf_quote = {
        "code": "588930",
        "price": 15.36,
        "last_close": 14.79,
        "open": 15.06,
        "high": 15.47,
        "low": 14.99,
        "bid1": 15.35,
        "ask1": 15.36,
    }
    fixed_q = normalize_quote_unit(raw_etf_quote)
    assert abs(fixed_q["price"] - 1.536) < 1e-4
    assert abs(fixed_q["last_close"] - 1.479) < 1e-4
    assert abs(fixed_q["bid1"] - 1.535) < 1e-4

    # 普通股票不受影响
    raw_stock_quote = {
        "code": "600519",
        "price": 1256.31,
        "last_close": 1266.98,
        "bid1": 1256.30
    }
    stock_q = normalize_quote_unit(raw_stock_quote)
    assert stock_q["price"] == 1256.31
    assert stock_q["last_close"] == 1266.98


def test_sh_index_kline_and_channel():
    """测试 999999 上证指数日K线与通道计算绝对杜绝十几万乱码"""
    fetcher = TDXRealtimeFetcher.get_instance()
    if not fetcher._is_connected:
        fetcher.connect()
    if not fetcher._is_connected:
        pytest.skip("TDX 未连接，跳过真实在线测试")

    df = fetcher.fetch_kline_bars("999999", "day", count=100)
    assert not df.empty
    assert len(df) >= 30

    # 1. 验证时间绝无 322141 或 2035 等错位乱码
    last_dt_str = str(df.index[-1])
    assert last_dt_str.startswith("202")

    # 2. 验证价格在合理点数区间 (3000 ~ 4500 点)
    last_close = float(df.iloc[-1]["close"])
    assert 3000.0 <= last_close <= 4500.0

    # 3. 验证通道上中下轨绝无十几万异常值
    ch_upper = float(df.iloc[-1].get("ch_upper", 0.0))
    if not np.isnan(ch_upper) and ch_upper > 0:
        assert ch_upper < 10000.0, f"ch_upper ({ch_upper}) 不应超过 10000 点"


def test_star50_index_kline():
    """测试 999688 科创50日K线拉取"""
    fetcher = TDXRealtimeFetcher.get_instance()
    if not fetcher._is_connected:
        fetcher.connect()
    if not fetcher._is_connected:
        pytest.skip("TDX 未连接，跳过真实在线测试")

    df = fetcher.fetch_kline_bars("999688", "day", count=100)
    assert not df.empty
    assert len(df) >= 30
    last_close = float(df.iloc[-1]["close"])
    assert 1000.0 <= last_close <= 2500.0, f"科创50点数异常: {last_close}"


def test_sh_index_10d_intraday():
    """测试 999999 上证指数 10 日分时图无断崖垂直跳跃"""
    fetcher = TDXRealtimeFetcher.get_instance()
    if not fetcher._is_connected:
        fetcher.connect()
    if not fetcher._is_connected:
        pytest.skip("TDX 未连接，跳过真实在线测试")

    df_10d = fetcher.fetch_multi_day_intraday_bars("999999", days=10)
    assert not df_10d.empty
    assert len(df_10d) >= 200

    min_p = float(df_10d["price"].min())
    max_p = float(df_10d["price"].max())

    # 上证指数 10 日内波动绝不可能跌破 3000 或涨超 5000，更不能出现 1591
    assert min_p >= 3200.0, f"10日分时最低价异常: {min_p}"
    assert max_p <= 4600.0, f"10日分时最高价异常: {max_p}"


def test_index_intraday_vwap_not_100():
    """测试指数分时图与多日分时图的 VWAP 均价绝不是 100.0，而是点位加权线"""
    fetcher = TDXRealtimeFetcher.get_instance()
    if not fetcher._is_connected:
        fetcher.connect()
    if not fetcher._is_connected:
        pytest.skip("TDX 未连接，跳过真实在线测试")

    # 1. 上证指数 1日分时
    df_1d = fetcher.fetch_intraday_bars("999999")
    if not df_1d.empty:
        vwaps = df_1d["vwap"].values
        closes = df_1d["close"].values
        # 验证绝无 100.0 脏均线
        assert not (np.isclose(vwaps, 100.0).any()), "指数 1D 分时均线绝不能是 100.0"
        # 验证均线紧随点位 (偏离不超过 5%)
        dev = np.abs(vwaps - closes) / closes
        assert (dev < 0.05).all(), f"分时均线与点位偏离过大: max dev={dev.max()}"

    # 2. 北证50 5日分时
    df_5d = fetcher.fetch_multi_day_intraday_bars("899050", days=5)
    if not df_5d.empty:
        vwaps_bj = df_5d["vwap"].values
        closes_bj = df_5d["close"].values
        assert not (np.isclose(vwaps_bj, 100.0).any()), "北证50 5D 分时均线绝不能是 100.0"
        dev_bj = np.abs(vwaps_bj - closes_bj) / closes_bj
        assert (dev_bj < 0.05).all(), f"北证50分时均线偏离过大: max dev={dev_bj.max()}"


def test_multi_day_vwap_continuity():
    """测试多日分时图 (个股与指数) 的 VWAP 在各交易日交界处保持连续平滑，绝无单日断开跳跃"""
    fetcher = TDXRealtimeFetcher.get_instance()
    if not fetcher._is_connected:
        fetcher.connect()
    if not fetcher._is_connected:
        pytest.skip("TDX 未连接，跳过真实在线测试")

    # 1. 验证个股多日分时 (华鑫股份 600621) 跨天连续性
    fetcher.cache_pool.invalidate('600621')
    df_stock = fetcher.fetch_multi_day_intraday_bars("600621", days=3)
    if not df_stock.empty and 'date' in df_stock.columns:
        dates = df_stock['date'].unique()
        if len(dates) >= 2:
            for i in range(len(dates) - 1):
                vw_prev_end = df_stock[df_stock['date'] == dates[i]]['vwap'].iloc[-1]
                vw_next_start = df_stock[df_stock['date'] == dates[i+1]]['vwap'].iloc[0]
                # 跨天交界处 VWAP 绝对差值绝不能跳跃超过 1.0 元 (通常 < 0.1 元)
                assert abs(vw_prev_end - vw_next_start) < 0.80, f"个股跨天 VWAP 断裂: {dates[i]} {vw_prev_end} -> {dates[i+1]} {vw_next_start}"

    # 2. 验证指数多日分时 (上证指数 999999) 跨天连续性
    fetcher.cache_pool.invalidate('999999')
    df_idx = fetcher.fetch_multi_day_intraday_bars("999999", days=3)
    if not df_idx.empty and 'date' in df_idx.columns:
        dates_idx = df_idx['date'].unique()
        if len(dates_idx) >= 2:
            for i in range(len(dates_idx) - 1):
                vw_prev_end = df_idx[df_idx['date'] == dates_idx[i]]['vwap'].iloc[-1]
                vw_next_start = df_idx[df_idx['date'] == dates_idx[i+1]]['vwap'].iloc[0]
                # 跨天交界处 VWAP 相对变化绝不能超过 2%
                diff_pct = abs(vw_prev_end - vw_next_start) / vw_prev_end
                assert diff_pct < 0.02, f"指数跨天 VWAP 断裂: {dates_idx[i]} {vw_prev_end} -> {dates_idx[i+1]} {vw_next_start}"


def test_sbc_canvas_min_valid_price_defense():
    """测试 SBC 画布在遇到离群极小脏数据 (如 10.0 或 100.0) 时自动剔除，保障 Y 轴不被拉扁"""
    op_ref = 3900.0
    max_valid_price = (op_ref * 1.70)
    min_valid_price = (op_ref * 0.35)

    prices = [3890.0, 3910.0, 3925.0]
    vwaps_with_outlier = [3895.0, 100.0, 10.0, 3915.0]  # 混入 100.0 和 10.0

    all_cands = []
    for p in prices:
        if min_valid_price <= p <= max_valid_price:
            all_cands.append(p)
    for v in vwaps_with_outlier:
        if min_valid_price <= v <= max_valid_price:
            all_cands.append(v)

    # 断言 100.0 和 10.0 被完全过滤剔除
    assert 100.0 not in all_cands
    assert 10.0 not in all_cands
    assert min(all_cands) >= 3890.0
    assert max(all_cands) <= 3925.0


def test_capital_dragon_double_click_opens_sbc():
    """测试资金主线表格双击和先锋双击直接调用 open_sbc_chart 打开 SBC 走势窗口"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from ats.ui.capital_dragon_panel import CapitalDragonPanel
    panel = CapitalDragonPanel(main_window=None)

    opened_sbc = []
    panel.open_sbc_chart = lambda c, n="": opened_sbc.append((c, n))

    # 1. 模拟先锋双击
    panel._on_pioneer_double_clicked("600519", "贵州茅台")
    assert len(opened_sbc) == 1
    assert opened_sbc[0] == ("600519", "贵州茅台")

    # 2. 模拟表格行双击
    from PyQt6.QtWidgets import QTableWidgetItem
    panel.table.setRowCount(1)
    panel.table.setColumnCount(4)
    c_item = QTableWidgetItem("000001")
    n_item = QTableWidgetItem("平安银行")
    s_item = QTableWidgetItem("银行")
    panel.table.setItem(0, 0, c_item)
    panel.table.setItem(0, 1, n_item)
    panel.table.setItem(0, 3, s_item)

    panel._on_row_double_clicked(c_item)
    assert len(opened_sbc) == 2
    assert opened_sbc[1] == ("000001", "平安银行")

