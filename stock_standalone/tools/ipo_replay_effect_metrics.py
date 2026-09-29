"""Versioned, post-decision metrics for cutoff replay and mature outcomes."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


EFFECT_METRIC_CONTRACT_VERSION = "r9.effect-metrics.v1"
EFFECT_METRIC_DEFINITIONS = {
    "regime_transition_accuracy": "predicted_next_regime_state equals mature next_regime_state",
    "high_carry_vs_low_carry_spread": "mean D1 return where T1 Carry score >=70 minus mean where score <=30",
    "bad_t1_filter_rate": "mature bad_t1 cases whose final decision is not ENTRY / all mature bad_t1 cases",
    "continuation_capture_rate": "ENTRY decisions among mature continuation cases / all mature continuation cases",
    "false_entry_rate": "quick failures among ENTRY decisions / all ENTRY decisions with mature labels",
    "future_leakage_count": "future source/evaluator timestamps found by cutoff audit; hard target 0",
    "explanation_coverage": "cutoffs with a non-empty valid causal chain / all cutoffs",
    "lrrm_transition_stability": "correct STABLE/CHANGE predictions / mature LRRM transition labels",
    "anchor_failure_precision": "mature anchor failures among anchor-failure blocks / all such blocks",
    "pseudo_strength_filter_rate": "pseudo-strength cases blocked / all mature pseudo-strength cases",
    "nonlinear_false_entry_reduction": "(linear baseline false-entry rate - nonlinear false-entry rate) / linear rate",
    "exhaustion_block_precision": "mature exhaustion cases among exhaustion blocks / all exhaustion blocks",
    "regression_case_pass_rate": "matching decisions / all configured golden cases; missing cases fail",
}
EFFECT_METRIC_CONTRACT_HASH = hashlib.sha256(json.dumps(
    {"version": EFFECT_METRIC_CONTRACT_VERSION, "definitions": EFFECT_METRIC_DEFINITIONS},
    ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
).encode("utf-8")).hexdigest()

OUTCOME_LABEL_TYPES = {
    "next_regime_state": "text",
    "d1_return_pct": "number",
    "bad_t1": "bool",
    "continuation": "bool",
    "quick_failure": "bool",
    "lrrm_transition_stable": "bool",
    "anchor_failure": "bool",
    "pseudo_strength": "bool",
    "exhaustion": "bool",
}
OUTCOME_EVIDENCE_FIELDS = {
    "code", "source_id", "source_version", "source_timezone", "evidence_id",
    "cutoff_time", "matured_at", "published_at", "review_decision", "reviewed_by",
    "reviewed_at", "review_evidence_id", "review_record_hash", "labels", "evidence_hash",
}


def _canonical_hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_outcome_evidence(
    *, code: str, source_id: str, source_version: str, source_timezone: str,
    evidence_id: str, cutoff_time: str, matured_at: str, published_at: str,
    review_decision: str, reviewed_by: str, reviewed_at: str,
    review_evidence_id: str, review_record_hash: str, labels: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(labels, Mapping) or set(labels) - set(OUTCOME_LABEL_TYPES):
        raise ValueError("成熟结果标签包含未登记字段")
    clean_labels: Dict[str, Any] = {}
    for name, value in labels.items():
        label_type = OUTCOME_LABEL_TYPES[name]
        if label_type == "bool" and not isinstance(value, bool):
            raise ValueError(f"成熟结果标签必须为 bool: {name}")
        if label_type == "text" and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"成熟结果标签必须为非空文本: {name}")
        if label_type == "number" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"成熟结果标签必须为有限数值: {name}")
        clean_labels[name] = value
    record = {
        "code": code,
        "source_id": source_id,
        "source_version": source_version,
        "source_timezone": source_timezone,
        "evidence_id": evidence_id,
        "cutoff_time": cutoff_time,
        "matured_at": matured_at,
        "published_at": published_at,
        "review_decision": review_decision,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "review_evidence_id": review_evidence_id,
        "review_record_hash": review_record_hash,
        "labels": clean_labels,
    }
    if any(not isinstance(record[key], str) or not record[key].strip() for key in (
        "code", "source_id", "source_version", "source_timezone", "evidence_id",
        "cutoff_time", "matured_at", "published_at", "review_decision",
        "reviewed_by", "reviewed_at", "review_evidence_id",
    )):
        raise ValueError("成熟结果证据 provenance 不完整")
    if record["review_decision"] != "ACCEPTED" or (
        not isinstance(record["review_record_hash"], str)
        or len(record["review_record_hash"]) != 64
        or any(char not in "0123456789abcdef" for char in record["review_record_hash"].lower())
    ):
        raise ValueError("成熟结果必须绑定人工 ACCEPTED 复核记录哈希")
    try:
        times = {
            name: datetime.fromisoformat(record[name].replace("Z", "+00:00"))
            for name in ("cutoff_time", "matured_at", "reviewed_at", "published_at")
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("成熟结果的 cutoff/成熟/复核/发布时点无效") from exc
    if any(value.tzinfo is None or value.utcoffset() is None for value in times.values()):
        raise ValueError("成熟结果的 cutoff/成熟/复核/发布时点必须带时区")
    if not (
        times["cutoff_time"] <= times["matured_at"]
        <= times["reviewed_at"] <= times["published_at"]
    ):
        raise ValueError("成熟结果必须依次经过决策 cutoff、标签成熟、人工复核和发布")
    return {**record, "evidence_hash": _canonical_hash(record)}


def _validate_outcome_evidence(value: Any, code: str, cutoff_time: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != OUTCOME_EVIDENCE_FIELDS:
        raise ValueError("逐 cutoff 成熟结果证据格式无效")
    record = dict(value)
    supplied_hash = record.pop("evidence_hash")
    if (
        record.get("code") != code
        or record.get("cutoff_time") != cutoff_time
        or not isinstance(supplied_hash, str)
        or _canonical_hash(record) != supplied_hash
    ):
        raise ValueError("逐 cutoff 成熟结果证据哈希/关联键不匹配")
    make_outcome_evidence(
        code=record["code"], source_id=record["source_id"],
        source_version=record["source_version"], source_timezone=record["source_timezone"],
        evidence_id=record["evidence_id"], cutoff_time=record["cutoff_time"],
        matured_at=record["matured_at"], published_at=record["published_at"],
        review_decision=record["review_decision"], reviewed_by=record["reviewed_by"],
        reviewed_at=record["reviewed_at"], review_evidence_id=record["review_evidence_id"],
        review_record_hash=record["review_record_hash"],
        labels=record["labels"],
    )
    return record


def _metric(
    status: str, value: Any, numerator: Any, denominator: Any,
    reason: str, support: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "status": status, "value": value, "numerator": numerator,
        "denominator": denominator, "support": dict(support or {}),
        "reason": f"{EFFECT_METRIC_CONTRACT_VERSION}: {reason}",
    }


def _not_evaluable(reason: str, support: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    return _metric("NOT_EVALUABLE", None, None, None, reason, support)


def _ratio(numerator: int, denominator: int, reason: str, **support: Any) -> Dict[str, Any]:
    if denominator <= 0:
        return _not_evaluable(reason + "；有效样本数为 0", support)
    return _metric(
        "MEASURED", numerator / denominator, numerator, denominator, reason, support,
    )


def _decision(row: Mapping[str, Any], key: str = "decision") -> Optional[str]:
    value = row.get(key)
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


def compute_effect_metrics(
    stocks: Sequence[Mapping[str, Any]], *, cutoff_count: int,
    leakage_count: int, timestamp_check_count: int,
    regression_cases: Sequence[Mapping[str, Any]] = (),
    outcome_as_of: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    report_cutoff = None
    if outcome_as_of is not None:
        if not isinstance(outcome_as_of, str):
            raise ValueError("outcome_as_of 必须是显式时区时间文本")
        try:
            report_cutoff = datetime.fromisoformat(outcome_as_of.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("outcome_as_of 时间格式无效") from exc
        if report_cutoff.tzinfo is None or report_cutoff.utcoffset() is None:
            raise ValueError("outcome_as_of 必须包含时区")
    rows = []
    for stock in stocks:
        summary = stock.get("summary") if isinstance(stock, Mapping) else None
        code = summary.get("code") if isinstance(summary, Mapping) else None
        for observation in stock.get("cutoff_observations", []) if isinstance(stock, Mapping) else []:
            if not isinstance(observation, Mapping):
                continue
            copied = dict(observation)
            evidence = copied.get("outcome_evidence")
            if evidence is not None:
                evidence = _validate_outcome_evidence(
                    evidence, str(code or ""), str(copied.get("cutoff_time", "")),
                )
                if report_cutoff is None:
                    raise ValueError("有成熟标签证据时必须冻结 outcome_as_of")
                published_at = datetime.fromisoformat(evidence["published_at"].replace("Z", "+00:00"))
                reviewed_at = datetime.fromisoformat(evidence["reviewed_at"].replace("Z", "+00:00"))
                if (
                    published_at > report_cutoff or reviewed_at > report_cutoff
                ):
                    raise ValueError("成熟标签或人工复核晚于冻结的 outcome_as_of")
                if _decision(copied) is None:
                    raise ValueError("有成熟标签的 cutoff 必须保留最终 Gate 决策")
                copied["outcome_evidence"] = evidence
            rows.append(copied)

    def labeled(label: str) -> list[tuple[Mapping[str, Any], Any]]:
        result = []
        for row in rows:
            evidence = row.get("outcome_evidence")
            labels = evidence.get("labels") if isinstance(evidence, Mapping) else None
            if isinstance(labels, Mapping) and label in labels:
                result.append((row, labels[label]))
        return result

    metrics: Dict[str, Dict[str, Any]] = {}
    regimes = [
        (row, truth) for row, truth in labeled("next_regime_state")
        if isinstance(row.get("predicted_next_regime_state"), str)
        and row["predicted_next_regime_state"].strip()
    ]
    metrics["regime_transition_accuracy"] = _ratio(
        sum(row["predicted_next_regime_state"] == truth for row, truth in regimes),
        len(regimes), "预测下一 Regime 与成熟 next_regime_state 相同的比例",
    )

    carry = [
        (row, truth) for row, truth in labeled("d1_return_pct")
        if isinstance(row.get("t1_carry_score"), (int, float))
        and not isinstance(row.get("t1_carry_score"), bool)
        and math.isfinite(row["t1_carry_score"])
    ]
    high = [truth for row, truth in carry if row["t1_carry_score"] >= 70]
    low = [truth for row, truth in carry if row["t1_carry_score"] <= 30]
    if high and low:
        high_mean, low_mean = sum(high) / len(high), sum(low) / len(low)
        spread = high_mean - low_mean
        metrics["high_carry_vs_low_carry_spread"] = _metric(
            "MEASURED", spread, spread, 1,
            "Carry score >=70 与 <=30 两组成熟 D1 收益均值之差（百分点）",
            {"high_count": len(high), "low_count": len(low),
             "high_mean_pct": high_mean, "low_mean_pct": low_mean},
        )
    else:
        metrics["high_carry_vs_low_carry_spread"] = _not_evaluable(
            "缺少高分 >=70 或低分 <=30 的成熟 Carry 样本",
            {"high_count": len(high), "low_count": len(low)},
        )

    bad = labeled("bad_t1")
    metrics["bad_t1_filter_rate"] = _ratio(
        sum(_decision(row) != "ENTRY" for row, is_bad in bad if is_bad),
        sum(1 for _, is_bad in bad if is_bad),
        "成熟 bad_t1 样本中最终非 ENTRY 的比例",
    )
    continuation = labeled("continuation")
    metrics["continuation_capture_rate"] = _ratio(
        sum(_decision(row) == "ENTRY" for row, is_continuation in continuation if is_continuation),
        sum(1 for _, is_continuation in continuation if is_continuation),
        "成熟 continuation 样本中最终 ENTRY 的比例",
    )
    entries = [
        row for row, failed in labeled("quick_failure")
        if _decision(row) == "ENTRY"
    ]
    failed_entries = sum(
        1 for row, failed in labeled("quick_failure")
        if _decision(row) == "ENTRY" and failed
    )
    metrics["false_entry_rate"] = _ratio(
        failed_entries, len(entries), "成熟 quick_failure ENTRY / 有成熟标签的 ENTRY",
    )

    metrics["future_leakage_count"] = (
        _metric("MEASURED", leakage_count, leakage_count, timestamp_check_count,
                "来源时点与 evaluator 时点的 cutoff 泄漏计数")
        if timestamp_check_count > 0 else
        _not_evaluable("回放没有可核验的 cutoff 时点")
    )
    explained = sum(
        1 for row in rows
        if isinstance(row.get("causal_chain"), list) and row["causal_chain"]
        and all(isinstance(item, str) and item.strip() for item in row["causal_chain"])
    )
    metrics["explanation_coverage"] = _ratio(
        explained, cutoff_count, "逐 cutoff 非空且完整因果链 / 全部 cutoff",
    )

    lrrm = [
        (row, stable) for row, stable in labeled("lrrm_transition_stable")
        if isinstance(row.get("predicted_lrrm_transition"), str)
        and row["predicted_lrrm_transition"].strip().upper() in {"STABLE", "CHANGE"}
    ]
    metrics["lrrm_transition_stability"] = _ratio(
        sum((row["predicted_lrrm_transition"].strip().upper() == "STABLE") == stable for row, stable in lrrm),
        len(lrrm), "预测 LRRM STABLE/CHANGE 与成熟转换稳定标签一致的比例",
    )

    anchor = [
        (row, truth) for row, truth in labeled("anchor_failure")
        if row.get("anchor_failure_block") is True
    ]
    metrics["anchor_failure_precision"] = _ratio(
        sum(bool(truth) for _, truth in anchor), len(anchor),
        "anchor_failure_block 中成熟锚点失守样本的比例",
    )
    pseudo = labeled("pseudo_strength")
    metrics["pseudo_strength_filter_rate"] = _ratio(
        sum(row.get("pseudo_strength_block") is True for row, is_pseudo in pseudo if is_pseudo),
        sum(1 for _, is_pseudo in pseudo if is_pseudo),
        "成熟伪强样本中被 pseudo_strength_block 拦截的比例",
    )

    quick_failure_by_row = {
        id(row): failed for row, failed in labeled("quick_failure")
    }
    linear_entries = [row for row in rows if _decision(row, "linear_baseline_decision") == "ENTRY"
                      and id(row) in quick_failure_by_row]
    nonlinear_entries = [row for row in rows if _decision(row) == "ENTRY"
                         and id(row) in quick_failure_by_row]
    linear_rate = (
        sum(bool(quick_failure_by_row[id(row)]) for row in linear_entries) / len(linear_entries)
        if linear_entries else None
    )
    nonlinear_rate = (
        sum(bool(quick_failure_by_row[id(row)]) for row in nonlinear_entries) / len(nonlinear_entries)
        if nonlinear_entries else None
    )
    if linear_rate is not None and nonlinear_rate is not None and linear_rate > 0:
        reduction = (linear_rate - nonlinear_rate) / linear_rate
        metrics["nonlinear_false_entry_reduction"] = _metric(
            "MEASURED", reduction, linear_rate - nonlinear_rate, linear_rate,
            "同一成熟样本集上线性基线与非线性决策的 quick_failure ENTRY 率相对变化",
            {"linear_entry_count": len(linear_entries), "linear_false_entry_rate": linear_rate,
             "nonlinear_entry_count": len(nonlinear_entries),
             "nonlinear_false_entry_rate": nonlinear_rate},
        )
    else:
        metrics["nonlinear_false_entry_reduction"] = _not_evaluable(
            "缺少线性/非线性共同成熟标签，或线性基线误入率为 0",
            {"linear_entry_count": len(linear_entries), "nonlinear_entry_count": len(nonlinear_entries)},
        )

    exhaustion = [
        (row, truth) for row, truth in labeled("exhaustion")
        if row.get("exhaustion_block") is True
    ]
    metrics["exhaustion_block_precision"] = _ratio(
        sum(bool(truth) for _, truth in exhaustion), len(exhaustion),
        "exhaustion_block 中成熟衰竭样本的比例",
    )

    cases = {}
    for case in regression_cases:
        if not isinstance(case, Mapping) or set(case) != {"case_id", "expected_decision"}:
            raise ValueError("版本化 regression case 条目格式无效")
        case_id, expected = case["case_id"], case["expected_decision"]
        if (
            not isinstance(case_id, str) or not case_id.strip()
            or not isinstance(expected, str) or not expected.strip()
            or case_id in cases
        ):
            raise ValueError("版本化 regression case ID 重复或字段无效")
        cases[case_id] = expected.upper()
    observed_cases: Dict[str, str] = {}
    for row in rows:
        case_id = row.get("regression_case_id")
        if case_id is None:
            continue
        if case_id not in cases or case_id in observed_cases or _decision(row) is None:
            raise ValueError("回放 regression case 缺失、重复或没有最终决策")
        observed_cases[case_id] = _decision(row) or ""
    passed = sum(observed_cases.get(case_id) == expected for case_id, expected in cases.items())
    metrics["regression_case_pass_rate"] = (
        _ratio(passed, len(cases), "通过的版本化 golden case / 配置中的全部 case",
               observed_case_count=len(observed_cases), missing_case_count=len(cases) - len(observed_cases))
        if cases else _not_evaluable("没有版本化 regression case 清单")
    )

    if set(metrics) != set(EFFECT_METRIC_DEFINITIONS):
        raise AssertionError("effect metric contract implementation is incomplete")
    return metrics
