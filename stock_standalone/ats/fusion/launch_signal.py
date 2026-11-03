# -*- coding: utf-8 -*-
"""ATS 融合梯度早盘两类启动结构；仅生成观察证据，不更改梯度/下单。

A: 既有跨日结构 -> 回踩 10 日 VWAP 附近、不破昨日低点 -> 再加速。
B: 20 日下跌 -> 当日从 10 日 VWAP 下方放量 V 形收复。
这里只读当前时点可见的日线锚点和实时字段，阈值需用逐笔/分钟回放校准。
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


def classify_launch(event: Any, day_open: float, prev_low: float = 0.0,
                    prev_high: float = 0.0, prejudged: bool = False,
                    struct_status: str = "") -> Dict[str, Any]:
    """返回可解释的 A/B 预警，绝不以缺失数据猜测确认。"""
    try:
        ts = float(event.ts)
        local = time.localtime(ts)
        minute_of_day = local.tm_hour * 60 + local.tm_min
    except (AttributeError, TypeError, ValueError, OverflowError):
        return {}
    if not (9 * 60 + 30 <= minute_of_day < 11 * 60 + 30):
        return {}

    if ("pct" in (event.extra.get("missing") or ())
            or "vwap" in (event.extra.get("missing") or ())
            or event.price <= 0 or event.vwap <= 0 or event.vwap_10d <= 0
            or event.day_low <= 0 or day_open <= 0
            or (event.freshness_s > 20)):
        return {}
    price, v10, vwap = float(event.price), float(event.vwap_10d), float(event.vwap)
    bias = (price / vwap - 1.0) * 100
    vwap10_bias = (price / v10 - 1.0) * 100
    if struct_status in ("BROKEN", "EVICTED"):
        prejudged = False

    # A 型必须有前一交易日低点。不能把缺失的前低默认为零并宣称“不破前低”。
    a_shape = bool(prejudged and struct_status == "CONFIRMED" and prev_low > 0
                   and event.day_low >= prev_low * 0.998
                   and v10 * 0.99 <= event.day_low <= v10 * 1.02
                   and price >= v10)
    # B 型必须有截至昨日的 5/20 日下跌证据，并在盘中低于 10 日 VWAP 后收复成本线。
    # 当天最低价和开盘价只使用当前时点已公开的分钟线。
    b_watch = bool(event.ret20d <= -5.0 and event.ret5d <= -3.0
                   and day_open < v10 * 0.995 and event.day_low < v10
                   and price >= v10 and price >= event.day_low * 1.01
                   and event.pct >= 0.0 and event.pct <= 7.0)

    kind = "A" if a_shape else "B" if b_watch else ""
    if not kind:
        return {}
    label = "A型·10日VWAP回踩再加速" if kind == "A" else "B型·单日V形收复"
    base_reason = ("跨日结构已确认，回踩未破昨日低点" if kind == "A"
                   else "前20日下跌，当日由10日VWAP下方收复")
    slope = _number(event.extra.get("vwap_slope_5m_pct"))
    criteria = bool(
        price >= v10 and price >= vwap and 0 <= bias <= 2.5
        and 0 <= vwap10_bias <= 2.5
        and 0 <= event.pct <= 7.0
        and event.sector_resonance >= 58.0
        and event.vol_ratio >= 2.0
        and event.velocity_pct >= 0.2
        and slope is not None and slope > 0.0
    )
    if criteria:
        status = "CONFIRMED"
        reason = base_reason + "；板块共振、放量及分时加速同步"
    elif bias > 2.5 or vwap10_bias > 2.5 or event.pct > 7.0:
        status, reason = "WATCH", "已偏离分时/10日VWAP计划入场区，禁止追高"
    elif slope is None or slope <= 0.0:
        status, reason = "WATCH", base_reason + "；等待分钟 VWAP 斜率转正"
    else:
        status, reason = "WATCH", base_reason + "；等待板块、成交与分时VWAP共同确认"
    return {
        "type": kind, "label": label, "status": status, "reason": reason,
        "vwap10": round(v10, 3), "vwap": round(vwap, 3),
        "bias_pct": round(bias, 2), "sector_resonance": round(float(event.sector_resonance), 1),
        "vwap10_bias_pct": round(vwap10_bias, 2),
        "vol_ratio": round(float(event.vol_ratio), 2),
        "velocity_pct": round(float(event.velocity_pct), 3),
        "vwap_slope_5m_pct": round(slope, 4) if slope is not None else None,
        "permission": "WATCH",  # 只有融合梯度风险门禁通过后才可改为人工确认许可
    }


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError, OverflowError):
        return None
