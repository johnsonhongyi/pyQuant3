import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import random
import time
import concurrent.futures

# ---- Dummy Data and Functions (replace with your actual data source) -----
def get_stock_data_from_source(stock_code):
    """Fetch live stock data from the real source."""
    time.sleep(1) # Simulate network delay
    # Replace this with your actual stock data fetching logic
    price = random.uniform(10, 100)
    change = random.uniform(-5, 5)
    return pd.Series({"Price": price, "Change": change})

def generate_stock_data():
    """Generates random stock data."""
    stocks = [
        ("600000", "Stock A"),
        ("600001", "Stock B"),
        ("000001", "Stock C"),
        ("000002", "Stock D"),
    ]
    data = []
    for code, name in stocks:
        price = random.uniform(10, 100)
        change = random.uniform(-5, 5)
        data.append((code, name, price, change))
    return data

# ---- Monitoring Window Class -----
class StockMonitorWindow(tk.Toplevel):
    def __init__(self, parent, stock_code):
        super().__init__(parent)
        self.stock_code = stock_code[0]
        self.title(f"Monitoring: {self.stock_code}")
        self.geometry("300x150")

        self.label = ttk.Label(self, text="Fetching data...", anchor=tk.CENTER)
        self.label.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        # Create a thread pool for background tasks
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # Start refreshing the stock data
        self.refresh_stock_data()
        
        # When closing window, shut down thread pool and destroy window
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """Handle window close event."""
        self.executor.shutdown(wait=False) # Safely shut down the executor
        self.destroy()

    def refresh_stock_data(self):
        """Asynchronously fetches and updates stock data."""
        future = self.executor.submit(get_stock_data_from_source, self.stock_code)
        future.add_done_callback(self.update_label)

    def update_label(self, future):
        """Callback to update the label with fetched data."""
        try:
            data = future.result()
            if data is not None:
                self.label.config(text=f"Price: {data['Price']:.2f}, Change: {data['Change']:.2f}")
            else:
                self.label.config(text="Error fetching data.")
        except Exception as e:
            self.label.config(text=f"Error: {e}")
        
        # Schedule the next refresh only if the window has not been destroyed
        if self.winfo_exists():
            self.after(5000, self.refresh_stock_data) # Refresh every 5 seconds

# ----- Main Application -----
class StockApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stock Monitor App")
        self.geometry("600x400")

        columns = ("Code", "Name", "Price", "Change")
        self.stock_tree = ttk.Treeview(self, columns=columns, show="headings")
        for col in columns:
            self.stock_tree.heading(col, text=col, anchor=tk.CENTER)
            self.stock_tree.column(col, width=120, anchor=tk.CENTER)
        self.stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.stock_tree.bind("<Button-3>", self.show_context_menu)
        
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Add to Monitor", command=self.add_selected_stock)

        self.load_stock_data()
        
        self.monitor_windows = {}

    def load_stock_data(self):
        """Loads stock data into the Treeview."""
        data = generate_stock_data()
        for stock_code, name, price, change in data:
            self.stock_tree.insert("", "end", values=(stock_code, name, f"{price:.2f}", f"{change:.2f}"))

    def show_context_menu(self, event):
        """Shows the context menu on right-click."""
        item = self.stock_tree.identify_row(event.y)
        if item:
            self.stock_tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def add_selected_stock(self):
        """Adds the selected stock to a monitoring window."""
        try:
            item = self.stock_tree.selection()
            if not item:
                messagebox.showwarning("Warning", "Please select a stock code.")
                return

            stock_info = self.stock_tree.item(item, "values")
            stock_code = stock_info[0]
            
            # Prevent opening same monitor window
            if stock_code in self.monitor_windows:
                messagebox.showwarning("Warning", f"A monitor for {stock_code} is already open.")
                return

            monitor_win = StockMonitorWindow(self, stock_info)
            self.monitor_windows[stock_code] = monitor_win
            
            # Capture the close event of the monitoring window.
            monitor_win.protocol("WM_DELETE_WINDOW", lambda: self.remove_monitor_window(stock_code, monitor_win))

        except IndexError:
            messagebox.showwarning("Warning", "Please select a stock code.")
    
    def remove_monitor_window(self, stock_code, window_instance):
       """Removes a monitoring window from the dict when it's closed."""
       if stock_code in self.monitor_windows:
           del self.monitor_windows[stock_code]
       window_instance.destroy()


if __name__ == "__main__":
    app = StockApp()
    app.mainloop()



'''
import concurrent.futures
import pandas as pd
import tkinter as tk
from tkinter import messagebox

# 创建一个全局线程池
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

def heavy_data_processing(data):
    """
    一个模拟耗时数据处理的函数，返回处理结果。
    """
    print("开始处理数据...")
    # 模拟耗时操作
    import time
    time.sleep(3)
    
    # 假设这里进行了一些数据处理，并返回一个结果
    processed_data = data * 2
    return processed_data

def on_processing_complete(future):
    """
    处理任务完成后的回调函数。
    这个函数会在主线程中被调用，可以安全地更新GUI。
    """
    try:
        # 获取任务的返回值
        result = future.result()
        messagebox.showinfo("处理完成", f"数据处理已完成，结果: {result}")
    except Exception as e:
        messagebox.showerror("错误", f"处理任务时出错: {e}")

def button_click():
    """
    按钮点击事件处理函数，启动异步任务。
    """
    sample_data = pd.DataFrame({'value': [1, 2, 3]})
    
    # 使用 executor.submit() 提交任务，它会立即返回一个 Future 对象
    future = executor.submit(heavy_data_processing, sample_data)
    print("已提交后台处理任务...")
    
    # 添加一个回调函数，当任务完成后，它会被自动调用
    future.add_done_callback(on_processing_complete)

# --- Tkinter GUI示例 ---
if __name__ == "__main__":
    root = tk.Tk()
    root.title("获取异步返回数据示例")
    
    tk.Button(root, text="启动耗时任务", command=button_click).pack(pady=20, padx=20)
    
    # 确保在程序退出时关闭线程池
    root.protocol("WM_DELETE_WINDOW", lambda: [executor.shutdown(wait=False), root.destroy()])
    
    root.mainloop()
'''

# import concurrent.futures
# import pandas as pd
# import tkinter as tk
# from tkinter import messagebox

# # 创建一个全局线程池，max_workers可以根据你的需求调整
# executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# def save_dataframe_to_csv_task(df, filepath):
#     """在线程池中执行的保存任务"""
#     try:
#         df.to_csv(filepath, index=False)
#         return True, f"文件已保存: {filepath}"
#     except Exception as e:
#         return False, f"保存文件时出错: {e}"

# def start_async_save_with_executor(df, filepath):
#     """使用线程池启动异步保存任务"""
#     # 提交任务到线程池
#     future = executor.submit(save_dataframe_to_csv_task, df, filepath)
#     print("已提交后台保存任务...")
    
#     # 可以在任务完成后处理结果
#     future.add_done_callback(on_save_completion)

# def on_save_completion(future):
#     """任务完成后的回调函数，在主线程中运行"""
#     success, message = future.result()
#     if success:
#         messagebox.showinfo("成功", message)
#     else:
#         messagebox.showerror("错误", message)

# # --- Tkinter GUI示例 ---
# def button_click(loaded_df):
#     filepath = "async_saved_data_executor.csv"
#     start_async_save_with_executor(loaded_df, filepath)

# if __name__ == "__main__":
#     # 创建一个示例DataFrame
#     sample_data = {'col1': [1, 2, 3], 'col2': ['A', 'B', 'C']}
#     loaded_df = pd.DataFrame(sample_data)

#     root = tk.Tk()
#     root.title("异步保存（线程池）示例")
    
#     tk.Button(root, text="异步保存DataFrame", command=lambda: button_click(loaded_df)).pack(pady=20, padx=20)
    
#     # 确保在程序退出时关闭线程池
#     root.protocol("WM_DELETE_WINDOW", lambda: [executor.shutdown(wait=False), root.destroy()])
    
#     root.mainloop()