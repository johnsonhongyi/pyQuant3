# -*- coding: utf-8 -*-
"""只读隔离回放档案，按兼容配置重建跨日观察；不写入生产影子流。"""
from collections import defaultdict
from datetime import datetime
import gzip
import json
import math
import os
from pathlib import Path
import time
import zlib

import numpy as np

from ats.fusion.cross_day import build_cross_day


def _manifest(directory):
    try:
        path = Path(directory) / "manifest.json"
        with path.open(encoding="utf-8-sig") as stream:
            data = json.load(stream)
        if data.get("status") != "complete" or not isinstance(data.get("completed"), list):
            return None
        return data
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def read_replay_follow(roots, asof_day, preferred_run="", price_days=(), minute_cache=None, now_ts=None, should_cancel=None):
    """按最新/指定批次配置，合并各日最新兼容档案，保留来源与坏文件提示。"""
    now = float(now_ts if now_ts is not None else time.time())
    today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    directories = []
    if preferred_run:
        directories.append(Path(preferred_run))
    for root in roots:
        try:
            directories.extend(p for p in Path(root).iterdir() if p.is_dir())
        except OSError:
            continue
    seen, runs = set(), []
    for directory in directories:
        if should_cancel and should_cancel():
            return {"rows": [], "status": "cancelled", "sources": {}, "errors": []}
        try:
            resolved = directory.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            data = _manifest(resolved)
            if data and any(str(e.get("day") or "") <= asof_day for e in data["completed"] if isinstance(e, dict)):
                runs.append((resolved, data, (resolved / "manifest.json").stat().st_mtime))
        except (OSError, TypeError, ValueError):
            continue
    if not runs:
        return {"rows": [], "status": "unavailable", "sources": {}, "errors": []}
    preferred = str(Path(preferred_run).resolve()) if preferred_run else ""
    runs.sort(key=lambda x: (str(x[0]) == preferred, x[2]), reverse=True)
    selected_run, chosen, _ = runs[0]
    fingerprint = chosen.get("config_fingerprint")
    engine = chosen.get("engine_fingerprint")
    compatible = [run for run in runs if run[0] == selected_run or (fingerprint and engine
                  and run[1].get("config_fingerprint") == fingerprint and run[1].get("engine_fingerprint") == engine)]
    replaced_days = set(chosen.get("days") or [entry.get("day") for entry in chosen["completed"]
                                              if isinstance(entry, dict)])
    files = {}
    for directory, manifest, mtime in compatible:
        for entry in manifest["completed"]:
            if not isinstance(entry, dict):
                continue
            day, name = str(entry.get("day") or ""), str(entry.get("file") or "")
            if len(day) != 10 or day > asof_day or name != day + ".json.gz":
                continue
            # 所选批次覆盖日期绝不借用其他批次；空结果也代表本次重算结果。
            if directory != selected_run and day in replaced_days:
                continue
            if day not in files or mtime > files[day][1]:
                files[day] = (directory / name, mtime)
    series, errors, sources = {}, [], {}
    for day, (path, _) in sorted(files.items()):
        if should_cancel and should_cancel():
            return {"rows": [], "status": "cancelled", "sources": {}, "errors": []}
        try:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                data = json.load(stream)
            result = data.get("result") or {}
            if result.get("day") != day or not isinstance(result.get("records"), list):
                raise ValueError("回放日期或记录无效")
            if (result.get("meta") or {}).get("records_truncated"):
                errors.append("{}：回放记录被截断".format(day))
            gap = ((data.get("summary") or {}).get("previous_observations") or {}).get("gap")
            if gap:
                errors.append("{}：{}".format(day, gap))
            grouped = defaultdict(list)
            bad_rows = 0
            for row in result["records"]:
                if not isinstance(row, dict) or not row.get("code"):
                    bad_rows += 1
                    continue
                code = str(row["code"]).split(".")[0].zfill(6)
                try:
                    ts, price = float(row.get("ts") or 0), float(row.get("entry") or 0)
                    if not code.isdigit() or len(code) != 6 or not math.isfinite(ts) or not math.isfinite(price) or ts <= 0 or price <= 0:
                        raise ValueError("invalid record")
                    if day > today or (day == today and ts > now):
                        bad_rows += 1
                        continue
                except (ValueError, TypeError, OverflowError):
                    bad_rows += 1
                    continue
                grouped[code].append({"code": code, "name": row.get("name") or "", "ts": ts,
                    "price": price, "trade_date": day, "source": "replay_archive",
                    "patterns": row.get("patterns") or [], "track": {"stage": row.get("track_stage") or ""},
                    "fusion": {"tier": row.get("tier"), "veto_reason": row.get("veto") or ""}})
            if bad_rows:
                errors.append("{}：{}条回放记录无效".format(day, bad_rows))
            series[day] = dict(grouped)
            sources[day] = str(path)
        except (OSError, EOFError, ValueError, TypeError, AttributeError, zlib.error) as exc:
            errors.append("{}：{}".format(day, exc))
    initial = build_cross_day(series, asof_day, allow_replay=True)
    if minute_cache:
        from ats.fusion.replay import MINUTE_PUBLICATION_LAG, day_bounds
        for state in initial:
            if should_cancel and should_cancel():
                return {"rows": [], "status": "cancelled", "sources": {}, "errors": []}
            code = state["code"]
            bars = minute_cache.get(code)
            if bars is None or not len(bars):
                continue
            for day in sorted(set(price_days)):
                if day < state["first_day"] or day > asof_day or day > today:
                    continue
                try:
                    start, end = day_bounds(day)
                    cutoff = min(start + 15 * 3600, now) if day == today else start + 15 * 3600
                    available = np.r_[bars["time"][1:].astype("int64") + MINUTE_PUBLICATION_LAG, np.inf]
                    mask = ((bars["time"] >= start) & (bars["time"] < end)
                            & (np.r_[bars["time"][1:], np.inf] < end) & (available <= cutoff)
                            & (available >= state["first_ts"]))
                    indices = np.flatnonzero(mask)
                    if not len(indices):
                        continue
                    i = int(indices[-1])
                    ts, price = int(available[i]), float(bars["close"][i])
                    if not math.isfinite(price) or price <= 0:
                        continue
                    existing = series.setdefault(day, {}).setdefault(code, [])
                    latest_signal = max((float(r.get("ts") or 0) for r in existing), default=0.0)
                    if ts <= latest_signal:
                        continue
                    existing.append({"code": code, "ts": ts, "price": price, "trade_date": day,
                                     "source": "replay_price_sample", "price_only": True, "fusion": {}})
                except (ValueError, TypeError, KeyError, OverflowError, OSError):
                    continue
    rows = build_cross_day(series, asof_day, allow_replay=True)
    config = chosen.get("config") if isinstance(chosen.get("config"), dict) else {}
    uses_production = config.get("use_production_history")
    independent = (uses_production is False and config.get("persist_context") is False
                   and not config.get("state_path")
                   and os.path.normcase(str(config.get("market_path") or "")) == os.path.normcase(os.devnull))
    return {"rows": rows, "status": "ready" if sources else "unavailable", "sources": sources,
            "errors": errors, "run_dir": str(selected_run), "config_fingerprint": fingerprint,
            "engine_fingerprint": engine,
            "independent": independent,
            "production_history": uses_production,
            "compatibility_note": "旧档案缺少版本指纹，仅展示所选批次" if not engine else "仅合并代码和配置指纹相同的批次"}


def compare_signal_streams(production_rows, replay_rows):
    """逐日对照同代码共同记录；不以任一来源作为另一来源的成交证据。"""
    production = {str(row.get("code")): row for row in production_rows}
    replay = {str(row.get("code")): row for row in replay_rows}
    result = {}
    for code in set(production) | set(replay):
        live, backtest = production.get(code), replay.get(code)
        if live is None or backtest is None:
            result[code] = "无生产记录" if live is None else "无回放记录"
            continue
        def daily(row):
            timeline = row.get("timeline") or []
            if timeline:
                return {d["day"]: d for d in timeline if d.get("signal_records", d.get("records", 0)) > 0}
            return {row.get("first_day"): {"first_ts": row.get("first_ts"), "first_price": row.get("reference")}}
        live_days, replay_days = daily(live), daily(backtest)
        common_days = sorted(set(live_days) & set(replay_days))
        if not common_days:
            result[code] = "无共同记录日：生产{} / 回放{}".format(live.get("first_day"), backtest.get("first_day"))
            continue
        comparisons = []
        for day in common_days:
            live_point, replay_point = live_days[day], replay_days[day]
            try:
                gap = (float(replay_point["first_ts"]) - float(live_point["first_ts"])) / 60.0
                if not math.isfinite(gap):
                    raise ValueError("记录时间无效")
                if abs(gap) <= 3:
                    reference = float(live_point["first_price"])
                    replay_price = float(replay_point["first_price"])
                    if not math.isfinite(reference) or reference <= 0 or not math.isfinite(replay_price) or replay_price <= 0:
                        raise ValueError("生产参考价无效")
                    delta = (replay_price / reference - 1) * 100
                    comparisons.append("{}首记录相差{:+.1f}分，价差{:+.2f}%".format(day, gap, delta))
                else:
                    comparisons.append("{}首记录相差{:+.1f}分，未作同刻价格比较".format(day, gap))
            except (KeyError, TypeError, ValueError, OverflowError):
                comparisons.append("{}来源时间或参考价不完整".format(day))
        result[code] = "｜".join(comparisons)
    return result
