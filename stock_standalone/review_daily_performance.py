# encoding: utf-8
import sys
import os
import pandas as pd
import numpy as np
import datetime
import gzip
import json
import glob
from typing import List, Dict, Optional

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_selector import StockSelector
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import commonTips as cct
from trading_logger import TradingLogger

def load_latest_snapshot(snapshot_dir: str = "snapshots"):
    """加载最新的实时快照数据"""
    files = glob.glob(os.path.join(snapshot_dir, "bidding_*.json.gz"))
    if not files:
        return {}
    latest_file = max(files, key=os.path.getmtime)
    print(f"📡 加载快照数据: {os.path.basename(latest_file)}")
    try:
        with gzip.open(latest_file, 'rt', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('meta_data', {})
    except Exception as e:
        print(f"⚠️ 加载快照失败: {e}")
        return {}

def build_current_context(code: str, raw_df: pd.DataFrame, rt_data: dict) -> pd.DataFrame:
    """构建用于 StockSelector 的快照数据"""
    if raw_df.empty: return pd.DataFrame()
    
    # 注入实时数据
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    last_row = raw_df.iloc[-1].copy()
    
    # 构建 snapshot dict (映射 bidding_momentum_detector 的 meta_data 字段)
    snap = last_row.to_dict()
    snap['code'] = code
    snap['trade'] = rt_data.get('now_price', rt_data.get('price', rt_data.get('trade', last_row['close'])))
    snap['price'] = snap['trade']
    snap['close'] = snap['trade']
    snap['high'] = rt_data.get('high_day', rt_data.get('high', last_row['high']))
    snap['low'] = rt_data.get('low_day', rt_data.get('low', last_row['low']))
    snap['open'] = rt_data.get('open_price', rt_data.get('open', last_row['open']))
    snap['amount'] = rt_data.get('amount', last_row.get('amount', 0))
    snap['vol'] = rt_data.get('vol', last_row.get('vol', 0))
    snap['volume'] = snap['vol']
    
    # 注入历史 (StockSelector 依赖这些字段进行趋势质量和均线判断)
    idx_pos = len(raw_df) - 1
    for i in range(1, 11):
        p_idx = idx_pos - i
        if p_idx >= 0:
            p_row = raw_df.iloc[p_idx]
            snap[f'lastp{i}d'] = p_row['close']
            snap[f'per{i}d'] = p_row.get('percent', p_row.get('per', 0))
            snap[f'lasth{i}d'] = p_row['high']
            snap[f'lastl{i}d'] = p_row['low']
            snap[f'lasto{i}d'] = p_row['open']
            
            # 均线注入
            for m in [5, 10, 20, 60]:
                snap[f'ma{m}d'] = p_row.get(f'ma{m}', p_row.get(f'ma{m}d', p_row['close']))

    # 斜率依赖
    if idx_pos >= 1:
        snap['ma51d'] = raw_df.iloc[idx_pos-1].get('ma5', raw_df.iloc[idx_pos-1].get('ma5d', snap['close']))

    # 汇总
    return pd.DataFrame([snap])

def review_performance(days: int = 3):
    print(f"🔍 启动盘前复盘工具 (回顾过去 {days} 天信号表现)")
    print("=" * 110)
    
    # 1. 初始化
    logger = TradingLogger()
    realtime_snapshots = load_latest_snapshot()
    if not realtime_snapshots:
        print("❌ 错误: 未能加载实时快照数据，无法进行当前状态对齐。")
        return

    # 2. 从数据库获取最近的信号
    # 注意：这里我们查询 signal_history，这是实战中触发报警的记录
    conn = logger.db_manager.get_connection()
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"SELECT DISTINCT code, name, date, price as signal_price, action as signal_action FROM signal_history WHERE date >= ?"
    df_signals = pd.read_sql_query(query, conn, params=(start_date,))
    # 注意：SQLiteConnectionManager 返回的连接不应该被手动关闭，或者如果是新生成的则需要处理。
    # 根据 trading_logger.py 的实现，它通常不关闭连接，或者由 Manager 管理。

    if df_signals.empty:
        print(f"📭 过去 {days} 天内没有记录到交易信号。")
        return

    print(f"📈 找到 {len(df_signals)} 条近期信号，正在进行实时状态分析...\n")

    results = []
    
    # 按代码去重，保留最近一次信号
    df_signals = df_signals.drop_duplicates(subset=['code'], keep='first')

    for _, sig in df_signals.iterrows():
        code = sig['code']
        rt_data = realtime_snapshots.get(code)
        if not rt_data:
            # print(f"⚠️ {code} 无实时快照数据，跳过...")
            continue
            
        # 获取历史数据以计算指标
        try:
            raw = tdd.get_tdx_Exp_day_to_df(code, dl=60)
            if raw.empty: continue
            
            # 构建当前上下文
            input_df = build_current_context(code, raw, rt_data)
            selector = StockSelector(df=input_df)
            res_df = selector.filter_strong_stocks(input_df)
            
            if not res_df.empty:
                r = res_df.iloc[0]
                results.append({
                    'Code': code,
                    'Name': sig['name'],
                    'SigDate': sig['date'],
                    'SigPrice': sig['signal_price'],
                    'CurrPrice': r['price'],
                    'Gain': f"{(r['price']/sig['signal_price']-1)*100:+.1f}%",
                    'Grade': r['grade'],
                    'Score': r['score'],
                    'CurrentStatus': r['status'],
                    'Reason': r['reason']
                })
            else:
                # 如果没选上，可能是因为 filter_strong_stocks 的门槛 (score >= 80)
                # 这种情况下通常认为是“转弱”或“震荡”
                results.append({
                    'Code': code,
                    'Name': sig['name'],
                    'SigDate': sig['date'],
                    'SigPrice': sig['signal_price'],
                    'CurrPrice': rt_data.get('price', 0),
                    'Gain': f"{(rt_data.get('price',0)/sig['signal_price']-1)*100:+.1f}%" if sig['signal_price']>0 else "0%",
                    'Grade': 'D',
                    'Score': 0,
                    'CurrentStatus': '失能/整理',
                    'Reason': '形态走弱或流动性不足'
                })
        except Exception as e:
            # print(f"❌ 分析 {code} 失败: {e}")
            pass

    # 3. 输出报告
    df_res = pd.DataFrame(results)
    if df_res.empty:
        print("📭 选出的股票在实时快照中均无记录。")
        return

    # 排序：按等级和得分
    grade_map = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
    df_res['grade_val'] = df_res['Grade'].map(grade_map)
    df_res.sort_values(by=['grade_val', 'Score'], ascending=True, inplace=True)

    print(f"{'代码':<8} | {'名称':<8} | {'信号日期':<10} | {'收益':<8} | {'等级':<4} | {'当前状态':<12} | {'核心理由'}")
    print("-" * 115)
    
    for _, row in df_res.iterrows():
        reason_short = row['Reason'][:50] + "..." if len(row['Reason']) > 50 else row['Reason']
        print(f"{row['Code']:<8} | {row['Name']:<8} | {row['SigDate']:<10} | {row['Gain']:<8} | {row['Grade']:<4} | {row['CurrentStatus']:<12} | {reason_short}")
    
    print("-" * 115)
    print("\n💡 复盘建议:")
    print("1. [主升加速/强势回踩]: 属于强势股的核心持有/加仓段，建议火力聚焦。")
    print("2. [趋势破位/失能]: 结构已坏，宁可错过不可做错，应果断止盈或腾挪仓位。")
    print("3. [空中接力]: 缩量调整未破 MA5/10，是波段参与的极佳位置。")

if __name__ == "__main__":
    review_performance(days=5)
