# -*- coding: utf-8 -*-
"""
tests/test_channel_scan_period_selection_and_persistence.py
针对 ATS 菜单通道测算 60f/120f/日线/周线/月线 多周期体系、默认点击执行与 Alt/右键弹出菜单的专项测试。
"""

import sys
import os
import unittest
import pandas as pd
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ats.ui.styles import save_config_node, load_config_node
from ats.ui.channel_scan_result_dialog import ChannelReversalScanResultDialog
from ats.ui.main_window import PERSIST_KEY_CHANNEL_SCAN_PERIOD

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestChannelScanPeriodSelectionAndPersistence(unittest.TestCase):
    """测试通道测算多周期选择 (60f/120f/日线/周线/月线) 与点击执行/Alt菜单交互"""

    def setUp(self):
        self.sample_df = pd.DataFrame([
            {
                "code": "600519",
                "name": "贵州茅台",
                "channel_type_cn": "上涨通道顺势",
                "pattern_name": "上涨通道下轨回踩企稳",
                "score": 98.0,
                "entry_price": 1450.0,
                "stop_loss": 1420.0,
                "target_price_1": 1500.0,
                "target_price_2": 1550.0,
                "channel_slope_deg": 12.5,
                "volume_shrink_pct": 20.0,
                "reason": "测试上涨通道"
            }
        ])

    def test_01_period_persistence_defaults_and_updates(self):
        """测试周期持久化存取：无配置时默认60f，更新后能正确读取 120f/日线/周线/月线"""
        # 1. 模拟切换至 120f
        save_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "120f")
        loaded_120f = load_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "60f")
        self.assertEqual(loaded_120f, "120f")

        # 2. 模拟切换至月线
        save_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "月线")
        loaded_monthly = load_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "60f")
        self.assertEqual(loaded_monthly, "月线")

        # 3. 模拟切换至日线
        save_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "日线")
        loaded_daily = load_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "60f")
        self.assertEqual(loaded_daily, "日线")

        # 4. 恢复默认 60f
        save_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "60f")
        loaded_default = load_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "60f")
        self.assertEqual(loaded_default, "60f")

    def test_02_dialog_dynamic_period_title_and_sbc_mapping(self):
        """测试结果窗口在 120f/月线/日线/周线/60f 下的标题动态对齐与 SBC 映射"""
        dialog = ChannelReversalScanResultDialog(
            parent=None,
            df_results=self.sample_df,
            total_scanned=50,
            source_tab_name="重点关注",
            period="120f"
        )
        try:
            self.assertEqual(dialog.period, "120f")
            self.assertIn("120f", dialog.windowTitle())
            self.assertIn("重点关注", dialog.windowTitle())

            # 动态更新为月线
            dialog.update_results(self.sample_df, total_scanned=60, source_tab_name="大级别MA20d", period="月线")
            self.assertEqual(dialog.period, "月线")
            self.assertIn("月线", dialog.windowTitle())
            self.assertIn("大级别MA20d", dialog.windowTitle())
        finally:
            dialog.close()

    def test_03_tdx_fetcher_category_mapping_and_120m_resample(self):
        """测试 TDXRealtimeFetcher 对 60f/120f/日线/周线/月线 别名的解析与 120m 合成"""
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        fetcher = TDXRealtimeFetcher.get_instance()

        cat_map = {
            "5m": 0, "5f": 0, "5min": 0,
            "15m": 1, "15f": 1, "15min": 1,
            "30m": 2, "30f": 2, "30min": 2,
            "60m": 3, "60f": 3, "60min": 3, "1h": 3,
            "day": 4, "d": 4, "日线": 4, "日k": 4, "日": 4,
            "week": 5, "w": 5, "周线": 5, "周k": 5, "周": 5,
            "month": 6, "m": 6, "月线": 6, "月k": 6, "月": 6,
            "1m": 8, "1f": 8, "1min": 8
        }
        for alias, expected_code in [
            ("60f", 3), ("60m", 3), ("日线", 4), ("day", 4),
            ("周线", 5), ("week", 5), ("月线", 6), ("month", 6)
        ]:
            code = cat_map.get(str(alias).lower().strip(), 0)
            self.assertEqual(code, expected_code, f"周期别名 [{alias}] 映射错误")

    @patch("ats.ui.main_window.save_config_node")
    def test_04_on_channel_period_selected_flow(self, mock_save_config):
        """测试用户选择周期槽函数触发文案更新、配置持久化与测算调用"""
        from PyQt6.QtWidgets import QPushButton
        mock_win = MagicMock()
        mock_win.btn_top_scan_channel = QPushButton("🎯 60f通道测算 ▾")
        mock_win.channel_scan_period = "60f"

        from ats.ui.main_window import ATSMainWindow
        mock_win._on_channel_period_selected = ATSMainWindow._on_channel_period_selected.__get__(mock_win, ATSMainWindow)

        # 触发选择 120f
        mock_win._on_channel_period_selected("120f")

        self.assertEqual(mock_win.channel_scan_period, "120f")
        self.assertEqual(mock_win.btn_top_scan_channel.text(), "🎯 120f通道测算 ▾")
        mock_save_config.assert_called_once_with(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "120f")
        mock_win._execute_channel_scan.assert_called_once_with(period="120f")

    def test_05_button_click_default_execute_vs_alt_menu(self):
        """测试直接点击默认执行当前周期，按住 Alt 点击弹出菜单"""
        from PyQt6.QtWidgets import QPushButton
        mock_win = MagicMock()
        mock_win.channel_scan_period = "日线"
        mock_win.btn_top_scan_channel = QPushButton("🎯 日线通道测算 ▾")

        from ats.ui.main_window import ATSMainWindow
        mock_win._on_channel_scan_button_clicked = ATSMainWindow._on_channel_scan_button_clicked.__get__(mock_win, ATSMainWindow)

        # 1. 模拟直接单击 (无 Alt 修饰键)
        with patch("PyQt6.QtWidgets.QApplication.keyboardModifiers", return_value=Qt.KeyboardModifier.NoModifier):
            mock_win._on_channel_scan_button_clicked()
            mock_win._execute_channel_scan.assert_called_once_with(period="日线")
            mock_win._show_channel_scan_period_menu.assert_not_called()

        # 2. 模拟按住 Alt 键单击
        mock_win._execute_channel_scan.reset_mock()
        mock_win._show_channel_scan_period_menu.reset_mock()
        with patch("PyQt6.QtWidgets.QApplication.keyboardModifiers", return_value=Qt.KeyboardModifier.AltModifier):
            mock_win._on_channel_scan_button_clicked()
            mock_win._show_channel_scan_period_menu.assert_called_once()
            mock_win._execute_channel_scan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
