# -*- coding: utf-8 -*-
"""ats/fusion/structure.py — 个股结构分类（先分类，再谈信号）。

用户的核心批评：**所有票都堆在一堆**，所以信号好坏互相抵消，看不出规律。
结构必须分层看，而且**时间周期越长越有效**。本模块按日线（截至昨日）把标的分为：

    MAIN_WAVE      主升浪结构：均线多头、站上 MA20、20 日涨幅可观、贴近 20 日高点
    CHANNEL        通道结构：20 日涨跌幅不大、价格在 MA20 附近（震荡/通道内）
    DROP_REBOUND   大幅杀跌后的缩量反弹：近 10 日跌幅明显、量能萎缩、今日转红
    OVERSOLD_BURST 长期超跌的突发：远离 MA20、20 日跌幅大、今日放量
    OTHER          其余

分类只用截至昨日的数据 + 当日价格，不使用当日收盘，避免未来函数。
"""

from __future__ import annotations

from typing import Any, Dict

MAIN_WAVE = "MAIN_WAVE"
CHANNEL = "CHANNEL"
DROP_REBOUND = "DROP_REBOUND"
OVERSOLD_BURST = "OVERSOLD_BURST"
OTHER = "OTHER"

LABELS = {
    MAIN_WAVE: "🌊 主升浪",
    CHANNEL: "📐 通道内",
    DROP_REBOUND: "🔻 杀跌缩量反弹",
    OVERSOLD_BURST: "💥 超跌突发",
    OTHER: "❓ 其他",
}


def classify(dc: Dict[str, Any], price: float, pct: float) -> str:
    """dc: DailyContext.asof() 的结果；price/pct: 当下价格与当日涨幅。"""
    if not dc or price <= 0:
        return OTHER

    ma5 = float(dc.get("ma5", 0.0))
    ma10 = float(dc.get("ma10", 0.0))
    ma20 = float(dc.get("ma20", 0.0))
    ret5 = float(dc.get("ret5d", 0.0))
    ret20 = float(dc.get("ret20d", 0.0))
    days_high = float(dc.get("days_since_high", 999.0))
    dist_ma20 = float(dc.get("dist_ma20_pct", 0.0))
    vol_dry = float(dc.get("vol_dry", 1.0) or 1.0)

    # 1) 主升浪：多头排列 + 站上 MA20 + 20 日有涨幅 + 贴近高点
    if ma5 > 0 and ma10 > 0 and ma20 > 0:
        if price > ma20 and ma5 >= ma10 >= ma20 and ret20 >= 5.0 and days_high <= 6.0:
            return MAIN_WAVE

    # 2) 长期超跌突发：远离 MA20 + 20 日跌幅大（今日放量由形态层判断）
    if dist_ma20 <= -12.0 or ret20 <= -18.0:
        return OVERSOLD_BURST

    # 3) 杀跌后缩量反弹：近 10 日跌幅明显、量能萎缩、今日转红
    if ret5 <= -6.0 and vol_dry <= 0.95 and pct > 0:
        return DROP_REBOUND

    # 4) 通道内：20 日涨跌幅不大、价格贴着 MA20
    if ma20 > 0 and abs(ret20) <= 10.0 and abs(dist_ma20) <= 6.0:
        return CHANNEL

    return OTHER


def label(name: str) -> str:
    return LABELS.get(name, name)
