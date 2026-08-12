# -*- coding: utf-8 -*-
"""
tests/test_intraday_strategy_engine.py — ATS 单独分时交易策略引擎单元测试
验证：
1. 开盘价档位速查与策略自动选定；
2. 盘中时间轴阶段推算（9:15~9:25 竞价定盘、9:30~10:00 冲高卖、10:00~15:00 临停/持股、14:50~14:57 尾盘清仓）；
3. 条件触发评估与价格笼子限价单挂单比例；
4. 策略 JSON 配置落盘与读取。
"""

import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from ats.intraday_strategy_engine import IntradayStrategyEngine
from signal_types import SignalType, SignalSource

@pytest.fixture
def engine():
    eng = IntradayStrategyEngine.get_instance()
    eng.reset_state()
    return eng

def test_open_price_tier_classification(engine):
    """测试开盘价档位速查与策略选择"""
    engine.reset_state()
    tier_b, strat_b, mode_b = engine.get_open_price_tier(480.0)
    assert tier_b == "乐观档"
    assert strat_b == "strategy_b_new_stock_trend_hold"

    tier_a, strat_a, mode_a = engine.get_open_price_tier(350.0)
    assert tier_a == "中性档"
    assert strat_a == "strategy_a_new_stock_batch_sell"
    assert mode_a == "standard"

    tier_dec, strat_dec, mode_dec = engine.get_open_price_tier(300.0)
    assert tier_dec == "中性下沿"
    assert mode_dec == "decelerated"

    tier_hold, strat_hold, mode_hold = engine.get_open_price_tier(250.0)
    assert tier_hold == "保守档"
    assert mode_hold == "hold_rebound"

def test_time_axis_phase_inference(engine):
    """测试时间轴阶段推算"""
    engine.reset_state()
    strategy_a = engine.auto_select_strategy(350.0)

    ph_call, idx_0 = engine.get_current_phase("09:20", strategy_a)
    assert ph_call["phase_id"] == "call_auction"

    ph_surge, idx_1 = engine.get_current_phase("09:45", strategy_a)
    assert ph_surge["phase_id"] == "opening_surge"

    ph_halt, idx_2 = engine.get_current_phase("10:30", strategy_a)
    assert ph_halt["phase_id"] == "circuit_breaker"

    ph_clear, idx_3 = engine.get_current_phase("14:52", strategy_a)
    assert ph_clear["phase_id"] == "closing_clearance"

def test_surge_sell_rule_trigger(engine):
    """测试开盘冲高卖出 50% 与买一价*1.02限价单规则"""
    engine.reset_state()
    code = "920199"
    open_p = 350.0
    # 较开盘涨 10.28% (386元 >= 385元)
    tick_surge = {"trade": 386.0, "high": 386.0, "low": 350.0}

    signals = engine.evaluate_tick(
        code=code,
        tick_row=tick_surge,
        open_price=open_p,
        current_time_str="09:35",
        bid1_price=385.5,
        bar_index=15
    )

    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_type == SignalType.SELL
    assert getattr(sig, "sell_ratio") == 0.50
    # 买一价 385.5 * 1.02 = 393.21
    assert getattr(sig, "suggested_price") == round(385.5 * 1.02, 2)
    assert getattr(sig, "rule_id") == "rule_a1_surge"

def test_timeout_fallback_rule(engine):
    """测试 10:00 整超时未触发冲高兜底卖出 30% 规则"""
    engine.reset_state()
    code = "688787"
    open_p = 300.0 # 中性下沿

    # 09:50 价格平淡 (未达到 315元 +5%)
    sigs_quiet = engine.evaluate_tick(
        code=code,
        tick_row={"trade": 302.0, "high": 305.0, "low": 298.0},
        open_price=open_p,
        current_time_str="09:50",
        bar_index=20
    )
    assert len(sigs_quiet) == 0

    # 10:00 到达，触发超时兜底
    sigs_timeout = engine.evaluate_tick(
        code=code,
        tick_row={"trade": 303.0, "high": 305.0, "low": 298.0},
        open_price=open_p,
        current_time_str="10:00",
        bar_index=30
    )

    assert len(sigs_timeout) == 1
    sig_to = sigs_timeout[0]
    assert getattr(sig_to, "sell_ratio") == 0.30
    assert getattr(sig_to, "order_type") == "market_price"
    assert getattr(sig_to, "rule_id") == "rule_a1_timeout"

def test_circuit_breaker_rule(engine):
    """测试较开盘价 +30% 临停复牌卖出 30% 规则"""
    engine.reset_state()
    code = "920199"
    open_p = 350.0

    # 10:15 盘中急速飙升触及 +30% (455.0元 >= 350 * 1.30 = 455.0元)
    signals = engine.evaluate_tick(
        code=code,
        tick_row={"trade": 456.0, "high": 456.0, "low": 350.0},
        open_price=open_p,
        current_time_str="10:15",
        bar_index=45
    )

    assert len(signals) == 1
    sig_cb = signals[0]
    assert getattr(sig_cb, "sell_ratio") == 0.30
    assert getattr(sig_cb, "rule_id") == "rule_a2_halt_30"
    # 临停挂单 Open * 1.28 = 448.0
    assert getattr(sig_cb, "suggested_price") == round(350.0 * 1.28, 2)

def test_config_save_and_reload(engine):
    """测试自定制策略 JSON 落盘与重新加载"""
    engine.reset_state()
    original_strategies_count = len(engine.strategies)
    assert original_strategies_count >= 2

    # 验证保存并还原
    with open(engine.config_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    assert engine.save_config(content) is True
    assert len(engine.strategies) == original_strategies_count
