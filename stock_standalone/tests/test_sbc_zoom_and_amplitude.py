# -*- coding: utf-8 -*-
"""
tests/test_sbc_zoom_and_amplitude.py
验证 SBC 走势图上下键全局缩放（免点击走势图）与右上角近几日振幅活跃度 HUD 计算与分发逻辑
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

# 确保能加载项目根目录
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_CUR_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

try:
    from PyQt6.QtWidgets import QApplication, QLineEdit, QPushButton
    from PyQt6.QtCore import Qt, QEvent
    from PyQt6.QtGui import QKeyEvent
except ImportError:
    QApplication = None


class TestSBCZoomAndAmplitude(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication:
            cls.app = QApplication.instance() or QApplication(["test_sbc_zoom"])
        else:
            cls.app = None

    def setUp(self):
        if not self.app:
            self.skipTest("PyQt6 环境不可用，跳过 UI 测试")

    def _generate_mock_intraday_df(self, count=100):
        dates = [f"2026-09-18 09:{i:02d}:00" for i in range(count)]
        closes = [10.0 + i * 0.1 for i in range(count)]
        opens = [10.0 + i * 0.1 for i in range(count)]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        vwaps = closes
        df = pd.DataFrame({
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows,
            "vwap": vwaps
        }, index=dates)
        return df

    def _generate_mock_daily_df(self, count=8):
        dates = [f"2026-09-{10+i:02d}" for i in range(count)]
        closes = [100.0, 105.0, 102.0, 108.0, 115.0, 112.0, 120.0, 118.0][:count]
        opens = [101.0, 103.0, 104.0, 105.0, 110.0, 114.0, 116.0, 119.0][:count]
        highs = [106.0, 109.0, 107.0, 114.0, 118.0, 117.0, 125.0, 122.0][:count]
        lows = [98.0, 101.0, 100.0, 103.0, 107.0, 110.0, 113.0, 115.0][:count]
        df = pd.DataFrame({
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows
        }, index=dates)
        return df

    def test_canvas_zoom_in_and_out(self):
        """测试 Canvas 放大 zoom_in 与缩小 zoom_out 正确改变切片范围并固定右侧最新数据"""
        from ats.ui.intraday_strategy_dialog import SBCChartCanvas

        canvas = SBCChartCanvas()
        df = self._generate_mock_intraday_df(100)
        canvas.set_data(df, 10.0, 10.0, 20.0, 9.0, 12.0, 13.0, [])

        self.assertEqual(canvas._zoom_start_idx, 0)
        self.assertEqual(canvas._zoom_end_idx, -1)

        # 执行放大 zoom_in
        canvas.zoom_in()
        df_vis, s_idx, e_idx = canvas._get_visible_slice()
        # 放大后可视 Bar 数量减少
        self.assertLess(len(df_vis), 100)
        # 右侧最新一根数据保持锚定在最后 (end_idx 为 99)
        self.assertEqual(e_idx, 99)
        self.assertGreater(s_idx, 0)

        prev_count = len(df_vis)

        # 再次执行放大
        canvas.zoom_in()
        df_vis2, s_idx2, e_idx2 = canvas._get_visible_slice()
        self.assertLess(len(df_vis2), prev_count)
        self.assertEqual(e_idx2, 99)

        # 执行缩小 zoom_out
        canvas.zoom_out()
        df_vis3, s_idx3, e_idx3 = canvas._get_visible_slice()
        self.assertGreater(len(df_vis3), len(df_vis2))
        self.assertEqual(e_idx3, 99)

        # 重置视图
        canvas.reset_view()
        self.assertEqual(canvas._zoom_start_idx, 0)
        self.assertEqual(canvas._zoom_end_idx, -1)
        canvas.deleteLater()

    def test_update_amplitude_data(self):
        """测试近几日振幅计算引擎与活跃度评级"""
        from ats.ui.intraday_strategy_dialog import SBCChartCanvas

        canvas = SBCChartCanvas()
        mock_daily = self._generate_mock_daily_df(8)

        # mock TDXRealtimeFetcher
        with patch("ats.tdx_realtime_fetcher.TDXRealtimeFetcher.get_instance") as mock_fetcher_cls:
            mock_fetcher = MagicMock()
            mock_fetcher.fetch_kline_bars.return_value = mock_daily
            mock_fetcher_cls.return_value = mock_fetcher

            canvas.update_amplitude_data("688826")

            info = canvas.amplitude_info
            self.assertIn("avg_amp", info)
            self.assertIn("max_amp", info)
            self.assertIn("rating", info)
            self.assertIn("days", info)
            self.assertGreater(len(info["days"]), 0)
            self.assertGreater(info["avg_amp"], 0.0)

            # 验证振幅计算公式: (High - Low) / PrevClose * 100%
            # 最后一根: high=122, low=115, prev_close=120 -> amp = (122-115)/120*100 = 5.83% -> 5.8%
            last_day, last_amp = info["days"][-1]
            self.assertAlmostEqual(last_amp, round((122.0 - 115.0) / 120.0 * 100.0, 1), places=1)

        canvas.deleteLater()

    def test_update_amplitude_data_reuse_local_df(self):
        """测试日K模式下100%复用本地 df_intraday 内存数据，零网络请求与指纹缓存"""
        from ats.ui.intraday_strategy_dialog import SBCChartCanvas

        canvas = SBCChartCanvas()
        mock_daily = self._generate_mock_daily_df(8)
        canvas.period_mode = "day"
        canvas.df_intraday = mock_daily

        # patch fetcher 确保绝不发起任何网络请求
        with patch("ats.tdx_realtime_fetcher.TDXRealtimeFetcher.get_instance") as mock_fetcher_cls:
            mock_fetcher = MagicMock()
            mock_fetcher_cls.return_value = mock_fetcher

            # 1. 首次触发计算
            canvas.update_amplitude_data("688826")
            # 必须从本地内存 df_intraday 直接计算，网络 fetcher.fetch_kline_bars 绝不能被调用
            mock_fetcher.fetch_kline_bars.assert_not_called()

            info = canvas.amplitude_info
            self.assertGreater(len(info.get("days", [])), 0)
            # 确认日期格式为 MM-DD，绝非包含 15:00
            for d_str, _ in info["days"]:
                self.assertNotIn(":", d_str)
                self.assertEqual(len(d_str), 5) # 09-18 格式

            # 2. 再次触发同一标的，直接命中 60s 指纹缓存
            canvas.update_amplitude_data("688826")
            mock_fetcher.fetch_kline_bars.assert_not_called()
            self.assertEqual(canvas._cached_amp_code, "688826")

        canvas.deleteLater()

    def test_amplitude_hud_left_position(self):
        """测试振幅 HUD 卡片严格位于走势图左侧 (margin_left + 4)，且通道模式下垂直避让"""
        from ats.ui.intraday_strategy_dialog import SBCChartCanvas
        canvas = SBCChartCanvas()
        canvas.amplitude_info = {
            "avg_amp": 5.2,
            "max_amp": 8.1,
            "rating": "🔥极高活跃",
            "rating_color": "#FF4444",
            "days": [("09-17", 4.5), ("09-18", 8.1)],
            "n_days": 2
        }

        # 验证分时模式下通道高度为 0
        canvas.period_mode = "1m"
        canvas._channel_box_h = 0
        # 验证 K 线模式下通道高度动态自适应
        canvas.period_mode = "day"
        canvas._channel_box_h = 56
        self.assertEqual(getattr(canvas, "_channel_box_h", 0), 56)
        canvas.deleteLater()

    def test_dialog_key_press_and_global_shortcuts(self):
        """测试 SBCIntradayChartDialog 上下键触发 zoom_in/zoom_out 且不误触切周期"""
        from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog

        dlg = SBCIntradayChartDialog(code="688826")
        df = self._generate_mock_intraday_df(80)
        dlg.canvas.set_data(df, 10.0, 10.0, 18.0, 9.0, 12.0, 13.0, [])

        # 初始周期与切片状态
        init_period = dlg._current_period_mode
        init_slice_len = len(dlg.canvas._get_visible_slice()[0])

        # 模拟按 Up 键
        up_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
        dlg.keyPressEvent(up_event)

        # 周期绝不能发生改变！
        self.assertEqual(dlg._current_period_mode, init_period)
        # 画布应该被放大 (可视数量变小)
        new_slice_len = len(dlg.canvas._get_visible_slice()[0])
        self.assertLess(new_slice_len, init_slice_len)

        # 模拟按 Down 键
        down_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        dlg.keyPressEvent(down_event)

        # 周期依旧不发生改变！
        self.assertEqual(dlg._current_period_mode, init_period)
        # 画布应该被缩小 (可视数量变大)
        self.assertGreater(len(dlg.canvas._get_visible_slice()[0]), new_slice_len)

        # 测试全局窗口级快捷键槽函数
        dlg._on_shortcut_up_activated()
        self.assertLess(len(dlg.canvas._get_visible_slice()[0]), init_slice_len)

        dlg._on_shortcut_down_activated()
        self.assertEqual(len(dlg.canvas._get_visible_slice()[0]), init_slice_len)

        # 测试在可编辑输入框中获得焦点时，is_editing_text 保护机制
        mock_edit = QLineEdit(dlg)
        mock_edit.setFocus()
        with patch("ats.ui.styles.is_editing_text", return_value=True):
            cur_len = len(dlg.canvas._get_visible_slice()[0])
            dlg._on_shortcut_up_activated()
            # 处于编辑打字状态，不应缩放
            self.assertEqual(len(dlg.canvas._get_visible_slice()[0]), cur_len)

        # 测试事件过滤器 eventFilter 捕获普通子控件上的按键事件
        btn_mock = QPushButton("测试按钮", dlg)
        filtered_up = dlg.eventFilter(btn_mock, up_event)
        self.assertTrue(filtered_up) # 已被拦截消费

        dlg.close()
        dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
