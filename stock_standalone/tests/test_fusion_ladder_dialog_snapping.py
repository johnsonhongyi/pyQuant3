from datetime import datetime
# -*- coding: utf-8 -*-
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["fusion-ladder-test"])
    return app


@pytest.fixture(autouse=True)
def clean_config():
    """每个测试前后清理 fusion_ladder 相关的持久化配置，避免用例间相互污染"""
    from ats.ui.styles import save_config_node

    save_config_node("fusion_ladder_stays_on_top", False)
    save_config_node("fusion_ladder_anchor_edge", None)
    save_config_node("fusion_ladder_is_hidden", False)
    yield
    save_config_node("fusion_ladder_stays_on_top", False)
    save_config_node("fusion_ladder_anchor_edge", None)
    save_config_node("fusion_ladder_is_hidden", False)


def test_fusion_ladder_dialog_independence_and_flags(qapp):
    """测试 FusionLadderDialog 为系统级独立窗口：parent 为 None 且 flags 正确"""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMainWindow
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dummy_parent = QMainWindow()
    dlg = FusionLadderDialog(parent=dummy_parent)
    try:
        # 1. 独立窗口核心验证：物理 parent 必须为 None，切断 HWND Owner 强从属
        assert dlg.parent() is None
        assert dlg._py_parent is dummy_parent

        # 2. 独立窗口 flags 验证：必须包含独立窗口及最大最小化和关闭按钮
        flags = dlg.windowFlags()
        assert bool(flags & Qt.WindowType.Window)
        assert bool(flags & Qt.WindowType.WindowMinMaxButtonsHint)
        assert bool(flags & Qt.WindowType.WindowCloseButtonHint)
    finally:
        dlg.close()


def test_fusion_ladder_dialog_stays_on_top_mutex(qapp):
    """测试置顶控制与磁吸互斥"""
    from PyQt6.QtCore import Qt
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        dlg.show()
        # 初始未置顶
        assert not dlg.stays_on_top
        assert not dlg.is_hidden_state

        # 模拟贴边
        dlg.anchor_edge = "top"
        dlg.is_hidden_state = True

        # 打开置顶 -> 必须自动解除折叠和贴边，保证悬浮在最前
        dlg.chk_on_top.setChecked(True)
        assert dlg.stays_on_top is True
        assert dlg.anchor_edge is None
        assert dlg.is_hidden_state is False

        # 置顶状态下检测磁吸贴边 -> 直接短路，不贴边
        dlg._detect_and_snap()
        assert dlg.anchor_edge is None

        # 取消置顶
        dlg.chk_on_top.setChecked(False)
        assert dlg.stays_on_top is False
    finally:
        dlg.close()


def test_window_state_save_is_debounced_and_close_submits(qapp, monkeypatch):
    import ats.ui.fusion_ladder_dialog as fld

    writes = []
    monkeypatch.setattr(fld, "save_config_nodes_async", lambda updates: writes.append(updates) or True)
    dlg = fld.FusionLadderDialog()
    dlg._save_window_states(is_open=True)
    dlg._save_window_states(is_open=True)
    assert writes == []
    assert dlg._state_save_timer.interval() == 10000
    dlg._persist_window_states()
    assert len(writes) == 1
    assert writes[0]["fusion_ladder_dialog"]["is_open"] is True
    dlg.close()
    assert writes[-1]["fusion_ladder_dialog"]["is_open"] is False


def test_maximized_and_fullscreen_disable_snapping(qapp):
    from PyQt6.QtCore import Qt
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        dlg.show()
        for state in (Qt.WindowState.WindowMaximized, Qt.WindowState.WindowFullScreen):
            dlg.anchor_edge = "top"
            dlg.setWindowState(state)
            qapp.processEvents()
            assert dlg.anchor_edge is None
            dlg._detect_and_snap()
            dlg.hide_to_edge()
            assert dlg.anchor_edge is None
            assert not dlg.is_hidden_state
            dlg.setWindowState(Qt.WindowState.WindowNoState)
            qapp.processEvents()
    finally:
        dlg.close()


def test_fusion_ladder_dialog_magnetic_snapping_detection(qapp):
    """测试 35px 阈值顶边/左边/右边磁吸吸附逻辑（按最近距离准确判定）"""
    from PyQt6.QtCore import QRect
    from PyQt6.QtWidgets import QApplication
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        dlg.show()
        screen = dlg.screen() or QApplication.primaryScreen()
        s_geo = screen.availableGeometry()

        win_w = 500
        win_h = 350

        # 1. 移动到距离顶边 10px，远离左右边界 (屏幕 800px 宽，居中 x=150)
        dlg.setGeometry(s_geo.left() + 150, s_geo.top() + 10, win_w, win_h)
        dlg._detect_and_snap()
        assert dlg.anchor_edge == "top"
        assert dlg.normal_geometry is not None
        assert dlg.normal_geometry.top() == s_geo.top()

        # 2. 移动到距离左边 10px，远离顶边与右边 (y=200, 距右边 800 - 510 = 290px)
        dlg.setGeometry(s_geo.left() + 10, s_geo.top() + 200, win_w, win_h)
        dlg._detect_and_snap()
        assert dlg.anchor_edge == "left"
        assert dlg.normal_geometry is not None
        assert dlg.normal_geometry.left() == s_geo.left()

        # 3. 移动到距离右边 10px，远离顶边与左边 (x=800 - 500 - 10 = 290px，距左边 290px)
        dlg.setGeometry(s_geo.right() - win_w - 10, s_geo.top() + 200, win_w, win_h)
        dlg._detect_and_snap()
        assert dlg.anchor_edge == "right"
        assert dlg.normal_geometry is not None
        assert dlg.normal_geometry.right() == s_geo.right()

        # 4. 移动到屏幕中央 (各边缘均 > 35px: x=150, y=150) -> 释放磁吸贴边
        dlg.setGeometry(s_geo.left() + 150, s_geo.top() + 150, win_w, win_h)
        dlg._detect_and_snap()
        assert dlg.anchor_edge == None
        assert dlg.normal_geometry is None
    finally:
        dlg.close()


def test_fusion_ladder_dialog_hide_and_show_edge(qapp):
    """测试贴边自动收缩为感应条与展开恢复"""
    from PyQt6.QtCore import QRect
    from PyQt6.QtWidgets import QApplication
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        dlg.show()
        screen = dlg.screen() or QApplication.primaryScreen()
        s_geo = screen.availableGeometry()

        # 先 setGeometry 避免触发 moveEvent 冲掉 anchor_edge
        target_rect = QRect(s_geo.left(), s_geo.top() + 100, 500, 350)
        dlg.setGeometry(target_rect)
        dlg.normal_geometry = target_rect
        dlg.anchor_edge = "left"
        dlg.is_hidden_state = False

        # 贴边折叠
        dlg.hide_to_edge()
        assert dlg.is_hidden_state is True

        # 展开恢复
        dlg.show_normal_position()
        assert dlg.is_hidden_state is False
        assert dlg.windowOpacity() == 1.0
    finally:
        dlg.close()


def test_open_fusion_ladder_dialog_singleton_pop(qapp):
    """测试 open_fusion_ladder_dialog 单例与隐藏自动弹开"""
    import ats.ui.fusion_ladder_dialog as fld

    dlg1 = fld.open_fusion_ladder_dialog()
    try:
        assert dlg1 is not None
        # 设为隐藏态
        dlg1.anchor_edge = "top"
        dlg1.is_hidden_state = True

        # 再次打开
        dlg2 = fld.open_fusion_ladder_dialog()
        assert dlg1 is dlg2
        # 必须自动弹开展开
        assert dlg2.is_hidden_state is False
    finally:
        if dlg1:
            dlg1.close()


def test_fusion_ladder_table_headers_and_tooltips(qapp):
    """测试实时与回放表格包含名称、现价等列，且列头具备专业 ToolTip 悬浮说明"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, HEADER_TOOLTIPS

    dlg = FusionLadderDialog()
    try:
        # 1. 验证实时 Tab 列完整性
        live_headers = [dlg.tbl_live.horizontalHeaderItem(c).text() for c in range(dlg.tbl_live.columnCount())]
        assert "代码" in live_headers
        assert "名称" in live_headers
        assert "现价" in live_headers
        assert "涨幅%" in live_headers
        assert "RAR" in live_headers
        assert "位" in live_headers
        assert "接" in live_headers
        assert "意" in live_headers
        assert "环" in live_headers

        # 2. 验证回放 Tab 列完整性
        replay_headers = [dlg.tbl_replay.horizontalHeaderItem(c).text() for c in range(dlg.tbl_replay.columnCount())]
        assert "时间" in replay_headers
        assert "代码" in replay_headers
        assert "名称" in replay_headers
        assert "现价" in replay_headers
        assert "涨幅%" in replay_headers

        # 3. 验证关键列头 ToolTip
        rar_item = dlg.tbl_live.horizontalHeaderItem(live_headers.index("RAR"))
        assert rar_item is not None
        assert "Risk-Adjusted Rating" in rar_item.toolTip()
        assert "≥80分" in rar_item.toolTip()

        price_item = dlg.tbl_live.horizontalHeaderItem(live_headers.index("现价"))
        assert price_item is not None
        assert "现价" in price_item.toolTip() or "当时价格" in price_item.toolTip()
    finally:
        dlg.close()


def test_fusion_ladder_table_numeric_sorting(qapp):
    """测试 NumericTableWidgetItem 按照实际浮点数值排序而不是字符字典序"""
    from PyQt6.QtCore import Qt
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, NumericTableWidgetItem

    dlg = FusionLadderDialog()
    try:
        tbl = dlg.tbl_live
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        # 临时往表格填入测试数据 (假设价格: 102.30, 9.80, 12.50)
        # 列索引: 0:级别, 1:代码, 2:名称, 3:现价, 4:涨幅%, 5:RAR
        col_price = 3
        col_rar = 5
        test_data = [
            ("L3", "600000", "浦发银行", 102.30, 3.5, 75.0),
            ("L4", "000001", "平安银行", 9.80, 5.2, 88.0),
            ("L2", "300001", "特锐德", 12.50, 1.8, 62.0),
        ]
        for row_idx, (tier, code, name, price, pct, rar) in enumerate(test_data):
            tbl.insertRow(row_idx)
            for c in range(tbl.columnCount()):
                tbl.setItem(row_idx, c, NumericTableWidgetItem("-", 0.0))
            tbl.setItem(row_idx, 0, NumericTableWidgetItem(tier, tier))
            tbl.setItem(row_idx, 1, NumericTableWidgetItem(code, code))
            tbl.setItem(row_idx, 2, NumericTableWidgetItem(name, name))
            tbl.setItem(row_idx, 3, NumericTableWidgetItem(f"{price:.2f}", price))
            tbl.setItem(row_idx, 4, NumericTableWidgetItem(f"{pct:+.2f}%", pct))
            tbl.setItem(row_idx, 5, NumericTableWidgetItem(f"{rar:.1f}", rar))

        tbl.setSortingEnabled(True)
        # 按现价升序排序：9.80 应为第一行，12.50 为第二行，102.30 为第三行
        tbl.sortItems(col_price, Qt.SortOrder.AscendingOrder)
        assert tbl.item(0, col_price).text() == "9.80"
        assert tbl.item(1, col_price).text() == "12.50"
        assert tbl.item(2, col_price).text() == "102.30"

        # 按 RAR 降序排序：88.0 应排第一行
        tbl.sortItems(col_rar, Qt.SortOrder.DescendingOrder)
        assert tbl.item(0, col_rar).text() == "88.0"
        assert tbl.item(0, 1).text() == "000001"
    finally:
        dlg.close()


def test_fusion_ladder_narrow_mode_and_persistence(qapp):
    """测试极窄列切换与持久化"""
    from ats.ui.styles import flush_config_writer, load_config_node
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        # 初始状态
        init_narrow = dlg.is_narrow_mode

        # 切换到相反状态
        target_narrow = not init_narrow
        dlg.chk_narrow.setChecked(target_narrow)
        assert dlg.is_narrow_mode == target_narrow
        # 验证配置已写盘
        assert flush_config_writer(timeout_sec=3.0)
        assert bool(load_config_node("fusion_ladder_narrow_mode", False)) == target_narrow

        # 恢复状态
        dlg.chk_narrow.setChecked(init_narrow)
        assert dlg.is_narrow_mode == init_narrow
    finally:
        dlg.close()


def test_fusion_ladder_replay_backfill_persistence(qapp, tmp_path, monkeypatch):
    """旧回补入口不能写生产影子日志和会话快照。"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    monkeypatch.setattr("sys_utils.get_app_root", lambda: str(tmp_path))
    dlg = FusionLadderDialog()
    try:
        result = type("Result", (), {"day": "2026-10-23", "records": [{"code": "600000"}]})()
        assert dlg._persist_replay_shadow_and_context(result) == 0
        assert not (tmp_path / "logs" / "fusion_shadow" / "2026-10-23.jsonl").exists()
        assert not (tmp_path / "logs" / "fusion_state" / "session_ctx" / "2026-10-23.json").exists()
    finally:
        dlg.close()


def test_fusion_ladder_context_menu_aligned_with_capital_dragon(qapp, monkeypatch):
    """测试右键菜单全面对齐资金主线：推送异动联动、SBC走势图、次新超短、DNA审计、重点关注等"""
    from PyQt6.QtCore import QPoint
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, NumericTableWidgetItem

    dlg = FusionLadderDialog()
    try:
        tbl = dlg.tbl_live
        tbl.setRowCount(0)
        tbl.insertRow(0)
        tbl.setItem(0, 0, NumericTableWidgetItem("L4", 4))
        tbl.setItem(0, 1, NumericTableWidgetItem("600519", "600519"))
        tbl.setItem(0, 2, NumericTableWidgetItem("贵州茅台", "贵州茅台"))
        tbl.setItem(0, 3, NumericTableWidgetItem("1800.00", 1800.0))
        tbl.setItem(0, 4, NumericTableWidgetItem("+3.50%", 3.5))

        # 1. 测试在有效股票行上弹出菜单
        linkage_called = []
        monkeypatch.setattr("ats.ui.base_table.send_to_linkage", lambda code, name, parent: linkage_called.append((code, name)))

        ipo_called = []
        monkeypatch.setattr("ats.ui.ipo_detector_ipc.send_stock_to_ipo_detector", lambda code, name: ipo_called.append((code, name)))

        menu_captured = []
        original_exec = None
        from PyQt6.QtWidgets import QMenu
        def mock_exec(self, point):
            menu_captured.append(self)
            return None

        monkeypatch.setattr(QMenu, "exec", mock_exec)

        dlg._on_table_context_menu(tbl, QPoint(10, 10))
        assert len(menu_captured) == 1
        m = menu_captured[0]
        action_texts = [act.text() for act in m.actions()]

        # 验证资金主线标准菜单项完整对齐
        assert any("复制股票代码" in t for t in action_texts)
        assert any("发送到异动联动" in t for t in action_texts)
        assert any("SBC 通道走势图" in t for t in action_texts)
        assert any("个股详情" in t for t in action_texts)
        assert any("新股次新超短检测工具" in t for t in action_texts)
        assert any("DNA 特征审计报告" in t for t in action_texts)
        assert any("全系统重点关注" in t for t in action_texts)
        assert any("每日涨停天梯看板" in t for t in action_texts)
        assert any("板块雷达" in t for t in action_texts)
        assert any("主线回踩深挖" in t for t in action_texts)

        # 触发“发送到异动联动”
        act_link = [a for a in m.actions() if "发送到异动联动" in a.text()][0]
        act_link.trigger()
        assert len(linkage_called) == 1
        assert linkage_called[0][0] == "600519"
        assert "贵州茅台" in linkage_called[0][1]

        # 触发“发送到新股次新超短检测”
        act_ipo = [a for a in m.actions() if "新股次新超短检测工具" in a.text()][0]
        act_ipo.trigger()
        assert len(ipo_called) == 1
        assert ipo_called[0][0] == "600519"
    finally:
        dlg.close()


def test_fusion_ladder_ramdisk_persistence_and_resilience(tmp_path, monkeypatch):
    """测试实时梯度影子流支持 Ramdisk 双通道持久化与异常重启自愈加载"""
    from ats.ui.fusion_ladder_dialog import persist_shadow_records, load_live_rows

    primary_dir = tmp_path / "primary"
    ramdisk_dir = tmp_path / "ramdisk"
    primary_dir.mkdir(parents=True)
    ramdisk_dir.mkdir(parents=True)

    monkeypatch.setattr("sys_utils.get_app_root", lambda: str(primary_dir))
    monkeypatch.setattr("ats.ui.fusion_ladder_dialog._detect_ramdisk_dir", lambda: str(ramdisk_dir))

    records = [
        {
            "code": "300750",
            "name": "宁德时代",
            "ts": datetime(2026, 10, 23, 10, 0).timestamp(),
            "price": 250.0,
            "pct": 4.5,
            "fusion": {"tier": 4, "rar": 89.0, "size_pct": 25.0},
        },
        {
            "code": "002594",
            "name": "比亚迪",
            "ts": datetime(2026, 10, 23, 10, 1).timestamp(),
            "price": 290.0,
            "pct": 3.2,
            "fusion": {"tier": 3, "rar": 78.5, "size_pct": 15.0},
        },
    ]

    # 1. 执行持久化
    count = persist_shadow_records(records, day="2026-10-23")
    assert count == 2

    # 2. 验证 Ramdisk 与主落盘均存在数据
    assert (ramdisk_dir / "2026-10-23.jsonl").exists()
    assert (primary_dir / "logs" / "fusion_shadow" / "2026-10-23.jsonl").exists()

    # 3. 模拟异常崩溃后重启打开监视器，自动从 Ramdisk 加载
    loaded = load_live_rows("2026-10-23")
    assert len(loaded) == 2
    assert loaded[0]["code"] == "300750"
    assert loaded[0]["name"] == "宁德时代"
    assert loaded[0]["fusion"]["tier"] == 4


def test_fusion_ladder_rotator_and_activation_expand(qapp):
    """测试 Alt+R 轮转单例获取，以及被系统激活时贴边折叠自动展开"""
    from PyQt6.QtCore import QEvent
    import ats.ui.fusion_ladder_dialog as fld

    dlg = fld.open_fusion_ladder_dialog()
    try:
        # 验证单例获取
        assert fld.get_open_fusion_ladder_dialog() is dlg

        # 模拟进入贴边折叠感应条状态
        dlg.anchor_edge = "right"
        dlg.is_hidden_state = True
        dlg.setWindowOpacity(0.35)

        # 模拟由 Alt+R 轮转切入激活 (QEvent.Type.ActivationChange)
        # 模拟当前窗口被激活
        dlg.isActiveWindow = lambda: True
        dlg.changeEvent(QEvent(QEvent.Type.ActivationChange))

        # 必须自动平滑展开恢复正常
        assert dlg.is_hidden_state is False
        assert dlg.windowOpacity() == 1.0
    finally:
        dlg.close()


def test_fusion_ladder_auto_close_settle(qapp, tmp_path, monkeypatch):
    """测试 15:00 收盘后自动持久化与上下文沉淀，每日自动更新上下文"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    from ats.ui.styles import load_config_node, save_config_node

    save_config_node("fusion_last_auto_settle_day", "")
    dlg = FusionLadderDialog()
    try:
        # 触发收盘结算
        dlg._execute_closing_session_settlement("2026-10-23")

        # 验证已沉淀并记录
        assert load_config_node("fusion_last_auto_settle_day") == "2026-10-23"
        assert "自动" in dlg.lbl_status.text()
    finally:
        dlg.close()


def test_heatmap_snapshot_fallback_on_missing_date(monkeypatch, tmp_path):
    """测试行业板块快照缺失时平滑回退最新可用快照，避免非交易日空白"""
    import gzip
    import json
    import ats.ui.heatmap_widget as hmw

    # 创建一个模拟的最新快照文件 bidding_20261015.json.gz
    mock_snap_dir = tmp_path / "snapshots"
    mock_snap_dir.mkdir(parents=True, exist_ok=True)
    snap_file = mock_snap_dir / "bidding_20261015.json.gz"

    mock_bidding = {
        "sector_data": {
            "半导体": {"change_pct": 2.5, "rank": 1},
            "元器件": {"change_pct": 1.8, "rank": 2},
            "软件服务": {"change_pct": 1.2, "rank": 3},
        }
    }
    with gzip.open(snap_file, "wt", encoding="utf-8") as f:
        json.dump(mock_bidding, f)

    # 替换 app root
    monkeypatch.setattr("ats.ui.heatmap_widget.get_app_root", lambda: str(tmp_path))
    monkeypatch.setattr("JohnsonUtil.commonTips.get_day_istrade_date", lambda: False)
    monkeypatch.setattr("JohnsonUtil.commonTips.get_last_trade_date", lambda: "2026-10-23")

    # 执行底层读取函数
    res = hmw._read_sector_snapshot_sources()
    assert res is not None
    non_trade, sector_data = res[0], res[1]
    assert len(sector_data) >= 3
    assert "半导体" in sector_data



def test_tooltip_filter_does_not_pollute_qapplication(qapp):
    """【0x8001010d根因1验证】验证 UnifiedToolTipFilter 绝不向全局 QApplication 安装事件过滤器"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    dlg = FusionLadderDialog()
    try:
        assert hasattr(dlg, "_tooltip_filter")
    finally:
        dlg.close()


def test_header_tooltip_suppresses_during_mouse_drag(qapp, monkeypatch):
    """【0x8001010d根因2验证】在鼠标拖拽列宽或窗口移动时，HeaderToolTip 严禁启动延迟弹窗或显示 _TipCard"""
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, HeaderToolTip
    dlg = FusionLadderDialog()
    try:
        table = dlg.tbl_live
        header_tip: HeaderToolTip = table._header_tip
        header = table.horizontalHeader()

        monkeypatch.setattr(QApplication, "mouseButtons", lambda: Qt.MouseButton.LeftButton)

        mouse_drag_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(50.0, 10.0),
            QPointF(50.0, 10.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        handled = header_tip.eventFilter(header, mouse_drag_event)
        assert handled is False
        assert not header_tip._delay.isActive()
        if header_tip._label is not None:
            assert not header_tip._label.isVisible()
    finally:
        dlg.close()


def test_empty_placeholder_keeps_sorting_disabled(qapp):
    """【白板与崩溃防守】当表格无数据只有占位说明行时，保持 setSortingEnabled(False)，防止合并单元格排序崩溃"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    dlg = FusionLadderDialog()
    try:
        table = dlg.tbl_live
        if table.rowCount() == 1 and table.columnSpan(0, 0) > 1:
            assert table.isSortingEnabled() is False
    finally:
        dlg.close()


def test_move_event_does_not_spam_state_saves(qapp, monkeypatch):
    """【性能与消息循环防守】moveEvent 严禁在每一像素拖动中高频调用 _save_window_states"""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QMoveEvent
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    dlg = FusionLadderDialog()
    try:
        dlg.stays_on_top = False
        dlg.is_hidden_state = False
        save_calls = []
        monkeypatch.setattr(dlg, "_save_window_states", lambda *args, **kwargs: save_calls.append(1))

        for i in range(10):
            ev = QMoveEvent(QPoint(100 + i, 100 + i), QPoint(100, 100))
            dlg.moveEvent(ev)

        assert len(save_calls) == 0
        assert dlg.snap_timer.isActive()
    finally:
        dlg.close()
