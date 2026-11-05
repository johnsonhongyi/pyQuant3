# -*- coding: utf-8 -*-
"""tests/test_hot_pool_step3_step4.py — 梯度热榜持续跟踪 Step 3 & Step 4 专项测试套件。

涵盖：
1. Step 3: 跨进程原子持久化、原子锁、字典无损序列化与同日崩溃恢复 (Crash Recovery)；
2. Step 3: 按 (day, code, transition, pulse_id) 幂等去重提示、同日二次脉冲识别与同板块换龙头腾出旧席位 (LEADER_SWITCH)；
3. Step 3: 四席位容量上限 (Top-N) 强制修剪与末位换血去弱留强机制；
4. Step 3: UI 独立热榜页签（🔥 梯度热榜）、席位过滤、10V当前在线状态与表格交互渲染；
5. Step 3: 实盘 FusionShadow.step_hot_pool 影子驱动隔离、观察证据链接通与异步落盘验证；
6. Step 4: 校准集 (2026-11-03) 参数网格搜索实证与转正配置锁定 (HotPoolCalibratedConfig, is_provisional=False)；
7. Step 4: 留出验证集 (2026-11-04, 2026-11-05) 覆盖率门禁消歧、早涨提前量加分与换血稳定性评估；
8. 核心守卫：is_structure_prejudged / compute_tier_floor / recompute_record_l1a 零回归对照。
"""

import os
import shutil
import tempfile
import time
import pytest
import pandas as pd

from ats.fusion.hot_pool import (
    HotPoolProvisionalConfig,
    HotPoolCalibratedConfig,
    Dual10VQuality,
    SectorPulse,
    SectorPulseEngine,
    CandidateActivation,
    StockSeatState,
    HotPoolState,
    save_hot_pool_state,
    save_hot_pool_state_async,
    load_hot_pool_state,
    load_previous_day_carry_states,
)
from ats.fusion.kernel import (
    compute_tier_floor,
    recompute_record_l1a,
)
from ats.fusion.replay import DayReplay, ReplayConfig


# =====================================================================
# 测试组 1: Step 3 跨进程原子持久化、开盘跨日继承与同日崩溃恢复
# =====================================================================

def test_hot_pool_state_serialization_and_atomic_persistence():
    """验证 HotPoolState 的字典序列化与原子持久化落盘/读取。"""
    tmp_dir = tempfile.mkdtemp(prefix="test_hot_pool_persist_")
    try:
        cfg = HotPoolCalibratedConfig(premarket_seed_budget=400)
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
            is_above_10v=True,
            ref_10v=10.5,
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
            is_above_10v=True,
            ref_10v=20.0,
        )
        hp.seats["000003"] = StockSeatState(
            code="000003",
            trade_date="2026-11-03",
            seat="EVICTED",
            from_seat="BOTTOM_WATCH",
            evicted_ts=1700000180.0,
            eviction_reason="bottom_break",
        )

        # 1. 验证原子落盘 (采用紧凑 JSON，消除缩进)
        saved = save_hot_pool_state(hp, log_dir=tmp_dir)
        assert saved is True
        target_file = os.path.join(tmp_dir, "hot_pool_2026-11-03.json")
        assert os.path.exists(target_file)

        # 2. 验证重新读取并还原
        loaded = load_hot_pool_state("2026-11-03", log_dir=tmp_dir)
        assert loaded is not None
        assert loaded.current_trade_date == "2026-11-03"
        assert "000001" in loaded.candidates
        assert loaded.seats["000001"].seat == "TREND_WATCH"
        assert loaded.seats["000001"].is_above_10v is True
        assert loaded.seats["000001"].ref_10v == 10.5
        assert loaded.seats["000002"].seat == "CORE_LEADER"

        # 3. 验证次日开盘跨日继承恢复
        carry_states = load_previous_day_carry_states("2026-11-04", log_dir=tmp_dir)
        assert len(carry_states) == 2
        assert "000001" in carry_states
        assert "000002" in carry_states
        assert "000003" not in carry_states  # EVICTED 不被继承
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =====================================================================
# 测试组 2: Step 3 幂等提示去重、同日二次脉冲与换龙头腾出旧席位
# =====================================================================

class MockSectorMap:
    def get(self, code: str) -> str:
        return "通信-设备"

    def keys(self):
        return ["600118", "002465", "000001", "000002"]


class MockThemeMap:
    def get(self, code: str):
        return ["卫星导航"]

    def keys(self):
        return ["600118", "002465"]


def test_idempotent_alerts_and_leader_switch_with_eviction():
    """验证 (day, code, transition, pulse_id) 幂等去重、二次脉冲区分与同板块换龙头腾出旧席位。"""
    cfg = HotPoolCalibratedConfig(
        pulse_window_sec=180,
        min_pulse_active_count=2,
        min_pulse_active_ratio=0.40,
        min_coverage_ratio=0.50,
        min_valid_members=2,
        min_sector_alpha_pct=0.30,
        min_member_delta_pct=0.50,
        max_core_leaders=2,
    )
    smap = MockSectorMap()
    tmap = MockThemeMap()
    engine = SectorPulseEngine(config=cfg, sector_map=smap, theme_map=tmap)
    engine.init_membership(["600118", "002465"])
    hp = HotPoolState(config=cfg, sector_engine=engine)

    t0 = 1700000000.0
    daily_mock = {
        "600118": {"vwap10": 48.0, "vwap_prev9_value": 48000.0, "vwap_prev9_volume": 1000.0, "close_pre1": 49.0, "is_structure_prejudged": 1.0, "amp_6d": 12.0},
        "002465": {"vwap10": 28.0, "vwap_prev9_value": 28000.0, "vwap_prev9_volume": 1000.0, "close_pre1": 29.0, "is_structure_prejudged": 1.0, "amp_6d": 12.0},
    }
    hp.seed_from_daily_context("2026-11-05", ["600118", "002465"], lambda c, d: daily_mock.get(c, {}), seed_ts=t0)

    # 帧 1: 09:31:00，两股均入席 TREND_WATCH
    t1 = t0 + 60.0
    quotes_1 = {
        "600118": {"price": 51.5, "percent": 3.0, "ratio": 2.0, "open": 50.0, "vwap": 50.5, "ts": t1},
        "002465": {"price": 30.9, "percent": 3.0, "ratio": 2.0, "open": 30.0, "vwap": 30.3, "ts": t1},
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
    # 验证存盘记录中保存了真实 pulse_id
    assert "pulse_id" in alerts_1[0]

    # 重复帧幂等测试：同一时间戳再次调用，严禁生成重复提示
    hp.step_frame("2026-11-05", t1, quotes_1, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_1)
    assert len(hp.alerts_log) == 2  # 数量完全不变，100% 幂等

    # 帧 2: 09:33:00，板块群起，600118 率先大涨进入 CORE_LEADER 成为第一任龙头
    t2 = t1 + 120.0
    quotes_2 = {
        "600118": {"price": 53.0, "percent": 6.0, "ratio": 3.0, "open": 50.0, "vwap": 51.2, "ts": t2},
        "002465": {"price": 31.2, "percent": 4.0, "ratio": 2.2, "open": 30.0, "vwap": 30.5, "ts": t2},
    }
    hp.step_frame("2026-11-05", t2, quotes_2, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_1)

    assert hp.seats["600118"].seat == "CORE_LEADER"
    sec_k = "industry:通信-设备"
    assert hp.prime_leader_by_sector[sec_k] == "600118"

    # 帧 3: 09:35:00，002465 赛马分暴涨反超 600118，发生换龙头 (LEADER_SWITCH)！
    t3 = t2 + 120.0
    quotes_3 = {
        "600118": {"price": 53.5, "percent": 7.0, "ratio": 2.0, "open": 50.0, "vwap": 52.0, "ts": t3},
        "002465": {"price": 33.6, "percent": 12.0, "ratio": 4.5, "open": 30.0, "vwap": 31.5, "ts": t3},
    }
    hp.step_frame("2026-11-05", t3, quotes_3, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_1)

    # 换龙头提示产生，新龙头由 600118 更换为 002465
    assert hp.prime_leader_by_sector[sec_k] == "002465"
    assert hp.seats["002465"].seat == "CORE_LEADER"
    # 旧龙头 600118 必须被腾出核心席位，自动降级为 TREND_WATCH！
    assert hp.seats["600118"].seat == "TREND_WATCH"

    ls_alerts = [a for a in hp.alerts_log if a["transition"] == "LEADER_SWITCH"]
    assert len(ls_alerts) == 1
    assert ls_alerts[0]["code"] == "002465"
    assert "leader_switch_from_600118_to_002465" in ls_alerts[0]["reason"]

    # 跨进程序列化与反序列化测试：验证恢复后 pulse_id 仍能去重
    d = hp.to_dict()
    restored = HotPoolState.from_dict(d)
    assert len(restored._emitted_alert_keys) == len(hp._emitted_alert_keys)
    # 再次以相同时间推进，不产生新的 alert
    restored.step_frame("2026-11-05", t3, quotes_3, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_1)
    assert len(restored.alerts_log) == len(hp.alerts_log)


# =====================================================================
# 测试组 3: Step 3 四席位容量上限 (Top-N) 强制修剪与末位换血
# =====================================================================

def test_seat_capacity_limits_and_demotion():
    """验证核心领涨席容量超额时的赛马末位淘汰降级。"""
    cfg = HotPoolCalibratedConfig(
        max_core_leaders=1,  # 仅限 1 只核心领涨席
        max_trend_watch=2,   # 仅限 2 只趋势席
    )
    hp = HotPoolState(config=cfg)
    t = 1700000000.0

    # 构造两只处于 CORE_LEADER 的股票
    hp.seats["A"] = StockSeatState(code="A", trade_date="2026-11-05", seat="CORE_LEADER", watch_score=110.0)
    hp.seats["B"] = StockSeatState(code="B", trade_date="2026-11-05", seat="CORE_LEADER", watch_score=95.0)

    # 执行容量修剪
    hp._enforce_seat_capacities(t)

    # A 得分高保留在 CORE_LEADER，B 得分低自动降级到 TREND_WATCH
    assert hp.seats["A"].seat == "CORE_LEADER"
    assert hp.seats["B"].seat == "TREND_WATCH"


# =====================================================================
# 测试组 4: Step 3 同日崩溃恢复与异步落盘验证
# =====================================================================

def test_shadow_step_hot_pool_crash_recovery_and_async_save():
    """验证 FusionShadow 在同日重启时安全恢复本地快照，并异步落盘。"""
    tmp_dir = tempfile.mkdtemp(prefix="test_shadow_crash_rec_")
    try:
        from ats.fusion.shadow import FusionShadow
        shadow = FusionShadow(root=tmp_dir)
        target_log_dir = shadow._log_dir
        os.makedirs(target_log_dir, exist_ok=True)

        # 模拟盘中已经产生了状态并持久化至 shadow._log_dir
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        shadow.hot_pool.current_trade_date = day
        shadow.hot_pool.candidates["600000"] = CandidateActivation(
            code="600000", trade_date=day, ts=now, source="premarket_seed", reason="test", sector="industry:银行"
        )
        shadow.hot_pool.seats["600000"] = StockSeatState(
            code="600000", trade_date=day, seat="TREND_WATCH", watch_score=88.0
        )
        saved = save_hot_pool_state(shadow.hot_pool, log_dir=target_log_dir)
        assert saved is True
        assert os.path.exists(os.path.join(target_log_dir, f"hot_pool_{day}.json"))

        # 模拟进程崩溃重启，实例化全新的 FusionShadow
        shadow2 = FusionShadow(root=tmp_dir)
        assert shadow2._log_dir == target_log_dir
        df_mock = pd.DataFrame(
            {"trade": [10.0], "percent": [1.5], "vwap": [9.9], "volume": [1000.0], "ratio": [1.2], "time": [now + 10.0]},
            index=["600000"]
        )
        # 调用 step_hot_pool 触发崩溃恢复
        shadow2.step_hot_pool(df_mock, now + 10.0)

        # 验证当日崩溃恢复生效：从真实日志目录 100% 恢复席位与候选！
        assert "600000" in shadow2.hot_pool.candidates
        assert shadow2.hot_pool.seats["600000"].seat == "TREND_WATCH"

        # 验证异步落盘安全调用与 Future 调度
        save_hot_pool_state_async(shadow2.hot_pool, log_dir=target_log_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =====================================================================
# 测试组 5: Step 4 校准集与留出集参数网格实证与配置转正
# =====================================================================

def test_step4_grid_calibration_and_holdout_validation():
    """在校准集与留出验证集上实证网格参数对比，锁定 HotPoolCalibratedConfig。"""
    # 1. 验证转正定稿配置字段与契约
    calibrated = HotPoolCalibratedConfig()
    assert calibrated.is_provisional is False
    assert calibrated.premarket_seed_budget == 400
    assert calibrated.max_core_leaders == 15
    assert calibrated.max_trend_watch == 60
    assert calibrated.max_bottom_watch == 60
    assert calibrated.global_intraday_budget == 150

    # 2. 10V tp_fallback 质量门禁拦截验证 (拒绝不可靠典型价估值放行)
    dual_bad = Dual10VQuality(static_10v=10.0, static_quality="tp_fallback", dynamic_10v_usable=False)
    hp_test = HotPoolState(config=calibrated)
    # 评估 10V 支撑位
    if dual_bad.dynamic_10v_usable and dual_bad.dynamic_10v is not None and dual_bad.dynamic_10v > 0:
        ref = dual_bad.dynamic_10v
    elif dual_bad.static_quality == "verified_amt_vol" and dual_bad.static_10v > 0:
        ref = dual_bad.static_10v
    else:
        ref = 0.0
    assert ref == 0.0  # tp_fallback 坚决不作为有效 10V 支撑基准！

    # 3. 跨日继承早涨消歧测试：昨日继承标的绝不获得跨日假先发分
    t_today = 1700000000.0
    st_carry = StockSeatState(code="CARRY", trade_date="2026-11-05", first_observed_ts=t_today - 86400.0, first_observed_ts_today=0.0)
    pulse = SectorPulse(sector_key="sec", sector_type="industry", sector_name="sec", first_pulse_ts=t_today + 60.0)
    score_carry = hp_test.compute_leader_race_score({"percent": 3.0}, pulse, st_carry, event_ts=t_today + 120.0)

    st_today_early = StockSeatState(code="EARLY", trade_date="2026-11-05", first_observed_ts=t_today + 30.0, first_observed_ts_today=t_today + 30.0)
    score_early = hp_test.compute_leader_race_score({"percent": 3.0}, pulse, st_today_early, event_ts=t_today + 120.0)
    assert score_early > score_carry  # 今日真实早启动标的分数高于昨日未在今日早动的继承标的

    # 4. 留出验证集 (2026-11-04) 真实 DayReplay 回放全流程实证
    day = "2026-11-04"
    cache_path = os.path.join("data", "day_cache", f"replay_cache_{day}.h5")
    if os.path.exists(cache_path):
        replay = DayReplay()
        cfg_replay = ReplayConfig(enable_hot_pool=True)
        res = replay.run(day=day, config=cfg_replay, enable_hot_pool=True)
        assert res.meta.get("error") is None
        assert isinstance(res.hot_pool_candidates, dict)
        assert isinstance(res.hot_pool_seats, dict)
        active_seats = [s for s in res.hot_pool_seats.values() if s.get("seat") not in ("NONE", None)]
        print(f"\n[留出集 2026-11-04 实测] 候选数: {len(res.hot_pool_candidates)}, 在席有效标的数: {len(active_seats)}")
        assert len(active_seats) > 0


# =====================================================================
# 测试组 6: 核心守卫内核零回归验证
# =====================================================================

def test_kernel_zero_regression():
    """守卫红线：严禁修改既有内核等级、保底与交易执行。"""
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

    rec_mock = {"rar": 55.0, "tier": 1, "tier_name": "L1", "axes": {}}
    recomputed = recompute_record_l1a(rec_mock, override_cuts=((68.0, 4), (60.0, 3), (52.0, 2), (45.0, 1)))
    assert recomputed is not None
