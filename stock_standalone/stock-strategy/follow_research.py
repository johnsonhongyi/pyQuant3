"""Read-only evidence and conditional plans for the existing paper execution gate."""
from urllib.parse import urlencode
import time


def stock_plan(stock, quote, minute, daily, cfg, now, previous_day, state):
    import auto_follow as af
    plan = {"checked_at": now.isoformat(), "trade_time": quote.get("trade_time"),
            "source": quote.get("meta", {}).get("source"), "meta": quote.get("meta", {}),
            "basis": "paper-follow-v1", "metrics": {}, "conditions": [], "errors": []}
    m = plan["metrics"]
    for name in ("price", "change_percent", "open", "high", "previous_close"):
        try:
            m[name] = af.number(quote[name])
        except (KeyError, ValueError, TypeError):
            plan["errors"].append(name + " unavailable")
    completed = sorted((b for b in daily if str(b["time"])[:10] < now.date().isoformat()), key=lambda b: b["time"])
    plan["daily_trade_date"] = str(completed[-1]["time"])[:10] if completed else None
    try:
        if len(completed) < 20 or plan["daily_trade_date"] != previous_day:
            raise ValueError("previous completed trading day unavailable")
        if any(b.get("meta", {}).get("stale") is not False or not b.get("meta", {}).get("source") for b in completed[-20:]):
            raise ValueError("daily source unavailable")
        m.update({"vwap" + str(n): af.exact_vwap(completed[-n:]) for n in (1, 3, 5, 10)})
        m["ma20"] = sum(af.number(b["close"]) for b in completed[-20:]) / 20
    except (KeyError, ValueError, TypeError) as exc:
        plan["errors"].append(str(exc))
    today = sorted((b for b in minute if str(b["time"])[:10] == now.date().isoformat()
                    and af.stamp(b["time"]) <= now), key=lambda b: b["time"])
    try:
        if len(today) < 4 or (now - af.stamp(today[-1]["time"])).total_seconds() > 360:
            raise ValueError("intraday bars unavailable")
        for b in today:
            af.fresh(b["meta"], now, 600)
        m["intraday_vwap"] = af.exact_vwap(today)
        plan["minute_trade_time"] = today[-1]["time"]
        m["entry_low"] = m["intraday_vwap"] * 1.005
        m["entry_high"] = m["intraday_vwap"] * 1.025
        last = today[-3:]
        m["volume_price_rising"] = len(last) == 3 and all(af.number(b["close"]) >= af.number(a["close"]) and
            af.number(b["volume"]) >= af.number(a["volume"]) for a, b in zip(last, last[1:]))
    except (KeyError, ValueError, TypeError) as exc:
        plan["errors"].append(str(exc))
    try:
        if af.symbol(quote["symbol"]) != stock["symbol"]:
            raise ValueError("quote symbol mismatch")
        af.entry_ok(quote, minute, daily, cfg, now, previous_day)
        plan["structure_ready"] = True
        plan["blocker"] = None
    except (KeyError, ValueError, TypeError) as exc:
        plan["structure_ready"] = False
        plan["blocker"] = str(exc)
    try:
        af.quote_ok(quote, now)
        plan["fresh_quote"] = True
    except (KeyError, ValueError, TypeError):
        plan["fresh_quote"] = False
    plan["conditions"] = ["报价与分钟线须为当日有效数据，日线须覆盖上一完整交易日",
        "P4：0 < 当日涨幅 ≤ %s%%，封涨停不假定成交" % cfg["buy"]["max_day_chg"],
        "P25：昨日 VWAP1 > VWAP3 > VWAP5，昨日收盘 ≥ MA20",
        "P8：现价位于当日 VWAP × 1.005～1.025，当日 VWAP ≥ VWAP3",
        "最近三根分钟线价格与成交量连续不降；冲高回落、高开低走否决",
        "结构通过后仍检查市场情绪、交易时段、开关、仓位、现金与当日去重"]
    valid = plan["fresh_quote"] and not plan["errors"]
    def check(name, result):
        return {"name": name, "status": "pass" if valid and result else "fail" if valid else "unknown"}
    plan["checks"] = [
        check("P4 涨幅", 0 < m.get("change_percent", -999) <= cfg["buy"]["max_day_chg"]),
        check("P25 多日趋势", m.get("vwap1", 0) > m.get("vwap3", 0) > m.get("vwap5", 0) and bool(completed) and af.number(completed[-1]["close"]) >= m.get("ma20", float("inf"))),
        check("P8 VWAP 区间", m.get("entry_low", float("inf")) <= m.get("price", 0) <= m.get("entry_high", 0) and m.get("intraday_vwap", 0) >= m.get("vwap3", float("inf"))),
        check("P8 量价连续", m.get("volume_price_rising") is True),
        check("冲高回落否决", not (m.get("change_percent", 0) > 3 and m.get("price", 0) < m.get("high", 0) * .99)),
        check("高开低走否决", not (m.get("open", 0) >= m.get("previous_close", float("inf")) * 1.02 and m.get("price", 0) < m.get("open", 0)))]
    price = m.get("price", 0)
    if price > 0:
        plan["reference_shares"] = int(min(cfg["buy"]["amount_per_trade"], state["cash"]) / price / 100) * 100
        plan["reference_amount"] = plan["reference_shares"] * price
        plan["take_profit_reference"] = price * (1 + cfg["sell"]["take_profit"])
        plan["stop_loss_reference"] = price * (1 + cfg["sell"]["stop_loss"])
    plan["response"] = "结构满足，等待执行层再次校验" if plan["structure_ready"] else "等待条件修复；未通过不模拟开仓"
    blocker = plan.get("blocker")
    if plan["fresh_quote"]:
        responses = {"P4 change gate": "涨幅不在允许区间，等待降温后重新评估，不追涨",
            "P25 trend gate": "多日趋势尚未满足，保留观察，等待趋势恢复",
            "P8 volume-price gate": "等待最近三根量价连续确认，当前不抢跑",
            "intraday pullback veto": "冲高回落，暂缓入场，等待重新站稳且量价恢复",
            "opening trap": "高开低走触发否决，等待结构修复",
            "sealed limit-up": "涨停封板，无法验证可成交，不假定买入"}
        plan["response"] = responses.get(blocker, plan["response"])
        if blocker == "P8 VWAP gate" and "intraday_vwap" in m:
            plan["response"] = "回落至 VWAP 区间下方，等待重新站稳" if m.get("price", 0) < m["entry_low"] else "VWAP 偏离或多日站位不符，等待回归有效区间，不追高"
    else:
        plan["response"] = "报价未通过当日新鲜度检查，仅保留条件参考，不模拟开仓"
    blocks = []
    if state.get("kill"):
        blocks.append("账户风控停止")
    if state.get("enabled") is False:
        blocks.append("暂停新开仓")
    if not ("09:30" <= now.strftime("%H:%M") < "11:30" or "13:00" <= now.strftime("%H:%M") < "15:00"):
        blocks.append("非连续交易时段")
    if len(state["positions"]) >= cfg["buy"]["max_positions"]:
        blocks.append("持仓数量已达上限")
    if not state.get("market") or state.get("cycle_status") in ("market_gate", "degraded"):
        blocks.append("市场门禁未确认通过")
    if any(p["symbol"] == stock["symbol"] for p in state["positions"]):
        blocks.append("已有持仓，监控退出而非重复买入")
    plan["execution_blockers"] = blocks
    plan["invalidation"] = "放弃追高：超涨幅上限、偏离 VWAP、量价转弱或市场门禁未通过；下一轮重新检查"
    plan["exit_plan"] = "成交后按实际成本重算止盈止损，并监控买入日 VWAP、十日 VWAP 与持有期限；遵守 T+1，跌停不假定卖出"
    return plan


def rotation_snapshot(payload, previous, now):
    import auto_follow as af
    meta = payload.get("meta", {})
    error = None
    try:
        af.fresh(meta, now, 1800)
        if not meta.get("trade_date"):
            raise ValueError("资金流缺少交易日，只作来源快照参考")
    except (KeyError, ValueError, TypeError) as exc:
        error = str(exc)
    rows = []
    for item in payload.get("data", []):
        try:
            item_meta = item.get("meta", meta)
            try:
                af.fresh(item_meta, now, 1800)
            except (KeyError, ValueError, TypeError) as exc:
                error = str(exc)
            fields = item_meta.get("available_fields", [])
            field = "main_net_inflow" if "main_net_inflow" in fields else "net_inflow"
            if field not in fields:
                continue
            flow = af.number(item[field])
            rows.append({"code": item["code"], "name": item["name"], "net_flow": flow, "flow_field": field,
                         "change_percent": af.number(item["change_percent"]) if "change_percent" in fields else None,
                         "meta": item_meta})
        except (KeyError, ValueError, TypeError):
            continue
    rows.sort(key=lambda r: (-r["net_flow"], r["code"]))
    comparable = not error and previous.get("meta", {}).get("trade_date") == meta.get("trade_date") and bool(meta.get("trade_date")) and not previous.get("error")
    old = {r["code"]: r for r in previous.get("rows", [])} if comparable else {}
    # Repeated cached payload is not another rotation observation.
    changed = meta.get("fetched_at") != previous.get("meta", {}).get("fetched_at")
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
        before = old.get(row["code"])
        if before and before.get("flow_field") == row["flow_field"] and before.get("meta", {}).get("source") == row["meta"].get("source") and changed:
            row["rank_change"] = before["rank"] - rank
            row["flow_change"] = row["net_flow"] - before["net_flow"]
        elif before:
            for key in ("rank_change", "flow_change"):
                if key in before:
                    row[key] = before[key]
    return {"checked_at": now.isoformat(), "meta": meta, "error": error, "rows": rows,
            "coverage": len(rows), "unit": "CNY", "comparison_at": previous.get("meta", {}).get("fetched_at") if comparable and changed else previous.get("comparison_at")}


def refresh_research(state, cfg, api, now, calendar, force=False, should_stop=None, clock=None):
    import auto_follow as af
    prior = state.get("research", {})
    if not force and prior.get("checked_at") and 0 <= (now - af.stamp(prior["checked_at"])).total_seconds() < 300:
        return
    research = {"checked_at": now.isoformat(), "errors": [], "execution": "paper-only"}
    deadline = time.monotonic() + 40
    state["research"] = research
    for dimension in ("industry", "theme"):
        try:
            payload = api("/api/v1/market/flows?dimension=%s&sort=net&limit=200" % dimension)
            research[dimension] = rotation_snapshot(payload, prior.get(dimension, {}), now)
        except (KeyError, ValueError, TypeError, OSError) as exc:
            research[dimension] = {"rows": [], "error": str(exc), "coverage": 0}
    overview = None
    try:
        overview = api("/api/v1/themes/overview")
        state["themes"] = [{"id": t["theme"], "name": t["name"], "change_percent": t.get("change_percent"),
            "main_net_inflow": t.get("main_net_inflow"), "rising_nodes": t.get("rising_nodes"),
            "falling_nodes": t.get("falling_nodes"), "source": overview.get("meta", {}).get("source"),
            "snapshot_at": overview.get("meta", {}).get("fetched_at")} for t in overview["data"]]
        ladder = api("/api/v1/short-term/limit-up-ladder")["data"]
        previous_day = calendar.prev_trading_day(now.date().isoformat(), market="CN")
        pool = af.candidates(ladder, overview, now, previous_day, state.get("settings", {}))
        research["pool_mode"] = "current"
    except (KeyError, ValueError, TypeError, OSError) as exc:
        # Preserve identities with their original evidence date; never admit them to execution.
        research["errors"].append(str(exc))
        pool = state.get("candidates", [])
        if not pool and overview:
            selected = state.get("settings", {})
            reference = {}
            for theme in sorted(overview["data"], key=lambda t: af.number(t.get("change_percent", 0)), reverse=True):
                if selected.get("theme_ids") and theme["theme"] not in selected["theme_ids"]:
                    continue
                if selected.get("theme_trend", True) and len(reference) < 15:
                    for stock in theme.get("leader_stocks", [])[:5]:
                        try:
                            code = af.symbol(stock["symbol"])
                            if "ST" not in stock.get("name", "").upper():
                                reference.setdefault(code, {"symbol": code, "name": stock.get("name"), "route": "theme_trend",
                                    "theme": theme["theme"], "status": "reference", "reason": "reference_only"})
                        except (KeyError, ValueError, TypeError):
                            continue
            pool = list(reference.values())[:20]
        research["pool_mode"] = "retained_reference"
        previous_day = calendar.prev_trading_day(now.date().isoformat(), market="CN")
    existing = {c["symbol"]: c for c in state.get("candidates", [])}
    codes = {c["symbol"] for c in pool}
    for held in state["positions"]:
        if held["symbol"] not in codes:
            pool.append({k: held[k] for k in ("symbol", "name", "route", "theme", "streak") if k in held})
    for stock in pool:
        if existing.get(stock["symbol"], {}).get("plan"):
            stock["plan"] = existing[stock["symbol"]]["plan"]
    pool.sort(key=lambda c: existing.get(c["symbol"], {}).get("plan", {}).get("checked_at", ""))
    for stock in pool:
        old = existing.get(stock["symbol"], {})
        for key in ("status", "reason", "price", "change_percent", "source", "trade_time", "plan"):
            if key in old:
                stock[key] = old[key]
        if should_stop and should_stop():
            research["errors"].append("pending_stop_command")
            break
        if time.monotonic() >= deadline:
            research["errors"].append("研究时间预算已到，保留原计划，后续轮次优先补齐旧计划")
            break
        try:
            code = stock["symbol"]
            q = api("/api/v1/quotes/realtime?" + urlencode({"symbols": code}))["data"][0]
            minute = api("/api/v1/quotes/kline?" + urlencode({"symbol": code, "period": "5", "limit": 60}))["data"]
            daily = api("/api/v1/quotes/kline?" + urlencode({"symbol": code, "period": "day", "limit": 30}))["data"]
            plan = stock_plan(stock, q, minute, daily, cfg, clock() if clock else now, previous_day, state)
            stock["plan"] = plan
        except (KeyError, ValueError, TypeError, OSError) as exc:
            stock["plan"] = {"checked_at": now.isoformat(), "errors": [str(exc)], "response": "数据缺失，等待补齐，禁止据此开仓"}
    state["candidates"] = pool
