# -*- coding: utf-8 -*-
"""ats/fusion/trade_sim.py — A股 T+1 约束下的订单与持仓模拟。

为什么必须单独一层：
    融合层输出的是"几级、多大仓、在哪进、错在哪出"，但 A 股是 T+1：
    **当日买入的股份当日不能卖**。这意味着
        1) 买入当天的止损位在物理上不可执行，只能等次日；
        2) 早盘诱多的最大风险不是"买贵了"，而是"买贵了还跑不掉"；
        3) VWAP 结构的作用是控制回撤，但它的兑现点也在次日。
    所以"信号对不对"和"这笔单子能不能活着出来"是两个问题，必须分开算。

本模块只做三件事：
    1. 把决策变成订单：什么时间、什么价、多少仓、何时可卖；
    2. 按 T+1 规则推进持仓：买入日只记录不卖出，次日起才允许止损/止盈；
    3. 输出每笔交易的买入价、卖出价、盈亏、当日不可控回撤、以及"本可止损但被 T+1 锁住"的代价。

不做：真实撮合、滑点建模、涨跌停无法成交的极端情形（仅按开盘价兜底）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ats.fusion.names import name_of

_ENTRY_WINDOWS = (
    (9 * 60 + 30, 10 * 60 + 30, "开盘30分"),
    (10 * 60 + 30, 13 * 60, "上午"),
    (13 * 60, 14 * 60 + 30, "午后"),
    (14 * 60 + 30, 15 * 60 + 1, "尾盘"),
)


def _window_of(ts: float) -> str:
    lt = time.localtime(ts)
    minutes = lt.tm_hour * 60 + lt.tm_min
    for lo, hi, name in _ENTRY_WINDOWS:
        if lo <= minutes < hi:
            return name
    return "其他"


def _day_str(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


@dataclass
class Order:
    code: str
    signal_ts: float
    order_ts: float
    side: str = "BUY"
    price_lo: float = 0.0
    price_hi: float = 0.0
    fill_price: float = 0.0
    size_pct: float = 0.0
    tier: int = 0
    stop: float = 0.0
    sellable_date: str = ""
    status: str = "PENDING"   # FILLED / EXPIRED / NO_DATA
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "signal_time": time.strftime("%H:%M", time.localtime(self.signal_ts)),
            "order_time": time.strftime("%H:%M", time.localtime(self.order_ts)) if self.order_ts else "-",
            "side": self.side,
            "band": [round(self.price_lo, 3), round(self.price_hi, 3)],
            "fill_price": round(self.fill_price, 3),
            "size_pct": self.size_pct,
            "tier": self.tier,
            "stop": round(self.stop, 3),
            "sellable_date": self.sellable_date,
            "status": self.status,
            "note": self.note,
        }


@dataclass
class Trade:
    code: str
    tier: int
    entry_ts: float
    entry_price: float
    size_pct: float
    stop: float
    sellable_date: str
    exit_ts: float = 0.0
    exit_price: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = "OPEN"
    hold_days: int = 0
    day0_mae_pct: float = 0.0       # 买入当日不可控回撤
    mfe_pct: float = 0.0
    stop_blocked: bool = False      # 当日触发止损但 T+1 无法执行
    blocked_loss_pct: float = 0.0   # 被锁住的额外损失（相对止损价）

    @property
    def entry_window(self) -> str:
        return _window_of(self.entry_ts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": name_of(self.code),
            "tier": self.tier,
            "entry_time": time.strftime("%m-%d %H:%M", time.localtime(self.entry_ts)),
            "entry_price": round(self.entry_price, 3),
            "size_pct": self.size_pct,
            "stop": round(self.stop, 3),
            "sellable_date": self.sellable_date,
            "window": self.entry_window,
            "exit_time": time.strftime("%m-%d %H:%M", time.localtime(self.exit_ts)) if self.exit_ts else "-",
            "exit_price": round(self.exit_price, 3),
            "pnl_pct": round(self.pnl_pct, 2),
            "exit_reason": self.exit_reason,
            "hold_days": self.hold_days,
            "day0_mae_pct": round(self.day0_mae_pct, 2),
            "mfe_pct": round(self.mfe_pct, 2),
            "stop_blocked": self.stop_blocked,
            "blocked_loss_pct": round(self.blocked_loss_pct, 2),
        }


class T1Simulator:
    """基于 3 分钟线的 T+1 订单/持仓模拟。"""

    def __init__(self, cache: Dict[str, np.ndarray], trading_days: Optional[List[str]] = None):
        self.cache = cache
        self.days = trading_days or []
        self._day_idx = {d: i for i, d in enumerate(self.days)}

    # -- 取数 -------------------------------------------------------------
    def _next_day(self, day: str) -> Optional[str]:
        i = self._day_idx.get(day)
        if i is None or i + 1 >= len(self.days):
            return None
        return self.days[i + 1]

    def _bars_of(self, code: str, day: str) -> Optional[Dict[str, np.ndarray]]:
        arr = self.cache.get(code)
        if arr is None or len(arr) == 0:
            return None
        st = time.strptime(day, "%Y-%m-%d")
        start = int(time.mktime((st.tm_year, st.tm_mon, st.tm_mday, 0, 0, 0, 0, 0, -1)))
        ts = arr["time"].astype("int64")
        mask = (ts >= start) & (ts < start + 86400)
        if not mask.any():
            return None
        sub = arr[mask]
        v = sub["volume"].astype("float64")
        close = sub["close"].astype("float64")
        high = sub["high"].astype("float64")
        low = sub["low"].astype("float64")
        tp = (high + low + close) / 3.0
        cum_v = np.cumsum(v)
        return {
            "ts": sub["time"].astype("int64"),
            "open": sub["open"].astype("float64"),
            "high": high,
            "low": low,
            "close": close,
            "vwap": np.divide(np.cumsum(tp * v), np.maximum(cum_v, 1e-9)),
        }

    # -- 主流程 -----------------------------------------------------------
    def simulate(
        self,
        decisions: List[Dict[str, Any]],
        hold_days: int = 2,
        target_pct: float = 6.0,
        max_fill_bars: int = 3,
        min_tier: int = 2,
        max_per_day: int = 5,
        focus_codes: Tuple[str, ...] = (),
        fill_mode: str = "limit",
    ) -> Tuple[List[Order], List[Trade]]:
        """decisions: [{code, ts, tier, rar, entry:{price_lo,price_hi}, stop, size_pct}, ...]

        max_per_day: 每日最多开几个仓位（按级别+RAR 取前 N）。
        不做这个限制等于"当天所有 L2+ 全买"，那不是策略，是散弹枪。
        """
        orders: List[Order] = []
        trades: List[Trade] = []

        # 每个 code 每天只取第一条 L2+（避免同一只票一天开十次仓）
        picked: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for d in sorted(decisions, key=lambda x: x["ts"]):
            if int(d.get("tier") or 0) < min_tier:
                continue
            key = (str(d["code"]).zfill(6), _day_str(d["ts"]))
            if key in picked:
                continue
            picked[key] = d

        # 每日按级别 + RAR 取前 N，模拟真实资金约束
        by_day: Dict[str, List[Dict[str, Any]]] = {}
        for (code, day), d in picked.items():
            by_day.setdefault(day, []).append(d)
        chosen: List[Dict[str, Any]] = []
        focus_set = {str(c).zfill(6) for c in focus_codes}
        for day, items in by_day.items():
            items.sort(key=lambda x: (int(x.get("tier") or 0), float(x.get("rar") or 0)), reverse=True)
            take = items[: max(1, max_per_day)]
            # 验收标的强制纳入模拟（否则会被"每日只开5仓"挤掉，无法回答"它到底能不能做"）
            for it in items[max(1, max_per_day):]:
                if str(it["code"]).zfill(6) in focus_set and it not in take:
                    take.append(it)
            chosen.extend(take)

        for d in sorted(chosen, key=lambda x: x["ts"]):
            code = str(d["code"]).zfill(6)
            day = _day_str(d["ts"])
            order, trade = self._run_one(code, day, d, hold_days, target_pct, max_fill_bars, fill_mode)
            if order is not None:
                orders.append(order)
            if trade is not None:
                trades.append(trade)
        return orders, trades

    def _run_one(
        self,
        code: str,
        day: str,
        d: Dict[str, Any],
        hold_days: int,
        target_pct: float,
        max_fill_bars: int,
        fill_mode: str = "limit",
    ) -> Tuple[Optional[Order], Optional[Trade]]:
        bars = self._bars_of(code, day)
        if bars is None:
            return None, None

        entry = d.get("entry") or {}
        lo = float(entry.get("price_lo") or 0.0)
        hi = float(entry.get("price_hi") or 0.0)
        stop = float(d.get("stop") or 0.0)
        if hi <= 0:
            hi = float(d.get("entry_price") or 0.0)
        if lo <= 0 or lo > hi:
            lo = hi * 0.998
        if hi <= 0:
            return None, None

        order = Order(
            code=code,
            signal_ts=float(d["ts"]),
            order_ts=0.0,
            price_lo=lo,
            price_hi=hi,
            size_pct=float(d.get("size_pct") or 0.0),
            tier=int(d.get("tier") or 0),
            stop=stop,
        )

        nxt_day = self._next_day(day)
        order.sellable_date = nxt_day or "T+1无数据"

        # 信号 bar 之后才开始挂单（当根不能成交）
        idx0 = int(np.searchsorted(bars["ts"], order.signal_ts, side="right"))
        if idx0 >= len(bars["ts"]):
            order.status = "NO_DATA"
            order.note = "信号在最后一根 bar"
            return order, None

        fill_i = -1
        if fill_mode == "market":
            fill_i = idx0
        else:
            for j in range(idx0, min(len(bars["ts"]), idx0 + max_fill_bars)):
                if bars["low"][j] <= hi:
                    fill_i = j
                    break
        if fill_i < 0:
            order.status = "EXPIRED"
            order.order_ts = float(bars["ts"][idx0])
            order.note = "{}根内未触及买入区间".format(max_fill_bars)
            return order, None

        if fill_mode == "market":
            fill_price = float(bars["open"][fill_i])
        else:
            fill_price = min(hi, float(bars["open"][fill_i]))
            if fill_price < lo:
                fill_price = lo
        order.status = "FILLED"
        order.order_ts = float(bars["ts"][fill_i])
        order.fill_price = fill_price

        trade = Trade(
            code=code,
            tier=order.tier,
            entry_ts=order.order_ts,
            entry_price=fill_price,
            size_pct=order.size_pct,
            stop=stop,
            sellable_date=nxt_day or "",
        )

        # ---- 买入当日：只记录，不能卖（T+1） ----
        day0 = bars["low"][fill_i:]
        if len(day0):
            trade.day0_mae_pct = (float(np.min(day0)) / fill_price - 1.0) * 100.0
        day0_high = bars["high"][fill_i:]
        if len(day0_high):
            trade.mfe_pct = max(trade.mfe_pct, (float(np.max(day0_high)) / fill_price - 1.0) * 100.0)

        if stop > 0 and len(day0) and float(np.min(day0)) <= stop:
            trade.stop_blocked = True
            trade.blocked_loss_pct = (stop / fill_price - 1.0) * 100.0 - trade.day0_mae_pct

        # 当日收盘跌破 VWAP -> 次日开盘处理（VWAP 结构用于控回撤）
        close_below_vwap = bool(bars["close"][-1] < bars["vwap"][-1])

        if not nxt_day:
            trade.exit_reason = "OPEN_T1无后续数据"
            return order, trade

        # ---- 次日起：允许卖出 ----
        target1 = fill_price * (1.0 + target_pct / 100.0)
        held = 0
        day_cursor = nxt_day
        while day_cursor is not None and held <= hold_days:
            db = self._bars_of(code, day_cursor)
            if db is None:
                day_cursor = self._next_day(day_cursor)
                continue
            held += 1

            # 次日开盘若已跌破止损：按开盘价出（跳空兜底）
            if stop > 0 and float(db["open"][0]) <= stop:
                trade.exit_ts = float(db["ts"][0])
                trade.exit_price = float(db["open"][0])
                trade.exit_reason = "跳空破止损"
                break

            hit_stop = stop > 0 and float(np.min(db["low"])) <= stop
            hit_target = float(np.max(db["high"])) >= target1

            if hit_stop and hit_target:
                # 同日双触：保守假设先触止损
                trade.exit_ts = float(db["ts"][int(np.argmax(db["low"] <= stop))])
                trade.exit_price = stop
                trade.exit_reason = "止损(双触保守)"
                break
            if hit_stop:
                trade.exit_ts = float(db["ts"][int(np.argmax(db["low"] <= stop))])
                trade.exit_price = stop
                trade.exit_reason = "止损"
                break
            if hit_target:
                trade.exit_ts = float(db["ts"][int(np.argmax(db["high"] >= target1))])
                trade.exit_price = target1
                trade.exit_reason = "止盈+{:.0f}%".format(target_pct)
                break

            if close_below_vwap:
                trade.exit_ts = float(db["ts"][0])
                trade.exit_price = float(db["open"][0])
                trade.exit_reason = "VWAP破位次日开盘出"
                break

            if held > hold_days:
                break
            day_cursor = self._next_day(day_cursor)

        if not trade.exit_ts:
            # 到期或数据耗尽：按最后一根收盘平
            last = self._bars_of(code, day_cursor or self.days[-1])
            if last is not None:
                trade.exit_ts = float(last["ts"][-1])
                trade.exit_price = float(last["close"][-1])
                trade.exit_reason = "持有到期/数据结束"

        if trade.exit_price > 0:
            trade.pnl_pct = (trade.exit_price / trade.entry_price - 1.0) * 100.0
            trade.hold_days = held
        return order, trade


def summarize_trades(trades: List[Trade]) -> Dict[str, Any]:
    """按档位与入场时段汇总，直接回答"早盘诱多值不值得做"。"""
    def _agg(rows: List[Trade]) -> Dict[str, Any]:
        if not rows:
            return {"n": 0}
        pnl = [t.pnl_pct for t in rows if t.exit_reason != "OPEN_T1无后续数据"]
        return {
            "n": len(rows),
            "closed": len(pnl),
            "win_rate": round(sum(1 for x in pnl if x > 0) / len(pnl), 3) if pnl else 0.0,
            "pnl_avg": round(float(np.mean(pnl)), 2) if pnl else 0.0,
            "pnl_best": round(float(np.max(pnl)), 2) if pnl else 0.0,
            "pnl_worst": round(float(np.min(pnl)), 2) if pnl else 0.0,
            "day0_mae_avg": round(float(np.mean([t.day0_mae_pct for t in rows])), 2),
            "stop_blocked": sum(1 for t in rows if t.stop_blocked),
        }

    out = {"all": _agg(trades), "by_tier": {}, "by_window": {}}
    for tier in (4, 3, 2, 1):
        rows = [t for t in trades if t.tier == tier]
        if rows:
            out["by_tier"]["L{}".format(tier)] = _agg(rows)
    for name in ("开盘30分", "上午", "午后", "尾盘", "其他"):
        rows = [t for t in trades if t.entry_window == name]
        if rows:
            out["by_window"][name] = _agg(rows)
    return out


def render_trades(orders: List[Order], trades: List[Trade], limit: int = 30) -> str:
    lines = ["## T+1 订单与成交（买入当日不可卖）", ""]
    if not orders:
        lines.append("- 当日无 L2 及以上可执行决策")
        return "\n".join(lines)

    filled = [o for o in orders if o.status == "FILLED"]
    lines.append(
        "- 订单 {} 笔｜成交 {}｜未成交(超时) {}｜不可卖日期按 T+1 顺延".format(
            len(orders), len(filled), sum(1 for o in orders if o.status == "EXPIRED")
        )
    )
    lines.append("")
    lines.append("| 代码 | 信号 | 挂单 | 买入区间 | 成交价 | 仓位 | 级别 | 止损 | 可卖日 | 状态 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for o in sorted(orders, key=lambda x: x.signal_ts)[:limit]:
        lines.append(
            "| {} | {} | {} | {:.2f}~{:.2f} | {} | {}% | L{} | {} | {} | {} |".format(
                o.code, o.to_dict()["signal_time"], o.to_dict()["order_time"],
                o.price_lo, o.price_hi, round(o.fill_price, 3) if o.fill_price else "-", o.size_pct, o.tier,
                o.stop or "-", o.sellable_date, o.status,
            )
        )
    lines.append("")

    if trades:
        lines.append("## 每笔交易结果（含买入当日不可控回撤）")
        lines.append("| 代码 | 买入 | 买入价 | 时段 | 卖出 | 卖出价 | 盈亏 | 当日最低 | 被锁止损 | 原因 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for t in sorted(trades, key=lambda x: x.entry_ts)[:limit]:
            d = t.to_dict()
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {}% | {}% | {} | {} |".format(
                    d["code"], d["entry_time"], d["entry_price"], d["window"],
                    d["exit_time"], d["exit_price"] or "-", d["pnl_pct"],
                    d["day0_mae_pct"], "是" if d["stop_blocked"] else "否", d["exit_reason"],
                )
            )
        lines.append("")

        s = summarize_trades(trades)
        lines.append("## T+1 口径汇总")
        lines.append("| 维度 | 笔数 | 胜率 | 平均盈亏 | 最好 | 最差 | 买入日均回撤 | 被锁止损 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        def _row(name, a):
            if not a.get("n"):
                return "| {} | 0 | - | - | - | - | - | - |".format(name)
            return "| {} | {} | {:.1%} | {}% | {}% | {}% | {}% | {} |".format(
                name, a["n"], a["win_rate"], a["pnl_avg"], a["pnl_best"], a["pnl_worst"],
                a["day0_mae_avg"], a["stop_blocked"])
        lines.append(_row("全部", s["all"]))
        for k, v in s["by_tier"].items():
            lines.append(_row(k, v))
        for k, v in s["by_window"].items():
            lines.append(_row("入场:" + k, v))
    return "\n".join(lines)
