# -*- coding: utf-8 -*-
"""
ats/market_guardian.py
----------------------
MarketGuardian — 大盘与板块宏观哨兵守护引擎
负责监控系统性市场风险，防止在泥沙俱下的大盘杀跌或板块集体出逃时误开仓被割。
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set, Tuple

from ats.vwap_rule_model import VWAPRuleModel

logger = logging.getLogger("MarketGuardian")


@dataclass
class GuardianVerdict:
    """宏观守护每周期评估结论"""
    buy_allowed: bool = True
    sell_urgency: str = "NONE"            # "NONE" | "REDUCE" | "EXIT_ALL"
    freeze_buy: bool = False              # 是否冻结所有进攻买入
    affected_sectors: List[str] = field(default_factory=list)
    reason: str = ""
    timestamp: float = 0.0


class MarketGuardian:
    """
    大盘/板块宏观守护者
    """

    def __init__(self, rule_model: Optional[VWAPRuleModel] = None):
        self.rule_model = rule_model or VWAPRuleModel()
        self._last_verdict = GuardianVerdict(timestamp=time.time())

    def evaluate_market_state(
        self,
        up_count: int,
        down_count: int,
        limit_up_count: int = 0,
        limit_down_count: int = 0,
        market_sentiment: str = "NEUTRAL",  # "PANIC" | "NEUTRAL" | "FOMO" | "COOLDOWN"
        sector_dumps: Optional[Dict[str, Dict[str, Any]]] = None,
        now: Optional[float] = None,
    ) -> GuardianVerdict:
        """
        评估大盘宏观状态与板块抛压
        """
        t = now if now is not None else time.time()
        rules = self.rule_model.guardian_rules
        if not rules.get("enabled", True):
            return GuardianVerdict(buy_allowed=True, sell_urgency="NONE", timestamp=t)

        crash_cfg = rules.get("market_crash", {})
        down_ratio_thresh = crash_cfg.get("down_ratio_threshold", 3.0)
        limit_down_min = crash_cfg.get("limit_down_min", 20)

        # 1. 大盘急杀 / 恐慌熔断检测 (Market Crash)
        is_panic = market_sentiment == "PANIC"
        ratio_crash = (down_count > up_count * down_ratio_thresh) if up_count > 0 else (down_count > 2500)
        limit_down_surge = (limit_down_count >= limit_down_min and limit_up_count < 10)

        if is_panic or limit_down_surge or (ratio_crash and down_count >= 3500):
            reason = (
                f"大盘极端恐慌杀跌 (下跌 {down_count} 家 vs 上涨 {up_count} 家, "
                f"跌停 {limit_down_count} 家, 情绪: {market_sentiment})，触发全局避险清仓"
            )
            logger.warning(f"🚨 MarketGuardian 触发熔断: {reason}")
            self._last_verdict = GuardianVerdict(
                buy_allowed=False,
                sell_urgency="EXIT_ALL",
                freeze_buy=True,
                reason=reason,
                timestamp=t,
            )
            return self._last_verdict

        # 2. 冻结买入检测 (Freeze Buy)
        freeze_cfg = rules.get("freeze_buy", {})
        if freeze_cfg.get("enabled", True):
            if market_sentiment in ("COOLDOWN", "WEAK") or down_count >= 3000:
                reason = f"大盘整体偏弱 (下跌家数 {down_count}，情绪 {market_sentiment})，全面冻结开仓买入"
                self._last_verdict = GuardianVerdict(
                    buy_allowed=False,
                    sell_urgency="NONE",
                    freeze_buy=True,
                    reason=reason,
                    timestamp=t,
                )
                return self._last_verdict

        # 3. 板块集中抛压检测 (Sector Dump)
        dump_cfg = rules.get("sector_dump", {})
        affected_sec: List[str] = []
        if dump_cfg.get("enabled", True) and sector_dumps:
            for sec_name, sec_info in sector_dumps.items():
                break_cnt = sec_info.get("break_count", 0)
                leader_drop = sec_info.get("leader_drop_pct", 0.0)
                if break_cnt >= dump_cfg.get("sector_break_count", 3) or leader_drop >= dump_cfg.get("leader_drop_pct", 3.0):
                    affected_sec.append(sec_name)

        if affected_sec:
            reason = f"板块集中抛压预警: 板块 {affected_sec} 出现大面积破位或龙头跳水，对应板块持仓避险减仓"
            self._last_verdict = GuardianVerdict(
                buy_allowed=True,
                sell_urgency="REDUCE",
                affected_sectors=affected_sec,
                reason=reason,
                timestamp=t,
            )
            return self._last_verdict

        # 正常常态
        self._last_verdict = GuardianVerdict(buy_allowed=True, sell_urgency="NONE", timestamp=t)
        return self._last_verdict

    def is_buy_permitted_for_stock(self, sector: Optional[str] = None) -> Tuple[bool, str]:
        """查询某只股票当前是否被允许买入"""
        if self._last_verdict.freeze_buy or not self._last_verdict.buy_allowed:
            return False, self._last_verdict.reason
        if sector and sector in self._last_verdict.affected_sectors:
            return False, f"所属板块 {sector} 正在遭遇集中抛压，禁止新开仓"
        return True, "宏观大盘与板块状态健康"
