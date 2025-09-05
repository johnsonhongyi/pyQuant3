import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import messagebox, ttk
import threading
import time
from datetime import datetime

# 定义所需的Windows API函数和类型
user32 = ctypes.windll.user32

# 定义回调函数类型
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_void_p)

# 定义所需的Windows API函数
EnumWindows = user32.EnumWindows
EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_void_p]
EnumWindows.restype = ctypes.c_bool

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int

GetClassNameW = user32.GetClassNameW
GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetClassNameW.restype = ctypes.c_int

PostMessageW = user32.PostMessageW
PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
PostMessageW.restype = ctypes.c_int

RegisterWindowMessageW = user32.RegisterWindowMessageW
RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
RegisterWindowMessageW.restype = ctypes.c_uint

# 全局变量，用于存储通达信窗口句柄
tdx_window_handle = 0

class HistoryRecord:
    def __init__(self, stock_code, generated_code, success, message):
        self.stock_code = stock_code
        self.generated_code = generated_code
        self.success = success
        self.message = message
        self.time = datetime.now().strftime("%H:%M:%S")

class TdxStockSenderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("通达信股票代码发送工具")
        self.root.geometry("500x500")
        self.root.resizable(False, False)
        self.root.configure(bg="#f5f7fa")
        
        # 设置中文字体
        self.style = ttk.Style()
        self.style.configure("TLabel", font=("Microsoft YaHei", 10))
        self.style.configure("TButton", font=("Microsoft YaHei", 10))
        self.style.configure("TEntry", font=("Microsoft YaHei", 10))
        
        # 历史记录
        self.history_records = []
        
        # 创建UI
        self.create_widgets()
        
        # 查找通达信窗口
        self.find_tdx_window()
    
    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 股票代码输入
        ttk.Label(main_frame, text="股票代码:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.stock_code_var = tk.StringVar()
        stock_code_entry = ttk.Entry(main_frame, textvariable=self.stock_code_var, width=20, font=("Microsoft YaHei", 12))
        stock_code_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        stock_code_entry.bind("<KeyRelease>", self.update_generated_code)
        
        ttk.Label(main_frame, text="生成代码:").grid(row=0, column=2, sticky=tk.W, pady=5, padx=10)
        self.generated_code_var = tk.StringVar(value="--")
        self.generated_code_label = ttk.Label(main_frame, textvariable=self.generated_code_var, foreground="#165DFF")
        self.generated_code_label.grid(row=0, column=3, sticky=tk.W, pady=5)
        
        # 通达信窗口句柄
        ttk.Label(main_frame, text="通达信窗口句柄:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.tdx_handle_var = tk.StringVar(value="未找到")
        ttk.Label(main_frame, textvariable=self.tdx_handle_var).grid(row=1, column=1, sticky=tk.W, pady=5)
        
        # 状态
        ttk.Label(main_frame, text="状态:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.status_var).grid(row=2, column=1, sticky=tk.W, pady=5)
        
        # 发送按钮
        self.send_button = ttk.Button(main_frame, text="发送到通达信", command=self.send_to_tdx)
        self.send_button.grid(row=3, column=0, columnspan=4, pady=20)
        
        # 历史记录标题
        ttk.Label(main_frame, text="发送历史:", font=("Microsoft YaHei", 10, "bold")).grid(row=4, column=0, sticky=tk.W, pady=10)
        
        # 历史记录列表
        history_frame = ttk.Frame(main_frame)
        history_frame.grid(row=5, column=0, columnspan=4, sticky=tk.NSEW, pady=5)
        
        self.history_tree = ttk.Treeview(history_frame, columns=("time", "stock_code", "generated_code", "status"), show="headings", height=8)
        self.history_tree.column("time", width=80, anchor=tk.CENTER)
        self.history_tree.column("stock_code", width=80, anchor=tk.CENTER)
        self.history_tree.column("generated_code", width=90, anchor=tk.CENTER)
        self.history_tree.column("status", width=200, anchor=tk.W)
        
        self.history_tree.heading("time", text="时间")
        self.history_tree.heading("stock_code", text="股票代码")
        self.history_tree.heading("generated_code", text="生成代码")
        self.history_tree.heading("status", text="状态")
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 底部信息
        ttk.Label(self.root, text="通达信股票代码发送工具 © 2023", foreground="#666").pack(pady=10)
    
    def find_tdx_window(self):
        """查找通达信窗口"""
        global tdx_window_handle
        
        def enum_windows_callback(hwnd, lparam):
            global tdx_window_handle
            
            # 获取窗口标题
            title_buffer = ctypes.create_unicode_buffer(256)
            GetWindowTextW(hwnd, title_buffer, 255)
            window_title = title_buffer.value
            
            # 获取窗口类名
            class_buffer = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, class_buffer, 255)
            window_class = class_buffer.value
            
            # 查找通达信窗口类名
            if "TdxW_MainFrame_Class" in window_class:
                tdx_window_handle = hwnd
                return False  # 找到后停止枚举
            
            return True
        
        # 将Python函数转换为C回调函数
        enum_proc = WNDENUMPROC(enum_windows_callback)
        
        # 重置通达信窗口句柄
        tdx_window_handle = 0
        
        # 枚举所有窗口
        EnumWindows(enum_proc, 0)
        
        if tdx_window_handle != 0:
            self.tdx_handle_var.set(str(tdx_window_handle))
            self.status_var.set("已找到通达信窗口")
        else:
            self.status_var.set("未找到通达信窗口，请确保通达信已打开")
    
    def generate_stock_code(self, stock_code):
        """根据股票代码的第一位数字生成对应的代码"""
        if not stock_code:
            return None
            
        first_char = stock_code[0]
        
        if first_char == '6':
            return f"7{stock_code}"
        else:
            return f"6{stock_code}"
    
    def update_generated_code(self, event=None):
        """更新生成的代码显示"""
        stock_code = self.stock_code_var.get().strip()
        if len(stock_code) == 6 and stock_code.isdigit():
            generated_code = self.generate_stock_code(stock_code)
            self.generated_code_var.set(generated_code)
        else:
            self.generated_code_var.set("--")
    
    def send_to_tdx(self):
        """发送股票代码到通达信"""
        stock_code = self.stock_code_var.get().strip()
        
        if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
            messagebox.showerror("错误", "请输入有效的6位股票代码")
            return
        
        # 生成股票代码
        generated_code = self.generate_stock_code(stock_code)
        
        # 更新状态
        self.status_var.set("正在发送...")
        self.send_button.config(state=tk.DISABLED)
        
        # 在新线程中执行发送操作，避免UI卡顿
        threading.Thread(target=self._send_to_tdx_thread, args=(stock_code, generated_code)).start()
    
    def _send_to_tdx_thread(self, stock_code, generated_code):
        """在线程中执行发送操作"""
        global tdx_window_handle
        
        try:
            # 获取通达信注册消息代码
            UWM_STOCK = RegisterWindowMessageW("Stock")
            
            # 发送消息
            if tdx_window_handle != 0:
                # 尝试将生成的代码转换为整数
                try:
                    message_code = int(generated_code)
                except ValueError:
                    message_code = 0
                
                # 发送消息
                PostMessageW(tdx_window_handle, UWM_STOCK, message_code, 2)
                
                # 更新状态
                status = "发送成功"
                success = True
            else:
                status = "未找到通达信窗口，请确保通达信已打开"
                success = False
                
        except Exception as e:
            status = f"发送失败: {str(e)}"
            success = False
        
        # 在主线程中更新UI
        self.root.after(0, self._update_ui_after_send, stock_code, generated_code, success, status)
    
    def _update_ui_after_send(self, stock_code, generated_code, success, status):
        """在发送操作完成后更新UI"""
        # 更新状态
        self.status_var.set(status)
        self.send_button.config(state=tk.NORMAL)
        
        # 添加到历史记录
        record = HistoryRecord(stock_code, generated_code, success, status)
        self.history_records.insert(0, record)
        
        # 限制历史记录数量
        if len(self.history_records) > 10:
            self.history_records.pop()
        
        # 更新历史记录显示
        self.update_history_display()
        
        # 成功时闪烁提示
        if success:
            self.generated_code_label.configure(foreground="#36D399")
            self.root.after(1000, lambda: self.generated_code_label.configure(foreground="#165DFF"))
    
    def update_history_display(self):
        """更新历史记录显示"""
        # 清空现有记录
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        # 添加新记录
        for record in self.history_records:
            status_text = "成功" if record.success else "失败"
            status_color = "#36D399" if record.success else "#F87272"
            
            self.history_tree.insert("", tk.END, values=(
                record.time,
                record.stock_code,
                record.generated_code,
                record.message
            ))

if __name__ == "__main__":
    root = tk.Tk()
    app = TdxStockSenderApp(root)
    root.mainloop()    
