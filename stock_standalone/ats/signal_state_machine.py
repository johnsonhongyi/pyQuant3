# -*- coding: utf-8 -*-
"""
ats/signal_state_machine.py
===========================
时序信号引擎 —— L2 状态机与持仓账本层

设计要点（对应 docs/tasks/2026-10-20_2045_ATS时序可交易信号引擎落地方案.md §6）：

1. **状态有记忆**：每次 ``step`` 都是"从某状态迁移到某状态"，而不是"每帧重算一个标签"。
2. **单调前进**：``ACCEL`` / ``TRAILING`` 不可回退到低级状态，只能走 ``EXITING``。
3. **确认 bar**：条件须连续 ``confirm_bars`` 根 bar 成立，过滤单帧假突破。
4. **最短驻留**：除硬止损外，状态须驻留 ``min_dwell_bars`` 才允许离开，防抖动。
5. **每 bar 一次**：同一 ``bar_id`` 重复调用只刷新持仓浮盈浮亏，不重复判决，保证幂等。
6. **事件可复盘**：每次迁移落一条 ``TransitionEvent``，含 bar、价、因、证据。
7. **MFE 用进场后极值**：不受进场前高点污染。

本模块纯计算、无 IO、无线程、无 Qt 依赖，可独立单测。
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple

from ats.signal_timeline import Structure

__all__ = [
    "SignalState",
    "STATE_LEVEL",
    "STATE_LABELS",
    "EXIT_REASON_LABELS",
    "SignalContext",
    "SignalParams",
    "TransitionEvent",
    "Position",
    "SignalStateMachine",
    "PositionLedger",
    "WeakStrongRanker",
]


# ---------------------------------------------------------------------------
# 状态定义
# ---------------------------------------------------------------------------
class SignalState(str, Enum):
    DORMANT = "DORMANT"        # 盘前合格，盘中未动
    ARMED = "ARMED"            # 逼近触发线，结构未坏
    TRIGGERED = "TRIGGERED"    # 触发进场（事件产生当 bar）
    HOLDING = "HOLDING"        # 持仓跟单
    TRAILING = "TRAILING"      # 浮盈达标，移动止盈
    ACCEL = "ACCEL"            # 加速锁定
    EXITING = "EXITING"        # 退场待确认（软退场）
    EXITED = "EXITED"          # 已退场


STATE_LEVEL: Dict[str, int] = {
    SignalState.DORMANT.value: 0,
    SignalState.ARMED.value: 1,
    SignalState.TRIGGERED.value: 2,
    SignalState.HOLDING.value: 3,
    SignalState.TRAILING.value: 4,
    SignalState.ACCEL.value: 5,
    SignalState.EXITING.value: 6,
    SignalState.EXITED.value: 7,
}

STATE_LABELS: Dict[str, str] = {
    SignalState.DORMANT.value: "💤 静默待机",
    SignalState.ARMED.value: "🎯 逼近触发",
    SignalState.TRIGGERED.value: "🚀 触发进场",
    SignalState.HOLDING.value: "📌 持仓跟单",
    SignalState.TRAILING.value: "🛡️ 移动止盈",
    SignalState.ACCEL.value: "👑 加速锁定",
    SignalState.EXITING.value: "🚪 退场确认中",
    SignalState.EXITED.value: "✅ 已退场",
}

# 退场原因码 -> 文案（P3 概率化时按此分组统计胜率）
EXIT_REASON_LABELS: Dict[str, str] = {
    "STOP_LOSS": "⛔ 硬止损",
    "ACCEL_STOP": "⛔ 加速后止损",
    "TRAIL_STOP": "🛡️ 移动止盈回撤",
    "STRUCT_BREAK": "↘ 结构破位(高降低降)",
    "TIME_STOP": "⏱ 时间止损(超预算无进展)",
    "TEMP_EBB": "🌊 市场退潮",
    "ORPHAN_RECONCILE": "🧹 孤儿仓位对账清理",
}

_ACTIVE_STATES = {
    SignalState.TRIGGERED.value,
    SignalState.HOLDING.value,
    SignalState.TRAILING.value,
    SignalState.ACCEL.value,
    SignalState.EXITING.value,
}

# 只有"活跃状态"之间的迁移才受最短驻留约束，避免把开仓/退场完成也拖慢
_DWELL_SCOPE = {
    SignalState.ARMED.value,
    SignalState.TRIGGERED.value,
    SignalState.HOLDING.value,
    SignalState.TRAILING.value,
    SignalState.ACCEL.value,
}

_DWELL_EXEMPT_REASONS = {
    "STOP_LOSS", "ACCEL_STOP", "TRAIL_STOP",
    "POSITION_OPEN", "EXIT_DONE",
}


# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------
@dataclass
class SignalParams:
    """信号参数。全部可由 CCT 覆盖；``derive_for`` 支持按个股波动预算自适应。"""

    bar_seconds: int = 15
    confirm_bars: int = 2
    min_dwell_bars: int = 2
    arm_dist_pct: float = 1.2
    trail_start_pct: float = 2.5
    trail_gap_pct: float = 1.2
    max_hold_bars: int = 80
    min_progress_pct: float = 1.0
    cooldown_bars: int = 8
    max_positions: int = 8
    shadow_mode: bool = True

    # 触发阈值（可由 derive_for 按波动预算重算）
    trigger_pct_thresh: float = 1.6
    trigger_vol_thresh: float = 1.15
    accel_pct_thresh: float = 5.5
    min_alpha_pct: float = 0.0
    above_ratio_need: float = 0.5
    arm_confirm_bars: int = 2
    # 跳空直通：开盘即站上触发线时允许 DORMANT -> TRIGGERED，但追高幅度受此限制
    gap_max_pct: float = 3.0
    # ARMED 僵死阈值：距触发线超过 arm_dist_pct 的该倍数则退回 DORMANT
    arm_stale_multiple: float = 3.0

    @classmethod
    def from_cct(cls) -> "SignalParams":
        """从 CCT 读取；任何异常都退回安全默认，绝不因配置缺失阻断信号。"""
        p = cls()
        try:
            from JohnsonUtil import commonTips as cct
        except Exception:
            return p

        def _get(name: str, default: Any, cast=float):
            try:
                val = getattr(cct, name, default)
                return default if val is None else cast(val)
            except Exception:
                return default

        p.bar_seconds = _get("ats_signal_bar_seconds", p.bar_seconds, int)
        p.confirm_bars = _get("ats_signal_confirm_bars", p.confirm_bars, int)
        p.min_dwell_bars = _get("ats_signal_min_dwell_bars", p.min_dwell_bars, int)
        p.arm_dist_pct = _get("ats_signal_arm_dist_pct", p.arm_dist_pct, float)
        p.trail_start_pct = _get("ats_signal_trail_start_pct", p.trail_start_pct, float)
        p.trail_gap_pct = _get("ats_signal_trail_gap_pct", p.trail_gap_pct, float)
        p.max_hold_bars = _get("ats_signal_max_hold_bars", p.max_hold_bars, int)
        p.min_progress_pct = _get("ats_signal_min_progress_pct", p.min_progress_pct, float)
        p.cooldown_bars = _get("ats_signal_cooldown_bars", p.cooldown_bars, int)
        p.max_positions = _get("ats_signal_max_positions", p.max_positions, int)
        p.shadow_mode = bool(_get("ats_signal_shadow_mode", p.shadow_mode, bool))
        p.gap_max_pct = _get("ats_signal_gap_max_pct", p.gap_max_pct, float)
        p.arm_stale_multiple = _get("ats_signal_arm_stale_multiple", p.arm_stale_multiple, float)
        return p

    def derive_for(self, vol_budget_pct: float, board_limit_pct: float = 10.0) -> "SignalParams":
        """按个股波动预算派生自适应阈值（方案 §7.2）。

        - 低波股放宽量能要求、收紧涨幅要求，避免"永远触发不了"；
        - 高波股抬高涨幅要求，避免"一根影线就触发"。
        """
        vb = float(vol_budget_pct or 0.0)
        if vb <= 0.0:
            return self
        out = SignalParams(**{**self.__dict__})
        out.trigger_pct_thresh = round(max(0.8, 0.55 * vb), 2)
        # 波动越小，越需要量能确认；波动越大，量能门槛可略降
        out.trigger_vol_thresh = round(max(1.05, 1.15 + 0.25 * (1.0 - vb / 4.0)), 2)
        out.accel_pct_thresh = round(max(2.5, board_limit_pct * 0.55), 2)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


# ---------------------------------------------------------------------------
# 单 bar 观测上下文
# ---------------------------------------------------------------------------
@dataclass
class SignalContext:
    """一根 bar 的全部判决依据。由 L1 轨迹层与盘前身份层组装。"""

    code: str
    bar_id: int
    ts: float
    price: float
    pct: float
    high: float = 0.0
    low: float = 0.0
    vwap: float = 0.0
    market_temp: float = 50.0
    trigger_line: float = 0.0
    defend_line: float = 0.0
    structure: Structure = Structure.RANGE
    slope_3: float = 0.0
    slope_12: float = 0.0
    vol_confirm: float = 1.0
    alpha_today: float = 0.0
    above_ratio: float = 0.0
    tradable: bool = True
    untradable_reason: str = ""
    temp_regime: str = ""

    @property
    def struct_value(self) -> str:
        return self.structure.value if isinstance(self.structure, Structure) else str(self.structure)


# ---------------------------------------------------------------------------
# 事件
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TransitionEvent:
    """状态迁移事件 —— 唯一可复盘的时序凭据。"""

    code: str
    from_state: str
    to_state: str
    bar_id: int
    ts: float
    price: float
    pct: float
    market_temp: float
    reason_code: str
    reason_text: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "from_label": STATE_LABELS.get(self.from_state, self.from_state),
            "to_label": STATE_LABELS.get(self.to_state, self.to_state),
            "bar_id": self.bar_id,
            "ts": self.ts,
            "time_str": time.strftime("%H:%M:%S", time.localtime(self.ts)) if self.ts else "--:--:--",
            "price": round(float(self.price), 3),
            "pct": round(float(self.pct), 2),
            "market_temp": round(float(self.market_temp), 1),
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "evidence": dict(self.evidence),
        }


# ---------------------------------------------------------------------------
# 持仓
# ---------------------------------------------------------------------------
@dataclass
class Position:
    code: str
    entry_bar: int
    entry_ts: float
    entry_price: float
    entry_pct: float
    entry_temp: float
    entry_reason: str
    stop_price: float = 0.0
    target_price: float = 0.0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    max_bar: int = -1
    adds: List[Dict[str, Any]] = field(default_factory=list)
    trims: List[Dict[str, Any]] = field(default_factory=list)
    last_bar: int = -1
    last_price: float = 0.0
    exit_bar: int = -1
    exit_ts: float = 0.0
    exit_price: float = 0.0
    exit_reason: str = ""
    realized_pct: float = 0.0
    # 分段加权收益：按 trims 的减仓价与剩余仓位的平仓价加权，口径与实盘一致
    realized_pct_weighted: float = 0.0
    peak_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.exit_bar < 0

    @property
    def holding_bars(self) -> int:
        end = self.exit_bar if self.exit_bar >= 0 else self.last_bar
        return max(0, end - self.entry_bar)

    @property
    def holding_seconds(self) -> float:
        end = self.exit_ts if self.exit_ts > 0 else time.time()
        return max(0.0, end - self.entry_ts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "entry_bar": self.entry_bar,
            "entry_time": time.strftime("%H:%M:%S", time.localtime(self.entry_ts)) if self.entry_ts else "--:--:--",
            "entry_price": round(self.entry_price, 3),
            "entry_pct": round(self.entry_pct, 2),
            "entry_temp": round(self.entry_temp, 1),
            "entry_reason": self.entry_reason,
            "stop_price": round(self.stop_price, 3),
            "target_price": round(self.target_price, 3),
            "mfe_pct": round(self.mfe_pct, 2),
            "mae_pct": round(self.mae_pct, 2),
            "max_bar": self.max_bar,
            "holding_bars": self.holding_bars,
            "last_price": round(self.last_price, 3),
            "exit_bar": self.exit_bar,
            "exit_price": round(self.exit_price, 3),
            "exit_reason": self.exit_reason,
            "exit_reason_label": EXIT_REASON_LABELS.get(self.exit_reason, self.exit_reason),
            "realized_pct": round(self.realized_pct, 2),
            "realized_pct_weighted": round(self.realized_pct_weighted, 2),
            "is_open": self.is_open,
            "n_adds": len(self.adds),
            "n_trims": len(self.trims),
        }


def _weighted_realized(pos: Position) -> float:
    """按减仓明细 + 剩余仓位加权计算真实收益率（%）。

    修正口径：``realized_pct`` 是"全仓单一平仓价"，若中途减过仓会失真；
    本函数按每笔减仓的比例与价格、以及剩余仓位的平仓价分段加权。
    """
    if pos.entry_price <= 0:
        return 0.0
    trimmed = 0.0
    acc = 0.0
    for t in pos.trims:
        try:
            frac = float(t.get("fraction", 0.0) or 0.0)
            px = float(t.get("price", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        frac = max(0.0, min(1.0, frac))
        if frac <= 0.0 or px <= 0.0:
            continue
        trimmed += frac
        acc += frac * (px / pos.entry_price - 1.0) * 100.0
    remaining = max(0.0, 1.0 - trimmed)
    if remaining > 0.0 and pos.exit_price > 0:
        acc += remaining * (pos.exit_price / pos.entry_price - 1.0) * 100.0
    return acc


class PositionLedger:
    """持仓账本 —— 让"去弱留强"成为跨时比较，而非帧内排序。"""

    __slots__ = ("max_positions", "_open", "_closed", "_max_closed")

    def __init__(self, max_positions: int = 8, max_closed: int = 500):
        self.max_positions = max(1, int(max_positions or 8))
        self._open: Dict[str, Position] = {}
        self._closed: Deque[Position] = deque(maxlen=max(32, int(max_closed)))

    # -- 查询 ---------------------------------------------------------------
    def can_open(self) -> bool:
        return len(self._open) < self.max_positions

    def is_open(self, code: str) -> bool:
        return str(code).strip() in self._open

    def get(self, code: str) -> Optional[Position]:
        return self._open.get(str(code).strip())

    def open_positions(self) -> List[Position]:
        return list(self._open.values())

    def closed_positions(self) -> List[Position]:
        return list(self._closed)

    # -- 变更 ---------------------------------------------------------------
    def open(self, code: str, ctx: SignalContext, reason: str,
             stop_price: float = 0.0, target_price: float = 0.0) -> Optional[Position]:
        """开仓。``code`` 必须显式传入（不得从 ctx 取键），
        否则会与 ``trim/close`` 使用的 machine.code 不一致，造成持仓泄漏。"""
        code = str(code).strip()
        if not code or code in self._open or not self.can_open():
            return None
        pos = Position(
            code=code,
            entry_bar=int(ctx.bar_id),
            entry_ts=float(ctx.ts),
            entry_price=float(ctx.price),
            entry_pct=float(ctx.pct),
            entry_temp=float(ctx.market_temp),
            entry_reason=reason,
            stop_price=float(stop_price or 0.0),
            target_price=float(target_price or 0.0),
            last_bar=int(ctx.bar_id),
            last_price=float(ctx.price),
            peak_price=float(ctx.price),
        )
        # 进场当 bar 自身的极值即计入 MFE/MAE（不再包含进场前高点）
        hi = float(ctx.high or ctx.price)
        lo = float(ctx.low or ctx.price)
        if hi > 0 and pos.entry_price > 0:
            pos.mfe_pct = max(0.0, (hi - pos.entry_price) / pos.entry_price * 100.0)
            pos.mae_pct = min(0.0, (lo - pos.entry_price) / pos.entry_price * 100.0)
            pos.peak_price = max(pos.entry_price, hi)
            pos.max_bar = int(ctx.bar_id) if pos.mfe_pct > 0 else -1
        self._open[code] = pos
        return pos

    def mark(self, ctx: SignalContext) -> None:
        """按 bar 极值刷新浮盈浮亏（幂等，可重复调用）。"""
        pos = self._open.get(str(ctx.code).strip())
        if pos is None:
            return
        hi = float(ctx.high or ctx.price)
        lo = float(ctx.low or ctx.price)
        if pos.entry_price <= 0:
            return
        if hi > 0:
            mfe = (hi - pos.entry_price) / pos.entry_price * 100.0
            if mfe > pos.mfe_pct:
                pos.mfe_pct = mfe
                pos.max_bar = int(ctx.bar_id)
            if hi > pos.peak_price:
                pos.peak_price = hi
        if lo > 0:
            mae = (lo - pos.entry_price) / pos.entry_price * 100.0
            if mae < pos.mae_pct:
                pos.mae_pct = mae
        pos.last_bar = int(ctx.bar_id)
        pos.last_price = float(ctx.price)

    def add(self, code: str, ctx: SignalContext, reason: str) -> bool:
        pos = self._open.get(str(code).strip())
        if pos is None:
            return False
        pos.adds.append({
            "bar_id": int(ctx.bar_id), "ts": float(ctx.ts),
            "price": round(float(ctx.price), 3), "reason": reason,
        })
        return True

    def trim(self, code: str, ctx: SignalContext, fraction: float, reason: str) -> bool:
        pos = self._open.get(str(code).strip())
        if pos is None:
            return False
        pos.trims.append({
            "bar_id": int(ctx.bar_id), "ts": float(ctx.ts),
            "price": round(float(ctx.price), 3),
            "fraction": round(float(fraction), 3), "reason": reason,
        })
        return True

    def close(self, code: str, ctx: SignalContext, reason: str) -> Optional[Position]:
        c = str(code).strip()
        pos = self._open.pop(c, None)
        if pos is None:
            return None
        pos.exit_bar = int(ctx.bar_id)
        pos.exit_ts = float(ctx.ts)
        pos.exit_price = float(ctx.price)
        pos.exit_reason = reason
        pos.last_bar = int(ctx.bar_id)
        pos.last_price = float(ctx.price)
        if pos.entry_price > 0:
            pos.realized_pct = (pos.exit_price - pos.entry_price) / pos.entry_price * 100.0
            pos.realized_pct_weighted = _weighted_realized(pos)
        self._closed.append(pos)
        return pos

    def reconcile(self, active_codes) -> List[str]:
        """对账：清掉不属于任何活跃机器的仓位，返回被清掉的代码。

        兜底持仓泄漏（键不一致、上游拼装错误），避免孤儿仓位永久占用名额、
        把系统伪装成"仓位已满"。
        """
        active = {str(c).strip() for c in (active_codes or ())}
        orphans = [c for c in list(self._open.keys()) if c not in active]
        for c in orphans:
            pos = self._open.pop(c)
            pos.exit_bar = pos.last_bar
            pos.exit_ts = time.time()
            pos.exit_price = pos.last_price
            pos.exit_reason = "ORPHAN_RECONCILE"
            if pos.entry_price > 0 and pos.last_price > 0:
                pos.realized_pct = (pos.last_price / pos.entry_price - 1.0) * 100.0
                pos.realized_pct_weighted = _weighted_realized(pos)
            self._closed.append(pos)
        return orphans

    def summary(self) -> Dict[str, Any]:
        closed = list(self._closed)
        wins = [p for p in closed if p.realized_pct_weighted > 0]
        return {
            "n_open": len(self._open),
            "n_closed": len(closed),
            "win_rate": round(len(wins) / len(closed) * 100.0, 1) if closed else 0.0,
            "avg_realized_pct": round(
                sum(p.realized_pct_weighted for p in closed) / len(closed), 2
            ) if closed else 0.0,
            "avg_holding_bars": round(
                sum(p.holding_bars for p in closed) / len(closed), 1
            ) if closed else 0.0,
            "open": [p.to_dict() for p in self._open.values()],
            "closed_recent": [p.to_dict() for p in closed[-20:]],
        }


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------
class SignalStateMachine:
    """单只股票的时序状态机。每根 bar 调用一次 ``step``。"""

    __slots__ = (
        "code", "params", "state", "bars_in_state", "last_bar", "last_ctx",
        "_streaks", "_events", "_diagnostics", "_position", "_last_exit_bar",
        "_entry_bar", "_trim_done", "_event_max", "_ledger", "_exit_reason",
    )

    def __init__(self, code: str, params: Optional[SignalParams] = None,
                 ledger: Optional[PositionLedger] = None, event_max: int = 200):
        self.code = str(code).strip()
        self.params = params or SignalParams()
        self.state: str = SignalState.DORMANT.value
        self.bars_in_state: int = 0
        self.last_bar: int = -1
        self.last_ctx: Optional[SignalContext] = None
        self._streaks: Dict[str, int] = {}
        self._events: Deque[TransitionEvent] = deque(maxlen=max(16, int(event_max)))
        self._diagnostics: Deque[Dict[str, Any]] = deque(maxlen=200)
        self._position: Optional[Position] = None
        # 账本必选：没有账本就无法记录持仓与止损位，状态机会"只进不出"卡在 HOLDING。
        # 传 None 时自动建一个独立账本，宁可容量独立也不要退化成无止损。
        self._ledger = ledger if ledger is not None else PositionLedger(
            getattr(self.params, "max_positions", 8)
        )
        self._last_exit_bar: int = -9999
        self._entry_bar: int = -1
        self._trim_done: bool = False
        self._event_max = event_max
        self._exit_reason: str = ""

    # -- 对外 ---------------------------------------------------------------
    @property
    def level(self) -> int:
        return STATE_LEVEL.get(self.state, 0)

    @property
    def is_active(self) -> bool:
        return self.state in _ACTIVE_STATES

    @property
    def position(self) -> Optional[Position]:
        return self._position

    def events(self, limit: int = 50) -> List[Dict[str, Any]]:
        items = list(self._events)[-limit:]
        return [e.to_dict() for e in items]

    def diagnostics(self) -> List[Dict[str, Any]]:
        return list(self._diagnostics)

    def step(self, ctx: SignalContext) -> Optional[TransitionEvent]:
        """推进一步。同一 ``bar_id`` 重复调用只刷新持仓，不重复判决（幂等）。"""
        if ctx is None or ctx.bar_id is None or ctx.bar_id < 0:
            return None
        # 防串味：ctx.code 与机器 code 不一致时拒绝推进。
        # 否则会 mark 到别人的持仓，并在账本里开出关不掉的孤儿仓位（永久占名额）。
        if str(ctx.code).strip() != self.code:
            self._diagnostics.append({
                "bar_id": ctx.bar_id, "code": self.code, "type": "CODE_MISMATCH",
                "ctx_code": str(ctx.code).strip(),
            })
            return None
        if self._ledger is not None:
            self._ledger.mark(ctx)

        if ctx.bar_id == self.last_bar:
            # 同 bar 重复调用：只更新快照与浮盈浮亏，绝不重复迁移
            self.last_ctx = ctx
            return None

        self.last_bar = int(ctx.bar_id)
        self.last_ctx = ctx
        self.bars_in_state += 1

        decided = self._decide(ctx)
        if decided is None:
            return None
        target, reason_code, reason_text = decided
        return self._apply(ctx, target, reason_code, reason_text)

    def force_exit(self, ctx: SignalContext, reason_code: str, reason_text: str = "") -> Optional[TransitionEvent]:
        """外部强制退场（如风控/人工干预），绕过确认 bar。"""
        if not self.is_active:
            return None
        return self._apply(ctx, SignalState.EXITING.value, reason_code, reason_text or "外部强制退场")

    # -- 判决 ---------------------------------------------------------------
    def _decide(self, ctx: SignalContext):
        p = self.params
        st = self.state
        price = float(ctx.price or 0.0)
        struct = ctx.struct_value
        pos = self._position
        mfe = pos.mfe_pct if pos else 0.0

        # EXITING 是"退场确认中"，下一根 bar 必然收敛到 EXITED。
        # 若在此处继续评估退场条件，会反复 EXITING->EXITING 而永远出不了场。
        if st == SignalState.EXITING.value:
            return (SignalState.EXITED.value, "EXIT_DONE", "退场完成")

        # ---- 条件全集（每根 bar 全部更新 streak，避免 elif 漏计） ----
        cond: Dict[str, bool] = {}

        # 退场类
        stop_line = pos.stop_price if pos and pos.stop_price > 0 else 0.0
        cond["hard_stop"] = bool(st in _ACTIVE_STATES and stop_line > 0 and price > 0 and price < stop_line)

        trail_line = 0.0
        if pos and pos.peak_price > 0:
            trail_line = pos.peak_price * (1.0 - p.trail_gap_pct / 100.0)
        cond["trail_stop"] = bool(
            st == SignalState.TRAILING.value and trail_line > 0 and price > 0 and price < trail_line
        )
        cond["accel_stop"] = bool(
            st == SignalState.ACCEL.value and stop_line > 0 and price > 0 and price < stop_line
        )
        cond["struct_break"] = bool(
            st in _ACTIVE_STATES and struct == Structure.LH_LL.value
            and ctx.vwap > 0 and price > 0 and price < ctx.vwap
        )
        cond["time_stop"] = bool(
            st in _ACTIVE_STATES and pos is not None
            and pos.holding_bars >= p.max_hold_bars and mfe < p.min_progress_pct
        )
        cond["temp_ebb"] = bool(
            st in (SignalState.HOLDING.value, SignalState.TRAILING.value)
            and ("退潮" in (ctx.temp_regime or "") or "COOLING" in (ctx.temp_regime or ""))
            and ctx.slope_3 < 0
        )

        # 晋级类
        cond["accel"] = bool(
            st in (SignalState.HOLDING.value, SignalState.TRAILING.value)
            and ctx.slope_3 > 0 and ctx.slope_3 > ctx.slope_12 > 0
            and ctx.vwap > 0 and price >= ctx.vwap
            and ctx.pct >= p.accel_pct_thresh
        )
        cond["trail_arm"] = bool(
            st == SignalState.HOLDING.value and mfe >= p.trail_start_pct
        )
        cond["trigger"] = bool(
            st == SignalState.ARMED.value
            and ctx.tradable
            and ctx.trigger_line > 0 and price > ctx.trigger_line
            and ctx.vol_confirm >= p.trigger_vol_thresh
            and ctx.above_ratio >= p.above_ratio_need
            and ctx.alpha_today >= p.min_alpha_pct
            and struct != Structure.LH_LL.value
        )
        # 跳空直通：开盘即站上触发线（价格在触发线上方），ARMED 永远不可达，
        # 必须允许 DORMANT 直接进场，否则高开突破全天无信号。追高幅度受 gap_max_pct 限制。
        cond["gap_trigger"] = bool(
            st == SignalState.DORMANT.value
            and ctx.tradable
            and ctx.trigger_line > 0 and price > ctx.trigger_line
            and price <= ctx.trigger_line * (1.0 + max(0.0, p.gap_max_pct) / 100.0)
            and ctx.vol_confirm >= p.trigger_vol_thresh
            and ctx.above_ratio >= p.above_ratio_need
            and ctx.alpha_today >= p.min_alpha_pct
            and struct != Structure.LH_LL.value
        )
        cond["arm"] = bool(
            st == SignalState.DORMANT.value
            and ctx.tradable
            and ctx.trigger_line > 0 and price > 0
            and 0.0 <= (ctx.trigger_line - price) / ctx.trigger_line * 100.0 <= p.arm_dist_pct
            and struct != Structure.LH_LL.value
            and (ctx.defend_line <= 0 or price >= ctx.defend_line)
        )
        # ARMED 僵死：价格已远离触发线（超过 arm_dist 的 N 倍）却仍挂着"逼近触发"
        cond["arm_invalid"] = bool(
            st == SignalState.ARMED.value
            and (
                struct == Structure.LH_LL.value
                or (ctx.defend_line > 0 and price > 0 and price < ctx.defend_line)
                or (
                    ctx.trigger_line > 0 and price > 0
                    and (ctx.trigger_line - price) / ctx.trigger_line * 100.0
                    > p.arm_dist_pct * max(1.0, p.arm_stale_multiple)
                )
            )
        )
        cond["rearm"] = bool(
            st == SignalState.EXITED.value
            and ctx.bar_id - self._last_exit_bar >= p.cooldown_bars
            and ctx.tradable
            and struct in (Structure.HH_HL.value, Structure.HH_LL.value, Structure.RANGE.value)
            and (ctx.defend_line <= 0 or price >= ctx.defend_line)
        )

        # 全部更新 streak
        hit = {k: self._hit(k, v) for k, v in cond.items()}

        # ---- 按优先级判决（风险优先，其次晋级） ----
        need_exit = max(1, p.confirm_bars)
        if hit["hard_stop"]:
            return (SignalState.EXITING.value, "STOP_LOSS",
                    "跌破止损位 %.3f，价格纪律出局" % stop_line)
        if hit["accel_stop"]:
            return (SignalState.EXITING.value, "ACCEL_STOP",
                    "加速后跌破锁定止损位 %.3f" % stop_line)
        if hit["trail_stop"]:
            return (SignalState.EXITING.value, "TRAIL_STOP",
                    "自峰值 %.3f 回撤超 %.1f%%，移动止盈出局" % (pos.peak_price if pos else 0.0, p.trail_gap_pct))
        if hit["struct_break"]:
            return (SignalState.EXITING.value, "STRUCT_BREAK",
                    "结构转为高降低降且跌破VWAP %.3f，结构纪律出局" % ctx.vwap)
        if hit["time_stop"]:
            return (SignalState.EXITING.value, "TIME_STOP",
                    "持有 %d bar 浮盈仅 %.2f%% 未达 %.1f%%，时间纪律出局"
                    % (pos.holding_bars if pos else 0, mfe, p.min_progress_pct))
        if hit["temp_ebb"]:
            return (SignalState.EXITING.value, "TEMP_EBB",
                    "市场退潮且短斜率转负，环境纪律出局")

        if hit["accel"]:
            return (SignalState.ACCEL.value, "ACCEL_LOCK",
                    "短斜率%.2f>中斜率%.2f>0 且站稳VWAP %.3f、涨幅%.2f%%达加速阈值，加速锁定"
                    % (ctx.slope_3, ctx.slope_12, ctx.vwap, ctx.pct))
        if hit["trail_arm"]:
            return (SignalState.TRAILING.value, "TRAIL_ARM",
                    "进场后最大浮盈 %.2f%% 达 %.1f%%，启用移动止盈(回撤%.1f%%)"
                    % (mfe, p.trail_start_pct, p.trail_gap_pct))
        if hit["trigger"]:
            return (SignalState.TRIGGERED.value, "BREAK_TRIGGER",
                    "突破触发线 %.3f，量能%.2fx，站线比例%.0f%%，超额%+.2f%%"
                    % (ctx.trigger_line, ctx.vol_confirm, ctx.above_ratio * 100.0, ctx.alpha_today))
        if hit["gap_trigger"]:
            return (SignalState.TRIGGERED.value, "GAP_BREAK_TRIGGER",
                    "开盘即站上触发线 %.3f(高于%.2f%%，追高上限%.1f%%)，量能%.2fx，站线%.0f%%，超额%+.2f%%"
                    % (ctx.trigger_line,
                       (price - ctx.trigger_line) / ctx.trigger_line * 100.0,
                       p.gap_max_pct, ctx.vol_confirm, ctx.above_ratio * 100.0, ctx.alpha_today))
        if hit["arm"]:
            return (SignalState.ARMED.value, "ARM_APPROACH",
                    "距触发线 %.3f 仅 %.2f%%，结构%s，进入待触发"
                    % (ctx.trigger_line,
                       (ctx.trigger_line - price) / ctx.trigger_line * 100.0,
                       ctx.struct_value))
        if hit["arm_invalid"]:
            dist_pct = 0.0
            if ctx.trigger_line > 0 and price > 0:
                dist_pct = (ctx.trigger_line - price) / ctx.trigger_line * 100.0
            if dist_pct > p.arm_dist_pct * max(1.0, p.arm_stale_multiple):
                return (SignalState.DORMANT.value, "ARM_STALE",
                        "距触发线 %.3f 已 %.2f%%（超过 %.1f 倍逼近阈值），退回静默"
                        % (ctx.trigger_line, dist_pct, p.arm_stale_multiple))
            return (SignalState.DORMANT.value, "ARM_INVALID",
                    "结构转弱或跌破防守线 %.3f，退回静默" % ctx.defend_line)
        if hit["rearm"]:
            return (SignalState.DORMANT.value, "REARM",
                    "冷却 %d bar 后结构重新合格，重新纳入观察" % p.cooldown_bars)

        # 未命中任何迁移：TRIGGERED 自动落到 HOLDING（开仓当 bar 的下一拍）
        if st == SignalState.TRIGGERED.value:
            return (SignalState.HOLDING.value, "POSITION_OPEN", "进场确认，转入持仓跟单")
        return None

    def _hit(self, name: str, cond: bool) -> bool:
        need = 1
        if name in ("arm", "trigger", "gap_trigger", "accel", "struct_break",
                    "time_stop", "temp_ebb", "arm_invalid", "rearm"):
            need = max(1, int(self.params.confirm_bars))
        elif name in ("hard_stop", "accel_stop", "trail_stop"):
            need = 1   # 止损不等待确认
        if cond:
            self._streaks[name] = self._streaks.get(name, 0) + 1
        else:
            self._streaks[name] = 0
        return self._streaks.get(name, 0) >= need

    # -- 迁移 ---------------------------------------------------------------
    def _apply(self, ctx: SignalContext, target: str, reason_code: str,
               reason_text: str) -> Optional[TransitionEvent]:
        p = self.params
        cur = self.state
        if cur == target:
            return None
        cur_level = STATE_LEVEL.get(cur, 0)
        tgt_level = STATE_LEVEL.get(target, 0)

        # 守卫 A：单调前进（ACCEL/TRAILING 不得回退到低级活跃状态）
        if cur in (SignalState.ACCEL.value, SignalState.TRAILING.value):
            if tgt_level < cur_level and target not in (
                SignalState.EXITING.value, SignalState.EXITED.value
            ):
                self._diagnostics.append({
                    "bar_id": ctx.bar_id, "code": self.code, "type": "MONOTONIC_BLOCK",
                    "from": cur, "blocked_to": target, "reason": reason_code,
                })
                return None

        # 守卫 B：最短驻留（仅约束"活跃状态"之间的迁移，止损/开仓/退场完成除外）
        if cur != target and reason_code not in _DWELL_EXEMPT_REASONS:
            if cur in _DWELL_SCOPE and self.bars_in_state < p.min_dwell_bars:
                self._diagnostics.append({
                    "bar_id": ctx.bar_id, "code": self.code, "type": "DWELL_BLOCK",
                    "from": cur, "blocked_to": target, "dwell": self.bars_in_state,
                })
                return None

        # 执行迁移副作用
        if target == SignalState.TRIGGERED.value and self._ledger is not None:
            stop = max(ctx.defend_line or 0.0, (ctx.vwap or 0.0) * 0.985)
            target_price = ctx.trigger_line * 1.06 if ctx.trigger_line > 0 else 0.0
            pos = self._ledger.open(self.code, ctx, reason_code,
                                    stop_price=stop, target_price=target_price)
            if pos is None:
                # 账本满：不进场，保持 ARMED（不产生假信号）
                self._diagnostics.append({
                    "bar_id": ctx.bar_id, "code": self.code, "type": "LEDGER_FULL",
                    "blocked_to": target,
                })
                return None
            self._position = pos
            self._entry_bar = int(ctx.bar_id)
            self._trim_done = False

        if target == SignalState.EXITING.value and self._ledger is not None:
            # 记住真正的退场原因，供 EXITING->EXITED 落账使用（不被 EXIT_DONE 覆盖）
            self._exit_reason = reason_code
            if not self._trim_done:
                self._ledger.trim(self.code, ctx, 0.5, reason_code)
                self._trim_done = True

        if target == SignalState.EXITED.value and self._ledger is not None:
            final_reason = self._exit_reason or reason_code
            self._ledger.close(self.code, ctx, final_reason)
            self._position = None
            self._last_exit_bar = int(ctx.bar_id)
            self._exit_reason = ""
            reason_code = final_reason

        if target == SignalState.DORMANT.value and cur == SignalState.EXITED.value:
            self._position = None
            self._trim_done = False

        ev = TransitionEvent(
            code=self.code,
            from_state=cur,
            to_state=target,
            bar_id=int(ctx.bar_id),
            ts=float(ctx.ts),
            price=float(ctx.price),
            pct=float(ctx.pct),
            market_temp=float(ctx.market_temp),
            reason_code=reason_code,
            reason_text=reason_text,
            evidence={
                "structure": ctx.struct_value,
                "slope_3": round(float(ctx.slope_3), 3),
                "slope_12": round(float(ctx.slope_12), 3),
                "vol_confirm": round(float(ctx.vol_confirm), 3),
                "above_ratio": round(float(ctx.above_ratio), 3),
                "alpha_today": round(float(ctx.alpha_today), 3),
                "vwap": round(float(ctx.vwap), 3),
                "trigger_line": round(float(ctx.trigger_line), 3),
                "defend_line": round(float(ctx.defend_line), 3),
                "mfe_pct": round(float(self._position.mfe_pct), 2) if self._position else 0.0,
                "tradable": bool(ctx.tradable),
            },
        )
        self._events.append(ev)
        self.state = target
        self.bars_in_state = 0
        self._streaks.clear()
        return ev

    # -- 快照 ---------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        ctx = self.last_ctx
        pos = self._position
        return {
            "code": self.code,
            "state": self.state,
            "state_label": STATE_LABELS.get(self.state, self.state),
            "level": self.level,
            "bars_in_state": self.bars_in_state,
            "bar_id": self.last_bar,
            "price": round(float(ctx.price), 3) if ctx else 0.0,
            "pct": round(float(ctx.pct), 2) if ctx else 0.0,
            "structure": ctx.struct_value if ctx else Structure.RANGE.value,
            "slope_3": round(float(ctx.slope_3), 3) if ctx else 0.0,
            "slope_12": round(float(ctx.slope_12), 3) if ctx else 0.0,
            "tradable": bool(ctx.tradable) if ctx else True,
            "untradable_reason": (ctx.untradable_reason if ctx else ""),
            "holding_bars": pos.holding_bars if pos else 0,
            "mfe_pct": round(pos.mfe_pct, 2) if pos else 0.0,
            "mae_pct": round(pos.mae_pct, 2) if pos else 0.0,
            "position": pos.to_dict() if pos else None,
            "last_event": self._events[-1].to_dict() if self._events else None,
        }


# ---------------------------------------------------------------------------
# 去弱留强（跨时比较）
# ---------------------------------------------------------------------------
class WeakStrongRanker:
    """按"浮盈增长速度 + 结构 + 回撤"给持仓排序，给出换仓建议。"""

    _STRUCT_BONUS = {
        Structure.HH_HL.value: 3.0,
        Structure.HH_LL.value: 1.0,
        Structure.LH_HL.value: 0.5,
        Structure.RANGE.value: 0.0,
        Structure.LH_LL.value: -3.0,
    }

    @classmethod
    def score(cls, pos: Position, structure: str = "", pct_now: float = 0.0) -> float:
        bars = max(1, pos.holding_bars)
        growth = pos.mfe_pct / bars          # 每 bar 浮盈增长：留强的核心
        return round(
            growth * 10.0
            + cls._STRUCT_BONUS.get(structure, 0.0)
            + pos.mfe_pct * 0.30
            + pos.mae_pct * 0.50
            + float(pct_now) * 0.10,
            3,
        )

    @classmethod
    def rank(cls, positions: List[Position],
             structure_map: Optional[Dict[str, str]] = None,
             pct_map: Optional[Dict[str, float]] = None) -> List[Tuple[str, float]]:
        structure_map = structure_map or {}
        pct_map = pct_map or {}
        scored = [
            (p.code, cls.score(p, structure_map.get(p.code, ""), pct_map.get(p.code, 0.0)))
            for p in positions
        ]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored

    @classmethod
    def suggest_swap(cls, positions: List[Position], incoming_score: float,
                     structure_map: Optional[Dict[str, str]] = None,
                     pct_map: Optional[Dict[str, float]] = None,
                     margin: float = 1.0) -> Optional[str]:
        """若新信号分显著高于最弱者，返回应被换掉的代码；否则 None。"""
        if not positions:
            return None
        ranked = cls.rank(positions, structure_map, pct_map)
        weakest_code, weakest_score = ranked[-1]
        if incoming_score - weakest_score >= margin:
            return weakest_code
        return None
