import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF, QRect
from PyQt6.QtGui import QMouseEvent

# 确保 QApplication 存在
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

def test_global_input_filter_mousemove_bypass():
    """验证 GlobalInputFilter 对 MouseMove 事件直接 O(1) 返回 False，绝不抢占 GIL"""
    from trade_visualizer_qt6 import GlobalInputFilter
    from PyQt6.QtCore import QObject
    
    class DummyWin(QObject):
        pass
    
    win = DummyWin()
    gif = GlobalInputFilter(win)
    
    # 模拟高频 MouseMove 事件
    ev_move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(100.0, 100.0),
        QPointF(100.0, 100.0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    
    # 必须直接返回 False，绝不拦截也不耗费计算
    res = gif.eventFilter(None, ev_move)
    assert res is False, "GlobalInputFilter must return False immediately for MouseMove!"

def test_stock_detail_dialog_hover_timer_throttle():
    """验证 StockDetailDialog hover_timer 在常规状态下保持停止，仅在贴边时激活"""
    from ats.ui.main_window import StockDetailDialog
    
    dlg = StockDetailDialog("600519", "贵州茅台", None)
    
    # 1. 初始状态：未贴边，hover_timer 必须是停止状态（0 开销）
    assert hasattr(dlg, 'hover_timer')
    assert dlg.hover_timer.isActive() is False, "hover_timer should be stopped by default!"
    
    # 2. 调用 _check_hover，由于未贴边，定时器应继续保持停止
    dlg._check_hover()
    assert dlg.hover_timer.isActive() is False
    
    # 3. 模拟进入贴边状态
    dlg.anchor_edge = "right"
    dlg.normal_geometry = QRect(100, 100, 400, 500)
    dlg.hover_timer.start()
    assert dlg.hover_timer.isActive() is True
    
    # 4. 模拟隐藏事件 (hideEvent)，必须彻底停止定时器
    from PyQt6.QtGui import QHideEvent
    dlg.hideEvent(QHideEvent())
    assert dlg.hover_timer.isActive() is False, "hover_timer should stop on hideEvent!"
    
    dlg.close()

def test_chart_widgets_detail_dialog_hover_timer_throttle():
    """验证 DistributionDetailsDialog hover_timer 默认停止与贴边启停"""
    from ats.ui.chart_widgets import DistributionDetailsDialog
    
    dlg = DistributionDetailsDialog(None)
    
    # 初始默认停止
    assert hasattr(dlg, 'hover_timer')
    assert dlg.hover_timer.isActive() is False
    
    # 离开边缘未贴边时自动停止
    dlg.anchor_edge = None
    dlg.is_hidden_state = False
    dlg.hover_timer.start()
    dlg._check_hover()
    assert dlg.hover_timer.isActive() is False
    
    # hideEvent 停止
    from PyQt6.QtGui import QHideEvent
    dlg.hover_timer.start()
    dlg.hideEvent(QHideEvent())
    assert dlg.hover_timer.isActive() is False
    
    dlg.close()

def test_dragon_monitor_dialog_hover_timer_throttle():
    """验证 DragonLeaderMonitorDialog hover_timer 默认停止与贴边启停"""
    from ats.ui.dragon_monitor import DragonLeaderMonitorDialog
    
    dlg = DragonLeaderMonitorDialog(None)
    
    # 初始默认停止
    assert hasattr(dlg, 'hover_timer')
    assert dlg.hover_timer.isActive() is False
    
    # 离开边缘未贴边时自动停止
    dlg.anchor_edge = None
    dlg.is_hidden_state = False
    dlg.hover_timer.start()
    dlg._check_hover()
    assert dlg.hover_timer.isActive() is False
    
    dlg.close()

def test_daily_limit_up_dialog_hover_timer_throttle():
    """验证 DailyLimitUpDialog hover_timer 默认停止与贴边启停"""
    from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog
    
    dlg = DailyLimitUpDialog(None)
    
    # 初始默认停止
    assert hasattr(dlg, 'hover_timer')
    assert dlg.hover_timer.isActive() is False
    
    # 离开边缘未贴边时自动停止
    dlg.anchor_edge = None
    dlg.is_hidden_state = False
    dlg.hover_timer.start()
    dlg._check_hover()
    assert dlg.hover_timer.isActive() is False
    
    dlg.close()

def test_hot_sector_dialog_hover_timer_throttle():
    """验证 HotSectorLeaderboardDialog hover_timer 默认停止与贴边启停"""
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
    
    dlg = HotSectorLeaderboardDialog(None)
    
    # 初始默认停止
    assert hasattr(dlg, 'hover_timer')
    assert dlg.hover_timer.isActive() is False
    
    # 离开边缘未贴边时自动停止
    dlg.anchor_edge = None
    dlg.is_hidden_state = False
    dlg.hover_timer.start()
    dlg._check_hover()
    assert dlg.hover_timer.isActive() is False
    
    dlg.close()
