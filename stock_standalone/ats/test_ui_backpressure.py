"""Regression checks for bounded market delivery and Qt rendering recovery."""
import ast
import threading
import sys
import time
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Dict, List

import pytest


def load_methods(filename, names, namespace):
    path = Path(__file__).parent / "ui" / filename
    tree = ast.parse(path.read_text(encoding="utf-8"))
    methods = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(methods) == len(names)
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), "exec"), namespace)


def test_market_mailbox_is_bounded_and_preserves_pending_sectors():
    namespace = {}
    load_methods("main_window.py", {"_queue_latest_ipc_frame", "_consume_latest_ipc_frame"}, namespace)
    received = []
    window = SimpleNamespace(_ipc_frame_lock=threading.Lock(), _pending_ipc_frame=None,
                             _is_closing=False, _handle_realtime_data=received.append)
    for revision in range(1000):
        attrs = {"sector_data": {"sector": "latest"}} if revision == 0 else {}
        namespace["_queue_latest_ipc_frame"](window, SimpleNamespace(attrs=attrs, revision=revision))
    namespace["_consume_latest_ipc_frame"](window)
    namespace["_consume_latest_ipc_frame"](window)
    assert len(received) == 1
    assert received[0].revision == 999
    assert received[0].attrs == {"type": "UPDATE_DF_ALL", "sector_data": {"sector": "latest"}}
    namespace["_queue_latest_ipc_frame"](window, SimpleNamespace(
        attrs={"sync_session": "old", "sector_data": {"stale": True}}, revision=1))
    namespace["_queue_latest_ipc_frame"](window, SimpleNamespace(
        attrs={"sync_session": "new"}, revision=2))
    namespace["_consume_latest_ipc_frame"](window)
    assert received[-1].attrs == {"type": "UPDATE_DF_ALL", "sync_session": "new"}
    window._is_closing = True
    namespace["_queue_latest_ipc_frame"](window, SimpleNamespace(attrs={}, revision=1000))
    namespace["_consume_latest_ipc_frame"](window)
    assert len(received) == 2
    assert window._pending_ipc_frame is None


@pytest.fixture
def qt_methods(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QBrush, QColor
    app = QApplication.instance() or QApplication([])

    class Item(QTableWidgetItem):
        def __init__(self, text, **kwargs):
            super().__init__(text)

        def set_pin_status(self, *args, **kwargs):
            pass

        def set_raw_value(self, *args, **kwargs):
            pass

    namespace = dict(Optional=Optional, Any=Any, Qt=Qt, QFont=QFont, QBrush=QBrush,
                     QColor=QColor, NumericTableWidgetItem=Item)
    load_methods("new_stock_panel.py", {"_set_or_update_item", "_render_table"}, namespace)
    table = QTableWidget(1, 1)
    yield namespace, SimpleNamespace(table=table), QFont
    table.close()
    app.processEvents()


def test_unchanged_cells_do_not_emit_model_updates(qt_methods):
    namespace, panel, font = qt_methods
    changes = []
    panel.table.model().dataChanged.connect(lambda *args: changes.append(1))
    kwargs = dict(color="#00ff88", font=font("Consolas", 9), bg_color="#112233")
    update = namespace["_set_or_update_item"]
    update(panel, 0, 0, "5.12", **kwargs)
    changes.clear()
    for _ in range(100):
        update(panel, 0, 0, "5.12", **kwargs)
    assert changes == []
    update(panel, 0, 0, "5.13", **kwargs)
    assert changes == [1]


def test_render_failure_restores_previous_widget_state(qt_methods):
    namespace, panel, _ = qt_methods
    panel.table.setSortingEnabled(True)

    def failing_render():
        panel.table.blockSignals(True)
        panel.table.setSortingEnabled(False)
        raise RuntimeError("render failed")

    panel._render_table_impl = failing_render
    with pytest.raises(RuntimeError, match="render failed"):
        namespace["_render_table"](panel)
    assert panel.table.updatesEnabled()
    assert not panel.table.signalsBlocked()
    assert panel.table.isSortingEnabled()


def test_failed_ledger_result_preserves_successful_ma20_cache():
    namespace = {}
    load_methods("main_window.py", {"_on_ledger_results"}, namespace)
    rows = [("600733", "test")]
    window = SimpleNamespace(_is_closing=False, _pending_swing_rows=rows,
                             _pending_fav_rows=rows)
    namespace["_on_ledger_results"](window, [], [], 0.0, [], "")
    assert window._pending_swing_rows is rows
    assert window._pending_fav_rows is rows


def test_ma20_loaded_but_filtered_is_reported(qt_methods, monkeypatch):
    from PyQt6.QtWidgets import QLabel, QCheckBox, QTableWidgetItem
    namespace, panel, _ = qt_methods
    load_methods("swing_table.py", {"_apply_favorite_filter"}, namespace)
    manager = SimpleNamespace(get_favorite_stocks=lambda: {"600733"})
    monkeypatch.setitem(sys.modules, "global_favorites",
                        SimpleNamespace(GlobalFavoriteManager=lambda: manager))
    panel.table.setColumnCount(2)
    panel.table.setItem(0, 0, QTableWidgetItem("600733"))
    panel.table.setItem(0, 1, QTableWidgetItem("test"))
    panel.chk_favorite_show = QCheckBox()
    panel.data_status = QLabel()
    panel._get_parent_mw = lambda: None
    namespace["_apply_favorite_filter"](panel)
    assert panel.table.isRowHidden(0)
    assert "1" in panel.data_status.text()
    panel.chk_favorite_show.setChecked(True)
    namespace["_apply_favorite_filter"](panel)
    assert not panel.table.isRowHidden(0)
    assert "1 / 1" in panel.data_status.text()


def test_hidden_and_forced_refresh_never_replay_an_older_frame(qt_methods):
    import pandas as pd
    from PyQt6.QtCore import QTimer
    from types import MethodType
    namespace = dict(pd=pd, QTimer=QTimer, clean_num=lambda x, default=0: float(x or default),
                     get_new_stock_extra_cols=lambda: [], cct=SimpleNamespace(vis_column_map={}))
    names = {"update_from_ipc_df", "_flush_ipc_render", "ensure_rendered"}
    load_methods("new_stock_panel.py", names, namespace)
    from PyQt6.QtWidgets import QWidget
    panel = QWidget()
    panel.df_data = pd.DataFrame({"code": ["600000"], "price": [10.0], "pct": [1.0]})
    panel.extra_cols, panel.selected_code = [], ""
    panel._needs_render = False
    visible, rendered = [False], []
    panel.is_panel_visible = lambda: visible[0]
    panel._render_table = lambda: rendered.append(panel.df_data.at[0, "rank"])
    for name in names:
        setattr(panel, name, MethodType(namespace[name], panel))
    def frame(rank):
        return pd.DataFrame({"Rank": [rank]}, index=pd.Index(["600000"], name="code"))
    panel.update_from_ipc_df(frame(1))
    panel.update_from_ipc_df(frame(2))
    assert rendered == []
    visible[0] = True
    panel.ensure_rendered()
    panel.update_from_ipc_df(frame(3))
    panel.update_from_ipc_df(frame(4), force=True)
    panel._flush_ipc_render()
    assert rendered == [2, 4]
    assert not panel._ipc_render_timer.isActive()
    panel.close()


def test_sbc_close_returns_while_worker_waits_and_restart_keeps_latest_request(qt_methods):
    from PyQt6.QtCore import QEventLoop, QTimer
    path = Path(__file__).parent / "ui" / "sbc_launcher.py"
    cls = next(n for n in ast.parse(path.read_text(encoding="utf-8")).body
               if isinstance(n, ast.ClassDef) and n.name == "SBCProcessManager")
    namespace = dict(Optional=Optional, Dict=Dict, List=List, subprocess=subprocess,
                     threading=threading, time=time,
                     atexit=SimpleNamespace(register=lambda *args: None))
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), namespace)
    manager = namespace["SBCProcessManager"]()
    entered, release = threading.Event(), threading.Event()
    proc = SimpleNamespace(pid=123, returncode=None)
    proc.poll = lambda: proc.returncode
    manager._procs["__holdings_launcher__"] = proc
    worker_ids = []
    def close_child(child):
        worker_ids.append(threading.get_ident())
        entered.set()
        release.wait(2)
        child.returncode = 0
    manager._close_launcher_subprocess = close_child
    requests = []
    try:
        assert manager.close_launcher_process()
        assert entered.wait(1)
        assert worker_ids != [threading.get_ident()]
        assert manager.launch_holdings_watcher(snapshot_idx=1) is None
        assert manager.launch_holdings_watcher(snapshot_idx=2) is None
        assert manager._pending_holdings_launch[0] == 2
        manager.launch_holdings_watcher = lambda snapshot_idx=None, snapshot_data=None: requests.append(snapshot_idx)
    finally:
        release.set()
        manager._close_workers[-1].join(2)
    loop = QEventLoop()
    QTimer.singleShot(200, loop.quit)
    loop.exec()
    assert requests == [2]
    assert not manager._close_workers[-1].daemon


def test_scan_error_is_delivered_on_gui_thread_without_blocking(qt_methods, monkeypatch):
    import sys
    from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QEventLoop, QTimer
    namespace = dict(threading=threading)
    load_methods("new_stock_panel.py", {"_start_channel_scan"}, namespace)
    entered, release = threading.Event(), threading.Event()
    def evaluate(code):
        entered.set()
        release.wait(2)
        raise RuntimeError("TDX unavailable")
    monkeypatch.setitem(sys.modules, "ats.channel_bottom_reversal_strategy",
                        SimpleNamespace(ChannelBottomReversalStrategy=lambda:
                                        SimpleNamespace(evaluate_stock_tdx=evaluate)))
    received = []
    class Panel(QObject):
        _channel_scan_ready = pyqtSignal(object)
        _start_channel_scan = namespace["_start_channel_scan"]
        @pyqtSlot(object)
        def ready(self, payload):
            received.append((threading.get_ident(), payload))
    panel = Panel()
    panel._channel_scan_ready.connect(panel.ready)
    panel._start_channel_scan({"code": "600000"})
    try:
        assert entered.wait(1)
        assert panel._channel_scan_busy
        assert received == []
    finally:
        release.set()
    loop = QEventLoop()
    QTimer.singleShot(200, loop.quit)
    loop.exec()
    assert received == [(threading.get_ident(), {"code": "600000", "error": "TDX unavailable"})]
