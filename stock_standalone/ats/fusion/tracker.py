# -*- coding: utf-8 -*-
"""ats/fusion/tracker.py — 赛马跟踪器：把"时间点快照"变成"带历史的连续判断"。

为什么需要它（这是当前系统最大的断点）：
    现在的融合层每次评估都是**无状态**的。10:12 看到"缩量转放量"，
    但它不知道这只票 09:45 已经"逆势带头"、09:54 已经放过一次量、
    也不知道它首异动时只有 +1.2%。
    结果就是：
        1) 每个时点都在重新判断"要不要买"，而不是判断"这只票跑到第几圈了"；
        2) 旧证据全部丢失，尾段加速的票在 10:30 之后只能靠"追高"才能进场；
        3) 一旦某个时点被否决，就永久失去参与资格（没有连续迭代）。

本模块做的事：
    - **发令枪**：记下每只票第一次出现异动的时间/价格/涨幅；
    - **带旧信号**：证据链累积（形态、级别、时段），新判断永远携带历史；
    - **第一波入局**：以"持续性"确认入场，而不是以"位置漂亮"确认；
    - **入局后才剔除**：入场前只做宽松观察（不因分数低而剔除），
      入场后才按量能衰减、回撤、跌破 10 日 VWAP 做剔除；
    - **量能持续 / 想的多回踩的少**：把这两个词直接变成可计算的分量。

三个核心量（全部 0~1，可解释、可校准）：
    vol_persist  放量 bar 占比 + 量能不衰减       —— 量能持续
    efficiency   累计上涨 / (累计上涨 + 累计回踩) —— 想的多回踩的少
    hold         站上 10 日 VWAP 的 bar 占比      —— 站得住
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 阶段：观察（未入局） -> 入局 -> 持有 -> 走弱 -> 剔除
STAGE_WATCH = "观察"
STAGE_ENTER = "入局"
STAGE_HOLD = "持有"
STAGE_WEAKEN = "走弱"
STAGE_EVICT = "剔除"

STAGE_ORDER = {STAGE_WATCH: 0, STAGE_ENTER: 1, STAGE_HOLD: 2, STAGE_WEAKEN: 3, STAGE_EVICT: 4}


@dataclass
class TrackConfig:
    """跟踪器阈值。改这里就能做阈值标定，不必动逻辑。"""

    min_bars: int = 3                 # 至少观察几根 bar 才允许入局
    min_evidence: int = 2             # 至少几条证据（形态/级别）才允许入局
    enter_persist: float = 55.0       # 入局所需持续性分
    enter_max_chase: float = 5.0      # 首异动 -> 入局 的最大涨幅（第一波，不追）
    enter_vwap10_tol: float = 0.995   # 站上 10 日 VWAP 的容差
    enter_eff_min: float = 0.52       # 想的多回踩的少：上涨占比下限
    evict_drawdown: float = 4.0       # 从片段高点回撤超过此值 -> 剔除
    evict_vwap10_tol: float = 0.985   # 跌破 10 日 VWAP 此比例 -> 剔除
    evict_flat_bars: int = 8          # 连续多少根未创新高算走弱
    vol_decay: float = 0.75           # 近期量能 / 前期量能 低于此值算衰减
    watch_expire_min: float = 90.0    # 观察期上限（仅当期间毫无新证据才过期）
    # 诱多陷阱
    trap_persist_penalty: float = 30.0   # 陷阱对持续性分的最大扣分
    gap_risk_block: float = 80.0         # 跨日风险超过此值，禁止入局
    gap_risk_caution: float = 50.0       # 超过此值，要求首异动更早（<=2%）
    # 趋同：大家都涨了就没有意义，那时的异动多是诱多
    # 实测：趋同 0.60~1.00 组 T+1 为负；但 0.60~0.65 且温度不高时仍有机会，
    # 所以入局闸门设在 0.65/55℃，把最坏的"高温+高度趋同"挡掉，其余交给可下单闸门。
    consensus_max: float = 0.65          # 趋同度上限
    consensus_hot_temp: float = 55.0     # 高于此温度且趋同>=上限 -> 禁止入局
    spike_evict_drawdown: float = 2.0    # 入局后冲高回落达此幅度即剔除
    max_history: int = 16             # 证据链保留条数
    day_carry_max: int = 5            # 跨日保留几日摘要


@dataclass
class TrackState:
    code: str
    day: str = ""

    first_ts: float = 0.0
    first_price: float = 0.0
    first_pct: float = 0.0
    first_kind: str = ""

    last_ts: float = 0.0
    last_price: float = 0.0
    last_pct: float = 0.0
    prev_price: float = 0.0

    hi: float = 0.0                   # 片段高点（自首异动起）
    hi_ts: float = 0.0
    lo: float = 0.0                   # 片段低点（自首异动起）

    bars: int = 0
    vol_up_bars: int = 0              # 放量 bar 数（vol_ratio >= 1.2）
    above_vwap10_bars: int = 0
    up_sum: float = 0.0               # 累计上涨（bar 级）
    down_sum: float = 0.0             # 累计回踩（bar 级）
    stale_bars: int = 0               # 距上次创新高的 bar 数

    vol_recent: float = 1.0           # 近 5 根平均量比
    vol_base: float = 1.0             # 首段平均量比

    patterns_seen: Dict[str, int] = field(default_factory=dict)
    traps_seen: Dict[str, int] = field(default_factory=dict)   # 诱多陷阱计数
    traps: List[str] = field(default_factory=list)             # 当前 bar 命中的陷阱
    consensus: float = 0.0                                     # 趋同度（0~1）
    temp: float = 0.0                                          # 市场温度
    gap_risk: float = 0.0                                      # 跨日风险（昨日大涨/长上影）
    risk_notes: List[str] = field(default_factory=list)
    best_tier: int = 0
    best_rar: float = 0.0
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    stage: str = STAGE_WATCH
    persist: float = 0.0
    enter_ts: float = 0.0
    enter_price: float = 0.0
    enter_pct: float = 0.0
    evict_ts: float = 0.0
    evict_reason: str = ""

    day_summaries: List[Dict[str, Any]] = field(default_factory=list)
    carried: bool = False          # 今日是否由昨日持仓延续而来
    t1_decided_day: str = ""       # 今日 T+1 决策是否已做

    # -- 输出 ---------------------------------------------------------------
    @property
    def age_min(self) -> float:
        if self.first_ts <= 0 or self.last_ts <= 0:
            return 0.0
        return max(0.0, (self.last_ts - self.first_ts) / 60.0)

    @property
    def efficiency(self) -> float:
        tot = self.up_sum + self.down_sum
        return self.up_sum / tot if tot > 0 else 0.5

    @property
    def vol_frac(self) -> float:
        return self.vol_up_bars / self.bars if self.bars else 0.0

    @property
    def hold_frac(self) -> float:
        return self.above_vwap10_bars / self.bars if self.bars else 0.0

    @property
    def drawdown(self) -> float:
        if self.hi <= 0 or self.last_price <= 0:
            return 0.0
        return max(0.0, (self.hi - self.last_price) / self.hi * 100.0)

    @property
    def since_first_pct(self) -> float:
        """自首异动以来的涨幅——"第一波"就是看这个，不是看当日涨幅。"""
        if self.first_price <= 0 or self.last_price <= 0:
            return 0.0
        return (self.last_price / self.first_price - 1.0) * 100.0

    def evidence_count(self) -> int:
        return len(self.evidence)

    def chain(self, limit: int = 6) -> str:
        """证据链文本：这就是"带上旧信号"的可读形式。"""
        if not self.evidence:
            return ""
        parts = []
        for e in self.evidence[-limit:]:
            t = time.strftime("%H:%M", time.localtime(int(e["ts"])))
            parts.append("{} {}{}".format(t, e["kind"], "(L{})".format(e["tier"]) if e.get("tier") else ""))
        return " → ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "day": self.day,
            "stage": self.stage,
            "persist": round(self.persist, 1),
            "first_time": time.strftime("%H:%M", time.localtime(int(self.first_ts))) if self.first_ts else "",
            "first_pct": round(self.first_pct, 2),
            "since_first_pct": round(self.since_first_pct, 2),
            "last_pct": round(self.last_pct, 2),
            "age_min": round(self.age_min, 1),
            "bars": self.bars,
            "vol_frac": round(self.vol_frac, 2),
            "efficiency": round(self.efficiency, 2),
            "hold_frac": round(self.hold_frac, 2),
            "drawdown": round(self.drawdown, 2),
            "evidence_n": self.evidence_count(),
            "patterns": dict(self.patterns_seen),
            "traps": list(self.traps),
            "traps_seen": dict(self.traps_seen),
            "gap_risk": round(self.gap_risk, 1),
            "consensus": round(self.consensus, 3),
            "temp": round(self.temp, 1),
            "risk_notes": list(self.risk_notes),
            "best_tier": self.best_tier,
            "best_rar": round(self.best_rar, 1),
            "chain": self.chain(),
            "enter_time": time.strftime("%H:%M", time.localtime(int(self.enter_ts))) if self.enter_ts else "",
            "enter_price": round(self.enter_price, 3),
            "enter_pct": round(self.enter_pct, 2),
            "evict_reason": self.evict_reason,
            "prev_day": self.day_summaries[-1] if self.day_summaries else None,
        }


def _clip01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


class RaceTracker:
    """赛马跟踪器：一只票一条状态，跨 bar 连续迭代，可选跨日携带。

    用法（回放里）：
        tracker = RaceTracker()
        for 每根 bar:
            st = tracker.update(code, ts, price, vwap10=..., vol_ratio=..., pct=...,
                                tier=..., rar=..., patterns=[...], ...)
            if st.stage == STAGE_ENTER and 之前不是入局:
                # 第一波入局 -> 下单
    """

    def __init__(self, config: Optional[TrackConfig] = None):
        self.cfg = config or TrackConfig()
        self._states: Dict[str, TrackState] = {}
        self._events: List[Dict[str, Any]] = []   # 入局/剔除事件流
        self._blocked: Dict[str, str] = {}        # code|day -> 被拦下的原因（去重计数）

    # -- 生命周期 -----------------------------------------------------------
    def get(self, code: str) -> Optional[TrackState]:
        return self._states.get(str(code).zfill(6))

    def states(self) -> List[TrackState]:
        return list(self._states.values())

    def events(self) -> List[Dict[str, Any]]:
        return list(self._events)

    def _block(self, st: TrackState, reason: str) -> None:
        self._blocked.setdefault("{}|{}".format(st.code, st.day), reason)

    def blocked_stats(self) -> Dict[str, int]:
        from collections import Counter

        c: Counter = Counter(self._blocked.values())
        return dict(c)

    def reset(self, keep_cross_day: bool = False) -> None:
        if keep_cross_day:
            for st in self._states.values():
                self._archive_day(st)
        self._states.clear()
        self._events.clear()

    def _archive_day(self, st: TrackState) -> None:
        if not st.day or st.bars == 0:
            return
        st.day_summaries.append(
            {
                "day": st.day,
                "stage": st.stage,
                "persist": round(st.persist, 1),
                "best_tier": st.best_tier,
                "enter_pct": round(st.enter_pct, 2),
                "enter_price": round(st.enter_price, 3),
                "evicted": st.stage == STAGE_EVICT,
            }
        )
        if len(st.day_summaries) > self.cfg.day_carry_max:
            st.day_summaries = st.day_summaries[-self.cfg.day_carry_max:]

    # -- 主更新 -------------------------------------------------------------
    def update(
        self,
        code: str,
        ts: float,
        price: float,
        pct: float,
        vwap10: float = 0.0,
        vwap: float = 0.0,
        vol_ratio: float = 1.0,
        tier: int = 0,
        rar: float = 0.0,
        patterns: Optional[List[str]] = None,
        day: str = "",
        anomaly: bool = False,
        note: str = "",
        traps: Optional[List[str]] = None,
        gap_risk: float = 0.0,
        risk_notes: Optional[List[str]] = None,
        consensus: float = 0.0,
        temp: float = 0.0,
    ) -> TrackState:
        code = str(code).zfill(6)
        st = self._states.get(code)
        if st is None:
            st = TrackState(code=code, day=day)
            self._states[code] = st
        elif day and st.day and day != st.day:
            self._archive_day(st)
            carry = st.day_summaries[-1]
            st = TrackState(code=code, day=day, day_summaries=st.day_summaries)
            self._states[code] = st
            # 跨日携带：昨日入局且未剔除 -> 今天以"持有"开局（多日无法骗人）
            if carry.get("stage") in (STAGE_ENTER, STAGE_HOLD) and not carry.get("evicted"):
                st.stage = STAGE_HOLD
                st.carried = True
                st.enter_price = float(carry.get("enter_price") or 0.0)
                st.enter_ts = 0.0

        patterns = list(patterns or [])
        traps = list(traps or [])
        st.traps = traps
        st.gap_risk = float(gap_risk or 0.0)
        st.consensus = float(consensus or 0.0)
        st.temp = float(temp or 0.0)
        if risk_notes:
            st.risk_notes = list(risk_notes)[:4]
        for t in traps:
            if t not in st.traps_seen:
                st.traps_seen[t] = 1
                self._push_evidence(st, ts, "陷阱:" + t, 0, 0.0, "trap")
            else:
                st.traps_seen[t] += 1
        st.day = day or st.day
        st.last_ts = float(ts)
        st.prev_price = st.last_price or float(price)
        st.last_price = float(price)
        st.last_pct = float(pct)
        st.bars += 1

        # 1) 发令枪：第一次出现异动（形态 / L2+ / 相对强度）就记下来
        if st.first_ts <= 0 and (anomaly or tier >= 2 or patterns):
            st.first_ts = float(ts)
            st.first_price = float(price)
            st.first_pct = float(pct)
            st.first_kind = patterns[0] if patterns else ("L{}".format(tier) if tier else "异动")
            st.hi = st.lo = float(price)
            st.hi_ts = float(ts)
            st.vol_base = max(1.0, float(vol_ratio))
            self._push_evidence(st, ts, st.first_kind, tier, rar, "首异动")

        if st.first_ts <= 0:
            if st.carried:
                # 昨日持仓延续：今日首根 bar 作为今日的观察起点，
                # 不能因为"今天还没出现异动"就把持仓丢掉（这正是 T+1 决策要处理的情形）
                st.first_ts = float(ts)
                st.first_price = float(price)
                st.first_pct = float(pct)
                st.first_kind = "昨日持仓"
                st.hi = st.lo = float(price)
                st.hi_ts = float(ts)
                st.vol_base = max(1.0, float(vol_ratio))
            else:
                st.persist = 0.0
                return st

        # 2) 逐 bar 累积"量能持续 / 想的多回踩的少 / 站得住"
        if vol_ratio >= 1.2:
            st.vol_up_bars += 1
        if vwap10 > 0 and price >= vwap10:
            st.above_vwap10_bars += 1

        delta = st.last_price - st.prev_price
        if delta > 0:
            st.up_sum += delta / max(1e-9, st.prev_price) * 100.0
        elif delta < 0:
            st.down_sum += -delta / max(1e-9, st.prev_price) * 100.0

        if price > st.hi:
            st.hi = float(price)
            st.hi_ts = float(ts)
            st.stale_bars = 0
        else:
            st.stale_bars += 1
        if price < st.lo or st.lo <= 0:
            st.lo = float(price)

        # 量能：近 5 根 vs 首段，判断"量能是否还在"
        st.vol_recent = 0.75 * st.vol_recent + 0.25 * float(vol_ratio)

        # 3) 证据累积（同一形态同一天只记一次，避免刷屏）
        if tier >= 2:
            st.best_tier = max(st.best_tier, int(tier))
        st.best_rar = max(st.best_rar, float(rar))
        for p in patterns:
            if p not in st.patterns_seen:
                st.patterns_seen[p] = 1
                self._push_evidence(st, ts, p, tier, rar, "形态")
        if tier >= 2:
            last = st.evidence[-1] if st.evidence else None
            if last is None or last.get("tier", 0) < tier or (ts - last["ts"]) >= 900:
                self._push_evidence(st, ts, "级别抬升", tier, rar, "级别")

        # 4) 持续性分（带旧信号：用累积量，不是快照）
        st.persist = self._persist(st)

        # 由历史累积出来的两条证据：量能持续、持续性达标
        # （这是"旧信号"里最有价值的两条，必须进证据链，否则单形态票永远凑不够证据）
        if st.vol_up_bars >= 3 and not any(e["kind"] == "量能持续" for e in st.evidence):
            self._push_evidence(st, ts, "量能持续", st.best_tier, st.best_rar, "vol")
        if st.persist >= 60.0 and not any(e["kind"] == "持续性达标" for e in st.evidence):
            self._push_evidence(st, ts, "持续性达标", st.best_tier, st.best_rar, "persist")

        # 5) 阶段推进
        self._advance(st, price, vwap10, ts)
        return st

    # -- 落盘：不能每天都是新的一天 -----------------------------------------
    _PERSIST_FIELDS = (
        "code", "day", "first_ts", "first_price", "first_pct", "first_kind",
        "last_ts", "last_price", "last_pct", "hi", "lo", "bars",
        "vol_up_bars", "above_vwap10_bars", "up_sum", "down_sum", "stale_bars",
        "vol_recent", "vol_base", "best_tier", "best_rar",
        "stage", "persist", "enter_ts", "enter_price", "enter_pct",
        "evict_ts", "evict_reason", "carried", "t1_decided_day",
        "patterns_seen", "traps_seen", "day_summaries",
    )

    def save(self, path: str, keep_days: int = 3) -> int:
        """把状态落到磁盘。只保留有历史价值的字段，不存临时证据链。"""
        import json
        import os

        payload = {"version": 1, "saved_at": time.time(), "states": []}
        for st in self._states.values():
            d = {k: getattr(st, k) for k in self._PERSIST_FIELDS}
            d["evidence"] = [e for e in st.evidence[-6:]]
            payload["states"].append(d)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
        return len(payload["states"])

    def load(self, path: str, keep_days: int = 3) -> int:
        """从磁盘恢复状态。只恢复近 keep_days 天有活动的票，避免无限膨胀。"""
        import json
        import os

        if not os.path.exists(path):
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return 0
        days = sorted({str(d.get("day") or "") for d in payload.get("states") or []})
        alive = set(days[-keep_days:]) if days else set()
        n = 0
        for d in payload.get("states") or []:
            if str(d.get("day") or "") not in alive:
                continue
            try:
                st = TrackState(**{k: d.get(k) for k in self._PERSIST_FIELDS if k in d})
            except Exception:
                continue
            st.evidence = list(d.get("evidence") or [])
            self._states[st.code] = st
            n += 1
        return n

    # -- 内部 ---------------------------------------------------------------
    def _push_evidence(self, st: TrackState, ts: float, kind: str, tier: int, rar: float, src: str) -> None:
        # 同一时刻、同一证据只记一次：首异动与形态循环会推到同一条
        for e in reversed(st.evidence[-3:]):
            if abs(e["ts"] - float(ts)) < 1.0 and e["kind"] == kind:
                if tier > e.get("tier", 0):
                    e["tier"] = int(tier)
                return
        st.evidence.append(
            {"ts": float(ts), "kind": kind, "tier": int(tier), "rar": round(float(rar), 1), "src": src}
        )
        if len(st.evidence) > self.cfg.max_history:
            st.evidence = st.evidence[-self.cfg.max_history:]

    def _persist(self, st: TrackState) -> float:
        vol_keep = _clip01(st.vol_recent / max(1e-6, st.vol_base) / 1.1)
        ev = _clip01(len(st.patterns_seen) / 3.0) * 0.6 + _clip01(st.best_tier / 4.0) * 0.4
        fresh = _clip01(1.0 - st.stale_bars / 12.0)
        # 跨日连续性加成：昨天入局/持有且没被剔除
        carry = 0.0
        if st.day_summaries:
            prev = st.day_summaries[-1]
            if prev.get("stage") in (STAGE_ENTER, STAGE_HOLD) and not prev.get("evicted"):
                carry = 1.0
        score = (
            0.24 * st.vol_frac
            + 0.22 * st.efficiency
            + 0.16 * st.hold_frac
            + 0.15 * ev
            + 0.09 * vol_keep
            + 0.06 * fresh
            + 0.08 * carry
        )
        raw = 100.0 * _clip01(score)
        # 诱多陷阱扣分：按"最强陷阱"扣，不叠加；跨日风险按比例扣
        if st.traps:
            from ats.fusion.trap import trap_severity
            raw -= self.cfg.trap_persist_penalty * trap_severity(st.traps)
        if st.gap_risk > 0:
            raw -= 0.10 * st.gap_risk
        return round(max(0.0, min(100.0, raw)), 1)

    def _advance(self, st: TrackState, price: float, vwap10: float, ts: float) -> None:
        cfg = self.cfg
        was = st.stage

        # 已剔除：不再回头（当日）
        if was == STAGE_EVICT:
            return

        if was in (STAGE_ENTER, STAGE_HOLD, STAGE_WEAKEN):
            # ---- T+1 持仓决策：昨天买的，今天要不要跟（每天只做一次）----
            if st.carried and st.t1_decided_day != st.day and st.bars >= 1:
                from ats.fusion.trap import position_decision, ACT_CLEAR, ACT_HALF
                act, why = position_decision(st.persist, st.traps, st.gap_risk, st.drawdown)
                st.t1_decided_day = st.day
                self._events.append({
                    "kind": "T1",
                    "code": st.code,
                    "ts": float(ts),
                    "time": time.strftime("%H:%M", time.localtime(int(ts))),
                    "action": act,
                    "reason": why,
                    "price": round(st.last_price, 3),
                    "pct": round(st.last_pct, 2),
                    "persist": st.persist,
                    "gap_risk": round(st.gap_risk, 1),
                    "traps": list(st.traps),
                    "pnl_from_enter": round(
                        (st.last_price / st.enter_price - 1.0) * 100.0, 2
                    ) if st.enter_price > 0 else 0.0,
                    "chain": st.chain(),
                })
                if act == ACT_CLEAR:
                    self._evict(st, ts, "T+1" + why)
                    return
                if act == ACT_HALF:
                    st.persist = max(0.0, st.persist - 10.0)

            # 昨日大涨、今日杀跌：开盘半小时内出现就清仓（这条不等 VWAP 规则）
            if st.carried and st.bars <= 10:
                from ats.fusion.trap import TRAP_PREV_DUMP as _PD
                if _PD in st.traps:
                    self._evict(st, ts, "T+1昨日大涨今日杀跌")
                    return

            # ---- 入局之后才开始剔除 ----
            # 诱多陷阱：冲高回落到一定幅度，或放量跌破均价且量能衰减
            from ats.fusion.trap import TRAP_SPIKE_FADE, TRAP_GAP_FADE, TRAP_BREAK_VWAP
            if (TRAP_SPIKE_FADE in st.traps or TRAP_GAP_FADE in st.traps) \
                    and st.drawdown >= cfg.spike_evict_drawdown:
                self._evict(st, ts, "诱多{}回撤{:.1f}%".format(
                    "冲高回落" if TRAP_SPIKE_FADE in st.traps else "高开回落", st.drawdown))
                return
            if TRAP_BREAK_VWAP in st.traps and st.vol_recent < st.vol_base * cfg.vol_decay:
                self._evict(st, ts, "放量跌破均价")
                return
            if vwap10 > 0 and price < vwap10 * cfg.evict_vwap10_tol:
                self._evict(st, ts, "跌破10日VWAP")
                return
            if st.drawdown >= cfg.evict_drawdown:
                self._evict(st, ts, "回撤{:.1f}%".format(st.drawdown))
                return
            vol_decayed = st.vol_recent < st.vol_base * cfg.vol_decay
            if st.stale_bars >= cfg.evict_flat_bars and vol_decayed:
                self._evict(st, ts, "{}根未创新高+量能衰减".format(st.stale_bars))
                return
            if st.stale_bars >= cfg.evict_flat_bars and was != STAGE_WEAKEN:
                st.stage = STAGE_WEAKEN
                return
            if st.stale_bars == 0 and was == STAGE_WEAKEN:
                st.stage = STAGE_HOLD
            return

        # ---- 入局前：只做宽松观察，不因分数低而剔除 ----
        if st.bars < cfg.min_bars:
            return
        if st.evidence_count() < cfg.min_evidence:
            return
        if st.age_min > cfg.watch_expire_min and st.stale_bars >= cfg.evict_flat_bars:
            self._evict(st, ts, "观察{}分钟无新证据".format(int(st.age_min)))
            return
        # 跨日风险：昨日大涨/长上影的票，今天只接"更早的第一波"，不接冲高
        from ats.fusion.trap import TRAP_PREV_DUMP, TRAP_SPIKE_FADE, TRAP_GAP_FADE
        if TRAP_PREV_DUMP in st.traps:
            self._block(st, "前日大涨今日杀跌")
            return
        if st.gap_risk >= cfg.gap_risk_block:
            self._block(st, "跨日风险>=80")
            return
        if TRAP_SPIKE_FADE in st.traps or TRAP_GAP_FADE in st.traps:
            self._block(st, "冲高回落中")
            return   # 正在回落的票不入局，等它重新站住
        if st.gap_risk >= cfg.gap_risk_caution and st.first_pct > 2.0:
            self._block(st, "跨日风险偏高且首异动>2%")
            return
        # 趋同：大家都异口同声了，此时出现的异动多是诱多（实测 T+1 为负）
        if st.consensus >= cfg.consensus_max and st.temp >= cfg.consensus_hot_temp:
            self._block(st, "高温趋同(诱多)")
            return

        if st.persist < cfg.enter_persist:
            return
        if st.efficiency < cfg.enter_eff_min:
            return
        if st.since_first_pct > cfg.enter_max_chase:
            return   # 第一波已经走完，不追
        if vwap10 > 0 and price < vwap10 * cfg.enter_vwap10_tol:
            return   # 10 日 VWAP 是启动确认门槛

        st.stage = STAGE_ENTER
        st.enter_ts = float(ts)
        st.enter_price = float(price)
        st.enter_pct = float(st.last_pct)
        self._events.append(
            {
                "kind": STAGE_ENTER,
                "code": st.code,
                "ts": float(ts),
                "time": time.strftime("%H:%M", time.localtime(int(ts))),
                "price": round(float(price), 3),
                "pct": round(st.last_pct, 2),
                "since_first_pct": round(st.since_first_pct, 2),
                "persist": st.persist,
                "first_time": time.strftime("%H:%M", time.localtime(int(st.first_ts))),
                "first_pct": round(st.first_pct, 2),
                "evidence_n": st.evidence_count(),
                "chain": st.chain(),
                "patterns": dict(st.patterns_seen),
                "best_tier": st.best_tier,
            }
        )

    def _evict(self, st: TrackState, ts: float, reason: str) -> None:
        st.stage = STAGE_EVICT
        st.evict_ts = float(ts)
        st.evict_reason = reason
        self._events.append(
            {
                "kind": STAGE_EVICT,
                "code": st.code,
                "ts": float(ts),
                "time": time.strftime("%H:%M", time.localtime(int(ts))),
                "price": round(st.last_price, 3),
                "pct": round(st.last_pct, 2),
                "reason": reason,
                "post_entry": st.enter_price > 0,
                "enter_pct": round(st.enter_pct, 2),
                "pnl_from_enter": round(
                    (st.last_price / st.enter_price - 1.0) * 100.0, 2
                ) if st.enter_price > 0 else 0.0,
                "chain": st.chain(),
            }
        )


@dataclass
class DeployRule:
    """从"入局"到"可下单"的最后一道闸（阈值由 5 日 T+1 结果校准，见 validate_track）。

    两条路径分开，因为目标不同：
        A 主升延续（当机立断）：必须有"两阳加速"——昨日一根有力度的阳线，今天继续加速。
          实测 答案占比 18%（基准 9%）、T+1 +1.84%、胜率 62%、约 3.4 笔/日。
        B 低风险收敛（观察参与）：必须有"缩量转放量"——极致缩量后第一波放量。
          实测 T+1 +2.50%、胜率 67%，但抓到的榜单票少（5%），属于"能把握"而非"抓牛"。
    """

    theme_rank_min: float = 0.60     # 赛道（概念）强度分位：个股是蓄势，板块才是赛道
    first_pct_max: float = 3.0       # 首异动涨幅上限：第一波，不追
    efficiency_min: float = 0.85     # 想的多回踩的少
    persist_min: float = 55.0        # 量能持续（A 路径）
    safe_persist_min: float = 60.0   # 量能持续（B 路径更严）
    trend_pattern: str = "两阳加速"
    safe_pattern: str = "缩量转放量"
    consensus_max: float = 0.60      # 趋同度超过此值不下单（大家都涨了，跟单容易被埋）
    lead_value_min: float = 0.50     # 带头价值下限（低温低趋同才值钱）


PATH_TREND = "A 主升延续"
PATH_SAFE = "B 低风险收敛"


def deploy_path(entry: Dict[str, Any], rule: Optional[DeployRule] = None) -> str:
    """返回可下单路径；空串表示不下单。"""
    r = rule or DeployRule()
    if entry.get("stage") != STAGE_ENTER:
        return ""
    pats = entry.get("patterns") or {}
    if float(entry.get("theme_rank") or 0.0) < r.theme_rank_min:
        return ""
    if float(entry.get("first_pct") or 0.0) > r.first_pct_max:
        return ""
    if float(entry.get("efficiency") or 0.0) < r.efficiency_min:
        return ""
    if float(entry.get("consensus") or 0.0) >= r.consensus_max:
        return ""
    if float(entry.get("lead_value") or 0.0) < r.lead_value_min:
        return ""
    persist = float(entry.get("persist") or 0.0)
    if r.trend_pattern in pats and persist >= r.persist_min:
        return PATH_TREND
    if r.safe_pattern in pats and persist >= r.safe_persist_min:
        return PATH_SAFE
    return ""


def is_deployable(entry: Dict[str, Any], rule: Optional[DeployRule] = None) -> bool:
    return bool(deploy_path(entry, rule))


def render_deployable(rows: List[Dict[str, Any]], day: str = "", top: int = 10) -> str:
    if not rows:
        return "## 可下单清单 {}｜今日无（宁可不做）\n".format(day)
    lines = ["## 可下单清单 {}（{} 只）".format(day, len(rows)), ""]
    lines.append("| # | 代码 | 入局 | 入局价 | 当时涨幅 | 首异动涨幅 | 持续分 | 赛道 | 概念强度 | 形态 | 证据链 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, e in enumerate(rows[:top], 1):
        lines.append("| {} | {} | {} | {} | {:+.1f}% | {:+.1f}% | {} | {} | {} | {} | {} |".format(
            i, e.get("code", ""), e.get("enter_time", ""), e.get("enter_price", ""),
            float(e.get("enter_pct") or 0), float(e.get("first_pct") or 0), e.get("persist", 0),
            e.get("sector", ""), e.get("theme_rank", 0),
            "、".join((e.get("patterns") or {}).keys()) or "-", (e.get("chain") or "-")[:44]))
    lines.append("")
    return "\n".join(lines)


def render_entries(entries: List[Dict[str, Any]], day: str = "", top: int = 20) -> str:
    """入局清单（这就是"可下单"的输出）。"""
    if not entries:
        return "## 赛马跟踪·第一波入局 {}｜无\n".format(day)
    lines = ["## 赛马跟踪·第一波入局 {}".format(day), ""]
    lines.append("| # | 代码 | 入局 | 入局价 | 当时涨幅 | 首异动 | 首异动涨幅 | 首→入 | 持续分 | 跨日风险 | 证据链 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, e in enumerate(entries[:top], 1):
        t = e.get("enter_time") or e.get("time") or ""
        px = e.get("enter_price") or e.get("price") or 0
        pc = e.get("enter_pct") if e.get("enter_pct") is not None else e.get("pct", 0)
        lines.append(
            "| {} | {} | {} | {} | {:+.1f}% | {} | {:+.1f}% | {:+.1f}% | {} | {} | {} |".format(
                i, e.get("code", ""), t, px, float(pc or 0), e.get("first_time", ""),
                float(e.get("first_pct") or 0), float(e.get("since_first_pct") or 0),
                e.get("persist", 0), e.get("gap_risk", 0), e.get("chain") or "-",
            )
        )
    lines.append("")
    return "\n".join(lines)
