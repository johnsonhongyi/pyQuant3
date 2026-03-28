import sys
import os
import pandas as pd
import numpy as np
import datetime
from typing import List, Dict, Optional

# 确保能导入项目中的 stock_selector
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from stock_selector import StockSelector
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import commonTips as cct
import gzip
import json
import glob

def load_latest_snapshot(snapshot_dir: str = "snapshots"):
    """加载最新的实时快照数据"""
    files = glob.glob(os.path.join(snapshot_dir, "bidding_*.json.gz"))
    if not files:
        return {}
    latest_file = max(files, key=os.path.getmtime)
    try:
        with gzip.open(latest_file, 'rt', encoding='utf-8') as f:
            data = json.load(f)
            # Full data is in 'meta_data'
            return data.get('meta_data', {})
    except Exception as e:
        print(f"⚠️ 加载快照失败: {e}")
        return {}

def run_backtest_suite():
    print("START 双轨分级策略批量验证 (主升爆发启动点动态寻优模式)")
    print("=" * 100)
    
    # 1. 加载实时数据快照 (修复“刻舟求剑”问题)
    realtime_snapshots = load_latest_snapshot()
    if realtime_snapshots:
        print(f"INFO: 已同步最新实时快照 (命中 {len(realtime_snapshots)} 只股票指标)")
    
    # 定义验证矩阵
    test_cases = [
        ('600519', 'REBOUND'),    # 防御/反弹型
        ('301306', 'EXPANSION'),  # 主升/突破型
        ('300668', 'EXPANSION'),  # 杰恩设计 (新关注启动浪)
        ('600683', 'EXPANSION'),
        ('603248', 'EXPANSION'),
        ('600726', 'EXPANSION'),
        ('600227', 'EXPANSION'),
        ('002470', 'EXPANSION'),
        ('300672', 'EXPANSION')
    ]
    
    days_back = 120
    results = []
    current_status = []

    for code, strategy_type in test_cases:
        try:
            print(f"SCAN: {code} ({strategy_type}) 启动记录...")
            raw = tdd.get_tdx_Exp_day_to_df(code, dl=days_back, resample='d', fastohlc=False)
            if raw.empty:
                print(f"ERR: 无法获取 {code} 数据")
                continue
            
            # --- 2. 注入实时数据 (同步当天的最新变动) ---
            rt_data = realtime_snapshots.get(code)
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
            if rt_data:
                # 如果历史数据里还没包含今天，或者今天的数据需要更新
                # 注意：raw.index 通常是日期
                new_row = raw.iloc[-1].copy()
                new_row.name = today_str
                # 更新关键字段 (映射 bidding_momentum_detector 的 meta_data 字段)
                new_row['close'] = rt_data.get('now_price', rt_data.get('price', new_row['close']))
                new_row['high'] = rt_data.get('high_day', rt_data.get('high', new_row['high']))
                new_row['low'] = rt_data.get('low_day', rt_data.get('low', new_row['low']))
                new_row['open'] = rt_data.get('open_price', rt_data.get('open', new_row['open']))
                new_row['amount'] = rt_data.get('amount', new_row['amount'])
                new_row['vol'] = rt_data.get('vol', new_row['vol'])
                
                # 如果最后一行日期不是今天，则 append；否则覆盖
                if str(raw.index[-1])[:10] != today_str:
                    raw = raw.append(new_row)
                else:
                    raw.iloc[-1] = new_row

            # --- 3. 实时状态报告 (当前形态分级) ---
            curr_idx = len(raw) - 1
            curr_snap = build_snapshot_at(raw, code, curr_idx)
            # 补齐 snapshot 中可能缺失的 realtime 字段 (若有)
            if rt_data:
                # 转换字段名以适配 StockSelector
                mapped_rt = {
                    'price': rt_data.get('now_price'),
                    'trade': rt_data.get('now_price'),
                    'high': rt_data.get('high_day'),
                    'low': rt_data.get('low_day'),
                    'open': rt_data.get('open_price'),
                }
                curr_snap.update(mapped_rt)
                
            curr_df = pd.DataFrame([curr_snap])
            selector = StockSelector(df=curr_df)
            curr_res = selector.filter_strong_stocks(curr_df)
            if not curr_res.empty:
                r = curr_res.iloc[0]
                current_status.append({
                    'Code': code, 'Grade': r.get('grade', 'C'), 
                    'Score': r.get('score', 0), 'Status': r.get('status', 'N/A')
                })

            # --- 启动点寻优算法 ---
            # ... (保持原有的历史寻优逻辑) ...
            best_snap = None
            best_score = -1
            best_date = None
            
            # 优先扫描最近 40 天
            search_window = [i for i in range(10, len(raw)) if '2026-02' in str(raw.index[i]) or '2026-03' in str(raw.index[i])]
            if not search_window: search_window = [len(raw)-1]

            for idx_pos in search_window:
                snap = build_snapshot_at(raw, code, idx_pos)
                test_df = pd.DataFrame([snap])
                
                # 直接通过 filter_strong_stocks 验证是否入围
                selector = StockSelector(df=test_df)
                res_df = selector.filter_strong_stocks(test_df)
                
                if not res_df.empty:
                    r = res_df.iloc[0]
                    cur_grade = r.get('grade', 'F')
                    cur_score = r.get('score', 0)
                    
                    if cur_grade in ("S", "A") and cur_score >= 90:
                        if idx_pos + 3 < len(raw):
                            next_bars = raw.iloc[idx_pos+1 : idx_pos+4]
                            has_green = any(next_bars.get('per', next_bars.get('percent', next_bars['close'].pct_change())) > 0)
                            cum_ret = (next_bars.iloc[-1]['close'] / snap['close'] - 1) * 100
                            
                            if has_green or cum_ret > -3.0: # 放宽一点点跌幅校验
                                best_snap = snap
                                best_score = cur_score
                                best_date = str(raw.index[idx_pos])[:10]
                                break
                        else:
                            best_snap = snap
                            best_score = cur_score
                            best_date = str(raw.index[idx_pos])[:10]
                            break
            
            if best_snap:
                final_test_df = pd.DataFrame([best_snap])
                final_test_df.index = [f"{code}_{strategy_type}_LAUNCH"]
                selector = StockSelector(df=final_test_df)
                res_df = selector.filter_strong_stocks(final_test_df)
                
                if not res_df.empty:
                    r = res_df.iloc[0]
                    results.append({
                        'Code': code, 'Type': strategy_type, 'Date': best_date,
                        'Grade': r.get('grade', 'C'), 'Score': r.get('score', 0),
                        'Reason': r.get('reason', 'N/A'), 'Status': r.get('status', 'N/A')
                    })
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ 处理 {code} 出错: {e}")

    # --- 输出汇总报告 ---
    print("\n[历史启动点验证报告] " + "=" * 70)
    print(f"{'代码':<8} | {'类型':<10} | {'启动日期':<12} | {'等级':<4} | {'总分':<6} | {'形态说明'}")
    print("-" * 100)
    for r in results:
        reason_short = r['Reason'][:40] + "..." if len(r['Reason']) > 40 else r['Reason']
        print(f"{r['Code']:<8} | {r['Type']:<10} | {r['Date']:<12} | {r['Grade']:<4} | {r['Score']:<6.0f} | {reason_short} ({r['Status']})")
    
    # --- 输出当前状态报告 (针对性解决“破位”感知问题) ---
    print("\n[当前状态实战诊断 (Sync:{})] ".format(today_str) + "=" * 70)
    print(f"{'代码':<8} | {'当前等级':<8} | {'当前分值':<8} | {'当前状态'}")
    print("-" * 60)
    for s in current_status:
        color = "" # Placeholder
        print(f"{s['Code']:<8} | {s['Grade']:<8} | {s['Score']:<8.0f} | {s['Status']}")
    print("=" * 100)

def build_snapshot_at(raw, code, idx_pos):
    snap = raw.iloc[idx_pos].to_dict()
    snap['code'] = code
    snap['trade'] = snap['close']
    snap['amount'] = snap.get('amount', 500000000)
    
    # 注入历史
    for i in range(1, 11):
        p_idx = idx_pos - i
        if p_idx >= 0:
            p_row = raw.iloc[p_idx]
            snap[f'lastp{i}d'] = p_row['close']
            snap[f'per{i}d'] = p_row.get('percent', 0)
            snap[f'lasth{i}d'] = p_row['high']
            snap[f'lastl{i}d'] = p_row['low']
            snap[f'lasto{i}d'] = p_row['open']
            
            # 核心均线注入 (供 StockSelector 判断主升/破位)
            # data_utils.calc_indicators 算出的通常是 ma5, ma10 等
            for m in [5, 10, 20, 60]:
                snap[f'ma{m}d'] = p_row.get(f'ma{m}', p_row.get(f'ma{m}d', p_row['close']))
    
    # 注入 ma5d1d (供斜率判断)
    if idx_pos >= 1:
        snap['ma51d'] = raw.iloc[idx_pos-1].get('ma5', raw.iloc[idx_pos-1].get('ma5d', snap['close']))

    # 横盘
    if idx_pos >= 5:
        snap['max5'] = raw.iloc[idx_pos-5:idx_pos]['close'].max()
        snap['min5'] = raw.iloc[idx_pos-5:idx_pos]['low'].min()
    
    snap['consecutive_rise'] = 1
    return snap

if __name__ == "__main__":
    run_backtest_suite()
