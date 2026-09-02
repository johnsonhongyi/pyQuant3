import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tkinter as tk
from tkinter import ttk
import pandas as pd
from popularity_resonance_gui import PRServiceGUI


class TestPopularityResonanceFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = PRServiceGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_tree_scroll_to_code_cross_views(self):
        """测试点击 code 时在主界面所有包含该 code 的视图中自动高亮滚动定位"""
        app = self.app
        # 清空
        app.clear_all_trees()

        # 在东表插入 300839 和 000001
        app.tree_em.insert("", "end", values=(1, "300839", "博汇科技", "20.02", "12.47", "20.7", "27.2", "60"))
        app.tree_em.insert("", "end", values=(2, "000001", "平安银行", "1.00", "10.00", "1.0", "1.0", "100"))

        # 在合表插入 600353 和 300839
        app.tree_res.insert("", "end", values=(1, "600353", "旭光电子", "10.00", "38.28", "67.9", "153.7", "67"))
        app.tree_res.insert("", "end", values=(2, "300839", "博汇科技", "20.02", "12.47", "20.7", "27.2", "60"))

        # 在花表插入 603083（没有 300839）
        app.tree_ths.insert("", "end", values=(1, "603083", "剑桥科技", "1.05", "180.97", "9.6", "53.0", "432"))

        # 调用 tree_scroll_to_code 定位 300839
        res = app.tree_scroll_to_code("300839", vis=False)
        self.assertTrue(res, "tree_scroll_to_code 应返回 True")

        # 验证东表中选中的项是否为 300839
        sel_em = app.tree_em.selection()
        self.assertTrue(len(sel_em) > 0, "东表应有选中项")
        em_code = app.tree_em.item(sel_em[0], "values")[1]
        self.assertEqual(em_code, "300839", "东表应选中 300839")

        # 验证合表中选中的项是否为 300839
        sel_res = app.tree_res.selection()
        self.assertTrue(len(sel_res) > 0, "合表应有选中项")
        res_code = app.tree_res.item(sel_res[0], "values")[1]
        self.assertEqual(res_code, "300839", "合表应选中 300839")

        # 验证花表（没有 300839）保持原样
        self.assertEqual(len(app.tree_ths.get_children()), 1)

    def test_concept_ranking_and_stock_sources(self):
        """测试板块热点聚合、得分计算与个股信息完整性"""
        app = self.app

        # 构造模拟的人气强势股数据
        all_stocks = {
            "300016": {
                "name": "北陆药业",
                "percent": 20.00,
                "category": "阿尔茨海默概念;创新药;猴痘概念",
                "close": 10.44,
                "ma5d": 10.0,
                "ma20d": 9.0,
                "ma60d": 8.0,  # is_bullish = True
                "rank": 17
            },
            "688185": {
                "name": "康希诺",
                "percent": 20.01,
                "category": "猴痘概念;疫苗;生物医药",
                "close": 77.32,
                "ma5d": 75.0,
                "ma20d": 70.0,
                "ma60d": 65.0,  # is_bullish = True
                "rank": 6
            },
            "600353": {
                "name": "旭光电子",
                "percent": 10.00,
                "category": "光刻机;半导体",
                "close": 38.28,
                "ma5d": 35.0,
                "ma20d": 32.0,
                "ma60d": 30.0,  # is_bullish = True
                "rank": 67
            },
            "002412": {
                "name": "汉森制药",
                "percent": 10.04,
                "category": "幽门螺杆菌概念;中药",
                "close": 10.19,
                "ma5d": 10.0,
                "ma20d": 9.5,
                "ma60d": 9.0,
                "rank": 3
            },
            "002903": {
                "name": "宇环数控",
                "percent": 10.01,
                "category": "光刻机;机器人概念",
                "close": 33.74,
                "ma5d": 30.0,
                "ma20d": 28.0,
                "ma60d": 25.0,
                "rank": 61
            }
        }

        # 增加一个多股票板块“黄金概念”（4只股票，平均涨幅+6%）
        all_stocks.update({
            "600547": {"name": "山东黄金", "percent": 5.5, "category": "黄金概念;贵金属", "close": 30.0, "ma5d": 30.0, "ma20d": 28.0, "ma60d": 25.0, "rank": 10},
            "601899": {"name": "紫金矿业", "percent": 6.2, "category": "黄金概念;有色金属", "close": 18.0, "ma5d": 17.5, "ma20d": 16.0, "ma60d": 15.0, "rank": 12},
            "000603": {"name": "盛达资源", "percent": 7.0, "category": "黄金概念;贵金属", "close": 15.0, "ma5d": 14.5, "ma20d": 13.0, "ma60d": 12.0, "rank": 18},
            "600988": {"name": "赤峰黄金", "percent": 6.8, "category": "黄金概念;贵金属", "close": 20.0, "ma5d": 19.0, "ma20d": 18.0, "ma60d": 16.0, "rank": 20},
        })

        app.update_concept_ranking(all_stocks)

        # 检查是否生成了 top5 概念
        self.assertTrue(len(app._last_categories) > 0, "应生成热门概念")
        # 验证异动个股最多的板块“黄金概念”（4只）因为群聚效应排名最前
        self.assertEqual(app._last_categories[0], "黄金概念", "4只股票异动的黄金概念应排在首位")
        self.assertIn("光刻机", app._last_categories, "光刻机板块应在前列 (旭光电子+宇环数控)")

        # 检查黄金概念下的个股
        gold_stocks = app._last_cat_dict.get("黄金概念", [])
        self.assertEqual(len(gold_stocks), 4, "黄金概念下应有 4 只股票")
        gold_names = [s[1] for s in gold_stocks]
        self.assertIn("山东黄金", gold_names)
        self.assertIn("紫金矿业", gold_names)
        self.assertIn("盛达资源", gold_names)
        self.assertIn("赤峰黄金", gold_names)

    def test_dynamic_feature_engine_time_slices_and_entry_points(self):
        """测试 DynamicFeatureEngine 在不同交易时钟下的三大黄金挂单点推演"""
        from popularity_resonance_service import DynamicFeatureEngine
        engine = DynamicFeatureEngine()

        # 1. 竞价期 (09:25) - 具备真金买压 (买压85%, 竞价2500万) 推演【买点 A: 09:25 竞价顶格挂单】
        plan_auction = engine.infer_actionable_entry_points(
            code="000017",
            price=11.45,
            stock_pct=9.99,
            last_close=10.41,
            bidding_amt_wan=2500.0,
            seal_circ_ratio=5.2,
            bid_pressure=85.0,
            now_time_str="09:25:30"
        )
        self.assertEqual(plan_auction["action_code"], "BUY_AUCTION")
        self.assertIn("09:25 竞价", plan_auction["action_type"])
        self.assertEqual(plan_auction["suggested_price"], 11.45)

        # 2. 开盘定龙期 (09:30:20) - 极速冲板 推演【买点 B: 涨停前秒级抢排】
        plan_open_burst = engine.infer_actionable_entry_points(
            code="002084",
            price=5.80,
            stock_pct=10.06,
            last_close=5.27,
            bid_pressure=90.0,
            now_time_str="09:30:20"
        )
        self.assertEqual(plan_open_burst["action_code"], "BUY_MOMENTUM")
        self.assertIn("秒级抢排", plan_open_burst["action_type"])

        # 3. 盘中与分歧期 (10:15:00) - VWAP 均线支撑 推演【买点 C: 分歧低吸/反包】
        plan_pullback = engine.infer_actionable_entry_points(
            code="600540",
            price=5.05,
            stock_pct=4.5,
            last_close=4.83,
            vwap=4.98,
            now_time_str="10:15:00"
        )
        self.assertEqual(plan_pullback["action_code"], "BUY_PULLBACK")
        self.assertEqual(plan_pullback["suggested_price"], 4.98)

    def test_counter_market_divergence_and_pioneer_dragon(self):
        """测试大盘连续下跌/缩量冰点期，个股逆势高开与突发催化的【冰点逆势破局龙】感知"""
        from popularity_resonance_service import DynamicFeatureEngine
        engine = DynamicFeatureEngine()

        # 场景 1: 大盘连跌弱势 (index_pct = -0.8%)，深中华A 逆势高开冲高 +9.99%，竞价真金 2000 万
        res_counter = engine.evaluate_counter_market_divergence(
            stock_pct=9.99,
            index_pct=-0.8,
            bidding_amt_wan=2000.0,
            seal_circ_ratio=4.5
        )
        self.assertTrue(res_counter["is_counter_market"], "大盘弱势时逆势大涨应判定为破局龙")
        self.assertEqual(res_counter["rs_divergence"], 10.79)
        self.assertIn("💎 逆势冰点破局龙", res_counter["pioneer_tag"])

        # 场景 2: 大盘下跌 (-0.5%)，个股同步下跌 (-1.2%)
        res_sync = engine.evaluate_counter_market_divergence(
            stock_pct=-1.2,
            index_pct=-0.5
        )
        self.assertFalse(res_sync["is_counter_market"], "同步下跌不属于逆势破局")
        self.assertIn("⏱️ 同步大盘博弈", res_sync["pioneer_tag"])

    def test_three_dimensional_resonance_scoring_and_enrichment(self):
        """测试三位一体综合评分模型：全网热度 + TDX 盘口真金 + 分段涨速 + VWAP偏离度 + 诱多惩罚"""
        from popularity_resonance_service import calculate_resonance_scores

        em_mock = {"002084": 1, "000017": 2, "000001": 50, "999999": 3}
        ths_mock = {"002084": 1, "000017": 3, "999999": 4}
        tgb_mock = {"002084": 1, "000017": 2}
        lh_mock = {"002084": 1}

        # 运行三位一体共振评分 (在大盘弱势 index_pct = -0.6% 环境下，指定 60m 分段模式)
        results = calculate_resonance_scores(em_mock, ths_mock, tgb_mock, lh_mock, index_pct=-0.6, segment_mode="60m")
        self.assertTrue(len(results) > 0)

        # 验证 Top 标的属性完整性（包含 ATS 同源的分段涨速与日内 VWAP 偏离度）
        top1 = results[0]
        self.assertIn("velocity_pct", top1)
        self.assertIn("velocity_tag", top1)
        self.assertIn("vwap", top1)
        self.assertIn("vwap_dev_pct", top1)
        self.assertGreater(top1["score"], 300, "多平台共振+盘口加成得分应显著高于基础分")

    def test_quick_order_executor(self):
        """测试一键直连交易终端与预埋单执行器 (QuickOrderExecutor)"""
        from popularity_resonance_service import QuickOrderExecutor
        executor = QuickOrderExecutor.get_instance()

        res = executor.execute_quick_buy(
            code="000017",
            name="深中华A",
            target_price=11.45,
            shares=1000,
            strategy_tag="💎 逆势冰点破局·09:25竞价挂单"
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["code"], "000017")
        self.assertEqual(res["target_price"], 11.45)
        self.assertIn("深中华A", res["msg"])

    def test_trade_automation_engine_and_self_check(self):
        """测试 TradeAutomationEngine 的自测自检与闪电下单参数装载能力"""
        from JohnsonUtil.trade_automation import TradeAutomationEngine
        engine = TradeAutomationEngine.get_instance()

        # 1. 自测自检环境探测
        env_status = engine.check_trade_environment()
        self.assertIn("tdx_running", env_status)
        self.assertIn("ready", env_status)

        # 2. 执行闪电挂单参数组装与下单调用
        res = engine.execute_lightning_order(
            code="002907",
            name="华森制药",
            target_price=15.74,
            shares=1000,
            strategy_tag="👑 天梯连板·🔥 强势主升首板"
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["code"], "002907")
        self.assertEqual(res["price"], 15.74)
        self.assertEqual(res["shares"], 1000)

    def test_limit_up_engine_popularity_resonance_injection(self):
        """测试天梯引擎反向识别全网热搜与逆势破局龙标签"""
        from ats.limit_up_engine import LimitUpEngine
        engine = LimitUpEngine.get_instance()

        df_mock = pd.DataFrame([
            {"code": "000017", "name": "深中华A", "trade": 11.45, "percent": 9.99, "last_close": 10.41, "bid1": 11.45, "buy": 11.45},
            {"code": "002084", "name": "海鸥住工", "trade": 5.80, "percent": 10.05, "last_close": 5.27, "bid1": 5.80, "buy": 5.80}
        ]).set_index("code")

        records = engine.scan_limit_up_records_from_df(df_mock, fetch_l2_quotes=False)
        self.assertTrue(len(records) >= 2)
        r0 = records[0]
        self.assertIn("momentum_score", r0)
        self.assertIn("pattern_desc", r0)

    def test_popularity_gui_10_columns_structure_and_segment_mode(self):
        """测试人气共振 GUI 的 10 列基础决策列定义 (含 velocity 与 vwap_dev，彻底剔除无意义4列) 与分段切换"""
        from popularity_resonance_gui import PRServiceGUI
        cols = PRServiceGUI._BASE_FIXED_COLS
        self.assertEqual(len(cols), 10)
        self.assertIn("velocity", cols)
        self.assertIn("vwap_dev", cols)
        # 确保旧的 4 列已被彻底移除
        self.assertNotIn("ladder", cols)
        self.assertNotIn("bid_p", cols)
        self.assertNotIn("pioneer", cols)
        self.assertNotIn("decision", cols)

        # 验证默认列宽配置与居中方法
        widths = PRServiceGUI.DEFAULT_COLUMN_WIDTHS
        self.assertIn("velocity", widths)
        self.assertIn("vwap_dev", widths)
        self.assertTrue(widths["velocity"] >= 55)
        self.assertTrue(widths["vwap_dev"] >= 55)
        self.assertTrue(hasattr(PRServiceGUI, "reset_sash_center"))

        # 测试分段模式切换与表头动态文案
        app = self.app
        app.segment_mode = "60m"
        self.assertEqual(app._get_velocity_header_text(), "60分涨速%")
        app.segment_mode = "30m"
        self.assertEqual(app._get_velocity_header_text(), "30分涨速%")
        app.segment_mode = "15m"
        self.assertEqual(app._get_velocity_header_text(), "15分涨速%")
        app.segment_mode = "day_open"
        self.assertEqual(app._get_velocity_header_text(), "开盘涨速%")
        app.segment_mode = "60s"
        self.assertEqual(app._get_velocity_header_text(), "60秒涨速%")
    def test_trade_flow_table_real_trade_logs(self):
        """测试 TradeFlowTable 能正确加载 TradeGateway 与 SQLite 中的真实交易流水"""
        from PyQt6.QtWidgets import QApplication
        _ = QApplication.instance() or QApplication([])

        from ats.ui.trade_flow import TradeFlowTable, TradeFlowDialog
        from trade_gateway import TradeGateway
        from popularity_resonance_service import QuickOrderExecutor

        # 触发一次模拟/实盘一键挂单
        executor = QuickOrderExecutor.get_instance()
        res = executor.execute_quick_buy(
            code="300142",
            name="沃森生物",
            target_price=14.28,
            shares=1000,
            strategy_tag="👑 空间真龙·一键抢单"
        )
        self.assertTrue(res["ok"])

        # 初始化 TradeFlowTable 并加载流水
        table_widget = TradeFlowTable()
        table_widget.load_real_trades()
        self.assertTrue(len(table_widget._all_flow_list) >= 1)
        
        # 验证最新一条流水包含 300142 沃森生物
        found = any("300142" in row[1] and "沃森生物" in row[2] for row in table_widget._all_flow_list)
        self.assertTrue(found)

        # 测试表头点击排序 (例如点击第4列成交价排序、第6列成交金额排序)
        table_widget._on_header_clicked(4) # 点击成交价
        self.assertEqual(table_widget._sort_col, 4)
        prices = [float(r[4]) for r in table_widget._all_flow_list]
        self.assertEqual(prices, sorted(prices, reverse=True))

        table_widget._on_header_clicked(4) # 再次点击升序
        prices_asc = [float(r[4]) for r in table_widget._all_flow_list]
        self.assertEqual(prices_asc, sorted(prices_asc, reverse=False))

        # 测试点击联动与键盘上下键联动防抖
        clicked_stocks = []
        table_widget.stock_clicked.connect(lambda c, n: clicked_stocks.append((c, n)))
        table_widget._on_cell_clicked(0, 1)
        self.assertTrue(len(clicked_stocks) >= 1)

        # 测试上下键 currentCellChanged 防抖触发
        table_widget._on_current_cell_changed(0, 1, -1, -1)
        self.assertIsNotNone(table_widget._pending_link)

    def test_trade_flow_dialog_structure(self):
        """测试 TradeFlowDialog 独立弹窗组件初始化、持久化与刷新接口"""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        _ = QApplication.instance() or QApplication([])

        from ats.ui.trade_flow import TradeFlowDialog
        dlg = TradeFlowDialog()
        self.assertIsNotNone(dlg.flow_table)
        dlg.refresh_data()
        self.assertIn("ATS 今日交易流水日志", dlg.windowTitle())

        # 验证独立窗口属性 (独立顶层窗口，带关闭与最小最大化按钮)
        flags = dlg.windowFlags()
        self.assertTrue(bool(flags & Qt.WindowType.Window))

        # 验证位置保存与恢复
        dlg._save_geometry()
        dlg._restore_geometry()


if __name__ == '__main__':
    unittest.main()

