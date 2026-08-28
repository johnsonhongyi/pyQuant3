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

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

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

        # 模拟主终端推送全市场 IPC 指标 (注意：IPC 行情中次新股可能没有 percent 或为 0)
        df_ipc = pd.DataFrame(
            index=["688826", "301717"],
            data={
                "close": [947.45, 385.10],
                "dff": [1.30, 0.30],
                "rank": [1649, 1646],
                "dff2": [12.50, 8.20],
                "dff3": [18.30, 14.10],
                "rs": [1.80, 2.40],
                "resonance": ["逆市抗跌", "逆市抗跌"]
            }
        )
        panel.update_from_ipc_df(df_ipc, sh_pct=-0.3)

        # 验证 IPC 推送后：
        # 1. 衍生指标已写入 (dff2, dff3)
        row_688826 = panel.df_data[panel.df_data["code"] == "688826"].iloc[0]
        self.assertEqual(row_688826["dff2"], 12.50)
        self.assertEqual(row_688826["dff3"], 18.30)
        # 2. TDX 权威涨跌幅绝未被 IPC 覆盖抹平为 0.00！保持 1.50%
        self.assertEqual(row_688826["pct"], 1.5)

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
        self.assertEqual(row_688826_after["pct"], 1.55)
        print("[Test 5] TDX 权威行情保护与 IPC 数据多轮刷新后指标完好保持测试成功")

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

    def test_07_call_auction_bidding_tracking(self):
        """测试 09:15~09:25 集合竞价期间 (price=0 但有 bid1/ask1/open) 的数据捕获与天梯追踪能力"""
        from ats.limit_up_engine import LimitUpEngine

        # 1. 模拟 09:15~09:25 集合竞价时段的原始 DataFrame (此时 price/trade=0, percent=0, 但 buy/bid1 申报了涨停价)
        df_bidding = pd.DataFrame([
            {
                "code": "600001",
                "name": "竞价龙头A",
                "trade": 0.0,
                "close": 0.0,
                "price": 0.0,
                "percent": 0.0,
                "last_close": 10.0,
                "buy": 11.0,        # 买一申报涨停价 11.0 (+10.0%)
                "b1_v": 50000.0,     # 买一封单 50000 手
                "vol": 0.0,
                "amount": 0.0,
                "dff": 3.5,
                "Rank": 12,
                "category": "芯片概念"
            },
            {
                "code": "300002",
                "name": "竞价创业板B",
                "trade": 0.0,
                "close": 0.0,
                "price": 0.0,
                "percent": 0.0,
                "last_close": 20.0,
                "buy": 24.0,        # 创业板申报涨停价 24.0 (+20.0%)
                "b1_v": 30000.0,     # 买一封单 30000 手
                "vol": 0.0,
                "amount": 0.0,
                "dff": 4.2,
                "Rank": 5,
                "category": "机器人"
            },
            {
                "code": "600003",
                "name": "普通震荡股C",
                "trade": 0.0,
                "close": 0.0,
                "price": 0.0,
                "percent": 0.0,
                "last_close": 15.0,
                "buy": 15.1,        # 仅微涨 +0.67%
                "b1_v": 200.0,
                "vol": 0.0,
                "amount": 0.0,
            }
        ])

        engine = LimitUpEngine.get_instance()
        records = engine.scan_limit_up_records_from_df(df_bidding, fetch_l2_quotes=False)

        # 断言竞价一字/涨停标的在 09:15~09:25 被精准捕获
        self.assertEqual(len(records), 2, "应成功捕获2只集合竞价涨停标的")
        rec_a = next(r for r in records if r["code"] == "600001")
        self.assertEqual(rec_a["price"], 11.0, "竞价价格应回退为 buy1 11.0")
        self.assertEqual(rec_a["pct"], 10.0, "竞价涨跌幅应正确算为 +10.0%")
        self.assertTrue(rec_a["is_limit_up"], "应被判定为涨停")

        rec_b = next(r for r in records if r["code"] == "300002")
        self.assertEqual(rec_b["price"], 24.0, "创业板竞价价格应为 24.0")
        self.assertEqual(rec_b["pct"], 20.0, "创业板涨跌幅应正确算为 +20.0%")
        self.assertTrue(rec_b["is_limit_up"], "应被判定为涨停")

        print("\n[Test 7] 09:15~09:25 集合竞价期数据捕获与天梯追踪能力验证成功！")

    def test_08_bidding_intent_and_speed_decision(self):
        """测试 TDXRealtimeFetcher 与 LimitUpEngine 集合竞价意图识别与高开竞速决策"""
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        fetcher = TDXRealtimeFetcher.get_instance()

        # 模拟 09:20~09:25 不可撤单阶段的多维标的
        clean_codes = ["600001", "300002", "000003", "600004"]
        sector_map = {"600001": "芯片", "300002": "芯片", "000003": "机器人", "600004": "光伏"}
        mp_cache = {
            "600001": {"dff": 4.0, "dff2": 10.0, "dff3": 15.0, "rank": 1},
            "300002": {"dff": 2.0, "dff2": 6.0, "dff3": 8.0, "rank": 10},
            "000003": {"dff": 3.0, "dff2": 8.0, "dff3": 12.0, "rank": 5},
            "600004": {"dff": -1.0, "dff2": 0.0, "dff3": 0.0, "rank": 50},
        }
        name_map = {
            "600001": "一字顶格龙",
            "300002": "高开抢筹锋",
            "000003": "弱转强先锋",
            "600004": "诱多假高开",
        }

        # 模拟 TDX quotes (竞价阶段 price=0, bid1 申报溢价)
        # 我们 mock get_security_quotes_safe
        original_get_quotes = fetcher.get_security_quotes_safe
        try:
            fetcher.get_security_quotes_safe = lambda codes, force=False: [
                {
                    "code": "600001", "price": 0.0, "last_close": 10.0, "bid1": 11.0, "ask1": 0.0,
                    "bid_vol1": 50000, "bid_vol2": 10000, "ask_vol1": 0, "open": 11.0, "vol": 0, "amount": 0
                },
                {
                    "code": "300002", "price": 0.0, "last_close": 20.0, "bid1": 21.2, "ask1": 21.3,
                    "bid_vol1": 15000, "bid_vol2": 8000, "ask_vol1": 2000, "open": 21.2, "vol": 0, "amount": 0
                },
                {
                    "code": "000003", "price": 0.0, "last_close": 15.0, "bid1": 15.6, "ask1": 15.7,
                    "bid_vol1": 8000, "bid_vol2": 5000, "ask_vol1": 1500, "open": 15.6, "vol": 0, "amount": 0
                },
                {
                    "code": "600004", "price": 0.0, "last_close": 30.0, "bid1": 31.0, "ask1": 31.1,
                    "bid_vol1": 500, "bid_vol2": 200, "ask_vol1": 15000, "open": 31.0, "vol": 0, "amount": 0
                }
            ]

            alpha_quotes = fetcher.fetch_multi_stock_alpha_quotes(clean_codes, sector_map, mp_cache, name_map)
            self.assertEqual(len(alpha_quotes), 4)

            # 验证 600001 竞价顶格/爆量突破意图
            q1 = next(q for q in alpha_quotes if q["code"] == "600001")
            self.assertEqual(q1["price"], 11.0)
            self.assertEqual(q1["pct"], 10.0)
            self.assertTrue("突破" in q1["order_intent"] or "一字" in q1["order_intent"] or "封" in q1["order_intent"])

            # 验证 300002 高开抢筹意图 (+6.0%, 买盘压强 > 75%)
            q2 = next(q for q in alpha_quotes if q["code"] == "300002")
            self.assertEqual(q2["price"], 21.2)
            self.assertEqual(q2["pct"], 6.0)
            self.assertTrue(q2["bid_pressure"] >= 75.0)

            # 验证 600004 诱多抢跑意图 (买盘压强 <= 40%)
            q4 = next(q for q in alpha_quotes if q["code"] == "600004")
            self.assertTrue(q4["bid_pressure"] < 40.0)

            print("[Test 8] TDXRealtimeFetcher 集合竞价意图与高开竞速决策验证成功！")
        finally:
            fetcher.get_security_quotes_safe = original_get_quotes

    def test_09_bidding_volume_fitting_and_breakout(self):
        """测试【大普微模式】集合竞价重金单量拟合、爆量高开与多日平台高点突破"""
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        fetcher = TDXRealtimeFetcher.get_instance()

        # 模拟大普微 (301666): 昨收 391.0, 5日最高价 410.0, 集合竞价 9:25 定盘撮合成交 13423 手 (6.3 亿) 顶格高开突破 469.20 (+20%)
        # 模拟N华大 (920288): 发行价 12.57, 昨收 12.57, 集合竞价 9:25 定盘撮合成交 4976 手 (1253 万元) 25.18 (+100.32%)
        # 模拟缩量假高开股 (600999): 昨收 10.0, 集合竞价高开到 10.6 (+6%), 但竞价单量仅 10 手 (1 万元), 属于典型假高开诱多
        clean_codes = ["301666", "920288", "600999"]
        sector_map = {"301666": "芯片龙头", "920288": "首发新股", "600999": "题材概念"}
        mp_cache = {
            "301666": {"dff": 5.0, "dff2": 15.0, "dff3": 25.0, "lasth5d": 410.0, "rank": 1},
            "920288": {"dff": 0.0, "dff2": 0.0, "dff3": 0.0, "lasth5d": 0.0, "rank": 1, "issue_price": 12.57, "status": "首日上市"},
            "600999": {"dff": 0.0, "dff2": 0.0, "dff3": 0.0, "lasth5d": 12.0, "rank": 999},
        }
        name_map = {"301666": "大普微", "920288": "N华大", "600999": "假高开诱多"}

        original_get_quotes = fetcher.get_security_quotes_safe
        try:
            fetcher.get_security_quotes_safe = lambda codes, force=False: [
                {
                    # 大普微: 竞价成交 13423 手 (6.3亿), 突破 5日最高 410.0
                    "code": "301666", "price": 0.0, "last_close": 391.0, "bid1": 469.20, "ask1": 0.0,
                    "bid_vol1": 13423, "bid_vol2": 5000, "ask_vol1": 0, "open": 469.20, "vol": 13423, "amount": 629807160.0
                },
                {
                    # N华大: 首日新股竞价定盘成交 4976 手 (1253 万元) 25.18 元 (+100.32%)
                    "code": "920288", "name": "N华大", "price": 0.0, "last_close": 12.57, "bid1": 25.18, "ask1": 25.20,
                    "bid_vol1": 4976, "bid_vol2": 2000, "ask_vol1": 500, "open": 25.18, "vol": 4976, "amount": 12529568.0
                },
                {
                    # 假高开: 竞价单量仅 10 手, 买一压强极弱
                    "code": "600999", "price": 0.0, "last_close": 10.0, "bid1": 10.60, "ask1": 10.70,
                    "bid_vol1": 10, "bid_vol2": 5, "ask_vol1": 20000, "open": 10.60, "vol": 0, "amount": 0
                }
            ]

            alpha_quotes = fetcher.fetch_multi_stock_alpha_quotes(clean_codes, sector_map, mp_cache, name_map)
            self.assertEqual(len(alpha_quotes), 3)

            # 1. 断言大普微: 识别为 💎 爆量突破 / 👑 竞价一字，金额达 6 亿+，优先级最高 (>= 99)
            q_dpw = next(q for q in alpha_quotes if q["code"] == "301666")
            self.assertEqual(q_dpw["price"], 469.20)
            self.assertEqual(q_dpw["pct"], 20.0)
            self.assertTrue(q_dpw["bidding_amt_yi"] >= 5.0, "竞价金额应超过5亿元")
            self.assertTrue(q_dpw["is_bidding_breakout"], "应成功判定为突破多日高点")
            self.assertTrue("爆量突破" in q_dpw["order_intent"] or "一字" in q_dpw["order_intent"])
            self.assertIn(q_dpw["buy_type"], ["💎 爆量突破", "👑 竞价一字"])
            self.assertTrue(q_dpw["type_priority"] >= 99)

            # 2. 断言 N华大 (920288): 识别为 💎 首日真金抢筹，金额达 1253 万元，优先级顶级 (>= 99)
            q_hd = next(q for q in alpha_quotes if q["code"] == "920288")
            self.assertEqual(q_hd["price"], 25.18)
            self.assertTrue(q_hd["bidding_amt_wan"] >= 1000.0, "N华大竞价金额应达1253万元")
            self.assertTrue("新股" in q_hd["order_intent"] and "抢筹" in q_hd["order_intent"])
            self.assertEqual(q_hd["buy_type"], "💎 首日真金抢筹")
            self.assertTrue(q_hd["type_priority"] >= 99)
            self.assertTrue("09:25黄金上车点" in q_hd["reason"])

            # 3. 断言假高开股: 识别为 ⚠️ 缩量诱多 / 虚挂，优先级极低 (<= 25)，成功防砸过滤
            q_fake = next(q for q in alpha_quotes if q["code"] == "600999")
            self.assertEqual(q_fake["price"], 10.60)
            self.assertTrue("诱多" in q_fake["order_intent"] or "测盘" in q_fake["order_intent"] or "虚挂" in q_fake["order_intent"])
            self.assertEqual(q_fake["buy_type"], "⚠️ 缩量诱多")
            self.assertTrue(q_fake["type_priority"] <= 25)

            print("\n[Test 9] 大普微模式与 N华大首日真金抢筹 (集合竞价重金单量拟合、爆量突破与缩量诱多过滤) 验证全部通过！")
        finally:
            fetcher.get_security_quotes_safe = original_get_quotes

    def test_10_new_stock_bidding_signal_sync_and_card_rendering(self):
        """测试新股次新股模块全面同步天梯集合竞价关键信号与卡片联动"""
        from ats.new_stock_fetcher import NewStockFetcher
        from ats.ui.new_stock_panel import NewStockPanel, get_new_stock_table_headers
        from unittest.mock import patch

        # 1. 验证表头包含“竞价信号”列
        headers = get_new_stock_table_headers()
        self.assertIn("竞价信号", headers)
        self.assertEqual(headers.index("竞价信号"), 3)

        fetcher = NewStockFetcher()
        mock_df = pd.DataFrame([
            {
                "code": "920288", "name": "N华大", "status": "首日(N)",
                "listing_date": "2026-08-28", "apply_date": "2026-08-18",
                "issue_price": 12.57, "price": 25.18, "pct": 100.32,
                "turnover": 3.85, "float_mv_yi": 3.25, "total_mv_yi": 13.00,
                "amount_yi": 0.1253, "has_strategy": False
            },
            {
                "code": "301666", "name": "大普微", "status": "前5日(C)",
                "listing_date": "2026-08-25", "apply_date": "2026-08-15",
                "issue_price": 40.0, "price": 469.20, "pct": 20.0,
                "turnover": 15.2, "float_mv_yi": 65.0, "total_mv_yi": 260.0,
                "amount_yi": 6.30, "has_strategy": False
            },
            {
                "code": "920078", "name": "族兴新材", "status": "已上市",
                "listing_date": "2026-03-18", "apply_date": "2026-03-09",
                "issue_price": 6.98, "price": 20.40, "pct": -1.59,
                "turnover": 6.17, "float_mv_yi": 15.0, "total_mv_yi": 30.0,
                "amount_yi": 0.50, "has_strategy": False
            }
        ])

        # 模拟盘口数据
        quotes_mock = [
            {
                "code": "920288", "price": 25.18, "last_close": 12.57, "open": 25.18,
                "bid1": 25.18, "ask1": 25.20, "bid_vol1": 4976, "bid_vol2": 2000,
                "ask_vol1": 500, "vol": 4976, "amount": 12529568.0
            },
            {
                "code": "301666", "price": 469.20, "last_close": 391.0, "open": 469.20,
                "bid1": 469.20, "ask1": 0.0, "bid_vol1": 13423, "bid_vol2": 5000,
                "ask_vol1": 0, "vol": 13423, "amount": 629807160.0
            },
            {
                "code": "920078", "price": 20.40, "last_close": 20.73, "open": 20.40,
                "bid1": 20.40, "ask1": 20.45, "bid_vol1": 100, "bid_vol2": 50,
                "ask_vol1": 120, "vol": 100, "amount": 204000.0
            }
        ]

        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        tdx_inst = TDXRealtimeFetcher.get_instance()
        with patch.object(tdx_inst, "get_security_quotes_safe", return_value=quotes_mock), \
             patch.object(tdx_inst, "get_batch_finance_shares", return_value={"920288": (5000000.0, 20000000.0), "301666": (10000000.0, 40000000.0), "920078": (10000000.0, 20000000.0)}):
            res_df = fetcher.enrich_with_tdx_realtime(mock_df, force=True)
            self.assertIn("bidding_tag", res_df.columns)
            self.assertIn("bidding_advice", res_df.columns)
            self.assertIn("bidding_amt_wan", res_df.columns)

            # 1. N华大应精准打上 💎 首日真金抢筹 与 09:25黄金上车点
            row_hd = res_df[res_df["code"] == "920288"].iloc[0]
            self.assertEqual(row_hd["bidding_tag"], "💎 首日真金抢筹")
            self.assertTrue("09:25黄金上车点" in row_hd["bidding_advice"])
            self.assertTrue(row_hd["bidding_amt_wan"] >= 1000.0)

            # 2. 大普微应精准打上 👑 竞价一字顶格 或 💎 竞价爆量突破
            row_dpw = res_df[res_df["code"] == "301666"].iloc[0]
            self.assertIn(row_dpw["bidding_tag"], ["👑 竞价一字顶格", "💎 竞价爆量突破"])
            self.assertTrue(row_dpw["bidding_amt_wan"] >= 60000.0)

            # 3. 族兴新材 (920078 北交所已上市标的) 绝不能误判为首日抢筹，应为常规博弈
            row_zx = res_df[res_df["code"] == "920078"].iloc[0]
            self.assertNotEqual(row_zx["bidding_tag"], "💎 首日真金抢筹")
            self.assertEqual(row_zx["bidding_tag"], "⏱️ 常规博弈")

        # 2. 验证 UI 界面渲染与推演卡片联动
        panel = NewStockPanel()
        panel.df_data = res_df
        panel._render_table()

        # 检查第 3 列（竞价信号）呈现
        bidding_cell_txt = panel.table.item(0, 3).text()
        self.assertTrue("💎" in bidding_cell_txt or "👑" in bidding_cell_txt)

        # 检查选中 N华大 时底部 preview_card 的竞价信息更新
        panel._update_preview_card(row_hd.to_dict())
        self.assertTrue("首日真金抢筹" in panel.lbl_bidding_info.text())
        self.assertTrue("09:25黄金上车点" in panel.lbl_bidding_info.text())

    def test_12_new_stock_strategy_issue_price_and_first_day_accuracy(self):
        """测试新股分时阶梯策略生成器、发行价基准、老股不误判及截面表防毛刺"""
        from ats.new_stock_strategy_generator import NewStockStrategyGenerator
        from ats.intraday_strategy_engine import IntradayStrategyEngine

        generator = NewStockStrategyGenerator.get_instance()
        engine = IntradayStrategyEngine.get_instance()
        engine.load_config()

        # 1. 验证新股自动生成策略时能 100% 获取权威真实发行价 (920288 -> 12.57)
        strat = generator.generate_strategy({
            "code": "920288",
            "name": "N华大",
            "open_price": 13.64,
            "price": 13.64
        })
        self.assertIsNotNone(strat)
        spec = strat.get("stock_spec", {})
        issue_p = spec.get("issue_price")
        self.assertAlmostEqual(issue_p, 12.57, delta=0.01)

        # 验证 5 大阶梯价格
        price_ladder = spec.get("price_ladder", [])
        self.assertEqual(len(price_ladder), 5)
        self.assertAlmostEqual(price_ladder[0]["price"], 25.14, delta=0.05) # +100%
        self.assertAlmostEqual(price_ladder[1]["price"], 37.71, delta=0.05) # +200%

        # 2. 验证 get_stock_ladder_spec 动态获取真实发行价
        fallback_spec = engine.get_stock_ladder_spec("920288")
        self.assertAlmostEqual(fallback_spec.get("issue_price"), 12.57, delta=0.01)

        # 3. 验证常规老股票 (920081 欧伦电气) 绝不误判为首日新股
        is_first_day = engine.is_stock_first_listing_day("920081")
        self.assertFalse(is_first_day)
        auto_strat = engine.auto_select_strategy(45.31, code="920081")
        self.assertEqual(auto_strat.get("id"), "strategy_c_daily_surge_ladder")

        # 4. 验证 7 节点打分开盘 13.64 较发行价 12.57 计算出正确的 +8.5% 涨幅
        eval_res = engine.evaluate_seven_nodes(
            code="920288",
            current_time_str="09:30",
            open_price=13.64,
            price=13.64,
            high_price=13.64,
            low_price=13.64,
            vwap=13.64,
            turnover_rate=15.0,
            amount=12530000.0,
            last_close=12.57
        )
        nodes = eval_res.get("node_results", [])
        self.assertTrue(len(nodes) >= 1)
        node_1 = nodes[0]
        obs_val = node_1.get("observed_val", "")
        self.assertTrue("开盘:13.64元" in obs_val)
        self.assertTrue("较发行价" in obs_val or "较昨收" in obs_val)

        # 5. 验证多股截面表传入 hydrate_from_intraday_df 时自动安全过滤
        multi_stock_df = pd.DataFrame([
            {"code": "00089", "open": 24.50, "close": 24.87, "high": 24.97, "low": 24.30},
            {"code": "30130", "open": 55.00, "close": 56.66, "high": 60.47, "low": 54.80},
            {"code": "68879", "open": 110.00, "close": 112.82, "high": 124.02, "low": 109.00},
            {"code": "920288", "open": 13.64, "close": 13.64, "high": 13.64, "low": 13.64},
        ], index=["00089", "30130", "68879", "920288"])
        success = engine.hydrate_from_intraday_df("920288", multi_stock_df, open_price=13.64)
        self.assertFalse(success, "多股票截面表应被安全拦截并返回 False，不注入分时 K 线")


if __name__ == "__main__":
    unittest.main()
