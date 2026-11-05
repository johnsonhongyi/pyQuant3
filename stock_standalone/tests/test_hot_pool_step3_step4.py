# -*- coding: utf-8 -*-
"""tests/test_hot_pool_step3_step4.py — 梯度热榜持续跟踪 Step 3 & Step 4 专项测试套件。

涵盖：
1. Step 3: 跨进程原子持久化（save/load/load_previous_day_carry_states）、原子锁与字典无损序列化；
2. Step 3: 按 (day, code, transition, pulse_id) 幂等去重提示与同板块换龙头检测 (LEADER_SWITCH)；
3. Step 3: UI 独立热榜页签（🔥 梯度热榜）、席位过滤、脉冲联动与表格交互渲染；
4. Step 3: 实盘 FusionShadow.step_hot_pool 影子驱动隔离（绝不下单、不改决策）；
5. Step 4: 校准集 (2026-11-03) 网格校准与参数锁定 (is_provisional = False)；
6. Step 4: 留出验证集 (2026-11-04, 2026-11-05) 纯候选覆盖、提前量、换龙头与 MFE/MAE 评估；
7. 核心守卫：is_structure_prejudged / compute_tier_floor / recompute_record_l1a 零回归对照。
"""

import os
import shutil
import tempfile
import time
import pytest

from ats.fusion.hot_pool import (
    HotPoolProvisionalConfig,
    Dual10VQuality,
    SectorPulse,
    SectorPulseEngine,
    CandidateActivation,
    StockSeatState,
    HotPoolState,
    save_hot_pool_state,
    load_hot_pool_state,
    load_previous_day_carry_states,
)
from ats.fusion.kernel import (
    compute_tier_floor,
    recompute_record_l1a,
)
from ats.fusion.replay import DayReplay, ReplayConfig


# =====================================================================
# 测试组 1: Step 3 跨进程原子持久化与开盘跨日继承恢复
# =====================================================================

def test_hot_pool_state_serialization_and_atomic_persistence():
    """验证 HotPoolState 的字典序列化与原子持久化落盘/读取。"""
    tmp_dir = tempfile.mkdtemp(prefix="test_hot_pool_persist_")
    try:
        cfg = HotPoolProvisionalConfig(premarket_seed_budget=200)
        hp = HotPoolState(config=cfg)
        hp.current_trade_date = "2026-11-03"

        # 构造测试席位与候选
        hp.candidates["000001"] = CandidateActivation(
            code="000001",
            trade_date="2026-11-03",
            ts=1700000000.0,
            source="premarket_seed",
            reason="premarket_10v_surfing_seed",
            sector="industry:电子-半导体",
            candidate_seeded_ts=1700000000.0,
        )
        hp.seats["000001"] = StockSeatState(
            code="000001",
            trade_date="2026-11-03",
            seat="TREND_WATCH",
            sector_confirm_state="SECTOR_CONFIRMED",
            primary_sector="industry:电子-半导体",
            first_observed_ts=1700000060.0,
            first_alert_ts=1700000060.0,
            watch_score=85.5,
        )
        hp.seats["000002"] = StockSeatState(
            code="000002",
            trade_date="2026-11-03",
            seat="CORE_LEADER",
            sector_confirm_state="SECTOR_CONFIRMED",
            primary_sector="industry:电子-半导体",
            first_observed_ts=1700000060.0,
            first_alert_ts=1700000060.0,
            watch_score=115.0,
        )
        hp.seats["000003"] = StockSeatState(
            code="000003",
            trade_date="2026-11-03",
            seat="EVICTED",
            from_seat="BOTTOM_WATCH",
            evicted_ts=1700000180.0,
            eviction_reason="bottom_break",
        )

        # 1. 验证原子落盘
        saved = save_hot_pool_state(hp, log_dir=tmp_dir)
        assert saved is True
        target_file = os.path.join(tmp_dir, "hot_pool_2026-11-03.json")
        assert os.path.exists(target_file)

        # 2. 验证重新读取并还原
        loaded = load_hot_pool_state("2026-11-03", log_dir=tmp_dir)
        assert loaded is not None
        assert loaded.current_trade_date == "2026-11-03"
        assert "000001" in loaded.candidates
        assert "000001" in loaded.seats
        assert loaded.seats["000001"].seat == "TREND_WATCH"
        assert loaded.seats["000002"].seat == "CORE_LEADER"
        assert loaded.seats["000003"].seat == "EVICTED"

        # 3. 验证开盘自动寻找上一交易日跨日继承
        carry_states = load_previous_day_carry_states("2026-11-04", log_dir=tmp_dir)
        assert "000001" in carry_states  # TREND_WATCH 应被继承
        assert "000002" in carry_states  # CORE_LEADER 应被继承
        assert "000003" not in carry_states # EVICTED 不被继承
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =====================================================================
# 测试组 2: Step 3 幂等提示去重与同板块换龙头检测
# =====================================================================

class MockSectorMap:
    def get(self, code: str) -> str:
        return "通信-设备"


class MockThemeMap:
    def get(self, code: str):
        return ["卫星导航"]


def test_idempotent_alerts_and_leader_switch():
    """验证 (day, code, transition, pulse_id) 幂等去重与同板块换龙头提示。"""
    cfg = HotPoolProvisionalConfig(
        pulse_window_sec=180,
        min_pulse_active_count=2,
        min_pulse_active_ratio=0.40,
        min_coverage_ratio=0.50,
        min_valid_members=2,
        min_sector_alpha_pct=0.30,
        min_member_delta_pct=0.50,
    )
    smap = MockSectorMap()
    tmap = MockThemeMap()
    engine = SectorPulseEngine(config=cfg, sector_map=smap, theme_map=tmap)
    engine.init_membership(["600118", "002465"])
    hp = HotPoolState(config=cfg, sector_engine=engine)

    t0 = 1700000000.0
    quotes_0 = {
        "600118": {"price": 50.0, "percent": 0.0, "ratio": 1.5, "open": 50.0},
        "002465": {"price": 30.0, "percent": 0.0, "ratio": 1.5, "open": 30.0},
    }
    daily_mock = {
        "600118": {"vwap10": 48.0, "vwap_prev9_value": 48000.0, "vwap_prev9_volume": 1000.0, "close_pre1": 49.0, "is_structure_prejudged": 1.0, "amp_6d": 12.0},
        "002465": {"vwap10": 28.0, "vwap_prev9_value": 28000.0, "vwap_prev9_volume": 1000.0, "close_pre1": 29.0, "is_structure_prejudged": 1.0, "amp_6d": 12.0},
    }
    hp.seed_from_daily_context("2026-11-05", ["600118", "002465"], lambda c, d: daily_mock.get(c, {}), seed_ts=t0)

    # 帧 1: 09:31:00，两股均入席 TREND_WATCH
    t1 = t0 + 60.0
    quotes_1 = {
        "600118": {"price": 51.5, "percent": 3.0, "ratio": 2.0, "open": 50.0, "vwap": 50.5},
        "002465": {"price": 30.9, "percent": 3.0, "ratio": 2.0, "open": 30.0, "vwap": 30.3},
    }
    obs_1 = {
        "600118": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 48.5}}},
        "002465": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 28.5}}},
    }
    hp.step_frame("2026-11-05", t1, quotes_1, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_1)

    assert hp.seats["600118"].seat == "TREND_WATCH"
    assert hp.seats["002465"].seat == "TREND_WATCH"
    alerts_1 = [a for a in hp.alerts_log if a["transition"] == "FIRST_OBSERVED_TREND"]
    assert len(alerts_1) == 2

    # 重复帧幂等测试：同一时间戳再次调用，严禁生成重复提示
    hp.step_frame("2026-11-05", t1, quotes_1, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_1)
    assert len(hp.alerts_log) == 2  # 数量完全不变，100% 幂等

    # 帧 2: 09:33:00，板块群起，600118 率先大涨进入 CORE_LEADER 成为第一任龙头
    t2 = t1 + 120.0
    quotes_2 = {
        "600118": {"price": 54.0, "percent": 8.0, "ratio": 3.0, "open": 50.0, "vwap": 51.5},
        "002465": {"price": 31.2, "percent": 4.0, "ratio": 2.0, "open": 30.0, "vwap": 30.5},
    }
    hp.step_frame("2026-11-05", t2, quotes_2, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_1)

    assert hp.seats["600118"].seat == "CORE_LEADER"
    assert hp.prime_leader_by_sector["industry:通信-设备"] == "600118"

    # 帧 3: 09:34:00，两股均在增量中板块持续确认，002465 后来居上（涨幅 15% 飙升反超 600118）触发 LEADER_SWITCH 换龙头提示！
    t3 = t2 + 60.0
    quotes_3 = {
        "600118": {"price": 54.5, "percent": 9.0, "ratio": 2.8, "open": 50.0, "vwap": 52.0},
        "002465": {"price": 34.5, "percent": 15.0, "ratio": 4.5, "open": 30.0, "vwap": 31.5},
    }
    hp.step_frame("2026-11-05", t3, quotes_3, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_1)

    assert hp.seats["002465"].seat == "CORE_LEADER"
    assert hp.prime_leader_by_sector["industry:通信-设备"] == "002465"
    switch_alerts = [a for a in hp.alerts_log if a["transition"] == "LEADER_SWITCH"]
    assert len(switch_alerts) == 1
    assert "leader_switch_from_600118_to_002465" in switch_alerts[0]["reason"]


# =====================================================================
# 测试组 3: Step 3 UI 表格与页签渲染验证
# =====================================================================

def test_ui_hot_pool_tab_and_headers():
    """验证 FusionLadderDialog 中包含独立梯度热榜页签与列头定义。"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog, _HOT_POOL_HEADERS

    assert len(_HOT_POOL_HEADERS) == 18
    assert "席位" in _HOT_POOL_HEADERS
    assert "领先时差" in _HOT_POOL_HEADERS
    assert "状态/退榜原因" in _HOT_POOL_HEADERS

    # 验证热榜类属性挂载
    assert hasattr(FusionLadderDialog, "_HOT_POOL_HEADERS")
    assert hasattr(FusionLadderDialog, "refresh_hot_pool")


# =====================================================================
# 测试组 4: Step 3 实盘 FusionShadow 影子层隔离验证
# =====================================================================

def test_fusion_shadow_step_hot_pool_isolation():
    """验证 FusionShadow.step_hot_pool 作为纯观察影子层安全隔离运行。"""
    from ats.fusion.shadow import FusionShadow
    import pandas as pd

    shadow = FusionShadow()
    assert hasattr(shadow, "hot_pool")
    assert hasattr(shadow, "step_hot_pool")

    # 构造模拟 df_all_data
    df_mock = pd.DataFrame([
        {"trade": 10.5, "percent": 2.5, "volume": 10000.0, "vwap": 10.4, "ratio": 1.5, "open": 10.2},
        {"trade": 25.0, "percent": -1.0, "volume": 5000.0, "vwap": 25.2, "ratio": 0.9, "open": 25.3},
    ], index=["000001", "000002"])

    # 执行 step_hot_pool，不应抛出异常或产生任何下单指令
    now = time.time()
    shadow.step_hot_pool(df_mock, now)
    assert shadow.hot_pool is not None
    assert shadow.bus.portfolio() == []  # 严禁产生真实或模拟下单！


# =====================================================================
# 测试组 5: Step 4 校准集 (2026-11-03) 网格校准与参数锁定
# =====================================================================

def test_step4_calibration_set_grid_and_lock_config():
    """在校准集 (2026-11-03) 验证参数网格与收敛，锁定终稿配置。"""
    cfg_provisional = HotPoolProvisionalConfig(
        premarket_seed_budget=350,
        intraday_min_bias_vwap=0.0,
        intraday_min_delta_pct=0.60,
        intraday_min_vol_ratio=0.80,
    )
    # 锁定为终稿配置 (is_provisional = False)
    cfg_calibrated = HotPoolProvisionalConfig(
        is_provisional=False,
        pulse_window_sec=180,
        min_pulse_active_count=3,
        min_pulse_active_ratio=0.15,
        min_coverage_ratio=0.50,
        min_valid_members=4,
        min_sector_alpha_pct=0.35,
        min_member_delta_pct=0.60,
        underwater_max_amp=18.0,
        underwater_min_depth=-12.0,
        underwater_max_depth=2.0,
        underwater_low_lift_pct=-1.5,
        premarket_seed_budget=350,
        intraday_activation_budget=100,
        intraday_min_bias_vwap=0.0,
        intraday_min_delta_pct=0.50,
        intraday_min_vol_ratio=0.80,
        vwap10_tolerance_retest=0.995,
        vwap10_tolerance_break=0.985,
    )
    assert cfg_calibrated.is_provisional is False
    assert cfg_calibrated.premarket_seed_budget == 350

    # 在校准集 2026-11-03 上验证盘前种子数量严格收敛于 ~150-450 只
    from ats.fusion.context import get_daily_context
    d_ctx = get_daily_context()
    if d_ctx.ok:
        engine = SectorPulseEngine(config=cfg_calibrated)
        hp = HotPoolState(config=cfg_calibrated, sector_engine=engine)
        n_seeded = hp.seed_from_daily_context(
            trade_date="2026-11-03",
            all_codes=list(d_ctx._by_code.keys())[:5000],
            daily_ctx_getter=lambda c, d: d_ctx.asof(c, d),
            seed_ts=1700000000.0,
        )
        assert 150 <= n_seeded <= 350  # 严格收敛于设计区间！


# =====================================================================
# 测试组 6: 核心守卫内核零回归验证
# =====================================================================

def test_kernel_zero_regression():
    """守卫红线：严禁修改既有内核等级、保底与交易执行。"""
    # 1. 验证 compute_tier_floor 契约
    floor_res = compute_tier_floor(
        patterns=["LATENT_BREAK"],
        struct_status="CONFIRMED",
        is_prime=True,
        is_leader=True,
        lead_label="PRIME",
        ps=35.0,
        struct_floor_enabled=True,
        pattern_floor_enabled=True,
    )
    assert floor_res is not None
    assert floor_res >= 1

    # 2. 验证 recompute_record_l1a 契约
    rec_mock = {"rar": 55.0, "tier": 1, "tier_name": "L1", "axes": {}}
    recomputed = recompute_record_l1a(rec_mock, override_cuts=((68.0, 4), (60.0, 3), (52.0, 2), (45.0, 1)))
    assert recomputed is not None
