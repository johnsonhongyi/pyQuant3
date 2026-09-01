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


def get_win32_ws_ex_topmost(widget):
    """获取 Windows 真实的 WS_EX_TOPMOST 扩展样式状态"""
    import sys
    if sys.platform != "win32":
        return getattr(widget, "stays_on_top", False)
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_TOPMOST = 0x00000008
        if sys.maxsize > 2**32:
            GetWindowLong = user32.GetWindowLongPtrW
            GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
            GetWindowLong.restype = ctypes.c_ssize_t
        else:
            GetWindowLong = user32.GetWindowLongW
            GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
            GetWindowLong.restype = wintypes.LONG
        ex = GetWindowLong(hwnd, GWL_EXSTYLE)
        return bool(ex & WS_EX_TOPMOST)
    except Exception:
        return getattr(widget, "stays_on_top", False)


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


def test_rolling_window_velocity_and_state_machine():
    """14. Test TDXRealtimeFetcher rolling window velocity & state machine (anti-noise for low price stocks)"""
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher

    fetcher = TDXRealtimeFetcher.get_instance()
    code = "000718"  # 苏宁环球 (2.00 元低价股)
    last_close = 1.98
    base_t = 1700000000.0

    # 1. 模拟苏宁环球在 3 秒内在 2.00 和 2.01 之间微观跳动
    # 刚启动采样 (t=0s)
    vel1, tag1 = fetcher.calculate_rolling_velocity(code, 2.00, last_close, base_t)
    assert vel1 == 0.0
    assert tag1 == "⏱️ 窄幅整理"

    # t = 3s (价格微跳到 2.01)
    vel2, tag2 = fetcher.calculate_rolling_velocity(code, 2.01, last_close, base_t + 3.0)
    # 由于时间跨度小于 5 秒，防放大启动保护生效，稳定为 0.0%
    assert vel2 == 0.0

    # t = 6s (价格回到 2.00)
    vel3, tag3 = fetcher.calculate_rolling_velocity(code, 2.00, last_close, base_t + 6.0)
    # 死区过滤生效，绝不跳变出 -10.2%！
    assert abs(vel3) < 0.2

    # 2. 模拟真实强势拉升：60 秒内从 2.00 快速拉升至 2.06 (+3.0%)
    for i in range(1, 21):
        cur_t = base_t + i * 3.0  # 每 3 秒一个点，直到 60 秒
        cur_p = 2.00 + (2.06 - 2.00) * (i / 20.0)
        vel_rise, tag_rise = fetcher.calculate_rolling_velocity(code, cur_p, last_close, cur_t)

    # 60 秒达到 2.06，真实 1 分钟涨速应为约 +3.0%，状态机判定为 🚀 极速拉升
    assert vel_rise >= 2.0
    assert tag_rise == "🚀 极速拉升"

    # 3. 模拟真实跳水：从 2.06 快速下挫至 2.01 (-2.5%)
    for i in range(1, 21):
        cur_t = base_t + 60.0 + i * 3.0
        cur_p = 2.06 - (2.06 - 2.01) * (i / 20.0)
        vel_fall, tag_fall = fetcher.calculate_rolling_velocity(code, cur_p, last_close, cur_t)

    assert vel_fall <= -1.5
    assert tag_fall == "❄️ 极速跳水"


def test_trading_segment_velocity_engine_and_cache():
    """15. Test trading segment velocity & base price/volume cache across 4-hour market slices"""
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
    from datetime import datetime

    fetcher = TDXRealtimeFetcher.get_instance()
    fetcher._segment_stock_cache.clear()

    # 构造当天 09:35:00 的 epoch 时间戳
    today = datetime.now()
    t_0935 = datetime(today.year, today.month, today.day, 9, 35, 0).timestamp()
    t_0955 = datetime(today.year, today.month, today.day, 9, 55, 0).timestamp()
    t_1005 = datetime(today.year, today.month, today.day, 10, 5, 0).timestamp()
    t_1025 = datetime(today.year, today.month, today.day, 10, 25, 0).timestamp()

    code = "000718"
    last_close = 2.00

    # 1. 09:35: 首次进入 09:30~10:00 时段，开盘价 2.00，现价 2.00，量 1000手
    res1 = fetcher.calculate_segmented_velocity(
        code=code, price=2.00, open_price=2.00, last_close=last_close,
        vol=1000, amount=200000, now_ts=t_0935, segment_mode="30m"
    )
    assert res1["segment_key"] == "09:30~10:00"
    assert res1["segment_base_price"] == 2.00
    assert res1["velocity_pct"] == 0.0
    assert res1["velocity_tag"] == "⏱️ 窄幅横盘"

    # 2. 09:55: 在同一个 09:30~10:00 时段内，价格拉升至 2.06 (+3.0%)，量达到 5000手
    res2 = fetcher.calculate_segmented_velocity(
        code=code, price=2.06, open_price=2.00, last_close=last_close,
        vol=5000, amount=1020000, now_ts=t_0955, segment_mode="30m"
    )
    assert res2["segment_key"] == "09:30~10:00"
    assert res2["segment_base_price"] == 2.00
    assert res2["velocity_pct"] == 3.0
    assert res2["velocity_tag"] == "🚀 极速拉升"
    assert res2["segment_vol_increment"] == 4000.0

    # 3. 10:05: 自动跨时段切换到 10:00~10:30 时段，第一笔数据为 2.06，建立新基准
    res3 = fetcher.calculate_segmented_velocity(
        code=code, price=2.06, open_price=2.00, last_close=last_close,
        vol=6000, amount=1230000, now_ts=t_1005, segment_mode="30m"
    )
    assert res3["segment_key"] == "10:00~10:30"
    assert res3["segment_base_price"] == 2.06
    assert res3["velocity_pct"] == 0.0
    assert res3["velocity_tag"] == "⏱️ 窄幅横盘"

    # 4. 10:25: 在 10:00~10:30 时段内，价格小幅冲至 2.08 (净拉升 2.08 - 2.06 = +0.02 / 2.00 = +1.0%)
    res4 = fetcher.calculate_segmented_velocity(
        code=code, price=2.08, open_price=2.00, last_close=last_close,
        vol=8000, amount=1650000, now_ts=t_1025, segment_mode="30m"
    )
    assert res4["segment_key"] == "10:00~10:30"
    assert res4["velocity_pct"] == 1.0
    assert res4["velocity_tag"] == "🔥 强势推升"
    assert res4["segment_vol_increment"] == 2000.0


def test_hot_sector_segment_combo_and_persistence(qapp):
    """16. Test HotSectorLeaderboardDialog combo_segment_mode and persistence"""
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
    from ats.ui.styles import load_config_node

    dialog = HotSectorLeaderboardDialog()
    assert hasattr(dialog, "combo_segment_mode")

    # Switch to 15m segment (index 1)
    dialog.combo_segment_mode.setCurrentIndex(1)
    assert dialog._get_current_segment_mode_key() == "15m"
    assert load_config_node("ats_velocity_segment_mode") == 1
    assert "15分" in dialog.table.horizontalHeaderItem(6).text()

    # Switch back to 30m segment (index 0)
    dialog.combo_segment_mode.setCurrentIndex(0)
    assert dialog._get_current_segment_mode_key() == "30m"
    assert load_config_node("ats_velocity_segment_mode") == 0
    assert "30分" in dialog.table.horizontalHeaderItem(6).text()

    dialog.close()


def test_seamless_topmost_physical_style_toggle(qapp):
    """17. Test set_seamless_stay_on_top correctly flips WS_EX_TOPMOST physical style on Win32"""
    from PyQt6.QtWidgets import QWidget
    from ats.ui.styles import set_seamless_stay_on_top

    w = QWidget()
    w.show()
    qapp.processEvents()

    # 1. 切换置顶 -> True
    set_seamless_stay_on_top(w, True)
    qapp.processEvents()
    assert w.stays_on_top is True
    assert get_win32_ws_ex_topmost(w) is True

    # 2. 彻底解除置顶 -> False (WS_EX_TOPMOST 剥离，其他程序可在窗口前)
    set_seamless_stay_on_top(w, False)
    qapp.processEvents()
    assert w.stays_on_top is False
    assert get_win32_ws_ex_topmost(w) is False

    # 3. 再次切换置顶 -> True
    set_seamless_stay_on_top(w, True)
    qapp.processEvents()
    assert w.stays_on_top is True
    assert get_win32_ws_ex_topmost(w) is True

    # 4. 再次彻底解除置顶 -> False
    set_seamless_stay_on_top(w, False)
    qapp.processEvents()
    assert w.stays_on_top is False
    assert get_win32_ws_ex_topmost(w) is False

    w.close()


def test_spatial_follow_hud_topmost_toggle(qapp):
    """18. Test SpatialFollowHUD stays-on-top seamless toggle and physical style"""
    from tk_gui_modules.spatial_follow_hud import SpatialFollowHUD

    hud = SpatialFollowHUD()
    hud.show()
    qapp.processEvents()

    init_top = hud.stays_on_top
    init_style = get_win32_ws_ex_topmost(hud)
    assert init_top == init_style

    # Toggle
    hud._toggle_stays_on_top()
    qapp.processEvents()
    assert hud.stays_on_top == (not init_top)
    assert get_win32_ws_ex_topmost(hud) == (not init_top)

    # Toggle back
    hud._toggle_stays_on_top()
    qapp.processEvents()
    assert hud.stays_on_top == init_top
    assert get_win32_ws_ex_topmost(hud) == init_top

    hud.close()


def test_volume_details_topmost_toggle(qapp):
    """19. Test VolumeDetailsDialog stays-on-top seamless toggle"""
    from signal_dashboard_panel import VolumeDetailsDialog

    dlg = VolumeDetailsDialog()
    dlg.show()
    qapp.processEvents()

    init_top = dlg.stays_on_top
    dlg.chk_on_top.setChecked(not init_top)
    qapp.processEvents()
    assert dlg.stays_on_top == (not init_top)
    assert get_win32_ws_ex_topmost(dlg) == (not init_top)

    dlg.chk_on_top.setChecked(init_top)
    qapp.processEvents()
    assert dlg.stays_on_top == init_top
    assert get_win32_ws_ex_topmost(dlg) == init_top

    dlg.close()



