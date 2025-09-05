# import tkinter as tk
# from tkinter import ttk, messagebox
# import pandas as pd
# import random
# import time
# import concurrent.futures

# # 全局变量
# root = None
# stock_tree = None
# context_menu = None
# monitor_windows = {}  # 存储监控窗口实例
# executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# # --- 模拟数据和函数 ---
# def get_stock_data_from_source(stock_code):
#     """模拟从源获取实时数据"""
#     time.sleep(1) # 模拟网络延迟
#     price = random.uniform(10, 100)
#     change = random.uniform(-5, 5)
#     return pd.Series({"Price": price, "Change": change})

# def generate_stock_data():
#     """生成模拟股票数据"""
#     stocks = [
#         ("600000", "股票A"),
#         ("600001", "股票B"),
#         ("000001", "股票C"),
#         ("000002", "股票D"),
#     ]
#     data = []
#     for code, name in stocks:
#         price = random.uniform(10, 100)
#         change = random.uniform(-5, 5)
#         data.append((code, name, f"{price:.2f}", f"{change:.2f}"))
#     return data

# # --- 子窗口监控逻辑 ---
# def refresh_stock_data(window, stock_code, label):
#     """异步获取并刷新数据"""
#     future = executor.submit(get_stock_data_from_source, stock_code)
#     future.add_done_callback(lambda f: update_label(f, label, window, stock_code))

# def update_label(future, label, window, stock_code):
#     """回调函数，更新标签"""
#     try:
#         data = future.result()
#         if data is not None and window.winfo_exists():
#             label.config(text=f"价格: {data['Price']:.2f}, 变动: {data['Change']:.2f}")
#     except Exception as e:
#         if window.winfo_exists():
#             label.config(text=f"错误: {e}")
            
#     # 如果窗口仍然存在，则安排下一次刷新
#     if window.winfo_exists():
#         window.after(5000, lambda: refresh_stock_data(window, stock_code, label))

# def on_close_monitor(window, stock_code):
#     """处理子窗口关闭事件"""
#     if stock_code in monitor_windows:
#         del monitor_windows[stock_code]
#     window.destroy()

# def create_monitor_window(stock_code, stock_name):
#     """创建并配置子窗口"""
#     monitor_win = tk.Toplevel(root)
#     monitor_win.title(f"监控: {stock_name}")
#     monitor_win.geometry("300x150")

#     label = ttk.Label(monitor_win, text="正在获取数据...", anchor=tk.CENTER)
#     label.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

#     # 启动刷新
#     refresh_stock_data(monitor_win, stock_code, label)
    
#     # 捕捉窗口关闭事件
#     monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(monitor_win, stock_code))
    
#     return monitor_win

# # --- 主窗口逻辑 ---
# def add_selected_stock():
#     """添加选中的股票到监控窗口"""
#     try:
#         selected_item = stock_tree.selection()
#         if not selected_item:
#             messagebox.showwarning("警告", "请选择一个股票代码。")
#             return

#         stock_info = stock_tree.item(selected_item, "values")
#         stock_code = stock_info[0]
#         stock_name = stock_info[1]
        
#         if stock_code in monitor_windows:
#             messagebox.showwarning("警告", f"{stock_code} 的监控窗口已打开。")
#             return

#         monitor_win = create_monitor_window(stock_code, stock_name)
#         monitor_windows[stock_code] = monitor_win

#     except IndexError:
#         messagebox.showwarning("警告", "请选择一个股票代码。")

# def show_context_menu(event):
#     """显示右键菜单"""
#     try:
#         item = stock_tree.identify_row(event.y)
#         if item:
#             stock_tree.selection_set(item)
#             context_menu.post(event.x_root, event.y_root)
#     except Exception:
#         pass

# def load_initial_data():
#     """加载初始股票数据到Treeview"""
#     stock_tree.delete(*stock_tree.get_children())
#     data = generate_stock_data()
#     for row in data:
#         stock_tree.insert("", "end", values=row)

# def on_main_window_close():
#     """处理主窗口关闭事件"""
#     for win in list(monitor_windows.values()):
#         win.destroy()
#     executor.shutdown(wait=False)
#     root.destroy()

# def setup_main_window():
#     """设置主窗口和UI元素"""
#     global root, stock_tree, context_menu

#     root = tk.Tk()
#     root.title("单文件监控")
#     root.geometry("600x400")

#     columns = ("代码", "简称", "现价", "竞价涨幅")
#     stock_tree = ttk.Treeview(root, columns=columns, show="headings")
#     for col in columns:
#         stock_tree.heading(col, text=col, anchor=tk.CENTER)
#         stock_tree.column(col, width=120, anchor=tk.CENTER)
#     stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

#     stock_tree.bind("<Button-3>", show_context_menu)

#     context_menu = tk.Menu(root, tearoff=0)
#     context_menu.add_command(label="添加到监控", command=add_selected_stock)

#     load_initial_data()

#     root.protocol("WM_DELETE_WINDOW", on_main_window_close)
#     root.mainloop()


# if __name__ == "__main__":
#     setup_main_window()


'''
import tkinter as tk
from tkinter import ttk
import random

# A mock function to simulate fetching real-time stock data.
def fetch_stock_data(stock_code):
    """Simulates fetching real-time stock data for a given code."""
    price = round(random.uniform(100.0, 500.0), 2)
    change = round(random.uniform(-5.0, 5.0), 2)
    return {"price": price, "change": change}

class SubWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Stock Data")
        self.geometry("350x250")
        
        self.stock_code = ""
        
        # Widgets to display the stock data
        ttk.Label(self, text="Stock Code:").pack(pady=5)
        self.code_label = ttk.Label(self, text="No stock selected", font=("Helvetica", 12, "bold"))
        self.code_label.pack(pady=5)
        
        ttk.Label(self, text="Current Price:").pack(pady=5)
        self.price_label = ttk.Label(self, text="N/A", font=("Helvetica", 14))
        self.price_label.pack(pady=5)
        
        ttk.Label(self, text="Daily Change:").pack(pady=5)
        self.change_label = ttk.Label(self, text="N/A", font=("Helvetica", 14))
        self.change_label.pack(pady=5)
        
        # Start the periodic data refresh.
        self.refresh_data()
        
    def refresh_data(self):
        """Fetches and displays updated stock data."""
        if self.stock_code:
            data = fetch_stock_data(self.stock_code)
            self.code_label.config(text=self.stock_code)
            self.price_label.config(text=f"${data['price']}")
            self.change_label.config(text=f"{data['change']}%")
        
        # Schedule the next refresh in 5 seconds (5000 ms).
        self.after(5000, self.refresh_data)
        
    def set_stock_code(self, new_code):
        """Updates the stock code and triggers an immediate refresh."""
        if self.stock_code != new_code:
            self.stock_code = new_code
            self.refresh_data()

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stock Selection")
        self.geometry("400x300")
        
        self.sub_window = None
        
        # Treeview to display stock codes
        self.tree = ttk.Treeview(self, columns=("Code"), show="headings")
        self.tree.heading("Code", text="Stock Code")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Sample stock codes
        stock_codes = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
        for code in stock_codes:
            self.tree.insert("", "end", values=(code,))
            
        # Bind the selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # Button to open the sub-window
        ttk.Button(self, text="Open Stock Data Window", command=self.open_sub_window).pack(pady=10)

    def open_sub_window(self):
        """Opens the sub-window if it's not already open."""
        if not self.sub_window or not self.sub_window.winfo_exists():
            self.sub_window = SubWindow(self)

    def on_tree_select(self, event):
        """Handles the Treeview selection event."""
        selected_item = self.tree.selection()
        if selected_item and self.sub_window and self.sub_window.winfo_exists():
            stock_code = self.tree.item(selected_item, "values")[0]
            self.sub_window.set_stock_code(stock_code)
            
if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
'''


import tkinter as tk
from tkinter import ttk

# --- 副視窗相關函數 ---

def create_details_window(parent):
    """建立並返回副視窗物件，包含更新函數。"""
    
    # 建立副視窗
    details_window = tk.Toplevel(parent)
    details_window.title("股票详细信息")
    details_window.geometry("400x300")
    
    # 用於顯示股票代碼的標籤
    stock_code_label = ttk.Label(details_window, text="未选择股票", font=('Microsoft YaHei', 12))
    stock_code_label.pack(pady=10)
    
    # 建立一個內部函數來處理副視窗的數據更新
    def refresh_data(stock_code):
        """根據股票代碼更新副視窗的數據。"""
        stock_code_label.config(text=f"当前股票代码: {stock_code}")
        print(f"副窗口已接收到股票代码: {stock_code}，正在更新数据...")
    
    # 將 refresh_data 函數作為一個屬性附加到副視窗物件上
    details_window.refresh_data = refresh_data
    
    return details_window


# --- 主視窗相關函數 ---

def main():
    """主應用程式函數，建立所有視窗和介面。"""
    root = tk.Tk()
    root.title("主窗口")

    # 建立副視窗並保存其引用
    details_window = create_details_window(root)

    # 假設的數據
    stock_data = {
        "000001": {"name": "平安银行"},
        "600000": {"name": "浦发银行"},
        "601398": {"name": "工商银行"},
    }

    # 建立 Treeview
    stock_tree = ttk.Treeview(root, columns=('代码', '简称'), show='headings')
    stock_tree.heading('代码', text='代码')
    stock_tree.heading('简称', text='简称')
    
    for code, info in stock_data.items():
        stock_tree.insert("", "end", values=(code, info['name']))
        
    stock_tree.pack(pady=10, padx=10)

    def on_table_select(event):
        """處理 Treeview 選擇事件"""
        selected_item = stock_tree.focus()
        if selected_item:
            item_values = stock_tree.item(selected_item, "values")
            if item_values:
                stock_code = item_values[0]
                print(f"主窗口选中了股票: {stock_code}")
                
                # 呼叫副視窗的 refresh_data 函數
                if details_window and details_window.winfo_exists():
                    details_window.refresh_data(stock_code)

    # 綁定 Treeview 選擇事件
    stock_tree.bind("<<TreeviewSelect>>", on_table_select)
    
    root.mainloop()

if __name__ == "__main__":
    main()
