from types import SimpleNamespace
from unittest.mock import Mock

import ats.ui.daily_limit_up_dialog as dialog


def test_mode_scan_ignores_stale_result_and_runs_latest(monkeypatch):
    scheduled = []
    monkeypatch.setattr(dialog.QTimer, 'singleShot', lambda delay, callback: scheduled.append(callback))
    monkeypatch.setattr(dialog.cct, 'get_trade_date_status', lambda: True, raising=False)
    widget = SimpleNamespace(
        current_mode='RADAR', _scan_request_revision=2, _scan_worker_busy=True,
        _scan_refresh_pending=True, current_records=['old'],
        _refresh_data_for_mode=Mock(), isVisible=lambda: True, isMinimized=lambda: False,
    )
    today = dialog.time.strftime('%Y-%m-%d')
    dialog.DailyLimitUpDialog._on_mode_scan_done(widget, ('BUBBLE', today, 1, ['stale'], None))
    assert widget.current_records == ['old']
    assert not widget._scan_worker_busy
    assert not widget._scan_refresh_pending
    assert scheduled == [widget._refresh_data_for_mode]


def test_mode_scan_failure_preserves_display(monkeypatch):
    monkeypatch.setattr(dialog.cct, 'get_trade_date_status', lambda: True, raising=False)
    widget = SimpleNamespace(
        current_mode='RADAR', _scan_request_revision=1, _scan_worker_busy=True,
        _scan_refresh_pending=False, current_records=['old'], isVisible=lambda: True,
        isMinimized=lambda: False, lbl_status=SimpleNamespace(setText=Mock()),
    )
    today = dialog.time.strftime('%Y-%m-%d')
    dialog.DailyLimitUpDialog._on_mode_scan_done(widget, ('RADAR', today, 1, None, 'failed'))
    assert widget.current_records == ['old']
    assert not widget._scan_worker_busy


def test_mode_scan_applies_current_result_and_coalesces_pending(monkeypatch):
    scheduled = []
    monkeypatch.setattr(dialog.QTimer, 'singleShot', lambda delay, callback: scheduled.append(callback))
    monkeypatch.setattr(dialog.cct, 'get_trade_date_status', lambda: True, raising=False)
    widget = SimpleNamespace(
        current_mode='BUBBLE', _scan_request_revision=3, _scan_worker_busy=True,
        _scan_refresh_pending=True, current_records=['old'], current_df=None,
        engine=SimpleNamespace(get_market_limit_up_summary=Mock(return_value={'count': 1})),
        _update_kpi_display=Mock(), _apply_filter=Mock(), _refresh_data_for_mode=Mock(), isVisible=lambda: True, isMinimized=lambda: False,
    )
    today = dialog.time.strftime('%Y-%m-%d')
    dialog.DailyLimitUpDialog._on_mode_scan_done(widget, ('BUBBLE', today, 3, ['new'], None))
    assert widget.current_records == ['new']
    widget._apply_filter.assert_called_once()
    assert scheduled == [widget._refresh_data_for_mode]
    assert not widget._scan_refresh_pending


def test_hidden_result_is_deferred_until_window_restored(monkeypatch):
    monkeypatch.setattr(dialog.cct, 'get_trade_date_status', lambda: True, raising=False)
    widget = SimpleNamespace(
        current_mode='RADAR', _scan_request_revision=4, _scan_worker_busy=True,
        _scan_refresh_pending=True, current_records=['old'],
        isVisible=lambda: False, isMinimized=lambda: False, _apply_filter=Mock(),
    )
    today = dialog.time.strftime('%Y-%m-%d')
    dialog.DailyLimitUpDialog._on_mode_scan_done(widget, ('RADAR', today, 4, ['new'], None))
    assert widget.current_records == ['new']
    assert widget._needs_render
    widget._apply_filter.assert_not_called()


def test_today_scan_failure_does_not_clear_records():
    widget = SimpleNamespace(current_mode='TODAY', _scan_request_revision=1,
        _scan_worker_busy=True, _scan_refresh_pending=False, current_records=['old'],
        isVisible=lambda: True, isMinimized=lambda: False, lbl_status=SimpleNamespace(setText=Mock()))
    dialog.DailyLimitUpDialog._on_today_scan_failed(widget, dialog.time.strftime('%Y-%m-%d'), 1)
    assert widget.current_records == ['old']
    assert not widget._scan_worker_busy
    widget.lbl_status.setText.assert_called_once()
