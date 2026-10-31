"""Strong-stock scan that feeds the paper follower's candidate pool.

Sources are deliberately cheap and already verified by the Go backend: hot
ranks, the limit-up ladder, theme leaders and manual symbols.  One batched
quote request and one batched daily-kline request per refresh keep the network
budget bounded; minute bars are only fetched later for the finalists.
"""
from urllib.parse import urlencode

DEFAULT = {"enabled": True, "interval_seconds": 600, "max_symbols": 24, "merge_limit": 8, "min_score": 45}


def _num(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result else default


def _settings(cfg):
    execution = (cfg or {}).get("execution") or {}
    return {**DEFAULT, **(execution.get("strong_scan") or {})}


def _symbol(value):
    import auto_follow as af
    try:
        return af.symbol(value)
    except (ValueError, TypeError):
        return None


def universe(state, ladder, overview):
    """Collect candidate identities without any market request."""
    found = {}

    def add(raw, name=None, source=None, **extra):
        code = _symbol(raw)
        if not code or "ST" in str(name or "").upper():
            return
        item = found.setdefault(code, {"symbol": code, "name": name or code, "sources": []})
        if name and item["name"] == code:
            item["name"] = name
        if source and source not in item["sources"]:
            item["sources"].append(source)
        for key, value in extra.items():
            if value is not None:
                item[key] = value

    for stock in ((state.get("settings") or {}).get("manual_symbols") or []):
        add(stock, source="manual")
    for level in ((ladder or {}).get("current", {}).get("levels") or []):
        for stock in level.get("stocks") or []:
            add(stock.get("symbol"), stock.get("name"), "ladder", streak=stock.get("streak"),
                theme=stock.get("primary_theme"))
    themes = sorted((overview or {}).get("data") or [], key=lambda t: -_num(t.get("change_percent")))
    for rank, theme in enumerate(themes[:3], 1):
        for leader_rank, stock in enumerate((theme.get("leader_stocks") or [])[:5], 1):
            add(stock.get("symbol"), stock.get("name"), "theme", theme=theme.get("theme"),
                theme_change=_num(theme.get("change_percent")), theme_rank=rank,
                leader_rank=leader_rank, rising_nodes=theme.get("rising_nodes"),
                falling_nodes=theme.get("falling_nodes"))
    return found


def _prescore(item, quote, hot_rank):
    change = _num(quote.get("change_percent"), -99)
    score = 0.0
    if 0 <= change <= 7:
        score += 30
    elif 7 < change <= 9:
        score += 18
    elif -3 <= change < 0:
        score += 14
    else:
        score += 0
    if hot_rank:
        score += max(0, 25 - min(hot_rank, 25))
    if item.get("theme"):
        score += 10 if _num(item.get("theme_change")) > 0 else 3
    if item.get("leader_rank") and item["leader_rank"] <= 5:
        score += 8
    if item.get("streak"):
        score += min(10, _num(item.get("streak")) * 2)
    return score


def _daily_strength(daily, today):
    bars = sorted((b for b in daily if str(b.get("time"))[:10] < today), key=lambda b: b["time"])
    if len(bars) < 20:
        return None
    closes = [_num(b.get("close")) for b in bars]
    amounts = [_num(b.get("amount")) for b in bars[-20:]]
    high20 = max(_num(b.get("high")) for b in bars[-20:])
    close = closes[-1]
    return {
        "ret5": close / closes[-6] - 1 if len(closes) >= 6 else 0,
        "ret20": close / closes[-21] - 1 if len(closes) >= 21 else 0,
        "proximity": close / high20 if high20 else 0,
        "amount20": sum(amounts) / len(amounts) if amounts else 0,
        "close": close,
        "trade_date": str(bars[-1]["time"])[:10],
    }


def _score(item, quote, daily):
    change = _num(quote.get("change_percent"), -99)
    score = 0.0
    layers = {}
    strength = 0.0
    if daily:
        if daily["ret5"] >= 0.10:
            strength += 12
        elif daily["ret5"] >= 0.05:
            strength += 9
        elif daily["ret5"] >= 0.02:
            strength += 6
        elif daily["ret5"] >= 0:
            strength += 3
        if daily["proximity"] >= 0.98:
            strength += 8
        elif daily["proximity"] >= 0.94:
            strength += 5
        elif daily["proximity"] >= 0.90:
            strength += 2
        if daily["amount20"] >= 300_000_000:
            strength += 10
        elif daily["amount20"] >= 150_000_000:
            strength += 7
        elif daily["amount20"] >= 80_000_000:
            strength += 4
        else:
            strength += 1
    layers["strength"] = round(strength, 1)
    score += strength
    momentum = 0.0
    if 0 <= change <= 7:
        momentum += 20
    elif 7 < change <= 9:
        momentum += 12
    elif -2 <= change < 0:
        momentum += 8
    elif -3 <= change < -2:
        momentum += 3
    layers["momentum"] = momentum
    score += momentum
    theme = 0.0
    if item.get("theme"):
        theme += 8 if _num(item.get("theme_change")) > 0 else 2
        if item.get("leader_rank") and item["leader_rank"] <= 5:
            theme += 6
    layers["theme"] = theme
    score += theme
    flow = min(10.0, _num(item.get("hot_rank_score")) / 20.0)
    layers["heat"] = round(flow, 1)
    score += flow
    return round(min(100.0, score), 1), layers


def refresh(state, api, now, cfg, ladder=None, overview=None, force=False):
    settings = _settings(cfg)
    if not settings.get("enabled", True):
        state["strong_scan"] = {"checked_at": now.isoformat(), "rows": [], "errors": ["disabled"], "trade_date": now.date().isoformat()}
        return state["strong_scan"]
    prior = state.get("strong_scan") or {}
    try:
        import auto_follow as af
        age = (now - af.stamp(prior["checked_at"])).total_seconds()
    except (KeyError, ValueError, TypeError):
        age = 10 ** 9
    if not force and prior.get("trade_date") == now.date().isoformat() and 0 <= age < settings["interval_seconds"]:
        return prior
    errors = []
    hot = {}
    try:
        payload = api("/api/v1/stocks/hot-ranks?limit=60")
        rows = ((payload.get("data") or {}).get("stocks") or [])
        for index, stock in enumerate(rows, 1):
            code = _symbol(stock.get("symbol") or stock.get("code"))
            if code:
                hot[code] = {"rank": index, "score": _num(stock.get("consensus_score"))}
    except (KeyError, ValueError, TypeError, OSError) as exc:
        errors.append("hot_ranks:%s" % exc)
    found = universe(state, ladder, overview)
    for code, meta in hot.items():
        item = found.setdefault(code, {"symbol": code, "name": code, "sources": ["hot"]})
        item.setdefault("sources", [])
        if "hot" not in item["sources"]:
            item["sources"].append("hot")
        item["hot_rank"] = meta["rank"]
        item["hot_rank_score"] = meta["score"]
    if not found:
        state["strong_scan"] = {"checked_at": now.isoformat(), "trade_date": now.date().isoformat(),
                                "rows": [], "errors": errors + ["empty universe"], "universe": 0}
        return state["strong_scan"]
    symbols = list(found)[:60]
    quotes = {}
    try:
        payload = api("/api/v1/quotes/realtime?" + urlencode({"symbols": ",".join(symbols)}))
        for quote in payload.get("data") or []:
            code = _symbol(quote.get("symbol"))
            if code:
                quotes[code] = quote
    except (KeyError, ValueError, TypeError, OSError) as exc:
        errors.append("quotes:%s" % exc)
    ranked = sorted(((code, _prescore(found[code], quotes.get(code, {}), (hot.get(code) or {}).get("rank")))
                     for code in found if code in quotes), key=lambda item: -item[1])
    finalists = [code for code, _ in ranked[:int(settings["max_symbols"])]]
    daily_by_symbol = {}
    if finalists:
        try:
            payload = api("/api/v1/quotes/kline/batch?" + urlencode(
                {"symbols": ",".join(finalists[:30]), "period": "day", "limit": 40}))
            daily_by_symbol = payload.get("data") or {}
        except (KeyError, ValueError, TypeError, OSError) as exc:
            errors.append("daily:%s" % exc)
    today = now.date().isoformat()
    rows = []
    for code in finalists:
        quote = quotes.get(code) or {}
        item = found[code]
        name = quote.get("name") or item.get("name") or code
        if "ST" in str(name).upper():
            continue
        daily = _daily_strength(daily_by_symbol.get(code) or [], today)
        score, layers = _score(item, quote, daily)
        rows.append({
            "symbol": code, "name": name,
            "price": _num(quote.get("price"), None), "change_percent": _num(quote.get("change_percent"), None),
            "score": score, "layers": layers, "sources": item.get("sources") or [],
            "theme": item.get("theme"), "streak": item.get("streak"),
            "hot_rank": item.get("hot_rank"), "trade_time": quote.get("trade_time"),
            "source": (quote.get("meta") or {}).get("source"), "daily_trade_date": daily and daily["trade_date"],
            "ret5": daily and daily["ret5"], "amount20": daily and daily["amount20"],
        })
    rows.sort(key=lambda row: -row["score"])
    result = {"checked_at": now.isoformat(), "trade_date": today, "rows": rows[:int(settings["max_symbols"])],
              "errors": errors, "universe": len(found), "settings": settings}
    state["strong_scan"] = result
    return result


def merge(pool, state, cfg):
    """Append the strongest scanned names as ``route=strong`` candidates."""
    settings = _settings(cfg)
    scan = state.get("strong_scan") or {}
    if not settings.get("enabled", True):
        return 0
    known = {c["symbol"] for c in pool}
    added = 0
    for row in scan.get("rows") or []:
        if added >= int(settings["merge_limit"]):
            break
        if row["symbol"] in known or row.get("score", 0) < settings["min_score"]:
            continue
        change = row.get("change_percent")
        code = str(row["symbol"]).upper().replace(".SH", "").replace(".SZ", "")
        max_day = _num(cfg.get("buy", {}).get("max_day_chg"), 7) * (2.0 if code.startswith(("688", "300")) else 1.0)
        if change is not None and not (-3 <= change <= max_day * 1.15):
            continue
        pool.append({"symbol": row["symbol"], "name": row.get("name"), "route": "strong",
                     "theme": row.get("theme"), "streak": row.get("streak") or 0,
                     "scan_score": row.get("score")})
        known.add(row["symbol"])
        added += 1
    return added
