#!/usr/bin/env python3
"""T+1 模拟交易引擎。

买入 (--signal, 10:05 跑): 关注池 + 早盘情绪确认 -> paper 买入(按现价)
  条件(strategy.yaml v1): 池分>=8, 市场情绪>-40, ch_pos<80, 非诱多, 最多5只同持
持有: T+1 锁定,买入日不可卖
卖出 (--settle 检查, 15:40 跑): +10%止盈 / -6%止损 / 持有5日 / 收盘结算
账本: logs/paper_ledger.json {positions:[], closed:[], cash}
复盘: --settle 输出胜率/盈亏比/归因;每周由 LLM 做参数迭代(只改 strategy.yaml 升版本)

用法:
  python3 paper_trade.py --signal [--dry-run]   # 早盘买入信号
  python3 paper_trade.py --settle [--dry-run]   # 收盘结算+卖出+复盘
"""
import glob
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

BJ = ZoneInfo("Asia/Shanghai")
SVC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SVC)
LEDGER = os.path.join(SVC, "logs", "paper_ledger.json")
LEDGER_US = os.path.join(SVC, "logs", "paper_ledger_us.json")
LEDGER_CRYPTO = os.path.join(SVC, "logs", "paper_ledger_crypto.json")
LEDGER_CRYPTO_SHORT = os.path.join(SVC, "logs", "paper_ledger_crypto_short.json")
# 影子实验仓(2026-10-03 v1.5,用户批准):独立账本,单变量实验(只放松入场阈值),主账本不动
LEDGER_CRYPTO_EXP = os.path.join(SVC, "logs", "paper_ledger_crypto_exp.json")
LEDGER_CRYPTO_EXP_SHORT = os.path.join(SVC, "logs", "paper_ledger_crypto_exp_short.json")
# near-miss 样本:主 sleeve 被阈值拦下的 [exp阈值,主阈值) 候选,append-only,供周一复盘
NEAR_MISS_FILE = os.path.join(SVC, "logs", "near_miss_crypto.jsonl")

# 市场上下文:CN=A股(人民币,T+1按A股日历);US=美股(美元,T+1按美股日历,用户定2026-09-29);
# CRYPTO=数字货币(美元,T+0,24×7,"日"=UTC自然日,用户定2026-10-01)
MARKET = "CN"
# 方向:long=做多(默认);short=永续做空镜像(仅 MARKET=CRYPTO 可用,独立账本,不碰多头)
SIDE = "long"
# 仓位系列:main=主模拟仓(默认);exp=影子实验仓(仅 MARKET=CRYPTO 可用,独立账本/独立kill/独立决策日志)
SLEEVE = "main"
LOT_SIZE = {"CN": 100, "US": 1, "CRYPTO": 0.000001}  # 币圈按金额取整到1e-6
CURR = {"CN": "¥", "US": "$", "CRYPTO": "$"}
FEE_RATE = {"CN": 0.0, "US": 0.0, "CRYPTO": 0.001}  # 币圈现货0.1%/边;股票暂不计费(行为不变)


def _cash_out(lg, gross):
    """买入付钱(含手续费)。CN/US费率为0,行为不变。"""
    lg["cash"] = lg["cash"] - gross * (1 + FEE_RATE[MARKET])


def _cash_in(lg, gross):
    """卖出收钱(扣手续费)。CN/US费率为0,行为不变。"""
    lg["cash"] = lg["cash"] + gross * (1 - FEE_RATE[MARKET])


def _net_pnl(buy_px, sell_px, shares):
    """手续费后净pnl。CN/US费率为0,与原来 (sell-buy)*shares 完全一致。"""
    f = FEE_RATE[MARKET]
    return (sell_px * (1 - f) - buy_px * (1 + f)) * shares


def _ledger_path():
    if MARKET == "US":
        return LEDGER_US
    if MARKET == "CRYPTO":
        if SLEEVE == "exp":
            return LEDGER_CRYPTO_EXP_SHORT if SIDE == "short" else LEDGER_CRYPTO_EXP
        return LEDGER_CRYPTO_SHORT if SIDE == "short" else LEDGER_CRYPTO
    return LEDGER


def _today():
    """账本日期:CN用北京时间,US用美东日期(美股交易日按美东算),CRYPTO用UTC日期。"""
    if MARKET == "US":
        from trading_calendar import today_str
        return today_str("US")
    if MARKET == "CRYPTO":
        from trading_calendar import today_str
        return today_str("CRYPTO")
    return datetime.now(BJ).strftime("%Y-%m-%d")


def _lot_shares(amt, price):
    """按市场最小单位取整股数。"""
    lot = LOT_SIZE[MARKET]
    n = int(amt / price / lot) * lot
    return n


def load_cfg():
    import yaml
    cfg = yaml.safe_load(open(os.path.join(SVC, "strategy.yaml")))
    if MARKET == "US":
        # 美股独立核算:us_ 开头参数覆盖在通用参数之上(同一套逻辑,只差异参数不同)。
        # 感知规则(P1-P21)复用同一套。
        for k in ("buy", "sell", "add", "account"):
            uk = "us_" + k
            if uk in cfg:
                merged = dict(cfg.get(k) or {})
                merged.update(cfg[uk] or {})
                cfg[k] = merged
    if MARKET == "CRYPTO":
        # 数字货币独立核算:crypto_ 开头参数覆盖通用参数。策略与股票版同源但独立版本化,
        # 在币圈验证有效前不反向影响股票参数(2026-10-01用户:股票策略在币圈可能失效,先验证)。
        for k in ("buy", "sell", "add", "account"):
            ck = "crypto_" + k
            if ck in cfg:
                merged = dict(cfg.get(k) or {})
                merged.update(cfg[ck] or {})
                cfg[k] = merged
    if MARKET == "CRYPTO" and SLEEVE == "exp":
        # 影子实验仓(v1.5):单变量实验,只覆盖入场阈值,其余与主完全一致。
        # 多头 cfg["buy"]["min_pool_score"],空头 cfg["crypto_short"]["entry"]["s_pool_score"]。
        exp = cfg.get("crypto_exp") or {}
        th = exp.get("min_pool_score")
        if th is not None:
            cfg["buy"]["min_pool_score"] = th
            cfg["crypto_short"]["entry"]["s_pool_score"] = th
    return cfg


def load_ledger():
    p = _ledger_path()
    if os.path.exists(p):
        lg = json.load(open(p))
        if MARKET == "CRYPTO" and SIDE == "short":
            return _normalize_short_ledger(lg)
        if MARKET == "CRYPTO" and SLEEVE == "exp":
            # 影子仓独立 kill,记账本内,不碰 logs/kill_switch.json
            lg.setdefault("exp_kill", {"armed": False, "reason": "", "at": ""})
        return lg
    init_cash = 100000.0  # CN=沿用旧账本;US/CRYPTO=10万美金(用户定)
    if MARKET == "CRYPTO" and SIDE == "short":
        return _normalize_short_ledger({})
    lg = {"cash": init_cash, "positions": [], "closed": [],
          "version": "v1", "market": MARKET,
          "currency": "USD" if MARKET in ("US", "CRYPTO") else "CNY"}
    if MARKET == "CRYPTO" and SLEEVE == "exp":
        lg["exp_kill"] = {"armed": False, "reason": "", "at": ""}
        lg["sleeve"] = "exp"
    return lg


def exp_kill_armed(lg):
    """影子仓独立 kill 状态(记账本内)。"""
    return bool((lg.get("exp_kill") or {}).get("armed"))


def _arm_exp_kill(lg, reason):
    lg["exp_kill"] = {"armed": True, "reason": reason,
                      "at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S")}


def _normalize_short_ledger(lg):
    """空头账本读-改-写合并:保留已有持仓/已平仓/资金,绝不重新初始化清空。
    兼容已落地的 account.margin_balance 口径;缺失字段补默认值。"""
    lg = lg or {}
    lg["market"] = "CRYPTO"
    lg["side"] = "short"
    lg.setdefault("currency", "USD")
    lg.setdefault("positions", [])
    lg.setdefault("closed", [])
    lg.setdefault("short_kill", {"armed": False, "reason": "", "at": ""})
    lg.setdefault("day_stats", {"date": "", "margin_base": 0.0, "realized": 0.0})
    acct = lg.setdefault("account", {})
    acct.setdefault("currency", "USD")
    acct.setdefault("leverage", 10)
    if "margin_balance" not in acct and "cash" not in lg:
        acct["margin_balance"] = 100000.0
    for p in lg["positions"]:
        p.setdefault("side", "short")
        p.setdefault("name", p.get("code"))
        if not p.get("qty") and p.get("entry"):
            p["qty"] = (p["notional"] / p["entry"]) if p.get("notional") else 0.0
        p.setdefault("partial_tp_done", False)
        p.setdefault("fee_open_paid", False)
        ot = p.get("open_time") or ""
        p.setdefault("open_date", ot[:10])
        p.setdefault("strategy_version", lg.get("strategy_version", "v1.4"))
    return lg


def save_ledger(lg):
    json.dump(lg, open(_ledger_path(), "w"), ensure_ascii=False, indent=1)


def _lock_until(today_s):
    """T+1锁止日:CRYPTO为T+0,返回当日(即时可卖,经 sellable_shares 验证)。
    原名 _next_td,2026-10-01 币圈接入时改名以承载 T+0 语义。"""
    if MARKET == "CRYPTO":
        return today_s
    try:
        from trading_calendar import next_trading_day
        return next_trading_day(today_s, market=MARKET)
    except Exception:
        return today_s


def sellable_shares(p, today):
    """T+1可卖份额:锁定期未到则扣减锁定数。locked_until缺失的老数据按旧逻辑。"""
    locked = p.get("locked", 0)
    until = p.get("locked_until")
    if locked and until and until > today:
        return p["shares"] - locked
    if locked and not until:
        return p["shares"] - locked  # 老数据:保守起见仍扣减
    return p["shares"]


def release_due_locks(lg, today):
    """只释放已到期的锁(locked_until<=today),settle跑多次也不会误解锁当日买入。"""
    for p in lg.get("positions", []):
        until = p.get("locked_until")
        if p.get("locked") and (not until or until <= today):
            p["locked"] = 0


def log_decision(date, entry, factors=None):
    """决策日志:每笔为何买/卖/不做都记一句话,供周复盘归因学习。
    美股独立文件 decisions_us_<date>.json,与A股隔离。
    factors:类型化因子dict(2026-10-01统一决策门改造),记录当时各P门原值,
    如 {"p8_vwap":true,"p25":false,"p26":58,"pool_score":11.0},
    供复盘时按因子拆解归因(统一门只汇总,依据全保留可查)。
    strategy_version 自动打戳,保证回溯时知道当时用的哪版规则。"""
    if MARKET == "US":
        fn = "decisions_us_%s.json" % date
    elif MARKET == "CRYPTO":
        # 影子实验仓独立决策日志,全程打标 sleeve:"exp"
        if SIDE == "short":
            fn = ("decisions_crypto_exp_short_%s.json" if SLEEVE == "exp"
                  else "decisions_crypto_short_%s.json") % date
        else:
            fn = ("decisions_crypto_exp_%s.json" if SLEEVE == "exp"
                  else "decisions_crypto_%s.json") % date
    else:
        fn = "decisions_%s.json" % date
    p = os.path.join(SVC, "logs", fn)
    try:
        d = json.load(open(p))
    except Exception:
        d = {"date": date, "decisions": []}
    entry["at"] = datetime.now(BJ).strftime("%H:%M:%S")
    entry.setdefault("sleeve", SLEEVE)
    try:
        entry.setdefault("strategy_version", load_cfg().get("version"))
    except Exception:
        pass
    if factors:
        entry["factors"] = factors
    if isinstance(d, dict):
        d.setdefault("decisions", []).append(entry)
    elif isinstance(d, list):
        d.append(entry)  # 兼容旧格式:顶层list
    else:
        d = {"date": date, "decisions": [entry]}
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)


def _near_miss_band(score, main_th, exp_th):
    """near-miss 判定:分数在 [exp阈值, 主阈值) 之间。主 sleeve 被阈值拦下、exp 会开仓的候选。"""
    try:
        return exp_th <= float(score) < float(main_th)
    except Exception:
        return False


def record_near_miss(code, side, score, price, reason, path=None):
    """near-miss 样本化(2026-10-03 v1.5,用户要求):主 sleeve 信号中 pool 分数在
    [exp阈值,主阈值) 被阈值拦下的候选,append-only 写入 near_miss_crypto.jsonl,
    供周一 paper-review 复盘"拦掉的该不该买"。只记录不交易;dry-run 不写。"""
    line = {"date": _today(), "coin": code, "side": side, "score": score,
            "entry_price": price, "reason": reason, "sleeve": "main",
            "strategy_version": load_cfg().get("version")}
    with open(path or NEAR_MISS_FILE, "a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


def latest_regime():
    date_s = _today()
    p = os.path.join(SVC, "logs", "market_regime_%s.json" % date_s)
    if os.path.exists(p):
        return json.load(open(p))
    return {}


def latest_pool():
    cands = sorted(glob.glob(os.path.join(SVC, "logs", "watchpool_*.json")), reverse=True)
    return json.load(open(cands[0])) if cands else None


def get_pool():
    """统一取池:CN=watchpool文件;US=us_pool(无则现场构建,读本地日K);CRYPTO=crypto_pool现场打分。"""
    if MARKET == "US":
        from trading_calendar import today_str
        p = os.path.join(SVC, "logs", "us_pool_%s.json" % today_str("US"))
        if os.path.exists(p):
            return json.load(open(p))
        import us_pool
        return us_pool.build()
    if MARKET == "CRYPTO":
        import crypto_pool
        if SIDE == "short":
            return crypto_pool.build_short()
        return crypto_pool.build()
    return latest_pool()


def morning_us():
    """美股早盘识别:与 A 股同一套 morning_action_from_bars(诱多/诱空/量价齐升/VWAP)。
    数据:Yahoo 5分钟K;today_s 用美东日期。"""
    from trading_calendar import today_str
    import bars_us
    from sentiment import morning_action_from_bars
    et_day = today_str("US")
    out = {}
    for s in get_us_universe():
        try:
            bars = bars_us.yahoo_intraday(s)
            m = morning_action_from_bars(s, bars, today_s=et_day)
            out[s] = m
        except Exception as e:
            out[s] = {"code": s, "error": "yahoo_5m_fail: %s" % str(e)[:60]}
        time.sleep(1)
    return out


def get_morning():
    """统一取早盘:CN=sentiment早盘文件;US=现场算(Yahoo 5m);CRYPTO=现场算(Kraken 1h)。"""
    if MARKET == "US":
        return morning_us()
    if MARKET == "CRYPTO":
        return morning_crypto()
    return latest_morning()


def get_crypto_universe():
    import json
    try:
        import crypto_universe
        return crypto_universe.universe_codes()
    except Exception:
        return json.load(open(os.path.join(SVC, "crypto_watchlist.json")))


def morning_crypto():
    """币圈"早盘"识别:无开盘,用 UTC 当日 00:00 起的小时K复用 morning_action_from_bars 纯函数。
    日开盘价=UTC 0点开盘;需要>=3根小时K(UTC 03:00后),否则 morning_bars_not_ready -> fail-closed。
    vwap_5min 字段实际为小时级VWAP,P8四条件语义不变(站上/量价齐升/偏离/多日结构)。"""
    from trading_calendar import today_str
    import bars_crypto
    from sentiment import morning_action_from_bars
    utc_day = today_str("CRYPTO")
    out = {}
    for s in get_crypto_universe():
        try:
            bars = bars_crypto.intraday_hourly(s, 40)
            tb = [b for b in bars if b["time"][:10] == utc_day]
            if len(tb) < 3:
                out[s] = {"code": s, "error": "morning_bars_not_ready", "n": len(tb)}
                continue
            m = morning_action_from_bars(s, bars, today_s=utc_day)
            out[s] = m
        except Exception as e:
            out[s] = {"code": s, "error": "kraken_1h_fail: %s" % str(e)[:60]}
        time.sleep(1)
    return out


def market_us():
    """美股市场情绪(-100~+100,与 A 股同口径,只做否决门,不制造买点):
    SPY/QQQ 日涨跌 + VIX。数据缺失 -> fail-closed(无情绪分不新开仓)。"""
    import bars_us
    def day_chg(sym):
        try:
            d = bars_us.yahoo_daily2(sym)
            if len(d) >= 2 and d[-2]["close"]:
                return (d[-1]["close"] / d[-2]["close"] - 1) * 100
        except Exception:
            pass
        return None
    spy, qqq, vix = day_chg("SPY"), day_chg("QQQ"), None
    try:
        vd = bars_us.yahoo_daily2("^VIX")
        vix = vd[-1]["close"] if vd else None
    except Exception:
        pass
    if spy is None or qqq is None:
        return {"score": None, "error": "us_sentiment_no_data",
                "water": {}, "risk_appetite": {}, "dead_day": False}
    s = (spy + qqq) / 2 * 25
    if vix is not None:
        if vix >= 30:
            s -= 25
        elif vix >= 25:
            s -= 15
        elif vix < 15:
            s += 10
    s = max(-100, min(100, s))
    return {"score": round(s, 1), "spy_chg": round(spy, 2), "qqq_chg": round(qqq, 2),
            "vix": round(vix, 1) if vix else None,
            "water": {}, "risk_appetite": {}, "dead_day": False}


def market_crypto():
    """币圈市场情绪(-100~+100,同口径只做否决门):
    BTC 24h涨跌×20 + 6币涨跌家数修正(全涨+10/全跌-10)。数据缺失 -> fail-closed。
    (用户2026-10-01:币圈对全球流动性感知强,此处同时是跨市场情绪点;
    第二阶段把 BTC 24h 涨跌影子接入 A股盘前情绪。)"""
    import bars_crypto
    try:
        px = bars_crypto.realtime_all()
        chgs = []
        for code in get_crypto_universe():
            bars = bars_crypto.get_bars(code)
            if len(bars) < 2 or code not in px:
                continue
            prev = bars[-1]["close"]
            if prev:
                chgs.append((px[code] / prev - 1) * 100)
        if not chgs:
            raise RuntimeError("no bars")
        btc_chg = chgs[0]
        s = btc_chg * 20
        up = sum(1 for c in chgs if c > 0)
        if up == len(chgs):
            s += 10
        elif up == 0:
            s -= 10
        s = max(-100, min(100, s))
        return {"score": round(s, 1), "btc_24h_chg": round(btc_chg, 2),
                "breadth_up": up, "breadth_n": len(chgs),
                "water": {}, "risk_appetite": {}, "dead_day": False}
    except Exception as e:
        return {"score": None, "error": "crypto_sentiment_no_data: %s" % str(e)[:60],
                "water": {}, "risk_appetite": {}, "dead_day": False}


def get_market():
    """统一取市场情绪:CN=盘前文件;US=SPY/QQQ/VIX现场算;CRYPTO=BTC/宽度现场算。"""
    if MARKET == "US":
        return market_us()
    if MARKET == "CRYPTO":
        return market_crypto()
    return latest_premarket()


def latest_morning():
    date_s = _today()
    p = os.path.join(SVC, "logs", "sentiment_%s_morning.json" % date_s)
    if os.path.exists(p):
        return {r["code"]: r for r in json.load(open(p)).get("stocks", [])}
    return {}


def latest_premarket():
    date_s = _today()
    p = os.path.join(SVC, "logs", "sentiment_%s_premarket.json" % date_s)
    if os.path.exists(p):
        return json.load(open(p)).get("market", {})
    return {}


def latest_intraday():
    """最新一条盘中情绪快照(无则返回{})"""
    date_s = _today()
    p = os.path.join(SVC, "logs", "sentiment_intraday_%s.jsonl" % date_s)
    if not os.path.exists(p):
        return {}
    try:
        lines = [l for l in open(p).read().splitlines() if l.strip()]
        return json.loads(lines[-1]) if lines else {}
    except Exception:
        return {}


def effective_dead_day(mkt):
    """P5盘中化:盘前dead_day + 盘中情绪仍差(<-15)才算真死;
    盘中情绪转暖(>=-15)则解除,让资金不闲置。"""
    if not mkt.get("dead_day"):
        return False
    intra = latest_intraday()
    if intra and intra.get("score") is not None and intra["score"] >= -15:
        print("盘前dead_day但盘中情绪%.1f转暖,门禁解除" % intra["score"])
        return False
    return True


def realtime_price(code):
    """实时价兜底:CN走后端 quotes,US走 sina gb_/腾讯 us(直连可用),CRYPTO走 Kraken ticker。"""
    if MARKET == "US":
        return us_realtime_price(code)
    if MARKET == "CRYPTO":
        try:
            import bars_crypto
            return bars_crypto.realtime(code)
        except Exception:
            return 0
    import daily_review as dr
    api_code = ("sh" if code[0] in "69" else "sz") + code
    try:
        d = dr.api("/api/v1/quotes/realtime?symbols=%s" % api_code, timeout=15)["data"]
        if isinstance(d, list):  # 后端返回 list[{"symbol","price",...}]
            q = d[0] if d else {}
        else:
            q = d.get(api_code) or d.get(code) or {}
        return float(q.get("price") or q.get("close") or 0)
    except Exception:
        return 0


def us_realtime_price(code):
    """美股实时价:sina gb_ 优先,腾讯 us 兜底。盘后 f[1] 即收盘价。"""
    import re
    import urllib.request
    sym = code.upper()
    try:
        req = urllib.request.Request(
            "http://hq.sinajs.cn/?format=text&list=gb_" + sym.lower(),
            headers={"User-Agent": "Mozilla/5.0",
                     "Referer": "https://finance.sina.com.cn/"})
        t = urllib.request.urlopen(req, timeout=15).read().decode("gbk", "ignore")
        m = re.search(r"gb_%s=[^,]*,([\d.]+)" % sym.lower(), t, re.I)
        if m and float(m.group(1)) > 0:
            return float(m.group(1))
    except Exception:
        pass
    try:
        req = urllib.request.Request("https://qt.gtimg.cn/q=us" + sym,
                                     headers={"User-Agent": "Mozilla/5.0"})
        t = urllib.request.urlopen(req, timeout=15).read().decode("gbk", "ignore")
        m = re.search(r'v_us%s="[^~]*~[^~]*~[^~]*~([\d.]+)' % sym, t)
        if m and float(m.group(1)) > 0:
            return float(m.group(1))
    except Exception:
        pass
    return 0


def mtag():
    tag = "[实验]" if SLEEVE == "exp" else ""
    if MARKET == "US":
        return tag + "(US)"
    if MARKET == "CRYPTO" and SIDE == "short":
        return tag + "(CRYPTO空头)"
    return tag


def market_brief(side=None):
    """定时结算推送用盘面简报(纯展示:只读本地底座+realtime,不写账本不交易)。
    200~350字,对齐策略语言(P25/池分/镜像单/触发点)。数据不可验证写"数据暂不可用",不编造。
    CN 返回 ""(A股盘后另有 daily_review 复盘,不在此叠加)。"""
    sd = side or SIDE
    try:
        if MARKET == "CRYPTO":
            return _brief_crypto(sd)
        if MARKET == "US":
            return _brief_us()
    except Exception as e:
        return "盘面简报生成失败:%s" % str(e)[:60]
    return ""


def _fmt_px(px):
    try:
        from crypto_util import fmt_price
        return fmt_price(px)
    except Exception:
        return round(float(px), 2) if px else 0


def _brief_crypto(side):
    import bars_crypto
    import crypto_pool
    try:
        bars = bars_crypto.get_bars("BTC")
    except Exception:
        bars = []
    if len(bars) < 25:
        return "【BTC盘面】数据暂不可用"
    last, prev = bars[-1], bars[-2]
    chg = (last["close"] / prev["close"] - 1) * 100 if prev["close"] else 0.0
    try:
        px = float(bars_crypto.realtime("BTC") or 0)
    except Exception:
        px = 0.0
    hi = lo = None
    try:
        hs = bars_crypto.intraday_hourly("BTC", n=24)
        hi, lo = max(h["high"] for h in hs), min(h["low"] for h in hs)
    except Exception:
        pass

    def vwap_n(n):
        seg = bars[-n:]
        v = sum(b["volume"] for b in seg)
        return sum(b["amount"] for b in seg) / v if v else 0
    v1, v3, v5 = vwap_n(1), vwap_n(3), vwap_n(5)
    ma20 = sum(b["close"] for b in bars[-20:]) / 20
    p25l = v1 > v3 > v5 and last["close"] >= ma20
    p25s = v1 < v3 < v5 and last["close"] < ma20
    trend = "P25多头" if p25l else ("P25空头" if p25s else "震荡")

    lt = st = None
    try:
        lp = crypto_pool.build()["pool"]
        if lp:
            lt = (lp[0]["code"], lp[0]["score"])
    except Exception:
        pass
    try:
        sp = crypto_pool.build_short()["pool"]
        if sp:
            st = (sp[0]["code"], sp[0]["score"])
    except Exception:
        pass

    mir = ""
    poss, p, mret = [], None, 0.0
    try:
        lg = json.load(open(os.path.join(SVC, "logs", "paper_ledger_crypto_short.json")))
        poss = [p for p in lg.get("positions", []) if p.get("side") == "short"]
        if poss:
            p = poss[0]
            mk = px or p.get("mark") or p["entry"]
            mret = (p["entry"] - mk) / p["entry"] * p.get("leverage", 10) * 100
            mir = "空头镜像单：%s空@%s，现%s，保证金浮盈%+.1f%%" % (
                p["code"], _fmt_px(p["entry"]), _fmt_px(mk), mret)
            if p.get("stop_loss"):
                mir += "，距止损%s点" % int(p["stop_loss"] - mk)
            if p.get("take_profit"):
                mir += "/距止盈%s点" % int(mk - p["take_profit"])
            mir += "。"
    except Exception:
        pass

    px_s = _fmt_px(px) if px else "暂不可用"
    hl_s = ("最高%s/最低%s" % (_fmt_px(hi), _fmt_px(lo))) if hi else "高低点暂不可用"
    lt_s = ("多头池最高%s %s分" % lt) if lt else "多头池暂不可用"
    st_s = ("空头池最高%s %s分" % st) if st else "空头池暂不可用"
    # 结构一句话
    if p25l and lt and lt[1] < 8:
        struct = "日线多头但%s池分%s<8不开多" % (lt[0], lt[1])
    elif p25s and st and st[1] >= 8:
        struct = "日线空头，%s池分%s达开空线" % (st[0], st[1])
    elif p25s:
        struct = "日线空头但空头池分不足"
    else:
        struct = "趋势不明，等P25方向"
    if mir and mret < 0:
        struct += "；镜像空单浮亏中"
    cyc = ""
    try:
        import cycle_structure
        chs = cycle_structure.drop_forming(bars_crypto.intraday_hourly("BTC", n=96))
        if len(chs) >= 12:
            cyc = cycle_structure.analyze(chs).get("summary", "")
    except Exception:
        cyc = ""
    if not cyc:
        cyc = "周期结构：暂不可用"
    nxt = []
    if lt and lt[1] < 8:
        nxt.append("%s池分上8开多" % lt[0])
    if p and p.get("take_profit"):
        nxt.append("跌破%s空头止盈" % _fmt_px(p["take_profit"]))
    if p and p.get("stop_loss"):
        nxt.append("涨上%s空头止损" % _fmt_px(p["stop_loss"]))
    out = ("【BTC盘面】现%s（24h %+.2f%%），24h%s。%s（1日VWAP>3日>5日，收盘%sMA20）。"
           "%s；%s。%s结构：%s。%s。下一步：%s。" % (
               px_s, chg, hl_s, trend,
               "站上" if last["close"] >= ma20 else "跌破",
               lt_s, st_s, mir, struct, cyc, "；".join(nxt) if nxt else "观望"))
    return out


def _brief_us():
    import re
    import urllib.request
    # 指数:新浪 gb_ 直连(只读当前价与涨跌幅,超时即"暂不可用")
    def idx(sym):
        try:
            req = urllib.request.Request(
                "http://hq.sinajs.cn/?format=text&list=gb_" + sym,
                headers={"User-Agent": "Mozilla/5.0",
                         "Referer": "https://finance.sina.com.cn/"})
            t = urllib.request.urlopen(req, timeout=8).read().decode("gbk", "ignore")
            m = re.search(r'gb_%s=[^,]*,([\d.]+),(-?[\d.]+)' % sym, t)
            if m:
                return float(m.group(1)), float(m.group(2))
        except Exception:
            pass
        return None, None
    spy, spy_c = idx("spy")
    qqq, qqq_c = idx("qqq")
    vix, _ = idx("vix")
    idx_s = "SPY %s%s，QQQ %s%s，VIX %s" % (
        round(spy, 1) if spy else "暂不可用",
        ("(%+.2f%%)" % spy_c) if spy_c is not None else "",
        round(qqq, 1) if qqq else "暂不可用",
        ("(%+.2f%%)" % qqq_c) if qqq_c is not None else "",
        round(vix, 1) if vix else "暂不可用")
    # 当日信号摘要:decisions_us_<date>.json 前3条 why
    skips = []
    try:
        d = json.load(open(os.path.join(SVC, "logs", "decisions_us_%s.json" % _today())))
        for e in d.get("decisions", [])[:3]:
            w = e.get("why") or ""
            if w:
                skips.append("%s：%s" % (e.get("code", "?"), w))
    except Exception:
        pass
    skip_s = "；".join(skips) if skips else "当日无信号记录"
    # 持仓
    try:
        lg = load_ledger()
        poss = lg.get("positions", [])
        pos_s = "持仓%d" % len(poss) if poss else "空仓"
        if poss:
            det = []
            for p in poss[:3]:
                pr = realtime_price(p["code"])
                r = (pr / p["buy_price"] - 1) * 100 if pr and p.get("buy_price") else 0
                det.append("%s %+.1f%%" % (p["code"], r))
            pos_s += "（" + "、".join(det) + "）"
    except Exception:
        pos_s = "持仓暂不可用"
    return ("【美股盘面】%s。%s。当日信号：%s。下一步：站上VWAP×1.005+量价齐升才开仓。" % (
        idx_s, pos_s, skip_s))


def buy_day_vwap(code):
    """买入日1日VWAP(节奏器):用5分钟K amount/Σvolume。
    US: Yahoo 5分钟K(无amount,用典型价估算,单位股)。
    CRYPTO: Kraken 小时K(UTC当日),amount=美元成交额。"""
    from vwap import vwap_of
    if MARKET == "US":
        try:
            import bars_us
            from trading_calendar import today_str
            bars = bars_us.yahoo_intraday(code)
            tb = [b for b in bars if b["time"][:10] == today_str("US")]
            return vwap_of(tb) if tb else None
        except Exception:
            return None
    if MARKET == "CRYPTO":
        try:
            import bars_crypto
            from trading_calendar import today_str
            bars = bars_crypto.intraday_hourly(code, 40)
            tb = [b for b in bars if b["time"][:10] == today_str("CRYPTO")]
            return vwap_of(tb) if tb else None
        except Exception:
            return None
    import daily_review as dr
    api_code = ("sh" if code[0] in "69" else "sz") + code
    try:
        bars = dr.api("/api/v1/quotes/kline?symbol=%s&period=5&limit=48" % api_code,
                      timeout=20)["data"]
        return vwap_of(bars)
    except Exception:
        return None


def buy_day_vwap10(code):
    """买入时10日VWAP(中期锚点,P6破位用):日K amount/Σ(volume*100)。
    US:用本地 bars_us 日K amount/Σvolume(股)。
    CRYPTO:用 bars_crypto UTC日K amount/Σvolume(币)。"""
    if MARKET == "US":
        try:
            import bars_us
            bars = bars_us.get_bars(code)[-10:]
            amt = sum(b["amount"] for b in bars)
            vol = sum(b["volume"] for b in bars)
            return amt / vol if vol else None
        except Exception:
            return None
    if MARKET == "CRYPTO":
        try:
            import bars_crypto
            bars = bars_crypto.get_bars(code)[-10:]
            amt = sum(b["amount"] for b in bars)
            vol = sum(b["volume"] for b in bars)
            return amt / vol if vol else None
        except Exception:
            return None
    import daily_review as dr
    api_code = ("sh" if code[0] in "69" else "sz") + code
    try:
        bars = dr.api("/api/v1/quotes/kline?symbol=%s&period=day&limit=12" % api_code,
                      timeout=20)["data"][-10:]
        amt = sum(b["amount"] for b in bars)
        vol = sum(b["volume"] * 100 for b in bars)
        return amt / vol if vol else None
    except Exception:
        return None


def buy_day_vwap_n(code, n):
    """买入时N日VWAP(多日结构锚点,P8条件4用)。
    CN:日K amount/Σ(volume*100),东财volume单位为手;
    US:本地 bars_us 日K amount/Σvolume(股);
    CRYPTO:本地 bars_crypto UTC日K amount/Σvolume(币)。"""
    if MARKET == "US":
        try:
            import bars_us
            bars = bars_us.get_bars(code)[-n:]
            amt = sum(b["amount"] for b in bars)
            vol = sum(b["volume"] for b in bars)
            return amt / vol if vol else None
        except Exception:
            return None
    if MARKET == "CRYPTO":
        try:
            import bars_crypto
            bars = bars_crypto.get_bars(code)[-n:]
            amt = sum(b["amount"] for b in bars)
            vol = sum(b["volume"] for b in bars)
            return amt / vol if vol else None
        except Exception:
            return None
    import daily_review as dr
    api_code = ("sh" if code[0] in "69" else "sz") + code
    try:
        bars = dr.api("/api/v1/quotes/kline?symbol=%s&period=day&limit=%d" % (api_code, n + 2),
                      timeout=20)["data"][-n:]
        amt = sum(b["amount"] for b in bars)
        vol = sum(b["volume"] * 100 for b in bars)
        return amt / vol if vol else None
    except Exception:
        return None


def trend_gate_ok(code):
    """P25 趋势门(2026-09-30用户拍板"主线任务"):只做多头趋势,不做超跌反弹/阴跌。
    条件:1日VWAP>3日VWAP>5日VWAP 且 昨日收盘站上MA20。数据不足->False(fail-closed)。"""
    try:
        v1 = buy_day_vwap_n(code, 1)
        v3 = buy_day_vwap_n(code, 3)
        v5 = buy_day_vwap_n(code, 5)
        if not (v1 and v3 and v5) or not (v1 > v3 > v5):
            return False
        if MARKET == "US":
            import bars_us
            bars = bars_us.get_bars(code)
        elif MARKET == "CRYPTO":
            import bars_crypto
            bars = bars_crypto.get_bars(code)
        else:
            from bars import get_bars
            bars = get_bars(code)
        if len(bars) < 20:
            return False
        closes = [b["close"] for b in bars[-20:]]  # 末根=昨日收盘(底座15:35后更新)
        ma20 = sum(closes) / 20
        return closes[-1] >= ma20
    except Exception:
        return False


def systemic_risk(ledger):
    """P27 系统性风险(2026-09-30用户拍板"除非vwap及大盘感知到风险才可以清仓出局观望")。
    大盘情绪风险 AND 持仓VWAP风险 -> True。数据缺失->False(fail-closed,不误判)。
    美股暂不启用(返回False,保持原行为)。币圈不启用(P27是A股情绪专属;币圈用 market_crypto 门禁+kill switch)。"""
    if MARKET in ("US", "CRYPTO"):
        return False
    try:
        emo = False
        td = _today()
        try:
            pre = json.load(open(os.path.join(SVC, "logs", "sentiment_%s_premarket.json" % td)))
            if (pre.get("score") or 0) <= -60:
                emo = True
        except (OSError, ValueError):
            pass
        try:
            rows = open(os.path.join(SVC, "logs", "sentiment_intraday_%s.jsonl" % td)).read().strip().split("\n")
            last = json.loads(rows[-1])
            tr = last.get("trend") or {}
            if (last.get("score") or 0) <= -30 and tr.get("streak_dir") == "走弱" and (tr.get("streak") or 0) >= 2:
                emo = True
        except (OSError, ValueError, IndexError):
            pass
        if not emo:
            return False
        poss = ledger.get("positions") or []
        if not poss:
            return False
        bad = 0
        from bars import get_bars as _get_bars
        for p in poss:
            try:
                v5 = buy_day_vwap_n(p["code"], 5)
                bars = _get_bars(p["code"])
                if v5 and bars and bars[-1]["close"] < v5:
                    bad += 1
            except Exception:
                pass
        return bad * 2 >= len(poss)
    except Exception:
        return False


class _RiskOffSkip(Exception):
    """P27:系统性风险时跳过P24跟随单的内部控制流。"""


# ---- 统一决策门 v1 (2026-10-01 用户拍板"各管各的统一+事后可拆解") ----
# 设计:统一的是"决策接口"(最后yes/no),保留的是"决策依据"(各因子原值全记录)。
# 高考总分录取,但每科分数都留着 -> 复盘时随时查出谁拉分谁拖后腿。
# mode=shadow:只计算+记录,不干预现有各P门行为;攒够样本后由周复盘决定是否转 enforce。
def unified_gate(factors, cfg):
    """纯函数:输入因子dict,输出 (pass, score, breakdown)。
    factors 键(缺失=不可验证,按0分计):
      p8_four: P8四条件全过(bool) / p25: 趋势门(bool) / p26: 板块分(0-100)
      pool_score: 池分 / p22_l2: 龙头L2确认(bool) / sentiment: 情绪分(-100~100)
      dayang: 大阳信号(startup_buy/pullback_buy/None)
    权重来自 strategy.yaml decision_gate.weights,版本随策略版本,可回溯。"""
    g = (cfg.get("decision_gate") or {})
    w = (g.get("weights") or {})
    th = g.get("threshold", 60)
    bd = {}
    score = 0.0
    if factors.get("p8_four"):
        score += w.get("p8_four", 30); bd["p8_four"] = w.get("p8_four", 30)
    else:
        bd["p8_four"] = 0
    if factors.get("p25"):
        score += w.get("p25", 20); bd["p25"] = w.get("p25", 20)
    else:
        bd["p25"] = 0
    p26 = factors.get("p26")
    if isinstance(p26, (int, float)) and p26 >= 50:
        score += w.get("p26_sector", 15); bd["p26_sector"] = w.get("p26_sector", 15)
    else:
        bd["p26_sector"] = 0
    ps = factors.get("pool_score")
    if isinstance(ps, (int, float)) and ps >= 8:
        score += w.get("pool_score", 15); bd["pool_score"] = w.get("pool_score", 15)
    else:
        bd["pool_score"] = 0
    if factors.get("p22_l2"):
        score += w.get("p22_leader", 10); bd["p22_leader"] = w.get("p22_leader", 10)
    else:
        bd["p22_leader"] = 0
    st = factors.get("sentiment")
    if isinstance(st, (int, float)) and st > 0:
        score += w.get("sentiment", 10); bd["sentiment"] = w.get("sentiment", 10)
    else:
        bd["sentiment"] = 0
    return (score >= th), round(score, 1), bd


KILL_SWITCH_FILE = os.path.join(SVC, "logs", "kill_switch.json")

def kill_switch_armed():
    """硬风控:kill switch 拉起后,任何模型/信号不得新开仓(网格/轮动/卖出照常)。
    状态文件可审计;拉起/解除都经 log_decision 留痕。"""
    try:
        d = json.load(open(KILL_SWITCH_FILE))
        return bool(d.get("armed"))
    except Exception:
        return False

def arm_kill_switch(reason):
    json.dump({"armed": True, "reason": reason,
               "at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S")},
              open(KILL_SWITCH_FILE, "w"), ensure_ascii=False, indent=1)

def disarm_kill_switch(reason="manual"):
    json.dump({"armed": False, "reason": reason,
               "at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S")},
              open(KILL_SWITCH_FILE, "w"), ensure_ascii=False, indent=1)


def daily_bars(code, limit=15):
    """日K(网格/趋势判断用)。US走本地 bars_us 底座,CRYPTO走 bars_crypto(UTC日),不碰上游。"""
    if MARKET == "US":
        try:
            import bars_us
            bars = bars_us.get_bars(code)[-limit:]
            return [{"time": b["date"], "open": b["open"], "high": b["high"],
                     "low": b["low"], "close": b["close"],
                     "volume": b["volume"], "amount": b["amount"]} for b in bars]
        except Exception:
            return []
    if MARKET == "CRYPTO":
        try:
            import bars_crypto
            bars = bars_crypto.get_bars(code)[-limit:]
            return [{"time": b["date"], "open": b["open"], "high": b["high"],
                     "low": b["low"], "close": b["close"],
                     "volume": b["volume"], "amount": b["amount"]} for b in bars]
        except Exception:
            return []
    import daily_review as dr
    api_code = ("sh" if code[0] in "69" else "sz") + code
    try:
        return dr.api("/api/v1/quotes/kline?symbol=%s&period=day&limit=%d" % (api_code, limit),
                      timeout=20)["data"]
    except Exception:
        return []


def min5_bars(code, limit=48):
    """5分钟K(破位三段式用)。CRYPTO:用小时K替代(币圈无5分钟底座,小时级足够)。"""
    if MARKET == "CRYPTO":
        try:
            import bars_crypto
            return bars_crypto.intraday_hourly(code, limit)
        except Exception:
            return []
    import daily_review as dr
    api_code = ("sh" if code[0] in "69" else "sz") + code
    try:
        return dr.api("/api/v1/quotes/kline?symbol=%s&period=5&limit=%d" % (api_code, limit),
                      timeout=20)["data"]
    except Exception:
        return []


def run_grid_t(cfg, lg, dry=False):
    """P11 两日网格做T(已有持仓专用,不受新开仓门禁限制)。
    卖出区=两日高+0.5%~1%卖可卖份额;买入区=两日低+1%~2%买回;趋势走坏一键清仓。
    返回 grid_trades 列表。"""
    import grid_t
    from vwap import vwap_of
    gcfg = cfg.get("grid", {})
    grid_trades = []
    today_s = _today()
    for p in lg["positions"]:
        code = p["code"]
        price = realtime_price(code)
        if price <= 0:
            continue
        bars = daily_bars(code)
        gl = grid_t.levels_from_daily(bars, today_s)
        if not gl:
            continue
        p.setdefault("snapshot", {})["grid"] = gl
        sellable = sellable_shares(p, _today())
        # P11 破位三段式:先标记(防震仓) -> 反弹确认 -> VWAP下方卖出,不等主杀
        m5 = min5_bars(code)
        sess_vwap = vwap_of(m5) if m5 else None
        bd_event, bd_new = grid_t.breakdown_update(
            m5, sess_vwap, (p.get("snapshot") or {}).get("breakdown"))
        p["snapshot"]["breakdown"] = bd_new
        if bd_event == "mark" and not dry:
            log_decision(today_s, {"session": "signal", "action": "MARK",
                                   "code": code, "name": p["name"],
                                   "price": round(price, 2),
                                   "why": "疑似破位先标记(跌破当日VWAP),不卖防震仓"})
        elif bd_event == "unmark" and not dry:
            log_decision(today_s, {"session": "signal", "action": "UNMARK",
                                   "code": code, "name": p["name"],
                                   "price": round(price, 2),
                                   "why": "收复VWAP,假破位/震仓解除,继续网格做T"})
        if bd_event == "confirm" and sellable > 0:
            pnl = _net_pnl(p["buy_price"], price, sellable)
            _cash_in(lg, price * sellable)
            p["shares"] -= sellable
            grid_trades.append((p, "CLEAR", sellable, price, pnl,
                                "破位确认(反弹%+.1f%%上不了VWAP,量能%.2f倍,VWAP下方卖出)" % (
                                    bd_new.get("bounce_pct", 0), bd_new.get("vol_ratio", 0))))
            continue
        brk = grid_t.trend_broken_daily(bars, price, today_s)
        if brk and sellable > 0:
            # 趋势走坏:一键清仓,不再做T
            pnl = _net_pnl(p["buy_price"], price, sellable)
            _cash_in(lg, price * sellable)
            p["shares"] -= sellable
            grid_trades.append((p, "CLEAR", sellable, price, pnl,
                                "一键清仓(趋势走坏:%s)" % "+".join(brk)))
        else:
            # P28 每日轮动T纪律(2026-09-30用户):不破趋势确认(P25)才做T;弱势不做T(砍掉弱势,T强势)。
            # 无区间信号不硬做T;操作节奏以周为节点,日级不盲目。
            if not trend_gate_ok(code):
                if not dry:
                    log_decision(today_s, {"session": "signal", "action": "T_SKIP",
                                           "code": code, "name": p["name"],
                                           "price": round(price, 2),
                                           "why": "P28弱势不做T(趋势门未通过),等清仓/止损逻辑"})
                continue
            zone = grid_t.zone_of(price, gl)
            if zone == "sell" and sellable > 0:
                pnl = _net_pnl(p["buy_price"], price, sellable)
                _cash_in(lg, price * sellable)
                p["shares"] -= sellable
                grid_trades.append((p, "GSELL", sellable, price, pnl,
                                    "网格T卖出(两日高%.2f+0.5%%~1%%区)" % gl["h2"]))
            elif zone == "buy":
                amt = min(lg["cash"], gcfg.get("amount_per_grid", 10000))
                shares = _lot_shares(amt, price)
                if shares > 0:
                    _cash_out(lg, shares * price)
                    total = p["buy_price"] * p["shares"] + shares * price
                    p["shares"] += shares
                    p["buy_price"] = round(total / p["shares"], 2)
                    p["locked"] = p.get("locked", 0) + shares; p["locked_until"] = _lock_until(_today())
                    grid_trades.append((p, "GBUY", shares, price, 0,
                                        "网格T买回(两日低%.2f+1%%~2%%区)" % gl["l2"]))
    lg["positions"] = [p for p in lg["positions"] if p["shares"] > 0]
    if grid_trades and not dry:
        for p, act, sh, px, pnl, why in grid_trades:
            # 信号会话的CLEAR全清同样记入closed[],避免结算统计失真(2026-09-30修复)
            if act == "CLEAR" and p["shares"] == 0:
                hold_days = (datetime.strptime(today_s, "%Y-%m-%d") -
                             datetime.strptime(p["buy_date"], "%Y-%m-%d")).days
                p.update({"sell_date": today_s, "sell_price": round(px, 2),
                          "ret_pct": round((px / p["buy_price"] - 1) * 100, 2),
                          "pnl": round(pnl, 2), "reason": why,
                          "hold_days": hold_days})
                lg["closed"].append(p)
        save_ledger(lg)
        for p, act, sh, px, pnl, why in grid_trades:
            _e = {"session": "signal", "action": act,
                  "code": p["code"], "name": p["name"],
                  "price": round(px, 2), "shares": sh,
                  "pnl": round(pnl, 2), "why": why}
            if act in ("CLEAR", "GSELL"):
                _e["buyback_plan"] = _plan(why)  # P16
            log_decision(today_s, _e)
    for p, act, sh, px, pnl, why in grid_trades:
        print("  %s %s %s %d股 @%.2f %s" % (act, p["code"], p["name"], sh, px, why))
    return grid_trades


def run_rotation(cfg, lg, dry=False):
    """P12 资金轮动:统一强度分 -> 卖弱(<=weak_th)释放资金,强者(>=strong_th)打码加仓。
    每只最多加仓一次(adds计数与P7共用)。返回 (sold, pyramided)。"""
    import grid_t
    from vwap import vwap_of
    rcfg = cfg.get("rotation", {})
    weak_th = rcfg.get("weak_th", grid_t.ROT_WEAK_TH)
    strong_th = rcfg.get("strong_th", grid_t.ROT_STRONG_TH)
    today_s = _today()
    scored = []
    for p in lg["positions"]:
        price = realtime_price(p["code"])
        if price <= 0:
            continue
        bars = daily_bars(p["code"])
        m5 = min5_bars(p["code"])
        sess_vwap = vwap_of(m5) if m5 else None
        gl = grid_t.levels_from_daily(bars, today_s)
        bd = (p.get("snapshot") or {}).get("breakdown") or {}
        s, tags = grid_t.position_strength(price, sess_vwap, bars, today_s, gl, bd)
        p.setdefault("snapshot", {})["strength"] = {"score": s, "tags": tags}
        scored.append([p, s, tags, price])
    sold, pyramided = [], []
    # ---- P15 双轨决策树(2026-09-30:强行换仓能力) ----
    # 轨1 换入(SCAN):弱持仓(强度分<=weak_th) + 严格同板块 + 龙头连续多日VWAP强势结构
    #   + 板块资金痕迹 + 盘中站上VWAP + 非复牌一字高开陷阱 + 偏离<2.5% -> 强行换仓(卖一半买龙头)
    # 轨2 跟踪(TRACK):昨日换仓买入的龙头 -> 次日龙头证伪/早盘下杀15分钟确认/动量证伪(不创新高)
    # 节奏锁:每只每天一次 + 同板块每天一次 + T+1锁定不可绕过 + 数据不可验证fail-closed
    try:
        from sector_leader import (leader_status as _ldst, leader_structure as _ldstruct,
                                   leader_track as _ldtrack, sector_capital_trace as _captr,
                                   resume_trap as _trap, plate_of as _plate_of,
                                   leader_strength as _ldstrg)
    except Exception:
        _ldst = _ldstruct = _ldtrack = _captr = _trap = _plate_of = _ldstrg = None
    _ld_cache = {}

    def _ld(code):
        if code not in _ld_cache:
            try:
                _ld_cache[code] = _ldst(code, today_s) if _ldst else {"ok": False}
            except Exception:
                _ld_cache[code] = {"ok": False}
        return _ld_cache[code]

    def _p15_skip(code, name, reason):
        if not dry:
            log_decision(today_s, {"session": "signal", "action": "SKIP",
                                   "code": code, "name": name, "why": reason})

    p15_done = set()
    for p, s, tags, price in scored:  # 证伪先行(既有):龙头跌破VWAP->清仓跟风股剩余可卖份额
        ld = _ld(p["code"])
        if not (ld.get("ok") and ld.get("dead") and not ld.get("is_self")):
            continue
        sellable = sellable_shares(p, _today())
        if sellable <= 0:
            continue
        pnl = _net_pnl(p["buy_price"], price, sellable)
        _cash_in(lg, price * sellable)
        p["shares"] -= sellable
        why = "P15龙头证伪清仓(龙头%s%s跌破VWAP,板块退潮)" % (ld["name"], ld["code"])
        sold.append((p, sellable, price, pnl, why))
        p15_done.add(p["code"])
        if not dry:
            log_decision(today_s, {"session": "signal", "action": "SELL",
                                   "code": p["code"], "name": p["name"],
                                   "price": round(price, 2), "shares": sellable,
                                   "pnl": round(pnl, 2), "why": why,
                                   "buyback_plan": _plan(why)})
    # 轨1:换入
    p15_sector_done = set()  # 同板块当天不反复横跳
    for p, s, tags, price in scored:
        if p["code"] in p15_done or s > weak_th:
            continue
        if (p.get("snapshot") or {}).get("p15_date") == today_s:
            continue  # 每只每天只换一次
        ld = _ld(p["code"])
        if not (ld.get("ok") and not ld.get("is_self")):
            continue  # fail-closed:无龙头数据不动
        plate = ld.get("plate") or ""
        p_plate = _plate_of(p["code"], today_s) if _plate_of else ""
        if not p_plate or not plate or p_plate != plate:
            continue  # 门1 严格同板块:不可验证或跨板块 -> fail-closed
        if plate in p15_sector_done:
            continue  # 门2 节奏锁:同板块当天只换一次
        if _sector_mode_of(plate) == "grid":
            continue  # P21:控盘板块只做T,不换仓追突破
        st = _ldstruct(ld["code"], today_s, market=MARKET) if _ldstruct else {"ok": False}
        if not (st.get("ok") and st.get("strong")):
            continue  # 门3a 规则1:龙头连续多日VWAP强势结构(近5日≥4天站上)
        ls = _ldstrg(ld["code"], today_s, market=MARKET) if _ldstrg else {"ok": False}
        if not (ls.get("ok") and ls.get("level", 0) >= 2):
            _p15_skip(ld["code"], ld["name"],
                       "P15换仓:龙头%s涨跌不对称不足(level=%s,需L2确认)" % (
                           ld["code"], ls.get("level")))
            continue  # 门3b P22:涨跌不对称(涨多跌少)需L2确认,不对称<3不换
        if _captr and not _captr(plate, today_s):
            continue  # 门4 规则5:板块资金痕迹(板块内≥2只强势)
        if not ld.get("above_vwap"):
            continue  # 门5 盘中站上VWAP,不接飞刀
        trap = _trap(ld["code"], today_s) if _trap else None
        if trap is not False:
            _p15_skip(ld["code"], ld["name"],
                       "P15换仓:龙头%s一字板/高开陷阱不可验证或命中,不追" % ld["code"])
            continue  # 门6 规则4:复牌一字次日高开>5%=T+1陷阱;None=不可验证
        # 龙头切换事件(规则3):只记录,不阻断
        try:
            tr = _ldtrack(p["code"], today_s) if _ldtrack else {}
            if tr.get("switched"):
                _p15_skip(p["code"], p["name"],
                           "P15龙头切换:板块%s焦点 %s->%s" % (
                               plate, (tr.get("prev") or {}).get("code"),
                               (tr.get("curr") or {}).get("code")))
        except Exception:
            pass
        # 强行执行换仓
        sellable = sellable_shares(p, _today())
        half = int(sellable / 200) * 100
        if half <= 0:
            continue
        pnl = _net_pnl(p["buy_price"], price, half)
        _cash_in(lg, price * half)
        p["shares"] -= half
        why_s = "P15换仓卖出半仓(强度分%d,龙头%s%s连续%d日VWAP强势,不对称%.2f)" % (
            s, ld["name"], ld["code"], (st.get("days_above") or 0),
            (ls.get("ratio") or 0))
        sold.append((p, half, price, pnl, why_s))
        if not dry:
            log_decision(today_s, {"session": "signal", "action": "SELL",
                                   "code": p["code"], "name": p["name"],
                                   "price": round(price, 2), "shares": half,
                                   "pnl": round(pnl, 2), "why": why_s,
                                   "buyback_plan": _plan(why_s)})
        lpx, lvw = ld["price"], ld.get("vwap")
        dev = abs(lpx - lvw) / lvw if lvw else 1
        if dev < 0.025:  # 不追高:偏离VWAP<2.5%才买
            amt = min(lg["cash"], price * half / 2,
                      cfg.get("buy", {}).get("amount_per_trade", 100000))
            lshares = _lot_shares(amt, lpx)
            if lshares > 0:
                _cash_out(lg, lshares * lpx)
                lp = next((x for x in lg["positions"]
                           if x["code"] == ld["code"]), None)
                if lp is None:
                    lp = {"code": ld["code"], "name": ld["name"],
                          "buy_date": today_s, "buy_price": round(lpx, 2),
                          "shares": 0, "cost": 0, "locked": 0, "adds": 0,
                          "strategy_version": cfg["version"], "snapshot": {}}
                    lg["positions"].append(lp)
                total = lp["buy_price"] * lp["shares"] + lshares * lpx
                lp["shares"] += lshares
                lp["buy_price"] = round(total / lp["shares"], 2)
                lp["locked"] = lp.get("locked", 0) + lshares  # T+1锁定
                lp.setdefault("snapshot", {})["p15_swap"] = {
                    "from": p["code"], "from_name": p["name"], "plate": plate,
                    "date": today_s, "leader_vwap": round(lvw, 2) if lvw else None,
                    "leader_high": ld.get("high"), "buy_price": round(lpx, 2)}
                # P23:换仓买入预期更短(盈利期就是几天)
                lp["snapshot"]["expect"] = {
                    "days": 3, "target_pct": 2.0,
                    "why": "P15换仓:3个交易日内龙头创新高(高于买入价2%),不及预期平仓"}
                why_b = "P15换仓买入龙头%s%s(偏离VWAP%0.1f%%,T+1锁定)" % (
                    ld["name"], ld["code"], dev * 100)
                if not dry:
                    log_decision(today_s, {"session": "signal", "action": "BUY",
                                           "code": lp["code"], "name": lp["name"],
                                           "price": round(lpx, 2),
                                           "shares": lshares, "why": why_b})
                print("  PROTATE %s %s %d股 @%.2f -> 龙头%s %d股 @%.2f %s" % (
                    p["code"], p["name"], half, price,
                    lp["code"], lshares, lpx, why_b))
        else:
            _p15_skip(ld["code"], ld["name"],
                       "P15换仓:龙头偏离VWAP%0.1f%%过高不追,留现金" % (dev * 100))
        p.setdefault("snapshot", {})["p15_date"] = today_s
        p15_sector_done.add(plate)
        p15_done.add(p["code"])
    # 轨2:昨日换仓买入的龙头 -> 次日跟踪(证伪/早盘确认/动量证伪)
    try:
        from trading_calendar import prev_trading_day as _ptd
        _yday = _ptd(today_s, market=MARKET)
    except Exception:
        _yday = None
    if _yday:
        for p in lg["positions"]:
            if p["code"] in p15_done or p["shares"] <= 0:
                continue
            sw = (p.get("snapshot") or {}).get("p15_swap")
            if not sw or sw.get("date") != _yday:
                continue
            ld = _ld(p["code"])
            if not ld.get("ok"):
                continue  # fail-closed:无数据不动
            price = realtime_price(p["code"])
            if price <= 0:
                continue
            sellable = sellable_shares(p, _today())
            if sellable <= 0:
                continue
            lvw = ld.get("vwap")
            do_sell, why_t = False, ""
            if ld.get("dead"):
                do_sell, why_t = True, "P15换仓腿证伪卖出(龙头%s%s跌破VWAP)" % (
                    ld["name"], ld["code"])
            elif lvw and price < lvw:
                # 规则2:次日早盘下杀是常态,等反弹确认上不上VWAP(15分钟)
                m5 = min5_bars(p["code"], limit=3)
                rec = any((b.get("close") or 0) >= lvw for b in (m5 or [])[-3:])
                if rec:
                    _p15_skip(p["code"], p["name"],
                               "P15换仓腿早盘下杀等反弹确认:15分钟内收复VWAP,假下杀持有")
                    p15_done.add(p["code"])  # 明确持有->不让轮动卖弱二次决策
                else:
                    do_sell, why_t = True, "P15换仓腿早盘确认失败(15分钟未收复VWAP,真下杀)"
            else:
                # 动量证伪:回落且当日不创新高(无第二波加速)
                bars = daily_bars(p["code"], limit=5)
                yb = bars[-1] if bars else {}
                ph, pc = yb.get("high") or 0, yb.get("close") or 0
                if ph and pc and (ld.get("high") or 0) < ph * 0.999 and price < pc:
                    do_sell, why_t = True, "P15换仓腿动量证伪(回落且不创新高,无第二波加速)"
            if do_sell:
                pnl = _net_pnl(p["buy_price"], price, sellable)
                _cash_in(lg, price * sellable)
                p["shares"] -= sellable
                sold.append((p, sellable, price, pnl, why_t))
                p15_done.add(p["code"])
                if not dry:
                    log_decision(today_s, {"session": "signal", "action": "SELL",
                                           "code": p["code"], "name": p["name"],
                                           "price": round(price, 2),
                                           "shares": sellable,
                                           "pnl": round(pnl, 2), "why": why_t,
                                           "buyback_plan": _plan(why_t)})
    lg["positions"] = [p for p in lg["positions"] if p["shares"] > 0]
    # 卖弱:强度分<=阈值 -> 卖出可卖份额,资金轮动到强者(P15已处理的不重复)
    for p, s, tags, price in scored:
        if p["code"] in p15_done:
            continue
        if s <= weak_th:
            sellable = sellable_shares(p, _today())
            if sellable <= 0:
                continue
            pnl = _net_pnl(p["buy_price"], price, sellable)
            _cash_in(lg, price * sellable)
            p["shares"] -= sellable
            why = "轮动卖弱(强度分%d:%s)" % (s, ",".join(tags))
            sold.append((p, sellable, price, pnl, why))
            if not dry:
                log_decision(today_s, {"session": "signal", "action": "SELL",
                                       "code": p["code"], "name": p["name"],
                                       "price": round(price, 2), "shares": sellable,
                                       "pnl": round(pnl, 2), "why": why})
    lg["positions"] = [p for p in lg["positions"] if p["shares"] > 0]
    # 强者打码:强度分>=阈值 -> 加仓一笔(与P7共用adds计数,每只最多一次)
    for p, s, tags, price in scored:
        if p["shares"] <= 0 or p.get("adds", 0) >= 1:
            continue
        # P21:控盘板块只适合网格做T,不追突破 -> 不加仓
        if _sector_mode_of(p.get("snapshot", {}).get("plate") or p["code"]) == "grid":
            continue
        if s >= strong_th:
            amt = min(lg["cash"], rcfg.get("pyramid_amount", 10000))
            shares = _lot_shares(amt, price)
            if shares <= 0:
                continue
            _cash_out(lg, shares * price)
            total = p["buy_price"] * p["shares"] + shares * price
            p["shares"] += shares
            p["buy_price"] = round(total / p["shares"], 2)
            p["locked"] = p.get("locked", 0) + shares; p["locked_until"] = _lock_until(_today())
            p["adds"] = p.get("adds", 0) + 1
            p["last_add"] = {"date": today_s, "price": round(price, 2), "reason": "强者打码"}
            why = "强者打码(强度分%d:%s)" % (s, ",".join(tags))
            pyramided.append((p, shares, price, why))
            if not dry:
                log_decision(today_s, {"session": "signal", "action": "ADD",
                                       "code": p["code"], "name": p["name"],
                                       "price": round(price, 2), "shares": shares,
                                       "why": why})
    if (sold or pyramided) and not dry:
        save_ledger(lg)
    for p, sh, px, pnl, why in sold:
        print("  RSELL %s %s %d股 @%.2f %s" % (p["code"], p["name"], sh, px, why))
    for p, sh, px, why in pyramided:
        print("  PYRAMID %s %s %d股 @%.2f %s" % (p["code"], p["name"], sh, px, why))
    return sold, pyramided


def _plan(why):
    """P16:卖出附买回计划(各卖出日志点统一调用)。"""
    try:
        import protect as _P
        return _P.buyback_plan_for(why)
    except Exception:
        return None


def _sector_mode_of(code_or_plate):
    """P21:持仓/候选的板块模式(grid=控盘只做T / normal)。失败回 normal。"""
    try:
        from sector_leader import sector_of, sector_mode
        s = str(code_or_plate or "")
        if MARKET == "CRYPTO":
            return "normal"  # 币圈无板块概念
        if MARKET == "US":
            sec = sector_of(s, "US")
        elif s.isdigit() and len(s) == 6:
            sec = sector_of(s, "CN") or s
        else:
            sec = s
        return sector_mode(sec, MARKET) if sec else "normal"
    except Exception:
        return "normal"


def _morning_one(code):
    """单个票的早盘识别(P18补回用,非池子票按需算)。"""
    try:
        from sentiment import morning_action_from_bars
        if MARKET == "US":
            from trading_calendar import today_str
            import bars_us
            return morning_action_from_bars(code, bars_us.yahoo_intraday(code), today_str("US"))
        if MARKET == "CRYPTO":
            from trading_calendar import today_str
            import bars_crypto
            return morning_action_from_bars(code, bars_crypto.intraday_hourly(code, 60),
                                            today_str("CRYPTO"))
        return morning_action_from_bars(code, min5_bars(code, limit=60))
    except Exception:
        return {"code": code, "error": "fetch_fail"}


def run_buyback(cfg, lg, mkt, mkt_score, min_sent, dry=False):
    """P18 止盈后补回:P16买回观察池里的票,重新站上VWAP且放量 -> 按P8同仓位买回。
    走同样的情绪/仓位/资金门禁;不因"卖飞难受"而抗拒,也不因FOMO乱买。"""
    import protect as _P
    bcfg = cfg["buy"]
    watch = _P.load_watch(MARKET)
    if not watch:
        return []
    if mkt_score < min_sent:
        print("P18: market sentiment %.1f < %s, 补回暂停" % (mkt_score, min_sent))
        return []
    held = {p["code"] for p in lg["positions"]}
    buys = []
    today_s = _today()
    for e in watch:
        code = e["code"]
        if code in held:
            if not dry:
                _P.drop_watch_entry(MARKET, code)
            continue
        if len(lg["positions"]) + len(buys) >= bcfg["max_positions"]:
            break
        m = _morning_one(code)
        ok, why0 = _P.p18_ok(m)
        if not ok:
            continue
        price = m["price"]
        amt = bcfg["amount_per_trade"]
        if lg["cash"] < amt:
            print("cash insufficient")
            break
        shares = _lot_shares(amt, price)
        if shares <= 0:
            continue
        cost = shares * price
        _cash_out(lg, cost)
        bv = buy_day_vwap(code)
        bv10 = buy_day_vwap10(code)
        pos = {
            "code": code, "name": e.get("name") or code, "buy_date": today_s,
            "buy_price": round(price, 2), "shares": shares, "cost": round(cost, 2),
            "locked": shares, "locked_until": _lock_until(today_s),
            "buy_vwap": round(bv, 2) if bv else None,
            "buy_vwap10": round(bv10, 2) if bv10 else None,
            "adds": 0,
            "strategy_version": cfg["version"],
            "snapshot": {
                "source": "P18补回", "buyback_of": e.get("reason"),
                "market_sentiment": mkt_score, "morning": m,
                "sector_mode": _sector_mode_of(code),
                # P23:买入必须带预期,不及预期平仓
                "expect": {"days": 5, "target_pct": 2.0,
                           "why": "P18补回后5个交易日内创新高(高于买入价2%),不及预期平仓"},
            },
        }
        lg["positions"].append(pos)
        buys.append(pos)
        if not dry:
            _P.drop_watch_entry(MARKET, code)
            log_decision(today_s, {"session": "signal", "action": "BUY",
                                   "code": code, "name": pos["name"],
                                   "price": round(price, 2),
                                   "why": "P18补回:买回计划触发(重新站上VWAP×1.005且放量),原卖出=%s"
                                          % e.get("reason")})
        print("  P18补回 %s %s %.2f x %d" % (code, pos["name"], price, shares))
    return buys


def do_signal(dry=False):
    """统一信号链路(两市同一套逻辑):网格T(P11) -> 轮动(P12) -> 池/早盘/情绪门禁 -> P8买入。
    数据层按市场分发:get_pool/get_morning/get_market。"""
    cfg = load_cfg()
    bcfg = cfg["buy"]
    lg = load_ledger()
    # P11 网格T先行:只对已有持仓,不受P5大跌装死日等新开仓门禁限制
    grid_trades = run_grid_t(cfg, lg, dry)
    # P12 轮动:卖弱释放资金 + 强者打码(同样只对已有持仓,不受新开仓门禁限制)
    rot_sold, rot_added = run_rotation(cfg, lg, dry)
    pool = get_pool()
    if not pool:
        print("no pool")
        return
    morning = get_morning()
    mkt = get_market()
    mkt_score = mkt.get("score")
    if mkt_score is None:
        # 情绪不可验证 -> fail-closed:已有持仓的网格/轮动已执行,不新开仓
        print("market sentiment unavailable, fail-closed: no new buys")
        if (grid_trades or rot_sold or rot_added) and not dry:
            from push import send as push_send
            body = "\n".join("%s %s %s %d股@%.2f %s" % (act, p["code"], p["name"], sh, px, why)
                             for p, act, sh, px, pnl, why in grid_trades)
            body += "\n".join("RSELL %s %s %d股@%.2f %s" % (p["code"], p["name"], sh, px, why)
                              for p, sh, px, pnl, why in rot_sold)
            body += "\n".join("PYRAMID %s %s %d股@%.2f %s" % (p["code"], p["name"], sh, px, why)
                              for p, sh, px, pnl, why in rot_added)
            push_send("📝 模拟盘"+mtag()+"网格T/轮动", body.strip())
        return []
    # P5 大跌装死日:不新开仓(盘中化:盘中情绪转暖则解除,资金不闲置)
    if bcfg["forbid_dead_day"] and effective_dead_day(mkt):
        print("dead_day: 大跌装死日,不新开仓")
        if (grid_trades or rot_sold or rot_added) and not dry:
            from push import send as push_send
            body = "\n".join("%s %s %s %d股@%.2f %s" % (act, p["code"], p["name"], sh, px, why)
                             for p, act, sh, px, pnl, why in grid_trades)
            body += "\n".join("RSELL %s %s %d股@%.2f %s" % (p["code"], p["name"], sh, px, why)
                              for p, sh, px, pnl, why in rot_sold)
            body += "\n".join("PYRAMID %s %s %d股@%.2f %s" % (p["code"], p["name"], sh, px, why)
                              for p, sh, px, why in rot_added)
            push_send("📝 模拟盘"+mtag()+"网格T/轮动", body.strip())
        return []
    # P27 系统性风险(2026-09-30用户拍板):除非vwap及大盘感知到风险,不清仓出局观望;
    # 风险确认时不新开仓(P8/P24/P18全停,网格/轮动照常)。fail-closed:数据不足->False。
    RISK_OFF = systemic_risk(lg)
    if RISK_OFF:
        print("systemic_risk: 系统性风险确认,不新开仓观望")
        log_decision(today_s, {"session": "signal", "action": "RISK_OFF",
                               "why": "P27系统性风险(大盘情绪+持仓VWAP双确认),不清仓但不新开仓"})
    # 硬 kill switch(2026-10-01):拉起后 P8/P24/P18 全停新开仓,网格/轮动/卖出照常。
    # 任何模型/信号不得覆盖;解除需 --kill off 手动操作并留痕。
    # 影子仓(v1.5):独立 in-ledger kill,不碰 logs/kill_switch.json。
    _is_exp = (MARKET == "CRYPTO" and SLEEVE == "exp")
    KILL_ON = exp_kill_armed(lg) if _is_exp else kill_switch_armed()
    if KILL_ON:
        print("KILL_SWITCH armed: 硬风控拉起,不新开仓")
        log_decision(today_s, {"session": "signal", "action": "KILL_SWITCH",
                               "why": "硬kill switch拉起中,停止一切新开仓(网格/轮动/卖出照常)"})
    # P27 最低半仓(2026-09-30用户"最少半仓操作,放开胆量做"):无系统性风险且仓位<50%时,
    # 本轮单笔上浮至1.5倍,直到半仓。美股暂不启用。
    _amt0 = bcfg["amount_per_trade"]
    _pos_val = 0.0
    try:
        _pos_val = sum((realtime_price(p["code"]) or p.get("cost") or 0) * p.get("shares", 0)
                       for p in lg.get("positions", []))
    except Exception:
        pass
    _equity = lg.get("cash", 0) + _pos_val
    if not RISK_OFF and MARKET == "CN" and _equity > 0 and _pos_val / _equity < 0.5:
        _amt0 = int(bcfg["amount_per_trade"] * 1.5)
        print("P27放开胆量:仓位%.1f%%<50%%,单笔上浮至%d" % (_pos_val / _equity * 100, _amt0))
    # P2 水位连续下降3日 -> 收紧买入门槛; P3 风险偏好低 -> 同样收紧
    min_sent = bcfg["min_market_sentiment"]
    water = mkt.get("water", {})
    if water.get("days_declining", 0) >= 3:
        min_sent = bcfg["min_market_sentiment_low_water"]
        print("水位连降%d日,买入门槛收紧到 %s" % (water["days_declining"], min_sent))
    if mkt.get("risk_appetite", {}).get("level") == "低":
        min_sent = max(min_sent, bcfg["min_market_sentiment_low_water"])
        print("风险偏好低,买入门槛收紧到 %s" % min_sent)
    held = {p["code"] for p in lg["positions"]}
    buys = []
    # P9:预挂单执行确认(09:25挂单->09:30执行->09:45窗口验证),先转持仓占名额(A股独有,美股无此链路)
    if MARKET == "CN" and not dry:
        pre_filled = confirm_preopen_orders(dry=False)
        for b in pre_filled:
            buys.append(b)
        lg = load_ledger()  # confirm内已save,重读
        held = {p["code"] for p in lg["positions"]}
    for s in pool.get("pool", []):
        code = s["symbol"]
        if RISK_OFF or KILL_ON:
            continue  # P27系统性风险/硬kill switch:不新开仓
        if code in held:
            continue
        if len(lg["positions"]) + len(buys) >= bcfg["max_positions"]:
            break
        if s.get("score", 0) < bcfg["min_pool_score"]:
            # near-miss 样本化(v1.5):主 sleeve 被阈值拦下、但在 [实验阈值,主阈值) 的候选只记录不交易
            if (not dry and MARKET == "CRYPTO" and SLEEVE == "main" and
                    _near_miss_band(s.get("score", 0), bcfg["min_pool_score"],
                                    (cfg.get("crypto_exp") or {}).get("min_pool_score", 6.0))):
                record_near_miss(code, "long", s.get("score"), s.get("price"),
                                 "pool分%s在[实验阈值,主阈值)被主阈值%.1f拦下" % (
                                     s.get("score"), bcfg["min_pool_score"]))
            continue
        if mkt_score < min_sent:
            print("market sentiment %.1f < %s, skip all" % (mkt_score, min_sent))
            break
        f = s.get("f", {})
        if f.get("ch_pos", 0) > bcfg["max_ch_pos"]:
            continue
        m = morning.get(code, {})
        if bcfg["forbid_trap"] and m.get("trap") == "诱多":
            s["_skip"] = "诱多"
            continue
        # P4 加速末端:当日涨幅>7%不追(涨幅不可验证则跳过,不赌)
        day_chg = m.get("day_chg")
        if day_chg is None:
            day_chg = s.get("change_percent")
        if day_chg is None:
            s["_skip"] = "涨幅不可验证"
            continue
        if day_chg > bcfg["max_day_chg"]:
            s["_skip"] = "加速末端"
            continue
        price = m.get("price") or realtime_price(code)
        if price <= 0:
            continue
        # P8 早盘诱多节点:10:05买入默认=追高,只买漂亮的首日VWAP结构+量价齐升
        # 四条件:站上1日VWAP×1.005 + 量价齐升 + 偏离VWAP<2.5% + 多日VWAP结构;节点冲高回落不买
        # 数据不可验证时一律不买(2026-09-29教训:故障窗口fail-open导致无数据盲买)
        if m.get("error") or not m.get("vwap_5min"):
            s["_skip"] = "早盘数据不可验证"
            continue
        vwap5 = m.get("vwap_5min")
        if price < vwap5 * 1.005:
            s["_skip"] = "未站上VWAP"
            continue
        if not m.get("vol_up"):
            s["_skip"] = "非量价齐升"
            continue
        if (price - vwap5) / vwap5 > 0.025:
            s["_skip"] = "偏离VWAP过大"
            continue
        # 条件4(2026-09-29用户纠正):多日VWAP结构过滤。昨日破位VWAP下杀后,
        # 早盘低开反弹不过多日VWAP=反抽,是卖点不是买点。要求盘中VWAP>=3日VWAP。
        d3 = buy_day_vwap_n(code, 3)
        if not d3:
            s["_skip"] = "多日VWAP不可验证"
            continue
        if vwap5 < d3:
            s["_skip"] = "反抽不买(盘中VWAP%.2f<3日VWAP%.2f)" % (vwap5, d3)
            continue
        dh = m.get("day_high")
        if dh and day_chg > 3 and price < dh * 0.99:
            s["_skip"] = "节点冲高回落"
            continue
        # P25 趋势门(2026-09-30"主线任务"):只做多头趋势,不做超跌反弹/阴跌
        if not trend_gate_ok(code):
            s["_skip"] = "非趋势(超跌反弹/阴跌)"
            continue
        amt = _amt0  # P27:最低半仓,仓位不足时1.5倍放开胆量
        if lg["cash"] < amt:
            print("cash insufficient")
            break
        shares = _lot_shares(amt, price)
        if shares <= 0:
            continue
        cost = shares * price
        _cash_out(lg, cost)
        bv = buy_day_vwap(code)
        bv10 = buy_day_vwap10(code)
        pos = {
            "code": code, "name": s.get("name"), "buy_date": _today(),
            "buy_price": round(price, 2), "shares": shares, "cost": round(cost, 2),
            "locked": shares, "locked_until": _lock_until(_today()),  # T+1:次一交易日解禁
            "buy_vwap": round(bv, 2) if bv else None,  # VWAP节奏器锚点
            "buy_vwap10": round(bv10, 2) if bv10 else None,  # P6中期锚点
            "adds": 0,
            "strategy_version": cfg["version"],
            "snapshot": {
                "pool_score": s.get("score"), "ch_pos": f.get("ch_pos"),
                "day_chg": round(day_chg, 2),
                "market_sentiment": mkt_score, "morning": m,
                "water": water.get("direction"),
                "risk_appetite": mkt.get("risk_appetite", {}).get("level"),
                "plate": s.get("plate"), "is_leader": s.get("is_leader"),
                # P21:控盘板块 -> 网格模式(只做T不追突破);日级缓存,首次稍慢
                "sector_mode": _sector_mode_of(s.get("plate") or code),
                # P23:买入必须带预期,不及预期平仓
                "expect": {"days": 5, "target_pct": 2.0,
                           "why": "买入后5个交易日内创新高(高于买入价2%),不及预期平仓"},
            },
        }
        lg["positions"].append(pos)
        buys.append(pos)
    # P24 大阳跟随单(2026-09-30用户拍板):打破"大阳不敢开仓"。强势股不会深调,资金密集。
    # 大阳启动特征(近3日startup_buy/pullback_buy)+VWAP启动结构(站上VWAP×1.005+量价齐升)
    # +不深调(当日最低>=大阳最低×0.98)+偏离<5%(启动票放宽)+OBV黄线上 -> 半仓跟随,P23预期3天
    # 数据不可验证一律不买(fail-closed);P8已买的不重复;P27系统性风险时不跟。
    try:
        import dayang as _dy
        if RISK_OFF or KILL_ON:
            print("RISK_OFF/KILL: 跳过P24跟随单")
            raise _RiskOffSkip()
        bought_codes = {b["code"] for b in buys}
        for s in pool.get("pool", []):
            code = s["symbol"]
            if code in bought_codes or s.get("_skip"):
                continue
            # P24豁免score门禁(2026-09-30):跟随单对象=dayang确认的启动票,
            # 大阳+VWAP+不深调+OBV四重筛选已足够;score>=8曾把江淮(5.0)拦在门外。
            dy = _dy.dayang_signal(code, market=MARKET)
            if dy.get("signal") not in ("startup_buy", "pullback_buy"):
                continue
            ev = dy.get("ev") or {}
            m = morning.get(code, {})
            if m.get("error") or not m.get("vwap_5min"):
                continue
            price = m.get("price") or realtime_price(code)
            if price <= 0:
                continue
            vwap5 = m["vwap_5min"]
            if price < vwap5 * 1.005:
                continue  # 没站上VWAP
            if not m.get("vol_up"):
                continue  # 非量价齐升
            if (price - vwap5) / vwap5 >= 0.05:
                continue  # 偏离过大不追
            dc = m.get("day_chg")
            if dc is None:
                dc = s.get("change_percent")
            if dc is None or dc > 9:
                continue  # 涨幅不可验证或加速>9%不跟
            m5 = _today_m5(code, today_s)
            day_low = min((b.get("low") or 0 for b in m5), default=0)
            if not day_low or not ev.get("low"):
                continue
            if day_low < ev["low"] * 0.98:
                continue  # 深调了,不是强势股
            ob = dy.get("obv_up", True)
            if dy.get("signal") == "startup_buy" and not ev.get("obv_above"):
                continue  # 资金不密集不跟
            # P25 趋势门:只做多头趋势,不做超跌反弹/阴跌
            if not trend_gate_ok(code):
                continue
            # P26 板块四维确认(2026-09-30"板块最重要"):个股再好,板块不行不跟
            # CRYPTO:币圈无板块概念,P26记中性50分不拦(2026-10-01)
            if MARKET == "CRYPTO":
                _ss = {"score": 50, "note": "crypto_neutral"}
            else:
                import sector_leader as _sl
                try:
                    _ss = _sl.sector_score(_sl.plate_of(code), market=MARKET)
                except Exception:
                    _ss = {"score": 0}
            if _ss.get("score", 0) < 50:
                continue
            amt = _amt0 * 0.5  # 跟随单半仓(P27:_amt0已含放开胆量上浮)
            if lg["cash"] < amt:
                print("cash insufficient(P24)")
                break
            shares = _lot_shares(amt, price)
            if shares <= 0:
                continue
            cost = shares * price
            _cash_out(lg, cost)
            bv = buy_day_vwap(code)
            pos = {
                "code": code, "name": s.get("name"), "buy_date": _today(),
                "buy_price": round(price, 2), "shares": shares,
                "cost": round(cost, 2), "locked": shares,
                "locked_until": _lock_until(_today()),
                "buy_vwap": round(bv, 2) if bv else None,
                "buy_vwap10": None, "adds": 0,
                "strategy_version": cfg["version"],
                "snapshot": {
                    "source": "P24大阳跟随单", "pool_score": s.get("score"),
                    "dayang": dy.get("signal"), "dayang_ev": ev.get("date"),
                    "day_chg": round(dc, 2), "morning": m,
                    "sector_score": _ss.get("score"),
                    "expect": {"days": 3, "target_pct": 2.0,
                               "why": "P24跟随单:3个交易日内创新高(高于买入价2%),不及预期平仓"},
                },
            }
            lg["positions"].append(pos)
            buys.append(pos)
            bought_codes.add(code)
            if not dry:
                log_decision(today_s, {
                    "session": "signal", "action": "BUY",
                    "code": code, "name": s.get("name"), "price": round(price, 2),
                    "shares": shares,
                    "why": "P24大阳跟随单:大阳启动特征(%s %s)+站上VWAP+不深调(最低%.2f>=大阳最低%.2f×0.98)+偏离<5%%+板块四维%d,半仓" % (
                        dy.get("signal"), ev.get("date"), day_low, ev["low"], _ss.get("score", 0))})
            print("  P24跟随 %s %s %.2f x %d" % (code, s.get("name"), price, shares))
    except _RiskOffSkip:
        pass
    except Exception as e:
        print("P24跳过: %s" % e)
    # P18 止盈后补回:买回观察池触发 -> 按P8同仓位买回(走同样门禁)
    if not RISK_OFF and not KILL_ON:
        buys += run_buyback(cfg, lg, mkt, mkt_score, min_sent, dry)
    else:
        print("RISK_OFF/KILL: 跳过P18补回")
    # 决策日志:买入why + 被筛掉的候选why(只记过池分数的)
    today_s = _today()
    regime = latest_regime()
    if not dry:
        for b in buys:
            if b.get("snapshot", {}).get("source") == "竞价预开仓":
                continue  # confirm里已记
            sn = b.get("snapshot", {})
            src = sn.get("source") or ""
            # 类型化因子(2026-10-01):统一门只汇总,各因子原值全记录,复盘可拆解归因
            factors = {
                "source": src,
                "p8_four": ("P24" not in src),  # P8/P18走四条件;P24走大阳四重筛选
                "p24_dayang": sn.get("dayang") or None,
                "p25": True,  # 能买入即已过趋势门(P8/P24/P18全链路)
                "p26": sn.get("sector_score"),
                "pool_score": sn.get("pool_score"),
                "sentiment": sn.get("market_sentiment"),
                "day_chg": sn.get("day_chg"),
                "ch_pos": sn.get("ch_pos"),
            }
            upass, uscore, ubd = unified_gate(factors, cfg)
            factors["gate_shadow"] = {"pass": upass, "score": uscore,
                                      "breakdown": ubd,
                                      "mode": (cfg.get("decision_gate") or {}).get("mode", "shadow")}
            log_decision(today_s, {
                "session": "signal", "action": "BUY",
                "code": b["code"], "name": b["name"], "price": b["buy_price"],
                "why": "池%d分 ch_pos%s 当日%+.1f%%,过P8四条件(站上VWAP×1.005/量价齐升/偏离<2.5%%/多日VWAP结构)" % (
                    sn.get("pool_score") or 0, sn.get("ch_pos"),
                    sn.get("day_chg") or 0),
                "regime_gate": regime.get("门禁")}, factors=factors)
        for s in pool.get("pool", []):
            if s.get("_skip") and s.get("score", 0) >= bcfg["min_pool_score"]:
                log_decision(today_s, {
                    "session": "signal", "action": "SKIP",
                    "code": s["symbol"], "name": s.get("name"),
                    "why": "过池%d分但%s,10:05不买" % (s["score"], s["_skip"])},
                    factors={"pool_score": s.get("score"),
                             "skip_gate": s["_skip"]})
    if not dry:
        save_ledger(lg)
    print("signal: 买入 %d 只" % len(buys))
    for b in buys:
        print("  BUY %s %s %.2f x %d" % (b["code"], b["name"], b["buy_price"], b["shares"]))
    # P7 翻转进击点:持仓浮亏<-3% 且早盘诱空->真强反转 -> 加仓一笔(人性不敢上,机器按规则上)
    acfg = cfg.get("add", {})
    adds = []
    today_s = _today()
    for p in lg["positions"]:
        if p.get("adds", 0) >= acfg.get("max_add_per_position", 1):
            continue
        m = morning.get(p["code"], {})
        if not m or m.get("error") or not m.get("price"):
            continue
        price = m["price"]
        float_ret = price / p["buy_price"] - 1
        reversal = (m.get("trap") == "诱空") or (m.get("open_chg", 0) < -1 and m.get("day_chg", 0) > 1)
        if float_ret <= acfg.get("add_trigger_loss", -0.03) and reversal:
            amt = acfg.get("add_amount", 10000)
            if lg["cash"] < amt:
                print("cash insufficient for add")
                break
            shares = _lot_shares(amt, price)
            if shares <= 0:
                continue
            _cash_out(lg, shares * price)
            total = p["buy_price"] * p["shares"] + shares * price
            p["shares"] += shares
            p["locked"] = p.get("locked", 0) + shares; p["locked_until"] = _lock_until(_today())  # T+1:当日加仓次日才可卖
            p["buy_price"] = round(total / p["shares"], 2)
            p["adds"] = p.get("adds", 0) + 1
            p["last_add"] = {"date": today_s, "price": round(price, 2), "reason": "翻转加仓"}
            adds.append(p)
    if adds and not dry:
        save_ledger(lg)
    for p in adds:
        print("  ADD %s %s 翻转加仓 %.2f 均价->%.2f" % (
            p["code"], p["name"], p["last_add"]["price"], p["buy_price"]))
    if (buys or adds or grid_trades or rot_sold or rot_added) and not dry:
        from push import send as push_send
        pre = [b for b in buys if b.get("snapshot", {}).get("source") == "竞价预开仓"]
        reg = [b for b in buys if b not in pre]
        title = "📝 模拟盘"+mtag()+"%s%d只%s" % (
            "竞价成交%d只 " % len(pre) if pre else "",
            len(reg), " 加仓%d只" % len(adds) if adds else "")
        body = "\n".join("FILL %s %s %.2f(竞价)" % (b["code"], b["name"], b["buy_price"]) for b in pre)
        body += "\n".join("BUY %s %s %.2f" % (b["code"], b["name"], b["buy_price"]) for b in reg)
        body += "\n".join("ADD %s %s 翻转加仓 %.2f" % (p["code"], p["name"], p["last_add"]["price"]) for p in adds)
        body += "\n".join("%s %s %s %d股@%.2f %s" % (act, p["code"], p["name"], sh, px, why)
                       for p, act, sh, px, pnl, why in grid_trades)
        body += "\n".join("RSELL %s %s %d股@%.2f %s" % (p["code"], p["name"], sh, px, why)
                       for p, sh, px, pnl, why in rot_sold)
        body += "\n".join("PYRAMID %s %s %d股@%.2f %s" % (p["code"], p["name"], sh, px, why)
                       for p, sh, px, why in rot_added)
        # 重点个股自动配图:买入的配K线图(最多3只)
        chart_imgs = []
        try:
            from stock_charts import draw_list as _draw
            cdir = os.path.join(SVC, "logs", "charts", today_s)
            chart_imgs = _draw([(b["code"], b["name"]) for b in buys],
                               cdir, max_n=3)
        except Exception as e:
            print("buy charts fail: %s" % e, flush=True)
        push_send(title, body.strip(), images=chart_imgs)
    return buys


def get_us_universe():
    try:
        w = json.load(open(os.path.join(SVC, "us_watchlist.json")))
        syms = w.get("symbols", w) if isinstance(w, dict) else w
        return [str(s).upper() for s in syms]
    except Exception:
        return []


def _p17_trigger(p, bars, price, today):
    """P17 买入次日下杀即走:买入次日(交易日)跌破买入日低点,或低开低走收不回买入价。
    数据不可验证时不触发(fail-closed)。"""
    from trading_calendar import prev_trading_day
    if p.get("buy_date") != prev_trading_day(today, market=MARKET):
        return False
    bb = next((b for b in bars if str(b.get("time", ""))[:10] == p["buy_date"]), None)
    tb = bars[-1] if bars and str(bars[-1].get("time", ""))[:10] == today else None
    if not bb or not tb:
        return False
    if (tb.get("low") or 0) <= (bb.get("low") or 0):
        return True
    return (tb.get("open") or 0) < p["buy_price"] and price < p["buy_price"]


def _p23_miss(p, bars, today):
    """P23 预期止损:买入时snapshot写了expect(几天内创新高),到期没兑现->不及预期平仓。
    买入不符合基础交易逻辑(事后发现买入时门禁条件不满足)视为错误单,按P17纪律纠正。
    数据不可验证时不触发(fail-closed)。"""
    ex = (p.get("snapshot") or {}).get("expect")
    if not ex:
        return False
    tds = [b for b in bars
           if p["buy_date"] < str(b.get("time", ""))[:10] <= today]
    if len(tds) < ex.get("days", 5):
        return False
    need = p["buy_price"] * (1 + ex.get("target_pct", 2.0) / 100)
    highs = [b.get("high") or 0 for b in tds]
    return bool(highs) and max(highs) < need


def _p19_confirm(p, bars, today):
    """P19次日确认:加速大阳次日不创新高/回落超2% -> 诱多确认,清仓。"""
    from trading_calendar import prev_trading_day
    sn = p.get("snapshot", {})
    if sn.get("accel_day") != prev_trading_day(today, market=MARKET):
        return False
    tb = bars[-1] if bars and str(bars[-1].get("time", ""))[:10] == today else None
    if not tb:
        return False
    if (tb.get("high") or 0) <= (sn.get("accel_high") or 0):
        return True
    return (tb.get("close") or 0) < (sn.get("accel_close") or 0) * 0.98


def _today_m5(code, today):
    """当日5分钟K(P11头肩顶用)。CN走后端,US走Yahoo直连。"""
    try:
        if MARKET == "US":
            import bars_us
            return [b for b in bars_us.yahoo_intraday(code) if b["time"][:10] == today]
        return [b for b in min5_bars(code, limit=60) if str(b.get("time", ""))[:10] == today]
    except Exception:
        return []


def do_settle(dry=False):
    cfg = load_cfg()
    scfg, bcfg = cfg["sell"], cfg["buy"]
    lg = load_ledger()
    today = _today()
    # P3 平仓配合:新股风向标降温到低 -> 情绪退潮,浮盈仓位提前止盈(仅A股,美股无此数据源)
    emotion_cool = False
    if MARKET == "CN":
        mkt = latest_premarket()
        ra = mkt.get("risk_appetite", {})
        emotion_cool = ra.get("trend") == "降温" and ra.get("level") == "低"
    if emotion_cool:
        print("新股风向标降温->低,情绪退潮:浮盈超%.0f%%提前止盈" % (scfg["emotion_cool_profit"] * 100))
    closed_today, still = [], []
    sold_part = []  # P19/P20减半:部分卖出,持仓还在
    import grid_t
    for p in lg["positions"]:
        price = realtime_price(p["code"])
        if price <= 0:
            still.append(p)
            continue
        p["last_price"] = round(price, 2)
        ret = price / p["buy_price"] - 1
        hold_days = (datetime.strptime(today, "%Y-%m-%d") -
                     datetime.strptime(p["buy_date"], "%Y-%m-%d")).days
        sellable = sellable_shares(p, _today())  # T+1:当日买入不可卖
        reason, frac = None, 1.0
        if sellable > 0:
            import protect as _P
            bars30 = daily_bars(p["code"], limit=30)
            if ret >= scfg["take_profit"]:
                reason = "止盈"
            elif _p17_trigger(p, bars30, price, today):
                reason = "P17次日下杀即走"
            elif ret <= scfg["stop_loss"]:
                reason = "止损"
            elif _p23_miss(p, bars30, today):
                reason = "P23不及预期平仓"
            elif hold_days >= scfg["max_hold_days"]:
                reason = "时间止损"
            else:
                # VWAP节奏器:跌破买入日1日VWAP-2% -> 止损
                bv = p.get("buy_vwap")
                if bv and price < bv * (1 - scfg["vwap_stop"]):
                    reason = "VWAP止损"
                # P6 破位:收盘跌破买入时10日VWAP -> 开仓逻辑被证伪,止损
                elif scfg.get("break_ma10") and p.get("buy_vwap10") and price < p["buy_vwap10"]:
                    reason = "破位止损"
                # P3 平仓配合:情绪退潮 -> 浮盈提前止盈,不等+10%
                elif emotion_cool and ret >= scfg.get("emotion_cool_profit", 0.05):
                    reason = "情绪退潮止盈"
                # P20 保本出局:曾被套后反弹回成本±1% -> 无条件减半,拿回选择权
                elif p.get("was_underwater") and abs(ret) <= scfg.get("p20_band", 0.01):
                    reason = "P20保本出局"
                    frac = 0.5
                else:
                    ac = _P.detect_accel(bars30)
                    if ac:
                        # P19 加速大阳诱多:借大阳减半,不恋战;次日确认再定去留
                        reason = "P19加速大阳减仓"
                        frac = 0.5
                        sn = p.setdefault("snapshot", {})
                        sn["accel_day"] = today
                        sn["accel_high"] = ac["high"]
                        sn["accel_close"] = ac["close"]
                    elif _p19_confirm(p, bars30, today):
                        reason = "P19诱多确认清仓"
                    else:
                        # P11头肩顶前置预警:分时VWAP下方头肩顶,右肩不过VWAP=最后离场点
                        ok, dt = _P.detect_hs_top(_today_m5(p["code"], today))
                        if ok:
                            reason = "P11头肩顶离场(%s)" % dt
            # P11 趋势走坏 -> 一键清仓,不再做T(收盘跌破10日线)
            if not reason:
                bars = daily_bars(p["code"])
                brk = grid_t.trend_broken_daily(bars, price, today)
                if brk:
                    reason = "一键清仓(趋势走坏:%s)" % "+".join(brk)
                else:
                    # P11 网格挂单建模:收盘落在卖出区视为挂单成交
                    gl = grid_t.levels_from_daily(bars, today)
                    if gl and grid_t.zone_of(price, gl) == "sell":
                        reason = "网格T卖出(收盘卖出区%.2f~%.2f)" % (gl["sell_lo"], gl["sell_hi"])
                    p.setdefault("snapshot", {})["grid"] = gl
        if reason:
            # P16:卖出必须附带买回计划,缺失视为情绪卖出,系统不执行
            plan = _P.buyback_plan_for(reason)
            if plan is None:
                if not dry:
                    log_decision(today, {"session": "settle", "action": "SKIP",
                                         "code": p["code"], "name": p["name"],
                                         "why": "P16无买回计划,卖出不执行:%s" % reason})
                p["float_ret"] = round(ret * 100, 2)
                still.append(p)
                continue
            sh = sellable
            if frac < 1.0:
                lot = LOT_SIZE[MARKET]
                sh = int(sellable * frac / lot) * lot
                if sh <= 0:
                    p["float_ret"] = round(ret * 100, 2)
                    still.append(p)
                    continue  # 不足一手无法减半,继续持有
            pnl = _net_pnl(p["buy_price"], price, sh)
            _cash_in(lg, price * sh)
            p["shares"] -= sh
            why_txt = "%s:持有%d天 %+.1f%%,卖出%d股,买入理由=%s" % (
                reason, hold_days, ret * 100, sh,
                (p.get("snapshot") or {}).get("why", p.get("snapshot", {}).get("source", "")))
            if not dry:
                log_decision(today, {"session": "settle", "action": "SELL",
                                     "code": p["code"], "name": p["name"],
                                     "price": round(price, 2), "shares": sh,
                                     "ret_pct": round(ret * 100, 2),
                                     "hold_days": hold_days, "why": why_txt,
                                     "buyback_plan": plan},
                             factors={"sell_reason": reason,
                                      "buy_source": (p.get("snapshot") or {}).get("source"),
                                      "buy_pool_score": (p.get("snapshot") or {}).get("pool_score"),
                                      "buy_dayang": (p.get("snapshot") or {}).get("dayang"),
                                      "buy_sector_score": (p.get("snapshot") or {}).get("sector_score"),
                                      "buy_date": p.get("buy_date")})
                if plan.get("auto_watch"):
                    _P.add_watch_entry(MARKET, p["code"], p["name"], today, reason)
            if p["shares"] <= 0:
                p.update({"sell_date": today, "sell_price": round(price, 2),
                          "ret_pct": round(ret * 100, 2), "pnl": round(pnl, 2),
                          "reason": reason, "hold_days": hold_days})
                lg["closed"].append(p)
                closed_today.append(p)
            else:
                p["float_ret"] = round(ret * 100, 2)
                if sh < sellable:
                    sold_part.append((p, sh, reason))  # 部分卖出也展示
                still.append(p)
        else:
            p["float_ret"] = round(ret * 100, 2)
            if ret < -0.01:
                p["was_underwater"] = True  # P20:记下曾被套,反弹回成本才触发保本出局
            still.append(p)
    lg["positions"] = still
    # T+1滚动:只释放已到期的锁,跑多次不误解锁
    release_due_locks({"positions": still}, _today())
    # 组合净值
    equity = lg["cash"] + sum(p.get("last_price", p["buy_price"]) * p["shares"] for p in still)
    lg["equity"] = round(equity, 2)
    lg["updated"] = today
    if not dry:
        save_ledger(lg)
    # 硬风控:单日已实现亏损超阈值 -> 拉起 kill switch,次日不再新开仓(2026-10-01)
    if not dry and MARKET == "CN":
        try:
            day_pnl = sum(t.get("pnl", 0) for t in closed_today)
            kcfg = (cfg.get("decision_gate") or {}).get("kill", {})
            max_day_loss = kcfg.get("max_day_loss_pct", 0.03)
            day_start = (lg.get("prev_equity") or equity) or equity
            if day_pnl < 0 and abs(day_pnl) / day_start >= max_day_loss and not kill_switch_armed():
                arm_kill_switch("单日已实现亏损%+.0f(%.1f%%),超阈值%.0f%%" % (
                    day_pnl, day_pnl / day_start * 100, max_day_loss * 100))
                log_decision(today, {"session": "settle", "action": "KILL_SWITCH",
                                     "why": "单日亏损超阈值,硬kill switch拉起,明日停新开仓"})
                from push import send as push_send
                push_send("🚨 模拟盘硬风控", "单日亏损%+.0f已拉起kill switch,明日停止新开仓,需手动 --kill off 解除" % day_pnl)
        except Exception as e:
            print("kill check跳过: %s" % e)
    # 影子仓(v1.5):多头 exp 独立 in-ledger kill(单日已实现亏损≥3%),不碰 kill_switch.json
    if not dry and MARKET == "CRYPTO" and SLEEVE == "exp" and SIDE == "long":
        try:
            day_pnl = sum(t.get("pnl", 0) for t in closed_today)
            day_start = (lg.get("prev_equity") or equity) or equity
            if day_pnl < 0 and abs(day_pnl) / day_start >= 0.03 and not exp_kill_armed(lg):
                _arm_exp_kill(lg, "单日已实现亏损%+.0f(%.1f%%),超阈值3%%" % (
                    day_pnl, day_pnl / day_start * 100))
                log_decision(today, {"session": "settle", "action": "EXP_KILL",
                                     "why": "单日亏损超阈值,影子仓独立kill拉起,明日停新开仓"})
                from push import send as push_send
                push_send("🚨 模拟盘"+mtag()+"硬风控",
                          "影子仓单日亏损%+.0f已拉起独立kill,明日停止新开仓" % day_pnl)
                save_ledger(lg)
        except Exception as e:
            print("exp kill check跳过: %s" % e)
    lg["prev_equity"] = round(equity, 2)
    # 复盘统计
    cl = lg["closed"]
    wins = [t for t in cl if t["pnl"] > 0]
    winrate = len(wins) / len(cl) * 100 if cl else 0
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    losses = [t for t in cl if t["pnl"] <= 0]
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    rr = abs(avg_win / avg_loss) if avg_loss else 0
    print("=== 模拟盘结算 %s (策略%s) ===" % (today, cfg["version"]))
    print("净值 %.0f | 持仓 %d | cash %.0f" % (equity, len(still), lg["cash"]))
    for p in still:
        print("  HOLD %s %s 浮盈 %+.1f%%" % (p["code"], p["name"], p.get("float_ret", 0)))
    for t in closed_today:
        print("  SELL %s %s %s %+.1f%% (%+.0f)" % (
            t["code"], t["name"], t["reason"], t["ret_pct"], t["pnl"]))
    for p, sh, rs in sold_part:
        print("  PSELL %s %s %s 卖出%d股(部分),剩余%d股" % (
            p["code"], p["name"], rs, sh, p["shares"]))
    print("累计: %d笔 胜率%.0f%% 盈亏比%.2f 总盈亏%+.0f" % (
        len(cl), winrate, rr, sum(t["pnl"] for t in cl)))
    if not dry:
        from push import send as push_send
        lines = ["净值%.0f 持仓%d cash%.0f" % (equity, len(still), lg["cash"])]
        for t in closed_today:
            lines.append("SELL %s%s %s %+.1f%%(%+.0f)" % (
                t["code"], t["name"], t["reason"], t["ret_pct"], t["pnl"]))
        lines.append("累计%d笔 胜率%.0f%% 盈亏比%.2f 总盈亏%+.0f" % (
            len(cl), winrate, rr, sum(t["pnl"] for t in cl)))
        body = "\n".join(lines)
        if MARKET in ("US", "CRYPTO"):  # 美股/币圈结算附盘面简报(2026-10-03)
            br = market_brief()
            if br:
                body += "\n\n" + br
        push_send("📊 模拟盘"+mtag()+"结算 %s" % today, body)
    # 归因:诱多/诱空 case
    for t in cl[-10:]:
        snap = t.get("snapshot", {})
        m = snap.get("morning", {}) or {}
        if m.get("trap") not in (None, "无", ""):
            print("  归因 %s: 早盘%s -> %s %+.1f%%" % (
                t["code"], m.get("trap"), t["reason"], t["ret_pct"]))


# ============ 数字货币永续做空镜像策略(2026-10-03, crypto_short v1.4) ============
# 10倍杠杆/小时级触发,独立账本 logs/paper_ledger_crypto_short.json。
# 设计原则:
#  - 只在 SIDE=="short" 且 MARKET=="CRYPTO" 时走这条链路;多头/CN/US 链路零改动。
#  - 账本读-改-写合并:已有持仓(含用户实盘镜像单)绝不重建清空。
#  - 镜像单(带显式 stop_loss/take_profit):只吃强平守卫+镜像止损+镜像止盈,不吃策略
#    的部分止盈/VWAP收复/时间止损/P12轮动,保证纸面与实盘同进退。
#  - P11网格对空头无意义,跳过;P12轮动保留为空头趋势证伪平空;情绪门禁镜像(过热不开空)。

def _short_cash(lg):
    """空头账本可用保证金:优先 account.margin_balance,兼容老 cash 口径。"""
    a = lg.get("account") or {}
    if "margin_balance" in a:
        return a["margin_balance"]
    return lg.get("cash", 0.0)


def _short_cash_add(lg, delta):
    a = lg.setdefault("account", {})
    if "margin_balance" in a or "cash" not in lg:
        a["margin_balance"] = round(a.get("margin_balance", 100000.0) + delta, 2)
    else:
        lg["cash"] = round(lg.get("cash", 0.0) + delta, 2)


def _pos_qty(p):
    q = p.get("qty") or 0
    if q <= 0 and p.get("entry"):
        q = (p.get("notional") or 0) / p["entry"]
    return q


def _is_mirror(p):
    """镜像单判定:带显式 stop_loss/take_profit,或 reason 以 mirror_ 开头。
    这类持仓只按自身止损止盈+强平守卫管理,不吃策略退出 ladder。"""
    return (p.get("stop_loss") is not None or p.get("take_profit") is not None
            or str(p.get("reason") or "").startswith("mirror_"))


def short_kill_armed(lg):
    return bool((lg.get("short_kill") or {}).get("armed"))


def _arm_short_kill(lg, reason):
    lg["short_kill"] = {"armed": True, "reason": reason,
                        "at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S")}


def _short_day_stats(lg, today):
    ds = lg.setdefault("day_stats", {"date": "", "margin_base": 0.0, "realized": 0.0})
    if ds.get("date") != today:
        ds.update({"date": today, "margin_base": 0.0, "realized": 0.0})
    return ds


def _hours_open(p):
    try:
        from datetime import timezone
        ot = p.get("open_time") or ""
        dt = datetime.fromisoformat(ot.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return 0.0


def _closed_hourly(code, n=12):
    """已收盘小时K(去掉 forming 中最后一根),point-in-time。"""
    import bars_crypto
    bars = bars_crypto.intraday_hourly(code, n + 1)
    return bars[:-1] if bars else []


def s_p25_bars_ok(code):
    """S-P25 空头趋势门(独立判定,供信号/P12复用):1日VWAP<3日VWAP<5日VWAP 且 昨收<MA20。"""
    try:
        v1 = buy_day_vwap_n(code, 1)
        v3 = buy_day_vwap_n(code, 3)
        v5 = buy_day_vwap_n(code, 5)
        if not (v1 and v3 and v5) or not (v1 < v3 < v5):
            return False
        import bars_crypto
        bars = bars_crypto.get_bars(code)
        if len(bars) < 20:
            return False
        closes = [b["close"] for b in bars[-20:]]
        return closes[-1] < sum(closes) / 20
    except Exception:
        return False


def _vwap_deviation_ok(code, price, cfg):
    """空头VWAP偏离门(镜像多头P8偏离<2.5%不追高):价格低于小时VWAP超过
    max_below_vwap_pct 不追空(远离VWAP必反抽,等回抽再空)。返回(ok, hvwap, dev_pct)。"""
    try:
        max_dev = float(cfg["crypto_short"]["entry"]["s_p8_hourly"].get("max_below_vwap_pct", 2.5))
        hb = _closed_hourly(code, 12)
        from trading_calendar import today_str
        utc_day = today_str("CRYPTO")
        tb = [b for b in hb if b["time"][:10] == utc_day]
        if len(tb) < 3:
            return False, 0, 0
        from vwap import vwap_of
        hvwap = vwap_of(tb)
        if not hvwap:
            return False, 0, 0
        dev = (hvwap - price) / hvwap * 100  # 正数=价格在VWAP下方偏离
        return dev <= max_dev, hvwap, round(dev, 2)
    except Exception:
        return False, 0, 0


def s_p8_short_trigger(code, price, cfg):
    """S-P8 小时触发(镜像多头P8四条件,方向反转):
    现价<当日小时VWAP×0.995 + 近3根已收盘小时K收盘递减 + 下跌放量 + 小时VWAP<3日VWAP。
    数据不可验证 -> (False, why) fail-closed。"""
    e = cfg["crypto_short"]["entry"]["s_p8_hourly"]
    hb = _closed_hourly(code, 12)
    if len(hb) < 6:
        return False, {"why": "小时K不足6根(fail-closed)"}
    from trading_calendar import today_str
    utc_day = today_str("CRYPTO")
    tb = [b for b in hb if b["time"][:10] == utc_day]
    if len(tb) < 3:
        return False, {"why": "UTC当日已收盘小时K不足3根(fail-closed)"}
    from vwap import vwap_of
    from crypto_util import fmt_price
    hvwap = vwap_of(tb)
    if not hvwap:
        return False, {"why": "小时VWAP不可验证"}
    if not (price < hvwap * e["below_hourly_vwap"]):
        return False, {"why": "未跌破小时VWAP×0.995"}
    dev_ok, _, dev_pct = _vwap_deviation_ok(code, price, cfg)
    if not dev_ok:
        return False, {"why": "远离小时VWAP %.2f%%超限不追空(等回抽)" % dev_pct}
    last3 = hb[-3:]
    if not (last3[0]["close"] > last3[1]["close"] > last3[2]["close"]):
        return False, {"why": "近3根小时K收盘非递减"}
    vols5 = [b["volume"] for b in hb[-6:-1]]
    if not vols5 or sum(vols5) <= 0:
        return False, {"why": "量能不可验证"}
    if not (hb[-1]["volume"] > sum(vols5) / len(vols5) * e["vol_mult"]):
        return False, {"why": "下跌未放量"}
    d3 = buy_day_vwap_n(code, 3)
    if not d3:
        return False, {"why": "3日VWAP不可验证"}
    if not (hvwap < d3):
        return False, {"why": "小时VWAP未低于3日VWAP"}
    return True, {"hourly_vwap": fmt_price(hvwap), "vwap3d": fmt_price(d3),
                  "last3_close": [fmt_price(b["close"]) for b in last3]}


def s_p24_short_trigger(code, price, cfg):
    """S-P24 大阴跟随(镜像多头P24大阳跟随):
    近3日出现 ≤-7% 大阴线 且 现价 < 大阴最低×1.02(没像样反弹,仍弱)。"""
    e = cfg["crypto_short"]["entry"]["s_p24_breakdown"]
    import bars_crypto
    from crypto_util import fmt_price
    bars = bars_crypto.get_bars(code)[-3:]
    if len(bars) < 3:
        return False, {"why": "日K不足3根(fail-closed)"}
    for b in bars:
        pc = b.get("prev_close")
        if pc and (b["close"] / pc - 1) <= e["big_down_pct"]:
            if price < b["low"] * e["bounce_limit"]:
                dev_ok, _, dev_pct = _vwap_deviation_ok(code, price, cfg)
                if not dev_ok:
                    return False, {"why": "远离小时VWAP %.2f%%超限不追空(等回抽)" % dev_pct}
                return True, {"big_down_day": b["date"],
                              "day_low": fmt_price(b["low"]),
                              "day_chg_pct": round((b["close"] / pc - 1) * 100, 2)}
    return False, {"why": "近3日无大阴或已反弹超限"}


def open_short_position(cfg, lg, code, name, price, factors, dry=False):
    """开空:扣保证金+开仓手续费(名义),建仓并记录快照。dry 时只返回 position 不落账。"""
    from crypto_util import fmt_price
    sc = cfg["crypto_short"]
    acct = sc["account"]
    margin = acct["amount_per_trade"]
    lev = acct["leverage"]
    fee = acct["fee_per_side"]
    notional = margin * lev
    qty = notional / price
    fee_open = notional * fee
    if _short_cash(lg) < margin + fee_open:
        print("short cash insufficient")
        return None
    from trading_calendar import today_str
    from vwap import vwap_of
    utc_day = today_str("CRYPTO")
    tb = [b for b in _closed_hourly(code, 30) if b["time"][:10] == utc_day]
    evw = vwap_of(tb) if tb else None
    pos = {
        "code": code, "name": name, "side": "short",
        "entry": fmt_price(price), "qty": qty,
        "notional": round(notional, 2), "margin": margin, "leverage": lev,
        "liq_price": fmt_price(price * (1 + 1.0 / lev - sc["exit"]["liq_buffer"])),
        "open_time": datetime.now(BJ).astimezone(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "open_date": utc_day,
        "fee_open_paid": True, "partial_tp_done": False,
        "entry_vwap_h": fmt_price(evw) if evw else None,
        "mark": fmt_price(price),
        "strategy_version": cfg["version"],
        "snapshot": factors,
    }
    if not dry:
        _short_cash_add(lg, -(margin + fee_open))
        lg["positions"].append(pos)
        ds = _short_day_stats(lg, utc_day)
        ds["margin_base"] = round(ds.get("margin_base", 0) + margin, 2)
        save_ledger(lg)
    return pos


def _close_short_qty(cfg, lg, p, qclose, mark, reason, dry=False):
    """平空(全平或部分):释放等比保证金 + 毛利 - 平仓手续费;记 closed[] 与决策日志。"""
    from crypto_util import fmt_price, short_close_pnl
    sc = cfg["crypto_short"]
    fee = sc["account"]["fee_per_side"]
    entry, qty = p["entry"], _pos_qty(p)
    qclose = min(qclose, qty)
    if qclose <= 0 or entry <= 0:
        return 0.0
    pnl = short_close_pnl(entry, mark, qclose, fee)
    # 镜像单开仓手续费当初未扣,这里一次性补扣(账本创建时间未扣保证金,保持总账正确)
    if not p.get("fee_open_paid"):
        pnl -= (qclose * entry) * fee
        p["fee_open_paid"] = True
    margin_release = p["margin"] * (qclose / qty)
    if not dry:
        _short_cash_add(lg, margin_release + pnl)
    p["qty"] = qty - qclose
    p["margin"] = round(p["margin"] - margin_release, 2)
    p["notional"] = round(p["qty"] * entry, 2)
    ret_pct = (entry - mark) / entry * 100
    today = _today()
    if not dry:
        ds = _short_day_stats(lg, today)
        ds["realized"] = round(ds.get("realized", 0) + pnl, 2)
        log_decision(today, {"session": "settle" if reason else "signal",
                             "action": "COVER_PART" if p["qty"] > 0 else "COVER",
                             "code": p["code"], "name": p.get("name"),
                             "side": "short",
                             "price": fmt_price(mark), "qty": round(qclose, 6),
                             "ret_pct": round(ret_pct, 2),
                             "pnl_margin": round(pnl, 2),
                             "hold_hours": round(_hours_open(p), 1),
                             "why": "%s: %s" % ("部分平空" if p["qty"] > 0 else "平空", reason)},
                     factors={"exit_reason": reason, "side": "short",
                              "entry": entry, "leverage": p.get("leverage"),
                              "mirror": _is_mirror(p)})
    if p["qty"] <= 1e-12:
        p.update({"exit": fmt_price(mark), "exit_time": today,
                  "ret_pct": round(ret_pct, 2), "pnl_margin": round(pnl, 2),
                  "reason": reason, "hold_hours": round(_hours_open(p), 1)})
        if not dry:
            lg["closed"].append(p)
    return pnl


def _expect_cooldown_skip(cfg, lg, code):
    """P30冷却:某币种被不及预期平空后 expect_cooldown_h 小时内不再新开空(防"平完秒开"churn)。"""
    try:
        from datetime import timezone
        cd = (lg.get("expect_cooldown") or {}).get(code)
        if not cd:
            return False
        h = float((cfg.get("p30_cycle") or {}).get("expect_cooldown_h", 12))
        ts = datetime.strptime(cd, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() < h * 3600
    except Exception:
        return False


def _expect_dead_short(code):
    """P30 不及预期时间窗(策略单专用):反弹时长≥下跌 expect_ratio_exit 倍 -> True。
    镜像单不走这里(只在 manage_shorts 的 not mirror 分支调用),保证与实盘同进退。"""
    try:
        import cycle_structure
        hs = _closed_hourly(code, 96)
        if len(hs) < 12:
            return False
        r = cycle_structure.expect_check(hs, "short")
        return bool(r.get("expect_dead"))
    except Exception:
        return False


def manage_shorts(cfg, lg, dry=False):
    """空头持仓管理(每轮信号4h粒度 + 每日结算各跑一次):
    退出优先级:强平守卫 > 镜像止损/硬止损 > 镜像止盈 > 部分止盈(-1.5%平2/3) >
    全止盈(-3%) > VWAP收复 > 时间止损(24h未达±1%) > P12空头趋势证伪。
    镜像单只吃:强平守卫/镜像止损/镜像止盈。返回 events 列表。"""
    from crypto_util import fmt_price, liq_guard_triggered
    sc = cfg["crypto_short"]
    ex = sc["exit"]
    events = []
    for p in list(lg["positions"]):
        code, entry = p["code"], p.get("entry") or 0
        qty = _pos_qty(p)
        if qty <= 0 or entry <= 0:
            continue
        mark = realtime_price(code) or entry
        p["mark"] = fmt_price(mark)
        lev = p.get("leverage", sc["account"]["leverage"])
        liq = p.get("liq_price") or entry * (1 + 1.0 / lev - ex["liq_buffer"])
        mirror = _is_mirror(p)
        reason, frac = None, 1.0
        if liq_guard_triggered(mark, liq):
            reason = "强平守卫(mark距强平价<2%%,强平价%s)" % fmt_price(liq)
        elif p.get("stop_loss") and mark >= p["stop_loss"]:
            reason = "镜像止损(mark>=%s)" % fmt_price(p["stop_loss"])
        elif not mirror and mark >= entry * (1 + ex["hard_stop_pct"]):
            reason = "硬止损+1.5%%(保证金约-15%%)"
        elif p.get("take_profit") and mark <= p["take_profit"]:
            reason = "镜像止盈(mark<=%s)" % fmt_price(p["take_profit"])
        elif not mirror:
            if not p.get("partial_tp_done") and mark <= entry * (1 + ex["partial_tp_pct"]):
                reason = "部分止盈-1.5%平2/3(镜像用户盈利先卖2/3)"
                frac = 2.0 / 3.0
            elif mark <= entry * (1 + ex["full_tp_pct"]):
                reason = "止盈-3%全平"
            else:
                evw = p.get("entry_vwap_h")
                hb = _closed_hourly(code, 6)
                if evw and hb and hb[-1]["close"] >= evw * ex["vwap_reclaim_mult"]:
                    reason = "VWAP收复平空(小时收盘站上开仓小时VWAP×1.005)"
                elif _hours_open(p) >= ex["time_stop_hours"] and abs(mark / entry - 1) < 0.01:
                    reason = "时间止损(持仓超24h且|涨跌|<1%)"
                elif _expect_dead_short(code):
                    reason = "不及预期平空(P30反弹时长≥下跌2.0x)"
                elif not s_p25_bars_ok(code):
                    reason = "P12轮动:空头趋势证伪(S-P25翻多)"
        if reason:
            pnl = _close_short_qty(cfg, lg, p, qty * frac, mark, reason, dry)
            events.append((p, reason, qty * frac, mark, pnl))
            if not dry and reason.startswith("不及预期平空") and frac >= 1.0:
                from datetime import timezone
                lg.setdefault("expect_cooldown", {})[code] = datetime.now(
                    timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            print("  COVER %s %s %s qty=%.6f @%s pnl=%+.2f" % (
                p["code"], p.get("name"), reason, qty * frac, fmt_price(mark), pnl))
    if not dry:
        lg["positions"] = [p for p in lg["positions"] if _pos_qty(p) > 1e-12]
        save_ledger(lg)
    return events


def short_kill_check(cfg, lg, dry=False):
    """空头 kill:单笔保证金亏损≥30% 或 单日已实现/保证金基数≤-20% -> 停新开空,平仓照常。
    独立记账本内 short_kill,不碰 logs/kill_switch.json。"""
    if short_kill_armed(lg):
        return True
    kc = cfg["crypto_short"]["kill"]
    today = _today()
    ds = _short_day_stats(lg, today)
    trig = None
    for t in lg.get("closed", []):
        if t.get("exit_time") == today and t.get("side") == "short":
            mg = t.get("margin") or 0
            if mg and t.get("pnl_margin", 0) / mg <= -kc["single_loss_margin_pct"]:
                trig = "单笔保证金亏损%.0f%%≥30%%(%s)" % (
                    t["pnl_margin"] / mg * 100, t["code"])
                break
    if not trig:
        base = ds.get("margin_base", 0)
        if base > 0 and ds.get("realized", 0) / base <= -kc["day_loss_margin_pct"]:
            trig = "单日已实现%+.0f/保证金基数%.0f≤-20%%" % (ds["realized"], base)
    if trig and not dry:
        _arm_short_kill(lg, trig)
        save_ledger(lg)
        log_decision(today, {"session": "settle", "action": "SHORT_KILL",
                             "why": "空头kill拉起:%s,停新开空(平仓照常)" % trig})
    return bool(trig)


def do_signal_short(dry=False):
    """空头信号链路:持仓exit管理(4h粒度) -> 情绪门禁(镜像) -> S-pool/S-P25/S-P8/S-P24开空。
    P11网格对空头无意义,跳过;P12以趋势证伪平空形式保留在 manage_shorts 内。"""
    from crypto_util import fmt_price
    cfg = load_cfg()
    sc = cfg["crypto_short"]
    lg = load_ledger()
    today = _today()
    # 1) 先管持仓(退出4h粒度)
    events = manage_shorts(cfg, lg, dry)
    # 2) 空头 kill:停新开空,平仓照常
    kill_on = short_kill_check(cfg, lg, dry)
    if kill_on:
        print("SHORT_KILL armed: 停新开空")
        if not dry:
            log_decision(today, {"session": "signal", "action": "SHORT_KILL",
                                 "why": "空头kill拉起中,停止新开空(平仓照常)"})
    # 3) 情绪门禁(镜像):情绪不可验证->fail-closed;过热(>+40)不开空
    mkt = get_market()
    mkt_score = mkt.get("score")
    if mkt_score is None:
        print("market sentiment unavailable, fail-closed: no new shorts")
        if not dry:
            save_ledger(lg)
        return []
    # 4) S-pool
    pool = get_pool()
    if not pool:
        print("no pool")
        return []
    opens = []
    held = {p["code"] for p in lg["positions"]}
    if not kill_on and not (mkt_score > sc["entry"]["sentiment_block_above"]):
        for s in pool.get("pool", []):
            code = s["symbol"]
            if code in held:
                continue
            if _expect_cooldown_skip(cfg, lg, code):
                s["_skip"] = "P30冷却中(不及预期平空后%dh内不开)" % int(
                    (cfg.get("p30_cycle") or {}).get("expect_cooldown_h", 12))
                continue
            if len(lg["positions"]) + len(opens) >= sc["entry"]["max_positions"]:
                break
            if s.get("score", 0) < sc["entry"]["s_pool_score"]:
                # near-miss 样本化(v1.5):主 sleeve 被阈值拦下、但在 [实验阈值,主阈值) 的候选只记录不交易
                if (not dry and SLEEVE == "main" and
                        _near_miss_band(s.get("score", 0), sc["entry"]["s_pool_score"],
                                        (cfg.get("crypto_exp") or {}).get("min_pool_score", 6.0))):
                    record_near_miss(code, "short", s.get("score"), s.get("price") or 0,
                                     "S池分%s在[实验阈值,主阈值)被主阈值%.1f拦下" % (
                                         s.get("score"), sc["entry"]["s_pool_score"]))
                continue
            if not s.get("p25"):
                s["_skip"] = "S-P25空头趋势门未过"
                continue
            price = realtime_price(code) or s.get("price") or 0
            if price <= 0:
                s["_skip"] = "实时价不可验证"
                continue
            ok8, d8 = s_p8_short_trigger(code, price, cfg)
            ok24, d24 = s_p24_short_trigger(code, price, cfg)
            if not (ok8 or ok24):
                s["_skip"] = "无小时触发(S-P8:%s;S-P24:%s)" % (d8.get("why"), d24.get("why"))
                continue
            factors = {"side": "short", "s_p25": True,
                       "s_pool_score": s.get("score"), "s_pool_tags": s.get("tags"),
                       "s_p8": {"trigger": ok8, **d8},
                       "s_p24": {"trigger": ok24, **d24},
                       "sentiment": mkt_score,
                       "entry_price": fmt_price(price)}
            # 统一门影子分(映射口径,供 gate_attribution 拆解;不干预)
            upass, uscore, ubd = unified_gate(
                {"p8_four": ok8 or ok24, "p25": True, "pool_score": s.get("score"),
                 "sentiment": -mkt_score}, cfg)
            factors["gate_shadow"] = {"pass": upass, "score": uscore,
                                      "breakdown": ubd, "mode": "shadow",
                                      "note": "空头映射:情绪取反(越冷越有利空头)"}
            pos = open_short_position(cfg, lg, code, s.get("name") or code,
                                      price, factors, dry)
            if pos:
                opens.append(pos)
                if not dry:
                    log_decision(today, {"session": "signal", "action": "SHORT_OPEN",
                                         "code": code, "name": pos["name"],
                                         "side": "short",
                                         "price": fmt_price(price),
                                         "margin": pos["margin"],
                                         "leverage": pos["leverage"],
                                         "notional": pos["notional"],
                                         "liq_price": pos["liq_price"],
                                         "why": "S池%s分%s + S-P25空头趋势 + %s" % (
                                             s.get("score"), s.get("tags"),
                                             "S-P8小时触发" if ok8 else "S-P24大阴跟随")},
                                 factors=factors)
    else:
        if mkt_score > sc["entry"]["sentiment_block_above"]:
            print("sentiment %.1f 过热,不开新空" % mkt_score)
    # 5) 被筛掉的候选记 SKIP(只记过池分但被拦的,供归因)
    if not dry:
        for s in pool.get("pool", []):
            if s.get("_skip") and s.get("score", 0) >= sc["entry"]["s_pool_score"]:
                log_decision(today, {"session": "signal", "action": "SKIP",
                                     "code": s["symbol"], "name": s.get("name"),
                                     "side": "short",
                                     "why": "空头过池%s分但%s,不开空" % (s["score"], s["_skip"])},
                             factors={"side": "short", "s_pool_score": s.get("score"),
                                      "skip_gate": s["_skip"]})
        save_ledger(lg)
    # 6) 推送:只在有开空/平空/异常时
    if (opens or events) and not dry:
        from push import send as push_send
        title = "📉 模拟盘%s开空%d只 平空%d笔" % (mtag(), len(opens), len(events))
        body = "\n".join("SHORT_OPEN %s%s @%s 保证金%s 10x 强平%s" % (
            p["code"], (" " + p["name"]) if p.get("name") and p.get("name") != p["code"] else "",
            p["entry"], p["margin"], p["liq_price"]) for p in opens)
        body += "\n".join("COVER %s %s %s pnl=%+.2f" % (
            p["code"], p.get("name"), rs, pnl) for p, rs, q, px, pnl in events)
        push_send(title, body.strip())
    print("short signal: 开空 %d 只,平空 %d 笔" % (len(opens), len(events)))
    return opens


def short_equity(lg):
    """空头账本净值:保证金余额 + Σ(保证金+未实现毛利)。"""
    eq = _short_cash(lg)
    for p in lg.get("positions", []):
        entry, qty = p.get("entry") or 0, _pos_qty(p)
        mark = p.get("mark") or entry
        if entry > 0 and qty > 0:
            eq += p.get("margin", 0) + (entry - mark) * qty
    return round(eq, 2)


def do_settle_short(dry=False):
    """空头日结算(bars-append后跑):持仓exit管理 -> 对账 -> kill检查 -> 复盘统计。
    只在有平空/异常时推送,无交易静默。"""
    cfg = load_cfg()
    lg = load_ledger()
    today = _today()
    events = manage_shorts(cfg, lg, dry)
    kill_on = short_kill_check(cfg, lg, dry)
    equity = short_equity(lg)
    lg["equity"] = equity
    lg["updated"] = today
    if not dry:
        save_ledger(lg)
    cl = [t for t in lg.get("closed", []) if t.get("side") == "short"]
    wins = [t for t in cl if t.get("pnl_margin", 0) > 0]
    winrate = len(wins) / len(cl) * 100 if cl else 0
    avg_win = sum(t["pnl_margin"] for t in wins) / len(wins) if wins else 0
    losses = [t for t in cl if t.get("pnl_margin", 0) <= 0]
    avg_loss = sum(t["pnl_margin"] for t in losses) / len(losses) if losses else 0
    rr = abs(avg_win / avg_loss) if avg_loss else 0
    closed_today = [t for t in cl if t.get("exit_time") == today]
    print("=== 空头模拟盘结算 %s (策略%s) ===" % (today, cfg["version"]))
    print("净值 %.0f | 持仓 %d | 保证金余额 %.0f" % (
        equity, len(lg["positions"]), _short_cash(lg)))
    for p in lg["positions"]:
        from crypto_util import margin_ret
        print("  HOLD_SHORT %s 保证金浮盈 %+.1f%%" % (
            p["code"], margin_ret(p["entry"], p.get("mark") or p["entry"],
                                  p.get("leverage", 10)) * 100))
    for t in closed_today:
        print("  COVER %s %s %+.1f%% (%+.0f保证金)" % (
            t["code"], t["reason"], t["ret_pct"], t["pnl_margin"]))
    print("累计: %d笔 胜率%.0f%% 盈亏比%.2f 总盈亏%+.0f(保证金口径)" % (
        len(cl), winrate, rr, sum(t.get("pnl_margin", 0) for t in cl)))
    if (closed_today or events or kill_on) and not dry:
        from push import send as push_send
        lines = ["净值%.0f 持仓%d 保证金余额%.0f" % (
            equity, len(lg["positions"]), _short_cash(lg))]
        for t in closed_today:
            lines.append("COVER %s %s %+.1f%%(%+.0f)" % (
                t["code"], t["reason"], t["ret_pct"], t["pnl_margin"]))
        if kill_on:
            lines.append("🚨 空头kill拉起中,停新开空")
        lines.append("累计%d笔 胜率%.0f%% 盈亏比%.2f 总盈亏%+.0f" % (
            len(cl), winrate, rr, sum(t.get("pnl_margin", 0) for t in cl)))
        br = market_brief("short")  # 空头结算附盘面简报(2026-10-03)
        body = "\n".join(lines) + ("\n\n" + br if br else "")
        push_send("📊 模拟盘%s结算 %s" % (mtag(), today), body)
    return events


def do_preopen(dry=False):
    """P9 预开仓(09:27跑):09:25集合竞价后预挂单,09:30开盘执行,09:45前是交易窗口。
    本步只生成预挂单 logs/preopen_orders_<date>.json,不直接成交。
    10:05 --signal 做执行确认:检查09:30-09:45价格行为,通过才转持仓(成交价=开盘价)。
    门禁: P5装死日 / P3风险偏好低 / P4高开>7%不追(竞价已否决,双保险)。"""
    cfg = load_cfg()
    bcfg = cfg["buy"]
    lg = load_ledger()
    today = _today()
    p = os.path.join(SVC, "logs", "auction_confirm_%s.json" % today)
    try:
        confirm = json.load(open(p)).get("confirm", {})
    except Exception:
        print("no auction_confirm for %s" % today)
        return []
    mkt = latest_premarket()
    mkt_score = mkt.get("score", 0)
    regime = latest_regime()
    if mkt.get("dead_day"):
        print("dead_day: 大跌装死日,不新开仓")
        if not dry:
            log_decision(today, {"session": "preopen", "action": "SKIP_ALL",
                                 "why": "P5装死日,大环境底座门禁=%s" % regime.get("门禁")})
        return []
    water = mkt.get("water", {})
    ra = mkt.get("risk_appetite", {}).get("level")
    min_sent = bcfg["min_market_sentiment"]
    if water.get("direction") == "连续下降":
        min_sent = max(min_sent, bcfg["min_market_sentiment_low_water"])
    if ra == "低":
        min_sent = max(min_sent, bcfg["min_market_sentiment_low_risk"])
    if mkt_score < min_sent:
        print("market sentiment %.1f < %s, skip preopen" % (mkt_score, min_sent))
        if not dry:
            log_decision(today, {"session": "preopen", "action": "SKIP_ALL",
                                 "why": "情绪%.1f<门槛%s,P3不让买" % (mkt_score, min_sent)})
        return []
    held = {x["code"] for x in lg["positions"]}
    orders = []
    for code, cf in confirm.items():
        if not cf.get("confirmed"):
            continue
        if code in held:
            continue
        if len(orders) >= bcfg["max_positions"]:
            break
        price = cf.get("price")
        if not price or price <= 0:
            continue
        if cf.get("gap", 0) > bcfg["max_day_chg"]:
            continue  # P4双保险
        amt = bcfg["amount_per_trade"]
        if lg["cash"] < amt:
            print("cash insufficient")
            break
        orders.append({
            "code": code, "name": cf.get("name"),
            "order_time": today + " 09:25",  # 竞价后预挂单
            "fill_time": today + " 09:30",   # 开盘执行
            "limit_price": round(price, 2),  # 开盘价限价
            "gap": cf.get("gap"),
            "pre_score": cf.get("pre_score"),
            "auction_score": cf.get("auction_score"),
            "auction_notes": cf.get("auction_notes"),
            "yesterday_vwap": cf.get("yesterday_vwap"),
            "market_sentiment": mkt_score,
            "strategy_version": cfg["version"],
            "why": "盘前%d分[%s]+竞价%d分[%s],高开%+.1f%%" % (
                cf.get("pre_score"), "/".join(cf.get("pre_reasons") or [])[:30],
                cf.get("auction_score"), "/".join(cf.get("auction_notes") or [])[:30],
                cf.get("gap", 0)),
        })
    opath = os.path.join(SVC, "logs", "preopen_orders_%s.json" % today)
    if not dry:
        json.dump({"date": today, "orders": orders}, open(opath, "w"),
                  ensure_ascii=False, indent=1)
        for o in orders:
            log_decision(today, {"session": "preopen", "action": "ORDER",
                                 "code": o["code"], "name": o["name"],
                                 "price": o["limit_price"], "why": o["why"],
                                 "regime_gate": regime.get("门禁")})
    print("preopen: 预挂单 %d 只(09:25挂单,09:30执行,09:45前窗口验证)" % len(orders))
    for o in orders:
        print("  ORDER %s %s 限价%.2f 高开%+.1f%%" % (
            o["code"], o["name"], o["limit_price"], o["gap"]))
    if orders and not dry:
        from push import send as push_send
        title = "📋 预开仓挂单 %d只(09:30执行)" % len(orders)
        body = "\n".join("ORDER %s %s 限价%.2f 高开%+.1f%% %s" % (
            o["code"], o["name"], o["limit_price"], o["gap"],
            "/".join(o["auction_notes"] or [])) for o in orders)
        body += "\n\n> 09:25竞价后预挂单 → 09:30开盘执行 → 09:45前窗口验证后转持仓"
        # 重点个股自动配图:挂单的配K线图(最多3只)
        chart_imgs = []
        try:
            from stock_charts import draw_list as _draw
            cdir = os.path.join(SVC, "logs", "charts", today)
            chart_imgs = _draw([(o["code"], o["name"]) for o in orders],
                               cdir, max_n=3)
        except Exception as e:
            print("order charts fail: %s" % e, flush=True)
        push_send(title, body, images=chart_imgs)
    return orders


def confirm_preopen_orders(dry=False):
    """10:05执行确认:预挂单 -> 检查09:30-09:45价格行为 -> 通过转持仓(成交价=开盘价)。
    开盘即破位(09:45价<开盘价×0.98) -> 取消挂单,不转持仓。"""
    cfg = load_cfg()
    bcfg = cfg["buy"]
    lg = load_ledger()
    today = _today()
    p = os.path.join(SVC, "logs", "preopen_orders_%s.json" % today)
    try:
        orders = json.load(open(p)).get("orders", [])
    except Exception:
        return []
    if not orders:
        return []
    # 批量取09:30-09:45的5分钟K验证执行窗口
    import daily_review as dr
    api_syms = [(("sh" if o["code"][0] in "69" else "sz") + o["code"]) for o in orders]
    bars_map = {}
    try:
        d = dr.api("/api/v1/quotes/kline/batch?symbols=%s&period=5&limit=12" %
                   ",".join(api_syms), timeout=30)["data"]
        for k, v in (d or {}).items():
            bars_map[k.split(".")[0]] = v
    except Exception as e:
        print("exec window bars failed: %s" % str(e)[:60])
    filled = []
    for o in orders:
        code = o["code"]
        bars = bars_map.get(code) or []
        tb = [b for b in bars if b["time"][:10] == today and "09:30" <= b["time"][11:16] <= "09:45"]
        limit = o["limit_price"]
        if tb:
            w45 = tb[-1]["close"]
            wlow = min(b["low"] for b in tb)
            # 开盘即破位:09:45收盘<开盘价×0.98 -> 取消
            if w45 < limit * 0.98:
                print("  CANCEL %s %s 开盘即破位(09:45 %.2f<开盘%.2f×0.98)" % (
                    code, o["name"], w45, limit))
                if not dry:
                    log_decision(today, {"session": "confirm", "action": "CANCEL",
                                         "code": code, "name": o["name"],
                                         "why": "09:30-09:45窗口开盘即破位,挂单取消"})
                continue
            fill_px = limit  # 限价单开盘按开盘价成交
        else:
            fill_px = limit  # 无窗口数据,按开盘价假设成交
        amt = bcfg["amount_per_trade"]
        if lg["cash"] < amt:
            print("cash insufficient")
            break
        shares = _lot_shares(amt, fill_px)
        if shares <= 0:
            continue
        _cash_out(lg, shares * fill_px)
        yvwap = o.get("yesterday_vwap")
        pos = {
            "code": code, "name": o["name"], "buy_date": today,
            "buy_price": round(fill_px, 2), "shares": shares,
            "cost": round(shares * fill_px, 2),
            "locked": shares, "locked_until": _lock_until(_today()),  # T+1:次一交易日解禁
            "buy_vwap": round(yvwap, 2) if yvwap else None,
            "buy_vwap10": None, "adds": 0,
            "strategy_version": cfg["version"],
            "snapshot": {
                "source": "竞价预开仓",
                "order_time": o["order_time"], "fill_time": o["fill_time"],
                "pre_score": o.get("pre_score"),
                "auction_score": o.get("auction_score"),
                "auction_notes": o.get("auction_notes"),
                "gap": o.get("gap"),
                "market_sentiment": o.get("market_sentiment"),
                # P23:买入必须带预期,不及预期平仓
                "expect": {"days": 5, "target_pct": 2.0,
                           "why": "预开仓买入后5个交易日内创新高(高于买入价2%),不及预期平仓"},
            },
        }
        lg["positions"].append(pos)
        filled.append(pos)
    if not dry:
        save_ledger(lg)
        for b in filled:
            log_decision(today, {"session": "confirm", "action": "FILL",
                                 "code": b["code"], "name": b["name"],
                                 "price": b["buy_price"],
                                 "why": "09:30-09:45窗口守住开盘价,按开盘价成交"})
    print("preopen: 执行确认 %d/%d 转持仓" % (len(filled), len(orders)))
    for b in filled:
        print("  FILL %s %s %.2f x %d" % (b["code"], b["name"], b["buy_price"], b["shares"]))
    return filled


def main():
    global MARKET, SIDE, SLEEVE
    if "--market" in sys.argv:
        i = sys.argv.index("--market")
        MARKET = sys.argv[i + 1].upper() if i + 1 < len(sys.argv) else "CN"
        if MARKET not in ("CN", "US", "CRYPTO"):
            print("unknown market", MARKET)
            return
    if "--side" in sys.argv:
        i = sys.argv.index("--side")
        SIDE = sys.argv[i + 1].lower() if i + 1 < len(sys.argv) else "long"
        if SIDE not in ("long", "short"):
            print("unknown side", SIDE)
            return
        if SIDE == "short" and MARKET != "CRYPTO":
            print("ERROR: --side short 只允许 --market CRYPTO")
            sys.exit(2)
    if "--sleeve" in sys.argv:
        i = sys.argv.index("--sleeve")
        SLEEVE = sys.argv[i + 1].lower() if i + 1 < len(sys.argv) else "main"
        if SLEEVE not in ("main", "exp"):
            print("unknown sleeve", SLEEVE)
            return
        if SLEEVE == "exp" and MARKET != "CRYPTO":
            print("ERROR: --sleeve exp 只允许 --market CRYPTO")
            sys.exit(2)
    from trading_calendar import guard_trading_day
    if "--kill" in sys.argv:  # kill switch 不受交易日门控,随时可操作
        i = sys.argv.index("--kill")
        op = sys.argv[i + 1].lower() if i + 1 < len(sys.argv) else "status"
        if op == "on":
            arm_kill_switch("手动拉起")
            print("kill switch ARMED")
        elif op == "off":
            disarm_kill_switch("手动解除")
            print("kill switch DISARMED")
        else:
            print("kill switch armed:", kill_switch_armed())
        return
    guard_trading_day("paper_trade", MARKET)  # 非交易日静默跳过(国庆等休市)
    dry = "--dry-run" in sys.argv or "--dry" in sys.argv  # --dry为别名,防误落账
    if "--signal" in sys.argv:
        (do_signal_short if SIDE == "short" else do_signal)(dry)
    elif "--settle" in sys.argv:
        (do_settle_short if SIDE == "short" else do_settle)(dry)
    elif "--preopen" in sys.argv:
        do_preopen(dry)
    else:
        print("usage: paper_trade.py [--market CN|US|CRYPTO] [--side long|short] [--sleeve main|exp] --signal|--settle|--preopen [--dry-run] | --kill on|off|status")


if __name__ == "__main__":
    main()
