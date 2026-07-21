# -*- coding: utf-8 -*-
"""
分时信号系统化回测与参数优化工具 (Intraday Signal Systematic Backtest & Optimization Tool)
支持：
1. 完整分时 Replay 模式 (逐笔 Tick 行情回放与买入信号评估)
2. 历史关键节点 Points 模式 (精确验证特定日期时间的决策输出)
3. 参数网格寻优 Optimize 模式 (自动调整评分门槛、止损止盈比例并对比期望收益)
"""

import sys
import os
import datetime as dt
import pandas as pd
import numpy as np
import argparse
import itertools
from unittest.mock import patch
from typing import Any, List, Dict

# Ensure stdout uses UTF-8 to prevent encoding gibberish on Windows terminal
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Import pyQuant3 module dependencies
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from JSONData import tdx_data_Day as tdd
from intraday_decision_engine import IntradayDecisionEngine
from JohnsonUtil import commonTips as cct

# Mock DateTime for time-sensitive decision logic
class MockDateTime(dt.datetime):
    _mock_now = dt.datetime(2026, 7, 21, 10, 0, 0)
    
    @classmethod
    def now(cls, tz=None):
        return cls._mock_now

class IntradayBacktester:
    def __init__(self, h5_path: str = r"g:\sina_MultiIndex_data.h5"):
        self.h5_path = h5_path
        self._tick_df_cache = None
        
    def load_tick_data(self) -> pd.DataFrame:
        """加载并缓存 HDF5 中的全量分时 Tick 数据"""
        if self._tick_df_cache is not None:
            return self._tick_df_cache
            
        if not os.path.exists(self.h5_path):
            print(f"Warning: HDF5 tick file not found at {self.h5_path}")
            return pd.DataFrame()
            
        print(f"Loading tick data from {self.h5_path}...")
        try:
            # 读取 all_30 数据
            df = pd.read_hdf(self.h5_path, "all_30")
            if isinstance(df.index, pd.MultiIndex):
                df = df.reset_index()
            # 标准化代码格式
            df['code'] = df['code'].astype(str).str.zfill(6)
            df['ticktime'] = pd.to_datetime(df['ticktime'])
            self._tick_df_cache = df
            return df
        except Exception as e:
            print(f"Failed to load HDF5 file: {e}")
            return pd.DataFrame()

    def get_stock_ticks(self, code: str, target_date: str) -> pd.DataFrame:
        """获取特定股票在指定日期的分时 Tick 序列"""
        df = self.load_tick_data()
        if df.empty:
            return pd.DataFrame()
            
        target_dt = pd.to_datetime(target_date).date()
        df_sub = df[(df['code'] == code) & (df['ticktime'].dt.date == target_dt)].copy()
        return df_sub.sort_values(by='ticktime')

    def run_replay(self, code: str, target_date: str, engine_params: Dict[str, Any], verbose: bool = False) -> List[Dict[str, Any]]:
        """
        对单只股票单日分时进行完整的 Tick 级回放仿真
        """
        # 1. 获取日线历史数据
        df_daily = tdd.get_tdx_append_now_df_api(code)
        if df_daily is None or df_daily.empty:
            if verbose:
                print(f"[{code}] Failed to load historical daily data.")
            return []
            
        df_daily = df_daily.sort_index()
        df_daily.index = [str(x)[:10] for x in df_daily.index]
        
        if target_date not in df_daily.index:
            if verbose:
                print(f"[{code}] Date {target_date} not in daily data index.")
            return []
            
        idx_loc = df_daily.index.get_loc(target_date)
        if idx_loc < 2:
            return []
            
        curr_daily = df_daily.iloc[idx_loc].to_dict()
        prev_daily = df_daily.iloc[idx_loc - 1].to_dict()
        prev2_daily = df_daily.iloc[idx_loc - 2].to_dict()
        
        # 2. 获取分时 Tick 序列
        df_ticks = self.get_stock_ticks(code, target_date)
        if df_ticks.empty:
            if verbose:
                print(f"[{code}] No tick data found for {target_date}.")
            return []
            
        # 3. 初始化决策引擎
        engine = IntradayDecisionEngine(**engine_params)
        
        # 4. 提取基准参考指标
        last_close = float(prev_daily["close"])
        nclose2d = float(prev2_daily.get("amount", 0) / prev2_daily.get("vol", 1.0)) if prev2_daily.get("vol", 0) > 0 else float(prev2_daily["close"])
        last_nclose = float(prev_daily.get("amount", 0) / prev_daily.get("vol", 1.0)) if prev_daily.get("vol", 0) > 0 else float(prev_daily["close"])
        
        # 防止计算异常溢出
        if last_nclose > last_close * 1.5 or last_nclose < last_close * 0.5:
            last_nclose = last_close
        if nclose2d > last_close * 1.5 or nclose2d < last_close * 0.5:
            nclose2d = last_close
            
        lastv1d = float(prev_daily.get("vol", 0))
        if lastv1d <= 0:
            lastv1d = 1.0
            
        cumulative_amount = 0.0
        last_volume = 0.0
        signals = []
        
        # 获取当天及次日基本行情参考以用于收益计算
        day_close = float(curr_daily["close"])
        day_high = float(curr_daily["high"])
        
        next_open = None
        next_close = None
        if idx_loc + 1 < len(df_daily):
            next_row = df_daily.iloc[idx_loc + 1]
            next_open = float(next_row["open"])
            next_close = float(next_row["close"])
            
        for _, tick in df_ticks.iterrows():
            tick_time = tick['ticktime']
            price = float(tick['close'])
            curr_vol = float(tick['volume'])
            
            # 计算成交量增量及分时均价 (nclose/VWAP)
            vol_increment = curr_vol - last_volume if last_volume > 0 else curr_vol
            last_volume = curr_vol
            cumulative_amount += price * vol_increment
            running_nclose = cumulative_amount / curr_vol if curr_vol > 0 else price
            
            # 计算实时量比
            time_ratio = cct.get_work_time_ratio_sbc(now_time=tick_time)
            if time_ratio <= 0:
                time_ratio = 0.001
            vol_ratio = (curr_vol / (lastv1d * time_ratio))
            
            # 拼装 snapshot 快照
            snapshot = {
                "code": code,
                "name": curr_daily.get("name", "Unknown"),
                "last_close": last_close,
                "lastp1d": last_close,
                "nclose": last_nclose,
                "last_nclose": last_nclose,
                "nclose2d": nclose2d,
                "highest_today": float(tick["high"]),
                "lowest_today": float(tick["low"]),
                "low10": float(curr_daily.get("low10", 0)),
                "low60": float(curr_daily.get("low60", 0)),
                "vol": lastv1d,
                "loss_streak": 0,
                "day_df": df_daily.iloc[:idx_loc + 1],
            }
            
            # 拼装 row 实时数据
            row = curr_daily.copy()
            row["code"] = code
            row["name"] = curr_daily.get("name", "Unknown")
            row["trade"] = price
            row["open"] = float(tick.get("open", curr_daily["open"]))
            row["high"] = float(tick["high"])
            row["low"] = float(tick["low"])
            row["volume"] = vol_ratio
            row["ratio"] = vol_ratio
            row["nclose"] = running_nclose
            row["percent"] = (price - last_close) / last_close * 100
            
            # 设定 Mock 时间并计算决策
            MockDateTime._mock_now = tick_time
            with patch('intraday_decision_engine.dt.datetime', MockDateTime):
                res = engine.evaluate(row, snapshot, mode="buy_only")
                
            action = res.get('action')
            
            if action == "买入":
                # 计算交易评估指标
                # 1. 触发买入时的涨幅 %
                trigger_pct = row["percent"]
                # 2. 收盘收益率 %
                profit_at_close = (day_close - price) / price * 100
                # 3. 日内买入后最大冲高收益率 %
                max_high_after = max(price, day_high) # 简化：以当天最高价对比买入价
                max_profit_intraday = (max_high_after - price) / price * 100
                # 4. 次日开盘/收盘收益率 %
                profit_next_open = ((next_open - price) / price * 100) if next_open is not None else None
                profit_next_close = ((next_close - price) / price * 100) if next_close is not None else None
                
                sig_info = {
                    "code": code,
                    "date": target_date,
                    "time": tick_time.strftime('%H:%M:%S'),
                    "buy_price": price,
                    "trigger_pct": trigger_pct,
                    "vol_ratio": vol_ratio,
                    "score": res.get("position", 0.0),
                    "reason": res.get("reason", ""),
                    "profit_close": profit_at_close,
                    "max_profit_intraday": max_profit_intraday,
                    "profit_next_open": profit_next_open,
                    "profit_next_close": profit_next_close,
                    "debug_details": res.get("debug", {})
                }
                signals.append(sig_info)
                
                if verbose:
                    print(f"🚀 [BUY SIGNAL] {code} @ {target_date} {sig_info['time']} | Price: {price:.2f} ({trigger_pct:+.2f}%) | Score: {sig_info['score']:.2f}")
                    print(f"   Reason: {sig_info['reason']}")
                    if profit_next_open is not None:
                        print(f"   Simulated P&L: Close={profit_at_close:+.2f}%, Next Open={profit_next_open:+.2f}%, Max Intraday={max_profit_intraday:+.2f}%")
                    print("-" * 50)
                    
        return signals

    def run_points_test(self, test_cases: List[Dict[str, Any]], engine_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        精确验证决策引擎在特定历史时间点/个股/价格下的静态输出。
        如果能查到当日分时 tick，则基于该时间点之前的历史 tick 计算真实的日内最高、最低、量比与成交均价，
        防止未来数据泄露导致的过滤误判。
        """
        engine = IntradayDecisionEngine(**engine_params)
        results = []
        
        for case in test_cases:
            code = case["code"]
            target_date = case["date"]
            time_str = case["time"]
            trade_price = case["trade"]
            desc = case.get("desc", "Custom Point")
            
            df_daily = tdd.get_tdx_append_now_df_api(code)
            if df_daily is None or df_daily.empty:
                print(f"Failed to load daily data for {code}")
                continue
                
            df_daily = df_daily.sort_index()
            df_daily.index = [str(x)[:10] for x in df_daily.index]
            
            if target_date not in df_daily.index:
                print(f"Date {target_date} not in data.")
                continue
                
            idx_loc = df_daily.index.get_loc(target_date)
            if idx_loc < 2:
                continue
                
            curr_row = df_daily.iloc[idx_loc].to_dict()
            prev_row = df_daily.iloc[idx_loc - 1].to_dict()
            prev2_row = df_daily.iloc[idx_loc - 2].to_dict()
            
            last_close = float(prev_row["close"])
            nclose2d = float(prev2_row.get("amount", 0) / prev2_row.get("vol", 1.0)) if prev2_row.get("vol", 0) > 0 else float(prev2_row["close"])
            last_nclose = float(prev_row.get("amount", 0) / prev_row.get("vol", 1.0)) if prev_row.get("vol", 0) > 0 else float(prev_row["close"])
            
            if last_nclose > last_close * 1.5 or last_nclose < last_close * 0.5:
                last_nclose = last_close
            if nclose2d > last_close * 1.5 or nclose2d < last_close * 0.5:
                nclose2d = last_close
                
            # 从分时 tick 中截取 target_date 在 time_str 之前的最高、最低、累计金额等
            df_ticks = self.get_stock_ticks(code, target_date)
            high_val = float(curr_row["high"])
            low_val = float(curr_row["low"])
            nclose = float(curr_row.get("amount", 0) / curr_row.get("vol", 1.0)) if curr_row.get("vol", 0) > 0 else float(curr_row["close"])
            if nclose > last_close * 1.5 or nclose < last_close * 0.5:
                nclose = last_close
            vol_ratio = 1.5
            
            if not df_ticks.empty:
                # 筛选当前时间点之前的 tick
                target_dt = pd.to_datetime(f"{target_date} {time_str}")
                df_before = df_ticks[df_ticks['ticktime'] <= target_dt]
                if not df_before.empty:
                    high_val = float(df_before['close'].max()) # 注意：对于历史tick close的最大值代表当前最高
                    low_val = float(df_before['close'].min())  # 最小值代表当前最低
                    # 重新从头递推
                    lastv1d = float(prev_row.get("vol", 1.0)) if float(prev_row.get("vol", 0)) > 0 else 1.0
                    last_volume = 0.0
                    cumulative_amount = 0.0
                    curr_vol = 0.0
                    for _, tick in df_before.iterrows():
                        t_price = float(tick['close'])
                        t_vol = float(tick['volume'])
                        vol_increment = t_vol - last_volume if last_volume > 0 else t_vol
                        last_volume = t_vol
                        cumulative_amount += t_price * vol_increment
                        curr_vol = t_vol
                    nclose = cumulative_amount / curr_vol if curr_vol > 0 else trade_price
                    
                    time_ratio = cct.get_work_time_ratio_sbc(now_time=target_dt)
                    if time_ratio <= 0:
                        time_ratio = 0.001
                    vol_ratio = (curr_vol / (lastv1d * time_ratio))
            
            snapshot = {
                "code": code,
                "name": curr_row.get("name", "Unknown"),
                "last_close": last_close,
                "lastp1d": last_close,
                "nclose": last_nclose,
                "last_nclose": last_nclose,
                "nclose2d": nclose2d,
                "highest_today": high_val,
                "lowest_today": low_val,
                "low10": float(curr_row.get("low10", 0)),
                "low60": float(curr_row.get("low60", 0)),
                "vol": float(prev_row["vol"]),
                "loss_streak": 0,
                "day_df": df_daily.iloc[:idx_loc + 1],
            }
            
            row = curr_row.copy()
            row["code"] = code
            row["name"] = curr_row.get("name", "Unknown")
            row["trade"] = trade_price
            row["open"] = float(curr_row["open"])
            row["high"] = high_val
            row["low"] = low_val
            row["volume"] = vol_ratio
            row["ratio"] = vol_ratio
            row["nclose"] = nclose
            row["percent"] = (trade_price - last_close) / last_close * 100
            
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2]) if len(parts) > 2 else 0
            y, m, d = map(int, target_date.split("-"))
            MockDateTime._mock_now = dt.datetime(y, m, d, hour, minute, second)
            
            with patch('intraday_decision_engine.dt.datetime', MockDateTime):
                result = engine.evaluate(row, snapshot, mode="buy_only")
                
            out = {
                "desc": desc,
                "code": code,
                "date": target_date,
                "time": time_str,
                "price": trade_price,
                "pct": row["percent"],
                "action": result.get("action"),
                "refuse_reason": result.get("refuse_buy") or result.get("reason") or "无",
                "score": result.get("position", 0.0) if result.get("action") == "买入" else result.get("debug", {}).get("实时买入分", 0.0),
                "debug": result.get("debug", {})
            }
            results.append(out)
            
            print("="*60)
            print(f"【节点描述】: {desc}")
            print(f" 评估点: {code} | {target_date} {time_str} | 股价: {trade_price:.2f} ({row['percent']:+.2f}%)")
            print(f" 递推高低: 高={high_val:.2f}, 低={low_val:.2f} | 均价(nclose): {nclose:.2f} | 量比: {vol_ratio:.2f}")
            print(f" 决策输出: 【{out['action']}】 | 评分: {out['score']:.2f}")
            print(f" 提示/拒绝原因: {out['refuse_reason']}")
            print("="*60 + "\n")
            
        return results

    def optimize_grid(self, codes: List[str], dates: List[str], param_grid: Dict[str, List[Any]]) -> pd.DataFrame:
        """
        在指定股票和日期区间内，对参数组合进行网格寻优，输出对比报表
        """
        keys, values = zip(*param_grid.items())
        experiments = [dict(zip(keys, v)) for v in itertools.product(*values)]
        
        print(f"Starting parameter optimization grid search...")
        print(f"Total experiment combinations: {len(experiments)}")
        print(f"Target stocks: {codes} | Target dates: {len(dates)} days")
        
        summary_results = []
        
        for idx, params in enumerate(experiments):
            print(f"Running Combo {idx+1}/{len(experiments)}: {params}")
            all_signals = []
            
            for code in codes:
                for target_date in dates:
                    signals = self.run_replay(code, target_date, params, verbose=False)
                    # 默认仅采用每日的首个买入信号（模拟实际交易开仓）
                    if signals:
                        all_signals.append(signals[0])
                        
            # 统计表现指标
            total_trades = len(all_signals)
            if total_trades > 0:
                avg_score = np.mean([s["score"] for s in all_signals])
                # 收盘期望
                avg_profit_close = np.mean([s["profit_close"] for s in all_signals])
                win_rate_close = np.mean([1 if s["profit_close"] > 0 else 0 for s in all_signals]) * 100
                # 最大冲高期望
                avg_max_profit = np.mean([s["max_profit_intraday"] for s in all_signals])
                # 次日开盘期望
                valid_next_open = [s["profit_next_open"] for s in all_signals if s["profit_next_open"] is not None]
                avg_profit_next_open = np.mean(valid_next_open) if valid_next_open else 0.0
                win_rate_next_open = (np.mean([1 if x > 0 else 0 for x in valid_next_open]) * 100) if valid_next_open else 0.0
            else:
                avg_score = 0.0
                avg_profit_close = 0.0
                win_rate_close = 0.0
                avg_max_profit = 0.0
                avg_profit_next_open = 0.0
                win_rate_next_open = 0.0
                
            res_entry = params.copy()
            res_entry.update({
                "TotalTrades": total_trades,
                "AvgScore": round(avg_score, 2),
                "WinRateClose%": round(win_rate_close, 1),
                "AvgProfitClose%": round(avg_profit_close, 2),
                "AvgMaxProfitIntraday%": round(avg_max_profit, 2),
                "WinRateNextOpen%": round(win_rate_next_open, 1),
                "AvgProfitNextOpen%": round(avg_profit_next_open, 2)
            })
            summary_results.append(res_entry)
            
        df_res = pd.DataFrame(summary_results)
        # 按照次日开盘收益率从高到低排序
        df_res = df_res.sort_values(by="AvgProfitNextOpen%", ascending=False)
        return df_res


def parse_dates(date_str: str) -> List[str]:
    """解析多种格式的日期参数"""
    if not date_str:
        return []
    if ":" in date_str:
        # 日期范围 2026-07-01:2026-07-21
        start_s, end_s = date_str.split(":")
        start_d = pd.to_datetime(start_s)
        end_d = pd.to_datetime(end_s)
        dates = pd.date_range(start_d, end_d).strftime('%Y-%m-%d').tolist()
        return dates
    elif "," in date_str:
        return [x.strip() for x in date_str.split(",")]
    else:
        return [date_str.strip()]

def main():
    parser = argparse.ArgumentParser(description="分时信号系统化回测与参数网格寻优工具")
    parser.add_argument("--mode", type=str, choices=["replay", "points", "optimize"], default="replay",
                        help="回测模式: replay(完整分时回放), points(特定历史节点评估), optimize(网格参数优化)")
    parser.add_argument("--code", type=str, default="688689",
                        help="股票代码 (多只股票使用逗号隔开, 如 688689,688561; optimize 模式下输入 all 代表全部)")
    parser.add_argument("--date", type=str, default="2026-07-21",
                        help="日期参数: 单日(2026-07-21), 多日(2026-07-13,2026-07-21), 或范围(2026-07-01:2026-07-21)")
    parser.add_argument("--h5-path", type=str, default=r"g:\sina_MultiIndex_data.h5",
                        help="HDF5 Tick 数据库文件路径")
    parser.add_argument("--verbose", action="store_true", help="是否输出 Tick 级详细计算明细")
    
    # 引擎初始化参数覆盖
    parser.add_argument("--buy-threshold", type=float, default=0.40, help="买入评分起步门槛")
    parser.add_argument("--stop-loss", type=float, default=0.05, help="止损回撤比 (如 0.05 代表 5%)")
    parser.add_argument("--take-profit", type=float, default=0.10, help="止盈比例 (如 0.10 代表 10%)")
    parser.add_argument("--trailing-stop", type=float, default=0.03, help="移动止盈幅度")
    
    args = parser.parse_args()
    
    backtester = IntradayBacktester(h5_path=args.h5_path)
    
    # 解析股票代码
    codes = [x.strip() for x in args.code.split(",") if x.strip()]
    # 解析日期
    dates = parse_dates(args.date)
    
    # 构造基础引擎参数
    base_engine_params = {
        "buy_threshold": args.buy_threshold,
        "stop_loss_pct": args.stop_loss,
        "take_profit_pct": args.take_profit,
        "trailing_stop_pct": args.trailing_stop
    }
    
    if args.mode == "replay":
        print(f"\n>>> Running Intraday Replay Backtest (Stocks: {codes}, Dates: {dates}) <<<\n")
        all_signals = []
        for code in codes:
            for target_date in dates:
                print(f"Simulating {code} on {target_date}...")
                signals = backtester.run_replay(code, target_date, base_engine_params, verbose=True)
                all_signals.extend(signals)
                
        # 统计结果输出
        print(f"\n==================== BACKTEST SUMMARY (Total Signals: {len(all_signals)}) ====================")
        if all_signals:
            df_summary = pd.DataFrame(all_signals)
            cols_show = ["code", "date", "time", "buy_price", "trigger_pct", "score", "profit_close", "max_profit_intraday", "profit_next_open"]
            cols_show = [c for c in cols_show if c in df_summary.columns]
            print(df_summary[cols_show].to_string(index=False))
            
            # 指标汇总
            avg_score = df_summary["score"].mean()
            avg_p_close = df_summary["profit_close"].mean()
            win_close = (df_summary["profit_close"] > 0).mean() * 100
            avg_max_p = df_summary["max_profit_intraday"].mean()
            
            print("-" * 80)
            print(f" 平均评分 (Avg Score): {avg_score:.2f}")
            print(f" 收盘胜率 (Win Rate at Close): {win_close:.1f}%")
            print(f" 收盘平均收益 (Avg Profit at Close): {avg_p_close:+.2f}%")
            print(f" 日内最高平均冲高 (Avg Max Intraday Profit): {avg_max_p:+.2f}%")
            
            if "profit_next_open" in df_summary.columns and not df_summary["profit_next_open"].isna().all():
                valid_next = df_summary["profit_next_open"].dropna()
                avg_next_open = valid_next.mean()
                win_next = (valid_next > 0).mean() * 100
                print(f" 次日开盘胜率 (Win Rate at Next Open): {win_next:.1f}%")
                print(f" 次日开盘平均收益 (Avg Profit at Next Open): {avg_next_open:+.2f}%")
        else:
            print("No buy signals triggered across the backtest period.")
            
    elif args.mode == "points":
        print(f"\n>>> Running Point-by-Point Evaluation <<<\n")
        # 默认使用 688689 的五个历史关键节点
        default_points = [
            {"code": "688689", "date": "2026-07-03", "time": "14:40", "trade": 67.50, "desc": "节点一：高位大跌首日尾盘诱多"},
            {"code": "688689", "date": "2026-07-09", "time": "14:50", "trade": 67.15, "desc": "用户实盘点一：下跌中继十字星"},
            {"code": "688689", "date": "2026-07-13", "time": "10:00", "trade": 53.00, "desc": "节点二：阴跌半山腰弱反弹"},
            {"code": "688689", "date": "2026-07-14", "time": "14:50", "trade": 53.20, "desc": "用户实盘点二：下跌企稳星"},
            {"code": "688689", "date": "2026-07-21", "time": "11:03:18", "trade": 37.32, "desc": "节点三：触底大长腿放量强反弹洗盘"}
        ]
        # 如果指定了其他代码，过滤为其他代码，或者直接采用 default_points
        target_points = [p for p in default_points if p["code"] in codes] if codes != ["688689"] else default_points
        backtester.run_points_test(target_points, base_engine_params)
        
    elif args.mode == "optimize":
        print(f"\n>>> Running Grid Search Parameter Optimization <<<\n")
        # 默认网格范围
        param_grid = {
            "buy_threshold": [0.35, 0.40, 0.45],
            "stop_loss_pct": [0.03, 0.05],
            "take_profit_pct": [0.08, 0.10, 0.12]
        }
        
        # 如果是 "--code all"，我们自动搜寻当前 HDF5 中拥有的所有代码
        if args.code.lower() == "all":
            df_ticks = backtester.load_tick_data()
            if not df_ticks.empty:
                codes = df_ticks['code'].unique().tolist()
                print(f"Auto-detected {len(codes)} unique stock codes in HDF5 database.")
            else:
                print("Error: Could not retrieve codes from HDF5.")
                return
                
        df_opt = backtester.optimize_grid(codes, dates, param_grid)
        
        print("\n==================== PARAMETER OPTIMIZATION REPORT (Sorted by Next Open P&L) ====================")
        print(df_opt.to_string(index=False))
        
        # 保存 Markdown 报告到 workspace
        report_path = os.path.join(os.path.dirname(__file__), "backtest_optimization_report.md")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("# 分时信号参数网格优化报告 (Intraday Signal Parameter Optimization Report)\n\n")
                f.write(f"生成时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"测试范围: 股票={codes}, 周期={dates}\n\n")
                f.write("## 优化结果对比表 (Sorted by AvgProfitNextOpen%)\n\n")
                f.write(df_opt.to_markdown(index=False))
                f.write("\n\n> [!NOTE]\n> 本回测针对每次触发时采用首笔开仓信号进行次日/日内冲高收益的测算。")
            print(f"\nReport successfully saved to: {report_path}")
        except Exception as e:
            print(f"Failed to save Markdown report: {e}")

if __name__ == "__main__":
    main()
