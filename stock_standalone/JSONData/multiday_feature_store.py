# -*- coding: utf-8 -*-
"""
JSONData/multiday_feature_store.py
全市场收盘精确换手率等多日缺失特征自动化持久化与初始化挂载引擎 (SSOT)

核心特性:
1. 扁平单表存储: (code, date, ratio, vol_ratio)，物理体积极小 (~1.2MB)，无 MultiIndex 碎片；
2. 动态滑动窗口: 自动根据 cct.compute_lastdays (如 9 天) 截断并淘汰老旧历史；
3. 幂等安全去重: 以 (code, date) 为主键去重，重跑或多次触发不膨胀；
4. 倒排宽表重塑: 盘前/初始化时微秒级重塑为 code -> ratio1 ~ ratio{N}，并由日内单例 TTL 缓存托管；
5. 优雅安全降级: 任何异常静默自愈并记录日志，绝不抛出未捕获异常中断主交易与监控管道。
"""

import os
import sys
import time
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
import numpy as np

# 日志初始化
try:
    from JohnsonUtil import LoggerFactory
    logger = LoggerFactory.getLogger('MultiDayFeatureStore')
except Exception:
    import logging
    logger = logging.getLogger('MultiDayFeatureStore')

try:
    from JohnsonUtil import commonTips as cct
except Exception:
    cct = None

# 表名常量
HDF5_TABLE_NAME = 'daily_multiday_ratio'
DEFAULT_MAX_DAYS = 9

# 日内全局单例宽表与字典缓存与线程安全锁
_CACHE_LOCK = threading.RLock()
_MULTIDAY_WIDE_CACHE: Optional[pd.DataFrame] = None
_MULTIDAY_DICT_CACHE: Optional[Dict[str, dict]] = None
_CACHE_DATE: str = ""
_CACHE_DAYS: int = 0


def get_multiday_store_path(custom_path: str = None) -> str:
    """获取 HDF5 存储路径: 优先对齐 cct.get_ramdisk_path 系统规范"""
    if custom_path:
        if os.path.isabs(custom_path):
            return custom_path
        if cct and hasattr(cct, 'get_ramdisk_path'):
            try:
                return cct.get_ramdisk_path(custom_path)
            except Exception:
                pass
        return os.path.abspath(custom_path)

    if cct and hasattr(cct, 'get_ramdisk_path'):
        try:
            return cct.get_ramdisk_path('tdx_last_features.h5')
        except Exception:
            pass

    target_dir = cct.get_base_path() if (cct and hasattr(cct, 'get_base_path')) else os.getcwd()
    return os.path.join(target_dir, 'tdx_last_features.h5')


def clear_multiday_cache():
    """手动清空/重置日内宽表与字典缓存"""
    global _MULTIDAY_WIDE_CACHE, _MULTIDAY_DICT_CACHE, _CACHE_DATE, _CACHE_DAYS
    with _CACHE_LOCK:
        _MULTIDAY_WIDE_CACHE = None
        _MULTIDAY_DICT_CACHE = None
        _CACHE_DATE = ""
        _CACHE_DAYS = 0
    logger.debug("MultiDay feature store cache cleared.")


def archive_daily_features(
    df_today: pd.DataFrame,
    max_days: Optional[int] = None,
    date_str: Optional[str] = None,
    store_path: Optional[str] = None
) -> bool:
    """
    每日收盘后持久化收割全市场官方精确换手率与量比数据:
    1. 提取 df_today 中的 code, ratio, vol_ratio (或 volume_ratio)；
    2. 加载已有扁平单表，基于 (code, date) 合并去重；
    3. 按交易日排序，保留最新的 max_days 天 (默认 cct.compute_lastdays, 如 9 天)；
    4. 原子写回 HDF5 扁平表并重置宽表缓存。
    """
    if df_today is None or df_today.empty:
        logger.warning("archive_daily_features: input df_today is None or empty, skip.")
        return False

    try:
        is_test_env = bool(store_path and ('test' in str(store_path).lower() or 'temp' in str(store_path).lower()))

        # 1. 确定日期与交易日合法性守卫
        if not date_str:
            is_trade_day = cct.get_trade_date_status() if (cct and hasattr(cct, 'get_trade_date_status')) else True
            if not is_trade_day:
                last_trade = cct.get_last_trade_date() if (cct and hasattr(cct, 'get_last_trade_date')) else None
                date_str = str(last_trade) if last_trade else datetime.now().strftime('%Y-%m-%d')
                logger.info(f"archive_daily_features: 当前为非交易日，自动对齐最近有效交易日: {date_str}")
            else:
                now_int = cct.get_now_time_int() if (cct and hasattr(cct, 'get_now_time_int')) else 1530
                if now_int < 1502 and not is_test_env:
                    logger.warning(f"archive_daily_features: 当前时间 {now_int} < 1502 尚未完全收盘结算出清，禁止将中间态数据作为多日收盘特征归档！")
                    return False
                date_str = str(cct.get_today()) if (cct and hasattr(cct, 'get_today')) else datetime.now().strftime('%Y-%m-%d')
        else:
            if cct and hasattr(cct, 'get_day_istrade_date') and not is_test_env:
                if not cct.get_day_istrade_date(date_str):
                    last_trade = cct.get_last_trade_date()
                    if last_trade:
                        logger.warning(f"archive_daily_features: 传入日期 {date_str} 为非交易日，自动纠偏为真实交易日 {last_trade}")
                        date_str = str(last_trade)

        if max_days is None or max_days <= 0:
            max_days = int(getattr(cct, 'compute_lastdays', DEFAULT_MAX_DAYS)) if cct else DEFAULT_MAX_DAYS

        h5_path = get_multiday_store_path(store_path)

        # 2. 从 df_today 中提取紧凑切片
        df_src = df_today.copy()
        if 'code' not in df_src.columns:
            if df_src.index.name == 'code' or (len(df_src) > 0 and str(df_src.index[0]).isdigit() and len(str(df_src.index[0])) == 6):
                df_src = df_src.reset_index()
                if 'index' in df_src.columns and 'code' not in df_src.columns:
                    df_src = df_src.rename(columns={'index': 'code'})

        if 'code' not in df_src.columns:
            logger.error("archive_daily_features: cannot find 'code' column or index in df_today.")
            return False

        # 智能查找 ratio 列与 vol_ratio 列
        ratio_col = None
        for col in ['ratio', 'turnover', 'turnover_rate', '换手率']:
            if col in df_src.columns:
                ratio_col = col
                break

        vol_ratio_col = None
        for col in ['vol_ratio', 'volume_ratio', 'vr', '量比']:
            if col in df_src.columns:
                vol_ratio_col = col
                break

        if ratio_col is None:
            logger.warning("archive_daily_features: neither 'ratio' nor 'turnover' found in df_today, skipping archive.")
            return False

        r_check = pd.to_numeric(df_src[ratio_col], errors='coerce').fillna(0.0)
        if len(r_check) > 100 and (r_check > 0).mean() < 0.02 and not is_test_env:
            logger.warning("archive_daily_features: 传入的 ratio 列非零数据占比不足 2%，疑似异常脏数据，拒绝持久化覆盖！")
            return False

        if vol_ratio_col is None:
            df_src['vol_ratio'] = 1.0
            vol_ratio_col = 'vol_ratio'

        # 规范化代码格式 (6位纯数字字符串)
        df_src['code'] = df_src['code'].astype(str).str.strip().str.zfill(6)
        valid_mask = df_src['code'].str.isdigit() & (df_src['code'].str.len() == 6)
        df_src = df_src[valid_mask]

        if df_src.empty:
            logger.warning("archive_daily_features: no valid 6-digit stock codes found.")
            return False

        # 构造今日扁平记录
        df_new = pd.DataFrame({
            'code': df_src['code'].values,
            'date': date_str,
            'ratio': pd.to_numeric(df_src[ratio_col], errors='coerce').fillna(0.0).astype(np.float64).round(2).values,
            'vol_ratio': pd.to_numeric(df_src[vol_ratio_col], errors='coerce').fillna(1.0).astype(np.float64).round(2).values
        })

        # 3. 读取已有 HDF5 历史数据
        from JSONData import tdx_hdf5_api as h5a
        df_existing = pd.DataFrame()
        try:
            with h5a.SafeHDFStore(h5_path, mode='r') as store:
                if store is not None and '/' + HDF5_TABLE_NAME in store.keys():
                    df_existing = store.get(HDF5_TABLE_NAME)
        except Exception as read_err:
            logger.debug(f"archive_daily_features: reading existing store: {read_err}")
            df_existing = pd.DataFrame()

        # 4. 防早盘低质数据倒退覆盖与去重合并
        if df_existing is not None and not df_existing.empty:
            req_cols = ['code', 'date', 'ratio', 'vol_ratio']
            for c in req_cols:
                if c not in df_existing.columns:
                    df_existing[c] = 0.0

            # 🛡️ 防倒退校验：如果库中已有该 date_str，但新传入的数据均值明显低于已有数据（如新传入的是未收盘早盘数据），拒绝覆盖
            if date_str in df_existing['date'].values:
                sub_old = df_existing[df_existing['date'] == date_str]
                old_ratio_mean = sub_old['ratio'].mean()
                new_ratio_mean = df_new['ratio'].mean()
                if len(sub_old) > 500 and old_ratio_mean > 0.5 and new_ratio_mean < old_ratio_mean * 0.7:
                    logger.warning(
                        f"archive_daily_features: 新数据换手率均值 ({new_ratio_mean:.2f}) 显著低于库中已有数据 ({old_ratio_mean:.2f})，"
                        f"疑似早盘或残缺快照，拒绝覆盖已有优质收盘数据！"
                    )
                    return False

            df_combined = pd.concat([df_existing[req_cols], df_new[req_cols]], ignore_index=True)
            df_combined = df_combined.drop_duplicates(subset=['code', 'date'], keep='last')
        else:
            df_combined = df_new

        # 5. 滑动窗口修剪：剔除非交易日并仅保留最新 max_days 天
        if cct and hasattr(cct, 'get_day_istrade_date') and not is_test_env:
            valid_dates_set = {d for d in df_combined['date'].unique() if cct.get_day_istrade_date(d)}
            if valid_dates_set:
                df_combined = df_combined[df_combined['date'].isin(valid_dates_set)].copy()

        unique_dates_asc = sorted(df_combined['date'].unique())
        if len(unique_dates_asc) > max_days:
            keep_dates = set(unique_dates_asc[-max_days:])
            df_trimmed = df_combined[df_combined['date'].isin(keep_dates)].copy()
            logger.info(f"archive_daily_features: trimmed {len(unique_dates_asc)} dates to latest {max_days} dates ({sorted(keep_dates)[0]} ~ {sorted(keep_dates)[-1]}).")
        else:
            df_trimmed = df_combined.copy()

        # 6. 原子写回 HDF5
        with h5a.SafeHDFStore(h5_path, mode='a') as store:
            if store is not None:
                store.put(HDF5_TABLE_NAME, df_trimmed, format='table', data_columns=['code', 'date'])
            else:
                logger.error(f"archive_daily_features: failed to open SafeHDFStore at {h5_path}")
                return False

        # 7. 刷新内存单例缓存
        clear_multiday_cache()
        logger.info(f"✅ archive_daily_features OK: archived {len(df_new)} stocks for {date_str}, total rows={len(df_trimmed)}, days={df_trimmed['date'].nunique()}")
        return True

    except Exception as e:
        logger.error(f"archive_daily_features exception: {e}", exc_info=True)
        return False


def get_multiday_features_wide(
    max_days: Optional[int] = None,
    force_reload: bool = False,
    store_path: Optional[str] = None
) -> pd.DataFrame:
    """
    盘前初始化与特征注入时获取重塑后的多日特征宽表:
    返回 DataFrame:
      index: code (6位股票代码)
      columns: ratio1, ratio2, ... ratio{N}, vol_ratio1, vol_ratio2, ... vol_ratio{N}
      (ratio1 为最新一天/昨日换手率，ratio2 为前天换手率，依此类推)
    具备日内全局单例 TTL 内存缓存，单日内高频调用耗时 0 毫秒。
    """
    global _MULTIDAY_WIDE_CACHE, _CACHE_DATE

    today_str = datetime.now().strftime('%Y-%m-%d')
    if max_days is None or max_days <= 0:
        max_days = int(getattr(cct, 'compute_lastdays', DEFAULT_MAX_DAYS)) if cct else DEFAULT_MAX_DAYS

    # 1. 优先命中日内单例内存缓存
    with _CACHE_LOCK:
        if not force_reload and _MULTIDAY_WIDE_CACHE is not None and _CACHE_DATE == today_str:
            return _MULTIDAY_WIDE_CACHE

    # 2. 从 HDF5 读出扁平单表
    h5_path = get_multiday_store_path(store_path)

    try:
        from JSONData import tdx_hdf5_api as h5a
        df_flat = pd.DataFrame()
        with h5a.SafeHDFStore(h5_path, mode='r') as store:
            if store is not None and '/' + HDF5_TABLE_NAME in store.keys():
                df_flat = store.get(HDF5_TABLE_NAME)

        if df_flat is None or df_flat.empty:
            return pd.DataFrame()

        # 3. 执行高性能 Pivot 倒排重塑
        # 严格按真实有效交易日降序排列: unique_dates[0] 为最新真实交易日 -> ratio1, unique_dates[1] -> ratio2...
        all_dates = df_flat['date'].unique()
        is_test_env = bool(store_path and ('test' in str(store_path).lower() or 'temp' in str(store_path).lower()))
        if cct and hasattr(cct, 'get_day_istrade_date') and not is_test_env:
            valid_dates = [d for d in all_dates if cct.get_day_istrade_date(d)]
        else:
            valid_dates = list(all_dates)

        unique_dates_desc = sorted(valid_dates, reverse=True)[:max_days]
        if not unique_dates_desc:
            return pd.DataFrame()

        # 过滤仅包含目标日期切片
        df_slice = df_flat[df_flat['date'].isin(set(unique_dates_desc))]

        # 重塑 ratio
        p_ratio = df_slice.pivot(index='code', columns='date', values='ratio')
        ratio_cols = {d: f'ratio{i}' for i, d in enumerate(unique_dates_desc, start=1)}
        valid_date_cols = [d for d in unique_dates_desc if d in p_ratio.columns]
        wide_ratio = p_ratio[valid_date_cols].rename(columns=ratio_cols)

        # 重塑 vol_ratio
        p_vol = df_slice.pivot(index='code', columns='date', values='vol_ratio')
        vol_cols = {d: f'vol_ratio{i}' for i, d in enumerate(unique_dates_desc, start=1)}
        valid_vol_cols = [d for d in unique_dates_desc if d in p_vol.columns]
        wide_vol = p_vol[valid_vol_cols].rename(columns=vol_cols)

        # 缺失值平滑处理 (以 0.0 与 1.0 填充)
        wide_ratio = wide_ratio.fillna(0.0)
        wide_vol = wide_vol.fillna(1.0)

        # 补齐未满 max_days 时的列 (优雅降级，防止 KeyError)
        for i in range(1, max_days + 1):
            rc = f'ratio{i}'
            vc = f'vol_ratio{i}'
            if rc not in wide_ratio.columns:
                wide_ratio[rc] = wide_ratio.iloc[:, -1] if not wide_ratio.empty else 0.0
            if vc not in wide_vol.columns:
                wide_vol[vc] = wide_vol.iloc[:, -1] if not wide_vol.empty else 1.0

        # 合并宽表
        wide_df = pd.concat([wide_ratio, wide_vol], axis=1)

        # 4. 存入内存单例缓存
        with _CACHE_LOCK:
            _MULTIDAY_WIDE_CACHE = wide_df
            _CACHE_DATE = today_str

        logger.debug(f"get_multiday_features_wide: successfully built wide table with shape {wide_df.shape} for {len(unique_dates_desc)} days.")
        return wide_df

    except Exception as e:
        logger.debug(f"get_multiday_features_wide store read/parse: {e}")
        return pd.DataFrame()


def get_multiday_features_dict(
    max_days: Optional[int] = None,
    force_reload: bool = False,
    store_path: Optional[str] = None
) -> Dict[str, dict]:
    """
    单例共享内存极速字典缓存 (Singleton Shared Memory Dict Cache):
    返回 {code: {'ratio1': 3.5, 'vol_ratio1': 1.2, ...}}
    纯 Python dict O(1) 纳秒级查找，专为全市场选股高频循环优化，
    循环外部一次获取，循环内部极速纳秒级注入，杜绝每只个股重复初始化。
    """
    global _MULTIDAY_DICT_CACHE, _CACHE_DATE, _CACHE_DAYS

    today_str = datetime.now().strftime('%Y-%m-%d')
    if max_days is None or max_days <= 0:
        max_days = int(getattr(cct, 'compute_lastdays', DEFAULT_MAX_DAYS)) if cct else DEFAULT_MAX_DAYS

    with _CACHE_LOCK:
        if not force_reload and _MULTIDAY_DICT_CACHE is not None and _CACHE_DATE == today_str and _CACHE_DAYS == max_days:
            return _MULTIDAY_DICT_CACHE

    wide_df = get_multiday_features_wide(max_days=max_days, force_reload=force_reload, store_path=store_path)
    if wide_df is None or wide_df.empty:
        return {}

    with _CACHE_LOCK:
        try:
            # 批量向量化规整为 float64 且保留 2 位小数，转为原生字典
            rounded_df = wide_df.astype(np.float64).round(2)
            _MULTIDAY_DICT_CACHE = rounded_df.to_dict(orient='index')
        except Exception:
            _MULTIDAY_DICT_CACHE = wide_df.to_dict(orient='index')
        _CACHE_DAYS = max_days
        return _MULTIDAY_DICT_CACHE


def inject_multiday_features_to_row(
    code: str,
    feat_dict: dict,
    wide_df: Optional[pd.DataFrame] = None,
    max_days: Optional[int] = None,
    store_path: Optional[str] = None,
    multiday_dict: Optional[Dict[str, dict]] = None
):
    """
    轻量微秒级单股特征字典注入器:
    优先利用单例共享内存字典进行 O(1) 极速注入。
    """
    if not code: return
    if max_days is None:
        max_days = int(getattr(cct, 'compute_lastdays', DEFAULT_MAX_DAYS)) if cct else DEFAULT_MAX_DAYS

    # 1. 若调用方传入了预提取的 multiday_dict，纳秒级直接注入
    if multiday_dict is not None:
        c_str = str(code).strip().zfill(6)
        if c_str in multiday_dict:
            feat_dict.update(multiday_dict[c_str])
            return
        elif code in multiday_dict:
            feat_dict.update(multiday_dict[code])
            return

    # 2. 若调用方显式传入了 wide_df (包括空的 DataFrame，用于单元测试或特定切片)
    if wide_df is not None:
        if not wide_df.empty and code in wide_df.index:
            row = wide_df.loc[code]
            for i in range(1, max_days + 1):
                rc = f'ratio{i}'
                vc = f'vol_ratio{i}'
                if rc in row:
                    feat_dict[rc] = round(float(row[rc]), 2)
                if vc in row:
                    feat_dict[vc] = round(float(row[vc]), 2)
            return
        else:
            # 显式传入了空 wide_df，执行安全兜底
            for i in range(1, max_days + 1):
                feat_dict.setdefault(f'ratio{i}', 0.0)
                feat_dict.setdefault(f'vol_ratio{i}', 1.0)
            return

    # 3. 默认使用单例共享内存极速字典 (无需 .loc 查找，O(1) 效率)
    d_cache = get_multiday_features_dict(max_days=max_days, store_path=store_path)
    c_str = str(code).strip().zfill(6)
    if d_cache and c_str in d_cache:
        feat_dict.update(d_cache[c_str])
    elif d_cache and code in d_cache:
        feat_dict.update(d_cache[code])
    else:
        # 优雅兜底补齐，绝不让下游报 KeyError
        for i in range(1, max_days + 1):
            feat_dict.setdefault(f'ratio{i}', 0.0)
            feat_dict.setdefault(f'vol_ratio{i}', 1.0)


def clean_and_repair_multiday_store(
    store_path: Optional[str] = None,
    sync_from_latest_close: bool = True
) -> Dict[str, Any]:
    """
    自动清理与自愈多日特征 HDF5 数据库:
    1. 剔除非交易日非法记录 (如 2026-09-12, 2026-09-13 等周末/节假日残留)；
    2. 若最新交易日 (如 2026-09-11) 缺失或为早盘脏数据，尝试从官方收盘库同步修复；
    3. 重写数据库并刷新内存单例缓存。
    返回修复报告字典 {'cleaned_invalid_dates': [...], 'repaired_trade_date': str, 'rows': int}
    """
    h5_path = get_multiday_store_path(store_path)
    res = {'cleaned_invalid_dates': [], 'repaired_trade_date': '', 'rows': 0, 'success': False}
    try:
        from JSONData import tdx_hdf5_api as h5a
        df_existing = pd.DataFrame()
        with h5a.SafeHDFStore(h5_path, mode='r') as store:
            if store is not None and '/' + HDF5_TABLE_NAME in store.keys():
                df_existing = store.get(HDF5_TABLE_NAME)

        if df_existing is None or df_existing.empty:
            logger.info("clean_and_repair_multiday_store: store is empty, nothing to clean.")
            return res

        # 1. 查找并剔除非交易日
        if cct and hasattr(cct, 'get_day_istrade_date'):
            all_dates = df_existing['date'].unique().tolist()
            invalid_dates = [d for d in all_dates if not cct.get_day_istrade_date(d)]
            if invalid_dates:
                logger.warning(f"clean_and_repair_multiday_store: 发现非法非交易日记录 {invalid_dates}，执行物理清理！")
                df_existing = df_existing[~df_existing['date'].isin(invalid_dates)].copy()
                res['cleaned_invalid_dates'] = invalid_dates

        # 2. 写回清理后的合法交易日记录
        with h5a.SafeHDFStore(h5_path, mode='a') as store:
            if store is not None:
                store.put(HDF5_TABLE_NAME, df_existing, format='table', data_columns=['code', 'date'])
        clear_multiday_cache()

        # 3. 如果开启了 sync_from_latest_close，且最新有效交易日存在
        if sync_from_latest_close and cct and hasattr(cct, 'get_last_trade_date'):
            last_trade = str(cct.get_last_trade_date())
            try:
                from JSONData import realdatajson as rl
                df_snap = rl.get_sina_Market_json('all')
                if df_snap is not None and not df_snap.empty and 'ratio' in df_snap.columns:
                    if (df_snap['ratio'] > 0).mean() > 0.3:
                        logger.info(f"clean_and_repair_multiday_store: 正在将官方最新收盘换手率同步至 {last_trade}...")
                        archive_daily_features(df_snap, date_str=last_trade, store_path=store_path)
                        res['repaired_trade_date'] = last_trade
            except Exception as e_sync:
                logger.debug(f"clean_and_repair sync latest close failed: {e_sync}")

        try:
            with h5a.SafeHDFStore(h5_path, mode='r') as store_chk:
                if store_chk is not None and '/' + HDF5_TABLE_NAME in store_chk.keys():
                    res['rows'] = len(store_chk.get(HDF5_TABLE_NAME))
                else:
                    res['rows'] = len(df_existing)
        except Exception:
            res['rows'] = len(df_existing)

        res['success'] = True
        logger.info(f"✅ clean_and_repair_multiday_store 完成: 清除垃圾日期 {res['cleaned_invalid_dates']}, 最新交易日: {res['repaired_trade_date']}, 当前总行数: {res['rows']}")
        return res
    except Exception as e:
        logger.error(f"clean_and_repair_multiday_store 异常: {e}")
        return res
