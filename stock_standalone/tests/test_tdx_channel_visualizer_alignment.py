# -*- coding: utf-8 -*-
"""
通达信通道、上涨支撑线与可视化数据全面对齐专项回归测试集 (SSOT)
覆盖个股:
  - 002384 东山精密: 可视化三轨非 NaN、对齐通达信三轨与 CDP 支撑反转、绝无 MID:-
  - 600353 旭光电子: 宏观大通道坚定为下跌通道 (ch_dir == -1)、上涨支撑线破位精准识别
  - 300563 神宇股份: 上涨通道 (ch_dir == 1)、KX DRAWLINE 支撑线无限延伸至最新天、下轨双共振、现价动态 ch_pos > 90%
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest
import numpy as np
import pandas as pd
from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df, calc_trend_channel
import trade_visualizer_qt6 as tv
from stock_logic_utils import generate_channel_strategy_text


def test_002384_dongshan_precision_channel_and_visualizer_alignment():
    """测试 002384 东山精密通道三轨非 NaN，完全对齐通达信"""
    df = get_tdx_Exp_day_to_df('002384')
    assert df is not None and len(df) >= 60, "东山精密日线数据不足"
    last = df.iloc[-1]
    n = len(df)

    # 1. 引擎层指标验证
    ch_upper = float(last['ch_upper'])
    ch_mid = float(last['ch_mid'])
    ch_lower = float(last['ch_lower'])
    ch_dir = int(last['ch_dir'])

    assert ch_dir == -1, f"东山精密从280暴跌下来宏观方向应为下跌通道: {ch_dir}"
    assert 200.0 <= ch_upper <= 230.0, f"上轨应在214元附近: {ch_upper}"
    assert 185.0 <= ch_mid <= 205.0, f"中轨应在194元附近: {ch_mid}"
    assert 160.0 <= ch_lower <= 180.0, f"下轨应在172元附近: {ch_lower}"
    assert ch_upper > ch_mid > ch_lower, "三轨未正确顺排"

    # 2. 可视化 calc_auto_channel 验证 (绝不出现 NaN)
    mid, up, dn, k, idx_far = tv.calc_auto_channel(df)
    assert pd.notna(mid[-1]), "可视化最新中轨不能为 NaN"
    assert pd.notna(up[-1]), "可视化最新上轨不能为 NaN"
    assert pd.notna(dn[-1]), "可视化最新下轨不能为 NaN"
    assert up[-1] > mid[-1] > dn[-1], f"可视化三轨倒挂: up={up[-1]}, mid={mid[-1]}, dn={dn[-1]}"


def test_600353_xuguang_electronics_downtrend_and_broken_support():
    """测试 600353 旭光电子通道方向严格为下跌 (-1)，识别破位跌破上涨支撑线"""
    df = get_tdx_Exp_day_to_df('600353')
    assert df is not None and len(df) >= 60, "旭光电子日线数据不足"
    last = df.iloc[-1]
    close_p = float(last['close'])

    # 1. 通道方向必须为下跌通道 (从 53.68 暴跌至 20.72)
    ch_dir = int(last['ch_dir'])
    deg = float(last['ch_slope_deg'])
    assert ch_dir == -1, f"旭光电子大趋势为下跌通道，绝不可因反弹误判为 1: {ch_dir}"
    assert deg < 0.0, f"下跌通道倾角必须为负: {deg}"

    # 2. 上涨支撑线破位识别
    supp_p = float(last['ch_supp_price'])
    supp_deg = float(last['ch_supp_slope_deg'])
    assert supp_p > 0, "应有有效支撑线价格"
    assert supp_deg > 0, "从 20.72 起来的反弹支撑线倾角应为正"
    assert close_p < supp_p, f"当前股价 {close_p} 应低于支撑线 {supp_p} (已破位)"

    # 3. 策略指引文本必须反映空头方向与破位警示
    strat_text = generate_channel_strategy_text(last.to_dict())
    assert "空头占优" in strat_text, "旭光电子策略指引必须明确判定空头占优"
    assert "已跌破" in strat_text, "旭光电子策略指引必须包含跌破提示"


def test_300563_shenyu_shares_uptrend_resonance_and_dynamic_pos():
    """测试 300563 神宇股份上升通道、支撑线无限延伸至最新天、下轨双共振、动态 pos 准确"""
    df = get_tdx_Exp_day_to_df('300563')
    assert df is not None and len(df) >= 60, "神宇股份日线数据不足"
    n = len(df)
    last = df.iloc[-1]
    close_p = float(last['close'])

    # 1. 验证上涨通道
    ch_dir = int(last['ch_dir'])
    deg = float(last['ch_slope_deg'])
    assert ch_dir == 1, f"神宇股份大通道必须为上涨通道: {ch_dir}"
    assert deg > 0.0, f"上涨通道倾角必须为正: {deg}"

    # 2. 验证 KX DRAWLINE 趋势线向右无限延伸至最新 K 线 (n-1)
    limit_high = np.max(df['high'].values[-100:]) * 1.10
    limit_low = np.min(df['low'].values[-100:]) * 0.90
    lines = tv.calc_kx_trend_lines_list(df, limit_low, limit_high, 0)
    assert len(lines) > 0, "必须能计算出 KX 支撑线"
    last_line = lines[-1]
    assert last_line['x'][-1] == n - 1, f"支撑线必须延伸至最新交易日 (索引 {n-1})，绝不能中途截断: {last_line['x'][-1]}"

    # 3. 验证支撑线与通道下轨双共振 (相差不超过 0.30 元，通达信真实值: 下轨 22.69 vs 支撑 22.81)
    ch_lower = float(last['ch_lower'])
    supp_p = float(last['ch_supp_price'])
    assert 22.0 <= ch_lower <= 23.5, f"通道下轨应在 22.69 元附近: {ch_lower}"
    assert 22.0 <= supp_p <= 23.5, f"支撑线最新价格应在 22.81 元附近: {supp_p}"
    assert abs(ch_lower - supp_p) < 0.30, f"通道下轨与上涨支撑线必须紧密共振重合: diff={abs(ch_lower - supp_p)}"

    # 4. 验证动态实时 ch_pos 重算 (收盘 27.92 元，绝非旧缓存 4.3%)
    strat_text = generate_channel_strategy_text(last.to_dict())
    assert "ch_pos = 96." in strat_text or "ch_pos = 95." in strat_text, f"收盘 27.92 元对应通道位置应在 95%~97% 之间，绝非 4.3%:\n{strat_text}"
    assert "多头控盘" in strat_text, "逼近上轨必须判定为多头控盘"


def test_tdx_channel_factory_ssot_consistency():
    """测试 TDXChannelFactory 统一工厂单一真实源一致性 (SSOT: calc_trend_channel 与 calc_auto_channel 100% 相同)"""
    from JSONData.tdx_channel_factory import TDXChannelFactory
    for code in ['002384', '600353', '300563']:
        df = get_tdx_Exp_day_to_df(code)
        assert df is not None and len(df) >= 60
        # 1. 验证 calc_trend_channel(df) 与 TDXChannelFactory.calculate(df) 结果 100% 相同
        df_calc = calc_trend_channel(df.copy())
        ch_res = TDXChannelFactory.calculate(df)
        np.testing.assert_allclose(df_calc['ch_upper'].values, ch_res.upper, rtol=1e-5, atol=1e-4)
        np.testing.assert_allclose(df_calc['ch_mid'].values, ch_res.mid, rtol=1e-5, atol=1e-4)
        np.testing.assert_allclose(df_calc['ch_lower'].values, ch_res.lower, rtol=1e-5, atol=1e-4)
        assert float(df_calc['ch_supp_price'].iloc[-1]) == pytest.approx(ch_res.supp_price, abs=0.01)

        # 2. 验证可视化直接调用与工厂结果 100% 相同
        vis_mid, vis_up, vis_dn, vis_k, vis_idx = tv.calc_auto_channel(df)
        np.testing.assert_allclose(vis_mid, ch_res.mid, rtol=1e-5, atol=1e-4)
        np.testing.assert_allclose(vis_up, ch_res.upper, rtol=1e-5, atol=1e-4)
        np.testing.assert_allclose(vis_dn, ch_res.lower, rtol=1e-5, atol=1e-4)
        assert vis_k == pytest.approx(ch_res.slope, abs=1e-6)


def test_channel_and_support_start_point_alignment():
    """验证趋势通道与支撑线严格从起点起笔 (start_idx)，起点之前为 DRAWNULL (NaN)，绝无超长横贯线条"""
    from JSONData.tdx_channel_factory import TDXChannelFactory
    for code in ['300563', '300319', '600353']:
        df = get_tdx_Exp_day_to_df(code)
        assert df is not None and len(df) >= 60
        res = TDXChannelFactory.calculate(df)
        n = len(df)
        start_idx = res.start_idx

        # 1. 验证起点索引必须在合理范围内 (大于 0 且小于 n-1)
        assert 0 < start_idx < n - 1, f"{code} start_idx 异常: {start_idx}"

        # 2. 验证起点之前的历史 K 线，通道三轨严格为 NaN (通达信原版 DRAWNULL)
        assert np.isnan(res.mid[:start_idx]).all(), f"{code} 起点之前 mid 不全为 NaN"
        assert np.isnan(res.upper[:start_idx]).all(), f"{code} 起点之前 upper 不全为 NaN"
        assert np.isnan(res.lower[:start_idx]).all(), f"{code} 起点之前 lower 不全为 NaN"

        # 3. 验证从起点到最新交易日，通道三轨严格为有效实数
        assert np.isfinite(res.mid[start_idx:]).all(), f"{code} 起点之后 mid 包含非实数"
        assert np.isfinite(res.upper[start_idx:]).all(), f"{code} 起点之后 upper 包含非实数"
        assert np.isfinite(res.lower[start_idx:]).all(), f"{code} 起点之后 lower 包含非实数"

        # 4. 验证最新支撑线严格从有效起点起笔，并延伸至最新交易日 (n-1)
        assert len(res.lines_for_visualizer) > 0, f"{code} 应有有效支撑线"
        latest_line = res.lines_for_visualizer[0]
        assert latest_line['x'][0] >= start_idx - 5, f"{code} 支撑线起点应与通道起点一致: {latest_line['x'][0]} vs {start_idx}"
        assert latest_line['x'][-1] == n - 1, f"{code} 支撑线终点必须延伸至最新交易日: {latest_line['x'][-1]} vs {n-1}"


