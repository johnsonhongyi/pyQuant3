# -*- coding: utf-8 -*-
"""
ats/strategy/ipo_trading_center.py
-----------------------------------
新股次新股统一集中交易仲裁与调度中心 (IPO Fleet Commander & Trading Center)
核心职责与终极闭环：
1. 【汇交全池守护报告，打破“各管一摊”】：
   - 接收所有守护标的 (40+ 新股次新) 提交的感知报告 (IPOStockPerceptionReport)；
   - 彻底消灭“自己看着自己守护的个股很好不知道山外有山”的局部盲区；
   - 掌握全市场全局视角，实时进行横向赛马冒泡排位。
2. 【买什么、什么时候买、买多少买 (精确仓位配置)】：
   - 资金有限，只重仓全池综合动能最强 (Top 1~2 赛马领头羊)；
   - 根据全市场情绪周期动态调节总仓位 (绝望地量期 30% 潜伏 / 共振升温期 80% 进攻 / 狂热高潮期 10% 锁定)；
   - 领头羊单只顶配 35%，前锋 15%，跟风平庸标的 0 额度拦截。
3. 【何时卖、买错就出局的终极闭环与高潮逃顶算法】：
   - 铁律 1 (买错立斩)：跌破 VWAP 超过 0.6%~1.0% 或跌破底台支撑，立即清仓止损；
   - 铁律 2 (提前算法设计高抛挂单)：先行者经历 2~4 次临停冲顶时，算法前瞻计算极限高抛价，以 urgency="LIMIT" 挂单提前排队，防复牌戛然而止被核按钮；
   - 铁律 3 (全局领头羊崩盘联动与豁免)：全池领头羊高位跳水时，全舰队收缩防守；但低位独立筑底 (BASE_PREORDER) 与多日通道突破 (SWING_PREORDER) 标的享有免死金牌，不被误杀；
   - 铁律 4 (T+1 追高买入禁令)：次日及之后狂飙标的当天买入无卖出权，严禁追高开仓接盘。
4. 【多周期通道突破预埋单 (SWING_PREORDER)】：
   - 识别 4 日大箱体 + 60F 通道突破且尾盘收最高标的，分配 10% 试探预埋仓，防守线精准锚定 60F 底台 (12.88元)；
5. 【持续跟随市场切换的跟随交易 (换马调仓)】：
   - 持仓走平滞涨、池中冒出超级领头羊时，果断弃弱留强、切换跟随。
"""

import os
import sys
import time
import math
import logging
import threading
import json
import copy
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

from ats.strategy.ipo_market_sentiment_engine import IPOMarketSentimentEngine, MarketSentimentSnapshot
from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal, batch_evaluate_horse_race_ranking
from ats.strategy.channel_secondary_buy_strategy import (
    IPOTradePlan,
    SecondaryBuyStage,
    TAG_CHANNEL_SECONDARY_BUY,
    TAG_SUBNEW_PULLBACK_REENTRY,
    TAG_IPO_VWAP_STABLE,
    TAG_IPO_BID_SURGE,
)
from ats.proactive_exit_engine import ProactiveExitEngine
from ats.strategy.signal_convergence import SignalConvergenceResult, converge_directives

logger = logging.getLogger("IPOTradingCenter")

TRADING_LEDGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "ipo_trading_ledger.json")


@dataclass
class IPOTradingPosition:
    """新股次新统一持仓状态容器 (全生命周期追踪与复盘迭代)"""
    code: str
    name: str
    shares: int = 0
    available_shares: int = 0
    cost_price: float = 0.0
    current_price: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = 999999.0
    entry_time: str = ""
    entry_date: str = ""              # 入场日期 (用于精确控制 T+1 交易权)
    target_weight_pct: float = 0.0    # 目标仓位百分比 (0~100)
    current_weight_pct: float = 0.0
    status: str = "IDLE"              # "IDLE" | "BUYING" | "HOLDING" | "CLIMAX_EXITING" | "STOP_EXITING" | "CLOSED"
    unrealized_pnl_pct: float = 0.0   # 浮动盈亏%
    max_drawdown_from_peak: float = 0.0 # 从最高点回撤%
    last_action: str = ""
    last_action_time: str = ""
    exit_price: float = 0.0           # 平仓卖出价
    exit_time: str = ""               # 平仓时间
    exit_date: str = ""               # 平仓日期
    realized_pnl_pct: float = 0.0     # 实际平仓盈亏%
    realized_pnl_amount: float = 0.0  # 实际平仓盈亏金额
    exit_reason: str = ""             # 平仓原因与复盘记录
    entry_reason: str = ""            # 买入建仓依据
    signal_tier: str = "S"            # 兼容旧代码 (SSS / S / A)
    signal_level: str = "S4"          # 规范命名: "S0" ~ "S5" (生命周期层级)
    quality_grade: str = "S"          # 规范命名: "A" | "S" | "SS" (形态质量等级)
    strategy_tag: str = ""            # 策略正交标签 (IPO_BID_SURGE, IPO_VWAP_STABLE, SUBNEW_PULLBACK_REENTRY, CHANNEL_SECONDARY_BUY)
    trade_plan: Optional[IPOTradePlan] = None
    exit_rule_id: str = ""
    exit_rule_layer: int = 0

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


@dataclass
class IPOOrderDirective:
    """交易中心向执行端分发的标准订单指令"""
    action: str                       # "BUY" | "BUY_SCOUT" | "BUY_CONFIRM" | "SELL" | "EXIT_ALL" | "HOLD" | "SWITCH_SWAP" | "FULL_ROTATION_SWAP"
    code: str
    name: str
    price: float = 0.0
    shares: int = 0
    size_pct: float = 0.0             # 建议仓位占用比 (0~100%)
    urgency: str = "NORMAL"           # "CRITICAL" (立即市价市价/极速) | "LIMIT" (限价)
    reason: str = ""                  # 决策原因与依据 (可解释性)
    horse_rank: int = 999             # 当前在全池的赛马排名
    sentiment_phase: str = ""         # 所处全市场情绪阶段
    timestamp: float = 0.0
    signal_tier: str = "S"            # 兼容旧代码: "SSS" | "S" | "A" | "ALERT"
    signal_level: str = "S4"          # 规范命名: "S0" ~ "S5" (生命周期层级)
    quality_grade: str = "S"          # 规范命名: "A" | "S" | "SS" (形态质量等级)
    strategy_tag: str = ""            # 策略正交标签 (IPO_BID_SURGE, IPO_VWAP_STABLE, SUBNEW_PULLBACK_REENTRY, CHANNEL_SECONDARY_BUY)
    target_swap_code: str = ""        # 全仓轮动换马接力目标代码
    target_swap_name: str = ""        # 全仓轮动换马接力目标名称
    trade_plan: Optional[IPOTradePlan] = None # 挂接的不可变 TradePlan
    exit_rule_id: str = ""
    exit_rule_layer: int = 0
    bypass_t1_lock: bool = False       # 仅灾难性硬止损可置 True

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class IPOTradingCenter:
    """新股次新股统一集中交易仲裁与调度中心单例"""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls(auto_load_ledger=True)
        return cls._instance

    def __init__(self, total_capital: float = 1000000.0, auto_load_ledger: bool = False,
                 ledger_file: Optional[str] = None,
                 exit_engine: Optional[ProactiveExitEngine] = None):
        self.total_capital = total_capital       # 虚拟/实盘总资金池 (默认 100 万基准)
        self.available_cash = total_capital
        self._ledger_file = ledger_file
        self._auto_load_ledger = auto_load_ledger
        self._positions: Dict[str, IPOTradingPosition] = {}
        self._closed_positions: List[IPOTradingPosition] = []
        self._signal_iteration_log: List[Dict[str, Any]] = []
        self._reports_cache: Dict[str, VWAPDetectorSignal] = {}
        self._ranked_cache: List[VWAPDetectorSignal] = []
        self._order_history: List[IPOOrderDirective] = []
        self._notified_directive_keys: Dict[str, float] = {}
        self._today_notified_subscriptions: set = set()
        self.trading_mode: str = "MULTI_POSITION" # 默认组合分仓模式 ("ROTATION_FULL_CAPITAL" 全仓轮动需手动启用)
        self._lock = threading.RLock()
        
        self.sentiment_engine = IPOMarketSentimentEngine.get_instance()
        self._last_market_context: Optional[MarketSentimentSnapshot] = None
        self._last_fleet_eval_ts: float = 0.0
        self._max_total_position_pct: float = 80.0 # 最大允许总仓位
        self.auto_follow_trading: bool = False     # 全自动跟随交易开关 (开启后自动撮合指令)
        self._pending_directives: List[IPOOrderDirective] = []
        self._signal_convergence_summary: Dict[str, Any] = {}
        self._trade_plans: Dict[str, IPOTradePlan] = {} # 标的对应的不变 TradePlan 字典
        self._emitted_plan_ids: set = set()            # 已生成指令的 TradePlan ID 集合 (刷新幂等防重)
        self._emitted_signal_ids: set = set()          # 已生成指令的 Signal ID 集合
        self.exit_engine = exit_engine or ProactiveExitEngine()

        # ATS 外部语音报警与异动信号感知统计与优质注入池
        self._external_signal_stats: Dict[str, int] = {
            "ladder_count": 0,
            "dragon_count": 0,
            "other_count": 0,
            "quality_injected_count": 0
        }
        self._perceived_external_signals: List[Dict[str, Any]] = []
        self._injected_quality_stocks: Dict[str, Dict[str, Any]] = {}

        # Only explicit persistent instances restore non-financial metadata.
        if auto_load_ledger or ledger_file:
            self._load_persisted_ledger()
        if auto_load_ledger and not ledger_file:
            self._sync_from_unified_paper_account()

    def get_position(self, code: str) -> Optional[IPOTradingPosition]:
        """获取指定标的当前的持仓状态容器"""
        clean_code = str(code).strip().zfill(6)
        with self._lock:
            return self._positions.get(clean_code)

    def _sync_from_unified_paper_account(self) -> None:
        """Mirror the TK paper SSOT into the command-room portfolio view."""
        if not self._auto_load_ledger:
            return
        try:
            from ats.unified_paper_account import get_ssot_read_model, reconcile_account

            read_model = get_ssot_read_model()
            kernel_positions = read_model.get("positions", {})
            account = read_model.get("account", {})
            unified_capital = float(account.get("initial_capital", self.total_capital) or self.total_capital)
            synced: Dict[str, IPOTradingPosition] = {}
            for code, raw in kernel_positions.items():
                clean_code = str(code).strip().zfill(6)
                old = self._positions.get(clean_code)
                shares = int(float(raw.get("volume", 0.0) or 0.0))
                cost = float(raw.get("entry_price", 0.0) or 0.0)
                current = float(raw.get("current_price", cost) or cost)
                entry_stamp = str(raw.get("entry_time", "") or "")
                entry_date = entry_stamp.replace("T", " ").split(" ", 1)[0] if entry_stamp else ""
                entry_time = entry_stamp.replace("T", " ").split(" ", 1)[1] if " " in entry_stamp.replace("T", " ") else ""
                name = (
                    getattr(self._reports_cache.get(clean_code), "name", "")
                    or (old.name if old is not None else clean_code)
                )
                pnl_pct = ((current - cost) / cost * 100.0) if cost > 0 else 0.0
                synced[clean_code] = IPOTradingPosition(
                    code=clean_code,
                    name=name,
                    shares=shares,
                    available_shares=shares,
                    cost_price=cost,
                    current_price=current,
                    highest_price=float(raw.get("max_high", current) or current),
                    lowest_price=min(cost, current) if cost > 0 and current > 0 else current,
                    entry_time=entry_time,
                    entry_date=entry_date,
                    current_weight_pct=(shares * current / unified_capital * 100.0) if unified_capital > 0 else 0.0,
                    status="HOLDING",
                    unrealized_pnl_pct=round(pnl_pct, 2),
                    entry_reason=old.entry_reason if old is not None else "TK内核PAPER统一持仓",
                    signal_tier=old.signal_tier if old is not None else "S",
                    signal_level=old.signal_level if old is not None else "S4",
                    quality_grade=old.quality_grade if old is not None else "S",
                    strategy_tag=old.strategy_tag if old is not None else str(raw.get("regime", "")),
                    trade_plan=old.trade_plan if old is not None else None,
                )
            self._positions = synced
            self.total_capital = unified_capital
            self.available_cash = float(account.get("cash", self.available_cash) or 0.0)
            self._paper_reconciliation = reconcile_account(read_model)
        except Exception as exc:
            logger.debug("TK PAPER position sync unavailable: %s", exc)

    def get_trade_plan(self, code: str) -> Optional[IPOTradePlan]:
        """获取指定标的当前的不可变 TradePlan"""
        clean_code = str(code).strip().zfill(6)
        with self._lock:
            return self._trade_plans.get(clean_code)

    def register_trade_plan(self, plan: IPOTradePlan) -> None:
        """注册或更新标的的不可变 TradePlan"""
        if not plan or not plan.code:
            return
        clean_code = str(plan.code).strip().zfill(6)
        with self._lock:
            self._trade_plans[clean_code] = plan
            logger.info(f"[IPO-TRADING] 注册 TradePlan: {plan.name}({clean_code}) Tag={plan.strategy_tag} Lv={plan.signal_level} 防守线={plan.higher_low_stop:.2f}")

    def create_trade_plan_from_signal(self, sig: VWAPDetectorSignal) -> Optional[IPOTradePlan]:
        """
        从前置感知信号构建标准不可变 TradePlan (共用 TradePlan，4大 Tag 正交分离)
        1. IPO_BID_SURGE: 首日早鸟竞价抢筹
        2. IPO_VWAP_STABLE: 首日/次日 VWAP 承接
        3. SUBNEW_PULLBACK_REENTRY: 次新缩量回踩再买点
        4. CHANNEL_SECONDARY_BUY: 长期通道底部次级买点
        """
        if not sig or not sig.code or sig.price <= 0:
            return None

        # 若信号已携带有效且不可变的 IPOTradePlan，直接复用注册，绝不重复生成新对象覆盖破坏
        if getattr(sig, "trade_plan", None) and isinstance(sig.trade_plan, IPOTradePlan):
            self.register_trade_plan(sig.trade_plan)
            return sig.trade_plan

        clean_code = str(sig.code).strip().zfill(6)
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        plan_id = f"TP_{clean_code}_{now_str}"

        # 1. 确定策略 Tag 与质量评级
        if getattr(sig, "is_swing_channel_breakout", False) or sig.signal_type == "SWING_PREORDER":
            tag = TAG_CHANNEL_SECONDARY_BUY
            s_level = "S4"
            q_grade = "SS" if sig.horse_race_score >= 85.0 else "S"
            base_supp = getattr(sig, "multi_day_base_support", 0.0) or sig.base_support_level
            hl_stop = sig.stop_loss_price if sig.stop_loss_price > 0 else round(sig.price * 0.985, 3)
            base_low = base_supp if base_supp > 0 else round(sig.price * 0.97, 3)
            t1 = round(sig.price * 1.08, 3)
            t2 = round(sig.price * 1.15, 3)
        elif sig.signal_type == "IPO_FIRST_BUY" or sig.is_ipo_first_day:
            tag = TAG_IPO_BID_SURGE if sig.launch_time_str <= "09:35" else TAG_IPO_VWAP_STABLE
            s_level = "S5" if sig.horse_race_rank <= 2 else "S4"
            q_grade = "SS" if sig.launch_slope_deg >= 45.0 else "S"
            hl_stop = round(sig.vwap * 0.994, 3) if sig.vwap > 0 else round(sig.price * 0.98, 3)
            base_low = sig.open_anchor_price if sig.open_anchor_price > 0 else round(sig.price * 0.97, 3)
            t1 = round(sig.price * 1.10, 3)
            t2 = round(sig.price * 1.20, 3)
        elif sig.pullback_no_touch or sig.signal_type == "PULLBACK_BUY":
            tag = TAG_SUBNEW_PULLBACK_REENTRY
            s_level = "S4"
            q_grade = "S"
            hl_stop = sig.stop_loss_price if sig.stop_loss_price > 0 else round(sig.vwap * 0.994, 3)
            base_low = round(sig.price * 0.97, 3)
            t1 = round(sig.price * 1.06, 3)
            t2 = round(sig.price * 1.12, 3)
        else:
            # 基础底部结构
            tag = TAG_CHANNEL_SECONDARY_BUY if sig.has_bottom_base else TAG_SUBNEW_PULLBACK_REENTRY
            s_level = "S4"
            q_grade = "A"
            hl_stop = sig.stop_loss_price if sig.stop_loss_price > 0 else round(sig.price * 0.98, 3)
            base_low = sig.base_support_level if sig.base_support_level > 0 else round(sig.price * 0.97, 3)
            t1 = round(sig.price * 1.06, 3)
            t2 = round(sig.price * 1.12, 3)

        plan = IPOTradePlan(
            plan_id=plan_id,
            code=clean_code,
            name=sig.name,
            strategy_tag=tag,
            signal_level=s_level,
            quality_grade=q_grade,
            trigger_price=sig.price,
            buy_zone_min=round(hl_stop * 1.005, 3),
            buy_zone_max=round(sig.price * 1.015, 3),
            higher_low_stop=hl_stop,
            base_low_invalid=base_low,
            hard_stop_loss_pct=round((sig.price - hl_stop) / sig.price * 100.0, 2) if sig.price > 0 else 2.5,
            target_1_channel_mid=t1,
            target_2_swing_high=t2,
            suggested_action="BUY_SCOUT",
            position_pct=30.0,
            expire_at="14:45:00",
            created_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            extra_info={
                "horse_rank": sig.horse_race_rank,
                "horse_score": sig.horse_race_score,
                "vwap": sig.vwap
            }
        )
        self.register_trade_plan(plan)
        return plan

    @property
    def enable_full_rotation(self) -> bool:
        """是否处于全仓轮动模式 (ROTATION_FULL_CAPITAL)"""
        return self.trading_mode == "ROTATION_FULL_CAPITAL"

    @enable_full_rotation.setter
    def enable_full_rotation(self, val: bool) -> None:
        self.set_full_rotation_enabled(val)

    def set_full_rotation_enabled(self, enabled: bool) -> None:
        """开启或关闭全仓轮动模式"""
        mode = "ROTATION_FULL_CAPITAL" if enabled else "MULTI_POSITION"
        self.set_trading_mode(mode)

    def set_trading_mode(self, mode: str) -> None:
        """切换交易模式: ROTATION_FULL_CAPITAL (全仓轮动换马接力) 或 MULTI_POSITION (组合分仓)"""
        with self._lock:
            if mode in ("ROTATION_FULL_CAPITAL", "MULTI_POSITION"):
                self.trading_mode = mode
                logger.info(f"🔄 [IPO-TRADING] 资金模式切换为: {self.trading_mode}")
                self._save_persisted_ledger()

    def set_auto_follow_trading(self, enabled: bool) -> None:
        """开启/关闭全自动跟随交易"""
        with self._lock:
            self.auto_follow_trading = bool(enabled)
            logger.info(f"[IPO-TRADING] 全自动跟随交易状态变更: {self.auto_follow_trading}")

    def get_pending_directives(self) -> List[IPOOrderDirective]:
        """Return the single converged directive view used by UI and execution."""
        with self._lock:
            result: SignalConvergenceResult = converge_directives(self._pending_directives)
            self._signal_convergence_summary = result.summary()
            return list(result.directives)

    def get_signal_convergence_summary(self) -> Dict[str, Any]:
        """Read-only count and suppression reasons for the command-room signal view."""
        with self._lock:
            return dict(self._signal_convergence_summary)

    def _publish_converged_directives(
        self, directives: List[IPOOrderDirective]
    ) -> List[IPOOrderDirective]:
        """Publish one clear, non-conflicting directive set without altering decisions."""
        result: SignalConvergenceResult = converge_directives(directives)
        self._pending_directives = list(result.directives)
        self._signal_convergence_summary = result.summary()
        self._broadcast_directives_to_alert_notifier(self._pending_directives)
        self._auto_execute_if_enabled()
        return self.get_pending_directives()

    def get_closed_positions(self) -> List[IPOTradingPosition]:
        """获取历史已平仓/出局持仓列表 (支持复盘回溯与迭代详情查看)"""
        with self._lock:
            return list(self._closed_positions)

    def get_signal_iteration_log(self) -> List[Dict[str, Any]]:
        """获取全生命周期信号决策与迭代历史日志 (杜绝今天卖了就没下文)"""
        with self._lock:
            return list(self._signal_iteration_log)

    def clear_signal_iteration_logs(self, keep_today: bool = False) -> int:
        """
        清理信号决策与迭代历史日志
        :param keep_today: 若为 True，仅清理历史陈旧日志（保留今日记录）；若为 False，彻底清空全部记录。
        :return: 被清理的记录条数
        """
        with self._lock:
            old_count = len(self._signal_iteration_log)
            if not keep_today:
                self._signal_iteration_log.clear()
            else:
                today_str = time.strftime("%Y-%m-%d")
                self._signal_iteration_log = [
                    item for item in self._signal_iteration_log
                    if str(item.get("time_str", "")).startswith(today_str)
                    or (item.get("timestamp") and time.strftime("%Y-%m-%d", time.localtime(float(item["timestamp"]))) == today_str)
                ]
            removed_count = old_count - len(self._signal_iteration_log)
            self._save_persisted_ledger()
            logger.info(f"🧹 [IPO-TRADING] 信号迭代历史日志清理完毕: 移除了 {removed_count} 条记录, 剩余 {len(self._signal_iteration_log)} 条 (keep_today={keep_today})")
            return removed_count

    def get_closed_trade_reviews(self) -> List[Dict[str, Any]]:
        """Return stable TradePlan-versus-execution metrics for offline review."""
        reviews: List[Dict[str, Any]] = []
        with self._lock:
            closed_items = list(self._closed_positions)
        for item in closed_items:
            value = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
            raw_plan = value("trade_plan")
            plan_get = (
                raw_plan.get if isinstance(raw_plan, dict)
                else (lambda key, default=None: getattr(raw_plan, key, default))
                if raw_plan is not None else lambda key, default=None: default
            )
            entry = float(value("cost_price", 0.0) or 0.0)
            exit_price = float(value("exit_price", 0.0) or 0.0)
            stop = float(plan_get("higher_low_stop", 0.0) or 0.0)
            target_1 = float(plan_get("target_1_channel_mid", 0.0) or 0.0)
            actual_pct = float(value("realized_pnl_pct", 0.0) or 0.0)
            planned_risk_pct = ((entry - stop) / entry * 100.0) if entry > 0 and stop > 0 else 0.0
            planned_reward_pct = ((target_1 - entry) / entry * 100.0) if entry > 0 and target_1 > 0 else 0.0
            reviews.append({
                "code": value("code", ""),
                "name": value("name", ""),
                "plan_id": plan_get("plan_id", ""),
                "strategy_tag": plan_get("strategy_tag", value("strategy_tag", "")),
                "signal_level": plan_get("signal_level", value("signal_level", "")),
                "quality_grade": plan_get("quality_grade", value("quality_grade", "")),
                "entry_price": entry,
                "exit_price": exit_price,
                "planned_stop": stop,
                "planned_target_1": target_1,
                "planned_risk_pct": round(planned_risk_pct, 3),
                "planned_reward_pct": round(planned_reward_pct, 3),
                "planned_reward_risk": round(planned_reward_pct / planned_risk_pct, 3) if planned_risk_pct > 0 else 0.0,
                "actual_return_pct": actual_pct,
                "target_1_deviation_pct": round(actual_pct - planned_reward_pct, 3),
                "exit_rule_id": value("exit_rule_id", ""),
                "exit_rule_layer": int(value("exit_rule_layer", 0) or 0),
                "exit_reason": value("exit_reason", ""),
            })
        return reviews

    def _load_persisted_ledger(self):
        """【💾 持久化账本加载】冷启动瞬间恢复历史持仓、平仓记录、指令历史与信号迭代日志"""
        target_file = getattr(self, "_ledger_file", None)
        if not target_file and getattr(self, "_auto_load_ledger", False):
            target_file = TRADING_LEDGER_FILE
        if not target_file or not os.path.exists(target_file):
            return
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return
                self.trading_mode = data.get("trading_mode", "ROTATION_FULL_CAPITAL")
                restore_financial_snapshot = bool(getattr(self, "_ledger_file", None))
                if restore_financial_snapshot:
                    self.total_capital = float(data.get("total_capital", self.total_capital))
                    self.available_cash = float(data.get("available_cash", self.available_cash))

                # Only explicit legacy/custom ledgers may restore financial facts.
                # Production ATS gets current positions/cash from TK SSOT immediately after load.
                pos_list = data.get("active_positions", []) if restore_financial_snapshot else []
                for p_dict in pos_list:
                    if isinstance(p_dict, dict) and p_dict.get("code"):
                        field_names = set(IPOTradingPosition.__dataclass_fields__.keys())
                        safe_kwargs = {k: v for k, v in p_dict.items() if k in field_names}
                        raw_plan = safe_kwargs.get("trade_plan")
                        if isinstance(raw_plan, dict):
                            plan_fields = set(IPOTradePlan.__dataclass_fields__.keys())
                            safe_kwargs["trade_plan"] = IPOTradePlan(**{
                                k: v for k, v in raw_plan.items() if k in plan_fields
                            })
                        p = IPOTradingPosition(**safe_kwargs)
                        if p.shares > 0:
                            self._positions[p.code] = p
                            if p.trade_plan is not None:
                                self._trade_plans[p.code] = p.trade_plan
                            watch = self.exit_engine.register_position(
                                code=p.code,
                                entry_price=p.cost_price,
                                shares=p.shares,
                            )
                            if p.trade_plan is not None:
                                watch.is_reversal_protected = True
                                watch.higher_low_stop = p.trade_plan.higher_low_stop

                # Restore strategy plans independently from current financial positions.
                for raw_plan in data.get("trade_plans", []):
                    if isinstance(raw_plan, dict) and raw_plan.get("code"):
                        plan_fields = set(IPOTradePlan.__dataclass_fields__.keys())
                        plan = IPOTradePlan(**{k: v for k, v in raw_plan.items() if k in plan_fields})
                        self._trade_plans[str(plan.code).strip().zfill(6)] = plan

                # 恢复已平仓历史记录
                closed_list = data.get("closed_positions", [])
                for c_item in closed_list:
                    if isinstance(c_item, dict) and c_item.get("code"):
                        self._closed_positions.append(c_item)

                # 恢复信号迭代日志
                raw_logs = data.get("signal_iteration_log", [])
                if isinstance(raw_logs, list):
                    self._signal_iteration_log = raw_logs
                logger.info(f"💾 [IPO-LEDGER] 成功从本地恢复交易账本: 活跃持仓 {len(self._positions)} 只 | 已平仓历史 {len(self._closed_positions)} 只 | 信号日志 {len(self._signal_iteration_log)} 条")
        except Exception as e:
            logger.debug(f"加载 IPO 交易账本异常: {e}")

    _load_ledger = _load_persisted_ledger

    def _save_persisted_ledger(self):
        """【💾 原子写盘】将活跃持仓、已平仓战绩、指令历史与信号迭代日志持久化落盘"""
        target_file = getattr(self, "_ledger_file", None)
        if not target_file and getattr(self, "_auto_load_ledger", False):
            target_file = TRADING_LEDGER_FILE
        if not target_file:
            return
        try:
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            active_list = []
            for p in self._positions.values():
                if p.shares > 0:
                    active_list.append(p.to_dict() if hasattr(p, "to_dict") else p.__dict__.copy())

            closed_list = []
            for p in self._closed_positions[:100]:
                if isinstance(p, dict):
                    closed_list.append(p.copy())
                elif hasattr(p, "to_dict"):
                    closed_list.append(p.to_dict())
                else:
                    closed_list.append(p.__dict__.copy())

            order_list = [
                d.to_dict() if hasattr(d, "to_dict") else d.__dict__.copy()
                for d in self._order_history[-100:]
            ]
            
            production_ssot = bool(
                getattr(self, "_auto_load_ledger", False)
                and not getattr(self, "_ledger_file", None)
            )
            trade_plans = [
                plan.to_dict() if hasattr(plan, "to_dict") else plan.__dict__.copy()
                for plan in self._trade_plans.values()
            ]
            payload = {
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "trading_mode": self.trading_mode,
                "financial_ssot": "KernelGateway.get_account_read_model",
                "trade_plans": trade_plans,
                "closed_positions": closed_list,
                "directive_history": order_list,
                "signal_iteration_log": self._signal_iteration_log[:200],
            }
            if not production_ssot:
                # Explicit legacy/custom ledgers remain backwards compatible for tests/tools.
                payload.update({
                    "total_capital": self.total_capital,
                    "available_cash": self.available_cash,
                    "active_positions": active_list,
                    "order_history": order_list,
                })
            tmp_f = f"{target_file}.tmp_{os.getpid()}"
            with open(tmp_f, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            if os.path.exists(target_file):
                os.replace(tmp_f, target_file)
            else:
                os.rename(tmp_f, target_file)
        except Exception as e:
            logger.debug(f"持久化保存 IPO 交易账本异常: {e}")

    _save_ledger = _save_persisted_ledger

    def check_today_ipo_subscriptions(self) -> List[Dict[str, Any]]:
        """
        【📢 今日新股申购即时嗅探与语音弹窗通知】
        - 直连 NewStockFetcher 权威 IPO 日历；
        - 识别 apply_date == today 的可申购标的；
        - 每日安全去重，通过 AlertNotifier 广播语音与屏幕卡片。
        """
        try:
            from ats.new_stock_fetcher import NewStockFetcher
            fetcher = NewStockFetcher.get_instance()
            ipo_dict = {}
            if hasattr(fetcher, "fetch_ipo_calendar"):
                try:
                    ipo_dict = fetcher.fetch_ipo_calendar() or {}
                except Exception:
                    ipo_dict = {}
            if not ipo_dict and hasattr(fetcher, "_cached_ipo_dict"):
                ipo_dict = fetcher._cached_ipo_dict or {}
        except Exception:
            ipo_dict = {}

        today_str = time.strftime("%Y-%m-%d")
        new_subscriptions = []

        with self._lock:
            for c, info in (ipo_dict or {}).items():
                if not isinstance(info, dict):
                    continue
                apply_d = str(info.get("apply_date", "") or "").strip()
                if apply_d == today_str:
                    sub_key = f"{today_str}_{c}"
                    if sub_key not in self._today_notified_subscriptions:
                        self._today_notified_subscriptions.add(sub_key)
                        info_copy = dict(info)
                        if "code" not in info_copy:
                            info_copy["code"] = str(c)
                        new_subscriptions.append(info_copy)

        if new_subscriptions:
            for sub in new_subscriptions:
                c = sub.get("code", "")
                nm = sub.get("name", f"新股{c}")
                apply_c = sub.get("apply_code", c)
                px = sub.get("issue_price", 0.0)
                px_str = f"{px:.2f}" if px > 0 else "待定"
                online_num = sub.get("online_issue_num")
                num_str = f" | 顶格申购: {online_num}股" if online_num else ""

                reason_text = f"今日新股申购: 代码{c} | 申购代码:{apply_c} | 发行价:¥{px_str}{num_str}"
                logger.info(f"📢 [IPO-SUBSCRIPTION] 发现今日新股申购标的: {nm}({c}) 发行价:¥{px_str}")

                try:
                    from ats.alert_notifier import AlertNotifier
                    AlertNotifier.get_instance().notify_special_signal(
                        code=c,
                        name=nm,
                        reason=reason_text,
                        score=99.0,
                        is_force=True,
                        source="新股申购"
                    )
                except Exception as ex_sub:
                    logger.debug(f"新股申购通知异常: {ex_sub}")

        return new_subscriptions

    # ── 外部信号感知、质量策略评估与自更新优质池注入 ──

    def is_ipo_or_subnew_stock(self, code: str) -> bool:
        """
        判断标的是否属于新股/次新股范畴
        - 创业板 301xxx、科创板 688xxx、北交所 920xxx/43xxxx/83xxxx/87xxxx 天然属于次新/新股主战场；
        - 查询 NewStockFetcher 日历，近 1 年 (250交易日) 内上市的新标的亦符合次新特征。
        """
        clean_code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
        if clean_code.startswith(("301", "688", "920", "43", "83", "87")):
            return True
        try:
            from ats.new_stock_fetcher import NewStockFetcher
            fetcher = NewStockFetcher.get_instance()
            ipo_dict = getattr(fetcher, "_cached_ipo_dict", None)
            if ipo_dict and clean_code in ipo_dict:
                return True
        except Exception:
            pass
        return False

    def evaluate_external_signal_quality(
        self, source: str, code: str, name: str, reason: str, score: float = 0.0,
        extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        【质量策略即时价值评估引擎】
        - 统一理解每日天梯语音报警信号与强势板块龙头突击跟单信号；
        - 即时评估信号质地、加速能力、VWAP均线结构与次新股属性；
        - 坚决过滤劣质信号 (如破位暴跌、天量冲顶跳水、炸板未回、大阴线退潮)；
        - 授予规范的战术评级 (👑 SSS / 🥇 S / 🎯 A / ❌ REJECT) 与专属来源标签。
        """
        clean_code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
        reason_str = str(reason or "").strip()

        # 1. 来源标识标准化
        source_str = str(source or "").strip()
        if "天梯" in source_str:
            source_tag = "⚡ 天梯报警"
        elif "龙头" in source_str:
            source_tag = "🚀 龙头突击"
        else:
            source_tag = f"🏷️ {source_str}" if source_str else "🏷️ 外部信号"

        is_subnew = self.is_ipo_or_subnew_stock(clean_code)

        # 2. 劣质/负面恶性形态一票否决拦截
        NEGATIVE_KEYWORDS = ["破位", "大跌", "炸板未回", "雪崩", "跳水", "坚决出局", "跌停", "闪崩", "泥沙俱下", "退潮雪崩"]
        if any(neg in reason_str for neg in NEGATIVE_KEYWORDS):
            return {
                "is_quality": False,
                "decision": "REJECT_NEGATIVE",
                "code": clean_code,
                "name": name,
                "source": source_str,
                "source_tag": source_tag,
                "signal_tier": "REJECT",
                "quality_score": 0.0,
                "is_subnew": is_subnew,
                "reason": f"拦截淘汰: 包含负面破位/退潮特征 ({reason_str})",
                "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        # 分数极低门槛过滤 (< 78分且无加速/龙头字眼)
        if score < 78.0 and not any(kw in reason_str for kw in ["双加速", "龙头", "加速", "首发", "涨停"]):
            return {
                "is_quality": False,
                "decision": "REJECT_LOW_SCORE",
                "code": clean_code,
                "name": name,
                "source": source_str,
                "source_tag": source_tag,
                "signal_tier": "REJECT",
                "quality_score": float(score),
                "is_subnew": is_subnew,
                "reason": f"拦截淘汰: 评分低于78分基础门槛({score:.1f})",
                "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        # 3. 正向加速形态量化加权与底层12级潮汐适配 (杜绝无脑打100满分)
        raw_score = float(score) if score > 0 else 75.0
        if raw_score >= 90.0:
            base_quality = 80.0 + (raw_score - 90.0) * 0.4
        elif raw_score >= 80.0:
            base_quality = 75.0 + (raw_score - 80.0) * 0.5
        else:
            base_quality = max(65.0, raw_score)

        bonus = 0.0

        # 次新股溢价加分 (轻装上阵，无历史套牢盘)
        if is_subnew:
            bonus += 3.0

        # 核心加速形态提权
        if "双加速" in reason_str:
            bonus += 5.0
        if "光脚加速" in reason_str or "缺口加速" in reason_str:
            bonus += 3.0
        if "首板突破" in reason_str or "放量反包" in reason_str or "主动扫买" in reason_str:
            bonus += 4.0
        if "领涨龙头" in reason_str or "板块龙头" in reason_str or "爆款领头羊" in reason_str:
            bonus += 5.0
        if "首发吸筹" in reason_str or "早鸟" in reason_str or "首发上市" in reason_str:
            bonus += 6.0

        # 结合底层 12 级潮汐状态机 (T0~T11) 自适应调节
        current_tide = "T0_INSUFFICIENT"
        try:
            if getattr(self, "_last_market_context", None):
                current_tide = getattr(self._last_market_context, "tide_state", "T0_INSUFFICIENT")
            elif hasattr(self, "sentiment_engine"):
                snap = self.sentiment_engine.get_latest_snapshot()
                if snap:
                    current_tide = getattr(snap, "tide_state", "T0_INSUFFICIENT")
        except Exception:
            pass

        tide_adj = 0.0
        if current_tide in ("T1_CLIMAX_DISTRIBUTION", "T11_OVERHEATED"):
            # 高潮派发与过热期：严厉惩罚追高，动能分折减
            tide_adj = -8.0
        elif current_tide in ("T2_EBB_EARLY", "T3_EBB_SPREAD", "T4_PANIC_ACCEL"):
            # 退潮与恐慌期：对纯追高施加风控扣分，防接飞刀；若有平底防守则不扣
            if not any(kw in reason_str for kw in ["平底", "次级买点", "筑底", "缩量"]):
                tide_adj = -6.0
        elif current_tide in ("T5_ICE", "T6_ICE_DIVERGENCE"):
            # 冰点与背离期：对率先逆势放量突破/首发吸筹的先锋给予溢价
            if any(kw in reason_str for kw in ["首发吸筹", "反包", "突破", "龙头", "次级买点"]):
                tide_adj = +4.0
        elif current_tide in ("T8_REFLOW_CONFIRM", "T9_FLOOD_SPREAD", "T10_MAIN_UP"):
            # 回流与主升浪：顺风共振
            if "龙头" in reason_str or "双加速" in reason_str:
                tide_adj = +3.0

        final_quality = max(40.0, min(95.0, base_quality + bonus + tide_adj))

        # 4. 战术级别判定 (SSS / S / A)
        if final_quality >= 90.0:
            signal_tier = "SSS"
        elif final_quality >= 82.0:
            signal_tier = "S"
        else:
            signal_tier = "A"

        # 恐慌与高潮派发期降级保护
        if current_tide in ("T1_CLIMAX_DISTRIBUTION", "T4_PANIC_ACCEL") and signal_tier == "SSS":
            signal_tier = "S"

        # 5. 准入资格判定 (是否判定为优质标的以注入自更新优质池)
        # 次新股只需达到 78 分即可准入；主板标的需具备顶级龙头质地 (>= 85 分或明确龙头/加速) 即可作为全市场标杆准入
        if is_subnew:
            is_quality = (final_quality >= 78.0)
        else:
            is_quality = (final_quality >= 85.0 or "龙头" in reason_str or "双加速" in reason_str)

        return {
            "is_quality": is_quality,
            "decision": "ACCEPT" if is_quality else "REJECT",
            "code": clean_code,
            "name": name,
            "source": source_str,
            "source_tag": source_tag,
            "signal_tier": signal_tier,
            "quality_score": round(final_quality, 1),
            "is_subnew": is_subnew,
            "reason": reason_str,
            "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def ingest_external_alarm_signal(
        self, source: str, code: str, name: str, reason: str, score: float = 0.0,
        extra: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        【外部语音报警与突击信号统一汇聚感知接口】
        - 接收来自每日天梯、龙头突击等模块的实时异动；
        - 即时执行质量策略评估；
        - 优质标的自动注入新股次新股检查中心并赋予专属来源标签；
        - 沉淀感知流水与统计，反哺指挥室与检查中心保持自更新优质池能力。
        """
        clean_code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
        if not clean_code or len(clean_code) != 6:
            return None

        # 统计计数
        with self._lock:
            s_str = str(source or "")
            if "天梯" in s_str:
                self._external_signal_stats["ladder_count"] = self._external_signal_stats.get("ladder_count", 0) + 1
            elif "龙头" in s_str:
                self._external_signal_stats["dragon_count"] = self._external_signal_stats.get("dragon_count", 0) + 1
            else:
                self._external_signal_stats["other_count"] = self._external_signal_stats.get("other_count", 0) + 1

        eval_res = self.evaluate_external_signal_quality(source, clean_code, name, reason, score, extra)

        with self._lock:
            self._perceived_external_signals.insert(0, eval_res)
            if len(self._perceived_external_signals) > 100:
                self._perceived_external_signals = self._perceived_external_signals[:100]

            if eval_res.get("is_quality", False):
                self._external_signal_stats["quality_injected_count"] = self._external_signal_stats.get("quality_injected_count", 0) + 1
                self._injected_quality_stocks[clean_code] = eval_res

                tier = eval_res.get("signal_tier", "S")
                stag = eval_res.get("source_tag", "🏷️ 外部信号")
                q_score = eval_res.get("quality_score", 90.0)
                price_val = 0.0
                if extra and isinstance(extra, dict):
                    price_val = float(extra.get("price") or extra.get("current_price") or extra.get("close") or 0.0)
                if price_val <= 0.0:
                    cached_sig = self._reports_cache.get(clean_code)
                    if cached_sig and getattr(cached_sig, "price", 0.0) > 0:
                        price_val = float(cached_sig.price)
                    else:
                        for r_sig in self._ranked_cache:
                            if r_sig.code == clean_code and getattr(r_sig, "price", 0.0) > 0:
                                price_val = float(r_sig.price)
                                break

                # 外部信号注入属于雷达感知并转入次新股重点监控池，不预设买入满仓，待次新策略产生明确买点
                self._append_signal_iteration_log(
                    action="SIGNAL_INJECT",
                    code=clean_code,
                    name=name,
                    price=price_val,
                    size_pct=0.0,
                    reason=f"[{stag}·{q_score:.0f}分] 质量策略评估通过，转入新股次新检查中心: {reason}",
                    signal_tier=tier
                )

        # 若新股次新股检查中心正在运行，立即向其注入优质标的
        if eval_res.get("is_quality", False):
            try:
                from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
                active_detector = IPOSubnewDetectorDialog.get_active_instance()
                if active_detector:
                    active_detector.inject_quality_signal_stock(
                        code=clean_code,
                        name=name,
                        source_tag=eval_res.get("source_tag", "🏷️ 优质信号"),
                        reason=eval_res.get("reason", reason),
                        signal_tier=eval_res.get("signal_tier", "S"),
                        quality_score=eval_res.get("quality_score", 90.0)
                    )
            except Exception as ex_det:
                logger.debug(f"向次新检查中心注入优质信号异常: {ex_det}")

        return eval_res

    def get_external_signal_stats(self) -> Dict[str, int]:
        """获取外部信号感知统计 (天梯、龙头突击、优质转入等)"""
        with self._lock:
            return dict(self._external_signal_stats)

    def get_perceived_external_signals(self) -> List[Dict[str, Any]]:
        """获取最近感知的外部信号流水"""
        with self._lock:
            return list(self._perceived_external_signals)

    def get_injected_quality_stocks(self) -> Dict[str, Dict[str, Any]]:
        """获取已被质量策略纳准的全部优质信号标的映射"""
        with self._lock:
            return dict(self._injected_quality_stocks)

    def submit_batch_reports(self, signals: List[VWAPDetectorSignal]) -> None:
        """批量提交各标的感知报告并统一触发统筹评估"""
        if not signals:
            return
        for s in signals:
            self.submit_stock_perception_report(s)
        self.evaluate_fleet_and_generate_orders()

    def evaluate_fleet_and_arbitrate(self, force_immediate: bool = True) -> List[IPOOrderDirective]:
        """统筹仲裁接口，兼容 evaluate_fleet_and_generate_orders"""
        return self.evaluate_fleet_and_generate_orders()

    def submit_stock_perception_report(self, signal: VWAPDetectorSignal) -> None:
        """
        【各守护标的提交体检与感知报告】
        - 无论是哪个后台 Worker 或哪个 UI 窗口计算完成，统一将报告汇交至交易中心；
        - 交易中心将其纳入全池大局统一评判。
        """
        if not signal or not signal.code:
            return
        clean_code = str(signal.code).strip().zfill(6)
        with self._lock:
            self._reports_cache[clean_code] = signal
            # 同步更新已有持仓的现价与高低极值
            if clean_code in self._positions:
                pos = self._positions[clean_code]
                if pos.shares > 0 and signal.price > 0:
                    pos.current_price = signal.price
                    if signal.price > pos.highest_price:
                        pos.highest_price = signal.price
                    if signal.price < pos.lowest_price:
                        pos.lowest_price = signal.price
                    if pos.cost_price > 0:
                        pos.unrealized_pnl_pct = round((pos.current_price - pos.cost_price) / pos.cost_price * 100.0, 2)
                    if pos.highest_price > 0:
                        pos.max_drawdown_from_peak = round((pos.highest_price - pos.current_price) / pos.highest_price * 100.0, 2)

    def evaluate_fleet_and_generate_orders(self) -> List[IPOOrderDirective]:
        """
        【核心决策引擎：掌握全数据，全池横向赛马，统一仲裁并产出交易指令】
        - 消除“各管一摊，自己看着自己守护的个股很好不知道山外有山”；
        - 全局仲裁结果直接回写到每个 signal 的 global_fleet_role 与 global_arbitration_desc；
        - 支持弃弱留强·换马调仓 (SWITCH_SWAP) 与买错立斩 (STOP_LOSS)。
        """
        self._sync_from_unified_paper_account()
        with self._lock:
            all_signals = list(self._reports_cache.values())
            if not all_signals:
                self._pending_directives = []
                self._signal_convergence_summary = converge_directives([]).summary()
                return []

            now_ts = time.time()
            today_str = time.strftime("%Y-%m-%d")
            directives: List[IPOOrderDirective] = []

            # 1. 全局大盘量能与新股梯队情绪感知 (依据最新汇交的全景信号实时感知)
            sentiment = self.sentiment_engine.get_market_sentiment(all_signals, force_refresh=True)
            self._last_market_context = sentiment

            # 2. 全池执行横向赛马冒泡排位 (“山外有山”·结合12级潮汐适配)
            ranked_signals = batch_evaluate_horse_race_ranking(
                all_signals,
                tide_state=getattr(sentiment, "tide_state", None)
            )
            self._ranked_cache = ranked_signals

            # 找出全池 Top 1 真实领头羊标杆 (未破位且非高潮狂热)
            valid_leaders = [s for s in ranked_signals if s.is_above_vwap and not s.is_climax_exit]
            top_leader: Optional[VWAPDetectorSignal] = valid_leaders[0] if valid_leaders else None

            # 3. ── 【“山外有山”全局统筹仲裁：消除局部盲区，回写至信号对象】 ──
            leader_is_crashing = False
            leader_code = ""
            for s in ranked_signals:
                if s.is_climax_exit:
                    leader_is_crashing = True
                    leader_code = s.code
                    break

            for sig in ranked_signals:
                # 计算与全池第一领头羊的差距
                if top_leader and top_leader.code != sig.code:
                    sig.relative_to_leader_gap = round(max(0.0, top_leader.horse_race_score - sig.horse_race_score), 1)
                else:
                    sig.relative_to_leader_gap = 0.0

                # 仲裁 A: 自身极端高潮冲顶天量滞涨 (坚决平仓逃顶)
                if sig.is_climax_exit:
                    sig.global_fleet_role = "CLIMAX_EXIT"
                    sig.global_arbitration_desc = f"🚨【高潮平仓 0%仓】偏离VWAP达+{sig.vwap_diff_pct:.1f}%且放天量滞涨冲顶，主力疯狂兑现，锁定翻倍胜果！"
                    continue

                # 仲裁 B0: 60F通道突破+多日平底尾盘蓄势 (蓝色光标同款结构)
                if sig.signal_type == "SWING_PREORDER":
                    sig.global_fleet_role = "SWING_PREORDER"
                    space_str = f"博周一冲破VWAP(空间+{sig.rebound_to_vwap_space_pct:.1f}%)" if sig.rebound_to_vwap_space_pct > 0 else "跨日反转蓄势"
                    sig.global_arbitration_desc = f"🔭【通道突破 12%仓】60F突破下降通道+多日平底({sig.base_support_level:.2f})尾盘收最高，防守线{sig.stop_loss_price:.2f}元(60F底台)，{space_str}！"
                    continue

                # 仲裁 B1: 底部放量共振加速 (动能拐点确立，主升/反抽突击)
                if sig.signal_type == "BASE_BREAKOUT":
                    sig.global_fleet_role = "RESONANCE_BUY"
                    space_str = f"博回抽VWAP+{sig.rebound_to_vwap_space_pct:.1f}%空间" if sig.rebound_to_vwap_space_pct > 0 else "放量突击"
                    sig.global_arbitration_desc = f"⚡【共振加速 20%仓】底部平底({sig.base_support_level:.2f})放量加速拐头，{space_str}，止损{sig.stop_loss_price:.2f}元！"
                    continue

                # 仲裁 B2: 底部平底缩量企稳预埋潜伏 (提前埋单，不追高)
                if sig.signal_type == "BASE_PREORDER":
                    sig.global_fleet_role = "BASE_PREORDER"
                    space_str = f"向上距VWAP空间+{sig.rebound_to_vwap_space_pct:.1f}%" if sig.rebound_to_vwap_space_pct > 0 else ""
                    sig.global_arbitration_desc = f"🎯【筑底预埋 15%仓】底部({sig.base_support_level:.2f})缩量横盘构筑扎实结构，动能拐头初现，提前预埋潜伏，{space_str}，买错跌破{sig.stop_loss_price:.2f}元立斩！"
                    continue

                # 仲裁 B_SEC: 长期通道企稳底部结构次级买点 (SECONDARY_BUY 独立战术角色，坚决避免被普通 FOLLOWER 和 VWAP 破位误杀)
                is_sec_buy_stage = (
                    sig.signal_type == "SECONDARY_BUY"
                    or getattr(sig, "channel_stage", "") in (SecondaryBuyStage.SECONDARY_BUY, "SECONDARY_BUY")
                )
                if is_sec_buy_stage:
                    sig.global_fleet_role = "SECONDARY_BUY"
                    plan = getattr(sig, "trade_plan", None)
                    hl_stop = getattr(sig, "higher_low_stop", 0.0) or (plan.higher_low_stop if plan else sig.stop_loss_price)
                    base_low = getattr(sig, "base_low_invalid", 0.0) or (plan.base_low_invalid if plan else sig.base_support_level)
                    buy_zone_max = plan.buy_zone_max if (plan and plan.buy_zone_max > 0) else round(sig.price * 1.015, 3)
                    q_g = getattr(plan, "quality_grade", "") or getattr(sig, "quality_grade", "S")
                    sig.global_arbitration_desc = (
                        f"👑【次级买点 {q_g}级】长期通道企稳，回踩抬高底放量确认，"
                        f"防守线{hl_stop:.2f}元(失效底{base_low:.2f})，买入网格上限{buy_zone_max:.2f}元，拒绝追高！"
                    )
                    continue

                # 仲裁 B3: 普通破位无结构股 (买错立斩出局)
                if not sig.is_above_vwap and sig.vwap_diff_pct < -0.6:
                    sig.global_fleet_role = "STOP_LOSS"
                    sig.global_arbitration_desc = f"⛔【买错立斩 0%仓】跌破VWAP({sig.vwap:.2f})达{sig.vwap_diff_pct:.1f}%且无筑底结构，全池一票否决，买错坚决出局斩仓！"
                    continue

                # 仲裁 C: 市场冰点泥沙俱下 (全池规避)
                if sentiment.heat_stage == "❄️ 冰点极寒" or sentiment.vwap_hold_ratio < 20.0:
                    sig.global_fleet_role = "ICE_ABORT"
                    sig.global_arbitration_desc = f"❄️【全局冰点 0%仓】次新池站稳率仅{sentiment.vwap_hold_ratio}%，山外无山皆泥沙，全局防守禁止开仓！"
                    continue

                # 仲裁 D: 🥇 爆款领头羊 (全池第 1 标杆，优先确立地位)
                if top_leader and sig.code == top_leader.code:
                    sig.global_fleet_role = "LEADER"
                    if sig.signal_type == "IPO_FIRST_BUY":
                        sig.global_arbitration_desc = f"🔥【首发吸筹 35%仓】首发上市紧贴VWAP({sig.vwap:.2f})惜售，全池唯一首发标杆，锁定极低成本重仓进击！"
                    elif sentiment.heat_stage == "🌋 狂热高潮":
                        sig.global_arbitration_desc = f"🥇【高潮领头羊 10%仓】全市场情绪狂热高潮，领头羊轻仓快进快出，严防T+1次日踩踏！"
                    else:
                        sig.global_arbitration_desc = f"🥇【全池领头羊 35%仓】动能分{sig.horse_race_score:.0f}全池第一，{sig.launch_time_str}拔地而起，集中重仓围猎！"
                    continue

                # 仲裁 E: 🥈 梯队前锋 (紧随领头羊，共振跟进)
                if sig.horse_race_rank in (2, 3) and sig.horse_race_score >= 70.0 and sig.is_above_vwap:
                    sig.global_fleet_role = "VANGUARD"
                    leader_nm = top_leader.name if top_leader else "领头羊"
                    sig.global_arbitration_desc = f"🥈【梯队前锋 15%仓】动能分{sig.horse_race_score:.0f}，紧随领头羊[{leader_nm}]多头共振，顺风跟进！"
                    continue

                # 仲裁 F: 龙头高潮冲顶崩盘联动避险 (仅对第 4 名之后的跟风高位标的退潮拦截，但低位独立筑底/共振/通道突破/次级买点标的除外！)
                if leader_is_crashing and sig.code != leader_code:
                    if (sig.signal_type in ("BASE_PREORDER", "BASE_BREAKOUT", "SWING_PREORDER", "SECONDARY_BUY")
                            or getattr(sig, "channel_stage", "") in (SecondaryBuyStage.SECONDARY_BUY, "SECONDARY_BUY")
                            or sig.has_bottom_base):
                        pass  # 底部独立结构与次级买点标的不被龙头冲顶误杀
                    else:
                        sig.global_fleet_role = "PANIC_DEFENSE"
                        sig.global_arbitration_desc = f"🛡️【全局避险 0%仓】超级龙头({leader_code})天量冲顶跳水，板块情绪退潮，跟风标的严禁盲目接飞刀！"
                        continue

                # 仲裁 G: 市场狂热高潮期对后排与跟风只卖不买，防T+1追高被埋
                if sentiment.heat_stage == "🌋 狂热高潮":
                    sig.global_fleet_role = "CLIMAX_DEFENSE"
                    sig.global_arbitration_desc = f"🌋【高潮避险 0%仓】全市场情绪极度狂热，跟风标的只卖不买，防T+1追高被埋纸面财富！"
                    continue

                # 仲裁 H: 🥉 后排跟风 (山外有山)
                sig.global_fleet_role = "FOLLOWER"
                leader_nm = top_leader.name if top_leader else "领头羊"
                gap_val = sig.relative_to_leader_gap
                sig.global_arbitration_desc = f"🥉【山外有山·观望 0%仓】动能分{sig.horse_race_score:.0f}落后领头羊[{leader_nm}]{gap_val:.0f}分，资金有限集中围猎头部，禁止分仓跟风！"


            # 4. ── 【防守端出局：何时卖 & 买错立斩出局】 ──
            for code, pos in list(self._positions.items()):
                if pos.shares <= 0:
                    continue

                sig = self._reports_cache.get(code)

                # 4.0 潮汐总控铁律：T1 高潮派发不是单纯的“停止买入”，而是
                # 自上而下主动降风险。非龙头全退，唯一 SSS 龙头先减半进入防守。
                # 当日新仓仍受 record_order_execution 的 T+1 物理锁约束。
                if getattr(sentiment, "tide_state", "") == "T1_CLIMAX_DISTRIBUTION":
                    exit_price = (
                        sig.price if sig is not None and sig.price > 0
                        else (pos.current_price if pos.current_price > 0 else pos.cost_price)
                    )
                    is_protected_leader = bool(
                        sig is not None
                        and pos.signal_tier == "SSS"
                        and (sig.global_fleet_role == "LEADER" or sig.horse_race_rank == 1)
                    )
                    tradable_shares = min(
                        pos.shares,
                        pos.available_shares if pos.available_shares > 0 else pos.shares,
                    )
                    action = "REDUCE_HALF" if is_protected_leader else "EXIT_ALL"
                    shares = (
                        int(tradable_shares * 0.5 / 100) * 100
                        if is_protected_leader else tradable_shares
                    )
                    if is_protected_leader and shares < 100:
                        action = "EXIT_ALL"
                        shares = tradable_shares
                    if exit_price > 0 and shares > 0:
                        directives.append(IPOOrderDirective(
                            action=action,
                            code=code,
                            name=pos.name,
                            price=exit_price,
                            shares=shares,
                            size_pct=50.0 if action == "REDUCE_HALF" else 100.0,
                            urgency="CRITICAL",
                            reason=(
                                "🚨 T1高潮派发组合风控: SSS核心龙头先减半锁盈并转入防守警戒。"
                                if action == "REDUCE_HALF" else
                                "🚨 T1高潮派发组合风控: 市场放量分化且VWAP承接衰退，非核心持仓立即退出。"
                            ),
                            horse_rank=sig.horse_race_rank if sig is not None else 999,
                            sentiment_phase=sentiment.heat_stage,
                            timestamp=now_ts,
                            signal_tier=pos.signal_tier,
                            signal_level=pos.signal_level,
                            quality_grade=pos.quality_grade,
                            strategy_tag=pos.strategy_tag,
                            trade_plan=pos.trade_plan,
                            exit_rule_id="exit_tide_climax_distribution",
                            exit_rule_layer=0,
                        ))
                    continue

                if not sig or sig.price <= 0:
                    continue

                # 4.1 铁律 1: 买错立斩出局 (跌破止损线)
                # 底部结构预埋标的：精准按底台防守线(-0.8%)执行；普通标的按跌破 VWAP 0.6% 执行
                is_stop_out = False
                stop_reason = ""
                if sig.has_bottom_base and sig.stop_loss_price > 0:
                    if sig.price < sig.stop_loss_price:
                        is_stop_out = True
                        stop_reason = f"⛔ 底台破位止损: 跌破底部平台防守线({sig.stop_loss_price:.2f})，买错立斩出局，严禁死扛！"
                else:
                    if not sig.is_above_vwap and sig.vwap_diff_pct < -0.6:
                        is_stop_out = True
                        stop_reason = f"⛔ 破位止损出局: 跌破VWAP({sig.vwap:.2f})达{sig.vwap_diff_pct:.1f}%，买错坚决出局斩仓，严禁死扛！"

                if is_stop_out:
                    directives.append(IPOOrderDirective(
                        action="SELL",
                        code=code,
                        name=pos.name,
                        price=sig.price,
                        shares=pos.shares,
                        size_pct=0.0,
                        urgency="CRITICAL",
                        reason=stop_reason,
                        horse_rank=sig.horse_race_rank,
                        sentiment_phase=sentiment.heat_stage,
                        timestamp=now_ts
                    ))
                    continue

                # 4.2 铁律 2: 极端高潮冲刺平仓与计算机提前算法挂单 (沈鼓集团同款高点逃顶)
                if sig.is_climax_exit or (sig.suspension_count >= 1 and sig.vwap_diff_pct >= 20.0):
                    sell_px = sig.climax_preset_sell_price if sig.climax_preset_sell_price > 0 else sig.price
                    urg_type = "LIMIT" if sig.climax_preset_sell_price > sig.price else "CRITICAL"
                    directives.append(IPOOrderDirective(
                        action="SELL",
                        code=code,
                        name=pos.name,
                        price=sell_px,
                        shares=pos.shares,
                        size_pct=0.0,
                        urgency=urg_type,
                        reason=f"🚨 提前算法设计挂单高抛: 累计临停加速，提前挂单¥{sell_px:.2f}冲顶止盈，防复牌戛然而止被核按钮！",
                        horse_rank=sig.horse_race_rank,
                        sentiment_phase=sentiment.heat_stage,
                        timestamp=now_ts
                    ))
                    continue

                # 4.3 铁律 3: 全局领头羊崩盘联动避险
                if leader_is_crashing and code != leader_code:
                    if sig.horse_race_rank > 2 or sig.vwap_diff_pct < 5.0:
                        directives.append(IPOOrderDirective(
                            action="SELL",
                            code=code,
                            name=pos.name,
                            price=sig.price,
                            shares=pos.shares,
                            size_pct=0.0,
                            urgency="CRITICAL",
                            reason=f"🛡️ 全局避险联动: 全池超级领头羊({leader_code})天量冲顶跳水，板块情绪退潮，跟随标的立即平仓防泥沙俱下！",
                            horse_rank=sig.horse_race_rank,
                            sentiment_phase=sentiment.heat_stage,
                            timestamp=now_ts
                        ))
                        continue

            # 5. ── 【调仓换马：弃弱留强与全仓轮动 (FULL_ROTATION_SWAP / SWITCH_SWAP)】 ──
            # 持续跟随市场切换：持仓股动能滞涨落后，全池涌现出更强的 Rank 1 领头羊时果断换马
            rotation_tide_state = getattr(sentiment, "tide_state", "T0_INSUFFICIENT")
            t10_absolute_leader = bool(
                top_leader
                and top_leader.horse_race_rank == 1
                and top_leader.signal_tier == "SSS"
                and top_leader.horse_race_score >= 90.0
            )
            rotation_entry_allowed = (
                rotation_tide_state != "T1_CLIMAX_DISTRIBUTION"
                and (rotation_tide_state != "T10_MAIN_UP" or t10_absolute_leader)
            )
            if rotation_entry_allowed and top_leader and top_leader.code not in self._positions:
                for code, pos in list(self._positions.items()):
                    if pos.shares <= 0 or code == top_leader.code:
                        continue
                    p_sig = self._reports_cache.get(code)
                    required_rotation_gap = 25.0 if rotation_tide_state == "T10_MAIN_UP" else 15.0
                    if p_sig and (p_sig.relative_to_leader_gap >= required_rotation_gap or p_sig.horse_race_rank > 2):
                        # 检查新领头羊是否具备进击买点
                        if top_leader.signal_type in ("IPO_FIRST_BUY", "PULLBACK_BUY", "BREAKOUT", "BASE_BREAKOUT") or (top_leader.launch_time_str <= "09:50" and top_leader.launch_slope_deg >= 30.0):
                            if self.trading_mode == "ROTATION_FULL_CAPITAL":
                                # 👑 【全仓轮动接力模式】：生成原子换马决议，受制于情绪风险模式、风险乘数与潮汐绝对上限
                                risk_mode = getattr(sentiment, "risk_mode", "NORMAL")
                                risk_mult = max(0.0, min(1.0, float(
                                    getattr(sentiment, "position_multiplier", 1.0) or 0.0
                                )))
                                if risk_mode == "BLOCK_NEW_BUYS":
                                    risk_mult = 0.0

                                tide_state = getattr(sentiment, "tide_state", "T0_INSUFFICIENT")
                                if tide_state in ("T1_CLIMAX_DISTRIBUTION", "T4_PANIC_ACCEL"):
                                    swap_cap = 0.0
                                elif tide_state != "T0_INSUFFICIENT":
                                    swap_cap = max(0.0, min(100.0, float(
                                        getattr(sentiment, "tide_position_cap_pct", 100.0)
                                    )))
                                else:
                                    swap_cap = 100.0

                                effective_swap_cap = min(100.0 * risk_mult, swap_cap)
                                if risk_mode == "BLOCK_NEW_BUYS" or tide_state in ("T1_CLIMAX_DISTRIBUTION", "T4_PANIC_ACCEL") or effective_swap_cap <= 0.0:
                                    # 风控闸门：T1/T4、BLOCK_NEW_BUYS 或受限上限为 0 时禁止生成换入决议
                                    continue

                                # 计算除被替换老标的以外的其他保留持仓市值与权重
                                other_pos_val = sum(
                                    p.shares * (p.current_price if p.current_price > 0 else p.cost_price)
                                    for p_code, p in self._positions.items()
                                    if p_code != code and p.shares > 0
                                )
                                other_weight = (other_pos_val / self.total_capital * 100.0) if self.total_capital > 0 else 0.0
                                remaining_swap_cap = max(0.0, round(effective_swap_cap - other_weight, 4))
                                if remaining_swap_cap <= 0.0:
                                    # 保留持仓已达或超过最终上限，禁止生成换入决议
                                    continue

                                leader_buy_budget = self.total_capital * (remaining_swap_cap / 100.0)
                                leader_buy_shares = int(leader_buy_budget / top_leader.price / 100.0) * 100 if top_leader.price > 0 else 0
                                if leader_buy_shares < 100:
                                    continue

                                reason_pct_str = "100%全仓" if remaining_swap_cap >= 99.9 else f"{remaining_swap_cap:.1f}%受限"
                                directives.append(IPOOrderDirective(
                                    action="FULL_ROTATION_SWAP",
                                    code=top_leader.code,
                                    name=top_leader.name,
                                    price=top_leader.price,
                                    shares=leader_buy_shares,
                                    size_pct=round(remaining_swap_cap, 2),
                                    urgency="CRITICAL",
                                    reason=f"🔄 全仓轮动换马: 坚决清仓[{pos.name}]，腾出{reason_pct_str}资金全速接力超级领头羊[{top_leader.name}({top_leader.horse_race_score:.0f}分)]！",
                                    horse_rank=top_leader.horse_race_rank,
                                    sentiment_phase=sentiment.heat_stage,
                                    timestamp=now_ts,
                                    signal_tier="SSS",
                                    target_swap_code=code,
                                    target_swap_name=pos.name
                                ))
                                break
                            else:
                                # 普通分仓换马模式
                                directives.append(IPOOrderDirective(
                                    action="SWITCH_SWAP",
                                    code=code,
                                    name=pos.name,
                                    price=p_sig.price,
                                    shares=pos.shares,
                                    size_pct=0.0,
                                    urgency="CRITICAL",
                                    reason=f"🔄 弃弱换强·换马调仓: 持仓动能落后领头羊{p_sig.relative_to_leader_gap:.0f}分，坚决卖出，腾出资金切换全速围猎超级领头羊[{top_leader.name}({top_leader.horse_race_score:.0f}分)]！",
                                    horse_rank=p_sig.horse_race_rank,
                                    sentiment_phase=sentiment.heat_stage,
                                    timestamp=now_ts,
                                    signal_tier="S"
                                ))

            # 6. ── 【进攻端开仓：什么时候买 & 买多少买】 ──
            # 狂热高潮期：常规次新严禁新开仓防 T+1 追高被埋，但首发上市首日黄金吸筹 (IPO_FIRST_BUY) 例外允许锁定极低成本筹码！
            if sentiment.heat_stage == "🌋 狂热高潮":
                if not (top_leader and top_leader.signal_type == "IPO_FIRST_BUY"):
                    return self._publish_converged_directives(directives)
                max_fleet_weight = 40.0
                single_leader_weight = 35.0
                single_follower_weight = 0.0
            elif sentiment.heat_stage == "🔥 梯队升温":
                max_fleet_weight = 80.0
                single_leader_weight = 35.0
                single_follower_weight = 10.0
            elif sentiment.index_phase == "绝望地量" or sentiment.heat_stage == "🌱 绝望孕育":
                max_fleet_weight = 35.0
                single_leader_weight = 15.0
                single_follower_weight = 10.0
            else:
                max_fleet_weight = 50.0
                single_leader_weight = 20.0
                single_follower_weight = 10.0

            # ⚡ 若处于全仓轮动模式且当前全池无持仓，首选领头羊分配 100% 仓位
            if self.trading_mode == "ROTATION_FULL_CAPITAL":
                active_pos_count = sum(1 for p in self._positions.values() if p.shares > 0)
                if active_pos_count == 0:
                    single_leader_weight = 100.0
                    max_fleet_weight = 100.0

            # Market context is the final budget gate and cannot be bypassed by
            # strategy rank or full-capital rotation mode. Exit orders remain free.
            risk_mode = getattr(sentiment, "risk_mode", "NORMAL")
            risk_multiplier = max(0.0, min(1.0, float(
                getattr(sentiment, "position_multiplier", 1.0) or 0.0
            )))
            if risk_mode == "BLOCK_NEW_BUYS":
                risk_multiplier = 0.0
            max_fleet_weight *= risk_multiplier
            single_leader_weight *= risk_multiplier
            single_follower_weight *= risk_multiplier
            tide_state = getattr(sentiment, "tide_state", "T0_INSUFFICIENT")
            if tide_state != "T0_INSUFFICIENT":
                tide_cap = max(0.0, min(100.0, float(
                    getattr(sentiment, "tide_position_cap_pct", 100.0)
                )))
                max_fleet_weight = min(max_fleet_weight, tide_cap)
                single_leader_weight = min(single_leader_weight, tide_cap)
                single_follower_weight = min(single_follower_weight, tide_cap)

            current_total_shares_val = sum(p.shares * (p.current_price if p.current_price > 0 else p.cost_price) for p in self._positions.values() if p.shares > 0)
            current_fleet_weight = (current_total_shares_val / self.total_capital) * 100.0 if self.total_capital > 0 else 0.0
            for d in directives:
                if d.action == "FULL_ROTATION_SWAP":
                    old_val = 0.0
                    if d.target_swap_code in self._positions:
                        old_p = self._positions[d.target_swap_code]
                        old_val = old_p.shares * (old_p.current_price if old_p.current_price > 0 else old_p.cost_price)
                    old_wt = (old_val / self.total_capital * 100.0) if self.total_capital > 0 else 0.0
                    current_fleet_weight = max(0.0, current_fleet_weight - old_wt) + d.size_pct
            current_fleet_weight = round(current_fleet_weight, 4)

            # 遍历赛马排名前列标的，只重仓 Top 1~2 领头羊与优质前锋
            for rank_idx, sig in enumerate(ranked_signals):
                if sig.price <= 0:
                    continue
                code = sig.code

                if code in self._positions and self._positions[code].shares > 0:
                    continue

                if sig.is_climax_exit:
                    continue

                # T+1 实战铁律：次日及之后冲高狂飙标的，当天无法卖出，严禁追高开仓买入！
                if getattr(sig, "is_t1_forbidden_buy", False):
                    continue

                # 若不在 VWAP 之上，但具备底部扎实结构与动能拐点 (BASE_BREAKOUT / BASE_PREORDER / SWING_PREORDER / SECONDARY_BUY)，允许开仓与预埋！
                is_sec_buy_sig = (
                    sig.signal_type == "SECONDARY_BUY"
                    or getattr(sig, "channel_stage", "") in (SecondaryBuyStage.SECONDARY_BUY, "SECONDARY_BUY")
                )
                if not sig.is_above_vwap and sig.signal_type not in ("BASE_BREAKOUT", "BASE_PREORDER", "SWING_PREORDER") and not is_sec_buy_sig:
                    continue

                # “山外有山”铁律：第 4 名之后的跟风平庸股，坚决不分配仓位，杜绝资金稀释！
                # 但底部具备独立扎实结构、跨日通道突破或次级买点的标的允许开仓
                if sig.horse_race_rank > 3 and sig.signal_type not in ("BASE_BREAKOUT", "BASE_PREORDER", "SWING_PREORDER") and not is_sec_buy_sig:
                    continue

                if current_fleet_weight >= max_fleet_weight:
                    break

                if is_sec_buy_sig:
                    # ── 【SECONDARY_BUY 专属开仓闭环】 ──
                    plan = getattr(sig, "trade_plan", None)
                    # 1. 严格校验 TradePlan 存在性与有效性
                    if plan is None or not isinstance(plan, IPOTradePlan):
                        logger.info(f"[IPO-TRADING] 拒绝次级买点开仓 {code}: 缺失有效 IPOTradePlan")
                        continue

                    # 2. 严格校验信号等级必须为 S4 或 S5
                    raw_level = str(getattr(plan, "signal_level", "") or getattr(sig, "signal_level", "")).strip()
                    if "S5" in raw_level:
                        s_level = "S5"
                    elif "S4" in raw_level or "次级买点" in raw_level:
                        s_level = "S4"
                    elif "S3" in raw_level:
                        s_level = "S3"
                    elif "S2" in raw_level:
                        s_level = "S2"
                    elif "S1" in raw_level:
                        s_level = "S1"
                    elif "S0" in raw_level:
                        s_level = "S0"
                    else:
                        s_level = raw_level

                    if s_level not in ("S4", "S5"):
                        logger.info(f"[IPO-TRADING] 拒绝次级买点开仓 {code}: 信号等级 {s_level} 低于 S4 门槛")
                        continue

                    # 3. 严格校验现价不得超过买入区上沿 (buy_zone_max)
                    buy_max = plan.buy_zone_max if plan.buy_zone_max > 0 else getattr(plan, "buy_zone_upper", 0.0)
                    if buy_max > 0 and sig.price > buy_max:
                        logger.info(f"[IPO-TRADING] 拒绝次级买点开仓 {code}: 现价 {sig.price:.2f} 超过买入区上沿 {buy_max:.2f}")
                        continue

                    # 4. 刷新循环幂等守卫：同一 plan_id / signal_id 不得重复生成买入指令
                    plan_id = getattr(plan, "plan_id", "")
                    signal_id = getattr(sig, "signal_id", "") or (sig.extra_data.get("signal_id", "") if hasattr(sig, "extra_data") and isinstance(sig.extra_data, dict) else "")
                    if plan_id and plan_id in self._emitted_plan_ids:
                        logger.debug(f"[IPO-TRADING] 幂等拦截 {code}: 计划 {plan_id} 已生成过指令")
                        continue
                    if signal_id and signal_id in self._emitted_signal_ids:
                        logger.debug(f"[IPO-TRADING] 幂等拦截 {code}: 信号 {signal_id} 已生成过指令")
                        continue

                    # 5. 动作与受控仓位计算 (S4=BUY_SCOUT 试探仓; S5=BUY_CONFIRM 确认仓，不得直接满仓)
                    remaining_fleet_weight = max(0.0, round(max_fleet_weight - current_fleet_weight, 4))
                    plan_weight = float(getattr(plan, "position_pct", 30.0) or 30.0)
                    if s_level == "S4":
                        buy_action = "BUY_SCOUT"
                        max_allowed = min(plan_weight, 30.0)
                    else:  # S5
                        buy_action = "BUY_CONFIRM"
                        max_allowed = min(plan_weight, 35.0)  # 严格限制上限，不得直接满仓 (如100%)

                    assigned_weight = min(max_allowed, remaining_fleet_weight)
                    if assigned_weight <= 0:
                        logger.info(f"[IPO-TRADING] 次级买点仓位受限 {code}: 剩余可用仓位 {remaining_fleet_weight:.1f}%")
                        continue

                    allocated_money = self.total_capital * (assigned_weight / 100.0)
                    buy_shares = int(allocated_money / sig.price / 100.0) * 100
                    if buy_shares < 100:
                        continue

                    q_grade = getattr(plan, "quality_grade", "") or getattr(sig, "quality_grade", "S")
                    strat_tag = getattr(plan, "strategy_tag", "") or getattr(sig, "strategy_tag", TAG_CHANNEL_SECONDARY_BUY) or TAG_CHANNEL_SECONDARY_BUY

                    # 6. 生成指令并完整携带原始不可变 trade_plan 与规范属性
                    directive = IPOOrderDirective(
                        action=buy_action,
                        code=code,
                        name=sig.name,
                        price=sig.price,
                        shares=buy_shares,
                        size_pct=assigned_weight,
                        urgency="LIMIT" if sig.price < plan.buy_zone_min else "NORMAL",
                        reason=(
                            f"👑 次级买点确认[{s_level}·{q_grade}级]: 长期通道企稳，回踩抬高底突破，"
                            f"买入网格¥{plan.buy_zone_min:.2f}~¥{plan.buy_zone_max:.2f}，次低防守止损¥{plan.higher_low_stop:.2f}"
                        ),
                        horse_rank=sig.horse_race_rank,
                        sentiment_phase=sentiment.heat_stage,
                        timestamp=now_ts,
                        signal_tier=q_grade,
                        signal_level=s_level,
                        quality_grade=q_grade,
                        strategy_tag=strat_tag,
                        trade_plan=plan
                    )

                    if not any(d.code == code and d.action in ("BUY", "BUY_SCOUT", "BUY_CONFIRM") for d in directives):
                        directives.append(directive)
                        current_fleet_weight = round(current_fleet_weight + assigned_weight, 4)
                        if plan_id:
                            self._emitted_plan_ids.add(plan_id)
                        if signal_id:
                            self._emitted_signal_ids.add(signal_id)
                    continue

                is_valid_buy = False
                buy_reason = ""
                assigned_weight = single_follower_weight
                order_urgency = "CRITICAL"
                s_tier = "S"

                if sig.signal_type == "IPO_FIRST_BUY":
                    is_valid_buy = True
                    assigned_weight = single_leader_weight
                    buy_reason = f"🔥 首发上市黄金吸筹: 全日紧贴VWAP({sig.vwap:.2f})惜售运行，丝毫不给低位筹码，锁定极低成本进击！"
                    s_tier = "SSS"
                elif sig.signal_type == "BASE_BREAKOUT":
                    is_valid_buy = True
                    assigned_weight = single_leader_weight if sig.horse_race_rank <= 2 else single_follower_weight
                    buy_reason = f"⚡ 筑底放量共振突击: 底部平底({sig.base_support_level:.2f})放量突破加速共振，博回抽VWAP+{sig.rebound_to_vwap_space_pct:.1f}%空间，止损{sig.stop_loss_price:.2f}元！"
                    order_urgency = "CRITICAL"
                    s_tier = "S"
                elif sig.signal_type == "BASE_PREORDER":
                    is_valid_buy = True
                    assigned_weight = single_follower_weight
                    buy_reason = f"🎯 底部平底缩量企稳预埋单: 底部({sig.base_support_level:.2f})缩量横盘构筑扎实结构，动能拐头初现，提前预埋潜伏，买错跌破{sig.stop_loss_price:.2f}元立斩！"
                    order_urgency = "LIMIT"
                    s_tier = "A"
                elif sig.signal_type == "SWING_PREORDER":
                    is_valid_buy = True
                    assigned_weight = single_follower_weight
                    base_supp = getattr(sig, "multi_day_base_support", 0.0) or sig.base_support_level
                    buy_reason = f"🔭 多日大平底+60F通道突破: 4日箱体底部({base_supp:.2f})蓄势，60F突破下降通道且尾盘收最高，博周一VWAP突破，止损{sig.stop_loss_price:.2f}元！"
                    order_urgency = "LIMIT"
                    s_tier = "A"
                elif sig.horse_race_rank <= 2 and sig.launch_time_str <= "09:50" and sig.launch_slope_deg >= 30.0:
                    is_valid_buy = True
                    assigned_weight = single_leader_weight
                    buy_reason = f"🥇 赛马超级领头羊: 开盘早鸟时段({sig.launch_time_str})拔地而起，斜率{sig.launch_slope_deg}°，全池动能分最高({sig.horse_race_score})！"
                    s_tier = "SSS"
                elif sig.pullback_no_touch:
                    is_valid_buy = True
                    assigned_weight = single_follower_weight
                    buy_reason = f"🚀 回踩VWAP不破极限买点: 现价在VWAP({sig.vwap:.2f})之上浅踩拉起，极窄止损线{sig.stop_loss_price:.2f}元！"
                    order_urgency = "LIMIT"
                    s_tier = "S"

                if is_valid_buy:
                    remaining_fleet_weight = max(0.0, round(max_fleet_weight - current_fleet_weight, 4))
                    assigned_weight = min(assigned_weight, remaining_fleet_weight)
                    if assigned_weight <= 0:
                        continue

                    allocated_money = self.total_capital * (assigned_weight / 100.0)
                    buy_shares = int(allocated_money / sig.price / 100.0) * 100
                    if buy_shares >= 100:
                        # 构建不可变 TradePlan 并在指令中挂接
                        t_plan = self.create_trade_plan_from_signal(sig)
                        buy_act = t_plan.suggested_action if t_plan else "BUY_SCOUT"
                        # 避免 directives 中重复添加相同标的买单
                        if not any(d.code == code and d.action in ("BUY", "BUY_SCOUT", "BUY_CONFIRM") for d in directives):
                            directives.append(IPOOrderDirective(
                                action="BUY",
                                code=code,
                                name=sig.name,
                                price=sig.price,
                                shares=buy_shares,
                                size_pct=assigned_weight,
                                urgency=order_urgency,
                                reason=buy_reason,
                                horse_rank=sig.horse_race_rank,
                                sentiment_phase=sentiment.heat_stage,
                                timestamp=now_ts,
                                signal_tier=s_tier,
                                signal_level=t_plan.signal_level if t_plan else "S4",
                                quality_grade=t_plan.quality_grade if t_plan else "S",
                                strategy_tag=t_plan.strategy_tag if t_plan else "",
                                trade_plan=t_plan
                            ))
                            current_fleet_weight = round(current_fleet_weight + assigned_weight, 4)

            directives = self._publish_converged_directives(directives)

            # ── 无条件追加全池赛马扫描快照日志 (盘后/收盘后历史信号日志面板不空白) ──
            pre_order_cnt = sum(1 for s in all_signals if getattr(s, "signal_type", "") in (
                "PRE_ORDER", "BASE_PREORDER", "SWING_PREORDER"
            ))
            leader_name = top_leader.name if top_leader else "暂无领头羊"
            leader_score = f"{top_leader.horse_race_score:.0f}" if top_leader else "0"
            leader_code = top_leader.code if top_leader else "--"
            scan_reason = (
                f"📊 全池赛马快照 | 情绪:{sentiment.heat_stage} | "
                f"领头羊:{leader_name}({leader_score}分) | "
                f"全池:{len(all_signals)}只 | 🎯预埋:{pre_order_cnt}只 | 指令:{len(directives)}条"
            )
            scan_log_item = {
                "timestamp": now_ts,
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "action": "SCAN_SUMMARY",
                "code": leader_code,
                "name": leader_name,
                "price": top_leader.price if top_leader else 0.0,
                "shares": 0,
                "size_pct": 0.0,
                "urgency": "NORMAL",
                "reason": scan_reason,
                "horse_rank": 1,
                "sentiment_phase": sentiment.heat_stage,
                "signal_tier": "A",
                "realized_pnl_pct": 0.0,
                "realized_pnl_amount": 0.0
            }
            self._signal_iteration_log.insert(0, scan_log_item)
            if len(self._signal_iteration_log) > 300:
                self._signal_iteration_log = self._signal_iteration_log[:300]
            # 异步落盘（不阻塞决策返回）
            try:
                self._save_persisted_ledger()
            except Exception:
                pass

            return directives

    def _broadcast_directives_to_alert_notifier(self, directives: List[IPOOrderDirective]):
        """【📢 集中交易指令广播至 ATS 报警中心】"""
        if not directives:
            return
        now_ts = time.time()
        for d in directives:
            if d.action not in ("BUY", "BUY_SCOUT", "BUY_CONFIRM", "FULL_ROTATION_SWAP", "SWITCH_SWAP", "SELL"):
                continue
            d_key = f"{d.action}_{d.code}_{d.urgency}"
            last_ts = self._notified_directive_keys.get(d_key, 0.0)
            if (now_ts - last_ts) < 180.0:  # 3分钟内相同指令不重复轰炸
                continue

            self._notified_directive_keys[d_key] = now_ts

            if d.action == "FULL_ROTATION_SWAP":
                reason_text = f"【全仓轮动换马】清仓[{d.name}]，100%全仓接力超级领头羊[{d.target_swap_name}]！"
                voice_p = 99.0
            elif d.action in ("BUY", "BUY_SCOUT", "BUY_CONFIRM"):
                act_label = "次级买点试探仓" if d.action == "BUY_SCOUT" else ("次级买点确认仓" if d.action == "BUY_CONFIRM" else "集中买入")
                reason_text = f"【集中{act_label}指令】{d.action} [{d.name}] 仓位{d.size_pct:.0f}%：{d.reason}"
                voice_p = 98.0
            elif d.action == "SELL":
                reason_text = f"【集中平仓警报】卖出[{d.name}]：{d.reason}"
                voice_p = 96.0
            else:
                reason_text = f"【集中交易指令】{d.action} [{d.name}]：{d.reason}"
                voice_p = 90.0

            try:
                from ats.alert_notifier import AlertNotifier
                AlertNotifier.get_instance().notify_special_signal(
                    code=d.code,
                    name=d.name,
                    reason=reason_text,
                    score=voice_p,
                    is_force=True,
                    source="集中交易"
                )
            except Exception as ex_alert:
                logger.debug(f"广播集中交易决议异常: {ex_alert}")

    def _auto_execute_if_enabled(self):
        """若开启全自动跟随交易，自动撮合执行 (注意：FULL_ROTATION_SWAP 仅作战术建议展示，严禁自动执行)"""
        directives = self.get_pending_directives()
        if self.auto_follow_trading and directives:
            for d in directives:
                if d.action in ("FULL_ROTATION_SWAP", "SWITCH_SWAP"):
                    logger.warning(f"[IPO-TRADING] 轮动换马指令 {d.action} 仅作战术建议展示，实盘保护拦截自动执行")
                    continue
                self.record_order_execution(d)

    def execute_directive(self, directive: IPOOrderDirective) -> bool:
        """【继续交易：执行单条决议】"""
        if not directive:
            return False
        return self.record_order_execution(directive)

    def execute_all_pending_directives(self) -> int:
        """【继续交易：一键执行全部待执行指令】"""
        directives = self.get_pending_directives()
        with self._lock:
            count = 0
            for d in directives:
                if self.record_order_execution(d):
                    count += 1
            return count

    def evaluate_position_exit(
        self,
        code: str,
        price: float,
        vwap_today: float,
        volume: float,
        volume_ratio: float = 1.0,
        current_time: Optional[float] = None,
        extra_ctx: Optional[Dict[str, Any]] = None,
    ) -> Optional[IPOOrderDirective]:
        """Evaluate one holding and translate the defensive action into an order directive."""
        clean_code = str(code).strip().zfill(6)
        with self._lock:
            pos = self._positions.get(clean_code)
            if not pos or pos.shares <= 0:
                return None
            if any(
                pending.code == clean_code
                and pending.action in ("REDUCE_30", "REDUCE_HALF", "EXIT_ALL", "SELL")
                for pending in self._pending_directives
            ):
                return None
            plan = pos.trade_plan or self._trade_plans.get(clean_code)
            ctx = dict(extra_ctx or {})
            if plan is not None:
                ctx.setdefault("trade_plan", plan)
                ctx.setdefault("higher_low_stop", plan.higher_low_stop)

            # 只有交易中心持有的、新鲜的实时快照可以赋予 T10 龙头锁仓保护；
            # 调用方传入的 extra_ctx 不能自行伪造宏观豁免。
            market_ctx = self._last_market_context
            market_ctx_fresh = False
            if market_ctx is not None:
                generated_at = float(getattr(market_ctx, "generated_at", 0.0) or 0.0)
                reference_ts = float(current_time if current_time is not None else time.time())
                market_ctx_fresh = generated_at > 0 and abs(reference_ts - generated_at) <= 300.0
            report = self._reports_cache.get(clean_code)
            ctx["tide_state"] = getattr(market_ctx, "tide_state", "") if market_ctx_fresh else ""
            ctx["is_tide_leader"] = bool(
                market_ctx_fresh
                and ctx["tide_state"] == "T10_MAIN_UP"
                and pos.signal_tier == "SSS"
                and report is not None
                and (report.global_fleet_role == "LEADER" or report.horse_race_rank == 1)
            )

            watch = self.exit_engine.get_position(clean_code)
            reduce_count_before = watch.reduce_count if watch is not None else 0
            last_reduce_before = watch.last_reduce_time if watch is not None else None
            action = self.exit_engine.evaluate_tick(
                code=clean_code,
                price=price,
                vwap_today=vwap_today,
                volume=volume,
                volume_ratio=volume_ratio,
                current_time=current_time,
                extra_ctx=ctx,
            )
            if action is None:
                return None

            catastrophic_rules = {
                "exit_higher_low_broken",
                "exit_base_low_broken",
                "exit_hard_stop",
            }
            is_catastrophic = action.rule_id in catastrophic_rules
            today_str = time.strftime("%Y-%m-%d")
            if pos.entry_date == today_str and not is_catastrophic:
                if watch is not None:
                    watch.reduce_count = reduce_count_before
                    watch.last_reduce_time = last_reduce_before
                logger.warning(
                    "[IPO-TRADING] T+1 hard lock blocked %s for %s (rule=%s)",
                    action.action_type, clean_code, action.rule_id,
                )
                return None

            if action.action_type == "REDUCE_30":
                shares = int(pos.shares * 0.3 / 100) * 100
            elif action.action_type == "REDUCE_HALF":
                shares = int(pos.shares * 0.5 / 100) * 100
            else:
                shares = pos.shares
            shares = min(pos.available_shares, max(0, shares))
            if shares <= 0:
                return None

            directive = IPOOrderDirective(
                action=action.action_type,
                code=clean_code,
                name=pos.name,
                price=action.trigger_price,
                shares=shares,
                size_pct=action.size_pct * 100.0,
                urgency="CRITICAL" if is_catastrophic else "NORMAL",
                reason=action.reason,
                timestamp=action.timestamp,
                signal_tier=pos.signal_tier,
                signal_level=pos.signal_level,
                quality_grade=pos.quality_grade,
                strategy_tag=pos.strategy_tag,
                trade_plan=plan,
                exit_rule_id=action.rule_id,
                exit_rule_layer=action.layer,
                bypass_t1_lock=is_catastrophic,
            )
            if any(
                pending.code == clean_code
                and pending.action == directive.action
                and pending.exit_rule_id == directive.exit_rule_id
                for pending in self._pending_directives
            ):
                return None
            self._pending_directives.append(directive)
            return directive

    def record_order_execution(self, directive: IPOOrderDirective) -> bool:
        """
        【同步撮合成交与全生命周期复盘追踪】
        - 彻底根治“今天卖了就没下文了”的断层痛点；
        - 平仓时将持仓完整快照、收益率、平仓理由压入 _closed_positions；
        - 将每次决议与撮合事件记录进 _signal_iteration_log；
        - 原子写盘持久化到本地账本。
        """
        # The persistent singleton used by the command room must execute through
        # the TK Paper kernel first.  Ephemeral instances used by unit tests and
        # offline strategy evaluation keep their isolated in-memory behavior.
        if self._auto_load_ledger and not getattr(directive, "_kernel_routed", False):
            try:
                from ats.unified_paper_account import execute_command_directive
                kernel_result = execute_command_directive(directive)
                if not kernel_result.executed:
                    logger.warning(
                        "[IPO-TRADING] TK PAPER rejected %s %s: %s",
                        directive.action, directive.code, kernel_result.reject_code,
                    )
                    return False
                setattr(directive, "_kernel_routed", True)
                if kernel_result.volume > 0:
                    directive.shares = int(kernel_result.volume)
                if kernel_result.size_pct > 0:
                    directive.size_pct = round(kernel_result.size_pct * 100.0, 2)
            except Exception as exc:
                logger.exception("[IPO-TRADING] Unified TK PAPER routing failed: %s", exc)
                return False

        with self._lock:
            code = directive.code
            today_str = time.strftime("%Y-%m-%d")
            if directive.action == "FULL_ROTATION_SWAP":
                old_pos = self._positions.get(directive.target_swap_code)
                if old_pos is not None and old_pos.entry_date == today_str:
                    logger.warning(
                        "[IPO-TRADING] T+1 hard lock rejected rotation sell: %s",
                        directive.target_swap_code,
                    )
                    return False
            t_str = time.strftime("%H:%M:%S")
            pnl_pct = 0.0
            pnl_amt = 0.0

            sell_actions = {"SELL", "EXIT_ALL", "REDUCE_30", "REDUCE_HALF", "SWITCH_SWAP"}
            if directive.action in sell_actions:
                pos = self._positions.get(code)
                if pos is None or pos.shares <= 0:
                    logger.warning(
                        "[IPO-TRADING] Sell action rejected: no holding position for %s (%s)",
                        code, directive.action,
                    )
                    return False
                catastrophic_rules = {
                    "exit_higher_low_broken",
                    "exit_base_low_broken",
                    "exit_hard_stop",
                }
                can_bypass_t1 = (
                    getattr(directive, "bypass_t1_lock", False)
                    and directive.exit_rule_id in catastrophic_rules
                )
                if pos.entry_date == today_str and not can_bypass_t1:
                    logger.warning(
                        "[IPO-TRADING] T+1 hard lock rejected execution: %s %s",
                        directive.action, code,
                    )
                    return False

            if directive.action in ("BUY", "BUY_SCOUT", "BUY_CONFIRM"):
                if directive.price <= 0:
                    logger.warning("[IPO-TRADING] Buy action rejected: non-positive price %s", directive.price)
                    return False

                # ── 普通买入执行端最终风控闸门校验 ──
                # 1. 取得可信预算快照（无可信快照坚决拒绝扩大仓位）
                ctx = self._last_market_context
                if ctx is None and self.sentiment_engine is not None:
                    ctx = getattr(self.sentiment_engine, "_cached_snapshot", None)

                if ctx is None:
                    logger.warning("[IPO-TRADING] Buy action rejected: missing market context snapshot")
                    return False

                directive_size_pct = float(getattr(directive, "size_pct", 0.0) or 0.0)
                if directive_size_pct <= 0.0 and directive.shares > 0 and directive.price > 0 and self.total_capital > 0:
                    directive_size_pct = (directive.shares * directive.price / self.total_capital) * 100.0

                exec_ts = time.time()
                ctx_gen_ts = float(getattr(ctx, "generated_at", 0.0) or 0.0)
                ctx_tide_state = getattr(ctx, "tide_state", "T0_INSUFFICIENT")
                ctx_risk_mode = getattr(ctx, "risk_mode", "NORMAL")
                ctx_risk_mult = max(0.0, min(1.0, float(getattr(ctx, "position_multiplier", 1.0) or 0.0)))
                if ctx_risk_mode == "BLOCK_NEW_BUYS":
                    ctx_risk_mult = 0.0

                # 铁律: T1/T4 或 BLOCK_NEW_BUYS 必须坚决拒绝普通买入，且不创建幽灵持仓、不扣减现金
                if ctx_tide_state in ("T1_CLIMAX_DISTRIBUTION", "T4_PANIC_ACCEL") or ctx_risk_mode == "BLOCK_NEW_BUYS" or ctx_risk_mult <= 0.0:
                    logger.warning(
                        "[IPO-TRADING] Buy action rejected: T1/T4/BLOCK_NEW_BUYS gate active (tide=%s, risk=%s, mult=%.2f)",
                        ctx_tide_state, ctx_risk_mode, ctx_risk_mult
                    )
                    return False

                is_fresh = True
                if ctx_gen_ts <= 0 or exec_ts <= 0 or abs(exec_ts - ctx_gen_ts) > 300.0:
                    is_fresh = False
                try:
                    if datetime.datetime.fromtimestamp(ctx_gen_ts).date() != datetime.datetime.fromtimestamp(exec_ts).date():
                        is_fresh = False
                except Exception:
                    is_fresh = False

                # 指令必须携带合法时间戳且与快照在同一有效时限内（<=300s）同日关联
                dir_ts = float(getattr(directive, "timestamp", 0.0) or 0.0)
                has_directive_link = False
                if dir_ts > 0 and ctx_gen_ts > 0 and abs(dir_ts - ctx_gen_ts) <= 300.0:
                    try:
                        if datetime.datetime.fromtimestamp(dir_ts).date() == datetime.datetime.fromtimestamp(ctx_gen_ts).date():
                            has_directive_link = True
                    except Exception:
                        has_directive_link = False

                # 仅当快照新鲜、指令与快照紧密因果关联、且非T0数据不足时，才属于可信快照关联指令
                if not (is_fresh and has_directive_link and ctx_tide_state != "T0_INSUFFICIENT"):
                    logger.warning(
                        "[IPO-TRADING] Buy action rejected: untrusted snapshot (fresh=%s, link=%s, tide=%s)",
                        is_fresh, has_directive_link, ctx_tide_state
                    )
                    return False

                tide_cap_val = float(getattr(ctx, "tide_position_cap_pct", 100.0) or 100.0)
                tide_cap = max(0.0, min(100.0, tide_cap_val))
                risk_cap = max(0.0, min(100.0, 100.0 * ctx_risk_mult))
                trusted_cap = min(risk_cap, tide_cap)

                # 最终组合计算必须包含当前全部持仓（包括同代码现有持仓，追加 BUY 也不能突破潮汐上限）
                total_pos_val = sum(
                    p.shares * (p.current_price if p.current_price > 0 else p.cost_price)
                    for p in self._positions.values()
                    if p.shares > 0
                )
                current_portfolio_weight = (total_pos_val / self.total_capital * 100.0) if self.total_capital > 0 else 0.0

                remaining_cap = max(0.0, round(trusted_cap - current_portfolio_weight, 4))
                allowed_pct = min(directive_size_pct, remaining_cap)

                if allowed_pct <= 0.0:
                    logger.warning(
                        "[IPO-TRADING] Buy action rejected: allowed budget is 0.0%% (dir=%.1f%%, remaining=%.1f%%, current_holding=%.1f%%)",
                        directive_size_pct, remaining_cap, current_portfolio_weight
                    )
                    return False

                allowed_money = self.total_capital * (allowed_pct / 100.0)
                calc_shares = int(allowed_money / directive.price / 100.0) * 100
                target_shares = min(calc_shares, directive.shares) if directive.shares > 0 else calc_shares

                if target_shares < 100:
                    logger.warning(
                        "[IPO-TRADING] Buy action rejected: target shares after budget limit %d < 100",
                        target_shares
                    )
                    return False

                # 现金硬约束与最小成交手数核验 (原子性守卫：不足 100 股坚决不成交)
                max_cash_shares = int(self.available_cash / directive.price / 100.0) * 100
                exec_shares = min(target_shares, max_cash_shares)

                if exec_shares < 100:
                    logger.warning(
                        "[IPO-TRADING] Buy action rejected: executable shares %d < 100 (target=%d, max_cash_shares=%d, px=%.2f, cash=%.1f)",
                        exec_shares, target_shares, max_cash_shares, directive.price, self.available_cash
                    )
                    return False

                # ── 校验完全通过，执行状态变更 ──
                cost_money = directive.price * exec_shares
                self.available_cash = max(0.0, self.available_cash - cost_money)

                if code not in self._positions:
                    pos = IPOTradingPosition(
                        code=code,
                        name=directive.name,
                        shares=exec_shares,
                        available_shares=exec_shares,
                        cost_price=directive.price,
                        current_price=directive.price,
                        highest_price=directive.price,
                        lowest_price=directive.price,
                        entry_time=t_str,
                        entry_date=today_str,
                        entry_reason=directive.reason,
                        signal_tier=directive.signal_tier,
                        signal_level=getattr(directive, "signal_level", "S4"),
                        quality_grade=getattr(directive, "quality_grade", "S"),
                        strategy_tag=getattr(directive, "strategy_tag", ""),
                        status="HOLDING",
                        last_action=directive.action,
                        last_action_time=t_str,
                    )
                    self._positions[code] = pos
                else:
                    pos = self._positions[code]
                    new_shares = pos.shares + exec_shares
                    pos.cost_price = (pos.cost_price * pos.shares + directive.price * exec_shares) / new_shares
                    pos.shares = new_shares
                    pos.available_shares = pos.shares
                    pos.entry_time = t_str
                    pos.entry_date = today_str
                    pos.entry_reason = directive.reason
                    pos.signal_tier = directive.signal_tier
                    pos.signal_level = getattr(directive, "signal_level", "S4")
                    pos.quality_grade = getattr(directive, "quality_grade", "S")
                    pos.strategy_tag = getattr(directive, "strategy_tag", "")
                    pos.status = "HOLDING"
                    pos.current_price = directive.price
                    pos.highest_price = max(pos.highest_price, directive.price)
                    pos.lowest_price = min(pos.lowest_price, directive.price) if pos.lowest_price > 0 else directive.price
                    pos.last_action = directive.action
                    pos.last_action_time = t_str

                if directive.trade_plan is not None:
                    pos.trade_plan = directive.trade_plan
                    self.register_trade_plan(directive.trade_plan)

                watch = self.exit_engine.get_position(code)
                if watch is None:
                    watch = self.exit_engine.register_position(
                        code=code,
                        entry_price=pos.cost_price,
                        shares=pos.shares,
                        entry_time=directive.timestamp or time.time(),
                    )
                else:
                    watch.entry_price = pos.cost_price
                    watch.shares = pos.shares

                if pos.trade_plan is not None:
                    watch.is_reversal_protected = True
                    watch.higher_low_stop = max(watch.higher_low_stop, pos.trade_plan.higher_low_stop)

                directive.shares = exec_shares
                directive.size_pct = round((exec_shares * directive.price / self.total_capital * 100.0), 2) if self.total_capital > 0 else allowed_pct

                logger.info(
                    f"[IPO-TRADING] 买入成交: {pos.name}({code}) {exec_shares}股 @ {directive.price:.2f}元 "
                    f"(动作: {directive.action}, 仓位: {directive.size_pct:.1f}%) | 剩余可用: {self.available_cash:.0f}元"
                )

            elif directive.action == "FULL_ROTATION_SWAP":
                # ── 全仓轮动模式：执行端双重风控校验 ──
                # 1. 取得可信预算快照
                ctx = self._last_market_context
                if ctx is None and self.sentiment_engine is not None:
                    ctx = getattr(self.sentiment_engine, "_cached_snapshot", None)

                # 即使是手工构造指令或快照已过期，已知的 T1/T4 也绝不能
                # 降级到“按老仓位换入”；这两个状态只允许风险退出。
                known_tide_state = getattr(ctx, "tide_state", "T0_INSUFFICIENT") if ctx is not None else "T0_INSUFFICIENT"
                if known_tide_state in ("T1_CLIMAX_DISTRIBUTION", "T4_PANIC_ACCEL"):
                    logger.warning(
                        "[IPO-TRADING] FULL_ROTATION_SWAP rejected: absolute tide exit gate active (%s)",
                        known_tide_state,
                    )
                    return False

                # 老股票持仓快照与仓位权重
                old_code = directive.target_swap_code
                old_pos = self._positions.get(old_code) if old_code else None
                old_val = 0.0
                if old_pos is not None and old_pos.shares > 0:
                    old_px = old_pos.current_price if old_pos.current_price > 0 else old_pos.cost_price
                    old_val = old_px * old_pos.shares
                old_weight = (old_val / self.total_capital * 100.0) if self.total_capital > 0 else 0.0

                directive_size_pct = float(getattr(directive, "size_pct", 0.0) or 0.0)
                if directive_size_pct <= 0.0 and directive.shares > 0 and directive.price > 0 and self.total_capital > 0:
                    directive_size_pct = (directive.shares * directive.price / self.total_capital) * 100.0

                # 2. 校验快照时效性、有效性与指令关联度；
                # 若无法取得可信预算快照（缺失、陈旧、跨日、T0数据不足或指令缺少时间戳/未关联），坚决拒绝扩大仓位（严格受限于被平老仓位，绝不默认100%）
                is_trusted_snapshot = False
                trusted_cap = 0.0
                if ctx is not None:
                    exec_ts = time.time()
                    ctx_gen_ts = float(getattr(ctx, "generated_at", 0.0) or 0.0)
                    ctx_tide_state = getattr(ctx, "tide_state", "T0_INSUFFICIENT")
                    ctx_risk_mode = getattr(ctx, "risk_mode", "NORMAL")
                    ctx_risk_mult = max(0.0, min(1.0, float(getattr(ctx, "position_multiplier", 1.0) or 0.0)))
                    if ctx_risk_mode == "BLOCK_NEW_BUYS":
                        ctx_risk_mult = 0.0

                    is_fresh = True
                    if ctx_gen_ts > 0 and exec_ts > 0:
                        if abs(exec_ts - ctx_gen_ts) > 300.0:
                            is_fresh = False
                        try:
                            if datetime.datetime.fromtimestamp(ctx_gen_ts).date() != datetime.datetime.fromtimestamp(exec_ts).date():
                                is_fresh = False
                        except Exception:
                            pass

                    # 指令必须携带合法时间戳且与快照在同一有效时限内（<=300s）同日关联
                    dir_ts = float(getattr(directive, "timestamp", 0.0) or 0.0)
                    has_directive_link = False
                    if dir_ts > 0 and ctx_gen_ts > 0 and abs(dir_ts - ctx_gen_ts) <= 300.0:
                        try:
                            if datetime.datetime.fromtimestamp(dir_ts).date() == datetime.datetime.fromtimestamp(ctx_gen_ts).date():
                                has_directive_link = True
                        except Exception:
                            has_directive_link = False

                    # 仅当快照新鲜、指令与快照紧密因果关联、且非T0数据不足时，才属于可信快照关联指令
                    if is_fresh and has_directive_link and ctx_tide_state != "T0_INSUFFICIENT":
                        is_trusted_snapshot = True
                        if ctx_tide_state in ("T1_CLIMAX_DISTRIBUTION", "T4_PANIC_ACCEL"):
                            trusted_cap = 0.0
                        else:
                            tide_cap_val = float(getattr(ctx, "tide_position_cap_pct", 100.0) or 100.0)
                            trusted_cap = max(0.0, min(100.0, tide_cap_val))
                        trusted_cap *= ctx_risk_mult

                # 计算除被平老仓以外的其他保留持仓市值与权重
                other_pos_val = sum(
                    p.shares * (p.current_price if p.current_price > 0 else p.cost_price)
                    for p_code, p in self._positions.items()
                    if p_code != old_code and p.shares > 0
                )
                other_weight = (other_pos_val / self.total_capital * 100.0) if self.total_capital > 0 else 0.0

                if is_trusted_snapshot:
                    remaining_cap = max(0.0, round(trusted_cap - other_weight, 4))
                    allowed_pct = min(directive_size_pct, remaining_cap)
                else:
                    # 快照缺失、陈旧、跨日或T0不足：执行端防穿透降级，拒绝扩大仓位
                    allowed_pct = min(directive_size_pct, old_weight)

                if allowed_pct <= 0.0 or directive.price <= 0:
                    logger.warning(
                        "[IPO-TRADING] FULL_ROTATION_SWAP rejected: allowed budget is 0.0%% (dir=%.1f%%, old=%.1f%%, other=%.1f%%)",
                        directive_size_pct, old_weight, other_weight
                    )
                    return False

                # 3. 计算受限买入预算与目标股数
                allowed_money = self.total_capital * (allowed_pct / 100.0)
                calc_shares = int(allowed_money / directive.price / 100.0) * 100
                target_shares = min(calc_shares, directive.shares) if directive.shares > 0 else calc_shares

                # 4. 原子性守卫：在变动旧持仓、现金、closed_positions或日志前，必须先验证目标买入预算与预期可用现金均可成交至少 100 股
                anticipated_cash = self.available_cash + (old_val if (old_pos is not None and old_pos.shares > 0) else 0.0)
                max_cash_shares = int(anticipated_cash / directive.price / 100.0) * 100
                new_shares = min(target_shares, max_cash_shares)

                if new_shares < 100:
                    logger.warning(
                        "[IPO-TRADING] FULL_ROTATION_SWAP rejected: executable shares %d < 100 (budget_shares=%d, cash_shares=%d, px=%.2f)",
                        new_shares, target_shares, max_cash_shares, directive.price
                    )
                    return False

                # 5. 校验完全通过，执行原子换马第 1 步：平仓老股票回笼资金
                if old_pos is not None and old_pos.shares > 0:
                    sell_px = old_pos.current_price if old_pos.current_price > 0 else old_pos.cost_price
                    sell_val = sell_px * old_pos.shares
                    self.available_cash += sell_val
                    pnl_amt = (sell_px - old_pos.cost_price) * old_pos.shares if old_pos.cost_price > 0 else 0.0
                    pnl_pct = round((sell_px - old_pos.cost_price) / old_pos.cost_price * 100.0, 2) if old_pos.cost_price > 0 else 0.0
                    old_pos.exit_price = sell_px
                    old_pos.exit_time = t_str
                    old_pos.exit_date = today_str
                    old_pos.realized_pnl_pct = pnl_pct
                    old_pos.realized_pnl_amount = round(pnl_amt, 2)
                    old_pos.exit_reason = f"全仓轮动换马接力新龙头 [{directive.name}({code})]"
                    old_pos.status = "CLOSED"
                    self._closed_positions.insert(0, copy.deepcopy(old_pos))
                    if len(self._closed_positions) > 200:
                        self._closed_positions = self._closed_positions[:200]
                    old_pos.shares = 0
                    old_pos.available_shares = 0
                    del self._positions[old_code]
                    self.exit_engine.unregister_position(old_code)
                    logger.info(f"[IPO-TRADING] 全仓轮动平出老标的: {old_pos.name}({old_code}) 回笼资金: {sell_val:.0f}元 | 盈亏: {pnl_pct:+.2f}%")

                # 6. 执行原子换马第 2 步：按受限预算买入新龙头（绝不直接使用全部 available_cash）
                cost_money = directive.price * new_shares
                self.available_cash = max(0.0, self.available_cash - cost_money)

                new_pos = IPOTradingPosition(
                    code=code, name=directive.name, shares=new_shares, available_shares=new_shares,
                    cost_price=directive.price, current_price=directive.price, highest_price=directive.price,
                    lowest_price=directive.price, entry_time=t_str, entry_date=today_str,
                    entry_reason=directive.reason, signal_tier=directive.signal_tier, status="HOLDING",
                    last_action="FULL_ROTATION_SWAP", last_action_time=t_str
                )
                self._positions[code] = new_pos
                directive.shares = new_shares
                directive.size_pct = round((new_shares * directive.price / self.total_capital * 100.0), 2) if self.total_capital > 0 else allowed_pct
                logger.info(
                    f"[IPO-TRADING] 全仓轮动接力新龙头成功: {new_pos.name}({code}) "
                    f"按受限仓位({allowed_pct:.1f}%)买入 {new_shares}股 @ {directive.price:.2f}元 (成本: {cost_money:.0f}元, 剩余现金: {self.available_cash:.0f}元)"
                )

            elif directive.action in ("SELL", "EXIT_ALL", "REDUCE_30", "REDUCE_HALF", "SWITCH_SWAP"):
                is_partial = directive.action in ("REDUCE_30", "REDUCE_HALF")
                sell_shares = min(pos.available_shares, directive.shares if is_partial else pos.shares)
                if sell_shares <= 0:
                    return False
                sell_val = directive.price * sell_shares
                self.available_cash += sell_val
                if pos.cost_price > 0:
                    pnl_amt = (directive.price - pos.cost_price) * sell_shares
                    pnl_pct = round((directive.price - pos.cost_price) / pos.cost_price * 100.0, 2)

                pos.exit_price = directive.price
                pos.exit_time = t_str
                pos.exit_date = today_str
                pos.realized_pnl_pct = pnl_pct
                pos.realized_pnl_amount = round(pnl_amt, 2)
                pos.exit_reason = directive.reason
                pos.exit_rule_id = directive.exit_rule_id
                pos.exit_rule_layer = directive.exit_rule_layer
                pos.last_action = directive.action
                pos.last_action_time = t_str
                pre_sell_snapshot = copy.deepcopy(pos)
                pos.shares -= sell_shares
                pos.available_shares = min(pos.available_shares - sell_shares, pos.shares)
                watch = self.exit_engine.get_position(code)
                if watch is not None:
                    watch.shares = pos.shares

                if pos.shares == 0:
                    pos.status = "CLOSED"
                    closed_snapshot = pre_sell_snapshot
                    closed_snapshot.exit_price = directive.price
                    closed_snapshot.exit_time = t_str
                    closed_snapshot.exit_date = today_str
                    closed_snapshot.realized_pnl_pct = pnl_pct
                    closed_snapshot.realized_pnl_amount = round(pnl_amt, 2)
                    closed_snapshot.exit_reason = directive.reason
                    closed_snapshot.exit_rule_id = directive.exit_rule_id
                    closed_snapshot.exit_rule_layer = directive.exit_rule_layer
                    closed_snapshot.last_action = directive.action
                    closed_snapshot.last_action_time = t_str
                    closed_snapshot.status = "CLOSED"
                    self._closed_positions.insert(0, closed_snapshot)
                    if len(self._closed_positions) > 200:
                        self._closed_positions = self._closed_positions[:200]
                    self.exit_engine.unregister_position(code)
                else:
                    pos.status = "HOLDING"

                logger.info(f"[IPO-TRADING] 卖出成交: {pos.name}({code}) {sell_shares}股 @ {directive.price:.2f}元 | 剩余: {pos.shares}股 | 盈亏: {pnl_pct:+.2f}% ({pnl_amt:+.0f}元)")

            self._order_history.append(directive)

            # 撮合执行后从待执行指令清单中移除匹配项
            self._pending_directives = [
                d for d in self._pending_directives
                if not (d.code == directive.code and d.action == directive.action)
            ]

            # 写入信号与决议迭代日志 (供操盘手点击详情回溯)
            log_item = {
                "timestamp": directive.timestamp or time.time(),
                "time_str": f"{today_str} {t_str}",
                "action": directive.action,
                "code": directive.code,
                "name": directive.name,
                "price": directive.price,
                "shares": directive.shares,
                "size_pct": directive.size_pct,
                "urgency": directive.urgency,
                "reason": directive.reason,
                "horse_rank": directive.horse_rank,
                "sentiment_phase": directive.sentiment_phase,
                "signal_tier": directive.signal_tier,
                "realized_pnl_pct": pnl_pct if directive.action not in ("BUY", "BUY_SCOUT", "BUY_CONFIRM") else 0.0,
                "realized_pnl_amount": round(pnl_amt, 2) if directive.action not in ("BUY", "BUY_SCOUT", "BUY_CONFIRM") else 0.0
            }
            self._signal_iteration_log.insert(0, log_item)
            if len(self._signal_iteration_log) > 300:
                self._signal_iteration_log = self._signal_iteration_log[:300]

            # 立即物理原子写盘落盘
            self._save_persisted_ledger()
            return True

    def _append_signal_iteration_log(
        self, action: str, code: str, name: str, price: float,
        size_pct: float, reason: str, signal_tier: str = "S"
    ) -> None:
        """追加一条信号产生与迭代日志记录并原子持久化"""
        with self._lock:
            today_str = time.strftime("%Y-%m-%d")
            t_str = time.strftime("%H:%M:%S")
            item = {
                "timestamp": time.time(),
                "time_str": f"{today_str} {t_str}",
                "action": action,
                "code": code,
                "name": name,
                "price": price,
                "shares": 0,
                "size_pct": size_pct,
                "urgency": "NORMAL",
                "reason": reason,
                "horse_rank": 1,
                "sentiment_phase": "活跃",
                "signal_tier": signal_tier,
                "realized_pnl_pct": 0.0,
                "realized_pnl_amount": 0.0
            }
            self._signal_iteration_log.insert(0, item)
            if len(self._signal_iteration_log) > 300:
                self._signal_iteration_log = self._signal_iteration_log[:300]
            self._save_persisted_ledger()

    def get_fleet_summary(self) -> Dict[str, Any]:
        """获取整个舰队统一交易与持仓概览快照 (供 UI 实时展示)"""
        self._sync_from_unified_paper_account()
        with self._lock:
            holding_list = [p for p in self._positions.values() if p.shares > 0]
            tot_val = sum(p.shares * p.current_price for p in holding_list)
            weight = round((tot_val / self.total_capital) * 100.0, 1) if self.total_capital > 0 else 0.0
            top_leader_sig = self._ranked_cache[0] if self._ranked_cache else None

            # 计算累计已实现盈亏总额
            total_realized_pnl = sum(
                (p.get("realized_pnl_amount", 0.0) if isinstance(p, dict) else getattr(p, "realized_pnl_amount", 0.0))
                for p in self._closed_positions
            )

            return {
                "total_capital": self.total_capital,
                "available_cash": round(self.available_cash, 2),
                "holding_count": len(holding_list),
                "closed_count": len(self._closed_positions),
                "total_holding_value": round(tot_val, 2),
                "total_realized_pnl": round(total_realized_pnl, 2),
                "fleet_weight_pct": weight,
                "trading_mode": self.trading_mode,
                "auto_follow_trading": self.auto_follow_trading,
                "pending_directive_count": len(self._pending_directives),
                "top_leader": top_leader_sig.code if top_leader_sig else "--",
                "top_leader_name": top_leader_sig.name if top_leader_sig else "--",
                "top_leader_score": top_leader_sig.horse_race_score if top_leader_sig else 0.0,
                "tide_state": getattr(self._last_market_context, "tide_state", "T0_INSUFFICIENT"),
                "tide_confidence": getattr(self._last_market_context, "tide_confidence", 0.0),
                "tide_position_cap_pct": getattr(self._last_market_context, "tide_position_cap_pct", 0.0),
                "tide_action": getattr(self._last_market_context, "tide_action", "WAIT"),
                "tide_transition_reasons": list(getattr(
                    self._last_market_context, "tide_transition_reasons", []
                )),
                "tide_revision_count": getattr(self._last_market_context, "tide_revision_count", 0),
                "holding_details": [
                    {
                        "code": p.code,
                        "name": p.name,
                        "shares": p.shares,
                        "cost": p.cost_price,
                        "now": p.current_price,
                        "pnl_pct": p.unrealized_pnl_pct,
                        "status": p.status,
                        "entry_date": p.entry_date,
                        "entry_time": p.entry_time,
                        "entry_reason": p.entry_reason,
                        "signal_tier": p.signal_tier
                    } for p in holding_list
                ],
                "closed_details": [
                    {
                        "code": p.get("code", "") if isinstance(p, dict) else p.code,
                        "name": p.get("name", "") if isinstance(p, dict) else p.name,
                        "shares": p.get("shares", 0) if isinstance(p, dict) else p.shares,
                        "cost": p.get("cost_price", 0.0) if isinstance(p, dict) else p.cost_price,
                        "exit_price": p.get("exit_price", 0.0) if isinstance(p, dict) else p.exit_price,
                        "pnl_pct": p.get("realized_pnl_pct", 0.0) if isinstance(p, dict) else p.realized_pnl_pct,
                        "pnl_amt": p.get("realized_pnl_amount", 0.0) if isinstance(p, dict) else p.realized_pnl_amount,
                        "status": p.get("status", "CLOSED") if isinstance(p, dict) else p.status,
                        "entry_date": p.get("entry_date", "") if isinstance(p, dict) else p.entry_date,
                        "exit_date": p.get("exit_date", "") if isinstance(p, dict) else p.exit_date,
                        "exit_time": p.get("exit_time", "") if isinstance(p, dict) else p.exit_time,
                        "exit_reason": p.get("exit_reason", "") if isinstance(p, dict) else p.exit_reason,
                        "signal_tier": p.get("signal_tier", "S") if isinstance(p, dict) else p.signal_tier
                    } for p in self._closed_positions
                ],
                "signal_iteration_log": list(self._signal_iteration_log),
                "paper_reconciliation": dict(getattr(self, "_paper_reconciliation", {})),
            }
