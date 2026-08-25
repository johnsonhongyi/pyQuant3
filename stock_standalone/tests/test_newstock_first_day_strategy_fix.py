# -*- coding: utf-8 -*-
"""
tests/test_newstock_first_day_strategy_fix.py — 验证新股上市首日策略自动匹配与 SBC 信息修复
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock, patch

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.new_stock_strategy_generator import NewStockStrategyGenerator


class TestNewStockFirstDayStrategyFix(unittest.TestCase):
    """测试新股首日策略路由与 SBC 修复"""

    def setUp(self):
        self.engine = IntradayStrategyEngine.get_instance()
        self.engine.load_config()
        self.fetcher = TDXRealtimeFetcher.get_instance()

    def test_01_get_yesterday_ohlc_first_day(self):
        """测试 1: 上市首日仅有今天 1 根日 K 线时，get_yesterday_ohlc 必须返回全 0，杜绝将今天当作昨天"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 模拟 TDX 返回仅有今天 1 根日 K 线的新股
        mock_df_1day = pd.DataFrame([
            {"datetime": f"{today_str} 15:00", "open": 209.00, "high": 262.00, "low": 200.01, "close": 253.16}
        ])

        with patch.object(self.fetcher, "fetch_kline_bars", return_value=mock_df_1day):
            if hasattr(self.fetcher, "_yesterday_ohlc_cache"):
                self.fetcher._yesterday_ohlc_cache.pop("688835", None)
            
            y_ohlc = self.fetcher.get_yesterday_ohlc("688835")
            self.assertEqual(y_ohlc["open"], 0.0, "上市首日昨日 open 必须为 0.0")
            self.assertEqual(y_ohlc["high"], 0.0, "上市首日昨日 high 必须为 0.0")
            self.assertEqual(y_ohlc["low"], 0.0, "上市首日昨日 low 必须为 0.0")
            self.assertEqual(y_ohlc["close"], 0.0, "上市首日昨日 close 必须为 0.0")

    def test_02_get_yesterday_ohlc_multi_days(self):
        """测试 2: 常规多日股票有历史日 K 线时，get_yesterday_ohlc 准确返回倒数第 2 根日 K (昨日)"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        mock_df_multi = pd.DataFrame([
            {"datetime": "2026-08-22 15:00", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5},
            {"datetime": "2026-08-24 15:00", "open": 10.5, "high": 11.5, "low": 10.2, "close": 11.2},
            {"datetime": f"{today_str} 15:00", "open": 11.2, "high": 12.0, "low": 11.0, "close": 11.8}
        ])

        with patch.object(self.fetcher, "fetch_kline_bars", return_value=mock_df_multi):
            if hasattr(self.fetcher, "_yesterday_ohlc_cache"):
                self.fetcher._yesterday_ohlc_cache.pop("600519", None)

            y_ohlc = self.fetcher.get_yesterday_ohlc("600519")
            self.assertEqual(y_ohlc["open"], 10.5)
            self.assertEqual(y_ohlc["high"], 11.5)
            self.assertEqual(y_ohlc["low"], 10.2)
            self.assertEqual(y_ohlc["close"], 11.2)

    def test_03_is_stock_first_listing_day(self):
        """测试 3: 上市首日判定逻辑权威性检验"""
        today_str = datetime.now().strftime("%Y-%m-%d")

        # A. 真实上市首日：仅有今天 1 根日 K 线且日期为今日 -> 判定为首日 True
        mock_df_1day = pd.DataFrame([
            {"datetime": f"{today_str} 15:00", "open": 209.00, "high": 262.00, "low": 200.01, "close": 253.16}
        ])
        with patch.object(TDXRealtimeFetcher.get_instance(), "fetch_kline_bars", return_value=mock_df_1day):
            if hasattr(self.engine, "_first_listing_day_cache"):
                self.engine._first_listing_day_cache.pop("688835", None)
            self.assertTrue(self.engine.is_stock_first_listing_day("688835"))

        # B. 智能防误判：名称虽然残留叫 'N高凯'，但已有 2 根日 K 线（上市第 2 天） -> 必须智能判定为非首日 False！
        mock_df_2days = pd.DataFrame([
            {"datetime": "2026-08-24 15:00", "open": 209.00, "high": 262.00, "low": 200.01, "close": 253.16},
            {"datetime": f"{today_str} 15:00", "open": 250.00, "high": 270.00, "low": 245.00, "close": 265.00}
        ])
        with patch("ats.intraday_strategy_engine.resolve_stock_name", return_value="N高凯"), \
             patch.object(TDXRealtimeFetcher.get_instance(), "fetch_kline_bars", return_value=mock_df_2days):
            if hasattr(self.engine, "_first_listing_day_cache"):
                self.engine._first_listing_day_cache.pop("688835", None)
            self.assertFalse(self.engine.is_stock_first_listing_day("688835"), "名称残留 N 但已有 2 根日 K 时，必须智能识破判定为非首日！")

        # C. 智能防误判：名称叫 'N高凯' 但日 K 记录为历史过去的交易日 -> 判定为非首日 False！
        mock_df_past_1day = pd.DataFrame([
            {"datetime": "2026-08-20 15:00", "open": 209.00, "high": 262.00, "low": 200.01, "close": 253.16}
        ])
        with patch("ats.intraday_strategy_engine.resolve_stock_name", return_value="N高凯"), \
             patch.object(TDXRealtimeFetcher.get_instance(), "fetch_kline_bars", return_value=mock_df_past_1day):
            if hasattr(self.engine, "_first_listing_day_cache"):
                self.engine._first_listing_day_cache.pop("688835", None)
            self.assertFalse(self.engine.is_stock_first_listing_day("688835"), "日 K 为过去交易日时必须判定为非首日！")

        # D. 历史老股（有多个日 K 且名称不带 N）判定为非首日
        mock_df_old = pd.DataFrame([
            {"datetime": "2026-08-22 15:00", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5},
            {"datetime": "2026-08-24 15:00", "open": 10.5, "high": 11.5, "low": 10.2, "close": 11.2},
            {"datetime": f"{today_str} 15:00", "open": 11.2, "high": 12.0, "low": 11.0, "close": 11.8}
        ])
        with patch("ats.intraday_strategy_engine.resolve_stock_name", return_value="贵州茅台"), \
             patch.object(TDXRealtimeFetcher.get_instance(), "fetch_kline_bars", return_value=mock_df_old), \
             patch.object(TDXRealtimeFetcher.get_instance(), "get_yesterday_ohlc", return_value={"open": 10.5, "high": 11.5, "low": 10.2, "close": 11.2}):
            if hasattr(self.engine, "_first_listing_day_cache"):
                self.engine._first_listing_day_cache.pop("600519", None)
            self.assertFalse(self.engine.is_stock_first_listing_day("600519"))

    def test_04_auto_select_strategy(self):
        """测试 4: 策略自动匹配路由检验"""
        # A. 688835 (N高凯) 在首日上市时，必须匹配到高凯专属首日策略或新股策略，绝不匹配日常策略
        with patch.object(self.engine, "is_stock_first_listing_day", return_value=True):
            st = self.engine.auto_select_strategy(open_price=209.0, code="688835")
            self.assertIsNotNone(st)
            self.assertNotEqual(st.get("id"), "strategy_c_daily_surge_ladder", "首日新股绝不能匹配日常策略")
            self.assertTrue("688835" in st.get("id") or "gaokai" in st.get("id") or "stock_spec" in st)

        # B. 非首日老股必须 100% 匹配日常策略
        with patch.object(self.engine, "is_stock_first_listing_day", return_value=False):
            st_daily = self.engine.auto_select_strategy(open_price=100.0, code="600519")
            self.assertEqual(st_daily.get("id"), "strategy_c_daily_surge_ladder")

    def test_05_generator_phases_have_rules(self):
        """测试 5: NewStockStrategyGenerator 生成的策略 phases 必须内置 rules"""
        gen = NewStockStrategyGenerator.get_instance()
        strat = gen.generate_strategy({
            "code": "688899",
            "name": "测试新股",
            "issue_price": 50.0,
            "price": 150.0,
            "float_mv_yi": 10.0
        })
        phases = strat.get("phases", [])
        self.assertGreater(len(phases), 0)
        
        has_surge_rule = False
        for p in phases:
            for r in p.get("rules", []):
                if "surge" in r.get("rule_id", "") or "1.10" in r.get("trigger_expr", ""):
                    has_surge_rule = True
        self.assertTrue(has_surge_rule, "生成的新股策略必须包含早盘冲高卖出规则 rules")


if __name__ == "__main__":
    unittest.main()
