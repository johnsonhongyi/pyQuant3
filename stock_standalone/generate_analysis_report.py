import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from trading_logger import TradingLogger
from trading_analyzer import TradingAnalyzer

def generate_report(db_path="./trading_signals.db"):
    logger = TradingLogger(db_path)
    analyzer = TradingAnalyzer(logger)
    
    # 1. 使用 TradingAnalyzer 获取合并后的数据 (包含已展开的指标)
    df = analyzer.get_trades_with_signals()
    
    if df.empty:
        print("未发现已平仓交易或信号历史匹配数据。")
        return

    # 2. 计算派生特征
    # price_at_sig 和 nclose 是由 TradingAnalyzer 展开的
    df['below_vwap'] = (df['price_at_sig'] < df['nclose']) & (df['nclose'] > 0)
    
    report = []
    report.append("="*50)
    report.append(f"交易分析报告 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("="*50)
    
    # 全局统计
    total_trades = len(df)
    win_trades = len(df[df['pnl_pct'] > 0])
    avg_pnl = df['pnl_pct'].mean()
    total_profit = df['profit'].sum()
    
    report.append(f"总交易笔数: {total_trades}")
    report.append(f"胜率: {win_trades/total_trades:.2%}")
    report.append(f"平均收益率: {avg_pnl:.2%}")
    report.append(f"总盈亏额: {total_profit:.2f}")
    
    # 1. 分析 "Reason" 影响
    report.append("\n[1. 按买入路由分析]")
    # 优先使用 signals 表中的 reason，如果没有则用 trade_records 中的 (如果有的话)
    reason_col = 'reason' if 'reason' in df.columns else None
    if reason_col:
        reason_stats = df.groupby(reason_col).agg({
            'pnl_pct': ['count', 'mean', lambda x: (x > 0).mean()],
            'profit': 'sum'
        }).sort_values(('pnl_pct', 'mean'), ascending=False)
        reason_stats.columns = ['Count', 'Avg_PNL', 'Win_Rate', 'Total_Profit']
        report.append(reason_stats.to_string())
    else:
        report.append("未发现 Reason 字段。")

    # 2. 分析 "Structure" 结构
    report.append("\n[2. 按盘中结构分析]")
    if 'structure' in df.columns:
        struct_stats = df.groupby('structure').agg({
            'pnl_pct': ['count', 'mean', lambda x: (x > 0).mean()],
            'profit': 'sum'
        })
        struct_stats.columns = ['Count', 'Avg_PNL', 'Win_Rate', 'Total_Profit']
        report.append(struct_stats.to_string())
    else:
        report.append("未发现 Structure 字段。")

    # 3. 分析 "Below VWAP" (均价线下买入) 的危害
    report.append("\n[3. 均价线下买入分析]")
    vwap_stats = df.groupby('below_vwap').agg({
        'pnl_pct': ['count', 'mean', lambda x: (x > 0).mean()],
        'profit': 'sum'
    })
    vwap_stats.columns = ['Count', 'Avg_PNL', 'Win_Rate', 'Total_Profit']
    report.append(vwap_stats.to_string())
    report.append("(True 表示买入时价格低于均价线)")

    # 4. 分析代码表现
    report.append("\n[4. 表现最差的 10 只股票]")
    stock_stats = df.groupby('code').agg({
        'pnl_pct': 'mean',
        'profit': 'sum',
        'buy_date': 'count'
    }).sort_values('profit').head(10)
    stock_stats.columns = ['Avg_PNL', 'Total_Profit', 'Trade_Count']
    report.append(stock_stats.to_string())

    # 5. 优化建议
    report.append("\n" + "="*50)
    report.append("策略优化建议 (Actionable Insights)")
    report.append("="*50)
    
    # 自动生成建议逻辑
    try:
        if True in vwap_stats.index and False in vwap_stats.index:
            if vwap_stats.loc[True, 'Avg_PNL'] < vwap_stats.loc[False, 'Avg_PNL']:
                report.append("- 严控均价线下买入: 数据显示线下买入的平均收益明显低于线上。建议在策略中加大对 price < vwap 的惩罚。")
    except: pass
    
    if 'structure' in df.columns:
        if '派发' in df['structure'].values:
            paifa_stats = df[df['structure'] == '派发']
            if paifa_stats['pnl_pct'].mean() < -0.01:
                report.append("- 过滤'派发'结构: '派发'状态下的买入风险极高，建议在 realtime_check 中直接拦截。")

    if total_profit < 0:
        report.append("- 风险控制: 当前整体盈亏为负，请检查止损逻辑是否严格执行。")
        
    report_text = "\n".join(report)
    print(report_text)
    
    with open("analysis_report_output.txt", "w", encoding="utf-8") as f:
        f.write(report_text)

if __name__ == "__main__":
    generate_report()
