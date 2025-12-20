import re
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Optional, Union, Callable
from JohnsonUtil import LoggerFactory
import logging
import tkinter as tk
# 获取或创建日志记录器
logger: logging.Logger = LoggerFactory.getLogger("instock_TK.StockLogic")

# === 概念过滤逻辑 ===
GENERIC_KEYWORDS = [
    "国企改革", "沪股通", "深股通", "融资融券", "高股息", "MSCI", "中字头",
    "央企改革", "标普概念", "B股", "AH股", "转融券", "股权转让", "新股与次新股",
    "战略", "指数", "主题", "计划", "预期", "改革", "通", "国企", "央企"
]

REAL_CONCEPT_KEYWORDS = [
    "半导体", "AI", "机器人", "光伏", "锂电", "医药", "芯片", "5G", "储能",
    "新能源", "军工", "卫星", "航天", "汽车", "算力", "氢能", "量子", "云计算",
    "电商", "游戏", "消费电子", "数据要素", "AI", "大模型"
]

def is_generic_concept(concept_name: str) -> bool:
    """识别是否为泛概念（需过滤）"""
    if any(k in concept_name for k in REAL_CONCEPT_KEYWORDS):
        return False
    if any(k in concept_name for k in GENERIC_KEYWORDS):
        return True
    if len(concept_name) <= 3:
        return True
    if any(x in concept_name for x in ["通", "改革", "指数", "主题", "计划", "战略", "预期"]):
        return True
    return False

def filter_concepts(cat_dict: dict[str, Any]) -> dict[str, Any]:
    """批量过滤概念"""
    INVALID: list[str] = [
        "国企改革", "沪股通", "深股通", "融资融券", "MSCI", "富时", 
        "标普", "中字头", "央企", "基金重仓", "机构重仓", "大盘股", "高股息"
    ]
    VALID_HINTS: list[str] = [
        "能源", "科技", "芯片", "AI", "人工智能", "光伏", "储能", 
        "汽车", "机器人", "碳", "半导体", "电力", "通信", "军工", "医药"
    ]
    res: dict[str, Any] = {}
    for k, v in cat_dict.items():
        if any(bad in k for bad in INVALID):
            continue
        if len(v) > 500 or len(v) < 2:
            continue
        if not any(ok in k for ok in VALID_HINTS):
            continue
        res[k] = v
    return res

def ensure_parentheses_balanced(expr: str) -> str:
    """自动补齐括号并确保外层有括号"""
    expr = expr.strip()
    left_count = expr.count("(")
    right_count = expr.count(")")

    if left_count > right_count:
        expr += ")" * (left_count - right_count)
    elif right_count > left_count:
        expr = "(" * (right_count - left_count) + expr

    if not (expr.startswith("(") and expr.endswith(")")):
        expr = f"({expr})"
    return expr

def remove_invalid_conditions(query: str, invalid_cols: list[str]) -> str:
    """从 query 表达式中剔除包含无效列的条件"""
    query = re.sub(r'\s+', ' ', query).strip()
    for col in invalid_cols:
        pattern: str = (
            rf'(\b(and|or)\s+[^()]*\b{col}\b[^()]*?)'
            rf'|(\([^()]*\b{col}\b[^()]*\))'
            rf'|([^()]*\b{col}\b[^()]*\s+(and|or))'
            rf'|([^()]*\b{col}\b[^()]*)'
        )
        query = re.sub(pattern, lambda m: "", query, flags=re.IGNORECASE)

    query = re.sub(r'\s+(and|or)\s+(\)|$)', ' ', query)
    query = re.sub(r'(\(|^)\s*(and|or)\s+', ' ', query)
    query = re.sub(r'\s{2,}', ' ', query).strip()

    open_count: int = query.count("(")
    close_count: int = query.count(")")
    if open_count > close_count:
        query += ")" * (open_count - close_count)
    elif close_count > open_count:
        query = "(" * (close_count - open_count) + query
    return query

def test_code_against_queries(df_code: pd.DataFrame, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """测试单只股票是否符合多个查询条件"""
    if not isinstance(df_code, pd.DataFrame) or df_code.empty:
        return []

    results: list[dict[str, Any]] = []
    for q in queries:
        expr: Any = q.get("query", "")
        if not isinstance(expr, str) or not expr:
            continue
            
        final_query: str = expr
        query_engine: str = 'numexpr'
        
        if not (expr.isdigit() and len(expr) == 6):
            bracket_patterns: list[str] = re.findall(r'\s+and\s+(\([^\(\)]*\))', expr)
            temp_query: str = expr
            for bracket in bracket_patterns:
                temp_query = temp_query.replace(f'and {bracket}', '')

            conditions: list[str] = [c.strip() for c in temp_query.split('and')]
            valid_conditions: list[str] = []
            removed_conditions: list[str] = []
            
            for cond in conditions:
                cond_clean: str = cond.lstrip('(').rstrip(')')
                if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or '==' in cond or 'or' in cond:
                    if not any(bp.strip('() ').strip() == cond_clean for bp in bracket_patterns):
                        valid_conditions.append(ensure_parentheses_balanced(cond))
                        continue

                cols_in_cond: list[str] = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)
                if all(col in df_code.columns for col in cols_in_cond):
                    valid_conditions.append(cond_clean)
                else:
                    removed_conditions.append(cond_clean)

            if not valid_conditions:
                continue

            final_query = ' and '.join(f"({c})" for c in valid_conditions)
            if bracket_patterns:
                final_query += ' and ' + ' and '.join(bracket_patterns)
            
            final_query = ensure_parentheses_balanced(final_query)

            if 'or' in expr and '(' in expr:
                final_query = expr
                if removed_conditions:
                    final_query = remove_invalid_conditions(final_query, removed_conditions)
                query_engine = 'python' if 'index.' in final_query.lower() or '.str' in final_query else 'numexpr'
            else:
                if 'index.' in final_query.lower():
                    query_engine = 'python'

        hit_count: int = 0
        try:
            df_hit: pd.DataFrame = df_code.query(final_query, engine=query_engine)
            hit_count = len(df_hit)
        except Exception as e:
            logger.error(f"执行 query 出错: {final_query}, {e}")

        results.append({
            "query": expr,
            "note": q.get("note", ""),
            "starred": q.get("starred", 0),
            "hit": hit_count
        })
    return results

def estimate_virtual_volume_simple(now=None):
    """估算当前时间已完成的成交量比例"""
    if now is None:
        now = datetime.now()
    t = now.time()
    minutes = t.hour * 60 + t.minute

    segments = [
        (9*60+30, 10*60, 0.25),
        (10*60, 11*60, 0.50),
        (11*60, 11*60+30, 0.60),
        (13*60, 14*60, 0.78),
        (14*60, 15*60, 1.00),
    ]

    passed_ratio = 0.0
    prev_ratio = 0.0

    for start, end, ratio in segments:
        if minutes <= start:
            passed_ratio = prev_ratio
            break
        elif start < minutes <= end:
            seg_progress = (minutes - start) / (end - start)
            passed_ratio = prev_ratio + (ratio - prev_ratio) * seg_progress
            break
        prev_ratio = ratio
    else:
        passed_ratio = 1.0

    return max(passed_ratio, 0.05)

def get_row_tags(latest_row: Union[pd.Series, dict[str, Any]]) -> list[str]:
    """
    根据最新行情数据返回 Treeview 行标签列表
    """
    row_tags: list[str] = []

    low: Any = latest_row.get("low")
    lastp1d: Any = latest_row.get("lastp1d")
    high: Any = latest_row.get("high")
    high4: Any = latest_row.get("high4")
    ma5d: Any = latest_row.get("ma5d")
    ma20d: Any = latest_row.get("ma20d")
    percent_val: Any = latest_row.get("percent", latest_row.get("per1d", 0))

    # 1️⃣ 红色：低点 > 昨收
    if pd.notna(low) and pd.notna(lastp1d):
        if low > lastp1d:
            row_tags.append("red_row")

    # 2️⃣ 橙色：高点或低点突破 high4
    if pd.notna(high) and pd.notna(high4):
        if high > high4 or (pd.notna(low) and low > high4):
            row_tags.append("orange_row")

    # 3️⃣ 紫色：弱势，低于 ma5d
    if pd.notna(high) and pd.notna(ma5d):
        if high < ma5d:
            row_tags.append("purple_row")

    # 4️⃣ 黄色：临界或预警，低于 ma20d
    if pd.notna(low) and pd.notna(ma20d):
        if low < ma20d:
            row_tags.append("yellow_row")

    # 5️⃣ 绿色：跌幅明显 <2% 且低于昨收
    if pd.notna(percent_val) and pd.notna(low) and pd.notna(lastp1d):
        if percent_val < 2 and low < lastp1d:
            row_tags.append("green_row")
    return row_tags

def safe_prev_signal_array(df: Optional[pd.DataFrame]) -> np.ndarray:
    """
    生成 prev_signal_arr，确保不会因为 df 异常、空值、结构错误而崩溃。
    """
    if df is None or df.empty:
        return np.array([])

    if 'prev_signal' not in df.columns:
        df.loc[:, 'prev_signal'] = None

    raw_vals: list[Any] = df['prev_signal'].tolist()
    safe_vals: list[int] = []
    for v in raw_vals:
        if isinstance(v, (pd.Series, np.ndarray, list, tuple, dict)):
            safe_vals.append(0)
            continue
        if isinstance(v, str):
            safe_vals.append(1 if v in ('BUY_N', 'BUY_S') else 0)
            continue
        if v is None or (isinstance(v, float) and np.isnan(v)):
            safe_vals.append(0)
            continue
        safe_vals.append(0)
    return np.array(safe_vals)

def toast_message(master, text, duration=1500):
    """短暂提示信息（浮层，不阻塞）"""
    toast = tk.Toplevel(master)
    toast.overrideredirect(True)
    toast.attributes("-topmost", True)
    label = tk.Label(toast, text=text, bg="black", fg="white", padx=10, pady=1)
    label.pack()
    try:
        master.update_idletasks()
        master_x = master.winfo_rootx()
        master_y = master.winfo_rooty()
        master_w = master.winfo_width()
    except Exception:
        master_x, master_y, master_w = 100, 100, 400
    toast.update_idletasks()
    toast_w = toast.winfo_width()
    toast_h = toast.winfo_height()
    toast.geometry(f"{toast_w}x{toast_h}+{master_x + (master_w-toast_w)//2}+{master_y + 50}")
    toast.after(duration, toast.destroy)

class RealtimeSignalManager:
    state: dict[str, Any]

    def __init__(self) -> None:
        self.state = {}

    def update_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = ''
        df['signal_strength'] = 0

        if 'code' in df.columns:
            # 兼容处理，避免重复 index 报错
            if not isinstance(df.index, pd.Index) or df.index.name != 'code':
                df.set_index('code', inplace=True, drop=False)

        for code, row in df.iterrows():
            if code not in self.state:
                self.state[code] = {
                    'prev_now': row.get('now', 0),
                    'today_high': row.get('high', 0),
                    'today_low': row.get('low', 0),
                    'prev_signal': None,
                    'down_streak': 0,
                    'recent_vols': [row.get('volume', 0)]
                }

        codes = df['code'].values
        prev_now_arr = np.array([self.state[c]['prev_now'] for c in codes])
        today_high_arr = np.array([self.state[c]['today_high'] for c in codes])
        today_low_arr = np.array([self.state[c]['today_low'] for c in codes])
        down_streak_arr = np.array([self.state[c]['down_streak'] for c in codes])
        recent_vols_list = [self.state[c]['recent_vols'] for c in codes]

        now_arr = df['now'].values
        high_arr = df['high'].values
        low_arr = df['low'].values
        volume_arr = df['volume'].values
        ma51d = df.get('ma51d', now_arr).values if 'ma51d' in df.columns else now_arr
        ma10d = df.get('ma10d', now_arr).values if 'ma10d' in df.columns else now_arr
        lastp1d = df.get('lastp1d', now_arr).values if 'lastp1d' in df.columns else now_arr
        lastp2d = df.get('lastp2d', now_arr).values if 'lastp2d' in df.columns else now_arr
        lastp3d = df.get('lastp3d', now_arr).values if 'lastp3d' in df.columns else now_arr
        macddif = df.get('macddif', 0).values if 'macddif' in df.columns else np.zeros(len(df))
        macddea = df.get('macddea', 0).values if 'macddea' in df.columns else np.zeros(len(df))
        macd = df.get('macd', 0).values if 'macd' in df.columns else np.zeros(len(df))
        macdlast1 = df.get('macdlast1', 0).values if 'macdlast1' in df.columns else np.zeros(len(df))
        macdlast2 = df.get('macdlast2', 0).values if 'macdlast2' in df.columns else np.zeros(len(df))
        macdlast3 = df.get('macdlast3', 0).values if 'macdlast3' in df.columns else np.zeros(len(df))
        rsi = df.get('rsi', 50).values if 'rsi' in df.columns else np.full(len(df), 50.0)
        kdj_j = df.get('kdj_j', 50).values if 'kdj_j' in df.columns else np.full(len(df), 50.0)
        kdj_k = df.get('kdj_k', 50).values if 'kdj_k' in df.columns else np.full(len(df), 50.0)
        kdj_d = df.get('kdj_d', 50).values if 'kdj_d' in df.columns else np.full(len(df), 50.0)
        open_arr = df['open'].values

        today_high_arr = np.maximum(today_high_arr, high_arr)
        today_low_arr = np.minimum(today_low_arr, low_arr)

        avg_vol_arr = np.array([np.mean((recent + [v])[-5:]) for recent, v in zip(recent_vols_list, volume_arr)])
        vol_boom_now = volume_arr > avg_vol_arr

        trend_up = ma51d > ma10d
        price_rise = (lastp1d > lastp2d) & (lastp2d > lastp3d)
        macd_bull = (macddif > macddea) & (macd > 0)
        macd_accel = (macdlast1 > macdlast2) & (macdlast2 > macdlast3)
        rsi_mid = (rsi > 45) & (rsi < 75)
        kdj_bull = (kdj_j > kdj_k) & (kdj_k > kdj_d)
        kdj_strong = kdj_j > 60
        morning_gap_up = open_arr <= low_arr * 1.001
        intraday_up = now_arr > prev_now_arr
        intraday_high_break = now_arr > today_high_arr
        intraday_low_break = now_arr < today_low_arr

        down_streak_arr = np.where(now_arr < prev_now_arr, down_streak_arr + 1, 0)

        score = np.zeros(len(df))
        score += trend_up * 2
        score += price_rise * 1
        score += macd_bull * 1
        score += macd_accel * 2
        score += rsi_mid * 1
        score += np.nan_to_num(rsi - 50) * 0.05
        score += kdj_bull * 1
        score += kdj_strong * 1
        score += morning_gap_up * 2
        score += intraday_up * 1
        score += intraday_high_break * 2
        score += vol_boom_now * 1
        score += ((down_streak_arr >= 2) & (now_arr > prev_now_arr * 1.005)) * 2

        prev_signal_arr = safe_prev_signal_array(df)
        score += prev_signal_arr

        df['signal_strength'] = score
        df['signal'] = ''
        df.loc[score >= 9, 'signal'] = 'BUY_S'
        df.loc[(score >= 6) & (score < 9), 'signal'] = 'BUY_N'
        df.loc[(score < 6) & (macd < 0), 'signal'] = 'SELL_WEAK'

        sell_cond = ((macddif < macddea) & (macd < 0)) | ((rsi < 45) & (kdj_j < kdj_k)) | ((now_arr < ma51d) & (macdlast1 < macdlast2)) | intraday_low_break
        df.loc[sell_cond, 'signal'] = 'SELL'

        for i, code in enumerate(codes):
            s = self.state[code]
            s['prev_now'] = now_arr[i]
            s['today_high'] = today_high_arr[i]
            s['today_low'] = today_low_arr[i]
            s['down_streak'] = down_streak_arr[i]
            recent_vols_list[i].append(volume_arr[i])
            if len(recent_vols_list[i]) > 5:
                recent_vols_list[i] = recent_vols_list[i][-5:]
            s['recent_vols'] = recent_vols_list[i]
            s['prev_signal'] = df.at[code, 'signal']

        return df

def calc_support_resistance(df: pd.DataFrame) -> pd.DataFrame:
    """
    根据通达信逻辑计算撑压位（压力）和支撑位
    """
    LLV: Callable[[pd.Series, int], pd.Series] = lambda x, n: x.rolling(n, min_periods=1).min()
    HHV: Callable[[pd.Series, int], pd.Series] = lambda x, n: x.rolling(n, min_periods=1).max()
    SMA: Callable[[pd.Series, int, int], pd.Series] = lambda x, n, m: x.ewm(alpha=m/n, adjust=False).mean()

    RSV13: pd.Series = (df['close'] - LLV(df['low'], 13)) / (HHV(df['high'], 13) - LLV(df['low'], 13)) * 100
    ARSV: pd.Series = SMA(RSV13, 3, 1)
    AK: pd.Series = SMA(ARSV, 3, 1)
    AD: pd.Series = 3 * ARSV - 2 * AK

    RSV55: pd.Series = (df['close'] - LLV(df['low'], 55)) / (HHV(df['high'], 55) - LLV(df['low'], 55)) * 100
    ARSV24: pd.Series = SMA(RSV55, 3, 1)
    AK24: pd.Series = SMA(ARSV24, 3, 1)
    AD24: pd.Series = 3 * ARSV24 - 2 * AK24

    cross_up: pd.Series = (AD24 > AD) & (AD24.shift(1) <= AD.shift(1))

    pressure: list[Optional[float]] = []
    last_high: Optional[float] = None
    for i in range(len(df)):
        if cross_up.iloc[i]:
            last_high = float(df['high'].iloc[i])
        pressure.append(last_high)
    df.loc[:, 'pressure'] = pressure
    df.loc[:, 'support'] = LLV(df['high'], 30)
    return df

def calc_breakout_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["signal_strength"] = 0
    df["signal"] = ""

    ma_short = df.get('ma51d', df['close']).values
    ma_mid = df.get('ma10d', df['close']).values

    cond_trend_up = (df['close'] > ma_short) & (ma_short > ma_mid)
    cond_trend_turn = (df['close'] > ma_short) & (df['ma51d'].diff() > 0)
    cond_price_rise = (df['lastp1d'] > df['lastp2d']) & (df['lastp2d'] > df['lastp3d'])

    cond_macd_bull = (df['macddif'] > df['macddea']) & (df['macd'] > 0)
    cond_macd_accel = (df['macdlast1'] > df['macdlast2']) & (df['macdlast2'] > df['macdlast3'])

    cond_rsi_mid = (df['rsi'] > 45) & (df['rsi'] < 75)
    cond_rsi_up = df['rsi'].diff() > 2

    cond_kdj_bull = (df['kdj_j'] > df['kdj_k']) & (df['kdj_k'] > df['kdj_d'])
    cond_kdj_strong = (df['kdj_j'] > 60)

    cond_break_high = df['close'] > df['lasth3d']
    cond_break_mid = df['close'] > df.get('max5', df['close'])

    cond_vol_boom = df['volume'] > 1

    score = 0
    score += cond_trend_up * 2
    score += cond_trend_turn * 1
    score += cond_price_rise * 1
    score += cond_macd_bull * 1
    score += cond_macd_accel * 2
    score += cond_rsi_mid * 1
    score += cond_rsi_up * 1
    score += cond_kdj_bull * 1
    score += cond_kdj_strong * 1
    score += cond_break_high * 2
    score += cond_break_mid * 1
    score += cond_vol_boom * 1

    df['signal_strength'] = score
    df.loc[df['signal_strength'] >= 8, 'signal'] = 'BUY_S'
    df.loc[(df['signal_strength'] >= 5) & (df['signal_strength'] < 8), 'signal'] = 'BUY_N'
    df.loc[(df['signal_strength'] < 5) & (df['macd'] < 0), 'signal'] = 'SELL_WEAK'

    sell_cond = (
        ((df['macddif'] < df['macddea']) & (df['macd'] < 0)) |
        ((df['rsi'] < 45) & (df['kdj_j'] < df['kdj_k'])) |
        ((df['close'] < ma_short) & (df['macdlast1'] < df['macdlast2']))
    )
    df.loc[sell_cond, "signal"] = "SELL"
    return df

# 管理器实例
signal_manager = RealtimeSignalManager()

def detect_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    if "code" not in df.columns:
        df["code"] = df.index.astype(str).str.zfill(6)

    df["signal"] = ""
    df["emotion"] = "中性"

    df = signal_manager.update_signals(df.copy())

    df.loc[df.get("volume", 0) > 1.2, "emotion"] = "乐观"
    df.loc[df.get("volume", 0) < 0.8, "emotion"] = "悲观"
    return df
