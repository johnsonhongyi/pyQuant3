import logging
import builtins
import os
import time

import pytest

from JSONData import tdx_hdf5_api as h5a


@pytest.mark.parametrize('codes', [None, ['600000']])
def test_history_permission_failure_keeps_original_empty_fallback(monkeypatch, codes):
    def denied(*args, **kwargs):
        raise PermissionError('history unavailable')
    monkeypatch.setattr(h5a, 'RAMDISK_KEY', 0)
    monkeypatch.setattr(h5a, 'SafeHDFStore', denied)
    result = h5a.load_hdf_db('isolated_permission_probe', code_l=codes, timelimit=False)
    assert result is None or result.empty


def lock_store(path, timeout=0.03):
    store = object.__new__(h5a.SafeHDFStore)
    store._lock = str(path)
    store._lock_acquired = False
    store.my_pid = os.getpid()
    store.lock_timeout = timeout
    store.probe_interval = 0.005
    store.start_time = time.time()
    store.log = logging.getLogger(__name__)
    return store


@pytest.mark.parametrize("busy", [False, True])
def test_live_or_busy_lock_times_out_without_removal(tmp_path, monkeypatch, busy):
    path = tmp_path / "data.lock"
    path.write_text("other-owner", encoding="utf-8")
    store = lock_store(path)
    monkeypatch.setattr(store, "_parse_lock_info", lambda: {
        "exists": True, "is_me": False, "is_busy": busy,
        "is_stale": False, "pid": 123, "is_alive": True, "elapsed": 1000,
    })
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        store._acquire_lock()
    assert time.monotonic() - started < 1
    assert path.read_text(encoding="utf-8") == "other-owner"
    assert not store._lock_acquired


def test_missing_lock_directory_fails_immediately(tmp_path):
    store = lock_store(tmp_path / "missing" / "data.lock", timeout=20)
    started = time.monotonic()
    with pytest.raises(FileNotFoundError):
        store._acquire_lock()
    assert time.monotonic() - started < 1
    assert not store._lock_acquired


def test_retry_keeps_original_deadline(tmp_path, monkeypatch):
    path = tmp_path / "data.lock"
    path.write_text("other-owner", encoding="utf-8")
    store = lock_store(path, timeout=20)
    store._open_deadline = time.monotonic() + .02
    monkeypatch.setattr(store, "_parse_lock_info", lambda: {
        "exists": True, "is_me": False, "is_busy": False,
        "is_stale": False, "pid": 123, "is_alive": True, "elapsed": 1000,
    })
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        store._acquire_lock()
    assert time.monotonic() - started < 1
    assert path.read_text(encoding="utf-8") == "other-owner"


def test_open_retry_cannot_restart_after_budget_expires(tmp_path, monkeypatch):
    attempts = []
    def fail_open(store, *args, **kwargs):
        store._handle = None
        attempts.append(time.monotonic())
        raise OSError('injected open failure')
    monkeypatch.setattr(h5a, 'BaseDir', str(tmp_path))
    monkeypatch.setattr(h5a.cct, 'get_ramdisk_path', lambda path: str(path))
    monkeypatch.setattr(h5a.SafeHDFStore, 'ensure_hdf_file', lambda store: None)
    monkeypatch.setattr(h5a.pd.HDFStore, '__init__', fail_open)
    path = tmp_path / 'data.h5'
    with pytest.raises(TimeoutError):
        h5a.SafeHDFStore(str(path), mode='r', lock_timeout=.02)
    assert len(attempts) == 1
    assert not (tmp_path / 'data.h5.lock').exists()


@pytest.mark.parametrize("error", [PermissionError, FileExistsError])
def test_lock_creation_errors_are_bounded(tmp_path, monkeypatch, error):
    store = lock_store(tmp_path / "data.lock")
    real_open = builtins.open

    def fail_lock(path, mode="r", *args, **kwargs):
        if path == store._lock and mode == "x":
            raise error("injected lock creation failure")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fail_lock)
    expected = PermissionError if error is PermissionError else TimeoutError
    started = time.monotonic()
    with pytest.raises(expected):
        store._acquire_lock()
    assert time.monotonic() - started < 1
    assert not store._lock_acquired


def test_nested_lock_survives_inner_release(tmp_path):
    path = tmp_path / "data.lock"
    outer = lock_store(path, timeout=0)
    inner = lock_store(path, timeout=0)
    try:
        assert outer._acquire_lock()
        assert inner._acquire_lock()
        inner._release_lock()
        assert path.exists()
        assert outer._lock_acquired
    finally:
        inner._release_lock()
        outer._release_lock()
    assert not path.exists()
