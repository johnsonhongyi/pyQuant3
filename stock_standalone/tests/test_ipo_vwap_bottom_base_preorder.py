# -*- coding: utf-8 -*-
"""
tests/test_ipo_vwap_bottom_base_preorder.py
--------------------------------------------
验证新股次新 VWAP 策略全面进化：
1. 底部平底/双底缩量企稳结构与动能拐点识别 (has_bottom_base, base_inflection_confirmed)
2. 决策树进化：提前生成【🎯 筑底预埋】与【⚡ 筑底共振】信号
3. 赛马打分进化：底部结构标的获得 80+ 动能分，冒泡进入前列
4. 破除一刀切全局避险：龙头天量冲顶不误杀低位独立筑底标的
5. 集中交易调度中心成功产生限价预埋买单 (LIMIT) 与共振突击单 (CRITICAL)
6. 极窄底台止损线精准锚定
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
import time

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_CUR_DIR)
_STANDALONE_DIR = os.path.join(_PROJ_ROOT, "stock_standalone")

for p in [_STANDALONE_DIR, _PROJ_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from ats.strategy.ipo_vwap_detector_engine import (
    VWAPDetectorSignal, IPOVWAPDetectorEngine, batch_evaluate_horse_race_ranking
)
from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOOrderDirective


def create_bottom_base_intraday_df(code="688836", base_price=470.0, vwap_price=505.0, is_breakout=False):
    """
    构造操盘手图 2 孚朗科技同款分时数据：
    - 前期远离 VWAP (负偏离 -7%)
    - 底部 470 元平底横盘震荡 25 根 Bar，成交量极度萎缩
    - 尾部放量微翘 (is_breakout=True 时放量冲到 480 元)
    """
    rows = []
    t_base = 9 * 60 + 30
    
    # 1. 前 30 根 Bar：放量下杀到 base_price
    drop_from = base_price * 1.05
    drop_range = drop_from - base_price
    for i in range(30):
        m = t_base + i
        time_str = f"{m//60:02d}:{m%60:02d}"
        p = drop_from - (drop_range * i / 29.0)
        rows.append({
            "time": time_str,
            "date": "2026-09-18",
            "open": p + 0.1,
            "high": p + 0.2,
            "low": p - 0.1,
            "close": p,
            "volume": 2000.0,
            "vwap": vwap_price
        })

    # 2. 中间 25 根 Bar：在 base_price 元横盘筑底 (极度缩量，振幅 < 1%)
    for i in range(25):
        m = t_base + 30 + i
        time_str = f"{m//60:02d}:{m%60:02d}"
        p = base_price + (0.01 * base_price * (i % 3 - 1) * 0.3)
        rows.append({
            "time": time_str,
            "date": "2026-09-18",
            "open": p,
            "high": p + 0.05,
            "low": p - 0.05,
            "close": p,
            "volume": 300.0,  # 严重缩量磨底
            "vwap": vwap_price
        })

    # 3. 尾部 5 根 Bar：动能拐头上翘
    for i in range(5):
        m = t_base + 55 + i
        time_str = f"{m//60:02d}:{m%60:02d}"
        if is_breakout:
            p = base_price * (1.015 + i * 0.008)  # 放量加速突破
            v = 1500.0
        else:
            p = base_price * (1.003 + i * 0.002)  # 平台初显拐头上翘
            v = 800.0
        rows.append({
            "time": time_str,
            "date": "2026-09-18",
            "open": p - 0.05,
            "high": p + 0.1,
            "low": p - 0.05,
            "close": p,
            "volume": v,
            "vwap": vwap_price
        })

    return pd.DataFrame(rows)


def test_bottom_base_and_inflection_detection():
    """测试 1: 验证底部横盘平底与动能拐点特征提取"""
    engine = IPOVWAPDetectorEngine.get_instance()
    
    # 1.1 预埋形态 (横盘企稳拐头)
    df_preorder = create_bottom_base_intraday_df(base_price=470.0, vwap_price=506.0, is_breakout=False)
    sig_pre = VWAPDetectorSignal(code="688836", name="孚朗科技")
    engine._evaluate_vwap_structure(df_preorder, sig_pre)
    engine._evaluate_bottom_base_structure(df_preorder, sig_pre)
    engine._synthesize_final_decision(sig_pre)

    assert sig_pre.has_bottom_base is True
    assert sig_pre.base_inflection_confirmed is True
    assert sig_pre.base_support_level >= 468.0 and sig_pre.base_support_level <= 471.0
    assert sig_pre.signal_type == "BASE_PREORDER"
    assert sig_pre.signal_level == "🎯 筑底预埋"
    assert sig_pre.stop_loss_price < sig_pre.base_support_level  # 极窄底台止损
    assert sig_pre.rebound_to_vwap_space_pct > 6.0  # 向上距 VWAP 有 6%+ 反弹空间

    # 1.2 共振突破形态 (放量加速)
    df_break = create_bottom_base_intraday_df(base_price=19.3, vwap_price=22.5, is_breakout=True)
    sig_break = VWAPDetectorSignal(code="002411", name="延安必康")
    engine._evaluate_vwap_structure(df_break, sig_break)
    engine._evaluate_bottom_base_structure(df_break, sig_break)
    engine._synthesize_final_decision(sig_break)

    assert sig_break.has_bottom_base is True
    assert sig_break.base_inflection_confirmed is True
    assert sig_break.signal_type == "BASE_BREAKOUT"
    assert sig_break.signal_level == "⚡ 筑底共振"
    assert "筑底放量共振" in sig_break.signal_desc or "放量加速" in sig_break.signal_desc


def test_horse_race_momentum_scoring_for_base_stocks():
    """测试 2: 验证赛马打分进化，具备底部结构的标的不再垫底，而是冒泡获得 80+ 动能分"""
    sig_base = VWAPDetectorSignal(
        code="688836", name="孚朗科技", price=472.0, vwap=506.0,
        signal_type="BASE_PREORDER", has_bottom_base=True,
        base_support_level=470.0, base_consolidation_bars=20,
        base_inflection_confirmed=True, rebound_to_vwap_space_pct=7.2,
        is_above_vwap=False, vwap_diff_pct=-6.7
    )
    sig_normal_down = VWAPDetectorSignal(
        code="301689", name="弱势股", price=30.0, vwap=33.0,
        is_above_vwap=False, vwap_diff_pct=-9.0
    )

    ranked = batch_evaluate_horse_race_ranking([sig_normal_down, sig_base])
    assert len(ranked) == 2
    # 底部预埋标的必须排在弱势破位股之前
    assert ranked[0].code == "688836"
    assert ranked[0].horse_race_score >= 80.0
    assert ranked[0].horse_race_tier == "🎯 筑底预埋"
    # 普通破位股依然保持低分
    assert ranked[1].horse_race_score <= 40.0
    assert ranked[1].horse_race_tier == "⛔ 破位出局"


def test_unshackle_panic_defense_when_leader_climaxes():
    """测试 3: 破除一刀切全局避险，龙头天量冲顶高潮平仓不误杀低位独立筑底标的"""
    trading_center = IPOTradingCenter.get_instance()
    trading_center._reports_cache.clear()
    trading_center._positions.clear()

    # 1. 模拟沈鼓集团冲顶天量高潮平仓 (is_climax_exit = True)
    sig_shengu = VWAPDetectorSignal(
        code="601091", name="沈鼓集团", price=57.77, vwap=19.64,
        is_above_vwap=True, vwap_diff_pct=194.1, is_climax_exit=True,
        horse_race_score=99.0
    )

    # 2. 模拟高位跟风标的 (排在后面且无结构)
    sig_follower = VWAPDetectorSignal(
        code="301707", name="展芯股份", price=75.40, vwap=73.0,
        change_pct=3.2, is_above_vwap=True, vwap_diff_pct=3.2, horse_race_score=77.0,
        horse_race_rank=4
    )

    # 3. 模拟底部构筑扎实结构的预埋标的 (孚朗科技)
    sig_base = VWAPDetectorSignal(
        code="688836", name="孚朗科技", price=472.0, vwap=506.0,
        change_pct=0.8, signal_type="BASE_PREORDER", has_bottom_base=True,
        base_support_level=470.0, base_consolidation_bars=25,
        base_inflection_confirmed=True, rebound_to_vwap_space_pct=7.2,
        is_above_vwap=False, vwap_diff_pct=-6.7, horse_race_score=85.0
    )

    # 增加 2 只正常的站稳 VWAP 的前锋标的，使全池处于正常活跃状态
    sig_vf1 = VWAPDetectorSignal(code="688801", name="前锋1", price=100.0, vwap=95.0, change_pct=5.5, is_above_vwap=True, horse_race_score=90.0)
    sig_vf2 = VWAPDetectorSignal(code="920298", name="前锋2", price=50.0, vwap=48.0, change_pct=4.2, is_above_vwap=True, horse_race_score=88.0)

    trading_center.submit_stock_perception_report(sig_vf1)
    trading_center.submit_stock_perception_report(sig_vf2)
    trading_center.submit_stock_perception_report(sig_shengu)
    trading_center.submit_stock_perception_report(sig_follower)
    trading_center.submit_stock_perception_report(sig_base)

    directives = trading_center.evaluate_fleet_and_generate_orders()

    # 断言 1: 沈鼓集团自身判定为高潮平仓
    assert sig_shengu.global_fleet_role == "CLIMAX_EXIT"

    # 断言 2: 高位跟风标的展芯股份触发避险
    assert sig_follower.global_fleet_role == "PANIC_DEFENSE"

    # 断言 3: 底部预埋标的孚朗科技绝不被误杀打成 PANIC_DEFENSE！
    assert sig_base.global_fleet_role == "BASE_PREORDER"
    assert "筑底预埋" in sig_base.global_arbitration_desc

    # 断言 4: 成功产生限价预埋买单
    buy_dirs = [d for d in directives if d.action == "BUY" and d.code == "688836"]
    assert len(buy_dirs) >= 1
    assert buy_dirs[0].urgency == "LIMIT"
    assert "预埋" in buy_dirs[0].reason


def test_base_stock_tight_stop_loss_arbitration():
    """测试 4: 底部结构标的的极窄止损守卫 (买错跌破底台立斩)"""
    trading_center = IPOTradingCenter.get_instance()
    trading_center._reports_cache.clear()
    trading_center._positions.clear()

    # 建立孚朗科技持仓：买入价 472.0，底台支撑 470.0，止损线 466.24
    from ats.strategy.ipo_trading_center import IPOTradingPosition
    pos = IPOTradingPosition(
        code="688836", name="孚朗科技", shares=200, available_shares=200,
        cost_price=472.0, current_price=472.0, status="HOLDING"
    )
    trading_center._positions["688836"] = pos

    # 4.1 价格在底台支撑之上 (471.0 > 466.24)，虽然在 VWAP(506.0) 之下，但不斩仓
    sig_hold = VWAPDetectorSignal(
        code="688836", name="孚朗科技", price=471.0, vwap=506.0,
        signal_type="BASE_PREORDER", has_bottom_base=True,
        base_support_level=470.0, stop_loss_price=466.24,
        is_above_vwap=False, vwap_diff_pct=-6.9
    )
    trading_center.submit_stock_perception_report(sig_hold)
    dirs = trading_center.evaluate_fleet_and_generate_orders()
    sell_dirs = [d for d in dirs if d.action == "SELL" and d.code == "688836"]
    assert len(sell_dirs) == 0  # 依然安全持仓

    # 4.2 价格破位跌破底台止损线 (465.0 < 466.24)，触发买错立斩！
    sig_break = VWAPDetectorSignal(
        code="688836", name="孚朗科技", price=465.0, vwap=506.0,
        signal_type="BASE_PREORDER", has_bottom_base=True,
        base_support_level=470.0, stop_loss_price=466.24,
        is_above_vwap=False, vwap_diff_pct=-8.1
    )
    trading_center.submit_stock_perception_report(sig_break)
    dirs2 = trading_center.evaluate_fleet_and_generate_orders()
    sell_dirs2 = [d for d in dirs2 if d.action == "SELL" and d.code == "688836"]
    assert len(sell_dirs2) == 1
    assert "底台破位止损" in sell_dirs2[0].reason


def test_multi_day_base_and_60f_channel_breakout():
    """测试 5: 蓝色光标同款结构 (4日大平底箱体 + 60F下降通道突破 + 尾盘放量收最高)"""
    engine = IPOVWAPDetectorEngine.get_instance()
    trading_center = IPOTradingCenter.get_instance()
    trading_center._reports_cache.clear()
    trading_center._positions.clear()

    # 构造 10 日多日分时，前 3 天在 12.60~12.95 横盘大平底，第 4 天尾盘收全天最高 13.15
    dates = ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
    data = []
    for d in dates[:-1]:
        for i in range(20):
            data.append({
                "date": d,
                "time": f"09:{30+i:02d}",
                "open": 12.75,
                "high": 12.95,
                "low": 12.65,
                "close": 12.80,
                "volume": 5000,
                "vwap": 13.47
            })
    # 第 4 天 (今日)，尾盘拉升收在最高 13.15
    for i in range(25):
        c_val = 12.80 + (i * 0.014)  # 逐步拉升至 13.15
        data.append({
            "date": dates[-1],
            "time": f"14:{30+i:02d}",
            "open": 12.80,
            "high": c_val,
            "low": 12.78,
            "close": c_val,
            "volume": 8000 if i >= 20 else 4000,
            "vwap": 13.47
        })

    df_multi = pd.DataFrame(data)

    sig = VWAPDetectorSignal(
        code="300058",
        name="蓝色光标",
        price=13.15,
        vwap=13.47,  # 股价在 10d VWAP 之下
        change_pct=2.8,
        is_above_vwap=False,
        vwap_diff_pct=-2.37,
        has_kline_launch_sig=True  # 60F / 日K 突破通道支撑
    )

    # 执行底台结构识别
    engine._evaluate_bottom_base_structure(df_multi, sig)
    # 断言识别出跨日通道突破
    assert sig.is_swing_channel_breakout is True
    assert sig.has_bottom_base is True
    assert sig.multi_day_base_support >= 12.60
    # 止损线严格锚定在底台支撑下方 0.8%，绝不以遥远的 13.47 VWAP 误杀
    assert sig.stop_loss_price < 13.00
    assert sig.stop_loss_price > 12.50

    # 执行最终信号综合
    engine._synthesize_final_decision(sig)
    assert sig.signal_type == "SWING_PREORDER"
    assert "突破下降通道" in sig.signal_desc or "箱体突破" in sig.signal_desc

    # 赛马天梯打分断言：跻身前列 (>= 80分)，获得专属徽章
    ranked = batch_evaluate_horse_race_ranking([sig])
    assert ranked[0].horse_race_score >= 80.0
    assert "通道突破" in ranked[0].horse_race_tier

    # 指挥中心指令生成断言：生成预埋买单
    trading_center.submit_stock_perception_report(sig)
    dirs = trading_center.evaluate_fleet_and_generate_orders()
    buy_dirs = [d for d in dirs if d.action == "BUY" and d.code == "300058"]
    assert len(buy_dirs) >= 1
    assert buy_dirs[0].urgency == "LIMIT"
    assert "通道突破" in buy_dirs[0].reason


def test_climax_surge_suspension_and_preset_sell_order():
    """测试 6: 沈鼓集团冲顶高潮感知、T+1追高买入禁令与提前算法高抛挂单"""
    engine = IPOVWAPDetectorEngine.get_instance()
    trading_center = IPOTradingCenter.get_instance()
    trading_center._reports_cache.clear()
    trading_center._positions.clear()

    # 1. 模拟沈鼓集团盘中触发 2 次临停，现价 80.0，开盘 50.0，最高 82.59，VWAP 60.0
    today_bars = []
    for i in range(30):
        today_bars.append({
            "date": "2026-09-18",
            "time": f"09:{30+i:02d}",
            "open": 50.0,
            "high": 82.59,
            "low": 48.0,
            "close": 80.0,
            "volume": 20000,
            "vwap": 60.0
        })
    df_today = pd.DataFrame(today_bars)

    sig_shengu = VWAPDetectorSignal(
        code="601091",
        name="沈鼓集团",
        price=80.0,
        vwap=60.0,
        change_pct=60.0,
        is_above_vwap=True,
        vwap_diff_pct=33.3,
        is_ipo_first_day=False  # 非上市首日 (T+1 标的)
    )

    # 评估分时与临停感知
    engine._evaluate_vwap_structure(df_today, sig_shengu)

    # 断言 1: 成功感知到临停次数 (>=2次)
    assert sig_shengu.suspension_count >= 2
    # 断言 2: 提前计算出计算机高抛挂单价 (接近最高点 82.59 附近)
    assert sig_shengu.climax_preset_sell_price >= 80.0
    # 断言 3: T+1 追高买入禁令生效
    assert sig_shengu.is_t1_forbidden_buy is True

    # 断言 4: 指挥中心在无持仓时，绝不给沈鼓集团生成买单 (被 T+1 追高禁令拦截)
    trading_center.submit_stock_perception_report(sig_shengu)
    dirs_nobuy = trading_center.evaluate_fleet_and_generate_orders()
    buy_dirs = [d for d in dirs_nobuy if d.action == "BUY" and d.code == "601091"]
    assert len(buy_dirs) == 0

    # 断言 5: 当有昨天买入的底仓持仓时，触发高潮平仓时生成 LIMIT 提前算法高抛挂单卖出！
    from ats.strategy.ipo_trading_center import IPOTradingPosition
    trading_center._positions["601091"] = IPOTradingPosition(
        code="601091", name="沈鼓集团", shares=500, available_shares=500,
        cost_price=50.0, current_price=80.0, status="HOLDING"
    )
    sig_shengu.is_climax_exit = True
    sig_shengu.signal_type = "CLIMAX_EXIT"
    trading_center.submit_stock_perception_report(sig_shengu)

    dirs_sell = trading_center.evaluate_fleet_and_generate_orders()
    sell_dirs = [d for d in dirs_sell if d.action == "SELL" and d.code == "601091"]
    assert len(sell_dirs) >= 1
    assert sell_dirs[0].urgency == "LIMIT"
    assert sell_dirs[0].price == sig_shengu.climax_preset_sell_price
    assert "提前算法设计挂单高抛" in sell_dirs[0].reason or "提前挂单" in sell_dirs[0].reason

