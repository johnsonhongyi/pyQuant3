# -*- coding: utf-8 -*-
"""
ats/premarket_profile.py
========================
时序信号引擎 —— L0 盘前身份层

设计要点（对应 docs/tasks/2026-10-20_2045_ATS时序可交易信号引擎落地方案.md §4 L0、§7.2）：

DFall 宽表里数百个"盘前预处理策略基数"（ch_slope_deg / ch_supp_pos / dff2 / resist_today /
support_today / bullbreak / TrendS / structure_base_score ...）盘中基本不变，
它们是**先验身份**，不是**瞬时行情**。

本模块只做一件事：把这几百列压成一个紧凑、可解释、可过滤的 ``PreMarketProfile``，
供盘中时间轴回答"现在是不是时机"——而不是让"瞬时涨幅"去污染"身份判断"。

核心原则：
- 盘前定身份（值不值得盯 / 触发线在哪 / 防守线在哪 / 波动预算多大）
- 盘中定时机（是否突破 / 是否站稳 / 是否该退）
- 两者不互相覆盖

本模块纯计算、无 IO、无线程、无 Qt 依赖，可独立单测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ats.signal_state_machine import SignalParams

__all__ = [
    "StructureClass",
    "STRUCTURE_CLASS_LABELS",
    "GATE_PASS",
    "GATE_WATCH",
    "GATE_REJECT",
    "PreMarketProfile",
    "build_profiles",
]


GATE_PASS = "PASS"
GATE_WATCH = "WATCH"
GATE_REJECT = "REJECT"

GATE_LABELS = {
    GATE_PASS: "✅ 通过",
    GATE_WATCH: "👀 观察",
    GATE_REJECT: "🚫 剔除",
}


class StructureClass(str, Enum):
    """盘前结构身份（与盘中 HH/HL 结构轴是两回事：一个是先验，一个是实时）。"""

    BREAKOUT_BASE = "BREAKOUT_BASE"   # 突破底座：贴近前高、斜率向上
    CHANNEL_UP = "CHANNEL_UP"         # 上升通道：通道上下轨同向抬升
    REVERSAL = "REVERSAL"             # 低位反转：连续杀跌后企稳
    RANGE = "RANGE"                   # 震荡：无明确方向
    WEAK_DOWN = "WEAK_DOWN"           # 弱势下行：通道向下、动能转负


STRUCTURE_CLASS_LABELS: Dict[str, str] = {
    StructureClass.BREAKOUT_BASE.value: "🚀 突破底座",
    StructureClass.CHANNEL_UP.value: "📈 上升通道",
    StructureClass.REVERSAL.value: "🔄 低位反转",
    StructureClass.RANGE.value: "↔ 区间震荡",
    StructureClass.WEAK_DOWN.value: "📉 弱势下行",
}

_STRUCT_SCORE = {
    StructureClass.BREAKOUT_BASE.value: 40.0,
    StructureClass.CHANNEL_UP.value: 36.0,
    StructureClass.REVERSAL.value: 30.0,
    StructureClass.RANGE.value: 22.0,
    StructureClass.WEAK_DOWN.value: 8.0,
}

_BOARD_20CM_PREFIX = ("688", "689", "300", "301", "302", "920", "83", "87", "43")


# ---------------------------------------------------------------------------
# 取值工具
# ---------------------------------------------------------------------------
def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _get(row: Any, keys: Sequence[str], default: float = 0.0,
         positive: bool = False) -> float:
    """按候选列名依次取值；``positive=True`` 时把 0/负值视为缺失继续往下找。"""
    for k in keys:
        val = None
        try:
            val = row[k]
        except Exception:
            try:
                val = row.get(k)  # type: ignore[attr-defined]
            except Exception:
                val = None
        f = _to_float(val)
        if f is None:
            continue
        if positive and f <= 0.0:
            continue
        return f
    return default


def _board_limit(code: str) -> float:
    c = str(code or "").strip()
    for p in _BOARD_20CM_PREFIX:
        if c.startswith(p):
            return 20.0
    return 10.0


# ---------------------------------------------------------------------------
# 身份画像
# ---------------------------------------------------------------------------
@dataclass
class PreMarketProfile:
    """单只股票的盘前身份。盘中不再改动，只读。"""

    code: str
    name: str = ""
    structure_class: str = StructureClass.RANGE.value
    vol_budget_pct: float = 3.0          # 日内正常波动幅度（%），由多日振幅中位数估
    trigger_line: float = 0.0            # 触发线：突破即考虑进场
    defend_line: float = 0.0             # 防守线：跌破即结构失效
    space_pct: float = 6.0               # 到空间上限的距离（%）
    prior_score: float = 0.0             # 先验分 0~100
    gate: str = GATE_WATCH
    gate_reason: str = ""
    board_limit_pct: float = 10.0
    # 关键基数快照（便于 UI 解释与 P3 分组统计）
    dff2: float = 0.0
    dff3: float = 0.0
    ch_supp_slope: float = 0.0
    ch_supp_pos: float = 0.0
    ch_slope_deg: float = 0.0
    trend_s: float = 0.0
    structure_base_score: float = 0.0
    win: float = 0.0
    power_idx: float = 0.0
    obs_d: float = 0.0
    trigger_params: SignalParams = field(default_factory=SignalParams)

    # -- 展示 ---------------------------------------------------------------
    @property
    def structure_label(self) -> str:
        return STRUCTURE_CLASS_LABELS.get(self.structure_class, self.structure_class)

    @property
    def gate_label(self) -> str:
        return GATE_LABELS.get(self.gate, self.gate)

    @property
    def is_tradable_candidate(self) -> bool:
        return self.gate != GATE_REJECT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "structure_class": self.structure_class,
            "structure_label": self.structure_label,
            "vol_budget_pct": round(self.vol_budget_pct, 2),
            "trigger_line": round(self.trigger_line, 3),
            "defend_line": round(self.defend_line, 3),
            "space_pct": round(self.space_pct, 2),
            "prior_score": round(self.prior_score, 1),
            "gate": self.gate,
            "gate_label": self.gate_label,
            "gate_reason": self.gate_reason,
            "board_limit_pct": self.board_limit_pct,
            "dff2": round(self.dff2, 2),
            "dff3": round(self.dff3, 2),
            "ch_supp_slope": round(self.ch_supp_slope, 3),
            "ch_supp_pos": round(self.ch_supp_pos, 3),
            "ch_slope_deg": round(self.ch_slope_deg, 2),
            "trend_s": round(self.trend_s, 2),
            "structure_base_score": round(self.structure_base_score, 1),
            "win": round(self.win, 1),
            "power_idx": round(self.power_idx, 2),
            "obs_d": round(self.obs_d, 2),
            "trigger_params": {
                "trigger_pct_thresh": self.trigger_params.trigger_pct_thresh,
                "trigger_vol_thresh": self.trigger_params.trigger_vol_thresh,
                "accel_pct_thresh": self.trigger_params.accel_pct_thresh,
            },
        }

    # -- 构建 ---------------------------------------------------------------
    @classmethod
    def from_row(cls, row: Any, code: Optional[str] = None,
                 name: Optional[str] = None,
                 base_params: Optional[SignalParams] = None) -> "PreMarketProfile":
        """从 DFall 宽表的一行（dict / pandas.Series / 任意支持 [] 的对象）构建身份。"""
        raw_code = str(code or _get_str(row, ("code", "代码"), "")).strip()
        c = raw_code.zfill(6) if raw_code.isdigit() else raw_code
        nm = str(name if name is not None else _get_str(row, ("name", "名称"), "")).strip()

        close = _get(row, ("trade", "price", "close", "nclose"), 0.0, positive=True)

        # ---- 波动预算：多日振幅中位数 ----
        vol_budget = _estimate_vol_budget(row)
        if vol_budget <= 0.0:
            vol_budget = 3.0

        # ---- 触发线 / 防守线 / 空间 ----
        nhigh = _get(row, ("nhigh", "lasth1d", "max5"), 0.0, positive=True)
        nlow = _get(row, ("nlow", "lastl1d", "min5"), 0.0, positive=True)
        resist_today = _get(row, ("resist_today", "resist_next"), 0.0, positive=True)
        support_today = _get(row, ("support_today", "support_next"), 0.0, positive=True)
        ptop = _get(row, ("ptop", "MainU"), 0.0, positive=True)

        raw_trigger = resist_today or nhigh or (close * 1.02 if close > 0 else 0.0)
        # 触发线不得低于当前价：若盘前已站上阻力，把触发线抬到当前价上方 0.2%。
        # 否则 (trigger - price) 恒为负，状态机永远进不了 ARMED，高开突破会全天无信号。
        trigger_line = max(raw_trigger, close * 1.002) if close > 0 else raw_trigger
        defend_line = support_today or nlow or (close * 0.97 if close > 0 else 0.0)

        space_pct = 6.0
        if close > 0:
            if ptop > close:
                space_pct = (ptop - close) / close * 100.0
            elif trigger_line > close:
                space_pct = (trigger_line - close) / close * 100.0 + 4.0

        # ---- 关键基数 ----
        dff2 = _get(row, ("dff2", "DFF2"), 0.0)
        dff3 = _get(row, ("dff3", "DFF3"), 0.0)
        ch_supp_slope = _get(row, ("ch_supp_slope",), 0.0)
        ch_supp_pos = _get(row, ("ch_supp_pos",), 0.5)
        ch_slope_deg = _get(row, ("ch_slope_deg", "ch_slope"), 0.0)
        trend_s = _get(row, ("TrendS", "trend_s"), 0.0)
        struct_base = _get(row, ("structure_base_score",), 0.0)
        win = _get(row, ("win",), 0.0)
        power_idx = _get(row, ("power_idx",), 0.0)
        obs_d = _get(row, ("obs_d",), 0.0)
        bullbreak = _get(row, ("bullbreak",), 0.0)

        # ---- 结构身份 ----
        sclass = _classify_structure(
            close=close, nhigh=nhigh, ch_slope_deg=ch_slope_deg,
            ch_supp_slope=ch_supp_slope, ch_supp_pos=ch_supp_pos,
            trend_s=trend_s, dff2=dff2, dff3=dff3, bullbreak=bullbreak,
        )

        # ---- 先验分：结构 40 + 动能 35 + 位置 25 ----
        struct_score = _STRUCT_SCORE.get(sclass, 22.0)
        if struct_base > 0:
            # DFall 自带的底座分参与加权（0~100 → 0~40）
            struct_score = struct_score * 0.6 + min(100.0, struct_base) * 0.4

        mom_score = _momentum_score(dff2, dff3, win, power_idx)
        pos_score = _position_score(space_pct, close, trigger_line, vol_budget)
        prior = max(0.0, min(100.0, struct_score + mom_score + pos_score))

        # ---- 门禁 ----
        gate, reason = _gate(sclass, prior, vol_budget, space_pct, dff2, close, obs_d)

        board = _board_limit(c)
        params = (base_params or SignalParams()).derive_for(vol_budget, board)

        return cls(
            code=c, name=nm, structure_class=sclass,
            vol_budget_pct=round(vol_budget, 2),
            trigger_line=round(trigger_line, 3),
            defend_line=round(defend_line, 3),
            space_pct=round(space_pct, 2),
            prior_score=round(prior, 1),
            gate=gate, gate_reason=reason,
            board_limit_pct=board,
            dff2=dff2, dff3=dff3,
            ch_supp_slope=ch_supp_slope, ch_supp_pos=ch_supp_pos,
            ch_slope_deg=ch_slope_deg, trend_s=trend_s,
            structure_base_score=struct_base,
            win=win, power_idx=power_idx, obs_d=obs_d,
            trigger_params=params,
        )


# ---------------------------------------------------------------------------
# 内部计算
# ---------------------------------------------------------------------------
def _get_str(row: Any, keys: Sequence[str], default: str = "") -> str:
    for k in keys:
        try:
            v = row[k]
        except Exception:
            try:
                v = row.get(k)  # type: ignore[attr-defined]
            except Exception:
                v = None
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return default


def _estimate_vol_budget(row: Any, max_days: int = 5) -> float:
    """用最近若干日 (高-低)/收 的中位数估日内波动预算（%）。"""
    samples: List[float] = []
    for i in range(1, max_days + 1):
        h = _get(row, ("lasth%dd" % i,), 0.0, positive=True)
        l = _get(row, ("lastl%dd" % i,), 0.0, positive=True)
        p = _get(row, ("lastp%dd" % i,), 0.0, positive=True)
        if h > 0 and l > 0 and p > 0 and h >= l:
            samples.append((h - l) / p * 100.0)
    if samples:
        samples.sort()
        mid = len(samples) // 2
        if len(samples) % 2 == 1:
            return samples[mid]
        return (samples[mid - 1] + samples[mid]) / 2.0

    # 退化：用 nhigh/nlow/nclose 单日振幅
    h = _get(row, ("nhigh",), 0.0, positive=True)
    l = _get(row, ("nlow",), 0.0, positive=True)
    p = _get(row, ("nclose", "trade"), 0.0, positive=True)
    if h > 0 and l > 0 and p > 0 and h >= l:
        return (h - l) / p * 100.0
    return 0.0


def _classify_structure(close: float, nhigh: float, ch_slope_deg: float,
                        ch_supp_slope: float, ch_supp_pos: float,
                        trend_s: float, dff2: float, dff3: float,
                        bullbreak: float) -> str:
    """盘前结构分类（先验，不是盘中 HH/HL）。"""
    near_high = bool(close > 0 and nhigh > 0 and close >= nhigh * 0.995)

    if trend_s < 0 and ch_slope_deg < -3.0 and dff2 < 0:
        return StructureClass.WEAK_DOWN.value
    if bullbreak > 0 or (near_high and ch_slope_deg >= 0):
        return StructureClass.BREAKOUT_BASE.value
    if ch_slope_deg > 0 and ch_supp_slope > 0 and ch_supp_pos >= 0.5:
        return StructureClass.CHANNEL_UP.value
    if dff2 < 0 and dff3 < 0 and ch_supp_pos <= 0.35:
        return StructureClass.REVERSAL.value
    return StructureClass.RANGE.value


def _momentum_score(dff2: float, dff3: float, win: float, power_idx: float) -> float:
    """动能分 0~35：dff2/dff3 为主，连阳与爆发力微调。"""
    base = (max(-10.0, min(10.0, dff2)) + 10.0) / 20.0 * 22.0      # 0~22
    base += (max(-10.0, min(10.0, dff3)) + 10.0) / 20.0 * 8.0      # 0~8
    base += max(0.0, min(5.0, win)) * 0.6                          # 0~3
    base += max(0.0, min(5.0, power_idx)) * 0.4                    # 0~2
    return max(0.0, min(35.0, base))


def _position_score(space_pct: float, close: float, trigger_line: float,
                    vol_budget: float) -> float:
    """位置分 0~25：空间越大越好，但"离触发线过远"要扣分（避免追不动）。"""
    score = max(0.0, min(15.0, space_pct / 10.0 * 15.0))
    if close > 0 and trigger_line > 0:
        dist_pct = (trigger_line - close) / close * 100.0
        if dist_pct <= 0:
            score += 0.0          # 已突破，不加分也不罚（避免追高）
        elif dist_pct <= vol_budget:
            score += 10.0         # 一步之遥，最佳
        elif dist_pct <= vol_budget * 2:
            score += 5.0
    return max(0.0, min(25.0, score))


def _gate(sclass: str, prior: float, vol_budget: float, space_pct: float,
          dff2: float, close: float, obs_d: float) -> Tuple[str, str]:
    """盘前门禁：决定这只股票要不要进盘中时间轴。"""
    if close <= 0:
        return GATE_REJECT, "无有效价格"
    if vol_budget > 12.0:
        return GATE_REJECT, "波动预算 %.1f%% 过大，日内不可控" % vol_budget
    if sclass == StructureClass.WEAK_DOWN.value and dff2 < -3.0:
        return GATE_REJECT, "弱势下行且动能转负(dff2=%.1f)" % dff2
    if space_pct < 1.0:
        return GATE_REJECT, "到空间上限仅 %.1f%%，无盈亏比" % space_pct
    if obs_d > 0 and prior < 45.0:
        return GATE_REJECT, "风险标记 obs_d=%.1f 且先验分不足" % obs_d
    if prior < 55.0:
        return GATE_WATCH, "先验分 %.1f 偏低，仅观察" % prior
    return GATE_PASS, "先验分 %.1f，结构%s" % (prior, STRUCTURE_CLASS_LABELS.get(sclass, sclass))


def build_profiles(rows: Iterable[Any], code_key: str = "code",
                   name_key: str = "name",
                   base_params: Optional[SignalParams] = None) -> Dict[str, PreMarketProfile]:
    """批量构建身份画像，返回 ``code -> PreMarketProfile``。

    盘前调用一次即可；盘中若 DFall 300s 刷新，可增量覆盖（先验变化极慢）。
    """
    out: Dict[str, PreMarketProfile] = {}
    for row in rows:
        code = _get_str(row, (code_key, "code"), "")
        if not code:
            continue
        name = _get_str(row, (name_key, "name"), "")
        try:
            prof = PreMarketProfile.from_row(row, code=code, name=name, base_params=base_params)
        except Exception:
            continue
        out[prof.code] = prof
    return out
