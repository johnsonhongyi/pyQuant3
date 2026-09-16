# -*- coding: utf-8 -*-
"""
Unit tests for SBC launcher, timer intervals and performance caching
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import pandas as pd
import numpy as np
from PyQt6.QtWidgets import QApplication

from JohnsonUtil import commonTips as cct
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, _SBCWindowProxy, rearrange_all_sbc_windows
from ats.ui.sbc_launcher import SBCProcessManager, launch_sbc_process, close_all_sbc_processes


app = QApplication.instance() or QApplication(sys.argv)


class TestSBCLauncherAndIntervals(unittest.TestCase):
    def test_hover_timer_and_poll_timer_alignment(self):
        """验证 hover_timer 为 300ms，poll_timer 对齐 cct.ats_tdx_interval"""
        old_val = getattr(cct, 'ats_tdx_interval', 5.0)
        try:
            cct.ats_tdx_interval = 5.0
            dlg = SBCIntradayChartDialog(code="688826")
            # 1. 验证 hover_timer 设为 300ms
            self.assertEqual(dlg.hover_timer.interval(), 300, "hover_timer 必须设为 300ms 以节约 66% CPU")
            # 2. 验证 poll_timer 动态对齐 cct.ats_tdx_interval (5.0s -> 5000ms)
            self.assertEqual(dlg.poll_timer.interval(), 5000, "poll_timer 必须对齐 cct.ats_tdx_interval 5000ms")
            dlg.close()
        finally:
            cct.ats_tdx_interval = old_val

    def test_eval_vwap_fingerprint_caching(self):
        """验证 _eval_vwap_proactive_strategy 指纹缓存 0 毫秒复用"""
        dlg = SBCIntradayChartDialog(code="688826")
        
        # 构造模拟 20 根 Bar 数据
        dates = pd.date_range("2026-03-01 09:30", periods=20, freq="1min")
        df_bars = pd.DataFrame({
            "open": np.linspace(10, 11, 20),
            "high": np.linspace(10.2, 11.2, 20),
            "low": np.linspace(9.8, 10.9, 20),
            "close": np.linspace(10.1, 11.1, 20),
            "vol": [1000] * 20,
            "vwap": np.linspace(10, 11, 20)
        }, index=dates)

        # 首次计算
        sigs1 = dlg._eval_vwap_proactive_strategy(df_bars, period_mode="1m")
        self.assertIsNotNone(dlg._cached_strat_fp)
        
        # 再次调用 (指纹相同)
        sigs2 = dlg._eval_vwap_proactive_strategy(df_bars, period_mode="1m")
        self.assertIs(sigs1, sigs2, "相同数据下必须 100% 命中缓存对象，避免重复 2400 根逐 Tick 模拟")
        dlg.close()

    def test_sbc_process_manager_launch_and_cleanup(self):
        """测试 SBC 独立子进程启动与清理"""
        mgr = SBCProcessManager.get_instance()
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            # 1. 启动标的 688826
            proc = mgr.launch("688826", "10d")
            self.assertIsNotNone(proc)
            self.assertIn("688826", mgr.get_running_codes())

            # 2. 统一关闭
            mgr.close_all()
            mock_proc.terminate.assert_called()
            self.assertEqual(len(mgr.get_running_codes()), 0)

    def test_capital_dragon_panel_open_sbc_chart(self):
        """测试资金主线右键正确调用 launch_sbc_process 独立子进程启动 SBC"""
        from ats.ui.capital_dragon_panel import CapitalDragonPanel
        panel = CapitalDragonPanel()
        with patch("ats.ui.sbc_launcher.launch_sbc_process") as mock_launch:
            panel.open_sbc_chart("000001", "平安银行")
            mock_launch.assert_called_with("000001", "10d")

    def test_universe_widget_run_sbc_button(self):
        """测试左侧股票池顶部工具栏一键 run_sbc.py 按钮存在并正确触发"""
        from ats.ui.universe_widget import UniverseTreeWidget
        widget = UniverseTreeWidget()
        self.assertTrue(hasattr(widget, 'btn_run_sbc'), "Universe 必须有 btn_run_sbc 按钮")
        self.assertIn("📈", widget.btn_run_sbc.text())
        with patch("ats.ui.sbc_launcher.SBCProcessManager.launch") as mock_launch, \
             patch("subprocess.Popen") as mock_popen:
            # 未选中时无参运行 run_sbc.py
            widget._on_launch_run_sbc_clicked()
            mock_popen.assert_called()


if __name__ == "__main__":
    unittest.main()
