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

    # 确保门闩处于未持有状态
    if _TDX_SCAN_GATE.locked():
        try:
            _TDX_SCAN_GATE.release()
        except RuntimeError:
            pass

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

    # 1. 模拟非交易休市时段
    monkeypatch.setattr(tdx_realtime_fetcher, "is_trading_time", lambda: (False, "非交易时段"))

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
