import tkinter as tk
from tkinter import ttk
import pandas as pd
import random
import time
import concurrent.futures
from datetime import datetime

class StockMonitorWindow(tk.Toplevel):
    def __init__(self, parent, executor, stock_info, on_close_callback):
        super().__init__(parent)
        self.executor = executor
        self.stock_info = stock_info
        self.on_close_callback = on_close_callback
        
        self.stock_code, self.stock_name, *rest = stock_info
        
        self.title(f"监控: {self.stock_name} ({self.stock_code})")
        self.geometry("500x150")

        self.tree = self._create_treeview()
        self.tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        
        # 插入占位符行
        self.item_id = self.tree.insert("", "end", values=("", "", "", "", "", ""))
        
        # 启动刷新
        # self.refresh_stock_data()
        # 立即启动第一次刷新，无延迟
        self.refresh_once()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _create_treeview(self):
        columns = ("时间", "代码", "名称", "板块", "现价", "变动")
        tree = ttk.Treeview(self, columns=columns, show="headings")
        tree.column("时间", width=80, anchor=tk.CENTER, stretch=False)
        tree.column("代码", width=60, anchor=tk.CENTER, stretch=False)
        tree.column("名称", width=80, anchor=tk.CENTER, stretch=False)
        tree.column("板块", width=80, anchor=tk.CENTER, stretch=False)
        tree.column("现价", width=60, anchor=tk.CENTER, stretch=False)
        tree.column("变动", width=60, anchor=tk.CENTER, stretch=False)
        for col in columns:
            tree.heading(col, text=col)
        return tree

    def refresh_stock_data(self):
        """异步获取并刷新数据"""
        # 模拟数据获取
        future = self.executor.submit(self._get_stock_data_from_source, self.stock_code)
        future.add_done_callback(self._update_treeview)

    def _update_treeview(self, future):
        """回调函数，更新子窗口的Treeview"""
        try:
            data = future.result()
            if self.winfo_exists():
                now = datetime.now().strftime('%H:%M:%S')
                if data is not None:
                    # 使用item()方法直接更新数据
                    self.tree.item(self.item_id, values=(
                        now, self.stock_code, self.stock_name, 
                        self.stock_info, f"{data['Price']:.2f}", f"{data['Change']:.2f}"
                    ))
                else:
                    self.tree.item(self.item_id, values=(now, self.stock_code, "错误", "获取失败", "", ""))
        except Exception as e:
            if self.winfo_exists():
                self.tree.item(self.item_id, values=(
                    datetime.now().strftime('%H:%M:%S'), self.stock_code, "错误", str(e), "", ""
                ))
            
        if self.winfo_exists():
            self.after(5000, self.refresh_stock_data)

    def refresh_once(self):
        """异步获取数据，仅执行一次"""
        future = self.executor.submit(self._get_stock_data_from_source, self.stock_code)
        future.add_done_callback(self._on_initial_load)

    def _on_initial_load(self, future):
            """第一次加载完成后的回调，并启动循环更新"""
            self._update_treeview(future)
            self.after(5000, self._start_periodic_refresh)

    def _start_periodic_refresh(self):
        """启动定时循环刷新"""
        future = self.executor.submit(self._get_stock_data_from_source, self.stock_code)
        future.add_done_callback(self._update_treeview)
        self.after(5000, self._start_periodic_refresh)

    def _update_treeview(self, future):
        """回调函数，更新子窗口的Treeview"""
        try:
            data = future.result()
            if self.winfo_exists():
                now = datetime.now().strftime('%H:%M:%S')
                if data is not None:
                    self.tree.item(self.item_id, values=(
                        now, self.stock_code, self.stock_name, 
                        self.stock_info, f"{data['Price']:.2f}", f"{data['Change']:.2f}"
                    ))
                else:
                    self.tree.item(self.item_id, values=(now, self.stock_code, "错误", "获取失败", "", ""))
        except Exception as e:
            if self.winfo_exists():
                self.tree.item(self.item_id, values=(
                    datetime.now().strftime('%H:%M:%S'), self.stock_code, "错误", str(e), "", ""
                ))

    def on_close(self):
        """处理窗口关闭事件"""
        self.on_close_callback(self.stock_code)
        self.destroy()

    def _get_stock_data_from_source(self, stock_code):
        """模拟从源获取实时数据"""
        time.sleep(10)
        price = random.uniform(10, 100)
        change = random.uniform(-5, 5)
        return pd.Series({"Price": price, "Change": change})

