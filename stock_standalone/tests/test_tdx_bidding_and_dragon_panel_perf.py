# -*- coding: utf-8 -*-
"""
tests/test_tdx_bidding_and_dragon_panel_perf.py
================================================
全面验证：
1. TDX 专属交易时间放行策略 (is_tdx_trading_allowed): 09:16 提开放行、09:20 不可撤单、09:25 定盘、15:05 闭盘
2. 集合竞价早盘意图拟合与不可撤单突击加速检测算法 (record_and_evaluate_bidding_surge)
3. 资金主线看板 (CapitalDragonPanel) 防卡顿节流、单元格原地复用与切股防抖机制
"""

import os
import sys
import datetime
import pytest
import pandas as pd

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.tdx_realtime_fetcher import (
    is_tdx_trading_allowed,
    TDXRealtimeFetcher
)


def test_tdx_trading_time_policy():
    """测试 TDX API 专属交易时间放行策略 (09:16 放行至 15:05)"""
    # 模拟周一交易日 2026-09-14
    monday = datetime.date(2026, 9, 14)

    # 1. 09:10 (休市早盘)
    t_0910 = datetime.datetime.combine(monday, datetime.time(9, 10, 0))
    allowed, desc, meta = is_tdx_trading_allowed(t_0910)
    assert allowed is False
    assert meta["stage"] == "OFF_HOURS"

    # 2. 09:16 (早盘集合竞价: 试撮合拟合阶段, 可撤单)
    t_0916 = datetime.datetime.combine(monday, datetime.time(9, 16, 0))
    allowed, desc, meta = is_tdx_trading_allowed(t_0916)
    assert allowed is True
    assert meta["stage"] == "BIDDING_SIMULATION"
    assert meta["is_bidding"] is True
    assert meta["can_cancel"] is True
    assert meta["is_locked"] is False

    # 3. 09:19:50 (试撮合拟合阶段末期)
    t_0919 = datetime.datetime.combine(monday, datetime.time(9, 19, 50))
    allowed, desc, meta = is_tdx_trading_allowed(t_0919)
    assert allowed is True
    assert meta["stage"] == "BIDDING_SIMULATION"
    assert meta["can_cancel"] is True

    # 4. 09:20:00 (不可撤单申报与突击监控阶段)
    t_0920 = datetime.datetime.combine(monday, datetime.time(9, 20, 0))
    allowed, desc, meta = is_tdx_trading_allowed(t_0920)
    assert allowed is True
    assert meta["stage"] == "BIDDING_LOCKED"
    assert meta["is_bidding"] is True
    assert meta["can_cancel"] is False
    assert meta["is_locked"] is True

    # 5. 09:24:40 (不可撤单申报与突击加速监测)
    t_0924 = datetime.datetime.combine(monday, datetime.time(9, 24, 40))
    allowed, desc, meta = is_tdx_trading_allowed(t_0924)
    assert allowed is True
    assert meta["stage"] == "BIDDING_LOCKED"

    # 6. 09:25:30 (定盘静默期)
    t_0925 = datetime.datetime.combine(monday, datetime.time(9, 25, 30))
    allowed, desc, meta = is_tdx_trading_allowed(t_0925)
    assert allowed is True
    assert meta["stage"] == "BIDDING_FINALIZED"

    # 7. 09:35:00 (连续交易)
    t_0935 = datetime.datetime.combine(monday, datetime.time(9, 35, 0))
    allowed, desc, meta = is_tdx_trading_allowed(t_0935)
    assert allowed is True
    assert meta["stage"] == "CONTINUOUS_TRADING"

    # 8. 11:45:00 (午间休市)
    t_1145 = datetime.datetime.combine(monday, datetime.time(11, 45, 0))
    allowed, desc, meta = is_tdx_trading_allowed(t_1145)
    assert allowed is False
    assert meta["stage"] == "NOON_REST"

    # 9. 15:02:00 (尾盘收盘集合竞价)
    t_1502 = datetime.datetime.combine(monday, datetime.time(15, 2, 0))
    allowed, desc, meta = is_tdx_trading_allowed(t_1502)
    assert allowed is True
    assert meta["stage"] == "CLOSING_AUCTION"

    # 10. 15:05:01 (收盘休盘)
    t_1506 = datetime.datetime.combine(monday, datetime.time(15, 6, 0))
    allowed, desc, meta = is_tdx_trading_allowed(t_1506)
    assert allowed is False
    assert meta["stage"] == "OFF_HOURS"

    # 11. 周六测试
    saturday = datetime.datetime(2026, 9, 12, 10, 0, 0)
    allowed, desc, meta = is_tdx_trading_allowed(saturday)
    assert allowed is False


def test_bidding_surge_and_intent_detection():
    """测试早盘集合竞价试盘意图拟合与不可撤单突击极强信号算法"""
    fetcher = TDXRealtimeFetcher.get_instance()
    code = "688826"
    fetcher.clear_stock_cache(code)

    trade_date = datetime.date(2026, 9, 14)

    # ── 场景 1: 09:16 ~ 09:19 试撮合拟合阶段 ────────────────────────────────
    # 09:16:10 拟合平开 0%
    q1 = {"code": code, "price": 100.0, "last_close": 100.0, "bid_vol1": 500, "ask_vol1": 500}
    t1 = datetime.datetime.combine(trade_date, datetime.time(9, 16, 10))
    res1 = fetcher.record_and_evaluate_bidding_surge(q1, now_dt=t1)
    assert res1["bidding_stage"] == "SIMULATION"

    # 09:17:00 虚假试盘打压至 -4.0%
    q2 = {"code": code, "price": 96.0, "last_close": 100.0, "bid_vol1": 200, "ask_vol1": 2000}
    t2 = datetime.datetime.combine(trade_date, datetime.time(9, 17, 0))
    res2 = fetcher.record_and_evaluate_bidding_surge(q2, now_dt=t2)
    assert res2["bidding_stage"] == "SIMULATION"
    assert "试盘" in res2["bidding_signal"]

    # 09:19:40 撤单回撤至 -0.5%
    q3 = {"code": code, "price": 99.5, "last_close": 100.0, "bid_vol1": 1000, "ask_vol1": 1000}
    t3 = datetime.datetime.combine(trade_date, datetime.time(9, 19, 40))
    res3 = fetcher.record_and_evaluate_bidding_surge(q3, now_dt=t3)
    assert res3["bidding_stage"] == "SIMULATION"

    # ── 场景 2: 09:20:00 进入不可撤单阶段 (锁定基准) ──────────────────────────
    # 09:20:05 不可撤单基准确立: 昨收 100.0, 拟合价 99.5 (-0.5%)
    q4 = {"code": code, "price": 99.5, "last_close": 100.0, "bid_vol1": 1200, "ask_vol1": 1100}
    t4 = datetime.datetime.combine(trade_date, datetime.time(9, 20, 5))
    res4 = fetcher.record_and_evaluate_bidding_surge(q4, now_dt=t4)
    assert res4["bidding_stage"] == "LOCKED"
    assert res4["bidding_surge_pct"] == 0.0

    # ── 场景 3: 09:23:00 不可撤单突然真金白银突击加速爆拉 (+3.0%) ──────────
    # 从 99.5 突击拉升至 103.0 (+3.0%, 较09:20基准突击幅度 +3.5%)
    # 且之前试盘阶段有 -4% 诱空，触发【试盘诱空真实反抢】或【竞价低开突击抢筹】极强信号！
    q5 = {"code": code, "price": 103.0, "last_close": 100.0, "bid_vol1": 8000, "ask_vol1": 1000}
    t5 = datetime.datetime.combine(trade_date, datetime.time(9, 23, 0))
    res5 = fetcher.record_and_evaluate_bidding_surge(q5, now_dt=t5)
    assert res5["bidding_stage"] == "LOCKED"
    assert res5["bidding_surge_pct"] >= 2.0
    assert any(sig in res5["bidding_signal"] for sig in ["抢筹", "反抢", "突击"])

    # ── 场景 4: 09:25:30 盘中定盘与回溯查询 ──────────────────────────────
    t6 = datetime.datetime.combine(trade_date, datetime.time(9, 26, 0))
    res6 = fetcher.record_and_evaluate_bidding_surge(q5, now_dt=t6)
    assert res6["bidding_stage"] == "FINALIZED"
    assert res6["bidding_surge_pct"] >= 2.0

    analysis = fetcher.get_bidding_analysis(code)
    assert analysis["bidding_surge_pct"] >= 2.0

    # ── 场景 5: 09:25:30 对新出现的标的进行定盘补偿测试 ────────────────────
    new_code = "600519"
    q_new = {"code": new_code, "price": 1800.0, "last_close": 1750.0, "bid_vol1": 100, "ask_vol1": 100}
    res_new = fetcher.record_and_evaluate_bidding_surge(q_new, now_dt=t6)
    assert res_new["bidding_stage"] == "FINALIZED"
    assert "定盘" in res_new["bidding_signal"]

    # ── 场景 6: 跨日自动清空与重置基准测试 (7x24 小时挂机安全) ──────────────
    next_day = datetime.date(2026, 9, 15)
    t_next_0916 = datetime.datetime.combine(next_day, datetime.time(9, 16, 30))
    q_next = {"code": code, "price": 105.0, "last_close": 103.0, "bid_vol1": 1000, "ask_vol1": 1000}
    res_next = fetcher.record_and_evaluate_bidding_surge(q_next, now_dt=t_next_0916)
    assert res_next["bidding_stage"] == "SIMULATION"
    assert code not in fetcher._bidding_locked_base  # 前一天的 09:20 锚定已干净清空


def test_bidding_dump_warning():
    """测试不可撤单阶段突击抢砸跳水极强风险信号"""
    fetcher = TDXRealtimeFetcher.get_instance()
    code = "000001"
    fetcher.clear_stock_cache(code)
    trade_date = datetime.date(2026, 9, 14)

    # 09:20:00 基准为红盘 +3.0% (price=10.30, last_close=10.00)
    q1 = {"code": code, "price": 10.30, "last_close": 10.00, "bid_vol1": 5000, "ask_vol1": 1000}
    t1 = datetime.datetime.combine(trade_date, datetime.time(9, 20, 5))
    fetcher.record_and_evaluate_bidding_surge(q1, now_dt=t1)

    # 09:23:30 突遭不可撤单持续大单砸盘下杀至 9.90 (-1.0%, 较基准下砸 -4.0%)
    q2 = {"code": code, "price": 9.90, "last_close": 10.00, "bid_vol1": 100, "ask_vol1": 20000}
    t2 = datetime.datetime.combine(trade_date, datetime.time(9, 23, 30))
    res2 = fetcher.record_and_evaluate_bidding_surge(q2, now_dt=t2)
    assert res2["bidding_stage"] == "LOCKED"
    assert res2["bidding_surge_pct"] <= -2.0
    assert any(sig in res2["bidding_signal"] for sig in ["抢砸", "下砸", "砸盘"])


def test_capital_dragon_panel_in_place_cell_reuse():
    """测试 CapitalDragonPanel 原地复用更新与 Dirty Check 机制"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from ats.ui.capital_dragon_panel import CapitalDragonPanel

    panel = CapitalDragonPanel()
    assert hasattr(panel, '_set_or_update_cell')
    assert hasattr(panel, '_throttle_timer')
    assert hasattr(panel, '_trigger_stock_linkage')

    panel.table.setRowCount(2)
    panel.table.setColumnCount(5)

    # 首次填充 (创建单元格)
    panel._set_or_update_cell(0, 0, "688826", raw_val=0)
    item1 = panel.table.item(0, 0)
    assert item1 is not None
    assert item1.text() == "688826"

    # 再次原地更新 (文本未变，对象应被完全复用，绝不重构)
    panel._set_or_update_cell(0, 0, "688826", raw_val=0)
    item2 = panel.table.item(0, 0)
    assert item1 is item2  # 同一个对象，无垃圾回收开销

    # 原地更新变动值
    panel._set_or_update_cell(0, 0, "600519", raw_val=0)
    assert item2.text() == "600519"
    assert item1 is item2

    # 选股联动去重测试
    emitted = []
    panel.stock_selected.connect(lambda c, n: emitted.append((c, n)))

    panel._trigger_stock_linkage("688826", "晶晨股份")
    assert len(emitted) == 1
    assert emitted[0][0] == "688826"

    # 连续再次触发相同标的 -> 拦截防抖
    panel._trigger_stock_linkage("688826", "晶晨股份")
    assert len(emitted) == 1  # 依然为 1，成功去重！

    # 切换不同标的 -> 正常放行
    panel._trigger_stock_linkage("600519", "贵州茅台")
    assert len(emitted) == 2
    assert emitted[1][0] == "600519"
