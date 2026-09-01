# -*- coding: UTF-8 -*-
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import singleAnalyseUtil as sau
from JohnsonUtil import commonTips as cct


class TestSingleAnalyseRzrq(unittest.TestCase):
    """测试 singleAnalyseUtil 中两融交易日计算与开盘前/后自动感知逻辑"""

    def test_pre_market_date(self):
        # 交易日开盘前 (如凌晨 02:00 或 09:14) 记录上一交易日
        res_midnight = sau.get_expected_rzrq_date('2026-09-01', 200)
        res_pre = sau.get_expected_rzrq_date('2026-09-01', 914)
        self.assertEqual(res_midnight, '2026-08-31')
        self.assertEqual(res_pre, '2026-08-31')

    def test_open_market_date(self):
        # 交易日开盘后 (如 09:15 或 10:30) 记录今日
        res_open = sau.get_expected_rzrq_date('2026-09-01', 915)
        res_intraday = sau.get_expected_rzrq_date('2026-09-01', 1030)
        res_post = sau.get_expected_rzrq_date('2026-09-01', 1530)
        self.assertEqual(res_open, '2026-09-01')
        self.assertEqual(res_intraday, '2026-09-01')
        self.assertEqual(res_post, '2026-09-01')

    def test_weekend_date(self):
        # 非交易日 (周六 2026-09-05) 记录最近交易日
        res_weekend = sau.get_expected_rzrq_date('2026-09-05', 1030)
        self.assertEqual(res_weekend, '2026-09-04')


if __name__ == '__main__':
    unittest.main()
