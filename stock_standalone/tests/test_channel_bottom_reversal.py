# -*- coding: utf-8 -*-
"""
60分钟走势通道底部缩量企稳与右侧突破测算策略专项单元测试与性能基准
"""

import sys
import os
import time
import unittest
import numpy as np
import pandas as pd

# 加入项目根目录搜索路径
CURR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURR_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ats.channel_bottom_reversal_strategy import (
    evaluate_channel_bottom_reversal,
    ChannelBottomReversalStrategy
)


def generate_mock_60m_df(
    pattern_type: str = "valid_reversal",
    n_bars: int = 60
) -> pd.DataFrame:
    """
    构造仿真 60分钟 K 线序列
    """
    times = pd.date_range(end="2026-08-21 15:00", periods=n_bars, freq="60min")
    
    closes = np.zeros(n_bars)
    highs = np.zeros(n_bars)
    lows = np.zeros(n_bars)
    opens = np.zeros(n_bars)
    vols = np.zeros(n_bars)

    # 1. 前 35 根 K 棒：标准下降通道 (从 100.0 跌到 70.0)
    for i in range(35):
        mid_p = 100.0 - (i / 35.0) * 30.0
        # 波动震荡触及上下轨
        wave = 2.5 * np.sin(i * 0.8)
        c = mid_p + wave
        closes[i] = c
        opens[i] = c - 0.5
        highs[i] = max(opens[i], closes[i]) + 1.2
        lows[i] = min(opens[i], closes[i]) - 1.2
        vols[i] = 20000.0 + np.random.uniform(0, 5000)

    # 2. 中间 35~54 根 K 棒 (20 根)：底部缩量企稳横盘震荡 (在 70.0~74.0 区间)
    lowest_val = 69.5
    for i in range(35, 55):
        c = 71.5 + 1.2 * np.sin((i - 35) * 1.0)
        closes[i] = c
        opens[i] = c - 0.2
        highs[i] = max(opens[i], closes[i]) + 0.8
        lows[i] = max(lowest_val + 0.2, min(opens[i], closes[i]) - 0.6)
        # 底部量能显著缩减 (为前期的 40%)
        vols[i] = 8000.0 + np.random.uniform(0, 1500)

    # 3. 最后 5 根 K 棒 (55~59)：根据 pattern_type 构造右侧形态
    if pattern_type == "valid_reversal":
        # 稳步抬升突破前高 73.5，且无新低
        for idx, i in enumerate(range(55, 60)):
            c = 72.5 + idx * 1.0  # 72.5, 73.5, 74.5, 75.5, 76.5 (放量突破 74.0 前高)
            closes[i] = c
            opens[i] = c - 0.5
            highs[i] = c + 0.8
            lows[i] = opens[i] - 0.2  # 低点稳步抬高
            vols[i] = 18000.0 + idx * 2000 # 放量

    elif pattern_type == "broken_new_low":
        # 跌破前期 69.5 低点
        for idx, i in enumerate(range(55, 60)):
            c = 68.0 - idx * 0.5
            closes[i] = c
            opens[i] = c + 0.5
            highs[i] = opens[i] + 0.2
            lows[i] = c - 0.8 # 创新低
            vols[i] = 12000.0

    elif pattern_type == "no_volume_shrink":
        # 底部未缩量 (持续巨量)
        vols[35:55] = 35000.0
        for idx, i in enumerate(range(55, 60)):
            c = 72.5 + idx * 1.0
            closes[i] = c
            opens[i] = c - 0.5
            highs[i] = c + 0.8
            lows[i] = opens[i] - 0.2
            vols[i] = 30000.0

    elif pattern_type == "no_breakout":
        # 横盘在底部，未突破前高
        for idx, i in enumerate(range(55, 60)):
            c = 71.0
            closes[i] = c
            opens[i] = c
            highs[i] = c + 0.3
            lows[i] = c - 0.3
            vols[i] = 7000.0

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "vol": vols
    }, index=times)
    return df


class TestChannelBottomReversalStrategy(unittest.TestCase):
    """60f 通道底部反转策略专项测试套件"""

    def setUp(self):
        self.strategy = ChannelBottomReversalStrategy()

    def test_01_valid_reversal_pattern(self):
        """测试标准下降通道 + 底部缩量横盘 + 右侧突破不创新低形态"""
        df = generate_mock_60m_df("valid_reversal")
        res = self.strategy.evaluate(df)
        
        self.assertTrue(res["is_matched"], f"标准形态应匹配成功，实际原因: {res.get('reason')}")
        self.assertGreater(res["score"], 60.0)
        self.assertGreater(res["entry_price"], 0.0)
        self.assertLess(res["stop_loss"], res["entry_price"])
        self.assertGreater(res["target_price_1"], res["entry_price"])
        self.assertGreaterEqual(res["volume_shrink_pct"], 25.0)
        print(f"[Test 1] 标准 60f 通道底部反转形态识别成功: 得分={res['score']}, 止损={res['stop_loss']}, 目标={res['target_price_1']}")

    def test_02_filter_broken_new_low(self):
        """测试最近 K 线跌破波谷新低被有效拦截"""
        df = generate_mock_60m_df("broken_new_low")
        res = self.strategy.evaluate(df)
        self.assertFalse(res["is_matched"])
        self.assertTrue("新低" in res["reason"] or "跌破" in res["reason"])
        print(f"[Test 2] 跌破新低过滤成功: {res['reason']}")

    def test_03_filter_no_volume_shrink(self):
        """测试底部未缩量企稳被有效拦截"""
        df = generate_mock_60m_df("no_volume_shrink")
        res = self.strategy.evaluate(df)
        self.assertFalse(res["is_matched"])
        self.assertIn("缩量", res["reason"])
        print(f"[Test 3] 未缩量过滤成功: {res['reason']}")

    def test_04_filter_no_breakout(self):
        """测试横盘但未发生右侧突破被有效拦截"""
        df = generate_mock_60m_df("no_breakout")
        res = self.strategy.evaluate(df)
        self.assertFalse(res["is_matched"])
        self.assertIn("突破", res["reason"])
        print(f"[Test 4] 未突破整理高点过滤成功: {res['reason']}")

    def test_05_batch_scan_engine(self):
        """测试全市场 / 多标的批量扫描引擎"""
        stock_dfs = {
            "688826": generate_mock_60m_df("valid_reversal"),
            "920012": generate_mock_60m_df("valid_reversal"),
            "301655": generate_mock_60m_df("broken_new_low"),
            "000001": generate_mock_60m_df("no_volume_shrink"),
            "600519": generate_mock_60m_df("no_breakout")
        }
        df_scan = self.strategy.scan_batch(stock_dfs)
        self.assertIsInstance(df_scan, pd.DataFrame)
        self.assertEqual(len(df_scan), 2)
        self.assertEqual(set(df_scan["code"]), {"688826", "920012"})
        print(f"[Test 5] 批量扫描成功: 命中 {len(df_scan)} 只标的")

    def test_06_extreme_performance_benchmark(self):
        """极限性能基准测试: 测算单次调用平均耗时"""
        df = generate_mock_60m_df("valid_reversal", n_bars=80)
        
        # 预热 JIT / 缓存
        for _ in range(20):
            _ = evaluate_channel_bottom_reversal(df)

        loops = 2000
        t0 = time.perf_counter()
        for _ in range(loops):
            _ = evaluate_channel_bottom_reversal(df)
        t_total = time.perf_counter() - t0
        avg_ms = (t_total / loops) * 1000.0

        print(f"[Test 6] 极限性能基准: 运行 {loops} 次测算, 总耗时 {t_total:.3f}s, 单次平均耗时 {avg_ms:.4f} ms")
        self.assertLess(avg_ms, 1.5, "单次测算耗时应在极速微秒/毫秒级别")


if __name__ == "__main__":
    unittest.main()
