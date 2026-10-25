# -*- coding: utf-8 -*-
"""ats/fusion/validate_track.py — 赛马跟踪层的闭卷验收。

验收口径（不给答案去找，而是系统先跑，再拿答案核对）：
    1) 每天系统自己给出"第一波入局"事件（时间、价格、涨幅、证据链）；
    2) 再按"可下单闸门"（赛道强度 + 首异动涨幅 + 想的多回踩的少 + 量能持续）收敛；
    3) 与本周涨幅榜 50 只核对，并给出 T+1 结果（买入当日不可卖）。

关键点：
    - 一个 RaceTracker 跨 5 天复用，才能携带"昨日入局"（多日连续性）；
    - 入局必须发生在涨幅还小的时候（自首异动 ≤5%），否则就是追高；
    - T+1 用次日收盘价 / 入局价；最后一天（10/23）无次日数据，不计入。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import numpy as np

from ats.fusion.names import codes_for
from ats.fusion.replay import DayReplay, ReplayConfig, day_bounds
from ats.fusion.tracker import DeployRule, deploy_path, is_deployable
from ats.fusion.panel import build_panel, lead_value_table, render_panel

WEEK_TOP = """凡拓数创 海天瑞声 利亚德 海洋王 大业股份 索辰科技 奥比中光 长盈精密 兆威机电 安培龙
华依科技 华阳智能 福莱新材 汉威科技 慧辰股份 敏芯股份 宇树科技 博汇股份 奥普特 嘉晨智能
大普微 众诚科技 斯菱智驱 慈星股份 步科股份 浙江荣泰 福赛科技 凌云光 云汉芯城 龙旗科技
大鹏工业 鸣志电器 新睿电子 上海九百 宁波东力 科森科技 赛摩智能 日盈电子 世纪恒通 精研科技
润建股份 乐鑫科技 三维天地 恒玄科技 正裕工业 巨能股份 奥雅股份 海正药业 奕帆传动 鼎捷数智""".split()

DAYS = ("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23")
CUTS = ((68, 4), (60, 3), (52, 2), (45, 1))


def _t1(cache: Dict[str, Any], code: str, day: str, entry: float) -> Optional[float]:
    """次日收盘相对入局价（T+1：买入当日不可卖，最早次日离场）。"""
    if day not in DAYS:
        return None
    i = DAYS.index(day)
    if i + 1 >= len(DAYS):
        return None
    arr = cache.get(code)
    if arr is None or len(arr) == 0:
        return None
    s, e = day_bounds(DAYS[i + 1])
    ts = arr["time"].astype("int64")
    m = (ts >= s) & (ts < e)
    if not m.any():
        return None
    return round((float(arr["close"][m][-1]) / entry - 1.0) * 100.0, 2)


def _agg(rows: List[Dict[str, Any]], ans: set) -> Dict[str, Any]:
    if not rows:
        return {"n": 0, "ans": 0, "close": 0.0, "t1": 0.0, "win": 0.0, "mfe": 0.0, "mae": 0.0}
    t1 = [r["t1"] for r in rows if r.get("t1") is not None]
    return {
        "n": len(rows),
        "ans": sum(1 for r in rows if r["code"] in ans),
        "close": round(float(np.mean([r["close_ret"] for r in rows])), 2),
        "mfe": round(float(np.mean([r["mfe"] for r in rows])), 2),
        "mae": round(float(np.mean([r["mae"] for r in rows])), 2),
        "t1": round(float(np.mean(t1)), 2) if t1 else 0.0,
        "win": round(100.0 * float(np.mean([1.0 if x > 0 else 0.0 for x in t1])), 0) if t1 else 0.0,
    }


def run(days=DAYS, top_n: int = 6000, step: int = 3, rule: Optional[DeployRule] = None) -> Dict[str, Any]:
    ans = set(codes_for(WEEK_TOP).values())
    rp = DayReplay(config=ReplayConfig(top_n=top_n, step=step, first_only=False))
    cache = rp.cache
    per_day: List[Dict[str, Any]] = []
    pool: List[Dict[str, Any]] = []
    deploy_all: List[Dict[str, Any]] = []

    for day in days:
        res = rp.run(day, cuts_override=CUTS, active_only=True)
        if res.meta.get("error"):
            per_day.append({"day": day, "error": res.meta["error"]})
            continue
        ents = sorted(res.entries, key=lambda x: -float(x.get("persist") or 0.0))
        for e in ents:
            e["t1"] = _t1(cache, e["code"], day, float(e["enter_price"]))
        for e in ents:
            e["path"] = deploy_path(e, rule)
        dep = [e for e in ents if e["path"]]
        dep.sort(key=lambda x: (
            float(x.get("persist") or 0) + 0.5 * float(x.get("lead_score") or 0)
            - 40.0 * max(0.0, float(x.get("consensus") or 0) - 0.4)
        ), reverse=True)
        dep = dep[:3]   # 每日最多 3 只（宁可不做）
        ev = res.meta.get("evictions") or []
        post = [e for e in ev if e.get("post_entry")]
        pool += ents
        deploy_all += dep
        row = {
            "day": day,
            "entries": len(ents),
            "deploy": len(dep),
            "evict_watch": len(ev) - len(post),
            "evict_post": len(post),
            "evict_pnl": round(float(np.mean([e.get("pnl_from_enter") or 0.0 for e in post])), 2) if post else 0.0,
            "records": len(res.records),
            "t1": res.meta.get("t1_decisions") or [],
            "blocked": res.meta.get("blocked") or {},
            "all_entries": ents,
            "deploy_list": dep,
            "hit": {k: sum(1 for e in ents[:k] if e["code"] in ans) for k in (3, 5, 10)},
            "dep_hit": sum(1 for e in dep if e["code"] in ans),
        }
        per_day.append(row)
        print("{} | 入局{:>3} 可下单{:>2} 剔除(持仓){:>3} | 入局Top5命中{} | 可下单命中{}/{} | 平均自首异动{:+.2f}%".format(
            day, row["entries"], row["deploy"], row["evict_post"], row["hit"][5],
            row["dep_hit"], row["deploy"],
            float(np.mean([e["since_first_pct"] for e in ents])) if ents else 0.0))

    ok = [r for r in per_day if "error" not in r]
    pool_agg = _agg(pool, ans)
    dep_agg = _agg(deploy_all, ans)
    summary = {
        "days": len(ok),
        "entries": sum(r["entries"] for r in ok),
        "deploy": sum(r["deploy"] for r in ok),
        "records": sum(r["records"] for r in ok),
        "evict_post": sum(r["evict_post"] for r in ok),
        "evict_watch": sum(r["evict_watch"] for r in ok),
        "evict_pnl": round(float(np.mean([r["evict_pnl"] for r in ok if r["evict_post"]])), 2) if ok else 0.0,
        "hit5": sum(r["hit"][5] for r in ok),
        "hit10": sum(r["hit"][10] for r in ok),
        "dep_hit": sum(r["dep_hit"] for r in ok),
        "pool": pool_agg,
        "deploy_agg": dep_agg,
        "since_first": round(float(np.mean([e["since_first_pct"] for e in pool])), 2) if pool else 0.0,
        "t1_actions": _count_actions(ok),
        "blocked": _sum_blocked(ok),
        "trap_agg": _trap_split(pool, ans),
    }
    return {
        "per_day": per_day,
        "summary": summary,
        "answers": sorted(ans),
        "pool_agg": pool_agg,
        "deploy_agg": dep_agg,
    }


def _sum_blocked(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    from collections import Counter

    c: Counter = Counter()
    for r in rows:
        for k, v in (r.get("blocked") or {}).items():
            c[k] += int(v)
    return dict(c)


def _label_split(rows: List[Dict[str, Any]], ans: set) -> List[Dict[str, Any]]:
    """按领先度标签（排头兵/冲锋队/夺旗/跟风/无导向）统计事后表现。"""
    out = []
    for lab in ("排头兵", "夺旗", "冲锋队", "无导向", "跟风"):
        g = [e for e in rows if (e.get("lead_label") or "") == lab]
        if not g:
            continue
        a = _agg(g, ans)
        a["label"] = lab
        out.append(a)
    return out


def _phase_split(rows: List[Dict[str, Any]], ans: set) -> List[Dict[str, Any]]:
    """按战役阶段（反攻/攻城略地/先锋阵亡/退守/冰点）统计事后表现。"""
    out = []
    for lab in ("反攻", "攻城略地", "先锋阵亡", "退守", "冰点"):
        g = [e for e in rows if (e.get("phase") or "") == lab]
        if not g:
            continue
        a = _agg(g, ans)
        a["phase"] = lab
        out.append(a)
    return out


def _count_actions(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    from collections import Counter

    c: Counter = Counter()
    for r in rows:
        for e in (r.get("t1") or []):
            c[e.get("action") or "?"] += 1
    return dict(c)


def _trap_split(rows: List[Dict[str, Any]], ans: set) -> Dict[str, Any]:
    """有陷阱 vs 无陷阱：验证"冲高回落/昨日大涨今日杀跌"是否真的更差。"""
    out: Dict[str, Any] = {}
    for name, pred in (
        ("无陷阱", lambda e: not (e.get("traps") or [])),
        ("有陷阱", lambda e: bool(e.get("traps") or [])),
    ):
        g = [e for e in rows if pred(e)]
        if g:
            out[name] = _agg(g, ans)
    # 按跨日风险分档
    for lo, hi in ((0, 30), (30, 60), (60, 101)):
        g = [e for e in rows if lo <= float(e.get("gap_risk") or 0.0) < hi]
        if g:
            out["跨日风险{:d}~{:d}".format(lo, min(hi, 100))] = _agg(g, ans)
    return out


def discrimination(data: Dict[str, Any]) -> Dict[str, Any]:
    ans = set(data["answers"])
    rows = [e for r in data["per_day"] if "error" not in r for e in (r.get("all_entries") or [])]
    a = [e for e in rows if e["code"] in ans]
    b = [e for e in rows if e["code"] not in ans]
    feats = ("persist", "vol_frac", "efficiency", "hold_frac", "evidence_n",
             "first_pct", "enter_pct", "since_first_pct", "sector_rank", "theme_rank")
    out: Dict[str, Any] = {"n_ans": len(a), "n_other": len(b), "feat": {}}
    for f in feats:
        va = [float(e.get(f) or 0.0) for e in a]
        vb = [float(e.get(f) or 0.0) for e in b]
        out["feat"][f] = {
            "ans": round(float(np.mean(va)), 2) if va else 0.0,
            "other": round(float(np.mean(vb)), 2) if vb else 0.0,
            "diff": round(float(np.mean(va)) - float(np.mean(vb)), 2) if va and vb else 0.0,
        }
    out["coverage"] = {
        "codes": len({e["code"] for e in a}), "of": len(ans),
        "list": sorted({e["code"] for e in a}),
    }
    out["lead_table"] = lead_value_table(rows)
    out["lead_label_table"] = _label_split(rows, ans)
    out["phase_table"] = _phase_split(rows, ans)
    out["ans_agg"] = _agg(a, ans)
    out["other_agg"] = _agg(b, ans)
    return out


def render(data: Dict[str, Any]) -> str:
    s = data["summary"]
    lines = ["# 赛马跟踪层验收（闭卷）", ""]
    lines.append("## 一、汇总")
    lines.append("")
    lines.append("- 交易日 {}｜L2+ 记录 {} 条 → 第一波入局 **{} 笔** → 可下单 **{} 笔**".format(
        s["days"], s["records"], s["entries"], s["deploy"]))
    lines.append("- 入局时自首异动平均涨幅 **{:+.2f}%**（第一波，不是追高）".format(s["since_first"]))
    lines.append("")
    p, d = s["pool"], s["deploy_agg"]
    lines.append("| 口径 | 笔数 | 命中榜单 | 当日收盘 | 次日收盘(T+1) | T+1胜率 | 之后MFE | 之后MAE |")
    lines.append("|---|---|---|---|---|---|---|---|")
    lines.append("| 第一波入局（全部） | {} | {} | {:+.2f}% | {:+.2f}% | {:.0f}% | {:+.2f}% | {:+.2f}% |".format(
        p["n"], p["ans"], p["close"], p["t1"], p["win"], p["mfe"], p["mae"]))
    lines.append("| **可下单清单** | **{}** | **{}** | **{:+.2f}%** | **{:+.2f}%** | **{:.0f}%** | **{:+.2f}%** | **{:+.2f}%** |".format(
        d["n"], d["ans"], d["close"], d["t1"], d["win"], d["mfe"], d["mae"]))
    lines.append("")
    lines.append("- 入局后剔除 {} 笔｜平均 {:+.2f}%（观察期过期 {} 笔另计）".format(
        s["evict_post"], s["evict_pnl"], s["evict_watch"]))
    if s.get("blocked"):
        lines.append("- 被陷阱/跨日风险拦下：{}".format(
            "｜".join("{} {}".format(k, v) for k, v in sorted(s["blocked"].items(), key=lambda x: -x[1]))))
    if s.get("t1_actions"):
        lines.append("- T+1 持仓决策：{}".format(
            "｜".join("{} {}".format(k, v) for k, v in s["t1_actions"].items())))
    lines.append("")
    ta = s.get("trap_agg") or {}
    if len(ta) > 1:
        lines.append("### 陷阱与跨日风险分组")
        lines.append("")
        lines.append("| 分组 | 笔数 | 当日收盘 | 次日收盘(T+1) | T+1胜率 | 之后MFE |")
        lines.append("|---|---|---|---|---|---|")
        for k, v in ta.items():
            lines.append("| {} | {} | {:+.2f}% | {:+.2f}% | {:.0f}% | {:+.2f}% |".format(
                k, v["n"], v["close"], v["t1"], v["win"], v["mfe"]))
        lines.append("")
    dc = data.get("disc") or {}
    if dc.get("feat"):
        lines.append("## 二、答案组 vs 其他组（入局时刻特征）")
        lines.append("")
        lines.append("- 覆盖：{} / {} 只（{:.0%}）拿到过入局信号".format(
            dc["coverage"]["codes"], dc["coverage"]["of"],
            dc["coverage"]["codes"] / max(1, dc["coverage"]["of"])))
        a = dc["ans_agg"]
        lines.append("- 答案组入局 {} 笔：当日 {:+.2f}%｜T+1 {:+.2f}%（胜率 {:.0f}%）".format(
            a["n"], a["close"], a["t1"], a["win"]))
        lines.append("")
        lines.append("| 特征 | 答案组 | 其他组 | 差值 |")
        lines.append("|---|---|---|---|")
        for f, v in dc["feat"].items():
            lines.append("| {} | {} | {} | {:+} |".format(f, v["ans"], v["other"], v["diff"]))
        lines.append("")
    lbl = dc.get("lead_label_table") or []
    if lbl:
        lines.append("## 四、领先度（排头兵 / 冲锋队 / 夺旗 / 跟风）")
        lines.append("")
        lines.append("| 领先度 | 笔数 | 命中榜单 | 当日收盘 | T+1 | T+1胜率 |")
        lines.append("|---|---|---|---|---|---|")
        for r in lbl:
            lines.append("| {} | {} | {} | {:+.2f}% | {:+.2f}% | {:.0f}% |".format(
                r["label"], r["n"], r["ans"], r["close"], r["t1"], r["win"]))
        lines.append("")

    ph = dc.get("phase_table") or []
    if ph:
        lines.append("## 五、战役阶段（反攻 / 攻城略地 / 先锋阵亡 / 退守 / 冰点）")
        lines.append("")
        lines.append("| 阶段 | 笔数 | 命中榜单 | 当日收盘 | T+1 | T+1胜率 |")
        lines.append("|---|---|---|---|---|---|")
        for r in ph:
            lines.append("| {} | {} | {} | {:+.2f}% | {:+.2f}% | {:.0f}% |".format(
                r["phase"], r["n"], r["ans"], r["close"], r["t1"], r["win"]))
        lines.append("")

    lt = dc.get("lead_table") or []
    if lt:
        lines.append("## 三、带头价值分档（温度越低、趋同越低，才值钱）")
        lines.append("")
        lines.append("| 带头价值 | 笔数 | 当日收盘 | T+1 | T+1胜率 |")
        lines.append("|---|---|---|---|---|")
        for r in lt:
            lines.append("| ×{} | {} | {:+.2f}% | {:+.2f}% | {:.0f}% |".format(
                r["range"], r["n"], r["close"], r["t1"], r["win"]))
        lines.append("")

    for r in data["per_day"]:
        if "error" in r:
            lines.append("## {}｜{}".format(r["day"], r["error"]))
            continue
        lines.append("## {}｜入局 {}｜可下单 {}".format(r["day"], r["entries"], r["deploy"]))
        lines.append("")
        if r["deploy_list"]:
            lines.append("| # | 代码 | 路径 | 入局 | 入局价 | 当时涨幅 | 首异动涨幅 | 持续分 | 赛道 | 形态 | T+1 |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
            for i, e in enumerate(r["deploy_list"], 1):
                lines.append("| {} | {} | {} | {} | {} | {:+.1f}% | {:+.1f}% | {} | {} | {} | {} |".format(
                    i, e["code"], e.get("path", ""), e["enter_time"], e["enter_price"],
                    e["enter_pct"], e["first_pct"], e["persist"], e.get("sector", ""),
                    "、".join((e.get("patterns") or {}).keys()) or "-",
                    "{:+.2f}%".format(e["t1"]) if e.get("t1") is not None else "-"))
        else:
            lines.append("- 今日无可下单标的（宁可不做）")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    t0 = time.time()
    data = run()
    data["disc"] = discrimination(data)
    md = render(data)
    os.makedirs("logs/fusion_mine", exist_ok=True)
    with open("logs/fusion_mine/track_validation.md", "w", encoding="utf-8") as f:
        f.write(md)
    with open("logs/fusion_mine/track_validation.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("\n耗时 {:.0f}s".format(time.time() - t0))
    print("入局 {} 笔 | 可下单 {} 笔 | 可下单 T+1 {:+.2f}% 胜率 {:.0f}%".format(
        data["summary"]["entries"], data["summary"]["deploy"],
        data["summary"]["deploy_agg"]["t1"], data["summary"]["deploy_agg"]["win"]))
