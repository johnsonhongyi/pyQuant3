"""板块龙头识别(盘中)。
三步: 板块归属 -> 板块成分 -> 实时涨幅排序取龙头。
成分来源: yidong.build() 异动集的 surge_plates,日级缓存 logs/sector_members_<date>.json。
证伪: 龙头跌破当日1日VWAP×0.995 -> 龙头不龙(dead=True)。
"""
import datetime
import json
import os

SVC = os.path.dirname(os.path.abspath(__file__))
BJ = datetime.timezone(datetime.timedelta(hours=8))

# 用户关键持仓的板块归属(兜底,不在异动池里时用)
SECTOR_HINT = {
    "600733": "新能源汽车",  # 北汽蓝谷
    "600418": "新能源汽车",  # 江淮汽车
}

# 板块静态成分(核心大票,兜底 yidong tags 缺失)
SECTOR_STATIC = {
    "新能源汽车": ["600733", "600418", "601238", "000625", "601633", "002594",
                 "600104", "600303", "601777", "000800", "002025", "002594"],
}
# 板块关键词(匹配 surge_plates/concept_tags/reason)
SECTOR_KEYWORDS = {
    "新能源汽车": ["新能源汽车", "汽车整车", "整车"],
}


def today_str():
    return datetime.datetime.now(BJ).strftime("%Y-%m-%d")


def _load_token():
    for p in (os.path.join(SVC, ".env"), os.path.expanduser("~/.easy-stock-token")):
        try:
            with open(p) as f:
                for line in f:
                    if line.startswith("A_STOCK_TOKEN="):
                        return line.split("=", 1)[1].strip().strip("'\"")
        except OSError:
            pass
    return ""


def _api(path, timeout=20):
    import urllib.request
    tok = _load_token()
    sep = "&" if "?" in path else "?"
    url = "http://127.0.0.1:20081%s%stoken=%s" % (path, sep, tok)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def _norm(code):
    c = str(code).lower().replace("sh", "").replace("sz", "").replace(".sh", "").replace(".sz", "")
    return "".join(ch for ch in c if ch.isdigit())


def plate_of(code, date_s=None):
    """板块归属: watchpool池 > 内置映射 > yidong实时。"""
    c = _norm(code)
    date_s = date_s or today_str()
    # 1) 当日关注池
    try:
        d = json.load(open(os.path.join(SVC, "logs", "watchpool_%s.json" % date_s)))
        for a in d.get("pool", []):
            if _norm(a.get("symbol", "")) == c and a.get("plate"):
                return a["plate"]
    except (OSError, ValueError):
        pass
    # 2) 内置映射
    if c in SECTOR_HINT:
        return SECTOR_HINT[c]
    # 3) yidong实时异动集(模糊匹配)
    for sector in list(SECTOR_KEYWORDS) + list(SECTOR_STATIC):
        for m in members_all(date_s):
            if _norm(m.get("code", "")) == c and _sector_match(m, sector):
                return sector
    return ""


def members_all(date_s=None):
    """当日异动集全量(带_plate),缓存。"""
    date_s = date_s or today_str()
    cp = os.path.join(SVC, "logs", "sector_members_%s.json" % date_s)
    try:
        return json.load(open(cp))
    except (OSError, ValueError):
        pass
    import yidong as yd
    res = yd.build() or {}
    items = res.get("stocks") if isinstance(res, dict) else res
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        plates = it.get("surge_plates") or []
        pl = plates[0].get("name") if plates else ""
        it["_plate"] = pl
        out.append(it)
    try:
        json.dump(out, open(cp, "w"), ensure_ascii=False)
    except OSError:
        pass
    return out


def _sector_match(m, sector):
    kws = SECTOR_KEYWORDS.get(sector, [sector])
    texts = []
    for p in (m.get("surge_plates") or []):
        if isinstance(p, dict):
            texts.append(p.get("name", ""))
    texts += [str(t) for t in (m.get("concept_tags") or [])]
    texts.append(str(m.get("reason") or ""))
    blob = "|".join(texts)
    return any(k in blob for k in kws)


def members_of(plate, date_s=None):
    date_s = date_s or today_str()
    seen = {}
    for c in SECTOR_STATIC.get(plate, []):
        seen[_norm(c)] = {"code": _norm(c), "name": "", "_plate": plate}
    for m in members_all(date_s):
        if _sector_match(m, plate):
            c = _norm(m.get("code", ""))
            if c and c not in seen:
                seen[c] = m
            elif c:
                # 补名字
                if not seen[c].get("name"):
                    seen[c]["name"] = m.get("name", "")
    return list(seen.values())


def _realtime(codes):
    syms = ",".join(("sh" + _norm(c)) for c in codes)
    try:
        d = _api("/api/v1/quotes/realtime?symbols=" + syms, timeout=25)
        rows = d.get("data") or []
        return {_norm(r.get("symbol", "")): r for r in rows}
    except Exception:
        return {}


def leader_of(code, date_s=None):
    """板块内实时涨幅最高者为龙头。返回 dict 或 None。"""
    date_s = date_s or today_str()
    plate = plate_of(code, date_s)
    if not plate:
        return None
    members = members_of(plate, date_s)
    codes = list({_norm(m.get("code", "")) for m in members if m.get("code")})
    if not codes:
        return None
    quotes = _realtime(codes)
    ranked = []
    locked_note = ""
    for m in members:
        c = _norm(m.get("code", ""))
        q = quotes.get(c)
        if not q or not q.get("price"):
            continue
        chg = q.get("change_percent")
        if chg is None:
            pc = q.get("previous_close") or 0
            chg = (q["price"] - pc) / pc * 100 if pc else 0
        hi, lo = q.get("high") or 0, q.get("low") or 0
        locked = (hi and lo and hi == lo and chg >= 9.5)  # 一字涨停买不进,不做龙头候选
        if locked:
            locked_note = "%s%s一字板" % (m.get("name") or q.get("name") or "", c)
            continue
        ranked.append({"code": c, "name": m.get("name") or q.get("name") or "",
                       "chg": chg, "price": q["price"], "high": q.get("high"),
                       "low": q.get("low"), "plate": plate})
    if not ranked:
        return None
    ranked.sort(key=lambda x: x["chg"], reverse=True)
    top = ranked[0]
    top["is_self"] = (top["code"] == _norm(code))
    top["rank_n"] = len(ranked)
    top["locked_note"] = locked_note
    try:
        record_daily_leader(plate, top, date_s)  # P15规则3:龙头日级落盘供连续跟踪
    except Exception:
        pass
    return top


def leader_status(code, date_s=None):
    """龙头实时状态 + 证伪判断。"""
    date_s = date_s or today_str()
    ld = leader_of(code, date_s)
    if not ld:
        return {"ok": False, "reason": "no_leader_data"}
    # 当日1日VWAP(走 vwap.analyze,与盯盘同口径)
    vwap = None
    try:
        from vwap import analyze
        sym = "sh" + ld["code"]
        q = _api("/api/v1/quotes/realtime?symbols=" + sym, timeout=15)["data"][0]
        min5 = _api("/api/v1/quotes/kline?symbol=%s&period=5&limit=60" % sym,
                    timeout=20).get("data") or []
        daily = _api("/api/v1/quotes/kline?symbol=%s&period=day&limit=25" % sym,
                     timeout=20).get("data") or []
        st = analyze(q.get("price") or ld["price"], min5, daily, date_s)
        vwap = (st.get("vwap") or {}).get("d1")
    except Exception:
        pass
    price = ld["price"]
    above = (vwap is not None and price >= vwap)
    dead = (vwap is not None and price < vwap * 0.995)
    new_high = (ld.get("high") or 0) >= price * 0.999  # 接近日内最高
    ld.update({"ok": True, "vwap": vwap, "above_vwap": above,
               "new_high": new_high, "dead": dead,
               "strong": above and ld["chg"] > 2})
    return ld


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "600733"
    st = leader_status(code)
    print(json.dumps(st, ensure_ascii=False, indent=1))


# ---------------- P21 控盘板块识别 ----------------
_US_SECTOR = {  # 美股观察池静态板块(热度票 fallback general)
    "AAPL": "tech", "MSFT": "tech", "GOOGL": "tech", "META": "tech",
    "AMZN": "tech", "NVDA": "semis", "TSLA": "ev",
}


def sector_of(code, market="CN"):
    """持仓/候选的板块归属。CN 走 plate_of,US 走静态映射。"""
    if market == "US":
        return _US_SECTOR.get(code.upper(), "general")
    try:
        return plate_of(code) or ""
    except Exception:
        return ""


def _index_bars(market, n=30):
    """指数日K(算板块-指数相关系数)。CN=上证,US=SPY。"""
    try:
        if market == "US":
            import bars_us
            d = bars_us.yahoo_daily2("SPY")
            return [{"close": x["close"]} for x in d[-n:]]
        import daily_review as dr
        d = dr.api("/api/v1/quotes/kline?symbol=sh000001&period=day&limit=%d" % n,
                   timeout=15)["data"]
        return [{"close": x["close"]} for x in d if x.get("close")]
    except Exception:
        return []


def _stock_bars(code, market, n=30):
    try:
        if market == "US":
            import bars_us
            return bars_us.get_bars(code.upper())[-n:]
        from bars import get_bars  # 本地日线底座,又快又不碰上游
        kl = get_bars(code)[-n:]
        return [{"close": k["close"], "open": k.get("open"),
                 "high": k.get("high"), "low": k.get("low")} for k in kl if k.get("close")]
    except Exception:
        return []


def sector_mode(sector, market="CN", date_s=None):
    """P21:板块特征 对大盘涨跌不敏感+持续小阴小阳+波动率低 = 资金控盘。
    控盘板块 -> "grid"(只适合网格做T,不追突破/不加仓);否则 "normal"。
    日级缓存 logs/sector_mode_<date>.json。"""
    import statistics
    date_s = date_s or today_str()
    cp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "logs", "sector_mode_%s.json" % date_s)
    try:
        cache = json.load(open(cp))
    except Exception:
        cache = {}
    key = "%s:%s" % (market, sector)
    if key in cache:
        return cache[key]
    if market == "US":
        import json as _j
        uni = _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "us_watchlist.json")))["symbols"]
        members = [c for c in uni if _US_SECTOR.get(c) == sector][:12]
    else:
        members = [m.get("code") for m in members_of(sector, date_s)][:12]
    idx = _index_bars(market)
    idx_rets = [idx[i]["close"] / idx[i - 1]["close"] - 1
                for i in range(1, len(idx)) if idx[i - 1]["close"]] if len(idx) > 5 else []
    vols, bigs, corrs = [], 0, []
    for c in members:
        bars = _stock_bars(c, market)
        if len(bars) < 20:
            continue
        cl = [b["close"] for b in bars if b.get("close")]
        if len(cl) < 20:
            continue
        rets = [cl[i] / cl[i - 1] - 1 for i in range(1, len(cl))]
        vols.append(statistics.pstdev(rets))
        if max(abs(r) for r in rets) > 0.04:
            bigs += 1
        if idx_rets and len(rets) >= len(idx_rets):
            r = rets[-len(idx_rets):]
            mx, my = sum(r) / len(r), sum(idx_rets) / len(idx_rets)
            den = (sum((a - mx) ** 2 for a in r) * sum((b - my) ** 2 for b in idx_rets)) ** 0.5
            if den:
                corrs.append(sum((a - mx) * (b - my) for a, b in zip(r, idx_rets)) / den)
    controlled = False
    if vols:
        med_vol = statistics.median(vols)
        med_corr = abs(statistics.median(corrs)) if corrs else 0.0
        # 波动率低(<1.5%) + 无大阳大阴 + 与指数相关弱(<0.4,无指数数据时只看前两项)
        controlled = med_vol < 0.015 and bigs == 0 and (not corrs or med_corr < 0.4)
    mode = "grid" if controlled else "normal"
    cache[key] = mode
    json.dump(cache, open(cp, "w"), ensure_ascii=False, indent=1)
    return mode


# ---------------- P15 强行换仓:结构/跟踪/资金痕迹/陷阱(2026-09-30) ----------------
# 用户2026-09-30口述编码:
#  规则1 龙头强势=连续多日VWAP强势结构,不是单日涨幅
#  规则2 换仓后次日早盘下杀是常态,等反弹确认上不上VWAP(15分钟),不按开盘价止损
#  规则3 龙头连续跟踪能力(龙头切换事件)
#  规则4 复牌一字板次日高开>5%=T+1陷阱,不追
#  规则5 同板块换仓触发要板块资金痕迹(板块内多只强势),不只看单龙头

def _day_vwap(b, market="CN"):
    v = b.get("volume") or 0
    a = b.get("amount") or 0
    if not v or not a:
        return None
    return a / v if market == "US" else a / (v * 100)  # CN volume单位=手,US=股


def leader_structure(code, date_s=None, n=5, need=4, market="CN"):
    """P15规则1:龙头强势=连续多日VWAP强势结构(近n个交易日≥need天收盘站上日VWAP)。
    fail-closed:数据不足/算不出 -> ok=False。"""
    date_s = date_s or today_str()
    try:
        if market == "US":
            import bars_us
            bars = bars_us.get_bars(code.upper())[-n:]
            bars = [{"close": b["close"], "volume": b["volume"], "amount": b["amount"]}
                    for b in bars]
        else:
            from bars import get_bars  # 本地日线底座
            bars = get_bars(_norm(code))[-n:]
        days, above = 0, 0
        for b in bars:
            vw = _day_vwap(b, market)
            cl = b.get("close")
            if vw is None or not cl:
                continue
            days += 1
            if cl >= vw:
                above += 1
        if days < n - 1:  # 缺数据太多,fail-closed
            return {"ok": False, "reason": "bars_short", "days": days}
        return {"ok": True, "strong": above >= need, "days_above": above,
                "days": days, "need": need, "n": n}
    except Exception as e:
        return {"ok": False, "reason": "err:%s" % e}


def _leader_daily_path(date_s):
    return os.path.join(SVC, "logs", "sector_leader_%s.json" % date_s)


# ---- P22 资金环:OBV黄白线(资金决定一切) ----
def obv_status(code, n=10, lookback=60, date_s=None, market="CN"):
    """P22资金确认:OBV(白线) vs MAOBV(黄线)。
    返回: above_ma(OBV站上MAOBV,资金确认) / div(底背离:近20日价格新低但OBV不新低,护盘)。
    只用已收盘K;数据不足->ok=False。"""
    date_s = date_s or today_str()
    try:
        if market == "US":
            import bars_us
            bars = [b for b in bars_us.get_bars(code.upper()) if b["date"] < date_s][-lookback:]
            bars = [{"close": b["close"], "volume": b["volume"]} for b in bars]
        elif market == "CRYPTO":
            import bars_crypto
            bars = [b for b in bars_crypto.get_bars(code.upper()) if b["date"] < date_s][-lookback:]
            bars = [{"close": b["close"], "volume": b["volume"]} for b in bars]
        else:
            from bars import get_bars
            bars = [b for b in get_bars(_norm(code)) if b["date"] < date_s][-lookback:]
        if len(bars) < n + 11:
            return {"ok": False, "reason": "bars_short"}
        obv, obvs = 0, []
        for i, b in enumerate(bars):
            if i > 0:
                v = b.get("volume") or 0
                if b["close"] > bars[i - 1]["close"]:
                    obv += v
                elif b["close"] < bars[i - 1]["close"]:
                    obv -= v
            obvs.append(obv)
        ma = sum(obvs[-n:]) / n
        above_ma = obvs[-1] >= ma
        # 底背离:近20日价格低点晚于OBV低点(价新低而资金不新低=护盘)
        w = 20
        closes = [b["close"] for b in bars[-w:]]
        pi = min(range(w), key=lambda k: closes[k])
        oi = min(range(w), key=lambda k: obvs[-w:][k])
        div = pi > oi
        return {"ok": True, "above_ma": above_ma, "divergence": div,
                "obv": obvs[-1], "maobv": round(ma, 1)}
    except Exception as e:
        return {"ok": False, "reason": "err:%s" % e}


# ---- P22 上轨运行:能在BOLL上轨运行=强势特征(大部分冲一波回落) ----
def boll_ride(code, n=5, date_s=None, market="CN"):
    """近n个已收盘日收盘>=UPPER(20,2)×0.98的天数。ride>=4=沿上轨运行(强势特征)。
    只用已收盘K;数据不足->ok=False。"""
    date_s = date_s or today_str()
    try:
        import math
        if market == "US":
            import bars_us
            bars = [b for b in bars_us.get_bars(code.upper()) if b["date"] < date_s]
            closes = [b["close"] for b in bars]
        else:
            from bars import get_bars
            bars = [b for b in get_bars(_norm(code)) if b["date"] < date_s]
            closes = [b["close"] for b in bars]
        if len(bars) < 20 + n:
            return {"ok": False, "reason": "bars_short"}
        ride = 0
        for i in range(len(bars) - n, len(bars)):
            w = closes[i - 19:i + 1]
            mid = sum(w) / 20
            sd = math.sqrt(sum((x - mid) ** 2 for x in w) / 20)
            up = mid + 2 * sd
            if closes[i] >= up * 0.98:
                ride += 1
        last = closes[-1]
        w = closes[-20:]
        mid = sum(w) / 20
        sd = math.sqrt(sum((x - mid) ** 2 for x in w) / 20)
        up = mid + 2 * sd
        return {"ok": True, "ride": ride, "n": n,
                "dev_pct": round((last / up - 1) * 100, 1),
                "strong": ride >= 4}
    except Exception as e:
        return {"ok": False, "reason": "err:%s" % e}


# ---- P22 龙头早发现:涨跌不对称(涨多跌少) + 强度阶梯 ----
def asymmetry(code, n=10, date_s=None, market="CN"):
    """P22:涨跌不对称系数 = 近n个已收盘交易日 上涨天平均涨幅 / 下跌天平均跌幅。
    龙头特征:涨得多(大步流星)、回调少(小碎步)。fail-closed:数据不足->ok=False。
    date_s:只用 date_s 之前的已收盘K线(盘中不剧透当日)。"""
    date_s = date_s or today_str()
    try:
        if market == "US":
            import bars_us
            bars = [b for b in bars_us.get_bars(code.upper()) if b["date"] < date_s][-n:]
            bars = [{"close": b["close"]} for b in bars]
        else:
            from bars import get_bars  # 本地日线底座
            bars = [b for b in get_bars(_norm(code)) if b["date"] < date_s][-n:]
        ups, dns = [], []
        for i in range(1, len(bars)):
            pc, cc = bars[i - 1].get("close"), bars[i].get("close")
            if not pc or not cc:
                continue
            r = (cc / pc - 1) * 100
            (ups if r > 0 else dns).append(abs(r))
        if len(ups) + len(dns) < n - 2 or not ups or not dns:
            return {"ok": False, "reason": "bars_short"}
        au = sum(ups) / len(ups)
        ad = sum(dns) / len(dns)
        return {"ok": True, "ratio": round(au / ad, 2) if ad else 99.0,
                "up_avg": round(au, 2), "down_avg": round(ad, 2),
                "up_days": len(ups), "down_days": len(dns), "n": n}
    except Exception as e:
        return {"ok": False, "reason": "err:%s" % e}


def surge_highs_rising(code, date_s=None, market="CN", pct=5.0, need=2):
    """P22:每日异动高点抬升。近20个已收盘日中涨幅>=pct的异动日,其最高价是否创新高。
    need=2:至少2个异动日且后者高点>前者。数据不足->ok=False。"""
    date_s = date_s or today_str()
    try:
        if market == "US":
            import bars_us
            bars = [b for b in bars_us.get_bars(code.upper()) if b["date"] < date_s][-20:]
            bars = [{"high": b["high"], "close": b["close"]} for b in bars]
        else:
            from bars import get_bars
            bars = [b for b in get_bars(_norm(code)) if b["date"] < date_s][-20:]
        highs = []
        for i in range(1, len(bars)):
            pc, cc = bars[i - 1].get("close"), bars[i].get("close")
            if pc and cc and (cc / pc - 1) * 100 >= pct and bars[i].get("high"):
                highs.append(bars[i]["high"])
        if len(highs) < need:
            return {"ok": False, "reason": "no_surge", "surge_days": len(highs)}
        return {"ok": True, "rising": highs[-1] > highs[-2],
                "surge_days": len(highs),
                "last_high": highs[-1], "prev_high": highs[-2]}
    except Exception as e:
        return {"ok": False, "reason": "err:%s" % e}


# 早发现阈值(2026-09-30 江淮 point-in-time 标定):
#  09-22收盘1.34 / 09-23收盘2.76 / 09-24收盘3.12 / 09-28收盘4.08 / 北汽当前2.62
ASY_WATCH, ASY_CONFIRM = 2.5, 3.0


def leader_strength(code, date_s=None, market="CN"):
    """P22 龙头强度阶梯(早发现早跟单;资金决定一切):
    L1 观察: 不对称>2.5(涨多跌少初现,只观察不换仓;底背离则备注资金护盘中)
    L2 确认: 不对称>3.0 且 近5日≥4天收盘站上VWAP 且 OBV站上MAOBV(资金确认,必要条件)
    L3 加码: L2 + 异动高点抬升(资金持续加码,可加码)
    任一环节数据不可验证 -> level=0,fail-closed。"""
    date_s = date_s or today_str()
    a = asymmetry(code, date_s=date_s, market=market)
    if not a.get("ok"):
        return {"ok": False, "level": 0, "reason": a.get("reason")}
    ratio = a["ratio"]
    if ratio <= ASY_WATCH:
        return {"ok": True, "level": 0, "ratio": ratio, "why": "asym_low"}
    ob = obv_status(code, date_s=date_s, market=market)
    ob_ok = bool(ob.get("ok"))
    st = leader_structure(code, date_s=date_s, market=market)
    struct_ok = bool(st.get("ok") and st.get("strong"))
    base = {"ratio": ratio, "days_above": st.get("days_above"),
            "obv_above_ma": ob.get("above_ma") if ob_ok else None,
            "obv_div": ob.get("divergence") if ob_ok else None}
    if ratio > ASY_CONFIRM and struct_ok:
        if ob_ok and ob.get("above_ma"):
            sh = surge_highs_rising(code, date_s=date_s, market=market)
            br = boll_ride(code, date_s=date_s, market=market)
            # L3:异动高点抬升 或 沿上轨运行(强势特征,用户2026-09-30)
            lvl = 3 if ((sh.get("ok") and sh.get("rising")) or
                        (br.get("ok") and br.get("strong"))) else 2
            base.update({"ok": True, "level": lvl, "surge": sh,
                         "boll_ride": br.get("ride") if br.get("ok") else None,
                         "why": "L3加码" if lvl == 3 else "L2确认"})
            return base
        # 资金决定一切:形态再好,OBV没站上黄线就不确认
        base.update({"ok": True, "level": 1, "struct_ok": struct_ok,
                     "why": "L1观察(等资金确认:OBV未站上MAOBV)"})
        return base
    base.update({"ok": True, "level": 1, "struct_ok": struct_ok,
                 "why": "L1观察" + ("(资金护盘中)" if (ob_ok and ob.get("divergence")) else "")})
    return base


def record_daily_leader(plate, leader, date_s=None):
    """龙头日级落盘(供次日连续跟踪)。leader含code/name/chg/price。"""
    date_s = date_s or today_str()
    if not plate or not leader:
        return
    p = _leader_daily_path(date_s)
    try:
        d = json.load(open(p))
    except (OSError, ValueError):
        d = {}
    d[plate] = {"code": leader.get("code"), "name": leader.get("name"),
                "chg": leader.get("chg"), "price": leader.get("price"),
                "date": date_s}
    try:
        ls = leader_strength(leader.get("code"), date_s=date_s)
        if ls.get("ok"):
            d[plate]["strength"] = {"level": ls["level"], "ratio": ls.get("ratio"),
                                    "why": ls.get("why")}
    except Exception:
        pass
    try:
        json.dump(d, open(p, "w"), ensure_ascii=False)
    except OSError:
        pass


def prev_leader(plate, date_s=None):
    """上一交易日的板块龙头(无则None)。"""
    date_s = date_s or today_str()
    try:
        import sys
        sys.path.insert(0, SVC)
        from trading_calendar import prev_trading_day
        y = prev_trading_day(date_s)
    except Exception:
        return None
    try:
        d = json.load(open(_leader_daily_path(y)))
        return d.get(plate)
    except (OSError, ValueError):
        return None


def leader_track(code, date_s=None):
    """P15规则3:龙头连续跟踪。返回今日龙头 + 是否发生切换(焦点转移)。
    {"switched":bool,"prev":{...}|None,"curr":{...}|None}"""
    date_s = date_s or today_str()
    plate = plate_of(code, date_s)
    if not plate:
        return {"ok": False, "reason": "no_plate"}
    curr = leader_of(code, date_s)
    prev = prev_leader(plate, date_s)
    if not curr:
        return {"ok": False, "reason": "no_curr_leader", "prev": prev}
    switched = bool(prev and prev.get("code") and
                    prev.get("code") != curr.get("code"))
    return {"ok": True, "plate": plate, "switched": switched,
            "prev": prev, "curr": {"code": curr.get("code"),
                                   "name": curr.get("name"),
                                   "chg": curr.get("chg")}}


def sector_capital_trace(plate, date_s=None, strong_n=2, strong_pct=3.0):
    """P15规则5:板块资金痕迹=板块内≥strong_n只成分涨幅>strong_pct%。
    fail-closed:拉不到实时行情 -> False。"""
    date_s = date_s or today_str()
    try:
        members = members_of(plate, date_s)
        codes = list({_norm(m.get("code", "")) for m in members if m.get("code")})
        if not codes:
            return False
        quotes = _realtime(codes)
        if not quotes:
            return False
        hot = 0
        for c, q in quotes.items():
            chg = q.get("change_percent")
            if chg is None:
                pc = q.get("previous_close") or 0
                chg = (q.get("price", 0) - pc) / pc * 100 if pc else 0
            if chg > strong_pct:
                hot += 1
        return hot >= strong_n
    except Exception:
        return False


def resume_trap(ld_code, date_s=None, gap_pct=5.0):
    """P15规则4:复牌一字板次日高开陷阱。
    昨日一字涨停(high==low且涨幅≥9.5%)且今日高开>gap_pct% -> True(不追)。
    fail-closed:数据不足 -> None(调用方视为不可验证,阻断换仓)。"""
    date_s = date_s or today_str()
    try:
        from bars import get_bars
        bars = get_bars(_norm(ld_code))
        # 昨日=最后一个 date<今日 的 bar(盘中时底座可能已含今日未完成bar)
        yb = None
        for b in reversed(bars):
            if str(b.get("date") or "") < date_s:
                yb = b
                break
        if not yb:
            return None
        yh, yl, yc = yb.get("high"), yb.get("low"), yb.get("close")
        pc = yb.get("preclose") or yb.get("prev_close") or 0
        if not pc:
            # fallback:用昨日之前最后一根收盘价当preclose
            for b in reversed(bars):
                if str(b.get("date") or "") < str(yb.get("date") or "") and b.get("close"):
                    pc = b["close"]
                    break
        if not (yh and yl and yc and pc):
            return None
        was_locked = (yh == yl and (yc / pc - 1) * 100 >= 9.5)
        if not was_locked:
            return False
        # 今日开盘(5分钟K第一根≈今开)
        kl = _api("/api/v1/quotes/kline?symbol=sh%s&period=5&limit=1" % _norm(ld_code),
                  timeout=15).get("data") or []
        if not kl:
            return None
        op = kl[0].get("open") or 0
        if not op:
            return None
        return (op / pc - 1) * 100 > gap_pct
    except Exception:
        return None


# ---------------- P26 板块四维确认 ----------------
def score_dims(chgs, limit_ups, leader_level, vol_ratio):
    """P26 板块四维打分(纯函数,可单元测试)。
    chgs:成分实时涨幅%列表;limit_ups:板块涨停数;leader_level:龙头P22等级('L3'/'L2'/'L1'/None);
    vol_ratio:板块昨日总成交额/20日均。阈值初版2026-09-30(用户:阈值你定,先给初版,复盘再调)。"""
    if chgs:
        med = sorted(chgs)[len(chgs) // 2]
        qiang = 25 if med >= 2 else (15 if med >= 1 else (8 if med >= 0 else 0))
    else:
        med, qiang = None, 0
    redu = 25 if (limit_ups or 0) >= 3 else (15 if (limit_ups or 0) >= 1 else 0)
    lidu = {"L3": 25, "L2": 15, "L1": 8}.get(leader_level, 0)
    vr = vol_ratio or 0
    liang = 25 if vr >= 1.5 else (15 if vr >= 1.2 else (8 if vr >= 1.0 else 0))
    return {"score": qiang + redu + lidu + liang, "强度": qiang, "热度": redu,
            "力度": lidu, "量能": liang,
            "detail": {"涨幅中位数": round(med, 2) if med is not None else None,
                       "涨停数": limit_ups, "龙头等级": leader_level,
                       "量比": round(vr, 2) if vr else None}}


def sector_score(plate, date_s=None, market="CN"):
    """P26 板块四维确认(2026-09-30用户拍板"板块最重要"):强度+热度+力度+量能。
    fail-closed:板块不明/拉不到数据 -> score 0。"""
    date_s = date_s or today_str()
    try:
        if not plate:
            return {"score": 0, "reason": "no_plate"}
        members = members_of(plate, date_s)
        codes = list({_norm(m.get("code", "")) for m in members if m.get("code")})
        if not codes:
            return {"score": 0, "reason": "no_members"}
        quotes = _realtime(codes)
        if not quotes:
            return {"score": 0, "reason": "no_quotes"}
        chgs = []
        for c, q in quotes.items():
            chg = q.get("change_percent")
            if chg is None:
                pc = q.get("previous_close") or 0
                chg = (q.get("price", 0) - pc) / pc * 100 if pc else 0
            chgs.append(chg)
        # 热度:板块内涨停数(yidong几天几板/涨停类型标记)
        limit_ups = sum(1 for m in members
                        if m.get("m_days_n_boards") or "涨停" in str(m.get("limit_up_type") or ""))
        # 力度:龙头=涨幅最高者(剔一字板),取P22等级
        ranked = []
        for c, q in quotes.items():
            hi, lo, chg = q.get("high") or 0, q.get("low") or 0, None
            pc = q.get("previous_close") or 0
            chg = q.get("change_percent")
            if chg is None:
                chg = (q.get("price", 0) - pc) / pc * 100 if pc else 0
            if hi and lo and hi == lo and chg >= 9.5:
                continue
            ranked.append((c, chg))
        leader_level = None
        leader_code = ranked[0][0] if ranked else None
        if leader_code:
            ls = leader_strength(leader_code, date_s=date_s, market=market)
            lv = ls.get("level") or 0
            leader_level = {3: "L3", 2: "L2", 1: "L1"}.get(lv)
        # 量能:板块昨日总成交额/20日均(本地底座,不碰上游)
        vol_ratio = None
        try:
            tot_y, tot_avg = 0.0, 0.0
            n = 0
            for c in codes:
                if market == "US":
                    import bars_us
                    kl = bars_us.get_bars(c.upper())[-21:]
                else:
                    from bars import get_bars
                    kl = get_bars(c)[-21:]
                amts = [k.get("amount") or 0 for k in kl if k.get("amount")]
                if len(amts) >= 21:
                    tot_y += amts[-1]
                    tot_avg += sum(amts[-21:-1]) / 20
                    n += 1
            if n and tot_avg:
                vol_ratio = tot_y / tot_avg
        except Exception:
            vol_ratio = None
        r = score_dims(chgs, limit_ups, leader_level, vol_ratio)
        r.update({"plate": plate, "members": len(codes), "leader": leader_code})
        return r
    except Exception as e:
        return {"score": 0, "reason": "exc:%s" % e}
