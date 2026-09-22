from __future__ import annotations

import json

from trading_kernel.kernel_service import TradingKernelService


def test_startup_reconciliation_snapshot_is_persisted(tmp_path):
    reconcile_dir = tmp_path / "reconcile"
    service = TradingKernelService(
        journal_path=str(tmp_path / "kernel.jsonl"),
        reconciliation_dir=str(reconcile_dir),
    )

    latest = reconcile_dir / "latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text(encoding="utf-8"))

    assert payload["reason"] == "STARTUP"
    assert payload["snapshot_version"] == "2.0"
    assert payload["t1_facts_version"] == "1.0"
    assert payload["account"]["initial_capital"] > 0
    assert payload["account"]["position_count"] == len(payload["positions"])
    assert payload["ssot"]["account"] == "trading_kernel.execution.paper_adapter"
    assert payload["reconciliation"]["order_count"] == len(payload["orders"])


def test_periodic_reconciliation_snapshot_is_throttled(tmp_path):
    reconcile_dir = tmp_path / "reconcile"
    service = TradingKernelService(
        journal_path=str(tmp_path / "kernel.jsonl"),
        reconciliation_dir=str(reconcile_dir),
    )
    history = next(reconcile_dir.glob("reconciliation_*.jsonl"))
    first_lines = history.read_text(encoding="utf-8").splitlines()

    assert service._persist_reconciliation_snapshot(reason="PERIODIC") is None
    assert history.read_text(encoding="utf-8").splitlines() == first_lines

    service._last_reconciliation_persist_monotonic = 0.0
    payload = service._persist_reconciliation_snapshot(reason="PERIODIC")
    assert payload is not None
    assert payload["reason"] == "PERIODIC"
    assert len(history.read_text(encoding="utf-8").splitlines()) == len(first_lines) + 1


def test_account_read_model_is_one_coherent_ssot_view(tmp_path):
    service = TradingKernelService(
        journal_path=str(tmp_path / "kernel.jsonl"),
        reconciliation_dir=str(tmp_path / "reconcile"),
    )
    model = service.get_account_read_model()

    assert set(model) >= {
        "account", "positions", "orders", "states",
        "reconciliation", "mode", "ssot",
    }
    assert model["account"]["position_count"] == len(model["positions"])
    assert model["reconciliation"]["position_count"] == len(model["positions"])
    assert model["reconciliation"]["order_count"] == len(model["orders"])
    assert model["ssot"]["orders"] == "trading_kernel.execution.paper_adapter"


def test_production_ipo_ledger_does_not_persist_financial_facts(tmp_path, monkeypatch):
    import ats.strategy.ipo_trading_center as module

    target = tmp_path / "ipo_trading_ledger.json"
    monkeypatch.setattr(module, "TRADING_LEDGER_FILE", str(target))

    center = module.IPOTradingCenter(auto_load_ledger=False)
    center._auto_load_ledger = True
    center.total_capital = 123456.0
    center.available_cash = 65432.0
    center._positions["000001"] = module.IPOTradingPosition(
        code="000001",
        name="test",
        shares=100,
        cost_price=10.0,
        current_price=10.5,
    )
    center._save_persisted_ledger()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["financial_ssot"] == "KernelGateway.get_account_read_model"
    assert "total_capital" not in payload
    assert "available_cash" not in payload
    assert "active_positions" not in payload


def test_explicit_custom_ipo_ledger_keeps_test_compatibility(tmp_path):
    from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOTradingPosition

    target = tmp_path / "isolated_ipo_ledger.json"
    center = IPOTradingCenter(
        total_capital=123456.0,
        auto_load_ledger=False,
        ledger_file=str(target),
    )
    center.available_cash = 65432.0
    center._positions["000001"] = IPOTradingPosition(
        code="000001", name="test", shares=100, cost_price=10.0, current_price=10.5,
    )
    center._save_persisted_ledger()

    restored = IPOTradingCenter(
        total_capital=1.0,
        auto_load_ledger=False,
        ledger_file=str(target),
    )

    assert restored.total_capital == 123456.0
    assert restored.available_cash == 65432.0
    assert restored.get_position("000001").shares == 100
