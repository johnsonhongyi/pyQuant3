# -*- coding: utf-8 -*-
"""
自动化测试：
1. 验证 QToolTip 在 DARK_THEME_QSS 及 QApplication Palette 中的高对比色彩保真（绝对防黑字）；
2. 验证东方财富新股限售解禁日历单次同步机制（绝对杜绝无线重复请求被封 IP）。
"""
import unittest
import os
import sys
import json
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QPalette, QColor


class TestTooltipAndLiftCalendarSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_tooltip_qss_and_palette_fidelity(self):
        """测试 1: 验证 QToolTip 样式与调色板高对比暗黑金融质感，防范黑字看不清"""
        from ats.ui.styles import DARK_THEME_QSS, apply_dark_theme

        # 1. 验证 DARK_THEME_QSS 中显式声明了 QToolTip 规则
        self.assertIn("QToolTip", DARK_THEME_QSS)
        self.assertIn("background-color: #1a1a24;", DARK_THEME_QSS)
        self.assertIn("color: #f1f5f9;", DARK_THEME_QSS)

        # 2. 验证 apply_dark_theme 正确注入了 QApplication 全局调色板
        dummy_widget = QWidget()
        apply_dark_theme(dummy_widget)

        pal = self.app.palette()
        tip_text_color = pal.color(QPalette.ColorRole.ToolTipText).name().lower()
        tip_base_color = pal.color(QPalette.ColorRole.ToolTipBase).name().lower()

        self.assertEqual(tip_text_color, "#f1f5f9", "ToolTipText 必须为明亮冰白色，杜绝 Windows 默认黑字")
        self.assertEqual(tip_base_color, "#1a1a24", "ToolTipBase 必须为暗黑金融微光底色")

    def test_02_lift_calendar_single_sync_and_cache_reuse(self):
        """测试 2: 验证限售解禁日历单次同步与缓存绝对复用，杜绝高频请求被封 IP"""
        from ats.new_stock_fetcher import NewStockFetcher

        fetcher = NewStockFetcher.get_instance()
        codes = ["601091", "301686", "920201", "301716", "920229", "001246", "920025"]

        # 1. 首次获取（已从磁盘清洗后加载）
        t0 = time.time()
        res1 = fetcher.fetch_restricted_release_calendar(codes, force=False)
        t1 = time.time()

        self.assertIsInstance(res1, dict)
        for c in codes:
            self.assertIn(c, res1, f"标的 {c} 必须在解禁字典中")
            self.assertTrue(res1[c].get("lift_stage"), f"标的 {c} 必须具有 lift_stage 字段，防止缺失判断")

        # 2. 紧接着二次获取，验证耗时极短 (< 0.05s) 且绝对不发起网络请求
        res2 = fetcher.fetch_restricted_release_calendar(codes, force=False)
        t2 = time.time()

        self.assertLess(t2 - t1, 0.05, "二次获取必须直接命中内存缓存返回，严禁发起网络请求")
        self.assertEqual(res1, res2)


if __name__ == "__main__":
    unittest.main()
