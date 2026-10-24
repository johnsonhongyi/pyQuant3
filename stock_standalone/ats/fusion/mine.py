# -*- coding: utf-8 -*-
"""ats/fusion/mine.py — 从全部回放记录里挖"什么形态真的赚钱"，并剔除干扰信号。

思路（对应"用所有数据挖出盈利路径、剔除干扰"）：
    1. 把多个交易日的全市场回放记录汇总成一张事件表；
    2. 按"命中的形态组合"分组，统计每组的样本数、平均收盘收益、胜率、相对基准提升；
    3. 给出三类结论：有效（可留）、干扰（建议剔除/降权）、样本不足（先观察）。

不做：不做参数搜索、不做单票挑选。它只回答"哪一类结构值得下注"。
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from ats.fusion.replay import DayReplay, ReplayConfig, cross_section_cuts, FusionEngine


def _key(patterns: Iterable[str]) -> str:
    ps = sorted(set(patterns))
    return " + ".join(ps) if ps else "（无形态）"


def collect(
    days: Iterable[str],
    top_n: int = 6000,
    step: int = 2,
    cuts: Optional[Tuple[Tuple[float, int], ...]] = None,
    cache: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """逐日跑全市场回放，收集"首次达到 L2+"的事件（含形态、事后收益）。"""
    rp = DayReplay(config=ReplayConfig(top_n=top_n, step=step), cache=cache)
    out: List[Dict[str, Any]] = []
    for day in days:
        if cuts is None:
            sample = DayReplay(cache=rp.cache, engine=FusionEngine(), config=ReplayConfig(top_n=300, step=2))
            sample.run(day, collect_only=True)
            day_cuts = cross_section_cuts(getattr(sample, "_rar_by_t", {}))
        else:
            day_cuts = cuts
        res = rp.run(day, cuts_override=day_cuts, first_only=True, active_only=True)
        first: Dict[str, Dict[str, Any]] = {}
        for r in sorted(res.records, key=lambda x: x["ts"]):
            if r["tier"] >= 2 and r["code"] not in first:
                first[r["code"]] = r
        for r in first.values():
            out.append({
                "day": day,
                "code": r["code"],
                "time": r["time"],
                "tier": r["tier"],
                "rar": r["rar"],
                "pct": r["pct"],
                "close_ret": r["close_ret"],
                "mfe": r["mfe"],
                "patterns": list(r.get("patterns") or []),
                "key": _key(r.get("patterns") or []),
            })
    return out


def analyze(events: List[Dict[str, Any]], min_n: int = 15) -> Dict[str, Any]:
    """按形态组合统计边际效果，并分类。"""
    if not events:
        return {"n": 0, "groups": [], "base": {}}

    base_win = float(np.mean([1.0 if e["close_ret"] >= 2.0 else 0.0 for e in events]))
    base_ret = float(np.mean([e["close_ret"] for e in events]))

    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        groups[e["key"]].append(e)

    rows = []
    for key, items in groups.items():
        rets = [i["close_ret"] for i in items]
        mfes = [i["mfe"] for i in items]
        win = float(np.mean([1.0 if x >= 2.0 else 0.0 for x in rets]))
        lift = win / base_win if base_win > 0 else 0.0
        if len(items) < min_n:
            verdict = "样本不足"
        elif lift >= 1.30 and float(np.mean(rets)) > base_ret:
            verdict = "有效"
        elif lift <= 0.85 or float(np.mean(rets)) <= 0:
            verdict = "干扰"
        else:
            verdict = "中性"
        rows.append({
            "key": key,
            "n": len(items),
            "codes": len({i["code"] for i in items}),
            "avg_ret": round(float(np.mean(rets)), 2),
            "win_rate": round(win, 3),
            "lift": round(lift, 2),
            "avg_mfe": round(float(np.mean(mfes)), 2),
            "verdict": verdict,
        })

    rows.sort(key=lambda r: (r["verdict"] != "有效", -r["lift"], -r["n"]))
    return {
        "n": len(events),
        "base": {"win_rate": round(base_win, 3), "avg_ret": round(base_ret, 2)},
        "groups": rows,
    }


def single_patterns(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """单个形态的边际效果（用于判断哪个形态真正有信息量）。"""
    base_win = float(np.mean([1.0 if e["close_ret"] >= 2.0 else 0.0 for e in events])) if events else 0.0
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        for p in (e["patterns"] or ["（无形态）"]):
            buckets[p].append(e)
    rows = []
    for p, items in buckets.items():
        rets = [i["close_ret"] for i in items]
        win = float(np.mean([1.0 if x >= 2.0 else 0.0 for x in rets]))
        rows.append({
            "pattern": p,
            "n": len(items),
            "avg_ret": round(float(np.mean(rets)), 2),
            "win_rate": round(win, 3),
            "lift": round(win / base_win, 2) if base_win > 0 else 0.0,
        })
    rows.sort(key=lambda r: -r["lift"])
    return rows


def render(report: Dict[str, Any], singles: List[Dict[str, Any]], days: List[str]) -> str:
    lines = ["# 形态有效性挖掘 {}".format("、".join(days)), ""]
    if not report.get("n"):
        lines.append("- 无样本")
        return "\n".join(lines)
    b = report["base"]
    lines.append("- 样本 {} 条（每票每日取首次 L2+）｜基准：胜率 {:.1%}、平均收盘 {:+.2f}%".format(
        report["n"], b["win_rate"], b["avg_ret"]))
    lines.append("")
    lines.append("## 单形态边际")
    lines.append("| 形态 | 样本 | 平均收盘 | 胜率 | 提升 |")
    lines.append("|---|---|---|---|---|")
    for r in singles:
        lines.append("| {} | {} | {:+.2f}% | {:.1%} | {}x |".format(
            r["pattern"], r["n"], r["avg_ret"], r["win_rate"], r["lift"]))
    lines.append("")
    lines.append("## 形态组合（按提升排序）")
    lines.append("| 组合 | 样本 | 标的 | 平均收盘 | 胜率 | 提升 | 结论 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in report["groups"][:25]:
        lines.append("| {} | {} | {} | {:+.2f}% | {:.1%} | {}x | {} |".format(
            r["key"], r["n"], r["codes"], r["avg_ret"], r["win_rate"], r["lift"], r["verdict"]))
    lines.append("")
    bad = [r for r in report["groups"] if r["verdict"] == "干扰"]
    if bad:
        lines.append("## 建议剔除/降权的干扰组合")
        for r in bad[:10]:
            lines.append("- {}（{} 条，平均 {:+.2f}%，胜率 {:.1%}）".format(
                r["key"], r["n"], r["avg_ret"], r["win_rate"]))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="形态有效性挖掘")
    parser.add_argument("--days", default="", help="逗号分隔交易日；默认取缓存最后 5 天")
    parser.add_argument("--top", type=int, default=6000)
    parser.add_argument("--step", type=int, default=2)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    rp = DayReplay(config=ReplayConfig(top_n=args.top, step=args.step))
    days = [d for d in (args.days.split(",") if args.days else []) if d] or rp.days()[-5:]
    events = collect(days, top_n=args.top, step=args.step, cache=rp.cache)
    report = analyze(events)
    singles = single_patterns(events)
    md = render(report, singles, days)

    out_dir = args.out or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "fusion_mine")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, "mine_{}".format("_".join(d[-5:].replace("-", "") for d in days)))
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"days": days, "report": report, "singles": singles, "events": events}, f, ensure_ascii=False)
    print(md)
    print("\n落盘: {}.md / .json".format(base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
