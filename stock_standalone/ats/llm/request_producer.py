"""Build bounded read-only Agent requests from accepted live decision snapshots."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping

from ats.llm.agent_contracts import payload_schema_hash
from ats.llm.learning_snapshot_store import get_snapshot_record, snapshot_store_recent
from ats.llm.offline_learning import compute_input_snapshot_hash, validate_input_snapshot
from ats.llm.worker_protocol import encode_worker_request


_MAX_SNAPSHOTS_PER_POLL = 8
_MAX_PROMPT_BYTES = 45 * 1024
_PROMPT_VERSION = "r9.market-regime.v1"


class LiveSnapshotRequestProducer:
    """Poll recent, frozen decision inputs; all missing acceptance evidence blocks output."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._seen: set[str] = set()
        self._seen_order: deque[str] = deque()
        self._pending: Dict[str, str] = {}
        self._generated = 0
        self._skipped_stale = 0
        self._rejected = 0
        self._last_snapshot_id = ""
        self._last_reason = "等待准入检查"

    def poll(self, runtime_accepting: bool) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "state": "BLOCKED", "reason": "", "scanned": 0, "generated": self._generated,
            "skipped_stale": self._skipped_stale, "rejected": self._rejected,
            "last_snapshot_id": self._last_snapshot_id, "requests": [],
        }
        try:
            config = self._load_config()
            acceptance_ok, reason = self._accepted_stages(config)
            if not acceptance_ok:
                return self._finish(status, "BLOCKED", reason)
            if not runtime_accepting:
                return self._finish(status, "WAITING_RUNTIME", "Worker 或 Provider 尚未通过运行准入")
            max_age_seconds = signal_max_age_seconds(config)
            backend = self._load_backend()
            status["state"] = "SCANNING"
            rows = snapshot_store_recent(self._root, limit=100)
            latest_by_ticker: Dict[str, Mapping[str, Any]] = {}
            for row in rows:
                ticker = row.get("ticker")
                if isinstance(ticker, str) and ticker not in latest_by_ticker:
                    latest_by_ticker[ticker] = row
            now = datetime.now(timezone.utc)
            requests: List[Dict[str, Any]] = []
            for row in latest_by_ticker.values():
                snapshot_id = row.get("snapshot_id")
                if (
                    not isinstance(snapshot_id, str) or snapshot_id in self._seen
                    or snapshot_id in self._pending.values()
                ):
                    continue
                status["scanned"] += 1
                record = get_snapshot_record(self._root, snapshot_id)
                if not isinstance(record, Mapping):
                    self._reject()
                    self._remember(snapshot_id)
                    continue
                if (
                    not _is_fresh(record.get("captured_at"), now, max_age_seconds)
                    or not _is_fresh(record.get("cutoff"), now, max_age_seconds)
                ):
                    self._skipped_stale += 1
                    self._remember(snapshot_id)
                    continue
                try:
                    snapshot = validate_input_snapshot(record.get("input_snapshot"), config)
                    snapshot_hash = compute_input_snapshot_hash(snapshot)
                    if snapshot_hash != record.get("snapshot_hash"):
                        raise ValueError("快照哈希与存储记录不一致")
                    if record.get("ticker") != row.get("ticker"):
                        raise ValueError("快照标的与索引不一致")
                    request = self._request(record, snapshot, snapshot_hash, backend["model_id"])
                    encode_worker_request(request)
                except Exception:
                    self._reject()
                    self._remember(snapshot_id)
                    continue
                requests.append(request)
                self._pending[request["request_id"]] = snapshot_id
                if len(requests) >= _MAX_SNAPSHOTS_PER_POLL:
                    break
            status["requests"] = requests
            status["generated"] = self._generated
            status["skipped_stale"] = self._skipped_stale
            status["rejected"] = self._rejected
            state = "REQUESTS_READY" if requests else "IDLE_NO_FRESH_SNAPSHOT"
            reason = f"本轮构造 {len(requests)} 条；历史旧样本累计跳过 {self._skipped_stale} 条"
            return self._finish(status, state, reason)
        except Exception as exc:
            self._reject()
            reason = str(exc).strip()[:160] or "校验异常"
            return self._finish(status, "BLOCKED", f"准入阻断：{reason}；本轮未提交请求")

    def acknowledge(self, request_id: str, accepted: bool) -> int:
        snapshot_id = self._pending.pop(request_id, "")
        if snapshot_id and accepted:
            self._remember(snapshot_id)
            self._last_snapshot_id = snapshot_id
            self._generated += 1
        return self._generated

    def _remember(self, snapshot_id: str) -> None:
        if snapshot_id in self._seen:
            return
        self._seen.add(snapshot_id)
        self._seen_order.append(snapshot_id)
        if len(self._seen_order) > 2000:
            self._seen.discard(self._seen_order.popleft())

    def _load_config(self) -> Any:
        from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot

        path = self._root / "config" / "ipo_sentiment.yaml"
        config = IPODecisionConfigSnapshot.from_yaml(str(path))
        if not config.verify_integrity():
            raise ValueError("IPO 配置哈希校验失败")
        return config

    def _accepted_stages(self, config: Any) -> tuple[bool, str]:
        path = self._root / "config" / "ipo_stage_acceptance.json"
        if not path.is_file():
            return False, "缺少 Stage 0–2 阶段验收证据文件"
        if path.stat().st_size > 64 * 1024:
            return False, "阶段验收文件超过大小限制"
        with path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
        stages = document.get("stages") if isinstance(document, dict) else None
        if not isinstance(stages, dict):
            return False, "Stage 0–2 验收证据未配置"
        for index in range(3):
            record = stages.get(str(index), stages.get(f"stage{index}"))
            if not isinstance(record, dict) or record.get("status") != "ACCEPTED" or not record.get("evidence"):
                return False, f"Stage {index} 尚无已验收证据"
            if index == 0 and not config.verify_integrity():
                return False, "Stage 0 的版本化数据契约未通过哈希校验"
        return True, ""

    def _load_backend(self) -> Dict[str, str]:
        from ats.llm.backend_factory import build_backend_factory

        path = self._root / "config" / "llm_config.yaml"
        build_backend_factory(path)
        import yaml

        with path.open("r", encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
        backend = document["backends"]["antigravity_sdk"]
        model_id = backend["model_id"].strip()
        return {"model_id": model_id}

    def _request(
        self, record: Mapping[str, Any], snapshot: Mapping[str, Any],
        snapshot_hash: str, model_id: str,
    ) -> Dict[str, Any]:
        ticker = str(record["ticker"])
        cutoff = str(record["cutoff"])
        request_id = hashlib.sha256(
            f"MARKET_REGIME|{ticker}|{cutoff}|{snapshot_hash}".encode("utf-8")
        ).hexdigest()
        evidence_id = snapshot_hash
        context = {
            "snapshot_hash": snapshot_hash,
            "ticker": ticker,
            "cutoff": cutoff,
            "rule_decision": record.get("decision", ""),
            "rule_proposal": record.get("standard_proposal", {}),
            "gate_causal_chain": record.get("gate_causal_chain", []),
            "input_snapshot": snapshot,
        }
        prompt = (
            "你是只读的新股情绪分析 Agent。只依据下面截止时点的已验证快照做辅助归纳；"
            "不得引入截止时间之后的信息，不得给出交易指令，也不得修改规则、标签或模型。"
            "输出必须严格符合给定 JSON Schema。所有催化与风险条目都必须引用 evidence_ids 中的快照哈希。\n"
            + json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
        if len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
            raise ValueError("提示内容超过本地请求大小限制")
        return {
            "request_id": request_id, "agent_type": "MARKET_REGIME",
            "scope_id": ticker, "ticker": ticker, "as_of_time": cutoff,
            "prompt": prompt, "model_id": model_id, "prompt_version": _PROMPT_VERSION,
            "evidence_ids": [evidence_id],
            "schema_hash": payload_schema_hash("MARKET_REGIME"),
        }

    def _reject(self) -> None:
        self._rejected += 1

    def _finish(self, status: Dict[str, Any], state: str, reason: str) -> Dict[str, Any]:
        status.update({
            "state": state, "reason": reason[:200], "generated": self._generated,
            "skipped_stale": self._skipped_stale, "rejected": self._rejected,
            "last_snapshot_id": self._last_snapshot_id,
        })
        return status


def signal_max_age_seconds(config: Any) -> float:
    decision_config = getattr(config, "decision_config", None)
    trade_gate = decision_config.get("trade_gate") if isinstance(decision_config, Mapping) else None
    value = trade_gate.get("signal_max_age_seconds") if isinstance(trade_gate, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("版本化 trade_gate.signal_max_age_seconds 缺失")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("版本化信号最大时效必须为正有限秒数") from exc
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError("版本化信号最大时效必须为正有限秒数")
    return normalized


def _is_fresh(value: Any, now: datetime, max_age_seconds: float) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return False
        age = (now - parsed.astimezone(timezone.utc)).total_seconds()
        return 0 <= age <= max_age_seconds
    except (TypeError, ValueError, OverflowError):
        return False
