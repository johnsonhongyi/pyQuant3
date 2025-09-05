import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import random
import time
import concurrent.futures
from datetime import datetime
import json
import os

# 全局变量
root = None
stock_tree = None
context_menu = None
# monitor_windows 将存储一个包含 stock_info 和 Toplevel 的字典
monitor_windows = {} 
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

MONITOR_LIST_FILE = "monitor_list.json"

# --- 数据持久化函数 ---
def save_monitor_list():
    """保存当前的监控股票列表到文件"""
    # 从 monitor_windows 中提取 stock_info
    monitor_list = [item['stock_info'] for item in monitor_windows.values()]
    with open(MONITOR_LIST_FILE, "w") as f:
        json.dump(monitor_list, f)
    print(f"监控列表已保存到 {MONITOR_LIST_FILE}")

def load_monitor_list():
    """从文件加载监控股票列表"""
    if os.path.exists(MONITOR_LIST_FILE):
        with open(MONITOR_LIST_FILE, "r") as f:
            try:
                loaded_list = json.load(f)
                if isinstance(loaded_list, list) and all(isinstance(item, (list, tuple)) for item in loaded_list):
                    return [list(item) for item in loaded_list]
                return []
            except (json.JSONDecodeError, TypeError):
                return []
    return []

# --- 模拟数据和函数 ---
def get_stock_data_from_source(stock_code):
    """模拟从源获取实时数据"""
    time.sleep(1)
    price = random.uniform(10, 100)
    change = random.uniform(-5, 5)
    return pd.Series({"Price": price, "Change": change})

def generate_stock_data():
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
        data.append([code, name, sector, f"{price:.2f}", f"{change:.2f}"])
    return data

# --- 子窗口监控逻辑 ---
def refresh_stock_data(window_info, tree, item_id):
    """异步获取并刷新数据"""
    stock_info = window_info['stock_info']
    stock_code = stock_info[0] # 使用 stock_info 中的第一个元素作为股票代码
    window = window_info['toplevel']
    
    future = executor.submit(get_stock_data_from_source, stock_code)
    future.add_done_callback(lambda f: update_monitor_tree(f, tree, window_info, item_id))

def update_monitor_tree(future, tree, window_info, item_id):
    """回调函数，更新子窗口的Treeview"""
    stock_info = window_info['stock_info']
    window = window_info['toplevel']
    stock_code, stock_name, *rest = stock_info

    try:
        data = future.result()
        if data is not None and window.winfo_exists():
            now = datetime.now().strftime('%H:%M:%S')
            tree.item(item_id, values=(
                now, stock_code, stock_name, rest, f"{data['Price']:.2f}", f"{data['Change']:.2f}"
            ))
    except Exception as e:
        if window.winfo_exists():
            tree.item(item_id, values=(
                datetime.now().strftime('%H:%M:%S'), stock_code, stock_name, rest, "错误", str(e)
            ))
            
    if window.winfo_exists():
        window.after(5000, lambda: refresh_stock_data(window_info, tree, item_id))


def on_close_monitor(window_info):
    """处理子窗口关闭事件"""
    stock_info = window_info['stock_info']
    stock_code = stock_info[0] # 使用 stock_info 中的第一个元素作为股票代码
    window = window_info['toplevel']
    if stock_code in monitor_windows:
        del monitor_windows[stock_code]
        save_monitor_list()
    window.destroy()

def create_monitor_window(stock_info):
    """创建并配置子窗口，使用Treeview显示数据"""
    stock_code, stock_name, *rest = stock_info
    
    monitor_win = tk.Toplevel(root)
    monitor_win.title(f"监控: {stock_name} ({stock_code})")
    monitor_win.geometry("500x150")
    
    # 将 stock_info 和 Toplevel 实例打包到一个字典中
    window_info = {'stock_info': stock_info, 'toplevel': monitor_win}
    
    columns = ("时间", "代码", "名称", "板块", "现价", "变动")
    monitor_tree = ttk.Treeview(monitor_win, columns=columns, show="headings")
    monitor_tree.column("时间", width=80, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("代码", width=60, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("名称", width=80, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("板块", width=80, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("现价", width=60, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("变动", width=60, anchor=tk.CENTER, stretch=False)
    for col in columns:
        monitor_tree.heading(col, text=col)
    monitor_tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
    
    item_id = monitor_tree.insert("", "end", values=("加载中...", "", "", "", "", ""))
    
    refresh_stock_data(window_info, monitor_tree, item_id)
    monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(window_info))
    
    return window_info

# --- 主窗口逻辑 ---
def add_selected_stock():
    """添加选中的股票到监控窗口"""
    try:
        selected_item = stock_tree.selection()
        if not selected_item:
            messagebox.showwarning("警告", "请选择一个股票代码。")
            return

        stock_info = list(stock_tree.item(selected_item, "values"))
        stock_code = stock_info[0] # 使用 stock_info 中的第一个元素作为股票代码
        
        if stock_code in monitor_windows:
            messagebox.showwarning("警告", f"{stock_code} 的监控窗口已打开。")
            return

        window_info = create_monitor_window(stock_info)
        monitor_windows[stock_code] = window_info
        save_monitor_list()

    except IndexError:
        messagebox.showwarning("警告", "请选择一个股票代码。")

def show_context_menu(event):
    """显示右键菜单"""
    try:
        item = stock_tree.identify_row(event.y)
        if item:
            stock_tree.selection_set(item)
            context_menu.post(event.x_root, event.y_root)
    except Exception:
        pass

def load_initial_data():
    """加载初始股票数据到Treeview"""
    stock_tree.delete(*stock_tree.get_children())
    data = generate_stock_data()
    for row in data:
        stock_tree.insert("", "end", values=row)

def on_main_window_close():
    """处理主窗口关闭事件"""
    save_monitor_list()
    for win_info in list(monitor_windows.values()):
        win_info['toplevel'].destroy()
    executor.shutdown(wait=False)
    root.destroy()

def setup_main_window():
    """设置主窗口和UI元素"""
    global root, stock_tree, context_menu

    root = tk.Tk()
    root.title("单文件监控")
    root.geometry("600x400")

    columns = ("代码", "简称", "板块", "现价", "变动")
    stock_tree = ttk.Treeview(root, columns=columns, show="headings")
    stock_tree.column("代码", width=80, anchor=tk.CENTER, stretch=False)
    stock_tree.column("简称", width=120, anchor=tk.CENTER, stretch=False)
    stock_tree.column("板块", width=120, anchor=tk.CENTER, stretch=False)
    stock_tree.column("现价", width=80, anchor=tk.CENTER, stretch=False)
    stock_tree.column("变动", width=80, anchor=tk.CENTER, stretch=False)
    for col in columns:
        stock_tree.heading(col, text=col)
    stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

    stock_tree.bind("<Button-3>", show_context_menu)

    context_menu = tk.Menu(root, tearoff=0)
    context_menu.add_command(label="添加到监控", command=add_selected_stock)

    load_initial_data()
    
    initial_monitor_list = load_monitor_list()
    if initial_monitor_list:
        for stock_info in initial_monitor_list:
            stock_code = stock_info[0]
            if stock_code not in monitor_windows:
                window_info = create_monitor_window(stock_info)
                monitor_windows[stock_code] = window_info

    root.protocol("WM_DELETE_WINDOW", on_main_window_close)
    root.mainloop()

if __name__ == "__main__":
    setup_main_window()
