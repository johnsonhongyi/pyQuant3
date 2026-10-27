# -*- coding: utf-8 -*-
"""ats/fusion/shadow.py — 影子观察器（P1）。

职责边界（很重要）：
    - 只读。不改 decision、不改 snap、不下单、不发语音。
    - 唯一的副作用是往 logs/fusion_shadow/YYYY-MM-DD.jsonl 追加一行。
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
from ats.fusion.anomaly import PATTERN_LATENT_BREAK, detect_patterns, pattern_score
from ats.fusion.config import engine_params, load_config
from ats.fusion.engine import FusionBus, FusionEngine
from ats.fusion.regime import MarketRegime, MarketRegimeTracker, RegimeSample
from ats.fusion.tracker import RaceTracker
from ats.fusion.vanguard import LABEL_FLAG, LABEL_VANGUARD, SectorClock

logger = logging.getLogger(__name__)

_BUY_ACTIONS = ("买入", "加仓", "BUY", "ADD")

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


def _app_root() -> str:
    try:
        from sys_utils import get_app_root  # type: ignore

        return get_app_root()
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FusionShadow:
    """影子观察器。线程安全，失败静默。"""

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
        self.sector_clock = SectorClock()
        self._latent_pool: Dict[str, float] = {}
        self._regime_provider = regime_provider

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
        self._max_per_day = int(self.cfg.get("max_records_per_day", 200000))
        self._sample_interval = float(self.cfg.get("sample_interval_s", 3.0))
        # 交易时段闸门：默认开启，盘后轮询不再污染当日流水（历史/回放不受影响）
        self._session_gate = bool(self.cfg.get("session_gate", True))
        self._last_sample: Dict[str, float] = {}

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
                        self._latent_pool.clear()
                        self._last_sample.clear()
                        self._rar_samples.clear()
                        self._latest_rar_by_code.clear()
                        self._cuts = None
                        self._last_cut_n = 0

                last = self._last_sample.get(code, 0.0)
                if now - last < self._sample_interval:
                    self._stats["skipped_interval"] += 1
                    return None
                self._last_sample[code] = now

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

            launch_ts = self.launch.note(code, now, pct, price, vwap, reset_wave=reset_wave)
            event = build_event(
                row=row,
                snap=snap,
                code=code,
                source=source,
                now=now,
                launch_ts=launch_ts,
                trade_date=day,
            )

            # ---- 异动形态识别与板块排头兵时钟（对齐回放 DayReplay）----
            mkt_ret5 = float(event.extra.get("mkt_ret5") or 0.0)
            prev_pct = 0.0
            ret_std20 = 0.0
            try:
                prev_pct = float(row.get("per1d") or (snap or {}).get("prev_pct") or 0.0)
                ret_std20 = float(row.get("ret_std20") or (snap or {}).get("ret_std20") or 0.0)
            except Exception:
                prev_pct = 0.0
                ret_std20 = 0.0
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
                )
            )
            if reset_wave and PATTERN_LATENT_BREAK not in patterns:
                patterns.append(PATTERN_LATENT_BREAK)

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

            raw_sector = str(
                event.extra.get("sector")
                or (row.get("category") if hasattr(row, "get") else "")
                or ""
            )
            sector = raw_sector.split(";")[0].strip() if raw_sector else ""
            if sector and "lead_score" not in event.extra:
                with self._lock:
                    _lead = self.sector_clock.observe(
                        code=code,
                        sector=sector,
                        ts=now,
                        pct=event.pct,
                        breakout=bool(patterns),
                    )
                ld_dict = _lead.to_dict()
                ld_dict["lead_label"] = _lead.label
                event.extra.update(ld_dict)

            lead_label = str(event.extra.get("lead_label") or event.extra.get("label") or "")
            lead_score = float(event.extra.get("lead_score") or 0.0)
            _ps = pattern_score(patterns)
            _floor: Optional[int] = None
            if _ps >= 100 or (event.is_leader and _ps >= 70):
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
                    _st = self.tracker.update(
                        code=code,
                        ts=now,
                        price=event.price,
                        pct=event.pct,
                        vwap10=event.vwap_10d,
                        vwap=event.vwap,
                        vol_ratio=event.vol_ratio,
                        tier=fusion.tier,
                        rar=fusion.rar,
                        patterns=patterns,
                        day=day,
                        anomaly=bool(patterns) or fusion.tier >= 2,
                        consensus=float(event.extra.get("consensus") or 0.5),
                        temp=regime.temp if regime else 50.0,
                        lead_label=lead_label,
                        lead_score=lead_score,
                    )
                    track_dict = _st.to_dict()
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
                "pct": round(float(pct or 0.0), 3),
                "vwap": round(float(vwap or 0.0), 3),
                "trade_date": day,
                "hit": bool(fusion.tier >= 2),
                "coverage": round(float(getattr(fusion, "coverage", 0.0) or 0.0), 3),
                "patterns": patterns,
                "sector": sector,
                "lead_label": lead_label,
                "lead_score": round(lead_score, 1),
                "is_leader": bool(event.is_leader),
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
        if self._written_today >= self._max_per_day:
            return
        try:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return

        with self._lock:
            try:
                if self._fh is None or self._fh_day != day:
                    self._rotate(day)
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
        try:
            if self._fh is not None:
                self._fh.flush()
                self._fh.close()
        except Exception:
            pass
        self._fh = None
        self._fh_day = day
        self._written_today = 0
        self._buf.clear()
        path = os.path.join(self._log_dir, "{}.jsonl".format(day))
        self._fh = open(path, "a", encoding="utf-8")

    def flush(self) -> None:
        with self._lock:
            try:
                if self._fh is not None:
                    self._fh.flush()
                    self._buf.clear()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            try:
                if self._fh is not None:
                    self._fh.flush()
                    self._fh.close()
            except Exception:
                pass
            self._fh = None

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
