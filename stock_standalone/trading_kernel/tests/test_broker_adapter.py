# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import pytest
from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.execution.broker_adapter import (
    KillSwitch,
    OrderIdempotencyManager,
    BrokerPositionSync,
    BrokerExecutionAdapter,
)
from trading_kernel.observability.journal import JsonlJournal


def test_kill_switch_dual_protection():
    """测试紧急切断开关：内存软判定与磁盘硬判定双重阻断防线"""
    switch_file = ".test_kill_switch"
    ks = KillSwitch(check_file_path=switch_file)
    
    try:
        # 初始未切断
        assert not ks.is_killed()

        # 1. 内存软开关触发
        ks._memory_killed = True
        assert ks.is_killed()
        
        # 恢复内存开关
        ks._memory_killed = False
        assert not ks.is_killed()

        # 2. 物理磁盘硬开关触发
        ks.activate()
        assert ks.is_killed()
        assert os.path.exists(switch_file)

        # 3. 解除开关
        ks.deactivate()
        assert not ks.is_killed()
        assert not os.path.exists(switch_file)

    finally:
        if os.path.exists(switch_file):
            os.remove(switch_file)


def test_order_idempotency_prevention():
    """测试订单幂等管理器：防止多进程高频重入双发单子"""
    im = OrderIdempotencyManager(expiry_seconds=1.0)
    order_id = "test-uuid-9999"

    # 首次提交通过
    assert not im.is_duplicate(order_id)
    im.mark_submitted(order_id)

    # 重复提交被强力拦截
    assert im.is_duplicate(order_id)
    
    # 模拟超时过期后释放
    import time
    time.sleep(1.1)
    # 过期后允许重新放行
    assert not im.is_duplicate(order_id)


def test_broker_position_reconciliation(tmp_path):
    """测试柜台持仓/资产同步比对与异常审计记录"""
    log_file = os.path.join(tmp_path, "sync_audit.jsonl")
    journal = JsonlJournal(log_file)
    sync = BrokerPositionSync(journal=journal)

    local_positions = {
        "600519": {"volume": 200, "entry_price": 1850.50},
        "000001": {"volume": 1000, "entry_price": 10.20},
    }

    # 1. 完美匹配状态
    broker_perfect = {
        "600519": {"volume": 200, "entry_price": 1850.50},
        "000001": {"volume": 1000, "entry_price": 10.20},
    }
    match, report = sync.sync_and_verify(local_positions, broker_perfect)
    assert match
    assert len(report["added"]) == 0
    assert len(report["removed"]) == 0
    assert len(report["modified"]) == 0

    # 2. 柜台相比于本地，持仓数量或价格漂移
    broker_drift = {
        "600519": {"volume": 200, "entry_price": 1850.50},
        "000001": {"volume": 800, "entry_price": 10.20}, # 仓位少了 200 股
    }
    match, report = sync.sync_and_verify(local_positions, broker_drift)
    assert not match
    assert len(report["modified"]) == 1
    assert report["modified"][0]["code"] == "000001"

    # 核对追溯审计写入
    with open(log_file, "r", encoding="utf-8") as f:
        records = f.readlines()
        assert len(records) == 1 # 记入了同步异常审计
        import json
        audit = json.loads(records[0])
        assert audit["journal_type"] == "POSITION_SYNC_AUDIT"
        assert len(audit["drift_report"]["modified"]) == 1


def test_broker_adapter_gatekeepers(tmp_path):
    """测试实盘柜台适配器核心防护关卡集成"""
    log_file = os.path.join(tmp_path, "live_broker.jsonl")
    journal = JsonlJournal(log_file)
    switch_file = os.path.join(tmp_path, ".test_broker_kill")
    
    ks = KillSwitch(check_file_path=switch_file)
    im = OrderIdempotencyManager()
    
    adapter = BrokerExecutionAdapter(
        journal=journal,
        kill_switch=ks,
        idempotency_manager=im,
    )

    order = ApprovedOrder(
        order_id="live-order-1",
        code="600519",
        action="BUY",
        size_pct=0.1,
        price=1850.0,
        stop_price=0.0,
    )

    try:
        # 1. 正常连接与下单成功
        assert adapter.submit_order(order)

        # 2. 幂等拦截第二次相同 order_id 提交
        assert not adapter.submit_order(order)

        # 3. 重置新订单，断开柜台连接进行拦截测试
        order2 = ApprovedOrder(
            order_id="live-order-2",
            code="600519",
            action="BUY",
            size_pct=0.1,
            price=1850.0,
            stop_price=0.0,
        )
        adapter.set_connected(False)
        assert not adapter.submit_order(order2)

        # 4. 恢复柜台连接，激活 KillSwitch 进行紧急切断测试
        adapter.set_connected(True)
        ks.activate()
        assert not adapter.submit_order(order2)

    finally:
        ks.deactivate()
        if os.path.exists(switch_file):
            os.remove(switch_file)
