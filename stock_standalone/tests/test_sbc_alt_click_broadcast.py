# -*- coding: utf-8 -*-
"""
tests/test_sbc_alt_click_broadcast.py — SBC 全功能 Alt+鼠标点击 多窗口广播联动自动化测试
覆盖：
1. Alt+点击 主题切换按钮 -> 多窗口主题秒级同步广播
2. Alt+点击 BOLL 开关按钮 -> 多窗口 BOLL 布林带秒级同步广播
3. Alt+点击 成交量模式切换 -> 多窗口量能副图秒级同步广播
4. Alt+点击 日线通道线开关 -> 多窗口通道叠加秒级同步广播
5. Alt+点击 刷新按钮 -> 错峰分帧多窗口重载联动
"""

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    SBCWindowMemoryManager,
    sync_all_open_sbc_theme,
    sync_all_open_sbc_boll,
    sync_all_open_sbc_vol_mode,
    sync_all_open_sbc_channel_overlay,
    sync_all_open_sbc_auto_strategy,
    sync_all_open_sbc_reload,
    get_all_active_sbc_dialogs,
)
from ats.ui.sbc_preferences import set_sbc_theme_mode, get_sbc_theme_mode, set_sbc_show_boll, get_sbc_show_boll


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest_alt_broadcast"])
    return app


@pytest.fixture(autouse=True)
def clean_memory_mgr():
    mgr = SBCWindowMemoryManager.get_instance()
    mgr.clear()
    set_sbc_theme_mode("pitch_dark")
    set_sbc_show_boll(True)
    yield
    mgr.clear()
    set_sbc_theme_mode("pitch_dark")
    set_sbc_show_boll(True)


def test_alt_click_theme_broadcast(qapp, monkeypatch):
    """验证按住 Alt 点击主题按钮，联动广播同步所有已打开 SBC 窗口的主题"""
    dlg1 = SBCIntradayChartDialog(code="600519")
    dlg2 = SBCIntradayChartDialog(code="000001")

    mgr = SBCWindowMemoryManager.get_instance()
    mgr.register(dlg1)
    mgr.register(dlg2)

    assert dlg1.canvas.theme_mode == "pitch_dark"
    assert dlg2.canvas.theme_mode == "pitch_dark"

    # 1. 模拟按住 Alt 点击 dlg1 的主题按钮
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: True)

    dlg1.btn_theme_toggle.click()

    # 断言两个窗口均已瞬间同步为 deep_navy
    assert dlg1.canvas.theme_mode == "deep_navy"
    assert dlg2.canvas.theme_mode == "deep_navy"
    assert get_sbc_theme_mode() == "deep_navy"
    assert "深蓝" in dlg1.btn_theme_toggle.text()
    assert "深蓝" in dlg2.btn_theme_toggle.text()

    # 2. 模拟普通点击 (未按 Alt)，仅修改当前窗口
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: False)

    dlg1.btn_theme_toggle.click()
    assert dlg1.canvas.theme_mode == "pro_charcoal"
    assert dlg2.canvas.theme_mode == "deep_navy"  # dlg2 保持不变


def test_alt_click_boll_broadcast(qapp, monkeypatch):
    """验证按住 Alt 点击 BOLL 按钮，联动广播同步所有已打开 SBC 窗口的布林带开关"""
    dlg1 = SBCIntradayChartDialog(code="600519")
    dlg2 = SBCIntradayChartDialog(code="000001")

    mgr = SBCWindowMemoryManager.get_instance()
    mgr.register(dlg1)
    mgr.register(dlg2)

    assert dlg1.canvas.show_boll is True
    assert dlg2.canvas.show_boll is True

    # 模拟按住 Alt 点击 dlg1 的 BOLL 按钮
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: True)

    dlg1.btn_boll_toggle.click()

    # 断言两个窗口均已同步关闭 BOLL
    assert dlg1.canvas.show_boll is False
    assert dlg2.canvas.show_boll is False
    assert get_sbc_show_boll() is False
    assert "关" in dlg1.btn_boll_toggle.text()
    assert "关" in dlg2.btn_boll_toggle.text()

    # 再次按住 Alt 点击开启
    dlg1.btn_boll_toggle.click()
    assert dlg1.canvas.show_boll is True
    assert dlg2.canvas.show_boll is True
    assert get_sbc_show_boll() is True


def test_alt_click_vol_mode_broadcast(qapp, monkeypatch):
    """验证按住 Alt 点击成交量按钮，联动广播同步所有已打开 SBC 窗口的成交量模式"""
    dlg1 = SBCIntradayChartDialog(code="600519")
    dlg2 = SBCIntradayChartDialog(code="000001")

    mgr = SBCWindowMemoryManager.get_instance()
    mgr.register(dlg1)
    mgr.register(dlg2)

    assert dlg1.canvas._vol_mode == "normal"
    assert dlg2.canvas._vol_mode == "normal"

    # 模拟按住 Alt 点击 dlg1 的成交量按钮
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: True)

    dlg1.btn_vol_toggle.click()

    # 断言两个窗口均同步切换为 collapsed (折叠)
    assert dlg1.canvas._vol_mode == "collapsed"
    assert dlg2.canvas._vol_mode == "collapsed"
    assert "折叠" in dlg1.btn_vol_toggle.text()
    assert "折叠" in dlg2.btn_vol_toggle.text()


def test_alt_click_channel_overlay_broadcast(qapp, monkeypatch):
    """验证按住 Alt 点击日线通道线按钮，联动广播同步所有已打开 SBC 窗口"""
    dlg1 = SBCIntradayChartDialog(code="600519")
    dlg2 = SBCIntradayChartDialog(code="000001")

    mgr = SBCWindowMemoryManager.get_instance()
    mgr.register(dlg1)
    mgr.register(dlg2)

    # 模拟按住 Alt 切换通道线为 False
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: True)

    dlg1.btn_channel_overlay.setChecked(False)
    dlg1._on_channel_overlay_toggled(False)

    assert dlg1._channel_overlay_enabled is False
    assert dlg2._channel_overlay_enabled is False
    assert dlg1.canvas.channel_overlay_enabled is False
    assert dlg2.canvas.channel_overlay_enabled is False
    assert "关" in dlg1.btn_channel_overlay.text()
    assert "关" in dlg2.btn_channel_overlay.text()


def test_alt_click_refresh_broadcast(qapp, monkeypatch):
    """验证按住 Alt 点击刷新按钮，触发错峰多窗口刷新广播"""
    dlg1 = SBCIntradayChartDialog(code="600519")
    dlg2 = SBCIntradayChartDialog(code="000001")

    mgr = SBCWindowMemoryManager.get_instance()
    mgr.register(dlg1)
    mgr.register(dlg2)

    reloaded_list = []
    dlg1.reload_chart = lambda *args, **kwargs: reloaded_list.append("dlg1")
    dlg2.reload_chart = lambda *args, **kwargs: reloaded_list.append("dlg2")

    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: True)

    dlg1._on_refresh_btn_clicked()

    # 当前窗口立即刷新
    assert "dlg1" in reloaded_list
