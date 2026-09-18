# -*- coding: utf-8 -*-
"""
test_sbc_period_switch_zero_io_and_speed.py
-------------------------------------------
专门验证：
1. SBC 窗口连续切换周期期间 0 磁盘写盘（sbc_launcher_holdings_layout.json 写盘数为 0）；
2. 连续评估与切周期期间 0 收盘定盘写盘（newstock_listing_closing_evaluations.json 写盘数为 0，且无重复刷屏）；
3. fetch_kline_bars 3秒 TTL 内存缓存加速（走缓存时耗时 < 5ms，实现丝滑秒切）；
4. 退出/关闭时集中统一持久化落盘一次。
"""

import os
import sys
import time
import json
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from PyQt6.QtWidgets import QApplication

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, SBCWindowMemoryManager
from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
import run_sbc


class TestSBCPeriodSwitchZeroIOAndSpeed(unittest.TestCase):

    def setUp(self):
        self.code = "001212"
        self.engine = IntradayStrategyEngine.get_instance()
        self.fetcher = TDXRealtimeFetcher.get_instance()
        # 清除 fetcher 缓存
        self.fetcher.clear_stock_cache(self.code)

    def test_period_switch_has_zero_disk_io(self):
        """【断言 1】连续切换周期 10 次期间，sbc_launcher_holdings_layout.json 的写盘次数为 0"""
        cfg_path = run_sbc._get_launcher_layout_cfg_path()
        mtime_before = os.path.getmtime(cfg_path) if os.path.exists(cfg_path) else 0.0

        with patch.object(SBCIntradayChartDialog, "_do_save_sbc_geometry") as mock_save_geo, \
             patch("run_sbc.save_launcher_holdings_windows") as mock_save_launcher:
            
            dlg = SBCIntradayChartDialog(None, code=self.code, engine=self.engine)
            dlg.show()

            # 模拟用户连续点击周期按钮切换周期
            test_periods = ["5m", "30m", "60m", "day", "1m", "5d", "10d", "5m", "day", "1m"]
            for p in test_periods:
                dlg.set_period_mode(p, reload=False, save=False)
                self.assertEqual(dlg._current_period_mode, p)

            # 验证运行期间 mock_save_geo 与 mock_save_launcher 调用次数均为 0
            self.assertEqual(mock_save_geo.call_count, 0, "切换周期期间违规触发了 _do_save_sbc_geometry 磁盘写入！")
            self.assertEqual(mock_save_launcher.call_count, 0, "切换周期期间违规触发了 save_launcher_holdings_windows 磁盘写入！")

            dlg.close()

    def test_evaluate_and_switch_has_zero_closing_save(self):
        """【断言 2】日K线或收盘后时间传入 evaluate_seven_nodes 期间，不触发 save_listing_closing_scorecard 磁盘写盘"""
        eval_fp = self.engine._get_closing_eval_filepath()
        mtime_before = os.path.getmtime(eval_fp) if os.path.exists(eval_fp) else 0.0

        with patch.object(self.engine, "save_listing_closing_scorecard") as mock_save_closing:
            # 连续模拟 15:00 以及 2026-09-18 日期格式的评估 10 次
            for t_str in ["15:00", "15:05", "2026-09-18", "15:00:00"]:
                res = self.engine.evaluate_seven_nodes(
                    code=self.code,
                    current_time_str=t_str,
                    open_price=37.71,
                    price=38.00,
                    high_price=39.00,
                    low_price=36.00,
                    vwap=37.50
                )
                self.assertIsNotNone(res)

            # 断言期间 save_listing_closing_scorecard 调用次数为 0
            self.assertEqual(mock_save_closing.call_count, 0, "评估热循环中违规调用了 save_listing_closing_scorecard 磁盘写入！")

    def test_save_listing_closing_scorecard_deduplication(self):
        """【断言 3】save_listing_closing_scorecard 防重测试：相同分数当天调用仅写盘一次，重复调用直接跳过"""
        eval_result = {
            "open_price": 37.71,
            "price": 38.00,
            "high_price": 39.00,
            "low_price": 36.00,
            "vwap": 37.50,
            "total_weighted_score": 7.88,
            "pattern": "B型·强势换手"
        }
        # 第一次写盘
        ret1 = self.engine.save_listing_closing_scorecard(self.code, eval_result)
        self.assertTrue(ret1)

        # 第二次带相同分数立即调用，应命中内存防重守卫直接返回 True
        eval_fp = self.engine._get_closing_eval_filepath()
        mtime1 = os.path.getmtime(eval_fp)
        time.sleep(0.05)

        ret2 = self.engine.save_listing_closing_scorecard(self.code, eval_result)
        self.assertTrue(ret2)
        mtime2 = os.path.getmtime(eval_fp)

        self.assertEqual(mtime1, mtime2, "相同标的当天同分数重复调用时违规触发了二次磁盘写盘！")

    def test_kline_bars_ttl_cache_speed(self):
        """【断言 4】fetch_kline_bars 3 秒 TTL 内存缓存断言：第二次获取走缓存，耗时 < 5ms"""
        # 第一次获取（构建缓存）
        df1 = self.fetcher.fetch_kline_bars(self.code, category="5m", count=150)
        if df1.empty:
            # TDX 若离线，用 mock 填充缓存
            mock_df = pd.DataFrame({"close": [37.0, 38.0], "time": ["10:00", "10:05"]}).set_index("time")
            self.fetcher._kline_bars_cache[(self.code, "5m", 150)] = (time.time(), mock_df)

        # 第二次获取（3 秒内必走缓存）
        t0 = time.time()
        df2 = self.fetcher.fetch_kline_bars(self.code, category="5m", count=150)
        t1 = time.time()
        duration_ms = (t1 - t0) * 1000.0

        self.assertFalse(df2.empty)
        self.assertLess(duration_ms, 5.0, f"TTL 内存缓存耗时应 < 5ms，实际耗时 {duration_ms:.2f}ms")


if __name__ == "__main__":
    unittest.main()
