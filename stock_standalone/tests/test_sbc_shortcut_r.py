# -*- coding: utf-8 -*-
"""
SBC 视图快捷键 R 自适应周期策略测算与图上标记专项单元测试
"""

import sys
import os
import unittest
import numpy as np
import pandas as pd

CURR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURR_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

# 确保 QApplication 单例存在
app = QApplication.instance()
if app is None:
    app = QApplication([])

from ats.ui.intraday_strategy_dialog import SBCChartCanvas, SBCIntradayChartDialog
try:
    from test_channel_bottom_reversal import generate_mock_60m_df
except ImportError:
    from tests.test_channel_bottom_reversal import generate_mock_60m_df


class TestSBCShortcutR(unittest.TestCase):
    """SBC 视图快捷键 R 联动测试套件"""

    def setUp(self):
        self.canvas = SBCChartCanvas()
        self.canvas.code = "688826"

    def test_01_shortcut_r_on_60m_period(self):
        """测试在 60m 周期下按下 R 键自适应运行通道策略并在图上生成信号点"""
        df_60m = generate_mock_60m_df("valid_reversal", n_bars=60)
        self.canvas.period_mode = "60m"
        self.canvas.df_intraday = df_60m

        # 模拟键盘按键 R
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier, "r")
        self.canvas.keyPressEvent(key_event)

        res = self.canvas.strategy_eval_result
        self.assertIsNotNone(res, "策略测算结果不应为空")
        self.assertTrue(res.get("is_matched"), "标准 60f 反转形态应匹配成功")
        self.assertEqual(res.get("period"), "60m")
        self.assertGreater(res.get("entry_price", 0.0), 0.0)
        self.assertGreater(res.get("target_price_1", 0.0), res.get("entry_price", 0.0))
        self.assertLess(res.get("stop_loss", 0.0), res.get("entry_price", 0.0))
        print(f"[Test 1] SBC 60m 周期快捷键 R 测算成功: 得分={res.get('score')}, 介入={res.get('entry_price')}, 止损={res.get('stop_loss')}")

    def test_02_shortcut_r_on_1m_period(self):
        """测试在 1m 日内分时周期下按下 R 键自适应运行 7 节点分时策略"""
        times = pd.date_range(end="2026-08-21 15:00", periods=60, freq="1min")
        df_1m = pd.DataFrame({
            "close": np.linspace(940.0, 948.0, 60),
            "high": np.linspace(941.0, 950.0, 60),
            "low": np.linspace(938.0, 946.0, 60),
            "open": np.full(60, 940.0),
            "vol": np.full(60, 1000.0)
        }, index=times)
        
        self.canvas.period_mode = "1m"
        self.canvas.df_intraday = df_1m
        self.canvas.open_price = 940.0

        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier, "r")
        self.canvas.keyPressEvent(key_event)

        res = self.canvas.strategy_eval_result
        self.assertIsNotNone(res)
        self.assertTrue(res.get("is_matched"))
        self.assertEqual(res.get("period"), "1m")
        self.assertIn("分时7节点评分", res.get("reason", ""))
        print(f"[Test 2] SBC 1m 分时周期快捷键 R 测算成功: 评分={res.get('score')}分 | {res.get('pattern_name')}")

    def test_03_dialog_shortcut_r_forwarding(self):
        """测试 SBCIntradayChartDialog 窗口级 R 键与按钮事件转发"""
        dialog = SBCIntradayChartDialog(code="688826")
        df_60m = generate_mock_60m_df("valid_reversal", n_bars=60)
        dialog.canvas.period_mode = "60m"
        dialog.canvas.df_intraday = df_60m
        dialog.auto_eval_enabled = False  # 确保初始为关，接下来切换为开启

        # 触发窗口级的 _on_eval_r_clicked
        dialog._on_eval_r_clicked(toggle=True)
        res = getattr(dialog.canvas, "strategy_eval_result", None)
        self.assertIsNotNone(res)
        self.assertTrue(res.get("is_matched"))
        self.assertTrue("自动测算开启" in dialog.lbl_info.text() or "策略测算" in dialog.lbl_info.text())
        dialog.close()
        print("[Test 3] 对话框级 R 键联动转发测试成功")

    def test_04_dialog_close_stops_poll_timer(self):
        """测试关闭 SBC 窗口时彻底停止 poll_timer，防止后台野定时器持续执行与日志泄露"""
        dialog = SBCIntradayChartDialog(code="688826")
        dialog.show()  # 触发 showEvent 激活定时器
        self.assertTrue(dialog.poll_timer.isActive(), "展示窗口后 poll_timer 应当已启动")
        self.assertTrue(dialog._save_timer.isActive(), "展示窗口后 _save_timer 应当已启动")

        # 触发关闭事件
        dialog.close()
        self.assertFalse(dialog.poll_timer.isActive(), "关闭窗口后 poll_timer 必须彻底停止！")
        self.assertFalse(dialog._save_timer.isActive(), "关闭窗口后 _save_timer 必须彻底停止！")
        self.assertFalse(dialog.hover_timer.isActive(), "关闭窗口后 hover_timer 必须彻底停止！")
        print("[Test 4] 窗口关闭销毁定时器防护测试成功")

    def test_05_eval_log_deduplication(self):
        """测试策略测算结果未变化时状态机签名去重，防止重复无意义刷屏"""
        df_60m = generate_mock_60m_df("valid_reversal", n_bars=60)
        self.canvas.period_mode = "60m"
        self.canvas.df_intraday = df_60m

        # 首次测算
        self.canvas.run_adaptive_strategy_eval()
        sig1 = getattr(self.canvas, "_last_eval_log_signature", None)
        self.assertIsNotNone(sig1, "首次测算后应记录日志签名")

        # 再次执行相同测算
        self.canvas.run_adaptive_strategy_eval()
        sig2 = getattr(self.canvas, "_last_eval_log_signature", None)
        self.assertEqual(sig1, sig2, "数据未变时日志签名应保持完全一致")
        print("[Test 5] 策略测算日志去重签名测试成功")


if __name__ == "__main__":
    unittest.main()
