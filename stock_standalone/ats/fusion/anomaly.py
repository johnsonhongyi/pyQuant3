# -*- coding: utf-8 -*-
"""ats/fusion/anomaly.py — 异动形态识别（不是所有涨跌都算异动）。

用户给的定义（反复强调，作为本模块的唯一口径）：
    1. **带头作用**：它先动，别人跟着动；不是自己涨自己的。
    2. **一阳穿三线**：一根阳线同时站上 MA5/MA10/MA20，且量能配合。
    3. **超出自身走势的异常**：相对它自己过去 20 天的波动与量能，出现显著偏离，
       而不是"今天涨了 5%"这种绝对值判断。

只做形态判定，不做打分权重；输出是"命中了哪几种"，供融合层决定是否给 L3+。
所有输入都是**当下可见**的量（当日开盘价、当前价、昨日及以前的均线与波动），
不使用当日收盘数据，避免未来函数。
"""

from __future__ import annotations

from typing import Dict, List, Optional

PATTERN_PIERCE = "一阳穿三线"
PATTERN_SELF_ABNORMAL = "超出自身波动"
PATTERN_LEADERSHIP = "逆势带头"

PATTERN_LABELS = {
    PATTERN_PIERCE: "🕯️ 一阳穿三线",
    PATTERN_SELF_ABNORMAL: "⚡ 超出自身波动",
    PATTERN_LEADERSHIP: "🧭 逆势带头",
}


def detect_patterns(
    price: float,
    day_open: float,
    ma5: float,
    ma10: float,
    ma20: float,
    pct: float,
    ret_std20: float,
    vol_ratio: float,
    rs5: float,
    mkt_ret5: float,
    is_leader: bool = False,
    thresholds: Optional[Dict[str, float]] = None,
) -> List[str]:
    """返回命中的形态名列表（可能为空）。"""
    t = {
        "pierce_vol": 1.00,     # 穿三线的量能门槛（穿三线本身已足够稀有）
        "abn_z": 1.80,          # 自身波动 z 门槛
        "abn_vol": 1.50,
        "lead_rs": 1.50,        # 相对全池超额门槛
        "lead_mkt": 0.20,       # 全池 5 根收益低于此值算"别人没涨/在跌"
    }
    if thresholds:
        t.update(thresholds)

    out: List[str] = []
    if price <= 0:
        return out

    mas = [m for m in (ma5, ma10, ma20) if m > 0]
    if len(mas) == 3:
        base = min(mas)
        if price > ma5 and price > ma10 and price > ma20 and day_open < base and vol_ratio >= t["pierce_vol"]:
            out.append(PATTERN_PIERCE)

    # 自身波动 z：用当日涨幅除以它自己近 20 日的日收益标准差
    if ret_std20 > 0:
        z = pct / max(0.8, ret_std20)
        if z >= t["abn_z"] and vol_ratio >= t["abn_vol"]:
            out.append(PATTERN_SELF_ABNORMAL)

    # 带头：跑赢全池，且全池没怎么涨（别人没动/在跌）
    if rs5 >= t["lead_rs"] and (mkt_ret5 <= t["lead_mkt"] or is_leader):
        out.append(PATTERN_LEADERSHIP)

    return out


def pattern_score(patterns: List[str]) -> float:
    """形态强度 0-100，用于展示与排序辅助（不直接改 RAR）。"""
    if not patterns:
        return 0.0
    w = {PATTERN_PIERCE: 40.0, PATTERN_LEADERSHIP: 35.0, PATTERN_SELF_ABNORMAL: 30.0}
    return min(100.0, sum(w.get(p, 20.0) for p in patterns))
