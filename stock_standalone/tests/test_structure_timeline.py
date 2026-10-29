# -*- coding: utf-8 -*-
"""结构信号时间轴测试：可成立、可失守、可剔除、可复活。

覆盖 2026-10-29 审核报告中的 P0：
    1. 悬空垫从"全时段累计最小"改为"滚动窗口"，价格重新站上均线后可恢复；
    2. 结构保底只允许越过 RAR 分档，不得越过温度/老化/组合预算等风控上限；
    3. rebalance 对结构票必须收敛，不得死循环；
    4. 失守/剔除后必须撤销保底并降档（不及预期就剔除）。
"""

from __future__ import annotations

import pytest

from ats.fusion.anomaly import (
    PATTERN_STRUCTURE_BREAK,
    PATTERN_STRUCTURE_CONFIRM,
    detect_patterns,
    pattern_score,
)
from ats.fusion.contract import SignalEvent
from ats.fusion.engine import FusionBus, FusionEngine
from ats.fusion.enrich import intraday_fields
from ats.fusion.structure_timeline import (
    STATUS_BROKEN,
    STATUS_CONFIRMED,
    STATUS_EVICTED,
    STATUS_WAITING,
    StructureTimeline,
)


# ---------------------------------------------------------------------------
# 1. 滚动悬空垫：跌过一次之后还能恢复
# ---------------------------------------------------------------------------
def _bars_with_dip(n: int = 30, dip_at: int = 5):
    """构造一段上行分时，在第 dip_at 根插一根跌破均线的针，其余时间都在均线上方。"""
    bars = []
    for i in range(n):
        c = 10.0 + i * 0.02
        low = c - 0.01
        if i == dip_at:
            low = 9.50          # 一次深度插针，全时段最小值会被它永久污染
        bars.append({"open": c, "high": c + 0.02, "low": low, "close": c, "vol": 1000.0})
    return bars


def test_rolling_cushion_recovers_after_dip():
    out = intraday_fields(_bars_with_dip(), price=10.6, cushion_window=20)
    # 全时段最小值被那根针打成负数（旧口径 → 当日永久失效）
    assert out["min_vwap_cushion"] < 0
    # 滚动窗口只看最近 20 根，早已不含那根针 → 结构可以重新成立
    assert out["cushion_roll"] > 0.0
    assert out["cushion_now"] > 0.0
    assert 0.0 <= out["vwap_hold_ratio"] <= 1.0


def test_rolling_cushion_detects_recent_break():
    bars = _bars_with_dip(n=30, dip_at=28)  # 针落在窗口内
    out = intraday_fields(bars, price=10.6, cushion_window=20)
    assert out["cushion_roll"] < 0.0


# ---------------------------------------------------------------------------
# 2. 状态机：成立 → 失守 → 重新成立
# ---------------------------------------------------------------------------
def test_timeline_confirm_break_reconfirm():
    tl = StructureTimeline(cushion_min=0.20, drawdown_limit=1.5)
    kw = dict(hi_pre1=10.0, close_pre1=9.9, prejudged=True)

    s = tl.update("600118", 100.0, price=10.2, vwap=10.0, cushion_roll=0.6, cushion_now=2.0, **kw)
    assert s.status == STATUS_CONFIRMED
    assert s.confirm_n == 1

    # 跌破分时均线 → 失守（撤销保底）
    s = tl.update("600118", 200.0, price=9.95, vwap=10.0, cushion_roll=-0.4, cushion_now=-0.5, **kw)
    assert s.status == STATUS_BROKEN
    assert s.break_n == 1
    assert s.blocked() is True

    # 价格重新站上均线并再破昨高 → 结构重新成立（不是一锤子买卖）
    s = tl.update("600118", 300.0, price=10.3, vwap=10.05, cushion_roll=0.5, cushion_now=2.5, **kw)
    assert s.status == STATUS_CONFIRMED
    assert s.confirm_n == 2


def test_timeline_drawdown_triggers_break():
    tl = StructureTimeline(cushion_min=0.20, drawdown_limit=1.5)
    kw = dict(hi_pre1=10.0, close_pre1=9.9, prejudged=True)
    tl.update("002865", 100.0, price=10.5, vwap=10.0, cushion_roll=0.8, cushion_now=5.0, **kw)
    # 自高点回撤 2%（价格仍在均线上方，但结构已走坏）
    s = tl.update("002865", 200.0, price=10.29, vwap=10.0, cushion_roll=0.5, cushion_now=2.9, **kw)
    assert s.status == STATUS_BROKEN
    assert "回撤" in s.reason


def test_timeline_evict_then_rearm():
    tl = StructureTimeline(cushion_min=0.20, max_break_n=2, rearm_bars=2)
    kw = dict(hi_pre1=10.0, close_pre1=9.9, prejudged=True)

    def confirm(ts, px=10.3):
        return tl.update("300827", ts, price=px, vwap=10.0, cushion_roll=0.6, cushion_now=3.0, **kw)

    def brk(ts):
        return tl.update("300827", ts, price=9.95, vwap=10.0, cushion_roll=-0.5, cushion_now=-0.5, **kw)

    confirm(100.0)
    assert brk(200.0).status == STATUS_BROKEN
    confirm(300.0)
    s = brk(400.0)
    assert s.status == STATUS_EVICTED          # 反复失守 → 当日剔除
    assert s.break_n == 2

    # 剔除后单次满足不够，必须连续 rearm_bars 次复核
    s = confirm(500.0)
    assert s.status == STATUS_EVICTED
    s = confirm(600.0)
    assert s.status == STATUS_CONFIRMED        # "直到符合条件" → 允许复活
    assert s.break_n >= 2                      # 履历保留，复活后只有更短的机会


def test_timeline_waits_without_prejudge():
    tl = StructureTimeline()
    s = tl.update("600000", 100.0, price=10.5, vwap=10.0, hi_pre1=10.0, close_pre1=9.9,
                  cushion_roll=0.9, cushion_now=5.0, prejudged=False)
    assert s.status == STATUS_WAITING


# ---------------------------------------------------------------------------
# 3. 形态层：用滚动垫而不是全时段最小值
# ---------------------------------------------------------------------------
def _detect(**kw):
    base = dict(
        price=10.5, day_open=10.0, ma5=10.0, ma10=10.0, ma20=10.0, pct=5.0,
        ret_std20=1.0, vol_ratio=1.5, rs5=1.0, mkt_ret5=0.0,
        vwap10=10.0, hi_pre1=10.4, hi_10d=11.0,
        is_structure_prejudged=True, close_over_vwap10=True,
    )
    base.update(kw)
    return detect_patterns(**base)


def test_anomaly_structure_confirm_uses_rolling_cushion():
    # 全时段最小值已为负（旧口径必然漏杀），但滚动窗口仍悬空 → 应当成立
    pats = _detect(min_vwap_cushion=-1.8, cushion_roll=0.45)
    assert PATTERN_STRUCTURE_CONFIRM in pats


def test_anomaly_structure_blocked_when_broken():
    pats = _detect(min_vwap_cushion=0.5, cushion_roll=0.45, struct_status=STATUS_BROKEN)
    assert PATTERN_STRUCTURE_CONFIRM not in pats
    assert PATTERN_STRUCTURE_BREAK in pats
    # 失守是负向形态，不能抬高形态强度
    assert pattern_score([PATTERN_STRUCTURE_BREAK]) == 0.0
    assert pattern_score(pats) == pattern_score([p for p in pats if p != PATTERN_STRUCTURE_BREAK])


def test_anomaly_structure_requires_breakout_of_pre1_high():
    pats = _detect(cushion_roll=0.45, price=10.1)   # 未破昨高 10.4
    assert PATTERN_STRUCTURE_CONFIRM not in pats


# ---------------------------------------------------------------------------
# 4. 引擎：保底不得越过风控上限
# ---------------------------------------------------------------------------
def _event(code: str, status: str = STATUS_CONFIRMED, patterns=("结构预判验证",)) -> SignalEvent:
    ev = SignalEvent(
        code=code, ts=100000.0, source="t", price=10.5, vwap=10.0, vwap_10d=10.0,
        pct=5.0, day_high=10.5, day_low=10.0, vol_ratio=1.6, amount_wan=50000.0,
        ma5=10.0, ma10=10.0, ma20=10.0,
    )
    ev.extra = {
        "patterns": list(patterns), "close_pre1": 10.4, "vwap10": 10.0,
        "hi_10d": 11.5, "hi_pre1": 10.4, "is_structure_prejudged": 1.0,
        "close_over_vwap10": 1.0, "vwap_multi_cycle_ready": 1.0,
        "underwater_depth_pct": 0.0, "has_rs": True, "struct_status": status,
    }
    return ev


def test_engine_structure_floor_does_not_bypass_tier_cap():
    eng = FusionEngine(today="")
    dec = eng.evaluate(_event("600001"), None, now=100000.0, tier_cap=1)
    assert dec.tier <= 1, "结构保底不得越过 tier_cap（组合预算/风控降档）"


def test_engine_structure_floor_does_not_bypass_age_decay():
    eng = FusionEngine(today="")
    ev = _event("600002")
    ev.launch_ts = 100000.0 - 3600.0     # 启动已 60 分钟
    dec = eng.evaluate(ev, None, now=100000.0)
    assert dec.tier <= 1, "启动 60 分钟后不得再给 L4（引擎自身的时间约束）"


def test_engine_structure_floor_still_lifts_above_rar_cut():
    eng = FusionEngine(today="")
    dec = eng.evaluate(_event("600003"), None, now=100000.0)
    assert dec.tier == 4, "结构成立且无风控压制时，应保底 L4"


def test_engine_evicted_structure_is_capped():
    eng = FusionEngine(today="")
    broken = eng.evaluate(_event("600004", STATUS_BROKEN, ("结构失守",)), None, now=100000.0)
    evicted = eng.evaluate(_event("600005", STATUS_EVICTED, ("结构失守",)), None, now=100000.0)
    assert broken.tier <= 2
    assert evicted.tier <= 1
    assert evicted.tier <= broken.tier


# ---------------------------------------------------------------------------
# 5. 组合重平衡必须收敛（原实现会死循环）
# ---------------------------------------------------------------------------
def test_rebalance_terminates_with_structure_floor():
    bus = FusionBus(FusionEngine(today=""), max_l4=2, max_total_pct=85.0)
    for code in ("600011", "600012", "600013", "600014"):
        bus.update(_event(code), None)
    portfolio = bus.rebalance()          # 原实现在这里无限循环
    assert portfolio
    assert bus.total_size_pct() <= 85.0
    assert max(d.tier for d in portfolio) <= 4


# ---------------------------------------------------------------------------
# 6. UI 过滤：失守/剔除不应再出现在"只看结构机会"里
# ---------------------------------------------------------------------------
def test_ui_filter_excludes_broken_and_evicted():
    from ats.ui.fusion_ladder_dialog import _row_is_structure_opportunity

    confirmed = {"struct": {"status": STATUS_CONFIRMED, "is_structure_prejudged": 1.0}}
    waiting = {"struct": {"status": STATUS_WAITING, "is_structure_prejudged": 1.0}}
    broken = {"struct": {"status": STATUS_BROKEN, "is_structure_prejudged": 1.0}}
    evicted = {"struct": {"status": STATUS_EVICTED, "is_structure_prejudged": 1.0}}

    assert _row_is_structure_opportunity(confirmed) is True
    assert _row_is_structure_opportunity(waiting) is True
    assert _row_is_structure_opportunity(broken) is False
    assert _row_is_structure_opportunity(evicted) is False


# ---------------------------------------------------------------------------
# 7. 实盘主链路（FusionShadow.observe）的时序演进：确认 → 失守 → 复活
# ---------------------------------------------------------------------------
def test_shadow_live_structure_evolves_with_time():
    from ats.fusion.shadow import FusionShadow

    # 刻意不用 pytest 的 tmp_path fixture：其清理会触发本机安全删除守卫而中断用例。
    # 落盘目录必须隔离，绝不能写生产 logs/fusion_shadow（会污染当日复盘）。
    import tempfile

    sh = FusionShadow(
        config={
            "sample_interval_s": 0.0,
            "session_gate": False,
            "log_dir": tempfile.mkdtemp(prefix="fusion_shadow_tl_"),
        }
    )
    t0 = 1793200000.0

    def feed(ts, price, vwap, cushion_roll):
        snap = {
            "prev_strong_vwap": True, "is_structure_prejudged": 1.0, "close_over_vwap10": 1.0,
            "sector": "航天卫星", "vwap": vwap, "hi_pre1": 51.21, "close_pre1": 50.82,
            "cushion_roll": cushion_roll, "cushion_now": (price / vwap - 1.0) * 100.0,
            "is_box10_ready": True, "vwap10": 51.0, "hi_10d": 52.0, "vwap3": 51.2,
            "wash_quality": 1.0,
        }
        row = {
            "trade": price, "price": price, "percent": (price / 50.82 - 1.0) * 100.0,
            "category": "航天卫星", "open": 51.0,
        }
        return sh.observe(code="600118", row=row, snap=snap, now=ts, force=True)

    r1 = feed(t0 + 60, 51.80, 51.30, 1.20)
    assert r1["struct_status"] == STATUS_CONFIRMED
    assert r1["fusion"]["tier"] == 4

    # 跌破分时均线 → 立刻失守，保底撤销
    r2 = feed(t0 + 180, 50.60, 51.35, -0.35)
    assert r2["struct_status"] == STATUS_BROKEN
    assert r2["fusion"]["tier"] == 0
    assert "跌破分时均线" in r2["struct_reason"]

    # 价格重新站回并再破昨高 → 结构复活，重新拿到保底
    r3 = feed(t0 + 300, 51.60, 51.35, 0.30)
    assert r3["struct_status"] == STATUS_CONFIRMED
    assert r3["fusion"]["tier"] == 4
    assert r3["struct_confirm_n"] >= 2

    # 落盘记录必须带状态，供 UI/复盘直接读取
    assert r3["struct"]["status"] == STATUS_CONFIRMED
    assert "label" in r3["struct"]
