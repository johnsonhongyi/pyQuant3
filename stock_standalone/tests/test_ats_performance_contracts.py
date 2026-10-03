import os
import threading
import time

import numpy as np
import pandas as pd
import pytest

from ats.frame_merge import merge_sparse_frame
from ats.request_gate import RequestGate


def test_display_projection_is_detached_from_canonical_writers():
    from types import SimpleNamespace
    from ats.ledger_update_service import LedgerUpdateService
    ledger = SimpleNamespace(_mutation_lock=threading.RLock(),
                             entries={'600000': SimpleNamespace(latest_price=10., facts={'qty': 100})})
    universe = SimpleNamespace(radar_pool={'600000': {'price': 10.}}, watch_pool={}, trade_pool={})
    entries, pools = LedgerUpdateService(ledger).capture_projection(universe)
    ledger.entries['600000'].facts['qty'] = 200
    universe.radar_pool['600000']['price'] = 20.
    entries['600000'].latest_price = 30.
    assert entries['600000'].facts['qty'] == 100
    assert pools['radar_pool']['600000']['price'] == 10.
    assert ledger.entries['600000'].latest_price == 10.


def test_display_projection_waits_for_complete_writer_transaction():
    from types import SimpleNamespace
    from ats.ledger_update_service import LedgerUpdateService
    ledger = SimpleNamespace(_mutation_lock=threading.RLock(), entries={'price': 10., 'qty': 100})
    universe = SimpleNamespace(radar_pool={}, watch_pool={}, trade_pool={})
    started, captured = threading.Event(), threading.Event()
    results = []
    def capture():
        started.set()
        results.append(LedgerUpdateService(ledger).capture_projection(universe)[0])
        captured.set()
    with ledger._mutation_lock:
        ledger.entries['price'] = 20.
        reader = threading.Thread(target=capture)
        reader.start()
        assert started.wait(2)
        assert not captured.is_set()
        ledger.entries['qty'] = 200
    reader.join(2)
    assert not reader.is_alive()
    assert results == [{'price': 20., 'qty': 200}]


def test_failed_close_preserves_records_and_resumes_polling():
    from types import SimpleNamespace, MethodType
    from ats.ui.main_window import ATSMainWindow
    calls = []
    done = threading.Event()
    done.set()
    watcher = SimpleNamespace(isRunning=lambda: False, start=lambda: calls.append('watcher'))
    records = [{'code': '600000'}]
    state = SimpleNamespace(_close_requested=True, _close_deadline=time.monotonic()+10,
                            _is_exiting=True, _close_poll_was_active=True,
                            _close_resume_watchers={'tdx_watcher'}, tdx_watcher=watcher,
                            _next_day_watch_timer=SimpleNamespace(start=lambda: calls.append('poll')),
                            _shutdown_drain=SimpleNamespace(done=done, errors=['disk failed']),
                            status_bar=SimpleNamespace(showMessage=lambda *args: None),
                            _recorded_alpha_list=records)
    state._resume_close_watchers = MethodType(ATSMainWindow._resume_close_watchers, state)
    state._cancel_close_attempt = MethodType(ATSMainWindow._cancel_close_attempt, state)
    ATSMainWindow.closeEvent(state, SimpleNamespace(ignore=lambda: calls.append('ignored')))
    assert not state._is_exiting and not state._close_requested
    assert state._shutdown_drain is None
    assert state._recorded_alpha_list is records
    assert calls == ['ignored', 'poll', 'watcher']


def test_alpha_old_flush_cannot_overwrite_new_snapshot(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from ats.ui.main_window import ATSMainWindow
    from ats.bounded_evaluation_store import evaluation_store
    import sys_utils
    pending = []
    writes = []
    class DeferredThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            pending.append(self.target)
    monkeypatch.setattr(threading, 'Thread', DeferredThread)
    monkeypatch.setattr(sys_utils, 'get_app_root', lambda: str(tmp_path))
    monkeypatch.setattr(evaluation_store, 'put', lambda path, records, writer: writes.append(records))
    state = SimpleNamespace(_recorded_alpha_list=[{'pct': 1}])
    ATSMainWindow._flush_alpha_records_to_disk(state, '2026-10-03')
    state._recorded_alpha_list = [{'pct': 2}]
    ATSMainWindow._flush_alpha_records_to_disk(state, '2026-10-03')
    for target in reversed(pending):
        target()
    assert writes == [[{'pct': 2}]]


def test_shared_capital_analysis_preserves_force_contract():
    from ats.capital_dragon_engine import CapitalDragonEngine
    engine = CapitalDragonEngine()
    flags = []
    engine._analyze_capital_dragon_universe = lambda frame, pct, force: flags.append(force) or {}
    frame = pd.DataFrame({'close': [10.]})
    for version, force in [(1, False), (2, False), (3, True)]:
        frame.attrs.update(sync_session='test', source_version=version)
        engine.analyze_capital_dragon_universe(frame, force=force)
    assert flags == [False, False, True]


@pytest.mark.parametrize("seed", range(8))
def test_sparse_batch_matches_legacy_with_schema_and_dtype_changes(monkeypatch, seed):
    rng = np.random.RandomState(seed)
    cache = pd.DataFrame(rng.randn(100, 16), columns=[f"n{i}" for i in range(16)])
    cache["name"] = "original"
    cache["int"] = np.arange(100)
    diff = cache.iloc[::7].copy()
    diff.iloc[:, :16] += .125
    diff.iloc[::2, ::3] = np.nan
    diff["name"] = "changed"
    diff["int"] = diff["int"].astype(float) + .5
    diff["new"] = 5.0
    diff.loc[101] = diff.iloc[-1]
    monkeypatch.setenv("ATS_BATCH_DIFF", "0")
    expected = merge_sparse_frame(cache.copy(), diff)
    monkeypatch.setenv("ATS_BATCH_DIFF", "1")
    actual = merge_sparse_frame(cache.copy(), diff)
    pd.testing.assert_frame_equal(actual, expected)


def test_distribution_boundary_and_empty_semantics():
    from ats.ui.market_tasks import distribution_projection
    frame = pd.DataFrame({"percent": [-999, -8, -6, -4, -2, 0, 2, 4, 6, 8, 999, np.nan]})
    counts, stats = distribution_projection(frame)
    assert counts == [1] * 10
    assert stats == {"up": 5, "down": 5, "flat": 1, "avg": 0.0, "temp": 5 / 11 * 100}
    counts, stats = distribution_projection(pd.DataFrame({"percent": [np.nan]}))
    assert counts == [0] * 10
    assert stats["avg"] == stats["temp"] == 0


def test_gate_queue_timeout_and_recovery():
    gate = RequestGate(capacity=1)
    failures = []
    def waiter():
        try:
            with gate.enter(time.monotonic() + .02):
                failures.append("unexpected admission")
        except TimeoutError:
            failures.append("timeout")
    with gate.enter(time.monotonic() + 1):
        thread = threading.Thread(target=waiter)
        thread.start()
        thread.join(1)
        assert not thread.is_alive()
    assert failures == ["timeout"]
    with gate.enter(time.monotonic() + 1):
        pass


def test_gate_ack_precedes_queued_display():
    gate = RequestGate()
    order = []
    def waiter(name, priority):
        with gate.enter(time.monotonic() + 2, priority):
            order.append(name)
    with gate.enter(time.monotonic() + 2):
        display = threading.Thread(target=waiter, args=("display", 1))
        display.start()
        ack = threading.Thread(target=waiter, args=("ack", 0))
        ack.start()
        deadline = time.monotonic() + 1
        while len(gate._waiting) != 2 and time.monotonic() < deadline:
            time.sleep(.001)
        assert len(gate._waiting) == 2
    display.join(1)
    ack.join(1)
    assert order == ["ack", "display"]


def test_singleflight_shares_inflight_and_detaches_results():
    from ats.request_gate import SingleFlight
    flight = SingleFlight()
    entered, release = threading.Event(), threading.Event()
    calls, results = [], []
    def call():
        calls.append(1)
        entered.set()
        assert release.wait(2)
        return [{'price': 10}]
    def run():
        results.append(flight.run('same', call))
    first = threading.Thread(target=run)
    first.start()
    assert entered.wait(1)
    joined = threading.Event()
    ready = flight._calls['same']['ready']
    original_wait = ready.wait
    def joined_wait(timeout):
        joined.set()
        return original_wait(timeout)
    ready.wait = joined_wait
    second = threading.Thread(target=run)
    second.start()
    assert joined.wait(1)
    release.set()
    first.join(2)
    second.join(2)
    assert len(calls) == 1 and len(results) == 2
    results[0][0]['price'] = 0
    assert results[1][0]['price'] == 10
    assert flight.run('same', lambda: [11]) == [11]


def test_frame_rows_preserve_dynamic_columns_and_nulls():
    from ats.frame_rows import iter_frame_rows
    frame = pd.DataFrame({'price': [10., np.nan], 'dynamic': ['x', None],
                          'flag': pd.array([1, None], dtype='Int64')}, index=['600001', '600002'])
    expected = frame.to_dict('index')
    for code, row in iter_frame_rows(frame):
        assert list(row) == list(frame.columns)
        for column, value in expected[code].items():
            actual = row.get(column)
            assert (pd.isna(actual) and pd.isna(value)) or actual == value
        assert row.get('absent', 7) == 7


def test_shutdown_drain_reports_failure_and_keeps_task_order():
    from ats.shutdown import ShutdownDrain
    order = []
    def fail():
        order.append('failed')
        raise OSError('disk unavailable')
    drain = ShutdownDrain([('first', fail), ('last', lambda: order.append('last'))],
                          time.monotonic() + 2)
    assert drain.done.wait(2)
    assert order == ['failed', 'last']
    assert drain.errors == ['first: disk unavailable']


def test_shutdown_deadline_prevents_new_work():
    from ats.shutdown import ShutdownDrain
    calls = []
    drain = ShutdownDrain([('save', lambda: calls.append(1))], time.monotonic() - 1)
    assert drain.done.wait(1)
    assert not calls
    assert drain.errors == ['save: deadline exceeded']


def test_alpha_cold_events_keep_order_time_and_dedup():
    from collections import deque
    from types import SimpleNamespace, MethodType
    from ats.ui.main_window import ATSMainWindow
    state = SimpleNamespace(_alpha_pending_events=deque(), _recorded_alpha_stocks=None,
        _start_alpha_history_load=lambda: None, _request_alpha_flush_debounced=lambda day: None)
    state._record_alpha_signal = MethodType(ATSMainWindow._record_alpha_signal, state)
    for pct, when in [(1., '09:31:00'), (2., '09:32:00'), (3., '09:33:00')]:
        assert not state._record_alpha_signal('600001', 'name', pct, 0., pct, '大盘共振',
                                              _date='2026-10-02', _time=when)
    state._recorded_alpha_today = '2026-10-02'
    state._recorded_alpha_stocks = {}
    ATSMainWindow._drain_alpha_pending_events(state)
    assert [(r['time'], r['pct']) for r in state._recorded_alpha_list] == [
        ('09:31:00', '+1.00%'), ('09:33:00', '+3.00%')]
    assert not state._alpha_pending_events


def _never_read_pipe(connection, root):
    time.sleep(30)


def test_spawn_blocked_send_has_total_deadline_and_restarts(tmp_path, monkeypatch):
    import ats.next_day_watch_process as module
    original = module._worker_entry
    monkeypatch.setenv('INSTOCK_APP_ROOT', str(tmp_path))
    monkeypatch.setattr(module, '_worker_entry', _never_read_pipe)
    service = module.NextDayWatchProcess(str(tmp_path))
    try:
        started = time.monotonic()
        result = service.request('snapshot', timeout=.5, manifest={'large': 'x' * 1000000})
        assert 'timeout' in result.get('error', '')
        assert time.monotonic() - started < 4
        monkeypatch.setattr(module, '_worker_entry', original)
        result = service.request('health', timeout=8)
        assert result.get('pid') and not result.get('error')
    finally:
        service.close()
