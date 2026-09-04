# -*- coding: utf-8 -*-
"""
tests/test_pullback_reversal_and_reentry_suite.py — 强势异动回调弱转强起爆、割肉回踩主升回补与板块ETF趋势过滤专项测试套件
"""

import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pytest
import pandas as pd
import numpy as np

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from ats.sector_etf_engine import SectorETFEngine, get_sector_etf_engine, SECTOR_TO_BENCHMARK_ETF
from ats.reentry_tracker import ReentryTracker, get_reentry_tracker
from ats.ui.hot_sector_leaderboard import compute_buy_type_sort_score


def test_sector_etf_engine_mapping_and_trend():
    """测试 1: 验证板块 ETF 映射与 2 个月趋势结构判定能力"""
    engine = get_sector_etf_engine()
    
    # 验证关键字倒排索引映射
    yangzhi_etf = engine.find_benchmark_etf_for_sector("养殖业")
    assert yangzhi_etf is not None
    assert yangzhi_etf["code"] == "159865"
    assert yangzhi_etf["name"] == "养殖ETF"

    nongye_etf = engine.find_benchmark_etf_for_sector("农业种业")
    assert nongye_etf is not None
    assert nongye_etf["code"] == "159825"

    gold_etf = engine.find_benchmark_etf_for_sector("贵金属黄金")
    assert gold_etf is not None
    assert gold_etf["code"] == "518880"

    # 验证天马科技 (603668, 渔业/养殖) 的板块 ETF 解析
    trend_info = engine.get_stock_sector_etf_trend("603668", "水产养殖")
    assert trend_info["has_etf"] is True
    assert trend_info["etf_code"] == "159865"
    # 实测通达信二进制日线，养殖ETF走出 2 个月反弹慢牛
    assert trend_info["trend_grade"] in ("🟢 趋势主升", "🟡 震荡筑底")
    if trend_info["trend_grade"] == "🟢 趋势主升":
        assert trend_info["trend_score_bonus"] > 0


def test_reentry_tracker_tmkj_buyback_signal():
    """测试 2: 验证天马科技 (603668) 割肉后回踩 MA20 企稳并突破反转位触发回补买点"""
    tracker = get_reentry_tracker()
    
    # 模拟用户在 10.97 买入，在 10.28 止损割肉离场
    code = "603668"
    tracker.add_tracked_trade(
        code=code,
        buy_price=10.97,
        sell_price=10.28,
        buy_date="2026-08-15",
        sell_date="2026-08-25"
    )
    
    # 场景 A: 股价在 9.84 回踩 MA20 企稳中，尚未反转突破
    sig_wait = tracker.check_reentry_signal(
        code=code,
        current_price=10.10,
        ma20=9.95,
        high_2d=10.25,
        pct=0.8,
        is_bidding=False
    )
    assert sig_wait["is_reentry"] is False

    # 场景 B: 早竞价弱转强高开站稳 MA20 (pct=+1.5%, 现价 10.35 高于割肉价 10.28)
    sig_bid = tracker.check_reentry_signal(
        code=code,
        current_price=10.35,
        ma20=10.00,
        high_2d=10.25,
        pct=1.5,
        is_bidding=True
    )
    assert sig_bid["is_reentry"] is True
    assert sig_bid["buy_type"] == "💎 割肉反转回补"
    assert "止损" in sig_bid["reason"]
    assert sig_bid["type_priority"] == 97

    # 场景 C: 盘中放量突破反转阻力位 (现价 10.89, 突破 2日高点 10.50, pct=+5.5%)
    sig_break = tracker.check_reentry_signal(
        code=code,
        current_price=10.89,
        ma20=10.00,
        high_2d=10.50,
        pct=5.5,
        is_bidding=False
    )
    assert sig_break["is_reentry"] is True
    assert sig_break["buy_type"] == "💎 割肉反转回补"
    assert sig_break["stop_loss"] > 0


def test_bxl_pullback_reversal_launch_and_sorting():
    """测试 3: 验证柏星龙 (920075) 强势异动洗盘后早竞价弱转强起爆识别与绝对高优先级"""
    # 柏星龙历史特征：昨日 per1d = -4.5%，今日早竞价平开微高开 pct = +0.37%
    # 反差动能 reversal_diff = 0.37 - (-4.5) = +4.87%
    item_bxl = {
        "code": "920075",
        "name": "柏星龙",
        "sector": "消费包装",
        "price": 16.75,
        "open": 16.75,
        "pct": 0.37,
        "per1d": -4.5,
        "reversal_diff": 4.87,
        "buy_type": "👑 弱转强起爆",
        "buy_tag": "BID_REVERSAL_LAUNCH",
        "alpha_score": 98.4,
        "low_diff_pct": 0.0,
        "bid_pressure": 65.0,
        "rank": 28,
        "perc3d": 54.0,
    }

    # 计算量化得分
    score_bxl = compute_buy_type_sort_score(item_bxl)
    # 验证基准 96,000 分，加上反差加分后达到 97,000+
    assert score_bxl >= 96000.0, f"柏星龙得分应该 >= 96000，实际 {score_bxl}"

    # 对比普通跟风扫买标的 (如 pct=+2.5%, base=45000)
    item_follow = {
        "code": "000001",
        "name": "跟风股",
        "sector": "银行",
        "price": 10.0,
        "pct": 2.5,
        "buy_type": "🔥 主动扫买",
        "buy_tag": "SURGE",
        "alpha_score": 75.0,
    }
    score_follow = compute_buy_type_sort_score(item_follow)
    assert score_bxl > score_follow, "弱转强起爆龙头必须碾压普通跟风扫买标的"

    # 对比普通观望标的
    item_watch = {
        "code": "000002",
        "name": "常规股",
        "sector": "地产",
        "price": 8.0,
        "pct": 0.2,
        "buy_type": "⏱️ 竞价观望",
        "buy_tag": "WATCH",
        "alpha_score": 50.0,
    }
    score_watch = compute_buy_type_sort_score(item_watch)
    assert score_bxl > score_watch + 80000.0


def test_trap_pulse_filter_and_monotonic_tiers():
    """测试 4: 验证板块 ETF 空头破位下的昙花一现脉冲过滤与全买点梯队严格单调性"""
    # 模拟空头板块中的昙花一现孤狼脉冲
    item_trap = {
        "code": "002000",
        "name": "脉冲诱多股",
        "sector": "下行板块",
        "price": 12.0,
        "pct": 3.8,
        "buy_type": "⚠️ 昙花一现脉冲",
        "buy_tag": "TRAP",
        "alpha_score": 20.0,
    }
    score_trap = compute_buy_type_sort_score(item_trap)
    assert score_trap <= 2500.0, f"昙花一现脉冲必须在 2,000 分左右拦截，实际 {score_trap}"

    # 验证天马科技割肉回补得分
    item_tmkj = {
        "code": "603668",
        "name": "天马科技",
        "sector": "养殖",
        "price": 10.89,
        "pct": 5.5,
        "buy_type": "💎 割肉反转回补",
        "buy_tag": "RE_ENTRY_BUY",
        "alpha_score": 96.0,
    }
    score_tmkj = compute_buy_type_sort_score(item_tmkj)
    assert score_tmkj >= 95000.0, f"天马科技割肉回补必须高居 95,000+ 分，实际 {score_tmkj}"

    # 梯队单调性验证：
    # 👑 弱转强起爆 (97,000+) > 💎 割肉反转回补 (95,000+) > ⚡ 冲板助攻 (60,000+) > 🚀 先锋突破 (30,000+) > 💎 反身低吸 (20,000+) > 📋 蓄势观察 (10,000+) > ⚠️ 昙花一现脉冲 (2,000) > ⚠️ 破位转弱 (1,000)
    item_breakout = {"buy_type": "🚀 先锋突破", "buy_tag": "BREAKOUT", "pct": 4.0, "alpha_score": 85.0}
    item_pullback = {"buy_type": "💎 反身低吸", "buy_tag": "PULLBACK", "pct": 1.5, "alpha_score": 80.0}
    item_watch = {"buy_type": "📋 蓄势观察", "buy_tag": "WATCH", "pct": 0.5, "alpha_score": 50.0}
    item_weak = {"buy_type": "⚠️ 破位转弱", "buy_tag": "WEAK", "pct": -2.5, "alpha_score": 20.0}

    score_bo = compute_buy_type_sort_score(item_breakout)
    score_pb = compute_buy_type_sort_score(item_pullback)
    score_wt = compute_buy_type_sort_score(item_watch)
    score_wk = compute_buy_type_sort_score(item_weak)

    assert score_tmkj > score_bo > score_pb > score_wt > score_trap > score_wk, (
        f"梯队顺序倒挂: 回补={score_tmkj} > 突破={score_bo} > 低吸={score_pb} > 观察={score_wt} > 脉冲={score_trap} > 破位={score_wk}"
    )
