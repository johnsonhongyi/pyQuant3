"""Bounded, auditable parameter tuning for the CN paper follower.

Only a small allow-list of keys may move, each with a hard step and range.
Changes are written to a mutable overlay (``params.json``) in the data
directory, never to the read-only release.  Every change carries its evidence
and can be rolled back automatically after a drawdown.
"""
import json
from pathlib import Path
try:
    from safe_copy import safe_deepcopy
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from safe_copy import safe_deepcopy

SPEC = {
    "execution.regime_policy.cautious.min_score": {"min": 62, "max": 78, "step": 2, "kind": "score"},
    "execution.signal.vwap_band.high": {"min": 1.025, "max": 1.040, "step": 0.005, "kind": "loosen"},
    "buy.max_day_chg": {"min": 7.0, "max": 9.0, "step": 0.5, "kind": "loosen"},
    "sell.stop_loss": {"min": -0.08, "max": -0.04, "step": 0.005, "kind": "tighten"},
    "sell.take_profit": {"min": 0.06, "max": 0.18, "step": 0.01, "kind": "both"},
    "execution.regime_policy.cautious.exposure": {"min": 0.3, "max": 0.6, "step": 0.1, "kind": "both"},
}
DEFAULT = {"mode": "auto", "min_samples": 8, "cooldown_days": 3, "max_daily_changes": 1,
           "rollback_loss_pct": 0.02, "rollback_trades": 5, "pause_days": 5}


def _num(value, default=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result else default


def settings(cfg):
    execution = (cfg or {}).get("execution") or {}
    return {**DEFAULT, **(execution.get("optimizer") or {})}


def _paths(account_db):
    root = Path(account_db).parent
    return root / "params.json", root / "optimizer_history.jsonl"


def load_params(account_db):
    path, _ = _paths(account_db)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_params(account_db, data):
    path, _ = _paths(account_db)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _append_history(account_db, entry):
    _, path = _paths(account_db)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _get(cfg, dotted):
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set(cfg, dotted, value):
    parts = dotted.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def apply_overrides(cfg, params):
    """Merge a validated overlay into a copy of the frozen config."""
    merged = safe_deepcopy(cfg)
    for key, value in (params.get("overrides") or {}).items():
        rule = SPEC.get(key)
        if not rule or isinstance(value, bool) or _num(value) is None:
            continue
        value = float(value)
        if not rule["min"] <= value <= rule["max"]:
            continue
        if key in ("execution.signal.entry_threshold", "execution.regime_policy.cautious.min_score"):
            value = int(round(value))
        _set(merged, key, value)
    if params.get("version"):
        merged["runtime_version"] = params["version"]
        merged["base_version"] = params.get("base_version") or cfg.get("version")
    return merged


def _clamp(key, value):
    rule = SPEC[key]
    value = max(rule["min"], min(rule["max"], value))
    if key in ("execution.signal.entry_threshold", "execution.regime_policy.cautious.min_score"):
        return int(round(value))
    return round(value, 4)


def _history(account_db):
    _, path = _paths(account_db)
    if not path.exists():
        return []
    entries = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    except (OSError, ValueError):
        return []
    return entries


def _days_between(older, newer):
    try:
        from datetime import date
        return (date.fromisoformat(newer[:10]) - date.fromisoformat(older[:10])).days
    except (TypeError, ValueError):
        return 10 ** 6


def _pick(summary, trades, cfg, params):
    """Return (key, new_value, reason, evidence) or None."""
    overrides = params.get("overrides") or {}
    current = {key: _get(cfg, key) for key in SPEC}
    for key, value in overrides.items():
        if key in current:
            current[key] = value
    min_samples = int(settings(cfg)["min_samples"])

    def evidence(reason, n, win=None, avg=None):
        return {"reason": reason, "samples": n, "win_rate": win, "avg_forward": avg}

    trade_n = int((trades or {}).get("n") or 0)
    win_rate = _num((trades or {}).get("win_rate"))
    avg_pnl = _num((trades or {}).get("avg_pnl"))
    if trade_n >= min_samples and win_rate is not None and win_rate < 0.40 and (avg_pnl or 0) < 0:
        old = _num(current["sell.stop_loss"], -0.06)
        new = _clamp("sell.stop_loss", old + SPEC["sell.stop_loss"]["step"])
        if new > old:
            return ("sell.stop_loss", new, "止损样本胜率偏低，收紧止损",
                    evidence("trades_losing", trade_n, win_rate, avg_pnl))
    blockers = {item["reason"]: item for item in (summary or {}).get("blockers") or []}
    band = blockers.get("P8 VWAP gate")
    if band and band.get("n", 0) >= min_samples and (_num(band.get("win")) or 0) >= 0.60 and (_num(band.get("avg")) or 0) >= 0.02:
        old = _num(current["execution.signal.vwap_band.high"], 1.030)
        new = _clamp("execution.signal.vwap_band.high", old + SPEC["execution.signal.vwap_band.high"]["step"])
        if new > old:
            return ("execution.signal.vwap_band.high", new, "被VWAP上沿拦截的样本后续偏强，小幅放宽上沿",
                    evidence("P8 VWAP gate", band["n"], band.get("win"), band.get("avg")))
    change_gate = blockers.get("P4 change gate")
    if change_gate and change_gate.get("n", 0) >= min_samples and (_num(change_gate.get("win")) or 0) >= 0.60 and (_num(change_gate.get("avg")) or 0) >= 0.02:
        old = _num(current["buy.max_day_chg"], 7.0)
        new = _clamp("buy.max_day_chg", old + SPEC["buy.max_day_chg"]["step"])
        if new > old:
            return ("buy.max_day_chg", new, "被涨幅上限拦截的样本后续偏强，小幅放宽上限",
                    evidence("P4 change gate", change_gate["n"], change_gate.get("win"), change_gate.get("avg")))
    buckets = {item["bucket"]: item for item in (summary or {}).get("buckets") or []}
    top = buckets.get("80+")
    low = buckets.get("60-69")
    if top and top.get("n", 0) >= min_samples and (_num(top.get("win")) or 0) >= 0.60 and (_num(top.get("avg")) or 0) > 0:
        if low and low.get("n", 0) >= min_samples and (_num(low.get("avg")) or 0) < 0:
            old = _num(current["execution.regime_policy.cautious.min_score"], 70)
            new = _clamp("execution.regime_policy.cautious.min_score", old + SPEC["execution.regime_policy.cautious.min_score"]["step"])
            if new > old:
                return ("execution.regime_policy.cautious.min_score", new, "高分桶显著优于低分桶，提高谨慎状态入场阈值",
                        evidence("score_bucket", top["n"], top.get("win"), top.get("avg")))
    if trade_n >= min_samples and (_num((trades or {}).get("profit_factor")) or 0) >= 1.2:
        exits = (trades or {}).get("exits") or {}
        if exits.get("take_profit", 0) >= max(3, trade_n * 0.4):
            old = _num(current["sell.take_profit"], 0.10)
            new = _clamp("sell.take_profit", old + SPEC["sell.take_profit"]["step"])
            if new > old:
                return ("sell.take_profit", new, "止盈退出占主导且盈亏比健康，小幅抬高目标",
                        evidence("take_profit_exits", trade_n, win_rate, avg_pnl))
    regimes = {item["regime"]: item for item in (summary or {}).get("regimes") or []}
    cautious = regimes.get("cautious")
    if cautious and cautious.get("n", 0) >= 10 and (_num(cautious.get("win")) or 0) >= 0.55 and (_num(cautious.get("avg")) or 0) > 0:
        old = _num(current["execution.regime_policy.cautious.exposure"], 0.5)
        new = _clamp("execution.regime_policy.cautious.exposure", old + SPEC["execution.regime_policy.cautious.exposure"]["step"])
        if new > old:
            return ("execution.regime_policy.cautious.exposure", new, "谨慎状态样本转正，提高暴露",
                    evidence("cautious_regime", cautious["n"], cautious.get("win"), cautious.get("avg")))
    return None


def _recent_closed(db, since, initial_cash):
    rows = db.execute("SELECT pnl,sell_date FROM trades WHERE sell_date>=? ORDER BY sell_date", (since[:10],)).fetchall()
    pnls = [row[0] for row in rows if row[0] is not None]
    return len(pnls), sum(pnls), (sum(pnls) / initial_cash if initial_cash else 0)


def run(db, state, cfg, now, account_db, summary, force=False):
    """Evaluate and optionally apply one bounded change for the day."""
    conf = settings(cfg)
    mode = conf.get("mode", "auto")
    params = load_params(account_db)
    base_version = cfg.get("base_version") or cfg.get("version")
    status = {"as_of": now.isoformat(), "mode": mode, "status": "off" if mode == "off" else "collecting",
              "version": params.get("version") or base_version, "last_run_date": now.date().isoformat(),
              "proposal": None, "reason": "", "history": _history(account_db)[-8:]}
    if mode == "off":
        state["optimizer"] = status
        return status
    paused = params.get("paused_until")
    if paused and paused >= now.date().isoformat():
        status.update(status="paused", reason="回滚后冷却至 %s" % paused)
        state["optimizer"] = status
        return status
    # Automatic rollback after a drawdown following an applied change.
    applied_at = params.get("applied_at")
    if applied_at and params.get("overrides"):
        count, total, ratio = _recent_closed(db, applied_at, state.get("initial_cash") or 0)
        if count >= int(conf["rollback_trades"]) and ratio <= -abs(float(conf["rollback_loss_pct"])):
            _append_history(account_db, {"at": now.isoformat(), "kind": "rollback", "from": params.get("version"),
                                         "trades": count, "pnl": total, "reason": "回滚阈值触发"})
            from datetime import date, timedelta
            params = {"version": base_version, "base_version": base_version, "overrides": {},
                      "paused_until": (now.date() + timedelta(days=int(conf["pause_days"]))).isoformat(),
                      "updated_at": now.isoformat()}
            _write_params(account_db, params)
            status.update(status="rolled_back", version=base_version, reason="连续亏损触发回滚",
                          history=_history(account_db)[-8:])
            state["optimizer"] = status
            return status
    if not force and (state.get("optimizer") or {}).get("last_run_date") == now.date().isoformat():
        status.update(status=(state.get("optimizer") or {}).get("status", "hold"),
                      reason="今日已运行", version=params.get("version") or base_version)
        state["optimizer"] = status
        return status
    history = _history(account_db)
    same_day = [e for e in history if str(e.get("at", ""))[:10] == now.date().isoformat() and e.get("kind") == "apply"]
    if not force and len(same_day) >= int(conf["max_daily_changes"]):
        status.update(status="hold", reason="今日变更次数已用完")
        state["optimizer"] = status
        return status
    samples = int((summary or {}).get("settled") or 0)
    if samples < int(conf["min_samples"]):
        status.update(status="collecting", reason="已结算样本 %d/%d" % (samples, int(conf["min_samples"])),
                      samples=samples)
        state["optimizer"] = status
        return status
    picked = _pick(summary, (summary or {}).get("trades"), cfg, params)
    if not picked:
        status.update(status="hold", reason="无参数变更证据", samples=samples)
        state["optimizer"] = status
        return status
    key, new_value, reason, evidence = picked
    last = next((e for e in reversed(history) if e.get("key") == key), None)
    if last and _days_between(last.get("at", ""), now.isoformat()) < int(conf["cooldown_days"]):
        status.update(status="hold", reason="%s 仍在冷却期" % key, samples=samples)
        state["optimizer"] = status
        return status
    old_value = _get(cfg, key)
    proposal = {"key": key, "old": old_value, "new": new_value, "reason": reason,
                "evidence": evidence, "confidence": min(0.9, 0.4 + samples / 40)}
    status["proposal"] = proposal
    status["samples"] = samples
    if mode != "auto":
        status.update(status="proposed", reason="propose 模式，等待人工确认")
        state["optimizer"] = status
        return status
    overrides = dict(params.get("overrides") or {})
    overrides[key] = new_value
    number = len([e for e in history if e.get("kind") == "apply"]) + 1
    version = "%s+opt.%d" % (base_version, number)
    payload = {"version": version, "base_version": base_version, "overrides": overrides,
               "applied_at": now.isoformat(), "updated_at": now.isoformat(),
               "last_key": key, "reason": reason}
    _write_params(account_db, payload)
    _append_history(account_db, {"at": now.isoformat(), "kind": "apply", "version": version,
                                 "key": key, "old": old_value, "new": new_value,
                                 "reason": reason, "evidence": evidence})
    status.update(status="applied", version=version, reason=reason,
                  history=_history(account_db)[-8:])
    state["optimizer"] = status
    return status
