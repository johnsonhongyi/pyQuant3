# -*- coding: utf-8 -*-
"""
verify_sbc_pattern.py — 统一买卖策略验证（日期感知·结构性信号）
设计原则：当卖则卖，当买则买；下跌结构出卖点，买点不管持仓。
每日最多 3 个买点 + 3 个卖点（精选最优信号点）。
"""

import pandas as pd
import sys
import os
import argparse
from datetime import datetime
import time

# ── 环境配置 ─────────────────────────────────────────────────────────────────
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'stock_standalone'))

try:
    from JSONData import tdx_data_Day as tdd
    from JohnsonUtil import johnson_cons as ct
    from realtime_data_service import IntradayEmotionTracker, DailyEmotionBaseline
    from intraday_decision_engine import IntradayDecisionEngine
    from signal_types import SignalPoint, SignalType
    from stock_visual_utils import show_chart_with_signals
except ImportError:
    from stock_standalone.JSONData import tdx_data_Day as tdd
    from stock_standalone.JohnsonUtil import johnson_cons as ct
    from stock_standalone.realtime_data_service import IntradayEmotionTracker, DailyEmotionBaseline
    from stock_standalone.intraday_decision_engine import IntradayDecisionEngine
    from stock_standalone.signal_types import SignalPoint, SignalType
    from stock_standalone.stock_visual_utils import show_chart_with_signals

# ── 常量 ─────────────────────────────────────────────────────────────────────
MAX_BUY_PER_DAY  = 3   # 每日上图买点上限
MAX_SELL_PER_DAY = 3   # 每日上图卖点上限

# 优先卖出关键词（结构性信号：反弹失败/高点下移/首次跌破均线）
PRIORITY_SELL_KW = [
    "高点下移", "反弹", "冲高回落", "乖离",
    "跌破均线", "跌破MA10", "量价背离",
    "趋势压力", "价格行为","结构派发", "结构走弱",
    "二次冲高失败", "持续下移",
]

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _ts_to_date(ts):
    """时间戳或时间字符串 → date"""
    if ts is None:
        return None
    # pandas Timestamp 或 datetime 对象
    if hasattr(ts, 'date'):
        try:
            return ts.date()
        except Exception:
            pass
    # Unix 时间戳 (float/int)
    if isinstance(ts, (int, float)) and ts > 1_000_000_000:
        return datetime.fromtimestamp(ts).date()
    # 字符串 ticktime: 'HH:MM:SS' 或 'YYYY-MM-DD HH:MM:SS'
    if isinstance(ts, str):
        try:
            if len(ts) <= 8:  # 'HH:MM:SS' → 今天
                return datetime.now().date()
            return datetime.strptime(ts[:10], '%Y-%m-%d').date()
        except Exception:
            return datetime.now().date()
    return None


def _fmt(ts) -> str:
    # pandas Timestamp 或 datetime 对象（ticktime MultiIndex reset 后）
    if hasattr(ts, 'strftime'):
        return ts.strftime("%H:%M")
    if isinstance(ts, str):
        # 'HH:MM:SS' 或 'YYYY-MM-DD HH:MM:SS'
        if " " in ts:
            ts = ts.split(" ")[1]
        return ts[:5]  # 'HH:MM'
    if isinstance(ts, (int, float)):
        if ts > 1_000_000_000:
            return datetime.fromtimestamp(ts).strftime("%H:%M")
        s = str(int(ts)).zfill(4)
        return f"{s[:2]}:{s[2:]}"
    try:
        return str(ts)[:5]
    except Exception:
        return '??:??'


def _prepare_day_df(raw: pd.DataFrame) -> pd.DataFrame:
    """标准化列名 + 计算 shift 衍生列 + 确保 DatetimeIndex"""
    df = raw.copy()
    for src, dst in [('ma60', 'ma60d'), ('ma20', 'ma20d'), ('ma5', 'ma5d'), ('ma10', 'ma10d')]:
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
        elif dst not in df.columns:
            df[dst] = df.get('close', 0)
    for n in range(1, 6):
        df[f'lasth{n}d'] = df['high'].shift(n)
        df[f'lastp{n}d'] = df['close'].shift(n)
    df['last_low']   = df['low'].shift(1)
    df['last_close'] = df['lastp1d']
    df['last_high']  = df['lasth1d']
    df = df.ffill().bfill()
    try:
        df.index = pd.to_datetime(df.index)
    except Exception:
        for col in ('date', 'trade_date'):
            if col in df.columns:
                df.index = pd.to_datetime(df[col])
                break
    return df


def _get_day_context(code: str, day_df: pd.DataFrame, tick_date):
    """
    【对齐两端逻辑链条】— 基于时间点提取严格历史基准
    确保锚点 (Yesterday High 等) 指向分时图日期 D 的前一交易日 D-1
    """
    # 1. 统一日期格式标识 (D)
    t_date_str = tick_date.strftime('%Y-%m-%d') if hasattr(tick_date, 'strftime') else str(tick_date)
    
    # 2. 选取严格早于当前分时日期的日线数据作为历史基板 (T-1 及其之前)
    # 这就是“用时间取”的核心：通过日期字符串进行索引切片隔离
    hist_day_df = day_df[day_df.index.astype(str) < t_date_str]
    
    if hist_day_df.empty:
        # 极端兜底
        return None, {}, 0.0, 0.0, 0.0, 0.0, None

    # T-1 行 (真正意义上的“昨日”)
    row = hist_day_df.iloc[-1]
    # T-2 行 (用于判定上升结构等)
    prev_row = hist_day_df.iloc[-2] if len(hist_day_df) >= 2 else row

    # 3. 构造与 DailyEmotionBaseline 对齐的审计数据组
    # 手动提取 D-1 实值，避免依赖 shift 列名冲突
    bl_data = {
        'code':          code,
        'last_high':     float(row['high']),
        'high2':         float(prev_row['high']),
        'last_close':    float(row['close']),
        'close2':        float(prev_row['close']),
        'last_low':      float(row['low']),
        # 均线参数显式传递
        'ma60d':         float(row.get('ma60', row.get('ma60d', row['close']))),
        'ma20d':         float(row.get('ma20', row.get('ma20d', row['close']))),
        'ma5d':          float(row.get('ma5',  row.get('ma5d',  row['close']))),
        'ma10d':         float(row.get('ma10', row.get('ma10d', row.get('ma10', 0)))),
    }
    bl_df = pd.DataFrame([bl_data])
    
    # 初始化基准实例并强制推演
    baseline = DailyEmotionBaseline()
    baseline._last_calc_date = None # 允许重复计算
    baseline.calculate_baseline(bl_df)

    # 4. 提取锚点字典 (用于打印和引擎内部判定)
    anchors = baseline.get_anchor(code)
    last_close = bl_data['last_close']
    ma5        = bl_data['ma5d']
    ma10       = bl_data['ma10d']
    ma60       = bl_data['ma60d']

    return baseline, anchors, last_close, ma5, ma10, ma60, row


# ── 主函数 ────────────────────────────────────────────────────────────────────

def verify_with_real_data(code: str = '688787', use_live: bool = False, show_viz: bool = True, hdf5_lock = None):
    source_name = "Sina Realtime" if use_live else "Cache PKL"
    print(f"\n🚀 [实战验证] 回放 {code} — 当卖则卖·当买则买 (Source: {source_name})")
    print("=" * 60)

    # 1. 日线数据
    try:
        resample = 'd'
        # [ALIGN] 强制对齐线上加载方式：开启 fastohlc 确保指标列名与线上一致
        # [LOCK] 如果提供了外部锁，则在锁内执行 HDF5 敏感操作
        if hdf5_lock:
            from PyQt6.QtCore import QMutexLocker
            with QMutexLocker(hdf5_lock):
                raw = tdd.get_tdx_Exp_day_to_df(
                    code, dl=ct.Resample_LABELS_Days[resample], resample=resample, fastohlc=True)
        else:
            raw = tdd.get_tdx_Exp_day_to_df(
                code, dl=ct.Resample_LABELS_Days[resample], resample=resample, fastohlc=True)

        if raw is None or raw.empty:
            print(f"❌ 无法获取 {code} 日线数据"); return None
        
        # [FIX] 统一索引为日期字符串 (解决 AttributeError)
        try:
            # 使用更稳健的转换链：to_datetime -> 检查是否为日期类型 -> 格式化
            dts = pd.to_datetime(raw.index)
            raw.index = [d.strftime('%Y-%m-%d') for d in dts]
        except Exception:
            # 兜底：从列中提取
            for col in ('date', 'trade_date'):
                if col in raw.columns:
                    raw.index = [pd.to_datetime(d).strftime('%Y-%m-%d') for d in raw[col]]
                    break
        
        day_df = _prepare_day_df(raw)
    except Exception as e:
        import traceback
        print(f"❌ 日线加载失败: {e}"); traceback.print_exc(); return

    # 2. 获取 Tick 数据源
    if use_live:
        try:
            try:
                from JSONData import sina_data
            except ImportError:
                from stock_standalone.JSONData import sina_data
            sina = sina_data.Sina()
            print(f"📡 正在从 Sina 获取 {code} 实时数据...")
            stock_df = sina.get_real_time_tick(code, enrich_data=True)
            if stock_df is None or stock_df.empty:
                print(f"❌ 无法获取 {code} 实时数据"); return
            
            stock_df = stock_df.copy()

            # Sina 返回 MultiIndex(code, ticktime) — 把 ticktime 从 index 提取成列
            if isinstance(stock_df.index, pd.MultiIndex):
                stock_df = stock_df.reset_index()
                # 过滤只保留当前 code
                if 'code' in stock_df.columns:
                    stock_df = stock_df[stock_df['code'] == code].copy()
                # ticktime 现在是列，直接用字符串格式 'YYYY-MM-DD HH:MM:SS'
                # 转为 RangeIndex 便于 itertuples
                stock_df = stock_df.reset_index(drop=True)
            elif stock_df.index.name == 'ticktime':
                # 单层 ticktime index
                stock_df = stock_df.reset_index()

            # 兼容性转换：Sina 实时数据列名标准化
            mapping = {
                'trade': 'close',
                'volume': 'volume',
                'amount': 'amount'
            }
            for src, dst in mapping.items():
                if src in stock_df.columns and dst not in stock_df.columns:
                    stock_df[dst] = stock_df[src]
            
            # 如果没有 high/low，用 close 替代 (Tick 数据特性)
            for col in ['high', 'low']:
                if col not in stock_df.columns:
                    stock_df[col] = stock_df['close']
            
            # Open 价逻辑：对于分时 Tick，每一笔的开盘价是上一笔的收盘价
            if 'open' not in stock_df.columns:
                stock_df['open'] = stock_df['close'].shift(1).fillna(stock_df['close'])


            print(f"✅ 成功获取 {len(stock_df)} 条实时数据")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ 获取实时数据失败: {e}"); return
    else:
        # 分钟线缓存
        cache_path = r"G:\minute_kline_cache.pkl"
        if not os.path.exists(cache_path):
            print(f"❌ 未找到缓存: {cache_path}"); return
        try:
            full = pd.read_pickle(cache_path)
            stock_df = full[full['code'] == code].copy().sort_values('time')
            if stock_df.empty:
                print(f"❌ 缓存中无 {code} 数据"); return
            print(f"✅ 成功加载 {len(stock_df)} 条分钟线数据")
            print(f"💰 价格区间: {stock_df['low'].min():.2f} – {stock_df['high'].max():.2f}\n")
        except Exception as e:
            print(f"❌ 读取缓存失败: {e}"); return

    # 3. 逐分钟回放（日期感知）
    tracker = IntradayEmotionTracker()
    engine  = IntradayDecisionEngine()
    signals: list = []

    # 生成用于图表 X 轴的字符串时间标签
    time_labels = []
    times = []
    if use_live:
        # live 模式：优先用 ticktime（实际成交时间）而非可能是抓取时间的 time 列
        if 'ticktime' in stock_df.columns:
            times = stock_df['ticktime'].tolist()
        elif 'time' in stock_df.columns:
            times = stock_df['time'].tolist()
    else:
        # cache 模式：index 是 DatetimeIndex 或 time 是 Unix 时间戳
        if isinstance(stock_df.index, pd.DatetimeIndex):
            times = (stock_df.index.view('int64') // 10**9).tolist()
        elif 'time' in stock_df.columns:
            times = stock_df['time'].tolist()

    if not times:
        now = time.time()
        times = [now + i * 60 for i in range(len(stock_df))]

    time_labels = [_fmt(t) for t in times]

    # 日期状态（每日边界重置）
    current_date = None
    baseline     = None
    anchors: dict  = {}
    last_close = ma5 = ma10 = ma60 = 0.0
    cum_vol = cum_amt = 0.0
    prices_so_far: list = []
    lows_so_far:   list = []
    day_high   = 0.0
    snapshot:  dict = {}
    day_buy_cnt = day_sell_cnt = 0

    print("Processing ticks...")
    for i, row in enumerate(stock_df.itertuples()):
        # 统一获取各列，带 fallback
        # live 模式下直接用 times[i]（已优先选择 ticktime）避免 getattr 拿到错误列
        if use_live and i < len(times):
            r_time = times[i]
        else:
            r_time = getattr(row, 'time', times[i] if i < len(times) else time.time())
        r_close = getattr(row, 'close', getattr(row, 'trade', 0.0))
        r_open = getattr(row, 'open', getattr(row, 'buy', r_close))
        r_high = getattr(row, 'high', r_close)
        r_low = getattr(row, 'low', r_close)
        r_vol = getattr(row, 'volume', getattr(row, 'vol', 0.0))
        r_tick_vol = getattr(row, 'tick_vol', r_vol)

        tick_date = _ts_to_date(r_time)
        if tick_date is None:
            # 对于 live 模式，ticktime 是字符串，_ts_to_date 已正确处理
            # 若仍然为 None，使用今天日期强制继续
            from datetime import date as _date
            tick_date = _date.today()

        # ── 日期边界：重建当日历史锚点 ──────────────────────────────────────
        if tick_date != current_date:
            ctx = _get_day_context(code, day_df, tick_date)
            if ctx[0] is None:
                continue
            baseline, anchors, last_close, ma5, ma10, ma60, _ = ctx

            current_date = tick_date
            cum_vol = cum_amt = 0.0
            prices_so_far, lows_so_far = [], []
            day_high = last_close
            tracker._last_sbc_status = {}  # type: ignore[attr-defined]
            day_buy_cnt = day_sell_cnt = 0

            # snapshot 仅保留必要的日线和基础结构数据，不 mock 持仓，避免提前触发硬止损
            snapshot = {
                "cost_price":        0.0,
                "highest_since_buy": 0.0,
                "last_close":        last_close,
                "loss_streak":       0,
                "market_win_rate":   0.5,
                "day_df":            day_df,
            }
            print(f"\n── {tick_date} | 昨收:{last_close:.2f}"
                  f" | 昨高:{anchors.get('yesterday_high', 0):.2f}"
                  f" | MA5:{ma5:.2f} | MA10:{ma10:.2f} ──")
            print(f"   [DEBUG] Engine Anchors: {baseline.get_anchor(code)}")

        # ── 累计 VWAP ────────────────────────────────────────────────────────
        # 如果是 enriched 数据，直接用它算的 cum_vol 和 cum_amt；否则手动累加
        v = r_tick_vol
        a = getattr(row, 'amount', v * r_close)
        
        cum_vol += v
        cum_amt += a
        nclose = getattr(row, 'avg_price', cum_amt / cum_vol if cum_vol > 0 else r_close)
        pct    = (r_close - last_close) / last_close * 100 if last_close else 0.0

        tick_data = pd.DataFrame([{
            'code':    code,
            'trade':   r_close,
            'high':    r_high,
            'low':     r_low,
            'vol':     cum_vol,
            'volume':  getattr(row, 'volume_ratio', 1.0),
            'amount':  cum_amt,
            'percent': pct,
            'avg_price': nclose,
        }])

        # ── 3.1 买入评估（SBC，每日最多 MAX_BUY_PER_DAY 个）────────────────
        tracker.update_batch(tick_data, baseline)
        status = tick_data['sbc_status'].iloc[0]
        if status and "🚀" in str(status) and day_buy_cnt < MAX_BUY_PER_DAY:
            t_str = _fmt(r_time)
            print(f"[{t_str}] 🎯 买入: {status} at {r_close:.2f}")
            signals.append(SignalPoint(code, r_time, i, r_close,
                                       SignalType.FOLLOW, reason=str(status)))
            day_buy_cnt += 1

        # ── 3.2 卖出评估（结构性信号，不依赖持仓）───────────────────────────
        prices_so_far.append(r_close)
        lows_so_far.append(r_low)
        day_high = max(day_high, r_high)

        if r_high > snapshot["highest_since_buy"]:
            snapshot["highest_since_buy"] = r_high
        snapshot.update({
            "nclose":        nclose,
            "highest_today": day_high,
            "low_val":       min(lows_so_far),
        })

        row_dict = {
            'code':    code,
            'trade':   row.close,
            'high':    row.high,
            'low':     row.low,
            'open':    row.open,
            'volume':  getattr(row, 'volume_ratio', 1.0),
            'vol':     v,
            'percent': pct,
            'nclose':  nclose,
            # 关键：直接用从 day_df 行读到的 MA 值 ↓
            'ma5d':    ma5,
            'ma10d':   ma10,
        }
        decision = engine.evaluate(row_dict, snapshot, mode="sell_only")
        action   = decision.get("action", "")
        reason   = decision.get("reason", "")

        sell_actions = {
            "卖出", "止损", "预警止损", "移动止盈", "高位止盈",
            "趋势止损", "破位减仓", "强制清仓",
            "主动防守", "主动减仓", "流动性预警",
        }
        if action in sell_actions:
            t_str       = _fmt(r_time)
            is_priority = any(kw in reason for kw in PRIORITY_SELL_KW)

            if day_sell_cnt < MAX_SELL_PER_DAY and is_priority:
                print(f"[{t_str}] ⚠️  卖出: {action} at {row.close:.2f} | {reason}")
                signals.append(SignalPoint(code, r_time, i, row.close,
                                           SignalType.EXIT_FOLLOW, reason=reason))
                day_sell_cnt += 1
            elif day_sell_cnt < MAX_SELL_PER_DAY and action in ("止损", "强制清仓", "主动减仓"):
                # 非结构性但强力止损：仅打印参考
                print(f"[{t_str}]   止损参考: {action} at {row.close:.2f} | {reason}")
            # else: 已达上限或噪音，静默

    # 4. 统计 & 可视化
    buy_cnt  = sum(1 for s in signals if s.signal_type in [SignalType.BUY, SignalType.FOLLOW])
    sell_cnt = sum(1 for s in signals if s.signal_type in [SignalType.SELL, SignalType.EXIT_FOLLOW])
    print(f"\n{'='*60}")
    print(f"✅ 回放完成: {buy_cnt} 个买点  |  {sell_cnt} 个卖出点")


    # 计算 VWAP 曲线
    # live 模式使用 tick_vol（增量成交量），cache 模式使用 volume
    import numpy as np
    c_arr = stock_df['close'].values if 'close' in stock_df.columns else stock_df['trade'].values
    # tick_vol: enrich_data=True 后的增量成交量；fallback 到 volume
    if 'tick_vol' in stock_df.columns:
        v_arr_vwap = stock_df['tick_vol'].values.astype(float)
    elif 'volume' in stock_df.columns:
        v_arr_vwap = stock_df['volume'].values.astype(float)
    else:
        v_arr_vwap = np.ones(len(stock_df))
    cv = np.maximum(v_arr_vwap.cumsum(), 1e-9)  # 防除零
    ca = (v_arr_vwap * c_arr).cumsum()
    vwap_series = (ca / cv).tolist()

    # 准备可视化 DataFrame：open/high/low/close 都已标准化
    # volume 在 viz_df 里不参与 K 线渲染，只作备用
    viz_df = pd.DataFrame({
        'open':   stock_df['open'].values if 'open' in stock_df.columns else c_arr,
        'high':   stock_df['high'].values if 'high' in stock_df.columns else c_arr,
        'low':    stock_df['low'].values  if 'low'  in stock_df.columns else c_arr,
        'close':  c_arr,
        'volume': v_arr_vwap,
    })

    # 5. 可视化
    if show_viz:
        return show_chart_with_signals(
            viz_df, signals,
            f"[{code}] 买卖验证 — 结构性信号",
            avg_series=vwap_series,
            time_labels=time_labels,
            use_line=use_live,  # live 模式用线图，避免密集竖柱
        )
    else:
        # 返回数据包，供 GUI 线程异步渲染
        return {
            "viz_df": viz_df,
            "signals": signals,
            "title": f"[{code}] 买卖验证 — 结构性信号",
            "avg_series": vwap_series,
            "time_labels": time_labels,
            "use_live": use_live
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SBC Pattern Verification Tool")
    parser.add_argument("code", nargs="?", default="688787", help="Stock code (default: 688787)")
    parser.add_argument("--live", action="store_true", help="Use live Sina data instead of cache")
    args = parser.parse_args()

    verify_with_real_data(args.code, use_live=args.live)
