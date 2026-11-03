# -*- coding: utf-8 -*-
"""ats/fusion/evaluate.py — ATS 梯度信号评估闭环与防泄漏统计。

核心契约（依据 2026-11-03 终稿方案）：
1. 五类顶层互斥分母状态：
   - FILLED_MATURE: 成交并在后续交易日成熟平仓（终结样本）
   - UNFILLED_EXPIRED: 挂单超时未触及买入上限区间（终结样本）
   - UNFILLED_LIMIT_LOCKED: 挂单窗口内因一字涨停无法买入（终结样本）
   - IMMATURE_OPEN: 未到期平仓、日内数据残缺（< 14:57）或次日数据缺失（未终结样本）
   - DATA_INVALID: 行情无效/时间戳未验证/停牌无数据（无效样本）
2. 已终结有效信号净期望收益公式：
   E_resolved[R_net] = sum(r_i_net for i in FILLED_MATURE) / |S_resolved|
   S_resolved = FILLED_MATURE U UNFILLED_EXPIRED U UNFILLED_LIMIT_LOCKED
   未成交已终结样本 r_i_net 计为 0.0%
3. 严格防泄漏截断：
   仅允许使用满足 label_available_ts < t_cutoff 的成熟终结样本
4. 主分组口径：
   按每只票每日首次达到可行动门槛（L2+）时当刻的确定档位（signal_tier / portfolio_tier）互斥评估，
   当日最高档位（Peak Tier）仅作盘后诊断。
5. 按交易日块自助法（Day-Block Bootstrap）：
   按交易日整块重采样，消除截面相关性对置信区间的低估。
6. 样本外（OOS）上线准入门槛检查：
   >= 15 交易日、>= 3 温度阶段、L2/L3/L4 各 >= 50 笔且合计 >= 200 笔成熟样本。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple, Set

import numpy as np

from ats.fusion.trade_sim import Order, Trade

# ---- 常量定义 ----
ROUND_TRIP_COST_PCT = 0.15

STATUS_FILLED_MATURE = "FILLED_MATURE"
STATUS_UNFILLED_EXPIRED = "UNFILLED_EXPIRED"
STATUS_UNFILLED_LIMIT_LOCKED = "UNFILLED_LIMIT_LOCKED"
STATUS_IMMATURE_OPEN = "IMMATURE_OPEN"
STATUS_DATA_INVALID = "DATA_INVALID"

RESOLVED_STATUSES: Set[str] = {
    STATUS_FILLED_MATURE,
    STATUS_UNFILLED_EXPIRED,
    STATUS_UNFILLED_LIMIT_LOCKED,
}

REASON_ZERO_VOLUME = "ZERO_VOLUME"
REASON_SUSPENDED = "SUSPENDED"
REASON_INCOMPLETE_INTRADAY_BARS = "INCOMPLETE_INTRADAY_BARS"
REASON_MISSING_NEXT_DAY_BARS = "MISSING_NEXT_DAY_BARS"
REASON_T1_LIMIT_DOWN_LOCKED = "T1_LIMIT_DOWN_LOCKED"
REASON_UNVERIFIED_TIME = "UNVERIFIED_TIME"
REASON_UNTOUCHED_BAND = "UNTOUCHED_BAND"
REASON_LIMIT_UP_LOCKED = "LIMIT_UP_LOCKED"
REASON_NORMAL_EXIT = "NORMAL_EXIT"


def _day_str(ts: float) -> str:
    if ts <= 0:
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(ts))


# ---- 毛净换算函数 ----
def gross_target_from_net(net_target_pct: float = 3.0, cost_pct: float = ROUND_TRIP_COST_PCT) -> float:
    """由净目标涨幅换算所需的毛涨幅目标。

    例如：基准净目标 +3.00% 对应毛涨幅 +3.15% (即 3.00 + 0.15)
    """
    return round(float(net_target_pct) + float(cost_pct), 4)


def gross_stop_from_net(net_stop_pct: float = -2.0, cost_pct: float = ROUND_TRIP_COST_PCT) -> float:
    """由净止损跌幅换算所需的毛跌幅止损。

    例如：基准净止损 -2.00% 对应毛跌幅 -1.85% (即 -2.00 + 0.15)
    """
    return round(float(net_stop_pct) + float(cost_pct), 4)


# ---- 期望收益与分母统计 ----
def calc_resolved_net_expectancy(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算已终结有效信号净期望收益 E_resolved[R_net]。

    公式：
        E_resolved[R_net] = sum(r_i_net for i in FILLED_MATURE) / |S_resolved|
        其中 S_resolved = FILLED_MATURE U UNFILLED_EXPIRED U UNFILLED_LIMIT_LOCKED
        未成交样本 r_i_net 计为 0.0%
    """
    mature_filled = [r for r in records if r.get("status") == STATUS_FILLED_MATURE]
    unfilled_exp = [r for r in records if r.get("status") == STATUS_UNFILLED_EXPIRED]
    unfilled_lmt = [r for r in records if r.get("status") == STATUS_UNFILLED_LIMIT_LOCKED]
    immature = [r for r in records if r.get("status") == STATUS_IMMATURE_OPEN]
    invalid = [r for r in records if r.get("status") == STATUS_DATA_INVALID]

    s_resolved_len = len(mature_filled) + len(unfilled_exp) + len(unfilled_lmt)
    sum_net_pnl = sum(float(r.get("net_pnl_pct", 0.0)) for r in mature_filled)
    sum_gross_pnl = sum(float(r.get("gross_pnl_pct", 0.0)) for r in mature_filled)

    expectancy = (sum_net_pnl / s_resolved_len) if s_resolved_len > 0 else 0.0
    fill_rate = (len(mature_filled) / s_resolved_len) if s_resolved_len > 0 else 0.0
    mean_net_filled = (sum_net_pnl / len(mature_filled)) if len(mature_filled) > 0 else 0.0
    mean_gross_filled = (sum_gross_pnl / len(mature_filled)) if len(mature_filled) > 0 else 0.0

    total_records = len(records)
    win_count = sum(1 for r in mature_filled if float(r.get("net_pnl_pct", 0.0)) > 0)
    win_rate = (win_count / len(mature_filled)) if len(mature_filled) > 0 else 0.0

    return {
        "total_count": total_records,
        "resolved_count": s_resolved_len,
        "filled_mature_count": len(mature_filled),
        "unfilled_expired_count": len(unfilled_exp),
        "unfilled_limit_locked_count": len(unfilled_lmt),
        "immature_open_count": len(immature),
        "data_invalid_count": len(invalid),
        "immature_rate": round(len(immature) / total_records, 4) if total_records > 0 else 0.0,
        "invalid_rate": round(len(invalid) / total_records, 4) if total_records > 0 else 0.0,
        "fill_rate_resolved": round(fill_rate, 4),
        "win_rate_mature": round(win_rate, 4),
        "mean_gross_pnl_mature": round(mean_gross_filled, 4),
        "mean_net_pnl_mature": round(mean_net_filled, 4),
        "resolved_net_expectancy": round(expectancy, 4),
        "batch_status": "BATCH_PENDING" if len(immature) > 0 else "BATCH_RESOLVED",
    }


# ---- 防泄漏时间截断 ----
def filter_mature_for_training(
    records: List[Dict[str, Any]],
    cutoff_ts: float,
) -> List[Dict[str, Any]]:
    """严格防泄漏截断：仅保留 label_available_ts < cutoff_ts 且属于已终结集合 S_resolved 的样本。"""
    out: List[Dict[str, Any]] = []
    for r in records:
        if r.get("status") not in RESOLVED_STATUSES:
            continue
        avail_ts = float(r.get("label_available_ts") or 0.0)
        if avail_ts > 0 and avail_ts < cutoff_ts:
            out.append(r)
    return out


# ---- 信号评估与标准化 ----
def evaluate_signals(
    orders: List[Order],
    trades: List[Trade],
    decisions: Optional[List[Dict[str, Any]]] = None,
    tier_field: str = "signal_tier",
    bar_granularity: str = "1m",
    round_trip_cost_pct: float = ROUND_TRIP_COST_PCT,
) -> Dict[str, Any]:
    """对模拟器生成的订单与持仓进行标准化多维度评估。

    主分组口径：每只票每日首次达到可行动门槛（L2+）时当刻的确定档位（由 tier_field 决定）。
    """
    # 建立 trade 映射：(code, entry_ts) -> trade
    trade_map: Dict[Tuple[str, float], Trade] = {}
    trade_by_code: Dict[str, List[Trade]] = {}
    for t in trades:
        trade_map[(str(t.code).zfill(6), round(float(t.entry_ts), 1))] = t
        trade_by_code.setdefault(str(t.code).zfill(6), []).append(t)

    # 提取 decisions 信息（首达档位、最高档位、温度阶段）
    first_decisions: Dict[Tuple[str, str], Dict[str, Any]] = {}
    peak_tiers: Dict[Tuple[str, str], int] = {}
    regimes: Dict[Tuple[str, str], str] = {}

    if decisions:
        for d in sorted(decisions, key=lambda x: x.get("ts", 0)):
            raw_tier = int(d.get(tier_field) or d.get("signal_tier") or d.get("portfolio_tier") or d.get("tier") or 0)
            if raw_tier < 2:
                continue
            code = str(d["code"]).zfill(6)
            day = _day_str(float(d.get("ts", 0)))
            key = (code, day)
            if key not in first_decisions:
                first_decisions[key] = d
                peak_tiers[key] = raw_tier
                regimes[key] = str(d.get("market_temp_regime") or d.get("regime") or "NORMAL")
            else:
                peak_tiers[key] = max(peak_tiers[key], raw_tier)

    eval_records: List[Dict[str, Any]] = []

    for o in orders:
        code = str(o.code).zfill(6)
        day = _day_str(float(o.signal_ts))
        key = (code, day)
        d = first_decisions.get(key)

        eval_tier = int(d.get(tier_field) or d.get("signal_tier") or d.get("portfolio_tier") or d.get("tier") or o.tier) if d else o.tier
        peak_tier = peak_tiers.get(key, eval_tier)
        market_regime = regimes.get(key, "NORMAL")

        rec: Dict[str, Any] = {
            "code": code,
            "trade_date": day,
            "signal_ts": o.signal_ts,
            "order_ts": o.order_ts,
            "eval_tier": eval_tier,
            "diagnostic_peak_tier": peak_tier,
            "market_temp_regime": market_regime,
            "bar_granularity": bar_granularity,
            "cost_pct": round_trip_cost_pct,
            "status": STATUS_DATA_INVALID,
            "status_reason": o.status_reason,
            "fill_price": o.fill_price,
            "exit_price": 0.0,
            "exit_reason": "",
            "gross_pnl_pct": 0.0,
            "net_pnl_pct": 0.0,
            "label_end_ts": 0.0,
            "label_available_ts": 0.0,
        }

        if o.status == "UNFILLED_LIMIT_LOCKED":
            rec["status"] = STATUS_UNFILLED_LIMIT_LOCKED
            rec["status_reason"] = o.status_reason or REASON_LIMIT_UP_LOCKED
            rec["label_end_ts"] = o.order_ts or o.signal_ts
            rec["label_available_ts"] = rec["label_end_ts"] + 180.0
        elif o.status == "EXPIRED":
            rec["status"] = STATUS_UNFILLED_EXPIRED
            rec["status_reason"] = o.status_reason or REASON_UNTOUCHED_BAND
            rec["label_end_ts"] = o.order_ts or o.signal_ts
            rec["label_available_ts"] = rec["label_end_ts"] + 180.0
        elif o.status == "NO_DATA":
            rec["status"] = STATUS_DATA_INVALID
            rec["status_reason"] = o.status_reason or REASON_ZERO_VOLUME
        elif o.status == "FILLED":
            # 查找对应 trade
            t = trade_map.get((code, round(float(o.order_ts), 1)))
            if t is None:
                # 兜底按 code 取
                candidates = trade_by_code.get(code, [])
                if candidates:
                    t = candidates[0]
            if t is not None:
                rec["exit_price"] = t.exit_price
                rec["exit_reason"] = t.exit_reason
                rec["gross_pnl_pct"] = t.gross_pnl_pct
                rec["net_pnl_pct"] = t.net_pnl_pct
                rec["label_end_ts"] = t.label_end_ts
                rec["label_available_ts"] = t.label_available_ts
                rec["status_reason"] = t.status_reason

                if t.resolution_status == STATUS_FILLED_MATURE:
                    rec["status"] = STATUS_FILLED_MATURE
                elif t.resolution_status == STATUS_IMMATURE_OPEN:
                    rec["status"] = STATUS_IMMATURE_OPEN
                else:
                    if t.exit_price > 0:
                        rec["status"] = STATUS_FILLED_MATURE
                    else:
                        rec["status"] = STATUS_IMMATURE_OPEN
            else:
                rec["status"] = STATUS_DATA_INVALID
                rec["status_reason"] = "MISSING_TRADE_MATCH"

        eval_records.append(rec)

    # 汇总各档位与全局
    summary_all = calc_resolved_net_expectancy(eval_records)
    by_tier: Dict[str, Dict[str, Any]] = {}
    for tier in (4, 3, 2):
        t_records = [r for r in eval_records if int(r.get("eval_tier") or 0) == tier]
        if t_records:
            by_tier["L{}".format(tier)] = calc_resolved_net_expectancy(t_records)
        else:
            by_tier["L{}".format(tier)] = {"total_count": 0, "resolved_net_expectancy": 0.0}

    # 检查档位单调性：mu_L4 >= mu_L3 >= mu_L2
    exp_l4 = by_tier.get("L4", {}).get("resolved_net_expectancy", 0.0)
    exp_l3 = by_tier.get("L3", {}).get("resolved_net_expectancy", 0.0)
    exp_l2 = by_tier.get("L2", {}).get("resolved_net_expectancy", 0.0)
    monotonic = bool(exp_l4 >= exp_l3 >= exp_l2) if (by_tier.get("L4", {}).get("resolved_count", 0) > 0 and by_tier.get("L3", {}).get("resolved_count", 0) > 0 and by_tier.get("L2", {}).get("resolved_count", 0) > 0) else False

    # 按温度阶段切片
    by_regime: Dict[str, Dict[str, Any]] = {}
    regime_names = sorted(list(set(r.get("market_temp_regime", "NORMAL") for r in eval_records)))
    for reg in regime_names:
        r_records = [r for r in eval_records if r.get("market_temp_regime") == reg]
        by_regime[reg] = calc_resolved_net_expectancy(r_records)

    return {
        "bar_granularity": bar_granularity,
        "cost_pct": round_trip_cost_pct,
        "tier_field": tier_field,
        "summary": summary_all,
        "by_tier": by_tier,
        "by_regime": by_regime,
        "point_estimate_monotonic": monotonic,
        "records": eval_records,
    }


# ---- 按交易日块自助法显著性检验 ----
def day_block_bootstrap_test(
    records: List[Dict[str, Any]],
    n_bootstraps: int = 1000,
    alpha: float = 0.10,
    random_seed: Optional[int] = 42,
    baseline_expectancy: Optional[float] = None,
) -> Dict[str, Any]:
    """按交易日块（Day-Block）自助法显著性检验。

    按日整块重采样，消除截面相关性对置信区间的低估。
    检验两项指标：
    1. L4 - L2 净期望收益差值的 90% 置信区间下界 > 0
    2. 新版本相对基线的净期望收益差值 90% 置信区间下界 >= -0.10%
    """
    if random_seed is not None:
        np.random.seed(random_seed)

    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        day = str(r.get("trade_date") or _day_str(float(r.get("signal_ts", 0))))
        if day:
            by_day.setdefault(day, []).append(r)

    days = sorted(list(by_day.keys()))
    if not days:
        return {"error": "NO_TRADING_DAYS", "n_days": 0}

    n_days = len(days)
    diff_l4_l2_list: List[float] = []
    diff_baseline_list: List[float] = []
    exp_all_list: List[float] = []
    exp_l4_list: List[float] = []
    exp_l3_list: List[float] = []
    exp_l2_list: List[float] = []

    for _ in range(n_bootstraps):
        sampled_day_idx = np.random.choice(n_days, size=n_days, replace=True)
        sampled_records: List[Dict[str, Any]] = []
        for idx in sampled_day_idx:
            sampled_records.extend(by_day[days[idx]])

        s_all = calc_resolved_net_expectancy(sampled_records)
        rec_l4 = [r for r in sampled_records if int(r.get("eval_tier") or 0) == 4]
        rec_l3 = [r for r in sampled_records if int(r.get("eval_tier") or 0) == 3]
        rec_l2 = [r for r in sampled_records if int(r.get("eval_tier") or 0) == 2]

        s_l4 = calc_resolved_net_expectancy(rec_l4)
        s_l3 = calc_resolved_net_expectancy(rec_l3)
        s_l2 = calc_resolved_net_expectancy(rec_l2)

        exp_all = s_all["resolved_net_expectancy"]
        exp_l4 = s_l4["resolved_net_expectancy"]
        exp_l3 = s_l3["resolved_net_expectancy"]
        exp_l2 = s_l2["resolved_net_expectancy"]

        exp_all_list.append(exp_all)
        exp_l4_list.append(exp_l4)
        exp_l3_list.append(exp_l3)
        exp_l2_list.append(exp_l2)

        diff_l4_l2_list.append(exp_l4 - exp_l2)
        if baseline_expectancy is not None:
            diff_baseline_list.append(exp_all - baseline_expectancy)

    diff_arr = np.array(diff_l4_l2_list)
    ci_5 = float(np.percentile(diff_arr, 5.0))
    ci_10 = float(np.percentile(diff_arr, 10.0))
    ci_90 = float(np.percentile(diff_arr, 90.0))
    ci_95 = float(np.percentile(diff_arr, 95.0))

    res: Dict[str, Any] = {
        "n_bootstraps": n_bootstraps,
        "n_days": n_days,
        "l4_minus_l2_mean": round(float(np.mean(diff_arr)), 4),
        "l4_minus_l2_ci_90_lower": round(ci_10, 4),  # 单侧 90% 下界
        "l4_minus_l2_ci_90_lower_2sided": round(ci_5, 4),  # 双侧 90% 下界 (5%)
        "l4_minus_l2_ci_upper": round(ci_90, 4),
        "l4_minus_l2_passed": bool(ci_10 > 0.0),
        "expectancy_by_tier_mean": {
            "L4": round(float(np.mean(exp_l4_list)), 4),
            "L3": round(float(np.mean(exp_l3_list)), 4),
            "L2": round(float(np.mean(exp_l2_list)), 4),
        },
    }

    if baseline_expectancy is not None and diff_baseline_list:
        base_arr = np.array(diff_baseline_list)
        base_ci_10 = float(np.percentile(base_arr, 10.0))
        base_passed = base_ci_10 >= -0.10
        res["baseline_diff_mean"] = round(float(np.mean(base_arr)), 4)
        res["baseline_diff_ci_90_lower"] = round(base_ci_10, 4)
        res["baseline_passed"] = bool(base_passed)

    return res


# ---- 样本外 (OOS) 上线准入门槛检查 ----
def check_oos_admission_gate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """检查样本外 (OOS) 上线准入门槛：

    1. >= 15 个完整交易日；
    2. 覆盖 >= 3 类温度阶段；
    3. 各可行动档位（L2/L3/L4）独立 FILLED_MATURE 样本各 >= 50 笔；
    4. 且 FILLED_MATURE 总笔数 >= 200 笔。
    """
    days = set()
    regimes = set()
    tier_mature_counts = {2: 0, 3: 0, 4: 0}
    total_mature = 0

    for r in records:
        if r.get("trade_date"):
            days.add(r["trade_date"])
        if r.get("market_temp_regime"):
            regimes.add(r["market_temp_regime"])
        if r.get("status") == STATUS_FILLED_MATURE:
            total_mature += 1
            t = int(r.get("eval_tier") or 0)
            if t in tier_mature_counts:
                tier_mature_counts[t] += 1

    days_passed = len(days) >= 15
    regimes_passed = len(regimes) >= 3
    tiers_passed = all(tier_mature_counts[t] >= 50 for t in (2, 3, 4))
    total_passed = total_mature >= 200

    unmet = []
    if not days_passed:
        unmet.append("交易日不足15日(当前: {})".format(len(days)))
    if not regimes_passed:
        unmet.append("温度阶段不足3类(当前: {})".format(len(regimes)))
    if not tiers_passed:
        unmet.append("L2/L3/L4各档成熟样本不足50笔(当前: L2={}, L3={}, L4={})".format(
            tier_mature_counts[2], tier_mature_counts[3], tier_mature_counts[4]
        ))
    if not total_passed:
        unmet.append("成熟样本总量不足200笔(当前: {})".format(total_mature))

    return {
        "passed": bool(days_passed and regimes_passed and tiers_passed and total_passed),
        "days_count": len(days),
        "days_passed": days_passed,
        "regimes_count": len(regimes),
        "regimes_passed": regimes_passed,
        "tier_mature_counts": {"L{}".format(t): tier_mature_counts[t] for t in (2, 3, 4)},
        "tiers_passed": tiers_passed,
        "total_mature": total_mature,
        "total_passed": total_passed,
        "unmet_reasons": unmet,
    }


# ---- 报告生成与渲染 ----
def format_evaluation_report(eval_res: Dict[str, Any], bootstrap_res: Optional[Dict[str, Any]] = None) -> str:
    """渲染标准化 Markdown 评估报表。"""
    lines = [
        "# ATS 梯度信号评估报告（{} 粒度）".format(eval_res.get("bar_granularity", "1m")),
        "",
        "- 往返总成本契约: `cost_pct = {}%` (15 bps)".format(eval_res.get("cost_pct", 0.15)),
        "- 档位评估基准字段: `{}`".format(eval_res.get("tier_field", "signal_tier")),
        "- 批次状态: `{}`".format(eval_res.get("summary", {}).get("batch_status", "-")),
        "- 点估计单调性 (L4 >= L3 >= L2): `{}`".format("通过" if eval_res.get("point_estimate_monotonic") else "未通过/样本不足"),
        "",
        "## 1. 分档已终结净期望收益（S_resolved 闭环）",
        "",
        "| 档位 | 样本总数 | 成交成熟 | 超时未成交 | 涨停买不进 | 未终结 | 无效 | 填充率 | 胜率 | 平均净收益 | 净期望收益 E[R_net] |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def _format_row(name: str, s: Dict[str, Any]) -> str:
        return "| {} | {} | {} | {} | {} | {} | {} | {:.1%} | {:.1%} | {}% | **{}%** |".format(
            name,
            s.get("total_count", 0),
            s.get("filled_mature_count", 0),
            s.get("unfilled_expired_count", 0),
            s.get("unfilled_limit_locked_count", 0),
            s.get("immature_open_count", 0),
            s.get("data_invalid_count", 0),
            s.get("fill_rate_resolved", 0.0),
            s.get("win_rate_mature", 0.0),
            s.get("mean_net_pnl_mature", 0.0),
            s.get("resolved_net_expectancy", 0.0),
        )

    lines.append(_format_row("全部 (L2+)", eval_res.get("summary", {})))
    by_tier = eval_res.get("by_tier", {})
    for t in ("L4", "L3", "L2"):
        if t in by_tier:
            lines.append(_format_row(t, by_tier[t]))

    lines.append("")
    lines.append("## 2. 市场温度阶段细分")
    lines.append("")
    lines.append("| 温度阶段 | 样本总数 | 成交成熟 | 填充率 | 胜率 | 净期望收益 E[R_net] |")
    lines.append("|---|---|---|---|---|---|")
    for reg, s in eval_res.get("by_regime", {}).items():
        lines.append(
            "| {} | {} | {} | {:.1%} | {:.1%} | **{}%** |".format(
                reg, s.get("total_count", 0), s.get("filled_mature_count", 0),
                s.get("fill_rate_resolved", 0.0), s.get("win_rate_mature", 0.0),
                s.get("resolved_net_expectancy", 0.0),
            )
        )

    if bootstrap_res:
        lines.append("")
        lines.append("## 3. 按交易日块自助法显著性检验（Day-Block Bootstrap）")
        lines.append("")
        lines.append("- 重采样交易日数: `{}`｜重采样次数: `{}`".format(bootstrap_res.get("n_days", 0), bootstrap_res.get("n_bootstraps", 0)))
        lines.append("- L4 - L2 净期望收益差值均值: `{}%`".format(bootstrap_res.get("l4_minus_l2_mean", 0.0)))
        lines.append("- L4 - L2 90% 置信区间单侧下界: `{}%` (门禁要求 > 0: `{}`)".format(
            bootstrap_res.get("l4_minus_l2_ci_90_lower", 0.0),
            "PASS" if bootstrap_res.get("l4_minus_l2_passed") else "FAIL",
        ))
        if "baseline_passed" in bootstrap_res:
            lines.append("- 相对基线版本差值 90% 置信区间下界: `{}%` (门禁要求 >= -0.10%: `{}`)".format(
                bootstrap_res.get("baseline_diff_ci_90_lower", 0.0),
                "PASS" if bootstrap_res.get("baseline_passed") else "FAIL",
            ))

    return "\n".join(lines)
