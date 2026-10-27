# -*- coding: utf-8 -*-
"""tests/test_fusion_tab_names_and_header_tips.py — 验证融合梯度监视器各Tab名称完整性、表头悬浮提示与Tab自动刷新机制。"""

import os
import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QHelpEvent, QMouseEvent

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["fusion-ladder-test"])
    return app


def test_names_resolution_all_candidates():
    """验证 ats/fusion/names.py 的全渠道名称解析引擎"""
    from ats.fusion.names import code_of, load_names, name_of

    names_map = load_names()
    assert len(names_map) > 1000

    # 验证典型白马、中小板与科创板股票名称解析
    test_cases = {
        "600519": "贵州茅台",
        "002865": "钧达股份",
        "002222": "福晶科技",
        "002129": "TCL中环",
        "603138": "海量数据",
        "600089": "特变电工",
        "300750": "宁德时代",
    }
    for code, expected in test_cases.items():
        resolved = name_of(code)
        assert resolved == expected, f"Code {code} expected {expected}, got {resolved}"
        # 兼容带后缀或非纯6位的输入
        assert name_of(f"{code}.SH") == expected or name_of(f"{code}.SZ") == expected

    # 验证反向通过名称查找代码
    assert code_of("贵州茅台") == "600519"
    assert code_of("宁德时代") == "300750"


def test_dialog_resolve_name_fallbacks(qapp):
    """验证 FusionLadderDialog._resolve_name 的多层兜底保障机制"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    class MockParent:
        def __init__(self):
            self.name_cache = {"999991": "测试股A"}

        def get_stock_name(self, code):
            if code == "999992":
                return "测试股B"
            return ""

    mock_parent = MockParent()
    dlg = FusionLadderDialog(parent=mock_parent)
    try:
        # 1. 优先从现有 fallback_dict 取
        assert dlg._resolve_name("000001", {"name": "平安银行"}) == "平安银行"
        # 2. 从本地强化 names_map 取
        assert dlg._resolve_name("600519") == "贵州茅台"
        # 3. 从父窗口 name_cache 取
        assert dlg._resolve_name("999991") == "测试股A"
        # 4. 从父窗口 get_stock_name 取
        assert dlg._resolve_name("999992") == "测试股B"
        # 5. 空代码安全防守
        assert dlg._resolve_name("") == ""
    finally:
        dlg.close()


def test_header_tooltip_event_filter(qapp):
    """验证 HeaderToolTip 事件过滤器在 viewport 上正常工作，杜绝 AttributeError 异常与悬停失效"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, HeaderToolTip

    dlg = FusionLadderDialog()
    try:
        table = dlg.tbl_live
        assert hasattr(table, "_header_tip")
        tip_filter: HeaderToolTip = table._header_tip

        header = table.horizontalHeader()
        viewport = header.viewport()

        # 检查逻辑列索引提取
        pos = QPoint(10, 10)
        idx = tip_filter._get_logical_index(viewport, pos)
        assert idx >= 0

        # 检查词条获取
        html = tip_filter._html_at_index(idx)
        assert "判断依据" in html or "该列的数值含义" in html

        # 模拟 MouseMove 事件发送到 viewport
        move_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(pos),
            QPointF(pos),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        res = tip_filter.eventFilter(viewport, move_event)
        # MouseMove 不应被拦截吞掉
        assert res is False
        assert tip_filter._pending_html != ""
        assert tip_filter._delay.isActive()

        # 模拟 ToolTip (QHelpEvent) 事件发送到 viewport
        help_event = QHelpEvent(QEvent.Type.ToolTip, pos, pos)
        res_help = tip_filter.eventFilter(viewport, help_event)
        # 匹配到深色卡片时，系统原生提示被拦截转为自绘深色卡片
        assert res_help is True
        assert tip_filter._label is not None
        assert tip_filter._label.isVisible()
    finally:
        dlg.close()


def test_tab_change_and_independent_signatures(qapp):
    """验证 Tab 切换与自动刷新机制，确保每个 Tab 拥有独立的更新签名"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        assert hasattr(dlg, "_tab_signatures")

        # 切换到赛马跟踪 Tab (index 3)
        dlg.tabs.setCurrentIndex(3)
        dlg._on_tab_changed(3)
        assert dlg.tbl_track.columnCount() >= 14

        # 切换回实时梯度 Tab (index 0)
        dlg.tabs.setCurrentIndex(0)
        dlg._on_tab_changed(0)
        assert dlg.tbl_live.columnCount() >= 18

        # 模拟定时刷新：Tab 0 与 Tab 3 签名独立记录，互不干扰跳过
        day = dlg.cmb_day.currentText().strip()
        sig = dlg._live_source_signature(day)
        dlg._tab_signatures[0] = sig
        assert dlg._tab_signatures.get(3) is None  # Tab 3 独立未被污染
    finally:
        dlg.close()


def test_track_entries_from_shadow_dynamic_snapshot(qapp):
    """验证赛马跟踪中利用权威行情对齐 MFE/MAE/收盘涨幅及集合竞价过滤"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        # Mock _get_batch_quotes_snapshot 提供通达信权威对齐快照 (现价 25.0, 昨收 24.0, 最高 28.0, 最低 19.0)
        dlg._get_batch_quotes_snapshot = lambda codes: {
            "688000": {
                "price": 25.0,
                "last_close": 24.0,
                "high": 28.0,
                "low": 19.0,
                "day_pct": 4.17,
            }
        }

        # 构造一组记录：09:25:00 集合竞价假价格 18.0，09:32:00 真实开盘价 20.0
        recs = [
            {
                "ts": 1793064300.0,  # 09:25:00 集合竞价
                "price": 18.0,
                "fusion": {"tier": 2, "evidence": ["集合竞价试盘"]},
            },
            {
                "ts": 1793064720.0,  # 09:32:00 连续竞价真实开盘
                "price": 20.0,
                "fusion": {"tier": 2, "evidence": ["突破"]},
            },
        ]
        import ats.ui.fusion_ladder_dialog as fld
        orig_load = fld.load_live_series
        fld.load_live_series = lambda day: {"688000": recs}

        try:
            entries = dlg._track_entries_from_shadow("2026-10-27")
            assert len(entries) == 1
            e = entries[0]
            assert e["code"] == "688000"
            # 1. 验证集合竞价被过滤，入局价严格为连续竞价的 20.0 (绝非 18.0)
            assert e["enter_price"] == 20.0
            # 2. 验证 MFE% = (28 - 20)/20 = 40.0%
            assert e["mfe"] == 40.0
            # 3. 验证 MAE% = (19 - 20)/20 = -5.0%
            assert e["mae"] == -5.0
            # 4. 验证 当日收盘涨幅% = (25 - 24)/24 = +4.17% (对齐通达信盘口)
            assert e["day_close_pct"] == 4.17
            # 5. 验证 入局收益率 = (25 - 20)/20 = +25.0%
            assert e["holding_ret"] == 25.0
        finally:
            fld.load_live_series = orig_load
    finally:
        dlg.close()
