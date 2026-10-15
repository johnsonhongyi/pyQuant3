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


@pytest.fixture
def sina_history_store(tmp_path, monkeypatch):
    from JSONData import tdx_hdf5_api as h5a
    from JSONData import sina_data
    path = tmp_path / 'sina_MultiIndex_data_memory.h5'
    index = pd.MultiIndex.from_product(
        [['600000', '000001'], pd.date_range('2026-10-15 09:25', periods=20, freq='min')],
        names=['code', 'ticktime'])
    frame = pd.DataFrame({'close': np.arange(40, dtype=float) + 10,
                          'volume': np.arange(40, dtype=float) + 100}, index=index)
    frame.iloc[0, 0] = np.nan
    frame.to_hdf(path, 'all_30', format='table')
    monkeypatch.setattr(h5a, 'RAMDISK_KEY', 0)
    monkeypatch.setattr(h5a, '_SINA_MI_CACHE', {})
    monkeypatch.setattr(h5a, '_SINA_MI_EPOCH', {})
    monkeypatch.setattr(h5a, '_SINA_MI_WRITE_LOCKS', {})
    monkeypatch.setattr(h5a, 'SafeHDFStore', lambda *a, **kw: pd.HDFStore(path, 'r'))
    monkeypatch.setattr(h5a.cct, 'get_ramdisk_path', lambda *a, **kw: str(path))
    monkeypatch.setattr(sina_data.Sina, '_MEM_CACHE', {})
    monkeypatch.setattr(sina_data.Sina, '_LOADING_ST', {})
    monkeypatch.setattr(sina_data.cct, 'sina_limit_time', 30)
    return h5a, sina_data, path, frame


def test_unified_history_and_hdf_cache_share_one_allocation(sina_history_store, monkeypatch):
    h5a, sina_data, path, frame = sina_history_store
    # 先以普通接口预热：统一层应复用底层缓存，而不是再保留第二份大表。
    detached = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False, MultiIndex=True)
    original_load = h5a.load_hdf_db
    calls = []
    def load(*a, **kw):
        calls.append(kw)
        return original_load(*a, **kw)
    monkeypatch.setattr(h5a, 'load_hdf_db', load)
    client = sina_data.Sina(readonly=True)
    results = []
    worker = threading.Thread(target=lambda: results.append(client._load_hdf_hist_unified(table='all_30')))
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive() and len(results) == 1
    canonical = h5a._SINA_MI_CACHE['all_30']['df']
    assert results[0] is canonical
    assert 'df' not in client._MEM_CACHE['all_30']
    assert calls[0]['_share_cache'] is True
    assert client._load_hdf_hist_unified(table='all_30') is canonical
    assert len(calls) == 1  # 统一层命中仍然不读 HDF。
    pd.testing.assert_frame_equal(detached, canonical)
    assert not np.shares_memory(detached['close'].values, canonical['close'].values)
    detached.iloc[0, 0] = 999
    assert canonical.iloc[0, 0] != 999
    # 竞价面板所用的筛选与 VWAP 计算不能修改共享轨迹源。
    before = canonical.copy()
    client.get_real_time_tick('600000', l_limit_time=30, enrich_data=True)
    client._calc_intraday_vwap_fast(canonical)
    pd.testing.assert_frame_equal(canonical, before)


def test_shared_history_cold_load_and_file_change(sina_history_store):
    h5a, sina_data, path, frame = sina_history_store
    options = dict(timelimit=False, MultiIndex=True, _share_cache=True)
    first = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', **options)
    assert first is h5a._SINA_MI_CACHE['all_30']['df']
    assert first['close'].isna().sum() == 0
    # 普通接口仍返回可独立修改的副本。
    public = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False, MultiIndex=True)
    public.iloc[0, 0] = 999
    assert first.iloc[0, 0] != 999
    frame['close'] += 5
    frame.to_hdf(path, 'all_30', format='table', mode='w')
    # 显式修改文件时间，避免 Windows 时间戳精度导致测试偶发命中旧缓存。
    import os
    info = path.stat()
    os.utime(path, (info.st_atime, info.st_mtime + 2))
    refreshed = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', **options)
    assert refreshed is not first
    assert refreshed is h5a._SINA_MI_CACHE['all_30']['df']
    assert refreshed['close'].max() == first['close'].max() + 5


def test_writer_cache_normalizes_without_mutating_old_generation(sina_history_store):
    h5a, sina_data, path, frame = sina_history_store
    info = path.stat()
    # 模拟现有写入同步发布的缓存（尚未执行读取侧的空值规范化）。
    h5a._SINA_MI_CACHE['all_30'] = {'df': frame, 'mtime': info.st_mtime, 'size': info.st_size,
        'path': h5a._sina_history_path('sina_MultiIndex_data'),
        'version': h5a._sina_history_version(path)}
    result = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False,
                            MultiIndex=True, _share_cache=True)
    assert result is h5a._SINA_MI_CACHE['all_30']['df']
    assert result['close'].isna().sum() == 0
    assert pd.isna(frame.iloc[0, 0])  # 其他读取者持有的旧代不被原地修改。
    again = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False,
                           MultiIndex=True, _share_cache=True)
    assert again is result


def test_history_singleflight_keeps_ui_nonblocking(sina_history_store, monkeypatch):
    h5a, sina_data, path, frame = sina_history_store
    started, release = threading.Event(), threading.Event()
    original_load = h5a.load_hdf_db
    calls, results = [], []
    def load(*a, **kw):
        calls.append(True)
        started.set()
        assert release.wait(timeout=5)
        return original_load(*a, **kw)
    monkeypatch.setattr(h5a, 'load_hdf_db', load)
    client = sina_data.Sina(readonly=True)
    workers = [threading.Thread(target=lambda: results.append(
        client._load_hdf_hist_unified(table='all_30'))) for _ in range(3)]
    try:
        workers[0].start()
        assert started.wait(timeout=5)
        pending = client._load_hdf_hist_unified(table='all_30')
        assert pending.empty and pending.attrs['freshness'] == 'loading'
        for worker in workers[1:]:
            worker.start()
    finally:
        release.set()
        for worker in workers:
            if worker.ident is not None:
                worker.join(timeout=10)
    assert all(not worker.is_alive() for worker in workers)
    assert len(calls) == 1 and len(results) == 3
    assert all(result is h5a._SINA_MI_CACHE['all_30']['df'] for result in results)
    assert not client._LOADING_ST


@pytest.mark.parametrize('multi_index', [True, False])
def test_cached_code_filter_keeps_shared_multiindex(sina_history_store, multi_index):
    h5a, sina_data, path, frame = sina_history_store
    # 冷读与热读均按实际存储索引过滤，未显式传 MultiIndex 也不能改坏源表。
    cold = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', code_l=['600000'],
                          timelimit=False, MultiIndex=multi_index)
    canonical = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False,
                               MultiIndex=True, _share_cache=True)
    before = canonical.copy()
    warm = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', code_l=['600000'],
                          timelimit=False, MultiIndex=multi_index)
    assert len(warm) == 20
    assert isinstance(warm.index, pd.MultiIndex)
    pd.testing.assert_frame_equal(warm, cold)
    warm.iloc[0, 0] = 999
    warm.index.names = ['changed', 'time']
    pd.testing.assert_frame_equal(canonical, before)


def test_public_history_getter_is_detached_and_keeps_cache_hits(sina_history_store, monkeypatch):
    h5a, sina_data, path, frame = sina_history_store
    canonical = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False,
                               MultiIndex=True, _share_cache=True)
    client = sina_data.Sina(readonly=True)
    client._MEM_CACHE['all_30'] = {'df': canonical, 'last_time': sina_data.time.time(), 'ready': True}
    monkeypatch.setattr(sina_data.cct, 'get_work_time_duration', lambda: False)
    from unittest.mock import Mock
    read = Mock(side_effect=AssertionError('warm getter must not read disk'))
    monkeypatch.setattr(h5a, 'SafeHDFStore', read)
    public = client.get_sina_MultiIndex_data()
    before = frame.fillna(0)
    public.iloc[0, 0] = 999
    public.columns.values[0] = 'price'
    public.index.levels[0].values[0] = '700000'
    public['extra'] = 1
    public.index.names = ['changed', 'time']
    public.columns = ['price', 'vol', 'extra']
    ordinary = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False, MultiIndex=True)
    pd.testing.assert_frame_equal(ordinary, before)
    ordinary.columns.values[0] = 'price'
    ordinary.index.levels[0].values[0] = '700000'
    pd.testing.assert_frame_equal(canonical, before)
    pd.testing.assert_frame_equal(client.get_sina_MultiIndex_data(), before)
    assert client._get_cached_hdf_history('sina_MultiIndex_data', 'all_30')[1] is canonical
    assert 'df' not in client._MEM_CACHE['all_30']  # 旧强引用条目安全迁移。
    read.assert_not_called()


@pytest.mark.parametrize('table', ['all_30', None])
def test_history_clear_releases_both_layers_and_legacy_references(sina_history_store, table):
    import gc
    import weakref
    from types import SimpleNamespace
    h5a, sina_data, path, frame = sina_history_store
    canonical = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False,
                               MultiIndex=True, _share_cache=True)
    client = sina_data.Sina(readonly=True)
    client._MEM_CACHE['all_30'] = {'df': canonical, 'last_time': 0, 'ready': True}
    legacy = {'unified_h5_hist_all_30': canonical, 'agg_metrics': frame.copy(), 'lastbuydf': frame['close']}
    client.agg_cache = SimpleNamespace(getkey=lambda k: legacy.get(k),
        setkey=lambda k, v: legacy.__setitem__(k, v))
    reference = weakref.ref(canonical)
    del canonical
    client.clear_unified_cache(table, force_gc=False)
    gc.collect()
    assert reference() is None
    assert 'all_30' not in client._MEM_CACHE and 'all_30' not in h5a._SINA_MI_CACHE
    assert legacy['agg_metrics'] is not None and legacy['lastbuydf'] is not None
    # 清理内存后仍可按原流程重读，不改变历史数据内容。
    reloaded = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False,
                              MultiIndex=True, _share_cache=True)
    pd.testing.assert_frame_equal(reloaded, frame.fillna(0))


def test_selective_clear_preserves_other_history_and_snapshot(sina_history_store):
    h5a, sina_data, path, frame = sina_history_store
    client = sina_data.Sina(readonly=True)
    snapshot = {'df': frame.copy(), 'time': 0}
    other = {'df': frame.copy(), 'last_time': 0, 'ready': True}
    client._MEM_CACHE.update({'all_30': other, 'all_60': other, 'snapshot': snapshot})
    h5a._SINA_MI_CACHE.update({'all_30': other, 'all_60': other})
    client.clear_unified_cache('all_30', force_gc=False)
    assert 'all_30' not in client._MEM_CACHE and 'all_30' not in h5a._SINA_MI_CACHE
    assert client._MEM_CACHE['all_60'] is other and h5a._SINA_MI_CACHE['all_60'] is other
    assert client._MEM_CACHE['snapshot'] is snapshot


def test_clear_during_load_does_not_resurrect_old_generation(sina_history_store, monkeypatch):
    h5a, sina_data, path, frame = sina_history_store
    entered, release = threading.Event(), threading.Event()
    original_read = h5a.safe_load_table
    reads, results, failures = [], [], []
    def read(*args, **kwargs):
        reads.append(True)
        if len(reads) == 1:
            stale = original_read(*args, **kwargs)
            stale['close'] = 999.0
            entered.set()
            assert release.wait(timeout=5)
            return stale
        return original_read(*args, **kwargs)
    monkeypatch.setattr(h5a, 'safe_load_table', read)
    client = sina_data.Sina(readonly=True)
    def load():
        try:
            results.append(client._load_hdf_hist_unified(table='all_30'))
        except Exception as exc:
            failures.append(exc)
    first, second = threading.Thread(target=load), threading.Thread(target=load)
    try:
        first.start()
        assert entered.wait(timeout=5)
        client.clear_unified_cache('all_30', force_gc=False)
        second.start()
        second.join(timeout=5)
        assert not second.is_alive()
    finally:
        release.set()
        first.join(timeout=10)
        if second.ident is not None:
            second.join(timeout=10)
    assert not failures and not first.is_alive()
    canonical = h5a._SINA_MI_CACHE['all_30']['df']
    assert canonical is client._get_cached_hdf_history('sina_MultiIndex_data', 'all_30')[1]
    assert canonical['close'].max() != 999.0
    assert not client._LOADING_ST


def test_cancelled_loader_starting_after_clear_cannot_publish(sina_history_store):
    h5a, sina_data, path, frame = sina_history_store
    h5a._clear_sina_history_cache(['all_30'])
    result = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False,
                            MultiIndex=True, _share_cache=True, _cache_valid=lambda: False)
    assert not result.empty  # 已经进行的调用仍可取得数据，不能重新驻留。
    assert not h5a._SINA_MI_CACHE


def test_cold_ui_history_load_stays_in_background(sina_history_store, monkeypatch):
    h5a, sina_data, path, frame = sina_history_store
    called = threading.Event()
    original = h5a.load_hdf_db
    threads = []
    def load(*a, **kw):
        threads.append(threading.current_thread())
        called.set()
        return original(*a, **kw)
    monkeypatch.setattr(h5a, 'load_hdf_db', load)
    client = sina_data.Sina(readonly=True)
    pending = client._load_hdf_hist_unified(table='all_30')
    assert pending.empty and pending.attrs['freshness'] == 'loading'
    assert called.wait(timeout=5)
    with client._LOAD_LOCK:
        event = client._LOADING_ST.get('all_30')
    if event is not None:
        assert event.wait(timeout=5)
    assert threads and all(thread is not threading.main_thread() for thread in threads)
    assert client._get_cached_hdf_history('sina_MultiIndex_data', 'all_30')[1] is h5a._SINA_MI_CACHE['all_30']['df']


def test_failed_history_load_releases_flight_and_can_retry(sina_history_store, monkeypatch):
    from unittest.mock import Mock
    h5a, sina_data, path, frame = sina_history_store
    original = h5a.load_hdf_db
    fail = Mock(side_effect=OSError('isolated read failure'))
    monkeypatch.setattr(h5a, 'load_hdf_db', fail)
    client = sina_data.Sina(readonly=True)
    results = []
    worker = threading.Thread(target=lambda: results.append(client._load_hdf_hist_unified(table='all_30')))
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive() and results[0].empty
    assert not client._LOADING_ST and not client._MEM_CACHE
    monkeypatch.setattr(h5a, 'load_hdf_db', original)
    worker = threading.Thread(target=lambda: results.append(client._load_hdf_hist_unified(table='all_30')))
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive() and not results[-1].empty


def test_internal_tk_recovery_borrows_without_mutating_shared_source(sina_history_store, monkeypatch):
    from realtime_data_service import DataPublisher
    from unittest.mock import Mock
    h5a, sina_data, path, frame = sina_history_store
    canonical = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False,
                               MultiIndex=True, _share_cache=True)
    client = sina_data.Sina(readonly=True)
    client._MEM_CACHE['all_30'] = {'df': canonical, 'last_time': sina_data.time.time(), 'ready': True}
    monkeypatch.setattr(client, 'get_sina_MultiIndex_data', Mock(side_effect=AssertionError('full copy')))
    monkeypatch.setattr(sina_data, 'Sina', lambda **kw: client)
    publisher = DataPublisher.__new__(DataPublisher)
    before = canonical.copy()
    full = publisher.recover_from_hdf5()
    partial = publisher.recover_from_hdf5_by_codes(['600000'])
    assert len(full) == 40 and len(partial) == 20
    pd.testing.assert_frame_equal(partial.reset_index(drop=True),
        full[full['code'] == '600000'].reset_index(drop=True))
    pd.testing.assert_frame_equal(canonical, before)
    assert client._get_cached_hdf_history('sina_MultiIndex_data', 'all_30')[1] is canonical


@pytest.mark.parametrize('layout', ['numeric', 'mapped', 'column'])
def test_cached_symbol_normalization_matches_cold_read_without_source_mutation(sina_history_store, layout):
    h5a, sina_data, path, frame = sina_history_store
    index = [1, 600000] if layout == 'numeric' else ['999999', '600000']
    data = pd.DataFrame({'close': [10.0, 11.0]}, index=pd.Index(index, name='code'))
    mapped = layout == 'mapped'
    requested = ['000001'] if layout in ('numeric', 'mapped') else ['999999']
    if layout == 'column':
        data = data.reset_index()
    data.to_hdf(path, 'all_30', format='table', mode='w')
    cold = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', code_l=requested,
                          index=mapped, timelimit=False)
    h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', timelimit=False)
    canonical = h5a._SINA_MI_CACHE['all_30']['df']
    before = canonical.copy()
    warm = h5a.load_hdf_db('sina_MultiIndex_data', 'all_30', code_l=requested,
                          index=mapped, timelimit=False)
    pd.testing.assert_frame_equal(warm, cold)
    assert len(warm) == 1
    warm.iloc[0, 0] = 999
    pd.testing.assert_frame_equal(canonical, before)


@pytest.fixture
def native_sina_store(tmp_path, monkeypatch):
    from JSONData import tdx_hdf5_api as h5a
    from JSONData import sina_data
    # 所有文件、锁和临时镜像均限制在 pytest 临时目录，使用真实 SafeHDFStore。
    fname = 'sina_MultiIndex_data_writer'
    path = tmp_path / (fname + '.h5')
    def resolve(name):
        base = str(name).replace('\\', '/').rsplit('/', 1)[-1]
        return str(tmp_path / (base if base.endswith('.h5') or '.tmp.' in base else base + '.h5'))
    monkeypatch.setattr(h5a.cct, 'get_ramdisk_path', resolve)
    monkeypatch.setattr(h5a, 'BaseDir', str(tmp_path))
    monkeypatch.setattr(h5a, '_CLEAN_RAMDISK_TEMP', False)
    monkeypatch.setattr(h5a, 'RAMDISK_KEY', 0)
    monkeypatch.setattr(h5a, '_SINA_MI_CACHE', {})
    monkeypatch.setattr(h5a, '_SINA_MI_EPOCH', {})
    monkeypatch.setattr(h5a, '_SINA_MI_WRITE_LOCKS', {})
    monkeypatch.setattr(sina_data.Sina, '_MEM_CACHE', {})
    monkeypatch.setattr(sina_data.Sina, '_LOADING_ST', {})
    index = pd.MultiIndex.from_arrays([['600000', '000001'],
        pd.to_datetime(['2026-10-15 09:30', '2026-10-15 09:30'])], names=['code', 'ticktime'])
    data = pd.DataFrame({'close': [10.0, 20.0], 'volume': [100.0, 200.0]}, index=index)
    data.to_hdf(path, 'all_30', format='table')
    return h5a, fname, path, data


@pytest.mark.parametrize('append,rewrite', [(True, False), (False, False), (False, True)])
def test_real_history_writer_keeps_atomic_persistence_and_cache_compatibility(native_sina_store, append, rewrite):
    h5a, fname, path, data = native_sina_store
    old = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    old_values = old.copy()
    update = data.copy()
    update.index = pd.MultiIndex.from_arrays([['600000', '000001'],
        pd.to_datetime(['2026-10-15 09:31', '2026-10-15 09:31'])], names=['code', 'ticktime'])
    update['close'] += 1
    update['volume'] += 10
    assert h5a.write_hdf_db(fname, update, table='all_30', append=append, rewrite=rewrite, MultiIndex=True)
    assert len(h5a._SINA_MI_CACHE['all_30']['df']) == (2 if rewrite else 4)
    current = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    disk = pd.read_hdf(path, 'all_30')
    pd.testing.assert_frame_equal(current.sort_index(), disk.sort_index())
    pd.testing.assert_frame_equal(old, old_values)
    assert len(disk) == (2 if rewrite else 4)
    assert current is h5a._SINA_MI_CACHE['all_30']['df']
    update.columns.values[0] = 'changed'
    update.index.levels[0].values[0] = '700000'
    pd.testing.assert_frame_equal(current.sort_index(), disk.sort_index())
    assert not path.with_name(path.name + '.lock').exists()


@pytest.mark.parametrize('warm_writer', [False, True])
@pytest.mark.parametrize('codes', [None, ['600000']])
def test_reader_postprocessing_cannot_stamp_old_data_as_new_file(native_sina_store, monkeypatch, warm_writer, codes):
    h5a, fname, path, data = native_sina_store
    entered, release = threading.Event(), threading.Event()
    original_fill = pd.DataFrame.fillna
    paused, results, errors = [], [], []
    def fill(frame, *args, **kwargs):
        if threading.current_thread().name == 'HistoryRaceReader' and not paused:
            paused.append(True)
            entered.set()
            assert release.wait(timeout=10)
        return original_fill(frame, *args, **kwargs)
    monkeypatch.setattr(pd.DataFrame, 'fillna', fill)
    def read():
        try:
            results.append(h5a.load_hdf_db(fname, 'all_30', timelimit=False,
                                          MultiIndex=True, _share_cache=True, code_l=codes))
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=read, name='HistoryRaceReader')
    try:
        worker.start()
        assert entered.wait(timeout=5)
        assert not path.with_name(path.name + '.lock').exists()
        if warm_writer:
            h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
        update = data.copy()
        update.index = pd.MultiIndex.from_arrays([['600000', '000001'],
            pd.to_datetime(['2026-10-15 09:31'] * 2)], names=['code', 'ticktime'])
        update['close'] += 1
        assert h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True)
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive() and not errors
    if warm_writer and codes is None:
        assert len(results[0]) == 4  # 复用写线程已发布的新版本，不额外读取全表。
    else:
        assert results[0].empty and results[0].attrs['freshness'] == 'stale'
    latest = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    assert len(latest) == 4
    assert latest is h5a._SINA_MI_CACHE['all_30']['df']
    assert h5a._SINA_MI_CACHE['all_30']['version'] == h5a._sina_history_version(path)
    pd.testing.assert_frame_equal(latest.sort_index(), pd.read_hdf(path, 'all_30').sort_index())


def test_unified_publication_rejects_snapshot_superseded_after_lower_read(native_sina_store, monkeypatch):
    from JSONData import sina_data
    h5a, fname, path, data = native_sina_store
    entered, release = threading.Event(), threading.Event()
    original_load = h5a.load_hdf_db
    calls, results, errors = [], [], []
    def load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=10)
        return result
    monkeypatch.setattr(h5a, 'load_hdf_db', load)
    client = sina_data.Sina(readonly=True)
    def read():
        try:
            results.append(client._load_hdf_hist_unified(fname=fname, table='all_30'))
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=read)
    try:
        worker.start()
        assert entered.wait(timeout=5)
        update = data.copy()
        update.index = pd.MultiIndex.from_arrays([['600000', '000001'],
            pd.to_datetime(['2026-10-15 09:31'] * 2)], names=['code', 'ticktime'])
        update['close'] += 1
        assert h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True)
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive() and not errors and results[0].empty
    assert 'all_30' not in client._MEM_CACHE
    worker = threading.Thread(target=read)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive() and not errors and len(results[-1]) == 4
    assert client._get_cached_hdf_history(fname, 'all_30')[1] is h5a._SINA_MI_CACHE['all_30']['df']


@pytest.mark.parametrize('append', [True, False])
@pytest.mark.parametrize('selective', [True, False])
def test_overlapping_batches_and_incoming_duplicate_ticks_keep_latest(native_sina_store, append, selective):
    h5a, fname, path, data = native_sina_store
    old = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    before = old.copy()
    update = data.copy()
    update.index = pd.MultiIndex.from_arrays([['600000', '000001'],
        pd.to_datetime(['2026-10-15 09:30', '2026-10-15 09:31'])], names=['code', 'ticktime'])
    update['close'] += 2
    last = update.iloc[[0]].copy()
    last['close'] = 13.0
    assert h5a.write_hdf_db(fname, pd.concat([update, last]), table='all_30',
                             append=append, MultiIndex=True)
    options = dict(timelimit=False, MultiIndex=True)
    if selective:
        options['code_l'] = ['600000']
    warm = h5a.load_hdf_db(fname, 'all_30', **options)
    h5a._clear_sina_history_cache()
    cold = h5a.load_hdf_db(fname, 'all_30', **options)
    key = ('600000', pd.Timestamp('2026-10-15 09:30'))
    assert warm.loc[key, 'close'] == cold.loc[key, 'close'] == 13.0
    pd.testing.assert_frame_equal(warm.sort_index(), cold.sort_index())
    pd.testing.assert_frame_equal(old, before)
    assert warm.index.is_unique and cold.index.is_unique


@pytest.mark.parametrize('count', [2, 12])
def test_same_tick_value_updates_are_written_but_identical_batches_are_skipped(native_sina_store, count):
    h5a, fname, path, data = native_sina_store
    if count == 12:
        index = pd.MultiIndex.from_arrays([[f'{i:06d}' for i in range(1, 13)],
            pd.to_datetime(['2026-10-15 09:30'] * 12)], names=['code', 'ticktime'])
        data = pd.DataFrame({'close': np.arange(12, dtype=float) + 10,
                             'volume': np.arange(12, dtype=float) + 100}, index=index)
        data.to_hdf(path, 'all_30', format='table', mode='w')
    h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    update = data.copy()
    update.iloc[-1, 0] += 5  # 时间不变，内容改变；也覆盖采样股票以外的代码。
    assert h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True)
    warm = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True)
    h5a._clear_sina_history_cache()
    cold = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True)
    pd.testing.assert_frame_equal(warm.sort_index(), update.sort_index())
    pd.testing.assert_frame_equal(cold.sort_index(), update.sort_index())
    version = h5a._sina_history_version(path)
    assert h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True) is False
    assert h5a._sina_history_version(path) == version


@pytest.mark.parametrize('rewrite_first', [False, True])
def test_second_writer_waits_until_first_cache_publication(native_sina_store, monkeypatch, rewrite_first):
    h5a, fname, path, data = native_sina_store
    h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    entered, release, second_attempt, second_commit = (threading.Event() for _ in range(4))
    original_sync, original_replace = h5a._sync_sina_history_after_write, h5a.os.replace
    errors, results = [], []
    def sync(*args, **kwargs):
        if threading.current_thread().name == 'FirstHistoryWriter':
            assert path.with_name(path.name + '.lock').exists()
            entered.set()
            assert release.wait(timeout=10)
        return original_sync(*args, **kwargs)
    def replace(*args, **kwargs):
        if threading.current_thread().name == 'SecondHistoryWriter':
            second_commit.set()
        return original_replace(*args, **kwargs)
    monkeypatch.setattr(h5a, '_sync_sina_history_after_write', sync)
    monkeypatch.setattr(h5a.os, 'replace', replace)
    def write(minute, rewrite):
        try:
            update = data.copy()
            update.index = pd.MultiIndex.from_arrays([['600000', '000001'],
                pd.to_datetime([f'2026-10-15 09:{minute}'] * 2)], names=['code', 'ticktime'])
            update['close'] += minute - 30
            if threading.current_thread().name == 'SecondHistoryWriter':
                second_attempt.set()
            results.append(h5a.write_hdf_db(fname, update, table='all_30',
                                             MultiIndex=True, rewrite=rewrite))
        except Exception as exc:
            errors.append(exc)
    first = threading.Thread(target=write, args=(31, rewrite_first), name='FirstHistoryWriter')
    second = threading.Thread(target=write, args=(32, False), name='SecondHistoryWriter')
    try:
        first.start()
        assert entered.wait(timeout=5)
        second.start()
        assert second_attempt.wait(timeout=5)
        assert not second_commit.wait(timeout=0.1)
    finally:
        release.set()
        first.join(timeout=10)
        if second.ident is not None:
            second.join(timeout=10)
    assert not errors and not first.is_alive() and not second.is_alive()
    assert results == [True, True]
    cached = h5a._SINA_MI_CACHE['all_30']['df']
    disk = pd.read_hdf(path, 'all_30')
    assert len(disk) == (4 if rewrite_first else 6)
    pd.testing.assert_frame_equal(cached.sort_index(), disk.sort_index())
    assert h5a._SINA_MI_CACHE['all_30']['version'] == h5a._sina_history_version(path)
    assert not path.with_name(path.name + '.lock').exists()


def test_open_reader_can_close_while_writer_waits_for_atomic_replace(native_sina_store, monkeypatch):
    h5a, fname, path, data = native_sina_store
    h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    attempted, results, errors = threading.Event(), [], []
    original = h5a.os.replace
    def replace(*args, **kwargs):
        attempted.set()
        return original(*args, **kwargs)
    monkeypatch.setattr(h5a.os, 'replace', replace)
    def write():
        try:
            update = data.copy()
            update.index = pd.MultiIndex.from_arrays([['600000', '000001'],
                pd.to_datetime(['2026-10-15 09:31'] * 2)], names=['code', 'ticktime'])
            update['close'] += 1
            results.append(h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True))
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=write, daemon=True)
    with h5a.SafeHDFStore(fname, 'r') as reader:
        worker.start()
        assert attempted.wait(timeout=5)
        # Windows 上读句柄仍打开，writer 重试 replace 时不能阻碍此处读取和关闭。
        pd.testing.assert_frame_equal(reader.get('all_30'), data)
    worker.join(timeout=10)
    assert not worker.is_alive() and not errors and results == [True]
    assert len(h5a._SINA_MI_CACHE['all_30']['df']) == 4
    assert not path.with_name(path.name + '.lock').exists()


def test_failed_writer_releases_transaction_for_next_thread(native_sina_store, monkeypatch):
    from unittest.mock import Mock
    h5a, fname, path, data = native_sina_store
    update = data.copy()
    update.index = pd.MultiIndex.from_arrays([['600000', '000001'],
        pd.to_datetime(['2026-10-15 09:31'] * 2)], names=['code', 'ticktime'])
    update['close'] += 1
    original = h5a.SafeHDFStore
    results = []
    monkeypatch.setattr(h5a, 'SafeHDFStore', Mock(side_effect=OSError('isolated open failure')))
    first = threading.Thread(target=lambda: results.append(
        h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True)), daemon=True)
    first.start()
    first.join(timeout=5)
    assert not first.is_alive() and results == [False]
    pd.testing.assert_frame_equal(pd.read_hdf(path, 'all_30'), data)
    monkeypatch.setattr(h5a, 'SafeHDFStore', original)
    second = threading.Thread(target=lambda: results.append(
        h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True)), daemon=True)
    second.start()
    second.join(timeout=10)
    assert not second.is_alive() and results == [False, True]
    assert len(pd.read_hdf(path, 'all_30')) == 4


def test_external_replace_with_same_mtime_and_size_rejects_old_read(native_sina_store, monkeypatch):
    import subprocess
    import sys
    h5a, fname, path, data = native_sina_store
    entered, release = threading.Event(), threading.Event()
    before = path.stat()
    original_fill = pd.DataFrame.fillna
    paused, results, errors = [], [], []
    def fill(frame, *args, **kwargs):
        if threading.current_thread().name == 'ExternalHistoryReader' and not paused:
            paused.append(True)
            entered.set()
            assert release.wait(timeout=15)
        return original_fill(frame, *args, **kwargs)
    monkeypatch.setattr(pd.DataFrame, 'fillna', fill)
    def read():
        try:
            results.append(h5a.load_hdf_db(fname, 'all_30', timelimit=False,
                                          MultiIndex=True, _share_cache=True))
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=read, name='ExternalHistoryReader')
    try:
        worker.start()
        assert entered.wait(timeout=5)
        # 独立进程不共享本进程清理代次；保留原时间和大小，验证文件标识变化。
        script = (
            'import os,sys,pandas as pd; p=sys.argv[1]; s=os.stat(p); '
            'd=pd.read_hdf(p,"all_30"); d["close"]+=5; q=p+".external"; '
            'd.to_hdf(q,"all_30",format="table",mode="w"); '
            'os.utime(q,ns=(s.st_atime_ns,s.st_mtime_ns)); os.replace(q,p)'
        )
        subprocess.run([sys.executable, '-c', script, str(path)],
                       check=True, capture_output=True, timeout=10)
        after = path.stat()
        assert after.st_size == before.st_size and after.st_mtime_ns == before.st_mtime_ns
        assert after.st_ino != before.st_ino
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive() and not errors
    assert results[0].empty and results[0].attrs['freshness'] == 'stale'
    latest = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    pd.testing.assert_frame_equal(latest, data.assign(close=data['close'] + 5))


def test_equal_values_at_distinct_ticks_remain_lossless(native_sina_store, monkeypatch):
    from unittest.mock import Mock
    h5a, fname, path, data = native_sina_store
    data = pd.concat([data, data])
    data.index = pd.MultiIndex.from_arrays([['600000', '000001'] * 2,
        pd.to_datetime(['2026-10-15 09:30'] * 2 + ['2026-10-15 09:31'] * 2)], names=['code', 'ticktime'])
    data[['close', 'volume']] = [10.0, 100.0]
    data.to_hdf(path, 'all_30', format='table', mode='w')
    write = Mock(side_effect=AssertionError('read must not rewrite equal-valued ticks'))
    monkeypatch.setattr(h5a, 'write_hdf_db', write)
    cold = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True)
    warm = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True)
    assert len(cold) == len(warm) == 4
    pd.testing.assert_frame_equal(cold, data)
    pd.testing.assert_frame_equal(warm, data)
    write.assert_not_called()


def test_other_hdf_tables_keep_legacy_first_record_policy(tmp_path):
    from JSONData import tdx_hdf5_api as h5a
    path = tmp_path / 'other_history.h5'
    index = pd.MultiIndex.from_arrays([['600000'] * 2,
        pd.to_datetime(['2026-10-15 09:30'] * 2)], names=['code', 'ticktime'])
    data = pd.DataFrame({'close': [10.0, 12.0]}, index=index)
    data.to_hdf(path, 'all_30', format='table')
    with pd.HDFStore(path, 'r') as store:
        actual = h5a.safe_load_table(store, 'all_30')
    pd.testing.assert_frame_equal(actual, data.iloc[[0]])


def test_unversioned_global_history_migrates_to_shared_current_cache(native_sina_store):
    from JSONData import sina_data
    from types import SimpleNamespace
    h5a, fname, path, data = native_sina_store
    legacy = {'unified_h5_hist_all_30': data.assign(close=999.0),
              'unified_h5_hist_time_all_30': sina_data.time.time()}
    client = sina_data.Sina(readonly=True)
    client.agg_cache = SimpleNamespace(getkey=lambda k: legacy.get(k),
        setkey=lambda k, v: legacy.__setitem__(k, v))
    results = []
    worker = threading.Thread(target=lambda: results.append(
        client._load_hdf_hist_unified(fname=fname, table='all_30')))
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive() and len(results) == 1
    pd.testing.assert_frame_equal(results[0], data)
    assert legacy['unified_h5_hist_all_30'] is None
    assert client._get_cached_hdf_history(fname, 'all_30')[1] is h5a._SINA_MI_CACHE['all_30']['df']


def _unified_history_in_worker(client, fname, table='all_30'):
    results, errors = [], []
    def read():
        try:
            results.append(client._load_hdf_hist_unified(fname=fname, table=table))
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=read)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive() and not errors and len(results) == 1
    return results[0]


@pytest.mark.parametrize('disabled', [1, 2])
def test_disabled_sina_hdf_writer_skips_paths_and_locks(monkeypatch, disabled):
    from unittest.mock import Mock
    from JSONData import tdx_hdf5_api as h5a
    index = pd.MultiIndex.from_tuples([('600000', pd.Timestamp('2026-10-15 09:30'))],
                                     names=['code', 'ticktime'])
    data = pd.DataFrame({'close': [np.nan]}, index=index)
    resolve = Mock(side_effect=AssertionError('disabled HDF must not resolve paths'))
    monkeypatch.setattr(h5a, 'RAMDISK_KEY', disabled)
    monkeypatch.setattr(h5a.cct, 'get_ramdisk_path', resolve)
    monkeypatch.setattr(h5a, '_SINA_MI_WRITE_LOCKS', {})
    result = h5a.write_hdf_db('sina_MultiIndex_data', data, MultiIndex=True)
    pd.testing.assert_frame_equal(result, data.fillna(0))
    assert not h5a._SINA_MI_WRITE_LOCKS
    resolve.assert_not_called()


@pytest.mark.parametrize('fail_prune,real_repack', [(False, False), (True, False), (False, True)])
def test_capacity_prune_preserves_sibling_tables_and_attributes(native_sina_store, monkeypatch, fail_prune, real_repack):
    import shutil
    if real_repack and shutil.which('ptrepack') is None:
        pytest.skip('ptrepack executable is unavailable')
    h5a, fname, path, data = native_sina_store
    index = pd.MultiIndex.from_product([['000001', '600000'],
        pd.date_range('2026-10-15 09:30', periods=100, freq='s')], names=['code', 'ticktime'])
    history = pd.DataFrame({'close': 10., 'volume': 100.}, index=index)
    with pd.HDFStore(path, 'w') as store:
        store.put('all_30', history, format='table')
        store.put('all_60', data, format='table')
        store.put('snapshot', data, format='fixed')
        store.get_storer('all_60').attrs.owner = 'sibling-table'
        store._handle.root._v_attrs.owner = 'history-file'
    h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True, _share_cache=True)
    original_put, original_repack = h5a.put_table_safe, h5a.repack_hdf_db
    attempts, repacks = [], []
    def put(*args, **kwargs):
        attempts.append(True)
        if fail_prune and len(attempts) == 1:
            raise OSError('isolated prune failure')
        return original_put(*args, **kwargs)
    def repack(*args, **kwargs):
        # 在重排前检查原子替换结果，并单独覆盖真实 ptrepack 路径。
        with pd.HDFStore(path, 'r') as store:
            repacks.append(set(store.keys()))
        return original_repack(*args, **kwargs) if real_repack else True
    monkeypatch.setattr(h5a, 'put_table_safe', put)
    monkeypatch.setattr(h5a, 'repack_hdf_db', repack)
    update = history.groupby(level='code').tail(1).copy()
    update['close'] = 13.
    assert h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True, sizelimit=0.001)
    with pd.HDFStore(path, 'r') as store:
        assert set(store.keys()) == {'/all_30', '/all_60', '/snapshot'}
        pd.testing.assert_frame_equal(store['all_60'], data)
        pd.testing.assert_frame_equal(store['snapshot'], data)
        assert store.get_storer('all_60').attrs.owner == 'sibling-table'
        assert store._handle.root._v_attrs.owner == 'history-file'
        disk = store['all_30']
    cold = h5a.load_hdf_db(fname, 'all_30', timelimit=False, MultiIndex=True)
    expected = history.copy()
    expected.loc[update.index, 'close'] = 13.
    if not fail_prune:
        expected = expected.groupby(level='code', group_keys=False).tail(80)
        assert repacks == [{'/all_30', '/all_60', '/snapshot'}]
    pd.testing.assert_frame_equal(cold.sort_index(), expected.sort_index())
    pd.testing.assert_frame_equal(cold.sort_index(), disk[~disk.index.duplicated(keep='last')].sort_index())
    assert not path.with_name(path.name + '.lock').exists()


@pytest.mark.parametrize('work_time', [True, False])
def test_unified_cache_adopts_written_version_without_retaining_old_table(native_sina_store, monkeypatch, work_time):
    import weakref
    from unittest.mock import Mock
    from JSONData import sina_data
    h5a, fname, path, data = native_sina_store
    monkeypatch.setattr(sina_data.cct, 'get_work_time_duration', lambda: work_time)
    client = sina_data.Sina(readonly=True)
    before = _unified_history_in_worker(client, fname)
    old_ref = weakref.ref(before)
    del before
    read = Mock(side_effect=AssertionError('current write cache must avoid HDF reload'))
    monkeypatch.setattr(h5a, 'load_hdf_db', read)
    update = data.assign(close=data['close'] + 5)
    assert h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True)
    assert old_ref() is None  # 上层元数据不能延长旧大表寿命，甚至不需要下一次读取。
    current = _unified_history_in_worker(client, fname)
    assert current is h5a._SINA_MI_CACHE['all_30']['df']
    pd.testing.assert_frame_equal(current.sort_index(), update.sort_index())
    item = client._MEM_CACHE['all_30']
    assert item['version'] == h5a._sina_history_version(path)
    assert item['path'] == h5a._sina_history_path(fname)
    assert not any(isinstance(value, pd.DataFrame) for value in item.values())
    read.assert_not_called()


@pytest.mark.parametrize('change', ['replace', 'delete', 'other_file'])
def test_unified_cache_checks_file_version_even_after_hours(native_sina_store, monkeypatch, change):
    import os
    import weakref
    from JSONData import sina_data
    h5a, fname, path, data = native_sina_store
    monkeypatch.setattr(sina_data.cct, 'get_work_time_duration', lambda: False)
    client = sina_data.Sina(readonly=True)
    before = _unified_history_in_worker(client, fname)
    old_ref = weakref.ref(before)
    del before
    update = data.assign(close=data['close'] + 5)
    if change == 'replace':
        version = h5a._sina_history_version(path)
        info = path.stat()
        replacement = str(path) + '.external'
        update.to_hdf(replacement, 'all_30', format='table', mode='w')
        os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
        os.replace(replacement, path)
        new_version = h5a._sina_history_version(path)
        assert new_version[:2] == version[:2] and new_version[2] != version[2]
    elif change == 'delete':
        path.unlink()
    else:
        fname = 'sina_MultiIndex_data_other'
        update.to_hdf(path.with_name(fname + '.h5'), 'all_30', format='table')
    original_read = h5a.safe_load_table
    def read(*args, **kwargs):
        assert old_ref() is None  # 重新读盘前释放失效的缓存引用。
        return original_read(*args, **kwargs)
    monkeypatch.setattr(h5a, 'safe_load_table', read)
    current = _unified_history_in_worker(client, fname)
    assert old_ref() is None
    if change == 'delete':
        assert current.empty and 'all_30' not in client._MEM_CACHE
        assert 'all_30' not in h5a._SINA_MI_CACHE
    else:
        pd.testing.assert_frame_equal(current, update)
        assert current is h5a._SINA_MI_CACHE['all_30']['df']


@pytest.mark.parametrize('busy_lock', ['upper', 'lower'])
def test_unified_ui_version_check_never_waits_for_busy_cache_locks(native_sina_store, busy_lock):
    from JSONData import sina_data
    h5a, fname, path, data = native_sina_store
    client = sina_data.Sina(readonly=True)
    _unified_history_in_worker(client, fname)
    lock = client._LOAD_LOCK if busy_lock == 'upper' else h5a._SINA_MI_LOCK
    entered, release = threading.Event(), threading.Event()
    expired = []
    def hold():
        with lock:
            entered.set()
            if not release.wait(timeout=5):
                expired.append(True)
    owner = threading.Thread(target=hold)
    try:
        owner.start()
        assert entered.wait(timeout=5)
        result = client._load_hdf_hist_unified(fname=fname, table='all_30')
        assert result.empty and result.attrs['freshness'] == 'loading'
        assert not expired and not client._LOADING_ST
    finally:
        release.set()
        owner.join(timeout=10)
    assert not owner.is_alive()
    assert client._load_hdf_hist_unified(fname=fname, table='all_30') is h5a._SINA_MI_CACHE['all_30']['df']


@pytest.mark.parametrize('action', ['clear', 'new_reader'])
def test_writer_merge_allows_clear_and_keeps_new_reader_publication(native_sina_store, monkeypatch, action):
    from JSONData import sina_data
    h5a, fname, path, data = native_sina_store
    client = sina_data.Sina(readonly=True)
    _unified_history_in_worker(client, fname)
    entered, release = threading.Event(), threading.Event()
    original_concat = pd.concat
    results, locks = [], []
    def concat(*args, **kwargs):
        if threading.current_thread().name == 'UnlockedHistoryMerge':
            locks.append(h5a._SINA_MI_LOCK._is_owned())
            entered.set()
            assert release.wait(timeout=10)
        return original_concat(*args, **kwargs)
    monkeypatch.setattr(pd, 'concat', concat)
    update = data.assign(close=data['close'] + 5)
    writer = threading.Thread(target=lambda: results.append(
        h5a.write_hdf_db(fname, update, table='all_30', MultiIndex=True)), name='UnlockedHistoryMerge')
    canonical = None
    try:
        writer.start()
        assert entered.wait(timeout=5)
        assert locks == [False]
        if action == 'clear':
            client.clear_unified_cache('all_30', force_gc=False)
        else:
            pending = client._load_hdf_hist_unified(fname=fname, table='all_30')
            assert pending.empty and pending.attrs['freshness'] == 'loading'
            with client._LOAD_LOCK:
                event = client._LOADING_ST.get('all_30')
            if event is not None:
                assert event.wait(timeout=5)
            canonical = h5a._SINA_MI_CACHE['all_30']['df']
            pd.testing.assert_frame_equal(canonical.sort_index(), update.sort_index())
    finally:
        release.set()
        writer.join(timeout=10)
    assert not writer.is_alive() and results == [True]
    if action == 'clear':
        assert 'all_30' not in h5a._SINA_MI_CACHE and 'all_30' not in client._MEM_CACHE
    else:
        assert h5a._SINA_MI_CACHE['all_30']['df'] is canonical
        assert client._get_cached_hdf_history(fname, 'all_30')[1] is canonical
    assert not path.with_name(path.name + '.lock').exists()


def test_handle_version_probe_waits_for_concurrent_hdf_operation(native_sina_store):
    from types import SimpleNamespace
    h5a, fname, path, data = native_sina_store
    started, accessed = threading.Event(), threading.Event()
    results, errors = [], []
    with open(path, 'rb') as handle:
        def fileno():
            accessed.set()
            return handle.fileno()
        store = SimpleNamespace(_handle=SimpleNamespace(fileno=fileno))
        def probe():
            started.set()
            try:
                results.append(h5a._sina_history_version(path, store))
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=probe)
        with h5a._HDF_GLOBAL_LOCK:
            worker.start()
            assert started.wait(timeout=5)
            assert not accessed.wait(timeout=0.1)
        worker.join(timeout=5)
        assert not worker.is_alive() and not errors and accessed.is_set()
        assert results == [h5a._sina_history_version(path)]


@pytest.mark.parametrize('kind', ['single', 'groups', 'invalid', 'nan', 'large_integer', 'empty'])
def test_vwap_group_end_optimization_matches_original_exactly(kind):
    from JSONData import sina_data
    if kind == 'empty':
        assert sina_data.Sina(readonly=True)._calc_intraday_vwap_fast(pd.DataFrame()).empty
        return
    codes = ['600000'] if kind == 'single' else ['600000', '600000', '000001', '000001', '000001']
    close = np.arange(len(codes), dtype=float) / 3 + 10
    volume = np.arange(len(codes), dtype=float) * 100 + 50
    if kind == 'invalid':
        close[0] = 0
        volume[1] = -1
        volume[3:] = 0
    elif kind == 'nan':
        close[1] = np.nan
    elif kind == 'large_integer':
        volume = np.arange(len(codes), dtype=np.uint64) + 2**53 + 1
    index = pd.MultiIndex.from_arrays([codes, pd.date_range('2026-10-15 09:25',
        periods=len(codes), freq='min')], names=['code', 'ticktime'])
    frame = pd.DataFrame({'close': close, 'volume': volume}, index=index)
    before = frame.copy()
    # 原算法：全长累计值、全长组偏移、全长 VWAP，再取每组最后一行。
    labels = frame.index.get_level_values(0).values
    ends = np.concatenate([labels[1:] != labels[:-1], [True]])
    starts = np.concatenate([[True], labels[1:] != labels[:-1]])
    delta = np.empty_like(volume)
    delta[0] = volume[0]
    delta[1:] = volume[1:] - volume[:-1]
    delta[starts] = volume[starts]
    delta[(close <= 0) | (delta <= 0)] = 0
    cum_vol, cum_amt = np.cumsum(delta), np.cumsum(close * delta)
    end_positions = np.where(ends)[0]
    lengths = np.diff(np.concatenate([[-1], end_positions]))
    vo = np.repeat(np.concatenate([[0], cum_vol[end_positions[:-1]]]), lengths)
    ao = np.repeat(np.concatenate([[0], cum_amt[end_positions[:-1]]]), lengths)
    with np.errstate(divide='ignore', invalid='ignore'):
        expected = pd.DataFrame({'nclose': ((cum_amt - ao) / (cum_vol - vo))[ends]},
                                index=frame.index.get_level_values(0)[ends])
    result = sina_data.Sina(readonly=True)._calc_intraday_vwap_fast(frame)
    pd.testing.assert_frame_equal(result, expected, check_exact=True)
    pd.testing.assert_frame_equal(frame, before, check_exact=True)
