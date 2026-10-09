"""Windows-only isolated Tk benchmark. Never imports or launches the trading app."""
import argparse
import ast
import copy
import ctypes
import gc
import json
import platform
import statistics
import subprocess
import sys
import threading
import time
import types
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import Tk, ttk
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import Mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLS = ['code', 'name', 'percent', 'trade', 'volume', 'ratio', 'grade', 'category',
        'high4', 'max5', 'max10', 'hmax', 'hmax60', 'low4', 'low10', 'low60', 'lmin',
        'min5', 'cmean', 'hv', 'lv', 'llowvol', 'lastdu4', 'ma5d', 'ma20d', 'ma60d']
CONFIG = types.SimpleNamespace(CFG=types.SimpleNamespace(co2float=[], co2int=[]))


def load(source, name):
    node = next(n for n in ast.parse(source).body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)
    ns = dict(pd=pd, time=time, copy=copy, platform=platform, ttk=ttk, Any=Any,
              Dict=Dict, List=List, Optional=Optional, Tuple=Tuple, logger=Mock(),
              GlobalFavoriteManager=None, cct=CONFIG)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<benchmark>', 'exec'), ns)
    return ns[name]


def source(path, revision=None):
    if revision:
        return subprocess.run(['git', 'show', f'{revision}:stock_standalone/{path}'],
                              cwd=ROOT, capture_output=True, text=True,
                              encoding='utf-8', check=True).stdout
    return (ROOT / path).read_text(encoding='utf-8')


def summary(samples):
    ordered = sorted(samples)
    if not ordered:
        return {'n': 0, 'p50_ms': None, 'p95_ms': None}
    index = min(len(ordered) - 1, max(0, int(len(ordered) * .95 + .999) - 1))
    return {'n': len(ordered), 'p50_ms': round(statistics.median(ordered), 2),
            'p95_ms': round(ordered[index], 2)}


def frame(rows):
    result = pd.DataFrame({col: [1.] * rows for col in COLS})
    result['code'] = [f'{i:06}' for i in range(rows)]
    result['name'] = ['\u6d4b\u8bd5\u80a1\u7968'] * rows
    result['grade'], result['category'] = 'C', 'test'
    return result


def tree(root, fast, rows, display=None, name='stock'):
    widget = ttk.Treeview(root, columns=COLS, show='headings')
    widget.pack(fill='both', expand=True)
    for col in COLS:
        widget.column(col, width=64, stretch=False, anchor='center')
    if fast:
        fast(widget)
    if display:
        widget.configure(displaycolumns=display)
    for i in range(rows):
        widget.insert('', 'end', values=[f'{i:06}', name, *(['1.0'] * 24)])
    root.update()
    return widget


def settle(root, updater, timeout=60):
    deadline = time.monotonic() + timeout
    while updater._chunked_insert_pending:
        root.update()
        if time.monotonic() > deadline:
            raise RuntimeError('Renderer completion timeout')
        time.sleep(.001)
    root.update()


def scenarios(root, cls, bind, fast, marker, rows, samples, interval,
              names=('static', 'realtime', 'rapid_wheel')):
    output = []
    post = ctypes.windll.user32.PostMessageW
    post.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    post.restype = ctypes.c_int
    for scenario in names:
        widget = tree(root, fast, 0)
        bind(widget)
        updater = cls(widget, COLS, feature_marker=marker(widget), root=root, chunk_size=64)
        data = frame(rows)
        widget.pack_forget()
        root.update_idletasks()
        updater.update(data)
        settle(root, updater)
        widget.pack(fill='both', expand=True)
        root.update()
        # Offscreen windows do not reliably receive a Windows expose event.
        # Explicit invalidation initializes native layout/scroll ranges first.
        widget.configure(height=26)
        root.update_idletasks()
        if len(widget.get_children()) != rows or widget.yview()[1] >= 1:
            raise RuntimeError(f'Table layout invalid: rows={len(widget.get_children())}, '
                               f'view={widget.yview()}, mapped={widget.winfo_ismapped()}, '
                               f'geometry={widget.winfo_geometry()}')
        widget.yview_moveto(.4)
        root.update_idletasks()
        scheduled, posted, painted, batches, deltas = [], [], [], [], []
        initial_view = widget.yview()
        counts = dict(item=0, cell=0, move=0, tag_configure=0, column_write=0,
                      wheel_calls=0, viewport_changes=0)
        original_scroll = widget.yview_scroll

        def measured_scroll(*args):
            previous = widget.yview()
            counts['wheel_calls'] += 1
            original_scroll(*args)
            counts['viewport_changes'] += widget.yview() != previous

        widget.yview_scroll = measured_scroll
        for name, counter in [('item', 'item'), ('set', 'cell'), ('move', 'move'),
                              ('tag_configure', 'tag_configure'), ('column', 'column_write')]:
            original = getattr(widget, name)

            def measured(*args, _fn=original, _counter=counter, **kwargs):
                if _counter in ('cell', 'move') or kwargs:
                    counts[_counter] += 1
                return _fn(*args, **kwargs)
            setattr(widget, name, measured)
        pending, lock, stop = deque(), threading.Lock(), threading.Event()
        market = {'version': 0, 'frame': data, 'delivered': 0}
        tag = 'PerfProbe'
        widget.bindtags((tag, *widget.bindtags()))

        def received(event):
            deltas.append(event.delta)
            with lock:
                due, sent = pending.popleft()
            now = time.perf_counter()
            scheduled.append((now - due) * 1000)
            posted.append((now - sent) * 1000)
            root.after_idle(lambda start=sent: root.after_idle(
                lambda: painted.append((time.perf_counter() - start) * 1000)))
            return None if scenario == 'rapid_wheel' else 'break'

        root.bind_class(tag, '<MouseWheel>', received)
        hwnd = widget.winfo_id()
        xy = ((root.winfo_rooty() + 50) & 0xffff) << 16 | ((root.winfo_rootx() + 50) & 0xffff)

        def inputs():
            begin = time.perf_counter() + .05
            for i in range(samples):
                due = begin + i * interval
                time.sleep(max(0, due - time.perf_counter()))
                # A single direction change prevents opposite events cancelling
                # before Tk paints, which would understate wheel redraw latency.
                delta = -120 if i < (samples + 1) // 2 else 120
                with lock:
                    pending.append((due, time.perf_counter()))
                if not post(hwnd, 0x020a, (delta & 0xffff) << 16, xy):
                    raise ctypes.WinError()

        def markets():
            while not stop.wait(.1):
                updated = data.copy()
                with lock:
                    version = market['version'] + 1
                updated['percent'] = float(1 + version % 2)
                with lock:
                    market.update(version=version, frame=updated)

        def pump():
            with lock:
                version, latest = market['version'], market['frame']
            if version != market['delivered']:
                market['delivered'] = version
                updater.update(latest)
            if len(posted) == samples:
                stop.set()
                if updater._render_after_id is not None:
                    root.after_cancel(updater._render_after_id)
                    updater._render_after_id = None
                root.after_idle(lambda: root.after_idle(root.quit))
            else:
                root.after(10, pump)

        root._record_latency_sample = lambda name, value: batches.append(value) if name == 'tree_render_batch' else None
        input_thread = threading.Thread(target=inputs)
        market_thread = threading.Thread(target=markets)
        input_thread.start()
        if scenario != 'static':
            market_thread.start()
        root.after(10, pump)
        root.after(30000, root.quit)
        root.mainloop()
        stop.set()
        input_thread.join()
        if market_thread.ident is not None:
            market_thread.join()
        if len(posted) != samples:
            raise RuntimeError(f'Missing native events: {len(posted)}/{samples}')
        if scenario == 'rapid_wheel' and counts['viewport_changes'] == 0:
            raise RuntimeError(f'Wheel did not move: {counts}, deltas={deltas}, '
                               f'view={initial_view}/{widget.yview()}')
        for job in root.tk.call('after', 'info'):
            root.after_cancel(job)
        root.unbind_class(tag, '<MouseWheel>')
        # Freshness is checked separately by targeted renderer regression tests.
        row = dict(rows=rows, scenario=scenario, event=summary(scheduled),
                   post_to_handler=summary(posted), input_to_idle_paint=summary(painted),
                   ui_batch=summary(batches), market_received=market['version'],
                   market_delivered=market['delivered'], writes=counts,
                   initial_view=initial_view, final_view=widget.yview())
        output.append(row)
        print(json.dumps(row), flush=True)
        updater._chunked_insert_pending = False
        if hasattr(updater, '_pending_render'):
            updater._pending_render = None
        root.view_executor.shutdown(wait=True)
        root.view_executor = ThreadPoolExecutor(max_workers=2)
        widget.destroy()
        root.update_idletasks()
        gc.collect()
    return output


def components(root, fast, rows, repeats):
    results = []
    for case in ('ascii', 'cjk', 'icons', 'bold', 'clipped_26', 'visible_6',
                 'whole_row', 'tags_only', 'tag_reconfigure', 'same_width'):
        root.geometry(('420x600' if case in ('clipped_26', 'visible_6') else '1200x600') + '+30000+30000')
        name = 'stock' if case == 'ascii' else '\u6d4b\u8bd5\u80a1\u7968'
        if case in ('icons', 'bold'):
            name = '\U0001f53c\U0001f53d ' + name
        widget = tree(root, fast, rows, COLS[:6] if case == 'visible_6' else None, name)
        widget.tag_configure('paint_a', background='#ffe6e6', foreground='#cc0000')
        widget.tag_configure('paint_b', background='#e6ffe6', foreground='#006600')
        if case == 'bold':
            widget.tag_configure('paint_a', font=('Microsoft YaHei', 9, 'bold'))
            for iid in widget.get_children():
                widget.item(iid, tags=('paint_a',))
        root.update()
        targets = widget.get_children()[:24]
        cached = {iid: widget.item(iid, 'values') for iid in targets}
        if case == 'tag_reconfigure':
            for iid in targets:
                widget.item(iid, tags=('paint_a',))
            root.update_idletasks()
        calls, redraws = [], []
        for n in range(repeats):
            begin = time.perf_counter()
            if case == 'whole_row':
                for iid in targets:
                    widget.item(iid, values=cached[iid])
            elif case == 'tags_only':
                for iid in targets:
                    widget.item(iid, tags=('paint_a' if n % 2 else 'paint_b',))
            elif case == 'tag_reconfigure':
                widget.tag_configure('paint_a', foreground='#cc0000')
            elif case == 'same_width':
                for col in COLS:
                    widget.column(col, width=64)
            else:
                widget.yview_scroll(3 if n % 2 else -3, 'units')
            dispatched = time.perf_counter()
            root.update_idletasks()
            calls.append((dispatched - begin) * 1000)
            redraws.append((time.perf_counter() - dispatched) * 1000)
        result = dict(rows=rows, case=case, call=summary(calls), native_redraw=summary(redraws))
        results.append(result)
        print(json.dumps(result), flush=True)
        widget.destroy()
        root.update_idletasks()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--repeats', type=int, default=12)
    parser.add_argument('--scenarios', nargs='+', default=['static', 'realtime', 'rapid_wheel'])
    parser.add_argument('--skip-components', action='store_true')
    parser.add_argument('--interval-ms', type=float, default=16)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Windows':
        parser.error('Native PostMessage measurements require Windows')
    johnson = types.ModuleType('JohnsonUtil')
    johnson.commonTips = CONFIG
    sys.modules['JohnsonUtil'] = johnson
    marker = load(source('stock_feature_marker.py'), 'StockFeatureMarker')
    versions = [(label, load(source('performance_optimizer.py', revision), 'TreeviewIncrementalUpdater'),
                 load(source('gui_utils.py', revision), 'bind_mouse_scroll'),
                 load(source('gui_utils.py'), 'configure_treeview_rendering') if revision is None else None)
                for label, revision in [('before', args.baseline), ('after', None)]]
    root = Tk()
    root.overrideredirect(True)
    root.geometry('1200x600+30000+30000')
    root.view_executor = ThreadPoolExecutor(max_workers=2)
    result = dict(baseline=args.baseline, tk=root.tk.call('info', 'patchlevel'),
                  theme=ttk.Style(root).theme_use(), viewport='1200x600', columns=26,
                  interval_ms=args.interval_ms, samples=args.samples, repeats=args.repeats, results=[])
    try:
        for label, cls, bind, fast in versions:
            for rows in (200, 5500):
                root.geometry('1200x600+30000+30000')
                gc.collect()
                result['results'].append(dict(version=label, rows=rows,
                    scenarios=scenarios(root, cls, bind, fast, marker, rows, args.samples,
                                        args.interval_ms / 1000, args.scenarios),
                    components=[] if args.skip_components else components(root, fast, rows, args.repeats)))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
    finally:
        root._is_closing = True
        root.view_executor.shutdown(wait=True, cancel_futures=True)
        root.destroy()
        gc.collect()


if __name__ == '__main__':
    main()
