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
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ats.fusion.adapter import LaunchTracker, build_event, today_str
from ats.fusion.config import engine_params, load_config
from ats.fusion.engine import FusionBus, FusionEngine
from ats.fusion.regime import MarketRegime, MarketRegimeTracker, RegimeSample

logger = logging.getLogger(__name__)

_BUY_ACTIONS = ("买入", "加仓", "BUY", "ADD")


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

        self._regime: Optional[MarketRegime] = None
        self._regime_ts = 0.0
        self._day = ""
        self._last_rebalance = 0.0

        if self.enabled:
            try:
                os.makedirs(self._log_dir, exist_ok=True)
            except Exception as exc:
                logger.warning("[fusion] 影子日志目录创建失败，降级为仅内存: %s", exc)

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
            fusion = self.engine.evaluate(event, regime, now=now)
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
                "ts": round(now, 3),
                "day": day,
                "code": code,
                "name": name or str((snap or {}).get("name") or ""),
                "source": source,
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
                if len(self._buf) >= 10:
                    self._fh.flush()
                    self._buf.clear()
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
        return out

    def top(self, n: int = 10) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self.bus.top(n)]
