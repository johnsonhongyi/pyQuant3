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
            # 全字段透传：structure/sector/sector_rank/vol_dry 等分层字段一个都不能丢
            item = dict(r)
            item["day"] = day
            item["patterns"] = list(r.get("patterns") or [])
            item["key"] = _key(item["patterns"])
            out.append(item)
    return out


def profit_ranking(rp: DayReplay, day: str, top: int = 20, start_hm: str = "10:00") -> List[Dict[str, Any]]:
    """当日"盈利排行榜"（答案）：从 start_hm 到收盘的涨幅，与系统信号无关。"""
    from ats.fusion.replay import day_bounds
    codes = rp._universe(day)
    aligned = rp._align(codes, day)
    if aligned is None:
        return []
    clock = aligned["clock"]
    close = aligned["mat"]["close"]
    ds, _ = day_bounds(day)
    hh, mm = start_hm.split(":")
    t0 = int(np.searchsorted(clock, ds + int(hh) * 3600 + int(mm) * 60))
    t0 = max(0, min(t0, close.shape[1] - 1))
    p0 = close[:, t0]
    last = close[:, -1]
    rows = []
    for i, c in enumerate(aligned["codes"]):
        if np.isfinite(p0[i]) and p0[i] > 0 and np.isfinite(last[i]):
            rows.append({"code": c, "profit": round(float(last[i] / p0[i] - 1) * 100, 2),
                         "p0": round(float(p0[i]), 3), "close": round(float(last[i]), 3)})
    try:
        from ats.fusion.sector import get_theme_map
        tm = get_theme_map()
    except Exception:
        tm = None
    for r in rows:
        if tm is not None and tm.ok:
            tags = tm.get(r["code"])
            r["theme"] = tags[0] if tags else ""
    rows.sort(key=lambda r: -r["profit"])
    return rows[:top]


def gap_report(ranking: List[Dict[str, Any]], events: List[Dict[str, Any]], day: str) -> Dict[str, Any]:
    """把"盈利排行榜"和"系统当天给的 L2+"对齐，看命中/漏掉/多报。"""
    ev = {e["code"]: e for e in events if e["day"] == day}
    hit, miss = [], []
    for r in ranking:
        e = ev.get(r["code"])
        if e:
            hit.append({**r, "time": e["time"], "tier": e["tier"], "rar": e["rar"], "patterns": e["patterns"]})
        else:
            miss.append(r)
    extra = [e for c, e in ev.items() if c not in {r["code"] for r in ranking}]
    return {
        "day": day, "rank_n": len(ranking), "hit": hit, "miss": miss,
        "system_n": len(ev), "extra_n": len(extra),
        "recall": round(len(hit) / len(ranking), 3) if ranking else 0.0,
    }


def stratified(events: List[Dict[str, Any]], min_n: int = 10) -> List[Dict[str, Any]]:
    """按 (结构, 时段) 分层，看每层里各形态的边际。这就是"先分类再谈信号"。"""
    from ats.fusion.structure import label as slabel
    out = []
    buckets: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        buckets[(e.get("structure") or "OTHER", e.get("session") or "AM")].append(e)
    for (st, sess), items in buckets.items():
        if len(items) < min_n:
            continue
        base_win = float(np.mean([1.0 if i["close_ret"] >= 2.0 else 0.0 for i in items]))
        base_ret = float(np.mean([i["close_ret"] for i in items]))
        by_pat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for i in items:
            for p in (i["patterns"] or ["（无形态）"]):
                by_pat[p].append(i)
        rows = []
        for p, ps in by_pat.items():
            rets = [x["close_ret"] for x in ps]
            win = float(np.mean([1.0 if x >= 2.0 else 0.0 for x in rets]))
            rows.append({
                "pattern": p, "n": len(ps),
                "avg_ret": round(float(np.mean(rets)), 2),
                "win_rate": round(win, 3),
                "lift": round(win / base_win, 2) if base_win > 0 else 0.0,
            })
        rows.sort(key=lambda r: -r["lift"])
        out.append({
            "structure": st, "label": slabel(st), "session": sess,
            "n": len(items), "base_win": round(base_win, 3), "base_ret": round(base_ret, 2),
            "patterns": rows,
        })
    out.sort(key=lambda x: (x["structure"], x["session"]))
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
    parser.add_argument("--rank", action="store_true", help="同时输出盈利排行榜与命中缺口")
    parser.add_argument("--select", action="store_true", help="输出每日收敛清单(每类最多N只)")
    args = parser.parse_args(argv)

    rp = DayReplay(config=ReplayConfig(top_n=args.top, step=args.step))
    days = [d for d in (args.days.split(",") if args.days else []) if d] or rp.days()[-5:]
    events = collect(days, top_n=args.top, step=args.step, cache=rp.cache)
    report = analyze(events)
    singles = single_patterns(events)
    md = render(report, singles, days)
    strat = stratified(events)
    if strat:
        md += "\n\n## 按结构 × 时段分层（先分类，再谈信号）\n"
        for g in strat:
            md += "\n### {}｜{}｜样本 {}｜基准胜率 {:.1%}、平均 {:+.2f}%\n".format(
                g["label"], "上午" if g["session"] == "AM" else "下午", g["n"], g["base_win"], g["base_ret"])
            md += "\n| 形态 | 样本 | 平均收盘 | 胜率 | 提升 |\n|---|---|---|---|---|\n"
            for r in g["patterns"]:
                md += "| {} | {} | {:+.2f}% | {:.1%} | {}x |\n".format(
                    r["pattern"], r["n"], r["avg_ret"], r["win_rate"], r["lift"])
    if args.select:
        from ats.fusion.select import select_day, render_selection
        for day in days:
            day_events = [e for e in events if e["day"] == day]
            sel = select_day(day_events)
            md += "\n" + render_selection(sel, day)
    if args.rank:
        rp2 = DayReplay(config=ReplayConfig(top_n=args.top, step=args.step), cache=rp.cache)
        md += "\n\n## 盈利排行榜 vs 系统命中\n"
        for day in days:
            rk = profit_ranking(rp2, day, top=20)
            g = gap_report(rk, events, day)
            md += "\n### {}｜榜单20只，系统命中 {}（召回 {:.0%}）｜系统当日 L2+ {} 只\n".format(
                day, len(g["hit"]), g["recall"], g["system_n"])
            md += "\n| # | 代码 | 涨幅 | 系统 | 时间 | 级别 | 形态 |\n|---|---|---|---|---|---|---|\n"
            for i, r in enumerate(rk, 1):
                e = {h["code"]: h for h in g["hit"]}.get(r["code"])
                if e:
                    md += "| {} | {} | {:+.1f}% | ✅ | {} | L{} | {} |\n".format(
                        i, r["code"], r["profit"], e["time"], e["tier"], "、".join(e["patterns"]) or "-")
                else:
                    md += "| {} | {} | {:+.1f}% | ❌ | - | - | - |\n".format(i, r["code"], r["profit"])

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
