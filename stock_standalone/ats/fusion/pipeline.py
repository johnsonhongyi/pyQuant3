# -*- coding: utf-8 -*-
"""ats/fusion/pipeline.py — 全流程日跑：赛道榜 → 盈利榜 → 个股收敛 → 三方对照。

一条命令跑完一天，回答三件事：
    1. 本地数据能不能找对赛道（赛道榜 vs 当日真实涨幅榜的主题分布）；
    2. 能不能找到答案（盈利榜前 20，我们命中几只）；
    3. 收敛清单里的票，落在哪些赛道、属于哪个阶段。

热榜暂不参与（它是对答案用的，见 sector.verify_heat）。
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np

from ats.fusion.mine import collect, profit_ranking
from ats.fusion.replay import DayReplay, ReplayConfig
from ats.fusion.select import STAGE_ORDER, render_selection, select_day
from ats.fusion.sector import get_theme_map
from ats.fusion.tracker import deploy_path
from ats.fusion.ranking import RankConfig, rank_entries, render_ranked
from ats.fusion.session_ctx import SessionContextStore
from ats.fusion.panel import build_panel, render_panel


def theme_board(rp: DayReplay, day: str, top: int = 15) -> List[Dict[str, Any]]:
    """本地概念赛道榜：当日（收盘）各概念成员平均涨幅与上涨占比。"""
    tm = get_theme_map()
    if not tm.ok:
        return []
    codes = rp._universe(day)
    prev = {}
    pct = {}
    for c in codes:
        sl = rp._slice_day(c, day)
        p0 = rp._prev_close(c, day)
        if sl is None or p0 <= 0:
            continue
        prev[c] = p0
        pct[c] = (float(sl["close"][-1]) / p0 - 1.0) * 100.0

    buckets: Dict[str, List[float]] = defaultdict(list)
    for c, v in pct.items():
        for t in tm.get(c):
            buckets[t].append(v)
    rows = []
    for t, vals in buckets.items():
        if len(vals) < 10:
            continue
        rows.append({
            "theme": t,
            "n": len(vals),
            "avg_pct": round(float(np.mean(vals)), 2),
            "breadth": round(float(np.mean([1.0 if x > 0 else 0.0 for x in vals])), 3),
        })
    rows.sort(key=lambda r: (-r["avg_pct"], -r["breadth"]))
    return rows[:top]


def run_day(day: str, top_n: int = 6000, step: int = 3,
            rank_cfg: Optional[RankConfig] = None) -> Dict[str, Any]:
    rp = DayReplay(config=ReplayConfig(top_n=top_n, step=step))

    themes = theme_board(rp, day)
    ranking = profit_ranking(rp, day, top=20)
    events = collect([day], top_n=top_n, step=step, cache=rp.cache)
    sel = select_day(events)

    # ④ 赛马跟踪：第一波入局 → 可下单（带旧信号的连续判断）
    track_res = rp.run(day, cuts_override=((68, 4), (60, 3), (52, 2), (45, 1)), active_only=True)
    entries = sorted(track_res.entries, key=lambda x: -float(x.get("persist") or 0.0))
    for e in entries:
        e["path"] = deploy_path(e)
    deploy = [e for e in entries if e["path"]]
    # 打分排序：四道闸门（趋同/跟风/阶段/跨日风险）不再"与"，而是给存活概率后取前 N。
    # 与闸门清单保留为对照列，便于每天核对"多放进来的是哪些、值不值"。
    ranked = rank_entries(entries, rank_cfg)
    panel = build_panel(records=track_res.records, entries=entries,
                        meta=track_res.meta, deploy_count=len(ranked))

    tm = get_theme_map()
    rank_map = {r["code"]: r for r in ranking}

    # 上下文交接：把"最近 N 日实盘上下文"放到日报最前面——
    # 这是每日自动迭代的入口，没有它每天都是从零开始判断
    handoff_md = ""
    try:
        handoff_md = SessionContextStore().render_handoff(day, 5)
    except Exception:
        handoff_md = ""

    # 盈利榜前 20 的赛道分布
    board_themes: Dict[str, int] = defaultdict(int)
    for r in ranking:
        for t in tm.get(r["code"])[:1]:
            board_themes[t] += 1

    # 我们的收敛清单命中了多少榜单
    sel_codes = {r["code"] for stage in sel["stages"].values() for r in stage}
    hits = [r for r in ranking if r["code"] in sel_codes]
    missed = [r for r in ranking if r["code"] not in sel_codes]
    ev_codes = {e["code"] for e in events}
    hit_events = [r for r in ranking if r["code"] in ev_codes]

    return {
        "day": day,
        "themes": themes,
        "ranking": ranking,
        "board_themes": dict(sorted(board_themes.items(), key=lambda x: -x[1])[:10]),
        "selection": sel,
        "hit": hits,
        "missed": missed,
        "recall": round(len(hits) / max(1, len(ranking)), 3),
        "hit_events": hit_events,
        "recall_events": round(len(hit_events) / max(1, len(ranking)), 3),
        "n_events": len(events),
        "entries": entries,
        "deploy": deploy,
        "ranked": ranked,
        "handoff": handoff_md,
        "panel": panel,
    }


def render(res: Dict[str, Any]) -> str:
    lines = ["# 全流程日跑 {}".format(res["day"]), ""]
    if res.get("handoff"):
        lines.append(res["handoff"])
    lines.append("- 当日 L2+ 事件 {} 条 → 收敛清单 {} 只".format(res["n_events"], res["selection"]["count"]))
    lines.append("- 盈利榜前20：**信号层覆盖 {} 只（{:.0%}）**｜收敛清单命中 {} 只（{:.0%}）".format(
        len(res["hit_events"]), res["recall_events"], len(res["hit"]), res["recall"]))
    lines.append("")
    lines.append("## ① 本地概念赛道榜（Top15）")
    lines.append("| 排名 | 概念 | 成员 | 平均涨幅 | 上涨占比 |")
    lines.append("|---|---|---|---|---|")
    for i, t in enumerate(res["themes"], 1):
        lines.append("| {} | {} | {} | {:+.2f}% | {:.0%} |".format(i, t["theme"], t["n"], t["avg_pct"], t["breadth"]))
    lines.append("")

    lines.append("## ② 盈利排行榜（答案，10:00→收盘）")
    lines.append("| # | 代码 | 涨幅 | 我们的阶段 | 赛道 |")
    lines.append("|---|---|---|---|---|")
    stage_of = {}
    for stage, rows in res["selection"]["stages"].items():
        for r in rows:
            stage_of.setdefault(r["code"], stage)
    for i, r in enumerate(res["ranking"], 1):
        lines.append("| {} | {} | {:+.1f}% | {} | {} |".format(
            i, r["code"], r["profit"], stage_of.get(r["code"], "—"), r.get("theme", "")))
    lines.append("")

    lines.append("## ③ 榜单主题分布（前 10）")
    for t, n in res["board_themes"].items():
        lines.append("- {}：{} 只".format(t, n))
    lines.append("")

    lines.append(render_selection(res["selection"], res["day"]))
    if res.get("panel"):
        lines.append(render_panel(res["panel"]))
    dep = res.get("deploy") or []
    ranked = res.get("ranked") or []
    lines.append("## ④ 赛马跟踪：入局 {} 笔 → 与闸门 {} 笔 → 打分排序 {} 笔".format(
        len(res.get("entries") or []), len(dep), len(ranked)))
    lines.append("")
    lines.append(render_ranked(ranked, res["day"]))
    if dep:
        lines.append("旧口径（与闸门）对照：{}".format("、".join(e["code"] for e in dep)))
    else:
        lines.append("旧口径（与闸门）：今日无（七项同时满足太难）")
    lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="全流程日跑")
    parser.add_argument("--day", default="")
    parser.add_argument("--top", type=int, default=6000)
    parser.add_argument("--step", type=int, default=3)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    rp = DayReplay(config=ReplayConfig(top_n=args.top, step=args.step))
    day = args.day or (rp.days()[-1] if rp.days() else "")
    res = run_day(day, top_n=args.top, step=args.step)
    md = render(res)

    out_dir = args.out or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "fusion_pipeline")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, day)
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, default=str)
    print(md)
    print("\n落盘: {}.md / .json".format(base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
