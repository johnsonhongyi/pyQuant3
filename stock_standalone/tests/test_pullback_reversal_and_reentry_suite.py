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
from PyQt6.QtCore import Qt
app = QApplication.instance() or QApplication(sys.argv)

from ats.sector_etf_engine import SectorETFEngine, get_sector_etf_engine, SECTOR_TO_BENCHMARK_ETF
from ats.reentry_tracker import ReentryTracker, get_reentry_tracker
from ats.ui.hot_sector_leaderboard import compute_buy_type_sort_score


def test_sector_etf_engine_mapping_and_trend():
    """测试 1: 验证板块 ETF 映射、20大核心概念扩充与通道支撑/反转位量化评级能力"""
    engine = get_sector_etf_engine()
    
    # 验证关键字倒排索引映射与 20 大赛道扩充 (AI, 传媒, 游戏, 机器人, 云计算, 养殖, 黄金等)
    ai_etf = engine.find_benchmark_etf_for_sector("AI智能体大模型")
    assert ai_etf is not None
    assert ai_etf["code"] == "159819"
    assert ai_etf["name"] == "人工智能ETF"

    media_etf = engine.find_benchmark_etf_for_sector("短剧影视传媒")
    assert media_etf is not None
    assert media_etf["code"] == "512980"

    game_etf = engine.find_benchmark_etf_for_sector("网络电竞游戏")
    assert game_etf is not None
    assert game_etf["code"] == "159869"

    robot_etf = engine.find_benchmark_etf_for_sector("人形机器人具身智能")
    assert robot_etf is not None
    assert robot_etf["code"] == "562500"

    yangzhi_etf = engine.find_benchmark_etf_for_sector("养殖业")
    assert yangzhi_etf is not None
    assert yangzhi_etf["code"] == "159865"
    assert yangzhi_etf["name"] == "养殖ETF"

    gold_etf = engine.find_benchmark_etf_for_sector("贵金属黄金")
    assert gold_etf is not None
    assert gold_etf["code"] == "518880"

    # 验证天马科技 (603668, 水产养殖) 的板块 ETF 通道支撑解析
    trend_info = engine.get_stock_sector_etf_trend("603668", "水产养殖")
    assert trend_info["has_etf"] is True
    assert trend_info["etf_code"] == "159865"
    # 跟个股一样：验证通达信原生自动通道指标 (supp_p, reversal_p, channel_score)
    assert trend_info["supp_p"] > 0.0
    assert trend_info["reversal_p"] > 0.0
    assert trend_info["trend_grade"] in ("🚀 回踩起爆", "👑 突破加速", "🟢 上升通道", "💎 支撑企稳", "🟡 箱体震荡", "🔴 空头破位")


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
    """测试 4: 验证板块 ETF 空头破位下的诱多脉冲拦截与全买点梯队严格单调性"""
    # 模拟空头破位板块中的孤狼诱多脉冲
    item_trap = {
        "code": "002000",
        "name": "脉冲诱多股",
        "sector": "下行板块",
        "price": 12.0,
        "pct": 3.8,
        "buy_type": "⚠️ 诱多脉冲(板块破位)",
        "buy_tag": "TRAP",
        "alpha_score": 20.0,
    }
    score_trap = compute_buy_type_sort_score(item_trap)
    assert score_trap <= 2500.0, f"诱多脉冲必须在 2,000 分左右拦截沉底，实际 {score_trap}"

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
    # 👑 弱转强起爆 (97,000+) > 💎 割肉反转回补 (95,000+) > ⚡ 冲板助攻 (60,000+) > 🚀 先锋突破 (30,000+) > 💎 反身低吸 (20,000+) > 📋 蓄势观察 (10,000+) > ⚠️ 诱多脉冲 (2,000) > ⚠️ 破位转弱 (1,000)
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


def test_context_menu_crash_proof_and_stateless_handlers():
    """测试 5: 验证右键菜单解绑 C++ 指针无状态分发、防崩溃保护与双击第2列聚焦板块"""
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
    dialog = HotSectorLeaderboardDialog()
    
    # 1. 验证无状态方法在纯字符串调用下安全稳定执行
    dialog._link_stock_by_code("002567", "唐人神")
    dialog._open_stock_strategy_by_code("002567", "唐人神")

    # 2. 验证防崩溃保护：传入已被析构或无效的 item 绝不报 RuntimeError
    dialog._on_item_clicked(None)
    dialog._on_item_double_clicked(None)

    # 3. 验证板块单选聚焦与恢复全选
    dialog.current_top_sectors = ["猪肉", "养鸡", "玉米"]
    dialog.active_sectors = {"猪肉", "养鸡", "玉米"}
    dialog.selected_single_sector = None

    # 模拟双击第 2 列【所属强板块】聚焦 "猪肉"
    dialog._select_single_sector_by_name("猪肉 [🟢养殖 支撑5.40]")
    assert dialog.selected_single_sector == "猪肉"
    assert dialog.active_sectors == {"猪肉"}

    # 再次双击 "猪肉"，平滑恢复全选
    dialog._select_single_sector_by_name("猪肉")
    assert dialog.selected_single_sector is None
    assert "猪肉" in dialog.active_sectors and "养鸡" in dialog.active_sectors

    dialog.close()


def test_sector_column_etf_display_and_radar_dialog():
    """测试 6: 验证主表第2列显性化呈现 ETF 通道支撑/评分与全市场 ETF 通道雷达窗口"""
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog, SectorETFRadarDialog
    from PyQt6.QtGui import QFont

    dialog = HotSectorLeaderboardDialog()
    dialog.table.setRowCount(2)

    font = QFont()
    # 模拟两只不同板块标的：一只养殖（上升通道/支撑），一只半导体（破位）
    rec_up = {
        "code": "002567",
        "name": "唐人神",
        "sector": "猪肉",
        "etf_name": "养殖ETF",
        "etf_trend": "🟢 上升通道",
        "etf_supp_p": 5.40,
        "etf_reversal_p": 5.43,
        "etf_channel_score": 75.0,
        "etf_gain_5d": 1.5,
        "etf_gain": 6.47,
        "price": 6.50,
        "pct": 9.98,
        "buy_type": "⚡ 脱离成本狙击",
        "buy_tag": "SURGE",
        "alpha_score": 92.0
    }
    rec_down = {
        "code": "688001",
        "name": "华兴源创",
        "sector": "半导体",
        "etf_name": "半导体ETF",
        "etf_trend": "🔴 空头破位",
        "etf_supp_p": 10.50,
        "etf_reversal_p": 11.20,
        "etf_channel_score": 25.0,
        "etf_gain_5d": -3.5,
        "etf_gain": -52.86,
        "price": 28.00,
        "pct": 2.1,
        "buy_type": "⚠️ 诱多脉冲(板块破位)",
        "buy_tag": "TRAP",
        "alpha_score": 25.0
    }

    dialog._populate_row(0, rec_up, font)
    dialog._populate_row(1, rec_down, font)

    # 验证第 2 列【所属强板块】文本显性化
    sec_item_up = dialog.table.item(0, 2)
    assert sec_item_up is not None
    assert "猪肉" in sec_item_up.text()
    assert "🟢" in sec_item_up.text()
    assert "养殖" in sec_item_up.text()
    assert "支撑5.40" in sec_item_up.text()
    # 验证 raw_val 注入 channel_score，支持按通道健康度高精排序
    assert sec_item_up.raw_val == 75.0

    sec_item_down = dialog.table.item(1, 2)
    assert sec_item_down is not None
    assert "半导体" in sec_item_down.text()
    assert "🔴" in sec_item_down.text()
    assert "破位" in sec_item_down.text()
    assert sec_item_down.raw_val == 25.0

    # 验证 SectorETFRadarDialog 初始化与数据加载 (20大赛道)
    radar_dlg = SectorETFRadarDialog(dialog)
    assert radar_dlg.table.rowCount() >= 20
    assert radar_dlg.table.columnCount() == 18

    # 1. 验证排序功能 (isSortingEnabled=True 与按 raw_val 高精排序)
    assert radar_dlg.table.isSortingEnabled() is True
    # 验证第一行启动动能评分必然大于等于最后一行（初始按启动动能降序排列）
    score_first = float(radar_dlg.table.item(0, 6).raw_val)
    score_last = float(radar_dlg.table.item(radar_dlg.table.rowCount() - 1, 6).raw_val)
    assert score_first >= score_last, f"ETF 雷达未按启动动能降序排列: 首行={score_first}, 末行={score_last}"

    # 验证今日涨跌% (列5) 与 预埋上车建议 (列7) 均已填充
    pct_item = radar_dlg.table.item(0, 5)
    assert pct_item is not None
    assert "%" in pct_item.text()
    adv_item = radar_dlg.table.item(0, 7)
    assert adv_item is not None
    assert len(adv_item.text()) > 0

    # 测试点击表头升序排序 (启动动能升序)
    radar_dlg.table.sortItems(6, Qt.SortOrder.AscendingOrder)
    score_asc_first = float(radar_dlg.table.item(0, 6).raw_val)
    score_asc_last = float(radar_dlg.table.item(radar_dlg.table.rowCount() - 1, 6).raw_val)
    assert score_asc_first <= score_asc_last, f"升序排序失效: 首行={score_asc_first}, 末行={score_asc_last}"

    # 测试按现价 (列4) 降序排序
    radar_dlg.table.sortItems(4, Qt.SortOrder.DescendingOrder)
    p_desc_first = float(radar_dlg.table.item(0, 4).raw_val)
    p_desc_last = float(radar_dlg.table.item(radar_dlg.table.rowCount() - 1, 4).raw_val)
    assert p_desc_first >= p_desc_last, f"现价降序排序失效: 首行={p_desc_first}, 末行={p_desc_last}"

    # 2. 验证窗口大小与位置持久化及列宽存盘
    radar_dlg.setGeometry(120, 150, 1100, 650)
    radar_dlg._save_window_geometry()
    radar_dlg._save_header_state()
    from ats.ui.styles import load_config_node
    saved_geo = load_config_node("sector_etf_radar_dialog_geo_v2") or load_config_node("sector_etf_radar_dialog_geo")
    assert saved_geo is not None
    assert saved_geo.get("w") == 1100
    assert saved_geo.get("h") == 650
    saved_header = load_config_node("sector_etf_radar_dialog_header_v2")
    assert saved_header is not None and len(saved_header) > 10

    # 3. 验证上下键联动与单击极速联动功能
    linked_codes = []
    dialog._link_stock_by_code = lambda c, n: linked_codes.append((c, n))
    
    # 模拟选中第 0 行并触发上下键/焦点联动
    radar_dlg._link_row_by_index(0)
    assert len(linked_codes) == 1
    assert linked_codes[-1][0] == radar_dlg.table.item(0, 2).text().strip()

    # 模拟防重复机制：重复同一行不重复广播
    radar_dlg._link_row_by_index(0)
    assert len(linked_codes) == 1

    # 模拟键盘向下键 (Down) 切换到第 1 行
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    radar_dlg.table.setCurrentCell(1, 0)
    key_down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    radar_dlg.keyPressEvent(key_down)
    assert len(linked_codes) == 2
    assert linked_codes[-1][0] == radar_dlg.table.item(1, 2).text().strip()

    radar_dlg.close()
    dialog.close()

