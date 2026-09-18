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

            # 1. 全局大盘量能与新股梯队情绪感知 (依据最新汇交的全景信号实时感知)
            sentiment = self.sentiment_engine.get_market_sentiment(all_signals, force_refresh=True)

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

                # 仲裁 F: 龙头高潮冲顶崩盘联动避险 (仅对第 4 名之后的跟风高位标的退潮拦截，但低位独立筑底/共振/通道突破标的除外！)
                if leader_is_crashing and sig.code != leader_code:
                    if sig.signal_type in ("BASE_PREORDER", "BASE_BREAKOUT", "SWING_PREORDER") or sig.has_bottom_base:
                        pass  # 底部独立结构标的不被龙头冲顶误杀
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

                if sig.is_climax_exit:
                    continue

                # T+1 实战铁律：次日及之后冲高狂飙标的，当天无法卖出，严禁追高开仓买入！
                if getattr(sig, "is_t1_forbidden_buy", False):
                    continue

                # 若不在 VWAP 之上，但具备底部扎实结构与动能拐点 (BASE_BREAKOUT / BASE_PREORDER / SWING_PREORDER)，允许开仓与预埋！
                if not sig.is_above_vwap and sig.signal_type not in ("BASE_BREAKOUT", "BASE_PREORDER", "SWING_PREORDER"):
                    continue

                # “山外有山”铁律：第 4 名之后的跟风平庸股，坚决不分配仓位，杜绝资金稀释！
                # 但底部具备独立扎实结构或跨日通道突破的标的如果跻身前列，允许开仓
                if sig.horse_race_rank > 3 and sig.signal_type not in ("BASE_BREAKOUT", "BASE_PREORDER", "SWING_PREORDER"):
                    continue

                if current_fleet_weight >= max_fleet_weight:
                    break

                is_valid_buy = False
                buy_reason = ""
                assigned_weight = single_follower_weight
                order_urgency = "CRITICAL"

                if sig.signal_type == "IPO_FIRST_BUY":
                    is_valid_buy = True
                    assigned_weight = single_leader_weight
                    buy_reason = f"🔥 首发上市黄金吸筹: 全日紧贴VWAP({sig.vwap:.2f})惜售运行，丝毫不给低位筹码，锁定极低成本进击！"
                elif sig.signal_type == "BASE_BREAKOUT":
                    is_valid_buy = True
                    assigned_weight = single_leader_weight if sig.horse_race_rank <= 2 else single_follower_weight
                    buy_reason = f"⚡ 筑底放量共振突击: 底部平底({sig.base_support_level:.2f})放量突破加速共振，博回抽VWAP+{sig.rebound_to_vwap_space_pct:.1f}%空间，止损{sig.stop_loss_price:.2f}元！"
                    order_urgency = "CRITICAL"
                elif sig.signal_type == "BASE_PREORDER":
                    is_valid_buy = True
                    assigned_weight = single_follower_weight
                    buy_reason = f"🎯 底部平底缩量企稳预埋单: 底部({sig.base_support_level:.2f})缩量横盘构筑扎实结构，动能拐头初现，提前预埋潜伏，买错跌破{sig.stop_loss_price:.2f}元立斩！"
                    order_urgency = "LIMIT"
                elif sig.signal_type == "SWING_PREORDER":
                    is_valid_buy = True
                    assigned_weight = single_follower_weight
                    base_supp = getattr(sig, "multi_day_base_support", 0.0) or sig.base_support_level
                    buy_reason = f"🔭 多日大平底+60F通道突破: 4日箱体底部({base_supp:.2f})蓄势，60F突破下降通道且尾盘收最高，博周一VWAP突破，止损{sig.stop_loss_price:.2f}元！"
                    order_urgency = "LIMIT"
                elif sig.horse_race_rank <= 2 and sig.launch_time_str <= "09:50" and sig.launch_slope_deg >= 30.0:
                    is_valid_buy = True
                    assigned_weight = single_leader_weight
                    buy_reason = f"🥇 赛马超级领头羊: 开盘早鸟时段({sig.launch_time_str})拔地而起，斜率{sig.launch_slope_deg}°，全池动能分最高({sig.horse_race_score})！"
                elif sig.pullback_no_touch:
                    is_valid_buy = True
                    assigned_weight = single_follower_weight
                    buy_reason = f"🚀 回踩VWAP不破极限买点: 现价在VWAP({sig.vwap:.2f})之上浅踩拉起，极窄止损线{sig.stop_loss_price:.2f}元！"
                    order_urgency = "LIMIT"

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
                            urgency=order_urgency,
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

