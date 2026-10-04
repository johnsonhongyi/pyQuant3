#!/usr/bin/env python3
"""卖出侧保护规则(2026-09-29用户拍板落地):
P16 卖出附买回计划 / P17 买入次日下杀即走 / P18 止盈后补回 /
P19 加速大阳诱多 / P20 保本出局 / P11头肩顶前置预警。
市场无关纯逻辑;paper_trade.py 在 --signal/--settle 中调用。"""
import json
import os

SVC = os.path.dirname(os.path.abspath(__file__))


# ---------------- P19 加速大阳诱多 ----------------
def detect_accel(daily):
    """长期抗跌横盘后首次加速大阳:当日涨幅>7%且放量>2倍,前20天无>7%大阳、
    20天振幅<25%(横盘)、最大回撤<15%(抗跌)。daily 老->新 [{time,open,high,low,close,volume}]。"""
    if not daily or len(daily) < 25:
        return None
    t, y = daily[-1], daily[-2]
    if not y.get("close"):
        return None
    chg = t["close"] / y["close"] - 1
    if chg <= 0.07:
        return None
    prev = daily[-21:-1]
    vols = [b.get("volume") or 0 for b in prev]
    avgv = sum(vols) / len(vols) if vols else 0
    if not avgv or (t.get("volume") or 0) <= 2 * avgv:
        return None
    for i in range(1, len(prev)):
        pc = prev[i - 1].get("close")
        if pc and prev[i]["close"] / pc - 1 > 0.07:
            return None  # 非首次加速
    hi = max(b["high"] for b in prev)
    lo = min(b["low"] for b in prev)
    if hi / lo - 1 >= 0.25:
        return None  # 非横盘
    if lo < hi * 0.85:
        return None  # 曾深跌,非抗跌
    return {"chg": round(chg * 100, 2),
            "vol_ratio": round((t.get("volume") or 0) / avgv, 2),
            "high": t["high"], "close": t["close"]}


# ---------------- P11 头肩顶前置预警 ----------------
def detect_hs_top(m5):
    """分时级别在VWAP下方形成头肩顶=多头衰竭前置预警。
    m5: 当日5分钟K老->新 [{time,open,high,low,close,volume}]。
    返回 (True/False, 描述)。右肩反弹不过VWAP是最后离场点,早于P11三段式确认。"""
    if not m5 or len(m5) < 12:
        return False, "bars不足"
    vw, cpv, cv = [], 0.0, 0.0
    for b in m5:
        tp = (b["high"] + b["low"] + b["close"]) / 3.0
        v = b.get("volume") or 0
        cpv += tp * v
        cv += v
        vw.append(cpv / cv if cv else None)
    highs = [b["high"] for b in m5]
    n = len(m5)
    peaks = [i for i in range(2, n - 2)
             if highs[i] == max(highs[i - 2:i + 3])]
    # 相邻峰去重(留更高者)
    ded = []
    for i in peaks:
        if ded and i - ded[-1] <= 2:
            if highs[i] > highs[ded[-1]]:
                ded[-1] = i
        else:
            ded.append(i)
    for a in range(len(ded)):
        for b in range(a + 1, len(ded)):
            for c in range(b + 1, len(ded)):
                i, j, k = ded[a], ded[b], ded[c]
                hi, hj, hk = highs[i], highs[j], highs[k]
                if not (hj > hi and hj > hk):
                    continue
                if (hj - hi) / hj < 0.008 or (hj - hk) / hj < 0.008:
                    continue  # 头不够突出
                if abs(hi - hk) / hj > 0.012:
                    continue  # 双肩不对称
                if not (vw[i] and vw[j] and vw[k]):
                    continue
                if not (hi < vw[i] and hj < vw[j] and hk < vw[k]):
                    continue  # 必须全在VWAP下方
                tail_hi = max(highs[k:]) if k < n - 1 else hk
                if tail_hi >= vw[-1]:
                    continue  # 右肩后反弹过VWAP,不算衰竭
                if m5[-1]["close"] >= vw[-1]:
                    continue
                return True, ("左肩%.2f 头%.2f 右肩%.2f 均在VWAP下方,"
                              "右肩后最高%.2f未过VWAP%.2f") % (hi, hj, hk, tail_hi, vw[-1])
    return False, ""


# ---------------- P16 卖出附买回计划 ----------------
def buyback_plan_for(reason):
    """任何主动卖出必须同时写明买回触发条件,否则视为情绪卖出不执行。
    返回 {trigger, line, auto_watch}。止损系不自动买回,需重走完整信号链。"""
    r = reason or ""
    if "止盈" in r or "P20" in r:
        return {"trigger": "P18补回:重新站上1日VWAP×1.005且放量(量价齐升)",
                "line": "1日VWAP", "auto_watch": True}
    if "网格T卖出" in r:
        return {"trigger": "回踩P11网格买入区(P11信号自动接回)", "line": "网格买入区",
                "auto_watch": False}
    if "轮动卖弱" in r:
        return {"trigger": "强度分回升≥加仓阈值,或重新走关注池→竞价→确认信号链",
                "line": "强度分", "auto_watch": False}
    if "P15" in r or "换仓" in r:
        return {"trigger": "龙头证伪(跌破VWAP)或原持仓强度分回升", "line": "龙头VWAP",
                "auto_watch": False}
    return {"trigger": "不自动买回:需重新走关注池→竞价→确认完整信号链",
            "line": "无", "auto_watch": False}


# ---------------- P16/P18 买回观察池 ----------------
def _watch_path(market):
    return os.path.join(SVC, "logs", "buyback_watch_%s.json" % market)


def load_watch(market):
    """读买回观察池,顺手清掉过期条目(expiry<今日)。"""
    p = _watch_path(market)
    try:
        d = json.load(open(p))
    except Exception:
        return []
    today = _today_s(market)
    kept = [e for e in d.get("entries", []) if e.get("expiry", "9999") >= today]
    if len(kept) != len(d.get("entries", [])):
        json.dump({"entries": kept}, open(p, "w"), ensure_ascii=False, indent=1)
    return kept


def _today_s(market):
    import sys
    sys.path.insert(0, SVC)
    if market == "US":
        from trading_calendar import today_str
        return today_str("US")
    import datetime
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")


def add_watch_entry(market, code, name, set_date, reason):
    """止盈/P20卖出 -> 进入买回观察池,5个交易日有效。"""
    import sys
    sys.path.insert(0, SVC)
    from trading_calendar import next_trading_day
    p = _watch_path(market)
    try:
        d = json.load(open(p))
        entries = d.get("entries", [])
    except Exception:
        entries = []
    entries = [e for e in entries if e.get("code") != code]
    entries.append({"code": code, "name": name, "set_date": set_date,
                    "expiry": next_trading_day(set_date, n=5, market=market),
                    "reason": reason})
    json.dump({"entries": entries}, open(p, "w"), ensure_ascii=False, indent=1)


def drop_watch_entry(market, code):
    p = _watch_path(market)
    try:
        d = json.load(open(p))
    except Exception:
        return
    d["entries"] = [e for e in d.get("entries", []) if e.get("code") != code]
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)


def p18_ok(m):
    """P18补回触发:重新站上1日VWAP×1.005且放量(量价齐升),偏离<2.5%。
    m 为早盘识别dict。买回计划的具体执行,不因"卖飞难受"而抗拒。"""
    if not m or m.get("error") or not m.get("vwap_5min"):
        return False, "早盘数据不可验证"
    vwap5 = m["vwap_5min"]
    px = m.get("price") or 0
    if px <= 0:
        return False, "无价"
    if px < vwap5 * 1.005:
        return False, "未站上VWAP"
    if not m.get("vol_up"):
        return False, "非量价齐升"
    if (px - vwap5) / vwap5 > 0.025:
        return False, "偏离VWAP过大"
    return True, ""
