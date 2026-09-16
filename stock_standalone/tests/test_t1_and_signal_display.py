# -*- coding: utf-8 -*-
"""
tests/test_t1_and_signal_display.py — T+1 交易制度与买卖点标记简略防重叠自动化测试套件
=============================================================================
验证目标：
1. 严格遵循 A 股 T+1 制度：当日买入的头寸在买入日（T 日）绝对不可卖出平仓；
2. 跨入次日（T+1 及之后）才解锁 8 层主动防守引擎离场评估；
3. 单日防重叠开仓约束：同一交易日内至多开仓 1 次，持仓未平绝不重叠开仓；
4. 回测数据末尾保护：若回测结束时仍在买入当日，维持开仓持有中状态（Open Position），绝不伪造虚假同日卖点；
5. SBC 画布买卖信号自适应简略显示与 2D 包围盒真实防碰撞避让。
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# 确保项目根目录位于 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, SBCChartCanvas


class TestT1StrategyAndSignalDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def _create_multi_day_bars(self) -> pd.DataFrame:
        """构造两个交易日（09-14 和 09-15）的多日分时数据，09-14 发生筑底放量突破"""
        rows = []
        # 09-14: 前 15 根横盘整理 (9.98~10.01)，第 16 根起放量突破至 10.75，盘中跌破均线
        for m in range(240):
            hh = 9 + (m + 30) // 60 if m < 120 else 13 + (m - 120) // 60
            mm = (m + 30) % 60 if m < 120 else (m - 120) % 60
            t_str = f"09-14 {hh:02d}:{mm:02d}"
            if m < 15:
                p = 10.00 + (m % 3 - 1) * 0.01
                vw = 10.00
                v = 1500.0
            elif m < 30:
                p = 10.00 + (m - 14) * 0.05  # 突破至 10.75
                vw = 10.05
                v = 3000.0
            elif m < 60:
                p = 10.75 - (m - 29) * 0.03  # 盘中破位下跌至 9.85 (若无 T+1 将在此同日平仓)
                vw = 10.10
                v = 800.0
            else:
                p = 10.00
                vw = 10.05
                v = 500.0

            rows.append({
                "time": t_str,
                "date": "2026-09-14",
                "open": p - 0.01,
                "close": p,
                "high": p + 0.02,
                "low": p - 0.02,
                "vwap": vw,
                "vol": v,
                "volume": v,
                "amount": p * v
            })

        # 09-15: 次日大幅回撤跌破 VWAP 触发主动防守离场
        for m in range(240):
            hh = 9 + (m + 30) // 60 if m < 120 else 13 + (m - 120) // 60
            mm = (m + 30) % 60 if m < 120 else (m - 120) % 60
            t_str = f"09-15 {hh:02d}:{mm:02d}"
            p = 9.80 - m * 0.01  # 持续回落跌破 VWAP
            vw = 10.00
            v = 600.0

            rows.append({
                "time": t_str,
                "date": "2026-09-15",
                "open": p - 0.01,
                "close": p,
                "high": p + 0.02,
                "low": p - 0.02,
                "vwap": vw,
                "vol": v,
                "volume": v,
                "amount": p * v
            })

        df = pd.DataFrame(rows).set_index("time")
        return df

    def test_t1_lock_on_entry_day_and_exit_on_next_day(self):
        """验证 T+1 核心规则：买入当日绝对不可卖出平仓，必须次日才能平仓"""
        df_multi = self._create_multi_day_bars()
        dialog = SBCIntradayChartDialog(code="688635")

        # 运行自动策略评估
        signals = dialog._eval_vwap_proactive_strategy(df_multi, period_mode="2d")
        self.assertTrue(len(signals) > 0, "应生成策略信号")

        buy_sigs = [s for s in signals if s.get("action") == "buy"]
        sell_sigs = [s for s in signals if s.get("action") == "sell"]

        self.assertTrue(len(buy_sigs) >= 1, "应至少包含 1 笔买入信号")

        # 1. 验证买入日期为 09-14
        first_buy = buy_sigs[0]
        self.assertEqual(first_buy.get("date"), "2026-09-14", "第一笔买入应在 09-14 发生")

        # 2. 验证 09-14 当天绝对没有触发任何卖出 (严格 T+1 锁定)
        sells_on_entry_day = [s for s in sell_sigs if s.get("date") == "2026-09-14"]
        self.assertEqual(len(sells_on_entry_day), 0, "【T+1 规则断言】买入当日 09-14 绝对不可产生卖出平仓信号！")

        # 3. 验证平仓发生在次日 09-15
        if sell_sigs:
            first_sell = sell_sigs[0]
            self.assertEqual(first_sell.get("date"), "2026-09-15", "【T+1 规则断言】卖出平仓必须跨入次日 09-15 才能执行！")
            self.assertGreaterEqual(first_sell.get("holding_days", 0), 1, "持有天数应大于等于 1 天")
            self.assertEqual(first_buy.get("holding_days"), 1, "买入信号应正确配对持有天数")

        # 4. 验证 09-14 当天没有重复频繁开仓 (单日限 1 次)
        buys_on_entry_day = [s for s in buy_sigs if s.get("date") == "2026-09-14"]
        self.assertEqual(len(buys_on_entry_day), 1, "09-14 当天至多开仓 1 次，严禁同一天频繁重叠开仓！")

    def test_single_day_holding_at_end_of_data(self):
        """验证单日分时下当天买入后，数据结束时保持开仓状态，绝不伪造虚假同日平仓点"""
        # 仅取 09-14 单日分时
        df_single = self._create_multi_day_bars().iloc[:240].copy()
        dialog = SBCIntradayChartDialog(code="688635")

        signals = dialog._eval_vwap_proactive_strategy(df_single, period_mode="1m")
        buy_sigs = [s for s in signals if s.get("action") == "buy"]
        sell_sigs = [s for s in signals if s.get("action") == "sell"]

        self.assertEqual(len(buy_sigs), 1, "单日应触发 1 次买入")
        self.assertEqual(len(sell_sigs), 0, "【T+1 规则断言】单日未跨日，数据末尾绝对不可伪造卖出平仓！")
        self.assertEqual(buy_sigs[0].get("holding_status"), "open_holding", "买入信号应保持开仓锁仓状态")

    def test_canvas_compact_badge_and_hit_boxes(self):
        """验证 SBC 画布买卖信号简略显示与 2D 包围盒碰撞避让机制"""
        canvas = SBCChartCanvas(None)
        canvas.resize(1000, 600)

        df_multi = self._create_multi_day_bars()
        canvas.set_data(
            df_intraday=df_multi,
            open_p=10.0,
            vwap_p=10.05,
            high_p=10.75,
            low_p=9.80,
            sell_min=10.50,
            sell_max=10.80,
            signals=[
                {"trade_id": 0, "action": "buy", "price": 10.15, "time": "09-14 09:45", "timestamp": "09-14 09:45"},
                {"trade_id": 0, "action": "sell", "price": 10.60, "time": "09-15 10:15", "timestamp": "09-15 10:15", "pnl_pct": 4.43},
                # 紧密相邻的第二个假想信号测试碰撞
                {"trade_id": 1, "action": "buy", "price": 10.20, "time": "09-14 09:46", "timestamp": "09-14 09:46"},
            ],
            period_mode="2d"
        )

        # 显式渲染到 pixmap 触发 paintEvent
        pixmap = QPixmap(1000, 600)
        canvas.render(pixmap)

        hit_boxes = canvas._signal_hit_boxes
        self.assertTrue(len(hit_boxes) >= 2, "应成功为信号注册 hit_boxes")

        # 验证相邻两个信号的矩形不会完全重合
        if len(hit_boxes) >= 2:
            r1 = hit_boxes[0]["rect"]
            r2 = hit_boxes[1]["rect"]
            self.assertFalse(r1 == r2, "两个相邻信号矩形坐标必须错开，不可完全重合")


if __name__ == "__main__":
    unittest.main()
