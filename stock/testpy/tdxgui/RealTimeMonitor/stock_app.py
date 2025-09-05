import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import random
import time
import concurrent.futures
import json
import os
from stock_monitor_window import StockMonitorWindow

class StockApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("单文件监控")
        self.geometry("600x400")

        self.monitor_windows = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.monitor_list_file = "monitor_list.json"
        
        self.tree = self._create_main_treeview()
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._bind_events()
        
        self.load_initial_data()
        self.load_and_open_monitors()

        self.protocol("WM_DELETE_WINDOW", self.on_main_window_close)
    
    def _create_main_treeview(self):
        columns = ("代码", "简称", "板块", "现价", "变动")
        tree = ttk.Treeview(self, columns=columns, show="headings")
        tree.column("代码", width=80, anchor=tk.CENTER, stretch=False)
        tree.column("简称", width=120, anchor=tk.CENTER, stretch=False)
        tree.column("板块", width=120, anchor=tk.CENTER, stretch=False)
        tree.column("现价", width=80, anchor=tk.CENTER, stretch=False)
        tree.column("变动", width=80, anchor=tk.CENTER, stretch=False)
        for col in columns:
            tree.heading(col, text=col)
        return tree
    
    def _bind_events(self):
        self.tree.bind("<Button-3>", self._show_context_menu)
        
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="添加到监控", command=self._add_selected_stock)

    def load_initial_data(self):
        """加载初始股票数据到Treeview"""
        data = self._generate_stock_data()
        for row in data:
            self.tree.insert("", "end", values=row)

    def load_and_open_monitors(self):
        """自动加载并开启监控窗口"""
        initial_monitor_list = self._load_monitor_list()
        for stock_info in initial_monitor_list:
            stock_code = stock_info[0] # Use the code from the saved tuple
            if stock_code not in self.monitor_windows:
                self._open_monitor_window(stock_info)

    def _show_context_menu(self, event):
        """显示右键菜单"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def _add_selected_stock(self):
        """添加选中的股票到监控窗口"""
        try:
            selected_item = self.tree.selection()
            if not selected_item:
                messagebox.showwarning("警告", "请选择一个股票代码。")
                return

            stock_info = self.tree.item(selected_item, "values")
            self._open_monitor_window(stock_info)

        except IndexError:
            messagebox.showwarning("警告", "请选择一个股票代码。")
    
    def _open_monitor_window(self, stock_info):
        stock_code = stock_info[0] # The code is the first element
        if stock_code in self.monitor_windows:
            messagebox.showwarning("警告", f"{stock_code} 的监控窗口已打开。")
            return

        monitor_win = StockMonitorWindow(
            self, self.executor, stock_info, self._on_monitor_close
        )
        self.monitor_windows[stock_code] = monitor_win
        self._save_monitor_list()

    def _on_monitor_close(self, stock_code):
        """处理子窗口关闭事件"""
        if stock_code in self.monitor_windows:
            del self.monitor_windows[stock_code]
            self._save_monitor_list()

    def on_main_window_close(self):
        """处理主窗口关闭事件"""
        self._save_monitor_list()
        for win in list(self.monitor_windows.values()):
            win.destroy()
        self.executor.shutdown(wait=False)
        self.destroy()

    def _save_monitor_list(self):
        """保存当前的监控股票列表到文件"""
        # Save a list of all stock_info tuples from the monitor windows
        monitor_list = [win.stock_info for win in self.monitor_windows.values()]
        with open(self.monitor_list_file, "w") as f:
            json.dump(monitor_list, f)

    def _load_monitor_list(self):
        """从文件加载监控股票列表"""
        if os.path.exists(self.monitor_list_file):
            with open(self.monitor_list_file, "r") as f:
                try:
                    loaded_list = json.load(f)
                    # Convert any lists back to tuples if necessary
                    return [tuple(item) for item in loaded_list]
                except (json.JSONDecodeError, TypeError):
                    return []
        return []

    def _generate_stock_data(self):
        """生成模拟股票数据"""
        stocks = [
            ("600000", "股票A", "银行"),
            ("600001", "股票B", "钢铁"),
            ("000001", "股票C", "银行"),
            ("000002", "股票D", "地产"),
        ]
        data = []
        for code, name, sector in stocks:
            price = random.uniform(10, 100)
            change = random.uniform(-5, 5)
            data.append((code, name, sector, f"{price:.2f}", f"{change:.2f}"))
        return data


if __name__ == "__main__":
    app = StockApp()
    app.mainloop()

