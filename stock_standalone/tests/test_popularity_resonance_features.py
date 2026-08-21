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


if __name__ == '__main__':
    unittest.main()
