# -*- coding: utf-8 -*-
"""ats/fusion/market_ctx.py — 大盘情绪与市场温度的**上下文**（跨日）。

用户原话：
    "没有大盘情绪的上下文，没有市场温度的上下文，所以找不到大盘连续冰点以后
      率先走出来的结构。饿了好几天，吃的第一个包子永远是最香的；
      连续暴跌以后的启动，永远是最热的。"

问题：
    信号本身不带上下文，同样的"逆势带头"，出现在连续冰点 5 天后的第一天，
    和出现在连涨 3 天的高位，含义完全相反。判可度（可信度）不一样。

本模块提供三样东西：
    1. DayContext：每天的市场摘要（开盘/收盘/最低温度、阶段、宽度）；
    2. 连续冰点/低温天数（ice_days / cold_days）——"饿了几天"；
    3. hunger 饥饿度（1.0~1.5）——越饿，第一个启动越值钱。

全部落盘到 logs/fusion_state/market_history.json，跨日累积，不依赖当天重算。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "fusion_state", "market_history.json",
)

ICE_TEMP = 35.0      # 冰点（温度口径）
COLD_TEMP = 48.0     # 低温（温度口径）
OVERHEAT_TEMP = 60.0
# 宽度口径（更稳）：上涨占比 <=20% 算冰点，<=35% 算低温
ICE_BREADTH = 0.20
COLD_BREADTH = 0.35
HOT_BREADTH = 0.70

DAILY_CANDIDATES = (
    r"G:/tdx_all_df_300.h5",
    r"G:/tdx_last_df.h5",
)


def _is_ice(c: "DayContext") -> bool:
    if c.breadth > 0:
        return c.breadth <= ICE_BREADTH
    return c.temp_close < ICE_TEMP


def _is_cold(c: "DayContext") -> bool:
    if c.breadth > 0:
        return c.breadth <= COLD_BREADTH
    return c.temp_close < COLD_TEMP


def _is_hot(c: "DayContext") -> bool:
    if c.breadth > 0:
        return c.breadth >= HOT_BREADTH
    return c.temp_close >= OVERHEAT_TEMP


@dataclass
class DayContext:
    day: str = ""
    temp_open: float = 50.0
    temp_close: float = 50.0
    temp_min: float = 50.0
    temp_max: float = 50.0
    stage: str = ""
    breadth: float = 0.5          # 当日上涨占比
    ice_days: int = 0             # 截至前一日，连续 <35℃ 的天数
    cold_days: int = 0            # 截至前一日，连续 <48℃ 的天数
    hot_days: int = 0             # 截至前一日，连续 >=60℃ 的天数
    hunger: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day, "temp_open": round(self.temp_open, 1),
            "temp_close": round(self.temp_close, 1), "temp_min": round(self.temp_min, 1),
            "temp_max": round(self.temp_max, 1), "stage": self.stage,
            "breadth": round(self.breadth, 3), "ice_days": self.ice_days,
            "cold_days": self.cold_days, "hot_days": self.hot_days,
            "hunger": round(self.hunger, 3),
        }

    def label(self) -> str:
        """一句人话，直接进信号证据链。"""
        if self.ice_days >= 3:
            return "冰点第{}天".format(self.ice_days)
        if self.ice_days >= 1:
            return "冰点后第{}天".format(self.ice_days)
        if self.cold_days >= 2:
            return "低温第{}天".format(self.cold_days)
        if self.hot_days >= 2:
            return "高温第{}天".format(self.hot_days)
        return "常温"


def hunger_of(ice_days: int, cold_days: int) -> float:
    """饥饿度：连续冰点/低温越久，第一个启动越值钱。

    1.00（常温）~ 1.50（冰点 5 天以上）。
    刻意做温和：它是"加分项"，不是"翻倍项"，避免把深跌股的反弹全推成 L4。
    """
    h = 1.0 + 0.10 * min(max(ice_days, 0), 3) + 0.03 * min(max(cold_days, 0), 5)
    return round(min(1.5, h), 3)


class MarketHistory:
    """按日累积的市场上下文。落盘 JSON，最多保留 120 天。"""

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.days: Dict[str, DayContext] = {}
        self.load()

    # -- 持久化 -------------------------------------------------------------
    def load(self) -> int:
        if not os.path.exists(self.path):
            return 0
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return 0
        n = 0
        for d in payload.get("days") or []:
            try:
                ctx = DayContext(**{k: v for k, v in d.items() if k in DayContext.__annotations__})
            except Exception:
                continue
            self.days[ctx.day] = ctx
            n += 1
        return n

    def save(self) -> int:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        items = [self.days[k].to_dict() for k in sorted(self.days)]
        payload = {"version": 1, "days": items[-120:]}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, self.path)
        return len(payload["days"])

    # -- 查询 ---------------------------------------------------------------
    def prev_days(self, day: str) -> List[DayContext]:
        return [self.days[k] for k in sorted(self.days) if k < day]

    def context_for(self, day: str, temp_open: Optional[float] = None,
                    breadth: Optional[float] = None) -> DayContext:
        """给某一天构造上下文：冰点/低温天数来自**此前**的日摘要，不含当天（无未来函数）。

        若该日已有（日线回填的）摘要，沿用它当天的宽度与温度，否则用传入值/默认值。
        """
        stored = self.days.get(day)
        if temp_open is None:
            temp_open = stored.temp_open if stored is not None else 50.0
        if breadth is None:
            breadth = stored.breadth if stored is not None else 0.0
        prev = self.prev_days(day)
        ice = cold = hot = 0
        for c in reversed(prev):
            if _is_ice(c):
                ice += 1
            else:
                break
        for c in reversed(prev):
            if _is_cold(c):
                cold += 1
            else:
                break
        for c in reversed(prev):
            if _is_hot(c):
                hot += 1
            else:
                break
        return DayContext(
            day=day, temp_open=float(temp_open), temp_close=float(temp_open),
            temp_min=float(temp_open), temp_max=float(temp_open),
            breadth=float(breadth), ice_days=ice, cold_days=cold, hot_days=hot,
            hunger=hunger_of(ice, cold),
        )

    def record(self, ctx: DayContext) -> None:
        old = self.days.get(ctx.day)
        if old is not None and old.breadth > 0 and ctx.breadth <= 0:
            ctx.breadth = old.breadth
        self.days[ctx.day] = ctx


    # -- 用日线历史回填（36 天），不依赖当天重算 ---------------------------
    def seed_from_daily(self, path: Optional[str] = None, keep_days: int = 60) -> int:
        """从日线宽表回填每日宽度，得到真实的"连续冰点天数"。

        宽度 = 当日上涨家数占比（用 close 与前一日 close 计算）。
        温度代理 = 100 × 宽度（只用于展示与兜底，冰点判定优先用宽度）。
        """
        try:
            import numpy as np
            import pandas as pd
        except Exception:
            return 0
        p = path or next((x for x in DAILY_CANDIDATES if os.path.exists(x)), None)
        if not p:
            return 0
        try:
            df = pd.read_hdf(p, key="/all_300")
            df = df[~df.index.duplicated(keep="last")]
        except Exception:
            return 0
        if "close" not in df.columns:
            return 0
        try:
            dates = sorted({d for _, d in df.index})
        except Exception:
            return 0
        prev_close = None
        n = 0
        for d in dates:
            try:
                sub = df.xs(d, level=1)
            except Exception:
                continue
            close = sub["close"].astype(float)
            if prev_close is not None:
                common = close.index.intersection(prev_close.index)
                if len(common) >= 100:
                    pct = (close[common] / prev_close[common] - 1.0) * 100.0
                    pct = pct.replace([np.inf, -np.inf], np.nan).dropna()
                    if len(pct) >= 100:
                        b = float((pct > 0).mean())
                        day = str(d)[:10]
                        if day not in self.days:
                            self.days[day] = DayContext(
                                day=day, temp_open=100.0 * b, temp_close=100.0 * b,
                                temp_min=100.0 * b, temp_max=100.0 * b,
                                stage="SEED", breadth=round(b, 4),
                            )
                            n += 1
            prev_close = close
        return n


def render_context(ctx: DayContext) -> str:
    return "{}｜{}｜开盘{:.0f}℃ 收盘{:.0f}℃ 最低{:.0f}℃｜宽度{:.0%}｜饥饿度×{:.2f}".format(
        ctx.day, ctx.label(), ctx.temp_open, ctx.temp_close, ctx.temp_min,
        ctx.breadth, ctx.hunger,
    )
