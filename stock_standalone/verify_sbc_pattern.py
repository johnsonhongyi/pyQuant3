# -*- coding: utf-8 -*-
"""
verify_sbc_pattern.py — 统一买卖策略验证（日期感知·结构性信号）
设计原则：当卖则卖，当买则买；下跌结构出卖点，买点不管持仓。
每日最多 3 个买点 + 3 个卖点（精选最优信号点）。
"""

import pandas as pd
import numpy as np
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
    from JohnsonUtil.commonTips import timed_ctx, print_timing_summary
    from signal_types import SignalType
    from stock_visual_utils import show_chart_with_signals
    import sbc_core as sbc_core
except ImportError:
    from stock_standalone.JSONData import tdx_data_Day as tdd
    from stock_standalone.JohnsonUtil import johnson_cons as ct
    from stock_standalone.JohnsonUtil.commonTips import timed_ctx, print_timing_summary
    from stock_standalone.signal_types import SignalType
    from stock_standalone.stock_visual_utils import show_chart_with_signals
    import stock_standalone.sbc_core as sbc_core

# ── 常量 ─────────────────────────────────────────────────────────────────────
MAX_BUY_PER_DAY  = 3   # 每日上图买点上限

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _fts(ts) -> str:
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

    for n in range(1, 6):
        df[f'lasth{n}d'] = df['high'].shift(n)
        df[f'lastp{n}d'] = df['close'].shift(n)
        df[f'lastl{n}d'] = df['low'].shift(n)
    df['last_low']   = df['lastl1d']
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


# ── 主函数 ────────────────────────────────────────────────────────────────────

def fetch_daily_data(code, days=150, hdf5_lock=None):
    """获取日线数据，默认获取150天以确保MA60稳定"""
    resample = 'd'
    if hdf5_lock:
        from PyQt6.QtCore import QMutexLocker
        with QMutexLocker(hdf5_lock):
            raw = tdd.get_tdx_Exp_day_to_df(
                code, dl=days, resample=resample, fastohlc=False)
    else:
        raw = tdd.get_tdx_Exp_day_to_df(
            code, dl=days, resample=resample, fastohlc=False)
    return raw

def verify_with_real_data(code: str = '688787', use_live: bool = False, show_viz: bool = True, hdf5_lock = None, extra_lines = None, days: int = 1, verbose: bool = False, concise: bool = True):
    source_name = "Sina Realtime" if use_live else "Cache PKL"
    print(f"\n🚀 [实战验证] 回放 {code} — 当卖则卖·当买则买 (Source: {source_name})")
    print("=" * 60)

    # 1. 日线数据
    try:
        resample = 'd'
        
        # [OPT] 如果传入了 TK 的整行 df_all 数据，则利用其伪造一个 day_df，节省本地读取
        if extra_lines and extra_lines.get('df_all_row'):
            print("🚀 使用 TK df_all_row 构建基准常数，跳过本地 tdd 读取...")
            r = extra_lines['df_all_row']
            val_h1  = r.get('lasth1d', r.get('high', 0))
            val_l1  = r.get('lastl1d', r.get('low', 0))
            val_c1  = r.get('lastp1d', r.get('close', 0))
            val_h2  = r.get('lasth2d', val_h1)
            val_c2  = r.get('lastp2d', val_c1)
            
            # 构建一个具有兼容时序的 4 行 DataFrame（采用极老的硬编码日期确保一定被视为 history）
            fake_dates = ['2000-01-01', '2000-01-02', '2000-01-03', '2000-01-04']
            records = [
                {'high': val_h1, 'close': val_c1, 'low': val_l1},  # prev3
                {'high': val_h1, 'close': val_c1, 'low': val_l1},  # prev2
                {'high': val_h2, 'close': val_c2, 'low': val_l1},  # prev1
                r.copy()  # prev (最终将作为 baseline 取用)
            ]
            
            # 对基准行对齐必须的字段名称
            records[-1]['close'] = val_c1
            records[-1]['high'] = val_h1
            records[-1]['low'] = val_l1
            records[-1]['ma5d'] = r.get('ma51d', val_c1)
            records[-1]['ma10d'] = r.get('ma101d', val_c1)
            records[-1]['ma20d'] = r.get('ma201d', val_c1)
            records[-1]['ma60d'] = r.get('ma601d', val_c1)
            records[-1]['last_close'] = val_c1
            records[-1]['last_high']  = val_h1
            records[-1]['last_low']   = val_l1
            records[-1]['lasth4d']    = r.get('high4', val_h1)

            day_df = pd.DataFrame(records, index=fake_dates)
        else:
            # [ALIGN] 强制对齐线上加载方式：开启 fastohlc 确保指标列名与线上一致
            if hdf5_lock:
                from PyQt6.QtCore import QMutexLocker
                with QMutexLocker(hdf5_lock):
                    raw = tdd.get_tdx_Exp_day_to_df(code, dl=ct.Resample_LABELS_Days[resample], resample=resample, fastohlc=False)
            else:
                raw = tdd.get_tdx_Exp_day_to_df(code, dl=ct.Resample_LABELS_Days[resample], resample=resample, fastohlc=False)

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
    # 2. 获取 Tick 数据源 (使用 sbc_core 统筹加载与补全逻辑)
    try:
        # 支持多日显示：如果 days > 1，尝试获取更多历史分钟线 (all_10000)
        l_time = None if days <= 1 else 10000
        stock_df = sbc_core.load_tick_data(code, use_live=use_live, limit_time=l_time)
        if stock_df is None or stock_df.empty:
            print(f"❌ 无法获取 {code} 数据（Cache & Sina 均失败）")
            return None
        
        # 统一标准化处理 (兼容 load_tick_data 返回)
        if 'trade' in stock_df.columns and 'close' not in stock_df.columns:
            stock_df['close'] = stock_df['trade']
        if 'tick_vol' in stock_df.columns and 'volume' not in stock_df.columns:
            stock_df['volume'] = stock_df['tick_vol']
        
        # 确保基础列存在供后续逻辑使用
        for col in ['high', 'low', 'open']:
            if col not in stock_df.columns:
                stock_df[col] = stock_df['close']

        print(f"✅ 成功加载 {len(stock_df)} 条数据 (Source: {source_name})")
        if not stock_df.empty:
            print(f"💰 价格区间: {stock_df['low'].min():.2f} – {stock_df['high'].max():.2f}\n")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ 数据加载失败: {e}"); return

    # 3. 逐分钟回放（日期感知）
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

    if times:
        # [FIX] 统一处理 Unix 时间戳，强制转为本地时间显示 (Asia/Shanghai)
        if isinstance(times[0], (int, float, np.integer, np.floating)):
            # 检查毫秒级时间戳 (> 1e12)
            t_unit = 'ms' if times[0] > 1e12 else 's'
            ts_objs = pd.to_datetime(times, unit=t_unit, utc=True).tz_convert('Asia/Shanghai').tz_localize(None)
        else:
            ts_objs = pd.to_datetime(times)

        if len(ts_objs) > 1 and ts_objs[0].date() != ts_objs[-1].date():
            # 多日模式：日期变换时显示日期前缀
            last_date = None
            for t in ts_objs:
                if t.date() != last_date:
                    time_labels.append(t.strftime("%d %H:%M"))
                    last_date = t.date()
                else:
                    time_labels.append(t.strftime("%H:%M"))
        else:
            time_labels = [_fts(t) for t in times]
    else:
        time_labels = []

    # 自动生成日期分割线 (Vertical Lines)
    day_separators = []
    if len(times) > 1:
        # [FIX] 复用已有的 ts_objs 确保日期分割线对齐
        dates = ts_objs.date
        breaks = np.where(dates[1:] != dates[:-1])[0] + 1
        for pos in breaks:
            day_separators.append((pos, 'gray', 0.8, 'v'))

    # ── 3. 分析逻辑 (使用 sbc_core 核心) ───────────────────────────────────
    all_signals = []
    
    # 预先标记日期列用于分组
    if 'date' not in stock_df.columns:
        # [FIX] 统一使用 ts_objs 的结果，确保日期对齐本地时间
        if times:
            stock_df['date'] = ts_objs.strftime('%Y-%m-%d')
        else:
            stock_df['date'] = datetime.now().strftime('%Y-%m-%d')
        
    grouped = list(stock_df.groupby('date'))
    print(f"Analyzing {len(grouped)} day(s)...")
    with timed_ctx("sbc_core_analysis", warn_ms=100):
        for tick_date, df_day in grouped:
            # 调用 sbc_core 核心逻辑 (包含 Baseline 提取、SBC 判定、决策引擎评估)
            res = sbc_core.run_sbc_analysis_core(code, day_df, df_day, use_live=use_live, verbose=verbose)
            # res = sbc_core.run_sbc_analysis_core_slow(code, day_df, df_day, verbose=True)
            
            day_signals = res.get('signals', [])
            # 获取 df_day 在原始 stock_df 中的位置索引偏移
            day_start_idx = stock_df.index.get_loc(df_day.index[0])
            
            if isinstance(day_signals, list):
                for s in day_signals:
                    # 避免对 None 或非 SignalPoint 对象操作 (如果是 dict 也兼容处理)
                    if hasattr(s, 'bar_index'):
                        s.bar_index += day_start_idx
                    elif isinstance(s, dict) and 'bar_index' in s:
                        s['bar_index'] += day_start_idx
                    all_signals.append(s)
    print_timing_summary(2)
    signals = all_signals
    
    # [NEW] 极简版本：默认开启，剔除多余标点，限 10 字符
    if concise:
        for s in signals:
            if hasattr(s, 'reason') and s.reason:
                # 剔除多余符号 . ( )
                clean_reason = s.reason.replace(".", "").replace("(", "").replace(")", "")
                if len(clean_reason) > 10:
                    s.reason = clean_reason[:10]
                else:
                    s.reason = clean_reason
    
    # 统计数据 - 使用 name 进行比对，防止枚举对象不一致
    buy_cnt  = sum(1 for s in signals if s.signal_type.name in ["BUY", "FOLLOW"])
    sell_cnt = sum(1 for s in signals if s.signal_type.name in ["SELL", "EXIT_FOLLOW", "STOP_LOSS"])
    print(f"\n{'='*60}")
    print(f"✅ 回放完成: {buy_cnt} 个买点  |  {sell_cnt} 个卖出点")


    # 计算 VWAP 曲线
    # live 模式使用 tick_vol（增量成交量），cache 模式使用 volume
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

    # 提取昨日价格参考线数据
    auto_extra = {
        'last_close': day_df['last_close'].iloc[-1] if 'last_close' in day_df.columns else 0,
        'last_high': day_df['last_high'].iloc[-1] if 'last_high' in day_df.columns else 0,
        'last_low': day_df['last_low'].iloc[-1] if 'last_low' in day_df.columns else 0,
        'high4': day_df['lasth2d'].iloc[-1] if 'lasth4d' in day_df.columns else 0,
        'v_lines': day_separators  # 注入日期分割线
    }
    # 如果外部传入了 extra_lines，则进行合并/覆盖
    if extra_lines and isinstance(extra_lines, dict):
        auto_extra.update(extra_lines)

    # 5. 可视化
    if show_viz:
        return show_chart_with_signals(
            viz_df, signals,
            f"[{code}] 买卖验证 — 结构性信号",
            avg_series=vwap_series,
            time_labels=time_labels,
            use_line=use_live,  # 无论 live 还是 cache，数据都是高密度 Tick 分时，必须用线图
            extra_lines=auto_extra,
            refresh_func=lambda: verify_with_real_data(code, use_live=use_live, show_viz=False, hdf5_lock=hdf5_lock, extra_lines=extra_lines, days=days, concise=concise)
        )
    else:
        # 返回数据包，供 GUI 线程异步渲染
        return {
            "viz_df": viz_df,
            "signals": signals,
            "title": f"[{code}] 买卖验证 — 结构性信号",
            "avg_series": vwap_series,
            "time_labels": time_labels,
            "use_line": True,
            "extra_lines": auto_extra
        }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SBC Pattern Verification Tool")
    parser.add_argument("code", nargs="?", default="603078", help="Stock code (default: 603078)")
    parser.add_argument("--cache", action="store_true", help="Use local cache instead of live Sina data")
    parser.add_argument("--no-viz", action="store_true", help="Disable visualization for benchmarking")
    parser.add_argument("--days", type=int, default=1, help="Number of days to display (default: 1)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--full", action="store_true", help="Full signal names (don't truncate to 8 chars)")
    args = parser.parse_args()
    
    use_live = not args.cache
    verify_with_real_data(args.code, use_live=use_live, show_viz=not args.no_viz, days=args.days, verbose=args.verbose, concise=not args.full)
