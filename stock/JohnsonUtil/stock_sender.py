# stock_sender.py
import threading
import ctypes
from ctypes import wintypes
import win32gui
import win32api
import win32process
import psutil
import pyperclip
import json
import os
import re
# import LoggerFactory 

FAGE_READWRITE = 0x04
PROCESS_ALL_ACCESS = 0x001F0FFF
VIRTUAL_MEN = (0x1000 | 0x2000)
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_void_p)
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

# class StockSender:
#     def __init__(self, tdx_var, ths_var, dfcf_var, base_dir=None):
#         self.tdx_var = tdx_var
#         self.ths_var = ths_var
#         self.dfcf_var = dfcf_var

#         self.tdx_window_handle = 0
#         self.ths_window_handle = 0
#         self.ths_process_hwnd = 0
#         self.dfcf_process_hwnd = 0
#         self.ahk_process_hwnd = 0
#         self.thsweb_process_hwnd = 0

#         self.tdx_status = ""
#         self.ths_status = ""
#         self.dfcf_status = ""

#         self.base_dir = base_dir or os.getcwd()
#         self.code_file_name = os.path.join(self.base_dir, "code_ths_other.json")
#         self.ths_code = []

#         self.load_ths_code()
#         self.find_tdx_window()
#         self.find_ths_window()
#         self.find_dfcf_handle()
class StockSender:
    def __init__(self, tdx_var, ths_var, dfcf_var, base_dir=None, callback=None):
        self.tdx_var = tdx_var
        self.ths_var = ths_var
        self.dfcf_var = dfcf_var

        self.callback = callback  # 回调函数，用于更新 UI

        # 句柄初始化
        self.tdx_window_handle = 0
        self.ths_window_handle = 0
        self.ths_process_hwnd = 0
        self.dfcf_process_hwnd = 0
        self.ahk_process_hwnd = 0
        self.thsweb_process_hwnd = 0

        # 状态
        self.tdx_status = ""
        self.ths_status = ""
        self.dfcf_status = ""

        # 股票代码列表
        self.base_dir = base_dir or os.getcwd()
        self.code_file_name = os.path.join(self.base_dir, "code_ths_other.json")
        self.ths_code = []
        self.load_ths_code()

        # 查找窗口
        self.find_tdx_window()
        self.find_ths_window()
        self.find_dfcf_handle()

    # ----------------- 统一发送 ----------------- #
    def send(self, stock_code):
        threading.Thread(target=self._send_thread, args=(stock_code,)).start()

    def _send_thread(self, stock_code):
        if self.tdx_var.get():
            self.send_to_tdx(stock_code)
        else:
            self.tdx_status = "TDX-> 未选中"

        if self.ths_var.get():
            self.send_to_ths(stock_code)
        else:
            self.ths_status = "THS-> 未选中"

        if self.dfcf_var.get():
            self.send_to_dfcf(stock_code)
        else:
            self.dfcf_status = "DC-> 未选中"

        status_dict = {
            "TDX": self.tdx_status,
            "THS": self.ths_status,
            "DC": self.dfcf_status
        }

        # 回调 UI 更新状态栏
        if self.callback:
            self.callback(status_dict)

    # ----------------- 加载 THS 股票列表 ----------------- #
    def load_ths_code(self):
        if os.path.exists(self.code_file_name):
            with open(self.code_file_name, "r", encoding="utf-8") as f:
                codelist = json.load(f).get('stock', [])
                self.ths_code = [co for co in codelist]

    # ----------------- 工具函数 ----------------- #
    @staticmethod
    def get_pids(pname):
        return [p.pid for p in psutil.process_iter() if pname.lower() in p.name().lower()]

    @staticmethod
    def get_handle_by_pid(pid):
        handles = []
        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    handles.append(hwnd)
            return True
        win32gui.EnumWindows(callback, None)
        return handles[0] if handles else 0

    @staticmethod
    def get_handle_by_name(pname):
        pids = StockSender.get_pids(pname)
        for pid in pids:
            hwnd = StockSender.get_handle_by_pid(pid)
            if hwnd:
                return hwnd
        return 0

    # ----------------- 查找窗口 ----------------- #
    def find_tdx_window(self):
        def enum_callback(hwnd, lparam):
            title_buf = ctypes.create_unicode_buffer(256)
            GetWindowTextW(hwnd, title_buf, 255)
            cls_buf = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, cls_buf, 255)
            if "TdxW_MainFrame_Class" in cls_buf.value:
                self.tdx_window_handle = hwnd
                return False
            return True
        enum_proc = WNDENUMPROC(enum_callback)
        user32.EnumWindows(enum_proc, 0)

    def ths_prc_hwnd(self):
        for pid in psutil.pids():
            try:
                if psutil.Process(pid).name().lower() == "hexin.exe":
                    self.ths_process_hwnd = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
                    return self.ths_process_hwnd
            except psutil.NoSuchProcess:
                continue
        return 0

    def find_ths_window(self):
        self.ths_process_hwnd = self.ths_prc_hwnd()
        self.ths_window_handle = self.get_handle_by_name("hexin.exe")

    def find_dfcf_handle(self):
        self.dfcf_process_hwnd = self.get_handle_by_name("mainfree.exe")
        self.ahk_process_hwnd = self.get_handle_by_name("AutoHotkey")
        print(f'dfcf_process_hwnd : {self.dfcf_process_hwnd}  ahk_process_hwnd :{self.ahk_process_hwnd }' )
        # LoggerFactory.info(f'dfcf_process_hwnd : {self.dfcf_process_hwnd}  ahk_process_hwnd :{self.ahk_process_hwnd }' )

    # ----------------- 代码转换 ----------------- #
    def bytes_16(self, dec_num, code):
        ascii_char = chr(dec_num)
        codex = ascii_char + str(code)
        return codex.encode('ascii', 'ignore')

    def ths_convert_code(self, code):
        c = str(code)
        dec_num = 0x21
        if c[0] == '6':
            dec_num = 0x16 if code in self.ths_code else 0x16
        elif c.startswith('11'):
            dec_num = 0x13
        elif c.startswith('12'):
            dec_num = 0x23
        elif c.startswith('15'):
            dec_num = 0x24
        elif c.startswith('90'):
            dec_num = 0x12
        elif c.startswith('20'):
            dec_num = 0x22
        return self.bytes_16(dec_num, code)

    # ----------------- 发送函数 ----------------- #
    def send_to_dfcf(self, stock_code):
        if self.dfcf_process_hwnd and (self.ahk_process_hwnd or self.thsweb_process_hwnd):
            pyperclip.copy(stock_code)
            self.dfcf_status = f"DC-> 成功"
        else:
            self.dfcf_status = "未找到DC"
        return self.dfcf_status

    def send_to_ths(self, stock_code):
        if self.ths_process_hwnd and self.ths_window_handle:
            argv_address = kernel32.VirtualAllocEx(self.ths_process_hwnd, 0, 8, VIRTUAL_MEN, FAGE_READWRITE)
            bytes_str = self.ths_convert_code(stock_code)
            kernel32.WriteProcessMemory(self.ths_process_hwnd, argv_address, bytes_str, len(bytes_str), None)
            win32api.SendMessage(self.ths_window_handle, int(1168), 0, argv_address)
            self.ths_status = "THS-> 成功"
        else:
            self.ths_status = "未找到THS"
        return self.ths_status

    def send_to_tdx(self, stock_code):
        UWM_STOCK = RegisterWindowMessageW("Stock")
        if self.tdx_window_handle:
            try:
                message_code = int(stock_code)
            except ValueError:
                message_code = 0
            PostMessageW(self.tdx_window_handle, UWM_STOCK, message_code, 2)
            self.tdx_status = "TDX-> 成功"
        else:
            self.tdx_status = "未找到TDX"
        return self.tdx_status

    # ----------------- 统一发送 ----------------- #
    # def send(self, stock_code):
    #     threading.Thread(target=self._send_thread, args=(stock_code,)).start()

    # def _send_thread(self, stock_code):
    #     if self.tdx_var.get():
    #         self.send_to_tdx(stock_code)
    #     if self.ths_var.get():
    #         self.send_to_ths(stock_code)
    #     if self.dfcf_var.get():
    #         self.send_to_dfcf(stock_code)
    #     print(f"发送状态 => TDX:{self.tdx_status}, THS:{self.ths_status}, DC:{self.dfcf_status}")
