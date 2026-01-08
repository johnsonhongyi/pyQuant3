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
    if not (830 <= now_time <= 915):
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
        MultiIndex_fname = get_ramdisk_path_func("sina_MultiIndex_data")
        if os.path.exists(MultiIndex_fname):
            os.remove(MultiIndex_fname)
            logger.info(f"[CLEAN_OK] {today} 同步已清理过期文件: {MultiIndex_fname}")
        logger.info(f"[CLEAN_OK] {today} 已清理过期文件: {fname} : {MultiIndex_fname}")
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

async def get_clipboard_contents(timesleep=0.5, code_startswith=None):
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

    last_code = None
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
                    if len(code) == 6 and isDigit(code) and code.startswith(code_startswith):
                        if code != last_code:
                            yield code
                            last_code = code
        except Exception:
            # 捕获剪贴板锁定异常，稍后重试
            await asyncio.sleep(timesleep)
            continue
            
        await asyncio.sleep(timesleep)

def start_clipboard_listener(sender: Any, timesleep: float = 0.5, code_startswith: Any = None, ignore_func: Optional[Callable[[str], bool]] = None) -> threading.Thread:
    """
    在后台线程中启动剪贴板监听，并尝试通过 sender.send(code) 发送代码。
    ignore_func: 接收代码字符串，返回 True 则忽略发送。
    """
    def _run_monitor():
        # 为子线程创建新的事件循环
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        
        async def _task():
            async for code in get_clipboard_contents(timesleep, code_startswith):
                try:
                    # 如果提供了外部逻辑检查（如：与 UI 选中代码重复），则忽略
                    if ignore_func and ignore_func(code):
                        logger.debug(f"📋 Clipboard Monitoring: Ignored (Current Selection: {code})")
                        continue
                        
                    if hasattr(sender, 'send'):
                        logger.info(f"📋 Clipboard Monitoring: Sending detected code {code}")
                        sender.send(code)
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