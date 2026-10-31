"""只读交易中心 PAPER 账本，投影跨日买卖过程；不创建内核、不生成订单。"""
import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path


def read_paper_account(root):
    path = Path(root) / "logs/paper_account_state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data.get("positions"), dict) or not isinstance(data.get("orders"), list):
            raise ValueError("PAPER快照缺少持仓/成交字段")
        data["source_path"] = str(path.resolve())
        data["source_mtime"] = path.stat().st_mtime
        data["read_status"] = "READY"
    except (OSError, ValueError, TypeError) as exc:
        return {"read_status": "UNAVAILABLE", "source_path": str(path), "error": str(exc)}
    ledger = Path(root) / "ats/config/ipo_trading_ledger.json"
    try:
        data["center"] = json.loads(ledger.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        data["center"] = {}
    return data


def _stamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def read_shadow_days(root, asof_day):
    series, errors = {}, 0
    for path in sorted((Path(root) / "logs/fusion_shadow").glob("????-??-??.jsonl")):
        day = path.stem
        if day > asof_day:
            continue
        by_code = defaultdict(list)
        with path.open(encoding="utf-8-sig") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    code = str(row["code"]).split(".")[0].zfill(6)
                    by_code[code].append(row)
                except (ValueError, TypeError, KeyError):
                    errors += 1
        series[day] = dict(by_code)
    return series, errors


def build_paper_follow(snapshot, observations, asof_day):
    """逐笔 FIFO 计算已实现收益；当前数量/可卖量始终服从原账户快照。"""
    if snapshot.get("read_status") != "READY":
        return {"rows": [], "account": snapshot}
    cutoff = datetime.strptime(asof_day, "%Y-%m-%d").replace(hour=23, minute=59, second=59).timestamp()
    historical = asof_day < str(snapshot.get("trade_date") or "")
    signals = {row["code"]: row for row in observations}
    center = snapshot.get("center") or {}
    directives = {}
    for entry in list(center.get("directive_history") or []) + list(center.get("signal_iteration_log") or []):
        key = entry.get("directive_id") or entry.get("request_id")
        if key:
            directives[str(key)] = entry
    pending = {str(p.get("code") or "").zfill(6): p for p in center.get("pending_exit_intents") or []}
    cycles, active, lots, seen = [], {}, defaultdict(deque), set()

    def new_cycle(code, order):
        row = {"code": code, "entry_time": order.get("timestamp", ""), "exit_time": "",
               "bought": 0.0, "sold": 0.0, "buy_value": 0.0, "remaining": 0.0,
               "realized": 0.0, "sold_cost": 0.0, "events": [], "issues": [],
               "last_price": None, "last_ts": 0.0, "directive": "", "exit_status": ""}
        cycles.append(row)
        return row

    orders = sorted(snapshot["orders"], key=lambda o: _stamp(o.get("timestamp")))
    for order in orders:
        ts = _stamp(order.get("timestamp"))
        code = str(order.get("code") or "").strip().zfill(6)
        action = str(order.get("action") or "").upper()
        price, volume = float(order.get("price") or 0), float(order.get("volume") or 0)
        if not 0 < ts <= cutoff or price <= 0 or volume <= 0 or action not in {"BUY", "ADD", "SELL", "REDUCE"}:
            continue
        identity = str(order.get("order_id") or "")
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        row = active.get(code)
        if row is None:
            row = new_cycle(code, order)
            active[code] = row
            if action not in {"BUY", "ADD"}:
                row["entry_time"] = ""
                row["issues"].append("缺少买入成本")
        fee = float(order.get("fee") or 0)
        row["events"].append(dict(order))
        row["last_price"], row["last_ts"] = price, ts
        request = str(order.get("request_id") or "")
        directive = directives.get(request) or directives.get(request.rsplit(":", 1)[0])
        if directive and str(directive.get("code") or "").zfill(6) == code:
            row["directive"] = str(directive.get("directive_id") or request)
        if action in {"BUY", "ADD"}:
            row["bought"] += volume
            row["buy_value"] += price * volume
            row["remaining"] += volume
            lots[code].append([volume, price, fee / volume])
            continue
        row["sold"] += volume
        remaining = volume
        while remaining > 1e-9 and lots[code]:
            lot = lots[code][0]
            matched = min(remaining, lot[0])
            row["realized"] += matched * (price - lot[1] - lot[2] - fee / volume)
            row["sold_cost"] += matched * lot[1]
            lot[0] -= matched
            remaining -= matched
            if lot[0] <= 1e-9:
                lots[code].popleft()
        if remaining > 1e-9:
            row["issues"].append("卖出数量缺少对应买入")
        row["remaining"] = max(0.0, row["remaining"] - volume)
        # 服从现有 PaperAdapter 的 SELL 整仓语义，异常旧数量不推算虚假利润。
        if action == "SELL" and row["remaining"] > 1e-9:
            row["issues"].append("SELL整仓记录数量不一致")
            row["remaining"] = 0.0
            lots[code].clear()
        if row["remaining"] <= 1e-9:
            row["exit_time"] = str(order.get("timestamp") or "")
            active.pop(code, None)

    positions = {str(c).zfill(6): p for c, p in snapshot["positions"].items()}
    if not historical:
        for code, position in positions.items():
            if code not in active:
                row = new_cycle(code, {"timestamp": position.get("entry_time") or ""})
                row["issues"].append("快照持仓未匹配买入流水")
                active[code] = row
        for code, row in active.items():
            position = positions.get(code, {})
            quantity = float(position.get("volume") or 0)
            if abs(quantity - row["remaining"]) > 1e-6:
                row["issues"].append("流水/持仓数量待对账")
            row["remaining"] = quantity
            row["sellable"] = position.get("sellable_qty", position.get("available_shares"))
            row["last_price"] = position.get("current_price")
            row["holding_cost"] = position.get("entry_price")
            intent = pending.get(code, {})
            if _stamp(intent.get("exit_requested_at")) >= _stamp(row["entry_time"]):
                row["exit_status"] = str(intent.get("exit_status") or "")
    for row in cycles:
        observation = signals.get(row["code"], {})
        entry_ts = _stamp(row["entry_time"])
        linked = observation and entry_ts and observation["first_ts"] <= entry_ts
        row["name"] = observation.get("name") or (center.get("name_snapshot") or {}).get(row["code"], "")
        row["signal_day"] = observation["first_day"] if linked else ""
        row["signal_price"] = observation["reference"] if linked else None
        row["association"] = "交易中心指令ID" if row["directive"] else "同码先于买入的观察参考（非归因）" if linked else "无已匹配信号"
        row["buy_price"] = row["buy_value"] / row["bought"] if row["bought"] else row.get("holding_cost")
        cost = float(row.get("holding_cost") or (lots[row["code"]][0][1] if active.get(row["code"]) is row and lots[row["code"]] else 0))
        if historical:
            cost = sum(v * p for v, p, f in lots[row["code"]]) / row["remaining"] if active.get(row["code"]) is row and row["remaining"] else 0
        row["floating_pct"] = (float(row["last_price"]) / cost - 1) * 100 if row["remaining"] and row["last_price"] and cost > 0 else None
        row["realized_pct"] = row["realized"] / row["sold_cost"] * 100 if row["sold_cost"] else None
        row["status"] = "账本待核" if row["issues"] else row["exit_status"] or ("持仓" if row["remaining"] else "已平仓")
        row["data_status"] = "历史成交投影" if historical else "持仓快照截至" + str(snapshot.get("trade_date") or "未知")
        if row["issues"]:
            row["realized"] = row["realized_pct"] = None
    return {"rows": sorted(cycles, key=lambda r: r["last_ts"] or _stamp(r["entry_time"]), reverse=True), "account": snapshot}
