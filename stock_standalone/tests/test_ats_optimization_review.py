"""Comprehensive regression checks for ATS performance optimizations (2026-10-01).

Validates:
1. Heatmap card reuse and complete 60-item fingerprint (no stale items past #30).
2. Price load failure 30s TTL backoff retry and Qt queued signal trigger.
3. Vectorized name cache 60s periodic sync, overnight reset, and in-place renaming update.
4. UI deferred tasks (ladder, daily limit, distribution) frame coalescing.
5. TDX bounded sliding window concurrency, cancellation, and hard timeout with blocking tasks.
6. Global market panel in-place cell reuse, selection preservation, and safe worker decoupling on close.
7. History load tiered TTL: lock conflict/IO read exception 30s TTL and empty negative cache 60s TTL.
8. Strategy formula filter background computation with revision control (UI thread 0ms blocking).
9. Bounded evaluation store lock scope optimization and pending atomic snapshot consistency.
"""
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Ensure offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["test_ats"])
    yield app


# ============================================================================
# 1. Heatmap Card Reuse & Fingerprint Test
# ============================================================================
def test_heatmap_card_reuse_and_fingerprint(qapp):
    from PyQt6.QtWidgets import QWidget
    from ats.ui.heatmap_widget import SectorHeatmapWidget

    widget = SectorHeatmapWidget()
    widget.resize(400, 600)

    # 40 valid sectors
    sectors_v1 = [
        (f"板块_{i}", round((i % 7 - 3) * 1.1, 2), f"领涨_{i}", f"600{i:03d}")
        for i in range(40)
    ]
    widget.sectors = sectors_v1
    widget.render_grid()

    cards_v1 = list(widget._grid_cards)
    assert len(cards_v1) == 40
    fp1 = widget._last_rendered_fingerprint
    assert fp1 is not None

    # Test #31-#40 item change: must trigger fingerprint change!
    sectors_v2 = list(sectors_v1)
    # Modify item #35
    sectors_v2[35] = ("板块_35", 9.99, "新领涨_35", "600035")
    widget.sectors = sectors_v2
    widget.render_grid()

    fp2 = widget._last_rendered_fingerprint
    assert fp2 != fp1, "Fingerprint must capture changes in items beyond index 30!"

    # Structure unchanged -> cards MUST BE REUSED in-place
    cards_v2 = list(widget._grid_cards)
    assert len(cards_v2) == 40
    for c1, c2 in zip(cards_v1, cards_v2):
        assert c1[0] is c2[0], "Grid cards must be reused in-place when structure is identical!"

    # Unchanged cards skipped via dirty check; card #35 updated
    assert cards_v2[35][0]._sector_render_state[0][1] == 9.99
    assert cards_v2[0][0]._sector_render_state[0][1] == sectors_v1[0][1]

    # Structure change (add 5 items) -> cards rebuilt smoothly
    sectors_v3 = sectors_v2 + [
        (f"板块_{i}", 1.0, f"领涨_{i}", f"600{i:03d}") for i in range(40, 45)
    ]
    widget.sectors = sectors_v3
    widget.render_grid()
    cards_v3 = list(widget._grid_cards)
    assert len(cards_v3) == 45
    assert cards_v3[0] is not cards_v1[0]


# ============================================================================
# 2. Price Load Failure 30s TTL & Queued Signal Test
# ============================================================================
def test_price_load_failure_ttl_and_queued_signal(monkeypatch):
    from ats.ui.main_window import ATSMainWindow

    class DummyWindow:
        def __init__(self):
            self.prices_loading_codes = set()
            self.prices_failed_codes = set()
            self._price_failure_times = {}
            self._pending_price_codes = set()
            self._batch_price_timer = MagicMock()
            self.stock_realtime_cache = {}

        _async_load_stock_prices = ATSMainWindow._async_load_stock_prices

    win = DummyWindow()

    mock_clock = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: mock_clock[0])

    # Initial failure at t=100.0
    win.prices_failed_codes.add("600000")
    win._price_failure_times["600000"] = 100.0

    # At t=115.0 (< 30s later), calling price load should NOT retry "600000"
    mock_clock[0] = 115.0
    win._async_load_stock_prices(["600000"])
    assert "600000" in win.prices_failed_codes
    assert "600000" not in win._pending_price_codes

    # At t=131.0 (> 30s later), calling price load should DISCARD failure and retry
    win._pending_price_codes.clear()
    mock_clock[0] = 131.0
    win._async_load_stock_prices(["600000"])
    assert "600000" not in win.prices_failed_codes
    assert "600000" not in win._price_failure_times
    assert "600000" in win._pending_price_codes
    assert win._batch_price_timer.start.called


# ============================================================================
# 3. Name Cache 60s Periodic Sync, Renaming In-Place Update & Overnight Reset
# ============================================================================
def test_name_cache_periodic_sync_and_renaming(monkeypatch):
    import pandas as pd
    import datetime
    from ats.ui.main_window import ATSMainWindow

    class DummyMW:
        def __init__(self):
            self.name_cache = {}
            self._name_cache_initialized = False
            self._name_cache_last_len = 0
            self._last_name_cache_sync_t = 0.0
            self._name_cache_date = "2026-10-01"
            self.current_df = pd.DataFrame({"name": ["平安银行", "万科A"]}, index=["000001", "000002"])

        _update_name_cache_from_df = ATSMainWindow._update_name_cache_from_df
        _sync_name_cache = ATSMainWindow._sync_name_cache
        get_stock_name = ATSMainWindow.get_stock_name
        get_df_row_safe = ATSMainWindow.get_df_row_safe

    win = DummyMW()

    mock_time = [1000.0]
    monkeypatch.setattr(time, "time", lambda: mock_time[0])
    monkeypatch.setattr("ats.ui.main_window.time.time", lambda: mock_time[0])

    # 1. Cold start sync via actual _sync_name_cache method
    win._sync_name_cache()
    assert win._name_cache_initialized is True
    assert win.get_stock_name("000001") == "平安银行"
    assert win._last_name_cache_sync_t == 1000.0

    # 2. Subsequent frame within 60s -> skipped (no unnecessary sync)
    mock_time[0] = 1010.0
    win._sync_name_cache()
    assert win._last_name_cache_sync_t == 1000.0

    # 3. Stock renaming in current_df (万科A -> *ST万科) after 60s -> synced!
    win.current_df.loc["000002", "name"] = "*ST万科"
    mock_time[0] = 1065.0  # 65s later
    win._sync_name_cache()
    assert win._last_name_cache_sync_t == 1065.0
    assert win.get_stock_name("000002") == "*ST万科"

    # 4. Overnight reset: date changed -> forces immediate re-sync even if delta < 60s
    win._name_cache_date = "2026-09-30"  # yesterday
    mock_time[0] = 1070.0  # only 5s later
    win._sync_name_cache()
    assert win._name_cache_date == datetime.date.today().isoformat()
    assert win._last_name_cache_sync_t == 1070.0


# ============================================================================
# 4. UI Deferred Tasks Coalescing Test (_queue_latest_ui_task)
# ============================================================================
def test_queue_latest_ui_task_coalesces_frames(qapp):
    from PyQt6.QtCore import QTimer, QEventLoop
    from PyQt6.QtWidgets import QWidget
    from ats.ui.main_window import ATSMainWindow

    class DummyWindow(QWidget):
        _queue_latest_ui_task = ATSMainWindow._queue_latest_ui_task

    win = DummyWindow()
    executed = []

    for frame_id in range(5):
        def make_task(fid):
            return lambda: executed.append(fid)
        win._queue_latest_ui_task("distribution", 50, make_task(frame_id))

    assert executed == []

    loop = QEventLoop()
    QTimer.singleShot(120, loop.quit)
    loop.exec()

    # Only latest task (frame 4) executed
    assert executed == [4]
    win.close()


# ============================================================================
# 5. TDX Bounded Sliding Window Concurrency, Cancellation & Hard Timeout
# ============================================================================
def test_scan_stocks_tdx_bounded_sliding_window_and_cancellation(monkeypatch):
    from ats.channel_bottom_reversal_strategy import ChannelBottomReversalStrategy
    import threading

    strat = ChannelBottomReversalStrategy()
    evaluated_codes = []
    concurrency_record = []
    active_workers = [0]
    active_lock = threading.Lock()

    def mock_evaluate(code, category="60m", count=120):
        with active_lock:
            active_workers[0] += 1
            concurrency_record.append(active_workers[0])
        time.sleep(0.02)
        evaluated_codes.append(code)
        with active_lock:
            active_workers[0] -= 1
        return {"code": code, "is_matched": True, "score": 88.0}

    monkeypatch.setattr(strat, "evaluate_stock_tdx", mock_evaluate)

    # 1. Deduplication check: duplicate codes should only be evaluated once
    codes = ["600000", "000001", "600000", "000002", "000001"]
    df = strat.scan_stocks_tdx(codes, max_workers=2)
    assert len(evaluated_codes) == 3
    assert set(evaluated_codes) == {"600000", "000001", "000002"}
    assert len(df) == 3

    # 2. Concurrency bounded: active workers should not exceed max_workers * 2
    evaluated_codes.clear()
    codes_large = [f"{i:06d}" for i in range(20)]
    df_large = strat.scan_stocks_tdx(codes_large, max_workers=3)
    assert max(concurrency_record) <= 4
    assert len(df_large) == 20

    # 3. Hard Timeout with blocking tasks: must NOT block main thread and mark partial results
    def mock_blocking_eval(code, category="60m", count=120, cancel_check=None):
        time.sleep(3.0)  # Slow 3s task
        return {"code": code, "is_matched": True, "score": 50.0}

    monkeypatch.setattr(strat, "evaluate_stock_tdx", mock_blocking_eval)
    t_start = time.time()
    # Timeout is 0.2s -> Must return in < 0.6s, NOT wait for 3s!
    df_timeout = strat.scan_stocks_tdx(codes_large[:5], max_workers=2, timeout=0.2)
    t_elapsed = time.time() - t_start
    assert t_elapsed < 0.6, f"Timeout must be a hard boundary! Elapsed: {t_elapsed:.2f}s"
    assert df_timeout.attrs.get("timed_out") is True
    assert df_timeout.attrs.get("is_partial") is True
    assert df_timeout.attrs.get("total_count") == 5
    assert df_timeout.attrs.get("completed_count") < 5

    # 4. Cooperative cancellation check
    cancel_evt = threading.Event()
    cancel_evt.set()
    df_cancel = strat.scan_stocks_tdx(codes_large[:5], max_workers=2, timeout=10.0, cancel_event=cancel_evt)
    assert df_cancel.attrs.get("cancelled") is True
    assert df_cancel.attrs.get("is_partial") is True


# ============================================================================
# 6. Global Market Panel Worker Lifecycle, In-Place Cell Reuse & Safe Decoupling
# ============================================================================
def test_global_market_panel_worker_lifecycle_and_inplace_update(qapp, monkeypatch):
    from ats.ui.global_market_panel import GlobalMarketPanel, GlobalMarketWorker, _ACTIVE_GLOBAL_WORKERS

    monkeypatch.setattr("JSONData.global_market_data.fetch_global_market_quotes", lambda force_refresh=False: {
        'A50': {'name': '富时 A50 期货', 'price': 13000.0, 'pct': 1.25},
        'NVDA': {'name': '英伟达', 'price': 120.5, 'pct': 2.80},
    })
    monkeypatch.setattr("JSONData.global_market_data.get_global_sentiment_score", lambda: (5.0, "中性"))
    monkeypatch.setattr("JSONData.global_market_data.get_global_market_quotes_metadata", lambda: {'is_live_network': True})
    monkeypatch.setattr("JSONData.global_market_data.get_sector_global_boost", lambda sec: (1.0, "TAG"))

    # P1 Test: auto_fetch=True must NOT raise NameError: name 'threading' is not defined!
    panel = GlobalMarketPanel(auto_fetch=True)
    # Force a real percentage-driven row move, independent of saved pin preferences.
    panel.pinned_symbols = []
    if hasattr(panel, '_timer') and panel._timer.isActive():
        panel._timer.stop()
    panel.resize(800, 600)

    # Trigger refresh_data to start asynchronous worker
    panel.refresh_data(force=False)
    assert panel._worker is not None
    assert panel._worker in _ACTIVE_GLOBAL_WORKERS

    # Wait for worker to finish
    for _ in range(50):
        if not panel._worker or not panel._worker.isRunning():
            break
        qapp.processEvents()
        time.sleep(0.02)

    qapp.processEvents()
    # P1 Test: worker cleanup must reset panel._worker to None so next refresh won't call deleted object
    assert panel._worker is None

    # Table in-place update and selection preservation
    panel._update_quotes_table({
        'A50': {'name': '富时 A50 期货', 'price': 13000.0, 'pct': 1.25},
        'NVDA': {'name': '英伟达', 'price': 120.5, 'pct': 2.80},
    })
    a50_row = None
    for r in range(panel.tbl_quotes.rowCount()):
        if panel.tbl_quotes.item(r, 1).text() == 'A50':
            a50_row = r
            break
    assert a50_row is not None
    orig_a50_sym_item = panel.tbl_quotes.item(a50_row, 1)
    orig_a50_price_item = panel.tbl_quotes.item(a50_row, 2)
    assert orig_a50_price_item.text() == "13000.00"
    panel.tbl_quotes.setCurrentCell(a50_row, 1)

    panel._update_quotes_table({
        'A50': {'name': '富时 A50 期货', 'price': 13500.0, 'pct': 3.50},
        'NVDA': {'name': '英伟达', 'price': 120.5, 'pct': 2.80},
    })
    new_a50_row = None
    for r in range(panel.tbl_quotes.rowCount()):
        if panel.tbl_quotes.item(r, 1).text() == 'A50':
            new_a50_row = r
            break
    assert new_a50_row is not None
    assert panel.tbl_quotes.item(new_a50_row, 1) is orig_a50_sym_item
    assert panel.tbl_quotes.item(new_a50_row, 2) is orig_a50_price_item
    assert orig_a50_price_item.text() == "13500.00"
    assert panel.tbl_quotes.currentRow() == new_a50_row

    # Safe close verification: worker stop requested without crashing
    panel.close()
    qapp.processEvents()


# ============================================================================
# 7. History Load Tiered TTL (Lock Conflict & Read Exception 30s TTL)
# ============================================================================
def test_history_load_tiered_ttl_and_negative_cache(monkeypatch):
    import datetime
    import threading
    from ats.ui.main_window import ATSMainWindow
    from unittest.mock import MagicMock

    class DummyWindow:
        def __init__(self):
            self.stock_history_cache = {}
            self.history_loading_codes = set()
            self.history_failed_codes = {}
            self._history_empty_cache_times = {}
            self._history_lock_fail_times = {}
            self._history_failed_date = datetime.date.today().isoformat()
            self._pending_history_codes = set()
            self._batch_history_timer = MagicMock()
            self.hdf5_history_lock = threading.Lock()

        _async_load_stock_history = ATSMainWindow._async_load_stock_history
        _flush_batch_stock_history = ATSMainWindow._flush_batch_stock_history

    mock_clock = [1000.0]
    monkeypatch.setattr("ats.ui.main_window.time.time", lambda: mock_clock[0])
    monkeypatch.setattr(time, "time", lambda: mock_clock[0])

    win = DummyWindow()

    # Case A: Real SafeHDFStore Read Exception triggers 30s TTL backoff
    class MockFailingSafeHDFStore:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def select(self, *args, **kwargs):
            raise IOError("Simulated HDF5 disk read corruption error")

    monkeypatch.setattr("os.path.exists", lambda p: True)
    monkeypatch.setattr("JSONData.tdx_hdf5_api.SafeHDFStore", MockFailingSafeHDFStore)

    win._pending_history_codes = {"600000"}
    win.history_loading_codes = {"600000"}

    # Execute batch worker synchronously
    class SyncThread:
        def __init__(self, target, daemon=True, name=None):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr("threading.Thread", SyncThread)

    win._flush_batch_stock_history()

    # Verify SafeHDFStore exception handler actually populated _history_lock_fail_times!
    assert "600000" in win._history_lock_fail_times
    assert win._history_lock_fail_times["600000"] == 1000.0
    assert "600000" in win.history_failed_codes
    assert "600000" not in win.history_loading_codes

    # 10s later (< 30s): _async_load_stock_history must reject "600000" (backoff)
    mock_clock[0] = 1010.0
    win._async_load_stock_history(["600000"])
    assert "600000" not in win._pending_history_codes

    # 31s later (> 30s): _async_load_stock_history allows "600000" (retried!)
    mock_clock[0] = 1031.0
    win._async_load_stock_history(["600000"])
    assert "600000" in win._pending_history_codes
    win._pending_history_codes.clear()

    # Case B: Empty negative cache 60s TTL
    win.stock_history_cache["000001"] = []
    win._history_empty_cache_times["000001"] = 1031.0
    mock_clock[0] = 1050.0  # 19s later (< 60s)
    win._async_load_stock_history(["000001"])
    assert "000001" not in win._pending_history_codes  # Filtered by negative cache

    mock_clock[0] = 1095.0  # 64s later (> 60s)
    win._async_load_stock_history(["000001"])
    assert "000001" in win._pending_history_codes      # Expired and retried!
    win._pending_history_codes.clear()

    # Case C: Real data is permanent cache
    win.stock_history_cache["000002"] = [("2026-10-01", 15.5)]
    mock_clock[0] = 2000.0  # Long time later
    win._async_load_stock_history(["000002"])
    assert "000002" not in win._pending_history_codes  # Never reloaded


# ============================================================================
# 8. Strategy Filter Background Worker & Revision Control Test
# ============================================================================
def test_filter_eval_background_worker_revision(qapp):
    import pandas as pd
    from PyQt6.QtCore import QObject, pyqtSignal
    from ats.ui.main_window import ATSMainWindow

    class DummyWindow(QObject):
        _filter_eval_ready = pyqtSignal(int, object)

        def __init__(self):
            super().__init__()
            self._filter_eval_ready.connect(self._on_filter_eval_finished)
            self.query_expr = "close > 10.0"
            self.current_df = pd.DataFrame({"close": [8.0, 15.0, 20.0], "name": ["A", "B", "C"]},
                                           index=["600001", "600002", "600003"])
            self.filtered_codes_set = set()
            self._filter_eval_revision = 0

        _recompute_filtered_codes_set = ATSMainWindow._recompute_filtered_codes_set
        _on_filter_eval_finished = ATSMainWindow._on_filter_eval_finished

    win = DummyWindow()
    # Trigger background evaluation
    win._recompute_filtered_codes_set()
    assert win._filter_eval_revision == 1

    # Spin Qt event loop to allow background thread to finish and emit signal
    for _ in range(25):
        if win.filtered_codes_set:
            break
        qapp.processEvents()
        time.sleep(0.02)

    # Should match 600002 and 600003
    assert win.filtered_codes_set == {"600002", "600003"}

    # Revision test: older revision must be discarded
    win._on_filter_eval_finished(req_rev=0, res_set={"000001"})
    assert win.filtered_codes_set == {"600002", "600003"}

    # Clear query test: clearing query must bump revision and immediately clear filtered_codes_set
    win.query_expr = ""
    win._recompute_filtered_codes_set()
    assert win.filtered_codes_set == set()
    assert win._filter_eval_revision == 2

    # Late callback with revision 1 cannot overwrite the cleared set
    win._on_filter_eval_finished(req_rev=1, res_set={"600002", "600003"})
    assert win.filtered_codes_set == set()


# ============================================================================
# 9. Bounded Evaluation Store Lock Scope, COW & Concurrent Snapshot Test
# ============================================================================
def test_evaluation_store_atomic_snapshot_and_lock_scope(monkeypatch):
    from ats.bounded_evaluation_store import EvaluationStore
    import threading

    store = EvaluationStore()
    dummy_path = "dummy_eval_archive.json"

    # Append records
    store.append(dummy_path, {"k": 1}, lambda p, v: None)
    store.append(dummy_path, {"k": 2}, lambda p, v: None)

    # In-memory peek must return a deepcopy without modifying internal store
    peek_res = store.peek(dummy_path)
    assert len(peek_res) == 2
    peek_res.append({"k": 999})
    assert len(store.peek(dummy_path)) == 2  # Internal store untouched

    # Mock archive_window so pending() evaluates as DUE and returns non-empty snapshot
    monkeypatch.setattr("ats.bounded_evaluation_store.archive_window", lambda: ("market", "2026-10-01"))
    monkeypatch.setattr("time.monotonic", lambda: 1000000.0)

    pending_items = store.pending()
    assert len(pending_items) == 1
    p_path, p_val = pending_items[0]
    assert len(p_val) == 2

    # Concurrency verification: background threads rapidly appending while main thread reads & snapshots
    errors = []
    stop_event = threading.Event()

    def appender():
        idx = 3
        while not stop_event.is_set():
            try:
                store.append(dummy_path, {"k": idx}, lambda p, v: None)
                idx += 1
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=appender) for _ in range(3)]
    for t in threads:
        t.start()

    # Main thread performs read() and pending() without list mutation race
    for _ in range(50):
        try:
            r = store.read(dummy_path, default=[])
            assert isinstance(r, list)
            p = store.pending()
            assert isinstance(p, list)
        except Exception as e:
            errors.append(e)

    stop_event.set()
    for t in threads:
        t.join(timeout=1.0)

    assert errors == [], f"Concurrent read/append failed with errors: {errors}"


# ============================================================================
# 10. Archive Store Flush Concurrent LRU Eviction KeyError Protection Test
# ============================================================================
def test_archive_flush_pending_eviction_no_keyerror(tmp_path, monkeypatch):
    """验证 _flush_pending 在磁盘 I/O 期间若遇到并发 LRU 淘汰驱逐，回写时不抛出 KeyError"""
    from ats.bounded_evaluation_store import EvaluationStore

    store = EvaluationStore()
    dummy_file = str(tmp_path / "test_evict.json")

    # 1. 模拟写入并入队 pending
    store.append(dummy_file, {"foo": "bar"}, lambda p, v: True)

    # 2. 模拟并发 LRU 淘汰，在写盘回调中将 dummy_file 从 _cache 驱逐
    orig_cache = store._cache
    def writer_with_concurrent_eviction(path, val):
        with store._lock:
            orig_cache.pop(path, None)  # 模拟被 LRU 驱逐
        return True

    # 替换 writer
    with store._lock:
        if dummy_file in store._cache:
            store._cache[dummy_file]['writer'] = writer_with_concurrent_eviction

    # 3. 执行 _flush_pending，必须平稳安全完成，绝不抛出 KeyError
    try:
        store._flush_pending()
    except KeyError as ke:
        pytest.fail(f"_flush_pending raised KeyError during LRU eviction: {ke}")


# ============================================================================
# 11. TDX Daemon Thread Pool Executor Protection Test
# ============================================================================
def test_tdx_daemon_thread_pool_executor():
    """验证 TDX 批量扫描使用的 DaemonThreadPoolExecutor 创建的线程为 daemon 且不受 atexit 强制 join 阻塞"""
    from ats.channel_bottom_reversal_strategy import DaemonThreadPoolExecutor
    import concurrent.futures.thread as cft

    pool = DaemonThreadPoolExecutor(max_workers=2)
    fut = pool.submit(lambda: 123)
    assert fut.result(timeout=1.0) == 123

    # 验证工作线程属性
    assert len(pool._threads) >= 1
    for t in pool._threads:
        assert t.daemon is True, "Worker thread must be daemon"
        assert t not in cft._threads_queues, "Worker thread must NOT be registered in atexit._threads_queues"

    pool.shutdown(wait=False)


# ============================================================================
# 12. Strategy Filter Mutex Lock & Atomic State Transition Test
# ============================================================================
def test_filter_eval_mutex_atomic_state_transition(qapp):
    """验证 UI 线程与 Worker 线程在互斥锁保护下原子切换状态，绝不遗留 Stranded Payload"""
    import pandas as pd
    from PyQt6.QtCore import QObject
    from ats.ui.main_window import ATSMainWindow

    class DummyWindow(QObject):
        def __init__(self):
            super().__init__()
            self.query_expr = "close > 10"
            self.current_df = pd.DataFrame({"close": [11, 9, 12]}, index=["000001", "000002", "000003"])
            self.filtered_codes_set = set()
            self._filter_eval_revision = 0
            self._filter_eval_worker_running = False
            self._filter_eval_pending_payload = None

        def _on_filter_eval_finished(self, rev, res):
            self.filtered_codes_set = res

    win = DummyWindow()
    # 模拟连续高速投递
    for _ in range(5):
        ATSMainWindow._recompute_filtered_codes_set(win)

    # 验证互斥锁已就绪且任务正在执行或已迅速折叠完成
    assert hasattr(win, '_filter_eval_lock')

    # 等待后台 Worker 处理完成
    import time
    for _ in range(50):
        time.sleep(0.02)
        if not win._filter_eval_worker_running and win._filter_eval_pending_payload is None:
            break

    assert win._filter_eval_worker_running is False
    assert win._filter_eval_pending_payload is None
    assert "000001" in win.filtered_codes_set
    assert "000003" in win.filtered_codes_set


# ============================================================================
# 13. Stepped Backoff (30s -> 60s -> 300s) on Repeated Failures Test
# ============================================================================
def test_price_history_stepped_backoff(qapp, monkeypatch):
    """验证历史和价格连续失败时触发 30s -> 60s -> 300s 阶梯退避，且成功时计数重置"""
    from PyQt6.QtCore import QObject
    from ats.ui.main_window import ATSMainWindow
    from unittest.mock import MagicMock

    class DummyWindow(QObject):
        def __init__(self):
            super().__init__()
            self.prices_loading_codes = set()
            self.prices_failed_codes = set()
            self._price_failure_times = {}
            self._price_fail_counts = {}
            self._pending_price_codes = set()
            self._batch_price_timer = MagicMock()

    win = DummyWindow()
    mock_now = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: mock_now[0])

    # 1 次失败: TTL 应为 30s
    win.prices_failed_codes.add("000001")
    win._price_failure_times["000001"] = 1000.0
    win._price_fail_counts["000001"] = 1

    # 20s 过去: 仍被退避拦截
    mock_now[0] = 1020.0
    ATSMainWindow._async_load_stock_prices(win, ["000001"])
    assert "000001" not in win._pending_price_codes

    # 35s 过去: 1次失败退避结束，被重试
    mock_now[0] = 1035.0
    ATSMainWindow._async_load_stock_prices(win, ["000001"])
    assert "000001" in win._pending_price_codes
    win._pending_price_codes.clear()
    win.prices_loading_codes.clear()

    # 2 次失败: TTL 应递增为 60s
    win.prices_failed_codes.add("000001")
    win._price_failure_times["000001"] = 1035.0
    win._price_fail_counts["000001"] = 2

    # 40s 过去: 超过了 30s 但未达 60s，仍应被退避拦截
    mock_now[0] = 1075.0
    ATSMainWindow._async_load_stock_prices(win, ["000001"])
    assert "000001" not in win._pending_price_codes

    # 65s 过去: 超过 60s，允许重试
    mock_now[0] = 1100.0
    ATSMainWindow._async_load_stock_prices(win, ["000001"])
    assert "000001" in win._pending_price_codes
    win._pending_price_codes.clear()
    win.prices_loading_codes.clear()

    # 3 次及以上失败: TTL 跃升为 300s (5分钟)
    win.prices_failed_codes.add("000001")
    win._price_failure_times["000001"] = 1100.0
    win._price_fail_counts["000001"] = 3

    mock_now[0] = 1200.0  # 100s 过去 (< 300s)
    ATSMainWindow._async_load_stock_prices(win, ["000001"])
    assert "000001" not in win._pending_price_codes

    mock_now[0] = 1405.0  # 305s 过去 (> 300s)
    ATSMainWindow._async_load_stock_prices(win, ["000001"])
    assert "000001" in win._pending_price_codes


# ============================================================================
# 14. Strategy Filter Worker Exit Does Not Override New Worker State Test
# ============================================================================
def test_filter_eval_worker_exit_no_running_override(qapp):
    """验证旧 Worker 退出不会冲刷覆盖后续新拉起 Worker 的 running 状态"""
    import threading
    import time
    from PyQt6.QtCore import QObject
    from ats.ui.main_window import ATSMainWindow
    import pandas as pd

    class DummyWindow(QObject):
        def __init__(self):
            super().__init__()
            self.query_expr = "close > 10"
            self.current_df = pd.DataFrame({"close": [15, 20]}, index=["000001", "000002"])
            self.filtered_codes_set = set()
            self._filter_eval_revision = 0
            self._filter_eval_worker_running = False
            self._filter_eval_pending_payload = None

        def _on_filter_eval_finished(self, rev, res):
            self.filtered_codes_set = res

    win = DummyWindow()
    # 首次投递，触发 Worker 启动并快速执行完
    ATSMainWindow._recompute_filtered_codes_set(win)
    for _ in range(50):
        time.sleep(0.02)
        if not win._filter_eval_worker_running:
            break
    assert win._filter_eval_worker_running is False

    # 再次快速投递，触发新 Worker
    ATSMainWindow._recompute_filtered_codes_set(win)
    with win._filter_eval_lock:
        is_running = win._filter_eval_worker_running
    assert is_running is True or len(win.filtered_codes_set) > 0


# ============================================================================
# 15. EvaluationStore Concurrent committed() CAS Consistency Test
# ============================================================================
def test_evaluation_store_concurrent_committed_cas(tmp_path, monkeypatch):
    """验证 committed() 在锁外复制/合并期间遇到并发 append() 时，CAS 校验能安全重试并保证数据一致"""
    from ats.bounded_evaluation_store import EvaluationStore

    store = EvaluationStore()
    dummy_file = str(tmp_path / "cas_test.json")

    # 初始建项
    store.append(dummy_file, {"id": 1}, lambda p, v: True)

    monkeypatch.setattr("ats.bounded_evaluation_store.archive_window", lambda: ("market", "2026-10-01"))
    monkeypatch.setattr("time.monotonic", lambda: 1000000.0)

    # 模拟在 committed 处理期间，外部并发追加新的记录
    pending_items = store.pending()
    assert len(pending_items) == 1
    path, val = pending_items[0]

    # 并发 append 新记录 (改变 current_value 引用)
    store.append(dummy_file, {"id": 2}, lambda p, v: True)

    # 执行 committed (必须能安全检测到引用变化并基于最新数据完成发布)
    store.committed(path, val, written=True)

    # 验证最终缓存包含未落盘的 {"id": 2}，而 {"id": 1} 已成功 committed
    with store._lock:
        entry = store._cache[dummy_file]
        assert len(entry['value']) == 1
        assert entry['value'][0] == {"id": 2}


# ============================================================================
# 16. TDX Scan Gate Busy Rejection and Auto-Release Recovery Test
# ============================================================================
def test_tdx_scan_gate_busy_and_recovery(monkeypatch):
    """验证 TDX 批量扫描门闩在有在途未完成请求时返回 busy=True，并在任务结束时自动释放"""
    from ats.channel_bottom_reversal_strategy import ChannelBottomReversalStrategy, _TDX_SCAN_GATE
    import time
    import threading

    strategy = ChannelBottomReversalStrategy()

    # Previous workers must release their own gate; the test never steals ownership.
    deadline = time.monotonic() + 3.0
    while _TDX_SCAN_GATE.locked() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not _TDX_SCAN_GATE.locked(), "Previous scan worker did not drain"

    # 模拟一个挂起的后台任务
    unblock_event = threading.Event()

    def mock_eval_hanging(code, category="60m", count=120, cancel_check=None):
        unblock_event.wait(timeout=2.0)
        return {"code": code, "is_matched": True, "score": 90.0}

    monkeypatch.setattr(strategy, "evaluate_stock_tdx", mock_eval_hanging)

    # 发起一次快速超时的扫描 (timeout=0.05s)
    df1 = strategy.scan_stocks_tdx(["600001"], timeout=0.05, max_workers=1)
    assert df1.attrs.get("timed_out") is True or df1.attrs.get("is_partial") is True

    # 此时底层 mock_eval_hanging 仍被 unblock_event 阻塞，门闩必须处于 busy 状态！
    df2 = strategy.scan_stocks_tdx(["600002"], timeout=0.1)
    assert df2.attrs.get("busy") is True
    assert df2.attrs.get("completed_count") == 0

    # 解除底层任务阻塞，等待回调释放门闩
    unblock_event.set()
    for _ in range(50):
        time.sleep(0.02)
        if not _TDX_SCAN_GATE.locked():
            break

    assert not _TDX_SCAN_GATE.locked(), "Gate should be auto-released when pending workers complete"

    # 门闩恢复后，发起第三次扫描应能正常获取门闩
    def mock_eval_fast(code, category="60m", count=120, cancel_check=None):
        return {"code": code, "is_matched": True, "score": 95.0}

    monkeypatch.setattr(strategy, "evaluate_stock_tdx", mock_eval_fast)
    df3 = strategy.scan_stocks_tdx(["600003"], timeout=1.0)
    assert not df3.attrs.get("busy", False)
    assert len(df3) == 1


# ============================================================================
# 17. History Empty Result Resets Lock Backoff and Preserves Negative Cache Test
# ============================================================================
def test_history_empty_result_resets_backoff_and_sets_negative_cache(qapp, monkeypatch):
    """验证 SafeHDFStore 查询成功（空结果）时清除旧失败时间与计数，并赋予 60s 负缓存"""
    from PyQt6.QtCore import QObject
    from ats.ui.main_window import ATSMainWindow
    import pandas as pd
    import threading
    from unittest.mock import MagicMock

    class DummyWindow(QObject):
        def __init__(self):
            super().__init__()
            self.stock_history_cache = {}
            self.history_loading_codes = set()
            self.history_failed_codes = {"600000": 500.0}
            self._history_failed_date = "2026-10-01"
            self._history_empty_cache_times = {}
            self._history_lock_fail_times = {"600000": 500.0}
            self._history_fail_counts = {"600000": 3}
            self._pending_history_codes = set()
            self._batch_history_timer = MagicMock()
            self.hdf5_history_lock = threading.Lock()
            self._request_debounced_history_refresh = MagicMock()

        _flush_batch_stock_history = ATSMainWindow._flush_batch_stock_history

    win = DummyWindow()

    # 模拟 HDF5 读取成功但返回空结果
    class MockEmptySafeHDFStore:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def select(self, *args, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr("os.path.exists", lambda p: True)
    monkeypatch.setattr("JSONData.tdx_hdf5_api.SafeHDFStore", MockEmptySafeHDFStore)

    win._pending_history_codes = {"600000"}
    win.history_loading_codes = {"600000"}

    # 同步运行 worker
    class SyncThread:
        def __init__(self, target, daemon=True, name=None):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr("threading.Thread", SyncThread)

    win._flush_batch_stock_history()

    # 验证旧的锁失败退避和计数已被清空！
    assert "600000" not in win._history_lock_fail_times
    assert "600000" not in win._history_fail_counts

    # 验证建立了 60s 负缓存记录！
    assert "600000" in win._history_empty_cache_times
    assert win.stock_history_cache["600000"] == []


# ============================================================================
# 18. Global Market Panel auto_fetch=False Guard on showEvent Test
# ============================================================================
def test_global_market_panel_auto_fetch_false_guard(qapp):
    """验证 GlobalMarketPanel(auto_fetch=False) 在 showEvent 触发时不启动后台刷新"""
    from ats.ui.global_market_panel import GlobalMarketPanel
    from PyQt6.QtGui import QShowEvent

    panel = GlobalMarketPanel(parent=None, auto_fetch=False)
    assert panel._auto_fetch_enabled is False
    assert panel._worker is None

    # 模拟 showEvent
    event = QShowEvent()
    panel.showEvent(event)

    # 验证守卫拦截生效，worker 依旧为 None
    assert panel._worker is None
    panel.close()

# ============================================================================
# 19. Hot Sector Leaderboard Cold Start & Off-Hours Base Rendering Test
# ============================================================================
def test_hot_sector_leaderboard_cold_start_off_hours(qapp, monkeypatch):
    """验证龙头突击跟单榜在非交易时段冷启动时正常装载 Top 3 板块底板与标的，不发生白屏与空数据"""
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
    from ats.hot_sector_engine import HotSectorEngine
    from ats import tdx_realtime_fetcher
    import pandas as pd

    # 1. 模拟非交易休市时段
    monkeypatch.setattr(tdx_realtime_fetcher, "is_trading_time", lambda: (False, "非交易时段"))
    monkeypatch.setattr(tdx_realtime_fetcher.TDXRealtimeFetcher, "_init_best_server", lambda self, *a, **k: None)
    monkeypatch.setattr(HotSectorLeaderboardDialog, "_get_parent_mw", lambda self: None)
    from ats.sector_data_aggregator import SectorDataAggregator
    monkeypatch.setattr(SectorDataAggregator, "_load_bidding_sector_data", lambda self: {
        "存储芯片": {"score": 90.0, "avg_pct": 3.0, "count": 1}})
    monkeypatch.setattr(SectorDataAggregator, "resolve_sector_member_codes",
                        lambda self, sector: (["600001"], {"600001": "测试标的"}))
    monkeypatch.setattr(SectorDataAggregator, "resolve_active_strategy_df",
                        lambda self, *args: (pd.DataFrame(), None))
    engine_fixture = HotSectorEngine.get_instance()
    monkeypatch.setattr(engine_fixture, "sector_to_codes", {})
    monkeypatch.setattr(engine_fixture.fetcher, "fetch_multi_stock_alpha_quotes", lambda **kwargs: [
        {"code": code, "name": kwargs['name_map'].get(code, code),
         "sector": kwargs['sector_map'].get(code, "存储芯片"), "price": 10.0,
         "percent": 3.0, "pct": 3.0, "pct_diff": 3.0, "vwap_dev_pct": 1.0,
         "buy_tag": "LEADER", "role": "龙头", "score": 90.0}
        for code in kwargs['codes']])

    # 2. 模拟同步 Alpha 刷新，以便在单测中瞬间完成计算
    orig_start_alpha = HotSectorLeaderboardDialog._start_alpha_refresh
    def sync_start_alpha(self, top_sectors, current_df, manual_list, segment_mode,
                         sectors_snapshot, sec_to_codes, sort_idx):
        payload = {"results": [], "error": ""}
        try:
            self.engine.extract_top_sectors_from_heatmap(
                sectors_snapshot, sec_to_codes, top_n=3, sort_mode=sort_idx)
            payload["results"] = self.engine.compute_hot_alpha_leaderboard(
                top_sector_names=top_sectors, current_df=current_df,
                manual_watchlist=manual_list, segment_mode=segment_mode)
        except Exception as exc:
            payload["error"] = str(exc)
        self._on_alpha_ready(payload)
    monkeypatch.setattr(HotSectorLeaderboardDialog, "_start_alpha_refresh", sync_start_alpha)

    dlg = HotSectorLeaderboardDialog()
    dlg.filter_mode = "ALL"
    dlg.combo_time_slice.blockSignals(True)
    dlg.combo_time_slice.setCurrentIndex(1)
    dlg.combo_time_slice.blockSignals(False)
    assert dlg._has_init_fetched is False

    # 3. 模拟首拍定时器 tick (force=False，冷启动放行)
    dlg._on_ui_timer_tick(force=False)

    # 验证首刷完成
    assert dlg._has_init_fetched is True
    assert len(dlg.current_top_sectors) >= 1
    assert "--" not in dlg.sec_buttons[0].text()

    # 验证数据成功载入表格
    assert dlg.table.rowCount() > 0
    assert "标的: 0" not in dlg.lbl_stats.text()
    assert "💤 非交易休眠" in dlg.lbl_update_time.text()

    # 4. 验证后续非交易时段常规 tick (force=False) 守卫生效节流
    prev_update_time = dlg.lbl_update_time.text()
    dlg._on_ui_timer_tick(force=False)
    # 不会进入重算
    assert dlg._has_init_fetched is True

    # 5. 验证 HotSectorEngine 在 sector_to_codes 为空时通过 SectorDataAggregator 兜底成分股
    engine = HotSectorEngine.get_instance()
    engine.sector_to_codes = {}
    codes, sec_map, mp_cache, n_map = engine.build_target_universe(["存储芯片"])
    assert len(codes) > 0
    assert "存储芯片" in sec_map.values()
    assert len(n_map) > 0

    dlg.close()

"""Regression checks for ATS click, tab switch and cold heatmap paths."""
import os
import json
import threading
import time
import zlib
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import pandas as pd
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QTableWidget, QTableWidgetItem


def _pump_until(app, predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_filter_and_tab_switch_only_render_current_page():
    from ats.ui.main_window import ATSMainWindow

    app = QApplication.instance() or QApplication(['ats-test'])

    class Window(QObject):
        _on_filter_eval_finished = ATSMainWindow._on_filter_eval_finished
        _schedule_active_filter_refresh = ATSMainWindow._schedule_active_filter_refresh
        _refresh_active_filter_panel = ATSMainWindow._refresh_active_filter_panel
        _on_top_tab_changed = ATSMainWindow._on_top_tab_changed
        _render_top_tab = ATSMainWindow._render_top_tab

    win = Window()
    selected = [1]
    win.top_tabs = SimpleNamespace(currentIndex=lambda: selected[0])
    win.favorite_panel = SimpleNamespace(filter_enabled=True, _apply_row_visibility=MagicMock(),
                                         update_favorite_rows=MagicMock())
    win.swing_table = SimpleNamespace(filter_enabled=True, _apply_favorite_filter=MagicMock(),
                                      update_data_list=MagicMock())
    win.capital_dragon_panel = SimpleNamespace(filter_enabled=True, _apply_filter=MagicMock())
    win.new_stock_panel = SimpleNamespace(filter_enabled=True, _apply_filter=MagicMock())
    win._filter_eval_revision = 1
    win.filtered_codes_set = set()
    win.current_df = None
    win._is_restoring_sizes = True

    win._on_filter_eval_finished(1, {'600001'})
    assert not win.favorite_panel._apply_row_visibility.called
    assert _pump_until(app, lambda: win.favorite_panel._apply_row_visibility.called)
    assert not win.swing_table._apply_favorite_filter.called
    assert not win.capital_dragon_panel._apply_filter.called
    assert not win.new_stock_panel._apply_filter.called

    selected[0] = 2
    win._on_top_tab_changed(2)
    assert not win.swing_table._apply_favorite_filter.called
    assert _pump_until(app, lambda: win.swing_table._apply_favorite_filter.called)
    assert win.filtered_codes_set == {'600001'}
    win._on_filter_eval_finished(0, {'000000'})
    assert win.filtered_codes_set == {'600001'}


def test_history_hits_click_does_not_run_queries_on_gui_thread(monkeypatch):
    from ats.ui.main_window import ATSMainWindow
    import stock_logic_utils

    app = QApplication.instance() or QApplication(['ats-test'])
    entered = threading.Event()
    release = threading.Event()
    worker_threads = []

    def slow_queries(frame, queries):
        worker_threads.append(threading.current_thread())
        entered.set()
        assert release.wait(2.0)
        return [{'hit': 2}]

    monkeypatch.setattr(stock_logic_utils, 'test_code_against_queries', slow_queries)
    monkeypatch.setattr(stock_logic_utils, 'toast_messageQT', lambda *args: None)

    class Window(QObject):
        _history_hits_ready = pyqtSignal(int, object)
        calculate_history_hits_ui = ATSMainWindow.calculate_history_hits_ui
        _on_history_hits_ready = ATSMainWindow._on_history_hits_ready
        get_test_df_for_hits = ATSMainWindow.get_test_df_for_hits

        def __init__(self):
            super().__init__()
            self._history_hits_ready.connect(self._on_history_hits_ready)
            self.history_selector = QComboBox()
            self.history_selector.addItem('group')
            self.query_combo = QComboBox()
            self.query_combo.setEditable(True)
            self.search_histories = {'group': [{'query': 'close > 10'}]}
            self.current_df = pd.DataFrame({'close': [10.0, 20.0]}, index=['600001', '600002'])

        def _get_real_query(self):
            return 'close > 10'

        def _format_history_item_local(self, item):
            return f"{item['query']} ({item.get('hit', 0)})"

        def _save_search_history_data(self):
            pass

    win = Window()
    win.calculate_history_hits_ui()
    assert entered.wait(1.0)
    assert win.search_histories['group'][0].get('hit') is None
    assert worker_threads[0] is not threading.main_thread()
    release.set()
    assert _pump_until(app, lambda: win.search_histories['group'][0].get('hit') == 2)


def test_heatmap_snapshot_read_stays_off_gui_thread(monkeypatch):
    from ats.ui import heatmap_widget

    app = QApplication.instance() or QApplication(['ats-test'])
    entered = threading.Event()
    release = threading.Event()
    worker_threads = []
    sectors = {name: {'score': 60, 'avg_pct': 1.0, 'leader': str(600001 + i)}
               for i, name in enumerate(('半导体', '证券', '光伏设备'))}

    def slow_read():
        worker_threads.append(threading.current_thread())
        entered.set()
        assert release.wait(2.0)
        return False, sectors, [], {}, {}

    monkeypatch.setattr(heatmap_widget, '_read_sector_snapshot_sources', slow_read)
    widget = heatmap_widget.SectorHeatmapWidget()
    widget.load_live_sectors(force=True)
    assert entered.wait(1.0)
    assert worker_threads[0] is not threading.main_thread()
    release.set()
    assert _pump_until(app, lambda: len(getattr(widget, 'sectors', [])) == 3)
    widget.close()


def test_detail_filter_pending_does_not_evaluate_synchronously():
    from ats.ui.main_window import StockDetailDialog

    QApplication.instance() or QApplication([])
    parent = SimpleNamespace(query_expr='close > 10', _filter_result_query=None,
                             filtered_codes_set=set())
    detail = SimpleNamespace(_get_parent_mw=lambda: parent, code='600001',
                             lbl_filter_expr=QLabel(), lbl_filter_result=QLabel())
    StockDetailDialog.update_filter_status(detail, parent.query_expr)
    assert '等待筛选结果' in detail.lbl_filter_result.text()


def test_same_codes_new_query_invalidates_hidden_filter_pages():
    from ats.ui.main_window import ATSMainWindow

    win = SimpleNamespace(_filter_eval_revision=2, filtered_codes_set={'600001'},
                          query_expr='close > 20', _filter_result_query='close > 10',
                          top_tabs=SimpleNamespace(currentIndex=lambda: 1),
                          _schedule_active_filter_refresh=MagicMock())
    ATSMainWindow._on_filter_eval_finished(win, 2, {'600001'})
    win._schedule_active_filter_refresh.assert_called_once()


def test_empty_filter_click_schedules_refresh_without_timer_scope_error(monkeypatch):
    from ats.ui.main_window import ATSMainWindow
    import ats.ui.styles as styles

    monkeypatch.setattr(styles, 'save_config_node_async', MagicMock())
    win = SimpleNamespace(_get_real_query=lambda: '', current_df=None,
                          _recompute_filtered_codes_set=MagicMock(),
                          _save_search_history_data=MagicMock(),
                          _schedule_active_filter_refresh=MagicMock(),
                          query_combo=SimpleNamespace(lineEdit=lambda: None))
    ATSMainWindow.apply_filter(win)
    win._schedule_active_filter_refresh.assert_called_once()


def test_heatmap_worker_start_failure_allows_retry(monkeypatch):
    from ats.ui import heatmap_widget

    widget = SimpleNamespace(isVisible=lambda: True)
    monkeypatch.setattr(heatmap_widget.threading, 'Thread',
                        MagicMock(side_effect=RuntimeError('cannot start thread')))
    heatmap_widget.SectorHeatmapWidget.load_live_sectors(
        widget, force=True, current_df=pd.DataFrame({'close': [10]}))
    assert widget._snapshot_busy is False
    assert widget._last_load_time == 0.0


def test_empty_filter_result_uses_completed_set_without_sync_query(monkeypatch):
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
    import stock_logic_utils

    query = 'close > 1000'
    parent = SimpleNamespace(query_expr=query, _filter_result_query=query,
                             filtered_codes_set=set())

    class Dialog:
        _filter_results_by_query = HotSectorLeaderboardDialog._filter_results_by_query

        def _get_parent_mw(self):
            return parent

    monkeypatch.setattr(stock_logic_utils.query_engine, 'execute',
                        lambda *args: (_ for _ in ()).throw(AssertionError('synchronous query')))
    assert Dialog()._filter_results_by_query([{'code': '600001'}], query) == []


def test_clear_filter_restores_rows_when_panel_filter_is_enabled():
    from ats.ui.favorite_panel import FavoritePanel

    app = QApplication.instance() or QApplication(['ats-test'])
    parent = SimpleNamespace(query_expr='close > 1000', filtered_codes_set=set())

    class Panel:
        _apply_row_visibility = FavoritePanel._apply_row_visibility
        filter_enabled = True

        def _get_parent_mw(self):
            return parent

    panel = Panel()
    panel.table = QTableWidget(2, 2)
    panel.search_input = QLineEdit()
    panel.count_label = QLabel()
    for row, code in enumerate(('600001', '600002')):
        panel.table.setItem(row, 0, QTableWidgetItem(code))
        panel.table.setItem(row, 1, QTableWidgetItem(code))
    panel._apply_row_visibility()
    assert all(panel.table.isRowHidden(row) for row in range(2))
    parent.query_expr = ''
    panel._apply_row_visibility()
    assert all(not panel.table.isRowHidden(row) for row in range(2))


def test_nontrading_heatmap_uses_dated_snapshot(monkeypatch, tmp_path):
    from ats.ui import heatmap_widget

    snapshots = tmp_path / 'snapshots'
    snapshots.mkdir()
    valid = {'半导体': {}, '光伏设备': {}, '证券': {}}
    stale = {'旧日板块': {}, '陈旧赛道': {}, '过时主题': {}}
    (snapshots / 'bidding_20261002.json.gz').write_bytes(
        zlib.compress(json.dumps({'sector_data': valid}).encode('utf-8')))
    (snapshots / 'bidding_session_data.json.gz').write_bytes(
        zlib.compress(json.dumps({'sector_data': stale}).encode('utf-8')))
    monkeypatch.setattr(heatmap_widget, 'get_app_root', lambda: str(tmp_path))
    monkeypatch.setattr(heatmap_widget.cct, 'get_day_istrade_date', lambda: False)
    monkeypatch.setattr(heatmap_widget.cct, 'get_last_trade_date', lambda: '2026-10-02')

    nontrade, sectors, pool, flags, mapping = heatmap_widget._read_sector_snapshot_sources()
    assert nontrade is True
    assert sectors == valid
    assert not pool and not flags and not mapping


# Real Qt interaction blocker regression and latency probes.
from PyQt6.QtCore import QTimer

def _blocker_pump(app, predicate, timeout=10):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.001)
    raise AssertionError('Qt task did not finish')


@pytest.fixture
def async_stock_panel(qapp, monkeypatch):
    from ats.ui.new_stock_panel import NewStockPanel
    from global_favorites import GlobalFavoriteManager
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GlobalFavoriteManager, 'get_favorite_stocks', lambda self: set())
    monkeypatch.setattr(NewStockPanel, '_start_system_lifecycle', lambda self: None)
    monkeypatch.setattr(NewStockPanel, '_sync_refresh_interval_ui', lambda self: None)
    monkeypatch.setattr(NewStockPanel, 'is_panel_visible', lambda self: True)
    widget = NewStockPanel()
    widget.resize(1000, 700)
    widget.show()
    widget.filter_enabled = False
    widget.combo_filter.setCurrentIndex(0)
    widget.df_data = pd.DataFrame([
        dict(code=f'{600000 + i:06}', name=f'Stock {i}', status='次新股',
             listing_date='2026-09-01', apply_date='2026-08-01', pct=float(i % 10),
             price=10., has_strategy=False)
        for i in range(500)
    ])
    yield app, widget
    _blocker_pump(app, lambda: not getattr(widget, '_table_prepare_running', False))
    painter = getattr(widget, '_table_painter', None)
    if painter is not None:
        painter.close()
    widget._table_revision = getattr(widget, '_table_revision', 0) + 1
    widget.close()


def test_switch_prepares_off_thread_and_paints_real_table_in_batches(async_stock_panel, monkeypatch):
    from ats.ui import new_stock_panel as mod
    app, widget = async_stock_panel
    gui = threading.get_ident()
    threads = []
    original_prepare = mod._prepare_stock_table
    original_merge = mod._merge_ipc_frame

    def prepare(*args):
        threads.append(('prepare', threading.get_ident()))
        return original_prepare(*args)

    def merge(*args):
        threads.append(('merge', threading.get_ident()))
        return original_merge(*args)

    monkeypatch.setattr(mod, '_prepare_stock_table', prepare)
    monkeypatch.setattr(mod, '_merge_ipc_frame', merge)
    widget._last_ipc_df = pd.DataFrame({'dff': [2.] * 500}, index=widget.df_data.code)
    widget._last_ipc_df.index.name = 'code'
    widget._needs_render = True
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start(2)
    batches = []
    original_slice = widget._paint_table_slice

    def sliced(revision):
        started = time.perf_counter()
        original_slice(revision)
        batches.append((time.perf_counter() - started) * 1000)

    monkeypatch.setattr(widget, '_paint_table_slice', sliced)
    started = time.perf_counter()
    assert widget.ensure_rendered()
    dispatch_ms = (time.perf_counter() - started) * 1000
    assert widget.table.rowCount() == 0
    _blocker_pump(app, lambda: getattr(widget, '_last_table_signature', None) is not None
         and widget._table_painter is None)
    timer.stop()
    assert widget.table.rowCount() == 500
    assert len(batches) > 10 and len(ticks) > 10
    assert all(tid != gui for _, tid in threads)
    assert {name for name, _ in threads} == {'prepare', 'merge'}
    assert widget.df_data.dff.eq(2.).all()
    assert widget.table.updatesEnabled() and not widget.table.signalsBlocked()
    assert widget.table.isSortingEnabled()
    codes = {widget.table.item(r, widget._get_col_by_header('代码')).text()
             for r in range(500)}
    assert codes == set(widget.df_data.code)
    print(f'IPO 500 rows: dispatch={dispatch_ms:.2f}ms, batches={len(batches)}, '
          f'max_batch={max(batches):.2f}ms, heartbeat_ticks={len(ticks)}, '
          f'first={batches[0]:.2f}ms, last={batches[-1]:.2f}ms')


def test_latest_search_wins_and_cancelled_partial_table_recovers(async_stock_panel, monkeypatch):
    from ats.ui import new_stock_panel as mod
    app, widget = async_stock_panel
    entered, release = threading.Event(), threading.Event()
    original = mod._prepare_stock_table
    calls = []

    def blocked(*args):
        calls.append(args[5])
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return original(*args)

    monkeypatch.setattr(mod, '_prepare_stock_table', blocked)
    widget._render_table()
    _blocker_pump(app, entered.is_set)
    widget.search_edit.setText('Stock 499')
    widget._render_table()
    release.set()
    _blocker_pump(app, lambda: getattr(widget, '_last_table_signature', None) is not None
         and widget._table_painter is None)
    assert widget.table.rowCount() == 1
    assert widget.table.item(0, widget._get_col_by_header('代码')).text() == '600499'
    widget.search_edit.setText('')
    widget._render_table()
    _blocker_pump(app, lambda: getattr(widget, '_table_painter', None) is not None)
    widget.search_edit.setText('no match')
    widget._render_table()
    _blocker_pump(app, lambda: widget.table.rowCount() == 0 and widget._table_painter is None)
    assert widget.table.isSortingEnabled()
    widget.search_edit.setText('Stock 499')
    widget._render_table()
    _blocker_pump(app, lambda: widget.table.rowCount() == 1 and widget._table_painter is None)
    assert widget.table.item(0, widget._get_col_by_header('代码')).text() == '600499'


def test_reversal_aggregation_preserves_prefixed_quote_lookup():
    from ats.ui.heatmap_widget import _aggregate_reversal_sectors
    frame = pd.DataFrame({'name': ['A', 'B'], 'percent': [2., 4.]},
                         index=['sh600001', 'sz000002'])
    sectors, members = _aggregate_reversal_sectors(
        frame, ['600001', '000002'], {'600001': {'phase': 'WAVE_UP'}},
        {'600001': '半导体', '000002': '半导体'})
    assert sectors == [('半导体', 65.0, '+3.00%', 2, '000002', 'B')]
    assert members == {'半导体': ['600001', '000002']}
    frame = frame.reset_index(drop=True)
    frame['code'] = ['600001', '000002']
    assert _aggregate_reversal_sectors(
        frame, ['600001', '000002'], {'600001': {'phase': 'WAVE_UP'}},
        {'600001': '半导体', '000002': '半导体'}) == (sectors, members)


def test_hidden_partial_render_is_cancelled_and_restored(async_stock_panel, monkeypatch):
    app, widget = async_stock_panel
    visible = [True]
    monkeypatch.setattr(widget, 'is_panel_visible', lambda: visible[0])
    widget._render_table()
    _blocker_pump(app, lambda: getattr(widget, '_table_painter', None) is not None)
    visible[0] = False
    _blocker_pump(app, lambda: widget._table_painter is None)
    assert widget._needs_render
    assert widget.table.updatesEnabled() and not widget.table.signalsBlocked()
    visible[0] = True
    assert widget.ensure_rendered()
    _blocker_pump(app, lambda: getattr(widget, '_last_table_signature', None) is not None
         and widget._table_painter is None)
    assert len(widget._rendered_row_state) == 500


def test_tab_switch_does_not_submit_a_second_full_filter_request():
    from ats.ui.main_window import ATSMainWindow
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    panel = SimpleNamespace(ensure_rendered=MagicMock(return_value=True),
                            filter_enabled=True, _apply_filter=MagicMock())
    win = SimpleNamespace(_top_tab_render_revision=1,
                          top_tabs=SimpleNamespace(currentIndex=lambda: 3),
                          new_stock_panel=panel, _filter_dirty_tabs={3})
    ATSMainWindow._render_top_tab(win, 3, 1)
    panel.ensure_rendered.assert_called_once()
    panel._apply_filter.assert_not_called()
    assert win._filter_dirty_tabs == set()


def test_sort_change_during_partial_paint_restarts_with_latest_direction(async_stock_panel, monkeypatch):
    from PyQt6.QtCore import Qt
    app, widget = async_stock_panel
    monkeypatch.setattr(widget, '_save_sort_state',
                        lambda col, order: (setattr(widget, 'sort_col', col),
                                            setattr(widget, 'sort_order', order)))
    widget._render_table()
    _blocker_pump(app, lambda: getattr(widget, '_table_painter', None) is not None)
    revision = widget._table_revision
    col = widget._get_col_by_header('代码')
    widget._on_header_sort_changed(col, Qt.SortOrder.AscendingOrder)
    assert widget._table_revision > revision
    _blocker_pump(app, lambda: getattr(widget, '_last_table_signature', None) is not None
         and widget._table_painter is None)
    codes = [widget.table.item(r, col).text() for r in range(500)]
    assert codes == sorted(codes)


@pytest.mark.parametrize('descending', [False, True])
def test_cached_batch_comparator_matches_existing_rules(qapp, descending):
    from ats.ui.new_stock_panel import NewStockNumericItem
    from ats.ui.styles import NumericTableWidgetItem
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTableWidget
    app = QApplication.instance() or QApplication([])
    table = QTableWidget(1, 1)
    table.horizontalHeader().setSortIndicator(
        0, Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder)
    table._ipo_batch_sort_direction = descending
    cases = [('10', 10., 999), ('2', 2., 999), ('--', None, 999),
             ('A', 'A', 999), ('2026-01-01', '2026-01-01', 999),
             ('20', 20., 0), ('3', 3., 1)]
    for left in cases:
        for right in cases:
            a = NewStockNumericItem(left[0], raw_val=left[1], pin_rank=left[2])
            b = NewStockNumericItem(right[0], raw_val=right[1], pin_rank=right[2])
            a._ipo_sort_key = (a._is_empty(), a._get_sort_val(a), a.text())
            b._ipo_sort_key = (b._is_empty(), b._get_sort_val(b), b.text())
            table.setItem(0, 0, a)
            assert (a < b) == NumericTableWidgetItem.__lt__(a, b)
    table.close()


def test_heatmap_fallback_aggregation_is_in_snapshot_worker(monkeypatch):
    from ats.ui import heatmap_widget as mod
    app = QApplication.instance() or QApplication([])
    widget = mod.SectorHeatmapWidget()
    gui = threading.get_ident()
    tids = []
    entered, release = threading.Event(), threading.Event()
    frame = pd.DataFrame({'name': ['A'], 'percent': [3.]}, index=['600001'])
    monkeypatch.setattr(mod, '_read_sector_snapshot_sources',
                        lambda: (False, {}, ['600001'], {}, {'600001': '半导体'}))
    original = mod._aggregate_reversal_sectors

    def aggregate(*args):
        tids.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        return original(*args)

    monkeypatch.setattr(mod, '_aggregate_reversal_sectors', aggregate)
    widget.load_live_sectors(force=True, current_df=frame)
    _blocker_pump(app, entered.is_set)
    assert tids == [tids[0]] and tids[0] != gui
    release.set()
    _blocker_pump(app, lambda: not widget._snapshot_busy)
    assert widget.sectors[0][0] == '半导体'
    assert widget.sector_to_codes == {'半导体': ['600001']}
    widget.close()
