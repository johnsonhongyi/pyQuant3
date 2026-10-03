# -*- coding: utf-8 -*-
import json
from types import SimpleNamespace

import pytest

import ats.strategy.ipo_trading_center as trading_center_module
import ats.strategy.ipo_vwap_detector_engine as detector_module
from tools.run_shadow_live_test import run_shadow_test


def test_shadow_runner_degrades_without_candidate_codes_even_in_dry_run(tmp_path):
    report_dir = tmp_path / "reports"

    result = run_shadow_test(
        dry_run=True,
        candidate_codes=[],
        log_dir=str(report_dir),
    )

    report_path = next(report_dir.glob("shadow_test_report_*.jsonl"))
    rows = [json.loads(line) for line in report_path.read_text(encoding="utf-8").splitlines()]
    assert result["status"] == "DEGRADED"
    assert result["ledger_stats"]["error"] == "MISSING_CANDIDATE_CODES"
    assert rows[-1]["status"] == "DEGRADED"
    assert rows[-1]["real_broker_orders"] == 0


def test_non_dry_shadow_requires_isolated_paper_state(tmp_path, monkeypatch):
    def fail_if_market_scan_starts():
        raise AssertionError("market scan must not start without isolated PAPER state")

    monkeypatch.setattr(detector_module, "IPOVWAPDetectorEngine", fail_if_market_scan_starts)
    report_dir = tmp_path / "reports"
    result = run_shadow_test(
        dry_run=False,
        candidate_codes=["000001"],
        log_dir=str(report_dir),
    )

    report_path = next(report_dir.glob("shadow_test_report_*.jsonl"))
    report = json.loads(report_path.read_text(encoding="utf-8").splitlines()[-1])
    assert result["status"] == "DEGRADED"
    assert result["error"] == "ISOLATED_PAPER_STATE_REQUIRED"
    assert report["ledger_stats"]["error"] == "ISOLATED_PAPER_STATE_REQUIRED"
    assert report["paper_execution"] == "NOT_CONNECTED_ISOLATED"
    assert report["status"] == "DEGRADED"
    assert report["real_broker_orders"] == 0


def test_shadow_runner_counts_detector_and_arbitration_results(tmp_path, monkeypatch):
    signal = SimpleNamespace(
        code="000001", name="test", price=10.0, change_pct=1.2, vwap_diff_pct=0.4
    )

    class FakeDetector:
        def analyze_stock(self, code, force_refresh=False):
            assert code == "000001"
            assert force_refresh is True
            return signal

    class FakeTradingCenter:
        def __init__(self, auto_load_ledger=False, ledger_file=None, directive_executor=None):
            assert auto_load_ledger is False
            self.submitted = []
            self.directive_executor = directive_executor

        def submit_batch_reports(self, signals):
            self.submitted.extend(signals)

        def get_pending_directives(self):
            return [SimpleNamespace(directive_id="d1"), SimpleNamespace(directive_id="d2")]

        def get_positions(self):
            return {"000001": {"shares": 100}}

        def execute_directive(self, directive):
            return bool(self.directive_executor(directive).executed)

    monkeypatch.setattr(detector_module, "IPOVWAPDetectorEngine", FakeDetector)
    monkeypatch.setattr(trading_center_module, "IPOTradingCenter", FakeTradingCenter)

    result = run_shadow_test(
        dry_run=True,
        candidate_codes=["000001"],
        log_dir=str(tmp_path / "reports"),
    )

    assert result["rounds_completed"] == 2
    assert result["signals_processed"] == 2
    assert result["directives_generated"] == 4
    assert result["ledger_stats"]["pipeline_status"] == "ATS_ARBITRATED_PAPER_NOT_CONNECTED"
    assert result["ledger_stats"]["paper_result_count"] == 0
    assert result["real_broker_orders"] == 0


def test_shadow_runner_writes_degraded_row_when_pipeline_raises(tmp_path, monkeypatch):
    signal = SimpleNamespace(
        code="000001", name="test", price=10.0, change_pct=1.2, vwap_diff_pct=0.4
    )

    class FakeDetector:
        def analyze_stock(self, code, force_refresh=False):
            return signal

    class FailingTradingCenter:
        def __init__(self, **kwargs):
            pass

        def submit_batch_reports(self, signals):
            raise RuntimeError("isolated pipeline failure")

    monkeypatch.setattr(detector_module, "IPOVWAPDetectorEngine", FakeDetector)
    monkeypatch.setattr(trading_center_module, "IPOTradingCenter", FailingTradingCenter)
    report_dir = tmp_path / "reports"

    result = run_shadow_test(
        dry_run=True,
        candidate_codes=["000001"],
        log_dir=str(report_dir),
    )

    report_path = next(report_dir.glob("shadow_test_report_*.jsonl"))
    rows = [json.loads(line) for line in report_path.read_text(encoding="utf-8").splitlines()]
    assert result["status"] == "DEGRADED"
    assert rows[-1]["status"] == "DEGRADED"
    assert rows[-1]["ledger_stats"]["error"] == "isolated pipeline failure"


def test_shadow_runner_uses_only_explicit_isolated_paper_paths(tmp_path, monkeypatch):
    signal = SimpleNamespace(
        code="000001", name="test", price=10.0, change_pct=1.2, vwap_diff_pct=0.4
    )
    captured = {}

    class FakeDetector:
        def analyze_stock(self, code, force_refresh=False):
            return signal

    class FakeAdapter:
        def __init__(self, state_file_path):
            captured["state_file_path"] = state_file_path

        def get_positions(self):
            return {"000001": {"volume": 100}}

    class FakeService:
        KERNEL_VERSION = "test-kernel"

        def __init__(self, **kwargs):
            self.mode = kwargs["initial_mode"]
            self.executor = kwargs["paper_adapter"]
            self.orders = []
            captured["service_kwargs"] = kwargs

        def get_execution_adapter(self):
            return self.executor

        def get_order_history(self):
            return self.orders

    class FakeTradingCenter:
        def __init__(self, auto_load_ledger=False, ledger_file=None, directive_executor=None):
            assert auto_load_ledger is False
            self.directive_executor = directive_executor

        def submit_batch_reports(self, signals):
            pass

        def get_pending_directives(self):
            return [SimpleNamespace(directive_id="d1")]

        def execute_directive(self, directive):
            return self.directive_executor(directive).executed

    monkeypatch.setattr(detector_module, "IPOVWAPDetectorEngine", FakeDetector)
    monkeypatch.setattr(trading_center_module, "IPOTradingCenter", FakeTradingCenter)
    import trading_kernel.execution.paper_adapter as adapter_module
    import trading_kernel.kernel_service as service_module
    import ats.unified_paper_account as paper_account_module

    monkeypatch.setattr(adapter_module, "PaperExecutionAdapter", FakeAdapter)
    monkeypatch.setattr(service_module, "TradingKernelService", FakeService)
    monkeypatch.setattr(
        paper_account_module,
        "execute_command_directive",
        lambda directive, *, gateway: SimpleNamespace(
            executed=True, order_id="o1", trace_id="t1", action="BUY",
            reject_code="", volume=100, size_pct=0.01, request_id="d1",
            execution_id="e1", status="FILLED", related_orders=(),
        ),
    )

    report_dir = tmp_path / "reports"
    state_dir = report_dir / "paper_state"
    result = run_shadow_test(
        dry_run=True,
        candidate_codes=["000001"],
        log_dir=str(report_dir),
        isolated_paper_state_dir=str(state_dir),
    )

    assert result["paper_execution"] == "CONNECTED"
    assert result["paper_execution_scope"] == "ISOLATED"
    assert result["ledger_stats"]["paper_result_count"] == 1
    assert result["ledger_stats"]["pipeline_status"] == "ATS_ARBITRATED_ISOLATED_TK_PAPER"
    assert result["ledger_stats"]["directive_audit"][0]["directive_id"] == "d1"
    assert result["ledger_stats"]["directive_audit"][0]["order_id"] == ""
    assert result["real_broker_orders"] == 0
    assert captured["state_file_path"] == str(state_dir / "paper_account_state.json")
    assert captured["service_kwargs"]["initial_mode"] == "PAPER"
    assert captured["service_kwargs"]["journal_path"].startswith(str(state_dir))


def test_shadow_runner_rejects_state_directory_outside_report_root(tmp_path):
    report_dir = tmp_path / "reports"
    outside_dir = tmp_path / "paper_state"
    with pytest.raises(ValueError, match="inside report directory"):
        run_shadow_test(
            dry_run=True,
            log_dir=str(report_dir),
            isolated_paper_state_dir=str(outside_dir),
        )


def test_paper_adapter_uses_explicit_state_path_without_resolving_default(tmp_path, monkeypatch):
    from trading_kernel.execution.paper_adapter import PaperExecutionAdapter

    state_path = tmp_path / "isolated" / "paper.json"
    monkeypatch.setattr(
        "trading_kernel.execution.paper_adapter.get_app_root",
        lambda: (_ for _ in ()).throw(AssertionError("default app root must not be used")),
    )
    adapter = PaperExecutionAdapter(state_file_path=str(state_path))
    assert adapter._state_file == str(state_path.resolve())
    assert not state_path.exists()


def test_tk_service_keeps_paper_state_and_reconciliation_under_injected_root(tmp_path, monkeypatch):
    from ats.bounded_evaluation_store import evaluation_store
    from trading_kernel.engine.state_manager import StateManager
    from trading_kernel.execution.paper_adapter import PaperExecutionAdapter
    from trading_kernel.gateway import KernelGateway
    from trading_kernel.kernel_service import TradingKernelService

    monkeypatch.setattr(
        TradingKernelService,
        "_auto_warm_up_from_preprocessed_hdf5",
        lambda self: None,
    )
    isolated_root = tmp_path / "isolated"
    isolated_root.mkdir()
    monkeypatch.setattr('tempfile.gettempdir', lambda: str(isolated_root))
    adapter = PaperExecutionAdapter(state_file_path=str(isolated_root / "paper.json"))
    service = TradingKernelService(
        journal_path=str(isolated_root / "kernel.jsonl"),
        reconciliation_dir=str(isolated_root / "reconciliation"),
        paper_adapter=adapter,
        state_store=StateManager(),
        initial_mode="PAPER",
    )
    gateway = KernelGateway(service=service)

    assert gateway.get_mode() == "PAPER"
    assert service.executor is adapter
    assert adapter._state_file == str((isolated_root / "paper.json").resolve())
    latest = str(isolated_root / 'reconciliation' / 'latest.json')
    assert latest in evaluation_store.paths(latest)
    assert evaluation_store.read(latest, {}).get('mode') == 'PAPER'
    assert not (tmp_path / "logs" / "paper_account_state.json").exists()
