# -*- coding: utf-8 -*-
"""
tests/test_sbc_zoom_signal_clipping.py
---------------------------------------
专项测试：验证 SBC 在多日分时与 K 线放大查看时，买卖信号的严格视口裁剪与精确坐标映射。
彻底根除：
1. 放大时历史多日前买卖点跨日乱投射到放大当天的 Bug；
2. 历史买卖点在同分同秒处垂直扎堆堆叠的 Bug；
3. 视野外历史信号污染放大视口 Y 轴动态范围的 Bug。
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPainter, QImage
from PyQt6.QtCore import Qt

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

from ats.ui.intraday_strategy_dialog import SBCChartCanvas


class TestSBCZoomSignalClipping(unittest.TestCase):
    """测试 SBC 画布在局部放大时的买卖信号视口裁剪机制"""

    def setUp(self):
        self.canvas = SBCChartCanvas()
        self.canvas.resize(800, 500)

        # 构造 3 日分时数据 (Day 1: 09-01, Day 2: 09-02, Day 3: 09-03)
        # 每天 10 根 K 线用于轻量快速测试，共 30 根
        dates = ["2026-09-01"] * 10 + ["2026-09-02"] * 10 + ["2026-09-03"] * 10
        times_raw = []
        for d in ["2026-09-01", "2026-09-02", "2026-09-03"]:
            for m in range(10):
                times_raw.append(f"{d} 09:{30+m:02d}")

        prices = [250.0 + i * 0.5 for i in range(30)]
        vwaps = [p - 0.2 for p in prices]

        df = pd.DataFrame({
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "vwap": vwaps,
            "vol": [1000] * 30,
            "date": dates,
        }, index=times_raw)

        # 设置 3 个信号分别位于 Day 1 (idx=2), Day 2 (idx=12), Day 3 (idx=22)
        # 故意让时间后 5 位相同 (都是 "09:32")
        signals = [
            {
                "trade_id": 1,
                "action": "buy",
                "price": 251.0,
                "date": "2026-09-01",
                "time": "2026-09-01 09:32",
                "timestamp": "2026-09-01 09:32",
                "bar_idx": 2,
                "note": "Day1买点"
            },
            {
                "trade_id": 2,
                "action": "sell",
                "price": 256.0,
                "date": "2026-09-02",
                "time": "2026-09-02 09:32",
                "timestamp": "2026-09-02 09:32",
                "bar_idx": 12,
                "note": "Day2卖点"
            },
            {
                "trade_id": 3,
                "action": "buy",
                "price": 261.0,
                "date": "2026-09-03",
                "time": "2026-09-03 09:32",
                "timestamp": "2026-09-03 09:32",
                "bar_idx": 22,
                "note": "Day3买点"
            },
        ]

        self.canvas.set_data(
            df_intraday=df,
            open_p=250.0,
            vwap_p=260.0,
            high_p=265.0,
            low_p=249.0,
            sell_min=248.0,
            sell_max=266.0,
            signals=signals,
            period_mode="3d"
        )
        self.df = df
        self.signals = signals

    def test_map_signal_in_full_view(self):
        """全景视图下（无缩放），3 个信号都能正确映射到各自在 df_view 中的局部索引"""
        df_view, start_i, end_i = self.canvas._get_visible_slice()
        self.assertEqual(start_i, 0)
        self.assertEqual(end_i, 29)

        idx0 = self.canvas._map_signal_to_visible_index(self.signals[0], df_view, start_i, end_i)
        idx1 = self.canvas._map_signal_to_visible_index(self.signals[1], df_view, start_i, end_i)
        idx2 = self.canvas._map_signal_to_visible_index(self.signals[2], df_view, start_i, end_i)

        self.assertEqual(idx0, 2)
        self.assertEqual(idx1, 12)
        self.assertEqual(idx2, 22)

    def test_map_signal_strictly_clips_when_zoomed(self):
        """放大查看 Day 3 时（start_i=20, end_i=29），Day 1 和 Day 2 的信号必须严格被裁剪为 None"""
        self.canvas._zoom_start_idx = 20
        self.canvas._zoom_end_idx = 29
        self.assertTrue(self.canvas._is_zoomed())

        df_view, start_i, end_i = self.canvas._get_visible_slice()
        self.assertEqual(start_i, 20)
        self.assertEqual(end_i, 29)
        self.assertEqual(len(df_view), 10)

        # Day 1 和 Day 2 必须返回 None，绝不能因为时间是 09:32 而被投射到 Day 3 的 09:32 (即局部索引 2)
        idx0 = self.canvas._map_signal_to_visible_index(self.signals[0], df_view, start_i, end_i)
        idx1 = self.canvas._map_signal_to_visible_index(self.signals[1], df_view, start_i, end_i)
        idx2 = self.canvas._map_signal_to_visible_index(self.signals[2], df_view, start_i, end_i)

        self.assertIsNone(idx0, "Day 1 信号在当前放大视口之外，必须被裁剪返回 None！")
        self.assertIsNone(idx1, "Day 2 信号在当前放大视口之外，必须被裁剪返回 None！")
        self.assertEqual(idx2, 2, "Day 3 信号在当前放大视口内，全局索引 22 必须映射为局部索引 22 - 20 = 2！")

    def test_painting_under_zoom_renders_only_visible_signals(self):
        """放大查看时，屏幕上只渲染当前视口内的信号，不会在屏幕上扎堆堆叠多日前信号"""
        # 放大到 Day 3 (索引 20~29)
        self.canvas._zoom_start_idx = 20
        self.canvas._zoom_end_idx = 29

        # 直接使用 QPainter 在 QImage 上测试 _paint_intraday 内部渲染
        img = QImage(800, 500, QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(img)
        self.canvas._signal_hit_boxes = []
        self.canvas._paint_intraday(painter, 55, 30, 670, 440)
        painter.end()

        # 校验绘制生成的命中矩形数量恰好等于 1 (仅 Day 3 信号被绘制)
        rendered_trade_ids = [box.get("trade_id") for box in self.canvas._signal_hit_boxes]
        self.assertEqual(len(rendered_trade_ids), 1, "放大时只应该渲染 1 个当前视口内的买卖标记！")
        self.assertIn(3, rendered_trade_ids, "当前视口内的 Day 3 信号必须被成功渲染！")
        self.assertNotIn(1, rendered_trade_ids, "视野外的 Day 1 信号绝不能被渲染！")
        self.assertNotIn(2, rendered_trade_ids, "视野外的 Day 2 信号绝不能被渲染！")

    def test_reset_view_restores_all_signals(self):
        """重置视口回全景后，所有信号全部恢复正常渲染"""
        self.canvas._zoom_start_idx = 20
        self.canvas._zoom_end_idx = 29
        self.canvas.reset_view()

        img = QImage(800, 500, QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(img)
        self.canvas._signal_hit_boxes = []
        self.canvas._paint_intraday(painter, 55, 30, 670, 440)
        painter.end()

        rendered_trade_ids = [box.get("trade_id") for box in self.canvas._signal_hit_boxes]
        self.assertEqual(len(rendered_trade_ids), 3, "全景视图下所有 3 个买卖标记均应恢复渲染！")


if __name__ == "__main__":
    unittest.main()
