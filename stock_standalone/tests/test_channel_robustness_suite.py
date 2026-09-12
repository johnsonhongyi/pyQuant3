# -*- coding: utf-8 -*-
"""
通道算法高可用、近端波段自适应寻优与极端边界防穿底自动化测试套件
验证 300400 等股票在历史暴跌后触底反弹、跨周期切片、极端数据外推下的通道三轨健康度与策略防呆机制。
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest
import numpy as np
import pandas as pd
from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df, calc_trend_channel
from stock_logic_utils import generate_channel_strategy_text


def test_stock_300400_channel_stability():
    """验证 300400 劲拓股份最新日线通道指标的健康度"""
    df = get_tdx_Exp_day_to_df('300400')
    assert df is not None and not df.empty, "300400 日线数据不能为空"
    last = df.iloc[-1]
    
    close_p = float(last['close'])
    upper_p = float(last['ch_upper'])
    mid_p = float(last['ch_mid'])
    lower_p = float(last['ch_lower'])
    deg_val = float(last['ch_slope_deg'])
    pos_val = float(last['ch_pos'])
    width_val = float(last['ch_width'])

    # 1. 通道三轨合理价格区间断言
    assert 30.0 <= upper_p <= 45.0, f"上轨异常: {upper_p}"
    assert 25.0 <= mid_p <= 40.0, f"中轨异常: {mid_p}"
    assert 20.0 <= lower_p <= 35.0, f"下轨异常: {lower_p}"
    assert upper_p > mid_p > lower_p, "三轨必须保持严格递增关系"
    assert width_val >= 3.0, f"通道宽度太小: {width_val}"

    # 2. 动能倾角与位置合理性断言 (绝不是 -89.99° 或 296500000000%)
    assert deg_val > 10.0, f"反弹行情中通道倾角应为多头: {deg_val}"
    assert 0.0 <= pos_val <= 100.0, f"通道位置百分比必须在正常区间: {pos_val}"
    assert last['ch_dir'] == 1, "通道方向应判定为多头上升"


def test_stock_300400_historical_slices_no_collapse():
    """验证 300400 在 2026-08-25 ~ 2026-09-02 历史反弹期各切片均无 0.01 塌缩"""
    df = get_tdx_Exp_day_to_df('300400')
    n = len(df)
    assert n >= 70, f"数据长度不足 70: {n}"

    # 测试 len 从 63 到 70 每一个历史交易日切片
    for l in range(63, n + 1):
        sub = df.iloc[:l].copy()
        res = calc_trend_channel(sub)
        last = res.iloc[-1]
        
        u = float(last['ch_upper'])
        m = float(last['ch_mid'])
        lo = float(last['ch_lower'])
        deg = float(last['ch_slope_deg'])
        pos = float(last['ch_pos'])
        dt = sub.index[-1]

        # 核心铁律断言：突破前高开启主升浪后 (l >= 64, 2026-09-03 起) 确立为明确上升通道 (deg > 40°)，绝不能出现 0.01 塌缩
        if l >= 64:
            assert u > 25.0, f"切片 len={l} ({dt}) 上轨塌缩: {u}"
            assert m > 20.0, f"切片 len={l} ({dt}) 中轨塌缩: {m}"
            assert lo > 15.0, f"切片 len={l} ({dt}) 下轨塌缩: {lo}"
            assert u > m > lo, f"切片 len={l} ({dt}) 三轨倒挂"
            assert deg > 40.0, f"切片 len={l} ({dt}) 突破后应为强势多头通道: {deg}"
            assert -50.0 <= pos <= 150.0, f"切片 len={l} ({dt}) pos 溢出: {pos}"
        else:
            # 突破前 (l=63) 处于暴跌通道向右外推停画阶段 (通达信 DRAWNULL/NaN)，绝不出现 0.01 塌缩
            assert pd.isna(u) or u > 25.0, f"切片 len={l} ({dt}) 出现 0.01 塌缩: {u}"


def test_multi_period_channel_consistency():
    """验证 300400 在 d, 2d, 3d, 5d 各周期下的通道指标一致性与健康度"""
    periods = ['d', '2d', '3d', '5d']
    for p in periods:
        df_p = get_tdx_Exp_day_to_df('300400', resample=p) if p != 'd' else get_tdx_Exp_day_to_df('300400')
        assert df_p is not None and not df_p.empty, f"{p} 周期数据不能为空"
        last = df_p.iloc[-1]
        
        u = float(last['ch_upper'])
        m = float(last['ch_mid'])
        lo = float(last['ch_lower'])
        deg = float(last['ch_slope_deg'])
        pos = float(last['ch_pos'])

        # 杜绝 0.01 塌缩；对于大周期暴跌通道外推停画 (NaN / -101)，遵照通达信官方 DRAWNULL
        if u != -101.0 and pd.notna(u):
            assert u > 25.0, f"{p} 周期上轨塌缩: {u}"
            assert m > 20.0, f"{p} 周期中轨塌缩: {m}"
            assert lo > 15.0, f"{p} 周期下轨塌缩: {lo}"
            assert u > m > lo, f"{p} 周期三轨未顺排: u={u}, m={m}, lo={lo}"
        if p == 'd':
            assert u > 25.0, f"{p} 日线必须为有效主通道: {u}"
            assert deg > 15.0, f"{p} 周期倾角应为多头: {deg}"
            assert -50.0 <= pos <= 200.0, f"{p} 周期位置异常: {pos}"


def test_generate_channel_strategy_text_safety_and_fallback():
    """验证策略指引文本生成器的防呆拦截与自愈机制"""
    # 场景 1: 传入历史异常塌缩数据 (上中下轨均为 0.01，pos 爆炸)
    corrupted_row = {
        'close': 33.65,
        'ch_upper': 0.01,
        'ch_mid': 0.01,
        'ch_lower': 0.01,
        'ch_pos': 296500000000.0,
        'ch_slope_deg': -89.99,
        'ch_pattern': 1
    }
    strat_text = generate_channel_strategy_text(corrupted_row)
    assert strat_text == "", f"脏数据必须被安全拦截，不得生成指引，当前返回:\n{strat_text}"

    # 场景 2: 传入倒挂数据 (upper <= lower)
    inverted_row = {
        'close': 33.65,
        'ch_upper': 20.0,
        'ch_mid': 25.0,
        'ch_lower': 30.0,
        'ch_pos': 50.0
    }
    assert generate_channel_strategy_text(inverted_row) == "", "倒挂数据必须拦截"

    # 场景 3: 传入正常 300400 数据，验证策略计划正常生成
    valid_row = {
        'close': 33.65,
        'ch_upper': 37.87,
        'ch_mid': 32.47,
        'ch_lower': 28.15,
        'ch_pos': 56.6,
        'ch_slope_deg': 46.76,
        'ch_pattern': 1
    }
    res_text = generate_channel_strategy_text(valid_row)
    assert "🎯 自动通道实战策略计划与操作指引" in res_text
    assert "通道三轨: 上轨 = 37.87 元 | 中轨 = 32.47 元 | 下轨 = 28.15 元" in res_text
    assert "最新收盘价: 33.65 元 (ch_pos = 56.6%)" in res_text
    assert "0.01" not in res_text, "正常输出绝不能含有 0.01 元"

    # 场景 4: 传入仅有 code="300400" 的空字典，验证自愈重算
    heal_row = {'code': '300400', 'close': 33.65}
    heal_text = generate_channel_strategy_text(heal_row)
    assert "🎯 自动通道实战策略计划与操作指引" in heal_text
    assert any(f"上轨 = {val}." in heal_text for val in [37, 38, 39, 40])


def test_extreme_data_extrapolation_protection():
    """验证极端单边暴跌后横盘的合成数据不发生穿底与负值"""
    # 构造合成极端数据：从 100 元连续暴跌到 10 元，随后横盘 40 天
    dates = pd.date_range('2026-01-01', periods=60)
    closes = np.zeros(60)
    closes[:20] = np.linspace(100.0, 10.0, 20)  # 暴跌
    closes[20:] = np.linspace(10.0, 11.0, 40)   # 底部微幅震荡
    
    highs = closes + 1.0
    lows = np.maximum(0.5, closes - 1.0)
    opens = closes - 0.2
    
    df_extreme = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'vol': 10000.0
    }, index=dates)

    res = calc_trend_channel(df_extreme)
    last = res.iloc[-1]
    
    assert last['ch_upper'] > 0.5, f"极端外推上轨不能为 0: {last['ch_upper']}"
    assert last['ch_mid'] > 0.5, f"极端外推中轨不能为 0: {last['ch_mid']}"
    assert last['ch_lower'] > 0.1, f"极端外推下轨不能为 0: {last['ch_lower']}"
    assert last['ch_upper'] > last['ch_lower'], "极端数据三轨不能重合"
    assert -100.0 <= last['ch_pos'] <= 200.0, f"极端数据 pos 必须受控: {last['ch_pos']}"


def test_stock_601890_ascending_channel_stability():
    """验证 601890 亚星锚链在开盘前及历史各切片下保持健康上升通道，绝不误判为 -67.5° 暴跌"""
    df = get_tdx_Exp_day_to_df('601890')
    assert df is not None and len(df) >= 60
    # 验证 2026-09-08 盘后 (即 09-09 早上开盘前)
    df_prev = df.iloc[:-1].copy()
    res_prev = calc_trend_channel(df_prev)
    last_prev = res_prev.iloc[-1]
    
    assert last_prev['ch_dir'] == 1, f"09-08 盘后通道方向必须为 1: {last_prev['ch_dir']}"
    assert last_prev['ch_slope_deg'] > 10.0, f"09-08 盘后倾角必须为正: {last_prev['ch_slope_deg']}"
    assert 9.5 <= last_prev['ch_upper'] <= 11.5, f"09-08 盘后上轨异常: {last_prev['ch_upper']}"
    assert 8.5 <= last_prev['ch_lower'] <= 9.3, f"09-08 盘后下轨异常: {last_prev['ch_lower']}"
    assert 0.0 <= last_prev['ch_pos'] <= 100.0, f"09-08 盘后位置应在通道内: {last_prev['ch_pos']}"

