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
PATTERN_VWAP_BREAK = "突破10日VWAP"
PATTERN_LATENT_BREAK = "潜伏转突破"
PATTERN_DRY_UP = "缩量转放量"
PATTERN_TWO_YANG = "两阳加速"
PATTERN_BOX10_VWAP_HOVER = "十日洗盘悬空突破"
PATTERN_STRUCTURE_CONFIRM = "结构预判验证"
PATTERN_STRUCTURE_BREAK = "结构失守"

PATTERN_LABELS = {
    PATTERN_PIERCE: "🕯️ 一阳穿三线",
    PATTERN_SELF_ABNORMAL: "⚡ 超出自身波动",
    PATTERN_LEADERSHIP: "🧭 逆势带头",
    PATTERN_VWAP_BREAK: "📈 突破10日VWAP",
    PATTERN_LATENT_BREAK: "🎯 潜伏转突破",
    PATTERN_DRY_UP: "💧 缩量转放量",
    PATTERN_TWO_YANG: "🕯️ 两阳加速",
    PATTERN_BOX10_VWAP_HOVER: "🚀 十日洗盘悬空突破",
    PATTERN_STRUCTURE_CONFIRM: "🎯 结构预判验证",
    PATTERN_STRUCTURE_BREAK: "⚠️ 结构失守",
}

# 结构失守：既不是买点也不是异动，只用于撤销结构保底，因此不参与形态强度加分
PATTERN_NEGATIVE = (PATTERN_STRUCTURE_BREAK,)


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
    vwap10: float = 0.0,
    vol_dry: float = 1.0,
    prev_pct: float = 0.0,
    is_box10_ready: bool = False,
    hi_10d: float = 0.0,
    hi_pre1: float = 0.0,
    min_vwap_cushion: float = 0.0,
    is_structure_prejudged: bool = False,
    close_over_vwap10: bool = False,
    vwap10_touch_count: int = 0,
    cushion_roll: Optional[float] = None,
    struct_status: str = "",
    thresholds: Optional[Dict[str, float]] = None,
) -> List[str]:
    """返回命中的形态名列表（可能为空）。"""
    t = {
        "pierce_vol": 1.00,     # 穿三线的量能门槛（穿三线本身已足够稀有）
        "abn_z": 1.80,          # 自身波动 z 门槛
        "abn_vol": 1.50,
        "lead_rs": 1.50,        # 相对全池超额门槛
        "lead_mkt": 0.20,       # 全池 5 根收益低于此值算"别人没涨/在跌"
        "dry_max": 0.75,        # 5日均量/20日均量 <= 此值 视为"极致缩量"
        "dry_vol_rise": 1.50,   # 缩量后放量：当前 bar 量比门槛
        "dry_pct_max": 3.50,    # 价格仍在低位：当日涨幅上限
        "dry_vwap_max": 1.01,   # 价格未远离 VWAP10（<= 1.01 倍）
        "yang_prev": 5.0,       # 两阳加速：昨日涨幅下限
        "yang_today": 3.0,      # 今日涨幅下限
        "yang_vol": 1.20,
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

    # 两阳加速：昨日已经是一根有力度的阳线，今天继续加速（用户习惯的结构）
    if prev_pct >= t["yang_prev"] and pct >= t["yang_today"] and vol_ratio >= t["yang_vol"]:
        if vwap10 <= 0 or price >= vwap10 * 0.99:
            out.append(PATTERN_TWO_YANG)

    # 缩量转放量：极致缩量之后的第一波放量，且价格还在低位
    if (vol_dry > 0 and vol_dry <= t["dry_max"]
            and vol_ratio >= t["dry_vol_rise"]
            and pct <= t["dry_pct_max"]
            and (vwap10 <= 0 or price <= vwap10 * t["dry_vwap_max"])):
        out.append(PATTERN_DRY_UP)

    # 突破 10 日 VWAP 压力区：开盘还在下方，现在站上去
    if vwap10 > 0 and price > vwap10 and day_open < vwap10:
        out.append(PATTERN_VWAP_BREAK)

    # 悬空垫统一口径：优先用【滚动窗口】值（时间可恢复），未提供时才回退到全时段最小值。
    # 两个结构形态必须同口径，否则"结构验证"能复活、"箱体悬空突破"却仍是一次性盖章。
    _eff_cushion = float(cushion_roll) if cushion_roll is not None else float(min_vwap_cushion)
    _struct_blocked = str(struct_status or "") in ("BROKEN", "EVICTED")

    # 十日洗盘蓄势突破 + 分时悬空不碰 VWAP
    if is_box10_ready and _eff_cushion >= 0.25 and not _struct_blocked:
        if (hi_10d <= 0 or price >= hi_10d * 0.998) and (hi_pre1 <= 0 or price >= hi_pre1 * 0.998):
            out.append(PATTERN_BOX10_VWAP_HOVER)

    # 结构预判验证 (果)：昨日确立尾盘站稳 10 日 VWAP 结构，今日日内悬空均线并突破昨高/昨收
    #   悬空垫改用【滚动窗口】口径：cushion_roll 只看最近 N 分钟，价格重新站上均线后会自动回升，
    #   结构因此可以"失守 → 重新成立"，不再是一锤子买卖。未提供滚动值时回退到全时段最小值（兼容旧调用）。
    #   资格严格限定为 is_structure_prejudged（设计文档支柱 2）。实测放开到 close_over_vwap10 兜底时，
    #   L4 里 1/3 来自兜底，其 MAE 中位 -3.40%、收盘相对 -2.02%，是严格组的 3.5 倍回撤 —— 属于无效异动。
    if (not _struct_blocked) and is_structure_prejudged and _eff_cushion >= 0.20:
        if hi_pre1 <= 0 or price >= hi_pre1 * 0.995:
            out.append(PATTERN_STRUCTURE_CONFIRM)

    # 结构失守：由时间轴状态机判定，用于撤销保底与提示操盘手"这个结构已经不成立"
    if str(struct_status or "") in ("BROKEN", "EVICTED"):
        out.append(PATTERN_STRUCTURE_BREAK)

    return out


def pattern_score(patterns: List[str]) -> float:
    """形态强度 0-100，用于展示与排序辅助（不直接改 RAR）。"""
    if not patterns:
        return 0.0
    w = {
        PATTERN_PIERCE: 40.0, PATTERN_LEADERSHIP: 35.0,
        PATTERN_SELF_ABNORMAL: 30.0, PATTERN_VWAP_BREAK: 35.0,
        PATTERN_LATENT_BREAK: 45.0, PATTERN_DRY_UP: 45.0, PATTERN_TWO_YANG: 40.0,
        PATTERN_BOX10_VWAP_HOVER: 60.0, PATTERN_STRUCTURE_CONFIRM: 60.0,
    }
    # 负向形态（结构失守）不计入强度，避免"越失守分越高"
    pos = [p for p in patterns if p not in PATTERN_NEGATIVE]
    if not pos:
        return 0.0
    return min(100.0, sum(w.get(p, 20.0) for p in pos))
