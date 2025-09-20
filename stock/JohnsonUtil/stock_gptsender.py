# stock_gptsender.py
# -*- coding:utf-8 -*-
import os
import threading
import ctypes
import win32gui
import win32api
import win32process
import pyperclip
import psutil
import json

# ---------------- Windows API 初始化 ---------------- #
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
FAGE_READWRITE = 0x04
PROCESS_ALL_ACCESS = 0x001F0FFF
VIRTUAL_MEM = (0x1000 | 0x2000)

class StockSender:
    def __init__(self, callback=None, base_dir=None):
        self.callback = callback  # UI回调
        self.base_dir = base_dir or os.getcwd()

        self.tdx_enabled = True
        self.ths_enabled = False
        self.dfcf_enabled = False

        self.tdx_window_handle = 0
        self.ths_window_handle = 0
        self.ths_process_hwnd = 0
        self.dfcf_process_hwnd = 0
        self.ahk_process_hwnd = 0
        self.thsweb_process_hwnd = 0
        self.ths_code = []

        # 初始化
        self.load_ths_code()
        self.find_tdx_window()
        self.find_ths_window()
        self.find_dfcf_handle()

    # ---------------- 状态控制 ---------------- #
    def set_states(self, tdx=True, ths=False, dfcf=False):
        self.tdx_enabled = tdx
        self.ths_enabled = ths
        self.dfcf_enabled = dfcf

    # ---------------- 加载 THS 股票代码 ---------------- #
    def load_ths_code(self):
        code_file = os.path.join(self.base_dir, "code_ths_other.json")
        if os.path.exists(code_file):
            with open(code_file, "r", encoding="utf-8") as f:
                self.ths_code = json.load(f).get('stock', [])

    # ---------------- 主发送接口 ---------------- #
    def send(self, stock_code):
        threading.Thread(target=self._send_thread, args=(stock_code,), daemon=True).start()

    def _send_thread(self, stock_code):
        status = {"TDX":"未发送", "THS":"未发送", "DC":"未发送"}

        if self.tdx_enabled:
            status["TDX"] = self.send_to_tdx(stock_code)
        if self.ths_enabled:
            status["THS"] = self.send_to_ths(stock_code)
        if self.dfcf_enabled:
            status["DC"] = self.send_to_dfcf(stock_code)

        if self.callback:
            self.callback(status)

    # ---------------- 发送到通达信 ---------------- #
    def send_to_tdx(self, stock_code):
        try:
            UWM_STOCK = user32.RegisterWindowMessageW("Stock")
            if self.tdx_window_handle != 0:
                try:
                    msg_code = int(self.generate_stock_code(stock_code))
                except ValueError:
                    msg_code = 0
                ret = user32.PostMessageW(self.tdx_window_handle, UWM_STOCK, msg_code, 2)
                return "TDX->成功" if ret else "TDX->失败"
            else:
                self.find_tdx_window()
                return "TDX->窗口未找到"
        except Exception as e:
            return f"TDX->错误:{e}"

    # ---------------- 发送到同花顺 ---------------- #
    def send_to_ths(self, stock_code):
        try:
            if self.ths_process_hwnd != 0 and self.ths_window_handle != 0:
                argv_address = kernel32.VirtualAllocEx(self.ths_process_hwnd, 0, 8, VIRTUAL_MEM, FAGE_READWRITE)
                bytes_str = self.ths_convert_code(stock_code)
                kernel32.WriteProcessMemory(self.ths_process_hwnd, argv_address, bytes_str, len(bytes_str), None)
                win32api.SendMessage(self.ths_window_handle, 1168, 0, argv_address)
                return "THS->成功"
            else:
                self.find_ths_window()
                return "THS->窗口未找到"
        except Exception as e:
            return f"THS->错误:{e}"

    # ---------------- 发送到大智慧 ---------------- #
    def send_to_dfcf(self, stock_code):
        try:
            if self.dfcf_process_hwnd != 0 and (self.ahk_process_hwnd != 0 or self.thsweb_process_hwnd != 0):
                pyperclip.copy(stock_code)
                return "DC->成功"
            else:
                self.find_dfcf_handle()
                return "DC->未找到"
        except Exception as e:
            return f"DC->错误:{e}"

    # ---------------- 辅助函数 ---------------- #
    def generate_stock_code(self, stock_code):
        if stock_code.startswith(('6','5')):
            return f"7{stock_code}"
        elif stock_code.startswith(('0','3','1')):
            return f"6{stock_code}"
        else:
            return f"4{stock_code}"

    def ths_convert_code(self, code):
        dec_num = 0x16 if code in self.ths_code else 0x11
        return (chr(dec_num) + code).encode('ascii', 'ignore')

    # ---------------- 窗口查找 ---------------- #
    def find_tdx_window(self):
        def callback(hwnd, lparam):
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, buf, 255)
            if "TdxW_MainFrame_Class" in buf.value:
                self.tdx_window_handle = hwnd
                return False
            return True
        user32.EnumWindows(WNDENUMPROC(callback), 0)

    def find_ths_window(self, exe='hexin.exe'):
        self.ths_process_hwnd = self.get_ths_process_handle()
        self.ths_window_handle = self.get_handle_by_exe(exe)

    def find_dfcf_handle(self):
        self.dfcf_process_hwnd = self.get_handle_by_exe('mainfree.exe')

    def get_ths_process_handle(self):
        for pid in psutil.pids():
            try:
                if psutil.Process(pid).name().lower() == 'hexin.exe':
                    return kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
            except psutil.NoSuchProcess:
                continue
        return 0

    def get_handle_by_exe(self, exe_name):
        handles = []

        def callback(hwnd, lparam):
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    if psutil.Process(pid).name().lower() == exe_name.lower():
                        handles.append(hwnd)
                except Exception:
                    pass
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)
        return handles[0] if handles else 0
