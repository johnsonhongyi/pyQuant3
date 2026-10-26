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

from ats.fusion.adapter import LaunchTracker, build_event, today_str
from ats.fusion.config import engine_params, load_config
from ats.fusion.engine import FusionBus, FusionEngine
from ats.fusion.regime import MarketRegime, MarketRegimeTracker, RegimeSample

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
        self._regime_provider = regime_provider

        self._lock = threading.Lock()
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
        n = len(self._rar_samples)
        if n < self._cuts_min_samples:
            return
        if self._cuts is not None and (n - self._last_cut_n) < 20:
            return
        try:
            self._cuts = adaptive_cuts(self._rar_samples, self._cuts_floors)
            self._last_cut_n = n
        except Exception as exc:  # 分档失败不能影响主循环
            logger.debug("[fusion] adaptive cuts failed: %s", exc)

    def current_cuts(self) -> tuple:
        return tuple(self._cuts) if self._cuts else tuple(self.engine.cuts)

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
        # 用状态温度喂状态机，主要为了拿到斜率与翻转态；
        # P2 应替换为真实分钟级横截面（涨停/跌停/封板率/上涨家数）。
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
    ) -> Optional[Dict[str, Any]]:
        """记录一条影子决策。返回落盘记录（未落盘返回 None）。永不抛异常。"""
        if not self.enabled:
            return None
        now = float(now if now is not None else time.time())
        code = str(code or "")

        try:
            day = today_str(now)
            if day != self._day:
                self._day = day
                self.launch.reset()
                self._last_sample.clear()
                self._rar_samples.clear()
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

            launch_ts = self.launch.note(code, now, pct, price, vwap)
            event = build_event(
                row=row,
                snap=snap,
                code=code,
                source=source,
                now=now,
                launch_ts=launch_ts,
                trade_date=day,
            )
            regime = self.current_regime(now)
            self._refresh_cuts()
            fusion = self.engine.evaluate(event, regime, now=now, cuts=self._cuts)
            self._rar_samples.append(float(fusion.rar))
            if len(self._rar_samples) > 4000:
                del self._rar_samples[:1000]
            self.bus.update(event, regime)
            if now - self._last_rebalance >= 60.0:
                try:
                    self.bus.rebalance()
                    self._last_rebalance = now
                except Exception:
                    pass

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
                "name": name or str((snap or {}).get("name") or ""),
                "source": source,
                # 行情快照：界面"现价/涨幅/更新时间"直接读这三个字段。
                # 旧实现只落 fusion 结论，不落行情，导致监视器全部显示 "-" 与 +0.00%。
                "price": round(float(price or 0.0), 3),
                "pct": round(float(pct or 0.0), 3),
                "vwap": round(float(vwap or 0.0), 3),
                "trade_date": day,
                "hit": bool(fusion.tier >= 2),
                "coverage": round(float(getattr(fusion, "coverage", 0.0) or 0.0), 3),
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
