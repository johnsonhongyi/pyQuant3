import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace, MethodType
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt, QTimer
from ats.ui.fusion_ladder_dialog import FusionLadderDialog


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def make_view(app):
    table = QTableWidget(0, 18)
    for i, name in enumerate(['级别', '代码', '名称'] + [str(x) for x in range(15)]):
        table.setHorizontalHeaderItem(i, QTableWidgetItem(name))
    table.setSortingEnabled(True)
    fake = SimpleNamespace(tbl_live=table, cmb_day=SimpleNamespace(currentText=lambda: '2026-11-02'),
        chk_focus_only=SimpleNamespace(isChecked=lambda: False), chk_hit_only=SimpleNamespace(isChecked=lambda: False),
        chk_structure_only=SimpleNamespace(isChecked=lambda: False), extra_cols=[],
        _is_trading_window=lambda: False, _resolve_ats_strategy_df=lambda: None,
        _resolve_name=lambda code, row: row.get('name', code),
        _get_row_code_name=lambda t, row: (t.item(row, 1).text(), t.item(row, 2).text()),
        _num_item=FusionLadderDialog._num_item, _update_live_cell=FusionLadderDialog._update_live_cell,
        _mark_focus_row=FusionLadderDialog._mark_focus_row,
        _live_sort_fingerprint=FusionLadderDialog._live_sort_fingerprint,
        _price_order_stays_fixed=FusionLadderDialog._price_order_stays_fixed, _set_status=Mock(),
        lbl_status=SimpleNamespace(setStyleSheet=Mock()), _apply_search_filter=Mock(),
        isVisible=lambda: True, isMinimized=lambda: False,
        _schedule_live_render_slice=lambda callback: QTimer.singleShot(0, callback))
    fake._live_render_context = MethodType(FusionLadderDialog._live_render_context, fake)
    fake._render_live_inner = MethodType(FusionLadderDialog._render_live_inner, fake)
    fake._render_live = MethodType(FusionLadderDialog._render_live, fake)
    return fake


def render(view, app, rows):
    view._render_live(rows=rows, source_sig=('test',))
    for _ in range(100):
        app.processEvents()
        if (view.tbl_live.isSortingEnabled() and not getattr(view, '_live_render_active', False)
                and not getattr(view, '_live_render_dispatch_scheduled', False)):
            break


def test_reuses_rows_after_sort_and_resets_focus(app):
    view = make_view(app)
    rows = [dict(code='600001', name='A', price=10., pct=1., ts=1., focus_rank=1, fusion={'tier': 2}),
            dict(code='600002', name='B', price=20., pct=2., ts=1., fusion={'tier': 1})]
    render(view, app, rows)
    table = view.tbl_live
    table.sortItems(3, Qt.SortOrder.DescendingOrder)
    by_code = {table.item(i, 1).text(): i for i in range(2)}
    price_item = table.item(by_code['600001'], 3)
    code_item = table.item(by_code['600001'], 1)
    table.selectRow(by_code['600001'])
    rows[0] = dict(rows[0], price=30., focus_rank=0)
    render(view, app, rows)
    by_code = {table.item(i, 1).text(): i for i in range(2)}
    row = by_code['600001']
    assert table.item(row, 3) is price_item
    assert table.item(row, 1) is code_item
    assert price_item.text() == '30.00'
    assert not code_item.focus_rank
    assert not code_item.is_pinned
    assert table.item(table.currentRow(), 1).text() == '600001'
    assert not table.item(row, 3).is_pinned


def test_unchanged_rows_do_not_make_items(app):
    view = make_view(app)
    rows = [dict(code='600001', name='A', price=10., pct=1., ts=1., fusion={'tier': 2})]
    render(view, app, rows)
    view._num_item = Mock(side_effect=AssertionError('unexpected new item'))
    render(view, app, rows)
    assert view.tbl_live.item(0, 1).text() == '600001'


def test_new_snapshot_supersedes_pending_batches(app, monkeypatch):
    from ats.ui import fusion_ladder_dialog as module
    callbacks = []
    monkeypatch.setattr(module.QTimer, 'singleShot', lambda delay, callback: callbacks.append(callback))
    view = make_view(app)
    rows = [dict(code=str(i).zfill(6), name=str(i), price=10., pct=1., ts=1., fusion={'tier': 1})
            for i in range(500)]
    render(view, app, rows)
    assert callbacks
    generation = view._live_render_generation
    updated = [dict(code='600001', name='latest', price=30., pct=3., ts=2., fusion={'tier': 2})]
    for _ in range(10):
        render(view, app, updated)
    assert view._live_render_generation == generation
    assert view._live_render_pending[1] is updated
    while callbacks:
        callbacks.pop(0)()
    assert view.tbl_live.rowCount() == 1
    assert view.tbl_live.item(0, 1).text() == '600001'
    assert view.tbl_live.item(0, 2).text() == 'latest'
    assert view.tbl_live.isSortingEnabled()
    assert view._set_status.call_count == 2


def test_evidence_and_name_changes_update_existing_cells(app):
    view = make_view(app)
    row = dict(code='600001', name='A', price=10., pct=1., ts=1.,
               observation_evidence={'why': 'first'}, fusion={'tier': 2})
    render(view, app, [row])
    item = view.tbl_live.item(0, 14)
    row = dict(row, name='changed', observation_evidence={'why': 'second'})
    render(view, app, [row])
    assert view.tbl_live.item(0, 14) is item
    assert item.data(Qt.ItemDataRole.UserRole + 100) == {'why': 'second'}
    assert view.tbl_live.item(0, 2).text() == 'changed'


def test_non_sort_change_does_not_restart_sorting(app):
    view = make_view(app)
    row = dict(code='600001', name='A', price=10., pct=1., ts=1., fusion={'tier': 2})
    render(view, app, [row])
    view.tbl_live.sortItems(3, Qt.SortOrder.DescendingOrder)
    render(view, app, [row])
    toggle = Mock(wraps=view.tbl_live.setSortingEnabled)
    view.tbl_live.setSortingEnabled = toggle
    render(view, app, [dict(row, name='B')])
    toggle.assert_not_called()
    assert view.tbl_live.item(0, 2).text() == 'B'


def test_custom_sort_value_updates_even_when_text_is_unchanged(app):
    view = make_view(app)
    view.tbl_live.setColumnCount(19)
    view.tbl_live.setHorizontalHeaderItem(18, QTableWidgetItem('custom'))
    view.extra_cols = ['foo']
    raw = {'600001': 1.001, '600002': 1.002}
    view._resolve_ats_strategy_df = lambda: object()
    view._custom_code_lookup = lambda frame: {}
    view._extract_stock_custom_val = lambda frame, code, col, lookup: ('1.00', raw[code])
    rows = [dict(code=code, name=code, price=10., pct=1., ts=1., fusion={'tier': 1})
            for code in raw]
    render(view, app, rows)
    view.tbl_live.sortItems(18, Qt.SortOrder.AscendingOrder)
    render(view, app, rows)
    row = next(i for i in range(2) if view.tbl_live.item(i, 1).text() == '600001')
    item = view.tbl_live.item(row, 18)
    raw['600001'] = 1.003
    render(view, app, rows)
    row = next(i for i in range(2) if view.tbl_live.item(i, 1).text() == '600001')
    assert view.tbl_live.item(row, 18) is item
    assert item.text() == '1.00'
    assert item.data(Qt.ItemDataRole.UserRole) == pytest.approx(1.003)
    assert row == 1


def test_newer_snapshot_replaces_queued_dispatch(app, monkeypatch):
    from ats.ui import fusion_ladder_dialog as module
    callbacks = []
    monkeypatch.setattr(module.QTimer, 'singleShot', lambda delay, callback: callbacks.append(callback))
    view = make_view(app)
    rows = [dict(code=str(i).zfill(6), name=str(i), price=10., pct=1., ts=1., fusion={'tier': 1})
            for i in range(500)]
    render(view, app, rows)
    first = [dict(code='600001', name='first', price=11., pct=1., ts=1., fusion={'tier': 1})]
    latest = [dict(code='600001', name='latest', price=12., pct=1., ts=1., fusion={'tier': 1})]
    render(view, app, first)
    while callbacks and not getattr(view, '_live_render_dispatch_scheduled', False):
        callbacks.pop(0)()
    assert view._live_render_dispatch_scheduled
    render(view, app, latest)
    while callbacks:
        callbacks.pop(0)()
    assert view.tbl_live.item(0, 2).text() == 'latest'
    assert view.tbl_live.item(0, 3).text() == '12.00'


def test_price_updates_skip_sort_only_when_order_cannot_cross(app):
    view = make_view(app)
    rows = [dict(code=str(600001+i), name=str(i), price=10.+i, pct=1., ts=1., fusion={'tier': 1})
            for i in range(3)]
    render(view, app, rows)
    view.tbl_live.sortItems(3, Qt.SortOrder.AscendingOrder)
    render(view, app, rows)
    toggle = Mock(wraps=view.tbl_live.setSortingEnabled)
    view.tbl_live.setSortingEnabled = toggle
    moved = [dict(row, price=row['price']+.1) for row in rows]
    render(view, app, moved)
    toggle.assert_not_called()
    assert [view.tbl_live.item(i, 1).text() for i in range(3)] == ['600001', '600002', '600003']
    crossed = [dict(moved[0], price=13.), *moved[1:]]
    render(view, app, crossed)
    assert toggle.call_count >= 2
    assert [view.tbl_live.item(i, 1).text() for i in range(3)] == ['600002', '600003', '600001']


def test_price_order_guard_rejects_rounding_ties_and_focus(app):
    view = make_view(app)
    rows = [dict(code='600001', name='A', price=10.001, pct=1., ts=1., fusion={'tier': 1}),
            dict(code='600002', name='B', price=10.004, pct=1., ts=1., fusion={'tier': 1})]
    render(view, app, rows)
    view.tbl_live.sortItems(3, Qt.SortOrder.AscendingOrder)
    assert not view._price_order_stays_fixed(view.tbl_live, rows, [r['code'] for r in rows])
    rows[0]['focus_rank'] = 1
    assert not view._price_order_stays_fixed(view.tbl_live, rows, [r['code'] for r in rows])


def test_price_order_guard_covers_descending_and_intermediate_values(app):
    view = make_view(app)
    rows = [dict(code='600001', name='A', price=10.004, pct=1., ts=1., fusion={'tier': 1}),
            dict(code='600002', name='B', price=9.996, pct=1., ts=1., fusion={'tier': 1})]
    render(view, app, rows)
    view.tbl_live.sortItems(3, Qt.SortOrder.DescendingOrder)
    # Rounded intermediate values both become 10.00 even though raw values differ.
    assert not view._price_order_stays_fixed(view.tbl_live, rows, [r['code'] for r in rows])
    safe = [dict(rows[0], price=11.), dict(rows[1], price=9.)]
    render(view, app, safe)
    safe2 = [dict(safe[0], price=11.1), dict(safe[1], price=9.1)]
    assert view._price_order_stays_fixed(view.tbl_live, safe2, [r['code'] for r in safe2])


@pytest.mark.parametrize('direction', [Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder])
def test_price_updates_preserve_sorted_order_under_mixed_changes(app, direction):
    import random
    rng = random.Random(192)
    view = make_view(app)
    rows = [dict(code=str(600000+i), name=str(i), price=10.+i, pct=1., ts=1., fusion={'tier': 1})
            for i in range(40)]
    render(view, app, rows)
    view.tbl_live.sortItems(3, direction)
    for step in range(12):
        rows = [dict(row, price=10.+i+rng.uniform(-.2,.2)) for i, row in enumerate(rows)]
        if step == 6:
            rows[0] = dict(rows[0], price=80.)
        render(view, app, rows)
        expected = sorted(rows, key=lambda row: row['price'], reverse=direction == Qt.SortOrder.DescendingOrder)
        assert [view.tbl_live.item(i, 1).text() for i in range(40)] == [row['code'] for row in expected]
