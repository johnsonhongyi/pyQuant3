# -*- coding: utf-8 -*-
"""ats/fusion — 全市场信号融合与梯度执行层 (Signal Fusion Ladder, SFL)。

存在意义：
    现有系统并不缺数据，也不缺信号。缺的是**把"强度"换算成"可参与度"、
    再把"可参与度"换算成"仓位/进场/止损/有效期"的那一层**。
    本包只做换算与分级，不产生行情、不改原始数据、不直接下单。

分层：
    contract.py  统一事件与决策契约（SignalEvent / FusionDecision）
    regime.py    市场温度与翻转状态机（IDLE/ARMED/FLIPPING/CONFIRMED/FADING）
    engine.py    三轴评分 + 风险否决 + L0~L4 梯度映射 + 先手时间衰减

约束：
    所有事件必须自带 source / trade_date / freshness_s；缺失或过期一律 L0，
    不得把过期或跨日数据伪装为有效行情。
"""

from ats.fusion.contract import (
    AxisScores,
    FusionDecision,
    SignalEvent,
    TierSpec,
)
from ats.fusion.engine import FusionEngine, LADDER, tier_of
from ats.fusion.regime import (
    FLIP_ARMED,
    FLIP_CONFIRMED,
    FLIP_FADING,
    FLIP_FLIPPING,
    FLIP_IDLE,
    MarketRegime,
    MarketRegimeTracker,
    RegimeSample,
    STAGE_COLD,
    STAGE_EBB,
    STAGE_ICE,
    STAGE_OVERHEAT,
    STAGE_WARMING,
)

__all__ = [
    "AxisScores",
    "FusionDecision",
    "SignalEvent",
    "TierSpec",
    "FusionEngine",
    "LADDER",
    "tier_of",
    "MarketRegime",
    "MarketRegimeTracker",
    "RegimeSample",
    "STAGE_ICE",
    "STAGE_COLD",
    "STAGE_WARMING",
    "STAGE_OVERHEAT",
    "STAGE_EBB",
    "FLIP_IDLE",
    "FLIP_ARMED",
    "FLIP_FLIPPING",
    "FLIP_CONFIRMED",
    "FLIP_FADING",
]
