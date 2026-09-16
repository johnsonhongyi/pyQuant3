# -*- coding: utf-8 -*-
"""
ats/vwap_trading_engine.py
--------------------------
VWAPTradingEngine — 分时均价交易策略引擎（进攻端与双组投票评估）
负责计算分时 VWAP 动态特征（斜率、穿越、横盘筑底）、分时结构清晰度、多空犹豫期特征，
并分别生成激进组买入提案与保守组辅助监管审核投票，交由 ConsensusArbiter 统一仲裁。
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd

from ats.vwap_rule_model import VWAPRuleModel
from ats.consensus_arbiter import ConsensusArbiter, VoteResult, ArbiterDecision

logger = logging.getLogger("VWAPTradingEngine")


@dataclass
class MinuteBar:
    """1 分钟 K 线特征"""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float

    @property
    def is_doji(self) -> bool:
        """实体占总振幅比例小于 25% 视为十字星/犹豫线"""
        rng = self.high - self.low
        if rng <= 0:
            return True
        body = abs(self.close - self.open)
        return (body / rng) < 0.25


@dataclass
class VWAPTickState:
    """分时状态动态快照"""
    code: str
    price: float
    vwap_today: float
    vwap_yesterday: float
    vwap_cum_5d: float
    
    vwap_slope_5m: float = 0.0            # 5分钟 VWAP 变化斜率 (%)
    vwap_direction: str = "FLAT"          # "UP" | "FLAT" | "DOWN"
    price_vs_vwap: str = "FLAT"           # "ABOVE" | "BELOW" | "CROSSING_UP" | "CROSSING_DOWN"
    
    minutes_above_vwap: int = 0
    minutes_below_vwap: int = 0
    consolidation_minutes: int = 0        # 横盘整理分钟数
    consolidation_range_pct: float = 0.0  # 横盘振幅 (%)
    volume_ratio: float = 1.0             # 量比
    
    # 辅助监管特征
    structure_clarity_score: float = 85.0 # 分时形态清晰度 (0 ~ 100)
    is_hesitation_period: bool = False    # 是否处于多空犹豫期
    hesitation_reason: str = ""


class VWAPTradingEngine:
    """
    分时均价交易策略引擎
    """

    def __init__(
        self,
        arbiter: Optional[Any] = None,
        rule_model: Optional[Any] = None,
    ):
        if isinstance(arbiter, VWAPRuleModel):
            rule_model, arbiter = arbiter, rule_model
        self.rule_model = rule_model or VWAPRuleModel()
        self.arbiter = arbiter or ConsensusArbiter(self.rule_model)
        
        # 每只标的的滑动分时历史 (最多保留 240 根 1 分钟柱)
        self._minute_bars: Dict[str, List[MinuteBar]] = {}
        self._last_price_vs_vwap: Dict[str, str] = {}

    def update_minute_bar(
        self,
        code: str,
        bar_time: float,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        vwap: float,
    ) -> None:
        """更新分时分钟线数据"""
        if code not in self._minute_bars:
            self._minute_bars[code] = []
        bars = self._minute_bars[code]
        bars.append(
            MinuteBar(
                timestamp=bar_time,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                vwap=vwap,
            )
        )
        if len(bars) > 240:
            bars.pop(0)

    def compute_tick_state(
        self,
        code: str,
        price: float,
        vwap_today: float,
        vwap_yesterday: float = 0.0,
        vwap_cum_5d: float = 0.0,
        volume_ratio: float = 1.0,
    ) -> VWAPTickState:
        """计算当前 Tick 的分时动态指标"""
        bars = self._minute_bars.get(code, [])
        prev_relation = self._last_price_vs_vwap.get(code, "FLAT")

        # 1. 价格与均价线相对关系判定
        curr_relation = "ABOVE" if price > vwap_today else ("BELOW" if price < vwap_today else "FLAT")
        if prev_relation == "BELOW" and curr_relation == "ABOVE":
            price_vs_vwap = "CROSSING_UP"
        elif prev_relation == "ABOVE" and curr_relation == "BELOW":
            price_vs_vwap = "CROSSING_DOWN"
        else:
            price_vs_vwap = curr_relation
        self._last_price_vs_vwap[code] = curr_relation

        # 2. VWAP 斜率与方向计算
        vwap_slope = 0.0
        vwap_direction = "FLAT"
        if len(bars) >= 5:
            past_vwap = bars[-5].vwap
            if past_vwap > 0:
                vwap_slope = (vwap_today - past_vwap) / past_vwap * 100.0
                if vwap_slope > 0.05:
                    vwap_direction = "UP"
                elif vwap_slope < -0.05:
                    vwap_direction = "DOWN"
                else:
                    vwap_direction = "FLAT"

        # 3. 连续站上/跌破 VWAP 分钟数
        minutes_above = 0
        minutes_below = 0
        for b in reversed(bars):
            if b.close >= b.vwap:
                if minutes_below > 0:
                    break
                minutes_above += 1
            else:
                if minutes_above > 0:
                    break
                minutes_below += 1

        # 4. 横盘筑底检测 (Consolidation)
        consolidation_minutes = 0
        consolidation_range = 0.0
        if len(bars) >= 10:
            for window_size in [30, 20, 15, 10]:
                if len(bars) >= window_size:
                    sub_bars = bars[-window_size:]
                    highs = max(b.high for b in sub_bars)
                    lows = min(b.low for b in sub_bars)
                    if lows > 0:
                        rng_pct = (highs - lows) / lows * 100.0
                        if rng_pct <= 1.5:  # 振幅在 1.5% 以内视为横盘整理
                            consolidation_minutes = window_size
                            consolidation_range = rng_pct
                            break

        # 5. 保守组专职审查指标：分时结构清晰度与犹豫期识别
        clarity_score, is_hesitating, hesitation_reason = self._analyze_structure_and_hesitation(bars, vwap_direction)

        return VWAPTickState(
            code=code,
            price=price,
            vwap_today=vwap_today,
            vwap_yesterday=vwap_yesterday,
            vwap_cum_5d=vwap_cum_5d,
            vwap_slope_5m=vwap_slope,
            vwap_direction=vwap_direction,
            price_vs_vwap=price_vs_vwap,
            minutes_above_vwap=minutes_above,
            minutes_below_vwap=minutes_below,
            consolidation_minutes=consolidation_minutes,
            consolidation_range_pct=consolidation_range,
            volume_ratio=volume_ratio,
            structure_clarity_score=clarity_score,
            is_hesitation_period=is_hesitating,
            hesitation_reason=hesitation_reason,
        )

    def _analyze_structure_and_hesitation(
        self, bars: List[MinuteBar], vwap_direction: str
    ) -> Tuple[float, bool, str]:
        """
        保守组专职辅助监管算法：
        评估分时形态清晰度 (0~100) 并判断是否处于十字星多空拉锯犹豫期
        """
        if len(bars) < 10:
            return 80.0, False, ""

        recent = bars[-10:]
        
        # 1. 计算十字星比例
        doji_count = sum(1 for b in recent if b.is_doji)
        doji_ratio = doji_count / len(recent)

        # 2. 计算多空反复交替锯齿次数 (Whipsaws)
        direction_flips = 0
        for i in range(1, len(recent)):
            prev_dir = 1 if recent[i - 1].close >= recent[i - 1].open else -1
            curr_dir = 1 if recent[i].close >= recent[i].open else -1
            if prev_dir != curr_dir:
                direction_flips += 1

        # 3. 清晰度评分计算 (满分 100)
        clarity = 100.0
        # 十字星过多扣分
        clarity -= doji_ratio * 40.0
        # 剧烈反复锯齿拉锯扣分
        if direction_flips >= 6:
            clarity -= 25.0
        # 均线向下扣分
        if vwap_direction == "DOWN":
            clarity -= 20.0

        clarity_score = max(0.0, min(100.0, clarity))

        # 4. 犹豫期判定 (Hesitation Period)
        is_hesitating = False
        hesitation_reason = ""

        if doji_ratio >= 0.40:
            is_hesitating = True
            hesitation_reason = f"近10分钟十字星占比达 {doji_ratio*100:.0f}%，多空博弈犹豫不决"
        elif direction_flips >= 7:
            is_hesitating = True
            hesitation_reason = "分时呈现多空高频锯齿拉锯，缺乏有效单边推升合力"
        elif vwap_direction == "DOWN":
            is_hesitating = True
            hesitation_reason = "均价线处于下倾通道，属于弱势混沌期"

        return clarity_score, is_hesitating, hesitation_reason

    def evaluate_buy_opportunity(
        self,
        state: VWAPTickState,
        multi_period_score: float = 75.0,
        extra_ctx: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
    ) -> ArbiterDecision:
        """
        全流程评估：
        1. 激进组评估进攻买点
        2. 保守组辅助监管审查 (分时结构清晰度 + 犹豫期一票否决)
        3. ConsensusArbiter 执行双组投票仲裁
        """
        ctx = extra_ctx or {}
        t = now if now is not None else time.time()

        # ---------------------------------------------------------------------
        # 1. 激进组投票评估 (Aggressive Group)
        # ---------------------------------------------------------------------
        agg_vote = VoteResult(voter_group="aggressive", decision="REJECT")

        is_reversal = ctx.get("is_reversal_structure", False)
        hl_price = float(ctx.get("higher_low", 0.0))
        prev_l = float(ctx.get("prev_low", 0.0))
        prev_h = float(ctx.get("prev_high", 0.0))

        # 规则 0: VWAP 位移底抬高反转突破 (高低点转换主升反转，最高优先级)
        if is_reversal:
            agg_vote = VoteResult(
                voter_group="aggressive",
                decision="APPROVE",
                proposed_size_pct=0.25,
                rule_id="buy_vwap_displacement_reversal",
                rule_name="VWAP位移底抬高反转突破",
                reason=f"底抬高企稳(次低{hl_price:.2f}元>前底{prev_l:.2f}元) + VWAP向上位移 + 突破前高({prev_h:.2f}元)高低点转换",
            )
        # 规则 1: VWAP 筑底放量突破 (301531 式)
        elif (
            state.price_vs_vwap in ("CROSSING_UP", "ABOVE")
            and state.consolidation_minutes >= 10
            and state.volume_ratio >= 1.1
            and state.vwap_direction in ("UP", "FLAT")
            and multi_period_score >= 65.0
        ):
            agg_vote = VoteResult(
                voter_group="aggressive",
                decision="APPROVE",
                proposed_size_pct=0.15,
                rule_id="buy_vwap_base_breakout",
                rule_name="VWAP筑底突破",
                reason=f"低位横盘 {state.consolidation_minutes} 分钟后放量向上突破 VWAP (量比 {state.volume_ratio:.2f})",
            )
        # 规则 2: 站稳 VWAP 回踩确认加仓
        elif (
            state.minutes_above_vwap >= 10
            and state.price >= state.vwap_today
            and state.volume_ratio >= 1.0
            and multi_period_score >= 70.0
        ):
            agg_vote = VoteResult(
                voter_group="aggressive",
                decision="APPROVE",
                proposed_size_pct=0.10,
                rule_id="buy_vwap_confirm",
                rule_name="站稳VWAP确认加仓",
                reason=f"持续站上均价线已达 {state.minutes_above_vwap} 分钟，回踩稳固",
            )
        # 规则 3: 低开高走站上均价
        elif (
            ctx.get("pattern_low_open_high_walk", False)
            and state.price_vs_vwap == "ABOVE"
            and multi_period_score >= 60.0
        ):
            agg_vote = VoteResult(
                voter_group="aggressive",
                decision="APPROVE",
                proposed_size_pct=0.10,
                rule_id="buy_low_open_above_vwap",
                rule_name="低开走高站上均价",
                reason="低开走高强势形态且突破均线压制",
            )

        # ---------------------------------------------------------------------
        # 2. 保守组辅助监管审查 (Conservative Group)
        # ---------------------------------------------------------------------
        con_cfg = self.rule_model.conservative_config
        min_clarity = con_cfg.min_structure_clarity if con_cfg else 70.0
        con_vote = VoteResult(
            voter_group="conservative",
            decision="REJECT",
            structure_clarity_score=state.structure_clarity_score,
            is_hesitation_period=state.is_hesitation_period,
            hesitation_details=state.hesitation_reason,
        )

        if is_reversal:
            # 反转主升确立，保守组豁免犹豫期并全力支持开仓
            con_vote.decision = "APPROVE"
            con_vote.proposed_size_pct = 0.20
            con_vote.reason = f"保守组审核通过: 底抬高企稳({hl_price:.2f}元)且VWAP位移向上，确立主升反转架构"
        elif state.is_hesitation_period:
            con_vote.decision = "HESITATE"
            con_vote.reason = f"保守组否决: {state.hesitation_reason}"
        elif state.structure_clarity_score < min_clarity:
            con_vote.decision = "REJECT"
            con_vote.reason = f"保守组否决: 分时结构清晰度不足 ({state.structure_clarity_score:.1f} < {min_clarity})"
        else:
            # 形态清晰且非犹豫期，支持开仓
            con_vote.decision = "APPROVE"
            con_vote.proposed_size_pct = 0.10
            con_vote.reason = f"分时形态规整 (清晰度 {state.structure_clarity_score:.1f})，确认非犹豫期"

        # ---------------------------------------------------------------------
        # 3. 双组投票仲裁
        # ---------------------------------------------------------------------
        decision = self.arbiter.arbitrate_buy(
            code=state.code,
            agg_vote=agg_vote,
            con_vote=con_vote,
            now=t,
        )
        return decision


def detect_vwap_displacement_reversal(df_bars: pd.DataFrame) -> Dict[str, Any]:
    """
    【📈 分时/多日走势：底抬高企稳 + VWAP位移 + 高低点转换反转结构识别器】
    支持多日分时 (df_bars 包含多天数据) 与单日分时 (df_bars 为单日分时数据)。
    """
    res = {
        "is_reversal": False,
        "higher_low": 0.0,
        "prev_low": 0.0,
        "prev_high": 0.0,
        "vwap_today": 0.0,
        "vwap_yesterday": 0.0,
        "vwap_displacement_pct": 0.0,
        "reason": ""
    }
    if df_bars is None or df_bars.empty or len(df_bars) < 10:
        return res

    # 1. 尝试按交易日分组 (针对 2d/3d/5d/10d 多日分时)
    dates = []
    if "date" in df_bars.columns:
        dates = df_bars["date"].dropna().unique().tolist()
    elif "datetime" in df_bars.columns:
        dates = [str(d)[:10] for d in df_bars["datetime"].dropna().unique()]
        dates = list(dict.fromkeys(dates))
    elif isinstance(df_bars.index, pd.Index):
        first_idx = str(df_bars.index[0])
        if " " in first_idx:
            dates = list(dict.fromkeys([str(idx).split()[0] for idx in df_bars.index]))

    if len(dates) >= 2:
        # 多日分时场景 (以 688635 / 300672 5日图为例)
        date_groups = []
        for d in dates:
            if "date" in df_bars.columns:
                sub = df_bars[df_bars["date"] == d]
            else:
                sub = df_bars[[str(idx).startswith(d) for idx in df_bars.index]]
            if not sub.empty:
                h = float(sub["high"].max())
                l = float(sub["low"].min())
                c = float(sub["close"].iloc[-1])
                vw = float(sub["vwap"].iloc[-1]) if "vwap" in sub.columns else c
                date_groups.append({"date": d, "high": h, "low": l, "close": c, "vwap": vw, "len": len(sub)})

        if len(date_groups) >= 2:
            today_info = date_groups[-1]
            prev_info = date_groups[-2]

            # 寻找今日之前的波谷最低点 L1 (探底大底)
            prior_lows = [g["low"] for g in date_groups[:-1]]
            l1 = min(prior_lows)
            # 昨日或最近回踩低点 L2
            l2 = prev_info["low"]

            # 昨日或前波段高点 H1
            h1 = prev_info["high"]
            curr_p = today_info["close"]
            vw_today = today_info["vwap"]
            vw_prev = prev_info["vwap"]

            # 条件 1: 次低点抬高企稳 (L2 >= L1 * 1.008 或今日最低 >= L1 * 1.01)
            # 例如 688635: 09-14=254, 09-15=261.1 > 254; 300672: 09-14=158, 09-15=160.6 > 158
            is_hl = (l2 >= l1 * 1.008) or (today_info["low"] >= l1 * 1.01 and l2 >= l1 * 0.995)

            # 条件 2: VWAP 向上位移 (vw_today >= vw_prev * 1.002 且当前价站稳均线之上)
            vw_disp_pct = (vw_today - vw_prev) / vw_prev * 100.0 if vw_prev > 0 else 0.0
            is_vwap_displaced = (vw_disp_pct >= 0.18) and (curr_p >= vw_today * 0.99)

            # 条件 3: 高低点转换 (突破前高 H1 或冲击前高)
            is_breakout = (curr_p >= h1 * 0.99) or (today_info["high"] >= h1)

            if is_hl and (is_vwap_displaced or is_breakout):
                res["is_reversal"] = True
                res["higher_low"] = l2 if l2 > l1 else today_info["low"]
                res["prev_low"] = l1
                res["prev_high"] = h1
                res["vwap_today"] = vw_today
                res["vwap_yesterday"] = vw_prev
                res["vwap_displacement_pct"] = round(vw_disp_pct, 2)
                res["reason"] = f"多日底抬高企稳(次低{res['higher_low']:.2f}元>前底{l1:.2f}元) + VWAP向上位移({vw_disp_pct:+.2f}%) + 突破前高({h1:.2f}元)结构转换"
                return res

    # 2. 单日分时场景 (1-day intraday)
    n = len(df_bars)
    if n >= 30:
        p1 = df_bars.iloc[:n//2]
        p2 = df_bars.iloc[n//2:]
        l1 = float(p1["low"].min())
        h1 = float(p1["high"].max())
        l2 = float(p2["low"].min())
        curr_p = float(df_bars["close"].iloc[-1])
        vw_early = float(p1["vwap"].iloc[-1]) if "vwap" in p1.columns else curr_p
        vw_curr = float(df_bars["vwap"].iloc[-1]) if "vwap" in df_bars.columns else curr_p

        if l2 > l1 * 1.005 and vw_curr > vw_early and curr_p >= h1 * 0.995:
            disp_pct = (vw_curr - vw_early) / vw_early * 100.0 if vw_early > 0 else 0.0
            res["is_reversal"] = True
            res["higher_low"] = l2
            res["prev_low"] = l1
            res["prev_high"] = h1
            res["vwap_today"] = vw_curr
            res["vwap_yesterday"] = vw_early
            res["vwap_displacement_pct"] = round(disp_pct, 2)
            res["reason"] = f"日内底抬高企稳(次低{l2:.2f}元>早盘底{l1:.2f}元) + 分时VWAP上移 + 突破日内前高({h1:.2f}元)"
            return res

    return res
