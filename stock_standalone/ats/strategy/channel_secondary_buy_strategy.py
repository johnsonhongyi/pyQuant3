# -*- coding: utf-8 -*-
"""
ats/strategy/channel_secondary_buy_strategy.py
-------------------------------------------------
长期通道后企稳与底部结构次级买点策略核心引擎 (Channel Secondary Buy Strategy)

【操盘手实战哲学与核心定位】：
1. 识别 60F/日K 长期下降通道的动能减速与走平（下行斜率衰减、成交量阶梯萎缩）；
2. 识别底部平底箱体扎底（Base Low），拒绝盲目抄底；
3. 首次试盘长阳突破（First Breakout）仅标记为结构启动，【实战铁律：严禁追高】；
4. 追踪极度缩量回踩企稳（Pullback Stable），要求守住次低点（Higher Low > Base Low）；
5. 次级放量突破确认（Secondary Buy）生成可交易买点，自动构建标准化不可变 IPOTradePlan；
6. 严格规范 signal_level (S0~S5) 与 quality_grade (A/S/SS)，与全池风控、退出引擎无缝对齐。
"""

import os
import sys
import math
import time
import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd

from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger("ChannelSecondaryBuy")


# ==============================================================================
# 1. 结构状态机与分级枚举规范
# ==============================================================================

class SecondaryBuyStage:
    """次级买点 6 阶状态机"""
    DESCENDING_CHANNEL = "DESCENDING_CHANNEL"  # 1. 长期通道压制/下行寻底
    BASE_DRYUP         = "BASE_DRYUP"          # 2. 底部缩量扎底/横盘平底箱体
    FIRST_BREAKOUT     = "FIRST_BREAKOUT"      # 3. 首阳试盘突破 (只标记不买)
    PULLBACK_STABLE    = "PULLBACK_STABLE"     # 4. 缩量回踩抬高 (守住 Higher Low)
    SECONDARY_BUY      = "SECONDARY_BUY"       # 5. 次级放量突破确认 (S4/S5 买点)
    INVALIDATED        = "INVALIDATED"         # 6. 跌破底台失效 (彻底清空)


# 策略 Tag 正交体系
TAG_CHANNEL_SECONDARY_BUY   = "CHANNEL_SECONDARY_BUY"
TAG_SUBNEW_PULLBACK_REENTRY = "SUBNEW_PULLBACK_REENTRY"
TAG_IPO_VWAP_STABLE         = "IPO_VWAP_STABLE"
TAG_IPO_BID_SURGE           = "IPO_BID_SURGE"


# ==============================================================================
# 2. 标准不可变交易计划 (IPOTradePlan) 数据容器
# ==============================================================================

@dataclass
class IPOTradePlan:
    """标准不可变交易计划容器 (实盘买卖点绑定与全生命周期保护基石)"""
    code: str = ""                            # 标的代码
    name: str = ""                            # 标的名称
    plan_id: str = ""                         # 唯一计划编号，如 TP_688826_20260919_093201
    strategy_tag: str = TAG_CHANNEL_SECONDARY_BUY # 策略正交标签
    signal_level: str = "S4"                  # "S0" ~ "S5" (生命周期层级)
    quality_grade: str = "S"                  # "A" | "S" | "SS" (形态质量等级)
    
    # 价格执行网络
    trigger_price: float = 0.0                # 次级买点确认触发价
    buy_zone_min: float = 0.0                 # 建议买入区间下限 (回踩均线支撑)
    buy_zone_max: float = 0.0                 # 建议买入区间上限 (严禁追高超幅 1.5%)
    
    # 结构防守与止损铁律 (严格溯源开仓形态，注入 ProactiveExitEngine)
    higher_low_stop: float = 0.0              # 核心防守位：次回踩次低点 (跌破即说明买点错误，立斩出局)
    base_low_invalid: float = 0.0             # 终极失效位：底部大平底箱体最低点
    hard_stop_loss_pct: float = 2.5           # 极窄风险兜底 (最大亏损不超过 2.5%)
    
    # 盈利目标阶梯
    target_1_channel_mid: float = 0.0         # 目标位 1：长期通道中轴/阻力位 (减仓 30% 并抬保本线)
    target_2_swing_high: float = 0.0          # 目标位 2：前期波段阻力高点 (减仓 40% 留底仓趋势跟踪)
    
    # 执行建议 (收敛为单向仓位指令，禁止自动全仓轮动换马)
    suggested_action: str = "BUY_SCOUT"        # "BUY_SCOUT" (30%) | "BUY_CONFIRM" (30%) | "EXIT_ALL"
    position_pct: float = 30.0                # 建议单笔执行仓位百分比
    expire_at: str = "14:45:00"               # 计划失效截止时间 (当日有效)
    created_time: str = ""
    extra_info: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.plan_id and self.code:
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.plan_id = f"TP_{self.code}_{now_str}"

    @property
    def buy_zone_lower(self) -> float:
        return self.buy_zone_min

    @property
    def buy_zone_upper(self) -> float:
        return self.buy_zone_max

    @property
    def target_2_breakout_high(self) -> float:
        return self.target_2_swing_high

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


# ==============================================================================
# 3. 极速纯 NumPy 辅助计算
# ==============================================================================

def _calc_slope_deg(y_arr: np.ndarray) -> float:
    """纯 NumPy 点积极速一维线性回归斜率角度 (-60° ~ +60°)，单次耗时 < 0.01ms"""
    m = len(y_arr)
    if m < 2:
        return 0.0
    p_mean = float(np.mean(y_arr))
    if p_mean <= 1e-4:
        return 0.0
    y_norm = (y_arr - p_mean) / p_mean * 100.0
    x_arr = np.arange(m, dtype=np.float64)
    x_mean = (m - 1.0) / 2.0
    y_m = float(np.mean(y_norm))
    num = float(np.dot(x_arr, y_norm)) - m * x_mean * y_m
    denom = (m * (m * m - 1.0)) / 12.0
    slope_pct = num / max(1e-6, denom)
    return float(math.atan(slope_pct * 1.5) * 180.0 / math.pi)


# ==============================================================================
# 4. 核心纯函数：evaluate_channel_secondary_buy
# ==============================================================================

def evaluate_channel_secondary_buy(
    df_60m: pd.DataFrame,
    df_day: Optional[pd.DataFrame] = None,
    current_quote: Optional[Dict[str, Any]] = None,
    min_bars: int = 20,
    code: str = "",
    name: str = ""
) -> Dict[str, Any]:
    """
    【长期通道后企稳与底部结构次级买点评估纯函数】
    输入：60F K线 (必须), 日K线 (可选), 实时盘口/现价 (可选)
    输出：标准化结构判断结果与不可变 TradePlan (若达到 S4/S5)
    严格遵守主流程安全原则，绝不抛出未捕获异常
    """
    try:
        return _evaluate_channel_secondary_buy_impl(
            df_60m=df_60m,
            df_day=df_day,
            current_quote=current_quote,
            min_bars=min_bars,
            code=code,
            name=name
        )
    except Exception as e:
        logger.error(f"[{code}] 通道次级买点评估异常: {e}", exc_info=True)
        return {
            "code": code,
            "name": name,
            "strategy_tag": TAG_CHANNEL_SECONDARY_BUY,
            "is_valid": False,
            "stage": SecondaryBuyStage.DESCENDING_CHANNEL,
            "signal_level": "S0",
            "quality_grade": "A",
            "base_low": 0.0,
            "higher_low": 0.0,
            "base_high": 0.0,
            "first_break_price": 0.0,
            "secondary_entry": 0.0,
            "invalid_price": 0.0,
            "hard_stop": 0.0,
            "target_1": 0.0,
            "target_2": 0.0,
            "slope_deg": 0.0,
            "vol_shrink_ratio": 1.0,
            "score": 0.0,
            "reason": f"通道次级买点计算异常: {e}",
            "trade_plan": None
        }


def _evaluate_channel_secondary_buy_impl(
    df_60m: pd.DataFrame,
    df_day: Optional[pd.DataFrame] = None,
    current_quote: Optional[Dict[str, Any]] = None,
    min_bars: int = 20,
    code: str = "",
    name: str = ""
) -> Dict[str, Any]:
    res = {
        "code": code,
        "name": name,
        "strategy_tag": TAG_CHANNEL_SECONDARY_BUY,
        "is_valid": False,
        "stage": SecondaryBuyStage.DESCENDING_CHANNEL,
        "signal_level": "S0",
        "quality_grade": "A",
        "base_low": 0.0,
        "higher_low": 0.0,
        "base_high": 0.0,
        "first_break_price": 0.0,
        "secondary_entry": 0.0,
        "invalid_price": 0.0,
        "hard_stop": 0.0,
        "target_1": 0.0,
        "target_2": 0.0,
        "slope_deg": 0.0,
        "vol_shrink_ratio": 1.0,
        "score": 0.0,
        "reason": "",
        "trade_plan": None
    }

    if df_60m is None or len(df_60m) < min_bars:
        res["reason"] = f"60F K线不足 {min_bars} 根 (实际 {len(df_60m) if df_60m is not None else 0})"
        return res

    closes = df_60m['close'].values.astype(np.float64) if 'close' in df_60m.columns else df_60m['trade'].values.astype(np.float64)
    highs = df_60m['high'].values.astype(np.float64) if 'high' in df_60m.columns else closes
    lows = df_60m['low'].values.astype(np.float64) if 'low' in df_60m.columns else closes
    opens = df_60m['open'].values.astype(np.float64) if 'open' in df_60m.columns else closes
    vols = df_60m['vol'].values.astype(np.float64) if 'vol' in df_60m.columns else (
        df_60m['volume'].values.astype(np.float64) if 'volume' in df_60m.columns else np.ones(len(closes), dtype=np.float64)
    )
    n = len(closes)

    # 现价确定
    curr_price = float(closes[-1])
    if current_quote and 'price' in current_quote and float(current_quote['price']) > 0:
        curr_price = float(current_quote['price'])
    elif current_quote and 'trade' in current_quote and float(current_quote['trade']) > 0:
        curr_price = float(current_quote['trade'])

    # 1. 测算长期通道斜率与走平减速特征 (考察过去 20~60 根 60F K线)
    w_long = min(n, 60)
    long_slope = _calc_slope_deg(closes[-w_long:])
    res["slope_deg"] = round(long_slope, 2)

    # 2. 定位底部平底箱体最低点 (Base Low) 与发生索引
    # 考察除最新 2 根外的历史波谷，防止最新 K 线暴跌直接把 base_low 动态拉低而无法检测破位
    w_base = min(n, 40)
    eval_bars = lows[-w_base:-2] if w_base > 4 else lows[-w_base:]
    min_idx_local = int(np.argmin(eval_bars))
    base_low_idx = (n - w_base) + min_idx_local if w_base > 4 else (n - len(eval_bars)) + min_idx_local
    base_low = float(lows[base_low_idx])
    res["base_low"] = round(base_low, 3)
    res["invalid_price"] = round(base_low * 0.99, 3)

    # 破位检查：如果现价跌破前期底部箱体支撑，则直接失效
    if curr_price < base_low * 0.992:
        res["stage"] = SecondaryBuyStage.INVALIDATED
        res["signal_level"] = "S0"
        res["reason"] = f"现价 {curr_price:.2f} 跌破底部箱体最低点 {base_low:.2f}，形态失效"
        return res

    # 3. 寻找 base_low 之后的首个试盘突破波峰 (First Peak / First Breakout)
    after_base_highs = highs[base_low_idx + 1:]
    if len(after_base_highs) == 0:
        res["stage"] = SecondaryBuyStage.BASE_DRYUP
        res["signal_level"] = "S1"
        return res

    # 寻找首个冲高回落波峰：从 base_low 往后遍历，找到第一个形成回落的局部高点
    first_break_idx = None
    for i in range(base_low_idx + 1, n - 1):
        if highs[i] >= base_low * 1.02 and closes[i + 1] < highs[i] * 0.998:
            first_break_idx = i
            break

    # 若未找到明确回落，但中间有显著高点
    if first_break_idx is None:
        if len(after_base_highs) >= 4:
            mid_len = max(2, len(after_base_highs) - 2)
            first_break_local = int(np.argmax(after_base_highs[:mid_len]))
            first_break_idx = base_low_idx + 1 + first_break_local
        else:
            first_break_idx = base_low_idx + 1 + int(np.argmax(after_base_highs))

    first_break_high = float(highs[first_break_idx])
    first_break_close = float(closes[first_break_idx])
    res["first_break_price"] = round(first_break_high, 3)
    res["base_high"] = round(first_break_high, 3)
    bars_since_break = n - 1 - first_break_idx

    # 如果刚刚产生首次突破（突破后仅 0~1 根 Bar 且在冲高），属于试盘冲高，严禁追高！
    if bars_since_break <= 1 and (curr_price >= first_break_high * 0.97):
        res["stage"] = SecondaryBuyStage.FIRST_BREAKOUT
        res["signal_level"] = "S2"
        res["reason"] = f"首次突破前高试盘 {first_break_high:.2f}，严禁冲高追买，等待缩量回踩"
        return res

    bars_since_base = n - 1 - base_low_idx
    if bars_since_base < 3:
        res["stage"] = SecondaryBuyStage.BASE_DRYUP
        res["signal_level"] = "S1"
        res["reason"] = f"刚触及大底波谷 {base_low:.2f} (历经 {bars_since_base} 根Bar)，处于底部平底初期"
        return res

    # 4. 寻找突破后的回踩次低点 (Higher Low)
    if first_break_idx < n - 1:
        pullback_lows = lows[first_break_idx + 1:]
        pullback_closes = closes[first_break_idx + 1:]
        pullback_vols = vols[first_break_idx + 1:]
        
        higher_low_local = int(np.argmin(pullback_lows))
        higher_low_idx = first_break_idx + 1 + higher_low_local
        higher_low = float(lows[higher_low_idx]) # 全局索引安全取值
    else:
        higher_low = base_low
        higher_low_idx = base_low_idx

    res["higher_low"] = round(higher_low, 3)
    res["hard_stop"] = round(higher_low * 0.992, 3)

    # 核心几何校验：次低点必须抬高 (Higher Low > Base Low)
    if higher_low <= base_low * 1.002:
        res["stage"] = SecondaryBuyStage.BASE_DRYUP
        res["signal_level"] = "S1"
        res["reason"] = f"回踩低点 {higher_low:.2f} 未能形成有效抬高 (BaseLow: {base_low:.2f})，仍在底部震荡"
        return res

    # 5. 回踩段量能萎缩检验 (Volume Dry-Up)
    prior_vol_mean = float(np.mean(vols[max(0, base_low_idx - 10):base_low_idx + 1])) if base_low_idx > 0 else 1.0
    pullback_vol_mean = float(np.mean(vols[first_break_idx + 1:])) if first_break_idx < n - 1 else prior_vol_mean
    vol_shrink_ratio = pullback_vol_mean / max(1e-4, prior_vol_mean)
    res["vol_shrink_ratio"] = round(vol_shrink_ratio, 2)

    # 6. 次级买点触发判断 (Secondary Buy Confirmation)
    # 次级确认线：以次回踩阶段的局部小箱体高点为准
    pullback_high = float(np.max(highs[higher_low_idx:-1])) if higher_low_idx < n - 1 else float(highs[first_break_idx])
    secondary_entry_line = pullback_high if pullback_high > higher_low * 1.01 else first_break_high
    res["secondary_entry"] = round(secondary_entry_line, 3)

    is_higher_low_safe = (curr_price >= higher_low * 0.998)
    is_inflection_up = (curr_price >= secondary_entry_line * 0.985) or (closes[-1] > closes[-2] and closes[-1] > opens[-1])

    # 设定目标位 (盈亏比计算)
    target_1 = round(curr_price * 1.08, 3)
    target_2 = round(curr_price * 1.16, 3)
    res["target_1"] = target_1
    res["target_2"] = target_2

    downside_risk_pct = (curr_price - higher_low) / curr_price * 100.0
    upside_space_pct = (target_1 - curr_price) / curr_price * 100.0
    reward_risk_ratio = upside_space_pct / max(0.5, downside_risk_pct)

    # 质量评级判定
    if reward_risk_ratio >= 3.5 and vol_shrink_ratio <= 0.8:
        quality_grade = "SS"
    elif reward_risk_ratio >= 2.5:
        quality_grade = "S"
    else:
        quality_grade = "A"
    res["quality_grade"] = quality_grade

    # 状态机分流
    if is_higher_low_safe and is_inflection_up and (curr_price >= secondary_entry_line * 0.992):
        # 命中次级买点确认！
        res["stage"] = SecondaryBuyStage.SECONDARY_BUY
        res["signal_level"] = "S4"
        res["is_valid"] = True
        
        # 评分模型 (基础分 80 + 缩量加分 + 盈亏比加分)
        score = 80.0
        if vol_shrink_ratio <= 0.75:
            score += 8.0
        if reward_risk_ratio >= 3.0:
            score += 7.0
        if long_slope >= -10.0:  # 通道明显走平
            score += 5.0
        res["score"] = round(min(98.0, score), 1)
        res["reason"] = (
            f"【次级买点确认】长期通道企稳(斜率{long_slope:.1f}°)，大底{base_low:.2f}首阳试盘后缩量回踩，"
            f"次低点{higher_low:.2f}有效抬高，现价{curr_price:.2f}放量上翘突破确认，盈亏比{reward_risk_ratio:.1f}:1"
        )

        # 构建标准不可变 TradePlan
        today_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        plan_id = f"TP_{code}_{today_str}"
        trade_plan = IPOTradePlan(
            plan_id=plan_id,
            code=code,
            name=name,
            strategy_tag=TAG_CHANNEL_SECONDARY_BUY,
            signal_level="S4",
            quality_grade=quality_grade,
            trigger_price=round(curr_price, 3),
            buy_zone_min=round(higher_low * 1.005, 3),
            buy_zone_max=round(curr_price * 1.015, 3),
            higher_low_stop=round(higher_low * 0.992, 3),
            base_low_invalid=round(base_low * 0.99, 3),
            hard_stop_loss_pct=round(min(3.0, max(1.5, downside_risk_pct)), 2),
            target_1_channel_mid=target_1,
            target_2_swing_high=target_2,
            suggested_action="BUY_SCOUT",
            position_pct=30.0,
            expire_at="14:45:00",
            created_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            extra_info={
                "base_low": base_low,
                "higher_low": higher_low,
                "first_break_price": first_break_high,
                "reward_risk_ratio": round(reward_risk_ratio, 2),
                "vol_shrink_ratio": round(vol_shrink_ratio, 2)
            }
        )
        res["trade_plan"] = trade_plan
    else:
        # 仍处于回踩守线阶段
        res["stage"] = SecondaryBuyStage.PULLBACK_STABLE
        res["signal_level"] = "S3"
        res["score"] = 72.0
        res["reason"] = f"缩量回踩企稳中，守住次低点 {higher_low:.2f}，等待放量突破次级确认线 {secondary_entry_line:.2f}"

    return res
