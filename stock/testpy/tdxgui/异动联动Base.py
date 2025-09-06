import requests
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox
import time
import json
import threading
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
def get_dfcf_all_data(df,selected_type):

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
    

    for sel_type in symbol_map:

        if sel_type == selected_type:
            continue
        else:
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
            time.sleep(5)

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

def start_async_save(df, filepath):
    """启动一个新线程来保存DataFrame"""
    # 创建并启动新线程
    save_thread = threading.Thread(target=save_dataframe, args=(df, filepath))
    save_thread.start()
    print("已启动后台保存任务...")

# --- 儲存 DataFrame 的函數 ---
def save_dataframe(df=None,selected_type=''):
    """獲取選取的日期，並將 DataFrame 儲存為以該日期命名的檔案。"""
    global date_write_is_processed
    global loaded_df

    if df is None:
        df = pd.DataFrame()
    # 如果正在處理中，則直接返回，不執行後續邏輯
    if date_write_is_processed:
        loaded_df_deduplicated = df.drop_duplicates(subset=['板块'])
        count =len(symbol_map.keys())
        if len(loaded_df_deduplicated) == len(symbol_map.keys()):
            print(f'loaded_df_deduplicated:{count} is Alldata OK')
        else:
            if loaded_df is not None:
                df = loaded_df
        return df

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
            all_df = get_dfcf_all_data(df,selected_type)
            # 4. 儲存 DataFrame
            all_df.to_csv(filename, index=False, encoding='utf-8-sig') #
            # messagebox.showinfo("成功", f"文件已儲存為: {filename}")
            print(f"文件已儲存為: {filename}")
            loaded_df = all_df

        return loaded_df

    except Exception as e:
        messagebox.showerror("錯誤", f"儲存文件時發生錯誤: {e}")
        print(f"儲存文件時發生錯誤: {e}")


def get_stock_changes(selected_type=None, stock_code=None):
    """获取股票异动数据"""
    url = "https://push2ex.eastmoney.com/getAllStockChanges?"
    # symbol_map = {
    #     "火箭发射": "8201",
    #     "快速反弹": "8202",
    #     "大笔买入": "8193",
    #     "封涨停板": "4",
    #     "打开跌停板": "32",
    #     "有大买盘": "64",
    #     "竞价上涨": "8207",
    #     "高开5日线": "8209",
    #     "向上缺口": "8211",
    #     "60日新高": "8213",
    #     "60日大幅上涨": "8215",
    #     "加速下跌": "8204",
    #     "高台跳水": "8203",
    #     "大笔卖出": "8194",
    #     "封跌停板": "8",
    #     "打开涨停板": "16",
    #     "有大卖盘": "128",
    #     "竞价下跌": "8208",
    #     "低开5日线": "8210",
    #     "向下缺口": "8212",
    #     "60日新低": "8214",
    #     "60日大幅下跌": "8216",
    # }
    reversed_symbol_map = {v: k for k, v in symbol_map.items()}

    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'pageindex': '0',
        'pagesize': '50000',
        'dpt': 'wzchanges',
        '_': int(time.time() * 1000)
    }
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
        else:
            temp_df = loaded_df

        if not date_write_is_processed and get_day_is_trade_day() and get_now_time_int() > 1505 or get_now_time_int() < 800:
        # if get_now_time_int() > 1505:

            if selected_type is None or selected_type == '':
                selected_type = temp_df.drop_duplicates(subset=['板块'])['板块'][0]
            start_async_save(temp_df,selected_type)
            if loaded_df is not None:
                temp_df = loaded_df

        # 数据过滤：排除8开头的股票、名称带*的股票、ST股票
        temp_df = filter_stocks(temp_df,selected_type)
        
        if stock_code:
            stock_code = stock_code.zfill(6)
            temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == stock_code]

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
    
    if not selected_type == '':
        df = df[df['板块'] == selected_type]
    df = df.sort_values(by="时间", ascending=False)
    # if selected_type is not None: 
    #     import ipdb;ipdb.set_trace()
    #     df = df.query(f'板块 == {selected_type}')

    # 排除名称中带*的股票
    # df = df[~df["名称"].str.contains('\\*')]
    
    # 排除ST股票
    # df = df[~df["名称"].str.startswith('ST')]
    
    return df

def populate_treeview(data=None):
    """填充表格数据"""
    for item in tree.get_children():
        tree.delete(item)
    
    if data is None:
        data = get_stock_changes()
    
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
        data = get_stock_changes(stock_code=code)
        populate_treeview(data)
    else:
        search_by_type()

def search_by_type():
    """按异动类型搜索"""
    code = code_entry.get().strip()
    selected_type = type_var.get()
    # code_entry.delete(0, tk.END)
    status_var.set(f"加载{selected_type if selected_type else '所有'}异动数据")
    root.update()
    data = get_stock_changes(selected_type=selected_type,stock_code=code)
    populate_treeview(data)

def refresh_data():
    """刷新数据"""
    global loaded_df
    global date_write_is_processed
    if not date_write_is_processed:
        loaded_df = None
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
    selected_item = tree.selection()
    if selected_item:
        values = tree.item(selected_item, 'values')
        stock_code = values[1]
        stock_code = stock_code.zfill(6)
        send_to_tdx(stock_code)

        # 1. 推送代码到输入框
        code_entry.delete(0, tk.END)
        code_entry.insert(0, stock_code)
        
        # 2. 更新其他数据（示例）
        print(f"选中股票代码: {stock_code}")
        # 在这里可以调用其他函数来更新图表、详细信息等
        # update_details(stock_code)
        
# def send_to_tdx(stock_code):
#     """发送股票代码到通达信"""
#     if stock_code:
#         root.after(100, lambda: _execute_tdx(stock_code))

# def _execute_tdx(stock_code):
#     """实际执行通达信联动的方法"""
#     try:
#         # 确保代码是6位长度
#         formatted_code = stock_code.zfill(6)
        
#         # 处理8开头的代码，使其与6开头的代码联动效果相同
#         if formatted_code.startswith('8'):
#             # 将8开头的代码转换为6开头，但保留后5位不变
#             formatted_code = '6' + formatted_code[1:]
        
#         # 发送处理后的代码到通达信
#         sender = TdxStockSenderApp(root)
#         sender.stock_code_var.set(formatted_code)
#         sender.update_generated_code()
#         sender.send_to_tdx()
#     except Exception as e:
#         messagebox.showerror("联动错误", f"通达信联动失败: {str(e)}")

def on_code_entry_change(event=None):
    """处理代码输入框变化事件"""
    code = code_entry.get().strip()
    if len(code) == 6:  # 仅当输入长度等于6时触发联动
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
    save_dataframe()
    # 在这里添加你的具体任务，例如：
    # crawl_data()
    # update_gui()
    # ...

# def schedule_daily_task(root):
#     """
#     调度每日定时任务。
#     """
#     # 立即执行一次任务（如果需要的话，或者可以注释掉）
#     # daily_task()

#     # 计算下一次执行任务的时间
#     now = datetime.now()
#     # 设定每日任务的目标时间，例如午夜 00:00:00
#     target_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
#     # 计算需要等待的毫秒数
#     delay_ms = int((target_time - now).total_seconds() * 1000)

#     print(f"下一次任务将在 {target_time} 执行，还有 {delay_ms // 1000} 秒。")

#     # 使用 root.after() 调度下一次任务
#     root.after(delay_ms, lambda: schedule_daily_task(root))
    
#     # 此外，可以在每次递归调用时执行任务
#     # root.after(delay_ms, lambda: [daily_task(), schedule_daily_task(root)])
    
#     # 更好的做法是，只在满足条件时执行任务
#     if now > target_time - timedelta(minutes=1): # 比如提前一分钟，防止错过
#         daily_task()

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

# def schedule_workday_task(root, target_hour, target_minute):
    # """
    # 调度任务在下一个工作日的指定时间执行。
    # """
    # next_execution_time = get_next_weekday_time(target_hour, target_minute)
    
    # now = datetime.now()
    # delay_ms = int((next_execution_time - now).total_seconds() * 1000)

    # print(f"下一次任务将在 {next_execution_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，还有 {delay_ms // 1000} 秒。")

    # # 使用 root.after() 调度任务
    # root.after(delay_ms, lambda: [daily_task(), schedule_workday_task(root, target_hour, target_minute)])

# def schedule_daily_task(root, target_hour, target_minute):
#     """
#     调度每日定时任务。

#     Args:
#         root (tk.Tk): Tkinter 根窗口。
#         target_hour (int): 目标执行时间的小时。
#         target_minute (int): 目标执行时间的分钟。
#     """
#     now = datetime.now()
#     # 设置今天的目标时间
#     target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
#     # 如果目标时间已经过去，则安排在明天的同一时间执行
#     if now >= target_time:
#         target_time += timedelta(days=1)
    
#     # 计算需要等待的毫秒数
#     delay_ms = int((target_time - now).total_seconds() * 1000)

#     print(f"下一次任务将在 {target_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，还有 {delay_ms // 1000} 秒。")

#     # 使用 root.after() 调度任务。任务执行完毕后，再次调用自己进行下一次调度。
#     root.after(delay_ms, lambda: [daily_task(), schedule_daily_task(root, target_hour, target_minute)])

# 创建主窗口
root = tk.Tk()
root.title("股票异动数据监控")
# root.geometry("1200x700")  # 增大窗口初始大小
root.geometry("750x550")
root.minsize(720,500)    # 设置最小尺寸限制

root.resizable(True, True)
root.protocol("WM_DELETE_WINDOW", on_closing)

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

tdx_checkbutton = tk.Checkbutton(toolbar, text="联动tdx", variable=tdx_var, 
                                 command=update_linkage_status)
tdx_checkbutton.pack(side=tk.LEFT, padx=5)

ths_checkbutton = tk.Checkbutton(toolbar, text="联动ths", variable=ths_var, 
                                 command=update_linkage_status)
ths_checkbutton.pack(side=tk.LEFT, padx=5)

# # 创建一个Frame来放置顶部控制按钮
# top_frame = tk.Frame(root)
# top_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

# # 添加日期选择输入框
# tk.Label(top_frame, text="选择日期:", font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=(10, 5))
# cal = DateEntry(top_frame, width=12, background='darkblue', foreground='white', borderwidth=2)
# cal.pack(side=tk.LEFT, padx=5)
# cal.bind("<<DateEntrySelected>>", on_date_selected)

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

tk.Label(root, text=f"程序正在运行，每日任务已设置在 {target_hour:02d}:{target_minute:02d} 执行。").pack(pady=20)

# 启动定时任务调度
schedule_workday_task(root, target_hour, target_minute)
# daily_task()
# 运行主循环
root.mainloop()
