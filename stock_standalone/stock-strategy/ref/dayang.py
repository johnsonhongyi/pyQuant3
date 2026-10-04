"""大阳事件与买卖点预判(江淮/北汽精华沉淀,2026-09-30用户拍板)。

精华:
- 江淮式启动: 长回撤后大阳(>=7%)站上MA60(前收<MA60) + 放量>=1.5x + OBV站上黄线 + 次日站住
- 北汽式跟风: OBV刚站上 + 涨跌不对称<3 + 没放巨量(量比<2) -> 只观察不追
买卖点(全部point-in-time,只用已收盘K,数据不足fail-closed):
- startup_buy 启动买点: 大阳在近3个交易日内 & 站上MA60 & 放量 & OBV黄线上 & 60日涨幅<80%
- pullback_buy 回踩买点: 大阳后1-5日 & 回踩不破大阳日最低*0.98 & 仍>=MA60 & OBV黄线上
- watch 跟风观察: 有大阳但不对称<3或没放量
- miss_sell 不及预期卖出: 大阳后3个交易日不创新高(最高<大阳最高)
- stop_sell 跌破卖出: 跌破大阳日最低 / OBV掉下黄线
"""
import datetime
import os
import sys

SVC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SVC)

DAYANG_PCT = 7.0       # 大阳线阈值
VOL_MULT = 1.5         # 放量倍数
HOLD_PCT = 0.98        # 次日站住:收盘>=大阳收盘*0.98
MISS_DAYS = 3          # 不及预期:大阳后N个交易日不创新高
HIGH_60D = 80.0        # 60日涨幅过滤(不过热)


def _norm(code):
    return str(code).strip().upper().lstrip("SH").lstrip("SZ")


def _bars(code, date_s, n, market):
    if market == "US":
        import bars_us
        bars = [b for b in bars_us.get_bars(_norm(code)) if b["date"] < date_s][-n:]
        return [{"date": b["date"], "open": b["open"], "high": b["high"],
                 "low": b["low"], "close": b["close"], "volume": b["volume"]}
                for b in bars]
    if market == "CRYPTO":
        import bars_crypto
        # 注意:不用 _norm(它的 lstrip("SH") 会把 "SOL" 切成 "OL")
        bars = [b for b in bars_crypto.get_bars(str(code).strip().upper())
                if b["date"] < date_s][-n:]
        return [{"date": b["date"], "open": b["open"], "high": b["high"],
                 "low": b["low"], "close": b["close"], "volume": b["volume"]}
                for b in bars]
    from bars import get_bars
    bars = [b for b in get_bars(_norm(code)) if b["date"] < date_s][-n:]
    return bars


def _ma60(bars, i):
    if i < 59:
        return None
    return sum(b["close"] for b in bars[i - 59:i + 1]) / 60


def dayang_events(code, n=20, pct=DAYANG_PCT, date_s=None, market="CN"):
    """近n个已收盘交易日的大阳线事件。fail-closed:数据不足->[]。"""
    date_s = date_s or datetime.date.today().isoformat()
    try:
        bars = _bars(code, date_s, n + 80, market)
        if len(bars) < n + 5:
            return []
        from sector_leader import obv_status
        evs = []
        for i in range(len(bars) - n, len(bars)):
            b, pb = bars[i], bars[i - 1]
            if not pb.get("close") or not b.get("close"):
                continue
            chg = (b["close"] / pb["close"] - 1) * 100
            if chg < pct:
                continue
            vols = [x.get("volume") or 0 for x in bars[max(0, i - 20):i]]
            avgv = sum(vols) / len(vols) if vols else 0
            ma60 = _ma60(bars, i)
            pma60 = _ma60(bars, i - 1)
            # 大阳日视角=date_s取大阳日次日,obv_status只用已收盘K,含大阳日本身
            ob2 = obv_status(code,
                             date_s=(datetime.date.fromisoformat(b["date"]) +
                                     datetime.timedelta(days=1)).isoformat(),
                             market=market)
            evs.append({
                "date": b["date"], "chg": round(chg, 2), "close": b["close"],
                "high": b["high"], "low": b["low"],
                "vol_ratio": round((b.get("volume") or 0) / avgv, 2) if avgv else 0,
                "above_ma60": ma60 is not None and b["close"] >= ma60,
                "prev_below_ma60": pma60 is not None and pb["close"] < pma60,
                "obv_above": bool(ob2.get("ok") and ob2.get("above_ma")),
                "ma60": round(ma60, 2) if ma60 else None,
            })
        return evs
    except Exception:
        return []


def dayang_signal(code, date_s=None, market="CN"):
    """对最近一次大阳做买卖点判断。返回{signal, ...};无大阳/数据不足->neutral。"""
    date_s = date_s or datetime.date.today().isoformat()
    try:
        bars = _bars(code, date_s, 90, market)
        if len(bars) < 65:
            return {"signal": "neutral", "reason": "bars_short"}
        evs = dayang_events(code, n=20, date_s=date_s, market=market)
        if not evs:
            return {"signal": "neutral", "reason": "no_dayang"}
        ev = evs[-1]
        last = bars[-1]
        # 大阳后经过的交易日数
        days_after = sum(1 for b in bars if b["date"] > ev["date"])
        from sector_leader import obv_status, asymmetry
        ob = obv_status(code, date_s=date_s, market=market)
        ob_ok = bool(ob.get("ok"))
        obv_up = ob_ok and ob.get("above_ma")
        # 60日涨幅
        b60 = bars[-61]["close"] if len(bars) >= 61 and bars[-61].get("close") else None
        r60 = (last["close"] / b60 - 1) * 100 if b60 else 0
        a = asymmetry(code, date_s=date_s, market=market)
        asym = a.get("ratio") if a.get("ok") else 0
        ma60 = _ma60(bars, len(bars) - 1)

        # 卖出侧先行:跌破大阳日最低 / OBV掉下黄线
        if last["close"] < ev["low"]:
            return {"signal": "stop_sell", "ev": ev,
                    "why": "跌破大阳日(%s)最低%.2f" % (ev["date"], ev["low"])}
        if ob_ok and not ob.get("above_ma"):
            return {"signal": "stop_sell", "ev": ev,
                    "why": "OBV掉下黄线,资金离场"}
        # 不及预期:大阳后3个交易日不创新高
        if days_after >= MISS_DAYS:
            highs = [b["high"] for b in bars if b["date"] > ev["date"]]
            if highs and max(highs) < ev["high"]:
                return {"signal": "miss_sell", "ev": ev,
                        "why": "大阳后%d个交易日不创新高(最高%.2f<大阳最高%.2f),不及预期" % (
                            days_after, max(highs), ev["high"])}
        # 买入侧:启动买点
        if days_after <= 3 and ev["above_ma60"] and ev["prev_below_ma60"] \
                and ev["vol_ratio"] >= VOL_MULT and ev["obv_above"] and r60 < HIGH_60D:
            # 次日站住确认(大阳次日及之后)
            if days_after >= 1:
                nb = next((b for b in bars if b["date"] > ev["date"]), None)
                if nb and (nb["close"] < ev["close"] * HOLD_PCT or
                           (ma60 and nb["close"] < ma60)):
                    return {"signal": "watch", "ev": ev,
                            "why": "大阳次日没站住,先观察"}
            return {"signal": "startup_buy", "ev": ev,
                    "why": "大阳站上MA60+放量%.1fx+OBV黄线上+60日+%.0f%%" % (
                        ev["vol_ratio"], r60)}
        # 回踩买点
        if 1 <= days_after <= 5 and ma60 and last["close"] >= ma60 \
                and last["low"] >= ev["low"] * 0.98 and obv_up:
            return {"signal": "pullback_buy", "ev": ev,
                    "why": "大阳后回踩不破(最低%.2f vs 大阳最低%.2f)+站上MA60+OBV黄线上" % (
                        last["low"], ev["low"])}
        # 跟风观察
        return {"signal": "watch", "ev": ev, "days_after": days_after,
                "asym": asym, "obv_up": obv_up,
                "why": "有大阳但%s" % (
                    "不对称%.2f<3,跟风" % asym if asym and asym < 3
                    else "量能/结构未确认,观察")}
    except Exception as e:
        return {"signal": "neutral", "reason": "err:%s" % e}


def scan(codes, date_s=None, market="CN"):
    """批量扫描,返回{signal: [code,...]}。"""
    out = {}
    for c in codes:
        try:
            r = dayang_signal(c, date_s=date_s, market=market)
        except Exception as e:
            r = {"signal": "neutral", "reason": "err:%s" % e}
        out.setdefault(r["signal"], []).append(c)
    return out


if __name__ == "__main__":
    import json
    date_s = sys.argv[1] if len(sys.argv) > 1 else None
    codes = sys.argv[2:] or ["600418", "600733"]
    res = {c: dayang_signal(c, date_s=date_s) for c in codes}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
