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
import queue
import time

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

        # --- 极限性能优化组件 ---
        self._task_queue = queue.Queue(maxsize=1)  # 状态覆盖队列
        self._latest_task = None
        self._last_exec_ts = 0
        self._last_ui_cb = 0
        self._last_clip = None
        self._running = True

        # 缓存消息 ID (核心优化：避免高频系统调用)
        self._UWM_STOCK = win32api.RegisterWindowMessage('stock')

        # 启动单实例工作线程 (核心优化：杜绝线程风暴)
        self._worker = threading.Thread(target=self._worker_loop, name="StockSenderWorker", daemon=True)
        self._worker.start()

    def close(self):
        """[NEW] 停止工作线程并清理资源"""
        self._running = False
        # 投递一个空任务以唤醒可能处于空闲等待状态的逻辑（虽然当前是 time.sleep 轮询）
        try:
            if self._task_queue.full():
                self._task_queue.get_nowait()
            self._task_queue.put_nowait(None)
        except:
            pass

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

    def reload(self):
        """
        重新查找各交易软件窗口句柄
        兼容 Tk BooleanVar / bool
        """

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
    # ----------------- 核心分发与工作循环 ----------------- #
    def send(self, stock_code, auto=False):
        """
        投递一个发送意图 (State Overwrite)
        :param auto: 是否为后台自动触发 (信号联动)
        """
        if not stock_code: return

        # [ROOT-FIX] 核心变更：转发到 LinkageManagerProxy (Proxy)
        if os.environ.get("IN_LINKAGE_PROCESS_MARK") != "1":
            try:
                # 在物理执行路径上提取状态快照，防止多线程环境下访问 Tkinter 变量崩溃
                flags = {
                    'tdx': self._get_flag(self.tdx_var),
                    'ths': self._get_flag(self.ths_var),
                    'dfcf': self._get_flag(self.dfcf_var)
                }
                from linkage_service import get_link_manager
                # 投递到独立的后台进程进行节流与重叠执行
                get_link_manager().push(stock_code, flags=flags, auto=auto)
                return
            except Exception:
                pass

        # [FIX] 在物理执行路径（或降级路径）上提取状态快照，防止多线程环境下访问 Tkinter 变量崩溃
        flags = {
            'tdx': self._get_flag(self.tdx_var),
            'ths': self._get_flag(self.ths_var),
            'dfcf': self._get_flag(self.dfcf_var)
        }

        # 状态覆盖：如果队列满了，丢弃旧任务，确保时效性
        try:
            if self._task_queue.full():
                self._task_queue.get_nowait()
            self._task_queue.put_nowait((stock_code, flags, auto))
        except:
            pass

    def _worker_loop(self):
        """
        单 Worker 线程循环：负责调度、物理节流与 UI 回调控制
        """
        while self._running:
            try:
                # 1. 尽可能清空队列，直到获取最新的一项意图 (State Overwrite)
                task = None
                while True:
                    try:
                        task = self._task_queue.get_nowait()
                    except queue.Empty:
                        break
                
                if task:
                    self._latest_task = task

                if self._latest_task:
                    now = time.time()
                    code, flags, auto = self._latest_task
                    
                    # 2. 物理节流
                    # ⭐ [UPGRADE] 针对后台自动信号 (auto=True) 实施更严格的防抖 (2s)
                    # 这样既能保证同步，又能防止高频信号洪水导致软件卡死
                    throttle = 2.0 if auto else 0.05
                    
                    if now - self._last_exec_ts >= throttle:
                        self._do_send(code, flags, auto=auto)
                        self._latest_task = None
                        self._last_exec_ts = now
                
                time.sleep(0.01)  # 降低 CPU 占用

            except Exception as e:
                # 不抛出异常，记录日志并继续
                print(f"❌ StockSender Worker Error: {e}")
                time.sleep(0.5)

    def _do_send(self, stock_code, flags, auto=False):
        """执行具体的物理发送动作并汇总状态"""
        tdx_enabled = flags.get('tdx', False)
        ths_enabled = flags.get('ths', False)
        dfcf_enabled = flags.get('dfcf', False)

        # 1. 执行物理发送
        if tdx_enabled: self.send_to_tdx(stock_code)
        else: self.tdx_status = "TDX-> 未选中"

        if ths_enabled: self.send_to_ths(stock_code)
        else: self.ths_status = "THS-> 未选中"

        if dfcf_enabled: self.send_to_dfcf(stock_code)
        else: self.dfcf_status = "DC-> 未选中"

        # 2. 汇总状态
        status_dict = {
            "TDX": self.tdx_status,
            "THS": self.ths_status,
            "DC": self.dfcf_status
        }

        # 3. 回调 UI (加入 100ms 频率保护)
        if self.callback:
            now = time.time()
            if now - self._last_ui_cb > 0.1:
                try:
                    self.callback(status_dict)
                    self._last_ui_cb = now
                except: pass

    def _safe_clip(self, stock_code):
        """安全且带去重的剪切板写入"""
        if stock_code == self._last_clip:
            return
            
        try:
            pyperclip.copy(stock_code)
            self._last_clip = stock_code
        except:
            # 记录失败但不中断流程
            self._last_clip = None 

    # ----------------- 加载 THS 股票列表 ----------------- #
    def load_ths_code(self):
        if os.path.exists(self.code_file_name):
            with open(self.code_file_name, "r", encoding="utf-8") as f:
                codelist = json.load(f).get('stock', [])
                self.ths_code = [co for co in codelist]
            print("Loaded:", len(self.ths_code))
    # ----------------- 工具函数 ----------------- #
    # @staticmethod
    # def get_pids(pname):
    #     """
    #     [FIXED] 安全地获取指定进程名的所有 PID
    #     使用方案 3 (process_iter cache)：原子性更高，防止扫描期间进程消失导致 NoSuchProcess 崩溃
    #     """
    #     pids = []
    #     try:
    #         # 仅请求 pid 和 name 属性，psutil 内部会处理大部分 NoSuchProcess 异常
    #         for p in psutil.process_iter(['pid', 'name']):
    #             try:
    #                 info = p.info
    #                 if info and info['name'] and pname.lower() in info['name'].lower():
    #                     pids.append(info['pid'])
    #             except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
    #                 continue
    #     except Exception as e:
    #         print(f"⚠️ get_pids error for {pname}: {e}")
    #     return pids

    @staticmethod
    def get_pids(pname, cache={}, ts=[0]):
        """
        高性能进程查找（长缓存优化版）
        - 10秒缓存
        - 降低 psutil 调用频率
        - UI友好
        """
        if not pname:
            return []
        now = time.time()
        # ⛔ 缓存命中（10秒）
        if now - ts[0] < 10.0:
            return cache.get(pname, [])
        pname = pname.lower().strip()
        pids = []
        try:
            for p in psutil.process_iter(['pid', 'name']):
                name = p.info.get('name')
                if not name:
                    continue

                if pname in name.lower():
                    pids.append(p.info['pid'])

        except Exception:
            pass

        cache[pname] = pids
        ts[0] = now

        return pids

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
        """
        [UPGRADE] 优化 hexin.exe 进程查找逻辑，使用高性能 attrs 过滤
        """
        try:
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    info = p.info
                    if info and info['name'] and info['name'].lower() == "hexin.exe":
                        pid = info['pid']
                        self.ths_process_hwnd = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
                        return self.ths_process_hwnd
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            print(f"⚠️ ths_prc_hwnd scan error: {e}")
        return 0

    def find_ths_window(self):
        self.ths_process_hwnd = self.ths_prc_hwnd()
        self.ths_window_handle = self.get_handle_by_name("hexin.exe")

    def find_dfcf_handle(self):
        self.dfcf_process_hwnd = self.get_handle_by_name("mainfree.exe")
        self.ahk_process_hwnd = self.get_pids("AutoHotkey")
        print(f'dfcf_process_hwnd : {self.dfcf_process_hwnd}  ahk_process_hwnd :{self.ahk_process_hwnd }' )

    # ----------------- 代码转换 ----------------- #
    def bytes_16(self, dec_num, code):
        ascii_char = chr(dec_num)
        codex = ascii_char + str(code)
        return codex.encode('ascii', 'ignore')

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
            bytes_codex = self.bytes_16(dec_num, code)
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
        if self.dfcf_process_hwnd and self.ahk_process_hwnd:
            self._safe_clip(stock_code)
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

    def send_to_tdx(self, stock_code, message_type='stock'):
        if not self.tdx_window_handle or not win32gui.IsWindow(self.tdx_window_handle):
            self.find_tdx_window() # 句柄失效则重连

        if self.tdx_window_handle:
            try:
                # 转换代码格式为 TDX 内部识别格式 (如 6xxxxxx 或 7xxxxxx)
                if isinstance(stock_code, dict):
                    stock_code = stock_code.get('content', '').strip()
                
                if len(stock_code) == 6:
                    codex = stock_code
                    if str(message_type) == 'stock':
                        if stock_code[0] in ['0', '3', '1']:
                            codex = '6' + stock_code
                        elif stock_code.startswith('999'):
                            codex = '7' + stock_code
                        elif stock_code[0] in ['6', '5']:
                            codex = '7' + stock_code
                        else:
                            codex = '4' + stock_code
                    
                    # 核心优化：不再使用广播，精准投递给句柄
                    win32gui.PostMessage(self.tdx_window_handle, self._UWM_STOCK, int(codex), 0)
                    self.tdx_status = "TDX-> 成功"
                else:
                    self.tdx_status = "TDX-> 代码非法"
            except Exception as e:
                self.tdx_status = f"TDX-> 异常: {e}"
                # 出错时尝试在下次任务前清空句柄强制重连
                self.tdx_window_handle = 0
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
