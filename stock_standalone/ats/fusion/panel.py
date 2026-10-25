# -*- coding: utf-8 -*-
"""ats/fusion/panel.py — 信号面板：**所有信号**的统计，而不是只列前几名。

为什么需要它：
    一天的信号量是 1000 / 2000 / 3000 / 4000 条量级（结构、破位、异动、陷阱…）。
    只给"Top10 可下单"会让决策者失去两个关键信息：
        1) 今天到底有多少信号？——**信号总量本身就是拥挤度/情绪指标**；
        2) 结构分布是什么样？——全是"突破"和全是"破位"是完全不同的盘面。

面板回答四个问题：
    - 量：今天多少条信号，比最近几天多还是少（拥挤度分位）；
    - 质：级别/结构/形态/陷阱的分布；
    - 时：上午 vs 下午、按小时；
    - 漏斗：评估 → L1+ → L2+ → 入局 → 可下单，每一层损耗多少。

用法：
    from ats.fusion.panel import build_panel, render_panel
    panel = build_panel(records=res.records, entries=res.entries, meta=res.meta)
    print(render_panel(panel))
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

try:  # 结构标签以 structure.py 为准，避免两处维护
    from ats.fusion.structure import LABELS as STRUCT_LABEL
except Exception:  # pragma: no cover
    STRUCT_LABEL = {
        "MAIN_WAVE": "🌊 主升浪",
        "CHANNEL": "📐 通道内",
        "OVERSOLD_BURST": "💥 超跌突发",
        "DROP_REBOUND": "🔻 杀跌反弹",
        "OTHER": "❓ 其他",
    }


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def build_panel(
    records: List[Dict[str, Any]],
    entries: Optional[List[Dict[str, Any]]] = None,
    meta: Optional[Dict[str, Any]] = None,
    deploy_count: Optional[int] = None,
    history: Optional[Iterable[int]] = None,
) -> Dict[str, Any]:
    """把一天的记录压成面板。records 只包含 >= record_tier_min 的信号。"""
    meta = meta or {}
    entries = entries or []
    n = len(records)
    panel: Dict[str, Any] = {
        "day": meta.get("day", ""),
        "universe": meta.get("codes", 0),
        "evaluations": meta.get("evaluations", 0),
        "signals": n,
        "entries": len(entries),
        "deploy": int(deploy_count if deploy_count is not None else 0),
        "tier": Counter(),
        "structure": Counter(),
        "pattern": Counter(),
        "trap": Counter(),
        "hour": Counter(),
        "session": Counter(),
        "temp_bucket": Counter(),
        "ctx": meta.get("ctx") or {},
        "consensus": [],
        "lead_value": [],
    }

    for r in records:
        panel["tier"][int(r.get("tier") or 0)] += 1
        panel["structure"][r.get("structure") or "OTHER"] += 1
        for p in (r.get("patterns") or []):
            panel["pattern"][p] += 1
        for t in (r.get("traps") or []):
            panel["trap"][t] += 1
        tm = str(r.get("time") or "")
        if len(tm) >= 2:
            panel["hour"][tm[:2] + "时"] += 1
        panel["session"][r.get("session") or "AM"] += 1
        temp = float(r.get("temp") or 0.0)
        panel["temp_bucket"][
            "<35℃" if temp < 35 else ("35~45℃" if temp < 45 else ("45~55℃" if temp < 55 else ">=55℃"))
        ] += 1
        if r.get("consensus") is not None:
            panel["consensus"].append(float(r["consensus"]))
        if r.get("lead_value") is not None:
            panel["lead_value"].append(float(r["lead_value"]))

    # 漏斗
    tier2 = sum(v for k, v in panel["tier"].items() if k >= 2)
    tier3 = sum(v for k, v in panel["tier"].items() if k >= 3)
    panel["funnel"] = [
        ("评估次数", int(panel["evaluations"])),
        ("L1+ 信号", n),
        ("L2+ 信号", tier2),
        ("L3+ 信号", tier3),
        ("第一波入局", len(entries)),
        ("可下单", panel["deploy"]),
    ]

    # 拥挤度：今日信号量在历史中的分位（历史由调用方提供）
    hist = [int(x) for x in (history or []) if x]
    if hist and n:
        allv = sorted(hist + [n])
        panel["crowd_pct"] = round(100.0 * allv.index(n) / max(1, len(allv) - 1), 0)
        panel["crowd_avg"] = round(float(np.mean(hist)), 0)
    else:
        panel["crowd_pct"] = 0.0
        panel["crowd_avg"] = 0.0

    if panel["consensus"]:
        panel["consensus_mean"] = round(float(np.mean(panel["consensus"])), 3)
    if panel["lead_value"]:
        panel["lead_value_mean"] = round(float(np.mean(panel["lead_value"])), 3)
    return panel


def render_panel(panel: Dict[str, Any]) -> str:
    """面板的 Markdown 版本（可直接贴进日跑报告/UI）。"""
    lines = ["## 信号面板 {}".format(panel.get("day", "")), ""]
    lines.append("- 标的 {} 只｜评估 {:,} 次｜**L1+ 信号 {:,} 条**｜入局 {} 笔｜可下单 {} 笔".format(
        panel.get("universe", 0), int(panel.get("evaluations") or 0),
        int(panel.get("signals") or 0), panel.get("entries", 0), panel.get("deploy", 0)))
    if panel.get("crowd_avg"):
        lines.append("- 信号总量：今日 {:,} 条｜近期均值 {:,.0f} 条｜拥挤度分位 {:.0f}%".format(
            int(panel.get("signals") or 0), panel["crowd_avg"], panel.get("crowd_pct", 0)))
    ctx = panel.get("ctx") or {}
    if ctx:
        lines.append("- 大盘上下文：{}｜开盘 {:.0f}℃ → 收盘 {:.0f}℃（最低 {:.0f}℃）｜宽度 {:.0%}｜饥饿度 ×{:.2f}".format(
            ctx.get("stage") or "-", float(ctx.get("temp_open") or 0), float(ctx.get("temp_close") or 0),
            float(ctx.get("temp_min") or 0), float(ctx.get("breadth") or 0), float(ctx.get("hunger") or 1.0)))
        lines.append("- 连续冰点 {} 天｜低温 {} 天｜高温 {} 天".format(
            ctx.get("ice_days", 0), ctx.get("cold_days", 0), ctx.get("hot_days", 0)))
    if panel.get("consensus_mean") is not None:
        lines.append("- 趋同度均值 {:.0%}｜带头价值均值 ×{:.2f}（低温低趋同时更高）".format(
            panel["consensus_mean"], panel.get("lead_value_mean", 0.0)))
    lines.append("")

    lines.append("### 漏斗（每一层损耗）")
    lines.append("")
    lines.append("| 层 | 数量 | 保留率 |")
    lines.append("|---|---|---|")
    base = None
    for name, v in panel.get("funnel") or []:
        if base is None:
            base = v or 1
        lines.append("| {} | {:,} | {:.1f}% |".format(name, v, _pct(v, base)))
    lines.append("")

    lines.append("### 级别分布")
    lines.append("")
    lines.append("| 级别 | 条数 | 占比 |")
    lines.append("|---|---|---|")
    n = max(1, int(panel.get("signals") or 0))
    for k in sorted(panel["tier"], reverse=True):
        lines.append("| L{} | {:,} | {:.1f}% |".format(k, panel["tier"][k], _pct(panel["tier"][k], n)))
    lines.append("")

    lines.append("### 结构分布")
    lines.append("")
    lines.append("| 结构 | 条数 | 占比 |")
    lines.append("|---|---|---|")
    for k, v in panel["structure"].most_common():
        lines.append("| {} | {:,} | {:.1f}% |".format(STRUCT_LABEL.get(k, k), v, _pct(v, n)))
    lines.append("")

    if panel["pattern"]:
        lines.append("### 形态分布（同一票多形态重复计）")
        lines.append("")
        lines.append("| 形态 | 次数 | 占比 |")
        lines.append("|---|---|---|")
        for k, v in panel["pattern"].most_common():
            lines.append("| {} | {:,} | {:.1f}% |".format(k, v, _pct(v, n)))
        lines.append("")

    if panel["trap"]:
        lines.append("### 陷阱分布（诱多）")
        lines.append("")
        lines.append("| 陷阱 | 次数 |")
        lines.append("|---|---|")
        for k, v in panel["trap"].most_common():
            lines.append("| {} | {:,} |".format(k, v))
        lines.append("")

    lines.append("### 时间分布")
    lines.append("")
    lines.append("| 时段 | 条数 | 占比 |")
    lines.append("|---|---|---|")
    for k in ("AM", "PM"):
        v = panel["session"].get(k, 0)
        lines.append("| {} | {:,} | {:.1f}% |".format("上午" if k == "AM" else "下午", v, _pct(v, n)))
    for k in sorted(panel["hour"]):
        lines.append("| {} | {:,} | {:.1f}% |".format(k, panel["hour"][k], _pct(panel["hour"][k], n)))
    lines.append("")

    if panel["temp_bucket"]:
        lines.append("### 温度分布")
        lines.append("")
        lines.append("| 温度 | 条数 | 占比 |")
        lines.append("|---|---|---|")
        for k in ("<35℃", "35~45℃", "45~55℃", ">=55℃"):
            v = panel["temp_bucket"].get(k, 0)
            if v:
                lines.append("| {} | {:,} | {:.1f}% |".format(k, v, _pct(v, n)))
        lines.append("")
    return "\n".join(lines)


def lead_value_table(entries: List[Dict[str, Any]], key: str = "lead_value") -> List[Dict[str, Any]]:
    """按带头价值分档统计入局结果（验证"低温低趋同才值钱"）。"""
    buckets = [(0.0, 0.45), (0.45, 0.60), (0.60, 0.75), (0.75, 1.01)]
    out = []
    for lo, hi in buckets:
        g = [e for e in entries if lo <= float(e.get(key) or 0.0) < hi]
        if not g:
            continue
        t1 = [float(e["t1"]) for e in g if e.get("t1") is not None]
        out.append({
            "range": "{:.2f}~{:.2f}".format(lo, min(hi, 1.0)),
            "n": len(g),
            "close": round(float(np.mean([float(e.get("close_ret") or 0) for e in g])), 2),
            "t1": round(float(np.mean(t1)), 2) if t1 else 0.0,
            "win": round(100.0 * float(np.mean([1.0 if x > 0 else 0.0 for x in t1])), 0) if t1 else 0.0,
        })
    return out
