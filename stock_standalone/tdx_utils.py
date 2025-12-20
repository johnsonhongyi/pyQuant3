# -*- coding:utf-8 -*-
import os
import pandas as pd
from datetime import datetime
from typing import Any, Optional, Union

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

def get_clean_flag_path(today_str: str, ramdisk_dir: str) -> str:
    """当天清理完成的跨进程标记文件路径"""
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
            logger.info(f"[CLEAN_OK] {today} 已清理过期文件: {MultiIndex_fname}")
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
