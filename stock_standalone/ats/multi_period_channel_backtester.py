# -*- coding: utf-8 -*-
"""
ats/multi_period_channel_backtester.py — 多周期通道支撑线上量化策略回测引擎
=============================================================================
核心职责：
1. 逐日推进时序切片 (防未来函数 Anti-Lookahead Bias)；
2. 在每个交易日运行【多周期通道支撑线上共振策略】识别买点；
3. 严格遵循 T+1 交易制度、支持次日开盘价撮合成交；
4. 全闭环持仓生命周期管理：
   - 动态通道支撑止损 (跌破支撑线 -3% 或关键波谷)
   - 通道上轨目标止盈 (触及周/日线 ch_upper)
   - 移动跟踪止盈 (最高浮盈回撤保利润)
   - 最大持仓期限超时离场
5. 输出高专业度量化绩效指标 (胜率、盈亏比、年化收益、最大回撤、夏普比率、卡玛比率及逐笔流水)。
"""

import os
import sys
import math
import time
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any

# 确保上一级项目根目录在 sys.path 中 (支持在 ats/ 目录直接命令行调用)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from logger_utils import LoggerFactory
    logger = LoggerFactory.getLogger("MultiPeriodBacktester")
except Exception:
    import logging
    logger = logging.getLogger("MultiPeriodBacktester")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from JSONData import tdx_data_Day as tdd
from ats.multi_period_resampler import normalize_kline_df
from ats.multi_period_channel_strategy import (
    evaluate_multi_period_channel_strategy,
    DEFAULT_PERIODS
)


class MultiPeriodChannelBacktester:
    """
    多周期通道支撑线上量化回测执行器
    """
    def __init__(
        self,
        initial_capital: float = 100000.0,
        position_pct: float = 1.0,           # 单标的占用资金比例
        commission_rate: float = 0.0003,     # 佣金 万三
        tax_rate: float = 0.0005,            # 印花税 万五 (卖出时收取)
        slippage: float = 0.001,             # 滑点 0.1%
        stop_loss_pct: float = 0.04,         # 硬止损 4%
        trailing_stop_activation: float = 0.08,  # 浮盈超 8% 激活跟踪止盈
        trailing_stop_drawdown: float = 0.035,   # 从最高点回撤 3.5% 止盈
        max_holding_days: int = 20,          # 最大持仓天数
        warmup_bars: int = 40,               # 预热 K 线根数
        min_signal_score: float = 80.0       # 触发买入的最小多周期共振评分
    ):
        self.initial_capital = initial_capital
        self.position_pct = position_pct
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate
        self.slippage = slippage
        self.stop_loss_pct = stop_loss_pct
        self.trailing_stop_activation = trailing_stop_activation
        self.trailing_stop_drawdown = trailing_stop_drawdown
        self.max_holding_days = max_holding_days
        self.warmup_bars = warmup_bars
        self.min_signal_score = min_signal_score

    def run_backtest_on_df(
        self,
        df_daily: pd.DataFrame,
        code: str = "600108",
        name: str = "亚盛集团",
        periods: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        在给定的日线数据上执行逐日回测
        """
        df_norm = normalize_kline_df(df_daily)
        total_bars = len(df_norm)

        if total_bars <= self.warmup_bars + 5:
            logger.warning(f"[{code}] 数据长度不足 ({total_bars} 根 <= 预热 {self.warmup_bars} 根)，无法有效回测")
            return self._empty_result(code, name)

        if periods is None:
            periods = DEFAULT_PERIODS

        cash = self.initial_capital
        position_shares = 0
        current_holding: Optional[Dict[str, Any]] = None
        trades: List[Dict[str, Any]] = []
        equity_records: List[Dict[str, Any]] = []

        pending_buy: Optional[Dict[str, Any]] = None

        # 逐日推进历史 (从第 warmup_bars 根开始)
        for i in range(self.warmup_bars, total_bars):
            curr_date = df_norm.index[i]
            curr_date_str = str(curr_date)[:10]
            curr_open = float(df_norm['open'].iloc[i])
            curr_high = float(df_norm['high'].iloc[i])
            curr_low = float(df_norm['low'].iloc[i])
            curr_close = float(df_norm['close'].iloc[i])

            # ── 1. 执行前一日产生的待买入订单 (T+1 开盘买入) ──
            if pending_buy is not None and position_shares == 0:
                buy_price = curr_open * (1.0 + self.slippage)
                invest_amt = cash * self.position_pct
                # 按 100 股取整
                shares_to_buy = int(invest_amt / (buy_price * 100)) * 100

                if shares_to_buy >= 100 and (shares_to_buy * buy_price) <= cash:
                    cost = shares_to_buy * buy_price
                    fee = cost * self.commission_rate
                    cash -= (cost + fee)
                    position_shares = shares_to_buy

                    current_holding = {
                        "code": code,
                        "name": name,
                        "buy_date": curr_date_str,
                        "buy_bar_idx": i,
                        "buy_price": round(buy_price, 3),
                        "shares": shares_to_buy,
                        "highest_price": curr_high,
                        "stop_loss": round(pending_buy.get("stop_loss", buy_price * (1.0 - self.stop_loss_pct)), 3),
                        "target_price": round(pending_buy.get("target_price_1", buy_price * 1.15), 3),
                        "signal_score": pending_buy.get("score", 0.0),
                        "pattern_name": pending_buy.get("pattern_name", ""),
                        "reason": pending_buy.get("reason", "")
                    }
                pending_buy = None

            # ── 2. 如果当前有持仓，更新浮动盈亏与检查出场条件 ──
            if current_holding is not None:
                # 更新持仓最高价
                if curr_high > current_holding["highest_price"]:
                    current_holding["highest_price"] = curr_high

                hold_bars = i - current_holding["buy_bar_idx"]
                buy_p = current_holding["buy_price"]
                high_p = current_holding["highest_price"]
                max_gain_pct = (high_p - buy_p) / buy_p

                sell_triggered = False
                sell_price = curr_close
                sell_reason = ""

                # 出场条件 A: 触及硬止损位或通道下轨
                eff_stop_loss = max(current_holding["stop_loss"], buy_p * (1.0 - self.stop_loss_pct))
                if curr_low <= eff_stop_loss:
                    sell_triggered = True
                    sell_price = min(curr_open, eff_stop_loss) * (1.0 - self.slippage)
                    sell_reason = f"跌破通道支撑止损线 ({eff_stop_loss:.2f})"

                # 出场条件 B: 移动跟踪止盈 (最高浮盈达标后回撤)
                elif max_gain_pct >= self.trailing_stop_activation:
                    pullback_from_high = (high_p - curr_close) / high_p
                    if pullback_from_high >= self.trailing_stop_drawdown:
                        sell_triggered = True
                        sell_price = curr_close * (1.0 - self.slippage)
                        sell_reason = f"最高浮盈+{max_gain_pct*100:.1f}%后回撤超{self.trailing_stop_drawdown*100:.1f}%移动止盈"

                # 出场条件 C: 触及大级别通道上轨阻力目标
                elif curr_high >= current_holding["target_price"]:
                    sell_triggered = True
                    sell_price = current_holding["target_price"] * (1.0 - self.slippage)
                    sell_reason = f"达到通道上轨阻力位目标 ({current_holding['target_price']:.2f})"

                # 出场条件 D: 超过最大持仓期限
                elif hold_bars >= self.max_holding_days:
                    sell_triggered = True
                    sell_price = curr_close * (1.0 - self.slippage)
                    sell_reason = f"持仓达到最大周期 ({self.max_holding_days}天) 到期平仓"

                # 执行平仓结算
                if sell_triggered and hold_bars > 0:  # 必须满足 T+1
                    gross_revenue = position_shares * sell_price
                    fee = gross_revenue * self.commission_rate
                    tax = gross_revenue * self.tax_rate
                    net_revenue = gross_revenue - fee - tax
                    cash += net_revenue

                    pnl = net_revenue - (position_shares * buy_p)
                    pnl_pct = (sell_price - buy_p) / buy_p * 100.0

                    trade_record = {
                        "code": code,
                        "name": name,
                        "buy_date": current_holding["buy_date"],
                        "sell_date": curr_date_str,
                        "holding_days": hold_bars,
                        "buy_price": current_holding["buy_price"],
                        "sell_price": round(sell_price, 3),
                        "shares": position_shares,
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 2),
                        "pattern_name": current_holding["pattern_name"],
                        "score": current_holding["signal_score"],
                        "sell_reason": sell_reason
                    }
                    trades.append(trade_record)

                    position_shares = 0
                    current_holding = None

            # ── 3. 严格防未来函数：仅截取 <= i 的日线切片计算多周期通道共振 ──
            if position_shares == 0 and pending_buy is None:
                df_history_slice = df_norm.iloc[:i + 1]
                eval_res = evaluate_multi_period_channel_strategy(
                    df_history_slice,
                    periods=periods
                )

                if eval_res.get("is_buy_signal", False) and eval_res.get("score", 0) >= self.min_signal_score:
                    # 记录待买入订单，次日开盘买入
                    pending_buy = eval_res

            # ── 4. 每日资产净值 (Equity) 记录 ──
            current_pos_val = position_shares * curr_close
            total_equity = cash + current_pos_val
            equity_records.append({
                "date": curr_date_str,
                "cash": round(cash, 2),
                "position_val": round(current_pos_val, 2),
                "total_equity": round(total_equity, 2),
                "close": curr_close
            })

        # 回测结束时如果有持仓，按最后一天的收盘价强平结算统计
        if current_holding is not None and position_shares > 0:
            last_close = float(df_norm['close'].iloc[-1])
            sell_price = last_close * (1.0 - self.slippage)
            gross_revenue = position_shares * sell_price
            fee = gross_revenue * self.commission_rate
            tax = gross_revenue * self.tax_rate
            net_revenue = gross_revenue - fee - tax
            cash += net_revenue
            pnl = net_revenue - (position_shares * current_holding["buy_price"])
            pnl_pct = (sell_price - current_holding["buy_price"]) / current_holding["buy_price"] * 100.0

            trades.append({
                "code": code,
                "name": name,
                "buy_date": current_holding["buy_date"],
                "sell_date": str(df_norm.index[-1])[:10],
                "holding_days": (total_bars - 1) - current_holding["buy_bar_idx"],
                "buy_price": current_holding["buy_price"],
                "sell_price": round(sell_price, 3),
                "shares": position_shares,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "pattern_name": current_holding["pattern_name"],
                "score": current_holding["signal_score"],
                "sell_reason": "回测区间结束自动平仓"
            })

        df_trades = pd.DataFrame(trades)
        df_equity = pd.DataFrame(equity_records)

        return self._compile_metrics(code, name, df_trades, df_equity, df_norm)

    def run_backtest_by_code(
        self,
        code: str,
        dl: int = 300,
        periods: Optional[List[str]] = None,
        name: str = ""
    ) -> Dict[str, Any]:
        """
        通过股票代码直连通达信本地数据进行回测
        """
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
        try:
            df = tdd.get_tdx_append_now_df_api(c_clean, dl=dl)
            if df is None or df.empty:
                df = tdd.get_tdx_Exp_day_to_df(c_clean)
            if df is None or df.empty:
                logger.error(f"[{c_clean}] 未能从本地读取到日 K 线数据")
                return self._empty_result(c_clean, name or "未知")

            if not name:
                if 'name' in df.columns:
                    name = str(df['name'].iloc[-1])
                elif c_clean == "600108":
                    name = "亚盛集团"
                if not name or name == "未知":
                    name = f"标的{c_clean}"

            return self.run_backtest_on_df(df, code=c_clean, name=name, periods=periods)
        except Exception as e:
            logger.error(f"[{c_clean}] 回测异常: {e}")
            return self._empty_result(c_clean, name or "异常")

    def _compile_metrics(
        self,
        code: str,
        name: str,
        df_trades: pd.DataFrame,
        df_equity: pd.DataFrame,
        df_norm: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        聚合生成专业量化回测评价报告
        """
        total_trades = len(df_trades)
        initial_cap = self.initial_capital
        final_equity = df_equity['total_equity'].iloc[-1] if not df_equity.empty else initial_cap

        total_return_pct = (final_equity - initial_cap) / initial_cap * 100.0

        # 计算年化收益率 (按 250 个交易日折算)
        num_days = len(df_equity)
        years = max(num_days / 250.0, 0.05)
        cagr = ((final_equity / initial_cap) ** (1.0 / years) - 1.0) * 100.0

        # 最大回撤 (Max Drawdown)
        if not df_equity.empty:
            cum_max = df_equity['total_equity'].cummax()
            dd_series = (df_equity['total_equity'] - cum_max) / cum_max
            max_drawdown_pct = abs(float(dd_series.min())) * 100.0
        else:
            max_drawdown_pct = 0.0

        # 胜率与盈亏比
        win_rate = 0.0
        profit_factor = 0.0
        avg_holding_days = 0.0
        avg_trade_pnl = 0.0
        max_win = 0.0
        max_loss = 0.0

        if total_trades > 0:
            win_trades = df_trades[df_trades['pnl'] > 0]
            loss_trades = df_trades[df_trades['pnl'] <= 0]
            win_rate = len(win_trades) / total_trades * 100.0

            gross_profit = float(win_trades['pnl'].sum()) if not win_trades.empty else 0.0
            gross_loss = abs(float(loss_trades['pnl'].sum())) if not loss_trades.empty else 0.0

            profit_factor = round(gross_profit / max(1e-4, gross_loss), 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
            avg_holding_days = round(float(df_trades['holding_days'].mean()), 1)
            avg_trade_pnl = round(float(df_trades['pnl_pct'].mean()), 2)
            max_win = round(float(df_trades['pnl_pct'].max()), 2)
            max_loss = round(float(df_trades['pnl_pct'].min()), 2)

        # 日收益率序列与夏普比率
        sharpe_ratio = 0.0
        if not df_equity.empty and len(df_equity) > 5:
            eq_series = df_equity['total_equity']
            daily_returns = eq_series.pct_change().dropna()
            std_r = float(daily_returns.std())
            mean_r = float(daily_returns.mean())
            if std_r > 1e-6:
                sharpe_ratio = round((mean_r * 250.0 - 0.02) / (std_r * math.sqrt(250.0)), 2)

        # 基准买入持有收益率 (Buy & Hold)
        bnh_return_pct = 0.0
        if len(df_norm) >= 2:
            start_p = float(df_norm['close'].iloc[self.warmup_bars])
            end_p = float(df_norm['close'].iloc[-1])
            bnh_return_pct = (end_p - start_p) / start_p * 100.0

        # 卡玛比率 (Calmar Ratio)
        calmar = round(cagr / max(1.0, max_drawdown_pct), 2)

        summary = {
            "code": code,
            "name": name,
            "df_kline": df_norm,
            "start_date": str(df_equity['date'].iloc[0]) if not df_equity.empty else "",
            "end_date": str(df_equity['date'].iloc[-1]) if not df_equity.empty else "",
            "total_trading_days": num_days,
            "initial_capital": round(initial_cap, 2),
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "annualized_return_pct": round(cagr, 2),
            "bnh_return_pct": round(bnh_return_pct, 2),
            "excess_return_pct": round(total_return_pct - bnh_return_pct, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "sharpe_ratio": sharpe_ratio,
            "calmar_ratio": calmar,
            "total_trades": total_trades,
            "win_trades": len(win_trades) if total_trades > 0 else 0,
            "loss_trades": len(loss_trades) if total_trades > 0 else 0,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": profit_factor,
            "avg_holding_days": avg_holding_days,
            "avg_trade_pnl_pct": avg_trade_pnl,
            "max_win_pct": max_win,
            "max_loss_pct": max_loss,
            "trades_df": df_trades,
            "equity_df": df_equity
        }
        return summary

    def _empty_result(self, code: str, name: str) -> Dict[str, Any]:
        return {
            "code": code,
            "name": name,
            "start_date": "",
            "end_date": "",
            "total_trading_days": 0,
            "initial_capital": self.initial_capital,
            "final_equity": self.initial_capital,
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "bnh_return_pct": 0.0,
            "excess_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "calmar_ratio": 0.0,
            "total_trades": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_holding_days": 0.0,
            "avg_trade_pnl_pct": 0.0,
            "max_win_pct": 0.0,
            "max_loss_pct": 0.0,
            "trades_df": pd.DataFrame(),
            "equity_df": pd.DataFrame()
        }

    def format_report_markdown(self, res: Dict[str, Any]) -> str:
        """格式化输出 Markdown 回测报告"""
        lines = []
        lines.append(f"# 📊 【多周期通道支撑线上量化策略】历史回测报告")
        lines.append(f"**标的代码**: `{res['code']}` | **标的名称**: **{res['name']}**")
        lines.append(f"**回测区间**: {res['start_date']} ~ {res['end_date']} (共 {res['total_trading_days']} 交易日)")
        lines.append("")
        lines.append("## 🏆 核心绩效总结")
        lines.append("| 绩效指标 | 策略表现 | 评价 / 基准对比 |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **累计总收益率** | **{res['total_return_pct']:+.2f}%** | 初始: ¥{res['initial_capital']:,.0f} → 期末: ¥{res['final_equity']:,.0f} |")
        lines.append(f"| **年化收益率 (CAGR)** | **{res['annualized_return_pct']:+.2f}%** | 基准买入持有: {res['bnh_return_pct']:+.2f}% (超额: {res['excess_return_pct']:+.2f}%) |")
        lines.append(f"| **胜率 (Win Rate)** | **{res['win_rate_pct']:.1f}%** | 盈利笔数: {res['win_trades']} / 亏损笔数: {res['loss_trades']} |")
        lines.append(f"| **盈亏比 (Profit Factor)** | **{res['profit_factor']:.2f}** | 总盈利 / 总亏损 |")
        lines.append(f"| **最大回撤 (Max Drawdown)** | **{res['max_drawdown_pct']:.2f}%** | 资产净值最大回撤 |")
        lines.append(f"| **夏普比率 (Sharpe Ratio)** | **{res['sharpe_ratio']:.2f}** | 风险调整后收益比 |")
        lines.append(f"| **卡玛比率 (Calmar Ratio)** | **{res['calmar_ratio']:.2f}** | 年化收益 / 最大回撤 |")
        lines.append(f"| **总交易笔数** | {res['total_trades']} 笔 | 平均单笔盈亏: {res['avg_trade_pnl_pct']:+.2f}% |")
        lines.append(f"| **平均持仓周期** | {res['avg_holding_days']} 天 | 盈亏极值: {res['max_win_pct']:+.1f}% / {res['max_loss_pct']:+.1f}% |")
        lines.append("")

        trades_df = res.get("trades_df")
        if trades_df is not None and not trades_df.empty:
            lines.append("## 📝 逐笔交易明细记录 (Trade Log)")
            lines.append("| 序号 | 买入日期 | 卖出日期 | 持仓天数 | 买入价 | 卖出价 | 盈亏% | 净利润(元) | 形态评级 | 平仓离场原因 |")
            lines.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |")
            for idx, row in trades_df.iterrows():
                pnl_str = f"**{row['pnl_pct']:+.2f}%**" if row['pnl_pct'] > 0 else f"{row['pnl_pct']:+.2f}%"
                lines.append(
                    f"| {idx+1} | {row['buy_date']} | {row['sell_date']} | {row['holding_days']}天 | "
                    f"{row['buy_price']:.2f} | {row['sell_price']:.2f} | {pnl_str} | "
                    f"{row['pnl']:+,.0f} | {row['pattern_name']} | {row['sell_reason']} |"
                )
        else:
            lines.append("*(回测区间内未触发满足多周期共振评分的买入信号)*")

        return "\n".join(lines)

    def plot_in_sbc(
        self,
        report_or_code: Any = None,
        dl: int = 250,
        df_kline: Optional[pd.DataFrame] = None,
        parent_win: Optional[Any] = None
    ) -> Any:
        """
        【📈 SBC 实盘图表调起】将多周期通道回测买卖点与收益指标一键加载至 SBC 独立走势图
        - 图上高亮标记买入点、卖出点与单笔盈亏率
        - 支持鼠标点击任意买卖点，自动展示持股区间高亮光束与悬浮收益详情卡片
        """
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        created_app = False
        if app is None:
            app = QApplication([])
            created_app = True

        report = None
        code = "600108"
        if isinstance(report_or_code, dict):
            report = report_or_code
            code = str(report.get("code", "600108"))
        elif isinstance(report_or_code, str):
            code = report_or_code
            report = self.run_backtest_by_code(code, dl=dl)
        elif report_or_code is None:
            code = "600108"
            report = self.run_backtest_by_code(code, dl=dl)

        trades_df = report.get("trades_df") if report else None
        if df_kline is None and report:
            df_kline = report.get("df_kline")

        from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
        dlg = open_sbc_chart_dialog(
            parent_win=parent_win,
            code=code,
            period_mode="day",
            trades_df=trades_df,
            df_kline=df_kline
        )

        if created_app and dlg:
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            app.exec()

        return dlg


def convert_backtest_trades_to_sbc_signals(trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    将量化回测逐笔交易明细 trades_df 转换为 SBC 走势图画布标准买卖信号列表
    每个交易配对生成：
    - 买入信号 (🟢 买:buy_price)
    - 卖出信号 (🔴 卖:sell_price (+pnl_pct%))
    携带完整的收益率、持仓天数、离场原因及配对交易信息，供画布点击高亮与收益悬浮卡片交互呈现。
    """
    signals = []
    if trades_df is None or trades_df.empty:
        return signals

    for i, (_, row) in enumerate(trades_df.iterrows()):
        b_date = str(row.get("buy_date", "")).strip()
        s_date = str(row.get("sell_date", "")).strip()
        b_p = float(row.get("buy_price", 0.0))
        s_p = float(row.get("sell_price", 0.0))
        pnl_pct = float(row.get("pnl_pct", 0.0))
        pnl_val = float(row.get("pnl", 0.0))
        h_days = int(row.get("holding_days", 1))
        pat_name = str(row.get("pattern_name", "共振启动"))
        sell_rsn = str(row.get("sell_reason", ""))

        # 买入信号
        signals.append({
            "trade_id": int(i),
            "action": "buy",
            "type": "buy",
            "price": b_p,
            "time": b_date[:10],
            "timestamp": b_date,
            "pnl_pct": pnl_pct,
            "pnl": pnl_val,
            "holding_days": h_days,
            "buy_date": b_date[:10],
            "sell_date": s_date[:10],
            "buy_price": b_p,
            "sell_price": s_p,
            "paired_date": s_date[:10],
            "paired_price": s_p,
            "pattern_name": pat_name,
            "sell_reason": sell_rsn,
            "note": f"买入价:{b_p:.2f} ({pat_name})"
        })

        # 卖出信号
        signals.append({
            "trade_id": int(i),
            "action": "sell",
            "type": "sell",
            "price": s_p,
            "time": s_date[:10],
            "timestamp": s_date,
            "pnl_pct": pnl_pct,
            "pnl": pnl_val,
            "holding_days": h_days,
            "buy_date": b_date[:10],
            "sell_date": s_date[:10],
            "buy_price": b_p,
            "sell_price": s_p,
            "paired_date": b_date[:10],
            "paired_price": b_p,
            "pattern_name": pat_name,
            "sell_reason": sell_rsn,
            "note": f"卖出收益:{pnl_pct:+.2f}% ({sell_rsn})"
        })

    # 按时间顺序稳定排序
    signals.sort(key=lambda s: str(s.get("timestamp", s.get("time", ""))))
    return signals


if __name__ == "__main__":
    # ── 命令行使用与演示 ──
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    target_code = "600108"
    dl_days = 250
    show_sbc = False

    args = [a for a in sys.argv[1:]]
    if "--sbc" in args:
        show_sbc = True
        args.remove("--sbc")
    if "--plot" in args:
        show_sbc = True
        args.remove("--plot")

    if len(args) > 0 and args[0].isdigit():
        target_code = args[0]
    if len(args) > 1 and args[1].isdigit():
        dl_days = int(args[1])

    target_name = "亚盛集团" if target_code == "600108" else ""

    print("=" * 68)
    print(f"🚀 [MultiPeriodChannelBacktester] 多周期通道支撑线上量化回测演示")
    print(f"   目标标的: {target_code} {target_name} | 回测天数: {dl_days} | 调起SBC: {show_sbc}")
    print("=" * 68)

    backtester = MultiPeriodChannelBacktester(
        initial_capital=100000.0,
        position_pct=1.0,
        commission_rate=0.0003,
        tax_rate=0.0005,
        slippage=0.001,
        stop_loss_pct=0.04,
        trailing_stop_activation=0.08,
        trailing_stop_drawdown=0.035,
        max_holding_days=20,
        warmup_bars=35,
        min_signal_score=80.0
    )

    report = backtester.run_backtest_by_code(target_code, dl=dl_days, name=target_name)
    md_report = backtester.format_report_markdown(report)
    print("\n" + md_report)

    print("\n💡 【使用方法说明】:")
    print("1. 命令行直接执行:")
    print("   python multi_period_channel_backtester.py [股票代码(默认600108)] [回测天数(默认250)] [--sbc]")
    print("2. Python 代码中导入并调起 SBC 走势图:")
    print("   from ats.multi_period_channel_backtester import MultiPeriodChannelBacktester")
    print("   bt = MultiPeriodChannelBacktester(initial_capital=100000.0)")
    print("   report = bt.run_backtest_by_code('600108', dl=250)")
    print("   bt.plot_in_sbc(report)  # 弹出 SBC 交互式买卖收益图")
    print("=" * 68)

    if show_sbc:
        print("\n📈 正在唤醒 SBC 实盘走势图并标记买卖点击收益...")
        backtester.plot_in_sbc(report, dl=dl_days)


