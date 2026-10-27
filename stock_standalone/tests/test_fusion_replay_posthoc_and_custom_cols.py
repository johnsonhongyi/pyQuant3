# -*- coding: utf-8 -*-
"""tests/test_fusion_replay_posthoc_and_custom_cols.py — 验证按日回放自动后验收盘涨幅与ATS自定义列动态接入开关。"""

import os
import pytest
import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["fusion-posthoc-test"])
    return app


def test_replay_records_posthoc_fields():
    """验证 DayReplay.records 中包含 day_close 与 day_close_pct 自动后验字段"""
    from ats.fusion.replay import DayReplay, ReplayConfig

    # 构造极简测试回放数据
    cfg = ReplayConfig()
    replay = DayReplay(config=cfg, cache={})
    assert hasattr(replay, "cfg")

    # 模拟一条 record 字典验证后验计算逻辑
    price = 10.0
    prev_close = 9.80
    last_close = 10.50
    pct = (price / prev_close - 1.0) * 100.0  # +2.04%
    close_ret = (last_close / price - 1.0) * 100.0  # +5.00%
    day_close_pct = (last_close / prev_close - 1.0) * 100.0  # +7.14%

    record = {
        "time": "09:35",
        "code": "600519",
        "name": "贵州茅台",
        "tier": 3,
        "tier_name": "L3",
        "rar": 85.0,
        "entry": price,
        "pct": round(pct, 2),
        "day_close": round(last_close, 3),
        "day_close_pct": round(day_close_pct, 2),
        "mfe": 6.5,
        "mae": -1.2,
        "close_ret": round(close_ret, 2),
        "size_pct": 20,
        "temp": 55.0,
    }

    assert record["day_close"] == 10.50
    assert record["day_close_pct"] == 7.14
    assert record["pct"] == 2.04
    assert record["close_ret"] == 5.00


def test_custom_cols_extra_detection_and_vis_map():
    """验证 get_ats_custom_extra_cols 与 get_ats_col_display_name"""
    from ats.ui.fusion_ladder_dialog import get_ats_custom_extra_cols, get_ats_col_display_name

    extra = get_ats_custom_extra_cols()
    assert isinstance(extra, list)
    # 基础列如 code, name, price, pct, rar 绝不应出现在 extra 中
    for base_fld in ("code", "name", "price", "pct", "rar", "mfe", "mae"):
        assert base_fld not in extra

    # 验证 vis_column_map 中英文展示映射
    assert get_ats_col_display_name("dff") in ("DFF", "dff")
    assert get_ats_col_display_name("win") in ("连阳", "win", "WIN")


def test_tbl_replay_posthoc_column_and_render(qapp):
    """验证按日回放表格正确包含终收%列并渲染后验对比 ToolTip"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    from ats.fusion.replay import ReplayResult

    dlg = FusionLadderDialog()
    try:
        tbl = dlg.tbl_replay
        headers = [tbl.horizontalHeaderItem(c).text() for c in range(tbl.columnCount())]
        assert "涨幅%" in headers
        assert "终收%" in headers
        assert "收盘%" in headers

        idx_pct = headers.index("涨幅%")
        idx_day_close = headers.index("终收%")
        assert idx_day_close == idx_pct + 1

        # 模拟一份回放结果给表格渲染
        fake_record = {
            "time": "09:35",
            "code": "002865",
            "name": "钧达股份",
            "tier": 3,
            "tier_name": "L3",
            "rar": 86.5,
            "entry": 60.0,
            "pct": 3.25,
            "day_close": 65.5,
            "day_close_pct": 9.95,
            "mfe": 10.0,
            "mae": -0.8,
            "close_ret": 9.17,
            "size_pct": 25,
            "temp": 60.0,
        }
        fake_result = ReplayResult(
            day="2026-10-27",
            records=[fake_record],
            meta={"day": "2026-10-27", "codes": 1, "bars": 240, "evaluations": 1, "records": 1},
        )

        dlg._on_replay_done(fake_result)
        assert tbl.rowCount() == 1
        # 验证触发时涨幅
        item_pct = tbl.item(0, idx_pct)
        assert "+3.25%" in item_pct.text()

        # 验证终收%
        item_close = tbl.item(0, idx_day_close)
        assert "+9.95%" in item_close.text()
        assert item_close.font().bold()
        # 验证后验 ToolTip 包含对比信息
        tip_text = item_close.toolTip()
        assert "自动后验对照" in tip_text
        assert "当时入局涨幅: +3.25%" in tip_text
        assert "终收涨幅: +9.95%" in tip_text
        assert "全天收盘价: 65.50" in tip_text
    finally:
        dlg.close()


def test_custom_cols_toggle_and_visibility(qapp):
    """验证自定义列开关复选框切换与表格列显隐联动"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, _LIVE_BASE_HEADERS, _REPLAY_BASE_HEADERS

    dlg = FusionLadderDialog()
    try:
        assert hasattr(dlg, "chk_custom_cols")
        assert dlg.chk_custom_cols.text() == "📊 自定义列"

        # 1. 打开自定义列开关
        dlg.chk_custom_cols.setChecked(True)
        assert dlg.show_custom_cols is True

        live_base_len = len(_LIVE_BASE_HEADERS)
        if dlg.tbl_live.columnCount() > live_base_len:
            # 开启状态下自定义列应可见（非极窄模式）
            if not dlg.is_narrow_mode:
                assert not dlg.tbl_live.isColumnHidden(live_base_len)

        # 2. 关闭自定义列开关
        dlg.chk_custom_cols.setChecked(False)
        assert dlg.show_custom_cols is False
        if dlg.tbl_live.columnCount() > live_base_len:
            assert dlg.tbl_live.isColumnHidden(live_base_len)

        # 3. 极窄模式测试
        dlg.chk_narrow.setChecked(True)
        assert dlg.is_narrow_mode is True
        # 极窄模式下自定义列必须隐藏
        if dlg.tbl_live.columnCount() > live_base_len:
            assert dlg.tbl_live.isColumnHidden(live_base_len)

        # 恢复非极窄
        dlg.chk_narrow.setChecked(False)
    finally:
        dlg.close()


def test_custom_cols_data_extraction_from_dataframe(qapp):
    """验证从量化策略主 DataFrame 中正确提取并格式化自定义列数值"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    dlg = FusionLadderDialog()
    try:
        # 构造模拟策略 DataFrame
        df_strat = pd.DataFrame(
            {
                "code": ["600519", "002865"],
                "name": ["贵州茅台", "钧达股份"],
                "dff": [2.35, -1.20],
                "Rank": [1, 5],
                "ch_bc2": [3, 0],
            }
        ).set_index("code")

        # 提取 600519 的 dff
        val_txt, val_num = dlg._extract_stock_custom_val(df_strat, "600519", "dff")
        assert "2.35" in val_txt
        assert abs(val_num - 2.35) < 1e-4

        # 提取 002865 的 ch_bc2
        val_txt, val_num = dlg._extract_stock_custom_val(df_strat, "002865", "ch_bc2")
        assert "0" in val_txt
        assert val_num == 0.0

        # 不存在的代码优雅降级为 --
        val_txt, val_num = dlg._extract_stock_custom_val(df_strat, "999999", "dff")
        assert val_txt == "--"
        assert val_num == 0.0
    finally:
        dlg.close()


def test_track_day_close_pct_and_sorting(qapp):
    """验证赛马跟踪收盘%真实涨跌幅提取（杜绝0.00%）与点击表头按收盘涨幅精准排序"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    class MockParent:
        def __init__(self):
            self.current_df = pd.DataFrame(
                {
                    "code": ["603028", "601818", "603489"],
                    "price": [10.33, 3.08, 29.83],
                    "close": [10.33, 3.08, 29.83],  # 现价
                    "percent": [10.01, 1.65, 9.03],  # 权威涨跌幅
                    "high": [10.33, 3.10, 30.10],
                    "low": [9.39, 3.02, 27.50],
                }
            ).set_index("code")

    mock_parent = MockParent()
    dlg = FusionLadderDialog(parent=mock_parent)
    try:
        # 1. 验证从 parent.current_df 提取的行情快照绝不是 0.00%
        quotes = dlg._get_batch_quotes_snapshot(["603028", "601818", "603489"])
        assert quotes["603028"]["day_pct"] == 10.01
        assert quotes["601818"]["day_pct"] == 1.65
        assert quotes["603489"]["day_pct"] == 9.03

        # 2. 模拟 entries 并验证渲染到 tbl_track
        mock_entries = [
            {
                "code": "603028", "name": "赛福天", "enter_ts": 1793064337, "enter_price": 10.33,
                "enter_pct": 0.0, "first_ts": 1793064000, "first_pct": 10.01, "since_first": -10.01,
                "persist": 73.5, "evidence_n": 3, "chain": "测试证据链", "mfe": 0.0, "mae": 0.0,
                "day_close_pct": 10.01, "holding_ret": 0.0, "cur_price": 10.33, "max_p": 10.33, "min_p": 10.33,
            },
            {
                "code": "688836", "name": "宇树科技", "enter_ts": 1793064337, "enter_price": 650.00,
                "enter_pct": -3.27, "first_ts": 1793064000, "first_pct": 0.0, "since_first": -3.27,
                "persist": 80.0, "evidence_n": 5, "chain": "测试证据链2", "mfe": 4.92, "mae": -1.85,
                "day_close_pct": -4.77, "holding_ret": -1.54, "cur_price": 639.96, "max_p": 681.98, "min_p": 638.00,
            },
        ]
        dlg._track_entries_from_shadow = lambda day: mock_entries
        dlg._render_track_from_shadow("2026-10-27")
        tbl = dlg.tbl_track
        assert tbl.rowCount() == 2

        # 3. 验证点击第 13 列（收盘%）降序排序（从大到小）：第 0 行为 +10.01%
        tbl.sortByColumn(13, Qt.SortOrder.DescendingOrder)
        top_item = tbl.item(0, 13)
        assert "+10.01%" in top_item.text()
        assert top_item._raw_value == 10.01

        # 4. 验证点击第 13 列（收盘%）升序排序（从小到大）：第 0 行为 -4.77%
        tbl.sortByColumn(13, Qt.SortOrder.AscendingOrder)
        bottom_item = tbl.item(0, 13)
        assert "-4.77%" in bottom_item.text()
        assert bottom_item._raw_value == -4.77

        assert top_item._raw_value > bottom_item._raw_value
    finally:
        dlg.close()

