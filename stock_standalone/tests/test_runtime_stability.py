from __future__ import annotations

import pickle
import struct
import threading
from unittest.mock import MagicMock, patch

import pandas as pd

from ats.ipc_bridge import IPCBridge
from JSONData import realdatajson
import popularity_resonance_gui as popularity_gui
from popularity_resonance_gui import (
    PRServiceGUI,
    _atomic_temp_path,
    _snapshot_persistence_due,
    _snapshot_write_window_open,
)
from stock_live_strategy import StockLiveStrategy


class _FrameConnection:
    def __init__(self, body):
        payload = pickle.dumps(("UPDATE_DF_DATA", body), protocol=pickle.HIGHEST_PROTOCOL)
        self._data = b"DATA" + struct.pack("!I", len(payload)) + payload

    def settimeout(self, _timeout):
        pass

    def recv(self, size):
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk

    def close(self):
        pass


def test_sina_cold_start_can_rebuild_last_trade_snapshot_on_non_trading_day(monkeypatch):
    fetched = []
    monkeypatch.setattr(
        realdatajson, "_get_dynamic_fetch_params",
        lambda *args, **kwargs: (8, (0.2, 0.6), False, 30),
    )
    monkeypatch.setattr(realdatajson.h5a, "load_hdf_db", lambda *args, **kwargs: None)
    monkeypatch.setattr(realdatajson.cct, "get_trade_date_status", lambda: False)
    monkeypatch.setattr(
        realdatajson, "_refresh_sina_Market_json",
        lambda *args, **kwargs: (fetched.append(True) or []),
    )

    assert realdatajson.get_sina_Market_json() == []
    assert fetched == [True]


def test_manual_force_does_not_write_daily_file_on_non_trading_day(monkeypatch):
    monkeypatch.setattr(popularity_gui.cct, "get_trade_date_status", lambda: False)
    with patch.object(popularity_gui.os, "makedirs", side_effect=AssertionError("must not write")):
        popularity_gui.PRServiceGUI.save_daily_resonance_csv(
            object(), {}, {}, {}, {}, [], {}, force_save=True,
        )


def test_snapshot_persistence_skips_unchanged_and_throttles_changes():
    assert not _snapshot_persistence_due("same", "same", 100.0, 500.0, force=True)
    assert not _snapshot_persistence_due("new", "old", 100.0, 399.0)
    assert _snapshot_persistence_due("new", "old", 100.0, 400.0)
    assert _snapshot_persistence_due("new", "old", 100.0, 101.0, force=True)


def test_snapshot_write_window_avoids_rehashing_during_cooldown():
    assert not _snapshot_write_window_open(100.0, 399.0)
    assert _snapshot_write_window_open(100.0, 400.0)
    assert _snapshot_write_window_open(100.0, 101.0, force=True)


def test_atomic_temp_path_is_unique_between_writer_threads():
    barrier = threading.Barrier(2)
    paths = []

    def build_path():
        barrier.wait(timeout=2.0)
        paths.append(_atomic_temp_path("snapshot.json"))

    threads = [threading.Thread(target=build_path) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2.0)

    assert all(not thread.is_alive() for thread in threads)
    assert len(set(paths)) == 2


def test_daily_persistence_skips_building_rows_during_cooldown(monkeypatch):
    owner = object.__new__(PRServiceGUI)
    owner._persistence_lock = threading.Lock()
    owner._persistence_state = {
        "daily": {"2026-09-28": {"signature": "previous", "written_at": 100.0}}
    }
    monkeypatch.setattr(popularity_gui.cct, "get_trade_date_status", lambda: True)
    monkeypatch.setattr(popularity_gui.time, "strftime", lambda _fmt: "2026-09-28")
    monkeypatch.setattr(popularity_gui.time, "monotonic", lambda: 200.0)

    with patch.object(popularity_gui.os, "makedirs", side_effect=AssertionError("must not build/write")):
        PRServiceGUI.save_daily_resonance_csv(owner, {}, {}, {}, {}, [], {}, force_save=False)


def test_strategy_does_not_submit_non_trading_day_work():
    strategy = StockLiveStrategy()
    strategy.executor = MagicMock()
    strategy._monitored_stocks = {"000001": {"snapshot": {}}}
    frame = pd.DataFrame({"close": [10.0]}, index=["000001"])

    with patch("JohnsonUtil.commonTips.get_trade_date_status", return_value=False), \
            patch("JohnsonUtil.commonTips.get_work_time_duration", return_value=False):
        strategy.process_data(frame, resample="d")

    strategy.executor.submit.assert_not_called()


def test_tdx_sync_worker_schedules_retry_cleanup_after_refresh_exception():
    owner = object.__new__(PRServiceGUI)
    owner.refresh_realtime_from_tdx = MagicMock(side_effect=RuntimeError("temporary TDX failure"))
    owner.root = MagicMock()
    owner._tdx_query_sync_started = True
    owner._queue_realtime_update = MagicMock()

    owner._query_tdx_sync_worker(["000001"])

    owner._queue_realtime_update.assert_called_once_with(action="_finish_query_tdx_sync")
    owner.root.after.assert_not_called()


def test_tdx_sync_worker_clears_busy_flag_if_tk_callback_cannot_be_queued():
    owner = object.__new__(PRServiceGUI)
    owner.refresh_realtime_from_tdx = MagicMock(return_value=False)
    owner.root = MagicMock()
    owner.root.after.side_effect = RuntimeError("window closed")
    owner._tdx_query_sync_started = True

    owner._query_tdx_sync_worker(["000001"])

    assert owner._tdx_query_sync_started is False


def test_ipc_off_hours_diff_is_acked_but_not_merged(monkeypatch):
    import ats.tdx_realtime_fetcher as fetcher

    monkeypatch.setattr(fetcher, "is_trading_time", lambda: (False, "closed"))
    bridge = object.__new__(IPCBridge)
    bridge._cached_df = pd.DataFrame({"trade": [10.0]}, index=["000001"])
    bridge._cache_sync_session = "session-a"
    bridge._cache_sync_version = 10
    acknowledged = []
    bridge._ack_data_frame = lambda body: acknowledged.append(body)
    delivered = []
    bridge._handle_client(_FrameConnection({
        "type": "UPDATE_DF_DIFF",
        "data": pd.DataFrame({"trade": [11.0]}, index=["000001"]),
        "ver": 11,
        "sync_session": "session-a",
    }), delivered.append, None)

    assert delivered == []
    assert float(bridge._cached_df.loc["000001", "trade"]) == 10.0
    assert bridge._cache_sync_version == 10
    assert bridge._cache_requires_full_baseline is True
    assert len(acknowledged) == 1


def test_ipc_off_hours_drop_requires_one_active_full_baseline(monkeypatch):
    import ats.tdx_realtime_fetcher as fetcher

    market_active = [False]
    monkeypatch.setattr(fetcher, "is_trading_time", lambda: (market_active[0], "session"))
    bridge = object.__new__(IPCBridge)
    bridge._cached_df = pd.DataFrame({"trade": [10.0]}, index=["000001"])
    bridge._cache_sync_session = "session-a"
    bridge._cache_sync_version = 10
    requests = []
    acknowledged = []
    delivered = []
    bridge._request_full_baseline = lambda: requests.append(True)
    bridge._ack_data_frame = lambda body: acknowledged.append(body)

    def receive(message):
        bridge._handle_client(_FrameConnection(message), delivered.append, None)

    receive({
        "type": "UPDATE_DF_DIFF",
        "data": pd.DataFrame({"trade": [11.0]}, index=["000001"]),
        "ver": 11,
        "sync_session": "session-a",
    })
    assert bridge._cache_sync_version == 10
    assert len(requests) == 0

    market_active[0] = True
    receive({
        "type": "UPDATE_DF_DIFF",
        "data": pd.DataFrame({"trade": [11.0]}, index=["000001"]),
        "ver": 11,
        "sync_session": "session-a",
    })
    receive({
        "type": "UPDATE_DF_DIFF",
        "data": pd.DataFrame({"trade": [12.0]}, index=["000001"]),
        "ver": 12,
        "sync_session": "session-a",
    })
    assert bridge._cached_df is None
    assert len(requests) == 1
    assert len(acknowledged) == 3
    assert delivered == []

    receive({
        "type": "UPDATE_DF_ALL",
        "data": pd.DataFrame({"trade": [12.0, 8.0]}, index=["000001", "000002"]),
        "ver": 20,
        "sync_session": "session-a",
    })
    assert bridge._cache_requires_full_baseline is False
    assert bridge._full_baseline_requested is False
    assert bridge._cache_sync_version == 20
    assert bridge._cached_df.index.tolist() == ["000001", "000002"]
    assert len(delivered) == 1
    assert len(acknowledged) == 4


def test_ipc_version_gap_during_market_requests_new_baseline(monkeypatch):
    import ats.tdx_realtime_fetcher as fetcher

    monkeypatch.setattr(fetcher, "is_trading_time", lambda: (True, "active"))
    bridge = object.__new__(IPCBridge)
    bridge._cached_df = pd.DataFrame({"trade": [10.0]}, index=["000001"])
    bridge._cache_sync_session = "session-a"
    bridge._cache_sync_version = 10
    requests = []
    bridge._request_full_baseline = lambda: requests.append(True)
    delivered = []
    bridge._handle_client(_FrameConnection({
        "type": "UPDATE_DF_DIFF",
        "data": pd.DataFrame({"trade": [12.0]}, index=["000001"]),
        "ver": 12,
        "sync_session": "session-a",
    }), delivered.append, None)

    assert bridge._cached_df is None
    assert requests == [True]
    assert delivered == []


def test_ipc_date_rollover_diff_clears_yesterday_baseline(monkeypatch):
    import ats.tdx_realtime_fetcher as fetcher

    monkeypatch.setattr(fetcher, "is_trading_time", lambda: (True, "active"))
    bridge = object.__new__(IPCBridge)
    bridge._cached_df = pd.DataFrame({"trade": [10.0]}, index=["000001"])
    bridge._last_cache_date = "2000-01-01"
    requests = []
    bridge._request_full_baseline = lambda: requests.append(True)
    delivered = []

    bridge._handle_client(_FrameConnection({
        "type": "UPDATE_DF_DIFF",
        "data": pd.DataFrame({"trade": [12.0]}, index=["000001"]),
    }), delivered.append, None)

    assert bridge._cached_df is None
    assert requests == [True]
    assert delivered == []


def test_ipc_diff_merge_failure_discards_cache_and_requests_baseline(monkeypatch):
    import ats.tdx_realtime_fetcher as fetcher

    monkeypatch.setattr(fetcher, "is_trading_time", lambda: (True, "active"))
    bridge = object.__new__(IPCBridge)
    bridge._cached_df = pd.DataFrame({"trade": [10.0]}, index=["000001"])
    requests = []
    bridge._request_full_baseline = lambda: requests.append(True)
    delivered = []
    monkeypatch.setattr(
        pd.Index, "intersection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("merge failure")),
    )

    bridge._handle_client(_FrameConnection({
        "type": "UPDATE_DF_DIFF",
        "data": pd.DataFrame({"trade": [12.0]}, index=["000001"]),
    }), delivered.append, None)

    assert bridge._cached_df is None
    assert requests == [True]
    assert delivered == []
