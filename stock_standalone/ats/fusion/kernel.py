# -*- coding: utf-8 -*-
"""ats/fusion/kernel.py — 融合层统一决策内核与确定性复算引擎。

职责边界：
    1. 前置数据卫生门禁：在更新任何时序状态机前拦截脏数据，防止污染。
    2. L1a 单条无状态确定性复算：从无损事件快照 100% 精确复算单票档位与计划。
    3. L1b 序列与组合确定性复算：按时间序列驱动 FusionBus 重平衡，支持断号与截断审计。
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from ats.fusion.adapter import is_data_hygiene_ok, today_str
from ats.fusion.anomaly import (
    PATTERN_BOX10_VWAP_HOVER,
    PATTERN_STRUCTURE_CONFIRM,
)
from ats.fusion.contract import FusionDecision, SignalEvent
from ats.fusion.engine import FusionBus, FusionEngine
from ats.fusion.regime import MarketRegime
from ats.fusion.structure_timeline import (
    STATUS_BROKEN,
    STATUS_EVICTED,
)
from ats.fusion.vanguard import (
    LABEL_FLAG,
    LABEL_FOLLOW,
    LABEL_PRIME,
    LABEL_STRIKE,
    LABEL_VANGUARD,
)

logger = logging.getLogger(__name__)


def check_data_hygiene(
    event: SignalEvent,
    expected_day: str = "",
    stale_seconds: float = 20.0,
    require_verified: bool = False,
) -> Tuple[bool, str]:
    """前置数据卫生门禁。

    拦截规则：
    - price <= 0 或 vwap <= 0
    - "pct" in missing (涨跌幅或昨收缺失)
    - freshness_s > stale_seconds (数据过期)
    - expected_day != "" 且 trade_date != expected_day (跨交易日)
    - require_verified 时拦截未经验证的 ts 或 trade_date 来源

    返回: (passed: bool, reason: str)
    """
    return is_data_hygiene_ok(
        event=event,
        expected_day=expected_day,
        stale_seconds=stale_seconds,
        require_verified_source=require_verified,
    )


def compute_config_fingerprint(cfg: Dict[str, Any]) -> str:
    """计算配置核心关键字段的指纹摘要。"""
    try:
        keys_to_hash = {
            "weights": cfg.get("weights"),
            "tier_cuts": cfg.get("tier_cuts"),
            "veto": cfg.get("veto"),
            "penalty": cfg.get("penalty"),
            "temp_matrix": cfg.get("temp_matrix"),
            "age_table": cfg.get("age_table"),
            "max_single_size_pct": cfg.get("max_single_size_pct"),
            "max_struct_floor_tier": cfg.get("max_struct_floor_tier"),
            "exempt_temp_cap_on_struct": cfg.get("exempt_temp_cap_on_struct"),
        }
        raw_str = json.dumps(keys_to_hash, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw_str.encode("utf-8")).hexdigest()[:12]
    except Exception:
        return "default"


def resolve_prime_leader(
    code: str,
    sector: str,
    prev_strong: bool,
    today_strong: bool,
    raw_lead_label: str,
    lead_gap_min: float,
    prime_leader_by_sector: Dict[str, str],
    lock: Any = None,
) -> Tuple[bool, str]:
    """共用总龙头判定与板块唯一占位逻辑。

    规则：
    1. 前置条件：昨日强均价 (prev_strong) 且今日维持强势 (today_strong)；
    2. 领先位置：处于先锋/领头旗或落后首动 <= 5 分钟，且不能是跟风或冲锋队；
    3. 板块唯一性：若有板块，则每个板块竞争同一占位名额（线程安全可配 lock）。

    返回: (is_prime: bool, final_lead_label: str)
    """
    is_prime = False
    if prev_strong and today_strong:
        is_front = (
            (raw_lead_label in (LABEL_VANGUARD, LABEL_FLAG) or lead_gap_min <= 5.0)
            and raw_lead_label not in (LABEL_FOLLOW, "跟风", LABEL_STRIKE, "冲锋队")
        )
        if is_front:
            if sector:
                if lock is not None:
                    with lock:
                        current_prime = prime_leader_by_sector.get(sector)
                        if current_prime is None or current_prime == code:
                            prime_leader_by_sector[sector] = code
                            is_prime = True
                else:
                    current_prime = prime_leader_by_sector.get(sector)
                    if current_prime is None or current_prime == code:
                        prime_leader_by_sector[sector] = code
                        is_prime = True
            else:
                is_prime = True

    if is_prime:
        return True, LABEL_PRIME
    return False, raw_lead_label


def compute_tier_floor(
    patterns: List[str],
    struct_status: str,
    is_prime: bool,
    is_leader: bool,
    lead_label: str,
    ps: float,
    struct_floor_enabled: bool = True,
    pattern_floor_enabled: bool = True,
    max_struct_floor_tier: int = 4,
) -> Optional[int]:
    """共用保底档位计算函数，受 max_struct_floor_tier 约束。

    保底规则：
    1. 结构突破保底：若满足十日洗盘悬空突破或结构预判验证形态，且结构未破位/剔除，且启用结构保底，
       则保底 min(4, max_struct_floor_tier)；
    2. 总龙头保底：若为总龙头且未破位，保底 min(4, max_struct_floor_tier)；
    3. 形态分数保底：若启用形态保底，
       - ps >= 100 或 (is_leader 且 ps >= 70): 保底 3；
       - ps >= 70 或 (lead_label 在先锋/领头旗且有形态): 保底 2；
    4. 无保底返回 None。
    """
    _struct_blocked = struct_status in (STATUS_BROKEN, STATUS_EVICTED, "BROKEN", "EVICTED")
    _has_struct_pat = bool(
        PATTERN_BOX10_VWAP_HOVER in patterns
        or PATTERN_STRUCTURE_CONFIRM in patterns
        or "十日洗盘悬空突破" in patterns
        or "结构预判验证" in patterns
    )
    floor: Optional[int] = None
    if struct_floor_enabled and _has_struct_pat and not _struct_blocked:
        floor = min(4, int(max_struct_floor_tier))
    elif is_prime and not _struct_blocked:
        floor = min(4, int(max_struct_floor_tier))
    elif pattern_floor_enabled:
        if ps >= 100.0 or (is_leader and ps >= 70.0):
            floor = 3
        elif ps >= 70.0 or (lead_label in (LABEL_VANGUARD, LABEL_FLAG, "先锋", "领头旗") and bool(patterns)):
            floor = 2
    return floor


def recompute_record_l1a(
    record: Dict[str, Any],
    engine: Optional[FusionEngine] = None,
    override_cuts: Optional[tuple] = None,
    use_engine_cuts: bool = False,
) -> FusionDecision:
    """L1a 单条记录无状态确定性复算。

    从无损快照或行记录还原 SignalEvent、MarketRegime、cuts、tier_floor 并复算。
    确保 score_tier / signal_tier / signal_size_pct / entry / stop / targets / rar 100% 精确一致。
    """
    if engine is None:
        engine = FusionEngine()

    # 1. 还原 SignalEvent
    snapshot = record.get("event_snapshot")
    if isinstance(snapshot, dict) and snapshot:
        event = SignalEvent.from_dict(snapshot)
    else:
        # 兼容旧格式记录
        code = str(record.get("code") or "")
        ts = float(record.get("ts") or 0.0)
        source = str(record.get("source") or "")
        price = float(record.get("price") or 0.0)
        vwap = float(record.get("vwap") or 0.0)
        pct_raw = record.get("pct")
        pct = float(pct_raw if pct_raw is not None else 0.0)
        trade_date = str(record.get("trade_date") or record.get("day") or "")

        extra: Dict[str, Any] = {}
        missing = list(record.get("missing") or [])
        if pct_raw is None:
            missing.append("pct")
        extra["missing"] = missing

        if record.get("patterns"):
            extra["patterns"] = list(record.get("patterns") or [])
        if record.get("struct_status"):
            extra["struct_status"] = record.get("struct_status")
        if record.get("struct"):
            struct_data = record.get("struct")
            if isinstance(struct_data, dict):
                for k, v in struct_data.items():
                    extra[k] = v
        if record.get("lead_label"):
            extra["lead_label"] = record.get("lead_label")
        if record.get("lead_score") is not None:
            extra["lead_score"] = float(record.get("lead_score"))
        if record.get("is_prime_leader") is not None:
            extra["is_prime_leader"] = bool(record.get("is_prime_leader"))
        if record.get("is_structure_prejudged") is not None:
            extra["is_structure_prejudged"] = float(record.get("is_structure_prejudged"))
        if record.get("prev_strong_vwap") is not None:
            extra["prev_strong_vwap"] = float(record.get("prev_strong_vwap"))

        event = SignalEvent(
            code=code,
            ts=ts,
            source=source,
            price=price,
            vwap=vwap,
            pct=pct,
            vol_ratio=float(record.get("vol_ratio") or 1.0),
            trade_date=trade_date,
            extra=extra,
        )

    # 2. 还原 MarketRegime
    regime_dict = record.get("regime")
    regime: Optional[MarketRegime] = None
    if isinstance(regime_dict, dict) and regime_dict:
        regime = MarketRegime(
            temp=float(regime_dict.get("temp") or 50.0),
            stage=str(regime_dict.get("stage") or "WARMING"),
            slope_5m=float(regime_dict.get("slope_5m") or 0.0),
            flip_state=str(regime_dict.get("flip_state") or "IDLE"),
            breadth=float(regime_dict.get("breadth") or regime_dict.get("up_ratio") or 0.5),
            limit_up=int(regime_dict.get("limit_up") or 0),
            limit_down=int(regime_dict.get("limit_down") or 0),
            seal_rate=float(regime_dict.get("seal_rate") or 0.8),
            peak_temp=float(regime_dict.get("peak_temp") or regime_dict.get("temp") or 50.0),
            updated_ts=float(regime_dict.get("updated_ts") or event.ts),
        )

    # 3. 还原 cuts
    cuts_tuple: Optional[tuple] = None
    if override_cuts is not None:
        cuts_tuple = override_cuts
    elif use_engine_cuts and engine is not None:
        cuts_tuple = engine.cuts
    else:
        cuts_raw = record.get("cuts")
        if isinstance(cuts_raw, (list, tuple)) and cuts_raw:
            parsed_cuts = []
            for item in cuts_raw:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    parsed_cuts.append((float(item[0]), int(item[1])))
            if parsed_cuts:
                cuts_tuple = tuple(parsed_cuts)

    # 4. 还原 tier_floor
    tier_floor = record.get("tier_floor")
    tier_floor_int = int(tier_floor) if tier_floor is not None else None
    if tier_floor_int is not None and engine is not None and hasattr(engine, "max_struct_floor_tier"):
        tier_floor_int = min(tier_floor_int, engine.max_struct_floor_tier)

    now = float(record.get("ts") or event.ts)

    # 5. 调用引擎重算
    return engine.evaluate(
        event=event,
        regime=regime,
        now=now,
        cuts=cuts_tuple,
        tier_floor=tier_floor_int,
    )


def recompute_sequence_l1b(
    records: List[Dict[str, Any]],
    engine: Optional[FusionEngine] = None,
    max_l4: int = 2,
    max_total_pct: float = 85.0,
    require_eof_checkpoint: bool = False,
) -> Tuple[List[FusionDecision], List[FusionDecision], Dict[str, Any]]:
    """L1b 序列与组合确定性复算。

    按 (ts, seq_no) 升序重放事件流，驱动 FusionBus 并支持断号与完整性检测。
    返回: (replayed_decisions, portfolio, audit_info)
    """
    if engine is None:
        engine = FusionEngine()

    bus = FusionBus(engine=engine, max_l4=max_l4, max_total_pct=max_total_pct)

    # 排序：按时间戳与单调序号排序
    sorted_records = sorted(
        records,
        key=lambda r: (float(r.get("ts") or 0.0), int(r.get("seq_no") or 0)),
    )

    replayed: List[FusionDecision] = []
    seq_broken = False
    last_seq: Optional[int] = None
    missing_seqs = 0
    has_eof_checkpoint = False
    truncated = False
    dropped_writes = 0

    for rec in sorted_records:
        cp_kind = str(rec.get("checkpoint_kind") or "")
        if cp_kind == "EOF_CHECKPOINT":
            has_eof_checkpoint = True

        if bool(rec.get("max_records_truncated")):
            truncated = True
        dw = rec.get("dropped_write_count")
        if dw is not None:
            try:
                dropped_writes = max(dropped_writes, int(dw))
            except Exception:
                pass

        cur_seq = rec.get("seq_no")
        if cur_seq is not None:
            cur_seq_int = int(cur_seq)
            if last_seq is not None and cur_seq_int > last_seq + 1:
                seq_broken = True
                missing_seqs += (cur_seq_int - last_seq - 1)
            last_seq = cur_seq_int

        # 检查是否为检查点记录（检查点记录不作为行情事件复算）
        if cp_kind:
            continue

        dec = recompute_record_l1a(rec, engine=engine)
        replayed.append(dec)

        # 还原 event 和 cuts 用于 bus.update
        snapshot = rec.get("event_snapshot")
        if isinstance(snapshot, dict) and snapshot:
            ev = SignalEvent.from_dict(snapshot)
        else:
            ev = SignalEvent(code=dec.code, ts=dec.ts, price=float(rec.get("price") or 0.0))

        regime_dict = rec.get("regime")
        rg = MarketRegime.from_dict(regime_dict) if hasattr(MarketRegime, "from_dict") and isinstance(regime_dict, dict) else None

        cuts_raw = rec.get("cuts")
        cuts_tuple: Optional[tuple] = None
        if isinstance(cuts_raw, (list, tuple)) and cuts_raw:
            cuts_items = []
            for item in cuts_raw:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    cuts_items.append((float(item[0]), int(item[1])))
            cuts_tuple = tuple(cuts_items) if cuts_items else None

        tier_floor = rec.get("tier_floor")
        tier_floor_int = int(tier_floor) if tier_floor is not None else None
        if tier_floor_int is not None and engine is not None and hasattr(engine, "max_struct_floor_tier"):
            tier_floor_int = min(tier_floor_int, engine.max_struct_floor_tier)

        bus.update(ev, rg, decision=dec, cuts=cuts_tuple, tier_floor=tier_floor_int)

    portfolio = bus.rebalance()

    is_incomplete = bool(
        seq_broken
        or missing_seqs > 0
        or truncated
        or dropped_writes > 0
        or (require_eof_checkpoint and not has_eof_checkpoint)
    )

    audit_info = {
        "total_records": len(records),
        "replayed_events": len(replayed),
        "sequence_broken": seq_broken,
        "missing_seq_count": missing_seqs,
        "has_eof_checkpoint": has_eof_checkpoint,
        "truncated": truncated,
        "dropped_writes": dropped_writes,
        "log_incomplete": is_incomplete,
        "portfolio_size": len(portfolio),
        "total_size_pct": bus.total_size_pct(),
    }

    return replayed, portfolio, audit_info


def run_l1_ablation(
    records: List[Dict[str, Any]],
    base_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """P1 单变量受控消融实验（One-Factor-at-a-Time）。

    在同一批实盘特征快照 records 上，分别运行基线与 4 个单变量对照实验：
    1. factor_fixed_cuts_68: 仅切换 tier_cuts={"l4": 68.0, "l3": 60.0, "l2": 52.0, "l1": 45.0}
    2. factor_struct_floor_l3: 仅将 max_struct_floor_tier 设为 3（结构/总龙头保底最高 L3）
    3. factor_no_temp_cap_exempt: 仅将 exempt_temp_cap_on_struct 设为 False（取消退潮/冰点期温度封顶越级豁免）
    4. factor_combined_p3_preview: 同时开启 max_struct_floor_tier=3 与 exempt_temp_cap_on_struct=False

    返回每个实验组的档位分布、平均 rar、与基线档位一致率及升降档转移统计。
    """
    valid_records = [r for r in records if not r.get("checkpoint_kind")]

    exp_configs: Dict[str, Dict[str, Any]] = {
        "baseline": dict(base_params or {}),
        "factor_fixed_cuts_68": dict(
            base_params or {},
            tier_cuts={"l4": 68.0, "l3": 60.0, "l2": 52.0, "l1": 45.0},
        ),
        "factor_struct_floor_l3": dict(
            base_params or {},
            max_struct_floor_tier=3,
        ),
        "factor_no_temp_cap_exempt": dict(
            base_params or {},
            exempt_temp_cap_on_struct=False,
        ),
        "factor_combined_p3_preview": dict(
            base_params or {},
            max_struct_floor_tier=3,
            exempt_temp_cap_on_struct=False,
        ),
    }

    cuts_68 = ((68.0, 4), (60.0, 3), (52.0, 2), (45.0, 1))

    results: Dict[str, Any] = {}
    base_tiers: List[int] = []

    for name, params in exp_configs.items():
        engine = FusionEngine(params=params)
        decisions: List[FusionDecision] = []
        for rec in valid_records:
            if name == "factor_fixed_cuts_68":
                dec = recompute_record_l1a(rec, engine=engine, override_cuts=cuts_68)
            else:
                dec = recompute_record_l1a(rec, engine=engine)
            decisions.append(dec)

        tiers = [d.tier for d in decisions]
        rars = [d.rar for d in decisions]

        if name == "baseline":
            base_tiers = list(tiers)

        tier_counts = {t: tiers.count(t) for t in range(5)}
        avg_rar = float(sum(rars) / len(rars)) if rars else 0.0

        if name == "baseline":
            tier_match_rate = 1.0
            upgrade_count = 0
            downgrade_count = 0
            unchanged_count = len(tiers)
            shift_matrix: Dict[str, int] = {}
        else:
            matches = sum(1 for bt, t in zip(base_tiers, tiers) if bt == t)
            tier_match_rate = float(matches / len(tiers)) if tiers else 1.0
            upgrade_count = sum(1 for bt, t in zip(base_tiers, tiers) if t > bt)
            downgrade_count = sum(1 for bt, t in zip(base_tiers, tiers) if t < bt)
            unchanged_count = matches
            shift_matrix = {}
            for bt, t in zip(base_tiers, tiers):
                if bt != t:
                    key = f"L{bt}->L{t}"
                    shift_matrix[key] = shift_matrix.get(key, 0) + 1

        results[name] = {
            "tier_counts": tier_counts,
            "avg_rar": round(avg_rar, 3),
            "tier_match_rate": round(tier_match_rate, 4),
            "upgrade_count": upgrade_count,
            "downgrade_count": downgrade_count,
            "unchanged_count": unchanged_count,
            "shift_matrix": shift_matrix,
        }

    return {
        "total_records": len(valid_records),
        "experiments": results,
    }


def compute_feature_drift_report(
    shadow_records: List[Dict[str, Any]],
    replay_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """P1 第 2 层特征漂移与对齐报告。

    按 (code, day) 对齐同日实盘快照与回放记录：
    1. 计算代码集合 Jaccard 相似度；
    2. 对比同一 code 首次触发 L2+ 时间差及 <= 1 bar (180s) 比例；
    3. 逐字段计算 MAE 与 Median AE，并按归一化偏差降序输出 top_drift_sources。
    """
    import numpy as np

    s_recs = [r for r in shadow_records if not r.get("checkpoint_kind")]
    r_recs = [r for r in replay_records if not r.get("checkpoint_kind")]

    s_codes = {str(r.get("code")) for r in s_recs if r.get("code")}
    r_codes = {str(r.get("code")) for r in r_recs if r.get("code")}
    union_codes = s_codes | r_codes
    inter_codes = s_codes & r_codes
    code_jaccard = float(len(inter_codes) / len(union_codes)) if union_codes else 1.0

    def _get_day(r: Dict[str, Any]) -> str:
        d = r.get("day") or r.get("trade_date")
        if d:
            return str(d)
        ts = float(r.get("ts") or 0.0)
        if ts > 0:
            return time.strftime("%Y-%m-%d", time.localtime(ts))
        return ""

    def _extract_first_l2(records: List[Dict[str, Any]]) -> Dict[Tuple[str, str], float]:
        first_map: Dict[Tuple[str, str], float] = {}
        for r in records:
            code = str(r.get("code") or "")
            if not code:
                continue
            day = _get_day(r)
            fus = r.get("fusion")
            tier_val = 0
            if isinstance(fus, dict):
                tier_val = fus.get("signal_tier") or fus.get("tier") or 0
            if not tier_val:
                tier_val = r.get("signal_tier") or r.get("tier") or 0
            tier = int(tier_val)
            if tier >= 2:
                ts = float(r.get("ts") or 0.0)
                key = (code, day)
                if key not in first_map or ts < first_map[key]:
                    first_map[key] = ts
        return first_map

    s_first_l2 = _extract_first_l2(s_recs)
    r_first_l2 = _extract_first_l2(r_recs)
    common_l2_keys = set(s_first_l2.keys()) & set(r_first_l2.keys())

    l2_time_diffs: List[float] = []
    for k in common_l2_keys:
        l2_time_diffs.append(abs(s_first_l2[k] - r_first_l2[k]))

    if l2_time_diffs:
        within_1bar = sum(1 for dt in l2_time_diffs if dt <= 180.0)
        first_l2_within_1bar_rate = float(within_1bar / len(l2_time_diffs))
        mean_l2_diff_s = float(np.mean(l2_time_diffs))
        median_l2_diff_s = float(np.median(l2_time_diffs))
    else:
        first_l2_within_1bar_rate = 1.0 if not (s_first_l2 or r_first_l2) else 0.0
        mean_l2_diff_s = 0.0
        median_l2_diff_s = 0.0

    def _extract_fields(r: Dict[str, Any]) -> Dict[str, float]:
        ev = r.get("event_snapshot") or {}
        reg = r.get("regime") or {}
        fus = r.get("fusion") or {}
        rc_det = r.get("reclaim_detail") or {}
        launch = r.get("launch_signal") or {}

        vr = ev.get("vol_ratio") or r.get("vol_ratio") or rc_det.get("vol_ratio") or 1.0
        vw = r.get("vwap") or ev.get("vwap") or rc_det.get("vwap") or r.get("entry") or 0.0
        tp = reg.get("temp") if isinstance(reg, dict) and "temp" in reg else r.get("temp")
        if tp is None:
            tp = 50.0
        sr = ev.get("sector_resonance") or launch.get("sector_resonance") or r.get("sector_resonance") or rc_det.get("sector_resonance") or 0.0
        rar_val = fus.get("rar") if isinstance(fus, dict) and "rar" in fus else r.get("rar")
        if rar_val is None:
            rar_val = 0.0
        st = 0.0
        if isinstance(fus, dict):
            st = fus.get("signal_tier") or fus.get("tier") or 0.0
        if not st:
            st = r.get("signal_tier") or r.get("tier") or 0.0

        return {
            "vol_ratio": float(vr),
            "vwap": float(vw),
            "temp": float(tp),
            "sector_resonance": float(sr),
            "rar": float(rar_val),
            "signal_tier": float(st),
        }

    from collections import defaultdict
    s_grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    r_grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    for r in s_recs:
        c = str(r.get("code") or "")
        if c:
            s_grouped[(c, _get_day(r))].append(r)
    for r in r_recs:
        c = str(r.get("code") or "")
        if c:
            r_grouped[(c, _get_day(r))].append(r)

    field_diffs: Dict[str, List[float]] = {
        "vol_ratio": [],
        "vwap": [],
        "temp": [],
        "sector_resonance": [],
        "rar": [],
        "signal_tier": [],
    }

    field_scales: Dict[str, float] = {
        "vol_ratio": 2.0,
        "vwap": 10.0,
        "temp": 100.0,
        "sector_resonance": 100.0,
        "rar": 100.0,
        "signal_tier": 4.0,
    }

    matched_pairs_count = 0
    common_groups = set(s_grouped.keys()) & set(r_grouped.keys())

    for grp in common_groups:
        s_list = sorted(s_grouped[grp], key=lambda x: float(x.get("ts") or 0.0))
        r_list = sorted(r_grouped[grp], key=lambda x: float(x.get("ts") or 0.0))

        r_used = set()
        for s_item in s_list:
            s_ts = float(s_item.get("ts") or 0.0)
            best_idx = -1
            best_dt = 1e9
            for idx, r_item in enumerate(r_list):
                if idx in r_used:
                    continue
                dt = abs(float(r_item.get("ts") or 0.0) - s_ts)
                if dt < best_dt:
                    best_dt = dt
                    best_idx = idx

            if best_idx >= 0 and best_dt <= 3600.0:
                r_used.add(best_idx)
                s_f = _extract_fields(s_item)
                r_f = _extract_fields(r_list[best_idx])
                for f_name in field_diffs:
                    field_diffs[f_name].append(abs(s_f[f_name] - r_f[f_name]))
                matched_pairs_count += 1

    field_metrics: Dict[str, Dict[str, float]] = {}
    drift_rank_list: List[Dict[str, Any]] = []

    for f_name, diffs in field_diffs.items():
        if diffs:
            mae = float(np.mean(diffs))
            med_ae = float(np.median(diffs))
            scale = field_scales.get(f_name, 1.0)
            norm_mae = mae / scale
        else:
            mae = 0.0
            med_ae = 0.0
            norm_mae = 0.0

        field_metrics[f_name] = {
            "mae": round(mae, 4),
            "median_ae": round(med_ae, 4),
            "norm_mae": round(norm_mae, 4),
            "sample_count": len(diffs),
        }
        drift_rank_list.append({
            "field": f_name,
            "mae": round(mae, 4),
            "median_ae": round(med_ae, 4),
            "norm_mae": round(norm_mae, 4),
        })

    drift_rank_list.sort(key=lambda x: x["norm_mae"], reverse=True)

    return {
        "code_jaccard": round(code_jaccard, 4),
        "shadow_code_count": len(s_codes),
        "replay_code_count": len(r_codes),
        "common_code_count": len(inter_codes),
        "common_l2_count": len(common_l2_keys),
        "first_l2_within_1bar_rate": round(first_l2_within_1bar_rate, 4),
        "mean_l2_diff_s": round(mean_l2_diff_s, 2),
        "median_l2_diff_s": round(median_l2_diff_s, 2),
        "matched_pairs_count": matched_pairs_count,
        "field_metrics": field_metrics,
        "top_drift_sources": drift_rank_list,
    }
