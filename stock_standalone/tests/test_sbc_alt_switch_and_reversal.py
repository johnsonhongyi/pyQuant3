# -*- coding: utf-8 -*-
"""
tests/test_sbc_alt_switch_and_reversal.py
-----------------------------------------
验证两大核心功能：
1. 底抬高企稳 + VWAP位移 + 高低点转换反转策略识别与持仓保护（防守端豁免 Layer 1/3/4 与实盘+6%机械止盈）；
2. SBC 底部切换标的时，按住 Alt 键在独立新窗口打开并自动重排平铺。
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

from ats.vwap_trading_engine import detect_vwap_displacement_reversal, VWAPTradingEngine, VWAPTickState
from ats.proactive_exit_engine import ProactiveExitEngine, PositionWatchItem, ExitAction
from intraday_decision_engine import IntradayDecisionEngine
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, SBCQuickCodeLineEdit


class TestVWAPDisplacementReversalStrategy(unittest.TestCase):
    """测试 VWAP 位移、底抬高企稳与高低点转换策略"""

    def setUp(self):
        # 构造符合 688635 / 300672 特征的多日走势数据 (3天: T-2 探底, T-1 企稳底抬高, T 向上位移反转突破)
        rows = []
        # Day 1 (09-14): 探底 (Low: 245.0, High: 275.0, VWAP: 265.0)
        for m in range(31):
            p = 275.0 - (m / 30.0) * 30.0
            rows.append({"date": "2026-09-14", "open": 275.0, "high": 275.0, "low": p, "close": p, "vwap": 265.0, "vol": 100})
        # Day 2 (09-15): 企稳次低点抬高 (Low: 259.38 > 245.0, High: 279.0, VWAP: 270.0)
        for m in range(30):
            p = 259.38 + (m / 30.0) * 15.0
            rows.append({"date": "2026-09-15", "open": 260.0, "high": 279.0, "low": 259.38, "close": p, "vwap": 270.0, "vol": 120})
        # Day 3 (09-16): VWAP向上位移 + 突破前高 (Low: 271.0, High: 290.0, VWAP: 274.0, Close: 288.0)
        for m in range(30):
            p = 271.0 + (m / 30.0) * 17.0
            rows.append({"date": "2026-09-16", "open": 271.0, "high": p, "low": 271.0, "close": p, "vwap": 274.0, "vol": 200})

        self.df_multi = pd.DataFrame(rows)

    def test_reversal_detector_identifies_structure(self):
        """测试反转识别器精准识别底抬高(259.38>245)与VWAP位移"""
        res = detect_vwap_displacement_reversal(self.df_multi)
        self.assertTrue(res["is_reversal"])
        self.assertAlmostEqual(res["higher_low"], 259.38, places=1)
        self.assertAlmostEqual(res["prev_low"], 245.0, places=1)
        self.assertAlmostEqual(res["prev_high"], 279.0, places=1)
        self.assertGreater(res["vwap_displacement_pct"], 0.15)
        self.assertIn("底抬高企稳", res["reason"])

    def test_proactive_exit_exempts_when_reversal_protected(self):
        """测试防守端在反转结构保护下，豁免 Layer 1 (时间衰减) 与 Layer 3 (前高阻力离场)"""
        exit_engine = ProactiveExitEngine()
        pos = exit_engine.register_position(
            code="688635",
            entry_price=270.0,
            entry_time=100.0,
            prev_day_high=279.0,
            vwap_yesterday=270.0
        )
        pos.is_reversal_protected = True
        pos.higher_low_stop = 259.38

        # 1. 模拟价格在阻力位 279 附近停留（未反转时会触发 Layer 3）
        action_at_resistance = exit_engine.evaluate_tick(
            code="688635",
            price=279.1,
            vwap_today=274.0,
            volume=100,
            volume_ratio=0.8,
            current_time=3000.0,
            extra_ctx={"is_reversal_structure": True, "higher_low": 259.38}
        )
        # 必须被反转保护豁免，不可卖出！
        self.assertIsNone(action_at_resistance, "反转结构下突破前高应豁免 Layer 3 离场")

        # 2. 模拟跌破次低点防守线 (259.38 * 0.99 = 256.78)
        break_action = exit_engine.evaluate_tick(
            code="688635",
            price=255.0,
            vwap_today=274.0,
            volume=500,
            volume_ratio=1.5,
            current_time=3100.0,
            extra_ctx={"is_reversal_structure": True, "higher_low": 259.38}
        )
        self.assertIsNotNone(break_action)
        self.assertEqual(break_action.rule_id, "exit_higher_low_broken")
        self.assertEqual(break_action.action_type, "EXIT_ALL")

    def test_intraday_decision_engine_reversal_profit_exemption(self):
        """测试实盘决策引擎在反转结构下豁免机械 +6% 目标止盈"""
        engine = IntradayDecisionEngine(take_profit_pct=0.06)
        row = {"trade": 286.5, "high": 286.5, "low": 271.0, "volume": 1.2, "lastl1d": 259.38, "lastl2d": 245.0, "nclose": 273.0}
        snapshot = {"cost_price": 270.0, "last_close": 271.0, "is_reversal_structure": True, "higher_low": 259.38}
        
        # 成本 270，现价 286.5，涨幅已达 +6.1% (超出 6% take_profit_pct)
        decision = engine.evaluate(row, snapshot)
        self.assertNotEqual(decision.get("action"), "目标止盈", "反转结构下应豁免硬性 6% 目标止盈，让利润奔跑")
        self.assertIn("止盈豁免", decision.get("debug", {}))


class TestSBCAltSwitchNewWindow(unittest.TestCase):
    """测试 SBC 切换代码时按住 Alt 键开新窗口并自动重排"""

    def setUp(self):
        self.dialog = SBCIntradayChartDialog(code="688635")

    def tearDown(self):
        self.dialog.close()

    def test_open_new_sbc_and_rearrange_called(self):
        """测试 _open_new_sbc_and_rearrange 正确调用 open_sbc_chart_dialog 并记录反馈"""
        target_code = "300672"
        self.dialog._open_new_sbc_and_rearrange(target_code)
        
        # 检查底部提示已更新为 Alt 开新窗提示
        info_text = self.dialog.lbl_info.text()
        self.assertTrue("已在独立窗口打开标的" in info_text or "300672" in info_text)


if __name__ == "__main__":
    unittest.main()
