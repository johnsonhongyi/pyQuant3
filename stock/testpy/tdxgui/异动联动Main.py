import requests
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox
import time
import json
from datetime import datetime, timedelta
from ctypes import wintypes
import ctypes
from tkcalendar import DateEntry
import os # 導入 os 模組

import psutil
import win32gui
import win32process
import win32api
import threading

import concurrent.futures
import pyperclip
# 全局变量
# root = None
# stock_tree = None
# context_menu = None
monitor_windows = {}  # 存储监控窗口实例
MONITOR_LIST_FILE = "monitor_list.json"
root = None
stock_tree = None
context_menu = None
code_entry = None  # 添加全局 Entry 变量
# sub_window = None  # 添加全局 to pop_code_entry  变量
# sub_monitor_tree = None # subWindow tree
# sub_item_id = None # sub_item_id
realdatadf = pd.DataFrame()  # 存储股票异动数据的DataFrame
last_updated_time = None # 记录上次更新时间
realdatadf_lock = threading.Lock() # 为 loaddf 创建一个全局锁
update_interval_minutes = 10
start_init = 0
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
GetWindowText = ctypes.windll.user32.GetWindowTextW
GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible


def get_pids(pname):
    # print(pname)
    pids = []
    for proc in psutil.process_iter():
        if pname in proc.name():
            pids.append(proc.pid)
    # print(pids)
    return pids


def get_handles(pid):
    def callback(hwnd, handles):
        if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)

            if found_pid == pid:
                handles.append(hwnd)
            return True

    handles = []
    win32gui.EnumWindows(callback, handles)
    return handles


def get_handle(pname):
    pids = get_pids(pname)
    for pid in pids:
        handles = get_handles(pid)
        # print(handles)
        for hwnd in handles:
            if IsWindowVisible(hwnd):
                return hwnd


FAGE_READWRITE = 0x04  # 偏移地址：0x04的意思就是：在空间上偏移4个内存单元
PROCESS_ALL_ACCESS = 0x001F0FFF
VIRTUAL_MEN = (0x1000 | 0x2000)

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32



def ths_prc_hwnd():
    pl = psutil.pids()
    for pid in pl:
        try:
            # 进程id 获取进程名 转化为小写
            if psutil.Process(pid).name().lower() == 'hexin.exe':
                # isinstance() 函数来判断一个对象是否是一个已知的类型 pid 是 int类型
                if isinstance(pid, int):
                    # 打开一个已存在的进程对象hexin.exe，并返回进程的句柄
                    ths_process_hwnd = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, int(pid))  # 申请内存所在的进程句柄
                    return ths_process_hwnd
        except psutil.NoSuchProcess:  # Catch the error caused by the process no longer existing
            print(f"NoSuchProcess with pid: {pid}")
            # pass  # Ignore it
        else:
            pass


def bytes_16(dec_num, code):
    # num=ord(char)   # 将ASCII字符转换为对应的整数
    # ord('?') -> 63  chr(63) -> ? bytes_16(63, code) ->b'?833171'
    # char=chr(num) # 将整数转换为对应的ASCII字符
    ascii_char = chr(dec_num)  # 将整数转换为对应的ASCII字符
    codex = ascii_char + str(code)
    # 将Python字符串转换为bytes类型
    bytes_codex = codex.encode('ascii', 'ignore')
    return bytes_codex


def ths_convert_code(code):
    '''
    代码转换
    :param code:
    :return:
    '''
    # 上海，深圳股票判断;

    if str(code)[0] == '6':
        # 将16进制数转换为整数
        dec_num = int('11', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 11开头的可转债
    elif str(code).startswith('11'):
        # 将16进制数转换为整数
        dec_num = int('13', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 12开头的可转债
    elif str(code).startswith('12'):
        # 将16进制数转换为整数
        dec_num = int('23', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 12开头的可转债
    elif str(code).startswith('15'):
        # 将16进制数转换为整数
        dec_num = int('24', 16)
        bytes_codex = bytes_16(dec_num, code)

    #     # 12开头的可转债
    # elif str(code).startswith('8') or str(code).startswith('92') or str(code).startswith('43'):
    #     # 将16进制数转换为整数
    #     # ord('?') -> 63  chr(63) -> ? bytes_16(63, code) ->b'?833171'
    #     # char=chr(num) # 将整数转换为对应的ASCII字符
    #     # (base16 - > int) ('%x' % 63) -> '3f'
    #     dec_num = int('97', 16)
    #     bytes_codex = bytes_16(dec_num, code)
    else:
        # 将16进制数转换为整数
        dec_num = int('21', 16)
        bytes_codex = bytes_16(dec_num, code)

    return bytes_codex

def send_code_clipboard(stock_code):
    pyperclip.copy(stock_code)
    print(f"Stock code {stock_code} copied to clipboard!")
    return True

def send_code_message(code,retry=True):
    global ths_window_handle
    global ths_process_hwnd
    # # 同花顺进程句柄
    # ths_process_hwnd = ths_prc_hwnd()
    # # 用kerne132.VirtualAllocEx在目标进程开辟内存空间(用于存放数据)
    # 在指定进程的虚拟地址空间中保留、提交或更改内存区域的状态。 函数将它分配的内存初始化为零。
    if ths_process_hwnd != 0 and ths_window_handle != 0:
        argv_address = kernel32.VirtualAllocEx(ths_process_hwnd, 0, 8, VIRTUAL_MEN, FAGE_READWRITE)
        bytes_str = ths_convert_code(code)
        # 用kerne132.WriteProcessMemory在目标进程内存空间写入数据
        kernel32.WriteProcessMemory(ths_process_hwnd, argv_address, bytes_str, 7, None)
    # # 同花顺窗口句柄
    # ths_handle = get_handle(exe)
        result = win32api.SendMessage(ths_window_handle, int(1168), 0, argv_address)
    else:
        if retry:
            find_ths_window()
            send_code_message(code,retry=False)
            print(f'ths_window_handle ths_process_hwnd not find')

    return result
# 导入通达信联动代码中的相关类和函数
# from 通达信联动代码 import TdxStockSenderApp, HistoryRecord
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
ths_window_handle = 0
ths_process_hwnd = 0
# 這個變數將用於存放載入的DataFrame
loaded_df = None
date_write_is_processed = False


def get_now_time_int():
    now_t = datetime.now().strftime("%H%M")
    return int(now_t)


# def get_day_is_trade_day(dt=None):
#     #2025
#     sep='-'
#     if dt is None:
#         TODAY = datetime.date.today()
#         fstr = "%Y" + sep + "%m" + sep + "%d"
#         dt = TODAY.strftime(fstr)
#     else:
#         if isinstance(dt, datetime.date):
#             dt = dt.strftime('%Y-%m-%d')
#     is_trade_date = a_trade_calendar.is_trade_date(dt)
#     return(is_trade_date)

def get_day_is_trade_day():
    today = datetime.today().date()
    day_n = int(today.strftime("%w"))

    if day_n > 0 and day_n < 6:
        return True
    else:
        return False

def get_work_time(now_t = None):
    # return True
    # now_t = str(get_now_time()).replace(':', '')
    # now_t = int(now_t)
    if not get_day_is_trade_day():
        return False
    if now_t == None:
        now_t = get_now_time_int()
    if (now_t > 1131 and now_t < 1300) or now_t < 915 or now_t > 1502:
        return False
        # return True
    else:
        # if now_t > 1300 and now_t <1302:
            # sleep(random.randint(5, 120))
        return True



def find_ths_window(exe='hexin.exe'):
    global ths_window_handle
    global ths_process_hwnd

    # 同花顺进程句柄
    ths_process_hwnd = ths_prc_hwnd()
    # 用kerne132.VirtualAllocEx在目标进程开辟内存空间(用于存放数据)
    # 在指定进程的虚拟地址空间中保留、提交或更改内存区域的状态。 函数将它分配的内存初始化为零。

    # argv_address = kernel32.VirtualAllocEx(ths_process_hwnd, 0, 8, VIRTUAL_MEN, FAGE_READWRITE)
    # bytes_str = ths_convert_code(code)
    # # 用kerne132.WriteProcessMemory在目标进程内存空间写入数据
    # kernel32.WriteProcessMemory(ths_process_hwnd, argv_address, bytes_str, 7, None)

    # 同花顺窗口句柄
    ths_window_handle = get_handle(exe)

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
    root.title(f"股票异动数据监控 + 通达信联动 - {status}")


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

# if str(message_type) == 'stock':
#         if str(stock_code)[0] in ['0','3','1']:
#             codex = '6' + str(stock_code)
#         elif str(stock_code)[0] in ['6','5']:
#             codex = '7' + str(stock_code)
#         # elif str(stock_code)[0] == '9':
#         #     codex = '2' + str(stock_code)
#         else:
#             codex = '4' + str(stock_code)
#     else:
#         codex = int(stock_code)

def send_to_tdx(stock_code):
    """发送股票代码到通达信"""
    if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
        messagebox.showerror("错误", "请输入有效的6位股票代码")
        return

    # 生成股票代码
    generated_code = generate_stock_code(stock_code)

    # 更新状态
    root.title(f"股票异动数据监控 + 通达信联动 - 正在发送...")

    # 在新线程中执行发送操作，避免UI卡顿
    threading.Thread(target=_send_to_tdx_thread, args=(stock_code, generated_code)).start()


def _send_to_tdx_thread(stock_code, generated_code,retry=True):
    """在线程中执行发送操作"""
    global tdx_window_handle
    tdx_state = tdx_var.get()
    ths_state = ths_var.get()
    dfcf_state = dfcf_var.get()
    status = '成功'
    try:
        if tdx_state:

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
                    print("TDX Message posted successfully.")
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

        if ths_state:
            status = send_code_message(stock_code)
            print(f"THS send Message posted successfully.")
        if dfcf_state:
            status = send_code_clipboard(stock_code)
            print(f"DFCF Paste successfully.")

    except Exception as e:
        status = f"发送失败: {str(e)}"

    # 在主线程中更新UI
    root.after(0, _update_ui_after_send, status)


def _update_ui_after_send(status):
    """在发送操作完成后更新UI"""
    # 更新状态
    root.title(f"股票异动数据监控 + 通达信联动 - {status}")

#init map
symbol_map = {
    "火箭发射": "8201",
    "快速反弹": "8202",
    "大笔买入": "8193",
    "封涨停板": "4",
    "打开跌停板": "32",
    "有大买盘": "64",
    "竞价上涨": "8207",
    "高开5日线": "8209",
    "向上缺口": "8211",
    "60日新高": "8213",
    "60日大幅上涨": "8215",
    "加速下跌": "8204",
    "高台跳水": "8203",
    "大笔卖出": "8194",
    "封跌停板": "8",
    "打开涨停板": "16",
    "有大卖盘": "128",
    "竞价下跌": "8208",
    "低开5日线": "8210",
    "向下缺口": "8212",
    "60日新低": "8214",
    "60日大幅下跌": "8216",
}

#获取全部数据
def get_dfcf_all_data():

    # if not (get_day_is_trade_day() and get_now_time_int() > 1505):
    url = "https://push2ex.eastmoney.com/getAllStockChanges?"

    reversed_symbol_map = {v: k for k, v in symbol_map.items()}

    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'pageindex': '0',
        'pagesize': '50000',
        'dpt': 'wzchanges',
        '_': int(time.time() * 1000)
    }

    # if realdatadf is not None:
    #     df = realdatadf
    #     loaded_df_deduplicated = df.drop_duplicates(subset=['板块'])
    #     if len(loaded_df_deduplicated) != len(symbol_map.keys()):
    #         df = get_stock_changes_time()
    # else:

    df = pd.DataFrame()

    for sel_type in symbol_map:

        # if sel_type == selected_type:
        #     continue
        # elif sel_type in loaded_df_deduplicated['板块']:
        #     continue
        # else:
        params['type'] = symbol_map[sel_type]
    
        try:
            # if  not date_write_is_processed or (get_now_time_int() <= 1505 and loaded_df is None):

            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data_json = response.json()
            
            if not data_json.get('data') or not data_json['data'].get('allstock'):
                messagebox.showinfo("提示", "未获取到数据")
                return pd.DataFrame()
            
            temp_df = pd.DataFrame(data_json["data"]["allstock"])
            if 'tm' not in temp_df.columns:
                return pd.DataFrame()
            
            temp_df["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors='coerce').dt.time
            temp_df.columns = ["时间", "代码", "_", "名称", "板块", "相关信息"]
            temp_df = temp_df[["时间", "代码", "名称", "板块", "相关信息"]]
            
            temp_df["板块"] = temp_df["板块"].astype(str).map(
                lambda x: reversed_symbol_map.get(x, f"未知类型({x})")
            )

            temp_df = temp_df.sort_values(by="时间", ascending=False)
            df = pd.concat([df, temp_df], axis=0)

        except requests.exceptions.Timeout:
            messagebox.showerror("错误", "请求超时")
            return pd.DataFrame()
        except requests.exceptions.RequestException as e:
            messagebox.showerror("错误", f"网络错误: {str(e)}")
            return pd.DataFrame()
        except Exception as e:
            messagebox.showerror("错误", f"数据处理错误: {str(e)}")
            return pd.DataFrame()

    return df


#获取全部数据
# def get_dfcf_all_data_old(df,selected_type):

#     # if not (get_day_is_trade_day() and get_now_time_int() > 1505):
#     url = "https://push2ex.eastmoney.com/getAllStockChanges?"

#     reversed_symbol_map = {v: k for k, v in symbol_map.items()}

#     params = {
#         'ut': '7eea3edcaed734bea9cbfc24409ed989',
#         'pageindex': '0',
#         'pagesize': '50000',
#         'dpt': 'wzchanges',
#         '_': int(time.time() * 1000)
#     }
    

#     for sel_type in symbol_map:

#         if sel_type == selected_type:
#             continue
#         else:
#             params['type'] = symbol_map[sel_type]
    
#         try:
#             # if  not date_write_is_processed or (get_now_time_int() <= 1505 and loaded_df is None):

#             response = requests.get(url, params=params, timeout=15)
#             response.raise_for_status()
#             data_json = response.json()
            
#             if not data_json.get('data') or not data_json['data'].get('allstock'):
#                 messagebox.showinfo("提示", "未获取到数据")
#                 return pd.DataFrame()
            
#             temp_df = pd.DataFrame(data_json["data"]["allstock"])
#             if 'tm' not in temp_df.columns:
#                 return pd.DataFrame()
            
#             temp_df["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors='coerce').dt.time
#             temp_df.columns = ["时间", "代码", "_", "名称", "板块", "相关信息"]
#             temp_df = temp_df[["时间", "代码", "名称", "板块", "相关信息"]]
            
#             temp_df["板块"] = temp_df["板块"].astype(str).map(
#                 lambda x: reversed_symbol_map.get(x, f"未知类型({x})")
#             )

#             temp_df = temp_df.sort_values(by="时间", ascending=False)
#             df = pd.concat([df, temp_df], axis=0)

#         except requests.exceptions.Timeout:
#             messagebox.showerror("错误", "请求超时")
#             return pd.DataFrame()
#         except requests.exceptions.RequestException as e:
#             messagebox.showerror("错误", f"网络错误: {str(e)}")
#             return pd.DataFrame()
#         except Exception as e:
#             messagebox.showerror("错误", f"数据处理错误: {str(e)}")
#             return pd.DataFrame()

#     return df

def start_async_save(df=None):
    """启动一个新线程来保存DataFrame"""
    # 创建并启动新线程
    save_thread = threading.Thread(target=save_dataframe)
    save_thread.start()
    print("已启动save_dataframe后台保存任务...")


# --- 儲存 DataFrame 的函數 ---
def save_dataframe(df=None):
    """獲取選取的日期，並將 DataFrame 儲存為以該日期命名的檔案。"""
    global date_write_is_processed
    global loaded_df,start_init

    # if df is None:
    #     df = pd.DataFrame()
    # 如果正在處理中，則直接返回，不執行後續邏輯
    # if date_write_is_processed:
    #     loaded_df_deduplicated = df.drop_duplicates(subset=['板块'])
    #     count =len(symbol_map.keys())
    #     if len(loaded_df_deduplicated) == len(symbol_map.keys()):
    #         print(f'loaded_df_deduplicated:{count} is Alldata OK')
    #     else:
    #         if loaded_df is not None:
    #             df = loaded_df
    #     return df
    while not start_init:
        time.sleep(5)
        print('wait init background 完成...')
    print(f'start_init:{start_init} will to save')    
    try:
        # 1. 從 DateEntry 獲取日期物件
        selected_date_obj = date_entry.get_date()
        # 2. 格式化日期為字串
        # 例如: 2025-09-03
        date_str = selected_date_obj.strftime("%Y-%m-%d")
        
        # 3. 建立檔名（這裡儲存為 CSV）
        # selected_type  = type_var.get()
        # filename = f"dfcf_{selected_type}_{date_str}.csv"
        filename = f"dfcf_{date_str}.csv"
        date_write_is_processed = True
        
        # --- 核心檢查邏輯 ---
        if os.path.exists(filename):
            # messagebox.showinfo("文件已存在", f"文件 '{filename}' 已存在，放棄寫入。")
            print(f"文件 '{filename}' 已存在，放棄寫入。")
            loaded_df = pd.read_csv(filename, encoding='utf-8-sig')
        else:
            # all_df = get_dfcf_all_data()
            global realdatadf_lock
            print(f'realdatadf_lock:{realdatadf_lock}')
            time.sleep(6)
            # while realdatadf_lock:
            #     print(f'file is lock')
            all_df = get_stock_changes_background()
            # all_df['代码'] = all_df['代码'].apply(lambda x:str(x))
            all_df['代码'] = all_df["代码"].astype(str).str.zfill(6)
            # 4. 儲存 DataFrame
            all_df.to_csv(filename, index=False, encoding='utf-8-sig') #
            # messagebox.showinfo("成功", f"文件已儲存為: {filename}")
            print(f"文件已儲存為: {filename}")
            loaded_df = all_df
        # loaded_df['代码'] = loaded_df['代码'].apply(lambda x:str(x))
        loaded_df['代码'] = loaded_df["代码"].astype(str).str.zfill(6)

        return loaded_df

    except Exception as e:
        messagebox.showerror("錯誤", f"儲存文件時發生錯誤: {e}")
        print(f"儲存文件時發生錯誤: {e}")

def get_stock_changes(selected_type=None, stock_code=None):
    """获取股票异动数据"""
    global realdatadf, last_updated_time
    current_time = datetime.now()
    # if (len(realdatadf) == 0 and last_updated_time is None) or current_time - last_updated_time >= timedelta(minutes=update_interval_minutes):
    #     save_thread = threading.Thread(target=get_stock_changes_time)
    #     save_thread.start()
    #     print("已启动get_stock_changes_time后台保存任务...")

    url = "https://push2ex.eastmoney.com/getAllStockChanges?"
    reversed_symbol_map = {v: k for k, v in symbol_map.items()}

    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'pageindex': '0',
        'pagesize': '50000',
        'dpt': 'wzchanges',
        '_': int(time.time() * 1000)
    }

    if selected_type is None:
        selected_type  = type_var.get()

    if selected_type:
        if selected_type in symbol_map:
            params['type'] = symbol_map[selected_type]
        else:
            messagebox.showerror("错误", f"无效的异动类型: {selected_type}")
            return pd.DataFrame()
    else:
        params['type'] = ','.join(symbol_map.values())
    
    try:
        global loaded_df
        global date_write_is_processed

        # if  not date_write_is_processed or (get_now_time_int() <= 1505 and loaded_df is None):
        if loaded_df is None:

            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data_json = response.json()
            
            if not data_json.get('data') or not data_json['data'].get('allstock'):
                print("提示", "未获取到数据")
                return pd.DataFrame()
            
            temp_df = pd.DataFrame(data_json["data"]["allstock"])
            if 'tm' not in temp_df.columns:
                return pd.DataFrame()
            
            temp_df["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors='coerce').dt.time
            temp_df.columns = ["时间", "代码", "_", "名称", "板块", "相关信息"]
            temp_df = temp_df[["时间", "代码", "名称", "板块", "相关信息"]]
            
            temp_df["板块"] = temp_df["板块"].astype(str).map(
                lambda x: reversed_symbol_map.get(x, f"未知类型({x})")
            )
            temp_df = temp_df.sort_values(by="时间", ascending=False)
        else:
            temp_df = loaded_df

        # if not date_write_is_processed and get_day_is_trade_day() and get_now_time_int() > 1505:
        # # if get_now_time_int() > 1505:

        #     if loaded_df is None and (selected_type is None or selected_type == ''):
        #         selected_type = temp_df.drop_duplicates(subset=['板块'])['板块'][0]
        #     # start_async_save(temp_df,selected_type)
        #     if loaded_df is not None:
        #         temp_df = loaded_df

        # 数据过滤：排除8开头的股票、名称带*的股票、ST股票
        temp_df = filter_stocks(temp_df,selected_type)
        
        if stock_code:
            stock_code = stock_code.zfill(6)
            temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == str(stock_code)]


        return temp_df
        
    except requests.exceptions.Timeout:
        messagebox.showerror("错误", "请求超时")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        messagebox.showerror("错误", f"网络错误: {str(e)}")
        return pd.DataFrame()
    except Exception as e:
        messagebox.showerror("错误", f"数据处理错误: {str(e)}")
        return pd.DataFrame()


def filter_stocks(df,selected_type):
    """过滤股票数据，排除8开头的股票、名称带*的股票、ST股票"""
    if df.empty:
        return df
    
    # 排除8开头的股票
    df = df[~df["代码"].astype(str).str.startswith('8')]

    if selected_type is not None and not selected_type == '':
        df = df[df['板块'] == selected_type]
    if '时间' in df.columns and len(df) > 0:
        df = df.sort_values(by="时间", ascending=False)
    # if selected_type is not None: 
    #     df = df.query(f'板块 == {selected_type}')

    # 排除名称中带*的股票
    # df = df[~df["名称"].str.contains('\\*')]
    
    # 排除ST股票
    # df = df[~df["名称"].str.startswith('ST')]
    
    return df

def get_today(sep='-'):
    TODAY = datetime.today().date()
    fstr = "%Y" + sep + "%m" + sep + "%d"
    today = TODAY.strftime(fstr)
    return today

def populate_treeview(data=None):
    """填充表格数据"""
    for item in tree.get_children():
        tree.delete(item)
    
    if data is None:
        data = get_stock_changes()
        # date_str = get_today()
        # filename = f"dfcf_{date_str}.csv"
        # # 2. 檢查檔案是否存在
        # if os.path.exists(filename):
        #     # 檔案存在，載入到 DataFrame
        #     global loaded_df,realdatadf
        #     print(f"嘗檔案存在，載入到 DataFrame: {filename}")
        #     loaded_df = pd.read_csv(filename, encoding='utf-8-sig')
        #     loaded_df['代码'] = loaded_df['代码'].apply(lambda x:str(x))
        #     realdatadf = loaded_df
        #     data = loaded_df
        # else:
        #     data = get_stock_changes_time()
    
    if data is not None and not data.empty:
        for index, row in data.iterrows():
            tree.insert("", "end", values=list(row))
        status_var.set(f"已加载 {len(data)} 条记录 | 更新于: {time.strftime('%H:%M:%S')}")
    else:
        status_var.set("无数据")
        tree.insert("", "end", values=("无数据", "", "", "", ""))

def search_by_code():
    """按代码搜索"""
    code = code_entry.get().strip()
    selected_type = type_var.get()
    if code:
        # type_var.set("")
        status_var.set(f"搜索代码: {code}")
        root.update()
        data = _get_stock_changes(stock_code=code)
        # data = get_stock_changes(stock_code=code)
        # data = get_stock_changes_time(stock_code=code)
        populate_treeview(data)
    else:
        search_by_type()

def search_by_type():
    """按异动类型搜索"""
    # code = code_entry.get().strip()
    selected_type = type_var.get()
    code_entry.delete(0, tk.END)
    status_var.set(f"加载{selected_type if selected_type else '所有'}异动数据")
    root.update()

    # data = _get_stock_changes(selected_type=selected_type,stock_code=code)
    data = _get_stock_changes(selected_type=selected_type)
    # data = get_stock_changes(selected_type=selected_type,stock_code=code)
    # data = get_stock_changes_time(selected_type=selected_type,stock_code=code)
    populate_treeview(data)

def refresh_data():
    """刷新数据"""
    global loaded_df
    global date_write_is_processed
    # if not date_write_is_processed:
    loaded_df = None
    realdatadf = pd.DataFrame()
    status_var.set("刷新中...")
    root.update()
    current_type = type_var.get()
    current_code = code_entry.get().strip()
    
    if current_code:
        search_by_code()
    else:
        search_by_type()
    
    tree.focus_set()

def on_tree_select(event):
    """处理表格行选择事件"""

    # global sub_window
    selected_item = tree.selection()
    if selected_item:
        stock_info = tree.item(selected_item, 'values')
        stock_code = stock_info[1]
        stock_code = stock_code.zfill(6)
        send_to_tdx(stock_code)

        # 1. 推送代码到输入框
        code_entry.delete(0, tk.END)
        code_entry.insert(0, stock_code)
        
        # 2. 更新其他数据（示例）
        print(f"选中股票代码: {stock_code}")
        time.sleep(0.1)
        # 在这里可以调用其他函数来更新图表、详细信息等
        # update_details(stock_code)
        # if sub_window and sub_window.winfo_exists():
        #     _refresh_stock_data(stock_info,sub_window)

def on_code_entry_change(event=None):
    """处理代码输入框变化事件"""
    code = code_entry.get().strip()
    if len(code) == 6:  # 仅当输入长度等于6时触发联动
         # _get_stock_changes(stock_code=code)
        send_to_tdx(code)

def delete_selected_records():
    """删除选中的记录"""
    selected_items = tree.selection()
    if selected_items:
        if messagebox.askyesno("确认", "确定要删除选中的记录吗？"):
            for item in selected_items:
                tree.delete(item)
            status_var.set(f"已删除 {len(selected_items)} 条记录")
    else:
        messagebox.showinfo("提示", "请先选择要删除的记录")

def on_closing():
    """处理窗口关闭事件"""
    if messagebox.askyesno("确认", "确定要退出程序吗?"):
        root.destroy()

def on_date_selected(event):
    """处理日期选择事件"""
    selected_date = date_entry.get()
    print(f"选择了日期: {selected_date}")
    # 在这里添加根据日期更新数据的逻辑
    # update_data_for_date(selected_date)
    # --- 假設的DataFrame ---
    # 這個變數將用於存放載入的DataFrame
    global loaded_df
    
    try:
        # 1. 獲取日期並建立檔名
        selected_date_obj = date_entry.get_date()
        date_str = selected_date_obj.strftime("%Y-%m-%d")
        selected_type  = type_var.get()
        # filename = f"dfcf_{selected_type}_{date_str}.csv"
        filename = f"dfcf_{date_str}.csv"

        print(f"嘗試載入文件: {filename}")

        # 2. 檢查檔案是否存在
        if os.path.exists(filename):
            # 檔案存在，載入到 DataFrame
            loaded_df = pd.read_csv(filename, encoding='utf-8-sig')
            # loaded_df['代码'] = loaded_df['代码'].apply(lambda x:str(x))
            loaded_df['代码'] = loaded_df["代码"].astype(str).str.zfill(6)
            # 這裡可以根據需要更新 Treeview 或其他UI
            populate_treeview(loaded_df)
            
            # messagebox.showinfo("成功", f"文件 '{filename}' 已成功載入。")
            
        else:
            # 檔案不存在
            # loaded_df = pd.DataFrame() # 清空DataFrame
            # update_treeview_from_df(tree_widget, loaded_df) # 清空Treeview
            messagebox.showinfo("文件不存在", f"文件 '{filename}' 不存在，請檢查。")
            
    except Exception as e:
        messagebox.showerror("錯誤", f"載入文件時發生錯誤: {e}")
        print(f"載入文件時發生錯誤: {e}")

def update_linkage_status():
    """處理tdx和ths選中狀態變化的函數"""
    tdx_state = tdx_var.get()
    ths_state = ths_var.get()
    
    print(f"tdx 联动: {tdx_state}")
    print(f"ths 联动: {ths_state}")

def daily_task():
    """
    这个函数包含了你希望每天执行的逻辑。
    """
    print(f"每日定时任务执行了！当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # save_dataframe()
    start_async_save()
    # 在这里添加你的具体任务，例如：
    # crawl_data()
    # update_gui()
    # ...



def get_next_weekday_time(target_hour, target_minute):
    """
    计算下一次在工作日的指定时间。
    """
    now = datetime.now()
    
    # 获取今天在工作日内的目标时间
    target_time_today = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # 如果今天已经过了目标时间，或者今天是周末，则从明天开始寻找下一个工作日
    if now >= target_time_today or now.weekday() >= 5: # 5是周六，6是周日
        next_day = now + timedelta(days=1)
    else:
        # 如果今天没过目标时间且是工作日，就在今天执行
        return target_time_today

    # 循环直到找到下一个工作日
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)

    # 结合找到的日期和目标时间
    next_weekday_time = next_day.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    return next_weekday_time

def check_readldf_exist():
    # selected_date_obj = date_entry.get_date()
    # # 2. 格式化日期為字串
    # # 例如: 2025-09-03
    # date_str = selected_date_obj.strftime("%Y-%m-%d")
    global loaded_df,realdatadf
    date_str = get_today()
    # 3. 建立檔名（這裡儲存為 CSV）
    # selected_type  = type_var.get()
    # filename = f"dfcf_{selected_type}_{date_str}.csv"
    filename = f"dfcf_{date_str}.csv"
    # --- 核心檢查邏輯 ---
    if os.path.exists(filename):
        # messagebox.showinfo("文件已存在", f"文件 '{filename}' 已存在，放棄寫入。")
        print(f"文件 '{filename}' 已存在，放棄寫入。")
        loaded_df = pd.read_csv(filename, encoding='utf-8-sig')
        loaded_df['代码'] = loaded_df["代码"].astype(str).str.zfill(6)
        realdatadf = loaded_df
        return True
    else:
        return False

def schedule_worktime_task():
    """
    每隔5分钟执行一次的任务。
    """
    current_time = datetime.now().strftime("%H:%M:%S")
    print(f"自动更新任务get_stock_changes_background执行于: {current_time}")
    # 在这里添加你的具体任务逻辑

    save_thread = threading.Thread(target=get_stock_changes_background)
    save_thread.start()
    # 5分钟后再次调用此函数
    root.after(5 * 60 * 1000, schedule_worktime_task)



    # # 创建一个标签来显示任务状态
    # status_label = ttk.Label(root, text="任务已启动，每5分钟执行一次。", font=('Microsoft YaHei', 10))
    # status_label.pack(pady=5)

    # # 首次调用任务，启动定时循环
    # schedule_worktime_task()

def schedule_workday_task(root, target_hour, target_minute):
    """
    调度任务在下一个工作日的指定时间执行。
    """
    next_execution_time = get_next_weekday_time(target_hour, target_minute)
    
    now = datetime.now()
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)

    print(f"下一次任务将在 {next_execution_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，还有 {delay_ms // 1000} 秒。")

    # 使用 root.after() 调度任务，在回调函数中使用 lambda 包装，
    # 确保在任务完成后再次调用自身进行重新调度。
    root.after(delay_ms, lambda: [daily_task(), schedule_workday_task(root, target_hour, target_minute)])

# # --- 子窗口监控逻辑 ---
# def refresh_stock_data(window, stock_code, label):
#     """异步获取并刷新数据"""
#     future = executor.submit(get_stock_changes, stock_code)
#     future.add_done_callback(lambda f: update_label(f, label, window, stock_code))


# --- 数据持久化函数 ---
def save_monitor_list():
    # with open(MONITOR_LIST_FILE, "w") as f:
    #     json.dump(list(monitor_windows.keys()), f)
    # print(f"监控列表已保存到 {MONITOR_LIST_FILE}")
    """保存当前的监控股票列表到文件"""
    # Save a list of all stock_info tuples from the monitor windows

    """保存当前的监控股票列表到文件"""

    monitor_list = [win['stock_info'] for win in monitor_windows.values()]
    mo_list = []
    if len(monitor_list) > 0:
        for m in monitor_list:
            stock_code = m[0]
            if stock_code:
                stock_code = stock_code.zfill(6)
            if len(m) != 4 or not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
                print(f"错误", "请输入有效的6位股票代码:{monitor_list}")
                continue
            mo_list.append(m)
    else:
        print('no window find')
    with open(MONITOR_LIST_FILE, "w") as f:
            json.dump(mo_list, f)
    print(f"监控列表已保存到 {MONITOR_LIST_FILE}")

# def load_monitor_list():
#     """从文件加载监控股票列表"""
#     if os.path.exists(MONITOR_LIST_FILE):
#         with open(MONITOR_LIST_FILE, "r") as f:
#             return json.load(f)
#     return []
def load_monitor_list():
    """从文件加载监控股票列表"""
    if os.path.exists(MONITOR_LIST_FILE):
        with open(MONITOR_LIST_FILE, "r") as f:
            try:
                loaded_list = json.load(f)
                # 确保加载的数据是列表，并且包含列表/元组
                if isinstance(loaded_list, list) and all(isinstance(item, (list, tuple)) for item in loaded_list):
                    return [list(item) for item in loaded_list]
                return []
            except (json.JSONDecodeError, TypeError):
                return []
    return []

#mod get
def get_stock_changes_background(selected_type=None, stock_code=None, update_interval_minutes=update_interval_minutes):
    """
    获取股票异动数据，根据时间间隔判断是否从API获取。
    Args:
        selected_type (str): 板块类型。
        stock_code (str): 股票代码。
        update_interval_minutes (int): 更新周期（分钟）。
    """
    global realdatadf, last_updated_time
    global loaded_df,start_init
    global date_write_is_processed
    
    current_time = datetime.now()
    start_time=time.time()
    
    if get_day_is_trade_day() and 922 < get_now_time_int() < 932:
        realdatadf = pd.DataFrame()
        loaded_df = None

    # 使用 with realdatadf_lock 确保只有一个线程可以进入此关键区域
    if loaded_df is None  and (len(realdatadf) == 0 or get_work_time() or (not date_write_is_processed and get_now_time_int() > 1505)):
        with realdatadf_lock:
            # 检查是否需要从API获取数据
            if last_updated_time is None or current_time - last_updated_time >= timedelta(minutes=update_interval_minutes):
                print(f"时间间隔已到，正在从API获取新数据...")
                last_updated_time = current_time
                # 模拟从 Eastmoney API 获取数据
                time.sleep(0.1)
                for symbol in symbol_map.keys():
                    # 构造模拟数据
                    # 假设每次调用都返回一些新的和一些旧的数据
                    old_data = realdatadf.copy()
                    # new_data = {
                    #     '时间': [datetime.now().strftime("%H:%M:%S")],
                    #     '代码': [stock_code],
                    #     '简称': [f'股票{stock_code}'],
                    #     '板块': [selected_type],
                    #     '相关信息': [f"{random.uniform(0, 1):.6f},{random.uniform(10, 20):.2f},{random.uniform(0, 1):.6f}"]
                    # }
                    
                    # 模拟东财API返回的全部数据
                    temp_df = get_stock_changes(selected_type=symbol)
                    if len(temp_df) < 10:
                        continue
                    # api_df = pd.concat([old_data, pd.DataFrame(new_data)], ignore_index=True)
                    
                    # 使用 pd.concat 合并全局 realdatadf 和新获取的 api_df
                    realdatadf = pd.concat([realdatadf, temp_df], ignore_index=True)
                    
                    # 去除重复数据，保留最新的数据
                    realdatadf.drop_duplicates(subset=['时间','代码', '板块'], keep='last', inplace=True)
                    print(f"为 ({symbol}) 获取了新的异动数据，并更新了 realdatadf")
                    time.sleep(3)
                print(f"time:{time.time() - start_time}全部更新 获取了新的异动数据，并更新了 realdatadf")
                current_time = datetime.now()
                last_updated_time = current_time
                print("realdatadf 已更新。")
                populate_treeview(realdatadf)

            else:
                print(f"{current_time - last_updated_time}:未到更新时间，返回内存realdatadf数据。")
    if start_init == 0:
        time.sleep(6)
        start_init = 1
    #     # 数据过滤：排除8开头的股票、名称带*的股票、ST股票
    #     # if len(realdatadf) > 10 and selected_type is not None or selected_type != '':
    #     if selected_type is not None and selected_type != '' or stock_code is not None:
    #         print(f'single select:{selected_type} stock_code:{stock_code}')
    #         temp_df = get_stock_changes(selected_type=selected_type,stock_code=stock_code)
    #     elif len(realdatadf) > 10 and selected_type is not None or selected_type != '':
    #         temp_df = filter_stocks(realdatadf,selected_type)
    #         if stock_code:
    #             stock_code = stock_code.zfill(6)
    #             temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == str(stock_code)]
    #     else:
    #         temp_df = realdatadf

    #     # if get_now_time_int() > 1505 and not date_write_is_processed:
    #     #     start_async_save(realdatadf)
    #     if not get_work_time() and get_now_time_int() > 1530:
    #         print('set realdatadf to loaded_df now time is no worktime:{get_now_time_int()}')
    #         loaded_df = realdatadf
    # else:
    #     print(f'loaddf:{len(loaddf)} or realdatadf:{len(realdatadf)} or not worktime:{get_now_time_int()}')
    #     temp_df = get_stock_changes(selected_type=None, stock_code=None)
    return realdatadf

def get_stock_changes_time(selected_type=None, stock_code=None, update_interval_minutes=update_interval_minutes):
    """
    获取股票异动数据，根据时间间隔判断是否从API获取。
    Args:
        selected_type (str): 板块类型。
        stock_code (str): 股票代码。
        update_interval_minutes (int): 更新周期（分钟）。
    """
    global realdatadf, last_updated_time
    global loaded_df
    global date_write_is_processed
    
    current_time = datetime.now()
    start_time=time.time()
    # 使用 with realdatadf_lock 确保只有一个线程可以进入此关键区域

    if loaded_df is None  and (len(realdatadf) == 0 or get_work_time() or (not date_write_is_processed and get_now_time_int() > 1505)):
        if selected_type is not None and selected_type != '' or stock_code is not None:
            # print(f'single select:{selected_type} stock_code:{stock_code}')
            # if stock_code is not None:
            #     temp_df = get_stock_changes(selected_type='',stock_code=stock_code)
            # else:
            temp_df = get_stock_changes(selected_type=selected_type)
        elif len(realdatadf) > 10 and selected_type is not None or selected_type != '':
            temp_df = filter_stocks(realdatadf,selected_type)
            if stock_code:
                stock_code = stock_code.zfill(6)
                temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == str(stock_code)]
        else:
            temp_df = realdatadf
        if not get_work_time() and get_now_time_int() > 1530:
            # if realdatadf is not None and len(realdatadf) > 5000:
            #     print(f'set realdatadf to loaded_df now time is no worktime:{get_now_time_int()}')
            #     loaded_df = realdatadf
            # else:
            temp_df = get_stock_changes()
    else:
        # print(f'loaddf:{len(loaddf)} or realdatadf:{len(realdatadf)} or not worktime:{get_now_time_int()}')
        temp_df = get_stock_changes(selected_type=selected_type, stock_code=stock_code)

    return temp_df

def _get_stock_changes(selected_type=None, stock_code=None):
    """获取股票异动数据"""
    global realdatadf,loaded_df
    global last_updated_time
    # sub_window
    current_time = datetime.now()


    # if loaded_df is None or (last_updated_time is not None and current_time - last_updated_time >= timedelta(minutes=update_interval_minutes)):
    if loaded_df is None:
        temp_df = get_stock_changes_time(selected_type=selected_type)
    else:
        temp_df = loaded_df.copy()

    temp_df = filter_stocks(temp_df,selected_type)
    
    if stock_code:
        stock_code = stock_code.zfill(6)
        temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == str(stock_code)]

    return temp_df
        
    
# --- Monitor Window Functions ---
# def refresh_stock_data(window, stock_code, tree):
def refresh_stock_data(window_info, tree, item_id):
    """Asynchronously fetches and updates the stock data in the treeview."""
    # global start_init
    # if start_init != 0:
    global loaded_df,realdatadf
    time.sleep(1)
    stock_info = window_info['stock_info']
    stock_code = stock_info[0] # 使用 stock_info 中的第一个元素作为股票代码
    window = window_info['toplevel']
    # if loaded_df is None and len(realdatadf) == 0:
    #     return
    future = executor.submit(_get_stock_changes, None,stock_code)
    # future.add_done_callback(lambda f: update_tree_data(f, tree, window, stock_code))
    future.add_done_callback(lambda f: update_monitor_tree(f, tree, window_info, item_id))
    # future.add_done_callback(lambda f: update_tree_data(f, tree, window, stock_code))

# def _refresh_stock_data(stock_info,sub_window):
#     global sub_monitor_tree,sub_item_id
#     window_info = {'stock_info': stock_info, 'toplevel': sub_window}
#     refresh_stock_data(window_info, sub_monitor_tree, sub_item_id)

# --- 关键优化部分 ---
# def update_tree_data_(future, tree, window, stock_info):
#     """回调函数，更新子窗口的Treeview"""
#     try:
#         data = future.result()
#         if data is not None and window.winfo_exists():
#             now = datetime.now().strftime('%H:%M:%S')
#             data = data[data['代码'] ==  stock_code].set_index('时间').reset_index()
#             # 找到 Treeview 的第一行，先进行检查
#             item_id = tree.get_children()

#             if item_id: # 检查是否非空
#                 tree.item(item_id[0], values=(data[0],data[1],data[2],data[3],data[4]))
#             else:
#                 # 如果 Treeview 为空，则插入新行
#                 # tree.insert("", "end", values=(now, stock_info[0], stock_info[1], stock_info[2], f"{data['Price']:.2f}", f"{data['Change']:.2f}"))
#                 tree.insert("", "end", values=(data[0],data[1],data[2],data[3],data[4]))

#     except Exception as e:
#         if window.winfo_exists():
#             item_id = tree.get_children()
#             if item_id:
#                 tree.item(item_id[0], values=(datetime.now().strftime('%H:%M:%S'), stock_info[0], stock_info[1], stock_info[2], "错误", str(e)))
#             else:
#                 tree.insert("", "end", values=(datetime.now().strftime('%H:%M:%S'), stock_info[0], stock_info[1], stock_info[2], "错误", str(e)))
            
#     if window.winfo_exists():
#         window.after(5000, lambda: refresh_stock_data(window, stock_info, tree))

def update_monitor_tree(future, tree, window_info, item_id):
    """回调函数，更新子窗口的Treeview"""
    stock_info = window_info['stock_info']
    window = window_info['toplevel']
    stock_code, stock_name, *rest = stock_info

    try:
        data = future.result()
        if data is not None and window.winfo_exists():
            data = data[data['代码'] ==  stock_code].set_index('时间').reset_index()
            # Clear existing data first
            tree.delete(*tree.get_children())
            for index, row in data.iterrows():
                tree.insert("", "end", values=list(row))
    except Exception as e:
        if window.winfo_exists():
            # tree.item(item_id, values=(
            #     datetime.now().strftime('%H:%M:%S'), stock_code, stock_name, rest, "错误", str(e)
            # ))
            print(f"Error fetching data for {stock_code}: {e}")
            tree.insert("", "end", values=[f"Error:{e}"]) 
    if window.winfo_exists():
        window.after(5000, lambda: refresh_stock_data(window_info, tree, item_id))


def update_tree_data_old(future, tree, window, stock_code):
    """Callback function to update the Treeview with fetched data."""
    # time.sleep(3) # 模拟网络延迟
    try:
        data = future.result()
        # print(f'data:{data[:1]}')
        # print(f'data:{data[:1]}')
        if data is not None and window.winfo_exists():
            data = data[data['代码'] ==  stock_code].set_index('时间').reset_index()
            # Clear existing data first
            tree.delete(*tree.get_children())
            for index, row in data.iterrows():
                tree.insert("", "end", values=list(row))
                # tree.item(item_id, values=(now, stock_info, "示例", "示例", f"{data['Price']:.2f}", f"{data['Change']:.2f}"))

    except Exception as e:
        # if window.winfo_exists():
        #     item_id = tree.get_children()[0]
        #     tree.item(item_id, values=(datetime.now().strftime('%H:%M:%S'), stock_info, "错误", str(e), "", ""))
        if window.winfo_exists():
            print(f"Error fetching data for {stock_code}: {e}")
            tree.insert("", "end", values=[f"Error:{e}"]) # Add error message if window is still open


    # Schedule next refresh only if the window has not been destroyed
    if window.winfo_exists():
        window.after(5000, lambda: refresh_stock_data(window, stock_code, tree))

# def on_close_monitor(window, stock_code):
#     """处理子窗口关闭事件"""
#     if stock_code in monitor_windows:
#         del monitor_windows[stock_code]
#         save_monitor_list() # 在窗口关闭时保存列表
#     window.destroy()

def on_close_monitor(window_info):
    """处理子窗口关闭事件"""
    stock_info = window_info['stock_info']
    stock_code = stock_info[0] # 使用 stock_info 中的第一个元素作为股票代码
    window = window_info['toplevel']
    if stock_code in monitor_windows.keys():
        del monitor_windows[stock_code]
        save_monitor_list()
    window.destroy()

def create_monitor_window(stock_info):
    if len(stock_info) > 4:
        stock_info = stock_info[1:]
    stock_code, stock_name, *rest = stock_info

    """创建并配置子窗口，使用Treeview显示数据"""
    """Creates a new monitor window with a Treeview."""
    monitor_win = tk.Toplevel(root)
    monitor_win.resizable(True, True)
    # monitor_win.title(f"Monitoring: {stock_name} ({stock_code})")
    monitor_win.title(f"监控: {stock_name} ({stock_code})")
    monitor_win.geometry("420x300") # 设置合适的初始大小
    # monitor_win.geometry("600x300")

    # def on_click_monitor_window(event):
    #     global code_entry
    #     code_entry.delete(0, tk.END)
    #     code_entry.insert(0, stock_code)
    # monitor_win.bind("<Button-1>", on_click_monitor_window)
    
    # def delete_monitor():
    #     """从监控列表中删除当前股票"""
    #     nonlocal window_info
    #     on_close_monitor(window_info)

    # 使用 frame 包含 treeview 和 scrollbar
    tree_frame = ttk.Frame(monitor_win)
    tree_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)



    # # 添加一个删除按钮
    # delete_btn = ttk.Button(monitor_win, text="删除", command=delete_monitor)
    # delete_btn.pack(side=tk.TOP, pady=5)

    # 将 stock_info 和 Toplevel 实例打包到一个字典中

    window_info = {'stock_info': stock_info, 'toplevel': monitor_win}
    monitor_win.bind("<Button-1>", lambda event: update_code_entry(stock_code))
    # # --- 添加按钮以返回主窗口 ---
    # button_frame = ttk.Frame(monitor_win)
    # button_frame.pack(fill=tk.X, padx=5, pady=5)
    
    # return_btn = ttk.Button(button_frame, text="返回主窗口", command=lambda: update_code_entry(stock_code))
    # return_btn.pack(side=tk.LEFT)

    # # columns = ("Code", "Price", "Change")
    # columns = ("时间", "代码", "名称", "异动类型", "相关信息")
    # monitor_tree = ttk.Treeview(monitor_win, columns=columns, show="headings")
    # for col in columns:
    #     monitor_tree.heading(col, text=col, anchor=tk.CENTER)
    #     monitor_tree.column(col, width=120, anchor=tk.CENTER)
    # monitor_tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=(0, 10))
    # tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    columns = ("时间", "代码", "名称", "板块", "相关信息")
    monitor_tree = ttk.Treeview(monitor_win, columns=columns, show="headings")
    
    # 调整列宽以适应内容，减小间距
    # monitor_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
    monitor_tree.column("时间", width=60, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("代码", width=60, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("名称", width=60, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("板块", width=80, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("相关信息", width=160, anchor=tk.CENTER, stretch=False)

    for col in columns:
        monitor_tree.heading(col, text=col)

    # # 添加垂直滚动条
    # vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=monitor_tree.yview)
    # vsb.pack(side=tk.RIGHT, fill=tk.Y)
    # monitor_tree.configure(yscrollcommand=vsb.set)

    # for col in columns:
    #     monitor_tree.heading(col, text=col)
    #     item_id = monitor_tree.insert("", "end", values=("加载中...", "", "", "", "", ""))
            
    #     refresh_stock_data(window_info, monitor_tree, item_id)
    #     monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(window_info))
    item_id = monitor_tree.insert("", "end", values=("加载中...", "", "", "", "", ""))

    monitor_tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
    # refresh_stock_data(monitor_win, stock_info, monitor_tree)
    # monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(monitor_win, stock_info))
    
    refresh_stock_data(window_info, monitor_tree, item_id)
    monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(window_info))

    return window_info

# def create_monitor_window(stock_code, stock_name):
def create_monitor_window_old(stock_info):
    idx,stock_code, stock_name, *rest = stock_info

    """创建并配置子窗口，使用Treeview显示数据"""
    """Creates a new monitor window with a Treeview."""
    monitor_win = tk.Toplevel(root)
    # monitor_win.title(f"Monitoring: {stock_name} ({stock_code})")
    monitor_win.title(f"监控: {stock_name} ({stock_code})")
    monitor_win.geometry("370x180") # 设置合适的初始大小
    # monitor_win.geometry("600x300")
    
    # 将 stock_info 和 Toplevel 实例打包到一个字典中
    window_info = {'stock_info': stock_info, 'toplevel': monitor_win}

    # # columns = ("Code", "Price", "Change")
    # columns = ("时间", "代码", "名称", "异动类型", "相关信息")
    # monitor_tree = ttk.Treeview(monitor_win, columns=columns, show="headings")
    # for col in columns:
    #     monitor_tree.heading(col, text=col, anchor=tk.CENTER)
    #     monitor_tree.column(col, width=120, anchor=tk.CENTER)
    # monitor_tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=(0, 10))
    # tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))




    columns = ("时间", "代码", "名称", "板块", "相关信息")
    monitor_tree = ttk.Treeview(monitor_win, columns=columns, show="headings")
    
    # 调整列宽以适应内容，减小间距
    monitor_tree.column("时间", width=60, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("代码", width=60, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("名称", width=60, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("板块", width=80, anchor=tk.CENTER, stretch=False)
    monitor_tree.column("相关信息", width=100, anchor=tk.CENTER, stretch=False)

    for col in columns:
        monitor_tree.heading(col, text=col)

    monitor_tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

    
    # Insert initial placeholder data
    monitor_tree.insert("", "end", values=("", "", "", "", "", ""))

    refresh_stock_data(monitor_win, stock_code, monitor_tree)
    monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(monitor_win, stock_code))

    # refresh_stock_data(monitor_win, stock_info, monitor_tree)
    # monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(monitor_win, stock_info))
    
    return monitor_win

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


# --- 主窗口逻辑 ---  (lag)
def add_selected_stock():
    """添加选中的股票到监控窗口"""
    try:
        selected_item = tree.selection()
        if selected_item:
            stock_info = tree.item(selected_item, 'values')
            stock_code = stock_info[1]
            stock_name = stock_info[2]
            stock_code = stock_code.zfill(6)
            send_to_tdx(stock_code)

            # 1. 推送代码到输入框
            code_entry.delete(0, tk.END)
            code_entry.insert(0, stock_code)

            # stock_info = tree.item(selected_item, "values")
            # stock_code = stock_info[1]
            # 2. 更新其他数据（示例）
            print(f"选中监控股票代码: {stock_code}")
        else:
            messagebox.showwarning("警告", "请选择一个股票代码。")
            return


        if stock_code in monitor_windows.keys():
            messagebox.showwarning("警告", f"{stock_code} 的监控窗口已打开。")
            return

        monitor_win = create_monitor_window(stock_info)
        monitor_windows[stock_code] = monitor_win

    except IndexError:
        messagebox.showwarning("警告", "请选择一个股票代码。")

# --- 主窗口逻辑 ---  (lag)
def add_selected_stock_popup_window():
    """添加选中的股票到监控窗口"""
    try:
        selected_item = tree.selection()
        if selected_item:
            stock_info = tree.item(selected_item, 'values')
            stock_code = stock_info[1]
            stock_name = stock_info[2]
            stock_code = stock_code.zfill(6)
            send_to_tdx(stock_code)

            # 1. 推送代码到输入框
            code_entry.delete(0, tk.END)
            code_entry.insert(0, stock_code)

            # stock_info = tree.item(selected_item, "values")
            # stock_code = stock_info[1]
            # 2. 更新其他数据（示例）
            print(f"选中监控股票代码: {stock_code}")
        else:
            messagebox.showwarning("警告", "请选择一个股票代码。")
            return


        if stock_code in monitor_windows.keys():
            messagebox.showwarning("警告", f"{stock_code} 的监控窗口已打开。")
            return

        monitor_win = create_popup_window(stock_info)
        # monitor_windows[stock_code] = monitor_win

    except IndexError:
        messagebox.showwarning("警告", "请选择一个股票代码。")

def show_context_menu(event):
    """显示右键菜单"""
    try:
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            context_menu.post(event.x_root, event.y_root)
    except Exception:
        pass

# def load_initial_data():
#     """加载初始股票数据到Treeview"""
#     stock_tree.delete(*stock_tree.get_children())
#     data = generate_stock_data()
#     for row in data:
#         stock_tree.insert("", "end", values=row)

def on_main_window_close():
    """处理主窗口关闭事件"""
    if messagebox.askyesno("确认", "确定要退出程序吗?"):
        save_monitor_list() # 确保在主程序关闭时保存列表
        """处理主窗口关闭事件"""
        for win_info in list(monitor_windows.values()):
            # 修正：访问内部字典的 'toplevel' 键
            win_info['toplevel'].destroy()
        executor.shutdown(wait=False)
        root.destroy()
    # for win in list(monitor_windows.values()):
    #     win.destroy()
    # executor.shutdown(wait=False)
    # root.destroy()

def update_code_entry(stock_code):
    """更新主窗口的 Entry"""
    global code_entry
    if not stock_code  or not stock_code.isdigit():
        print(f"错误", "请输入有效的6位股票代码:{stock_code}")
        return
    if stock_code:
        stock_code = stock_code.zfill(6)
    code_entry.delete(0, tk.END)
    code_entry.insert(0, stock_code)

# def create_popup_window(stock_info,parent=None):
#     # 创建新的 Toplevel 窗口（弹出窗口）
#     global sub_window,sub_monitor_tree
#     if len(stock_info) > 4:
#         stock_info = stock_info[1:]
#     stock_code, stock_name, *rest = stock_info

#     if parent:
#         sub_window = tk.Toplevel(parent)
#     else:
#         sub_window = tk.Toplevel(root)
#     sub_window.title("详细信息")


#     """创建并配置子窗口，使用Treeview显示数据"""
#     """Creates a new monitor window with a Treeview."""
#     sub_window.resizable(True, True)
#     sub_window.geometry("420x300") # 设置合适的初始大小
#     # monitor_win.title(f"Monitoring: {stock_name} ({stock_code})")


#     sub_window.title(f"详情: {stock_name} ({stock_code})")
#     tree_frame = ttk.Frame(sub_window)
#     tree_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

#     window_info = {'stock_info': stock_info, 'toplevel': sub_window}

#     columns = ("时间", "代码", "名称", "板块", "相关信息")
#     sub_monitor_tree = ttk.Treeview(sub_window, columns=columns, show="headings")
#     # 调整列宽以适应内容，减小间距
#     # monitor_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
#     sub_monitor_tree.column("时间", width=60, anchor=tk.CENTER, stretch=False)
#     sub_monitor_tree.column("代码", width=60, anchor=tk.CENTER, stretch=False)
#     sub_monitor_tree.column("名称", width=60, anchor=tk.CENTER, stretch=False)
#     sub_monitor_tree.column("板块", width=80, anchor=tk.CENTER, stretch=False)
#     sub_monitor_tree.column("相关信息", width=160, anchor=tk.CENTER, stretch=False)

#     for col in columns:
#         sub_monitor_tree.heading(col, text=col)

#     sub_item_id = sub_monitor_tree.insert("", "end", values=("加载中...", "", "", "", "", ""))

#     sub_monitor_tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
#     # refresh_stock_data(window_info, sub_monitor_tree, sub_item_id)
#     return sub_window

# def setup_main_window():
#     """设置主窗口和UI元素"""
#     global root, tree, context_menu
#     # 创建主窗口
# MONITOR_LIST_FILE = "monitor_list.txt"
# global code_entry

root = tk.Tk()
root.title("股票异动数据监控")
# root.geometry("1200x700")  # 增大窗口初始大小
root.geometry("750x550")
root.minsize(720,500)    # 设置最小尺寸限制

root.resizable(True, True)
# root.protocol("WM_DELETE_WINDOW", on_closing)

# 配置样式
style = ttk.Style()
style.theme_use('clam')
style.configure("Treeview", 
    background="white", 
    foreground="black", 
    rowheight=25,
    fieldbackground="white",
    font=('Microsoft YaHei', 9)
)
style.configure("Treeview.Heading", 
    font=('Microsoft YaHei', 10, 'bold'),
    background="#4a6984",
    foreground="white",
    relief="flat"
)
style.map("Treeview", background=[('selected', '#3478bf')])

# 创建顶部工具栏
toolbar = tk.Frame(root, bg="#f0f0f0", padx=5, pady=5)
toolbar.pack(fill=tk.X)

# 刷新按钮
refresh_btn = tk.Button(toolbar, text="↻ 刷新数据", command=refresh_data, 
                       font=('Microsoft YaHei', 10), bg="#5b9bd5", fg="white",
                       padx=10, pady=3, relief="flat")
refresh_btn.pack(side=tk.LEFT, padx=5)

# 删除按钮
delete_btn = tk.Button(toolbar, text="删除选中记录", command=delete_selected_records,
                       font=('Microsoft YaHei', 10), bg="#d9534f", fg="white",
                       padx=10, pady=3, relief="flat")
delete_btn.pack(side=tk.LEFT, padx=5)


# # --- 日期選擇器和選項框的 Frame ---
# date_options_frame = tk.Frame(toolbar)
# date_options_frame.pack(side=tk.LEFT, padx=10)

# --- 日期選擇器 ---
# 添加一个Label作为日期选择器的说明
date_label = tk.Label(toolbar, text="选择日期:", font=('Microsoft YaHei', 10), bg=toolbar['bg'])
date_label.pack(side=tk.LEFT, padx=(10, 5))

# 创建DateEntry并放置在删除按钮右侧
date_entry = DateEntry(toolbar, width=12, background='darkblue', foreground='white', borderwidth=2,
                       font=('Microsoft YaHei', 10))
date_entry.pack(side=tk.LEFT, padx=5)

# 绑定日期选择事件
date_entry.bind("<<DateEntrySelected>>", on_date_selected)

# --- tdx 和 ths 聯動屬性框 ---
tdx_var = tk.BooleanVar(value=True)
ths_var = tk.BooleanVar(value=False)
dfcf_var = tk.BooleanVar(value=False)

tdx_checkbutton = tk.Checkbutton(toolbar, text="联动TDX", variable=tdx_var, 
                                 command=update_linkage_status)
tdx_checkbutton.pack(side=tk.LEFT, padx=5)

ths_checkbutton = tk.Checkbutton(toolbar, text="联动THS", variable=ths_var, 
                                 command=update_linkage_status)
ths_checkbutton.pack(side=tk.LEFT, padx=5)

dfcf_checkbutton = tk.Checkbutton(toolbar, text="联动DC", variable=dfcf_var, 
                                 command=update_linkage_status)
dfcf_checkbutton.pack(side=tk.LEFT, padx=5)

# 创建异动类型选择框架
type_frame = tk.LabelFrame(root, text="异动类型选择", font=('Microsoft YaHei', 9), 
                          padx=10, pady=10, bg="#f9f9f9")
type_frame.pack(fill=tk.X, padx=10, pady=5)

# 定义异动类型列表
stock_types = [
    "火箭发射", "快速反弹", "大笔买入", "封涨停板", "打开跌停板", "有大买盘", 
    "竞价上涨", "高开5日线", "向上缺口", "60日新高", "60日大幅上涨", "加速下跌", 
    "高台跳水", "大笔卖出", "封跌停板", "打开涨停板", "有大卖盘", "竞价下跌", 
    "低开5日线", "向下缺口", "60日新低", "60日大幅下跌"
]

# 创建单选按钮变量
type_var = tk.StringVar(value="")
# type_var = tk.StringVar(value="火箭发射")

# 创建单选按钮容器
radio_container = tk.Frame(type_frame, bg="#f9f9f9")
radio_container.pack(fill=tk.X)

# 每行显示7个异动类型按钮
buttons_per_row = 7
for i, stock_type in enumerate(stock_types):
    row = i // buttons_per_row
    col = i % buttons_per_row
    
    btn = tk.Radiobutton(
        radio_container, 
        text=stock_type, 
        variable=type_var, 
        value=stock_type,
        command=search_by_type,
        font=('Microsoft YaHei', 8),
        bg="#f9f9f9",
        activebackground="#e6f3ff",
        padx=5, 
        pady=2
    )
    btn.grid(row=row, column=col, sticky=tk.W, padx=5, pady=3)

# 创建搜索框和按钮
search_frame = tk.Frame(root, bg="#f0f0f0", padx=10, pady=10)
search_frame.pack(fill=tk.X, padx=10)

tk.Label(search_frame, text="股票代码搜索:", font=('Microsoft YaHei', 9), 
        bg="#f0f0f0").pack(side=tk.LEFT, padx=(0, 5))

code_entry = tk.Entry(search_frame, width=10, font=('Microsoft YaHei', 9))
code_entry.pack(side=tk.LEFT, padx=5)
code_entry.bind("<KeyRelease>", on_code_entry_change)

search_btn = tk.Button(search_frame, text="搜索", command=search_by_code, 
                      font=('Microsoft YaHei', 9), bg="#5b9bd5", fg="white",
                      padx=12, pady=2, relief="flat")
search_btn.pack(side=tk.LEFT, padx=5)

clear_btn = tk.Button(search_frame, text="清空", 
                     command=lambda: [code_entry.delete(0, tk.END), search_by_code()],
                     font=('Microsoft YaHei', 9), 
                     padx=10, pady=2)
clear_btn.pack(side=tk.LEFT, padx=5)

                     # command=lambda: [type_var.set(""), code_entry.delete(0, tk.END), search_by_type()],
clear_btn = tk.Button(search_frame, text="清除筛选", 
                     command=lambda: [type_var.set(""), search_by_type()],
                     font=('Microsoft YaHei', 9), 
                     padx=10, pady=2)
clear_btn.pack(side=tk.LEFT, padx=5)



# 创建Treeview组件和滚动条
columns = ("时间", "代码", "名称", "异动类型", "相关信息")
tree_frame = tk.Frame(root)
tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

# 配置列
tree.heading("时间", text="时间", anchor=tk.CENTER)
tree.heading("代码", text="代码", anchor=tk.CENTER)
tree.heading("名称", text="名称", anchor=tk.CENTER)
tree.heading("异动类型", text="异动类型", anchor=tk.CENTER)
tree.heading("相关信息", text="相关信息", anchor=tk.W)

# 增大列宽
tree.column("时间", width=120, anchor=tk.CENTER, minwidth=100)
tree.column("代码", width=100, anchor=tk.CENTER, minwidth=80)
tree.column("名称", width=120, anchor=tk.CENTER, minwidth=100)
tree.column("异动类型", width=150, anchor=tk.CENTER, minwidth=120)
tree.column("相关信息", width=500, anchor=tk.W, minwidth=300)

# 布局
tree.grid(row=0, column=0, sticky="nsew")
vsb.grid(row=0, column=1, sticky="ns")
hsb.grid(row=1, column=0, sticky="ew")

tree_frame.grid_rowconfigure(0, weight=1)
tree_frame.grid_columnconfigure(0, weight=1)

# 绑定选择事件
tree.bind("<<TreeviewSelect>>", on_tree_select)

# 状态栏
status_var = tk.StringVar(value="就绪 | 等待操作...")
status_bar = ttk.Label(root, textvariable=status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(5, 2))
status_bar.pack(side=tk.BOTTOM, fill=tk.X)

# 添加键盘快捷键
root.bind("<F5>", lambda event: refresh_data())
root.bind("<Control-r>", lambda event: refresh_data())

# 初始加载数据
root.after(100, lambda: populate_treeview())

# 设置你希望任务每天执行的时间（例如：每天 23:00）
target_hour = 15
target_minute = 5

tk.Label(root, text=f"程序正在运行，每日任务已设置在 {target_hour:02d}:{target_minute:02d} 执行。").pack(pady=10)

# 启动定时任务调度
schedule_workday_task(root, target_hour, target_minute)

# 创建一个标签来显示任务状态
status_label = ttk.Label(root, text="更新任务，每5分钟执行一次。", font=('Microsoft YaHei', 10))
status_label.pack(pady=5)
# 首次调用任务，启动定时循环
check_readldf_exist()
schedule_worktime_task()
# 运行主循环
# root.mainloop()

if get_now_time_int() > 1530 and not date_write_is_processed:
    start_async_save()

# root = tk.Tk()
# root.title("单文件监控")
# root.geometry("600x400")

# columns = ("代码", "简称", "现价", "竞价涨幅")
# stock_tree = ttk.Treeview(root, columns=columns, show="headings")
# for col in columns:
#     stock_tree.heading(col, text=col, anchor=tk.CENTER)
#     stock_tree.column(col, width=120, anchor=tk.CENTER)
# stock_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

tree.bind("<Button-3>", show_context_menu)

context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="添加到监控", command=add_selected_stock)
context_menu.add_command(label="POP详情", command=add_selected_stock_popup_window)

# load_initial_data()
# 自动加载并开启监控窗口
initial_monitor_list = load_monitor_list()
# if initial_monitor_list:
#     for stock_info in initial_monitor_list:
#         if isinstance(stock_info, list):
#             stock_code = stock_info[0]
#             stock_code = stock_info[0]
#             if stock_code not in monitor_windows:
#                 monitor_win = create_monitor_window(stock_info)
#                 monitor_windows[stock_code] = monitor_win
if initial_monitor_list:
    for stock_info in initial_monitor_list:
        if isinstance(stock_info, list) and stock_info:
            stock_code = stock_info[0]
            if stock_code not in monitor_windows:
                monitor_win = create_monitor_window(stock_info)
                monitor_windows[stock_code] = monitor_win
        elif isinstance(stock_info, str):
            stock_code = stock_info
            # 重新构造 stock_info，以便 create_monitor_window 使用
            # 注意：这里需要你自行获取完整信息或根据需要调整逻辑
            if stock_code not in monitor_windows:
                monitor_win = create_monitor_window([stock_code, "未知", "未知", 0, 0])
                monitor_windows[stock_code] = monitor_win

root.protocol("WM_DELETE_WINDOW", on_main_window_close)
root.mainloop()

# if __name__ == "__main__":
#     setup_main_window()