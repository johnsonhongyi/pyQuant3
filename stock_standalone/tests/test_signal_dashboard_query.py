from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QComboBox, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem
from PyQt6.QtGui import QColor

from signal_dashboard_panel import SignalDashboardPanel, CATEGORY_MAP, SignalBus


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


class QueryHarness:
    for _name in ('_signal_matches_query', '_refresh_signal_dates', '_refresh_all_tables',
                  '_show_all_signal_details', '_refresh_signal_query', '_on_render_timer_timeout',
                  '_refresh_type_filter_items', '_show_stock_signal_details'):
        locals()[_name] = getattr(SignalDashboardPanel, _name)

    def __init__(self):
        self.date_filter = QComboBox()
        self.date_filter.addItem('今日', 'TODAY')
        self.date_filter.addItem('全部日期', 'ALL')
        self.type_filter = QComboBox()
        self.type_filter.addItem('全部信号', 'ALL')
        self.type_filter.addItem('ALERT', 'ALERT')
        self.search_input = QLineEdit()
        self.fold_check = QCheckBox()
        self.fold_check.setChecked(True)
        self._all_events = []
        self._dashboard_refresh_running = False
        self._row_cache = {}
        self.tables = {name: QTableWidget(0, 8) for name in ['全部信号', *CATEGORY_MAP, '其它信号', '📋 每日操作指南']}
        self._dashboard_refresh_timer = MagicMock()
        self._stock_stats = {'600000': {'count': 99}}
        self._stats_counters = {'breakout': 99}
        self._signal_type_counts = {'ALL': 99, 'ALERT': 99}
        self._save_ui_timer = MagicMock()
        self.tabs = MagicMock()
        self._engine_dirty = False
        self._stats_dirty = False


def event(day=0, code='600000', pattern='ALERT', detail='', hour=10):
    date = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=day)
    return SimpleNamespace(timestamp=date, event_type=SignalBus.EVENT_ALERT,
                           payload=dict(code=code, name='测试', pattern=pattern, detail=detail))


def jobs(state):
    return {job[0]: job[2] for job in state._dashboard_refresh_state['jobs']}


def test_date_query_and_day_stock_summary(qapp):
    state = QueryHarness()
    state._all_events = [event(-1), event(hour=9), event(hour=11)]
    state._refresh_all_tables()
    assert jobs(state)['全部信号'] == [state._all_events[-1]]
    state._dashboard_refresh_running = False
    state.date_filter.setCurrentIndex(1)
    state._refresh_all_tables()
    assert jobs(state)['全部信号'] == [state._all_events[0], state._all_events[-1]]
    assert state._stock_stats['600000']['count'] == 99
    assert state._stats_counters['breakout'] == 99
    assert state._signal_type_counts['ALL'] == 99


def test_filter_before_fold_preserves_older_matching_signal(qapp):
    state = QueryHarness()
    state._all_events = [event(detail='突破目标', hour=9), event(detail='别的形态', hour=11)]
    state.search_input.setText('突破目标')
    state._refresh_all_tables()
    assert jobs(state)['全部信号'] == state._all_events[:1]


def test_specific_date_and_empty_date(qapp):
    state = QueryHarness()
    old = event(-1)
    state._all_events = [old, event()]
    state._refresh_signal_dates()
    state.date_filter.setCurrentIndex(state.date_filter.findData(old.timestamp.date().isoformat()))
    assert state._signal_matches_query(old)
    assert not state._signal_matches_query(state._all_events[1])
    state._all_events = []
    state._refresh_signal_dates()
    assert state.date_filter.currentData() == old.timestamp.date().isoformat()


@pytest.mark.parametrize('size', [1200, 5000])
def test_all_details_not_truncated_at_500_and_no_engine_table_clear(qapp, size):
    state = QueryHarness()
    state.date_filter.setCurrentIndex(1)
    state.fold_check.setChecked(False)
    state._all_events = [event(code=f'{i:06d}') for i in range(size)]
    guidance = state.tables['📋 每日操作指南']
    guidance.setRowCount(3)
    state._refresh_all_tables()
    assert len(jobs(state)['全部信号']) == size
    assert guidance.rowCount() == 3


def test_summary_uses_latest_timestamp_with_out_of_order_arrivals(qapp):
    state = QueryHarness()
    state._all_events = [event(hour=11), event(hour=9)]
    state._refresh_all_tables()
    assert jobs(state)['全部信号'] == state._all_events[:1]


def test_all_details_shortcut_resets_query_only(qapp):
    state = QueryHarness()
    state.search_input.setText('600000')
    state.type_filter.setCurrentIndex(1)
    state._all_events = [event(-1), event()]
    state._show_all_signal_details()
    assert state.date_filter.currentData() == 'ALL'
    assert state.type_filter.currentData() == 'ALL'
    assert not state.search_input.text()
    assert not state.fold_check.isChecked()
    assert len(jobs(state)['全部信号']) == 2
    assert state._signal_type_counts['ALL'] == 99


def test_midnight_today_query_rebuilds(qapp):
    state = QueryHarness()
    state._query_today = (datetime.now() - timedelta(days=1)).date().isoformat()
    state._all_events = [event(-1), event()]
    state._on_render_timer_timeout()
    assert jobs(state)['全部信号'] == state._all_events[1:]


def test_type_counts_do_not_depend_on_filtered_rows(qapp):
    state = QueryHarness()
    state._accept_events = True
    state._type_filter_timer = MagicMock()
    state._last_type_filter_counts = None
    state._refresh_type_filter_items()
    assert '(99)' in state.type_filter.itemText(state.type_filter.findData('ALL'))


def test_stock_detail_keeps_selected_date(qapp):
    state = QueryHarness()
    state._all_events = [event(-1), event(), event(code='600001')]
    state._show_stock_signal_details('600000')
    assert state.date_filter.currentData() == 'TODAY'
    assert jobs(state)['全部信号'] == state._all_events[1:2]
    assert not state.fold_check.isChecked()


def test_actual_incremental_rows_use_date_key_and_keep_original_count(qapp, monkeypatch):
    import signal_dashboard_panel as module
    import global_favorites
    monkeypatch.setattr(module, 'get_alert_manager', lambda: SimpleNamespace(is_alerted=lambda code: False))
    monkeypatch.setattr(global_favorites, 'GlobalFavoriteManager', lambda: SimpleNamespace(favorite_stocks=set()))
    state = QueryHarness()
    state._ROLE_SEARCH_BLOB = Qt.ItemDataRole.UserRole + 106
    state._brushes = {}
    state._colors = {'#ffffff': QColor('#ffffff')}
    state._get_item_color = lambda *args: QColor('#ffffff')
    state._get_pattern_color = lambda *args: '#ffffff'
    state._flash_row = MagicMock()
    table = state.tables['全部信号']
    def insert(ts):
        SignalDashboardPanel._insert_row(state, table, ts, '600000', '测试', 'ALERT', '', 99, 0, payload={})
    insert('2026-10-12 15:00:00')
    insert('2026-10-13 09:30:00')
    insert('2026-10-13 10:00:00')
    insert('2026-10-13 09:45:00')
    assert table.rowCount() == 2
    assert table.item(1, 0).text() == '2026-10-13 10:00:00'
    assert table.item(1, 6).text() == '99'
    table.sortItems(0, Qt.SortOrder.DescendingOrder)
    insert('2026-10-12 15:01:00')
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == '2026-10-13 10:00:00'

    def fill(table, row, col, text, **kwargs):
        table.setItem(row, col, QTableWidgetItem(text))
    state._fast_update_cell = fill
    SignalDashboardPanel._fill_row_data(state, table, 1, event(-1).payload, event(-1).timestamp)
    assert len(table.item(1, 0).text()) == 19
    assert table.item(1, 6).text() == '99'


def test_query_change_during_chunked_refresh_runs_again(qapp, monkeypatch):
    import signal_dashboard_panel as module
    state = QueryHarness()
    state._all_events = [event()]
    state._refresh_all_tables()
    state._all_events.append(event(code='600001'))
    state._refresh_all_tables()
    assert state._dashboard_refresh_pending
    state._apply_filter = MagicMock()
    state._update_stats_display = MagicMock()
    state._limit_table_column_widths = MagicMock()
    state._queue_visible_sort = MagicMock()
    state._table_update_buffer = []
    callbacks = []
    monkeypatch.setattr(module.QTimer, 'singleShot', lambda ms, callback: callbacks.append(callback))
    SignalDashboardPanel._finish_all_tables_refresh(state)
    assert len(callbacks) == 1
    callbacks[0]()
    assert len(jobs(state)['全部信号']) == 2


def test_sort_waits_for_full_chunked_refresh(qapp):
    state = QueryHarness()
    state._dashboard_refresh_running = True
    state._pending_visible_sort = state.tables['全部信号']
    state._visible_sort_timer = MagicMock()
    SignalDashboardPanel._flush_visible_sort(state)
    assert state._pending_visible_sort is state.tables['全部信号']
    state._visible_sort_timer.start.assert_called_once_with(50)
