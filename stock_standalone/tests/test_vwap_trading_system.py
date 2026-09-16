# -*- coding: utf-8 -*-
"""
tests/test_vwap_trading_system.py
---------------------------------
分时多周期交易执行系统核心引擎全链路测试套件：
1. ProactiveExitEngine 8层防守出局守护测试
2. ConsensusArbiter 共享仓位池与双组投票仲裁机制测试 (严进宽出 + 犹豫期一票否决)
3. VWAPTradingEngine 状态计算与形态清晰度评估测试
4. MarketGuardian 宏观大盘与板块风控测试
"""

import time
import pytest
from typing import Dict, Any

from ats.vwap_rule_model import VWAPRuleModel
from ats.proactive_exit_engine import ProactiveExitEngine, ExitAction
from ats.consensus_arbiter import ConsensusArbiter, SharedPositionState, VoteResult, ArbiterDecision
from ats.vwap_trading_engine import VWAPTradingEngine, VWAPTickState
from ats.market_guardian import MarketGuardian, GuardianVerdict


# -----------------------------------------------------------------------------
# 1. ProactiveExitEngine 8层主动出局守护测试
# -----------------------------------------------------------------------------
def test_proactive_exit_layer1_time_decay():
    """测试 Layer 1: 时间衰减止损"""
    engine = ProactiveExitEngine()
    now = time.time()
    
    # 注册标的，买入价 10.00
    pos = engine.register_position(code="600733", entry_price=10.00, entry_time=now)
    
    # 5分钟内涨幅0，不触发
    act = engine.evaluate_tick("600733", price=10.00, vwap_today=10.00, volume=100, current_time=now + 300)
    assert act is None
    
    # 20分钟涨幅不足 0.3% -> 触发 REDUCE_HALF
    act2 = engine.evaluate_tick("600733", price=10.01, vwap_today=10.00, volume=100, current_time=now + 1205)
    assert act2 is not None
    assert act2.layer == 1
    assert act2.action_type == "REDUCE_HALF"
    assert "不及预期减半" in act2.rule_name
    
    # 30分钟仍处于浮亏 (9.95) -> 触发 EXIT_ALL
    act3 = engine.evaluate_tick("600733", price=9.95, vwap_today=10.00, volume=100, current_time=now + 1805)
    assert act3 is not None
    assert act3.layer == 1
    assert act3.action_type == "EXIT_ALL"
    assert "超时浮亏清仓" in act3.rule_name


def test_proactive_exit_layer3_failed_rally_600733():
    """测试 Layer 3: 反弹前高不过 (600733 假反弹克星)"""
    engine = ProactiveExitEngine()
    now = time.time()
    
    # 假设前日高点为 10.50，买入价 10.00
    pos = engine.register_position(
        code="600733",
        entry_price=10.00,
        entry_time=now,
        prev_day_high=10.50,
    )
    
    # 价格反弹冲击 10.48 (接近 10.50 阻力区)，但缩量徘徊 (量比 0.7)
    # 模拟在阻力位徘徊 45 个 tick (累积超过 120 秒)
    for i in range(45):
        act = engine.evaluate_tick(
            code="600733",
            price=10.48,
            vwap_today=10.20,
            volume=50,
            volume_ratio=0.6,
            current_time=now + (i * 3),
        )
        if act is not None:
            break
            
    assert act is not None
    assert act.layer == 3
    assert act.action_type in ("REDUCE_HALF", "EXIT_ALL")
    assert "反弹前高不过" in act.rule_name
    assert "10.50" in act.reason


def test_proactive_exit_layer3_retreat_exit():
    """测试 Layer 3: 遇阻后快速回撤超过 1.5% 强制清仓"""
    engine = ProactiveExitEngine()
    now = time.time()
    pos = engine.register_position(code="600733", entry_price=10.00, entry_time=now, prev_day_high=10.50)
    
    # 价格摸到 10.52 (高位)
    engine.evaluate_tick("600733", price=10.52, vwap_today=10.20, volume=100, volume_ratio=1.2, current_time=now + 60)
    
    # 价格快速砸回 10.30 (从 10.52 回撤超过 2.0% > 1.5% 清仓线)
    act = engine.evaluate_tick("600733", price=10.30, vwap_today=10.20, volume=100, volume_ratio=1.0, current_time=now + 120)
    assert act is not None
    assert act.layer == 3
    assert act.action_type == "EXIT_ALL"
    assert "遇阻回落清仓" in act.rule_name


def test_proactive_exit_layer7_ma5d_rollover():
    """测试 Layer 7: 大级别 MA5d 拐头，分时反抽 VWAP 即刻出清"""
    engine = ProactiveExitEngine()
    now = time.time()
    engine.register_position(code="600733", entry_price=10.00, entry_time=now)
    
    # 模拟日线 MA5 走坏 (10.20 < 10.50)，60分通道斜率 -10度，价格跌破 MA5 (9.80 < 10.20)
    # 当分时价格反抽到 VWAP 附近 (9.80 与 VWAP 9.80 对齐)
    extra_ctx = {
        "ma5d": 10.20,
        "ma5d_prev5": 10.50,
        "channel_slope_60m": -10.5,
    }
    act = engine.evaluate_tick(
        code="600733",
        price=9.80,
        vwap_today=9.80,
        volume=100,
        current_time=now + 60,
        extra_ctx=extra_ctx,
    )
    assert act is not None
    assert act.layer == 7
    assert act.action_type == "EXIT_ALL"
    assert "大级别MA5d拐头" in act.rule_name


def test_proactive_exit_layer8_vwap_breakdown():
    """测试 Layer 8: VWAP 破位最后防线"""
    engine = ProactiveExitEngine()
    now = time.time()
    engine.register_position(code="600733", entry_price=10.00, entry_time=now)
    
    # 持续跌破今日均价 VWAP 10.00 (价格 9.90)，模拟连续 105 个 tick
    act = None
    for i in range(105):
        act = engine.evaluate_tick(
            code="600733",
            price=9.90,
            vwap_today=10.00,
            volume=50,
            current_time=now + (i * 3),
        )
        if act is not None:
            break
            
    assert act is not None
    assert act.layer == 8
    assert act.action_type == "EXIT_ALL"
    assert "VWAP破位兜底" in act.rule_name


# -----------------------------------------------------------------------------
# 2. ConsensusArbiter 仓位管理与双组投票测试
# -----------------------------------------------------------------------------
def test_consensus_arbiter_dual_consent_success():
    """测试双组一致同意 (Dual Consent) 顺利批准开仓"""
    arbiter = ConsensusArbiter()
    
    agg_vote = VoteResult(
        voter_group="aggressive",
        decision="APPROVE",
        proposed_size_pct=0.15,
        rule_id="buy_vwap_base_breakout",
        rule_name="VWAP筑底突破",
    )
    con_vote = VoteResult(
        voter_group="conservative",
        decision="APPROVE",
        proposed_size_pct=0.10,
        structure_clarity_score=88.0,
        is_hesitation_period=False,
    )
    
    decision = arbiter.arbitrate_buy("301531", agg_vote, con_vote)
    assert decision.allow is True
    assert decision.action == "BUY_SCOUT"
    assert decision.size_pct == 0.10  # 取保守较小值
    assert decision.is_vetoed is False
    assert "双组共识达成" in decision.reason


def test_consensus_arbiter_conservative_veto_on_hesitation():
    """测试保守组在多空犹豫期行使一票否决权"""
    arbiter = ConsensusArbiter()
    
    agg_vote = VoteResult(
        voter_group="aggressive",
        decision="APPROVE",
        proposed_size_pct=0.15,
        rule_id="buy_vwap_base_breakout",
        rule_name="VWAP筑底突破",
    )
    con_vote = VoteResult(
        voter_group="conservative",
        decision="HESITATE",
        structure_clarity_score=75.0,
        is_hesitation_period=True,
        hesitation_details="近10分钟十字星占比50%，缺乏合力",
    )
    
    decision = arbiter.arbitrate_buy("600733", agg_vote, con_vote)
    assert decision.allow is False
    assert decision.action == "HOLD"
    assert decision.is_vetoed is True
    assert decision.veto_by == "conservative_guard"
    assert "犹豫期" in decision.reason


def test_consensus_arbiter_conservative_veto_on_low_clarity():
    """测试保守组在分时结构混乱时行使一票否决权"""
    arbiter = ConsensusArbiter()
    
    agg_vote = VoteResult(
        voter_group="aggressive",
        decision="APPROVE",
        proposed_size_pct=0.15,
        rule_id="buy_vwap_base_breakout",
    )
    con_vote = VoteResult(
        voter_group="conservative",
        decision="REJECT",
        structure_clarity_score=55.0,  # 低于 70 门槛
        is_hesitation_period=False,
    )
    
    decision = arbiter.arbitrate_buy("600733", agg_vote, con_vote)
    assert decision.allow is False
    assert decision.is_vetoed is True
    assert "清晰度" in decision.reason


def test_consensus_arbiter_fast_exit():
    """测试宽出机制：防守出局一票执行，无需协商"""
    arbiter = ConsensusArbiter()
    
    # 模拟先开仓 1000 股
    arbiter.record_trade_execution("600733", action="BUY_SCOUT", price=10.00, shares=1000)
    pos = arbiter.get_or_create_position("600733")
    assert pos.shares == 1000
    
    # 8层守护发出清仓指令
    proactive_exit = ExitAction(
        code="600733",
        rule_id="exit_failed_rally",
        rule_name="反弹前高不过",
        layer=3,
        action_type="EXIT_ALL",
        size_pct=1.0,
        trigger_price=10.30,
        reason="遇阻回落",
        timestamp=time.time(),
    )
    
    decision = arbiter.arbitrate_exit("600733", proactive_exit=proactive_exit)
    assert decision.allow is True
    assert decision.action == "EXIT_ALL"
    assert "8层出局守护" in decision.reason
    
    # 执行清仓撮合
    arbiter.record_trade_execution("600733", action="EXIT_ALL", price=10.30, shares=1000)
    assert pos.shares == 0
    assert pos.status == "CLOSED"
    assert pos.realized_pnl == pytest.approx(300.0)  # (10.30 - 10.00) * 1000


# -----------------------------------------------------------------------------
# 3. VWAPTradingEngine 状态与形态指标测试
# -----------------------------------------------------------------------------
def test_vwap_trading_engine_clarity_and_hesitation():
    """测试 VWAPTradingEngine 对十字星密集与锯齿拉锯形态的自动识别"""
    engine = VWAPTradingEngine()
    now = time.time()
    
    # 构造 10 根十字星多空拉锯 K 线 (实体极小，上下影线频繁反转)
    for i in range(10):
        # 十字星: open=10.00, close=10.005, high=10.05, low=9.95
        engine.update_minute_bar(
            code="600733",
            bar_time=now + (i * 60),
            open_=10.00 if i % 2 == 0 else 10.005,
            high=10.05,
            low=9.95,
            close=10.005 if i % 2 == 0 else 10.00,
            volume=500,
            vwap=10.00,
        )
        
    state = engine.compute_tick_state("600733", price=10.00, vwap_today=10.00)
    assert state.is_hesitation_period is True
    assert "十字星" in state.hesitation_reason
    assert state.structure_clarity_score < 70.0


# -----------------------------------------------------------------------------
# 4. MarketGuardian 宏观大盘风控测试
# -----------------------------------------------------------------------------
def test_market_guardian_panic_and_freeze():
    """测试 MarketGuardian 恐慌熔断与冻结买入"""
    guardian = MarketGuardian()
    
    # 模拟大盘暴跌：下跌 4200 家，跌停 35 家，情绪 PANIC
    verdict = guardian.evaluate_market_state(
        up_count=600,
        down_count=4200,
        limit_up_count=8,
        limit_down_count=35,
        market_sentiment="PANIC",
    )
    
    assert verdict.buy_allowed is False
    assert verdict.sell_urgency == "EXIT_ALL"
    assert verdict.freeze_buy is True
    assert "大盘极端恐慌杀跌" in verdict.reason
    
    allowed, reason = guardian.is_buy_permitted_for_stock()
    assert allowed is False


# -----------------------------------------------------------------------------
# 5. SignalAutoDispatcher 统一信号调度器全流程测试
# -----------------------------------------------------------------------------
def test_signal_auto_dispatcher_flow():
    """测试统一调度器: 行情接入 -> 双组投票买入 -> 持仓守护 -> 8层主动出局"""
    from ats.signal_auto_dispatcher import SignalAutoDispatcher
    import pandas as pd

    dispatcher = SignalAutoDispatcher()
    now = time.time()
    code = "600733"

    # 1. 初始状态无持仓，行情不符合条件时 HOLD
    res1 = dispatcher.dispatch_tick(code, price=10.0, vwap=10.0, volume=100, timestamp=now)
    assert res1.action == "HOLD"
    assert res1.is_buy is False

    # 2. 模拟分时筑底放量突破，触发展开开仓
    for i in range(15):
        dispatcher.vwap_engine.update_minute_bar(
            code=code,
            bar_time=now + i * 60,
            open_=9.95,
            high=10.05,
            low=9.92,
            close=10.02,
            volume=1500,
            vwap=9.98
        )
    # 模拟突破 VWAP
    res_buy = dispatcher.dispatch_tick(
        code,
        price=10.15,
        vwap=10.00,
        volume=2500,
        timestamp=now + 1000,
        extra_ctx={"volume_ratio": 1.5, "multi_period_score": 80.0}
    )
    if res_buy.is_buy:
        assert res_buy.shares > 0
        assert dispatcher.arbiter.get_or_create_position(code).has_position

        # 3. 产生持仓后，模拟价格冲高后回撤，触发 L4 或 L3 保护
        res_exit = dispatcher.dispatch_tick(
            code,
            price=9.70,
            vwap=10.00,
            volume=500,
            timestamp=now + 3000,
            extra_ctx={"volume_ratio": 0.8}
        )
        assert res_exit.is_exit is True
        assert res_exit.layer > 0


def test_signal_auto_dispatcher_backtest_df():
    """测试统一调度器在 DataFrame 历史走势上的跑测"""
    from ats.signal_auto_dispatcher import SignalAutoDispatcher
    import pandas as pd

    dispatcher = SignalAutoDispatcher()
    dates = pd.date_range("2026-09-15 09:30", periods=60, freq="1min")
    data = []
    p = 10.0
    for d in dates:
        p += 0.02
        data.append({
            "open": p - 0.01,
            "high": p + 0.03,
            "low": p - 0.02,
            "close": p,
            "vol": 1200,
            "vwap": p - 0.01
        })
    df = pd.DataFrame(data, index=dates)

    sigs = dispatcher.run_backtest_on_dataframe("600733", df)
    assert isinstance(sigs, list)

