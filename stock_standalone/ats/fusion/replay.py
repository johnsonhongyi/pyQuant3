# -*- coding: utf-8 -*-
"""ats/fusion/replay.py — 按日回放引擎（盘后即可跑，不必等 10 个交易日）。

为什么需要它：
    影子模式要等真实交易日累积样本，一轮迭代至少一天，开发节奏被市场日历绑死。
    本模块把"已经发生的行情"重新喂进融合引擎，当天收盘后就能看到：
        1) 各档位在这套行情里的分布；
        2) 每个决策之后 MFE / MAE / 收盘收益；
        3) 温度与翻转状态在盘中怎么走；
        4) 与现有信号账本（RADAR/WATCH/TRADE）的分歧点。
    改一次权重或阈值，重跑一次回放，当天就能判断方向对不对。

数据来源（全部离线，不联网、不下单）：
    - 3 分钟线：RAMDisk `minute_kline_cache.pkl`（`MinuteKlineCache.save_cache` 的 v2 格式），
      实测覆盖 5576 只 × 最近 5 个交易日 × 每日约 77 根。
    - 信号账本：`logs/signal_snapshots/signal_ledger_latest.json.gz`（当日 entries）。
    - 温度历史：`logs/market_temp_history.json`（可选，缺失时用横截面自算）。

必须说清的近似（不要当成精确回测）：
    - 没有盘口逐笔：`taker_buy_ratio` / `bid_pressure` 取中性 50，`structure_clarity` 取 0；
    - 没有真实 VWAP：用 3 分钟线的 (H+L+C)/3 按量加权近似；
    - 没有真实底台：用 `max(当日最低, 均价×0.985)` 作为止损锚代理，并在 evidence 标注；
    - 没有板块共振：取中性 50。
    因此本引擎用于"方向验证与阈值标定"，不用于估算收益曲线。
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from ats.fusion.adapter import today_str
from ats.fusion.engine import FusionEngine
from ats.fusion.regime import (
    MarketRegime,
    MarketRegimeTracker,
    RegimeSample,
)
from ats.fusion.contract import SignalEvent

logger = logging.getLogger(__name__)
from ats.fusion.trade_sim import T1Simulator, render_trades, summarize_trades
from ats.fusion.context import get_daily_context
from ats.fusion.anomaly import detect_patterns, pattern_score, PATTERN_LATENT_BREAK
from ats.fusion.premarket import get_premarket
from ats.fusion.structure import classify as classify_structure
from ats.fusion.sector import get_sector_map, sector_strength
from dataclasses import replace

_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_CACHE_DEFAULT = r"G:/minute_kline_cache.pkl"
_LIMIT_MAIN = 9.8
_LIMIT_GROWTH = 19.6


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def _app_root() -> str:
    try:
        from sys_utils import get_app_root  # type: ignore

        return get_app_root()
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def default_cache_path() -> str:
    if os.path.exists(_CACHE_DEFAULT):
        return _CACHE_DEFAULT
    for cand in (
        os.path.join(_app_root(), "logs", "minute_kline_cache.pkl"),
        os.path.join(_app_root(), "minute_kline_cache.pkl"),
    ):
        if os.path.exists(cand):
            return cand
    return _CACHE_DEFAULT


def load_minute_cache(path: Optional[str] = None) -> Dict[str, np.ndarray]:
    """读取 MinuteKlineCache v2 文件，返回 {code: structured array}。坏文件返回空。"""
    path = path or default_cache_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            f.seek(0)
            if magic == _ZSTD_MAGIC:
                import zstandard as zstd

                with zstd.ZstdDecompressor().stream_reader(f) as reader:
                    obj = pickle.load(reader)
            else:
                obj = pickle.load(f)
    except Exception:
        return {}

    data = obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(data, dict):
        return {}
    return {str(k).zfill(6): v for k, v in data.items() if isinstance(v, np.ndarray) and len(v)}


def day_bounds(day: str) -> Tuple[int, int]:
    st = time.strptime(day, "%Y-%m-%d")
    start = int(time.mktime((st.tm_year, st.tm_mon, st.tm_mday, 0, 0, 0, 0, 0, -1)))
    return start, start + 86400


def _is_growth_board(code: str) -> bool:
    return code.startswith(("300", "301", "688", "689"))


# ---------------------------------------------------------------------------
# 配置与结果
# ---------------------------------------------------------------------------
@dataclass
class ReplayConfig:
    top_n: int = 600                 # 参与回放的标的数（按成交额代理排序）
    step: int = 1                    # 每 N 根 bar 评估一次
    min_bars: int = 20               # 当日最少 bar 数
    record_tier_min: int = 1         # 只记录 L1 以上（否决原因单独计数）
    max_records: int = 20000
    focus_codes: Tuple[str, ...] = ()   # 验收标的：无论成交额排名如何都纳入
    cuts_mode: str = "percentile"    # percentile=按当日分位自适应；fixed=用配置固定阈值
    hold_days: int = 2               # T+1 模拟最长持有交易日
    target_pct: float = 6.0          # 止盈目标
    max_positions_per_day: int = 5   # 每日最多开仓数（按级别+RAR 取前 N）
    fill_mode: str = "limit"         # limit=挂区间限价等回踩；market=次根开盘市价
    require_pattern: bool = True     # L3+ 必须命中至少一种异动形态（千金买马骨）
    pattern_floor: bool = False      # 形态是否可以直接抬级别（挖掘显示会稀释质量，默认关）
    first_only: bool = False         # 每只票首次 L2+ 后不再评估（全市场自选用，省 3~5 倍）


@dataclass
class ReplayResult:
    day: str
    records: List[Dict[str, Any]] = field(default_factory=list)
    regime_series: List[Dict[str, Any]] = field(default_factory=list)
    tier_stats: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    orders: List[Any] = field(default_factory=list)
    trades: List[Any] = field(default_factory=list)
    trade_stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "meta": self.meta,
            "tier_stats": self.tier_stats,
            "regime_series": self.regime_series,
            "orders": [o.to_dict() for o in self.orders],
            "trades": [t.to_dict() for t in self.trades],
            "trade_stats": self.trade_stats,
            "records": self.records,
        }


def percentile_cuts(samples: List[float], floors: Optional[Dict[int, float]] = None) -> Tuple[Tuple[float, int], ...]:
    """按 RAR 分位生成自适应分档，并受绝对下限约束（单序列版本）。"""
    floors = floors or {4: 68.0, 3: 60.0, 2: 52.0, 1: 45.0}
    if not samples:
        return tuple((floors[t], t) for t in (4, 3, 2, 1))
    arr = np.asarray(samples, dtype="float64")
    cuts = []
    for tier, q in ((4, 98.0), (3, 92.0), (2, 80.0), (1, 60.0)):
        cut = float(np.percentile(arr, q))
        cuts.append((round(max(floors[tier], cut), 1), tier))
    return tuple(cuts)


def cross_section_cuts(
    rar_by_t: Dict[int, List[float]],
    floors: Optional[Dict[int, float]] = None,
) -> Tuple[Tuple[float, int], ...]:
    """按时点横截面分位取中位数作为分档阈值。

    为什么不用全样本分位：
        全样本会被"强势股被评估更多次"污染（越强的票越常进入评估），
        导致阈值随参与标的数漂移。按时点横截面算，等于问"此刻它排第几"，
        与标的池大小无关，也与"某只票今天很活跃"无关。
    """
    floors = floors or {4: 68.0, 3: 60.0, 2: 52.0, 1: 45.0}
    per_q: Dict[float, List[float]] = {98.0: [], 92.0: [], 80.0: [], 60.0: []}
    for _t, vals in rar_by_t.items():
        if len(vals) < 20:
            continue
        arr = np.asarray(vals, dtype="float64")
        for q in per_q:
            per_q[q].append(float(np.percentile(arr, q)))
    cuts = []
    for tier, q in ((4, 98.0), (3, 92.0), (2, 80.0), (1, 60.0)):
        vals = per_q[q]
        cut = float(np.median(vals)) if vals else floors[tier]
        cuts.append((round(max(floors[tier], cut), 1), tier))
    return tuple(cuts)


# ---------------------------------------------------------------------------
# 回放主体
# ---------------------------------------------------------------------------
class DayReplay:
    """把一个交易日的 3 分钟线重放成融合决策流。"""

    def __init__(
        self,
        cache: Optional[Dict[str, np.ndarray]] = None,
        engine: Optional[FusionEngine] = None,
        config: Optional[ReplayConfig] = None,
        cache_path: Optional[str] = None,
    ):
        self.cache = cache if cache is not None else load_minute_cache(cache_path)
        self.cfg = config or ReplayConfig()
        self.engine = engine or FusionEngine()
        self._day_cache: Dict[Tuple[str, str], Dict[str, np.ndarray]] = {}

    # -- 基础取数 ---------------------------------------------------------
    def days(self) -> List[str]:
        """从样本标的的 bar 时间戳推出可用交易日。"""
        seen: set = set()
        for i, (code, arr) in enumerate(self.cache.items()):
            if i >= 200:
                break
            for ts in arr["time"][:: max(1, len(arr) // 60)]:
                seen.add(time.strftime("%Y-%m-%d", time.localtime(int(ts))))
        return sorted(seen)

    def _slice_day(self, code: str, day: str) -> Optional[Dict[str, np.ndarray]]:
        key = (code, day)
        if key in self._day_cache:
            return self._day_cache[key]
        arr = self.cache.get(code)
        if arr is None or len(arr) == 0:
            return None
        start, end = day_bounds(day)
        ts = arr["time"].astype("int64")
        mask = (ts >= start) & (ts < end)
        if int(mask.sum()) < self.cfg.min_bars:
            return None
        sub = arr[mask]
        v = sub["volume"].astype("float64")
        close = sub["close"].astype("float64")
        high = sub["high"].astype("float64")
        low = sub["low"].astype("float64")
        tp = (high + low + close) / 3.0
        cum_v = np.cumsum(v)
        vwap = np.divide(np.cumsum(tp * v), np.maximum(cum_v, 1e-9))
        # --- 盘口代理：3 分钟线能推出来的两个量 ---
        # 外盘占比：用**滚动 10 根**而不是全天累计。
        # 累计口径是滞后的：早盘走弱会把全天的外盘占比压住，
        # 等下午真加速时它还在低位，导致"启动"被误判为"承接差"。
        bar_up = close > sub["open"].astype("float64")
        buy_v = np.where(bar_up, v, 0.0)
        win = np.ones(10)
        roll_buy = np.convolve(buy_v, win, "full")[: len(buy_v)]
        roll_vol = np.convolve(v, win, "full")[: len(v)]
        taker = np.divide(roll_buy, np.maximum(roll_vol, 1e-9)) * 100.0
        # 买盘压：收盘在 bar 区间中的位置，映射到 40~80
        rng = np.maximum(high - low, 1e-6)
        bid = 40.0 + (close - low) / rng * 40.0
        above_vwap = (close >= vwap).astype("float64")
        out = {
            "ts": sub["time"].astype("int64"),
            "open": sub["open"].astype("float64"),
            "high": high,
            "low": low,
            "close": close,
            "volume": v,
            "cum_vol": cum_v,
            "vwap": vwap,
            "taker": taker,
            "bid": bid,
            "above_vwap": above_vwap,
        }
        self._day_cache[key] = out
        return out

    def _prev_close(self, code: str, day: str) -> float:
        arr = self.cache.get(code)
        if arr is None or len(arr) == 0:
            return 0.0
        start, _ = day_bounds(day)
        ts = arr["time"].astype("int64")
        mask = ts < start
        if mask.any():
            return float(arr["close"][mask][-1])
        # 缓存里没有前一日（如缓存起始日）：用当日首根 bar 的开盘价代理前收，
        # 否则该日整池都因 prev_close=0 被剔除，形成"最早一天全盲"的假象。
        m2 = (ts >= start) & (ts < start + 86400)
        if m2.any():
            return float(arr["open"][m2][0])
        return 0.0

    def _prev_high(self, code: str, day: str) -> float:
        arr = self.cache.get(code)
        if arr is None or len(arr) == 0:
            return 0.0
        start, _ = day_bounds(day)
        ts = arr["time"].astype("int64")
        mask = ts < start
        if not mask.any():
            return 0.0
        sub = arr[mask]
        last_day = time.strftime("%Y-%m-%d", time.localtime(int(sub["time"][-1])))
        d_start, d_end = day_bounds(last_day)
        m2 = (sub["time"].astype("int64") >= d_start) & (sub["time"].astype("int64") < d_end)
        if not m2.any():
            return 0.0
        return float(np.max(sub["high"][m2]))

    # -- 宇宙与矩阵 -------------------------------------------------------
    def _universe(self, day: str, focus: Iterable[str] = (), active_only: bool = False) -> List[str]:
        scored: List[Tuple[float, str]] = []
        for code in self.cache:
            sl = self._slice_day(code, day)
            if sl is None:
                continue
            prev = self._prev_close(code, day)
            if prev <= 0:
                continue
            if active_only:
                # 候选池预筛：当日从未涨过 0.8% 的票，引擎本来也不会给 L2+，
                # 先剔掉可以省 2/3 算力（只影响"看谁"，不影响"怎么看"）。
                if float(np.nanmax(sl["close"])) / prev - 1.0 < 0.008:
                    continue
            amount_proxy = float(sl["cum_vol"][-1] * sl["close"][-1])
            scored.append((amount_proxy, code))
        scored.sort(reverse=True)
        picked = [c for _, c in scored[: max(1, self.cfg.top_n)]]

        # 验收标的强制纳入：哪怕成交额排不进 TopN
        for raw in list(focus) + list(self.cfg.focus_codes):
            code = str(raw).strip().zfill(6)
            if code in self.cache and code not in picked and self._slice_day(code, day) is not None:
                picked.append(code)
        return picked

    def _align(self, codes: List[str], day: str) -> Optional[Dict[str, Any]]:
        """把不同标的的 bar 对齐到统一时钟（取并集时间戳，缺失用前值填充）。"""
        slices = {c: self._slice_day(c, day) for c in codes}
        slices = {c: s for c, s in slices.items() if s is not None}
        if not slices:
            return None

        clock = sorted({int(t) for s in slices.values() for t in s["ts"]})
        n_code, n_t = len(slices), len(clock)
        codes = list(slices)

        mat = {
            k: np.full((n_code, n_t), np.nan, dtype="float64")
            for k in ("open", "close", "high", "low", "vwap", "volume", "cum_vol", "taker", "bid", "above_vwap")
        }
        prev_close = np.zeros(n_code, dtype="float64")
        prev_high = np.zeros(n_code, dtype="float64")
        ref = np.array(clock, dtype="int64")

        for i, code in enumerate(codes):
            s = slices[code]
            idx = np.searchsorted(s["ts"], ref, side="right") - 1
            valid = idx >= 0
            if not valid.any():
                continue
            pos = idx[valid]
            for key in mat:
                mat[key][i, valid] = s[key][pos]
            prev_close[i] = self._prev_close(code, day)
            prev_high[i] = self._prev_high(code, day)

        return {
            "codes": codes,
            "clock": ref,
            "mat": mat,
            "prev_close": prev_close,
            "prev_high": prev_high,
            "limit_pct": np.array([_LIMIT_GROWTH if _is_growth_board(c) else _LIMIT_MAIN for c in codes]),
        }

    # -- 主流程 -----------------------------------------------------------
    def run(
        self,
        day: str,
        progress: Optional[Any] = None,
        focus: Iterable[str] = (),
        cuts_override: Optional[Tuple[Tuple[float, int], ...]] = None,
        collect_only: bool = False,
        first_only: Optional[bool] = None,
        active_only: bool = False,
    ) -> ReplayResult:
        day = day or today_str()
        if first_only is not None:
            self.cfg.first_only = bool(first_only)
        if cuts_override:
            self.engine.cuts = cuts_override
        codes = self._universe(day, focus, active_only=active_only)
        aligned = self._align(codes, day)
        if aligned is None:
            return ReplayResult(day=day, meta={"error": "当日无可用分钟线", "codes": 0})

        codes = aligned["codes"]
        mat = aligned["mat"]
        prev_close = aligned["prev_close"]
        prev_high = aligned["prev_high"]
        limit_pct = aligned["limit_pct"]
        clock = aligned["clock"]
        n_code, n_t = mat["close"].shape

        tracker = MarketRegimeTracker()
        regime_series: List[Dict[str, Any]] = []
        records: List[Dict[str, Any]] = []
        veto_counts: Dict[str, int] = {}
        eval_count = 0

        focus_set = {
            str(c).strip().zfill(6) for c in list(focus) + list(self.cfg.focus_codes)
        }
        focus_diag: Dict[str, Dict[str, Any]] = {}
        rar_samples: List[float] = []
        self._rar_by_t: Dict[int, List[float]] = {}

        fut_max, fut_min = _future_extremes(mat["close"])
        # 预计算滚动基准：把循环里的 4 次小切片变成一次矩阵运算
        vol_mean20 = _shift1(_roll_mean(mat["volume"], 20))
        rng_mat = mat["high"] - mat["low"]
        rng_mean20 = _shift1(_roll_mean(rng_mat, 20))
        prev_high20 = _shift1(_roll_max(mat["high"], 20))
        ret5_mat = np.full_like(mat["close"], np.nan)
        if mat["close"].shape[1] > 5:
            ret5_mat[:, 5:] = (mat["close"][:, 5:] / np.maximum(mat["close"][:, :-5], 1e-9) - 1.0) * 100.0

        # 跨日结构：截至昨日（不含当日），避免未来函数
        try:
            _dctx = get_daily_context()
            daily_ctx = {c: _dctx.asof(c, day) for c in codes} if _dctx.ok else {}
        except Exception:
            daily_ctx = {}

        # 注意：tdx_last_df.h5 是"最新一天盘前"的快照，直接套到历史某天就是未来函数。
        # 历史回放一律用 DailyContext 按 (code, day) 现算的 VWAP10；盘前表只做兜底。
        try:
            _pm = get_premarket()
            _pm_vwap = {c: _pm.vwap10(c) for c in codes} if _pm.ok else {}
        except Exception:
            _pm_vwap = {}
        vwap10_map = {}
        for _c in codes:
            _v = float((daily_ctx.get(_c) or {}).get("vwap10", 0.0))
            vwap10_map[_c] = _v if _v > 0 else float(_pm_vwap.get(_c, 0.0))
        latent: Dict[str, float] = {}
        # 赛道（板块）索引：个股分类是"蓄势"，板块才是"赛道"
        try:
            _sm = get_sector_map()
            sec_index = _sm.build_index(codes) if _sm.ok else {}
        except Exception:
            _sm, sec_index = None, {}

        day_open_map = {}
        for _c in codes:
            _sl = self._slice_day(_c, day)
            if _sl is not None and len(_sl["open"]):
                day_open_map[_c] = float(_sl["open"][0])

        done = np.zeros(n_code, dtype=bool)
        launch_idx = np.full(n_code, -1, dtype="int64")
        day_high = np.full(n_code, np.nan)
        day_low = np.full(n_code, np.nan)

        prev_day_vol: Optional[np.ndarray] = None

        for t in range(n_t):
            close = mat["close"][:, t]
            high = mat["high"][:, t]
            low = mat["low"][:, t]
            vwap = mat["vwap"][:, t]
            vol = mat["volume"][:, t]
            valid = ~np.isnan(close)

            # 当日高低点（滚动）
            day_high = np.where(valid, np.fmax(np.nan_to_num(day_high, nan=-1e9), high), day_high)
            day_low = np.where(valid, np.fmin(np.nan_to_num(day_low, nan=1e9), low), day_low)

            pct = np.where(prev_close > 0, (close / np.maximum(prev_close, 1e-9) - 1.0) * 100.0, 0.0)

            # 先手打点：首次涨幅>=1% 或 站上均价 0.5%
            bias = np.where(vwap > 0, (close / np.maximum(vwap, 1e-9) - 1.0) * 100.0, 0.0)
            newly = valid & (launch_idx < 0) & ((pct >= 1.0) | (bias >= 0.5))
            launch_idx = np.where(newly, t, launch_idx)

            # 市场横截面 -> 温度
            v = valid & (prev_close > 0)
            if v.sum() >= 20:
                up_ratio = float(np.mean(pct[v] > 0))
                lim_up = int(np.sum(pct[v] >= limit_pct[v] - 0.2))
                lim_down = int(np.sum(pct[v] <= -limit_pct[v] + 0.2))
                above_vwap = float(np.mean(close[v] >= vwap[v]))
                total_vol = float(np.nansum(vol[v]))
                amount_yoy = 1.0
                if prev_day_vol is not None and prev_day_vol > 0:
                    amount_yoy = min(1.5, max(0.5, total_vol / prev_day_vol))
                regime = tracker.update(
                    RegimeSample(
                        ts=int(clock[t]),
                        up_ratio=up_ratio,
                        limit_up=lim_up,
                        limit_down=lim_down,
                        seal_rate=0.8,
                        amount_yoy=amount_yoy,
                        index_vwap_ratio=above_vwap,
                    )
                )
            else:
                regime = tracker.regime

            if t % max(1, n_t // 12) == 0 or t == n_t - 1:
                regime_series.append(
                    {
                        "ts": int(clock[t]),
                        "time": time.strftime("%H:%M", time.localtime(int(clock[t]))),
                        "temp": round(regime.temp, 1),
                        "stage": regime.stage,
                        "flip": regime.flip_state,
                        "slope": round(regime.slope_5m, 2),
                        "up_ratio": round(float(np.mean(pct[v] > 0)), 3) if v.any() else 0.0,
                        "limit_up": int(np.sum(pct[v] >= limit_pct[v] - 0.2)) if v.any() else 0,
                    }
                )

            if t % max(1, self.cfg.step) != 0:
                continue

            # 相对强度：个股 5 根 bar 收益 - 全池等权 5 根 bar 收益
            ret5_arr = ret5_mat[:, t]
            mkt_ret5 = float(np.nanmean(ret5_arr)) if np.isfinite(ret5_arr).any() else 0.0
            mkt_pct = float(np.mean(pct[v])) if v.any() else 0.0

            # 赛道实时强度与排名（每个时点重算，避免用当日收盘）
            sec_strength: Dict[str, float] = {}
            sec_rank: Dict[str, float] = {}
            sec_breadth: Dict[str, float] = {}
            if sec_index:
                sec_strength = sector_strength(pct, valid, sec_index)
                if sec_strength:
                    _vals = np.array(sorted(sec_strength.values()))
                    for _k, _v in sec_strength.items():
                        sec_rank[_k] = float(np.searchsorted(_vals, _v) / max(1, len(_vals)))
                for _k, _idx in sec_index.items():
                    _m = valid[_idx]
                    if _m.sum() >= 3:
                        sec_breadth[_k] = float(np.mean(pct[_idx][_m] > 0))

            # 龙头代理：当日涨幅进入全池前 1% 且量比>1.5（无板块数据时的近似）
            leader_mask = np.zeros(n_code, dtype=bool)
            t_rar: List[float] = []
            base_mfe = float("nan")
            base_mae = float("nan")
            if v.sum() >= 20:
                thr = float(np.percentile(pct[v], 99.0))
                leader_mask = v & (pct >= max(thr, 3.0))
                _bm = (fut_max[v, t] / close[v] - 1.0) * 100.0
                _bn = (fut_min[v, t] / close[v] - 1.0) * 100.0
                if np.isfinite(_bm).any():
                    base_mfe = float(np.nanmean(_bm))
                if np.isfinite(_bn).any():
                    base_mae = float(np.nanmean(_bn))

            for i in range(n_code):
                if not valid[i] or prev_close[i] <= 0 or done[i]:
                    continue
                if launch_idx[i] < 0 and pct[i] < 0.5 and codes[i] not in focus_set:
                    continue   # 未启动且无涨幅，跳过（省算力）；验收标的例外，便于诊断"为什么没抓到"

                price = float(close[i])
                vw = float(vwap[i])
                dh = float(day_high[i]) if not np.isnan(day_high[i]) else price
                dl = float(day_low[i]) if not np.isnan(day_low[i]) else price
                # 底台代理：当日最低与均价下方 1.5% 取高者，避免止损距离失真；
                # 若价格已跌破该代理，则不给底台（否则会误报"跌破底台"），交给偏离度处理。
                support_proxy = max(dl, vw * 0.985) if vw > 0 else dl
                if price <= support_proxy:
                    support_proxy = 0.0

                _vm = vol_mean20[i, t]
                vol_ratio = float(vol[i] / _vm) if np.isfinite(_vm) and _vm > 0 else 1.0
                vol_ratio = max(0.2, min(8.0, vol_ratio))

                # --- 从 bar 推导的意愿代理（替代实时盘的攻角/意图分） ---
                base_i = max(0, t - 5)
                ret5 = (price / float(mat["close"][i, base_i]) - 1.0) * 100.0 if mat["close"][i, base_i] > 0 else 0.0
                slope_proxy = float(np.clip(40.0 + ret5 * 25.0, 10.0, 100.0))
                vel_proxy = (price / float(mat["close"][i, max(0, t - 3)]) - 1.0) * 100.0 if mat["close"][i, max(0, t - 3)] > 0 else 0.0
                recent = mat["volume"][i, max(0, t - 2): t + 1]
                older = mat["volume"][i, max(0, t - 8): max(1, t - 2)]
                recent = recent[~np.isnan(recent)]
                older = older[~np.isnan(older)]
                accel = (float(np.mean(recent)) / max(1e-9, float(np.mean(older)))) if len(recent) and len(older) else 1.0
                accel = max(0.3, min(3.0, accel))
                seg = mat["close"][i, max(0, t - 4): t + 1]
                seg = seg[~np.isnan(seg)]
                up_ratio_i = float(np.mean(np.diff(seg) > 0)) if len(seg) >= 2 else 0.5
                intent_proxy = float(np.clip(50.0 + (accel - 1.0) * 40.0 + (up_ratio_i - 0.5) * 40.0, 15.0, 100.0))

                # --- 点火强度：与"安全度"分开的弹性指标 ---
                # 现有四轴偏"确认"（位置/承接），会把刚启动的票判成中庸；
                # 这里单独量化"量能扩张 + 波动扩张 + 突破前高 + 加速"。
                vol_exp = float(np.clip(vol_ratio, 0.3, 5.0))
                _rb = rng_mean20[i, t]
                rng_now = (dh - dl) / max(1e-9, price)
                rng_base = float(_rb) / max(1e-9, price) if np.isfinite(_rb) and _rb > 0 else rng_now
                rng_exp = float(np.clip(rng_now / max(1e-6, rng_base), 0.3, 5.0))
                _ph = prev_high20[i, t]
                breakout = 1.0 if (np.isfinite(_ph) and price > float(_ph)) else 0.0
                accel_term = float(np.clip(vel_proxy / 1.5, -2.0, 3.0))
                ignition = float(np.clip(
                    30.0 + 18.0 * np.log2(vol_exp) + 12.0 * np.log2(rng_exp)
                    + 8.0 * accel_term + 22.0 * breakout, 0.0, 100.0
                ))

                launch_ts = float(clock[launch_idx[i]]) if launch_idx[i] >= 0 else 0.0
                # 结构清晰度代理：最近 10 根 bar 中站上均价的比例
                av = mat["above_vwap"][i, max(0, t - 9): t + 1]
                av = av[~np.isnan(av)]
                clarity_proxy = float(np.mean(av) * 100.0) if len(av) else 0.0
                taker_proxy = float(mat["taker"][i, t]) if np.isfinite(mat["taker"][i, t]) else 50.0
                bid_proxy = float(mat["bid"][i, t]) if np.isfinite(mat["bid"][i, t]) else 50.0

                _dc = daily_ctx.get(codes[i]) or {}
                _ma5 = float(_dc.get("ma5", 0.0)); _ma10 = float(_dc.get("ma10", 0.0)); _ma20 = float(_dc.get("ma20", 0.0))
                _day_open = day_open_map.get(codes[i], price)
                ev = SignalEvent(
                    code=codes[i],
                    ts=float(clock[t]),
                    source="replay",
                    price=price,
                    vwap=vw,
                    base_support=support_proxy,
                    resistance=float(prev_high[i]) if prev_high[i] > price else 0.0,
                    day_high=dh,
                    day_low=dl,
                    pct=float(pct[i]),
                    vol_ratio=vol_ratio,
                    turnover=0.0,
                    amount_wan=float(mat["cum_vol"][i, t] * price / 1e4),
                    taker_buy_ratio=max(30.0, min(85.0, taker_proxy)),
                    bid_pressure=max(35.0, min(90.0, bid_proxy)),
                    structure_clarity=clarity_proxy,
                    minutes_above_vwap=(
                        float(max(0.0, (float(clock[t]) - float(clock[launch_idx[i]])) / 60.0))
                        if launch_idx[i] >= 0 else 0.0
                    ),
                    slope_score=slope_proxy,
                    intent_score=intent_proxy,
                    velocity_pct=vel_proxy,
                    segment_vol_inc=accel,
                    sector_resonance=(
                        100.0 * (0.6 * sec_rank.get(_sm.get(codes[i]), 0.5) + 0.4 * sec_breadth.get(_sm.get(codes[i]), 0.5))
                        if sec_index else 0.0
                    ),
                    is_leader=bool(leader_mask[i]),
                    ma5=float((daily_ctx.get(codes[i]) or {}).get("ma5", 0.0)),
                    ma10=float((daily_ctx.get(codes[i]) or {}).get("ma10", 0.0)),
                    ma20=float((daily_ctx.get(codes[i]) or {}).get("ma20", 0.0)),
                    ret5d=float((daily_ctx.get(codes[i]) or {}).get("ret5d", 0.0)),
                    ret10d=float((daily_ctx.get(codes[i]) or {}).get("ret10d", 0.0)),
                    ret20d=float((daily_ctx.get(codes[i]) or {}).get("ret20d", 0.0)),
                    days_since_high=float((daily_ctx.get(codes[i]) or {}).get("days_since_high", 0.0)),
                    limit_up_streak=float((daily_ctx.get(codes[i]) or {}).get("limit_up_streak", 0.0)),
                    dist_ma20_pct=float((daily_ctx.get(codes[i]) or {}).get("dist_ma20_pct", 0.0)),
                    vwap_10d=float(vwap10_map.get(codes[i], 0.0)),
                    rs5=float(ret5_arr[i] - mkt_ret5) if np.isfinite(ret5_arr[i]) else 0.0,
                    rs_day=float(pct[i] - mkt_pct),
                    launch_ts=launch_ts,
                    freshness_s=0.0,
                    trade_date=day,
                    extra={"support_proxy": True, "replay": True, "has_rs": True, "mkt_ret5": mkt_ret5},
                )
                _rs5 = float(ret5_arr[i] - mkt_ret5) if np.isfinite(ret5_arr[i]) else 0.0
                _vw10 = float(vwap10_map.get(codes[i], 0.0))
                _pat_early = detect_patterns(
                    price=price, day_open=_day_open,
                    ma5=_ma5, ma10=_ma10, ma20=_ma20,
                    pct=float(pct[i]), ret_std20=float(_dc.get("ret_std20", 0.0)),
                    vol_ratio=vol_ratio, rs5=_rs5,
                    mkt_ret5=mkt_ret5, is_leader=bool(leader_mask[i]),
                    vwap10=_vw10,
                    vol_dry=float(_dc.get("vol_dry", 1.0) or 1.0),
                    prev_pct=float(_dc.get("prev_pct", 0.0) or 0.0),
                )
                patterns = list(_pat_early)

                # 潜伏池：大盘在跌、它在悄悄抗跌（涨幅还不大），先记下来
                if mkt_ret5 < -0.3 and _rs5 >= 1.0 and float(pct[i]) < 3.0:
                    latent.setdefault(codes[i], float(clock[t]))

                # 潜伏转突破：曾在下跌中抗跌，现在站上 10 日 VWAP，且间隔 <=60 分钟
                _lt = latent.get(codes[i])
                if (_lt is not None and _vw10 > 0 and price > _vw10
                        and 0 <= (float(clock[t]) - _lt) <= 3600):
                    if PATTERN_LATENT_BREAK not in patterns:
                        patterns.append(PATTERN_LATENT_BREAK)

                _ps = pattern_score(patterns)
                _floor = None
                if self.cfg.pattern_floor:
                    _floor = 3 if _ps >= 100 else (2 if _ps >= 70 else None)
                decision = self.engine.evaluate(
                    ev, regime, now=float(clock[t]), tier_floor=_floor
                )
                if PATTERN_LATENT_BREAK in patterns and decision.tier < 2:
                    try:
                        ev2 = replace(ev, launch_ts=float(clock[t]) - 300.0)
                        d2 = self.engine.evaluate(ev2, regime, now=float(clock[t]))
                        if d2.tier > decision.tier:
                            decision = d2
                    except Exception:
                        pass

                # 千金买马骨：没有明确异动形态的，最多给到 L2
                if self.cfg.require_pattern and decision.tier >= 3 and not patterns:
                    decision = self.engine.evaluate(ev, regime, now=float(clock[t]), tier_cap=2)
                eval_count += 1
                t_rar.append(decision.rar)
                if len(rar_samples) < 50000:
                    rar_samples.append(decision.rar)

                # 验收标的诊断：即使被否决也要留下最高分与原因，用来回答"为什么没抓到"
                if codes[i] in focus_set:
                    prev_diag = focus_diag.get(codes[i])
                    if prev_diag is None or decision.rar > prev_diag["max_rar"]:
                        focus_diag[codes[i]] = {
                            "max_rar": round(decision.rar, 2),
                            "time": time.strftime("%H:%M", time.localtime(int(clock[t]))),
                            "tier": decision.tier,
                            "tier_name": decision.tier_name,
                            "veto": decision.veto_reason,
                            "pct": round(float(pct[i]), 2),
                            "axes": decision.axes.to_dict(),
                            "temp": round(regime.temp, 1),
                            "flip": regime.flip_state,
                        }

                if self.cfg.first_only and decision.tier >= 2:
                    done[i] = True

                if collect_only:
                    continue

                if decision.tier < self.cfg.record_tier_min:
                    key = decision.veto_reason.split("(")[0] if decision.veto_reason else "RAR不足"
                    veto_counts[key] = veto_counts.get(key, 0) + 1
                    continue
                if len(records) >= self.cfg.max_records:
                    continue

                fm = fut_max[i, t]
                fn = fut_min[i, t]
                mfe = (float(fm) / price - 1.0) * 100.0 if np.isfinite(fm) else 0.0
                mae = (float(fn) / price - 1.0) * 100.0 if np.isfinite(fn) else 0.0
                close_ret = (float(mat["close"][i, -1]) / price - 1.0) * 100.0 if not np.isnan(mat["close"][i, -1]) else 0.0
                excess = mfe - base_mfe if np.isfinite(base_mfe) else 0.0

                records.append(
                    {
                        "ts": int(clock[t]),
                        "time": time.strftime("%H:%M", time.localtime(int(clock[t]))),
                        "code": codes[i],
                        "tier": decision.tier,
                        "tier_name": decision.tier_name,
                        "rar": round(decision.rar, 2),
                        "axes": decision.axes.to_dict(),
                        "size_pct": decision.size_pct,
                        "entry": round(price, 3),
                        "entry_lo": round(float((decision.entry or {}).get("price_lo") or 0.0), 3),
                        "entry_hi": round(float((decision.entry or {}).get("price_hi") or 0.0), 3),
                        "stop": decision.stop.get("price", 0.0),
                        "age_min": round(decision.age_min, 1),
                        "temp": round(regime.temp, 1),
                        "flip": regime.flip_state,
                        "pct": round(float(pct[i]), 2),
                        "mfe": round(mfe, 2),
                        "mae": round(mae, 2),
                        "close_ret": round(close_ret, 2),
                        "base_mfe": round(base_mfe, 2) if np.isfinite(base_mfe) else 0.0,
                        "excess": round(excess, 2),
                        "ignition": round(ignition, 1),
                        "patterns": patterns,
                        "structure": classify_structure(_dc, price, float(pct[i])),
                        "sector": _sm.get(codes[i]) if sec_index else "",
                        "sector_rank": round(float(sec_rank.get(_sm.get(codes[i]), 0.5)), 2) if sec_index else 0.0,
                        "below_vwap10": bool(_vw10 > 0 and price < _vw10),
                        "dist_ma20": round(float(_dc.get("dist_ma20_pct", 0.0) or 0.0), 2),
                        "vol_dry": round(float(_dc.get("vol_dry", 1.0) or 1.0), 3),
                        "above_vwap": bool(vw > 0 and price >= vw),
                        "pullback_pct": round((dh - price) / price * 100.0, 2) if price > 0 else 0.0,
                        "session": "AM" if time.localtime(int(clock[t])).tm_hour < 13 else "PM",
                        "pattern_score": round(pattern_score(patterns), 1),
                        "leader": bool(leader_mask[i]),
                        "veto": decision.veto_reason,
                    }
                )

            if collect_only and t_rar:
                self._rar_by_t[int(clock[t])] = t_rar

            if progress is not None:
                try:
                    progress(t + 1, n_t)
                except Exception:
                    pass

        stats = summarize_tiers(records)
        self._last_rar_samples = rar_samples

        # ---- T+1 订单与持仓模拟（买入当日不可卖）----
        focus_all = [str(c).strip().zfill(6) for c in list(focus) + list(self.cfg.focus_codes)]
        orders: List[Any] = []
        trades: List[Any] = []
        trade_stats: Dict[str, Any] = {}
        if not collect_only and records:
            try:
                decisions = [
                    {
                        "code": r["code"],
                        "ts": r["ts"],
                        "tier": r["tier"],
                        "rar": r["rar"],
                        "size_pct": r["size_pct"],
                        "stop": r["stop"],
                        "entry_price": r["entry"],
                        "entry": {"price_lo": r.get("entry_lo"), "price_hi": r.get("entry_hi")},
                    }
                    for r in records
                ]
                sim = T1Simulator(self.cache, self.days())
                orders, trades = sim.simulate(
                    decisions,
                    hold_days=self.cfg.hold_days,
                    target_pct=self.cfg.target_pct,
                    max_per_day=self.cfg.max_positions_per_day,
                    focus_codes=tuple(focus_all),
                    fill_mode=self.cfg.fill_mode,
                )
                trade_stats = summarize_trades(trades)
            except Exception as exc:
                logger.debug("[replay] T+1 模拟失败: %s", exc)

        focus_all = [str(c).strip().zfill(6) for c in list(focus) + list(self.cfg.focus_codes)]
        meta = {
            "day": day,
            "codes": n_code,
            "bars": n_t,
            "evaluations": eval_count,
            "records": len(records),
            "focus": list(dict.fromkeys(focus_all)),
            "focus_diag": focus_diag,
            "rar_dist": {
                "p50": round(float(np.percentile(rar_samples, 50)), 1) if rar_samples else 0.0,
                "p90": round(float(np.percentile(rar_samples, 90)), 1) if rar_samples else 0.0,
                "p98": round(float(np.percentile(rar_samples, 98)), 1) if rar_samples else 0.0,
                "max": round(float(np.max(rar_samples)), 1) if rar_samples else 0.0,
            },
            "veto_counts": dict(sorted(veto_counts.items(), key=lambda x: -x[1])[:10]),
            "cache_path": default_cache_path(),
            "orders": len(orders),
            "orders_filled": sum(1 for o in orders if o.status == "FILLED"),
            "trades": len(trades),
            "trade_stats": trade_stats,
            "approximations": [
                "vwap=3分钟(H+L+C)/3按量加权",
                "taker/bid 由 bar 推导（外盘占比/收盘位置）",
                "structure_clarity=近10根站上均价比例",
                "base_support=当日最低与均价×0.985 取高",
                "T+1：买入当日不卖出，止损最早次日生效",
            ],
        }
        return ReplayResult(
            day=day, records=records, regime_series=regime_series,
            tier_stats=stats, meta=meta, orders=orders, trades=trades, trade_stats=trade_stats,
        )

    def discover(
        self,
        day: str,
        top_k: int = 20,
        cutoff: str = "14:00",
        opportunity_pct: float = 5.0,
    ) -> Dict[str, Any]:
        """让系统自己在全市场里选票，再用事后走势打分（不给答案）。

        口径：
            - 系统自选 = 每只票"首次达到 L2+"的那一刻，按 RAR 取前 top_k，且时间 <= cutoff；
            - 机会集   = 当日 10:00 到收盘涨幅 >= opportunity_pct 的票（事后真相）；
            - 命中     = 系统自选里当日收盘相对买入价 >= 2% 的比例；
            - 召回     = 机会集中被系统选中的比例；
            - 提升     = 命中率 / 全市场基准命中率。
        """
        self.cfg.step = max(2, int(self.cfg.step))
        if self.cfg.cuts_mode == "percentile":
            try:
                sample = DayReplay(
                    cache=self.cache,
                    engine=FusionEngine(params=self.engine.params),
                    config=ReplayConfig(top_n=300, step=2, cuts_mode="percentile"),
                )
                sample.run(day, collect_only=True)
                cuts = cross_section_cuts(getattr(sample, "_rar_by_t", {}))
                res = self.run(day, cuts_override=cuts, first_only=True, active_only=True)
                res.meta["cuts_used"] = {"L{}".format(t): c for c, t in cuts}
            except Exception as exc:
                logger.warning("[replay] 采样分档失败，回退两遍: %s", exc)
                res = self.run_day(day)
        else:
            res = self.run_day(day)
        if res.meta.get("error"):
            return {"day": day, "error": res.meta["error"]}

        def _hm(s: str) -> int:
            try:
                h, m = s.split(":")
                return int(h) * 60 + int(m)
            except Exception:
                return 24 * 60

        cutoff_min = _hm(cutoff)

        # 每只票首次 L2+（真实可执行时点）
        first: Dict[str, Dict[str, Any]] = {}
        for r in sorted(res.records, key=lambda x: x["ts"]):
            if r["tier"] < 2 or r["code"] in first:
                continue
            first[r["code"]] = r

        eligible = {c: r for c, r in first.items() if _hm(r["time"]) <= cutoff_min}
        picks = sorted(eligible.values(), key=lambda r: r["rar"], reverse=True)[:top_k]
        picks_ign = sorted(eligible.values(), key=lambda r: r.get("ignition", 0), reverse=True)[:top_k]

        # 机会集：当日 10:00 到收盘的涨幅（与系统无关）
        aligned = self._align(self._universe(day), day)
        opportunity: Dict[str, float] = {}
        if aligned is not None:
            codes = aligned["codes"]
            close = aligned["mat"]["close"]
            clock = aligned["clock"]
            day_start, _ = day_bounds(day)
            t10 = int(np.searchsorted(clock, day_start + 10 * 3600))
            t10 = max(0, min(t10, close.shape[1] - 1))
            p10 = close[:, t10]
            last = close[:, -1]
            for i, c in enumerate(codes):
                if np.isfinite(p10[i]) and p10[i] > 0 and np.isfinite(last[i]):
                    opportunity[c] = (float(last[i]) / float(p10[i]) - 1.0) * 100.0

        opp_set = {c for c, v in opportunity.items() if v >= opportunity_pct}
        pick_codes = {r["code"] for r in picks}
        hit = [r for r in picks if float(r.get("close_ret") or 0.0) >= 2.0]
        base_rate = (
            sum(1 for v in opportunity.values() if v >= 2.0) / len(opportunity)
            if opportunity else 0.0
        )
        precision = len(hit) / len(picks) if picks else 0.0
        recall = len(pick_codes & opp_set) / len(opp_set) if opp_set else 0.0

        hit_ign = [r for r in picks_ign if float(r.get("close_ret") or 0.0) >= 2.0]
        prec_ign = len(hit_ign) / len(picks_ign) if picks_ign else 0.0
        rec_ign = (len({r["code"] for r in picks_ign} & opp_set) / len(opp_set)) if opp_set else 0.0

        return {
            "day": day,
            "cutoff": cutoff,
            "picks_ign": picks_ign,
            "precision_ign": round(prec_ign, 3),
            "recall_ign": round(rec_ign, 3),
            "lift_ign": round(prec_ign / base_rate, 2) if base_rate > 0 else 0.0,
            "opportunity_pct": opportunity_pct,
            "universe": len(opportunity),
            "opportunity_n": len(opp_set),
            "picks": picks,
            "pick_n": len(picks),
            "hit_n": len(hit),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "base_rate": round(base_rate, 3),
            "lift": round(precision / base_rate, 2) if base_rate > 0 else 0.0,
            "avg_close_ret": round(float(np.mean([r.get("close_ret", 0) for r in picks])), 2) if picks else 0.0,
            "opportunity_sample": sorted(opp_set)[:10],
        }

    def run_day(
        self,
        day: str,
        progress: Optional[Any] = None,
        focus: Iterable[str] = (),
    ) -> ReplayResult:
        """按日回放入口：percentile 模式下先采样当日 RAR 分布，再按分位重跑一遍。"""
        if self.cfg.cuts_mode != "percentile":
            return self.run(day, progress=progress, focus=focus)

        warm = self.run(day, focus=focus, collect_only=True)
        if warm.meta.get("error"):
            return warm
        cuts = cross_section_cuts(getattr(self, "_rar_by_t", {}))
        result = self.run(day, progress=progress, focus=focus, cuts_override=cuts)
        result.meta["cuts_used"] = {"L{}".format(t): c for c, t in cuts}
        return result


def _roll_mean(mat: np.ndarray, w: int) -> np.ndarray:
    """按行滚动均值（忽略 NaN），用于量比/振幅基准，避免循环里反复切片。"""
    v = np.nan_to_num(mat, nan=0.0)
    c = np.isfinite(mat).astype("float64")
    cs = np.cumsum(v, axis=1)
    cc = np.cumsum(c, axis=1)
    out = np.full_like(mat, np.nan)
    out[:, :w] = cs[:, :w] / np.maximum(cc[:, :w], 1.0)
    if mat.shape[1] > w:
        out[:, w:] = (cs[:, w:] - cs[:, :-w]) / np.maximum(cc[:, w:] - cc[:, :-w], 1.0)
    return out


def _roll_max(mat: np.ndarray, w: int) -> np.ndarray:
    out = np.full_like(mat, -np.inf)
    for k in range(w):
        out[:, k:] = np.fmax(out[:, k:], mat[:, : mat.shape[1] - k])
    out[~np.isfinite(out)] = np.nan
    return out


def _shift1(mat: np.ndarray) -> np.ndarray:
    out = np.full_like(mat, np.nan)
    if mat.shape[1] > 1:
        out[:, 1:] = mat[:, :-1]
    return out


def _future_extremes(close: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """每个 (code, t) 之后（严格 t+1 起）的最高/最低收盘价。

    用于计算 MFE/MAE 与"同一时刻全池基线"，后者是把"今天普涨"剥离出去，
    否则任何档位在上涨日都显得很准，无法判断梯度是否真的有区分度。
    """
    n_code, n_t = close.shape
    fut_max = np.full_like(close, np.nan)
    fut_min = np.full_like(close, np.nan)
    for i in range(n_code):
        rev = close[i][::-1]
        fut_max[i] = np.fmax.accumulate(rev)[::-1]
        fut_min[i] = np.fmin.accumulate(rev)[::-1]
    if n_t > 1:
        fut_max = np.concatenate([fut_max[:, 1:], np.full((n_code, 1), np.nan)], axis=1)
        fut_min = np.concatenate([fut_min[:, 1:], np.full((n_code, 1), np.nan)], axis=1)
    return fut_max, fut_min


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
def focus_summary(records: List[Dict[str, Any]], codes: Iterable[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in codes:
        code = str(raw).strip().zfill(6)
        rows = sorted([r for r in records if r.get("code") == code], key=lambda r: r["ts"])
        if not rows:
            out.append({"code": code, "hit": False, "reason": "未捕捉：当日无 L1 以上决策"})
            continue
        act = [r for r in rows if r["tier"] >= 2]
        first = act[0] if act else rows[0]
        best = max(rows, key=lambda r: (r["tier"], r["rar"]))
        out.append(
            {
                "code": code,
                "hit": bool(act),
                "first_time": first["time"],
                "first_tier": first["tier"],
                "first_tier_name": first["tier_name"],
                "first_rar": first["rar"],
                "first_entry": first["entry"],
                "first_pct": first["pct"],
                "first_temp": first["temp"],
                "first_flip": first["flip"],
                "mfe": first["mfe"],
                "mae": first["mae"],
                "close_ret": first["close_ret"],
                "excess": first.get("excess", 0.0),
                "best_tier": best["tier"],
                "best_time": best["time"],
                "best_rar": best["rar"],
                "signals": len(rows),
            }
        )
    return out


def render_focus(result: ReplayResult, codes: Iterable[str]) -> str:
    rows = focus_summary(result.records, codes)
    if not rows:
        return ""
    diag = (result.meta or {}).get("focus_diag") or {}
    dist = (result.meta or {}).get("rar_dist") or {}
    lines = ["## 验收标的（走出来的答案 vs 系统触发）", ""]
    lines.append("| 代码 | 结论 | 首触发 | 级别 | RAR | 触发时涨幅 | 温度 | 之后MFE | MAE | 收盘 | 当日最高级 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if not r.get("hit") and r.get("first_time") is None:
            lines.append("| {} | ❌ 未捕捉 | - | - | - | - | - | - | - | - | - |".format(r["code"]))
            continue
        verdict = "✅ 捕捉" if r["hit"] else "⚠️ 仅观察"
        lines.append(
            "| {} | {} | {} | {} | {} | {}% | {}℃ | {}% | {}% | {}% | L{} |".format(
                r["code"], verdict, r["first_time"], r["first_tier_name"], r["first_rar"],
                r["first_pct"], r["first_temp"], r["mfe"], r["mae"], r["close_ret"], r["best_tier"],
            )
        )
    lines.append("")

    if diag:
        lines.append("### 未达标原因诊断（当日该标的最高 RAR）")
        lines.append("| 代码 | 最高RAR | 时间 | 判定 | 否决原因 | 位置/承接/意愿/环境 |")
        lines.append("|---|---|---|---|---|---|")
        for code, d in diag.items():
            ax = d.get("axes") or {}
            lines.append(
                "| {} | {} | {} | {} | {} | {}/{}/{}/{} |".format(
                    code, d.get("max_rar"), d.get("time"), d.get("tier_name"),
                    d.get("veto") or "-",
                    ax.get("position"), ax.get("support"), ax.get("intent"), ax.get("regime"),
                )
            )
        lines.append("")
        if dist:
            lines.append(
                "当日全池 RAR 分布：p50={} / p90={} / p98={} / max={}　"
                "（对照可判断阈值是否偏高：若验收标的最高分落在 p90~p98 之间，说明只需下调到 p95 左右即可捕捉）".format(
                    dist.get("p50"), dist.get("p90"), dist.get("p98"), dist.get("max")
                )
            )
            lines.append("")
    return "\n".join(lines)


def render_discover(d: Dict[str, Any]) -> str:
    if d.get("error"):
        return "## 全市场自选\n\n- ❌ {}".format(d["error"])
    lines = ["## 全市场自选（系统自己挖，未给答案）", ""]
    lines.append(
        "- {}｜全池 {} 只｜当日涨幅≥{}% 的机会 {} 只｜系统自选 {} 只（{} 前）".format(
            d["day"], d["universe"], d["opportunity_pct"], d["opportunity_n"],
            d["pick_n"], d["cutoff"],
        )
    )
    lines.append(
        "- 按 RAR 自选：命中率 {:.1%}（收盘≥+2%）｜基准 {:.1%}｜提升 {}x｜**召回 {:.1%}**".format(
            d["precision"], d["base_rate"], d["lift"], d["recall"],
        )
    )
    lines.append(
        "- 按点火强度自选：命中率 {:.1%}｜提升 {}x｜**召回 {:.1%}**".format(
            d.get("precision_ign", 0.0), d.get("lift_ign", 0.0), d.get("recall_ign", 0.0),
        )
    )
    lines.append(
        "- 自选平均收盘收益 {}%｜机会集 {} 只（10:00→收盘 ≥{}%）".format(
            d["avg_close_ret"], d["opportunity_n"], d["opportunity_pct"],
        )
    )
    lines.append("")
    lines.append("| # | 代码 | 首次L2+ | 级别 | RAR | 点火 | 买入价 | 当时涨幅 | 之后MFE | 收盘 | 超额 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(d["picks"], 1):
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {}% | {}% | {}% | {}% |".format(
                i, r["code"], r["time"], r["tier_name"], r["rar"], r.get("ignition", 0),
                r["entry"], r["pct"], r["mfe"], r["close_ret"], r.get("excess", 0),
            )
        )
    lines.append("")
    return "\n".join(lines)


def summarize_tiers(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按档位统计事后表现：MFE / MAE / 收盘收益 / 胜率。"""
    out: Dict[str, Any] = {}
    for tier in (4, 3, 2, 1):
        rows = [r for r in records if r.get("tier") == tier]
        if not rows:
            out["L{}".format(tier)] = {"n": 0}
            continue
        mfe = [float(r["mfe"]) for r in rows]
        mae = [float(r["mae"]) for r in rows]
        ret = [float(r["close_ret"]) for r in rows]
        exc = [float(r.get("excess", 0.0)) for r in rows]
        wins = sum(1 for x in mfe if x >= 1.5)
        beats = sum(1 for x in exc if x > 0)
        out["L{}".format(tier)] = {
            "n": len(rows),
            "codes": len({r["code"] for r in rows}),
            "mfe_avg": round(float(np.mean(mfe)), 2),
            "mfe_p90": round(float(np.percentile(mfe, 90)), 2),
            "mae_avg": round(float(np.mean(mae)), 2),
            "close_ret_avg": round(float(np.mean(ret)), 2),
            "excess_avg": round(float(np.mean(exc)), 2),
            "beat_rate": round(beats / len(rows), 3),
            "win_rate": round(wins / len(rows), 3),
            "avg_size_pct": round(float(np.mean([r["size_pct"] for r in rows])), 1),
        }
    return out


def render_report(result: ReplayResult, top: int = 20) -> str:
    m = result.meta
    lines = ["# 融合梯度回放报告 {}".format(result.day), ""]
    if m.get("error"):
        lines.append("- ❌ {}".format(m["error"]))
        return "\n".join(lines)

    lines.append(
        "- 标的 {} 只｜bar {} 根｜评估 {} 次｜记录 {} 条".format(
            m["codes"], m["bars"], m["evaluations"], m["records"]
        )
    )
    if m.get("cuts_used"):
        lines.append(
            "- 自适应分档（当日分位 + 绝对下限）：{}".format(
                " / ".join("{}≥{}".format(k, v) for k, v in m["cuts_used"].items())
            )
        )
    lines.append("")

    if m.get("focus"):
        section = render_focus(result, m["focus"])
        if section:
            lines.append(section)

    lines.append("## 分档事后表现（MFE=之后最高收盘，MAE=之后最低收盘，超额=相对同时刻全池）")
    lines.append("| 档位 | 样本 | 标的数 | 平均MFE | MFE p90 | 平均MAE | 收盘收益 | 超额 | 跑赢率 | 胜率(≥1.5%) | 平均仓位 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for tier in ("L4", "L3", "L2", "L1"):
        s = result.tier_stats.get(tier) or {}
        if not s.get("n"):
            lines.append("| {} | 0 | - | - | - | - | - | - | - | - | - |".format(tier))
            continue
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {:.1%} | {:.1%} | {} |".format(
                tier, s["n"], s["codes"], s["mfe_avg"], s["mfe_p90"], s["mae_avg"],
                s["close_ret_avg"], s["excess_avg"], s["beat_rate"], s["win_rate"], s["avg_size_pct"],
            )
        )
    lines.append("")

    if result.orders:
        lines.append(render_trades(result.orders, result.trades))
        lines.append("")

    lines.append("## 温度轨迹")
    lines.append("| 时间 | 温度 | 阶段 | 翻转 | 斜率 | 上涨占比 | 涨停 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in result.regime_series:
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                r["time"], r["temp"], r["stage"], r["flip"], r["slope"], r["up_ratio"], r["limit_up"]
            )
        )
    lines.append("")

    lines.append("## 否决原因 Top")
    if m.get("veto_counts"):
        for k, v in m["veto_counts"].items():
            lines.append("- {}：{}".format(k, v))
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 决策明细 Top {}".format(top))
    lines.append("| 时间 | 代码 | 级别 | RAR | 仓位 | 涨幅 | MFE | MAE | 收盘 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    ranked = sorted(result.records, key=lambda r: (r["tier"], r["rar"]), reverse=True)[:top]
    for r in ranked:
        lines.append(
            "| {} | {} | {} | {} | {}% | {}% | {}% | {}% | {}% |".format(
                r["time"], r["code"], r["tier_name"], r["rar"], r["size_pct"],
                r["pct"], r["mfe"], r["mae"], r["close_ret"],
            )
        )
    lines.append("")
    lines.append("## 近似说明")
    for item in m.get("approximations", []):
        lines.append("- {}".format(item))
    return "\n".join(lines)


def save_result(result: ReplayResult, out_dir: Optional[str] = None) -> Dict[str, str]:
    out_dir = out_dir or os.path.join(_app_root(), "logs", "fusion_replay")
    os.makedirs(out_dir, exist_ok=True)
    jsonl_path = os.path.join(out_dir, "{}.jsonl".format(result.day))
    md_path = os.path.join(out_dir, "{}.md".format(result.day))
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in result.records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_report(result))
    return {"jsonl": jsonl_path, "markdown": md_path}


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="融合梯度按日回放")
    parser.add_argument("--day", default="", help="交易日 YYYY-MM-DD，默认取缓存最后一天")
    parser.add_argument("--top", type=int, default=600, help="参与回放的标的数")
    parser.add_argument("--step", type=int, default=1, help="每 N 根 bar 评估一次")
    parser.add_argument("--cache", default="", help="分钟线缓存路径")
    parser.add_argument("--focus", default="", help="验收标的，逗号分隔，如 688787,300296")
    parser.add_argument("--fill", default="limit", choices=("limit", "market"), help="成交方式：挂限价等回踩 / 次根开盘市价")
    parser.add_argument("--max-pos", type=int, default=5, help="每日最多开仓数")
    parser.add_argument("--out", default="", help="输出目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    parser.add_argument("--discover", action="store_true", help="全市场自选模式：系统自己选票并打分")
    parser.add_argument("--top-k", type=int, default=20, help="自选前 K 只")
    parser.add_argument("--cutoff", default="14:00", help="自选时间上限 HH:MM")
    args = parser.parse_args(argv)

    focus = tuple(c.strip() for c in args.focus.split(",") if c.strip())
    rp = DayReplay(
        cache_path=args.cache or None,
        config=ReplayConfig(top_n=args.top, step=args.step, focus_codes=focus,
                            fill_mode=args.fill, max_positions_per_day=args.max_pos),
    )
    if not rp.cache:
        print("❌ 找不到可用的分钟线缓存")
        return 2
    day = args.day or (rp.days()[-1] if rp.days() else today_str())

    if args.discover:
        disc = rp.discover(day, top_k=args.top_k, cutoff=args.cutoff)
        if args.json:
            print(json.dumps({k: v for k, v in disc.items() if k != "picks"}, ensure_ascii=False, indent=2))
        else:
            print(render_discover(disc))
        return 0

    result = rp.run_day(day, focus=focus)
    paths = save_result(result, args.out or None)

    if args.json:
        print(json.dumps({"day": day, "meta": result.meta, "tier_stats": result.tier_stats}, ensure_ascii=False, indent=2))
    else:
        print(render_report(result))
    print("\n落盘: {} | {}".format(paths["jsonl"], paths["markdown"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
