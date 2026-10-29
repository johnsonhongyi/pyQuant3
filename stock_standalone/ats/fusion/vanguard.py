# -*- coding: utf-8 -*-
"""ats/fusion/vanguard.py — 排头兵 / 冲锋队 / 夺旗 / 跟风：板块内的领先度。

用户原话：
    "跟风的都是没有导向性的，要的就是排头兵、冲锋队、夺旗的生力军。"

为什么"涨幅"分不出这两种票：
    同一时刻，板块龙头涨 6%、跟风票也涨 6%，涨幅一模一样。
    差别只在**时间**：龙头 09:35 就动了，跟风票 10:20 才动。
    到 10:20 才看到跟风票"放量拉升"，那不是信号，那是别人吃完的残羹。

本模块只用一件事做区分：**谁先动**。
    排头兵  板块内第 1~2 个启动，且领先板块首动 <=5 分钟
    冲锋队  板块内第 3~5 个启动，延迟 <=15 分钟，且攻击速度快
    夺旗    板块内第一个突破前高 / 10 日 VWAP —— 旗手
    跟风    板块首动 30 分钟之后才启动，或排名 >=8
    无导向  板块没起来（启动家数 <3），孤军奋战

用法（回放/实时都一样）：
    clock = SectorClock()
    info = clock.observe(code, sector, ts, pct, breakout=True/False)
    # info.rank / info.lead_gap_min / info.label / info.score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

LABEL_PRIME = "总龙头"
LABEL_VANGUARD = "排头兵"
LABEL_STRIKE = "冲锋队"
LABEL_FLAG = "夺旗"
LABEL_FOLLOW = "跟风"
LABEL_LONE = "无导向"

# 启动判定：涨幅首次达到该值
LAUNCH_PCT = 1.0

LABEL_SCORE = {
    LABEL_PRIME: 98.0,
    LABEL_VANGUARD: 92.0,
    LABEL_FLAG: 88.0,
    LABEL_STRIKE: 78.0,
    LABEL_LONE: 55.0,
    LABEL_FOLLOW: 30.0,
}


@dataclass
class LeadInfo:
    code: str = ""
    sector: str = ""
    rank: int = 0                 # 板块内第几个启动（1 = 排头兵）
    lead_gap_min: float = 0.0     # 相对板块首动的延迟（分钟；0 = 自己就是首动）
    sector_n: int = 0             # 该板块已启动家数
    is_flag: bool = False         # 是否板块内第一个突破（夺旗）
    is_prime_leader: bool = False # 是否是昨日率先强势突破带动板块的总龙头 (如电科蓝天)
    temporal_strength: float = 1.0 # 时间结构强度 0.0~1.0 (启动早=1.0，滞后跟风衰减)
    label: str = LABEL_LONE
    score: float = 50.0

    def to_dict(self) -> Dict[str, object]:
        return {
            "rank": self.rank, "lead_gap_min": round(self.lead_gap_min, 1),
            "sector_n": self.sector_n, "is_flag": self.is_flag,
            "is_prime_leader": self.is_prime_leader,
            "temporal_strength": round(self.temporal_strength, 2),
            "label": self.label, "lead_score": round(self.score, 1),
        }


class SectorClock:
    """板块启动时钟：记录每个板块成员的首次启动时间与顺序。"""

    def __init__(self, launch_pct: float = LAUNCH_PCT):
        self.launch_pct = float(launch_pct)
        self._launch: Dict[Tuple[str, str], float] = {}          # (sector, code) -> ts
        self._order: Dict[str, List[Tuple[float, str]]] = {}     # sector -> [(ts, code)]
        self._rank: Dict[str, Dict[str, int]] = {}               # sector -> {code: rank}，避免每根 bar 扫列表
        self._flag: Dict[str, str] = {}                          # sector -> 首个夺旗 code
        self._day = ""

    def reset(self, day: str = "") -> None:
        self._launch.clear()
        self._order.clear()
        self._rank.clear()
        self._flag.clear()
        self._day = day

    def observe(
        self,
        code: str,
        sector: str,
        ts: float,
        pct: float,
        breakout: bool = False,
        is_prime_leader: bool = False,
    ) -> LeadInfo:
        """喂一根 bar，返回该票此刻在板块内的领先度。"""
        code = str(code).zfill(6)
        sector = sector or ""
        info = LeadInfo(code=code, sector=sector)

        # 板块缺失：无法判断领先度，给中性
        if not sector:
            info.label = LABEL_LONE
            info.score = LABEL_SCORE[LABEL_LONE]
            return info

        key = (sector, code)
        first_ts = self._launch.get(key)
        if first_ts is None:
            if float(pct) < self.launch_pct:
                # 还没启动：返回当前板块状态，rank=0
                order = self._order.get(sector) or []
                info.sector_n = len(order)
                info.label = LABEL_LONE
                info.score = LABEL_SCORE[LABEL_LONE]
                return info
            first_ts = float(ts)
            self._launch[key] = first_ts
            order = self._order.setdefault(sector, [])
            order.append((first_ts, code))
            self._rank.setdefault(sector, {})[code] = len(order)

        order = self._order.get(sector) or []
        rank = self._rank.get(sector, {}).get(code, len(order))
        sector_first_ts = order[0][0] if order else first_ts
        lead_gap = max(0.0, (first_ts - sector_first_ts) / 60.0)

        # 夺旗：板块内第一个突破（前高 / 10 日 VWAP）的票
        if breakout and sector not in self._flag:
            self._flag[sector] = code
        is_flag = self._flag.get(sector) == code

        info.rank = rank
        info.lead_gap_min = lead_gap
        info.sector_n = len(order)
        info.is_flag = is_flag
        info.is_prime_leader = is_prime_leader
        info.label, info.score, info.temporal_strength = classify(rank, lead_gap, len(order), is_flag, is_prime_leader)
        return info


def classify(rank: int, lead_gap_min: float, sector_n: int, is_flag: bool, is_prime_leader: bool = False) -> Tuple[str, float, float]:
    """把"第几个动 / 落后多久 / 板块几家在动 / 是否夺旗 / 是否总龙头"翻译成标签、分数与时间结构强度。"""
    # 时间结构强度：启动早为 1.0，随滞后分钟数递减
    if is_prime_leader:
        return LABEL_PRIME, LABEL_SCORE[LABEL_PRIME], 1.0

    if rank == 1 and lead_gap_min <= 2.0:
        temporal_strength = 1.0
    elif rank <= 2 and lead_gap_min <= 5.0:
        temporal_strength = 0.90
    elif rank <= 5 and lead_gap_min <= 15.0:
        temporal_strength = 0.70
    elif lead_gap_min <= 30.0:
        temporal_strength = 0.45
    else:
        temporal_strength = 0.25

    if sector_n < 3:
        # 板块只有 1~2 家在动：孤军
        label = LABEL_LONE
        score = LABEL_SCORE[LABEL_LONE]
        if is_flag:
            score += 8.0
        return label, min(100.0, score), temporal_strength

    if is_flag and rank <= 3:
        return LABEL_FLAG, LABEL_SCORE[LABEL_FLAG], max(0.85, temporal_strength)

    if rank <= 2 and lead_gap_min <= 5.0:
        return LABEL_VANGUARD, LABEL_SCORE[LABEL_VANGUARD], max(0.90, temporal_strength)

    if rank <= 5 and lead_gap_min <= 15.0:
        return LABEL_STRIKE, LABEL_SCORE[LABEL_STRIKE], temporal_strength

    if lead_gap_min >= 30.0 or rank >= 8:
        return LABEL_FOLLOW, LABEL_SCORE[LABEL_FOLLOW], min(0.35, temporal_strength)

    # 中间地带（第 6~7 个、落后 15~30 分钟）：中性偏弱
    return LABEL_STRIKE, LABEL_SCORE[LABEL_STRIKE] - 12.0, temporal_strength


def is_follower(info: LeadInfo) -> bool:
    return info.label == LABEL_FOLLOW


def render_lead_table(rows: List[Dict]) -> str:
    """按领先度分档统计（复盘用）。"""
    from collections import Counter

    if not rows:
        return ""
    c: Counter = Counter()
    for r in rows:
        c[r.get("lead_label") or "-"] += 1
    order = [LABEL_VANGUARD, LABEL_FLAG, LABEL_STRIKE, LABEL_LONE, LABEL_FOLLOW]
    lines = ["| 领先度 | 笔数 |", "|---|---|"]
    for k in order:
        if c.get(k):
            lines.append("| {} | {} |".format(k, c[k]))
    return "\n".join(lines)
