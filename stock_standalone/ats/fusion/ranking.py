# -*- coding: utf-8 -*-
"""ats/fusion/ranking.py — 把"四道闸门"从「与」改成「打分排序」。

为什么要改（实测证据，10/19–10/23 全市场闭卷）：
    tracker.deploy_path 是「与」关系：赛道强度 + 首异动涨幅 + 想的多回踩的少
    + 趋同 + 带头价值 + 持续性 + 形态，7 个条件必须同时成立。
    结果是 10/20 全天只剩 3 笔、整周 5 笔——样本内 T+1 反而从 +3.22% 掉到 −2.07%。
    闸门越多不等于越好：每加一道「与」，留下的都是同时踩中所有极端值的票，
    而不是「概率最高」的票。

改法：
    每道闸门不再问「过不过」，而是给一个 0~1 的**存活概率**，
    加权求和成 0~100 的 rank_score，再取前 N（默认 3）。
    这样"宁可不做"由 min_score 下限保证，而不是由条件堆叠保证。

四道闸门（用户指定，全部软化为概率）：
    趋同      consensus 越低越值钱（0~0.30 组 T+1 +2.37%；≥0.60 组 −0.33%）
    跟风      lead_label 决定（冲锋队 −1.98% 最差，比无导向还差）
    阶段      phase 决定（先锋阵亡 +3.94% > 反攻 +2.76% > 冰点 −0.77% > 攻城略地 −1.90%）
    跨日风险  gap_risk 越高越差

另加一条"该不该进"的入场维度（形态/持续性/不追高/回踩少/赛道），但它只做**资格 + 0.10 微调**：
    实测「排头兵不带形态直接下单」是亏的（多出 2 笔 T+1 全负），所以无形态直接不具备资格；
    但反过来，把形态当排序主力也不行——60 个样本里 persist 与"两阳加速"跟 T+1 的相关是
    **负的**（−0.18/−0.16），等于把"已经涨得最漂亮"的票排到最前，正是追高的老毛病。
    领先度是**归因**维度，形态是**资格**维度，两者都不能替代排序。

仍然硬拦的只有"风险底线 + 入场资格"，都不是可调闸门：
    - stage != 入局（没入局就没有下单这件事）
    - first_pct > hard_chase（首异动已涨 6%，那是追高，不是第一波）
    - gap_risk >= hard_gap（跨日风险极值，昨日大涨/长上影，宁可错过）
    - 无形态（require_pattern；领先度是归因维度，不能替代"该不该进"）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 领先度存活概率：按 10/19–10/23 实测 T+1 排序，不是按直觉排序。
# 排头兵 +2.06%/62%｜夺旗 +1.52%｜跟风 +2.71%(n=8，样本太小只给中性)｜
# 无导向 −1.18%｜冲锋队 −1.98%（"半跟不跟"最差）
LEAD_SURV = {
    "排头兵": 1.00,
    "夺旗": 0.85,
    "跟风": 0.45,
    "无导向": 0.55,
    "冲锋队": 0.30,
}
LEAD_SURV_DEFAULT = 0.55

# 阶段存活概率：先锋阵亡期只有最强的能做（所以要看 lead_label），攻城略地最差。
PHASE_SURV = {
    "先锋阵亡": 1.00,
    "反攻": 0.85,
    "冰点": 0.60,
    "退守": 0.45,
    "攻城略地": 0.25,
}
PHASE_SURV_DEFAULT = 0.60

# 先锋阵亡期：非排头兵/夺旗的票，阶段分直接打折（实测该阶段只有最强的那批能赚）
PHASE_VANGUARD_ONLY = 0.30


def _clip01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass
class RankConfig:
    """打分权重与下限。所有权重和为 1.0，改这里就能标定，不必动逻辑。

    权重取值的依据（不是"挑最好看的那一格"，5 天样本挑出来的必然过拟合）：
        - 四道闸门是排序主体，权重近似均分（0.22~0.24），因为它们的实测 T+1 排序
          各自成立（领先度、阶段、趋同都有方向性证据）；
        - "该不该进"只留 0.10 做质量微调，因为它的合成项在 60 个样本上与 T+1
          相关为负（persist/两阳加速 −0.16~−0.18）——它是**资格**，不是排序维度；
        - 形态从权重项改成**资格**（require_pattern）：无形态直接不进清单，
          这就是"排头兵不带形态直接下单是亏的"那条实测结论的可执行形式。
    """

    w_entry: float = 0.10       # 该不该进（形态/持续性/不追高/回踩少/赛道）——只做微调
    w_consensus: float = 0.24   # 趋同
    w_lead: float = 0.22        # 跟风（领先度）
    w_phase: float = 0.24       # 阶段
    w_gap: float = 0.20         # 跨日风险

    min_score: float = 50.0     # 下限：宁可不做。低于此分不进清单
    top_n: int = 5              # 每天最多取前 N。分数区分力弱时，分散比集中安全
    hard_chase: float = 6.0     # 硬追高线：首异动涨幅超过此值，直接否（不是闸门，是底线）
    hard_gap: float = 90.0      # 跨日风险极值，直接否
    require_pattern: bool = True  # 无形态不具备下单资格（C 路径默认关闭）
    # 趋同曲线的两个端点：<=lo 满分，>=hi 零分
    consensus_lo: float = 0.30
    consensus_hi: float = 0.65

    def normalized(self) -> "RankConfig":
        """权重归一化，避免调用方传了不自洽的权重。"""
        s = self.w_entry + self.w_consensus + self.w_lead + self.w_phase + self.w_gap
        if s <= 0:
            return RankConfig()
        if abs(s - 1.0) < 1e-9:
            return self
        c = RankConfig(**{k: getattr(self, k) for k in self.__dataclass_fields__})
        c.w_entry /= s
        c.w_consensus /= s
        c.w_lead /= s
        c.w_phase /= s
        c.w_gap /= s
        return c


# -- 四道闸门 -> 0~1 存活概率 ------------------------------------------------
def surv_consensus(consensus: float, cfg: Optional[RankConfig] = None) -> float:
    """趋同度越低越值钱：0.30 以下满分，0.65 以上零分，中间线性。"""
    c = cfg or RankConfig()
    span = max(1e-6, c.consensus_hi - c.consensus_lo)
    return 1.0 - _clip01((_num(consensus) - c.consensus_lo) / span)


def surv_lead(lead_label: str) -> float:
    """跟风闸门：领先度标签 -> 存活概率。"""
    return LEAD_SURV.get((lead_label or "").strip(), LEAD_SURV_DEFAULT)


def surv_phase(phase: str, lead_label: str = "") -> float:
    """阶段闸门：先锋阵亡期只有排头兵/夺旗能活，其余按阶段表。"""
    p = (phase or "").strip()
    base = PHASE_SURV.get(p, PHASE_SURV_DEFAULT)
    if p == "先锋阵亡" and (lead_label or "").strip() not in ("排头兵", "夺旗"):
        return PHASE_VANGUARD_ONLY
    return base


def surv_gap(gap_risk: float) -> float:
    """跨日风险：0 分满分，60 分剩 0.4，90 分以上接近 0（且硬拦）。"""
    g = _num(gap_risk)
    if g <= 0:
        return 1.0
    if g <= 60:
        return 1.0 - 0.6 * (g / 60.0)
    return max(0.0, 0.4 * (1.0 - (g - 60.0) / 40.0))


def surv_entry(entry: Dict[str, Any]) -> float:
    """该不该进：形态权重最高（无形态的排头兵实测是亏的），其次持续性/不追高。"""
    pats = entry.get("patterns") or {}
    keys = set(pats.keys()) if isinstance(pats, dict) else set(pats or [])
    if keys & {"两阳加速", "缩量转放量"}:
        p_pat = 1.00
    elif keys:
        p_pat = 0.45
    else:
        p_pat = 0.10

    persist = _clip01((_num(entry.get("persist")) - 45.0) / 30.0)     # 45->0, 75->1
    chase = 1.0 - _clip01((_num(entry.get("first_pct")) - 0.5) / 3.5)  # 0.5%->1, 4%->0
    eff = _clip01((_num(entry.get("efficiency"), 0.5) - 0.55) / 0.35)
    theme = _clip01((_num(entry.get("theme_rank")) - 0.45) / 0.35)

    return 0.40 * p_pat + 0.25 * persist + 0.15 * chase + 0.10 * eff + 0.10 * theme


# -- 汇总 -------------------------------------------------------------------
def score_entry(entry: Dict[str, Any], cfg: Optional[RankConfig] = None) -> Dict[str, Any]:
    """给一笔入局打分。返回 {score, parts, ok, reason}。

    ok=False 表示被硬底线拦下（未入局 / 追高 / 跨日风险极值），此时 score 仍给出，
    方便事后复盘"差一点就进了"。
    """
    c = (cfg or RankConfig()).normalized()
    parts = {
        "entry": round(surv_entry(entry), 3),
        "consensus": round(surv_consensus(entry.get("consensus"), c), 3),
        "lead": round(surv_lead(entry.get("lead_label")), 3),
        "phase": round(surv_phase(entry.get("phase"), entry.get("lead_label")), 3),
        "gap": round(surv_gap(entry.get("gap_risk")), 3),
    }
    raw = (
        c.w_entry * parts["entry"]
        + c.w_consensus * parts["consensus"]
        + c.w_lead * parts["lead"]
        + c.w_phase * parts["phase"]
        + c.w_gap * parts["gap"]
    )
    score = round(100.0 * _clip01(raw), 1)

    ok, reason = True, ""
    if str(entry.get("stage") or "") not in ("", "入局"):
        ok, reason = False, "未入局"
    elif _num(entry.get("first_pct")) > c.hard_chase:
        ok, reason = False, "追高(首异动>{:.0f}%)".format(c.hard_chase)
    elif _num(entry.get("gap_risk")) >= c.hard_gap:
        ok, reason = False, "跨日风险极值"
    elif c.require_pattern and not (entry.get("patterns") or {}):
        ok, reason = False, "无形态(无下单资格)"
    return {"score": score, "parts": parts, "ok": ok, "reason": reason}


def explain(res: Dict[str, Any]) -> str:
    """一行可读的归因：为什么是这个分。"""
    p = res.get("parts") or {}
    return "形态{:.2f}/趋同{:.2f}/领先{:.2f}/阶段{:.2f}/跨日{:.2f}".format(
        p.get("entry", 0.0), p.get("consensus", 0.0), p.get("lead", 0.0),
        p.get("phase", 0.0), p.get("gap", 0.0))


def rank_entries(
    entries: List[Dict[str, Any]],
    cfg: Optional[RankConfig] = None,
    top_n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """把入局清单按存活概率排序，取前 N。返回新 dict（不修改入参）。

    排序键：rank_score 降序；同分时用 persist 与 lead_score 做次级排序（稳定可复现）。
    """
    c = (cfg or RankConfig()).normalized()
    n = int(top_n if top_n is not None else c.top_n)
    rows: List[Dict[str, Any]] = []
    for e in entries or []:
        r = dict(e)
        sc = score_entry(r, c)
        r["rank_score"] = sc["score"]
        r["rank_parts"] = sc["parts"]
        r["rank_ok"] = sc["ok"]
        r["rank_reason"] = sc["reason"]
        r["rank_explain"] = explain(sc)
        rows.append(r)

    rows.sort(key=lambda r: (
        -float(r.get("rank_score") or 0.0),
        -float(r.get("persist") or 0.0),
        -float(r.get("lead_score") or 0.0),
        str(r.get("code") or ""),          # 末位键：同分也要可复现，不受入参顺序影响
    ))
    picked = [r for r in rows if r["rank_ok"] and float(r["rank_score"]) >= c.min_score]
    for i, r in enumerate(picked, 1):
        r["rank"] = i
    return picked[:n] if n > 0 else picked


def rank_all(
    entries: List[Dict[str, Any]],
    cfg: Optional[RankConfig] = None,
) -> List[Dict[str, Any]]:
    """只排序不过滤（含被硬拦的），用于复盘与阈值扫描。"""
    c = (cfg or RankConfig()).normalized()
    rows = []
    for e in entries or []:
        r = dict(e)
        sc = score_entry(r, c)
        r["rank_score"] = sc["score"]
        r["rank_parts"] = sc["parts"]
        r["rank_ok"] = sc["ok"]
        r["rank_reason"] = sc["reason"]
        r["rank_explain"] = explain(sc)
        rows.append(r)
    rows.sort(key=lambda r: (
        -float(r.get("rank_score") or 0.0), str(r.get("code") or "")
    ))
    return rows


def render_ranked(rows: List[Dict[str, Any]], day: str = "", top: int = 10) -> str:
    """可下单清单（打分版）：每行都带分数与归因，便于事后核对"为什么是它"。"""
    if not rows:
        return "## 打分排序·可下单 {}｜今日无（分数未达下限，宁可不做）\n".format(day)
    lines = ["## 打分排序·可下单 {}（{} 只）".format(day, len(rows)), ""]
    lines.append("| # | 代码 | 分 | 归因(形态/趋同/领先/阶段/跨日) | 领先度 | 阶段 | 入局 | 入局价 | 当时涨幅 | 持续分 | 形态 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, e in enumerate(rows[:top], 1):
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {:+.1f}% | {} | {} |".format(
            e.get("rank", i), e.get("code", ""), e.get("rank_score", 0),
            e.get("rank_explain", ""), e.get("lead_label", "") or "-", e.get("phase", "") or "-",
            e.get("enter_time", ""), e.get("enter_price", ""),
            _num(e.get("enter_pct")), e.get("persist", 0),
            "、".join((e.get("patterns") or {}).keys()) or "-"))
    lines.append("")
    return "\n".join(lines)
