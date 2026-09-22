# -*- coding: utf-8 -*-
"""
tests/test_tradeplan_structural_rr.py
-------------------------------------
S4 TradePlan 结构锚点与动态 RR 计算纯函数契约测试 (Task 019)
验证:
1. CHANNEL_SECONDARY_BUY 生成的 IPOTradePlan 固定 signal_level=S4。
2. 只读 structural_stop -> higher_low_stop 与 structural_target -> target_1_channel_mid。
3. calculate_rr_now 小型纯函数及边界校验 (price<=stop, target<=price, target<=stop, 非数值)。
4. structural_stop / target 锚点不可变性 (不因算 RR 移动锚点)。
5. buy_zone_max 生成时不得超过 trigger_price * 1.015。
"""

import pytest
import math
import numpy as np
import pandas as pd

from ats.strategy.channel_secondary_buy_strategy import (
    IPOTradePlan,
    TAG_CHANNEL_SECONDARY_BUY,
    calculate_rr_now,
    evaluate_channel_secondary_buy,
    SecondaryBuyStage,
)


def test_ipo_trade_plan_signal_level_fixed_s4():
    """测试 IPOTradePlan 在 CHANNEL_SECONDARY_BUY 策略下固定 signal_level='S4'"""
    # 默认实例
    p1 = IPOTradePlan()
    assert p1.signal_level == "S4"
    assert p1.strategy_tag == TAG_CHANNEL_SECONDARY_BUY

    # 尝试指定非 S4 等级
    p2 = IPOTradePlan(strategy_tag=TAG_CHANNEL_SECONDARY_BUY, signal_level="S2")
    assert p2.signal_level == "S4", "CHANNEL_SECONDARY_BUY 的 TradePlan 必须保持 S4"

    # 非 CHANNEL_SECONDARY_BUY 策略 tag 保持原设计
    p3 = IPOTradePlan(strategy_tag="OTHER_STRATEGY", signal_level="S2")
    assert p3.signal_level == "S2"


def test_structural_anchors_mapping():
    """测试 structural_stop 和 structural_target 映射至核心防守位与目标位"""
    plan = IPOTradePlan(
        higher_low_stop=52.3,
        target_1_channel_mid=68.5,
    )
    assert plan.structural_stop == 52.3
    assert plan.structural_target == 68.5

    # 支持字典形式访问与 get 方法
    assert plan["structural_stop"] == 52.3
    assert plan["structural_target"] == 68.5
    assert plan.get("structural_stop") == 52.3
    assert plan.get("structural_target") == 68.5


def test_structural_anchors_readonly():
    """测试 structural_stop 和 structural_target 为只读属性，禁止直接修改"""
    plan = IPOTradePlan(
        higher_low_stop=50.0,
        target_1_channel_mid=65.0,
    )
    with pytest.raises(AttributeError):
        plan.structural_stop = 55.0

    with pytest.raises(AttributeError):
        plan.structural_target = 70.0

    with pytest.raises(AttributeError):
        plan["structural_stop"] = 55.0

    with pytest.raises(AttributeError):
        plan["structural_target"] = 70.0


def test_calculate_rr_now_valid():
    """测试 calculate_rr_now 正常合法输入计算: RR = (target - price) / (price - stop)"""
    plan = IPOTradePlan(
        higher_low_stop=100.0,
        target_1_channel_mid=120.0,
    )

    # 现价 110: (120 - 110) / (110 - 100) = 10 / 10 = 1.0
    rr_110 = calculate_rr_now(110.0, plan)
    assert rr_110 == pytest.approx(1.0)
    assert plan.calculate_rr_now(110.0) == pytest.approx(1.0)

    # 现价 105: (120 - 105) / (105 - 100) = 15 / 5 = 3.0
    rr_105 = calculate_rr_now(105.0, plan)
    assert rr_105 == pytest.approx(3.0)

    # 现价 115: (120 - 115) / (115 - 100) = 5 / 15 = 1/3
    rr_115 = calculate_rr_now(115.0, plan)
    assert rr_115 == pytest.approx(1.0 / 3.0)

    # 支持字典结构入参
    dict_plan = {"structural_stop": 100.0, "structural_target": 120.0}
    assert calculate_rr_now(110.0, dict_plan) == pytest.approx(1.0)

    # 支持以 higher_low_stop / target_1_channel_mid 回退键名的字典入参
    dict_plan_fallback = {"higher_low_stop": 100.0, "target_1_channel_mid": 120.0}
    assert calculate_rr_now(110.0, dict_plan_fallback) == pytest.approx(1.0)

    # 支持 (plan, price) 参数位置逆序容错
    assert calculate_rr_now(plan, 110.0) == pytest.approx(1.0)


def test_calculate_rr_now_does_not_mutate_anchors():
    """测试 calculate_rr_now 纯函数执行绝不篡改 plan 上的锚点 (不为达标移动锚点)"""
    plan = IPOTradePlan(
        higher_low_stop=95.0,
        target_1_channel_mid=110.0,
    )
    original_stop = plan.higher_low_stop
    original_target = plan.target_1_channel_mid

    _ = calculate_rr_now(100.0, plan)
    _ = calculate_rr_now(90.0, plan)  # 即使无效现价
    _ = calculate_rr_now(120.0, plan) # 即使无效现价

    assert plan.higher_low_stop == original_stop
    assert plan.target_1_channel_mid == original_target
    assert plan.structural_stop == original_stop
    assert plan.structural_target == original_target


def test_calculate_rr_now_boundary_price_le_stop():
    """边界测试: price <= stop 时明确不可执行，返回 None"""
    plan = IPOTradePlan(
        higher_low_stop=100.0,
        target_1_channel_mid=120.0,
    )
    # price == stop
    assert calculate_rr_now(100.0, plan) is None
    # price < stop
    assert calculate_rr_now(99.99, plan) is None
    assert calculate_rr_now(80.0, plan) is None


def test_calculate_rr_now_boundary_target_le_price():
    """边界测试: target <= price 时明确不可执行，返回 None"""
    plan = IPOTradePlan(
        higher_low_stop=100.0,
        target_1_channel_mid=120.0,
    )
    # price == target
    assert calculate_rr_now(120.0, plan) is None
    # price > target
    assert calculate_rr_now(120.01, plan) is None
    assert calculate_rr_now(150.0, plan) is None


def test_calculate_rr_now_boundary_target_le_stop():
    """边界测试: target <= stop 倒置或相等时明确不可执行，返回 None"""
    # target == stop
    plan_eq = IPOTradePlan(higher_low_stop=100.0, target_1_channel_mid=100.0)
    assert calculate_rr_now(100.0, plan_eq) is None
    assert calculate_rr_now(95.0, plan_eq) is None

    # target < stop (倒置)
    plan_inv = IPOTradePlan(higher_low_stop=100.0, target_1_channel_mid=80.0)
    assert calculate_rr_now(90.0, plan_inv) is None
    assert calculate_rr_now(70.0, plan_inv) is None


def test_calculate_rr_now_non_numeric_inputs():
    """测试非数值输入时明确返回 None"""
    plan = IPOTradePlan(
        higher_low_stop=100.0,
        target_1_channel_mid=120.0,
    )
    # price 为非数值
    assert calculate_rr_now(None, plan) is None
    assert calculate_rr_now("110", plan) is None
    assert calculate_rr_now("invalid", plan) is None
    assert calculate_rr_now(True, plan) is None
    assert calculate_rr_now(False, plan) is None
    assert calculate_rr_now(float("nan"), plan) is None
    assert calculate_rr_now(float("inf"), plan) is None
    assert calculate_rr_now(-float("inf"), plan) is None
    assert calculate_rr_now([110.0], plan) is None
    assert calculate_rr_now({"price": 110.0}, plan) is None

    # plan 为 None 或缺失/非法锚点
    assert calculate_rr_now(110.0, None) is None
    assert calculate_rr_now(110.0, {}) is None
    assert calculate_rr_now(110.0, {"structural_stop": None, "structural_target": 120.0}) is None
    assert calculate_rr_now(110.0, {"structural_stop": "100", "structural_target": 120.0}) is None
    assert calculate_rr_now(110.0, {"structural_stop": 100.0, "structural_target": float("nan")}) is None
    assert calculate_rr_now(110.0, {"structural_stop": 100.0, "structural_target": float("inf")}) is None


def test_buy_zone_max_capping():
    """测试 buy_zone_max 生成时不得超过 trigger_price * 1.015"""
    # 显式传入超过 1.5% 阈值的 buy_zone_max
    plan_overflow = IPOTradePlan(
        trigger_price=100.0,
        buy_zone_max=103.0,
    )
    assert plan_overflow.buy_zone_max <= 100.0 * 1.015 + 1e-6
    assert plan_overflow.buy_zone_max == pytest.approx(101.5)

    # 显式传入边界值 1.5%
    plan_exact = IPOTradePlan(
        trigger_price=100.0,
        buy_zone_max=101.5,
    )
    assert plan_exact.buy_zone_max == pytest.approx(101.5)

    # 显式传入小于 1.5% 的安全值
    plan_safe = IPOTradePlan(
        trigger_price=100.0,
        buy_zone_max=100.8,
    )
    assert plan_safe.buy_zone_max == pytest.approx(100.8)


def test_evaluate_secondary_buy_generates_s4_and_capped_buy_zone_max():
    """测试 evaluate_channel_secondary_buy 生成的 trade_plan 满足所有合同规范"""
    # 构造能够触发 SECONDARY_BUY (S4) 的合成 60F K 线
    # 结构步骤:
    # 1. 前 30 根长期下行斜率趋平
    # 2. base_low 在索引 35，价格 20.0
    # 3. 首次突破波峰 (first_breakout) 达到 22.0 (在索引 42)
    # 4. 缩量回踩次低点 (higher_low) 21.0 > base_low 20.0 (在索引 47)
    # 5. 最新现价 22.2 放量突破次级确认线
    n_bars = 50
    closes = np.linspace(25.0, 20.5, 30).tolist() # 前30根下行走平
    closes += [20.2, 20.1, 20.05, 20.0, 20.0]     # base_low = 20.0
    closes += [20.8, 21.5, 22.0, 21.8]            # first breakout = 22.0
    closes += [21.4, 21.3, 21.2, 21.1, 21.0, 21.1, 21.2] # pullback higher_low = 21.0 (7根缩量回踩)
    closes += [21.6, 21.8, 22.0, 22.2]            # secondary buy break

    highs = [c + 0.3 for c in closes]
    lows = [c - 0.3 for c in closes]
    opens = [c - 0.1 for c in closes]
    vols = [10000.0] * 35 + [15000.0] * 4 + [3000.0] * 7 + [12000.0] * 4

    assert len(closes) == n_bars
    assert len(vols) == n_bars

    df_60m = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "vol": vols,
    })

    result = evaluate_channel_secondary_buy(
        df_60m=df_60m,
        code="688826",
        name="测试次新",
    )

    assert result.get("trade_plan") is not None, f"Expected trade_plan, got stage={result.get('stage')}, reason={result.get('reason')}"
    plan = result["trade_plan"]
    assert plan.signal_level == "S4"
    assert plan.strategy_tag == TAG_CHANNEL_SECONDARY_BUY
    assert plan.buy_zone_max <= plan.trigger_price * 1.015 + 1e-6
    assert plan.structural_stop == plan.higher_low_stop
    assert plan.structural_target == plan.target_1_channel_mid

    rr = calculate_rr_now(plan.trigger_price, plan)
    assert rr is not None
    assert rr > 0
