# stock_sender.py
import threading
import ctypes
from ctypes import wintypes
import win32gui
import win32api
import win32con
import win32process
import psutil
import pyperclip
import json
import os
# import re
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
# PostMessageW = user32.PostMessageW
# PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
# PostMessageW.restype = ctypes.c_int
# RegisterWindowMessageW = user32.RegisterWindowMessageW
# RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
# RegisterWindowMessageW.restype = ctypes.c_uint

class StockSender:
    def __init__(self, tdx_var=True, ths_var=True, dfcf_var=False, base_dir=None, callback=None):
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
        # self.thsweb_process_hwnd = 0

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
        # if self.tdx_var.get()
        self.find_tdx_window()
        # if self.ths_var.get()
        self.find_ths_window()
        # if self.dfcf_var.get():
        self.find_dfcf_handle()

    def _get_flag(self, var):
        """
        兼容 tk.BooleanVar / bool
        """
        if hasattr(var, "get"):
            try:
                return bool(var.get())
            except Exception:
                return False
        return bool(var)

    # def reload_old(self):
    #     # 句柄初始化
    #     # print(f'reload process_hwnd')
    #     # print(f'self.tdx_var : {self.tdx_var.get()} self.ths_var : {self.ths_var.get()} self.dfcf_var : {self.dfcf_var.get()}')
    #     if  self.tdx_var.get():
    #         self.tdx_window_handle = 0
    #         self.find_tdx_window()
    #         print(f'reload  tdx_window_handle: {self.tdx_window_handle}')
    #     if  self.ths_var.get():
    #         self.ths_process_hwnd = 0
    #         self.ths_window_handle = 0
    #         self.find_ths_window()
    #         print(f'reload ths_process_hwnd: {self.ths_process_hwnd} ths_window_handle :{self.ths_window_handle}')

    #     if  self.dfcf_var.get():
    #         self.dfcf_process_hwnd = 0
    #         self.ahk_process_hwnd = 0
    #         # self.thsweb_process_hwnd = 0
    #         self.find_dfcf_handle()
    #         print(f'reload dfcf_process_hwnd: {self.dfcf_process_hwnd} ahk_process_hwnd: {self.ahk_process_hwnd}')

    def reload(self):
        """
        重新查找各交易软件窗口句柄
        兼容 Tk BooleanVar / bool
        """

        # print('reload process_hwnd')
        # print(f'tdx:{self._get_flag(self.tdx_var)} '
        #       f'ths:{self._get_flag(self.ths_var)} '
        #       f'dfcf:{self._get_flag(self.dfcf_var)}')

        if self._get_flag(self.tdx_var):
            self.tdx_window_handle = 0
            self.find_tdx_window()
            print(f'reload tdx_window_handle: {self.tdx_window_handle}')

        if self._get_flag(self.ths_var):
            self.ths_process_hwnd = 0
            self.ths_window_handle = 0
            self.find_ths_window()
            print(
                f'reload ths_process_hwnd: {self.ths_process_hwnd} '
                f'ths_window_handle: {self.ths_window_handle}'
            )

        if self._get_flag(self.dfcf_var):
            self.dfcf_process_hwnd = 0
            self.ahk_process_hwnd = 0
            # self.thsweb_process_hwnd = 0
            self.find_dfcf_handle()
            print(
                f'reload dfcf_process_hwnd: {self.dfcf_process_hwnd} '
                f'ahk_process_hwnd: {self.ahk_process_hwnd}'
            )

        # 查找窗口
    # ----------------- 统一发送 ----------------- #
    def send(self, stock_code):
        # print(f'send :{stock_code}')
        threading.Thread(target=self._send_thread, args=(stock_code,)).start()

    def _send_thread(self, stock_code):
        """
        发送股票代码到各客户端
        兼容 tk.BooleanVar / bool
        """

        # === TDX ===
        if self._get_flag(self.tdx_var):
            self.send_to_tdx(stock_code)
            self.tdx_status = f"TDX-> 已发送 {stock_code}"
        else:
            self.tdx_status = "TDX-> 未选中"

        # === THS ===
        if self._get_flag(self.ths_var):
            self.send_to_ths(stock_code)
            self.ths_status = f"THS-> 已发送 {stock_code}"
        else:
            self.ths_status = "THS-> 未选中"

        # === 东方财富 ===
        if self._get_flag(self.dfcf_var):
            self.send_to_dfcf(stock_code)
            self.dfcf_status = f"DC-> 已发送 {stock_code}"
        else:
            self.dfcf_status = "DC-> 未选中"

        status_dict = {
            "TDX": self.tdx_status,
            "THS": self.ths_status,
            "DC": self.dfcf_status
        }

        # === 回调 UI ===
        if self.callback:
            self.callback(status_dict)

    # def _send_thread_old(self, stock_code):
    #     # print(f"TDX:{self.tdx_var.get()}, THS:{self.ths_var.get()}, DC:{self.dfcf_var.get()}")
    #     if self.tdx_var.get():
    #         self.send_to_tdx(stock_code)
    #     else:
    #         self.tdx_status = "TDX-> 未选中"

    #     if self.ths_var.get():
    #         self.send_to_ths(stock_code)
    #     else:
    #         self.ths_status = "THS-> 未选中"

    #     if self.dfcf_var.get():
    #         self.send_to_dfcf(stock_code)
    #     else:
    #         self.dfcf_status = "DC-> 未选中"

    #     status_dict = {
    #         "TDX": self.tdx_status,
    #         "THS": self.ths_status,
    #         "DC": self.dfcf_status
    #     }

    #     # 回调 UI 更新状态栏
    #     if self.callback:
    #         self.callback(status_dict)

    # ----------------- 加载 THS 股票列表 ----------------- #
    def load_ths_code(self):
        if os.path.exists(self.code_file_name):
            with open(self.code_file_name, "r", encoding="utf-8") as f:
                codelist = json.load(f).get('stock', [])
                self.ths_code = [co for co in codelist]
            print("Loaded:", len(self.ths_code))
    # ----------------- 工具函数 ----------------- #
    @staticmethod
    def get_pids(pname):
        return [p.pid for p in psutil.process_iter() if pname.lower() in p.name().lower()]

    # @staticmethod    
    # def get_pids_values(pname):
    #     # print(pname)
    #     # find AutoHotkeyU64.exe
    #     pids = 0
    #     for proc in psutil.process_iter():
    #         if pname in proc.name():
    #             # pids.append(proc.pid)
    #             pids = proc.pid
    #     return pids
    
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
        self.ahk_process_hwnd = self.get_pids("AutoHotkey")
        print(f'dfcf_process_hwnd : {self.dfcf_process_hwnd}  ahk_process_hwnd :{self.ahk_process_hwnd }' )
        # LoggerFactory.info(f'dfcf_process_hwnd : {self.dfcf_process_hwnd}  ahk_process_hwnd :{self.ahk_process_hwnd }' )

    # ----------------- 代码转换 ----------------- #
    def bytes_16(self, dec_num, code):
        ascii_char = chr(dec_num)
        codex = ascii_char + str(code)
        return codex.encode('ascii', 'ignore')

    # def ths_convert_code(self, code):
    #     c = str(code)
    #     dec_num = 0x21
    #     if c[0] == '6':
    #         dec_num = 0x16 if code in self.ths_code else 0x16
    #     elif c.startswith('11'):
    #         dec_num = 0x13
    #     elif c.startswith('12'):
    #         dec_num = 0x23
    #     elif c.startswith('15'):
    #         dec_num = 0x24
    #     elif c.startswith('90'):
    #         dec_num = 0x12
    #     elif c.startswith('20'):
    #         dec_num = 0x22
    #     return self.bytes_16(dec_num, code)
    def ths_convert_code(self,code):

        # 上海，深圳股票判断;
        if str(code)[0] == '6':
            # 将16进制数转换为整数
            dec_num = int('11', 16)
            if code in self.ths_code:
                dec_num = 0x16
            bytes_codex = self.bytes_16(dec_num, code)
        # 11开头的可转债
        elif str(code).startswith('11'):
            # 将16进制数转换为整数
            dec_num = int('13', 16)
            bytes_codex = bself.ytes_16(dec_num, code)
        # 12开头的可转债
        elif str(code).startswith('12'):
            # 将16进制数转换为整数
            dec_num = int('23', 16)
            bytes_codex = self.bytes_16(dec_num, code)
        # 12开头的可转债
        elif str(code).startswith('15'):
            # 将16进制数转换为整数
            dec_num = int('24', 16)
            bytes_codex = self.bytes_16(dec_num, code)

        elif str(code).startswith('90'):
            # 将16进制数转换为整数
            dec_num = int('12', 16)
            bytes_codex = self.bytes_16(dec_num, code)
        elif str(code).startswith('20'):
            # 将16进制数转换为整数
            dec_num = int('22', 16)
            bytes_codex = self.bytes_16(dec_num, code)
        else:
            # 将16进制数转换为整数
            dec_num = int('21', 16)
            bytes_codex = self.bytes_16(dec_num, code)

        return bytes_codex

    # ----------------- 发送函数 ----------------- #
    def send_to_dfcf(self, stock_code):
        # print(self.dfcf_process_hwnd , self.ahk_process_hwnd)
        if self.dfcf_process_hwnd and self.ahk_process_hwnd:
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

    def send_to_tdx(self,stock_code,message_type='stock'):
        if self.tdx_window_handle:
            try:
                message_code = int(stock_code)
            except ValueError:
                message_code = 0
            if isinstance(stock_code, dict):
                stock_code = stock_code['content']
                stock_code = stock_code.strip()
            if len(stock_code) == 6:
                codex = int(stock_code)
                if str(message_type) == 'stock':
                    if str(stock_code)[0] in ['0','3','1']:
                        codex = '6' + str(stock_code)
                    elif str(stock_code)[0] in ['6','5']:
                        codex = '7' + str(stock_code)
                    # elif str(stock_code)[0] == '9':
                    #     codex = '2' + str(stock_code)
                    else:
                        codex = '4' + str(stock_code)
                else:
                    codex = int(stock_code)
                UWM_STOCK = win32api.RegisterWindowMessage('stock')
                # print(win32con.HWND_BROADCAST,UWM_STOCK,str(codex))
                #系统广播
                win32gui.PostMessage( win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)
            self.tdx_status = "TDX-> 成功"
        else:
            self.tdx_status = "未找到TDX"
        return self.tdx_status
    # def send_to_tdx(self, stock_code):
    #     UWM_STOCK = RegisterWindowMessageW("Stock")
    #     if self.tdx_window_handle:
    #         try:
    #             message_code = int(stock_code)
    #         except ValueError:
    #             message_code = 0
    #         PostMessageW(self.tdx_window_handle, UWM_STOCK, message_code, 2)
    #         self.tdx_status = "TDX-> 成功"
    #     else:
    #         self.tdx_status = "未找到TDX"
    #     return self.tdx_status

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
