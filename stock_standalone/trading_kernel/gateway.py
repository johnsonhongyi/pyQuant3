# -*- coding: utf-8 -*-
"""Stable public gateway for ATS, TK UI and future broker/strategy modules."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import date
import hashlib
import json
import threading
from typing import Any, Mapping

from trading_kernel.contracts import (
    DECISION_ACTIONS,
    KERNEL_API_VERSION,
    REJECT_CODES,
    TRADE_STATES,
    TRADING_MODES,
    DecisionRequest,
    DecisionResponse,
)


class KernelGateway:
    """Public API boundary; hides kernel implementation details from callers."""

    REQUEST_CACHE_MAX = 10000

    def __init__(self, service: Any = None):
        if service is None:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
        self._service = service
        self._request_cache: dict[str, tuple[str, DecisionResponse]] = {}
        self._request_cache_lock = threading.RLock()
        self._request_cache_day = date.today().isoformat()

    @staticmethod
    def _request_fingerprint(request: DecisionRequest) -> str:
        payload = json.dumps(asdict(request), ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _rollover_request_cache_if_needed(self) -> None:
        today = date.today().isoformat()
        if self._request_cache_day != today:
            self._request_cache.clear()
            self._request_cache_day = today

    def _trim_request_cache_for_insert(self) -> None:
        while len(self._request_cache) >= self.REQUEST_CACHE_MAX:
            oldest_key = next(iter(self._request_cache))
            self._request_cache.pop(oldest_key, None)

    def _evaluate_request(
        self,
        request: DecisionRequest,
        *,
        write_journal: bool,
        request_id: str,
    ) -> DecisionResponse:
        result = self._service.evaluate_decision_item(
            request.to_kernel_item(), write_journal=write_journal
        )
        return DecisionResponse(
            accepted=bool(result.get("kernel_allowed")),
            executed=bool(result.get("kernel_executed")),
            action=str(result.get("kernel_action") or "HOLD"),
            size_pct=float(result.get("kernel_size_pct") or 0.0),
            trace_id=str(result.get("kernel_trace_id") or ""),
            order_id=str(result.get("kernel_order_id") or ""),
            reject_code=str(result.get("kernel_reject_code") or ""),
            state=str(result.get("kernel_state") or "FLAT"),
            request_id=request_id,
        )

    @property
    def api_version(self) -> str:
        return KERNEL_API_VERSION

    def submit(self, request: DecisionRequest, *, write_journal: bool = True) -> DecisionResponse:
        if request.api_version.split(".", 1)[0] != KERNEL_API_VERSION.split(".", 1)[0]:
            return DecisionResponse(
                accepted=False, executed=False, action="BLOCK", size_pct=0.0,
                trace_id="", order_id="", reject_code="INCOMPATIBLE_API_VERSION",
                request_id=request.request_id,
            )

        request_id = str(request.request_id or "").strip()
        if not request_id:
            return self._evaluate_request(
                request, write_journal=write_journal, request_id=""
            )

        fingerprint = self._request_fingerprint(request)
        with self._request_cache_lock:
            self._rollover_request_cache_if_needed()
            cached = self._request_cache.get(request_id)
            if cached is not None:
                cached_fingerprint, cached_response = cached
                if cached_fingerprint == fingerprint:
                    return cached_response
                return DecisionResponse(
                    accepted=False, executed=False, action="BLOCK", size_pct=0.0,
                    trace_id="", order_id="", reject_code="IDEMPOTENCY_CONFLICT",
                    request_id=request_id,
                )
            self._trim_request_cache_for_insert()
            response = self._evaluate_request(
                request, write_journal=write_journal, request_id=request_id
            )
            self._request_cache[request_id] = (fingerprint, response)
            return response

    def submit_mapping(self, payload: Mapping[str, Any], *, write_journal: bool = True) -> dict[str, Any]:
        """JSON/IPC-friendly decision endpoint with the same version contract."""
        allowed = {item.name for item in fields(DecisionRequest)}
        request = DecisionRequest(**{key: value for key, value in payload.items() if key in allowed})
        return asdict(self.submit(request, write_journal=write_journal))

    def capabilities(self) -> dict[str, Any]:
        """Machine-readable handshake for ATS and future external modules."""
        return {
            "api_version": KERNEL_API_VERSION,
            "kernel_version": str(getattr(self._service, "KERNEL_VERSION", "")),
            "modes": list(TRADING_MODES),
            "decision_actions": list(DECISION_ACTIONS),
            "trade_states": list(TRADE_STATES),
            "reject_codes": list(REJECT_CODES),
            "extension_ports": ["strategy_provider", "execution_adapter", "state_store", "event_sink"],
        }

    def register_strategy_provider(self, provider: Any) -> None:
        self._service.register_strategy_provider(provider)

    def register_execution_adapter(self, mode: str, adapter: Any) -> None:
        self._service.register_execution_adapter(mode, adapter)

    def register_state_store(self, store: Any, *, migrate: bool = True) -> None:
        self._service.register_state_store(store, migrate=migrate)

    def register_event_sink(self, sink: Any) -> None:
        self._service.register_event_sink(sink)

    def set_mode(self, mode: str) -> bool:
        return bool(self._service.set_trading_mode(mode))

    def get_mode(self) -> str:
        return str(self._service.mode)

    def get_positions(self) -> dict[str, Any]:
        return self._service.get_execution_adapter().get_positions()

    def get_account_snapshot(self) -> dict[str, Any]:
        adapter = self._service.get_execution_adapter()
        snapshot = dict(adapter.get_account_snapshot())
        snapshot.setdefault("initial_capital", float(getattr(adapter, "initial_capital", 0.0) or 0.0))
        snapshot.setdefault("position_count", len(adapter.get_positions()))
        return snapshot

    def get_order_history(self) -> list[dict[str, Any]]:
        return self._service.get_order_history()

    def get_state_snapshot(self) -> dict[str, str]:
        return self._service.state_manager.snapshot()

    def reconcile_state(self) -> dict[str, Any]:
        return self._service.reconcile_runtime_state()
