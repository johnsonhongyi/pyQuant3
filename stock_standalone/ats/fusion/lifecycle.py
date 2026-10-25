# -*- coding: utf-8 -*-
"""ats/fusion/lifecycle.py — 先锋队生命周期：谁在进攻、谁在退守。

用户原话：
    "当先锋队阵亡，跟风的就会鸟兽散；组织下一次进攻，直到先锋队全部阵亡，就会退守，
     大盘就会再次温度下降，直到组织下一次反攻。全市场的资金量能的变化就是冲锋号，
     攻城略地还是退避三舍。这就是我们的交易内核。"

这条链把"个股信号"升级成"战役进程"：
    冲锋号（量能放大 + 宽度扩张）
      → 先锋队启动（排头兵 / 夺旗）
        → 跟风扩散（板块内多数票跟上）
          → 先锋阵亡（排头兵跌破 10 日 VWAP / 被剔除）
            → 跟风鸟兽散（板块退潮）
              → 退守（温度下降）
                → 等下一次冲锋号

本模块提供三层：
    VanguardWatch  先锋队名册与存活率（板块级 / 全市场级）
    CapitalGauge   资金量能冲锋号（近 5 根 vs 前 5 根）
    MarketLifecycle 阶段状态机（ATTACK / ADVANCE / VANGUARD_DYING / RETREAT / ICE）

结论只有一个：**当前该进攻还是该退守**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

PHASE_ATTACK = "反攻"
PHASE_ADVANCE = "攻城略地"
PHASE_VANGUARD_DYING = "先锋阵亡"
PHASE_RETREAT = "退守"
PHASE_ICE = "冰点"

# 每个阶段允许的动作
PHASE_ACTION = {
    PHASE_ATTACK: "进攻（可入局，先锋优先）",
    PHASE_ADVANCE: "持有（不追高，只做排头兵）",
    PHASE_VANGUARD_DYING: "只减不加（跟风先撤）",
    PHASE_RETREAT: "退守（禁止入局）",
    PHASE_ICE: "等待（只看不动，等第一枪）",
}

PHASE_ALLOW_ENTRY = {
    PHASE_ATTACK: True,
    PHASE_ADVANCE: True,
    PHASE_VANGUARD_DYING: False,
    PHASE_RETREAT: False,
    PHASE_ICE: True,     # 冰点期允许"第一个启动"，但要求极严（见 tracker 的 gap_risk/hunger）
}


@dataclass
class Vanguard:
    code: str
    sector: str
    ts: float
    price: float
    vwap10: float
    alive: bool = True
    dead_ts: float = 0.0
    dead_reason: str = ""


class VanguardWatch:
    """先锋队名册：谁先动的、现在还活着几个。"""

    def __init__(self, dead_tol: float = 0.985):
        self.dead_tol = float(dead_tol)
        self._by_code: Dict[str, Vanguard] = {}
        self._by_sector: Dict[str, List[str]] = {}

    def reset(self) -> None:
        self._by_code.clear()
        self._by_sector.clear()

    def register(self, code: str, sector: str, ts: float, price: float, vwap10: float) -> None:
        code = str(code).zfill(6)
        if code in self._by_code:
            return
        v = Vanguard(code=code, sector=sector or "", ts=float(ts),
                     price=float(price), vwap10=float(vwap10))
        self._by_code[code] = v
        self._by_sector.setdefault(sector or "", []).append(code)

    def update(self, code: str, price: float, vwap10: float, ts: float = 0.0) -> None:
        v = self._by_code.get(str(code).zfill(6))
        if v is None or not v.alive:
            return
        ref = float(vwap10) if vwap10 > 0 else v.vwap10
        if ref > 0 and float(price) < ref * self.dead_tol:
            v.alive = False
            v.dead_ts = float(ts)
            v.dead_reason = "跌破10日VWAP"

    def survival(self, sector: Optional[str] = None,
                 now: Optional[float] = None, window_s: float = 3600.0) -> Tuple[int, int, float]:
        """返回 (存活数, 总数, 存活率)。sector 为空表示全市场。

        window_s：只看"最近这一波"的先锋（默认 60 分钟）。
        为什么：先锋队是分批上场的。上午那批全灭了，下午新一批上来仍然是进攻；
        如果按全天累计算，上午死光就永远退守，会错过下午的反转（10/23 就是这种日子）。
        """
        codes = self._by_sector.get(sector or "", []) if sector is not None else list(self._by_code)
        if now is not None and window_s > 0:
            codes = [c for c in codes if now - self._by_code[c].ts <= window_s]
        if not codes:
            return 0, 0, 1.0
        alive = sum(1 for c in codes if self._by_code[c].alive)
        return alive, len(codes), alive / max(1, len(codes))

    def dead_recent(self, ts: float, window_s: float = 1800.0) -> List[Vanguard]:
        return [v for v in self._by_code.values()
                if not v.alive and 0 < ts - v.dead_ts <= window_s]

    def alive_codes(self) -> List[str]:
        return [c for c, v in self._by_code.items() if v.alive]


class CapitalGauge:
    """资金量能冲锋号：近 5 根 vs 前 5 根的成交额。

    用户："全市场的资金量能的变化就是冲锋号，攻城略地还是退避三舍。"
    """

    def __init__(self, window: int = 5):
        self.window = int(window)
        self._hist: List[float] = []

    def reset(self) -> None:
        self._hist.clear()

    def update(self, amount: float) -> float:
        self._hist.append(float(amount))
        if len(self._hist) > self.window * 2 + 1:
            self._hist = self._hist[-(self.window * 2 + 1):]
        return self.ratio()

    def ratio(self) -> float:
        w = self.window
        if len(self._hist) < w * 2:
            return 1.0
        recent = sum(self._hist[-w:]) / w
        prev = sum(self._hist[-2 * w:-w]) / w
        if prev <= 0:
            return 1.0
        return recent / prev

    def label(self) -> str:
        r = self.ratio()
        if r >= 1.15:
            return "冲锋号"
        if r <= 0.85:
            return "退避三舍"
        return "常态"


@dataclass
class LifecycleState:
    phase: str = PHASE_ICE
    survival: float = 1.0
    survival_n: int = 0
    capital: float = 1.0
    capital_label: str = "常态"
    temp: float = 50.0
    breadth: float = 0.5
    note: str = ""

    @property
    def allow_entry(self) -> bool:
        return PHASE_ALLOW_ENTRY.get(self.phase, True)

    @property
    def action(self) -> str:
        return PHASE_ACTION.get(self.phase, "")

    def to_dict(self) -> Dict[str, object]:
        return {
            "phase": self.phase, "action": self.action,
            "survival": round(self.survival, 2), "survival_n": self.survival_n,
            "capital": round(self.capital, 2), "capital_label": self.capital_label,
            "temp": round(self.temp, 1), "breadth": round(self.breadth, 3),
            "note": self.note,
        }


class MarketLifecycle:
    """阶段状态机：把温度、宽度、先锋存活率、量能合成一个结论。"""

    def __init__(self, cfg: Optional[Dict[str, float]] = None):
        c = {
            "ice_temp": 35.0,
            "ice_breadth": 0.20,
            "attack_temp": 45.0,
            "retreat_survival": 0.30,
            "dying_survival": 0.55,
            "capital_attack": 1.15,
            "capital_retreat": 0.85,
        }
        c.update(cfg or {})
        self.cfg = c
        self._prev_phase = ""

    def update(
        self,
        temp: float,
        breadth: float,
        survival: float,
        survival_n: int,
        capital: float,
        capital_label: str = "",
    ) -> LifecycleState:
        c = self.cfg
        st = LifecycleState(
            temp=float(temp), breadth=float(breadth), survival=float(survival),
            survival_n=int(survival_n), capital=float(capital),
            capital_label=capital_label or ("冲锋号" if capital >= c["capital_attack"]
                                            else ("退避三舍" if capital <= c["capital_retreat"] else "常态")),
        )

        # 1) 冰点：没量、没宽度、温度低
        if st.temp < c["ice_temp"] and st.breadth <= c["ice_breadth"]:
            st.phase = PHASE_ICE
            st.note = "冰点：等第一枪"
            return st

        # 2) 先锋阵亡：存活率掉下来（哪怕温度还高）
        if st.survival_n >= 3 and st.survival < c["retreat_survival"]:
            st.phase = PHASE_RETREAT
            st.note = "先锋几乎全灭({:.0%})，退守".format(st.survival)
            return st
        if st.survival_n >= 3 and st.survival < c["dying_survival"]:
            st.phase = PHASE_VANGUARD_DYING
            st.note = "先锋阵亡过半({:.0%})，跟风先撤".format(st.survival)
            return st

        # 3) 退守：量能萎缩 + 宽度收缩
        if st.capital <= c["capital_retreat"] and st.breadth < 0.45:
            st.phase = PHASE_RETREAT
            st.note = "量能退避三舍({:.2f})，宽度{:.0%}".format(st.capital, st.breadth)
            return st

        # 4) 反攻：量能放大 + 温度在低位抬升
        if st.capital >= c["capital_attack"] and st.temp < 55.0 and st.breadth >= 0.35:
            st.phase = PHASE_ATTACK
            st.note = "冲锋号({:.2f})，温度{:.0f}℃".format(st.capital, st.temp)
            return st

        # 5) 其余：攻城略地（顺势，但不追高）
        st.phase = PHASE_ADVANCE
        st.note = "攻城略地：顺势持有"
        return st


def render_lifecycle(st: LifecycleState) -> str:
    return "{}｜{}｜先锋存活 {:.0%}（{}只）｜量能 {:.2f} {}｜温度 {:.0f}℃｜宽度 {:.0%}".format(
        st.phase, st.action, st.survival, st.survival_n,
        st.capital, st.capital_label, st.temp, st.breadth,
    )
