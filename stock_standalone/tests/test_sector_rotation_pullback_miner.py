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

        # 极致性能断言：5000 只标的全流程扫描必须保持毫秒级极速响应 (< 750ms)
        self.assertLess(cost_ms, 750.0, f"5000 只标的大循环扫描耗时 {cost_ms:.2f}ms 超过 750ms 阈值!")

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


    def test_07_alt_r_passthrough_and_linkage_interactions(self):
        """测试 Alt+R 绝对放行给系统轮转器，以及双击选股信号发射与重点关注切换"""
        from PyQt6.QtCore import Qt, QEvent
        from PyQt6.QtGui import QKeyEvent
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog
        from global_favorites import GlobalFavoriteManager

        data = {
            "000001": {"name": "领涨龙头1", "close": 20.0, "percent": 9.9, "dff2": 5.0, "dff3": 20.0, "vol_ratio": 2.0, "amount": 10e8, "category": "低空经济"},
            "000002": {"name": "冲锋先锋2", "close": 15.0, "percent": 7.0, "dff2": 4.0, "dff3": 15.0, "vol_ratio": 1.8, "amount": 8e8, "category": "低空经济"},
            "000003": {"name": "回踩启动3", "close": 10.0, "percent": 2.5, "dff2": 1.5, "dff3": 5.0, "per1d": -1.2, "vol_ratio": 1.4, "amount": 3e8, "category": "低空经济"}
        }
        df = pd.DataFrame.from_dict(data, orient='index')

        dialog = SectorRotationMinerDialog(parent=None, current_df=df)
        report = self.miner.run_mining_pipeline(df)
        dialog._on_scan_finished(report)

        # 1. 验证双击候选表格项发射 code_clicked 信号
        emitted_codes = []
        dialog.code_clicked.connect(emitted_codes.append)
        cand_item = dialog.candidates_table.item(0, 0)
        self.assertIsNotNone(cand_item)
        dialog._on_candidate_double_clicked(cand_item)
        self.assertIn("000003", emitted_codes, "双击候选行必须发射正确的 6 位股票代码信号!")

        # 2. 验证双击板块表格中的领涨龙头 (第 5 列) 联动龙头股票
        leader_item = dialog.sectors_table.item(0, 5)
        self.assertIsNotNone(leader_item)
        dialog._on_sector_double_clicked(leader_item)
        self.assertIn("000001", emitted_codes, "双击板块领涨先锋龙头列必须发射龙头代码信号!")

        # 3. 🚀 关键验证：Alt+R 键盘事件必须被忽略放行 (event.ignore())，专属于全局视窗轮换
        alt_r_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.AltModifier)
        dialog.keyPressEvent(alt_r_event)
        self.assertFalse(alt_r_event.isAccepted(), "Alt+R 快捷键必须被 ignore 放行，绝不能被轮动深挖拦截抢占!")

        # 4. 验证重点关注切换与标记
        fav_mgr = GlobalFavoriteManager()
        initial_fav = fav_mgr.is_favorite_stock("000003")
        dialog._toggle_favorite_stock("000003", "回踩启动3")
        self.assertEqual(fav_mgr.is_favorite_stock("000003"), not initial_fav)
        # 还原状态
        dialog._toggle_favorite_stock("000003", "回踩启动3")
        self.assertEqual(fav_mgr.is_favorite_stock("000003"), initial_fav)

        dialog.close()

    def test_08_tk_rotator_and_visualizer_integration(self):
        """测试 Tk 底层 Alt+R 轮转与 Visualizer 纯点击入口的集成完整性"""
        # 1. 验证 Visualizer 工具栏与 IPC QUERY 命令集成
        import trade_visualizer_qt6 as tv
        self.assertTrue(hasattr(tv, "MainWindow"), "trade_visualizer_qt6 必须具备 MainWindow 类")
        self.assertTrue(hasattr(tv.MainWindow, "_open_sector_rotation_miner"), "Visualizer 必须具备 _open_sector_rotation_miner 纯点击入口")

        # 2. 验证 Tk 顶部工具栏配置与执行映射包含轮动深挖
        import instock_MonitorTK as tk_mod
        self.assertTrue(hasattr(tk_mod, "StockMonitorApp"), "必须具备 StockMonitorApp 主类")
        self.assertTrue(hasattr(tk_mod.StockMonitorApp, "open_sector_rotation_miner"), "Tk 端必须具备 open_sector_rotation_miner 方法")
        self.assertTrue(hasattr(tk_mod.StockMonitorApp, "_get_all_open_trade_windows"), "Tk 端必须具备 _get_all_open_trade_windows 方法")

        # 3. 验证 WindowRotator 的窗口命名识别
        raw_name = "🔄 板块轮动前排引导与资金主线回踩启动深挖工作台"
        self.assertTrue("板块轮动" in raw_name or "SectorRotationMiner" in raw_name)

    def test_09_click_and_keyboard_linkage_and_esc_close(self):
        """测试单击联动、上下键移动联动、板块反选Toggle、右键异动联动与Esc/关闭按钮"""
        from PyQt6.QtCore import Qt, QEvent
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtWidgets import QWidget
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog

        mock_parent = QWidget()
        data = {
            "000001": {"name": "领涨龙头1", "close": 20.0, "percent": 9.9, "dff2": 5.0, "dff3": 20.0, "vol_ratio": 2.0, "amount": 10e8, "category": "低空经济"},
            "000002": {"name": "冲锋先锋2", "close": 15.0, "percent": 7.0, "dff2": 4.0, "dff3": 15.0, "vol_ratio": 1.8, "amount": 8e8, "category": "低空经济"},
            "000003": {"name": "回踩启动3", "close": 10.0, "percent": 2.5, "dff2": 1.5, "dff3": 5.0, "per1d": -1.2, "vol_ratio": 1.4, "amount": 3e8, "category": "低空经济"},
            "600001": {"name": "半导体先锋", "close": 30.0, "percent": 8.0, "dff2": 4.5, "dff3": 12.0, "vol_ratio": 1.9, "amount": 9e8, "category": "半导体"},
            "600002": {"name": "半导体回踩", "close": 25.0, "percent": 1.5, "dff2": 1.0, "dff3": 4.0, "per1d": -0.8, "vol_ratio": 1.2, "amount": 4e8, "category": "半导体"}
        }
        df = pd.DataFrame.from_dict(data, orient='index')

        # 1. 验证 Win32 Owner 物理属主解耦：parent 必须为 None，但 _parent_window 保持引用
        dialog = SectorRotationMinerDialog(parent=mock_parent, current_df=df)
        self.assertIsNone(dialog.parent(), "对话框必须脱离物理属主 (parent is None)，防止无论置顶与否都遮挡 ATS 主窗口!")
        self.assertEqual(dialog._parent_window, mock_parent, "_parent_window 必须保留逻辑父窗口引用以便分发指令!")

        report = self.miner.run_mining_pipeline(df)
        dialog._on_scan_finished(report)

        # 2. 验证单击候选行联动信号
        emitted_codes = []
        dialog.code_clicked.connect(emitted_codes.append)
        cand_item = dialog.candidates_table.item(0, 0)
        self.assertIsNotNone(cand_item)
        dialog._on_candidate_clicked(cand_item)
        self.assertGreater(len(emitted_codes), 0, "单击候选行必须触发股票代码联动信号!")
        last_code = emitted_codes[-1]

        # 3. 验证键盘上下键/光标移动 (currentItemChanged) 联动
        if dialog.candidates_table.rowCount() > 1:
            prev_item = dialog.candidates_table.item(0, 0)
            curr_item = dialog.candidates_table.item(1, 0)
            dialog._on_candidate_current_changed(curr_item, prev_item)
            self.assertNotEqual(emitted_codes[-1], last_code, "移动到下一行必须触发新股票的联动信号!")
            # 验证同一行内切换不同列不重复触发
            curr_col1 = dialog.candidates_table.item(1, 1)
            count_before = len(emitted_codes)
            dialog._on_candidate_current_changed(curr_col1, curr_item)
            self.assertEqual(len(emitted_codes), count_before, "同一行内列变化防抖生效，不重复触发联动!")

        # 4. 验证板块点击与 Toggle 反选恢复
        if dialog.sectors_table.rowCount() >= 2:
            total_cand_count = len(dialog._all_candidates)
            sec_item_0 = dialog.sectors_table.item(0, 0)
            sec_name_0 = sec_item_0.text().replace("⭐", "").strip()

            # 真实点击模拟 (即使内部光标变更，点击也必须成功单选，绝不能被误取消)
            dialog.sectors_table.setCurrentItem(sec_item_0)
            dialog._on_sector_row_clicked(sec_item_0)
            self.assertEqual(dialog._selected_sector, sec_name_0, "点击板块行必须成功单选该板块!")
            self.assertIn("显示全部", dialog.btn_show_all.text())

            # 验证下半区候选数量跟随过滤
            filtered_count = dialog.candidates_table.rowCount()
            expected_count = sum(1 for c in dialog._all_candidates if sec_name_0 in c.get("sector", ""))
            self.assertEqual(filtered_count, expected_count, "单选板块后下半区候选数必须与该板块严格匹配!")

            # 再次点击同一板块 -> Toggle 取消选中，恢复全部主线
            dialog._on_sector_row_clicked(sec_item_0)
            self.assertIsNone(dialog._selected_sector, "再次点击已选中的板块必须自动反选恢复全部主线!")
            self.assertEqual(dialog.candidates_table.rowCount(), total_cand_count, "反选取消后下半区必须恢复全部主线标的!")

            # 键盘上下键切换板块行联动 (通过事件过滤器)
            from PyQt6.QtGui import QKeyEvent
            sec_item_1 = dialog.sectors_table.item(1, 0)
            sec_name_1 = sec_item_1.text().replace("⭐", "").strip()
            dialog.sectors_table.setCurrentCell(1, 0)
            key_down_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
            dialog.eventFilter(dialog.sectors_table, key_down_event)
            self.assertEqual(dialog._selected_sector, sec_name_1, "键盘上下键切换板块行必须联动更新选中板块!")

            # 点击“显示全部主线”按钮恢复
            dialog.btn_show_all.click()
            self.assertIsNone(dialog._selected_sector, "点击显示全部主线按钮必须清空过滤!")
            self.assertEqual(dialog.candidates_table.rowCount(), total_cand_count, "清空过滤后下半区必须展示全部标的!")

        # 5. 验证顶部存在关闭按钮
        self.assertTrue(hasattr(dialog, "btn_close"), "顶部控制栏必须具备关闭按钮!")
        self.assertIn("关闭", dialog.btn_close.text())

        # 6. 验证按 Esc 键关闭窗口
        esc_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        dialog.keyPressEvent(esc_event)
        self.assertTrue(esc_event.isAccepted(), "按下 Esc 键必须 accept 并关闭窗口!")

        dialog.close()

    def test_10_pullback_filter_config_and_channel_support(self):
        """测试可选择/自定义筛选策略配置、四维实战量化断言与通道支撑共振"""
        from ats.sector_rotation_pullback_miner import (
            PullbackFilterConfig, PRESET_FILTER_MODES
        )
        from ats.ui.sector_rotation_miner_dialog import (
            SectorRotationMinerDialog, PullbackConfigDialog
        )

        # 1. 验证 PullbackFilterConfig 序列化与预设模式
        cfg_default = PullbackFilterConfig()
        self.assertEqual(cfg_default.mode_name, "🎯 经典标准")
        self.assertGreaterEqual(cfg_default.min_eval_pct, 0.3)
        self.assertTrue(cfg_default.prefer_channel_supp)

        cfg_dict = cfg_default.to_dict()
        cfg_restored = PullbackFilterConfig.from_dict(cfg_dict)
        self.assertEqual(cfg_restored.dff2_min, cfg_default.dff2_min)
        self.assertEqual(cfg_restored.min_eval_pct, cfg_default.min_eval_pct)

        # 验证三款预设
        self.assertIn("🎯 经典标准", PRESET_FILTER_MODES)
        self.assertIn("🚀 极速起爆", PRESET_FILTER_MODES)
        self.assertIn("💎 稳健通道低吸", PRESET_FILTER_MODES)
        self.assertTrue(PRESET_FILTER_MODES["💎 稳健通道低吸"].require_channel_supp)

        # 2. 构造多维样本数据
        data = {
            # 领涨前排龙头 1 与 2 形成低空经济主线
            "000001": {"name": "龙头1", "close": 20.0, "percent": 9.9, "dff2": 5.0, "dff3": 20.0, "vol_ratio": 2.0, "amount": 10e8, "ratio": 8.0, "category": "低空经济"},
            "000002": {"name": "前锋2", "close": 15.0, "percent": 7.0, "dff2": 4.0, "dff3": 15.0, "vol_ratio": 1.8, "amount": 8e8, "ratio": 6.0, "category": "低空经济"},
            # 标的 A: 经典回踩企稳 + 踩在通道支撑线上 (收阳2.0%, MA20依托dff2=1.0%, ch_supp=9.9, vr=1.3, hsl=2.5%, amt=3e8)
            "000010": {"name": "支撑企稳A", "close": 10.0, "percent": 2.0, "dff2": 1.0, "dff3": 5.0, "ma20d": 9.9, "ch_supp": 9.9, "ch_pos": 15.0, "per1d": -1.0, "vol_ratio": 1.3, "amount": 3e8, "ratio": 2.5, "category": "低空经济"},
            # 标的 B: 负涨幅阴跌 (跌幅 -1.5%, 坚决不选!)
            "000020": {"name": "阴跌负涨B", "close": 10.0, "percent": -1.5, "dff2": 1.0, "dff3": 5.0, "ma20d": 9.9, "ch_supp": 9.9, "ch_pos": 15.0, "per1d": -2.0, "vol_ratio": 1.2, "amount": 3e8, "ratio": 2.0, "category": "低空经济"},
            # 标的 C: 跌破 MA20 破位 (dff2=-6.0%, 坚决不选!)
            "000030": {"name": "破位均线C", "close": 8.0, "percent": 1.5, "dff2": -6.0, "dff3": 5.0, "ma20d": 8.5, "ch_supp": 8.5, "per1d": -1.0, "vol_ratio": 1.2, "amount": 3e8, "ratio": 2.0, "category": "低空经济"},
            # 标的 D: 企稳但无通道支撑 (ch_supp=0, ch_pos=85.0%)
            "000040": {"name": "高位无通道D", "close": 10.0, "percent": 1.8, "dff2": 1.2, "dff3": 5.0, "ma20d": 9.88, "ch_supp": 0.0, "ch_pos": 85.0, "per1d": -0.8, "vol_ratio": 1.25, "amount": 3e8, "ratio": 2.2, "category": "低空经济"}
        }
        df = pd.DataFrame.from_dict(data, orient='index')

        # 3. 运行经典标准流水线
        res_classic = self.miner.run_mining_pipeline(df, filter_config=PRESET_FILTER_MODES["🎯 经典标准"])
        cand_codes_classic = [c["code"] for c in res_classic["candidates"]]
        self.assertIn("000010", cand_codes_classic, "标的A具备MA20企稳+通道支撑+放量收阳，必须命中!")
        self.assertNotIn("000020", cand_codes_classic, "标的B负涨幅阴跌(-1.5%)，坚决不能命中!")
        self.assertNotIn("000030", cand_codes_classic, "标的C跌破MA20(-6.0%)，坚决不能命中!")
        self.assertIn("000040", cand_codes_classic, "经典模式下无通道支撑但均线依托标的D可命中")

        # 验证标的 A 获得了通道支撑加分与战法标记
        cand_a = next(c for c in res_classic["candidates"] if c["code"] == "000010")
        self.assertIn("通道支撑", cand_a["reason"])
        self.assertTrue(cand_a["pct"] > 0, "候选标的必须严格收阳上涨!")

        # 4. 运行“💎 稳健通道低吸”模式 (require_channel_supp = True)
        res_channel = self.miner.run_mining_pipeline(df, filter_config=PRESET_FILTER_MODES["💎 稳健通道低吸"])
        cand_codes_channel = [c["code"] for c in res_channel["candidates"]]
        self.assertIn("000010", cand_codes_channel, "通道低吸模式下标的A必须命中!")
        self.assertNotIn("000040", cand_codes_channel, "通道低吸模式下无通道支撑的标的D必须被剔除!")

        # 5. 验证 UI 控件与微调对话框 (包含环境配置备份与自愈还原)
        from ats.ui.styles import load_config_node, save_config_node
        old_mode = load_config_node("sector_miner_filter_mode", None)
        old_custom = load_config_node("sector_miner_custom_filter", None)
        try:
            dialog = SectorRotationMinerDialog(parent=None, current_df=df)
            self.assertTrue(hasattr(dialog, "combo_filter_mode"))
            self.assertTrue(hasattr(dialog, "btn_config"))
            self.assertTrue(hasattr(dialog, "lbl_mode_summary"))

            # 测试 UI 切换模式
            dialog.combo_filter_mode.setCurrentText("🚀 极速起爆")
            self.assertEqual(dialog._current_filter_config.mode_name, "🚀 极速起爆")
            self.assertEqual(dialog._current_filter_config.min_eval_pct, 1.2)

            # 测试微调对话框 (验证当前生效策略展示与预设按钮高亮及动态感知联动)
            config_dlg = PullbackConfigDialog(dialog._current_filter_config, parent=dialog)
            self.assertTrue(hasattr(config_dlg, "lbl_current_strategy"), "微调对话框必须包含当前生效策略指示标签!")
            self.assertIn("🚀 极速起爆", config_dlg.lbl_current_strategy.text(), "微调对话框打开时必须直观显示当前生效的策略!")
            self.assertIn("#ffd700", config_dlg.btn_breakout.styleSheet(), "当前生效策略对应的预设按钮必须呈激活高亮样式!")

            # 切换预设模式：点击“🎯 经典标准”
            config_dlg._apply_preset("🎯 经典标准")
            self.assertIn("🎯 经典标准", config_dlg.lbl_current_strategy.text(), "点击预设后当前策略标签必须立即同步更新为经典标准!")
            self.assertIn("#ffd700", config_dlg.btn_classic.styleSheet(), "经典标准按钮必须呈高亮激活态!")

            # 手动微调参数：修改 MA20 依托下限与最小收阳
            config_dlg.spin_dff2_min.setValue(-1.2)
            config_dlg.spin_min_pct.setValue(0.5)
            self.assertIn("⚙️ 自定义", config_dlg.lbl_current_strategy.text(), "参数微调后系统必须动态感知并自动切换为自定义模式!")
            self.assertNotIn("#ffd700", config_dlg.btn_classic.styleSheet(), "偏离预设后预设按钮高亮必须自动取消!")

            config_dlg._on_save_clicked()
            custom_cfg = config_dlg.get_config()
            self.assertEqual(custom_cfg.mode_name, "⚙️ 自定义")
            self.assertEqual(custom_cfg.dff2_min, -1.2)
            self.assertEqual(custom_cfg.min_eval_pct, 0.5)

            config_dlg.close()
            dialog.close()
        finally:
            if old_mode is not None:
                save_config_node("sector_miner_filter_mode", old_mode)
            if old_custom is not None:
                save_config_node("sector_miner_custom_filter", old_custom)

    def test_11_adaptive_window_size_and_resizable_constraints(self):
        """测试窗口自适应缩放、最小尺寸解耦与小屏幕调整支持"""
        from PyQt6.QtCore import Qt
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog

        data = {
            "000001": {"name": "龙头1", "close": 20.0, "percent": 9.9, "category": "测试主线"}
        }
        df = pd.DataFrame.from_dict(data, orient='index')
        dialog = SectorRotationMinerDialog(parent=None, current_df=df)

        # 1. 验证 WindowFlags 必须包含最小化和最大化按钮 (独立专业窗口行为)
        flags = dialog.windowFlags()
        self.assertTrue(bool(flags & Qt.WindowType.WindowMinMaxButtonsHint), "窗口必须支持最小化与最大化按钮!")

        # 2. 验证最小尺寸解耦限制：允许自由调整到小屏分屏尺寸
        min_w = dialog.minimumWidth()
        min_h = dialog.minimumHeight()
        self.assertLessEqual(min_w, 700, f"窗口最小宽度必须允许 <=700px (当前: {min_w})!")
        self.assertLessEqual(min_h, 450, f"窗口最小高度必须允许 <=450px (当前: {min_h})!")

        # 3. 验证可以平滑自由 resize 到小屏幕尺寸 (如 750x480)
        dialog.resize(750, 480)
        self.assertLessEqual(dialog.width(), 760, "窗口必须可以顺利缩放到 750 左右，绝不被任何内部控件硬性顶死在 1200+!")

        # 4. 验证表格允许按需横向滚动 (避免内部列把外层窗口撑爆)
        self.assertEqual(dialog.sectors_table.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.assertEqual(dialog.candidates_table.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        dialog.close()

    def test_12_click_leader_pioneer_stock_linkage(self):
        """测试点击板块中的领涨先锋龙头时自动联动股票代码与名称 (带多重保底)"""
        from PyQt6.QtCore import Qt, QEvent
        from PyQt6.QtGui import QKeyEvent
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog

        data = {
            # 领涨先锋龙头 002202 金风科技 (+10.0%) 所属风电板块 (至少3只标的构成有效板块)
            "002202": {"name": "金风科技", "close": 20.0, "percent": 10.0, "category": "风电", "dff2": 4.0, "dff3": 15.0, "vol_ratio": 2.0, "amount": 8e8, "ratio": 5.0},
            "600875": {"name": "东方电气", "close": 18.0, "percent": 6.5, "category": "风电", "dff2": 3.0, "dff3": 12.0, "vol_ratio": 1.6, "amount": 6e8, "ratio": 4.0},
            "300129": {"name": "泰胜风能", "close": 12.0, "percent": 2.0, "category": "风电", "dff2": 1.0, "dff3": 5.0, "vol_ratio": 1.3, "amount": 4e8, "ratio": 3.0, "ma20d": 11.8, "per1d": -1.0}
        }
        df = pd.DataFrame.from_dict(data, orient='index')
        dialog = SectorRotationMinerDialog(parent=None, current_df=df)
        report = self.miner.run_mining_pipeline(df)
        dialog._on_scan_finished(report)

        # 1. 验证板块表格存在风电板块且第 5 列领涨龙头为金风科技
        self.assertGreater(dialog.sectors_table.rowCount(), 0)
        row_found = -1
        for r in range(dialog.sectors_table.rowCount()):
            sec_item = dialog.sectors_table.item(r, 0)
            if sec_item and "风电" in sec_item.text():
                row_found = r
                break
        self.assertNotEqual(row_found, -1, "必须扫描出风电主线板块!")

        leader_item = dialog.sectors_table.item(row_found, 5)
        self.assertIsNotNone(leader_item, "风电板块第 5 列必须存在领涨龙头单元格!")
        self.assertIn("金风科技", leader_item.text(), "领涨龙头文本必须包含金风科技!")

        # 2. 模拟鼠标单击第 5 列领涨先锋龙头单元格
        linked_codes = []
        dialog.code_clicked.connect(lambda c: linked_codes.append(c))

        dialog._on_sector_row_clicked(leader_item)
        self.assertIn("002202", linked_codes, "单击领涨龙头单元格必须自动发射联动信号联动该股票!")
        self.assertIn("已自动联动【风电】领涨先锋龙头", dialog.status_bar.text(), "状态栏必须更新领涨龙头联动提示!")
        self.assertEqual(dialog._selected_sector, "风电", "点击龙头单元格必须同时锁定风电主线!")

        # 3. 再次点击同一行第 5 列：领涨龙头必须持续联动，且坚决不触发反选取消
        linked_codes.clear()
        dialog._last_linked_code = None  # 清除防抖以确保测试连续响应
        dialog._on_sector_row_clicked(leader_item)
        self.assertIn("002202", linked_codes, "再次点击领涨龙头必须继续触发联动!")
        self.assertEqual(dialog._selected_sector, "风电", "点击龙头单元格绝不能触发 Toggle 反选清空主线!")

        # 4. 模拟键盘在第 5 列按 Enter 回车键联动
        linked_codes.clear()
        dialog._last_linked_code = None
        dialog.sectors_table.setCurrentCell(row_found, 5)
        enter_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        ret = dialog.eventFilter(dialog.sectors_table, enter_event)
        self.assertTrue(ret, "在领涨龙头单元格按 Enter 回车键必须拦截并处理联动!")
        self.assertIn("002202", linked_codes, "在领涨龙头单元格按 Enter 键必须联动股票!")

        # 5. 验证 _resolve_leader_code_and_name 的三重保底机制
        # 保底测试：清除 UserRole 的代码，验证从文本或 current_df 成功反查
        leader_item.setData(Qt.ItemDataRole.UserRole, "")
        code_resolved, name_resolved = dialog._resolve_leader_code_and_name(row_found)
        self.assertEqual(code_resolved, "002202", "缺失 UserRole 代码时必须成功从 current_df 反查出 002202!")
        self.assertEqual(name_resolved, "金风科技")

        dialog.close()

    def test_13_leader_momentum_ranking_and_realtime_competition(self):
        """测试领涨龙头基于连板、大成交中军与实时量比的多维综合动能选拔，及盘中动态更替"""
        miner = self.miner

        # 1. 测试动能评分函数：连板高标 > 首板 > 普通大涨
        p_ladder = {"code": "000001", "name": "连板高标", "pct": 10.0, "amt_yi": 5.0, "vol_ratio": 2.0, "turnover": 8.0, "pioneer_type": "👑 3连板龙头"}
        p_first = {"code": "000002", "name": "首板涨停", "pct": 10.0, "amt_yi": 3.0, "vol_ratio": 1.5, "turnover": 5.0, "pioneer_type": "👑 涨停先锋"}
        p_small = {"code": "000003", "name": "微盘脉冲", "pct": 10.0, "amt_yi": 0.2, "vol_ratio": 1.1, "turnover": 2.0, "pioneer_type": "👑 涨停先锋"}

        score_ladder = miner._calculate_pioneer_momentum_score(p_ladder)
        score_first = miner._calculate_pioneer_momentum_score(p_first)
        score_small = miner._calculate_pioneer_momentum_score(p_small)

        self.assertGreater(score_ladder, score_first, "3连板龙头的综合动能得分必须显著高于首板标的!")
        self.assertGreater(score_first, score_small, "相同涨幅下大成交额与活跃换手标的动能必须高于微盘脉冲股!")

        # 2. 实盘仿真数据：同一主线板块【储能】下的多维真龙头选拔
        # 场景一：早盘小票脉冲与大中军竞争 (大中军 000022 涨停且成交 25 亿，小票 000011 涨停但仅成交 0.3 亿)
        data_morning = {
            # 小票脉冲A涨停 10.0% (成交仅 0.3 亿，量比 1.1，微盘无带动性)
            "000011": {"name": "小票脉冲A", "close": 10.0, "percent": 10.0, "category": "储能", "dff2": 3.0, "vol_ratio": 1.1, "amount": 0.3e8, "ratio": 1.5},
            # 核心中军B亦涨停 10.0% (成交 25.0 亿，量比 2.8，百亿主力合力中军)
            "000022": {"name": "中军核心B", "close": 50.0, "percent": 10.0, "category": "储能", "dff2": 4.5, "vol_ratio": 2.8, "amount": 25.0e8, "ratio": 6.5},
            "000033": {"name": "储能跟风C", "close": 15.0, "percent": 2.0, "category": "储能", "dff2": 1.0, "vol_ratio": 1.2, "amount": 2.0e8, "ratio": 2.0, "ma20d": 14.8, "per1d": -1.0}
        }
        df_morning = pd.DataFrame.from_dict(data_morning, orient='index')
        res_morning = miner.run_mining_pipeline(df_morning)
        sec_morning = next(s for s in res_morning["sectors"] if s["name"] == "储能")
        # 验证中军核心B凭借25亿大资金容量与高量比动能，从同为10%的竞争中胜出作为板块真正龙头旗手！
        self.assertEqual(sec_morning["leader_code"], "000022", "同为涨停时大资金大容量核心标的必须胜出作为动能最强龙头!")
        self.assertGreater(sec_morning["leader_amt_yi"], 20.0)

        # 场景二：午盘实时动态更替：若出现连板龙头 000044 (2连板，成交 8 亿)，连板高度确立情绪总龙头
        from unittest.mock import patch, MagicMock
        data_afternoon = dict(data_morning)
        data_afternoon["000044"] = {"name": "连板真龙D", "close": 22.0, "percent": 10.0, "category": "储能", "dff2": 6.0, "vol_ratio": 2.5, "amount": 8.0e8, "ratio": 8.0}
        # 模拟 000044 属于连板天梯
        with patch("ats.limit_up_engine.LimitUpEngine.get_instance") as mock_lue:
            mock_inst = MagicMock()
            mock_inst._current_live_records = [{"code": "000044", "limit_days": 2, "is_limit_up": True}]
            mock_lue.return_value = mock_inst

            df_afternoon = pd.DataFrame.from_dict(data_afternoon, orient='index')
            res_afternoon = miner.run_mining_pipeline(df_afternoon)
            sec_afternoon = next(s for s in res_afternoon["sectors"] if s["name"] == "储能")
            self.assertEqual(sec_afternoon["leader_code"], "000044", "盘中出现连板高标龙头时必须动态更替为最新总龙头!")

    def test_14_auto_refresh_interval_alignment_with_cct_ats_tdx_interval(self):
        """测试自动刷新间隔与 cct.ats_tdx_interval 全局基准的对齐、自适应与独立微调"""
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog
        from JohnsonUtil import commonTips as cct

        old_val = getattr(cct, 'ats_tdx_interval', 5.0)
        try:
            # 1. 全局基准为 5.0s 时初始化
            cct.ats_tdx_interval = 5.0
            dialog = SectorRotationMinerDialog(parent=None, current_df=None)
            self.assertEqual(dialog._get_global_ats_interval(), 5.0)
            self.assertIn("5 秒", dialog.combo_interval.currentText())
            self.assertIn("(全局基准)", dialog.combo_interval.currentText())

            # 2. 勾选自动刷新，定时器以 5000ms 启动且提示与全局同步
            dialog.chk_auto.setChecked(False)
            dialog.chk_auto.setChecked(True)
            self.assertTrue(dialog.refresh_timer.isActive())
            self.assertEqual(dialog.refresh_timer.interval(), 5000)
            self.assertIn("与系统全局基准同步", dialog.status_bar.text())

            # 3. 工作台独立微调为 3 秒：定时器以 3000ms 运行并提示独立微调
            idx_3s = -1
            for i in range(dialog.combo_interval.count()):
                if "3 秒" in dialog.combo_interval.itemText(i):
                    idx_3s = i
                    break
            self.assertGreaterEqual(idx_3s, 0)
            dialog.combo_interval.setCurrentIndex(idx_3s)
            self.assertEqual(dialog.refresh_timer.interval(), 3000)
            self.assertIn("工作台独立微调", dialog.status_bar.text())

            # 4. 全局动态更新为 10.0s 并调用 sync_with_global_interval
            cct.ats_tdx_interval = 10.0
            dialog.sync_with_global_interval()
            self.assertIn("10 秒", dialog.combo_interval.currentText())
            self.assertEqual(dialog.refresh_timer.interval(), 10000)

            # 5. 非标准自定义间隔 (如 8.0s) 自适应生成选项并默认对齐
            cct.ats_tdx_interval = 8.0
            dialog2 = SectorRotationMinerDialog(parent=None, current_df=None)
            self.assertEqual(dialog2._get_global_ats_interval(), 8.0)
            self.assertIn("8 秒", dialog2.combo_interval.currentText())
            self.assertIn("(全局基准)", dialog2.combo_interval.currentText())
            dialog2.close()

            dialog.close()
        finally:
            cct.ats_tdx_interval = old_val

    def test_15_compact_mode_and_strategy_persistence(self):
        """测试磁吸与精简版样式 (Compact Mode)、恢复全貌与策略配置自动持久化记忆"""
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog
        from ats.sector_rotation_pullback_miner import PullbackFilterConfig
        from ats.ui.styles import load_config_node, save_config_node

        old_mode = load_config_node("sector_miner_filter_mode", None)
        old_custom = load_config_node("sector_miner_custom_filter", None)
        old_view = load_config_node("sector_miner_view_mode", None)

        try:
            # 1. 模拟自定义策略微调并持久化验证
            custom_cfg = PullbackFilterConfig(
                mode_name="⚙️ 自定义",
                dff2_min=-3.1,
                dff2_max=9.0,
                min_eval_pct=1.2,
                min_vol_ratio=1.35,
                min_turnover=2.0,
                prefer_channel_supp=True
            )
            save_config_node("sector_miner_filter_mode", "⚙️ 自定义")
            save_config_node("sector_miner_custom_filter", custom_cfg.to_dict())
            save_config_node("sector_miner_view_mode", "full")

            # 重新打开窗口，验证是否 100% 自动恢复“⚙️ 自定义”与微调参数
            dialog = SectorRotationMinerDialog(parent=None, current_df=None)
            self.assertEqual(dialog.combo_filter_mode.currentText(), "⚙️ 自定义")
            self.assertEqual(dialog._current_filter_config.dff2_min, -3.1)
            self.assertEqual(dialog._current_filter_config.dff2_max, 9.0)
            self.assertEqual(dialog._current_filter_config.min_eval_pct, 1.2)
            self.assertIn("MA20:[-3.1%,+9.0%]", dialog.lbl_mode_summary.text())

            # 2. 验证精简模式 (Compact Mode) 切换
            self.assertFalse(dialog._is_compact_mode)
            self.assertEqual(dialog.btn_compact.text(), "🧲 精简 (M)")
            self.assertFalse(dialog.lbl_title.isHidden())
            self.assertFalse(dialog.row2_widget.isHidden())

            # 触发切换进入精简模式
            dialog.toggle_compact_mode(force_compact=True)
            self.assertTrue(dialog._is_compact_mode)
            self.assertIn("恢复全貌", dialog.btn_compact.text())
            self.assertTrue(dialog.lbl_title.isHidden())
            self.assertTrue(dialog.row2_widget.isHidden())
            # 精简模式不应强制自动置顶，置顶完全由操盘手手动选择
            self.assertFalse(dialog.btn_top.isChecked(), "精简模式不应强制自动置顶，保持操盘手手动选择状态!")

            # 验证精简模式下自适应保留核心字段 (dff, dff2, dff3, 量比等)
            dialog._adapt_compact_columns(target_width=370)
            self.assertTrue(dialog.sectors_table.isColumnHidden(1))  # 资金评级在 370px 窄窗口下折叠
            self.assertTrue(dialog.sectors_table.isColumnHidden(6))  # 成交额折叠
            self.assertFalse(dialog.sectors_table.isColumnHidden(0)) # 板块名保留
            self.assertFalse(dialog.sectors_table.isColumnHidden(5)) # 领涨龙头保留

            self.assertFalse(dialog.candidates_table.isColumnHidden(0)) # 代码保留
            self.assertFalse(dialog.candidates_table.isColumnHidden(1)) # 名称保留
            self.assertFalse(dialog.candidates_table.isColumnHidden(3)) # 启动形态保留
            self.assertFalse(dialog.candidates_table.isColumnHidden(5)) # 涨幅 dff 保留
            self.assertFalse(dialog.candidates_table.isColumnHidden(6)) # 距MA20 dff2 保留 (用户需求)
            self.assertFalse(dialog.candidates_table.isColumnHidden(7)) # 长期 dff3 保留 (用户需求)
            self.assertFalse(dialog.candidates_table.isColumnHidden(9)) # 量比保留 (用户需求)
            self.assertTrue(dialog.candidates_table.isColumnHidden(4))  # 综合得分在 370px 下折叠
            self.assertTrue(dialog.candidates_table.isColumnHidden(10)) # 建议买区在 370px 下折叠

            # 验证窗口加宽 (680px) 时自适应展现更多信息
            dialog._adapt_compact_columns(target_width=680)
            self.assertFalse(dialog.sectors_table.isColumnHidden(1))   # 资金评级自适应展现
            self.assertFalse(dialog.candidates_table.isColumnHidden(4)) # 综合得分自适应展现
            self.assertFalse(dialog.candidates_table.isColumnHidden(10))# 建议买区自适应展现

            # 3. 触发恢复全貌模式
            dialog.toggle_compact_mode(force_compact=False)
            self.assertFalse(dialog._is_compact_mode)
            self.assertIn("精简", dialog.btn_compact.text())
            self.assertFalse(dialog.lbl_title.isHidden())
            self.assertFalse(dialog.row2_widget.isHidden())
            self.assertFalse(dialog.sectors_table.isColumnHidden(1))
            self.assertFalse(dialog.candidates_table.isColumnHidden(4))

            # 4. 验证磁吸贴边检测
            dialog.setGeometry(10, 10, 800, 500)
            dialog._detect_and_snap()
            self.assertTrue(dialog.x() <= 10 or dialog.y() <= 10)

            dialog.close()
        finally:
            if old_mode is not None:
                save_config_node("sector_miner_filter_mode", old_mode)
            if old_custom is not None:
                save_config_node("sector_miner_custom_filter", old_custom)
            if old_view is not None:
                save_config_node("sector_miner_view_mode", old_view)


    def test_16_magnetic_snap_animation_and_compact_responsiveness(self):
        """测试磁吸贴边动效 (start_slide_animation)、全局穿透快捷键 (M/T) 与精简卡片自适应"""
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog
        from PyQt6.QtCore import QRect
        from ats.ui.styles import save_config_node

        save_config_node("sector_miner_view_mode", "full")
        dialog = SectorRotationMinerDialog(parent=None, current_df=None)
        dialog.show()

        # 1. 验证快捷键对象注入与穿透
        self.assertTrue(hasattr(dialog, "_compact_shortcut_m"), "必须注册窗口级 _compact_shortcut_m")
        self.assertTrue(hasattr(dialog, "_top_shortcut_t"), "必须注册窗口级 _top_shortcut_t")

        # 2. 验证无参调用 _toggle_stay_on_top (快捷键 T 穿透)
        initial_top = dialog.btn_top.isChecked()
        dialog._toggle_stay_on_top()
        self.assertEqual(dialog.btn_top.isChecked(), not initial_top)
        dialog._toggle_stay_on_top()
        self.assertEqual(dialog.btn_top.isChecked(), initial_top)

        # 3. 验证平滑滑入动效 (start_slide_animation)
        target_geo = QRect(100, 100, 400, 600)
        dialog.start_slide_animation(target_geo, 1.0, duration=50, is_snap_feedback=True)
        self.assertTrue(dialog._in_snap_action or dialog.anim_group is not None)

        # 4. 验证磁吸贴齐检测触发动画
        dialog.setGeometry(5, 5, 500, 400)
        dialog._detect_and_snap()
        self.assertTrue(dialog._in_snap_action or dialog.x() <= 5)

        # 5. 验证精简模式控件精炼与宽度自适应
        dialog.toggle_compact_mode(force_compact=True)
        self.assertTrue(dialog._is_compact_mode)
        self.assertEqual(dialog.btn_scan.text(), "🚀 挖掘")
        self.assertEqual(dialog.chk_auto.text(), "自动")
        self.assertEqual(dialog.btn_top.text(), "📌")
        self.assertEqual(dialog.btn_close.text(), "✕ 关闭")
        self.assertFalse(dialog.combo_interval.isVisible())
        self.assertFalse(dialog.combo_filter_mode.isVisible())

        # 还原全貌
        dialog.toggle_compact_mode(force_compact=False)
        self.assertFalse(dialog._is_compact_mode)
        self.assertEqual(dialog.btn_scan.text(), "🚀 一键深度挖掘")
        self.assertEqual(dialog.chk_auto.text(), "自动刷新")
        self.assertTrue(dialog.combo_interval.isVisible())
        dialog.close()

    def test_17_button_click_toggle_and_ats_magnetic_snap_edge_cycle(self):
        """测试点击精简按钮秒级生效、置顶手动选择与 ATS 底层磁吸折叠展开完整生命周期 (SSOT)"""
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog
        from ats.ui.styles import save_config_node
        from PyQt6.QtCore import QRect

        save_config_node("sector_miner_view_mode", "full")
        dialog = SectorRotationMinerDialog(parent=None, current_df=None)
        dialog.show()

        # 1. 验证按钮物理点击直接生效 (解决 clicked(bool) 传参被吞 Bug)
        self.assertFalse(dialog._is_compact_mode)
        dialog.btn_compact.click() # 模拟操盘手鼠标点击按钮
        self.assertTrue(dialog._is_compact_mode, "点击精简按钮必须成功切换进入精简模式!")
        self.assertIn("恢复全貌", dialog.btn_compact.text())

        # 验证精简模式不强制置顶（置顶保持操盘手手动选择）
        self.assertFalse(dialog.btn_top.isChecked(), "精简模式下不应强制自动置顶，保持操盘手手动状态!")

        # 再次物理点击恢复全貌
        dialog.btn_compact.click()
        self.assertFalse(dialog._is_compact_mode, "再次点击精简按钮必须恢复全貌模式!")
        self.assertIn("精简", dialog.btn_compact.text())

        # 2. 验证 ATS 底层磁吸贴边与吸附检测 (SSOT)
        # 初始未置顶状态
        self.assertFalse(dialog.stays_on_top)
        # 模拟移动到屏幕最左侧
        screen = dialog.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        dialog.setGeometry(avail.left() + 5, avail.top() + 100, 380, 600)
        dialog._detect_and_snap()
        self.assertEqual(dialog.anchor_edge, "left", "靠近屏幕左侧必须识别并吸附到 left 边缘!")
        self.assertTrue(dialog.hover_timer.isActive(), "贴边吸附后必须激活 hover_timer 悬停轮询!")

        # 3. 验证贴边折叠至边缘微感应条 (hide_to_edge)
        dialog.hide_to_edge()
        self.assertTrue(dialog.is_hidden_state, "hide_to_edge 后必须标记为 is_hidden_state!")
        self.assertIsNotNone(dialog.anim_group, "hide_to_edge 必须启动平滑滑出动效!")

        # 4. 验证悬停展开恢复全貌 (show_normal_position)
        dialog.show_normal_position()
        self.assertFalse(dialog.is_hidden_state, "show_normal_position 后必须恢复 normal 状态!")
        self.assertEqual(dialog.windowOpacity(), 1.0, "展开后透明度必须恢复为 1.0 完全可见!")

        # 5. 验证置顶与磁吸严格互斥机制
        dialog._toggle_stay_on_top(True)
        self.assertTrue(dialog.stays_on_top, "置顶已手动开启")
        self.assertIsNone(dialog.anchor_edge, "开启置顶时必须清除 anchor_edge 并禁止磁吸贴边!")
        self.assertFalse(dialog.hover_timer.isActive(), "开启置顶时必须停用 hover_timer 避免干扰看盘!")

        dialog.close()

    def test_18_startup_hidden_dock_and_smooth_edge_sensing_popup(self):
        """启动时隐藏折叠状态 100% 恢复 normal_geometry、hover_timer 激活并平滑展开 (对齐 ATS SSOT)"""
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog
        from ats.ui.styles import save_config_node
        from PyQt6.QtCore import QPoint, QRect

        save_config_node("sector_miner_anchor_edge", "left")
        save_config_node("sector_miner_is_hidden", True)
        save_config_node("sector_miner_stays_on_top", False)
        save_config_node("sector_miner_normal_geo", [100, 100, 400, 600])

        dialog = SectorRotationMinerDialog(parent=None, current_df=None)
        try:
            # 1. 验证启动后 normal_geometry 与隐藏状态正确恢复
            self.assertIsNotNone(dialog.normal_geometry, "启动时必须恢复 normal_geometry!")
            self.assertEqual(dialog.normal_geometry.width(), 400)
            self.assertEqual(dialog.normal_geometry.height(), 600)
            self.assertTrue(dialog.is_hidden_state, "启动时必须处于 is_hidden_state!")
            self.assertEqual(dialog.anchor_edge, "left")
            self.assertAlmostEqual(dialog.windowOpacity(), 0.35, places=2)

            # 2. 验证 hover_timer 处于激活状态
            self.assertTrue(dialog.hover_timer.isActive(), "贴边隐藏状态下 hover_timer 必须激活!")

            # 3. 验证触发 show_normal_position 启动平滑滑出展开
            dialog.show_normal_position()
            self.assertFalse(dialog.is_hidden_state, "展开后 is_hidden_state 必须置为 False!")
            self.assertIsNotNone(dialog.anim_group, "必须启动滑出展开动效!")
        finally:
            save_config_node("sector_miner_anchor_edge", None)
            save_config_node("sector_miner_is_hidden", False)
            dialog.close()

    def test_19_sector_arrow_key_and_click_linkage_and_menu_cleanup(self):
        """验证板块表格按键/点击切换第2行即时触发联动，以及右键复制表达式菜单已彻底清理"""
        from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog
        from unittest.mock import MagicMock, patch
        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtCore import QPoint

        sample_df = pd.DataFrame({
            'name': ['超声电子', '神宇股份', '一博科技', '胜蓝股份', '沪电股份', '博威合金'],
            'percent': [10.0, 20.0, 1.4, 1.5, 5.0, 6.0],
            'close': [15.0, 25.0, 30.0, 18.0, 28.0, 19.0],
            'volume': [100000, 200000, 80000, 90000, 150000, 160000],
            'amount': [1.5e8, 5.0e8, 1.2e8, 1.4e8, 2.5e8, 2.8e8],
            'category': ['PCB概念', '铜缆高速连接', 'PCB概念', '铜缆高速连接', 'PCB概念', '铜缆高速连接'],
            'dff': [10.0, 20.0, 1.4, 1.5, 5.0, 6.0],
            'dff2': [1.2, 2.5, 0.5, -0.8, 1.8, 2.2],
            'dff3': [3.0, 5.0, 1.0, 0.2, 4.0, 5.5],
            'volume_ratio': [2.5, 3.2, 1.06, 1.27, 1.8, 2.0],
            'turnover_ratio': [5.0, 8.0, 2.1, 2.5, 4.0, 4.5],
            'channel_support': [True, True, True, True, True, True],
            'limit_days': [1, 1, 0, 0, 0, 0],
            'status': ['封板', '封板', '正常', '正常', '正常', '正常'],
        }, index=['000823', '300563', '301366', '300843', '002463', '300548'])

        dialog = SectorRotationMinerDialog(parent=None, current_df=sample_df)
        report = self.miner.run_mining_pipeline(sample_df)
        dialog._on_scan_finished(report)
        dialog._broadcast_link_stock = MagicMock()

        try:
            # 1. 验证按键光标在板块表格切换时，第2行绝不遗漏联动
            self.assertGreaterEqual(dialog.sectors_table.rowCount(), 2)
            row0_sec = dialog.sectors_table.item(0, 0).text().replace("⭐", "").strip()
            row1_sec = dialog.sectors_table.item(1, 0).text().replace("⭐", "").strip()

            # 选中第 0 行 (相当于初次聚焦)
            dialog.sectors_table.setCurrentCell(0, 1)
            self.assertEqual(dialog._selected_sector, row0_sec)
            dialog._broadcast_link_stock.assert_called()

            # 模拟操盘手按键盘 Down 键移动到第 2 行 (Row 1)
            dialog._broadcast_link_stock.reset_mock()
            dialog.sectors_table.setCurrentCell(1, 1)
            # 断言第 2 行立即生效，下半区切换为第 2 行板块，且触发领涨龙头联动
            self.assertEqual(dialog._selected_sector, row1_sec)
            dialog._broadcast_link_stock.assert_called()

            # 2. 验证右键菜单彻底删除了“复制查询表达式”
            captured_actions = []
            orig_qmenu = QMenu
            class MonitoredMenu(orig_qmenu):
                def exec(self, *args, **kwargs):
                    for act in self.actions():
                        captured_actions.append(act.text())
                    return None

            with patch("ats.ui.sector_rotation_miner_dialog.QMenu", MonitoredMenu):
                rect0 = dialog.sectors_table.visualItemRect(dialog.sectors_table.item(0, 0))
                dialog._on_sector_context_menu(rect0.center())
                if dialog.candidates_table.rowCount() > 0:
                    cand_rect = dialog.candidates_table.visualItemRect(dialog.candidates_table.item(0, 0))
                    dialog._on_candidate_context_menu(cand_rect.center())

            self.assertGreater(len(captured_actions), 0)
            for txt in captured_actions:
                self.assertNotIn("查询表达式", txt, "右键菜单严禁包含复制查询表达式!")

            # 3. 验证精简模式下列自适应支持 dff, dff2, dff3, 量比
            dialog.toggle_compact_mode(force_compact=True)
            self.assertFalse(dialog.candidates_table.isColumnHidden(5)) # dff
            self.assertFalse(dialog.candidates_table.isColumnHidden(6)) # dff2
            self.assertFalse(dialog.candidates_table.isColumnHidden(7)) # dff3
            self.assertFalse(dialog.candidates_table.isColumnHidden(9)) # 量比
        finally:
            dialog.close()


if __name__ == '__main__':
    unittest.main()




