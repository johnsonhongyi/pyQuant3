# -*- coding: utf-8 -*-
"""
tests/test_sbc_backtest_trade_pnl.py — 测试 SBC 走势图加载多周期量化回测买卖标记与交互式点击收益
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPainter, QImage, QMouseEvent, QKeyEvent
from PyQt6.QtCore import Qt, QPointF, QPoint

# 确保项目根路径
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.multi_period_channel_backtester import (
    MultiPeriodChannelBacktester,
    convert_backtest_trades_to_sbc_signals
)
from ats.ui.intraday_strategy_dialog import (
    SBCChartCanvas,
    SBCIntradayChartDialog,
    open_sbc_chart_dialog
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _create_mock_daily_kline_df(count=60):
    """构造日K线数据，带有日期索引与通道指标"""
    dates = pd.date_range("2026-01-01", periods=count, freq="B")
    rows = []
    base_p = 4.0
    for i, d in enumerate(dates):
        d_str = d.strftime("%Y-%m-%d")
        op = base_p + np.sin(i / 8.0) * 0.8
        cl = op + np.cos(i / 5.0) * 0.3
        hi = max(op, cl) + 0.15
        lo = min(op, cl) - 0.15
        vol = 1000000.0 + i * 20000
        rows.append({
            "time": d_str,
            "open": op,
            "close": cl,
            "high": hi,
            "low": lo,
            "vol": vol,
            "amount": cl * vol,
            "ma5": cl,
            "ma20": cl * 0.96,
            "ch_upper": hi * 1.08,
            "ch_mid": cl,
            "ch_lower": lo * 0.92,
            "ch_tc2": 15,
            "ch_bc2": 15,
            "ch_supp_price": lo * 0.95,
            "ch_supp_days": 10,
            "ch_supp_slope": 0.01,
            "ch_supp_slope_deg": 12.5,
            "ch_supp_pos": 3.2,
            "ch_slope_deg": 8.0,
            "ch_pos": 65.0,
            "reversal_line": cl * 1.02
        })
    df = pd.DataFrame(rows).set_index("time")
    return df


def _create_mock_trades_df():
    """构造 3 笔典型回测交易记录"""
    trades = [
        {
            "code": "600108",
            "name": "亚盛集团",
            "buy_date": "2026-01-15",
            "sell_date": "2026-01-22",
            "holding_days": 5,
            "buy_price": 4.20,
            "sell_price": 4.82,
            "shares": 20000,
            "pnl": 12400.0,
            "pnl_pct": 14.76,
            "pattern_name": "共振起爆",
            "score": 92.5,
            "sell_reason": "触及通道上轨阻力位目标 (4.82)"
        },
        {
            "code": "600108",
            "name": "亚盛集团",
            "buy_date": "2026-02-05",
            "sell_date": "2026-02-12",
            "holding_days": 5,
            "buy_price": 4.50,
            "sell_price": 5.03,
            "shares": 20000,
            "pnl": 10600.0,
            "pnl_pct": 11.78,
            "pattern_name": "共振起爆",
            "score": 88.0,
            "sell_reason": "移动跟踪止盈"
        },
        {
            "code": "600108",
            "name": "亚盛集团",
            "buy_date": "2026-02-25",
            "sell_date": "2026-03-02",
            "holding_days": 3,
            "buy_price": 4.90,
            "sell_price": 4.75,
            "shares": 20000,
            "pnl": -3000.0,
            "pnl_pct": -3.06,
            "pattern_name": "支撑确认",
            "score": 81.0,
            "sell_reason": "跌破通道支撑止损线 (4.75)"
        }
    ]
    return pd.DataFrame(trades)


def test_convert_backtest_trades_to_sbc_signals():
    """测试将 trades_df 转换生成配对的 SBC 标准买卖信号列表"""
    trades_df = _create_mock_trades_df()
    signals = convert_backtest_trades_to_sbc_signals(trades_df)

    # 3 笔交易应生成 6 个买卖信号点 (3买 + 3卖)
    assert len(signals) == 6

    # 验证配对关系与字段
    buy_signals = [s for s in signals if s["action"] == "buy"]
    sell_signals = [s for s in signals if s["action"] == "sell"]
    assert len(buy_signals) == 3
    assert len(sell_signals) == 3

    # 验证交易 #0
    sig_b0 = next(s for s in buy_signals if s["trade_id"] == 0)
    sig_s0 = next(s for s in sell_signals if s["trade_id"] == 0)
    assert sig_b0["price"] == 4.20
    assert sig_b0["time"] == "2026-01-15"
    assert sig_b0["paired_date"] == "2026-01-22"
    assert sig_b0["paired_price"] == 4.82

    assert sig_s0["price"] == 4.82
    assert sig_s0["time"] == "2026-01-22"
    assert sig_s0["pnl_pct"] == 14.76
    assert sig_s0["pnl"] == 12400.0
    assert sig_s0["holding_days"] == 5


def test_sbc_canvas_kline_paint_with_backtest_signals_and_hit_boxes(qapp):
    """测试 SBCChartCanvas 在日K模式下根据回测买卖日期精确定位K棒并注册点击命中框"""
    canvas = SBCChartCanvas()
    canvas.resize(800, 500)

    df_kline = _create_mock_daily_kline_df(60)
    trades_df = _create_mock_trades_df()
    signals = convert_backtest_trades_to_sbc_signals(trades_df)

    canvas.set_kline_data(
        df_kline=df_kline,
        open_p=float(df_kline['open'].iloc[0]),
        vwap_p=float(df_kline['close'].mean()),
        high_p=float(df_kline['high'].max()),
        low_p=float(df_kline['low'].min()),
        signals=signals,
        period_mode="day"
    )

    # 模拟渲染绘制
    img = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    try:
        canvas.render(painter)
    finally:
        painter.end()

    # 验证 _signal_hit_boxes 成功记录了全部 6 个信号点击区
    assert len(canvas._signal_hit_boxes) == 6
    for hb in canvas._signal_hit_boxes:
        assert hb["rect"].isValid()
        assert hb["rect"].width() > 10
        assert hb["rect"].height() > 10
        assert hb["trade_id"] in (0, 1, 2)


def test_sbc_canvas_click_signal_selects_trade_and_renders_linkage(qapp):
    """测试鼠标点击买卖信号标签触发点击收益交互与持仓光束渲染"""
    canvas = SBCChartCanvas()
    canvas.resize(800, 500)

    df_kline = _create_mock_daily_kline_df(60)
    trades_df = _create_mock_trades_df()
    signals = convert_backtest_trades_to_sbc_signals(trades_df)

    canvas.set_kline_data(df_kline=df_kline, signals=signals, period_mode="day")

    # 渲染一次建立 hit_boxes
    img = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    try:
        canvas.render(painter)
    finally:
        painter.end()

    assert len(canvas._signal_hit_boxes) > 0
    # 模拟点击第 1 笔交易 (trade_id=1) 的卖出标签中心
    target_box = next(hb for hb in canvas._signal_hit_boxes if hb["trade_id"] == 1 and not hb["is_buy"])
    click_pos = target_box["rect"].center()

    press_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(click_pos.x(), click_pos.y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mousePressEvent(press_ev)

    # 验证成功选中了 trade_id=1
    assert canvas.selected_trade_id == 1

    # 再次渲染验证 _draw_selected_trade_linkage 绘制光束、色块与浮动卡片无崩溃
    img2 = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    painter2 = QPainter(img2)
    try:
        canvas.render(painter2)
    finally:
        painter2.end()


def test_sbc_canvas_cycle_selected_trade_and_shortcuts(qapp):
    """测试 Space / [ / ] 快捷键与 cycle_selected_trade 轮换切换交易"""
    canvas = SBCChartCanvas()
    canvas.resize(800, 500)

    trades_df = _create_mock_trades_df()
    signals = convert_backtest_trades_to_sbc_signals(trades_df)
    canvas.signals = signals

    # 1. 初始未选中时调用 cycle_selected_trade(1) 选中第一笔 trade_id=0
    canvas.cycle_selected_trade(1)
    assert canvas.selected_trade_id == 0

    # 2. 再次向前步进 -> trade_id=1
    canvas.cycle_selected_trade(1)
    assert canvas.selected_trade_id == 1

    # 3. 再次向前步进 -> trade_id=2
    canvas.cycle_selected_trade(1)
    assert canvas.selected_trade_id == 2

    # 4. 环形轮转回到 0
    canvas.cycle_selected_trade(1)
    assert canvas.selected_trade_id == 0

    # 5. 向后步进 -> trade_id=2
    canvas.cycle_selected_trade(-1)
    assert canvas.selected_trade_id == 2

    # 6. 测试按键事件: 按下 Space
    key_ev_space = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.keyPressEvent(key_ev_space)
    assert canvas.selected_trade_id == 0


def test_sbc_dialog_set_custom_backtest_trades(qapp):
    """测试 SBCIntradayChartDialog.set_custom_backtest_trades 完整注入与标题更新"""
    trades_df = _create_mock_trades_df()
    df_kline = _create_mock_daily_kline_df(60)

    dlg = SBCIntradayChartDialog(code="600108")
    try:
        dlg.set_custom_backtest_trades(trades_df, df_kline=df_kline)

        assert dlg.canvas.period_mode == "day"
        assert len(dlg.canvas.signals) == 6
        assert dlg.canvas.selected_trade_id == 0
        assert "多周期通道回测" in dlg.lbl_title.text()
        assert "胜率:66.7%" in dlg.lbl_title.text()
        assert "交易:3笔" in dlg.lbl_title.text()
    finally:
        dlg.close()


def test_open_sbc_chart_dialog_with_backtest_trades(qapp):
    """测试 open_sbc_chart_dialog 支持 trades_df 参数直接唤醒并注入回测交易"""
    trades_df = _create_mock_trades_df()
    df_kline = _create_mock_daily_kline_df(60)

    dlg = open_sbc_chart_dialog(
        code="600108",
        period_mode="day",
        trades_df=trades_df,
        df_kline=df_kline
    )
    try:
        assert dlg is not None
        assert dlg.canvas.selected_trade_id == 0
        assert len(dlg.canvas.signals) == 6
    finally:
        dlg.close()


def test_backtester_plot_in_sbc_helper(qapp):
    """测试 MultiPeriodChannelBacktester.plot_in_sbc 快捷调起方法"""
    bt = MultiPeriodChannelBacktester()
    trades_df = _create_mock_trades_df()
    df_kline = _create_mock_daily_kline_df(60)
    mock_report = {
        "code": "600108",
        "name": "亚盛集团",
        "trades_df": trades_df,
        "total_trades": len(trades_df)
    }

    dlg = bt.plot_in_sbc(mock_report, df_kline=df_kline)
    try:
        assert dlg is not None
        assert dlg.canvas.selected_trade_id == 0
    finally:
        dlg.close()
