# -*- coding: utf-8 -*-
"""
sbc_core.py — SBC 核心逻辑提取（策略与数据对齐统一）
旨在解决回测/回放与实时监控逻辑不一致的问题，确保两端共用同一套数据处理与信号触发链条。
"""

import pandas as pd
import numpy as np
import time
import os
import logging
from datetime import datetime, date as _date
from typing import List, Dict, Any, Optional, Union

# 尝试导入系统组件
try:
    from JSONData import tdx_data_Day as tdd
    from JohnsonUtil import johnson_cons as ct
    from JohnsonUtil.commonTips import timed_ctx, print_timing_summary
    from realtime_data_service import IntradayEmotionTracker, DailyEmotionBaseline
    from intraday_decision_engine import IntradayDecisionEngine
except ImportError:
    from stock_standalone.JSONData import tdx_data_Day as tdd
    from stock_standalone.JohnsonUtil import johnson_cons as ct
    from stock_standalone.JohnsonUtil.commonTips import timed_ctx, print_timing_summary
    from stock_standalone.realtime_data_service import IntradayEmotionTracker, DailyEmotionBaseline
    from stock_standalone.intraday_decision_engine import IntradayDecisionEngine

try:
    from signal_types import SignalPoint, SignalType, SignalSource
except ImportError:
    from stock_standalone.signal_types import SignalPoint, SignalType, SignalSource

logger = logging.getLogger(__name__)

# 配置常量
MAX_BUY_PER_DAY = 2    # 回放中每日允许的最大买点数
MAX_SELL_PER_DAY = 5   # 回放中每日允许的最大卖点数
PRIORITY_SELL_KW = [
    "高点下移", "反弹", "冲高回落", "乖离",
    "跌破均线", "跌破MA10", "量价背离",
    "趋势压力", "价格行为","结构派发", "结构走弱",
    "二次冲高失败", "持续下移", "破位", "跌穿", "止损"
]

def ts_to_date(ts):
    """时间戳或时间字符串 -> date 对象"""
    if ts is None: return None
    try:
        if isinstance(ts, str):
            # 处理 '2026-01-24 10:15:00' 或 '2026-01-24'
            return pd.to_datetime(ts[:10]).date()
        if isinstance(ts, (int, float)):
            # 处理 Unix 时间戳
            return datetime.fromtimestamp(ts).date()
        if hasattr(ts, 'date'):
            return ts.date()
    except:
        pass
    return None

def format_timestamp(ts):
    """时间戳 -> 'HH:MM:SS' string"""
    try:
        if isinstance(ts, str): return ts[-8:]
        return datetime.fromtimestamp(ts).strftime('%H:%M:%S')
    except:
        return str(ts)

def prepare_day_df(df: pd.DataFrame) -> pd.DataFrame:
    """标准化列名并确保指标存在（性能优化：避免重复计算）"""
    if df is None or df.empty: return df
    
    # 统一转换小写并映射关键列
    mapping = {'Vol': 'volume', 'Amount': 'amount'}
    df = df.rename(columns=mapping).copy()
    df.columns = [c.lower() for c in df.columns]
    
    # needed = ['ma5', 'ma10', 'ma20', 'ma60']

    # if 'close' in df.columns:
    #     # 强制重新计算以确保逻辑一致性
    #     df['ma5'] = df['close'].rolling(5).mean()
    #     df['ma10'] = df['close'].rolling(10).mean()
    #     # ⭐ [CRITICAL] 对齐原始逻辑：MA20 使用 EMA(26)，MA60 使用 EMA(60)
    #     df['ma20'] = tdd.ema_tdx_numpy(df['close'], timeperiod=26)
    #     df['ma60'] = tdd.ema_tdx_numpy(df['close'], timeperiod=60)
        
    #     # [NEW] 计算 win (连阳) 和 red (5日线上) 以对齐 baseline
    #     df['is_up'] = (df['close'] > df['close'].shift(1)).astype(int)
    #     df['win'] = df['is_up'].groupby((df['is_up'] != df['is_up'].shift()).cumsum()).cumsum()
    #     df.loc[df['is_up'] == 0, 'win'] = 0
        
    #     df['is_red'] = (df['close'] > df['ma5']).astype(int)
    #     df['red'] = df['is_red'].groupby((df['is_red'] != df['is_red'].shift()).cumsum()).cumsum()
    #     df.loc[df['is_red'] == 0, 'red'] = 0

    #     # 同步映射后缀版本
    #     for m in needed:
    #         df[f'{m}d'] = df[m]

    # 确保索引是 DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
             df.index = pd.to_datetime(df.index)
        except: pass
            
    return df

def load_day_data(code: str, hdf5_lock=None, resample: str = 'd', fastohlc: bool = True) -> Optional[pd.DataFrame]:
    """标准化加载成交日线数据"""
    try:
        # [LOCK] 如果提供了外部锁，则在锁内执行 HDF5 敏感操作
        if hdf5_lock:
            from PyQt6.QtCore import QMutexLocker
            with QMutexLocker(hdf5_lock):
                raw = tdd.get_tdx_Exp_day_to_df(
                    code, dl=ct.Resample_LABELS_Days[resample], resample=resample, fastohlc=fastohlc)
        else:
            raw = tdd.get_tdx_Exp_day_to_df(
                code, dl=ct.Resample_LABELS_Days[resample], resample=resample, fastohlc=fastohlc)

        if raw is None or raw.empty:
            logger.error(f"❌ 无法获取 {code} 日线数据")
            return None
        
        # 统一索引为日期字符串
        try:
            dts = pd.to_datetime(raw.index)
            raw.index = [d.strftime('%Y-%m-%d') for d in dts]
        except Exception:
            for col in ('date', 'trade_date'):
                if col in raw.columns:
                    raw.index = [pd.to_datetime(d).strftime('%Y-%m-%d') for d in raw[col]]
                    break
        
        return prepare_day_df(raw)
    except Exception as e:
        logger.error(f"❌ 日线加载失败: {e}")
        return None

def load_tick_data(code: str, use_live: bool = False, cache_path: str = r"G:\minute_kline_cache.pkl"):
    """加载 Tick 或分钟线数据"""
    if use_live:
        stock_df = None
        try:
            from data_hub_service import DataHubService
            hub_df = DataHubService.get_instance().get_tick_cache(code)
            if hub_df is not None and not hub_df.empty:
                logger.info(f"⚡ [DataHub] Successfully fetched {len(hub_df)} live ticks for {code}")
                stock_df = hub_df.copy()
        except Exception as e:
            logger.error(f"[DataHub] Failed to fetch live tick for {code}: {e}")

        if stock_df is None or stock_df.empty:
            try:
                try:
                    from JSONData import sina_data
                except ImportError:
                    from stock_standalone.JSONData import sina_data
                sina = sina_data.Sina()
                logger.info(f"📡 正在从 Sina 获取 {code} 实时数据...")
                stock_df = sina.get_real_time_tick(code, enrich_data=True)
                if stock_df is None or stock_df.empty:
                    logger.error(f"❌ 无法获取 {code} 实时数据")
                    return None
                
                stock_df = stock_df.copy()

                # Sina 数据标准化
                if isinstance(stock_df.index, pd.MultiIndex):
                    stock_df = stock_df.reset_index()
                    if 'code' in stock_df.columns:
                        stock_df = stock_df[stock_df['code'] == code].copy()
                    stock_df = stock_df.reset_index(drop=True)
                elif stock_df.index.name == 'ticktime':
                    stock_df = stock_df.reset_index()

                mapping = {'trade': 'close', 'volume': 'volume', 'amount': 'amount'}
                for src, dst in mapping.items():
                    if src in stock_df.columns and dst not in stock_df.columns:
                        stock_df[dst] = stock_df[src]
                
                for col in ['high', 'low']:
                    if col not in stock_df.columns:
                        stock_df[col] = stock_df['close']
                
                if 'open' not in stock_df.columns:
                    stock_df['open'] = stock_df['close'].shift(1).fillna(stock_df['close'])

                logger.info(f"✅ 成功获取 {len(stock_df)} 条实时数据")
                return stock_df
            except Exception as e:
                logger.error(f"❌ 获取实时数据失败: {e}")
                return None
    else:
        if not os.path.exists(cache_path):
            logger.error(f"❌ 未找到缓存: {cache_path}")
            return None
        try:
            full = pd.read_pickle(cache_path)
            stock_df = full[full['code'] == code].copy().sort_values('time')
            if stock_df.empty:
                logger.error(f"❌ 缓存中无 {code} 数据")
                return None
            logger.info(f"✅ 成功加载 {len(stock_df)} 条分钟线数据")
            return stock_df
        except Exception as e:
            logger.error(f"❌ 读取缓存失败: {e}")
            return None

def get_sbc_analysis_package(code: str, use_live: bool = False, hdf5_lock=None, resample: str = 'd', fastohlc: bool = True, cache_path: str = r"G:\minute_kline_cache.pkl", day_df: Optional[pd.DataFrame] = None, tick_df: Optional[pd.DataFrame] = None, verbose: bool = True) -> Optional[Dict[str, Any]]:
    """
    一键式获取 SBC 分析结果包（整合数据加载与逻辑运算）
    """
    # 1. 对齐可视化器传入的 raw 数据环境
    if day_df is None:
        day_df = load_day_data(code, hdf5_lock=hdf5_lock, resample=resample, fastohlc=fastohlc)
    
    day_df, tick_df, current_date = align_visualizer_context(code, day_df, tick_df)
    
    if day_df is None: return None
    
    # 2. 加载 Tick (如果未提供)
    if tick_df is None:
        tick_df = load_tick_data(code, use_live=use_live, cache_path=cache_path)
    if tick_df is None: return None
    
    # 3. 执行核心逻辑
    return run_sbc_analysis_core(code, day_df, tick_df, use_live=use_live, verbose=verbose)


def get_day_context(code: str, day_df: pd.DataFrame, tick_date):
    """
    【对齐两端逻辑链条】— 基于时间点提取严格历史基准
    确保锚点指向分时图日期 D 的前一交易日 D-1
    """
    try:
        t_date_str = tick_date.strftime('%Y-%m-%d') if hasattr(tick_date, 'strftime') else str(tick_date)
        hist_day_df = day_df[day_df.index.astype(str) < t_date_str]
        
        if hist_day_df.empty:
            return None, {}, 0.0, 0.0, 0.0, 0.0, None

        row = hist_day_df.iloc[-1]
        prev_row = hist_day_df.iloc[-2] if len(hist_day_df) >= 2 else row
        prev2_row = hist_day_df.iloc[-3] if len(hist_day_df) >= 3 else prev_row
        prev3_row = hist_day_df.iloc[-4] if len(hist_day_df) >= 4 else prev2_row

        bl_data = {
            'code':          code,
            'high':          float(row['high']),
            'lasth1d':       float(row['high']),
            'lasth2d':       float(prev_row['high']),
            'close':         float(row['close']),
            'lastp1d':       float(row['close']),
            'lastp2d':       float(prev_row['close']),
            'low':           float(row['low']),
            'last_low':      float(row['low']),
            'ma60d':         float(row.get('ma60', row.get('ma60d', row['close']))),
            'ma20d':         float(row.get('ma20', row.get('ma20d', row['close']))),
            'ma5d':          float(row.get('ma5',  row.get('ma5d',  row['close']))),
            'ma10d':         float(row.get('ma10', row.get('ma10d', row.get('ma10', 0)))),
            'prev3_high_max': float(max(prev_row['high'], prev2_row['high'], prev3_row['high'])),
            'prev3_close_max': float(max(prev_row['close'], prev2_row['close'], prev3_row['close'])),
        }
        
        # 🚀 [NEW] Centralized df_all extraction for structure_base_score
        try:
            from data_hub_service import DataHubService
            hub_df_all = DataHubService.get_instance().get_df_all()
            if hub_df_all is not None and not hub_df_all.empty:
                # support both code string and numerical index if padded
                code_pad = code.zfill(6)
                if code_pad in hub_df_all.index:
                    hub_row = hub_df_all.loc[code_pad]
                elif 'code' in hub_df_all.columns:
                    match = hub_df_all[hub_df_all['code'] == code_pad]
                    hub_row = match.iloc[0] if not match.empty else None
                else:
                    hub_row = None
                
                if hub_row is not None and 'structure_base_score' in hub_row:
                    bl_data['structure_base_score'] = float(hub_row['structure_base_score'])
                    logger.debug(f"[SBC] Loaded structure_base_score={bl_data['structure_base_score']} from DataHub")
        except Exception as e:
            logger.error(f"[SBC] Failed to fetch df_all from DataHub: {e}")

        bl_df = pd.DataFrame([bl_data])
        
        baseline = DailyEmotionBaseline()
        baseline._last_calc_date = None
        baseline.calculate_baseline(bl_df)

        anchors = baseline.get_anchor(code)
        last_close = bl_data['close']
        ma5        = bl_data['ma5d']
        ma10       = bl_data['ma10d']
        ma60       = bl_data['ma60d']

        return baseline, anchors, last_close, ma5, ma10, ma60, row
    except Exception as e:
        logger.error(f"Error in get_day_context: {e}")
        return None, {}, 0.0, 0.0, 0.0, 0.0, None


# def evaluate_sell_tick(row: dict, snapshot: dict) -> dict[str, Any]:
#     """
#     针对 tick 的增量卖出信号判断
#     日线指标只计算一次，tick 只做阈值/增量比较
#     """
#     debug: dict[str, Any] = {}
#     price = float(row.get("trade", 0))
#     if price <= 0:
#         return {"action": "持仓", "reason": "价格无效", "debug": debug}

#     high = float(row.get("high", price))
#     low = float(row.get("low", price))
#     nclose = float(row.get("nclose", snapshot.get("nclose", price)))

#     # ---------- 初始化缓存 (日线指标) ----------
#     cache = snapshot.setdefault("sell_cache", {})
#     if not cache.get("initialized", False):
#         day_df: pd.DataFrame = snapshot.get("day_df", pd.DataFrame())
#         if day_df.empty or len(day_df) < 10:
#             cache["initialized"] = True
#             cache["top_info"] = {"score": 0.0, "signals": []}
#             cache["ma5"] = day_df['close'].tail(5).mean() if 'close' in day_df else 0
#             cache["ma10"] = day_df['close'].tail(10).mean() if 'close' in day_df else 0
#             cache["ma20"] = day_df['close'].tail(20).mean() if 'close' in day_df else 0
#         else:
#             cache["top_info"] = detect_top_signals(day_df, cache_dict={})
#             last_row = day_df.iloc[-1]
#             cache["ma5"] = last_row.get("ma5d", day_df['close'].tail(5).mean())
#             cache["ma10"] = last_row.get("ma10d", day_df['close'].tail(10).mean())
#             cache["ma20"] = last_row.get("ma20d", day_df['close'].tail(20).mean())
#         cache["initialized"] = True

#     top_info = cache["top_info"]
#     ma5 = cache["ma5"]
#     ma10 = cache["ma10"]
#     ma20 = cache["ma20"]

#     debug["top_score"] = top_info["score"]
#     debug["top_signals"] = top_info["signals"]

#     # ---------- 卖出信号判定 ----------
#     # 1. 优先止损 / T+1限制
#     cost_price = float(snapshot.get("cost_price", 0))
#     is_t1_restricted = snapshot.get("buy_date", "").startswith(dt.datetime.now().strftime("%Y-%m-%d"))
#     if cost_price > 0 and not is_t1_restricted:
#         stop_result = getattr(self, "_stop_check", lambda r, s, d: {"triggered": False})(
#             row, snapshot, debug
#         )
#         if stop_result["triggered"]:
#             debug["early_stop_priority"] = True
#             return {
#                 "action": stop_result["action"],
#                 "position": stop_result["position"],
#                 "reason": f"[风控优先] {stop_result['reason']}",
#                 "debug": debug
#             }

#     # 2. 增量阈值卖出判定
#     # ⚡ 核心：只对敏感字段做比较
#     sell_reason = []
#     action = "持仓"
#     pos = float(snapshot.get("position", 1.0))

#     # 顶部信号分数过高 → 减仓 / 卖出
#     if top_info["score"] > 0.6:
#         action = "卖出"
#         sell_reason.append("顶部信号高分")
    
#     # VWAP / nclose 下穿 → 卖出
#     if nclose > 0 and price < nclose:
#         action = "卖出"
#         sell_reason.append(f"低于分时均线 VWAP={nclose:.2f}")

#     # MA5 / MA10 下穿 → 卖出
#     if ma5 > 0 and price < ma5:
#         action = "卖出"
#         sell_reason.append(f"下破 MA5={ma5:.2f}")
#     elif ma10 > 0 and price < ma10:
#         action = "卖出"
#         sell_reason.append(f"下破 MA10={ma10:.2f}")

#     # 高位放量滞涨 / 阴跌 → 卖出
#     if "高位放量滞涨" in top_info["signals"] or "高位放量阴跌/分歧" in top_info["signals"]:
#         action = "卖出"
#         sell_reason.append("高位放量滞涨/阴跌信号")

#     # 如果卖出条件触发
#     if action == "卖出":
#         debug["sell_reason"] = " | ".join(sell_reason)
#         return {
#             "action": "卖出",
#             "position": pos,
#             "reason": " | ".join(sell_reason),
#             "debug": debug
#         }

#     # 默认持仓
#     return {"action": "持仓", "reason": "无卖出信号", "debug": debug}

# ---------- 调试函数 ----------
def debug_sbc_signals(tick_df: pd.DataFrame, lastp1d_val: float, verbose: bool = True):
    tick_df = tick_df.copy()
    tick_df['trade'] = tick_df.get('trade', tick_df.get('close', tick_df.get('Close', 0))).astype(float)

    signals = []
    last_signal_times = {}
    
    for i, r in enumerate(tick_df.itertuples(index=False)):
        status = str(getattr(r, 'sbc_status', ''))
        trade = getattr(r, 'trade', 0.0)

        # t_str = getattr(r, 'ticktime', getattr(r, 'time', getattr(r, 'Timestamp', '00:00')))
        t_str = get_tick_str(r)

        if hasattr(t_str, 'strftime'):
            t_str = t_str.strftime('%H:%M')
        
        follow_allowed = i - last_signal_times.get("FOLLOW", -999) > 30

        if verbose:
            print(f"[{i:03d}] {t_str} | trade={trade:.2f} | sbc_status='{status}' | "
                  f"last_follow_idx={last_signal_times.get('FOLLOW', None)} | follow_allowed={follow_allowed}")

        if "🚀" in status and follow_allowed:
            print(f"    >>> BUY SIGNAL WOULD FIRE at {t_str} price={trade:.2f}")
            last_signal_times["FOLLOW"] = i
            signals.append((i, t_str, trade, status))

    print(f"\nTotal BUY signals detected: {len(signals)}")
    for idx, t_str, trade, status in signals:
        print(f"  [{idx:03d}] {t_str} | {trade:.2f} | {status}")
    
    return signals


def parse_t(t):
    """
    将 tick 的时间值统一转换成 HH:MM 格式（北京时间）。
    t 可以是:
        - 字符串 '2026-03-07 13:45:12' 或 '13:45:12'
        - pd.Timestamp
        - Unix 时间戳（秒或毫秒）
    """
    try:
        if t is None or pd.isna(t) or t == '':
            return '00:00'

        # 字符串优先处理 (通常已经是本地时间 HH:MM:SS 或 YYYY-MM-DD HH:MM:SS)
        if isinstance(t, str):
            if ' ' in t: # YYYY-MM-DD HH:MM:SS
                return t.split(' ')[1][:5]
            if ':' in t: # HH:MM:SS
                return t[:5]
            # 其他字符串尝试 pd.to_datetime 兜底

        # 数字类型 -> Unix 时间戳 (处理北京时间偏移)
        if isinstance(t, (int, float, np.integer, np.floating)):
            # 毫秒级时间戳 (> 10位)
            if t > 1e12:
                dt_val = pd.to_datetime(t / 1000, unit='s', utc=True)
            else:
                dt_val = pd.to_datetime(t, unit='s', utc=True)
            
            # 转北京时间 (如果是 Unix 时间戳通常是绝对时间，需要 +8)
            dt_val = dt_val.tz_convert('Asia/Shanghai') if dt_val.tzinfo else dt_val + pd.Timedelta(hours=8)
            return dt_val.strftime('%H:%M')
            
        # 其他类型 (pd.Timestamp 等)
        dt_val = pd.to_datetime(t)
        return dt_val.strftime('%H:%M')
        
    except Exception:
        s = str(t)
        # 尝试提取末尾的 HH:MM
        if ':' in s:
            parts = s.split(':')
            if len(parts) >= 2:
                # 简单寻找数字
                import re
                m = re.search(r'(\d{1,2}:\d{2})', s)
                if m: return m.group(1)
        return s[:5]

def get_tick_str(r):
    # 取优先级时间列 (兼容对象与字典)
    t_val = None
    # 增加更多可能的键名，特别是 reset_index 后的 index 或 level_0
    for attr in ('ticktime', 'time', 'Timestamp', 'index', 'level_0', 'now', 'tick_time'):
        if isinstance(r, dict):
            t_val = r.get(attr)
        else:
            t_val = getattr(r, attr, None)
            
        if t_val is not None:
            break
            
    if t_val is None or pd.isna(t_val) or t_val == '':
        # 兜底：如果都没有，尝试从整个 dict 中寻找包含 time 的 key (仅针对 dict)
        if isinstance(r, dict):
            for k, v in r.items():
                if 'time' in k.lower() and v is not None:
                    t_val = v
                    break
        
    if t_val is None or pd.isna(t_val) or t_val == '':
        t_val = '00:00'
    return parse_t(t_val)




def run_sbc_analysis_core(code: str, day_df: pd.DataFrame, tick_df: pd.DataFrame, use_live: bool = False, verbose: bool = False):
    """
    SBC 信号分析核心逻辑 (高性能版本：数据全对齐 + 动态决策引擎 + 🚀&🔥全捕捉)
    """
    # 1. 环境准备 (使用副本防止污染原始 DataFrame)
    with timed_ctx("1_copy_df", warn_ms=800):
        day_df = prepare_day_df(day_df.copy())
        tick_df = tick_df.copy()
    
    # 2. 计算 Baseline (锚点提取逻辑) - 必须确保信号判定的基准线唯一且正确
    with timed_ctx("2_baseline_date_sync", warn_ms=800):
        try:
            if isinstance(tick_df.index, pd.MultiIndex):
                raw_ts = tick_df.index.get_level_values('ticktime')[0]
            else:
                raw_ts = tick_df['ticktime'].iloc[0] if 'ticktime' in tick_df.columns else tick_df['time'].iloc[0]
                
            # [ALIGN] 增强型日期转换
            if isinstance(raw_ts, (int, float, np.integer, np.floating)):
                ts_val = raw_ts / 1000.0 if raw_ts > 1.5e12 else raw_ts
                t_date_str = pd.to_datetime(ts_val, unit='s').strftime('%Y-%m-%d')
            else:
                t_date_str = pd.to_datetime(raw_ts).strftime('%Y-%m-%d')
        except:
            t_date_str = str(day_df.index[-1])[:10]

        hist = day_df[day_df.index.astype(str) < t_date_str]
        if hist.empty:
            hist = day_df[day_df.index.astype(str) <= t_date_str]
            if len(hist) >= 2: hist = hist.iloc[:-1]
            else:
                valid_days = day_df[day_df.index.astype(str) < t_date_str]
                hist = valid_days if not valid_days.empty else (day_df.iloc[:-1] if len(day_df) >= 2 else day_df)
            
        row = hist.iloc[-1]
        prev_row = hist.iloc[-2] if len(hist) >= 2 else row
        prev2_row = hist.iloc[-3] if len(hist) >= 3 else prev_row
        prev3_row = hist.iloc[-4] if len(hist) >= 4 else prev2_row
    

    with timed_ctx("3_baseline_calc", warn_ms=800):
        bl_data = {
            'code':        code,
            'trade':       float(row['close']),
            'lasth1d':     float(row['high']),
            'lasth2d':     float(prev_row['high']),
            'lastp1d':     float(row['close']),
            'lastp2d':     float(prev_row['close']),
            'last_low':    float(row['low']),
            'ma60d':       float(row.get('ma60', row.get('ma60d', row['close']))),
            'ma20d':       float(row.get('ma20', row.get('ma20d', row['close']))),
            'ma10d':       float(row.get('ma10', row.get('ma10d', row['close']))),
            'ma5d':        float(row.get('ma5',  row.get('ma5d',  row['close']))),
            'win':         float(row.get('win', 0)),
            'red':         float(row.get('red', 0)),
            'TrendS':      float(row.get('TrendS', 50)),
            'slope':       float(row.get('slope', 0)),
            'sum_perc':    float(row.get('sum_perc', 0)),
            'power_idx':   float(row.get('power_idx', 0)),
            'upper':       float(row.get('upper', 0)),
            'dist_h_l':    float(row.get('dist_h_l', 4.0)),
            'prev3_high_max': float(max(prev_row['high'], prev2_row['high'], prev3_row['high'])),
            'prev3_close_max': float(max(prev_row['close'], prev2_row['close'], prev3_row['close'])),
        }

        # 动态判定上升结构: 1. 连续两天抬升 2. 或突破/贴近上轨 3. 或均线多头且连阳 4. 或突破前3日高点 5. 或日线均线反转(站回MA5/MA10)
        basic_rise = (bl_data['lastp1d'] > bl_data['lastp2d'] > 0) and (bl_data['lasth1d'] > bl_data['lasth2d'] > 0)
        near_upper = (bl_data['upper'] > 0) and (bl_data['lastp1d'] >= bl_data['upper'] * 0.985)
        strong_trend = (bl_data['ma5d'] > bl_data['ma10d'] > 0) and (bl_data['lastp1d'] > bl_data['ma5d']) and (bl_data['win'] >= 2)
        break_3d = (bl_data['lastp1d'] > bl_data['prev3_high_max']) or (bl_data['lastp1d'] >= bl_data['prev3_close_max'] and bl_data['lastp1d'] > bl_data['lastp2d'])
        
        # 反转结构：类似分时站回均线，收盘强势收复 MA5 或 MA10 且大于昨收
        reversal = (bl_data['lastp1d'] > bl_data['lastp2d']) and (
            (bl_data['lastp1d'] > bl_data['ma5d'] >= bl_data['lastp2d']) or 
            (bl_data['lastp1d'] > bl_data['ma10d'] >= bl_data['lastp2d'])
        )
        
        is_rising_struct = basic_rise or near_upper or strong_trend or break_3d or reversal
        bl_data['is_rising_struct'] = is_rising_struct
        
        if verbose:
            print(f"\n── {t_date_str} | 昨收:{bl_data['lastp1d']:.2f} | 昨高:{bl_data['lasth1d']:.2f} | MA5:{bl_data['ma5d']:.2f} | MA10:{bl_data['ma10d']:.2f} ──")
            print(f"   [DEBUG] Engine Anchors: {{'yesterday_high': {bl_data['lasth1d']:.2f}, 'prev_high': {bl_data['lasth2d']:.2f}, 'ma60': {bl_data['ma60d']:.2f}, 'ma20': {bl_data['ma20d']:.2f}, 'last_low': {bl_data['last_low']:.2f}, 'last_close': {bl_data['lastp1d']:.2f}, 'last_close_p2': {bl_data['lastp2d']:.2f}, 'is_rising_struct上涨结构': {is_rising_struct}}}")
        
        baseline_loader = DailyEmotionBaseline()
        baseline_loader.calculate_baseline(pd.DataFrame([bl_data]))
    
    # 3. 准备分时数据并执行分析 (VWAP 计算)
    with timed_ctx("4_tick_df_fix", warn_ms=800):
        if isinstance(tick_df.index, pd.MultiIndex):
            tick_df = tick_df.reset_index()
            
        c_clean = str(code).zfill(6)
        if 'code' not in tick_df.columns: tick_df['code'] = c_clean
        
        # 统一价格列
        for p_col in ['trade', 'price', 'close', 'Close']:
            if p_col in tick_df.columns:
                tick_df['trade'] = tick_df[p_col].astype(float)
                break
            
        if 'amount' not in tick_df.columns and 'amt' in tick_df.columns:
            tick_df['amount'] = tick_df['amt']
        
        if 'avg_price' not in tick_df.columns:
            if 'amount' in tick_df.columns and 'volume' in tick_df.columns:
                tick_df['avg_price'] = (tick_df['amount'] / tick_df['volume']).fillna(tick_df['trade'])
            else:
                c_arr = tick_df['trade'].values
                v_arr = tick_df['volume'].values if 'volume' in tick_df.columns else np.ones(len(tick_df))
                ca = (c_arr * v_arr).cumsum()
                cv = np.maximum(v_arr.cumsum(), 1e-9)
                tick_df['avg_price'] = ca / cv
                
        if 'volume' in tick_df.columns:
            tick_df['vol'] = tick_df['volume'].diff().fillna(tick_df['volume']).clip(lower=0)
        elif 'vol' not in tick_df.columns:
            tick_df['vol'] = 0

    # 4. 批量更新 EmotionTracker
    with timed_ctx("5_tracker_batch_update", warn_ms=800):
        tracker = IntradayEmotionTracker()
        tracker.update_batch(tick_df, baseline_loader)
    
    # 5. 信号提取循环 (使用 evaluate_dynamic 极大提升遍历性能)
    signals = []
    engine = IntradayDecisionEngine()
    snapshot = {
        "cost_price": 0.0,
        "highest_since_buy": 0.0,
        "last_close": bl_data['lastp1d'],
        "loss_streak": 0,
        "market_win_rate": 0.5,
        "day_df": day_df,
        **bl_data
    }
    
    lastp1d_val = float(bl_data['lastp1d'])
    row_init = {k: bl_data[k] for k in ['ma5d','ma10d','ma20d','ma60d','lastp1d','lastp2d','lasth1d','lasth2d','last_low','trade']}
    base_eval = engine.evaluate(row_init, snapshot, mode="sell_only")
    
    last_signal_times = {} # {signal_type.name: last_idx}
    
    # [PERF] 先将 DataFrame 转为 list of dicts 提升 5-10 倍遍历速度
    with timed_ctx("6_engine_loop", warn_ms=800):
        # reset_index 确保索引中的时间/代码信息进入 dict
        tick_list = tick_df.reset_index().to_dict('records')
        row_dict = row_init.copy() 
        day_high = lastp1d_val
        day_low = bl_data['last_low']
        
        # [NEW] 追踪实时情绪分 (Emotion Score) 以对应 buyscore
        baseline_score = float(bl_data.get('TrendS', 50))
        
        # 结构溢价 (Structural Alpha): 如果多日结构处于上升态势，给予显著的基础分加成
        # 这是为了解决用户反馈的“多日连续性”问题，让强势股在开盘即拥有更高的情绪起点
        struct_alpha = 15 if bl_data.get('is_rising_struct', False) else 0
        baseline_score += struct_alpha
        
        curr_emo_score = baseline_score
        EMA_ALPHA = 0.25 # 略微降低 EMA 权重，让初始结构溢价维持更久
        
        for i, r in enumerate(tick_list):
            p = float(r.get('trade', 0))
            cur_high = float(r.get('high', p))
            cur_low = float(r.get('low', p))
            avg_price = float(r.get('avg_price', p))
            
            day_high = max(day_high, cur_high)
            day_low = min(day_low, cur_low)
            
            # 手动同步 snapshot 关键点 (evaluate_dynamic 内部也会尝试 max，但外部显式同步更安全)
            snapshot["nclose"] = avg_price
            snapshot["highest_today"] = day_high
            snapshot["low_val"] = day_low
            
            row_dict.update({
                'trade':   p,
                'high':    cur_high,
                'low':     cur_low,
                'open':    float(r.get('open', p)),
                'vol':     float(r.get('vol', 0)),
                'percent': (p - lastp1d_val) / lastp1d_val * 100 if lastp1d_val else 0,
                'nclose':  avg_price,
            })
            
            # (A.0) 实时计算买入强度 (buyscore)
            pct_now = row_dict['percent']
            vol_ratio = float(r.get('amount_ratio', r.get('ratio', 1.0)))
            
            # 价增分：涨幅贡献更加灵敏 (每 1% 约 4-5分)
            price_score = pct_now * 4.5
            
            # 量能分：成交量/金额比贡献 (线性增长，不再是硬门槛)
            # 例如 1.5倍量贡 4分, 3倍量贡献 16分, 5倍量贡献 32分
            volume_score = (vol_ratio - 1.0) * 8.0 if vol_ratio > 1.0 else 0
            
            # 状态分：如果是强势结构或加速，额外加成
            status_bonus = 0
            if "加速" in str(r.get('sbc_status', '')): status_bonus += 10
            elif "强势" in str(r.get('sbc_status', '')): status_bonus += 5
            
            # 位置分：创新高或突破关键昨高
            pos_bonus = 0
            if p >= day_high: pos_bonus += 5
            if p >= bl_data.get('yesterday_high', 0): pos_bonus += 3
            
            target_score = baseline_score + price_score + volume_score + status_bonus + pos_bonus
            
            # EMA 平滑，防止分值剧烈跳变
            curr_emo_score = curr_emo_score * (1 - EMA_ALPHA) + target_score * EMA_ALPHA
            curr_emo_score = np.clip(curr_emo_score, 0, 100)
            row_dict['emotion_score'] = curr_emo_score
            
            # (A) SBC 买入信号判定: 🚀强势结构 或 🔥趋势加速
            status = str(r.get('sbc_status', ''))
            # 规范化图标显示，确保“趋势加速”带🔥，“强势结构”带🚀 (不覆盖原有明细文字)
            if "趋势加速" in status and "🔥" not in status: status = "🔥" + status
            if "强势结构" in status and "🚀" not in status: status = "🚀" + status
            
            is_buy_sbc = any(kw in status for kw in ["强势结构", "趋势加速", "🚀", "🔥"])
            
            if is_buy_sbc:
                last_idx = last_signal_times.get("FOLLOW", -999)
                last_s = last_signal_times.get("FOLLOW_STATUS", "")
                last_p = last_signal_times.get("LAST_BUY_PRICE", 0.0)
                
                # 1. 信号分级与状态
                is_cur_acc = "趋势加速" in status or "🔥" in status
                is_cur_struct = ("强势结构" in status or "🚀" in status) and not is_cur_acc
                was_last_acc = "🔥" in last_s or "趋势加速" in last_s
                
                # 2. 核心逻辑：逐级确认 (Step-by-Step Confirmation)
                # (a) 动量升级：从 🚀 转为 🔥，无视 30 Tick 立即确认
                is_upgrade = is_cur_acc and not was_last_acc
                
                # (b) 价格加强：如果是相同性质的信号，必须价格创新高才显示 (过滤横盘)
                # (c) 性质切换：如果信号性质发生变化 (🔥<->🚀)，且在 30 Tick 冷却外，视为新的确认买点
                is_status_change = status != last_s
                is_price_higher = p > last_p
                
                # 3. 最终触发条件
                # 允许性质切换或价格加强后的信号，只要冷却时间已到；或者是即时的动量升级
                should_trigger = (i - last_idx > 30 and (is_status_change or is_price_higher)) or is_upgrade
                
                if should_trigger:
                    t_str = get_tick_str(r) if verbose else ""
                    if verbose:
                        # 组合前缀图标，保留 🎯 并注明具体级别 emoji
                        emoji = "🔥" if is_cur_acc else "🚀"
                        print(f"[{t_str}] 🎯 {emoji} 买入: {status} at {p:.2f} \033[93m({curr_emo_score:.1f})\033[0m")
                    
                    signals.append(SignalPoint(
                        code=code, timestamp=str(r.get('ticktime', t_str)), 
                        bar_index=i, price=p, 
                        signal_type=SignalType.FOLLOW, source=SignalSource.STRATEGY_ENGINE, reason=status,
                        debug_info={'buy_score': round(curr_emo_score, 1)}
                    ))
                    last_signal_times["FOLLOW"] = i
                    last_signal_times["FOLLOW_STATUS"] = status
                    last_signal_times["LAST_BUY_PRICE"] = p
    
            # (B) 决策引擎动态评估 (卖出信号判定)
            decision = engine.evaluate_dynamic(base_eval, row_dict, snapshot)
            action = decision.get("action", "")
            reason = decision.get("reason", "")
            
            if action in {"卖出", "止损", "预警止损", "移动止盈", "高位止盈", "趋势止损", "破位减仓", "强制清仓", "主动防守", "主动减仓"}:
                if any(kw in reason for kw in PRIORITY_SELL_KW):
                    last_idx = last_signal_times.get("EXIT", -999)
                    if i - last_idx > 30:
                        t_str = get_tick_str(r) if verbose else ""
                        if verbose:
                            sel_score = decision.get("debug", {}).get("top_score", 0.0)
                            print(f"[{t_str}] ⚠️  卖出: \033[1;32m{action}\033[0m at {p:.2f} | {reason} \033[93m({sel_score:.2f})\033[0m")
                        
                        signals.append(SignalPoint(
                            code=code, timestamp=str(r.get('ticktime', t_str)), 
                            bar_index=i, price=p,
                            signal_type=SignalType.EXIT_FOLLOW, source=SignalSource.STRATEGY_ENGINE, reason=reason,
                            debug_info={'sell_score': round(decision.get("debug", {}).get("top_score", 0.0), 2)}
                        ))
                        last_signal_times["EXIT"] = i
            
    # 6. 可视化后期处理 (Time Labels & Avg Series)
    with timed_ctx("7_viz_prep", warn_ms=800):
        if 'ticktime' in tick_df.columns:
            raw_times = tick_df['ticktime']
        elif 'time' in tick_df.columns:
            raw_times = tick_df['time']
        elif isinstance(tick_df.index, pd.MultiIndex):
            raw_times = tick_df.index.get_level_values('ticktime')
        else:
            raw_times = tick_df.index

        t_labels = [parse_t(t) for t in raw_times]
        
        if 'amount' in tick_df.columns and 'volume' in tick_df.columns:
            avg_series = (tick_df['amount'].cumsum() / tick_df['volume'].cumsum()).fillna(tick_df['trade']).tolist()
        else:
            avg_series = tick_df['avg_price'].tolist() if 'avg_price' in tick_df.columns else []

    return {
        "signals": signals,
        "viz_df": tick_df,
        "title": f"SBC Core - {code} ({t_date_str})",
        "avg_series": avg_series,
        "time_labels": t_labels,
        "use_live": use_live
    }

def align_visualizer_context(code: str, day_df: Optional[pd.DataFrame], tick_df: Optional[pd.DataFrame]):
    """
    [专门为可视化器定制] 
    输入原始加载的 day_df 和 tick_df，输出对齐后的 (day_df, tick_df, current_date_str)
    """
    if day_df is None:
        return None, tick_df, None
    
    # 1. 确定当前逻辑日期 D
    current_date_str = None
    if tick_df is not None and not tick_df.empty:
        try:
            # 简化版日期提取
            raw_ts = None
            if isinstance(tick_df.index, pd.MultiIndex):
                raw_ts = tick_df.index.get_level_values('ticktime')[0]
            elif 'ticktime' in tick_df.columns:
                raw_ts = tick_df['ticktime'].iloc[0]
            
            if raw_ts is not None:
                if isinstance(raw_ts, str) and len(raw_ts) <= 9:
                    current_date_str = format_timestamp(day_df.index[-1])
                else:
                    current_date_str = format_timestamp(raw_ts)
        except: pass

    if not current_date_str:
        current_date_str = format_timestamp(day_df.index[-1])

    # 2. 边界检查
    last_d = format_timestamp(day_df.index[-1])
    if current_date_str > last_d:
        current_date_str = last_d

    return day_df, tick_df, current_date_str

def get_sbc_baseline_data(code: str, day_df: pd.DataFrame, current_date: str) -> Optional[dict]:
    """
    [超轻量函数] 专门供可视化器渲染循环调用。
    只负责提取 D-1 锚点数据，不涉及任何指标重算。
    """
    try:
        # [性能关键] 这里尽量不 copy，只读
        # 统一格式化定位
        d_idx = day_df.index
        if not isinstance(d_idx[0], str): # 可能是 DatetimeIndex
            current_dt = pd.to_datetime(current_date)
            hist = day_df[day_df.index < current_dt]
        else:
            hist = day_df[day_df.index < current_date]
            
        if hist.empty:
            if len(day_df) >= 2: hist = day_df.iloc[:-1]
            else: return None
            
        row = hist.iloc[-1]
        prev_row = hist.iloc[-2] if len(hist) >= 2 else row
        
        # 转换为计算所需的标准字典
        # 兼容大小写
        def gv(r, keys):
            for k in keys:
                if k in r: return float(r[k])
                if k.lower() in r: return float(r[k.lower()])
                if k.upper() in r: return float(r[k.upper()])
            return float(r['close']) if 'close' in r else 0.0

        return {
            'code':        code,
            'last_high':   gv(row, ['high', 'highd']),
            'high2':       gv(prev_row, ['high', 'highd']),
            'last_close':  gv(row, ['close', 'closed']),
            'close2':      gv(prev_row, ['close', 'closed']),
            'last_low':    gv(row, ['low', 'lowd']),
            'ma60':        gv(row, ['ma60', 'ma60d']),
            'ma20':        gv(row, ['ma20', 'ma20d']),
            'ma5':         gv(row, ['ma5', 'ma5d']),
        }
    except:
        return None

def tick_to_daily_bar(tick_df: pd.DataFrame) -> pd.DataFrame:
    """
    将 tick_df（MultiIndex: code, ticktime）聚合成“今天的一根日 K”
    返回：
        index: DatetimeIndex([today])
        columns: open, high, low, close, volume
    """
    if tick_df is None or tick_df.empty:
        return pd.DataFrame()

    df = tick_df.copy()
    # === 1. 取 ticktime ===
    if isinstance(df.index, pd.MultiIndex) and 'ticktime' in df.index.names:
        tick_time = pd.to_datetime(df.index.get_level_values('ticktime'))
    elif 'ticktime' in df.columns:
        tick_time = pd.to_datetime(df['ticktime'])
    else:
        # 尝试 time 列
        for col in ['time', 'date_time']:
            if col in df.columns:
                tick_time = pd.to_datetime(df[col])
                break
        else:
            return pd.DataFrame()

    df['_dt'] = tick_time
    df['_date'] = df['_dt'].dt.normalize()

    if df.empty:
        return pd.DataFrame()
        
    latest_date = df['_date'].max()
    df = df[df['_date'] == latest_date]
    
    if df.empty:
        return pd.DataFrame()

    # === 2. 价格列统一与 OHLC 获取 ===
    price_col = 'close'
    if price_col not in df.columns:
        for c in ['trade', 'price']:
            if c in df.columns:
                price_col = c
                break
    
    # 查找官方 OHLC 列
    def get_val(df, keys, fallback_func, use_last=True):
        for k in keys:
            if k in df.columns:
                valid = df[k][df[k] > 0]
                if not valid.empty:
                    return valid.iloc[-1] if use_last else valid.iloc[0]
        return fallback_func()

    try:
        open_p = get_val(df, ['open', 'nopen'], lambda: df[price_col].iloc[0], use_last=False)
        high_p = get_val(df, ['high', 'nhigh'], lambda: df[price_col].max())
        low_p = get_val(df, ['low', 'nlow'], lambda: df[price_col].min())
        close_p = df[price_col].iloc[-1]
        
        # 修正逻辑
        high_p = max(high_p, open_p, close_p)
        low_p = min(low_p, open_p, close_p)

        # 成交量
        vol_col = 'volume' if 'volume' in df.columns else ('vol' if 'vol' in df.columns else None)
        total_vol = df[vol_col].iloc[-1] if vol_col else 0 # 假设是累积的
        if vol_col and total_vol < df[vol_col].sum() / 10: # 可能不是累积的
             total_vol = df[vol_col].sum()

        bar = pd.DataFrame(
            {
                'open':   [open_p],
                'high':   [high_p],
                'low':    [low_p],
                'close':  [close_p],
                'volume': [total_vol],
            },
            index=[latest_date]
        )
        return bar
    except Exception as e:
        logger.error(f"tick_to_daily_bar error: {e}")
        return pd.DataFrame()
