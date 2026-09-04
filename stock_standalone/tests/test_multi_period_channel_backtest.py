# -*- coding: utf-8 -*-
"""
tests/test_multi_period_channel_backtest.py — 多周期通道支撑线上量化策略与回测系统自动化测试套件
"""

import os
import sys
import math
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ats.multi_period_resampler import (
    normalize_kline_df,
    resample_kline,
    get_multi_period_klines
)
from ats.multi_period_channel_strategy import (
    calculate_single_period_channel,
    evaluate_multi_period_channel_strategy
)
from ats.multi_period_channel_backtester import MultiPeriodChannelBacktester


def generate_mock_daily_data(n: int = 120, trend: str = "up") -> pd.DataFrame:
    """生成确定性模拟日 K 线"""
    np.random.seed(42)
    dates = pd.date_range(start="2025-01-01", periods=n, freq="D")
    
    if trend == "up":
        base = 10.0 + np.linspace(0, 15, n)
    elif trend == "down":
        base = 25.0 - np.linspace(0, 15, n)
    else:
        base = np.full(n, 15.0)

    noise = np.random.normal(0, 0.2, n)
    close = np.maximum(1.0, base + noise)
    high = close + np.abs(np.random.normal(0.3, 0.1, n))
    low = np.maximum(0.5, close - np.abs(np.random.normal(0.3, 0.1, n)))
    open_p = (close + low) / 2.0
    vol = np.random.randint(1000, 5000, size=n).astype(float)
    amount = close * vol

    df = pd.DataFrame({
        'open': open_p,
        'high': high,
        'low': low,
        'close': close,
        'vol': vol,
        'amount': amount
    }, index=dates)
    return df


def test_01_multi_period_resampler_ohlcv():
    """测试 1: 验证日线到 2d, 3d, w, m 的重采样行数折算与 OHLCV 逻辑"""
    df_daily = generate_mock_daily_data(n=60, trend="up")
    mp = get_multi_period_klines(df_daily, periods=['d', '2d', '3d', 'w', 'm'])

    assert len(mp['d']) == 60
    assert len(mp['2d']) == 30
    assert len(mp['3d']) == 20
    assert 8 <= len(mp['w']) <= 12
    assert 2 <= len(mp['m']) <= 4

    # 验证末端 close 对齐
    last_close = df_daily['close'].iloc[-1]
    for p in ['d', '2d', '3d', 'w', 'm']:
        assert math.isclose(mp[p]['close'].iloc[-1], last_close, abs_tol=1e-3)


def test_02_resampler_anti_lookahead_slice():
    """测试 2: 验证按日期截断重采样的防未来函数特性"""
    df_daily = generate_mock_daily_data(n=100, trend="up")
    cutoff_date = "2025-02-15"

    mp_sliced = get_multi_period_klines(df_daily, periods=['d', '2d'], as_of_date=cutoff_date)
    # 所有周期最大日期严禁超过 cutoff_date
    assert str(mp_sliced['d'].index[-1])[:10] <= cutoff_date
    assert str(mp_sliced['2d'].index[-1])[:10] <= cutoff_date


def test_03_single_period_channel_support_calculation():
    """测试 3: 验证单周期通道与支撑线提取"""
    df_daily = generate_mock_daily_data(n=60, trend="up")
    res = calculate_single_period_channel(df_daily, period_tag='d')

    assert res["period"] == 'd'
    assert res["supp_price"] > 0
    assert res["reversal_price"] > 0
    assert "is_above_support" in res
    assert "dist_to_supp_pct" in res
    assert res["score"] >= 60.0
    assert "ch_height" in res
    assert "ch_height_pct" in res
    assert "upper_height" in res
    assert "lower_height" in res
    assert "ch_pos" in res
    if res["ch_upper"] > 0 and res["ch_lower"] > 0:
        assert res["ch_height"] >= 0
        assert res["upper_height"] >= 0
        assert res["lower_height"] >= 0


def test_04_multi_period_resonance_strategy_up_trend():
    """测试 4: 验证上升通道中多周期通道共振判定与高分触发"""
    df_daily = generate_mock_daily_data(n=90, trend="up")
    res = evaluate_multi_period_channel_strategy(df_daily)

    assert res["above_support_count"] >= 3
    assert res["score"] >= 80.0
    assert res["is_buy_signal"] is True
    assert "支撑" in res["buy_suggest"]


def test_05_multi_period_resonance_strategy_down_trend():
    """测试 5: 验证持续下跌空头行情下防诱多与低分拦截"""
    df_down = generate_mock_daily_data(n=90, trend="down")
    res = evaluate_multi_period_channel_strategy(df_down)

    assert res["is_buy_signal"] is False
    assert res["score"] < 75.0


def test_06_backtester_simulation_and_metrics():
    """测试 6: 验证逐日回测引擎撮合、出场控制与量化指标计算"""
    df_daily = generate_mock_daily_data(n=100, trend="up")
    backtester = MultiPeriodChannelBacktester(
        initial_capital=100000.0,
        warmup_bars=30,
        min_signal_score=80.0
    )

    report = backtester.run_backtest_on_df(df_daily, code="600108", name="测试标的")

    assert report["total_trading_days"] == 70  # 100 - 30
    assert report["initial_capital"] == 100000.0
    assert "total_return_pct" in report
    assert "win_rate_pct" in report
    assert "profit_factor" in report
    assert "trades_df" in report

    # 验证 Markdown 格式化能力
    md = backtester.format_report_markdown(report)
    assert "核心绩效总结" in md
    assert "600108" in md
