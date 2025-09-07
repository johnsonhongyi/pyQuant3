# import tkinter as tk
# from tkinter import ttk, messagebox
# import pandas as pd
# import random
# import time
# import concurrent.futures
# from datetime import datetime
# import json
# import os
# import threading

# # 全局变量
# root = None
# stock_tree = None
# context_menu = None
# code_entry = None
# monitor_windows = {}
# executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# MONITOR_LIST_FILE = "monitor_list.json"
# loaddf = pd.DataFrame()
# last_updated_time = None
# loaddf_lock = threading.Lock()

# # --- 数据持久化函数 ---
# def save_monitor_list():
#     monitor_list = [item['stock_info'] for item in monitor_windows.values()]
#     with open(MONITOR_LIST_FILE, "w") as f:
#         json.dump(monitor_list, f)
#     print(f"监控列表已保存到 {MONITOR_LIST_FILE}")

# def load_monitor_list():
#     if os.path.exists(MONITOR_LIST_FILE):
#         with open(MONITOR_LIST_FILE, "r") as f:
#             try:
#                 loaded_list = json.load(f)
#                 if isinstance(loaded_list, list) and all(isinstance(item, (list, tuple)) for item in loaded_list):
#                     return [list(item) for item in loaded_list]
#                 return []
#             except (json.JSONDecodeError, TypeError):
#                 return []
#     return []

# # --- 模拟数据和函数 ---
# def get_stock_data_from_source(stock_code):
#     time.sleep(1)
#     price = random.uniform(10, 100)
#     change = random.uniform(-5, 5)
#     return pd.Series({"Price": price, "Change": change})

# def _get_stock_changes(selected_type=None, stock_code=None, update_interval_minutes=5):
#     """获取股票异动数据"""
#     global loaddf, last_updated_time
#     current_time = datetime.now()
#     with loaddf_lock:
#         if last_updated_time is None or current_time - last_updated_time >= timedelta(minutes=update_interval_minutes):
#             time.sleep(1)
#             new_data = {
#                 '时间': [datetime.now().strftime("%H:%M:%S")],
#                 '代码': [stock_code],
#                 '简称': [f'股票{stock_code}'],
#                 '板块': [selected_type],
#                 '相关信息': [f"{random.uniform(0, 1):.6f},{random.uniform(10, 20):.2f},{random.uniform(0, 1):.6f}"]
#             }
#             new_df = pd.DataFrame(new_data)
#             loaddf = pd.concat([loaddf, new_df], ignore_index=True)
#             loaddf.drop_duplicates(subset=['代码', '板块'], keep='last', inplace=True)
#             last_updated_time = current_time
#         else:
#             print("未到更新时间，返回内存中的 loaddf 数据。")

# def _get_stock_info_by_code(stock_code):
#     if stock_code == "600000":
#         return ["600000", "股票A", "银行", "12.34", "0.56"]
#     elif stock_code == "600001":
#         return ["600001", "股票B", "钢铁", "25.45", "-1.23"]
#     else:
#         return [stock_code, f"未知{stock_code}", "未知", "0.00", "0.00"]

# def generate_stock_data():
#     stocks = [
#         ("600000", "股票A", "银行"),
#         ("600001", "股票B", "钢铁"),
#         ("000001", "股票C", "银行"),
#         ("000002", "股票D", "地产"),
#     ]
#     data = []
#     for code, name, sector in stocks:
#         price = random.uniform(10, 100)
#         change = random.uniform(-5, 5)
#         data.append([code, name, sector, f"{price:.2f}", f"{change:.2f}"])
#     return data

# # --- 子窗口监控逻辑 ---
# def refresh_stock_data(window_info, tree, item_id):
#     stock_info = window_info['stock_info']
#     stock_code = stock_info
#     window = window_info['toplevel']
#     future = executor.submit(get_stock_data_from_source, stock_code)
#     future.add_done_callback(lambda f: update_monitor_tree(f, tree, window_info, item_id))

# def update_monitor_tree(future, tree, window_info, item_id):
#     stock_info = window_info['stock_info']
#     window = window_info['toplevel']
#     stock_code, stock_name, *rest = stock_info
#     try:
#         data = future.result()
#         if data is not None and window.winfo_exists():
#             now = datetime.now().strftime('%H:%M:%S')
#             tree.item(item_id, values=(now, stock_code, stock_name, rest, f"{data['Price']:.2f}", f"{data['Change']:.2f}"))
#     except Exception as e:
#         if window.winfo_exists():
#             tree.item(item_id, values=(datetime.now().strftime('%H:%M:%S'), stock_code, stock_name, rest, "错误", str(e)))
#     if window.winfo_exists():
#         window.after(5000, lambda: refresh_stock_data(window_info, tree, item_id))

# def on_close_monitor(window_info):
#     stock_info = window_info['stock_info']
#     stock_code = stock_info
#     window = window_info['toplevel']
#     if stock_code in monitor_windows:
#         del monitor_windows[stock_code]
#         save_monitor_list()
#     window.destroy()

# def create_monitor_window(stock_info):
#     stock_code, stock_name, *rest = stock_info
#     monitor_win = tk.Toplevel(root)
#     monitor_win.title(f"监控: {stock_name} ({stock_code})")
#     monitor_win.geometry("500x150")
#     window_info = {'stock_info': stock_info, 'toplevel': monitor_win}

#     def on_click_monitor_window(event):
#         global code_entry
#         code_entry.delete(0, tk.END)
#         code_entry.insert(0, stock_code)

#     def delete_monitor():
#         nonlocal window_info
#         on_close_monitor(window_info)

#     monitor_win.bind("<Button-1>", on_click_monitor_window)
#     delete_btn = ttk.Button(monitor_win, text="删除", command=delete_monitor)
#     delete_btn.pack(side=tk.TOP, pady=5)
    
#     # 使用 frame 包含 treeview 和 scrollbar
#     tree_frame = ttk.Frame(monitor_win)
#     tree_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

#     columns = ("时间", "代码", "名称", "板块", "现价", "变动")
#     monitor_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
#     monitor_tree.column("时间", width=80, anchor=tk.CENTER, stretch=False)
#     monitor_tree.column("代码", width=60, anchor=tk.CENTER, stretch=False)
#     monitor_tree.column("名称", width=80, anchor=tk.CENTER, stretch=False)
#     monitor_tree.column("板块", width=80, anchor=tk.CENTER, stretch=False)
#     monitor_tree.column("现价", width=60, anchor=tk.CENTER, stretch=False)
#     monitor_tree.column("变动", width=60, anchor=tk.CENTER, stretch=False)
#     for col in columns:
#         monitor_tree.heading(col, text=col)

#     # 添加垂直滚动条
#     vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=monitor_tree.yview)
#     vsb.pack(side=tk.RIGHT, fill=tk.Y)
#     monitor_tree.configure(yscrollcommand=vsb.set)

#     monitor_tree.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

#     item_id = monitor_tree.insert("", "end", values=("加载中...", "", "", "", "", ""))
#     refresh_stock_data(window_info, monitor_tree, item_id)
#     monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(window_info))
#     return window_info

# # --- 主窗口逻辑 ---
# def add_selected_stock():
#     try:
#         selected_item = stock_tree.selection()
#         if not selected_item:
#             messagebox.showwarning("警告", "请选择一个股票代码。")
#             return
#         stock_info = list(stock_tree.item(selected_item, "values"))
#         stock_code = stock_info
#         if stock_code in monitor_windows:
#             messagebox.showwarning("警告", f"{stock_code} 的监控窗口已打开。")
#             return
#         window_info = create_monitor_window(stock_info)
#         monitor_windows[stock_code] = window_info
#         save_monitor_list()
#     except IndexError:
#         messagebox.showwarning("警告", "请选择一个股票代码。")

# def show_context_menu(event):
#     try:
#         item = stock_tree.identify_row(event.y)
#         if item:
#             stock_tree.selection_set(item)
#             context_menu.post(event.x_root, event.y_root)
#     except Exception:
#         pass

# def load_initial_data():
#     stock_tree.delete(*stock_tree.get_children())
#     data = generate_stock_data()
#     for row in data:
#         stock_tree.insert("", "end", values=row)

# def on_main_window_close():
#     save_monitor_list()
#     for win_info in list(monitor_windows.values()):
#         win_info['toplevel'].destroy()
#     executor.shutdown(wait=False)
#     root.destroy()
    
# def update_code_entry(stock_code):
#     global code_entry
#     code_entry.delete(0, tk.END)
#     code_entry.insert(0, stock_code)

# def create_popup_window():
#     # 创建新的 Toplevel 窗口（弹出窗口）
#     popup_window = tk.Toplevel(root)
#     popup_window.title("弹出窗口")
#     popup_window.geometry("200x100") # 设置子窗口大小

#     # 在子窗口中添加一个标签
#     label = tk.Label(popup_window, text="这是一个弹出窗口！")
#     label.pack(pady=20) # 使用 pack 布局并添加一些垂直填充

# def setup_main_window():
#     global root, stock_tree, context_menu, code_entry
#     root = tk.Tk()
#     root.title("单文件监控")
#     root.geometry("600x400")
#     entry_frame = ttk.Frame(root)
#     entry_frame.pack(fill=tk.X, padx=10, pady=5)
#     ttk.Label(entry_frame, text="股票代码:").pack(side=tk.LEFT, padx=5)
#     code_entry = ttk.Entry(entry_frame)
#     code_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
#     columns = ("代码", "简称", "板块", "现价", "变动")
#     stock_tree = ttk.Treeview(root, columns=columns, show="headings")
#     stock_tree.column("代码", width=80, anchor=tk.CENTER, stretch=False)
#     stock_tree.column("简称", width=120, anchor=tk.CENTER, stretch=False)
#     stock_tree.column("板块", width=120, anchor=tk.CENTER, stretch=False)
#     stock_tree.column("现价", width=80, anchor=tk.CENTER, stretch=False)
#     stock_tree.column("变动", width=80, anchor=tk.CENTER, stretch=False)
#     for col in columns:
#         stock_tree.heading(col, text=col)
#     stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
#     stock_tree.bind("<Button-3>", show_context_menu)
#     context_menu = tk.Menu(root, tearoff=0)
#     context_menu.add_command(label="添加到监控", command=add_selected_stock)
#     load_initial_data()
#     initial_monitor_list = load_monitor_list()
#     # if initial_monitor_list:
#     #     for stock_info in initial_monitor_list:
#     #         stock_code = stock_info
#     #         if stock_code not in list(monitor_windows):
#     #             window_info = create_monitor_window(stock_info)
#     #             monitor_windows[stock_code] = window_info
#     root.protocol("WM_DELETE_WINDOW", on_main_window_close)

#     # 在主窗口中创建一个按钮，点击时会调用 create_popup_window 函数
#     popup_button = tk.Button(root, text="弹出子窗口", command=create_popup_window)
#     popup_button.pack(pady=50) # 将按钮放置在主窗口中

#     root.mainloop()

# if __name__ == "__main__":
#     setup_main_window()



# import tkinter as tk
# from tkinter import ttk

# # --- Function for the Sub Window ---
# def create_sub_window(parent_window):
#     """Creates and returns the sub window and its entry widget."""
#     sub_window = tk.Toplevel(parent_window)
#     sub_window.title("Sub Window")
#     sub_window.geometry("300x200")
    
#     code_entry = ttk.Entry(sub_window, width=40)
#     code_entry.pack(pady=20)
    
#     return sub_window, code_entry

# # --- Function to Handle Data Sending ---
# def send_to_subwindow(search_entry, sub_window, code_entry, event=None):
#     """Sends text from the search entry to the sub window's code entry."""
#     # Check if the subwindow exists before trying to update it.
#     if sub_window and sub_window.winfo_exists():
#         search_text = search_entry.get()
#         code_entry.delete(0, tk.END)
#         code_entry.insert(0, search_text)

# # --- Main Application Logic ---
# def main():
#     """Initializes the main application window and its components."""
#     root = tk.Tk()
#     root.title("Main Window")
#     root.geometry("500x400")
    
#     # These will be initialized later when the subwindow is opened.
#     sub_window = None
#     code_entry = None

#     # Function to open the subwindow and store its widgets.
#     def open_subwindow():
#         nonlocal sub_window, code_entry
#         if not sub_window or not sub_window.winfo_exists():
#             sub_window, code_entry = create_sub_window(root)

#     # Function that wraps the sender to pass the correct arguments.
#     def handle_key_press(event):
#         # We must check if the sub_window and code_entry are available
#         # before calling the sender function.
#         if sub_window and code_entry:
#             send_to_subwindow(search_entry, sub_window, code_entry, event)

#     # --- Main Window Widgets ---
#     search_frame = ttk.Frame(root)
#     search_frame.pack(pady=10)
    
#     ttk.Label(search_frame, text="Search:").pack(side="left", padx=5)
#     search_entry = ttk.Entry(search_frame)
#     search_entry.pack(side="left", padx=5)
    
#     # Bind the entry's change event to the wrapping function.
#     search_entry.bind("<KeyRelease>", handle_key_press)
    
#     open_btn = ttk.Button(root, text="Open Sub Window", command=open_subwindow)
#     open_btn.pack(pady=10)
    
#     root.mainloop()

# if __name__ == "__main__":
#     main()


import tkinter as tk
from tkinter import ttk
import pandas as pd

# 假设这是你的 DataFrame，并用作全域变量
df = pd.DataFrame([
    ("14:55:01", "000001", "平安银行", "大笔买入", "资金流入"),
    ("14:58:30", "600000", "浦发银行", "竞价上涨", "涨幅超3%"),
    ("14:59:15", "000002", "万科A", "向上缺口", "股价创60日新高"),
    ("14:56:45", "601398", "工商银行", "快速反弹", "股价反弹"),
], columns=["时间", "代码", "名称", "异动类型", "相关信息"])

# 设置一个变量来追踪每列的排序方向
sort_directions = {}

def load_df_to_treeview(tree, dataframe):
    """
    将 DataFrame 的内容加载到 Treeview 中。
    """
    tree.delete(*tree.get_children())
    
    for row in dataframe.itertuples(index=False):
        tree.insert("", "end", values=row)

def sort_treeview(tree, col_name):
    """
    点击列标题时，使用 DataFrame 排序并更新 Treeview。
    """
    global df
    
    # 获取当前排序方向，如果未设置则默认为 False (升序)
    reverse_sort = sort_directions.get(col_name, False)
    
    # --- 核心逻辑修改部分 ---
    if col_name == '时间':
        # 如果点击的是“时间”列，强制按增序排序（reverse=False）
        df.sort_values(by=col_name, ascending=True, inplace=True)
        # 强制更新排序方向为 True，以便下一次点击时为降序
        sort_directions[col_name] = True
    else:
        # 其他列正常切换排序方向
        df.sort_values(by=col_name, ascending=not reverse_sort, inplace=True)
        # 更新排序方向
        sort_directions[col_name] = not reverse_sort
    
    # 重新加载排序后的 DataFrame 到 Treeview
    load_df_to_treeview(tree, df)
    
def create_main_window():
    root = tk.Tk()
    root.title("Treeview DataFrame 排序示例")

    columns = ["时间", "代码", "名称", "异动类型", "相关信息"]
    
    stock_tree = ttk.Treeview(root, columns=columns, show='headings')
    
    for col in columns:
        stock_tree.heading(col, text=col, command=lambda c=col: sort_treeview(stock_tree, c))
        stock_tree.column(col, width=120, anchor=tk.CENTER)

    # 首次加载数据
    load_df_to_treeview(stock_tree, df)

    stock_tree.pack(fill=tk.BOTH, expand=True)
    root.mainloop()

if __name__ == "__main__":
    create_main_window()

