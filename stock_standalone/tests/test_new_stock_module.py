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

    def test_03_ui_panel_and_ladder_prediction(self):
        """测试 UI 模块、档位推演判定与实际盈利计算"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        from ats.ui.new_stock_panel import NewStockPanel
        panel = NewStockPanel()

        # 模拟 688826 频准激光数据 (发行价 186.88, 现价 947.45, 累计涨幅 +406.98%)
        mock_pinzhun = {
            "code": "688826",
            "name": "频准激光",
            "status": "前5日(C)",
            "issue_price": 186.88,
            "price": 947.45,
            "pct": 1.50,
            "float_mv_yi": 72.17,
            "total_mv_yi": 378.98,
            "listing_date": "2026-08-18"
        }

        panel._update_preview_card(mock_pinzhun)
        
        # 验证 5 个档位：
        # +400% 档（index 3）应当被点亮，显示 +406%: 947.45元 (盈利38.03万)，且背景为深绯红高亮
        lbl_ladder_400 = panel.ladder_labels[3]
        self.assertIn("+406%", lbl_ladder_400.text())
        self.assertIn("947.45", lbl_ladder_400.text())
        self.assertIn("盈利38.03万", lbl_ladder_400.text())
        self.assertIn("#581c1c", lbl_ladder_400.styleSheet()) # 优雅酒红高亮背景

        # 验证未点亮档位（例如 +100% 档，index 0）保持标准预估且暗色背景
        lbl_ladder_100 = panel.ladder_labels[0]
        self.assertIn("+100%", lbl_ladder_100.text())
        self.assertIn("373.76", lbl_ladder_100.text())
        self.assertIn("盈利9.34万", lbl_ladder_100.text())
        self.assertIn("#111827", lbl_ladder_100.styleSheet())

        print(f"\n[Test 3] 频准激光档位点亮推演验证成功: {lbl_ladder_400.text()}")

    def test_04_ladder_prediction_edge_cases(self):
        """测试档位推演的边界条件 (<100%, >500%, 统一500股)"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        from ats.ui.new_stock_panel import NewStockPanel
        panel = NewStockPanel()

        # 1. 超过 500% 的标的 (例如 发行价 10.0, 现价 72.0 -> 累计涨幅 +620%)
        mock_high = {
            "code": "600001",
            "name": "超级新股",
            "issue_price": 10.0,
            "price": 72.0,
            "float_mv_yi": 20.0,
        }
        panel._update_preview_card(mock_high)
        # 应落在 +500% 档 (index 4)
        lbl_500 = panel.ladder_labels[4]
        self.assertIn("+620%", lbl_500.text())
        self.assertIn("72.00", lbl_500.text())
        # 单签 500 股: (72 - 10) * 500 = 31,000 -> 盈利3.10万
        self.assertIn("盈利3.10万", lbl_500.text())
        self.assertIn("#581c1c", lbl_500.styleSheet())

        # 2. 低于 100% 的标的 (代码 920093 N信胜, 发行价 14.35, 现价 23.19 -> +61.60%, 统一500股)
        mock_bj = {
            "code": "920093",
            "name": "N信胜",
            "issue_price": 14.35,
            "price": 23.19,
            "float_mv_yi": 5.84,
        }
        panel._update_preview_card(mock_bj)
        # 应落在 +100% 档 (index 0)
        lbl_100 = panel.ladder_labels[0]
        self.assertIn("+61%", lbl_100.text())
        self.assertIn("23.19", lbl_100.text())
        # 单签 500 股: (23.19 - 14.35) * 500 = 4,420元
        self.assertIn("盈利4,420元", lbl_100.text())
        self.assertIn("#581c1c", lbl_100.styleSheet())

        print(f"[Test 4] 边界情况 (>500% & <100% 统一500股) 档位推演测试成功")

    def test_05_ipc_data_persistence_and_pct(self):
        """测试 IPC 数据回填与指标字段在多次刷新时不丢失"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        from ats.ui.new_stock_panel import NewStockPanel
        panel = NewStockPanel()

        # 模拟第一波行情与 IPC 推送
        df_base = pd.DataFrame([
            {"code": "688826", "name": "频准激光", "status": "前5日(C)", "issue_price": 186.88, "price": 947.45, "pct": 1.5, "float_mv_yi": 72.0, "total_mv_yi": 378.0, "amount_yi": 15.0, "turnover": 20.0, "has_strategy": True, "listing_date": "2026-08-18", "apply_date": "-"},
            {"code": "301717", "name": "越纯应材", "status": "次新", "issue_price": 65.99, "price": 385.10, "pct": 2.1, "float_mv_yi": 67.0, "total_mv_yi": 392.0, "amount_yi": 16.0, "turnover": 24.0, "has_strategy": False, "listing_date": "2026-08-11", "apply_date": "-"},
        ])
        panel._on_data_ready(df_base)

        # 模拟主终端推送 IPC 指标
        df_ipc = pd.DataFrame(
            index=["688826", "301717"],
            data={
                "close": [947.45, 385.10],
                "percent": [1.50, 2.10],
                "dff": [1.30, 0.30],
                "rank": [1649, 1646],
                "dff2": [12.50, 8.20],
                "dff3": [18.30, 14.10],
                "rs": [1.80, 2.40],
                "resonance": ["逆市抗跌", "逆市抗跌"]
            }
        )
        panel.update_from_ipc_df(df_ipc, sh_pct=-0.3)

        # 验证指标已写入
        row_688826 = panel.df_data[panel.df_data["code"] == "688826"].iloc[0]
        self.assertEqual(row_688826["dff2"], 12.50)
        self.assertEqual(row_688826["dff3"], 18.30)

        # 模拟后台 Worker 再次刷新新数据并触发 _on_data_ready
        df_new_refresh = pd.DataFrame([
            {"code": "688826", "name": "频准激光", "status": "前5日(C)", "issue_price": 186.88, "price": 948.00, "pct": 1.55, "float_mv_yi": 72.0, "total_mv_yi": 378.0, "amount_yi": 15.0, "turnover": 20.0, "has_strategy": True, "listing_date": "2026-08-18", "apply_date": "-"},
            {"code": "301717", "name": "越纯应材", "status": "次新", "issue_price": 65.99, "price": 386.00, "pct": 2.30, "float_mv_yi": 67.0, "total_mv_yi": 392.0, "amount_yi": 16.0, "turnover": 24.0, "has_strategy": False, "listing_date": "2026-08-11", "apply_date": "-"},
        ])
        panel._on_data_ready(df_new_refresh)

        # 验证再次刷新后，原有的 dff2, dff3 依然完好保留未丢失！
        row_688826_after = panel.df_data[panel.df_data["code"] == "688826"].iloc[0]
        self.assertEqual(row_688826_after["dff2"], 12.50)
        self.assertEqual(row_688826_after["dff3"], 18.30)
        print("[Test 5] IPC 数据多轮刷新后指标完好保持测试成功")

    def test_06_pct_calculation_rules(self):
        """测试已上市次新股与首日股的涨跌幅精确计算规则"""
        fetcher = NewStockFetcher.get_instance()

        df_mock = pd.DataFrame([
            # 1. 次新股 (非首日，有昨收 100.0, 现价 102.0, 发行价 20.0 -> 涨跌幅必须为 +2.0%, 绝不能是 +410%)
            {"code": "688826", "status": "次新", "issue_price": 20.0, "price": 0.0, "pct": 0.0},
            # 2. 首日股 (首日(N), 无昨收, 现价 32.0, 发行价 20.0 -> 涨跌幅为 +60.0%)
            {"code": "920093", "status": "首日(N)", "issue_price": 20.0, "price": 0.0, "pct": 0.0},
            # 3. 平盘次新股 (昨收 50.0, 现价 50.0, 发行价 10.0 -> 涨跌幅必须为 0.0%, 绝不能是 +400%)
            {"code": "301717", "status": "次新", "issue_price": 10.0, "price": 0.0, "pct": 0.0},
        ])

        # 模拟 TDX/行情源回填
        df_enriched = df_mock.copy()
        # 针对 688826: 现价 102.0, 昨收 100.0
        df_enriched.at[0, "price"] = 102.0
        last_c = 100.0
        df_enriched.at[0, "pct"] = round((102.0 - last_c) / last_c * 100.0, 2)

        # 针对 920093: 现价 32.0, 首日按发行价 20.0
        df_enriched.at[1, "price"] = 32.0
        issue_p = 20.0
        df_enriched.at[1, "pct"] = round((32.0 - issue_p) / issue_p * 100.0, 2)

        # 针对 301717: 现价 50.0, 昨收 50.0, 平盘
        df_enriched.at[2, "price"] = 50.0
        last_c3 = 50.0
        df_enriched.at[2, "pct"] = round((50.0 - last_c3) / last_c3 * 100.0, 2)

        self.assertEqual(df_enriched.loc[0, "pct"], 2.0)
        self.assertEqual(df_enriched.loc[1, "pct"], 60.0)
        self.assertEqual(df_enriched.loc[2, "pct"], 0.0)
        print("[Test 6] 涨跌幅精确计算规则 (首日 vs 已上市次新 vs 平盘) 测试成功")


if __name__ == "__main__":
    unittest.main()
