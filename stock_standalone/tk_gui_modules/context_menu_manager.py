# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk
import os
from JohnsonUtil import LoggerFactory
from stock_logic_utils import toast_message

logger = LoggerFactory.getLogger("instock_TK.ContextMenuManager")

class ContextMenuManager:
    """
    负责管理 Treeview 的右键菜单、列替换以及其他交互式快捷菜单。
    """
    def __init__(self, monitor_app):
        self.app = monitor_app
        self._menu_frame = None

    def show_column_menu(self, col, event):
        """
        右键弹出选择列菜单。
        col: 当前被点击的列名
        event: 鼠标事件
        """
        if col == "code" or col in ("#1", "code"):
            return

        if self._menu_frame and self._menu_frame.winfo_exists():
            self._menu_frame.destroy()

        # 创建顶级 Frame
        menu_frame = tk.Toplevel(self.app)
        menu_frame.overrideredirect(True)
        self._menu_frame = menu_frame

        # 搜索框
        search_var = tk.StringVar()
        search_entry = ttk.Entry(menu_frame, textvariable=search_var)
        search_entry.pack(fill="x", padx=4, pady=1)

        # 按钮容器
        btn_frame = tk.Frame(menu_frame)
        btn_frame.pack(fill="both", expand=True)

        # 动态定位逻辑
        x_root = event.x_root
        y_root = event.y_root
        screen_w = self.app.winfo_screenwidth()
        screen_h = self.app.winfo_screenheight()
        
        # 预设尺寸
        win_w, win_h = 450, 250
        x, y = x_root, y_root

        if x < screen_w / 2:
            x = x_root 
        else:
            x = x_root - win_w

        menu_frame.geometry(f"{win_w}x{win_h}+{int(x)}+{int(y)}")

        def refresh_buttons():
            for w in btn_frame.winfo_children():
                w.destroy()
            kw = search_var.get().lower()

            if kw:
                filtered = [c for c in self.app.df_all.columns if kw in c.lower() and c not in self.app.current_cols]
            else:
                keywords = ["perc","status","obs","hold","bull","has","lastdu","red","ma"]
                filtered = [c for c in self.app.df_all.columns if any(k in c.lower() for k in keywords) and c not in self.app.current_cols]

            n = len(filtered)
            cols_per_row = 5 if n > 5 else n
            for i, c in enumerate(filtered):
                btn = tk.Button(btn_frame, text=c, width=12,
                               command=lambda nc=c: [self.app.replace_column(col, nc), menu_frame.destroy()])
                btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)

        def on_search_changed(*args):
             refresh_buttons()

        search_var.trace_add("write", on_search_changed)
        refresh_buttons()

        # 失焦关闭
        menu_frame.bind("<FocusOut>", lambda e: menu_frame.destroy())
        menu_frame.focus_force()

    def replace_column(self, old_col, new_col, apply_search=True):
        """
        [DEPRECATED in main] 逻辑应保留在 ContextMenuManager 或主 App 中？
        由于 replace_column 涉及核心 Treeview 刷新，建议在主 App 保留 Proxy。
        """
        pass
