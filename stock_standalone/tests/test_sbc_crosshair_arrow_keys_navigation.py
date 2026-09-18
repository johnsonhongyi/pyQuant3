# -*- coding: utf-8 -*-
"""
tests/test_sbc_crosshair_arrow_keys_navigation.py
测试 SBC 走势图左右方向键移动查价、鼠标点击锁定、Esc 退出查价以及当时情况数据 HUD 呈现
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_CUR_DIR)
_STANDALONE_DIR = os.path.join(_PROJ_ROOT, "stock_standalone")

for p in [_STANDALONE_DIR, _PROJ_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QPainter, QPixmap

app = QApplication.instance() or QApplication(sys.argv)

from ats.ui.intraday_strategy_dialog import SBCChartCanvas, SBCIntradayChartDialog


@pytest.fixture
def sample_kline_df():
    """构造示例 60M K 线数据"""
    dates = pd.date_range("2026-09-18 09:30", periods=30, freq="60min")
    df = pd.DataFrame({
        "open": np.linspace(35.0, 38.0, 30),
        "high": np.linspace(35.5, 38.8, 30),
        "low": np.linspace(34.8, 37.5, 30),
        "close": np.linspace(35.2, 38.5, 30),
        "vol": np.linspace(10000, 50000, 30),
        "ch_upper": np.linspace(36.0, 39.0, 30),
        "ch_mid": np.linspace(35.0, 38.0, 30),
        "ch_lower": np.linspace(34.0, 37.0, 30),
    }, index=dates)
    return df


@pytest.fixture
def sample_intraday_df():
    """构造示例 1M 分时数据"""
    times = pd.date_range("2026-09-18 09:30", periods=50, freq="1min").strftime("%H:%M")
    df = pd.DataFrame({
        "close": np.linspace(35.0, 36.5, 50),
        "vwap": np.linspace(35.0, 36.0, 50),
        "vol": np.linspace(100, 500, 50),
    }, index=times)
    return df


def test_crosshair_arrow_keys_navigation(sample_kline_df):
    """测试左右方向键移动查价十字线及跨屏平移"""
    canvas = SBCChartCanvas()
    canvas.set_kline_data(sample_kline_df, open_p=35.0, period_mode="60m")
    canvas.resize(800, 600)

    # 初始状态未激活查价线
    assert not canvas._crosshair_active
    assert canvas._crosshair_idx == -1

    # 按右键首次激活：定位到最新一根（总共 30 根，索引 29）
    canvas.move_crosshair(1)
    assert canvas._crosshair_active
    assert canvas._crosshair_idx == 29

    # 按左键向左移动一根：索引变为 28
    canvas.move_crosshair(-1)
    assert canvas._crosshair_idx == 28

    # 连续按左键移动
    canvas.move_crosshair(-1)
    assert canvas._crosshair_idx == 27

    # 测试局部缩放时的跨屏边界自动平移
    canvas._zoom_start_idx = 10
    canvas._zoom_end_idx = 20
    canvas._crosshair_idx = 0  # 停在可视区第 0 根（对应全局第 10 根）

    # 向左越界：应自动将可视窗口向左推一格
    canvas.move_crosshair(-1)
    assert canvas._zoom_start_idx == 9
    assert canvas._zoom_end_idx == 19
    assert canvas._crosshair_idx == 0

    # 测试 Esc 退出查价线
    event_esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(event_esc)
    assert not canvas._crosshair_active


def test_mouse_click_locks_crosshair(sample_kline_df):
    """测试鼠标点击 K 线图锁定十字查价线"""
    canvas = SBCChartCanvas()
    canvas.set_kline_data(sample_kline_df, open_p=35.0, period_mode="60m")
    canvas.resize(800, 600)

    # 预渲染一次以初始化 _coord_info
    pix = QPixmap(800, 600)
    painter = QPainter(pix)
    canvas.paintEvent(None)
    painter.end()

    assert canvas._coord_info.get("ready")

    # 模拟鼠标按下和松开在同一个位置 (单击未拖拽)
    click_x = canvas.MARGIN_LEFT + 150
    click_y = canvas.MARGIN_TOP + 100

    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(click_x, click_y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mousePressEvent(press_event)

    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(click_x, click_y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseReleaseEvent(release_event)

    # 单击后应当激活查价线并选中有效 Bar
    assert canvas._crosshair_active
    assert canvas._crosshair_idx >= 0

    # 右键单击应清除查价线并重置
    r_press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(click_x, click_y),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mousePressEvent(r_press)

    r_release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(click_x, click_y),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseReleaseEvent(r_release)

    assert not canvas._crosshair_active
    assert canvas._crosshair_idx == -1


def test_hud_data_rendering_kline_and_intraday(sample_kline_df, sample_intraday_df):
    """测试 K 线与分时模式下 HUD 当时数据看板绘制不崩溃且内容完备"""
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    pix = QPixmap(800, 600)

    # 1. 测试 K 线模式 HUD 渲染
    canvas.set_kline_data(sample_kline_df, open_p=35.0, period_mode="60m")
    canvas.move_crosshair(1) # 激活十字查价
    assert canvas._crosshair_active

    painter = QPainter(pix)
    # paintEvent 内部会绘制 HUD 看板
    canvas.paintEvent(None)
    painter.end()

    # 2. 测试分时模式 HUD 渲染
    canvas.set_data(
        sample_intraday_df,
        open_p=35.0,
        vwap_p=35.5,
        high_p=36.5,
        low_p=34.8,
        sell_min=34.0,
        sell_max=37.0,
        signals=[],
        period_mode="1m"
    )
    canvas.move_crosshair(1) # 激活十字查价
    assert canvas._crosshair_active

    painter2 = QPainter(pix)
    canvas.paintEvent(None)
    painter2.end()


def test_dialog_left_right_keys_and_a_d_decoupling(sample_kline_df):
    """测试主窗口下左右键移动查价，A/D 键轮转周期"""
    dlg = SBCIntradayChartDialog(code="920038", initial_period_mode="60m")
    dlg.canvas.set_kline_data(sample_kline_df, open_p=35.0, period_mode="60m")
    dlg.resize(800, 600)
    dlg.show()

    # 1. 测试按 Left / Right 键：转调 canvas.move_crosshair，而不是轮转周期
    init_mode = dlg._current_period_mode
    event_right = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    dlg.keyPressEvent(event_right)

    # 周期保持不变
    assert dlg._current_period_mode == init_mode
    # canvas 十字查价线被激活并移动
    assert dlg.canvas._crosshair_active

    # 2. 测试按 A 键：轮转上一周期
    event_a = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
    dlg.keyPressEvent(event_a)
    assert dlg._current_period_mode != init_mode

    # 3. 再次按 Right 键激活查价线，测试按 Esc 键：优先退出十字查价线
    dlg.keyPressEvent(event_right)
    assert dlg.canvas._crosshair_active
    event_esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    dlg.keyPressEvent(event_esc)
    assert not dlg.canvas._crosshair_active
    # 窗口依然正常展示未被关闭
    assert not dlg.isHidden()

    dlg.close()
