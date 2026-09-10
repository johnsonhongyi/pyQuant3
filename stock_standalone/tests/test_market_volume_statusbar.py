# -*- coding: utf-8 -*-
"""
tests/test_market_volume_statusbar.py — 大盘四大指数资金量比与全市交易额增减测试用例
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import datetime
import pandas as pd
import numpy as np

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QLabel, QStatusBar
from PyQt6.QtCore import Qt

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication([])

from ats.capital_dragon_engine import CapitalDragonEngine


class TestMarketVolumeEngineAndStatusBar(unittest.TestCase):

    def setUp(self):
        self.engine = CapitalDragonEngine.get_instance()
        with self.engine._cache_lock:
            # 清理引擎缓存
            self.engine._market_summary_cache = None
            self.engine._market_summary_cache_ts = 0.0

    def test_01_extract_indices_and_volume_from_df_all(self):
        """测试从 df_all 中提取上证、深证、创业板、北证的资金、量比及全市总交易额"""
        mock_records = [
            {"code": "999999", "name": "上证指数", "amount": 7796.7e8, "vol_ratio": 0.94},
            {"code": "399001", "name": "深证成指", "amount": 8674.8e8, "vol_ratio": 0.93},
            {"code": "399006", "name": "创业板指", "amount": 3840.6e8, "vol_ratio": 0.91},
            {"code": "899050", "name": "北证50",   "amount": 153.7e8,  "vol_ratio": 0.90},
            {"code": "600000", "name": "浦发银行", "amount": 12.5e8,   "vol_ratio": 1.15},
        ]
        df_all = pd.DataFrame(mock_records).set_index("code", drop=False)

        # 模拟昨日总成交额 (如昨日总计 18732.5 亿)
        today_str = "2026-09-10"
        self.engine._yesterday_index_amounts = {
            'sh': 8500.0, 'sz': 10050.0, 'cy': 4200.0, 'bj': 182.5,
            'total': 18732.5,
            'vol_sh': 1000.0, 'vol_sz': 1200.0, 'vol_cy': 500.0, 'vol_bj': 20.0
        }
        self.engine._yesterday_cache_date = today_str

        # 1. 盘后测试 (hour >= 15)
        now_dt = datetime.datetime(2026, 9, 10, 15, 30, 0)
        res = self.engine.get_market_indices_and_volume_summary(df_all, now_dt=now_dt)

        self.assertAlmostEqual(res["sh_amt"], 7796.7, places=1)
        self.assertAlmostEqual(res["sh_vr"], 0.94, places=2)
        self.assertAlmostEqual(res["sz_amt"], 8674.8, places=1)
        self.assertAlmostEqual(res["sz_vr"], 0.93, places=2)
        self.assertAlmostEqual(res["cy_amt"], 3840.6, places=1)
        self.assertAlmostEqual(res["cy_vr"], 0.91, places=2)
        self.assertAlmostEqual(res["bj_amt"], 153.7, places=1)
        self.assertAlmostEqual(res["bj_vr"], 0.90, places=2)

        # 官方全市成交额口径: 沪市 + 深市 + 北交所
        expected_total = round(7796.7 + 8674.8 + 153.7, 1) # 16625.2
        self.assertAlmostEqual(res["total_amt"], expected_total, places=1)

        # 盘后较昨日增减额: 16625.2 - 18732.5 = -2107.3亿
        expected_diff = round(expected_total - 18732.5, 1)
        self.assertAlmostEqual(res["diff_amt"], expected_diff, places=1)
        self.assertEqual(res["diff_str"], f"{expected_diff:.1f}亿")

        # HTML 与 纯文本检查
        self.assertIn("上证:", res["formatted_html"])
        self.assertIn("7796.7亿", res["formatted_html"])
        self.assertIn("(0.94x)", res["formatted_html"])
        self.assertIn("深证:", res["formatted_html"])
        self.assertIn("8674.8亿", res["formatted_html"])
        self.assertIn("(0.93x)", res["formatted_html"])
        self.assertIn("创业板:", res["formatted_html"])
        self.assertIn("3840.6亿", res["formatted_html"])
        self.assertIn("(0.91x)", res["formatted_html"])
        self.assertIn("北证:", res["formatted_html"])
        self.assertIn("153.7亿", res["formatted_html"])
        self.assertIn("(0.90x)", res["formatted_html"])
        self.assertIn("全市:", res["formatted_html"])
        self.assertIn(f"{expected_total:.1f}亿", res["formatted_html"])
        self.assertIn(f"(较昨 {expected_diff:.1f}亿)", res["formatted_html"])

    def test_02_intraday_volume_difference_with_work_time_ratio(self):
        """测试盘中时段按工作时间比例计算同比增减额"""
        mock_records = [
            {"code": "999999", "name": "上证指数", "amount": 2000.0e8, "vol_ratio": 1.20},
            {"code": "399001", "name": "深证成指", "amount": 2500.0e8, "vol_ratio": 1.25},
            {"code": "399006", "name": "创业板指", "amount": 1000.0e8, "vol_ratio": 1.18},
            {"code": "899050", "name": "北证50",   "amount": 50.0e8,   "vol_ratio": 1.10},
        ]
        df_all = pd.DataFrame(mock_records).set_index("code", drop=False)

        # 模拟昨日总成交额为 18000.0 亿
        self.engine._yesterday_index_amounts = {
            'sh': 8000.0, 'sz': 9800.0, 'cy': 4000.0, 'bj': 200.0,
            'total': 18000.0
        }
        self.engine._yesterday_cache_date = "2026-09-10"

        # 模拟盘中 10:00 (ratio_t = 0.25)
        now_dt = datetime.datetime(2026, 9, 10, 10, 0, 0)
        with patch("JohnsonUtil.commonTips.get_work_time_ratio", return_value="0.25"):
            res = self.engine.get_market_indices_and_volume_summary(df_all, now_dt=now_dt)

        # 今日盘中此时全市: 2000 + 2500 + 50 = 4550.0 亿
        # 昨日同期基准: 18000.0 * 0.25 = 4500.0 亿
        # 较昨增减: 4550.0 - 4500.0 = +50.0 亿 (放量)
        self.assertAlmostEqual(res["total_amt"], 4550.0, places=1)
        self.assertAlmostEqual(res["diff_amt"], 50.0, places=1)
        self.assertEqual(res["diff_str"], "+50.0亿")
        self.assertIn("+50.0亿", res["formatted_html"])
        self.assertIn("#ff5555", res["formatted_html"]) # 放量红色高亮

    def test_03_cache_debounce_behavior(self):
        """测试 1.5 秒轻量防抖缓存机制"""
        mock_records = [
            {"code": "999999", "amount": 1000.0e8, "vol_ratio": 1.0},
            {"code": "399001", "amount": 1000.0e8, "vol_ratio": 1.0},
            {"code": "399006", "amount": 500.0e8,  "vol_ratio": 1.0},
            {"code": "899050", "amount": 10.0e8,   "vol_ratio": 1.0},
        ]
        df_all = pd.DataFrame(mock_records).set_index("code", drop=False)

        res1 = self.engine.get_market_indices_and_volume_summary(df_all)
        # 立即不带 df_all 获取，应命中缓存
        res2 = self.engine.get_market_indices_and_volume_summary(None)
        self.assertEqual(res1["total_amt"], res2["total_amt"])
        self.assertEqual(res1["formatted_html"], res2["formatted_html"])

    def test_04_status_bar_ui_integration(self):
        """测试 MainWindow 状态栏常驻控件的初始化与动态刷新"""
        from ats.ui.main_window import ATSMainWindow

        # 模拟主窗口轻量实例
        mock_win = MagicMock()
        mock_win.status_bar = QStatusBar()
        mock_win.lbl_market_volume_status = QLabel()
        mock_win.current_df = pd.DataFrame([
            {"code": "999999", "name": "上证指数", "amount": 7700.0e8, "vol_ratio": 1.05},
            {"code": "399001", "name": "深证成指", "amount": 8800.0e8, "vol_ratio": 1.02},
            {"code": "399006", "name": "创业板指", "amount": 3500.0e8, "vol_ratio": 0.98},
            {"code": "899050", "name": "北证50",   "amount": 160.0e8,  "vol_ratio": 1.10},
        ]).set_index("code", drop=False)

        # 绑定 ATSMainWindow 的 _refresh_market_volume_status 方法
        mock_win._refresh_market_volume_status = ATSMainWindow._refresh_market_volume_status.__get__(mock_win, ATSMainWindow)

        # 执行刷新
        mock_win._refresh_market_volume_status()

        # 验证控件文本成功更新
        rendered_text = mock_win.lbl_market_volume_status.text()
        self.assertIn("上证:", rendered_text)
        self.assertIn("深证:", rendered_text)
        self.assertIn("创业板:", rendered_text)
        self.assertIn("北证:", rendered_text)
        self.assertIn("全市:", rendered_text)
        self.assertIn("亿", rendered_text)


if __name__ == "__main__":
    unittest.main()
