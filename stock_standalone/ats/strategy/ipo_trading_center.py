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
    signal_tier: str = "S"            # 触发建仓时的信号级别 (SSS / S / A)

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
    action: str                       # "BUY" | "SELL" | "HOLD" | "SWITCH_SWAP" | "FULL_ROTATION_SWAP"
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
    signal_tier: str = "S"            # "SSS" | "S" | "A" | "ALERT"
    target_swap_code: str = ""        # 全仓轮动换马接力目标代码
    target_swap_name: str = ""        # 全仓轮动换马接力目标名称

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

    def __init__(self, total_capital: float = 1000000.0, auto_load_ledger: bool = False, ledger_file: Optional[str] = None):
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
        self.trading_mode: str = "ROTATION_FULL_CAPITAL" # "ROTATION_FULL_CAPITAL" (全仓轮动单股接力) | "MULTI_POSITION" (组合分仓)
        self._lock = threading.RLock()
        
        self.sentiment_engine = IPOMarketSentimentEngine.get_instance()
        self._last_fleet_eval_ts: float = 0.0
        self._max_total_position_pct: float = 80.0 # 最大允许总仓位
        self.auto_follow_trading: bool = False     # 全自动跟随交易开关 (开启后自动撮合指令)
        self._pending_directives: List[IPOOrderDirective] = []

        # ATS 外部语音报警与异动信号感知统计与优质注入池
        self._external_signal_stats: Dict[str, int] = {
            "ladder_count": 0,
            "dragon_count": 0,
            "other_count": 0,
            "quality_injected_count": 0
        }
        self._perceived_external_signals: List[Dict[str, Any]] = []
        self._injected_quality_stocks: Dict[str, Dict[str, Any]] = {}

        # 仅当明确开启或指定账本文件时才从磁盘加载 (测试创建的纯内存临时实例不被磁盘历史污染)
        if auto_load_ledger or ledger_file:
            self._load_persisted_ledger()

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
        """获取当前待执行的最新交易指令"""
        with self._lock:
            return list(self._pending_directives)

    def get_closed_positions(self) -> List[IPOTradingPosition]:
        """获取历史已平仓/出局持仓列表 (支持复盘回溯与迭代详情查看)"""
        with self._lock:
            return list(self._closed_positions)

    def get_signal_iteration_log(self) -> List[Dict[str, Any]]:
        """获取全生命周期信号决策与迭代历史日志 (杜绝今天卖了就没下文)"""
        with self._lock:
            return list(self._signal_iteration_log)

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
                self.total_capital = float(data.get("total_capital", self.total_capital))
                self.available_cash = float(data.get("available_cash", self.available_cash))
                
                # 恢复活跃持仓
                pos_list = data.get("active_positions", [])
                for p_dict in pos_list:
                    if isinstance(p_dict, dict) and p_dict.get("code"):
                        field_names = set(IPOTradingPosition.__dataclass_fields__.keys())
                        safe_kwargs = {k: v for k, v in p_dict.items() if k in field_names}
                        p = IPOTradingPosition(**safe_kwargs)
                        if p.shares > 0:
                            self._positions[p.code] = p

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

            order_list = [d.__dict__.copy() for d in self._order_history[-100:]]
            
            payload = {
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "trading_mode": self.trading_mode,
                "total_capital": self.total_capital,
                "available_cash": self.available_cash,
                "active_positions": active_list,
                "closed_positions": closed_list,
                "order_history": order_list,
                "signal_iteration_log": self._signal_iteration_log[:200]
            }
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

            # 5. ── 【调仓换马：弃弱留强与全仓轮动 (FULL_ROTATION_SWAP / SWITCH_SWAP)】 ──
            # 持续跟随市场切换：持仓股动能滞涨落后，全池涌现出更强的 Rank 1 领头羊时果断换马
            if top_leader and top_leader.code not in self._positions:
                for code, pos in list(self._positions.items()):
                    if pos.shares <= 0 or code == top_leader.code:
                        continue
                    p_sig = self._reports_cache.get(code)
                    if p_sig and (p_sig.relative_to_leader_gap >= 15.0 or p_sig.horse_race_rank > 2):
                        # 检查新领头羊是否具备进击买点
                        if top_leader.signal_type in ("IPO_FIRST_BUY", "PULLBACK_BUY", "BREAKOUT", "BASE_BREAKOUT") or (top_leader.launch_time_str <= "09:50" and top_leader.launch_slope_deg >= 30.0):
                            if self.trading_mode == "ROTATION_FULL_CAPITAL":
                                # 👑 【全仓轮动接力模式】：生成原子换马决议 (100%全仓资金腾挪接力新龙头)
                                leader_buy_shares = int(self.total_capital / top_leader.price / 100.0) * 100 if top_leader.price > 0 else 0
                                directives.append(IPOOrderDirective(
                                    action="FULL_ROTATION_SWAP",
                                    code=top_leader.code,
                                    name=top_leader.name,
                                    price=top_leader.price,
                                    shares=leader_buy_shares,
                                    size_pct=100.0,
                                    urgency="CRITICAL",
                                    reason=f"🔄 全仓轮动换马: 坚决清仓[{pos.name}]，腾出100%全仓资金全速接力超级领头羊[{top_leader.name}({top_leader.horse_race_score:.0f}分)]！",
                                    horse_rank=top_leader.horse_race_rank,
                                    sentiment_phase=sentiment.heat_stage,
                                    timestamp=now_ts,
                                    signal_tier="SSS",
                                    target_swap_code=code,
                                    target_swap_name=pos.name
                                ))
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
                    self._pending_directives = directives
                    self._broadcast_directives_to_alert_notifier(directives)
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

            # ⚡ 若处于全仓轮动模式且当前全池无持仓，首选领头羊分配 100% 仓位
            if self.trading_mode == "ROTATION_FULL_CAPITAL":
                active_pos_count = sum(1 for p in self._positions.values() if p.shares > 0)
                if active_pos_count == 0:
                    single_leader_weight = 100.0
                    max_fleet_weight = 100.0

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
                    # 全仓模式下确保至少有 100 股
                    allocated_money = self.total_capital * (assigned_weight / 100.0)
                    buy_shares = int(allocated_money / sig.price / 100.0) * 100
                    if buy_shares >= 100:
                        # 避免 directives 中重复添加相同标的买单
                        if not any(d.code == code and d.action == "BUY" for d in directives):
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
                                signal_tier=s_tier
                            ))
                            current_fleet_weight += assigned_weight

            self._pending_directives = directives
            self._broadcast_directives_to_alert_notifier(directives)
            self._auto_execute_if_enabled(directives)
            return directives

    def _broadcast_directives_to_alert_notifier(self, directives: List[IPOOrderDirective]):
        """【📢 集中交易指令广播至 ATS 报警中心】"""
        if not directives:
            return
        now_ts = time.time()
        for d in directives:
            if d.action not in ("BUY", "FULL_ROTATION_SWAP", "SWITCH_SWAP", "SELL"):
                continue
            d_key = f"{d.action}_{d.code}_{d.urgency}"
            last_ts = self._notified_directive_keys.get(d_key, 0.0)
            if (now_ts - last_ts) < 180.0:  # 3分钟内相同指令不重复轰炸
                continue

            self._notified_directive_keys[d_key] = now_ts

            if d.action == "FULL_ROTATION_SWAP":
                reason_text = f"【全仓轮动换马】清仓[{d.name}]，100%全仓接力超级领头羊[{d.target_swap_name}]！"
                voice_p = 99.0
            elif d.action == "BUY":
                reason_text = f"【集中买入指令】买入[{d.name}] 仓位{d.size_pct:.0f}%：{d.reason}"
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
        """
        【同步撮合成交与全生命周期复盘追踪】
        - 彻底根治“今天卖了就没下文了”的断层痛点；
        - 平仓时将持仓完整快照、收益率、平仓理由压入 _closed_positions；
        - 将每次决议与撮合事件记录进 _signal_iteration_log；
        - 原子写盘持久化到本地账本。
        """
        with self._lock:
            code = directive.code
            if code not in self._positions:
                self._positions[code] = IPOTradingPosition(code=code, name=directive.name)
            pos = self._positions[code]
            t_str = time.strftime("%H:%M:%S")
            today_str = time.strftime("%Y-%m-%d")
            pnl_pct = 0.0
            pnl_amt = 0.0

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
                pos.entry_reason = directive.reason
                pos.signal_tier = directive.signal_tier
                pos.status = "HOLDING"
                pos.current_price = directive.price
                pos.highest_price = directive.price
                pos.lowest_price = directive.price
                pos.last_action = "BUY"
                pos.last_action_time = t_str
                logger.info(f"[IPO-TRADING] 买入成交: {pos.name}({code}) {directive.shares}股 @ {directive.price:.2f}元 | 剩余可用: {self.available_cash:.0f}元")

            elif directive.action == "FULL_ROTATION_SWAP":
                # ── 全仓轮动模式：第 1 步，全额平仓老股票回笼资金 ──
                old_code = directive.target_swap_code
                if old_code and old_code in self._positions:
                    old_pos = self._positions[old_code]
                    if old_pos.shares > 0:
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
                        old_pos.shares = 0
                        old_pos.available_shares = 0
                        del self._positions[old_code]
                        logger.info(f"[IPO-TRADING] 全仓轮动平出老标的: {old_pos.name}({old_code}) 回笼资金: {sell_val:.0f}元 | 盈亏: {pnl_pct:+.2f}%")

                # ── 全仓轮动模式：第 2 步，100% 满仓腾挪接力新龙头 ──
                new_shares = int(self.available_cash / (directive.price * 100)) * 100 if directive.price > 0 else 0
                if new_shares == 0 and directive.shares > 0:
                    new_shares = directive.shares
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
                logger.info(f"[IPO-TRADING] 全仓轮动接力新龙头成功: {new_pos.name}({code}) 满仓买入 {new_shares}股 @ {directive.price:.2f}元")

            elif directive.action in ("SELL", "SWITCH_SWAP"):
                sell_val = directive.price * pos.shares
                self.available_cash += sell_val
                if pos.cost_price > 0 and pos.shares > 0:
                    pnl_amt = (directive.price - pos.cost_price) * pos.shares
                    pnl_pct = round((directive.price - pos.cost_price) / pos.cost_price * 100.0, 2)

                pos.exit_price = directive.price
                pos.exit_time = t_str
                pos.exit_date = today_str
                pos.realized_pnl_pct = pnl_pct
                pos.realized_pnl_amount = round(pnl_amt, 2)
                pos.exit_reason = directive.reason
                pos.status = "CLOSED"
                pos.last_action = directive.action
                pos.last_action_time = t_str

                # 记录到历史已平仓持久化列表 (最新排最前)
                closed_snapshot = copy.deepcopy(pos)
                self._closed_positions.insert(0, closed_snapshot)
                if len(self._closed_positions) > 200:
                    self._closed_positions = self._closed_positions[:200]

                logger.info(f"[IPO-TRADING] 卖出平仓归档: {pos.name}({code}) {pos.shares}股 @ {directive.price:.2f}元 | 平仓收益: {pnl_pct:+.2f}% ({pnl_amt:+.0f}元) | 回笼: {sell_val:.0f}元")
                pos.shares = 0
                pos.available_shares = 0

            self._order_history.append(directive)

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
                "realized_pnl_pct": pnl_pct if directive.action != "BUY" else 0.0,
                "realized_pnl_amount": round(pnl_amt, 2) if directive.action != "BUY" else 0.0
            }
            self._signal_iteration_log.insert(0, log_item)
            if len(self._signal_iteration_log) > 300:
                self._signal_iteration_log = self._signal_iteration_log[:300]

            # 立即物理原子写盘落盘
            self._save_persisted_ledger()

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
                "signal_iteration_log": list(self._signal_iteration_log)
            }

