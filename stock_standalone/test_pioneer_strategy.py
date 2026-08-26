# -*- coding: utf-8 -*-
"""
测试与验证逆势企稳先锋策略 (EarlyStabilizationPioneerStrategy)
"""
import unittest
import os
import sys
import io

# 确保 stdout 支持 UTF-8
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from early_stabilization_pioneer_strategy import EarlyStabilizationPioneerStrategy
from stock_selector import StockSelector


class TestPioneerStrategy(unittest.TestCase):
    
    def setUp(self):
        self.strategy = EarlyStabilizationPioneerStrategy()
        
    def _create_mock_divergence_data(self, is_pioneer: bool = True) -> pd.DataFrame:
        """
        构造模拟日K线数据:
        - 前期下跌触底
        - 底部抬高 (Higher Low)
        - 均线收敛
        - 启动日放量一阳穿多线突破
        """
        n = 40
        dates = pd.date_range(end=datetime.now(), periods=n, freq='D')
        
        # 基础价格走势
        # 前15天: 从 30 跌到 20 (触底 L1)
        # 中间15天: 反弹到 23 再回踩到 21 (触底 L2, 21 > 20, 底抬高)
        # 最后10天: 在 21-23 窄幅震荡，均线粘合
        prices = [30.0 - i * 0.67 for i in range(15)] # 30 -> 20.0
        prices += [20.0 + i * 0.4 for i in range(7)]  # 20 -> 22.8
        prices += [22.8 - i * 0.25 for i in range(8)] # 22.8 -> 20.8 (底抬高 L2=20.8 > 20.0)
        prices += [21.0 + (i % 3) * 0.3 for i in range(9)] # 21.0~21.6 窄幅收敛
        
        if is_pioneer:
            # 第40天 (最后一天): 大阳线启动突破 23.5 (放量突破平台)
            prices.append(24.2)
        else:
            # 弱势继续跌破
            prices.append(19.5)
            
        df = pd.DataFrame(index=dates)
        df['close'] = prices
        df['open'] = [p - 0.2 for p in prices]
        df['high'] = [p + 0.3 for p in prices]
        df['low'] = [p - 0.4 for p in prices]
        df['volume'] = [10000.0] * (n - 1) + [25000.0 if is_pioneer else 8000.0]
        df['name'] = '测试先锋'
        
        return df

    def test_pioneer_detection_positive(self):
        """测试阳性样本：成功触发逆势先锋信号"""
        df = self._create_mock_divergence_data(is_pioneer=True)
        signals = self.strategy.evaluate_historical("300927", df)
        self.assertGreater(len(signals), 0, "应当成功识别出逆势先锋启动形态")
        sig = signals[0]
        self.assertIn("逆势先锋启动", sig.reason)
        self.assertEqual(sig.code, "300927")
        print(f"[PASS] 成功触发信号: {sig.reason}")

    def test_pioneer_detection_negative(self):
        """测试阴性样本：破位下跌不应触发"""
        df = self._create_mock_divergence_data(is_pioneer=False)
        signals = self.strategy.evaluate_historical("000001", df)
        self.assertEqual(len(signals), 0, "破位或无放量形态不应触发信号")
        print("[PASS] 阴性样本未误报，符合预期")

    def test_selector_pioneer_method(self):
        """测试 StockSelector 的先锋选股接口"""
        selector = StockSelector()
        df_mock = pd.DataFrame({
            'code': ['300927', '688828', '000001'],
            'name': ['江天化学', '国仪公司', '平安银行'],
            'close': [24.23, 89.59, 10.5],
            'open': [22.39, 79.95, 10.5],
            'percent': [6.98, 10.39, -0.5],
            'ratio': [2.12, 2.20, 0.8],
            'volume': [139671, 110986, 50000],
            'vol': [139671, 110986, 50000],
            'ma5': [22.8, 81.0, 10.6],
            'ma10': [22.45, 80.2, 10.7],
            'ma20': [22.08, 79.8, 10.8],
        })
        res = selector.select_early_stabilization_pioneer(df_mock, top_n=10)
        self.assertFalse(res.empty)
        self.assertIn('300927', res['code'].values)
        self.assertIn('688828', res['code'].values)
        self.assertNotIn('000001', res['code'].values)
        print(f"[PASS] 选股器成功筛选出先锋标的: {res['code'].tolist()}")



if __name__ == '__main__':
    unittest.main()
