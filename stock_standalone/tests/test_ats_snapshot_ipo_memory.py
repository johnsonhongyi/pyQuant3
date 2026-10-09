"""Packaged snapshot handoff and IPO resident-memory regressions only."""
import gc
import json
import threading
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QObject, Qt, pyqtSignal, QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QMenu


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_snapshot_menu_freezes_ten_codes_before_disk_changes(qapp, monkeypatch):
    import run_sbc
    from ats.ui.universe_widget import UniverseTreeWidget
    from ats.ui.sbc_launcher import SBCProcessManager
    selected = dict(codes=[f'60010{i}' for i in range(10)], windows=[dict(code='600100')])
    snapshots = [selected]
    manager = MagicMock()
    monkeypatch.setattr(run_sbc, 'get_launcher_history_snapshots', lambda: snapshots)
    monkeypatch.setattr(SBCProcessManager, 'get_instance', lambda: manager)
    state = SimpleNamespace(_update_launcher_btn_state=MagicMock(), _notify_status=MagicMock())
    menu = QMenu()
    UniverseTreeWidget._append_snapshots_menu(state, menu)
    selected['codes'] = ['600733']
    menu.actions()[0].menu().actions()[0].trigger()
    payload = manager.launch_holdings_watcher.call_args.kwargs['snapshot_data']
    assert payload['codes'] == [f'60010{i}' for i in range(10)]


def test_packaged_child_receives_complete_selected_snapshot(monkeypatch, tmp_path):
    import run_sbc
    from ats.ui import sbc_launcher as launcher
    exe = tmp_path / 'ATS_Terminal.exe'
    exe.touch()
    monkeypatch.setattr(launcher.sys, 'executable', str(exe))
    monkeypatch.setattr(launcher.sys, 'frozen', True, raising=False)
    monkeypatch.setenv('_MEIPASS2', 'parent-unpack-dir')
    monkeypatch.setenv('PYINSTALLER_RESET_ENVIRONMENT', '1')
    monkeypatch.setattr(launcher.tempfile, 'gettempdir', lambda: str(tmp_path))
    monkeypatch.setattr(launcher, 'is_packaged_env', lambda: True)
    monkeypatch.setattr(launcher, 'get_app_root', lambda: str(tmp_path))
    monkeypatch.setattr(launcher, '_open_sbc_log', lambda *args: launcher.subprocess.DEVNULL)
    monkeypatch.setattr(launcher, '_get_sbc_log_path', lambda *args: str(tmp_path / 'unused'))
    monkeypatch.setattr(run_sbc, '_get_launcher_layout_cfg_path', lambda: str(tmp_path / 'layout.json'))
    popen = MagicMock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', popen)
    manager = launcher.SBCProcessManager()
    snapshot = dict(codes=[f'60010{i}' for i in range(10)], windows=[dict(code='600100')])
    try:
        manager.launch_holdings_watcher(snapshot_idx=2, snapshot_data=snapshot)
        cmd = popen.call_args.args[0]
        assert cmd[:5] == [str(exe), '--sbc-hold', '--snapshot', '2', '--snapshot-file']
        assert json.loads(Path(cmd[5]).read_text(encoding='utf-8')) == snapshot
        env = popen.call_args.kwargs['env']
        assert 'SBC_RESTORE_SNAPSHOT' not in env
        received = json.loads(Path(cmd[5]).read_text(encoding='utf-8'))
        assert len(run_sbc._snapshot_window_items(received)) == 10
        assert env['SBC_LAYOUT_CONFIG_PATH'] == str(tmp_path / 'layout.json')
        assert 'PYINSTALLER_RESET_ENVIRONMENT' not in env
        assert '_MEIPASS2' not in env
        assert env['ATS_SBC_LOG_PATH'] == str(tmp_path / 'unused')
    finally:
        for proc in manager._procs.values():
            manager._cleanup_process_files(proc)
        manager._procs.clear()
        launcher.atexit.unregister(manager._close_at_exit)


@pytest.mark.parametrize('corrupt', [False, True])
def test_snapshot_file_precedes_environment_and_has_legacy_fallback(monkeypatch, tmp_path, corrupt):
    import run_sbc
    snapshot = {'codes': [f'60010{i}' for i in range(8)]}
    path = tmp_path / 'selected.json'
    path.write_text('{' if corrupt else json.dumps(snapshot), encoding='utf-8')
    monkeypatch.setenv('SBC_RESTORE_SNAPSHOT', json.dumps(snapshot if corrupt else {'codes': ['600733']}))
    assert run_sbc._consume_restore_snapshot(str(path)) == snapshot


@pytest.mark.parametrize('gbk', [False, True])
def test_real_qt_restores_eight_codes_with_windowed_stdio(tmp_path, gbk):
    import os
    import subprocess
    import sys
    script = r'''
import os, sys, time, io
from unittest.mock import patch
out = sys.stdout
sys.argv = [sys.argv[0], '--sbc-hold']
legacy_stream = io.TextIOWrapper(io.BytesIO(), encoding='gbk') if os.environ.get('SBC_PROBE_GBK') == '1' else None
for name in ('stdout','stderr','__stdout__','__stderr__'): setattr(sys, name, legacy_stream)
from ats.subprocess_stdio import ensure_sbc_stdio
ensure_sbc_stdio()
assert sys.stdout is not None and sys.stderr is not None
assert sys.stdout.encoding == 'utf-8'
print('\U0001f4c2 快照恢复验证', flush=True)
import run_sbc
from ats.ui import intraday_strategy_dialog as ui
from ats.intraday_strategy_engine import IntradayStrategyEngine as E
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher as F, TDXGlobalCachePool as P
from ats.new_stock_fetcher import NewStockFetcher as N
from PyQt6.QtWidgets import QApplication
patches = []
for obj,names in [(E,['load_config','load_intraday_cache','_cleanup_legacy_tmp_files','_on_process_exit']),
                  (N,['refresh_ipo_calendar_background']), (F,['_init_best_server','connect']),
                  (P,['_load_from_ramdisk']), (ui.SBCGlobalDispatcher,['start']),
                  (run_sbc,['rearrange_all_sbc_windows','save_launcher_holdings_windows']),
                  (ui,['_persist_sbc_recent_codes'])]:
    for name in names:
        p = patch.object(obj, name, lambda *a, **k: None)
        p.start(); patches.append(p)
app = QApplication([])
codes = [f'60010{i}' for i in range(8)]
restored = run_sbc.restore_launcher_holdings_windows(snapshot_data={'codes': codes, 'windows': []})
deadline = time.monotonic() + 8
while run_sbc._is_restoring_holdings and time.monotonic() < deadline: app.processEvents()
assert [w.code for w in restored] == codes, [w.code for w in restored]
assert len({id(w) for w in restored}) == 8
print('real Qt windows: 8 distinct codes', file=out, flush=True)
sys.stdout.flush()
os._exit(0)
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', ATS_SYNTHETIC_QT_WORKLOAD='1',
               SBC_PROBE_GBK='1' if gbk else '0',
               SBC_IS_HOLDINGS_LAUNCHER='1', SBC_LAYOUT_CONFIG_PATH=str(tmp_path / 'layout.json'),
               ATS_SBC_LOG_PATH=str(tmp_path / 'startup.txt'))
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', script], env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr or (tmp_path / 'startup.txt').read_text(encoding='utf-8')[-1600:]
    assert '8 distinct codes' in result.stdout


def test_ipo_reuses_history_without_duplicate_frame(monkeypatch):
    from ats.strategy.ipo_vwap_detector_engine import IPOVWAPDetectorEngine, batch_fetch_60m_kline_fast
    from ats.new_stock_fetcher import NewStockFetcher
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
    frame = pd.DataFrame(dict(date=['2026-09-30', '2026-10-08'], close=[12.3456789012345, 13.]))
    engine = IPOVWAPDetectorEngine.__new__(IPOVWAPDetectorEngine)
    engine.fetcher = SimpleNamespace(fetch_multi_day_intraday_bars=lambda *a, **k: frame)
    engine._history_multi_day_cache = {}
    monkeypatch.setattr(NewStockFetcher, 'get_instance', lambda: SimpleNamespace(_cached_ipo_dict={}))
    result, _ = engine._fetch_multi_day_bars_fast('600108')
    assert result is frame and not engine._history_multi_day_cache
    fetcher = TDXRealtimeFetcher.__new__(TDXRealtimeFetcher)
    fetcher.fetch_kline_bars = lambda *a, **k: frame
    assert batch_fetch_60m_kline_fast(['600108'], fetcher=fetcher)['600108'] is frame
    custom = SimpleNamespace(fetch_kline_bars=lambda *a, **k: frame)
    independent = batch_fetch_60m_kline_fast(['600108'], fetcher=custom)['600108']
    independent.loc[0, 'close'] = 0.
    assert frame.loc[0, 'close'] == 12.3456789012345


def test_ipo_stream_queues_one_latest_snapshot_on_gui_thread(qapp):
    from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
    from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal

    class Harness(QObject):
        _stream_ui_update_requested = pyqtSignal(object)
        _run_stream_ui_update = IPOSubnewDetectorDialog._run_stream_ui_update
        _on_tk_stream_data = IPOSubnewDetectorDialog._on_tk_stream_data

    state = Harness()
    state.ipc_df = None
    state._stream_ui_lock = threading.Lock()
    state._stream_ui_pending = False
    state._check_is_trading_time = lambda: (True, '')
    state._stream_ui_update_requested.connect(state._run_stream_ui_update, Qt.ConnectionType.QueuedConnection)
    state.table = SimpleNamespace(rowCount=lambda: 1, item=lambda *args: SimpleNamespace(text=lambda: '600108'))
    state.signals_map = {'600108': VWAPDetectorSignal(code='600108', name='test')}
    updates, refs = [], []
    state._update_table_row_data = lambda sig, **kwargs: updates.append((sig.price, threading.get_ident()))

    def publish():
        for price in range(1, 21):
            frame = pd.DataFrame({'trade': [float(price)]}, index=['600108'])
            refs.append(weakref.ref(frame))
            state._on_tk_stream_data(frame)

    worker = threading.Thread(target=publish)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    gc.collect()
    assert all(ref() is None for ref in refs[:-1])
    qapp.processEvents()
    assert updates == [(20., threading.get_ident())]
    assert not state._stream_ui_pending


def test_finished_scan_worker_clears_only_its_own_reference(qapp):
    from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog

    class Harness(QObject):
        _on_scan_worker_finished = IPOSubnewDetectorDialog._on_scan_worker_finished

    class Worker(QObject):
        finished = pyqtSignal()

    state, old, current = Harness(), Worker(), Worker()
    old.finished.connect(state._on_scan_worker_finished)
    state.worker = current
    old.finished.emit()
    assert state.worker is current
    current.finished.connect(state._on_scan_worker_finished)
    current.finished.emit()
    assert state.worker is None
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
