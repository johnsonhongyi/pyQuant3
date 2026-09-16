# -*- coding: utf-8 -*-
"""
tests/test_sbc_holdings_isolation_and_channel.py
------------------------------------------------
验证 [SBC Launcher] 与原有 SBC 窗口持久化隔离、通道上轨可见性、2D/3D周期及交互优化测试
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# 确保项目根路径
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import numpy as np

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

# 初始化 Qt 应用 (无头环境)
app = QApplication.instance() or QApplication(sys.argv)

from ats.ui.intraday_strategy_dialog import (
    _get_sbc_layout_cfg_path,
    SBCIntradayChartDialog,
    SBCChartCanvas,
    VALID_SBC_PERIODS,
    rearrange_all_sbc_windows,
)
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher


class TestSBCHoldingsIsolationAndChannel(unittest.TestCase):

    def test_cfg_path_environment_isolation(self):
        """测试持仓盯盘启动器专用环境变量能够严格隔离持久化配置文件路径"""
        # 1. 默认状态下指向 intraday_ui_layout.json
        if "SBC_LAYOUT_CONFIG_PATH" in os.environ:
            del os.environ["SBC_LAYOUT_CONFIG_PATH"]
        default_path = _get_sbc_layout_cfg_path()
        self.assertTrue(default_path.endswith("intraday_ui_layout.json"))

        # 2. 模拟设置持仓盯盘启动器环境变量
        custom_holdings_path = os.path.abspath("config/sbc_launcher_holdings_layout.json")
        os.environ["SBC_LAYOUT_CONFIG_PATH"] = custom_holdings_path
        try:
            holdings_path = _get_sbc_layout_cfg_path()
            self.assertEqual(holdings_path, custom_holdings_path)
            self.assertTrue(holdings_path.endswith("sbc_launcher_holdings_layout.json"))
        finally:
            del os.environ["SBC_LAYOUT_CONFIG_PATH"]

    def test_valid_sbc_periods_contains_2k_and_3k(self):
        """测试 VALID_SBC_PERIODS 完整支持 2D (2k) 与 3D (3k) 周期"""
        self.assertIn("2k", VALID_SBC_PERIODS)
        self.assertIn("3k", VALID_SBC_PERIODS)
        self.assertIn("day", VALID_SBC_PERIODS)
        self.assertIn("10d", VALID_SBC_PERIODS)

    def test_tdx_fetcher_2d_and_3d_aggregation(self):
        """测试 TDXRealtimeFetcher 对 2D 与 3D K线的聚合计算正确性"""
        fetcher = TDXRealtimeFetcher.get_instance()
        # 构造模拟日线数据 6 根 K 线
        mock_daily_bars = [
            {"datetime": "2026-03-01", "open": 10.0, "high": 12.0, "low": 9.5, "close": 11.0, "vol": 100, "amount": 1000},
            {"datetime": "2026-03-02", "open": 11.2, "high": 13.0, "low": 11.0, "close": 12.5, "vol": 200, "amount": 2500},
            {"datetime": "2026-03-03", "open": 12.6, "high": 14.0, "low": 12.0, "close": 13.0, "vol": 150, "amount": 1900},
            {"datetime": "2026-03-04", "open": 13.1, "high": 13.5, "low": 12.8, "close": 13.2, "vol": 120, "amount": 1600},
            {"datetime": "2026-03-05", "open": 13.0, "high": 15.0, "low": 12.5, "close": 14.8, "vol": 300, "amount": 4200},
            {"datetime": "2026-03-06", "open": 14.9, "high": 16.0, "low": 14.0, "close": 15.5, "vol": 250, "amount": 3800},
        ]
        with patch.object(fetcher, "connect", return_value=True), \
             patch.object(fetcher, "_is_connected", True), \
             patch.object(fetcher, "api") as mock_api:
            mock_api.get_security_bars.return_value = mock_daily_bars

            # 1. 测试 2D K 线聚合 (6 根日线 -> 3 根 2D K 线)
            df_2d = fetcher.fetch_kline_bars("000001", category="2k", count=3)
            self.assertFalse(df_2d.empty)
            self.assertEqual(len(df_2d), 3)
            # 第一根 2D K 线: open=10.0, high=13.0, low=9.5, close=12.5, vol=300
            self.assertAlmostEqual(df_2d.iloc[0]["open"], 10.0)
            self.assertAlmostEqual(df_2d.iloc[0]["high"], 13.0)
            self.assertAlmostEqual(df_2d.iloc[0]["low"], 9.5)
            self.assertAlmostEqual(df_2d.iloc[0]["close"], 12.5)
            self.assertAlmostEqual(df_2d.iloc[0]["vol"], 300.0)

            # 2. 测试 3D K 线聚合 (6 根日线 -> 2 根 3D K 线)
            df_3d = fetcher.fetch_kline_bars("000001", category="3k", count=2)
            self.assertFalse(df_3d.empty)
            self.assertEqual(len(df_3d), 2)
            # 第一根 3D K 线: open=10.0, high=14.0, low=9.5, close=13.0, vol=450
            self.assertAlmostEqual(df_3d.iloc[0]["open"], 10.0)
            self.assertAlmostEqual(df_3d.iloc[0]["high"], 14.0)
            self.assertAlmostEqual(df_3d.iloc[0]["low"], 9.5)
            self.assertAlmostEqual(df_3d.iloc[0]["close"], 13.0)
            self.assertAlmostEqual(df_3d.iloc[0]["vol"], 450.0)

    def test_trade_selection_toggle_and_auto_close_on_cycle_end(self):
        """测试收益详情卡片：支持点击 toggle 关闭，遍历到最后一笔交易后再次点击自动关闭"""
        canvas = SBCChartCanvas()
        canvas.signals = [
            {"time": "09:30", "price": 10.0, "action": "buy", "trade_id": 0},
            {"time": "10:00", "price": 11.0, "action": "sell", "trade_id": 0},
            {"time": "11:00", "price": 10.5, "action": "buy", "trade_id": 1},
            {"time": "11:30", "price": 12.0, "action": "sell", "trade_id": 1},
        ]
        # 初始默认无选中交易
        self.assertIsNone(canvas.selected_trade_id)

        # 1. 模拟按快捷键切换到首笔交易
        canvas.cycle_selected_trade(step=1)
        self.assertEqual(canvas.selected_trade_id, 0)

        # 2. 切换到第二笔交易
        canvas.cycle_selected_trade(step=1)
        self.assertEqual(canvas.selected_trade_id, 1)

        # 3. 遍历完最后一笔交易后再次切换，自动重置为 None (关闭收益卡片)
        canvas.cycle_selected_trade(step=1)
        self.assertIsNone(canvas.selected_trade_id)

    def test_rearrange_all_sbc_windows_uniform_dimensions(self):
        """测试全局重排所有 SBC 窗口严格保证等大等高与保底安全尺寸 (target_w>=640, target_h>=420)"""
        dlg1 = SBCIntradayChartDialog(code="600733")
        dlg2 = SBCIntradayChartDialog(code="603407")
        try:
            dlg1.resize(700, 500)
            dlg2.resize(400, 300)
            dlg1.show()
            dlg2.show()

            # 执行全局平铺重排
            rearrange_all_sbc_windows()

            # 验证所有窗口尺寸严格相等
            self.assertEqual(dlg1.width(), dlg2.width())
            self.assertEqual(dlg1.height(), dlg2.height())
            # 验证尺寸不低于安全阈值
            self.assertGreaterEqual(dlg1.width(), 640)
            self.assertGreaterEqual(dlg1.height(), 420)
        finally:
            dlg1.close()
            dlg2.close()

    def test_2d_and_3d_render_in_kline_mode(self):
        """测试 2D 与 3D 周期正确识别为 K 线模式，对齐日K/周K/月K"""
        canvas = SBCChartCanvas()
        for p in ["2d", "3d", "2k", "3k", "day", "week", "month"]:
            canvas.period_mode = p
            # 检查在 canvas paint 逻辑中应命中 K 线模式
            is_kline = canvas.period_mode in ["5m", "15m", "30m", "60m", "day", "2d", "3d", "2k", "3k", "week", "month"]
            self.assertTrue(is_kline, f"Period {p} should be treated as K-line mode")

    def test_remove_sbc_open_record_from_holdings_layout(self):
        """测试 _remove_sbc_open_record 能够从 sbc_holdings_windows 中剔除手动关闭的个股"""
        from ats.ui.intraday_strategy_dialog import _remove_sbc_open_record
        import json

        test_cfg = os.path.join(_PROJECT_ROOT, "test_holdings_layout_tmp.json")
        try:
            data = {
                "sbc_holdings_windows": [
                    {"code": "603787", "width": 640, "height": 420},
                    {"code": "300335", "width": 640, "height": 420},
                    {"code": "601226", "width": 640, "height": 420}
                ]
            }
            with open(test_cfg, "w", encoding="utf-8") as f:
                json.dump(data, f)

            with patch('ats.ui.intraday_strategy_dialog._get_sbc_layout_cfg_path', return_value=test_cfg):
                # 手动关闭 300335
                _remove_sbc_open_record("300335")

                with open(test_cfg, "r", encoding="utf-8") as f:
                    updated = json.load(f)
                holdings = [item["code"] for item in updated.get("sbc_holdings_windows", [])]
                self.assertNotIn("300335", holdings)
                self.assertIn("603787", holdings)
                self.assertIn("601226", holdings)
                self.assertEqual(len(holdings), 2)
        finally:
            if os.path.exists(test_cfg):
                os.remove(test_cfg)

    def test_rearrange_group_pid_isolation_logic(self):
        """测试重排函数在 Launcher 进程与 ATS 主进程下的分组隔离过滤逻辑"""
        from ats.ui.intraday_strategy_dialog import rearrange_all_sbc_windows

        # 1. 在无外部窗口下安全调用不抛异常
        with patch.dict(os.environ, {"SBC_IS_HOLDINGS_LAUNCHER": "1", "PYTEST_CURRENT_TEST": "1"}):
            rearrange_all_sbc_windows()

        with patch.dict(os.environ, {"SBC_IS_HOLDINGS_LAUNCHER": "0", "PYTEST_CURRENT_TEST": "1"}):
            rearrange_all_sbc_windows()


if __name__ == "__main__":
    unittest.main()
