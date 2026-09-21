from trading_kernel.gateway import KernelGateway
from trading_kernel.kernel_service import TradingKernelService


def test_live_readiness_preview_is_read_only_and_blocks_base_broker(tmp_path):
    service = TradingKernelService(
        journal_path=str(tmp_path / "journal.jsonl"),
        reconciliation_dir=str(tmp_path / "recon"),
    )
    before_mode = service.mode
    readiness = service.preview_live_readiness()
    assert service.mode == before_mode
    assert readiness["ready"] is False
    assert "PHYSICAL_BROKER_ADAPTER_REQUIRED" in readiness["reasons"]
    assert readiness["details"]["broker_adapter_class"] == "BrokerExecutionAdapter"


def test_gateway_exposes_live_readiness(tmp_path):
    service = TradingKernelService(
        journal_path=str(tmp_path / "journal2.jsonl"),
        reconciliation_dir=str(tmp_path / "recon2"),
    )
    gateway = KernelGateway(service=service)
    readiness = gateway.get_live_readiness()
    assert "ready" in readiness
    assert "reasons" in readiness
    assert "details" in readiness
