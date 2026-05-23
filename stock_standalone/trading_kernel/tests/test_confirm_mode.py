# -*- coding: utf-8 -*-
import os
import json
import pytest
from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.execution.paper_adapter import PaperExecutionAdapter
from trading_kernel.execution.confirm_adapter import ConfirmExecutionAdapter
from trading_kernel.observability.journal import JsonlJournal


def test_confirm_execution_adapter_flows(tmp_path):
    """测试 ConfirmExecutionAdapter 在各种人明确认与人工干预场景下的完整生命周期"""
    log_file = tmp_path / "confirm_audit.jsonl"
    journal = JsonlJournal(path=str(log_file))

    # 初始化底层纸单执行器与装饰器
    paper_adapter = PaperExecutionAdapter(initial_capital=1000000.0)
    confirm_adapter = ConfirmExecutionAdapter(
        underlying_adapter=paper_adapter,
        journal=journal,
        mode="CONFIRM"
    )

    # 1. 构造一个标准的 ApprovedOrder
    order = ApprovedOrder(
        order_id="order-001",
        code="600519",
        action="BUY",
        size_pct=0.15,  # 15% 仓位
        price=1700.0,
        stop_price=1600.0,
    )

    # 2. 测试场景：确认模式下未挂载回调，默认自动安全拦截拒绝
    success = confirm_adapter.submit_order(order)
    assert not success
    assert len(paper_adapter.orders) == 0

    # 核验审计记录
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        audit = json.loads(lines[0])
        assert audit["confirmed"] is False
        assert audit["override_reason"] == "NO_CONFIRM_CALLBACK_REGISTERED"

    # 3. 测试场景：AUTO 模式下直接秒级放行，不触发回调
    confirm_adapter.mode = "AUTO"
    success = confirm_adapter.submit_order(order)
    assert success
    assert len(paper_adapter.orders) == 1
    assert paper_adapter.orders[0]["code"] == "600519"
    assert paper_adapter.orders[0]["size_pct"] == 0.15

    # 4. 测试场景：CONFIRM 模式下，操盘手确认通过
    confirm_adapter.mode = "CONFIRM"
    
    # 模拟人工弹窗应答：操盘手点击“同意”，原样大小提交
    def mock_confirmed_callback(ord):
        return {
            "confirmed": True,
            "size_pct_override": None,
            "override_reason": "Approved by Trader Johnson"
        }
    
    confirm_adapter.set_confirm_callback(mock_confirmed_callback)
    
    order2 = ApprovedOrder(
        order_id="order-002",
        code="000001",
        action="BUY",
        size_pct=0.10,
        price=10.0,
        stop_price=9.5,
    )
    
    success = confirm_adapter.submit_order(order2)
    assert success
    assert len(paper_adapter.orders) == 2
    assert paper_adapter.orders[1]["code"] == "000001"
    assert paper_adapter.orders[1]["size_pct"] == 0.10

    # 核验确认后的 Journal 审计
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 2
        audit = json.loads(lines[1])
        assert audit["confirmed"] is True
        assert audit["override_reason"] == "Approved by Trader Johnson"
        assert audit["actual_order_id"] == "order-002"

    # 5. 测试场景：CONFIRM 模式下，操盘手物理修改下单占比 (Override Size 15% -> 5%)
    def mock_size_override_callback(ord):
        return {
            "confirmed": True,
            "size_pct_override": 0.05,  # 操盘手觉得风险偏高，缩容到 5%
            "override_reason": "Trader manual risk reduction"
        }
    
    confirm_adapter.set_confirm_callback(mock_size_override_callback)
    
    order3 = ApprovedOrder(
        order_id="order-003",
        code="601318",
        action="BUY",
        size_pct=0.15,
        price=50.0,
        stop_price=48.0,
    )
    
    success = confirm_adapter.submit_order(order3)
    assert success
    assert len(paper_adapter.orders) == 3
    # 底层收到的执行订单，下单尺寸应当是操盘手 override 修改后的 5%！
    assert paper_adapter.orders[2]["code"] == "601318"
    assert paper_adapter.orders[2]["size_pct"] == 0.05
    assert paper_adapter.orders[2]["order_id"] == "order-003-override"

    # 核验 override 修改尺寸后的 Journal 审计记录
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 3
        audit = json.loads(lines[2])
        assert audit["confirmed"] is True
        assert audit["override_reason"] == "Trader manual risk reduction"
        assert audit["actual_order_id"] == "order-003-override"
        assert audit["override_metadata"]["size_changed"] is True
        assert audit["override_metadata"]["original_size_pct"] == 0.15
        assert audit["override_metadata"]["actual_size_pct"] == 0.05

    # 6. 测试场景：CONFIRM 模式下，操盘手主动拒绝/撤回
    def mock_rejected_callback(ord):
        return {
            "confirmed": False,
            "size_pct_override": None,
            "override_reason": "Trader clicked Cancel button"
        }
        
    confirm_adapter.set_confirm_callback(mock_rejected_callback)
    
    order4 = ApprovedOrder(
        order_id="order-004",
        code="300750",
        action="BUY",
        size_pct=0.20,
        price=350.0,
        stop_price=330.0,
    )
    
    success = confirm_adapter.submit_order(order4)
    assert not success
    assert len(paper_adapter.orders) == 3  # 底层成交量没有增加

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 4
        audit = json.loads(lines[3])
        assert audit["confirmed"] is False
        assert audit["override_reason"] == "Trader clicked Cancel button"
        assert audit["actual_order_id"] == "order-004"
