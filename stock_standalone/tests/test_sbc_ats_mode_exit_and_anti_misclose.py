# -*- coding: utf-8 -*-
"""
tests/test_sbc_ats_mode_exit_and_anti_misclose.py
-------------------------------------------------
专项测试：
1. 【SBC防误关加固】：标题栏关闭按钮、系统菜单、任务栏及退出流程中绝对放行，仅在画布内操作时拦截；
2. 【ATS模式Alt+点击关闭】：ATS 模式下按住 Alt 点击关闭时，联动关闭所有其他 SBC 窗口并持久化，不杀 ATS 主程序；
3. 【ATS主窗口退出联动】：ATS 关闭流程中，优雅遍历关闭同进程所有 SBC 窗口。
"""
import time
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QCloseEvent

from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    SBCWindowMemoryManager,
    close_all_open_sbc_dialogs,
    get_all_active_sbc_dialogs,
    _is_ats_shutting_down
)


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setProperty("is_app_exiting", False)
    return app


def test_anti_misclose_allows_titlebar_and_shutdown(qapp, monkeypatch):
    """验证防误关机制：标题栏区域或退出期绝对放行，画布内误操作精准拦截"""
    dlg = SBCIntradayChartDialog(code="688347")
    dlg.resize(800, 600)
    dlg.show()
    
    # 模拟刚点击过鼠标，处于锁定期
    now = time.time()
    dlg._esc_mouse_lock_until = now + 10.0
    if hasattr(dlg, "canvas") and dlg.canvas:
        dlg.canvas._esc_mouse_lock_until = now + 10.0

    # 1. 模拟鼠标在标题栏关闭按钮（假设光标在窗口外部或非画布区域）
    # 画布区域为窗口中央，标题栏在 y < 0 或者在顶部工具栏上方
    monkeypatch.setattr("PyQt6.QtGui.QCursor.pos", lambda: dlg.mapToGlobal(QPoint(780, 10)))
    
    # 模拟不是处于退出期，不是 Alt 点击
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args: False)
    qapp.setProperty("is_app_exiting", False)

    # 标题栏关闭应该被放行（canvas.rect().contains 为 False）
    evt = QCloseEvent()
    dlg.closeEvent(evt)
    assert evt.isAccepted(), "标题栏关闭应该被正常放行，不能被防误关拦截！"

    # 2. 模拟鼠标在画布正中央（双击/右键误触场景）
    dlg2 = SBCIntradayChartDialog(code="600000")
    dlg2.resize(800, 600)
    dlg2.show()
    dlg2._esc_mouse_lock_until = now + 10.0
    if hasattr(dlg2, "canvas") and dlg2.canvas:
        dlg2.canvas._esc_mouse_lock_until = now + 10.0
        # 将光标定位在 canvas 内部
        center_in_canvas = dlg2.canvas.rect().center()
        global_canvas_pos = dlg2.canvas.mapToGlobal(center_in_canvas)
        monkeypatch.setattr("PyQt6.QtGui.QCursor.pos", lambda: global_canvas_pos)

        evt2 = QCloseEvent()
        dlg2.closeEvent(evt2)
        assert not evt2.isAccepted(), "画布内部操作派发的关闭事件应该被防误关拦截！"

    # 3. 模拟处于 ATS 退出期（is_app_exiting 为 True）
    # 即使光标在画布内，也必须绝对放行退出
    qapp.setProperty("is_app_exiting", True)
    evt3 = QCloseEvent()
    dlg2.closeEvent(evt3)
    assert evt3.isAccepted(), "处于退出期时必须绝对放行所有关闭事件！"

    qapp.setProperty("is_app_exiting", False)
    dlg.close()
    dlg2.close()


def test_alt_close_in_ats_mode_closes_all_sbcs_without_quitting_app(qapp, monkeypatch):
    """验证 ATS 模式下 Alt+点击关闭：批量关闭所有同进程 SBC 窗口，不调用 app.quit()"""
    dlg1 = SBCIntradayChartDialog(code="688347")
    dlg2 = SBCIntradayChartDialog(code="600000")
    dlg3 = SBCIntradayChartDialog(code="000001")
    dlg1.show()
    dlg2.show()
    dlg3.show()

    # 确保都被注册到活跃列表
    active = get_all_active_sbc_dialogs()
    assert dlg1 in active
    assert dlg2 in active
    assert dlg3 in active

    # 模拟处于 ATS 模式
    dlg1.is_ats_sbc_mode = lambda: True
    dlg2.is_ats_sbc_mode = lambda: True
    dlg3.is_ats_sbc_mode = lambda: True

    # 模拟按住 Alt 键
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args: True)

    app_quit_called = False
    def fake_quit():
        nonlocal app_quit_called
        app_quit_called = True
    monkeypatch.setattr(qapp, "quit", fake_quit)

    # 操盘手按住 Alt 点击 dlg1 的关闭按钮
    dlg1.close()

    # 验证：dlg1, dlg2, dlg3 全部被关闭
    assert not dlg1.isVisible() or getattr(dlg1, "_is_closing", False)
    assert not dlg2.isVisible() or getattr(dlg2, "_is_closing", False)
    assert not dlg3.isVisible() or getattr(dlg3, "_is_closing", False)

    # 验证：ATS 主程序未被误杀死 (app.quit 未被调用)
    assert not app_quit_called, "ATS 模式下 Alt+关闭绝不能误调用 app.quit() 杀死主程序！"


def test_close_all_open_sbc_dialogs_helper(qapp):
    """验证 close_all_open_sbc_dialogs 工具函数"""
    dlg1 = SBCIntradayChartDialog(code="688001")
    dlg2 = SBCIntradayChartDialog(code="688002")
    dlg1.show()
    dlg2.show()

    assert dlg1.isVisible()
    assert dlg2.isVisible()

    closed_cnt = close_all_open_sbc_dialogs()
    assert closed_cnt >= 2
    assert getattr(dlg1, "_is_closing", False) or not dlg1.isVisible()
    assert getattr(dlg2, "_is_closing", False) or not dlg2.isVisible()


def test_single_sbc_close_removes_from_disk_and_does_not_persist(qapp, tmp_path, monkeypatch):
    """验证手动单独关闭 SBC 窗口：彻底从磁盘和内存中除名，下次启动绝不自动打开"""
    import json
    from ats.ui.intraday_strategy_dialog import _remove_sbc_open_record, _get_sbc_layout_cfg_path

    fake_cfg = str(tmp_path / "sbc_layout.json")
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog._get_sbc_layout_cfg_path", lambda: fake_cfg)

    # 预设磁盘上有 000001 和 600000 两个打开窗口
    initial_data = {
        "sbc_open_windows": [
            {"code": "000001", "x": 100, "y": 100, "width": 680, "height": 420},
            {"code": "600000", "x": 800, "y": 100, "width": 680, "height": 420},
        ]
    }
    with open(fake_cfg, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)

    # 操盘手单独关闭了 000001
    dlg = SBCIntradayChartDialog(code="000001")
    dlg.show()
    # 触发单窗关闭
    dlg.close()

    # 读取磁盘配置，验证 000001 已被彻底除名，只保留 600000
    with open(fake_cfg, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    codes_on_disk = [item["code"] for item in saved_data.get("sbc_open_windows", [])]
    assert "000001" not in codes_on_disk, "单独关闭的个股窗口必须从磁盘配置彻底移除！"
    assert "600000" in codes_on_disk, "未关闭的个股窗口应继续保留！"

