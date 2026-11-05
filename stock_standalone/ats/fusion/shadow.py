# -*- coding: utf-8 -*-
"""ats/fusion/shadow.py — 影子观察器（P1）。

职责边界（很重要）：
    - 只读。不改 decision、不改 snap、不下单、不发语音。
    - 仅写影子分片及跟踪状态，不回写 PAPER 或执行入口。
    - 任何异常都吞掉并计数，绝不影响主循环——融合层是"旁听者"。

为什么先做影子：
    现有 9 套打分与监理规则已经在实盘跑着，直接替换等于同时改风控与执行。
    先用 10 个交易日把两套结论并行记录下来，才能回答三个问题：
        1) 覆盖率：有多少标的能构造出有效事件（missing 字段多不多）；
        2) 分歧点：融合层说 L3+ 而现有逻辑否决的，事后谁对；
        3) 分级单调性：L4 的胜率是否真的高于 L3/L2/L1。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ats.fusion.adapter import LaunchTracker, build_event, in_trading_session, is_today, today_str
from ats.fusion.anomaly import PATTERN_BOX10_VWAP_HOVER, PATTERN_COUNTER_HOLD, PATTERN_COUNTER_RECLAIM, PATTERN_LATENT_BREAK, PATTERN_STRUCTURE_CONFIRM, counter_reclaim, detect_patterns, pattern_score, rolling_vwaps
from ats.fusion.config import engine_params, load_config
from ats.fusion.launch_signal import classify_launch
from ats.fusion.engine import FusionBus, FusionEngine
from ats.fusion.kernel import (
    check_data_hygiene,
    compute_config_fingerprint,
    compute_tier_floor,
    resolve_prime_leader,
)
from ats.fusion.regime import MarketRegime, MarketRegimeTracker, RegimeSample
from ats.fusion.structure_timeline import (
    STATUS_BROKEN,
    STATUS_CONFIRMED,
    STATUS_EVICTED,
    STATUS_LABEL,
    STATUS_WAITING,
    StructureSnapshot,
    StructureTimeline,
)
from ats.fusion.tracker import RaceTracker
from ats.fusion.vanguard import (
    LABEL_FLAG,
    LABEL_FOLLOW,
    LABEL_PRIME,
    LABEL_STRIKE,
    LABEL_VANGUARD,
    SectorClock,
)

logger = logging.getLogger(__name__)

_BUY_ACTIONS = ("买入", "加仓", "BUY", "ADD")
_TRACKER_SOURCES = frozenset(("live_strategy", "counter_reclaim", "vanguard_funnel", "strategy_observation"))

_DEFAULT_CUT_FLOORS = {4: 68.0, 3: 60.0, 2: 52.0, 1: 45.0}
_CUT_QUANTILES = ((4, 98.0), (3, 92.0), (2, 80.0), (1, 60.0))


def _quantile(sorted_vals: List[float], q: float) -> float:
    """纯 Python 线性插值分位（避免为一行统计引入 numpy 依赖）。"""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_vals[0])
    pos = (q / 100.0) * (n - 1)
    lo = int(pos)
    hi = min(n - 1, lo + 1)
    frac = pos - lo
    return float(sorted_vals[lo]) * (1.0 - frac) + float(sorted_vals[hi]) * frac


def adaptive_cuts(samples: List[float], floors: Optional[Dict[int, float]] = None) -> tuple:
    """按当日 RAR 分布取分位阈值，并受绝对下限约束，保证 4>3>2>1 严格递减。"""
    floors = floors or _DEFAULT_CUT_FLOORS
    vals = sorted(float(x) for x in samples)
    out: List[tuple] = []
    prev = 101.0
    for tier, q in _CUT_QUANTILES:
        cut = max(float(floors.get(tier, 0.0)), _quantile(vals, q))
        cut = round(cut, 1)
        cut = min(cut, round(prev - 0.1, 1))
        out.append((cut, tier))
        prev = cut
    return tuple(out)


def _pick_float(*values: Any, default: float = 0.0) -> float:
    for v in values:
        if v is None or v == "":
            continue
        try:
            return float(v)
        except Exception:
            continue
    return default


def _app_root() -> str:
    try:
        from sys_utils import get_app_root  # type: ignore

        return get_app_root()
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FusionShadow:
    """影子观察器。线程安全，失败静默。"""

    @staticmethod
    def _tracks_source(source: str) -> bool:
        return source in _TRACKER_SOURCES

    def _record_launch_vwap_slope(self, code: str, ts: float, vwap: float) -> Optional[float]:
        """用同一标的已到达的真实分时 VWAP 样本计算约 5 分钟斜率。"""
        if not (0.0 < ts < float("inf") and 0.0 < vwap < float("inf")):
            return None
        with self._launch_vwap_lock:
            samples = self._launch_vwap_samples.setdefault(str(code).zfill(6), [])
            if samples and ts < samples[-1][0]:
                samples.clear()
            if samples and ts - samples[-1][0] < 30.0:
                samples[-1] = (ts, vwap)
            else:
                samples.append((ts, vwap))
            cutoff = ts - 600.0
            while samples and samples[0][0] < cutoff:
                samples.pop(0)
            prior = [item for item in samples[:-1] if 240.0 <= ts - item[0] <= 420.0]
            if not prior:
                return None
            _, baseline = min(prior, key=lambda item: abs((ts - item[0]) - 300.0))
            if baseline <= 0:
                return None
            return (vwap / baseline - 1.0) * 100.0

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        regime_provider: Optional[Callable[[float], Optional[MarketRegime]]] = None,
        root: Optional[str] = None,
    ):
        self.cfg = config or load_config()
        self.enabled = bool(self.cfg.get("enabled", True))
        self.shadow_only = bool(self.cfg.get("shadow_only", True))

        params = engine_params(self.cfg)
        self.engine = FusionEngine(params=params)
        pf = self.cfg.get("portfolio") or {}
        self.bus = FusionBus(
            self.engine,
            max_l4=int(pf.get("max_l4", 2)),
            max_total_pct=float(pf.get("max_total_pct", 85.0)),
        )
        self.launch = LaunchTracker()
        self.regime_tracker = MarketRegimeTracker()
        self.tracker = RaceTracker()
        self._tracker_loaded = False
        self._strategy_observation_days = {}
        self._tracker_dirty = False
        self._last_tracker_save = 0.0
        self._tracker_save_interval = max(1.0, float(self.cfg.get("tracker_save_interval_s", 15.0)))
        self.sector_clock = SectorClock()
        self._prime_leader_by_sector: Dict[str, str] = {}
        self._latent_pool: Dict[str, float] = {}
        self._counter_reclaim_first: Dict[str, float] = {}
        self._launch_vwap_samples: Dict[str, List[tuple]] = {}
        self._launch_vwap_lock = threading.Lock()
        self._regime_provider = regime_provider

        # 结构机会时间轴
        self._struct_timeline = StructureTimeline(
            cushion_min=float(self.cfg.get("struct_cushion_min", 0.20) or 0.20),
            max_break_n=int(self.cfg.get("struct_max_break_n", 3) or 3),
            rearm_bars=int(self.cfg.get("struct_rearm_bars", 3) or 3),
            drawdown_limit=float(self.cfg.get("struct_drawdown_limit", 1.5) or 1.5),
        )

        self._lock = threading.Lock()
        self._regime_lock = threading.Lock()
        self._market_sample: Optional[Dict[str, float]] = None
        self._stats: Dict[str, Any] = {
            "records": 0,
            "errors": 0,
            "skipped_interval": 0,
            "tier_counts": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0},
            "divergence": {"both_buy": 0, "fusion_only": 0, "legacy_only": 0, "both_skip": 0},
            "missing": {},
        }

        self._root = root or _app_root()
        self._log_dir = os.path.join(self._root, self.cfg.get("log_dir", "logs/fusion_shadow"))
        self._tracker_state_path = os.path.join(
            self._log_dir, "tracker_state_live_strategy_{}.json".format(os.getpid())
        )
        self._max_per_day = int(self.cfg.get("max_records_per_day", 200000))
        self._sample_interval = float(self.cfg.get("sample_interval_s", 3.0))
        self._session_gate = bool(self.cfg.get("session_gate", True))
        self._last_sample: Dict[str, float] = {}

        self._observation_state: Dict[str, tuple] = {}
        self._observation_last_ts: Dict[str, float] = {}
        self._observation_active: Dict[str, bool] = {}
        self._observation_heartbeat = max(60.0, float(self.cfg.get("observation_state_heartbeat_s", 600.0) or 600.0))

        self._fh = None
        self._fh_day = ""
        self._written_today = 0
        self._buf: List[str] = []
        self._last_flush = 0.0

        self._regime: Optional[MarketRegime] = None
        self._regime_ts = 0.0
        self._day = ""
        self._last_rebalance = 0.0

        # ---- 序列化与审计增强（P0/P1）----
        self._seq_no = 0
        self._session_id = "{}_{}_{}".format(today_str(), os.getpid(), int(time.time() * 1000))
        self._config_fingerprint = compute_config_fingerprint(self.cfg)
        self._dropped_write_count = 0
        self._max_records_truncated = False

        self._cuts_mode = str(self.cfg.get("tier_cuts_mode", "adaptive") or "adaptive").lower()
        self._cuts_min_samples = int(self.cfg.get("tier_cuts_min_samples", 30) or 30)
        self._cuts_floors = dict(_DEFAULT_CUT_FLOORS)
        cfg_floors = self.cfg.get("tier_cuts_floors")
        if isinstance(cfg_floors, dict):
            try:
                self._cuts_floors.update({int(k): float(v) for k, v in cfg_floors.items()})
            except Exception:
                pass
        self._rar_samples: List[float] = []
        self._latest_rar_by_code: Dict[str, float] = {}
        self._cuts: Optional[tuple] = None
        self._last_cut_n = 0

        # 梯度热榜持续跟踪独立观察状态机 (Step 3)
        from ats.fusion.hot_pool import HotPoolState
        self.hot_pool = HotPoolState()
        self._last_hot_pool_save_ts = 0.0
        self._hot_pool_seeded_day = ""

        if self.enabled:
            try:
                os.makedirs(self._log_dir, exist_ok=True)
                from ats.fusion.shadow_archive import register_archive_worker
                register_archive_worker(self._log_dir)
            except Exception as exc:
                logger.warning("[fusion] 影子日志目录创建失败，降级为仅内存: %s", exc)

    def write_checkpoint(self, kind: str = "STATE_CHECKPOINT") -> Optional[Dict[str, Any]]:
        """写入检查点记录（STATE_CHECKPOINT 或 EOF_CHECKPOINT）。"""
        if not self.enabled:
            return None
        now = time.time()
        day = today_str(now)
        with self._lock:
            self._seq_no += 1
            seq = self._seq_no
            rec = {
                "schema": 2,
                "checkpoint_kind": str(kind),
                "seq_no": seq,
                "session_id": self._session_id,
                "writer_pid": os.getpid(),
                "writer_exe": os.path.basename(sys.executable or ""),
                "ts": round(now, 3),
                "day": day,
                "config_fingerprint": self._config_fingerprint,
                "stats": dict(self._stats),
                "dropped_write_count": self._dropped_write_count,
                "max_records_truncated": self._max_records_truncated,
                "struct_states": self._struct_timeline.snapshot_state(),
            }
        self._append(rec, day)
        self.flush()
        return rec

    def _refresh_cuts(self) -> None:
        """当日样本足够时，用横截面分位重算 L0~L4 阈值；样本不足则沿用引擎固定阈值。"""
        if self._cuts_mode != "adaptive":
            return
        if len(self._latest_rar_by_code) >= self._cuts_min_samples:
            pool = list(self._latest_rar_by_code.values())
        else:
            pool = self._rar_samples
        n = len(pool)
        if n < self._cuts_min_samples:
            return
        total_n = len(self._rar_samples)
        if self._cuts is not None and (total_n - self._last_cut_n) < 20:
            return
        try:
            self._cuts = adaptive_cuts(pool, self._cuts_floors)
            self._last_cut_n = total_n
        except Exception as exc:
            logger.debug("[fusion] adaptive cuts failed: %s", exc)

    def current_cuts(self) -> tuple:
        return tuple(self._cuts) if self._cuts else tuple(self.engine.cuts)

    def update_market_breadth(
        self,
        up_ratio: float,
        limit_up: int = 0,
        limit_down: int = 0,
        seal_rate: float = 0.8,
        now: Optional[float] = None,
    ) -> None:
        ts = float(now if now is not None else time.time())
        with self._regime_lock:
            self._market_sample = {
                "ts": ts,
                "up_ratio": max(0.0, min(1.0, float(up_ratio))),
                "limit_up": int(limit_up),
                "limit_down": int(limit_down),
                "seal_rate": max(0.0, min(1.0, float(seal_rate))),
            }

    def _read_state_temp(self) -> float:
        state_map = self.cfg.get("state_temp_map") or {}
        try:
            import market_pulse_db  # type: ignore

            published = market_pulse_db.get_current_sentiment_state(today_str())
            if isinstance(published, dict):
                state = str(published.get("state") or "")
                if state in state_map:
                    return float(state_map[state])
        except Exception:
            pass
        return float(state_map.get("NEUTRAL", 50.0))

    def current_regime(self, now: Optional[float] = None) -> MarketRegime:
        now = float(now if now is not None else time.time())
        cached = self._regime
        if cached is not None and now - self._regime_ts < 60.0:
            return cached

        with self._regime_lock:
            if self._regime is not None and now - self._regime_ts < 60.0:
                return self._regime

            if self._regime_provider is not None:
                try:
                    provided = self._regime_provider(now)
                    if provided is not None:
                        self._regime = provided
                        self._regime_ts = now
                        return provided
                except Exception:
                    pass

            temp = self._read_state_temp()
            ms = self._market_sample
            if ms is not None and (now - float(ms.get("ts") or 0.0)) < 180.0:
                up_r = float(ms.get("up_ratio", temp / 100.0))
                lu = int(ms.get("limit_up", 0))
                ld = int(ms.get("limit_down", 0))
                sr = float(ms.get("seal_rate", 0.8))
                eff_temp = 0.55 * temp + 0.45 * (up_r * 100.0)
                sample = RegimeSample(
                    ts=now,
                    temp=eff_temp,
                    up_ratio=up_r,
                    limit_up=lu,
                    limit_down=ld,
                    seal_rate=sr,
                )
            else:
                sample = RegimeSample(ts=now, temp=temp, up_ratio=temp / 100.0, seal_rate=0.8)
            self._regime = self.regime_tracker.update(sample)
            self._regime_ts = now
            return self._regime

    def observe(
        self,
        code: str,
        row: Any,
        snap: Any = None,
        decision: Optional[Dict[str, Any]] = None,
        vetoed: bool = False,
        veto_reason: str = "",
        name: str = "",
        now: Optional[float] = None,
        source: str = "live_strategy",
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """记录一条影子决策。返回落盘记录（未落盘返回 None）。永不抛异常。"""
        if not self.enabled:
            return None
        now = float(now if now is not None else time.time())
        code = str(code or "")

        try:
            if not force and self._session_gate and is_today(now) and not in_trading_session(now):
                with self._lock:
                    self._stats["skipped_off_session"] = self._stats.get("skipped_off_session", 0) + 1
                return None

            day = today_str(now)
            with self._lock:
                if day != self._day:
                    prev_day = self._day
                    self._day = day
                    if prev_day:
                        self.launch.reset()
                        self.sector_clock = SectorClock()
                        self._prime_leader_by_sector.clear()
                        self._latent_pool.clear()
                        self._counter_reclaim_first.clear()
                        self._struct_timeline.reset(day)
                        self._last_sample.clear()
                        self._observation_state.clear()
                        self._observation_last_ts.clear()
                        self._observation_active.clear()
                        self._rar_samples.clear()
                        self._latest_rar_by_code.clear()
                        self._cuts = None
                        self._last_cut_n = 0

                last = self._last_sample.get(code, 0.0)
                if now - last < self._sample_interval:
                    self._stats["skipped_interval"] += 1
                    return None
                self._last_sample[code] = now

            if self._tracks_source(source) and not self._tracker_loaded:
                with self._lock:
                    if not self._tracker_loaded:
                        try:
                            self._load_tracker_states(day)
                        except Exception as exc:
                            logger.warning("[fusion] 跟踪状态恢复失败: %s", exc)
                        self._tracker_loaded = True

            price = 0.0
            try:
                price = float(row.get("trade") or row.get("price") or 0.0)
            except Exception:
                price = 0.0
            pct = 0.0
            try:
                pct = float(row.get("percent") or row.get("change_pct") or 0.0)
            except Exception:
                pct = 0.0
            vwap = 0.0
            try:
                vwap = float(row.get("vwap") or (snap or {}).get("vwap") or 0.0)
            except Exception:
                vwap = 0.0
            day_open = 0.0
            try:
                day_open = float(row.get("open") or (snap or {}).get("open") or price or 0.0)
            except Exception:
                day_open = price

            reset_wave = False
            try:
                reset_wave = bool((snap or {}).get("latent_break") or row.get("latent_break"))
            except Exception:
                reset_wave = False

            event = build_event(
                row=row,
                snap=snap,
                code=code,
                source=source,
                now=now,
                launch_ts=0.0,
                trade_date=day,
            )
            pct = event.pct

            # ---- 前置数据卫生门禁（严格防止脏数据污染状态机）----
            is_hygiene_ok, hygiene_reason = check_data_hygiene(
                event=event,
                expected_day=day,
                stale_seconds=float(self.engine.veto_params.get("stale_seconds", 20.0)),
            )

            patterns: List[str] = []
            launch_signal: Dict[str, Any] = {}
            lead_label = ""
            lead_score = 0.0
            sector = ""
            _is_prime = False
            _floor: Optional[int] = None
            _v3, _v5 = 0.0, 0.0
            track_dict: Dict[str, Any] = {}

            if not is_hygiene_ok:
                # 卫生门禁未通过：直接由引擎产出否决结论，坚决跳过所有状态机更新
                _tl = self._struct_timeline.get(code) or StructureSnapshot(code=code, status=STATUS_WAITING, ts=now)
                event.extra["struct_status"] = _tl.status
                regime = self.current_regime(now)
                with self._lock:
                    self._refresh_cuts()
                    active_cuts = self.current_cuts()
                fusion = self.engine.evaluate(event, regime, now=now, cuts=active_cuts)
            else:
                launch_ts = self.launch.note(code, now, pct, event.price, event.vwap, reset_wave=reset_wave)
                event.launch_ts = launch_ts
                price, vwap = event.price, event.vwap

                mkt_ret5 = float(event.extra.get("mkt_ret5") or 0.0)
                prev_pct = 0.0
                ret_std20 = 0.0
                try:
                    prev_pct = float(
                        event.extra.get("prev_pct")
                        or (snap or {}).get("prev_pct")
                        or (row.get("prev_pct") if hasattr(row, "get") else None)
                        or (row.get("per1d") if hasattr(row, "get") else None)
                        or 0.0
                    )
                    ret_std20 = float(row.get("ret_std20") or (snap or {}).get("ret_std20") or 0.0)
                except Exception:
                    prev_pct = 0.0
                    ret_std20 = 0.0

                _is_box10_ready = bool(
                    event.extra.get("is_box10_ready")
                    or (snap or {}).get("is_box10_ready")
                    or (row.get("is_box10_ready") if hasattr(row, "get") else False)
                )
                _hi_10d = float(
                    event.extra.get("hi_10d")
                    or (snap or {}).get("hi_10d")
                    or (row.get("hi_10d") if hasattr(row, "get") else 0.0)
                    or 0.0
                )
                _hi_pre1 = float(
                    event.extra.get("hi_pre1")
                    or (snap or {}).get("hi_pre1")
                    or (row.get("hi_pre1") if hasattr(row, "get") else 0.0)
                    or 0.0
                )
                _min_cushion = float(
                    event.extra.get("min_vwap_cushion")
                    or (snap or {}).get("min_vwap_cushion")
                    or (row.get("min_vwap_cushion") if hasattr(row, "get") else 0.0)
                    or 0.0
                )
                _is_struct_ready = bool(
                    event.extra.get("is_structure_prejudged")
                    or (snap or {}).get("is_structure_prejudged")
                    or (row.get("is_structure_prejudged") if hasattr(row, "get") else False)
                )
                _close_over_v10 = bool(
                    event.extra.get("close_over_vwap10")
                    or (snap or {}).get("close_over_vwap10")
                    or (row.get("close_over_vwap10") if hasattr(row, "get") else False)
                )
                _touch_cnt = int(
                    event.extra.get("vwap10_touch_count")
                    or (snap or {}).get("vwap10_touch_count")
                    or (row.get("vwap10_touch_count") if hasattr(row, "get") else 0)
                    or 0
                )
                _cushion_roll = _pick_float(
                    event.extra.get("cushion_roll"),
                    (snap or {}).get("cushion_roll"),
                    (row.get("cushion_roll") if hasattr(row, "get") else None),
                    default=_min_cushion,
                )
                _cushion_now = _pick_float(
                    event.extra.get("cushion_now"),
                    (snap or {}).get("cushion_now"),
                    (row.get("cushion_now") if hasattr(row, "get") else None),
                    default=0.0,
                )
                _close_pre1 = _pick_float(
                    event.extra.get("close_pre1"),
                    (snap or {}).get("close_pre1"),
                    (row.get("close_pre1") if hasattr(row, "get") else None),
                    default=0.0,
                )
                _prejudged = bool(_is_struct_ready)

                with self._lock:
                    _tl = self._struct_timeline.update(
                        code=code,
                        ts=now,
                        price=event.price,
                        vwap=event.vwap,
                        hi_pre1=_hi_pre1,
                        close_pre1=_close_pre1,
                        cushion_roll=_cushion_roll,
                        cushion_now=_cushion_now,
                        prejudged=_prejudged,
                    )
                event.extra["struct_status"] = _tl.status
                event.extra["struct_confirm_n"] = _tl.confirm_n
                event.extra["struct_break_n"] = _tl.break_n
                event.extra["struct_reason"] = _tl.reason
                event.extra["struct_cushion_roll"] = _tl.cushion_roll
                event.extra["struct_drawdown_pct"] = _tl.drawdown_pct

                patterns = list(
                    detect_patterns(
                        price=event.price,
                        day_open=day_open,
                        ma5=event.ma5,
                        ma10=event.ma10,
                        ma20=event.ma20,
                        pct=event.pct,
                        ret_std20=ret_std20,
                        vol_ratio=event.vol_ratio,
                        rs5=event.rs5,
                        mkt_ret5=mkt_ret5,
                        is_leader=event.is_leader,
                        vwap10=event.vwap_10d,
                        prev_pct=prev_pct,
                        is_box10_ready=_is_box10_ready,
                        hi_10d=_hi_10d,
                        hi_pre1=_hi_pre1,
                        min_vwap_cushion=_min_cushion,
                        is_structure_prejudged=_is_struct_ready,
                        close_over_vwap10=_close_over_v10,
                        vwap10_touch_count=_touch_cnt,
                        cushion_roll=_cushion_roll,
                        struct_status=_tl.status,
                        vol_dry=float(event.extra.get("vol_dry") or (snap or {}).get("vol_dry") or 1.0),
                    )
                )
                if reset_wave and PATTERN_LATENT_BREAK not in patterns:
                    patterns.append(PATTERN_LATENT_BREAK)

                _amount = _pick_float(row.get("amount"), (snap or {}).get("amount"))
                _volume = _pick_float(row.get("volume"), row.get("vol"), (snap or {}).get("volume"))
                _valid_amount = (event.vwap > 0 and _amount > 0 and _volume > 0 and
                                 any(0.95 <= _amount / (_volume * factor * event.vwap) <= 1.05 for factor in (1, 100)))
                _v3, _v5 = rolling_vwaps(event.extra, event.vwap, _amount / event.vwap if _valid_amount else 0)
                if event.extra.get("vwap_observed_days", 0) >= 5 and counter_reclaim(event.price, event.vwap, _v3,
                                   _v5, _close_pre1, event.pct,
                                   event.extra.get("market_pct"), event.sector_resonance,
                                   _pick_float(row.get("ratio"), row.get("vol_ratio"), (snap or {}).get("vol_ratio")),
                                   event.velocity_pct, float(event.extra.get("vwap_hold_ratio") or 0), event.extra.get("sector_pct")):
                    patterns.append(PATTERN_COUNTER_RECLAIM)
                    with self._lock:
                        self._counter_reclaim_first.setdefault(code, now)
                elif (code in self._counter_reclaim_first and event.velocity_pct >= -0.3
                      and float(event.extra.get("vwap_hold_ratio") or 0) >= 0.7
                      and counter_reclaim(event.price, event.vwap, _v3, _v5, _close_pre1, event.pct,
                                          event.extra.get("market_pct"), event.sector_resonance,
                                          _pick_float(row.get("ratio"), row.get("vol_ratio"), (snap or {}).get("vol_ratio")),
                                          0.001, float(event.extra.get("vwap_hold_ratio") or 0), event.extra.get("sector_pct"))):
                    patterns.append(PATTERN_COUNTER_HOLD)

                with self._lock:
                    if mkt_ret5 < -0.3 and event.rs5 >= 1.0 and event.pct < 3.0:
                        self._latent_pool.setdefault(code, now)
                    _lt = self._latent_pool.get(code)
                    if (
                        _lt is not None
                        and event.vwap_10d > 0
                        and event.price > event.vwap_10d
                        and 0.0 <= (now - _lt) <= 3600.0
                    ):
                        if PATTERN_LATENT_BREAK not in patterns:
                            patterns.append(PATTERN_LATENT_BREAK)

                if PATTERN_LATENT_BREAK in patterns and event.launch_ts > 0 and (now - event.launch_ts) > 600.0:
                    new_launch = self.launch.reset_code(code, max(0.0, now - 300.0))
                    event.launch_ts = new_launch

                event.extra["patterns"] = list(patterns)

                raw_sector = str(
                    event.extra.get("sector")
                    or (row.get("category") if hasattr(row, "get") else "")
                    or ""
                )
                sector = raw_sector.split(";")[0].strip() if raw_sector else ""
                prev_strong = bool(
                    event.extra.get("prev_strong_vwap")
                    or (snap or {}).get("prev_strong_vwap")
                    or (row.get("prev_strong_vwap") if hasattr(row, "get") else False)
                )
                today_strong = bool(event.pct > 0 and event.price >= event.vwap * 0.998)

                if sector and "lead_score" not in event.extra:
                    with self._lock:
                        _lead = self.sector_clock.observe(
                            code=code,
                            sector=sector,
                            ts=now,
                            pct=event.pct,
                            breakout=bool(patterns),
                            is_prime_leader=False,
                        )
                    ld_dict = _lead.to_dict()
                    ld_dict["lead_label"] = _lead.label
                    event.extra.update(ld_dict)

                raw_lead_label = str(event.extra.get("lead_label") or event.extra.get("label") or "")
                lead_gap_min = float(event.extra.get("lead_gap_min") or 0.0)

                _is_prime, lead_label = resolve_prime_leader(
                    code=code,
                    sector=sector,
                    prev_strong=prev_strong,
                    today_strong=today_strong,
                    raw_lead_label=raw_lead_label,
                    lead_gap_min=lead_gap_min,
                    prime_leader_by_sector=self._prime_leader_by_sector,
                    lock=self._lock,
                )
                event.extra["is_prime_leader"] = _is_prime
                event.extra["lead_label"] = lead_label

                lead_score = float(event.extra.get("lead_score") or 0.0)
                event.extra["vwap_slope_5m_pct"] = self._record_launch_vwap_slope(
                    code, float(event.ts), float(event.vwap)
                )
                _prior_low = _pick_float(
                    row.get("lastl1d"), (snap or {}).get("lastl1d"),
                    row.get("prev_low"), (snap or {}).get("prev_low"),
                )
                launch_signal = classify_launch(
                    event, day_open=day_open, prev_low=_prior_low,
                    prev_high=_hi_pre1, prejudged=_is_struct_ready,
                    struct_status=_tl.status,
                )
                event.extra["launch_signal"] = launch_signal
                _ps = pattern_score(patterns)
                if PATTERN_STRUCTURE_CONFIRM in patterns:
                    event.extra["structure_confirmed"] = True
                _floor = compute_tier_floor(
                    patterns=patterns,
                    struct_status=_tl.status,
                    is_prime=_is_prime,
                    is_leader=event.is_leader,
                    lead_label=lead_label,
                    ps=_ps,
                    struct_floor_enabled=True,
                    pattern_floor_enabled=True,
                    max_struct_floor_tier=getattr(self.engine, "max_struct_floor_tier", 4),
                )

                regime = self.current_regime(now)
                with self._lock:
                    self._refresh_cuts()
                    active_cuts = self.current_cuts()

                fusion = self.engine.evaluate(
                    event, regime, now=now, cuts=active_cuts, tier_floor=_floor
                )
                if patterns:
                    for p in patterns:
                        tag = "形态:{}".format(p)
                        if tag not in fusion.evidence:
                            fusion.evidence.append(tag)
                if launch_signal:
                    if (launch_signal["status"] == "CONFIRMED" and fusion.tier >= 2
                            and not fusion.veto_reason and not vetoed
                            and not fusion.provisional and fusion.coverage >= 0.70):
                        launch_signal["permission"] = "MANUAL_CONFIRM"
                    else:
                        launch_signal["permission"] = "WATCH"
                        if fusion.veto_reason:
                            launch_signal["reason"] += "；梯度否决:{}".format(fusion.veto_reason)
                        elif vetoed:
                            launch_signal["reason"] += "；既有策略否决"
                        elif launch_signal["status"] == "CONFIRMED":
                            launch_signal["reason"] += "；待L2及数据覆盖门禁确认"
                    if launch_signal["permission"] == "MANUAL_CONFIRM":
                        try:
                            from ats.reentry_tracker import get_reentry_tracker
                            prior_exit = get_reentry_tracker().prior_exit_context(code)
                            if prior_exit:
                                launch_signal["reentry_permission"] = "MANUAL_CONFIRM"
                                launch_signal["prior_exit"] = prior_exit
                        except Exception as exc:
                            logger.debug("[fusion] 历史平仓上下文不可用 %s: %s", code, exc)
                    fusion.evidence.append(
                        "早盘启动:{}；{}；许可:{}".format(
                            launch_signal["label"], launch_signal["reason"], launch_signal["permission"]
                        )
                    )
                    if launch_signal.get("reentry_permission"):
                        fusion.evidence.append("重新介入许可：存在历史平仓，当前独立入场信号成立；持仓未核实")
                if lead_label in (LABEL_VANGUARD, LABEL_FLAG):
                    ltag = "先锋:{}({:.0f})".format(lead_label, lead_score)
                    if ltag not in fusion.evidence:
                        fusion.evidence.append(ltag)

            # 更新组合 Bus（直接复用当次 fusion，消除二次无参重评）
            with self._lock:
                self._rar_samples.append(float(fusion.rar))
                if len(self._rar_samples) > 4000:
                    del self._rar_samples[:1000]
                if code:
                    self._latest_rar_by_code[code] = float(fusion.rar)
                self.bus.update(event, regime, decision=fusion, cuts=active_cuts, tier_floor=_floor)
                if now - self._last_rebalance >= 60.0:
                    try:
                        self.bus.rebalance()
                        self._last_rebalance = now
                    except Exception:
                        pass
                try:
                    if (is_hygiene_ok
                            and self._tracks_source(source)
                            and "pct" not in event.extra.get("missing", ())
                            and event.trade_date == day):
                        _st = self.tracker.update(
                            code=code, ts=now, price=event.price, pct=event.pct,
                            vwap10=event.vwap_10d, vwap=event.vwap, vol_ratio=event.vol_ratio,
                            tier=fusion.tier, rar=fusion.rar, patterns=patterns, day=day,
                            anomaly=bool(patterns) or fusion.tier >= 2,
                            consensus=float(event.extra.get("consensus") or 0.5),
                            temp=regime.temp if regime else 50.0,
                            lead_label=lead_label, lead_score=lead_score,
                        )
                        track_dict = _st.to_dict()
                        self._tracker_dirty = True
                        self._save_tracker_locked()
                except Exception:
                    track_dict = {}

            legacy_action = str((decision or {}).get("action") or "")
            legacy_buy = legacy_action in _BUY_ACTIONS
            fusion_buy = fusion.tier >= 2

            if legacy_buy and fusion_buy:
                divergence = "both_buy"
            elif fusion_buy:
                divergence = "fusion_only"
            elif legacy_buy:
                divergence = "legacy_only"
            else:
                divergence = "both_skip"

            snap_name = str((snap or {}).get("name") or "")

            # 策略观察源节流（保持在状态与组合更新之后；状态、档位、先锋变化 100% 落盘）
            if source == "strategy_observation":
                from ats.fusion.observation import observation_reason
                reason = observation_reason(event.extra.get("observation_evidence"))
                state_key = (
                    str(getattr(_tl, "status", "") or ""),
                    int(getattr(_tl, "confirm_n", 0) or 0),
                    int(fusion.tier),
                    str(lead_label),
                    reason,
                    launch_signal.get("type", "") if isinstance(launch_signal, dict) else "",
                    launch_signal.get("status", "") if isinstance(launch_signal, dict) else "",
                    launch_signal.get("permission", "") if isinstance(launch_signal, dict) else "",
                )
                if reason or fusion.tier >= 2:
                    self._observation_active[code] = True
                if self._observation_state.get(code) != state_key:
                    self._observation_state[code] = state_key
                    self._observation_last_ts[code] = now
                elif (self._observation_active.get(code)
                      and (now - self._observation_last_ts.get(code, 0.0)) >= self._observation_heartbeat):
                    self._observation_last_ts[code] = now
                else:
                    with self._lock:
                        self._stats["skipped_state"] = self._stats.get("skipped_state", 0) + 1
                    return None

            with self._lock:
                self._seq_no += 1
                seq = self._seq_no

            record = {
                "schema": 2,
                "writer_pid": os.getpid(),
                "writer_exe": os.path.basename(sys.executable or ""),
                "seq_no": seq,
                "session_id": self._session_id,
                "config_fingerprint": self._config_fingerprint,
                "ts": round(now, 3),
                "day": day,
                "code": code,
                "name": name or snap_name,
                "source": source,
                "price": round(float(price or 0.0), 3),
                "pct": round(float(pct), 3) if "pct" not in event.extra.get("missing", ()) else None,
                "pct_source": event.extra.get("pct_source"),
                "reported_pct": event.extra.get("reported_pct"),
                "quote_prev_close": event.extra.get("quote_prev_close"),
                "vwap": round(float(vwap or 0.0), 3),
                "trade_date": event.trade_date,
                "hit": bool(fusion.tier >= 2),
                "coverage": round(float(getattr(fusion, "coverage", 0.0) or 0.0), 3),
                "cuts": [list(item) if isinstance(item, (list, tuple)) else item for item in (active_cuts or self.engine.cuts)],
                "tier_floor": _floor,
                "event_snapshot": event.to_dict(),
                "patterns": patterns,
                "launch_signal": launch_signal,
                "observation_evidence": event.extra.get("observation_evidence"),
                "counter_reclaim_first_ts": self._counter_reclaim_first.get(code),
                "reclaim_vwap3": round(_v3, 3),
                "reclaim_vwap5": round(_v5, 3),
                "reclaim_detail": {
                    "vwap3": round(_v3, 3), "vwap5": round(_v5, 3),
                    "vwap": round(event.vwap, 3),
                    "market_pct": event.extra.get("market_pct"),
                    "sector_pct": event.extra.get("sector_pct"),
                    "sector_resonance": event.sector_resonance,
                    "vol_ratio": _pick_float(row.get("ratio"), row.get("vol_ratio"), (snap or {}).get("vol_ratio")),
                    "velocity": event.velocity_pct,
                    "hold_ratio": event.extra.get("vwap_hold_ratio"),
                },
                "quote_timestamp": _pick_float((snap or {}).get("server_ts"), (snap or {}).get("ts"), row.get("server_ts")) or None,
                "sector": sector,
                "lead_label": lead_label,
                "lead_score": round(lead_score, 1),
                "is_leader": bool(event.is_leader),
                "is_structure_prejudged": float(event.extra.get("is_structure_prejudged") or (snap or {}).get("is_structure_prejudged") or 0.0),
                "wash_quality": float(event.extra.get("wash_quality") or (snap or {}).get("wash_quality") or 0.0),
                "prev_strong_vwap": float(event.extra.get("prev_strong_vwap") or (snap or {}).get("prev_strong_vwap") or 0.0),
                "is_prime_leader": 1.0 if _is_prime else 0.0,
                "struct_status": _tl.status,
                "struct_confirm_n": int(_tl.confirm_n),
                "struct_break_n": int(_tl.break_n),
                "struct_reason": _tl.reason,
                "struct": dict(
                    {
                        k_s: round(float(v_s), 3) if isinstance(v_s, (int, float)) else v_s
                        for k_s in ("is_structure_prejudged", "wash_quality", "prev_strong_vwap", "is_prime_leader", "close_over_vwap10", "underwater_depth_pct")
                        for v_s in [event.extra.get(k_s) or (snap or {}).get(k_s)]
                        if v_s
                    },
                    **{
                        "status": _tl.status,
                        "label": STATUS_LABEL.get(_tl.status, _tl.status),
                        "confirm_n": int(_tl.confirm_n),
                        "break_n": int(_tl.break_n),
                        "cushion_roll": round(float(_tl.cushion_roll), 2),
                        "cushion_now": round(float(_tl.cushion_now), 2),
                        "drawdown_pct": round(float(_tl.drawdown_pct), 2),
                        "reason": _tl.reason,
                    },
                ),
                "track": track_dict,
                "legacy": {
                    "action": legacy_action,
                    "reason": str((decision or {}).get("reason") or "")[:120],
                    "vetoed": bool(vetoed),
                    "veto_reason": str(veto_reason or "")[:80],
                },
                "fusion": fusion.to_dict(),
                "divergence": divergence,
                "regime": regime.to_dict() if regime else {},
                "missing": event.extra.get("missing", []),
            }

            with self._lock:
                from ats.fusion.observation import observation_reason
                if observation_reason(record.get("observation_evidence")):
                    self._strategy_observation_days[code] = day
                    self._tracker_dirty = True
                    self._save_tracker_locked()
                self._stats["records"] += 1
                self._stats["tier_counts"][fusion.tier] = (
                    self._stats["tier_counts"].get(fusion.tier, 0) + 1
                )
                self._stats["divergence"][divergence] += 1
                for key in record["missing"]:
                    self._stats["missing"][key] = self._stats["missing"].get(key, 0) + 1

            self._append(record, day)
            return record

        except Exception as exc:
            with self._lock:
                self._stats["errors"] += 1
            logger.debug("[fusion] shadow observe failed %s: %s", code, exc)
            return None

    def _append(self, record: Dict[str, Any], day: str) -> None:
        from ats.fusion.source_identity import is_replay_record
        if is_replay_record(record):
            logger.warning("[fusion] 拒绝回放记录写入生产影子")
            return
        try:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return

        with self._lock:
            try:
                if self._fh is None or self._fh_day != day:
                    self._rotate(day)
                if self._written_today >= self._max_per_day:
                    self._max_records_truncated = True
                    return
                if self._fh is None:
                    self._dropped_write_count += 1
                    return
                self._fh.write(line + "\n")
                self._buf.append(line)
                self._written_today += 1
                now_ts = time.time()
                if len(self._buf) >= 10 or (now_ts - self._last_flush) >= 2.0:
                    self._fh.flush()
                    self._buf.clear()
                    self._last_flush = now_ts
            except Exception as exc:
                self._stats["errors"] += 1
                self._dropped_write_count += 1
                logger.debug("[fusion] 写影子日志失败: %s", exc)

    def _rotate(self, day: str) -> None:
        if self._fh is not None:
            self._fh.close()
        self._fh = None
        self._fh_day = day
        self._written_today = 0
        self._buf.clear()
        from ats.fusion.shadow_writer import open_writer
        self._fh = open_writer(self._log_dir, day)

    def flush(self) -> None:
        with self._lock:
            try:
                if self._fh is not None:
                    self._fh.checkpoint()
                    self._buf.clear()
            except Exception:
                logger.exception("[fusion] 影子 flush 失败")
            self._save_tracker_locked(force=True)

    def close(self) -> None:
        try:
            self.write_checkpoint("EOF_CHECKPOINT")
        except Exception:
            pass
        with self._lock:
            try:
                if self._fh is not None:
                    self._fh.flush()
                    self._fh.close()
            except Exception:
                self._stats["errors"] += 1
                logger.exception("[fusion] 影子退出落盘失败，保留待重试 writer")
            else:
                self._fh = None
            self._save_tracker_locked(force=True)

    def _save_tracker_locked(self, force: bool = False) -> None:
        if not self._tracker_loaded or not self._tracker_dirty:
            return
        now = time.monotonic()
        if not force and now - self._last_tracker_save < self._tracker_save_interval:
            return
        try:
            self.tracker.save(
                self._tracker_state_path,
                metadata={
                    "day": self._day,
                    "counter_reclaim_first": dict(self._counter_reclaim_first),
                    "strategy_observation_days": dict(self._strategy_observation_days),
                },
            )
            self._last_tracker_save = now
            self._tracker_dirty = False
        except Exception as exc:
            self._stats["errors"] += 1
            logger.warning("[fusion] 跟踪状态保存失败: %s", exc)

    def _load_tracker_states(self, asof_day: str) -> int:
        import glob

        pattern = os.path.join(self._log_dir, "tracker_state_live_strategy_*.json")
        paths = set(glob.glob(pattern))
        legacy = os.path.join(self._log_dir, "tracker_state_live_strategy.json")
        if os.path.isfile(legacy):
            paths.add(legacy)
        merged = {}
        if not hasattr(self, "_strategy_observation_days"):
            self._strategy_observation_days = {}
        for path in sorted(paths):
            candidate = RaceTracker()
            metadata: Dict[str, Any] = {}
            try:
                candidate.load(path, asof_day=asof_day, metadata=metadata)
            except Exception as exc:
                logger.warning("[fusion] 跟踪状态文件读取失败 %s: %s", os.path.basename(path), exc)
                continue
            observation_days = metadata.get("strategy_observation_days")
            if isinstance(observation_days, dict) and str(metadata.get("day") or "") <= asof_day:
                from datetime import date
                for code, observed_day in observation_days.items():
                    try:
                        age = (date.fromisoformat(asof_day) - date.fromisoformat(observed_day)).days
                        if 0 <= age <= 9 and len(code) == 6 and code.isdigit():
                            self._strategy_observation_days[code] = max(
                                observed_day, self._strategy_observation_days.get(code, observed_day))
                    except (TypeError, ValueError):
                        continue
            if metadata.get("day") == asof_day:
                first_map = metadata.get("counter_reclaim_first")
                if isinstance(first_map, dict):
                    for code, raw_ts in first_map.items():
                        try:
                            first_ts = float(raw_ts)
                        except (TypeError, ValueError):
                            continue
                        if first_ts <= 0:
                            continue
                        key = str(code).zfill(6)
                        current_ts = self._counter_reclaim_first.get(key)
                        if current_ts is None or first_ts < current_ts:
                            self._counter_reclaim_first[key] = first_ts
            for code, state in candidate._states.items():
                current = merged.get(code)
                if current is None or state.last_ts > current.last_ts:
                    merged[code] = state
        self.tracker._states.update(merged)
        return len(merged)

    def observation_codes(self, asof_day: str):
        from datetime import date
        with self._lock:
            if not self._tracker_loaded:
                self._load_tracker_states(asof_day)
                self._tracker_loaded = True
            return {code for code, observed_day in self._strategy_observation_days.items()
                    if 0 <= (date.fromisoformat(asof_day) - date.fromisoformat(observed_day)).days <= 9}

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            out = json.loads(json.dumps(self._stats))
            out["log_dir"] = self._log_dir
            out["written_today"] = self._written_today
            out["seq_no"] = self._seq_no
            out["session_id"] = self._session_id
            out["dropped_write_count"] = self._dropped_write_count
            out["max_records_truncated"] = self._max_records_truncated
        out["portfolio"] = {
            "total_size_pct": self.bus.total_size_pct(),
            "positions": len(self.bus.portfolio()),
            "l4": sum(1 for d in self.bus.portfolio() if d.get("tier") == 4),
        }
        out["cuts"] = [list(c) for c in self.current_cuts()]
        out["rar_samples"] = len(self._rar_samples)
        return out

    def top(self, n: int = 10) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self.bus.top(n)]

    def step_hot_pool(self, df_all_data: Any, now: float) -> None:
        """驱动梯度热榜持续跟踪（独立观察层，绝不下单，不改既有决策与执行）。"""
        if df_all_data is None or (hasattr(df_all_data, "empty") and df_all_data.empty):
            return
        try:
            day = today_str(now)
            # 1. 跨日重置与盘前种子初始化
            if self._hot_pool_seeded_day != day:
                self._hot_pool_seeded_day = day
                from ats.fusion.hot_pool import HotPoolState, load_previous_day_carry_states
                self.hot_pool = HotPoolState()
                prev_carry = load_previous_day_carry_states(day, self._log_dir)
                if prev_carry:
                    self.hot_pool.carry_from_previous_day(day, prev_carry, carry_ts=now)
                from ats.fusion.context import get_daily_context
                d_ctx = get_daily_context()
                if d_ctx and getattr(d_ctx, "ok", False):
                    all_cds = [str(c).split(".")[0].zfill(6) for c in df_all_data.index]
                    self.hot_pool.seed_from_daily_context(day, all_cds, lambda c, d: d_ctx.asof(c, d), seed_ts=now)

            # 2. 构造快照字典
            quotes_map = {}
            idx_list = df_all_data.index
            c_px = df_all_data["trade"] if "trade" in df_all_data.columns else (df_all_data["price"] if "price" in df_all_data.columns else df_all_data.get("close"))
            c_pct = df_all_data.get("percent") if "percent" in df_all_data.columns else df_all_data.get("pct")
            c_vw = df_all_data.get("vwap")
            c_vol = df_all_data.get("volume")
            c_ratio = df_all_data.get("ratio")
            c_open = df_all_data.get("open")

            for idx_c in idx_list:
                c6 = str(idx_c).split(".")[0].zfill(6)
                try:
                    px = float(c_px.loc[idx_c]) if c_px is not None else 0.0
                    if px <= 0.0:
                        continue
                    pct_val = float(c_pct.loc[idx_c]) if c_pct is not None else 0.0
                    vw_val = float(c_vw.loc[idx_c]) if c_vw is not None else px
                    vol_val = float(c_vol.loc[idx_c]) if c_vol is not None else 0.0
                    r_val = float(c_ratio.loc[idx_c]) if c_ratio is not None else 1.0
                    op_val = float(c_open.loc[idx_c]) if c_open is not None else px
                    quotes_map[c6] = {
                        "price": px,
                        "percent": pct_val,
                        "volume": vol_val,
                        "vwap": vw_val,
                        "ratio": r_val,
                        "open": op_val,
                        "trade": px,
                    }
                except Exception:
                    continue

            if not quotes_map:
                return

            from ats.fusion.context import get_daily_context
            d_ctx = get_daily_context()
            self.hot_pool.step_frame(
                trade_date=day,
                event_ts=now,
                quotes_map=quotes_map,
                daily_ctx_getter=lambda c, d: d_ctx.asof(c, d) if (d_ctx and d_ctx.ok) else {},
                source="live_snapshot",
            )

            # 3. 按间隔（每 5 秒）原子持久化
            if now - self._last_hot_pool_save_ts >= 5.0:
                self._last_hot_pool_save_ts = now
                from ats.fusion.hot_pool import save_hot_pool_state
                save_hot_pool_state(self.hot_pool, self._log_dir)
        except Exception as exc:
            logger.debug("[FusionShadow] step_hot_pool exception: %s", exc)
