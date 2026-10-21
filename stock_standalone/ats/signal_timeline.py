# -*- coding: utf-8 -*-
"""
ats/signal_timeline.py
======================
时序信号引擎 —— L1 时钟与轨迹层

设计要点（对应 docs/tasks/2026-10-20_2045_ATS时序可交易信号引擎落地方案.md §5）：

1. **Bar 时钟**：把 wall clock 映射到当日交易 bar 索引（排除 11:30-13:00 午休），
   使所有判断挂在"时间"而不是"调用次数"上。
2. **幂等聚合**：同一 bar 内多次推送合并到同一槽位（open 取首、high/low 取极值、
   其余取末），多消费方重复调用不会污染时间轴。
3. **显式空洞**：没有推送的 bar 记为 gap（NaN），不当作 0，避免伪信号。
4. **环缓冲**：每股只保留最近 ``capacity`` 根 bar，float32 存储，5500 只全市场约 40MB。
5. **结构轴**：HH/HL/LH/LL 枢轴判定，给出"上下"（抬高/降低）而非仅有涨跌。

本模块纯计算、无 IO、无线程、无 Qt 依赖，可独立单测。
"""

from __future__ import annotations

import time
from array import array
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

__all__ = [
    "Structure",
    "STRUCTURE_LABELS",
    "AM_START",
    "AM_END",
    "PM_START",
    "PM_END",
    "DAY_TRADING_SECONDS",
    "trading_elapsed",
    "BarClock",
    "TrackSeries",
    "TimelineHub",
    "DEFAULT_BAR_SECONDS",
    "DEFAULT_CAPACITY",
]

# ---------------------------------------------------------------------------
# 交易时段常量（秒，自当日 00:00 起算）
# ---------------------------------------------------------------------------
AM_START = 9 * 3600 + 30 * 60      # 09:30:00 -> 34200
AM_END = 11 * 3600 + 30 * 60       # 11:30:00 -> 41400
PM_START = 13 * 3600               # 13:00:00 -> 46800
PM_END = 15 * 3600                 # 15:00:00 -> 54000
DAY_TRADING_SECONDS = (AM_END - AM_START) + (PM_END - PM_START)   # 14400

# CCT 缺省值兜底（真正的取值在 commonTips，这里只做模块内默认，便于独立单测）
DEFAULT_BAR_SECONDS = 15
DEFAULT_CAPACITY = 240             # 240 * 15s = 60 分钟回看窗口


# ---------------------------------------------------------------------------
# 结构轴（"上下"的量化定义）
# ---------------------------------------------------------------------------
class Structure(str, Enum):
    """价格结构分类 —— 回答"高点低点是否在抬高"。"""

    HH_HL = "HH_HL"   # 高点抬高 + 低点抬高：上升结构（进）
    LH_LL = "LH_LL"   # 高点降低 + 低点降低：下降结构（退）
    HH_LL = "HH_LL"   # 高点抬高 + 低点降低：扩张（波动放大，方向未定）
    LH_HL = "LH_HL"   # 高点降低 + 低点抬高：收敛（压缩待变盘）
    RANGE = "RANGE"   # 无有效枢轴或方向不明


STRUCTURE_LABELS: Dict[str, str] = {
    Structure.HH_HL.value: "↗ 上升结构(高抬低抬)",
    Structure.LH_LL.value: "↘ 下降结构(高降低降)",
    Structure.HH_LL.value: "⇗ 扩张结构(高抬低降)",
    Structure.LH_HL.value: "⇘ 收敛结构(高降低抬)",
    Structure.RANGE.value: "↔ 震荡无枢轴",
}


def trading_elapsed(ts: float) -> Optional[int]:
    """把时间戳映射为"当日交易已进行秒数"（排除午休）。

    返回 ``None`` 表示不在连续竞价时段内（盘前/午休/盘后）。
    """
    lt = time.localtime(float(ts))
    hms = lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec
    if AM_START <= hms < AM_END:
        return hms - AM_START
    if PM_START <= hms < PM_END:
        return (AM_END - AM_START) + (hms - PM_START)
    return None


# ---------------------------------------------------------------------------
# Bar 时钟
# ---------------------------------------------------------------------------
class BarClock:
    """wall clock -> 当日交易 bar 索引。

    - ``bar_id`` 取值 ``0 .. bars_per_day-1``，跨午休连续（11:30 的下一根即 13:00 首根）。
    - 非交易时段返回 ``-1``。
    - 同一 bar 内的任何时刻映射到同一 ``bar_id``，这是幂等聚合的前提。
    """

    __slots__ = ("bar_seconds", "bars_per_day")

    def __init__(self, bar_seconds: int = DEFAULT_BAR_SECONDS):
        self.bar_seconds = max(1, int(bar_seconds or DEFAULT_BAR_SECONDS))
        self.bars_per_day = max(1, DAY_TRADING_SECONDS // self.bar_seconds)

    # -- 映射 ---------------------------------------------------------------
    def bar_id(self, ts: Optional[float] = None) -> int:
        ts = time.time() if ts is None else float(ts)
        elapsed = trading_elapsed(ts)
        if elapsed is None:
            return -1
        bid = elapsed // self.bar_seconds
        if bid >= self.bars_per_day:
            bid = self.bars_per_day - 1
        return int(bid)

    def bar_start_ts(self, bar_id: int, day_ts: Optional[float] = None) -> float:
        """返回该 bar 起点的绝对时间戳（同一天内），供事件记录使用。"""
        if bar_id < 0:
            return float(day_ts if day_ts is not None else time.time())
        day_ts = float(day_ts if day_ts is not None else time.time())
        lt = time.localtime(day_ts)
        midnight = time.mktime(
            (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
        )
        elapsed = int(bar_id) * self.bar_seconds
        if elapsed < (AM_END - AM_START):
            return midnight + AM_START + elapsed
        return midnight + PM_START + (elapsed - (AM_END - AM_START))

    def bar_clock_text(self, bar_id: int, day_ts: Optional[float] = None) -> str:
        """``bar_id`` -> ``HH:MM:SS`` 文本，供 UI 直接展示。"""
        if bar_id < 0:
            return "--:--:--"
        ts = self.bar_start_ts(bar_id, day_ts)
        return time.strftime("%H:%M:%S", time.localtime(ts))

    def is_same_day(self, ts_a: float, ts_b: float) -> bool:
        return time.strftime("%Y-%m-%d", time.localtime(ts_a)) == time.strftime(
            "%Y-%m-%d", time.localtime(ts_b)
        )


# ---------------------------------------------------------------------------
# 单股轨迹环
# ---------------------------------------------------------------------------
_FIELDS = ("close", "high", "low", "vol", "pct", "vwap", "temp", "n_samples")


class TrackSeries:
    """单只股票按 bar 对齐的轨迹环缓冲。

    只保留最近 ``capacity`` 根 bar。字段用 ``array('f')``（4 字节/元素）存储：
    相比 numpy 小数组，标量读写快约一个数量级，且内存同样紧凑
    （240 bar x 8 字段 x 5500 只 ≈ 42MB）。

    ``bar_ids[slot] == bid`` 是"该槽位确实存着这一根 bar"的唯一凭据，
    用于区分"空洞"与"旧数据残留"。
    """

    __slots__ = ("code", "bar_seconds", "capacity", "_bar_ids",
                 *("_" + _f for _f in _FIELDS))

    def __init__(self, code: str, bar_seconds: int = DEFAULT_BAR_SECONDS,
                 capacity: int = DEFAULT_CAPACITY):
        self.code = str(code).strip()
        self.bar_seconds = max(1, int(bar_seconds or DEFAULT_BAR_SECONDS))
        self.capacity = max(8, int(capacity or DEFAULT_CAPACITY))
        cap = self.capacity
        self._bar_ids = array("i", [-1]) * cap
        nan = float("nan")
        for name in _FIELDS:
            setattr(self, "_" + name, array("f", [nan]) * cap)

    # -- 写入 ---------------------------------------------------------------
    def update(
        self,
        bar_id: int,
        price: float,
        high: Optional[float] = None,
        low: Optional[float] = None,
        vol: float = 0.0,
        pct: float = 0.0,
        vwap: float = 0.0,
        temp: float = 0.0,
    ) -> bool:
        """写入一根 bar 的观测（幂等）。

        Returns:
            True 表示这是该 bar 的首次写入（新 bar），False 表示合并到已有 bar。
        """
        if bar_id is None or bar_id < 0:
            return False
        try:
            price = float(price)
        except (TypeError, ValueError):
            return False
        if price != price or price <= 0.0:
            return False

        hi = price if high is None else _num(high, price)
        lo = price if low is None else _num(low, price)
        if hi != hi or hi <= 0.0:
            hi = price
        if lo != lo or lo <= 0.0 or lo > hi:
            lo = price if price <= hi else hi

        slot = int(bar_id) % self.capacity
        is_new = int(self._bar_ids[slot]) != int(bar_id)

        if is_new:
            self._bar_ids[slot] = int(bar_id)
            self._close[slot] = price
            self._high[slot] = hi
            self._low[slot] = lo
            self._vol[slot] = _num(vol, 0.0)
            self._pct[slot] = _num(pct, 0.0)
            self._vwap[slot] = _num(vwap, 0.0)
            self._temp[slot] = _num(temp, 0.0)
            self._n_samples[slot] = 1.0
            return True

        # 合并：high/low 取极值，其余取末值
        if hi > self._high[slot]:
            self._high[slot] = hi
        cur_lo = self._low[slot]
        if lo < cur_lo or cur_lo != cur_lo:
            self._low[slot] = lo
        self._close[slot] = price
        if vol:
            self._vol[slot] = _num(vol, 0.0)
        if pct:
            self._pct[slot] = _num(pct, 0.0)
        if vwap:
            self._vwap[slot] = _num(vwap, 0.0)
        if temp:
            self._temp[slot] = _num(temp, 0.0)
        self._n_samples[slot] = self._n_samples[slot] + 1.0
        return False

    # -- 读取 ---------------------------------------------------------------
    def _ok_list(self, n: int, end_bar: int) -> List[bool]:
        """最近 ``n`` 根 bar 是否真实存在（空洞为 False）。"""
        n = max(1, int(n))
        cap = self.capacity
        ids = self._bar_ids
        out: List[bool] = []
        for b in range(end_bar - n + 1, end_bar + 1):
            out.append(b >= 0 and ids[b % cap] == b)
        return out

    def window(self, field: str, n: int, end_bar: int) -> np.ndarray:
        """取最近 ``n`` 根 bar 的某字段，长度恒为 ``n``，空洞为 NaN。"""
        if field not in _FIELDS:
            raise KeyError("unknown field: %s" % field)
        return np.array(
            [np.nan if v is None else v for v in self._window_py(field, n, end_bar)],
            dtype=np.float64,
        )

    def last_price(self, end_bar: int) -> float:
        w = self._window_py("close", 1, end_bar)
        return float(w[0]) if w and w[0] is not None else 0.0

    def bar_count(self, end_bar: int, n: int = DEFAULT_CAPACITY) -> int:
        return sum(self._ok_list(n, end_bar))

    def gap_ratio(self, end_bar: int, n: int = 12) -> float:
        """最近 ``n`` 根 bar 的空洞比例（数据质量诊断用）。"""
        ok = self._ok_list(n, end_bar)
        return float(1.0 - sum(ok) / float(len(ok)))

    # -- 派生量（热路径：一次提窗 + 纯 Python 计算）-------------------------
    def _window3(self, n: int, end_bar: int):
        """一次循环同时取出 close/high/low 三条窗口（热路径专用）。"""
        n = max(1, int(n))
        cap = self.capacity
        ids = self._bar_ids
        ca, ha, la = self._close, self._high, self._low
        cl: List[Optional[float]] = []
        hi: List[Optional[float]] = []
        lo: List[Optional[float]] = []
        for b in range(end_bar - n + 1, end_bar + 1):
            if b < 0:
                cl.append(None)
                hi.append(None)
                lo.append(None)
                continue
            s = b % cap
            if ids[s] == b:
                cl.append(ca[s])
                hi.append(ha[s])
                lo.append(la[s])
            else:
                cl.append(None)
                hi.append(None)
                lo.append(None)
        return cl, hi, lo

    def _window_py(self, field: str, n: int, end_bar: int) -> List[Optional[float]]:
        """取最近 ``n`` 根 bar，返回长度 ``n`` 的 list，空洞为 None。

        纯 Python 逐槽读取：12 点约 5us，明显快于 np.arange+mod+fancy-index 的组合
        （后者在小数组上每次约 14us，几乎全是 numpy 调用开销）。
        """
        n = max(1, int(n))
        cap = self.capacity
        ids = self._bar_ids
        arr = getattr(self, "_" + field)
        out: List[Optional[float]] = []
        for b in range(end_bar - n + 1, end_bar + 1):
            if b < 0:
                out.append(None)
                continue
            s = b % cap
            if int(ids[s]) == b:
                out.append(float(arr[s]))
            else:
                out.append(None)
        return out

    def derive(self, end_bar: int, n: int = 12, line: float = 0.0, k: int = 2,
               n_slope: Optional[int] = None, n_above: int = 4):
        """一次提窗算出 ``(斜率 %/min, 结构, 站线比例)``。

        热路径专用：只做一次 fancy-index，随后纯 Python 计算，
        相比分别调用三个方法快一个数量级。
        """
        if end_bar < 0:
            return 0.0, Structure.RANGE, 0.0
        n = max(1, int(n))
        cl, hi, lo = self._window3(n, end_bar)

        ns = n if n_slope is None else max(1, min(n, int(n_slope)))
        na = max(1, min(n, int(n_above)))
        return (
            _slope_of(cl[-ns:], self.bar_seconds),
            _structure_of(hi, lo, k),
            _above_of(cl[-na:], line),
        )

    def slope(self, n: int = 12, end_bar: int = -1) -> float:
        """最近 ``n`` 根 bar 的收盘线性回归斜率，单位 %/分钟。

        有效样本 < 3 时返回 0.0（不足以判方向）。
        """
        if end_bar < 0:
            return 0.0
        return _slope_of(self._window_py("close", n, end_bar), self.bar_seconds)

    def above_ratio(self, line: float, n: int = 4, end_bar: int = -1) -> float:
        """最近 ``n`` 根 bar 中收盘价站上 ``line`` 的比例（0~1）。"""
        if end_bar < 0 or line is None:
            return 0.0
        return _above_of(self._window_py("close", n, end_bar), line)

    def structure(self, n: int = 12, k: int = 2, end_bar: int = -1) -> Structure:
        """基于枢轴判定 HH/HL/LH/LL 结构。

        枢轴不足时退化为"前半段 vs 后半段"的高/低均值比较，保证恒有结论。
        """
        if end_bar < 0:
            return Structure.RANGE
        return _structure_of(
            self._window_py("high", n, end_bar),
            self._window_py("low", n, end_bar),
            k,
        )

    def extremes(self, bar_from: int, bar_to: int):
        """``[bar_from, bar_to]`` 区间内的 (最高, 最低)，无有效数据返回 (0.0, 0.0)。"""
        if bar_to < bar_from:
            return 0.0, 0.0
        span = bar_to - bar_from + 1
        if span > self.capacity:
            bar_from = bar_to - self.capacity + 1
            span = self.capacity
        hi = self.window("high", span, bar_to)
        lo = self.window("low", span, bar_to)
        vh = hi[~np.isnan(hi)]
        vl = lo[~np.isnan(lo)]
        return (
            float(vh.max()) if vh.size else 0.0,
            float(vl.min()) if vl.size else 0.0,
        )

    def to_rows(self, end_bar: int, n: int = 12) -> List[Dict[str, Any]]:
        """导出最近 ``n`` 根 bar 的明细，供 UI 时间轴视图直接渲染。"""
        if end_bar < 0:
            return []
        n = max(1, int(n))
        cap = self.capacity
        ids = self._bar_ids
        rows: List[Dict[str, Any]] = []
        for b in range(end_bar - n + 1, end_bar + 1):
            if b < 0:
                continue
            slot = b % cap
            if ids[slot] != b:
                continue
            rows.append({
                "bar_id": b,
                "close": _r(self._close[slot]),
                "high": _r(self._high[slot]),
                "low": _r(self._low[slot]),
                "pct": _r(self._pct[slot]),
                "vol": _r(self._vol[slot]),
                "vwap": _r(self._vwap[slot]),
                "temp": _r(self._temp[slot]),
                "n_samples": int(self._n_samples[slot]),
            })
        return rows

    def reset(self) -> None:
        cap = self.capacity
        self._bar_ids[:] = array("i", [-1]) * cap
        nan = float("nan")
        for name in _FIELDS:
            getattr(self, "_" + name)[:] = array("f", [nan]) * cap


# ---------------------------------------------------------------------------
# 多股轨迹中心
# ---------------------------------------------------------------------------
class TimelineHub:
    """管理全市场 ``code -> TrackSeries`` 与共享 ``BarClock``。

    每根 bar 只应 ``ingest`` 一次（同一 bar 重复 ingest 会幂等合并），
    这样"调用次数"与"时间"彻底解耦。
    """

    __slots__ = ("clock", "capacity", "_series", "_day_str", "_last_ts_checked")

    def __init__(self, bar_seconds: int = DEFAULT_BAR_SECONDS,
                 capacity: int = DEFAULT_CAPACITY):
        self.clock = BarClock(bar_seconds)
        self.capacity = max(8, int(capacity or DEFAULT_CAPACITY))
        self._series: Dict[str, TrackSeries] = {}
        self._day_str = time.strftime("%Y-%m-%d")
        self._last_ts_checked = 0.0

    # -- 生命周期 -----------------------------------------------------------
    def _check_rollover(self, ts: float) -> None:
        day = time.strftime("%Y-%m-%d", time.localtime(float(ts)))
        if day != self._day_str:
            self.reset_daily(day)

    def reset_daily(self, day_str: Optional[str] = None) -> None:
        self._day_str = day_str or time.strftime("%Y-%m-%d")
        for s in self._series.values():
            s.reset()

    def apply_bar_seconds(self, bar_seconds: int) -> bool:
        """运行期切换 bar 长度。

        盘中热改会让 ``bar_id`` 的映射整体平移，旧环缓冲里的 bar_id 全部错位，
        窗口会取到错位的 bar 而**不报错**。因此这里强制清空时间轴。
        状态机与账本不受影响（它们只记 bar_id 的差值，不依赖绝对编号）。

        Returns:
            True 表示确实发生了切换。
        """
        bs = max(1, int(bar_seconds or DEFAULT_BAR_SECONDS))
        if bs == self.clock.bar_seconds:
            return False
        self.clock = BarClock(bs)
        for s in self._series.values():
            s.bar_seconds = bs
            s.reset()
        return True

    # -- 写入 ---------------------------------------------------------------
    def series(self, code: str) -> TrackSeries:
        c = str(code).strip()
        s = self._series.get(c)
        if s is None:
            s = TrackSeries(c, self.clock.bar_seconds, self.capacity)
            self._series[c] = s
        return s

    def ingest(
        self,
        code: str,
        ts: float,
        price: float,
        high: Optional[float] = None,
        low: Optional[float] = None,
        vol: float = 0.0,
        pct: float = 0.0,
        vwap: float = 0.0,
        temp: float = 0.0,
    ) -> int:
        """写入一次观测，返回落到的 ``bar_id``（非交易时段返回 -1）。"""
        ts = float(ts)
        # 日期翻转检查 60 秒一次即可：避免每只股票都做 localtime/strftime（实测占 ingest 的 1/3）
        if ts - self._last_ts_checked > 60.0 or ts < self._last_ts_checked:
            self._last_ts_checked = ts
            self._check_rollover(ts)
        bid = self.clock.bar_id(ts)
        if bid < 0:
            return -1
        self.series(code).update(
            bid, price, high=high, low=low, vol=vol, pct=pct, vwap=vwap, temp=temp
        )
        return bid

    # -- 读取 ---------------------------------------------------------------
    def get(self, code: str) -> Optional[TrackSeries]:
        return self._series.get(str(code).strip())

    def tracked_codes(self) -> List[str]:
        return list(self._series.keys())

    def prune(self, max_series: int = 6000) -> int:
        """超出上限时按"最近是否有数据"裁剪，返回裁掉的数量。

        裁剪只丢弃轨迹，不影响任何账本/状态（那些由上层持有）。
        """
        if len(self._series) <= max_series:
            return 0
        # 以每个序列最后一个有效 bar 的写入时间近似新鲜度：用 bar_id 最大值兜底
        def _fresh(s: TrackSeries) -> int:
            ids = s._bar_ids
            return max(ids) if ids else -1

        ordered = sorted(self._series.items(), key=lambda kv: _fresh(kv[1]), reverse=True)
        keep = dict(ordered[:max_series])
        removed = len(self._series) - len(keep)
        self._series = keep
        return removed


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _num(val: Any, default: float) -> float:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return f


def _r(val: Any) -> float:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return 0.0
    if f != f or f in (float("inf"), float("-inf")):
        return 0.0
    return round(f, 3)


def _slope_of(vals: List[Optional[float]], bar_seconds: int) -> float:
    """线性回归斜率 -> %/分钟。有效点 < 3 返回 0。纯 Python，12 点约 2us。"""
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    m = len(pts)
    if m < 3:
        return 0.0
    xm = sum(p[0] for p in pts) / m
    ym = sum(p[1] for p in pts) / m
    num = 0.0
    den = 0.0
    for x, y in pts:
        dx = x - xm
        num += dx * (y - ym)
        den += dx * dx
    if den <= 1e-12:
        return 0.0
    last = pts[-1][1]
    if last <= 0.0:
        return 0.0
    return (num / den) / last * 100.0 * (60.0 / float(bar_seconds))


def _above_of(vals: List[Optional[float]], line: float) -> float:
    try:
        line = float(line)
    except (TypeError, ValueError):
        return 0.0
    if line <= 0.0:
        return 0.0
    v = [x for x in vals if x is not None]
    if not v:
        return 0.0
    return sum(1 for x in v if x >= line) / float(len(v))


def _structure_of(hi: List[Optional[float]], lo: List[Optional[float]],
                  k: int) -> Structure:
    hi_p = _pivot_list(hi, k, want_max=True)
    lo_p = _pivot_list(lo, k, want_max=False)
    if len(hi_p) >= 2 and len(lo_p) >= 2:
        higher_high = hi_p[-1] > hi_p[-2]
        higher_low = lo_p[-1] > lo_p[-2]
    else:
        cmp = _half_compare(hi, lo)
        if cmp is None:
            return Structure.RANGE
        higher_high, higher_low = cmp

    if higher_high and higher_low:
        return Structure.HH_HL
    if (not higher_high) and (not higher_low):
        return Structure.LH_LL
    if higher_high:
        return Structure.HH_LL
    return Structure.LH_HL


def _pivot_list(arr: List[Optional[float]], k: int, want_max: bool) -> List[float]:
    """局部极值（左右各 ``k`` 根确认，要求唯一极值）。纯 Python。"""
    k = max(1, int(k))
    n = len(arr)
    out: List[float] = []
    for i in range(k, n - k):
        seg = arr[i - k:i + k + 1]
        # ``None in seg`` 走 C 层比较，比 any(生成器) 快数倍
        if None in seg:
            continue
        cur = arr[i]
        if want_max:
            if cur >= max(seg) and seg.count(cur) == 1:
                out.append(cur)
        else:
            if cur <= min(seg) and seg.count(cur) == 1:
                out.append(cur)
    return out


def _half_compare(hi: List[Optional[float]], lo: List[Optional[float]]):
    """枢轴不足时的退化判定：比较前后半段的高/低均值。"""
    def _hm(a):
        v = [x for x in a if x is not None]
        if len(v) < 4:
            return None
        h = len(v) // 2
        return (sum(v[:h]) / h, sum(v[h:]) / (len(v) - h))

    mh = _hm(hi)
    ml = _hm(lo)
    if mh is None or ml is None:
        return None
    return (mh[1] > mh[0], ml[1] > ml[0])
