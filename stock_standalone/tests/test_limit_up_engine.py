# -*- coding: utf-8 -*-
"""
tests/test_limit_up_engine.py — ATS 每日涨停与多日强势股核心引擎单元测试
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

# 确保项目根目录在 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.limit_up_engine import (
    LimitUpEngine, 
    get_limit_up_ratio_threshold, 
    calc_theoretical_limit_up_price,
    get_ats_custom_extra_cols
)


class TestLimitUpEngine(unittest.TestCase):

    def setUp(self):
        self.engine = LimitUpEngine.get_instance()

    def test_limit_up_ratio_thresholds(self):
        """测试不同板块涨停阈值"""
        self.assertEqual(get_limit_up_ratio_threshold("600519"), 9.8) # 沪市主板
        self.assertEqual(get_limit_up_ratio_threshold("000001"), 9.8) # 深市主板
        self.assertEqual(get_limit_up_ratio_threshold("300750"), 19.5) # 创业板
        self.assertEqual(get_limit_up_ratio_threshold("688981"), 19.5) # 科创板
        self.assertEqual(get_limit_up_ratio_threshold("920093"), 29.2) # 北交所
        self.assertEqual(get_limit_up_ratio_threshold("830001"), 29.2) # 北交所
        self.assertEqual(get_limit_up_ratio_threshold("600000", name="*ST华仪"), 4.85) # ST股

    def test_calc_theoretical_limit_up_price(self):
        """测试理论涨停价计算"""
        self.assertEqual(calc_theoretical_limit_up_price("600519", 10.0), 11.00)
        self.assertEqual(calc_theoretical_limit_up_price("300750", 10.0), 12.00)
        self.assertEqual(calc_theoretical_limit_up_price("920093", 10.0), 13.00)
        self.assertEqual(calc_theoretical_limit_up_price("600000", 10.0, name="ST股票"), 10.50)

    def test_scan_limit_up_records_from_df(self):
        """测试从 DataFrame 扫描识别涨停与封单/量能特征"""
        mock_data = [
            {
                "code": "600001",
                "name": "主板龙头",
                "close": 11.00,
                "price": 11.00,
                "trade": 11.00,
                "last_close": 10.00,
                "open": 10.50,
                "high": 11.00,
                "low": 10.40,
                "percent": 10.00,
                "pct": 10.00,
                "volume": 50000,
                "vol": 50000,
                "amount": 55000000,
                "dff": 3.5,
                "dff2": 18.0,
                "dff3": 45.0,
                "rank": 1,
                "category": "半导体",
                "ch_bc2": "3.88"
            },
            {
                "code": "300002",
                "name": "创板先锋",
                "close": 24.00,
                "price": 24.00,
                "trade": 24.00,
                "last_close": 20.00,
                "open": 21.00,
                "high": 24.00,
                "low": 20.80,
                "percent": 20.00,
                "pct": 20.00,
                "volume": 80000,
                "vol": 80000,
                "amount": 180000000,
                "dff": 5.2,
                "dff2": 22.5,
                "dff3": 60.0,
                "rank": 2,
                "category": "CPO",
                "ch_bc2": "5.12"
            },
            {
                "code": "600003",
                "name": "炸板股票",
                "close": 10.40,
                "price": 10.40,
                "trade": 10.40,
                "last_close": 10.00,
                "open": 10.00,
                "high": 11.00,
                "low": 9.90,
                "percent": 4.00,
                "pct": 4.00,
                "volume": 120000,
                "vol": 120000,
                "amount": 125000000,
                "dff": -1.2,
                "dff2": 5.0,
                "dff3": 12.0,
                "rank": 35,
                "category": "医药",
                "ch_bc2": "-0.50"
            }
        ]
        df = pd.DataFrame(mock_data)
        df.set_index("code", drop=False, inplace=True)

        records = self.engine.scan_limit_up_records_from_df(df, fetch_l2_quotes=False)
        self.assertGreaterEqual(len(records), 2)

        # 检查主板龙头
        r_zb = next((r for r in records if r["code"] == "600001"), None)
        self.assertIsNotNone(r_zb)
        self.assertTrue(r_zb["is_limit_up"])
        self.assertEqual(r_zb["dff"], 3.5)
        self.assertEqual(r_zb["dff2"], 18.0)
        self.assertEqual(r_zb["dff3"], 45.0)

        # 检查创板先锋
        r_cb = next((r for r in records if r["code"] == "300002"), None)
        self.assertIsNotNone(r_cb)
        self.assertTrue(r_cb["is_limit_up"])
        self.assertEqual(r_cb["pct"], 20.00)

        # 检查炸板
        r_zb_broken = next((r for r in records if r["code"] == "600003"), None)
        self.assertIsNotNone(r_zb_broken)
        self.assertTrue(r_zb_broken["is_broken"])

    def test_multi_day_aggregation_and_persistence(self):
        """测试多日历史强势股聚合与原子持久化"""
        test_date_1 = "2099-12-01"
        test_date_2 = "2099-12-02"
        
        recs_1 = [
            {
                "code": "600999",
                "name": "多日牛股",
                "price": 11.00,
                "pct": 10.00,
                "is_limit_up": True,
                "is_broken": False,
                "consecutive_boards": 1,
                "seal_to_circ_ratio": 6.5,
                "dff": 2.5,
                "dff2": 15.0,
                "dff3": 35.0,
                "rank": 1,
                "extra_cols": {}
            }
        ]
        recs_2 = [
            {
                "code": "600999",
                "name": "多日牛股",
                "price": 12.10,
                "pct": 10.00,
                "is_limit_up": True,
                "is_broken": False,
                "consecutive_boards": 2,
                "seal_to_circ_ratio": 8.0,
                "dff": 4.0,
                "dff2": 26.5,
                "dff3": 48.5,
                "rank": 1,
                "extra_cols": {}
            }
        ]

        try:
            self.engine.save_daily_records_atomic(test_date_1, recs_1, allow_test_date=True)
            self.engine.save_daily_records_atomic(test_date_2, recs_2, allow_test_date=True)

            # 聚合测试
            strong_stocks = self.engine.aggregate_multi_day_strong_stocks(days=2, min_limit_ups=1)
            self.assertGreaterEqual(len(strong_stocks), 1)
            target = next((s for s in strong_stocks if s["code"] == "600999"), None)
            self.assertIsNotNone(target)
            self.assertEqual(target["zt_count"], 2)
            self.assertIn("2板", target["n_days_m_boards"])
        finally:
            # 彻底清理测试数据，绝不污染生产环境持久化文件
            with self.engine._cache_lock:
                self.engine._history_daily_records.pop(test_date_1, None)
                self.engine._history_daily_records.pop(test_date_2, None)
            from ats.limit_up_engine import ARCHIVE_PREFIX, LIMIT_UP_RECORDS_FILE, _safe_atomic_write_json_gz
            for d in [test_date_1, test_date_2]:
                for ext in [".json.gz", ".json"]:
                    f_path = f"{ARCHIVE_PREFIX}{d}{ext}"
                    if os.path.exists(f_path):
                        try:
                            os.remove(f_path)
                        except Exception:
                            pass
            # 确保主文件中也绝不残留 2099 测试键
            with self.engine._cache_lock:
                pure_data = {k: v for k, v in self.engine._history_daily_records.items() if not k.startswith("2099")}
                _safe_atomic_write_json_gz(LIMIT_UP_RECORDS_FILE, pure_data)

    def test_dirty_future_date_filtering_and_self_healing(self):
        """测试 2099 等未来脏日期的合法性拦截、持久化防污染与自愈清洗"""
        from ats.limit_up_engine import _is_valid_trade_date_str

        # 1. 验证日期格式与未来年份校验
        self.assertFalse(_is_valid_trade_date_str("2099-12-02"))
        self.assertFalse(_is_valid_trade_date_str("2099-12-01"))
        self.assertFalse(_is_valid_trade_date_str("invalid-date"))
        self.assertTrue(_is_valid_trade_date_str("2026-08-28"))

        # 2. 默认模式下 save_daily_records_atomic 拒绝写入未来测试日期
        test_future_date = "2099-12-03"
        self.engine.save_daily_records_atomic(test_future_date, [{"code": "600000", "price": 10.0}])
        self.assertNotIn(test_future_date, self.engine._history_daily_records, "生产模式下应主动拦截未来脏日期写盘")

        # 3. 验证 get_all_archived_dates 绝不返回 2099 等未来日期
        with self.engine._cache_lock:
            # 假设内存中意外混入脏数据
            self.engine._history_daily_records["2099-12-05"] = [{"code": "000001"}]
        try:
            archived = self.engine.get_all_archived_dates()
            self.assertNotIn("2099-12-05", archived, "get_all_archived_dates 必须自动过滤未来脏日期")
        finally:
            with self.engine._cache_lock:
                self.engine._history_daily_records.pop("2099-12-05", None)


if __name__ == "__main__":
    unittest.main()
