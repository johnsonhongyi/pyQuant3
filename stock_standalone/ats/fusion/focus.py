# -*- coding: utf-8 -*-
"""按当时证据收敛逆势重点；不读取后验收益、不产生交易指令。"""
from collections import defaultdict
from datetime import datetime

from ats.fusion.anomaly import PATTERN_COUNTER_HOLD, PATTERN_COUNTER_RECLAIM


def select_focus(rows, asof_ts, limit=10, max_age=360):
    """最多十只当前重点：站稳优先，同等承接下优先低追高距离。"""
    latest = {}
    for row in rows:
        ts = float(row.get("ts") or 0)
        code = row.get("code")
        if row.get("trade_date") and str(row["trade_date"])[:10] != datetime.fromtimestamp(ts).strftime("%Y-%m-%d"):
            continue
        if code and 0 <= asof_ts - ts <= max_age and ts >= float(latest.get(code, {}).get("ts") or 0):
            latest[code] = row
    ranked = []
    for row in latest.values():
        patterns = set(row.get("patterns") or [])
        detail = row.get("reclaim_detail") or {}
        price = float(row.get("price") or row.get("entry") or 0)
        vwap = float(row.get("vwap") or detail.get("vwap") or 0)
        if (not patterns.intersection((PATTERN_COUNTER_RECLAIM, PATTERN_COUNTER_HOLD))
                or row.get("pct") is None or price <= 0 or vwap <= 0):
            continue
        anchors = [vwap, float(detail.get("vwap3") or 0), float(detail.get("vwap5") or 0)]
        if min(anchors) <= 0 or price < max(anchors):
            continue
        # 排序不奖励急拉或极端量比，避免把已经放量拉升者排在先手前。
        key = (float(detail.get("hold_ratio") or 0),
               -(price / vwap - 1),
               float(row.get("pct") or 0) - float(detail.get("sector_pct") or 0))
        ranked.append((key, str(row["code"]), row))
    ranked.sort(key=lambda item: (tuple(-x for x in item[0]), item[1]))
    budget = min(10, max(0, limit))
    # 留出两个首次发现席位，避免长时间站稳的旧候选占满十席，延迟展示新收复。
    fresh = [item for item in ranked
             if item[2].get("counter_reclaim_first_ts")
             and 0 <= asof_ts - float(item[2]["counter_reclaim_first_ts"]) <= max_age]
    fresh.sort(key=lambda item: -float(item[2]["counter_reclaim_first_ts"]))
    fresh = fresh[:min(2, budget)]
    fresh_codes = {item[1] for item in fresh}
    ranked = fresh + [item for item in ranked if item[1] not in fresh_codes]
    selected, sector_counts = [], defaultdict(int)
    for item in ranked:
        sector = item[2].get("sector") or item[1]
        if sector_counts[sector] >= 2:
            continue
        selected.append(item)
        sector_counts[sector] += 1
        if len(selected) >= budget:
            break
    return [dict(row, focus_rank=i + 1,
                 focus_stage="首次发现" if code in fresh_codes else "持续观察",
                 execution_veto=row.get("veto") or (row.get("fusion") or {}).get("veto_reason") or "")
            for i, (_, code, row) in enumerate(selected[:budget])]


def audit_focus(records, next_close, limit=10):
    """逐时点回放重点池，结算使用首次真正进入重点的价；单独报告换入数量。"""
    frames = defaultdict(list)
    for row in records:
        if row.get("time", "") <= "14:45":
            frames[float(row.get("ts") or 0)].append(row)
    latest, first = {}, {}
    peak = 0
    for ts, rows in sorted(frames.items()):
        latest.update((row["code"], row) for row in rows)
        selected = select_focus(latest.values(), ts, limit)
        peak = max(peak, len(selected))
        for row in selected:
            first.setdefault(row["code"], dict(row, signal_time=row["time"],
                                              time=datetime.fromtimestamp(ts).strftime("%H:%M")))
    settled = [row for code, row in first.items() if code in next_close]
    false_n = sum(next_close[row["code"]] <= row["entry"] for row in settled)
    return {"limit": limit, "max_simultaneous": peak, "daily_distinct": len(first),
            "outcome_samples": len(settled), "false_positive_count": false_n,
            "false_positive_rate": round(false_n / len(settled), 4) if settled else None,
            "first_selected": [{k: row.get(k) for k in ("code", "time", "signal_time", "entry", "pct", "focus_rank")}
                               for row in first.values()],
            "note": "重点为观察排序，非交易指令；同时上限不等于全天累计上限。"}
