# -*- coding: utf-8 -*-
"""
tests/test_sbc_theme_and_boll.py — SBC 3组高对比主题色与K线通达信标准BOLL布林带专项自动化测试
覆盖：
1. 3 组主题色（pitch_dark / deep_navy / pro_charcoal）轮换切换与持久化读写
2. 通达信标准 BOLL (20, 2) 向量化计算精度 (与通达信官方公式严格对齐)
3. BOLL 布林带默认开启与 toggle_boll 切换及持久化记忆
4. 3 组主题下 K 线与分时 QPainter 真实渲染 Smoke 测试
5. 快捷键 B 键与 T 键事件响应测试
"""

import os
import pytest
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QKeyEvent
from PyQt6.QtCore import Qt, QEvent

from ats.ui.sbc_preferences import (
    get_sbc_theme_mode,
    set_sbc_theme_mode,
    get_sbc_show_boll,
    set_sbc_show_boll,
    VALID_THEMES,
)
from ats.ui.intraday_strategy_dialog import SBCChartCanvas, SBC_THEMES


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest_theme_boll"])
    return app


def test_theme_presets_definition():
    """验证 3 组专业高对比主题色定义完整且关键色彩参数齐备"""
    for mode in ("pitch_dark", "deep_navy", "pro_charcoal"):
        assert mode in SBC_THEMES
        theme = SBC_THEMES[mode]
        assert "name" in theme
        assert "bg_color" in theme
        assert "border_color" in theme
        assert "grid_color" in theme
        assert "gap_up_brush" in theme
        assert "gap_dn_brush" in theme
        assert "gap_badge_bg" in theme
        assert "gap_badge_border" in theme
        assert "gap_badge_text" in theme


def test_theme_switching_and_persistence():
    """验证主题色循环切换与持久化保存"""
    # 恢复初始状态
    set_sbc_theme_mode("pitch_dark")
    assert get_sbc_theme_mode() == "pitch_dark"

    canvas = SBCChartCanvas()
    assert canvas.theme_mode == "pitch_dark"

    # 循环切换第 1 次: pitch_dark -> deep_navy
    canvas.cycle_theme()
    assert canvas.theme_mode == "deep_navy"
    assert get_sbc_theme_mode() == "deep_navy"
    assert "0e1626" in canvas.styleSheet().lower()

    # 循环切换第 2 次: deep_navy -> pro_charcoal
    canvas.cycle_theme()
    assert canvas.theme_mode == "pro_charcoal"
    assert get_sbc_theme_mode() == "pro_charcoal"
    assert "1a1d24" in canvas.styleSheet().lower()

    # 循环切换第 3 次: pro_charcoal -> pitch_dark
    canvas.cycle_theme()
    assert canvas.theme_mode == "pitch_dark"
    assert get_sbc_theme_mode() == "pitch_dark"
    assert "0a0b0e" in canvas.styleSheet().lower()

    # 直接设置指定主题
    canvas.set_theme("deep_navy")
    assert canvas.theme_mode == "deep_navy"
    assert get_sbc_theme_mode() == "deep_navy"

    # 验证新实例能正确加载持久化主题
    new_canvas = SBCChartCanvas()
    assert new_canvas.theme_mode == "deep_navy"

    # 还原
    set_sbc_theme_mode("pitch_dark")


def test_boll_calculation_precision_and_alignment():
    """
    验证通达信标准 BOLL (20, 2) 算法与精度：
    MID = MA(C, 20)
    UB = MID + 2 * STD(C, 20, ddof=0)
    LB = MID - 2 * STD(C, 20, ddof=0)
    """
    np.random.seed(42)
    closes = np.array([10.0 + i * 0.15 + np.sin(i) * 0.5 for i in range(30)], dtype=float)
    df = pd.DataFrame({
        "close": closes,
        "open": closes - 0.05,
        "high": closes + 0.10,
        "low": closes - 0.10,
        "vol": [1000] * 30,
    })

    canvas = SBCChartCanvas()
    canvas.set_kline_data(df, open_p=closes[0], period_mode="day")

    # 验证 df_intraday 中自动计算了通达信标准 BOLL
    assert "boll_mid" in canvas.df_intraday.columns
    assert "boll_upper" in canvas.df_intraday.columns
    assert "boll_lower" in canvas.df_intraday.columns

    # 针对第 25 根 K 棒精确手算核对通达信标准
    window_closes = closes[6:26]  # 20 根
    expected_mid = float(np.mean(window_closes))
    expected_std = float(np.std(window_closes, ddof=0))  # 通达信 ddof=0
    expected_ub = expected_mid + 2.0 * expected_std
    expected_lb = expected_mid - 2.0 * expected_std

    actual_mid = canvas.df_intraday["boll_mid"].iloc[25]
    actual_ub = canvas.df_intraday["boll_upper"].iloc[25]
    actual_lb = canvas.df_intraday["boll_lower"].iloc[25]

    assert pytest.approx(actual_mid, abs=1e-5) == expected_mid
    assert pytest.approx(actual_ub, abs=1e-5) == expected_ub
    assert pytest.approx(actual_lb, abs=1e-5) == expected_lb


def test_boll_toggle_and_persistence():
    """验证 BOLL 布林带开关默认开启、切换与持久化"""
    # 默认应当为 True
    set_sbc_show_boll(True)
    assert get_sbc_show_boll() is True

    canvas = SBCChartCanvas()
    assert canvas.show_boll is True

    # 切换为 False
    canvas.toggle_boll()
    assert canvas.show_boll is False
    assert get_sbc_show_boll() is False

    # 新建画布实例继承用户偏好 False
    c2 = SBCChartCanvas()
    assert c2.show_boll is False

    # 再次切换恢复为 True
    canvas.toggle_boll()
    assert canvas.show_boll is True
    assert get_sbc_show_boll() is True


def test_paint_smoke_all_themes_and_boll(qapp):
    """Smoke 测试：在 3 组主题下、开/关 BOLL 时执行真实 QPainter 渲染 100% 稳定无异常"""
    dates = pd.date_range("2026-09-01", periods=25, freq="B").strftime("%Y-%m-%d")
    df_kline = pd.DataFrame({
        "open":  [10.0 + i * 0.1 for i in range(25)],
        "close": [10.2 + i * 0.1 for i in range(25)],
        "high":  [10.5 + i * 0.1 for i in range(25)],
        "low":   [9.8 + i * 0.1 for i in range(25)],
        "vol":   [2000] * 25,
    }, index=dates)

    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    canvas.set_kline_data(df_kline, open_p=10.0, period_mode="day")

    pix = QPixmap(800, 600)

    for theme_mode in ("pitch_dark", "deep_navy", "pro_charcoal"):
        canvas.set_theme(theme_mode)
        for boll_state in (True, False):
            canvas.show_boll = boll_state
            pix.fill(Qt.GlobalColor.black)
            p = QPainter(pix)
            try:
                canvas._paint_kline(p, 50, 20, 700, 500)
            finally:
                p.end()

            # 分时图渲染验证
            df_intraday = pd.DataFrame({
                "date": ["2026-10-22"] * 10,
                "open": [10.0] * 10,
                "high": [10.5] * 10,
                "low": [9.9] * 10,
                "close": [10.2] * 10,
                "vwap": [10.1] * 10,
                "vol": [500] * 10,
            }, index=[f"09:{30+i:02d}" for i in range(10)])
            canvas.set_data(df_intraday, open_p=10.0, period_mode="1m")
            p2 = QPainter(pix)
            try:
                canvas._paint_intraday(p2, 50, 20, 700, 500)
            finally:
                p2.end()


def test_key_press_events_b_and_t(qapp):
    """验证按键 B 键 (BOLL切换) 与 T 键 (主题切换) 的响应机制"""
    canvas = SBCChartCanvas()
    canvas.show_boll = True
    canvas.set_theme("pitch_dark")

    # 模拟按下 B 键
    ev_b = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(ev_b)
    assert canvas.show_boll is False  # 已切换为 False

    canvas.keyPressEvent(ev_b)
    assert canvas.show_boll is True   # 已切换为 True

    # 模拟按下 T 键
    ev_t = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_T, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(ev_t)
    assert canvas.theme_mode == "deep_navy"  # 已循环切换为 deep_navy

    # 还原
    set_sbc_theme_mode("pitch_dark")
    set_sbc_show_boll(True)
