# -*- coding: utf-8 -*-
"""ats/fusion/adapter.py — 把现有实时行/快照适配成 SignalEvent。

为什么单独一层：
    `stock_live_strategy._detect_signals_single_stock` 拿到的 `row` 是
    `convert_quotes_to_df` 产出的 DataFrame 行，`snap` 是稀疏的监控快照，
    两者的字段随数据源、resample、是否 alpha 行情而不同。
    适配层负责"尽力取值 + 缺省不崩"，绝不让融合层反向依赖业务对象。

字段优先级：row（实时行情） > snap（监控快照） > 计算回退 > 中性默认。
所有缺失都退化为中性值并在 `extra['missing']` 里记账，便于影子期统计覆盖率。
"""

from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ats.fusion.contract import SignalEvent

_NEUTRAL = {
    "taker_buy_ratio": 50.0,
    "bid_pressure": 50.0,
    "slope_score": 40.0,
    "intent_score": 50.0,
    "structure_clarity": 0.0,
}


def _num(value: Any, default: float = 0.0) -> float:
    """把 None / NaN / pd.NA / '-' / '12.3%' 统一成 float。"""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            s = value.strip().replace("%", "").replace(",", "")
            if not s or s in ("-", "--", "nan", "None", "NaN"):
                return default
            return float(s)
        f = float(value)
    except Exception:
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    try:
        return obj.get(key)
    except Exception:
        return None


def _first_num(sources: List[Tuple[Any, str]], default: float = 0.0) -> float:
    for obj, key in sources:
        v = _num(_get(obj, key), float("nan"))
        if v == v and v != 0.0:
            return v
    return default


def _first_raw(sources: List[Tuple[Any, str]]) -> Any:
    for obj, key in sources:
        v = _get(obj, key)
        if v is not None and v != "":
            return v
    return None


def today_str(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts if ts else time.time()))


# A 股连续竞价 + 集合竞价的可评估窗口（与监控侧口径一致）
TRADING_SESSION = ("09:15", "15:05")


def in_trading_session(ts: Optional[float] = None) -> bool:
    """是否落在当日交易时段（09:15~15:05）。"""
    try:
        hm = time.strftime("%H:%M", time.localtime(float(ts) if ts else time.time()))
    except Exception:
        return False
    return TRADING_SESSION[0] <= hm <= TRADING_SESSION[1]


def is_today(ts: Optional[float] = None) -> bool:
    """时间戳是否属于今天。"""
    try:
        return today_str(ts) == today_str()
    except Exception:
        return False


class LaunchTracker:
    """记录每个标的"本轮启动"的时刻，用于先手衰减。

    判定启动：当日涨幅 >= 1.0% 或 现价站上分时均价 0.5% 以上。
    这是近似口径——现有各引擎没有统一的 launch_ts，等 P2 接入
    `signal_timeline` 的首个 TRIGGERED bar 后应替换为精确值。
    单日重置，容量上限 6000，超限淘汰最早记录。
    """

    def __init__(self, pct_threshold: float = 1.0, bias_threshold: float = 0.5, capacity: int = 6000):
        self._lock = threading.Lock()
        self._day = ""
        self._marks: Dict[str, float] = {}
        self._pct_threshold = pct_threshold
        self._bias_threshold = bias_threshold
        self._capacity = capacity

    def note(
        self,
        code: str,
        ts: float,
        pct: float,
        price: float,
        vwap: float,
        reset_wave: bool = False,
    ) -> float:
        day = today_str(ts)
        with self._lock:
            if day != self._day:
                self._day = day
                self._marks.clear()

            if reset_wave:
                wave_ts = max(0.0, float(ts) - 300.0)
                self._marks[code] = wave_ts
                return wave_ts

            marked = self._marks.get(code)
            if marked:
                return marked

            bias = ((price - vwap) / vwap * 100.0) if vwap > 0 else 0.0
            if pct >= self._pct_threshold or bias >= self._bias_threshold:
                if len(self._marks) >= self._capacity:
                    self._marks.pop(next(iter(self._marks)), None)
                self._marks[code] = float(ts)
                return float(ts)
            return 0.0

    def reset_code(self, code: str, ts: float) -> float:
        with self._lock:
            self._marks[code] = float(ts)
            return float(ts)

    def reset(self) -> None:
        with self._lock:
            self._marks.clear()
            self._day = ""


def build_event(
    row: Any,
    snap: Any = None,
    code: str = "",
    source: str = "live_strategy",
    now: Optional[float] = None,
    launch_ts: float = 0.0,
    trade_date: str = "",
) -> SignalEvent:
    """从实时行 + 快照构造 SignalEvent。永不抛异常。"""
    now = float(now if now is not None else time.time())
    missing: List[str] = []

    price = _first_num([(row, "trade"), (row, "price"), (row, "close"), (snap, "trade"), (snap, "price")])
    vwap = _first_num([(row, "vwap"), (snap, "vwap")])
    if vwap <= 0:
        amount = _first_num([(row, "amount"), (snap, "amount")])
        volume = _first_num([(row, "volume"), (row, "vol"), (snap, "volume")])
        if amount > 0 and volume > 0:
            vwap = amount / (volume * 100.0)
    if vwap <= 0:
        missing.append("vwap")

    pct = _first_num([(row, "percent"), (row, "change_pct"), (row, "pct"), (snap, "percent")])
    day_high = _first_num([(row, "high"), (row, "high_price"), (snap, "high_price")])
    day_low = _first_num([(row, "low"), (row, "low_price"), (snap, "low_price")])
    amount = _first_num([(row, "amount"), (snap, "amount")])
    amount_wan = amount / 10000.0 if amount > 0 else _first_num([(snap, "amount_wan")])

    resistance = _first_num(
        [
            (snap, "resistance"),
            (snap, "neck_price"),
            (row, "neck_price"),
            (row, "yesterday_high"),
            (row, "last_high"),
            (row, "high_1d"),
        ]
    )
    base_support = _first_num(
        [
            (snap, "base_support"),
            (snap, "sbc_supp_price"),
            (row, "base_support"),
            (row, "sbc_supp_price"),
        ]
    )

    taker = _first_num([(snap, "taker_buy_ratio"), (row, "taker_buy_ratio")], float("nan"))
    bid_p = _first_num([(snap, "bid_pressure"), (row, "bid_pressure")], float("nan"))
    if taker != taker or bid_p != bid_p:
        try:
            from ats.fusion.enrich import depth_fields

            df_fb = depth_fields(snap, row=row)
            if taker != taker and "taker_buy_ratio" in df_fb:
                taker = float(df_fb["taker_buy_ratio"])
            if bid_p != bid_p and "bid_pressure" in df_fb:
                bid_p = float(df_fb["bid_pressure"])
        except Exception:
            pass

    if taker != taker:
        taker = _NEUTRAL["taker_buy_ratio"]
        missing.append("taker_buy_ratio")

    if bid_p != bid_p:
        bid_p = _NEUTRAL["bid_pressure"]
        missing.append("bid_pressure")

    slope = _first_num([(snap, "slope_score"), (row, "slope_score")], 0.0)
    if slope <= 0:
        slope = _NEUTRAL["slope_score"]
        missing.append("slope_score")

    intent = _first_num([(snap, "intent_score"), (row, "intent_score")], 0.0)
    if intent <= 0:
        intent = _NEUTRAL["intent_score"]
        missing.append("intent_score")

    clarity = _first_num(
        [(snap, "structure_clarity_score"), (snap, "structure_clarity"), (row, "structure_clarity")]
    )
    if clarity <= 0:
        missing.append("structure_clarity")

    freshness = _num(_get(snap, "freshness_s"), 0.0)
    if freshness <= 0:
        src_ts = _first_num([(snap, "server_ts"), (snap, "ts"), (row, "server_ts")])
        if src_ts > 1e9:
            freshness = max(0.0, now - src_ts)

    is_leader = (
        bool(_get(snap, "is_leader"))
        or bool(_get(row, "is_leader"))
        or str(_get(snap, "global_fleet_role") or "") == "LEADER"
    )

    # 相对强度（5 日超额）：只有真实算出 rs5 时才置 has_rs，否则计入 missing，
    # 让覆盖率如实反映"这一轴没有数据"，不按 0 分拉低总分。
    rs5 = _first_num([(snap, "rs5"), (row, "rs5")], 0.0)
    has_rs = bool(_get(snap, "has_rs")) or bool(_get(row, "has_rs"))
    mkt_ret5 = _first_num([(snap, "mkt_ret5"), (row, "mkt_ret5")], 0.0)
    if not has_rs:
        missing.append("rs5")

    ma5 = _first_num([(row, "ma5d"), (row, "ma5"), (snap, "ma5d"), (snap, "ma5")])
    ma10 = _first_num([(row, "ma10d"), (row, "ma10"), (snap, "ma10d"), (snap, "ma10")])
    ma20 = _first_num([(row, "ma20d"), (row, "ma20"), (snap, "ma20d"), (snap, "ma20")])
    vwap_10d = _first_num(
        [
            (row, "ma10dcum"),
            (row, "vwap_10d"),
            (row, "vwap10"),
            (snap, "ma10dcum"),
            (snap, "vwap_10d"),
            (snap, "vwap10"),
            (row, "vwap_cum_5d"),
        ]
    )
    ret5d = _first_num([(row, "per5d"), (row, "ret5d"), (snap, "ret5d"), (snap, "per5d")])
    ret10d = _first_num([(row, "per10d"), (row, "ret10d"), (snap, "ret10d")])
    ret20d = _first_num([(row, "per20d"), (row, "ret20d"), (snap, "ret20d")])
    days_since_high = _first_num([(row, "days_since_high"), (snap, "days_since_high")])
    limit_up_streak = _first_num([(snap, "win"), (row, "win"), (snap, "limit_up_streak"), (row, "limit_up_streak")])
    dist_ma20_pct = ((price - ma20) / ma20 * 100.0) if (price > 0 and ma20 > 0) else 0.0
    rs_day = _first_num([(snap, "rs_day"), (row, "rs_day")])

    # K3 数据源对齐：优先读 DailyContext 严格日线计算的 prev_pct，取不到再用分时快照 per1d
    prev_pct_val = _first_num([(snap, "prev_pct"), (row, "prev_pct"), (snap, "per1d"), (row, "per1d")], 0.0)

    extra: Dict[str, Any] = {"missing": missing, "has_rs": has_rs, "mkt_ret5": mkt_ret5, "prev_pct": prev_pct_val}
    from ats.fusion.context import STRUCTURE_FIELDS
    extra_keys = set(STRUCTURE_FIELDS) | {
        "lead_score",
        "lead_label",
        "rank",
        "lead_gap_min",
        "is_flag",
        "sector_n",
        "consensus",
        "hunger",
        "ice_days",
        "sector",
        "latent_break",
        "patterns",
        "min_vwap_cushion",
        "box10_hover_break",
        "vwap_zero_touch",
        "day_high",
        "structure_confirmed",
        "temporal_strength",
        "is_prime_leader",
    }
    for k in extra_keys:
        val = _first_raw([(snap, k), (row, k)])
        if val is not None:
            extra[k] = val

    return SignalEvent(
        code=str(code or _first_raw([(row, "code"), (snap, "code")]) or ""),
        ts=now,
        source=source,
        price=price,
        vwap=vwap,
        vwap_5d=_first_num([(row, "vwap_cum_5d"), (snap, "vwap_cum_5d"), (row, "vwap_5d"), (snap, "vwap_5d")]),
        vwap_10d=vwap_10d,
        sbc_supp=_first_num([(snap, "sbc_supp_price"), (row, "sbc_supp_price")]),
        sbc_rev=_first_num([(snap, "sbc_rev_price"), (row, "sbc_rev_price")]),
        base_support=base_support,
        resistance=resistance,
        day_high=day_high,
        day_low=day_low,
        pct=pct,
        vol_ratio=_first_num([(row, "ratio"), (row, "vol_ratio"), (snap, "vol_ratio")], 1.0),
        turnover=_first_num([(row, "turnover"), (row, "turnover_rate"), (snap, "turnover")]),
        amount_wan=amount_wan,
        taker_buy_ratio=taker,
        bid_pressure=bid_p,
        structure_clarity=clarity,
        minutes_above_vwap=_first_num([(snap, "minutes_above_vwap"), (row, "minutes_above_vwap")]),
        slope_score=slope,
        intent_score=intent,
        velocity_pct=_first_num([(snap, "velocity_pct"), (row, "velocity_pct")]),
        segment_vol_inc=_first_num([(snap, "segment_vol_inc"), (row, "segment_vol_inc")]),
        sector_resonance=_first_num([(snap, "sector_resonance"), (row, "sector_resonance")]),
        is_leader=is_leader,
        upper_score=_first_num([(snap, "upper_score"), (row, "upper_score")]),
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        ret5d=ret5d,
        ret10d=ret10d,
        ret20d=ret20d,
        days_since_high=days_since_high,
        limit_up_streak=limit_up_streak,
        dist_ma20_pct=dist_ma20_pct,
        launch_ts=float(launch_ts or 0.0),
        freshness_s=freshness,
        trade_date=trade_date or today_str(now),
        rs5=rs5,
        rs_day=rs_day,
        extra=extra,
    )
