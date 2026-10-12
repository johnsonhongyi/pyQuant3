"""Exercise GUI scheduling and worker contention without starting market services."""
import ast
import threading
import time
from functools import lru_cache
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import List
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


class GuiOwner(SimpleNamespace):
    """Weak-referenceable receiver for real Qt signal/timer tests."""


@lru_cache(maxsize=2)
def source_tree(path):
    return ast.parse((ROOT / path).read_text(encoding='utf-8'))


def load_method(path, owner_class, name, **namespace):
    tree = source_tree(path)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == owner_class)
    node = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name == name)
    env = dict(time=time, logger=Mock())
    env.update(namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), env)
    return env[name]


def test_panel_open_coalesces_until_gui_delivery_and_releases_gate_after_failure(monkeypatch):
    import queue
    import sys

    for fail in (False, True):
        clock = [100.0]
        created = []

        def panel_factory(**_kwargs):
            created.append(threading.get_ident())
            if fail:
                raise RuntimeError('injected construction failure')
            return SimpleNamespace(show=Mock())

        monkeypatch.setitem(sys.modules, 'sector_bidding_panel',
                            SimpleNamespace(SectorBiddingPanel=panel_factory))
        owner = GuiOwner(tk_dispatch_queue=queue.Queue(), after=Mock(),
                         _auto_bidding_panel_requested=True)
        open_panel = load_method('instock_MonitorTK.py', 'StockMonitorApp',
                                 'open_sector_bidding_panel', threading=threading,
                                 time=SimpleNamespace(time=lambda: clock[0]), toast_message=Mock())
        open_panel(owner)
        callback = owner.tk_dispatch_queue.get(timeout=2)
        clock[0] += 3
        open_panel(owner)
        assert owner._bidding_panel_build_pending and owner.tk_dispatch_queue.empty()
        assert created == []
        callback()
        assert created == [threading.get_ident()]
        assert not owner._bidding_panel_build_pending
        if fail:
            assert not owner._auto_bidding_panel_requested


def panel_owner():
    scheduled = []
    timer = SimpleNamespace(singleShot=lambda delay, callback: scheduled.append((delay, callback)))
    owner = GuiOwner(
        _update_lock=threading.Lock(), _force_update_requested=False,
        _has_scoring_result=True,
    _last_refresh_ts=time.time(), _worker=SimpleNamespace(
        latest_df=object(), data_updated=Mock(), _score_request_count=0,
    ),
        _is_macro_active=True, _macro_query_str='close > 0',
        _run_macro_query_internal=Mock(), _refresh_sector_list=Mock(), main_window=None,
    )
    for name in ('_on_worker_finished', '_flush_worker_refresh', '_on_score_finished_callback'):
        method = load_method('sector_bidding_panel.py', 'SectorBiddingPanel', name,
                             QTimer=timer, cct=SimpleNamespace(CFG=SimpleNamespace(duration_sleep_time=30)))
        setattr(owner, name, MethodType(method, owner))
    return owner, scheduled


def test_automatic_scoring_does_not_force_render_or_macro_query():
    owner, scheduled = panel_owner()
    for _ in range(100):
        owner._on_score_finished_callback()
        owner._on_worker_finished()
    assert not owner._force_update_requested
    assert scheduled == []
    owner._run_macro_query_internal.assert_not_called()
    owner._refresh_sector_list.assert_not_called()


def test_first_scoring_result_is_shown_immediately_then_obeys_cooldown():
    owner, scheduled = panel_owner()
    owner._has_scoring_result = False
    owner._on_score_finished_callback()
    owner._on_worker_finished()
    assert len(scheduled) == 1
    scheduled.pop(0)[1]()
    for _ in range(100):
        owner._on_score_finished_callback()
        owner._on_worker_finished()
    assert scheduled == []
    owner._refresh_sector_list.assert_called_once()


def test_refresh_burst_coalesces_and_queries_the_latest_frame():
    owner, scheduled = panel_owner()
    owner._last_refresh_ts = 0
    for _ in range(100):
        owner._worker.latest_df = object()
        owner._on_worker_finished()
    latest = owner._worker.latest_df
    assert len(scheduled) == 1
    def check_latest(*_args, **_kwargs):
        assert owner._last_source_df is latest
    owner._run_macro_query_internal.side_effect = check_latest
    scheduled.pop(0)[1]()
    owner._run_macro_query_internal.assert_called_once_with('close > 0', is_auto_refresh=True)
    owner._refresh_sector_list.assert_called_once()
    assert not owner._ui_refresh_pending
    owner._on_worker_finished()
    assert scheduled == []


def test_manual_request_survives_an_ordinary_market_frame():
    owner, scheduled = panel_owner()
    owner._is_history_mode = False
    owner._force_update_requested = True
    owner._worker.df_queue = SimpleNamespace(get_nowait=Mock(side_effect=__import__('queue').Empty))
    owner._worker.add_data = Mock()
    receive = load_method('sector_bidding_panel.py', 'SectorBiddingPanel', 'on_realtime_data_arrived',
                          Empty=__import__('queue').Empty)
    receive(owner, object())
    assert owner._force_update_requested
    owner._on_worker_finished()
    assert len(scheduled) == 1
    scheduled.pop(0)[1]()
    assert not owner._force_update_requested
    owner._refresh_sector_list.assert_called_once()


def test_failed_render_releases_pending_gate_and_can_retry():
    owner, scheduled = panel_owner()
    owner._last_refresh_ts = 0
    owner._refresh_sector_list.side_effect = RuntimeError('temporary render failure')
    owner._on_worker_finished()
    scheduled.pop(0)[1]()
    assert not owner._ui_refresh_pending
    owner._refresh_sector_list.side_effect = None
    owner._on_worker_finished()
    scheduled.pop(0)[1]()
    assert owner._refresh_sector_list.call_count == 2


def restore_owner():
    saved = [('600000', '', 'A'), ('600001', '', 'B'), ('600002', '', 'C')]
    scheduled = []
    owner = SimpleNamespace(_pg_top10_window_simple={}, _is_closing=False,
                            show_concept_top10_window_simple=Mock(side_effect=[object(), object(), object()]),
                            after=lambda delay, callback: scheduled.append((delay, callback)))
    restore = load_method('tk_gui_modules/window_mixin.py', 'WindowMixin', 'restore_all_monitor_windows',
                          load_monitor_list=lambda _path: saved, MONITOR_LIST_FILE='unused')
    return owner, scheduled, restore


def test_startup_restoration_yields_between_windows_and_coalesces():
    owner, scheduled, restore = restore_owner()
    restore(owner)
    assert owner.show_concept_top10_window_simple.call_count == 1
    assert len(scheduled) == 1 and scheduled[0][0] > 0
    restore(owner)
    assert owner.show_concept_top10_window_simple.call_count == 1
    while scheduled:
        scheduled.pop(0)[1]()
    assert list(owner._pg_top10_window_simple) == ['A_', 'B_', 'C_']
    assert not owner._monitor_restore_pending


def test_shutdown_cancels_remaining_window_restoration():
    owner, scheduled, restore = restore_owner()
    restore(owner)
    owner._is_closing = True
    scheduled.pop(0)[1]()
    assert owner.show_concept_top10_window_simple.call_count == 1
    assert not owner._monitor_restore_pending and scheduled == []


def test_busy_stock_search_reuses_only_results_for_the_same_query():
    lock = threading.Lock()
    cached = [{'code': '600000'}]
    detector = SimpleNamespace(_lock=lock, search_by_index=Mock())
    owner = SimpleNamespace(detector=detector, _ui_stock_search_cache=('600000', cached))
    search = load_method('sector_bidding_panel.py', 'SectorBiddingPanel', '_search_sectors_by_stock', List=List)
    lock.acquire()
    try:
        started = time.perf_counter()
        assert search(owner, '600000') is cached
        assert search(owner, 'different') == []
        assert time.perf_counter() - started < 0.1
        detector.search_by_index.assert_not_called()
    finally:
        lock.release()


def test_search_index_fallback_is_locked_and_releases_after_failure():
    lock = threading.RLock()
    detector = SimpleNamespace(_lock=lock, active_sectors={})
    results = [{'code': '600000'}]
    def index_search(_query):
        assert lock._is_owned()
        with lock:
            return results
    detector.search_by_index = index_search
    owner = SimpleNamespace(detector=detector)
    search = load_method('sector_bidding_panel.py', 'SectorBiddingPanel', '_search_sectors_by_stock', List=List)
    assert search(owner, '600000') is results
    assert not lock._is_owned()
    detector.search_by_index = Mock(side_effect=RuntimeError('bad index'))
    try:
        search(owner, 'new')
    except RuntimeError:
        pass
    assert not lock._is_owned()


def test_chart_opens_from_table_snapshot_when_both_worker_locks_are_busy():
    class QtRoles:
        ItemDataRole = SimpleNamespace(UserRole=1)
    detector_lock, cache_lock = threading.Lock(), threading.Lock()
    rs = SimpleNamespace(kline_cache=SimpleNamespace(_lock=cache_lock),
                         get_minute_klines=Mock(), get_emotion_score=Mock(return_value=50),
                         get_55188_data=Mock(return_value={}))
    detector = SimpleNamespace(_lock=detector_lock, realtime_service=rs)
    klines = [{'close': 10.0}]
    table = Mock()
    table.item.side_effect = lambda _row, col: (
        SimpleNamespace(text=lambda: '600000') if col == 0 else
        SimpleNamespace(text=lambda: 'test') if col == 1 else
        SimpleNamespace(data=lambda _role: dict(klines=klines, last_close=9.0, prices=[10.0])))
    dialog = Mock()
    create_dialog = Mock(return_value=dialog)
    owner = SimpleNamespace(detector=detector, stock_table=table, stock_cols=['code', 'name', 'trend'])
    click = load_method('sector_bidding_panel.py', 'SectorBiddingPanel', '_on_stock_double_clicked',
                        Qt=QtRoles, DetailedChartDialog=create_dialog)
    detector_lock.acquire()
    cache_lock.acquire()
    try:
        started = time.perf_counter()
        click(owner, 0, 2)
        assert time.perf_counter() - started < 0.1
        rs.get_minute_klines.assert_not_called()
        assert create_dialog.call_args.args[2] is klines
        dialog.exec.assert_called_once()
    finally:
        cache_lock.release()
        detector_lock.release()


def test_single_window_failure_does_not_abort_startup_restoration():
    owner, scheduled, restore = restore_owner()
    owner.show_concept_top10_window_simple.side_effect = [RuntimeError('unavailable'), object(), object()]
    restore(owner)
    while scheduled:
        scheduled.pop(0)[1]()
    assert list(owner._pg_top10_window_simple) == ['B_', 'C_']
    assert not owner._monitor_restore_pending


def test_malformed_saved_entry_does_not_cancel_valid_windows():
    owner, scheduled, _restore = restore_owner()
    restore = load_method('tk_gui_modules/window_mixin.py', 'WindowMixin', 'restore_all_monitor_windows',
                          load_monitor_list=lambda _path: [None, ('600000', '', 'valid')],
                          MONITOR_LIST_FILE='unused')
    restore(owner)
    while scheduled:
        scheduled.pop(0)[1]()
    assert list(owner._pg_top10_window_simple) == ['valid_']
    assert not owner._monitor_restore_pending


def test_live_tk_input_runs_between_restored_windows():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    created, input_times = [], []
    def create_window(*_args, **_kwargs):
        time.sleep(0.025)
        created.append(object())
        return created[-1]
    owner = SimpleNamespace(_pg_top10_window_simple={}, after=root.after,
                            show_concept_top10_window_simple=create_window)
    restore = load_method('tk_gui_modules/window_mixin.py', 'WindowMixin', 'restore_all_monitor_windows',
                          load_monitor_list=lambda _path: [('600000', '', str(i)) for i in range(8)],
                          MONITOR_LIST_FILE='unused')
    started = time.perf_counter()
    root.after(0, lambda: restore(owner))
    root.after(1, lambda: input_times.append((time.perf_counter() - started, len(created))))
    def check_done():
        if len(created) == 8:
            root.quit()
        else:
            root.after(10, check_done)
    root.after(10, check_done)
    root.after(3000, root.quit)
    try:
        root.mainloop()
        assert len(created) == 8
        assert input_times and input_times[0][0] < 0.15 and input_times[0][1] < 8
    finally:
        root.destroy()


def test_live_qt_completion_burst_does_not_starve_input_timer():
    from PyQt6.QtCore import QObject, QEventLoop, QTimer, pyqtSignal
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    loop = QEventLoop()
    class Bridge(QObject):
        completed = pyqtSignal()
    bridge = Bridge()
    owner, _scheduled = panel_owner()
    for name in ('_on_worker_finished', '_flush_worker_refresh'):
        method = load_method('sector_bidding_panel.py', 'SectorBiddingPanel', name,
                             QTimer=QTimer, cct=SimpleNamespace(CFG=SimpleNamespace(duration_sleep_time=30)))
        setattr(owner, name, MethodType(method, owner))
    owner._last_refresh_ts = 0
    owner._run_macro_query_internal.side_effect = lambda *_args, **_kwargs: time.sleep(0.003)
    owner._refresh_sector_list.side_effect = lambda: time.sleep(0.003)
    bridge.completed.connect(owner._on_worker_finished)
    input_times = []
    def send_burst():
        for _ in range(100):
            bridge.completed.emit()
    worker = threading.Thread(target=send_burst)
    started = time.perf_counter()
    worker.start()
    QTimer.singleShot(1, lambda: input_times.append(time.perf_counter() - started))
    stop = QTimer()
    stop.setSingleShot(True)
    stop.timeout.connect(loop.quit)
    stop.start(500)
    loop.exec()
    worker.join(timeout=1)
    assert not worker.is_alive() and input_times and input_times[0] < 0.15
    owner._refresh_sector_list.assert_called_once()
    owner._run_macro_query_internal.assert_called_once()


class CodeFrame:
    """Minimal frame contract for AST-extracted worker methods."""

    columns = ['code']
    empty = False

    def __init__(self, codes=('600000',)):
        self.codes = list(codes)
        self.index = self.codes

    def __getitem__(self, column):
        assert column == 'code'
        return self.codes


def worker_owner(score_in_worker=False):
    detector = SimpleNamespace(register_codes=Mock(), update_scores=Mock())
    owner = SimpleNamespace(
        detector=detector, score_in_worker=score_in_worker, latest_df=None,
        _safe_log_error=Mock(), _score_request_count=0, _is_running=True,
    )
    method = load_method(
        'sector_bidding_panel.py', 'DataProcessWorker', '_process_df_chunked',
        _RE_NON_DIGIT=__import__('re').compile(r'\D'), traceback=__import__('traceback'),
        time=SimpleNamespace(sleep=Mock()),
    )
    owner._process_df_chunked = MethodType(method, owner)
    return owner


def shared_panel_owner(worker, work_time):
    owner = SimpleNamespace(
        _is_history_mode=False, _is_global_detector=True,
        _update_lock=threading.Lock(), _force_update_requested=False,
        _fallback_df=None, _global_detector_is_empty=lambda: False,
        main_window=SimpleNamespace(
            realtime_service=SimpleNamespace(is_ready=True, paused=False),
        ),
        _worker=worker,
    )
    receive = load_method(
        'sector_bidding_panel.py', 'SectorBiddingPanel', 'on_realtime_data_arrived',
        cct=SimpleNamespace(get_work_time_duration=lambda: work_time), logger=Mock(),
    )
    owner.on_realtime_data_arrived = MethodType(receive, owner)
    worker.detector = SimpleNamespace(register_codes=Mock(), update_scores=Mock())
    worker._safe_log_error = Mock()
    worker.latest_df = None
    def enqueue_and_process(df, score_requested=False, force_score=False):
        worker._process_df_chunked(df, score_requested, force_score)
        return True
    worker.add_data = Mock(side_effect=enqueue_and_process)
    return owner


def test_shared_worker_does_not_reingest_or_rescore_normal_market_frame():
    owner = worker_owner(score_in_worker=False)
    panel = shared_panel_owner(owner, work_time=True)
    frame = CodeFrame()
    panel.on_realtime_data_arrived(frame)
    owner.detector.register_codes.assert_not_called()
    owner.detector.update_scores.assert_not_called()
    owner.add_data.assert_called_once_with(
        frame, score_requested=False, force_score=False,
    )
    assert owner.latest_df is frame


def test_shared_worker_can_register_and_score_requested_after_hours_frame():
    owner = worker_owner(score_in_worker=False)
    panel = shared_panel_owner(owner, work_time=False)
    frame = CodeFrame(('600000', '000001'))
    panel.on_realtime_data_arrived(frame)
    owner.detector.register_codes.assert_called_once_with(frame)
    owner.detector.update_scores.assert_called_once_with(
        active_codes=['600000', '000001'], force=False,
    )
    assert owner._score_request_count == 1
    owner.add_data.assert_called_once_with(
        frame, score_requested=True, force_score=False,
    )
    panel.on_realtime_data_arrived(frame)
    owner.detector.register_codes.assert_called_once_with(frame)
    owner.detector.update_scores.assert_called_once()
    assert owner._score_request_count == 1
    newer_frame = CodeFrame(('600000', '000001', '600002'))
    panel.on_realtime_data_arrived(newer_frame)
    assert owner.detector.register_codes.call_count == 2
    assert owner.detector.register_codes.call_args.args == (newer_frame,)
    assert owner.detector.update_scores.call_count == 2
    assert owner._score_request_count == 2
    assert owner.latest_df is newer_frame


def test_queued_frame_merge_preserves_manual_force_request():
    class QueueStub:
        def __init__(self):
            self.items = [
                (object(), False, False),
                (object(), False, True),
                (object(), False, False),
            ]
            self.put_items = []

        def qsize(self):
            return len(self.items)

        def get_nowait(self):
            return self.items.pop(0)

        def put_nowait(self, item):
            self.put_items.append(item)

    queue_stub = QueueStub()
    add_data = load_method(
        'sector_bidding_panel.py', 'DataProcessWorker', 'add_data',
    )
    worker = SimpleNamespace(df_queue=queue_stub)
    newest = CodeFrame(('600003',))
    assert add_data(worker, newest, score_requested=False, force_score=False)
    assert queue_stub.put_items == [(newest, False, True)]


def test_force_score_waits_for_active_shared_score_then_submits(monkeypatch):
    owner = worker_owner(score_in_worker=False)
    score_lock = threading.Lock()
    owner.detector._score_lock = score_lock
    owner.detector._score_active = True
    sleep_calls = []

    def release_active_score(delay):
        sleep_calls.append(delay)
        with score_lock:
            owner.detector._score_active = False

    process = load_method(
        'sector_bidding_panel.py', 'DataProcessWorker', '_process_df_chunked',
        _RE_NON_DIGIT=__import__('re').compile(r'\D'),
        traceback=__import__('traceback'),
        time=SimpleNamespace(sleep=release_active_score),
    )
    owner._process_df_chunked = MethodType(process, owner)
    frame = CodeFrame()
    owner._process_df_chunked(frame, score_requested=True, force_score=True)
    assert sleep_calls[0] == 0.05
    owner.detector.register_codes.assert_called_once_with(frame)
    owner.detector.update_scores.assert_called_once_with(
        active_codes=['600000'], force=True,
    )
    assert owner._score_request_count == 1


def test_manual_refresh_forces_recalculation_from_existing_market_frame():
    frame = CodeFrame()
    worker = SimpleNamespace(add_data=Mock(), trigger_recalc=Mock())
    owner = SimpleNamespace(
        _is_history_mode=False, _is_global_detector=True,
        _update_lock=threading.Lock(),
        _force_update_requested=False, _fallback_df=frame,
        _worker=worker,
        main_window=SimpleNamespace(df_all=frame),
        btn_refresh=SimpleNamespace(setEnabled=Mock(), setText=Mock()),
        _restore_refresh_button_state=Mock(),
    )
    receive_frame = load_method(
        'sector_bidding_panel.py', 'SectorBiddingPanel', 'on_realtime_data_arrived',
        logger=Mock(),
    )
    owner.on_realtime_data_arrived = MethodType(receive_frame, owner)
    manual_refresh = load_method(
        'sector_bidding_panel.py', 'SectorBiddingPanel', 'manual_refresh',
        QTimer=SimpleNamespace(singleShot=Mock()), logger=Mock(),
    )
    manual_refresh(owner)
    worker.add_data.assert_called_once_with(
        frame, score_requested=True, force_score=True,
    )
    worker.trigger_recalc.assert_not_called()


def test_first_empty_shared_panel_requests_one_detector_seed_from_current_frame():
    frame = CodeFrame()
    detector = SimpleNamespace(
        _lock=threading.RLock(), _tick_series={}, active_sectors={}, daily_watchlist={},
    )
    owner = SimpleNamespace(
        sector_table=SimpleNamespace(rowCount=lambda: 0),
        status_lbl=SimpleNamespace(setText=Mock()),
        _is_global_detector=True, detector=detector,
        _global_detector_is_empty=lambda: True,
        main_window=SimpleNamespace(df_all=frame),
        on_realtime_data_arrived=Mock(),
    )
    show_event = load_method(
        'sector_bidding_panel.py', 'SectorBiddingPanel', 'showEvent',
        QTimer=SimpleNamespace(singleShot=Mock()),
    )
    show_event.__globals__['super'] = lambda: SimpleNamespace(showEvent=Mock())
    show_event(owner, object())
    owner.on_realtime_data_arrived.assert_called_once_with(
        frame, force_update=True, score_if_needed=True,
    )
