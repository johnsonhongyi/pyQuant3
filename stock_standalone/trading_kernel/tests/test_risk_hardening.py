from __future__ import annotations

import pytest
from trading_kernel.core.intent import DecisionIntent, DecisionReason
from trading_kernel.core.signal import StrategySignal
from trading_kernel.engine.risk_gate import RiskLimits, evaluate


@pytest.fixture
def mock_reason() -> DecisionReason:
    return DecisionReason(
        regime="bull",
        setup="breakout",
        sector_heat=0.85,
        sector_rank=1,
        is_leader=True,
        breakout=True,
        volume_ratio=2.5,
        dff=1.2,
        dff_positive=True,
        price_above_vwap=True,
        confidence_inputs=(("trend", 0.9), ("volume", 0.8)),
    )


@pytest.fixture
def mock_signal() -> StrategySignal:
    return StrategySignal(
        code="600519",
        name="贵州茅台",
        ts="2026-05-23T10:30:00",
        source="SinaBidding",
        signal_type="BiddingRacing",
        price=1800.0,
        features={"pct_diff": 2.5},
    )


@pytest.fixture
def mock_intent(mock_reason) -> DecisionIntent:
    return DecisionIntent(
        code="600519",
        action="BUY",
        size_pct=0.20,
        stop_price=1710.0,
        confidence=0.85,
        reason=mock_reason,
        expires_at="2026-05-23T10:35:00",
    )


def test_risk_gate_non_trading_session(mock_reason, mock_intent):
    # 非交易时段 23:30:00
    signal_night = StrategySignal(
        code="600519",
        name="贵州茅台",
        ts="2026-05-23T23:30:00",
        source="SinaBidding",
        signal_type="BiddingRacing",
        price=1800.0,
        features={"pct_diff": 2.5},
    )
    decision = evaluate(intent=mock_intent, signal=signal_night, state="OUT_OF_TRADE")
    assert not decision.allowed
    assert decision.final_action == "BLOCK"
    assert decision.reject_context["code"] == "NON_TRADING_SESSION"


def test_risk_gate_blacklist(mock_signal, mock_intent):
    limits = RiskLimits(blacklist=("600519", "000001"))
    decision = evaluate(intent=mock_intent, signal=mock_signal, state="OUT_OF_TRADE", limits=limits)
    assert not decision.allowed
    assert decision.reject_context["code"] == "BLACKLISTED_SYMBOL"


def test_risk_gate_expired_signal(mock_signal, mock_intent):
    # 信号在 10:30:00，当前已是 10:36:00 (差 360秒)
    decision = evaluate(
        intent=mock_intent,
        signal=mock_signal,
        state="OUT_OF_TRADE",
        current_time="2026-05-23T10:36:00",
    )
    assert not decision.allowed
    assert decision.reject_context["code"] == "SIGNAL_EXPIRED"
    assert decision.reject_context["diff_seconds"] == 360.0


def test_risk_gate_consecutive_losses_cooldown(mock_signal, mock_intent):
    # 已连续亏损 3 次，触发冷却拦截
    decision = evaluate(
        intent=mock_intent,
        signal=mock_signal,
        state="OUT_OF_TRADE",
        consecutive_losses=3,
    )
    assert not decision.allowed
    assert decision.reject_context["code"] == "CONSECUTIVE_LOSS_COOLDOWN"


def test_risk_gate_daily_loss_limit(mock_signal, mock_intent):
    # 今日累计已亏损超过限额
    limits = RiskLimits(daily_loss_limit_amount=10000.0)
    decision = evaluate(
        intent=mock_intent,
        signal=mock_signal,
        state="OUT_OF_TRADE",
        limits=limits,
        today_pnl_loss=12000.0,
    )
    assert not decision.allowed
    assert decision.reject_context["code"] == "DAILY_LOSS_LIMIT_EXCEEDED"


def test_risk_gate_high_extension_no_chase(mock_intent):
    # 涨幅偏离过高，比如当天已经涨了 8.5%，限制为 6.0%
    signal_high = StrategySignal(
        code="600519",
        name="贵州茅台",
        ts="2026-05-23T10:30:00",
        source="SinaBidding",
        signal_type="BiddingRacing",
        price=1800.0,
        features={"pct_diff": 8.5},
    )
    limits = RiskLimits(max_pct_diff=6.0)
    decision = evaluate(intent=mock_intent, signal=signal_high, state="OUT_OF_TRADE", limits=limits)
    assert not decision.allowed
    assert decision.reject_context["code"] == "HIGH_EXTENSION_NO_CHASE"


def test_risk_gate_single_stock_exposure_sizing(mock_signal, mock_intent):
    limits = RiskLimits(max_single_stock_position_pct=0.30)
    
    # Change action to ADD to test add sizing and exposure limits
    add_intent = DecisionIntent(
        code=mock_intent.code,
        action="ADD",
        size_pct=mock_intent.size_pct,
        stop_price=mock_intent.stop_price,
        confidence=mock_intent.confidence,
        reason=mock_intent.reason,
        expires_at=mock_intent.expires_at,
    )
    
    # 场景 A: 已持仓 15%，拟买入 20%，此时超过 30% 限制，应缩容买入 15%
    decision = evaluate(
        intent=add_intent,
        signal=mock_signal,
        state="IN_TRADE",
        limits=limits,
        current_stock_exposure=0.15,
    )
    assert decision.allowed
    assert decision.final_size_pct == 0.15
    assert decision.order.size_pct == 0.15

    # 场景 B: 已持仓已达到或超过 30%，应当彻底 BLOCK 拦截
    decision_block = evaluate(
        intent=add_intent,
        signal=mock_signal,
        state="IN_TRADE",
        limits=limits,
        current_stock_exposure=0.32,
    )
    assert not decision_block.allowed
    assert decision_block.reject_context["code"] == "SINGLE_STOCK_EXPOSURE_EXCEEDED"


def test_risk_gate_sector_exposure_sizing(mock_signal, mock_intent):
    limits = RiskLimits(max_single_sector_exposure_pct=0.50)
    
    # 板块已暴露 40%，拟买入 20% (总 60%)，应被缩容为最多买入 10%
    decision = evaluate(
        intent=mock_intent,
        signal=mock_signal,
        state="OUT_OF_TRADE",
        limits=limits,
        current_sector_exposure=0.40,
    )
    assert decision.allowed
    assert decision.final_size_pct == 0.10

    # 板块已暴露 55%，彻底拦截
    decision_block = evaluate(
        intent=mock_intent,
        signal=mock_signal,
        state="OUT_OF_TRADE",
        limits=limits,
        current_sector_exposure=0.55,
    )
    assert not decision_block.allowed
    assert decision_block.reject_context["code"] == "SECTOR_EXPOSURE_EXCEEDED"


def test_risk_gate_total_exposure_sizing(mock_signal, mock_intent):
    limits = RiskLimits(total_exposure_cap_pct=0.80)
    
    # 全局总仓位 75%，拟买 20%，应缩容为 5%
    decision = evaluate(
        intent=mock_intent,
        signal=mock_signal,
        state="OUT_OF_TRADE",
        limits=limits,
        current_total_exposure=0.75,
    )
    assert decision.allowed
    assert decision.final_size_pct == 0.05

    # 全局已满仓 85%，彻底拦截
    decision_block = evaluate(
        intent=mock_intent,
        signal=mock_signal,
        state="OUT_OF_TRADE",
        limits=limits,
        current_total_exposure=0.85,
    )
    assert not decision_block.allowed
    assert decision_block.reject_context["code"] == "TOTAL_EXPOSURE_EXCEEDED"


def test_risk_gate_stop_price_inheritance(mock_signal, mock_intent):
    decision = evaluate(intent=mock_intent, signal=mock_signal, state="OUT_OF_TRADE")
    assert decision.allowed
    assert decision.order.stop_price == 1710.0
