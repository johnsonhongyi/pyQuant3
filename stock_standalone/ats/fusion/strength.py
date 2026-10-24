# -*- coding: utf-8 -*-
"""ats/fusion/strength.py — 强势排序（当机立断用），与 RAR（观察参与）并列。

RAR 的目标是"低风险可参与"：贴近均价、止损近、不追高。
涨幅榜的特征相反：远离均价、不断新高、尾段加速。
两者是反向目标，必须分成两套清单，不能混用一个分数。

strength_rank = 当日强度分位(40) + 赛道强度(25) + 点火(20) + RAR(15)
"""

from __future__ import annotations

from typing import Any, Dict, List


def _pctile(values: List[float], x: float) -> float:
    if not values:
        return 0.5
    lo = sum(1 for v in values if v < x)
    return lo / max(1, len(values) - 1) if len(values) > 1 else 0.5


def rank_strength(events: List[Dict[str, Any]], top: int = 20) -> List[Dict[str, Any]]:
    """按强势分排序（用于实时下单清单）。"""
    if not events:
        return []
    pcts = [float(e.get("pct") or 0.0) for e in events]
    out = []
    for e in events:
        s = (
            40.0 * _pctile(pcts, float(e.get("pct") or 0.0))
            + 25.0 * float(e.get("sector_rank") or 0.0)
            + 20.0 * float(e.get("ignition") or 0.0) / 100.0
            + 15.0 * float(e.get("rar") or 0.0) / 100.0
        )
        item = dict(e)
        item["strength"] = round(s, 2)
        out.append(item)
    out.sort(key=lambda x: -x["strength"])
    return out[:top]


def render_strength(rows: List[Dict[str, Any]], day: str = "") -> str:
    if not rows:
        return "## 强势清单 {}\n\n- 无\n".format(day)
    lines = ["## 强势清单（当机立断） {}".format(day), ""]
    lines.append("| # | 代码 | 名称 | 时间 | 强势分 | 涨幅 | 赛道 | 形态 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        lines.append("| {} | {} | {} | {} | {} | {:+.1f}% | {} | {} |".format(
            i, r.get("code", ""), r.get("name", ""), r.get("time", ""), r.get("strength", 0),
            float(r.get("pct") or 0), r.get("sector", ""), "、".join(r.get("patterns") or []) or "-"))
    lines.append("")
    return "\n".join(lines)
