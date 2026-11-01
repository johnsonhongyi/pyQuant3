# -*- coding: utf-8 -*-
"""以用户提供的周榜作为事后标签，对照独立回放与生产观察记录。"""
from __future__ import annotations

import argparse
from datetime import datetime, time
import gzip
import json
import math
from pathlib import Path

import pandas as pd

from ats.fusion.context import _find_daily_path
from ats.fusion.iteration import _next_cached_session
from ats.fusion.replay import day_bounds, load_minute_cache
from ats.fusion.replay_follow import read_replay_follow


def _session(ts, day):
    try:
        stamp = datetime.fromtimestamp(float(ts))
        clock = stamp.time()
        return stamp.strftime("%Y-%m-%d") == day and (time(9, 30) <= clock < time(11, 30) or time(13) <= clock <= time(14, 45))
    except (TypeError, ValueError, OverflowError, OSError):
        return False


def _is_observation(tier, veto, patterns):
    return (tier >= 2 and not veto) or bool({"逆势收复启动", "逆势收复持稳"} & set(patterns or []))


def _next_close(cache, code, day):
    bars = cache.get(code)
    if bars is None:
        return None
    start, _ = day_bounds(day)
    selected = bars[(bars["time"] >= start + 14 * 3600 + 54 * 60)
                    & (bars["time"] <= start + 15 * 3600 + 3 * 60)]
    price = float(selected[-1]["close"]) if len(selected) else 0
    return price if math.isfinite(price) and price > 0 else None


def audit(labels, daily, cache, production_root, replay_run):
    entries = labels["entries"]
    codes = {str(x["code"]).zfill(6) for x in entries}
    start, end = labels["start_date"], labels["end_date"]
    follow = read_replay_follow([], end, replay_run)
    if follow.get("status") != "ready" or not follow.get("independent"):
        raise ValueError("需要输入可核验的独立回放档案")
    days = sorted(d for d in follow["sources"] if start < d <= end)
    production, replay, candidates = {}, {}, set()
    for day in days:
        from ats.fusion.shadow_io import iter_day_records
        directory = str(Path(production_root) / "logs" / "fusion_shadow")
        for row in iter_day_records(directory, day):
            try:
                code, ts = str(row.get("code") or "").zfill(6), row.get("ts")
                origin, source = str(row.get("writer_exe") or "").upper(), str(row.get("source") or "").lower()
                fusion = row.get("fusion") or {}
                price = float(row.get("price") or 0)
                pct = float(row["pct"]) if row.get("pct") is not None else float("nan")
                if (code not in codes or not _session(ts, day) or "REPLAY" in origin or "BACKFILL" in origin
                        or "replay" in source or row.get("writer_pid") == 0 or not row.get("price")
                        or not math.isfinite(price) or not math.isfinite(pct) or price <= 0 or pct <= -50
                        or (row.get("trade_date") and str(row["trade_date"])[:10] != day)):
                    continue
                tier, veto = int(fusion.get("tier") or 0), str(fusion.get("veto_reason") or "")
                if _is_observation(tier, veto, row.get("patterns")) and (code not in production or float(ts) < production[code]["ts"]):
                    production[code] = {"ts": float(ts), "price": float(row["price"]), "tier": tier, "veto": veto}
            except (ValueError, TypeError, AttributeError, OverflowError):
                continue
        with gzip.open(follow["sources"][day], "rt", encoding="utf-8") as stream:
            obj = json.load(stream)["result"]
        candidates.update(str(c).zfill(6) for c in (obj.get("meta") or {}).get("candidate_codes", []))
        for row in obj.get("records") or []:
            try:
                code, ts = str(row.get("code") or "").zfill(6), row.get("ts")
                tier, veto = int(row.get("tier") or 0), str(row.get("veto") or "")
                if (code in codes and _session(ts, day) and float(row.get("entry") or 0) > 0
                        and _is_observation(tier, veto, row.get("patterns"))
                        and (code not in replay or float(ts) < replay[code]["ts"])):
                    replay[code] = {"ts": float(ts), "price": float(row["entry"]), "tier": tier, "veto": veto}
            except (ValueError, TypeError, AttributeError, OverflowError):
                continue
    rows = []
    for entry in entries:
        item = dict(entry)
        code = str(item["code"]).zfill(6)
        try:
            base = float(daily.loc[(code, pd.Timestamp(start)), "close"])
        except (KeyError, ValueError, TypeError):
            base = None
        try:
            end_price = float(daily.loc[(code, pd.Timestamp(end)), "close"])
            end_source = "日线"
        except (KeyError, ValueError, TypeError):
            end_price, end_source = _next_close(cache, code, end), "分钟缓存末价"
        base = base if base and math.isfinite(base) and base > 0 else None
        end_price = end_price if end_price and math.isfinite(end_price) and end_price > 0 else None
        actual = (end_price / base - 1) * 100 if base and end_price else None
        item.update(weekly_calculated_pct=round(actual, 2) if actual is not None else None,
                    weekly_price_source=end_source if end_price else "缺失",
                    weekly_match=abs(actual - float(item["pct"])) <= 0.02 if actual is not None else None,
                    replay_candidate=code in candidates)
        for label, events in (("production", production), ("independent_replay", replay)):
            event = events.get(code)
            if event:
                event = dict(event)
                date = datetime.fromtimestamp(event["ts"]).strftime("%Y-%m-%d")
                event["time"] = datetime.fromtimestamp(event["ts"]).strftime("%Y-%m-%d %H:%M:%S")
                event["week_pct_at_event"] = round((event["price"] / base - 1) * 100, 2) if base else None
                event["remaining_to_week_end_pct"] = round((end_price / event["price"] - 1) * 100, 2) if end_price else None
                next_day = _next_cached_session(days, days.index(date)) if date in days else None
                next_price = _next_close(cache, code, next_day) if next_day else None
                event["next_day_close_pct"] = round((next_price / event["price"] - 1) * 100, 2) if next_price else None
            item[label] = event
        rows.append(item)
    return {"week": [start, end], "label_source": labels["label_source"], "replay_run": follow["run_dir"],
            "replay_independent": True, "limitations": ["周榜是事后选出的极端样本，不可用作准确率",
                "参考价到后续价格是观察差额，不代表实际成交；分钟缓存末价并非经独立确认的官方收盘价",
                "题材由用户提供，未逐条验证；新股缺失基准时周涨跌幅记为未知"], "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", default="artifacts/fusion_research/2026-10-30_用户周涨跌榜.json")
    parser.add_argument("--production-root", default=r"<INSTALL_DIR>\instockMonitorTK")
    parser.add_argument("--replay-run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.labels, encoding="utf-8") as stream:
        labels = json.load(stream)
    daily = pd.read_hdf(_find_daily_path(), key="/all_300")
    daily = daily[~daily.index.duplicated(keep="last")]
    result = audit(labels, daily, load_minute_cache(), args.production_root, args.replay_run)
    with open(args.output, "x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print("报告：{}".format(args.output))


if __name__ == "__main__":
    main()
