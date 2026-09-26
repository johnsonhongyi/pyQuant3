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
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


_LOCK = threading.RLock()
_LAST_CYCLE: Dict[str, float] = {}
_HISTORY_INDEX_CACHE: Dict[str, Any] = {}
_HISTORY_INDEX_TTL_SEC = 30.0
_FEATURES = {
    "ch_dir", "ch_slope_deg", "ch_pos", "ch_lower", "td_sell",
    "lastp1d", "lastp2d", "lastp3d", "lasto1d",
    "lasth1d", "lasth2d", "lasth3d", "lastl1d", "lastl2d", "lastl3d", "lastl4d", "lastl5d",
    "lastv1d", "lastv2d", "lastv3d", "lastv4d", "lastv5d", "per1d",
}


def _atomic_json(path: str, value: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as current_stream:
            if json.load(current_stream) == value:
                return
    except (OSError, ValueError, TypeError):
        pass
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    fd, tmp = tempfile.mkstemp(prefix=".next_day_watch_", suffix=".tmp", dir=os.path.dirname(path))
    replaced = False
    preserve_temp = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(tmp, path)
            replaced = True
        except OSError:
            quarantine_dir = os.path.join(os.path.dirname(path), ".next_day_watch_quarantine")
            os.makedirs(quarantine_dir, exist_ok=True)
            stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
            quarantine_path = os.path.join(quarantine_dir, "%s.%s.%s.tmp" %
                (os.path.basename(path), stamp, threading.get_ident()))
            try:
                os.replace(tmp, quarantine_path)
                tmp = quarantine_path
            except OSError:
                # Keep the same-directory temp if even quarantine rename is blocked.
                pass
            metadata = {
                "target": os.path.abspath(path),
                "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                "schema_version": value.get("schema_version", value.get("snapshot_version", value.get("version")))
                    if isinstance(value, dict) else None,
                "payload_timestamp": _payload_timestamp(value) if isinstance(value, dict) else None,
            }
            try:
                with open(tmp + ".meta.json", "w", encoding="utf-8") as meta_stream:
                    json.dump(metadata, meta_stream, ensure_ascii=False, indent=2)
                    meta_stream.flush()
                    os.fsync(meta_stream.fileno())
                preserve_temp = True
            except OSError:
                preserve_temp = os.path.exists(tmp)
            raise
    finally:
        if not replaced and not preserve_temp:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass


def _payload_timestamp(value: Dict[str, Any]) -> Optional[str]:
    for key in ("updated_at", "generated_at", "timestamp", "observed_at"):
        stamp = value.get(key)
        if stamp:
            return str(stamp)
    return None


def _validate_quarantined_json(temp_path: str, target_path: str) -> bool:
    """Fail-closed gate for any future manual recovery of a quarantined write."""
    try:
        with open(temp_path + ".meta.json", "r", encoding="utf-8") as stream:
            metadata = json.load(stream)
        with open(temp_path, "rb") as stream:
            raw = stream.read()
        if metadata.get("target") != os.path.abspath(target_path):
            return False
        if hashlib.sha256(raw).hexdigest() != metadata.get("sha256"):
            return False
        candidate = json.loads(raw.decode("utf-8"))
        if not isinstance(candidate, dict) or not _payload_timestamp(candidate):
            return False
        candidate_version = candidate.get("schema_version", candidate.get("snapshot_version", candidate.get("version")))
        if candidate_version != metadata.get("schema_version"):
            return False
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8") as stream:
                current = json.load(stream)
            if not isinstance(current, dict):
                return False
            current_version = current.get("schema_version", current.get("snapshot_version", current.get("version")))
            if current_version != candidate_version:
                return False
            current_stamp = _payload_timestamp(current)
            if current_stamp and _timestamp_key(_payload_timestamp(candidate)) <= _timestamp_key(current_stamp):
                return False
        return True
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _timestamp_key(value: Optional[str]) -> str:
    try:
        return datetime.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        return str(value or "")


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


_CODE_ALIASES = ("code", "symbol", "ts_code", "ticker", "证券代码", "股票代码", "代码")


def _source_with_code(df: Any) -> Any:
    """Return a frame with a canonical code column, preserving code indexes."""
    columns = list(getattr(df, "columns", ()))
    by_lower = {str(column).strip().lower(): column for column in columns}
    code_column = next((by_lower[name] for name in _CODE_ALIASES if name in by_lower), None)
    frame = df
    if code_column is None and hasattr(df, "reset_index"):
        index_name = getattr(getattr(df, "index", None), "name", None)
        index_key = str(index_name).strip().lower() if index_name is not None else ""
        if index_key in _CODE_ALIASES:
            frame = df.reset_index()
            code_column = next((c for c in frame.columns if str(c).strip().lower() == index_key), None)
        elif "index" not in by_lower:
            # Some ATS wide frames use an unnamed stock-code index. Accept it
            # only when almost all values look like actual 4-6 digit codes.
            values = list(getattr(df.index, "tolist", lambda: [])())
            code_like = sum(1 for value in values if len("".join(ch for ch in str(value) if ch.isdigit())) in (4, 5, 6))
            if values and code_like / len(values) >= 0.8:
                frame = df.reset_index()
                code_column = frame.columns[0]
    if code_column is not None and str(code_column) != "code":
        frame = frame.copy()
        frame["code"] = frame[code_column]
    return frame


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


def _trend_score(row: Dict[str, Any]) -> float:
    """Rank admitted candidates by their measured price/volume structure (0..100)."""
    def n(key: str) -> float:
        return _number(row.get(key)) or 0.0

    def clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    slope = clamp((n("ch_slope_deg") - 1.5) / 33.5, 0.0, 1.0) * 22.0
    structure_checks = [
        n("lasth1d") > n("lasth2d"), n("lasth2d") > n("lasth3d"),
        n("lastl1d") > n("lastl2d"), n("lastl2d") > n("lastl3d"),
        n("lastl3d") > n("lastl4d"), n("lastl4d") > n("lastl5d"),
    ]
    structure = sum(structure_checks) / len(structure_checks) * 24.0
    position = n("ch_pos")
    position_score = (5.0 + (position - 5.0) * 0.25 if position <= 45.0
                      else 15.0 - (position - 45.0) * 0.25)
    position_score = clamp(position_score, 0.0, 15.0)
    volume_ratio = n("lastv1d") / max(n("lastv3d"), 1e-12)
    volume_score = clamp((volume_ratio - 0.7) / 1.1, 0.0, 1.0) * 18.0
    volume_score += 2.0 * sum(n(f"lastv{i}d") >= n(f"lastv{i + 1}d") * 0.9 for i in (1, 2))
    support_pct = (n("lastp1d") / max(n("ch_lower"), 1e-12) - 1.0) * 100.0
    if support_pct < 0:
        support_score = clamp((support_pct + 1.5) / 1.5, 0.0, 1.0) * 4.0
    elif support_pct <= 2.0:
        support_score = 4.0 + support_pct * 4.0
    elif support_pct <= 5.0:
        support_score = 12.0 + (support_pct - 2.0) * (4.0 / 3.0)
    else:
        support_score = clamp(16.0 - (support_pct - 5.0) * 1.6, 0.0, 16.0)
    td_score = clamp(5.0 - n("td_sell"), 0.0, 5.0)
    return round(clamp(slope + structure + position_score + volume_score + support_score + td_score, 0.0, 100.0), 1)


def _trend_rating(score: float) -> str:
    if score >= 80:
        return "强势"
    if score >= 65:
        return "健康"
    if score >= 50:
        return "跟踪"
    return "偏弱"


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
    configured = {field for field, _label in _ats_custom_column_specs()} | _FEATURES | {
        "code", "name", "high", "trade", "close", "percent", "category", "vol", "volume",
        "amount", "server_time", "time"
    }
    result = {}
    for key, value in values.items():
        flat_key = next((part for part in key if part in configured), key[0]) if isinstance(key, tuple) and key else key
        result[str(flat_key)] = value.item() if hasattr(value, "item") else value
    return result


def _ats_custom_column_specs() -> List[Tuple[str, str]]:
    """Return configured ATS custom field names and their visible headers."""
    try:
        from JohnsonUtil import commonTips as cct
        columns = getattr(cct, "ats_col", []) or getattr(cct.CFG, "ats_col", []) or []
        labels = getattr(cct, "vis_column_map", {}) or {}
    except Exception:
        return []
    excluded = {"code", "name", "tier", "phase", "score", "category", "raw_category",
                "strategy_id", "version", "status", "feature_values"}
    specs, seen = [], set()
    for value in columns:
        field = str(value).strip()
        if not field or field.lower() in excluded or field.lower() in seen:
            continue
        seen.add(field.lower())
        label = labels.get(field, labels.get(field.lower(), field))
        specs.append((field, str(label)))
    return specs


def _custom_feature_values(row: Dict[str, Any]) -> Dict[str, Any]:
    values = {}
    for field, label in _ats_custom_column_specs():
        key = field if field in row else next(
            (key for key in row if isinstance(key, tuple) and field in key), None
        )
        if key is None:
            continue
        value = row.get(key)
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        if value is None or (isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null"}):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        if isinstance(value, (str, int, float, bool)):
            values[field] = value
        else:
            values[field] = str(value)
    return values


def _build_market_projection(df: Any, vwap_field: Optional[str],
                             candidate_codes: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Normalize codes once and materialize selected fields for all or requested rows."""
    columns = list(getattr(df, "columns", ()))
    aliases = {name.lower() for name in _CODE_ALIASES}
    by_lower = {str(column).strip().lower(): column for column in columns}
    code_column = next((by_lower[name] for name in _CODE_ALIASES if name in by_lower), None)
    index_values = None
    if code_column is None:
        index = getattr(df, "index", None)
        index_name = str(getattr(index, "name", "") or "").strip().lower()
        if index_name in aliases:
            index_values = list(index.tolist())
        elif index is not None and "index" not in by_lower:
            values = list(getattr(index, "tolist", lambda: [])())
            code_like = sum(1 for value in values if len("".join(ch for ch in str(value) if ch.isdigit())) in (4, 5, 6))
            if values and code_like / len(values) >= 0.8:
                index_values = values
    if code_column is None and index_values is None:
        return {"rows": [], "by_code": {}}

    custom_fields = {field for field, _label in _ats_custom_column_specs()}
    base_fields = {"code", "name", "high", "trade", "close", "percent", "dff", "category",
                   "industry", "ind", "行业", "所属行业", "行业分类", "vol", "volume", "amount",
                   "server_time", "time", vwap_field}
    base_fields.update(_FEATURES)
    selected = []
    for column in columns:
        names = set(column) if isinstance(column, tuple) else {column}
        if names.intersection(base_fields | custom_fields):
            selected.append(column)
    if code_column is not None and code_column not in selected:
        selected.append(code_column)
    raw_codes = df[code_column].tolist() if code_column is not None else index_values
    normalized_codes = [_normalize_code(code) for code in raw_codes]
    if candidate_codes is None:
        row_positions = range(len(normalized_codes))
    else:
        requested = {_normalize_code(code) for code in candidate_codes}
        row_positions = [position for position, code in enumerate(normalized_codes) if code in requested]
    frame = df.iloc[list(row_positions)].loc[:, selected].copy()
    normalized_codes = [normalized_codes[position] for position in row_positions]
    frame["code"] = normalized_codes
    rows, by_code = [], {}
    for raw in frame.to_dict("records"):
        code = str(raw.get("code", "000000"))
        row = _row_dict(raw)
        row["code"] = code
        rows.append((code, row))
        by_code[code] = row
    return {"rows": rows, "by_code": by_code}


def _candidate_row_lookup(projection: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not candidates:
        return {}
    by_code = projection.get("by_code", {}) if isinstance(projection, dict) else {}
    return {str(item.get("code", "")): by_code[str(item.get("code", ""))]
            for item in candidates if str(item.get("code", "")) in by_code}


def _history_manifest_index(data_dir: str, asof_date: str) -> List[Dict[str, Any]]:
    """Cache frozen manifests and index only cohorts whose own frozen window applies."""
    cache_key = os.path.abspath(data_dir)
    now_mono = time.monotonic()
    with _LOCK:
        cached = _HISTORY_INDEX_CACHE.get(cache_key)
        if not cached or now_mono >= cached.get("expires_at", 0):
            manifests = []
            for path in sorted(glob.glob(os.path.join(data_dir, "next_day_anomaly_watch_*.json"))):
                watch = _read_json(path, {})
                trade_date = str(watch.get("target_trade_date", ""))
                candidates = watch.get("candidates", [])
                if trade_date and isinstance(candidates, list):
                    eval_path = os.path.join(data_dir, "next_day_anomaly_eval_%s.json" % trade_date)
                    evaluation = _read_json(eval_path, {})
                    items = evaluation.get("candidates", {}) if isinstance(evaluation, dict) else {}
                    terminal_states = {"EARLY_VALID", "DELAYED", "MISSED", "UNVERIFIABLE"}
                    fully_terminal = bool(candidates)
                    for candidate in candidates:
                        key = str(candidate.get("code", "")) + ":" + str(candidate.get("strategy_id", ""))
                        item = items.get(key, {})
                        tracked = item.get("candidate", candidate)
                        pending_confirmation = any(
                            event.get("type") == "NEXT_DAY_WATCH_CONFIRM" and not event.get("delivered")
                            for event in item.get("events", []) if isinstance(event, dict))
                        if tracked.get("status") not in terminal_states or pending_confirmation:
                            fully_terminal = False
                            break
                    if fully_terminal:
                        continue
                    manifests.append({"date": trade_date, "path": path, "candidates": candidates})
            cached = {"expires_at": now_mono + _HISTORY_INDEX_TTL_SEC, "manifests": manifests}
            _HISTORY_INDEX_CACHE[cache_key] = cached

        effective = []
        for manifest in cached["manifests"]:
            if manifest["date"] >= asof_date:
                continue
            scheduled = []
            for candidate in manifest["candidates"]:
                try:
                    horizon = max(1, int(candidate.get("followup_trading_days", 3)))
                    from JohnsonUtil import commonTips as _cct
                    elapsed = int(_cct.a_trade_calendar.get_trade_days_interval(manifest["date"], asof_date))
                except Exception:
                    continue
                if elapsed >= 1:
                    scheduled.append((candidate, elapsed, horizon))
            if scheduled:
                effective.append({"date": manifest["date"], "eval_path": os.path.join(
                    data_dir, "next_day_anomaly_eval_%s.json" % manifest["date"]), "scheduled": scheduled})
        return effective


def get_followup_candidates(data_dir: str, asof_date: str) -> List[Dict[str, Any]]:
    """Return only unresolved candidates whose frozen trading-day window is active."""
    active, terminal = [], {"EARLY_VALID", "DELAYED", "MISSED", "UNVERIFIABLE"}
    for cohort in _history_manifest_index(data_dir, asof_date):
        evaluation = _read_json(cohort["eval_path"], {})
        items = evaluation.get("candidates", {}) if isinstance(evaluation, dict) else {}
        for candidate, elapsed, horizon in cohort["scheduled"]:
            key = str(candidate.get("code", "")) + ":" + str(candidate.get("strategy_id", ""))
            item = items.get(key, {})
            tracked = item.get("candidate", candidate)
            if tracked.get("status") in terminal:
                continue
            types = {event.get("type") for event in item.get("events", []) if isinstance(event, dict)}
            if types.intersection({"DAY_MISS", "UNVERIFIABLE"}) and not types.intersection({"DELAYED", "MISSED"}):
                active.append(candidate)
    return active


def _pending_confirmation_events(data_dir: str, target_date: str, current_evaluation: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = []
    seen = set()
    evaluations = [(target_date, current_evaluation)]
    for cohort in _history_manifest_index(data_dir, target_date):
        evaluations.append((cohort["date"], _read_json(cohort["eval_path"], {})))
    for _date, evaluation in evaluations:
        candidates = evaluation.get("candidates", {}) if isinstance(evaluation, dict) else {}
        for item in candidates.values():
            for event in item.get("events", []):
                event_id = str(event.get("event_id", ""))
                if (event.get("type") == "NEXT_DAY_WATCH_CONFIRM" and event_id
                        and not event.get("delivered") and event_id not in seen):
                    events.append(event)
                    seen.add(event_id)
    return events


_SECTOR_NOISE_MARKERS = (
    "股通", "融资融券", "漂亮100", "指数", "成分股", "重仓", "持股", "国企改革", "央企改革",
    "回购", "增持", "转债", "自贸区", "自贸港", "大湾区", "一带一路", "昨日涨停", "昨日触板",
    "次新股", "超级品牌", "ST板块", "风险警示",
)
_SECTOR_NOISE_NAMES = {"概念", "板块", "其它", "其他", "未知", "未分类", "默认", "综合", "主流活跃", "实时报警"}


def _sector_tags(category: Any, industry: Any = None) -> List[str]:
    tags = []
    for value in (industry, category):
        normalized = str(value or "").replace("；", ";").replace("，", ";").replace(",", ";").replace("、", ";").replace("|", ";")
        for part in normalized.split(";"):
            name = part.strip()
            if not name or name in _SECTOR_NOISE_NAMES or name.isdigit() or len(name) > 30:
                continue
            if name.lower() in {"nan", "none", "null", "--", "-", "0", "0.0"}:
                continue
            if any(marker in name for marker in _SECTOR_NOISE_MARKERS):
                continue
            if name not in tags:
                tags.append(name)
    return tags


def _row_industry(row: Dict[str, Any]) -> str:
    for key in ("industry", "ind", "行业", "所属行业", "行业分类"):
        value = row.get(key)
        if value is not None and str(value).strip() and str(value).strip().lower() not in {"nan", "none", "--"}:
            return str(value).strip()
    return ""


def _sector_info(name: str, snapshot: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return None
    if isinstance(snapshot.get(name), dict):
        return snapshot[name]
    canonical = name.removesuffix("概念").removesuffix("行业").strip()
    for key, value in snapshot.items():
        if isinstance(value, dict) and str(key).strip().removesuffix("概念").removesuffix("行业") == canonical:
            return value
    return None


def _sector_metrics(info: Dict[str, Any]) -> Tuple[float, float, float]:
    score = _number(info.get("score", info.get("momentum_score"))) or 0.0
    pct = _number(info.get("avg_pct", info.get("avg_pct_diff", info.get("pct_diff")))) or 0.0
    follow = _number(info.get("follow_ratio")) or 0.0
    return score, pct, follow


def _sector_is_starting(info: Dict[str, Any]) -> bool:
    score, pct, follow = _sector_metrics(info)
    if score < 8.0:
        return False
    # TK's board score deliberately preserves leader-led breakouts even when
    # breadth is still weak. Keep those valid starts while requiring some
    # member follow-through; the old avg-pct-only gate hid them all.
    if pct > 0.0 and follow >= 0.4:
        return True
    leader_pct = _number(info.get("leader_pct")) or _number(info.get("leader_pct_diff")) or 0.0
    return leader_pct >= 5.0 and follow >= 0.2


def _sector_contains_code(info: Dict[str, Any], code: str) -> bool:
    members = [info.get("leader", "")]
    for key in ("followers", "race_candidates"):
        values = info.get(key, [])
        if isinstance(values, list):
            members.extend(item.get("code", "") if isinstance(item, dict) else item for item in values)
    return any(_normalize_code(member) == code for member in members if member not in (None, ""))


def _select_primary_sectors(category: Any, industry: Any, snapshot: Any) -> List[str]:
    tags = _sector_tags(category, industry)
    if not tags:
        return []
    # Active, rising sectors lead; remaining useful tags are only a compact
    # context fallback, never the entire raw category string.
    ranked = []
    for order, name in enumerate(tags):
        info = _sector_info(name, snapshot)
        if info and _sector_is_starting(info):
            score, pct, follow = _sector_metrics(info)
            ranked.append((score, pct, follow, -order, name))
    ranked.sort(reverse=True)
    selected = [item[-1] for item in ranked[:3]]
    selected.extend(name for name in tags if name not in selected)
    return selected[:3]


def _sector_evidence(category: Any, snapshot: Any, *, code: str = "", industry: Any = None,
                     stock_started: bool = False) -> Dict[str, Any]:
    result = {"snapshot_at": None, "matches": [], "stock_started": bool(stock_started), "reason": "个股未处于上行/启动阶段"}
    if not stock_started or not isinstance(snapshot, dict):
        return result
    result["reason"] = "无同时满足板块启动和个股归属的共振板块"
    ranked = []
    tags = _sector_tags(category, industry)
    tag_keys = {str(name).removesuffix("概念").removesuffix("行业").strip() for name in tags}
    for order, (name, info) in enumerate(snapshot.items()):
        if not isinstance(info, dict) or not _sector_is_starting(info):
            continue
        canonical = str(name).strip().removesuffix("概念").removesuffix("行业").strip()
        # ATS 分类名称与赛马板块名称并非总是同一套命名：允许规范化标签匹配，
        # 或以板块真实龙头/跟随股/竞速股成员关系作为个股归属依据。
        if canonical not in tag_keys and not _sector_contains_code(info, code):
            continue
        score, pct, follow = _sector_metrics(info)
        ranked.append((score, pct, follow, -order, str(name), info))
    if not ranked:
        return result
    ranked.sort(reverse=True, key=lambda item: item[:4])
    _, _, _, _, name, info = ranked[0]
    clean = {key: (str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value)
             for key, value in info.items() if key in {"score", "momentum_score", "leader", "leader_name", "leader_pct",
                 "leader_pct_diff", "followers", "ts", "score_diff", "avg_pct", "avg_pct_diff", "follow_ratio"}}
    result["snapshot_at"] = clean.get("ts")
    result["matches"] = [{"name": name, **clean}]
    result["sector_started"] = True
    result["reason"] = ""
    return result


def run_cycle(df: Any, *, config_path: str, data_dir: str, asof_date: str,
              target_date: str, observed_at: Optional[str] = None,
              vwap_field: Optional[str] = None, sector_snapshot: Any = None,
              source_version: Any = None, observe: bool = True,
              force_freeze: bool = False) -> Dict[str, Any]:
    """Create the frozen next-session list and append candidate outcome facts."""
    if df is None or getattr(df, "empty", True):
        return {"status": "empty"}
    t_start = time.perf_counter()
    from ats.strategy.next_day_watch_config_manager import NextDayWatchConfigManager
    _, config, config_error = NextDayWatchConfigManager.load_config(config_path)
    valid, error = _valid_config(config)
    if not valid:
        return {"status": "invalid_config", "reason": config_error or error}
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
        # Manual补算 may repair a previously frozen empty list after the ATS
        # source data becomes available. Never mutate a non-empty frozen pool.
        if force_freeze and watch is not None and not watch.get("candidates"):
            watch = None
        if watch is None and not force_freeze and (now.date().isoformat() != target_date or (now.hour, now.minute) > (9, 15)):
            return {"status": "not_frozen", "candidate_count": 0, "events": []}

        # Freeze needs every market row for strategy evaluation. Once frozen, only
        # materialize the current cohort and unresolved historical followups.
        history_cohorts = []
        if observe and now.date().isoformat() == target_date:
            history_cohorts = _history_manifest_index(data_dir, target_date)
        if watch is None:
            projection_codes = None
        else:
            projection_codes = {str(candidate.get("code", "")) for candidate in watch.get("candidates", [])}
            for cohort in history_cohorts:
                projection_codes.update(str(candidate.get("code", ""))
                    for candidate, _elapsed, _horizon in cohort["scheduled"])
        market_projection = _build_market_projection(df, vwap_field, projection_codes)
        t_proj = time.perf_counter()

        if watch is None:
            records = []
            invalid_by_strategy = {}
            prefilter_rejected = {}
            tier_rejected = {}
            valid_codes = set()
            for code, row in market_projection.get("rows", []):
                if len(code) != 6 or code == "000000":
                    continue
                valid_codes.add(code)
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
                    req_fields = strategy.get("required_fields")
                    if req_fields is not None and isinstance(req_fields, list):
                        required = tuple(req_fields)
                    else:
                        required = ("ch_dir", "ch_slope_deg", "ch_pos", "lastp1d", "ch_lower", "td_sell",
                                    "lasth1d", "lasth2d", "lasth3d", "lastl1d", "lastl2d", "lastl3d", "lastl4d", "lastl5d",
                                    "lastv1d", "lastv2d", "lastv3d") if strategy.get("template") == "channel_stepup" else ()
                    missing_required = any(_number(row.get(field)) is None for field in required)
                    strategy_id = str(strategy["strategy_id"])
                    if match is None or missing_required:
                        invalid_by_strategy[strategy_id] = invalid_by_strategy.get(strategy_id, 0) + 1
                        continue
                    if match is False:
                        prefilter_rejected[strategy_id] = prefilter_rejected.get(strategy_id, 0) + 1
                        continue
                    # No unknown/missing feature may silently become a passing result.
                    if match is True and tier:
                        raw_category = str(row.get("category", ""))
                        industry = _row_industry(row)
                        primary_sectors = _select_primary_sectors(raw_category, industry, sector_snapshot)
                        trend_score = _trend_score(row)
                        records.append({"code": code, "name": str(row.get("name", code)),
                            "category": ";".join(primary_sectors) or industry or "未分类", "raw_category": raw_category,
                            "industry": industry,
                            "strategy_id": str(strategy["strategy_id"]), "version": str(strategy["version"]),
                            "config_hash": digest, "tier": tier, "score": trend_score,
                            "trend_rating": _trend_rating(trend_score), "score_model_version": 1,
                            "reason_codes": ["channel_support", "higher_highs_lows" if tier != "A" else "support_stable"],
                            "sector_evidence": _sector_evidence(raw_category, sector_snapshot, code=code, industry=industry,
                                stock_started=tier in {"B", "C"}),
                            "feature_values": ({k: row.get(k) for k in sorted(_FEATURES) if _number(row.get(k)) is not None}
                                               | _custom_feature_values(row)),
                            "first_selected_date": target_date, "status": "WATCHING",
                            "phase": {"A": "STABILIZING", "B": "RISING", "C": "PRE_ACCELERATION"}[tier],
                            "followup_trading_days": int(strategy.get("followup", {}).get("trading_days", 3)),
                            "followup_proof_any": list(strategy.get("followup", {}).get("proof_any", ["daily_high_break", "verified_vwap_rise"]))})
                    elif match is True:
                        tier_rejected[strategy_id] = tier_rejected.get(strategy_id, 0) + 1
            if not valid_codes:
                return {"status": "no_valid_codes", "reason": "ATS宽表中未识别到有效证券代码列/索引",
                        "universe_count": len(df), "valid_code_count": 0, "target_trade_date": target_date}
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
                     "universe_count": len(df), "valid_code_count": len(valid_codes),
                     "invalid_count": invalid_by_strategy, "prefilter_rejected": prefilter_rejected,
                     "tier_rejected": tier_rejected, "candidates": records}
            _atomic_json(watch_path, watch)
        if force_freeze:
            # A manual补算 can complete sector evidence on an existing frozen
            # manifest without changing the selected cohort or its ranking.
            enriched = False
            custom_row_lookup = _candidate_row_lookup(market_projection, watch.get("candidates", []))
            for candidate in watch.get("candidates", []):
                raw_category = candidate.get("raw_category") or candidate.get("category", "")
                primary_sectors = _select_primary_sectors(raw_category, candidate.get("industry", ""), sector_snapshot)
                compact_category = ";".join(primary_sectors) or candidate.get("industry") or "未分类"
                if candidate.get("category") != compact_category:
                    candidate["raw_category"] = raw_category
                    candidate["category"] = compact_category
                    enriched = True
                evidence = candidate.get("sector_evidence") or {}
                if isinstance(sector_snapshot, dict) and sector_snapshot:
                    evidence = _sector_evidence(raw_category, sector_snapshot, code=str(candidate.get("code", "")),
                        industry=candidate.get("industry", ""),
                        stock_started=candidate.get("tier") in {"B", "C"})
                    if evidence != candidate.get("sector_evidence"):
                        candidate["sector_evidence"] = evidence
                        enriched = True
                source_row = custom_row_lookup.get(str(candidate.get("code", "")))
                if source_row:
                    feature_values = candidate.setdefault("feature_values", {})
                    for field in _FEATURES:
                        value = _number(source_row.get(field))
                        if value is not None and feature_values.get(field) != value:
                            feature_values[field] = value
                            enriched = True
                    for field, value in _custom_feature_values(source_row).items():
                        if feature_values.get(field) != value:
                            feature_values[field] = value
                            enriched = True
                feature_values = candidate.get("feature_values", {})
                score = _trend_score(feature_values)
                if candidate.get("score_model_version") != 1 or candidate.get("score") != score:
                    candidate["score"] = score
                    candidate["trend_rating"] = _trend_rating(score)
                    candidate["score_model_version"] = 1
                    enriched = True
            if enriched:
                _atomic_json(watch_path, watch)
        if not observe:
            candidates = watch.get("candidates", [])
            sector_evidence_count = sum(
                bool((item.get("sector_evidence") or {}).get("matches")) for item in candidates
            )
            return {"status": "manifest_ready", "candidate_count": len(candidates),
                    "valid_code_count": watch.get("valid_code_count", 0),
                    "invalid_count": watch.get("invalid_count", {}),
                    "prefilter_rejected": watch.get("prefilter_rejected", {}),
                    "tier_rejected": watch.get("tier_rejected", {}),
                    "sector_evidence_count": sector_evidence_count,
                    "target_trade_date": target_date, "watch_path": watch_path, "eval_path": eval_path, "events": []}
        evaluation = _read_json(eval_path, {"schema_version": 1, "target_trade_date": target_date, "config_hash": watch.get("config_hash"), "candidates": {}})
        if now.date().isoformat() != target_date:
            return {"status": "manifest_ready", "candidate_count": len(watch.get("candidates", [])), "watch_path": watch_path, "eval_path": eval_path, "events": []}

        # 2. 证据保真跳写标记 (Evidence-Fidelity Skip-Write Dirty Flag)
        eval_dirty = False
        row_lookup = _candidate_row_lookup(market_projection, watch.get("candidates", []))
        for candidate in watch.get("candidates", []):
            code = candidate["code"]
            row = row_lookup.get(code)
            if not row:
                item = evaluation["candidates"].setdefault(code + ":" + candidate["strategy_id"], {"candidate": candidate, "checkpoints": [], "events": []})
                if now.hour >= 15 and not any(event.get("type") == "UNVERIFIABLE" for event in item["events"]):
                    item.setdefault("candidate", candidate)["status"] = "UNVERIFIABLE"
                    item["events"].append({"type": "UNVERIFIABLE", "date": target_date, "observed_at": observed_at,
                                           "reason": "candidate_row_missing_at_target_day_close"})
                    eval_dirty = True
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
            cur_vol = _number(row.get("volume", row.get("vol")))
            cur_amt = _number(row.get("amount"))
            cur_time = str(row.get("server_time") or row.get("time") or "")
            proof_rules = candidate.get("followup_proof_any") or ["daily_high_break", "verified_vwap_rise"]
            proof_high = sustained_high if "daily_high_break" in proof_rules else False
            proof_vw = proof_vwap if "verified_vwap_rise" in proof_rules else False
            proof = proof_high or proof_vw

            item["checkpoints"].append({"observed_at": observed_at, "phase": "market" if now.hour < 15 else "close",
                "high": daily_high, "close": close, "vwap": real_vwap, "vwap_source": vwap_field if real_vwap is not None else None,
                "volume": cur_vol, "amount": cur_amt, "server_time": cur_time,
                "sustained_high": sustained_high, "verified_vwap_rise": proof_vwap, "sector": str(row.get("category", "")),
                "sector_evidence": _sector_evidence(row.get("category"), sector_snapshot,
                    code=code, industry=candidate.get("industry", ""),
                    stock_started=candidate.get("tier") in {"B", "C"})})
            eval_dirty = True

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
                eval_dirty = True

            in_continuous_session = (now.hour, now.minute) >= (9, 30) and (now.hour, now.minute) <= (15, 0)
            prior_age = None
            has_quote_progress = True
            if prior_checkpoint:
                try:
                    prior_age = (now - datetime.fromisoformat(prior_checkpoint["observed_at"])).total_seconds()
                except (KeyError, TypeError, ValueError):
                    prior_age = None
                prior_vol = _number(prior_checkpoint.get("volume"))
                prior_amt = _number(prior_checkpoint.get("amount"))
                prior_time = str(prior_checkpoint.get("server_time") or "")
                # 必须有真实的量额递增或时间戳推进，同一报价重复重放不得视作新帧
                if cur_vol is not None and prior_vol is not None:
                    has_quote_progress = (cur_vol > prior_vol)
                elif cur_amt is not None and prior_amt is not None:
                    has_quote_progress = (cur_amt > prior_amt)
                elif cur_time and prior_time:
                    has_quote_progress = (cur_time > prior_time)
                else:
                    # 无量额和时间时，若价格完全未变，不允许触发
                    p_curr = (daily_high, close, real_vwap)
                    p_prior = (_number(prior_checkpoint.get("high")), _number(prior_checkpoint.get("close")), _number(prior_checkpoint.get("vwap")))
                    if p_curr == p_prior:
                        has_quote_progress = False

            prior_matched = bool(prior_checkpoint and (
                (proof_high and prior_checkpoint.get("sustained_high")) or
                (proof_vw and prior_checkpoint.get("verified_vwap_rise"))
            ))

            if (in_continuous_session and proof and has_quote_progress and prior_age is not None and 0 < prior_age <= 8
                    and prior_matched):
                if not any(e.get("type") == "NEXT_DAY_WATCH_CONFIRM" for e in item["events"]):
                    event = {"type": "NEXT_DAY_WATCH_CONFIRM", "event_id": "%s:%s:%s:first_confirm" %
                             (target_date, code, candidate["strategy_id"]), "target_trade_date": target_date,
                             "code": code, "name": candidate.get("name", code), "strategy_id": candidate["strategy_id"],
                             "version": candidate["version"], "config_hash": candidate["config_hash"],
                             "observed_at": observed_at, "action": "WATCH", "reason": "两帧确认：持续新高或真实 VWAP 上移",
                             "price": close or 0.0, "pct": _number(row.get("percent")) or 0.0,
                             "deviation": _number(row.get("dff")) or 0.0, "sector_name": str(row.get("category", "")),
                             "sector_snapshot_ts": _sector_evidence(row.get("category"), sector_snapshot,
                                 code=code, industry=candidate.get("industry", ""),
                                 stock_started=candidate.get("tier") in {"B", "C"}).get("snapshot_at"),
                             "evidence": {"sustained_high": sustained_high, "verified_vwap_rise": proof_vwap,
                                          "vwap": real_vwap, "vwap_source": vwap_field if real_vwap is not None else None,
                                          "confirm_frames": 2, "first_observed_at": prior_checkpoint["observed_at"]}}
                    item["events"].append(event)
                    eval_dirty = True
            has_confirmed = any(e.get("type") == "NEXT_DAY_WATCH_CONFIRM" for e in item["events"])
            has_vwap_observation = any(point.get("vwap") is not None for point in item["checkpoints"])
            prev_status = tracked_candidate.get("status")
            if has_confirmed:
                tracked_candidate["status"] = "EARLY_VALID"
            elif now.hour >= 15 and not proof and (daily_high is None or close is None or not has_vwap_observation):
                if not any(e.get("type") == "UNVERIFIABLE" for e in item["events"]):
                    item["events"].append({"type": "UNVERIFIABLE", "date": target_date, "observed_at": observed_at,
                                           "reason": "missing_price_or_verified_vwap_observation"})
                    tracked_candidate["status"] = "UNVERIFIABLE"
                    eval_dirty = True
            elif now.hour >= 15 and not proof and not any(e["type"] == "DAY_MISS" for e in item["events"]):
                item["events"].append({"type": "DAY_MISS", "date": target_date, "observed_at": observed_at,
                                       "reason": "no_sustained_high_and_verified_vwap_did_not_rise"})
                tracked_candidate["status"] = "DAY_MISS"
                eval_dirty = True
            elif proof and any(e["type"] == "DAY_MISS" for e in item["events"]):
                if not any(e["type"] == "DELAYED" for e in item["events"]):
                    item["events"].append({"type": "DELAYED", "date": now.date().isoformat(), "observed_at": observed_at})
                    eval_dirty = True
                tracked_candidate["status"] = "DELAYED"
                tracked_candidate["phase"] = "RISING"
            elif proof:
                tracked_candidate["status"] = "EARLY_VALID"

            if tracked_candidate.get("status") != prev_status:
                eval_dirty = True

        if eval_dirty:
            evaluation["updated_at"] = observed_at
            _atomic_json(eval_path, evaluation)

        # 3. 历史顺延与到期终结结算 (基于各自独立 followup 期限与有效索引)
        for cohort in history_cohorts:
            prior_date = cohort["date"]
            prior_eval_path = cohort["eval_path"]
            prior_eval = _read_json(prior_eval_path, {})
            changed = False
            items = prior_eval.get("candidates", {}) if isinstance(prior_eval, dict) else {}
            for candidate, elapsed, horizon in cohort["scheduled"]:
                key = str(candidate.get("code", "")) + ":" + str(candidate.get("strategy_id", ""))
                item = items.get(key)
                if not item:
                    continue
                prior_types = {event.get("type") for event in item.get("events", []) if isinstance(event, dict)}
                tracked = item.get("candidate", candidate)
                if tracked.get("status") in {"EARLY_VALID", "DELAYED", "MISSED", "UNVERIFIABLE"}:
                    continue
                code = str(candidate.get("code", ""))
                row = market_projection.get("by_code", {}).get(code)
                due = elapsed > horizon or (elapsed == horizon and now.hour >= 15)
                if not row:
                    if due:
                        if not prior_types.intersection({"UNVERIFIABLE", "DELAYED", "MISSED"}):
                            item.setdefault("events", []).append({"type": "UNVERIFIABLE", "date": target_date,
                                "observed_at": observed_at, "reason": "followup_window_expired_without_quote_evidence"})
                            tracked["status"] = "UNVERIFIABLE"
                            changed = True
                    continue
                high = _number(row.get("high"))
                close = _number(row.get("trade", row.get("close")))
                prior_day_checkpoints = [point for point in item.get("checkpoints", [])
                    if str(point.get("observed_at", ""))[:10] < target_date]
                prior_high = (_number(prior_day_checkpoints[-1].get("high")) if prior_day_checkpoints
                              else _number(candidate.get("feature_values", {}).get("lasth1d")))
                real_vwap = _number(row.get(vwap_field)) if vwap_field and vwap_field in row else None
                proof_rules = candidate.get("followup_proof_any") or ["daily_high_break", "verified_vwap_rise"]
                proof_high = ("daily_high_break" in proof_rules and high is not None and close is not None
                              and prior_high is not None and high > prior_high and close > prior_high)
                prior_checkpoint = item.get("checkpoints", [])[-1] if item.get("checkpoints") else None
                proof_vwap = bool("verified_vwap_rise" in proof_rules and real_vwap is not None and real_vwap > 0
                                  and prior_checkpoint
                                  and prior_checkpoint.get("vwap_source") == vwap_field
                                  and _number(prior_checkpoint.get("vwap")) is not None
                                  and real_vwap > float(prior_checkpoint["vwap"]))
                checkpoint = {"observed_at": observed_at, "phase": "market" if now.hour < 15 else "close",
                    "high": high, "close": close, "vwap": real_vwap,
                    "vwap_source": vwap_field if real_vwap is not None else None,
                    "volume": _number(row.get("volume", row.get("vol"))), "amount": _number(row.get("amount")),
                    "server_time": str(row.get("server_time") or row.get("time") or ""),
                    "sustained_high": proof_high, "verified_vwap_rise": proof_vwap,
                    "sector": str(row.get("category", ""))}
                checkpoints = item.setdefault("checkpoints", [])
                if elapsed <= horizon and (not checkpoints or checkpoints[-1].get("observed_at") != observed_at):
                    checkpoints.append(checkpoint)
                    changed = True
                if elapsed <= horizon and (proof_high or proof_vwap):
                    if not any(e.get("type") == "DELAYED" for e in item.get("events", [])):
                        item.setdefault("events", []).append({
                            "type": "DELAYED",
                            "date": target_date,
                            "observed_at": observed_at,
                            "reason": "later_sustained_high_after_target_day_miss" if proof_high
                                      else "verified_vwap_rise_after_target_day_miss"
                        })
                        changed = True
                    if tracked.get("status") != "DELAYED":
                        tracked["status"] = "DELAYED"
                        changed = True
                    continue
                # 在窗口最后一日收盘结算；若程序错过该日，之后首轮也补结算。
                if due:
                    if high is None or close is None:
                        if not prior_types.intersection({"UNVERIFIABLE", "DELAYED", "MISSED"}):
                            item.setdefault("events", []).append({"type": "UNVERIFIABLE", "date": target_date,
                                "observed_at": observed_at, "reason": "followup_window_expired_without_quote_evidence"})
                            tracked["status"] = "UNVERIFIABLE"
                            changed = True
                    elif not prior_types.intersection({"DELAYED", "MISSED"}):
                        item.setdefault("events", []).append({"type": "MISSED", "date": target_date,
                            "observed_at": observed_at, "reason": "followup_window_expired_after_day_miss"})
                        tracked["status"] = "MISSED"
                        changed = True
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

        # 4. 统计汇总与证据保真跳写
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

        cur_stats_path = os.path.join(data_dir, "next_day_anomaly_stats_%s.json" % target_date)
        stats_rows = list(stats.values())
        old_current_stats = _read_json(cur_stats_path, {})
        if not os.path.exists(cur_stats_path) or old_current_stats.get("strategies") != stats_rows:
            _atomic_json(cur_stats_path,
                         {"target_trade_date": target_date, "updated_at": observed_at, "strategies": stats_rows})

        # 5. 持久待发 (Outbox): 持续投递当前与历史跨日未确认送达的确认事件
        events_to_send = _pending_confirmation_events(data_dir, target_date, evaluation)
        telemetry = {
            "elapsed_ms": round((time.perf_counter() - t_start) * 1000, 2),
            "projection_ms": round((t_proj - t_start) * 1000, 2),
            "eval_dirty": eval_dirty,
            "pending_event_count": len(events_to_send),
        }
        return {"status": "ok", "candidate_count": len(watch.get("candidates", [])),
                "watch_path": watch_path, "eval_path": eval_path,
                "events": events_to_send, "telemetry": telemetry}


def mark_events_delivered(data_dir: str, target_date: str, event_ids: Iterable[str]) -> None:
    """Persist successful pipe/signal handoff across current and historical cohorts."""
    ids = set(str(event_id) for event_id in event_ids if event_id)
    if not ids:
        return
    # 分解 target_date 或直接从 event_id 提取日期（格式通常为 YYYY-MM-DD:code:strategy:...）
    date_to_ids: Dict[str, set] = {}
    for eid in ids:
        parts = eid.split(":")
        if len(parts) >= 1 and len(parts[0]) == 10 and parts[0].count("-") == 2:
            date_to_ids.setdefault(parts[0], set()).add(eid)
        else:
            date_to_ids.setdefault(target_date, set()).add(eid)

    with _LOCK:
        for d, batch_ids in date_to_ids.items():
            path = os.path.join(data_dir, f"next_day_anomaly_eval_{d}.json")
            if not os.path.exists(path):
                continue
            evaluation = _read_json(path, {})
            changed = False
            for item in evaluation.get("candidates", {}).values():
                for event in item.get("events", []):
                    if event.get("event_id") in batch_ids and not event.get("delivered"):
                        event["delivered"] = True
                        changed = True
            if changed:
                _atomic_json(path, evaluation)
