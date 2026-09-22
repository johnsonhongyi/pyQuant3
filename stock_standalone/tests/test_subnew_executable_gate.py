# -*- coding: utf-8 -*-
"""
tests/test_subnew_executable_gate.py
-----------------------------------
Task 023: S5 可执行准入门禁单元测试套件
"""

import copy
import json
import pytest

from ats.strategy.channel_secondary_buy_strategy import (
    IPOTradePlan,
    TAG_CHANNEL_SECONDARY_BUY,
)
from ats.strategy.subnew_executable_gate import (
    evaluate_s5_executable,
    S5ExecutableGateResult,
    REJECT_MARKET_BLOCKED,
    REJECT_INVALID_STRATEGY,
    REJECT_INVALID_SIGNAL_LEVEL,
    REJECT_INVALID_QUALITY_GRADE,
    REJECT_STRUCTURAL_INVALID,
    REJECT_PRICE_ABOVE_BUY_ZONE,
    REJECT_PRICE_BELOW_BUY_ZONE,
    REJECT_RR_BELOW_THRESHOLD,
    REJECT_TTL_TRADING_15M,
    REJECT_TTL_CROSS_DAY,
)


def _create_valid_s4_plan(**kwargs) -> IPOTradePlan:
    """Helper to build a standard compliant S4 IPOTradePlan."""
    defaults = {
        "code": "688826",
        "name": "N华海",
        "plan_id": "TP_688826_20260921_093500",
        "strategy_tag": TAG_CHANNEL_SECONDARY_BUY,
        "signal_level": "S4",
        "quality_grade": "S",
        "trigger_price": 10.9,
        "buy_zone_min": 10.8,
        "buy_zone_max": 11.0,
        "higher_low_stop": 10.0,
        "base_low_invalid": 9.5,
        "hard_stop_loss_pct": 2.5,
        "target_1_channel_mid": 15.0,
        "target_2_swing_high": 17.5,
        "suggested_action": "BUY_SCOUT",
        "position_pct": 30.0,
        "expire_at": "14:45:00",
        "created_time": "2026-09-21 09:35:00",
        "extra_info": {"notes": "test_fixture"},
    }
    defaults.update(kwargs)
    requested_level = kwargs.get("signal_level", defaults.get("signal_level", "S4"))
    plan = IPOTradePlan(**defaults)
    if requested_level != getattr(plan, "signal_level", None):
        try:
            plan.signal_level = requested_level
        except Exception:
            try:
                plan.signal_stage = requested_level
            except Exception:
                pass
        if requested_level != getattr(plan, "signal_level", None):
            class _CustomSignalLevelPlan(plan.__class__):
                signal_level = requested_level
            plan.__class__ = _CustomSignalLevelPlan
    return plan


def test_s5_executable_all_green_path():
    """Definition of Done 1: 全绿路径判定跃迁为 S5，包含所有必须返回字段。"""
    plan = _create_valid_s4_plan()
    price = 11.0
    now = "2026-09-21 09:40:00"  # 5 trading minutes elapsed (< 15m)

    res = evaluate_s5_executable(plan=plan, price=price, now=now, market_allowed=True)

    assert isinstance(res, S5ExecutableGateResult)
    assert res.allowed is True
    assert bool(res) is True
    assert res.signal_level == "S5"
    assert res.reject_code is None
    assert res.reject_reason is None
    # RR = (15.0 - 11.0) / (11.0 - 10.0) = 4.0 >= 2.5
    assert res.rr_now == pytest.approx(4.0, abs=1e-3)
    assert res.elapsed_trading_minutes == pytest.approx(5.0, abs=1e-3)
    assert res.plan_id == "TP_688826_20260921_093500"
    assert res.code == "688826"

    # Dict-like access
    assert res["allowed"] is True
    assert res["signal_level"] == "S5"
    assert res.get("rr_now") == pytest.approx(4.0, abs=1e-3)


def test_quality_grades_allowed_and_rejected():
    """Definition of Done 2: B/C 评级拒绝，A/S/SS 评级通过。"""
    now = "2026-09-21 09:40:00"
    price = 11.0

    # Grade SS: Allowed
    plan_ss = _create_valid_s4_plan(quality_grade="SS")
    res_ss = evaluate_s5_executable(plan_ss, price, now)
    assert res_ss.allowed is True
    assert res_ss.signal_level == "S5"

    # Grade A: Allowed
    plan_a = _create_valid_s4_plan(quality_grade="A")
    res_a = evaluate_s5_executable(plan_a, price, now)
    assert res_a.allowed is True
    assert res_a.signal_level == "S5"

    # Grade B: Rejected
    plan_b = _create_valid_s4_plan(quality_grade="B")
    res_b = evaluate_s5_executable(plan_b, price, now)
    assert res_b.allowed is False
    assert res_b.reject_code == REJECT_INVALID_QUALITY_GRADE
    assert res_b.signal_level is None

    # Grade C: Rejected
    plan_c = _create_valid_s4_plan(quality_grade="C")
    res_c = evaluate_s5_executable(plan_c, price, now)
    assert res_c.allowed is False
    assert res_c.reject_code == REJECT_INVALID_QUALITY_GRADE


def test_price_above_buy_zone_rejection():
    """Definition of Done 2: 现价超过买入区间上沿，稳定返回 PRICE_ABOVE_BUY_ZONE。"""
    plan = _create_valid_s4_plan(buy_zone_min=10.8, buy_zone_max=11.0)
    now = "2026-09-21 09:40:00"

    # 11.05 exceeds 11.0
    res = evaluate_s5_executable(plan, price=11.05, now=now)
    assert res.allowed is False
    assert res.reject_code == REJECT_PRICE_ABOVE_BUY_ZONE
    assert res.signal_level is None


def test_price_below_buy_zone_rejection():
    """现价低于买入区间下沿，稳定返回 PRICE_BELOW_BUY_ZONE。"""
    plan = _create_valid_s4_plan(buy_zone_min=10.8, buy_zone_max=11.0)
    now = "2026-09-21 09:40:00"

    # 10.75 is below 10.8
    res = evaluate_s5_executable(plan, price=10.75, now=now)
    assert res.allowed is False
    assert res.reject_code == REJECT_PRICE_BELOW_BUY_ZONE
    assert res.signal_level is None


def test_price_buy_zone_boundaries():
    """现价恰好等于区间下沿与上沿时均合法。"""
    plan = _create_valid_s4_plan(buy_zone_min=10.8, buy_zone_max=11.0)
    now = "2026-09-21 09:40:00"

    res_lower = evaluate_s5_executable(plan, price=10.8, now=now)
    assert res_lower.allowed is True
    assert res_lower.signal_level == "S5"

    res_upper = evaluate_s5_executable(plan, price=11.0, now=now)
    assert res_upper.allowed is True
    assert res_upper.signal_level == "S5"


def test_dynamic_rr_below_threshold_rejection():
    """Definition of Done 2: RR < 2.5 拒绝，返回稳定 reject code RR_BELOW_THRESHOLD。"""
    # stop=10.0, price=10.9, target=12.0
    # RR = (12.0 - 10.9) / (10.9 - 10.0) = 1.1 / 0.9 = 1.222 < 2.5
    plan = _create_valid_s4_plan(
        higher_low_stop=10.0,
        target_1_channel_mid=12.0,
        buy_zone_min=10.8,
        buy_zone_max=11.0,
    )
    now = "2026-09-21 09:40:00"

    res = evaluate_s5_executable(plan, price=10.9, now=now)
    assert res.allowed is False
    assert res.reject_code == REJECT_RR_BELOW_THRESHOLD
    assert res.rr_now == pytest.approx(1.2222, abs=1e-3)
    assert res.signal_level is None


def test_dynamic_rr_boundary_2_5():
    """RR 恰好为 2.5 时允许通过。"""
    # stop=10.0, price=10.8, target=12.8
    # RR = (12.8 - 10.8) / (10.8 - 10.0) = 2.0 / 0.8 = 2.5
    plan = _create_valid_s4_plan(
        higher_low_stop=10.0,
        target_1_channel_mid=12.8,
        buy_zone_min=10.8,
        buy_zone_max=11.0,
    )
    now = "2026-09-21 09:40:00"

    res = evaluate_s5_executable(plan, price=10.8, now=now)
    assert res.allowed is True
    assert res.signal_level == "S5"
    assert res.rr_now == pytest.approx(2.5, abs=1e-3)


def test_ttl_15m_expiration_rejection():
    """Definition of Done 2: 交易时间 >= 15分钟拒绝，保留 TTL_TRADING_15M。"""
    plan = _create_valid_s4_plan(created_time="2026-09-21 09:35:00")
    # 09:35 -> 09:50 = exactly 15 trading minutes
    now = "2026-09-21 09:50:00"

    res = evaluate_s5_executable(plan, price=11.0, now=now)
    assert res.allowed is False
    assert res.reject_code == REJECT_TTL_TRADING_15M
    assert res.elapsed_trading_minutes == pytest.approx(15.0, abs=1e-3)


def test_ttl_lunch_break_excluded():
    """跨午盘停牌期间不计入 TTL 交易时间。"""
    # 11:25 创建，11:30 停盘 (5 trading mins)
    # 13:00 开盘，13:09 仅累计 14 trading mins (< 15m) -> allowed
    plan = _create_valid_s4_plan(created_time="2026-09-21 11:25:00")
    now_1309 = "2026-09-21 13:09:00"
    res_1309 = evaluate_s5_executable(plan, price=11.0, now=now_1309)
    assert res_1309.allowed is True
    assert res_1309.elapsed_trading_minutes == pytest.approx(14.0, abs=1e-3)

    # 13:10 累计 15 trading mins -> expired
    now_1310 = "2026-09-21 13:10:00"
    res_1310 = evaluate_s5_executable(plan, price=11.0, now=now_1310)
    assert res_1310.allowed is False
    assert res_1310.reject_code == REJECT_TTL_TRADING_15M
    assert res_1310.elapsed_trading_minutes == pytest.approx(15.0, abs=1e-3)


def test_ttl_cross_day_expired():
    """跨自然日或交易日计划立即失效。"""
    plan = _create_valid_s4_plan(created_time="2026-09-20 14:50:00")
    now = "2026-09-21 09:35:00"

    res = evaluate_s5_executable(plan, price=11.0, now=now)
    assert res.allowed is False
    assert res.reject_code == REJECT_TTL_CROSS_DAY


@pytest.mark.parametrize(
    "invalid_kwargs",
    [
        {"higher_low_stop": 0.0},                  # structural_stop <= 0
        {"higher_low_stop": -1.0},                 # structural_stop < 0
        {"target_1_channel_mid": 10.0},            # target <= stop (10.0 <= 10.0)
        {"target_1_channel_mid": 9.0},             # target < stop
        {"trigger_price": 0.0},                    # trigger <= 0
        {"buy_zone_min": 0.0},                     # buy_zone_min <= 0
        {"buy_zone_min": 11.5, "buy_zone_max": 11.0},  # buy_zone_max < buy_zone_min
        {"higher_low_stop": 10.8, "buy_zone_min": 10.8}, # stop >= buy_zone_min
        {"target_1_channel_mid": 11.0, "buy_zone_max": 11.0}, # target <= buy_zone_max
    ],
)
def test_structural_invalid_cases(invalid_kwargs):
    """Definition of Done 2: 结构无效测试集合。"""
    plan = _create_valid_s4_plan(**invalid_kwargs)
    now = "2026-09-21 09:40:00"

    res = evaluate_s5_executable(plan, price=11.0, now=now)
    assert res.allowed is False
    assert res.reject_code == REJECT_STRUCTURAL_INVALID
    assert res.signal_level is None


def test_market_blocked():
    """Definition of Done 2: market_allowed=False 必须拒绝，但不改变 plan。"""
    plan = _create_valid_s4_plan()
    now = "2026-09-21 09:40:00"

    res = evaluate_s5_executable(plan, price=11.0, now=now, market_allowed=False)
    assert res.allowed is False
    assert res.reject_code == REJECT_MARKET_BLOCKED
    assert res.signal_level is None
    assert plan.signal_level == "S4"


def test_invalid_strategy_tag():
    """非 CHANNEL_SECONDARY_BUY 策略标签拒绝。"""
    plan = _create_valid_s4_plan(strategy_tag="OTHER_STRATEGY")
    now = "2026-09-21 09:40:00"

    res = evaluate_s5_executable(plan, price=11.0, now=now)
    assert res.allowed is False
    assert res.reject_code == REJECT_INVALID_STRATEGY


def test_invalid_signal_level():
    """非 S4 信号层级拒绝。"""
    # 1. IPOTradePlan 对象且 signal_level 为 S3
    plan = _create_valid_s4_plan(signal_level="S3")
    now = "2026-09-21 09:40:00"

    res = evaluate_s5_executable(plan, price=11.0, now=now)
    assert res.allowed is False
    assert res.reject_code == REJECT_INVALID_SIGNAL_LEVEL
    assert res.signal_level is None

    # 2. 字典格式且 signal_level 为 S3
    dict_plan = {
        "code": "688826",
        "name": "N华海",
        "plan_id": "TP_688826_20260921_093500",
        "strategy_tag": TAG_CHANNEL_SECONDARY_BUY,
        "signal_level": "S3",
        "quality_grade": "S",
        "trigger_price": 10.9,
        "buy_zone_min": 10.8,
        "buy_zone_max": 11.0,
        "higher_low_stop": 10.0,
        "target_1_channel_mid": 15.0,
        "created_time": "2026-09-21 09:35:00",
    }
    res_dict = evaluate_s5_executable(dict_plan, price=11.0, now=now)
    assert res_dict.allowed is False
    assert res_dict.reject_code == REJECT_INVALID_SIGNAL_LEVEL
    assert res_dict.signal_level is None


def test_plan_immutability_strict():
    """Definition of Done 3: S4 plan 调用前后字段完全不变，纯函数零状态修改。"""
    original_plan = _create_valid_s4_plan()
    deep_copied = copy.deepcopy(original_plan)

    now = "2026-09-21 09:40:00"

    # 1. 成功调用 S5
    res1 = evaluate_s5_executable(original_plan, price=11.0, now=now, market_allowed=True)
    assert res1.allowed is True
    assert original_plan.signal_level == "S4"
    assert original_plan == deep_copied

    # 2. 失败调用 (market_allowed=False)
    res2 = evaluate_s5_executable(original_plan, price=11.0, now=now, market_allowed=False)
    assert res2.allowed is False
    assert original_plan.signal_level == "S4"
    assert original_plan == deep_copied

    # 3. 失败调用 (price above buy zone)
    res3 = evaluate_s5_executable(original_plan, price=12.0, now=now, market_allowed=True)
    assert res3.allowed is False
    assert original_plan.signal_level == "S4"
    assert original_plan == deep_copied

    # 4. 失败调用 (TTL expired)
    res4 = evaluate_s5_executable(original_plan, price=11.0, now="2026-09-21 10:00:00", market_allowed=True)
    assert res4.allowed is False
    assert original_plan.signal_level == "S4"
    assert original_plan == deep_copied


def test_dict_plan_support():
    """支持等价字典输入。"""
    plan_dict = {
        "code": "688826",
        "name": "N华海",
        "plan_id": "TP_688826_20260921_093500",
        "strategy_tag": TAG_CHANNEL_SECONDARY_BUY,
        "signal_level": "S4",
        "quality_grade": "S",
        "trigger_price": 10.9,
        "buy_zone_min": 10.8,
        "buy_zone_max": 11.0,
        "higher_low_stop": 10.0,
        "target_1_channel_mid": 15.0,
        "created_time": "2026-09-21 09:35:00",
    }
    plan_dict_copy = dict(plan_dict)
    now = "2026-09-21 09:40:00"

    res = evaluate_s5_executable(plan_dict, price=11.0, now=now)
    assert res.allowed is True
    assert res.signal_level == "S5"
    assert res.rr_now == pytest.approx(4.0, abs=1e-3)
    assert plan_dict == plan_dict_copy


def test_result_dict_serialization():
    """测试返回结果容器字典化与 JSON 序列化。"""
    plan = _create_valid_s4_plan()
    now = "2026-09-21 09:40:00"
    res = evaluate_s5_executable(plan, price=11.0, now=now)

    d = res.to_dict()
    assert isinstance(d, dict)
    assert d["allowed"] is True
    assert d["signal_level"] == "S5"

    json_str = json.dumps(d)
    parsed = json.loads(json_str)
    assert parsed["allowed"] is True
    assert parsed["signal_level"] == "S5"
