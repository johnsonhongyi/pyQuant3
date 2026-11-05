# -*- coding: utf-8 -*-
import json
import logging
import math
from unittest.mock import MagicMock
import pytest

from trading_kernel.core.risk import ApprovedOrder
import trading_kernel.execution.paper_adapter as pa
from trading_kernel.execution.paper_adapter import AccountSnapshot, PaperExecutionAdapter, Position


def test_manual_sell_replay_without_preexisting_buy_does_not_break_reconciliation():
    """测试手动平仓外部/历史底仓时，回放不抛出致命 SELL_EXCEEDS_LEDGER_POSITION 且正常增加回款。"""
    orders = [
        {"order_id": "b1", "code": "600000", "action": "BUY", "price": 10.0, "volume": 100, "timestamp": "2026-11-01T09:31:00"},
        # 手动卖出 600119（该股票从未记录在模拟订单流水的 BUY 中）
        {
            "order_id": "MANUAL_600119",
            "request_id": "MANUAL_600119_2026-11-02T09:30:00",
            "code": "600119",
            "action": "SELL",
            "price": 5.0,
            "volume": 1000,
            "fee": 0.0,
            "timestamp": "2026-11-02T09:30:00",
        },
    ]
    replayed, cash, problems = PaperExecutionAdapter._replay_order_ledger(orders, 10000.0)

    # 不应出现 SELL_EXCEEDS_LEDGER_POSITION:600119
    assert not any("SELL_EXCEEDS_LEDGER_POSITION" in p for p in problems)
    assert problems == []
    # 现金正确结算：10000 - 1000(买600000) + 5000(卖600119) = 14000
    assert abs(cash - 14000.0) < 1e-4
    assert "600000" in replayed
    assert "600119" not in replayed


def test_automated_impossible_sell_still_fails_closed():
    """测试非手动（自动策略发出的无底仓卖单）仍然严格拦截并报错，维持风控铁律。"""
    orders = [
        # 自动卖出 600119（非 MANUAL）
        {
            "order_id": "auto_strat_sell",
            "request_id": "strat_req_001",
            "code": "600119",
            "action": "SELL",
            "price": 5.0,
            "volume": 1000,
            "fee": 0.0,
            "timestamp": "2026-11-02T09:30:00",
        },
    ]
    replayed, cash, problems = PaperExecutionAdapter._replay_order_ledger(orders, 10000.0)
    assert any("SELL_EXCEEDS_LEDGER_POSITION:600119:0" in p for p in problems)


def test_gate_rejection_log_throttling(monkeypatch):
    """测试 Trade Gate 在处于阻断状态时，短时间内频繁拒单自动限频防刷屏。"""
    adapter = PaperExecutionAdapter(initial_capital=10000.0)
    adapter._execution_block_reason = "RESTORE_RECONCILIATION_FAILED:TEST_ERROR"
    order = ApprovedOrder(
        order_id="test_buy_01",
        code="600000",
        action="BUY",
        size_pct=0.1,
        price=10.0,
        stop_price=9.5,
    )

    mock_error = MagicMock()
    monkeypatch.setattr(pa.logger, "error", mock_error)

    # 连续提交 10 次
    for _ in range(10):
        res = adapter.submit_order(order)
        assert res is False

    # 验证日志：应该被抑制，仅打印 1 条日志，其余 9 次被合并压制
    assert mock_error.call_count == 1
    assert adapter._gate_rejection_suppressed_count == 9


def test_realign_ledger_baseline(tmp_path, monkeypatch):
    """测试 realign_ledger_baseline 原子固化基线并清除阻断原因。"""
    state_file = tmp_path / "test_realign_state.json"
    adapter = PaperExecutionAdapter(initial_capital=10000.0, state_file_path=str(state_file))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    adapter._execution_block_reason = "RESTORE_RECONCILIATION_FAILED:OLD_BLOCK"
    adapter.orders = [
        {"order_id": "o1", "code": "600000", "action": "BUY", "price": 10.0, "volume": 100, "timestamp": "2026-11-05T09:30:00"}
    ]
    adapter.account = AccountSnapshot(
        cash=9000.0,
        initial_capital=10000.0,
        positions={"600000": Position(code="600000", entry_price=10.0, volume=100.0, current_price=10.5)},
    )

    baseline = adapter.realign_ledger_baseline(source="TEST_ALIGN")
    assert baseline["status"] == "ALIGNED"
    assert baseline["order_count"] == 1
    assert baseline["cash"] == 9000.0
    assert "600000" in baseline["positions"]
    assert adapter._execution_block_reason == ""

    # 重新加载验证
    adapter2 = PaperExecutionAdapter(initial_capital=10000.0, state_file_path=str(state_file))
    assert adapter2.get_restore_status()["ready"] is True
    assert adapter2.get_restore_status()["block_reason"] == ""
