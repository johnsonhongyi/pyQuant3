# -*- coding: utf-8 -*-
"""只读日线研究：以前一日收盘结构解释次日开盘后的异动，不生成交易指令。"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ats.fusion.context import _find_daily_path


def prepare_daily(frame):
    """返回数据中相邻日期、至少 20 个连续已观测交易日的研究样本。"""
    duplicate = frame[frame.index.duplicated(keep=False)]
    if not duplicate.empty and duplicate.groupby(level=[0, 1]).nunique(dropna=False).gt(1).any(axis=None):
        raise ValueError("日线存在同代码同日冲突记录，无法安全去重")
    frame = frame[~frame.index.duplicated(keep="last")].reset_index()
    frame["code"] = frame["code"].astype(str).str.zfill(6)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame[frame["code"].str.fullmatch(r"(?:000|001|002|003|300|301|600|601|603|605|688|689)\d{3}|(?:4|8)\d{5}|92\d{4}")]
    frame = frame.dropna(subset=["date", "open", "high", "low", "close", "vol"])
    frame = frame.sort_values(["code", "date"]).copy()
    sessions = sorted(frame["date"].unique())
    session_index = {d: i for i, d in enumerate(sessions)}
    frame["session"] = frame["date"].map(session_index)
    grouped = frame.groupby("code", sort=False)
    frame["prev_close"] = grouped["close"].shift(1)
    frame["prev_session"] = grouped["session"].shift(1)
    frame["old_session"] = grouped["session"].shift(19)
    frame["next_session"] = grouped["session"].shift(-1)
    for column in ("open", "high", "low", "close", "vol"):
        frame["next_" + column] = grouped[column].shift(-1)
    frame["ma5"] = grouped["close"].transform(lambda x: x.rolling(5, min_periods=5).mean())
    frame["ma20"] = grouped["close"].transform(lambda x: x.rolling(20, min_periods=20).mean())
    frame["high20_prior"] = grouped["high"].transform(lambda x: x.shift(1).rolling(20, min_periods=20).max())
    frame["vol5_prior"] = grouped["vol"].transform(lambda x: x.shift(1).rolling(5, min_periods=5).mean())
    frame["close5_prior"] = grouped["close"].shift(5)
    frame["pct"] = (frame["close"] / frame["prev_close"] - 1) * 100
    market_sample = frame[(frame["session"] - frame["prev_session"] == 1)
                          & (frame["close"] > 0) & (frame["prev_close"] > 0)]
    median_by_day = market_sample.groupby("date")["pct"].median()
    frame["market_median_pct"] = frame["date"].map(median_by_day)
    frame["ret5"] = (frame["close"] / frame["close5_prior"] - 1) * 100
    frame["vol_ratio"] = frame["vol"] / frame["vol5_prior"]
    frame["close_position"] = (frame["close"] - frame["low"]) / (frame["high"] - frame["low"]).replace(0, np.nan)
    frame["next_high_pct"] = (frame["next_high"] / frame["next_open"] - 1) * 100
    frame["next_close_pct"] = (frame["next_close"] / frame["next_open"] - 1) * 100
    frame["next_low_pct"] = (frame["next_low"] / frame["next_open"] - 1) * 100
    frame["next_gap_pct"] = (frame["next_open"] / frame["close"] - 1) * 100
    valid = (
        (frame["session"] - frame["old_session"] == 19)
        & (frame["session"] - frame["prev_session"] == 1)
        & (frame["next_session"] - frame["session"] == 1)
        & (frame[["open", "high", "low", "close", "vol", "next_open", "next_high", "next_low", "next_close", "next_vol"]] > 0).all(axis=1)
        & (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
        & (frame["next_high"] >= frame[["next_open", "next_close", "next_low"]].max(axis=1))
        & (frame["next_low"] <= frame[["next_open", "next_close"]].min(axis=1))
        & frame[["ma5", "ma20", "high20_prior", "vol5_prior", "close_position"]].notna().all(axis=1)
    )
    # 排除开盘即达到常见涨停阈值的样本；ST、停牌及真实盘口仍需独立核验。
    limit = np.where(frame["code"].str.startswith(("300", "301", "688", "689")), 19.5,
                     np.where(frame["code"].str.startswith(("4", "8", "92")), 29.5, 9.5))
    valid &= frame["next_gap_pct"] < limit
    return frame.loc[valid].copy()


def summarize(frame):
    if frame.empty:
        return {"n": 0, "high_ge_6_pct": None, "close_ge_3_pct": None, "low_le_minus3_pct": None, "median_close_pct": None}
    return {"n": len(frame), "high_ge_6_pct": round(float((frame["next_high_pct"] >= 6).mean()), 4),
            "close_ge_3_pct": round(float((frame["next_close_pct"] >= 3).mean()), 4),
            "low_le_minus3_pct": round(float((frame["next_low_pct"] <= -3).mean()), 4),
            "median_close_pct": round(float(frame["next_close_pct"].median()), 2)}


def analyze(frame, holdout_days=5):
    dates = sorted(frame["date"].unique())
    if len(dates) <= holdout_days:
        raise ValueError("可用研究日期不足以保留独立日期")
    split = dates[-holdout_days]
    rules = {
        "all": pd.Series(True, index=frame.index),
        "close_above_ma5_and_ma20": (frame["close"] > frame["ma5"]) & (frame["close"] > frame["ma20"]),
        "near_prior_20d_high": (frame["close"] >= frame["high20_prior"] * 0.98) & (frame["pct"] > 0) & (frame["pct"] < 7),
        "rising_volume_strong_close": (frame["pct"] > 0) & (frame["pct"] < 7) & (frame["vol_ratio"] >= 1.2) & (frame["close_position"] >= 0.7),
        "pullback_reclaim": (frame["ret5"] > 0) & (frame["pct"] > 0) & (frame["pct"] < 5) & (frame["close"] > frame["ma5"]) & (frame["close_position"] >= 0.7),
        "weak_market_all": frame["market_median_pct"] <= -0.5,
        "weak_market_relative_strength": (frame["market_median_pct"] <= -0.5) & (frame["pct"] > 0) & (frame["pct"] < 5),
    }
    result = {"method": "日线收盘后已知结构；标签为数据中下一交易日开盘到最高/最低/收盘，不代表成交或收益；不修改策略",
              "limitations": ["未验证交易日历及停牌复权，历史数据可信度待核", "当日收盘特征不能冒充收盘前实时信号",
                              "时间留出样本先前已用于项目研究，不是严格盲测"],
              "holdout_start": str(pd.Timestamp(split).date()), "rules": {}, "days": [], "board_strata": {}}
    for name, mask in rules.items():
        result["rules"][name] = {"development": summarize(frame[mask & (frame["date"] < split)]),
                                 "holdout": summarize(frame[mask & (frame["date"] >= split)])}
    for date in dates:
        d = frame[frame["date"] == date]
        result["days"].append({"date": str(pd.Timestamp(date).date()), "all": summarize(d),
                               "trend": summarize(d[rules["close_above_ma5_and_ma20"].loc[d.index]]),
                               "next_day_big_moves": int((d["next_high_pct"] >= 6).sum())})
    for name, board in (("20pct_boards", frame["code"].str.startswith(("300", "301", "688", "689"))),
                        ("other_boards", ~frame["code"].str.startswith(("300", "301", "688", "689")))):
        result["board_strata"][name] = {}
        for period, time_mask in (("development", frame["date"] < split), ("holdout", frame["date"] >= split)):
            subset = frame[board & time_mask]
            result["board_strata"][name][period] = {
                "all": summarize(subset),
                "trend": summarize(subset[rules["close_above_ma5_and_ma20"].loc[subset.index]]),
            }
    return result


def analyze_shadow(frame, root):
    """仅用截止当日 14:45 已记录的生产事件，按股票和日期去重。"""
    from datetime import datetime

    labelled = frame.set_index(["date", "code"])
    reports = []
    from ats.fusion.shadow_io import day_paths, log_days, log_directories, read_paths
    directories = log_directories(str(Path(root) / "logs" / "fusion_shadow"))
    for day_text in log_days(directories):
        day = pd.Timestamp(day_text)
        if day not in labelled.index.get_level_values(0):
            continue
        first = {}
        records, read_errors = read_paths(day_paths(directories, day_text))
        errors, invalid, excluded = len(read_errors), 0, 0
        for row in records:
            try:
                origin = str(row.get("writer_exe") or "").upper()
                source = str(row.get("source") or "").lower()
                if "REPLAY" in origin or "BACKFILL" in origin or "replay" in source or row.get("writer_pid") == 0:
                    excluded += 1
                    continue
                ts = float(row.get("ts") or 0)
                stamp = datetime.fromtimestamp(ts)
                code = str(row.get("code") or "").split(".")[0].zfill(6)
                if stamp.date().isoformat() != day_text or stamp.strftime("%H:%M:%S") > "14:45:00":
                    continue
                price, pct = float(row.get("price") or 0), float(row.get("pct", -100))
                if not math.isfinite(price) or not math.isfinite(pct) or price <= 0 or pct <= -50:
                    invalid += 1
                    continue
                fusion = row.get("fusion") or {}
                if int(fusion.get("tier") or 0) < 2 or fusion.get("veto_reason"):
                    continue
                if (day, code) not in labelled.index:
                    continue
                old = first.get(code)
                if old is None or ts < old["ts"]:
                    first[code] = {"ts": ts, "patterns": list(row.get("patterns") or [])}
            except (ValueError, TypeError, OverflowError, OSError, AttributeError):
                errors += 1
        selected = labelled.loc[[(day, code) for code in first]] if first else frame.iloc[0:0]
        universe = frame[frame["date"] == day]
        positive = set(universe.loc[universe["next_high_pct"] >= 6, "code"])
        captured = positive & set(first)
        patterns = {}
        for code, event in first.items():
            for pattern in set(event["patterns"]):
                patterns.setdefault(pattern, []).append(code)
        pattern_stats = {name: summarize(labelled.loc[[(day, code) for code in codes]])
                         for name, codes in patterns.items() if len(codes) >= 5}
        reports.append({"date": day_text, "signal": summarize(selected), "universe": summarize(universe),
                        "status": "observed" if first else "no_usable_l2_events",
                        "positive_codes_seen": len(captured), "positive_universe": len(positive),
                        "recall": round(len(captured) / len(positive), 4) if positive and first else None,
                        "invalid_rows": invalid, "excluded_backfill": excluded, "parse_errors": errors,
                        "first_signal_patterns": pattern_stats})
    return reports


def analyze_shadow_to_minute_close(replay, root):
    """比较生产首个 L2+ 记录价与下一缓存日收盘；不模拟成交。"""
    from datetime import datetime
    from ats.fusion.iteration import _next_cached_session
    from ats.fusion.replay import day_bounds
    from ats.fusion.context import get_daily_context

    available = replay.days()
    context = get_daily_context()
    reports = []
    for index, day in enumerate(available):
        next_day = _next_cached_session(available, index)
        from ats.fusion.shadow_io import day_paths, log_directories, read_paths
        directory = str(Path(root) / "logs" / "fusion_shadow")
        paths = day_paths(log_directories(directory), day)
        if not paths:
            continue
        rows, errors = read_paths(paths)
        if errors:
            raise ValueError("生产影子日志不完整: {}".format(errors[:5]))
        first = {}
        for row in rows:
            try:
                origin = str(row.get("writer_exe") or "").upper()
                source = str(row.get("source") or "").lower()
                if "REPLAY" in origin or "BACKFILL" in origin or "replay" in source or row.get("writer_pid") == 0:
                    continue
                ts = float(row.get("ts") or 0)
                stamp = datetime.fromtimestamp(ts)
                if stamp.date().isoformat() != day or stamp.strftime("%H:%M:%S") > "14:45:00":
                    continue
                code = str(row.get("code") or "").split(".")[0].zfill(6)
                price, pct = float(row.get("price") or 0), float(row.get("pct", -100))
                fusion = row.get("fusion") or {}
                if (not math.isfinite(price) or not math.isfinite(pct) or price <= 0 or pct <= -50
                        or int(fusion.get("tier") or 0) < 2 or fusion.get("veto_reason")):
                    continue
                if code not in first or ts < first[code]["ts"]:
                    first[code] = {"ts": ts, "price": price, "pct": pct,
                                   "vwap": float(row.get("vwap") or 0),
                                   "patterns": list(row.get("patterns") or [])}
            except (ValueError, TypeError, OverflowError, OSError, AttributeError):
                continue
        returns = []
        cohorts = {}
        if next_day:
            start, _ = day_bounds(next_day)
            for code, event in first.items():
                bars = replay.cache.get(code)
                if bars is None or not len(bars):
                    continue
                idx = np.flatnonzero((bars["time"] >= start + 9 * 3600 + 30 * 60)
                                     & (bars["time"] <= start + 15 * 3600 + 3 * 60))
                if (len(idx) < 50 or bars["time"][idx[0]] > start + 9 * 3600 + 33 * 60
                        or bars["time"][idx[-1]] < start + 14 * 3600 + 54 * 60):
                    continue
                close = float(bars["close"][idx[-1]])
                if close > 0:
                    result = (close / event["price"] - 1) * 100
                    returns.append(result)
                    pct = event["pct"]
                    key = ("pct_negative" if pct < 0 else "pct_0_to_3" if pct < 3 else
                           "pct_3_to_6" if pct < 6 else "pct_6_plus")
                    cohorts.setdefault(key, []).append(result)
                    # 旧日线不能伪装成昨日结构；只在上一缓存交易日有日线时分组。
                    series = context._by_code.get(code) if context.ok else None
                    prior_day = available[index - 1] if index > 0 else None
                    dates = series["dates"].astype("datetime64[D]") if series is not None else np.array([])
                    dc = context.asof(code, day) if prior_day and np.datetime64(prior_day) in dates else {}
                    ma5, ma20 = float(dc.get("ma5") or 0), float(dc.get("ma20") or 0)
                    if ma5 > 0 and ma20 > 0:
                        key = "above_ma5_ma20" if event["price"] > max(ma5, ma20) else "below_ma5_or_ma20"
                        cohorts.setdefault(key, []).append(result)
                    if event["vwap"] > 0 and math.isfinite(event["vwap"]):
                        key = "above_intraday_vwap" if event["price"] >= event["vwap"] else "below_intraday_vwap"
                        cohorts.setdefault(key, []).append(result)
                    for pattern in event["patterns"]:
                        cohorts.setdefault("pattern:" + pattern, []).append(result)
        cohort_stats = {name: {"n": len(values), "above_signal": round(float(np.mean(np.array(values) > 0)), 4),
                               "close_le_minus3_pct": round(float(np.mean(np.array(values) <= -3)), 4),
                               "median_pct": round(float(np.median(values)), 2)}
                        for name, values in cohorts.items() if len(values) >= 5}
        reports.append({"date": day, "next_day": next_day, "signal_codes": len(first),
                        "labelled": len(returns), "close_above_signal": round(float(np.mean(np.array(returns) > 0)), 4) if returns else None,
                        "close_ge_3_pct": round(float(np.mean(np.array(returns) >= 3)), 4) if returns else None,
                        "close_le_minus3_pct": round(float(np.mean(np.array(returns) <= -3)), 4) if returns else None,
                        "median_close_vs_signal_pct": round(float(np.median(returns)), 2) if returns else None,
                        "cohorts": cohort_stats})
    return reports


def verify_shadow_quote_prices(root, snapshot_path):
    """将生产信号价与同代码此前最近一笔快照核对，最多容忍 180 秒。"""
    from datetime import datetime

    reports = []
    with pd.HDFStore(snapshot_path, mode="r") as store:
        from ats.fusion.shadow_io import day_paths, log_days, log_directories, read_paths
        directories = log_directories(str(Path(root) / "logs" / "fusion_shadow"))
        for day in log_days(directories):
            first = {}
            records, read_errors = read_paths(day_paths(directories, day))
            if read_errors:
                raise ValueError("生产影子日志不完整: {}".format(read_errors[:5]))
            for row in records:
                try:
                    origin = str(row.get("writer_exe") or "").upper()
                    source = str(row.get("source") or "").lower()
                    if "REPLAY" in origin or "BACKFILL" in origin or "replay" in source or row.get("writer_pid") == 0:
                        continue
                    ts = float(row.get("ts") or 0)
                    stamp = datetime.fromtimestamp(ts)
                    code = str(row.get("code") or "").split(".")[0].zfill(6)
                    price, pct = float(row.get("price") or 0), float(row.get("pct", -100))
                    fusion = row.get("fusion") or {}
                    if (stamp.date().isoformat() != day or stamp.strftime("%H:%M:%S") > "14:45:00"
                            or not math.isfinite(price) or not math.isfinite(pct) or price <= 0 or pct <= -50
                            or int(fusion.get("tier") or 0) < 2 or fusion.get("veto_reason")):
                        continue
                    if code not in first or ts < first[code]["ts"]:
                        first[code] = {"ts": ts, "price": price}
                except (ValueError, TypeError, OverflowError, OSError, AttributeError):
                    continue
            if not first:
                reports.append({"date": day, "signal_codes": 0, "matched": 0})
                continue
            quotes = store.select("/all_30", where=[f'ticktime >= Timestamp("{day} 09:25:00")',
                                                     f'ticktime <= Timestamp("{day} 14:45:00")'],
                                  columns=["close"]).reset_index()
            quotes = quotes[quotes["code"].isin(first)].sort_values("ticktime")
            groups = {code: rows for code, rows in quotes.groupby("code")}
            errors = []
            for code, signal in first.items():
                rows = groups.get(code)
                if rows is None:
                    continue
                stamp = pd.Timestamp(datetime.fromtimestamp(signal["ts"]))
                pos = int(rows["ticktime"].searchsorted(stamp, side="right")) - 1
                if pos < 0:
                    continue
                quote = rows.iloc[pos]
                if (stamp - quote["ticktime"]).total_seconds() > 180 or quote["close"] <= 0:
                    continue
                errors.append(abs(signal["price"] / float(quote["close"]) - 1) * 100)
            reports.append({"date": day, "signal_codes": len(first), "matched": len(errors),
                            "median_abs_price_difference_pct": round(float(np.median(errors)), 4) if errors else None,
                            "over_1pct": int(np.sum(np.array(errors) > 1))})
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily", default=None, help="只读日线 HDF 路径")
    parser.add_argument("--holdout-days", type=int, default=5)
    parser.add_argument("--shadow-root", default=None, help="生产影子流根目录；只读")
    parser.add_argument("--quote-snapshots", default=None, help="逐时行情 HDF；仅用于生产信号价交叉核验")
    args = parser.parse_args()
    path = args.daily or _find_daily_path()
    if not path:
        raise SystemExit("找不到日线数据")
    frame = pd.read_hdf(path, key="/all_300")
    prepared = prepare_daily(frame)
    result = analyze(prepared, args.holdout_days)
    if args.shadow_root:
        result["production_shadow"] = analyze_shadow(prepared, args.shadow_root)
        from ats.fusion.replay import DayReplay
        result["production_shadow_to_minute_close"] = analyze_shadow_to_minute_close(DayReplay(), args.shadow_root)
        if args.quote_snapshots:
            result["production_quote_check"] = verify_shadow_quote_prices(args.shadow_root, args.quote_snapshots)
    result["source"] = path
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
