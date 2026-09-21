from trading_kernel.contracts import DecisionRequest, DecisionResponse
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
    assert capabilities["modes"] == ["OBSERVE", "PAPER", "CONFIRM", "LIVE_AUTO"]
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
