# -*- coding: utf-8 -*-
"""
ats/multi_period_resampler.py — 多周期 K 线重采样器 (Multi-Period K-Line Resampler)
=============================================================================
功能职责：
1. 将标准日线 DataFrame (OHLCV) 纯向量化重采样为多周期 K 线：
   - 'd' / '1d' : 原生日 K 线
   - '2d'       : 2 日 K 线 (每 2 交易日合并)
   - '3d'       : 3 日 K 线 (每 3 交易日合并)
   - 'w' / 'week': 周 K 线 (自然周聚合)
   - 'm' / 'month': 月 K 线 (自然月聚合)
2. 严守 K 线聚合物理法则：
   - open: 区间首根 open
   - high: 区间最高 high
   - low: 区间最低 low
   - close: 区间末根 close
   - vol: 区间成交量总和
   - amount: 区间成交额总和
3. 防未来函数 (Anti-Lookahead Bias)：
   - 支持时序截断切片，确保回测任意 T 日时，重采样数据严格仅使用 <= T 日的历史。
"""

import os
import sys
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Union

# 确保上一级项目根目录在 sys.path 中 (支持在 ats/ 目录直接命令行调用)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from logger_utils import LoggerFactory
    logger = LoggerFactory.getLogger("MultiPeriodResampler")
except Exception:
    import logging
    logger = logging.getLogger("MultiPeriodResampler")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def normalize_kline_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化 K 线 DataFrame，统一包含规范的 open, high, low, close, vol 列，并按日期升序排列。
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'vol', 'amount'])

    res = df.copy()

    # 处理日期索引与列
    if 'date' in res.columns and not isinstance(res.index, pd.DatetimeIndex):
        res.index = pd.to_datetime(res['date'])
    elif not isinstance(res.index, pd.DatetimeIndex):
        try:
            res.index = pd.to_datetime(res.index)
        except Exception:
            pass

    # 规范列名兼容性映射
    col_map = {
        'trade': 'close',
        'p': 'close',
        'volume': 'vol',
        'turnover': 'amount',
        'money': 'amount'
    }
    for old_c, new_c in col_map.items():
        if old_c in res.columns and new_c not in res.columns:
            res[new_c] = res[old_c]

    # 必要列兜底
    if 'close' not in res.columns and 'open' in res.columns:
        res['close'] = res['open']
    if 'high' not in res.columns and 'close' in res.columns:
        res['high'] = res['close']
    if 'low' not in res.columns and 'close' in res.columns:
        res['low'] = res['close']
    if 'open' not in res.columns and 'close' in res.columns:
        res['open'] = res['close']
    if 'vol' not in res.columns:
        res['vol'] = 1.0
    if 'amount' not in res.columns:
        res['amount'] = res['close'] * res['vol']

    # 按时间单调递增排序
    if not res.index.is_monotonic_increasing:
        res = res.sort_index(ascending=True)

    # 转换数值类型为 float64
    for c in ['open', 'high', 'low', 'close', 'vol', 'amount']:
        if c in res.columns:
            res[c] = pd.to_numeric(res[c], errors='coerce').fillna(0.0).astype(np.float64)

    return res


def resample_n_days(df_norm: pd.DataFrame, n_days: int = 2) -> pd.DataFrame:
    """
    将日 K 线按实际交易日序数合并为 N 日 K 线 (如 2d, 3d)。
    对齐机制：从前往后分组，末尾不足 N 天的作为最新未完成的一根 K 线 (与通达信 2d/3d 视图逻辑一致)。
    """
    total_len = len(df_norm)
    if total_len == 0:
        return df_norm.copy()
    if n_days <= 1:
        return df_norm.copy()

    # 生成分组标签 (0, 0, 1, 1, 2, 2, ...)
    group_ids = np.arange(total_len) // n_days

    # 向量化分组聚合
    agg_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'vol': 'sum',
        'amount': 'sum'
    }

    # 如果有 code，保留 first
    if 'code' in df_norm.columns:
        agg_dict['code'] = 'first'
    if 'name' in df_norm.columns:
        agg_dict['name'] = 'first'

    # 使用临时 group 列加速
    df_temp = df_norm.copy()
    df_temp['_grp_id'] = group_ids

    # 记录每个 group 的最后一个有效日期作为该 K 棒的 index
    df_temp['_orig_date'] = df_temp.index
    agg_dict['_orig_date'] = 'last'

    grouped = df_temp.groupby('_grp_id', as_index=False).agg(agg_dict)
    grouped.index = pd.to_datetime(grouped['_orig_date'])
    grouped.drop(columns=['_orig_date'], inplace=True, errors='ignore')
    grouped.index.name = 'date'

    return grouped


def resample_calendar_period(df_norm: pd.DataFrame, rule: str = 'W-FRI') -> pd.DataFrame:
    """
    基于自然日历周期的重采样 (周线 'W-FRI'，月线 'ME' 或 'M')。
    """
    if len(df_norm) == 0:
        return df_norm.copy()

    # 确保索引为 DatetimeIndex
    if not isinstance(df_norm.index, pd.DatetimeIndex):
        try:
            df_norm = df_norm.copy()
            df_norm.index = pd.to_datetime(df_norm.index)
        except Exception as e:
            logger.warning(f"无法将索引转换为日期类型: {e}")
            return df_norm

    agg_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'vol': 'sum',
        'amount': 'sum'
    }
    if 'code' in df_norm.columns:
        agg_dict['code'] = 'first'
    if 'name' in df_norm.columns:
        agg_dict['name'] = 'first'

    # 使用 resample，保留实际有交易数据的周期 (dropna)
    try:
        res = df_norm.resample(rule).agg(agg_dict).dropna(subset=['close'])
    except ValueError:
        # 兼容旧版本 pandas 'M' / 新版本 'ME'
        fallback_rule = 'M' if 'M' in rule else 'W'
        res = df_norm.resample(fallback_rule).agg(agg_dict).dropna(subset=['close'])

    res.index.name = 'date'
    return res


def resample_kline(df: pd.DataFrame, period: str = 'd') -> pd.DataFrame:
    """
    通用多周期重采样入口函数。
    支持 period:
    - 'd', '1d', 'day', '日线'
    - '2d', '2day', '2日', '2日线'
    - '3d', '3day', '3日', '3日线'
    - '5d', '5day', '5日', '5日线'
    - 'w', 'week', '周线', '周k'
    - 'm', 'month', '月线', '月k'
    """
    df_norm = normalize_kline_df(df)
    if len(df_norm) == 0:
        return df_norm

    p_clean = str(period).lower().strip()

    if p_clean in ('d', '1d', 'day', '日线', '日k', '日'):
        return df_norm
    elif p_clean in ('2d', '2day', '2日', '2日线'):
        return resample_n_days(df_norm, n_days=2)
    elif p_clean in ('3d', '3day', '3日', '3日线'):
        return resample_n_days(df_norm, n_days=3)
    elif p_clean in ('5d', '5day', '5日', '5日线'):
        return resample_n_days(df_norm, n_days=5)
    elif p_clean in ('w', 'week', '周线', '周k', '周'):
        return resample_calendar_period(df_norm, rule='W-FRI')
    elif p_clean in ('m', 'month', '月线', '月k', '月'):
        try:
            return resample_calendar_period(df_norm, rule='ME')
        except Exception:
            return resample_calendar_period(df_norm, rule='M')
    else:
        logger.warning(f"未知周期类型: [{period}]，默认返回原生日 K 线")
        return df_norm


def get_multi_period_klines(
    df_daily: pd.DataFrame,
    periods: Optional[List[str]] = None,
    as_of_date: Optional[str] = None
) -> Dict[str, pd.DataFrame]:
    """
    一次性获取多周期的标准 K 线字典。
    参数:
      df_daily: 原始日 K 线
      periods: 周期列表，默认 ['d', '2d', '3d', 'w', 'm']
      as_of_date: 可选截断日期 (防未来函数: 仅截取 <= as_of_date 的切片后再重采样)
    返回:
      Dict[str, pd.DataFrame]: 映射 { 'd': df_d, '2d': df_2d, '3d': df_3d, 'w': df_w, 'm': df_m }
    """
    if periods is None:
        periods = ['d', '2d', '3d', 'w', 'm']

    df_base = normalize_kline_df(df_daily)
    if as_of_date:
        try:
            cutoff = pd.to_datetime(as_of_date)
            df_base = df_base[df_base.index <= cutoff]
        except Exception as e:
            logger.warning(f"按日期截断异常 ({as_of_date}): {e}")

    result = {}
    for p in periods:
        result[p] = resample_kline(df_base, period=p)

    return result


if __name__ == "__main__":
    # ── 命令行使用与演示 ──
    # 解决终端 Windows GBK 编码输出问题
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    target_code = sys.argv[1] if len(sys.argv) > 1 else "600108"
    dl_days = int(sys.argv[2]) if len(sys.argv) > 2 else 250

    print("=" * 68)
    print(f"🚀 [MultiPeriodResampler] 多周期 K 线重采样器命令行演示")
    print(f"   目标标的: {target_code} | 拉取历史天数: {dl_days}")
    print("=" * 68)

    try:
        from JSONData import tdx_data_Day as tdd
        df_daily = tdd.get_tdx_append_now_df_api(target_code, dl=dl_days)
        if df_daily is None or df_daily.empty:
            df_daily = tdd.get_tdx_Exp_day_to_df(target_code)
    except Exception as e:
        print(f"⚠️ 读取通达信日线失败: {e}，使用随机模拟数据演示")
        dates = pd.date_range(end=pd.Timestamp.today(), periods=dl_days, freq="D")
        df_daily = pd.DataFrame({
            "open": np.random.uniform(10, 20, dl_days),
            "high": np.random.uniform(20, 25, dl_days),
            "low": np.random.uniform(5, 10, dl_days),
            "close": np.random.uniform(10, 20, dl_days),
            "vol": np.random.uniform(1000, 5000, dl_days),
            "amount": np.random.uniform(10000, 50000, dl_days)
        }, index=dates)

    if df_daily is not None and not df_daily.empty:
        periods = ['d', '2d', '3d', 'w', 'm']
        mp_dict = get_multi_period_klines(df_daily, periods=periods)

        print(f"✅ 原始日线加载成功: 共 {len(df_daily)} 根交易日 (起止: {df_daily.index[0]} ~ {df_daily.index[-1]})\n")
        print("📊 各周期聚合重采样结果对照:")
        print(f"{'周期':<8} {'K线根数':<10} {'起始日期':<12} {'结束日期':<12} {'最新收盘价':<10} {'最新成交量':<12}")
        print("-" * 68)
        for p in periods:
            k_df = mp_dict[p]
            start_d = str(k_df.index[0])[:10] if len(k_df) > 0 else "-"
            end_d = str(k_df.index[-1])[:10] if len(k_df) > 0 else "-"
            latest_c = f"{k_df['close'].iloc[-1]:.2f}" if len(k_df) > 0 else "-"
            latest_v = f"{k_df['vol'].iloc[-1]:,.0f}" if len(k_df) > 0 else "-"
            print(f"{p:<8} {len(k_df):<10} {start_d:<12} {end_d:<12} {latest_c:<10} {latest_v:<12}")

        print("\n💡 【使用方法说明】:")
        print("1. 命令行直接执行:")
        print("   python multi_period_resampler.py [股票代码(默认600108)] [历史天数(默认250)]")
        print("2. Python 代码中导入使用:")
        print("   from ats.multi_period_resampler import get_multi_period_klines, resample_kline")
        print("   mp_klines = get_multi_period_klines(df_daily, periods=['d', '2d', '3d', 'w', 'm'])")
        print("   df_2d = mp_klines['2d']")
        print("=" * 68)
