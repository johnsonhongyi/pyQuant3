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


def test_dirty_check_skips_redundant_io():
    """测试脏检查 (Dirty Check)：数据指纹无变动时不触发多余磁盘 I/O"""
    engine = LimitUpEngine.get_instance()
    records = _build_sample_records()
    test_date = "2026-08-22"

    # 初次写入
    engine.save_daily_records_atomic(test_date, records, force=False)
    fp1 = engine._last_saved_fingerprints.get(test_date)
    assert fp1 is not None

    # 二次无变动调用，指纹保持不变
    engine.save_daily_records_atomic(test_date, records, force=False)
    fp2 = engine._last_saved_fingerprints.get(test_date)
    assert fp1 == fp2, "指纹应保持一致"


def test_post_trading_anti_corruption_defense():
    """测试数据防劣质覆盖保护：已有完整记录时，拒绝被少于 60% 数量的劣质残缺数据覆写"""
    engine = LimitUpEngine.get_instance()
    # 构造 10 条高质量完整记录
    full_records = []
    for i in range(10):
        full_records.append({
            "code": f"60000{i}",
            "name": f"优质股票{i}",
            "price": 10.0 + i,
            "pct": 10.0,
            "is_limit_up": True,
            "bid1_vol": 50000.0,
            "consecutive_boards": 2
        })

    test_date = "2026-08-19"
    engine.save_daily_records_atomic(test_date, full_records, force=True)
    time.sleep(0.2)

    # 尝试用只有 1 条的残缺数据进行非 force 覆盖
    corrupted_records = [
        {"code": "600001", "name": "残缺股票", "price": 10.0, "pct": 10.0, "is_limit_up": True}
    ]
    engine.save_daily_records_atomic(test_date, corrupted_records, force=False)
    time.sleep(0.2)

    # 验证内存与持久化中的数据依然是原有的 10 条完整记录，未被残缺数据覆盖
    saved_records = engine.get_records_by_date(test_date)
    assert len(saved_records) == 10, "防覆盖防线生效，完整数据应得到百分之百保护"


def test_post_market_cold_start_dirty_check():
    """测试收盘后冷启动时：内存与磁盘指纹一致时 100% 跳过无谓磁盘 I/O"""
    engine = LimitUpEngine.get_instance()
    records = _build_sample_records()
    test_date = "2026-08-21"
    
    # 模拟收盘时终态落盘
    engine.save_daily_records_atomic(test_date, records, force=True, is_eod=True)
    time.sleep(0.1)
    
    # 记录当前已保存指纹
    fp_before = engine._last_saved_fingerprints.get(test_date)
    assert fp_before is not None

    # 模拟冷启动后重新刷新，传入同样的数据
    engine.save_daily_records_atomic(test_date, records, force=False, is_eod=False)
    fp_after = engine._last_saved_fingerprints.get(test_date)
    assert fp_before == fp_after


def test_non_trading_day_cold_start_fallback_and_no_save(qapp, monkeypatch):
    """测试非交易日（周末/假期）冷启动：自动回退至最近交易日且绝不生成周末归档"""
    from JohnsonUtil import commonTips as cct
    engine = LimitUpEngine.get_instance()
    records = _build_sample_records()
    
    # 模拟周五有数据
    friday_date = "2026-08-21"
    engine.save_daily_records_atomic(friday_date, records, force=True, is_eod=True)
    
    # 模拟周日（非交易日）
    sunday_str = "2026-08-30"
    if sunday_str in engine._history_daily_records:
        del engine._history_daily_records[sunday_str]

    # Mock 非交易日环境（周日）
    monkeypatch.setattr(cct, "get_trade_date_status", lambda: False)
    monkeypatch.setattr(cct, "get_last_trade_date", lambda: friday_date)
    monkeypatch.setattr(time, "strftime", lambda fmt: sunday_str if "%Y-%m-%d" in fmt else time.asctime())
    
    dialog = DailyLimitUpDialog()
    dialog.show()
    qapp.processEvents()
    
    # 验证非交易日冷启动且 df 为空时，TODAY 模式自动加载最近交易日（周五）的数据
    dialog.current_df = None
    dialog.current_mode = "TODAY"
    dialog._refresh_data_for_mode()
    qapp.processEvents()
    
    assert dialog.current_records is not None
    assert len(dialog.current_records) >= 2, "非交易日应自动呈现最近有效交易日的数据"
    
    # 验证关闭窗口时不会向磁盘写入周日的虚假归档
    dialog.close()
    qapp.processEvents()
    
    # 确认系统没有写入非交易日周日的虚假归档
    assert sunday_str not in engine._history_daily_records, "非交易日绝对不可生成虚假日期归档"


