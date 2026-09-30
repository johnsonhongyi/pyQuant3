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


def test_checkpoint_bound_preserves_proof_and_delivery_receipts(tmp_path, monkeypatch):
    points = [{'observed_at': '2026-09-30T10:%02d:%02d+08:00' % (i // 60, i % 60),
               'high': i, 'vwap': 10 if i == 1 else None} for i in range(1000)]
    event = {'type': 'NEXT_DAY_WATCH_CONFIRM', 'event_id': 'durable-id', 'delivered': True,
             'observed_at': points[500]['observed_at'],
             'evidence': {'first_observed_at': points[499]['observed_at']}}
    value = {'config_hash': 'same', 'candidates': {'600123:s': {
        'candidate': {'status': 'EARLY_VALID'}, 'checkpoints': points, 'events': [event]}}}
    legacy = copy.deepcopy(value)
    expected = copy.deepcopy([points[i] for i in (0, 499, 500, 999)])
    assert module.compact_checkpoints(value) == 996
    item = value['candidates']['600123:s']
    assert item['checkpoints'] == expected
    assert item['events'] == [event] and item['checkpoint_summary']['has_vwap_observation']
    incoming = copy.deepcopy(value)
    incoming['candidates']['600123:s']['events'][0]['delivered'] = False
    module.merge_evaluations(value, incoming)
    assert incoming['candidates']['600123:s']['events'][0]['delivered'] is True
    path = tmp_path / 'next_day_anomaly_eval_2026-09-30.json'
    path.write_text(json.dumps(legacy), encoding='utf-8')
    os.utime(str(path), (0, 0))
    store = module.EvaluationStore()
    store._started = True
    import next_day_anomaly_watch as watch
    monkeypatch.setattr(watch, 'evaluation_store', store)
    window = [None]
    monkeypatch.setattr(module, 'archive_window', lambda: (window[0], '2026-09-30'))
    assert len(store.read(str(path), {})['candidates']['600123:s']['checkpoints']) == 4
    store.flush()
    assert not Path(str(path) + '.gz').exists()
    window[0] = 'market'
    store._cache[str(path.resolve())]['last_write'] -= module.WRITE_INTERVAL
    store.flush()
    with gzip.open(str(path) + '.gz', 'rt', encoding='utf-8') as stream:
        saved = json.load(stream)['candidates']['600123:s']
    assert len(saved['checkpoints']) == 4 and saved['events'][0]['delivered']
    assert not path.exists()


def test_real_calendar_and_trading_windows():
    from ats.archive_policy import archive_window
    assert archive_window(datetime(2026, 9, 30, 10, 0))[0] == 'market'
    assert archive_window(datetime(2026, 9, 30, 12, 0))[0] is None
    assert archive_window(datetime(2026, 9, 30, 15, 5))[0] == 'close'
    assert archive_window(datetime(2026, 10, 1, 10, 0))[0] is None


def test_next_day_quotes_stay_in_ram_and_confirm_receipt_needs_no_file(tmp_path, monkeypatch):
    import pandas as pd
    import next_day_anomaly_watch as watch
    from ats.strategy.next_day_watch_config_manager import NextDayWatchConfigManager
    store = module.EvaluationStore()
    store._started = True
    monkeypatch.setattr(watch, 'evaluation_store', store)
    monkeypatch.setattr(watch, '_LIVE_OBSERVATIONS', {})
    monkeypatch.setattr(watch, '_history_manifest_index', lambda *args: [])
    config = NextDayWatchConfigManager.get_default_config()
    config['vwap_field'] = 'vwap'
    config_path = tmp_path / 'strategies.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    day = '2026-09-30'
    data_dir = str(tmp_path / 'datacsv')
    candidate = {'code': '600001', 'name': '测试股', 'strategy_id': 'channel_stepup',
        'version': 1, 'config_hash': 'frozen', 'tier': 'A', 'phase': 'STABILIZING',
        'feature_values': {'lasth1d': 11, 'lastp1d': 10}, 'status': 'WATCHING'}
    watch._atomic_json(os.path.join(data_dir, f'next_day_anomaly_watch_{day}.json'),
        {'target_trade_date': day, 'config_hash': 'frozen', 'candidates': [candidate]})
    start = datetime.fromisoformat(day + 'T09:30:00+08:00')
    for i in range(200):
        observed = (start + timedelta(seconds=i * 4)).isoformat()
        result = watch.run_cycle(pd.DataFrame([{'code': '600001', 'high': 12,
            'trade': 11.5, 'percent': 15, 'vwap': 11.2, 'volume': 1000 + i,
            'amount': 11200 + 11.2 * i}]), config_path=str(config_path),
            data_dir=data_dir, asof_date='2026-09-29', target_date=day, observed_at=observed)
        assert result['status'] == 'ok'
        if i >= 2:
            assert not result['telemetry']['eval_dirty']
    evaluation = watch._read_json(result['eval_path'], {})
    entry = evaluation['candidates']['600001:channel_stepup']
    assert len(entry['checkpoints']) == 2
    assert {e['type'] for e in entry['events']} == {'PHASE_CHANGED', 'NEXT_DAY_WATCH_CONFIRM'}
    assert all(e['price'] == 11.5 and e['pct'] == 15 for e in entry['events'])
    confirm = entry['events'][-1]
    assert confirm['evidence']['first_observed_at'] == entry['checkpoints'][0]['observed_at']
    assert watch.get_live_watch_quotes(data_dir, day)['600001']['observed_at'] == observed
    watch.mark_events_delivered(data_dir, day, [confirm['event_id']])
    assert watch._read_json(result['eval_path'], {})['candidates']['600001:channel_stepup']['events'][-1]['delivered']
    assert not list((tmp_path / 'datacsv').glob('*.json*'))


def test_next_day_sector_snapshot_enriches_view_without_mutating_frozen_pool(tmp_path, monkeypatch):
    import next_day_anomaly_watch as watch
    from ats.next_day_watch_process import _snapshot, compact_sector_snapshot
    store = module.EvaluationStore()
    store._started = True
    monkeypatch.setattr(module, 'evaluation_store', store)
    monkeypatch.setattr(watch, 'evaluation_store', store)
    day = datetime.now().astimezone().date().isoformat()
    path = str(tmp_path / 'datacsv' / f'next_day_anomaly_watch_{day}.json')
    manifest = {'target_trade_date': day, 'candidates': [
        {'code': '600001', 'strategy_id': 's', 'tier': 'B', 'category': '汽车类'},
        {'code': '600002', 'strategy_id': 's', 'tier': 'A', 'category': '汽车类'}]}
    store.put(path, manifest, archive.write_json_gzip)
    sectors = {'汽车类': {'score': 12, 'avg_pct': 2, 'follow_ratio': .6,
        'leader': '600001', 'leader_pct': 6, 'ts': day + 'T10:00:00',
        'followers': [{'code': '600002', 'large_tick_payload': [1] * 100}]}}
    compact = compact_sector_snapshot(sectors)
    assert compact['汽车类']['followers'] == ['600002']
    result = _snapshot(str(tmp_path), day, sector_snapshot=compact)
    active, observing = result['manifest']['candidates']
    assert active['sector_evidence']['matches'][0]['name'] == '汽车类'
    assert 'followers' not in active['sector_evidence']['matches'][0]
    assert observing['sector_evidence']['reason'] == '个股未处于上行/启动阶段'
    assert not observing['sector_evidence']['matches']
    assert store.peek(path) == manifest
    assert watch._sector_evidence('汽车类', None, stock_started=True)['reason'] == '板块快照未到达'
    historical = copy.deepcopy(manifest)
    historical['target_trade_date'] = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    archived_evidence = {'matches': [{'name': '昨日板块', 'score': 7}]}
    evaluation = {'candidates': {'600001:s': {'candidate': {'sector_evidence': archived_evidence}}}}
    watch.enrich_manifest_sector_evidence(historical, evaluation, compact)
    assert historical['candidates'][0]['sector_evidence'] == archived_evidence
    assert manifest['candidates'][0].get('sector_evidence') is None
    import ats.ui.next_day_watch_dialog as dialog
    monkeypatch.setattr(dialog, '_is_market_session_active', lambda: False)
    refreshed = []
    panel = SimpleNamespace(isVisible=lambda: True, _main_window=lambda:
        SimpleNamespace(current_sector_snapshot=sectors), tab_widget=SimpleNamespace(currentIndex=lambda: 0),
        auto_refresh_timer=SimpleNamespace(interval=lambda: 60000),
        reload_all_data=lambda: refreshed.append(True), _last_manifest_refresh=0)
    dialog.NextDayAnomalyWatchWidget._on_auto_refresh_tick(panel)
    panel._manifest_sector_source = sectors
    dialog.NextDayAnomalyWatchWidget._on_auto_refresh_tick(panel)
    assert refreshed == [True]


def test_next_day_event_sort_selection_and_legacy_price_repair(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PyQt6.QtWidgets import QApplication, QWidget, QTabWidget
    from PyQt6.QtCore import Qt
    import ats.ui.next_day_watch_dialog as dialog
    cls = dialog.NextDayAnomalyWatchWidget
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(cls, '_configure_stock_table', lambda *args: None)
    monkeypatch.setattr(dialog, 'setup_header_persistence', lambda *args, **kwargs: None)
    monkeypatch.setattr(dialog, '_ats_custom_column_specs', lambda: [])
    links = []
    monkeypatch.setattr(cls, '_link_current_stock', lambda *args: links.append(True))
    view = cls.__new__(cls)
    QWidget.__init__(view)
    view.tab_widget = QTabWidget(view)
    view.eval_data = {}
    view.manifest_data = {}
    view.manifest_custom_specs = []
    view._build_manifest_tab()
    view._build_eval_tab()
    day = datetime.now().astimezone().date().isoformat()
    stamp = day + 'T10:00:00+08:00'
    data = {'target_trade_date': day, 'candidates': {}}
    for code, strategy, price in [('600001', 'one', 2), ('600001', 'two', 10), ('600003', 'one', None)]:
        key = code + ':' + strategy
        data['candidates'][key] = {'candidate': {'code': code, 'name': strategy,
            'feature_values': {'lastp1d': 1}}, 'checkpoints': ([
            {'observed_at': stamp, 'close': price, 'high': price, 'kind': 'PHASE_CHANGED'}] if price else []),
            'events': [{'type': 'PHASE_CHANGED', 'observed_at': stamp, 'price': 0, 'pct': 0}]}
    try:
        dialog._prepare_eval_view(data)
        view._on_eval_loaded(data)
        view.table_events.sortItems(4, Qt.SortOrder.AscendingOrder)
        assert [view.table_events.item(r, 4).text() for r in range(3)] == ['2.00', '10.00', '--']
        view.table_events.setCurrentCell(1, 1)
        assert view.table_checkpoints.item(0, 3).text() == '10.00'
        assert len(links) == 1
        data['candidates']['600001:two']['candidate']['status'] = 'EARLY_VALID'
        view._on_eval_loaded(copy.deepcopy(data))
        assert view.table_events.item(view.table_events.currentRow(), 1).data(Qt.ItemDataRole.UserRole)[0] == '600001:two'
        assert view.table_checkpoints.item(0, 3).text() == '10.00' and len(links) == 1
        unchanged_cell = view.table_events.item(1, 4)
        view._on_eval_loaded(dict(copy.deepcopy(data), quotes={'600001': {'close': 11}}))
        assert view.table_events.item(1, 4) is unchanged_cell and len(links) == 1
        view.table_events.sortItems(5, Qt.SortOrder.DescendingOrder)
        assert [view.table_events.item(r, 5).text() for r in range(3)] == ['+900.00%', '+100.00%', '--']
        assert data['candidates']['600003:one']['events'][0]['price'] is None
        data['candidates']['600001:two']['checkpoints'].append({
            'observed_at': stamp, 'kind': 'CLOSE', 'close': 10, 'vwap': 'bad', 'volume': 'bad'})
        view._on_eval_loaded(copy.deepcopy(data))
        selected = next(r for r in range(view.table_events.rowCount())
            if view.table_events.item(r, 1).data(Qt.ItemDataRole.UserRole)[0] == '600001:two')
        view.table_events.setCurrentCell(selected, 1)
        view._on_event_row_selected(link=False)
        assert any(view.table_checkpoints.item(r, 4).text() == '无效'
            and view.table_checkpoints.item(r, 5).text() == '--'
            for r in range(view.table_checkpoints.rowCount()))
        assert view.table_checkpoints.updatesEnabled()

        manifest = {'target_trade_date': day, 'candidates': [
            {'code': '600001', 'strategy_id': strategy, 'tier': 'A', 'score': score, 'score_model_version': 1,
             'sector_evidence': {'matches': [{'name': strategy}]}}
            for strategy, score in [('one', 2), ('two', 10)]]}
        view._on_manifest_loaded(manifest)
        view.table_manifest.sortItems(4, Qt.SortOrder.DescendingOrder)
        view.table_manifest.setCurrentCell(0, 0)
        baseline_links = len(links)
        manifest['candidates'][0]['score'] = 20  # Reorder the two strategies for one code.
        view._on_manifest_loaded(copy.deepcopy(manifest))
        row = view.table_manifest.currentRow()
        assert view.table_manifest.item(row, 0).data(Qt.ItemDataRole.UserRole) == ('600001', 'two')
        assert '策略: two' in view.text_feature_detail.toPlainText()
        assert len(links) == baseline_links
        opened_sectors = []
        monkeypatch.setattr(view, '_open_sector_detail', opened_sectors.append)
        view._on_candidate_double_clicked(view.table_manifest.item(row, 9))
        assert opened_sectors == ['two']
    finally:
        view.close()
        app.processEvents()


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
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget
    from ats.ui.main_window import ATSMainWindow
    from ats.capital_dragon_engine import CapitalDragonEngine
    app = QApplication.instance() or QApplication([])
    summary = {'formatted_html': '<b>上证: 6794.0亿</b> (1.04x) | 深证: 7586.2亿 (1.02x) | '
               '创业板: 3689.7亿 (1.04x) | 北证: 122.4亿 (1.03x) | 全市: 14502.6亿 (较昨 +285.4亿)'}
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
    window.lbl_data_time_status.setText('🕒 19:30:00')
    for width in [2048, 1600, 1100]:
        window.resize(width, 400)
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            message = '信号池: 候选 86 | 精选 12 | 实盘 0 | 今日新发现 0'
            window.status_bar.showMessage(message)
            app.processEvents()
            left = window.lbl_status_message
            middle = window.lbl_market_volume_status
            right = window.lbl_data_time_status
            assert left.isVisible() and left.text() == message and left.width() > 0
            assert middle.isVisible() and middle.text() == summary['formatted_html']
            assert middle.alignment() & Qt.AlignmentFlag.AlignHCenter
            assert left.geometry().right() < middle.geometry().left()
            assert middle.geometry().right() < right.geometry().left()
    window.status_bar.clearMessage()
    app.processEvents()
    assert window.lbl_status_message.text() == ''
    assert window.lbl_market_volume_status.isVisible()
    window.close()


def test_learning_console_renders_empty_cold_snapshot_before_ticker_selection(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from ats.ui.ipo_learning_console import IPOLearningConsole, _LearningMonitorWorker
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(_LearningMonitorWorker, 'start', lambda self: None)
    # Render during construction, before a collection result can select a ticker.
    monkeypatch.setattr(_LearningMonitorWorker, 'request_refresh',
                        lambda self: self.parent()._render_snapshot({}))
    console = IPOLearningConsole(project_root=str(tmp_path), simulation_read_only=True)
    try:
        assert console._active_ticker == ''
        assert 'NOT_STARTED' in console.lbl_local_llm.text()
        console._active_ticker = '688001'
        console._render_snapshot({'static_sentiment': {'results': {
            '688001': {'emotion_score': 64.0, 'score_quality': 'READY'}}}})
        assert '64.0/100' in console.lbl_local_llm.text()
        console._render_snapshot({})
        assert 'NOT_STARTED' in console.lbl_local_llm.text()
    finally:
        console.stop_monitor()
        console.close()
        app.processEvents()


def test_next_day_failed_sector_load_retries_and_closing_view_refreshes(tmp_path, monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PyQt6.QtWidgets import QApplication, QWidget, QComboBox
    import ats.ui.next_day_watch_dialog as dialog
    app = QApplication.instance() or QApplication([])
    cls = dialog.NextDayAnomalyWatchWidget
    view = cls.__new__(cls)
    QWidget.__init__(view)
    day = date.today().isoformat()
    view.combo_manifest_date = QComboBox(view)
    view.combo_manifest_date.addItem(day)
    view.active_worker = None
    view._pending_load_request = None
    sectors = {'汽车类': {'score': 12}}
    main = SimpleNamespace(current_sector_snapshot=sectors)
    monkeypatch.setattr(cls, '_main_window', lambda self: main)
    monkeypatch.setattr(dialog, 'get_app_root', lambda: str(tmp_path))
    store = module.EvaluationStore()
    store._started = True
    monkeypatch.setattr(module, 'evaluation_store', store)
    workers = []
    signal = SimpleNamespace(connect=lambda *args: None)
    def create_worker(*args, **kwargs):
        worker = SimpleNamespace(sector_snapshot=kwargs['sector_snapshot'], loaded=signal,
            finished=signal, deleteLater=lambda: None, start=lambda: None)
        workers.append(worker)
        return worker
    monkeypatch.setattr(dialog, 'NextDayWatchDataLoaderWorker', create_worker)
    monkeypatch.setattr(dialog, '_is_market_session_active', lambda: False)
    view.tab_widget = SimpleNamespace(currentIndex=lambda: 0)
    view.auto_refresh_timer = SimpleNamespace(interval=lambda: 60000)
    monkeypatch.setattr(view, 'isVisible', lambda: True)
    monkeypatch.setattr(view, 'reload_all_data', lambda: view._start_data_load((day, False)))
    for method in ('_on_dates_scanned', '_on_manifest_loaded', '_on_eval_loaded', '_on_stats_loaded'):
        monkeypatch.setattr(view, method, lambda *args: None)
    try:
        view._start_data_load((day, False))
        assert getattr(view, '_manifest_sector_source', None) is None
        view._on_loader_result({'error': 'temporary unavailable'}, workers[0])
        view._on_loader_finished(workers[0])
        view._last_manifest_refresh -= 31
        view._on_auto_refresh_tick()
        assert len(workers) == 2
        view._on_loader_result({'target_date': day}, workers[1])
        assert view._manifest_sector_source is sectors
        view._on_loader_finished(workers[1])
        view._last_manifest_refresh -= 31
        view._on_auto_refresh_tick()
        assert len(workers) == 2
        requests = []
        view.tab_widget = SimpleNamespace(currentIndex=lambda: 1)
        monkeypatch.setattr(view, '_request_data_load', lambda *args, **kwargs: requests.append((args, kwargs)))
        view._on_auto_refresh_tick()
        assert requests == [((day,), {'eval_only': True})]
        monkeypatch.setattr(view, 'isVisible', lambda: False)
        view._on_auto_refresh_tick()
        assert len(requests) == 1
    finally:
        view.close()
        app.processEvents()


def test_strategy_config_cache_reuses_and_detects_concurrent_replacement(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from ats import intraday_strategy_engine as strategy_module
    engine = object.__new__(strategy_module.IntradayStrategyEngine)
    engine.config_path = str(tmp_path / 'strategies.json')
    engine._lock = threading.RLock()
    engine._config_version = None
    engine.clean_invalid_strategies = lambda: 0
    path = Path(engine.config_path)
    path.write_text('{"strategies": [{"id": "first"}]}', encoding='utf-8')
    original_load = json.load
    reads = []
    def counted_load(stream):
        reads.append(stream.name)
        return original_load(stream)
    monkeypatch.setattr(strategy_module.json, 'load', counted_load)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(lambda _: engine.load_config(), range(16)))
    assert len(reads) == 1 and engine.strategies[0]['id'] == 'first'
    # Replace after parsing but before load_config records its cache version.
    engine._config_version = None
    replacement = tmp_path / 'replacement.json'
    replacement.write_text('{"strategies": [{"id": "second-version"}]}', encoding='utf-8')
    def replace_after_parse():
        os.replace(str(replacement), str(path))
        engine.clean_invalid_strategies = lambda: 0
        return 0
    engine.clean_invalid_strategies = replace_after_parse
    assert engine.load_config() and engine.strategies[0]['id'] == 'first'
    assert engine.load_config() and engine.strategies[0]['id'] == 'second-version'
    assert engine.load_config() and len(reads) == 3


def test_reopening_sbc_reuses_data_and_period_change_fetches_once(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QWidget
    from ats.ui import intraday_strategy_dialog as sbc
    app = QApplication.instance() or QApplication([])
    subscriptions = []
    dispatcher = SimpleNamespace(subscribe=lambda dlg: subscriptions.append(dlg._current_period_mode))
    manager = SimpleNamespace(update_period=lambda *args: None)
    monkeypatch.setattr(sbc.SBCGlobalDispatcher, 'get_instance', classmethod(lambda cls: dispatcher))
    monkeypatch.setattr(sbc.SBCWindowMemoryManager, 'get_instance', classmethod(lambda cls: manager))
    monkeypatch.setattr(sbc, 'sys', SimpleNamespace(platform='test'))
    monkeypatch.setattr(sbc, 'resolve_stock_name', lambda code: '')
    class Window(QWidget):
        set_period_mode = sbc.SBCIntradayChartDialog.set_period_mode
        _save_sbc_geometry = lambda self: None
        def reload_chart(self):
            self.reloads += 1
        def showEvent(self, event):
            super().showEvent(event)
            if self._dispatcher_enabled:
                dispatcher.subscribe(self)
    window = Window()
    window.code = '688185'
    window._current_period_mode = '10d'
    window._dispatcher_enabled = False
    window.reloads = 0
    monkeypatch.setattr(sbc, 'find_existing_sbc_window_by_code', lambda code: window)
    try:
        for _ in range(2):
            assert sbc.open_sbc_chart_dialog(code=window.code, period_mode='10d', record_open=False) is window
        assert window.reloads == 0
        sbc.open_sbc_chart_dialog(code=window.code, period_mode='5d', record_open=False)
        assert window.reloads == 1
        window.hide()
        window._dispatcher_enabled = True
        sbc.open_sbc_chart_dialog(code=window.code, period_mode='3d', record_open=False)
        assert subscriptions == ['3d'] and window.reloads == 1
        sbc.open_sbc_chart_dialog(code=window.code, period_mode='10d', record_open=False)
        assert subscriptions == ['3d', '10d'] and window.reloads == 1
    finally:
        window.close()
        app.processEvents()


def test_index_large_cumulative_amount_survives_cache_roundtrip(monkeypatch):
    import pandas as pd
    from ats.tdx_realtime_fetcher import TDXGlobalCachePool
    from ats.new_stock_fetcher import NewStockFetcher
    pool = object.__new__(TDXGlobalCachePool)
    pool._mutex = threading.RLock()
    pool._current_date_str = '2026-09-30'
    pool._incremental_intraday_pool = {}
    pool._multi_day_df_cache = {}
    pool._cache_generations = {}
    pool._dirty_revision = 0
    pool._maybe_sync_from_ramdisk = lambda **kwargs: None
    pool._check_date_rollover = lambda: None
    pool._has_complete_frame = lambda *args, **kwargs: True
    pool._has_complete_sessions = lambda *args, **kwargs: True
    monkeypatch.setattr(NewStockFetcher, 'get_instance', classmethod(
        lambda cls: SimpleNamespace(_cached_ipo_dict={})))
    frame = pd.DataFrame({'date': ['2026-09-30'] * 2, 'time_only': ['14:59', '15:00'],
                          'cum_vol_shares': [1e8, 1e8], 'cum_amt': [8.63e11, 8.63e11]})
    for code, amount in [('999688', 8.63e11), ('399005', 1.12e12), ('688185', 8.63e11)]:
        pool.set_incremental_intraday(code, 10, frame, '15:00', 2, 1e8, amount)
        history = {'records': frame.to_dict('records'), 'date': pool._current_date_str,
                   'days': 10, 'last_cum_amt': amount, 'last_cum_vol': 1e8}
        assert pool._validate_history_entry(code, history, pool._current_date_str) == (code != '688185')
    assert ('688185', 10) not in pool._incremental_intraday_pool
    for key, entry in pool._incremental_intraday_pool.items():
        assert pool._validate_incremental_entry(key, entry, pool._current_date_str)
        assert not pool._validate_incremental_entry(key, dict(entry, last_cum_amt=float('nan')), pool._current_date_str)
    assert len(pool._incremental_intraday_pool) == 2


def test_sbc_offhours_skips_heartbeat_but_applies_new_period_batch(monkeypatch):
    from JohnsonUtil import commonTips as cct
    from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
    monkeypatch.setattr(cct, 'get_work_time', lambda: False)
    fetched, applied = [], []
    window = SimpleNamespace(isVisible=lambda: True, _has_initial_loaded=True,
        _current_period_mode='5d', _load_epoch=0, code='688185',
        _do_fetch_chart_data=lambda **kwargs: fetched.append(kwargs) or {},
        _apply_chart_payload=lambda payload, **kwargs: applied.append(payload))
    SBCIntradayChartDialog.reload_chart(window, is_timer_tick=True, force_sync=True)
    assert not fetched
    batch = {'modes': ['5d']}
    SBCIntradayChartDialog.reload_chart(window, is_timer_tick=True, force_sync=True, preloaded=batch)
    assert len(fetched) == len(applied) == 1 and fetched[0]['preloaded'] is batch


def test_pioneer_single_and_double_click_dispatch_once():
    from ats.ui.capital_dragon_panel import CapitalDragonPanel
    linked, opened, notified = [], [], []
    main = SimpleNamespace(link_stock=lambda *args: linked.append(args),
                           open_sbc_for_stock=lambda *args: opened.append(args))
    panel = SimpleNamespace(main_window=main,
        stock_selected=SimpleNamespace(emit=main.link_stock),
        stock_double_clicked=SimpleNamespace(emit=lambda *args: notified.append(args)),
        open_sbc_chart=lambda *args: opened.append(args))
    CapitalDragonPanel._on_pioneer_clicked(panel, '688185', '测试')
    CapitalDragonPanel._on_pioneer_double_clicked(panel, '688185', '测试')
    assert linked == opened == notified == [('688185', '测试')]
