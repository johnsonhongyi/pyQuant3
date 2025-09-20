import os
import sys
import win32gui
import win32process
import win32api
import win32con
import threading
from ctypes import wintypes
import ctypes
EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
GetWindowText = ctypes.windll.user32.GetWindowTextW
GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
date_entry = None
codelist = []
ths_code=[]

def get_base_path():
    """
    プログラム実行時のベースパスを取得する。
    PyInstallerでexe化された場合でも、実行ファイルのディレクトリを返す。
    """
    if getattr(sys, 'frozen', False):
        # PyInstallerでexe化された場合
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 通常の.pyファイルとして実行された場合
        return os.path.dirname(os.path.abspath(__file__))
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
dfcf_process_hwnd = 0
tdx_pid = 0
dfcf_pid = 0
ths_pid = 0
thsweb_process_hwnd = 0
ahk_process_hwnd = 0

BASE_DIR = get_base_path()

code_file_name= os.path.join(BASE_DIR, "code_ths_other.json")
MONITOR_LIST_FILE =  os.path.join(BASE_DIR, "monitor_list.json")
CONFIG_FILE =  os.path.join(BASE_DIR, "window_config.json")
ALERTS_FILE =  os.path.join(BASE_DIR, "alerts.json")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archives")
DARACSV_DIR = os.path.join(BASE_DIR, "datacsv")
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(DARACSV_DIR, exist_ok=True)

def get_ths_code():
    global ths_code,code_file_name
    if os.path.exists(code_file_name):
        print(f"{code_file_name} exists, loading...")
        with open(code_file_name, "r", encoding="utf-8") as f:
            codelist = json.load(f)['stock']
            # ths_code = [co for co in codelist if co.startswith('60')]
            ths_code = [co for co in codelist]
        print("Loaded:", len(ths_code))
    # else:
    #     print(f"{code_file_name} not found, creating...")
    #     data = {"stock": ths_code}
    #     with open(code_file_name, "w", encoding="utf-8") as f:
    #         json.dump(data, f, ensure_ascii=False, indent=4)

def get_pids(pname):
    # print(pname)
    # find AutoHotkeyU64.exe
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
    #not find AutoHotkeyU64.exe ths-tdx-web.py
    hwnd = 0
    pids = get_pids(pname)
    for pid in pids:
        handles = get_handles(pid)
        # print(handles)
        for hwnd in handles:
            if IsWindowVisible(hwnd):
                return hwnd
    return hwnd


def get_pids_values(pname):
    # print(pname)
    # find AutoHotkeyU64.exe
    pids = 0
    for proc in psutil.process_iter():
        if pname in proc.name():
            # pids.append(proc.pid)
            pids = proc.pid
    # print(pids)
    return pids


def find_window_by_title_safe(target_title: str):
    # find ths-tdx-web.py
    """
    通过对目标标题使用 re.escape()，安全地查找包含空格和括号的窗口。
    """
    found_windows = []
    # findhwnd = 0
    # 使用 re.escape() 自动转义所有特殊字符
    escaped_title = re.escape(target_title)
    # 使用正则表达式匹配，并忽略大小写
    title_pattern = re.compile(escaped_title, re.IGNORECASE)

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            window_title = win32gui.GetWindowText(hwnd)
            # 使用编译后的模式进行搜索
            if title_pattern.search(window_title):
                found_windows.append((hwnd, window_title))
    win32gui.EnumWindows(enum_handler, None)
    return found_windows


FAGE_READWRITE = 0x04  # 偏移地址：0x04的意思就是：在空间上偏移4个内存单元
PROCESS_ALL_ACCESS = 0x001F0FFF
VIRTUAL_MEN = (0x1000 | 0x2000)

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

def check_pid(pname,srcpid):
    pid = get_pids(pname)
    return pid == srcpid

def check_pids_all():
    # ['mainfree.exe','hexin.exe']
    tdxpname='tdxw.exe'
    thspname='hexin.exe'
    dfcfpname='mainfree.exe'
    global tdx_pid, ths_pid,dfcf_pid
    if not check_pid(tdxpname,tdx_pid):
        tdx_pid = get_pids(tdxpname)
        print(f'tdx_pid:{tdx_pid}')
        find_tdx_window()
    if not check_pid(dfcfpname,dfcf_pid):
        global dfcf_process_hwnd
        dfcf_pid = get_pids('mainfree.exe')
        print(f'dfcf_pid:{dfcf_pid}')
        dfcf_process_hwnd = get_handle('mainfree.exe')
    if not check_pid(thspname,ths_pid):
        global ths_process_hwnd,ths_prc_hwnd
        ths_pid = get_pids(thspname)
        print(f'ths_pid:{ths_pid}')
        find_ths_window()

def ths_prc_hwnd(procname='hexin.exe'):
    global ths_process_hwnd
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
    return ths_process_hwnd

def bytes_16(dec_num, code):

    ascii_char = chr(dec_num)  # 将整数转换为对应的ASCII字符
    codex = ascii_char + str(code)
    # 将Python字符串转换为bytes类型
    bytes_codex = codex.encode('ascii', 'ignore')
    return bytes_codex

def ths_convert_code(code):

    # 上海，深圳股票判断;
    if str(code)[0] == '6':
        # 将16进制数转换为整数
        dec_num = int('11', 16)
        if code in ths_code:
            dec_num = 0x16
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

    elif str(code).startswith('90'):
        # 将16进制数转换为整数
        dec_num = int('12', 16)
        bytes_codex = bytes_16(dec_num, code)
    elif str(code).startswith('20'):
        # 将16进制数转换为整数
        dec_num = int('22', 16)
        bytes_codex = bytes_16(dec_num, code)
    else:
        # 将16进制数转换为整数
        dec_num = int('21', 16)
        bytes_codex = bytes_16(dec_num, code)

    return bytes_codex

def send_code_clipboard(stock_code,retry=True):
    global dfcf_process_hwnd,ahk_process_hwnd,thsweb_process_hwnd
    status = "未找到DC"
    if  dfcf_process_hwnd != 0 and (ahk_process_hwnd != 0 or thsweb_process_hwnd !=0):
        status = f" DC-> 成功"
        print(f"已找到DFCF: {dfcf_process_hwnd} 发送成功")
        pyperclip.copy(stock_code)
        print(f"hwnd:{dfcf_process_hwnd} Stock code {stock_code} copied to clipboard!")
    else:
        if retry:
            dfcf_process_hwnd = get_handle('mainfree.exe')
            ahk_process_hwnd = get_pids_values('AutoHotkey')
            result = find_window_by_title_safe('ths-tdx-web.py')
            if len(result) > 0:
                thsweb_process_hwnd,window_title = result[0]
            status = send_code_clipboard(stock_code,retry=False)

    return status

def send_code_message(code,retry=True):
    global ths_window_handle
    global ths_process_hwnd
    # # 同花顺进程句柄
    # ths_process_hwnd = ths_prc_hwnd()
    # # 用kerne132.VirtualAllocEx在目标进程开辟内存空间(用于存放数据)
    # 在指定进程的虚拟地址空间中保留、提交或更改内存区域的状态。 函数将它分配的内存初始化为零。
    status = "未找到THS"

    if ths_process_hwnd != 0 and ths_window_handle != 0:
        status = f"THS-> 成功"
        argv_address = kernel32.VirtualAllocEx(ths_process_hwnd, 0, 8, VIRTUAL_MEN, FAGE_READWRITE)
        bytes_str = ths_convert_code(code)
        # 用kerne132.WriteProcessMemory在目标进程内存空间写入数据
        kernel32.WriteProcessMemory(ths_process_hwnd, argv_address, bytes_str, 7, None)
    # # 同花顺窗口句柄
        print(f"已找到THS: {ths_window_handle} process: {ths_process_hwnd} 发送成功 bytes_str:{bytes_str}")
        # ths_window_handle = get_handle(exe)
        result = win32api.SendMessage(ths_window_handle, int(1168), 0, argv_address)
    else:
        if retry:
            find_ths_window()
            status = send_code_message(code,retry=False)
    return status

def send_to_tdx(stock_code):
    """发送股票代码到通达信"""
    tdx_state = tdx_var.get()
    ths_state = ths_var.get()
    dfcf_state = dfcf_var.get()
    if not tdx_state and not ths_state and not dfcf_state:
        # root.title(f"股票异动数据监控")
        pass
    else:

        if len(stock_code.split()) == 2:
            stock_code,stock_name = stock_code.split()
        elif not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
            messagebox.showerror("错误", "请输入有效的6位股票代码")
            return

        # 生成股票代码
        generated_code = generate_stock_code(stock_code)

        # 更新状态
        # root.title(f"股票异动数据监控 + 通达信联动 - 正在发送...")

        # 在新线程中执行发送操作，避免UI卡顿
        threading.Thread(target=_send_to_tdx_thread, args=(stock_code, generated_code)).start()

def _send_to_tdx_thread(stock_code, generated_code,retry=True):
    """在线程中执行发送操作"""
    global tdx_window_handle
    tdx_state = tdx_var.get()
    ths_state = ths_var.get()
    dfcf_state = dfcf_var.get()
    status = '成功'
    thsstatus = '成功'
    dfcfstatus = '成功'
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
            # root.after(0, _update_ui_after_send, status)
        if ths_state:
            thsstatus = send_code_message(stock_code)
            print(f"THS send Message posted:{thsstatus}")
            # root.after(3, _update_ui_after_send, status)
            status = f'{status} : {thsstatus}' 
        if dfcf_state:
            dfcfstatus = send_code_clipboard(stock_code)
            print(f"DC Paste:{dfcfstatus}")
            if ths_state:
                status = f'{status} : {thsstatus} : {dfcfstatus}'
            else: 
                status = f'{status} : {dfcfstatus}' 

    except Exception as e:
        status = f"发送失败: {str(e)}"

    # 在主线程中更新UI
    # root.after(0, _update_ui_after_send, status)

def find_tdx_window():
    """查找通达信窗口"""
    # global tdx_window_handle,tdx_pid
    global tdx_window_handle
    # tdx_pid = get_pids('tdxw.exe')
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
    # root.title(f"股票异动数据监控 + 通达信联动 - {status}")


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

def find_ths_window(exe='hexin.exe'):
    global ths_window_handle
    global ths_process_hwnd
    # global ths_pid
    # ths_pid = get_pids('hexin.exe')
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
    if ths_process_hwnd != 0 and ths_window_handle != 0:
        status = True
    else:
        status = False
    return status


# Toolbar
toolbar = tk.Frame(root, bg="#f0f0f0", padx=2, pady=2)
toolbar.pack(fill=tk.X)

# Right frame: Checkbuttons
frame_right = tk.Frame(toolbar, bg="#f0f0f0")
frame_right.pack(side=tk.RIGHT, padx=2, pady=2)

# Variables
tdx_var = tk.BooleanVar(value=True)
ths_var = tk.BooleanVar(value=False)
dfcf_var = tk.BooleanVar(value=False)
uniq_var = tk.BooleanVar(value=False)
sub_var = tk.BooleanVar(value=False)

checkbuttons_info = [
    ("TDX", tdx_var),
    ("THS", ths_var),
    ("DC", dfcf_var),
    ("Uniq", uniq_var),
    ("Sub", sub_var)
]

for text, var in checkbuttons_info:
    cb = tk.Checkbutton(frame_right, text=text, variable=var, command=update_linkage_status,
                        bg="#f0f0f0", font=('Microsoft YaHei', 9),
                        padx=0, pady=0,  # 内部填充设为0
                        bd=0, highlightthickness=0)  # 边框也设为0
    cb.pack(side=tk.LEFT, padx=1)  # 外部间距减小到1像素