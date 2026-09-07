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

        # 验证系统虚拟量比与板块预估成交额 (SSOT)
        self.assertIn("vol_ratio", nd_info)
        self.assertGreaterEqual(nd_info["vol_ratio"], 0.1)
        sec_battery = next(s for s in report["top_sectors"] if "固态电池" in s["name"])
        self.assertIn("vol_ratio", sec_battery)
        self.assertIn("proj_amt_yi", sec_battery)
        self.assertGreater(sec_battery["proj_amt_yi"], 0.0)

    def test_index_filtering_and_acceleration_features(self):
        from ats.capital_dragon_engine import is_index_or_fund
        # 1. 验证指数过滤
        self.assertTrue(is_index_or_fund("399005", "中小100"))
        self.assertTrue(is_index_or_fund("999999", "上证指数"))
        self.assertTrue(is_index_or_fund("899050", "北证50"))
        self.assertTrue(is_index_or_fund("000001", "上证指数"))
        self.assertFalse(is_index_or_fund("000001", "平安银行"))
        self.assertFalse(is_index_or_fund("600519", "贵州茅台"))

        # 2. 验证包含指数与双加速/缺口加速标的的全量分析
        engine = CapitalDragonEngine.get_instance()
        data = {
            # 指数：巨额成交量，必须被过滤
            "399005": {
                "name": "中小100", "close": 8480.0, "open": 8400.0, "low": 8390.0, "last_close": 8350.0,
                "percent": 1.5, "amount": 3.7e11, "category": "0", "dff": 0.0, "dff2": 10.0, "dff3": 20.0, "ma20d": 8000.0
            },
            "999999": {
                "name": "上证指数", "close": 3932.0, "open": 3930.0, "low": 3925.0, "last_close": 3920.0,
                "percent": 0.3, "amount": 1.8e11, "category": "0", "dff": 0.0, "dff2": 5.0, "dff3": 10.0, "ma20d": 3800.0
            },
            # 真实个股 A：双加速 (跳空高开 + 开盘即最低)
            "300308": {
                "name": "中际旭创", "close": 898.0, "open": 880.0, "low": 880.0, "last_close": 850.0, "lasth1d": 860.0,
                "percent": 10.38, "amount": 3.8e9, "category": "共封装光学(CPO);光通信", "dff": 1.5, "dff2": 16.8, "dff3": 65.6, "ma20d": 800.0
            },
            # 真实个股 B：缺口加速 (跳空高开且缺口未补，但有微小下影)
            "300502": {
                "name": "新易盛", "close": 417.0, "open": 405.0, "low": 402.0, "last_close": 390.0, "lasth1d": 395.0,
                "percent": 8.08, "amount": 2.1e9, "category": "共封装光学(CPO);光通信", "dff": 1.4, "dff2": 11.9, "dff3": 59.1, "ma20d": 370.0
            },
            # 真实个股 C：光脚加速 (平开/低开但开盘即最低)
            "002384": {
                "name": "东山精密", "close": 190.5, "open": 180.0, "low": 180.0, "last_close": 180.0, "lasth1d": 185.0,
                "percent": 6.65, "amount": 1.3e9, "category": "共封装光学(CPO);消费电子", "dff": 1.2, "dff2": 10.9, "dff3": 27.8, "ma20d": 170.0
            }
        }
        df = pd.DataFrame.from_dict(data, orient='index')
        report = engine.analyze_capital_dragon_universe(df, force=True)

        dragon_codes = report["dragon_codes_set"]
        # 指数与基金保留在候选池中，便于操盘手即时纵览全景综合走势
        self.assertIn("399005", dragon_codes)
        self.assertIn("999999", dragon_codes)
        info_399 = engine.get_dragon_info("399005")
        self.assertIsNotNone(info_399)
        self.assertEqual(info_399.get("sector"), "综合指数/ETF")

        # 验证同时包含全量池与极限性能收敛池
        self.assertIn("dragon_records_all", report)
        self.assertIn("dragon_records_converged", report)
        self.assertGreaterEqual(len(report["dragon_records_all"]), len(report["dragon_records_converged"]))

        # 验证中际旭创被标记为双加速
        zj_info = engine.get_dragon_info("300308")
        self.assertIsNotNone(zj_info)
        self.assertEqual(zj_info.get("accel_tag"), "👑双加速")
        self.assertTrue(zj_info.get("is_dual_accel"))
        self.assertIn("👑双加速", zj_info.get("action_type"))

        # 验证新易盛被标记为缺口加速
        xys_info = engine.get_dragon_info("300502")
        self.assertIsNotNone(xys_info)
        self.assertEqual(xys_info.get("accel_tag"), "🚀缺口加速")
        self.assertTrue(xys_info.get("is_gap_accel"))

        # 验证板块加速计数与加成
        sec_cpo = next(s for s in report["top_sectors"] if "共封装光学" in s["name"])
        self.assertGreaterEqual(sec_cpo.get("accel_total_count", 0), 2)
        self.assertGreaterEqual(sec_cpo.get("dual_accel_count", 0), 1)

    def test_virtual_vol_ratio_no_zero_bug(self):
        """验证虚拟量比彻底根治 0.00x Bug：当某些非强势标的 vol_ratio 为 0 时，自动赋能投影或兜底 1.0"""
        engine = CapitalDragonEngine.get_instance()
        data = {
            "000333": {"name": "美的集团", "close": 86.0, "percent": -1.0, "amount": 1.9e9, "vol_ratio": 0.0, "vol": 2e7, "lastv1d": 2e7},
            "601988": {"name": "中国银行", "close": 6.4, "percent": -1.5, "amount": 1.8e9, "vol_ratio": 0.0, "vol": 3e8, "lastv1d": 3e8},
            "601138": {"name": "工业富联", "close": 66.0, "percent": 4.5, "amount": 1.1e10, "vol_ratio": 1.52, "vol": 1e8, "lastv1d": 8e7}
        }
        df = pd.DataFrame.from_dict(data, orient='index')
        vr_series = engine._get_virtual_vol_ratio(df)
        self.assertEqual(vr_series.loc["601138"], 1.52)
        # 美的集团与中国银行绝不允许出现 0.00x！必须 >= 0.1 且有效
        self.assertGreaterEqual(float(vr_series.loc["000333"]), 0.5)
        self.assertGreaterEqual(float(vr_series.loc["601988"]), 0.5)

    def test_tdx_index_amount_correction_and_api(self):
        """验证通达信 TDX API 接口对 399xxx, 999xxx, 899xxx 等指数成交额真实修正"""
        engine = CapitalDragonEngine.get_instance()
        # 测试直接调用 _fetch_tdx_index_data
        idx_data = engine._fetch_tdx_index_data(["399006", "399001", "899050"])
        if idx_data:
            # 创业板指 399006 真实成交额约为 5000+ 亿 (严禁出现 563725.1亿 的点数乘股数异常值)
            if "399006" in idx_data:
                amt_399006 = idx_data["399006"]["amount_yi"]
                self.assertGreater(amt_399006, 1000.0)
                self.assertLess(amt_399006, 20000.0)
            # 深证成指 399001 真实成交额约为 10000+ 亿 (严禁出现 8094494.2亿 异常值)
            if "399001" in idx_data:
                amt_399001 = idx_data["399001"]["amount_yi"]
                self.assertGreater(amt_399001, 2000.0)
                self.assertLess(amt_399001, 30000.0)


if __name__ == "__main__":
    unittest.main()
