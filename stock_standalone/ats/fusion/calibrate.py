# -*- coding: utf-8 -*-
"""ats/fusion/calibrate.py — 用"盈利排行榜"反向校准收敛规则。

问题：`select` 按"结构美观（阶段+RAR）"筛，答案是"涨幅"，目标函数不一致，
10/23 出现"信号层覆盖 15/20、收敛清单命中 0/20"。

做法：
    1. 训练日：把每个 L2+ 事件标上"是否进了当日盈利榜前 N"（答案标签）；
    2. 统计 (阶段 × 赛道强弱 × 是否带缩量转放量) 的历史命中率；
    3. 测试日：按历史命中率排序取前 K，量召回；
    4. 自动比较几种排序口径，保留最优。

不引入模型、不做参数搜索——只用可解释的分组命中率。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from ats.fusion.anomaly import PATTERN_DRY_UP, PATTERN_TWO_YANG, PATTERN_LATENT_BREAK
from ats.fusion.mine import collect, profit_ranking
from ats.fusion.replay import DayReplay, ReplayConfig
from ats.fusion.select import classify_stage


def _bucket_sector(r: Dict[str, Any]) -> str:
    return "强赛道" if float(r.get("sector_rank") or 0.0) >= 0.6 else "弱赛道"


def _bucket_stage(r: Dict[str, Any]) -> str:
    return classify_stage(r) or "无阶段"


def _has_dry(r: Dict[str, Any]) -> str:
    return "缩量转放量" if PATTERN_DRY_UP in (r.get("patterns") or []) else "无缩量"


def label_events(events: List[Dict[str, Any]], top_codes: Dict[str, set], min_ret: float = 8.0) -> None:
    """给事件打标签：是否进了当日盈利榜前 N（或收盘收益 >= min_ret）。"""
    for e in events:
        day = e.get("day")
        e["in_top"] = bool(e["code"] in (top_codes.get(day) or set())) or float(e.get("close_ret") or 0.0) >= min_ret


def build_table(events: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, float]]:
    """(阶段, 赛道强弱, 缩量) -> 命中率。"""
    buckets: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        buckets[(_bucket_stage(e), _bucket_sector(e), _has_dry(e))].append(e)
    table = {}
    for k, rows in buckets.items():
        n = len(rows)
        hit = sum(1 for r in rows if r.get("in_top"))
        table[k] = {"n": n, "hit": hit, "rate": hit / n if n else 0.0}
    return table


def _rate(table: Dict, e: Dict[str, Any], prior: float = 0.05, strength: float = 20.0) -> float:
    """带平滑的命中率（小样本往先验收缩）。"""
    k = (_bucket_stage(e), _bucket_sector(e), _has_dry(e))
    row = table.get(k)
    if not row:
        return prior
    return (row["hit"] + prior * strength) / (row["n"] + strength)


def rank_events(events: List[Dict[str, Any]], table: Dict, mode: str = "calibrated") -> List[Dict[str, Any]]:
    def _score(e: Dict[str, Any]) -> float:
        if mode == "rar":
            return float(e.get("rar") or 0.0)
        if mode == "profit_proxy":
            return float(e.get("rar") or 0.0) * 0.4 + float(e.get("sector_rank") or 0) * 40.0
        if mode == "pct":
            return float(e.get("pct") or 0.0)
        if mode == "ignition":
            return float(e.get("ignition") or 0.0)
        if mode == "pct_x_sector":
            return float(e.get("pct") or 0.0) * (0.5 + float(e.get("sector_rank") or 0.0))
        # calibrated：历史命中率为主，赛道与形态为辅
        s = _rate(table, e) * 100.0
        s += 8.0 * float(e.get("sector_rank") or 0.0)
        if PATTERN_DRY_UP in (e.get("patterns") or []):
            s += 5.0
        if PATTERN_TWO_YANG in (e.get("patterns") or []):
            s += 4.0
        if PATTERN_LATENT_BREAK in (e.get("patterns") or []):
            s += 3.0
        return s

    return sorted(events, key=_score, reverse=True)


def evaluate(ranked: List[Dict[str, Any]], top_codes: set, k: int = 20) -> Dict[str, Any]:
    picks = ranked[:k]
    hit = [p for p in picks if p["code"] in top_codes]
    return {
        "k": k,
        "hit": len(hit),
        "recall": round(len(hit) / max(1, len(top_codes)), 3),
        "hit_codes": [p["code"] for p in hit],
    }


def run(
    train_days: Iterable[str],
    test_day: str,
    top_n: int = 6000,
    step: int = 3,
    answer_top: int = 20,
) -> Dict[str, Any]:
    rp = DayReplay(config=ReplayConfig(top_n=top_n, step=step))
    days = list(train_days)

    top_codes: Dict[str, set] = {}
    all_events: List[Dict[str, Any]] = []
    for d in days + [test_day]:
        top_codes[d] = {r["code"] for r in profit_ranking(rp, d, top=answer_top)}
    for d in days:
        ev = collect([d], top_n=top_n, step=step, cache=rp.cache)
        label_events(ev, top_codes)
        all_events.extend(ev)

    table = build_table(all_events)

    test_events = collect([test_day], top_n=top_n, step=step, cache=rp.cache)
    label_events(test_events, top_codes)

    results = {}
    for mode in ("rar", "profit_proxy", "pct", "ignition", "pct_x_sector", "calibrated"):
        ranked = rank_events(test_events, table, mode=mode)
        results[mode] = evaluate(ranked, top_codes[test_day], k=answer_top)

    best = max(results.items(), key=lambda kv: kv[1]["recall"])
    return {
        "train_days": days,
        "test_day": test_day,
        "n_train_events": len(all_events),
        "n_test_events": len(test_events),
        "table": {"/".join(k): v for k, v in sorted(table.items(), key=lambda kv: -kv[1]["rate"])},
        "results": results,
        "best": {"mode": best[0], **best[1]},
    }


def render(res: Dict[str, Any]) -> str:
    lines = ["# 收敛规则校准", ""]
    lines.append("- 训练：{}（{} 条事件）｜测试：{}（{} 条事件）".format(
        "、".join(res["train_days"]), res["n_train_events"], res["test_day"], res["n_test_events"]))
    lines.append("")
    lines.append("## 历史命中率（阶段 × 赛道 × 缩量）")
    lines.append("| 分组 | 样本 | 命中 | 命中率 |")
    lines.append("|---|---|---|---|")
    for k, v in list(res["table"].items())[:15]:
        lines.append("| {} | {} | {} | {:.1%} |".format(k, v["n"], v["hit"], v["rate"]))
    lines.append("")
    lines.append("## 测试日召回（Top{}）".format(res["results"]["rar"]["k"]))
    lines.append("| 排序口径 | 命中 | 召回 |")
    lines.append("|---|---|---|")
    for mode, r in res["results"].items():
        lines.append("| {} | {}/{} | {:.0%} |".format(mode, r["hit"], r["k"], r["recall"]))
    lines.append("")
    lines.append("最优：**{}**，召回 {:.0%}".format(res["best"]["mode"], res["best"]["recall"]))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="用盈利榜校准收敛规则")
    parser.add_argument("--train", default="2026-10-19,2026-10-21")
    parser.add_argument("--test", default="2026-10-23")
    parser.add_argument("--top", type=int, default=6000)
    parser.add_argument("--step", type=int, default=3)
    args = parser.parse_args(argv)

    res = run([d for d in args.train.split(",") if d], args.test, top_n=args.top, step=args.step)
    print(render(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
