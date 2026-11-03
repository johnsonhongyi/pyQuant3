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

P2 阶段增强：
    - 限价买单严格上限为 price_hi，撮合消除虚构高价 (fill_price < lo)
    - 识别挂单窗口一字涨停锁死 UNFILLED_LIMIT_LOCKED
    - 逐 bar 推进退出，区分同日跨 bar 触发与同根 bar 双触保守止损
    - 次日开盘跳空/VWAP 破位优先退出
    - 跌停受阻 pending_exit 顺延并在开板首根 bar 按 open 退出
    - 日内数据完整性检查（>= 14:57），残缺数据标记 IMMATURE_OPEN
    - 引入往返总成本 cost_pct (默认 0.15%) 与净收益 net_pnl_pct
    - 区分 label_end_ts 与 label_available_ts
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set

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


def _is_limit_up_locked(bars: Dict[str, np.ndarray], j: int, code: str, ref_price: float = 0.0) -> bool:
    """判断某根 bar 是否一字涨停锁死（无法买入）。"""
    if bars["low"][j] < bars["high"][j]:
        return False
    # low == high
    if bars.get("volume") is not None and bars["volume"][j] <= 0:
        return False  # 停牌，由停牌逻辑处理
    curr_p = float(bars["close"][j])
    threshold = 0.195 if (code.startswith("30") or code.startswith("68")) else 0.095
    if ref_price > 0:
        return (curr_p / ref_price - 1.0) >= threshold
    if "is_limit_up" in bars:
        return bool(bars["is_limit_up"][j])
    return False


def _is_limit_down_locked(bars: Dict[str, np.ndarray], k: int, code: str, prev_close: float = 0.0) -> bool:
    """判断某根 bar 是否一字跌停锁死（无法卖出）。"""
    if bars["low"][k] < bars["high"][k]:
        return False
    # low == high
    curr_p = float(bars["close"][k])
    threshold = -0.195 if (code.startswith("30") or code.startswith("68")) else -0.097
    if prev_close > 0:
        return (curr_p / prev_close - 1.0) <= threshold
    if "is_limit_down" in bars:
        return bool(bars["is_limit_down"][k])
    return False


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
    status: str = "PENDING"   # FILLED / EXPIRED / NO_DATA / UNFILLED_LIMIT_LOCKED
    note: str = ""
    status_reason: str = ""

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
            "status_reason": self.status_reason,
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
    gross_pnl_pct: float = 0.0      # 毛收益率 (%)
    net_pnl_pct: float = 0.0        # 净收益率 (%) = gross_pnl_pct - cost_pct
    cost_pct: float = 0.15          # 往返总成本 (%)，默认 0.15
    label_end_ts: float = 0.0       # 退出/事件结束时间戳
    label_available_ts: float = 0.0 # 标签数据落盘可读时间戳
    availability_mode: str = "bar_close_conservative"
    resolution_status: str = ""     # FILLED_MATURE / IMMATURE_OPEN 等
    status_reason: str = ""         # 细粒度状态原因

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
            "gross_pnl_pct": round(self.gross_pnl_pct, 2),
            "net_pnl_pct": round(self.net_pnl_pct, 2),
            "cost_pct": self.cost_pct,
            "exit_reason": self.exit_reason,
            "hold_days": self.hold_days,
            "day0_mae_pct": round(self.day0_mae_pct, 2),
            "mfe_pct": round(self.mfe_pct, 2),
            "stop_blocked": self.stop_blocked,
            "blocked_loss_pct": round(self.blocked_loss_pct, 2),
            "label_end_ts": self.label_end_ts,
            "label_available_ts": self.label_available_ts,
            "availability_mode": self.availability_mode,
            "resolution_status": self.resolution_status,
            "status_reason": self.status_reason,
        }


class T1Simulator:
    """基于分钟线的 T+1 订单/持仓模拟。"""

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
        res = {
            "ts": sub["time"].astype("int64"),
            "open": sub["open"].astype("float64"),
            "high": high,
            "low": low,
            "close": close,
            "volume": v,
            "vwap": np.divide(np.cumsum(tp * v), np.maximum(cum_v, 1e-9)),
        }
        if "limit_up" in sub.dtype.names:
            res["is_limit_up"] = sub["limit_up"].astype("bool")
        if "limit_down" in sub.dtype.names:
            res["is_limit_down"] = sub["limit_down"].astype("bool")
        return res

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
        selection_mode: str = "chronological",
        require_full_day_close: bool = False,
        cost_pct: float = 0.15,
    ) -> Tuple[List[Order], List[Trade]]:
        """decisions: [{code, ts, tier, rar, entry:{price_lo,price_hi}, stop, size_pct}, ...]

        selection_mode:
            - 'chronological': 严格按信号时间流序推进开仓（无未来信息），结合每日预算 max_per_day；若有 focus_codes 则额外允许纳入。
            - 'top_n': 盘后按 tier + rar 降序选前 N（兼容历史逻辑）。
        """
        orders: List[Order] = []
        trades: List[Trade] = []

        focus_set = {str(c).zfill(6) for c in focus_codes}

        if selection_mode == "top_n":
            # 每个 code 每天只取第一条 L2+
            picked: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for d in sorted(decisions, key=lambda x: x["ts"]):
                if int(d.get("tier") or 0) < min_tier:
                    continue
                key = (str(d["code"]).zfill(6), _day_str(d["ts"]))
                if key in picked:
                    continue
                picked[key] = d

            # 每日按级别 + RAR 取前 N
            by_day: Dict[str, List[Dict[str, Any]]] = {}
            for (code, day), d in picked.items():
                by_day.setdefault(day, []).append(d)
            chosen: List[Dict[str, Any]] = []
            for day, items in by_day.items():
                items.sort(key=lambda x: (int(x.get("tier") or 0), float(x.get("rar") or 0)), reverse=True)
                take = items[: max(1, max_per_day)]
                for it in items[max(1, max_per_day):]:
                    if str(it["code"]).zfill(6) in focus_set and it not in take:
                        take.append(it)
                chosen.extend(take)
            sorted_candidates = sorted(chosen, key=lambda x: x["ts"])
        else:
            # chronological 模式：流序推进
            sorted_all = sorted(decisions, key=lambda x: x["ts"])
            chosen = []
            day_seen: Set[Tuple[str, str]] = set()
            day_open_counts: Dict[str, int] = {}
            for d in sorted_all:
                if int(d.get("tier") or 0) < min_tier:
                    continue
                code = str(d["code"]).zfill(6)
                day = _day_str(d["ts"])
                key = (code, day)
                if key in day_seen:
                    continue
                day_seen.add(key)

                current_day_count = day_open_counts.get(day, 0)
                if current_day_count < max(1, max_per_day):
                    chosen.append(d)
                    day_open_counts[day] = current_day_count + 1
                elif code in focus_set:
                    # 允许验收标的强制纳入
                    chosen.append(d)

            sorted_candidates = chosen

        for d in sorted_candidates:
            code = str(d["code"]).zfill(6)
            day = _day_str(d["ts"])
            order, trade = self._run_one(
                code, day, d, hold_days, target_pct, max_fill_bars, fill_mode,
                require_full_day_close=require_full_day_close, cost_pct=cost_pct
            )
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
        require_full_day_close: bool = False,
        cost_pct: float = 0.15,
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
            order.status_reason = "NO_DATA"
            return order, None

        # 检查挂单窗口是否有成交量
        end_idx = min(len(bars["ts"]), idx0 + max_fill_bars)
        sub_v = bars["volume"][idx0:end_idx]
        if len(sub_v) == 0 or np.all(sub_v <= 0):
            order.status = "NO_DATA"
            order.note = "挂单窗口内无成交量/停牌"
            order.status_reason = "ZERO_VOLUME"
            return order, None

        ref_price = float(d.get("prev_close") or d.get("last_close") or 0.0)

        fill_i = -1
        all_limit_locked = True
        touched_hi = False

        if fill_mode == "market":
            fill_i = idx0
        else:
            for j in range(idx0, end_idx):
                if bars["volume"][j] <= 0:
                    continue
                if bars["low"][j] <= hi:
                    touched_hi = True
                    # 检查是否一字涨停锁死
                    if _is_limit_up_locked(bars, j, code, ref_price=ref_price) or bool(d.get("is_limit_up")):
                        continue
                    all_limit_locked = False
                    fill_i = j
                    break
                else:
                    all_limit_locked = False

        if fill_i < 0:
            order.order_ts = float(bars["ts"][idx0])
            if touched_hi and all_limit_locked:
                order.status = "UNFILLED_LIMIT_LOCKED"
                order.note = "{}根内因一字涨停无法买入".format(max_fill_bars)
                order.status_reason = "LIMIT_UP_LOCKED"
            else:
                order.status = "EXPIRED"
                order.note = "{}根内未触及买入区间".format(max_fill_bars)
                order.status_reason = "UNTOUCHED_BAND"
            return order, None

        if fill_mode == "market":
            fill_price = float(bars["open"][fill_i])
        else:
            fill_price = min(hi, float(bars["open"][fill_i]))
            # 绝不用 if fill_price < lo: fill_price = lo 强行捏造高价！

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
            cost_pct=cost_pct,
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

        # 当日收盘跌破 VWAP 判定
        close_below_vwap = bool(bars["close"][-1] < bars["vwap"][-1])

        # 检查 T+0 收盘完整性
        lt_last0 = time.localtime(bars["ts"][-1])
        last_m0 = lt_last0.tm_hour * 60 + lt_last0.tm_min
        if require_full_day_close and last_m0 < 14 * 60 + 57:
            close_below_vwap = False  # 残缺数据不作为可靠破位依据

        if not nxt_day:
            if require_full_day_close and last_m0 < 14 * 60 + 57:
                trade.exit_reason = "IMMATURE_INCOMPLETE_BARS"
                trade.resolution_status = "IMMATURE_OPEN"
                trade.status_reason = "INCOMPLETE_INTRADAY_BARS"
            else:
                trade.exit_reason = "OPEN_T1无后续数据"
                trade.resolution_status = "IMMATURE_OPEN"
                trade.status_reason = "MISSING_NEXT_DAY_BARS"
            return order, trade

        # ---- 次日起：逐 bar 推进允许卖出 ----
        target1 = fill_price * (1.0 + target_pct / 100.0)
        held = 0
        day_cursor = nxt_day
        pending_exit_reason = ""
        prev_close_for_day = float(bars["close"][-1])

        while day_cursor is not None and held < hold_days:
            db = self._bars_of(code, day_cursor)
            if db is None:
                day_cursor = self._next_day(day_cursor)
                continue
            held += 1

            n_bars = len(db["ts"])
            for k in range(n_bars):
                bar_open = float(db["open"][k])
                bar_high = float(db["high"][k])
                bar_low = float(db["low"][k])
                bar_close = float(db["close"][k])
                bar_ts = float(db["ts"][k])
                bar_vol = float(db["volume"][k])

                is_locked_down = _is_limit_down_locked(db, k, code, prev_close_for_day)
                can_sell = (bar_vol > 0) and not is_locked_down

                # 1. 前序受阻退出恢复检查
                if pending_exit_reason:
                    if can_sell:
                        trade.exit_ts = bar_ts
                        trade.exit_price = bar_open
                        trade.exit_reason = pending_exit_reason
                        pending_exit_reason = ""
                        break
                    else:
                        continue

                # 2. T+1 首根 bar 检查 VWAP 破位
                if held == 1 and k == 0 and close_below_vwap:
                    if can_sell:
                        trade.exit_ts = bar_ts
                        trade.exit_price = bar_open
                        trade.exit_reason = "VWAP破位次日开盘出"
                        break
                    else:
                        pending_exit_reason = "VWAP破位次日开盘出(受阻顺延)"
                        continue

                # 3. 开盘跳空检查
                if stop > 0 and bar_open <= stop:
                    if can_sell:
                        trade.exit_ts = bar_ts
                        trade.exit_price = bar_open
                        trade.exit_reason = "跳空破止损"
                        break
                    else:
                        pending_exit_reason = "跳空破止损(受阻顺延)"
                        continue

                if bar_open >= target1:
                    if can_sell:
                        trade.exit_ts = bar_ts
                        trade.exit_price = bar_open
                        trade.exit_reason = "止盈+{:.0f}%".format(target_pct)
                        break
                    else:
                        pending_exit_reason = "止盈+{:.0f}%(受阻顺延)".format(target_pct)
                        continue

                # 4. 盘中高低点检查
                bar_hit_stop = (stop > 0 and bar_low <= stop)
                bar_hit_target = (bar_high >= target1)

                if bar_hit_stop and bar_hit_target:
                    # 仅当同一根 bar 内同时双触时，保守按止损
                    if can_sell:
                        trade.exit_ts = bar_ts
                        trade.exit_price = stop
                        trade.exit_reason = "止损(双触保守)"
                        break
                    else:
                        pending_exit_reason = "止损(双触保守,受阻顺延)"
                        continue
                elif bar_hit_stop:
                    if can_sell:
                        trade.exit_ts = bar_ts
                        trade.exit_price = stop
                        trade.exit_reason = "止损"
                        break
                    else:
                        pending_exit_reason = "止损(受阻顺延)"
                        continue
                elif bar_hit_target:
                    if can_sell:
                        trade.exit_ts = bar_ts
                        trade.exit_price = target1
                        trade.exit_reason = "止盈+{:.0f}%".format(target_pct)
                        break
                    else:
                        pending_exit_reason = "止盈+{:.0f}%(受阻顺延)".format(target_pct)
                        continue

            # end for k
            if trade.exit_ts > 0:
                break

            prev_close_for_day = float(db["close"][-1])

            # 到期检查：若 held == hold_days 且未在盘中退出
            if held == hold_days and not trade.exit_ts and not pending_exit_reason:
                lt_last = time.localtime(db["ts"][-1])
                last_m = lt_last.tm_hour * 60 + lt_last.tm_min
                if require_full_day_close and last_m < 14 * 60 + 57:
                    trade.exit_reason = "IMMATURE_INCOMPLETE_BARS"
                    trade.resolution_status = "IMMATURE_OPEN"
                    trade.status_reason = "INCOMPLETE_INTRADAY_BARS"
                    break
                else:
                    last_vol = float(db["volume"][-1])
                    last_locked = _is_limit_down_locked(db, -1, code, prev_close_for_day)
                    if last_vol > 0 and not last_locked:
                        trade.exit_ts = float(db["ts"][-1])
                        trade.exit_price = float(db["close"][-1])
                        trade.exit_reason = "持有到期/数据结束"
                        break
                    else:
                        pending_exit_reason = "持有到期(受阻顺延)"

            day_cursor = self._next_day(day_cursor)
        # end while

        # 处理受阻顺延直到无后续数据的情况
        if not trade.exit_ts:
            if pending_exit_reason:
                trade.exit_reason = "OPEN_跌停受阻无后续数据"
                trade.resolution_status = "IMMATURE_OPEN"
                trade.status_reason = "T1_LIMIT_DOWN_LOCKED"
            elif trade.exit_reason == "IMMATURE_INCOMPLETE_BARS":
                pass
            else:
                trade.exit_reason = "持有到期/数据结束"
                # 若还有最后一根可尝试收盘退出
                last = self._bars_of(code, day_cursor or (self.days[-1] if self.days else day))
                if last is not None:
                    trade.exit_ts = float(last["ts"][-1])
                    trade.exit_price = float(last["close"][-1])

        if trade.exit_price > 0:
            trade.gross_pnl_pct = (trade.exit_price / trade.entry_price - 1.0) * 100.0
            trade.cost_pct = cost_pct
            trade.net_pnl_pct = trade.gross_pnl_pct - cost_pct
            trade.pnl_pct = trade.gross_pnl_pct
            trade.hold_days = held
            trade.resolution_status = "FILLED_MATURE"
            trade.status_reason = "NORMAL_EXIT"
            trade.label_end_ts = trade.exit_ts
            trade.label_available_ts = trade.exit_ts + 180.0

        return order, trade


def summarize_trades(trades: List[Trade]) -> Dict[str, Any]:
    """按档位与入场时段汇总，直接回答"早盘诱多值不值得做"。"""
    def _agg(rows: List[Trade]) -> Dict[str, Any]:
        if not rows:
            return {"n": 0}
        pnl = [t.pnl_pct for t in rows if t.exit_reason not in ("OPEN_T1无后续数据", "IMMATURE_INCOMPLETE_BARS", "OPEN_跌停受阻无后续数据") and t.exit_price > 0]
        net_pnl = [t.net_pnl_pct for t in rows if t.exit_reason not in ("OPEN_T1无后续数据", "IMMATURE_INCOMPLETE_BARS", "OPEN_跌停受阻无后续数据") and t.exit_price > 0]
        return {
            "n": len(rows),
            "closed": len(pnl),
            "win_rate": round(sum(1 for x in pnl if x > 0) / len(pnl), 3) if pnl else 0.0,
            "pnl_avg": round(float(np.mean(pnl)), 2) if pnl else 0.0,
            "net_pnl_avg": round(float(np.mean(net_pnl)), 2) if net_pnl else 0.0,
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
        "- 订单 {} 笔｜成交 {}｜未成交(超时) {}｜未成交(一字涨停) {}｜不可卖日期按 T+1 顺延".format(
            len(orders), len(filled),
            sum(1 for o in orders if o.status == "EXPIRED"),
            sum(1 for o in orders if o.status == "UNFILLED_LIMIT_LOCKED"),
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
        lines.append("## 每笔交易结果（含买入当日不可控回撤与净收益）")
        lines.append("| 代码 | 买入 | 买入价 | 时段 | 卖出 | 卖出价 | 毛盈亏 | 净盈亏 | 当日最低 | 被锁止损 | 原因 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for t in sorted(trades, key=lambda x: x.entry_ts)[:limit]:
            d = t.to_dict()
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {}% | {}% | {}% | {} | {} |".format(
                    d["code"], d["entry_time"], d["entry_price"], d["window"],
                    d["exit_time"], d["exit_price"] or "-", d["gross_pnl_pct"], d["net_pnl_pct"],
                    d["day0_mae_pct"], "是" if d["stop_blocked"] else "否", d["exit_reason"],
                )
            )
        lines.append("")

        s = summarize_trades(trades)
        lines.append("## T+1 口径汇总")
        lines.append("| 维度 | 笔数 | 胜率 | 平均毛盈亏 | 平均净盈亏 | 最好 | 最差 | 买入日均回撤 | 被锁止损 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        def _row(name, a):
            if not a.get("n"):
                return "| {} | 0 | - | - | - | - | - | - | - |".format(name)
            return "| {} | {} | {:.1%} | {}% | {}% | {}% | {}% | {}% | {} |".format(
                name, a["n"], a["win_rate"], a["pnl_avg"], a.get("net_pnl_avg", 0.0),
                a["pnl_best"], a["pnl_worst"], a["day0_mae_avg"], a["stop_blocked"])
        lines.append(_row("全部", s["all"]))
        for k, v in s["by_tier"].items():
            lines.append(_row(k, v))
        for k, v in s["by_window"].items():
            lines.append(_row("入场:" + k, v))
    return "\n".join(lines)
