# -*- coding: utf-8 -*-
"""
Follow Queue Analysis Script - 跟单队列复盘分析工具
分析“竞价买入”失败案例，识别“杀跌模式”。
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def analyze_follow_queue():
    signal_db = "signal_strategy.db"
    trading_db = "trading_signals.db"
    
    print(f"--- 正在分析跟单队列与交易历史 ({datetime.now().strftime('%Y-%m-%d')}) ---")
    
    try:
        # 1. 获取跟单队列执行记录 (已入场/已离场)
        conn_sig = sqlite3.connect(signal_db)
        follow_df = pd.read_sql_query("""
            SELECT code, name, signal_type, entry_strategy, status, detected_date, notes 
            FROM follow_queue 
            WHERE status IN ('ENTERED', 'EXITED')
        """, conn_sig)
        conn_sig.close()
        
        if follow_df.empty:
            print("未发现已入场的跟单记录。")
            return

        # 2. 获取交易记录 (盈亏情况)
        conn_trade = sqlite3.connect(trading_db)
        trade_df = pd.read_sql_query("""
            SELECT code, name, buy_date, buy_price, sell_date, sell_price, pnl_pct, buy_reason 
            FROM trade_records 
            WHERE buy_date >= ?
        """, conn_trade, params=((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),))
        conn_trade.close()

        # 3. 合并分析：重点关注“竞价买入”且“亏损”的案例
        print(f"\n[全样本统计] 总跟单数: {len(follow_df)}")
        
        # 过滤竞价买入
        auction_df = follow_df[follow_df['entry_strategy'].str.contains('竞价', na=False)]
        print(f"[竞价策略统计] 竞价买入总数: {len(auction_df)}")
        
        # 关联盈亏数据
        merged = pd.merge(auction_df, trade_df, on='code', how='inner')
        
        # 识别“杀跌模式”：亏损 > 5% 或 连续大幅下跌 (如果能从分时看更好，这里看最终盈亏)
        killing_mode = merged[merged['pnl_pct'] < -5.0]
        
        print(f"\n[杀跌案例分析] 亏损超过5%的竞价买入记录: {len(killing_mode)}")
        for i, row in killing_mode.iterrows():
            print(f"  - {row['code']} {row['name_x']} | 日期: {row['buy_date']} | 盈亏: {row['pnl_pct']:.2f}%")
            print(f"    信号: {row['signal_type']} | 备注: {row['notes']}")

        # 4. 分析建议
        print("\n--- 逻辑分析结论 ---")
        if len(killing_mode) > 0:
            print("1. 观察到部分高开标的在竞价阶段缺乏“强结构(Open=Low)”支撑，导致冲高回落。")
            print("2. 需增加胜率过滤：历史连板 win 计数不匹配或趋势走弱时不应 Follow。")
            print("3. 需要集成『诱多跑路』信号，在跌破均线时不论是否触发止损位都应先行离场。")
        else:
            print("近期数据未发现显著异常，但仍需加强风险过滤。")

    except Exception as e:
        print(f"分析出错: {e}")

if __name__ == "__main__":
    analyze_follow_queue()
