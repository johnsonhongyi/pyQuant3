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

        # 3. 验证从起点到核心波段终点，通道三轨严格为有效实数；波段之后跌破最低限制自然停画 (通达信 DRAWNULL)
        core_end = n - min(res.tc2, res.bc2) + 1
        assert np.isfinite(res.mid[start_idx:core_end]).all(), f"{code} 波段内 mid 包含非实数"
        assert np.isfinite(res.upper[start_idx:core_end]).all(), f"{code} 波段内 upper 包含非实数"
        assert np.isfinite(res.lower[start_idx:core_end]).all(), f"{code} 波段内 lower 包含非实数"

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

    # 3. 模拟悬停 180ms 定时器超时触发 (当鼠标仍在 K 线图内时正常弹出)
    win.current_crosshair_idx = 10
    win._show_kline_detail_window = MagicMock()
    from unittest import mock
    with mock.patch.object(tv.QtWidgets.QApplication, 'activeWindow', return_value=win), \
         mock.patch.object(tv.QtGui.QCursor, 'pos', return_value=tv.QtCore.QPoint(100, 100)):
        win.kline_plot.mapFromGlobal.return_value = tv.QtCore.QPoint(50, 50)
        win.kline_plot.rect.return_value.contains.return_value = True
        win.kline_plot.mapToScene.return_value = MagicMock()
        win.kline_plot.vb.sceneBoundingRect.return_value.contains.return_value = True
        win.kline_plot.vb.mapSceneToView.return_value = MagicMock(x=lambda: 10.0)
        win._on_kline_hover_timeout()
        win._show_kline_detail_window.assert_called_with(10)

    # 4. ⭐ 核心修复验证：当鼠标移动到其他屏幕或第三方应用(如通达信)时，悬停定时器触发必须立即隐藏，绝不弹出！
    win._show_kline_detail_window.reset_mock()
    win._hide_crosshair = MagicMock()
    with mock.patch.object(tv.QtWidgets.QApplication, 'activeWindow', return_value=win), \
         mock.patch.object(tv.QtGui.QCursor, 'pos', return_value=tv.QtCore.QPoint(2500, 500)):
        win.kline_plot.mapFromGlobal.return_value = tv.QtCore.QPoint(2500, 500)
        win.kline_plot.rect.return_value.contains.return_value = False  # 明确不在主视口内
        win._on_kline_hover_timeout()
        win._show_kline_detail_window.assert_not_called()
        win._hide_crosshair.assert_called()

    # 5. 模拟主程序非激活窗口（切换到通达信）时，悬停定时器触发必须立即隐藏，绝不弹出！
    win._show_kline_detail_window.reset_mock()
    win._hide_crosshair.reset_mock()
    with mock.patch.object(tv.QtWidgets.QApplication, 'activeWindow', return_value=None):
        win._on_kline_hover_timeout()
        win._show_kline_detail_window.assert_not_called()
        win._hide_crosshair.assert_called()


def test_kline_detail_window_no_global_stays_on_top():
    """验证 KLineDetailWindow 严禁携带全局跨程序置顶标志 WindowStaysOnTopHint，并绑定父对象"""
    app = tv.QtWidgets.QApplication.instance() or tv.QtWidgets.QApplication([])
    win = tv.MainWindow.__new__(tv.MainWindow)
    detail_win = tv.KLineDetailWindow(win)
    flags = detail_win.windowFlags()
    # 绝不能包含 WindowStaysOnTopHint
    assert not (flags & tv.Qt.WindowType.WindowStaysOnTopHint), "详情窗严禁包含 WindowStaysOnTopHint，防止跨屏幕干扰通达信！"
    assert bool(flags & tv.Qt.WindowType.Tool), "详情窗应为 Tool 窗口"
    assert detail_win.main_window == win



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

    # 6. ⭐ 核心对齐验证：通达信官方主图日线 120 根 K 棒全景视野下，最新上轨精确等于 46.37 元
    df120 = get_tdx_Exp_day_to_df('301148', dl=120)
    assert df120 is not None and len(df120) == 120
    res120 = TDXChannelFactory.calculate(df120)
    assert res120.ch_dir == -1, "120 根全景视野下必须为下跌通道"
    assert res120.tc2 == 77, f"120 根全景视野下最高点 87.000 周期 tc2 应为 77: {res120.tc2}"
    assert res120.bc2 == 39, f"120 根全景视野下最低点 35.260 周期 bc2 应为 39: {res120.bc2}"
    assert float(res120.upper[-1]) == pytest.approx(46.37, abs=0.05), f"301148 全景最新上轨必须精准对齐通达信 46.37 元: {res120.upper[-1]}"
    assert float(res120.mid[-1]) == pytest.approx(39.05, abs=0.1), f"中轨采用几何中轴自愈顺排，杜绝 NaN 与 -101: {res120.mid[-1]}"
    assert res120.upper[-1] > res120.mid[-1] > res120.lower[-1], "三轨必须保持严格物理顺排"


def test_date_axis_no_duplicate_out_of_bounds_ticks():
    """验证 DateAxis 越界刻度不打印重复最后一天日期，杜绝 09-11 连续重影"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    dates = [f"2026-09-0{i}" for i in range(1, 10)] + ["2026-09-10", "2026-09-11"]
    axis = tv.DateAxis(dates=dates)
    
    # 模拟视口向右空出 5 个刻度以及左侧负数刻度
    test_values = [-2, -1, 0, 5, 10, 11, 12, 13, 15]
    ticks = axis.tickStrings(test_values, scale=1, spacing=1)
    
    # 索引 0 (2026-09-01) -> '09-01'
    assert ticks[2] == '09-01'
    # 索引 10 (2026-09-11) -> '09-11'
    assert ticks[4] == '09-11'
    
    # 越界区域必须全部为空字符串，绝不可重复出现 '09-11'
    assert ticks[0] == "", "负索引应为空"
    assert ticks[1] == "", "负索引应为空"
    assert ticks[5] == "", "未来越界索引 11 应为空"
    assert ticks[6] == "", "未来越界索引 12 应为空"
    assert ticks[7] == "", "未来越界索引 13 应为空"
    assert ticks[8] == "", "未来越界索引 15 应为空"


def test_zoom_kline_right_anchored_expansion_and_auto_y_fit():
    """验证通达信同款缩放模式：右侧最新 K 线固定锚定不变，向下键向左展开历史数据，向上键收缩聚焦近期"""
    from unittest.mock import MagicMock
    df = get_tdx_Exp_day_to_df('301148')
    assert df is not None and len(df) >= 60
    total_bars = len(df)
    RIGHT_MARGIN = 2
    expected_x_max = float(total_bars + RIGHT_MARGIN)

    win = tv.MainWindow.__new__(tv.MainWindow)
    win.day_df = df
    win.current_crosshair_idx = -1
    win.vline = MagicMock()
    win.vline.isVisible.return_value = False

    # 模拟真实可更新范围的 ViewBox
    class MockViewBox:
        def __init__(self, init_x, init_y):
            self.cur_x = list(init_x)
            self.cur_y = list(init_y)
        def viewRange(self):
            return [list(self.cur_x), list(self.cur_y)]
        def setXRange(self, min_x, max_x, padding=0):
            self.cur_x = [min_x, max_x]
        def setYRange(self, min_y, max_y, padding=0):
            self.cur_y = [min_y, max_y]

    init_span = 50.0
    mock_vb = MockViewBox([expected_x_max - init_span, expected_x_max], [30.0, 70.0])
    win.kline_plot = MagicMock()
    win.kline_plot.vb = mock_vb

    # 1. 模拟连续按向下键 (缩小显示更多历史) 3 次
    for _ in range(3):
        win.zoom_kline(in_=False)
        r = mock_vb.viewRange()[0]
        # 核心铁律：右侧最新 K 线位置始终锚定不变！
        assert r[1] == pytest.approx(expected_x_max, abs=1e-4), f"右边界必须锚定在最新 K 线处，当前: {r[1]}"
        # 左侧必须向左延伸，显示更多历史
        assert r[0] < expected_x_max - init_span, "左侧边界必须向左扩展以展示历史数据"

    expanded_range = mock_vb.viewRange()[0]
    expanded_span = expanded_range[1] - expanded_range[0]
    assert expanded_span > init_span, "缩小后可视跨度必须增大"

    # 2. 验证 Y 轴随着历史展开自动包络视野内的最高低点
    y_range = mock_vb.viewRange()[1]
    vis_start = int(max(0, expanded_range[0]))
    sub_df = df.iloc[vis_start:]
    assert y_range[1] >= float(sub_df['high'].max()), "Y 轴上界必须包络可视区最高价"
    assert y_range[0] <= float(sub_df['low'].min()), "Y 轴下界必须包络可视区最低价"

    # 3. 模拟连续按向上键 (放大聚焦近期) 4 次
    for _ in range(4):
        win.zoom_kline(in_=True)
        r = mock_vb.viewRange()[0]
        # 右侧依然恒定
        assert r[1] == pytest.approx(expected_x_max, abs=1e-4)

    zoomed_in_range = mock_vb.viewRange()[0]
    zoomed_in_span = zoomed_in_range[1] - zoomed_in_range[0]
    assert zoomed_in_span < expanded_span, "放大后可视跨度必须缩小"
    assert zoomed_in_span >= 15.0, "可视跨度不应低于保护下限"

    # 4. ⭐ 核心场景验证：当十字光标激活 (鼠标悬停在图表中间) 时，上下键仍然始终保持最右侧的数据显示不变！
    win.current_crosshair_idx = 35
    win.vline.isVisible.return_value = True

    # 向上键连续放大 3 次
    for _ in range(3):
        win.zoom_kline(in_=True)
        r = mock_vb.viewRange()[0]
        assert r[1] == pytest.approx(expected_x_max, abs=1e-4), "光标悬停时按向上键，最右侧最新K线位置仍必须严格保持不变！"

    # 向下键连续缩小 5 次
    for _ in range(5):
        win.zoom_kline(in_=False)
        r = mock_vb.viewRange()[0]
        assert r[1] == pytest.approx(expected_x_max, abs=1e-4), "光标悬停时按向下键，最右侧最新K线位置仍必须严格保持不变！"


def test_kline_double_click_lock_and_right_click_reset_lifecycle():
    """验证双击 K 线打开十字星详情并锁定关闭自动关闭，以及右键重置为跟随光标模式恢复自动关闭完整闭环"""
    from unittest.mock import MagicMock
    app = tv.QtWidgets.QApplication.instance() or tv.QtWidgets.QApplication([])
    df = get_tdx_Exp_day_to_df('300563')
    win = tv.MainWindow.__new__(tv.MainWindow)
    win.day_df = df
    win.crosshair_enabled = True
    win.current_kline_signals = []
    win.current_crosshair_idx = -1
    win.vline = MagicMock()
    win.hline = MagicMock()
    win.crosshair_label = MagicMock()
    win.crosshair_line_tag = MagicMock()
    win.crosshair_y_cursor = MagicMock()
    win.ma_legend_label = MagicMock()
    win.kline_hover_timer = MagicMock()
    win._update_line_price_tag = MagicMock()
    win._update_ma_legend = MagicMock()
    win.save_detail_window_position = MagicMock()

    # 实例化真实的 KLineDetailWindow
    detail_win = tv.KLineDetailWindow(win)
    win.kline_detail_win = detail_win

    mock_vb = MagicMock()
    mock_vb.sceneBoundingRect.return_value.contains.return_value = True
    # 映射到 idx=25, price=23.50
    mock_vb.mapSceneToView.return_value = tv.QtCore.QPointF(25.0, 23.50)
    mock_kline_plot = MagicMock()
    mock_kline_plot.vb = mock_vb
    win.kline_plot = mock_kline_plot
    win._show_kline_detail_window = MagicMock()

    # 1. ⭐ 初始状态：未锁定，跟随光标模式，自动关闭生效
    assert detail_win.auto_close_disabled is False
    assert detail_win.is_custom_positioned is False
    assert detail_win.handle_bar.isVisible() is False

    # 2. ⭐ 双击 K 线图：打开十字星详情并关闭自动关闭 (锁定调整模式)
    dummy_scene_pos = tv.QtCore.QPointF(100, 200)
    handled = win._on_kline_double_clicked(dummy_scene_pos)
    assert handled is True
    assert win.current_crosshair_idx == 25
    win.vline.setPos.assert_called_with(25)
    win.hline.setPos.assert_called_with(23.50)
    win._show_kline_detail_window.assert_called_with(25, force=True)

    # 验证详情窗进入锁定调整状态
    assert detail_win.auto_close_disabled is True, "双击后必须关闭自动关闭"
    assert detail_win.is_custom_positioned is True, "双击后标记为自定义位置模式"
    # ⭐ 用户需求 2：锁定后顶部的锁定信息平时自动隐藏！
    assert detail_win.handle_bar.isHidden(), "锁定状态下把手栏平时自动隐藏，保持纯净紧凑"
    assert detail_win.auto_hide_timer.isActive() is False, "自动隐藏定时器必须被停止"

    # 3. ⭐ 用户需求 1：锁定状态下鼠标移动到新 K 线，数据实时自动更新！
    detail_win.hide = MagicMock()
    win._show_kline_detail_window.reset_mock()
    # 模拟鼠标移动到 idx=30 的 K 线
    mock_vb.mapSceneToView.return_value = tv.QtCore.QPointF(30.0, 24.80)
    dummy_scene_pos_30 = tv.QtCore.QPointF(150, 210)
    win._on_kline_mouse_moved(dummy_scene_pos_30)
    
    assert win.current_crosshair_idx == 30, "十字光标索引必须更新到新 K 线"
    win._show_kline_detail_window.assert_called_with(30, force=True), "锁定模式下鼠标移动必须实时自动更新对应 K 线数据！"
    detail_win.hide.assert_not_called(), "锁定模式下移动鼠标绝不能被隐藏！"

    # 模拟移出视口 _hide_crosshair
    win._hide_crosshair()
    detail_win.hide.assert_not_called(), "锁定模式下移出视口十字线隐藏但详情窗绝不能被隐藏！"

    # 4. ⭐ 用户需求 2：跟之前的逻辑一致，在窗口悬停后才触发显示拖动调整框，移动后自动隐藏
    enter_ev = tv.QtGui.QEnterEvent(tv.QtCore.QPointF(10, 10), tv.QtCore.QPointF(100, 100), tv.QtCore.QPointF(100, 100))
    detail_win.enterEvent(enter_ev)
    assert detail_win.handle_bar.isHidden(), "刚进入未悬停前拖动调整框必须保持隐藏"
    
    # 悬停延时到达，触发显示
    detail_win._on_hover_timeout()
    assert not detail_win.handle_bar.isHidden(), "悬停后才触发显示拖动调整框"
    assert "已锁定" in detail_win.handle_label.text(), "手柄栏必须提示已锁定"

    # 点击并拖拽
    press_event = tv.QtGui.QMouseEvent(
        tv.QtCore.QEvent.Type.MouseButtonPress,
        tv.QtCore.QPointF(10, 5),
        tv.QtCore.QPointF(100, 100),
        tv.Qt.MouseButton.LeftButton,
        tv.Qt.MouseButton.LeftButton,
        tv.Qt.KeyboardModifier.NoModifier
    )
    detail_win.mousePressEvent(press_event)
    assert detail_win.is_dragging is True, "点击把手栏必须立即进入拖拽状态"

    # 释放鼠标（移动完毕）
    release_event = tv.QtGui.QMouseEvent(
        tv.QtCore.QEvent.Type.MouseButtonRelease,
        tv.QtCore.QPointF(10, 5),
        tv.QtCore.QPointF(100, 100),
        tv.Qt.MouseButton.LeftButton,
        tv.Qt.MouseButton.NoButton,
        tv.Qt.KeyboardModifier.NoModifier
    )
    detail_win.mouseReleaseEvent(release_event)
    assert detail_win.is_dragging is False, "释放后退出拖拽状态"
    win.save_detail_window_position.assert_called(), "拖动结束保存自定义位置"
    # ⭐ 移动后自动隐藏拖动调整框！
    assert detail_win.handle_bar.isHidden(), "移动后拖动调整框必须立即自动隐藏！"

    # 5. ⭐ 右键重置为自动跟随光标模式，恢复自动关闭
    detail_win.reset_to_auto_follow()
    assert detail_win.auto_close_disabled is False, "右键重置后必须恢复自动关闭"
    assert detail_win.is_custom_positioned is False, "右键重置后必须恢复自动跟随光标"
    assert detail_win.handle_bar.isHidden(), "恢复跟随模式后手柄栏恢复默认隐藏"

    # 6. ⭐ 恢复自动关闭后，移出视口调用 _hide_crosshair 必须正常自动隐藏
    detail_win.hide.reset_mock()
    win._hide_crosshair()
    detail_win.hide.assert_called(), "恢复自动关闭后移出视口必须自动隐藏！"









