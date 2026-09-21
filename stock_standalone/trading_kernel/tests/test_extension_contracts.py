from trading_kernel.build_fingerprint import collect_build_fingerprint
from trading_kernel.contracts import (
    DECISION_ACTIONS,
    REJECT_CODES,
    TRADE_STATES,
    TRADING_MODES,
    DecisionRequest,
    DecisionResponse,
)
from trading_kernel.core.intent import DecisionIntent, DecisionReason
from trading_kernel.gateway import KernelGateway
from trading_kernel.kernel_service import TradingKernelService


class HoldStrategy:
    provider_id = "test.hold.v1"

    def __init__(self):
        self.calls = 0

    def decide(self, signal, state):
        self.calls += 1
        return DecisionIntent(
            code=signal.code,
            action="HOLD",
            size_pct=0.0,
            stop_price=None,
            confidence=1.0,
            reason=DecisionReason(
                regime="TEST_PROVIDER", setup="hold", sector_heat=0.0,
                sector_rank=None, is_leader=False, breakout=False,
                volume_ratio=1.0, dff=0.0, dff_positive=False,
                price_above_vwap=True, confidence_inputs=(),
            ),
            expires_at=signal.ts,
        )


def test_versioned_gateway_routes_external_strategy(tmp_path):
    provider = HoldStrategy()
    service = TradingKernelService(
        journal_path=str(tmp_path / "kernel.jsonl"),
        strategy_provider=provider,
    )
    gateway = KernelGateway(service)
    response = gateway.submit(
        DecisionRequest(code="000001", price=10.0, signal_type="EXTERNAL_TEST"),
        write_journal=False,
    )
    assert isinstance(response, DecisionResponse)
    assert response.accepted is True
    assert response.action == "HOLD"
    assert provider.calls == 1


def test_gateway_rejects_incompatible_major_version():
    class NeverCalledService:
        def evaluate_decision_item(self, *args, **kwargs):
            raise AssertionError("incompatible request must not enter the kernel")

    response = KernelGateway(NeverCalledService()).submit(
        DecisionRequest(code="000001", api_version="2.0")
    )
    assert response.accepted is False
    assert response.reject_code == "INCOMPATIBLE_API_VERSION"


def test_execution_adapter_registration_contract(tmp_path):
    service = TradingKernelService(journal_path=str(tmp_path / "kernel.jsonl"))

    class Adapter:
        orders = []

        def submit_order(self, order): return True
        def cancel_order(self, order_id): return False
        def get_positions(self): return {}
        def get_account_snapshot(self): return {"cash": 1.0}

    adapter = Adapter()
    service.register_execution_adapter("PAPER", adapter)
    service.set_trading_mode("PAPER")
    assert service.get_execution_adapter() is adapter


def test_gateway_exposes_stable_capability_handshake(tmp_path):
    gateway = KernelGateway(TradingKernelService(journal_path=str(tmp_path / "kernel.jsonl")))
    capabilities = gateway.capabilities()
    assert capabilities["api_version"] == "1.0"
    assert capabilities["modes"] == list(TRADING_MODES)
    assert capabilities["decision_actions"] == list(DECISION_ACTIONS)
    assert capabilities["trade_states"] == list(TRADE_STATES)
    assert capabilities["reject_codes"] == list(REJECT_CODES)
    assert set(capabilities["extension_ports"]) == {
        "strategy_provider", "execution_adapter", "state_store", "event_sink",
    }


def test_mapping_endpoint_is_ipc_friendly():
    class NeverCalledService:
        KERNEL_VERSION = "test"

        def evaluate_decision_item(self, *args, **kwargs):
            raise AssertionError("incompatible request must not enter the kernel")

    response = KernelGateway(NeverCalledService()).submit_mapping({
        "code": "000001", "api_version": "2.0", "future_field": "ignored",
    })
    assert response["accepted"] is False
    assert response["reject_code"] == "INCOMPATIBLE_API_VERSION"
    assert response["api_version"] == "1.0"


def test_runtime_state_and_event_ports_can_be_replaced(tmp_path):
    service = TradingKernelService(journal_path=str(tmp_path / "kernel.jsonl"))
    gateway = KernelGateway(service)

    class Store:
        def __init__(self): self.states = {}
        def get(self, code): return self.states.get(code, "FLAT")
        def set(self, code, state): self.states[code] = state
        def snapshot(self): return dict(self.states)

    class Sink:
        def __init__(self): self.records = []
        def append(self, record): self.records.append(dict(record))

    store, sink = Store(), Sink()
    gateway.register_state_store(store, migrate=False)
    gateway.register_event_sink(sink)
    assert service.state_manager is store
    assert service.journal is sink
    assert service.confirm_adapter.journal is sink
    assert service.broker_adapter.journal is sink


def test_gateway_request_id_is_idempotent():
    class Service:
        KERNEL_VERSION = "test"

        def __init__(self):
            self.calls = 0

        def evaluate_decision_item(self, item, **kwargs):
            self.calls += 1
            return {
                "kernel_allowed": True,
                "kernel_executed": False,
                "kernel_action": "HOLD",
                "kernel_size_pct": 0.0,
                "kernel_trace_id": "trace-1",
                "kernel_order_id": "",
                "kernel_reject_code": "",
                "kernel_state": "FLAT",
            }

    service = Service()
    gateway = KernelGateway(service)
    request = DecisionRequest(code="000001", price=10.0, request_id="req-1")
    first = gateway.submit(request, write_journal=False)
    second = gateway.submit(request, write_journal=False)
    assert second == first
    assert second.request_id == "req-1"
    assert service.calls == 1


def test_gateway_rejects_request_id_payload_conflict():
    class Service:
        KERNEL_VERSION = "test"

        def evaluate_decision_item(self, item, **kwargs):
            return {
                "kernel_allowed": True, "kernel_executed": False,
                "kernel_action": "HOLD", "kernel_size_pct": 0.0,
                "kernel_trace_id": "trace-1", "kernel_order_id": "",
                "kernel_reject_code": "", "kernel_state": "FLAT",
            }

    gateway = KernelGateway(Service())
    gateway.submit(DecisionRequest(code="000001", price=10.0, request_id="req-2"))
    response = gateway.submit(DecisionRequest(code="000001", price=10.1, request_id="req-2"))
    assert response.accepted is False
    assert response.action == "BLOCK"
    assert response.reject_code == "IDEMPOTENCY_CONFLICT"
    assert response.request_id == "req-2"


def test_build_fingerprint_contains_release_identity():
    payload = collect_build_fingerprint()
    assert payload["api_version"] == "1.0"
    assert payload["kernel_version"]
    assert "git_commit" in payload
    assert "git_dirty" in payload
    assert payload["generated_at_utc"]


def test_gateway_request_id_is_atomic_under_concurrency():
    from concurrent.futures import ThreadPoolExecutor
    import time

    class Service:
        KERNEL_VERSION = "test"

        def __init__(self):
            self.calls = 0

        def evaluate_decision_item(self, item, **kwargs):
            self.calls += 1
            time.sleep(0.02)
            return {
                "kernel_allowed": True, "kernel_executed": False,
                "kernel_action": "HOLD", "kernel_size_pct": 0.0,
                "kernel_trace_id": "trace-concurrent", "kernel_order_id": "",
                "kernel_reject_code": "", "kernel_state": "FLAT",
            }

    service = Service()
    gateway = KernelGateway(service)
    request = DecisionRequest(code="000001", price=10.0, request_id="req-concurrent")
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: gateway.submit(request), range(8)))
    assert service.calls == 1
    assert len({response.trace_id for response in responses}) == 1
