# -*- coding: utf-8 -*-
"""从影子记录重建跨日信号观察；不推断真实成交或未记录行情。"""
from datetime import datetime
import math
from ats.fusion.source_identity import is_replay_record


def build_cross_day(series_by_day, asof_day, allow_replay=False):
    states = {}
    for day in sorted(d for d in series_by_day if d <= asof_day):
        for code, rows in series_by_day[day].items():
            valid_rows = []
            for row in rows:
                try:
                    ts = float(row.get("ts") or 0)
                    if math.isfinite(ts):
                        valid_rows.append((ts, row))
                except (TypeError, ValueError, OverflowError, AttributeError):
                    continue
            for _, row in sorted(valid_rows, key=lambda item: item[0]):
                try:
                    ts = float(row.get("ts") or 0)
                    valid_day = ts > 0 and datetime.fromtimestamp(ts).strftime("%Y-%m-%d") == day
                except (TypeError, ValueError, OverflowError, OSError):
                    valid_day = False
                if not valid_day:
                    continue
                is_replay = is_replay_record(row)
                if is_replay != allow_replay:
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
                    if row.get("price_only"):
                        continue
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
                                              "high": price, "low": price, "records": 0, "signal_records": 0})
                daily = state["timeline"][-1]
                daily.update(last_ts=ts, last_price=price, high=max(daily["high"], price),
                             low=min(daily["low"], price), records=daily["records"] + 1)
                if row.get("price_only"):
                    daily["price_source"] = "分钟缓存采样"
                else:
                    daily["signal_records"] += 1
                state["high"], state["low"] = max(state["high"], price), min(state["low"], price)
                tracking = row.get("track") or row.get("tracker") or {}
                if row.get("price_only"):
                    if not daily["signal_records"]:
                        state["signal_status"] = "仅行情采样，当日信号未知"
                else:
                    state["signal_status"] = tracking.get("stage") or ("信号被否决" if (row.get("fusion") or {}).get("veto_reason") else
                                               "仍有观察证据" if {"逆势收复启动", "逆势收复持稳"} & set(row.get("patterns") or []) else "无收复证据")
                    daily["signal_status"] = state["signal_status"]
                    daily["tier"] = tier
                visible_tier = (state.get("tier") if daily["signal_records"] else None) if row.get("price_only") else tier
                state.update(last_day=day, last_ts=ts, last_price=price, tier=visible_tier,
                             status=("所选日仅行情采样" if row.get("price_only") and not daily["signal_records"] else "所选日有记录") if day == asof_day else "所选日无记录")
    result = list(states.values())
    for state in result:
        state["return_pct"] = (state["last_price"] / state["reference"] - 1) * 100
        state["mfe_pct"] = (state["high"] / state["reference"] - 1) * 100
        state["mae_pct"] = (state["low"] / state["reference"] - 1) * 100
        for daily in state["timeline"]:
            daily["return_pct"] = (daily["last_price"] / state["reference"] - 1) * 100
    return sorted(result, key=lambda x: x["last_ts"], reverse=True)
