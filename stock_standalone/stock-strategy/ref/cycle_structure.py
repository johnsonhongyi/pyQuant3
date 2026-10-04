#!/usr/bin/env python3
"""P30 时间周期结构(2026-10-03 用户感知编码):
上涨/下跌/反弹段的"时间周期+斜率"量化的是市场情绪本身,不是价格形态。
弱反弹=情绪消耗;情绪耗尽后若选择向上突破=结构切换。

纯函数,point-in-time:只用已收盘 bar(调用方先用 drop_forming 剔除 forming 中那根)。
阈值全部来自 strategy.yaml 的 p30_cycle 段,不 hardcode。
bar 格式: dict(time='YYYY-MM-DD HH:MM'(UTC),open,high,low,close,...) 升序。
"""
import datetime
import os

SVC = os.path.dirname(os.path.abspath(__file__))

_DEFAULTS = {
    "swing_k": 2,          # 摆动点左右各 k 根确认
    "lookback_hours": 96,  # 回看小时数
    "weak_time_ratio": 1.2,   # 反弹时长/下跌时长 > 该值
    "weak_retrace": 0.382,    # 反弹点数/下跌点数 < 该值
    "steady_slope_mult": 1.5, # 稳态:快段斜率 > 慢段斜率×该值
    "accel_mult": 1.0,        # 结构切换:急拉斜率 > 下跌段斜率×该值(V型选择)
    "accel_window": 3,        # 加速判定时长(小时)
    "switch_window": 24,      # 结构切换:弱反弹形态过期时长(小时)
    "break_tol": 0.002,       # 破前高/前低容差
    "expect_ratio_warn": 1.0,  # 不及预期预警:反向段时长/原段时长 ≥ 该值(建议出局)
    "expect_ratio_exit": 2.0,  # 不及预期出局:≥ 该值策略单自动平(镜像单只预警)
}


def load_cfg():
    """读 strategy.yaml 的 p30_cycle 段(缺失则用 _DEFAULTS)。"""
    cfg = dict(_DEFAULTS)
    try:
        import yaml
        d = yaml.safe_load(open(os.path.join(SVC, "strategy.yaml"))) or {}
        sec = d.get("p30_cycle") or {}
        for k in cfg:
            if k in sec:
                cfg[k] = sec[k]
        cfg["_strategy_version"] = d.get("version", "?")
    except Exception:
        cfg["_strategy_version"] = "?"
    return cfg


def drop_forming(bars):
    """剔除最后一根 forming 中的 bar(其 time 小时 == 当前 UTC 小时)。"""
    if not bars:
        return bars
    try:
        cur_h = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H")
        if str(bars[-1].get("time", ""))[:13] == cur_h:
            return bars[:-1]
    except Exception:
        pass
    return bars


def _swings(bars, k):
    """分形摆动点:k 根确认。返回 [(idx, kind, px)] kind in {'H','L'}。"""
    n = len(bars)
    out = []
    for i in range(k, n - k):
        hi, lo = bars[i]["high"], bars[i]["low"]
        if all(hi >= bars[j]["high"] for j in range(i - k, i + k + 1)):
            out.append((i, "H", hi))
        if all(lo <= bars[j]["low"] for j in range(i - k, i + k + 1)):
            out.append((i, "L", lo))
    # 端点:首根若是前 k+1 根极值也算摆动点(给 detect 起点)
    if n > k:
        h0 = max(b["high"] for b in bars[: k + 1])
        l0 = min(b["low"] for b in bars[: k + 1])
        if bars[0]["high"] >= h0:
            out.append((0, "H", bars[0]["high"]))
        if bars[0]["low"] <= l0:
            out.append((0, "L", bars[0]["low"]))
    out.sort(key=lambda x: x[0])
    # 强制高低交替:连续同类只留极值
    alt = []
    for idx, kind, px in out:
        if alt and alt[-1][1] == kind:
            if (kind == "H" and px > alt[-1][2]) or (kind == "L" and px < alt[-1][2]):
                alt[-1] = (idx, kind, px)
        else:
            alt.append((idx, kind, px))
    return alt


def detect_legs(bars, cfg=None, lookback=None):
    """摆动高低点切分出最近的段。返回 [leg...] 由老到新,每段:
    {dir,start,end,hours,points,slope,start_px,end_px,high,low,provisional}。
    点数/斜率按摆动极值价算(高点high/低点low),与用户盘感口径一致。
    最后一根 bar 视为 provisional 段终点(未确认摆动点,按收盘价)。"""
    cfg = cfg or load_cfg()
    k = int(cfg["swing_k"])
    lb = lookback or int(cfg["lookback_hours"])
    bars = bars[-lb:] if len(bars) > lb else list(bars)
    if len(bars) < k * 2 + 3:
        return []
    sw = _swings(bars, k)
    if len(sw) < 2:
        return []

    def _mk(i1, px1, i2, px2, provisional):
        seg = bars[i1: i2 + 1]
        hours = max(i2 - i1, 1)  # 小时K:bar 间隔即小时数
        points = abs(px2 - px1)
        return {
            "dir": "up" if px2 >= px1 else "down",
            "start": bars[i1]["time"], "end": bars[i2]["time"],
            "hours": float(hours), "points": round(points, 2),
            "slope": round(points / hours, 2),
            "start_px": px1, "end_px": px2,
            "high": max(b["high"] for b in seg), "low": min(b["low"] for b in seg),
            "provisional": provisional,
        }

    legs = []
    for (i1, _k1, p1), (i2, _k2, p2) in zip(sw, sw[1:]):
        legs.append(_mk(i1, p1, i2, p2, False))
    # 最后一个确认摆动点 -> 最新收盘:provisional 段
    li, _lk, lp = sw[-1]
    if li < len(bars) - 1:
        last_close = bars[-1]["close"]
        if abs(last_close - lp) > 0:
            legs.append(_mk(li, lp, len(bars) - 1, last_close, True))
    return legs[-6:]  # 最多保留最近 6 段


def _weak_pair(dn, up, cfg):
    """[下跌,反弹] 是否构成弱反弹(情绪消耗)。"""
    if dn["dir"] != "down" or up["dir"] != "up":
        return False
    if dn["hours"] <= 0 or dn["points"] <= 0:
        return False
    tr = up["hours"] / dn["hours"]
    rr = up["points"] / dn["points"]
    return tr > cfg["weak_time_ratio"] and rr < cfg["weak_retrace"]


def analyze(bars, cfg=None):
    """主入口。返回 legs/time_ratio/retrace_ratio/judgments/summary/strategy_version。"""
    cfg = cfg or load_cfg()
    legs = detect_legs(bars, cfg)
    res = {"legs": legs, "time_ratio": None, "retrace_ratio": None,
           "judgments": {"weak_rebound": False, "steady_up": False,
                         "steady_down": False, "regime_switch": False},
           "summary": "周期结构：数据不足", "strategy_version": cfg.get("_strategy_version", "?")}
    if len(legs) < 2:
        return res
    a, b = legs[-2], legs[-1]  # a=前段,b=最新段
    tol = cfg["break_tol"]

    # ---- 弱反弹(情绪消耗):[下跌,反弹],反弹耗时更长但修复更少 ----
    if _weak_pair(a, b, cfg):
        res["judgments"]["weak_rebound"] = True
        res["time_ratio"] = round(b["hours"] / a["hours"], 2)
        res["retrace_ratio"] = round(b["points"] / a["points"], 3)

    # ---- 稳态上升:[上涨,回踩],涨得陡、回踩不破前低 ----
    if a["dir"] == "up" and b["dir"] == "down":
        if a["slope"] > b["slope"] * cfg["steady_slope_mult"] and \
                b["low"] >= a["low"] * (1 - tol):
            res["judgments"]["steady_up"] = True

    # ---- 稳态下跌:[下跌,反弹],跌得陡、反弹不破前高 ----
    if a["dir"] == "down" and b["dir"] == "up":
        if a["slope"] > b["slope"] * cfg["steady_slope_mult"] and \
                b["high"] <= a["high"] * (1 + tol):
            res["judgments"]["steady_down"] = True

    # ---- 结构切换:最近出现过弱反弹形态,随后价格突破前高(情绪耗尽后选择向上) ----
    # 只看最近 switch_window 小时内的形态,过期不算(牛市里早晚都会破前高)
    cur_close = legs[-1]["end_px"]
    try:
        cur_t = datetime.datetime.strptime(legs[-1]["end"], "%Y-%m-%d %H:%M")
    except Exception:
        cur_t = None
    win = datetime.timedelta(hours=cfg.get("switch_window", 24))
    for dn, up in zip(legs, legs[1:]):
        if up.get("provisional"):
            continue  # 只看已走完的形态
        if not _weak_pair(dn, up, cfg):
            continue
        if cur_t:
            try:
                up_t = datetime.datetime.strptime(up["end"], "%Y-%m-%d %H:%M")
            except Exception:
                continue
            if cur_t - up_t > win:
                continue  # 形态过期
        if cur_close > dn["high"] * (1 + tol):
            res["judgments"]["regime_switch"] = True
            break
    # 加速变体:最新段为短时急拉,斜率超过前跌段×accel_mult 且 3 小时内修复超 38.2%
    # (真正的 V 型选择,不是死猫跳;与 weak_rebound 互斥:急拉耗时短)
    if not res["judgments"]["regime_switch"] and b["dir"] == "up" and a["dir"] == "down":
        if b["hours"] <= cfg["accel_window"] and b["slope"] > a["slope"] * cfg["accel_mult"]:
            if not _weak_pair(a, b, cfg) and b["points"] / a["points"] > cfg["weak_retrace"]:
                res["judgments"]["regime_switch"] = True

    # ---- 一句话摘要 ----
    j = res["judgments"]
    def _lname(leg, prev):
        if leg["dir"] == "up":
            return "反弹" if prev is not None and prev["dir"] == "down" else "上涨"
        return "回踩" if prev is not None and prev["dir"] == "up" else "下跌"
    seg_s = "%s%gh/%s%gh" % (_lname(a, legs[-3] if len(legs) >= 3 else None),
                             a["hours"], _lname(b, a), b["hours"])
    if j["regime_switch"]:
        res["summary"] = "周期结构：%s，结构切换·情绪耗尽后选择向上" % seg_s
    elif j["weak_rebound"]:
        res["summary"] = "周期结构：%s，修复%.0f%%，弱反弹·情绪消耗中" % (
            seg_s, res["retrace_ratio"] * 100)
    elif j["steady_down"]:
        res["summary"] = "周期结构：%s，稳态下跌·反弹不破前高" % seg_s
    elif j["steady_up"]:
        res["summary"] = "周期结构：%s，稳态上升·回踩不破前低" % seg_s
    else:
        res["summary"] = "周期结构：%s，方向不明" % seg_s
    return res


def expect_check(bars, side, cfg=None, now=None):
    """P30 不及预期时间窗(2026-10-03 用户拍板:P23"买入必须带预期"的周期维度扩展)。

    持仓方向的反向段(空单的反弹/多单的回调)时长超过原段 expect_ratio_warn 倍→预警;
    超过 expect_ratio_exit 倍→出局。方向自适应。
    原段=最近窗口内点数最大的持仓方向段(主要趋势段,不被反弹中的小回踩带偏);
    反向段时长=原段结束点 -> now(墙钟)。point-in-time(摆动检测只用已收盘 bar)。
    返回 {time_ratio, expect_warn, expect_dead, orig_leg, counter_hours,
           strategy_version}。
    """
    cfg = cfg or load_cfg()
    bars = drop_forming(list(bars))
    if now is None:
        now_t = datetime.datetime.now(datetime.timezone.utc)
    else:
        now_t = now if now.tzinfo else now.replace(tzinfo=datetime.timezone.utc)
        # point-in-time:只看 now 之前(含)的 bar,调用方传全量也不偷看未来
        now_s = now_t.strftime("%Y-%m-%d %H:%M")
        bars = [b for b in bars if str(b.get("time", ""))[:16] <= now_s]
    res = {"time_ratio": None, "expect_warn": False, "expect_dead": False,
           "orig_leg": None, "counter_leg": None, "counter_hours": None,
           "strategy_version": cfg.get("_strategy_version", "?")}
    legs = detect_legs(bars, cfg)
    if len(legs) < 2:
        return res
    orig_dir = "down" if side == "short" else "up"
    cands = [lg for lg in legs if lg["dir"] == orig_dir and lg["points"] > 0]
    if not cands:
        return res
    orig = max(cands, key=lambda lg: lg["points"])
    oi = next(i for i, lg in enumerate(legs) if lg is orig)
    if oi == len(legs) - 1:
        return res  # 原段就是最新段,无活跃反向段
    if orig["hours"] <= 0:
        return res
    try:
        start_t = datetime.datetime.strptime(
            orig["end"], "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return res
    live_h = max((now_t - start_t).total_seconds() / 3600.0, 0.0)
    ratio = live_h / orig["hours"]
    res.update({
        "time_ratio": round(ratio, 2),
        "counter_hours": round(live_h, 1),
        "orig_leg": orig,
        "expect_warn": ratio >= cfg["expect_ratio_warn"],
        "expect_dead": ratio >= cfg["expect_ratio_exit"],
    })
    return res


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, SVC)
    import bars_crypto
    code = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    hs = drop_forming(bars_crypto.intraday_hourly(code, n=96))
    a = analyze(hs)
    print(json.dumps(a, ensure_ascii=False, indent=1)[:2000])
