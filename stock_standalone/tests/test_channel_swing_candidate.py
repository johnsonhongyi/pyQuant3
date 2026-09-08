# -*- coding: utf-8 -*-
"""
tests/test_channel_swing_candidate.py
=============================================================================
全面测试【通道上涨与支撑线上的 MA20d 震荡企稳候选池核心引擎】(SSOT)
包含三大实战案例验证：
1. 法尔胜 (000890): 上升通道+支撑线(8.45)+MA20(8.21)上方企稳，偏离度+6.46%，通道有高度，走势有振幅，卖出后防丢筹码二次上车；
2. 中农联合 (003042): 支撑线(15.10)+MA20(14.31)企稳后次日加速冲板；
3. 爱尔眼科 (300015): 均线空头向下，跌破支撑线，日均振幅仅1.2%(织布死水)，一票否决剔除！
"""

import sys
import os
import unittest
import numpy as np
import pandas as pd

# 将 stock_standalone 根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.channel_swing_candidate_engine import ChannelSwingCandidateEngine
from ats.swing_tracker import SwingTracker
from ats.signal_ledger import SignalLedger


class TestChannelSwingCandidateSuite(unittest.TestCase):

    def setUp(self):
        self.engine = ChannelSwingCandidateEngine.get_instance()
        self.tracker = SwingTracker()
        self.ledger = SignalLedger()

    def test_case1_faersheng_reentry_guard(self):
        """测试实战案例 1: 法尔胜 (000890) 卖出后支撑线上企稳防丢失筹码二次上车"""
        # 法尔胜参数模拟: 现价 8.74, MA20 8.21 (偏离 +6.46%), 支撑线 8.45, 上轨 9.65
        row_faersheng = {
            "name": "法尔胜",
            "close": 8.74,
            "open": 8.65,
            "high": 8.85,
            "low": 8.52,
            "percent": 1.04,
            "ma20d": 8.21,
            "ma10d": 8.74,
            "ma5d": 8.68,
            "ch_supp_price": 8.45,
            "ch_slope_deg": 3.8,
            "upper": 9.65,
            "lower": 8.20,
            "lasth1d": 8.90,
            "lastl1d": 8.48,
            "lastp1d": 8.65,
            "lastp2d": 8.55,
            "lastp3d": 8.40,
        }

        # 1. 评估候选池引擎判定
        res = self.engine.evaluate_channel_swing_structure(
            code="000890",
            name="法尔胜",
            price=8.74,
            row=row_faersheng,
            is_traded_or_closed=True,  # 用户近期买入后卖出
            is_favorite=False
        )

        self.assertTrue(res["is_channel_up"], "法尔胜通道倾角与均线必须判定为通道向上")
        self.assertTrue(res["is_above_support"], "法尔胜现价 8.74 稳居支撑线 8.45 上方")
        self.assertTrue(res["is_reentry_candidate"], "曾卖出标的在支撑线上企稳必须触发二次上车候选")
        self.assertGreaterEqual(res["ch_height_pct"], 12.0, "通道高度充裕")
        self.assertGreaterEqual(res["amplitude_pct"], 3.5, "走势有振幅波动")
        self.assertGreaterEqual(res["score"], 80.0, "量化评分必须达到高分梯队")
        self.assertIn("二次上车", res["tag"])

        # 2. 状态机测试: 曾卖出 (STATE_CLOSED) 标的平滑跃迁至回踩企稳
        self.tracker.set_state("000890", SwingTracker.STATE_CLOSED)
        close_series = [8.20, 8.35, 8.55, 8.65, 8.74]
        ma20_series = [8.05, 8.10, 8.15, 8.18, 8.21]
        ma5_series = [8.40, 8.50, 8.58, 8.65, 8.68]

        new_state, dev_str, pos, reason = self.tracker.update_stock_state(
            code="000890",
            name="法尔胜",
            price=8.74,
            close_series=close_series,
            ma20_series=ma20_series,
            ma5_series=ma5_series,
            supp_price=res["supp_price"],
            ch_slope_deg=res["ch_slope_deg"],
            ch_height_pct=res["ch_height_pct"],
            amplitude_pct=res["amplitude_pct"],
            is_traded_or_closed=True,
            swing_tag=res["tag"]
        )

        self.assertEqual(new_state, SwingTracker.STATE_STABILIZED, "卖出标的在支撑线上企稳必须跃迁至回踩企稳")
        self.assertIn("二次上车", reason, "理由必须明确指出二次上车信号确认")
        self.assertEqual(pos, "20%", "建议仓位 20%")

        # 3. 信号账本准入测试: 打破狭隘的 5% 限制，成功进入账本并获提权
        entry = self.ledger.record_signal(
            code="000890",
            name="法尔胜",
            price=8.74,
            pct=1.04,
            deviation=res["ma20_dev"],  # +6.46%
            row=row_faersheng,
            signal_tag=res["tag"],
            ch_slope_deg=res["ch_slope_deg"],
            supp_price=res["supp_price"],
            ch_height_pct=res["ch_height_pct"],
            amplitude_pct=res["amplitude_pct"],
            is_channel_swing=True
        )

        self.assertIsNotNone(entry, "法尔胜虽然偏离度+6.46% > 5%，但属于支撑线企稳，绝不可被过滤！")
        self.assertGreaterEqual(entry.priority_score, 100.0, "完美通道支撑企稳标的获得大幅优先级提权")

    def test_case2_zhongnong_lianhe_acceleration(self):
        """测试实战案例 2: 中农联合 (003042) 支撑线上企稳后加速冲板起爆"""
        # 中农联合参数模拟: 支撑线 15.10, MA20 14.31, 现价 16.17 (大涨+6.8%), 上轨 17.65
        row_zhongnong = {
            "name": "中农联合",
            "close": 16.17,
            "open": 15.35,
            "high": 16.35,
            "low": 15.28,
            "percent": 6.80,
            "ma20d": 14.31,
            "ma10d": 14.75,
            "ma5d": 15.20,
            "ch_supp_price": 15.10,
            "ch_slope_deg": 4.5,
            "upper": 17.65,
            "lower": 13.80,
            "lastp1d": 15.14,
            "lasth1d": 15.40,
            "lastl1d": 15.05,
        }

        res = self.engine.evaluate_channel_swing_structure(
            code="003042",
            name="中农联合",
            price=16.17,
            row=row_zhongnong,
            is_traded_or_closed=False,
            is_favorite=False
        )

        self.assertTrue(res["is_channel_up"], "中农联合必须判定为通道向上")
        self.assertTrue(res["is_above_support"], "必须稳居支撑线 15.10 上方")
        self.assertTrue(res["is_accelerating"], "必须识别为支撑企稳后的主升加速冲板")
        self.assertIn("主升加速", res["tag"])
        self.assertGreaterEqual(res["score"], 90.0, "中农联合加速必须达到 90 分以上")

        # 状态机测试: 从回踩企稳跃迁至持股主升
        self.tracker.set_state("003042", SwingTracker.STATE_STABILIZED)
        close_series = [14.80, 15.00, 15.14, 16.17]
        ma20_series = [14.10, 14.20, 14.25, 14.31]
        ma5_series = [14.90, 15.05, 15.12, 15.20]

        new_state, dev_str, pos, reason = self.tracker.update_stock_state(
            code="003042",
            name="中农联合",
            price=16.17,
            close_series=close_series,
            ma20_series=ma20_series,
            ma5_series=ma5_series,
            supp_price=res["supp_price"],
            ch_slope_deg=res["ch_slope_deg"],
            ch_height_pct=res["ch_height_pct"],
            amplitude_pct=res["amplitude_pct"],
            is_traded_or_closed=False,
            swing_tag=res["tag"]
        )

        self.assertEqual(new_state, SwingTracker.STATE_HOLDING, "企稳加速冲板必须跃迁至持股主升")
        self.assertEqual(pos, "30%", "加速突破推荐仓位达到 30%")
        self.assertIn("起爆加速", reason)

    def test_case3_aier_eye_failure_case_rejection(self):
        """测试实战案例 3 (反面教材): 爱尔眼科 (300015) 均线空头下压、跌破支撑线、织布死水一票否决"""
        # 爱尔眼科参数模拟: 现价 8.15, MA20 8.44↓, MA10 8.33↓, 支撑线 8.25, 日振幅仅 1.1%
        row_aier = {
            "name": "爱尔眼科",
            "close": 8.15,
            "open": 8.18,
            "high": 8.20,
            "low": 8.12,
            "percent": -0.73,
            "ma20d": 8.44,
            "ma10d": 8.33,
            "ma250d": 10.32,
            "ch_supp_price": 8.25,
            "ch_slope_deg": -2.5,
            "upper": 8.48,
            "lower": 8.10,
            "lasth1d": 8.22,
            "lastl1d": 8.13,
            "lastp1d": 8.21,
        }

        res = self.engine.evaluate_channel_swing_structure(
            code="300015",
            name="爱尔眼科",
            price=8.15,
            row=row_aier,
            is_traded_or_closed=False,
            is_favorite=False
        )

        self.assertFalse(res["is_above_support"], "爱尔眼科跌破支撑线 8.25 元必须判定为 False")
        self.assertFalse(res["is_perfect_double"], "爱尔眼科绝非完美双结构")
        self.assertLessEqual(res["score"], 30.0, "爱尔眼科破位转弱评分必须处于极低分")
        self.assertIn("⚠️", res["tag"], "必须打上警告标签")

        # 状态机测试: 跌破支撑线必须触发平仓防御
        self.tracker.set_state("300015", SwingTracker.STATE_STABILIZED)
        close_series = [8.35, 8.28, 8.21, 8.15]
        ma20_series = [8.50, 8.48, 8.46, 8.44]
        ma5_series = [8.30, 8.26, 8.22, 8.18]

        new_state, dev_str, pos, reason = self.tracker.update_stock_state(
            code="300015",
            name="爱尔眼科",
            price=8.15,
            close_series=close_series,
            ma20_series=ma20_series,
            ma5_series=ma5_series,
            supp_price=res["supp_price"],
            ch_slope_deg=res["ch_slope_deg"],
            ch_height_pct=res["ch_height_pct"],
            amplitude_pct=res["amplitude_pct"],
            is_traded_or_closed=False,
            swing_tag=res["tag"]
        )

        self.assertEqual(new_state, SwingTracker.STATE_CLOSED, "跌破支撑线必须转为已平仓防守")
        self.assertEqual(pos, "0%", "平仓仓位 0%")
        self.assertIn("跌破支撑线", reason)

    def test_screen_channel_swing_candidates_universe(self):
        """测试全市场筛选池: 法尔胜与中农联合顺利入选，爱尔眼科被彻底剔除"""
        df_all = pd.DataFrame([
            {"code": "000890", "name": "法尔胜", "close": 8.74, "open": 8.65, "high": 8.85, "low": 8.52, "percent": 1.04, "ma20d": 8.21, "ma10d": 8.74, "ch_supp_price": 8.45, "ch_slope_deg": 3.8, "upper": 9.65, "lower": 8.20, "lasth1d": 8.90, "lastl1d": 8.48, "lastp1d": 8.65},
            {"code": "003042", "name": "中农联合", "close": 16.17, "open": 15.35, "high": 16.35, "low": 15.28, "percent": 6.80, "ma20d": 14.31, "ma10d": 14.75, "ch_supp_price": 15.10, "ch_slope_deg": 4.5, "upper": 17.65, "lower": 13.80, "lasth1d": 15.40, "lastl1d": 15.05, "lastp1d": 15.14},
            {"code": "300015", "name": "爱尔眼科", "close": 8.15, "open": 8.18, "high": 8.20, "low": 8.12, "percent": -0.73, "ma20d": 8.44, "ma10d": 8.33, "ch_supp_price": 8.25, "ch_slope_deg": -2.5, "upper": 8.48, "lower": 8.10, "lasth1d": 8.22, "lastl1d": 8.13, "lastp1d": 8.21},
            {"code": "600000", "name": "浦发银行", "close": 9.50, "open": 9.51, "high": 9.52, "low": 9.49, "percent": 0.10, "ma20d": 9.48, "ma10d": 9.49, "ch_supp_price": 9.45, "ch_slope_deg": 0.2, "upper": 9.60, "lower": 9.40, "lasth1d": 9.52, "lastl1d": 9.49, "lastp1d": 9.50}, # 织布机
        ]).set_index("code")

        trade_codes = {"000890"} # 曾交易法尔胜

        candidates = self.engine.screen_channel_swing_candidates(
            df_all=df_all,
            trade_history_codes=trade_codes,
            max_candidates=10
        )

        cand_codes = [c["code"] for c in candidates]
        self.assertIn("000890", cand_codes, "法尔胜必须成功入选候选池")
        self.assertIn("003042", cand_codes, "中农联合必须成功入选候选池")
        self.assertNotIn("300015", cand_codes, "爱尔眼科跌破支撑线必须坚决被剔除！")

        # 检查排序：加速标的与二次上车标的排在最前列
        top_codes = cand_codes[:2]
        self.assertTrue("003042" in top_codes and "000890" in top_codes, "中农联合与法尔胜稳居候选池前两名")


if __name__ == "__main__":
    unittest.main()
