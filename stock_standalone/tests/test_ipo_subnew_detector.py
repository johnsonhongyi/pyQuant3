# -*- coding: utf-8 -*-
"""
tests/test_ipo_subnew_detector.py
---------------------------------
专项验证：新股次新股独立超短检测工具 (SBC 极限 10日 VWAP 预判与异动引擎)
1. 极限 VWAP 走平蓄势 1~3 天判定 (预下单潜伏)；
2. 在 VWAP 上方回踩不碰判定 (黄金极限启动买点)；
3. 跌破 VWAP 破位弱势股拦截 (反抽仅为止损点)；
4. IPC 跨进程队列通信与心跳守护；
5. run_ats.py 顶层命令行分发 (--ipo-detector)。
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

# 确保路径
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from ats.strategy.ipo_vwap_detector_engine import (
    IPOVWAPDetectorEngine, VWAPDetectorSignal
)
from ats.ui.ipo_detector_ipc import (
    send_stock_to_ipo_detector,
    pop_queued_stocks,
    update_detector_heartbeat,
    is_ipo_detector_alive,
    build_ipo_detector_command
)


class TestIPOSubnewDetector(unittest.TestCase):
    """新股次新超短检测工具自动化测试"""

    def setUp(self):
        self.engine = IPOVWAPDetectorEngine.get_instance()

    def test_vwap_consolidation_pre_order_detection(self):
        """【测试】验证在 VWAP 上方走平蓄势 3 天精准触发【🎯 预下单】信号 (如天海电子走势)"""
        # 构造连续 3 天在 VWAP 上方窄幅震荡 (< 3% 振幅) 的多日分时数据
        rows = []
        dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"]
        for d in dates[:-1]:
            # 走平天: VWAP=34.0, 价格在 33.8 ~ 34.2 极窄波动
            for minute in range(30):
                rows.append({
                    "time": f"{d} 09:{minute:02d}",
                    "date": d,
                    "open": 34.0,
                    "close": 34.1,
                    "high": 34.2,
                    "low": 33.9,
                    "price": 34.1,
                    "vwap": 34.0,
                    "amount": 1000000,
                    "volume": 30000
                })
        # 今日 (2026-09-17): 现价 34.2, VWAP=34.0
        d_today = dates[-1]
        for minute in range(10):
            rows.append({
                "time": f"{d_today} 09:{30+minute:02d}",
                "date": d_today,
                "open": 34.0,
                "close": 34.2,
                "high": 34.3,
                "low": 34.0,
                "price": 34.2,
                "vwap": 34.0,
                "amount": 1500000,
                "volume": 45000
            })

        mock_df = pd.DataFrame(rows)
        mock_kline = pd.DataFrame({
            "close": [33.0, 33.2, 33.5, 33.8, 34.2],
            "low": [32.5, 32.5, 32.8, 33.0, 33.5],
            "ma5": [33.0, 33.2, 33.4, 33.6, 33.8],
            "lower": [32.4, 32.4, 32.5, 32.5, 32.5]
        })

        with patch.object(self.engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.engine.fetcher, "fetch_kline_bars", return_value=mock_kline):
            sig = self.engine.analyze_stock("001365", force_refresh=True)

            self.assertEqual(sig.code, "001365")
            self.assertTrue(sig.is_above_vwap)
            self.assertGreaterEqual(sig.consolidation_days, 1)
            self.assertEqual(sig.signal_type, "PRE_ORDER")
            self.assertIn("预下单", sig.signal_level)
            self.assertIn("走平", sig.structure_tag)

    def test_vwap_pullback_no_touch_buy_detection(self):
        """【测试】验证在 VWAP 上方回踩不碰触发【🚀 回踩启动】黄金买点"""
        rows = []
        d = "2026-09-17"
        # 价格在 35.0，向 VWAP(34.0) 靠拢下探到 34.1 (回踩不碰)，随后拉起至 34.8
        for m in range(20):
            p = 35.0 - m * 0.045  # 最低打到约 34.1
            rows.append({
                "time": f"{d} 10:{m:02d}",
                "date": d,
                "open": p + 0.02,
                "close": p,
                "high": p + 0.05,
                "low": p - 0.02,
                "price": p,
                "vwap": 34.0,
                "amount": 500000,
                "volume": 15000
            })
        # 随后拐头拉起到 34.8
        for m in range(10):
            p = 34.1 + m * 0.07
            rows.append({
                "time": f"{d} 10:{20+m:02d}",
                "date": d,
                "open": p - 0.02,
                "close": p,
                "high": p + 0.05,
                "low": p - 0.01,
                "price": p,
                "vwap": 34.0,
                "amount": 1000000,
                "volume": 30000
            })

        mock_df = pd.DataFrame(rows)
        with patch.object(self.engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.engine.fetcher, "fetch_kline_bars", return_value=pd.DataFrame()):
            sig = self.engine.analyze_stock("688826", force_refresh=True)

            self.assertTrue(sig.is_above_vwap)
            self.assertTrue(sig.pullback_no_touch)
            self.assertEqual(sig.signal_type, "PULLBACK_BUY")
            self.assertIn("回踩启动", sig.signal_level)
            self.assertIn("回踩不碰", sig.structure_tag)

    def test_broken_stock_vwap_stop_loss_rejection(self):
        """【测试】验证破位跌破 VWAP 的弱势股，反抽触碰 VWAP 仅视作止损点，严禁发出买入"""
        rows = []
        d = "2026-09-17"
        # VWAP=50.0, 现价破位下跌至 48.0 (-4%)
        for m in range(25):
            p = 50.0 - m * 0.08
            rows.append({
                "time": f"{d} 09:{30+m:02d}",
                "date": d,
                "open": p + 0.05,
                "close": p,
                "high": p + 0.08,
                "low": p - 0.05,
                "price": p,
                "vwap": 50.0,
                "amount": 500000,
                "volume": 10000
            })

        mock_df = pd.DataFrame(rows)
        with patch.object(self.engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.engine.fetcher, "fetch_kline_bars", return_value=pd.DataFrame()):
            sig = self.engine.analyze_stock("301677", force_refresh=True)

            self.assertFalse(sig.is_above_vwap)
            self.assertLess(sig.vwap_diff_pct, -0.8)
            self.assertEqual(sig.signal_type, "WEAK_EXIT")
            self.assertIn("破位止损点", sig.signal_level)
            self.assertIn("破位", sig.structure_tag)

    def test_ipc_queue_push_and_pop(self):
        """【测试】验证跨进程通信中心队列原子压入与消费"""
        with patch("ats.ui.ipo_detector_ipc.is_ipo_detector_alive", return_value=True):
            send_stock_to_ipo_detector("001365", "天海电子")
            send_stock_to_ipo_detector("688826", "派林激光")

            queued = pop_queued_stocks()
            self.assertIn("001365", queued)
            self.assertIn("688826", queued)

            # 再次拉取应已清空
            queued_again = pop_queued_stocks()
            self.assertEqual(queued_again, [])

    def test_run_ats_command_dispatch(self):
        """【测试】验证 run_ats.py 顶层支持 --ipo-detector 独立分发"""
        import run_ats
        cmd = build_ipo_detector_command(code="001365")
        self.assertTrue(any("run_ipo_detector" in c or "--ipo-detector" in c for c in cmd))

    def test_dialog_ui_add_remove_and_filter(self):
        """【测试】验证 IPOSubnewDetectorDialog 界面加码、移除与持久化"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        with patch("ats.ui.ipo_subnew_detector_dialog.IPOScanWorker.start"):
            from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
            dlg = IPOSubnewDetectorDialog(initial_code="001365")

            # 验证 001365 已在监控池首位
            self.assertIn("001365", dlg.monitored_codes)

            # 手动添加一只标的
            dlg.add_stock("688826")
            self.assertIn("688826", dlg.monitored_codes)
            self.assertEqual(dlg.monitored_codes[0], "688826")

            # 移除标的
            dlg.remove_stock("688826")
            self.assertNotIn("688826", dlg.monitored_codes)

            # 保存持久化并关闭
            dlg.save_persisted_state()
            dlg.close()


if __name__ == "__main__":
    unittest.main()
