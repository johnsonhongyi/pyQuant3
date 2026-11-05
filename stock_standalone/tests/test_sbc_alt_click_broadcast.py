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

    sync_all_open_sbc_clear_cache,

    sync_all_open_sbc_log_panel,

    sync_all_open_sbc_eval_r,

    SBCGlobalFlashController,

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





def test_alt_click_clear_cache_staggered_queue(qapp, monkeypatch):

    """验证按住 Alt 点击【清缓】按钮，触发全窗口统一队列错峰清理调度"""

    dlg1 = SBCIntradayChartDialog(code="600519")

    dlg2 = SBCIntradayChartDialog(code="000001")



    mgr = SBCWindowMemoryManager.get_instance()

    mgr.register(dlg1)

    mgr.register(dlg2)



    cleared_records = []



    def mock_clear_reload(self, is_batch=False, batch_idx=1, batch_total=1):

        cleared_records.append((self.code, is_batch, batch_idx, batch_total))



    monkeypatch.setattr(SBCIntradayChartDialog, "_execute_clear_cache_and_reload", mock_clear_reload)



    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.get_all_active_sbc_dialogs", lambda: [dlg1, dlg2])



    # 1. 模拟按住 Alt 点击 dlg1 的清缓按钮

    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: True)

    dlg1._on_clear_cache_clicked()



    # 焦点窗口立即被清理并调度

    assert len(cleared_records) >= 1

    assert cleared_records[0][0] == "600519"

    assert cleared_records[0][1] is True  # is_batch 为 True

    assert cleared_records[0][3] == 2     # batch_total 为 2



    # 2. 模拟普通点击 (未按 Alt)，仅清理当前单个窗口

    cleared_records.clear()

    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: False)

    dlg1._on_clear_cache_clicked()



    assert len(cleared_records) == 1

    assert cleared_records[0][0] == "600519"

    assert cleared_records[0][1] is False  # 非 batch 单窗





def test_alt_click_log_panel_broadcast(qapp, monkeypatch):

    """验证按住 Alt 点击日志按钮，触发所有窗口联动展开/收起"""

    dlg1 = SBCIntradayChartDialog(code="600519")

    dlg2 = SBCIntradayChartDialog(code="000001")



    mgr = SBCWindowMemoryManager.get_instance()

    mgr.register(dlg1)

    mgr.register(dlg2)



    assert dlg1.log_box.isHidden() is True

    assert dlg2.log_box.isHidden() is True



    # 模拟按住 Alt 点击日志按钮

    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: True)

    dlg1._toggle_log_panel()



    # 两个窗口均应联动展开

    assert dlg1.log_box.isHidden() is False

    assert dlg2.log_box.isHidden() is False



    # 再次按住 Alt 点击收起

    dlg1._toggle_log_panel()

    assert dlg1.log_box.isHidden() is True

    assert dlg2.log_box.isHidden() is True





def test_alt_click_eval_r_broadcast(qapp, monkeypatch):

    """验证按住 Alt 点击自动测算按钮，触发所有窗口联动开启/关闭"""

    dlg1 = SBCIntradayChartDialog(code="600519")

    dlg2 = SBCIntradayChartDialog(code="000001")



    mgr = SBCWindowMemoryManager.get_instance()

    mgr.register(dlg1)

    mgr.register(dlg2)



    assert dlg1.auto_eval_enabled is True

    assert dlg2.auto_eval_enabled is True



    # 模拟按住 Alt 点击关闭自动测算

    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args, **kwargs: True)

    dlg1._on_eval_r_clicked(toggle=True)



    assert dlg1.auto_eval_enabled is False

    assert dlg2.auto_eval_enabled is False



    # 再次按住 Alt 点击开启

    dlg1._on_eval_r_clicked(toggle=True)

    assert dlg1.auto_eval_enabled is True

    assert dlg2.auto_eval_enabled is True





def test_sbc_open_gap_up_down_10s_slow_flash(qapp):

    """验证 SBC 撮合成交与开盘价高开/反向低开 间隔 2 秒慢闪与全局控制器调度"""

    import time

    ctrl = SBCGlobalFlashController.get_instance()

    assert ctrl.FLASH_CYCLE_SECONDS == 2.0      # 🌟 验证间隔 2 秒呼吸周期

    assert ctrl.MAX_CONCURRENT_FLASH == 2       # 🌟 验证全局限流最多 2 个窗口同时慢闪防卡顿



    dlg = SBCIntradayChartDialog(code="600118")

    canvas = dlg.canvas

    canvas.last_close = 34.33



    # 1. 触发高开慢闪

    canvas.trigger_open_flash(41.00)

    assert canvas._open_flash_price == 41.00

    assert ctrl.is_canvas_flashing(canvas) is True



    # 2. 验证间隔 2 秒正弦呼吸 Alpha 与线宽

    alpha, line_w = ctrl.get_pulse_alpha_and_width(canvas)

    assert 100 <= alpha <= 255

    assert 1.2 <= line_w <= 2.1



    # 3. 验证 10 秒后超时自动移出并恢复稳态常亮

    ctrl._active_flash_entries[canvas] = time.time() - 11.0

    ctrl._on_master_tick()

    assert ctrl.is_canvas_flashing(canvas) is False

    alpha_end, line_w_end = ctrl.get_pulse_alpha_and_width(canvas)

    assert alpha_end == 255

    assert line_w_end == 1.2





def test_sbc_clear_notice_single_vs_batch_modes(qapp, monkeypatch):
    from PyQt6.QtWidgets import QLabel, QWidget
    from PyQt6.QtGui import QMouseEvent

    """验证清缓存通知：单独操作弹单窗通知，批量操作由协调器仅弹 1 个置顶汇总窗口"""

    import ats.ui.intraday_strategy_dialog as sbc_mod

    from ats.ui.intraday_strategy_dialog import (

        SBCClearNoticeDialog,

        SBCBatchClearCoordinator,

        show_sbc_single_clear_notice,

        show_sbc_batch_clear_notice,

    )



    # 1. 验证单独操作弹出单个通知窗口

    dlg_single = SBCIntradayChartDialog(code="600519")

    try:

        show_sbc_single_clear_notice(

            code="600519", name="贵州茅台", success=True,

            missing_today=False, frame_len=240,

            last_date="2026-11-05", last_time="10:45", last_close=1500.0,

            parent=dlg_single

        )

        cur_notice = sbc_mod._CURRENT_NOTICE_DIALOG

        assert cur_notice is not None

        assert cur_notice.isVisible()

        # 验证非模态、强力置顶

        assert cur_notice.isModal() is False

        assert bool(cur_notice.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) is True

        cur_notice.close()

    finally:

        dlg_single.close()



    # 2. 验证批量操作：多个窗口上报，仅弹出 1 个唯一的汇总窗口

    coord = SBCBatchClearCoordinator.get_instance()

    coord.start_batch(total_count=3)

    assert coord.is_batch_active is True



    # 模拟前两个窗口完成：此时尚未达到 total_count，不应弹出窗口

    sbc_mod._CURRENT_NOTICE_DIALOG = None

    coord.record_completed("600118", success=True, name="中国卫通")

    coord.record_completed("000568", success=True, name="泸州老窖")

    assert sbc_mod._CURRENT_NOTICE_DIALOG is None



    # 模拟第三个窗口完成：达到 total_count，触发唯一的批量提示窗口

    coord.record_completed("300139", success=True, name="晓程科技")

    assert coord.is_batch_active is False

    batch_notice = sbc_mod._CURRENT_NOTICE_DIALOG

    assert batch_notice is not None

    assert batch_notice.isVisible()

    all_label_text = "".join(l.text() for l in batch_notice.findChildren(QLabel))
    assert "批量缓存清理" in all_label_text or "3" in all_label_text

    batch_notice.close()





def test_sbc_clear_notice_dismiss_on_click_or_esc(qapp):
    from PyQt6.QtWidgets import QLabel, QWidget, QApplication
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer

    """验证提示窗口支持任意窗口点击或按 Esc 瞬间关闭，恢复正常操作"""

    import ats.ui.intraday_strategy_dialog as sbc_mod

    from ats.ui.intraday_strategy_dialog import SBCClearNoticeDialog



    dlg = SBCClearNoticeDialog(

        title="测试通知", icon_str="✅", content_html="<b>测试内容</b>", timeout_sec=10

    )

    sbc_mod._CURRENT_NOTICE_DIALOG = dlg

    dlg.show()

    assert dlg.isVisible()



    # 模拟外部窗口鼠标点击事件通过全局事件过滤器

    other_widget = QWidget()

    mouse_event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10.0, 10.0), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

    handled = dlg._filter.eventFilter(other_widget, mouse_event)

    # 事件过滤器应放行点击（返回 False），使得其他窗口操作生效

    assert handled is False



    # 处理事件队列使 QTimer.singleShot(0, dlg.close) 执行

    QApplication.processEvents()

    assert not dlg.isVisible()

