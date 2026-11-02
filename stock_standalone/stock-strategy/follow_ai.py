"""Durable AI research jobs and bounded proposal admission for paper follow."""
import hashlib
import json
import math
import sqlite3
import uuid
from datetime import timedelta

DEFAULT_AI = {"enabled": False, "mode": "shadow", "node_id": "", "workspace_id": "", "interval_seconds": 900, "model": "gpt-6-luna", "reasoning_effort": "medium"}
POLICY_DEFAULT = {"enabled": False, "interval_seconds": 900, "daily_max_runs": 3, "daily_token_budget": 300000}
REVIEW_QUESTION = "盘后闭环复盘：核对当日市场状态、漏斗拦截、AI提案与实际成交/退出，指出最大的闭环瓶颈与下一交易日观察重点；不直接修改参数。"
REVIEW_STAGES = ("post_close_review", "execution_review")
REVIEW_MAX_ATTEMPTS = 3
AI_JOB_DETAIL = 5


def init_ai(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ai_jobs(
      id TEXT PRIMARY KEY, trade_date TEXT NOT NULL, evidence_hash TEXT NOT NULL,
      node_id TEXT NOT NULL, workspace_id TEXT NOT NULL, context TEXT NOT NULL,
      question TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued', lease_token TEXT, lease_until TEXT,
      result TEXT, result_hash TEXT, finished_at TEXT);
    CREATE INDEX IF NOT EXISTS ai_jobs_queue ON ai_jobs(node_id,workspace_id,status,created_at);
    CREATE TABLE IF NOT EXISTS ai_desktop(node_id TEXT,workspace_id TEXT,heartbeat TEXT,status TEXT,
      detail TEXT,PRIMARY KEY(node_id,workspace_id));
    """)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def admission(db, now):
    """Mirror the API claim gate so a job is never queued that cannot be claimed.

    The server refuses a claim when the day's run count, the token budget, an
    unsettled run or its own interval says no.  Queueing anyway produced jobs
    that could only expire ten minutes later, and the UI then blamed the desktop
    for not picking them up.  Returns None when the run ledger is unreadable, so
    a missing table or a read error never stalls research by itself.
    """
    from auto_research_policy import _parse_iso
    try:
        row = db.execute("SELECT body FROM automatic_research_policy WHERE id=1").fetchone()
        policy = {**POLICY_DEFAULT, **(json.loads(row[0]) if row else {})}
        day = now.date().isoformat()
        # The console can clear a day's usage; those rows stay for audit but stop
        # counting.  Older databases predate the column, so probe for it.
        cleared = any(column[1] == "cleared" for column in db.execute("PRAGMA table_info(automatic_research_runs)"))
        usage = ("SELECT count(*),COALESCE(sum(total_tokens),0),"
                 "COALESCE(sum(CASE WHEN usage_known=0 THEN 1 ELSE 0 END),0) "
                 "FROM automatic_research_runs WHERE day=?")
        runs, tokens, unknown = db.execute(usage + (" AND cleared=0" if cleared else ""), (day,)).fetchone()
        last = db.execute("SELECT started_at FROM automatic_research_runs" + (" WHERE cleared=0" if cleared else "")
                          + " ORDER BY started_at DESC LIMIT 1").fetchone()
    except (sqlite3.Error, ValueError, TypeError):
        return None
    remaining = None
    if last and last[0]:
        try:
            remaining = int(policy.get("interval_seconds", 900) - (now - _parse_iso(last[0])).total_seconds())
        except (ValueError, TypeError, OverflowError):
            remaining = None
    max_runs, budget = int(policy.get("daily_max_runs", 3)), int(policy.get("daily_token_budget", 300000))
    if policy.get("enabled") is not True:
        status = "disabled"
    elif unknown:
        status = "usage_unsettled"
    elif runs >= max_runs or tokens >= budget:
        status = "budget_exhausted"
    elif remaining is not None and remaining > 0:
        status = "interval_wait"
    else:
        status = "ready"
    return {"status": status, "day": day, "runs": runs, "max_runs": max_runs, "tokens": tokens,
            "token_budget": budget, "unsettled": unknown, "interval_remaining_seconds": remaining,
            "checked_at": now.isoformat()}


def review_state(db, day):
    """(completed, attempts) for the day's explicit review jobs.

    The job table is the source of truth, so a lost state file cannot silently
    skip a whole day of review, and an expired attempt is retried instead of
    ending the day with no review at all.
    """
    completed, attempts = False, 0
    try:
        rows = db.execute("SELECT status,context FROM ai_jobs WHERE trade_date=? ORDER BY created_at DESC LIMIT 60",
                          (day,)).fetchall()
    except sqlite3.Error:
        return False, REVIEW_MAX_ATTEMPTS
    for status, raw in rows:
        try:
            stage = json.loads(raw).get("workflow_stage")
        except (ValueError, TypeError, AttributeError):
            continue
        if stage != "post_close_review" or status == "cancelled":
            continue
        attempts += 1
        completed = completed or status == "completed"
    return completed, attempts


def unclaimed_reason(state):
    """Say why a queued job expired unclaimed instead of always blaming the desktop."""
    gate = state.get("auto_research_admission") or {}
    status = gate.get("status")
    if status == "budget_exhausted":
        return "服务端额度已用尽（%s/%s 次），任务未被领取" % (gate.get("runs"), gate.get("max_runs"))
    if status == "usage_unsettled":
        return "服务端用量未结算，任务未被领取"
    if status == "interval_wait":
        return "服务端调用间隔未到，任务未被领取"
    if status == "disabled":
        return "自动投研已停用，任务未被领取"
    return "等待桌面领取超时"


def evidence_context(state, now):
    stocks = []
    for stock in state.get("candidates", [])[:25]:
        plan = stock.get("plan", {})
        stocks.append({k: stock[k] for k in ("symbol", "name", "theme", "route", "streak") if k in stock} |
                      {"analysis": {k: plan[k] for k in ("checked_at", "trade_time", "daily_trade_date", "source",
                          "fresh_quote", "metrics", "checks", "blocker", "errors") if k in plan}})
    rotation = {}
    for dim in ("industry", "theme"):
        snap = state.get("research", {}).get(dim, {})
        rows = snap.get("rows", [])
        rotation[dim] = {"meta": snap.get("meta"), "error": snap.get("error"), "coverage": snap.get("coverage"),
                         "rows": rows[:8] + rows[-8:] if len(rows) > 16 else rows}
    closed = state.get("closed", [])
    loop = state.get("loop") or {}
    optimizer_state = state.get("optimizer") or {}
    attribution_state = state.get("attribution") or {}
    scan = state.get("strong_scan") or {}
    return {"schema_version": 1, "trade_date": now.date().isoformat(), "as_of": now.isoformat(),
            "mode": "paper", "market": state.get("market", {}), "regime": state.get("regime", {}),
            "rotation": rotation, "stocks": stocks,
            "loop": {"funnel": loop.get("funnel"), "blockers": (loop.get("blockers") or [])[:6],
                     "stages": loop.get("stages"), "next": loop.get("next")},
            "strong_scan": [{k: row[k] for k in ("symbol", "name", "score", "change_percent", "theme", "sources")
                             if k in row} for row in (scan.get("rows") or [])[:10]],
            "attribution": {"samples": attribution_state.get("samples"), "settled": attribution_state.get("settled"),
                            "blockers": (attribution_state.get("blockers") or [])[:5],
                            "buckets": attribution_state.get("buckets"),
                            "trades": attribution_state.get("trades")},
            "optimizer": {"status": optimizer_state.get("status"), "version": optimizer_state.get("version"),
                          "proposal": optimizer_state.get("proposal"), "reason": optimizer_state.get("reason")},
            "account": {"cash": state["cash"], "positions": [{k: p[k] for k in
                ("symbol", "name", "theme", "shares", "buy_price", "buy_date", "last_price", "last_price_at") if k in p}
                for p in state["positions"]], "closed_count": len(closed),
                "realized_pnl": sum(p.get("pnl", 0) for p in closed), "recent_closed": closed[-20:]},
            "recent_decisions": state.get("events", [])[-30:], "risk": state.get("risk_config", {}),
            "validation_scope": state.get("validation_scope", "production_paper"),
            "scope": "CN main-board paper; reference snapshots are not realtime; p22_l2 remains disconnected"}


def enqueue(db, state, now, question="", force=False, stage=None):
    import auto_follow as af
    from auto_research_policy import selection
    policy, status = selection(db, now)
    state['auto_research_status'] = status
    if policy is None:
        return None
    pending = db.execute("SELECT id,context FROM ai_jobs WHERE node_id=? AND workspace_id=? AND status IN ('queued','running') AND expires_at>? LIMIT 1",
                         (policy["node_id"], policy["workspace_id"], now.isoformat())).fetchone()
    if pending and not force:
        if stage and json.loads(pending[1]).get("workflow_stage") != stage:
            return None
        return pending[0]
    gate = admission(db, now)
    if gate is not None:
        state["auto_research_admission"] = gate
        if gate["status"] != "ready":
            # The server would refuse the claim; do not create a job that can
            # only expire and then be misreported as a desktop timeout.
            state["auto_research_status"] = gate["status"]
            return None
    prior = state.get("ai_last_requested_at")
    if prior and (now - af.stamp(prior)).total_seconds() < policy.get("interval_seconds", 900):
        return None
    context = evidence_context(state, now)
    phase = stage or ("interactive" if question else "post_close_review" if now.strftime("%H:%M") >= "15:35" else
                      "premarket" if now.strftime("%H:%M") < "09:30" else "intraday")
    context["workflow_stage"] = phase
    # Only an explicitly staged review may replace the review panel; a generic
    # post-close snapshot keeps its own slot instead of overwriting the review.
    context["review_stage"] = stage if stage in REVIEW_STAGES else None
    context["ai_runtime"] = {"model": policy.get("model", "gpt-6-luna"), "reasoning_effort": policy.get("reasoning_effort", "medium")}
    context['auto_research_revision'] = policy.get('revision', 0)
    # Keep all stock and freshness evidence; trim only explicitly marked optional
    # summaries before hashing so both bridges receive the same frozen input.
    def input_size():
        envelope = {'context': context, 'question': question[:4000], 'evidence_hash': '0' * 64}
        return len(json.dumps(envelope, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    omitted = []
    for key in ('recent_decisions',):
        if input_size() > 24000:
            context[key] = []
            omitted.append(key)
    for dim in ('industry', 'theme'):
        if input_size() > 24000:
            context['rotation'][dim]['rows'] = []
            omitted.append('rotation.' + dim + '.rows')
    if input_size() > 24000:
        context['account']['recent_closed'] = []
        omitted.append('account.recent_closed')
    if input_size() > 24000:
        context['loop']['stages'] = []
        context['strong_scan'] = []
        omitted.append('loop.stages,strong_scan')
    if input_size() > 24000:
        context['attribution'] = {}
        context['optimizer']['history'] = []
        omitted.append('attribution,optimizer.history')
    if omitted:
        context['omitted_evidence'] = omitted
    if input_size() > 24000:
        raise ValueError('AI_EVIDENCE_TOO_LARGE')
    if not force and phase != "intraday" and state.get("ai_phase_requested") == phase + ":" + context["trade_date"]:
        return None
    if db.execute("SELECT COUNT(*) FROM ai_jobs WHERE node_id=? AND workspace_id=? AND status IN ('queued','running') AND expires_at>?",
                  (policy["node_id"], policy["workspace_id"], now.isoformat())).fetchone()[0] >= 8:
        raise ValueError("AI queue full")
    if not context["stocks"] and not question:
        return None
    identity = uuid.uuid4().hex
    raw = json.dumps(context, ensure_ascii=False, allow_nan=False)
    db.execute("INSERT INTO ai_jobs(id,trade_date,evidence_hash,node_id,workspace_id,context,question,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?)",
               (identity, context["trade_date"], digest(context), policy["node_id"], policy["workspace_id"], raw,
                question[:4000], now.isoformat(), (now + timedelta(minutes=10)).isoformat()))
    state["ai_last_requested_at"] = now.isoformat()
    state["ai_phase_requested"] = phase + ":" + context["trade_date"]
    return identity


PLAN_PROPERTIES = {"symbol": {"type": "string"}, "action": {"type": "string", "enum": ["observe", "follow", "avoid"]},
    "thesis": {"type": "string"}, "entry_low": {"type": ["number", "null"]}, "entry_high": {"type": ["number", "null"]},
    "invalidation": {"type": "string"}, "exit_response": {"type": "string"},
    "evidence_refs": {"type": "array", "items": {"type": "string"}},
    "missing_data": {"type": "array", "items": {"type": "string"}}}
RESPONSE_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"market_view": {"type": "string"}, "rotation_view": {"type": "string"},
        "answer": {"type": "string"}, "plans": {"type": "array", "items": {"type": "object",
            "additionalProperties": False, "properties": PLAN_PROPERTIES, "required": list(PLAN_PROPERTIES)}}},
    "required": ["market_view", "rotation_view", "answer", "plans"]}


def validate_result(result, context):
    if not isinstance(result, dict) or set(result) != set(RESPONSE_SCHEMA["required"]):
        raise ValueError("AI result schema mismatch")
    for key in ("market_view", "rotation_view", "answer"):
        if not isinstance(result[key], str) or len(result[key]) > 12000:
            raise ValueError("AI narrative invalid")
    plans = result["plans"]
    symbols = {s["symbol"] for s in context["stocks"]}
    references = {"market", "rotation:industry", "rotation:theme", "ats:ipc"} | {"stock:" + code for code in symbols}
    seen = set()
    if not isinstance(plans, list) or len(plans) > 25:
        raise ValueError("AI plans invalid")
    for plan in plans:
        if not isinstance(plan, dict) or set(plan) != set(PLAN_PROPERTIES):
            raise ValueError("AI plan schema mismatch")
        if plan["symbol"] not in symbols or plan["symbol"] in seen or plan["action"] not in ("observe", "follow", "avoid"):
            raise ValueError("AI plan symbol/action invalid")
        seen.add(plan["symbol"])
        for key in ("thesis", "invalidation", "exit_response"):
            if not isinstance(plan[key], str) or len(plan[key]) > 3000:
                raise ValueError("AI plan text invalid")
        for key in ("evidence_refs", "missing_data"):
            if not isinstance(plan[key], list) or len(plan[key]) > 30 or any(not isinstance(v, str) or len(v) > 300 for v in plan[key]):
                raise ValueError("AI references invalid")
        if any(ref not in references for ref in plan["evidence_refs"]):
            raise ValueError("AI evidence reference unknown")
        if plan["action"] == "follow" and "stock:" + plan["symbol"] not in plan["evidence_refs"]:
            raise ValueError("AI follow proposal lacks stock evidence")
        low, high = plan["entry_low"], plan["entry_high"]
        if (low is None) != (high is None):
            raise ValueError("AI range incomplete")
        if low is not None and (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (low, high)) or not 0 < low <= high):
            raise ValueError("AI range invalid")
    return result


def slim_job(item, rank):
    """Keep the expandable answer for the newest jobs only.

    Every cycle rewrites the whole state row, and sixteen completed jobs with
    full proposals were the second largest block in it.  Older entries keep
    their status, identifiers and error so the task list stays complete.
    """
    if rank < AI_JOB_DETAIL:
        return item
    result = item.get("result")
    if not isinstance(result, dict):
        return item
    proposal = result.get("proposal") if isinstance(result.get("proposal"), dict) else {}
    trimmed = {key: result[key] for key in ("thread_id", "model", "reasoning_effort", "error_code", "token_usage")
               if key in result}
    trimmed["proposal"] = {key: proposal[key] for key in ("answer", "market_view", "rotation_view") if key in proposal}
    return {**item, "result": trimmed}


def sync_ai(db, state, now):
    import auto_follow as af
    gate = admission(db, now)
    if gate is not None:
        # Keep the ledger's own verdict next to the jobs so an unclaimed expiry
        # can name the real reason instead of always blaming the desktop.
        state["auto_research_admission"] = gate
    db.execute("UPDATE ai_jobs SET status='expired' WHERE status IN ('queued','running') AND expires_at<=?", (now.isoformat(),))
    try:
        db.execute("UPDATE automatic_research_runs SET usage_known=1, total_tokens=COALESCE(total_tokens, 0) WHERE usage_known=0 AND job_id IN (SELECT id FROM ai_jobs WHERE status IN ('expired','failed','cancelled','completed'))")
    except sqlite3.OperationalError as exc:
        if 'no such table' not in str(exc):
            raise
    runtime_row = db.execute('SELECT body FROM desktop_chat_config WHERE id=1').fetchone()
    policy = json.loads(runtime_row[0]) if runtime_row else {}
    rows = db.execute("SELECT id,status,question,created_at,finished_at,result,evidence_hash,trade_date,context,lease_token FROM ai_jobs ORDER BY created_at DESC LIMIT 20").fetchall()
    jobs = []
    for row in rows:
        job_id, status, question, created, finished, raw, evidence_hash, trade_date, context_raw, lease = row
        item = {"id": job_id, "status": status, "question": question, "created_at": created, "finished_at": finished,
                "evidence_hash": evidence_hash, "trade_date": trade_date}
        if status == 'expired':
            item['error'] = '执行或回传超时' if lease else unclaimed_reason(state)
        if raw:
            try:
                result = json.loads(raw)
            except (ValueError, TypeError):
                item["status"] = "invalid_result"
                jobs.append(item)
                continue
            item["result"] = result
            if status == "completed":
                try:
                    validate_result(result["proposal"], json.loads(context_raw))
                    context = json.loads(context_raw)
                    stage = context.get("review_stage", context.get("workflow_stage"))
                    destination = "ai_review" if stage in REVIEW_STAGES else "ai_latest"
                    if not state.get(destination) or created > state[destination].get("created_at", ""):
                        state[destination] = {**item, "as_of": context["as_of"], "workflow_stage": context.get("workflow_stage"),
                                              "basis_context": {"account": context.get("account"), "risk": context.get("risk")}}
                except (KeyError, ValueError, TypeError):
                    item["status"] = "invalid_result"
        jobs.append(item)
    health = db.execute("SELECT heartbeat,status,detail FROM ai_desktop WHERE node_id=? AND workspace_id=?",
                        (policy.get("node_id", ""), policy.get("workspace_id", ""))).fetchone()
    state["ai"] = {"jobs": [slim_job(item, rank) for rank, item in enumerate(jobs)], "desktop_online": bool(health and 0 <= (now - af.stamp(health[0])).total_seconds() < 90),
                   "desktop_heartbeat": health[0] if health else None, "desktop_status": health[1] if health else "not_connected",
                   "desktop_detail": json.loads(health[2]) if health and health[2] else {}}


def ai_entry_gate(state, code, price, now):
    import auto_follow as af
    policy = state.get("ai_settings", DEFAULT_AI)
    latest = state.get("ai_latest", {})
    if not policy.get("enabled"):
        return {"mode": "shadow", "status": "not_enforced", "reason": "AI_disabled"}
    if policy.get("mode") == "shadow":
        comparison = {**state, "ai_settings": {**policy, "mode": "enforce"}}
        try:
            decision = ai_entry_gate(comparison, code, price, now)
            return {**decision, "mode": "shadow", "status": "not_enforced", "would_admit": True}
        except ValueError as exc:
            return {"mode": "shadow", "status": "not_enforced", "would_admit": False, "reason": str(exc), "job_id": latest.get("id")}
    if latest.get("trade_date") != now.date().isoformat() or not latest.get("as_of") or not 0 <= (now - af.stamp(latest["as_of"])).total_seconds() <= 300:
        raise ValueError("AI proposal missing or expired")
    result = latest.get("result", {})
    plans = result.get("proposal", {}).get("plans", [])
    plan = next((p for p in plans if p.get("symbol") == code), None)
    if not plan or plan.get("action") != "follow" or plan.get("missing_data") or not plan.get("evidence_refs"):
        raise ValueError("AI proposal does not admit entry")
    if plan.get("entry_low") is not None and not plan["entry_low"] <= price <= plan["entry_high"]:
        raise ValueError("AI conditional range not reached")
    return {"mode": "enforce", "status": "admitted", "job_id": latest["id"], "evidence_hash": latest["evidence_hash"],
            "thread_id": result.get("thread_id"), "action": plan["action"]}


def ai_overlay(state, code, price, now, cfg):
    """AI as a weighted evidence layer, not a hard 5-minute switch.

    ``veto`` is reserved for an explicit ``avoid`` plan (or a configured hard
    fallback).  A missing/expired proposal degrades to neutral in paper mode so
    the deterministic structure gates keep working while the desktop is away.
    """
    import auto_follow as af
    execution = (cfg or {}).get("execution") or {}
    gate = {"mode": "overlay", "weight": 12, "ttl_seconds": 900, "veto_on_avoid": True, "fallback": "neutral",
            **(execution.get("ai_gate") or {})}
    policy = state.get("ai_settings", DEFAULT_AI)
    if not policy.get("enabled") or gate.get("mode") == "off":
        return {"mode": "off", "status": "off", "delta": 0, "veto": False, "reason": "AI_disabled"}
    latest = state.get("ai_latest") or {}
    try:
        age = (now - af.stamp(latest["as_of"])).total_seconds()
    except (KeyError, ValueError, TypeError):
        age = None
    fresh = (latest.get("trade_date") == now.date().isoformat() and age is not None
             and 0 <= age <= float(gate.get("ttl_seconds", 900)))
    if not fresh:
        fallback = gate.get("fallback", "neutral")
        return {"mode": gate.get("mode", "overlay"), "status": "neutral" if fallback != "block" else "blocked",
                "delta": 0, "veto": fallback == "block", "reason": "AI proposal missing or expired",
                "job_id": latest.get("id"), "evidence_hash": latest.get("evidence_hash"),
                "age_seconds": int(age) if age is not None else None}
    plans = ((latest.get("result") or {}).get("proposal") or {}).get("plans") or []
    plan = next((item for item in plans if item.get("symbol") == code), None)
    base = {"mode": gate.get("mode", "overlay"), "job_id": latest.get("id"),
            "evidence_hash": latest.get("evidence_hash"), "age_seconds": int(age)}
    if not plan:
        return {**base, "status": "neutral", "delta": 0, "veto": False, "reason": "AI has no plan for symbol"}
    action = plan.get("action")
    if action == "avoid" and gate.get("veto_on_avoid", True):
        return {**base, "status": "veto", "delta": 0, "veto": True, "reason": "AI avoid"}
    if action == "follow" and not plan.get("missing_data") and plan.get("evidence_refs"):
        low, high = plan.get("entry_low"), plan.get("entry_high")
        if low is None or low <= price <= high:
            return {**base, "status": "admit", "delta": int(gate.get("weight", 12)), "veto": False,
                    "reason": "AI follow within range"}
        return {**base, "status": "neutral", "delta": 0, "veto": False, "reason": "AI conditional range not reached"}
    return {**base, "status": "neutral", "delta": 0, "veto": False, "reason": "AI observe"}


def schedule_workflow(db, state, now, calendar):
    """Existing worker owns scheduling; no feed-pulse/heartbeat cron is cloned."""
    if not calendar.is_trading_day(now.date().isoformat(), "CN"):
        return
    if not "08:30" <= now.strftime("%H:%M") <= "17:30":
        return
    today = now.date().isoformat()
    if now.strftime("%H:%M") >= "15:35":
        completed, attempts = review_state(db, today)
        if not completed and attempts < REVIEW_MAX_ATTEMPTS:
            job = enqueue(db, state, now, question=REVIEW_QUESTION, stage="post_close_review", force=True)
            if job:
                state["ai_review_day"] = today
                return
    closed_count = len(state.get("closed", []))
    if closed_count > state.get("ai_review_requested_closed_count", 0):
        job = enqueue(db, state, now, question="复盘已实际发生的模拟成交、拒绝和退出，核对AI提案与风控执行差异，提出下一轮观察重点，不修改参数。",
                      stage="execution_review", force=True)
        if job:
            requested = json.loads(db.execute("SELECT context FROM ai_jobs WHERE id=?", (job,)).fetchone()[0])
            state["ai_review_requested_closed_count"] = requested["account"]["closed_count"]
        return
    import auto_follow as af
    # A newly valid entry blocked only by stale AI evidence requests a fresh
    # analysis; it never reuses an old narrative as a current trading decision.
    last_requested=state.get("ai_last_requested_at")
    waiting=any(e.get("action")=="AI_DECISION" and e.get("decision",{}).get("reason")=="AI proposal missing or expired" and
                0 <= (now-af.stamp(e["at"])).total_seconds() <= 120 for e in state.get("events",[])[-40:])
    if waiting and (not last_requested or (now-af.stamp(last_requested)).total_seconds() >= 120):
        policy=state.get("ai_settings",DEFAULT_AI)
        pending=db.execute("SELECT 1 FROM ai_jobs WHERE node_id=? AND workspace_id=? AND status IN ('queued','running') AND expires_at>? LIMIT 1",
                           (policy.get('node_id',''),policy.get('workspace_id',''),now.isoformat())).fetchone()
        if not pending:
            enqueue(db,state,now,force=True,stage="intraday_refresh")
        # One pending research job at a time; event-triggered refreshes are
        # throttled separately from the normal 15-minute research cadence.
        return
    enqueue(db, state, now)
