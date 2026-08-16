# -*- coding: utf-8 -*-
"""
tests/test_intraday_dialog_fix.py — 分时策略窗口关闭与策略编辑器联动专项测试
"""

import sys
import os
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QCloseEvent

# 确保项目根路径
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.ui.intraday_strategy_dialog import PinzhunLadderStandaloneWindow, IntradayStrategyEditDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_intraday_dialog_close_event_no_name_error(qapp):
    """测试分时策略窗口 closeEvent 正常关闭且无 NameError 异常"""
    win = PinzhunLadderStandaloneWindow(code="920199", name="测试标的", parent=None)
    assert win.code == "920199"
    assert bool(win.name)

    # 模拟触发 closeEvent
    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted()


def test_strategy_edit_dialog_strategy_selection(qapp):
    """测试 IntradayStrategyEditDialog 策略联动选择与加载"""
    engine = IntradayStrategyEngine.get_instance()
    
    # 1. 传入策略 A
    dlg_a = IntradayStrategyEditDialog(parent=None, initial_strategy_id="strategy_a_new_stock_batch_sell")
    assert dlg_a.combo_strat.currentData() == "strategy_a_new_stock_batch_sell"
    content_a = dlg_a.txt_json.toPlainText()
    assert "strategy_a_new_stock_batch_sell" in content_a
    assert "策略A" in dlg_a.windowTitle()
    dlg_a.close()

    # 2. 传入代码 688826 (应自动匹配到频准激光)
    dlg_pz = IntradayStrategyEditDialog(parent=None, current_code="688826")
    assert dlg_pz.combo_strat.currentData() == "strategy_pinzhun_laser_688826"
    assert "频准激光" in dlg_pz.windowTitle()
    dlg_pz.close()

    # 3. 切换到全量模式
    dlg_all = IntradayStrategyEditDialog(parent=None)
    all_idx = dlg_all.combo_strat.findData("__ALL__")
    assert all_idx >= 0
    dlg_all.combo_strat.setCurrentIndex(all_idx)
    assert dlg_all._current_selected_mode == "__ALL__"
    assert "全量 JSON 配置" in dlg_all.windowTitle()
    assert "strategies" in dlg_all.txt_json.toPlainText()
    dlg_all.close()


def test_main_window_selected_code_linkage(qapp):
    """测试主窗口 link_stock 与 open_intraday_strategy_dialog 动态关联选中股票与策略"""
    from ats.ui.main_window import ATSMainWindow
    mw = ATSMainWindow()
    
    # 模拟在主界面表格中点击选中 920199
    mw.link_stock("920199", "华岭股份")
    assert mw.current_selected_code == "920199"
    assert mw.current_selected_name == "华岭股份"

    # 调用 open_intraday_strategy_dialog
    mw.open_intraday_strategy_dialog()
    assert mw.ladder_monitor_win is not None
    assert mw.ladder_monitor_win.code == "920199"
    assert mw.ladder_monitor_win.selected_strategy_id == "strategy_a_new_stock_batch_sell"

    # 模拟切换到 300058 (策略 B)
    mw.link_stock("300058", "蓝色光标")
    mw.open_intraday_strategy_dialog()
    assert mw.ladder_monitor_win.code == "300058"
    assert mw.ladder_monitor_win.selected_strategy_id == "strategy_b_new_stock_trend_hold"

    mw.close()
