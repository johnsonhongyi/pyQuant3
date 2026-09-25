"""Configurable next-session candidate pool and causal outcome tracker.

This module deliberately uses only the verified, precomputed daily columns. It
does not infer VWAP from price or silently substitute missing feature values.
"""
from __future__ import annotations

import hashlib
import glob
import json
import math
import os
import tempfile
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


_LOCK = threading.RLock()
_LAST_CYCLE: Dict[str, float] = {}
_FEATURES = {
    "ch_dir", "ch_slope_deg", "ch_pos", "ch_lower", "td_sell",
    "lastp1d", "lastp2d", "lastp3d", "lasto1d",
    "lasth1d", "lasth2d", "lasth3d", "lastl1d", "lastl2d", "lastl3d", "lastl4d", "lastl5d",
    "lastv1d", "lastv2d", "lastv3d", "lastv4d", "lastv5d", "per1d",
}


def _atomic_json(path: str, value: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".next_day_watch_", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError, TypeError):
        return default


def _number(value: Any) -> Optional[float]:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _normalize_code(value: Any) -> str:
    raw = str(value or "").strip().split(".", 1)[0]
    digits = "".join(ch for ch in raw if ch.isdigit())[-6:]
    return digits.zfill(6) if digits else "000000"


def _condition(row: Dict[str, Any], spec: Dict[str, Any]) -> Optional[bool]:
    field = spec.get("field")
    if field not in _FEATURES:
        return None
    actual = _number(row.get(field))
    if actual is None:
        return None
    op, expected = spec.get("op"), spec.get("value")
    if op == "between" and isinstance(expected, list) and len(expected) == 2:
        bounds = [_number(v) for v in expected]
        return None if None in bounds else bounds[0] <= actual <= bounds[1]
    expected_num = _number(expected)
    if expected_num is None:
        return None
    return {"==": lambda: actual == expected_num, ">": lambda: actual > expected_num,
            ">=": lambda: actual >= expected_num, "<": lambda: actual < expected_num,
            "<=": lambda: actual <= expected_num}.get(op, lambda: None)()


def _matches(row: Dict[str, Any], node: Any) -> Optional[bool]:
    if not isinstance(node, dict):
        return None
    if "all" in node:
        results = [_matches(row, child) for child in node["all"]]
        return False if False in results else (None if None in results else True)
    if "any" in node:
        results = [_matches(row, child) for child in node["any"]]
        return True if True in results else (None if None in results else False)
    if set(node).issuperset({"field", "op", "value"}):
        return _condition(row, node)
    return None


def _tier(row: Dict[str, Any], strategy: Dict[str, Any]) -> Optional[str]:
    values = {key: _number(row.get(key)) for key in _FEATURES}
    if any(values.get(key) is None for key in ("ch_dir", "ch_slope_deg", "ch_pos", "lastp1d", "ch_lower", "td_sell", "lasth1d", "lasth2d", "lasth3d", "lastl1d", "lastl2d", "lastl3d", "lastl4d", "lastl5d", "lastv1d", "lastv2d", "lastv3d")):
        return None
    thresholds = strategy.get("thresholds", {})
    support = (values["ch_dir"] == 1 and values["ch_slope_deg"] > thresholds.get("slope_min", 1.5)
               and thresholds.get("ch_pos_min", 5) <= values["ch_pos"] <= thresholds.get("ch_pos_max", 60)
               and values["lastp1d"] >= values["ch_lower"] * (1 - thresholds.get("support_tolerance", 0.015))
               and values["td_sell"] < thresholds.get("td_sell_max", 5))
    if not support:
        return None
    if sum(values[f"lastl{i}d"] >= values[f"lastl{i + 1}d"] * (1 - thresholds.get("low_stability_tolerance", 0.01)) for i in range(1, 5)) < thresholds.get("low_stability_count", 2):
        return None
    tier = "A"
    highs_rising = values["lasth1d"] > values["lasth2d"] > values["lasth3d"]
    lows_rising = values["lastl1d"] > values["lastl2d"] > values["lastl3d"]
    if highs_rising and lows_rising:
        tier = "B"
        vols = [values[f"lastv{i}d"] for i in (1, 2, 3)]
        ratio = vols[0] / vols[2] if vols[2] else 0
        if thresholds.get("volume_ratio_min", 1.1) <= ratio <= thresholds.get("volume_ratio_max", 2.5) and sum(vols[i] >= vols[i + 1] * thresholds.get("daily_volume_floor", 0.9) for i in (0, 1)) >= thresholds.get("volume_growth_days", 2) and max(vols) / max(min(vols), 1e-12) <= thresholds.get("volume_spike_max", 3.2):
            tier = "C"
    return tier


def _valid_config(config: Any) -> Tuple[bool, str]:
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        return False, "schema_version must be 1"
    strategies = config.get("strategies")
    if not isinstance(strategies, list):
        return False, "strategies must be a list"
    for item in strategies:
        if not isinstance(item, dict) or not item.get("strategy_id") or not isinstance(item.get("version"), (int, str)):
            return False, "each strategy needs strategy_id and version"
        if item.get("enabled") and item.get("template") != "channel_stepup":
            return False, "only the registered channel_stepup template is supported"
        if item.get("enabled") and not _expression_valid(item.get("pre_filter", {})):
            return False, f"invalid pre_filter for {item.get('strategy_id')}"
        capacity = item.get("capacity", {})
        if not isinstance(capacity, dict) or any(not isinstance(v, int) or v < 0 for v in capacity.values()):
            return False, f"invalid capacity for {item.get('strategy_id')}"
        required_fields = item.get("required_fields", [])
        if not isinstance(required_fields, list) or not set(required_fields).issubset(_FEATURES):
            return False, f"unsupported required_fields for {item.get('strategy_id')}"
        thresholds = item.get("thresholds", {})
        allowed_thresholds = {"slope_min", "ch_pos_min", "ch_pos_max", "support_tolerance", "td_sell_max",
            "low_stability_tolerance", "low_stability_count", "volume_ratio_min", "volume_ratio_max",
            "daily_volume_floor", "volume_growth_days", "volume_spike_max"}
        if not isinstance(thresholds, dict) or not set(thresholds).issubset(allowed_thresholds) or any(_number(value) is None for value in thresholds.values()):
            return False, f"invalid threshold for {item.get('strategy_id')}"
        tiers = item.get("tiers", [{"id": "A"}, {"id": "B"}, {"id": "C"}])
        rules = {"A": "support_stable", "B": "higher_highs_lows", "C": "gentle_volume_growth"}
        if not isinstance(tiers, list) or any(not isinstance(tier, dict) or rules.get(tier.get("id")) != tier.get("rule") for tier in tiers):
            return False, f"invalid tiers for {item.get('strategy_id')}"
        universe = item.get("universe", {})
        if not isinstance(universe, dict) or any(not isinstance(universe.get(key, []), list) for key in ("include_code_prefixes", "exclude_code_prefixes")):
            return False, f"invalid universe for {item.get('strategy_id')}"
        weights = item.get("rank_weights", {})
        if not isinstance(weights, dict) or any(_number(value) is None or _number(value) < 0 for value in weights.values()):
            return False, f"invalid rank_weights for {item.get('strategy_id')}"
    return True, ""


def _expression_valid(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    if "all" in node or "any" in node:
        key = "all" if "all" in node else "any"
        return isinstance(node[key], list) and bool(node[key]) and all(_expression_valid(child) for child in node[key])
    value = node.get("value")
    valid_value = (isinstance(value, list) and len(value) == 2 and all(_number(v) is not None for v in value)
                   if node.get("op") == "between" else _number(value) is not None)
    return node.get("field") in _FEATURES and node.get("op") in {"==", ">", ">=", "<", "<=", "between"} and valid_value


def _row_dict(row: Any) -> Dict[str, Any]:
    try:
        values = row.to_dict()
    except AttributeError:
        values = dict(row)
    return {str(k): (v.item() if hasattr(v, "item") else v) for k, v in values.items()}


def _candidate_row_lookup(df: Any, candidates: List[Dict[str, Any]], vwap_field: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if "code" not in getattr(df, "columns", ()) or not candidates:
        return {}
    columns = [name for name in ("code", "name", "high", "trade", "close", "percent", "dff", "category", vwap_field)
               if name and name in df.columns]
    frame = df[columns].copy()
    frame["_watch_code"] = frame["code"].map(_normalize_code)
    wanted = {item["code"] for item in candidates}
    frame = frame[frame["_watch_code"].isin(wanted)].drop_duplicates("_watch_code", keep="last").set_index("_watch_code")
    return {str(code): _row_dict(row) for code, row in frame.iterrows()}


def _sector_evidence(category: Any, snapshot: Any) -> Dict[str, Any]:
    result = {"snapshot_at": None, "matches": []}
    if not isinstance(snapshot, dict):
        return result
    names = [part.strip() for part in str(category or "").replace("；", ";").replace("，", ",").split(";")]
    names = [name for part in names for name in part.split(",") if name.strip()]
    for name in names:
        data = snapshot.get(name)
        if not isinstance(data, dict):
            continue
        clean = {key: (str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value)
                 for key, value in data.items() if key in {"score", "momentum_score", "leader", "followers", "ts", "base_score", "score_diff", "pct_diff", "follow_ratio"}}
        if clean.get("ts") is not None:
            result["snapshot_at"] = clean["ts"]
        result["matches"].append({"name": name, **clean})
    return result


def run_cycle(df: Any, *, config_path: str, data_dir: str, asof_date: str,
              target_date: str, observed_at: Optional[str] = None,
              vwap_field: Optional[str] = None, sector_snapshot: Any = None,
              source_version: Any = None, observe: bool = True) -> Dict[str, Any]:
    """Create the frozen next-session list and append candidate outcome facts."""
    if df is None or getattr(df, "empty", True):
        return {"status": "empty"}
    config = _read_json(config_path, {})
    valid, error = _valid_config(config)
    if not valid:
        return {"status": "invalid_config", "reason": error}
    if not config.get("enabled", False):
        return {"status": "disabled"}
    if vwap_field is None:
        vwap_field = config.get("vwap_field")
    observed_at = observed_at or datetime.now().astimezone().isoformat(timespec="seconds")
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    watch_path = os.path.join(data_dir, f"next_day_anomaly_watch_{target_date}.json")
    eval_path = os.path.join(data_dir, f"next_day_anomaly_eval_{target_date}.json")
    with _LOCK:
        now = datetime.fromisoformat(observed_at)
        watch = _read_json(watch_path, None)
        if watch is None:
            if now.date().isoformat() != target_date or (now.hour, now.minute) > (9, 15):
                return {"status": "not_frozen", "candidate_count": 0, "events": []}
            records = []
            invalid_by_strategy = {}
            source = df.reset_index(drop=True) if hasattr(df, "reset_index") else df
            for raw in source.to_dict("records"):
                row = _row_dict(raw)
                code = _normalize_code(row.get("code", ""))
                if len(code) != 6 or code == "000000":
                    continue
                for strategy in config["strategies"]:
                    if not strategy.get("enabled", False):
                        continue
                    match = _matches(row, strategy.get("pre_filter", {"all": [{"field": "ch_dir", "op": "==", "value": 1}]}))
                    tier = _tier(row, strategy) if strategy.get("template") == "channel_stepup" else None
                    tier_ids = {str(entry["id"]) for entry in strategy.get("tiers", [{"id": "A"}, {"id": "B"}, {"id": "C"}])}
                    if tier not in tier_ids:
                        tier = None
                    universe = strategy.get("universe", {})
                    included_prefixes = tuple(str(prefix) for prefix in universe.get("include_code_prefixes", []))
                    excluded_prefixes = tuple(str(prefix) for prefix in universe.get("exclude_code_prefixes", []))
                    if (included_prefixes and not code.startswith(included_prefixes)) or (excluded_prefixes and code.startswith(excluded_prefixes)):
                        continue
                    required = ("ch_dir", "ch_slope_deg", "ch_pos", "lastp1d", "ch_lower", "td_sell",
                                "lasth1d", "lasth2d", "lasth3d", "lastl1d", "lastl2d", "lastl3d", "lastl4d", "lastl5d",
                                "lastv1d", "lastv2d", "lastv3d") if strategy.get("template") == "channel_stepup" else ()
                    if match is None or any(_number(row.get(field)) is None for field in required):
                        invalid_by_strategy[str(strategy["strategy_id"])] = invalid_by_strategy.get(str(strategy["strategy_id"]), 0) + 1
                    # No unknown/missing feature may silently become a passing result.
                    if match is True and tier:
                        records.append({"code": code, "name": str(row.get("name", code)), "category": str(row.get("category", "")),
                            "strategy_id": str(strategy["strategy_id"]), "version": str(strategy["version"]),
                            "config_hash": digest, "tier": tier, "score": _number(strategy.get("rank_weights", {}).get(tier, {"A": 1, "B": 2, "C": 3}[tier])) or 0,
                            "reason_codes": ["channel_support", "higher_highs_lows" if tier != "A" else "support_stable"],
                            "sector_evidence": _sector_evidence(row.get("category"), sector_snapshot),
                            "feature_values": {k: row.get(k) for k in sorted(_FEATURES) if _number(row.get(k)) is not None},
                            "first_selected_date": target_date, "status": "WATCHING",
                            "phase": {"A": "STABILIZING", "B": "RISING", "C": "PRE_ACCELERATION"}[tier],
                            "followup_trading_days": int(strategy.get("followup", {}).get("trading_days", 3))})
            records.sort(key=lambda x: (-x["score"], x["code"], x["strategy_id"]))
            limited = []
            for strategy in config["strategies"]:
                if not strategy.get("enabled", False):
                    continue
                per_tier = {}
                capacity = strategy.get("capacity", {})
                for candidate in records:
                    if candidate["strategy_id"] != str(strategy["strategy_id"]):
                        continue
                    tier = candidate["tier"]
                    per_tier[tier] = per_tier.get(tier, 0) + 1
                    if per_tier[tier] <= int(capacity.get(tier, 10**9)):
                        limited.append(candidate)
            records = limited
            watch = {"schema_version": 1, "source_asof_trade_date": asof_date, "target_trade_date": target_date,
                     "generated_at": observed_at, "source_version": str(source_version if source_version is not None else digest[:16]), "config_hash": digest,
                     "universe_count": len(df), "invalid_count": invalid_by_strategy, "candidates": records}
            _atomic_json(watch_path, watch)
        if not observe:
            return {"status": "manifest_ready", "candidate_count": len(watch.get("candidates", [])),
                    "watch_path": watch_path, "eval_path": eval_path, "events": []}
        evaluation = _read_json(eval_path, {"schema_version": 1, "target_trade_date": target_date, "config_hash": watch.get("config_hash"), "candidates": {}})
        if now.date().isoformat() != target_date:
            return {"status": "manifest_ready", "candidate_count": len(watch.get("candidates", [])), "watch_path": watch_path, "eval_path": eval_path, "events": []}
        row_lookup = _candidate_row_lookup(df, watch.get("candidates", []), vwap_field)
        for candidate in watch.get("candidates", []):
            code = candidate["code"]
            row = row_lookup.get(code)
            if not row:
                item = evaluation["candidates"].setdefault(code + ":" + candidate["strategy_id"], {"candidate": candidate, "checkpoints": [], "events": []})
                if now.hour >= 15 and not any(event.get("type") == "UNVERIFIABLE" for event in item["events"]):
                    item.setdefault("candidate", candidate)["status"] = "UNVERIFIABLE"
                    item["events"].append({"type": "UNVERIFIABLE", "date": target_date, "observed_at": observed_at,
                                           "reason": "candidate_row_missing_at_target_day_close"})
                continue
            daily_high = _number(row.get("high"))
            close = _number(row.get("trade", row.get("close")))
            prior_high = _number(candidate.get("feature_values", {}).get("lasth1d"))
            sustained_high = bool(daily_high is not None and close is not None and prior_high is not None and daily_high > prior_high and close > prior_high)
            real_vwap = _number(row.get(vwap_field)) if vwap_field and vwap_field in row else None
            item = evaluation["candidates"].setdefault(code + ":" + candidate["strategy_id"], {"candidate": candidate, "checkpoints": [], "events": []})
            tracked_candidate = item.get("candidate", candidate)
            if item["checkpoints"] and item["checkpoints"][-1].get("observed_at") == observed_at:
                continue
            prior_checkpoint = item["checkpoints"][-1] if item["checkpoints"] else None
            proof_vwap = bool(real_vwap is not None and real_vwap > 0 and prior_checkpoint
                              and prior_checkpoint.get("vwap_source") == vwap_field
                              and _number(prior_checkpoint.get("vwap")) is not None
                              and real_vwap > float(prior_checkpoint["vwap"]))
            item["checkpoints"].append({"observed_at": observed_at, "phase": "market" if now.hour < 15 else "close",
                "high": daily_high, "close": close, "vwap": real_vwap, "vwap_source": vwap_field if real_vwap is not None else None,
                "sustained_high": sustained_high, "verified_vwap_rise": proof_vwap, "sector": str(row.get("category", "")),
                "sector_evidence": _sector_evidence(row.get("category"), sector_snapshot)})
            proof = sustained_high or proof_vwap
            previous_phase = tracked_candidate.get("phase", "STABILIZING")
            if sustained_high and proof_vwap and real_vwap is not None and close is not None and close >= real_vwap:
                next_phase = "ACCELERATING"
            elif proof:
                next_phase = "RISING"
            else:
                next_phase = previous_phase
            phase_order = {"STABILIZING": 0, "PRE_ACCELERATION": 1, "RISING": 2, "ACCELERATING": 3}
            if phase_order.get(next_phase, 0) > phase_order.get(previous_phase, 0):
                item["events"].append({"type": "PHASE_CHANGED", "phase_before": previous_phase,
                    "phase_after": next_phase, "observed_at": observed_at, "target_trade_date": target_date})
                tracked_candidate["phase"] = next_phase
            in_continuous_session = (now.hour, now.minute) >= (9, 30) and (now.hour, now.minute) <= (15, 0)
            prior_age = None
            if prior_checkpoint:
                try:
                    prior_age = (now - datetime.fromisoformat(prior_checkpoint["observed_at"])).total_seconds()
                except (KeyError, TypeError, ValueError):
                    prior_age = None
            if (in_continuous_session and proof and prior_age is not None and 0 < prior_age <= 8
                    and (prior_checkpoint.get("sustained_high") or prior_checkpoint.get("verified_vwap_rise"))):
                if not any(e.get("type") == "NEXT_DAY_WATCH_CONFIRM" for e in item["events"]):
                    event = {"type": "NEXT_DAY_WATCH_CONFIRM", "event_id": "%s:%s:%s:first_confirm" %
                             (target_date, code, candidate["strategy_id"]), "target_trade_date": target_date,
                             "code": code, "name": candidate.get("name", code), "strategy_id": candidate["strategy_id"],
                             "version": candidate["version"], "config_hash": candidate["config_hash"],
                             "observed_at": observed_at, "action": "WATCH", "reason": "两帧确认：持续新高或真实 VWAP 上移",
                             "price": close or 0.0, "pct": _number(row.get("percent")) or 0.0,
                             "deviation": _number(row.get("dff")) or 0.0, "sector_name": str(row.get("category", "")),
                             "sector_snapshot_ts": _sector_evidence(row.get("category"), sector_snapshot).get("snapshot_at"),
                             "evidence": {"sustained_high": sustained_high, "verified_vwap_rise": proof_vwap,
                                          "vwap": real_vwap, "vwap_source": vwap_field if real_vwap is not None else None,
                                          "confirm_frames": 2, "first_observed_at": prior_checkpoint["observed_at"]}}
                    item["events"].append(event)
            has_vwap_observation = any(point.get("vwap") is not None for point in item["checkpoints"])
            if now.hour >= 15 and not proof and (daily_high is None or close is None or not has_vwap_observation):
                if not any(e.get("type") == "UNVERIFIABLE" for e in item["events"]):
                    item["events"].append({"type": "UNVERIFIABLE", "date": target_date, "observed_at": observed_at,
                                           "reason": "missing_price_or_verified_vwap_observation"})
                    tracked_candidate["status"] = "UNVERIFIABLE"
            elif now.hour >= 15 and not proof and not any(e["type"] == "DAY_MISS" for e in item["events"]):
                item["events"].append({"type": "DAY_MISS", "date": target_date, "observed_at": observed_at,
                                       "reason": "no_sustained_high_and_verified_vwap_did_not_rise"})
                tracked_candidate["status"] = "DAY_MISS"
            elif proof and any(e["type"] == "DAY_MISS" for e in item["events"]):
                if not any(e["type"] == "DELAYED" for e in item["events"]):
                    item["events"].append({"type": "DELAYED", "date": now.date().isoformat(), "observed_at": observed_at})
                tracked_candidate["status"] = "DELAYED"
                tracked_candidate["phase"] = "RISING"
            elif proof:
                tracked_candidate["status"] = "EARLY_VALID"
        evaluation["updated_at"] = observed_at
        _atomic_json(eval_path, evaluation)
        # Later strength is recorded against its original cohort as DELAYED; it never
        # rewrites the target-day DAY_MISS event or its date.
        for prior_watch_path in glob.glob(os.path.join(data_dir, "next_day_anomaly_watch_*.json")):
            prior_watch = _read_json(prior_watch_path, {})
            prior_date = str(prior_watch.get("target_trade_date", ""))
            if not prior_date or prior_date >= target_date:
                continue
            prior_eval_path = os.path.join(data_dir, "next_day_anomaly_eval_%s.json" % prior_date)
            prior_eval = _read_json(prior_eval_path, {})
            changed = False
            for item in prior_eval.get("candidates", {}).values():
                prior_types = {event.get("type") for event in item.get("events", [])}
                if not (prior_types & {"DAY_MISS", "UNVERIFIABLE"}) or prior_types & {"DELAYED", "MISSED"}:
                    continue
                candidate = item.get("candidate", {})
                try:
                    from JohnsonUtil import commonTips as _cct
                    elapsed_days = int(_cct.a_trade_calendar.get_trade_days_interval(prior_date, target_date))
                    if elapsed_days > int(candidate.get("followup_trading_days", 3)):
                        item["events"].append({"type": "MISSED", "date": target_date, "observed_at": observed_at,
                                               "reason": "followup_window_expired_after_day_miss"})
                        candidate["status"] = "MISSED"
                        changed = True
                        continue
                    code = candidate["code"]
                    row = _candidate_row_lookup(df, [candidate], vwap_field).get(code)
                    if not row:
                        continue
                    high, close = _number(row.get("high")), _number(row.get("trade", row.get("close")))
                    prior_high = _number(candidate.get("feature_values", {}).get("lasth1d"))
                    if high is not None and close is not None and prior_high is not None and high > prior_high and close > prior_high:
                        item["events"].append({"type": "DELAYED", "date": target_date, "observed_at": observed_at,
                                               "reason": "later_sustained_high_after_target_day_miss"})
                        candidate["status"] = "DELAYED"
                        changed = True
                except Exception:
                    continue
            if changed:
                prior_eval["updated_at"] = observed_at
                _atomic_json(prior_eval_path, prior_eval)
                stats_path = os.path.join(data_dir, "next_day_anomaly_stats_%s.json" % prior_date)
                old_stats = _read_json(stats_path, {})
                for stat in old_stats.get("strategies", []):
                    matching = [entry for entry in prior_eval.get("candidates", {}).values()
                                if entry.get("candidate", {}).get("strategy_id") == stat.get("strategy_id")
                                and str(entry.get("candidate", {}).get("version")) == str(stat.get("version"))]
                    stat["delayed"] = sum(any(event.get("type") == "DELAYED" for event in entry.get("events", [])) for entry in matching)
                    stat["missed"] = sum(any(event.get("type") == "MISSED" for event in entry.get("events", [])) for entry in matching)
                if old_stats:
                    old_stats["updated_at"] = observed_at
                    _atomic_json(stats_path, old_stats)
        stats = {}
        for candidate in watch.get("candidates", []):
            item = evaluation["candidates"].get(candidate.get("code", "") + ":" + candidate.get("strategy_id", ""), {})
            key = str(candidate.get("strategy_id", "")) + ":" + str(candidate.get("version", ""))
            bucket = stats.setdefault(key, {"strategy_id": candidate.get("strategy_id"), "version": candidate.get("version"),
                "candidate_count": 0, "day_miss": 0, "delayed": 0, "early_valid": 0, "missed": 0,
                "unverifiable": 0, "vwap_unavailable": 0})
            bucket["candidate_count"] += 1
            types = {event.get("type") for event in item.get("events", [])}
            bucket["day_miss"] += int("DAY_MISS" in types)
            bucket["delayed"] += int("DELAYED" in types)
            bucket["missed"] += int("MISSED" in types)
            evaluated_candidate = item.get("candidate", candidate)
            bucket["early_valid"] += int(evaluated_candidate.get("status") == "EARLY_VALID")
            bucket["unverifiable"] += int("UNVERIFIABLE" in types)
            bucket["vwap_unavailable"] += int(not any(point.get("vwap") is not None for point in item.get("checkpoints", [])))
        _atomic_json(os.path.join(data_dir, "next_day_anomaly_stats_%s.json" % target_date),
                     {"target_trade_date": target_date, "updated_at": observed_at, "strategies": list(stats.values())})
        events_to_send = [event for item in evaluation["candidates"].values() for event in item.get("events", [])
                          if event.get("type") == "NEXT_DAY_WATCH_CONFIRM" and not event.get("delivered")]
        return {"status": "ok", "candidate_count": len(watch.get("candidates", [])), "watch_path": watch_path, "eval_path": eval_path, "events": events_to_send}


def mark_events_delivered(data_dir: str, target_date: str, event_ids: Iterable[str]) -> None:
    """Persist successful pipe handoff so failed/offline delivery is retried next cycle."""
    ids = set(str(event_id) for event_id in event_ids)
    if not ids:
        return
    path = os.path.join(data_dir, "next_day_anomaly_eval_%s.json" % target_date)
    with _LOCK:
        evaluation = _read_json(path, {})
        changed = False
        for item in evaluation.get("candidates", {}).values():
            for event in item.get("events", []):
                if event.get("event_id") in ids:
                    event["delivered"] = True
                    changed = True
        if changed:
            _atomic_json(path, evaluation)
