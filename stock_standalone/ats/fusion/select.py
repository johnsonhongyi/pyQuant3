# -*- coding: utf-8 -*-
"""ats/fusion/select.py — 每日收敛层：把几千个信号压成"每个分类最多 3~5 个"。

回答用户的问题：能不能给出「刚启动 / 蓄势 / 加速 / 止损 / 震仓」这几类答案？
    - 每个分类最多 3~5 个（宁缺毋滥）；
    - "共振"（赛道排名靠前 + 个股结构成立）才算可操作；
    - 赛道弱但个股强的，单独列为"独立观察"，不占可操作名额。

输入：某日回放的 records（含 tier/rar/patterns/structure/sector_rank/axes）。
输出：分好类的候选清单 + 每类名额约束。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from ats.fusion.anomaly import (
    PATTERN_DRY_UP,
    PATTERN_LATENT_BREAK,
    PATTERN_PIERCE,
    PATTERN_TWO_YANG,
    PATTERN_VWAP_BREAK,
)
from ats.fusion.structure import CHANNEL, MAIN_WAVE, OVERSOLD_BURST, DROP_REBOUND

# 阶段
JUST_START = "刚启动"
ACCUMULATING = "蓄势"
ACCELERATING = "加速"
SHAKEOUT = "震仓"
EXIT_WARN = "止损/离场"

STAGE_ORDER = (ACCELERATING, JUST_START, ACCUMULATING, SHAKEOUT, EXIT_WARN)


def _has(r: Dict[str, Any], *names: str) -> bool:
    ps = set(r.get("patterns") or [])
    return any(n in ps for n in names)


def classify_stage(r: Dict[str, Any]) -> Optional[str]:
    """把一个决策归到某个阶段；不属于任何阶段返回 None。"""
    pats = set(r.get("patterns") or [])
    st = r.get("structure") or ""
    pct = float(r.get("pct") or 0.0)
    rar = float(r.get("rar") or 0.0)

    # 止损/离场：已经跌破 10 日 VWAP 且走弱（针对持仓，不是开仓）
    if r.get("below_vwap10") and pct <= -1.0:
        return EXIT_WARN

    # 加速：主升浪里继续加速
    if st == MAIN_WAVE and (PATTERN_TWO_YANG in pats or PATTERN_LATENT_BREAK in pats):
        return ACCELERATING

    # 刚启动：今日首次站上 10 日 VWAP 或缩量后第一波放量，价格还不高
    if (PATTERN_VWAP_BREAK in pats or PATTERN_DRY_UP in pats) and pct <= 3.5:
        return JUST_START

    # 蓄势：通道内 + 极致缩量 + 贴着 VWAP10
    if st == CHANNEL and float(r.get("vol_dry") or 1.0) <= 0.85 and abs(float(r.get("dist_ma20") or 0.0)) <= 3.0:
        return ACCUMULATING

    # 震仓：日内冲高后回踩、仍站在均价上方（洗盘特征）
    if float(r.get("pullback_pct") or 0.0) >= 1.2 and r.get("above_vwap") and pct > -1.0:
        return SHAKEOUT

    return None


def _score(r: Dict[str, Any]) -> float:
    """同一阶段内的排序分：结构强度 + 形态 + 相对强度。"""
    ax = r.get("axes") or {}
    return (
        float(r.get("rar") or 0.0) * 0.5
        + float(ax.get("relative") or 50.0) * 0.3
        + float(r.get("pattern_score") or 0.0) * 0.2
    )


def select_day(
    records: Iterable[Dict[str, Any]],
    per_stage: int = 3,
    resonance_min: float = 0.60,
) -> Dict[str, Any]:
    """输出：{可操作(共振), 独立观察, 按阶段分组}。"""
    buckets: Dict[str, List[Dict[str, Any]]] = {s: [] for s in STAGE_ORDER}
    seen: set = set()

    for r in records:
        code = r.get("code")
        if not code or code in seen:
            continue
        stage = classify_stage(r)
        if not stage:
            continue
        seen.add(code)
        item = dict(r)
        item["stage"] = stage
        item["score"] = round(_score(r), 2)
        buckets[stage].append(item)

    resonance, independent = [], []
    for stage in STAGE_ORDER:
        rows = sorted(buckets[stage], key=lambda x: -x["score"])
        if stage == EXIT_WARN:
            buckets[stage] = rows[: max(per_stage, 5)]
            continue
        keep_res = [r for r in rows if float(r.get("sector_rank") or 0.0) >= resonance_min]
        keep_ind = [r for r in rows if float(r.get("sector_rank") or 0.0) < resonance_min]
        buckets[stage] = keep_res[:per_stage] + keep_ind[: max(1, per_stage - 2)]
        resonance.extend(keep_res[:per_stage])
        independent.extend(keep_ind[: max(1, per_stage - 2)])

    return {
        "stages": buckets,
        "actionable": resonance[: per_stage * 2],
        "independent": independent[: per_stage * 2],
        "count": sum(len(v) for v in buckets.values()),
    }


def render_selection(sel: Dict[str, Any], day: str = "") -> str:
    lines = ["## 每日收敛清单 {}".format(day), ""]
    lines.append("- 可操作（赛道共振）：{} 只｜独立观察：{} 只｜合计 {} 只".format(
        len(sel["actionable"]), len(sel["independent"]), sel["count"]))
    lines.append("")

    def _table(title: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        lines.append("### {}".format(title))
        lines.append("| 代码 | 时间 | 级别 | RAR | 涨幅 | 赛道 | 赛道排名 | 结构 | 形态 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            lines.append("| {} | {} | L{} | {} | {:+.1f}% | {} | {} | {} | {} |".format(
                r["code"], r.get("time", ""), r.get("tier", 0), r.get("rar", 0),
                float(r.get("pct") or 0), r.get("sector", ""), r.get("sector_rank", 0),
                r.get("structure", ""), "、".join(r.get("patterns") or []) or "-"))
        lines.append("")

    _table("✅ 可操作（赛道共振）", sel["actionable"])
    _table("👀 独立观察（赛道不强、个股独立）", sel["independent"])
    for stage in STAGE_ORDER:
        if stage in (ACCELERATING, JUST_START, ACCUMULATING):
            _table("📌 {}（分类明细）".format(stage), sel["stages"].get(stage) or [])
    if sel["stages"].get(EXIT_WARN):
        _table("⛔ 止损/离场提示", sel["stages"][EXIT_WARN])
    return "\n".join(lines)
