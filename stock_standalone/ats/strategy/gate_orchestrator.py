"""Fail-closed six-gate IPO decision arbitration with RiskGate final approval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

from ats.strategy.channel_secondary_buy_strategy import IPOTradePlan
from ats.strategy.ipo_data_contracts import IPODataContractSet, build_decision_config_hash
from ats.strategy.ipo_live_heat_engine import IPOLiveHeatSnapshot
from ats.strategy.ipo_preheat_engine import IPOPreHeatSnapshot
from ats.strategy.listing_anchor_store import ListingAnchors, ListingAnchorStore
from ats.vwap_factory import VWAPSnapshot
from trading_kernel.core.intent import DecisionIntent
from trading_kernel.core.risk import RiskDecision
from trading_kernel.core.signal import StrategySignal
from trading_kernel.engine.risk_gate import RiskLimits, evaluate as evaluate_risk_gate


_EXCHANGE_TZ = ZoneInfo("Asia/Shanghai")


def _finite(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _config_number(config: Any, section: str, key: str) -> Optional[float]:
    values = config.get(section) if isinstance(config, Mapping) else None
    if not isinstance(values, Mapping):
        return None
    value = values.get(key)
    return float(value) if _finite(value) else None


def _diagnostic_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:180]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if _finite(value):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [item[:180] for item in value[:12] if isinstance(item, str)]
    return None


def _diagnostic_group(obj: Any, fields: Tuple[str, ...]) -> Dict[str, Any]:
    if obj is None:
        return {"status": "UNAVAILABLE"}
    data_ready = getattr(obj, "data_ready", None)
    result: Dict[str, Any] = {
        "status": "READY" if data_ready is True else "UNREADY" if data_ready is False else "PRESENT"
    }
    for name in fields:
        result[name] = _diagnostic_value(getattr(obj, name, None))
    return result


def _build_gate_diagnostics(
    lrrm: Any, ipo_regime: Any, preheat: Any, live_heat: Any,
    t1_carry: Any, listing_anchors: Any, vwap: Any, trade_plan: Any,
    market_as_of_time: Any, data_contract: Any,
) -> Dict[str, Any]:
    carry_positive = _diagnostic_value(getattr(t1_carry, "positive_factors", [])) or []
    carry_negative = _diagnostic_value(getattr(t1_carry, "negative_factors", [])) or []
    negative = list(carry_negative)
    live_veto = (
        getattr(live_heat, "veto_reason", None)
        if getattr(live_heat, "is_overheated_veto", False) is True
        or getattr(live_heat, "data_ready", None) is not True else None
    )
    preheat_unready = (
        getattr(preheat, "unready_reason_code", None)
        if getattr(preheat, "data_status", None) != "READY" else None
    )
    for item in (live_veto, preheat_unready):
        if isinstance(item, str) and item and item not in negative:
            negative.append(item[:180])
    regime = _diagnostic_group(ipo_regime, (
        "state", "confidence", "d1_positive_rate", "first_day_peak_ratio",
        "new_high_ratio", "turnover_median", "sample_count", "generated_at",
        "trigger_factors", "missing_metrics",
    ))
    anchors = _diagnostic_group(listing_anchors, (
        "listing_date", "listing_open", "listing_high", "listing_low",
        "listing_close", "listing_vwap", "listing_anchored_vwap",
        "first_30m_vwap", "close_location", "first_day_turnover",
    ))
    if listing_anchors is None:
        anchors["status"] = "UNAVAILABLE"
    elif isinstance(listing_anchors, ListingAnchors):
        anchors["status"] = "SEALED"
    else:
        anchors["status"] = "INVALID"
    vwap_summary = _diagnostic_group(vwap, (
        "code", "date", "time", "version", "vwap_1d", "vwap_5d",
        "vwap_10d", "coverage_days", "current_price", "structure",
        "complete_5d", "complete_10d", "stale", "basis",
    ))
    if vwap is not None:
        vwap_summary["status"] = (
            "INVALID" if not isinstance(vwap, VWAPSnapshot)
            else "STALE" if getattr(vwap, "stale", False) is True else "PRESENT"
        )
    as_of_time = ""
    try:
        if (
            isinstance(market_as_of_time, datetime)
            and market_as_of_time.tzinfo is not None
            and market_as_of_time.utcoffset() is not None
        ):
            as_of_time = market_as_of_time.isoformat()
    except (OverflowError, OSError, TypeError, ValueError):
        as_of_time = ""
    result = {
        "as_of_time": as_of_time,
        "lrrm": _diagnostic_group(lrrm, (
            "liquidity_regime", "risk_appetite", "concentration_state",
            "liquidity_confidence", "transition_reason", "market_amount_yi",
            "amount_20d_percentile", "advance_decline_ratio", "limit_down_count",
            "generated_at", "missing_inputs",
        )),
        "regime": regime,
        "preheat": _diagnostic_group(preheat, (
            "preheat_tier", "preheat_score", "valuation_score",
            "subscription_score", "scarcity_score", "theme_match_score",
            "capital_structure_score", "valuation_status", "data_status",
            "unready_reason_code", "as_of_date",
        )),
        "live_heat": _diagnostic_group(live_heat, (
            "nonlinear_zone", "heat_score", "overheat_score", "exhaustion_risk",
            "intraday_velocity", "turnover_pct", "turnover_climb_speed",
            "price_vwap_dist_pct", "close_location", "minutes_above_vwap_ratio",
            "pullback_from_peak_pct", "halt_count", "veto_reason",
        )),
        "carry": _diagnostic_group(t1_carry, (
            "state", "score", "nonlinear_zone", "overheat_score",
            "exhaustion_risk", "positive_factors", "negative_factors",
            "is_pseudo_strength_blocked", "veto_reason",
        )),
        "anchors": anchors,
        "vwap": vwap_summary,
        "data_contract": {
            "status": "PRESENT" if isinstance(data_contract, IPODataContractSet) else "UNAVAILABLE",
            "version": _diagnostic_value(getattr(data_contract, "config_version", None)),
            "hash": _diagnostic_value(getattr(data_contract, "config_hash", None)),
            "required_count": len(getattr(data_contract, "required_fields", ()) or ()),
        },
        "trade_plan": _diagnostic_group(trade_plan, (
            "plan_id", "suggested_action", "buy_zone_min", "buy_zone_max",
            "stop_loss_price", "higher_low_stop", "created_at",
        )),
        "risk": {"status": "UNAVAILABLE" if trade_plan is None else "PENDING"},
        "positive_factors": carry_positive,
        "negative_factors": negative,
    }
    return result


@dataclass
class GatePassport:
    code: str
    name: str
    gate0_lrrm_passed: bool = False
    gate1_regime_passed: bool = False
    gate2_t1_carry_passed: bool = False
    gate2_state: str = ""
    gate2_score: float = 0.0
    gate3_anchor_passed: bool = False
    gate4_vwap_passed: bool = False
    gate5_tde_passed: bool = False
    final_decision: str = "BLOCK"
    block_at_gate: int = -1
    causal_chain: List[str] = field(default_factory=list)
    approved_order: Any = None
    configuration_version: str = ""
    configuration_hash: str = ""
    data_contract_hash: str = ""
    authorization_ttl_seconds: float = 0.0
    preheat_passed: bool = False
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    learning_input_snapshot: Optional[Dict[str, Any]] = None
    learning_input_snapshot_hash: str = ""


@dataclass(frozen=True)
class RiskGateContext:
    intent: DecisionIntent
    signal: StrategySignal
    state: str
    limits: RiskLimits
    held_codes: Dict[str, str]
    current_stock_exposure: float
    current_sector_exposure: float
    current_total_exposure: float
    today_pnl_loss: float
    consecutive_losses: int
    current_time: str


def evaluate_gate4_vwap(
    vwap: Optional[VWAPSnapshot],
    code: str,
    current_price: float,
    listing_age_sessions: int,
    listing_anchors: Optional[ListingAnchors],
    as_of_time: datetime,
    max_vwap_stale_seconds: int,
    thresholds: Mapping[str, float],
) -> Tuple[bool, str]:
    if not isinstance(vwap, VWAPSnapshot):
        return False, "Gate 4 阻断: VWAP 数据源缺失或类型无效"
    if vwap.stale or vwap.code != code or vwap.basis != "turnover":
        return False, "Gate 4 阻断: VWAP 已过期、标的不匹配或基准不是成交额"
    if (
        not isinstance(as_of_time, datetime) or as_of_time.tzinfo is None
        or isinstance(max_vwap_stale_seconds, bool)
        or not isinstance(max_vwap_stale_seconds, int) or max_vwap_stale_seconds <= 0
        or isinstance(listing_age_sessions, bool) or not isinstance(listing_age_sessions, int)
        or listing_age_sessions < 1
    ):
        return False, "Gate 4 阻断: 行情时点、时效配置或上市交易日数无效"
    support_pct = thresholds.get("min_price_support_pct")
    early_anchor_pct = thresholds.get("early_anchor_support_pct")
    if (
        not _finite(support_pct) or not 0 <= support_pct < 100
        or not _finite(early_anchor_pct) or not 0 <= early_anchor_pct < 100
    ):
        return False, "Gate 4 阻断: VWAP 支撑阈值未在有效版本化配置中定义"
    try:
        if as_of_time.utcoffset() is None:
            raise ValueError("as_of_time offset missing")
        snapshot_time = datetime.strptime(f"{vwap.date} {vwap.time}", "%Y-%m-%d %H:%M")
        snapshot_time = snapshot_time.replace(tzinfo=_EXCHANGE_TZ)
        age_seconds = (
            as_of_time.astimezone(_EXCHANGE_TZ) - snapshot_time
        ).total_seconds()
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False, "Gate 4 阻断: VWAP 或行情时点格式无效"
    if age_seconds < 0 or age_seconds > max_vwap_stale_seconds:
        return False, f"Gate 4 阻断: VWAP 快照超龄或晚于行情时点 ({age_seconds:.0f}s)"

    vwap_today = vwap.vwap_1d
    if not _finite(current_price) or current_price <= 0 or not _finite(vwap_today) or vwap_today <= 0:
        return False, "Gate 4 阻断: 现价或当日 VWAP 缺失/无效，禁止以现价补值"
    coverage = vwap.coverage_days
    if isinstance(coverage, bool) or not isinstance(coverage, int) or coverage < min(listing_age_sessions, 10):
        return False, "Gate 4 阻断: VWAP 覆盖交易日不足"

    if 1 < listing_age_sessions < 5:
        anchor_vwap = getattr(listing_anchors, "listing_anchored_vwap", None)
        if not _finite(anchor_vwap) or anchor_vwap <= 0:
            return False, "Gate 4 阻断: 早期上市标的缺少有效首日锚定 VWAP"
        if current_price < anchor_vwap * (1.0 - early_anchor_pct / 100.0):
            return False, "Gate 4 阻断: 现价跌破配置化首日锚定 VWAP 支撑"
    elif 5 <= listing_age_sessions < 10:
        if (
            coverage < 5 or not vwap.complete_5d
            or not _finite(vwap.vwap_5d) or vwap.vwap_5d <= 0
        ):
            return False, "Gate 4 阻断: 已满 5 个上市交易日但 5D VWAP 不完整"
    elif listing_age_sessions >= 10:
        if (
            coverage < 10 or not vwap.complete_5d or not _finite(vwap.vwap_5d)
            or vwap.vwap_5d <= 0 or not vwap.complete_10d
            or not _finite(vwap.vwap_10d) or vwap.vwap_10d <= 0
        ):
            return False, "Gate 4 阻断: 已满 10 个上市交易日但 5D/10D VWAP 不完整"

    known_structures = {"数据不足", "多周期偏强", "日内转弱 / 中期偏强", "多周期偏弱", "多周期混合"}
    if vwap.structure not in known_structures:
        return False, "Gate 4 阻断: VWAP 结构状态缺失"
    if listing_age_sessions > 1 and vwap.structure == "数据不足":
        return False, "Gate 4 阻断: D1+ VWAP 结构数据不足"
    if current_price < vwap_today * (1.0 - support_pct / 100.0) or vwap.structure == "多周期偏弱":
        return False, "Gate 4 阻断: 现价跌破配置化当日 VWAP 支撑或 VWAP 结构偏弱"
    return True, f"Gate 4 放行: 当日 VWAP 与上市日龄适用结构校验通过 ({vwap.structure})"


class GateOrchestrator:
    """Gate 0–5 short-circuit arbiter; only an approved RiskGate order can yield ENTRY."""

    def evaluate(
        self,
        code: str,
        name: str,
        lrrm: Any,
        ipo_regime: Any,
        t1_carry: Any,
        listing_anchors: Optional[ListingAnchors],
        vwap: Optional[VWAPSnapshot],
        current_price: float,
        intraday_low: float,
        listing_age_sessions: int,
        horse_rank: int,
        market_as_of_time: datetime,
        max_vwap_stale_seconds: int,
        trade_plan: Optional[IPOTradePlan] = None,
        risk_context: Optional[RiskGateContext] = None,
        d0_listing_open_price: Optional[float] = None,
        issue_price: Optional[float] = None,
        d0_open_break_pct: Optional[float] = None,
        requested_position_pct: Optional[float] = None,
        preheat: Optional[IPOPreHeatSnapshot] = None,
        live_heat: Optional[IPOLiveHeatSnapshot] = None,
        data_contract: Optional[IPODataContractSet] = None,
        data_observations: Optional[Dict[str, Dict[str, Any]]] = None,
        data_contract_hash: str = "",
        configuration_version: str = "",
        configuration_hash: str = "",
        decision_config: Optional[Mapping[str, Any]] = None,
    ) -> GatePassport:
        passport = GatePassport(code=code if isinstance(code, str) else "", name=name or "")
        passport.configuration_version = configuration_version if isinstance(configuration_version, str) else ""
        passport.configuration_hash = configuration_hash if isinstance(configuration_hash, str) else ""
        passport.data_contract_hash = data_contract_hash if isinstance(data_contract_hash, str) else ""
        passport.diagnostics = _build_gate_diagnostics(
            lrrm, ipo_regime, preheat, live_heat, t1_carry,
            listing_anchors, vwap, trade_plan, market_as_of_time, data_contract,
        )

        if (
            not passport.configuration_version.strip()
            or not re.fullmatch(r"[0-9a-fA-F]{64}", passport.configuration_hash)
        ):
            return self._block(passport, 0, "Gate 0 阻断: 缺少有效版本化决策配置哈希")
        if (
            not isinstance(data_contract, IPODataContractSet)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", passport.data_contract_hash)
            or data_contract.config_hash != passport.data_contract_hash
            or not isinstance(market_as_of_time, datetime)
        ):
            return self._block(passport, 0, "Gate 0 阻断: 数据字典或来源契约哈希缺失/不匹配")
        try:
            expected_config_hash = build_decision_config_hash(
                passport.configuration_version, decision_config, data_contract
            )
        except ValueError:
            return self._block(passport, 0, "Gate 0 阻断: 决策配置内容缺失或不可哈希")
        if passport.configuration_hash.lower() != expected_config_hash:
            return self._block(passport, 0, "Gate 0 阻断: 决策配置哈希与实际配置内容不一致")
        carry_allow = _config_number(decision_config, "t1_carry", "allow_threshold")
        min_rr = _config_number(decision_config, "trade_gate", "min_risk_reward")
        trade_gate_config = decision_config.get("trade_gate", {})
        allowed_actions = (
            trade_gate_config.get("allowed_actions")
            if isinstance(trade_gate_config, Mapping) else None
        )
        signal_max_age = _config_number(decision_config, "trade_gate", "signal_max_age_seconds")
        risk_clock_skew = _config_number(decision_config, "trade_gate", "risk_clock_skew_seconds")
        auth_ttl = _config_number(decision_config, "trade_gate", "authorization_ttl_seconds")
        configured_vwap_stale = _config_number(decision_config, "vwap_freshness", "max_stale_seconds")
        vwap_support = _config_number(decision_config, "vwap_execution", "min_price_support_pct")
        early_anchor_support = _config_number(decision_config, "vwap_execution", "early_anchor_support_pct")
        d0_open_break = _config_number(decision_config, "listing_anchors", "d0_open_break_pct")
        if (
            carry_allow is None or not 0 <= carry_allow <= 100
            or min_rr is None or min_rr <= 0
            or not isinstance(allowed_actions, (list, tuple))
            or not allowed_actions
            or any(action not in {"WATCH", "BUY", "SELL"} for action in allowed_actions)
            or signal_max_age is None or signal_max_age <= 0
            or risk_clock_skew is None or risk_clock_skew < 0
            or auth_ttl is None or auth_ttl <= 0 or auth_ttl > signal_max_age
            or configured_vwap_stale is None or configured_vwap_stale <= 0
            or int(configured_vwap_stale) != configured_vwap_stale
            or vwap_support is None or not 0 <= vwap_support < 100
            or early_anchor_support is None or not 0 <= early_anchor_support < 100
            or d0_open_break is None or not 0 <= d0_open_break < 1
            or max_vwap_stale_seconds != int(configured_vwap_stale)
        ):
            return self._block(passport, 0, "Gate 0 阻断: 门禁阈值/凭据 TTL 缺失、非法或与调用参数不一致")
        passport.authorization_ttl_seconds = auth_ttl
        data_ready, field_checks = data_contract.validate_observations(
            data_observations or {}, market_as_of_time
        )
        unready_fields = [
            {"field_id": field_id, "reason": check.reason_code or check.status}
            for field_id, check in field_checks.items() if not check.usable
        ]
        passport.diagnostics["data_contract"] = {
            "status": "READY" if data_ready else "UNREADY",
            "version": data_contract.config_version,
            "hash": data_contract.config_hash,
            "required_count": len(data_contract.required_fields),
            "ready_count": sum(1 for check in field_checks.values() if check.usable),
            "unready_count": len(unready_fields),
            "unready_fields": unready_fields[:20],
        }
        if not data_ready:
            reasons = "、".join(
                f"{item['field_id']}:{item['reason']}" for item in unready_fields[:4]
            )
            suffix = f"（{reasons}）" if reasons else ""
            return self._block(passport, 0, f"Gate 0 阻断: 指标来源、可用时点或 TTL 未全部通过校验{suffix}")

        try:
            from ats.llm.offline_learning import compute_input_snapshot_hash

            cutoff_utc = data_contract._parse_timestamp(
                market_as_of_time, "UTC", allow_naive=False
            )
            frozen_features = {}
            for field_id in data_contract.required_fields:
                contract = data_contract.fields[field_id]
                observation = data_observations[field_id]
                as_of = data_contract._parse_timestamp(
                    observation[contract.as_of_key], contract.source_timezone,
                    allow_naive=False,
                )
                available_at = data_contract._parse_timestamp(
                    observation[contract.available_at_key], contract.source_timezone,
                    allow_naive=False,
                )
                frozen_features[field_id] = {
                    "status": observation["status"],
                    "value": observation.get(contract.value_key),
                    "source_id": contract.source_id,
                    "source_version": contract.source_version,
                    "source_timezone": contract.source_timezone,
                    "as_of_time": as_of.isoformat(),
                    "available_at": available_at.isoformat(),
                }
            learning_snapshot = {
                "as_of_time": cutoff_utc.isoformat(),
                "configuration_hash": passport.configuration_hash.lower(),
                "data_contract_hash": passport.data_contract_hash.lower(),
                "features": frozen_features,
            }
            passport.learning_input_snapshot = learning_snapshot
            passport.learning_input_snapshot_hash = compute_input_snapshot_hash(learning_snapshot)
            passport.diagnostics["learning_snapshot_status"] = "CAPTURED"
        except (ImportError, KeyError, TypeError, ValueError, OverflowError, RecursionError):
            passport.learning_input_snapshot = None
            passport.learning_input_snapshot_hash = ""
            passport.diagnostics["learning_snapshot_status"] = "UNAVAILABLE"

        if getattr(lrrm, "data_ready", False) is not True:
            return self._block(passport, 0, "Gate 0 阻断: LRRM 快照缺失或必需输入未就绪")
        if (
            getattr(lrrm, "liquidity_regime", None) not in {"NORMAL", "LOOSE"}
            or getattr(lrrm, "risk_appetite", None) not in {"RISK_ON", "NEUTRAL"}
        ):
            return self._block(passport, 0, f"Gate 0 阻断: {getattr(lrrm, 'transition_reason', '状态不允许')}")
        passport.gate0_lrrm_passed = True
        passport.causal_chain.append("Gate 0 放行: LRRM 宏观流动性允许")

        if (
            getattr(ipo_regime, "data_ready", False) is not True
            or isinstance(getattr(ipo_regime, "sample_count", None), bool)
            or not isinstance(getattr(ipo_regime, "sample_count", None), int)
            or ipo_regime.sample_count < 5
        ):
            return self._block(passport, 1, "Gate 1 阻断: IPO Regime 样本或关键数据未就绪")
        if getattr(ipo_regime, "state", None) not in {"REPAIR", "CONTINUATION"}:
            return self._block(
                passport, 1,
                f"Gate 1 阻断: 板块处于禁止买入阶段({getattr(ipo_regime, 'state', 'UNKNOWN')})",
            )
        passport.gate1_regime_passed = True
        passport.causal_chain.append(f"Gate 1 放行: IPO Regime {ipo_regime.state}")

        if (
            not isinstance(preheat, IPOPreHeatSnapshot)
            or preheat.code != code
            or preheat.data_status != "READY"
            or preheat.is_watch_candidate is not True
            or preheat.preheat_tier not in {"PRE_WARM", "PRE_HOT"}
            or not _finite(preheat.preheat_score)
        ):
            return self._block(passport, 1, "Gate 1 阻断: Pre-Heat 候选或来源数据未就绪")
        passport.preheat_passed = True
        passport.causal_chain.append("Pre-Heat 放行: 评分达到版本化候选阈值")

        if (
            not isinstance(live_heat, IPOLiveHeatSnapshot)
            or live_heat.code != code
            or live_heat.data_ready is not True
            or live_heat.nonlinear_zone not in {"NORMAL", "HOT", "EXTREME"}
        ):
            return self._block(passport, 2, "Gate 2 阻断: Live Heat 指标或来源时效未就绪")

        if getattr(t1_carry, "data_ready", False) is not True:
            return self._block(passport, 2, "Gate 2 阻断: T1 Carry 数据未就绪")
        if getattr(t1_carry, "nonlinear_zone", None) != live_heat.nonlinear_zone:
            return self._block(passport, 2, "Gate 2 阻断: Live Heat 与 T1 Carry 快照不一致")
        passport.gate2_state = getattr(t1_carry, "state", "UNKNOWN")
        if not _finite(getattr(t1_carry, "score", None)):
            return self._block(passport, 2, "Gate 2 阻断: T1 Carry 评分无效")
        passport.gate2_score = float(t1_carry.score)
        if passport.gate2_state == "BLOCK" or getattr(t1_carry, "is_pseudo_strength_blocked", False):
            return self._block(passport, 2, f"Gate 2 阻断: {getattr(t1_carry, 'veto_reason', '')}")
        if passport.gate2_state == "CAUTION":
            passport.block_at_gate = 2
            passport.final_decision = "WATCH"
            passport.causal_chain.append("Gate 2 待命: T1 Carry CAUTION 不授予开仓许可")
            passport.diagnostics["next_condition"] = "T1 Carry 达到 ALLOW 阈值，且 Live Heat 不处于 EXTREME"
            return passport
        if (
            passport.gate2_state != "ALLOW" or passport.gate2_score < carry_allow
            or getattr(t1_carry, "nonlinear_zone", "UNKNOWN") == "EXTREME"
        ):
            return self._block(passport, 2, "Gate 2 阻断: T1 Carry 状态未知、评分不足或过热")
        passport.gate2_t1_carry_passed = True
        passport.causal_chain.append("Gate 2 放行: T1 Carry 达标")

        if isinstance(listing_age_sessions, bool) or not isinstance(listing_age_sessions, int) or listing_age_sessions < 1:
            return self._block(passport, 3, "Gate 3 阻断: 上市交易日数无效")
        if listing_age_sessions == 1:
            values = (d0_listing_open_price, issue_price, intraday_low, current_price)
            if (
                any(not _finite(value) or value <= 0 for value in values)
                or not _finite(d0_open_break_pct)
                or abs(float(d0_open_break_pct) - float(d0_open_break)) > 1e-9
                or not 0 <= d0_open_break_pct < 1.0
            ):
                return self._block(passport, 3, "Gate 3 阻断: D0 开盘价/发行价/行情或容差无效")
            open_price = float(d0_listing_open_price)
            if (
                intraday_low < open_price * (1.0 - d0_open_break_pct)
                or current_price < open_price * (1.0 - d0_open_break_pct)
                or intraday_low < issue_price or current_price < issue_price
            ):
                return self._block(passport, 3, "Gate 3 阻断: D0 跌破开盘支撑或发行价")
            passport.gate3_anchor_passed = True
            passport.final_decision = "WATCH"
            passport.causal_chain.append("Gate 3 观察: D0 只观察并沉淀锚点，不生成 ENTRY")
            passport.diagnostics["next_condition"] = "进入 D1+ 后重新确认首日双锚、VWAP 支撑、交易计划与 RiskGate"
            return passport

        if (
            not isinstance(listing_anchors, ListingAnchors)
            or listing_anchors.code != code
        ):
            return self._block(passport, 3, "Gate 3 阻断: D1+ 缺少合法封存的首日锚点")
        if not listing_anchors.matches_contract(
            passport.configuration_hash, passport.data_contract_hash,
        ):
            return self._block(passport, 3, "Gate 3 阻断: 首日锚点来源时区或配置/数据契约哈希不匹配")
        breached, reason = ListingAnchorStore().check_dual_anchor_failure(
            listing_anchors, intraday_low, current_price
        )
        if breached:
            return self._block(passport, 3, f"Gate 3 阻断: {reason}")
        passport.gate3_anchor_passed = True
        passport.causal_chain.append("Gate 3 放行: 首日关键双锚守住")

        vwap_ok, vwap_message = evaluate_gate4_vwap(
            vwap, code, current_price, listing_age_sessions, listing_anchors,
            market_as_of_time, max_vwap_stale_seconds,
            {"min_price_support_pct": vwap_support,
             "early_anchor_support_pct": early_anchor_support},
        )
        if not vwap_ok:
            return self._block(passport, 4, vwap_message)
        passport.gate4_vwap_passed = True
        passport.causal_chain.append(vwap_message)

        if not isinstance(trade_plan, IPOTradePlan):
            passport.block_at_gate = 5
            passport.final_decision = "WATCH"
            passport.causal_chain.append("Gate 5 待命: 尚未生成有效 IPOTradePlan")
            passport.diagnostics["next_condition"] = "生成与该标的匹配的有效 IPOTradePlan 后重新评估 Gate 5"
            return passport
        prices = (current_price, trade_plan.buy_zone_min, trade_plan.buy_zone_max)
        if (
            trade_plan.code != code
            or trade_plan.suggested_action not in {"BUY_SCOUT", "BUY_CONFIRM"}
            or any(not _finite(value) or value <= 0 for value in prices)
            or trade_plan.buy_zone_max < trade_plan.buy_zone_min
        ):
            return self._block(passport, 5, "Gate 5 阻断: 交易计划代码或买入区间无效")
        if "BUY" not in allowed_actions:
            return self._block(passport, 5, "Gate 5 阻断: 版本化交易配置未授权 BUY")
        if current_price < trade_plan.buy_zone_min:
            passport.block_at_gate = 5
            passport.final_decision = "WATCH"
            passport.causal_chain.append("Gate 5 观察: 现价低于买入区间下限")
            passport.diagnostics["next_condition"] = (
                f"现价回到买入区间 {trade_plan.buy_zone_min:.3f}–{trade_plan.buy_zone_max:.3f}，并重新通过全部门禁"
            )
            return passport
        if current_price > trade_plan.buy_zone_max:
            return self._block(passport, 5, "Gate 5 阻断: 现价突破买入上限，禁止追高")
        try:
            rr = trade_plan.calculate_rr_now(current_price)
        except (TypeError, ValueError, OverflowError):
            rr = None
        if not _finite(rr) or rr < min_rr:
            return self._block(passport, 5, f"Gate 5 阻断: 动态 RR 无效或低于 {min_rr:.2f}:1")
        if isinstance(horse_rank, bool) or not isinstance(horse_rank, int) or horse_rank != 1:
            passport.block_at_gate = 5
            passport.final_decision = "WATCH"
            passport.causal_chain.append("Gate 5 待命: 赛马排位不是第一名")
            passport.diagnostics["next_condition"] = "赛马排位升至第 1，并在授权时重新通过 Gate 0–5 与 RiskGate"
            return passport

        approved_order = self._evaluate_risk_context(
            code, trade_plan, risk_context, market_as_of_time,
            current_price, requested_position_pct, signal_max_age, risk_clock_skew,
        )
        if isinstance(approved_order, str):
            passport.diagnostics["risk"] = {
                "status": "BLOCKED", "reason": approved_order[:180],
            }
            return self._block(passport, 5, f"Gate 5 风控阻断: {approved_order}")
        passport.diagnostics["risk"] = {
            "status": "APPROVED",
            "order_id": _diagnostic_value(getattr(approved_order, "order_id", None)),
            "price": _diagnostic_value(getattr(approved_order, "price", None)),
            "size_pct": _diagnostic_value(getattr(approved_order, "size_pct", None)),
        }
        try:
            approved_rr = trade_plan.calculate_rr_now(approved_order.price)
        except (TypeError, ValueError, OverflowError):
            approved_rr = None
        if not _finite(approved_rr) or approved_rr < min_rr:
            return self._block(passport, 5, "Gate 5 阻断: RiskGate 批准价格对应 RR 无效或不足")
        passport.gate5_tde_passed = True
        passport.approved_order = approved_order
        passport.final_decision = "ENTRY"
        passport.causal_chain.append(
            f"Gate 5 终审通过: RiskGate 已批准订单 {approved_order.order_id}"
        )
        passport.diagnostics["next_condition"] = (
            "执行前保持 Gate 0–5 与 RiskGate 批准订单一致；授权过期后重新评估"
        )
        return passport

    @staticmethod
    def _evaluate_risk_context(
        code: str,
        plan: IPOTradePlan,
        context: Optional[RiskGateContext],
        market_as_of_time: datetime,
        current_price: float,
        requested_position_pct: Optional[float],
        signal_max_age_seconds: float,
        risk_clock_skew_seconds: float,
    ) -> Any:
        if not isinstance(context, RiskGateContext):
            return "RiskGate 上下文缺失"
        intent, signal = context.intent, context.signal
        try:
            structural_stop = plan.structural_stop
        except (TypeError, ValueError, OverflowError):
            return "TradePlan 结构止损无效"
        if (
            not isinstance(intent, DecisionIntent) or not isinstance(signal, StrategySignal)
            or signal.code != code or intent.code != code or intent.action != "BUY"
            or not _finite(signal.price) or signal.price <= 0
            or not _finite(plan.position_pct) or not 0 < plan.position_pct <= 100
            or not _finite(intent.size_pct) or not 0 < intent.size_pct <= 1.0
            or not _finite(current_price) or current_price <= 0
            or abs(signal.price - current_price) > 0.001
            or not _finite(
                requested_position_pct
                if requested_position_pct is not None else plan.position_pct
            )
            or not 0 < (
                requested_position_pct
                if requested_position_pct is not None else plan.position_pct
            ) <= plan.position_pct
            or abs(
                intent.size_pct - (
                    requested_position_pct
                    if requested_position_pct is not None else plan.position_pct
                ) / 100.0
            ) > 1e-6
            or not _finite(intent.stop_price) or intent.stop_price <= 0
            or not _finite(structural_stop) or structural_stop <= 0
            or abs(intent.stop_price - structural_stop) > 0.001
            or getattr(getattr(intent, "reason", None), "regime", "") == "MANUAL_OVERRIDE"
        ):
            return "信号/意图/TradePlan 身份或仓位单位不匹配"
        if (
            not isinstance(context.limits, RiskLimits)
            or not isinstance(context.held_codes, dict)
            or any(not _finite(value) or value < 0 for value in (
                context.current_stock_exposure,
                context.current_sector_exposure,
                context.current_total_exposure,
            ))
            or not _finite(context.today_pnl_loss)
            or isinstance(context.consecutive_losses, bool)
            or not isinstance(context.consecutive_losses, int)
            or context.consecutive_losses < 0
            or not isinstance(context.current_time, str)
            or not context.current_time.strip()
        ):
            return "RiskGate 限额、敞口或账户时点上下文无效"
        try:
            if market_as_of_time.tzinfo is None or market_as_of_time.utcoffset() is None:
                raise ValueError("行情时点缺少有效 UTC 偏移")
            market_time = market_as_of_time.astimezone(_EXCHANGE_TZ)
            signal_time = datetime.fromisoformat(signal.ts.replace("Z", "+00:00"))
            risk_time = datetime.fromisoformat(context.current_time.replace("Z", "+00:00"))
            if signal_time.tzinfo is None or signal_time.utcoffset() is None:
                raise ValueError("信号时点缺少有效 UTC 偏移")
            if risk_time.tzinfo is None or risk_time.utcoffset() is None:
                raise ValueError("风控时点缺少有效 UTC 偏移")
            signal_age = (market_time - signal_time.astimezone(_EXCHANGE_TZ)).total_seconds()
            risk_skew = abs((market_time - risk_time.astimezone(_EXCHANGE_TZ)).total_seconds())
        except (AttributeError, TypeError, ValueError, OverflowError):
            return "行情、信号或风控时间无效"
        if (
            signal_age < 0 or signal_age > signal_max_age_seconds
            or risk_skew > risk_clock_skew_seconds
        ):
            return "信号超龄/来自未来或风控时钟与行情时点不一致"

        try:
            decision: RiskDecision = evaluate_risk_gate(
                intent,
                signal,
                context.state,
                limits=context.limits,
                held_codes=context.held_codes,
                current_stock_exposure=context.current_stock_exposure,
                current_sector_exposure=context.current_sector_exposure,
                current_total_exposure=context.current_total_exposure,
                today_pnl_loss=context.today_pnl_loss,
                consecutive_losses=context.consecutive_losses,
                current_time=market_time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception:
            return "RiskGate 调用异常"
        order = getattr(decision, "order", None)
        if (
            getattr(decision, "allowed", False) is not True or order is None
            or getattr(decision, "final_action", None) != "BUY"
            or getattr(order, "code", None) != code or getattr(order, "action", None) != "BUY"
            or not _finite(getattr(order, "price", None))
            or not plan.buy_zone_min <= getattr(order, "price", 0.0) <= plan.buy_zone_max
            or not _finite(getattr(order, "size_pct", None))
            or not 0 < order.size_pct <= intent.size_pct
            or not _finite(getattr(order, "stop_price", None))
            or abs(order.stop_price - structural_stop) > 0.001
        ):
            return str(getattr(decision, "reject_context", None) or "RiskGate 未批准合规订单")
        return order

    @staticmethod
    def _block(passport: GatePassport, gate: int, reason: str) -> GatePassport:
        passport.block_at_gate = gate
        passport.final_decision = "BLOCK"
        passport.causal_chain.append(reason)
        passport.diagnostics["next_condition"] = reason[:240]
        return passport
