"""CN paper-only follower. Never imports a broker or submits real orders."""
import argparse
import json
import math
import os
import re
from pathlib import Path
import sqlite3
import sys
import time
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
SERVICE = Path(os.environ.get("EASY_STOCK_FOLLOW_SERVICE_DIR", str(ROOT / "source" / "easy-stock-service")))
BJ = ZoneInfo("Asia/Shanghai")
VERSION = "paper-follow-v1"


def number(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not market data")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non-finite market data")
    return value


def stamp(value):
    value = value.replace("Z", "+00:00")
    # Go RFC3339Nano fractions exceed Python 3.9's microsecond parser.
    value = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d+)([+-]\d{2}:\d{2})$",
                   lambda m: m[1] + "." + m[2][:6].ljust(6, "0") + m[3], value)
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return result.astimezone(BJ)


def fresh(meta, now, age=120):
    if (not meta.get("source") or meta.get("stale") is not False
            or meta.get("carry_forward") or meta.get("error")):
        raise ValueError("source unavailable or stale")
    elapsed = (now - stamp(meta["fetched_at"])).total_seconds()
    if not 0 <= elapsed <= age:
        raise ValueError("source snapshot expired")
    if meta.get("trade_date") and meta["trade_date"] != now.date().isoformat():
        raise ValueError("cross-day snapshot")


def symbol(value):
    value = str(value).upper()
    code = value.replace(".SH", "").replace(".SZ", "")
    if code.startswith(("SH", "SZ")):
        code = code[2:]
    # First release: existing 100-share main-board order model only.
    if len(code) != 6 or not code.isdigit() or not code.startswith(("00", "60")):
        raise ValueError("unsupported board")
    return code + (".SH" if code.startswith("60") else ".SZ")


def quote_ok(q, now):
    fresh(q["meta"], now)
    elapsed = (now - stamp(q["trade_time"])).total_seconds()
    if not 0 <= elapsed <= 120 or stamp(q["trade_time"]).date() != now.date():
        raise ValueError("quote trade_time expired")
    price, previous = number(q["price"]), number(q["previous_close"])
    if price <= 0 or previous <= 0:
        raise ValueError("invalid price")
    change = (price / previous - 1) * 100
    if abs(change - number(q["change_percent"])) > 0.15:
        raise ValueError("inconsistent change_percent")
    return price, change


def exact_vwap(bars):
    if not bars or any(number(b["amount"]) <= 0 or number(b["volume"]) <= 0
                       or b.get("vwap_estimated") for b in bars):
        raise ValueError("exact VWAP unavailable")
    shares = 0
    for b in bars:
        meta = b.get("meta", {})
        fields = meta.get("available_fields", [])
        if "volume_shares" in fields or meta.get("source") in ("sina", "yahoo", "kraken", "instock-tdx-daily"):
            units = 1
        elif meta.get("source") == "eastmoney":
            units = 100
        else:
            raise ValueError("volume unit unavailable")
        if meta.get("source") == "instock-tdx-daily":
            # Local writer converts TDX lots to shares before exporting forwardp;
            # reject legacy/mixed-unit files instead of trusting the source name alone.
            average = number(b["amount"]) / number(b["volume"])
            if not number(b["low"]) * .99 <= average <= number(b["high"]) * 1.01:
                raise ValueError("daily amount-volume unit mismatch")
        shares += number(b["volume"]) * units
    value = sum(number(b["amount"]) for b in bars) / shares
    if value <= 0:
        raise ValueError("invalid VWAP")
    return value


def entry_ok(q, minute, daily, cfg, now, previous_day):
    price, change = quote_ok(q, now)
    if "ST" in q.get("name", "").upper():
        raise ValueError("ST excluded")
    if not 0 < change <= cfg["buy"]["max_day_chg"]:
        raise ValueError("P4 change gate")
    # A sealed board is never assumed fillable. Main-board limits only.
    if price >= round(number(q["previous_close"]) * 1.10, 2) - 0.01:
        raise ValueError("sealed limit-up")
    today = now.date().isoformat()
    minute = sorted((b for b in minute if stamp(b["time"]).date() == now.date()
                     and stamp(b["time"]) <= now), key=lambda b: b["time"])
    if len(minute) < 4 or (now - stamp(minute[-1]["time"])).total_seconds() > 360:
        raise ValueError("intraday bars unavailable")
    for b in minute:
        fresh(b["meta"], now, 600)
    daily = sorted((b for b in daily if str(b["time"])[:10] < today), key=lambda b: b["time"])
    if len(daily) < 20 or str(daily[-1]["time"])[:10] != previous_day:
        raise ValueError("previous completed trading day unavailable")
    if any(b.get("meta", {}).get("stale") is not False or not b.get("meta", {}).get("source")
           for b in daily[-20:]):
        raise ValueError("daily source unavailable")
    v1, v3, v5, v10 = (exact_vwap(daily[-n:]) for n in (1, 3, 5, 10))
    if not v1 > v3 > v5 or number(daily[-1]["close"]) < sum(number(b["close"]) for b in daily[-20:]) / 20:
        raise ValueError("P25 trend gate")
    intraday = exact_vwap(minute)
    if not intraday * 1.005 <= price <= intraday * 1.025 or intraday < v3:
        raise ValueError("P8 VWAP gate")
    last = minute[-3:]
    if not all(number(b["close"]) >= number(a["close"]) and
               number(b["volume"]) >= number(a["volume"]) for a, b in zip(last, last[1:])):
        raise ValueError("P8 volume-price gate")
    if change > 3 and price < number(q["high"]) * 0.99:
        raise ValueError("intraday pullback veto")
    if number(q["open"]) >= number(q["previous_close"]) * 1.02 and price < number(q["open"]):
        raise ValueError("opening trap")
    return {"buy_vwap": v1, "buy_vwap10": v10}


def candidates(ladder, overview, now, previous_day, settings=None):
    settings = settings or {}
    result = {}
    fresh(ladder["meta"], now, 1800)
    if ladder["current"]["trade_date"] != now.date().isoformat():
        raise ValueError("ladder is not today's snapshot")
    if ladder["previous"]["trade_date"] != previous_day:
        raise ValueError("previous ladder date mismatch")
    for level in ladder["previous"]["levels"] if settings.get("limit_up", True) else []:
        for stock in level["stocks"]:
            if stock.get("is_st") or stock.get("streak", 0) < 2:
                continue
            try:
                code = symbol(stock["symbol"])
            except ValueError:
                continue
            result[code] = {"symbol": code, "name": stock["name"], "route": "limit_up",
                            "theme": stock.get("primary_theme"), "streak": stock["streak"]}
    fresh(overview["meta"], now, 1800)
    # Dynamic hot themes, deterministic ranking; no LLM-generated order instruction.
    themes = sorted(overview["data"], key=lambda t: number(t.get("change_percent", 0)), reverse=True)
    if settings.get("theme_ids"):
        themes = [t for t in themes if t["theme"] in settings["theme_ids"]]
    for theme in themes[:3] if settings.get("theme_trend", True) else []:
        if number(theme.get("change_percent", 0)) <= 0 or theme.get("rising_nodes", 0) <= theme.get("falling_nodes", 0):
            continue
        for stock in theme.get("leader_stocks", [])[:5]:
            try:
                code = symbol(stock["symbol"])
            except ValueError:
                continue
            result.setdefault(code, {"symbol": code, "name": stock["name"], "route": "theme_trend",
                                     "theme": theme["theme"], "streak": 0})
            if not result[code].get("theme"):
                # The same stock can be both a ladder candidate and a verified
                # leader in today's eligible theme; preserve that attribution.
                result[code]["theme"] = theme["theme"]
    return sorted(result.values(), key=lambda s: (-s["streak"], s["symbol"]))[:20]


def shared_permissions(path):
    if os.name == "posix" and os.environ.get("EASY_STOCK_FOLLOW_SHARED") == "1":
        for name in (str(path), str(path) + "-wal", str(path) + "-shm"):
            if Path(name).exists():
                os.chmod(name, 0o660)


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=1, isolation_level=None)
    shared_permissions(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)")
    shared_permissions(path)
    return db


def connect_control(path):
    control_path = Path(path).with_name("control.db")
    db = sqlite3.connect(control_path, timeout=3, isolation_level=None)
    shared_permissions(control_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS commands(
        id TEXT PRIMARY KEY, action TEXT NOT NULL, payload TEXT NOT NULL,
        created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        applied_at TEXT, result TEXT)""")
    db.execute("CREATE TABLE IF NOT EXISTS runtime(id INTEGER PRIMARY KEY CHECK(id=1), heartbeat TEXT NOT NULL, phase TEXT NOT NULL)")
    shared_permissions(control_path)
    return db


def initial():
    return {"version": VERSION, "mode": "paper", "initial_cash": 500000,
            "cash": 500000, "positions": [], "closed": [], "events": [],
            "seen": [], "kill": False, "enabled": True,
            "settings": {"limit_up": True, "theme_trend": True, "theme_ids": []}}


def apply_commands(db, state, now):
    rows = db.execute("SELECT id,action,payload FROM commands WHERE status='pending' ORDER BY created_at,id LIMIT 50").fetchall()
    receipts = []
    for command_id, action, payload in rows:
        previous = next((r for r in state.get("command_receipts", []) if r[0] == command_id), None)
        if previous:
            receipts.append(previous)
            continue
        result, status = "applied", "applied"
        try:
            if action in ("pause", "resume"):
                state["enabled"] = action == "resume"
            elif action in ("kill", "release_kill"):
                state["kill"] = action == "kill"
            elif action == "scan":
                result = "scan_requested; trading-session and data gates still apply"
            elif action == "ai_settings":
                import re
                from follow_ai import DEFAULT_AI
                data = json.loads(payload)
                if not {"enabled", "mode", "node_id", "workspace_id"} <= set(data) or set(data) - {"enabled", "mode", "node_id", "workspace_id", "model", "reasoning_effort"} or not isinstance(data["enabled"], bool) or data["mode"] not in ("shadow", "enforce"):
                    raise ValueError("invalid AI settings")
                if any(not isinstance(data[k], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", data[k]) for k in ("node_id", "workspace_id")):
                    raise ValueError("invalid AI desktop identity")
                if "model" in data and not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", data["model"]):
                    raise ValueError("invalid AI model")
                if data.get("reasoning_effort", "medium") not in ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"):
                    raise ValueError("invalid reasoning effort")
                state["ai_settings"] = {**DEFAULT_AI, **data}
                state.pop("ai_latest", None)
            elif action == "ai_ask":
                from follow_ai import enqueue
                data = json.loads(payload)
                if set(data) != {"question"} or not isinstance(data["question"], str) or not 1 <= len(data["question"].strip()) <= 4000:
                    raise ValueError("invalid AI question")
                job_id = enqueue(db, state, now, question=data["question"].strip(), force=True)
                if not job_id:
                    raise ValueError("AI desktop not configured or disabled")
                result = "ai_job=" + job_id
            elif action == "settings":
                data = json.loads(payload)
                if set(data) != {"limit_up", "theme_trend", "theme_ids"} or not all(isinstance(data[k], bool) for k in ("limit_up", "theme_trend")):
                    raise ValueError("invalid settings")
                ids = data["theme_ids"]
                if not isinstance(ids, list) or len(ids) > 10 or any(not isinstance(v, str) or not v or len(v) > 80 for v in ids):
                    raise ValueError("invalid theme IDs")
                state["settings"] = data
            else:
                raise ValueError("unsupported action")
        except (ValueError, TypeError, KeyError) as exc:
            result, status = str(exc), "rejected"
        event(state, now, "CONTROL", command_id=command_id, command=action, result=result, status=status)
        receipt = [command_id, status, now.isoformat(), result]
        receipts.append(receipt)
        state.setdefault("command_receipts", []).append(receipt)
        state["command_receipts"] = state["command_receipts"][-1000:]
    return receipts


def wait_next_cycle(db, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if db.execute("SELECT 1 FROM commands WHERE status='pending' LIMIT 1").fetchone():
            return
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def load_config():
    snapshot = os.environ.get("EASY_STOCK_FOLLOW_CONFIG")
    if snapshot:
        return json.loads(Path(snapshot).read_text(encoding="utf-8"))
    import yaml
    return yaml.safe_load((SERVICE / "strategy.yaml").read_text(encoding="utf-8"))


def backend_market(api, now):
    data = api("/api/v1/short-term/emotion-history")["data"]
    intraday = data["intraday"]
    if data.get("intraday_error"):
        raise ValueError("backend intraday emotion unavailable")
    fresh({"source": "go.marketemotion.intraday", "stale": intraday["stale"],
           "fetched_at": intraday["updated_at"], "trade_date": intraday["trade_date"]}, now, 660)
    metrics = intraday["metrics"]
    samples, quotes = number(metrics["high_sample_count"]), number(metrics["high_quote_count"])
    if samples <= 0 or quotes / samples < .75:
        raise ValueError("backend emotion quote coverage insufficient")
    return {"backend_status": intraday["status"], "risk_score": number(intraday["risk_score"]),
            "trade_date": intraday["trade_date"], "source": "go.marketemotion.intraday"}


def event(state, now, action, code="", **details):
    state["events"].append({"at": now.isoformat(), "action": action, "symbol": code, **details})
    state["events"] = state["events"][-2000:]


def sell(state, p, price, reason, now):
    pnl = round((price - p["buy_price"]) * p["shares"], 2)
    state["cash"] = round(state["cash"] + price * p["shares"], 2)
    state["closed"].append({**p, "sell_date": now.date().isoformat(), "sell_price": price,
                            "sold_at": now.isoformat(), "pnl": pnl, "reason": reason})
    state["positions"].remove(p)
    event(state, now, "SELL", p["symbol"], price=price, pnl=pnl, reason=reason)


def cycle(state, cfg, api, now, calendar, sentiment, external_kill, clock=None, should_stop=None):
    day = now.date().isoformat()
    session_time = now.strftime("%H:%M")
    if not calendar.is_trading_day(day, "CN") or not ("09:30" <= session_time < "11:30" or "13:00" <= session_time < "15:00"):
        return "outside_session"
    previous_day = calendar.prev_trading_day(day, market="CN")
    if state.get("mode") != "paper" or state.get("version") != VERSION:
        raise ValueError("unsupported account/version")
    # Exit monitoring precedes candidate/market-data gates; T+1 is absolute.
    for p in list(state["positions"]):
        try:
            q = api("/api/v1/quotes/realtime?" + urlencode({"symbols": p["symbol"]}))["data"][0]
            price, change = quote_ok(q, clock() if clock else now)
            if symbol(q["symbol"]) != p["symbol"]:
                raise ValueError("quote symbol mismatch")
            p["last_price"] = price
            p["last_price_at"] = q["trade_time"]
            if p["buy_date"] >= day:
                if p.get("t1_notice_day") != day:
                    event(state, now, "T1_LOCK", p["symbol"], reason="CN_T1_same_day_position_locked",
                          trade_id=p.get("trade_id"), buy_date=p["buy_date"], ai_job_id=p.get("ai_decision", {}).get("job_id"))
                    p["t1_notice_day"] = day
                continue
            if change <= -9.5:
                event(state, now, "SKIP_SELL", p["symbol"], reason="limit-down liquidity unverified")
                continue
            ret = price / p["buy_price"] - 1
            scfg = cfg["sell"]
            held = (now.date() - datetime.fromisoformat(p["buy_date"]).date()).days
            reason = ("take_profit" if ret >= scfg["take_profit"] else
                      "stop_loss" if ret <= scfg["stop_loss"] else
                      "vwap_stop" if price < p["buy_vwap"] * (1 - scfg["vwap_stop"]) else
                      "break_ma10" if scfg["break_ma10"] and price < p["buy_vwap10"] else
                      "time_stop" if held >= scfg["max_hold_days"] else None)
            if reason:
                sell(state, p, price, reason, now)
        except (KeyError, ValueError, TypeError, OSError) as exc:
            event(state, now, "DATA_ERROR", p["symbol"], reason=str(exc))
    realized = sum(p["pnl"] for p in state["closed"] if p["sell_date"] == day)
    if realized <= -state["initial_cash"] * cfg["decision_gate"]["kill"]["max_day_loss_pct"]:
        state["kill"] = True
    state["as_of"] = now.isoformat()
    if state["kill"] or external_kill:
        event(state, now, "BLOCK", reason="kill_switch")
        return "kill_switch"
    if not state.get("enabled", True):
        event(state, now, "BLOCK", reason="entry_paused; exits remain active")
        return "paused"
    bcfg = cfg["buy"]
    if callable(sentiment):
        sentiment = sentiment()
    if "backend_status" in sentiment:
        market_blocked = sentiment["backend_status"] not in ("高位延续", "高位震荡") or sentiment["risk_score"] >= 40
    else:
        score = number(sentiment["score"])
        threshold = bcfg["min_market_sentiment"]
        if sentiment.get("water", {}).get("days_declining", 0) >= 3 or sentiment.get("risk_appetite", {}).get("level") == "低":
            threshold = bcfg["min_market_sentiment_low_water"]
        market_blocked = sentiment.get("error") or score < threshold or (bcfg["forbid_dead_day"] and sentiment.get("dead_day")) or score <= -60
    event(state, now, "MARKET_GATE", evidence=sentiment,
          reason="%s / risk=%s" % (sentiment.get("backend_status", "sentiment"), sentiment.get("risk_score", sentiment.get("score"))))
    state["market"] = {**sentiment, "checked_at": now.isoformat()}
    if market_blocked:
        event(state, now, "BLOCK", reason="market_gate")
        return "market_gate"
    ladder = api("/api/v1/short-term/limit-up-ladder")["data"]
    overview = api("/api/v1/themes/overview")
    settings = state.get("settings", {})
    pool = candidates(ladder, overview, clock() if clock else now, previous_day, settings)
    state["last_scan_at"] = (clock() if clock else now).isoformat()
    state["themes"] = [{"id": t["theme"], "name": t["name"], "change_percent": t.get("change_percent"),
                        "rising_nodes": t.get("rising_nodes"), "falling_nodes": t.get("falling_nodes"),
                        "source": overview["meta"].get("source"), "snapshot_at": overview["meta"].get("fetched_at")}
                       for t in overview["data"]]
    previous_plans = {c["symbol"]: c.get("plan") for c in state.get("candidates", [])}
    state["candidates"] = pool
    for c in pool:
        if previous_plans.get(c["symbol"]):
            c["plan"] = previous_plans[c["symbol"]]
        c.update(status="waiting", checked_at=state["last_scan_at"])
    for c in pool:
        code = c["symbol"]
        if should_stop and should_stop():
            c.update(status="blocked", reason="pending_stop_command")
            continue
        key = day + ":" + code
        if key in state["seen"] or any(p["symbol"] == code for p in state["positions"]):
            c.update(status="held", reason="already_held_or_traded_today")
            continue
        if len(state["positions"]) >= bcfg["max_positions"]:
            c.update(status="blocked", reason="max_positions")
            continue
        try:
            q = api("/api/v1/quotes/realtime?" + urlencode({"symbols": code}))["data"][0]
            if symbol(q["symbol"]) != code:
                raise ValueError("quote symbol mismatch")
            checked_quote_at = clock() if clock else now
            quoted_price, quoted_change = quote_ok(q, checked_quote_at)
            c.update(price=quoted_price, change_percent=quoted_change, source=q["meta"]["source"], trade_time=q["trade_time"])
            minute = api("/api/v1/quotes/kline?" + urlencode({"symbol": code, "period": "5", "limit": 60}))["data"]
            daily = api("/api/v1/quotes/kline?" + urlencode({"symbol": code, "period": "day", "limit": 30}))["data"]
            checked_at = clock() if clock else now
            current_clock = checked_at.strftime("%H:%M")
            if checked_at.date() != now.date() or not ("09:30" <= current_clock < "11:30" or "13:00" <= current_clock < "15:00"):
                break
            anchors = entry_ok(q, minute, daily, cfg, checked_at, previous_day)
            price = number(q["price"])
            from follow_ai import ai_entry_gate
            try:
                ai_decision = ai_entry_gate(state, code, price, checked_at)
                event(state, checked_at, "AI_DECISION", code, decision=ai_decision)
            except ValueError as exc:
                event(state, checked_at, "AI_DECISION", code, decision={"status": "blocked", "reason": str(exc),
                      "job_id": state.get("ai_latest", {}).get("id"), "evidence_hash": state.get("ai_latest", {}).get("evidence_hash")})
                raise
            c.update(price=price, change_percent=q["change_percent"], source=q["meta"]["source"], trade_time=q["trade_time"])
            amount = min(bcfg["amount_per_trade"], state["cash"])
            shares = int(amount / price / 100) * 100
            if should_stop and should_stop():
                c.update(status="blocked", reason="pending_stop_command")
                continue
            if shares <= 0:
                c.update(status="blocked", reason="insufficient_cash")
                continue
            state["cash"] = round(state["cash"] - shares * price, 2)
            identity = {k: c[k] for k in ("symbol", "name", "route", "theme", "streak") if k in c}
            state["positions"].append({**identity, **anchors, "ai_decision": ai_decision, "shares": shares, "buy_price": price,
                                       "last_price": price, "buy_date": day,
                                       "bought_at": checked_at.isoformat(), "trade_id": key,
                                       "source": q["meta"]["source"], "trade_time": q["trade_time"], "last_price_at": q["trade_time"]})
            c.update(status="bought", reason="P8_P25_confirmed")
            state["seen"].append(key)
            event(state, now, "BUY", code, route=c["route"], price=price, shares=shares,
                  ai_decision=ai_decision,
                  fill_model="fresh_quote_reference", fee_model="CN_existing_zero_fee")
        except (KeyError, ValueError, TypeError, OSError) as exc:
            c.update(status="skipped", reason=str(exc))
            event(state, now, "SKIP", code, reason=str(exc))
    state["seen"] = [key for key in state["seen"] if key.startswith(day + ":")]
    return "completed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("EASY_STOCK_FOLLOW_DB", str(ROOT / "logs" / "auto-follow.db")))
    parser.add_argument("--watch", action="store_true", help="run every 60 seconds during CN sessions")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="rollback account changes; upstream caches may still write")
    parser.add_argument("--preflight", action="store_true", help="validate local runtime/config only; never requests market data")
    parser.add_argument("--kill", choices=("on", "off"))
    args = parser.parse_args()
    sys.path.insert(0, str(SERVICE))
    import daily_review as dr
    import trading_calendar as calendar
    dr.BASE = os.environ.get("EASY_STOCK_API_URL", dr.BASE).rstrip("/")
    try:
        db = connect(args.db)
        control = connect_control(args.db)
        from follow_ai import init_ai
        init_ai(control)
    except (sqlite3.Error, OSError) as exc:
        print(json.dumps({"status": "startup_error", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    try:
        if args.preflight:
            cfg=load_config()
            for value in (cfg['buy']['max_positions'],cfg['buy']['amount_per_trade'],cfg['buy']['max_day_chg']):
                if number(value)<=0:raise ValueError('invalid paper risk configuration')
            calendar.is_trading_day(datetime.now(BJ).date().isoformat(),'CN')
            print(json.dumps({'status':'preflight_ok','mode':'paper','config_version':cfg['version'],'network_used':False}),flush=True)
            return
        while True:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
                state = json.loads(row[0]) if row else initial()
                if args.status:
                    print(json.dumps(state, ensure_ascii=False))
                    db.rollback()
                    return
                now = datetime.now(BJ)
                receipts = apply_commands(control, state, now)
                from follow_ai import sync_ai
                try:
                    sync_ai(control, state, now)
                except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                    event(state, now, "AI_ERROR", reason=type(exc).__name__)
                state["last_heartbeat"] = now.isoformat()
                state["engine_revision"] = "paper-follow-ai-v4"
                cfg = load_config()
                def beat(phase):
                    control.execute("INSERT OR REPLACE INTO runtime VALUES(1,?,?)", (datetime.now(BJ).isoformat(), phase))
                def worker_api(path, timeout=25):
                    beat("scanning")
                    try:
                        return dr.api(path, timeout=timeout)
                    finally:
                        beat("scanning")
                beat("processing")
                state["risk_config"] = {"strategy_version": cfg["version"], "max_positions": cfg["buy"]["max_positions"],
                                        "amount_per_trade": cfg["buy"]["amount_per_trade"], "max_day_chg": cfg["buy"]["max_day_chg"],
                                        "take_profit": cfg["sell"]["take_profit"], "stop_loss": cfg["sell"]["stop_loss"],
                                        "daily_loss_limit": cfg["decision_gate"]["kill"]["max_day_loss_pct"]}
                if args.kill:
                    state["kill"] = args.kill == "on"
                    event(state, now, "MANUAL_KILL", armed=state["kill"])
                    result = "kill_updated"
                else:
                    kill_file = SERVICE / "logs" / "kill_switch.json"
                    try:
                        external_kill = json.loads(kill_file.read_text(encoding="utf-8"))["armed"] if kill_file.exists() else False
                        if not isinstance(external_kill, bool):
                            raise ValueError("invalid kill flag")
                    except (OSError, ValueError, KeyError):
                        external_kill = True
                    def market():
                        if os.environ.get("EASY_STOCK_FOLLOW_MARKET_SOURCE") == "backend":
                            # Response fetch completes before capturing the validation clock.
                            payload = worker_api("/api/v1/short-term/emotion-history")
                            return backend_market(lambda path: payload, datetime.now(BJ))
                        path = SERVICE / "logs" / ("sentiment_%s_premarket.json" % now.date().isoformat())
                        data = json.loads(path.read_text(encoding="utf-8"))
                        if data["date"] != now.date().isoformat():
                            raise ValueError("sentiment date mismatch")
                        return data["market"]
                    try:
                        result = cycle(state, cfg, worker_api, now, calendar, market, external_kill,
                                       clock=lambda: datetime.now(BJ),
                                       should_stop=lambda: bool(control.execute("SELECT 1 FROM commands WHERE status='pending' AND action IN ('pause','kill') LIMIT 1").fetchone()))
                    except (KeyError, ValueError, TypeError, OSError) as exc:
                        # Commit completed exits and their evidence even if entry data failed.
                        event(state, now, "CYCLE_ERROR", reason=str(exc))
                        result = "degraded"
                if os.environ.get("EASY_STOCK_FOLLOW_RESEARCH") == "1" and not args.kill:
                    from follow_research import refresh_research
                    try:
                        refresh_research(state, cfg, lambda path: worker_api(path, timeout=6), datetime.now(BJ), calendar,
                                         force=any(e.get("command") in ("scan", "settings") and e.get("command_id") in {r[0] for r in receipts}
                                                   for e in state["events"][-50:]),
                                         clock=lambda: datetime.now(BJ),
                                         should_stop=lambda: bool(control.execute("SELECT 1 FROM commands WHERE status='pending' AND action IN ('pause','kill') LIMIT 1").fetchone()))
                    except (KeyError, ValueError, TypeError, OSError) as exc:
                        state["research"] = {"checked_at": datetime.now(BJ).isoformat(), "errors": [str(exc)]}
                from follow_ai import schedule_workflow
                try:
                    schedule_workflow(control, state, datetime.now(BJ), calendar)
                    sync_ai(control, state, datetime.now(BJ))
                except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                    # AI transport cannot undo already completed exits or paper fills.
                    event(state, datetime.now(BJ), "AI_ERROR", reason=type(exc).__name__)
                state["cycle_status"] = result
                state["cycle_finished_at"] = datetime.now(BJ).isoformat()
                beat("waiting")
                if args.dry_run:
                    db.rollback()
                else:
                    db.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(state, ensure_ascii=False, allow_nan=False),))
                    db.commit()
                    for command_id, status, applied_at, result_text in receipts:
                        control.execute("UPDATE commands SET status=?,applied_at=?,result=? WHERE id=?",
                                        (status, applied_at, result_text, command_id))
                print(json.dumps({"status": result, "mode": "paper", "dry_run": args.dry_run}, ensure_ascii=False), flush=True)
                if result == "degraded" and not args.watch:
                    raise SystemExit(1)
            except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
                db.rollback()
                print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), flush=True)
                if not args.watch:
                    raise SystemExit(1)
            if not args.watch or args.kill:
                break
            wait_next_cycle(control)
    except KeyboardInterrupt:
        db.rollback()
    finally:
        db.close()
        control.close()


if __name__ == "__main__":
    main()
