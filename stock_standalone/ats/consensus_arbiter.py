# -*- coding: utf-8 -*-
"""
ats/consensus_arbiter.py
------------------------
ConsensusArbiter — 仓位共享与双组投票决策仲裁器。
核心原则：
1. 激进组与保守组共享单一标的持仓池 (SharedPositionState)，严禁分仓割裂。
2. 进攻端买入：实行严格的双重同意 (Dual Consent / AND 逻辑)。
   激进组抓分时突破动能；保守组作为辅助监管审查员，专职对"分时结构不清晰、多空犹豫期"行使一票否决权 (VETO)。
   两组都同意才允许开仓！
3. 防守端出局：实行宽出机制 (Fast Exit / OR 逻辑)。
   8层主动出局守护阵列或任一策略组察觉风险，立即执行减仓/清仓，决不犹豫迟疑。
"""

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from ats.proactive_exit_engine import ExitAction
from ats.vwap_rule_model import VWAPRuleModel

logger = logging.getLogger("ConsensusArbiter")


@dataclass
class SharedPositionState:
    """单一标的共享仓位池状态"""
    code: str
    shares: int = 0
    available_shares: int = 0
    cost_price: float = 0.0
    current_price: float = 0.0
    entry_time: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = 999999.0
    status: str = "IDLE"                  # "IDLE" | "SCOUT" | "HOLDING" | "REDUCED" | "CLOSED"
    total_invested: float = 0.0
    realized_pnl: float = 0.0
    last_update_time: float = 0.0

    @property
    def has_position(self) -> bool:
        return self.shares > 0

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_price <= 0:
            return 0.0
        return (self.current_price - self.cost_price) / self.cost_price * 100.0


@dataclass
class VoteResult:
    """策略组单向投票评估结果"""
    voter_group: str                      # "aggressive" | "conservative"
    decision: str                         # "APPROVE" | "REJECT" | "HESITATE" | "EXIT"
    proposed_size_pct: float = 0.0        # 建议仓位 (0.0 ~ 1.0)
    rule_id: str = ""
    rule_name: str = ""
    reason: str = ""
    
    # 辅助监管特征指标
    structure_clarity_score: float = 100.0  # 分时形态清晰度 (0 ~ 100)
    is_hesitation_period: bool = False      # 是否处于多空犹豫拉锯期
    hesitation_details: str = ""


@dataclass
class ArbiterDecision:
    """仲裁器最终执行决议"""
    allow: bool
    action: str                           # "BUY_SCOUT" | "BUY_ADD" | "REDUCE_HALF" | "REDUCE_30" | "EXIT_ALL" | "HOLD"
    size_pct: float = 0.0
    target_shares: int = 0
    reason: str = ""
    is_vetoed: bool = False
    veto_by: str = ""
    timestamp: float = 0.0


class ConsensusArbiter:
    """
    共识仲裁器：管理共享仓位池与双组投票裁决
    """

    def __init__(self, rule_model: Optional[VWAPRuleModel] = None):
        self.rule_model = rule_model or VWAPRuleModel()
        self._positions: Dict[str, SharedPositionState] = {}
        self._lock = threading.RLock()

    def get_or_create_position(self, code: str) -> SharedPositionState:
        """获取或创建某标的的共享仓位对象"""
        with self._lock:
            if code not in self._positions:
                self._positions[code] = SharedPositionState(code=code)
            return self._positions[code]

    def update_position_price(self, code: str, price: float) -> None:
        """每 Tick 更新标的最新价与持仓极值"""
        with self._lock:
            pos = self._positions.get(code)
            if pos and pos.has_position:
                pos.current_price = price
                pos.last_update_time = time.time()
                if price > pos.highest_price:
                    pos.highest_price = price
                if price < pos.lowest_price:
                    pos.lowest_price = price

    def record_trade_execution(
        self,
        code: str,
        action: str,
        price: float,
        shares: int,
        timestamp: Optional[float] = None,
    ) -> SharedPositionState:
        """执行撮合后同步更新共享仓位池"""
        with self._lock:
            pos = self.get_or_create_position(code)
            t = timestamp if timestamp is not None else time.time()

            if action in ("BUY_SCOUT", "BUY_ADD", "BUY"):
                new_shares = pos.shares + shares
                if new_shares > 0:
                    pos.cost_price = (pos.cost_price * pos.shares + price * shares) / new_shares
                    pos.shares = new_shares
                    pos.available_shares = pos.shares  # 虚拟回测暂按即时可用或T+1规则管理
                    pos.total_invested += price * shares
                if pos.status == "IDLE":
                    pos.entry_time = t
                    pos.highest_price = price
                    pos.lowest_price = price
                    pos.status = "SCOUT" if action == "BUY_SCOUT" else "HOLDING"
                else:
                    pos.status = "HOLDING"

            elif action in ("REDUCE_HALF", "REDUCE_30", "EXIT_ALL", "SELL"):
                sell_shares = min(shares, pos.shares)
                if sell_shares > 0:
                    pnl = (price - pos.cost_price) * sell_shares
                    pos.realized_pnl += pnl
                    pos.shares -= sell_shares
                    pos.available_shares = max(0, pos.available_shares - sell_shares)
                    if pos.shares <= 0:
                        pos.status = "CLOSED"
                        pos.shares = 0
                    else:
                        pos.status = "REDUCED"

            pos.current_price = price
            pos.last_update_time = t
            return pos

    def arbitrate_buy(
        self,
        code: str,
        agg_vote: VoteResult,
        con_vote: VoteResult,
        now: Optional[float] = None,
    ) -> ArbiterDecision:
        """
        开仓进攻仲裁：实行严格的双重同意 (Dual Consent)
        - 激进组必须赞成 (APPROVE)
        - 保守组必须赞成 (APPROVE) 且对分时结构清晰、非犹豫期进行严格审查
        - 两组都同意才准开仓！
        """
        t = now if now is not None else time.time()
        pos = self.get_or_create_position(code)

        # 1. 激进组未触发买点
        if agg_vote.decision != "APPROVE":
            return ArbiterDecision(
                allow=False,
                action="HOLD",
                reason=f"激进组未批准开仓: {agg_vote.reason or '未达买入触发条件'}",
                timestamp=t,
            )

        # 2. 保守组（辅助监管审查员）行使审查与一票否决权
        # 2.1 犹豫期一票否决
        if con_vote.is_hesitation_period or con_vote.decision == "HESITATE":
            logger.debug(f"[{code}] 保守组行使辅助监管否决权: 分时处于犹豫期 ({con_vote.hesitation_details})")
            return ArbiterDecision(
                allow=False,
                action="HOLD",
                is_vetoed=True,
                veto_by="conservative_guard",
                reason=f"保守组一票否决: 分时处于多空犹豫期/拉锯震荡 ({con_vote.hesitation_details})，杜绝盲目开仓",
                timestamp=t,
            )

        # 2.2 结构清晰度不足一票否决
        con_cfg = self.rule_model.conservative_config
        min_clarity = con_cfg.min_structure_clarity if con_cfg else 70.0
        if con_vote.structure_clarity_score < min_clarity:
            logger.debug(f"[{code}] 保守组行使辅助监管否决权: 分时结构混乱 (清晰度 {con_vote.structure_clarity_score:.1f} < {min_clarity})")
            return ArbiterDecision(
                allow=False,
                action="HOLD",
                is_vetoed=True,
                veto_by="conservative_guard",
                reason=f"保守组一票否决: 分时结构不清晰/杂波过多 (清晰度评分 {con_vote.structure_clarity_score:.1f} < 门槛 {min_clarity})",
                timestamp=t,
            )

        # 2.3 保守组拒绝
        if con_vote.decision != "APPROVE":
            return ArbiterDecision(
                allow=False,
                action="HOLD",
                is_vetoed=True,
                veto_by="conservative_guard",
                reason=f"保守组未通过合规审查: {con_vote.reason}",
                timestamp=t,
            )

        # 3. 两组均投赞成票 (Dual Consent) -> 批准开仓
        chosen_size = min(agg_vote.proposed_size_pct, con_vote.proposed_size_pct)
        if chosen_size <= 0:
            chosen_size = 0.10  # 默认 10% 试探仓

        action_type = "BUY_ADD" if pos.has_position else "BUY_SCOUT"
        logger.debug(f"[{code}] ★ 激进与保守双组共识通过! 批准开仓动作: {action_type} (建议仓位: {chosen_size*100:.1f}%)")

        return ArbiterDecision(
            allow=True,
            action=action_type,
            size_pct=chosen_size,
            reason=f"双组共识达成: 激进组捕捉突破动能 ({agg_vote.rule_name}) + 保守组确认分时形态规整 (清晰度 {con_vote.structure_clarity_score:.1f})",
            timestamp=t,
        )

    def arbitrate_exit(
        self,
        code: str,
        proactive_exit: Optional[ExitAction] = None,
        agg_vote: Optional[VoteResult] = None,
        con_vote: Optional[VoteResult] = None,
        now: Optional[float] = None,
    ) -> ArbiterDecision:
        """
        出局防守仲裁：实行宽出机制 (Fast Exit / OR 逻辑)
        - 优先遵从 ProactiveExitEngine 8层主动离场指令
        - 任一组提出 EXIT 投票，秒级出局，绝不因分歧犹豫！
        """
        t = now if now is not None else time.time()
        pos = self.get_or_create_position(code)

        if not pos.has_position:
            return ArbiterDecision(allow=False, action="HOLD", reason="无持仓无需出场", timestamp=t)

        # 1. 8层防守守护指令优先
        if proactive_exit is not None:
            return ArbiterDecision(
                allow=True,
                action=proactive_exit.action_type,
                size_pct=proactive_exit.size_pct,
                reason=f"8层出局守护(L{proactive_exit.layer}): {proactive_exit.rule_name} -> {proactive_exit.reason}",
                timestamp=t,
            )

        # 2. 策略组主动避险指令
        if con_vote and con_vote.decision == "EXIT":
            return ArbiterDecision(
                allow=True,
                action="EXIT_ALL",
                size_pct=1.0,
                reason=f"保守组发出避险清仓指令: {con_vote.reason}",
                timestamp=t,
            )

        if agg_vote and agg_vote.decision == "EXIT":
            return ArbiterDecision(
                allow=True,
                action="EXIT_ALL",
                size_pct=1.0,
                reason=f"激进组发出平仓指令: {agg_vote.reason}",
                timestamp=t,
            )

        return ArbiterDecision(allow=False, action="HOLD", reason="无出局信号，继续持仓守护", timestamp=t)
