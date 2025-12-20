# -*- coding:utf-8 -*-
import logging
import traceback
import tkinter as tk
from tkinter import ttk
import pandas as pd
from typing import Any, Optional, Protocol, Union, runtime_checkable, TYPE_CHECKING
from JohnsonUtil import commonTips as cct

logger = logging.getLogger("instock_TK.Treeview")

@runtime_checkable
class TreeviewAppProtocol(Protocol):
    """Protocol for StockMonitorApp to satisfy Pylance attribute checks in TreeviewMixin."""
    df_all: pd.DataFrame
    tree: ttk.Treeview
    current_cols: list[str]
    DISPLAY_COLS: list[str]
    dfcf_var: tk.BooleanVar
    _name_col_width: int
    _pending_cols: list[str]
    def get_scaled_value(self) -> float: ...
    def refresh_tree(self, df_sorted: Optional[pd.DataFrame] = None) -> None: ...
    def bind_treeview_column_resize(self) -> None: ...

class TreeviewMixin:
    """Handles Treeview configuration, sorting, and data management."""
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        df_all: pd.DataFrame
        tree: ttk.Treeview
        current_cols: list[str]
        DISPLAY_COLS: list[str]
        dfcf_var: tk.BooleanVar
        _name_col_width: int
        _pending_cols: list[str]
        def get_scaled_value(self) -> float: ...
        def refresh_tree(self, df_sorted: Optional[pd.DataFrame] = None) -> None: ...
        def bind_treeview_column_resize(self) -> None: ...

    def _setup_tree_columns(self, tree: ttk.Treeview, cols: Union[list[str], tuple[str, ...]], sort_callback: Optional[Any] = None, other: dict[str, Any] = {}) -> None:
        """
        通用 Treeview 列初始化函数
        """
        co2int = ['ra', 'ral', 'fib', 'fibl', 'op', 'ra']
        co2width = ['boll', 'kind', 'red']
        co3other = ['MainU']
        col_scaled = self.get_scaled_value() 

        for col in cols:
            if sort_callback:
                tree.heading(col, text=col, command=lambda _col=col: sort_callback(_col, False))
            else:
                tree.heading(col, text=col)
            
            if col == "code":
                width = int(100 * col_scaled)
                minwidth = int(60 * col_scaled)
                stretch = False
            elif col == "name":
                width = int(getattr(self, "_name_col_width", 80 * col_scaled))
                minwidth = int(60 * col_scaled)
                stretch = False
            elif col in co3other:
                width = int(60 * col_scaled)
                minwidth = int(30 * col_scaled)
                stretch = False
            elif col in co2int or col in co2width:
                width = int(40 * col_scaled)
                minwidth = int(25 * col_scaled)
                stretch = not getattr(self, 'dfcf_var', tk.BooleanVar(value=False)).get()
            else:
                width = int(60 * col_scaled)
                minwidth = int(30 * col_scaled)
                stretch = not getattr(self, 'dfcf_var', tk.BooleanVar(value=False)).get()
            tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=stretch)

    def update_treeview_cols(self, new_cols: list[str]) -> None:
        try:
            if not hasattr(self, 'df_all') or self.df_all is None or self.df_all.empty:
                logger.warning("⚠️ df_all为空,无法更新列配置")
                self._pending_cols = new_cols
                return
            
            valid_cols = [c for c in new_cols if c in self.df_all.columns]
            if not valid_cols:
                valid_cols = list(self.df_all.columns)[:5]
            
            if 'code' not in valid_cols and 'code' in self.df_all.columns:
                valid_cols = ["code"] + valid_cols
 
            if valid_cols == getattr(self, 'current_cols', []):
                return
 
            self.current_cols = valid_cols
            cols = tuple(self.current_cols)
            
            self.tree["displaycolumns"] = ()
            self.tree["columns"] = ()
            self.tree.update_idletasks()
 
            self.tree["columns"] = cols
            self.tree["displaycolumns"] = cols
            self.tree.configure(show="headings")
 
            self._setup_tree_columns(
                self.tree,
                cols,
                sort_callback=getattr(self, 'sort_by_column', None)
            )
 
            self.tree.after(100, getattr(self, 'refresh_tree', lambda: None))
            self.tree.after(500, getattr(self, 'bind_treeview_column_resize', lambda: None))
 
        except Exception as e:
            logger.error(f"❌ 更新 Treeview 列失败：{e}")
            traceback.print_exc()

    def sort_by_column(self, col: str, reverse: bool) -> None:
        """点击表头排序"""
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        # 尝试转为数字排序
        try:
            l.sort(key=lambda t: float(t[0].replace('%', '').replace('+', '')), reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        # 反转排序方向，以便下次点击
        self.tree.heading(col, command=lambda _col=col: self.sort_by_column(_col, not reverse))

    def refresh_tree_with_query(self, query_dict: dict[str, Any]) -> None:
        if not hasattr(self, 'df_all') or self.df_all.empty:
            return
        
        df = self.df_all.copy()
        display_cols = getattr(self, 'DISPLAY_COLS', [])
        
        if query_dict:
            for col, cond in query_dict.items():
                if col not in df.columns:
                    continue
                if isinstance(cond, str):
                    cond = cond.strip()
                    if '~' in cond:
                        try:
                            low, high = map(float, cond.split('~'))
                            df = df[(df[col] >= low) & (df[col] <= high)]
                        except: pass
                    elif cond.startswith(('>', '<', '>=', '<=', '==')):
                        df = df.query(f"{col}{cond}")
                    else:
                        df = df[df[col].astype(str).str.contains(cond)]
                else:
                    df = df[df[col] == cond]

        self.tree.delete(*self.tree.get_children())
        for idx, row in df.iterrows():
            values = [row.get(col, '') for col in display_cols]
            self.tree.insert("", "end", values=values)
