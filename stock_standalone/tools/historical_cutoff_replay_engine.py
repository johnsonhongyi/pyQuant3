"""Versioned, timezone-aware historical cut-off replay primitives.

The replay source manifest is deliberately required: naive source timestamps
must never inherit the machine's local timezone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


DEFAULT_EXCHANGE_TIMEZONE = "Asia/Shanghai"
REPLAY_MANIFEST_VERSION = "1"
REPLAY_REPORT_SCHEMA_VERSION = "ipo_historical_replay_report.v2"
REPLAY_REPORT_INDEX_VERSION = "r9.replay-report-index.v2"
MAX_REPLAY_REPORT_BYTES = 512 * 1024 * 1024
REPLAY_EFFECT_METRICS = (
    "regime_transition_accuracy", "high_carry_vs_low_carry_spread",
    "bad_t1_filter_rate", "continuation_capture_rate", "false_entry_rate",
    "future_leakage_count", "explanation_coverage", "lrrm_transition_stability",
    "anchor_failure_precision", "pseudo_strength_filter_rate",
    "nonlinear_false_entry_reduction", "exhaustion_block_precision",
    "regression_case_pass_rate",
)


def _validated_zone(name: Any) -> ZoneInfo:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("回放数据源必须声明 IANA source_timezone")
    try:
        return ZoneInfo(name)
    except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError(f"无效的 IANA source_timezone: {name!r}") from exc


def _json_safe(value: Any) -> Any:
    """Normalize replay evidence without stringifying unknown object types."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("回放报告中的时间戳必须包含时区")
        return value.isoformat()
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("回放报告映射的键必须是字符串")
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    native = getattr(value, "item", None)
    if callable(native):
        try:
            return _json_safe(native())
        except (TypeError, ValueError, OverflowError):
            pass
    raise ValueError(f"回放报告包含不支持的值类型: {type(value).__name__}")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("回放报告必须只包含严格 JSON 数据") from exc


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=str(path.parent), prefix=".r9-replay-", suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary_path), str(path))
        temporary_path = None
    except OSError as exc:
        raise ValueError("回放报告无法原子落盘") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


class HistoricalReplayReportStore:
    """Persist hash-verified full-input replay evidence and its latest summary."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.index_path = self.root / "latest.json"

    @staticmethod
    def _report_hash(report: Mapping[str, Any]) -> str:
        content = dict(report)
        content.pop("replay_report_hash", None)
        return hashlib.sha256(_canonical_json(content)).hexdigest()

    @staticmethod
    def _validate_report(report: Any) -> Dict[str, Any]:
        from ats.strategy.ipo_data_contracts import IPO_REQUIRED_FIELDS

        required = {
            "schema_version", "run_manifest", "stock_count", "cutoff_count",
            "unready_cutoff_count", "input_contract_status", "stocks",
            "effect_metrics", "replay_report_hash",
        }
        if not isinstance(report, dict) or set(report) != required:
            raise ValueError("回放报告字段不符合存储契约")
        if report.get("schema_version") != REPLAY_REPORT_SCHEMA_VERSION:
            raise ValueError("回放报告 schema_version 无效")
        manifest = report.get("run_manifest")
        if (
            not isinstance(manifest, Mapping)
            or set(manifest) != {
                "source_manifest", "source_id", "source_timezone", "configuration_version",
                "decision_config_hash", "data_contract_hash", "input_contract_status", "config_hash",
            }
            or not _is_sha256(manifest.get("config_hash"))
            or not _is_sha256(manifest.get("decision_config_hash"))
            or not _is_sha256(manifest.get("data_contract_hash"))
            or manifest.get("input_contract_status") != "ENFORCED_ALL_41_FIELDS"
        ):
            raise ValueError("回放报告缺少已哈希的来源/配置 manifest")
        stocks = report.get("stocks")
        if not isinstance(stocks, list) or report.get("stock_count") != len(stocks):
            raise ValueError("回放报告股票计数不一致")
        cutoff_count = 0
        unready_count = 0
        leakage_count = 0
        timestamp_check_count = 0
        explanation_count = 0
        for stock in stocks:
            if not isinstance(stock, Mapping) or not isinstance(stock.get("cutoff_observations"), list):
                raise ValueError("回放报告缺少逐 cutoff 观察")
            for observation in stock["cutoff_observations"]:
                if not isinstance(observation, Mapping):
                    raise ValueError("逐 cutoff 报告观察格式无效")
                try:
                    cutoff_time = datetime.fromisoformat(
                        str(observation.get("cutoff_time", "")).replace("Z", "+00:00")
                    )
                    observed_time = datetime.fromisoformat(
                        str(observation.get("as_of_time", "")).replace("Z", "+00:00")
                    )
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("逐 cutoff 报告时间戳无效") from exc
                if (
                    cutoff_time.tzinfo is None or cutoff_time.utcoffset() is None
                    or observed_time.tzinfo is None or observed_time.utcoffset() is None
                ):
                    raise ValueError("逐 cutoff 报告时间戳必须包含时区")
                leakage_count += int(observed_time > cutoff_time)
                timestamp_check_count += 1
                causal_chain = observation.get("causal_chain")
                if (
                    isinstance(causal_chain, list) and causal_chain
                    and all(isinstance(reason, str) and reason.strip() for reason in causal_chain)
                ):
                    explanation_count += 1
                contract = observation.get("input_contract") if isinstance(observation, Mapping) else None
                checks = contract.get("field_checks") if isinstance(contract, Mapping) else None
                if not isinstance(checks, Mapping) or set(checks) != set(IPO_REQUIRED_FIELDS):
                    raise ValueError("逐 cutoff 报告必须包含 41 项字段核验")
                cutoff_count += 1
                contract_status = contract.get("status")
                if contract_status == "READY":
                    snapshot = contract.get("input_snapshot")
                    snapshot_hash = contract.get("input_snapshot_hash")
                    if (
                        not isinstance(snapshot, Mapping)
                        or not isinstance(snapshot.get("features"), Mapping)
                        or set(snapshot["features"]) != set(IPO_REQUIRED_FIELDS)
                        or not _is_sha256(snapshot_hash)
                        or hashlib.sha256(_canonical_json(snapshot)).hexdigest() != snapshot_hash
                    ):
                        raise ValueError("READY cutoff 缺少可复核的 41 项输入快照")
                    if snapshot.get("as_of_time") != observation.get("cutoff_time"):
                        raise ValueError("READY 输入快照时间必须等于当前 cutoff")
                    for feature in snapshot["features"].values():
                        if not isinstance(feature, Mapping):
                            raise ValueError("41 项输入快照字段格式无效")
                        for key in ("as_of_time", "available_at"):
                            try:
                                source_time = datetime.fromisoformat(
                                    str(feature.get(key, "")).replace("Z", "+00:00")
                                )
                            except (TypeError, ValueError, OverflowError) as exc:
                                raise ValueError("41 项输入快照缺少有效来源时点") from exc
                            if source_time.tzinfo is None or source_time.utcoffset() is None:
                                raise ValueError("41 项输入快照来源时点必须包含时区")
                            leakage_count += int(source_time > cutoff_time)
                            timestamp_check_count += 1
                elif contract_status == "UNREADY":
                    unready_count += 1
                else:
                    raise ValueError("逐 cutoff 数据契约状态无效")
        expected_status = "READY" if cutoff_count > 0 and unready_count == 0 else "UNREADY"
        if (
            report.get("cutoff_count") != cutoff_count
            or report.get("unready_cutoff_count") != unready_count
            or report.get("input_contract_status") != expected_status
        ):
            raise ValueError("回放报告 cutoff 计数或数据契约状态不一致")
        metrics = report.get("effect_metrics")
        if not isinstance(metrics, Mapping) or set(metrics) != set(REPLAY_EFFECT_METRICS):
            raise ValueError("回放报告缺少完整 13 项效果指标")
        for name, metric in metrics.items():
            if not isinstance(metric, Mapping) or set(metric) != {
                "status", "value", "numerator", "denominator", "reason",
            }:
                raise ValueError(f"回放效果指标格式无效: {name}")
            if metric.get("status") == "NOT_EVALUABLE":
                if metric.get("value") is not None or metric.get("numerator") is not None or metric.get("denominator") is not None:
                    raise ValueError(f"不可评估指标不得带数值: {name}")
            elif metric.get("status") == "MEASURED":
                value = metric.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"已测量指标数值无效: {name}")
                numerator, denominator = metric.get("numerator"), metric.get("denominator")
                if (
                    not isinstance(numerator, int) or isinstance(numerator, bool) or numerator < 0
                    or not isinstance(denominator, int) or isinstance(denominator, bool) or denominator < 0
                    or numerator > denominator
                ):
                    raise ValueError(f"已测量指标分子/分母无效: {name}")
                if name == "explanation_coverage" and (
                    denominator <= 0 or not math.isclose(value, numerator / denominator)
                ):
                    raise ValueError("解释覆盖率必须与逐 cutoff 分子/分母一致")
                if name == "future_leakage_count" and value != numerator:
                    raise ValueError("未来泄漏数必须与泄漏分子一致")
            else:
                raise ValueError(f"效果指标状态无效: {name}")
            if not isinstance(metric.get("reason"), str) or not metric["reason"].strip():
                raise ValueError(f"效果指标缺少依据说明: {name}")
        future_metric = metrics["future_leakage_count"]
        expected_future_status = "MEASURED" if timestamp_check_count > 0 else "NOT_EVALUABLE"
        if (
            future_metric.get("status") != expected_future_status
            or future_metric.get("value") != (leakage_count if timestamp_check_count else None)
            or future_metric.get("numerator") != (leakage_count if timestamp_check_count else None)
            or future_metric.get("denominator") != (timestamp_check_count if timestamp_check_count else None)
        ):
            raise ValueError("未来泄漏指标与逐 cutoff 时间戳证据不一致")
        expected_explanation_status = "MEASURED" if cutoff_count > 0 else "NOT_EVALUABLE"
        explanation_metric = metrics["explanation_coverage"]
        if (
            explanation_metric.get("status") != expected_explanation_status
            or explanation_metric.get("numerator") != (explanation_count if cutoff_count else None)
            or explanation_metric.get("denominator") != (cutoff_count if cutoff_count else None)
            or explanation_metric.get("value") != (
                explanation_count / cutoff_count if cutoff_count else None
            )
        ):
            raise ValueError("解释覆盖率与逐 cutoff 因果链证据不一致")
        if any(
            metrics[name].get("status") != (
                "MEASURED"
                if (
                    (name == "future_leakage_count" and timestamp_check_count > 0)
                    or (name == "explanation_coverage" and cutoff_count > 0)
                ) else "NOT_EVALUABLE"
            )
            for name in REPLAY_EFFECT_METRICS
        ):
            raise ValueError("缺少真实标签或基线的效果指标不得标记为已量化")
        return report

    def save(self, report: Mapping[str, Any]) -> Dict[str, Any]:
        clean = _json_safe(dict(report))
        self._validate_report(clean)
        report_hash = clean.get("replay_report_hash")
        if not _is_sha256(report_hash) or self._report_hash(clean) != report_hash:
            raise ValueError("回放报告哈希校验失败")
        payload = _canonical_json(clean)
        if len(payload) > MAX_REPLAY_REPORT_BYTES:
            raise ValueError("回放报告超过 512 MiB 存储上限")
        artifact_path = self.root / f"{report_hash}.json"
        if artifact_path.exists():
            existing = self.load(report_hash)
            if self._report_hash(existing) != report_hash:
                raise ValueError("同哈希回放报告内容不一致")
        else:
            _atomic_write(artifact_path, payload)
        run_manifest = clean["run_manifest"]
        manifest = {
            "schema_version": REPLAY_REPORT_INDEX_VERSION,
            "replay_report_hash": report_hash,
            "artifact_file": artifact_path.name,
            "input_contract_status": clean.get("input_contract_status", "UNREADY"),
            "stock_count": clean.get("stock_count", 0),
            "cutoff_count": clean.get("cutoff_count", 0),
            "unready_cutoff_count": clean.get("unready_cutoff_count", 0),
            "effect_metrics": {
                name: {
                    "status": metric["status"],
                    "value": metric["value"],
                    "reason": metric["reason"],
                }
                for name, metric in clean["effect_metrics"].items()
            },
            "config_hash": run_manifest.get("config_hash", ""),
            "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        manifest["index_hash"] = hashlib.sha256(_canonical_json(manifest)).hexdigest()
        _atomic_write(self.index_path, _canonical_json(manifest))
        return self.summary()

    def load(self, report_hash: str) -> Dict[str, Any]:
        if not _is_sha256(report_hash):
            raise ValueError("回放报告哈希格式无效")
        path = self.root / f"{report_hash}.json"
        try:
            if path.is_symlink() or path.stat().st_size > MAX_REPLAY_REPORT_BYTES:
                raise ValueError("回放报告文件不安全或超过大小限制")
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("回放报告缺失或不可读取") from exc
        if not isinstance(report, dict) or report.get("replay_report_hash") != report_hash:
            raise ValueError("回放报告文件哈希校验失败")
        self._validate_report(report)
        if self._report_hash(report) != report_hash:
            raise ValueError("回放报告文件哈希校验失败")
        return report

    def summary(self) -> Dict[str, Any]:
        if not self.index_path.is_file():
            return {"status": "MISSING", "replay_report_hash": ""}
        try:
            if self.index_path.stat().st_size > 16 * 1024:
                raise ValueError("回放报告索引超过大小限制")
            manifest = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return {"status": "UNAVAILABLE", "replay_report_hash": ""}
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != REPLAY_REPORT_INDEX_VERSION
            or set(manifest) != {
                "schema_version", "replay_report_hash", "artifact_file",
                "input_contract_status", "stock_count", "cutoff_count",
                "unready_cutoff_count", "effect_metrics", "config_hash",
                "saved_at", "index_hash",
            }
        ):
            return {"status": "UNAVAILABLE", "replay_report_hash": ""}
        expected_hash = manifest.get("index_hash")
        content = dict(manifest)
        content.pop("index_hash", None)
        try:
            valid_index_hash = (
                isinstance(expected_hash, str)
                and hashlib.sha256(_canonical_json(content)).hexdigest() == expected_hash
            )
        except ValueError:
            valid_index_hash = False
        if not valid_index_hash:
            return {"status": "UNAVAILABLE", "replay_report_hash": ""}
        artifact_name = manifest.get("artifact_file")
        report_hash = manifest.get("replay_report_hash")
        metrics = manifest.get("effect_metrics")
        counts = (
            manifest.get("stock_count"), manifest.get("cutoff_count"),
            manifest.get("unready_cutoff_count"),
        )
        if (
            not _is_sha256(report_hash)
            or artifact_name != f"{report_hash}.json"
            or not _is_sha256(manifest.get("config_hash"))
            or manifest.get("input_contract_status") not in {"READY", "UNREADY"}
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts)
            or not isinstance(metrics, Mapping)
            or set(metrics) != set(REPLAY_EFFECT_METRICS)
            or any(
                not isinstance(metric, Mapping)
                or set(metric) != {"status", "value", "reason"}
                or metric.get("status") not in {"MEASURED", "NOT_EVALUABLE"}
                or not isinstance(metric.get("reason"), str)
                or not metric["reason"].strip()
                or (
                    metric.get("status") == "NOT_EVALUABLE"
                    and metric.get("value") is not None
                )
                or (
                    metric.get("status") == "MEASURED"
                    and (
                        isinstance(metric.get("value"), bool)
                        or not isinstance(metric.get("value"), (int, float))
                        or not math.isfinite(metric["value"])
                    )
                )
                for metric in metrics.values()
            )
            or any(
                metrics[name].get("status") != (
                    "MEASURED"
                    if name in {"future_leakage_count", "explanation_coverage"} and counts[1] > 0
                    else "NOT_EVALUABLE"
                )
                for name in REPLAY_EFFECT_METRICS
            )
        ):
            return {"status": "UNAVAILABLE", "replay_report_hash": ""}
        artifact = self.root / artifact_name
        try:
            artifact_available = (
                artifact.is_file() and not artifact.is_symlink()
                and artifact.stat().st_size <= MAX_REPLAY_REPORT_BYTES
            )
        except OSError:
            artifact_available = False
        if not artifact_available:
            return {"status": "UNAVAILABLE", "replay_report_hash": ""}
        return {"status": "AVAILABLE", **manifest}


@dataclass(frozen=True)
class ReplaySource:
    source_id: str
    source_version: str
    source_timezone: str
    source_role: str
    access: str
    availability_time_keys: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("回放来源缺少 source_id")
        if not isinstance(self.source_version, str) or not self.source_version.strip():
            raise ValueError(f"回放来源 {self.source_id!r} 缺少 source_version")
        if self.source_role not in {
            "bars", "feature", "news", "announcement", "subscription",
            "vector_evidence", "outcome",
        }:
            raise ValueError(f"回放来源 {self.source_id!r} 的 source_role 无效")
        if self.access not in {"MODEL_INPUT", "OUTCOME_ONLY"}:
            raise ValueError(f"回放来源 {self.source_id!r} 的 access 无效")
        if (self.source_role == "outcome") != (self.access == "OUTCOME_ONLY"):
            raise ValueError("结果标签源必须隔离为 OUTCOME_ONLY，其余来源必须是 MODEL_INPUT")
        if (
            not isinstance(self.availability_time_keys, tuple)
            or not self.availability_time_keys
            or any(not isinstance(key, str) or not key.strip() for key in self.availability_time_keys)
            or len(self.availability_time_keys) != len(set(self.availability_time_keys))
        ):
            raise ValueError(f"回放来源 {self.source_id!r} 必须声明可用时点字段")
        if self.source_role == "bars" and self.availability_time_keys != ("datetime",):
            raise ValueError("bars 来源的 availability_time_keys 必须为 ('datetime',)")
        if self.source_role != "bars" and any(
            not key.replace("_", "").isalnum() for key in self.availability_time_keys
        ):
            raise ValueError("非 bars 来源的可用时点字段名无效")
        _validated_zone(self.source_timezone)


@dataclass(frozen=True)
class ReplaySourceManifest:
    manifest_version: str
    sources: Tuple[ReplaySource, ...]

    def __post_init__(self) -> None:
        if self.manifest_version != REPLAY_MANIFEST_VERSION:
            raise ValueError(f"不支持的回放来源 manifest 版本: {self.manifest_version!r}")
        if not self.sources:
            raise ValueError("回放来源 manifest 不能为空")
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("回放来源 manifest 中 source_id 不得重复")
        roles = {source.source_role for source in self.sources}
        required_roles = {
            "bars", "feature", "news", "announcement", "subscription",
            "vector_evidence", "outcome",
        }
        if not required_roles.issubset(roles):
            raise ValueError(
                "全输入回放 manifest 缺少来源类别: "
                + ", ".join(sorted(required_roles - roles))
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReplaySourceManifest":
        if not isinstance(value, Mapping):
            raise ValueError("缺少版本化回放来源 manifest")
        version = value.get("manifest_version")
        raw_sources = value.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise ValueError("回放来源 manifest 的 sources 必须是非空列表")
        sources: List[ReplaySource] = []
        for item in raw_sources:
            if not isinstance(item, Mapping):
                raise ValueError("回放来源条目必须是映射")
            sources.append(ReplaySource(
                source_id=item.get("source_id"),
                source_version=item.get("source_version"),
                source_timezone=item.get("source_timezone"),
                source_role=item.get("source_role"),
                access=item.get("access"),
                availability_time_keys=tuple(item.get("availability_time_keys", ())),
            ))
        return cls(manifest_version=version, sources=tuple(sources))

    def source(self, source_id: str) -> ReplaySource:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise ValueError(f"回放来源未在 manifest 中登记: {source_id!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "sources": [
                {
                    "source_id": source.source_id,
                    "source_version": source.source_version,
                    "source_timezone": source.source_timezone,
                    "source_role": source.source_role,
                    "access": source.access,
                    "availability_time_keys": list(source.availability_time_keys),
                }
                for source in sorted(self.sources, key=lambda item: item.source_id)
            ],
        }


def build_replay_config_hash(
    replay_config: Mapping[str, Any],
    source_manifest: ReplaySourceManifest,
) -> str:
    """Hash replay settings and the complete versioned source manifest."""
    if not isinstance(replay_config, Mapping):
        raise ValueError("回放配置必须是映射")
    payload = {
        "replay_config": dict(replay_config),
        "source_manifest": source_manifest.to_dict(),
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
        raise ValueError("回放配置/来源 manifest 必须可稳定序列化") from exc
    return hashlib.sha256(canonical).hexdigest()


class TimeSandbox:
    """Normalize source timestamps and expose data no later than one cutoff."""

    def __init__(
        self,
        current_cutoff_time: Any,
        source_timezone: str,
        exchange_timezone: str = DEFAULT_EXCHANGE_TIMEZONE,
    ) -> None:
        self.source_tz = _validated_zone(source_timezone)
        self.exchange_tz = _validated_zone(exchange_timezone)
        self.cutoff_dt = self.normalize_time(current_cutoff_time)

    def normalize_time(self, value: Any) -> pd.Timestamp:
        try:
            if isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is None:
                raise ValueError("时间戳没有有效 UTC 偏移")
            timestamp = pd.Timestamp(value)
            if pd.isna(timestamp):
                raise ValueError("时间戳为空")
            if timestamp.tzinfo is None:
                local_value = timestamp.to_pydatetime()
                candidates = []
                for fold in (0, 1):
                    candidate = local_value.replace(tzinfo=self.source_tz, fold=fold)
                    round_trip = candidate.astimezone(ZoneInfo("UTC")).astimezone(self.source_tz)
                    if round_trip.replace(tzinfo=None) == local_value:
                        candidates.append(candidate)
                if not candidates:
                    raise ValueError("本地时间不存在")
                if (
                    len(candidates) > 1
                    and candidates[0].utcoffset() != candidates[1].utcoffset()
                ):
                    raise ValueError("本地时间有歧义")
                timestamp = pd.Timestamp(candidates[0])
            elif timestamp.utcoffset() is None:
                raise ValueError("时间戳没有有效 UTC 偏移")
            return timestamp.tz_convert(self.exchange_tz)
        except Exception as exc:
            raise ValueError(f"无效或时区不兼容的回放时间戳: {value!r}") from exc

    def filter_bars(self, frame: pd.DataFrame, time_col: str = "datetime") -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame) or frame.empty or time_col not in frame.columns:
            raise ValueError(f"回放输入缺失行情或时间列: {time_col}")
        timestamps = [self.normalize_time(value) for value in frame[time_col].tolist()]
        keep_positions = [
            position for position, timestamp in enumerate(timestamps)
            if timestamp <= self.cutoff_dt
        ]
        filtered = frame.iloc[keep_positions].copy()
        filtered[time_col] = [timestamps[position] for position in keep_positions]
        return filtered.sort_values(time_col, kind="stable")

    def filter_source_frame(
        self,
        frame: pd.DataFrame,
        availability_time_keys: Tuple[str, ...],
    ) -> pd.DataFrame:
        """Cut off every declared availability/publication timestamp in a source."""
        if not isinstance(frame, pd.DataFrame):
            raise ValueError("回放模型输入来源类型无效")
        missing_columns = set(availability_time_keys) - set(frame.columns)
        if missing_columns:
            raise ValueError(f"回放来源缺少时间字段: {', '.join(sorted(missing_columns))}")
        normalized = frame.copy()
        keep = [True] * len(normalized)
        for time_col in availability_time_keys:
            timestamps = [self.normalize_time(value) for value in normalized[time_col].tolist()]
            normalized[time_col] = timestamps
            keep = [
                is_kept and timestamp <= self.cutoff_dt
                for is_kept, timestamp in zip(keep, timestamps)
            ]
        filtered = normalized.loc[keep].copy()
        sort_key = availability_time_keys[0]
        return filtered.sort_values(sort_key, kind="stable")


class IPOReplayInputContract:
    """Assemble and validate the frozen 41-field IPO input at one replay cutoff."""

    def __init__(self, decision_config_snapshot: Any, source_manifest: ReplaySourceManifest) -> None:
        from ats.strategy.ipo_data_contracts import (
            IPO_REQUIRED_FIELDS,
            IPODecisionConfigSnapshot,
        )

        if (
            not isinstance(decision_config_snapshot, IPODecisionConfigSnapshot)
            or not decision_config_snapshot.verify_integrity()
        ):
            raise ValueError("全输入回放必须使用通过完整性校验的 IPO 决策配置快照")
        data_contract = decision_config_snapshot.data_contract
        if set(data_contract.required_fields) != set(IPO_REQUIRED_FIELDS):
            raise ValueError("全输入回放数据契约必须精确覆盖 41 项 IPO 必需输入")
        manifest_sources = {source.source_id: source for source in source_manifest.sources}
        for field_id in IPO_REQUIRED_FIELDS:
            field_contract = data_contract.fields[field_id]
            source = manifest_sources.get(field_contract.source_id)
            if source is None or source.access != "MODEL_INPUT":
                raise ValueError(f"回放 manifest 未声明模型输入来源: {field_id}")
            if (
                source.source_version != field_contract.source_version
                or source.source_timezone != field_contract.source_timezone
            ):
                raise ValueError(f"字段契约与回放来源版本/时区不一致: {field_id}")
            missing_time_keys = {
                field_contract.as_of_key, field_contract.available_at_key,
            } - set(source.availability_time_keys)
            if missing_time_keys:
                raise ValueError(
                    f"回放 manifest 未冻结字段时点: {field_id} / "
                    + ", ".join(sorted(missing_time_keys))
                )
        self.config_snapshot = decision_config_snapshot
        self.data_contract = data_contract
        self.required_fields = tuple(IPO_REQUIRED_FIELDS)
        self.availability_keys_by_source: Dict[str, Tuple[str, ...]] = {}
        for field_id in self.required_fields:
            field_contract = data_contract.fields[field_id]
            keys = set(self.availability_keys_by_source.get(field_contract.source_id, ()))
            keys.add(field_contract.as_of_key)
            keys.add(field_contract.available_at_key)
            self.availability_keys_by_source[field_contract.source_id] = tuple(sorted(keys))

    @staticmethod
    def _native_value(value: Any) -> Any:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        item = getattr(value, "item", None)
        if callable(item):
            try:
                return item()
            except (TypeError, ValueError):
                pass
        return value

    def validate(
        self,
        cutoff: pd.Timestamp,
        source_frames: Mapping[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        observations: Dict[str, Dict[str, Any]] = {}
        snapshot_features: Dict[str, Dict[str, Any]] = {}
        for field_id in self.required_fields:
            contract = self.data_contract.fields[field_id]
            frame = source_frames.get(contract.source_id)
            required_columns = {
                contract.value_key, contract.as_of_key,
                contract.available_at_key, "status",
            }
            if not isinstance(frame, pd.DataFrame) or frame.empty or not required_columns.issubset(frame.columns):
                observations[field_id] = {
                    "status": "UNREADY",
                    "source_id": contract.source_id,
                    "source_version": contract.source_version,
                }
                snapshot_features[field_id] = {
                    "status": "UNREADY", "value": None,
                    "source_id": contract.source_id,
                    "source_version": contract.source_version,
                    "source_timezone": contract.source_timezone,
                    "as_of_time": None, "available_at": None,
                }
                continue
            ordered = frame.sort_values(contract.available_at_key, kind="stable")
            row = ordered.iloc[-1]
            status = self._native_value(row.get("status"))
            if not isinstance(status, str):
                status = "UNREADY"
            source_time = self._native_value(row.get(contract.as_of_key))
            available_at = self._native_value(row.get(contract.available_at_key))
            source_sandbox = TimeSandbox(cutoff, contract.source_timezone)
            try:
                if source_time is not None:
                    source_time = source_sandbox.normalize_time(source_time)
                if available_at is not None:
                    available_at = source_sandbox.normalize_time(available_at)
            except (TypeError, ValueError, OverflowError):
                source_time = None
                available_at = None
                status = "UNREADY"
            observations[field_id] = {
                "status": status,
                "source_id": contract.source_id,
                "source_version": contract.source_version,
                "source_timezone": contract.source_timezone,
                contract.value_key: self._native_value(row.get(contract.value_key)),
                contract.as_of_key: source_time,
                contract.available_at_key: available_at,
            }
            snapshot_features[field_id] = {
                "status": status,
                "value": self._native_value(row.get(contract.value_key)),
                "source_id": contract.source_id,
                "source_version": contract.source_version,
                "source_timezone": contract.source_timezone,
                "as_of_time": source_time.isoformat() if source_time is not None else None,
                "available_at": available_at.isoformat() if available_at is not None else None,
            }

        ready, checks = self.data_contract.validate_observations(
            observations, cutoff.to_pydatetime(),
        )
        field_checks = {
            field_id: {
                "status": check.status,
                "usable": check.usable,
                "reason_code": check.reason_code or "",
                "source_as_of_utc": (
                    check.source_as_of_utc.isoformat()
                    if check.source_as_of_utc is not None else ""
                ),
            }
            for field_id, check in checks.items()
        }
        result = {
            "status": "READY" if ready else "UNREADY",
            "configuration_hash": self.config_snapshot.config_hash,
            "data_contract_hash": self.data_contract.config_hash,
            "field_checks": field_checks,
            "unready_fields": [
                field_id for field_id, check in checks.items() if not check.usable
            ],
        }
        if ready:
            snapshot = {
                "as_of_time": cutoff.isoformat(),
                "configuration_hash": self.config_snapshot.config_hash,
                "data_contract_hash": self.data_contract.config_hash,
                "features": snapshot_features,
            }
            try:
                encoded = json.dumps(
                    snapshot, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                ).encode("utf-8")
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("41 项回放输入快照必须是严格 JSON 数据") from exc
            if len(encoded) > 128 * 1024:
                raise ValueError("41 项回放输入快照超过离线学习样本大小限制")
            result["input_snapshot"] = snapshot
            result["input_snapshot_hash"] = hashlib.sha256(encoded).hexdigest()
        return result


class HistoricalCutoffReplayEngine:
    """Replay each bar cutoff using a pinned, versioned source timezone."""

    def __init__(
        self,
        sample_codes: List[str],
        load_history: Callable[[str, str], Any],
        evaluate_as_of: Callable[
            [str, pd.DataFrame, pd.Timestamp, Mapping[str, pd.DataFrame]],
            Mapping[str, Any],
        ],
        build_summary: Callable[[Any, List[Mapping[str, Any]]], Dict[str, Any]],
        source_timezone: str,
        source_manifest: Mapping[str, Any],
        source_id: str,
        start_date: str = "2026-08-01",
        replay_config: Optional[Mapping[str, Any]] = None,
        decision_config_snapshot: Optional[Any] = None,
    ) -> None:
        self.sample_codes = list(sample_codes)
        self.load_history = load_history
        self.evaluate_as_of = evaluate_as_of
        self.build_summary = build_summary
        self.source_manifest = ReplaySourceManifest.from_mapping(source_manifest)
        self.source_id = source_id
        declared_source = self.source_manifest.source(source_id)
        if declared_source.source_role != "bars" or declared_source.access != "MODEL_INPUT":
            raise ValueError("source_id 必须指向 MODEL_INPUT bars 来源")
        _validated_zone(source_timezone)
        if declared_source.source_timezone != source_timezone:
            raise ValueError("source_timezone 与版本化来源 manifest 不一致")
        self.source_timezone = source_timezone
        self.start_date = start_date
        self.replay_config = dict(replay_config or {})
        if decision_config_snapshot is None:
            raise ValueError("R9 全输入回放缺少版本化 IPO 决策配置/41 项数据源契约")
        self.input_contract = IPOReplayInputContract(
            decision_config_snapshot, self.source_manifest,
        )
        self.decision_config_hash = decision_config_snapshot.config_hash
        self.config_hash = build_replay_config_hash(
            {
                **self.replay_config,
                "sample_codes": sorted(str(code) for code in self.sample_codes),
                "start_date": self.start_date,
                "source_id": self.source_id,
                "source_timezone": self.source_timezone,
                "exchange_timezone": DEFAULT_EXCHANGE_TIMEZONE,
                "decision_config_hash": self.decision_config_hash,
                "data_contract_hash": self.input_contract.data_contract.config_hash,
            },
            self.source_manifest,
        )

    @property
    def run_manifest(self) -> Dict[str, Any]:
        """Return the replay provenance fields for persistence with a report."""
        return {
            "source_manifest": self.source_manifest.to_dict(),
            "source_id": self.source_id,
            "source_timezone": self.source_timezone,
            "configuration_version": self.input_contract.config_snapshot.config_version,
            "decision_config_hash": self.decision_config_hash,
            "data_contract_hash": self.input_contract.data_contract.config_hash,
            "input_contract_status": "ENFORCED_ALL_41_FIELDS",
            "config_hash": self.config_hash,
        }

    @staticmethod
    def _history_value(history: Any, key: str) -> Any:
        if isinstance(history, Mapping):
            return history.get(key)
        return getattr(history, key, None)

    def _replay_stock_with_evidence(
        self, code: str,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Recompute one stock and retain each cutoff's complete input checks."""
        history = self.load_history(code, self.start_date)
        raw_bars = self._history_value(history, "bars")
        metadata = self._history_value(history, "metadata")
        if not isinstance(raw_bars, pd.DataFrame) or raw_bars.empty:
            raise ValueError(f"{code}: 回放区间无行情数据")

        initial_sandbox = TimeSandbox(
            raw_bars["datetime"].iloc[0], self.source_timezone
        )
        bars = raw_bars.copy()
        bars["datetime"] = [
            initial_sandbox.normalize_time(value) for value in bars["datetime"].tolist()
        ]
        bars = bars.sort_values("datetime", kind="stable")

        raw_inputs = self._history_value(history, "inputs")
        model_sources = {
            source.source_id: source
            for source in self.source_manifest.sources
            if source.access == "MODEL_INPUT" and source.source_id != self.source_id
        }
        if not isinstance(raw_inputs, Mapping) or set(raw_inputs) != set(model_sources):
            raise ValueError("全输入回放来源与版本化 manifest 不一致或不完整")

        observations: List[Mapping[str, Any]] = []
        evidence_observations: List[Dict[str, Any]] = []
        for cutoff in bars["datetime"].drop_duplicates().sort_values():
            sandbox = TimeSandbox(cutoff, self.source_timezone)
            known_bars = sandbox.filter_bars(bars)
            known_inputs = {}
            for source_id, source in model_sources.items():
                known_inputs[source_id] = TimeSandbox(
                    sandbox.cutoff_dt, source.source_timezone
                ).filter_source_frame(raw_inputs[source_id], source.availability_time_keys)
            source_frames = {self.source_id: known_bars, **known_inputs}
            input_contract = self.input_contract.validate(sandbox.cutoff_dt, source_frames)
            observation = self.evaluate_as_of(
                code, known_bars, sandbox.cutoff_dt, known_inputs
            )
            if not isinstance(observation, Mapping) or "as_of_time" not in observation:
                raise ValueError("回放观察必须包含 as_of_time")
            observation = dict(observation)
            observation["input_contract"] = input_contract
            observation["cutoff_time"] = sandbox.cutoff_dt.isoformat()
            if input_contract["status"] != "READY":
                prior_decision = observation.get("decision", "UNKNOWN")
                observation["decision_before_input_contract"] = (
                    prior_decision if isinstance(prior_decision, str) else "UNKNOWN"
                )
                observation["decision"] = "BLOCK"
                observation["data_status"] = "UNREADY"
                observation["block_reason"] = "IPO_INPUT_CONTRACT_UNREADY"
                prior_chain = observation.get("causal_chain", [])
                if not isinstance(prior_chain, list):
                    prior_chain = []
                observation["causal_chain"] = [
                    item for item in prior_chain if isinstance(item, str)
                ] + [
                    "IPO_INPUT_CONTRACT_UNREADY:" + ",".join(input_contract["unready_fields"][:12])
                ]
            observed_at = sandbox.normalize_time(observation["as_of_time"])
            if observed_at > sandbox.cutoff_dt:
                raise ValueError("回放观察时间越过当前 cutoff，拒绝未来数据泄漏")
            observations.append(observation)
            evidence_observation = dict(observation)
            evidence_observation["as_of_time"] = observed_at.isoformat()
            evidence_observations.append(_json_safe(evidence_observation))

        result = self.build_summary(metadata, observations)
        required = {
            "code", "name", "listing_date", "preheat_at_listing",
            "first_entry_ready_time", "max_heat_before_entry", "t1_carry_close",
            "D1_open_gap", "D1_min_vs_listing_open", "D1_min_vs_listing_low",
            "D1_reclaim_status", "false_entry_flag", "survival_flag",
            "blocked_by_rule", "transition_log",
        }
        if not isinstance(result, dict) or set(result) != required:
            raise ValueError("回放汇总字段契约不符，预期 15 项标准字段")
        return result, evidence_observations

    def replay_stock(self, code: str) -> Dict[str, Any]:
        """Return the standard 15-field summary for one replayed stock."""
        result, _ = self._replay_stock_with_evidence(code)
        return result

    def replay(self) -> List[Dict[str, Any]]:
        return [self.replay_stock(code) for code in self.sample_codes]

    def replay_report(
        self, output_directory: Optional[str | os.PathLike[str]] = None,
    ) -> Dict[str, Any]:
        """Return and optionally persist hash-bound per-cutoff 41-field evidence."""
        stocks = []
        total_cutoffs = 0
        unready_cutoffs = 0
        for code in self.sample_codes:
            summary, observations = self._replay_stock_with_evidence(code)
            total_cutoffs += len(observations)
            unready_cutoffs += sum(
                1 for item in observations
                if item.get("input_contract", {}).get("status") != "READY"
            )
            stocks.append({
                "summary": summary,
                "cutoff_observations": observations,
            })
        report = {
            "schema_version": REPLAY_REPORT_SCHEMA_VERSION,
            "run_manifest": self.run_manifest,
            "stock_count": len(stocks),
            "cutoff_count": total_cutoffs,
            "unready_cutoff_count": unready_cutoffs,
            "input_contract_status": (
                "READY" if total_cutoffs > 0 and unready_cutoffs == 0 else "UNREADY"
            ),
            "stocks": stocks,
            "effect_metrics": self._effect_metrics(stocks, total_cutoffs),
        }
        report = _json_safe(report)
        serialized = json.dumps(
            report, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        report["replay_report_hash"] = hashlib.sha256(serialized).hexdigest()
        if output_directory is not None:
            HistoricalReplayReportStore(output_directory).save(report)
        return report

    @staticmethod
    def _effect_metrics(stocks: List[Mapping[str, Any]], cutoff_count: int) -> Dict[str, Any]:
        observations = [
            item
            for stock in stocks
            for item in stock.get("cutoff_observations", [])
            if isinstance(item, Mapping)
        ]
        explanation_count = sum(
            1 for item in observations
            if isinstance(item.get("causal_chain"), list)
            and bool(item["causal_chain"])
            and all(isinstance(reason, str) and reason.strip() for reason in item["causal_chain"])
        )
        not_evaluable_reasons = {
            "regime_transition_accuracy": "缺少独立的下一阶段 Regime 真值标签",
            "high_carry_vs_low_carry_spread": "缺少经契约定义的 Carry 分组收益标签",
            "bad_t1_filter_rate": "缺少已验收的 T+1 坏样本定义与真值标签",
            "continuation_capture_rate": "缺少独立延续行情真值标签",
            "false_entry_rate": "缺少冻结的误入定义、成熟结果标签及统计窗口",
            "lrrm_transition_stability": "缺少 LRRM 转换真值与稳定性统计定义",
            "anchor_failure_precision": "缺少锚点失效真值标签及精确率定义",
            "pseudo_strength_filter_rate": "缺少伪强势样本真值标签",
            "nonlinear_false_entry_reduction": "缺少线性基线与同批成熟结果标签",
            "exhaustion_block_precision": "缺少衰竭真值标签与阻断结果定义",
            "regression_case_pass_rate": "未接入版本化回归案例集及期望结果",
        }
        metrics = {
            name: {
                "status": "NOT_EVALUABLE", "value": None,
                "numerator": None, "denominator": None,
                "reason": not_evaluable_reasons[name],
            }
            for name in not_evaluable_reasons
        }
        denominator = int(cutoff_count)
        timestamp_check_count = len(observations) + 82 * sum(
            1 for item in observations
            if isinstance(item.get("input_contract"), Mapping)
            and item["input_contract"].get("status") == "READY"
        )
        metrics["future_leakage_count"] = {
            "status": "MEASURED" if timestamp_check_count > 0 else "NOT_EVALUABLE",
            "value": 0 if timestamp_check_count > 0 else None,
            "numerator": 0 if timestamp_check_count > 0 else None,
            "denominator": timestamp_check_count if timestamp_check_count > 0 else None,
            "reason": (
                "逐 cutoff 检查 evaluator 时点及 READY 输入快照中全部来源时点；越界会中止报告生成"
                if timestamp_check_count > 0 else "回放没有可核验的 cutoff 时点"
            ),
        }
        metrics["explanation_coverage"] = {
            "status": "MEASURED" if denominator > 0 else "NOT_EVALUABLE",
            "value": explanation_count / denominator if denominator > 0 else None,
            "numerator": explanation_count if denominator > 0 else None,
            "denominator": denominator if denominator > 0 else None,
            "reason": "逐 cutoff 因果链非空且每项均为有效文本的比例",
        }
        return metrics
