# -*- coding: utf-8 -*-
"""
tests/test_flicker_free_realtime_updates.py
=============================================================================
验证 ATS 高频实时数据更新时各管理窗口与核心看板的【零闪烁】特性：
1. UniverseTreeWidget: update_pools 原地节点复用 (In-Place Reuse)，杜绝 clear() 重建；
2. PositionPanel: update_positions 原地单元格复用与无缝行数增删，杜绝 setRowCount(0)；
3. TradeFlowTable: _render_current_page 原地单元格复用与 setUpdatesEnabled 保护；
4. DragonLeaderMonitorDialog: update_data 原地单元格复用与滚动条锁定。
"""

import sys
import pytest
import pandas as pd
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


def test_universe_tree_inplace_item_reuse():
    """验证 UniverseTreeWidget 在连续调用 update_pools 时节点原地复用，绝不销毁已有 QTreeWidgetItem"""
    from ats.ui.universe_widget import UniverseTreeWidget

    widget = UniverseTreeWidget()

    radar_init = [
        ("600001", "标的A", "10.00", "+1.50%", "竞价", "描述1"),
        ("600002", "标的B", "20.00", "+3.20%", "竞价", "描述2"),
    ]
    watch_init = [
        ("300001", "标的C", "15.00", "+2.00%", "观察", "描述3"),
    ]
    trade_init = []

    # 1. 首次填充数据
    widget.update_pools(radar_init, watch_init, trade_init)

    assert widget.radar_root is not None
    assert widget.radar_root.childCount() == 2
    assert widget.watch_root.childCount() == 1

    item_a_first = None
    item_b_first = None
    for i in range(widget.radar_root.childCount()):
        c = widget.radar_root.child(i)
        if c.data(0, Qt.ItemDataRole.UserRole) == "600001":
            item_a_first = c
        elif c.data(0, Qt.ItemDataRole.UserRole) == "600002":
            item_b_first = c

    assert item_a_first is not None
    assert item_b_first is not None
    radar_root_first = widget.radar_root

    # 2. 第二次行情更新（标的A价格变化，新增标的D，标的B依然存在）
    radar_updated = [
        ("600001", "标的A", "10.50", "+6.50%", "竞价", "描述1-更新"),
        ("600002", "标的B", "20.00", "+3.20%", "竞价", "描述2"),
        ("600004", "标的D", "8.80", "+9.90%", "突破", "新增标的"),
    ]
    widget.update_pools(radar_updated, watch_init, trade_init)

    # 核心验证 1: 根节点对象必须完全保持原实例 (未被 clear() 重建)
    assert widget.radar_root is radar_root_first
    assert widget.radar_root.childCount() == 3

    # 核心验证 2: 标的A和标的B的子节点对象必须是同一个实例 (In-Place Reuse)
    found_a = None
    found_b = None
    found_d = None
    for i in range(widget.radar_root.childCount()):
        child = widget.radar_root.child(i)
        code = child.data(0, Qt.ItemDataRole.UserRole)
        if code == "600001":
            found_a = child
        elif code == "600002":
            found_b = child
        elif code == "600004":
            found_d = child

    assert found_a is not None
    assert found_b is not None
    assert found_d is not None

    # 原地复用断言：对象身份一致
    assert found_a is item_a_first
    assert found_b is item_b_first

    # 数据变动原地应用
    assert found_a.text(2) == "10.50"
    assert found_a.text(3) == "+6.50%"
    assert found_a.text(4) == "描述1-更新"

    # 3. 第三次更新（标的B从池中移出）
    radar_removed = [
        ("600001", "标的A", "10.60", "+7.50%", "竞价", "描述1-更新2"),
    ]
    widget.update_pools(radar_removed, watch_init, trade_init)
    assert widget.radar_root.childCount() == 1
    assert widget.radar_root.child(0).data(0, Qt.ItemDataRole.UserRole) == "600001"
    assert widget.radar_root.child(0) is item_a_first

    widget.close()


def test_position_panel_flicker_free_update():
    """验证 PositionPanel 在连续调用 update_positions 时单元格复用，杜绝清空闪烁"""
    from ats.ui.trade_flow import PositionPanel

    panel = PositionPanel()

    data_1 = [
        ("600030", "中信证券", "5,000", "20.15", "20.25", "101,250", "+0.50%", "10.0%"),
        ("300750", "宁德时代", "800", "185.50", "189.20", "151,360", "+2.00%", "15.0%"),
    ]
    panel.update_positions(data_1, cash=500000.0, total_assets=1000000.0)

    assert panel.table.rowCount() == 2
    item_0_0 = panel.table.item(0, 0)
    assert item_0_0 is not None
    assert item_0_0.text() == "600030"

    # 第二次更新（价格变动）
    data_2 = [
        ("600030", "中信证券", "5,000", "20.15", "21.00", "105,000", "+4.22%", "10.5%"),
        ("300750", "宁德时代", "800", "185.50", "189.20", "151,360", "+2.00%", "15.0%"),
    ]
    panel.update_positions(data_2, cash=500000.0, total_assets=1003750.0)

    # 核心验证：行数保持 2，单元格对象原地复用，内容变更为新价格
    assert panel.table.rowCount() == 2
    assert panel.table.item(0, 0) is item_0_0  # 内存对象复用
    assert panel.table.item(0, 4).text() == "21.00"

    panel.close()


def test_trade_flow_flicker_free_render():
    """验证 TradeFlowTable 在渲染流水时单元格就地复用"""
    from ats.ui.trade_flow import TradeFlowTable

    table = TradeFlowTable()

    flow_data = [
        ["2026-09-11 09:35:00", "600030", "中信证券", "买入", "20.15", "5,000", "100,750", "+0.00%", "突破买入"],
        ["2026-09-11 09:40:00", "300750", "宁德时代", "买入", "185.50", "800", "148,400", "+0.00%", "支撑吸筹"],
    ]
    table.update_flow_list(flow_data)

    assert table.table.rowCount() == 2
    # 流水表默认最新时间在前，09:40:00 宁德时代在第 0 行
    item_0_1 = table.table.item(0, 1)
    assert item_0_1 is not None
    assert item_0_1.text() == "300750"

    # 重新渲染当前页
    table._render_current_page()
    assert table.table.rowCount() == 2
    assert table.table.item(0, 1) is item_0_1  # 单元格复用

    table.close()


def test_dragon_monitor_flicker_free_update():
    """验证 DragonLeaderMonitorDialog 在 update_data 时单元格就地复用"""
    from ats.ui.dragon_monitor import DragonLeaderMonitorDialog

    dialog = DragonLeaderMonitorDialog()
    dialog.manual_codes = ["600030", "300750"]

    df1 = pd.DataFrame([
        {"code": "600030", "name": "中信证券", "close": 20.0, "percent": 1.5, "state": "持股中"},
        {"code": "300750", "name": "宁德时代", "close": 180.0, "percent": 3.0, "state": "持股中"},
    ]).set_index("code")

    dialog.update_data(df1, 0.5)
    assert dialog.table.rowCount() == 2
    first_item = dialog.table.item(0, 0)
    assert first_item is not None

    df2 = pd.DataFrame([
        {"code": "600030", "name": "中信证券", "close": 21.0, "percent": 6.5, "state": "持股中"},
        {"code": "300750", "name": "宁德时代", "close": 182.0, "percent": 4.1, "state": "持股中"},
    ]).set_index("code")

    dialog.update_data(df2, 0.8)
    assert dialog.table.rowCount() == 2
    # 核心验证：单元格对象原地复用，绝不 setRowCount(0) 重建
    assert dialog.table.item(0, 0) is first_item

    dialog.close()
