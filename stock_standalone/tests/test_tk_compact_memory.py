"""Memory budgets, detached minute buffers and lossless HDF selective reads."""
import pickle
import threading

import numpy as np
import pandas as pd
import pytest


def test_sqlite_thread_budgets_keep_wal_and_committed_data(tmp_path):
    from db_utils import SQLiteConnectionManager
    manager = SQLiteConnectionManager(str(tmp_path / 'budget.db'))
    manager.execute_update('CREATE TABLE sample (value INTEGER)')
    manager.execute_update('INSERT INTO sample VALUES (?)', (2**53 + 1,))
    checks = []

    def read_thread():
        try:
            conn = manager.get_connection()
            checks.append((conn.execute('PRAGMA cache_size').fetchone()[0],
                           conn.execute('PRAGMA mmap_size').fetchone()[0],
                           conn.execute('PRAGMA journal_mode').fetchone()[0],
                           conn.execute('SELECT value FROM sample').fetchone()[0]))
        finally:
            manager.close_thread_connection()

    worker = threading.Thread(target=read_thread)
    worker.start()
    worker.join(timeout=5)
    manager.close_thread_connection()
    assert not worker.is_alive() and len(checks) == 1
    cache, mmap, journal, value = checks[0]
    assert 0 < -cache <= 16 * 1024
    assert 0 <= mmap <= 64 * 1024 * 1024
    assert journal == 'wal' and value == 2**53 + 1


def test_minute_trim_and_restore_release_parent_buffers():
    from realtime_data_service import KLINE_DTYPE, KLineSeries, MinuteKlineCache
    original = np.zeros(2400, dtype=KLINE_DTYPE)
    original['time'] = np.arange(len(original))
    original['close'] = np.arange(len(original)) / 100.0
    cache = MinuteKlineCache(max_len=300)
    cache.from_dict({'600000': original})
    restored = cache._shared_cache['600000'].raw_array
    np.testing.assert_array_equal(restored, original[-300:])
    assert restored.base is None and not np.shares_memory(restored, original)
    cache.set_mode(100)
    trimmed = cache._shared_cache['600000'].raw_array
    np.testing.assert_array_equal(trimmed, original[-100:])
    assert trimmed.base is None and trimmed.nbytes == 100 * KLINE_DTYPE.itemsize
    series = KLineSeries(original.copy())
    series.trim_old(2100)
    assert series.raw_array.base is None
    np.testing.assert_array_equal(series.raw_array, original[-300:])
    roundtrip = pickle.loads(pickle.dumps(series))
    np.testing.assert_array_equal(roundtrip.raw_array, series.raw_array)


def test_minute_dataframe_merge_releases_sorted_parent():
    from realtime_data_service import MinuteKlineCache
    times = pd.date_range('2026-09-30 09:30', periods=20, freq='min', tz='Asia/Shanghai')
    frame = pd.DataFrame(dict(code='600000', time=times,
                              open=12., high=13., low=11., close=12.345678,
                              volume=np.arange(20, dtype=float), cum_vol_start=0.))
    cache = MinuteKlineCache(max_len=15)
    cache.from_dataframe(frame.iloc[:15])
    cache.from_dataframe(frame.iloc[15:], merge=True)
    merged = cache._shared_cache['600000'].raw_array
    assert len(merged) == 15 and merged.base is None
    np.testing.assert_array_equal(merged['time'], times[5:].asi8 // 10**9)
    np.testing.assert_array_equal(merged['volume'], frame['volume'].to_numpy()[5:])


@pytest.mark.parametrize('layout', ['multi', 'index', 'column', 'fixed',
                                   'numeric', 'mapped', 'unqueryable', 'query_error'])
def test_hdf_selective_read_matches_legacy_without_full_load(tmp_path, monkeypatch, layout):
    from JSONData import tdx_hdf5_api as h5a
    path = tmp_path / 'layout.h5'
    codes = ['000001', '600000', '000001']
    frame = pd.DataFrame({'close': [12.3456789012345, np.nan, 13.0],
                          'volume': [2**53 + 1, 2**53 + 2, 2**53 + 3]},
                         index=pd.Index(codes, name='code'))
    multi, mapped = layout == 'multi', layout == 'mapped'
    if multi:
        frame.index = pd.MultiIndex.from_arrays([codes, ['a', 'b', 'c']], names=['code', 'date'])
    elif layout in ('column', 'unqueryable'):
        frame = frame.reset_index()
        frame.index += 10
    elif layout == 'numeric':
        frame.index = pd.Index([1, 600000, 1], name='code')
    elif mapped:
        frame.index = pd.Index(['999999', '600000', '999999'], name='code')
    with pd.HDFStore(path, 'w') as store:
        store.put('all', frame, format='fixed' if layout == 'fixed' else 'table',
                  data_columns=None if layout in ('fixed', 'unqueryable') else True)
    monkeypatch.setattr(h5a, 'RAMDISK_KEY', 0)
    monkeypatch.setattr(h5a, 'SafeHDFStore', lambda *args, **kwargs: pd.HDFStore(path, 'r'))
    direct = h5a._read_requested_hdf_codes
    monkeypatch.setattr(h5a, '_read_requested_hdf_codes', lambda s, t, *args: s.get(t))
    expected = h5a.load_hdf_db('memory_probe', code_l=['000001'], timelimit=False,
                              MultiIndex=multi, index=mapped)
    monkeypatch.setattr(h5a, '_read_requested_hdf_codes', direct)
    full_reads = []
    legacy_get = pd.HDFStore.get
    legacy_select = pd.HDFStore.select

    def track_get(store, key):
        full_reads.append(key)
        return legacy_get(store, key)

    def select(store, key, *args, **kwargs):
        if layout == 'query_error' and kwargs.get('where'):
            raise ValueError('legacy query layout')
        return legacy_select(store, key, *args, **kwargs)

    monkeypatch.setattr(pd.HDFStore, 'get', track_get)
    monkeypatch.setattr(pd.HDFStore, 'select', select)
    result = h5a.load_hdf_db('memory_probe', code_l=['000001'], timelimit=False,
                            MultiIndex=multi, index=mapped)
    pd.testing.assert_frame_equal(result, expected)
    assert bool(full_reads) == (layout in ('fixed', 'numeric', 'unqueryable', 'query_error'))
