from __future__ import annotations
import pandas as pd
import json
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from trading_logger import TradingLogger

class TradingAnalyzer:
    """
    提供多种维度的交易分析逻辑，返回 pandas DataFrame
    """
    def __init__(self, logger: TradingLogger):
        self.logger: TradingLogger = logger

    def get_all_trades_df(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """获取所有交易记录的 DataFrame"""
        trades: list[dict[str, Any]] = self.logger.get_trades(start_date, end_date)
        df: pd.DataFrame = pd.DataFrame(trades)
        if df.empty:
            return df
        # 转换日期格式
        if 'buy_date' in df.columns:
            df['buy_date'] = pd.to_datetime(df['buy_date'])
        if 'sell_date' in df.columns:
            df['sell_date'] = pd.to_datetime(df['sell_date'])
        return df

    def get_signal_history_df(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """获取信号历史数据的 DataFrame，并展开 indicators 列"""
        signals: list[dict[str, Any]] = self.logger.get_signals(start_date, end_date)
        df: pd.DataFrame = pd.DataFrame(signals)
        if df.empty:
            return df
        
        def expand_indicators(x):
            try:
                d = json.loads(x) if x else {}
                return pd.Series({
                    # 原有字段
                    'win': d.get('win', 0),
                    'red': d.get('red', 0),
                    'gren': d.get('gren', 0),
                    'sum_perc': d.get('sum_perc', 0),
                    'buy_score': d.get('实时买入分', 0.0),
                    'nclose': d.get('nclose', 0),
                    'price_at_sig': d.get('price', 0),
                    'structure': d.get('structure', 'UNKNOWN'),
                    'trend_strength': d.get('trend_strength', 0),
                    # 新增行情指标字段
                    'ma5d': round(d.get('ma5d', 0), 2),
                    'ma10d': round(d.get('ma10d', 0), 2),
                    'ratio': round(d.get('ratio', 0), 2),
                    'volume': round(d.get('volume', 0), 2),
                    'percent': round(d.get('percent', 0), 2),
                    'high': round(d.get('high', 0), 2),
                    'low': round(d.get('low', 0), 2),
                    'open': round(d.get('open', 0), 2),
                    # 新增日内追踪字段
                    'highest_today': round(d.get('highest_today', 0), 2),
                    'pump_height': round(d.get('pump_height', 0) * 100, 2),  # 转为百分比
                    'pullback_depth': round(d.get('pullback_depth', 0) * 100, 2),  # 转为百分比
                    'hvolume': round(d.get('hvolume', 0), 2),
                    'lvolume': round(d.get('lvolume', 0), 2),
                    'time_msg': d.get('时间窗口说明', ''),
                    'buy_reason': d.get('buy_reason', ''),
                    'sell_reason': d.get('sell_reason', ''),
                })
            except:
                return pd.Series({
                    'win': 0, 'red': 0, 'gren': 0, 'sum_perc': 0, 'buy_score': 0.0,
                    'nclose': 0, 'price_at_sig': 0, 'structure': 'UNKNOWN', 'trend_strength': 0,
                    'ma5d': 0, 'ma10d': 0, 'ratio': 0, 'volume': 0, 'percent': 0,
                    'high': 0, 'low': 0, 'open': 0,
                    'highest_today': 0, 'pump_height': 0, 'pullback_depth': 0,
                    'hvolume': 0, 'lvolume': 0, 'time_msg': '',
                    'buy_reason': '', 'sell_reason': ''
                })

        expanded = df['indicators'].apply(expand_indicators)
        df = pd.concat([df, expanded], axis=1)
        # 移除原始 JSON 字段以保持界面整洁
        if 'indicators' in df.columns:
            df = df.drop(columns=['indicators'])
        return df
    
    def summarize_by_stock(self) -> pd.DataFrame:
        """按股票汇总交易情况"""
        df: pd.DataFrame = self.get_all_trades_df()
        if df.empty:
            return df
            
        summary_list: list[dict[str, Any]] = []
        for code, group in df.groupby('code'):
            total_amount: float = group['buy_amount'].sum()
            closed_group: pd.DataFrame = group[group['status'] == 'CLOSED']
            # 注意：这里逻辑简略，实际应加权平均
            avg_price: float = (group['buy_price'] * group['buy_amount']).sum() / total_amount if total_amount > 0 else 0
            open_count: int = len(group[group['status'] == 'OPEN'])
            
            summary_list.append({
                'code': code,
                'name': group['name'].iloc[0],
                'avg_buy_price': round(avg_price, 2),
                'total_bought': total_amount,
                'open_positions': open_count,
                'total_profit': round(closed_group['profit'].sum(), 2) if not closed_group.empty else 0,
                'avg_pnl_pct': round(closed_group['pnl_pct'].mean(), 4) if not closed_group.empty else 0,
                'last_buy_reason': group['buy_reason'].iloc[-1] if 'buy_reason' in group.columns else '',
                'last_sell_reason': group['sell_reason'].iloc[-1] if 'sell_reason' in group.columns else ''
            })
            
        return pd.DataFrame(summary_list).sort_values('total_profit', ascending=False)

    def get_stock_detail(self, code: str) -> pd.DataFrame:
        """查询某只股票的所有交易记录"""
        df: pd.DataFrame = self.get_all_trades_df()
        if df.empty:
            return df
        return df[df['code'] == code].sort_values('buy_date', ascending=False)

    def daily_summary(self, days: int = 30) -> pd.DataFrame:
        """每日盈亏统计"""
        trades: list[dict[str, Any]] = self.logger.get_trades()
        if not trades:
            return pd.DataFrame()
            
        df: pd.DataFrame = pd.DataFrame(trades)
        # 获取所有日期
        dates: list[str] = sorted(list(set([t['sell_date'][:10] for t in trades if t['sell_date']] + 
                                  [t['buy_date'][:10] for t in trades if t['buy_date']])), reverse=True)
        
        daily_list: list[dict[str, Any]] = []
        for d in dates[:days]:
            daily_trades: pd.DataFrame = df[(df['buy_date'].str.startswith(d)) | (df['sell_date'].str.startswith(d))]
            daily_amount: float = daily_trades['buy_amount'].sum()
            closed_trades: pd.DataFrame = daily_trades[daily_trades['status'] == 'CLOSED']
            daily_profit: float = closed_trades['profit'].sum() if not closed_trades.empty else 0
            daily_list.append({
                'date': d,
                'trade_count': len(daily_trades),
                'total_amount': daily_amount,
                'profit': round(daily_profit, 2)
            })
        return pd.DataFrame(daily_list)

    def top_trades(self, n: int = 10, largest: bool = True) -> pd.DataFrame:
        """获取收益最高/最低的 N 笔交易"""
        df: pd.DataFrame = self.get_all_trades_df()
        if df.empty:
            return df
        closed: pd.DataFrame = df[df['status'] == 'CLOSED']
        if closed.empty:
            return pd.DataFrame()
        return closed.sort_values('profit', ascending=not largest).head(n)

    def stock_performance(self) -> pd.DataFrame:
        """所有交易过的股票整体表现 (胜率、盈亏比等)"""
        df: pd.DataFrame = self.get_all_trades_df()
        if df.empty:
            return df
        closed: pd.DataFrame = df[df['status'] == 'CLOSED']
        if closed.empty:
            return pd.DataFrame()
            
        perf: list[dict[str, Any]] = []
        for code, group in closed.groupby('code'):
            win_count: int = len(group[group['profit'] > 0])
            total_count: int = len(group)
            total_profit: float = group['profit'].sum()
            perf.append({
                'code': code,
                'name': group['name'].iloc[0] if 'name' in group.columns else code,
                'trades': total_count,
                'win_rate': round(win_count / total_count, 2),
                'total_profit': round(total_profit, 2),
                'avg_pnl_pct': round(group['pnl_pct'].mean(), 4) if 'pnl_pct' in group.columns else 0
            })
        return pd.DataFrame(perf).sort_values('total_profit', ascending=False)

    def get_trades_with_signals(self) -> pd.DataFrame:
        """
        合并交易记录与信号历史，用于深入分析 (如：买入时的指标与后续盈亏的关系)
        """
        trades = self.get_all_trades_df()
        if trades.empty:
            return pd.DataFrame()
            
        # 仅分析已平仓交易
        trades_closed = trades[trades['status'] == 'CLOSED'].copy()
        if trades_closed.empty:
            return pd.DataFrame()

        signals = self.get_signal_history_df()
        if signals.empty:
            return trades_closed

        # 预处理合并 Key
        trades_closed['buy_date_str'] = trades_closed['buy_date'].dt.strftime('%Y-%m-%d')
        signals['date_str'] = pd.to_datetime(signals['date']).dt.strftime('%Y-%m-%d')
        
        # 合并
        df = pd.merge(
            trades_closed, 
            signals, 
            left_on=['buy_date_str', 'code'], 
            right_on=['date_str', 'code'], 
            how='left',
            suffixes=('', '_sig')
        )
        return df
