import threading
from unittest.mock import Mock

import pandas as pd
import stock_live_strategy as module


def strategy():
    obj = module.StockLiveStrategy.__new__(module.StockLiveStrategy)
    obj._df_lock = threading.Lock()
    obj._monitored_stocks = {}
    obj._last_sector_status = {}
    obj.scan_hot_concepts_status = True
    obj.is_blacklisted = lambda code: False
    obj.add_monitor = Mock()
    obj.voice_announcer = Mock()
    return obj


def test_snapshot_respects_lock_and_projects_dependencies():
    obj = strategy()
    frame = pd.DataFrame({'close': [10.], 'name': ['A'], 'unrelated': [123]})
    snap = obj._strategy_scan_snapshot(frame, obj._HOT_SCAN_COLUMNS)
    assert list(snap.columns) == ['close', 'name']
    frame.loc[0, 'close'] = 20.
    assert snap.loc[0, 'close'] == 10.
    with obj._df_lock:
        assert obj._strategy_scan_snapshot(frame, obj._HOT_SCAN_COLUMNS) is None


def test_rank_snapshot_matches_full_frame(monkeypatch):
    obj = strategy()
    hub = Mock()
    hub.get_follow_queue_df.return_value = pd.DataFrame()
    hub.add_to_watchlist.return_value = True
    monkeypatch.setattr(module, 'get_trading_hub', lambda: hub)
    frame = pd.DataFrame([{'category': '热点', 'name': 'A', 'close': 10., 'trade': 10.,
                           'high': 10.01, 'low': 9.8, 'open': 10., 'lastp1d': 10.,
                           'ma5d': 9.95, 'ma10d': 9.5, 'percent': 2.5,
                           'win': 0, 'volume': 1.5, 'unrelated': 999}], index=['600001'])
    obj._scan_rank_for_follow(frame, ['热点'])
    expected = hub.add_to_watchlist.call_args_list
    assert expected
    hub.reset_mock()
    hub.get_follow_queue_df.return_value = pd.DataFrame()
    obj._scan_rank_for_follow_snapshot(obj._strategy_scan_snapshot(frame, obj._RANK_SCAN_COLUMNS), ['热点'])
    assert hub.add_to_watchlist.call_args_list == expected


def test_validation_snapshot_matches_full_frame(monkeypatch):
    obj = strategy()
    hub = Mock()
    hub.validate_watchlist.return_value = {'validated': []}
    monkeypatch.setattr(module, 'get_trading_hub', lambda: hub)
    frame = pd.DataFrame([{'close': 10., 'high': 11., 'low': 9., 'open': 9.5,
                           'ma5d': 9.7, 'ma10d': 9.6, 'upper': 11., 'high4': 10.,
                           'volume': 2., 'win': 1, 'unrelated': 999}], index=['600001'])
    obj._daily_watchlist_validation(frame)
    expected = hub.validate_watchlist.call_args
    hub.reset_mock()
    hub.validate_watchlist.return_value = {'validated': []}
    obj._daily_watchlist_validation_snapshot(obj._strategy_scan_snapshot(frame, obj._VALIDATION_COLUMNS))
    assert hub.validate_watchlist.call_args == expected


def test_hot_snapshot_matches_full_frame():
    obj = strategy()
    frame = pd.DataFrame([{'close': 11., 'high4': 10., 'ma5d': 10., 'hmax': 10.,
                           'red': 6, 'top10': 1, 'volume': 2., 'lastp1d': 9.,
                           'lastp2d': 9., 'win': 3, 'category': '热点', 'name': 'A',
                           'percent': 10., 'high10': 12., 'low10': 9., 'low': 10.,
                           'high': 11., 'open': 10., 'trade': 11., 'ma10d': 9.5,
                           'ma20d': 9., 'unrelated': 999}], index=['600001'])
    obj._scan_hot_concepts(frame.copy(), ['热点'])
    expected = obj.add_monitor.call_args_list
    assert expected
    obj.add_monitor.reset_mock()
    obj._scan_hot_concepts(obj._strategy_scan_snapshot(frame, obj._HOT_SCAN_COLUMNS), ['热点'])
    assert obj.add_monitor.call_args_list == expected


def test_snapshot_isolates_mutable_object_cells():
    obj = strategy()
    nested = {'sectors': ['one'], 'meta': {'value': 1}}
    frame = pd.DataFrame({'category': [nested], 'close': [10.]})
    snap = obj._strategy_scan_snapshot(frame, obj._HOT_SCAN_COLUMNS)
    nested['sectors'].append('two')
    nested['meta']['value'] = 2
    assert snap.at[0, 'category'] == {'sectors': ['one'], 'meta': {'value': 1}}


def test_snapshot_uses_same_locked_frame_version():
    obj = strategy()
    frame = pd.DataFrame({'close': [0.], 'high': [0.]})
    done = threading.Event()
    def writer():
        for value in range(1, 500):
            with obj._df_lock:
                frame.at[0, 'close'] = value
                frame.at[0, 'high'] = value
        done.set()
    worker = threading.Thread(target=writer)
    worker.start()
    while not done.is_set():
        snap = obj._strategy_scan_snapshot(frame, obj._HOT_SCAN_COLUMNS)
        if snap is not None:
            assert snap.at[0, 'close'] == snap.at[0, 'high']
    worker.join(2)
    assert not worker.is_alive()
