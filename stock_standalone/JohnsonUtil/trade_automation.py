# -*- encoding: utf-8 -*-
"""
trade_automation.py
通达信 (TDX) / 同花顺 (THS) 交易终端自动呼出与安全填单引擎 (Lightning Order & Trade Automation)
功能：
1. 查找通达信主窗口 (TdxW_MainFrame_Class / TdxW.exe) 与独立交易进程 (xiadan.exe)；
2. 智能呼出通达信【闪电买入】独立对话框或内置交易买入面板；
3. 精准填入证券代码、买入价格、买入数量，并将焦点置于【买入】按钮；
4. 【安全强约束】绝不自动代点提交，安全等待用户人工点击确认；
5. 提供系统自测自检接口 check_trade_environment()。
"""

import os
import sys
import time
import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GW_HWNDNEXT = 2
GW_CHILD = 5
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
EM_SETSEL = 0x00B1
WM_PASTE = 0x0302
VK_RETURN = 0x0D
VK_TAB = 0x09
BM_CLICK = 0x00F5


def _ensure_desktop():
    """附加到活动输入桌面，确保在所有子进程中均能稳定遍历 GUI 窗口"""
    try:
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def get_window_text(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 511)
    return buf.value


def get_class_name(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetClassNameW(hwnd, buf, 511)
    return buf.value


def force_foreground(hwnd):
    """使用 AttachThreadInput 强行穿透 Windows 焦点防护将窗口置顶前台"""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    try:
        import win32process, win32gui, win32con, win32api
        fore_hwnd = win32gui.GetForegroundWindow()
        fore_tid, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
        cur_tid = win32api.GetCurrentThreadId()
        target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
        
        if cur_tid != target_tid:
            try: win32process.AttachThreadInput(cur_tid, target_tid, True)
            except Exception: pass
        if fore_hwnd and fore_tid != target_tid:
            try: win32process.AttachThreadInput(fore_tid, target_tid, True)
            except Exception: pass
            
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        win32gui.BringWindowToTop(hwnd)
        
        if cur_tid != target_tid:
            try: win32process.AttachThreadInput(cur_tid, target_tid, False)
            except Exception: pass
        if fore_hwnd and fore_tid != target_tid:
            try: win32process.AttachThreadInput(fore_tid, target_tid, False)
            except Exception: pass
        return True
    except Exception:
        try:
            user32.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False


class TradeAutomationEngine:
    """
    通达信/同花顺交易终端自动化挂单引擎
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._last_call_time = 0.0

    def check_trade_environment(self) -> dict:
        """
        [自测自检] 检查当前系统交易环境就绪状态
        """
        _ensure_desktop()
        tdx_main_pids = []
        xiadan_pids = []
        ths_pids = []

        for p in psutil.process_iter(['pid', 'name']):
            try:
                name = (p.info.get('name') or '').lower()
                if 'tdxw' in name:
                    tdx_main_pids.append(p.info['pid'])
                elif 'xiadan' in name or 'trade' in name:
                    xiadan_pids.append(p.info['pid'])
                elif 'hexin' in name:
                    ths_pids.append(p.info['pid'])
            except Exception:
                pass

        tdx_hwnd = self.find_tdx_main_window()
        lightning_hwnd = self.find_lightning_buy_window()
        xiadan_hwnd = self.find_xiadan_main_window()

        status = {
            "tdx_running": len(tdx_main_pids) > 0 or tdx_hwnd > 0,
            "xiadan_running": len(xiadan_pids) > 0 or xiadan_hwnd > 0,
            "ths_running": len(ths_pids) > 0,
            "tdx_main_hwnd": tdx_hwnd,
            "lightning_buy_hwnd": lightning_hwnd,
            "xiadan_main_hwnd": xiadan_hwnd,
            "ready": tdx_hwnd > 0 or lightning_hwnd > 0 or xiadan_hwnd > 0
        }
        return status

    def find_tdx_main_window(self) -> int:
        """
        查找通达信主窗口句柄
        """
        _ensure_desktop()
        # 1. 优先通过类名精确查找
        h = user32.FindWindowW("TdxW_MainFrame_Class", None)
        if h and user32.IsWindow(h):
            return h

        # 2. 遍历顶级窗口查找
        found_h = 0
        hwnd = user32.GetTopWindow(None)
        while hwnd:
            cls = get_class_name(hwnd)
            title = get_window_text(hwnd)
            if "TdxW_MainFrame_Class" in cls or ("通达信" in title and "行情" in title):
                found_h = hwnd
                break
            hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
        return found_h

    def find_xiadan_main_window(self) -> int:
        """
        查找通达信独立交易进程 (xiadan.exe) 的主窗口句柄
        """
        _ensure_desktop()
        found_h = 0
        hwnd = user32.GetTopWindow(None)
        while hwnd:
            cls = get_class_name(hwnd)
            title = get_window_text(hwnd)
            if "网上股票交易系统" in title or (cls.startswith("Afx:") and ("交易" in title or "买入" in title)):
                found_h = hwnd
                break
            hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
        return found_h

    def find_lightning_buy_window(self) -> int:
        """
        查找已打开的【闪电买入】对话框或买入窗口
        """
        _ensure_desktop()
        # 1. 标题精确匹配 "闪电买入"
        h = user32.FindWindowW("#32770", "闪电买入")
        if h and user32.IsWindow(h):
            return h
        h = user32.FindWindowW(None, "闪电买入")
        if h and user32.IsWindow(h):
            return h

        # 2. 遍历所有顶级对话框
        found_h = 0
        hwnd = user32.GetTopWindow(None)
        while hwnd:
            cls = get_class_name(hwnd)
            title = get_window_text(hwnd)
            if "闪电买入" in title or (cls == "#32770" and ("买入" in title or "委托" in title)):
                found_h = hwnd
                break
            hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
        return found_h

    def open_lightning_buy_dialog(self, code: str) -> int:
        """
        向通达信发送指令呼出【闪电买入】窗口
        """
        _ensure_desktop()
        # 1. 先检查是否已经打开
        h = self.find_lightning_buy_window()
        if h:
            force_foreground(h)
            return h

        # 2. 查找通达信主窗口并强行置顶前台
        tdx_h = self.find_tdx_main_window()
        if not tdx_h:
            # 降级尝试查找 xiadan.exe 交易窗口
            xd_h = self.find_xiadan_main_window()
            if xd_h:
                force_foreground(xd_h)
                return xd_h
            return 0

        try:
            force_foreground(tdx_h)
            time.sleep(0.08)

            # 3. 发送通达信内置键盘指令: 数字键 2 1 + Enter (通达信官方买入快捷键)
            import win32api
            import win32con
            win32api.keybd_event(ord('2'), 0, 0, 0)
            win32api.keybd_event(ord('2'), 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('1'), 0, 0, 0)
            win32api.keybd_event(ord('1'), 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception:
            pass

        # 4. 等待窗口弹出 (轮询 800ms)
        for _ in range(8):
            time.sleep(0.1)
            h = self.find_lightning_buy_window()
            if h:
                force_foreground(h)
                return h
        return 0

    def populate_order_details(
        self,
        hwnd: int,
        code: str,
        price: float = 0.0,
        shares: int = 1000
    ) -> bool:
        """
        向交易对话框精准填入证券代码、买入价格与数量，并将焦点停在【买入】按钮
        """
        if not hwnd or not user32.IsWindow(hwnd):
            return False

        _ensure_desktop()
        force_foreground(hwnd)

        # 遍历该窗口下的所有 Edit 与 Button 控件
        edits = []
        buttons = []

        def enum_children(parent):
            ch = user32.GetWindow(parent, GW_CHILD)
            while ch:
                cc = get_class_name(ch)
                ct = get_window_text(ch)
                if cc == "Edit":
                    edits.append(ch)
                elif cc == "Button":
                    buttons.append((ch, ct))
                elif cc == "#32770":
                    enum_children(ch)
                ch = user32.GetWindow(ch, GW_HWNDNEXT)

        enum_children(hwnd)

        # 1. 填入价格与数量
        price_str = f"{price:.2f}" if price > 0 else ""
        shares_str = str(int(shares)) if shares > 0 else "1000"

        if len(edits) >= 2:
            try:
                if len(edits) >= 3:
                    if code:
                        user32.SendMessageW(edits[0], WM_SETTEXT, 0, code)
                    if price_str:
                        user32.SendMessageW(edits[1], WM_SETTEXT, 0, price_str)
                    if shares_str:
                        user32.SendMessageW(edits[2], WM_SETTEXT, 0, shares_str)
                elif len(edits) == 2:
                    if price_str:
                        user32.SendMessageW(edits[0], WM_SETTEXT, 0, price_str)
                    if shares_str:
                        user32.SendMessageW(edits[1], WM_SETTEXT, 0, shares_str)
            except Exception:
                pass

        # 2. 将焦点置于【买入】按钮 (安全等待确认，绝不自动代点提交！)
        for b_hwnd, b_text in buttons:
            if "买入" in b_text or "买" in b_text:
                try:
                    user32.SetFocus(b_hwnd)
                except Exception:
                    pass
                break

        return True

    def execute_lightning_order(
        self,
        code: str,
        name: str = "",
        target_price: float = 0.0,
        shares: int = 1000,
        strategy_tag: str = ""
    ) -> dict:
        """
        完整的一键挂单执行流水线
        """
        code_str = str(code).strip().zfill(6)
        
        # 1. 剪贴板复制备份 (格式: 代码 价格)
        try:
            import pyperclip
            clip_str = f"{code_str} {target_price:.2f}" if target_price > 0 else code_str
            pyperclip.copy(clip_str)
        except Exception:
            pass

        # 2. 尝试获取或呼出交易窗口
        trade_hwnd = self.find_lightning_buy_window()
        if not trade_hwnd:
            trade_hwnd = self.open_lightning_buy_dialog(code_str)

        # 3. 填入参数并聚焦确认
        populated = False
        if trade_hwnd:
            populated = self.populate_order_details(trade_hwnd, code_str, target_price, shares)

        return {
            "ok": True,
            "trade_hwnd": trade_hwnd,
            "populated": populated,
            "code": code_str,
            "name": name,
            "price": target_price,
            "shares": shares,
            "msg": f"[{code_str} {name}] 委托价:{target_price:.2f}元 数量:{shares}股 -> " +
                   ("已载入交易终端，请核对并确认【买入】" if trade_hwnd else "已激活通达信并复制指令到剪贴板，请核对确认")
        }
