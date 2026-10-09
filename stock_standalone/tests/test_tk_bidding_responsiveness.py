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
    env = dict(time=time, logger=Mock(), **namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), env)
    return env[name]


def panel_owner():
    scheduled = []
    timer = SimpleNamespace(singleShot=lambda delay, callback: scheduled.append((delay, callback)))
    owner = GuiOwner(
        _update_lock=threading.Lock(), _force_update_requested=False,
        _has_scoring_result=True,
        _last_refresh_ts=time.time(), _worker=SimpleNamespace(latest_df=object(), data_updated=Mock()),
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
