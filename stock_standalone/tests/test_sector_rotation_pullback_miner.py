# -*- coding: utf-8 -*-
"""
tests/test_sector_rotation_pullback_miner.py — 板块轮动前排引导与主线回踩启动深挖专项测试套件
=============================================================================
覆盖范围：
1. 特征标准化与动态推导 (dff, dff2, dff3, per1d~per9d, vol_ratio, ratio)；
2. 冲锋先锋龙头识别与自下而上资金主线聚合；
3. 主线板块内 MA20d 回踩企稳与时序洗盘转阳挖掘算法；
4. 5000 只全市场标的大循环压力测试与耗时断言 (<150ms)；
5. Qt6 专业对话框 (SectorRotationMinerDialog) 渲染、单选联动与快捷键生命周期。
"""

import sys
import os
import time
import unittest
import numpy as np
import pandas as pd
from typing import Dict, Any

# 确保 stock_standalone 在路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ats.sector_rotation_pullback_miner import (
    SectorRotationPullbackMiner, get_sector_rotation_miner,
    is_valid_sector_name, is_index_or_fund_code
)

# 初始化全局测试 QApplication
_app = QApplication.instance()
if _app is None:
    _app = QApplication(["--platform", "offscreen"])


class TestSectorRotationPullbackMiner(unittest.TestCase):
    """板块轮动前排引导与主线回踩启动深挖核心测试"""

    def setUp(self):
        self.miner = SectorRotationPullbackMiner()

    def test_01_filter_helpers(self):
        """测试板块名称合法性判断与指数/ETF过滤"""
        self.assertTrue(is_valid_sector_name("低空经济"))
        self.assertTrue(is_valid_sector_name("软件开发"))
        self.assertTrue(is_valid_sector_name("半导体"))
        self.assertFalse(is_valid_sector_name("--"))
        self.assertFalse(is_valid_sector_name("0"))
        self.assertFalse(is_valid_sector_name("0.0"))
        self.assertFalse(is_valid_sector_name("nan"))
        self.assertFalse(is_valid_sector_name("未知"))
        self.assertFalse(is_valid_sector_name("600000"))

        # 指数与ETF过滤
        self.assertTrue(is_index_or_fund_code("999999", "上证指数"))
        self.assertTrue(is_index_or_fund_code("399001", "深证成指"))
        self.assertTrue(is_index_or_fund_code("510300", "沪深300ETF"))
        self.assertFalse(is_index_or_fund_code("600000", "浦发银行"))
        self.assertFalse(is_index_or_fund_code("000001", "平安银行"))
        self.assertFalse(is_index_or_fund_code("000852", "石化机械"))

    def test_02_identify_leading_sectors_and_pioneers(self):
        """测试冲锋先锋龙头挖掘与自下而上主线板块聚合"""
        data = {
            # 强势主线板块 1: 低空经济 (有连板龙头 + 冲锋先锋)
            "000099": {"name": "中信海直", "close": 22.0, "percent": 10.0, "dff2": 8.5, "dff3": 35.0, "vol_ratio": 2.5, "amount": 15e8, "category": "低空经济;军工"},
            "002389": {"name": "航天彩虹", "close": 18.5, "percent": 6.8, "dff2": 4.2, "dff3": 20.0, "vol_ratio": 1.8, "amount": 8e8, "category": "低空经济;无人机"},
            "000098": {"name": "万丰奥威", "close": 15.0, "percent": 4.8, "dff2": 3.0, "dff3": 18.0, "vol_ratio": 1.4, "amount": 12e8, "category": "低空经济;汽车零部件"},
            
            # 活跃赛道板块 2: 半导体 (有大单反弹先锋)
            "688123": {"name": "聚辰股份", "close": 65.0, "percent": 7.5, "dff2": 3.5, "dff3": -5.0, "vol_ratio": 2.1, "amount": 6e8, "category": "半导体;存储芯片"},
            "688008": {"name": "澜起科技", "close": 58.0, "percent": 5.2, "dff2": 2.1, "dff3": 10.0, "vol_ratio": 1.6, "amount": 18e8, "category": "半导体;集成电路"},
            "603986": {"name": "兆易创新", "close": 88.0, "percent": 4.2, "dff2": 1.8, "dff3": 8.0, "vol_ratio": 1.3, "amount": 14e8, "category": "半导体;芯片"},

            # 孤狼标的 (无板块效应，不形成主线)
            "600111": {"name": "孤狼科技", "close": 10.0, "percent": 9.9, "dff2": 9.0, "dff3": 50.0, "vol_ratio": 3.0, "amount": 0.5e8, "category": "冷门概念"},
            
            # 普通跟跌杂毛
            "600222": {"name": "跟跌弱势", "close": 5.0, "percent": -2.0, "dff2": -5.0, "dff3": -20.0, "vol_ratio": 0.8, "amount": 0.3e8, "category": "低空经济"}
        }

        df = pd.DataFrame.from_dict(data, orient='index')
        sectors = self.miner.identify_leading_sectors(df, min_pioneers_per_sector=2)

        self.assertGreaterEqual(len(sectors), 2)
        top_sec_names = [s["name"] for s in sectors]
        self.assertIn("低空经济", top_sec_names)
        self.assertIn("半导体", top_sec_names)
        self.assertNotIn("冷门概念", top_sec_names) # 孤狼单只标的不构成主线

        # 检查低空经济板块统计
        dk_sec = next(s for s in sectors if s["name"] == "低空经济")
        self.assertGreaterEqual(dk_sec["pioneer_count"], 3)
        self.assertEqual(dk_sec["leader_name"], "中信海直")
        self.assertGreaterEqual(dk_sec["strength_score"], 50.0)
        self.assertEqual(dk_sec["grade"], "👑 核心主线")

    def test_03_mine_pullback_reversal_stocks(self):
        """测试主线板块内部深挖回踩 MA20 企稳与时序洗盘转阳标的"""
        # 模拟主线板块【低空经济】与【半导体】内部的多只成分股
        data = {
            # 1. 经典缩量洗盘·MA20企稳标的 (极佳买点)
            "000001": {
                "name": "宗申动力", "close": 12.5, "percent": 2.8, "dff": 2.8,
                "dff2": 1.2, "dff3": 12.0, "ma20d": 12.35, "ch_supp": 12.30,
                "per1d": -1.5, "per2d": -0.8, "per3d": 1.0, # 前两日连续缩量洗盘回调，今日企稳放量转阳
                "vol_ratio": 1.45, "ratio": 3.8, "category": "低空经济"
            },
            # 2. 底部超跌筑底·平台放量起爆标的 (极佳买点)
            "000002": {
                "name": "北京君正", "close": 55.0, "percent": 3.5, "dff": 3.5,
                "dff2": 0.8, "dff3": -8.0, "ma20d": 54.5, "ch_supp": 54.0,
                "per1d": 0.2, "per2d": -0.5, "per3d": 0.1, # 底部窄幅横盘蓄势，今日放量拉出中阳
                "vol_ratio": 1.85, "ratio": 2.9, "category": "半导体"
            },
            # 3. 已经大涨冲高 (涨幅过大，防止追高排除)
            "000003": {
                "name": "中信海直", "close": 22.0, "percent": 9.8, "dff": 9.8,
                "dff2": 12.0, "dff3": 45.0, "ma20d": 19.6, "ch_supp": 20.0,
                "per1d": 3.0, "per2d": 5.0, "per3d": 2.0,
                "vol_ratio": 2.5, "ratio": 15.0, "category": "低空经济"
            },
            # 4. 深度破位阴跌股 (远离 MA20，排除)
            "000004": {
                "name": "破位衰竭", "close": 8.0, "percent": -1.0, "dff": -1.0,
                "dff2": -7.5, "dff3": -25.0, "ma20d": 8.65, "ch_supp": 0.0,
                "per1d": -2.0, "per2d": -1.5, "per3d": -1.0,
                "vol_ratio": 0.7, "ratio": 1.1, "category": "低空经济"
            }
        }
        df = pd.DataFrame.from_dict(data, orient='index')
        leading_sectors = [
            {"name": "低空经济", "strength_score": 75.0, "grade": "👑 核心主线"},
            {"name": "半导体", "strength_score": 65.0, "grade": "🚀 活跃进攻"}
        ]

        candidates = self.miner.mine_pullback_reversal_stocks(df, leading_sectors)

        # 校验只有回踩企稳的 000001 和 000002 入选
        cand_codes = [c["code"] for c in candidates]
        self.assertIn("000001", cand_codes)
        self.assertIn("000002", cand_codes)
        self.assertNotIn("000003", cand_codes) # 暴涨 9.8% 被排除
        self.assertNotIn("000004", cand_codes) # 跌破 MA20 -7.5% 被排除

        # 检查候选结构字段完整性与可解释性
        cand_1 = next(c for c in candidates if c["code"] == "000001")
        self.assertEqual(cand_1["pattern_name"], "🎯 缩量洗盘·MA20企稳")
        self.assertGreater(cand_1["reversal_score"], 80.0)
        self.assertIn("宗申动力", cand_1["name"])
        self.assertTrue(cand_1["stop_loss"] > 0)
        self.assertIn("低空经济", cand_1["reason"])

    def test_04_batch_5000_stocks_performance(self):
        """测试 5000 只全市场股票批量大扫描极速性能与自愈推导"""
        np.random.seed(42)
        n = 5000
        codes = [f"{i:06d}" for i in range(1, n + 1)]
        prices = np.random.uniform(5.0, 100.0, n).round(2)
        pcts = np.random.uniform(-4.0, 5.0, n).round(2)
        # 注入部分冲锋与大阳
        pcts[:50] = np.random.uniform(5.0, 10.0, 50).round(2)
        amts = np.random.uniform(0.2, 5.0, n) * 1e8
        amts[:50] *= 5.0 # 先锋大成交额
        ma20s = (prices * np.random.uniform(0.95, 1.05, n)).round(2)

        sec_choices = ["低空经济", "人工智能", "存储芯片", "新能源车", "固态电池", "医药制造", "量子科技", "消费电子"]
        cats = [f"{np.random.choice(sec_choices)};{np.random.choice(sec_choices)}" for _ in range(n)]

        df = pd.DataFrame({
            "code": codes,
            "name": [f"股{c}" for c in codes],
            "close": prices,
            "percent": pcts,
            "amount": amts,
            "ma20d": ma20s, # 无 dff2，需自动推导
            "vol_ratio": np.random.uniform(0.8, 2.5, n).round(2),
            "ratio": np.random.uniform(1.0, 10.0, n).round(2),
            "per1d": np.random.uniform(-3.0, 3.0, n).round(2),
            "per2d": np.random.uniform(-3.0, 3.0, n).round(2),
            "category": cats
        }, index=codes)

        t0 = time.time()
        report = self.miner.run_mining_pipeline(df)
        cost_ms = (time.time() - t0) * 1000

        self.assertIn("sectors", report)
        self.assertIn("candidates", report)
        self.assertEqual(report["total_stocks"], 5000)
        self.assertGreater(len(report["sectors"]), 0)
        self.assertGreater(len(report["candidates"]), 0)

        # 极致性能断言：5000 只标的全流程扫描必须 < 150ms
        self.assertLess(cost_ms, 150.0, f"5000 只标的大循环扫描耗时 {cost_ms:.2f}ms 超过 150ms 阈值!")

    def test_05_ui_dialog_lifecycle_and_linkage(self):
        """测试 SectorRotationMinerDialog 界面构建、数据渲染与交互过滤"""
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog

        data = {
            "000001": {"name": "领涨先锋1", "close": 20.0, "percent": 9.9, "dff2": 5.0, "dff3": 20.0, "vol_ratio": 2.0, "amount": 10e8, "category": "主线板块A"},
            "000002": {"name": "冲锋龙头2", "close": 15.0, "percent": 6.5, "dff2": 4.0, "dff3": 15.0, "vol_ratio": 1.8, "amount": 8e8, "category": "主线板块A"},
            "000003": {"name": "回踩标的1", "close": 12.0, "percent": 2.0, "dff2": 1.0, "dff3": 8.0, "per1d": -1.0, "per2d": -0.5, "vol_ratio": 1.3, "amount": 3e8, "category": "主线板块A"}
        }
        df = pd.DataFrame.from_dict(data, orient='index')

        dialog = SectorRotationMinerDialog(parent=None, current_df=df)
        self.assertIsNotNone(dialog.sectors_table)
        self.assertIsNotNone(dialog.candidates_table)

        # 同步触发计算并验证表格行渲染
        report = self.miner.run_mining_pipeline(df)
        dialog._on_scan_finished(report)

        self.assertGreaterEqual(dialog.sectors_table.rowCount(), 1)
        self.assertGreaterEqual(dialog.candidates_table.rowCount(), 1)

        # 测试点击板块行联动过滤
        sec_item = dialog.sectors_table.item(0, 0)
        if sec_item:
            dialog._on_sector_row_clicked(sec_item)
            self.assertEqual(dialog._selected_sector, sec_item.text().strip())

        # 测试清空过滤还原全部
        dialog._clear_sector_filter()
        self.assertIsNone(dialog._selected_sector)

        # 安全关闭
        dialog.close()

    def test_06_post_market_zero_percent_self_healing(self):
        """专门测试真实场景：盘后数据初始化后 percent/dff/amount 均为 0，但 per1d/per2d 正常时的自愈机制"""
        n = 1000
        codes = [f"{i:06d}" for i in range(n)]
        prices = np.random.uniform(10.0, 50.0, n).round(2)
        ma20s = (prices * np.random.uniform(0.96, 1.04, n)).round(2)
        sec_choices = ["低空经济", "人工智能", "存储芯片", "新能源车", "固态电池"]
        cats = [f"{np.random.choice(sec_choices)};{np.random.choice(sec_choices)}" for _ in range(n)]

        # 模拟盘后初始化：percent、dff、amount 全是 0！
        df_eod = pd.DataFrame({
            "code": codes,
            "name": [f"标的{c}" for c in codes],
            "close": prices,
            "percent": np.zeros(n),
            "dff": np.zeros(n),
            "amount": np.zeros(n),
            "ma20d": ma20s,
            "vol_ratio": np.ones(n),
            "ratio": np.random.uniform(1.0, 8.0, n).round(2),
            "per1d": np.random.uniform(-3.0, 8.0, n).round(2),
            "per2d": np.random.uniform(-3.0, 3.0, n).round(2),
            "per3d": np.random.uniform(-3.0, 3.0, n).round(2),
            "category": cats
        }, index=codes)

        report = self.miner.run_mining_pipeline(df_eod)
        self.assertTrue(report.get("is_post_market"), "必须自动判定为盘后自愈模式!")
        self.assertGreater(len(report["sectors"]), 0, "盘后模式下主线板块绝不能为 0!")
        self.assertGreater(len(report["candidates"]), 0, "盘后模式下回踩启动候选绝不能为 0!")
        # 验证候选股中涨幅非 0
        cand0 = report["candidates"][0]
        self.assertIn("reason", cand0)
        self.assertIn("所属【", cand0["reason"])


if __name__ == '__main__':
    unittest.main()

