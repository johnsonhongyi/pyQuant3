# -*- coding: utf-8 -*-
"""
上涨通道极限性能测算与通道类型分支引擎专项单元测试
"""

import sys
import os
import unittest
import time
import numpy as np
import pandas as pd

CURR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURR_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ats.channel_bottom_reversal_strategy import (
    classify_channel_type,
    evaluate_ascending_channel_strategy,
    evaluate_channel_bottom_reversal,
    evaluate_channel_strategy,
    ChannelTrendStrategy
)


def generate_mock_ascending_df(pattern_type: str = "pullback_support", n_bars: int = 60) -> pd.DataFrame:
    """生成真实的上涨通道测试用例"""
    np.random.seed(42)
    times = pd.date_range(end="2026-08-21 15:00", periods=n_bars, freq="60min")
    
    # 基础主升波段：从 20.0 上升至 32.0 (斜率持续向上)
    trend_base = np.linspace(20.0, 32.0, n_bars)
    
    # 叠加波段震荡（Higher Highs + Higher Lows）
    wave = 1.2 * np.sin(np.linspace(0, 4 * np.pi, n_bars))
    closes = trend_base + wave
    highs = closes + np.random.uniform(0.3, 0.8, n_bars)
    lows = closes - np.random.uniform(0.3, 0.8, n_bars)
    opens = closes + np.random.uniform(-0.2, 0.2, n_bars)
    vols = np.random.uniform(1000, 3000, n_bars)

    if pattern_type == "pullback_support":
        # 形成历史前高 33.5，最近回踩支撑 31.0 缩量企稳
        highs[-15] = 33.5
        closes[-4] = 30.5
        closes[-3] = 30.8
        closes[-2] = 31.0
        closes[-1] = 31.6  # 企稳阳线
        opens[-1] = 31.1
        highs[-1] = 31.8
        lows[-1] = 30.9
        # 回踩期间缩量
        vols[-4:-1] = 500.0
        vols[-1] = 1600.0

    elif pattern_type == "box_breakout":
        # 前期横盘小箱体 31.0，最近 1 根放量突破
        highs[-15:-3] = 31.0
        closes[-3:-1] = 30.8
        closes[-1] = 32.5  # 强势突破
        opens[-1] = 31.0
        highs[-1] = 32.8
        vols[-1] = 4500.0  # 放量

    elif pattern_type == "broken_support":
        # 跌破前期大底 18.0
        lows[-2:] = 16.0
        closes[-2:] = 16.5

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "vol": vols
    }, index=times)
    return df


class TestAscendingChannelStrategy(unittest.TestCase):
    """上涨通道策略与通道分类器测试套件"""

    def test_01_channel_classifier(self):
        """测试通道类型极速判决器"""
        df_up = generate_mock_ascending_df("pullback_support", n_bars=60)
        cls_up = classify_channel_type(df_up)
        self.assertEqual(cls_up["channel_type"], "ascending")
        self.assertGreater(cls_up["slope_deg"], 2.0)
        print("[Test 1.1] 通道分类器上涨通道判定成功")

    def test_02_ascending_channel_pullback_support(self):
        """测试上涨通道下轨回踩企稳形态"""
        df_up = generate_mock_ascending_df("pullback_support", n_bars=60)
        res = evaluate_ascending_channel_strategy(df_up)
        self.assertTrue(res["is_matched"])
        self.assertEqual(res["channel_type"], "ascending")
        self.assertEqual(res["pattern_name"], "上涨通道下轨回踩企稳")
        self.assertGreater(res["score"], 70.0)
        self.assertGreater(res["entry_price"], 0.0)
        self.assertGreater(res["target_price_1"], res["entry_price"])
        self.assertLess(res["stop_loss"], res["entry_price"])
        print(f"[Test 2] 上涨通道回踩企稳识别成功: 得分={res['score']}, 介入={res['entry_price']}")

    def test_03_ascending_channel_box_breakout(self):
        """测试上涨通道中继平台放量突破形态"""
        df_break = generate_mock_ascending_df("box_breakout", n_bars=60)
        res = evaluate_ascending_channel_strategy(df_break)
        self.assertTrue(res["is_matched"])
        self.assertEqual(res["pattern_name"], "上涨通道中继突破")
        self.assertGreaterEqual(res["score"], 80.0)
        print(f"[Test 3] 上涨通道中继突破识别成功: 得分={res['score']}")

    def test_04_broken_support_filtered(self):
        """测试破位跌破支撑线拦截"""
        df_broken = generate_mock_ascending_df("broken_support", n_bars=60)
        res = evaluate_ascending_channel_strategy(df_broken)
        self.assertFalse(res["is_matched"])
        self.assertIn("跌破", res["reason"])
        print("[Test 4] 破位新低拦截成功")

    def test_05_unified_strategy_engine(self):
        """测试统一分发引擎 evaluate_channel_strategy"""
        strategy = ChannelTrendStrategy()
        
        # 上涨通道样本
        df_up = generate_mock_ascending_df("pullback_support", n_bars=60)
        res_up = strategy.evaluate(df_up)
        self.assertTrue(res_up["is_matched"])
        self.assertEqual(res_up["channel_type"], "ascending")

        print("[Test 5] 统一分发引擎自适应分支测试成功")

    def test_06_stress_benchmark_performance(self):
        """2,000 次纯 NumPy 极限性能基准压力测试"""
        df_test = generate_mock_ascending_df("pullback_support", n_bars=60)
        rounds = 2000
        t0 = time.perf_counter()
        for _ in range(rounds):
            _ = evaluate_channel_strategy(df_test)
        total_time = time.perf_counter() - t0
        avg_ms = (total_time / rounds) * 1000.0
        self.assertLess(avg_ms, 0.5, f"单次平均耗时 {avg_ms:.4f}ms 必须低于 0.5ms")
        print(f"[Test 6] 极限性能基准: 运行 {rounds} 次测算, 总耗时 {total_time:.3f}s, 单次平均耗时 {avg_ms:.4f} ms")


if __name__ == "__main__":
    unittest.main()
