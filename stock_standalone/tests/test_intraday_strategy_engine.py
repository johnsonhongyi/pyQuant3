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
import pandas as pd
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

def _make_test_strategy():
    return {
        "id": "test_pinzhun_strategy",
        "name": "测试专属策略",
        "phases": [
            {
                "phase_id": "phase_call",
                "name": "集合竞价",
                "start_time": "09:15",
                "end_time": "09:25",
                "rules": []
            },
            {
                "phase_id": "phase_surge",
                "name": "开盘冲高卖出",
                "start_time": "09:30",
                "end_time": "10:00",
                "rules": [
                    {
                        "rule_id": "rule_surge_50",
                        "name": "开盘冲高+10%卖50%",
                        "condition_mode": "all",
                        "trigger_expr": "price >= open_price * 1.10",
                        "sell_ratio": 0.50,
                        "order_type": "limit",
                        "limit_price_expr": "bid1_price * 0.98",
                        "description": "开盘快速冲高达到+10%则挂笼子下沿限价单卖出50%"
                    },
                    {
                        "rule_id": "rule_halt_30",
                        "name": "较开盘+30%临停复牌卖30%",
                        "condition_mode": "all",
                        "trigger_expr": "max_price >= open_price * 1.30",
                        "sell_ratio": 0.30,
                        "order_type": "limit",
                        "limit_price_expr": "open_price * 1.28",
                        "description": "复牌前挂 Open*1.28 限价单"
                    },
                    {
                        "rule_id": "rule_timeout_30",
                        "name": "10:00超时未冲高卖30%",
                        "condition_mode": "all",
                        "trigger_expr": "current_time >= '10:00' and max_price < open_price * 1.10",
                        "sell_ratio": 0.30,
                        "order_type": "market",
                        "description": "若10:00仍未出现+10%冲高，则按市价卖出30%"
                    }
                ]
            },
            {
                "phase_id": "circuit_breaker",
                "name": "盘中临停复牌卖出",
                "start_time": "10:00",
                "end_time": "14:50",
                "rules": [
                    {
                        "rule_id": "rule_halt_30_mid",
                        "name": "较开盘+30%临停复牌卖30%",
                        "condition_mode": "all",
                        "trigger_expr": "max_price >= open_price * 1.30",
                        "sell_ratio": 0.30,
                        "order_type": "limit",
                        "limit_price_expr": "open_price * 1.28",
                        "description": "复牌前挂 Open*1.28 限价单"
                    }
                ]
            },
            {
                "phase_id": "phase_clear",
                "name": "尾盘清仓",
                "start_time": "14:50",
                "end_time": "14:57",
                "rules": []
            }
        ]
    }

def test_time_axis_phase_inference(engine):
    """测试时间轴阶段推算"""
    engine.reset_state()
    strategy_a = _make_test_strategy()

    ph_call, idx_0 = engine.get_current_phase("09:20", strategy_a)
    assert "call" in str(ph_call.get("phase_id", ""))

    ph_surge, idx_1 = engine.get_current_phase("09:45", strategy_a)
    assert "surge" in str(ph_surge.get("phase_id", ""))

    ph_halt, idx_2 = engine.get_current_phase("10:30", strategy_a)
    assert "circuit_breaker" in str(ph_halt.get("phase_id", ""))

    ph_clear, idx_3 = engine.get_current_phase("14:52", strategy_a)
    assert "clear" in str(ph_clear.get("phase_id", ""))

def test_surge_sell_rule_trigger(engine):
    """测试开盘冲高卖出与限价单规则"""
    engine.reset_state()
    code = "688826"
    open_p = 565.0
    strat_a = _make_test_strategy()
    # 较开盘涨 10% (625元 >= 621.5元)
    tick_surge = {"trade": 625.0, "high": 625.0, "low": 565.0}

    signals = engine.evaluate_tick(
        code=code,
        tick_row=tick_surge,
        open_price=open_p,
        current_time_str="09:35",
        bid1_price=624.5,
        strategy=strat_a,
        bar_index=15
    )

    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_type == SignalType.SELL
    assert getattr(sig, "sell_ratio") >= 0.30
    assert getattr(sig, "suggested_price") > 0.0

def test_timeout_fallback_rule(engine):
    """测试 10:00 整超时未触发冲高兜底卖出规则"""
    engine.reset_state()
    code = "688826"
    open_p = 565.0
    strat_a = _make_test_strategy()

    # 09:50 价格平淡
    sigs_quiet = engine.evaluate_tick(
        code=code,
        tick_row={"trade": 570.0, "high": 575.0, "low": 560.0},
        open_price=open_p,
        current_time_str="09:50",
        strategy=strat_a,
        bar_index=20
    )
    assert len(sigs_quiet) == 0

    # 10:00 到达，触发超时兜底
    sigs_timeout = engine.evaluate_tick(
        code=code,
        tick_row={"trade": 570.0, "high": 575.0, "low": 560.0},
        open_price=open_p,
        current_time_str="10:00",
        strategy=strat_a,
        bar_index=30
    )

    assert len(sigs_timeout) == 1
    sig_to = sigs_timeout[0]
    assert getattr(sig_to, "sell_ratio") == 0.30
    assert "timeout" in getattr(sig_to, "rule_id")

def test_circuit_breaker_rule(engine):
    """测试较开盘价 +30% 临停复牌卖出 30% 规则"""
    engine.reset_state()
    code = "688826"
    open_p = 565.0
    strat_a = _make_test_strategy()

    # 09:45 盘中急速飙升触及 +30% (735.0元 >= 565 * 1.30 = 734.5元)
    signals = engine.evaluate_tick(
        code=code,
        tick_row={"trade": 736.0, "high": 736.0, "low": 565.0},
        open_price=open_p,
        current_time_str="09:45",
        strategy=strat_a,
        bar_index=15
    )

    assert len(signals) >= 1
    halt_sigs = [s for s in signals if "halt" in getattr(s, "rule_id") or "circuit" in getattr(s, "rule_id")]
    assert len(halt_sigs) == 1
    sig_cb = halt_sigs[0]
    assert getattr(sig_cb, "sell_ratio") == 0.30

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


def test_pinzhun_laser_ladder_spec_and_thresholds(engine):
    """测试频准激光 688826 证券阶梯规格与阈值计算"""
    engine.reset_state()
    spec = engine.get_stock_ladder_spec("688826")
    assert spec["code"] == "688826"
    assert spec["issue_price"] == 186.88
    assert spec["float_shares_wan"] in (761.78, 3990.8)
    assert spec["float_mv_yi"] in (14.24, 74.58)

    # 校验价格档位 (+100%, +200%, +300%, +400%, +500%)
    price_ladder = {item["name"]: item["price"] for item in spec["price_ladder"]}
    assert price_ladder["+100%"] == 373.76
    assert price_ladder["+200%"] == 560.64
    assert price_ladder["+300%"] == 747.52
    assert price_ladder["+400%"] == 934.40
    assert price_ladder["+500%"] == 1121.28

    # 校验 688826 开盘价档位
    tier_high, strat_high, mode_high = engine.get_open_price_tier(580.0, code="688826")
    assert "乐观档" in tier_high
    assert "688826" in strat_high


def test_seven_timeline_nodes_evaluation_and_pattern(engine):
    """测试 7 节点时序评估、加权综合得分、形态分类与实操建议"""
    engine.reset_state("688826")
    code = "688826"
    open_p = 565.0  # +202% 强势高开
    price = 625.0   # 冲高突破开盘价 (+10.6%)
    high_p = 630.0
    low_p = 560.0
    vwap = 610.0
    turnover = 65.0 # 标准健康换手
    amount = 200.0 * 1e8 # 200 亿成交额

    res = engine.evaluate_seven_nodes(
        code=code,
        current_time_str="09:35",
        open_price=open_p,
        price=price,
        high_price=high_p,
        low_price=low_p,
        vwap=vwap,
        turnover_rate=turnover,
        amount=amount,
        strategy_id="strategy_频准激光_688826"
    )

    assert res["code"] == "688826"
    assert len(res["node_results"]) == 7
    # 权重总和必须为 1.0 (100%)
    total_weights = sum(item["weight"] for item in res["node_results"])
    assert round(total_weights, 2) == 1.00

    # 节点① 9:25 高开>560.64 判定为强，>=8.0分
    assert res["node_results"][0]["judgment"] == "强"
    assert res["node_results"][0]["final_score"] >= 8.0

    # 节点② 9:40 涨超10% 判定为强
    assert res["node_results"][1]["judgment"] == "强"
    assert res["node_results"][1]["final_score"] >= 9.0

    # 资金强度倍数
    assert res["intensity_ratio"] >= 2.0

    # 检查综合得分与形态判定
    assert res["total_weighted_score"] >= 6.5
    assert res["pattern"] in ["A型·超强趋势", "B型·强势换手"]

    # 检查阶段自动解析与实操指引
    assert "早盘第一波" in res["active_node_name"] or "第一波攻击" in res["current_status_diagnosis"]
    assert "触发卖出" in res["action_execution_text"] or "50%" in res["action_execution_text"]


def test_manual_score_override(engine):
    """测试人工覆盖打分与动态加权得分即时更新"""
    engine.reset_state("688826")
    code = "688826"

    # 人工为 7 个节点全部打 10 分满分
    for i in range(7):
        engine.set_manual_node_score(code, i, 10.0)

    res = engine.evaluate_seven_nodes(
        code=code,
        current_time_str="15:00",
        open_price=565.0,
        price=620.0,
        high_price=630.0,
        low_price=560.0
    )

    assert res["total_weighted_score"] == 10.00
    assert res["pattern"] == "A型·超强趋势"
    assert "★关注竞价接力" in res["t1_advice"]

    # 人工调整为全 2 分弱势
    for i in range(7):
        engine.set_manual_node_score(code, i, 2.0)

    res_weak = engine.evaluate_seven_nodes(
        code=code,
        current_time_str="15:00",
        open_price=300.0,
        price=270.0,
        high_price=305.0,
        low_price=268.0
    )

    assert res_weak["total_weighted_score"] == 2.00
    assert res_weak["pattern"] == "D/E型·弱势或衰竭"
    assert "★回避" in res_weak["t1_advice"]


def test_extract_market_snapshot_from_df_automatic(engine):
    """测试从推送的 DataFrame 中全自动提取换手率、成交量、成交额与最高最低价等字段"""
    df_mock = pd.DataFrame([
        {
            "code": "688826",
            "name": "频准激光",
            "open": 580.0,
            "close": 645.0,
            "trade": 645.0,
            "high": 650.0,
            "low": 575.0,
            "turnover": 68.5,
            "amount": 4120000000.0, # 41.2 亿元
            "volume": 63800, # 手
            "buy": 644.5,
            "sell": 645.5,
            "percent": 11.2
        }
    ]).set_index("code")

    snap = engine.extract_market_snapshot_from_df(df_mock, "688826")
    assert snap["open_price"] == 580.0
    assert snap["price"] == 645.0
    assert snap["high_price"] == 650.0
    assert snap["low_price"] == 575.0
    assert snap["turnover_rate"] == 68.5
    assert snap["amount"] == 4120000000.0
    assert snap["bid1_price"] == 644.5
    assert snap["vwap"] > 0.0


def test_818_scenario_intraday_full_day_backtest(engine):
    """测试 8/18 开盘时间对齐全天分时模拟回测演练 (四大情景完整跑通)"""
    # 1. 测试 A型·超强主升主线情景
    df_a = engine.generate_scenario_intraday_df("A_SUPER_TREND", code="688826")
    assert len(df_a) >= 240
    assert "09:25" in df_a.index
    assert "15:00" in df_a.index

    res_a = engine.run_full_day_backtest("688826", df_a)
    final_a = res_a["final_evaluation"]
    assert final_a["total_weighted_score"] >= 8.0
    assert final_a["pattern"] == "A型·超强趋势"
    assert len(res_a["signals"]) >= 1 # 至少触发早盘冲高卖出或临停卖出

    # 2. 测试 B型·强势换手洗盘情景
    df_b = engine.generate_scenario_intraday_df("B_STRONG_TURNOVER", code="688826")
    res_b = engine.run_full_day_backtest("688826", df_b)
    final_b = res_b["final_evaluation"]
    assert 6.5 <= final_b["total_weighted_score"] <= 9.0
    assert final_b["pattern"] in ["B型·强势换手", "A型·超强趋势"]

    # 3. 测试 C型·冲高兑现回落情景
    df_c = engine.generate_scenario_intraday_df("C_SURGE_AND_CASH", code="688826")
    res_c = engine.run_full_day_backtest("688826", df_c)
    final_c = res_c["final_evaluation"]
    assert final_c["pattern"] in ["C型·冲高兑现", "B型·强势换手"]

    # 4. 测试 D型·弱势衰竭情景
    df_d = engine.generate_scenario_intraday_df("D_WEAK_EXHAUSTION", code="688826")
    res_d = engine.run_full_day_backtest("688826", df_d)
    final_d = res_d["final_evaluation"]
    assert final_d["total_weighted_score"] < 5.0
    assert final_d["pattern"] == "D/E型·弱势或衰竭"


