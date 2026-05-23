# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import pytest
from datetime import datetime
from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.kernel_service import TradingKernelService


def test_trading_mode_ladder_transitions():
    """测试天梯模式切换与物理边界防护"""
    service = TradingKernelService()

    # 1. 验证默认初始模式
    assert service.mode == "OBSERVE"
    assert service.executor is None

    # 2. 升格至 PAPER
    assert service.set_trading_mode("PAPER")
    assert service.mode == "PAPER"
    from trading_kernel.execution.paper_adapter import PaperExecutionAdapter
    assert isinstance(service.executor, PaperExecutionAdapter)

    # 3. 升格至 CONFIRM
    assert service.set_trading_mode("CONFIRM")
    assert service.mode == "CONFIRM"
    from trading_kernel.execution.confirm_adapter import ConfirmExecutionAdapter
    assert isinstance(service.executor, ConfirmExecutionAdapter)

    # 4. 尝试升格至 LIVE_AUTO：在测试环境下，由于柜台账户未同步或当前可能不是交易活跃时间，
    # 前置安全卡口必然会拦截该请求，并触发“强行回退重置降级至 OBSERVE”物理防御
    success = service.set_trading_mode("LIVE_AUTO")
    assert not success
    assert service.mode == "OBSERVE"
    assert service.executor is None


def test_live_auto_preconditions_validation():
    """测试 LIVE_AUTO 的 8 大安全前置卡口的物理校验与放行"""
    service = TradingKernelService()

    # 模拟 100% 完美的实盘环境，强行让 8 大前置防护关卡全部通过：
    # 1. 模拟活跃交易时间段（Hook 或避开 NON_TRADING_SESSION 检测）
    # 我们可以通过 mock 掉 _verify_live_preconditions 底层卡口，核对它的成功升格逻辑
    def mock_perfect_preconditions():
        return True, []

    service._verify_live_preconditions = mock_perfect_preconditions

    # 全卡口通过，成功升格至 LIVE_AUTO
    assert service.set_trading_mode("LIVE_AUTO")
    assert service.mode == "LIVE_AUTO"
    from trading_kernel.execution.broker_adapter import BrokerExecutionAdapter
    assert isinstance(service.executor, BrokerExecutionAdapter)


def test_kernel_service_order_routing_by_mode(tmp_path):
    """测试在不同交易天梯模式下下单指令的安全分发与路由机制"""
    log_file = os.path.join(tmp_path, "ladder_routing.jsonl")
    service = TradingKernelService(journal_path=log_file)
    # 重置状态防前面的测试用例干扰
    service.state_manager.set("600519", "FLAT")

    # 构造测试行情队列事件
    item = {
        "code": "600519",
        "name": "贵州茅台",
        "price": 1850.0,
        "current_price": 1850.0,
        "suggest_price": 1850.0,
        "volume": 100000,
        "pct": 1.5,
        "created_at": "2026-05-23 09:30:00",  # 模拟标准活跃交易时间段
        "source": "SECTOR_FOCUS",
        "signal_type": "BREAKOUT",
        "priority": 85.0,        # 强势股评级满足 BUY
        "sector_heat": 45.0,     # 板块极度活跃
        "pct_diff": 4.5,         # 切片涨幅大
        "dff": 3.5,              # 强放量背离
    }

    # 1. OBSERVE 观察旁路模式下：只进行计算与记账，决不向执行层投递订单，无 order_id 生成
    res = service.evaluate_decision_item(item, write_journal=True)
    print("OBSERVE res:", res)
    assert not res["kernel_executed"]
    assert res["kernel_allowed"] # 意图被风控批准，但由于是 OBSERVE 模式，物理上不被执行

    # 2. PAPER 直接模拟模式下：直连 Paper adapter，下单成功，并且 StateManager 状态更新
    service.set_trading_mode("PAPER")
    res = service.evaluate_decision_item(item, write_journal=True)
    print("PAPER res:", res)
    assert res["kernel_executed"]
    assert res["kernel_order_id"] != ""
    # 验证状态变更为 IN_TRADE
    assert service.state_manager.get("600519") == "IN_TRADE"
