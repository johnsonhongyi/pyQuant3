import os
import sys
import time
import asyncio
import threading
import logging
try:
    import pyperclip
except ImportError:
    pyperclip = None

import pandas as pd
from datetime import datetime
from typing import Any, Optional, Union, Callable
try:
    import win32api
    import win32con
except ImportError:
    win32api = win32con = None
from JohnsonUtil import commonTips as cct
import re

logger = logging.getLogger()

def clean_bad_columns(df: pd.DataFrame) -> pd.DataFrame:
    """清理异常列名"""
    bad_cols = [
        c for c in df.columns
        if not isinstance(c, str) or not c.isidentifier()
    ]
    if bad_cols:
        # print("清理异常列:", bad_cols)
        df = df.drop(columns=bad_cols)
    return df

def cross_process_lock(date_str: str, lock_pattern: str = "clean_once_{date}.lock") -> Optional[int]:
    """跨进程锁定"""
    lock = lock_pattern.format(date=date_str)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        return fd
    except FileExistsError:
        return None

# def get_clean_flag_path(today_str: str, ramdisk_dir: str) -> str:
#     """当天清理完成的跨进程标记文件路径"""
#     return os.path.join(
#         ramdisk_dir,
#         f".tdx_last_df.cleaned.{today_str}"
#     )

def get_clean_flag_path(today_str: str, ramdisk_dir: str) -> str:
    ramdisk_dir = normalize_windows_root(ramdisk_dir)
    return os.path.join(
        ramdisk_dir,
        f".tdx_last_df.cleaned.{today_str}"
    )


def cleanup_old_clean_flags(ramdisk_dir: str, keep_days: int = 5) -> None:
    """清理过期的 clean flag 文件"""
    if not os.path.exists(ramdisk_dir):
        return
    today = datetime.today().date()
    for fn in os.listdir(ramdisk_dir):
        if not fn.startswith(".tdx_last_df.cleaned."):
            continue
        try:
            date_str = fn.rsplit(".", 1)[-1]
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if (today - d).days > keep_days:
                os.remove(os.path.join(ramdisk_dir, fn))
        except Exception:
            pass

def normalize_windows_root(path: str) -> str:
    """
    确保 Windows 盘符路径为 G:\\ 形式
    """
    if re.fullmatch(r"[A-Za-z]:", path):
        return path + "\\"
    return os.path.abspath(path)


def clean_expired_tdx_file(logger: Any, g_values: Any, get_trade_date_status_func: Any, 
                          get_today_func: Any, get_now_time_int_func: Any, 
                          get_ramdisk_path_func: Any, ramdisk_dir: str) -> bool:
    """
    每个交易日 08:30–09:15 清理一次 tdx_last_df
    """
    # ① 是否交易日
    if not get_trade_date_status_func():
        return False

    today = get_today_func()
    now_time = get_now_time_int_func()

    # ② 进程内已完成
    if (
        g_values.getkey("tdx.clean.done") is True
        and g_values.getkey("tdx.clean.date") == today
    ):
        return True

    # ③ 时间窗口校验
    if not (cct.start_init_tdx_time  <= now_time <= 915):
        logger.debug(f"[CLEAN_SKIP] {today} now={now_time} 不在清理窗口")
        return False

    fname = get_ramdisk_path_func("tdx_last_df")
    flag_path = get_clean_flag_path(today, ramdisk_dir)

    logger.debug(
        f"[CLEAN_CHECK] pid={os.getpid()} today={today} now={now_time} "
        f"file_exists={os.path.exists(fname)} flag_exists={os.path.exists(flag_path)}"
    )
    # ④ 跨进程：今天已完成
    if os.path.exists(flag_path):
        g_values.setkey("tdx.clean.done", True)
        g_values.setkey("tdx.clean.date", today)
        return True

    # ⑤ 文件不存在 → 直接视为完成
    if not os.path.exists(fname):
        logger.info(f"[CLEAN_DONE] {today} 文件不存在，直接标记完成")
        try:
            open(flag_path, "w").close()
        except Exception as e:
            logger.error(f"[CLEAN_ERR] flag 写入失败: {flag_path}, err={e}")
            return False
        g_values.setkey("tdx.clean.done", True)
        g_values.setkey("tdx.clean.date", today)
        return True

    # ⑥ 真正删除
    try:
        os.remove(fname)
        # MultiIndex_fname = get_ramdisk_path_func("sina_MultiIndex_data")
        # if os.path.exists(MultiIndex_fname):
        #     os.remove(MultiIndex_fname)
        #     logger.info(f"[CLEAN_OK] {today} 同步已清理过期文件: {MultiIndex_fname}")
        
        # sina_data_fname = get_ramdisk_path_func("sina_data")
        # if os.path.exists(sina_data_fname):
        #     os.remove(sina_data_fname)
        #     logger.info(f"[CLEAN_OK] {today} 同步已清理过期文件: {sina_data_fname}")
        logger.info(f"[CLEAN_OK] {today} 已清理过期文件: {fname}")
    except Exception as e:
        logger.error(f"[CLEAN_ERR] 删除失败: {fname}, err={e}")
        return False

    # ⑦ 写入完成标记
    try:
        open(flag_path, "w").close()
        logger.info(f"[CLEAN_FLAG] {today} 清理完成标记已写入")
    except Exception as e:
        logger.error(f"[CLEAN_ERR] flag 写入失败: {flag_path}, err={e}")
        return False

    # ⑧ 同步进程内状态
    g_values.setkey("tdx.clean.done", True)
    g_values.setkey("tdx.clean.date", today)
    return True

def is_tdx_clean_done(ramdisk_dir: str, today: Optional[str] = None, get_today_func: Optional[Any] = None) -> bool:
    """检查今天是否已完成清理"""
    if today is None:
        if get_today_func:
            today = get_today_func()
        else:
            return False
    flag_path = get_clean_flag_path(today, ramdisk_dir)
    return os.path.exists(flag_path)

def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """全面修复重复 index / 重复主键 / 异常残留"""
    if df is None or df.empty:
        return df
    # 1. index 去重
    df = df.loc[~df.index.duplicated(keep='last')]
    # 2. 常见主键去重
    if 'code' in df.columns:
        if 'date' in df.columns:
            df = df.drop_duplicates(subset=['code', 'date'], keep='last')
        else:
            df = df.drop_duplicates(subset=['code'], keep='last')
    # 3. 删除 NA index
    if df.index.isna().any():
        df = df.loc[~df.index.isna()]
    return df

def isDigit(x):
    #re def isdigit()
    try:
        if str(x) == 'nan' or x is None:
            return False
        else:
            float(x)
            return True
    except ValueError:
        return False

# ==============================================================================
# 🐭 [NEW] Mouse Hook Trigger Integration
# ==============================================================================
class MouseClickState:
    __slots__ = ("last_click", "clicks", "double_flag")
    def __init__(self):
        self.last_click = 0.0
        self.clicks = 0
        self.double_flag = False

def trigger_key_copy():
    """执行 ESC (清除干扰) 然后 Ctrl+Ins (更通用的复制)"""
    if not win32api: return
    try:
        # 发送 ESC
        win32api.keybd_event(0x1B, 0, 0, 0)
        win32api.keybd_event(0x1B, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)
        # 发送 Ctrl + Ins
        win32api.keybd_event(0x11, 0, 0, 0) # Ctrl down
        win32api.keybd_event(0x2D, 0, 0, 0) # Ins down
        win32api.keybd_event(0x2D, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(0x11, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception as e:
        logger.error(f"[MouseHook] trigger_key_copy error: {e}")

async def mouse_hook_loop(click_timeout=0.25, double_min=0.05, right_timeout=1.5):
    """
    状态机检测：双击左键后在 1.5s 内抬起右键 -> 触发复制
    """
    if not win32api:
        logger.warning("[MouseHook] win32api not found. Mouse trigger disabled.")
        return

    state = MouseClickState()
    try:
        state_left = win32api.GetKeyState(0x01)
        state_right = win32api.GetKeyState(0x02)
    except Exception:
        return

    while True:
        try:
            a = win32api.GetKeyState(0x01)
            b = win32api.GetKeyState(0x02)
            
            # 1. 左键逻辑：处理双击检测
            if a != state_left:
                state_left = a
                if a >= 0: # Left UP
                    now = time.perf_counter()
                    dt = now - state.last_click
                    if dt > click_timeout:
                        state.clicks = 1
                        state.double_flag = False
                    else:
                        state.clicks += 1
                        if state.clicks == 2 and dt > double_min:
                            state.double_flag = True
                    state.last_click = now
            
            # 2. 右键逻辑：双击后的组合触发
            if b != state_right:
                state_right = b
                if b >= 0: # Right UP
                    now = time.perf_counter()
                    if state.double_flag and (now - state.last_click < right_timeout):
                        logger.info(f"🐭 [MouseHook] Double-Left + Right triggered! Executing Copy...")
                        # 使用 to_thread 执行同步按键模拟，防止阻塞事件循环
                        await asyncio.to_thread(trigger_key_copy)
                    # 无论是否触发，右键抬起均重置双击标志
                    state.double_flag = False
                    state.clicks = 0
            
            await asyncio.sleep(0.005) # 5ms 高频轮询
        except Exception as e:
            logger.error(f"[MouseHook] loop error: {e}")
            await asyncio.sleep(1)

async def get_clipboard_contents(timesleep=0.5, code_startswith=None, keep_clipboard=False):
    """
    异步生成器：监控剪贴板并返回符合条件的股票代码。
    支持在后台线程中运行的 asyncio 任务环境，通过 to_thread 避免剪贴板操作阻塞循环。
    """
    if pyperclip is None:
        logger.error("pyperclip is not installed. Clipboard monitoring disabled.")
        return

    if code_startswith is None:
        # 默认匹配 A股/ETF/北证 (00, 30, 60, 68, 8, 4, 1, 5)
        code_startswith = ('00', '1', '3', '5', '6', '8', '9')
    elif isinstance(code_startswith, str):
        # 兼容 "'00','30'..." 格式
        code_startswith = tuple(x.strip().strip("'").strip('"') for x in code_startswith.split(',') if x.strip())

    last_emit_code = None   # ⭐ 新增
    # last_time = 0
    # 增加微小启动延迟，确保外部信号接收端（UI）已完成初始化绑定
    await asyncio.sleep(0.3)
    
    while True:
        try:
            # 剪贴板操作在 Windows 下是阻塞的且容易冲突，使用 to_thread 提高并发性
            content = await asyncio.to_thread(pyperclip.paste)
            if content:
                text = content.strip()
                # 兼容格式如 "600000 浦发银行"
                parts = text.split()
                if parts:
                    code = parts[0]
                    now = time.time()
                    if len(code) == 6 and isDigit(code) and code.startswith(code_startswith):
                        # 如果代码变更，或者同一个代码在 2 秒后再次拷贝，则触发
                        if code != last_emit_code:
                            yield code
                            last_emit_code = code
                            # 注意：这里不再清空剪贴板，确保用户可以黏贴到其他地方
        except Exception:
            # 捕获剪贴板锁定异常，稍后重试
            await asyncio.sleep(timesleep)
            continue
            
        await asyncio.sleep(timesleep)

def start_clipboard_listener(sender: Any, timesleep: float = 0.5, code_startswith: Any = None, 
                             ignore_func: Optional[Callable[[str], bool]] = None, 
                             on_new_code: Optional[Callable[[str], None]] = None, 
                             keep_clipboard: bool = False,
                             logger=logger) -> threading.Thread:
    """
    在后台线程中启动剪贴板监听，并尝试通过 sender.send(code) 发送代码。
    ignore_func: 接收代码字符串，返回 True 则忽略发送。
    """
    def _run_monitor():
        # 为子线程创建新的事件循环
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        
        async def _task():
            # [NEW] 启动鼠标钩子任务
            asyncio.create_task(mouse_hook_loop())
            
            async for code in get_clipboard_contents(timesleep, code_startswith, keep_clipboard=keep_clipboard):
                try:
                    # 如果提供了外部逻辑检查（如：与 UI 选中代码重复），则忽略
                    if ignore_func and ignore_func(code):
                        logger.debug(f"📋 Clipboard Monitoring: Ignored (Current Selection: {code})")
                        continue
                        
                    if hasattr(sender, 'send'):
                        logger.info(f"📋 Clipboard Monitoring: Sending detected code {code}")
                        sender.send(code)
                    # 新增 UI callback
                    if on_new_code:
                        logger.info(f"📋 Clipboard Monitoring: Sending open_visualizer code {code}")
                        on_new_code(code)
                except Exception as e:
                    # Assuming 'logger' is available in this scope (e.g., imported globally)
                    logger.error(f"ClipboardListener send error: {e}")
        
        new_loop.run_until_complete(_task())

    thread = threading.Thread(target=_run_monitor, daemon=True, name="ClipboardMonitor")
    thread.start()
    return thread

if __name__ == '__main__':
    # from tdx_utils import start_clipboard_listener
    # 假设主类中有 self.sender
    from JohnsonUtil.stock_sender import StockSender
    sender=StockSender()
    print(f'start start_clipboard_listener')
    clipboard_thread = start_clipboard_listener(sender, timesleep=0.8)