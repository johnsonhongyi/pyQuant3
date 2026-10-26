# -*- coding: utf-8 -*-
"""ats/fusion/enrich.py — 融合层输入补全（真实数据，不做推断式造假）。

为什么需要这一层：
    融合引擎的五轴里有三项（承接 / 意图 / 结构清晰度）需要盘口与分时序列，
    而 `stock_live_strategy` 调用 `FusionShadow.observe` 时只传了
    `row`（TDX 行情行）和 `snap`（监控状态字典），这两个都没有这些字段，
    于是 coverage 长期只有 50% 左右，梯度只能靠位置与环境两轴撑着。

    本模块只做"搬运 + 派生"：
      - 盘口字段直接取自 TDX 五档快照（外部提供，本模块不造数）；
      - 分时派生指标（攻角/意图/清晰度/站上均价分钟数）由真实 1 分钟序列算出，
        每项都限定在 0~100 且带明确的统计口径，缺数据就返回空 dict，绝不填默认值冒充。

边界：
    - 纯函数，不做任何 I/O、不加锁、不缓存；
    - 只返回"能算出来"的键，调用方按"缺失才补"的方式合并。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _f(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
    except Exception:
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return v


def depth_fields(snapshot: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """从 TDX 五档快照里取出盘口字段（只搬运，不推算）。

    只取引擎真正会用的键；取不到就不返回，让 adapter 继续按 missing 记账。
    """
    if not snapshot:
        return {}
    out: Dict[str, float] = {}
    for key in ("taker_buy_ratio", "bid_pressure"):
        if snapshot.get(key) is None:
            continue
        val = _f(snapshot.get(key), -1.0)
        if 0.0 < val <= 100.0:
            out[key] = round(val, 2)
    return out


def intraday_fields(
    bars: Any,
    vwap: float = 0.0,
    price: float = 0.0,
    slope_window: int = 15,
    velocity_window: int = 10,
) -> Dict[str, float]:
    """由当日 1 分钟分时序列派生攻角/意图/结构清晰度等指标。

    bars 需要包含 `close`（每分钟价格）与 `vol`（该分钟成交量）两列，
    支持 DataFrame 或 list[dict]；数据不足（<8 根）时返回空 dict。

    口径（全部可复算）：
      slope_score        最近 slope_window 根收盘价的线性斜率，换算成 %/分钟，
                         50 分为横盘，每 0.1%/min 加 30 分。
      velocity_pct       最近 velocity_window 根的净涨幅（%）。
      segment_vol_inc    最近 5 根均量 / 前 20 根均量，衡量增量资金。
      minutes_above_vwap 收盘价站在当日均价之上的分钟数。
      intent_score       上涨分钟成交量占比 × 70 + 净拉升加成 + 15 基线。
      structure_clarity  1 - 噪声比：噪声比 = 平均每分钟波动 / 当日振幅。
    """
    closes, vols = _extract_series(bars)
    n = len(closes)
    if n < 8:
        return {}

    window = max(4, min(int(slope_window), n))
    seg = closes[-window:]
    slope_pct_per_min = _slope_pct_per_min(seg)
    slope_score = _clip(50.0 + slope_pct_per_min * 300.0, 10.0, 100.0)

    vw = max(1, min(int(velocity_window), n - 1))
    base = closes[-vw - 1]
    velocity_pct = ((closes[-1] - base) / base * 100.0) if base > 0 else 0.0

    recent_vol = _mean(vols[-5:]) if n >= 5 else 0.0
    prior_vol = _mean(vols[-25:-5]) if n >= 25 else 0.0
    segment_vol_inc = (recent_vol / prior_vol) if prior_vol > 0 else 0.0

    minutes_above_vwap = 0
    if vwap > 0:
        minutes_above_vwap = sum(1 for c in closes if c > vwap)

    up_vol = 0.0
    total_vol = 0.0
    for i in range(1, n):
        v = max(0.0, vols[i])
        total_vol += v
        if closes[i] > closes[i - 1]:
            up_vol += v
    up_ratio = (up_vol / total_vol) if total_vol > 0 else 0.0
    intent_score = _clip(15.0 + up_ratio * 70.0 + max(-10.0, min(15.0, velocity_pct * 3.0)), 15.0, 100.0)

    hi, lo = max(closes), min(closes)
    rng = hi - lo
    if rng <= 0:
        structure_clarity = 0.0
    else:
        moves = [abs(closes[i] - closes[i - 1]) for i in range(1, n)]
        noise = (_mean(moves) / rng) if moves else 1.0
        structure_clarity = _clip((1.0 - min(1.0, noise * 3.0)) * 100.0, 0.0, 100.0)

    out = {
        "slope_score": round(slope_score, 2),
        "velocity_pct": round(velocity_pct, 3),
        "minutes_above_vwap": float(minutes_above_vwap),
        "intent_score": round(intent_score, 2),
        "structure_clarity": round(structure_clarity, 2),
    }
    if segment_vol_inc > 0:
        out["segment_vol_inc"] = round(segment_vol_inc, 3)
    return out


def merge_missing(base: Dict[str, Any], extra: Dict[str, Any], keys: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """把 extra 合并进 base：只补 base 里没有/为 0 的键，绝不覆盖已有真实值。"""
    out = dict(base or {})
    allow = set(keys) if keys is not None else None
    for k, v in (extra or {}).items():
        if allow is not None and k not in allow:
            continue
        if v is None:
            continue
        cur = out.get(k)
        if cur is None or (isinstance(cur, (int, float)) and float(cur) == 0.0):
            out[k] = v
    return out


def _extract_series(bars: Any):
    """从 DataFrame 或 list[dict] 里取出 (closes, vols) 两条序列。"""
    closes: List[float] = []
    vols: List[float] = []
    if bars is None:
        return closes, vols
    try:
        if hasattr(bars, "columns"):
            if "close" not in getattr(bars, "columns", []):
                return closes, vols
            closes = [_f(x) for x in bars["close"].tolist()]
            vols = [_f(x) for x in bars["vol"].tolist()] if "vol" in bars.columns else [0.0] * len(closes)
            return closes, vols
        seq: Sequence[Any] = bars
        for row in seq:
            if isinstance(row, dict):
                closes.append(_f(row.get("close") or row.get("price")))
                vols.append(_f(row.get("vol") or row.get("volume")))
    except Exception:
        return [], []
    return closes, vols


def _slope_pct_per_min(seg: Sequence[float]) -> float:
    """最小二乘斜率，换算成"每分钟涨跌百分比"（以区间均值为基准）。"""
    n = len(seg)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(seg) / n
    if mean_y <= 0:
        return 0.0
    num = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(seg))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if den <= 0:
        return 0.0
    return (num / den) / mean_y * 100.0


def _mean(values: Sequence[float]) -> float:
    vals = [v for v in values if v == v]
    return (sum(vals) / len(vals)) if vals else 0.0
