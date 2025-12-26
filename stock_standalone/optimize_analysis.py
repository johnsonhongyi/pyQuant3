import sqlite3
import json
import pandas as pd
from datetime import datetime

def analyze_signals(db_path="./trading_signals.db"):
    conn = sqlite3.connect(db_path)
    
    # 1. 提取所有已平仓的交易
    trades_query = """
    SELECT id, code, name, buy_date, buy_price, sell_date, sell_price, profit, pnl_pct, status
    FROM trade_records
    WHERE status='CLOSED'
    """
    df_trades = pd.read_sql_query(trades_query, conn)
    
    if df_trades.empty:
        print("没有已平仓的交易记录。")
        return

    # 提取日期部分用于匹配
    df_trades['buy_date_str'] = pd.to_datetime(df_trades['buy_date']).dt.strftime('%Y-%m-%d')
    
    # 2. 提取所有的信号历史
    signals_query = "SELECT date, code, action, reason, indicators FROM signal_history"
    df_signals = pd.read_sql_query(signals_query, conn)
    
    # 3. 合并数据
    df_merged = pd.merge(
        df_trades, 
        df_signals, 
        left_on=['buy_date_str', 'code'], 
        right_on=['date', 'code'], 
        how='left'
    )
    
    print(f"总交易笔数: {len(df_trades)}")
    print(f"成功匹配信号笔数: {df_merged['reason'].notna().sum()}")
    
    # 4. 按 Reason 分析盈亏
    reason_stats = df_merged.groupby('reason').agg(
        count=('id', 'count'),
        avg_pnl=('pnl_pct', 'mean'),
        total_profit=('profit', 'sum')
    ).sort_values(by='avg_pnl', ascending=False)
    
    print("\n=== 按买入理由 (Reason) 统计 ===")
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(reason_stats)
    
    # 5. 分析指标 (Indicators)
    all_indicators = []
    for idx, row in df_merged.iterrows():
        if pd.isna(row['indicators']):
            continue
        try:
            inds = json.loads(row['indicators'])
            # 扁平化一些嵌套字典
            flat_inds = {}
            def flatten(d, prefix=''):
                for k, v in d.items():
                    if isinstance(v, dict):
                        flatten(v, prefix + k + '_')
                    else:
                        flat_inds[prefix + k] = v
            flatten(inds)
            
            flat_inds['trade_id'] = row['id']
            flat_inds['pnl_pct'] = row['pnl_pct']
            flat_inds['profit'] = row['profit']
            flat_inds['code'] = row['code']
            flat_inds['reason'] = row['reason']
            all_indicators.append(flat_inds)
        except Exception as e:
            # print(f"Error parsing indicators for trade {row['id']}: {e}")
            pass
            
    if all_indicators:
        df_inds = pd.DataFrame(all_indicators)
        
        # 转换数值列
        numeric_cols = df_inds.select_dtypes(include=['number']).columns
        
        print("\n=== 指标与 PNL 相关性分析 ===")
        # 只保留有一定变化的列
        corrs = df_inds[numeric_cols].corr()['pnl_pct'].sort_values(ascending=False)
        print(corrs.dropna())

        print("\n=== 亏损最多的 5 笔交易及其关键指标 ===")
        losers = df_inds.sort_values(by='pnl_pct').head(5)
        # 挑选一些重点字段
        important_fields = ['trade_id', 'code', 'pnl_pct', '实时买入分', 'trend_strength', '成交情绪分', '均线差距%', 'reason']
        available_fields = [f for f in important_fields if f in df_inds.columns]
        print(losers[available_fields])

        # 看看特定条件的胜率
        if '实时买入分' in df_inds.columns:
            print("\n=== 实时买入分分布与 PNL ===")
            df_inds['score_bin'] = pd.cut(df_inds['实时买入分'], bins=[-10, 0, 5, 10, 20, 50, 100])
            score_stats = df_inds.groupby('score_bin').agg(
                count=('trade_id', 'count'),
                win_rate=('pnl_pct', lambda x: (x > 0).mean()),
                avg_pnl=('pnl_pct', 'mean')
            )
            print(score_stats)

    conn.close()

if __name__ == "__main__":
    analyze_signals()
    analyze_signals()
