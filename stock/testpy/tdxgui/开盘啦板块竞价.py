#开盘啦板块竞价
import ctypes
from ctypes import wintypes
import requests
import tkinter as tk
from tkinter import messagebox, ttk
import threading
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

# 获取当前日期
current_date = datetime.now().strftime('%Y-%m-%d')
current_filter = 8000000


def load_block_data():
    try:
        is_history = current_date != datetime.now().strftime('%Y-%m-%d')
        if is_history:
            url = f'https://apphis.longhuvip.com/w1/api/index.php?Index=0&Order=1&PhoneOSNew=2&Token=3463abf8cad359085e58d02b44189e4d&Type=1&UserID=2183031&VerSion=5.13.0.9&a=GetBKJJ&apiv=w35&c=StockBidYiDong&st=20&Day={current_date.replace("-", "")}'
        else:
            url = 'https://apphq.longhuvip.com/w1/api/index.php?Index=0&Order=1&PhoneOSNew=2&Token=3463abf8cad359085e58d02b44189e4d&Type=1&UserID=2183031&VerSion=5.13.0.9&a=GetBKJJ&apiv=w35&c=StockBidYiDong&st=20'

        response = requests.get(url)
        if is_history:
            data = response.json()
        else:
            data = response.json()

        # 过滤数据
        filtered_data = [item for item in data['List'] if float(item[2]) > 5 and float(item[3]) > 1e8]
        block_df = [(item[0], item[1], item[2], item[3], item[4]) for item in filtered_data]
        return block_df
    except Exception as e:
        print(f'加载板块数据失败: {e}')
        return []


def load_stock_data(block_code):
    try:
        is_history = current_date != datetime.now().strftime('%Y-%m-%d')
        if is_history:
            url = f'https://apphis.longhuvip.com/w1/api/index.php?Index=0&IsLB=0&IsZT=0&Isst=1&Order=1&PhoneOSNew=2&Token=3463abf8cad359085e58d02b44189e4d&Type=1&UserID=2183031&VerSion=5.13.0.9&a=GetBKJJBL&apiv=w35&c=StockBidYiDong&st=60&filter=1&StockID={block_code}&Day={current_date.replace("-", "")}'
        else:
            url = f'https://apphq.longhuvip.com/w1/api/index.php?Index=0&IsLB=0&IsZT=0&Isst=1&Order=1&PhoneOSNew=2&Token=3463abf8cad359085e58d02b44189e4d&Type=1&UserID=2183031&VerSion=5.13.0.9&a=GetBKJJBL&apiv=w35&c=StockBidYiDong&st=60&filter=1&StockID={block_code}'

        response = requests.get(url)
        if is_history:
            data = response.json()
        else:
            data = response.json()

        # 过滤数据
        filtered_data = [item for item in data['List'] if float(item[5]) >= current_filter and float(item[9]) < 120e8]
        stock_df = [(item[0], item[1], item[2], item[5], item[7], item[6], item[3], item[9], item[10]) for item in filtered_data]
        return stock_df
    except Exception as e:
        print(f'加载股票数据失败: {e}')
        return []


def populate_listbox():
    block_data = load_block_data()
    allitem=list(block_listbox.get(0, tk.END))
    for item in block_data:
        if item[1] not in allitem:
            block_listbox.insert(tk.END, item[1])
    print(f'刷新列表完毕:{allitem}')

def populate_table(event):
    selected_index = block_listbox.curselection()
    if selected_index:
        block_data = load_block_data()
        selected_block = block_data[selected_index[0]]
        block_code = selected_block[0]
        stock_data = load_stock_data(block_code)

        # 清空表格
        for i in stock_tree.get_children():
            stock_tree.delete(i)

        # 填充表格
        for item in stock_data:
            stock_tree.insert('', tk.END, values=item)


def find_tdx_window():
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
        status = f"已找到通达信窗口，句柄: {tdx_window_handle}"
    else:
        status = "未找到通达信窗口，请确保通达信已打开"
    root.title(f"开盘啦竞价板块观察1.0 + 通达信联动 - {status}")


def generate_stock_code(stock_code):
    """根据股票代码的第一位数字生成对应的代码"""
    if not stock_code:
        return None

    first_char = stock_code[0]

    if first_char in ['6','5']:
        return f"7{stock_code}"

    elif first_char in ['0','3','1']:
        
        return f"6{stock_code}"
    else:
        
        return f"4{stock_code}"


def send_to_tdx(stock_code):
    """发送股票代码到通达信"""
    if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
        messagebox.showerror("错误", "请输入有效的6位股票代码")
        return

    # 生成股票代码
    generated_code = generate_stock_code(stock_code)

    # 更新状态
    root.title(f"开盘啦竞价板块观察1.0 + 通达信联动 - 正在发送...")

    # 在新线程中执行发送操作，避免UI卡顿
    threading.Thread(target=_send_to_tdx_thread, args=(stock_code, generated_code)).start()


def _send_to_tdx_thread(stock_code, generated_code,retry=True):
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
            status = PostMessageW(tdx_window_handle, UWM_STOCK, message_code, 2)
            if status:
                print("Message posted successfully.")
            else:
                # PostMessageW returns 0 on failure.
                print("Failed to post message.")
                if retry:
                    find_tdx_window()
                    _send_to_tdx_thread(stock_code, generated_code,retry=False)

            # 更新状态
            status = "发送成功"
        else:
            status = "未找到通达信窗口，请确保通达信已打开"
            if retry:
                find_tdx_window()
                _send_to_tdx_thread(stock_code, generated_code,retry=False)

    except Exception as e:
        status = f"发送失败: {str(e)}"

    # 在主线程中更新UI
    root.after(0, _update_ui_after_send, status)


def _update_ui_after_send(status):
    """在发送操作完成后更新UI"""
    # 更新状态
    root.title(f"开盘啦竞价板块观察1.0 + 通达信联动 - {status}")


# def on_table_select(event):
#     """表格行选中事件处理函数"""
#     selected_item = stock_tree.selection()
#     if selected_item:
#         values = stock_tree.item(selected_item, "values")
#         stock_code = values[0]
#         send_to_tdx(stock_code)
def add_refresh_button(root, refresh_command):
    """
    添加一個刷新按鈕到主窗口頂部，並將其與 refresh_command 綁定。
    """
    # 創建一個新的 Frame 來容納按鈕
    button_frame = tk.Frame(root)
    button_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
    
    refresh_btn = tk.Button(button_frame, text="刷新数据", command=refresh_command,
                            font=('Microsoft YaHei', 9), padx=10, pady=2)
    refresh_btn.pack(side=tk.LEFT, padx=5)

def on_table_select(event):
    """Handles table selection and prints the selected item values."""
    # selected_item = stock_tree.selection()[0]
    selected_item = stock_tree.selection()
    values = stock_tree.item(selected_item, "values")
    print("Selected Item Values:", values)
    selected_item = stock_tree.selection()
    if selected_item:
        # values = stock_tree.item(selected_item, "values")
        stock_code = values[0]
        send_to_tdx(stock_code)


def sort_treeview(tree, col, reverse):
    """Sorts the table by the specified column."""

    items = [(stock_tree.set(item, col), item) for item in stock_tree.get_children("")]
    # Convert numerical columns to float for proper sorting
    if col in ('现价', '竞价金额', '竞价净额', '竞价涨幅', '实时涨幅', '流通市值'):
        try:
            items = [(float(val), item) for val, item in items]
        except ValueError:
            # Handle cases where value cannot be converted to float (e.g. empty)
            pass
    # items.sort()
    items.sort(key=lambda t: t[0], reverse=reverse)
    
    for index, (val, item) in enumerate(items):
        stock_tree.move(item, "", index)

    # # Reverse the sort direction for the next click on this column
    stock_tree.heading(col, command=lambda: sort_treeview(stock_tree, col, not reverse))

# def sort_column(col):
#     """Sorts the table by the specified column."""
#     items = [(stock_tree.set(item, col), item) for item in stock_tree.get_children("")]
#     # Convert numerical columns to float for proper sorting
#     if col in ('现价', '竞价金额', '竞价净额', '竞价涨幅', '实时涨幅', '流通市值'):
#         try:
#             items = [(float(val), item) for val, item in items]
#         except ValueError:
#             # Handle cases where value cannot be converted to float (e.g. empty)
#             pass
#     # items.sort()
#     items.sort(key=lambda t: t[0], reverse=reverse)

#     for index, (val, item) in enumerate(items):
#         stock_tree.move(item, "", index)

# 创建主窗口
root = tk.Tk()
root.title("开盘啦竞价板块观察1.0 + 通达信联动")

# 添加刷新按钮
add_refresh_button(root, populate_listbox)

# 创建列表框
block_listbox = tk.Listbox(root, width=12)
block_listbox.pack(side=tk.LEFT, fill=tk.Y)
block_listbox.bind("<<ListboxSelect>>", populate_table)



# 创建表格
columns = ('代码', '简称', '现价', '竞价金额', '竞价净额', '竞价涨幅', '实时涨幅', '流通市值', '板块')
stock_tree = ttk.Treeview(root, columns=columns, show='headings')
for col in columns:
    # stock_tree.heading(col, text=col)
    # stock_tree.heading(col, text=col, command=lambda c=col: sort_column(c)) #Bind to the column
    stock_tree.heading(col, text=col, command=lambda c=col: sort_treeview(stock_tree, c, False))
    # 设置列宽度为100，数据居中对齐
    stock_tree.column(col, width=88, anchor=tk.CENTER)
stock_tree.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
stock_tree.bind("<<TreeviewSelect>>", on_table_select)
# sort_treeview(stock_tree, '实时涨幅', False)

# 填充列表框
populate_listbox()

# This will automatically sort by 'name' in ascending order on startup.

# 添加键盘快捷键
root.bind("<F5>", lambda event: populate_listbox())
root.bind("<Control-r>", lambda event: populate_listbox())

# 查找通达信窗口
find_tdx_window()

# 运行主循环
root.mainloop()

# for col in columns:
#     stock_tree.heading(col, text=col, command=lambda c=col: sort_column(c)) #Bind to the column
#     stock_tree.column(col, width=88, anchor=tk.CENTER)
# stock_tree.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
# stock_tree.bind("<<TreeviewSelect>>", on_table_select)


'''
# Check if a valid handle was found.
 
import ctypes
import time

# Load the user32.dll library
user32 = ctypes.windll.user32

# Define required types for clarity
HWND = ctypes.wintypes.HWND
UINT = ctypes.wintypes.UINT
WPARAM = ctypes.wintypes.WPARAM
LPARAM = ctypes.wintypes.LPARAM

# Define the message and window class name
UWM_STOCK = 0x0400 + 100 # Example private message, replace with your actual message ID
TDX_WINDOW_CLASS = "TdxW_MainFrame_Class" # Replace with the correct class name

def send_message_to_tdx(message_id, w_param=0, l_param=0):
    """
    Finds the TDX window and sends a message to it if it is open.
    """
    # Find the window handle by its class name.
    # Passing 0 for the window title finds the first window with the class.
    tdx_window_handle = user32.FindWindowW(TDX_WINDOW_CLASS, None)

    # Check if a valid handle was found.
    if tdx_window_handle:
        # The window was found. Now, use IsWindow() to verify it's still open.
        if user32.IsWindow(tdx_window_handle):
            print(f"Found TDX window with handle: {tdx_window_handle}")
            
            # Post the message to the window.
            result = user32.PostMessageW(
                tdx_window_handle,
                message_id,
                WPARAM(w_param),
                LPARAM(l_param)
            )
            
            if result:
                print("Message posted successfully.")
            else:
                # PostMessageW returns 0 on failure.
                print("Failed to post message.")
        else:
            print("Handle is no longer valid. The window might have closed.")
    else:
        print("Could not find the TDX window.")

if __name__ == "__main__":
    # Example usage: send the UWM_STOCK message.
    send_message_to_tdx(UWM_STOCK)
    
    # You can also use a timer to run this periodically.
    # For a simple example, a loop with a delay works.
    print("\nStarting a loop to check for the window...")
    for _ in range(3):
        time.sleep(5)
        send_message_to_tdx(UWM_STOCK)

'''