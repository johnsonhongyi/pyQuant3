from __future__ import annotations

import json
import os
from typing import Any, Mapping

from trading_kernel.core.signal import StrategySignal
from trading_kernel.core.intent import DecisionIntent, DecisionReason
from trading_kernel.core.risk import RiskDecision, ApprovedOrder
from trading_kernel.core.trace import KernelTrace
from trading_kernel.engine.decision_engine import decide
from trading_kernel.engine.risk_gate import RiskLimits, evaluate
from trading_kernel.observability.trace_hasher import stable_hash


def reconstruct_signal(sig_dict: dict[str, Any]) -> StrategySignal:
    """从 journal dict 反序列化为 StrategySignal 实体"""
    features = sig_dict.get("features", {})
    return StrategySignal(
        code=sig_dict.get("code", ""),
        name=sig_dict.get("name", ""),
        ts=sig_dict.get("ts", ""),
        source=sig_dict.get("source", ""),
        signal_type=sig_dict.get("signal_type", ""),
        price=float(sig_dict.get("price", 0.0)),
        features=features,
    )


class ReplayReport:
    """回放报告模型"""
    def __init__(self) -> None:
        self.total_records: int = 0
        self.success_count: int = 0
        self.mismatches: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "success_count": self.success_count,
            "mismatch_count": len(self.mismatches),
            "mismatches": self.mismatches,
        }


class ReplayRunner:
    """确定性决策回放运行器"""
    def __init__(self, journal_path: str = "logs/trading_kernel_trace.jsonl") -> None:
        self.journal_path = journal_path

    def run_replay(self) -> ReplayReport:
        report = ReplayReport()
        if not os.path.exists(self.journal_path):
            return report

        with open(self.journal_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception as exc:
                    report.mismatches.append({
                        "line_num": line_idx,
                        "error": "JSON_PARSE_ERROR",
                        "exception": str(exc),
                    })
                    continue

                report.total_records += 1

                # 提取历史各字段与元数据
                hist_trace = data.get("trace", {})
                hist_sig_dict = data.get("signal", {})
                hist_state = hist_trace.get("state", "FLAT")
                
                # 提取期望的哈希值
                expected_intent_hash = hist_trace.get("intent_hash")
                expected_risk_hash = hist_trace.get("risk_hash")
                trace_id = hist_trace.get("trace_id", "")

                try:
                    # 1. 还原 StrategySignal 对象
                    signal = reconstruct_signal(hist_sig_dict)
                    
                    # 2. 调用纯决定引擎重建 DecisionIntent
                    replayed_intent = decide(signal, hist_state)
                    
                    # 3. 调用风控网关进行评估
                    replayed_risk = evaluate(replayed_intent, signal, hist_state, RiskLimits())
                    
                    # 4. 计算重新决定的稳定哈希值
                    replayed_intent_hash = stable_hash(replayed_intent)
                    replayed_risk_hash = stable_hash(replayed_risk)

                    # 5. 比对新老决策与风控决策哈希
                    mismatch: dict[str, Any] = {}
                    if replayed_intent_hash != expected_intent_hash:
                        mismatch["intent"] = {
                            "expected_hash": expected_intent_hash,
                            "actual_hash": replayed_intent_hash,
                            "expected_action": data.get("intent", {}).get("action"),
                            "actual_action": replayed_intent.action,
                        }
                    
                    if replayed_risk_hash != expected_risk_hash:
                        mismatch["risk"] = {
                            "expected_hash": expected_risk_hash,
                            "actual_hash": replayed_risk_hash,
                            "expected_allowed": data.get("risk", {}).get("allowed"),
                            "actual_allowed": replayed_risk.allowed,
                        }

                    if mismatch:
                        mismatch["line_num"] = line_idx
                        mismatch["trace_id"] = trace_id
                        mismatch["code"] = signal.code
                        mismatch["state"] = hist_state
                        report.mismatches.append(mismatch)
                    else:
                        report.success_count += 1

                except Exception as exc:
                    report.mismatches.append({
                        "line_num": line_idx,
                        "trace_id": trace_id,
                        "error": "REPLAY_EXECUTION_ERROR",
                        "exception": str(exc),
                    })

        return report
