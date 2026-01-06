# -*- coding: utf-8 -*-
"""交易日志深度分析脚本 - 用于策略优化"""
import sqlite3
import pandas as pd
import json

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 500)
pd.set_option('display.max_rows', 100)

def main():
    conn = sqlite3.connect('./trading_signals.db')
    
    # 1. 获取交易统计
    print('='*60)
    print('1. 交易记录统计')
    print('='*60)
    df_trades = pd.read_sql_query('SELECT * FROM trade_records WHERE status="CLOSED"', conn)
    print(f'已平仓交易总数: {len(df_trades)}')
    if not df_trades.empty:
        print(f'总盈亏: {df_trades["profit"].sum():.2f}')
        wins = len(df_trades[df_trades["profit"] > 0])
        print(f'胜率: {wins / len(df_trades) * 100:.1f}%')
        print(f'平均收益率: {df_trades["pnl_pct"].mean() * 100:.2f}%')
        print(f'最大单笔盈利: {df_trades["profit"].max():.2f}')
        print(f'最大单笔亏损: {df_trades["profit"].min():.2f}')
    
    # 2. 信号历史分析
    print()
    print('='*60)
    print('2. 信号历史分析 (买入信号)')
    print('='*60)
    df_signals = pd.read_sql_query("SELECT * FROM signal_history WHERE action='买入'", conn)
    print(f'买入信号总数: {len(df_signals)}')
    
    if not df_signals.empty:
        # 解析 indicators JSON
        def parse_indicators(x):
            try:
                if x:
                    return json.loads(x)
                return {}
            except:
                return {}
        
        df_signals['ind'] = df_signals['indicators'].apply(parse_indicators)
        df_signals['buy_score'] = df_signals['ind'].apply(lambda x: x.get('实时买入分', 0))
        df_signals['volume'] = df_signals['ind'].apply(lambda x: x.get('volume', 0))
        df_signals['win'] = df_signals['ind'].apply(lambda x: x.get('win', 0))
        df_signals['red'] = df_signals['ind'].apply(lambda x: x.get('red', 0))
        df_signals['percent'] = df_signals['ind'].apply(lambda x: x.get('percent', 0))
        
        print(f'买入分数分布:')
        print(df_signals['buy_score'].describe())
        
    # 3. 关联买入信号与交易结果
    print()
    print('='*60)
    print('3. 买入信号质量分析')
    print('='*60)
    
    # 将 trades 和 signals 关联
    df_trades['buy_date_str'] = pd.to_datetime(df_trades['buy_date']).dt.strftime('%Y-%m-%d')
    df_signals['date'] = pd.to_datetime(df_signals['date'])
    df_signals['date_str'] = df_signals['date'].dt.strftime('%Y-%m-%d')
    
    df_merged = pd.merge(
        df_trades, 
        df_signals[['date_str', 'code', 'buy_score', 'volume', 'win', 'red', 'percent', 'position']],
        left_on=['buy_date_str', 'code'],
        right_on=['date_str', 'code'],
        how='left'
    )
    
    print(f'关联成功: {df_merged["buy_score"].notna().sum()} / {len(df_merged)}')
    
    # 按买入分数区间分析胜率
    if df_merged['buy_score'].notna().any():
        df_merged['score_bin'] = pd.cut(df_merged['buy_score'], bins=[-100, 0.3, 0.5, 0.7, 1.0, 100], labels=['<0.3', '0.3-0.5', '0.5-0.7', '0.7-1.0', '>1.0'])
        score_analysis = df_merged.groupby('score_bin', observed=True).agg(
            trades=('profit', 'count'),
            win_rate=('profit', lambda x: (x > 0).sum() / len(x) if len(x) > 0 else 0),
            avg_pnl=('pnl_pct', 'mean'),
            total_profit=('profit', 'sum')
        ).reset_index()
        print('按买入分数区间:')
        print(score_analysis.to_string(index=False))
        
    # 4. 按量能分析
    print()
    print('='*60)
    print('4. 量能与交易结果关系')
    print('='*60)
    if df_merged['volume'].notna().any():
        df_merged['vol_bin'] = pd.cut(df_merged['volume'], bins=[0, 0.8, 1.2, 2.0, 5.0, 100], labels=['地量<0.8', '正常0.8-1.2', '放量1.2-2', '大量2-5', '天量>5'])
        vol_analysis = df_merged.groupby('vol_bin', observed=True).agg(
            trades=('profit', 'count'),
            win_rate=('profit', lambda x: (x > 0).sum() / len(x) if len(x) > 0 else 0),
            avg_pnl=('pnl_pct', 'mean'),
            total_profit=('profit', 'sum')
        ).reset_index()
        print('按量能区间:')
        print(vol_analysis.to_string(index=False))
        
    # 5. 按连阳天数分析
    print()
    print('='*60)
    print('5. 连阳天数与交易结果关系')
    print('='*60)
    if df_merged['win'].notna().any():
        df_merged['win_bin'] = pd.cut(df_merged['win'], bins=[-10, 0, 1, 2, 3, 10], labels=['阴线', '1阳', '2连阳', '3连阳', '>3阳'])
        win_analysis = df_merged.groupby('win_bin', observed=True).agg(
            trades=('profit', 'count'),
            win_rate=('profit', lambda x: (x > 0).sum() / len(x) if len(x) > 0 else 0),
            avg_pnl=('pnl_pct', 'mean'),
            total_profit=('profit', 'sum')
        ).reset_index()
        print('按连阳天数:')
        print(win_analysis.to_string(index=False))
        
    # 6. 盈利与亏损交易的信号特征对比
    print()
    print('='*60)
    print('6. 盈利 vs 亏损交易的信号特征对比')
    print('='*60)
    wins = df_merged[df_merged['profit'] > 0]
    losses = df_merged[df_merged['profit'] < 0]
    
    features = ['buy_score', 'volume', 'win', 'red', 'percent', 'position']
    comparison = pd.DataFrame({
        '特征': features,
        '盈利平均': [wins[f].mean() if f in wins.columns and wins[f].notna().any() else 0 for f in features],
        '亏损平均': [losses[f].mean() if f in losses.columns and losses[f].notna().any() else 0 for f in features]
    })
    comparison['差异'] = comparison['盈利平均'] - comparison['亏损平均']
    print(comparison.to_string(index=False))
    
    conn.close()

if __name__ == '__main__':
    main()
