"""Runtime work bounds, snapshot fidelity and GUI shutdown responsiveness."""
import ast
import datetime
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import Future
from functools import lru_cache
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pandas as pd
ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=8)
def source_tree(path):
    return ast.parse((ROOT / path).read_text(encoding='utf-8'))


def method(path, cls_name, name, **extra):
    cls = next(n for n in source_tree(path).body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    fn = ast.FunctionDef(name=fn.name, args=fn.args, body=fn.body, decorator_list=[],
                         returns=fn.returns, type_comment=None)
    ast.fix_missing_locations(fn)
    ns = dict(pd=pd, time=time, threading=threading, datetime=datetime, logger=Mock())
    ns.update(extra)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), path, 'exec'), ns)
    return ns[name]


def pump_owner():
    from tk_frame_fingerprint import same_fingerprint
    owner = SimpleNamespace(global_values=SimpleNamespace(getkey=lambda _key: 'd'),
                            compute_executor=Mock(), _run_compute_async=Mock(),
                            _on_compute_done=Mock(), _sort_dataframe=lambda df: df)
    owner.compute_executor.submit.side_effect = lambda *_args: Future()
    pump = method('instock_MonitorTK.py', 'StockMonitorApp', '_process_tree_data_async',
                  same_fingerprint=same_fingerprint,
                  frame_fingerprint=Mock(side_effect=AssertionError('full-table hash in pump')))
    return owner, MethodType(pump, owner)


def packet(version=1):
    df = pd.DataFrame({'code': ['000001', '000002'], 'trade': [10., 20.],
                       'name': ['one', 'two'], 'history': [[1, 2], [3, 4]]})
    result = dict(full_snapshot=df, filtered_ui_data=df, timestamp=100.)
    if version is not None:
        result['source_version'] = version
    return result


def test_versioned_pump_skips_only_same_snapshot_and_handles_all_metadata_changes():
    owner, pump = pump_owner()
    first = packet()
    pump(first)
    pump(first)
    assert owner.compute_executor.submit.call_count == 1
    second = packet(2)
    second['full_snapshot'].loc[1, 'trade'] = 99.
    pump(second)
    assert owner.compute_executor.submit.call_count == 2
    assert owner.compute_executor.submit.call_args.args[1].loc[1, 'trade'] == 99.
    owner.sortby_col = 'name'
    pump(second)
    pump(second, force=True)
    assert owner.compute_executor.submit.call_count == 4


def test_unversioned_inputs_never_skip_changed_or_unhashable_data():
    owner, pump = pump_owner()
    first = packet(None)
    pump(first)
    first['full_snapshot'].loc[1, 'history'].append(5)
    pump(first)
    assert owner.compute_executor.submit.call_count == 2
    assert owner._last_processed_df_hash is None


def test_clearing_query_on_same_snapshot_still_recomputes(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'query_engine_util', SimpleNamespace(
        query_engine=SimpleNamespace(execute=lambda df, query: df)))
    monkeypatch.setitem(sys.modules, 'realtime_data_service', SimpleNamespace(
        get_global_kline_cache=lambda: None))
    owner, pump = pump_owner()
    data = packet()
    pump(data, query='trade > 0')
    pump(data, query='')
    assert owner.compute_executor.submit.call_count == 2


def test_market_bus_copies_each_distinct_input_once_without_mutating_source():
    from market_state_bus import MarketStateBus
    df = pd.DataFrame({'trade': [10.]}, index=['000001'])
    copy = Mock(wraps=df.copy)
    df.copy = copy
    bus = MarketStateBus()
    bus.publish(df, df, df, df)
    copy.assert_called_once()
    version, full, filtered, _stamp, res, filtered_res = bus.get_latest_dual()
    assert full is filtered is res is filtered_res and full is not df
    df.iloc[0, 0] = 20.
    assert full.iloc[0, 0] == 10.
    bus.publish(df, df, df, df)
    assert bus.get_latest_dual()[0] == version + 1
    assert bus.get_latest_dual()[1].iloc[0, 0] == 20.


def test_binary_send_fingerprint_covers_objects_late_columns_and_schema(monkeypatch):
    import hashlib
    import pickle
    import tk_frame_fingerprint as fingerprints
    monkeypatch.setattr(pd.util, 'hash_pandas_object',
                        Mock(side_effect=AssertionError('object string conversion')))
    df = packet()['full_snapshot']
    original = fingerprints.send_content_fingerprint(df)
    assert original == hashlib.blake2b(pickle.dumps(df, protocol=5), digest_size=16).digest()
    monkeypatch.setattr(pickle, 'dumps', Mock(side_effect=AssertionError('full payload allocation')))
    assert original == fingerprints.send_content_fingerprint(df.copy())
    modified = df.copy(deep=True)
    modified['history'] = [[1, 2], [3, 4, 5]]
    assert original != fingerprints.send_content_fingerprint(modified)
    assert original != fingerprints.send_content_fingerprint(df.rename(columns={'trade': 'price'}))
    assert fingerprints.send_content_fingerprint(None) is None


def test_strategy_reuses_selector_and_refreshes_its_data_reference():
    seen = []
    def create_selector(**kwargs):
        selector = SimpleNamespace(df_all_realtime=kwargs['df'])
        def candidates(**_kw):
            seen.append(selector.df_all_realtime)
            return pd.DataFrame()
        selector.get_candidates_df = candidates
        return selector
    selector_cls = Mock(side_effect=create_selector)
    owner = SimpleNamespace(_lock=threading.Lock(), _monitored_stocks={},
                            _is_checking_resamples=set(), _data_check_rounds=0)
    scan = method('stock_live_strategy.py', 'StockLiveStrategy', '_check_strategies',
                  StockSelector=selector_cls, StockLiveStrategy=SimpleNamespace())
    first = packet()['full_snapshot'].set_index('code', drop=False)
    scan(owner, first, ['000001'])
    second = first.copy()
    second.loc['000001', 'trade'] = 50.
    scan(owner, second, ['000001'])
    assert selector_cls.call_count == 1
    assert seen == [first, second]
    assert owner._candidate_selectors['d'].df_all_realtime is None
    scan(owner, second, ['000001'], resample='w')
    assert selector_cls.call_count == 2
    assert 'resample' not in selector_cls.call_args.kwargs


def test_voice_overflow_is_summarized_without_an_unbounded_per_stock_cache():
    clock = SimpleNamespace(monotonic=lambda: 1.)
    log = Mock()
    owner = SimpleNamespace(_voice_overflow_log_lock=threading.Lock(),
                            _voice_overflow_log_time=float('-inf'), _voice_overflow_log_count=0)
    report = method('alert_manager.py', 'AlertManager', '_log_voice_overflow', time=clock, logger=log)
    for i in range(100):
        report(owner, 'skipped', str(i))
    assert log.warning.call_count == 1
    clock.monotonic = lambda: 31.
    report(owner, 'replaced', 'latest')
    assert log.warning.call_count == 2
    assert log.warning.call_args.args[-1] == 99


def test_history_fetch_is_single_flight_and_submit_failure_allows_retry():
    owner = SimpleNamespace(daily_pattern_detector=object(), _daily_hist_cache_status=True,
        daily_history_cache={}, _pending_hist_fetches=set(), _lock=threading.Lock(),
        _io_executor=Mock(), _async_fetch_history=Mock())
    fetch = method('stock_live_strategy.py', 'StockLiveStrategy', '_update_daily_history_cache')
    workers = [threading.Thread(target=fetch, args=(owner, '600000')) for _ in range(20)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=1)
    assert owner._io_executor.submit.call_count == 1
    owner._pending_hist_fetches.clear()
    owner._io_executor.submit.side_effect = RuntimeError('pool temporarily unavailable')
    fetch(owner, '600000')
    assert owner._pending_hist_fetches == set()
    owner._io_executor.submit.side_effect = None
    fetch(owner, '600000')
    assert owner._pending_hist_fetches == {'600000_d'}


def test_t1_warning_summary_preserves_changed_facts_and_bounds_memory():
    clock = SimpleNamespace(monotonic=lambda: 1.)
    log = Mock()
    owner = SimpleNamespace(_t1_warning_lock=threading.Lock(), _t1_warning_state={})
    report = method('trading_kernel/execution/paper_adapter.py', 'PaperExecutionAdapter',
                    '_log_t1_rejection', time=clock, logger=log)
    for _ in range(100):
        report(owner, 'SELL', '000001', 'FAIL_CLOSED', 100., 0., 0., 100.)
    assert log.warning.call_count == 1
    report(owner, 'SELL', '000001', 'READY', 100., 0., 50., 100.)
    assert log.warning.call_count == 2
    assert log.warning.call_args.args[-1] == 99
    for i in range(1000):
        report(owner, 'SELL', str(i), 'FAIL_CLOSED', 100., 0., 0., 100.)
    assert len(owner._t1_warning_state) == 512


def test_sector_increment_reads_only_five_bars_and_copies_only_affected_memberships():
    class History(deque):
        full_scans = 0
        def __iter__(self):
            self.full_scans += 1
            return super().__iter__()
    class Membership(dict):
        copies = 0
        def copy(self):
            self.copies += 1
            return super().copy()
    tree = source_tree('bidding_momentum_detector.py')
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BiddingMomentumDetector')
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_aggregate_sectors')
    tick_attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)
                  and isinstance(n.value, ast.Name) and n.value.id == 'ts'}
    ticks = {}
    for code in ('600000', '600001', '600002'):
        tick = SimpleNamespace(**{name: 0 for name in tick_attrs})
        tick.score, tick.current_pct, tick.current_price = .6, .1, 10.
        tick.name, tick.category = code, 'sector'
        tick.get_splitted_cats = lambda: ['sector', 'sector2']
        tick.klines = History({'close': float(i)} for i in range(1000))
        ticks[code] = tick
    unused = Membership({'other': {'score': 1.}})
    owner = SimpleNamespace(_lock=threading.RLock(), _tick_series=ticks, _global_snap_cache={},
        _sector_active_stocks_persistent=defaultdict(dict, unused=unused),
        active_sectors={}, sector_map={'sector': set(ticks), 'sector2': set(ticks)}, score_threshold=10.,
        _concept_data_date=datetime.date.today(), daily_watchlist={}, in_history_mode=False,
        last_data_ts=time.time(), baseline_time=time.time(), comparison_interval=1200,
        sector_anchors={}, sector_score_threshold=1e9, stock_selector_seeds={},
        realtime_service=None, data_version=0, is_active_session=lambda: False,
        _calculate_leader_score=lambda data, *_args: data['score'])
    aggregate = method('bidding_momentum_detector.py', 'BiddingMomentumDetector', '_aggregate_sectors',
        cct=SimpleNamespace(CFG=SimpleNamespace(bidding_window_col=[])), SECTOR_BLACKLIST=set(),
        get_limit_up_threshold=lambda code: 9.9, _datetime=datetime.datetime)
    aggregate(owner, list(ticks))
    assert unused.copies == 0
    assert all(tick.klines.full_scans == 0 for tick in ticks.values())
    assert all(row['prices5'] == [995., 996., 997., 998., 999.]
               for row in owner._global_snap_cache.values())
    for code, row in owner._global_snap_cache.items():
        assert owner._sector_active_stocks_persistent['sector'][code] is row
        assert owner._sector_active_stocks_persistent['sector2'][code] is row
        assert 'leader_score' not in row
    assert owner.data_version == 1


def test_thread_shutdown_has_one_total_budget_and_never_joins_the_gui_thread():
    clock = SimpleNamespace(monotonic=lambda: 0.)
    elapsed = [0.]
    clock.monotonic = lambda: elapsed[0]
    class SlowThread:
        daemon = False
        name = 'slow'
        def join(self, timeout):
            elapsed[0] += timeout
        def is_alive(self):
            return True
    main = Mock(daemon=False)
    current = Mock(daemon=False)
    threads = [main, current, *(SlowThread() for _ in range(10))]
    fake_threading = SimpleNamespace(current_thread=lambda: current, main_thread=lambda: main,
                                     enumerate=lambda: threads, _DummyThread=type('Dummy', (), {}))
    wait = method('instock_MonitorTK.py', 'StockMonitorApp', 'wait_all_threads',
                  time=clock, threading=fake_threading)
    wait(SimpleNamespace(), timeout=.5)
    assert elapsed[0] == .5
    main.join.assert_not_called()
    current.join.assert_not_called()
