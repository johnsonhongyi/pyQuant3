"""Real Tk tests for column culling without importing the trading application."""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tk_gui_modules.column_viewport import ColumnViewportTreeview


@pytest.fixture
def root():
    window = tk.Tk()
    window.attributes('-alpha', 0)
    window.geometry('640x300')
    yield window
    window.destroy()


def table(root, cls=ColumnViewportTreeview, count=74, display=None):
    columns = tuple(f'c{i}' for i in range(count))
    tree = cls(root, columns=columns, show='headings', height=8)
    if display is not None:
        tree.configure(displaycolumns=display)
    for i, column in enumerate(columns):
        tree.column(column, width=80, minwidth=20, stretch=False, anchor='center')
        tree.heading(column, text=column)
    tree.pack(fill='both', expand=True)
    for row in range(200):
        tree.insert('', 'end', iid=f'r{row}', values=tuple(f'{row}:{col}' for col in columns),
                    tags=('alert',) if row % 2 else ('favorite',))
    root.update()
    return tree, columns


def physical_columns(tree):
    return tuple(tree.tk.splitlist(tree.tk.call(tree._w, 'cget', '-displaycolumns')))


def assert_visible_mapping(tree, columns):
    row_y = tree.bbox('r0')[1] + 5
    for x in range(10, tree.winfo_width() - 10, 37):
        native = tree.tk.call(tree._w, 'identify', 'column', x, row_y)
        name = str(tree.tk.call(tree._w, 'column', native, '-id'))
        logical = tree.identify_column(x)
        assert tree.column(logical, 'id') == name
        assert columns[int(logical[1:]) - 1] == name
        assert tree.set('r0', logical) == '0:' + name
        assert tree.heading(logical, 'text') == name
        assert tree.bbox('r0', logical) == tree.bbox('r0', name)


def test_only_viewport_columns_paint_but_all_model_values_remain(root):
    tree, columns = table(root)
    assert tree['columns'] == columns
    assert tree['displaycolumns'] == ('#all',)
    assert len(physical_columns(tree)) <= 12
    assert len(tree.item('r0', 'values')) == 74
    assert tree.item('r1', 'tags') == ('alert',)
    assert [tree.column(col, 'width') for col in columns] == [80] * 74
    assert_visible_mapping(tree, columns)


def test_horizontal_positions_match_native_and_rightmost_is_reachable(root):
    tree, columns = table(root)
    positions = []
    for fraction in (0, .2, .5, 1, .25, 0):
        tree.xview_moveto(fraction)
        root.update()
        positions.append(tree.xview())
        assert len(physical_columns(tree)) <= 13
        assert_visible_mapping(tree, columns)
        native_width = sum(int(tree.tk.call(tree._w, 'column', col, '-width'))
                           for col in physical_columns(tree))
        assert native_width == sum(tree.column(col, 'width') for col in columns)
    tree.destroy()
    native, _ = table(root, ttk.Treeview)
    for fraction, expected in zip((0, .2, .5, 1, .25, 0), positions):
        native.xview_moveto(fraction)
        root.update()
        assert native.xview() == pytest.approx(expected, abs=1 / (74 * 80))


def test_hidden_updates_sort_and_selection_survive_horizontal_scroll(root):
    tree, columns = table(root)
    tree.selection_set('r5')
    tree.focus('r5')
    tree.set('r5', columns[-1], 'latest')
    tree.move('r5', '', 0)
    for fraction in (.9, .1, 1):
        tree.xview('moveto', fraction)
        root.update()
    assert tree.item('r5', 'values')[-1] == 'latest'
    assert tree.get_children()[0] == 'r5'
    assert tree.selection() == ('r5',) and tree.focus() == 'r5'
    assert tree['columns'] == columns


def test_scrollbar_callback_replacement_and_unit_page_scroll(root):
    tree, _ = table(root)
    delivered = []
    tree.configure(xscroll=lambda first, last: delivered.append((float(first), float(last))))
    tree.xview_scroll(3, 'units')
    root.update()
    first = tree.xview()[0]
    assert first > 0 and delivered[-1] == tree.xview()
    tree.xview_scroll(1, 'pages')
    root.update()
    assert tree.xview()[0] > first
    tree.configure(xscrollcommand='')
    tree.xview_moveto(1)
    root.update()
    assert tree.xview()[1] == 1


def test_column_schema_clear_and_replacement_match_main_table_workflow(root):
    tree, columns = table(root)
    tree.xview_moveto(.5)
    root.update()
    tree['displaycolumns'] = ()
    tree['columns'] = ()
    root.update_idletasks()
    assert not physical_columns(tree)
    replacement = ('code', 'name', 'percent')
    tree.config(columns=replacement, displaycolumns=replacement)
    for col in replacement:
        tree.column(col, width=90, stretch=False)
    root.update()
    assert tree['columns'] == replacement
    assert tree['displaycolumns'] == replacement
    assert physical_columns(tree) == replacement
    assert tree.xview() == (0., 1.)


def test_native_header_drag_preserves_logical_column_and_total_width(root):
    tree, columns = table(root)
    tree.xview_moveto(.4)
    root.update()
    for x in range(20, tree.winfo_width() - 20):
        if tree.identify_region(x, 5) == 'separator':
            break
    else:
        pytest.fail('No visible header separator')
    name = tree.column(tree.identify_column(x), 'id')
    parcel = tree.bbox('r0', name)
    x = parcel[0] + parcel[2]
    before = tree.column(name, 'width')
    shown = physical_columns(tree)
    tree.event_generate('<ButtonPress-1>', x=x, y=5)
    tree.event_generate('<B1-Motion>', x=x + 20, y=5)
    root.update()
    assert physical_columns(tree) == shown
    tree.event_generate('<ButtonRelease-1>', x=x + 20, y=5)
    root.update()
    assert tree.column(name, 'width') == before + 20
    assert tree['columns'] == columns
    assert_visible_mapping(tree, columns)


def test_resize_and_spacer_width_changes_keep_natural_widths(root):
    tree, columns = table(root)
    tree.xview_moveto(.5)
    root.update()
    assert tree.column(columns[0], 'width') == 80
    tree.column(columns[0], width=100)
    root.geometry('940x300')
    root.update()
    assert tree.column(columns[0], 'width') == 100
    assert sum(tree.column(col, 'width') for col in columns) == 74 * 80 + 20
    assert_visible_mapping(tree, columns)
    root.geometry('640x300')
    tree.xview_moveto(0)
    root.update()
    assert tree.column(columns[0], 'width') == 100


def test_all_columns_fitting_and_explicit_display_subset(root):
    tree, columns = table(root, count=6, display=('c3', 'c1', 'c5'))
    assert tree['displaycolumns'] == ('c3', 'c1', 'c5')
    assert physical_columns(tree) == ('c3', 'c1', 'c5')
    assert tree.xview() == (0., 1.)
    assert tree.column('#1', 'id') == 'c3'
    tree.configure(displaycolumns='#all')
    root.update()
    assert physical_columns(tree) == columns


def test_configuration_queries_never_export_internal_display_window(root):
    tree, columns = table(root)
    tree.xview_moveto(.5)
    root.update()
    assert tree.configure('displaycolumns')[-1] == ('#all',)
    assert tree.config()['displaycolumns'][-1] == ('#all',)
    assert tree.configure()['columns'][-1] == columns
    assert tree.configure({}) is None


def test_header_click_after_scroll_invokes_original_logical_command(root):
    tree, columns = table(root)
    invoked = []
    for column in columns:
        tree.heading(column, command=lambda col=column: invoked.append(col))
    tree.xview_moveto(.5)
    root.update()
    column = tree.column(tree.identify_column(200), 'id')
    x, y, width, height = tree.bbox('r0', column)
    tree.event_generate('<ButtonPress-1>', x=x + width // 2, y=5)
    tree.event_generate('<ButtonRelease-1>', x=x + width // 2, y=5)
    root.update()
    assert invoked == [column]


def test_horizontal_wheel_and_native_selection_keep_complete_row_payload(root):
    from test_tk_input_responsiveness import load_node

    tree, columns = table(root)
    load_node('gui_utils.py', 'bind_mouse_scroll')(tree)
    tree.xview_moveto(.5)
    root.update()
    before = tree.xview()[0]
    tree.event_generate('<Shift-MouseWheel>', delta=-120)
    root.update()
    assert tree.xview()[0] > before
    assert tree._last_scroll_time > 0
    assert_visible_mapping(tree, columns)
    received = []
    tree.bind('<<TreeviewSelect>>', lambda event: received.append(
        tree.item(tree.selection()[0], 'values')))
    y = tree.bbox('r0')[1] + 5
    tree.event_generate('<ButtonPress-1>', x=200, y=y)
    tree.event_generate('<ButtonRelease-1>', x=200, y=y)
    root.update()
    assert tree.selection() == ('r0',)
    assert len(received[-1]) == 74 and received[-1][0] == '0:c0'


def test_vertical_scrolling_does_not_reconfigure_columns(root, monkeypatch):
    tree, _ = table(root)
    writes = []
    original = ttk.Treeview.configure

    def configure(self, *args, **kwargs):
        if 'displaycolumns' in kwargs:
            writes.append(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ttk.Treeview, 'configure', configure)
    for _ in range(5):
        tree.yview_scroll(3, 'units')
        root.update()
    assert not writes


def test_stretch_resize_round_trip_keeps_visible_mapping_and_scroll_range(root):
    tree, columns = table(root, count=20)
    for column in columns[2:]:
        tree.column(column, stretch=True)
    root.update()
    for width in (1000, 1800, 800, 1200, 640):
        root.geometry(f'{width}x300')
        root.update()
        tree.xview_moveto(1)
        root.update()
        assert tree.xview()[1] == 1
        assert_visible_mapping(tree, columns)
        assert sum(tree.column(col, 'width') for col in columns) >= tree.winfo_width() - 2


@pytest.mark.parametrize('rows', [200, 5500])
def test_existing_incremental_renderer_keeps_full_hidden_data_and_order(root, rows):
    from concurrent.futures import ThreadPoolExecutor
    import pandas as pd
    from test_tk_input_responsiveness import load_node, settle

    tree, columns = table(root)
    tree.delete(*tree.get_children())
    cls = load_node('performance_optimizer.py', 'TreeviewIncrementalUpdater')
    root.view_executor = ThreadPoolExecutor(max_workers=2)
    updater = cls(tree, list(columns), root=root)
    frame = pd.DataFrame({col: [1.] * rows for col in columns})
    frame['code'] = [f'{i:06}' for i in range(rows)]
    try:
        updater.update(frame)
        settle(root, updater)
        selected = updater._item_map['000005']
        tree.selection_set(selected)
        tree.xview_moveto(.5)
        root.update()
        updated = frame.iloc[::-1].copy()
        updated[columns[-1]] = 9.
        updater.update(updated)
        settle(root, updater)
        tree.xview_moveto(1)
        root.update()
        assert tree.get_children()[0] == updater._item_map[f'{rows - 1:06}']
        assert tree.selection() == (selected,)
        assert float(tree.item(selected, 'values')[-1]) == 9.
        assert tree['columns'] == columns
        assert len(physical_columns(tree)) <= 13
    finally:
        root._is_closing = True
        root.view_executor.shutdown(wait=True, cancel_futures=True)
