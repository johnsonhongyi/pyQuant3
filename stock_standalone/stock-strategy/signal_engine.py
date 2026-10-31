"""Point-in-time multi-layer signal scoring for the CN paper follower.

Pure functions only: no network, no persistence, no clock reads.  The caller
passes already-filtered bars and a frozen evaluation time.  Hard risk vetoes
stay separate from the score so a single weak layer cannot silently admit an
order.
"""

DEFAULT_WEIGHTS = {"trend": 25, "intraday": 25, "relative": 20, "theme": 15, "liquidity": 15}
DEFAULT_BAND = {"low": 0.995, "high": 1.030}
DEFAULT_HARD = {"change_floor": -3.0, "change_ceiling_multiple": 1.15, "min_daily_bars": 20}
MAX_LAYER_NOTES = 6


def _num(value, default=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result or result in (float("inf"), float("-inf")):
        return default
    return result


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _slope(values):
    """Simple least-squares slope over an evenly spaced series."""
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return 0.0
    n = len(values)
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(values) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if not denom:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / denom


def _limit_ratio(code):
    code = str(code).upper().replace(".SH", "").replace(".SZ", "")
    return 1.20 if code.startswith(("688", "300")) else 1.10


def _vwap(bars, minimum=1):
    """VWAP over bars that actually traded.

    Zero-volume bars (suspensions, empty auction buckets) contribute nothing to
    VWAP and must not invalidate an otherwise usable window.
    """
    import auto_follow as af
    valid = [b for b in bars if _num(b.get("amount"), 0) > 0 and _num(b.get("volume"), 0) > 0
             and not b.get("vwap_estimated")]
    if len(valid) < max(1, minimum):
        raise ValueError("exact VWAP unavailable")
    return af.exact_vwap(valid)


def daily_metrics(daily, today, previous_day, now):
    """Daily anchors using only completed bars before ``today``."""
    import auto_follow as af
    completed = sorted((b for b in daily if str(b.get("time"))[:10] < today), key=lambda b: b["time"])
    if len(completed) < 20 or str(completed[-1]["time"])[:10] != previous_day:
        return None, "previous completed trading day unavailable"
    if any(b.get("meta", {}).get("stale") is not False or not b.get("meta", {}).get("source")
           for b in completed[-20:]):
        return None, "daily source unavailable"
    try:
        vwap = {n: _vwap(completed[-n:], max(1, n - 2)) for n in (1, 3, 5, 10)}
    except (KeyError, ValueError, TypeError) as exc:
        return None, str(exc) or "exact VWAP unavailable"
    closes = [af.number(b["close"]) for b in completed]
    amounts = [_num(b.get("amount")) for b in completed[-20:]]
    ma = {n: _mean(closes[-n:]) for n in (5, 10, 20)}
    ma5_prev = _mean(closes[-10:-5])
    high20 = max(_num(b.get("high"), 0) for b in completed[-20:])
    close = closes[-1]
    ret5 = close / closes[-6] - 1 if len(closes) >= 6 else 0.0
    ret20 = close / closes[-21] - 1 if len(closes) >= 21 else 0.0
    return {
        "close": close,
        "vwap1": vwap[1], "vwap3": vwap[3], "vwap5": vwap[5], "vwap10": vwap[10],
        "ma5": ma[5], "ma10": ma[10], "ma20": ma[20],
        "ma5_slope": (ma[5] / ma5_prev - 1) if ma5_prev else 0.0,
        "high20": high20, "ret5": ret5, "ret20": ret20,
        "amount20": _mean(amounts),
        "trade_date": str(completed[-1]["time"])[:10],
        "bars": len(completed),
    }, None


def intraday_metrics(minute, price, now, today):
    """Intraday structure from bars closed at or before ``now``."""
    import auto_follow as af
    bars = sorted((b for b in minute
                   if str(b.get("time"))[:10] == today and af.stamp(b["time"]) <= now),
                  key=lambda b: b["time"])
    if len(bars) < 4 or (now - af.stamp(bars[-1]["time"])).total_seconds() > 360:
        return None, "intraday bars unavailable"
    for b in bars:
        try:
            af.fresh(b["meta"], now, 600)
        except (KeyError, ValueError, TypeError):
            return None, "intraday source unavailable"
    try:
        vwap = _vwap(bars, 4)
    except (KeyError, ValueError, TypeError):
        return None, "exact VWAP unavailable"
    last = bars[-3:]
    rising = all(af.number(b["close"]) >= af.number(a["close"]) and
                 af.number(b["volume"]) >= af.number(a["volume"]) for a, b in zip(last, last[1:]))
    session_high = max(_num(b.get("high"), price) for b in bars)
    session_open = _num(bars[0].get("open"), price)
    return {
        "vwap": vwap,
        "bars": len(bars),
        "last_bar": bars[-1]["time"],
        "rising": rising,
        "session_high": session_high,
        "session_open": session_open,
    }, None


def _trend_layer(dm, notes):
    score = 0
    if dm["vwap1"] > dm["vwap3"] > dm["vwap5"]:
        score += 10
        notes.append("多日VWAP多头排列")
    else:
        notes.append("VWAP未多头排列")
    if dm["close"] >= dm["ma20"]:
        score += 6
        notes.append("收盘站上MA20")
    if dm["ma5"] > dm["ma10"]:
        score += 4
        notes.append("MA5>MA10")
    if dm["ma5_slope"] > 0:
        score += 5
        notes.append("MA5斜率向上")
    return score


def _intraday_layer(im, price, band, notes):
    score = 0
    low, high = im["vwap"] * band["low"], im["vwap"] * band["high"]
    if low <= price <= high:
        score += 10
        notes.append("价格处于VWAP带")
    elif im["vwap"] * (band["low"] - 0.005) <= price <= im["vwap"] * (band["high"] + 0.005):
        score += 6
        notes.append("价格贴近VWAP带边缘")
    else:
        notes.append("价格偏离VWAP带")
    if im["rising"]:
        score += 6
        notes.append("最近三根量价齐升")
    else:
        notes.append("量价未连续")
    return score, low, high


def _relative_layer(dm, change, pool_change_median, notes):
    score = 0
    ret5 = dm["ret5"]
    if ret5 >= 0.12:
        score += 8
    elif ret5 >= 0.07:
        score += 6
    elif ret5 >= 0.03:
        score += 4
    elif ret5 >= 0:
        score += 2
    if ret5 > 0:
        notes.append("5日强度%+.1f%%" % (ret5 * 100))
    proximity = dm["close"] / dm["high20"] if dm["high20"] else 0
    if proximity >= 0.98:
        score += 6
        notes.append("接近20日高点")
    elif proximity >= 0.95:
        score += 4
    elif proximity >= 0.90:
        score += 2
    if pool_change_median is not None and change is not None:
        if change >= pool_change_median + 2:
            score += 6
            notes.append("当日强于池内中位")
        elif change >= pool_change_median:
            score += 4
        elif change >= pool_change_median - 2:
            score += 2
    else:
        score += 3
    return score


def _theme_layer(theme, notes):
    if not theme:
        return 7  # neutral: no verified theme evidence must not look bullish
    score = 0
    change = _num(theme.get("change_percent"), 0)
    rising, falling = _num(theme.get("rising_nodes"), 0), _num(theme.get("falling_nodes"), 0)
    if change > 0 and rising > falling:
        score += 8
        notes.append("题材上涨且扩散")
    elif change > 0:
        score += 4
    if theme.get("leader_rank") and theme["leader_rank"] <= 5:
        score += 4
        notes.append("题材前五")
    if theme.get("rank") and theme["rank"] <= 3:
        score += 3
        notes.append("题材前三")
    return score


def _liquidity_layer(dm, price, notes):
    score = 0
    amount = dm.get("amount20") or 0
    if amount >= 300_000_000:
        score += 8
    elif amount >= 150_000_000:
        score += 6
    elif amount >= 80_000_000:
        score += 4
    else:
        score += 2
    if 2 <= price <= 200:
        score += 4
    else:
        notes.append("价格区间异常")
    score += 3  # not ST / not sealed is enforced as a hard veto
    return score


def evaluate(stock, quote, minute, daily, context):
    """Return a transparent score plus hard blockers for one candidate.

    ``context`` keys: now, today, previous_day, cfg, regime, pool_change_median,
    theme, ai (optional overlay dict).
    """
    import auto_follow as af
    now, today = context["now"], context["today"]
    cfg = context.get("cfg") or {}
    execution = cfg.get("execution") or {}
    band = {**DEFAULT_BAND, **((execution.get("signal") or {}).get("vwap_band") or {})}
    hard_cfg = {**DEFAULT_HARD, **((execution.get("signal") or {}).get("hard") or {})}
    weights = {**DEFAULT_WEIGHTS, **((execution.get("signal") or {}).get("weights") or {})}
    notes = []
    blockers = []
    code = stock.get("symbol") or quote.get("symbol")

    price = _num(quote.get("price"))
    change = _num(quote.get("change_percent"))
    if price is None or price <= 0:
        blockers.append("invalid price")
    if price:
        exposure = (context.get("regime") or {}).get("exposure", 1) or 0
        budget = _num((cfg.get("buy") or {}).get("amount_per_trade"), 100000) * exposure
        if budget > 0 and price * 100 > budget:
            blockers.append("lot size exceeds budget")
    if change is None:
        blockers.append("invalid change_percent")
    name = str(quote.get("name") or stock.get("name") or "")
    if "ST" in name.upper():
        blockers.append("ST excluded")
    previous_close = _num(quote.get("previous_close"))
    if previous_close and price:
        limit = round(previous_close * _limit_ratio(code), 2)
        if price >= limit - 0.01:
            blockers.append("sealed limit-up")
    if change is not None:
        is_20cm = str(code).upper().replace(".SH", "").replace(".SZ", "").startswith(("688", "300"))
        max_day = _num(cfg.get("buy", {}).get("max_day_chg"), 7.0) * (2.0 if is_20cm else 1.0)
        ceiling = max_day * hard_cfg["change_ceiling_multiple"]
        if change <= hard_cfg["change_floor"]:
            blockers.append("P4 falling knife")
        elif change >= ceiling:
            blockers.append("P4 change gate")

    dm, error = daily_metrics(daily, today, context["previous_day"], now)
    if error:
        blockers.append(error)
    im, error = intraday_metrics(minute, price or 0, now, today)
    if error:
        blockers.append(error)

    layers = {}
    if dm and im:
        trend = _trend_layer(dm, notes)
        intraday, band_low, band_high = _intraday_layer(im, price, band, notes)
        if im["vwap"] >= dm["vwap3"]:
            intraday += 5
            notes.append("日内VWAP≥VWAP3")
        else:
            notes.append("日内VWAP低于VWAP3")
        if not (change and change > 3 and price < im["session_high"] * 0.99):
            intraday += 2
        else:
            notes.append("冲高回落否决")
        if previous_close and im["session_open"] >= previous_close * 1.02 and price < im["session_open"]:
            notes.append("高开低走否决")
        else:
            intraday += 2
        relative = _relative_layer(dm, change, context.get("pool_change_median"), notes)
        theme = _theme_layer(context.get("theme"), notes)
        liquidity = _liquidity_layer(dm, price, notes)
        layers = {
            "trend": {"score": trend, "max": weights["trend"], "notes": notes[:MAX_LAYER_NOTES]},
            "intraday": {"score": min(intraday, weights["intraday"]), "max": weights["intraday"]},
            "relative": {"score": min(relative, weights["relative"]), "max": weights["relative"]},
            "theme": {"score": min(theme, weights["theme"]), "max": weights["theme"]},
            "liquidity": {"score": min(liquidity, weights["liquidity"]), "max": weights["liquidity"]},
        }
        total = sum(v["score"] for v in layers.values())
        if price > band_high * 1.005:
            blockers.append("P8 VWAP gate")
        if price < band_low * 0.99:
            blockers.append("P8 below VWAP")
    else:
        total = 0
        band_low = band_high = None

    ai = context.get("ai") or {}
    ai_delta = int(ai.get("delta") or 0)
    if ai.get("veto"):
        blockers.append("AI veto")
    score = max(0, min(100, total + ai_delta))
    return {
        "symbol": code,
        "score": score,
        "raw_score": total,
        "layers": layers,
        "blockers": sorted(set(blockers)),
        "notes": notes[:MAX_LAYER_NOTES],
        "metrics": {
            "price": price, "change_percent": change,
            "vwap1": dm and dm["vwap1"], "vwap3": dm and dm["vwap3"], "vwap5": dm and dm["vwap5"],
            "vwap10": dm and dm["vwap10"], "ma20": dm and dm["ma20"],
            "intraday_vwap": im and im["vwap"],
            "entry_low": band_low, "entry_high": band_high,
            "ret5": dm and dm["ret5"], "high20": dm and dm["high20"],
            "amount20": dm and dm["amount20"],
        },
        "ai": ai,
        "band": band,
        "checked_at": now.isoformat(),
        "trade_date": today,
    }
