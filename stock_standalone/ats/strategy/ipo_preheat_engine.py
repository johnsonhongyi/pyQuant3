"""Fail-closed IPO pre-listing prior score with per-input freshness checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional


_REQUIRED_INPUTS = (
    "issue_price",
    "float_shares_wan",
    "pe_ratio",
    "industry_pe_median",
    "online_sub_multiple",
    "winning_rate_pct",
    "scarcity_rank",
    "hot_themes",
)
_EXCHANGE_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _has_valid_offset(value: Any) -> bool:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return False
    try:
        return value.utcoffset() is not None
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class PreHeatConfig:
    watch_candidate_threshold: float
    hot_candidate_threshold: float
    weight_valuation: float
    weight_subscription: float
    weight_scarcity: float
    weight_theme: float
    weight_capital: float
    input_max_age_seconds_by_field: Mapping[str, float]

    def __post_init__(self) -> None:
        weights = (
            self.weight_valuation,
            self.weight_subscription,
            self.weight_scarcity,
            self.weight_theme,
            self.weight_capital,
        )
        numeric_values = weights + (
            self.watch_candidate_threshold,
            self.hot_candidate_threshold,
        )
        if (
            any(not _is_finite_number(value) for value in numeric_values)
            or any(weight < 0 for weight in weights)
            or not math.isclose(sum(weights), 1.0)
        ):
            raise ValueError("PreHeatConfig 权重必须为非负有限值且总和为 1.0")
        if not (
            0 <= self.watch_candidate_threshold
            < self.hot_candidate_threshold
            <= 100
        ):
            raise ValueError("PreHeatConfig 阈值必须满足 0 <= watch < hot <= 100")
        ttl_values = self.input_max_age_seconds_by_field
        if (
            not isinstance(ttl_values, Mapping)
            or set(ttl_values) != set(_REQUIRED_INPUTS)
            or any(
                not _is_finite_number(ttl) or ttl <= 0
                for ttl in ttl_values.values()
            )
        ):
            raise ValueError("PreHeatConfig 必须为每个必需输入配置独立正有限 TTL")
        object.__setattr__(
            self,
            "input_max_age_seconds_by_field",
            MappingProxyType(dict(ttl_values)),
        )

    @staticmethod
    def _config_number(value: Any, field_name: str) -> float:
        if not _is_finite_number(value):
            raise ValueError(f"PreHeatConfig {field_name} 必须为有限数值")
        return float(value)

    @classmethod
    def from_mapping(cls, section: Mapping[str, Any]) -> "PreHeatConfig":
        if not isinstance(section, Mapping):
            raise ValueError("PreHeatConfig 配置节类型无效")
        weights = section.get("weights")
        ttl_values = section.get("input_max_age_seconds_by_field")
        if not isinstance(weights, Mapping) or not isinstance(ttl_values, Mapping):
            raise ValueError("PreHeatConfig weights/TTL 必须为映射")
        try:
            return cls(
                watch_candidate_threshold=cls._config_number(
                    section["watch_candidate_threshold"], "watch_candidate_threshold"
                ),
                hot_candidate_threshold=cls._config_number(
                    section["hot_candidate_threshold"], "hot_candidate_threshold"
                ),
                weight_valuation=cls._config_number(weights["valuation"], "weight_valuation"),
                weight_subscription=cls._config_number(
                    weights["subscription"], "weight_subscription"
                ),
                weight_scarcity=cls._config_number(weights["scarcity"], "weight_scarcity"),
                weight_theme=cls._config_number(weights["theme"], "weight_theme"),
                weight_capital=cls._config_number(
                    weights["capital_structure"], "weight_capital"
                ),
                input_max_age_seconds_by_field={
                    key: cls._config_number(value, f"ttl.{key}")
                    for key, value in ttl_values.items()
                },
            )
        except KeyError as exc:
            raise ValueError(f"PreHeatConfig 缺少必需配置: {exc.args[0]}") from exc


@dataclass(frozen=True)
class IPOPreHeatSnapshot:
    code: str
    name: str
    preheat_score: float = 0.0
    preheat_tier: str = "UNREADY"
    valuation_score: float = 0.0
    subscription_score: float = 0.0
    scarcity_score: float = 0.0
    theme_match_score: float = 0.0
    capital_structure_score: float = 0.0
    is_watch_candidate: bool = False
    data_status: str = "UNREADY"
    valuation_status: str = "UNREADY"
    unready_reason_code: Optional[str] = "DATA_NOT_READY"
    as_of_date: str = ""


class IPOPreHeatEngine:
    def __init__(self, config: PreHeatConfig) -> None:
        if not isinstance(config, PreHeatConfig):
            raise ValueError("缺少已校验的 PreHeatConfig，禁止生成可交易候选")
        self.config = config

    def evaluate(
        self,
        code: str,
        name: str,
        issue_price: float,
        float_shares_wan: float,
        pe_ratio: Optional[float],
        pe_status: str,
        industry_pe_median: float,
        online_sub_multiple: float,
        winning_rate_pct: float,
        scarcity_rank: int = 3,
        hot_themes: Optional[List[str]] = None,
        as_of_date: str = "",
        source_as_of: Optional[Mapping[str, datetime]] = None,
        evaluation_time: Optional[datetime] = None,
    ) -> IPOPreHeatSnapshot:
        def unready(reason: str) -> IPOPreHeatSnapshot:
            return IPOPreHeatSnapshot(
                code=code if isinstance(code, str) else "",
                name=name if isinstance(name, str) else "",
                preheat_tier="UNREADY",
                data_status="UNREADY",
                unready_reason_code=reason,
                as_of_date=as_of_date if isinstance(as_of_date, str) else "",
            )

        if (
            not isinstance(code, str) or not code.strip()
            or not isinstance(name, str) or not name.strip()
        ):
            return unready("identity_missing")
        if not _has_valid_offset(evaluation_time):
            return unready("evaluation_time_invalid")
        assert isinstance(evaluation_time, datetime)
        try:
            evaluation_time = evaluation_time.astimezone(_EXCHANGE_TZ)
        except (OverflowError, OSError, ValueError):
            return unready("evaluation_time_invalid")

        if not isinstance(source_as_of, Mapping) or not set(_REQUIRED_INPUTS).issubset(source_as_of):
            return unready("source_timestamp_missing")
        for field_name in _REQUIRED_INPUTS:
            source_time = source_as_of[field_name]
            if not _has_valid_offset(source_time):
                return unready("source_timestamp_invalid")
            assert isinstance(source_time, datetime)
            try:
                age_seconds = (
                    evaluation_time - source_time.astimezone(_EXCHANGE_TZ)
                ).total_seconds()
            except (OverflowError, OSError, ValueError):
                return unready("source_timestamp_invalid")
            if age_seconds < 0 or age_seconds > self.config.input_max_age_seconds_by_field[field_name]:
                return unready("source_stale_or_future")

        numeric_inputs = {
            "issue_price": (issue_price, 0.0, None),
            "float_shares_wan": (float_shares_wan, 0.0, None),
            "industry_pe_median": (industry_pe_median, 0.0, None),
            "online_sub_multiple": (online_sub_multiple, 0.0, None),
            "winning_rate_pct": (winning_rate_pct, 0.0, 100.0),
        }
        for field_name, (value, minimum, maximum) in numeric_inputs.items():
            if (
                not _is_finite_number(value)
                or value <= minimum
                or (maximum is not None and value > maximum)
            ):
                return unready(f"{field_name}_invalid")
        if (
            isinstance(scarcity_rank, bool)
            or not isinstance(scarcity_rank, int)
            or scarcity_rank not in {1, 2, 3, 4, 5}
        ):
            return unready("scarcity_rank_invalid")
        if (
            not isinstance(hot_themes, list)
            or any(not isinstance(theme, str) or not theme.strip() for theme in hot_themes)
        ):
            return unready("hot_themes_invalid")
        try:
            parsed_as_of_date = date.fromisoformat(as_of_date)
        except (TypeError, ValueError):
            return unready("as_of_date_invalid")
        if parsed_as_of_date > evaluation_time.date():
            return unready("as_of_date_future")

        if (
            not isinstance(pe_status, str)
            or pe_status not in {"OBSERVED", "MISSING_CONFIRMED"}
            or (pe_status == "OBSERVED" and pe_ratio is None)
            or (pe_status == "MISSING_CONFIRMED" and pe_ratio is not None)
        ):
            return unready("pe_status_value_mismatch")
        if pe_ratio is not None and not _is_finite_number(pe_ratio):
            return unready("pe_ratio_invalid")

        valuation_status = "READY"
        if pe_ratio is None or pe_ratio <= 0:
            valuation_score = 0.0
            valuation_status = "CONSERVATIVE_MISSING_PE"
        else:
            pe_discount = (industry_pe_median - pe_ratio) / max(industry_pe_median, 1.0)
            valuation_score = max(0.0, min(25.0, 12.5 + pe_discount * 25.0))

        sub_ratio_score = min(15.0, math.log10(max(online_sub_multiple, 1.0)) * 3.75)
        win_rate_score = max(0.0, min(10.0, (8.0 - winning_rate_pct) * 1.25))
        subscription_score = max(0.0, min(25.0, sub_ratio_score + win_rate_score))
        scarcity_score = {1: 20.0, 2: 15.0, 3: 10.0, 4: 5.0, 5: 0.0}[scarcity_rank]
        theme_score = 15.0 if hot_themes and any(theme in name for theme in hot_themes) else 5.0
        if float_shares_wan < 2000:
            capital_score = 10.0
        elif float_shares_wan < 4000:
            capital_score = 7.0
        elif float_shares_wan < 8000:
            capital_score = 4.0
        else:
            capital_score = 1.0

        total = 100.0 * (
            self.config.weight_valuation * (valuation_score / 25.0)
            + self.config.weight_subscription * (subscription_score / 25.0)
            + self.config.weight_scarcity * (scarcity_score / 20.0)
            + self.config.weight_theme * (theme_score / 20.0)
            + self.config.weight_capital * (capital_score / 10.0)
        )
        if total >= self.config.hot_candidate_threshold:
            tier = "PRE_HOT"
        elif total >= self.config.watch_candidate_threshold:
            tier = "PRE_WARM"
        else:
            tier = "PRE_COLD"

        return IPOPreHeatSnapshot(
            code=code,
            name=name,
            preheat_score=round(total, 1),
            preheat_tier=tier,
            valuation_score=round(valuation_score, 1),
            subscription_score=round(subscription_score, 1),
            scarcity_score=round(scarcity_score, 1),
            theme_match_score=round(theme_score, 1),
            capital_structure_score=round(capital_score, 1),
            is_watch_candidate=total >= self.config.watch_candidate_threshold,
            data_status="READY",
            valuation_status=valuation_status,
            as_of_date=as_of_date,
        )
