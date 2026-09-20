# -*- coding: utf-8 -*-
"""
tests/test_ipo_detector_and_trading_center_voice_alert.py
---------------------------------------------------------
全套自动化测试验证：
1. 集中交易指挥室全仓轮动 (100% 动态满仓腾挪换马接力新龙头)；
2. 本地交易账本持久化 (已平仓历史战绩 + 信号产生与迭代日志沉淀，告别“今天卖了就没下文”)；
3. 今日新股次新股申购自动嗅探与语音广播提醒；
4. 开盘首日四大高级形态战术分级 (首日早鸟吸筹 SSS 级、首日恐吓反包 SSS 级、临停挂单 ALERT 级等)；
5. 检测中心与指挥室的直达定位 (locate_stock_in_table)；
6. 集中仲裁详情窗对平仓复盘与迭代日志的富文本渲染。
"""

import os
import sys
import json
import time
import pytest
from unittest.mock import patch, MagicMock

cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from ats.strategy.ipo_trading_center import (
    IPOTradingCenter, IPOOrderDirective, IPOTradingPosition
)
from ats.strategy.ipo_vwap_detector_engine import (
    IPOVWAPDetectorEngine, VWAPDetectorSignal
)
from ats.alert_notifier import AlertNotifier
from ats.ui.ipo_command_room_dialog import IPOCommandRoomDialog
from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
from ats.ui.ipo_arbitration_detail_dialog import IPOArbitrationDetailDialog

TEST_LEDGER_FILE = os.path.join(cur_dir, "_tmp_ipo_test_ledger.json")


def setup_function():
    """每个测试前重置 IPOTradingCenter 单例状态"""
    center = IPOTradingCenter.get_instance()
    center._positions.clear()
    center._pending_directives.clear()
    center._closed_positions.clear()
    center._signal_iteration_log.clear()
    center.total_capital = 1000000.0
    center.available_cash = 1000000.0
    center.enable_full_rotation = False
    center._ledger_file = TEST_LEDGER_FILE


def teardown_module():
    if os.path.exists(TEST_LEDGER_FILE):
        try:
            os.remove(TEST_LEDGER_FILE)
        except Exception:
            pass


def test_full_rotation_swap_generation_and_t1_guarded_execution():
    """1. 验证全仓轮动模式：满仓 100% 换马新龙头与历史平仓记录沉淀"""
    center = IPOTradingCenter(total_capital=1000000.0)
    center._ledger_file = TEST_LEDGER_FILE

    # 开启全仓轮动模式
    center.set_full_rotation_enabled(True)
    assert center.enable_full_rotation is True

    # 1. 初始买入老股票 300001 (成本 50.0，满仓 20000 股，耗资 100 万)
    d_buy_old = IPOOrderDirective(
        action="BUY", code="300001", name="老标的", price=50.0,
        shares=20000, size_pct=100.0, urgency="NORMAL", reason="初始全仓买入"
    )
    center.execute_directive(d_buy_old)
    assert "300001" in center._positions
    assert center._positions["300001"].shares == 20000
    assert center.available_cash == 0.0

    # 2. 模拟全池赛马天梯，新龙头 300002 拔地而起 (100分，LEADER)，老标的 300001 走弱 (50分，FOLLOWER)
    sig_leader = VWAPDetectorSignal(
        code="300002", name="新龙头", price=100.0, vwap=95.0, vwap_diff_pct=5.26,
        is_above_vwap=True, launch_time_str="09:31", launch_slope_deg=45.0,
        signal_type="BREAKOUT", signal_tier="SSS", horse_race_score=100.0, horse_race_rank=1
    )
    sig_follower = VWAPDetectorSignal(
        code="300001", name="老标的", price=52.0, vwap=53.0, vwap_diff_pct=-1.88,
        is_above_vwap=False, signal_type="PULLBACK_BUY",
        signal_tier="WATCH", horse_race_score=50.0, horse_race_rank=8
    )

    # 提交报告并触发仲裁
    center.submit_batch_reports([sig_leader, sig_follower])

    # 验证生成的待执行指令中包含全仓轮动指令 FULL_ROTATION_SWAP
    pending = center.get_pending_directives()
    assert len(pending) > 0

    swap_directive = next((d for d in pending if d.action == "FULL_ROTATION_SWAP"), None)
    assert swap_directive is not None
    assert swap_directive.code == "300002"
    assert swap_directive.target_swap_code == "300001"
    assert swap_directive.size_pct == 100.0
    assert "全仓轮动" in swap_directive.reason

    # 3. 执行全仓轮动决议
    # Same-day holdings are physically locked by A-share T+1 rules.
    assert center.execute_directive(swap_directive) is False
    assert "300001" in center._positions
    assert "300002" not in center._positions
    assert center.available_cash == 0.0
    assert center.get_closed_positions() == []

    # The identical tactical directive becomes executable on the next day.
    center._positions["300001"].entry_date = "2026-09-19"
    assert center.execute_directive(swap_directive) is True

    # 验证老持仓已结清平仓，新龙头成为唯一持仓
    assert "300001" not in center._positions
    assert "300002" in center._positions
    assert center._positions["300002"].shares > 0

    # 验证平仓历史战绩被忠实记录 (不是卖了就没下文了)
    closed = center.get_closed_positions()
    assert len(closed) >= 1
    closed_pos = closed[-1]
    assert closed_pos["code"] == "300001"
    assert closed_pos["exit_price"] == 52.0
    assert closed_pos["realized_pnl_pct"] == pytest.approx(4.0, abs=0.1) # 50 -> 52
    assert "全仓轮动" in closed_pos["exit_reason"]

    # 验证信号迭代日志沉淀 (按时间倒序排列，logs[0] 为最新生成的轮动日志)
    logs = center.get_signal_iteration_log()
    assert len(logs) >= 2
    latest_log = logs[0]
    assert latest_log["code"] == "300002"
    assert latest_log["action"] == "FULL_ROTATION_SWAP"


def test_closed_positions_and_iteration_ledger_persistence():
    """2. 验证本地交易账本持久化与跨实例恢复"""
    center = IPOTradingCenter.get_instance()

    # 写入一条平仓战绩和一条信号日志
    p = IPOTradingPosition(
        code="688001", name="次新先锋", shares=1000, cost_price=80.0,
        current_price=92.0, status="PROFIT_EXIT", entry_date="2026-09-18",
        entry_time="09:35:00", exit_date="2026-09-19", exit_time="10:15:00",
        exit_price=92.0, realized_pnl_pct=15.0, realized_pnl_amount=12000.0,
        exit_reason="首日临停冲高算法锁定利润", entry_reason="首日早鸟贴线吸筹",
        signal_tier="SSS"
    )
    center._closed_positions.append(p.to_dict())
    center._append_signal_iteration_log(
        action="BUY", code="688001", name="次新先锋", price=80.0,
        size_pct=100.0, reason="首日贴线吸筹绝杀", signal_tier="SSS"
    )
    center._save_ledger()

    assert os.path.exists(TEST_LEDGER_FILE)

    # 重新加载账本验证数据完好无损
    center._closed_positions.clear()
    center._signal_iteration_log.clear()
    center._load_ledger()

    assert len(center._closed_positions) == 1
    assert center._closed_positions[0]["code"] == "688001"
    assert center._closed_positions[0]["realized_pnl_pct"] == 15.0
    assert center._closed_positions[0]["exit_reason"] == "首日临停冲高算法锁定利润"

    assert len(center._signal_iteration_log) == 1
    assert center._signal_iteration_log[0]["signal_tier"] == "SSS"


def test_today_ipo_subscription_alert():
    """3. 验证今日新股申购嗅探与即时语音/Toast广播"""
    center = IPOTradingCenter.get_instance()

    mock_fetcher = MagicMock()
    today_date = time.strftime("%Y-%m-%d")
    mock_dict = {
        "301599": {
            "code": "301599",
            "name": "芯晨微",
            "apply_date": today_date,
            "issue_price": 28.50,
            "pe_ratio": 22.5
        }
    }
    mock_fetcher.fetch_ipo_calendar.return_value = mock_dict
    mock_fetcher._cached_ipo_dict = mock_dict

    with patch("ats.new_stock_fetcher.NewStockFetcher.get_instance", return_value=mock_fetcher):
        with patch.object(AlertNotifier.get_instance(), "notify_special_signal") as mock_notify:
            alerts = center.check_today_ipo_subscriptions()
            assert len(alerts) >= 1
            assert alerts[0]["code"] == "301599"
            assert alerts[0]["name"] == "芯晨微"
            assert mock_notify.called


def test_first_day_signals_and_tiering():
    """4. 验证开盘首日四大高级形态战术分级 (SSS / S / ALERT / WATCH)"""
    engine = IPOVWAPDetectorEngine.get_instance()

    # 形态 1: 首日早鸟贴线吸筹 (SSS 级)
    sig_sss = VWAPDetectorSignal(
        code="301600", name="首发牛股", price=30.0, vwap=29.8,
        vwap_diff_pct=0.67, is_above_vwap=True, is_ipo_first_day=True,
        vwap_adhesion_ratio=80.0
    )
    engine._synthesize_final_decision(sig_sss)
    assert sig_sss.signal_tier == "SSS"
    assert sig_sss.signal_type == "IPO_FIRST_BUY"
    assert "首发上市紧贴VWAP" in sig_sss.signal_desc

    # 形态 2: 首日临停冲高 (ALERT 级)
    sig_climax = VWAPDetectorSignal(
        code="301601", name="爆炒新股", price=60.0, vwap=40.0,
        vwap_diff_pct=50.0, is_climax_exit=True, climax_preset_sell_price=62.0
    )
    engine._synthesize_final_decision(sig_climax)
    assert sig_climax.signal_tier == "ALERT"
    assert "坚决平仓保利" in sig_climax.signal_desc
    assert sig_climax.signal_type == "CLIMAX_EXIT"

    # 形态 3: 首日破位弱势避险 (ALERT 级)
    sig_weak = VWAPDetectorSignal(
        code="301602", name="破位新股", price=25.0, vwap=28.0,
        vwap_diff_pct=-10.7, is_above_vwap=False, is_ipo_first_day=True
    )
    engine._synthesize_final_decision(sig_weak)
    assert sig_weak.signal_tier == "ALERT"
    assert "首日破位避险" in sig_weak.signal_desc


def test_command_room_dual_mode_views_and_detail_popup():
    """5. 验证集中交易指挥室双模式切换与 locate_stock_in_table 定位"""
    center = IPOTradingCenter.get_instance()
    center._positions.clear()
    center._closed_positions.clear()
    center._signal_iteration_log.clear()

    # 准备历史平仓数据和历史日志数据
    center._closed_positions.append({
        "code": "301555", "name": "历史战绩股", "cost_price": 20.0,
        "exit_price": 25.0, "realized_pnl_pct": 25.0, "exit_date": "2026-09-18",
        "exit_reason": "止盈离场", "realized_pnl_amount": 5000.0
    })
    center._signal_iteration_log.append({
        "timestamp": "2026-09-18 09:45:00", "signal_tier": "SSS",
        "action": "BUY", "code": "301555", "name": "历史战绩股", "reason": "早鸟突破"
    })

    dlg = IPOCommandRoomDialog()
    try:
        dlg.refresh_data()
        # 活跃持仓为0且有平仓历史时，智能自适应切换至 CLOSED 模式
        assert dlg._pos_view_mode == "CLOSED"
        assert dlg.tbl_pos.rowCount() == 1

        # 切换到活跃持仓模式
        dlg._set_pos_view_mode("ACTIVE")
        assert dlg._pos_view_mode == "ACTIVE"
        assert dlg.tbl_pos.rowCount() == 0

        # 切换到历史信号日志模式
        dlg._set_orders_view_mode("HISTORY")
        assert dlg._orders_view_mode == "HISTORY"
        assert dlg.tbl_orders.rowCount() == 1

        # 测试直达定位能力
        dlg.locate_stock_in_table("301555", auto_popup=False)
        assert dlg.tbl_orders.currentRow() == 0
    finally:
        dlg.close()


def test_arbitration_detail_dialog_closed_and_log_views():
    """6. 验证集中仲裁详情窗对平仓复盘与信号迭代日志的富文本渲染"""
    closed_pos_data = {
        "code": "301555", "name": "复盘测试股", "cost_price": 20.0,
        "exit_price": 26.0, "realized_pnl_pct": 30.0, "realized_pnl_amount": 30000.0,
        "exit_date": "2026-09-18", "exit_time": "14:30:00", "exit_reason": "达成目标止盈",
        "entry_reason": "首日贴线吸筹", "signal_tier": "SSS"
    }
    dlg = IPOArbitrationDetailDialog.show_or_update(
        "301555", closed_pos=closed_pos_data
    )
    try:
        assert "历史平仓战绩" in dlg.lbl_code_name.text()
        assert "+30.00%" in dlg.lbl_role_tag.text()
        assert "全流程复盘" in dlg.txt_arbitration_desc.toHtml()
    finally:
        dlg.close()

    # 测试信号日志渲染
    log_data = {
        "code": "301555", "name": "复盘测试股", "action": "FULL_ROTATION_SWAP",
        "price": 20.0, "size_pct": 100.0, "signal_tier": "SSS",
        "reason": "弃弱接力新龙头", "timestamp": "2026-09-18 09:30:00",
        "target_swap_code": "300001", "target_swap_name": "老标的"
    }
    dlg = IPOArbitrationDetailDialog.show_or_update(
        "301555", log_item=log_data
    )
    try:
        assert "信号迭代日志" in dlg.lbl_code_name.text()
        assert "全仓轮动换马目标" in dlg.txt_arbitration_desc.toHtml()
    finally:
        dlg.close()


def test_detector_dialog_locate_and_voice_toggle():
    """7. 验证检测中心 locate_stock_in_table 与语音开关"""
    dlg = IPOSubnewDetectorDialog()
    try:
        # 语音切换
        initial_voice = dlg.voice_alert_enabled
        dlg._on_toggle_voice_alert()
        assert dlg.voice_alert_enabled != initial_voice
        dlg._on_toggle_voice_alert()
        assert dlg.voice_alert_enabled == initial_voice

        # 模拟表格中有标的
        dlg.table.setRowCount(1)
        from PyQt6.QtWidgets import QTableWidgetItem
        dlg.table.setItem(0, 0, QTableWidgetItem("301666"))
        dlg.locate_stock_in_table("301666", auto_popup=False)
        assert dlg.table.currentRow() == 0
    finally:
        dlg.close()
