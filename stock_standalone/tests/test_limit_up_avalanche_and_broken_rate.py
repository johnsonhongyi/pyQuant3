# -*- coding: utf-8 -*-
"""
专项测试：验证涨停/退潮雪崩真实炸板率与市场温度科学计算，杜绝0样本误报100%炸板与非交易时间乱播报
"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication

from ats.limit_up_engine import LimitUpEngine
from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_broken_rate_is_zero_when_no_attempts():
    """当冲板总数为0时，封板率与真实炸板率均为0.0%，绝不能误报为100%炸板"""
    engine = LimitUpEngine.get_instance()
    
    # 模拟构建全市场 DataFrame: 2000上涨, 3000下跌
    pcts = [2.0] * 2000 + [-2.0] * 3000
    df = pd.DataFrame({"pct": pcts})

    # 无冲板记录
    summary = engine.get_market_limit_up_summary(date_str="2099-01-01", current_df=df)
    
    assert summary["total_attempts"] == 0
    assert summary["seal_rate"] == 0.0
    assert summary["broken_rate"] == 0.0  # 真实炸板率必须是 0.0%，绝非 100.0%
    assert summary["is_avalanche"] is False
    # 市场温度 = 2000 / 5000 * 100 = 40.0℃
    assert summary["market_temp"] == pytest.approx(40.0, rel=1e-2)
    assert "100%" not in summary["defense_status"]


def test_broken_rate_scientific_calculation():
    """验证真实冲板样本下的封板率与炸板率科学计算"""
    engine = LimitUpEngine.get_instance()

    # 模拟 40 只封死涨停，10 只炸板
    records = []
    for i in range(40):
        records.append({"code": f"6000{i:02d}", "name": f"涨停{i}", "is_limit_up": True, "is_broken": False, "consecutive_boards": 1})
    for j in range(10):
        records.append({"code": f"0000{j:02d}", "name": f"炸板{j}", "is_limit_up": False, "is_broken": True, "consecutive_boards": 0})

    pcts = [3.0] * 3000 + [-1.0] * 2000
    df = pd.DataFrame({"pct": pcts})

    with patch.object(engine, "_current_live_records", records):
        summary = engine.get_market_limit_up_summary(current_df=df)

    assert summary["zt_count"] == 40
    assert summary["broken_count"] == 10
    assert summary["total_attempts"] == 50
    # 封板率: 40/50 = 80.0%, 炸板率: 10/50 = 20.0%
    assert summary["seal_rate"] == 80.0
    assert summary["broken_rate"] == 20.0
    assert summary["market_temp"] == pytest.approx(60.0, rel=1e-2)


def test_dialog_voice_alert_blocked_outside_trading_hours(qapp):
    """非交易时段（夜间/休市/周末）坚决静音，严禁弹出盘中开仓/止损交易级语音骚扰"""
    dialog = DailyLimitUpDialog.__new__(DailyLimitUpDialog)
    dialog.is_voice_alert_enabled = True
    dialog.lbl_status = MagicMock()
    dialog.btn_kpi_zt = MagicMock()
    dialog.btn_kpi_ladder = MagicMock()
    dialog.btn_kpi_broken = MagicMock()
    dialog.lbl_kpi_seal = MagicMock()
    dialog.btn_top_leader = MagicMock()
    dialog._update_kpi_styles = MagicMock()

    # 极端退潮雪崩数据
    summary = {
        "is_avalanche": True,
        "market_temp": 15.0,
        "broken_rate": 60.0,
        "total_attempts": 20,
        "down_cnt": 4500,
        "up_cnt": 500,
        "limit_down_cnt": 35,
        "defense_status": "全市场退潮雪崩",
        "zt_count": 8,
        "broken_count": 12,
        "seal_rate": 40.0
    }

    # 模拟当前为非交易时段（如晚上 22:25）
    with patch("ats.tdx_realtime_fetcher.is_trading_time", return_value=(False, "closed")), \
         patch("ats.alert_notifier.AlertNotifier.get_instance") as mock_notifier:
        
        notifier_inst = MagicMock()
        mock_notifier.return_value = notifier_inst

        dialog._update_kpi_display(summary)

        # 坚决不调用 notify_special_signal
        assert not notifier_inst.notify_special_signal.called


def test_dialog_voice_alert_with_accurate_temperature_in_trading_hours(qapp):
    """在交易时段触发雪崩时，语音播报文案准确携带市场温度与真实炸板率"""
    dialog = DailyLimitUpDialog.__new__(DailyLimitUpDialog)
    dialog.is_voice_alert_enabled = True
    dialog._last_avalanche_voice_ts = 0.0
    dialog.lbl_status = MagicMock()
    dialog.btn_kpi_zt = MagicMock()
    dialog.btn_kpi_ladder = MagicMock()
    dialog.btn_kpi_broken = MagicMock()
    dialog.lbl_kpi_seal = MagicMock()
    dialog.btn_top_leader = MagicMock()
    dialog._update_kpi_styles = MagicMock()

    summary = {
        "is_avalanche": True,
        "market_temp": 18.5,
        "broken_rate": 55.0,
        "total_attempts": 20,
        "down_cnt": 4200,
        "up_cnt": 800,
        "limit_down_cnt": 28,
        "defense_status": "全市场退潮雪崩",
        "zt_count": 9,
        "broken_count": 11,
        "seal_rate": 45.0
    }

    # 模拟当前为交易时段（如 10:30）
    with patch("ats.tdx_realtime_fetcher.is_trading_time", return_value=(True, "trading")), \
         patch("ats.alert_notifier.AlertNotifier.get_instance") as mock_notifier:
        
        notifier_inst = MagicMock()
        mock_notifier.return_value = notifier_inst

        dialog._update_kpi_display(summary)

        # 必须触发播报，且文案准确
        assert notifier_inst.notify_special_signal.called
        call_pos_args = notifier_inst.notify_special_signal.call_args[0]
        reason_text = call_pos_args[2] if len(call_pos_args) >= 3 else notifier_inst.notify_special_signal.call_args[1].get("reason", "")
        # 必须包含真实温度 18.5℃ 和 真实炸板率 55.0%
        assert "18.5℃" in reason_text
        assert "55.0%" in reason_text
        assert "100%" not in reason_text  # 严禁出现虚假 100% 炸板
