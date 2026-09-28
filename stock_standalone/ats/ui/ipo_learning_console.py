# -*- coding: utf-8 -*-
"""IPO/LLM learning monitor; runtime is read-only and reviews are audited."""

from __future__ import annotations

import json
import html
import math
import queue
import re
import sqlite3
import threading
import time
import copy
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PyQt6.QtCore import QThread, QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
    QPushButton, QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QLineEdit,
    QWidget, QHeaderView, QTabWidget, QSizePolicy,
)


_STAGES = (
    ("Stage 0 · 数据与配置准入", "先冻结数据字典、来源时效、阈值与 Provider 环境证据"),
    ("Stage 1 · 规则与回放", "真实指标生产者、六层门禁、全输入截断回放与隔离压测"),
    ("Stage 2 · 只读 Agent", "Provider 验收、证据追溯、截止时间过滤与复盘候选"),
    ("Stage 3 · UI 与告警", "行情状态、单股因果、状态迁移及 Regime/Carry 告警"),
    ("Stage 4 · 离线学习", "成熟样本复核、SFT/DPO、影子评估、人工晋级与回滚"),
)
_REPLAY_METRICS = (
    ("regime_transition_accuracy", "Regime 转换准确率"),
    ("high_carry_vs_low_carry_spread", "高/低 Carry 收益差"),
    ("bad_t1_filter_rate", "T+1 坏样本过滤率"),
    ("continuation_capture_rate", "延续行情捕获率"),
    ("false_entry_rate", "误入率"),
    ("future_leakage_count", "未来数据泄漏数"),
    ("explanation_coverage", "决策解释覆盖率"),
    ("lrrm_transition_stability", "LRRM 转换稳定性"),
    ("anchor_failure_precision", "锚点失效精确率"),
    ("pseudo_strength_filter_rate", "伪强势过滤率"),
    ("nonlinear_false_entry_reduction", "非线性规则误入降低幅度"),
    ("exhaustion_block_precision", "衰竭阻断精确率"),
    ("regression_case_pass_rate", "回归案例通过率"),
)
_DISPLAY_TURNOVER_TRACKERS: Dict[Tuple[str, str], Any] = {}
_DISPLAY_TURNOVER_TRACKERS_LOCK = threading.Lock()


def _read_json(path: Path, max_bytes: int = 256 * 1024) -> Optional[Dict[str, Any]]:
    try:
        if path.stat().st_size > max_bytes:
            return None
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, ValueError):
        return None


def _safe_text(value: Any, limit: int = 300) -> str:
    if not isinstance(value, (str, int, float, bool)):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).replace("\r", " ").replace("\n", " ")[:limit]


def _json_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, RecursionError, UnicodeError):
        return ""


def _outcome_evidence_ids(value: Any) -> Optional[List[str]]:
    if not isinstance(value, str) or len(value) > 8192:
        return None
    try:
        refs = json.loads(value)
    except (ValueError, RecursionError):
        return None
    if (
        not isinstance(refs, list) or not refs or len(refs) > 32
        or any(
            not isinstance(ref, str) or not ref.startswith("outcome:")
            or len(ref) > 160 or "\x00" in ref
            for ref in refs
        )
        or len(refs) != len(set(refs))
    ):
        return None
    return refs


def _number_label(value: Any, precision: int = 1, suffix: str = "") -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            if math.isfinite(value):
                return f"{value:.{precision}f}{suffix}"
        except (OverflowError, TypeError, ValueError):
            pass
    return "--"


def _nonnegative_count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _passport_gate_detail(
    passport: Any, causal_chain: Any, decision: str, block_gate: Any,
) -> Dict[str, Any]:
    detail = passport.get("gate_detail") if isinstance(passport, dict) else None
    if isinstance(detail, dict) and detail:
        return detail
    gates = {f"gate_{index}": "UNAVAILABLE" for index in range(6)}
    if isinstance(block_gate, int) and not isinstance(block_gate, bool) and 0 <= block_gate <= 5:
        gates[f"gate_{block_gate}"] = "WATCH" if decision == "WATCH" else "BLOCK"
    chain = causal_chain if isinstance(causal_chain, list) else []
    return {
        "as_of_time": "",
        "gates": gates,
        "lrrm": {"status": "UNAVAILABLE"},
        "regime": {"status": "UNAVAILABLE"},
        "preheat": {"status": "UNAVAILABLE"},
        "live_heat": {"status": "UNAVAILABLE"},
        "carry": {"status": "UNAVAILABLE"},
        "anchors": {"status": "UNAVAILABLE"},
        "vwap": {"status": "UNAVAILABLE"},
        "data_contract": {"status": "UNAVAILABLE"},
        "risk": {"status": "UNAVAILABLE"},
        "positive_factors": [],
        "negative_factors": [],
        "next_condition": str(chain[-1])[:240] if chain else "历史事件未包含 Gate 诊断快照",
    }


def _tail_events(path: Path, limit: int = 200) -> List[Dict[str, str]]:
    """Read only the bounded, UI-safe event envelope; never display prompts/payloads."""
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            stream.seek(max(0, size - 512 * 1024))
            raw = stream.read(512 * 1024).decode("utf-8", errors="replace")
        rows: List[Dict[str, str]] = []
        for line in raw.splitlines()[-limit:]:
            try:
                item = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            outcome_refs = payload.get("outcome_evidence_ids", item.get("outcome_evidence_ids"))
            worker_evidence_ids = metadata.get("evidence_ids")
            outcome_refs_well_formed = bool(
                isinstance(outcome_refs, list) and outcome_refs
                and len(outcome_refs) <= 32
                and all(
                    isinstance(ref, str) and ref.startswith("outcome:")
                    and 0 < len(ref) <= 160 and "\x00" not in ref
                    for ref in outcome_refs
                )
                and len(outcome_refs) == len(set(outcome_refs))
            )
            outcome_refs_valid = bool(
                outcome_refs_well_formed
                and isinstance(worker_evidence_ids, list)
                and all(isinstance(ref, str) for ref in worker_evidence_ids)
                and set(outcome_refs).issubset(set(worker_evidence_ids))
            )
            draft = item.get("review_draft") or payload.get("review_draft")
            audit = item.get("audit_envelope") if isinstance(item.get("audit_envelope"), dict) else {}
            passport = audit.get("ipo_gate_passport") if isinstance(audit.get("ipo_gate_passport"), dict) else {}
            causal_chain = (
                item.get("gate_causal_chain") or payload.get("gate_causal_chain")
                or item.get("causal_chain") or passport.get("causal_chain")
            )
            row = {key: _safe_text(item.get(key)) for key in (
                "timestamp", "level", "stage", "event", "status", "ticker",
                "request_id", "message", "summary", "candidate_id", "matured_at", "cutoff",
                "event_id", "listing_date",
                "input_snapshot_hash", "label_source", "labels_mature", "reviewer",
                "decision", "reason", "gate", "execution_status", "reject_code",
                "configuration_version", "configuration_hash", "data_contract_hash",
                "model_id", "prompt_version", "review_draft_hash",
            )}
            row.update({
                "ticker": _safe_text(
                    item.get("ticker") or payload.get("ticker") or metadata.get("ticker"), 16
                ),
                "event_id": _safe_text(
                    item.get("event_id") or payload.get("event_id") or metadata.get("event_id"), 160
                ),
                "listing_date": _safe_text(
                    item.get("listing_date") or payload.get("listing_date") or metadata.get("listing_date"), 10
                ),
                "matured_at": _safe_text(
                    item.get("matured_at") or payload.get("matured_at"), 80
                ),
                "configuration_hash": _safe_text(
                    item.get("configuration_hash") or payload.get("configuration_hash")
                    or metadata.get("configuration_hash"), 64
                ),
                "data_contract_hash": _safe_text(
                    item.get("data_contract_hash") or payload.get("data_contract_hash")
                    or metadata.get("data_contract_hash"), 64
                ),
                "model_id": _safe_text(item.get("model_id") or metadata.get("model_id"), 120),
                "prompt_version": _safe_text(item.get("prompt_version") or metadata.get("prompt_version"), 120),
                "review_draft_hash": _json_sha256(draft) if isinstance(draft, dict) and draft else "",
                "review_draft": (
                    json.dumps(draft, ensure_ascii=False, sort_keys=True)[:4000]
                    if isinstance(draft, dict) else _safe_text(draft, 4000)
                ),
                "gate_trace_present": "true" if isinstance(causal_chain, list) and causal_chain else "false",
                "outcome_evidence_ids_json": (
                    json.dumps(outcome_refs, ensure_ascii=False, separators=(",", ":"))
                    if outcome_refs_well_formed else "[]"
                ),
                "outcome_evidence_valid": "true" if outcome_refs_valid else "false",
            })
            rows.append(row)
        return rows
    except OSError:
        return []


def _read_yaml_backend(path: Path) -> str:
    try:
        if path.stat().st_size > 128 * 1024:
            return "配置文件超限"
        import yaml
        with path.open("r", encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
        if not isinstance(document, dict):
            return "配置格式无效"
        settings = document.get("llm_settings", {})
        if not isinstance(settings, dict):
            return "未配置 Provider"
        return _safe_text(settings.get("active_backend") or "未配置", 100)
    except ImportError:
        return "PyYAML 缺失"
    except FileNotFoundError:
        return "未配置"
    except Exception:
        return "配置不可读取"


def _replay_report_summary(root: Path) -> Dict[str, Any]:
    metric_names = {name for name, _label in _REPLAY_METRICS}
    index_path = root / "data" / "ipo_learning" / "replay_reports" / "latest.json"
    index = _read_json(index_path, max_bytes=16 * 1024)
    if not isinstance(index, dict) or index.get("schema_version") != "r9.replay-report-index.v2":
        return {"status": "MISSING", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    if set(index) != {
        "schema_version", "replay_report_hash", "artifact_file", "input_contract_status",
        "stock_count", "cutoff_count", "unready_cutoff_count", "effect_metrics", "config_hash",
        "saved_at", "index_hash",
    }:
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    report_hash = index.get("replay_report_hash")
    if not isinstance(report_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", report_hash):
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    if index.get("artifact_file") != f"{report_hash}.json":
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    counts = (index.get("stock_count"), index.get("cutoff_count"), index.get("unready_cutoff_count"))
    if (
        any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts)
        or index.get("input_contract_status") not in {"READY", "UNREADY"}
        or not re.fullmatch(r"[0-9a-f]{64}", str(index.get("config_hash", "")))
    ):
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    effect_metrics = index.get("effect_metrics")
    if not isinstance(effect_metrics, dict) or set(effect_metrics) != metric_names:
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    for metric in effect_metrics.values():
        if (
            not isinstance(metric, dict) or set(metric) != {"status", "value", "reason"}
            or metric.get("status") not in {"MEASURED", "NOT_EVALUABLE"}
            or not isinstance(metric.get("reason"), str) or not metric["reason"].strip()
            or (
                metric.get("status") == "NOT_EVALUABLE" and metric.get("value") is not None
            )
            or (
                metric.get("status") == "MEASURED"
                and (
                    isinstance(metric.get("value"), bool)
                    or not isinstance(metric.get("value"), (int, float))
                    or not math.isfinite(metric["value"])
                )
            )
        ):
            return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    if any(
        effect_metrics[name].get("status") != (
            "MEASURED" if name in {"future_leakage_count", "explanation_coverage"}
            and index.get("cutoff_count", 0) > 0
            else "NOT_EVALUABLE"
        )
        for name in metric_names
    ):
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    expected_index_hash = index.get("index_hash")
    index_content = dict(index)
    index_content.pop("index_hash", None)
    try:
        canonical = json.dumps(
            index_content, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    if hashlib.sha256(canonical).hexdigest() != expected_index_hash:
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    artifact_path = index_path.parent / index["artifact_file"]
    try:
        if artifact_path.is_symlink() or artifact_path.stat().st_size > 512 * 1024 * 1024:
            raise OSError("replay artifact is unsafe")
    except OSError:
        return {"status": "UNAVAILABLE", "replay_report_hash": "", "cutoff_count": 0, "unready_cutoff_count": 0}
    return {
        "status": "AVAILABLE",
        "replay_report_hash": report_hash,
        "input_contract_status": _safe_text(index.get("input_contract_status"), 24),
        "cutoff_count": index.get("cutoff_count", 0),
        "unready_cutoff_count": index.get("unready_cutoff_count", 0),
        "effect_metrics": effect_metrics,
        "saved_at": _safe_text(index.get("saved_at"), 32),
    }


def _reviewable(event: Dict[str, str]) -> bool:
    if (
        event.get("event") != "REVIEW_CANDIDATE"
        or event.get("labels_mature") != "true"
        or event.get("reviewed") == "true"
        or event.get("outcome_evidence_valid") != "true"
    ):
        return False
    if _outcome_evidence_ids(event.get("outcome_evidence_ids_json", "")) is None:
        return False
    if not re.fullmatch(r"[0-9a-fA-F]{64}", event.get("input_snapshot_hash", "")):
        return False
    if (
        not event.get("model_id") or not event.get("prompt_version")
        or not re.fullmatch(r"[0-9a-fA-F]{64}", event.get("review_draft_hash", ""))
        or event.get("gate_trace_present") != "true"
    ):
        return False
    candidate_id = event.get("candidate_id", "")
    if (
        not candidate_id or len(candidate_id) > 128 or "\x00" in candidate_id
        or not event.get("cutoff") or not event.get("label_source")
        or not re.fullmatch(r"\d{6}", event.get("ticker", ""))
        or not event.get("event_id") or len(event.get("event_id", "")) > 160
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", event.get("listing_date", ""))
        or not re.fullmatch(r"[0-9a-fA-F]{64}", event.get("configuration_hash", ""))
        or not re.fullmatch(r"[0-9a-fA-F]{64}", event.get("data_contract_hash", ""))
    ):
        return False
    try:
        date.fromisoformat(event["listing_date"])
        matured = datetime.fromisoformat(event["matured_at"].replace("Z", "+00:00"))
        cutoff = datetime.fromisoformat(event["cutoff"].replace("Z", "+00:00"))
        if (
            matured.tzinfo is None or matured.utcoffset() is None
            or cutoff.tzinfo is None or cutoff.utcoffset() is None
            or cutoff > matured
        ):
            return False
        return matured.astimezone(timezone.utc) <= datetime.now(timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _load_metric_contracts(path: Path) -> Dict[str, Any]:
    try:
        if path.stat().st_size > 256 * 1024:
            return {}
        import yaml
        from ats.strategy.ipo_data_contracts import MetricFieldContract
        with path.open("r", encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
        data_contract = document.get("data_contract", {}) if isinstance(document, dict) else {}
        raw_fields = data_contract.get("fields", {}) if isinstance(data_contract, dict) else {}
        if not isinstance(raw_fields, dict):
            return {}
        result = {}
        for field_id, raw in raw_fields.items():
            try:
                result[field_id] = MetricFieldContract.from_mapping(field_id, raw)
            except (TypeError, ValueError):
                continue
        return result
    except Exception:
        return {}


def _field_runtime_state(
    contract: Any, observation: Any, now: datetime, data_contract: Any = None
) -> str:
    if contract is None:
        return "缺少来源/时效契约"
    if not isinstance(observation, dict):
        return "未接入实时观测"
    try:
        from ats.strategy.ipo_data_contracts import IPODataContractSet

        validator = data_contract
        if validator is None:
            validator = IPODataContractSet(
                "ui-runtime-check", {contract.field_id: contract}, (contract.field_id,)
            )
        observation_timezone = observation.get("source_timezone")
        if observation_timezone is not None and observation_timezone != contract.source_timezone:
            return "来源时区不符"
        normalized = dict(observation)
        for alias, key in (
            ("value", contract.value_key),
            ("as_of_time", contract.as_of_key),
            ("available_at", contract.available_at_key),
        ):
            if key not in normalized and alias in observation:
                normalized[key] = observation[alias]
        check = validator.validate_observation(contract.field_id, normalized, now)
        if not check.usable:
            reasons = {
                "source_unready": "来源未就绪",
                "source_identity_mismatch": "来源版本不符",
                "source_timezone_mismatch": "来源时区缺失/不符",
                "source_timestamp_missing": "缺少观测时点",
                "timestamp_offset_missing": "观测时点缺少时区",
                "source_timestamp_future": "观测时点在未来",
                "source_stale": "观测已过期",
                "available_at_missing": "缺少 available_at",
                "available_at_invalid": "available_at 无效",
                "available_at_after_cutoff": "available_at 晚于观察截点",
                "observed_value_missing": "观测值缺失",
                "value_type_invalid": "观测值类型无效",
                "missing_policy_violation": "确认缺失不符合契约",
            }
            return reasons.get(check.reason_code, _safe_text(check.reason_code or "契约校验失败", 80))
        if check.status == "MISSING_CONFIRMED":
            return "确认缺失（契约允许）"
        age = (now.astimezone(timezone.utc) - check.source_as_of_utc).total_seconds()
        return f"新鲜 {age:.0f}s"
    except (ImportError, TypeError, ValueError, OverflowError, AttributeError, KeyError):
        return "契约校验不可用"


def _field_runtime_value(contract: Any, observation: Any) -> str:
    if not isinstance(observation, dict):
        return "--"
    if contract is None:
        value = observation.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return f"{value:g}" if math.isfinite(value) else "无效值"
            except (OverflowError, TypeError, ValueError):
                return "无效值"
        return _safe_text(value, 100) or "--"
    if (
        observation.get("source_id") != contract.source_id
        or observation.get("source_version") != contract.source_version
    ):
        return "--"
    if observation.get("status") == "MISSING_CONFIRMED":
        return "已确认缺失"
    value = observation.get("value", observation.get(contract.value_key))
    if contract.value_type == "number":
        try:
            valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        except (OverflowError, TypeError, ValueError):
            valid = False
        return f"{value:g}" if valid else "无效值"
    if contract.value_type == "integer":
        return str(value) if isinstance(value, int) and not isinstance(value, bool) else "无效值"
    if contract.value_type == "boolean":
        return "是" if value is True else "否" if value is False else "无效值"
    if contract.value_type == "string":
        return _safe_text(value, 100) if isinstance(value, str) else "无效值"
    return _safe_text(value, 100) or "--"


def _collect_market_pulse_field_observations(root: Path) -> Dict[str, Dict[str, Any]]:
    """Expose verified local values for display; contract validation remains separate."""
    try:
        import market_pulse_db

        database_path = Path(market_pulse_db.DB_PATH)
        if not database_path.is_absolute():
            database_path = (root / database_path).resolve()
        if not database_path.is_file():
            return {}
        connection = sqlite3.connect(
            f"{database_path.as_uri()}?mode=ro", uri=True, timeout=0.05
        )
        try:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(daily_sentiment)")
            }
            required = {
                "up_count", "down_count", "limit_down", "source_id",
                "source_version", "source_timezone", "as_of_time_utc",
                "available_at_utc",
            }
            if not required.issubset(columns):
                return {}
            candidates = connection.execute(
                "SELECT up_count, down_count, limit_down, source_id, source_version, "
                "source_timezone, as_of_time_utc, available_at_utc "
                "FROM daily_sentiment ORDER BY date DESC LIMIT 64"
            ).fetchall()
        finally:
            connection.close()
    except (ImportError, OSError, sqlite3.Error, ValueError):
        return {}

    now = datetime.now(timezone.utc)
    for row in candidates:
        up_count, down_count, limit_down = row[:3]
        source_id, source_version, source_timezone, as_of, available_at = row[3:]
        if not all(isinstance(value, str) and value.strip() for value in (
            source_id, source_version, source_timezone, as_of, available_at,
        )):
            continue
        try:
            ZoneInfo(source_timezone)
            as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            available_dt = datetime.fromisoformat(available_at.replace("Z", "+00:00"))
            if any(value.tzinfo is None or value.utcoffset() is None for value in (
                as_of_dt, available_dt,
            )):
                continue
            as_of_utc = as_of_dt.astimezone(timezone.utc)
            available_utc = available_dt.astimezone(timezone.utc)
        except (ZoneInfoNotFoundError, TypeError, ValueError, OverflowError, OSError):
            continue
        if as_of_utc > available_utc or available_utc > now:
            continue
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
               for value in (up_count, down_count, limit_down)):
            continue
        total = up_count + down_count
        if total <= 0:
            continue
        provenance = {
            "source_id": source_id.strip(),
            "source_version": source_version.strip(),
            "source_timezone": source_timezone.strip(),
            "as_of_time": as_of.strip(),
            "available_at": available_at.strip(),
            "status": "OBSERVED_UNCONTRACTED",
        }
        return {
            "advance_decline_ratio": {**provenance, "value": up_count / total},
            "limit_down_count": {**provenance, "value": limit_down},
        }
    return {}


def _configured_turnover_tracker(root: Path) -> Any:
    """Build the display-only rate tracker from a fully verified frozen config."""
    try:
        from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
        from ats.strategy.ipo_live_heat_engine import TurnoverClimbTracker

        snapshot = IPODecisionConfigSnapshot.from_yaml(
            str(root / "config" / "ipo_sentiment.yaml")
        )
        if not snapshot.verify_integrity():
            return None
        heat = snapshot.decision_config.get("ipo_live_heat", {})
        settings = heat.get("turnover_tracker", {}) if isinstance(heat, Mapping) else {}
        if not isinstance(settings, Mapping):
            return None
        lunch_start = datetime.strptime(settings["lunch_start"], "%H:%M").time()
        lunch_end = datetime.strptime(settings["lunch_end"], "%H:%M").time()
        max_gap = settings["max_sample_gap_trading_minutes"]
        if isinstance(max_gap, bool) or not isinstance(max_gap, (int, float)):
            return None
        key = (str(root.resolve()), snapshot.config_hash)
        with _DISPLAY_TURNOVER_TRACKERS_LOCK:
            tracker = _DISPLAY_TURNOVER_TRACKERS.get(key)
            if tracker is None:
                tracker = TurnoverClimbTracker(lunch_start, lunch_end, max_gap)
                _DISPLAY_TURNOVER_TRACKERS[key] = tracker
                while len(_DISPLAY_TURNOVER_TRACKERS) > 8:
                    _DISPLAY_TURNOVER_TRACKERS.pop(next(iter(_DISPLAY_TURNOVER_TRACKERS)))
            return tracker
    except (ImportError, KeyError, OSError, TypeError, ValueError):
        return None


def _collect_tdx_live_heat_observations(root: Path) -> Dict[str, Dict[str, Any]]:
    """Read the latest already-cached intraday bars for display; never fetch or initialize."""
    try:
        from ats.strategy.ipo_vwap_detector_engine import IPOVWAPDetectorEngine
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool

        detector = IPOVWAPDetectorEngine._instance
        pool = TDXGlobalCachePool._instance
        if detector is None or pool is None:
            return {}
        eval_cache = getattr(detector, "_eval_cache", {})
        try:
            signal_rows = tuple(eval_cache.items())
        except RuntimeError:
            return {}
        signals = [
            (str(code).zfill(6), row[0], float(row[1]))
            for code, row in signal_rows
            if isinstance(row, tuple) and len(row) == 2
            and isinstance(row[1], (int, float)) and not isinstance(row[1], bool)
            and math.isfinite(row[1])
        ]
        if not signals:
            return {}
        code, signal, _signal_cached_at = max(signals, key=lambda item: item[2])

        mutex = getattr(pool, "_mutex", None)
        if mutex is None or not mutex.acquire(timeout=0.01):
            return {}
        try:
            cache = getattr(pool, "_incremental_intraday_pool", {})
            entry = None
            for key, candidate in cache.items():
                if (
                    isinstance(key, tuple) and len(key) == 2
                    and str(key[0]).zfill(6) == code and isinstance(candidate, dict)
                    and candidate.get("df") is not None
                    and (
                        entry is None
                        or float(candidate.get("updated_at", 0.0) or 0.0)
                        > float(entry.get("updated_at", 0.0) or 0.0)
                    )
                ):
                    entry = candidate
            frame = entry.get("df") if entry else None
            updated_at = entry.get("updated_at") if entry else None
        finally:
            mutex.release()

        if frame is None or not hasattr(frame, "empty") or frame.empty:
            return {}
        if not {"date", "time_only", "close"}.issubset(frame.columns):
            return {}
        if not isinstance(updated_at, (int, float)) or isinstance(updated_at, bool):
            return {}
        available_dt = datetime.fromtimestamp(float(updated_at), timezone.utc)
        if available_dt > datetime.now(timezone.utc):
            return {}
        latest_date = str(frame.iloc[-1].get("date", "")).strip()[:10]
        today = frame[frame["date"].astype(str).str[:10] == latest_date]
        if not latest_date or today.empty:
            return {}
        first = today.iloc[0]
        latest = today.iloc[-1]
        time_text = str(latest.get("time_only", "")).strip()
        if len(time_text) == 5:
            time_text += ":00"
        as_of_dt = datetime.fromisoformat(f"{latest_date}T{time_text}").replace(
            tzinfo=ZoneInfo("Asia/Shanghai")
        )
        if as_of_dt.astimezone(timezone.utc) > available_dt:
            return {}

        current = float(latest.get("close", 0.0) or 0.0)
        if not math.isfinite(current) or current <= 0:
            return {}
        high_column = "high" if "high" in today.columns else "close"
        low_column = "low" if "low" in today.columns else "close"
        session_high = float(today[high_column].max())
        session_low = float(today[low_column].min())
        vwap = float(latest.get("vwap", 0.0) or 0.0)
        open_price = float(first.get("open", 0.0) or 0.0)
        turnover = latest.get("turnover_rate", latest.get("turnover"))
        if turnover is not None:
            turnover = float(turnover)
        turnover_climb_speed = None
        tracker = _configured_turnover_tracker(root)
        if tracker is not None and turnover is not None:
            with _DISPLAY_TURNOVER_TRACKERS_LOCK:
                turnover_climb_speed = tracker.update(
                    code, latest_date, turnover, as_of_dt
                )
        previous = frame[frame["date"].astype(str).str[:10] < latest_date]
        previous_close = float(previous.iloc[-1].get("close", 0.0) or 0.0) if not previous.empty else 0.0
        ret_pct = (current / previous_close - 1.0) * 100.0 if previous_close > 0 else None
        vwap_dist = (current / vwap - 1.0) * 100.0 if vwap > 0 else None
        extra_data = getattr(signal, "extra_data", {})
        slope_deg = extra_data.get("ipo_slope_angle") if isinstance(extra_data, Mapping) else None
        valid_vwap_bars = (
            today[(today["vwap"] > 0) & (today["close"] > 0)]
            if "vwap" in today.columns else today.iloc[0:0]
        )

        # This is a UI-side cache view, not a TDX vendor release or accepted data contract.
        provenance = {
            "source_id": "ui.tdx_intraday_cache",
            "source_version": "display-adapter-v1",
            "source_timezone": "Asia/Shanghai",
            "ticker": code,
            "as_of_time": as_of_dt.isoformat(),
            "available_at": available_dt.isoformat(),
            "status": "OBSERVED_UNCONTRACTED",
        }
        values: Dict[str, Any] = {
            "ret_pct": ret_pct,
            "turnover_pct": turnover,
            "price_vwap_dist_pct": vwap_dist,
            "open_premium_pct": (current / open_price - 1.0) * 100.0 if open_price > 0 else None,
            "slope_deg": slope_deg,
            "session_high": session_high,
            "session_low": session_low,
            "current_price": current,
            "turnover_climb_speed": turnover_climb_speed,
            "minutes_above_vwap_ratio": (
                float((valid_vwap_bars["close"] >= valid_vwap_bars["vwap"]).sum()) / len(valid_vwap_bars)
                if len(valid_vwap_bars) else None
            ),
            "pullback_from_peak_pct": (session_high - current) / session_high * 100.0 if session_high > 0 else None,
            "halt_count": getattr(signal, "suspension_count", None),
        }
        observations = {}
        for field_id, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            observations[field_id] = {**provenance, "value": value}
        return observations
    except (AttributeError, ImportError, KeyError, OSError, OverflowError, RuntimeError, TypeError, ValueError):
        return {}


def _collect_local_source_health(root: Path) -> List[Dict[str, str]]:
    """Inspect only already-created in-process caches; never fetch or initialize providers."""
    now = time.time()
    rows: List[Dict[str, str]] = []

    def age_text(updated_at: Any) -> str:
        if isinstance(updated_at, (int, float)) and not isinstance(updated_at, bool):
            try:
                age = now - float(updated_at)
                if math.isfinite(age) and age >= 0:
                    return f"{age:.1f}s"
            except (OverflowError, TypeError, ValueError):
                pass
        return "未知"

    try:
        from ats.new_stock_fetcher import NewStockFetcher
        fetcher = NewStockFetcher._instance
    except Exception:
        fetcher = None
    if fetcher is None:
        rows.append({
            "source": "IPO 日历 / 新股列表", "status": "未启动",
            "cached": "0", "latest": "未知",
            "detail": "只读监控不创建数据采集器；缓存数据不能证明 41 项指标完整",
        })
    else:
        calendar_count = len(getattr(fetcher, "_cached_ipo_dict", {}) or {})
        stock_frame = getattr(fetcher, "_cached_stocks_df", None)
        stock_count = len(stock_frame) if stock_frame is not None else 0
        observed_columns = (
            [str(column) for column in stock_frame.columns[:16]]
            if stock_frame is not None and hasattr(stock_frame, "columns") else []
        )
        column_summary = ", ".join(observed_columns) or "无字段快照"
        calendar_age = age_text(getattr(fetcher, "_last_calendar_fetch_time", 0))
        stocks_age = age_text(getattr(fetcher, "_last_fetch_time", 0))
        rows.append({
            "source": "IPO 日历", "status": "有缓存" if calendar_count else "无数据",
            "cached": f"{calendar_count} 条", "latest": calendar_age,
            "detail": "已加载日历缓存；日历字段不等于情绪指标契约",
        })
        rows.append({
            "source": "TDX 新股行情聚合", "status": "有缓存" if stock_count else "无数据",
            "cached": f"{stock_count} 只", "latest": stocks_age,
            "detail": f"当前表字段：{column_summary}；读内存表，不触发网络刷新",
        })

    try:
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool, TDXRealtimeFetcher
        fetcher = TDXRealtimeFetcher._instance
        pool = TDXGlobalCachePool._instance
    except Exception:
        fetcher = None
        pool = None
    if fetcher is None:
        rows.append({
            "source": "TDX Provider", "status": "未启动", "cached": "0",
            "latest": "未知", "detail": "没有已运行的 TDX 实例；监控未主动连接 Provider",
        })
    else:
        # These scalar reads stay lock-free: quote retrieval can hold _conn_lock
        # across network I/O, which must never stall the monitor worker.
        connected = bool(getattr(fetcher, "_is_connected", False))
        host = getattr(fetcher, "current_host", None)
        latency = getattr(fetcher, "latency_ms", None)
        quote_cache = getattr(fetcher, "_off_hours_cached_quotes", {}) or {}
        quote_count = len(quote_cache)
        endpoint = ""
        if isinstance(host, (tuple, list)) and len(host) >= 3:
            endpoint = f"{_safe_text(host[1], 80)}:{_safe_text(host[2], 8)}"
        latency_label = (
            f"{latency:.0f} ms" if isinstance(latency, (int, float))
            and not isinstance(latency, bool) and math.isfinite(latency) else "未知"
        )
        rows.append({
            "source": "TDX Provider", "status": "已连接" if connected else "未连接",
            "cached": f"{quote_count} 只报价快照", "latest": "时点未记录",
            "detail": f"端点 {endpoint or '未知'} · 延迟 {latency_label}；报价快照年龄不可判定",
        })

    if pool is None:
        rows.append({
            "source": "TDX 历史 / 指标缓存", "status": "未启动", "cached": "0",
            "latest": "未知", "detail": "没有已创建的本地缓存池",
        })
    else:
        mutex = getattr(pool, "_mutex", None)
        locked = False
        try:
            if mutex is not None:
                locked = mutex.acquire(timeout=0.02)
            if locked:
                history = getattr(pool, "_history_static_bars", {})
                intraday = getattr(pool, "_incremental_intraday_pool", {})
                daily = getattr(pool, "_daily_metrics_cache", {})
                latest_history = max((item.get("updated_at", 0) for item in history.values() if isinstance(item, dict)), default=0)
                latest_intraday = max((item.get("updated_at", 0) for item in intraday.values() if isinstance(item, dict)), default=0)
                latest_daily = max((item.get("updated_at", 0) for item in daily.values() if isinstance(item, dict)), default=0)
                latest = max(latest_history, latest_intraday, latest_daily)
                stats = dict(getattr(pool, "stats", {}))
                counts = (len(history), len(intraday), len(daily))
            else:
                counts = None
                latest = 0
                stats = {}
        except Exception:
            counts, latest, stats = None, 0, {}
        finally:
            if locked:
                mutex.release()
        rows.append({
            "source": "TDX 历史 / 指标缓存",
            "status": "读取繁忙" if counts is None else "有缓存" if any(counts) else "无数据",
            "cached": "--" if counts is None else f"静态历史 {counts[0]} · 增量分时 {counts[1]} · 日指标 {counts[2]}",
            "latest": "未采样" if counts is None else age_text(latest),
            "detail": "缓存池锁忙，等待下次刷新" if counts is None else f"缓存池命中 {stats.get('cache_hits', 0)} / 历史网络请求 {stats.get('network_calls', 0)}；不代表全输入回放已验收",
        })

    try:
        import market_pulse_db
        database_path = Path(market_pulse_db.DB_PATH)
        if not database_path.is_absolute():
            database_path = (root / database_path).resolve()
        if not database_path.is_file():
            rows.append({
                "source": "Market Pulse 日情绪", "status": "数据库不存在",
                "cached": "0", "latest": "未知",
                "detail": f"只读检查路径：{database_path}",
            })
        else:
            connection = sqlite3.connect(
                f"{database_path.as_uri()}?mode=ro", uri=True, timeout=0.05
            )
            try:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(daily_sentiment)")
                }
                required_columns = {
                    "source_id", "source_version", "source_timezone",
                    "as_of_time_utc", "available_at_utc",
                }
                row_count = connection.execute(
                    "SELECT COUNT(*) FROM daily_sentiment"
                ).fetchone()[0] if "daily_sentiment" in {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                } else 0
                if not required_columns.issubset(columns):
                    rows.append({
                        "source": "Market Pulse 日情绪", "status": "时点字段待迁移",
                        "cached": f"{row_count} 条", "latest": "不可用",
                        "detail": "daily_sentiment 尚无完整 source/as-of/available-at 列",
                    })
                else:
                    latest = connection.execute(
                        "SELECT date, source_id, source_version, source_timezone, "
                        "as_of_time_utc, available_at_utc FROM daily_sentiment "
                        "ORDER BY date DESC LIMIT 1"
                    ).fetchone()
                    if not latest:
                        rows.append({
                            "source": "Market Pulse 日情绪", "status": "无记录",
                            "cached": "0 条", "latest": "未知",
                            "detail": "表结构已包含来源时点字段，尚无日情绪快照",
                        })
                    else:
                        source_id, source_version, source_timezone = latest[1:4]
                        as_of, available_at = latest[4], latest[5]
                        as_of_age = "缺失"
                        available_age = "缺失"
                        as_of_valid = False
                        available_valid = False
                        source_valid = False
                        as_of_dt = None
                        available_dt = None
                        try:
                            source_valid = all(
                                isinstance(value, str) and bool(value.strip())
                                for value in (source_id, source_version, source_timezone)
                            )
                            if source_valid:
                                ZoneInfo(source_timezone)
                        except (ZoneInfoNotFoundError, TypeError, ValueError, OSError):
                            source_valid = False
                        try:
                            parsed = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
                            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                                as_of_dt = parsed.astimezone(timezone.utc)
                                as_of_age = age_text(parsed.timestamp())
                                as_of_valid = as_of_age != "未知"
                        except (TypeError, ValueError, OverflowError, OSError):
                            pass
                        try:
                            parsed = datetime.fromisoformat(str(available_at).replace("Z", "+00:00"))
                            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                                available_dt = parsed.astimezone(timezone.utc)
                                available_age = age_text(parsed.timestamp())
                                available_valid = available_age != "未知"
                        except (TypeError, ValueError, OverflowError, OSError):
                            pass
                        has_provenance = bool(
                            source_valid and as_of_valid and available_valid
                            and as_of_dt is not None and available_dt is not None
                            and as_of_dt <= available_dt <= datetime.now(timezone.utc)
                        )
                        rows.append({
                            "source": "Market Pulse 日情绪",
                            "status": "有来源时点" if has_provenance else "来源身份/时点缺失或无效",
                            "cached": f"{row_count} 条",
                            "latest": f"as-of {as_of_age} / available {available_age}",
                            "detail": (
                                f"{latest[1]}@{latest[2]} · {latest[3]} · {latest[0]} · "
                                f"as-of {as_of or '缺失'} · available {available_at or '缺失'}；"
                                "仅表示日情绪落库时点，不代表 41 项指标已满足契约"
                            ),
                        })
            finally:
                connection.close()
    except (ImportError, OSError, sqlite3.Error, ValueError) as exc:
        rows.append({
            "source": "Market Pulse 日情绪", "status": "读取失败",
            "cached": "--", "latest": "未知",
            "detail": _safe_text(exc, 180),
        })
    return rows


def _collect_snapshot(root: Path) -> Dict[str, Any]:
    config_path = root / "config" / "ipo_sentiment.yaml"
    llm_config_path = root / "config" / "llm_config.yaml"
    acceptance_path = root / "config" / "ipo_stage_acceptance.json"
    try:
        from ats.llm.runtime_service import _load_authorization
        runtime_authorization = _load_authorization(
            root / "config" / "llm_runtime_acceptance.json"
        )
    except Exception:
        runtime_authorization = {}
    runtime_path = root / "logs" / "llm_runtime_status.json"
    events_path = root / "logs" / "ipo_learning_events.jsonl"
    simulation_manifest = _read_json(root / "simulation_manifest.json", max_bytes=64 * 1024) or {}
    simulation_only = isinstance(simulation_manifest, dict) and simulation_manifest.get("simulation_only") is True
    metric_contracts = _load_metric_contracts(config_path)
    try:
        from ats.llm.provider_preflight import inspect_provider_preflight
        provider_preflight = inspect_provider_preflight(
            llm_config_path, authorization=runtime_authorization
        )
    except Exception:
        provider_preflight = {
            "backend": "不可用", "mode": "未知", "locality": "未确认",
            "state": "未就绪", "execution_allowed": False,
            "checks": [{
                "name": "Provider 预检", "status": "阻断",
                "detail": "预检器不可用；LLM 旁路保持关闭",
            }],
        }
    checks = provider_preflight.setdefault("checks", [])
    if isinstance(checks, list):
        try:
            from ats.llm.runtime_service import stage0_to_2_accepted

            stage0_to_2_ready = stage0_to_2_accepted(root)
        except Exception:
            stage0_to_2_ready = False
        remote_provider = provider_preflight.get("backend") in {
            "antigravity_cli", "codex_cli",
        }
        base_auth_keys = {
            "stage0_accepted", "provider_accepted", "process_tree_isolation_accepted",
            "acceptance_id",
        }
        remote_auth_keys = base_auth_keys | {
            "tool_access_isolation_accepted", "remote_egress_isolation_accepted",
        }
        expected_auth_shapes = {frozenset(remote_auth_keys)} if remote_provider else {
            frozenset(base_auth_keys), frozenset(remote_auth_keys),
        }
        required_auth_flags = remote_auth_keys if remote_provider else base_auth_keys
        authorization_ready = (
            frozenset(runtime_authorization) in expected_auth_shapes
            and all(runtime_authorization.get(key) is True for key in required_auth_flags - {"acceptance_id"})
            and isinstance(runtime_authorization.get("acceptance_id"), str)
            and bool(runtime_authorization.get("acceptance_id", "").strip())
            and stage0_to_2_ready
        )
        checks.append({
            "name": "运行准入授权",
            "status": "通过" if authorization_ready else "阻断",
            "detail": (
                (
                    "Stage 0–2、Provider、进程树、工具/MCP 与出口均有验收记录"
                    if remote_provider else "Stage 0–2、Provider 与进程树隔离均有验收记录"
                )
                if authorization_ready else "缺少完整的 Stage 0–2、Provider、Windows 隔离验收证据；Worker 不启动"
            ),
        })
        try:
            from ats.llm.agent_contracts import (
                AGENT_CONTRACT_VERSION, AGENT_TYPES, payload_schema,
                payload_schema_hash,
            )
            contracts_ready = len(AGENT_TYPES) == 3 and all(
                payload_schema(agent_type).get("additionalProperties") is False
                for agent_type in AGENT_TYPES
            )
            contract_hashes = ", ".join(
                f"{agent_type}={payload_schema_hash(agent_type)[:10]}"
                for agent_type in AGENT_TYPES
            )
        except Exception:
            contracts_ready = False
            contract_hashes = "不可用"
        checks.append({
            "name": "三类 Agent 严格输出契约",
            "status": "通过" if contracts_ready else "阻断",
            "detail": (
                f"{AGENT_CONTRACT_VERSION} 独立 Schema 与本地信封校验已就绪；哈希 {contract_hashes}。"
                "仅静态能力，不代表 Provider 或隔离验收通过"
                if contracts_ready else "Agent 契约不可用；LLM 旁路保持关闭"
            ),
        })

    config_ok = False
    config_detail = "缺少 config/ipo_sentiment.yaml；来源与逐字段 TTL 未冻结"
    if config_path.is_file():
        try:
            from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
            from ats.llm.request_producer import signal_max_age_seconds

            config = IPODecisionConfigSnapshot.from_yaml(str(config_path))
            config_ok = config.verify_integrity() and signal_max_age_seconds(config) > 0
            config_detail = (
                f"配置 {config.config_version} / 哈希 {config.config_hash[:12]}"
                if config_ok else "决策配置哈希校验失败"
            )
        except Exception as exc:
            config_detail = _safe_text(exc)

    acceptance = _read_json(acceptance_path) or {}
    accepted = acceptance.get("stages", {})
    if not isinstance(accepted, dict):
        accepted = {}
    stage_rows = []
    previous_stage_valid = True
    for index, (title, requirement) in enumerate(_STAGES):
        record = accepted.get(str(index), accepted.get(f"stage{index}", {}))
        valid = (
            isinstance(record, dict)
            and record.get("status") == "ACCEPTED"
            and bool(record.get("evidence"))
            and previous_stage_valid
        )
        if index == 0 and not config_ok:
            valid = False
            detail = config_detail
        elif valid:
            detail = _safe_text(record.get("summary") or record.get("accepted_at") or "已记录验收证据")
        else:
            detail = requirement
        previous_stage_valid = valid
        stage_rows.append({
            "stage": title,
            "status": "已验收" if valid else "未验收",
            "detail": detail,
        })
    if simulation_only:
        for row in stage_rows:
            row["status"] = "仿真通过" if row["status"] == "已验收" else "仿真待验收"
            row["detail"] = "合成数据演示，不构成真实 Stage 验收或实盘授权。"

    try:
        from ats.llm.offline_learning import DATASET_SCHEMA_VERSION
        from ats.llm.learning_snapshot_store import (
            snapshot_store_recent, snapshot_store_summary, snapshot_writer_status,
        )
        from ats.llm.sealed_dataset_store import SealedDatasetRepository
        replay_summary = _replay_report_summary(root)
        snapshot_summary = snapshot_store_summary(root)
        snapshot_writer = snapshot_writer_status(root)
        snapshot_rows = snapshot_store_recent(root, limit=50)
        dataset_summary = SealedDatasetRepository(
            root / "data" / "ipo_learning" / "sealed_datasets", create=False
        ).summary()
        if dataset_summary["status"] == "READY":
            dataset_status = (
                f"已封存 {dataset_summary['dataset_count']} 批 / "
                f"{dataset_summary['sample_count']} 条样本"
            )
        else:
            dataset_status = "封存仓库已接入，当前 0 批"
        if replay_summary["status"] != "AVAILABLE":
            shadow_status = "等待全量回放报告"
        elif (
            replay_summary.get("input_contract_status") == "READY"
            and replay_summary.get("unready_cutoff_count") == 0
            and replay_summary.get("cutoff_count", 0) > 0
        ):
            shadow_status = "回放索引已保存，内容哈希/效果指标待验收"
        else:
            shadow_status = (
                f"回放存在 {replay_summary.get('unready_cutoff_count', 0)} 个未就绪时点，影子评估阻断"
            )
        offline_pipeline_detail = (
            f"离线样本校验/事件分组前向切分/影子指标评估 {DATASET_SCHEMA_VERSION} 已实现；"
            f"Gate 完整输入快照 {snapshot_summary['snapshot_count']} 条，待结果标签 {snapshot_summary['waiting_outcome_count']} 条；"
            f"封存仓库 {dataset_status}；回放：{shadow_status}；"
            "Gate 决策快照保存规则 Proposal；D1-D3 成熟标签采集已接入并待人工复核；复盘 Agent 请求、训练执行器和模型晋级仍未接入"
        )
        effect_metrics = replay_summary.get("effect_metrics", {})
        measured_metric_count = sum(
            1 for metric in effect_metrics.values()
            if isinstance(metric, dict) and metric.get("status") == "MEASURED"
        )
        leakage_metric = effect_metrics.get("future_leakage_count", {})
        explanation_metric = effect_metrics.get("explanation_coverage", {})
        explanation_value = explanation_metric.get("value")
        explanation_coverage = _number_label(
            explanation_value * 100
            if isinstance(explanation_value, (int, float))
            and not isinstance(explanation_value, bool) else None,
            suffix="%",
        )
        effect_metric_status = (
            f"{measured_metric_count}/13 指标可量化 · 泄漏 {leakage_metric.get('value', '--')} · "
            f"解释覆盖 {explanation_coverage}"
        )
    except Exception:
        replay_summary = {
            "status": "UNAVAILABLE", "replay_report_hash": "",
            "cutoff_count": 0, "unready_cutoff_count": 0,
        }
        shadow_status = "回放报告状态不可用"
        dataset_summary = {
            "status": "UNAVAILABLE", "dataset_count": 0,
            "sample_count": 0, "event_group_count": 0,
            "latest_sealed_at": "", "integrity": "仓库不可用",
        }
        dataset_status = "封存仓库不可用"
        snapshot_summary = {
            "status": "UNAVAILABLE", "snapshot_count": 0,
            "waiting_outcome_count": 0, "latest_captured_at": "",
        }
        snapshot_writer = {"queued": 0, "dropped": 0, "failed": 0, "last_error": ""}
        snapshot_rows = []
        offline_pipeline_detail = "离线样本与影子评估模块不可用；训练保持关闭"
        effect_metric_status = "效果指标不可用"
    if len(stage_rows) > 4:
        stage_rows[4]["detail"] = f"{stage_rows[4]['detail']}；{offline_pipeline_detail}"

    runtime = _read_json(runtime_path) or {}
    runtime_status = _safe_text(runtime.get("status", "未启动"), 80)
    backend = _safe_text(runtime.get("provider") or _read_yaml_backend(llm_config_path), 100)
    raw_worker = runtime.get("worker", {})
    raw_worker = raw_worker if isinstance(raw_worker, dict) else {}
    raw_interaction = runtime.get("interaction", {})
    raw_interaction = raw_interaction if isinstance(raw_interaction, dict) else {}

    def _nonnegative_count(value: Any) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    def _nonnegative_age(value: Any) -> Optional[float]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            normalized = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
        return normalized if math.isfinite(normalized) and normalized >= 0 else None

    worker_monitor = {
        "state": _safe_text(raw_worker.get("state", "未启动"), 32),
        "pending_count": _nonnegative_count(raw_worker.get("pending_count")),
        "queued_count": _nonnegative_count(raw_worker.get("queued_count")),
        "inflight_scope_count": _nonnegative_count(raw_worker.get("inflight_scope_count")),
        "dropped_results": _nonnegative_count(raw_worker.get("dropped_results")),
        "heartbeat_healthy": raw_worker.get("heartbeat_healthy") is True,
        "heartbeat_age_seconds": _nonnegative_age(raw_worker.get("heartbeat_age_seconds")),
        "last_error": _safe_text(raw_worker.get("last_error"), 120),
    }
    interaction_summary = {
        key: _nonnegative_count(raw_interaction.get(key))
        for key in (
            "command_drops", "coalesced_requests", "stale_requests",
            "expired_requests", "invalid_requests", "submitted_requests",
            "ok_results", "failed_results",
        )
    }
    raw_last_result = raw_interaction.get("last_result", {})
    raw_last_result = raw_last_result if isinstance(raw_last_result, dict) else {}
    interaction_summary["last_result"] = {
        key: _safe_text(raw_last_result.get(key), limit)
        for key, limit in (
            ("request_id", 128), ("status", 24), ("ticker", 16),
            ("agent_type", 40), ("as_of_time", 40), ("completed_at", 40),
            ("summary", 300),
        ) if raw_last_result.get(key)
    }
    raw_recent_results = raw_interaction.get("recent_results", [])
    interaction_summary["recent_results"] = []
    if isinstance(raw_recent_results, list):
        for item in raw_recent_results[-100:]:
            if not isinstance(item, dict):
                continue
            interaction_summary["recent_results"].append({
                key: _safe_text(item.get(key), limit)
                for key, limit in (
                    ("request_id", 128), ("status", 24), ("ticker", 16),
                    ("agent_type", 40), ("as_of_time", 40), ("completed_at", 40),
                    ("summary", 300),
                )
            })
    try:
        from ats.llm.interaction_journal import (
            interaction_journal_status, recent_agent_interactions,
        )

        journal_status = interaction_journal_status(root)
        journal_results = recent_agent_interactions(root, limit=100)
        if journal_results:
            interaction_summary["recent_results"] = [
                {
                    key: _safe_text(item.get(key), limit)
                    for key, limit in (
                        ("request_id", 128), ("status", 24), ("ticker", 16),
                        ("agent_type", 40), ("as_of_time", 40), ("completed_at", 40),
                        ("summary", 300), ("model_id", 160),
                        ("prompt_version", 128), ("result_sha256", 64),
                    )
                }
                for item in journal_results
            ]
        interaction_summary["journal"] = {
            key: _nonnegative_count(journal_status.get(key))
            for key in ("queued", "accepted", "dropped", "failed")
        }
        interaction_summary["journal"]["last_error"] = _safe_text(
            journal_status.get("last_error"), 180
        )
    except Exception:
        interaction_summary["journal"] = {
            "queued": 0, "accepted": 0, "dropped": 0, "failed": 0,
            "last_error": "交互档案读取不可用",
        }
    raw_request_producer = raw_interaction.get("request_producer", {})
    raw_request_producer = raw_request_producer if isinstance(raw_request_producer, dict) else {}
    interaction_summary["request_producer"] = {
        "state": _safe_text(raw_request_producer.get("state"), 40) or "UNKNOWN",
        "reason": _safe_text(raw_request_producer.get("reason"), 200),
        "generated": _nonnegative_count(raw_request_producer.get("generated")),
        "submitted": _nonnegative_count(raw_request_producer.get("submitted")),
        "skipped_stale": _nonnegative_count(raw_request_producer.get("skipped_stale")),
        "rejected": _nonnegative_count(raw_request_producer.get("rejected")),
    }
    runtime_age = None
    timestamp = runtime.get("updated_at")
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        age = time.time() - timestamp
        runtime_age = age if 0 <= age <= 3 else None
    elif isinstance(timestamp, str):
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                age = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
                runtime_age = age if 0 <= age <= 3 else None
        except (TypeError, ValueError, OverflowError):
            pass
    stage2_accepted = not simulation_only and stage_rows[2]["status"] == "已验收"
    runtime_qualified = bool(
        not simulation_only and runtime_age is not None and stage2_accepted
        and runtime.get("qualified") is True
        and provider_preflight.get("execution_allowed") is True
        and worker_monitor.get("heartbeat_healthy") is True
    )
    if runtime_age is None:
        runtime_status = "未就绪 / 无新鲜健康快照"
    elif simulation_only:
        runtime_status = f"仿真交互已运行 / 实盘准入关闭（快照 {runtime_age:.1f}s）"
    elif (
        not stage2_accepted
        or runtime.get("qualified") is not True
        or provider_preflight.get("execution_allowed") is not True
    ):
        runtime_status = f"{runtime_status}（快照 {runtime_age:.1f}s）/ Provider 未通过准入"
    else:
        runtime_status = f"{runtime_status}（快照 {runtime_age:.1f}s）"

    try:
        from ats.strategy.ipo_data_contracts import IPO_REQUIRED_FIELDS
        required_fields = IPO_REQUIRED_FIELDS
    except Exception:
        required_fields = tuple(sorted(metric_contracts))
    observations = runtime.get("field_status", {})
    observations = dict(observations) if isinstance(observations, dict) else {}
    try:
        from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
        from ats.strategy.ipo_source_orchestrator import load_latest_valid_observations

        source_config = IPODecisionConfigSnapshot.from_yaml(str(config_path))
        for field_id, observation in load_latest_valid_observations(root, source_config, now_utc).items():
            observations.setdefault(field_id, observation)
    except Exception:
        pass
    for field_id, observation in _collect_market_pulse_field_observations(root).items():
        observations.setdefault(field_id, observation)
    for field_id, observation in _collect_tdx_live_heat_observations(root).items():
        observations.setdefault(field_id, observation)
    now_utc = datetime.now(timezone.utc)
    try:
        from ats.strategy.ipo_data_contracts import IPODataContractSet

        field_contract = IPODataContractSet(
            "ui-runtime-check", metric_contracts, tuple(metric_contracts)
        ) if metric_contracts else None
    except (ImportError, TypeError, ValueError):
        field_contract = None
    contract_rows = []
    try:
        from ats.strategy.ipo_source_orchestrator import source_route
    except ImportError:
        source_route = lambda _field_id: {"route": "来源路线未加载", "action": "保持阻断并检查预检报告"}
    for field_id in required_fields:
        contract = metric_contracts.get(field_id)
        observation = observations.get(field_id)
        route_info = source_route(field_id)
        observed_source = (
            f"{_safe_text(observation.get('source_id'), 80)}@"
            f"{_safe_text(observation.get('source_version'), 40)}"
            if isinstance(observation, dict) else ""
        )
        contract_rows.append({
            "field_id": field_id,
            "ticker": (
                ("全市场" if observation.get("ticker") == "000000" else _safe_text(observation.get("ticker"), 16)) or "--"
                if isinstance(observation, dict) else "--"
            ),
            "value": _field_runtime_value(contract, observation),
            "contract_configured": contract is not None,
            "source": f"{contract.source_id}@{contract.source_version}" if contract else observed_source,
            "timezone": contract.source_timezone if contract else (
                _safe_text(observation.get("source_timezone"), 80)
                if isinstance(observation, dict) else ""
            ),
            "ttl": f"{contract.max_age_seconds:g}" if contract else "",
            "unit": contract.unit if contract else "",
            "window": contract.window if contract else "",
            "missing_policy": contract.missing_policy if contract else "",
            "acquisition_route": route_info.get("route", ""),
            "next_action": route_info.get("action", ""),
            "available_at": (
                _safe_text(
                    observation.get(contract.available_at_key)
                    or observation.get("available_at"), 40,
                )
                if contract and isinstance(observation, dict) else (
                    _safe_text(observation.get("available_at"), 40)
                    if isinstance(observation, dict) else ""
                )
            ),
            "as_of_time": (
                _safe_text(
                    observation.get(contract.as_of_key)
                    or observation.get("as_of_time"), 40,
                )
                if contract and isinstance(observation, dict) else (
                    _safe_text(observation.get("as_of_time"), 40)
                    if isinstance(observation, dict) else ""
                )
            ),
            "status": _field_runtime_state(contract, observation, now_utc, field_contract),
        })
    contract_status_counts = {
        "required": len(contract_rows),
        "configured": sum(1 for row in contract_rows if row["contract_configured"]),
        "fresh": sum(1 for row in contract_rows if row["status"].startswith("新鲜")),
        "confirmed_missing": sum(
            1 for row in contract_rows if row["status"].startswith("确认缺失")
        ),
        "unobserved": sum(1 for row in contract_rows if row["status"] == "未接入实时观测"),
        "uncontracted": sum(1 for row in contract_rows if row["status"] == "缺少来源/时效契约"),
    }
    contract_status_counts["blocked_or_invalid"] = max(
        0,
        contract_status_counts["required"]
        - contract_status_counts["fresh"]
        - contract_status_counts["confirmed_missing"]
        - contract_status_counts["unobserved"]
        - contract_status_counts["uncontracted"],
    )

    events = _tail_events(events_path)
    # Add the live IPO gate trace without initializing the trading center or exposing raw payloads.
    operation_states = []
    gate_context_status = "TRADING_CENTER_NOT_STARTED"
    gate_context_generation = None
    gate_authorization_records = None
    try:
        from ats.strategy.ipo_trading_center import IPOTradingCenter
        trading_center = IPOTradingCenter._instance
        if trading_center:
            center_lock = getattr(trading_center, "_lock", None)
            lock_acquired = bool(center_lock and center_lock.acquire(timeout=0.02))
            if lock_acquired:
                try:
                    logs_ref = list(trading_center._signal_iteration_log[:50])
                    pending_refs = list(trading_center._pending_directives[:50])
                    market_ref = trading_center._last_market_context
                    operation_machine = trading_center._r9_operation_state_machine
                    provider_state = trading_center.get_r9_gate_context_status()
                    if isinstance(provider_state, dict):
                        gate_context_generation = provider_state.get("generation")
                        gate_authorization_records = provider_state.get("authorization_records")
                        provider_configured = provider_state.get("configured") is True
                    else:
                        provider_configured = False
                finally:
                    center_lock.release()
                gate_context_status = (
                    "PROVIDER_CONFIGURED" if provider_configured else "PROVIDER_UNCONFIGURED"
                )
                live_logs = copy.deepcopy(logs_ref)
                live_pending = copy.deepcopy(pending_refs)
                market_context = copy.deepcopy(market_ref)
                operation_states = operation_machine.snapshot() if operation_machine else []
            else:
                gate_context_status = "READ_BUSY"
                live_logs = []
                live_pending = []
                market_context = None
        else:
            live_logs = []
            live_pending = []
            market_context = None
    except Exception:
        gate_context_status = "READ_ERROR"
        live_logs = []
        live_pending = []
        market_context = None
        operation_states = []
    market_snapshot = {}
    if market_context is not None:
        market_snapshot = {
            key: getattr(market_context, key, None) for key in (
                "generated_at", "snapshot_id", "data_quality", "risk_mode", "heat_stage",
                "heat_score", "ipo_count", "red_ratio", "vwap_hold_ratio", "avg_change_pct",
                "surge_count", "sh_amount_yi", "sh_volume_ratio", "index_phase",
                "tide_state", "tide_confidence", "tide_action", "tide_position_cap_pct",
            )
        }
    live_events = []
    seen_request_ids = set()
    for item in live_logs:
        if not isinstance(item, dict):
            continue
        envelope = item.get("audit_envelope")
        envelope = envelope if isinstance(envelope, dict) else {}
        passport = envelope.get("ipo_gate_passport")
        if not isinstance(passport, dict) and not str(item.get("reject_code", "")).startswith("R9_GATE_"):
            continue
        causal_chain = passport.get("causal_chain", []) if isinstance(passport, dict) else []
        message = "；".join(str(value)[:160] for value in causal_chain[:4]) if isinstance(causal_chain, list) else ""
        if not message:
            message = str(item.get("reject_reason") or item.get("reason") or "R9 门禁事件")
        decision = str(passport.get("decision") or "BLOCK") if isinstance(passport, dict) else "BLOCK"
        raw_gate = passport.get("block_at_gate", -1) if isinstance(passport, dict) else -1
        gate_detail = _passport_gate_detail(passport, causal_chain, decision, raw_gate)
        gate = f"Gate {raw_gate}" if isinstance(raw_gate, int) and not isinstance(raw_gate, bool) and 0 <= raw_gate <= 5 else "--"
        request_id = _safe_text(item.get("directive_id"), 128)
        if request_id:
            seen_request_ids.add(request_id)
        timestamp = item.get("timestamp")
        if isinstance(timestamp, (int, float)) and math.isfinite(timestamp):
            try:
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(timestamp))
            except (OverflowError, OSError, ValueError):
                timestamp = ""
        live_events.append({
            "timestamp": _safe_text(timestamp or item.get("time_str"), 80),
            "level": "INFO",
            "stage": "R9_GATE",
            "event": "R9_GATE_DECISION",
            "status": _safe_text(decision, 32),
            "ticker": _safe_text(item.get("code"), 16),
            "request_id": request_id,
            "message": _safe_text(message, 300),
            "candidate_id": _safe_text(envelope.get("candidate_id"), 128),
            "decision": _safe_text(decision, 32),
            "reason": _safe_text(item.get("reject_code") or "", 100),
            "gate": gate,
            "causal_chain": list(causal_chain[:8]) if isinstance(causal_chain, list) else [],
            "gate_detail": gate_detail,
            "operation_state": passport.get("operation_state", {}) if isinstance(passport, dict) and isinstance(passport.get("operation_state"), dict) else {},
            "execution_status": _safe_text(item.get("execution_status"), 32),
            "reject_code": _safe_text(item.get("reject_code"), 100),
            "configuration_version": _safe_text(passport.get("configuration_version"), 64) if isinstance(passport, dict) else "",
            "configuration_hash": _safe_text(passport.get("configuration_hash"), 16) if isinstance(passport, dict) else "",
            "data_contract_hash": _safe_text(passport.get("data_contract_hash"), 16) if isinstance(passport, dict) else "",
        })
    for directive in live_pending:
        request_id = _safe_text(getattr(directive, "directive_id", ""), 128)
        if request_id in seen_request_ids:
            continue
        envelope = getattr(directive, "audit_envelope", None)
        envelope = envelope if isinstance(envelope, dict) else {}
        passport = envelope.get("ipo_gate_passport")
        reject_code = _safe_text(getattr(directive, "reject_code", ""), 100)
        if not isinstance(passport, dict) and not reject_code.startswith("R9_GATE_"):
            continue
        causal_chain = passport.get("causal_chain", []) if isinstance(passport, dict) else []
        message = "；".join(str(value)[:160] for value in causal_chain[:4]) if isinstance(causal_chain, list) else ""
        if not message:
            message = str(getattr(directive, "reject_reason", "") or "R9 门禁阻断")
        decision = str(passport.get("decision") or "BLOCK") if isinstance(passport, dict) else "BLOCK"
        raw_gate = passport.get("block_at_gate", -1) if isinstance(passport, dict) else -1
        gate_detail = _passport_gate_detail(passport, causal_chain, decision, raw_gate)
        gate = f"Gate {raw_gate}" if isinstance(raw_gate, int) and not isinstance(raw_gate, bool) and 0 <= raw_gate <= 5 else "--"
        timestamp = getattr(directive, "timestamp", None)
        if isinstance(timestamp, (int, float)) and math.isfinite(timestamp):
            try:
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(timestamp))
            except (OverflowError, OSError, ValueError):
                timestamp = ""
        live_events.append({
            "timestamp": _safe_text(timestamp, 80),
            "level": "INFO", "stage": "R9_GATE", "event": "R9_GATE_ACTIVE_DIRECTIVE",
            "status": _safe_text(decision, 32),
            "ticker": _safe_text(getattr(directive, "code", ""), 16),
            "request_id": request_id, "message": _safe_text(message, 300),
            "candidate_id": _safe_text(envelope.get("candidate_id"), 128),
            "decision": _safe_text(decision, 32), "reason": reject_code,
            "gate": gate, "execution_status": _safe_text(getattr(directive, "signal_state", ""), 32),
            "causal_chain": list(causal_chain[:8]) if isinstance(causal_chain, list) else [],
            "gate_detail": gate_detail,
            "operation_state": passport.get("operation_state", {}) if isinstance(passport, dict) and isinstance(passport.get("operation_state"), dict) else {},
            "reject_code": reject_code,
            "configuration_version": _safe_text(passport.get("configuration_version"), 64) if isinstance(passport, dict) else "",
            "configuration_hash": _safe_text(passport.get("configuration_hash"), 16) if isinstance(passport, dict) else "",
            "data_contract_hash": _safe_text(passport.get("data_contract_hash"), 16) if isinstance(passport, dict) else "",
        })
    events = (live_events + events)[:200]
    gate_events = [event for event in events if event.get("stage") == "R9_GATE"]
    diagnostic_history: Dict[str, List[Dict[str, Any]]] = {}
    for event in live_events:
        detail = event.get("gate_detail")
        code = event.get("ticker")
        if not isinstance(detail, dict) or not isinstance(code, str) or not code:
            continue
        as_of = detail.get("as_of_time")
        if not isinstance(as_of, str) or not as_of:
            as_of = event.get("timestamp", "")
        try:
            parsed_time = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        diagnostic_history.setdefault(code, []).append({
            "time": parsed_time, "as_of_time": as_of, "decision": event.get("decision", ""),
            "gate_detail": detail, "causal_chain": event.get("causal_chain", []),
            "operation_state": event.get("operation_state", {}),
            "configuration_version": event.get("configuration_version", ""),
            "configuration_hash": event.get("configuration_hash", ""),
            "data_contract_hash": event.get("data_contract_hash", ""),
        })
    gate_diagnostics = []
    gate_alerts = []
    for code, records in diagnostic_history.items():
        records.sort(key=lambda item: item["time"])
        deduplicated = {}
        for record in records:
            deduplicated[record["as_of_time"]] = record
        records = sorted(deduplicated.values(), key=lambda item: item["time"])
        latest = dict(records[-1])
        latest["ticker"] = code
        gate_diagnostics.append(latest)
        for previous, current in zip(records, records[1:]):
            before = previous["gate_detail"]
            after = current["gate_detail"]
            before_regime = before.get("regime", {}) if isinstance(before.get("regime"), dict) else {}
            after_regime = after.get("regime", {}) if isinstance(after.get("regime"), dict) else {}
            before_carry = before.get("carry", {}) if isinstance(before.get("carry"), dict) else {}
            after_carry = after.get("carry", {}) if isinstance(after.get("carry"), dict) else {}
            transitions = []
            old_state, new_state = before_regime.get("state"), after_regime.get("state")
            if isinstance(old_state, str) and isinstance(new_state, str) and old_state and new_state and old_state != new_state:
                transitions.append(f"Regime {old_state} → {new_state}")
            for field in ("state", "nonlinear_zone"):
                old_value, new_value = before_carry.get(field), after_carry.get(field)
                if isinstance(old_value, str) and isinstance(new_value, str) and old_value and new_value and old_value != new_value:
                    transitions.append(f"Carry {field} {old_value} → {new_value}")
            if transitions:
                gate_alerts.append({
                    "ticker": code, "as_of_time": current["as_of_time"],
                    "_sort_time": current["time"],
                    "message": "；".join(transitions),
                })
    gate_diagnostics.sort(key=lambda item: item["time"], reverse=True)
    gate_alerts.sort(key=lambda item: item["_sort_time"], reverse=True)
    gate_diagnostics = gate_diagnostics[:100]
    gate_alerts = gate_alerts[:30]
    for alert in gate_alerts:
        alert.pop("_sort_time", None)
    gate_summary = {
        "context_status": gate_context_status,
        "context_generation": gate_context_generation,
        "authorization_records": gate_authorization_records,
        "recent": len(gate_events),
        "entry": sum(event.get("decision") == "ENTRY" for event in gate_events),
        "watch": sum(event.get("decision") == "WATCH" for event in gate_events),
        "block": sum(event.get("decision") == "BLOCK" for event in gate_events),
        "active_block": sum(
            event.get("event") == "R9_GATE_ACTIVE_DIRECTIVE" and event.get("decision") == "BLOCK"
            for event in gate_events
        ),
        "active_entry": sum(
            event.get("event") == "R9_GATE_ACTIVE_DIRECTIVE" and event.get("decision") == "ENTRY"
            for event in gate_events
        ),
        "regime_carry_alerts": len(gate_alerts),
    }
    review_db = root / "logs" / "ipo_learning_reviews.sqlite"
    review_counts = {"ACCEPTED": 0, "REJECTED": 0}
    if review_db.is_file():
        candidate_ids = [event["candidate_id"] for event in events if event.get("candidate_id")]
        try:
            with sqlite3.connect(str(review_db), timeout=0.1) as connection:
                for decision, count in connection.execute(
                    "SELECT decision, COUNT(*) FROM sample_review_decisions GROUP BY decision"
                ).fetchall():
                    if decision in review_counts:
                        review_counts[decision] = int(count)
                if candidate_ids:
                    placeholders = ",".join("?" for _ in candidate_ids)
                    rows = connection.execute(
                        f"SELECT candidate_id, decision FROM sample_review_decisions WHERE candidate_id IN ({placeholders})",
                        candidate_ids,
                    ).fetchall()
                    reviewed = {row[0]: row[1] for row in rows}
                    for event in events:
                        if event.get("candidate_id") in reviewed:
                            event["reviewed"] = "true"
                            event["decision"] = reviewed[event["candidate_id"]]
        except sqlite3.Error:
            pass
    for event in events:
        if not event.get("message"):
            event["message"] = event.get("summary", "")
    pending_reviews = sum(1 for event in events if _reviewable(event))
    learning_status = (
        _safe_text(runtime.get("learning_status"))
        if stage_rows[4]["status"] == "已验收" and runtime.get("learning_status")
        else (
            f"Stage 4 未验收；最近事件成熟待复核 {pending_reviews}；"
            f"人工接受 {review_counts['ACCEPTED']} / 拒绝 {review_counts['REJECTED']}；训练保持关闭"
        )
    )
    gate_sync_raw = _read_json(
        root / "data" / "ipo_learning" / "gate_context_provider.latest.json",
        max_bytes=16 * 1024,
    ) or {}
    gate_sync_updated_at = _safe_text(gate_sync_raw.get("updated_at"), 40)
    gate_sync_age = None
    try:
        parsed_sync_time = datetime.fromisoformat(gate_sync_updated_at.replace("Z", "+00:00"))
        if parsed_sync_time.tzinfo is not None and parsed_sync_time.utcoffset() is not None:
            gate_sync_age = max(
                0.0,
                (datetime.now(timezone.utc) - parsed_sync_time.astimezone(timezone.utc)).total_seconds(),
            )
    except (TypeError, ValueError, OverflowError):
        pass
    gate_sync_state = _safe_text(gate_sync_raw.get("state"), 32) or "NOT_RUNNING"
    if gate_sync_age is None or gate_sync_age > 15.0:
        gate_sync_state = "STALE" if gate_sync_updated_at else "NOT_RUNNING"
    gate_context_sync = {
        "state": gate_sync_state,
        "updated_at": gate_sync_updated_at,
        "heartbeat_age_seconds": gate_sync_age,
        "reader_process_id": _nonnegative_count(gate_sync_raw.get("reader_process_id")),
        "stored_observation_count": _nonnegative_count(gate_sync_raw.get("stored_observation_count")),
        "typed_gate_contexts_ready": gate_sync_raw.get("typed_gate_contexts_ready") is True,
        "latest_context_readiness": (
            gate_sync_raw.get("latest_context_readiness")
            if isinstance(gate_sync_raw.get("latest_context_readiness"), dict) else {}
        ),
        "runtime_authorized": gate_sync_raw.get("runtime_authorized") is True,
        "refresh_error": _safe_text(gate_sync_raw.get("refresh_error"), 80),
        "transport": _safe_text(gate_sync_raw.get("transport"), 40),
    }
    return {
        "monitor_updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_status": "有效配置" if config_ok else "未就绪",
        "config_detail": config_detail,
        "provider": backend,
        "provider_preflight": provider_preflight,
        "gate_context_sync": gate_context_sync,
        "runtime_status": runtime_status,
        "runtime_age": runtime_age,
        "runtime_qualified": runtime_qualified,
        "simulation_only": simulation_only,
        "simulation_provider": _safe_text(simulation_manifest.get("provider"), 80),
        "simulation_result": _safe_text(simulation_manifest.get("result_status"), 40),
        "worker_monitor": worker_monitor,
        "interaction_summary": interaction_summary,
        "rule_path": "确定性规则路径；LLM 结果只读且不参与下单",
        "learning_status": learning_status,
        "learning_progress": {
            "pending_reviews": pending_reviews,
            "accepted_reviews": review_counts["ACCEPTED"],
            "rejected_reviews": review_counts["REJECTED"],
            "decision_snapshot_count": snapshot_summary["snapshot_count"],
            "snapshot_storage_status": snapshot_summary["status"],
            "waiting_outcome_count": snapshot_summary["waiting_outcome_count"],
            "latest_snapshot_at": snapshot_summary["latest_captured_at"],
            "snapshot_writer_queued": snapshot_writer["queued"],
            "snapshot_writer_dropped": snapshot_writer["dropped"],
            "snapshot_writer_failed": snapshot_writer["failed"],
            "snapshot_writer_last_error": _safe_text(snapshot_writer.get("last_error"), 180),
            "dataset_status": dataset_status,
            "sealed_dataset_count": dataset_summary["dataset_count"],
            "sealed_sample_count": dataset_summary["sample_count"],
            "sealed_event_group_count": dataset_summary["event_group_count"],
            "latest_sealed_at": dataset_summary["latest_sealed_at"],
            "dataset_integrity": dataset_summary["integrity"],
            "replay_report_hash": replay_summary["replay_report_hash"],
            "replay_cutoff_count": replay_summary["cutoff_count"],
            "replay_unready_cutoff_count": replay_summary["unready_cutoff_count"],
            "effect_metric_status": effect_metric_status,
            "measured_effect_metric_count": measured_metric_count if replay_summary["status"] == "AVAILABLE" else 0,
            "training_status": "训练执行器未接入",
            "shadow_status": shadow_status,
            "promotion_status": "模型切换关闭",
        },
        "decision_snapshots": snapshot_rows,
        "outcome_labels": _collect_outcome_label_rows(root),
        "stages": stage_rows,
        "replay_effect_metrics": replay_summary.get("effect_metrics", {}),
        "contracts": contract_rows,
        "contract_status_counts": contract_status_counts,
        "source_health": _collect_local_source_health(root),
        "events": events,
        "gate_summary": gate_summary,
        "gate_diagnostics": gate_diagnostics,
        "gate_alerts": gate_alerts,
        "market_snapshot": market_snapshot,
        "operation_states": operation_states,
        "acceptance_file": str(acceptance_path),
    }


def _collect_outcome_label_rows(root: Path) -> List[Dict[str, str]]:
    """Read bounded, whitelisted D1-D3 outcome evidence for the learning console."""
    directory = root / "data" / "ipo_learning" / "outcome_evidence"
    try:
        from ats.strategy.ipo_outcome_review import load_latest_outcome_reviews

        reviews = load_latest_outcome_reviews(root)
    except Exception:
        reviews = {}
    try:
        paths = sorted(
            (path for path in directory.glob("*.json") if path.is_file() and path.stat().st_size <= 64 * 1024),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:200]
    except OSError:
        return []
    rows = []
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as stream:
                item = json.load(stream)
            if not isinstance(item, dict) or item.get("schema_version") != "ipo-outcome-evidence.v1":
                continue
            evidence_id = _safe_text(item.get("evidence_id"), 160)
            evidence_hash = _safe_text(item.get("evidence_hash"), 64)
            review = reviews.get(evidence_id, {})
            review_status = "待人工复核"
            if review.get("evidence_hash") == evidence_hash:
                review_status = {
                    "ACCEPTED": "已确认",
                    "REJECTED": "已拒绝",
                }.get(review.get("decision"), review_status)
            rows.append({
                "ticker": _safe_text(item.get("ticker"), 16),
                "listing_date": _safe_text(item.get("listing_date"), 10),
                "d1": _number_label(item.get("d1_return_pct"), 2, "%"),
                "d2": _number_label(item.get("d2_return_pct"), 2, "%"),
                "d3": _number_label(item.get("d3_return_pct"), 2, "%"),
                "drawdown": _number_label(item.get("d1_d3_close_max_drawdown_pct"), 2, "%"),
                "issue_break": "是" if item.get("broke_issue_price") is True else "否",
                "anchor_break": (
                    "是" if item.get("broke_both_listing_anchors") is True else
                    "否" if item.get("broke_both_listing_anchors") is False else "未就绪"
                ),
                "matured_at": _safe_text(item.get("matured_at"), 40),
                "review": review_status if item.get("review_status") == "PENDING_HUMAN_REVIEW" else "待检查",
                "evidence_id": evidence_id,
                "evidence_hash": evidence_hash,
                "evidence_path": str(path.resolve()),
            })
        except (OSError, UnicodeError, ValueError, TypeError):
            continue
    return rows


def _is_market_session_active() -> bool:
    try:
        from ats.tdx_realtime_fetcher import is_trading_time

        return bool(is_trading_time()[0])
    except Exception:
        return False


class _LearningMonitorWorker(QThread):
    snapshot_ready = pyqtSignal(dict)
    review_completed = pyqtSignal(str, bool, str)
    outcome_review_completed = pyqtSignal(str, bool, str)
    interaction_detail_ready = pyqtSignal(str, str)

    def __init__(self, project_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._root = project_root
        self._commands: "queue.Queue[Dict[str, str]]" = queue.Queue(maxsize=32)
        self._stopping = False
        self._interval = 2.0

    def request_refresh(self) -> None:
        try:
            self._commands.put_nowait({"command": "refresh"})
        except queue.Full:
            pass

    def request_interaction_detail(self, request_id: str) -> bool:
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
            return False
        try:
            self._commands.put_nowait({
                "command": "interaction_detail", "request_id": request_id,
            })
            return True
        except queue.Full:
            return False

    def submit_note(self, note: str, source_event: Dict[str, str]) -> bool:
        try:
            self._commands.put_nowait({
                "command": "note", "message": note[:500],
                "source_stage": source_event.get("stage", "")[:80],
                "source_event": source_event.get("event", "")[:100],
                "candidate_id": source_event.get("candidate_id", "")[:128],
                "request_id": source_event.get("request_id", "")[:128],
                "ticker": source_event.get("ticker", "")[:16],
            })
            return True
        except queue.Full:
            return False

    def submit_review(self, event: Dict[str, str], decision: str, reviewer: str, reason: str) -> bool:
        if (
            not _reviewable(event) or decision not in {"ACCEPTED", "REJECTED"}
            or not reviewer.strip() or not reason.strip()
        ):
            return False
        try:
            self._commands.put_nowait({
                "command": "review", "candidate_id": event["candidate_id"],
                "decision": decision, "reviewer": reviewer[:120], "reason": reason[:500],
                "input_snapshot_hash": event["input_snapshot_hash"],
                "cutoff": event["cutoff"], "label_source": event["label_source"],
                "model_id": event["model_id"], "prompt_version": event["prompt_version"],
                "review_draft_hash": event["review_draft_hash"],
                "outcome_evidence_ids_json": event["outcome_evidence_ids_json"],
                "ticker": event["ticker"], "event_id": event["event_id"],
                "listing_date": event["listing_date"], "matured_at": event["matured_at"],
                "configuration_hash": event["configuration_hash"],
                "data_contract_hash": event["data_contract_hash"],
            })
            return True
        except queue.Full:
            return False

    def submit_outcome_review(
        self, record: Dict[str, str], decision: str, reviewer: str, reason: str,
    ) -> bool:
        if (
            not isinstance(record, dict)
            or record.get("review") != "待人工复核"
            or not record.get("evidence_id")
            or not re.fullmatch(r"[0-9a-fA-F]{64}", record.get("evidence_hash", ""))
            or decision not in {"ACCEPTED", "REJECTED"}
            or not reviewer.strip() or not reason.strip()
        ):
            return False
        try:
            self._commands.put_nowait({
                "command": "outcome_review", "evidence_id": record["evidence_id"],
                "evidence_path": record["evidence_path"],
                "evidence_hash": record["evidence_hash"],
                "decision": decision, "reviewer": reviewer[:120], "reason": reason[:1000],
            })
            return True
        except queue.Full:
            return False

    def stop(self) -> None:
        self._stopping = True
        try:
            self._commands.put_nowait({"command": "stop"})
        except queue.Full:
            pass

    def run(self) -> None:
        while not self._stopping:
            market_active = _is_market_session_active()
            payload = None
            try:
                timeout = self._interval if market_active else 60.0
                payload = self._commands.get(timeout=timeout)
                command = payload.get("command")
                if command == "stop":
                    break
                if command == "note":
                    self._append_note(payload)
                elif command == "review":
                    saved, detail = self._append_review(payload)
                    self.review_completed.emit(
                        payload.get("candidate_id", ""), saved, detail
                    )
                elif command == "outcome_review":
                    saved, detail = self._append_outcome_review(payload)
                    self.outcome_review_completed.emit(
                        payload.get("evidence_id", ""), saved, detail
                    )
                elif command == "interaction_detail":
                    self._load_interaction_detail(payload.get("request_id", ""))
            except queue.Empty:
                pass
            if not self._stopping and (market_active or payload is not None):
                self.snapshot_ready.emit(_collect_snapshot(self._root))

    def _load_interaction_detail(self, request_id: str) -> None:
        try:
            from ats.llm.interaction_journal import get_agent_interaction_detail

            detail = get_agent_interaction_detail(self._root, request_id)
            if detail is None:
                text = "没有找到已保存的校验结果。"
            else:
                text = json.dumps(
                    detail, ensure_ascii=False, sort_keys=True, indent=2,
                )
        except Exception:
            text = "读取校验结果失败。"
        self.interaction_detail_ready.emit(request_id, text)

    def _append_note(self, payload: Dict[str, str]) -> None:
        note = payload.get("message", "")
        if not note.strip():
            return
        path = self._root / "logs" / "ipo_learning_events.jsonl"
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "level": "INFO",
            "stage": "OPERATOR",
            "event": "OPERATOR_NOTE",
            "status": "RECORDED",
            "message": note.strip(),
            "related_event": {
                key: payload[key] for key in (
                    "source_stage", "source_event", "candidate_id", "request_id", "ticker"
                ) if payload.get(key)
            },
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            return

    def _append_outcome_review(self, payload: Dict[str, str]) -> Tuple[bool, str]:
        try:
            from ats.strategy.ipo_outcome_review import record_outcome_review

            result = record_outcome_review(
                self._root, payload.get("evidence_path", ""),
                decision=payload.get("decision", ""),
                reviewer=payload.get("reviewer", ""),
                reason=payload.get("reason", ""),
            )
        except Exception:
            return False, "标签证据复核写入失败。"
        if (
            result.get("status") != "SAVED"
            or result.get("evidence_id") != payload.get("evidence_id")
            or result.get("evidence_hash") != payload.get("evidence_hash")
        ):
            return False, _safe_text(result.get("reason"), 160) or "标签证据复核校验失败。"
        return True, "决定已写入追加式审计库；原始证据未修改，训练授权仍关闭。"

    def _append_review(self, review: Dict[str, str]) -> Tuple[bool, str]:
        path = self._root / "logs" / "ipo_learning_events.jsonl"
        candidate_id = review.get("candidate_id", "")
        outcome_refs = _outcome_evidence_ids(review.get("outcome_evidence_ids_json", ""))
        if (
            not candidate_id or outcome_refs is None
            or not re.fullmatch(r"\d{6}", review.get("ticker", ""))
            or not review.get("event_id") or len(review.get("event_id", "")) > 160
            or "\x00" in review.get("event_id", "")
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", review.get("listing_date", ""))
            or not re.fullmatch(r"[0-9a-fA-F]{64}", review.get("configuration_hash", ""))
            or not re.fullmatch(r"[0-9a-fA-F]{64}", review.get("data_contract_hash", ""))
        ):
            return False, "候选事件身份、配置哈希或结果证据无效，复核未保存。"
        try:
            date.fromisoformat(review.get("listing_date", ""))
        except ValueError:
            return False, "上市日期无效，复核未保存。"
        review_time = datetime.now(timezone.utc).isoformat()
        db_path = self._root / "logs" / "ipo_learning_reviews.sqlite"
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(db_path), timeout=1.0) as connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS sample_review_decisions (
                        candidate_id TEXT PRIMARY KEY,
                        decision TEXT NOT NULL,
                        reviewer TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        input_snapshot_hash TEXT NOT NULL,
                        cutoff TEXT NOT NULL,
                        label_source TEXT NOT NULL,
                        reviewed_at TEXT NOT NULL,
                        model_id TEXT NOT NULL DEFAULT '',
                        prompt_version TEXT NOT NULL DEFAULT '',
                        review_draft_hash TEXT NOT NULL DEFAULT '',
                        outcome_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                        ticker TEXT NOT NULL DEFAULT '',
                        event_id TEXT NOT NULL DEFAULT '',
                        listing_date TEXT NOT NULL DEFAULT '',
                        matured_at TEXT NOT NULL DEFAULT '',
                        configuration_hash TEXT NOT NULL DEFAULT '',
                        data_contract_hash TEXT NOT NULL DEFAULT ''
                    )"""
                )
                existing_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(sample_review_decisions)").fetchall()
                }
                for column in ("model_id", "prompt_version", "review_draft_hash"):
                    if column not in existing_columns:
                        connection.execute(
                            f"ALTER TABLE sample_review_decisions ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                        )
                if "outcome_evidence_ids_json" not in existing_columns:
                    connection.execute(
                        "ALTER TABLE sample_review_decisions "
                        "ADD COLUMN outcome_evidence_ids_json TEXT NOT NULL DEFAULT '[]'"
                    )
                for column in (
                    "ticker", "event_id", "listing_date", "matured_at",
                    "configuration_hash", "data_contract_hash",
                ):
                    if column not in existing_columns:
                        connection.execute(
                            f"ALTER TABLE sample_review_decisions ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                        )
                connection.commit()
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """INSERT INTO sample_review_decisions
                        (candidate_id, decision, reviewer, reason, input_snapshot_hash,
                        cutoff, label_source, reviewed_at, model_id, prompt_version, review_draft_hash,
                        outcome_evidence_ids_json, ticker, event_id, listing_date, matured_at,
                        configuration_hash, data_contract_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        candidate_id, review.get("decision", ""), review.get("reviewer", ""),
                        review.get("reason", ""), review.get("input_snapshot_hash", ""),
                        review.get("cutoff", ""), review.get("label_source", ""), review_time,
                        review.get("model_id", ""), review.get("prompt_version", ""),
                        review.get("review_draft_hash", ""),
                        json.dumps(outcome_refs, ensure_ascii=False, separators=(",", ":")),
                        review.get("ticker", ""), review.get("event_id", ""),
                        review.get("listing_date", ""), review.get("matured_at", ""),
                        review.get("configuration_hash", ""), review.get("data_contract_hash", ""),
                    ),
                )
        except sqlite3.IntegrityError:
            return False, "该候选已存在复核记录，未重复写入。"
        except (OSError, sqlite3.Error):
            return False, "复核数据库写入失败，请检查日志目录或数据库状态。"
        event = {
            "timestamp": review_time,
            "level": "INFO",
            "stage": "STAGE_4_REVIEW",
            "event": "SAMPLE_REVIEW_DECISION",
            "status": "RECORDED",
            **review,
            "outcome_evidence_ids": outcome_refs,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            return True, "复核已写入数据库；事件日志镜像写入失败。"
        return True, "复核已写入审计数据库和事件日志。"


class _SourceAcquisitionWorker(QThread):
    completed = pyqtSignal(dict)

    def __init__(
        self, project_root: Path, ticker: str, collect_labels: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._root = project_root
        self._ticker = ticker
        self._collect_labels = collect_labels

    def run(self) -> None:
        try:
            from tools.run_ipo_data_acquisition import run_cycle

            result = run_cycle(self._ticker, collect_labels=self._collect_labels, root=self._root)
        except Exception as exc:
            result = {"status": "UNREADY", "reason": type(exc).__name__}
        self.completed.emit(result)


class IPOLearningConsole(QWidget):
    """Live view for staged readiness, sidecar health and mature-sample reviews."""

    def __init__(
        self, parent: Optional[QWidget] = None, project_root: Optional[str] = None,
        simulation_read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        if project_root:
            self._root = Path(project_root)
        else:
            # __file__ points into PyInstaller's temporary _MEI directory when frozen;
            # use the shared resolver, which returns the physical application root.
            from sys_utils import get_app_root

            self._root = Path(get_app_root())
        self._simulation_read_only = simulation_read_only is True
        self._worker = _LearningMonitorWorker(self._root, self)
        self._worker.snapshot_ready.connect(self._render_snapshot)
        self._worker.review_completed.connect(self._review_completed)
        self._worker.outcome_review_completed.connect(self._outcome_review_completed)
        self._worker.interaction_detail_ready.connect(self._show_interaction_detail)
        self._selected_event: Optional[Dict[str, str]] = None
        self._selected_snapshot_id = ""
        self._pending_interaction_detail_id = ""
        self._review_pending_candidate_ids = set()
        self._outcome_review_pending_ids = set()
        self._runtime_control = None
        self._source_worker: Optional[_SourceAcquisitionWorker] = None
        self._build_ui()
        if self._simulation_read_only:
            self.lbl_boundary.setText(
                "仿真只读监控：行情与指标为合成数据；本次 Provider 调用不构成 Stage 验收、"
                "不产生交易授权，也不触发真实数据采集或人工复核写入。"
            )
            for button in self.findChildren(QPushButton):
                if button not in {self.btn_refresh, self.btn_interaction_detail}:
                    button.setEnabled(False)
                    button.setToolTip("仿真只读模式已禁用写入和采集操作")
        self._worker.start()
        if not self._simulation_read_only:
            try:
                from ats.llm.runtime_service import create_runtime_control_thread

                self._runtime_control = create_runtime_control_thread(self._root)
                self._runtime_control.start()
            except Exception:
                self._runtime_control = None
            self._source_auto_timer = QTimer(self)
            market_active = _is_market_session_active()
            self._source_auto_timer.setInterval(
                5 * 60 * 1000 if market_active else 60 * 1000
            )
            self._source_auto_timer.timeout.connect(self._on_source_auto_tick)
            self._source_auto_timer.start()
            if market_active:
                QTimer.singleShot(
                    2500, lambda: self._start_source_collection(collect_labels=True)
                )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 顶部自适应两行容器：第1行状态栏，第2行操作栏
        header_container = QVBoxLayout()
        header_container.setSpacing(4)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.lbl_runtime = QLabel("LLM 旁路：读取中")
        self.lbl_provider = QLabel("Provider：读取中")
        self.lbl_worker = QLabel("Worker：读取中")
        self.lbl_learning = QLabel("离线学习：读取中")
        self.lbl_monitor_updated_at = QLabel("监控刷新：读取中")
        for label in (
            self.lbl_runtime, self.lbl_provider, self.lbl_worker, self.lbl_learning,
            self.lbl_monitor_updated_at,
        ):
            label.setStyleSheet("font-weight: bold; padding: 4px 6px; background: #20232b; border: 1px solid #414653; border-radius: 3px;")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            status_row.addWidget(label, 1)
        header_container.addLayout(status_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addStretch(1)

        self.btn_refresh = QPushButton("立即刷新")
        self.btn_refresh.clicked.connect(self._worker.request_refresh)
        self.btn_note = QPushButton("记录复核备注")
        self.btn_note.setToolTip("写入审计事件，不会自动生成训练标签或触发模型更新")
        self.btn_note.clicked.connect(self._add_note)
        self.btn_accept = QPushButton("接收成熟样本")
        self.btn_accept.setToolTip("仅接受带成熟标签、结果证据、快照与复核草稿哈希、模型/提示版本、Gate 因果链、标的事件身份及配置/数据契约哈希的样本；不会启动训练")
        self.btn_accept.setEnabled(False)
        self.btn_accept.clicked.connect(lambda: self._review_candidate("ACCEPTED"))
        self.btn_reject = QPushButton("拒绝样本")
        self.btn_reject.setEnabled(False)
        self.btn_reject.clicked.connect(lambda: self._review_candidate("REJECTED"))

        for btn in (self.btn_refresh, self.btn_note, self.btn_accept, self.btn_reject):
            btn.setStyleSheet("padding: 4px 10px; font-weight: bold;")
            action_row.addWidget(btn)

        header_container.addLayout(action_row)
        layout.addLayout(header_container)

        self.content_tabs = QTabWidget()
        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        self.lbl_rule = QLabel("规则路径：读取中")
        self.lbl_rule.setWordWrap(True)
        overview_layout.addWidget(self.lbl_rule)
        self.lbl_market_hud = QLabel("IPO 市场 HUD：等待实时行情快照")
        self.lbl_market_hud.setWordWrap(True)
        self.lbl_market_hud.setStyleSheet("padding: 6px; background: #20232b; border: 1px solid #414653;")
        overview_layout.addWidget(self.lbl_market_hud)
        self.lbl_learning_progress = QLabel("样本闭环：读取中")
        self.lbl_learning_progress.setWordWrap(True)
        self.lbl_learning_progress.setStyleSheet(
            "padding: 6px; background: #20232b; border: 1px solid #8a7040; color: #f0c674;"
        )
        overview_layout.addWidget(self.lbl_learning_progress)
        self.lbl_boundary = QLabel(
            "此页只读监控运行与人工审阅记录；页面状态不授予交易权限，样本审阅也不会直接启动训练。"
        )
        self.lbl_boundary.setStyleSheet("color: #f0c674; padding: 4px;")
        overview_layout.addWidget(self.lbl_boundary)
        self.lbl_operator_guide = QLabel(
            "启动：python tools/run_ipo_learning_console.py。推荐顺序：①数据契约与时效：看字段状态并运行采集；"
            "②单股因果与状态告警：看 Gate 阻断原因；"
            "③盘后生成 D1-D3 标签，再到成熟标签页人工复核；④回放效果验收：看已量化指标。"
        )
        self.lbl_operator_guide.setWordWrap(True)
        self.lbl_operator_guide.setStyleSheet(
            "padding: 7px; background: #172536; border: 1px solid #42627f; color: #d7e8f7;"
        )
        overview_layout.addWidget(self.lbl_operator_guide)
        guide_actions = QHBoxLayout()
        for label, tab_name in (
            ("① 数据与采集", "数据契约与时效"),
            ("② Gate 诊断", "单股因果与状态告警"),
            ("③ 标签复核", "D1-D3 成熟标签"),
            ("④ 回放验收", "回放效果验收"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, name=tab_name: self._select_console_tab(name)
            )
            guide_actions.addWidget(button)
        guide_actions.addStretch(1)
        overview_layout.addLayout(guide_actions)
        self.stage_table = QTableWidget(0, 3)
        self.stage_table.setHorizontalHeaderLabels(["阶段", "状态", "准入说明"])
        self.stage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.stage_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.stage_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stage_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        overview_layout.addWidget(self.stage_table)
        self.content_tabs.addTab(overview, "实施阶段")

        replay_metrics_page = QWidget()
        replay_metrics_layout = QVBoxLayout(replay_metrics_page)
        replay_metrics_layout.addWidget(QLabel(
            "每 2 秒读取最近一次已保存回放的 13 项验收指标。不可评估表示缺少真实标签、基线或回归集，不计为通过。"
        ))
        self.replay_metrics_table = QTableWidget(0, 4)
        self.replay_metrics_table.setHorizontalHeaderLabels(["验收指标", "状态", "数值", "证据 / 缺口"])
        self.replay_metrics_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.replay_metrics_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.replay_metrics_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.replay_metrics_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.replay_metrics_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.replay_metrics_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        replay_metrics_layout.addWidget(self.replay_metrics_table)
        self.content_tabs.addTab(replay_metrics_page, "回放效果验收")

        provider_page = QWidget()
        provider_layout = QVBoxLayout(provider_page)
        provider_layout.addWidget(QLabel(
            "只读环境预检：不会实例化模型、探测服务或启动旁路。绿色仅表示单项静态检查通过，"
            "不能替代模型/Windows/结构化输出/隔离压测验收。"
        ))
        self.provider_table = QTableWidget(0, 3)
        self.provider_table.setHorizontalHeaderLabels(["检查项", "状态", "结果 / 缺口"])
        self.provider_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.provider_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.provider_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.provider_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.provider_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        provider_layout.addWidget(self.provider_table)
        self.content_tabs.addTab(provider_page, "Provider / 本地运行预检")

        contracts_page = QWidget()
        contracts_layout = QVBoxLayout(contracts_page)
        contracts_layout.addWidget(QLabel(
            "41 项必需输入的来源契约与时效；只有配置完整且观测来源/版本/时区/TTL 均匹配时才显示新鲜。"
        ))
        self.contract_table = QTableWidget(0, 14)
        self.lbl_contract_status = QLabel("数据契约：等待读取 41 项来源与实时观测状态")
        self.lbl_contract_status.setWordWrap(True)
        self.lbl_contract_status.setStyleSheet(
            "padding: 6px; background: #20232b; border: 1px solid #414653; color: #f0c674;"
        )
        contracts_layout.addWidget(self.lbl_contract_status)
        source_actions = QHBoxLayout()
        self.edt_acquisition_code = QLineEdit("301689")
        self.edt_acquisition_code.setMaxLength(6)
        self.edt_acquisition_code.setFixedWidth(86)
        self.edt_acquisition_code.setPlaceholderText("六位代码")
        self.btn_collect_issue_price = QPushButton("采集可用数据并自检")
        self.btn_collect_issue_price.clicked.connect(self._collect_supported_source)
        self.btn_collect_labels = QPushButton("盘后生成 D1-D3 标签")
        self.btn_collect_labels.setToolTip(
            "15:30 后扫描冻结快照及近45日新股日历，分批生成成熟 D1-D3 证据；"
            "仅进入人工复核池，不会自动训练"
        )
        self.btn_collect_labels.clicked.connect(self._collect_matured_labels)
        self.lbl_acquisition_status = QLabel(
            "自动采集仅在交易时段运行；休市时每 60 秒更新一次状态心跳。"
        )
        self.lbl_acquisition_status.setWordWrap(True)
        source_actions.addWidget(QLabel("标的"))
        source_actions.addWidget(self.edt_acquisition_code)
        source_actions.addWidget(self.btn_collect_issue_price)
        source_actions.addWidget(self.btn_collect_labels)
        source_actions.addWidget(self.lbl_acquisition_status, 1)
        contracts_layout.addLayout(source_actions)
        self.contract_table.setHorizontalHeaderLabels(
            [
                "指标", "标的", "当前值", "来源@版本", "来源时区", "TTL 秒", "单位",
                "统计窗口", "缺失策略", "as_of", "available_at", "实时状态",
                "采集/计算路线", "自检与下一步",
            ]
        )
        for index in range(11):
            self.contract_table.horizontalHeader().setSectionResizeMode(
                index, QHeaderView.ResizeMode.ResizeToContents
            )
        self.contract_table.horizontalHeader().setSectionResizeMode(11, QHeaderView.ResizeMode.ResizeToContents)
        self.contract_table.horizontalHeader().setSectionResizeMode(12, QHeaderView.ResizeMode.ResizeToContents)
        self.contract_table.horizontalHeader().setSectionResizeMode(13, QHeaderView.ResizeMode.Stretch)
        self.contract_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.contract_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        contracts_layout.addWidget(self.contract_table)
        self.content_tabs.addTab(contracts_page, "数据契约与时效")

        sources_page = QWidget()
        sources_layout = QVBoxLayout(sources_page)
        sources_layout.addWidget(QLabel(
            "每 2 秒读取已运行实例的本地缓存状态，不触发网络请求或连接 Provider；缓存在线不代表数据契约、回放或准入已验收。"
        ))
        self.source_health_table = QTableWidget(0, 5)
        self.source_health_table.setHorizontalHeaderLabels(["来源", "状态", "缓存规模", "最近缓存年龄", "说明"])
        for index, mode in enumerate((
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.Stretch,
        )):
            self.source_health_table.horizontalHeader().setSectionResizeMode(index, mode)
        self.source_health_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_health_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        sources_layout.addWidget(self.source_health_table)
        self.content_tabs.addTab(sources_page, "本地来源实时状态")

        snapshots_page = QWidget()
        snapshots_layout = QVBoxLayout(snapshots_page)
        snapshots_layout.addWidget(QLabel(
            "仅记录通过 Gate 0 全 41 项来源、时区、available_at 与 TTL 校验的冻结快照。"
            "选择一条记录查看输入值和来源血缘；结果标签成熟前不会进入人工训练复核。"
        ))
        snapshot_actions = QHBoxLayout()
        self.btn_snapshot_note = QPushButton("为所选快照记录备注")
        self.btn_snapshot_note.setEnabled(False)
        self.btn_snapshot_note.clicked.connect(self._add_snapshot_note)
        snapshot_actions.addWidget(self.btn_snapshot_note)
        snapshot_actions.addStretch(1)
        snapshots_layout.addLayout(snapshot_actions)
        self.snapshot_table = QTableWidget(0, 6)
        self.snapshot_table.setHorizontalHeaderLabels(
            ["决策截点", "标的", "Gate 决策", "输入哈希", "学习状态", "事件 ID"]
        )
        for index, mode in enumerate((
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.Stretch,
        )):
            self.snapshot_table.horizontalHeader().setSectionResizeMode(index, mode)
        self.snapshot_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.snapshot_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.snapshot_table.itemSelectionChanged.connect(self._show_selected_snapshot)
        snapshots_layout.addWidget(self.snapshot_table, 1)
        self.snapshot_detail = QPlainTextEdit()
        self.snapshot_detail.setReadOnly(True)
        self.snapshot_detail.setMaximumBlockCount(1200)
        self.snapshot_detail.setPlaceholderText("选择冻结快照查看 41 项输入值、来源版本和时点。")
        snapshots_layout.addWidget(self.snapshot_detail, 1)
        self.content_tabs.addTab(snapshots_page, "学习输入快照")

        outcome_page = QWidget()
        outcome_layout = QVBoxLayout(outcome_page)
        outcome_layout.addWidget(QLabel(
            "D1-D3 结果只生成带来源时点的待复核证据；D3 收盘前保持待成熟，缺少首日锚点时明确显示未就绪，"
            "不会自动接受样本或开启训练。"
        ))
        self.outcome_table = QTableWidget(0, 10)
        self.outcome_table.setHorizontalHeaderLabels([
            "代码", "上市日", "D1 收益", "D2 收益", "D3 收益", "D1-D3 收盘回撤",
            "破发行价", "双锚失守", "成熟时点", "复核状态",
        ])
        for index in range(9):
            self.outcome_table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        self.outcome_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        self.outcome_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.outcome_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.outcome_table.itemSelectionChanged.connect(self._show_selected_outcome)
        outcome_layout.addWidget(self.outcome_table)
        outcome_actions = QHBoxLayout()
        self.btn_accept_outcome = QPushButton("确认标签证据")
        self.btn_accept_outcome.setToolTip("确认标签证据质量；原始证据只读，不会加入训练")
        self.btn_accept_outcome.setEnabled(False)
        self.btn_accept_outcome.clicked.connect(lambda: self._review_outcome_label("ACCEPTED"))
        self.btn_reject_outcome = QPushButton("拒绝标签证据")
        self.btn_reject_outcome.setToolTip("拒绝无效/错误标签并记录理由；不会删除原始证据")
        self.btn_reject_outcome.setEnabled(False)
        self.btn_reject_outcome.clicked.connect(lambda: self._review_outcome_label("REJECTED"))
        outcome_actions.addWidget(self.btn_accept_outcome)
        outcome_actions.addWidget(self.btn_reject_outcome)
        outcome_actions.addStretch(1)
        outcome_layout.addLayout(outcome_actions)
        self.content_tabs.addTab(outcome_page, "D1-D3 成熟标签")

        operation_page = QWidget()
        operation_layout = QVBoxLayout(operation_page)
        self.lbl_operation_summary = QLabel("操作状态机：等待交易中心生命周期事件")
        self.lbl_operation_summary.setStyleSheet("color: #f0c674; padding: 3px;")
        operation_layout.addWidget(self.lbl_operation_summary)
        operation_layout.addWidget(QLabel(
            "状态迁移由 Gate 评估与确认的本地账本成交驱动；LOCAL_PAPER_SIMULATOR 明确表示本地模拟成交。"
        ))
        self.operation_table = QTableWidget(0, 6)
        self.operation_table.setHorizontalHeaderLabels(
            ["标的", "当前状态", "最近迁移", "迁移时间", "原因", "迁移次数 / 快照版本"]
        )
        for index, mode in enumerate((
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.Stretch,
            QHeaderView.ResizeMode.ResizeToContents,
        )):
            self.operation_table.horizontalHeader().setSectionResizeMode(index, mode)
        self.operation_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.operation_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        operation_layout.addWidget(self.operation_table, 1)
        self.content_tabs.addTab(operation_page, "实时操作状态机")

        diagnostics_page = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_page)
        self.lbl_gate_alerts = QLabel("Regime / Carry 状态变化：等待连续有效快照")
        self.lbl_gate_alerts.setWordWrap(True)
        self.lbl_gate_alerts.setStyleSheet("color: #f0c674; padding: 5px; background: #20232b; border: 1px solid #414653;")
        diagnostics_layout.addWidget(self.lbl_gate_alerts)
        diagnostics_layout.addWidget(QLabel(
            "单股诊断来自最近一次真实 Gate 评估；缺少快照时显示 UNAVAILABLE，指标值不以默认零值代替。"
        ))
        self.gate_diagnostic_table = QTableWidget(0, 11)
        self.gate_diagnostic_table.setHorizontalHeaderLabels(
            ["标的", "评估时点", "决策", "Gate 0–5", "Regime", "PreHeat", "LiveHeat", "Carry", "VWAP", "RiskGate", "下一条件"]
        )
        for index, mode in enumerate((
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.Stretch,
        )):
            self.gate_diagnostic_table.horizontalHeader().setSectionResizeMode(index, mode)
        self.gate_diagnostic_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.gate_diagnostic_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.gate_diagnostic_table.itemSelectionChanged.connect(self._show_selected_gate_diagnostic)
        diagnostics_layout.addWidget(self.gate_diagnostic_table, 1)
        self.gate_diagnostic_detail = QPlainTextEdit()
        self.gate_diagnostic_detail.setReadOnly(True)
        self.gate_diagnostic_detail.setMaximumBlockCount(80)
        self.gate_diagnostic_detail.setMaximumHeight(165)
        self.gate_diagnostic_detail.setPlaceholderText("选择标的查看正负因素、锚点、Gate 因果链和操作状态。")
        diagnostics_layout.addWidget(self.gate_diagnostic_detail)
        self.content_tabs.addTab(diagnostics_page, "单股因果与状态告警")

        events_page = QWidget()
        events_layout = QVBoxLayout(events_page)
        self.lbl_gate_summary = QLabel("R9 Gate 实时审计：等待快照")
        self.lbl_gate_summary.setStyleSheet("color: #f0c674; padding: 3px;")
        events_layout.addWidget(self.lbl_gate_summary)
        events_layout.addWidget(QLabel("最近 200 条自学习事件（含交易中心 R9 门禁；双击 Gate 事件打开仲裁详情；仅显示状态摘要，不展示提示词、行情原文或模型载荷）"))
        self.event_table = QTableWidget(0, 7)
        self.event_table.setHorizontalHeaderLabels(["时间", "阶段", "事件", "状态", "标的", "Gate", "摘要"])
        for index, mode in enumerate((
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.Stretch,
        )):
            self.event_table.horizontalHeader().setSectionResizeMode(index, mode)
        self.event_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.event_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.event_table.itemSelectionChanged.connect(self._show_selected_event)
        self.event_table.cellDoubleClicked.connect(self._open_gate_event_detail)
        events_layout.addWidget(self.event_table, 1)
        self.event_detail = QPlainTextEdit()
        self.event_detail.setReadOnly(True)
        self.event_detail.setMaximumBlockCount(20)
        self.event_detail.setMaximumHeight(80)
        self.event_detail.setPlaceholderText("选择事件查看其审计摘要。")
        events_layout.addWidget(self.event_detail)
        self.content_tabs.addTab(events_page, "学习事件与复核")

        interactions_page = QWidget()
        interactions_layout = QVBoxLayout(interactions_page)
        self.lbl_interaction_summary = QLabel("LLM 交互：等待新鲜 Worker 状态")
        self.lbl_interaction_summary.setWordWrap(True)
        self.lbl_interaction_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_interaction_summary.setStyleSheet(
            "color: #f0c674; padding: 5px; background: #20232b; border: 1px solid #414653;"
        )
        interactions_layout.addWidget(self.lbl_interaction_summary)
        interactions_layout.addWidget(QLabel(
            "每 2 秒刷新最近 100 条结果。档案只保存通过严格校验的响应、输入时点、模型/提示版本、证据 ID 与哈希；不保存提示词或未校验原始响应。"
        ))
        self.interaction_table = QTableWidget(0, 6)
        self.interaction_table.setHorizontalHeaderLabels(
            ["完成时间", "标的", "Agent", "状态", "响应摘要", "Request ID"]
        )
        for index, mode in enumerate((
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.ResizeToContents,
            QHeaderView.ResizeMode.Stretch,
            QHeaderView.ResizeMode.ResizeToContents,
        )):
            self.interaction_table.horizontalHeader().setSectionResizeMode(index, mode)
        self.interaction_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.interaction_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        interactions_layout.addWidget(self.interaction_table, 1)
        interaction_detail_controls = QHBoxLayout()
        self.btn_interaction_detail = QPushButton("查看选中结果详情")
        self.btn_interaction_detail.clicked.connect(self._request_interaction_detail)
        interaction_detail_controls.addWidget(self.btn_interaction_detail)
        interaction_detail_controls.addStretch(1)
        interactions_layout.addLayout(interaction_detail_controls)
        self.interaction_detail = QPlainTextEdit()
        self.interaction_detail.setReadOnly(True)
        self.interaction_detail.setMaximumBlockCount(500)
        self.interaction_detail.setMaximumHeight(210)
        self.interaction_detail.setPlaceholderText("选中一条交互后查看校验结果、输入证据和内容哈希。")
        interactions_layout.addWidget(self.interaction_detail)
        self.content_tabs.addTab(interactions_page, "LLM 实时交互")
        layout.addWidget(self.content_tabs, 1)
        self.setStyleSheet("""
            QWidget {
                color: #e5e7eb;
                background-color: #17191f;
            }
            QTabWidget::pane {
                background-color: #17191f;
                border: 1px solid #353a45;
                top: -1px;
            }
            QTabBar::tab {
                color: #cbd5e1;
                background-color: #20232b;
                border: 1px solid #353a45;
                padding: 6px 9px;
                min-height: 22px;
            }
            QTabBar::tab:selected {
                color: #ffffff;
                background-color: #273244;
                border-bottom: 2px solid #60a5fa;
            }
            QTabBar::tab:hover:!disabled {
                background-color: #2a303b;
            }
            QTabBar::tab:disabled {
                color: #7b8492;
                background-color: #1b1e25;
                border-color: #303540;
            }
            QTableWidget, QPlainTextEdit, QLineEdit {
                color: #e5e7eb;
                background-color: #1d2028;
                border: 1px solid #353a45;
                selection-background-color: #315579;
                selection-color: #ffffff;
            }
            QTableWidget {
                alternate-background-color: #222630;
                gridline-color: #353a45;
            }
            QHeaderView::section {
                color: #cbd5e1;
                background-color: #242832;
                border: 1px solid #353a45;
                padding: 5px 7px;
                font-weight: bold;
            }
            QTableCornerButton::section {
                background-color: #242832;
                border: 1px solid #353a45;
            }
            QPushButton {
                color: #e5e7eb;
                background-color: #252a34;
                border: 1px solid #414653;
                border-radius: 3px;
                padding: 4px 9px;
            }
            QPushButton:hover:!disabled {
                background-color: #303a49;
                border-color: #5b8fc5;
            }
            QPushButton:disabled {
                color: #737b88;
                background-color: #20232b;
                border-color: #353a45;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background-color: #17191f;
                border: none;
                margin: 0;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background-color: #454c58;
                border-radius: 4px;
                min-width: 18px;
                min-height: 18px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                width: 0;
                height: 0;
            }
        """)

    def _select_console_tab(self, title: str) -> None:
        for index in range(self.content_tabs.count()):
            if self.content_tabs.tabText(index) == title:
                self.content_tabs.setCurrentIndex(index)
                return

    def _request_interaction_detail(self) -> None:
        row = self.interaction_table.currentRow()
        item = self.interaction_table.item(row, 5) if row >= 0 else None
        request_id = item.text().strip() if item is not None else ""
        if not request_id:
            self.interaction_detail.setPlainText("请先选择一条交互记录。")
            return
        self._pending_interaction_detail_id = request_id
        self.interaction_detail.setPlainText("正在读取已保存的校验结果…")
        if not self._worker.request_interaction_detail(request_id):
            self.interaction_detail.setPlainText("详情读取队列繁忙，请稍后重试。")

    def _show_interaction_detail(self, request_id: str, detail: str) -> None:
        if request_id == self._pending_interaction_detail_id:
            self.interaction_detail.setPlainText(detail)

    def _render_snapshot(self, snapshot: Dict[str, Any]) -> None:
        status = snapshot.get("runtime_status", "未知")
        simulation_only = snapshot.get("simulation_only") is True
        refreshed_at = snapshot.get("monitor_updated_at", "未知")
        gate_sync = snapshot.get("gate_context_sync", {})
        gate_sync = gate_sync if isinstance(gate_sync, dict) else {}
        gate_sync_state = gate_sync.get("state", "NOT_RUNNING")
        self.lbl_monitor_updated_at.setText(
            f"监控刷新：{refreshed_at} · ATS数据同步：{gate_sync_state}"
        )
        sync_age = gate_sync.get("heartbeat_age_seconds")
        sync_age_text = f"心跳 {sync_age:.1f}s" if isinstance(sync_age, (int, float)) else "无新鲜心跳"
        context_readiness = gate_sync.get("latest_context_readiness", {})
        context_readiness = context_readiness if isinstance(context_readiness, dict) else {}
        self.lbl_monitor_updated_at.setToolTip(
            "ATS只读桥接：{transport} · {age} · 观测 {count} 条 · 最近刷新 {updated} · "
            "PreHeat {preheat} · Live Heat {live_heat} · 锚点 {anchors} · VWAP快照 {vwap} · "
            "未就绪字段 {unready}/{missing} · PreHeat原因 {preheat_reason} · LiveHeat原因 {reason} · "
            "Gate 类型化上下文 {typed} · 运行授权 {authorized} · {error}".format(
                transport=gate_sync.get("transport", "未知"),
                age=sync_age_text,
                count=gate_sync.get("stored_observation_count", 0),
                updated=gate_sync.get("updated_at", "未知"),
                preheat=_safe_text(context_readiness.get("preheat_state"), 16) or "未评估",
                live_heat=_safe_text(context_readiness.get("live_heat_state"), 16) or "未评估",
                anchors=_safe_text(context_readiness.get("listing_anchors_state"), 16) or "未评估",
                vwap=_safe_text(context_readiness.get("vwap_state"), 16) or "未评估",
                unready=_nonnegative_count(context_readiness.get("unready_field_count")),
                missing=_nonnegative_count(context_readiness.get("missing_required_field_count")),
                preheat_reason=_safe_text(context_readiness.get("preheat_reason"), 80) or "无",
                reason=_safe_text(context_readiness.get("live_heat_reason"), 100) or "实时热度无阻断原因",
                typed="就绪" if gate_sync.get("typed_gate_contexts_ready") else "未就绪",
                authorized="通过" if gate_sync.get("runtime_authorized") else "关闭",
                error=gate_sync.get("refresh_error", ""),
            )
        )
        self.lbl_runtime.setText(f"仿真 LLM：{status}" if simulation_only else f"LLM 旁路：{status}")
        self.lbl_runtime.setStyleSheet(
            "font-weight: bold; padding: 6px; background: #20232b; border: 1px solid #414653; color: "
            + ("#ff7070" if "未就绪" in status or "未通过准入" in status else "#65d98a") + ";"
        )
        preflight = snapshot.get("provider_preflight", {})
        provider_name = preflight.get("backend") or snapshot.get("provider", "未配置")
        provider_state = preflight.get("state", "未就绪")
        self.lbl_provider.setText(
            f"仿真 Provider：{provider_name} · {snapshot.get('simulation_result', '未运行')} · 实盘关闭"
            if simulation_only else f"Provider：{provider_name} · {provider_state} · 旁路关闭"
        )
        worker = snapshot.get("worker_monitor", {})
        worker = worker if isinstance(worker, dict) else {}
        heartbeat_age = worker.get("heartbeat_age_seconds")
        heartbeat_text = (
            f"心跳 {heartbeat_age:.1f}s" if worker.get("heartbeat_healthy")
            and isinstance(heartbeat_age, (int, float)) else "无有效心跳"
        )
        worker_freshness = "状态新鲜" if snapshot.get("runtime_age") is not None else "状态过期/未启动"
        self.lbl_worker.setText(
            "Worker：{state} · {heartbeat} · 队列 {queued} · 在途 {inflight} · {freshness}".format(
                state=worker.get("state", "未启动"), heartbeat=heartbeat_text,
                queued=worker.get("queued_count", 0),
                inflight=worker.get("inflight_scope_count", 0),
                freshness=worker_freshness,
            )
        )
        self.lbl_worker.setToolTip(worker.get("last_error", "Worker 健康状态由独立控制线程发布"))
        self.lbl_learning.setText(f"自学习：{snapshot.get('learning_status', '未知')}")
        interaction = snapshot.get("interaction_summary", {})
        interaction = interaction if isinstance(interaction, dict) else {}
        recent_results = interaction.get("recent_results", [])
        recent_results = recent_results if isinstance(recent_results, list) else []
        agent_counts = {"MARKET_REGIME": 0, "CASE_RETRIEVAL": 0, "POST_CLOSE_REVIEW": 0}
        for record in recent_results[-100:]:
            if isinstance(record, dict) and record.get("agent_type") in agent_counts:
                agent_counts[record["agent_type"]] += 1
        journal = interaction.get("journal", {})
        journal = journal if isinstance(journal, dict) else {}
        request_producer = interaction.get("request_producer", {})
        request_producer = request_producer if isinstance(request_producer, dict) else {}
        self.lbl_interaction_summary.setText(
            "交互状态：{runtime} · 请求源 {producer}（生成 {generated} / 新鲜度跳过 {stale} / 校验拒绝 {rejected}）"
            " · {producer_reason}"
            " · 提交 {submitted} · 成功 {ok} · 失败 {failed} · 最近档案 {count} 条"
            " · 最近 Agent：市场 {market} / 案例 {cases} / 盘后复盘 {reviews}"
            " · 写入队列 {queued} / 丢弃 {dropped} / 失败 {write_failed}".format(
                runtime="准入通过" if snapshot.get("runtime_qualified") is True else "旁路未通过准入",
                producer=request_producer.get("state", "未知"),
                producer_reason=request_producer.get("reason", "请求生产端状态尚未发布"),
                generated=request_producer.get("generated", 0),
                stale=request_producer.get("skipped_stale", 0),
                rejected=request_producer.get("rejected", 0),
                submitted=interaction.get("submitted_requests", 0),
                ok=interaction.get("ok_results", 0),
                failed=interaction.get("failed_results", 0),
                count=len(recent_results),
                market=agent_counts["MARKET_REGIME"],
                cases=agent_counts["CASE_RETRIEVAL"],
                reviews=agent_counts["POST_CLOSE_REVIEW"],
                queued=journal.get("queued", 0),
                dropped=journal.get("dropped", 0),
                write_failed=journal.get("failed", 0),
            )
        )
        self.lbl_interaction_summary.setToolTip(
            html.escape(
                "请求源：{reason}；交互档案：{journal_error}".format(
                    reason=request_producer.get("reason", "请求生产端状态尚未发布"),
                    journal_error=journal.get("last_error", "无写入错误"),
                ), quote=True,
            )
        )
        self.interaction_table.setRowCount(len(recent_results))
        for row, record in enumerate(reversed(recent_results)):
            values = (
                record.get("completed_at", ""), record.get("ticker", ""),
                record.get("agent_type", ""), record.get("status", ""),
                record.get("summary", ""), record.get("request_id", ""),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 3:
                    item.setForeground(QColor(
                        "#65d98a" if item.text() == "OK"
                        else "#ff7070" if item.text() in {"INVALID", "UNAVAILABLE"}
                        else "#f0c674"
                    ))
                elif col == 4:
                    item.setToolTip(
                        "{summary}\n模型：{model}\n提示版本：{prompt}\n结果 SHA-256：{digest}".format(
                            summary=item.text(), model=record.get("model_id", ""),
                            prompt=record.get("prompt_version", ""),
                            digest=record.get("result_sha256", ""),
                        )
                    )
                self.interaction_table.setItem(row, col, item)
        learning_progress = snapshot.get("learning_progress", {})
        if isinstance(learning_progress, dict):
            last_result = interaction.get("last_result", {})
            if isinstance(last_result, dict) and last_result:
                last_result_text = " · ".join(
                    str(last_result.get(key, ""))
                    for key in ("ticker", "agent_type", "status") if last_result.get(key)
                ) or "已收到结果"
            else:
                last_result_text = "暂无结果"
            self.lbl_learning_progress.setText(
                "学习链（每 2 秒刷新）：完整输入快照 {snapshots} · 待 D1-D3 标签 {waiting} · 最近捕获 {snapshot_at} · "
                "存储 {storage} · 写入队列 {queued} / 丢弃 {dropped} · 写入失败 {writer_failed} | "
                "近期可复核 {pending} · 已接受 {accepted} · 已拒绝 {rejected} | "
                "数据集 {dataset} · 事件组 {groups} · 最近封存 {sealed_at} | "
                "回放 {cutoffs} 时点 / {unready} 未就绪 · 哈希 {replay_hash} · "
                "效果指标 {effect_metrics} · "
                "训练 {training} · 影子 {shadow} · 晋级 {promotion}\n"
                "LLM 交互：提交 {submitted} · 成功 {ok} · 失败 {failed} · 合并 {coalesced} · "
                "过期 {expired} · 旧时点 {stale} · 丢弃 {drops} · 最近 {last_result}".format(
                    snapshots=learning_progress.get("decision_snapshot_count", 0),
                    waiting=learning_progress.get("waiting_outcome_count", 0),
                    snapshot_at=_safe_text(learning_progress.get("latest_snapshot_at"), 32) or "无",
                    storage=learning_progress.get("snapshot_storage_status", "未知"),
                    queued=learning_progress.get("snapshot_writer_queued", 0),
                    dropped=learning_progress.get("snapshot_writer_dropped", 0),
                    writer_failed=learning_progress.get("snapshot_writer_failed", 0),
                    pending=learning_progress.get("pending_reviews", 0),
                    accepted=learning_progress.get("accepted_reviews", 0),
                    rejected=learning_progress.get("rejected_reviews", 0),
                    dataset=learning_progress.get("dataset_status", "未知"),
                    groups=learning_progress.get("sealed_event_group_count", 0),
                    sealed_at=_safe_text(learning_progress.get("latest_sealed_at"), 32) or "无",
                    cutoffs=learning_progress.get("replay_cutoff_count", 0),
                    unready=learning_progress.get("replay_unready_cutoff_count", 0),
                    replay_hash=_safe_text(learning_progress.get("replay_report_hash"), 10) or "无",
                    effect_metrics=learning_progress.get("effect_metric_status", "未评估"),
                    training=learning_progress.get("training_status", "未知"),
                    shadow=learning_progress.get("shadow_status", "未知"),
                    promotion=learning_progress.get("promotion_status", "未知"),
                    submitted=interaction.get("submitted_requests", 0),
                    ok=interaction.get("ok_results", 0),
                    failed=interaction.get("failed_results", 0),
                    coalesced=interaction.get("coalesced_requests", 0),
                    expired=interaction.get("expired_requests", 0),
                    stale=interaction.get("stale_requests", 0),
                    drops=(interaction.get("command_drops", 0) + worker.get("dropped_results", 0)),
                    last_result=last_result_text,
                )
            )
            self.lbl_learning_progress.setToolTip(
                _safe_text(learning_progress.get("snapshot_writer_last_error"), 180)
                or "快照写入器无记录错误"
            )
        market = snapshot.get("market_snapshot", {})
        if market:
            generated_at = market.get("generated_at")
            age = time.time() - generated_at if isinstance(generated_at, (int, float)) and not isinstance(generated_at, bool) and math.isfinite(generated_at) else None
            freshness = f"快照 {age:.1f}s" if age is not None and 0 <= age <= 60 else "快照过期/时点未知"
            confidence = market.get("tide_confidence")
            confidence_label = _number_label(
                confidence * 100 if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None,
                suffix="%",
            )
            self.lbl_market_hud.setText(
                "IPO 市场 HUD：{tide} · {action} · 潮汐置信度 {confidence} · 仓位上限 {cap} | "
                "指数 {index_phase} · 成交 {amount}亿 / 量比 {volume_ratio} · "
                "新股热度 {heat_stage}/{heat_score} · 监控 {count} 只 · 红盘 {red} · 站 VWAP {vwap} · "
                "平均涨跌 {change} · 涨幅≥5% {surge} 只 | "
                "风险 {risk} / 数据 {quality} · {freshness} · snapshot {snapshot_id}".format(
                    tide=_safe_text(market.get("tide_state"), 40) or "未知",
                    action=_safe_text(market.get("tide_action"), 24) or "未知",
                    confidence=confidence_label,
                    cap=_number_label(market.get("tide_position_cap_pct"), suffix="%"),
                    index_phase=_safe_text(market.get("index_phase"), 32) or "指数未知",
                    amount=_number_label(market.get("sh_amount_yi")),
                    volume_ratio=_number_label(market.get("sh_volume_ratio")),
                    heat_stage=_safe_text(market.get("heat_stage"), 40) or "未知",
                    heat_score=_number_label(market.get("heat_score")),
                    count=_safe_text(market.get("ipo_count"), 12) or "--",
                    red=_number_label(market.get("red_ratio"), suffix="%"),
                    vwap=_number_label(market.get("vwap_hold_ratio"), suffix="%"),
                    change=_number_label(market.get("avg_change_pct"), suffix="%"),
                    surge=_safe_text(market.get("surge_count"), 12) or "--",
                    risk=_safe_text(market.get("risk_mode"), 24) or "未知",
                    quality=_safe_text(market.get("data_quality"), 24) or "未知",
                    freshness=freshness,
                    snapshot_id=_safe_text(market.get("snapshot_id"), 16) or "--",
                )
            )
        else:
            self.lbl_market_hud.setText("IPO 市场 HUD：暂无交易中心情绪快照（该状态不构成交易准入）。")
        gate_summary = snapshot.get("gate_summary", {})
        context_status = gate_summary.get("context_status", "TRADING_CENTER_NOT_STARTED")
        context_label = {
            "TRADING_CENTER_NOT_STARTED": "交易中心未启动",
            "PROVIDER_UNCONFIGURED": "上下文接口未挂接",
            "PROVIDER_CONFIGURED": "上下文接口已挂接（仍需 Gate 校验）",
            "READ_BUSY": "交易中心读取繁忙",
            "READ_ERROR": "交易中心状态读取失败",
        }.get(context_status, "状态未知")
        self.lbl_gate_summary.setText(
            "R9：{context} · 接口#{generation} · 授权记录 {authorizations} · 近况 ENTRY/WATCH/BLOCK {entry}/{watch}/{block} · 活动阻断/ENTRY {active_block}/{active_entry} · 告警 {alerts}".format(
                context=context_label,
                generation=gate_summary.get("context_generation") if gate_summary.get("context_generation") is not None else "未采样",
                authorizations=gate_summary.get("authorization_records") if gate_summary.get("authorization_records") is not None else "未采样",
                recent=gate_summary.get("recent", 0), entry=gate_summary.get("entry", 0),
                watch=gate_summary.get("watch", 0), block=gate_summary.get("block", 0),
                active_block=gate_summary.get("active_block", 0),
                active_entry=gate_summary.get("active_entry", 0),
                alerts=gate_summary.get("regime_carry_alerts", 0),
            )
        )
        gate_alerts = snapshot.get("gate_alerts", [])
        if gate_alerts:
            alert_text = "；".join(
                f"{_safe_text(item.get('ticker'), 16)} {_safe_text(item.get('message'), 100)}"
                for item in gate_alerts[:3] if isinstance(item, dict)
            )
            self.lbl_gate_alerts.setText(f"近期 Regime / Carry 状态变化（最多显示 3 条）：{alert_text}")
        else:
            self.lbl_gate_alerts.setText("Regime / Carry 状态变化：尚无可用的连续有效快照。")
        self._render_gate_diagnostics(snapshot.get("gate_diagnostics", []))
        operation_states = snapshot.get("operation_states", [])
        state_counts = {}
        self.operation_table.setRowCount(len(operation_states))
        for row, record in enumerate(operation_states):
            history = record.get("history", []) if isinstance(record, dict) else []
            latest = history[-1] if history and isinstance(history[-1], dict) else {}
            from_state = latest.get("from_state", "")
            to_state = latest.get("to_state", "")
            transition = f"{from_state} → {to_state}" if from_state and to_state else "--"
            version = latest.get("snapshot_version", "")
            state = str(record.get("state", ""))
            state_counts[state] = state_counts.get(state, 0) + 1
            facts = latest.get("facts", {}) if isinstance(latest, dict) else {}
            tooltip = json.dumps(
                {"snapshot_version": version, "facts": facts},
                ensure_ascii=False, sort_keys=True, default=str,
            )
            values = (
                record.get("code", ""), state, transition,
                latest.get("as_of_time", ""), latest.get("transition_reason", ""),
                f"{record.get('history_count', len(history))} 次 · {version}" if history else "0 次",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(tooltip)
                if col == 1:
                    color = (
                        "#65d98a" if state in {"ENTRY_READY", "ENTERED", "EXIT_READY"}
                        else "#f0c674" if state in {"ARMED", "HOLD_T1"}
                        else "#ff7070" if state == "BLOCKED" else "#e5e7eb"
                    )
                    item.setForeground(QColor(color))
                self.operation_table.setItem(row, col, item)
        state_text = " · ".join(
            f"{name} {count}" for name, count in sorted(state_counts.items())
        )
        self.lbl_operation_summary.setText(
            f"操作状态机：{len(operation_states)} 个标的"
            + (f" · {state_text}" if state_text else " · 暂无已确认迁移")
        )
        self.lbl_rule.setText(f"规则路径：{snapshot.get('rule_path', '')}；配置：{snapshot.get('config_status', '')}（{snapshot.get('config_detail', '')}）")

        checks = preflight.get("checks", [])
        self.provider_table.setRowCount(len(checks))
        for row, check in enumerate(checks):
            for col, key in enumerate(("name", "status", "detail")):
                item = QTableWidgetItem(str(check.get(key, "")))
                if col == 1:
                    color = "#65d98a" if item.text() == "通过" else "#f0c674" if item.text() in {"待验收", "未探测"} else "#ff7070"
                    item.setForeground(QColor(color))
                self.provider_table.setItem(row, col, item)

        stages = snapshot.get("stages", [])
        self.stage_table.setRowCount(len(stages))
        for row, stage in enumerate(stages):
            for col, key in enumerate(("stage", "status", "detail")):
                item = QTableWidgetItem(str(stage.get(key, "")))
                if key == "status":
                    item.setForeground(QColor("#65d98a" if item.text() == "已验收" else "#f0c674"))
                self.stage_table.setItem(row, col, item)

        replay_metrics = snapshot.get("replay_effect_metrics", {})
        self.replay_metrics_table.setRowCount(len(_REPLAY_METRICS))
        for row, (metric_name, label) in enumerate(_REPLAY_METRICS):
            metric = replay_metrics.get(metric_name, {}) if isinstance(replay_metrics, dict) else {}
            metric = metric if isinstance(metric, dict) else {}
            state = "已量化" if metric.get("status") == "MEASURED" else "不可评估"
            value = metric.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                formatted_value = (
                    f"{value * 100:.2f}%" if metric_name == "explanation_coverage"
                    else str(value) if metric_name == "future_leakage_count"
                    else _number_label(value, precision=4)
                )
            else:
                formatted_value = "--"
            reason = _safe_text(metric.get("reason"), 500) or "尚无已保存回放报告"
            values = (label, state, formatted_value, reason)
            for col, cell in enumerate(values):
                item = QTableWidgetItem(str(cell))
                if col == 1:
                    item.setForeground(QColor("#65d98a" if state == "已量化" else "#f0c674"))
                self.replay_metrics_table.setItem(row, col, item)

        contracts = snapshot.get("contracts", [])
        contract_counts = snapshot.get("contract_status_counts", {})
        contract_counts = contract_counts if isinstance(contract_counts, dict) else {}
        required = _nonnegative_count(contract_counts.get("required"))
        configured = _nonnegative_count(contract_counts.get("configured"))
        fresh = _nonnegative_count(contract_counts.get("fresh"))
        confirmed_missing = _nonnegative_count(contract_counts.get("confirmed_missing"))
        unobserved = _nonnegative_count(contract_counts.get("unobserved"))
        uncontracted = _nonnegative_count(contract_counts.get("uncontracted"))
        blocked_or_invalid = _nonnegative_count(contract_counts.get("blocked_or_invalid"))
        if required:
            progress = f"当前实时新鲜 {fresh}/{required} 项。"
            next_step = (
                "先处理数据页各行的‘自检与下一步’，再看 Gate 诊断。"
                if fresh < required else "继续查看 Gate 诊断；字段新鲜不代表交易准入通过。"
            )
        else:
            progress = "当前尚未读取到必需字段契约。"
            next_step = "先到数据与采集页查看配置与采集结果。"
        self.lbl_operator_guide.setText(
            f"{progress}{next_step}\n"
            "流程：数据/TTL → Gate 阻断原因 → 盘后 D1-D3 → 人工复核 → 回放指标。"
            "启动约 2.5 秒后自动采集默认标的 301689，之后每 30 分钟重试。"
            "运行入口：python tools/run_ipo_learning_console.py；LLM 与交易授权仍关闭。"
        )
        self.lbl_contract_status.setText(
            f"来源契约 {configured}/{required} 项；实时新鲜 {fresh} 项；"
            f"契约确认缺失 {confirmed_missing} 项；未接观测 {unobserved} 项；"
            f"缺契约 {uncontracted} 项；过期/无效/来源不匹配 {blocked_or_invalid} 项。"
            "任一必需输入未满足门禁要求时，R9 保持阻断。"
        )
        self.contract_table.setRowCount(len(contracts))
        for row, contract in enumerate(contracts):
            values = (
                contract.get("field_id", ""), contract.get("ticker", "--"),
                contract.get("value", "--"),
                contract.get("source", ""), contract.get("timezone", ""),
                contract.get("ttl", ""), contract.get("unit", ""),
                contract.get("window", ""), contract.get("missing_policy", ""),
                contract.get("as_of_time", ""), contract.get("available_at", ""),
                contract.get("status", ""), contract.get("acquisition_route", ""),
                contract.get("next_action", ""),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 11:
                    text = item.text()
                    color = (
                        "#65d98a" if text.startswith("新鲜") else
                        "#f0c674" if text.startswith("确认缺失") else
                        "#9298a7" if text in {"未接入实时观测", "缺少来源/时效契约"} else
                        "#ff7070"
                    )
                    item.setForeground(QColor(color))
                self.contract_table.setItem(row, col, item)

        source_health = snapshot.get("source_health", [])
        self.source_health_table.setRowCount(len(source_health))
        for row, source in enumerate(source_health):
            values = tuple(source.get(key, "") for key in (
                "source", "status", "cached", "latest", "detail",
            ))
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 1:
                    state = item.text()
                    item.setForeground(QColor(
                        "#65d98a" if state in {"已连接", "有缓存"}
                        else "#9298a7" if state == "未启动" else "#ff7070"
                    ))
                self.source_health_table.setItem(row, col, item)

        self._render_learning_snapshots(snapshot.get("decision_snapshots", []))
        self._render_outcome_labels(snapshot.get("outcome_labels", []))

        events = snapshot.get("events", [])
        selected = self._selected_event or {}
        selected_fields = ("candidate_id", "request_id", "timestamp", "event", "ticker")
        selected_key = tuple(selected.get(key, "") for key in selected_fields)
        scroll_value = self.event_table.verticalScrollBar().value()
        self.event_table.blockSignals(True)
        self.event_table.setRowCount(len(events))
        for row, event in enumerate(events):
            for col, key in enumerate(("timestamp", "stage", "event", "status", "ticker", "gate", "message")):
                value = "已复核" if key == "status" and event.get("reviewed") == "true" else event.get(key, "")
                item = QTableWidgetItem(value)
                if key == "status":
                    item.setForeground(QColor(
                        "#65d98a" if value == "ENTRY" else "#f0c674" if value == "WATCH" else "#ff7070" if value == "BLOCK" else "#e5e7eb"
                    ))
                item.setData(Qt.ItemDataRole.UserRole, event)
                self.event_table.setItem(row, col, item)
        selected_row = None
        if any(selected_key):
            for row, event in enumerate(events):
                if tuple(event.get(key, "") for key in selected_fields) == selected_key:
                    selected_row = row
                    break
        if selected_row is not None:
            self.event_table.selectRow(selected_row)
            self.event_table.setCurrentCell(selected_row, 0)
        else:
            self.event_table.clearSelection()
        self.event_table.verticalScrollBar().setValue(scroll_value)
        self.event_table.blockSignals(False)
        self._show_selected_event()

    def _render_learning_snapshots(self, records: Any) -> None:
        records = records if isinstance(records, list) else []
        self.snapshot_table.blockSignals(True)
        self.snapshot_table.setRowCount(len(records))
        selected_row = None
        for row, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            values = (
                record.get("cutoff", ""),
                record.get("ticker", ""),
                record.get("decision", ""),
                str(record.get("snapshot_hash", ""))[:16],
                "待 D1-D3 结果标签" if record.get("label_status") == "WAITING_OUTCOME" else record.get("label_status", ""),
                record.get("event_id", ""),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(_safe_text(value, 180))
                item.setData(Qt.ItemDataRole.UserRole, record)
                if col == 2:
                    item.setForeground(QColor(
                        "#65d98a" if value == "ENTRY" else "#f0c674" if value == "WATCH" else "#ff7070"
                    ))
                self.snapshot_table.setItem(row, col, item)
            if record.get("snapshot_id") == self._selected_snapshot_id:
                selected_row = row
        self.snapshot_table.blockSignals(False)
        if selected_row is None and records:
            selected_row = 0
        if selected_row is not None:
            self.snapshot_table.selectRow(selected_row)
            self._show_selected_snapshot()
        else:
            self._selected_snapshot_id = ""
            self.snapshot_detail.clear()

    def _render_outcome_labels(self, records: Any) -> None:
        values = records if isinstance(records, list) else []
        selected_items = self.outcome_table.selectedItems()
        selected_record = selected_items[0].data(Qt.ItemDataRole.UserRole) if selected_items else None
        selected_id = selected_record.get("evidence_id") if isinstance(selected_record, dict) else ""
        self.outcome_table.setRowCount(len(values))
        columns = ("ticker", "listing_date", "d1", "d2", "d3", "drawdown", "issue_break", "anchor_break", "matured_at", "review")
        for row, record in enumerate(values):
            if not isinstance(record, dict):
                continue
            for col, key in enumerate(columns):
                item = QTableWidgetItem(str(record.get(key, "")))
                if key == "review":
                    item.setForeground(QColor("#f0c674"))
                if key == "anchor_break" and item.text() == "未就绪":
                    item.setForeground(QColor("#9298a7"))
                item.setToolTip(str(record.get("evidence_id", "")))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record)
                self.outcome_table.setItem(row, col, item)
        if values:
            selected_row = next((
                row for row, record in enumerate(values)
                if isinstance(record, dict) and record.get("evidence_id") == selected_id
            ), 0)
            self.outcome_table.selectRow(selected_row)
        else:
            self.btn_accept_outcome.setEnabled(False)
            self.btn_reject_outcome.setEnabled(False)

    def _show_selected_outcome(self) -> None:
        selected = self.outcome_table.selectedItems()
        record = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        can_review = bool(
            isinstance(record, dict)
            and record.get("review") == "待人工复核"
            and record.get("evidence_id") not in self._outcome_review_pending_ids
        )
        self.btn_accept_outcome.setEnabled(can_review)
        self.btn_reject_outcome.setEnabled(can_review)

    def _review_outcome_label(self, decision: str) -> None:
        selected = self.outcome_table.selectedItems()
        record = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        if not isinstance(record, dict) or record.get("review") != "待人工复核":
            QMessageBox.warning(self, "不能复核", "请选择一条待人工复核的成熟标签证据。")
            return
        reviewer, accepted = QInputDialog.getText(self, "D1-D3 标签复核", "复核人：")
        if not accepted or not reviewer.strip():
            return
        reason, accepted = QInputDialog.getMultiLineText(
            self, "D1-D3 标签复核理由", "填写确认/拒绝理由："
        )
        if not accepted or not reason.strip():
            return
        if not self._worker.submit_outcome_review(record, decision, reviewer.strip(), reason.strip()):
            QMessageBox.warning(self, "无法提交", "复核队列繁忙或证据已失效。")
            return
        self._outcome_review_pending_ids.add(record["evidence_id"])
        self._show_selected_outcome()

    def _outcome_review_completed(self, evidence_id: str, saved: bool, detail: str) -> None:
        self._outcome_review_pending_ids.discard(evidence_id)
        self._worker.request_refresh()
        if saved:
            QMessageBox.information(self, "复核已保存", detail)
        else:
            QMessageBox.warning(self, "复核未保存", detail)
        self._show_selected_outcome()

    def _collect_supported_source(self) -> None:
        self._start_source_collection(collect_labels=False)

    def _collect_matured_labels(self) -> None:
        self._start_source_collection(collect_labels=True)

    def _on_source_auto_tick(self) -> None:
        market_active = _is_market_session_active()
        interval_ms = 5 * 60 * 1000 if market_active else 60 * 1000
        if self._source_auto_timer.interval() != interval_ms:
            self._source_auto_timer.setInterval(interval_ms)
        if market_active:
            self._start_source_collection(collect_labels=True)

    def _start_source_collection(self, collect_labels: bool) -> None:
        if self._simulation_read_only:
            return
        if self._source_worker is not None and self._source_worker.isRunning():
            return
        ticker = self.edt_acquisition_code.text().strip()
        if len(ticker) != 6 or not ticker.isdigit():
            self.lbl_acquisition_status.setText("请输入六位数字股票代码。")
            return
        self.btn_collect_issue_price.setEnabled(False)
        self.btn_collect_labels.setEnabled(False)
        suffix = "并扫描成熟标签" if collect_labels else ""
        self.lbl_acquisition_status.setText(f"正在后台采集 {ticker}：发行/供给、个股行情、两融日数据、涨停/炸板池、TDX历史与全市场快照{suffix}，并执行 41 项来源/时区/TTL 自检…")
        self._source_worker = _SourceAcquisitionWorker(self._root, ticker, collect_labels, self)
        self._source_worker.completed.connect(self._source_collection_completed)
        self._source_worker.finished.connect(lambda: (
            self.btn_collect_issue_price.setEnabled(True), self.btn_collect_labels.setEnabled(True)
        ))
        self._source_worker.start()

    def _source_collection_completed(self, result: Dict[str, Any]) -> None:
        state = str(result.get("status", "UNREADY"))
        count = _nonnegative_count(result.get("ready_count"))
        required = _nonnegative_count(result.get("required_count"))
        parts = []
        for key, label in (
            ("acquisition", "发行日历"), ("ipo_facts", "IPO先验"),
            ("listing_anchors", "首日锚点"),
            ("listing_supply", "上市供给"), ("market", "A股横截面"),
            ("live", "个股行情"), ("market_history", "TDX历史"),
            ("market_snapshot", "TDX全市场快照"),
            ("limit_up_pool", "涨停/炸板池"),
            ("financing", "两融日数据"),
            ("market_pulse", "本地脉冲"),
        ):
            component = result.get(key)
            if isinstance(component, dict):
                fields = component.get("saved_fields", [])
                saved_count = len(fields) if isinstance(fields, list) else _nonnegative_count(component.get("saved_count"))
                parts.append(f"{label}{saved_count}项/{component.get('status', 'UNREADY')}")
                component_reason = _safe_text(component.get("reason"), 120)
                if component_reason:
                    parts.append(f"{label}诊断:{component_reason}")
        bridge = result.get("gate_data_bridge", {})
        if isinstance(bridge, dict):
            bridge_state = bridge.get("reader_state", "NOT_RUNNING")
            bridge_age = bridge.get("reader_age_seconds")
            age_text = f"{bridge_age:.0f}s" if isinstance(bridge_age, (int, float)) else "无心跳"
            parts.append(f"ATS只读同步{bridge_state}/{age_text}；类型化门禁上下文未就绪")
        label_reports = result.get("label_reports", [])
        if isinstance(label_reports, list) and label_reports:
            label_rows = [
                report for report in label_reports
                if isinstance(report, dict)
                and report.get("status") not in {"COHORT_SCAN_COMPLETE", "COHORT_RETRY_LATER"}
            ]
            matured = sum(
                report.get("status") == "MATURED_PENDING_REVIEW"
                for report in label_rows
            )
            cohort = next((report for report in label_reports
                           if isinstance(report, dict)
                           and report.get("status") in {"COHORT_SCAN_COMPLETE", "COHORT_RETRY_LATER"}), None)
            if cohort:
                selected = _nonnegative_count(cohort.get("selected"))
                candidates = _nonnegative_count(cohort.get("calendar_candidates"))
                parts.append(f"标签新增{matured}条待复核；近期队列{selected}/{candidates}")
            else:
                parts.append(f"标签{matured}条待复核/{len(label_rows)}条扫描")
            label_reason = _safe_text(next((item.get("reason") for item in label_reports
                if isinstance(item, dict) and item.get("reason")), ""), 100)
            if label_reason:
                parts.append(f"标签诊断:{label_reason}")
        reason = _safe_text(result.get("reason"), 180)
        self.lbl_acquisition_status.setText(
            f"{state} · 全局契约 {count}/{required} 就绪 · " + " / ".join(parts)
            + (f" · {reason}" if reason else "")
        )
        self._worker.request_refresh()

    def _show_selected_snapshot(self) -> None:
        selected = self.snapshot_table.selectedItems()
        record = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        if not isinstance(record, dict):
            self.btn_snapshot_note.setEnabled(False)
            self.snapshot_detail.clear()
            return
        snapshot_id = record.get("snapshot_id", "")
        if not isinstance(snapshot_id, str):
            self.snapshot_detail.clear()
            return
        self._selected_snapshot_id = snapshot_id
        self.btn_snapshot_note.setEnabled(bool(snapshot_id))
        try:
            from ats.llm.learning_snapshot_store import get_snapshot_record

            detail = get_snapshot_record(self._root, snapshot_id)
        except Exception:
            detail = None
        if not isinstance(detail, dict):
            self.snapshot_detail.setPlainText("所选快照暂不可读取；存储仍保持只读监控状态。")
            return
        input_snapshot = detail.get("input_snapshot", {})
        features = input_snapshot.get("features", {}) if isinstance(input_snapshot, dict) else {}
        lines = [
            f"标的 / 事件：{detail.get('ticker', '')} / {detail.get('event_id', '')}",
            f"决策截点：{detail.get('cutoff', '')} · 捕获：{detail.get('captured_at', '')}",
            f"Gate：{detail.get('decision', '')} · 标签：{detail.get('label_status', '')}",
            f"输入快照 SHA-256：{detail.get('snapshot_hash', '')}",
            f"决策配置：{detail.get('configuration_version', '') or '旧记录未保存版本'} / {detail.get('configuration_hash', '')}",
            f"数据契约哈希：{detail.get('data_contract_hash', '')}",
            f"规则 Proposal 时间：{detail.get('proposal_created_at', '') or '旧记录未保存'}",
            "规则 Proposal：" + json.dumps(
                detail.get("standard_proposal", {}), ensure_ascii=False,
                sort_keys=True, separators=(",", ":"),
            )[:4000],
            "Gate 因果链：" + "；".join(
                _safe_text(item, 300) for item in detail.get("gate_causal_chain", [])
                if isinstance(item, str)
            ),
            "",
            "字段 | 值 | 来源@版本 | 来源时区 | as_of | available_at",
        ]
        if isinstance(features, dict):
            for field_id, feature in sorted(features.items()):
                if not isinstance(feature, dict):
                    continue
                try:
                    value_text = json.dumps(
                        feature.get("value"), ensure_ascii=False, separators=(",", ":"),
                        allow_nan=False,
                    )[:180]
                except (TypeError, ValueError, OverflowError):
                    value_text = "<不可序列化>"
                lines.append(
                    f"{_safe_text(field_id, 100)} | {value_text} | "
                    f"{_safe_text(feature.get('source_id'), 100)}@{_safe_text(feature.get('source_version'), 80)} | "
                    f"{_safe_text(feature.get('source_timezone'), 80)} | "
                    f"{_safe_text(feature.get('as_of_time'), 40)} | "
                    f"{_safe_text(feature.get('available_at'), 40)}"
                )
        self.snapshot_detail.setPlainText("\n".join(lines))

    def _add_snapshot_note(self) -> None:
        selected = self.snapshot_table.selectedItems()
        record = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        if not isinstance(record, dict):
            return
        note, accepted = QInputDialog.getText(self, "记录快照备注", "备注（写入学习审计，不会生成训练标签）：")
        if not accepted or not note.strip():
            return
        queued = self._worker.submit_note(note, {
            "stage": "LEARNING_SNAPSHOT",
            "event": "INPUT_SNAPSHOT_NOTE",
            "request_id": record.get("snapshot_id", ""),
            "ticker": record.get("ticker", ""),
        })
        if queued:
            QMessageBox.information(self, "已排队", "快照备注已排入本地审计写入队列。")
        else:
            QMessageBox.warning(self, "未提交", "审计写入队列已满，请稍后重试。")

    def _render_gate_diagnostics(self, records: List[Dict[str, Any]]) -> None:
        selected = self.gate_diagnostic_table.selectedItems()
        selected_record = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        selected_code = selected_record.get("ticker") if isinstance(selected_record, dict) else ""
        self.gate_diagnostic_table.blockSignals(True)
        self.gate_diagnostic_table.setRowCount(len(records))
        for row, record in enumerate(records):
            detail = record.get("gate_detail", {}) if isinstance(record, dict) else {}
            detail = detail if isinstance(detail, dict) else {}
            groups = {
                key: detail.get(key, {}) if isinstance(detail.get(key), dict) else {}
                for key in ("lrrm", "regime", "preheat", "live_heat", "carry", "vwap", "risk")
            }
            gates = detail.get("gates", {}) if isinstance(detail.get("gates"), dict) else {}
            lrrm = groups["lrrm"]
            regime = groups["regime"]
            preheat = groups["preheat"]
            live_heat = groups["live_heat"]
            carry = groups["carry"]
            vwap = groups["vwap"]
            risk = groups["risk"]
            gate_status = " · ".join(
                f"G{index} {gates.get(f'gate_{index}', 'UNAVAILABLE')}"
                for index in range(6)
            )
            values = (
                _safe_text(record.get("ticker"), 16),
                _safe_text(record.get("as_of_time"), 40),
                _safe_text(record.get("decision"), 16) or "UNKNOWN",
                gate_status,
                _safe_text(regime.get("state"), 24) or _safe_text(regime.get("status"), 24) or "UNAVAILABLE",
                f"{_safe_text(preheat.get('preheat_tier'), 24) or _safe_text(preheat.get('status'), 24)} · {_number_label(preheat.get('preheat_score'))}",
                f"{_safe_text(live_heat.get('nonlinear_zone'), 24) or _safe_text(live_heat.get('status'), 24)} · {_number_label(live_heat.get('heat_score'))}",
                f"{_safe_text(carry.get('state'), 24) or _safe_text(carry.get('status'), 24)} · {_number_label(carry.get('score'))}",
                f"{_safe_text(vwap.get('status'), 24)} · {_safe_text(vwap.get('structure'), 24)}".strip(" ·"),
                _safe_text(risk.get("status"), 24) or "UNAVAILABLE",
                _safe_text(detail.get("next_condition"), 240) or "UNAVAILABLE",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record)
                if col == 2:
                    item.setForeground(QColor(
                        "#65d98a" if value == "ENTRY" else "#f0c674" if value == "WATCH" else "#ff7070"
                    ))
                self.gate_diagnostic_table.setItem(row, col, item)
        self.gate_diagnostic_table.blockSignals(False)
        if records:
            row_to_select = next(
                (index for index, record in enumerate(records) if record.get("ticker") == selected_code),
                0,
            )
            self.gate_diagnostic_table.selectRow(row_to_select)
            self._show_selected_gate_diagnostic()
        else:
            self.gate_diagnostic_detail.clear()

    def _show_selected_gate_diagnostic(self) -> None:
        selected = self.gate_diagnostic_table.selectedItems()
        record = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        if not isinstance(record, dict):
            self.gate_diagnostic_detail.clear()
            return
        detail = record.get("gate_detail", {})
        data_contract = detail.get("data_contract", {}) if isinstance(detail, dict) else {}
        unready_fields = data_contract.get("unready_fields", []) if isinstance(data_contract, dict) else []
        unready_names = [
            _safe_text(item.get("field_id"), 100)
            for item in unready_fields
            if isinstance(item, dict) and item.get("field_id")
        ] if isinstance(unready_fields, list) else []
        lines = [
            f"标的 / 时点：{record.get('ticker', '')} / {record.get('as_of_time', '')}",
            f"决策：{record.get('decision', '')}",
            f"配置：{record.get('configuration_version', '')} / {record.get('configuration_hash', '')}",
            f"数据契约哈希：{record.get('data_contract_hash', '') or detail.get('data_contract', {}).get('hash', '')}",
            f"六道 Gate：{json.dumps(detail.get('gates', {}), ensure_ascii=False, sort_keys=True)}",
            f"下一条件：{detail.get('next_condition', 'UNAVAILABLE')}",
            f"未就绪指标：{'、'.join(unready_names) or '无明细'}",
            f"正向因素：{'；'.join(detail.get('positive_factors', [])) or '无已记录因素'}",
            f"负向因素：{'；'.join(detail.get('negative_factors', [])) or '无已记录因素'}",
            f"数据契约：{json.dumps(detail.get('data_contract', {}), ensure_ascii=False, sort_keys=True)}",
            f"LRRM：{json.dumps(detail.get('lrrm', {}), ensure_ascii=False, sort_keys=True)}",
            f"Regime：{json.dumps(detail.get('regime', {}), ensure_ascii=False, sort_keys=True)}",
            f"PreHeat / LiveHeat：{json.dumps({'preheat': detail.get('preheat', {}), 'live_heat': detail.get('live_heat', {})}, ensure_ascii=False, sort_keys=True)}",
            f"Carry / VWAP / Risk：{json.dumps({'carry': detail.get('carry', {}), 'vwap': detail.get('vwap', {}), 'risk': detail.get('risk', {})}, ensure_ascii=False, sort_keys=True)}",
            f"首日锚点：{json.dumps(detail.get('anchors', {}), ensure_ascii=False, sort_keys=True)}",
            f"交易计划：{json.dumps(detail.get('trade_plan', {}), ensure_ascii=False, sort_keys=True)}",
            f"因果链：{'；'.join(record.get('causal_chain', [])) or 'UNAVAILABLE'}",
            f"操作状态：{json.dumps(record.get('operation_state', {}), ensure_ascii=False, sort_keys=True)}",
        ]
        self.gate_diagnostic_detail.setPlainText("\n".join(lines))

    def _show_selected_event(self) -> None:
        selected = self.event_table.selectedItems()
        self._selected_event = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        if self._selected_event:
            summary = "\n".join(f"{key}: {value}" for key, value in self._selected_event.items() if value)
            self.event_detail.setPlainText(summary)
        selected_candidate_id = (
            self._selected_event.get("candidate_id", "")
            if self._selected_event else ""
        )
        can_review = bool(
            self._selected_event
            and _reviewable(self._selected_event)
            and selected_candidate_id not in self._review_pending_candidate_ids
        )
        self.btn_accept.setEnabled(can_review)
        self.btn_reject.setEnabled(can_review)

    def _review_completed(self, candidate_id: str, saved: bool, detail: str) -> None:
        self._review_pending_candidate_ids.discard(candidate_id)
        self._worker.request_refresh()
        if saved:
            QMessageBox.information(self, "复核已保存", detail)
        else:
            QMessageBox.warning(self, "复核未保存", detail)
        self._show_selected_event()

    def _review_candidate(self, decision: str) -> None:
        event = self._selected_event
        if not event or not _reviewable(event):
            QMessageBox.warning(self, "不能复核", "候选缺少成熟标签、结果证据、有效时间、标的事件身份、快照/复核草稿哈希、模型/提示版本、配置/数据契约哈希或 Gate 因果链。")
            return
        reviewer, accepted = QInputDialog.getText(self, "样本复核", "复核人：")
        if not accepted or not reviewer.strip():
            return
        reason, accepted = QInputDialog.getMultiLineText(self, "样本复核理由", "填写接受/拒绝理由：")
        if not accepted or not reason.strip():
            return
        if not self._worker.submit_review(event, decision, reviewer.strip(), reason.strip()):
            QMessageBox.warning(self, "无法提交", "复核队列繁忙或候选已失效/已复核。")
            return
        self._review_pending_candidate_ids.add(event["candidate_id"])
        self._show_selected_event()

    def _open_gate_event_detail(self, row: int, _column: int = 0) -> None:
        row_item = self.event_table.item(row, 0)
        event = row_item.data(Qt.ItemDataRole.UserRole) if row_item else None
        if not event or event.get("stage") != "R9_GATE":
            return
        code = event.get("ticker", "")
        request_id = event.get("request_id", "")
        if not code:
            return
        try:
            from ats.strategy.ipo_trading_center import IPOTradingCenter
            trading_center = IPOTradingCenter._instance
            if trading_center is None:
                return
            with trading_center._lock:
                directive = next((
                    item for item in trading_center._pending_directives
                    if getattr(item, "directive_id", "") == request_id
                ), None)
                log_item = next((
                    item for item in trading_center._signal_iteration_log
                    if isinstance(item, dict) and item.get("directive_id") == request_id
                ), None)
                directive = copy.deepcopy(directive) if directive is not None else None
                log_item = copy.deepcopy(log_item) if log_item is not None else None
            from ats.ui.ipo_arbitration_detail_dialog import IPOArbitrationDetailDialog
            IPOArbitrationDetailDialog.show_or_update(
                code, directive_obj=directive,
                log_item=log_item if directive is None else None,
                parent=self,
            )
        except Exception:
            return

    def _add_note(self) -> None:
        if not self._selected_event:
            QMessageBox.information(self, "记录复核备注", "请先选择一条事件。")
            return
        note, accepted = QInputDialog.getMultiLineText(
            self, "记录复核备注", "备注将作为人工审计事件保存，不会直接改变样本标签、交易规则或模型："
        )
        if accepted and note.strip() and not self._worker.submit_note(note.strip(), self._selected_event):
            QMessageBox.warning(self, "事件队列繁忙", "备注队列已满，请稍后再试。")

    def stop_monitor(self, timeout_ms: int = 1500) -> None:
        if hasattr(self, "_source_auto_timer"):
            self._source_auto_timer.stop()
        control = self._runtime_control
        if control is not None and control.is_alive():
            control.stop()
            control.join(max(0, min(int(timeout_ms), 2500)) / 1000.0)
        if self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(timeout_ms)
        source_worker = self._source_worker
        if source_worker is not None and source_worker.isRunning():
            source_worker.wait(min(max(0, int(timeout_ms)), 3500))
