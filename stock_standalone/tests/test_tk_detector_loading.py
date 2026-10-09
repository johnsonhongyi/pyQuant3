"""Single-flight cold loading, callback delivery and transient payload ownership."""
import ast
import concurrent.futures
import threading
import time
import weakref
from collections import deque
from functools import lru_cache
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Callable
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=2)
def source_tree(path):
    return ast.parse((ROOT / path).read_text(encoding='utf-8'))


def method(path, cls_name, name, **extra):
    cls = next(n for n in source_tree(path).body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = dict(threading=threading, time=time, Callable=Callable, logger=Mock(),
              get_app_root=lambda: 'unused', _build_detector_state_process=Mock(), **extra)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), ns)
    return ns[name]


def detector_owner():
    owner = SimpleNamespace(_load_lock=threading.Lock(), _loading_callbacks=[],
                            _loading_thread=None, _is_ready=False, simulation_mode=False,
                            _apply_detector_state=Mock(return_value=True))
    for name in ('ensure_data_ready_async', '_apply_and_finalize'):
        setattr(owner, name, MethodType(method('bidding_momentum_detector.py',
                                               'BiddingMomentumDetector', name), owner))
    return owner


def install_pool(monkeypatch, futures):
    pools = []
    def factory(**_kwargs):
        pool = Mock()
        pool.submit.return_value = futures[len(pools)]
        pools.append(pool)
        return pool
    monkeypatch.setattr(concurrent.futures, 'ProcessPoolExecutor', factory)
    return pools


def finish_on_background_thread(future, state):
    worker = threading.Thread(target=lambda: future.set_result(state))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_concurrent_open_requests_share_one_loader_and_receive_ready(monkeypatch):
    future = concurrent.futures.Future()
    pools = install_pool(monkeypatch, [future])
    owner = detector_owner()
    barrier = threading.Barrier(8)
    delivered = []
    def open_panel(index):
        barrier.wait(timeout=2)
        owner.ensure_data_ready_async(lambda: delivered.append((index, owner._is_ready)))
    threads = [threading.Thread(target=open_panel, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()
    owner._loading_thread.join(timeout=2)
    assert len(pools) == 1
    assert not owner._is_ready and owner._loading_in_progress
    # Completion thread has no Qt event loop; finalization must still run.
    finish_on_background_thread(future, {'tick_series': {}})
    assert sorted(delivered) == [(i, True) for i in range(8)]
    assert owner._is_ready and not owner._loading_in_progress
    assert owner._loading_callbacks == []
    pools[0].shutdown.assert_called_once_with(wait=False, cancel_futures=True)
    owner.ensure_data_ready_async(lambda: delivered.append(('warm', owner._is_ready)))
    assert delivered[-1] == ('warm', True) and len(pools) == 1


def test_future_releases_transient_payload_after_state_transfer(monkeypatch):
    class Payload:
        def __init__(self):
            self.data = bytearray(1024 * 1024)
    future = concurrent.futures.Future()
    install_pool(monkeypatch, [future])
    owner = detector_owner()
    owner.ensure_data_ready_async()
    owner._loading_thread.join(timeout=2)
    payload = Payload()
    reference = weakref.ref(payload)
    state = {'transient_payload': payload}
    del payload
    finish_on_background_thread(future, state)
    assert future.result() == {} and reference() is None


def test_callback_exception_does_not_drop_other_subscribers(monkeypatch):
    future = concurrent.futures.Future()
    install_pool(monkeypatch, [future])
    owner = detector_owner()
    bad = Mock(side_effect=RuntimeError('closed panel'))
    good = Mock()
    owner.ensure_data_ready_async(bad)
    owner.ensure_data_ready_async(good)
    owner._loading_thread.join(timeout=2)
    finish_on_background_thread(future, {})
    bad.assert_called_once()
    good.assert_called_once()
    assert owner._is_ready and owner._loading_callbacks == []


def test_loader_failure_releases_subscribers_and_allows_retry(monkeypatch):
    first, second = concurrent.futures.Future(), concurrent.futures.Future()
    pools = install_pool(monkeypatch, [first, second])
    owner = detector_owner()
    callback = Mock()
    owner.ensure_data_ready_async(callback)
    owner._loading_thread.join(timeout=2)
    first.set_exception(RuntimeError('temporary loader error'))
    assert not owner._loading_in_progress and not owner._is_ready
    assert owner._loading_callbacks == []
    callback.assert_not_called()
    owner.ensure_data_ready_async(callback)
    owner._loading_thread.join(timeout=2)
    finish_on_background_thread(second, {})
    assert len(pools) == 2 and owner._is_ready
    callback.assert_called_once()


def test_apply_failure_never_marks_detector_ready(monkeypatch):
    future = concurrent.futures.Future()
    install_pool(monkeypatch, [future])
    owner = detector_owner()
    owner._apply_detector_state.return_value = False
    callback = Mock()
    owner.ensure_data_ready_async(callback)
    owner._loading_thread.join(timeout=2)
    finish_on_background_thread(future, {})
    assert not owner._is_ready and not owner._loading_in_progress
    assert owner._loading_callbacks == []
    callback.assert_not_called()


def test_transferred_state_remains_intact_after_future_container_is_released(monkeypatch):
    import datetime
    future = concurrent.futures.Future()
    install_pool(monkeypatch, [future])
    owner = detector_owner()
    owner._lock = threading.RLock()
    owner.data_version = 0
    apply = method('bidding_momentum_detector.py', 'BiddingMomentumDetector', '_apply_detector_state',
                   datetime=datetime, get_effective_trade_date=lambda: '2026-10-09')
    owner._apply_detector_state = MethodType(apply, owner)
    ticks, snap, sectors = {'600000': object()}, {'600000': {'price': 10}}, {'bank': {'score': 8}}
    watchlist = {'600000': {'trigger_ts': 42}}
    state = dict(tick_series=ticks, global_snap_cache=snap, active_sectors=sectors,
                 daily_watchlist=watchlist, data_date='2026-10-09',
                 stock_selector_seeds={'600000': {'reason': 'seed'}}, dragon_3day_history=[])
    owner.ensure_data_ready_async()
    owner._loading_thread.join(timeout=2)
    finish_on_background_thread(future, state)
    assert future.result() == {} and owner._is_ready
    assert owner._tick_series is ticks and owner._global_snap_cache is snap
    assert owner.active_sectors is sectors and owner.daily_watchlist is watchlist
    assert owner.stock_selector_seeds == {'600000': {'reason': 'seed'}}
    assert owner.data_version == 1


def test_submit_failure_closes_pool_and_releases_single_flight_gate(monkeypatch):
    future = concurrent.futures.Future()
    pools = install_pool(monkeypatch, [future])
    factory = concurrent.futures.ProcessPoolExecutor
    def broken_pool(**kwargs):
        pool = factory(**kwargs)
        pool.submit.side_effect = RuntimeError('worker launch failed')
        return pool
    monkeypatch.setattr(concurrent.futures, 'ProcessPoolExecutor', broken_pool)
    owner = detector_owner()
    owner.ensure_data_ready_async(Mock())
    owner._loading_thread.join(timeout=2)
    assert not owner._loading_in_progress and owner._loading_callbacks == []
    pools[0].shutdown.assert_called_once_with(wait=False, cancel_futures=True)


def worker_owner(detector):
    owner = SimpleNamespace(detector=detector, _is_running=True,
                            _safe_log_info=Mock(), _safe_log_warning=Mock(), _safe_log_error=Mock())
    init = method('sector_bidding_panel.py', 'DataProcessWorker', '_background_init',
                  traceback=__import__('traceback'))
    return owner, lambda: init(owner)


def test_panel_worker_reuses_loading_detector_instead_of_reloading_snapshot():
    callbacks, subscribed = [], threading.Event()
    detector = SimpleNamespace(_loading_in_progress=True, _load_stock_selector_data=Mock())
    def ensure(on_ready_callback):
        callbacks.append(on_ready_callback)
        subscribed.set()
    detector.ensure_data_ready_async = ensure
    owner, init = worker_owner(detector)
    worker = threading.Thread(target=init)
    worker.start()
    assert subscribed.wait(timeout=1)
    callbacks.pop()()
    worker.join(timeout=1)
    assert not worker.is_alive()
    detector._load_stock_selector_data.assert_not_called()
    owner._safe_log_info.assert_called_once()


def test_worker_can_stop_while_shared_snapshot_is_loading():
    subscribed = threading.Event()
    detector = SimpleNamespace(_loading_in_progress=True,
                               ensure_data_ready_async=lambda **_kwargs: subscribed.set())
    owner, init = worker_owner(detector)
    worker = threading.Thread(target=init)
    worker.start()
    assert subscribed.wait(timeout=1)
    owner._is_running = False
    worker.join(timeout=1)
    assert not worker.is_alive()


def test_failed_restore_falls_back_to_live_processing():
    detector = SimpleNamespace(_loading_in_progress=False, ensure_data_ready_async=Mock())
    owner, init = worker_owner(detector)
    init()
    owner._safe_log_warning.assert_called_once()
    owner._safe_log_error.assert_not_called()


def test_kline_payload_is_consumed_incrementally_without_losing_bars():
    bars = [{'close': 10.0}, {'close': 11.0}]
    for name, payload_key in (('_deferred_restore_klines', 'new'),
                              ('_deferred_restore_klines_legacy', 'legacy')):
        payload = {'600000': bars, '600001': bars}
        series = {code: SimpleNamespace(klines=deque(maxlen=30)) for code in payload}
        owner = SimpleNamespace(_lock=threading.RLock(), _tick_series=series,
                                _global_snap_cache={code: {} for code in payload})
        for ts in series.values():
            ts.push_kline = ts.klines.append
        remaining_counts = []
        def decompress(data):
            remaining_counts.append(len(payload))
            return data
        restore = method('bidding_momentum_detector.py', 'BiddingMomentumDetector', name,
                         decompress_klines=decompress)
        restore(owner, payload)
        assert payload == {} and remaining_counts == [1, 0], payload_key
        assert all(list(ts.klines) == bars for ts in series.values())
        assert all(row['klines'] is bars for row in owner._global_snap_cache.values())
