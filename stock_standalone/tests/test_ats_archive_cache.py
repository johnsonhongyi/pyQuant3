import copy
import builtins
import gzip
import json
import os
import threading
from datetime import date
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

from ats import bounded_evaluation_store as module
from ats import bounded_evaluation_store as cache
from ats import storage_archive as archive
from ats.storage_archive import write_json_gzip


def test_cache_defers_compresses_and_obeys_closing_gate(tmp_path, monkeypatch):
    clock = [100.0]
    window = ['market', '2026-09-30']
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module, 'archive_window', lambda: tuple(window))
    store = module.EvaluationStore()
    store._started = True
    path = str(tmp_path / 'sample.json')
    receipts = []
    store.put(path, {'value': 1}, write_json_gzip, receipts.append)
    for _ in range(100):
        assert store.read(path, {}) == {'value': 1}
    store.flush()
    assert not Path(path + '.gz').exists() and not receipts
    clock[0] += module.WRITE_INTERVAL
    window[0] = None  # Lunch or holiday cannot bypass the archive gate.
    store.flush()
    assert not Path(path + '.gz').exists()
    window[0] = 'market'
    store.flush()
    with gzip.open(path + '.gz', 'rt', encoding='utf-8') as stream:
        assert json.load(stream) == {'value': 1}
    assert receipts == [{'value': 1}]
    import os
    market = datetime(2026, 9, 30, 10, 0, tzinfo=timezone(timedelta(hours=8))).timestamp()
    os.utime(path + '.gz', (market, market))
    peer = module.EvaluationStore()
    peer._started = True
    peer.put(path, {'value': 99}, write_json_gzip)
    store.put(path, {'value': 2}, write_json_gzip)
    window[0] = 'close'
    store.flush()
    peer.flush()  # A cache initialized before close must honor another writer's checkpoint.
    store.put(path, {'value': 3}, write_json_gzip)
    store.flush()
    with gzip.open(path + '.gz', 'rt', encoding='utf-8') as stream:
        assert json.load(stream) == {'value': 2}
    assert store.read(path, {}) == {'value': 3}

    import os
    closed = datetime(2026, 9, 30, 15, 5, tzinfo=timezone(timedelta(hours=8))).timestamp()
    os.utime(path + '.gz', (closed, closed))
    restarted = module.EvaluationStore()
    restarted._started = True
    restarted.put(path, {'value': 4}, write_json_gzip)
    restarted.flush()
    with gzip.open(path + '.gz', 'rt', encoding='utf-8') as stream:
        assert json.load(stream) == {'value': 2}


def test_coalesced_record_changed_during_checkpoint_remains_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'archive_window', lambda: ('market', '2026-09-30'))
    store = module.EvaluationStore()
    store._started = True
    path = str(tmp_path / 'trace.jsonl')
    key = ('600123', 'simulation')
    saved = []
    def writer(filename, records):
        saved.extend(records)
        store.append(filename, {'price': 2}, writer, coalesce_key=key)
    store.append(path, {'price': 1}, writer, coalesce_key=key)
    store._cache[str(Path(path).resolve())]['last_write'] -= module.WRITE_INTERVAL
    store.flush()
    assert saved == [{'price': 1}]
    assert store.buffered_records(path) == [{'price': 2}]


def test_checkpoint_bound_preserves_proof_and_delivery_receipts():
    points = [{'observed_at': '2026-09-30T10:%02d:%02d+08:00' % (i // 60, i % 60),
               'high': i, 'vwap': 10 if i == 1 else None} for i in range(1000)]
    event = {'type': 'NEXT_DAY_WATCH_CONFIRM', 'event_id': 'durable-id', 'delivered': True}
    value = {'config_hash': 'same', 'candidates': {'600123:s': {
        'candidate': {'status': 'EARLY_VALID'}, 'checkpoints': points, 'events': [event]}}}
    tail = copy.deepcopy(points[-2:])
    assert module.compact_checkpoints(value) == 936
    item = value['candidates']['600123:s']
    assert len(item['checkpoints']) == 64 and item['checkpoints'][-2:] == tail
    assert item['events'] == [event] and item['checkpoint_summary']['has_vwap_observation']
    incoming = copy.deepcopy(value)
    incoming['candidates']['600123:s']['events'][0]['delivered'] = False
    module.merge_evaluations(value, incoming)
    assert incoming['candidates']['600123:s']['events'][0]['delivered'] is True


def test_real_calendar_and_trading_windows():
    from ats.archive_policy import archive_window
    assert archive_window(datetime(2026, 9, 30, 10, 0))[0] == 'market'
    assert archive_window(datetime(2026, 9, 30, 12, 0))[0] is None
    assert archive_window(datetime(2026, 9, 30, 15, 5))[0] == 'close'
    assert archive_window(datetime(2026, 10, 1, 10, 0))[0] is None


def test_next_day_process_is_reused_and_closed(tmp_path):
    from ats.next_day_watch_process import NextDayWatchProcess
    process = NextDayWatchProcess(str(tmp_path))
    try:
        first = process.request('health', timeout=20)
        assert first.get('pid') and first == process.request('health', timeout=20)
    finally:
        process.close()
    assert process._process is None


def test_ma20_observations_display_without_trading_pool_admission(monkeypatch):
    import pandas as pd
    import ats.ui.main_window as main
    from ats.capital_dragon_engine import CapitalDragonEngine
    from ats.channel_swing_candidate_engine import ChannelSwingCandidateEngine
    noop = lambda *args, **kwargs: None
    dragon = SimpleNamespace(get_cached_report=lambda **kw: {}, get_dragon_codes=lambda: set(),
                             analyze_capital_dragon_universe=noop)
    monkeypatch.setattr(CapitalDragonEngine, 'get_instance', classmethod(lambda cls: dragon))
    monkeypatch.setattr(ChannelSwingCandidateEngine, 'get_instance', classmethod(lambda cls:
        SimpleNamespace(evaluate_channel_swing_structure=lambda **kw: {})))
    import ats.ui.favorite_panel as favorite
    monkeypatch.setattr(favorite, 'get_ats_extra_cols', lambda: [])
    monkeypatch.setattr(main.cct, 'get_trade_date_status', lambda: False)
    ledger = SimpleNamespace(entries={})
    volume = SimpleNamespace(update_market_context=noop, update_profile=noop,
        analyze_sector_resonance=noop, get_volume_score=lambda code: 0,
        market_context=SimpleNamespace(is_rebound_from_shrink=False))
    snapshot = SimpleNamespace(should_snapshot=lambda: False)
    pools = SimpleNamespace(radar_pool={}, watch_pool={}, trade_pool={})
    tracker = SimpleNamespace(update_stock_state=lambda *args, **kw: ('观察', '1.0%', '0%', 'MA20'))
    service = SimpleNamespace(update_snapshot=noop, sync_projection=noop)
    frame = pd.DataFrame({'close': [10.1], 'ma20d': [10.0], 'percent': [1.0]}, index=['600123'])
    worker = main.LedgerUpdateWorker(frame, ledger, volume, snapshot, tracker, {}, {}, {}, [], pools,
                                   '2026-09-30', service)
    received = []
    worker.results_ready.connect(lambda *args: received.append(args))
    # The independent ladder scan is irrelevant to this MA20 regression.
    from ats.limit_up_engine import LimitUpEngine
    monkeypatch.setattr(LimitUpEngine, 'get_instance', classmethod(lambda cls:
        SimpleNamespace(update_live_snapshot=noop)))
    worker.run()
    assert received and received[0][0] and received[0][0][0][0] == '600123'
    assert ledger.entries == {} and pools.trade_pool == {}


def test_slow_tdx_computation_does_not_block_gui_dispatch():
    import threading
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def compute(**kwargs):
        started.set()
        assert release.wait(3)
        return ['complete']
    target = SimpleNamespace(_alpha_busy=False, _alpha_closed=False,
        engine=SimpleNamespace(extract_top_sectors_from_heatmap=lambda *a, **k: [],
                               compute_hot_alpha_leaderboard=compute),
        _alpha_ready=SimpleNamespace(emit=lambda result: finished.set()))
    HotSectorLeaderboardDialog._start_alpha_refresh(target, [], None, None, 0, [], {}, 0)
    try:
        assert started.wait(2) and target._alpha_busy
        # The caller reached this assertion while TDX remains blocked.
        assert not finished.is_set()
        HotSectorLeaderboardDialog._start_alpha_refresh(target, [], None, None, 0, [], {}, 0)
    finally:
        release.set()
    assert finished.wait(2)


def test_strategy_index_parses_once_and_accepts_list(tmp_path, monkeypatch):
    from ats import new_stock_fetcher as fetcher_module
    config = tmp_path / 'config'
    config.mkdir()
    path = config / 'intraday_newstock_strategies.json'
    path.write_text(json.dumps({'strategies': [{'code': '600123'}]}), encoding='utf-8')
    monkeypatch.setattr(fetcher_module, 'get_app_root', lambda: str(tmp_path))
    calls = []
    load = json.load
    def counted(stream):
        calls.append(1)
        return load(stream)
    monkeypatch.setattr(fetcher_module.json, 'load', counted)
    fetcher = object.__new__(fetcher_module.NewStockFetcher)
    for _ in range(100):
        assert fetcher._check_strategy_exists('600123')
    assert len(calls) == 1


def test_missing_result_cached_and_memory_update_visible(tmp_path, monkeypatch):
    store = cache.EvaluationStore()
    store._started = True
    path = str(tmp_path / 'absent.json')
    opens = []
    real_open = builtins.open
    def tracked(*args, **kwargs):
        opens.append(args[0])
        return real_open(*args, **kwargs)
    monkeypatch.setattr(builtins, 'open', tracked)
    for i in range(20):
        assert store.read(path, {'default': i}) == {'default': i}
    assert opens == [path]
    store.put(path, {'value': 1}, archive.write_json_gzip)
    assert store.peek(path) == store.read(path, {}) == {'value': 1}
    assert not os.path.exists(path + '.gz')


def test_peer_checkpoint_defers_dirty_data(tmp_path, monkeypatch):
    clock = [2000.0]
    wall = [10000.0]
    monkeypatch.setattr(cache.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(cache.time, 'time', lambda: wall[0])
    monkeypatch.setattr(cache, 'archive_window', lambda: ('market', '2026-09-30'))
    path = str(tmp_path / 'peer.json')
    store = cache.EvaluationStore()
    store._started = True
    store.put(path, {'value': 2}, archive.write_json_gzip)
    clock[0] += cache.WRITE_INTERVAL
    archive.write_json_gzip(path, {'value': 1})
    os.utime(path + '.gz', (wall[0] - 10, wall[0] - 10))
    store.flush()
    assert store._cache[path]['dirty']
    with gzip.open(path + '.gz', 'rt', encoding='utf-8') as stream:
        assert json.load(stream) == {'value': 1}
    clock[0] += cache.WRITE_INTERVAL
    wall[0] += cache.WRITE_INTERVAL
    store.flush()
    assert not store._cache[path]['dirty']
    with gzip.open(path + '.gz', 'rt', encoding='utf-8') as stream:
        assert json.load(stream) == {'value': 2}


def test_snapshot_sees_unsaved_worker_evaluation(tmp_path, monkeypatch):
    from ats.next_day_watch_process import _snapshot
    store = cache.EvaluationStore()
    store._started = True
    monkeypatch.setattr(cache, 'evaluation_store', store)
    import next_day_anomaly_watch as watch
    monkeypatch.setattr(watch, 'evaluation_store', store)
    day = '2026-09-30'
    path = str(tmp_path / 'datacsv' / ('next_day_anomaly_eval_%s.json' % day))
    value = {'candidates': {'600001': {'candidate': {'status': 'DELAYED'}, 'events': []}}}
    store.put(path, value, archive.write_json_gzip)
    store.put(str(tmp_path / 'datacsv' / ('next_day_anomaly_stats_%s.json' % day)),
              {'target_trade_date': day}, archive.write_json_gzip)
    result = _snapshot(str(tmp_path), day)
    assert result['eval'] == value and result['delayed_winners'] == [({'status': 'DELAYED'}, day)]
    assert not os.path.exists(path + '.gz')


def test_spawn_snapshot_preserves_newer_memory_manifest(tmp_path):
    from ats.next_day_watch_process import NextDayWatchProcess
    worker = NextDayWatchProcess(str(tmp_path))
    manifest = {'target_trade_date': '2026-09-30', 'generated_at': '2026-09-30T09:20:00',
                'candidates': [{'code': '600001'}]}
    try:
        first = worker.request('snapshot', manifest=manifest, timeout=20)
        assert first['manifest'] == manifest and first['dates'] == ['2026-09-30']
        enriched = dict(manifest, candidates=[{'code': '600001', 'name': 'updated'}])
        assert worker.request('snapshot', manifest=enriched, timeout=20)['manifest'] == enriched
        assert worker.request('snapshot', manifest=manifest, timeout=20)['manifest'] == enriched
        assert not list(tmp_path.glob('datacsv/*.gz'))
    finally:
        worker.close()


def test_trace_tail_cache_and_segment_retention(tmp_path):
    path = str(tmp_path / 'reconciliation_20250901.jsonl')
    archive.append_jsonl_gzip(path, [{'i': i} for i in range(200)])
    assert [json.loads(line)['i'] for line in archive.load_trace_tail(path, 2)] == [199, 198]
    archive.append_jsonl_gzip(path, [{'i': 200}])
    assert [json.loads(line)['i'] for line in archive.load_trace_tail(path, 2)] == [200, 199]
    assert archive.remove_expired_reconciliation_segments(tmp_path, None, date(2026, 9, 30)) == []
    assert len(archive.remove_expired_reconciliation_segments(tmp_path, 365, date(2026, 9, 30))) == 2
    assert not os.path.exists(path + '.parts')


def test_sparse_trace_older_than_recent_index_remains_available(tmp_path):
    path = str(tmp_path / 'trace.jsonl')
    old = {'signal': {'code': '600001'}, 'timestamp': 'older'}
    archive.append_jsonl_gzip(path, [old] + [{'signal': {'code': '600002'}}] * 5001)
    assert archive.load_latest_trace(path, '600001') == old


def test_offhours_summary_runs_once_and_notifies(monkeypatch):
    import ats.capital_dragon_engine as engine
    import ats.tdx_realtime_fetcher as tdx
    instance = object.__new__(engine.CapitalDragonEngine)
    instance._bg_updater_lock = threading.Lock()
    instance._bg_updater_running = False
    calls, loops, sleeps = [], [], []
    instance._compute_market_summary_bg = lambda: calls.append('compute')
    monkeypatch.setattr(tdx, 'is_trading_time', lambda: (False, 'closed'))
    monkeypatch.setattr(engine.threading, 'Thread', lambda **kw:
                        SimpleNamespace(start=lambda: loops.append(kw['target'])))
    class StopLoop(BaseException):
        pass
    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop()
    monkeypatch.setattr(engine.time, 'sleep', sleep)
    callback = lambda: calls.append('notify')
    instance.start_market_summary_bg_updater(on_updated=callback)
    instance.start_market_summary_bg_updater(on_updated=callback)
    try:
        loops[0]()
    except StopLoop:
        pass
    assert calls == ['compute', 'notify'] and len(loops) == 1 and sleeps[-1] >= 60


def test_disabled_ipo_console_blocks_all_provider_auto_start_callers(monkeypatch):
    from ats.strategy.ipo_gate_context_provider import IPOGateContextProvider
    from JohnsonUtil import commonTips as cct
    provider = object.__new__(IPOGateContextProvider)
    # A disabled start must return before accessing thread fields or reading the database.
    for disabled in [False, 'False', '0', 'off']:
        monkeypatch.setattr(cct, 'ipo_learning_console', disabled, raising=False)
        assert provider.start_auto_refresh() is False


def test_status_summary_persists_across_tabs_and_temporary_messages(monkeypatch):
    from PyQt6.QtCore import pyqtSignal
    from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget
    from ats.ui.main_window import ATSMainWindow
    from ats.capital_dragon_engine import CapitalDragonEngine
    app = QApplication.instance() or QApplication([])
    summary = {'formatted_html': '上证: 4889亿 | 深证: 5489亿'}
    receivers = []
    engine = SimpleNamespace(get_market_indices_and_volume_summary=lambda: summary,
        start_market_summary_bg_updater=lambda **kw: receivers.append(kw['on_updated']))
    monkeypatch.setattr(CapitalDragonEngine, 'get_instance', classmethod(lambda cls: engine))
    class Window(QMainWindow):
        _market_summary_ready = pyqtSignal()
        _refresh_market_volume_status = ATSMainWindow._refresh_market_volume_status
        _is_market_session_active = lambda self: False
        _refresh_statusbar_time_display = lambda self: None
    window = Window()
    tabs = QTabWidget(window)
    for name in ['IPO', 'Orders', 'Trace']:
        tabs.addTab(QWidget(), name)
    window.setCentralWidget(tabs)
    ATSMainWindow._init_statusbar(window)
    window.resize(1600, 400)
    window.show()
    receiver = threading.Thread(target=receivers[0])
    receiver.start()
    receiver.join()
    app.processEvents()
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        window.status_bar.showMessage('测试消息')
        app.processEvents()
        assert window.lbl_market_volume_status.isVisible()
        assert window.lbl_market_volume_status.text() == summary['formatted_html']
    window.close()
