# -*- coding: utf-8 -*-
"""ats/fusion/context.py — 跨日上下文（日线级）。

为什么必须补：
    原来的回放把每个交易日当成孤立的一天，看不到"昨天在哪、前几天怎么走、
    这是第几个板、离 20 日高点多远"。于是所有"启动"看起来都一样，
    分不清"第一根放量"和"第五根加速"。

数据源：`G:/tdx_all_df_300.h5` 的 `/all_300`（日线 OHLCV，实测 36 个交易日，
2026-08-27 ~ 2026-10-23，全市场）。只读，不参与实盘。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np

_DAILY_CANDIDATES = (
    r"G:/tdx_all_df_300.h5",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "JSONData", "tdx_all_df_300.h5"),
)


def _find_daily_path() -> Optional[str]:
    for p in _DAILY_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


class DailyContext:
    """按 (code, 交易日) 提供"截至昨日"的多日结构。

    刻意只用 **昨日及以前** 的数据，避免把当天收盘信息泄漏进当天决策。
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or _find_daily_path()
        self._by_code: Dict[str, Dict[str, np.ndarray]] = {}
        self._cache: Dict[tuple, Dict[str, float]] = {}
        self.ok = False
        if self.path:
            self._load()

    def _load(self) -> None:
        try:
            import pandas as pd

            df = pd.read_hdf(self.path, key="/all_300")
            # 该表每个 (code, date) 有重复行，必须去重，否则均线与多日收益全部错位
            df = df[~df.index.duplicated(keep="last")]
            codes = df.index.get_level_values(0).astype(str)
            dates = pd.to_datetime(df.index.get_level_values(1), errors="coerce")
            close = df["close"].to_numpy(dtype="float64")
            high = df["high"].to_numpy(dtype="float64")
            low = df["low"].to_numpy(dtype="float64")
            vol = df["vol"].to_numpy(dtype="float64")
            amount = df["amount"].to_numpy(dtype="float64") if "amount" in df.columns else np.zeros_like(vol)

            order = np.lexsort((dates.to_numpy(), codes.to_numpy()))
            codes_s = codes.to_numpy()[order]
            dates_s = dates.to_numpy()[order]
            close, high, low, vol = close[order], high[order], low[order], vol[order]
            amount = amount[order]

            uniq, starts = np.unique(codes_s, return_index=True)
            ends = np.append(starts[1:], len(codes_s))
            for code, s, e in zip(uniq, starts, ends):
                self._by_code[str(code).zfill(6)] = {
                    "dates": dates_s[s:e],
                    "close": close[s:e],
                    "high": high[s:e],
                    "low": low[s:e],
                    "vol": vol[s:e],
                    "amount": amount[s:e],
                }
            self.ok = bool(self._by_code)
        except Exception:
            self.ok = False

    def days(self) -> List[str]:
        seen = set()
        for v in self._by_code.values():
            for d in v["dates"]:
                try:
                    seen.add(np.datetime64(d, "D").astype(str))
                except Exception:
                    pass
        return sorted(seen)

    def asof(self, code: str, day: str) -> Dict[str, float]:
        """返回截至 day 前一日（不含 day）的结构指标；缺数据返回全 0。"""
        key = (code, day)
        if key in self._cache:
            return self._cache[key]

        out = {
            "ma5": 0.0, "ma10": 0.0, "ma20": 0.0,
            "ret5d": 0.0, "ret10d": 0.0, "ret20d": 0.0,
            "days_since_high": 0.0, "limit_up_streak": 0.0,
            "dist_ma20_pct": 0.0, "vol_ratio_5d": 1.0,
            "ret_std20": 0.0, "vol_mean20": 0.0, "vol_std20": 0.0,
            "vwap5": 0.0, "vwap10": 0.0,
            "vol_ma5": 0.0, "vol_ma20": 0.0, "vol_dry": 1.0,
        }
        v = self._by_code.get(str(code).zfill(6))
        if v is None:
            self._cache[key] = out
            return out

        try:
            target = np.datetime64(day, "D")
            idx = np.searchsorted(v["dates"].astype("datetime64[D]"), target, side="left") - 1
        except Exception:
            idx = -1
        if idx < 0:
            self._cache[key] = out
            return out

        c = v["close"][: idx + 1]
        h = v["high"][: idx + 1]
        vol = v["vol"][: idx + 1]
        n = len(c)
        last = float(c[-1])

        for w, name in ((5, "ma5"), (10, "ma10"), (20, "ma20")):
            if n >= w:
                out[name] = float(np.mean(c[-w:]))
        for w, name in ((5, "ret5d"), (10, "ret10d"), (20, "ret20d")):
            if n > w and c[-w - 1] > 0:
                out[name] = (last / float(c[-w - 1]) - 1.0) * 100.0

        if n >= 20:
            hi = float(np.max(h[-20:]))
            if hi > 0:
                out["days_since_high"] = float(n - 1 - int(np.argmax(h[-20:])))
        if out["ma20"] > 0:
            out["dist_ma20_pct"] = (last / out["ma20"] - 1.0) * 100.0

        # 连板：从最近一天往前数，单日涨幅 >= 9.7% 的连续天数
        streak = 0
        for i in range(n - 1, 0, -1):
            if c[i - 1] > 0 and (c[i] / c[i - 1] - 1.0) * 100.0 >= 9.7:
                streak += 1
            else:
                break
        out["limit_up_streak"] = float(streak)

        # 10 日 / 5 日累计均价（VWAP），只用截至昨日的成交额与成交量
        amt = v["amount"][: idx + 1]
        for w, name in ((5, "vwap5"), (10, "vwap10")):
            if n >= w:
                sv = float(np.sum(vol[-w:]))
                if sv > 0:
                    out[name] = float(np.sum(amt[-w:]) / sv)

        # 缩量程度：5 日均量 / 20 日均量。越小说明越"干"，是放量的前提
        if n >= 21:
            vma5 = float(np.mean(vol[-5:]))
            vma20 = float(np.mean(vol[-20:]))
            out["vol_ma5"] = vma5
            out["vol_ma20"] = vma20
            if vma20 > 0:
                out["vol_dry"] = round(vma5 / vma20, 3)

        if n >= 6 and np.mean(vol[-6:-1]) > 0:
            out["vol_ratio_5d"] = float(vol[-1] / np.mean(vol[-6:-1]))

        # 自身历史波动：用于判断"超出自身走势"的异常
        if n >= 21:
            rets = np.diff(c[-21:]) / np.maximum(c[-21:-1], 1e-9) * 100.0
            out["ret_std20"] = float(np.std(rets)) if len(rets) else 0.0
            v20 = vol[-20:]
            out["vol_mean20"] = float(np.mean(v20))
            out["vol_std20"] = float(np.std(v20)) if len(v20) else 0.0

        self._cache[key] = out
        return out


_CTX: Optional[DailyContext] = None


def get_daily_context() -> DailyContext:
    global _CTX
    if _CTX is None:
        _CTX = DailyContext()
    return _CTX
