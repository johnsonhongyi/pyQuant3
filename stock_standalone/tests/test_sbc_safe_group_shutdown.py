from types import SimpleNamespace
from unittest.mock import MagicMock
import subprocess

import pytest


def test_group_save_precedes_all_window_closes_and_cache_checkpoint(monkeypatch):
    import run_sbc
    calls, properties = [], {}
    class Window:
        _sbc_alt_close_in_progress = False
        def __init__(self, index): self.index = index
        def close(self): calls.append(('close', self.index))
    windows = [Window(i) for i in range(13)]
    app = SimpleNamespace(property=properties.get,
        setProperty=lambda k, v: properties.__setitem__(k, v),
        topLevelWidgets=lambda: windows, quit=lambda: calls.append('quit'))
    monkeypatch.setattr(run_sbc, 'QApplication', SimpleNamespace(instance=lambda: app))
    monkeypatch.setattr(run_sbc, 'SBCIntradayChartDialog', Window)
    monkeypatch.setattr(run_sbc, 'save_launcher_holdings_windows', lambda **kw: calls.append('layout') or True)
    monkeypatch.setattr(run_sbc, 'persist_sbc_runtime_caches', lambda: calls.append('caches') or True)
    monkeypatch.setenv('SBC_IS_HOLDINGS_LAUNCHER', '1')
    run_sbc.quit_and_save_all_sbc_windows()
    assert calls == ['layout'] + [('close', i) for i in range(13)] + ['caches', 'quit']
    assert properties['_sbc_save_complete'] is True
    run_sbc.quit_and_save_all_sbc_windows()
    assert calls.count('layout') == calls.count('caches') == 1


@pytest.mark.parametrize('saved', [True, False])
def test_packaged_watchdog_only_after_confirmed_persistence(monkeypatch, tmp_path, saved):
    import run_sbc
    import ats.ui.styles as styles
    import sys_utils
    import ats.shutdown as shutdown
    from ats.bounded_evaluation_store import evaluation_store
    receipt = tmp_path / 'saved'
    monkeypatch.setenv('ATS_SBC_SAVED_PATH', str(receipt))
    monkeypatch.setattr(styles, 'flush_config_writer', lambda **kw: saved)
    monkeypatch.setattr(evaluation_store, 'flush', lambda **kw: True)
    monkeypatch.setattr(sys_utils, 'is_packaged_env', lambda: True)
    watchdog = MagicMock()
    monkeypatch.setattr(shutdown, 'start_exit_watchdog', watchdog)
    assert run_sbc._finish_sbc_packaged_shutdown(SimpleNamespace(property=lambda k: True), 0) == saved
    assert receipt.exists() == saved
    assert watchdog.called == saved


@pytest.mark.parametrize('forced', [False, True])
def test_parent_uses_group_request_and_requires_saved_receipt(monkeypatch, tmp_path, forced):
    from ats.ui.sbc_launcher import SBCProcessManager
    request, receipt = tmp_path / 'request', tmp_path / 'saved'
    proc = SimpleNamespace(pid=123, returncode=0, stdout=None, stderr=None, stdin=None,
        _sbc_shutdown_path=str(request), _sbc_saved_path=str(receipt), poll=lambda: 0)
    waits = []
    def wait(timeout):
        assert request.read_text() == 'save-and-close'
        waits.append(timeout)
        if forced and len(waits) == 1:
            raise subprocess.TimeoutExpired('sbc', timeout)
        if forced:
            proc.returncode = 1
        else:
            receipt.write_text('saved')
    proc.wait = wait
    manager = SimpleNamespace(_sbc_bootloader_children=lambda proc: [],
        _cleanup_process_files=MagicMock(), _signal_sbc_process=MagicMock())
    # 新协议不应导入 Win32 扫窗、逐窗 WM_CLOSE 或父进程抢写窗口布局。
    assert SBCProcessManager._close_launcher_subprocess(manager, proc) == (not forced)
    assert waits[0] == 20.


def test_background_close_failure_is_not_lost():
    from ats.ui.sbc_launcher import SBCProcessManager
    manager = SimpleNamespace(_close_workers=[], _closing_processes={}, _close_failures=[], _procs={})
    proc = SimpleNamespace(pid=123, poll=lambda: 0)
    assert SBCProcessManager._start_close_worker(manager, lambda proc: False, proc)
    manager._close_workers[0].join(2)
    assert manager._close_failures


@pytest.mark.parametrize('alt', [False, True])
def test_single_close_and_alt_group_close_keep_existing_semantics(monkeypatch, alt):
    import run_sbc
    from ats.ui import intraday_strategy_dialog as sbc
    from PyQt6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    app.setProperty('is_app_exiting', False)
    window = sbc.SBCIntradayChartDialog.__new__(sbc.SBCIntradayChartDialog)
    QWidget.__init__(window)
    window.code = '012345'
    window._do_save_sbc_geometry = MagicMock()
    window.is_ats_sbc_mode = lambda: False
    monkeypatch.setattr(sbc, 'is_alt_modifier_active', lambda: alt)
    monkeypatch.setattr(sbc.SBCWindowMemoryManager, 'get_instance', lambda: SimpleNamespace(unregister=lambda w: None))
    monkeypatch.setenv('SBC_IS_HOLDINGS_LAUNCHER', '1')
    group, save = MagicMock(), MagicMock()
    monkeypatch.setattr(run_sbc, 'quit_and_save_all_sbc_windows', group)
    monkeypatch.setattr(run_sbc, 'save_launcher_holdings_windows', save)
    window.close()
    assert group.called == alt
    save.assert_not_called()


def test_parent_rejects_clean_process_exit_without_save_receipt(tmp_path):
    from ats.ui.sbc_launcher import SBCProcessManager
    proc = SimpleNamespace(pid=123, returncode=0, stdout=None, stderr=None, stdin=None,
        _sbc_shutdown_path=str(tmp_path / 'request'), _sbc_saved_path=str(tmp_path / 'absent'),
        poll=lambda: 0, wait=lambda **kw: None)
    manager = SimpleNamespace(_sbc_bootloader_children=lambda proc: [], _cleanup_process_files=MagicMock())
    assert not SBCProcessManager._close_launcher_subprocess(manager, proc)


@pytest.mark.parametrize('dirty, engine_ok, expected', [(True, True, False), (False, True, True), (False, False, False)])
def test_runtime_cache_failure_cannot_be_reported_as_saved(monkeypatch, dirty, engine_ok, expected):
    import run_sbc
    from ats.tdx_realtime_fetcher import TDXGlobalCachePool
    from ats.intraday_strategy_engine import IntradayStrategyEngine
    monkeypatch.setattr(TDXGlobalCachePool, '_instance', SimpleNamespace(
        _is_dirty=dirty, flush_to_ramdisk=lambda **kw: False))
    monkeypatch.setattr(IntradayStrategyEngine, '_instance', SimpleNamespace(
        save_intraday_cache=lambda **kw: engine_ok))
    assert run_sbc.persist_sbc_runtime_caches() == expected


def test_exit_layout_persists_all_open_windows_but_excludes_manually_closed(monkeypatch, tmp_path):
    import json
    import run_sbc
    from PyQt6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    windows = []
    for i in range(14):
        window = run_sbc.SBCIntradayChartDialog.__new__(run_sbc.SBCIntradayChartDialog)
        QWidget.__init__(window)
        window.code = f'{600000+i:06d}'
        window.normal_geometry = window.geometry()
        window._current_period_mode = '1m' if i % 2 else '10d'
        window._is_closing = i == 13
        windows.append(window)
    path = tmp_path / 'layout.json'
    monkeypatch.setattr(run_sbc, 'QApplication', SimpleNamespace(
        instance=lambda: SimpleNamespace(property=lambda k: True), topLevelWidgets=lambda: windows))
    monkeypatch.setattr(run_sbc, '_get_launcher_layout_cfg_path', lambda: str(path))
    monkeypatch.setattr(run_sbc, '_last_saved_content_fingerprint', None)
    monkeypatch.setattr(run_sbc, '_is_restoring_holdings', False)
    assert run_sbc.save_launcher_holdings_windows(force=True)
    data = json.loads(path.read_text(encoding='utf-8'))
    assert len(data['sbc_holdings_windows']) == 13
    assert {item['code'] for item in data['sbc_holdings_windows']} == {w.code for w in windows[:13]}
    assert {item['period_mode'] for item in data['sbc_holdings_windows']} == {'1m', '10d'}
    for window in windows:
        window.deleteLater()


@pytest.mark.parametrize('packaged', [False, True])
def test_confirmed_save_exits_even_with_stuck_non_daemon_thread(tmp_path, packaged):
    import os
    import sys
    from pathlib import Path
    receipt = tmp_path / 'saved'
    code = '''
import sys, threading, os, multiprocessing, time
from types import SimpleNamespace
import run_sbc, sys_utils
import ats.ui.styles as styles
from ats.bounded_evaluation_store import evaluation_store
styles.flush_config_writer = lambda **kw: True
evaluation_store.flush = lambda **kw: True
sys_utils.is_packaged_env = lambda: os.environ['SBC_TEST_PACKAGED'] == '1'
child = multiprocessing.get_context('spawn').Process(target=time.sleep, args=(60,), daemon=True)
child.start()
threading.Thread(target=threading.Event().wait, daemon=False).start()
assert run_sbc._finish_sbc_packaged_shutdown(SimpleNamespace(property=lambda k: True), 0)
assert not child.is_alive()
sys.exit(0)
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', ATS_SBC_SAVED_PATH=str(receipt),
               ATS_SBC_SUBPROCESS='1', SBC_TEST_PACKAGED='1' if packaged else '0')
    result = subprocess.run([sys.executable, '-c', code],
        cwd=str(Path(__file__).resolve().parents[1]), env=env,
        capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    assert receipt.read_text(encoding='utf-8') == 'saved'


def test_ats_drain_rejects_failed_sbc_close(monkeypatch):
    from ats.ui.main_window import ATSMainWindow
    from ats.ui.sbc_launcher import SBCProcessManager
    from ats.bounded_evaluation_store import evaluation_store
    import ats.ui.styles as styles
    import ats.shutdown as shutdown
    from PyQt6.QtCore import QTimer
    failures = ['forced shutdown']
    monkeypatch.setattr(SBCProcessManager, 'get_instance', lambda: SimpleNamespace(
        _close_workers=[], _close_failures=failures))
    monkeypatch.setattr(ATSMainWindow, '_drain_shutdown_voice', lambda self: True)
    monkeypatch.setattr(shutdown, 'reap_multiprocessing_children', lambda deadline: True)
    monkeypatch.setattr(styles, 'flush_config_writer', lambda **kw: True)
    monkeypatch.setattr(evaluation_store, 'flush', lambda **kw: True)
    monkeypatch.setattr(QTimer, 'singleShot', lambda *a: None)
    state = SimpleNamespace(_retry_close_after_workers=lambda: None)
    ATSMainWindow._complete_shutdown(state, SimpleNamespace(ignore=lambda: None))
    assert state._exit_cleanup_drain.done.wait(2)
    assert 'subprocess cleanup: drain failed' in state._exit_cleanup_drain.errors
    assert not getattr(state, '_exit_cleanup_complete', False)


def test_exit_checkpoint_waits_for_same_process_writer_and_accepts_clean_cache(monkeypatch):
    import threading
    import run_sbc
    from ats.tdx_realtime_fetcher import TDXGlobalCachePool
    from ats.intraday_strategy_engine import IntradayStrategyEngine
    pool = TDXGlobalCachePool.__new__(TDXGlobalCachePool)
    pool._snapshot_write_lock = threading.RLock()
    pool._is_dirty = True
    entered, release, exit_done = threading.Event(), threading.Event(), threading.Event()
    calls, results = [], []
    def write(**kwargs):
        if not pool._is_dirty:
            return False
        calls.append('write')
        entered.set()
        assert release.wait(2)
        pool._is_dirty = False
        return True
    pool._flush_to_ramdisk_serial = write
    monkeypatch.setattr(TDXGlobalCachePool, '_instance', pool)
    monkeypatch.setattr(IntradayStrategyEngine, '_instance', None)
    background = threading.Thread(target=lambda: pool.flush_to_ramdisk(force=True, history_checkpoint=True))
    def exit_save():
        results.append(run_sbc.persist_sbc_runtime_caches())
        exit_done.set()
    background.start()
    assert entered.wait(1)
    closer = threading.Thread(target=exit_save)
    closer.start()
    try:
        assert not exit_done.wait(.05)
        assert calls == ['write']
    finally:
        release.set()
        background.join(2)
        closer.join(2)
    assert results == [True]
    assert calls == ['write']


def test_dispatcher_does_not_fetch_history_after_windows_unsubscribe(monkeypatch):
    import threading
    from PyQt6.QtWidgets import QApplication
    from ats.ui import intraday_strategy_dialog as sbc
    app = QApplication.instance() or QApplication([])
    dispatcher = sbc.SBCGlobalDispatcher()
    dispatcher._subscribers = {1: (lambda: None, '600000', '10d')}
    stop, wake = threading.Event(), threading.Event()
    fetcher = MagicMock()
    def snapshots(codes):
        dispatcher._subscribers.clear()
        return {}
    fetcher.fetch_batch_stock_snapshots.side_effect = snapshots
    dispatcher._wait_or_wake = lambda *args: stop.set()
    monkeypatch.setattr(sbc.TDXRealtimeFetcher, 'get_instance', lambda: fetcher)
    monkeypatch.setattr(sbc.TDXGlobalCachePool, '_instance', MagicMock())
    dispatcher._run_loop(stop, wake)
    fetcher.fetch_multi_horizon_vwap.assert_not_called()


def test_vwap_snapshot_precedes_writer_lock(monkeypatch):
    import threading
    from ats.tdx_realtime_fetcher import TDXGlobalCachePool
    from ats.vwap_factory import VWAPFactory
    pool = TDXGlobalCachePool.__new__(TDXGlobalCachePool)
    pool._snapshot_write_lock = threading.Lock()
    def export():
        assert not pool._snapshot_write_lock.locked()
        return {'600000': {'updated_at': 1}}
    def write(**kwargs):
        assert pool._snapshot_write_lock.locked()
        assert '600000' in kwargs['vwap_states']
        return True
    monkeypatch.setattr(VWAPFactory, 'get_instance', lambda: SimpleNamespace(export_states=export))
    pool._flush_to_ramdisk_serial = write
    assert pool.flush_to_ramdisk(force=True, history_checkpoint=True)


@pytest.mark.parametrize('dirty', [False, True])
def test_real_midday_archive_gate_uses_isolated_recovery_and_can_restore(monkeypatch, tmp_path, dirty):
    import run_sbc
    import ats.bounded_evaluation_store as archive
    import ats.ui.styles as styles
    import ats.shutdown as shutdown
    import sys_utils
    store = archive.EvaluationStore()
    store._started = True
    monkeypatch.setattr(archive, 'archive_window', lambda **kwargs: (None, '2026-10-13'))
    data_path = str(tmp_path / 'signal_eval.json')
    value = {'code': '600000', 'pending': 'midday'}
    writer = MagicMock()
    if dirty:
        store.put(data_path, value, writer)
    receipt, journal = tmp_path / 'saved', tmp_path / '.sbc_holdings_recovery.json.gz'
    monkeypatch.setenv('ATS_SBC_SAVED_PATH', str(receipt))
    monkeypatch.setenv('ATS_SBC_RECOVERY_PATH', str(journal))
    monkeypatch.setattr(archive, 'evaluation_store', store)
    monkeypatch.setattr(styles, 'flush_config_writer', lambda **kwargs: True)
    monkeypatch.setattr(shutdown, 'reap_multiprocessing_children', lambda deadline: True)
    monkeypatch.setattr(shutdown, 'start_exit_watchdog', MagicMock())
    monkeypatch.setattr(sys_utils, 'is_packaged_env', lambda: True)
    assert not store.flush(force=True, require_clean=True)
    assert run_sbc._finish_sbc_packaged_shutdown(SimpleNamespace(property=lambda key: True), 0)
    assert receipt.read_text() == 'saved'
    writer.assert_not_called()  # 不绕过盘中正式归档门禁。
    if dirty:
        restored = archive.EvaluationStore()
        restored._started = True
        assert restored.restore_recovery(str(journal)) == 1
        assert restored.peek(data_path) == value
    else:
        assert not journal.exists()


def test_recovery_failure_still_blocks_receipt_and_watchdog(monkeypatch, tmp_path):
    import run_sbc
    import ats.bounded_evaluation_store as archive
    import ats.ui.styles as styles
    import ats.shutdown as shutdown
    receipt = tmp_path / 'saved'
    monkeypatch.setenv('ATS_SBC_SAVED_PATH', str(receipt))
    monkeypatch.setattr(styles, 'flush_config_writer', lambda **kwargs: True)
    monkeypatch.setattr(archive, 'evaluation_store', SimpleNamespace(
        flush=lambda **kwargs: False, persist_recovery=lambda *a, **kwargs: False))
    watchdog = MagicMock()
    monkeypatch.setattr(shutdown, 'start_exit_watchdog', watchdog)
    assert not run_sbc._finish_sbc_packaged_shutdown(SimpleNamespace(property=lambda key: True), 0)
    assert not receipt.exists()
    watchdog.assert_not_called()


def test_selective_flush_skips_nonresident_validation_and_restored_seed_checkpoint(monkeypatch, tmp_path):
    import copy
    import pandas as pd
    import ats.tdx_realtime_fetcher as tdx
    from ats.compact_cache import read_cache_payload, write_cache_payload
    from ats.new_stock_fetcher import NewStockFetcher

    cache_path = str(tmp_path / 'ramdisk.pkl.z')
    monkeypatch.setattr(tdx.TDXGlobalCachePool, '_get_ramdisk_cache_path', lambda self: cache_path)
    monkeypatch.setattr(tdx.TDXGlobalCachePool, 'is_trading_day', classmethod(lambda cls, day=None: True))
    monkeypatch.setattr(NewStockFetcher, '_instance', SimpleNamespace(_cached_ipo_dict={}))

    today = tdx.datetime.now().strftime('%Y-%m-%d')
    dates = pd.bdate_range('2026-09-23', periods=10).strftime('%Y-%m-%d').tolist()
    recs = []
    cum_v, cum_a = 0.0, 0.0
    for d in dates:
        for idx, hm in enumerate(('09:30', '10:30', '13:30', '15:00')):
            v = 1000.0
            a = 10000.0
            cum_v += v
            cum_a += a
            recs.append({
                'datetime': f'{d} {hm}', 'date': d, 'time_only': hm,
                'open': 10.0, 'close': 10.0, 'high': 10.1, 'low': 9.9,
                'vol': v, 'amount': a, 'bar_vol': v, 'bar_amt': a,
                'cum_vol_shares': cum_v, 'cum_amt': cum_a,
                'vwap': 10.0, 'vwap_1d': 10.0,
            })
    base_entry = {
        'records': recs, 'date': today, 'days': 10,
        'last_cum_vol': cum_v, 'last_cum_amt': cum_a, 'last_cum_pv': 0.0,
        'updated_at': 100.0, '_cache_generation': 1,
    }
    payload = {
        'date': today, 'version': 4, 'frozen': True,
        'history_static_bars': {
            '600108': copy.deepcopy(base_entry),
            '600109': copy.deepcopy(base_entry),
            '600110': copy.deepcopy(base_entry),
        },
        'incremental_intraday_pool': {},
        'cache_generations': {'600108': 1, '600109': 1, '600110': 1},
        'daily_metrics_cache': {'600109': {'date': today, 'metrics': {'ma5': 10.0}, 'updated_at': 100.0}},
        'shares_cache': {'600110': (1000000.0, 100.0)},
        'vwap_states': {},
        'updated_at': 100.0,
    }
    with open(cache_path, 'wb') as f:
        write_cache_payload(payload, f)

    monkeypatch.setattr(tdx.TDXGlobalCachePool, '_validate_history_entry', lambda self, k, v, d: True)
    monkeypatch.setattr(tdx.TDXGlobalCachePool, '_validate_and_repair_records',
                        lambda self, r, d, days, k: (list(r), False))

    selective = tdx.TDXGlobalCachePool(startup_codes=['600108'])
    assert selective._history_static_bars['600108'].get('_from_ramdisk') is True

    # 1. Restored static history from RamDisk must not trigger a redundant background flush on startup
    df_seed = pd.DataFrame(recs)
    selective.checkpoint_history_seed('600108', df_seed)
    assert not selective._seed_flush_inflight
    assert '600108' in selective._seed_flush_tokens

    # 2. Selective flush must not re-validate non-resident codes (600109, 600110) or even unchanged resident 600108
    validated_codes = []
    def spy_validate(self, recs_in, today_in, days_in, code_in):
        validated_codes.append(str(code_in).zfill(6))
        return list(recs_in), False
    monkeypatch.setattr(tdx.TDXGlobalCachePool, '_validate_and_repair_records', spy_validate)

    selective._is_dirty = True
    assert selective.flush_to_ramdisk(force=True, history_checkpoint=True)
    assert validated_codes == []

    saved = read_cache_payload(cache_path)
    assert set(saved['history_static_bars']) == {'600108', '600109', '600110'}
    assert '600109' in saved['daily_metrics_cache']
    assert '600110' in saved['shares_cache']


def test_save_launcher_holdings_windows_handles_missing_normal_geometry_and_concurrent_window_config(monkeypatch, tmp_path):
    import json
    import threading
    import run_sbc
    from PyQt6.QtCore import QRect
    from tk_gui_modules.window_mixin import WindowMixin

    cfg_path = tmp_path / 'sbc_holdings_layout.json'
    monkeypatch.setattr(run_sbc, '_get_launcher_layout_cfg_path', lambda: str(cfg_path))
    monkeypatch.setattr(run_sbc, '_is_restoring_holdings', False)
    monkeypatch.setattr(run_sbc, '_last_save_holdings_time', 0.0)

    class DummyHoldingsDialog:
        def __init__(self, code):
            self.code = code
            self._is_closing = False
            self.is_hidden_state = False
            self._current_period_mode = '10d'
            # Intentionally no `normal_geometry` attribute!
        def isVisible(self):
            return True
        def geometry(self):
            return QRect(100, 120, 640, 420)

    import PyQt6.sip
    win = DummyHoldingsDialog('301666')
    monkeypatch.setattr(run_sbc, 'SBCIntradayChartDialog', DummyHoldingsDialog)
    monkeypatch.setattr(PyQt6.sip, 'isdeleted', lambda w: False)
    app = SimpleNamespace(
        property=lambda key: True if key == 'is_app_exiting' else None,
        topLevelWidgets=lambda: [win],
    )
    monkeypatch.setattr(run_sbc, 'QApplication', SimpleNamespace(
        instance=lambda: app,
        topLevelWidgets=lambda: [win],
    ))
    assert run_sbc.save_launcher_holdings_windows(force=True) is True
    saved_layout = json.loads(cfg_path.read_text(encoding='utf-8'))
    assert saved_layout['sbc_holdings_windows'][0]['code'] == '301666'

    # Concurrent save_window_position_qt must use isolated temp files without collision
    win_cfg = tmp_path / 'window_config.json'
    class DummyHost(WindowMixin):
        def _get_dpi_scale_factor(self):
            return 1.0
        def _get_config_file_path(self, file_path, scale):
            return str(win_cfg)
    host = DummyHost()
    errors = []
    def worker(idx):
        try:
            qwin = SimpleNamespace(geometry=lambda: QRect(10 * idx, 20 * idx, 500, 400))
            host.save_window_position_qt(qwin, f'win_{idx}', str(win_cfg))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert not errors
    assert win_cfg.exists()
    assert not list(tmp_path.glob('*.tmp'))
