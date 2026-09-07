# -*- coding: utf-8 -*-
"""
tests/test_capital_dragon_engine.py — 资金趋势与真龙辨识度核心量化引擎单元测试
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.capital_dragon_engine import CapitalDragonEngine, _clean_code, _safe_float


class TestCapitalDragonEngine(unittest.TestCase):

    def test_safe_helpers(self):
        self.assertEqual(_safe_float(None), 0.0)
        self.assertEqual(_safe_float("--"), 0.0)
        self.assertEqual(_safe_float("12.34"), 12.34)
        self.assertEqual(_clean_code("sh600519"), "600519")
        self.assertEqual(_clean_code(1), "000001")
        self.assertEqual(_clean_code("300750.SZ"), "300750")

    def test_capital_dragon_engine_analysis(self):
        engine = CapitalDragonEngine.get_instance()

        # 构建模拟测试全市场数据
        data = {
            # 1. 空间高度龙 (3连板)
            "600108": {
                "name": "亚盛集团", "close": 3.85, "percent": 10.0, "amount": 8.5e8,
                "category": "农业种植;西部大开发", "dff": 2.5, "dff2": 6.8, "dff3": 12.0, "ma20d": 3.2
            },
            # 2. 趋势容量中军 (45亿成交额 + 多头向上)
            "300750": {
                "name": "宁德时代", "close": 265.0, "percent": 4.8, "amount": 4.5e9,
                "category": "固态电池;锂电池", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 240.0
            },
            # 3. 主线先锋龙 (电池板块首板)
            "002812": {
                "name": "恩捷股份", "close": 42.5, "percent": 9.98, "amount": 1.2e9,
                "category": "固态电池;锂电池", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 38.0
            },
            # 4. 固态电池板块助攻中坚
            "300037": {
                "name": "新宙邦", "close": 38.2, "percent": 5.6, "amount": 6.8e8,
                "category": "固态电池;氟化工", "dff": 0.8, "dff2": 3.2, "dff3": 6.0, "ma20d": 35.0
            },
            # 5. 孤狼杂毛 (成交额仅3000万，无板块支持，脉冲冲高)
            "000002": {
                "name": "边缘杂毛", "close": 8.5, "percent": 2.5, "amount": 3.0e7,
                "category": "房地产;其他", "dff": 0.1, "dff2": -1.0, "dff3": -2.0, "ma20d": 8.4
            },
            # 6. 破位诱多 (空头向下，拉升诱多)
            "000003": {
                "name": "破位阴跌", "close": 5.2, "percent": 3.2, "amount": 1.5e8,
                "category": "光伏设备;旧能源", "dff": -2.0, "dff2": -8.5, "dff3": -12.0, "ma20d": 6.1
            }
        }

        df = pd.DataFrame.from_dict(data, orient='index')

        report = engine.analyze_capital_dragon_universe(df, sh_pct=0.5, force=True)

        self.assertIn("top_sectors", report)
        self.assertIn("dragon_records", report)
        self.assertIn("dragon_codes_set", report)
        self.assertIn("trap_codes_set", report)

        # 验证主线板块识别 (固态电池应该排名靠前)
        sec_names = [s["name"] for s in report["top_sectors"]]
        self.assertTrue(any("固态电池" in s for s in sec_names))

        # 验证真龙代码集
        dragon_codes = report["dragon_codes_set"]
        self.assertIn("300750", dragon_codes)  # 容量中军必须在
        self.assertIn("002812", dragon_codes)  # 主线先锋必须在

        # 验证黑名单/陷阱代码集
        trap_codes = report["trap_codes_set"]
        self.assertTrue("000002" in trap_codes or "000003" in trap_codes)
        self.assertNotIn("000002", dragon_codes)
        self.assertNotIn("000003", dragon_codes)

        # 验证宁德时代的角色为容量中军
        nd_info = engine.get_dragon_info("300750")
        self.assertIsNotNone(nd_info)
        self.assertIn("容量中军", nd_info["role"])
        self.assertGreaterEqual(nd_info["amount_yi"], 40.0)
        self.assertIn("buy_zone", nd_info)
        self.assertGreater(nd_info["stop_loss"], 0)

        # 验证单例状态接口
        self.assertTrue(engine.is_true_dragon("300750"))
        self.assertFalse(engine.is_true_dragon("000002"))


if __name__ == "__main__":
    unittest.main()
