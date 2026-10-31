"""Regime policy, funnel accounting and the loop summary exposed to the UI."""

REGIME_ORDER = ("attack", "balanced", "cautious", "defense")
REGIME_LABELS = {"attack": "进攻", "balanced": "均衡", "cautious": "谨慎", "defense": "防守", "legacy": "旧版门禁"}
DEFAULT_POLICY = {
    "attack": {"statuses": ["高位延续"], "exposure": 1.0, "min_score": 60, "max_positions": 5},
    "balanced": {"statuses": ["高位震荡"], "exposure": 0.8, "min_score": 64, "max_positions": 4},
    "cautious": {"statuses": ["分歧"], "exposure": 0.5, "min_score": 70, "max_positions": 2, "risk_ceiling": 70},
    "defense": {"statuses": ["强分歧", "高位退潮", "高位样本不足"], "exposure": 0.0, "min_score": 100,
                "max_positions": 0},
}


def _num(value, default=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result else default


def policy(cfg):
    execution = (cfg or {}).get("execution") or {}
    configured = execution.get("regime_policy")
    if not configured:
        return None
    merged = {}
    for code in REGIME_ORDER:
        merged[code] = {**DEFAULT_POLICY[code], **(configured.get(code) or {})}
    return merged


def classify(sentiment, cfg):
    """Map market evidence to an exposure regime.

    Legacy configurations (no ``execution`` section) keep the old binary gate.
    """
    policies = policy(cfg)
    if policies is None:
        return {"code": "legacy", "label": REGIME_LABELS["legacy"], "exposure": 1.0,
                "min_score": 0, "max_positions": _num((cfg or {}).get("buy", {}).get("max_positions"), 5),
                "status": None, "risk_score": None, "reason": "legacy_config"}
    sentiment = sentiment or {}
    status = sentiment.get("backend_status") or sentiment.get("status")
    risk = _num(sentiment.get("risk_score"))
    score = _num(sentiment.get("score"))
    code = None
    if status:
        for candidate in REGIME_ORDER:
            if status in policies[candidate]["statuses"]:
                code = candidate
                break
        if code is None:
            code = "defense" if ("退潮" in status or "冰点" in status) else "cautious"
    elif score is not None:
        code = "attack" if score >= 60 else "balanced" if score >= 20 else "cautious" if score >= -20 else "defense"
    else:
        code = "defense"
    # High risk downgrades one step even when the label is still constructive.
    if code == "attack" and risk is not None and risk >= 55:
        code = "balanced"
    elif code == "balanced" and risk is not None and risk >= 65:
        code = "cautious"
    elif code == "cautious" and risk is not None and risk >= (policies["cautious"].get("risk_ceiling") or 70):
        code = "defense"
    chosen = policies[code]
    return {"code": code, "label": REGIME_LABELS[code], "exposure": _num(chosen["exposure"], 0),
            "min_score": _num(chosen["min_score"], 70), "max_positions": int(_num(chosen["max_positions"], 0)),
            "status": status, "risk_score": risk, "score": score,
            "reason": "status=%s risk=%s" % (status or score, risk)}


def new_run(now, regime, candidates=0):
    return {"started_at": now.isoformat(), "regime": regime.get("code"), "candidates": candidates,
            "counts": {"scored": 0, "structure_pass": 0, "score_pass": 0, "ai_pass": 0,
                       "risk_pass": 0, "orders": 0, "fills": 0, "closed": 0},
            "blockers": {}, "top": [], "errors": []}


def bump(run, key, amount=1):
    run["counts"][key] = run["counts"].get(key, 0) + amount


def blocker(run, reason, detail=None):
    item = run["blockers"].setdefault(reason, {"count": 0, "symbols": []})
    item["count"] += 1
    if detail and len(item["symbols"]) < 8:
        item["symbols"].append(detail)


def finish(state, run, now, cycle_status):
    counts = run["counts"]
    closed_today = [p for p in state.get("closed", []) if p.get("sell_date") == now.date().isoformat()]
    counts["closed"] = len(closed_today)
    blockers = sorted(({"reason": k, **v} for k, v in run["blockers"].items()),
                      key=lambda item: -item["count"])[:8]
    stages = [
        {"id": "universe", "label": "股票池", "count": run["candidates"], "status": "ok" if run["candidates"] else "idle"},
        {"id": "signal", "label": "多层信号", "count": counts["scored"], "status": "ok" if counts["scored"] else "idle"},
        {"id": "structure", "label": "结构通过", "count": counts["structure_pass"],
         "status": "ok" if counts["structure_pass"] else ("blocked" if counts["scored"] else "idle")},
        {"id": "score", "label": "评分达标", "count": counts["score_pass"],
         "status": "ok" if counts["score_pass"] else ("blocked" if counts["structure_pass"] else "idle")},
        {"id": "ai", "label": "AI投研", "count": counts["ai_pass"],
         "status": "ok" if counts["ai_pass"] else ("blocked" if counts["score_pass"] else "idle")},
        {"id": "risk", "label": "风控仓位", "count": counts["risk_pass"],
         "status": "ok" if counts["risk_pass"] else ("blocked" if counts["ai_pass"] else "idle")},
        {"id": "order", "label": "模拟委托", "count": counts["orders"],
         "status": "ok" if counts["orders"] else "idle"},
        {"id": "fill", "label": "成交", "count": counts["fills"], "status": "ok" if counts["fills"] else "idle"},
        {"id": "exit", "label": "退出", "count": counts["closed"],
         "status": "ok" if counts["closed"] else ("watching" if state.get("positions") else "idle")},
        {"id": "review", "label": "归因复盘", "count": (state.get("attribution") or {}).get("samples", 0),
         "status": "ok" if (state.get("attribution") or {}).get("samples") else "waiting"},
        {"id": "optimize", "label": "参数优化", "count": len((state.get("optimizer") or {}).get("history") or []),
         "status": (state.get("optimizer") or {}).get("status") or "waiting"},
    ]
    ai = state.get("ai") or {}
    research = state.get("research") or {}
    state["loop"] = {
        "updated_at": now.isoformat(),
        "cycle_status": cycle_status,
        "regime": run["regime"],
        "stages": stages,
        "funnel": {"candidates": run["candidates"], **counts},
        "blockers": blockers,
        "health": {
            "data_fresh": bool(state.get("market")),
            "ai_online": bool(ai.get("desktop_online")),
            "research_ok": not bool(research.get("errors")),
            "positions": len(state.get("positions", [])),
            "max_positions": (state.get("risk_config") or {}).get("max_positions"),
        },
        "next": _next_action(state, run, cycle_status),
    }
    return state["loop"]


def _next_action(state, run, cycle_status):
    if cycle_status == "outside_session":
        return "等待交易时段；盘后任务继续结算归因与优化"
    if cycle_status == "defense":
        return "防守状态：只管理退出，不开新仓"
    if cycle_status == "kill_switch":
        return "风控停止开仓；卖出与归因继续执行"
    if cycle_status == "paused":
        return "新开仓已暂停；持仓退出继续监控"
    if cycle_status == "degraded":
        return "数据异常已降级；保留已完成退出，等待下一轮"
    if run["counts"]["fills"]:
        return "已成交：按止盈/止损/移动止盈管理持仓"
    if run["counts"]["score_pass"]:
        return "有标的通过评分，检查 AI 与仓位约束"
    if run["blockers"]:
        top = max(run["blockers"].items(), key=lambda item: item[1]["count"])
        return "主要拦截：%s（%d 次），等待结构修复" % (top[0], top[1]["count"])
    return "本轮无候选，等待下一轮扫描"
