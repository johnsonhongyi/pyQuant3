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


def test_crosshair_nearest_line_price_tag_detection():
    """测试通达信同款线位吸附检测：根据当前 K 线与 Y 价格精确吸附 KX 支撑线、通道三轨、均线或当前价格"""
    from unittest.mock import MagicMock
    df = get_tdx_Exp_day_to_df('300563')
    assert df is not None and len(df) >= 60

    # 构造 MainWindow 模拟对象
    win = tv.MainWindow.__new__(tv.MainWindow)
    win.day_df = df
    win.kline_plot = MagicMock()
    # 模拟 ViewBox viewRange: x 范围 [0, 100], y 范围 [15.0, 35.0], y_span = 20.0 (threshold ~ 0.76)
    win.kline_plot.vb.viewRange.return_value = ([0, len(df)], [15.0, 35.0])

    idx = len(df) - 1
    last_row = df.iloc[-1]
    supp_p = float(last_row['ch_supp_price'])
    ch_up = float(last_row['ch_upper'])
    ch_mid = float(last_row['ch_mid'])
    ch_dn = float(last_row['ch_lower'])

    # 1. 当光标 Y 价格接近 KX 支撑线时 (diff < 0.20)，吸附命中 GG通道线走势(KX)
    tag_info = win._detect_crosshair_nearest_line(idx, supp_p + 0.05)
    name, p_val, color, disp_text, prio = tag_info
    assert name == "GG通道线走势(KX)", f"应吸附到 KX 支撑线: {name}"
    assert "GG通道线走势(KX)" in disp_text
    assert f"{supp_p:.2f}" in disp_text

    # 2. 当光标 Y 价格接近通道上轨时 (diff < 0.20)，吸附命中 通道上轨
    tag_info = win._detect_crosshair_nearest_line(idx, ch_up - 0.08)
    name, p_val, color, disp_text, prio = tag_info
    assert name == "通道上轨", f"应吸附到通道上轨: {name}"
    assert f"{ch_up:.2f}" in disp_text

    # 3. 当光标 Y 价格接近通道中轨时，吸附命中 通道中轨
    tag_info = win._detect_crosshair_nearest_line(idx, ch_mid + 0.06)
    name, p_val, color, disp_text, prio = tag_info
    assert name == "通道中轨", f"应吸附到通道中轨: {name}"

    # 4. 当光标 Y 价格接近通道下轨时，吸附命中 通道下轨 (注意神宇股份支撑线与下轨共振相近)
    tag_info = win._detect_crosshair_nearest_line(idx, ch_dn - 0.15)
    assert tag_info[0] in ["通道下轨", "GG通道线走势(KX)"]

    # 5. 当光标远离所有指标线时 (例如 50.0 元)，返回当前光标物理价格
    tag_info = win._detect_crosshair_nearest_line(idx, 50.0)
    assert tag_info[0] == "光标价"
    assert "价格: 50.00" in tag_info[3]


def test_crosshair_hover_timer_and_auto_hide_lifecycle():
    """测试鼠标移动、悬停 180ms 延时显示与移出有效 K 线柱立即自动隐藏机制 (对齐通达信)"""
    from unittest.mock import MagicMock
    df = get_tdx_Exp_day_to_df('300563')
    win = tv.MainWindow.__new__(tv.MainWindow)
    win.day_df = df
    win.crosshair_enabled = True
    win.current_kline_signals = []
    win.vline = MagicMock()
    win.hline = MagicMock()
    win.crosshair_label = MagicMock()
    win.crosshair_line_tag = MagicMock()
    win.crosshair_y_cursor = MagicMock()
    win.kline_detail_win = MagicMock()
    win.kline_detail_win.is_dragging = False
    win.kline_hover_timer = MagicMock()
    win.ma_legend_label = MagicMock()
    win.qt_theme = 'dark'
    win._update_ma_legend = MagicMock()
    win.kline_plot = MagicMock()
    win.kline_plot.vb.viewRange.return_value = ([0, len(df)], [15.0, 35.0])

    # 1. 模拟鼠标移出有效 K 线或离开视口时调用 _hide_crosshair
    win._hide_crosshair()
    win.kline_hover_timer.stop.assert_called()
    win.vline.setVisible.assert_called_with(False)
    win.hline.setVisible.assert_called_with(False)
    win.crosshair_line_tag.setVisible.assert_called_with(False)
    win.crosshair_y_cursor.setVisible.assert_called_with(False)
    win.kline_detail_win.hide.assert_called()  # 必须立即自动隐藏！

    # 2. 模拟鼠标移入有效 K 线柱 (idx = 10) 移动
    # 模拟视口包含 pos
    win.kline_plot.vb.sceneBoundingRect.return_value.contains.return_value = True
    win.kline_plot.vb.mapSceneToView.return_value = MagicMock(x=lambda: 10.2, y=lambda: 22.5)
    win._on_kline_mouse_moved(MagicMock())

    # 验证快速滑动中：更新十字线与线位标签，重置 180ms 悬停定时器，详情窗保持隐藏
    win.vline.setPos.assert_called_with(10)
    win.hline.setPos.assert_called_with(22.5)
    win.crosshair_line_tag.setVisible.assert_called_with(True)
    win.kline_detail_win.hide.assert_called()
    win.kline_hover_timer.start.assert_called_with(180)

    # 3. 模拟悬停 180ms 定时器超时触发
    win.current_crosshair_idx = 10
    win._show_kline_detail_window = MagicMock()
    win._on_kline_hover_timeout()
    win._show_kline_detail_window.assert_called_with(10)


def test_688813_taijin_descending_channel_alignment():
    """测试 688813 泰金新能大暴跌下降通道完全呈现，对齐通达信官方主图"""
    df = get_tdx_Exp_day_to_df('688813')
    assert df is not None and len(df) >= 60, "泰金新能日线数据不足"
    from JSONData.tdx_channel_factory import TDXChannelFactory
    res = TDXChannelFactory.calculate(df)
    n = len(df)

    # 1. 验证大下降通道宏观方向与斜率
    assert res.ch_dir == -1, f"泰金新能从 248.940 暴跌至 90.130 宏观方向必须为下跌通道 (-1): {res.ch_dir}"
    assert res.slope < -1.0, f"主跌通道斜率必须为显著负斜率: {res.slope}"
    assert res.slope_deg < -60.0, f"通道倾角必须为大倾角下跌 (-60°以下): {res.slope_deg}"

    # 2. 验证趋势起点与波段极值
    assert res.start_idx == 13, f"趋势起点必须为 248.940 高点所在日 (idx 13): {res.start_idx}"
    assert res.tc2 == 57, f"高点周期 tc2 应为 57: {res.tc2}"
    assert res.bc2 == 32, f"低点周期 bc2 应为 32: {res.bc2}"
    assert res.upper_price == pytest.approx(248.94, abs=0.1)
    assert res.lower_price == pytest.approx(90.13, abs=0.1)

    # 3. 验证波段内 (idx 13 到 idx 38) 三轨物理真实性与顺排
    for i in range(res.start_idx, n - res.bc2 + 1):
        assert pd.notna(res.upper[i]), f"idx {i} 上轨不能为 NaN"
        assert pd.notna(res.mid[i]), f"idx {i} 中轨不能为 NaN"
        assert pd.notna(res.lower[i]), f"idx {i} 下轨不能为 NaN"
        assert res.upper[i] > res.mid[i] > res.lower[i], f"idx {i} 三轨倒挂: up={res.upper[i]}, mid={res.mid[i]}, dn={res.lower[i]}"

    # 4. 验证起点之前全为 NaN (DRAWNULL，绝无超长线条)
    for i in range(res.start_idx):
        assert pd.isna(res.upper[i]), f"idx {i} 起点前上轨必须为 NaN"
        assert pd.isna(res.mid[i]), f"idx {i} 起点前中轨必须为 NaN"
        assert pd.isna(res.lower[i]), f"idx {i} 起点前下轨必须为 NaN"

    # 5. 验证可视化与底层数据一致性
    vis_mid, vis_up, vis_dn, vis_k, vis_idx = tv.calc_auto_channel(df)
    np.testing.assert_allclose(vis_mid, res.mid, rtol=1e-5, atol=1e-4)
    np.testing.assert_allclose(vis_up, res.upper, rtol=1e-5, atol=1e-4)
    np.testing.assert_allclose(vis_dn, res.lower, rtol=1e-5, atol=1e-4)


def test_301148_jiarong_descending_channel_alignment():
    """测试 301148 嘉戎技术大暴跌下降通道完全呈现，对齐通达信官方主图"""
    df = get_tdx_Exp_day_to_df('301148')
    assert df is not None and len(df) >= 60, "嘉戎技术日线数据不足"
    from JSONData.tdx_channel_factory import TDXChannelFactory
    res = TDXChannelFactory.calculate(df)
    n = len(df)

    # 1. 验证大下降通道宏观方向与斜率
    assert res.ch_dir == -1, f"嘉戎技术宏观方向必须为下跌通道 (-1): {res.ch_dir}"
    assert res.slope < -0.5, f"主跌通道斜率必须为负斜率: {res.slope}"
    assert res.slope_deg < -50.0, f"通道倾角必须为大倾角下跌: {res.slope_deg}"

    # 2. 验证趋势起点与波段极值
    assert res.start_idx == 11, f"趋势起点必须为高点所在日 (idx 11): {res.start_idx}"
    assert res.tc2 == 59, f"高点周期 tc2 应为 59: {res.tc2}"
    assert res.bc2 == 39, f"低点周期 bc2 应为 39: {res.bc2}"
    assert res.upper_price == pytest.approx(66.13, abs=0.1)
    assert res.lower_price == pytest.approx(35.26, abs=0.1)

    # 3. 验证波段内 (idx 11 到 idx 31) 三轨物理真实性与顺排
    for i in range(res.start_idx, n - res.bc2 + 1):
        assert pd.notna(res.upper[i]), f"idx {i} 上轨不能为 NaN"
        assert pd.notna(res.mid[i]), f"idx {i} 中轨不能为 NaN"
        assert pd.notna(res.lower[i]), f"idx {i} 下轨不能为 NaN"
        assert res.upper[i] > res.mid[i] > res.lower[i], f"idx {i} 三轨倒挂: up={res.upper[i]}, mid={res.mid[i]}, dn={res.lower[i]}"

    # 4. 验证起点之前全为 NaN (DRAWNULL，绝无超长线条)
    for i in range(res.start_idx):
        assert pd.isna(res.upper[i]), f"idx {i} 起点前上轨必须为 NaN"
        assert pd.isna(res.mid[i]), f"idx {i} 起点前中轨必须为 NaN"
        assert pd.isna(res.lower[i]), f"idx {i} 起点前下轨必须为 NaN"

    # 5. 验证可视化与底层数据一致性
    vis_mid, vis_up, vis_dn, vis_k, vis_idx = tv.calc_auto_channel(df)
    np.testing.assert_allclose(vis_mid, res.mid, rtol=1e-5, atol=1e-4)
    np.testing.assert_allclose(vis_up, res.upper, rtol=1e-5, atol=1e-4)
    np.testing.assert_allclose(vis_dn, res.lower, rtol=1e-5, atol=1e-4)





