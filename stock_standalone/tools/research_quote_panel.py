# -*- coding: utf-8 -*-
"""固定时点全市场快照研究；仅输出统计，不生成选股或交易指令。"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ats.fusion.context import _find_daily_path


def _quotes(store, day, start, end):
    rows = store.select("/all_30", where=[f'ticktime >= Timestamp("{day} {start}")',
                                          f'ticktime <= Timestamp("{day} {end}")'],
                        columns=["close", "high", "low", "volume"]).reset_index()
    rows["code"] = rows["code"].astype(str).str.zfill(6)
    rows = rows[rows["code"].str.fullmatch(r"(?:000|001|002|003|300|301|600|601|603|605|688|689)\d{3}|(?:4|8)\d{5}|92\d{4}")]
    return rows.sort_values("ticktime").drop_duplicates("code", keep="last").set_index("code")


def panel_for_day(store, daily, day, next_day, asof="14:45"):
    """特征截至指定盘中时间；后续日期的行情只用于标签。"""
    cutoff = pd.Timestamp(day + " " + asof)
    now = _quotes(store, day, (cutoff - pd.Timedelta(minutes=3)).strftime("%H:%M:%S"), cutoff.strftime("%H:%M:%S"))
    prior = cutoff - pd.Timedelta(minutes=15)
    earlier = _quotes(store, day, (prior - pd.Timedelta(minutes=3)).strftime("%H:%M:%S"), prior.strftime("%H:%M:%S"))
    future = _quotes(store, next_day, "14:54:00", "15:05:00")
    if now.empty or future.empty:
        return pd.DataFrame()
    old = daily[daily["date"] < pd.Timestamp(day)].sort_values(["code", "date"])
    calendar = sorted(daily.loc[daily["date"] < pd.Timestamp(day), "date"].unique())
    if not calendar:
        return pd.DataFrame()
    prior_day = calendar[-1]
    last = old.groupby("code", sort=False).tail(1).set_index("code")
    last = last[last["date"] == prior_day]
    old20 = old.groupby("code", sort=False).tail(20)
    aggregates = old20.groupby("code")["close"].agg(["count", "mean"])
    oldest = old20.groupby("code")["date"].min()
    last = last.join(aggregates.rename(columns={"count": "history_n", "mean": "ma20"}))
    if len(calendar) >= 20:
        last.loc[oldest[oldest != calendar[-20]].index.intersection(last.index), "history_n"] = 0
    else:
        last["history_n"] = 0
    panel = now.join(last[["close", "history_n", "ma20"]].rename(columns={"close": "prev_close"}), how="inner")
    panel = panel.join(earlier[["close"]].rename(columns={"close": "close_1430"}), how="left")
    market = panel[(panel["close"] > 0) & (panel["prev_close"] > 0)]
    market_median = float(((market["close"] / market["prev_close"] - 1) * 100).median()) if len(market) else None
    panel = panel.join(future[["close", "high"]].rename(columns={"close": "next_close", "high": "next_high"}), how="inner")
    valid = (panel[["close", "high", "low", "prev_close", "next_close", "next_high"]] > 0).all(axis=1)
    valid &= (panel["low"] <= panel["close"]) & (panel["close"] <= panel["high"])
    valid &= panel["next_high"] >= panel["next_close"]
    panel = panel[valid].copy()
    panel["pct"] = (panel["close"] / panel["prev_close"] - 1) * 100
    panel["ret15"] = (panel["close"] / panel["close_1430"] - 1) * 100
    panel["near_high"] = panel["close"] / panel["high"]
    panel["next_close_pct"] = (panel["next_close"] / panel["close"] - 1) * 100
    panel["next_high_pct"] = (panel["next_high"] / panel["close"] - 1) * 100
    panel.attrs["market_median_pct"] = market_median
    return panel


def _stats(frame, total_positive):
    if frame.empty:
        return {"n": 0, "big_move_recall": None}
    positive = frame["next_high_pct"] >= 6
    return {"n": len(frame), "next_high_ge6": round(float(positive.mean()), 4),
            "big_move_recall": round(float(positive.sum() / total_positive), 4) if total_positive else None,
            "next_close_ge3": round(float((frame["next_close_pct"] >= 3).mean()), 4),
            "next_close_le_minus3": round(float((frame["next_close_pct"] <= -3).mean()), 4),
            "median_next_close_pct": round(float(frame["next_close_pct"].median()), 2)}


def analyze_panel(panel):
    median = panel.attrs.get("market_median_pct")
    positive = int((panel["next_high_pct"] >= 6).sum())
    valid_history = (panel["history_n"] >= 20) & (panel["ma20"] > 0)
    rules = {
        "all": pd.Series(True, index=panel.index),
        "prior_ma20_above": valid_history & (panel["close"] > panel["ma20"]),
        "intraday_relative_strength": (panel["pct"] > 0) & (panel["pct"] < 5),
        "near_day_high": panel["near_high"] >= 0.98,
        "late_rising": panel["ret15"] > 0,
        "relative_strength_and_ma20": valid_history & (panel["close"] > panel["ma20"]) & (panel["pct"] > 0) & (panel["pct"] < 5),
    }
    return {"market_median_pct": round(median, 2) if median is not None else None, "labelled_codes": len(panel),
            "next_high_ge6_count": positive, "factors": {name: _stats(panel[mask], positive) for name, mask in rules.items()}}


def compare_production(panel, root, day, asof="14:45"):
    from ats.fusion.shadow_io import day_paths, log_directories, read_paths
    directory = str(Path(root) / "logs" / "fusion_shadow")
    paths = day_paths(log_directories(directory), day)
    if not paths:
        return {"status": "missing"}
    records, errors = read_paths(paths)
    if errors:
        raise ValueError("生产影子日志不完整: {}".format(errors[:5]))
    signals = set()
    for row in records:
        try:
            origin = str(row.get("writer_exe") or "").upper()
            source = str(row.get("source") or "").lower()
            if "REPLAY" in origin or "BACKFILL" in origin or "replay" in source or row.get("writer_pid") == 0:
                continue
            stamp = datetime.fromtimestamp(float(row.get("ts") or 0))
            price, pct = float(row.get("price") or 0), float(row.get("pct", -100))
            fusion = row.get("fusion") or {}
            if (stamp.date().isoformat() != day or stamp > datetime.fromisoformat(day + " " + asof)
                    or not math.isfinite(price) or not math.isfinite(pct) or price <= 0 or pct <= -50
                    or int(fusion.get("tier") or 0) < 2 or fusion.get("veto_reason")):
                continue
            signals.add(str(row.get("code") or "").split(".")[0].zfill(6))
        except (ValueError, TypeError, OverflowError, OSError, AttributeError):
            continue
    matched = panel[panel.index.isin(signals)]
    positive = int((panel["next_high_pct"] >= 6).sum())
    missing = panel[(panel["next_high_pct"] >= 6) & ~panel.index.isin(signals)].sort_index().head(20)
    examples = []
    for code, row in missing.iterrows():
        examples.append({"code": code, "pct_at_cutoff": round(float(row["pct"]), 2),
                         "price_vs_day_high_pct": round((float(row["near_high"]) - 1) * 100, 2),
                         "above_prior_ma20": bool(row["history_n"] >= 20 and row["close"] > row["ma20"]),
                         "next_high_pct": round(float(row["next_high_pct"]), 2),
                         "next_close_pct": round(float(row["next_close_pct"]), 2)})
    return {"status": "observed" if signals else "no_usable_l2_events", "production_codes": len(signals),
            "matched_at_cutoff": len(matched), "fixed_time_outcomes": _stats(matched, positive),
            "missed_examples_by_code": examples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", default=r"G:\sina_MultiIndex_data.h5")
    parser.add_argument("--daily", default=None)
    parser.add_argument("--shadow-root", default=None)
    parser.add_argument("--times", nargs="+", default=["10:00", "13:30", "14:45"])
    parser.add_argument("--days", nargs="+", default=["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"])
    args = parser.parse_args()
    path = args.daily or _find_daily_path()
    daily = pd.read_hdf(path, key="/all_300")
    if daily[daily.index.duplicated(keep=False)].groupby(level=[0, 1]).nunique(dropna=False).gt(1).any(axis=None):
        raise ValueError("日线存在冲突重复记录")
    daily = daily[~daily.index.duplicated(keep="last")].reset_index()
    daily["code"] = daily["code"].astype(str).str.zfill(6)
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce").dt.normalize()
    output = {"method": "指定时点前实时快照与截至前日的日线，后续快照只用于标签；信号价格不代表可成交",
              "source": args.snapshots, "daily_source": path, "days": {}}
    with pd.HDFStore(args.snapshots, "r") as store:
        for day, next_day in zip(args.days, args.days[1:]):
            output["days"][day] = {"next_day": next_day, "times": {}}
            for asof in args.times:
                panel = panel_for_day(store, daily, day, next_day, asof=asof)
                result = analyze_panel(panel) if not panel.empty else {"status": "insufficient"}
                if not panel.empty and args.shadow_root:
                    result["production"] = compare_production(panel, args.shadow_root, day, asof=asof)
                output["days"][day]["times"][asof] = result
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
