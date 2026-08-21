# -*- coding: utf-8 -*-
"""
tests/test_sbc_rearrange.py — SBC 窗口网格平铺重排与 ATS 顶层 CornerWidget 按钮专项测试
"""

import sys
import os
import pytest
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import Qt

# 确保项目根路径
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import json
from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    rearrange_all_sbc_windows,
    open_sbc_chart_dialog,
    save_all_open_sbc_windows,
    restore_all_open_sbc_windows,
    _get_sbc_layout_cfg_path,
    VALID_SBC_PERIODS
)
from ats.ui.main_window import ATSMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_top_tabs_corner_widget_structure(qapp):
    """测试 ATS 主窗口 top_tabs 的 CornerWidget 包含 SBC 重排按钮与刷新状态按钮"""
    win = ATSMainWindow()
    try:
        # 1. 断言 top_tabs 存在
        assert hasattr(win, "top_tabs")
        corner_widget = win.top_tabs.cornerWidget(Qt.Corner.TopRightCorner)
        assert corner_widget is not None
        
        # 2. 检查内部按钮
        buttons = corner_widget.findChildren(QPushButton)
        btn_texts = [b.text() for b in buttons]
        
        # 验证包含 [🪟 SBC 重排] 与 [🔄 刷新状态]，且 SBC 重排在前
        assert any("SBC" in t and "重排" in t for t in btn_texts), f"Buttons found: {btn_texts}"
        assert any("刷新状态" in t for t in btn_texts), f"Buttons found: {btn_texts}"
        
        # 检查顺序：SBC 重排按钮在刷新状态按钮之前
        sbc_idx = next(i for i, t in enumerate(btn_texts) if "SBC" in t and "重排" in t)
        refresh_idx = next(i for i, t in enumerate(btn_texts) if "刷新状态" in t)
        assert sbc_idx < refresh_idx, f"Expected SBC rearrange button before refresh button, got indices {sbc_idx}, {refresh_idx}"
        
        # 3. 检查按钮属性与实例绑定
        assert hasattr(win, "btn_rearrange_sbc")
        assert win.btn_rearrange_sbc is not None
        assert "重排" in win.btn_rearrange_sbc.toolTip()

        # 4. 检查主窗口的 rearrange_all_sbc_windows 成员方法可正常调用
        assert hasattr(win, "rearrange_all_sbc_windows")
        assert callable(win.rearrange_all_sbc_windows)
        win.rearrange_all_sbc_windows()
    finally:
        win.close()


def test_rearrange_all_sbc_windows_with_multiple_dialogs(qapp):
    """测试多个 SBC 窗口调用 rearrange_all_sbc_windows 时的网格平铺与磁吸重置"""
    dlg1 = SBCIntradayChartDialog(code="688826")
    dlg2 = SBCIntradayChartDialog(code="002189")
    dlg3 = SBCIntradayChartDialog(code="300570")

    try:
        # 显示窗口
        dlg1.show()
        dlg2.show()
        dlg3.show()
        qapp.processEvents()

        # 模拟设置某些窗口处于磁吸/半隐藏状态
        dlg2.anchor_edge = "right"
        dlg2.is_hidden_state = True
        dlg2.setWindowOpacity(0.5)

        # 执行重排
        rearrange_all_sbc_windows(parent_win=None)
        qapp.processEvents()

        # 验证所有窗口均已重置磁吸半隐藏状态并完全展开
        for dlg in [dlg1, dlg2, dlg3]:
            assert dlg.anchor_edge is None
            assert dlg.is_hidden_state is False
            assert dlg.windowOpacity() == 1.0
            assert dlg.isVisible()

        # 验证所有窗口坐标已成功重排（坐标唯一不重叠）
        positions = [(dlg.x(), dlg.y()) for dlg in [dlg1, dlg2, dlg3]]
        assert len(set(positions)) == 3, f"Expected 3 distinct positions, got {positions}"

    finally:
        dlg1.close()
        dlg2.close()
        dlg3.close()


def test_rearrange_no_active_dialogs_safe(qapp):
    """测试在无可见 SBC 窗口时调用 rearrange_all_sbc_windows 安全返回不抛异常"""
    # 保证没有抛出任何未捕获异常
    rearrange_all_sbc_windows(parent_win=None)


def test_sbc_set_period_mode(qapp):
    """测试 SBCIntradayChartDialog 的 set_period_mode 切换、按钮选中状态同步与非法值兜底"""
    dlg = SBCIntradayChartDialog(code="688826", initial_period_mode="1m")
    try:
        dlg.show()
        qapp.processEvents()

        # 1. 默认应为 '1m'
        assert dlg._current_period_mode == "1m"
        btn_1m = next((b for b in dlg.btn_group_period.buttons() if b.property("period_mode") == "1m"), None)
        assert btn_1m is not None and btn_1m.isChecked()

        # 2. 依次测试各个有效周期的切换与 UI 按钮选中态同步
        test_periods = ["2d", "3d", "5m", "30m", "60m", "day"]
        for p in test_periods:
            dlg.set_period_mode(p, reload=False, save=False)
            assert dlg._current_period_mode == p
            btn = next((b for b in dlg.btn_group_period.buttons() if b.property("period_mode") == p), None)
            assert btn is not None and btn.isChecked()
            assert not btn_1m.isChecked()

        # 3. 测试非法周期模式传入时的安全兜底 (自动回退至 '1m')
        dlg.set_period_mode("invalid_mode_xyz", reload=False, save=False)
        assert dlg._current_period_mode == "1m"
        assert btn_1m.isChecked()

        dlg.set_period_mode(None, reload=False, save=False)
        assert dlg._current_period_mode == "1m"
        assert btn_1m.isChecked()

    finally:
        dlg.close()


def test_sbc_save_all_open_windows_with_period(qapp):
    """测试多个处于不同周期的 SBC 窗口在调用 save_all_open_sbc_windows 时能够正确落盘周期模式"""
    dlg1 = SBCIntradayChartDialog(code="688826")
    dlg2 = SBCIntradayChartDialog(code="002189")
    dlg3 = SBCIntradayChartDialog(code="300570")

    try:
        dlg1.show()
        dlg2.show()
        dlg3.show()
        qapp.processEvents()

        # 设置不同周期
        dlg1.set_period_mode("5m", reload=False, save=False)
        dlg2.set_period_mode("2d", reload=False, save=False)
        dlg3.set_period_mode("day", reload=False, save=False)

        # 全局持久化保存
        save_all_open_sbc_windows()

        # 检查持久化配置文件
        cfg_path = _get_sbc_layout_cfg_path()
        assert os.path.exists(cfg_path)
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        sbc_list = data.get("sbc_open_windows", [])
        saved_dict = {item.get("code"): item.get("period_mode") for item in sbc_list}

        assert saved_dict.get("688826") == "5m"
        assert saved_dict.get("002189") == "2d"
        assert saved_dict.get("300570") == "day"

        # 检查 sbc_period_modes 字段
        assert "sbc_period_modes" in data
        assert data["sbc_period_modes"].get("688826") == "5m"
        assert data["sbc_period_modes"].get("002189") == "2d"
        assert data["sbc_period_modes"].get("300570") == "day"

    finally:
        dlg1.close()
        dlg2.close()
        dlg3.close()


def test_sbc_restore_all_open_windows_with_period(qapp):
    """测试 restore_all_open_sbc_windows 启动恢复时能准确还原各窗口原本选择的周期"""
    cfg_path = _get_sbc_layout_cfg_path()
    mock_data = {
        "sbc_open_windows": [
            {"code": "600519", "x": 100, "y": 100, "width": 680, "height": 420, "period_mode": "30m"},
            {"code": "000001", "x": 200, "y": 200, "width": 680, "height": 420, "period_mode": "3d"}
        ],
        "sbc_period_modes": {
            "600519": "30m",
            "000001": "3d"
        }
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(mock_data, f, ensure_ascii=False, indent=2)

    # 恢复窗口
    restore_all_open_sbc_windows(parent_win=None)
    qapp.processEvents()

    restored_dlgs = [w for w in QApplication.topLevelWidgets() if isinstance(w, SBCIntradayChartDialog) and w.isVisible()]
    try:
        dlg_map = {dlg.code: dlg for dlg in restored_dlgs}
        assert "600519" in dlg_map
        assert "000001" in dlg_map

        assert dlg_map["600519"]._current_period_mode == "30m"
        btn_30m = next((b for b in dlg_map["600519"].btn_group_period.buttons() if b.property("period_mode") == "30m"), None)
        assert btn_30m is not None and btn_30m.isChecked()

        assert dlg_map["000001"]._current_period_mode == "3d"
        btn_3d = next((b for b in dlg_map["000001"].btn_group_period.buttons() if b.property("period_mode") == "3d"), None)
        assert btn_3d is not None and btn_3d.isChecked()

    finally:
        for dlg in restored_dlgs:
            dlg.close()


def test_open_sbc_chart_dialog_with_explicit_period(qapp):
    """测试 open_sbc_chart_dialog 显式传入 period_mode 参数时正确初始化与唤醒切换"""
    dlg = open_sbc_chart_dialog(None, code="688981", period_mode="60m")
    try:
        assert dlg is not None
        assert dlg._current_period_mode == "60m"
        btn_60m = next((b for b in dlg.btn_group_period.buttons() if b.property("period_mode") == "60m"), None)
        assert btn_60m is not None and btn_60m.isChecked()

        # 再次调用同一个窗口，切换到 5m
        dlg2 = open_sbc_chart_dialog(None, code="688981", period_mode="5m")
        assert dlg2 is dlg
        assert dlg._current_period_mode == "5m"
        btn_5m = next((b for b in dlg.btn_group_period.buttons() if b.property("period_mode") == "5m"), None)
        assert btn_5m is not None and btn_5m.isChecked()

    finally:
        if dlg:
            dlg.close()


def test_backward_compatibility_fallback_to_1m(qapp):
    """测试当历史配置文件缺少 period_mode 字段时，自动安全回退为 1m 分时且不报错"""
    cfg_path = _get_sbc_layout_cfg_path()
    mock_legacy_data = {
        "sbc_open_windows": [
            {"code": "002594", "x": 150, "y": 150, "width": 680, "height": 420}
        ]
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(mock_legacy_data, f, ensure_ascii=False, indent=2)

    restore_all_open_sbc_windows(parent_win=None)
    qapp.processEvents()

    restored_dlgs = [w for w in QApplication.topLevelWidgets() if isinstance(w, SBCIntradayChartDialog) and w.isVisible() and w.code == "002594"]
    try:
        assert len(restored_dlgs) == 1
        dlg = restored_dlgs[0]
        assert dlg._current_period_mode == "1m"
        btn_1m = next((b for b in dlg.btn_group_period.buttons() if b.property("period_mode") == "1m"), None)
        assert btn_1m is not None and btn_1m.isChecked()
    finally:
        for dlg in restored_dlgs:
            dlg.close()


def test_sbc_all_periods_and_month_support(qapp):
    """测试包含 2d, 3d, week, month 在内的全部周期支持及按钮初始化"""
    assert "month" in VALID_SBC_PERIODS
    assert "week" in VALID_SBC_PERIODS
    assert "2d" in VALID_SBC_PERIODS
    assert "3d" in VALID_SBC_PERIODS

    dlg = SBCIntradayChartDialog(code="688313", initial_period_mode="month")
    try:
        dlg.show()
        qapp.processEvents()

        assert dlg._current_period_mode == "month"
        btn_month = next((b for b in dlg.btn_group_period.buttons() if b.property("period_mode") == "month"), None)
        assert btn_month is not None and btn_month.isChecked()

        # 切换到 week
        dlg.set_period_mode("week", reload=False)
        assert dlg._current_period_mode == "week"
        btn_week = next((b for b in dlg.btn_group_period.buttons() if b.property("period_mode") == "week"), None)
        assert btn_week is not None and btn_week.isChecked()
    finally:
        dlg.close()


def test_sbc_maximized_normal_geometry_persistence_and_screen_limit(qapp):
    """测试 SBC 窗口最大化时不记忆全屏尺寸，且恢复与保存尺寸绝不超过屏幕规格 2/3"""
    dlg = SBCIntradayChartDialog(code="001309")
    try:
        dlg.resize(600, 400)
        dlg.show()
        qapp.processEvents()

        # 检查最大允许尺寸 (2/3 屏幕规格)
        max_w, max_h = dlg._get_max_allowed_sbc_size()
        screen = dlg.screen() or QApplication.primaryScreen()
        if screen:
            ag = screen.availableGeometry()
            assert max_w <= int(ag.width() * 2 / 3) + 1
            assert max_h <= int(ag.height() * 2 / 3) + 1

        # 模拟提取正常尺寸
        effective_geo = dlg._get_effective_normal_geometry()
        assert effective_geo is not None
        assert effective_geo["width"] <= max_w
        assert effective_geo["height"] <= max_h

        # 模拟窗口最大化后提取有效尺寸 (不应返回全屏尺寸，而是返回正常窗口尺寸)
        dlg.showMaximized()
        qapp.processEvents()
        max_effective_geo = dlg._get_effective_normal_geometry()
        if max_effective_geo:
            assert max_effective_geo["width"] <= max_w
            assert max_effective_geo["height"] <= max_h
    finally:
        dlg.close()


def test_sbc_initial_focus_on_period_button(qapp):
    """测试 SBC 窗口打开后默认焦点在当前周期按钮上，便于键盘与鼠标直接操作"""
    dlg = SBCIntradayChartDialog(code="688826", initial_period_mode="30m")
    try:
        dlg.show()
        qapp.processEvents()

        btn_30m = next((b for b in dlg.btn_group_period.buttons() if b.property("period_mode") == "30m"), None)
        assert btn_30m is not None
        assert btn_30m.isChecked()
        assert btn_30m.hasFocus() or dlg.focusWidget() == btn_30m
    finally:
        dlg.close()


def test_rearrange_with_maximized_sbc_dialog(qapp):
    """测试当 SBC 窗口处于最大化查看时，点击重排能自动恢复窗口大小并正确执行网格平铺"""
    dlg1 = SBCIntradayChartDialog(code="688826")
    dlg2 = SBCIntradayChartDialog(code="002189")
    dlg3 = SBCIntradayChartDialog(code="300570")

    try:
        dlg1.show()
        dlg2.show()
        dlg3.show()
        qapp.processEvents()

        # 模拟用户将 dlg1 最大化查看
        dlg1.showMaximized()
        qapp.processEvents()
        assert dlg1.isMaximized()

        # 执行重排
        rearrange_all_sbc_windows(parent_win=None)
        qapp.processEvents()

        # 1. 验证 dlg1 已经自动退出最大化状态
        assert not dlg1.isMaximized()
        assert not dlg2.isMaximized()
        assert not dlg3.isMaximized()

        # 2. 验证所有窗口尺寸恢复为与同屏正常窗口相同的一致紧凑尺寸（绝非 2/3 或全屏巨型尺寸）
        screen = dlg1.screen() or QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            # 验证 dlg1 恢复后与 dlg2, dlg3 尺寸保持完全一致（对应图 1 原始并排大小）
            assert dlg1.width() == dlg2.width() == dlg3.width()
            assert dlg1.height() == dlg2.height() == dlg3.height()
            assert dlg1.width() <= int(sg.width() * 0.5)
            assert dlg1.height() <= int(sg.height() * 0.6)

        # 3. 验证所有窗口坐标已成功平铺，互不重叠
        positions = [(dlg.x(), dlg.y()) for dlg in [dlg1, dlg2, dlg3]]
        assert len(set(positions)) == 3, f"Expected 3 distinct positions, got {positions}"

    finally:
        dlg1.close()
        dlg2.close()
        dlg3.close()

