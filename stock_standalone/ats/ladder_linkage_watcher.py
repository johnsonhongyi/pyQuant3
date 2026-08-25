# -*- coding: utf-8 -*-
"""
ATS LadderLinkageWatcher
【连板天梯 / 涨停采集工具】跨进程上下键联动与右键注入守护线程

核心特性:
1. 0.00% CPU 占用: 持久复用跨进程内存空间与句柄，非前台时智能挂起。
2. 精准指纹识别: 准确识别【涨停采集工具共享版.exe】(WTWindow 且具备 SysListView32 ID=140 与 Edit ID=280 特征)。
3. 双重触发通道: 键盘导航键(↑/↓/PgUp/PgDn/Home/End)即时响应 + 鼠标点击选行变动同步。
4. 右键菜单注入: 采用【硬件级鼠标点击原生选行机制】，0 手工坐标换算，彻底免疫任何 DPI 缩放与滚动条偏移，鼠标点哪就 100% 选中哪。
5. 防回跳锁定机制: 右键点击时原子锁定目标标的与选行，屏蔽异步旧状态干扰，彻底消除选行跳变。
"""

import time
import struct
import ctypes
from ctypes import wintypes
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("ATS.LadderLinkageWatcher")

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# 键盘与鼠标虚拟键码
VK_RBUTTON = 0x02 # 鼠标右键
VK_PRIOR   = 0x21 # Page Up
VK_NEXT    = 0x22 # Page Down
VK_END     = 0x23 # End
VK_HOME    = 0x24 # Home
VK_UP      = 0x26 # Up
VK_DOWN    = 0x28 # Down

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

KEY_WATCH_LIST = [VK_UP, VK_DOWN, VK_PRIOR, VK_NEXT, VK_HOME, VK_END]


class LadderLinkageWatcher(QThread):
    """
    连板天梯跨进程上下键联动与右键注入后台服务 (QThread)
    """
    # 联动信号：(股票代码, 行号, 触发源/状态)
    code_linked = pyqtSignal(str, int, str)
    # 右键菜单信号：(股票代码, 股票名称, 屏幕X, 屏幕Y)
    right_click_requested = pyqtSignal(str, str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        
        self.target_pid = 0
        self.main_hwnd = 0
        self.lv_hwnd = 0
        self.tdx_hwnd = 0
        
        self.h_proc = None
        self.remote_buf = 0
        
        self.last_selected_row = -1
        self.last_sent_code = None
        self.uwm_stock = user32.RegisterWindowMessageW("stock")
        self.last_scan_time = 0
        
        # 右键按键状态跟踪与防跳变抑制锁
        self._rbutton_was_down = False
        self._last_rclick_ts = 0
        self._suppress_link_until = 0.0

    def _attach_desktop(self):
        hdesk_in = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk_in:
            user32.SetThreadDesktop(hdesk_in)
        return hdesk_in

    def _cleanup_remote_proc(self):
        if self.remote_buf and self.h_proc:
            try:
                kernel32.VirtualFreeEx(self.h_proc, self.remote_buf, 0, 0x8000)
            except Exception:
                pass
            self.remote_buf = 0
        if self.h_proc:
            try:
                kernel32.CloseHandle(self.h_proc)
            except Exception:
                pass
            self.h_proc = None

    def find_windows(self) -> bool:
        """低频查找目标窗口句柄与进程（仅在初始化或句柄失效时触发）"""
        hdesk_in = self._attach_desktop()
        
        # 1. 查找通达信主窗口 (TdxW_MainFrame_Class)
        found_tdx = [0]
        def tdx_cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if "TdxW_MainFrame_Class" in cls_buf.value:
                found_tdx[0] = hwnd
                return False
            return True
            
        # 2. 查找涨停采集工具主窗口 (包含 ID=140 SysListView32 和 ID=280 Edit 的 WTWindow)
        found_target = {'main': 0, 'lv': 0, 'pid': 0}
        def target_cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value == "WTWindow":
                children = {}
                def child_cb(chwnd, _):
                    ccls = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(chwnd, ccls, 256)
                    cid = user32.GetWindowLongW(chwnd, -12)
                    children[cid] = (chwnd, ccls.value)
                    return True
                user32.EnumChildWindows(hwnd, ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(child_cb), 0)
                
                # 涨停采集工具窗口特征
                if 140 in children and children[140][1] == "SysListView32" and 280 in children:
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    found_target['main'] = hwnd
                    found_target['lv'] = children[140][0]
                    found_target['pid'] = pid.value
                    return False
            return True
            
        enum_func = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        if hdesk_in:
            user32.EnumDesktopWindows(hdesk_in, enum_func(tdx_cb), 0)
            user32.EnumDesktopWindows(hdesk_in, enum_func(target_cb), 0)
        else:
            user32.EnumWindows(enum_func(tdx_cb), 0)
            user32.EnumWindows(enum_func(target_cb), 0)
            
        self.tdx_hwnd = found_tdx[0]
        
        # 目标发生变化时重建内存缓冲区
        if found_target['pid'] != self.target_pid or found_target['lv'] != self.lv_hwnd:
            self._cleanup_remote_proc()
            self.target_pid = found_target['pid']
            self.main_hwnd = found_target['main']
            self.lv_hwnd = found_target['lv']
            
            if self.target_pid:
                self.h_proc = kernel32.OpenProcess(0x1F0FFF, False, self.target_pid)
                if self.h_proc:
                    self.remote_buf = kernel32.VirtualAllocEx(self.h_proc, 0, 4096, 0x1000 | 0x2000, 0x04)
        
        self.last_scan_time = time.time()
        return bool(self.main_hwnd and self.lv_hwnd and self.tdx_hwnd)

    def _get_cell_text(self, row: int, col: int) -> str:
        """读取指定单元格文本"""
        if not self.lv_hwnd or not self.h_proc or not self.remote_buf or row < 0:
            return ""
        text_ptr = self.remote_buf + 512
        lvitem_bytes = struct.pack("<IIIIII", 0x0001, row, col, 0, 0, text_ptr) + struct.pack("<I", 256)
        written = ctypes.c_size_t()
        kernel32.WriteProcessMemory(self.h_proc, self.remote_buf, lvitem_bytes, len(lvitem_bytes), ctypes.byref(written))
        user32.SendMessageW(self.lv_hwnd, 0x102D, row, self.remote_buf) # LVM_GETITEMTEXTA
        read_buf = ctypes.create_string_buffer(256)
        kernel32.ReadProcessMemory(self.h_proc, text_ptr, read_buf, 256, ctypes.byref(written))
        return read_buf.value.decode('gbk', errors='ignore').strip()

    def get_selected_stock(self):
        """跨进程读取 SysListView32 当前选中的股票代码与行号"""
        if not self.lv_hwnd or not self.h_proc or not self.remote_buf:
            return None, -1
            
        # LVM_GETNEXTITEM = 0x100C, LVNI_SELECTED = 0x0002
        sel_idx = user32.SendMessageW(self.lv_hwnd, 0x100C, -1, 0x0002)
        if sel_idx < 0:
            sel_idx = user32.SendMessageW(self.lv_hwnd, 0x100C, -1, 0x0001)  # LVNI_FOCUSED
            
        if sel_idx < 0:
            return None, -1
            
        raw_code = self._get_cell_text(sel_idx, 1)
        code = ''.join([c for c in raw_code if c.isdigit()])
        if len(code) == 6:
            return code, sel_idx
        return None, sel_idx

    def send_to_tdx(self, stock_code: str) -> bool:
        """向通达信投递股票代码切换消息"""
        if not self.tdx_hwnd or not stock_code:
            return False
            
        if stock_code[0] in ['0', '3', '1']:
            codex = int('6' + stock_code)
        elif stock_code.startswith('999') or stock_code[0] in ['6', '5']:
            codex = int('7' + stock_code)
        else:
            codex = int('4' + stock_code)
            
        res = user32.PostMessageW(self.tdx_hwnd, self.uwm_stock, codex, 0)
        return bool(res)

    def run(self):
        self._running = True
        logger.info("[LadderLinkageWatcher] 连板天梯上下键联动与右键注入守护线程已启动")
        
        self.find_windows()
        
        while self._running:
            try:
                now = time.time()
                
                # 检查窗口句柄是否有效（低频，每 3 秒检测一次）
                if not (self.main_hwnd and user32.IsWindow(self.main_hwnd) and self.tdx_hwnd and user32.IsWindow(self.tdx_hwnd)):
                    if now - self.last_scan_time > 3.0:
                        self.find_windows()
                    time.sleep(0.5)
                    continue
                    
                # 检查前台活动窗口
                fg_hwnd = user32.GetForegroundWindow()
                is_target_active = (fg_hwnd == self.main_hwnd or user32.IsChild(self.main_hwnd, fg_hwnd))
                
                if not is_target_active:
                    # 连板天梯不在前台，休眠挂起，0% CPU
                    time.sleep(0.1)
                    continue

                # ── 1. 鼠标右键点击拦截与硬件级精准选行注入 ──
                rbutton_down = bool(user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)
                if rbutton_down and not self._rbutton_was_down:
                    if now - self._last_rclick_ts > 0.25: # 250ms 防抖
                        pt = wintypes.POINT()
                        user32.GetCursorPos(ctypes.byref(pt))
                        
                        # 检查鼠标光标是否落在 ListView 区域内
                        pt_hwnd = user32.WindowFromPoint(pt)
                        if pt_hwnd == self.lv_hwnd or user32.IsChild(self.lv_hwnd, pt_hwnd):
                            # 🚀【核心机制】：在鼠标光标处触发一次微秒级原生左键点击，让易语言 ListView 原生选行与高亮！
                            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            time.sleep(0.02) # 20ms 等待原生高亮选行完成
                            
                            code, sel_idx = self.get_selected_stock()
                            if code:
                                name = self._get_cell_text(sel_idx, 2)
                                self._last_rclick_ts = now
                                self.last_selected_row = sel_idx
                                self.last_sent_code = code
                                self._suppress_link_until = now + 0.6 # 锁定防回跳
                                
                                # 同步联动通达信
                                self.send_to_tdx(code)
                                self.code_linked.emit(code, sel_idx + 1, "右键点击")
                                # 发射右键菜单请求 (使用物理屏幕坐标)
                                self.right_click_requested.emit(code, name, pt.x, pt.y)
                self._rbutton_was_down = rbutton_down

                # 如果处于右键防跳变保护期，跳过普通的轮询选行检测
                if now < self._suppress_link_until:
                    time.sleep(0.02)
                    continue

                # ── 2. 键盘导航键(↑/↓/PgUp/PgDn/Home/End)拦截与联动 ──
                key_pressed = False
                for vk in KEY_WATCH_LIST:
                    if user32.GetAsyncKeyState(vk) & 0x8000:
                        key_pressed = True
                        break
                        
                if key_pressed:
                    time.sleep(0.015) # 给 ListView 15ms 完成内部选行更新
                    code, row = self.get_selected_stock()
                    if code and (row != self.last_selected_row or code != self.last_sent_code):
                        self.last_selected_row = row
                        self.last_sent_code = code
                        ok = self.send_to_tdx(code)
                        self.code_linked.emit(code, row + 1, "键盘翻页")
                else:
                    # 鼠标左键点击选行变动同步
                    code, row = self.get_selected_stock()
                    if code and row != self.last_selected_row:
                        self.last_selected_row = row
                        self.last_sent_code = code
                        ok = self.send_to_tdx(code)
                        self.code_linked.emit(code, row + 1, "鼠标选行")
                        
                time.sleep(0.02)
                
            except Exception as e:
                time.sleep(1.0)
                
        self._cleanup_remote_proc()
        logger.info("[LadderLinkageWatcher] 连板天梯上下键联动与右键注入守护线程已退出")

    def stop(self):
        """优雅停止线程"""
        self._running = False
        self.wait(1000)
