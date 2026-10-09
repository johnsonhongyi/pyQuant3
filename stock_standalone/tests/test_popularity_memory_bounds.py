"""Only snapshot ownership, bounded delivery and lightweight name resolution."""
import gc
import pickle
import struct
import threading
import weakref
from types import SimpleNamespace

import numpy as np
import pandas as pd

from ipc_sync_manager import IPCSyncManager


def manager_with_frame(frame):
    manager = IPCSyncManager()
    manager._send_received_feedback = lambda *args: None
    manager.current_df = frame
    return manager


def test_selected_callback_preserves_complete_baseline_and_precision():
    prices = [10.1234567890123, 300.9876543210987]
    frame = pd.DataFrame({'trade': prices, 'ma20d': [9.8, 290.0],
                          'category': ['银行', '半导体']}, index=['000001', '688146'])
    manager = manager_with_frame(frame.copy())
    manager.callback_codes_provider = lambda: ('000001',)
    delivered = []
    manager.data_callback = delivered.append
    manager._process_data_package({'type': 'UPDATE_DF_ALL', 'data': frame})
    pd.testing.assert_frame_equal(delivered[-1], manager.get_current_df(['000001']))
    assert delivered[-1].loc['000001', 'trade'] == prices[0]
    delivered[-1].loc['000001', 'trade'] = -1
    assert manager.get_current_df().loc['000001', 'trade'] == prices[0]
    manager.callback_codes_provider = lambda: ('688146',)
    manager._process_data_package({'type': 'UPDATE_DF_DIFF', 'data':
                                  pd.DataFrame({'trade': [301.123456789]}, index=['688146'])})
    assert delivered[-1].loc['688146', 'ma20d'] == 290.0
    assert delivered[-1].loc['688146', 'category'] == '半导体'
    assert delivered[-1].loc['688146', 'trade'] == 301.123456789
    assert len(manager.get_current_df()) == 2
    assert manager.get_current_df([]).empty
    manager.callback_codes_provider = None
    manager._process_data_package({'type': 'UPDATE_DF_ALL', 'data': frame})
    assert len(delivered[-1]) == 2


def test_fragmented_pickle_buffer_released_before_callback():
    body = {'type': 'UPDATE_DF_ALL', 'data': pd.DataFrame({'trade': [10.123456789]}, index=['000001'])}
    payload = pickle.dumps(('UPDATE_DF_DATA', body))
    class Connection:
        def __init__(self):
            self.parts = [b'DATA', struct.pack('!I', len(payload))]
            self.body = payload
            self.closed = False
        def settimeout(self, timeout):
            pass
        def recv(self, size):
            if self.parts:
                return self.parts.pop(0)
            chunk, self.body = self.body[:min(size, 17)], self.body[min(size, 17):]
            return chunk
        def close(self):
            self.closed = True
    manager = manager_with_frame(None)
    seen = []
    def accept(package):
        import inspect
        assert 'data' not in inspect.currentframe().f_back.f_locals
        seen.append(package)
    manager._process_data_package = accept
    conn = Connection()
    manager._handle_client(conn)
    assert conn.closed and len(seen) == 1
    pd.testing.assert_frame_equal(seen[0]['data'], body['data'])


def gui_harness():
    from popularity_resonance_gui import PRServiceGUI
    gui = PRServiceGUI.__new__(PRServiceGUI)
    gui._shutdown_event = threading.Event()
    gui.df_lock = threading.Lock()
    gui._realtime_ui_lock = threading.Lock()
    gui._realtime_ui_pending = False
    gui._pending_tdx_quotes = {}
    gui._pending_ui_actions = set()
    gui._popularity_codes_snapshot = ()
    gui._ipc_sync_manager = None
    gui.current_df = None
    gui._last_data_cache = {'em_data': {'000001': 1, '000002': 2},
                            'resonance_results': [{'code': '688146'}]}
    gui.resonance_codes = []
    gui.get_all_displayed_codes = lambda: ['000001']
    gui._get_current_tdx_interval = lambda: 5.0
    gui._is_tdx_auto_refresh_enabled = lambda: True
    gui._ipc_baseline_ready = threading.Event()
    return gui


def test_background_burst_retains_only_latest_frame_and_one_tk_timer():
    gui = gui_harness()
    owner_thread = threading.get_ident()
    timers, updates, refs, actions = [], [], [], []
    def after(delay, callback):
        assert threading.get_ident() == owner_thread
        timers.append((delay, callback))
        return len(timers)
    gui.root = SimpleNamespace(after=after)
    gui._on_ipc_baseline_received = lambda: actions.append('baseline')
    gui.refresh_realtime_fields = lambda frame, quotes: updates.append((frame, quotes, threading.get_ident()))
    index = [f'{c:06d}' for c in range(1, 1001)]
    def publish():
        for tick in range(100):
            frame = pd.DataFrame(np.full((1000, 32), float(tick)), index=index)
            refs.append(weakref.ref(frame))
            gui._on_ipc_data_updated(frame)
            gui._queue_realtime_update({'000001': {'price': float(tick)}})
    worker = threading.Thread(target=publish)
    worker.start()
    worker.join(5)
    assert not worker.is_alive() and not timers
    gc.collect()
    assert all(ref() is None for ref in refs[:-1])
    gui._drain_realtime_updates()
    assert len(timers) == 1 and len(updates) == 1 and actions == ['baseline']
    frame, quotes, thread_id = updates[0]
    assert thread_id == owner_thread and len(frame) == 2
    assert frame.loc['000001', 0] == 99.0 and quotes['000001']['price'] == 99.0
    assert '000002' in gui._popularity_codes_snapshot  # 完整池包含被 Treeview 过滤的股票。
    assert frame.memory_usage(deep=True).sum() < gui.current_df.memory_usage(deep=True).sum() / 100
    gui._shutdown_event.set()
    timers[-1][1]()
    assert len(timers) == 1


def test_gui_keeps_small_pool_while_full_public_snapshot_remains_compatible():
    gui = gui_harness()
    baseline = pd.DataFrame({'trade': [10.123456789, 20.987654321],
                             'ma20d': [9.0, 19.0], 'category': ['银行', '芯片']},
                            index=['000001', '688146'])
    gui._ipc_sync_manager = manager_with_frame(baseline.copy())
    gui.current_df = baseline.loc[['000001']].copy()
    gui.current_df.loc['000001', 'trade'] = 11.123456789
    complete = gui.get_current_df()
    assert list(complete.index) == list(baseline.index)
    assert list(complete.columns) == list(baseline.columns)
    assert complete.loc['000001', 'trade'] == 11.123456789
    assert complete.loc['688146', 'trade'] == 20.987654321
    assert gui.get_current_df(['688146']).loc['688146', 'ma20d'] == 19.0
    complete.loc['688146', 'ma20d'] = -1
    pd.testing.assert_frame_equal(gui._ipc_sync_manager.current_df, baseline)


def test_gui_preserves_tdx_only_rows_fields_and_snapshot_isolation():
    gui = gui_harness()
    baseline = pd.DataFrame({'trade': [10.1234567890123], 'ma20d': [9.]}, index=['000001'])
    local = pd.DataFrame({'trade': [11.1234567890123, 22.9876543210987],
                          'ma20d': [9., 21.], 'vwap': [10.9876543210987, 21.1234567890123]},
                         index=['000001', '688146'])
    gui._ipc_sync_manager = manager_with_frame(baseline.copy())
    gui.current_df = local.copy()
    for codes in (None, ['000001', '688146'], ['000001'], ['688146'], []):
        result = gui.get_current_df(codes)
        expected = local if codes is None else local.loc[local.index.isin(codes)]
        pd.testing.assert_frame_equal(result, expected)
        if not result.empty:
            result.loc[result.index[0], ['trade', 'vwap']] = -1.
        pd.testing.assert_frame_equal(gui.current_df, local)
        pd.testing.assert_frame_equal(gui._ipc_sync_manager.current_df, baseline)


def test_lightweight_name_resolution_skips_sina_and_hdf(monkeypatch, tmp_path):
    import builtins
    import http.client
    import sys_utils
    original_import = builtins.__import__
    heavy_imports = []
    def guarded_import(name, *args, **kwargs):
        if name in ('JSONData.sina_data', 'JSONData.tdx_hdf5_api') or (
            name == 'JSONData' and 'sina_data' in (kwargs.get('fromlist') or (args[2] if len(args) > 2 else ()))
        ):
            heavy_imports.append(name)
        assert name not in ('JSONData.sina_data', 'JSONData.tdx_hdf5_api')
        if name == 'JSONData':
            assert 'sina_data' not in (kwargs.get('fromlist') or (args[2] if len(args) > 2 else ()))
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    monkeypatch.setattr(sys_utils, '_resolved_name_cache', {})
    monkeypatch.setattr(sys_utils, '_name_resolution_retry_after', {})
    monkeypatch.setattr(sys_utils, 'get_app_root', lambda: str(tmp_path))
    monkeypatch.setattr(sys_utils.os.path, 'exists', lambda path: str(path).endswith('top_all.h5'))
    saved = {}
    monkeypatch.setattr(sys_utils, '_save_to_name_cache', lambda code, name, **kw: saved.update({code: name}))
    response = SimpleNamespace(status=200, read=lambda: 'var hq_str_sh600731="湖南海利,10,10";'.encode('gbk'))
    monkeypatch.setattr(http.client, 'HTTPConnection', lambda *a, **kw:
                        SimpleNamespace(request=lambda *a, **kw: None, getresponse=lambda: response, close=lambda: None))
    assert sys_utils.resolve_stock_name('600731', allow_heavy=False) == '湖南海利'
    assert saved == {'600731': '湖南海利'}
    assert not heavy_imports
