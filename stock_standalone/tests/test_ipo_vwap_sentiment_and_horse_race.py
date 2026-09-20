# -*- coding: utf-8 -*-
"""
tests/test_ipo_vwap_sentiment_and_horse_race.py
------------------------------------------------
专项自动化测试：
新股次新股全市场情绪感知、早盘基石价启动赛马与集中交易调度中心终极闭环
1. IPOMarketSentimentEngine 大盘地量与新股梯队情绪判定；
2. 早盘 9:15-10:00 时间切片、开盘基石价与拔地而起斜率计算；
3. 神股 601091 沈鼓集团极端高潮天量滞涨平仓识别 (🚨 疯狂平仓)；
4. 首发上市首日贴线惜售黄金买点 (🔥 首发吸筹)；
5. 买错跌破 VWAP 立即斩仓出局铁律 (⛔ 破位止损点)；
6. 逐日赛马冒泡排位算法 (🥇 领头羊 / 🥈 梯队前锋)；
7. IPOTradingCenter 汇交全池报告、横向比对(“山外有山”)、动态仓位与指令生成。
"""

import os
import sys
import unittest
import time
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

# 确保路径
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from ats.strategy.ipo_market_sentiment_engine import IPOMarketSentimentEngine, MarketSentimentSnapshot
from ats.strategy.ipo_vwap_detector_engine import (
    IPOVWAPDetectorEngine, VWAPDetectorSignal, batch_evaluate_horse_race_ranking
)
from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOTradingPosition, IPOOrderDirective


class TestIPOVWAPSentimentAndHorseRace(unittest.TestCase):
    """新股情绪感知、赛马动能与统一交易调度中心自动化测试"""

    def setUp(self):
        self.sentiment_engine = IPOMarketSentimentEngine.get_instance()
        self.detector_engine = IPOVWAPDetectorEngine.get_instance()
        self.trading_center = IPOTradingCenter.get_instance()

    def test_market_sentiment_low_volume_and_heat_stage(self):
        """【测试】验证大盘绝望地量判定与新股梯队升温周期计算"""
        # 1. 模拟大盘绝望地量 (量比 0.75)
        mock_sh_snap = {"amount": 250000000000.0, "vol_ratio": 0.75}
        with patch.object(self.sentiment_engine.fetcher, "fetch_stock_snapshot", return_value=mock_sh_snap):
            snap = self.sentiment_engine.get_market_sentiment(ipo_signals=[], force_refresh=True)
            self.assertEqual(snap.index_phase, "绝望地量")
            self.assertIn("缩量至地量低谷", snap.index_desc)

        # 2. 模拟新股样本池 80% 红盘且站上 VWAP，进入梯队升温共振
        mock_signals = [
            VWAPDetectorSignal(code="601091", name="沈鼓集团", price=57.77, change_pct=177.0, vwap=19.64, is_above_vwap=True),
            VWAPDetectorSignal(code="920298", name="腾信精密", price=90.48, change_pct=40.7, vwap=67.35, is_above_vwap=True),
            VWAPDetectorSignal(code="688837", name="信诺维", price=55.60, change_pct=34.4, vwap=45.16, is_above_vwap=True),
            VWAPDetectorSignal(code="301689", name="电科思仪", price=63.00, change_pct=17.8, vwap=51.40, is_above_vwap=True),
            VWAPDetectorSignal(code="301707", name="晨芯股份", price=75.40, change_pct=7.1, vwap=71.38, is_above_vwap=True),
        ]
        with patch.object(self.sentiment_engine.fetcher, "fetch_stock_snapshot", return_value={"vol_ratio": 1.5}):
            snap = self.sentiment_engine.get_market_sentiment(ipo_signals=mock_signals, force_refresh=True)
            self.assertEqual(snap.index_phase, "爆发共振")
            self.assertEqual(snap.red_ratio, 100.0)
            self.assertEqual(snap.vwap_hold_ratio, 100.0)
            self.assertEqual(snap.heat_stage, "🌋 狂热高潮")

    def test_market_context_snapshot_marks_climax_and_round_trips(self):
        signals = [
            VWAPDetectorSignal(
                code="688001", name="context", price=10.0, change_pct=8.0,
                vwap=9.5, is_above_vwap=True,
            )
        ]
        with patch.object(
            self.sentiment_engine.fetcher,
            "fetch_stock_snapshot",
            return_value={"amount": 300000000000.0, "vol_ratio": 2.3},
        ):
            snap = self.sentiment_engine.get_market_sentiment(signals, force_refresh=True)

        self.assertEqual(snap.index_phase, "天量高潮")
        self.assertEqual(snap.risk_mode, "CAUTION")
        self.assertEqual(snap.position_multiplier, 0.25)
        self.assertEqual(len(snap.snapshot_id), 16)
        restored = MarketSentimentSnapshot.from_dict(snap.to_dict())
        self.assertEqual(restored.to_dict(), snap.to_dict())

    def test_market_context_snapshot_degrades_when_index_source_is_missing(self):
        with patch.object(
            self.sentiment_engine.fetcher,
            "fetch_stock_snapshot",
            return_value={},
        ):
            snap = self.sentiment_engine.get_market_sentiment([], force_refresh=True)

        self.assertEqual(snap.data_quality, "DEGRADED")
        self.assertEqual(snap.risk_mode, "CAUTION")
        self.assertEqual(snap.position_multiplier, 0.5)
        self.assertIn("INDEX_SNAPSHOT_UNAVAILABLE", snap.source_errors)

    def test_market_context_risk_budget_limits_generated_buy(self):
        center = IPOTradingCenter(total_capital=1000000.0)
        signal = VWAPDetectorSignal(
            code="688002", name="budget", price=100.0, change_pct=3.0,
            vwap=98.0, is_above_vwap=True, signal_type="IPO_FIRST_BUY",
            is_ipo_first_day=True, horse_race_rank=1, horse_race_score=95.0,
            launch_time_str="09:31", launch_slope_deg=45.0,
        )
        center.submit_stock_perception_report(signal)
        context = MarketSentimentSnapshot(
            heat_stage="🔥 梯队升温", index_phase="温和放量",
            risk_mode="CAUTION", position_multiplier=0.5,
        ).finalize()
        with patch.object(center.sentiment_engine, "get_market_sentiment", return_value=context):
            orders = center.evaluate_fleet_and_generate_orders()

        buys = [order for order in orders if order.action == "BUY"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0].size_pct, 17.5)
        self.assertEqual(center._last_market_context.snapshot_id, context.snapshot_id)

        blocked = MarketSentimentSnapshot(
            heat_stage="❄️ 冰点极寒", risk_mode="BLOCK_NEW_BUYS",
            position_multiplier=0.0,
        ).finalize()
        center._pending_directives.clear()
        with patch.object(center.sentiment_engine, "get_market_sentiment", return_value=blocked):
            self.assertEqual(center.evaluate_fleet_and_generate_orders(), [])

    def test_tide_position_cap_is_final_budget_and_visible_in_summary(self):
        center = IPOTradingCenter(total_capital=1000000.0)
        signal = VWAPDetectorSignal(
            code="688003", name="tide-budget", price=100.0, change_pct=2.0,
            vwap=99.0, is_above_vwap=True, signal_type="IPO_FIRST_BUY",
            is_ipo_first_day=True, horse_race_rank=1, horse_race_score=96.0,
            launch_time_str="09:31", launch_slope_deg=45.0,
        )
        center.submit_stock_perception_report(signal)
        context = MarketSentimentSnapshot(
            heat_stage="🔥 梯队升温", index_phase="温和放量",
            tide_state="T5_ICE", tide_confidence=0.9,
            tide_position_cap_pct=5.0, tide_action="PROBE_ONLY",
            tide_transition_reasons=["selling_pressure_decelerating"],
        ).finalize()
        with patch.object(center.sentiment_engine, "get_market_sentiment", return_value=context):
            orders = center.evaluate_fleet_and_generate_orders()

        buys = [order for order in orders if order.action == "BUY"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0].size_pct, 5.0)
        summary = center.get_fleet_summary()
        self.assertEqual(summary["tide_state"], "T5_ICE")
        self.assertEqual(summary["tide_position_cap_pct"], 5.0)
        self.assertEqual(summary["tide_action"], "PROBE_ONLY")

    def test_shengu_extreme_climax_exit_detection(self):
        """【测试】神股 601091 沈鼓集团：暴涨至 82.59 天量滞涨跳水精准触发【🚨 疯狂平仓】"""
        # 构造分时：从 11.9 暴拉至 82.59，随后回落至 57.77，偏离 VWAP 达 194%
        rows = []
        d = "2026-09-18"
        for m in range(40):
            # 冲顶阶段
            p = 11.9 + m * 1.76  # 最高达 82.59
            rows.append({
                "time": f"{d} 09:{30+m:02d}",
                "date": d,
                "open": 11.9,
                "close": p,
                "high": 82.59 if m == 39 else p,
                "low": 11.9,
                "price": p,
                "vwap": 19.64,
                "amount": 50000000,
                "volume": 200000
            })
        # 高位砸盘回落到 57.77
        rows.append({
            "time": f"{d} 10:15",
            "date": d,
            "open": 82.59,
            "close": 57.77,
            "high": 82.59,
            "low": 57.77,
            "price": 57.77,
            "vwap": 19.64,
            "amount": 80000000,
            "volume": 300000
        })

        mock_df = pd.DataFrame(rows)
        with patch.object(self.detector_engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.detector_engine.fetcher, "fetch_kline_bars", return_value=pd.DataFrame()):
            sig = self.detector_engine.analyze_stock("601091", force_refresh=True)

            self.assertTrue(sig.is_climax_exit)
            self.assertEqual(sig.signal_type, "CLIMAX_EXIT")
            self.assertEqual(sig.signal_level, "🚨 疯狂平仓")
            self.assertIn("极端高潮放量", sig.structure_tag)
            self.assertIn("坚决平仓保利", sig.signal_desc)

    def test_ipo_first_day_adhesion_buy_detection(self):
        """【测试】验证上市首日贴线惜售吸筹模式精准打标【🔥 首发吸筹】"""
        rows = []
        d = "2026-09-17"
        # 首日 11.0 附近微幅爬升至 11.8，VWAP=10.9，回踩丝毫不碰 VWAP
        for m in range(30):
            p = 11.0 + m * 0.02
            rows.append({
                "time": f"{d} 09:{30+m:02d}",
                "date": d,
                "open": 11.0,
                "close": p,
                "high": p + 0.05,
                "low": 11.0,
                "price": p,
                "vwap": 10.9,
                "amount": 2000000,
                "volume": 150000
            })
        mock_df = pd.DataFrame(rows)
        mock_dict = {"601091": {"name": "沈鼓集团", "listing_date": "2026-09-17"}}

        with patch.object(self.detector_engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.detector_engine.fetcher, "fetch_kline_bars", return_value=pd.DataFrame()), \
             patch("time.strftime", return_value="2026-09-17"), \
             patch("ats.new_stock_fetcher.NewStockFetcher.get_instance") as mock_fetcher_cls:
            mock_inst = MagicMock()
            mock_inst._cached_ipo_dict = mock_dict
            mock_fetcher_cls.return_value = mock_inst

            sig = self.detector_engine.analyze_stock("601091", force_refresh=True)

            self.assertTrue(sig.is_ipo_first_day)
            self.assertTrue(sig.is_above_vwap)
            self.assertEqual(sig.signal_type, "IPO_FIRST_BUY")
            self.assertEqual(sig.signal_level, "🔥 首发吸筹")
            self.assertIn("首日贴线惜售", sig.structure_tag)

    def test_broken_vwap_strict_exit_discipline(self):
        """【测试】铁律风控：跌破 VWAP 0.6% 坚决触发【⛔ 破位止损点】，买错就出局"""
        rows = []
        d = "2026-09-18"
        # 现价 48.5，VWAP=50.0，跌破 3%
        for m in range(20):
            p = 50.0 - m * 0.1
            rows.append({
                "time": f"{d} 09:{30+m:02d}",
                "date": d,
                "open": 50.0,
                "close": p,
                "high": 50.0,
                "low": p - 0.05,
                "price": p,
                "vwap": 50.0,
                "amount": 1000000,
                "volume": 20000
            })
        mock_df = pd.DataFrame(rows)
        with patch.object(self.detector_engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.detector_engine.fetcher, "fetch_kline_bars", return_value=pd.DataFrame()):
            sig = self.detector_engine.analyze_stock("920065", force_refresh=True)

            self.assertFalse(sig.is_above_vwap)
            self.assertEqual(sig.signal_type, "WEAK_EXIT")
            self.assertEqual(sig.signal_level, "⛔ 破位止损点")
            self.assertIn("买错坚决止损出局", sig.signal_desc)

    def test_horse_race_ranking_and_bubble_up(self):
        """【测试】逐日赛马冒泡排位算法：早起爆+大斜率+高站稳率标的自动置顶 🥇 领头羊"""
        sig1 = VWAPDetectorSignal(
            code="601091", name="沈鼓集团", price=25.0, vwap=20.0, is_above_vwap=True,
            launch_time_str="09:33", launch_slope_deg=58.0, vwap_adhesion_ratio=95.0, sbc_activity_pct=326.5
        )
        sig2 = VWAPDetectorSignal(
            code="920298", name="腾信精密", price=90.0, vwap=70.0, is_above_vwap=True,
            launch_time_str="09:42", launch_slope_deg=42.0, vwap_adhesion_ratio=88.0, sbc_activity_pct=210.0
        )
        sig3 = VWAPDetectorSignal(
            code="001232", name="跟风标的", price=50.0, vwap=48.0, is_above_vwap=True,
            launch_time_str="10:45", launch_slope_deg=15.0, vwap_adhesion_ratio=60.0, sbc_activity_pct=35.0
        )
        sig4 = VWAPDetectorSignal(
            code="920065", name="破位标的", price=32.0, vwap=35.0, is_above_vwap=False, vwap_diff_pct=-8.5
        )

        ranked = batch_evaluate_horse_race_ranking([sig3, sig4, sig1, sig2])

        # 验证冒泡置顶: sig1 凭借 09:33 极速拔起与 58° 爆量斜率夺得 🥇 领头羊
        self.assertEqual(ranked[0].code, "601091")
        self.assertEqual(ranked[0].horse_race_tier, "🥇 领头羊")
        self.assertEqual(ranked[0].horse_race_rank, 1)
        self.assertGreaterEqual(ranked[0].horse_race_score, 90.0)

        # sig2 为 🥈 梯队前锋
        self.assertEqual(ranked[1].code, "920298")
        self.assertEqual(ranked[1].horse_race_tier, "🥈 梯队前锋")

        # sig3 10:45 启动被降级为 ⏱️ 迟滞跟风
        self.assertIn("迟滞跟风", ranked[2].horse_race_tier)

        # sig4 破位被拦截为 ⛔ 破位出局
        self.assertEqual(ranked[3].horse_race_tier, "⛔ 破位出局")

    def test_ipo_trading_center_fleet_coordination_and_orders(self):
        """【测试】验证 IPOTradingCenter 全池汇交、破除各管一摊、输出精准买卖指令"""
        tc = IPOTradingCenter(total_capital=1000000.0)

        # 1. 提交 4 只股票报告
        s_leader = VWAPDetectorSignal(
            code="601091", name="沈鼓集团", price=25.0, vwap=20.0, is_above_vwap=True,
            signal_type="BREAKOUT", launch_time_str="09:33", launch_slope_deg=55.0,
            vwap_adhesion_ratio=95.0, sbc_activity_pct=320.0
        )
        s_weak = VWAPDetectorSignal(
            code="920065", name="千岸科技", price=32.0, vwap=35.0, is_above_vwap=False,
            vwap_diff_pct=-8.5, signal_type="WEAK_EXIT"
        )
        s_first = VWAPDetectorSignal(
            code="688837", name="信诺维", price=45.0, vwap=44.0, is_above_vwap=True,
            signal_type="IPO_FIRST_BUY", is_ipo_first_day=True, vwap_diff_pct=2.2, vwap_adhesion_ratio=90.0
        )

        tc.submit_stock_perception_report(s_leader)
        tc.submit_stock_perception_report(s_weak)
        tc.submit_stock_perception_report(s_first)

        # 假设当前持有千岸科技 2000 股 (买错破位状态)
        tc.record_order_execution(IPOOrderDirective(
            action="BUY", code="920065", name="千岸科技", price=34.0, shares=2000, size_pct=6.8
        ))
        self.assertEqual(tc._positions["920065"].shares, 2000)

        # 2. 全局裁决生成订单
        with patch.object(tc.sentiment_engine, "get_market_sentiment") as mock_sent:
            mock_sent.return_value = MarketSentimentSnapshot(heat_stage="🔥 梯队升温", index_phase="温和放量")
            orders = tc.evaluate_fleet_and_generate_orders()

            # 必须产出两类关键指令：
            # A: 针对 920065 千岸科技发出 SELL 破位立斩清仓指令
            sell_orders = [o for o in orders if o.action == "SELL" and o.code == "920065"]
            self.assertEqual(len(sell_orders), 1)
            self.assertIn("破位止损出局", sell_orders[0].reason)
            self.assertEqual(sell_orders[0].shares, 2000)

            # B: 针对 601091 领头羊与 688837 首发吸筹发出 BUY 进攻开仓指令 (分配 35% 顶级仓位)
            buy_orders = [o for o in orders if o.action == "BUY"]
            self.assertGreaterEqual(len(buy_orders), 1)
            top_buy = buy_orders[0]
            self.assertEqual(top_buy.size_pct, 35.0)
            self.assertGreaterEqual(top_buy.shares, 100)

            # 3. 验证汇总概览
            summary = tc.get_fleet_summary()
            self.assertEqual(summary["holding_count"], 1)
            self.assertIn("沈鼓集团", summary["top_leader_name"])

    def test_continuous_force_refresh_no_crash_and_no_revision_inflation(self):
        """【回归测试】连续强制刷新不抛异常且不增加虚假交易日/纠错次数"""
        mock_signals = [
            VWAPDetectorSignal(code="601091", name="沈鼓集团", price=57.77, change_pct=177.0, vwap=19.64, is_above_vwap=True),
            VWAPDetectorSignal(code="920298", name="腾信精密", price=90.48, change_pct=40.7, vwap=67.35, is_above_vwap=True),
            VWAPDetectorSignal(code="688837", name="信诺维", price=55.60, change_pct=34.4, vwap=45.16, is_above_vwap=True),
            VWAPDetectorSignal(code="301689", name="电科思仪", price=63.00, change_pct=17.8, vwap=51.40, is_above_vwap=True),
            VWAPDetectorSignal(code="301707", name="晨芯股份", price=75.40, change_pct=7.1, vwap=71.38, is_above_vwap=True),
        ]
        self.sentiment_engine.reset()
        initial_revisions = None
        for i in range(25):
            with patch.object(self.sentiment_engine.fetcher, "fetch_stock_snapshot", return_value={"vol_ratio": 1.5}):
                snap = self.sentiment_engine.get_market_sentiment(ipo_signals=mock_signals, force_refresh=True)
                if initial_revisions is None:
                    initial_revisions = snap.tide_revision_count
                self.assertEqual(snap.tide_revision_count, initial_revisions)
                self.assertIsNotNone(snap.tide_state)

    def test_clock_rollback_handled_gracefully(self):
        """【回归测试】Windows时钟回退或NTP对时产生非递增时点，适配层保证严格递增微秒不崩溃"""
        self.sentiment_engine.reset()
        now = time.time()
        # 第一次调用：正常时点
        snap1 = self.sentiment_engine.get_market_sentiment(ipo_signals=[], force_refresh=True, current_time=now)
        # 第二次调用：模拟时钟倒退 10 秒
        snap2 = self.sentiment_engine.get_market_sentiment(ipo_signals=[], force_refresh=True, current_time=now - 10.0)
        self.assertIsNotNone(snap2)
        self.assertEqual(snap2.tide_state, "T0_INSUFFICIENT")

    def test_explicit_historical_replay_point_in_time_and_no_future_leakage(self):
        """【回归测试】显式历史回放时点严格保持，不跨日推进，不向后泄漏未来数据"""
        self.sentiment_engine.reset()
        # 1. 显式时点 2026-09-15 15:00:00
        snap1 = self.sentiment_engine.get_market_sentiment(
            ipo_signals=[], force_refresh=True, as_of="2026-09-15 15:00:00"
        )
        self.assertEqual(snap1.update_time, "15:00:00")
        self.assertEqual(self.sentiment_engine._last_tide_dt.date().isoformat(), "2026-09-15")

        # 2. 显式回放回溯到历史时点 2026-09-14 10:00:00：绝不能被改写为 2026-09-15 之后
        snap2 = self.sentiment_engine.get_market_sentiment(
            ipo_signals=[], force_refresh=True, as_of="2026-09-14 10:00:00"
        )
        self.assertEqual(snap2.update_time, "10:00:00")
        self.assertEqual(self.sentiment_engine._last_tide_dt.date().isoformat(), "2026-09-14")
        self.assertEqual(self.sentiment_engine._last_tide_dt.hour, 10)
        self.assertEqual(self.sentiment_engine._last_tide_dt.microsecond, 0)

        # 3. 显式回放相同历史时点 2026-09-14 10:00:00 重复查询：严格保持显式历史时点，绝不得推进 1 微秒改写至未来
        snap3 = self.sentiment_engine.get_market_sentiment(
            ipo_signals=[], force_refresh=True, as_of="2026-09-14 10:00:00"
        )
        self.assertEqual(snap3.update_time, "10:00:00")
        self.assertEqual(self.sentiment_engine._last_tide_dt.microsecond, 0, "显式历史时点重复请求绝不得推进1微秒！")
        self.assertEqual(snap3.tide_state, snap2.tide_state)

    def test_midnight_boundary_guard_prevents_fake_trading_day_and_revision_inflation(self):
        """【回归测试】日终午夜边界高频刷新不跨交易日推进，不生成虚假交易日与纠错通胀"""
        self.sentiment_engine.reset()
        from datetime import datetime as pydt
        dt_end = pydt(2026, 9, 15, 23, 59, 59, 999999)
        # 初始化在当日最后一微秒
        snap1 = self.sentiment_engine.get_market_sentiment(
            ipo_signals=[], force_refresh=True, current_time=dt_end
        )
        initial_revisions = snap1.tide_revision_count
        # 相同日期内再次调用，不得跨入 2026-09-16
        snap2 = self.sentiment_engine.get_market_sentiment(
            ipo_signals=[], force_refresh=True, current_time=dt_end
        )
        self.assertIsNotNone(snap2)
        self.assertEqual(snap2.tide_revision_count, initial_revisions)
        self.assertEqual(self.sentiment_engine._last_tide_dt.date().isoformat(), "2026-09-15")


if __name__ == "__main__":
    unittest.main()

