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

    # -- 生命周期 -----------------------------------------------------------
    def get(self, code: str) -> Optional[TrackState]:
        return self._states.get(str(code).zfill(6))

    def states(self) -> List[TrackState]:
        return list(self._states.values())

    def events(self) -> List[Dict[str, Any]]:
        return list(self._events)

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

        patterns = list(patterns or [])
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

        # 5) 阶段推进
        self._advance(st, price, vwap10, ts)
        return st

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
        return round(100.0 * _clip01(score), 1)

    def _advance(self, st: TrackState, price: float, vwap10: float, ts: float) -> None:
        cfg = self.cfg
        was = st.stage

        # 已剔除：不再回头（当日）
        if was == STAGE_EVICT:
            return

        if was in (STAGE_ENTER, STAGE_HOLD, STAGE_WEAKEN):
            # ---- 入局之后才开始剔除 ----
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
    lines.append("| # | 代码 | 入局 | 入局价 | 当时涨幅 | 首异动 | 首异动涨幅 | 首→入 | 持续分 | 证据 | 证据链 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, e in enumerate(entries[:top], 1):
        t = e.get("enter_time") or e.get("time") or ""
        px = e.get("enter_price") or e.get("price") or 0
        pc = e.get("enter_pct") if e.get("enter_pct") is not None else e.get("pct", 0)
        lines.append(
            "| {} | {} | {} | {} | {:+.1f}% | {} | {:+.1f}% | {:+.1f}% | {} | {} | {} |".format(
                i, e.get("code", ""), t, px, float(pc or 0), e.get("first_time", ""),
                float(e.get("first_pct") or 0), float(e.get("since_first_pct") or 0),
                e.get("persist", 0), e.get("evidence_n", 0), e.get("chain") or "-",
            )
        )
    lines.append("")
    return "\n".join(lines)
