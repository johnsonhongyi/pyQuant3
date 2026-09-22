# -*- coding: utf-8 -*-
"""Tests for UI decision badges (WEAKENED / INVALIDATED / Drawdown) and shadow live runner."""

import os
import pytest
from types import SimpleNamespace

from ats.signal_ledger import SignalLedger, SignalEntry
from ats.universe_manager import UniverseManager
from tools.run_shadow_live_test import ShadowTestHealthMonitor, run_shadow_test


def test_universe_manager_extracts_weakened_and_invalidated_badges():
    mgr = UniverseManager()
    ledger = SignalLedger()

    # 1. 正常标的
    normal_entry = SignalEntry(
        code="000001",
        name="平安银行",
        price=10.0,
        pct=1.0,
        deviation=0.5,
        phase="GOLDEN",
    )
    normal_entry.tier = "WATCH"
    normal_entry.peak_pct = 1.0
    ledger.entries["000001"] = normal_entry

    # 2. 动能走弱标的 (高位回撤 4.5%)
    weak_entry = SignalEntry(
        code="600519",
        name="贵州茅台",
        price=1600.0,
        pct=0.5,
        deviation=1.0,
        phase="GOLDEN",
    )
    weak_entry.tier = "WATCH"
    weak_entry.peak_pct = 5.0  # Peak 5.0% -> Current 0.5% => Drawdown 4.5%
    weak_entry.weak_since_ts = 1700000000.0
    weak_entry.state_history.append({
        "action": "WEAKENED_BY_MOMENTUM_REVERSAL",
        "reason": "峰值回撤4.50个百分点",
    })
    ledger.entries["600519"] = weak_entry

    # 3. 结构失效标的 (双VWAP破位)
    inv_entry = SignalEntry(
        code="300750",
        name="宁德时代",
        price=240.0,
        pct=-2.5,
        deviation=-3.5,
        phase="GOLDEN",
    )
    inv_entry.tier = "INACTIVE"
    inv_entry.signal_tag = "⛔ 双VWAP破位"
    inv_entry.state_history.append({
        "action": "INVALIDATED_BY_CROSS_DAY_VWAP",
        "reason": "跌破今日VWAP后跌破昨日VWAP，WATCH->INACTIVE",
    })
    ledger.entries["300750"] = inv_entry

    # 同步投影
    mgr.sync_from_ledger(ledger)

    # 验证 watch_pool
    assert "000001" in mgr.watch_pool
    assert mgr.watch_pool["000001"]["lifecycle_badge"] == ""

    assert "600519" in mgr.watch_pool
    assert "⚠️ 回撤" in mgr.watch_pool["600519"]["lifecycle_badge"]
    assert mgr.watch_pool["600519"]["drawdown_pct"] == pytest.approx(4.5, 0.1)
    assert "⚠️ 回撤" in mgr.watch_pool["600519"]["strategy"]
    assert "高位回撤" in mgr.watch_pool["600519"]["reason"]


def test_shadow_health_monitor_records_metrics_and_dump_json(tmp_path):
    log_dir = str(tmp_path / "logs")
    monitor = ShadowTestHealthMonitor(log_dir=log_dir)

    metrics = monitor.record_round(
        signal_count=5,
        directive_count=1,
        active_positions=2,
        ledger_stats={"total_entries": 10},
    )

    assert metrics["rounds_completed"] == 1
    assert metrics["signals_processed"] == 5
    assert metrics["directives_generated"] == 1
    assert metrics["status"] == "HEALTHY"
    assert metrics["memory_rss_mb"] >= 0.0

    # Verify report file exists
    files = os.listdir(log_dir)
    assert any(f.startswith("shadow_test_report_") for f in files)


def test_shadow_runner_dry_run_executes_safely():
    res = run_shadow_test(dry_run=True, interval_seconds=0.01)
    assert res["rounds_completed"] == 2
    assert res["status"] == "HEALTHY"
    assert res["errors_encountered"] == 0
