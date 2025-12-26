import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime

def generate_report(db_path="./trading_signals.db"):
    conn = sqlite3.connect(db_path)
    
    # 1. 加载数据
    trades = pd.read_sql_query("SELECT * FROM trade_records WHERE status='CLOSED'", conn)
    signals = pd.read_sql_query("SELECT * FROM signal_history", conn)
    
    if trades.empty:
        print("未发现已平仓交易。")
        return

    # 预处理
    trades['buy_date_str'] = pd.to_datetime(trades['buy_date']).dt.strftime('%Y-%m-%d')
    signals['date_str'] = pd.to_datetime(signals['date']).dt.strftime('%Y-%m-%d')
    
    # 合并
    df = pd.merge(trades, signals, left_on=['buy_date_str', 'code'], right_on=['date_str', 'code'], how='left')
    
    # 展开 Indicators
    def safe_json_load(x):
        try:
            return json.loads(x) if x else {}
        except:
            return {}
            
    df['ind_dict'] = df['indicators'].apply(safe_json_load)
    
    # 核心字段提取
    df['nclose_val'] = df['ind_dict'].apply(lambda d: d.get('nclose', 0))
    df['price_at_signal'] = df['ind_dict'].apply(lambda d: d.get('price', 0))
    df['structure'] = df['ind_dict'].apply(lambda d: d.get('structure', 'UNKNOWN'))
    df['buy_score'] = df['ind_dict'].apply(lambda d: d.get('实时买入分', 0))
    df['trend_strength'] = df['ind_dict'].apply(lambda d: d.get('trend_strength', 0))

    # 计算一些特征
    df['below_vwap'] = (df['price_at_signal'] < df['nclose_val']) & (df['nclose_val'] > 0)
    
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
    reason_col = 'reason' if 'reason' in df.columns else ('reason_y' if 'reason_y' in df.columns else None)
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
    struct_stats = df.groupby('structure').agg({
        'pnl_pct': ['count', 'mean', lambda x: (x > 0).mean()],
        'profit': 'sum'
    })
    struct_stats.columns = ['Count', 'Avg_PNL', 'Win_Rate', 'Total_Profit']
    report.append(struct_stats.to_string())

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
    id_col = 'id' if 'id' in df.columns else df.columns[0]
    stock_stats = df.groupby('code').agg({
        'pnl_pct': 'mean',
        'profit': 'sum',
        id_col: 'count'
    }).sort_values('profit').head(10)
    report.append(stock_stats.to_string())

    # 5. 优化建议
    report.append("\n" + "="*50)
    report.append("策略优化建议 (Actionable Insights)")
    report.append("="*50)
    
    # 自动生成建议逻辑
    if vwap_stats.loc[True, 'Avg_PNL'] < vwap_stats.loc[False, 'Avg_PNL']:
        report.append("- 严控均价线下买入: 数据显示线下买入的平均收益明显低于线上。建议在 IntradayDecisionEngine 中加大对 price < nclose 的惩罚或直接禁止。")
    
    if '派发' in struct_stats.index and struct_stats.loc['派发', 'Avg_PNL'] < -0.01:
        report.append("- 过滤'派发'结构: '派发'状态下的买入通常是陷阱。建议在 realtime_check 中若识别为'派发'则跳过买入。")

    if total_profit < 0:
        report.append("- 止损点位调整: 当前平均 PNL 为负，考虑是否止损设置过宽或手续费占比过高。")
        
    report_text = "\n".join(report)
    print(report_text)
    
    with open("analysis_report_output.txt", "w", encoding="utf-8") as f:
        f.write(report_text)

    conn.close()

if __name__ == "__main__":
    generate_report()
