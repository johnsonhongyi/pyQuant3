# -*- coding: utf-8 -*-
"""
tests/test_market_volume_statusbar.py — 大盘四大指数资金量比与全市交易额增减测试用例
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import datetime
import pandas as pd
import numpy as np

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QLabel, QStatusBar
from PyQt6.QtCore import Qt

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication([])

from ats.capital_dragon_engine import CapitalDragonEngine


class TestMarketVolumeEngineAndStatusBar(unittest.TestCase):

    def setUp(self):
        self.engine = CapitalDragonEngine.get_instance()
        with self.engine._cache_lock:
            # 清理引擎缓存
            self.engine._market_summary_cache = None
            self.engine._market_summary_cache_ts = 0.0

    def test_01_extract_indices_and_volume_from_df_all(self):
        """测试从 df_all 中提取上证、深证、创业板、北证的资金、量比及全市总交易额"""
        mock_records = [
            {"code": "999999", "name": "上证指数", "amount": 7796.7e8, "vol_ratio": 0.94},
            {"code": "399001", "name": "深证成指", "amount": 8674.8e8, "vol_ratio": 0.93},
            {"code": "399006", "name": "创业板指", "amount": 3840.6e8, "vol_ratio": 0.91},
            {"code": "899050", "name": "北证50",   "amount": 153.7e8,  "vol_ratio": 0.90},
            {"code": "600000", "name": "浦发银行", "amount": 12.5e8,   "vol_ratio": 1.15},
        ]
        df_all = pd.DataFrame(mock_records).set_index("code", drop=False)

        # 模拟昨日总成交额 (如昨日总计 18732.5 亿)
        today_str = "2026-09-10"
        self.engine._yesterday_index_amounts = {
            'sh': 8500.0, 'sz': 10050.0, 'cy': 4200.0, 'bj': 182.5,
            'total': 18732.5,
            'vol_sh': 1000.0, 'vol_sz': 1200.0, 'vol_cy': 500.0, 'vol_bj': 20.0
        }
        self.engine._yesterday_cache_date = today_str

        # 1. 盘后测试 (hour >= 15)
        now_dt = datetime.datetime(2026, 9, 10, 15, 30, 0)
        res = self.engine.get_market_indices_and_volume_summary(df_all, now_dt=now_dt)

        self.assertAlmostEqual(res["sh_amt"], 7796.7, places=1)
        self.assertAlmostEqual(res["sh_vr"], 0.94, places=2)
        self.assertAlmostEqual(res["sz_amt"], 8674.8, places=1)
        self.assertAlmostEqual(res["sz_vr"], 0.93, places=2)
        self.assertAlmostEqual(res["cy_amt"], 3840.6, places=1)
        self.assertAlmostEqual(res["cy_vr"], 0.91, places=2)
        self.assertAlmostEqual(res["bj_amt"], 153.7, places=1)
        self.assertAlmostEqual(res["bj_vr"], 0.90, places=2)

        # 官方全市成交额口径: 沪市 + 深市 + 北交所
        expected_total = round(7796.7 + 8674.8 + 153.7, 1) # 16625.2
        self.assertAlmostEqual(res["total_amt"], expected_total, places=1)

        # 盘后较昨日增减额: 16625.2 - 18732.5 = -2107.3亿
        expected_diff = round(expected_total - 18732.5, 1)
        self.assertAlmostEqual(res["diff_amt"], expected_diff, places=1)
        self.assertEqual(res["diff_str"], f"{expected_diff:.1f}亿")

        # HTML 与 纯文本检查
        self.assertIn("上证:", res["formatted_html"])
        self.assertIn("7796.7亿", res["formatted_html"])
        self.assertIn("(0.94x)", res["formatted_html"])
        self.assertIn("深证:", res["formatted_html"])
        self.assertIn("8674.8亿", res["formatted_html"])
        self.assertIn("(0.93x)", res["formatted_html"])
        self.assertIn("创业板:", res["formatted_html"])
        self.assertIn("3840.6亿", res["formatted_html"])
        self.assertIn("(0.91x)", res["formatted_html"])
        self.assertIn("北证:", res["formatted_html"])
        self.assertIn("153.7亿", res["formatted_html"])
        self.assertIn("(0.90x)", res["formatted_html"])
        self.assertIn("全市:", res["formatted_html"])
        self.assertIn(f"{expected_total:.1f}亿", res["formatted_html"])
        self.assertIn(f"(较昨 {expected_diff:.1f}亿)", res["formatted_html"])

    def test_02_intraday_volume_difference_with_work_time_ratio(self):
        """测试盘中时段按工作时间比例计算同比增减额"""
        mock_records = [
            {"code": "999999", "name": "上证指数", "amount": 2000.0e8, "vol_ratio": 1.20},
            {"code": "399001", "name": "深证成指", "amount": 2500.0e8, "vol_ratio": 1.25},
            {"code": "399006", "name": "创业板指", "amount": 1000.0e8, "vol_ratio": 1.18},
            {"code": "899050", "name": "北证50",   "amount": 50.0e8,   "vol_ratio": 1.10},
        ]
        df_all = pd.DataFrame(mock_records).set_index("code", drop=False)

        # 模拟昨日总成交额为 18000.0 亿
        self.engine._yesterday_index_amounts = {
            'sh': 8000.0, 'sz': 9800.0, 'cy': 4000.0, 'bj': 200.0,
            'total': 18000.0
        }
        self.engine._yesterday_cache_date = "2026-09-10"

        # 模拟盘中 10:00 (ratio_t = 0.25)
        now_dt = datetime.datetime(2026, 9, 10, 10, 0, 0)
        with patch("JohnsonUtil.commonTips.get_work_time_ratio", return_value="0.25"):
            res = self.engine.get_market_indices_and_volume_summary(df_all, now_dt=now_dt)

        # 今日盘中此时全市: 2000 + 2500 + 50 = 4550.0 亿
        # 昨日同期基准: 18000.0 * 0.25 = 4500.0 亿
        # 较昨增减: 4550.0 - 4500.0 = +50.0 亿 (放量)
        self.assertAlmostEqual(res["total_amt"], 4550.0, places=1)
        self.assertAlmostEqual(res["diff_amt"], 50.0, places=1)
        self.assertEqual(res["diff_str"], "+50.0亿")
        self.assertIn("+50.0亿", res["formatted_html"])
        self.assertIn("#ff5555", res["formatted_html"]) # 放量红色高亮

    def test_03_cache_debounce_behavior(self):
        """测试 1.5 秒轻量防抖缓存机制"""
        mock_records = [
            {"code": "999999", "amount": 1000.0e8, "vol_ratio": 1.0},
            {"code": "399001", "amount": 1000.0e8, "vol_ratio": 1.0},
            {"code": "399006", "amount": 500.0e8,  "vol_ratio": 1.0},
            {"code": "899050", "amount": 10.0e8,   "vol_ratio": 1.0},
        ]
        df_all = pd.DataFrame(mock_records).set_index("code", drop=False)

        res1 = self.engine.get_market_indices_and_volume_summary(df_all)
        # 立即不带 df_all 获取，应命中缓存
        res2 = self.engine.get_market_indices_and_volume_summary(None)
        self.assertEqual(res1["total_amt"], res2["total_amt"])
        self.assertEqual(res1["formatted_html"], res2["formatted_html"])

    def test_04_status_bar_ui_integration(self):
        """测试 MainWindow 状态栏常驻控件的初始化与动态刷新"""
        from ats.ui.main_window import ATSMainWindow

        # 模拟主窗口轻量实例
        mock_win = MagicMock()
        mock_win.status_bar = QStatusBar()
        mock_win.lbl_market_volume_status = QLabel()
        mock_win.current_df = pd.DataFrame([
            {"code": "999999", "name": "上证指数", "amount": 7700.0e8, "vol_ratio": 1.05},
            {"code": "399001", "name": "深证成指", "amount": 8800.0e8, "vol_ratio": 1.02},
            {"code": "399006", "name": "创业板指", "amount": 3500.0e8, "vol_ratio": 0.98},
            {"code": "899050", "name": "北证50",   "amount": 160.0e8,  "vol_ratio": 1.10},
        ]).set_index("code", drop=False)

        # 绑定 ATSMainWindow 的 _refresh_market_volume_status 方法
        mock_win._refresh_market_volume_status = ATSMainWindow._refresh_market_volume_status.__get__(mock_win, ATSMainWindow)

        # 执行刷新
        mock_win._refresh_market_volume_status()

        # 验证控件文本成功更新
        rendered_text = mock_win.lbl_market_volume_status.text()
        self.assertIn("上证:", rendered_text)
        self.assertIn("深证:", rendered_text)
        self.assertIn("创业板:", rendered_text)
        self.assertIn("北证:", rendered_text)
        self.assertIn("全市:", rendered_text)
        self.assertIn("亿", rendered_text)

    def test_05_intraday_virtual_volume_and_same_period_comparison(self):
        """测试盘中时段【较昨同期对比】与【虚拟全天成交额预测】的完整数学逻辑与展示格式"""
        mock_records = [
            {"code": "999999", "name": "上证指数", "amount": 5424.1e8, "vol_ratio": 0.85},
            {"code": "399001", "name": "深证成指", "amount": 5957.7e8, "vol_ratio": 0.86},
            {"code": "399006", "name": "创业板指", "amount": 2810.4e8, "vol_ratio": 0.88},
            {"code": "899050", "name": "北证50",   "amount": 98.8e8,   "vol_ratio": 0.90},
        ]
        df_all = pd.DataFrame(mock_records).set_index("code", drop=False)

        # 模拟昨日全天总成交额为 19871.9 亿
        self.engine._yesterday_index_amounts = {
            'sh': 9581.9, 'sz': 10137.1, 'cy': 4626.2, 'bj': 152.9,
            'total': 19871.9
        }
        self.engine._yesterday_cache_date = "2026-09-14"

        # 模拟盘中 11:28 (上午快收盘，时间进度约 64.3%)
        now_dt = datetime.datetime(2026, 9, 14, 11, 28, 0)
        res = self.engine.get_market_indices_and_volume_summary(df_all, now_dt=now_dt)

        # 今日盘中此时全市成交: 5424.1 + 5957.7 + 98.8 = 11480.6 亿
        self.assertAlmostEqual(res["total_amt"], 11480.6, places=1)
        self.assertTrue(res["is_intraday"])
        self.assertEqual(res["diff_label"], "较同期")

        # 验证昨日同期基准与同期增减
        expected_ratio = res["ratio_t"]
        self.assertGreater(expected_ratio, 0.60)
        self.assertLess(expected_ratio, 0.66)
        expected_prev_same = round(19871.9 * expected_ratio, 1)
        self.assertAlmostEqual(res["prev_same_amt"], expected_prev_same, places=1)

        expected_diff = round(11480.6 - expected_prev_same, 1)
        self.assertAlmostEqual(res["diff_amt"], expected_diff, places=1)

        # 验证虚拟全天成交额预测 (proj_total)
        expected_proj = round(11480.6 / expected_ratio, 1)
        self.assertAlmostEqual(res["proj_total_amt"], expected_proj, places=1)
        self.assertIn("万亿", res["proj_total_str"])

        # 验证格式化展示文本
        self.assertIn("较同期", res["formatted_html"])
        self.assertIn("虚拟", res["formatted_html"])
        self.assertIn(res["diff_str"], res["formatted_html"])
        self.assertIn(res["proj_total_str"], res["formatted_html"])

        # 验证 ToolTip 包含完整的量化分析全景
        self.assertIn("📊 全市成交额与虚拟量统计 (盘中实时)", res["tooltip_text"])
        self.assertIn("昨日同期成交额", res["tooltip_text"])
        self.assertIn("全天预估虚拟量", res["tooltip_text"])
        self.assertIn("四大指数虚拟量比", res["tooltip_text"])

    def test_06_work_time_ratio_monotonicity_and_edge_times(self):
        """测试 commonTips 日内时间进度比率的连续性、单调性与关键时段边界"""
        import JohnsonUtil.commonTips as cct

        test_timeline = [
            (datetime.datetime(2026, 9, 14, 9, 25), 0.05),
            (datetime.datetime(2026, 9, 14, 9, 30), 0.05),
            (datetime.datetime(2026, 9, 14, 10, 0), 0.35),
            (datetime.datetime(2026, 9, 14, 10, 45), 0.50),
            (datetime.datetime(2026, 9, 14, 11, 30), 0.65),
            (datetime.datetime(2026, 9, 14, 12, 0), 0.65), # 午间休市保持 0.65
            (datetime.datetime(2026, 9, 14, 13, 0), 0.65), # 下午开盘保持 0.65
            (datetime.datetime(2026, 9, 14, 13, 30), 0.725),
            (datetime.datetime(2026, 9, 14, 14, 0), 0.80),
            (datetime.datetime(2026, 9, 14, 14, 30), 0.90),
            (datetime.datetime(2026, 9, 14, 15, 0), 1.00), # 收盘 1.00
            (datetime.datetime(2026, 9, 14, 15, 30), 1.00), # 盘后 1.00
        ]

        prev_r = 0.0
        for dt_point, expected_val in test_timeline:
            r = cct.get_work_time_ratio('d', now_time=dt_point)
            self.assertAlmostEqual(r, expected_val, places=3,
                                   msg=f"时段 {dt_point.strftime('%H:%M')} 进度计算异常: 期望 {expected_val}, 实际 {r}")
            self.assertGreaterEqual(r, prev_r, msg=f"时段 {dt_point.strftime('%H:%M')} 未满足单调递增")
            prev_r = r

    def test_07_stock_sector_exact_tag_matching(self):
        """测试个股板块独立标签精准比对，彻底杜绝中京电子/科森科技被'新型烟草'误匹配到'烟草'"""
        from ats.hot_sector_engine import is_stock_matched_sector

        # 1. 中京电子 (002579) 真实板块标签：含有 '新型烟草(电子烟)'，但绝不属于 '烟草'
        zj_cat = "6G概念;PCB概念;新型烟草(电子烟);苹果概念;华为概念;消费电子"
        self.assertFalse(is_stock_matched_sector(zj_cat, "烟草"),
                         "中京电子不应被判定为属于【烟草】板块")
        self.assertTrue(is_stock_matched_sector(zj_cat, "PCB"),
                        "中京电子应匹配【PCB】板块")
        self.assertTrue(is_stock_matched_sector(zj_cat, "PCB概念"),
                        "中京电子应匹配【PCB概念】板块")
        self.assertTrue(is_stock_matched_sector(zj_cat, "新型烟草(电子烟)"),
                        "中京电子可匹配其真实的【新型烟草(电子烟)】原标签")

        # 2. 科森科技 (603626) 真实板块标签：含有 '新型烟草(电子烟)'，绝不属于 '烟草'
        ks_cat = "折叠屏;消费电子;新型烟草(电子烟);无线耳机"
        self.assertFalse(is_stock_matched_sector(ks_cat, "烟草"),
                         "科森科技不应被判定为属于【烟草】板块")
        self.assertTrue(is_stock_matched_sector(ks_cat, "消费电子"),
                        "科森科技应匹配【消费电子】板块")

        # 3. 传统真正烟草板块个股 (如陕西金叶、顺灏股份)
        real_tobacco_1 = "烟草概念;包装印刷;陕西板块"
        real_tobacco_2 = "烟草;造纸印刷"
        self.assertTrue(is_stock_matched_sector(real_tobacco_1, "烟草"),
                        "含【烟草概念】标签的真实标的应匹配【烟草】")
        self.assertTrue(is_stock_matched_sector(real_tobacco_2, "烟草"),
                        "含【烟草】标签的真实标的应匹配【烟草】")

        # 4. 同义词扩展匹配测试 (例如 '共封装光学(CPO)' 与 'CPO')
        cpo_cat = "CPO概念;光通信;通信设备"
        self.assertTrue(is_stock_matched_sector(cpo_cat, "共封装光学(CPO)", synonyms=["CPO", "硅光", "光模块"]),
                        "含【CPO概念】标签的标的应通过同义词匹配【共封装光学(CPO)】")

    def test_08_periodic_market_volume_announcement_and_notifier(self):
        """测试 30 分钟定时大盘全市成交额播报文案与 AlertNotifier 统一通知体系集成"""
        from ats.alert_notifier import AlertNotifier, get_alert_notifier
        notifier = get_alert_notifier()
        self.assertIs(notifier, AlertNotifier.get_instance())

        # 1. 模拟盘中 11:30 上午收市时段数据
        summary_midday = {
            "sh_amt": 5120.5, "sh_vr": 0.88,
            "sz_amt": 6240.3, "sz_vr": 0.90,
            "cy_amt": 2810.0, "cy_vr": 0.92,
            "bj_amt": 120.0,  "bj_vr": 0.85,
            "total_amt": 11480.8,
            "diff_amt": -1840.5,
            "diff_str": "-1840.5亿",
            "diff_label": "较同期",
            "prev_same_amt": 13321.3,
            "proj_total_amt": 17662.8,
            "proj_total_str": "1.77万亿",
            "is_intraday": True,
            "plain_text": "全市: 11480.8亿 (较同期 -1840.5亿 | 虚拟 1.77万亿)"
        }

        # 测试 notify_market_volume 队列入队与文案
        with patch.object(notifier, '_speak_text') as mock_speak:
            notifier.clear_queue()
            notifier.notify_market_volume(summary_midday, parent=None)

            if mock_speak.called:
                spoken = mock_speak.call_args[0][0]
                self.assertIn("全市成交额", spoken)
                self.assertIn("较同期缩量1840.5亿元", spoken)
                self.assertIn("全天预估1.77万亿", spoken)

        # 2. 模拟 15:00 收盘时段播报
        summary_close = {
            "sh_amt": 7796.7, "sh_vr": 0.94,
            "sz_amt": 8674.8, "sz_vr": 0.93,
            "cy_amt": 3840.6, "cy_vr": 0.91,
            "bj_amt": 153.7,  "bj_vr": 0.90,
            "total_amt": 16625.2,
            "diff_amt": -2107.3,
            "diff_str": "-2107.3亿",
            "diff_label": "较昨",
            "prev_same_amt": 18732.5,
            "proj_total_amt": 16625.2,
            "proj_total_str": "1.66万亿",
            "is_intraday": False,
            "plain_text": "全市: 16625.2亿 (较昨 -2107.3亿)"
        }
        with patch.object(notifier, '_speak_text') as mock_speak:
            notifier.clear_queue()
            notifier.notify_market_volume(summary_close, parent=None)
            if mock_speak.called:
                spoken = mock_speak.call_args[0][0]
                self.assertIn("全市收盘总成交额", spoken)
                self.assertIn("较昨缩量2107.3亿元", spoken)

        # 3. 模拟 ATS 主窗口 _check_market_volume_announcement 定时触发判定
        from ats.ui.main_window import ATSMainWindow
        mock_win = MagicMock(spec=ATSMainWindow)
        mock_win._announced_market_volume_slots = set()

        # 绑定真实方法
        mock_win._check_market_volume_announcement = ATSMainWindow._check_market_volume_announcement.__get__(mock_win, ATSMainWindow)

        with patch("ats.alert_notifier.AlertNotifier.get_instance") as mock_get_inst:
            mock_inst = MagicMock()
            mock_get_inst.return_value = mock_inst
            with patch("ats.capital_dragon_engine.CapitalDragonEngine.get_instance") as mock_get_cde:
                mock_cde = MagicMock()
                mock_cde.get_market_indices_and_volume_summary.return_value = summary_midday
                mock_get_cde.return_value = mock_cde

                # 3.1 命中定时点：周一 10:00:00 -> 必须触发
                dt_1000 = datetime.datetime(2026, 9, 14, 10, 0, 0)
                with patch("JohnsonUtil.commonTips.get_work_day_status", return_value=True):
                    mock_win._check_market_volume_announcement(now_dt=dt_1000)
                    self.assertEqual(mock_inst.notify_market_volume.call_count, 1)

                    # 3.2 同一时间槽位防抖去重：再次在 10:00:15 调用 -> 绝不重复触发
                    dt_1000_15 = datetime.datetime(2026, 9, 14, 10, 0, 15)
                    mock_win._check_market_volume_announcement(now_dt=dt_1000_15)
                    self.assertEqual(mock_inst.notify_market_volume.call_count, 1)

                    # 3.3 非定时点：10:15:00 -> 绝不触发
                    dt_1015 = datetime.datetime(2026, 9, 14, 10, 15, 0)
                    mock_win._check_market_volume_announcement(now_dt=dt_1015)
                    self.assertEqual(mock_inst.notify_market_volume.call_count, 1)

                    # 3.4 命中下一个 30 分钟定时点：10:30:00 -> 触发第 2 次
                    dt_1030 = datetime.datetime(2026, 9, 14, 10, 30, 0)
                    mock_win._check_market_volume_announcement(now_dt=dt_1030)
                    self.assertEqual(mock_inst.notify_market_volume.call_count, 2)


if __name__ == "__main__":
    unittest.main()
