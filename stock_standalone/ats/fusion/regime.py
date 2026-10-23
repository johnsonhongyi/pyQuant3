# -*- coding: utf-8 -*-
"""ats/fusion/regime.py — 市场温度与"翻转"状态机。

为什么单独做：
    现有温度有两套口径但都是**快照**：
      - ats/ultra_short_anomaly_engine.py:159 MarketTemperatureCycleTracker（0~100℃，按温度带分档）
      - market_pulse_db.current_sentiment_state（COOLDOWN/NEUTRAL/REPAIR/REVERSAL/FOMO，状态机）
    两者都能告诉你"现在几度"，但都不能告诉你"**每分钟在升几度**"。
    而 2026-10-23 这种 30~60 分钟从低温直接翻转的行情，决定仓位梯度的
    恰恰是斜率，不是温度本身。

本模块只做三件事：
    1. 把温度、上涨家数、涨停/跌停、封板率、成交额同比合成 0~100 的温度；
    2. 计算 5 分钟斜率，并维护 IDLE/ARMED/FLIPPING/CONFIRMED/FADING 五态；
    3. 把温度映射为阶段（冰点/偏冷/回暖/过热/退潮），供引擎查梯度矩阵。

设计原则：
    - ARMED 是"提前量"状态：温度还没到 48，但斜率已经起来、跌停在减少。
      这是唯一允许在低温期放开 L2/L3 名额的窗口，用来解决
      "等确认时涨幅已经大了"的滞后。
    - 状态迁移带滞回（hysteresis），避免在阈值附近抖动导致仓位反复。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional, Tuple

# 温度阶段
STAGE_ICE = "ICE_COLD"          # ❄️ 冰点极寒  < 35
STAGE_COLD = "COLD_WEAK"        # 🌨️ 偏冷分歧  35 ~ 48
STAGE_WARMING = "WARMING"       # 🌱 回暖升温  48 ~ 60
STAGE_OVERHEAT = "OVERHEATED"   # 🔥 过热大考  >= 60
STAGE_EBB = "COOLING_EBB"       # 🌊 冲高退潮

STAGE_LABELS = {
    STAGE_ICE: "❄️ 冰点极寒",
    STAGE_COLD: "🌨️ 偏冷分歧",
    STAGE_WARMING: "🌱 回暖升温",
    STAGE_OVERHEAT: "🔥 过热大考",
    STAGE_EBB: "🌊 冲高退潮",
}

# 翻转状态
FLIP_IDLE = "IDLE"
FLIP_ARMED = "ARMED"           # 低位拐头，提前布防
FLIP_FLIPPING = "FLIPPING"     # 正在穿越 48℃
FLIP_CONFIRMED = "CONFIRMED"   # 翻转确认，涨停扩散
FLIP_FADING = "FADING"         # 退潮

FLIP_LABELS = {
    FLIP_IDLE: "—",
    FLIP_ARMED: "🎯 低位拐头",
    FLIP_FLIPPING: "🚀 正在翻转",
    FLIP_CONFIRMED: "✅ 翻转确认",
    FLIP_FADING: "🌊 退潮中",
}


@dataclass
class RegimeSample:
    """一分钟（或任意固定周期）一条的市场横截面样本。

    所有字段都可由现有数据算出：
      up_ratio          上涨家数 / 全市场
      limit_up/down     涨停、跌停家数
      seal_rate         封板率 = 未炸板数 / 触板数
      amount_yoy        成交额同比（1.0 = 与基准持平）
      index_vwap_ratio  指数成分中站上 VWAP 的占比（0~1）
    """

    ts: float
    up_ratio: float = 0.5
    limit_up: int = 0
    limit_down: int = 0
    seal_rate: float = 0.8
    amount_yoy: float = 1.0
    index_vwap_ratio: float = 0.5
    temp: Optional[float] = None   # 外部已算好的温度，给了就直接用


@dataclass
class MarketRegime:
    temp: float = 50.0
    stage: str = STAGE_WARMING
    slope_5m: float = 0.0            # ℃ / 5min
    flip_state: str = FLIP_IDLE
    breadth: float = 0.5
    limit_up: int = 0
    limit_down: int = 0
    seal_rate: float = 0.8
    peak_temp: float = 50.0
    updated_ts: float = 0.0

    @property
    def stage_label(self) -> str:
        return STAGE_LABELS.get(self.stage, self.stage)

    @property
    def flip_label(self) -> str:
        return FLIP_LABELS.get(self.flip_state, self.flip_state)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temp": round(self.temp, 1),
            "stage": self.stage,
            "stage_label": self.stage_label,
            "slope_5m": round(self.slope_5m, 2),
            "flip_state": self.flip_state,
            "flip_label": self.flip_label,
            "breadth": round(self.breadth, 3),
            "limit_up": self.limit_up,
            "limit_down": self.limit_down,
            "seal_rate": round(self.seal_rate, 3),
            "peak_temp": round(self.peak_temp, 1),
            "updated_ts": self.updated_ts,
        }


class MarketRegimeTracker:
    """温度斜率 + 翻转状态机。

    用法：
        tracker = MarketRegimeTracker()
        regime = tracker.update(RegimeSample(ts=now, up_ratio=0.62, limit_up=48, ...))
        decision = engine.evaluate(event, regime)

    只做单写者内存态；不落盘、不跨进程共享，避免引入新的锁与持久化契约。
    """

    def __init__(self, window: int = 30, slope_span_min: float = 5.0):
        self._samples: Deque[Tuple[float, float]] = deque(maxlen=max(6, int(window)))
        self._slope_span_min = max(1.0, float(slope_span_min))
        self._peak_temp = 0.0
        self._peak_limit_up = 0
        self._state = FLIP_IDLE
        self._state_since = 0.0
        self._last = MarketRegime()

    # -- 温度合成 ---------------------------------------------------------
    @staticmethod
    def compose_temp(sample: RegimeSample) -> float:
        """没有外部温度时，用横截面四项加权合成 0~100。

        权重刻意让"扩散度"（上涨家数占比）占主导，因为温度的本质是
        参与面而不是指数点位；跌停家数只做扣减。
        """
        breadth = max(0.0, min(1.0, sample.up_ratio))
        limit_up_score = max(0.0, min(1.0, sample.limit_up / 80.0))
        vwap_score = max(0.0, min(1.0, sample.index_vwap_ratio))
        seal = max(0.0, min(1.0, sample.seal_rate))
        amount = max(0.0, min(1.5, sample.amount_yoy)) / 1.5

        temp = 100.0 * (
            0.35 * breadth
            + 0.25 * limit_up_score
            + 0.15 * vwap_score
            + 0.15 * seal
            + 0.10 * amount
        )
        temp -= min(15.0, sample.limit_down * 0.75)
        return max(0.0, min(100.0, temp))

    # -- 斜率 -------------------------------------------------------------
    def _slope(self, now: float, temp: float) -> float:
        """最近 slope_span_min 分钟的温度变化，折算成 ℃/5min。"""
        if not self._samples:
            return 0.0
        target = now - self._slope_span_min * 60.0
        ref_ts, ref_temp = self._samples[0]
        for ts, t in self._samples:
            if ts <= target:
                ref_ts, ref_temp = ts, t
            else:
                break
        span_min = (now - ref_ts) / 60.0
        if span_min <= 0.05:
            return 0.0
        return (temp - ref_temp) / span_min * self._slope_span_min

    # -- 状态机 -----------------------------------------------------------
    def _next_state(self, temp: float, slope: float, sample: RegimeSample) -> str:
        prev = self._state
        limit_up_expanding = sample.limit_up >= max(1, int(self._peak_limit_up * 1.2))
        breadth_ok = sample.up_ratio >= 0.55

        # 退潮优先：斜率转负或炸板严重
        if slope <= -1.5 or (sample.seal_rate < 0.55 and temp >= 55.0):
            return FLIP_FADING
        if prev == FLIP_FADING and slope < 0.8:
            return FLIP_FADING

        # 翻转确认：温度过 55 且涨停扩散
        if temp >= 55.0 and slope >= 0.5 and (limit_up_expanding or breadth_ok):
            return FLIP_CONFIRMED

        # 正在翻转：穿越 48
        if temp >= 48.0 and slope >= 2.0:
            return FLIP_FLIPPING

        # 低位拐头：温度还没到 48，但斜率起来了、跌停在减少
        if temp < 48.0 and slope >= 1.5 and sample.limit_down <= 8:
            return FLIP_ARMED

        if prev in (FLIP_ARMED, FLIP_FLIPPING) and slope >= 1.0 and temp >= 44.0:
            return prev  # 滞回：不让提前量刚建立就掉回 IDLE

        return FLIP_IDLE

    def _stage(self, temp: float, slope: float, prev_stage: str) -> str:
        # 退潮优先：从峰值回落且斜率为负
        if self._peak_temp - temp >= 6.0 and slope <= -1.0:
            return STAGE_EBB
        if prev_stage == STAGE_EBB and slope < 0.5:
            return STAGE_EBB

        # 过热不是"温度高"，而是"升温趋缓/滞涨"。
        # 30 分钟内从 40℃ 直冲 62℃ 属于加速段，此时按过热削仓会
        # 正好在翻转确认的窗口把仓位砍掉，与实战相反。
        if temp >= 72.0:
            return STAGE_OVERHEAT
        if temp >= 60.0 and slope < 1.0:
            return STAGE_OVERHEAT

        if temp < 35.0:
            return STAGE_ICE
        if temp < 48.0:
            return STAGE_COLD
        return STAGE_WARMING

    # -- 对外 -------------------------------------------------------------
    def update(self, sample: RegimeSample) -> MarketRegime:
        temp = float(sample.temp) if sample.temp is not None else self.compose_temp(sample)
        temp = max(0.0, min(100.0, temp))

        slope = self._slope(sample.ts, temp)
        prev_stage = self._last.stage

        self._peak_temp = max(self._peak_temp, temp)
        self._peak_limit_up = max(self._peak_limit_up, int(sample.limit_up))

        new_state = self._next_state(temp, slope, sample)
        if new_state != self._state:
            self._state = new_state
            self._state_since = sample.ts

        stage = self._stage(temp, slope, prev_stage)

        self._samples.append((sample.ts, temp))
        self._last = MarketRegime(
            temp=temp,
            stage=stage,
            slope_5m=slope,
            flip_state=self._state,
            breadth=sample.up_ratio,
            limit_up=sample.limit_up,
            limit_down=sample.limit_down,
            seal_rate=sample.seal_rate,
            peak_temp=self._peak_temp,
            updated_ts=sample.ts,
        )
        return self._last

    @property
    def regime(self) -> MarketRegime:
        return self._last

    def reset_daily(self) -> None:
        self._samples.clear()
        self._peak_temp = 0.0
        self._peak_limit_up = 0
        self._state = FLIP_IDLE
        self._state_since = 0.0
        self._last = MarketRegime()
