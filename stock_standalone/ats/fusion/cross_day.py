# -*- coding: utf-8 -*-
"""从影子记录重建跨日信号观察；不推断真实成交或未记录行情。"""
from datetime import datetime
import math


def build_cross_day(series_by_day, asof_day):
    states = {}
    for day in sorted(d for d in series_by_day if d <= asof_day):
        for code, rows in series_by_day[day].items():
            for row in sorted(rows, key=lambda x: float(x.get("ts") or 0)):
                try:
                    ts = float(row.get("ts") or 0)
                    valid_day = ts > 0 and datetime.fromtimestamp(ts).strftime("%Y-%m-%d") == day
                except (TypeError, ValueError, OverflowError, OSError):
                    valid_day = False
                if not valid_day:
                    continue
                origin = str(row.get("writer_exe") or "").upper()
                source = str(row.get("source") or "").lower()
                if "REPLAY" in origin or "BACKFILL" in origin or "replay" in source or "backfill" in source or row.get("writer_pid") == 0:
                    continue
                if row.get("trade_date") and str(row["trade_date"])[:10] != day:
                    continue
                try:
                    price = float(row.get("price") or 0)
                    tier = int((row.get("fusion") or {}).get("tier") or 0)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(price) or price <= 0:
                    continue
                state = states.get(code)
                if state is None:
                    observing = {"逆势收复启动", "逆势收复持稳"} & set(row.get("patterns") or [])
                    if not observing and (tier < 2 or (row.get("fusion") or {}).get("veto_reason")):
                        continue
                    state = {"code": code, "name": str(row.get("name") or ""),
                             "first_day": day, "first_ts": ts, "reference": price, "days": [],
                             "timeline": [], "high": price, "low": price}
                    states[code] = state
                if day not in state["days"]:
                    state["days"].append(day)
                    state["timeline"].append({"day": day, "first_ts": ts, "last_ts": ts,
                                              "first_price": price, "last_price": price,
                                              "high": price, "low": price, "records": 0})
                daily = state["timeline"][-1]
                daily.update(last_ts=ts, last_price=price, high=max(daily["high"], price),
                             low=min(daily["low"], price), records=daily["records"] + 1)
                state["high"], state["low"] = max(state["high"], price), min(state["low"], price)
                tracking = row.get("track") or row.get("tracker") or {}
                state["signal_status"] = tracking.get("stage") or ("信号被否决" if (row.get("fusion") or {}).get("veto_reason") else
                                           "仍有观察证据" if {"逆势收复启动", "逆势收复持稳"} & set(row.get("patterns") or []) else "无收复证据")
                state.update(last_day=day, last_ts=ts, last_price=price, tier=tier,
                             status="所选日有记录" if day == asof_day else "所选日无记录")
    result = list(states.values())
    for state in result:
        state["return_pct"] = (state["last_price"] / state["reference"] - 1) * 100
        state["mfe_pct"] = (state["high"] / state["reference"] - 1) * 100
        state["mae_pct"] = (state["low"] / state["reference"] - 1) * 100
        for daily in state["timeline"]:
            daily["return_pct"] = (daily["last_price"] / state["reference"] - 1) * 100
    return sorted(result, key=lambda x: x["last_ts"], reverse=True)
