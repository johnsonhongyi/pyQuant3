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
3. 【何时卖、买错就出局的终极闭环】：
   - 铁律 1 (买错立斩)：跌破 VWAP 超过 0.6%~1.0%，立即清仓止损；
   - 铁律 2 (高潮天量平仓)：偏离 VWAP 达极限且放天量滞涨，坚决止盈保利；
   - 铁律 3 (全局领头羊崩盘联动)：全池领头羊高位跳水时，全舰队联动收缩防守。
4. 【持续跟随市场切换的跟随交易 (换马调仓)】：
   - 持仓走平滞涨、池中冒出超级领头羊时，果断弃弱留强、切换跟随。
"""

import os
import sys
import time
import math
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

from ats.strategy.ipo_market_sentiment_engine import IPOMarketSentimentEngine, MarketSentimentSnapshot
from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal, batch_evaluate_horse_race_ranking

logger = logging.getLogger("IPOTradingCenter")


@dataclass
class IPOTradingPosition:
    """新股次新统一持仓状态容器"""
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


@dataclass
class IPOOrderDirective:
    """交易中心向执行端分发的标准订单指令"""
    action: str                       # "BUY" | "SELL" | "HOLD" | "SWITCH_SWAP"
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


class IPOTradingCenter:
    """新股次新股统一集中交易仲裁与调度中心单例"""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, total_capital: float = 1000000.0):
        self.total_capital = total_capital       # 虚拟/实盘总资金池 (默认 100 万基准)
        self.available_cash = total_capital
        self._positions: Dict[str, IPOTradingPosition] = {}
        self._reports_cache: Dict[str, VWAPDetectorSignal] = {}
        self._ranked_cache: List[VWAPDetectorSignal] = []
        self._order_history: List[IPOOrderDirective] = []
        self._lock = threading.RLock()
        
        self.sentiment_engine = IPOMarketSentimentEngine.get_instance()
        self._last_fleet_eval_ts: float = 0.0
        self._max_total_position_pct: float = 80.0 # 最大允许总仓位
        self.auto_follow_trading: bool = False     # 全自动跟随交易开关 (开启后自动撮合指令)
        self._pending_directives: List[IPOOrderDirective] = []

    def set_auto_follow_trading(self, enabled: bool) -> None:
        """开启/关闭全自动跟随交易"""
        with self._lock:
            self.auto_follow_trading = bool(enabled)
            logger.info(f"[IPO-TRADING] 全自动跟随交易状态变更: {self.auto_follow_trading}")

    def get_pending_directives(self) -> List[IPOOrderDirective]:
        """获取当前待执行的最新交易指令"""
        with self._lock:
            return list(self._pending_directives)

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
        with self._lock:
            all_signals = list(self._reports_cache.values())
            if not all_signals:
                self._pending_directives = []
                return []

            now_ts = time.time()
            today_str = time.strftime("%Y-%m-%d")
            directives: List[IPOOrderDirective] = []

            # 1. 全局大盘量能与新股梯队情绪感知
            sentiment = self.sentiment_engine.get_market_sentiment(all_signals)

            # 2. 全池执行横向赛马冒泡排位 (“山外有山”)
            ranked_signals = batch_evaluate_horse_race_ranking(all_signals)
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

                # 仲裁 A: 极端高潮冲顶天量滞涨
                if sig.is_climax_exit:
                    sig.global_fleet_role = "CLIMAX_EXIT"
                    sig.global_arbitration_desc = f"🚨【高潮平仓 0%仓】偏离VWAP达+{sig.vwap_diff_pct:.1f}%且放天量滞涨冲顶，主力疯狂兑现，锁定翻倍胜果！"
                    continue

                # 仲裁 B: 买错立斩出局 (跌破 VWAP 超过 0.6%)
                if not sig.is_above_vwap and sig.vwap_diff_pct < -0.6:
                    sig.global_fleet_role = "STOP_LOSS"
                    sig.global_arbitration_desc = f"⛔【买错立斩 0%仓】跌破VWAP({sig.vwap:.2f})达{sig.vwap_diff_pct:.1f}%，全池一票否决，买错坚决出局斩仓！"
                    continue

                # 仲裁 C: 市场冰点泥沙俱下 (全池规避)
                if sentiment.heat_stage == "❄️ 冰点极寒" or sentiment.vwap_hold_ratio < 20.0:
                    sig.global_fleet_role = "ICE_ABORT"
                    sig.global_arbitration_desc = f"❄️【全局冰点 0%仓】次新池站稳率仅{sentiment.vwap_hold_ratio}%，山外无山皆泥沙，全局防守禁止开仓！"
                    continue

                # 仲裁 D: 领头羊崩溃全局避险
                if leader_is_crashing and sig.code != leader_code:
                    sig.global_fleet_role = "PANIC_DEFENSE"
                    sig.global_arbitration_desc = f"🛡️【全局避险 0%仓】超级领头羊({leader_code})天量冲顶跳水，板块退潮泥沙俱下，严禁逆市伸手！"
                    continue

                # 仲裁 E: 🥇 爆款领头羊 (全池第 1 标杆，优先确立地位)
                if top_leader and sig.code == top_leader.code:
                    sig.global_fleet_role = "LEADER"
                    if sig.signal_type == "IPO_FIRST_BUY":
                        sig.global_arbitration_desc = f"🔥【首发吸筹 35%仓】首发上市紧贴VWAP({sig.vwap:.2f})惜售，全池唯一首发标杆，锁定极低成本重仓进击！"
                    elif sentiment.heat_stage == "🌋 狂热高潮":
                        sig.global_arbitration_desc = f"🥇【高潮领头羊 10%仓】全市场情绪狂热高潮，领头羊轻仓快进快出，严防T+1次日踩踏！"
                    else:
                        sig.global_arbitration_desc = f"🥇【全池领头羊 35%仓】动能分{sig.horse_race_score:.0f}全池第一，{sig.launch_time_str}拔地而起，集中重仓围猎！"
                    continue

                # 仲裁 F: 市场狂热高潮期对后排与跟风只卖不买，防T+1追高被埋
                if sentiment.heat_stage == "🌋 狂热高潮":
                    sig.global_fleet_role = "CLIMAX_DEFENSE"
                    sig.global_arbitration_desc = f"🌋【高潮避险 0%仓】全市场情绪极度狂热，跟风标的只卖不买，防T+1追高被埋纸面财富！"
                    continue

                # 仲裁 G: 🥈 梯队前锋
                if sig.horse_race_rank in (2, 3) and sig.horse_race_score >= 70.0 and sig.is_above_vwap:
                    sig.global_fleet_role = "VANGUARD"
                    leader_nm = top_leader.name if top_leader else "领头羊"
                    sig.global_arbitration_desc = f"🥈【梯队前锋 15%仓】动能分{sig.horse_race_score:.0f}，紧随领头羊[{leader_nm}]多头共振，顺风跟进！"
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
                if not sig or sig.price <= 0:
                    continue

                # 4.1 铁律 1: 买错立斩出局 (跌破 VWAP 超过 0.6%)
                if not sig.is_above_vwap and sig.vwap_diff_pct < -0.6:
                    directives.append(IPOOrderDirective(
                        action="SELL",
                        code=code,
                        name=pos.name,
                        price=sig.price,
                        shares=pos.shares,
                        size_pct=0.0,
                        urgency="CRITICAL",
                        reason=f"⛔ 破位止损出局: 跌破VWAP({sig.vwap:.2f})达{sig.vwap_diff_pct:.1f}%，买错坚决出局斩仓，严禁死扛！",
                        horse_rank=sig.horse_race_rank,
                        sentiment_phase=sentiment.heat_stage,
                        timestamp=now_ts
                    ))
                    continue

                # 4.2 铁律 2: 极端高潮天量平仓
                if sig.is_climax_exit:
                    directives.append(IPOOrderDirective(
                        action="SELL",
                        code=code,
                        name=pos.name,
                        price=sig.price,
                        shares=pos.shares,
                        size_pct=0.0,
                        urgency="CRITICAL",
                        reason=f"🚨 极端高潮平仓: 现价偏离VWAP达+{sig.vwap_diff_pct:.1f}%且放天量冲顶滞涨，主力疯狂兑现，保住翻倍胜果！",
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

            # 5. ── 【调仓换马：弃弱留强 (SWITCH_SWAP)】 ──
            # 持续跟随市场切换：持仓股动能滞涨落后，全池涌现出更强的 Rank 1 领头羊时果断换马
            if top_leader and top_leader.code not in self._positions:
                for code, pos in list(self._positions.items()):
                    if pos.shares <= 0 or code == top_leader.code:
                        continue
                    p_sig = self._reports_cache.get(code)
                    if p_sig and (p_sig.relative_to_leader_gap >= 20.0 or p_sig.horse_race_rank > 2):
                        # 检查新领头羊是否具备进击买点
                        if top_leader.signal_type in ("IPO_FIRST_BUY", "PULLBACK_BUY", "BREAKOUT") or (top_leader.launch_time_str <= "09:50" and top_leader.launch_slope_deg >= 30.0):
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
                                timestamp=now_ts
                            ))

            # 6. ── 【进攻端开仓：什么时候买 & 买多少买】 ──
            # 狂热高潮期：常规次新严禁新开仓防 T+1 追高被埋，但首发上市首日黄金吸筹 (IPO_FIRST_BUY) 例外允许锁定极低成本筹码！
            if sentiment.heat_stage == "🌋 狂热高潮":
                if not (top_leader and top_leader.signal_type == "IPO_FIRST_BUY"):
                    self._pending_directives = directives
                    self._auto_execute_if_enabled(directives)
                    return directives
                max_fleet_weight = 40.0
                single_leader_weight = 35.0
                single_follower_weight = 0.0
            elif sentiment.heat_stage == "🔥 梯队升温":
                max_fleet_weight = 80.0
                single_leader_weight = 35.0
                single_follower_weight = 15.0
            elif sentiment.index_phase == "绝望地量" or sentiment.heat_stage == "🌱 绝望孕育":
                max_fleet_weight = 35.0
                single_leader_weight = 15.0
                single_follower_weight = 10.0
            else:
                max_fleet_weight = 50.0
                single_leader_weight = 20.0
                single_follower_weight = 10.0


            current_total_shares_val = sum(p.shares * p.current_price for p in self._positions.values() if p.shares > 0)
            current_fleet_weight = (current_total_shares_val / self.total_capital) * 100.0 if self.total_capital > 0 else 0.0

            # 遍历赛马排名前列标的，只重仓 Top 1~2 领头羊与优质前锋
            for rank_idx, sig in enumerate(ranked_signals):
                if sig.price <= 0:
                    continue
                code = sig.code

                if code in self._positions and self._positions[code].shares > 0:
                    continue

                if not sig.is_above_vwap or sig.is_climax_exit:
                    continue

                # “山外有山”铁律：第 4 名之后的跟风平庸股，坚决不分配仓位，杜绝资金稀释！
                if sig.horse_race_rank > 3:
                    continue

                if current_fleet_weight >= max_fleet_weight:
                    break

                is_valid_buy = False
                buy_reason = ""
                assigned_weight = single_follower_weight

                if sig.signal_type == "IPO_FIRST_BUY":
                    is_valid_buy = True
                    assigned_weight = single_leader_weight
                    buy_reason = f"🔥 首发上市黄金吸筹: 全日紧贴VWAP({sig.vwap:.2f})惜售运行，丝毫不给低位筹码，锁定极低成本进击！"
                elif sig.horse_race_rank <= 2 and sig.launch_time_str <= "09:50" and sig.launch_slope_deg >= 30.0:
                    is_valid_buy = True
                    assigned_weight = single_leader_weight
                    buy_reason = f"🥇 赛马超级领头羊: 开盘早鸟时段({sig.launch_time_str})拔地而起，斜率{sig.launch_slope_deg}°，全池动能分最高({sig.horse_race_score})！"
                elif sig.pullback_no_touch:
                    is_valid_buy = True
                    assigned_weight = single_follower_weight
                    buy_reason = f"🚀 回踩VWAP不破极限买点: 现价在VWAP({sig.vwap:.2f})之上浅踩拉起，极窄止损线{sig.stop_loss_price:.2f}元！"

                if is_valid_buy:
                    allocated_money = self.total_capital * (assigned_weight / 100.0)
                    buy_shares = int(allocated_money / sig.price / 100.0) * 100
                    if buy_shares >= 100:
                        directives.append(IPOOrderDirective(
                            action="BUY",
                            code=code,
                            name=sig.name,
                            price=sig.price,
                            shares=buy_shares,
                            size_pct=assigned_weight,
                            urgency="LIMIT" if sig.pullback_no_touch else "CRITICAL",
                            reason=buy_reason,
                            horse_rank=sig.horse_race_rank,
                            sentiment_phase=sentiment.heat_stage,
                            timestamp=now_ts
                        ))
                        current_fleet_weight += assigned_weight

            self._pending_directives = directives
            self._auto_execute_if_enabled(directives)
            return directives

    def _auto_execute_if_enabled(self, directives: List[IPOOrderDirective]):
        """若开启全自动跟随交易，自动撮合执行"""
        if self.auto_follow_trading and directives:
            for d in directives:
                self.record_order_execution(d)

    def execute_directive(self, directive: IPOOrderDirective) -> bool:
        """【继续交易：执行单条决议】"""
        if not directive:
            return False
        self.record_order_execution(directive)
        return True

    def execute_all_pending_directives(self) -> int:
        """【继续交易：一键执行全部待执行指令】"""
        with self._lock:
            count = len(self._pending_directives)
            for d in list(self._pending_directives):
                self.record_order_execution(d)
            self._pending_directives.clear()
            return count

    def record_order_execution(self, directive: IPOOrderDirective) -> None:
        """同步订单撮合成交状态并更新资金账户与持仓"""
        with self._lock:
            code = directive.code
            if code not in self._positions:
                self._positions[code] = IPOTradingPosition(code=code, name=directive.name)
            pos = self._positions[code]
            t_str = time.strftime("%H:%M:%S")
            today_str = time.strftime("%Y-%m-%d")

            if directive.action == "BUY":
                cost_money = directive.price * directive.shares
                self.available_cash = max(0.0, self.available_cash - cost_money)
                new_shares = pos.shares + directive.shares
                if new_shares > 0:
                    pos.cost_price = (pos.cost_price * pos.shares + directive.price * directive.shares) / new_shares
                    pos.shares = new_shares
                    pos.available_shares = pos.shares
                pos.entry_time = t_str
                pos.entry_date = today_str
                pos.status = "HOLDING"
                pos.current_price = directive.price
                pos.highest_price = directive.price
                pos.lowest_price = directive.price
                pos.last_action = "BUY"
                pos.last_action_time = t_str
                logger.info(f"[IPO-TRADING] 买入成交: {pos.name}({code}) {directive.shares}股 @ {directive.price:.2f}元 | 剩余可用: {self.available_cash:.0f}元")

            elif directive.action in ("SELL", "SWITCH_SWAP"):
                sell_val = directive.price * pos.shares
                self.available_cash += sell_val
                logger.info(f"[IPO-TRADING] 卖出平仓: {pos.name}({code}) {pos.shares}股 @ {directive.price:.2f}元 | 浮动盈亏: {pos.unrealized_pnl_pct}% | 回笼资金: {sell_val:.0f}元")
                pos.shares = 0
                pos.available_shares = 0
                pos.status = "CLOSED"
                pos.last_action = directive.action
                pos.last_action_time = t_str

            self._order_history.append(directive)

    def get_fleet_summary(self) -> Dict[str, Any]:
        """获取整个舰队统一交易与持仓概览快照 (供 UI 实时展示)"""
        with self._lock:
            holding_list = [p for p in self._positions.values() if p.shares > 0]
            tot_val = sum(p.shares * p.current_price for p in holding_list)
            weight = round((tot_val / self.total_capital) * 100.0, 1) if self.total_capital > 0 else 0.0
            top_leader_sig = self._ranked_cache[0] if self._ranked_cache else None
            return {
                "total_capital": self.total_capital,
                "available_cash": round(self.available_cash, 2),
                "holding_count": len(holding_list),
                "total_holding_value": round(tot_val, 2),
                "fleet_weight_pct": weight,
                "auto_follow_trading": self.auto_follow_trading,
                "pending_directive_count": len(self._pending_directives),
                "top_leader": top_leader_sig.code if top_leader_sig else "--",
                "top_leader_name": top_leader_sig.name if top_leader_sig else "--",
                "top_leader_score": top_leader_sig.horse_race_score if top_leader_sig else 0.0,
                "holding_details": [
                    {
                        "code": p.code,
                        "name": p.name,
                        "shares": p.shares,
                        "cost": p.cost_price,
                        "now": p.current_price,
                        "pnl_pct": p.unrealized_pnl_pct,
                        "status": p.status
                    } for p in holding_list
                ]
            }

