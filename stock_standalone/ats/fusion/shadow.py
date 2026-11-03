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
from ats.fusion.regime import MarketRegime, MarketRegimeTracker, RegimeSample
from ats.fusion.structure_timeline import (
    STATUS_BROKEN,
    STATUS_CONFIRMED,
    STATUS_EVICTED,
    STATUS_LABEL,
    STATUS_WAITING,
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

# 自适应分档的绝对下限：防止"整段行情都很烂"时也评出 L4。
# 与回放 percentile_cuts 的 floors 保持一致（68/60/52/45）：
# 补全盘口与分时后，实盘 RAR 量纲已与回放对齐，下限也必须对齐，
# 否则 58 分就能评 L4，梯度会失去区分意义。
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
        # 四舍五入后仍须严格递减，否则相邻档位会被合并
        cut = min(cut, round(prev - 0.1, 1))
        out.append((cut, tier))
        prev = cut
    return tuple(out)


def _pick_float(*values: Any, default: float = 0.0) -> float:
    """按优先级取第一个"有值"的数值。0.0 是合法值（例如悬空垫正好为 0），
    不能用 `a or b` 判断，否则会被后面的负值覆盖。"""
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
        self._prime_leader_by_sector: Dict[str, str] = {}  # sector -> code 板块总龙头唯一性
        self._latent_pool: Dict[str, float] = {}
        self._counter_reclaim_first: Dict[str, float] = {}
        self._launch_vwap_samples: Dict[str, List[tuple]] = {}
        self._launch_vwap_lock = threading.Lock()
        self._regime_provider = regime_provider

        # 结构机会时间轴：让"结构验证"成为可成立/可失守/可恢复的状态，而不是开盘一次性盖章
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
        # 交易时段闸门：默认开启，盘后轮询不再污染当日流水（历史/回放不受影响）
        self._session_gate = bool(self.cfg.get("session_gate", True))
        self._last_sample: Dict[str, float] = {}
        # 策略观察源的"阶梯"闸门：只在状态变化时落一条；已激活标的再按心跳留价格锚点。
        # 旧行为是每轮采样都写，单上午 3.3 万条/222MB，占全部记录量的 91%。
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

        # ---- 自适应分档（当日横截面分位）----
        # 固定绝对阈值（82/72/62/50）是按"回放全量数据"标定的；实盘四轴覆盖不足时
        # RAR 天花板只有 ~60，导致永远评不出 L2~L4。这里改为当日分位自适应，
        # 让梯度真实展开，同时用 coverage 标注"这次结论建立在多少真实数据上"。
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

        if self.enabled:
            try:
                os.makedirs(self._log_dir, exist_ok=True)
                from ats.fusion.shadow_archive import register_archive_worker
                register_archive_worker(self._log_dir)
            except Exception as exc:
                logger.warning("[fusion] 影子日志目录创建失败，降级为仅内存: %s", exc)

    # ------------------------------------------------------------------
    # 自适应分档
    # ------------------------------------------------------------------
    def _refresh_cuts(self) -> None:
        """当日样本足够时，用横截面分位重算 L0~L4 阈值；样本不足则沿用引擎固定阈值。"""
        if self._cuts_mode != "adaptive":
            return
        # 优先按个股去重后的最新横截面分布计算分位，防止 1~2 只高频活跃股污染 p98/p92；
        # 若唯一标的数量尚不足（例如单标的单元测试），自动回退到全样本池。
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
        except Exception as exc:  # 分档失败不能影响主循环
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
        """由主循环注入全市场真实横截面宽度（零 I/O），供 current_regime 融合。"""
        ts = float(now if now is not None else time.time())
        with self._regime_lock:
            self._market_sample = {
                "ts": ts,
                "up_ratio": max(0.0, min(1.0, float(up_ratio))),
                "limit_up": int(limit_up),
                "limit_down": int(limit_down),
                "seal_rate": max(0.0, min(1.0, float(seal_rate))),
            }

    # ------------------------------------------------------------------
    # 温度
    # ------------------------------------------------------------------
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
                # 融合状态机温度与真实盘面涨跌比
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

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
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
            # 交易时段闸门：盘后轮询（如 21:11）仍在评估时，不再往当日流水里写记录，
            # 否则"入局时间/当日 MFE"都会被盘后噪声污染。
            # 只拦"当天"的记录：历史日期（回放、补数）一律放行；force 用于测试与补录。
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
            launch_ts = self.launch.note(code, now, pct, event.price, event.vwap, reset_wave=reset_wave) if "pct" not in event.extra.get("missing", ()) and event.trade_date == day else 0.0
            event.launch_ts = launch_ts
            price, vwap = event.price, event.vwap

            # ---- 异动形态识别与板块排头兵时钟（对齐回放 DayReplay）----
            mkt_ret5 = float(event.extra.get("mkt_ret5") or 0.0)
            prev_pct = 0.0
            ret_std20 = 0.0
            try:
                # K3 数据源对齐：优先读 adapter 注入的 event.extra["prev_pct"] (来自 DailyContext 权威日线)，与回放 100% 同源
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
            # 滚动悬空垫（时间可恢复）：只看最近 20 分钟，价格重新站上均线后会自动回升。
            # 这是"结构不是一锤子买卖"的关键输入，缺失时才回退到全时段最小值。
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
            # 结构资格严格口径（设计文档支柱 2）：只认 is_structure_prejudged。
            # close_over_vwap10 全市场占 37%，仅作诊断字段，不再作为结构候选的兜底资格
            # （实测兜底组 L4 的 MAE 是严格组的 3.5 倍）。
            _prejudged = bool(_is_struct_ready)

            # ---- 结构时间轴：每一根行情都重新判定"结构还在不在" ----
            # WAITING→CONFIRMED（点火）/ CONFIRMED→BROKEN（失守）/ BROKEN→CONFIRMED（重新站回）
            # 反复失守 >= max_break_n 次进入 EVICTED，当日不再给保底，需连续 rearm_bars 次复核才复活。
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

            # 同步写回 event.extra，让引擎与证据链完整读取形态
            event.extra["patterns"] = list(patterns)

            raw_sector = str(
                event.extra.get("sector")
                or (row.get("category") if hasattr(row, "get") else "")
                or ""
            )
            sector = raw_sector.split(";")[0].strip() if raw_sector else ""
            # K2 操盘手优化：总龙头判定（彻底杜绝自证循环、排除跟风、板块唯一）
            prev_strong = bool(
                event.extra.get("prev_strong_vwap")
                or (snap or {}).get("prev_strong_vwap")
                or (row.get("prev_strong_vwap") if hasattr(row, "get") else False)
            )
            today_strong = bool(event.pct > 0 and event.price >= event.vwap * 0.998)

            # 1. 先调用板块时钟获取客观排名 (坚决传 is_prime_leader=False，杜绝自证循环)
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

            # 2. 严密判定总龙头：
            # 昨日倍量突破 + 今日连阳站稳均线 + 客观是排头兵/夺旗/极早启动 (落后<=5分钟) + 坚决排除跟风/冲锋队 + 板块唯一性
            _is_prime = False
            if prev_strong and today_strong:
                is_front = (
                    (raw_lead_label in (LABEL_VANGUARD, LABEL_FLAG) or lead_gap_min <= 5.0)
                    and raw_lead_label not in (LABEL_FOLLOW, "跟风", LABEL_STRIKE, "冲锋队")
                )
                if is_front:
                    if sector:
                        with self._lock:
                            current_prime = self._prime_leader_by_sector.get(sector)
                            if current_prime is None or current_prime == code:
                                self._prime_leader_by_sector[sector] = code
                                _is_prime = True
                    else:
                        _is_prime = True

            if _is_prime:
                event.extra["is_prime_leader"] = True
                event.extra["lead_label"] = LABEL_PRIME
                lead_label = LABEL_PRIME
            else:
                event.extra["is_prime_leader"] = False
                lead_label = raw_lead_label

            lead_score = float(event.extra.get("lead_score") or 0.0)
            # 两类早盘启动证据只作为独立观察，不给形态分加权或抬高梯度。
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
            # 结构失守/剔除后不再给结构保底；只有"此刻仍成立"的结构才配拿 L4 保底
            _struct_blocked = _tl.status in (STATUS_BROKEN, STATUS_EVICTED)
            _floor: Optional[int] = None
            if (PATTERN_BOX10_VWAP_HOVER in patterns or PATTERN_STRUCTURE_CONFIRM in patterns) and not _struct_blocked:
                _floor = 4
                if PATTERN_STRUCTURE_CONFIRM in patterns:
                    event.extra["structure_confirmed"] = True
            elif _is_prime:
                _floor = 4
            elif _ps >= 100 or (event.is_leader and _ps >= 70):
                _floor = 3
            elif _ps >= 70 or (lead_label in (LABEL_VANGUARD, LABEL_FLAG) and patterns):
                _floor = 2

            regime = self.current_regime(now)
            with self._lock:
                self._refresh_cuts()
                active_cuts = self._cuts

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
                    # 仅查询新近可行动信号；历史平仓不改变当前梯度/价格或风险门禁。
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

            track_dict: Dict[str, Any] = {}
            with self._lock:
                self._rar_samples.append(float(fusion.rar))
                if len(self._rar_samples) > 4000:
                    del self._rar_samples[:1000]
                if code:
                    self._latest_rar_by_code[code] = float(fusion.rar)
                self.bus.update(event, regime)
                if now - self._last_rebalance >= 60.0:
                    try:
                        self.bus.rebalance()
                        self._last_rebalance = now
                    except Exception:
                        pass
                try:
                    if (self._tracks_source(source)
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

            # 注意：保持 (snap or {}).get("name") 直接调用，使异常隔离单测 Boom() 可精确触发
            snap_name = str((snap or {}).get("name") or "")

            # 策略观察是"过程类"记录：阶梯的每一级都要留，但同一个状态不再重复写。
            # 口径：
            #   1) 结构状态 / 确认次数 / 级别 / 观察结论 任一变化 -> 立刻落一条（阶梯步点）
            #   2) 状态没变 -> 只有"曾经激活"的标的按心跳留价格锚点（保证入局后 MFE/MAE 连续）
            #   3) 从未激活且状态未变的票 -> 不落盘（它们的价格序列没有下游用途）
            if source == "strategy_observation":
                from ats.fusion.observation import observation_reason
                reason = observation_reason(event.extra.get("observation_evidence"))
                state_key = (
                    str(getattr(_tl, "status", "") or ""),
                    int(getattr(_tl, "confirm_n", 0) or 0),
                    int(fusion.tier),
                    reason,
                    launch_signal.get("type", ""),
                    launch_signal.get("status", ""),
                    launch_signal.get("permission", ""),
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

            record = {
                # 记录结构版本：2 = 含 price/pct/vwap/hit/coverage。
                # 界面据此判断"写盘进程是不是新版本"，旧版本写的记录会缺字段。
                "schema": 2,
                # 写入方身份：排查"窗口是新的、数据是旧的"时，一眼看出是哪个进程在写。
                "writer_pid": os.getpid(),
                "writer_exe": os.path.basename(sys.executable or ""),
                "ts": round(now, 3),
                "day": day,
                "code": code,
                "name": name or snap_name,
                "source": source,
                # 行情快照：界面"现价/涨幅/更新时间"直接读这三个字段。
                # 旧实现只落 fusion 结论，不落行情，导致监视器全部显示 "-" 与 +0.00%。
                "price": round(float(price or 0.0), 3),
                "pct": round(float(pct), 3) if "pct" not in event.extra.get("missing", ()) else None,
                "pct_source": event.extra.get("pct_source"),
                "reported_pct": event.extra.get("reported_pct"),
                "quote_prev_close": event.extra.get("quote_prev_close"),
                "vwap": round(float(vwap or 0.0), 3),
                "trade_date": event.trade_date,
                "hit": bool(fusion.tier >= 2),
                "coverage": round(float(getattr(fusion, "coverage", 0.0) or 0.0), 3),
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
                # 结构时间轴状态（顶层冗余一份，UI 与复盘脚本可直接读，不必再钻 struct 字典）
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

    # ------------------------------------------------------------------
    # 落盘
    # ------------------------------------------------------------------
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
                    return
                if self._fh is None:
                    return
                self._fh.write(line + "\n")
                self._buf.append(line)
                self._written_today += 1
                # 时间驱动 flush：旧实现每 10 行才刷一次，低频标的的记录会长时间停在
                # 缓冲区里，进程被强杀就永久丢失（表现为"上午的梯度没有持久化"）。
                now_ts = time.time()
                if len(self._buf) >= 10 or (now_ts - self._last_flush) >= 2.0:
                    self._fh.flush()
                    self._buf.clear()
                    self._last_flush = now_ts
            except Exception as exc:
                self._stats["errors"] += 1
                logger.debug("[fusion] 写影子日志失败: %s", exc)

    def _rotate(self, day: str) -> None:
        if self._fh is not None:
            # 检查点失败时保留旧 writer 及待落盘记录，由后台重试。
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
        """合并本生产角色各进程的状态；对同一代码采用最新 last_ts。"""
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

    def observation_codes(self, asof_day):
        """恢复最近九个日历日的观察名单，独立于是否曾经入局。"""
        from datetime import date
        with self._lock:
            if not self._tracker_loaded:
                self._load_tracker_states(asof_day)
                self._tracker_loaded = True
            return {code for code, observed_day in self._strategy_observation_days.items()
                    if 0 <= (date.fromisoformat(asof_day) - date.fromisoformat(observed_day)).days <= 9}

    # ------------------------------------------------------------------
    # 观测
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            out = json.loads(json.dumps(self._stats))
            out["log_dir"] = self._log_dir
            out["written_today"] = self._written_today
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
