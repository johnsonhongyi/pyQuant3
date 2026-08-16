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
    
    # 模拟在主界面表格中点击选中普通个股 300862 (蓝盾光电)
    mw.link_stock("300862", "蓝盾光电")
    assert mw.current_selected_code == "300862"
    assert mw.current_selected_name == "蓝盾光电"

    # 调用 open_intraday_strategy_dialog，应自动路由到通用日常分时阶梯策略
    mw.open_intraday_strategy_dialog()
    assert mw.ladder_monitor_win is not None
    assert mw.ladder_monitor_win.code == "300862"
    assert mw.ladder_monitor_win.selected_strategy_id == "strategy_c_daily_surge_ladder"

    # 模拟切换到 688826 (频准激光专属策略)
    mw.link_stock("688826", "频准激光")
    mw.open_intraday_strategy_dialog()
    assert mw.ladder_monitor_win.code == "688826"
    assert mw.ladder_monitor_win.selected_strategy_id == "strategy_pinzhun_laser_688826"

    # 验证在切到 688826 后，标的下拉列表中依然保留了 300862，用户随时可以选回
    combo = mw.ladder_monitor_win.combo_code
    idx_300862 = combo.findData("300862")
    assert idx_300862 >= 0

    # 模拟用户在下拉框再次选择 300862
    combo.setCurrentIndex(idx_300862)
    assert mw.ladder_monitor_win.code == "300862"
    assert mw.ladder_monitor_win.selected_strategy_id == "strategy_c_daily_surge_ladder"

    mw.close()


def test_strategy_edit_dialog_new_clone_delete(qapp):
    """测试策略编辑器新建、复制、删除策略功能"""
    dlg = IntradayStrategyEditDialog(parent=None)
    init_count = len(dlg._full_config_data.get("strategies", []))

    # 1. 测试新建策略
    dlg._on_create_new_strategy()
    assert len(dlg._full_config_data.get("strategies", [])) == init_count + 1
    new_strat_id = dlg.combo_strat.currentData()
    assert "strategy_custom" in new_strat_id

    # 2. 测试复制策略
    dlg._on_clone_current_strategy()
    assert len(dlg._full_config_data.get("strategies", [])) == init_count + 2
    cloned_id = dlg.combo_strat.currentData()
    assert "_copy_" in cloned_id

    dlg.close()


def test_daily_common_strategy_trigger_expr():
    """测试通用日常个股分时策略：早盘冲高卖出与10点冲高回落破分时均线减仓"""
    engine = IntradayStrategyEngine.get_instance()
    engine.load_config()

    daily_strat = next((s for s in engine.strategies if s.get("id") == "strategy_c_daily_surge_ladder"), None)
    assert daily_strat is not None

    code = "000001"
    open_p = 10.0
    engine.rule_state_map.clear()

    # 1. 09:35 价格冲高到 10.35 (涨 3.5%)，触发冲高≥3%卖出 30%
    tick_1 = {"trade": 10.35, "close": 10.35, "vwap": 10.20, "turnover": 1.2}
    sigs_1 = engine.evaluate_tick(code, tick_1, open_p, "09:35:00", strategy=daily_strat)
    assert len(sigs_1) == 1
    assert "冲高涨幅≥3%" in sigs_1[0].rule_name
    assert sigs_1[0].sell_ratio == 0.3

    # 2. 09:55 价格回落到 10.10，跌破分时均线 (vwap=10.25)，触发10点冲高回落破均线卖出 30%
    tick_2 = {"trade": 10.10, "close": 10.10, "vwap": 10.25, "turnover": 2.5}
    sigs_2 = engine.evaluate_tick(code, tick_2, open_p, "09:55:00", strategy=daily_strat)
    assert len(sigs_2) == 1
    assert "冲高回落破分时均线" in sigs_2[0].rule_name
    assert sigs_2[0].sell_ratio == 0.3

    # 3. 14:52 尾盘清仓
    tick_3 = {"trade": 10.05, "close": 10.05, "vwap": 10.15, "turnover": 4.0}
    sigs_3 = engine.evaluate_tick(code, tick_3, open_p, "14:52:00", strategy=daily_strat)
    assert len(sigs_3) == 1
    assert "尾盘市价清仓" in sigs_3[0].rule_name
    assert sigs_3[0].sell_ratio == 1.0

