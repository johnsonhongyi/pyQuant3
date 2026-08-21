# -*- coding: utf-8 -*-
"""
tests/test_new_stock_module.py — 验证新股/次新股获取与分时阶梯策略自动生成模块
"""

import sys
import os
import unittest
import pandas as pd

# 加入项目根目录
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.new_stock_fetcher import NewStockFetcher
from ats.new_stock_strategy_generator import NewStockStrategyGenerator
from ats.intraday_strategy_engine import IntradayStrategyEngine


class TestNewStockModule(unittest.TestCase):

    def test_01_fetch_ipo_and_spot(self):
        """测试新股日历与实时行情抓取"""
        fetcher = NewStockFetcher.get_instance()
        df = fetcher.get_combined_new_stocks(force_refresh=True)
        print(f"\n[Test 1] 抓取到综合新股/次新股数量: {len(df)}")
        self.assertFalse(df.empty, "综合新股列表不应为空")
        self.assertIn("code", df.columns)
        self.assertIn("name", df.columns)
        self.assertIn("status", df.columns)
        self.assertIn("has_strategy", df.columns)

    def test_02_strategy_generator(self):
        """测试自动生成分时阶梯策略与热重载"""
        generator = NewStockStrategyGenerator.get_instance()
        engine = IntradayStrategyEngine.get_instance()

        mock_stock = {
            "code": "688828",
            "name": "国仪公司-U",
            "issue_price": 21.22,
            "float_mv_yi": 24.70,
            "total_mv_yi": 379.45,
            "listing_date": "2026-08-11",
            "apply_date": "2026-07-31",
            "business_summary": "量子精密测量与高端科学仪器龙头",
            "sector_tags": ["量子科技", "科学仪器", "高端装备"]
        }

        strat = generator.generate_strategy(mock_stock)
        print(f"\n[Test 2] 生成策略 ID: {strat.get('id')}")
        self.assertEqual(strat.get("schema_version"), "v1.0-unified")
        self.assertIn("688828", strat.get("target_codes", []))
        
        spec = strat.get("stock_spec", {})
        self.assertEqual(spec.get("code"), "688828")
        self.assertEqual(spec.get("issue_price"), 21.22)
        self.assertEqual(len(spec.get("price_ladder", [])), 5)
        
        # 阶梯 +100% 价格应该为 21.22 * 2.0 = 42.44
        self.assertEqual(spec["price_ladder"][0]["price"], 42.44)
        # 阶梯 +200% 价格应该为 21.22 * 3.0 = 63.66
        self.assertEqual(spec["price_ladder"][1]["price"], 63.66)

        # 测试落盘与热重载
        ok = generator.save_or_update_strategy(strat)
        self.assertTrue(ok, "保存策略应该成功")

        # 检查引擎是否热重载到了该标的
        reloaded_spec = engine.get_stock_ladder_spec("688828")
        self.assertIsNotNone(reloaded_spec, "引擎应能加载到 688828 的 stock_spec")
        self.assertEqual(reloaded_spec.get("name"), "国仪公司-U")
        print(f"[Test 2] 引擎热重载验证成功: {reloaded_spec.get('name')} 发行价 {reloaded_spec.get('issue_price')}")

    def test_03_ui_panel_import(self):
        """测试 UI 模块与依赖导入"""
        from ats.ui.new_stock_panel import NewStockPanel
        self.assertIsNotNone(NewStockPanel)
        print("\n[Test 3] NewStockPanel 导入验证成功")


if __name__ == "__main__":
    unittest.main()
