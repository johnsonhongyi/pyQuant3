from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping

from trading_kernel.core.trace import KernelTrace
from trading_kernel.engine.decision_engine import decide
from trading_kernel.engine.risk_gate import RiskLimits, evaluate
from trading_kernel.engine.signal_canonicalizer import canonicalize_decision_queue_item
from trading_kernel.engine.state_manager import StateManager
from trading_kernel.observability.journal import JsonlJournal
from trading_kernel.observability.trace_hasher import stable_hash


class TradingKernelService:
    def __init__(self, journal_path: str = "logs/trading_kernel_trace.jsonl"):
        self.state_manager = StateManager()
        self.journal = JsonlJournal(journal_path)
        
        # Phase 4 & Phase 7: 初始化纸单模拟适配器并包装 Confirm 确认执行器
        from trading_kernel.execution.paper_adapter import PaperExecutionAdapter
        from trading_kernel.execution.confirm_adapter import ConfirmExecutionAdapter
        self.paper_adapter = PaperExecutionAdapter()
        self.executor = ConfirmExecutionAdapter(
            underlying_adapter=self.paper_adapter,
            journal=self.journal,
            mode="CONFIRM"
        )
        
        # 挂载 confirm 弹窗回调（Lazy import 避免无头回测环境导入 PyQt6 报错）
        try:
            from tk_gui_modules.confirm_bubble import show_confirmation_bubble_sync
            self.executor.set_confirm_callback(show_confirmation_bubble_sync)
        except ImportError:
            def headless_fallback_confirm(ord):
                return {
                    "confirmed": False,
                    "size_pct_override": None,
                    "override_reason": "Headless environment bypass rejection",
                }
            self.executor.set_confirm_callback(headless_fallback_confirm)

    def evaluate_decision_item(self, item: Mapping[str, Any], write_journal: bool = True) -> dict[str, Any]:
        raw_hash = stable_hash(dict(item))
        signal = canonicalize_decision_queue_item(item)
        state = self.state_manager.get(signal.code)
        intent = decide(signal, state)
        risk = evaluate(intent, signal, state, RiskLimits())

        signal_hash = stable_hash(signal)
        intent_hash = stable_hash(intent)
        risk_hash = stable_hash(risk)
        trace = KernelTrace(
            trace_id=stable_hash((raw_hash, signal_hash, state, intent_hash, risk_hash))[:20],
            raw_event_hash=raw_hash,
            signal_hash=signal_hash,
            state=state,
            intent_hash=intent_hash,
            risk_hash=risk_hash,
            execution_hash=None,
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )

        result = {
            "kernel_state": state,
            "kernel_action": risk.final_action,
            "kernel_size_pct": risk.final_size_pct,
            "kernel_confidence": intent.confidence,
            "kernel_allowed": risk.allowed,
            "kernel_reject_code": str(risk.reject_context.get("code", "")) if risk.reject_context else "",
            "kernel_stop_price": intent.stop_price,
            "kernel_trace_id": trace.trace_id,
            "kernel_reason": asdict(intent.reason),
            "kernel_order_id": risk.order.order_id if risk.order else "",
            "kernel_executed": False,
        }

        # Phase 7 & Phase 4: 如果风控允许，则进入执行层投递订单
        if risk.allowed and risk.order:
            executed = self.executor.submit_order(risk.order)
            result["kernel_executed"] = executed
            
            # 如果确认执行交易成功，同步更新 StateManager 状态
            if executed:
                if risk.final_action in {"BUY", "ADD"}:
                    self.state_manager.set(signal.code, "IN_TRADE")
                elif risk.final_action == "SELL":
                    self.state_manager.set(signal.code, "FLAT")

        if write_journal:
            self.journal.append(
                {
                    "trace": trace,
                    "signal": signal,
                    "intent": intent,
                    "risk": risk,
                    "kernel_result": result,
                }
            )
        return result


_SERVICE: TradingKernelService | None = None


def get_kernel_service() -> TradingKernelService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = TradingKernelService()
    return _SERVICE


def enrich_decision_item(item: Mapping[str, Any], write_journal: bool = True) -> dict[str, Any]:
    enriched = dict(item)
    try:
        enriched.update(get_kernel_service().evaluate_decision_item(item, write_journal=write_journal))
    except Exception as exc:
        enriched.update(
            {
                "kernel_state": "",
                "kernel_action": "ERROR",
                "kernel_size_pct": 0.0,
                "kernel_confidence": 0.0,
                "kernel_allowed": False,
                "kernel_reject_code": f"KERNEL_ERROR:{exc}",
                "kernel_stop_price": None,
                "kernel_trace_id": "",
                "kernel_order_id": "",
            }
        )
    return enriched

