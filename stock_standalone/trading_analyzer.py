import pandas as pd
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime

class TradingAnalyzer:
    def __init__(self, logger):
        """
        logger: 你的 TradingLogger 实例
        """
        self.logger = logger

    def get_all_trades_df(self) -> pd.DataFrame:
        """
        获取所有交易记录的 DataFrame
        """
        trades = self.logger.get_trades()
        df = pd.DataFrame(trades)
        if df.empty:
            return df
        # 确保 buy_date / sell_date 为 datetime
        df['buy_date'] = pd.to_datetime(df['buy_date'])
        df['sell_date'] = pd.to_datetime(df['sell_date'], errors='coerce')
        return df

    def summarize_by_stock(self) -> pd.DataFrame:
        """
        按股票汇总：状态（OPEN/CLOSED）、总量、平均价、笔数、占比
        """
        df = self.get_all_trades_df()
        if df.empty: 
            return pd.DataFrame()

        summary_list = []
        total_amount = df['buy_amount'].sum()

        for code, group in df.groupby('code'):
            status = 'OPEN' if any(group['status'] == 'OPEN') else 'CLOSED'
            avg_price = (group['buy_price'] * group['buy_amount']).sum() / group['buy_amount'].sum()
            total_volume = group['buy_amount'].sum()
            trade_count = len(group)
            pct = total_volume / total_amount * 100 if total_amount > 0 else 0
            name = group['name'].iloc[0]
            summary_list.append({
                'code': code,
                'name': name,
                'status': status,
                'avg_price': round(avg_price, 2),
                'total_amount': total_volume,
                'trade_count': trade_count,
                'pct': round(pct, 2)
            })
        summary_df = pd.DataFrame(summary_list)
        # 按持仓/平仓、占比排序
        summary_df['status_sort'] = summary_df['status'].apply(lambda x: 0 if x=='OPEN' else 1)
        summary_df = summary_df.sort_values(by=['status_sort', 'pct'], ascending=[True, False]).drop(columns='status_sort')
        return summary_df

    def get_stock_detail(self, code: str) -> pd.DataFrame:
        """
        查询单只股票交易明细，按时间排序
        """
        df = self.get_all_trades_df()
        return df[df['code'] == code].sort_values(by='buy_date')

    def daily_summary(self) -> pd.DataFrame:
        """
        按天统计每日开仓笔数、总量、已平仓盈亏
        """
        df = self.get_all_trades_df()
        if df.empty: 
            return pd.DataFrame()
        df['buy_date_only'] = df['buy_date'].dt.date
        df['sell_date_only'] = df['sell_date'].dt.date

        daily = []
        dates = sorted(set(df['buy_date_only'].tolist() + df['sell_date_only'].dropna().tolist()))
        for d in dates:
            daily_trades = df[df['buy_date_only'] == d]
            daily_amount = daily_trades['buy_amount'].sum()
            closed_trades = df[(df['status']=='CLOSED') & (df['sell_date_only']==d)]
            daily_profit = closed_trades['profit'].sum() if not closed_trades.empty else 0
            daily.append({
                'date': d,
                'daily_trades': len(daily_trades),
                'daily_amount': daily_amount,
                'daily_profit': daily_profit
            })
        return pd.DataFrame(daily).sort_values(by='date', ascending=False)

    def top_trades(self, n: int = 5, largest: bool = True) -> pd.DataFrame:
        """
        top 盈利或亏损交易
        largest=True: 最大盈利，largest=False: 最大亏损
        """
        df = self.get_all_trades_df()
        df_closed = df[df['status'] == 'CLOSED']
        if df_closed.empty:
            return df_closed
        return df_closed.sort_values(by='profit', ascending=not largest).head(n)

    def stock_performance(self) -> pd.DataFrame:
        """
        按股票计算累计盈亏和收益率
        """
        df = self.get_all_trades_df()
        if df.empty:
            return pd.DataFrame()
        performance = []
        for code, group in df.groupby('code'):
            closed = group[group['status']=='CLOSED']
            open_ = group[group['status']=='OPEN']
            closed_profit = closed['profit'].sum() if not closed.empty else 0
            open_cost = (open_['buy_price']*open_['buy_amount']).sum() if not open_.empty else 0
            open_current = (open_['buy_amount'] * open_['buy_price']).sum() if not open_.empty else 0
            total_profit = closed_profit
            total_cost = (closed['buy_price']*closed['buy_amount']).sum() + open_cost
            pct = total_profit/total_cost if total_cost>0 else 0
            performance.append({
                'code': code,
                'name': group['name'].iloc[0],
                'status': 'OPEN' if len(open_)>0 else 'CLOSED',
                'profit': round(total_profit,2),
                'return_pct': round(pct*100,2),
                'total_trades': len(group)
            })
        return pd.DataFrame(performance).sort_values(by='profit', ascending=False)









# import pandas as pd
# from typing import Optional, List, Dict, Any

# class TradingAnalyzer:
#     """
#     策略交易数据分析类
#     对单个股票、持仓状态、交易时间和盈亏进行系统评估
#     """
#     def __init__(self, logger):
#         """
#         logger: TradingLogger 对象
#         """
#         self.logger = logger
#         self.trades_df = self._load_trades()

#     def _load_trades(self) -> pd.DataFrame:
#         """
#         将 trades 转换为 DataFrame，方便分析
#         """
#         trades = self.logger.get_trades()
#         if not trades:
#             return pd.DataFrame()
#         df = pd.DataFrame(trades)
#         # 规范列，避免 KeyError
#         for col in ['code','name','status','buy_date','sell_date','buy_price','sell_price','buy_amount','profit','pnl_pct']:
#             if col not in df.columns:
#                 df[col] = None
#         return df

#     def summary(self) -> Dict[str, Any]:
#         """
#         返回整体策略汇总信息
#         """
#         if self.trades_df.empty:
#             return {}
        
#         total_profit = self.trades_df.loc[self.trades_df['status']=='CLOSED','profit'].sum()
#         avg_pnl_pct = self.trades_df.loc[self.trades_df['status']=='CLOSED','pnl_pct'].mean()
#         total_trades = len(self.trades_df)
        
#         open_positions = self.trades_df[self.trades_df['status']=='OPEN']
#         closed_positions = self.trades_df[self.trades_df['status']=='CLOSED']
        
#         return {
#             'total_profit': total_profit,
#             'avg_pnl_pct': avg_pnl_pct,
#             'total_trades': total_trades,
#             'open_positions': open_positions,
#             'closed_positions': closed_positions
#         }

#     def per_stock_analysis(self) -> pd.DataFrame:
#         """
#         按股票归类，计算平均价、总量、笔数、占比
#         """
#         if self.trades_df.empty:
#             return pd.DataFrame()
        
#         df = self.trades_df.copy()
#         df['amount'] = df['buy_amount'].fillna(0)
#         df['total_price'] = df['buy_price'].fillna(0) * df['amount']
        
#         agg = df.groupby(['code','status','name']).agg(
#             total_amount=('amount','sum'),
#             total_price=('total_price','sum'),
#             trade_count=('code','count'),
#         ).reset_index()
#         agg['avg_price'] = agg['total_price'] / agg['total_amount']
        
#         # 计算占比 (仅 OPEN)
#         total_open_amount = agg.loc[agg['status']=='OPEN','total_amount'].sum()
#         agg['pct'] = agg.apply(lambda row: row['total_amount']/total_open_amount*100 if row['status']=='OPEN' else 0, axis=1)
#         return agg.sort_values(['status','total_amount'], ascending=[True, False])

#     def stock_detail(self, code: str) -> pd.DataFrame:
#         """
#         获取某只股票所有交易记录，含状态和时间
#         """
#         if self.trades_df.empty:
#             return pd.DataFrame()
#         return self.trades_df[self.trades_df['code']==code].sort_values(['buy_date','sell_date'])

#     def daily_profit(self, days: int = 30) -> pd.DataFrame:
#         """
#         获取最近 N 天的每日收益
#         """
#         db_summary = self.logger.get_db_summary(days)
#         df = pd.DataFrame(db_summary, columns=['date','profit','count'])
#         return df.sort_values('date', ascending=False)

#     def top_winners_losers(self, top_n:int=5) -> Dict[str, pd.DataFrame]:
#         """
#         输出盈利最多和亏损最多的前 N 个交易
#         """
#         if self.trades_df.empty:
#             return {'winners': pd.DataFrame(), 'losers': pd.DataFrame()}
        
#         closed = self.trades_df[self.trades_df['status']=='CLOSED']
#         winners = closed.nlargest(top_n,'profit')
#         losers = closed.nsmallest(top_n,'profit')
#         return {'winners': winners, 'losers': losers}

#     def trade_timing_analysis(self) -> pd.DataFrame:
#         """
#         按买入日期统计每日开仓笔数及总金额
#         """
#         if self.trades_df.empty:
#             return pd.DataFrame()
#         df = self.trades_df.copy()
#         df['buy_date_only'] = df['buy_date'].str[:10]
#         result = df.groupby('buy_date_only').agg(
#             daily_trades=('code','count'),
#             daily_amount=('buy_amount','sum')
#         ).reset_index()
#         return result.sort_values('buy_date_only', ascending=False)