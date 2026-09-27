"""Create the versioned R9 configuration skeleton with execution gates closed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ats.strategy.ipo_data_contracts import (  # noqa: E402
    DATA_CONTRACT_SCHEMA_VERSION,
    IPO_REQUIRED_FIELDS,
    IPODecisionConfigSnapshot,
    IPODataContractSet,
    MetricFieldContract,
    build_decision_config_hash,
)
from ats.strategy.ipo_source_orchestrator import source_route  # noqa: E402


_PREHEAT_TTLS = {
    "issue_price": 86_400,
    "float_shares_wan": 2_592_000,
    "pe_ratio": 604_800,
    "industry_pe_median": 86_400,
    "online_sub_multiple": 86_400,
    "winning_rate_pct": 86_400,
    "scarcity_rank": 86_400,
    "hot_themes": 21_600,
}
_LIVE_TTLS = {field: 30 for field in (
    "ret_pct", "turnover_pct", "price_vwap_dist_pct", "open_premium_pct",
    "slope_deg", "session_high", "session_low", "current_price",
    "turnover_climb_speed", "minutes_above_vwap_ratio",
    "pullback_from_peak_pct", "halt_count",
)}
_INTEGER_FIELDS = {"limit_down_count", "scarcity_rank", "halt_count"}
_STRING_ARRAY_FIELDS = {"hot_themes"}
_UNITS = {
    "issue_price": "CNY/share", "float_shares_wan": "10k shares",
    "pe_ratio": "ratio", "industry_pe_median": "ratio",
    "online_sub_multiple": "multiple", "winning_rate_pct": "%",
    "scarcity_rank": "rank 1-5", "hot_themes": "theme names",
    "ret_pct": "%", "turnover_pct": "%", "price_vwap_dist_pct": "%",
    "open_premium_pct": "%", "slope_deg": "degree",
    "session_high": "CNY/share", "session_low": "CNY/share",
    "current_price": "CNY/share", "turnover_climb_speed": "%/minute",
    "minutes_above_vwap_ratio": "%", "pullback_from_peak_pct": "%",
    "halt_count": "count", "volume_percentile_20d": "percentile",
    "volume_percentile_60d": "percentile", "advance_decline_ratio": "ratio",
    "limit_down_count": "count", "financing_balance_change": "%",
    "limit_up_break_rate": "%", "high_volatility_amount_share": "%",
    "index_relative_strength": "%", "ipo_amount_share": "%",
    "theme_concentration": "HHI", "listing_supply_pace": "listings/20 calendar days",
    "d1_positive_rate": "%", "d1_top_rate": "%", "d2_positive_rate": "%",
    "d3_positive_rate": "%", "d1_d2_max_drawdown": "%",
    "limit_down_rate": "%", "new_stock_relative_strength": "%",
    "close_position": "ratio 0-1", "new_stock_turnover_median": "%",
    "new_stock_innovation_high_rate": "%",
}


def _source_identity(field_id: str) -> tuple[str, str]:
    if field_id == "issue_price":
        return "eastmoney.datacenter-web.RPTA_APP_IPOAPPLY", "ipo_calendar.v1"
    if field_id == "float_shares_wan":
        return "tdx.finance_info", "pytdx.fin_info.v1"
    if field_id == "advance_decline_ratio":
        return "eastmoney.push2.market_quotes", "a_share_breadth.v1"
    if field_id == "limit_down_count":
        # The current publisher estimates every board with a single 9.8% bound.
        # Keep its output incompatible until board/ST/IPO-session rules are verified.
        return "market_sentiment_fsm.board_aware_limit_down", "board_limit_down.v1"
    if field_id == "limit_up_break_rate":
        return "eastmoney.push2ex.limit_up_pool", "eastmoney_limit_up_break.v1"
    if field_id == "theme_concentration":
        return "eastmoney.push2.market_quotes", "a_share_turnover_metrics.v1"
    if field_id in {"pe_ratio", "online_sub_multiple", "winning_rate_pct"}:
        return "eastmoney.ipo_issuance_results", "RPTA_APP_IPOAPPLY.all.v1"
    if field_id == "industry_pe_median":
        return "eastmoney.push2.industry_valuation", "a_share_industry_pe.v1"
    if field_id == "advance_decline_ratio":
        return "eastmoney.push2.market_quotes", "a_share_breadth.v1"
    if field_id in {"ret_pct", "turnover_pct", "current_price", "session_high", "session_low"}:
        return "tencent.quote_snapshot", "gtimg_hq.v1"
    if field_id == "price_vwap_dist_pct":
        return "tencent.derived.quote_vwap", "quote_amount_volume.v1"
    if field_id == "minutes_above_vwap_ratio":
        return "eastmoney.push2his.minute_kline", "minute_kline.v1"
    if field_id == "pullback_from_peak_pct":
        return "tencent.derived.quote_session_peak", "quote_with_session_high.v1"
    if field_id == "open_premium_pct":
        return "tencent.derived.issue_price_premium", "quote_plus_ipo.v1"
    if field_id in {
        "float_shares_wan", "slope_deg", "turnover_climb_speed", "halt_count", "volume_percentile_20d",
        "volume_percentile_60d", "advance_decline_ratio", "limit_down_count",
        "limit_up_break_rate", "high_volatility_amount_share", "index_relative_strength",
        "ipo_amount_share", "theme_concentration",
    }:
        if field_id in {"volume_percentile_20d", "volume_percentile_60d"}:
            return "tdx.daily_index_kline", "sh_sz_index_turnover.v1"
        if field_id in {"high_volatility_amount_share", "ipo_amount_share"}:
            return "tdx.market_observation_pipeline", "tdx_a_share_snapshot.v1"
        return "tdx.market_observation_pipeline", "planned.v1"
    if field_id == "listing_supply_pace":
        return "eastmoney.datacenter-web.RPTA_APP_IPOAPPLY", "ipo_listing_supply.v1"
    if field_id == "scarcity_rank":
        return "ipo.cross_section_analytics", "planned.v1"
    if field_id == "hot_themes":
        return "ipo.announcement_theme_pipeline", "planned.v1"
    return "ipo.matured_cohort_pipeline", "planned.v1"


def _accepted_sources(field_id: str) -> tuple[tuple[str, str], ...]:
    if field_id in {"high_volatility_amount_share", "ipo_amount_share"}:
        return (("eastmoney.push2.market_quotes", "a_share_turnover_metrics.v1"),)
    if field_id == "advance_decline_ratio":
        return (("tdx.daily_index_breadth", "index_up_down_count.v1"),)
    if field_id in {"ret_pct", "turnover_pct", "current_price", "session_high", "session_low"}:
        return (("tdx.quote_snapshot", "tdx_hq.quote.v1"),)
    if field_id == "price_vwap_dist_pct":
        return (("tdx.derived.quote_vwap", "tdx_quote_amount_volume.v1"),)
    if field_id == "minutes_above_vwap_ratio":
        return (("tdx.minute_bars", "intraday_1m.v1"),)
    if field_id == "pullback_from_peak_pct":
        return (("tdx.derived.session_peak_pullback", "tdx_quote_with_session_high.v1"),)
    if field_id == "open_premium_pct":
        return (("tdx.derived.issue_price_premium", "tdx_quote_plus_ipo.v1"),)
    return ()


def _ttl(field_id: str) -> int:
    if field_id in _PREHEAT_TTLS:
        return _PREHEAT_TTLS[field_id]
    if field_id in _LIVE_TTLS:
        return _LIVE_TTLS[field_id]
    if field_id == "limit_up_break_rate":
        return 3_600
    return 86_400


def build_configuration() -> Dict[str, Any]:
    fields: Dict[str, MetricFieldContract] = {}
    for field_id in IPO_REQUIRED_FIELDS:
        source_id, source_version = _source_identity(field_id)
        value_type = (
            "integer" if field_id in _INTEGER_FIELDS else
            "any" if field_id in _STRING_ARRAY_FIELDS else "number"
        )
        fields[field_id] = MetricFieldContract(
            field_id=field_id,
            source_id=source_id,
            source_version=source_version,
            value_key="value",
            as_of_key="as_of_time",
            available_at_key="available_at",
            source_timezone="Asia/Shanghai",
            max_age_seconds=float(_ttl(field_id)),
            value_type=value_type,
            unit=_UNITS[field_id],
            window=source_route(field_id)["route"],
            missing_policy="BLOCK",
            accepted_sources=_accepted_sources(field_id),
        )
    contract_set = IPODataContractSet(
        config_version="ipo-r9-source-contract-draft-5-eastmoney-market-sources",
        fields=fields,
    )
    ttl_by_field = {field: fields[field].max_age_seconds for field in (
        "issue_price", "float_shares_wan", "pe_ratio", "industry_pe_median",
        "online_sub_multiple", "winning_rate_pct", "scarcity_rank", "hot_themes",
    )}
    decision = {
        "implementation_status": "DRAFT_FAIL_CLOSED",
        "source_registry": {
            field_id: {
                **source_route(field_id),
                "source_id": fields[field_id].source_id,
                "source_version": fields[field_id].source_version,
                "source_timezone": fields[field_id].source_timezone,
                "ttl_seconds": fields[field_id].max_age_seconds,
                "accepted_sources": [
                    {"source_id": source_id, "source_version": source_version}
                    for source_id, source_version in fields[field_id].accepted_sources
                ],
                "verified": field_id in {
                    "issue_price", "pe_ratio", "online_sub_multiple",
                    "winning_rate_pct", "float_shares_wan", "listing_supply_pace",
                },
            }
            for field_id in IPO_REQUIRED_FIELDS
        },
        "ipo_preheat": {
            "watch_candidate_threshold": 55.0,
            "hot_candidate_threshold": 75.0,
            "weights": {
                "valuation": 0.25, "subscription": 0.25, "scarcity": 0.20,
                "theme": 0.20, "capital_structure": 0.10,
            },
            "input_max_age_seconds_by_field": ttl_by_field,
        },
        "ipo_live_heat": {
            "overheat_threshold_warning": 15.0,
            "overheat_threshold_veto": 35.0,
            "exhaustion_risk_threshold_veto": 45.0,
            "close_location_veto": 0.40,
            "turnover_tracker": {
                "lunch_start": "11:30", "lunch_end": "13:00",
                "max_sample_gap_trading_minutes": 30.0,
            },
        },
        "vwap_freshness": {"max_stale_seconds": 120},
        "ipo_regime": {
            "lookback_stocks": 10, "lookback_days": 20,
            "transition_thresholds": {
                "distribution_to_repair": {"d1_positive_rate_min": 0.40, "limit_down_rate_max": 0.10},
                "repair_to_continuation": {"d1_positive_rate_min": 0.55, "new_high_ratio_min": 0.40},
                "continuation_to_mania": {"d1_positive_rate_min": 0.80, "turnover_extreme_pct": 60.0},
                "mania_to_exhaustion": {"first_day_peak_ratio_min": 0.40},
                "exhaustion_to_distribution": {"d1_positive_rate_max": 0.30},
            },
        },
        "lrrm": {
            "amount_shock_percentile": 5, "amount_tight_percentile": 20,
            "amount_loose_percentile": 80, "advance_decline_shock": 0.20,
            "limit_down_shock": 30,
        },
        "t1_carry": {
            "allow_threshold": 65.0, "caution_threshold": 40.0,
            "adjustment_bounds": {"max_positive": 10, "max_negative": -25},
        },
        "listing_anchors": {"d0_open_break_pct": 0.0},
        "vwap_execution": {"min_price_support_pct": 0.0, "early_anchor_support_pct": 0.0},
        "trade_gate": {
            "min_risk_reward": 2.5, "signal_max_age_seconds": 30.0,
            "risk_clock_skew_seconds": 5.0, "authorization_ttl_seconds": 10.0,
            "allowed_actions": ["WATCH"],
        },
    }
    config_version = "1.1-R9-implementation-draft.3"
    config_hash = build_decision_config_hash(config_version, decision, contract_set)
    return {
        "version": config_version,
        "decision_config": decision,
        "data_contract": contract_set.to_manifest(),
        "decision_config_hash": config_hash,
    }


def _dump_yaml(payload: Dict[str, Any]) -> str:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("生成 YAML 需要 PyYAML") from exc
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=110)


def _write_once(path: Path, content: str, force: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return False
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 R9 版本化配置骨架；授权门禁保持关闭")
    parser.add_argument("--force", action="store_true", help="覆盖已有配置文件")
    args = parser.parse_args()
    config = build_configuration()
    config_path = APP_ROOT / "config" / "ipo_sentiment.yaml"
    config_written = _write_once(config_path, _dump_yaml(config), args.force)
    anchors = {"schema_version": "1", "anchors": {}}
    anchors_written = _write_once(
        APP_ROOT / "config" / "listing_anchors.json",
        json.dumps(anchors, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        args.force,
    )
    llm_config = {
        "version": "1.1-R9",
        "llm_settings": {
            "active_backend": "antigravity_cli", "allow_remote": False,
            "request_timeout_seconds": 30.0, "cache_ttl_seconds": 60,
            "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 30},
            "remote_egress": {"approval_id": "", "destination": "", "policy_version": "", "field_allowlist_by_agent": {}},
        },
        "backends": {
            "antigravity_cli": {"execution_mode": "remote_api", "enabled": False, "cli_path": "agy", "scratch_cwd": ""},
            "codex_cli": {"execution_mode": "remote_api", "enabled": False, "bin_path": "codex", "scratch_cwd": ""},
            "antigravity_sdk": {"execution_mode": "local_litert", "model_path": "", "model_sha256": "", "model_id": ""},
            "ollama_http": {"base_url": "http://127.0.0.1:11434", "model": ""},
        },
    }
    llm_written = _write_once(
        APP_ROOT / "config" / "llm_config.yaml", _dump_yaml(llm_config), args.force
    )
    acceptance = {
        "schema_version": "ipo-stage-acceptance.v1",
        "stages": {
            str(index): {"status": "PENDING", "evidence": []}
            for index in range(5)
        },
    }
    acceptance_written = _write_once(
        APP_ROOT / "config" / "ipo_stage_acceptance.json",
        json.dumps(acceptance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        args.force,
    )
    try:
        loaded = IPODecisionConfigSnapshot.from_yaml(str(config_path))
        valid = loaded.verify_integrity()
        config_hash = loaded.config_hash
    except Exception as exc:
        valid = False
        config_hash = f"INVALID:{type(exc).__name__}"
    print(json.dumps({
        "status": "READY_FOR_REVIEW" if valid else "INVALID",
        "runtime_authorized": False,
        "config_hash": config_hash,
        "files_written": {
            "ipo_sentiment.yaml": config_written,
            "listing_anchors.json": anchors_written,
            "llm_config.yaml": llm_written,
            "ipo_stage_acceptance.json": acceptance_written,
        },
        "required_fields": len(IPO_REQUIRED_FIELDS),
    }, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
