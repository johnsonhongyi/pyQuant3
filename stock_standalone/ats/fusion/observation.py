"""观察证据契约：记录已到达的特征及其时点，不参与评分或执行。"""
from datetime import datetime
import math

ANCHORS = ("ch_bc2", "ch_tc2", "ch_nod")
EARLY_FIELDS = ("sig_bottom", "sig_top", "sig_launch", "sig_start", "sig_escape",
                "pdays", "pbreak", "obs_d", "win", "red",
                "ch_pattern", "open_anchor_price", "morning_low_price", "launch_time_str",
                "launch_slope_deg", "vwap_adhesion_ratio", "is_morning_scare_rebound",
                "has_bottom_base", "horse_race_score", "horse_race_tier")
PREPROCESSED_FIELDS = ANCHORS + ("sig_bottom", "sig_top", "sig_launch", "sig_start", "sig_escape", "ch_pattern")


def _number(value, positive=False):
    try:
        value = float(value)
        return value if math.isfinite(value) and (not positive or value > 0) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _prune_none(value):
    """剔除值为 None 的键：对所有 .get() 读取方语义等价，但单条记录可省 25%+。

    观察证据占单条影子记录 68%（实测 4.4KB/6.6KB），其中约 9 个字段整条为 None、
    另有一批 asof/feature_timestamp 为空。这些空键只贡献字节不贡献信息，且当日
    33k 条记录会把分片推到 220MB，读取端每次刷新都要重新解析。
    """
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            item = _prune_none(item)
            if item is None:
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [_prune_none(item) for item in value if item is not None]
    return value


def build_observation_evidence(row, snap, now, day, source, today_vwap=0, today_volume=0):
    row = row if hasattr(row, "get") else {}
    snap = snap if hasattr(snap, "get") else {}
    def pick(key):
        for label, data in (("input_row", row), ("input_snapshot", snap)):
            value = data.get(key)
            if value is not None:
                return value, label
        return None, "missing"

    def field_time(key, origin):
        data = row if origin == "input_row" else snap if origin == "input_snapshot" else {}
        stamp = _number(data.get(key + "_timestamp"), True)
        basis = "field"
        if stamp is None and key in PREPROCESSED_FIELDS:
            stamp = _number(data.get("_observation_preprocess_ts"), True)
            basis = "preprocess"
        if stamp is None:
            stamp = next((_number(data.get(k), True) for k in ("server_ts", "quote_timestamp", "ts")
                          if _number(data.get(k), True) is not None), None)
            basis = "container"
        state = "unverified_time"
        if stamp is not None:
            try:
                state = ("future" if stamp > now else "cross_day" if datetime.fromtimestamp(stamp).strftime("%Y-%m-%d") != day
                         else "stale" if basis != "preprocess" and now - stamp > 120 else "same_day")
            except (ValueError, OverflowError, OSError):
                state = "invalid_time"
        asof = str(data.get("_observation_preprocess_asof") or "")[:10] if basis == "preprocess" else ""
        if asof and asof > day:
            state = "future"
        elif asof and asof < day:
            state = "historical_context"
        elif basis == "preprocess" and not asof and state == "same_day":
            state = "unverified_asof"
        own_day = str(data.get(key + "_trade_date") or data.get("trade_date") or "")[:10]
        if len(own_day) == 8 and own_day.isdigit():
            own_day = own_day[:4] + "-" + own_day[4:6] + "-" + own_day[6:]
        if own_day and own_day != day:
            state = "cross_day"
        if key in PREPROCESSED_FIELDS and basis == "container" and state == "same_day":
            state = "unverified_feature_time"
        return {"feature_timestamp": stamp, "freshness": state, "time_basis": basis, "asof": asof or None}

    timestamp = next((_number(pick(k)[0], True) for k in ("server_ts", "quote_timestamp", "ts")
                      if _number(pick(k)[0], True) is not None), None)
    freshness = "unverified_time"
    if timestamp is not None:
        try:
            freshness = ("future" if timestamp > now else "cross_day"
                         if datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d") != day else
                         "stale" if now - timestamp > 120 else "same_day")
        except (ValueError, OverflowError, OSError):
            freshness = "invalid_time"
    raw_day = str(pick("trade_date")[0] or "")[:10]
    if len(raw_day) == 8 and raw_day.isdigit():
        raw_day = raw_day[:4] + "-" + raw_day[4:6] + "-" + raw_day[6:]
    if raw_day and raw_day != day:
        freshness = "cross_day"
    anchors = {}
    for key in ANCHORS:
        raw, origin = pick(key)
        value = _number(raw, True)
        anchors[key] = {"value": int(value) if value is not None and value.is_integer() else None,
                        "source": origin, "unit": "input_bars", **field_time(key, origin)}
    early = {}
    for key in EARLY_FIELDS:
        value, origin = pick(key)
        if isinstance(value, str):
            early[key] = {"value": value[:160], "source": origin, **field_time(key, origin)}
        else:
            early[key] = {"value": _number(value), "source": origin, **field_time(key, origin)}
    # 未收到的字段只留空壳：整条剔除（读取方全部走 .get()，语义等价），
    # 保留的字段仅去掉值为 None 的键（asof / feature_timestamp 常为空）。
    early = {key: item for key, item in ((k, _prune_none(v)) for k, v in early.items())
             if item is not None and item.get("value") is not None}
    context = snap.get("_observation_daily_context") or {}
    history = context.get("values", {}) if isinstance(context, dict) and context.get("asof_day") == day else {}
    if not isinstance(history, dict):
        history = {}
    current = {"1": _number(today_vwap, True)}
    volume = _number(today_volume, True)
    if volume is None and current["1"]:
        amount, raw_volume = _number(pick("amount")[0], True), _number(pick("volume")[0], True)
        if amount and raw_volume and any(.95 <= amount / (raw_volume * factor * current["1"]) <= 1.05
                                        for factor in (1, 100)):
            volume = amount / current["1"]
    for window in (3, 5, 10):
        total = _number(history.get("vwap_prev{}_volume".format(window - 1)), True)
        value = _number(history.get("vwap_prev{}_value".format(window - 1)), True)
        current[str(window)] = ((value + current["1"] * volume) / (total + volume)
                                if total and value and volume and current["1"] else None)
    previous = {str(k): _number(history.get("vwap1_prev_session" if k == 1 else "vwap" + str(k)), True)
                for k in (1, 3, 5, 10)}
    vwap_origin = next((label for label, data in (("input_row", row), ("input_snapshot", snap))
                        if _number(data.get("vwap"), True) is not None), "missing")
    if source == "replay_minute_proxy":
        vwap_origin = "input_row"
    vwap_timing = field_time("vwap", vwap_origin)
    usable = freshness == "same_day" and vwap_timing["freshness"] == "same_day"
    ordered = (all(current[str(a)] >= current[str(b)] for a, b in ((1, 3), (3, 5), (5, 10)))
               if usable and all(v is not None for v in current.values()) else None)
    return {"schema": 1, "role": "observation_only", "observed_at": now, "trade_date": day,
            "source": source, "feature_timestamp": timestamp, "freshness": freshness,
            "anchors": anchors, "anchor_period": pick("ch_period")[0] if isinstance(pick("ch_period")[0], str) else None,
            "early_signals": early,
            "vwap": {"including_current": current, "previous_session": previous,
                     "timing": vwap_timing,
                     "ordered_1_3_5_10": ordered,
                     "above_previous_session": {k: current[k] > previous[k]
                                                if usable and current[k] and previous[k] else None for k in current}},
            "missing": [key for key, item in anchors.items() if item["value"] is None],
            "note": "接收时点不等于特征产生时点；周期或来源时点未知的 IPC 特征不可回填历史评分"}


def observation_summary(evidence):
    if not isinstance(evidence, dict):
        return "观察证据：旧记录未保存，不能回填推断"
    anchors = evidence.get("anchors") or {}
    values = (evidence.get("vwap") or {}).get("including_current") or {}
    early = evidence.get("early_signals") or {}
    active = "、".join("{}={}[{}]".format(k, item.get("value"), item.get("freshness", "时间待核"))
                      for k, item in early.items() if item.get("value"))
    if not active:
        active = "已收到字段，暂无激活" if any(item.get("value") is not None for item in early.values()) else "未收到预处理字段，不能推断无信号"
    return ("观察证据（非交易指令）｜时点：{}\n周期锚点：{}；K线周期：{}\n含今日VWAP（时点：{}）：{}\n预处理观察：{}".format(
        evidence.get("freshness", "unknown"),
        " / ".join("{}={}[{}]".format(k, (anchors.get(k) or {}).get("value"),
                                     (anchors.get(k) or {}).get("freshness", "时间待核")) for k in ANCHORS),
        evidence.get("anchor_period") or "未知，不能解释为自然日",
        ((evidence.get("vwap") or {}).get("timing") or {}).get("freshness", "时间待核"),
        " / ".join("{}V={}".format(k, "未知" if values.get(k) is None else "{:.3f}".format(values[k])) for k in ("1", "3", "5", "10")),
        active))


def observation_reason(evidence):
    if not isinstance(evidence, dict) or evidence.get("role") != "observation_only" or evidence.get("freshness") != "same_day":
        return ""
    early = evidence.get("early_signals") or {}
    if any(isinstance(early.get(k), dict) and early[k].get("value") == 1 and early[k].get("freshness") == "same_day"
           for k in ("sig_bottom", "sig_launch", "sig_start", "has_bottom_base")):
        return "早盘策略观察"
    vwap = evidence.get("vwap") or {}
    above = vwap.get("above_previous_session") or {}
    if vwap.get("ordered_1_3_5_10") is True and all(above.get(k) is True for k in ("1", "3", "5", "10")):
        return "多周期VWAP抬升观察"
    return ""


def strategy_observation_rows(frame, follow_codes=()):
    """只选择观察候选，不使用涨幅、量比或梯度门槛；不修改输入 DF。"""
    import pandas as pd
    codes = set(follow_codes)
    mask = pd.Series(frame.index.map(lambda code: str(code).split(".")[0].zfill(6) in codes), index=frame.index)
    for key in ("sig_bottom", "sig_launch", "sig_start", "has_bottom_base"):
        if key in frame.columns:
            mask |= pd.to_numeric(frame[key], errors="coerce").eq(1)
    return frame.loc[mask]
