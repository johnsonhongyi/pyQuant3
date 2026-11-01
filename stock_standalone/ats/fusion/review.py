# -*- coding: utf-8 -*-
"""ats/fusion/review.py — 影子期复盘与分档阈值建议（闭环的最后一环）。

闭环链路：
    实时评估 -> 影子 JSONL -> 本模块汇总 -> 阈值建议 -> 回写 config/fusion_ladder.json

设计原则：
    - 只读日志，不改任何运行时状态；
    - 样本不足时明确说"不足"，不给出看似精确的阈值；
    - 阈值按 RAR 实际分位给出，而不是拍脑袋的固定 82/72/62/50。

用法：
    python -m ats.fusion.review --day 2026-10-23
    python -m ats.fusion.review --day 2026-10-23 --write-cut   # 打印建议配置片段
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from ats.fusion.adapter import today_str


def _app_root() -> str:
    try:
        from sys_utils import get_app_root  # type: ignore

        return get_app_root()
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def log_dir(root: Optional[str] = None) -> str:
    return os.path.join(root or _app_root(), "logs", "fusion_shadow")


def load_records(day: str = "", root: Optional[str] = None) -> List[Dict[str, Any]]:
    """读取某日（默认今日）影子日志；坏行跳过，不抛异常。"""
    day = day or today_str()
    from ats.fusion.shadow_io import day_paths, log_directories, read_paths
    paths = day_paths(log_directories(log_dir(root)), day)
    rows, errors = read_paths(paths)
    if errors:
        import logging
        logging.getLogger(__name__).warning("影子复盘读取异常: %s", errors[:5])
    return rows


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    data = sorted(values)
    if len(data) == 1:
        return float(data[0])
    pos = (len(data) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(data) - 1)
    frac = pos - lo
    return float(data[lo] * (1 - frac) + data[hi] * frac)


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按级别、分歧、缺失字段、否决原因汇总。"""
    n = len(records)
    tiers = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    divergence = {"both_buy": 0, "fusion_only": 0, "legacy_only": 0, "both_skip": 0}
    veto_reasons: Dict[str, int] = {}
    missing: Dict[str, int] = {}
    rar_by_tier: Dict[int, List[float]] = {0: [], 1: [], 2: [], 3: [], 4: []}
    actionable = 0

    for rec in records:
        fusion = rec.get("fusion") or {}
        tier = int(fusion.get("tier") or 0)
        tiers[tier] = tiers.get(tier, 0) + 1
        rar = float(fusion.get("rar") or 0.0)
        rar_by_tier[tier].append(rar)

        div = str(rec.get("divergence") or "")
        if div in divergence:
            divergence[div] += 1

        if fusion.get("veto_reason"):
            key = str(fusion["veto_reason"]).split("(")[0]
            veto_reasons[key] = veto_reasons.get(key, 0) + 1

        for key in rec.get("missing") or []:
            missing[key] = missing.get(key, 0) + 1

        if tier >= 1 and not fusion.get("veto_reason"):
            actionable += 1

    warnings: List[str] = []
    if n:
        l4_share = tiers.get(4, 0) / n
        if l4_share > 0.15:
            warnings.append("L4 占比 {:.1%} 超过 15%，建议按分位上调 l4 阈值".format(l4_share))
        if actionable / n > 0.90:
            warnings.append("可参与占比 {:.1%} 过高，梯度失去区分度".format(actionable / n))
    for key in ("vwap", "taker_buy_ratio", "bid_pressure", "structure_clarity"):
        if n and missing.get(key, 0) / n > 0.20:
            warnings.append("{} 缺失率 {:.0%}，该轴评分不可信".format(key, missing[key] / n))

    return {
        "records": n,
        "actionable": actionable,
        "actionable_share": round(actionable / n, 4) if n else 0.0,
        "tier_counts": tiers,
        "tier_share": {k: round(v / n, 4) for k, v in tiers.items()} if n else {},
        "divergence": divergence,
        "veto_reasons": dict(sorted(veto_reasons.items(), key=lambda x: -x[1])[:10]),
        "missing": dict(sorted(missing.items(), key=lambda x: -x[1])),
        "warnings": warnings,
        "rar_stats": {
            k: {
                "n": len(v),
                "p50": round(_percentile(v, 0.50), 1),
                "p90": round(_percentile(v, 0.90), 1),
            }
            for k, v in rar_by_tier.items()
            if v
        },
    }


def suggest_cuts(records: List[Dict[str, Any]], min_samples: int = 30) -> Dict[str, Any]:
    """按未否决样本的 RAR 分位给分档阈值建议。

    L4 取 p90、L3 取 p70、L2 取 p45、L1 取 p20 —— 与"L4 是历史前 10%"的设计一致。
    样本不足时返回 ok=False，不制造精确幻觉。
    """
    rars = [
        float((rec.get("fusion") or {}).get("rar") or 0.0)
        for rec in records
        if not (rec.get("fusion") or {}).get("veto_reason")
        and float((rec.get("fusion") or {}).get("rar") or 0.0) > 0
    ]
    if len(rars) < min_samples:
        return {
            "ok": False,
            "reason": "有效样本 {} < {}，暂不给阈值建议".format(len(rars), min_samples),
            "samples": len(rars),
        }

    cuts = {
        "l4": round(_percentile(rars, 0.90), 1),
        "l3": round(_percentile(rars, 0.70), 1),
        "l2": round(_percentile(rars, 0.45), 1),
        "l1": round(_percentile(rars, 0.20), 1),
    }
    return {"ok": True, "samples": len(rars), "tier_cuts": cuts}


def render_markdown(summary: Dict[str, Any], cuts: Dict[str, Any], day: str = "") -> str:
    lines = ["# 融合层影子复盘 {}".format(day or today_str()), ""]
    lines.append("- 记录数：{records}｜可参与（L1+ 且未否决）：{actionable}（{share:.1%}）".format(
        records=summary["records"], actionable=summary["actionable"], share=summary["actionable_share"]))
    lines.append("")
    lines.append("## 级别分布")
    lines.append("| 级别 | 条数 | 占比 | RAR p50 | RAR p90 |")
    lines.append("|---|---|---|---|---|")
    for tier in (4, 3, 2, 1, 0):
        stat = summary["rar_stats"].get(tier) or summary["rar_stats"].get(str(tier)) or {}
        lines.append("| L{} | {} | {:.1%} | {} | {} |".format(
            tier,
            summary["tier_counts"].get(tier, summary["tier_counts"].get(str(tier), 0)),
            summary["tier_share"].get(tier, summary["tier_share"].get(str(tier), 0.0)),
            stat.get("p50", "-"),
            stat.get("p90", "-"),
        ))
    lines.append("")
    lines.append("## 与现有逻辑的分歧")
    div = summary["divergence"]
    lines.append("- 双方都买：{}｜仅融合层买：{}｜仅现有逻辑买：{}｜都不买：{}".format(
        div["both_buy"], div["fusion_only"], div["legacy_only"], div["both_skip"]))
    lines.append("")
    if summary.get("warnings"):
        lines.append("## ⚠️ 告警")
        for item in summary["warnings"]:
            lines.append("- {}".format(item))
        lines.append("")
    lines.append("## 否决原因 Top")
    if summary["veto_reasons"]:
        for reason, cnt in summary["veto_reasons"].items():
            lines.append("- {}：{}".format(reason, cnt))
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 字段覆盖（缺失计数）")
    if summary["missing"]:
        for key, cnt in summary["missing"].items():
            lines.append("- {}：{}".format(key, cnt))
    else:
        lines.append("- 无缺失")
    lines.append("")
    lines.append("## 阈值建议")
    if cuts.get("ok"):
        lines.append("基于 {} 条有效样本的分位：".format(cuts["samples"]))
        lines.append("```json")
        lines.append(json.dumps({"tier_cuts": cuts["tier_cuts"]}, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("- {}".format(cuts.get("reason")))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="融合层影子复盘")
    parser.add_argument("--day", default="", help="交易日 YYYY-MM-DD，默认今天")
    parser.add_argument("--root", default="", help="项目根目录，默认自动探测")
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是 Markdown")
    args = parser.parse_args(argv)

    day = args.day or today_str()
    records = load_records(day, args.root or None)
    summary = summarize(records)
    cuts = suggest_cuts(records, args.min_samples)

    if args.json:
        print(json.dumps({"day": day, "summary": summary, "cuts": cuts}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(summary, cuts, day))
    return 0 if records else 1


if __name__ == "__main__":
    sys.exit(main())
