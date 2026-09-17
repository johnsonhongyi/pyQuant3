# -*- coding: utf-8 -*-
"""
测试：SBC 窗口重排不改变原有的显示位置顺序，恢复时原来在什么位置就在什么位置（除非换行）
------------------------------------------------------------------------------------
1. 验证 rearrange_all_sbc_windows 空间排序后进行平铺重排，原有视觉位置顺序不被 Z-order 打乱；
2. 验证 _calculate_safe_geometry_with_wrap 原位恢复与换行排布逻辑；
3. 验证 _sort_holding_items_by_spatial_order 保持物理空间行优先排序。
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

app = QApplication.instance() or QApplication(sys.argv)

import run_sbc
from ats.ui.intraday_strategy_dialog import (
    rearrange_all_sbc_windows,
    SBCIntradayChartDialog
)


def test_rearrange_does_not_change_original_spatial_display_order():
    """测试重排绝不改变原有的物理显示位置顺序 (即使点击激活使窗口 Z-Order 变成第 1 个)"""
    # 模拟 4 个窗口，原本排布为 2 行 2 列：
    # A(左上: x=10, y=10), B(右上: x=900, y=10), C(左下: x=10, y=500), D(右下: x=900, y=500)
    def make_mock_dialog(code, x, y, w=680, h=420):
        dlg = MagicMock(spec=SBCIntradayChartDialog)
        dlg.__class__ = SBCIntradayChartDialog
        dlg.geometry.return_value = QRect(x, y, w, h)
        dlg.isMaximized.return_value = False
        dlg.isMinimized.return_value = False
        dlg.isFullScreen.return_value = False
        dlg.isVisible.return_value = True
        dlg.windowTitle.return_value = f"SBC 实盘分时走势 - [{code}]"
        dlg.code = code
        dlg.normal_geometry = None
        dlg.anchor_edge = None
        dlg.is_hidden_state = False
        dlg.winId.return_value = 12345

        applied_coords = {}
        dlg.move.side_effect = lambda mx, my: applied_coords.update({"x": mx, "y": my})
        dlg.resize.side_effect = lambda mw, mh: applied_coords.update({"w": mw, "h": mh})
        dlg.applied_coords = applied_coords
        return dlg

    dlg_a = make_mock_dialog("600733", 10, 10)     # 原左上
    dlg_b = make_mock_dialog("603407", 900, 10)    # 原右上
    dlg_c = make_mock_dialog("688635", 10, 500)    # 原左下
    dlg_d = make_mock_dialog("000001", 900, 500)   # 原右下

    # 关键：模拟操盘手刚刚鼠标点击激活了窗口 D，导致 D 在 topLevelWidgets 里排在最前：[D, A, B, C]
    shuffled_active_dialogs = [dlg_d, dlg_a, dlg_b, dlg_c]

    with patch("PyQt6.QtWidgets.QApplication.topLevelWidgets", return_value=shuffled_active_dialogs):
        rearrange_all_sbc_windows()

    # 验证重排后各窗口的目标排布位置：
    # 窗口 A 必须仍然在左上 (X 较小, Y 较小)
    # 窗口 B 必须仍然在右上 (X 较大, Y 较小)
    # 窗口 C 必须仍然在左下 (X 较小, Y 较大)
    # 窗口 D 必须仍然在右下 (X 较大, Y 较大)
    assert dlg_a.applied_coords["x"] < dlg_b.applied_coords["x"], "A 必须在 B 的左侧"
    assert dlg_a.applied_coords["y"] == dlg_b.applied_coords["y"], "A 与 B 必须在同一行 (第一行)"
    assert dlg_c.applied_coords["x"] < dlg_d.applied_coords["x"], "C 必须在 D 的左侧"
    assert dlg_c.applied_coords["y"] == dlg_d.applied_coords["y"], "C 与 D 必须在同一行 (第二行)"
    assert dlg_c.applied_coords["y"] > dlg_a.applied_coords["y"], "第二行必须在第一行下方"


def test_calculate_safe_geometry_with_wrap_same_position_and_wrap():
    """测试恢复时原来在什么位置排布就在什么位置排布，除非右侧超出换行"""
    sg = QRect(0, 0, 1920, 1080)
    prev_bottom = 12

    # 1. 未超出右边缘：原位保持
    item1 = {"code": "600733", "x": 100, "y": 100, "width": 680, "height": 420}
    tx1, ty1, tw1, th1, new_bottom1 = run_sbc._calculate_safe_geometry_with_wrap(item1, sg, prev_bottom)
    assert tx1 == 100
    assert ty1 == 100
    assert tw1 == 680
    assert th1 == 420

    # 2. 超出右边缘 (例如原在双屏右侧 x=1600, w=680 -> 1600+680=2280 > 1920)：安全夹取至屏幕可用区域
    item2 = {"code": "603407", "x": 1600, "y": 100, "width": 680, "height": 420}
    tx2, ty2, tw2, th2, new_bottom2 = run_sbc._calculate_safe_geometry_with_wrap(item2, sg, new_bottom1)
    assert tx2 + tw2 <= sg.right() + 1, "超出右边缘必须安全 clamp 限制在屏幕右边界内"
    assert ty2 >= sg.top(), "Y 坐标在屏幕内"


def test_sort_holding_items_by_spatial_order():
    """测试 _sort_holding_items_by_spatial_order 保持物理空间行优先排序"""
    raw_items = [
        {"code": "000001", "x": 900, "y": 500, "height": 420},  # 右下
        {"code": "688635", "x": 20, "y": 510, "height": 420},   # 左下
        {"code": "603407", "x": 920, "y": 15, "height": 420},   # 右上
        {"code": "600733", "x": 10, "y": 10, "height": 420},    # 左上
    ]
    sorted_items = run_sbc._sort_holding_items_by_spatial_order(raw_items)
    codes = [it["code"] for it in sorted_items]
    # 必须是：第一行(左上 600733, 右上 603407)，第二行(左下 688635, 右下 000001)
    assert codes == ["600733", "603407", "688635", "000001"]
