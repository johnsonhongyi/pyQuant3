"""Exercise real Tk bindtags and the production renderer without starting trading."""
import ast
import copy
import platform
import queue
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import Mock
from tkinter import ttk

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_node(path, name, class_name=None, **extra):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    nodes = tree.body
    if class_name:
        nodes = next(n.body for n in nodes if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in nodes if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)
    ns = dict(pd=pd, time=time, copy=copy, platform=platform, queue=queue, threading=threading,
              Any=Any, Dict=Dict, List=List, Optional=Optional, Tuple=Tuple, logger=Mock(),
              GlobalFavoriteManager=None, cct=None)
    ns.update(extra)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), ns)
    return ns[name]


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    window.attributes('-alpha', 0.0)
    window.geometry('400x260')
    window.view_executor = ThreadPoolExecutor(max_workers=2)
    yield window
    window._is_closing = True
    window.view_executor.shutdown(wait=True, cancel_futures=True)
    window.destroy()


def make_tree(root, rows=0):
    tree = ttk.Treeview(root, columns=('code', 'name', 'percent'), show='headings', height=8)
    tree.pack(fill='both', expand=True)
    for i in range(rows):
        tree.insert('', 'end', values=(f'{i:06}', f'stock-{i}', i))
    root.update()
    return tree


def settle(root, updater):
    deadline = time.monotonic() + 8
    while updater._chunked_insert_pending:
        root.update()
        assert time.monotonic() < deadline, 'renderer did not finish'
        time.sleep(0.001)
    root.update()


@pytest.mark.parametrize('rows', [200, 5500])
@pytest.mark.parametrize('delta', [-120, 120, -30, 30])
def test_real_wheel_consumed_once_and_fractional_motion_is_symmetric(root, rows, delta):
    tree = make_tree(root, rows)
    bind = load_node('gui_utils.py', 'bind_mouse_scroll',
                     platform=SimpleNamespace(system=lambda: 'Windows'))
    bind(tree)
    tree.yview_moveto(0.5)
    before = tree.yview()[0]
    for _ in range(4 if abs(delta) == 30 else 1):
        tree.event_generate('<MouseWheel>', delta=delta)
    root.update()
    moved = round((tree.yview()[0] - before) * rows)
    assert moved == (-3 if delta > 0 else 3)
    assert tree._last_scroll_time > 0


def test_wheel_modifiers_have_independent_accumulators():
    bindings = {}
    widget = SimpleNamespace(bind=lambda event, fn: bindings.update({event: fn}),
                             yview_scroll=Mock(), xview_scroll=Mock())
    load_node('gui_utils.py', 'bind_mouse_scroll',
              platform=SimpleNamespace(system=lambda: 'Windows'))(widget)
    event = SimpleNamespace(delta=-30)
    assert bindings['<MouseWheel>'](event) == 'break'
    assert bindings['<Shift-MouseWheel>'](event) == 'break'
    widget.xview_scroll.assert_not_called()
    assert bindings['<Alt-MouseWheel>'](event) == 'break'
    widget.xview_scroll.assert_called_once_with(1, 'units')
    widget.yview_scroll.assert_not_called()


@pytest.mark.parametrize('system,event,delta', [
    ('Linux', '<Button-5>', 0), ('Darwin', '<MouseWheel>', -1)])
def test_non_windows_wheel_keeps_single_unit_behavior(system, event, delta):
    bindings = {}
    widget = SimpleNamespace(bind=lambda key, fn: bindings.update({key: fn}),
                             yview_scroll=Mock(), xview_scroll=Mock())
    load_node('gui_utils.py', 'bind_mouse_scroll',
              platform=SimpleNamespace(system=lambda: system))(widget)
    assert bindings[event](SimpleNamespace(delta=delta)) == 'break'
    widget.yview_scroll.assert_called_once_with(1, 'units')


def renderer(root, count=200):
    tree = make_tree(root)
    cls = load_node('performance_optimizer.py', 'TreeviewIncrementalUpdater')
    updater = cls(tree, ['code', 'name', 'percent'], root=root, chunk_size=64)
    frame = pd.DataFrame({'code': [f'{i:06}' for i in range(count)],
                          'name': [f'stock-{i}' for i in range(count)],
                          'percent': [1.] * count})
    return tree, updater, frame


@pytest.mark.parametrize('count', [200, 5500])
def test_real_renderer_formats_off_thread_and_skips_unchanged_writes(root, count, monkeypatch):
    tree, updater, frame = renderer(root, count)
    preparation_threads = []
    original = type(updater)._prepare_render_rows

    def prepare(self, df):
        assert self.tree is None and self.root is None
        assert self.feature_marker is None or self.feature_marker.tree is None
        preparation_threads.append(threading.get_ident())
        return original(self, df)

    monkeypatch.setattr(type(updater), '_prepare_render_rows', prepare)
    updater.update(frame)
    settle(root, updater)
    assert len(tree.get_children()) == count
    assert preparation_threads and all(t != threading.get_ident() for t in preparation_threads)
    writes, moves = Mock(wraps=tree.item), Mock(wraps=tree.move)
    monkeypatch.setattr(tree, 'item', writes)
    monkeypatch.setattr(tree, 'move', moves)
    updater.update(frame.copy())
    settle(root, updater)
    writes.assert_not_called()
    moves.assert_not_called()
    updater.update(frame.iloc[[1, 0, *range(2, count)]])
    settle(root, updater)
    assert tree.get_children()[:2] == (updater._item_map['000001'], updater._item_map['000000'])
    writes.assert_not_called()
    assert moves.call_count == 1


def test_render_burst_finishes_then_applies_latest_and_input_defers_writes(root, monkeypatch):
    tree, updater, frame = renderer(root)
    gate = threading.Event()
    started = threading.Event()
    original = type(updater)._prepare_render_rows
    prepared = []

    def prepare(self, df):
        prepared.append(float(df.iloc[-1]['percent']))
        started.set()
        assert gate.wait(3)
        return original(self, df)

    monkeypatch.setattr(type(updater), '_prepare_render_rows', prepare)
    updater.update(frame)
    assert started.wait(2)
    for version in range(2, 12):
        latest = frame.copy()
        latest.loc[len(latest) - 1, 'percent'] = float(version)
        updater.update(latest)
    tree._last_scroll_time = time.monotonic() + 10
    gate.set()
    for _ in range(20):
        root.update()
        time.sleep(0.002)
    assert not tree.get_children()
    tree._last_scroll_time = 0
    settle(root, updater)
    assert prepared == [1., 11.]
    assert tree.item(updater._item_map['000199'], 'values')[-1] == '11.0'


def test_force_clear_discards_inflight_payload_without_parallel_preparation(root, monkeypatch):
    tree, updater, frame = renderer(root)
    gate = threading.Event()
    original = type(updater)._prepare_render_rows

    def prepare(self, df):
        assert gate.wait(3)
        return original(self, df)

    monkeypatch.setattr(type(updater), '_prepare_render_rows', prepare)
    updater.update(frame)
    updater.update(pd.DataFrame(), force_full=True)
    gate.set()
    settle(root, updater)
    assert not tree.get_children()
    assert not updater._item_map


def test_mixed_inserts_deletes_and_reordering_keep_target_order_and_selection(root):
    tree, updater, frame = renderer(root, 4)
    updater.update(frame)
    settle(root, updater)
    selected = updater._item_map['000002']
    tree.selection_set(selected)
    added = pd.DataFrame({'code': ['999999'], 'name': ['new'], 'percent': [9.]})
    target = pd.concat([added, frame.iloc[[2, 0]]], ignore_index=True)
    updater.update(target)
    settle(root, updater)
    assert [tree.item(iid, 'values')[0] for iid in tree.get_children()] == ['999999', '000002', '000000']
    assert tree.selection() == (selected,)


def test_background_formatting_preserves_feature_icons_tags_and_favorites(root):
    tree, updater, frame = renderer(root, 2)
    updater.feature_marker = SimpleNamespace(enable_colors=True,
                                            get_icon_for_row=lambda row: '[+]',
                                            get_tags_for_row=lambda row: ['up'])
    frame['grade'] = ['S', 'A']
    prepare = type(updater)._prepare_render_rows
    prepare.__globals__['GlobalFavoriteManager'] = lambda: SimpleNamespace(
        get_favorite_stocks=lambda: {'000000', '000001'})
    updater.update(frame)
    settle(root, updater)
    assert tree.item(updater._item_map['000000'], 'values')[1] == '\u3010\u91cd\u70b9\u3011[+] stock-0'
    assert tree.item(updater._item_map['000000'], 'tags') == ('up', 'favorite_S')
    assert tree.item(updater._item_map['000001'], 'tags') == ('up', 'favorite_A')


def test_closing_during_preparation_does_not_write_or_start_pending_job(root, monkeypatch):
    tree, updater, frame = renderer(root)
    gate = threading.Event()
    original = type(updater)._prepare_render_rows
    calls = []

    def prepare(self, df):
        calls.append(1)
        assert gate.wait(3)
        return original(self, df)

    monkeypatch.setattr(type(updater), '_prepare_render_rows', prepare)
    updater.update(frame)
    updater.update(frame.copy())
    root._is_closing = True
    gate.set()
    settle(root, updater)
    assert not tree.get_children()
    assert len(calls) == 1
    assert updater._pending_render is None


def test_strategy_reports_capture_rows_and_only_deliver_latest_selection():
    jobs, deliveries = [], []

    def submit(fn, *args):
        future = Future()
        jobs.append((future, args))
        return future

    owner = SimpleNamespace(
        global_values=SimpleNamespace(getkey=lambda key: 'd'),
        df_all=pd.DataFrame({'trade': [1., 2., 3.]}, index=['a', 'b', 'c']),
        view_executor=SimpleNamespace(submit=submit), _compute_strategy_report=Mock(),
        _show_strategy_report_window=Mock(),
        _put_deduped_task=lambda key, callback: deliveries.append(callback))
    for name in ('test_strategy_for_stock', '_start_strategy_report'):
        fn = load_node('instock_MonitorTK.py', name, 'StockMonitorApp', messagebox=Mock())
        setattr(owner, name, MethodType(fn, owner))
    owner.test_strategy_for_stock('a', 'A')
    owner.df_all.loc['a', 'trade'] = 9.
    assert jobs[0][1][-1]['trade'] == 1.
    owner.test_strategy_for_stock('b', 'B')
    owner.test_strategy_for_stock('c', 'C')
    assert len(jobs) == 1
    jobs[0][0].set_result(('old', {}, 1., ''))
    deliveries.pop(0)()
    owner._show_strategy_report_window.assert_not_called()
    assert len(jobs) == 2 and jobs[1][1][0] == 'c'
    jobs[1][0].set_result(('latest', {}, 3., ''))
    deliveries.pop(0)()
    owner._show_strategy_report_window.assert_called_once_with('c', 'C', 'latest', {}, price=3.)


def test_strategy_report_worker_returns_payload_without_tk_access(monkeypatch):
    result = {'action': 'HOLD', 'position': 0., 'reason': 'test', 'debug': {}}
    monkeypatch.setitem(sys.modules, 'intraday_decision_engine', SimpleNamespace(
        IntradayDecisionEngine=lambda: SimpleNamespace(evaluate=lambda *args, **kwargs: result)))
    fn = load_node('instock_MonitorTK.py', '_compute_strategy_report', 'StockMonitorApp',
                   messagebox=SimpleNamespace(showerror=Mock(side_effect=AssertionError('Tk on worker'))))
    text, actual, price, error = fn(SimpleNamespace(live_strategy=None), 'a', 'A',
                                    pd.Series({'trade': 10., 'percent': 1.}))
    assert not error and actual == result and price == 10.
    assert 'A (a)' in text


def test_sender_snapshots_flags_on_caller_and_recovers_proxy_only_on_worker():
    entered, release, last_sent = threading.Event(), threading.Event(), threading.Event()
    sent = []
    main_thread = threading.get_ident()

    def get_flag(value):
        assert threading.get_ident() == main_thread
        return bool(value)

    def push(code, flags, auto=False):
        assert threading.get_ident() != main_thread
        sent.append(code)
        entered.set()
        assert release.wait(3)
        if code == 'c':
            last_sent.set()
        return True

    owner = SimpleNamespace(tdx_var=True, ths_var=False, dfcf_var=False,
                            _get_flag=get_flag, _task_queue=queue.Queue(maxsize=1),
                            _latest_task=None, _last_exec_ts=0, _running=True,
                            _push_linkage=push, _do_send=Mock())
    sender_class = SimpleNamespace()
    send = load_node('JohnsonUtil/stock_sender.py', 'send', 'StockSender', StockSender=sender_class)
    loop = load_node('JohnsonUtil/stock_sender.py', '_worker_loop', 'StockSender')
    worker = threading.Thread(target=loop, args=(owner,))
    owner._ensure_worker_alive = lambda: worker.start() if not worker.is_alive() else None
    try:
        send(owner, 'a')
        assert entered.wait(2)
        send(owner, 'b')
        send(owner, 'c')
        release.set()
        assert last_sent.wait(3)
        assert sent == ['a', 'c']
        owner._do_send.assert_not_called()
    finally:
        release.set()
        owner._running = False
        worker.join(timeout=3)
        assert not worker.is_alive()


def test_full_linkage_queue_cannot_block_recovery():
    process = Mock()
    process.is_alive.return_value = True
    owner = SimpleNamespace(queue=Mock(), process=process)
    owner.queue.put_nowait.side_effect = queue.Full
    stop = load_node('linkage_service.py', 'stop', 'LinkageManagerProxy')
    stop(owner)
    owner.queue.put.assert_not_called()
    process.terminate.assert_called_once()
    assert process.join.call_count == 2


def test_linkage_environment_marker_is_only_set_in_child():
    tree = ast.parse((ROOT / 'linkage_service.py').read_text(encoding='utf-8'))
    top_level = ast.Module(body=[n for n in tree.body if isinstance(n, ast.Assign)], type_ignores=[])
    assert 'IN_LINKAGE_PROCESS_MARK' not in ast.unparse(top_level)
    worker = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_start_linkage_worker')
    assert 'IN_LINKAGE_PROCESS_MARK' in ast.unparse(worker)


def test_cell_layout_fast_path_preserves_columns_anchors_and_tag_fonts(root):
    tree = make_tree(root)
    tree.column('percent', anchor='center', width=90)
    tree.tag_configure('bold', font=('Microsoft YaHei', 9, 'bold'))
    font = tree.tag_configure('bold', 'font')
    columns = tree['columns']
    configure = load_node('gui_utils.py', 'configure_treeview_rendering', ttk=ttk,
                          platform=SimpleNamespace(system=lambda: 'Windows'))
    assert configure(tree)
    assert tree['columns'] == columns
    assert str(tree.column('percent', 'anchor')) == 'center'
    assert tree.column('percent', 'width') == 90
    assert tree.tag_configure('bold', 'font') == font
    assert ttk.Style(tree).layout('Fast.Treeview.Cell')[0][0] == 'Treeitem.text'
    assert not configure(tree)


def test_cell_delta_writes_do_not_reassign_whole_row_or_unchanged_tags(root, monkeypatch):
    tree, updater, frame = renderer(root, 4)
    updater.update(frame)
    settle(root, updater)
    item = Mock(wraps=tree.item)
    cell = Mock(wraps=tree.set)
    monkeypatch.setattr(tree, 'item', item)
    monkeypatch.setattr(tree, 'set', cell)
    frame.loc[2, 'percent'] = 9.
    updater.update(frame)
    settle(root, updater)
    item.assert_not_called()
    cell.assert_called_once_with(updater._item_map['000002'], 'percent', 9.)


def test_linked_order_sort_does_not_scan_native_indices(root, monkeypatch):
    tree, updater, frame = renderer(root, 12)
    updater.update(frame)
    settle(root, updater)
    monkeypatch.setattr(tree, 'index', Mock(side_effect=AssertionError('native sibling scan')))
    for order in ([11, 1, 2, 0, 4, 8, 6, 7, 5, 9, 10, 3], list(range(11, -1, -1)), list(range(12))):
        updater.update(frame.iloc[order])
        settle(root, updater)
        assert [tree.item(iid, 'values')[0] for iid in tree.get_children()] == [f'{i:06}' for i in order]


def test_scroll_resume_applies_latest_frame_without_replaying_old_ui_payload(root, monkeypatch):
    tree, updater, frame = renderer(root, 12)
    updater.update(frame)
    settle(root, updater)
    cell = Mock(wraps=tree.set)
    monkeypatch.setattr(tree, 'set', cell)
    tree._last_scroll_time = time.monotonic() + 10
    for value in (2., 3., 9.):
        incoming = frame.copy()
        incoming['percent'] = value
        updater.update(incoming)
    for _ in range(10):
        root.update()
        time.sleep(.002)
    cell.assert_not_called()
    tree._last_scroll_time = 0
    settle(root, updater)
    assert len(cell.call_args_list) == len(frame)
    assert {call.args[-1] for call in cell.call_args_list} == {9.}


def test_column_width_adjustment_skips_unchanged_native_options():
    widths = {'code': 80, 'name': 120, 'percent': 49}
    writes = []

    def column(col, option=None, **kwargs):
        if option == 'width':
            return widths[col]
        writes.append((col, kwargs))
        widths[col] = kwargs['width']

    class Tree:
        winfo_exists = staticmethod(lambda: True)

        def __getitem__(self, key):
            return tuple(widths)

    tree = Tree()
    tree.column = column
    owner = SimpleNamespace(tree=tree, current_df=pd.DataFrame(
        {'code': ['000001'], 'name': ['one'], 'percent': [1.]}), scale_factor=1.,
        get_scaled_value=lambda: 1.)
    adjust = load_node('instock_MonitorTK.py', 'adjust_column_widths', 'StockMonitorApp')
    adjust(owner)
    assert not writes
    owner._name_col_width = 140
    adjust(owner)
    assert writes == [('name', {'width': 140})]


def test_column_width_work_is_coalesced_and_delayed_while_scrolling():
    callbacks = []

    def after(delay, fn):
        callbacks.append(fn)
        return len(callbacks)

    owner = SimpleNamespace(tree=SimpleNamespace(_last_scroll_time=time.monotonic() + 10),
                            after=after, adjust_column_widths=Mock(), current_cols=['code'])
    request = load_node('instock_MonitorTK.py', '_request_column_width_adjustment', 'StockMonitorApp')
    request(owner)
    request(owner)
    assert len(callbacks) == 1
    callbacks[0]()
    owner.adjust_column_widths.assert_not_called()
    assert len(callbacks) == 2
    owner.tree._last_scroll_time = 0
    owner.current_cols = ['code', 'percent']
    callbacks[1]()
    owner.adjust_column_widths.assert_called_once()
    assert owner._last_adjust_cols == ['code', 'percent']


def test_cell_layout_unsupported_theme_keeps_existing_style():
    style = SimpleNamespace(layout=Mock(side_effect=tk.TclError('missing layout')))
    tree = SimpleNamespace(cget=lambda key: 'Custom.Treeview', configure=Mock())
    configure = load_node('gui_utils.py', 'configure_treeview_rendering',
                          ttk=SimpleNamespace(Style=lambda tree: style, Treeview=ttk.Treeview), tk=tk)
    assert configure(tree) is False
    tree.configure.assert_not_called()


def test_sender_concurrent_start_creates_only_one_worker():
    release, barrier = threading.Event(), threading.Barrier(8)
    workers = []

    def create_worker(**kwargs):
        time.sleep(.01)
        worker = threading.Thread(**kwargs)
        workers.append(worker)
        return worker

    ensure = load_node('JohnsonUtil/stock_sender.py', '_ensure_worker_alive', 'StockSender',
                       threading=SimpleNamespace(Thread=create_worker))
    owner = SimpleNamespace(_worker=None, _worker_start_lock=threading.Lock(),
                            _worker_loop=lambda: release.wait(3))

    def start():
        barrier.wait(3)
        ensure(owner)

    callers = [threading.Thread(target=start) for _ in range(8)]
    try:
        for caller in callers:
            caller.start()
        for caller in callers:
            caller.join(3)
        assert not any(caller.is_alive() for caller in callers)
        assert len(workers) == 1 and owner._worker.is_alive()
    finally:
        release.set()
        for worker in workers:
            worker.join(3)


def test_sender_proxy_keeps_service_throttle_and_local_fallback_keeps_its_throttle():
    proxied, fallback, sent = threading.Event(), threading.Event(), threading.Event()

    def push(code, flags, auto=False):
        (proxied if code == 'proxy' else fallback).set()
        return code == 'proxy'

    owner = SimpleNamespace(_running=True, _task_queue=queue.Queue(maxsize=1),
                            _latest_task=None, _last_exec_ts=time.time(),
                            _push_linkage=push, _do_send=Mock(side_effect=lambda *a, **kw: sent.set()))
    loop = load_node('JohnsonUtil/stock_sender.py', '_worker_loop', 'StockSender')
    worker = threading.Thread(target=loop, args=(owner,))
    try:
        owner._task_queue.put_nowait(('proxy', {}, True))
        worker.start()
        assert proxied.wait(1), 'proxy must not wait for the fallback 2-second throttle'
        owner._task_queue.put_nowait(('fallback', {}, True))
        assert fallback.wait(1)
        assert not sent.wait(.05), 'fallback must retain the original auto throttle'
        owner._last_exec_ts = 0
        assert sent.wait(1)
        owner._do_send.assert_called_once_with('fallback', {}, auto=True)
    finally:
        owner._running = False
        worker.join(3)
        assert not worker.is_alive()
