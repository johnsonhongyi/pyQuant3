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

import attribution
import loop_state
import optimizer
import signal_engine
import strong_scan


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
    if len(code) != 6 or not code.isdigit() or not code.startswith(("00", "60", "688", "300")):
        raise ValueError("unsupported board")
    return code + (".SH" if code.startswith(("60", "688")) else ".SZ")


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
    code_raw = str(q.get("symbol", "")).upper().replace(".SH", "").replace(".SZ", "")
    is_20cm = code_raw.startswith(("688", "300"))
    max_day_chg = cfg["buy"]["max_day_chg"] * (2.0 if is_20cm else 1.0)
    if not 0 < change <= max_day_chg:
        raise ValueError("P4 change gate")
    # A sealed board is never assumed fillable. 20% limit for 688/300; 10% for main-board.
    limit_ratio = 1.20 if is_20cm else 1.10
    if price >= round(number(q["previous_close"]) * limit_ratio, 2) - 0.01:
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
    vwap_max_bias = 1.045 if is_20cm else 1.025
    if not intraday * 1.005 <= price <= intraday * vwap_max_bias or intraday < v3:
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
    for sym_item in settings.get("manual_symbols", []):
        try:
            m_code = symbol(sym_item)
            result[m_code] = {"symbol": m_code, "name": m_code, "route": "manual",
                             "theme": "手动跟单", "streak": 99}
        except ValueError:
            continue
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
    overview_ok = False
    try:
        fresh(overview.get("meta", {}), now, 1800)
        overview_ok = True
    except (KeyError, ValueError, TypeError):
        overview_ok = False
    if overview_ok and settings.get("theme_trend", True):
        # Dynamic hot themes, deterministic ranking; no LLM-generated order instruction.
        themes = sorted(overview.get("data", []), key=lambda t: number(t.get("change_percent", 0)), reverse=True)
        if settings.get("theme_ids"):
            themes = [t for t in themes if t["theme"] in settings["theme_ids"]]
        for theme in themes[:3]:
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
    # The state row is rewritten every cycle; cap the WAL instead of letting a
    # checkpoint that never truncates grow it without limit.
    db.execute("PRAGMA wal_autocheckpoint=512")
    db.execute("PRAGMA journal_size_limit=%d" % (64 * 1024 * 1024))
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
            "loop": {}, "strong_scan": {}, "attribution": {}, "optimizer": {}, "regime": {},
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
                state["ai_settings"] = {**DEFAULT_AI, **state.get("ai_settings", {}), **data}
                state.pop("ai_latest", None)
            elif action == "ai_ask":
                from follow_ai import enqueue
                data = json.loads(payload)
                if set(data) != {"question"} or not isinstance(data["question"], str) or not 1 <= len(data["question"].strip()) <= 4000:
                    raise ValueError("invalid AI question")
                job_id = enqueue(db, state, now, question=data["question"].strip(), force=True)
                if not job_id:
                    raise ValueError("AI task not queued: " + str(state.get("auto_research_status") or "unknown"))
                result = "ai_job=" + job_id
            elif action == "resume_research":
                # The console cleared the day's automatic-research usage; drop the
                # worker's own request throttle so planning resumes on this cycle
                # instead of waiting out the configured interval.
                for key in ("ai_last_requested_at", "ai_phase_requested", "ai_review_day"):
                    state.pop(key, None)
                result = "research_resumed"
            elif action == "settings":
                data = json.loads(payload)
                allowed = {"limit_up", "theme_trend", "theme_ids", "manual_symbols"}
                if not set(data).issubset(allowed) or not all(isinstance(data.get(k, True), bool) for k in ("limit_up", "theme_trend")):
                    raise ValueError("invalid settings")
                ids = data.get("theme_ids", [])
                if not isinstance(ids, list) or len(ids) > 10 or any(not isinstance(v, str) or not v or len(v) > 80 for v in ids):
                    raise ValueError("invalid theme IDs")
                manual = data.get("manual_symbols", [])
                if not isinstance(manual, list) or len(manual) > 30 or any(not isinstance(v, str) for v in manual):
                    raise ValueError("invalid manual symbols")
                state["settings"] = {**state.get("settings", {}), **data}
            elif action == "manual_symbols":
                data = json.loads(payload)
                if not isinstance(data, list) or any(not isinstance(v, str) for v in data):
                    raise ValueError("invalid manual symbols")
                valid_syms = [symbol(s) for s in data]
                state.setdefault("settings", {})["manual_symbols"] = valid_syms
                result = "manual_symbols=" + ",".join(valid_syms)
            elif action == "add_symbol":
                data = json.loads(payload)
                raw = data.get("symbol", data) if isinstance(data, dict) else str(data)
                sym = symbol(raw)
                manual = state.setdefault("settings", {}).setdefault("manual_symbols", [])
                if sym not in manual:
                    manual.append(sym)
                result = "added=" + sym
            elif action == "remove_symbol":
                data = json.loads(payload)
                raw = data.get("symbol", data) if isinstance(data, dict) else str(data)
                sym = symbol(raw)
                manual = state.setdefault("settings", {}).setdefault("manual_symbols", [])
                if sym in manual:
                    manual.remove(sym)
                result = "removed=" + sym
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


def wait_next_cycle(db, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if db.execute("SELECT 1 FROM commands WHERE status='pending' LIMIT 1").fetchone():
            return
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def load_config():
    snapshot = os.environ.get("EASY_STOCK_FOLLOW_CONFIG")
    if snapshot:
        cfg = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    else:
        try:
            import yaml
            cfg = yaml.safe_load((SERVICE / "strategy.yaml").read_text(encoding="utf-8"))
        except ImportError:
            import simple_config
            cfg = simple_config.load(SERVICE / "strategy.yaml")
    try:
        account_db = os.environ.get("EASY_STOCK_FOLLOW_DB", str(ROOT / "logs" / "auto-follow.db"))
        params = optimizer.load_params(account_db)
        if params:
            cfg = optimizer.apply_overrides(cfg, params)
            cfg["runtime_params"] = {"version": params.get("version"), "overrides": params.get("overrides") or {}}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return cfg


def backend_market(api, now):
    data = api("/api/v1/short-term/emotion-history")["data"]
    intraday = data["intraday"]
    if data.get("intraday_error"):
        raise ValueError("backend intraday emotion unavailable")
    meta = {"source": "go.marketemotion.intraday", "stale": intraday["stale"],
            "fetched_at": intraday["updated_at"], "trade_date": intraday["trade_date"]}
    try:
        fresh(meta, now, 1800)
    except ValueError:
        if meta.get("trade_date") != now.date().isoformat():
            raise
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
    pnl = round((price - p["buy_price"]) * p["shares"], 2) + p.get("realized_partial", 0)
    state["cash"] = round(state["cash"] + price * p["shares"], 2)
    state["closed"].append({**p, "sell_date": now.date().isoformat(), "sell_price": price,
                            "sold_at": now.isoformat(), "pnl": pnl, "reason": reason})
    state["positions"].remove(p)
    event(state, now, "SELL", p["symbol"], price=price, pnl=pnl, reason=reason)


def sell_partial(state, p, price, shares, reason, now):
    pnl = round((price - p["buy_price"]) * shares, 2)
    state["cash"] = round(state["cash"] + price * shares, 2)
    p["shares"] -= shares
    p["realized_partial"] = round(p.get("realized_partial", 0) + pnl, 2)
    p["partial_done"] = True
    event(state, now, "PARTIAL_SELL", p["symbol"], price=price, shares=shares, pnl=pnl,
          reason=reason, remaining=p["shares"])


def cycle(state, cfg, api, now, calendar, sentiment, external_kill, clock=None, should_stop=None, journal=None):
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
            quotes = api("/api/v1/quotes/realtime?" + urlencode({"symbols": p["symbol"]})).get("data") or []
            if not quotes:
                raise ValueError("quote unavailable")
            q = quotes[0]
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
            p["peak"] = max(p.get("peak", p["buy_price"]), price)
            p["mfe"] = max(p.get("mfe", 0), ret)
            p["mae"] = min(p.get("mae", 0), ret)
            held = (now.date() - datetime.fromisoformat(p["buy_date"]).date()).days
            partial_at = scfg.get("partial_take_profit")
            if partial_at and not p.get("partial_done") and ret >= partial_at:
                ratio = scfg.get("partial_ratio", 0.5)
                lots = int(p["shares"] * ratio / 100) * 100
                if 0 < lots < p["shares"]:
                    sell_partial(state, p, price, lots, "partial_take_profit", now)
                    continue
            trailing_arm = scfg.get("trailing_arm")
            trailing_giveback = scfg.get("trailing_giveback")
            trailing = bool(trailing_arm and trailing_giveback and
                            p["peak"] >= p["buy_price"] * (1 + trailing_arm) and
                            price <= p["peak"] * (1 - trailing_giveback))
            reason = ("stop_loss" if ret <= scfg["stop_loss"] else
                      "trailing_stop" if trailing else
                      "take_profit" if ret >= scfg["take_profit"] else
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
    regime = loop_state.classify(sentiment, cfg)
    state["regime"] = regime
    run = loop_state.new_run(now, regime)
    market_blocked = False
    if regime["code"] == "legacy":
        if "backend_status" in sentiment:
            market_blocked = sentiment["backend_status"] not in ("高位延续", "高位震荡") or sentiment["risk_score"] >= 40
        else:
            score = number(sentiment["score"])
            threshold = bcfg["min_market_sentiment"]
            if sentiment.get("water", {}).get("days_declining", 0) >= 3 or sentiment.get("risk_appetite", {}).get("level") == "低":
                threshold = bcfg["min_market_sentiment_low_water"]
            market_blocked = sentiment.get("error") or score < threshold or (bcfg["forbid_dead_day"] and sentiment.get("dead_day")) or score <= -60
    event(state, now, "MARKET_GATE", evidence=sentiment, regime=regime,
          reason="%s / risk=%s" % (sentiment.get("backend_status", "sentiment"), sentiment.get("risk_score", sentiment.get("score"))))
    state["market"] = {**sentiment, "checked_at": now.isoformat()}
    if market_blocked:
        event(state, now, "BLOCK", reason="market_gate")
        loop_state.finish(state, run, now, "market_gate")
        return "market_gate"
    if regime["code"] == "defense":
        event(state, now, "BLOCK", reason="regime_defense", regime=regime)
        loop_state.finish(state, run, now, "defense")
        return "defense"
    ladder = api("/api/v1/short-term/limit-up-ladder")["data"]
    overview = api("/api/v1/themes/overview")
    settings = state.get("settings", {})
    checked_now = clock() if clock else now
    pool = candidates(ladder, overview, checked_now, previous_day, settings)
    if regime["code"] != "legacy":
        try:
            strong_scan.refresh(state, api, checked_now, cfg, ladder, overview)
            strong_scan.merge(pool, state, cfg)
        except (KeyError, ValueError, TypeError, OSError) as exc:
            event(state, now, "STRONG_SCAN_ERROR", reason=str(exc)[:200])
    pool.sort(key=lambda c: (-(c.get("scan_score") or 0), -(c.get("streak") or 0), c["symbol"]))
    run["candidates"] = len(pool)
    state["last_scan_at"] = checked_now.isoformat()
    state["themes"] = [{"id": t["theme"], "name": t["name"], "change_percent": t.get("change_percent"),
                        "rising_nodes": t.get("rising_nodes"), "falling_nodes": t.get("falling_nodes"),
                        "source": overview.get("meta", {}).get("source"), "snapshot_at": overview.get("meta", {}).get("fetched_at")}
                       for t in overview.get("data", [])]
    previous_plans = {c["symbol"]: c.get("plan") for c in state.get("candidates", [])}
    state["candidates"] = pool
    for c in pool:
        if previous_plans.get(c["symbol"]):
            c["plan"] = previous_plans[c["symbol"]]
        c.update(status="waiting", checked_at=state["last_scan_at"])
    loop_cfg = (cfg.get("execution") or {}).get("signal") or {}
    max_evaluations = int(loop_cfg.get("max_evaluations", 14))
    pool_changes = [c["change_percent"] for c in pool if isinstance(c.get("change_percent"), (int, float))]
    pool_changes += [row["change_percent"] for row in ((state.get("strong_scan") or {}).get("rows") or [])
                     if isinstance(row.get("change_percent"), (int, float))]
    for c in pool:
        code = c["symbol"]
        if should_stop and should_stop():
            c.update(status="blocked", reason="pending_stop_command")
            continue
        key = day + ":" + code
        if key in state["seen"] or any(p["symbol"] == code for p in state["positions"]):
            c.update(status="held", reason="already_held_or_traded_today")
            continue
        max_positions = min(bcfg["max_positions"], regime["max_positions"] or bcfg["max_positions"])
        if len(state["positions"]) >= max_positions:
            c.update(status="blocked", reason="max_positions")
            continue
        if run["counts"]["scored"] >= max_evaluations:
            c.update(status="waiting", reason="evaluation_budget")
            continue
        try:
            quotes = api("/api/v1/quotes/realtime?" + urlencode({"symbols": code})).get("data") or []
            if not quotes:
                raise ValueError("quote unavailable")
            q = quotes[0]
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
            price = number(q["price"])
            if regime["code"] == "legacy":
                anchors = entry_ok(q, minute, daily, cfg, checked_at, previous_day)
                from follow_ai import ai_entry_gate
                try:
                    ai_decision = ai_entry_gate(state, code, price, checked_at)
                    event(state, checked_at, "AI_DECISION", code, decision=ai_decision)
                except ValueError as exc:
                    event(state, checked_at, "AI_DECISION", code, decision={"status": "blocked", "reason": str(exc),
                          "job_id": state.get("ai_latest", {}).get("id"), "evidence_hash": state.get("ai_latest", {}).get("evidence_hash")})
                    raise
                evaluation = None
                threshold = 0
            else:
                from follow_ai import ai_overlay
                ai_decision = ai_overlay(state, code, price, checked_at, cfg)
                event(state, checked_at, "AI_DECISION", code, decision=ai_decision)
                theme = next((t for t in overview.get("data", []) if t.get("theme") == c.get("theme")), None)
                theme_info = None
                if theme:
                    leaders = theme.get("leader_stocks") or []
                    rank = None
                    for index, leader in enumerate(leaders, 1):
                        try:
                            if symbol(leader.get("symbol")) == code:
                                rank = index
                                break
                        except (KeyError, ValueError, TypeError):
                            continue
                    changes = sorted((number(t.get("change_percent") or 0) for t in overview.get("data", [])), reverse=True)
                    theme_change = number(theme.get("change_percent") or 0)
                    theme_info = {"change_percent": theme_change,
                                  "rising_nodes": theme.get("rising_nodes"),
                                  "falling_nodes": theme.get("falling_nodes"),
                                  "leader_rank": rank,
                                  "rank": changes.index(theme_change) + 1 if theme_change in changes else None}
                evaluation = signal_engine.evaluate(c, q, minute, daily, {
                    "now": checked_at, "today": day, "previous_day": previous_day, "cfg": cfg,
                    "regime": regime, "theme": theme_info, "ai": ai_decision,
                    "pool_change_median": sorted(pool_changes)[len(pool_changes) // 2] if pool_changes else None,
                })
                c.update(score=evaluation["score"], raw_score=evaluation["raw_score"],
                         layers=evaluation["layers"], blockers=evaluation["blockers"],
                         notes=evaluation["notes"], ai=ai_decision)
                loop_state.bump(run, "scored")
                threshold = regime["min_score"]
                if evaluation["blockers"]:
                    reason, status = evaluation["blockers"][0], "blocked"
                    loop_state.blocker(run, reason, code)
                    c.update(status="skipped", reason=reason)
                    event(state, checked_at, "SKIP", code, reason=reason, score=evaluation["score"],
                          threshold=threshold, blockers=evaluation["blockers"])
                    if journal is not None:
                        attribution.record(journal, checked_at, evaluation, status, reason, regime["code"], threshold)
                    continue
                loop_state.bump(run, "structure_pass")
                if evaluation["score"] < threshold:
                    reason, status = "score below threshold", "below_score"
                    loop_state.blocker(run, reason, code)
                    c.update(status="skipped", reason=reason)
                    event(state, checked_at, "SKIP", code, reason=reason, score=evaluation["score"],
                          threshold=threshold, blockers=[])
                    if journal is not None:
                        attribution.record(journal, checked_at, evaluation, status, reason, regime["code"], threshold)
                    continue
                loop_state.bump(run, "score_pass")
                if ai_decision.get("veto"):
                    reason, status = "AI veto", "ai_veto"
                    loop_state.blocker(run, reason, code)
                    c.update(status="skipped", reason=reason)
                    event(state, checked_at, "SKIP", code, reason=reason, score=evaluation["score"],
                          threshold=threshold, blockers=[])
                    if journal is not None:
                        attribution.record(journal, checked_at, evaluation, status, reason, regime["code"], threshold)
                    continue
                loop_state.bump(run, "ai_pass")
                anchors = {"buy_vwap": evaluation["metrics"].get("vwap1"),
                           "buy_vwap10": evaluation["metrics"].get("vwap10")}
            c.update(price=price, change_percent=q["change_percent"], source=q["meta"]["source"], trade_time=q["trade_time"])
            exposure = regime["exposure"] if regime["code"] != "legacy" else 1.0
            amount = min(bcfg["amount_per_trade"] * exposure, state["cash"])
            shares = int(amount / price / 100) * 100
            if should_stop and should_stop():
                c.update(status="blocked", reason="pending_stop_command")
                continue
            if shares <= 0:
                c.update(status="blocked", reason="insufficient_cash")
                if evaluation is not None and journal is not None:
                    attribution.record(journal, checked_at, evaluation, "risk_blocked", "insufficient_cash", regime["code"], threshold)
                continue
            if evaluation is not None:
                loop_state.bump(run, "risk_pass")
                loop_state.bump(run, "orders")
            state["cash"] = round(state["cash"] - shares * price, 2)
            identity = {k: c[k] for k in ("symbol", "name", "route", "theme", "streak") if k in c}
            position = {**identity, **anchors, "ai_decision": ai_decision, "shares": shares, "buy_price": price,
                        "last_price": price, "buy_date": day, "bought_at": checked_at.isoformat(),
                        "trade_id": key, "source": q["meta"]["source"], "trade_time": q["trade_time"],
                        "last_price_at": q["trade_time"], "mfe": 0, "mae": 0, "peak": price}
            if evaluation is not None:
                position.update(entry_score=evaluation["score"], entry_regime=regime["code"],
                                entry_layers=evaluation["layers"])
            state["positions"].append(position)
            c.update(status="bought", reason="score_admitted" if evaluation is not None else "P8_P25_confirmed")
            state["seen"].append(key)
            if evaluation is not None:
                loop_state.bump(run, "fills")
                if journal is not None:
                    attribution.record(journal, checked_at, evaluation, "filled", "score_admitted", regime["code"], threshold)
            event(state, now, "BUY", code, route=c["route"], price=price, shares=shares,
                  score=evaluation["score"] if evaluation is not None else None,
                  regime=regime["code"], exposure=exposure, ai_decision=ai_decision,
                  fill_model="fresh_quote_reference", fee_model="CN_existing_zero_fee")
        except (KeyError, ValueError, TypeError, OSError) as exc:
            c.update(status="skipped", reason=str(exc))
            event(state, now, "SKIP", code, reason=str(exc))
            if regime["code"] != "legacy":
                loop_state.blocker(run, str(exc)[:80], code)
    state["seen"] = [key for key in state["seen"] if key.startswith(day + ":")]
    loop_state.finish(state, run, now, "completed")
    return "completed"


def after_cycle(journal, state, cfg, api, now, calendar, account_db, result):
    """Settlement, attribution and optimization run outside the trading loop."""
    session_done = now.strftime("%H:%M") >= "15:05"
    trading_day = calendar.is_trading_day(now.date().isoformat(), "CN")
    if session_done or not trading_day:
        try:
            attribution.settle(journal, api, now)
            summary = attribution.summary(journal, now)
            state["attribution"] = summary
            optimizer.run(journal, state, cfg, now, account_db, summary)
        except (sqlite3.Error, KeyError, ValueError, TypeError, OSError) as exc:
            event(state, now, "LOOP_ERROR", reason="settle/optimize:%s" % str(exc)[:160])
    if not trading_day or not ("09:15" <= now.strftime("%H:%M") <= "15:30"):
        if not (state.get("strong_scan") or {}).get("rows"):
            try:
                ladder = api("/api/v1/short-term/limit-up-ladder")["data"]
                overview = api("/api/v1/themes/overview")
                strong_scan.refresh(state, api, now, cfg, ladder, overview)
            except (KeyError, ValueError, TypeError, OSError) as exc:
                state["strong_scan"] = {"checked_at": now.isoformat(), "rows": [], "errors": [str(exc)[:160]]}
    regime = state.get("regime") or loop_state.classify(state.get("market") or {}, cfg)
    state["regime"] = regime
    if result in ("outside_session", "kill_switch", "paused", "degraded"):
        run = loop_state.new_run(now, regime, len(state.get("candidates") or []))
        loop_state.finish(state, run, now, result)
    state["risk_config"] = {**(state.get("risk_config") or {}),
                            "regime": regime.get("code"), "exposure": regime.get("exposure"),
                            "entry_threshold": regime.get("min_score"),
                            "regime_max_positions": regime.get("max_positions")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("EASY_STOCK_FOLLOW_DB", str(ROOT / "logs" / "auto-follow.db")))
    parser.add_argument("--watch", action="store_true", help="run every 180 seconds during CN sessions")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="rollback account changes; upstream caches may still write")
    parser.add_argument("--preflight", action="store_true", help="validate local runtime/config only; never requests market data")
    parser.add_argument("--kill", choices=("on", "off"))
    parser.add_argument("--add-symbol", help="manually add a symbol (e.g. 688787 or 688787.SH)")
    parser.add_argument("--remove-symbol", help="manually remove a symbol")
    parser.add_argument("--interval", type=int, default=int(os.environ.get("EASY_STOCK_FOLLOW_INTERVAL", "180")),
                        help="seconds between scan cycles (default 180)")
    args = parser.parse_args()
    sys.path.insert(0, str(SERVICE))
    import daily_review as dr
    import housekeeping
    import trading_calendar as calendar
    dr.BASE = os.environ.get("EASY_STOCK_API_URL", dr.BASE).rstrip("/")
    try:
        db = connect(args.db)
        control = connect_control(args.db)
        journal = attribution.connect(args.db)
        from follow_ai import init_ai
        init_ai(control)
    except (sqlite3.Error, OSError) as exc:
        print(json.dumps({"status": "startup_error", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    try:
        if args.add_symbol:
            sym = symbol(args.add_symbol)
            import uuid
            cid = uuid.uuid4().hex
            control.execute("INSERT INTO commands(id,action,payload,created_at,status) VALUES(?,?,?,?,'pending')",
                            (cid, "add_symbol", json.dumps(sym), datetime.now(BJ).isoformat()))
            print(json.dumps({"status": "command_queued", "action": "add_symbol", "symbol": sym, "command_id": cid}))
            return
        if args.remove_symbol:
            sym = symbol(args.remove_symbol)
            import uuid
            cid = uuid.uuid4().hex
            control.execute("INSERT INTO commands(id,action,payload,created_at,status) VALUES(?,?,?,?,'pending')",
                            (cid, "remove_symbol", json.dumps(sym), datetime.now(BJ).isoformat()))
            print(json.dumps({"status": "command_queued", "action": "remove_symbol", "symbol": sym, "command_id": cid}))
            return
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
                state["engine_revision"] = "paper-follow-loop-v5"
                cfg = load_config()
                def beat(phase):
                    control.execute("INSERT OR REPLACE INTO runtime VALUES(1,?,?)", (datetime.now(BJ).isoformat(), phase))
                def worker_api(path, timeout=25):
                    if "/kline/batch" in path or "/hot-ranks" in path:
                        timeout = max(timeout, 45)
                    beat("scanning")
                    try:
                        return dr.api(path, timeout=timeout)
                    finally:
                        beat("scanning")
                beat("processing")
                state["risk_config"] = {"strategy_version": cfg.get("runtime_version") or cfg["version"], "max_positions": cfg["buy"]["max_positions"],
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
                                       should_stop=lambda: bool(control.execute("SELECT 1 FROM commands WHERE status='pending' AND action IN ('pause','kill') LIMIT 1").fetchone()),
                                       journal=journal)
                    except (KeyError, ValueError, TypeError, OSError) as exc:
                        # Commit completed exits and their evidence even if entry data failed.
                        event(state, now, "CYCLE_ERROR", reason=str(exc))
                        result = "degraded"
                    state["cycle_status"] = result
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
                    event(state, datetime.now(BJ), "AI_ERROR", reason=str(exc)[:200] or type(exc).__name__)
                try:
                    after_cycle(journal, state, cfg, worker_api, datetime.now(BJ), calendar, args.db, result)
                except (sqlite3.Error, KeyError, ValueError, TypeError, OSError) as exc:
                    event(state, datetime.now(BJ), "LOOP_ERROR", reason=str(exc)[:200])
                state["cycle_status"] = result
                state["cycle_finished_at"] = datetime.now(BJ).isoformat()
                beat("waiting")
                if args.dry_run:
                    db.rollback()
                else:
                    housekeeping.slim_state(state)
                    housekeeping_day = datetime.now(BJ).date().isoformat()
                    if state.get("housekeeping_day") != housekeeping_day:
                        state["housekeeping_day"] = housekeeping_day
                        state["housekeeping_last"] = housekeeping.prune(control, journal, datetime.now(BJ))
                    db.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(state, ensure_ascii=False, allow_nan=False),))
                    db.commit()
                    housekeeping.checkpoint(db, args.db)
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
            wait_next_cycle(control, seconds=args.interval)
    except KeyboardInterrupt:
        db.rollback()
    finally:
        db.close()
        control.close()
        journal.close()


if __name__ == "__main__":
    main()
