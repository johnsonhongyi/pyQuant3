"""Versioned per-field source and freshness contracts for IPO decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DATA_CONTRACT_SCHEMA_VERSION = "2"
LRRM_REQUIRED_FIELDS = (
    "volume_percentile_20d",
    "volume_percentile_60d",
    "advance_decline_ratio",
    "limit_down_count",
    "financing_balance_change",
    "limit_up_break_rate",
    "high_volatility_amount_share",
    "index_relative_strength",
    "ipo_amount_share",
    "theme_concentration",
    "listing_supply_pace",
)
REGIME_REQUIRED_FIELDS = (
    "d1_positive_rate",
    "d1_top_rate",
    "d2_positive_rate",
    "d3_positive_rate",
    "d1_d2_max_drawdown",
    "limit_down_rate",
    "new_stock_relative_strength",
    "close_position",
    "new_stock_turnover_median",
    "new_stock_innovation_high_rate",
)
PREHEAT_REQUIRED_FIELDS = (
    "issue_price",
    "float_shares_wan",
    "pe_ratio",
    "industry_pe_median",
    "online_sub_multiple",
    "winning_rate_pct",
    "scarcity_rank",
    "hot_themes",
)
LIVE_HEAT_REQUIRED_FIELDS = (
    "ret_pct",
    "turnover_pct",
    "price_vwap_dist_pct",
    "open_premium_pct",
    "slope_deg",
    "session_high",
    "session_low",
    "current_price",
    "turnover_climb_speed",
    "minutes_above_vwap_ratio",
    "pullback_from_peak_pct",
    "halt_count",
)
IPO_REQUIRED_FIELDS = (
    LRRM_REQUIRED_FIELDS + REGIME_REQUIRED_FIELDS + PREHEAT_REQUIRED_FIELDS
    + LIVE_HEAT_REQUIRED_FIELDS
)


def _valid_zone(name: Any) -> bool:
    if not isinstance(name, str) or not name.strip():
        return False
    try:
        ZoneInfo(name)
        return True
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return False


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class MetricFieldContract:
    field_id: str
    source_id: str
    source_version: str
    value_key: str
    as_of_key: str
    available_at_key: str
    source_timezone: str
    max_age_seconds: float
    value_type: str
    unit: str
    window: str
    missing_policy: str
    accepted_sources: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for key in (
            "field_id", "source_id", "source_version", "value_key",
            "as_of_key", "available_at_key",
        ):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"指标契约缺少 {key}: {self.field_id!r}")
        if not _valid_zone(self.source_timezone):
            raise ValueError(f"指标 {self.field_id} 的 IANA source_timezone 无效")
        if not _finite_number(self.max_age_seconds) or self.max_age_seconds <= 0:
            raise ValueError(f"指标 {self.field_id} 必须配置正有限 TTL")
        if not isinstance(self.value_type, str) or self.value_type not in {
            "number", "integer", "boolean", "string", "any"
        }:
            raise ValueError(f"指标 {self.field_id} 的 value_type 无效")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError(f"指标 {self.field_id} 必须声明单位")
        if not isinstance(self.window, str) or not self.window.strip():
            raise ValueError(f"指标 {self.field_id} 必须声明统计窗口/可用时点")
        if not isinstance(self.missing_policy, str) or self.missing_policy not in {
            "BLOCK", "ALLOW_CONFIRMED_MISSING"
        }:
            raise ValueError(f"指标 {self.field_id} 的 missing_policy 无效")
        if any(
            not isinstance(identity, tuple) or len(identity) != 2
            or not all(isinstance(item, str) and item.strip() for item in identity)
            for identity in self.accepted_sources
        ):
            raise ValueError(f"指标 {self.field_id} 的备选来源契约无效")

    @classmethod
    def from_mapping(cls, field_id: str, value: Mapping[str, Any]) -> "MetricFieldContract":
        if not isinstance(value, Mapping):
            raise ValueError(f"指标 {field_id} 的契约必须为映射")
        accepted = value.get("accepted_sources", ())
        if not isinstance(accepted, (list, tuple)) or any(not isinstance(item, Mapping) for item in accepted):
            raise ValueError(f"指标 {field_id} 的备选来源必须为来源对象列表")
        try:
            return cls(
                field_id=field_id,
                source_id=value["source_id"],
                source_version=value["source_version"],
                value_key=value["value_key"],
                as_of_key=value["as_of_key"],
                available_at_key=value["available_at_key"],
                source_timezone=value["source_timezone"],
                max_age_seconds=value["max_age_seconds"],
                value_type=value["value_type"],
                unit=value["unit"],
                window=value["window"],
                missing_policy=value["missing_policy"],
                accepted_sources=tuple((item["source_id"], item["source_version"]) for item in accepted),
            )
        except KeyError as exc:
            raise ValueError(f"指标 {field_id} 缺少契约字段: {exc.args[0]}") from exc

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "value_key": self.value_key,
            "as_of_key": self.as_of_key,
            "available_at_key": self.available_at_key,
            "source_timezone": self.source_timezone,
            "max_age_seconds": self.max_age_seconds,
            "value_type": self.value_type,
            "unit": self.unit,
            "window": self.window,
            "missing_policy": self.missing_policy,
            "accepted_sources": [
                {"source_id": source_id, "source_version": source_version}
                for source_id, source_version in self.accepted_sources
            ],
        }


@dataclass(frozen=True)
class FieldCheck:
    field_id: str
    status: str
    usable: bool
    value: Any = None
    source_as_of_utc: Optional[datetime] = None
    reason_code: Optional[str] = None


class IPODataContractSet:
    """Validate a complete source dictionary and field observations fail-closed."""

    def __init__(
        self,
        config_version: str,
        fields: Mapping[str, MetricFieldContract],
        required_fields: Tuple[str, ...] = IPO_REQUIRED_FIELDS,
    ) -> None:
        if not isinstance(config_version, str) or not config_version.strip():
            raise ValueError("数据字典必须声明 config_version")
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError("数据字典 fields 必须为非空映射")
        if (
            not isinstance(required_fields, tuple)
            or not required_fields
            or any(not isinstance(field, str) or not field.strip() for field in required_fields)
            or len(required_fields) != len(set(required_fields))
        ):
            raise ValueError("required_fields 必须是唯一且非空的字段元组")
        missing = set(required_fields) - set(fields)
        if missing:
            raise ValueError(f"数据字典缺少必需指标: {', '.join(sorted(missing))}")
        if any(
            not isinstance(contract, MetricFieldContract)
            or key != contract.field_id
            for key, contract in fields.items()
        ):
            raise ValueError("数据字典键必须与 field_id 一致")
        self.config_version = config_version
        self.fields = MappingProxyType(dict(fields))
        self.required_fields = tuple(required_fields)
        self.config_hash = self._build_hash()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IPODataContractSet":
        if not isinstance(value, Mapping):
            raise ValueError("缺少版本化 IPO 数据字典")
        schema_version = value.get("schema_version")
        if schema_version != DATA_CONTRACT_SCHEMA_VERSION:
            raise ValueError(f"不支持的数据字典 schema_version: {schema_version!r}")
        raw_fields = value.get("fields")
        if not isinstance(raw_fields, Mapping):
            raise ValueError("数据字典 fields 必须为映射")
        raw_required_fields = value.get("required_fields", IPO_REQUIRED_FIELDS)
        if not isinstance(raw_required_fields, (list, tuple)):
            raise ValueError("数据字典 required_fields 必须为列表")
        fields = {
            str(field_id): MetricFieldContract.from_mapping(str(field_id), item)
            for field_id, item in raw_fields.items()
        }
        contract_set = cls(
            value.get("config_version"), fields, tuple(raw_required_fields)
        )
        declared_hash = value.get("config_hash")
        if declared_hash is not None and declared_hash != contract_set.config_hash:
            raise ValueError("数据字典 config_hash 与内容不一致")
        return contract_set

    def _build_hash(self) -> str:
        payload = {
            "schema_version": DATA_CONTRACT_SCHEMA_VERSION,
            "config_version": self.config_version,
            "required_fields": list(self.required_fields),
            "fields": {
                field_id: contract.to_dict()
                for field_id, contract in sorted(self.fields.items())
            },
        }
        try:
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("数据字典必须可稳定序列化") from exc
        return hashlib.sha256(serialized).hexdigest()

    def to_manifest(self) -> Dict[str, Any]:
        """Return the exact versioned source dictionary covered by config_hash."""
        return {
            "schema_version": DATA_CONTRACT_SCHEMA_VERSION,
            "config_version": self.config_version,
            "required_fields": list(self.required_fields),
            "fields": {
                field_id: contract.to_dict()
                for field_id, contract in sorted(self.fields.items())
            },
            "config_hash": self.config_hash,
        }

    def validate_observations(
        self,
        observations: Mapping[str, Mapping[str, Any]],
        evaluation_time: datetime,
        *,
        allow_naive_source_time: bool = False,
    ) -> Tuple[bool, Mapping[str, FieldCheck]]:
        """Validate every required field; missing or stale input keeps the set closed."""
        if not isinstance(observations, Mapping):
            return False, MappingProxyType({
                field_id: FieldCheck(field_id, "UNREADY", False, reason_code="observations_invalid")
                for field_id in self.required_fields
            })
        checks = {
            field_id: self.validate_observation(
                field_id,
                observations.get(field_id),
                evaluation_time,
                allow_naive_source_time=allow_naive_source_time,
            )
            for field_id in self.required_fields
        }
        frozen_checks = MappingProxyType(checks)
        return all(check.usable for check in checks.values()), frozen_checks

    @staticmethod
    def _parse_timestamp(value: Any, source_timezone: str, allow_naive: bool) -> datetime:
        if isinstance(value, str):
            value = value.strip()
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            try:
                value = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("timestamp_invalid") from exc
        if not isinstance(value, datetime):
            raise ValueError("timestamp_invalid")
        try:
            if value.tzinfo is None:
                if not allow_naive:
                    raise ValueError("timestamp_offset_missing")
                source_tz = ZoneInfo(source_timezone)
                candidates = []
                for fold in (0, 1):
                    candidate = value.replace(tzinfo=source_tz, fold=fold)
                    round_trip = candidate.astimezone(timezone.utc).astimezone(source_tz)
                    if round_trip.replace(tzinfo=None) == value:
                        candidates.append(candidate)
                if not candidates:
                    raise ValueError("timestamp_nonexistent_local_time")
                if len(candidates) > 1 and candidates[0].utcoffset() != candidates[1].utcoffset():
                    raise ValueError("timestamp_ambiguous_local_time")
                value = candidates[0]
            elif value.utcoffset() is None:
                raise ValueError("timestamp_offset_missing")
            return value.astimezone(timezone.utc)
        except (OverflowError, OSError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            if isinstance(exc, ValueError) and str(exc) in {
                "timestamp_offset_missing", "timestamp_invalid"
            }:
                raise
            raise ValueError("timestamp_invalid") from exc

    @staticmethod
    def _value_matches(contract: MetricFieldContract, value: Any) -> bool:
        if contract.value_type == "number":
            return _finite_number(value)
        if contract.value_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if contract.value_type == "boolean":
            return isinstance(value, bool)
        if contract.value_type == "string":
            return isinstance(value, str)
        return True

    def validate_observation(
        self,
        field_id: str,
        observation: Mapping[str, Any],
        evaluation_time: datetime,
        *,
        allow_naive_source_time: bool = False,
    ) -> FieldCheck:
        if not isinstance(field_id, str):
            return FieldCheck(str(field_id), "UNREADY", False, reason_code="field_id_invalid")
        contract = self.fields.get(field_id)
        if contract is None:
            return FieldCheck(field_id, "UNREADY", False, reason_code="contract_missing")
        if not isinstance(observation, Mapping):
            return FieldCheck(field_id, "UNREADY", False, reason_code="observation_missing")
        try:
            evaluation_utc = self._parse_timestamp(evaluation_time, "UTC", allow_naive=False)
        except ValueError:
            return FieldCheck(field_id, "UNREADY", False, reason_code="evaluation_time_invalid")

        status = observation.get("status")
        if not isinstance(status, str) or status not in {
            "OBSERVED", "MISSING_CONFIRMED", "UNREADY"
        }:
            return FieldCheck(field_id, "UNREADY", False, reason_code="observation_status_invalid")
        if status == "UNREADY":
            return FieldCheck(field_id, "UNREADY", False, reason_code="source_unready")
        identity = (observation.get("source_id"), observation.get("source_version"))
        if identity != (contract.source_id, contract.source_version) and identity not in contract.accepted_sources:
            return FieldCheck(field_id, "UNREADY", False, reason_code="source_identity_mismatch")
        if observation.get("source_timezone") != contract.source_timezone:
            return FieldCheck(field_id, "UNREADY", False, reason_code="source_timezone_mismatch")

        raw_time = observation.get(contract.as_of_key)
        if raw_time is None:
            return FieldCheck(field_id, "UNREADY", False, reason_code="source_timestamp_missing")
        try:
            source_utc = self._parse_timestamp(
                raw_time, contract.source_timezone, allow_naive_source_time
            )
        except ValueError as exc:
            return FieldCheck(
                field_id, "UNREADY", False,
                reason_code=str(exc) if str(exc).startswith("timestamp_") else "timestamp_invalid",
            )
        age_seconds = (evaluation_utc - source_utc).total_seconds()
        if age_seconds < 0:
            return FieldCheck(field_id, "UNREADY", False, reason_code="source_timestamp_future")
        if age_seconds > contract.max_age_seconds:
            return FieldCheck(field_id, "UNREADY", False, reason_code="source_stale")
        raw_available_at = observation.get(contract.available_at_key)
        if raw_available_at is None:
            return FieldCheck(field_id, "UNREADY", False, reason_code="available_at_missing")
        try:
            available_at_utc = self._parse_timestamp(
                raw_available_at, contract.source_timezone, allow_naive_source_time
            )
        except ValueError:
            return FieldCheck(field_id, "UNREADY", False, reason_code="available_at_invalid")
        if available_at_utc > evaluation_utc:
            return FieldCheck(field_id, "UNREADY", False, reason_code="available_at_after_cutoff")

        value = observation.get(contract.value_key)
        if status == "MISSING_CONFIRMED":
            if value is not None or contract.missing_policy != "ALLOW_CONFIRMED_MISSING":
                return FieldCheck(field_id, "UNREADY", False, reason_code="missing_policy_violation")
            return FieldCheck(
                field_id, "MISSING_CONFIRMED", True, None, source_utc,
                reason_code="confirmed_missing",
            )
        if value is None:
            return FieldCheck(field_id, "UNREADY", False, reason_code="observed_value_missing")
        if not self._value_matches(contract, value):
            return FieldCheck(field_id, "UNREADY", False, reason_code="value_type_invalid")
        return FieldCheck(field_id, "OBSERVED", True, value, source_utc)


def build_decision_config_hash(
    config_version: str,
    decision_config: Mapping[str, Any],
    data_contract: IPODataContractSet,
) -> str:
    """Bind every threshold/config value and source timezone contract to a decision hash."""
    if not isinstance(config_version, str) or not config_version.strip():
        raise ValueError("决策配置必须声明 config_version")
    if not isinstance(decision_config, Mapping):
        raise ValueError("决策配置内容必须为映射")
    if not isinstance(data_contract, IPODataContractSet):
        raise ValueError("决策配置必须绑定有效数据字典")
    payload = {
        "schema_version": "IPO_DECISION_CONFIG_1",
        "config_version": config_version,
        "decision_config": dict(decision_config),
        "data_contract": data_contract.to_manifest(),
    }
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("决策配置必须可稳定序列化") from exc
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class IPODecisionConfigSnapshot:
    """Immutable top-level snapshot loaded from the versioned YAML source."""

    config_version: str
    decision_config: Mapping[str, Any]
    data_contract: IPODataContractSet
    config_hash: str

    @classmethod
    def from_yaml(cls, path: str) -> "IPODecisionConfigSnapshot":
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("当前运行环境缺少 PyYAML，IPO 配置保持未就绪") from exc
        try:
            with Path(path).open("r", encoding="utf-8") as stream:
                document = yaml.safe_load(stream)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(f"无法读取版本化 IPO YAML 配置: {path}") from exc
        if not isinstance(document, Mapping):
            raise ValueError("IPO YAML 根节点必须是映射")
        config_version = document.get("version")
        if not isinstance(config_version, str) or not config_version.strip():
            raise ValueError("IPO YAML 缺少非空 version")
        data_contract = IPODataContractSet.from_mapping(document.get("data_contract"))
        raw_decision_config = document.get("decision_config")
        if raw_decision_config is None:
            raw_decision_config = {
                key: value for key, value in document.items()
                if key not in {"version", "data_contract", "decision_config_hash"}
            }
        if not isinstance(raw_decision_config, Mapping) or not raw_decision_config:
            raise ValueError("IPO YAML 缺少 decision_config 阈值映射")

        # PreHeat receives the same per-field TTLs as the source contract, never
        # a second independently maintained freshness table.
        preheat = raw_decision_config.get("ipo_preheat")
        if not isinstance(preheat, Mapping):
            raise ValueError("IPO YAML 缺少 ipo_preheat 配置")
        raw_preheat_ttls = preheat.get("input_max_age_seconds_by_field")
        expected_preheat_ttls = {
            field_id: data_contract.fields[field_id].max_age_seconds
            for field_id in PREHEAT_REQUIRED_FIELDS
            if field_id in data_contract.fields
        }
        if (
            not isinstance(raw_preheat_ttls, Mapping)
            or dict(raw_preheat_ttls) != expected_preheat_ttls
            or set(expected_preheat_ttls) != set(PREHEAT_REQUIRED_FIELDS)
        ):
            raise ValueError("PreHeat 逐字段 TTL 必须与版本化来源契约完全一致")
        try:
            from ats.strategy.ipo_preheat_engine import PreHeatConfig

            PreHeatConfig.from_mapping(preheat)
        except (ImportError, TypeError, ValueError) as exc:
            raise ValueError("ipo_preheat 配置校验失败") from exc

        frozen_config = MappingProxyType(dict(raw_decision_config))
        config_hash = build_decision_config_hash(
            config_version, frozen_config, data_contract
        )
        declared_hash = document.get("decision_config_hash")
        if declared_hash is not None and declared_hash != config_hash:
            raise ValueError("IPO YAML decision_config_hash 与配置内容不一致")
        return cls(config_version, frozen_config, data_contract, config_hash)

    def verify_integrity(self) -> bool:
        try:
            return self.config_hash == build_decision_config_hash(
                self.config_version, self.decision_config, self.data_contract
            )
        except ValueError:
            return False

    def gate_context_fields(self) -> Dict[str, Any]:
        """Return the identity fields expected by GateOrchestrator."""
        if not self.verify_integrity():
            raise ValueError("IPO 决策配置快照完整性校验失败")
        return {
            "configuration_version": self.config_version,
            "configuration_hash": self.config_hash,
            "data_contract_hash": self.data_contract.config_hash,
            "data_contract": self.data_contract,
            "decision_config": dict(self.decision_config),
        }
