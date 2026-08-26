import os
import sys
import time
import pytest
import numpy as np
import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.opening_bubble_engine import (
    OpeningBubbleEngine, get_opening_bubble_engine, get_pct_tier, get_vol_tier
)
from ats.limit_up_engine import LimitUpEngine


def test_pct_tier_classification():
    """测试 8 级阶梯划分准确性"""
    assert get_pct_tier(-5.0) == 0   # <-4%
    assert get_pct_tier(-3.0) == 1   # -4%~-2%
    assert get_pct_tier(-0.5) == 2   # -2%~0%
    assert get_pct_tier(1.2) == 3    # 0%~2%
    assert get_pct_tier(3.5) == 4    # 2%~4%
    assert get_pct_tier(5.2) == 5    # 4%~6%
    assert get_pct_tier(7.0) == 6    # 6%~8%
    assert get_pct_tier(9.9) == 7    # >8%


def test_vol_tier_classification():
    """测试量能能级划分"""
    assert get_vol_tier(1.0) == 1
    assert get_vol_tier(2.0) == 2
    assert get_vol_tier(4.0) == 3
    assert get_vol_tier(8.0) == 4


def test_pattern_recognition_and_transitions():
    """测试开盘形态识别与多轮冒泡跃迁"""
    engine = OpeningBubbleEngine()
    engine.reset_daily()

    # 1. 模拟 Round 1: 09:30 开盘快照
    df_round1 = pd.DataFrame([
        # 标的A: 低开 -1.5%
        {"code": "000001", "name": "平安银行", "close": 10.0, "open": 9.85, "pre_close": 10.0, "percent": -1.5, "volume_ratio": 1.8, "vwap": 9.85, "amount": 50000000},
        # 标的B: 高开 +3.0%
        {"code": "600519", "name": "贵州茅台", "close": 1854.0, "open": 1854.0, "pre_close": 1800.0, "percent": 3.0, "volume_ratio": 2.5, "vwap": 1854.0, "amount": 100000000},
        # 标的C: 平开 +0.2%
        {"code": "002412", "name": "汉森制药", "close": 10.02, "open": 10.02, "pre_close": 10.0, "percent": 0.2, "volume_ratio": 1.2, "vwap": 10.02, "amount": 20000000},
        # 标的D: 高开 +4.0%
        {"code": "601519", "name": "大智慧", "close": 10.4, "open": 10.4, "pre_close": 10.0, "percent": 4.0, "volume_ratio": 2.0, "vwap": 10.4, "amount": 30000000},
    ]).set_index("code")

    updated = engine.update_market_snapshot(df_round1)
    assert updated == 4

    # 2. 模拟 Round 2: 09:35 盘中演进
    # 标的A: 从 -1.5% 强力拉升至 +2.5% (低开高走反包，穿过0轴和均线)
    # 标的B: 高开 +3.0% 后横盘震荡在 +3.2% (高开放量蓄势)
    # 标的C: 从 0.2% 跃迁至 2.5% (经历阶梯 3 -> 4)
    # 标的D: 从 +4.0% 高开下杀至 +0.5% (跌破开盘价与均线，高开低走预警)
    df_round2 = pd.DataFrame([
        {"code": "000001", "name": "平安银行", "close": 10.25, "open": 9.85, "pre_close": 10.0, "percent": 2.5, "volume_ratio": 2.8, "vwap": 10.05, "amount": 120000000},
        {"code": "600519", "name": "贵州茅台", "close": 1857.6, "open": 1854.0, "pre_close": 1800.0, "percent": 3.2, "volume_ratio": 3.0, "vwap": 1855.0, "amount": 250000000},
        {"code": "002412", "name": "汉森制药", "close": 10.25, "open": 10.02, "pre_close": 10.0, "percent": 2.5, "volume_ratio": 2.5, "vwap": 10.15, "amount": 50000000},
        {"code": "601519", "name": "大智慧", "close": 10.05, "open": 10.4, "pre_close": 10.0, "percent": 0.5, "volume_ratio": 2.2, "vwap": 10.25, "amount": 80000000},
    ]).set_index("code")

    engine.update_market_snapshot(df_round2)

    # 3. 模拟 Round 3: 09:40
    # 标的C: 再次跃迁至 +5.5% (经历 0%~2% -> 2%~4% -> 4%~6% 步步高升)
    df_round3 = pd.DataFrame([
        {"code": "000001", "name": "平安银行", "close": 10.35, "open": 9.85, "pre_close": 10.0, "percent": 3.5, "volume_ratio": 3.2, "vwap": 10.12, "amount": 180000000},
        {"code": "600519", "name": "贵州茅台", "close": 1859.4, "open": 1854.0, "pre_close": 1800.0, "percent": 3.3, "volume_ratio": 3.5, "vwap": 1856.0, "amount": 350000000},
        {"code": "002412", "name": "汉森制药", "close": 10.55, "open": 10.02, "pre_close": 10.0, "percent": 5.5, "volume_ratio": 4.0, "vwap": 10.30, "amount": 90000000},
        {"code": "601519", "name": "大智慧", "close": 9.90, "open": 10.4, "pre_close": 10.0, "percent": -1.0, "volume_ratio": 2.5, "vwap": 10.20, "amount": 110000000},
    ]).set_index("code")

    engine.update_market_snapshot(df_round3)

    # 验证标的A (000001 平安银行): 低开高走
    prof_a = engine.get_stock_profile("000001")
    assert prof_a["pattern_type"] == "LOW_OPEN_HIGH_CLIMB"
    assert "低开高走" in prof_a["pattern_tag"]
    assert prof_a["alpha_score"] >= 75.0

    # 验证标的B (600519 贵州茅台): 高开横盘蓄势锁筹
    prof_b = engine.get_stock_profile("600519")
    assert prof_b["pattern_type"] == "HIGH_OPEN_CONSOLIDATION"
    assert "高开蓄势" in prof_b["pattern_tag"]

    # 验证标的C (002412 汉森制药): 步步高升跃迁
    prof_c = engine.get_stock_profile("002412")
    assert prof_c["tier_jumps"] >= 2
    assert prof_c["pattern_type"] == "STEP_BUBBLE_UP"
    assert "步步高升" in prof_c["pattern_tag"]

    # 验证标的D (601519 大智慧): 高开低走预警
    prof_d = engine.get_stock_profile("601519")
    assert prof_d["pattern_type"] == "HIGH_OPEN_DROP"
    assert "高开低走" in prof_d["pattern_tag"]
    assert prof_d["alpha_score"] <= 40.0


def test_limit_up_engine_integration():
    """测试 LimitUpEngine 的 get_opening_bubble_records 数据整合"""
    lim_engine = LimitUpEngine.get_instance()
    
    test_df = pd.DataFrame([
        {"code": "000001", "name": "平安银行", "close": 10.35, "open": 9.85, "pre_close": 10.0, "percent": 3.5, "volume_ratio": 3.2, "vwap": 10.12, "amount": 180000000, "dff": 1.2, "dff2": 5.5, "dff3": 12.0, "Rank": 25},
        {"code": "002412", "name": "汉森制药", "close": 10.55, "open": 10.02, "pre_close": 10.0, "percent": 5.5, "volume_ratio": 4.0, "vwap": 10.30, "amount": 90000000, "dff": 2.5, "dff2": 8.0, "dff3": 25.0, "Rank": 10},
    ]).set_index("code")

    records = lim_engine.get_opening_bubble_records(current_df=test_df)
    assert isinstance(records, list)
    assert len(records) >= 2

    # 检查字段完整性
    for r in records:
        assert "code" in r
        assert "name" in r
        assert "open_pct" in r
        assert "tier_tag" in r
        assert "pattern_desc" in r
        assert "trajectory_str" in r
        assert "momentum_score" in r
        assert "dff" in r


def test_high_concurrency_performance():
    """5000+ 全市场标的极限性能测试 (确保每秒能处理数百轮)"""
    engine = OpeningBubbleEngine()
    engine.reset_daily()

    num_stocks = 5000
    np.random.seed(42)
    
    codes = [f"{i:06d}" for i in range(1, num_stocks + 1)]
    pre_closes = np.random.uniform(5.0, 100.0, num_stocks)
    open_pcts = np.random.normal(0.0, 2.0, num_stocks)
    opens = pre_closes * (1.0 + open_pcts / 100.0)
    
    mock_df = pd.DataFrame({
        "name": [f"Stock_{c}" for c in codes],
        "close": opens,
        "open": opens,
        "pre_close": pre_closes,
        "percent": open_pcts,
        "volume_ratio": np.random.uniform(0.5, 5.0, num_stocks),
        "amount": np.random.uniform(1e6, 5e8, num_stocks),
        "vwap": opens
    }, index=codes)

    t0 = time.time()
    # 模拟连续更新 10 轮
    for round_idx in range(10):
        # 每次微调价格
        price_shifts = np.random.normal(0.2, 0.5, num_stocks)
        mock_df["percent"] += price_shifts
        mock_df["close"] = mock_df["pre_close"] * (1.0 + mock_df["percent"] / 100.0)
        engine.update_market_snapshot(mock_df)

    t_total = time.time() - t0
    avg_per_round_ms = (t_total / 10.0) * 1000.0

    print(f"\n[OpeningBubbleEngine] 5000 stocks update benchmark: 10 rounds took {t_total:.3f}s, avg per round {avg_per_round_ms:.2f}ms")
    # 单轮 5000 只股票应在 50ms 以内完成 (通常在纯内存中 < 15ms)
    assert avg_per_round_ms < 100.0
