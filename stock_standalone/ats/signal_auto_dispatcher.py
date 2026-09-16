# -*- coding: utf-8 -*-
"""
ats/signal_auto_dispatcher.py
-----------------------------
统一信号调度器 (SignalAutoDispatcher)。
严格落实设计方案 v2.1 调度流水线：
1. 阶段模式: 锁定为 PAPER 模拟交易模式，杜绝裸跑实盘。
2. 调度次序:
   Tick 行情接入 -> 
   [Step 1] 先派发至 ProactiveExitEngine 与 MarketGuardian (持仓防守绝对优先)；
   [Step 2] 触发 8 层出局或宏观熔断 -> 秒级执行虚拟平仓并记录原因；
   [Step 3] 若持仓安全/无持仓 -> 派发至 VWAPTradingEngine 与 ConsensusArbiter 执行双组投票；
   [Step 4] 双重同意 (Dual Consent) 批准开仓 -> 虚拟撮合执行开仓；
   [Step 5] 打包买卖信号推送到 SBC 分时图图形标记通道。
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd

from ats.vwap_rule_model import VWAPRuleModel
from ats.market_guardian import MarketGuardian, GuardianVerdict
from ats.proactive_exit_engine import ProactiveExitEngine, ExitAction
from ats.vwap_trading_engine import VWAPTradingEngine, VWAPTickState
from ats.consensus_arbiter import ConsensusArbiter, SharedPositionState, VoteResult, ArbiterDecision

logger = logging.getLogger("SignalAutoDispatcher")


@dataclass
class DispatchResult:
    """单个 Tick 的调度执行结果"""
    code: str
    timestamp: float
    action: str = "HOLD"                  # "BUY_SCOUT" | "BUY_ADD" | "EXIT" | "HOLD"
    rule_name: str = ""
    reason: str = ""
    price: float = 0.0
    shares: int = 0
    pnl_pct: float = 0.0
    pnl_val: float = 0.0
    is_exit: bool = False
    is_buy: bool = False
    layer: int = 0


class SignalAutoDispatcher:
    """
    全自动分时多周期统一信号调度器
    """

    def __init__(self, rule_model: Optional[VWAPRuleModel] = None):
        self.rule_model = rule_model or VWAPRuleModel()
        self.arbiter = ConsensusArbiter(self.rule_model)
        self.exit_engine = ProactiveExitEngine(self.rule_model)
        self.vwap_engine = VWAPTradingEngine(arbiter=self.arbiter, rule_model=self.rule_model)
        self.guardian = MarketGuardian(self.rule_model)

        self.execution_mode: str = "PAPER"  # 严格锁定在 PAPER 模拟模式
        self.trade_history: List[Dict[str, Any]] = []
        self._trade_seq: int = 1

    def dispatch_tick(
        self,
        code: str,
        price: float,
        vwap: float,
        volume: float,
        timestamp: float,
        open_: float = 0.0,
        high: float = 0.0,
        low: float = 0.0,
        extra_ctx: Optional[Dict[str, Any]] = None,
    ) -> DispatchResult:
        """
        逐 Tick 驱动流水线：防守优先 -> 宏观守护 -> 双组投票进攻 -> 撮合记录
        """
        ctx = extra_ctx or {}
        pos = self.arbiter.get_or_create_position(code)
        self.arbiter.update_position_price(code, price)

        # ---------------------------------------------------------------------
        # [Step 1] 宏观大盘与板块守护审查 (Layer 3 Guardian)
        # ---------------------------------------------------------------------
        mkt_stats = ctx.get("market_stats")
        if mkt_stats:
            mkt_verdict = self.guardian.evaluate_market_state(
                up_count=mkt_stats.get("up_count", 2500),
                down_count=mkt_stats.get("down_count", 2000),
                limit_up_count=mkt_stats.get("limit_up_count", 40),
                limit_down_count=mkt_stats.get("limit_down_count", 5),
                market_sentiment=ctx.get("sentiment_state", "NEUTRAL"),
                sector_dumps=ctx.get("sector_dumps"),
                now=timestamp,
            )
        else:
            mkt_verdict = self.guardian._last_verdict

        # ---------------------------------------------------------------------
        # [Step 2] 持仓防守端 — 绝对优先 (Layer 1-A: ProactiveExitEngine)
        # ---------------------------------------------------------------------
        if pos.has_position:
            # 2.1 宏观大盘熔断强平
            if mkt_verdict.sell_urgency == "EXIT_ALL":
                return self._execute_exit(
                    code, price, timestamp,
                    rule_name="大盘急杀熔断",
                    reason=mkt_verdict.reason,
                    layer=9
                )

            # 2.2 8 层主动防守阵列审查
            exit_act = self.exit_engine.evaluate_tick(
                code=code,
                price=price,
                vwap_today=vwap,
                volume=volume,
                volume_ratio=ctx.get("volume_ratio", 1.0),
                current_time=timestamp,
                extra_ctx=ctx
            )
            if exit_act:
                return self._execute_exit(
                    code, price, timestamp,
                    rule_name=exit_act.rule_name,
                    reason=exit_act.reason,
                    layer=exit_act.layer
                )

            return DispatchResult(code=code, timestamp=timestamp, action="HOLD", reason="持仓正常守护中")

        # ---------------------------------------------------------------------
        # [Step 3] 开仓进攻端 — 双组投票监管 (Layer 1-B: VWAPTradingEngine)
        # ---------------------------------------------------------------------
        # 3.1 宏观买入冻结拦截
        buy_ok, buy_reason = self.guardian.is_buy_permitted_for_stock(ctx.get("sector"))
        if not buy_ok or mkt_verdict.freeze_buy:
            return DispatchResult(
                code=code,
                timestamp=timestamp,
                action="HOLD",
                reason=f"宏观买入冻结: {buy_reason or mkt_verdict.reason}"
            )

        # 3.2 计算分时 VWAP 状态与结构清晰度
        tick_state = self.vwap_engine.compute_tick_state(
            code=code,
            price=price,
            vwap_today=vwap,
            volume_ratio=ctx.get("volume_ratio", 1.0)
        )

        # 3.3 双组投票仲裁开仓机会
        decision = self.vwap_engine.evaluate_buy_opportunity(
            state=tick_state,
            multi_period_score=ctx.get("multi_period_score", 75.0),
            extra_ctx=ctx,
            now=timestamp
        )

        if decision.allow:
            return self._execute_buy(code, price, timestamp, decision)

        return DispatchResult(code=code, timestamp=timestamp, action="HOLD", reason=decision.reason)

    def _execute_buy(
        self,
        code: str,
        price: float,
        timestamp: float,
        decision: ArbiterDecision
    ) -> DispatchResult:
        """执行虚拟开仓买入"""
        shares = 1000  # 标准虚拟测试手数
        self.arbiter.record_trade_execution(
            code=code,
            action=decision.action,
            price=price,
            shares=shares,
            timestamp=timestamp
        )
        self.exit_engine.register_position(
            code=code,
            entry_price=price,
            entry_time=timestamp,
            prev_day_high=price * 1.02,
            vwap_yesterday=price
        )

        trade_id = self._trade_seq
        self._trade_seq += 1

        self.trade_history.append({
            "trade_id": trade_id,
            "code": code,
            "action": "BUY",
            "price": price,
            "shares": shares,
            "time": timestamp,
            "rule_name": decision.reason,
            "status": "OPEN"
        })

        return DispatchResult(
            code=code,
            timestamp=timestamp,
            action=decision.action,
            price=price,
            shares=shares,
            is_buy=True,
            rule_name=decision.action,
            reason=decision.reason
        )

    def _execute_exit(
        self,
        code: str,
        price: float,
        timestamp: float,
        rule_name: str,
        reason: str,
        layer: int
    ) -> DispatchResult:
        """执行虚拟主动出局平仓"""
        pos = self.arbiter.get_or_create_position(code)
        cost = pos.cost_price
        shares = pos.shares
        pnl_pct = (price - cost) / cost * 100.0 if cost > 0 else 0.0
        pnl_val = (price - cost) * shares

        self.arbiter.record_trade_execution(
            code=code,
            action="EXIT_ALL",
            price=price,
            shares=shares,
            timestamp=timestamp
        )
        self.exit_engine.unregister_position(code)

        for tr in reversed(self.trade_history):
            if tr["code"] == code and tr["status"] == "OPEN":
                tr["status"] = "CLOSED"
                tr["exit_price"] = price
                tr["exit_time"] = timestamp
                tr["pnl_pct"] = round(pnl_pct, 2)
                tr["pnl_val"] = round(pnl_val, 2)
                tr["exit_rule"] = rule_name
                break

        return DispatchResult(
            code=code,
            timestamp=timestamp,
            action="EXIT",
            price=price,
            shares=shares,
            is_exit=True,
            layer=layer,
            pnl_pct=round(pnl_pct, 2),
            pnl_val=round(pnl_val, 2),
            rule_name=rule_name,
            reason=reason
        )

    def run_backtest_on_dataframe(
        self,
        code: str,
        df_bars: pd.DataFrame,
        period_mode: str = "1m"
    ) -> List[Dict[str, Any]]:
        """
        在历史分时数据上回放全流程，生成可直接注入 SBC 画布的买卖信号列表
        """
        if df_bars is None or df_bars.empty:
            return []

        signals: List[Dict[str, Any]] = []
        n_bars = len(df_bars)
        prev_high = 0.0

        for idx in range(n_bars):
            row = df_bars.iloc[idx]
            close_p = float(row.get("close", 0.0))
            if close_p <= 0:
                continue
            vwap_p = float(row.get("vwap", close_p))
            open_p = float(row.get("open", close_p))
            high_p = float(row.get("high", close_p))
            low_p = float(row.get("low", close_p))
            vol_p = float(row.get("vol", row.get("volume", 0.0)))
            time_key = str(row.name)

            self.vwap_engine.update_minute_bar(
                code=code,
                bar_time=idx * 60.0,
                open_=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=vol_p,
                vwap=vwap_p
            )

            res = self.dispatch_tick(
                code=code,
                price=close_p,
                vwap=vwap_p,
                volume=vol_p,
                timestamp=idx * 60.0,
                open_=open_p,
                high=high_p,
                low=low_p,
                extra_ctx={"prev_day_high": prev_high, "intraday_high": high_p}
            )

            if res.is_buy:
                signals.append({
                    "trade_id": self._trade_seq - 1,
                    "action": "buy",
                    "type": "buy",
                    "price": close_p,
                    "time": time_key,
                    "timestamp": time_key,
                    "rule_name": res.reason,
                    "note": f"▲买入: {close_p:.2f}元 ({res.reason})"
                })
            elif res.is_exit:
                t_id = self._trade_seq - 1
                prefix = f"▼L{res.layer}主动出局" if res.layer < 8 else ("◆VWAP兜底" if res.layer == 8 else "■宏观守护")
                signals.append({
                    "trade_id": t_id,
                    "action": "sell",
                    "type": "sell",
                    "price": close_p,
                    "time": time_key,
                    "timestamp": time_key,
                    "pnl_pct": res.pnl_pct,
                    "pnl": res.pnl_val,
                    "layer": res.layer,
                    "rule_name": res.rule_name,
                    "sell_reason": res.reason,
                    "note": f"{prefix}: {close_p:.2f}元 ({res.pnl_pct:+.1f}%) | {res.rule_name}"
                })

            if high_p > prev_high:
                prev_high = high_p

        return signals
