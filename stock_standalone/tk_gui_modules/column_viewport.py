"""Horizontal paint culling for the existing, fully populated ttk Treeview."""
from bisect import bisect_left, bisect_right
from tkinter import ttk


class ColumnViewportTreeview(ttk.Treeview):
    """Keep full row values while painting the viewport and one buffer column."""

    def __init__(self, master=None, **kwargs):
        self._logical_display = ('#all',)
        self._natural_widths = {}
        self._spacers = {}
        self._viewport_after = None
        self._refreshing_viewport = False
        self._resizing_column = False
        self._last_native_view = None
        self._viewport_closed = False
        callback = kwargs.pop('xscrollcommand', kwargs.pop('xscroll', ''))
        super().__init__(master, xscrollcommand=self._native_xscroll, **kwargs)
        self._user_xscroll = self.register(callback) if callable(callback) else callback
        self._logical_display = tuple(self.tk.splitlist(super().cget('displaycolumns')))
        self.bind('<Configure>', lambda event: self._request_viewport(), add='+')
        self.bind('<ButtonPress-1>', self._begin_column_drag, add='+')
        self.bind('<ButtonRelease-1>', self._end_column_drag, add='+')
        self._request_viewport()

    def _display_order(self):
        columns = tuple(super().cget('columns'))
        if self._logical_display == ('#all',):
            return columns
        return tuple(columns[int(col)] if str(col).isdigit() else str(col)
                     for col in self._logical_display)

    def _resolve_column(self, column):
        if isinstance(column, str) and column.startswith('#') and column != '#0':
            index = int(column[1:]) - 1
            order = self._display_order()
            if 0 <= index < len(order):
                return order[index]
        return column

    def cget(self, key):
        if key == 'displaycolumns':
            return self._logical_display
        if key in ('xscrollcommand', 'xscroll'):
            return self._user_xscroll
        return super().cget(key)

    __getitem__ = cget

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, str) or (not cnf and not kwargs):
            result = super().configure(cnf, **kwargs)
            if isinstance(result, dict):
                for key in ('displaycolumns', 'xscrollcommand'):
                    result[key] = (*result[key][:-1], self.cget(key))
            elif cnf in ('displaycolumns', 'xscrollcommand'):
                result = (*result[:-1], self.cget(cnf))
            return result
        options = dict(cnf or {}, **kwargs)
        if not options:
            return super().configure()
        schema = 'columns' in options or 'displaycolumns' in options
        if schema:
            self._resizing_column = False
            self._restore_spacers()
            if 'columns' in options and 'displaycolumns' not in options:
                columns = tuple(self.tk.splitlist(options['columns']))
                options['displaycolumns'] = ('#all' if self._logical_display == ('#all',)
                                             else tuple(col for col in self._display_order() if col in columns))
        for key in ('xscroll', 'xscrollcommand'):
            if key in options:
                callback = options.pop(key)
                self._user_xscroll = self.register(callback) if callable(callback) else callback
        result = super().configure(**options) if options else None
        if schema:
            self._logical_display = tuple(self.tk.splitlist(super().cget('displaycolumns')))
            self._natural_widths.clear()
        self._request_viewport()
        return result

    config = configure

    def column(self, column, option=None, **kwargs):
        column = self._resolve_column(column)
        requested = kwargs.get('width')
        if requested is not None and column in self._spacers:
            kwargs['width'] = self._spacers[column] + int(requested) - self._natural_widths[column]
        result = super().column(column, option, **kwargs)
        if requested is not None:
            self._natural_widths[column] = int(requested)
            if column in self._spacers:
                self._spacers[column] = int(kwargs['width'])
        if kwargs:
            if any(key in kwargs for key in ('width', 'minwidth', 'stretch')):
                self._request_viewport()
        elif column in self._spacers:
            if option == 'width':
                return self._natural_widths[column]
            if option is None:
                result['width'] = self._natural_widths[column]
        return result

    def heading(self, column, option=None, **kwargs):
        return super().heading(self._resolve_column(column), option, **kwargs)

    def set(self, item, column=None, value=None):
        return super().set(item, self._resolve_column(column), value)

    def bbox(self, item, column=None):
        return super().bbox(item, self._resolve_column(column))

    def identify(self, component, x, y):
        found = super().identify(component, x, y)
        if component != 'column' or not found or found == '#0':
            return found
        column = str(super().column(found, 'id'))
        if column in self._spacers:
            return ''
        return '#' + str(self._display_order().index(column) + 1)

    def xview(self, *args):
        self._update_viewport()
        result = super().xview(*args)
        if args:
            self._update_viewport()
        return result

    def xview_moveto(self, fraction):
        self.xview('moveto', fraction)

    def xview_scroll(self, number, what):
        self.xview('scroll', number, what)

    def _native_xscroll(self, first, last):
        view = (float(first), float(last))
        if view != self._last_native_view:
            self._last_native_view = view
            self._request_viewport()
        if self._user_xscroll:
            self.tk.call(self._user_xscroll, first, last)

    def _request_viewport(self):
        if not self._viewport_closed and self._viewport_after is None:
            self._viewport_after = self.after_idle(self._apply_requested_viewport)

    def _apply_requested_viewport(self):
        self._viewport_after = None
        self._update_viewport()

    def _restore_spacers(self):
        for column in self._spacers:
            super().column(column, width=self._natural_widths[column])
        self._spacers.clear()

    def _update_viewport(self):
        if self._refreshing_viewport or self._viewport_closed:
            return
        self._refreshing_viewport = True
        try:
            order = self._display_order()
            for column in super().cget('columns'):
                if column not in self._spacers:
                    self._natural_widths[column] = int(super().column(column, 'width'))
            # Native drag bindings retain physical display indices until release.
            if self._resizing_column:
                return
            edges = [0]
            for column in order:
                edges.append(edges[-1] + self._natural_widths[column])
            width, total = max(1, self.winfo_width() - 2), edges[-1]
            shown, spacers = order, {}
            if total > width and 'tree' not in self.tk.splitlist(super().cget('show')):
                first = super().xview()[0] * total
                start = max(0, bisect_right(edges, first) - 2)
                end = min(len(order), bisect_left(edges, first + width) + 1)
                shown = order[start:end]
                # Offscreen endpoint columns carry the hidden width without
                # adding columns to the model or changing any row values.
                if start:
                    spacers[order[0]] = edges[start]
                    shown = (order[0], *shown)
                if end < len(order):
                    spacers[order[-1]] = total - edges[end]
                    shown = (*shown, order[-1])
            for column in self._spacers.keys() | spacers.keys():
                target = spacers.get(column, self._natural_widths[column])
                if int(super().column(column, 'width')) != target:
                    super().column(column, width=target)
            self._spacers = spacers
            if tuple(self.tk.splitlist(super().cget('displaycolumns'))) != shown:
                super().configure(displaycolumns=shown)
        finally:
            self._refreshing_viewport = False

    def _begin_column_drag(self, event):
        self._resizing_column = self.identify_region(event.x, event.y) == 'separator'

    def _end_column_drag(self, event):
        self._resizing_column = False
        self._request_viewport()

    def destroy(self):
        self._viewport_closed = True
        if self._viewport_after is not None:
            self.after_cancel(self._viewport_after)
            self._viewport_after = None
        super().destroy()
