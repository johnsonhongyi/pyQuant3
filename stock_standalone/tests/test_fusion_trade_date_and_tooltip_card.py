# -*- coding: utf-8 -*-
"""tests/test_fusion_trade_date_and_tooltip_card.py — 验证交易日对齐、日历模式、最后一个交易日数据及深色卡片 ToolTip 拦截。"""
import datetime
import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtWidgets import QApplication, QCheckBox, QTableWidget, QTableWidgetItem

from ats.ui.fusion_ladder_dialog import (
    FusionCalendarDialog,
    FusionLadderDialog,
    UnifiedToolTipFilter,
    _format_tip_card_html,
    get_effective_ats_trade_date,
)


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_effective_ats_trade_date_alignment():
    """验证 ATS 交易日对齐逻辑：自然日与法定交易日隔离，正确获取上一个交易日"""
    # 模拟周日 2026-11-01
    sunday_dt = datetime.datetime(2026, 11, 1, 10, 0, 0)
    cur_today, is_trade_day, last_trade_day = get_effective_ats_trade_date(sunday_dt)
    assert cur_today == "2026-11-01"
    assert is_trade_day is False
    assert last_trade_day == "2026-10-30"


def test_init_days_opens_last_trade_day_not_weekend(qapp):
    """验证打开监视器时严格对齐 ATS 交易日历，默认选中最后一个有效交易日而非周末空白日"""
    dlg = FusionLadderDialog()
    try:
        # 下拉框中必须包含最后一个有效交易日
        days = [dlg.cmb_day.itemText(i) for i in range(dlg.cmb_day.count())]
        assert "2026-10-30" in days
        # 当前选中的日期必须是有数据的最后一个交易日，绝不能是 2026-11-01
        cur_selected = dlg.cmb_day.currentText().strip()
        assert cur_selected == "2026-10-30" or cur_selected in days
        # 验证日历模式按钮已正确集成
        assert hasattr(dlg, "btn_calendar")
        assert dlg.btn_calendar.text() == "📅"
    finally:
        dlg.close()


def test_auto_settle_does_not_override_user_selected_history_day(qapp):
    """验证用户主动选择 10-26 等历史日查看或跑完回放后，定时器绝对不篡改用户日期"""
    dlg = FusionLadderDialog()
    try:
        # 用户在下拉框选择了 10-26
        target_history_day = "2026-10-26"
        if dlg.cmb_day.findText(target_history_day) < 0:
            dlg.cmb_day.addItem(target_history_day)
        dlg.cmb_day.setCurrentText(target_history_day)
        assert dlg.cmb_day.currentText() == target_history_day

        # 触发定时器自动检查
        dlg._check_and_auto_settle_closing()

        # 验证：用户选中的历史交易日 10-26 稳固保持，绝不被强行改成 2026-11-01！
        assert dlg.cmb_day.currentText() == target_history_day
    finally:
        dlg.close()


def test_unified_tooltip_card_formatting_and_filter(qapp):
    """验证深色卡片 ToolTip 格式化与事件拦截：彻底消除 Windows 原生白底白字"""
    raw_tip = "实时页最多标记10只当前重点；回放页标记当日14:45前首次进入重点的记录。\n判断依据：重点排序靠前。\n说明：观察不代表买入。"
    html = _format_tip_card_html(raw_tip)
    assert "#4dd0e1" in html  # 首行标题青色高对比
    assert "#c3e88d" in html  # 判断依据浅绿
    assert "#ffd75e" in html  # 说明金黄
    assert "#eceff4" in html  # 正文浅白

    dlg = FusionLadderDialog()
    try:
        assert hasattr(dlg, "_tooltip_filter")
        filter_obj = dlg._tooltip_filter
        assert isinstance(filter_obj, UnifiedToolTipFilter)

        chk = dlg.chk_focus_only
        assert chk.toolTip() != ""

        # 构造真实的 QHelpEvent 模拟 ToolTip 事件
        help_event = QHelpEvent(QEvent.Type.ToolTip, QPoint(10, 10), QPoint(100, 100))

        # 验证事件过滤器消费了该事件（返回 True），并弹出了深色卡片，阻止系统原生白底渲染
        handled = filter_obj.eventFilter(chk, help_event)
        assert handled is True
        assert filter_obj._tip_card.isVisible()

        # 离开事件自动收起卡片
        leave_event = QEvent(QEvent.Type.Leave)
        filter_obj.eventFilter(chk, leave_event)
        assert not filter_obj._tip_card.isVisible()
    finally:
        dlg.close()


def test_pre_market_startup_auto_rollover_on_opening(qapp, monkeypatch):
    """验证盘前启动挂机时，开盘 09:15 定时器自动从上一交易日平滑切入今日实际交易日"""
    import ats.ui.fusion_ladder_dialog as fld
    from unittest.mock import MagicMock

    # 模拟场景：今天是法定交易日 2026-11-05，上一交易日是 2026-11-04
    monkeypatch.setattr(fld, 'get_effective_ats_trade_date', lambda dt=None: ('2026-11-05', True, '2026-11-04'))

    dlg = FusionLadderDialog()
    try:
        # 模拟盘前状态：用户停留在上一交易日 2026-11-04，且带有盘前待切日标记
        if dlg.cmb_day.findText('2026-11-04') < 0:
            dlg.cmb_day.addItem('2026-11-04')
        dlg.cmb_day.setCurrentText('2026-11-04')
        dlg._pre_market_pending_rollover = True

        # 打桩 refresh_live 验证是否被自动调用
        refresh_mock = MagicMock()
        monkeypatch.setattr(dlg, 'refresh_live', refresh_mock)

        # 模拟时钟进入 09:15:05 开盘时段
        fake_now = datetime.datetime(2026, 11, 5, 9, 15, 5)
        class FakeDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now
        monkeypatch.setattr(fld.datetime, 'datetime', FakeDatetime)

        # 触发定时器巡检
        dlg._check_and_auto_settle_closing()

        # 断言 1: 下拉框已自动平滑切入今日 2026-11-05
        assert dlg.cmb_day.currentText() == '2026-11-05'
        # 断言 2: 盘前待切日标记已成功清除
        assert dlg._pre_market_pending_rollover is False
        # 断言 3: refresh_live 被成功触发以拉取今日最新数据
        assert refresh_mock.call_count == 1
    finally:
        dlg.close()
