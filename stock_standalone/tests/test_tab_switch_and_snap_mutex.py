# -*- coding: utf-8 -*-
"""
测试 Tab 栏左右箭头点击直接切换 Tab 栏以及 ATS 各窗口置顶停用磁吸互斥逻辑
"""
import pytest
import os
import sys

from PyQt6.QtWidgets import QApplication, QTabWidget, QLabel, QToolButton
from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QMouseEvent

from ats.ui.styles import enable_tab_direct_switch
from ats.ui.chart_widgets import DistributionDetailsDialog
from ats.ui.dragon_monitor import DragonLeaderMonitorDialog
from ats.ui.main_window import StockDetailDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_tab_direct_switch_by_arrow_buttons(qapp):
    """测试 Tab 栏空间狭小时，左右滚动箭头点击直接切换选项卡"""
    tw = QTabWidget()
    tw.setUsesScrollButtons(True)
    tw.addTab(QLabel("Tab 0"), "📊 市场分布")
    tw.addTab(QLabel("Tab 1"), "📈 资金明细")
    tw.resize(60, 40)
    tw.show()
    qapp.processEvents()

    # 启用直接切换过滤器
    enable_tab_direct_switch(tw)
    qapp.processEvents()

    btns = tw.tabBar().findChildren(QToolButton)
    assert len(btns) >= 2, "TabBar 应生成左右滚动 QToolButton"

    assert tw.currentIndex() == 0

    # 模拟点击右箭头
    right_btns = [b for b in btns if b.arrowType() == Qt.ArrowType.RightArrow]
    btn_r = right_btns[0] if right_btns else btns[-1]

    press_ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    rel_ev = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(btn_r, press_ev)
    qapp.sendEvent(btn_r, rel_ev)
    qapp.processEvents()

    assert tw.currentIndex() == 1, "点击右箭头后应直接切换到 Tab 1 (资金明细)"

    # 再次模拟点击左箭头
    left_btns = [b for b in btns if b.arrowType() == Qt.ArrowType.LeftArrow]
    btn_l = left_btns[0] if left_btns else btns[0]
    qapp.sendEvent(btn_l, press_ev)
    qapp.sendEvent(btn_l, rel_ev)
    qapp.processEvents()

    assert tw.currentIndex() == 0, "点击左箭头后应直接切换回 Tab 0 (市场分布)"
    tw.close()


def test_distribution_details_dialog_snap_mutex(qapp):
    """测试涨跌分布个股明细窗口置顶与磁吸互斥"""
    dlg = DistributionDetailsDialog(bucket_idx=0)
    dlg.show()
    dlg.chk_on_top.setChecked(False)
    qapp.processEvents()

    # 模拟处于折叠隐藏状态
    dlg.is_hidden_state = True
    dlg.anchor_edge = "right"

    # 勾选置顶
    dlg.chk_on_top.setChecked(True)
    qapp.processEvents()

    assert dlg.stays_on_top is True
    assert dlg.anchor_edge is None, "置顶后应重置 anchor_edge"
    assert dlg.is_hidden_state is False, "置顶后应退出折叠展开还原"
    assert dlg.windowOpacity() == 1.0, "置顶后不透明度应恢复为 1.0"

    # 验证置顶时 _detect_and_snap 直接失效
    dlg._detect_and_snap()
    assert dlg.anchor_edge is None, "置顶状态下 _detect_and_snap 不应触发磁吸"

    # 验证置顶时 hide_to_edge 直接失效
    dlg.anchor_edge = "top" # 哪怕意外存在
    dlg.hide_to_edge()
    assert dlg.is_hidden_state is False, "置顶状态下 hide_to_edge 不应折叠隐藏"

    # 验证置顶时 _check_hover 直接失效
    dlg._check_hover()
    assert dlg.is_hidden_state is False

    dlg.close()


def test_dragon_monitor_panel_snap_mutex(qapp):
    """测试加速龙头追踪器置顶与磁吸互斥"""
    panel = DragonLeaderMonitorDialog()
    panel.show()
    panel.chk_on_top.setChecked(False)
    qapp.processEvents()

    panel.is_hidden_state = True
    panel.anchor_edge = "left"

    panel.chk_on_top.setChecked(True)
    qapp.processEvents()

    assert panel.stays_on_top is True
    assert panel.anchor_edge is None
    assert panel.is_hidden_state is False
    assert panel.windowOpacity() == 1.0

    panel._detect_and_snap()
    assert panel.anchor_edge is None

    panel.anchor_edge = "left"
    panel.hide_to_edge()
    assert panel.is_hidden_state is False

    panel._check_hover()
    assert panel.is_hidden_state is False

    panel.close()


def test_stock_detail_dialog_snap_mutex(qapp):
    """测试实时实盘个股详情置顶复选框与磁吸互斥"""
    dlg = StockDetailDialog(code="600000", name="浦发银行")
    dlg.show()
    dlg.chk_on_top.setChecked(False)
    qapp.processEvents()

    assert hasattr(dlg, "chk_on_top"), "StockDetailDialog 必须具备置顶复选框"
    dlg.is_hidden_state = True
    dlg.anchor_edge = "top"

    dlg.chk_on_top.setChecked(True)
    qapp.processEvents()

    assert dlg.stays_on_top is True
    assert dlg.anchor_edge is None
    assert dlg.is_hidden_state is False
    assert dlg.windowOpacity() == 1.0

    dlg._detect_and_snap()
    assert dlg.anchor_edge is None

    dlg.anchor_edge = "top"
    dlg.hide_to_edge()
    assert dlg.is_hidden_state is False

    dlg._check_hover()
    assert dlg.is_hidden_state is False

    dlg.close()
