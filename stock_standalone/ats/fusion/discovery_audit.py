# -*- coding: utf-8 -*-
"""按时点审计逆势收复观察；只读行情缓存，不连接交易接口。"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

from ats.fusion.anomaly import PATTERN_COUNTER_RECLAIM
from ats.fusion.replay import DayReplay, ReplayConfig, day_bounds


def _price_at(cache, code, day, hour, minute, max_age=360):
    arr = cache.get(code)
    if arr is None:
        return None
    start, _ = day_bounds(day)
    target = start + hour * 3600 + minute * 60
    i = np.searchsorted(arr["time"], target, side="right") - 1
    if i < 0 or arr["time"][i] < start or target - arr["time"][i] > max_age:
        return None
    return float(arr["close"][i])


def summarize_result(replay, result, next_day, focus=()):
    day = result.day
    cutoff = day_bounds(day)[0] + 14 * 3600 + 45 * 60
    universe = set(result.meta.get("initial_candidate_codes") or ())
    universe.update(c for c, ts in (result.meta.get("candidate_activation") or {}).items() if ts <= cutoff)
    first = {}
    for row in result.records:
        if (row["code"] in universe and row["time"] <= "14:45"
                and PATTERN_COUNTER_RECLAIM in row.get("patterns", [])):
            first.setdefault(row["code"], row)

    opportunities, observed, false_positives, changes = set(), set(), set(), []
    outcomes = {}
    for code in universe:
        prev = replay._prev_close(code, day)
        close = _price_at(replay.cache, code, day, 15, 0)
        if prev > 0 and close is not None:
            changes.append((round((close / prev - 1) * 100, 2), code))
        if not next_day:
            continue
        morning = _price_at(replay.cache, code, day, 10, 0)
        future = _price_at(replay.cache, code, next_day, 15, 0)
        if morning is None or morning <= 0 or future is None:
            continue
        outcomes[code] = {"morning": morning, "next_close": future}
        if future / morning - 1 >= 0.03:
            opportunities.add(code)
        if code in first:
            observed.add(code)
            if future <= first[code]["entry"]:
                false_positives.add(code)

    detected = opportunities & observed
    trace = {}
    for code in focus:
        rows = [r for r in result.records if r["code"] == code]
        hits = [r for r in rows if PATTERN_COUNTER_RECLAIM in r.get("patterns", [])]
        trace[code] = {
            "first_observation": {k: hits[0].get(k) for k in ("time", "entry", "pct", "tier", "veto")} if hits else None,
            "points": [r for r in result.meta.get("focus_trace", {}).get(code, []) if r["time"] in ("10:37", "14:30")],
        }
    changes.sort()
    from ats.fusion.focus import audit_focus
    focus_metrics = audit_focus(result.records, {c: x["next_close"] for c, x in outcomes.items()})
    focus_detected = opportunities & {x["code"] for x in focus_metrics["first_selected"]}
    focus_metrics["detected_opportunities"] = len(focus_detected)
    focus_metrics["miss_rate"] = round(1 - len(focus_detected) / len(opportunities), 4) if opportunities else None
    return {
        "day": day, "next_day": next_day, "candidates": len(universe),
        "focus_selection": focus_metrics,
        "market_codes": result.meta.get("market_codes"), "observations_before_1445": len(first),
        "outcome_definition": "次交易日收盘相对当日10:00上涨至少3%；观察误报为次日收盘不高于首次发现价",
        "outcome_samples": len(observed), "false_positive_count": len(false_positives),
        "labelled_candidates": len(outcomes),
        "false_positive_rate": round(len(false_positives) / len(observed), 4) if observed else None,
        "opportunity_count": len(opportunities), "detected_opportunities": len(detected),
        "miss_rate": round(1 - len(detected) / len(opportunities), 4) if opportunities else None,
        "largest_falls": changes[:5], "largest_gains": list(reversed(changes[-5:])),
        "missed_examples": [{"code": c, "morning": round(outcomes[c]["morning"], 3),
                             "next_close": round(outcomes[c]["next_close"], 3)}
                            for c in sorted(opportunities - observed)[:100]],
        "false_positive_examples": [{"code": c, "time": first[c]["time"], "entry": first[c]["entry"],
                                     "next_close": round(outcomes[c]["next_close"], 3),
                                     "detail": first[c].get("reclaim_detail", {})}
                                    for c in sorted(false_positives)[:100]],
        "signal_samples": [{"code": c, "day": day, "time": first[c]["time"],
                            "not_above": c in false_positives,
                            "detail": first[c].get("reclaim_detail", {})}
                           for c in sorted(observed)],
        "focus": trace,
    }


def audit(replay, day, next_day, focus):
    return summarize_result(replay, replay.run_day(day, focus=focus), next_day, focus)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("days", nargs="+", help="依时间顺序传入交易日；最后一天仅用于前一天的次日评价")
    parser.add_argument("--top", type=int, default=800)
    parser.add_argument("--focus", nargs="*", default=["000568", "600809", "002281"])
    args = parser.parse_args()
    replay = DayReplay(config=ReplayConfig(top_n=args.top, step=1, cuts_mode="fixed", track=False,
                                          record_tier_min=4, max_records=100000,
                                          persist_context=False, market_path=os.devnull))
    for i, day in enumerate(args.days):
        next_day = args.days[i + 1] if i + 1 < len(args.days) else None
        print(json.dumps(audit(replay, day, next_day, args.focus), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
