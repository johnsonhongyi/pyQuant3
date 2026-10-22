# -*- coding: utf-8 -*-
"""
tests/test_sbc_gap_channels.py — SBC 跳空缺口通道带与阶梯回补专项自动化测试
覆盖：
1. K 线向上跳空缺口生成、后续下杀部分回补收窄与向右延伸 (星光股份 002076 实盘复现)
2. 底层引擎全回补检测与有效缺口筛选 (完全打穿后不再在图表显示)
3. 向下跳空缺口生成、冲高部分回补收窄与完全回补
4. 多日分时日间跳空缺口生成与动态回补收窄 (北新路桥 002307 实盘复现)
5. 10D 真实多日分时左侧假缺口彻底消除测试 (杜绝跨日 op_ref 污染，缺口仅由今天跳空高开产生)
6. 单日分时早盘跳空缺口 (相对昨收 op_ref) 生成与日内回补
7. SBCChartCanvas 真实 QPainter 渲染 Smoke 测试与开/关切换
"""

import sys
import os
import pytest
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtCore import Qt

from ats.ui.intraday_strategy_dialog import SBCChartCanvas


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest_gui"])
    return app


def test_kline_up_gap_lifecycle_and_step_reduction():
    """
    【星光股份 002076 实盘复现】
    向上跳空缺口生成、下杀部分回补阶梯收窄并向右延伸
    """
    # 模拟数据：
    # bar 0: High = 2.30, Low = 2.20
    # bar 1: High = 2.50, Low = 2.40  -> 向上缺口 [2.30, 2.40]
    # bar 2: High = 2.55, Low = 2.42  -> 维持 [2.30, 2.40]
    # bar 3: High = 2.45, Low = 2.38  -> 今日下杀到 2.38，缺口收窄为 [2.30, 2.38]
    # bar 4: High = 2.42, Low = 2.38  -> 延续 [2.30, 2.38]
    highs = np.array([2.30, 2.50, 2.55, 2.45, 2.42], dtype=float)
    lows = np.array([2.20, 2.40, 2.42, 2.38, 2.38], dtype=float)

    canvas = SBCChartCanvas()
    gaps = canvas._compute_kline_gaps(highs, lows)

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["type"] == "UP"
    assert pytest.approx(gap["init_low"]) == 2.30
    assert pytest.approx(gap["init_high"]) == 2.40
    assert gap["start_idx"] == 1
    assert gap["is_closed"] is False

    # 验证分段阶梯：应当包含 2 个分段
    # 段 0: [1, 3] 区间 2.30 ~ 2.40
    # 段 1: [3, 4] 区间 2.30 ~ 2.38
    assert len(gap["segments"]) == 2
    seg0 = gap["segments"][0]
    assert seg0[0] == 1
    assert seg0[1] == 3
    assert pytest.approx(seg0[2]) == 2.30
    assert pytest.approx(seg0[3]) == 2.40

    seg1 = gap["segments"][1]
    assert seg1[0] == 3
    assert seg1[1] == 4
    assert pytest.approx(seg1[2]) == 2.30
    assert pytest.approx(seg1[3]) == 2.38


def test_kline_up_gap_full_fill_closure():
    """
    向上跳空缺口后续被完全打穿，底层引擎标记关闭，图表层不再显示已闭合缺口
    """
    # bar 0: High = 10.0, Low = 9.5
    # bar 1: High = 11.5, Low = 10.8  -> 向上缺口 [10.0, 10.8]
    # bar 2: High = 11.0, Low = 10.4  -> 部分回补，收窄为 [10.0, 10.4]
    # bar 3: High = 10.5, Low = 9.8   -> 完全打穿 10.0，缺口在 bar 3 完全回补关闭！
    # bar 4: High = 10.2, Low = 9.9
    highs = np.array([10.0, 11.5, 11.0, 10.5, 10.2], dtype=float)
    lows = np.array([9.5, 10.8, 10.4, 9.8, 9.9], dtype=float)

    canvas = SBCChartCanvas()
    candidates = [(1, 10.0, 9.5)]
    all_gaps = canvas._calculate_gaps_engine(highs, lows, candidates)

    assert len(all_gaps) == 1
    gap = all_gaps[0]
    assert gap["type"] == "UP"
    assert gap["is_closed"] is True
    assert gap["close_idx"] == 3

    # 图表计算接口遵循通达信标准：已完全闭合的缺口自动清除不显示
    visible_gaps = canvas._compute_kline_gaps(highs, lows)
    assert len(visible_gaps) == 0


def test_kline_down_gap_lifecycle_and_step_reduction():
    """
    向下跳空缺口生成、冲高部分回补收窄与完全回补
    """
    # bar 0: High = 20.0, Low = 19.0
    # bar 1: High = 18.0, Low = 17.5  -> 向下缺口 [18.0, 19.0]
    # bar 2: High = 18.2, Low = 17.6  -> 冲高至 18.2 部分回补收窄
    # bar 3: High = 18.6, Low = 18.1  -> 冲高至 18.6 进一步收窄为 [18.6, 19.0]
    highs = np.array([20.0, 18.0, 18.2, 18.6], dtype=float)
    lows = np.array([19.0, 17.5, 17.6, 18.1], dtype=float)

    canvas = SBCChartCanvas()
    gaps = canvas._compute_kline_gaps(highs, lows)

    down_gaps = [g for g in gaps if g["type"] == "DOWN"]
    assert len(down_gaps) == 1
    gap = down_gaps[0]
    assert gap["type"] == "DOWN"
    assert pytest.approx(gap["init_low"]) == 18.0
    assert pytest.approx(gap["init_high"]) == 19.0
    assert gap["is_closed"] is False

    # 验证分段：
    # bar 2 冲高至 18.2 (部分回补 18.0~18.2，缺口收窄为 18.2~19.0)
    # bar 3 冲高至 18.6 (部分回补 18.2~18.6，缺口收窄为 18.6~19.0)
    assert len(gap["segments"]) == 3
    assert gap["segments"][0] == (1, 2, 18.0, 19.0)
    assert gap["segments"][1] == (2, 3, 18.2, 19.0)
    assert gap["segments"][2] == (3, 3, 18.6, 19.0)


def test_intraday_multi_day_gap_and_step_reduction():
    """
    【北新路桥 002307 5日分时实盘复现】
    多日分时图日间跳空缺口生成、盘中下杀收窄与向右延伸
    """
    # 模拟两天分时数据：
    # Day 1: 3 根分钟线 (最高 5.80, 最低 5.50)
    # Day 2: 3 根分钟线 (开盘最低 6.30，最高 6.40，形成向上日间缺口 [5.80, 6.30])
    #        第 2 分钟下杀到 6.10，收窄为 [5.80, 6.10]
    df_intraday = pd.DataFrame({
        "date": ["2026-10-20"] * 3 + ["2026-10-21"] * 3,
        "high": [5.60, 5.80, 5.70, 6.40, 6.35, 6.25],
        "low":  [5.50, 5.65, 5.60, 6.30, 6.10, 6.15],
        "close": [5.55, 5.75, 5.68, 6.35, 6.15, 6.20],
    }, index=["09:30", "10:30", "15:00", "09:30", "10:30", "15:00"])

    canvas = SBCChartCanvas()
    highs = df_intraday["high"].values
    lows = df_intraday["low"].values
    times = list(df_intraday.index.astype(str))

    gaps = canvas._compute_intraday_gaps(df_intraday, highs, lows, times, op_ref=5.50)

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["type"] == "UP"
    assert pytest.approx(gap["init_low"]) == 5.80
    assert pytest.approx(gap["init_high"]) == 6.30
    assert gap["start_idx"] == 3  # Day 2 开始于 index 3
    assert gap["is_closed"] is False

    # 验证分段：
    # 段 0: 从 3 到 4，高度 5.80 ~ 6.30
    # 段 1: 从 4 到 5 (末尾)，下杀到 6.10，高度收窄为 5.80 ~ 6.10
    assert len(gap["segments"]) == 2
    assert gap["segments"][0] == (3, 4, 5.80, 6.30)
    assert gap["segments"][1] == (4, 5, 5.80, 6.10)


def test_002307_10d_intraday_no_left_fake_gaps():
    """
    【002307 北新路桥 10D 实测闭环】
    多日分时左侧历史天数绝对不产生虚假缺口，缺口仅在今天跳空高开产生
    """
    # 模拟 10 天各 2 根柱子 (左侧前 9 天在 2.90~3.05 之间，今天 10-22 跳空高开 3.39，盘中探底 3.25)
    days = [f"2026-10-{i:02d}" for i in range(1, 10)] + ["2026-10-22"]
    dates_list = []
    high_list = []
    low_list = []
    close_list = []
    for d in days[:-1]:
        dates_list.extend([d, d])
        high_list.extend([3.04, 3.02])
        low_list.extend([2.95, 2.96])
        close_list.extend([3.00, 3.03])

    # 今天 10-22 跳空高开在 3.39，低点 3.25
    today = "2026-10-22"
    dates_list.extend([today, today])
    high_list.extend([3.39, 3.39])
    low_list.extend([3.39, 3.25])
    close_list.extend([3.39, 3.39])

    df_10d = pd.DataFrame({
        "date": dates_list,
        "high": high_list,
        "low": low_list,
        "close": close_list,
    })

    canvas = SBCChartCanvas()
    highs = df_10d["high"].values
    lows = df_10d["low"].values
    times = [f"T{i}" for i in range(len(df_10d))]

    # 传入今天的 op_ref = 3.39
    gaps = canvas._compute_intraday_gaps(df_10d, highs, lows, times, op_ref=3.39)

    # 核心断言：
    # 1. 绝不能在 index 0 (10天前) 或左侧历史产生任何虚假缺口！
    # 2. 全图仅有且只有 1 个缺口，且起始点必须是今天 10-22 开盘 (start_idx = 18)！
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["type"] == "UP"
    assert gap["start_idx"] == 18  # 今天 10-22
    assert pytest.approx(gap["init_low"]) == 3.04  # 昨天全天最高 3.04
    assert pytest.approx(gap["segments"][-1][3]) == 3.25  # 经今天下杀至 3.25 后收窄为 [3.04, 3.25]
    assert gap["is_closed"] is False


def test_intraday_single_day_gap_with_op_ref():
    """
    单日分时图早盘跳空 (相对昨收 op_ref) 生成与回补
    """
    # 昨收 op_ref = 10.00
    # 09:30 首根最低 10.50，最高 10.60 -> 跳空缺口 [10.00, 10.50]
    # 09:31 最低 10.20 -> 收窄为 [10.00, 10.20]
    df_day = pd.DataFrame({
        "date": ["2026-10-22"] * 2,
        "high": [10.60, 10.40],
        "low":  [10.50, 10.20],
        "close": [10.55, 10.25],
    }, index=["09:30", "09:31"])

    canvas = SBCChartCanvas()
    highs = df_day["high"].values
    lows = df_day["low"].values
    times = list(df_day.index.astype(str))

    gaps = canvas._compute_intraday_gaps(df_day, highs, lows, times, op_ref=10.00)

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["type"] == "UP"
    assert pytest.approx(gap["init_low"]) == 10.00
    assert pytest.approx(gap["init_high"]) == 10.50
    assert gap["is_closed"] is False
    assert gap["segments"][-1] == (1, 1, 10.00, 10.20)


def test_canvas_paint_gap_channels_smoke(qapp):
    """
    SBCChartCanvas 真实 QPainter 渲染 Smoke 测试：
    确保在 K 线模式和分时模式下，开启缺口通道带绘制 100% 稳定无异常
    """
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    canvas.show_gap_channels = True

    # 1. 模拟 K 线模式数据 (日K)
    dates = pd.date_range("2026-09-01", periods=10, freq="B").strftime("%Y-%m-%d")
    df_kline = pd.DataFrame({
        "open":  [10.0, 10.8, 11.2, 11.5, 11.0, 10.6, 12.0, 12.5, 12.2, 12.8],
        "close": [10.5, 11.0, 11.4, 11.2, 10.8, 11.8, 12.4, 12.3, 12.6, 13.0],
        "high":  [10.6, 11.3, 11.6, 11.6, 11.2, 12.0, 12.6, 12.8, 12.7, 13.2],
        "low":   [9.8,  10.7, 11.0, 11.0, 10.5, 10.5, 11.9, 12.1, 12.0, 12.5],
        "vol":   [1000] * 10,
    }, index=dates)

    canvas.set_kline_data(df_kline, open_p=10.0, period_mode="day")
    pix = QPixmap(800, 600)
    pix.fill(Qt.GlobalColor.black)
    p = QPainter(pix)
    try:
        canvas._paint_kline(p, 50, 20, 700, 500)
    finally:
        p.end()

    # 2. 模拟分时模式数据 (多日分时)
    df_intraday = pd.DataFrame({
        "date": ["2026-10-20"] * 5 + ["2026-10-21"] * 5,
        "open":  [5.55, 5.65, 5.62, 5.70, 5.74, 6.35, 6.20, 6.18, 6.22, 6.24],
        "high": [5.60, 5.80, 5.70, 5.75, 5.78, 6.40, 6.35, 6.25, 6.30, 6.28],
        "low":  [5.50, 5.65, 5.60, 5.68, 5.70, 6.30, 6.10, 6.15, 6.20, 6.22],
        "close": [5.55, 5.75, 5.68, 5.72, 5.75, 6.35, 6.15, 6.20, 6.25, 6.26],
        "vwap": [5.52, 5.70, 5.65, 5.70, 5.72, 6.32, 6.20, 6.18, 6.22, 6.24],
        "vol":  [100] * 10,
    }, index=[f"T{i}" for i in range(10)])

    canvas.set_data(df_intraday, open_p=5.50, period_mode="2d")
    pix2 = QPixmap(800, 600)
    pix2.fill(Qt.GlobalColor.black)
    p2 = QPainter(pix2)
    try:
        canvas._paint_intraday(p2, 50, 20, 700, 500)
    finally:
        p2.end()

    # 3. 验证开关缺口通道带
    canvas.show_gap_channels = False
    pix3 = QPixmap(800, 600)
    p3 = QPainter(pix3)
    try:
        canvas._paint_kline(p3, 50, 20, 700, 500)
        canvas._paint_intraday(p3, 50, 20, 700, 500)
    finally:
        p3.end()
