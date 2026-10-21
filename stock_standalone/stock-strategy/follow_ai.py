"""Durable AI research jobs and bounded proposal admission for paper follow."""
import hashlib
import json
import math
import uuid
from datetime import timedelta

DEFAULT_AI = {"enabled": False, "mode": "shadow", "node_id": "", "workspace_id": "", "interval_seconds": 900, "model": "gpt-6-luna", "reasoning_effort": "medium"}


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
    return {"schema_version": 1, "trade_date": now.date().isoformat(), "as_of": now.isoformat(),
            "mode": "paper", "market": state.get("market", {}), "rotation": rotation, "stocks": stocks,
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
    prior = state.get("ai_last_requested_at")
    if prior and (now - af.stamp(prior)).total_seconds() < policy.get("interval_seconds", 900):
        return None
    context = evidence_context(state, now)
    phase = stage or ("interactive" if question else "post_close_review" if now.strftime("%H:%M") >= "15:35" else
                      "premarket" if now.strftime("%H:%M") < "09:30" else "intraday")
    context["workflow_stage"] = phase
    context["ai_runtime"] = {"model": policy.get("model", "gpt-6-luna"), "reasoning_effort": policy.get("reasoning_effort", "medium")}
    context['auto_research_revision'] = policy.get('revision', 0)
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


def sync_ai(db, state, now):
    import auto_follow as af
    db.execute("UPDATE ai_jobs SET status='expired' WHERE status IN ('queued','running') AND expires_at<=?", (now.isoformat(),))
    try:
        db.execute("UPDATE automatic_research_runs SET usage_known=1, total_tokens=COALESCE(total_tokens, 0) WHERE usage_known=0 AND job_id IN (SELECT id FROM ai_jobs WHERE status IN ('expired','failed','cancelled','completed'))")
    except Exception:
        pass
    policy = state.get("ai_settings", DEFAULT_AI)
    rows = db.execute("SELECT id,status,question,created_at,finished_at,result,evidence_hash,trade_date,context FROM ai_jobs WHERE node_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT 20",
                      (policy.get("node_id", ""), policy.get("workspace_id", ""))).fetchall()
    jobs = []
    for row in rows:
        job_id, status, question, created, finished, raw, evidence_hash, trade_date, context_raw = row
        item = {"id": job_id, "status": status, "question": question, "created_at": created, "finished_at": finished,
                "evidence_hash": evidence_hash, "trade_date": trade_date}
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
                    destination = "ai_review" if context.get("workflow_stage") in ("post_close_review", "execution_review") else "ai_latest"
                    if not state.get(destination) or created > state[destination].get("created_at", ""):
                        state[destination] = {**item, "as_of": context["as_of"], "workflow_stage": context.get("workflow_stage"),
                                              "basis_context": {"account": context.get("account"), "risk": context.get("risk")}}
                except (KeyError, ValueError, TypeError):
                    item["status"] = "invalid_result"
        jobs.append(item)
    health = db.execute("SELECT heartbeat,status,detail FROM ai_desktop WHERE node_id=? AND workspace_id=?",
                        (policy.get("node_id", ""), policy.get("workspace_id", ""))).fetchone()
    state["ai"] = {"jobs": jobs, "desktop_online": bool(health and 0 <= (now - af.stamp(health[0])).total_seconds() < 90),
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


def schedule_workflow(db, state, now, calendar):
    """Existing worker owns scheduling; no feed-pulse/heartbeat cron is cloned."""
    if not calendar.is_trading_day(now.date().isoformat(), "CN"):
        return
    if not "08:30" <= now.strftime("%H:%M") <= "17:30":
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
