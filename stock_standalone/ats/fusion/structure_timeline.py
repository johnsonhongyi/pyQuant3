# -*- coding: utf-8 -*-
"""ats/fusion/structure_timeline.py — 结构机会的时间轴状态机。

为什么必须有这个模块：
    原实现把"分时悬空"判定成 `min(自开盘以来的全部低点垫)`，该值单调不增，
    任一分钟的最低价碰一下均线，这只票当天就**永久**失去结构资格。
    实盘后果：钧达股份 (002865) 09:31 悬空垫恰好 0.000%，当日 +11.43% 全程无法触发；
    中国卫星 (600118) 09:33 回踩后同样永久失效。

    价格是随时间流动的，"结构还在不在"必须是一个**可更新、可撤销、可恢复**的状态，
    而不是开盘三分钟内一次性盖章。

状态定义：
    WAITING   结构底色在（昨日站稳 10V），今日尚未点火 —— 候选，不给保底
    CONFIRMED 悬空 + 突破昨高，结构验证成立 —— 允许保底（但仍受风控上限约束）
    BROKEN    曾经成立后失守（跌破分时均线 / 跌破昨收 / 自高点回撤超限）—— 撤销保底
    EVICTED   反复失守被剔除 —— 当日不再参与，需连续 rearm_bars 次复核才能复活

    "直到符合条件"：EVICTED 不是永久黑名单，满足更严格的复核条件即可重新 CONFIRMED。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

STATUS_WAITING = "WAITING"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_BROKEN = "BROKEN"
STATUS_EVICTED = "EVICTED"

# 这些状态下不允许给结构保底
BLOCKED_STATUS = (STATUS_BROKEN, STATUS_EVICTED)

STATUS_LABEL = {
    STATUS_WAITING: "⏳ 结构待点火",
    STATUS_CONFIRMED: "🎯 结构验证中",
    STATUS_BROKEN: "⚠️ 结构失守",
    STATUS_EVICTED: "🚫 结构剔除",
}


@dataclass
class StructureSnapshot:
    """某一时刻的结构状态快照（全部可回溯）。"""

    code: str = ""
    status: str = STATUS_WAITING
    ts: float = 0.0

    confirm_n: int = 0          # 当日累计成立次数（反复点火）
    break_n: int = 0            # 当日累计失守次数
    confirm_ts: float = 0.0     # 最近一次成立时刻
    break_ts: float = 0.0       # 最近一次失守时刻
    status_since: float = 0.0   # 当前状态的起始时刻

    cushion_roll: float = 0.0   # 近窗口最小悬空垫（时间可恢复）
    cushion_now: float = 0.0    # 当前价距分时均线
    drawdown_pct: float = 0.0   # 自确认后最高价回撤
    high_water: float = 0.0     # 确认后最高价

    reason: str = ""            # 失守/剔除原因（可解释）

    def blocked(self) -> bool:
        return self.status in BLOCKED_STATUS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "status": self.status,
            "ts": round(float(self.ts), 3),
            "label": STATUS_LABEL.get(self.status, self.status),
            "confirm_n": int(self.confirm_n),
            "break_n": int(self.break_n),
            "confirm_ts": round(float(self.confirm_ts), 3),
            "break_ts": round(float(self.break_ts), 3),
            "status_since": round(float(self.status_since), 3),
            "cushion_roll": round(float(self.cushion_roll), 3),
            "cushion_now": round(float(self.cushion_now), 3),
            "drawdown_pct": round(float(self.drawdown_pct), 2),
            "high_water": round(float(self.high_water), 4),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StructureSnapshot:
        if not d:
            return cls()
        return cls(
            code=str(d.get("code") or ""),
            status=str(d.get("status") or STATUS_WAITING),
            ts=float(d.get("ts") or 0.0),
            confirm_n=int(d.get("confirm_n") or 0),
            break_n=int(d.get("break_n") or 0),
            confirm_ts=float(d.get("confirm_ts") or 0.0),
            break_ts=float(d.get("break_ts") or 0.0),
            status_since=float(d.get("status_since") or 0.0),
            cushion_roll=float(d.get("cushion_roll") or 0.0),
            cushion_now=float(d.get("cushion_now") or 0.0),
            drawdown_pct=float(d.get("drawdown_pct") or 0.0),
            high_water=float(d.get("high_water") or 0.0),
            reason=str(d.get("reason") or ""),
        )


class StructureTimeline:
    """按 code 维护结构状态的时间轴。线程安全由调用方保证（shadow 持锁）。"""

    def __init__(
        self,
        cushion_min: float = 0.20,
        max_break_n: int = 3,
        rearm_bars: int = 3,
        drawdown_limit: float = 1.50,
        close_break_pct: float = 1.00,
        vwap_break_tol: float = 0.20,
    ):
        self.cushion_min = float(cushion_min)
        self.max_break_n = int(max_break_n)
        self.rearm_bars = max(1, int(rearm_bars))
        self.drawdown_limit = float(drawdown_limit)
        self.close_break_pct = float(close_break_pct)
        self.vwap_break_tol = float(vwap_break_tol)
        self._states: Dict[str, StructureSnapshot] = {}
        self._streak: Dict[str, int] = {}
        self._day = ""

    # ------------------------------------------------------------------
    def reset(self, day: str = "") -> None:
        self._states.clear()
        self._streak.clear()
        self._day = day

    def get(self, code: str) -> Optional[StructureSnapshot]:
        return self._states.get(str(code).zfill(6))

    def snapshot_state(self) -> Dict[str, Any]:
        return {
            "day": self._day,
            "states": {k: v.to_dict() for k, v in self._states.items()},
            "streak": dict(self._streak),
        }

    def load_state(self, data: Dict[str, Any]) -> None:
        if not data:
            return
        self._day = str(data.get("day") or "")
        raw_states = data.get("states") or {}
        self._states = {
            str(k).zfill(6): StructureSnapshot.from_dict(v) for k, v in raw_states.items()
        }
        self._streak = {str(k).zfill(6): int(v) for k, v in (data.get("streak") or {}).items()}

    # ------------------------------------------------------------------
    def update(
        self,
        code: str,
        ts: float,
        price: float,
        vwap: float,
        hi_pre1: float = 0.0,
        close_pre1: float = 0.0,
        cushion_roll: float = 0.0,
        cushion_now: float = 0.0,
        prejudged: bool = False,
    ) -> StructureSnapshot:
        """喂一根最新行情，返回当前结构状态。纯内存、O(1)、永不抛异常。"""
        code = str(code).zfill(6)
        st = self._states.get(code)
        if st is None:
            st = StructureSnapshot(code=code, status=STATUS_WAITING, ts=ts, status_since=ts)
            self._states[code] = st

        # 行情不可用：保持原状态，不误判
        if price <= 0 or vwap <= 0:
            st.ts = ts
            return st

        st.ts = ts
        st.cushion_roll = float(cushion_roll)
        st.cushion_now = float(cushion_now)

        # ---- 点火条件（随时间重算，不依赖开盘瞬间）：严禁 hi_pre1 <= 0 短路判定为突破 ----
        breakout = (hi_pre1 > 0) and (price >= hi_pre1 * 0.995)
        cushion_ok = float(cushion_roll) >= self.cushion_min
        signal = bool(breakout and cushion_ok and prejudged)

        # ---- 失守条件（三条硬边界，任一命中即失守）----
        reason = ""
        if price < vwap * (1.0 - self.vwap_break_tol / 100.0):
            reason = "跌破分时均线{:.2f}".format(vwap)
        elif close_pre1 > 0 and price < close_pre1 * (1.0 - self.close_break_pct / 100.0):
            reason = "跌破昨收{:.2f}".format(close_pre1)

        if st.status == STATUS_CONFIRMED:
            if price > st.high_water:
                st.high_water = price
            if st.high_water > 0:
                st.drawdown_pct = (st.high_water - price) / st.high_water * 100.0
            if not reason and st.drawdown_pct >= self.drawdown_limit:
                reason = "自高点回撤{:.1f}%".format(st.drawdown_pct)

        if reason:
            if st.status == STATUS_CONFIRMED:
                st.break_n += 1
                st.break_ts = ts
                st.status_since = ts
                st.reason = reason
                st.status = STATUS_EVICTED if st.break_n >= self.max_break_n else STATUS_BROKEN
                self._streak[code] = 0
            elif st.status == STATUS_WAITING and st.break_n == 0:
                # 尚未成立就已在均线下方：只是"没结构"，不算失守，避免误伤
                pass
            st.ts = ts
            return st

        # ---- 状态迁移：成立 / 恢复 ----
        if st.status in (STATUS_WAITING, STATUS_BROKEN, STATUS_EVICTED):
            if signal:
                need = self.rearm_bars if st.status == STATUS_EVICTED else 1
                streak = int(self._streak.get(code, 0)) + 1
                self._streak[code] = streak
                if streak >= need:
                    st.status = STATUS_CONFIRMED
                    st.confirm_n += 1
                    st.confirm_ts = ts
                    st.status_since = ts
                    st.high_water = price
                    st.drawdown_pct = 0.0
                    st.reason = ""
                    # break_n 刻意不归零：当日累计失守次数是"这只票值不值得再信"的证据，
                    # 归零会让反复失守的票无限复活。复活的票保留履历，只有一次更短的机会。
                    self._streak[code] = 0
            else:
                self._streak[code] = 0
        elif st.status == STATUS_CONFIRMED:
            if price > st.high_water:
                st.high_water = price
            if st.high_water > 0:
                st.drawdown_pct = (st.high_water - price) / st.high_water * 100.0

        return st
