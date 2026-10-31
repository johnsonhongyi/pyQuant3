"""Decision journal, forward-return settlement and attribution.

The journal answers the question the old system could not: for every candidate
it saw, what did it decide, why, and what happened next?  Outcomes are
counterfactual (entry at the observed price, no slippage) and are labelled as
such wherever they surface.
"""
import json
import sqlite3
from datetime import date
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions(
  trade_date TEXT NOT NULL, symbol TEXT NOT NULL, at TEXT NOT NULL,
  price REAL, score INTEGER, raw_score INTEGER, regime TEXT, threshold REAL,
  status TEXT, reason TEXT, blockers TEXT, layers TEXT, ai TEXT,
  outcome_1d REAL, outcome_3d REAL, outcome_5d REAL, settled_at TEXT,
  PRIMARY KEY(trade_date, symbol));
CREATE INDEX IF NOT EXISTS decisions_pending ON decisions(trade_date, settled_at);
CREATE TABLE IF NOT EXISTS trades(
  trade_id TEXT PRIMARY KEY, symbol TEXT, buy_date TEXT, sell_date TEXT,
  buy_price REAL, sell_price REAL, shares INTEGER, pnl REAL, reason TEXT,
  score INTEGER, regime TEXT, layers TEXT, mfe REAL, mae REAL, at TEXT);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, body TEXT);
"""

STATUS_PRIORITY = {"blocked": 0, "below_score": 1, "ai_veto": 2, "risk_blocked": 3, "ordered": 4, "filled": 5}


def connect(account_db):
    path = Path(account_db).with_name("loop.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=3, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    return db


def record(db, now, evaluation, status, reason, regime, threshold):
    trade_date = now.date().isoformat()
    row = db.execute("SELECT status FROM decisions WHERE trade_date=? AND symbol=?",
                     (trade_date, evaluation["symbol"])).fetchone()
    if row and STATUS_PRIORITY.get(row[0], 0) > STATUS_PRIORITY.get(status, 0):
        return
    db.execute("""INSERT INTO decisions(trade_date,symbol,at,price,score,raw_score,regime,threshold,status,reason,blockers,layers,ai)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(trade_date,symbol) DO UPDATE SET
                    at=excluded.at, price=excluded.price, score=excluded.score, raw_score=excluded.raw_score,
                    regime=excluded.regime, threshold=excluded.threshold, status=excluded.status,
                    reason=excluded.reason, blockers=excluded.blockers, layers=excluded.layers, ai=excluded.ai""",
               (trade_date, evaluation["symbol"], now.isoformat(), evaluation["metrics"].get("price"),
                evaluation.get("score"), evaluation.get("raw_score"), regime, threshold, status, reason or "",
                json.dumps(evaluation.get("blockers") or [], ensure_ascii=False),
                json.dumps(evaluation.get("layers") or {}, ensure_ascii=False),
                json.dumps(evaluation.get("ai") or {}, ensure_ascii=False)))


def record_trade(db, position, now):
    trade_id = position.get("trade_id") or "%s:%s" % (position.get("symbol"), position.get("buy_date"))
    db.execute("""INSERT OR REPLACE INTO trades(trade_id,symbol,buy_date,sell_date,buy_price,sell_price,shares,pnl,reason,score,regime,layers,mfe,mae,at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (trade_id, position.get("symbol"), position.get("buy_date"), position.get("sell_date"),
                position.get("buy_price"), position.get("sell_price"), position.get("shares"),
                position.get("pnl"), position.get("reason"), position.get("entry_score"),
                position.get("entry_regime"), json.dumps(position.get("entry_layers") or {}, ensure_ascii=False),
                position.get("mfe"), position.get("mae"), now.isoformat()))


def _forward_returns(bars, trade_date):
    completed = sorted((b for b in bars if str(b.get("time"))[:10] <= trade_date), key=lambda b: b["time"])
    if not completed or str(completed[-1]["time"])[:10] != trade_date:
        return None
    base = float(completed[-1]["close"])
    later = sorted((b for b in bars if str(b.get("time"))[:10] > trade_date), key=lambda b: b["time"])
    result = {}
    for horizon in (1, 3, 5):
        if len(later) >= horizon and base:
            result["outcome_%dd" % horizon] = later[horizon - 1]["close"] / base - 1
        else:
            result["outcome_%dd" % horizon] = None
    return result


def settle(db, api, now, calendar=None, max_symbols=40):
    """Fill forward returns for decisions old enough to have later bars."""
    rows = db.execute("""SELECT trade_date,symbol FROM decisions
                         WHERE settled_at IS NULL AND trade_date < ?
                         GROUP BY trade_date,symbol ORDER BY trade_date LIMIT ?""",
                      (now.date().isoformat(), max_symbols)).fetchall()
    if not rows:
        return 0
    cache, updated = {}, 0
    for trade_date, symbol in rows:
        if symbol not in cache:
            try:
                cache[symbol] = api("/api/v1/quotes/kline?symbol=%s&period=day&limit=80" % symbol)["data"]
            except (KeyError, ValueError, TypeError, OSError):
                cache[symbol] = []
        result = _forward_returns(cache[symbol], trade_date)
        if not result:
            continue
        # Keep the row open until the 5-day horizon exists so 3d/5d returns can
        # fill progressively instead of freezing at the 1-day value.
        settled_at = now.isoformat() if result.get("outcome_5d") is not None else None
        db.execute("""UPDATE decisions SET outcome_1d=?,outcome_3d=?,outcome_5d=?,settled_at=?
                      WHERE trade_date=? AND symbol=?""",
                   (result.get("outcome_1d"), result.get("outcome_3d"), result.get("outcome_5d"),
                    settled_at, trade_date, symbol))
        updated += 1
    if updated:
        db.execute("INSERT INTO runs(at,kind,body) VALUES(?,?,?)",
                   (now.isoformat(), "settle", json.dumps({"updated": updated}, ensure_ascii=False)))
    return updated


def _agg(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0, "win": None, "avg": None}
    return {"n": len(values), "win": sum(1 for v in values if v > 0) / len(values),
            "avg": sum(values) / len(values)}


def summary(db, now, days=30):
    since = (now.date().toordinal() - days)
    rows = db.execute("""SELECT trade_date,symbol,score,regime,status,reason,blockers,outcome_1d,outcome_3d,outcome_5d
                         FROM decisions""").fetchall()
    decisions = []
    for row in rows:
        try:
            ordinal = date.fromisoformat(row[0]).toordinal()
        except ValueError:
            continue
        if ordinal >= since:
            decisions.append(row)
    blockers, buckets, regimes = {}, {}, {}
    for trade_date, symbol, score, regime, status, reason, raw_blockers, o1, o3, o5 in decisions:
        if status == "blocked":
            key = (json.loads(raw_blockers or "[]") or [reason or "unknown"])[0]
            blockers.setdefault(key, []).append(o3)
        bucket = "<60" if (score or 0) < 60 else "60-69" if score < 70 else "70-79" if score < 80 else "80+"
        buckets.setdefault(bucket, []).append(o3)
        regimes.setdefault(regime or "unknown", []).append(o3)
    trades = db.execute("""SELECT pnl,reason,mfe,mae FROM trades""").fetchall()
    pnls = [r[0] for r in trades if r[0] is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    trade_stats = {
        "n": len(pnls), "wins": len(wins),
        "win_rate": (len(wins) / len(pnls)) if pnls else None,
        "avg_pnl": (sum(pnls) / len(pnls)) if pnls else None,
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses and sum(losses) else None,
        "avg_mfe": _agg([r[2] for r in trades])["avg"],
        "avg_mae": _agg([r[3] for r in trades])["avg"],
        "exits": {},
    }
    for _, reason, _, _ in trades:
        trade_stats["exits"][reason or "unknown"] = trade_stats["exits"].get(reason or "unknown", 0) + 1
    settled = [row for row in decisions if row[8] is not None]
    return {
        "as_of": now.isoformat(),
        "window_days": days,
        "samples": len(decisions),
        "settled": len(settled),
        "conversion": {
            "decisions": len(decisions),
            "filled": sum(1 for row in decisions if row[4] == "filled"),
            "rate": (sum(1 for row in decisions if row[4] == "filled") / len(decisions)) if decisions else None,
        },
        "blockers": sorted(({"reason": k, **_agg(v)} for k, v in blockers.items()),
                           key=lambda item: -item["n"])[:8],
        "buckets": [{"bucket": k, **_agg(v)} for k, v in sorted(buckets.items())],
        "regimes": sorted(({"regime": k, **_agg(v)} for k, v in regimes.items()),
                          key=lambda item: -item["n"])[:5],
        "trades": trade_stats,
        "note": "counterfactual: entry at observed decision price, no slippage or fees",
    }
