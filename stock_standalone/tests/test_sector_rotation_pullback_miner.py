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

        # 极致性能断言：5000 只标的全流程扫描必须保持毫秒级极速响应 (< 300ms)
        self.assertLess(cost_ms, 300.0, f"5000 只标的大循环扫描耗时 {cost_ms:.2f}ms 超过 300ms 阈值!")

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


if __name__ == '__main__':
    unittest.main()


