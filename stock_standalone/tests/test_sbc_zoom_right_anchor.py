# -*- coding: utf-8 -*-
"""
tests/test_sbc_zoom_right_anchor.py
验证 SBC 走势图全周期 (1日/3日/5日/10日分时, 30分/60分K线, 日K/周K/月K) 通达信经典缩放逻辑与右侧最新行情数据/现价始终锚定保持机制
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_CUR_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QWheelEvent
from ats.ui.intraday_strategy_dialog import SBCChartCanvas, SBCIntradayChartDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _create_mock_intraday_df(n_bars: int = 100) -> pd.DataFrame:
    """生成具有连续分钟索引与价格的测试 DataFrame"""
    times = [f"2026-09-24 09:{i:02d}:00" if i < 60 else f"2026-09-24 10:{i-60:02d}:00" for i in range(n_bars)]
    prices = 10.0 + np.cumsum(np.random.normal(0, 0.05, n_bars))
    df = pd.DataFrame({
        "time": times,
        "open": prices - 0.02,
        "high": prices + 0.05,
        "low": prices - 0.05,
        "close": prices,
        "vol": np.random.randint(100, 1000, n_bars),
        "volume": np.cumsum(np.random.randint(100, 1000, n_bars)),
        "vwap": prices - 0.01,
        "amount": prices * 1000,
    })
    df.set_index("time", inplace=True)
    return df


def test_zoom_right_anchor_on_all_periods(qapp):
    """
    1. 验证 1日/3日/5日分时与 30分/60分/日K 全周期缩放：
       无论放大还是缩小，可视切片最右侧 end_i 必须永远等于 total_n - 1，
       最右侧最新行情数据和现价始终锚定保持！
    """
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    
    test_periods = ["1m", "3d", "5d", "10d", "30m", "60m", "day", "week"]
    
    for period in test_periods:
        total_bars = 120
        df = _create_mock_intraday_df(total_bars)
        
        if period in ["5m", "15m", "30m", "60m", "day", "week"]:
            canvas.set_kline_data(df, open_p=10.0, vwap_p=10.0, period_mode=period)
        else:
            canvas.set_data(df, open_p=10.0, vwap_p=10.0, period_mode=period)
            
        # 初始未缩放状态：默认全景，末尾必须是最后一根
        df_view, s_i, e_i = canvas._get_visible_slice()
        assert e_i == total_bars - 1, f"[{period}] 初始末尾索引必须为 total_n - 1"
        assert s_i == 0, f"[{period}] 初始起始索引必须为 0"
        assert len(df_view) == total_bars
        assert canvas._is_right_anchored is True
        
        # 放大 (zoom_in)：减少可视数量，最右侧最新数据必须牢牢固定
        canvas.zoom_in(factor=0.8)
        df_view, s_i, e_i = canvas._get_visible_slice()
        assert e_i == total_bars - 1, f"[{period}] 放大后末尾索引必须始终为 total_n - 1"
        assert s_i > 0, f"[{period}] 放大后起始索引必须大于 0"
        assert len(df_view) < total_bars, f"[{period}] 放大后可视 Bar 数量必须缩减"
        assert canvas._is_right_anchored is True
        
        # 再次放大
        cur_vis = len(df_view)
        canvas.zoom_in(factor=0.8)
        df_view2, s_i2, e_i2 = canvas._get_visible_slice()
        assert e_i2 == total_bars - 1, f"[{period}] 二次放大后末尾索引必须始终为 total_n - 1"
        assert len(df_view2) < cur_vis, f"[{period}] 二次放大后可视 Bar 数量应进一步缩减"
        
        # 缩小 (zoom_out)：增加可视数量，最右侧最新数据依然牢牢固定
        canvas.zoom_out(factor=1.25)
        df_view3, s_i3, e_i3 = canvas._get_visible_slice()
        assert e_i3 == total_bars - 1, f"[{period}] 缩小后末尾索引必须始终为 total_n - 1"
        assert len(df_view3) > len(df_view2), f"[{period}] 缩小后可视 Bar 数量必须增加"
        assert canvas._is_right_anchored is True


def test_realtime_data_append_viewport_sliding(qapp):
    """
    2. 验证盘中新行情推送（追加新 Bar 时）：
       在缩放状态下，视口自动顺延滑动，最新追加的 Bar 永远出现在可视切片末尾，最新价格绝不丢失！
    """
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    
    # 初始 100 根数据
    df100 = _create_mock_intraday_df(100)
    canvas.set_data(df100, open_p=10.0, vwap_p=10.0, period_mode="1m")
    
    # 用户按 Up 放大，锁定最近 40 根
    canvas.zoom_in(factor=0.4)
    df_view1, s1, e1 = canvas._get_visible_slice()
    assert e1 == 99
    assert len(df_view1) <= 42
    latest_time_1 = df_view1.index[-1]
    assert latest_time_1 == df100.index[-1]
    
    # 盘中实时追加 5 根新分钟 Bar (total_n 变为 105)
    df105 = _create_mock_intraday_df(105)
    canvas.set_data(df105, open_p=10.0, vwap_p=10.0, period_mode="1m")
    
    # 核心检验：视口自动推进，end_i 必须自动变成 104，包含最新的第 105 根！
    df_view2, s2, e2 = canvas._get_visible_slice()
    assert e2 == 104, "盘中追加新 Bar 后，end_i 必须自动顺延至最新的 104"
    assert s2 > s1, "起始索引必须相应向右顺延，保持视口窗口跨度稳定"
    assert df_view2.index[-1] == df105.index[-1], "可视切片末尾时间必须是最新到达的时间点"


def test_zoom_out_to_full_view_auto_recovery(qapp):
    """
    3. 验证连续缩小直到超过全量数据时，自动恢复全景模式 (_visible_bar_count is None)
    """
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    df = _create_mock_intraday_df(50)
    canvas.set_data(df, open_p=10.0, vwap_p=10.0, period_mode="3d")
    
    canvas.zoom_in(factor=0.5)
    assert canvas._visible_bar_count is not None
    assert canvas._is_zoomed() is True
    
    # 连续执行多次缩小
    for _ in range(10):
        canvas.zoom_out(factor=1.5)
        
    df_view, s, e = canvas._get_visible_slice()
    assert s == 0
    assert e == 49
    assert canvas._visible_bar_count is None, "超出全量数据后应恢复为 None (全景)"
    assert canvas._is_zoomed() is False


def test_mouse_wheel_event_zoom(qapp):
    """
    4. 验证鼠标滚轮事件 (wheelEvent)：
       向前滚 (angleDelta > 0) 触发放大；
       向后滚 (angleDelta < 0) 触发缩小；
    """
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    df = _create_mock_intraday_df(80)
    canvas.set_data(df, open_p=10.0, vwap_p=10.0, period_mode="5m")
    
    init_view, s0, e0 = canvas._get_visible_slice()
    init_count = len(init_view)
    assert init_count == 80
    
    # 模拟滚轮向前推 (向上滚 120 单位) -> 放大
    wheel_up = QWheelEvent(
        QPointF(400, 300),
        QPointF(400, 300),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False
    )
    canvas.wheelEvent(wheel_up)
    
    view_after_up, s_up, e_up = canvas._get_visible_slice()
    assert len(view_after_up) < init_count, "滚轮向前推必须减少可视 Bar 数量 (放大)"
    assert e_up == 79, "滚轮放大时末尾必须牢牢吸附在最新一根"
    
    # 模拟滚轮向后拉 (向下滚 -120 单位) -> 缩小
    wheel_down = QWheelEvent(
        QPointF(400, 300),
        QPointF(400, 300),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False
    )
    canvas.wheelEvent(wheel_down)
    
    view_after_down, s_dn, e_dn = canvas._get_visible_slice()
    assert len(view_after_down) > len(view_after_up), "滚轮向后拉必须增加可视 Bar 数量 (缩小)"
    assert e_dn == 79, "滚轮缩小时末尾必须牢牢吸附在最新一根"


def test_panning_and_reset_view(qapp):
    """
    5. 验证鼠标向左拖动查看历史脱离锚定，重置 (reset_view) 重新恢复右侧吸附
    """
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    df = _create_mock_intraday_df(100)
    canvas.set_data(df, open_p=10.0, vwap_p=10.0, period_mode="day")
    
    # 用户拖拽查看历史：end_i 变为 60 (< 99)
    canvas._is_right_anchored = False
    canvas._zoom_start_idx = 20
    canvas._zoom_end_idx = 60
    
    df_view, s, e = canvas._get_visible_slice()
    assert s == 20
    assert e == 60
    assert canvas._is_right_anchored is False
    
    # 按 0 键或右键短按触发 reset_view
    canvas.reset_view()
    df_view_reset, s_r, e_r = canvas._get_visible_slice()
    assert s_r == 0
    assert e_r == 99
    assert canvas._is_right_anchored is True, "reset_view 必须恢复右侧最新吸附"
    assert canvas._visible_bar_count is None

def test_paint_rendering_with_zoom(qapp):
    """
    6. 验证在 1m 分时与 30m/60m/day K 线在缩放状态下 QPainter 完整渲染流程，
       验证最新现价水平虚线与右轴价格胶囊正常绘制无异常
    """
    from PyQt6.QtGui import QImage, QPainter
    
    canvas = SBCChartCanvas()
    canvas.resize(800, 600)
    
    for period in ["1m", "3d", "5d", "30m", "60m", "day"]:
        df = _create_mock_intraday_df(80)
        if period in ["30m", "60m", "day"]:
            canvas.set_kline_data(df, open_p=10.0, vwap_p=10.0, period_mode=period)
        else:
            canvas.set_data(df, open_p=10.0, vwap_p=10.0, period_mode=period)
            
        # 缩放至局部视野
        canvas.zoom_in(factor=0.6)
        
        # 创建离屏画板触发 paintEvent
        img = QImage(800, 600, QImage.Format.Format_ARGB32)
        painter = QPainter(img)
        try:
            margin_left = canvas.MARGIN_LEFT
            margin_top = canvas.MARGIN_TOP
            chart_w = 800 - margin_left - canvas.MARGIN_RIGHT
            chart_h = 600 - margin_top - canvas.MARGIN_BOTTOM
            
            if period in ["30m", "60m", "day"]:
                canvas._paint_kline(painter, margin_left, margin_top, chart_w, chart_h)
            else:
                canvas._paint_intraday(painter, margin_left, margin_top, chart_w, chart_h)
        finally:
            painter.end()
            
        c_info = canvas._coord_info
        assert c_info.get("ready") is True, f"[{period}] 绘制后 coord_info 必须为 ready"
        assert c_info.get("max_p") >= c_info.get("min_p")


def test_dialog_event_filter_wheel(qapp):
    """
    7. 验证 SBCIntradayChartDialog.eventFilter 对 Wheel 滚轮事件的拦截与转派：
       在窗口任意位置滚动滚轮，均能触发底层 canvas 缩放且保持最右侧最新数据
    """
    dialog = SBCIntradayChartDialog(code="688826", initial_period_mode="1m")
    dialog.async_load_enabled = False
    dialog.resize(900, 700)
    
    df = _create_mock_intraday_df(60)
    dialog.canvas.set_data(df, open_p=10.0, vwap_p=10.0, period_mode="1m")
    
    init_view, _, _ = dialog.canvas._get_visible_slice()
    assert len(init_view) == 60
    
    # 模拟在对话框上滚动滚轮向前推 (放大)
    wheel_up = QWheelEvent(
        QPointF(200, 200),
        QPointF(200, 200),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False
    )
    handled = dialog.eventFilter(dialog, wheel_up)
    assert handled is True, "eventFilter 必须消费并处理 Wheel 事件"
    
    view_after_up, _, e_up = dialog.canvas._get_visible_slice()
    assert len(view_after_up) < 60, "滚轮转发必须成功触发放大"
    assert e_up == 59, "末尾索引必须牢牢保持在最新"
    
    dialog.close()


def test_alt_zoom_sync_all_open_sbc_windows(qapp):
    """
    8. 验证按住 Alt 缩放时 (Alt+Up / Alt+Down / Alt+滚轮)，
       同步当前所有已打开的同组 SBC 窗口缩放视图，且每个窗口最右侧最新数据始终锚定保持！
    """
    from ats.ui.intraday_strategy_dialog import sync_all_open_sbc_zoom, SBCWindowMemoryManager
    
    mgr = SBCWindowMemoryManager.get_instance()
    
    dlg1 = SBCIntradayChartDialog(code="688826", initial_period_mode="1m")
    dlg2 = SBCIntradayChartDialog(code="600000", initial_period_mode="3d")
    dlg3 = SBCIntradayChartDialog(code="000001", initial_period_mode="day")
    
    dlg1.async_load_enabled = False
    dlg2.async_load_enabled = False
    dlg3.async_load_enabled = False
    
    # 给各窗口注入测试数据
    dlg1.canvas.set_data(_create_mock_intraday_df(100), open_p=10.0, vwap_p=10.0, period_mode="1m")
    dlg2.canvas.set_data(_create_mock_intraday_df(150), open_p=10.0, vwap_p=10.0, period_mode="3d")
    dlg3.canvas.set_kline_data(_create_mock_intraday_df(80), open_p=10.0, vwap_p=10.0, period_mode="day")
    
    # 注册到内存管理器
    mgr.register(dlg1)
    mgr.register(dlg2)
    mgr.register(dlg3)
    
    try:
        # 在 dlg1 上触发 Alt+放大 (sync_all_open_sbc_zoom in_=True)
        count = sync_all_open_sbc_zoom(in_=True, factor=0.5, trigger_dlg=dlg1)
        assert count >= 3, "必须同步全部 3 个已打开窗口"
        
        target_vis = dlg1.canvas._visible_bar_count
        assert target_vis is not None, "触发窗口缩放后可视条数应被设定"
        assert target_vis <= 52, "0.5 倍缩放后条数应明显缩减"
        
        # 验证所有 3 个窗口的可视 Bar 数量与右侧锚定全部精准对齐
        for dlg in (dlg1, dlg2, dlg3):
            cv = dlg.canvas
            assert cv._visible_bar_count == target_vis, f"[{dlg.code}] 可视条数必须与触发窗严格一致"
            assert cv._is_right_anchored is True, f"[{dlg.code}] 必须处于右侧锚定状态"
            _, _, e_i = cv._get_visible_slice()
            assert e_i == len(cv.df_intraday) - 1, f"[{dlg.code}] 最右侧必须始终是最新一根 Bar"
            
        # 再次触发 Alt+缩小 直至恢复全景
        for _ in range(5):
            sync_all_open_sbc_zoom(in_=False, factor=1.5, trigger_dlg=dlg1)
            
        assert dlg1.canvas._visible_bar_count is None, "放大后连续缩小应恢复全景"
        for dlg in (dlg1, dlg2, dlg3):
            cv = dlg.canvas
            assert cv._visible_bar_count is None, f"[{dlg.code}] 恢复全景后应全量对齐为 None"
            assert cv._is_right_anchored is True
            _, _, e_i = cv._get_visible_slice()
            assert e_i == len(cv.df_intraday) - 1
    finally:
        dlg1.close()
        dlg2.close()
        dlg3.close()


def test_is_alt_modifier_active_three_tiers(qapp, monkeypatch):
    """
    9. 验证 is_alt_modifier_active 的三层严密判定：
       - 第 1 层：event 自带 AltModifier
       - 第 2 层：QApplication 全局 AltModifier
       - 第 3 层：Windows 原生硬件 GetAsyncKeyState(0x12) & 0x8000 穿透
    """
    from ats.ui.intraday_strategy_dialog import is_alt_modifier_active
    from unittest.mock import MagicMock
    import sys

    # 1. 纯无修饰符事件
    dummy_event_no_mod = MagicMock()
    dummy_event_no_mod.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    assert is_alt_modifier_active(dummy_event_no_mod) is False

    # 2. 事件自身带有 AltModifier
    dummy_event_alt = MagicMock()
    dummy_event_alt.modifiers.return_value = Qt.KeyboardModifier.AltModifier
    assert is_alt_modifier_active(dummy_event_alt) is True

    # 3. 模拟 Windows 现场：Qt 事件丢失 Alt (NoModifier)，但底层硬件 GetAsyncKeyState 检测到 Alt 处于按下状态
    if sys.platform == "win32":
        import ctypes
        try:
            # Mock VK_MENU (0x12) 返回 0x8000
            def mock_get_async_key_state(vk):
                if vk in (0x12, 0xA4, 0xA5):
                    return 0x8000
                return 0
            monkeypatch.setattr(ctypes.windll.user32, "GetAsyncKeyState", mock_get_async_key_state)
            
            # 即使 event.modifiers() 完全为 NoModifier，也必须穿透判定为 True！
            assert is_alt_modifier_active(dummy_event_no_mod) is True
        finally:
            monkeypatch.undo()


def test_wheel_event_with_alt_and_win32_physical_sync(qapp, monkeypatch):
    """
    10. 验证鼠标滚轮在 Alt 按下时 (分别测试 Qt 修饰符路径 与 Win32 硬件穿透路径)
        在 eventFilter 拦截时 100% 触发同组所有 SBC 窗口毫秒级同步缩放！
    """
    from ats.ui.intraday_strategy_dialog import SBCWindowMemoryManager, is_alt_modifier_active
    import sys
    
    mgr = SBCWindowMemoryManager.get_instance()
    dlg1 = SBCIntradayChartDialog(code="688826", initial_period_mode="1m")
    dlg2 = SBCIntradayChartDialog(code="600000", initial_period_mode="3d")
    dlg1.async_load_enabled = False
    dlg2.async_load_enabled = False
    
    dlg1.canvas.set_data(_create_mock_intraday_df(100), open_p=10.0, vwap_p=10.0, period_mode="1m")
    dlg2.canvas.set_data(_create_mock_intraday_df(100), open_p=10.0, vwap_p=10.0, period_mode="3d")
    
    mgr.register(dlg1)
    mgr.register(dlg2)
    
    try:
        # A. 路径 1: Qt 事件自带 AltModifier 滚轮向前推 (放大)
        wheel_alt_up = QWheelEvent(
            QPointF(200, 200),
            QPointF(200, 200),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.AltModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False
        )
        handled = dlg1.eventFilter(dlg1, wheel_alt_up)
        assert handled is True
        
        target_vis_1 = dlg1.canvas._visible_bar_count
        assert target_vis_1 is not None and target_vis_1 < 100
        # 验证同组的 dlg2 也被毫秒级同步缩放！
        assert dlg2.canvas._visible_bar_count == target_vis_1
        assert dlg2.canvas._is_right_anchored is True

        # B. 路径 2: 模拟 Windows 原生缺陷现场——滚轮事件完全没有 AltModifier (NoModifier)，
        # 但是操盘手手指正物理按在键盘 Alt 键上 (GetAsyncKeyState 触发)
        if sys.platform == "win32":
            import ctypes
            def mock_get_async_key_state(vk):
                if vk in (0x12, 0xA4, 0xA5):
                    return 0x8000
                return 0
            monkeypatch.setattr(ctypes.windll.user32, "GetAsyncKeyState", mock_get_async_key_state)

            wheel_physical_alt_up = QWheelEvent(
                QPointF(200, 200),
                QPointF(200, 200),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,  # 模拟 Windows 滚轮丢修饰符
                Qt.ScrollPhase.NoScrollPhase,
                False
            )
            handled = dlg1.eventFilter(dlg1, wheel_physical_alt_up)
            assert handled is True

            target_vis_2 = dlg1.canvas._visible_bar_count
            assert target_vis_2 < target_vis_1, "二次放大条数应进一步缩减"
            # 核心验证：同组的 dlg2 同样被同步缩放！
            assert dlg2.canvas._visible_bar_count == target_vis_2
            assert dlg2.canvas._is_right_anchored is True

        # C. 路径 3: 水平滚轮兼容性测试 (部分鼠标驱动按 Alt+滚轮生成 horizontal delta x)
        wheel_horizontal = QWheelEvent(
            QPointF(200, 200),
            QPointF(200, 200),
            QPoint(0, 0),
            QPoint(120, 0),  # x 有值, y 为 0
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.AltModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False
        )
        handled = dlg1.eventFilter(dlg1, wheel_horizontal)
        assert handled is True
        target_vis_3 = dlg1.canvas._visible_bar_count
        assert target_vis_3 < target_vis_2, "水平滚轮也能正常触发放大"
        assert dlg2.canvas._visible_bar_count == target_vis_3

    finally:
        dlg1.close()
        dlg2.close()

