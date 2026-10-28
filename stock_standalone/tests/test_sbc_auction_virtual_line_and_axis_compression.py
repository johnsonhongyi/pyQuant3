# -*- coding: utf-8 -*-
"""
tests/test_sbc_auction_virtual_line_and_axis_compression.py
SBC 集合竞价虚拟现价水平线、右轴胶囊及坐标轴防压缩离群值治理专项测试
"""
import sys
import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.ui.intraday_strategy_dialog import SBCChartCanvas


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_tdx_normalize_quote_safe_low_price_fallback():
    """验证在早盘/竞价期间 quote 无 price/open/low 时，安全取 last_close，绝不硬编码 10.0"""
    fetcher = TDXRealtimeFetcher.get_instance()
    # 模拟北新路桥 (002307) 3.22元，盘口尚未成交
    q_bidding = {
        "code": "002307",
        "price": 0.0,
        "open": 0.0,
        "high": 0.0,
        "low": 0.0,
        "last_close": 3.22,
        "vol": 0,
        "amount": 0.0
    }
    snap = fetcher._normalize_quote_to_snapshot(q_bidding)
    # 必须回退至昨收 3.22，绝对不能变成 10.0
    assert snap["low_price"] == pytest.approx(3.22, abs=0.01)
    assert snap["high_price"] == pytest.approx(3.22, abs=0.01)

    # 模拟长城军工 (601606) 30.68元，盘口尚未成交
    q_military = {
        "code": "601606",
        "price": 0.0,
        "open": 0.0,
        "high": 0.0,
        "low": 0.0,
        "last_close": 30.68,
        "vol": 0,
        "amount": 0.0
    }
    snap2 = fetcher._normalize_quote_to_snapshot(q_military)
    assert snap2["low_price"] == pytest.approx(30.68, abs=0.01)
    assert snap2["high_price"] == pytest.approx(30.68, abs=0.01)


def test_sbc_auction_virtual_price_line_and_right_capsule(qapp):
    """
    【需求 1 专项测试】
    集合竞价虚拟撮合价 (如 269.00) 绘制虚拟水平线、右侧胶囊，
    并自动将竞价价格纳入 Y 轴候选点，保证走势图包容该虚拟水平线。
    """
    canvas = SBCChartCanvas()
    canvas.resize(600, 400)
    canvas.code = "300750"

    # 模拟历史走势：价格在 260 ~ 265 之间，基准开盘价 262.0
    times = [f"10-27 {h:02d}:{m:02d}" for h in (9, 10, 11) for m in range(0, 60, 5)]
    prices = [260.0 + (i % 10) * 0.5 for i in range(len(times))]
    df_bars = pd.DataFrame({
        "time": times,
        "close": prices,
        "open": prices,
        "high": [p + 0.5 for p in prices],
        "low": [p - 0.5 for p in prices],
        "vwap": prices,
        "vol": [100.0] * len(times),
        "amount": [p * 100.0 for p in prices],
    }).set_index("time")

    # 设置集合竞价未成交撮合价为 269.00 (高开 +2.6%)
    canvas.market_phase = "auction_indicative"
    canvas.auction_price = 269.00
    canvas.auction_samples = [
        {"time_only": "09:20", "price": 269.00, "kind": "auction_indicative"}
    ]

    canvas.set_data(
        df_bars,
        open_p=262.0,
        vwap_p=262.5,
        high_p=265.0,
        low_p=259.5,
        sell_min=0.0,
        sell_max=0.0,
        signals=[],
        period_mode="1m"
    )

    # 触发渲染
    pix = QPixmap(600, 400)
    painter = QPainter(pix)
    try:
        canvas._paint_intraday(painter, 62, 22, 480, 350)
    finally:
        painter.end()

    # 坐标系校验
    coord = getattr(canvas, "_coord_info", {})
    assert coord.get("ready") is True
    # Y 轴最大值必须包容 269.00 (因为竞价到了 269.00)
    assert coord["max_p"] >= 269.0
    assert coord["min_p"] <= 260.0


def test_sbc_auction_axis_compression_defense_for_low_priced_stock(qapp):
    """
    【需求 2 专项测试：低价股 (如北新路桥 3.22元) 防压缩治理】
    即使盘口传入 low_price=10.0 或历史数据混入 8.65 离群毛刺，
    统计学防御与集合竞价门禁坚决将其剔除，坐标轴绝不被撑爆压扁！
    """
    canvas = SBCChartCanvas()
    canvas.resize(600, 400)
    canvas.code = "002307"

    # 模拟真实分时数据在 3.10 ~ 3.35 之间
    times = [f"10-27 {h:02d}:{m:02d}" for h in (9, 10, 11) for m in range(0, 60, 5)]
    prices = [3.15 + (i % 8) * 0.02 for i in range(len(times))]
    highs = [p + 0.03 for p in prices]
    # 模拟一根异常脏数据毛刺：high 误被写成了 8.65
    highs[-1] = 8.65

    df_bars = pd.DataFrame({
        "time": times,
        "close": prices,
        "open": prices,
        "high": highs,
        "low": [p - 0.03 for p in prices],
        "vwap": prices,
        "vol": [1000.0] * len(times),
        "amount": [p * 1000.0 for p in prices],
    }).set_index("time")

    # 处于竞价时段，且外部参考值被传入了 10.0 (旧逻辑Bug)
    canvas.market_phase = "auction_indicative"
    canvas.auction_price = 3.25
    canvas.high_price = 8.65
    canvas.low_price = 10.0  # 离群脏数据
    canvas.target_sell_min = 7.64

    canvas.set_data(
        df_bars,
        open_p=3.20,
        vwap_p=3.22,
        high_p=8.65,
        low_p=10.0,
        sell_min=7.64,
        sell_max=0.0,
        signals=[],
        period_mode="5d"
    )

    pix = QPixmap(600, 400)
    painter = QPainter(pix)
    try:
        canvas._paint_intraday(painter, 62, 22, 480, 350)
    finally:
        painter.end()

    coord = getattr(canvas, "_coord_info", {})
    assert coord.get("ready") is True

    # 核心断言：max_p 绝不能被撑到 8.65 或 10.0！
    # 3.2 附近的股票，max_p 应当在 3.6 以下，min_p 在 2.9 以上
    assert coord["max_p"] < 4.0, f"max_p 被撑到了 {coord['max_p']}，防压缩失败！"
    assert coord["min_p"] > 2.8, f"min_p 塌陷到了 {coord['min_p']}，防压缩失败！"
    # 跨度应该小于 1.0 元，保持走势图舒展饱满，绝不是被压缩的一条横线
    assert (coord["max_p"] - coord["min_p"]) < 1.0


def test_sbc_auction_axis_compression_defense_for_high_priced_stock(qapp):
    """
    【需求 2 专项测试：中高价股 (如长城军工 30.68元) 防压缩治理】
    即使混入 14.79 或 41.51 离群值，坐标轴坚决拦截，保持走势图舒展。
    """
    canvas = SBCChartCanvas()
    canvas.resize(600, 400)
    canvas.code = "601606"

    # 模拟真实分时数据在 30.0 ~ 32.5 之间
    times = [f"10-27 {h:02d}:{m:02d}" for h in (9, 10, 11) for m in range(0, 60, 5)]
    prices = [30.5 + (i % 6) * 0.3 for i in range(len(times))]

    df_bars = pd.DataFrame({
        "time": times,
        "close": prices,
        "open": prices,
        "high": [p + 0.2 for p in prices],
        "low": [p - 0.2 for p in prices],
        "vwap": prices,
        "vol": [1000.0] * len(times),
        "amount": [p * 1000.0 for p in prices],
    }).set_index("time")

    # 处于竞价时段，外部参考值被传入了 14.79 和 41.51
    canvas.market_phase = "auction_open"
    canvas.auction_price = 31.00
    canvas.high_price = 41.51
    canvas.low_price = 14.79

    canvas.set_data(
        df_bars,
        open_p=30.68,
        vwap_p=31.2,
        high_p=41.51,
        low_p=14.79,
        sell_min=0.0,
        sell_max=0.0,
        signals=[],
        period_mode="1m"
    )

    pix = QPixmap(600, 400)
    painter = QPainter(pix)
    try:
        canvas._paint_intraday(painter, 62, 22, 480, 350)
    finally:
        painter.end()

    coord = getattr(canvas, "_coord_info", {})
    assert coord.get("ready") is True

    # 核心断言：max_p 绝不能达到 40，min_p 绝不能掉到 20 以下！
    assert coord["max_p"] < 35.0, f"max_p 被撑到了 {coord['max_p']}，防压缩失败！"
    assert coord["min_p"] > 27.0, f"min_p 塌陷到了 {coord['min_p']}，防压缩失败！"
