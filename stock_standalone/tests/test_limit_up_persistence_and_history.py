# -*- coding: utf-8 -*-
"""
测试涨停天梯每日数据全列持久化与历史回溯回放完整性
"""
import pytest
import os
import sys
import time
import json
import pandas as pd
from PyQt6.QtWidgets import QApplication

from ats.limit_up_engine import LimitUpEngine
from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _build_sample_records():
    engine = LimitUpEngine.get_instance()
    test_df = pd.DataFrame([
        {
            "code": "600785",
            "name": "新华百货",
            "trade": 10.71,
            "last_close": 9.74,
            "percent": 9.96,
            "open": 9.80,
            "high": 10.71,
            "low": 9.80,
            "vol": 158900.0,
            "amount": 170000000.0,
            "dff": 0.0,
            "DFF2": 22.7,
            "DFF3": 39.1,
            "Rank": 28,
            "n_bc": 24,
            "连阳": 3,
            "rec": 7,
            "ch_bc2": 19,
            "category": "粮食概念;IP经济;统一大市场"
        },
        {
            "code": "301520",
            "name": "万邦医药",
            "trade": 77.10,
            "last_close": 71.15,
            "percent": 8.36,
            "open": 72.0,
            "high": 85.38,
            "low": 71.5,
            "vol": 113300.0,
            "amount": 874000000.0,
            "dff": 1.5,
            "DFF2": 14.5,
            "DFF3": 227.4,
            "Rank": 311,
            "n_bc": 45,
            "连阳": 2,
            "rec": 8,
            "ch_bc2": 25,
            "category": "仿制药;一致性评价;CRO概念"
        }
    ]).set_index("code")

    return engine.scan_limit_up_records_from_df(
        test_df,
        fetch_l2_quotes=False,
        extra_cols=["n_bc", "连阳", "rec", "ch_bc2"]
    )


def test_limit_up_records_full_column_persistence():
    """测试涨停引擎扫描得到的数据结构包含全部指标列，且原子写盘后 100% 完整复原"""
    engine = LimitUpEngine.get_instance()
    records = _build_sample_records()

    assert len(records) >= 2, "应成功提取涨停与大阳冲板标的"

    rec1 = [r for r in records if r["code"] == "600785"][0]
    assert rec1["name"] == "新华百货"
    assert rec1["price"] == 10.71
    assert rec1["pct"] == 9.96
    assert rec1["dff2"] == 22.7
    assert rec1["dff3"] == 39.1
    assert rec1["rank"] == 28
    assert "24" in str(rec1["extra_cols"]["n_bc"])
    assert "3" in str(rec1["extra_cols"]["连阳"])
    assert "7" in str(rec1["extra_cols"]["rec"])
    assert "粮食概念" in rec1["category"]
    assert rec1["is_limit_up"] is True

    # 验证保存指定历史日期并读取
    test_date = "2026-08-23"
    engine.save_daily_records_atomic(test_date, records, force=True)
    time.sleep(0.3)

    loaded_records = engine.get_records_by_date(test_date)
    assert len(loaded_records) == len(records), "从持久化历史中加载的记录数应完全一致"

    loaded_rec1 = [r for r in loaded_records if r["code"] == "600785"][0]
    assert loaded_rec1["name"] == "新华百货"
    assert loaded_rec1["price"] == 10.71
    assert "24" in str(loaded_rec1["extra_cols"]["n_bc"])
    assert "3" in str(loaded_rec1["extra_cols"]["连阳"])
    assert "7" in str(loaded_rec1["extra_cols"]["rec"])


def test_daily_limit_up_dialog_history_view(qapp):
    """测试 DailyLimitUpDialog 在历史回溯模式下正确填充所有数据列"""
    engine = LimitUpEngine.get_instance()
    records = _build_sample_records()
    test_date = "2026-08-23"
    engine.save_daily_records_atomic(test_date, records, force=True)
    time.sleep(0.3)

    dialog = DailyLimitUpDialog()
    dialog.show()
    qapp.processEvents()

    # 切换到 2026-08-23 历史回溯
    dialog.selected_history_date = test_date
    dialog.current_mode = "HISTORY"
    dialog._refresh_data_for_mode()
    qapp.processEvents()

    assert dialog.table.rowCount() >= 2, "历史回溯表格应呈现保存的历史记录"

    # 验证第一行数据
    row0_code = dialog.table.item(0, 0).text()
    assert row0_code in ("600785", "301520")

    # 验证历史模式下，自动跟随被识别为全天全时段，不会过滤掉历史数据
    assert dialog.current_records is not None
    assert len(dialog.current_records) >= 2

    dialog.close()
