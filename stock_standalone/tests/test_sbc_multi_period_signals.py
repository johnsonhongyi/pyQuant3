# -*- coding: utf-8 -*-
"""
tests/test_sbc_multi_period_signals.py — ATS SBC 买卖价格在多周期（多日分时与各级别K线）同步显示专项测试
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPainter, QImage

# 确保项目根路径
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.ui.intraday_strategy_dialog import (
    SBCChartCanvas,
    SBCIntradayChartDialog,
    VALID_SBC_PERIODS
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _create_mock_kline_df(count=30):
    """构造用于测试的 K 线数据"""
    dates = pd.date_range("2026-08-20 09:30", periods=count, freq="5min")
    times = [d.strftime("%Y-%m-%d %H:%M") for d in dates]
    rows = []
    base_p = 100.0
    for i, t in enumerate(times):
        op = base_p + np.sin(i / 5.0) * 5.0
        cl = op + np.cos(i / 3.0) * 2.0
        hi = max(op, cl) + 1.0
        lo = min(op, cl) - 1.0
        vol = 1000.0 + i * 50
        rows.append({
            "time": t,
            "open": op,
            "close": cl,
            "high": hi,
            "low": lo,
            "vol": vol,
            "amount": cl * vol,
            "ma5": cl,
            "ma20": cl * 0.98,
            "ma60": cl * 0.95,
            "boll_upper": cl * 1.05,
            "boll_lower": cl * 0.95,
        })
    df = pd.DataFrame(rows).set_index("time")
    return df


def _create_mock_intraday_df(days=2):
    """构造用于测试的多日分时数据"""
    rows = []
    dates = ["2026-08-19", "2026-08-20"][-days:]
    for d in dates:
        times = ["09:30", "09:35", "10:00", "11:30", "13:00", "14:00", "15:00"]
        for t in times:
            t_label = f"{d[5:]} {t}"
            rows.append({
                "time": t_label,
                "date": d,
                "time_only": t,
                "open": 100.0,
                "close": 102.5,
                "trade": 102.5,
                "price": 102.5,
                "high": 105.0,
                "low": 99.0,
                "vwap": 101.5,
                "volume": 5000.0,
                "vol": 5000.0,
                "amount": 512500.0,
                "turnover": 5.2,
                "turnover_rate": 5.2
            })
    df = pd.DataFrame(rows).set_index("time")
    return df


def test_sbc_canvas_kline_mode_receives_and_stores_signals(qapp):
    """测试 SBCChartCanvas 在 K 线模式下正确接收并存储 signals 与基准价格"""
    canvas = SBCChartCanvas()
    df_kline = _create_mock_kline_df(20)

    test_signals = [
        {"action": "buy", "price": 98.5, "time": "09:35", "note": "开盘买点"},
        {"action": "sell", "price": 108.0, "time": "10:00", "note": "冲高卖点"}
    ]

    canvas.set_kline_data(
        df_kline=df_kline,
        open_p=100.0,
        vwap_p=102.0,
        high_p=106.0,
        low_p=97.0,
        sell_min=103.0,
        sell_max=105.0,
        signals=test_signals,
        period_mode="5m"
    )

    assert canvas.period_mode == "5m"
    assert canvas.open_price == 100.0
    assert canvas.vwap == 102.0
    assert canvas.high_price == 106.0
    assert canvas.low_price == 97.0
    assert canvas.target_sell_min == 103.0
    assert canvas.target_sell_max == 105.0
    assert len(canvas.signals) == 2
    assert canvas.signals[0]["price"] == 98.5
    assert canvas.signals[1]["price"] == 108.0


def test_sbc_canvas_kline_paint_event_with_signals(qapp):
    """测试 SBCChartCanvas 在各种 K 线周期下执行 paintEvent 正常绘制买卖线与 Tag，无异常崩溃"""
    canvas = SBCChartCanvas()
    canvas.resize(600, 400)
    df_kline = _create_mock_kline_df(30)

    test_signals = [
        {"action": "buy", "price": 95.0, "time": "09:35", "timestamp": "09:35:00"},
        {"action": "sell", "price": 115.0, "time": "10:15", "timestamp": "10:15:00"}
    ]

    for p_mode in ["5m", "15m", "30m", "60m", "day", "week"]:
        canvas.set_kline_data(
            df_kline=df_kline,
            open_p=100.0,
            vwap_p=102.0,
            high_p=110.0,
            low_p=96.0,
            sell_min=103.0,
            sell_max=105.0,
            signals=test_signals,
            period_mode=p_mode
        )

        # 模拟执行 paintEvent 绘制到 QImage
        img = QImage(canvas.size(), QImage.Format.Format_ARGB32)
        painter = QPainter(img)
        try:
            canvas.render(painter)
        finally:
            painter.end()


def test_sbc_canvas_multi_day_intraday_paint_event_with_signals(qapp):
    """测试 SBCChartCanvas 在 2日/3日分时模式下正确接收 signals 并完成绘制"""
    canvas = SBCChartCanvas()
    canvas.resize(600, 400)

    test_signals = [
        {"action": "买", "price": 99.5, "time": "09:35"},
        {"action": "卖", "price": 105.5, "time": "10:00"}
    ]

    for p_mode in ["2d", "3d"]:
        days = 2 if p_mode == "2d" else 3
        df_intraday = _create_mock_intraday_df(days=days)
        canvas.set_data(
            df_intraday=df_intraday,
            open_p=100.0,
            vwap_p=101.5,
            high_p=105.0,
            low_p=99.0,
            sell_min=103.0,
            sell_max=105.0,
            signals=test_signals,
            period_mode=p_mode
        )
        assert canvas.period_mode == p_mode
        assert len(canvas.signals) == 2

        img = QImage(canvas.size(), QImage.Format.Format_ARGB32)
        painter = QPainter(img)
        try:
            canvas.render(painter)
        finally:
            painter.end()


def test_sbc_dialog_reload_chart_dispatches_signals_to_all_periods(qapp):
    """测试 SBCIntradayChartDialog.reload_chart 在切换不同周期时均向画布透传 signals 与价格"""
    dlg = SBCIntradayChartDialog(code="688826")
    try:
        # Mock TDXRealtimeFetcher 和 IntradayStrategyEngine
        mock_snapshot = {
            "open_price": 100.0,
            "price": 103.5,
            "vwap": 102.0,
            "high_price": 105.0,
            "low_price": 98.0,
            "amount": 250000000.0,
            "turnover_rate": 8.5
        }
        mock_signals = [
            {"action": "buy", "price": 99.0, "time": "09:31"},
            {"action": "sell", "price": 105.0, "time": "09:45"}
        ]

        with patch("ats.ui.intraday_strategy_dialog.TDXRealtimeFetcher.get_instance") as mock_get_fetcher:
            mock_fetcher = MagicMock()
            mock_fetcher.fetch_stock_snapshot.return_value = mock_snapshot
            mock_fetcher.fetch_intraday_bars.return_value = _create_mock_intraday_df(1)
            mock_fetcher.fetch_multi_day_intraday_bars.return_value = _create_mock_intraday_df(2)
            mock_fetcher.fetch_kline_bars.return_value = _create_mock_kline_df(20)
            mock_get_fetcher.return_value = mock_fetcher

            # 模拟引擎返回 signals
            dlg.engine._get_stock_state = MagicMock(return_value={"signals": mock_signals})

            # 1. 验证 1日分时 (1m)
            dlg.set_period_mode("1m", reload=True, save=False)
            assert dlg.canvas.period_mode == "1m"
            assert len(dlg.canvas.signals) == 2
            assert dlg.canvas.open_price == 100.0

            # 2. 验证 2日分时 (2d)
            dlg.set_period_mode("2d", reload=True, save=False)
            assert dlg.canvas.period_mode == "2d"
            assert len(dlg.canvas.signals) == 2
            assert dlg.canvas.open_price == 100.0

            # 3. 验证 30分K (30m)
            dlg.set_period_mode("30m", reload=True, save=False)
            assert dlg.canvas.period_mode == "30m"
            assert len(dlg.canvas.signals) == 2
            assert dlg.canvas.open_price == 100.0
            assert dlg.canvas.target_sell_min == 103.0

            # 4. 验证 日K (day)
            dlg.set_period_mode("day", reload=True, save=False)
            assert dlg.canvas.period_mode == "day"
            assert len(dlg.canvas.signals) == 2
            assert dlg.canvas.open_price == 100.0
            assert dlg.canvas.target_sell_min == 103.0
    finally:
        dlg.close()


def test_sbc_canvas_kline_with_tdx_trend_channel_and_support_lines(qapp):
    """测试 SBCChartCanvas 在 K 线模式下完整渲染通达信自动通道三轨、支撑线、翻转线、Fibonacci 与拐点信号"""
    from JSONData.tdx_data_Day import calc_trend_channel

    canvas = SBCChartCanvas()
    canvas.resize(700, 450)

    # 1. 构造基础 K 线数据并调用真实的 calc_trend_channel
    df_raw = _create_mock_kline_df(50)
    df_kline = calc_trend_channel(df_raw)

    # 验证指标已成功计算
    assert "ch_upper" in df_kline.columns
    assert "ch_mid" in df_kline.columns
    assert "ch_lower" in df_kline.columns
    assert "ch_supp_price" in df_kline.columns
    assert "reversal_line" in df_kline.columns
    assert "fib_50" in df_kline.columns
    assert "sig_bottom" in df_kline.columns

    # 2. 传入带有通道指标的 DataFrame 执行渲染
    test_signals = [
        {"action": "buy", "price": float(df_kline['close'].iloc[10]), "time": "09:40"},
        {"action": "sell", "price": float(df_kline['close'].iloc[30]), "time": "10:30"}
    ]

    canvas.set_kline_data(
        df_kline=df_kline,
        open_p=float(df_kline['open'].iloc[0]),
        vwap_p=float(df_kline['close'].mean()),
        high_p=float(df_kline['high'].max()),
        low_p=float(df_kline['low'].min()),
        sell_min=float(df_kline['open'].iloc[0] * 1.03),
        sell_max=float(df_kline['open'].iloc[0] * 1.05),
        signals=test_signals,
        period_mode="5m"
    )

    # 3. 模拟渲染到 QImage 验证全套通达信图元绘制无崩溃
    img = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    try:
        canvas.render(painter)
    finally:
        painter.end()


def test_sbc_canvas_wheel_zoom_and_pan(qapp):
    """测试 SBCChartCanvas 鼠标滚轮缩放与鼠标拖拽平移"""
    from PyQt6.QtCore import Qt, QPoint, QPointF
    from PyQt6.QtGui import QWheelEvent, QMouseEvent

    canvas = SBCChartCanvas()
    canvas.resize(600, 400)
    df_kline = _create_mock_kline_df(60)
    canvas.set_kline_data(df_kline=df_kline, period_mode="5m")

    # 初始为全量 60 根
    df_view, s_i, e_i = canvas._get_visible_slice()
    assert len(df_view) == 60
    assert not canvas._is_zoomed()

    # 1. 模拟鼠标向前滚轮 (angleDelta.y() > 0)，执行放大
    wheel_ev = QWheelEvent(
        QPointF(300, 200),
        QPointF(300, 200),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False
    )
    canvas.wheelEvent(wheel_ev)

    # 放大后可视数量减少
    df_view_zoomed, s_z, e_z = canvas._get_visible_slice()
    assert len(df_view_zoomed) < 60
    assert canvas._is_zoomed()

    # 2. 模拟鼠标向后滚轮 (angleDelta.y() < 0)，执行缩小
    wheel_down_ev = QWheelEvent(
        QPointF(300, 200),
        QPointF(300, 200),
        QPoint(0, 0),
        QPoint(0, -240),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False
    )
    canvas.wheelEvent(wheel_down_ev)
    df_view_unzoomed, _, _ = canvas._get_visible_slice()
    assert len(df_view_unzoomed) > len(df_view_zoomed)


def test_sbc_canvas_right_click_reset_view(qapp):
    """测试鼠标右键点击一键重置图表全景视图"""
    from PyQt6.QtCore import Qt, QPoint, QPointF
    from PyQt6.QtGui import QMouseEvent

    canvas = SBCChartCanvas()
    canvas.resize(600, 400)
    df_kline = _create_mock_kline_df(60)
    canvas.set_kline_data(df_kline=df_kline, period_mode="5m")

    # 人为设置局部缩放状态
    canvas._zoom_start_idx = 10
    canvas._zoom_end_idx = 30
    assert canvas._is_zoomed()
    df_view, _, _ = canvas._get_visible_slice()
    assert len(df_view) == 21

    # 模拟鼠标右键按下与松开 (无拖拽单击)
    press_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(300, 200),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mousePressEvent(press_ev)

    release_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(300, 200),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseReleaseEvent(release_ev)

    # 验证已一键重置为 100% 全景
    assert not canvas._is_zoomed()
    df_view_reset, s_i, e_i = canvas._get_visible_slice()
    assert len(df_view_reset) == 60
    assert s_i == 0
    assert e_i == 59


def test_sbc_canvas_box_zoom_and_channel_cutoff(qapp):
    """测试默认鼠标左键拖拽平移视图 (Pan) 与 Shift+左键框选放大 (Box Zoom)"""
    from PyQt6.QtCore import Qt, QPoint, QPointF
    from PyQt6.QtGui import QMouseEvent

    canvas = SBCChartCanvas()
    canvas.resize(600, 400)
    df_kline = _create_mock_kline_df(100)
    
    # 模拟极端通道下轨 (低于最低价 20%，测试是否截断且不崩溃)
    df_kline['ch_upper'] = df_kline['high'] * 1.05
    df_kline['ch_mid'] = df_kline['close']
    df_kline['ch_lower'] = df_kline['low'] * 0.70  # 极低值
    df_kline['ch_tc2'] = 10
    df_kline['ch_bc2'] = 10
    
    canvas.set_kline_data(df_kline=df_kline, period_mode="5m")

    # 1. 默认左键拖拽：执行平移视图 (Pan)
    press_pan_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(300, 150),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mousePressEvent(press_pan_ev)
    assert canvas._is_panning

    move_pan_ev = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(200, 150),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseMoveEvent(move_pan_ev)
    assert canvas._is_zoomed()  # 平移已切入可移动局部视口

    release_pan_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(200, 150),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseReleaseEvent(release_pan_ev)
    assert not canvas._is_panning

    # 2. Shift+左键拖拽：执行框选放大 (Rubberband Box Zoom)
    canvas.reset_view()
    assert not canvas._is_zoomed()

    press_zoom_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(100, 150),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier
    )
    canvas.mousePressEvent(press_zoom_ev)

    move_zoom_ev = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(300, 250),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier
    )
    canvas.mouseMoveEvent(move_zoom_ev)
    assert canvas._is_box_zooming

    release_zoom_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(300, 250),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ShiftModifier
    )
    canvas.mouseReleaseEvent(release_zoom_ev)
    assert not canvas._is_box_zooming
    assert canvas._is_zoomed()

    # 2. 模拟渲染，验证通道截断无异常
    img = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    try:
        canvas.render(painter)
    finally:
        painter.end()


def test_sbc_canvas_td_sequential_and_price_dedup(qapp):
    """测试神奇九转 (TD Sequential 9) 序列计算与 10 根 K 棒价格去重渲染"""
    from JSONData.tdx_data_Day import calc_trend_channel, td_sequential_fast
    
    canvas = SBCChartCanvas()
    canvas.resize(700, 450)
    
    # 构造持续上涨触发九转的数据
    df_raw = _create_mock_kline_df(60)
    df_kline = calc_trend_channel(df_raw)
    df_kline = td_sequential_fast(df_kline, lookback=4)
    
    assert "td_buy_count" in df_kline.columns
    assert "td_sell_count" in df_kline.columns
    assert "td_buy_signal" in df_kline.columns
    assert "td_sell_signal" in df_kline.columns

    canvas.set_kline_data(df_kline=df_kline, period_mode="60m")
    
    # 执行 paintEvent 渲染验证
    img = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    try:
        canvas.render(painter)
    finally:
        painter.end()


def test_sbc_canvas_hover_crosshair_and_price_display(qapp):
    """测试鼠标指针悬停时十字光标与价格浮标计算以及 leaveEvent 清除"""
    from PyQt6.QtCore import Qt, QPointF, QEvent
    from PyQt6.QtGui import QMouseEvent, QImage, QPainter

    canvas = SBCChartCanvas()
    canvas.resize(700, 450)
    df_kline = _create_mock_kline_df(80)
    canvas.set_kline_data(df_kline=df_kline, period_mode="day")

    # 1. 模拟鼠标移动到 (350, 200)
    move_ev = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(350, 200),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseMoveEvent(move_ev)
    assert canvas._hover_pos is not None
    assert canvas._hover_pos.x() == 350
    assert canvas._hover_pos.y() == 200

    # 2. 模拟渲染，验证十字光标与价格反推逻辑无崩溃
    img = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    try:
        canvas.render(painter)
    finally:
        painter.end()

    assert canvas._coord_info.get("ready", False) is True
    assert canvas._coord_info["min_p"] > 0
    assert canvas._coord_info["max_p"] > canvas._coord_info["min_p"]

    # 3. 模拟鼠标移出画布 (leaveEvent)
    leave_ev = QEvent(QEvent.Type.Leave)
    canvas.leaveEvent(leave_ev)
    assert canvas._hover_pos is None



