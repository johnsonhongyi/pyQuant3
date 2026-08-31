# -*- coding: utf-8 -*-
"""
tests/test_snap_windows_top_hotkey.py
Comprehensive automated test suite for ATS snap windows and standalone monitor dialogs
verifying QShortcut 'T' toggling stays-on-top, input guard, and TDX dormant cooling mechanism.
"""

import sys
import os
import pytest
import pandas as pd
from PyQt6.QtWidgets import QApplication, QLineEdit, QTextEdit, QTableWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent

# Ensure stock_standalone is in path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def trigger_shortcut_or_key(widget):
    """Trigger QShortcut or keyPressEvent directly on widget"""
    if hasattr(widget, '_top_shortcut_t') and widget._top_shortcut_t:
        widget._top_shortcut_t.activated.emit()
    else:
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_T, Qt.KeyboardModifier.NoModifier, "t")
        widget.keyPressEvent(event)


def test_is_editing_text_helper(qapp):
    """1. Test is_editing_text utility under various focus conditions"""
    from ats.ui.styles import is_editing_text
    from PyQt6.QtWidgets import QWidget, QLabel

    w = QWidget()
    edit = QLineEdit(w)
    lbl = QLabel("Test", w)
    w.show()
    w.activateWindow()
    qapp.processEvents()

    # When no text edit is focused
    lbl.setFocus()
    qapp.processEvents()
    assert is_editing_text(w) is False

    # When QLineEdit is focused
    edit.setFocus()
    qapp.processEvents()
    assert is_editing_text(w) is True

    w.close()


def test_daily_limit_up_dialog_top_hotkey(qapp):
    """2. Test DailyLimitUpDialog T hotkey toggles stays_on_top even when table is focused"""
    from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog

    dialog = DailyLimitUpDialog(restore_state={})
    dialog.show()
    dialog.activateWindow()
    dialog.table.setFocus()
    qapp.processEvents()
    assert hasattr(dialog, 'chk_ontop')
    assert "置顶" in dialog.chk_ontop.text()

    # Initial state
    init_state = dialog.stays_on_top

    # Press T -> Toggle via QShortcut
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == (not init_state)
    assert dialog.chk_ontop.isChecked() == dialog.stays_on_top

    # Press T again -> Toggle back
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state
    assert dialog.chk_ontop.isChecked() == init_state

    # Input guard test: when search edit is focused, T does not toggle
    dialog.activateWindow()
    dialog.edit_search.setFocus()
    qapp.processEvents()
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state

    dialog.close()


def test_dragon_leader_monitor_top_hotkey(qapp):
    """3. Test DragonLeaderMonitorDialog T hotkey toggles stays_on_top"""
    from ats.ui.dragon_monitor import DragonLeaderMonitorDialog

    dialog = DragonLeaderMonitorDialog(restore_state={})
    dialog.show()
    dialog.activateWindow()
    dialog.table.setFocus()
    qapp.processEvents()
    assert hasattr(dialog, 'chk_on_top')
    assert "置顶" in dialog.chk_on_top.text()

    init_state = dialog.stays_on_top
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == (not init_state)
    assert dialog.chk_on_top.isChecked() == dialog.stays_on_top

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state
    assert dialog.chk_on_top.isChecked() == init_state

    dialog.close()


def test_hot_sector_leaderboard_top_hotkey(qapp):
    """4. Test HotSectorLeaderboardDialog T hotkey toggles stays_on_top"""
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog

    dialog = HotSectorLeaderboardDialog(restore_state={})
    dialog.show()
    dialog.activateWindow()
    dialog.table.setFocus()
    qapp.processEvents()
    assert hasattr(dialog, 'chk_on_top')
    assert "置顶" in dialog.chk_on_top.text()

    init_state = dialog.stays_on_top
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == (not init_state)
    assert dialog.chk_on_top.isChecked() == dialog.stays_on_top

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state
    assert dialog.chk_on_top.isChecked() == init_state

    dialog.close()


def test_distribution_details_dialog_top_hotkey(qapp):
    """5. Test DistributionDetailsDialog T hotkey toggles stays_on_top"""
    from ats.ui.chart_widgets import DistributionDetailsDialog

    dialog = DistributionDetailsDialog(bucket_idx=0)
    dialog.show()
    dialog.activateWindow()
    dialog.table.setFocus()
    qapp.processEvents()
    assert hasattr(dialog, 'chk_on_top')
    assert "置顶" in dialog.chk_on_top.text()

    init_state = dialog.stays_on_top
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == (not init_state)
    assert dialog.chk_on_top.isChecked() == dialog.stays_on_top

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state
    assert dialog.chk_on_top.isChecked() == init_state

    # Search edit input guard
    dialog.activateWindow()
    dialog.search_edit.setFocus()
    qapp.processEvents()
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state

    dialog.close()


def test_stock_detail_dialog_top_hotkey(qapp):
    """6. Test StockDetailDialog T hotkey toggles stays_on_top"""
    from ats.ui.main_window import StockDetailDialog

    dialog = StockDetailDialog(code="688826", name="大普微")
    dialog.show()
    dialog.activateWindow()
    qapp.processEvents()
    assert hasattr(dialog, 'chk_on_top')
    assert "置顶" in dialog.chk_on_top.text()

    init_state = getattr(dialog, 'stays_on_top', False)
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == (not init_state)
    assert dialog.chk_on_top.isChecked() == dialog.stays_on_top

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state
    assert dialog.chk_on_top.isChecked() == init_state

    dialog.close()


def test_sbc_intraday_chart_dialog_top_hotkey(qapp):
    """7. Test SBCIntradayChartDialog T hotkey toggles stays_on_top"""
    from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog

    dialog = SBCIntradayChartDialog(code="688826")
    dialog.show()
    dialog.activateWindow()
    qapp.processEvents()
    init_state = getattr(dialog, '_is_stay_on_top', False)

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert getattr(dialog, '_is_stay_on_top', False) == (not init_state)

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert getattr(dialog, '_is_stay_on_top', False) == init_state

    dialog.close()


def test_intraday_strategy_dialog_top_hotkey(qapp):
    """8. Test IntradayStrategyDialog (PinzhunLadderStandaloneWindow) T hotkey toggles stays_on_top"""
    from ats.ui.intraday_strategy_dialog import IntradayStrategyDialog

    dialog = IntradayStrategyDialog(code="688826")
    dialog.show()
    dialog.activateWindow()
    qapp.processEvents()
    init_state = getattr(dialog, '_is_stay_on_top', False)

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert getattr(dialog, '_is_stay_on_top', False) == (not init_state)
    assert "开" in dialog.btn_topmost.text() or "关" in dialog.btn_topmost.text()

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert getattr(dialog, '_is_stay_on_top', False) == init_state

    dialog.close()


def test_all_codes_eval_dialog_top_hotkey(qapp):
    """9. Test AllCodesStrategyEvalDialog T hotkey toggles stays_on_top"""
    from ats.ui.intraday_strategy_dialog import IntradayStrategyDialog, AllCodesStrategyEvalDialog

    parent_win = IntradayStrategyDialog(code="688826")
    dialog = AllCodesStrategyEvalDialog(parent_workbench=parent_win)
    dialog.show()
    dialog.activateWindow()
    dialog.table_all.setFocus()
    qapp.processEvents()
    init_state = getattr(dialog, '_is_stay_on_top', False)

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert getattr(dialog, '_is_stay_on_top', False) == (not init_state)

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert getattr(dialog, '_is_stay_on_top', False) == init_state

    # Search edit input guard
    dialog.activateWindow()
    dialog.search_edit.setFocus()
    qapp.processEvents()
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert getattr(dialog, '_is_stay_on_top', False) == init_state

    dialog.close()
    parent_win.close()


def test_multi_period_dialog_top_hotkey(qapp):
    """10. Test MultiPeriodDialog T hotkey toggles on_top_chk"""
    from ats.ui.multi_period_dialog import MultiPeriodDialog

    dialog = MultiPeriodDialog()
    dialog.show()
    dialog.activateWindow()
    dialog.table.setFocus()
    qapp.processEvents()
    assert hasattr(dialog, 'on_top_chk')
    assert "置顶" in dialog.on_top_chk.text()

    init_state = dialog.stays_on_top
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == (not init_state)
    assert dialog.on_top_chk.isChecked() == dialog.stays_on_top

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state
    assert dialog.on_top_chk.isChecked() == init_state

    dialog.close()


def test_trade_flow_dialog_top_hotkey(qapp):
    """11. Test TradeFlowDialog T hotkey toggles stays_on_top"""
    from ats.ui.trade_flow import TradeFlowDialog

    dialog = TradeFlowDialog()
    dialog.show()
    dialog.activateWindow()
    dialog.flow_table.setFocus()
    qapp.processEvents()
    assert hasattr(dialog, 'chk_on_top')
    assert "置顶" in dialog.chk_on_top.text()

    init_state = dialog.stays_on_top
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == (not init_state)
    assert dialog.chk_on_top.isChecked() == dialog.stays_on_top

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state
    assert dialog.chk_on_top.isChecked() == init_state

    dialog.close()


def test_channel_scan_result_dialog_top_hotkey(qapp):
    """12. Test ChannelReversalScanResultDialog T hotkey toggles stays_on_top"""
    from ats.ui.channel_scan_result_dialog import ChannelReversalScanResultDialog

    dialog = ChannelReversalScanResultDialog(df_results=pd.DataFrame([{"score": 90, "code": "688826"}]))
    dialog.show()
    dialog.activateWindow()
    dialog.table.setFocus()
    qapp.processEvents()
    assert hasattr(dialog, 'chk_on_top')
    assert "置顶" in dialog.chk_on_top.text()

    init_state = dialog.stays_on_top
    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == (not init_state)
    assert dialog.chk_on_top.isChecked() == dialog.stays_on_top

    trigger_shortcut_or_key(dialog)
    qapp.processEvents()
    assert dialog.stays_on_top == init_state
    assert dialog.chk_on_top.isChecked() == init_state

    dialog.close()


def test_tdx_dormant_cooling_and_no_infinite_retry():
    """13. Test TDXRealtimeFetcher unlisted / dormant codes automatic cooling mechanism"""
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
    from unittest.mock import MagicMock

    fetcher = TDXRealtimeFetcher.get_instance()
    # Mock api.get_security_quotes to return empty for mock unlisted codes
    mock_api = MagicMock()
    mock_api.get_security_quotes.return_value = []
    fetcher.api = mock_api
    fetcher._is_connected = True

    unlisted_codes = ["688835", "920288", "301689"]
    fetcher.reset_code_dormancy()

    # 1st call -> Batch fails -> single calls fail -> count incremented
    quotes1 = fetcher.get_security_quotes_safe(unlisted_codes, force=False)
    assert len(quotes1) == 0
    for c in unlisted_codes:
        assert fetcher._no_quote_counts.get(c, 0) >= 1

    # 2nd call -> Count >= 2 -> added to _unlisted_or_dormant_codes
    quotes2 = fetcher.get_security_quotes_safe(unlisted_codes, force=False)
    assert len(quotes2) == 0
    for c in unlisted_codes:
        assert c in fetcher._unlisted_or_dormant_codes

    # 3rd call -> Since they are in _unlisted_or_dormant_codes and cooled down, api is NOT flooded
    mock_api.reset_mock()
    quotes3 = fetcher.get_security_quotes_safe(unlisted_codes, force=False)
    assert len(quotes3) == 0
    # Verified: api should NOT be called since all codes are in cooling period!
    mock_api.get_security_quotes.assert_not_called()
