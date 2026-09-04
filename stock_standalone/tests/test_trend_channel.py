import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import numpy as np
import pandas as pd
from JSONData.tdx_data_Day import calc_trend_channel, get_tdx_macd
from query_engine_util import PandasQueryEngine

def generate_mock_stock_data(n=60, trend="up"):
    np.random.seed(42)
    dates = pd.date_range(start="2026-01-01", periods=n, freq="D")
    
    if trend == "up":
        base_price = 10.0 + np.linspace(0, 15, n)
    elif trend == "down":
        base_price = 25.0 - np.linspace(0, 15, n)
    else:
        base_price = np.full(n, 15.0)
        
    noise = np.random.normal(0, 0.5, n)
    close = np.maximum(1.0, base_price + noise)
    high = close + np.abs(np.random.normal(0.5, 0.2, n))
    low = np.maximum(0.5, close - np.abs(np.random.normal(0.5, 0.2, n)))
    open_p = (close + low) / 2.0
    vol = np.random.randint(1000, 10000, size=n).astype(float)
    
    df = pd.DataFrame({
        'open': open_p,
        'high': high,
        'low': low,
        'close': close,
        'vol': vol
    }, index=dates)
    return df

def test_calc_trend_channel_up_trend():
    df = generate_mock_stock_data(60, trend="up")
    df_res = calc_trend_channel(df.copy())
    
    # 验证新列是否存在
    expected_cols = [
        'ch_upper', 'ch_mid', 'ch_lower', 'ch_slope', 'ch_slope_deg', 
        'ch_width', 'ch_height', 'ch_height_pct', 'ch_width_pct',
        'upper_height', 'lower_height', 'ch_pos', 'ch_dir',
        'fib_high', 'fib_low', 'fib_50', 
        'sig_bottom', 'sig_top', 'sig_launch', 'sig_escape', 'sig_start', 'trend_dir'
    ]
    for col in expected_cols:
        assert col in df_res.columns, f"缺少预期列: {col}"
        
    # 上升趋势校验
    assert df_res['ch_dir'].iloc[-1] == 1, "上升趋势下 ch_dir 应当为 1"
    assert df_res['ch_slope'].iloc[-1] > 0, "上升趋势下斜率应当大于 0"
    assert df_res['trend_dir'].iloc[-1] == 1, "MA9 趋势方向应为上升 (1)"

    # 通道尺寸数学等价性校验 (SSOT)
    last_row = df_res.iloc[-1]
    assert np.isclose(last_row['ch_height'], last_row['ch_width'], atol=1e-3)
    assert np.isclose(last_row['upper_height'] + last_row['lower_height'], last_row['ch_height'], atol=1e-2)
    expected_h_pct = (last_row['ch_upper'] - last_row['ch_lower']) / last_row['ch_mid'] * 100.0
    assert np.isclose(last_row['ch_height_pct'], expected_h_pct, atol=1e-2)
    expected_w_pct = (last_row['ch_width']) / last_row['close'] * 100.0
    assert np.isclose(last_row['ch_width_pct'], expected_w_pct, atol=1e-2)

def test_calc_trend_channel_down_trend():
    df = generate_mock_stock_data(60, trend="down")
    df_res = calc_trend_channel(df.copy())
    
    assert df_res['ch_dir'].iloc[-1] == -1, "下降趋势下 ch_dir 应当为 -1"
    assert df_res['ch_slope'].iloc[-1] < 0, "下降趋势下斜率应当小于 0"

def test_get_tdx_macd_integration():
    df = generate_mock_stock_data(60, trend="up")
    df_res = get_tdx_macd(df.copy())
    
    assert 'ch_upper' in df_res.columns, "get_tdx_macd 中未成功集成为通道指标"
    assert 'ch_mid' in df_res.columns
    assert 'ch_height_pct' in df_res.columns
    assert 'bandwidth_pct' in df_res.columns
    assert 'fib_50' in df_res.columns

def test_query_engine_channel_synonyms():
    df = generate_mock_stock_data(60, trend="up")
    df_res = get_tdx_macd(df.copy())
    
    engine = PandasQueryEngine()
    
    # 测试通过通道别名/同义词执行查询与排序
    query1 = "ch_dir == 1 and ch_slope > 0 and ch_height_pct > 0"
    res1 = engine.execute(df_res, query1)
    assert len(res1) > 0, "查询 ch_dir == 1 and ch_slope > 0 应当有匹配项"
    
    query2 = "close > ch_mid and fib_50 > 0 and ch_width_pct > 0 and bandwidth_pct > 0"
    res2 = engine.execute(df_res, query2)
    assert isinstance(res2, pd.DataFrame)
    assert len(res2) > 0
