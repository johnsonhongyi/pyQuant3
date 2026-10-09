"""Isolated native redraw comparison against the already optimized Treeview."""
import argparse
import ast
import json
import platform
import statistics
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tk_gui_modules.column_viewport import ColumnViewportTreeview


def summary(values):
    ordered = sorted(values)
    if not ordered:
        return dict(n=0, p50_ms=None, p95_ms=None)
    return dict(n=len(values), p50_ms=round(statistics.median(ordered), 2),
                p95_ms=round(ordered[min(len(ordered) - 1, int(len(ordered) * .95 + .999) - 1)], 2))


def fast_layout():
    node = next(n for n in ast.parse((ROOT / 'gui_utils.py').read_text(encoding='utf-8')).body
                if isinstance(n, ast.FunctionDef) and n.name == 'configure_treeview_rendering')
    ns = dict(platform=platform, tk=tk, ttk=ttk)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<production-cell-layout>', 'exec'), ns)
    return ns['configure_treeview_rendering']


def measure(root, cls, columns, rows, repeats, horizontal_only=False):
    tree = cls(root, columns=columns, show='headings')
    fast_layout()(tree)
    for col in columns:
        tree.column(col, width=80 if col == 'code' else 240 if col == 'name' else 64,
                    stretch=False, anchor='center')
        tree.heading(col, text=col)
    tree.tag_configure('alert', foreground='#cc0000', background='#ffcccc')
    values = ['000001', '\u2606\u6d4b\u8bd5\u80a1\u7968', *(['1.23'] * (len(columns) - 2))]
    for i in range(rows):
        tree.insert('', 'end', iid=str(i), values=values, tags=('alert',))
    tree.pack(fill='both', expand=True)
    root.update()
    tree.yview_moveto(.4)
    root.update_idletasks()
    if tree.yview()[1] >= 1 or len(tree.item('0', 'values')) != len(columns):
        raise RuntimeError('Native table was not populated or laid out')
    calls, paints, horizontal, displayed = [], [], [], []
    for i in range(0 if horizontal_only else repeats):
        before = tree.yview()
        started = time.perf_counter()
        tree.yview_scroll(3 if i < repeats // 2 else -3, 'units')
        dispatched = time.perf_counter()
        root.update_idletasks()
        calls.append((dispatched - started) * 1000)
        paints.append((time.perf_counter() - dispatched) * 1000)
        if tree.yview() == before:
            raise RuntimeError('Vertical sample did not move')
        shown = tree.tk.splitlist(tree.tk.call(tree._w, 'cget', '-displaycolumns'))
        displayed.append(len(columns) if shown == ('#all',) else len(shown))
    first, last = tree.xview()
    max_fraction = max(0., 1 - (last - first))
    for i in range(repeats if max_fraction > 0 else 0):
        before = tree.xview()
        started = time.perf_counter()
        tree.xview_moveto(max_fraction * (i + 1) / (repeats + 1))
        root.update_idletasks()
        horizontal.append((time.perf_counter() - started) * 1000)
        if tree.xview() == before:
            raise RuntimeError('Horizontal sample did not move')
    tree.xview_moveto(1)
    root.update_idletasks()
    if tree.xview()[1] != 1:
        raise RuntimeError('Rightmost logical column is unreachable')
    result = dict(call=summary(calls), native_redraw=summary(paints),
                  horizontal_move_and_redraw=summary(horizontal),
                  painted_columns=min(displayed) if displayed else None, full_columns=len(columns))
    tree.destroy()
    root.update_idletasks()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=12)
    parser.add_argument('--widths', type=int, nargs='+', default=[1200, 2938])
    parser.add_argument('--horizontal-only', action='store_true',
                        help='Replace only horizontal measurements in an existing output file')
    args = parser.parse_args()
    presets = json.loads((ROOT / 'display_cols.json').read_text(encoding='utf-8'))['sets']
    presets = [preset for preset in presets if preset['name'] in
               ('\u9ed8\u8ba4\u89c4\u5219', '\u8fde\u9633Upper-hmax')]
    root = tk.Tk()
    root.overrideredirect(True)
    output = dict(tk=root.tk.call('info', 'patchlevel'), theme=ttk.Style(root).theme_use(),
                  repeats=args.repeats, height=600, comparison='Both use the previous fast cell layout',
                  horizontal_samples_verified=True,
                  font=ttk.Style(root).lookup('Treeview', 'font'),
                  scaling=float(root.tk.call('tk', 'scaling')), results=[])
    if args.horizontal_only:
        output = json.loads(args.output.read_text(encoding='utf-8'))
        output['horizontal_samples_verified'] = True
    try:
        for width in args.widths:
            root.geometry(f'{width}x600+30000+30000')
            for preset in presets:
                columns = tuple(dict.fromkeys(['code', *preset['cols']]))
                for rows in (200, 5500):
                    for label, cls in (('before', ttk.Treeview), ('after', ColumnViewportTreeview)):
                        result = dict(version=label, preset=preset['name'], rows=rows, width=width,
                                      **measure(root, cls, columns, rows, args.repeats, args.horizontal_only))
                        if args.horizontal_only:
                            previous = next(item for item in output['results'] if all(
                                item[key] == result[key] for key in ('version', 'preset', 'rows', 'width')))
                            previous['horizontal_move_and_redraw'] = result['horizontal_move_and_redraw']
                            result = previous
                        else:
                            output['results'].append(result)
                        print(json.dumps(result, ensure_ascii=True), flush=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding='utf-8')
    finally:
        root.destroy()


if __name__ == '__main__':
    main()
