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

    click_x = canvas.MARGIN_LEFT + 150
    click_y = canvas.MARGIN_TOP + 100

    # 1. 模拟鼠标单击：单击不激活查价线 (避免遮挡视线)
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

    # 操盘手明确要求：悬停/单击绝不弹出查价线
    assert not canvas._crosshair_active, "单击不应激活十字查价线"

    # 2. 模拟鼠标双击：只有双击才激活十字查价线
    dbl_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPointF(click_x, click_y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseDoubleClickEvent(dbl_event)
    assert canvas._crosshair_active, "双击必须激活十字查价线"
    assert canvas._crosshair_idx >= 0

    # 3. 再次双击：退出十字查价线
    canvas.mouseDoubleClickEvent(dbl_event)
    assert not canvas._crosshair_active, "再次双击必须退出十字查价线"
    assert canvas._crosshair_idx == -1

    # 4. 双击再次激活后，测试右键单击一键清除查价线
    canvas.mouseDoubleClickEvent(dbl_event)
    assert canvas._crosshair_active

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


def test_intraday_volume_subchart_modes_and_toggle(sample_intraday_df):
    """测试成交量副图 normal / collapsed / expanded 三种模式"""
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    canvas.set_data(
        sample_intraday_df,
        open_p=35.0,
        vwap_p=35.5,
        high_p=36.8,
        low_p=34.8,
        sell_min=34.0,
        sell_max=37.0,
        signals=[],
        period_mode="1m"
    )

    pix = QPixmap(800, 600)

    # 1. 默认 normal 模式
    assert canvas._vol_mode == "normal"
    painter = QPainter(pix)
    canvas.paintEvent(None)
    painter.end()
    assert canvas._coord_info["vol_h"] > 0
    assert canvas._coord_info["main_h"] < canvas.height() - canvas.MARGIN_TOP - canvas.MARGIN_BOTTOM

    # 2. 切换到折叠模式 collapsed
    canvas.cycle_vol_mode("collapsed")
    assert canvas._vol_mode == "collapsed"
    painter2 = QPainter(pix)
    canvas.paintEvent(None)
    painter2.end()
    assert canvas._coord_info["vol_h"] == 0
    # 折叠后主图占满全高
    assert canvas._coord_info["main_h"] == canvas.height() - canvas.MARGIN_TOP - canvas.MARGIN_BOTTOM

    # 3. 切换到放大模式 expanded
    canvas.cycle_vol_mode("expanded")
    assert canvas._vol_mode == "expanded"
    painter3 = QPainter(pix)
    canvas.paintEvent(None)
    painter3.end()
    assert canvas._coord_info["vol_h"] > canvas._coord_info["main_h"]


def test_double_click_volume_subchart_zoom_and_restore(sample_intraday_df):
    """测试双击副图区域在放大与还原之间快速切换"""
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    canvas.set_data(
        sample_intraday_df,
        open_p=35.0,
        vwap_p=35.5,
        high_p=36.8,
        low_p=34.8,
        sell_min=34.0,
        sell_max=37.0,
        signals=[],
        period_mode="1m"
    )

    # 预渲染一次获取副图位置
    pix = QPixmap(800, 600)
    painter = QPainter(pix)
    canvas.paintEvent(None)
    painter.end()

    vol_top = canvas._coord_info["vol_top"]
    vol_h = canvas._coord_info["vol_h"]
    assert vol_h > 15

    # 双击副图区域：从 normal 放大为 expanded
    dbl_sub = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPointF(250, vol_top + 20),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseDoubleClickEvent(dbl_sub)
    assert canvas._vol_mode == "expanded", "双击成交量副图应切换为 expanded 放大模式"

    # 再次双击副图区域：从 expanded 还原为 normal
    canvas.mouseDoubleClickEvent(dbl_sub)
    assert canvas._vol_mode == "normal", "再次双击成交量副图应还原为 normal 模式"

    # 若当前处于 expanded，双击主图区域也应快速还原为 normal
    canvas.cycle_vol_mode("expanded")
    assert canvas._vol_mode == "expanded"
    dbl_main = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPointF(250, 100),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseDoubleClickEvent(dbl_main)
    assert canvas._vol_mode == "normal", "放大状态下双击主图应快速一键还原 normal"


def test_v_key_and_toolbar_button_interaction(sample_intraday_df):
    """测试 V 快捷键和工具栏按钮循环切换模式与文字样式同步"""
    dlg = SBCIntradayChartDialog(code="688826", initial_period_mode="1m")
    dlg.canvas.set_data(
        sample_intraday_df,
        open_p=35.0,
        vwap_p=35.5,
        high_p=36.8,
        low_p=34.8,
        sell_min=34.0,
        sell_max=37.0,
        signals=[],
        period_mode="1m"
    )
    dlg.resize(800, 600)
    dlg.show()

    assert dlg.canvas._vol_mode == "normal"
    assert "量:开" in dlg.btn_vol_toggle.text()

    # 1. 按 V 键：normal -> collapsed
    event_v = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.NoModifier)
    dlg.keyPressEvent(event_v)
    assert dlg.canvas._vol_mode == "collapsed"
    assert "量:折叠" in dlg.btn_vol_toggle.text()

    # 2. 再次按 V 键：collapsed -> expanded
    dlg.keyPressEvent(event_v)
    assert dlg.canvas._vol_mode == "expanded"
    assert "量:放大" in dlg.btn_vol_toggle.text()

    # 3. 再次按 V 键：expanded -> normal
    dlg.keyPressEvent(event_v)
    assert dlg.canvas._vol_mode == "normal"
    # 4. 点击工具栏按钮触发切换
    dlg.btn_vol_toggle.click()
    assert dlg.canvas._vol_mode == "collapsed"

    dlg.close()


def test_intraday_volume_incremental_split():
    """测试分时图成交量全增量拆分算法：从累加斜坡转换为真实每分钟 Bar 独立量能脉冲"""
    canvas = SBCChartCanvas()

    # 1. 模拟单调递增的全天累计 volume 数据（即用户截图中的斜坡现象）
    cum_volumes = [100.0, 250.0, 420.0, 700.0, 1050.0, 1500.0]
    df_cum = pd.DataFrame({
        "close": [10.0, 10.1, 10.2, 10.15, 10.25, 10.3],
        "volume": cum_volumes,
        "vwap": [10.0, 10.05, 10.1, 10.12, 10.15, 10.2]
    })
    split_vols = canvas._extract_intraday_bar_volumes(df_cum)

    # 校验：拆分后的增量应为 [100, 150, 170, 280, 350, 450]
    expected = [100.0, 150.0, 170.0, 280.0, 350.0, 450.0]
    assert np.allclose(split_vols, expected), f"拆分增量结果异常: {split_vols} != {expected}"

    # 2. 模拟存在底层真实独立当分钟量 'bar_vol' (股)
    bar_vols_shares = [50000.0, 20000.0, 80000.0, 15000.0]  # 股
    df_with_bar_vol = pd.DataFrame({
        "close": [10.0, 10.1, 10.2, 10.3],
        "volume": [500.0, 700.0, 1500.0, 1650.0],
        "bar_vol": bar_vols_shares
    })
    res_vols = canvas._extract_intraday_bar_volumes(df_with_bar_vol)

    # 校验：优先采用 bar_vol 并转换为“手” (除以 100) -> [500, 200, 800, 150]
    expected_hands = [500.0, 200.0, 800.0, 150.0]
    assert np.allclose(res_vols, expected_hands), f"优先使用 bar_vol 转换手失败: {res_vols}"


def test_mouse_left_right_click_anti_misclose_and_ctrl_c(sample_intraday_df):
    """测试鼠标左键点击/双击 + 右键点击防穿透、防误关及 Ctrl+C 安全拦截"""
    dlg = SBCIntradayChartDialog(code="688826", initial_period_mode="1m")
    dlg.canvas.set_data(
        sample_intraday_df,
        open_p=35.0,
        vwap_p=35.5,
        high_p=36.8,
        low_p=34.8,
        sell_min=34.0,
        sell_max=37.0,
        signals=[],
        period_mode="1m"
    )
    dlg.resize(800, 600)
    dlg.show()

    # 预渲染一次
    pix = QPixmap(800, 600)
    dlg.canvas.paintEvent(None)

    # 1. 模拟操盘手先左键双击激活查价
    click_pt = QPointF(200, 200)
    dbl_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        click_pt,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    dlg.canvas.mouseDoubleClickEvent(dbl_event)
    assert dlg.canvas._crosshair_active, "左键双击应激活十字查价"

    # 2. 紧接着鼠标右键按下并松开 (重置视图并退出查价)
    r_press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        click_pt,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    dlg.canvas.mousePressEvent(r_press)
    r_release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        click_pt,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    dlg.canvas.mouseReleaseEvent(r_release)

    # 校验：十字线退出，但窗口绝不关闭！
    assert not dlg.canvas._crosshair_active, "右键点击后十字查价应退出"
    assert not dlg.isHidden(), "右键点击绝不应误关闭窗口"

    # 3. 模拟右键双击：应被严格拦截，绝不向外部冒泡
    r_dbl = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        click_pt,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    dlg.canvas.mouseDoubleClickEvent(r_dbl)
    assert not dlg.isHidden(), "右键双击绝不应误关闭窗口"

    # 4. 模拟右键上下文菜单事件：应被严格消费，绝不向父级冒泡
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtCore import QPoint
    ctx_event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(200, 200))
    dlg.canvas.contextMenuEvent(ctx_event)
    assert ctx_event.isAccepted(), "contextMenuEvent 必须被 canvas 显式消费"

    # 5. 模拟操盘手按 Ctrl+C：在非文本输入状态下应被 dlg 消费，绝不触发外部终端中断
    event_ctrl_c = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier
    )
    dlg.keyPressEvent(event_ctrl_c)
    assert event_ctrl_c.isAccepted(), "非文本状态下 Ctrl+C 必须被消费，防止穿透至控制台误关"
    assert not dlg.isHidden(), "Ctrl+C 绝不应导致窗口关闭"

    dlg.close()


