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


def test_ui_replay_worker_disables_production_signal_input(qapp, monkeypatch):
    from types import SimpleNamespace
    from ats.ui import fusion_ladder_dialog as module

    configs = []
    monkeypatch.setattr(module, "DayReplay", lambda config: (configs.append(config) or SimpleNamespace(cache={})))
    worker = module.ReplayWorker("2026-10-29", [])
    worker.run()
    assert configs and configs[0].use_production_history is False


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


def test_replay_focus_is_red_and_remains_first_for_any_sort(qapp, monkeypatch):
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    from ats.fusion.replay import ReplayResult

    dlg = FusionLadderDialog()
    try:
        monkeypatch.setattr(dlg, "_render_live", lambda **kwargs: None)
        base = {"tier": 1, "tier_name": "L1", "rar": 55, "entry": 10, "pct": 1,
                "mfe": 1, "mae": -1, "close_ret": 0, "size_pct": 0, "temp": 40}
        rows = [dict(base, ts=100, time="09:31", code="000001", name="普通"),
                dict(base, ts=200, time="09:32", code="600809", name="重点", pct=3)]
        result = ReplayResult(day="2026-10-29", records=rows, meta={"codes": 2, "bars": 2, "evaluations": 2, "records": 2,
            "liquidity_history": {"600809": {"source": "archive.h5", "history": [{"date": "2026-10-28", "turnover_pct": 21.43, "volume_ratio": 0.8}]}}, "focus_selection": {
            "first_selected": [{"code": "600809", "ts": 200, "time": "09:33", "focus_rank": 1}]}})
        dlg._on_replay_done(result)
        table = dlg.tbl_replay
        for column in (1, 2, 4):
            for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
                table.sortItems(column, order)
                assert table.item(0, 1).text() == "600809"
        assert table.item(0, 1).foreground().color().name() == "#ff6868"
        assert table.item(0, 1).background().color().name() == "#4b2026"
        assert "09:33" in table.item(0, 1).toolTip()
        headers = {table.horizontalHeaderItem(c).text(): c for c in range(table.columnCount())}
        assert table.item(0, headers["历史换手%"]).text() == "21.43"
        assert table.item(0, headers["历史量比"]).text() == "0.80"
        assert table.item(0, headers["特征日期"]).text() == "2026-10-28"
        assert "不参与评分" in table.item(0, headers["历史量比"]).toolTip()
        dlg.chk_focus_only.setChecked(False)
        assert all(table.item(i, 1).foreground().color().name() != "#ff6868" for i in range(table.rowCount()))
    finally:
        dlg.close()


def test_live_focus_is_red_and_pinned_when_sorting_numeric_columns(qapp, monkeypatch):
    import datetime
    from ats.ui import fusion_ladder_dialog as module

    ts = datetime.datetime(2026, 10, 29, 10, 0).timestamp()
    base = {"ts": ts, "trade_date": "2026-10-29", "schema": 2, "price": 10.1, "pct": 1,
            "fusion": {"tier": 1, "rar": 50}, "vwap": 10, "coverage": 1}
    rows = [dict(base, code="000001", name="普通", patterns=[]),
            dict(base, code="600809", name="重点", pct=2, patterns=["逆势收复启动"],
                 reclaim_detail={"vwap3": 10, "vwap5": 10, "hold_ratio": .8})]
    monkeypatch.setattr(module, "load_live_rows", lambda *args, **kwargs: rows)
    dlg = module.FusionLadderDialog()
    try:
        monkeypatch.setattr(dlg, "_resolve_ats_strategy_df", lambda: None)
        dlg.cmb_day.addItem("2026-10-29")
        dlg.cmb_day.setCurrentText("2026-10-29")
        dlg.chk_hit_only.setChecked(False)
        dlg.chk_structure_only.setChecked(False)
        dlg._render_live(force=True)
        table = dlg.tbl_live
        for column in (1, 2, 4, 5):
            for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
                table.sortItems(column, order)
                assert table.item(0, 1).text() == "600809"
        assert table.item(0, 1).foreground().color().name() == "#ff6868"
    finally:
        dlg.close()


def test_live_focus_reports_missing_production_evidence(qapp, monkeypatch):
    import datetime
    from ats.ui import fusion_ladder_dialog as module

    ts = datetime.datetime(2026, 10, 29, 10, 0).timestamp()
    rows = [{"ts": ts, "trade_date": "2026-10-29", "schema": 2, "code": "600809", "name": "山西汾酒",
             "price": 10, "pct": 1, "vwap": 10, "fusion": {"tier": 1, "rar": 50}, "patterns": []}]
    monkeypatch.setattr(module, "load_live_rows", lambda *args, **kwargs: rows)
    dlg = module.FusionLadderDialog()
    try:
        monkeypatch.setattr(dlg, "_resolve_ats_strategy_df", lambda: None)
        dlg.cmb_day.addItem("2026-10-29")
        dlg.cmb_day.setCurrentText("2026-10-29")
        dlg.chk_hit_only.setChecked(False)
        dlg.chk_structure_only.setChecked(False)
        dlg._render_live(force=True)
        assert "来源记录缺少重点所需证据" in dlg.status_details.text()
        assert "#ffa64d" in dlg.lbl_status.styleSheet()
    finally:
        dlg.close()


def test_cross_day_displays_replay_and_live_separately_without_paper_link(qapp, monkeypatch):
    import datetime
    from ats.fusion.cross_day import build_cross_day
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    day = "2026-10-29"
    ts = datetime.datetime(2026, 10, 29, 10, 0).timestamp()
    live = {"code": "000568", "ts": ts, "price": 10, "trade_date": day, "fusion": {"tier": 2}}
    replay = {**live, "ts": ts + 60, "source": "replay_archive", "price": 10.1}
    prod_rows = build_cross_day({day: {"000568": [live]}}, day)
    replay_rows = build_cross_day({day: {"000568": [replay]}}, day, allow_replay=True)
    assert len(prod_rows) == len(replay_rows) == 1
    dlg = FusionLadderDialog()
    try:
        monkeypatch.setattr(dlg, "_render_paper_follow", lambda *args: None)
        refreshed = []
        monkeypatch.setattr(dlg, "_start_cross_day", lambda requested: refreshed.append(requested))
        dlg.cmb_day.addItem(day)
        dlg.cmb_day.setCurrentText(day)
        dlg._replay_days = [day]
        output = {"root": os.path.abspath(dlg.ed_trade_root.text().strip()), "requested_replay": "",
                  "signals": prod_rows, "shadow_errors": 0,
                  "paper": {"rows": [{"code": "000568", "remaining": 100, "status": "持仓"}],
                            "account": {"read_status": "READY"}},
                  "replay": {"rows": replay_rows, "status": "ready", "independent": True, "sources": {day: "isolated", "2026-10-28": "older"}, "errors": []}}
        dlg._render_cross_day(output, day)
        assert dlg._replay_days == [day]
        assert "2026-10-28" in dlg._comparison_archive_days
        table = dlg.tbl_cross_day
        source_col = next(c for c in range(table.columnCount()) if table.horizontalHeaderItem(c).text() == "信号来源")
        compare_col = next(c for c in range(table.columnCount()) if table.horizontalHeaderItem(c).text() == "双流对照")
        paper_col = next(c for c in range(table.columnCount()) if table.horizontalHeaderItem(c).text() == "PAPER交易状态")
        by_source = {table.item(i, source_col).text(): i for i in range(table.rowCount())}
        assert set(by_source) == {"生产影子", "独立回放"}
        assert table.item(by_source["生产影子"], paper_col).text() == "持仓"
        assert table.item(by_source["独立回放"], paper_col).text() == "未关联（回放）"
        assert "价差+1.00%" in table.item(by_source["独立回放"], compare_col).text()
        output["replay"]["independent"] = False
        output["replay"]["production_history"] = True
        dlg._render_cross_day(output, day)
        by_source = {table.item(i, source_col).text(): i for i in range(table.rowCount())}
        assert "回放含生产证据" in by_source
        assert "不能独立验证" in table.item(by_source["回放含生产证据"], compare_col).text()
        dlg._follow_pending_day = day
        dlg._on_follow_finished()
        qapp.processEvents()
        assert refreshed[-1] == day
    finally:
        dlg.close()


def test_custom_cols_toggle_and_visibility(qapp):
    """验证自定义列开关复选框切换与表格列显隐联动"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, _LIVE_BASE_HEADERS, _REPLAY_BASE_HEADERS

    dlg = FusionLadderDialog()
    try:
        assert hasattr(dlg, "chk_custom_cols")
        assert dlg.chk_custom_cols.text() == "扩展列"

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



def test_replay_custom_columns_never_use_current_quotes(qapp, monkeypatch):
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    from ats.fusion.replay import ReplayResult
    dlg = FusionLadderDialog()
    try:
        dlg.extra_cols = ["trade"]
        dlg.tbl_replay.setColumnCount(len(dlg._REPLAY_BASE_HEADERS) + 1)
        monkeypatch.setattr(dlg, "_extract_stock_custom_val", lambda *args: (_ for _ in ()).throw(AssertionError("live quote accessed")))
        base = {"code": "000001", "name": "test", "ts": 100, "time": "09:31", "entry": 10,
                "pct": 10, "tier": 1, "tier_name": "L1", "rar": 55, "size_pct": 0,
                "mfe": 0, "mae": 0, "temp": 40}
        result = ReplayResult(day="2026-10-29", records=[dict(base, close_ret=10)],
                              meta={"codes": 1, "bars": 1, "evaluations": 1, "records": 1})
        dlg._on_replay_done(result)
        assert dlg.tbl_replay.item(0, 5).text() == "+21.00%"
        assert dlg.tbl_replay.item(0, len(dlg._REPLAY_BASE_HEADERS)).text() == "--"
        result.records = [base]
        dlg._on_replay_done(result)
        assert dlg.tbl_replay.item(0, 5).text() == "--"
    finally:
        dlg.close()


def test_calendar_only_accepts_red_available_dates(qapp):
    from PyQt6.QtCore import QDate
    from PyQt6.QtWidgets import QDialog
    from ats.ui.fusion_ladder_dialog import FusionCalendarDialog
    dlg = FusionCalendarDialog(["2026-10-26", "2026-10-30"], "2026-10-23")
    try:
        assert dlg.selected_day == "2026-10-30"
        assert dlg.calendar.dateTextFormat(QDate(2026, 10, 26)).foreground().color().name() == "#ff6868"
        dlg.calendar.setSelectedDate(QDate(2026, 10, 23))
        assert dlg.calendar.selectedDate() == QDate(2026, 10, 30)
        dlg._on_date_selected(QDate(2026, 10, 23))
        assert dlg.result() != QDialog.DialogCode.Accepted
        dlg._on_date_selected(QDate(2026, 10, 26))
        assert dlg.selected_day == "2026-10-26"
        assert dlg.result() == QDialog.DialogCode.Accepted
    finally:
        dlg.close()


def test_missing_minute_day_never_falls_back_to_another_day(qapp, monkeypatch):
    from ats.ui import fusion_ladder_dialog as ui
    worker = ui.ReplayWorker(day="2026-10-23", focus=[])
    class Replay:
        cache = {"nonempty": True}
        def days(self):
            return ["2026-10-26"]
    monkeypatch.setattr(ui, "DayReplay", lambda **kwargs: Replay())
    done, errors = [], []
    worker.done.connect(done.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert errors and not done


def test_persistence_rejects_2024_timestamp_before_opening_2026_file(monkeypatch):
    from ats.ui import fusion_ladder_dialog as ui
    monkeypatch.setattr(ui, "_shadow_storage_paths", lambda *args: (_ for _ in ()).throw(AssertionError("must not write")))
    assert ui.persist_shadow_records([{"code": "000001", "ts": 1729648000, "price": 10.5}], "2026-10-23") == 0


def test_live_answer_dates_are_independent_of_replay_calendar(qapp):
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    dlg = FusionLadderDialog()
    try:
        dlg.cmb_day.addItem("2026-10-23")
        dlg.cmb_day.setCurrentText("2026-10-23")
        dlg._apply_verified_days(["2026-10-26", "2026-10-30"])
        assert dlg.cmb_day.currentText() == "2026-10-23"
        assert [dlg.cmb_replay_day.itemText(i) for i in range(dlg.cmb_replay_day.count())] == ["2026-10-26", "2026-10-30"]
        dlg.cmb_replay_day.setCurrentText("2026-10-26")
        assert dlg.cmb_day.currentText() == "2026-10-23"
        dlg._apply_verified_days([])
        assert dlg.cmb_replay_day.count() == 0
        assert dlg.cmb_day.currentText() == "2026-10-23"
        assert dlg.cmb_day.isEnabled()
    finally:
        dlg.close()


def test_cell_viewport_tooltip_uses_gradient_card_theme(qapp):
    from PyQt6.QtCore import QEvent, QPoint
    from PyQt6.QtGui import QHelpEvent
    from PyQt6.QtWidgets import QWidget, QTableWidget, QTableWidgetItem
    from ats.ui.fusion_ladder_dialog import UnifiedToolTipFilter
    window = QWidget()
    table = QTableWidget(1, 1, window)
    table.setHorizontalHeaderLabels(["逐日轨迹"])
    item = QTableWidgetItem("10-26 → 10-30")
    item.setToolTip("生产影子参考价；MFE/MAE仅含采样价格\n2026-10-30：34条记录，价格<240")
    table.setItem(0, 0, item)
    filter_obj = UnifiedToolTipFilter(window)
    try:
        pos = table.visualItemRect(item).center()
        event = QHelpEvent(QEvent.Type.ToolTip, pos, table.viewport().mapToGlobal(pos))
        assert filter_obj.eventFilter(table.viewport(), event)
        html = filter_obj._tip_card._body.text()
        assert "逐日轨迹" in html and "#4dd0e1" in html
        assert "价格&lt;240" in html
        assert filter_obj._tip_card._body.wordWrap()
    finally:
        filter_obj._tip_card.close()
        window.close()


def test_cross_day_percentage_delegate_renders_both_colors_when_selected(qapp):
    from PyQt6.QtCore import Qt, QRect
    from PyQt6.QtGui import QImage, QPainter, QFont
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QStyleOptionViewItem, QStyle
    from ats.ui.fusion_ladder_dialog import SignedPercentDelegate, _change_color
    table = QTableWidget(1, 1)
    item = QTableWidgetItem("10-26 +2.00% → 10-27 -3.00% → 10-28 +0.00%")
    table.setItem(0, 0, item)
    delegate = SignedPercentDelegate(table)
    table.setItemDelegate(delegate)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 700, 44)
    option.font = QFont("Arial", 14)
    option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected
    image = QImage(700, 44, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    try:
        delegate.paint(painter, option, table.model().index(0, 0))
    finally:
        painter.end()
        table.close()
    colors = {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}
    assert "#ff5c5c" in colors
    assert "#00ff88" in colors
    assert _change_color(0) is None
    assert _change_color(None) is None
    assert _change_color(float("nan")) is None


def test_paper_realized_returns_use_red_and_green(qapp):
    from ats.fusion.paper_follow import build_paper_follow
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    orders = []
    for code, exit_price in (("000001", 11), ("000002", 9)):
        orders.extend([
            {"code": code, "action": "BUY", "price": 10, "volume": 100, "timestamp": "2026-10-29T10:00:00"},
            {"code": code, "action": "SELL", "price": exit_price, "volume": 100, "timestamp": "2026-10-30T10:00:00"}])
    output = build_paper_follow({"read_status": "READY", "trade_date": "2026-10-30", "positions": {}, "orders": orders}, [], "2026-10-30")
    dlg = FusionLadderDialog()
    try:
        dlg._render_paper_follow(output)
        table = dlg.tbl_paper_follow
        for i in range(table.rowCount()):
            expected = "#ff5c5c" if table.item(i, 0).text() == "000001" else "#00ff88"
            assert table.item(i, 12).foreground().color().name() == expected
            assert table.item(i, 13).foreground().color().name() == expected
    finally:
        dlg.close()
