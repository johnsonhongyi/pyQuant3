# -*- coding: utf-8 -*-
"""tests/test_hot_pool_step1_step2.py — 梯度热榜持续跟踪 Step 1 & Step 2 专项测试套件。

涵盖：
1. Step 1: 试验参数预登记、Dual10VQuality 与双 10V 质量核验硬门禁、SBC VWAP 核源记录；
2. Step 1: 行业与多概念双轨 SectorPulseEngine、最低覆盖率门禁与状态滞回；
3. Step 2: 三路候选激活契约（盘前种子、盘中板块脉冲、跨日继承）；
4. Step 2: 单写者 HotPoolState 严格按 (trade_date, event_ts, code) 推进；
5. Step 2: 四席位（BOTTOM_WATCH, TREND_WATCH, CORE_LEADER, EVICTED）准入、晋级、降级、淘汰与 rearm；
6. Step 2: 三类时间戳严格分离（candidate_seeded/activated_ts, first_observed_ts, first_alert_ts）；
7. Step 2: DayReplay 纯候选覆盖实证验证（关闭人工焦点、关闭继承、关闭历史注入）。
"""

import time
import pytest
import numpy as np

from ats.fusion.hot_pool import (
    HotPoolProvisionalConfig,
    Dual10VQuality,
    evaluate_10v_quality,
    compare_sbc_vwap_source,
    SectorPulse,
    SectorPulseEngine,
    CandidateActivation,
    StockSeatState,
    HotPoolState,
)
from ats.fusion.replay import DayReplay, ReplayConfig


# =====================================================================
# 测试组 1: Step 1 预登记试验参数与 Dual10VQuality 硬门禁
# =====================================================================

def test_provisional_config_defaults():
    """验证预登记试验参数集默认值与 provisional 标记。"""
    cfg = HotPoolProvisionalConfig()
    assert cfg.is_provisional is True
    assert cfg.pulse_window_sec == 180
    assert cfg.min_pulse_active_count == 3
    assert cfg.min_pulse_active_ratio == 0.15
    assert cfg.min_coverage_ratio == 0.50
    assert cfg.min_valid_members == 4
    assert cfg.min_sector_alpha_pct == 0.35
    assert cfg.min_member_delta_pct == 0.60
    assert cfg.underwater_min_depth == -12.0
    assert cfg.underwater_max_depth == 2.0


def test_dual_10v_static_and_dynamic_quality_gates():
    """验证静态与动态 10V 的质量评估及硬门禁。"""
    # 1. 静态 10V: 包含前 9 日完整量价 -> verified_amt_vol
    daily_good = {
        "vwap10": 10.50,
        "vwap_prev9_value": 90000.0,
        "vwap_prev9_volume": 9000.0,
        "close_pre1": 10.60,
    }
    q1 = evaluate_10v_quality(daily_good, None, "2026-11-05")
    assert q1.static_10v == 10.50
    assert q1.static_quality == "verified_amt_vol"
    assert q1.prev9_keys_present is True
    assert q1.dynamic_10v_usable is False
    assert "missing_obs_evidence" in q1.unusable_reason

    # 2. 静态 10V: 缺失前 9 日键但有 vwap10 -> tp_fallback
    daily_tp = {
        "vwap10": 10.50,
        "close_pre1": 10.60,
    }
    q2 = evaluate_10v_quality(daily_tp, None, "2026-11-05")
    assert q2.static_quality == "tp_fallback"
    assert q2.prev9_keys_present is False

    # 3. 动态 10V: 当缺少前 9 日量价键时，严禁使用 dynamic_10v
    obs_ev_same_day = {
        "freshness": "same_day",
        "vwap": {
            "timing": {"freshness": "same_day"},
            "including_current": {"10": 10.55},
        },
    }
    q3 = evaluate_10v_quality(daily_tp, obs_ev_same_day, "2026-11-05", today_vwap=10.60, today_volume=1000.0)
    assert q3.dynamic_10v_usable is False
    assert "missing_prev9_value_volume_keys" in q3.unusable_reason

    # 4. 动态 10V: 非 same_day 新鲜特征 -> 严禁使用
    obs_ev_stale = {
        "freshness": "stale",
        "vwap": {
            "timing": {"freshness": "same_day"},
            "including_current": {"10": 10.55},
        },
    }
    q4 = evaluate_10v_quality(daily_good, obs_ev_stale, "2026-11-05", today_vwap=10.60, today_volume=1000.0)
    assert q4.dynamic_10v_usable is False
    assert "obs_freshness_not_same_day" in q4.unusable_reason

    # 5. 动态 10V: 全要素齐备且新鲜 -> dynamic_10v_usable 为 True
    q5 = evaluate_10v_quality(daily_good, obs_ev_same_day, "2026-11-05", today_vwap=11.00, today_volume=1000.0)
    assert q5.dynamic_10v_usable is True
    # 验算: (90000 + 11.0 * 1000) / (9000 + 1000) = 101000 / 10000 = 10.10
    assert q5.dynamic_10v == pytest.approx(10.10, abs=1e-3)


def test_compare_sbc_vwap_source():
    """验证 SBC 分时金色均价线与动态 10V 的核源记录。"""
    rec = compare_sbc_vwap_source(
        period_mode="10d",
        df_view_vwap=10.52,
        dynamic_10v=10.50,
        source="sbc_multi_day_dialog",
        ts=1700000000.0,
    )
    assert rec["period_mode"] == "10d"
    assert rec["diff"] == 0.02
    assert rec["is_same_concept"] is True


# =====================================================================
# 测试组 2: Step 1 行业与多概念双轨板块脉冲与最低覆盖率硬门禁
# =====================================================================

class DummySectorMap:
    def get(self, code: str) -> str:
        if code in ("000001", "000002", "000003", "000004", "000005"):
            return "电子-半导体"
        return "未分类"


class DummyThemeMap:
    def get(self, code: str):
        if code in ("000001", "000002", "000003"):
            return ["人形机器人", "融资融券"] # "融资融券" 是宽泛概念应被过滤
        return []


def test_sector_pulse_dual_track_and_coverage_gate():
    """验证双轨板块脉冲、覆盖率硬门禁与状态滞回。"""
    smap = DummySectorMap()
    tmap = DummyThemeMap()
    cfg = HotPoolProvisionalConfig(
        pulse_window_sec=180,
        min_pulse_active_count=3,
        min_pulse_active_ratio=0.50,
        min_coverage_ratio=0.50,
        min_valid_members=3,
        min_sector_alpha_pct=0.30,
        min_member_delta_pct=0.50,
    )
    engine = SectorPulseEngine(config=cfg, sector_map=smap, theme_map=tmap)
    # 显式注册该板块的全部 5 个成员建立全市场分母 (total_member_count = 5)
    engine.init_membership(["000001", "000002", "000003", "000004", "000005"])

    # 场景 1: 行情覆盖率不足门禁 (total=5, 仅2个有效报价 -> coverage = 0.40 < 0.50)
    # 即使 2 只股票全部大涨 delta=1.5%，也严禁判定为群起！
    t0 = 1700000000.0
    quotes_low_coverage = {
        "000001": {"price": 10.0, "percent": 0.0, "ratio": 1.5, "ts": t0},
        "000002": {"price": 10.0, "percent": 0.0, "ratio": 1.5, "ts": t0},
    }
    engine.step_frame("2026-11-05", t0, quotes_low_coverage)

    t1 = t0 + 60.0
    quotes_low_cov_pulse = {
        "000001": {"price": 11.5, "percent": 1.5, "ratio": 2.0, "ts": t1},
        "000002": {"price": 11.5, "percent": 1.5, "ratio": 2.0, "ts": t1},
    }
    pulses1 = engine.step_frame("2026-11-05", t1, quotes_low_cov_pulse, market_pct=0.0)
    p_semi = pulses1.get("industry:电子-半导体")
    assert p_semi is not None
    assert p_semi.coverage_ratio == 0.40  # 2/5
    assert p_semi.is_confirmed is False   # 覆盖率不足，严禁判定为群起！
    assert p_semi.state == "IDLE"

    # 场景 2: 覆盖率达标 (4/5 = 80% >= 50%)，且 3 只增量脉冲达标 -> NEW_IMPULSE
    quotes_full = {
        "000001": {"price": 10.0, "percent": 0.0, "ratio": 1.5, "ts": t0},
        "000002": {"price": 10.0, "percent": 0.0, "ratio": 1.5, "ts": t0},
        "000003": {"price": 10.0, "percent": 0.0, "ratio": 1.5, "ts": t0},
        "000004": {"price": 10.0, "percent": 0.0, "ratio": 1.0, "ts": t0},
    }
    engine._price_windows.clear()
    engine.step_frame("2026-11-05", t0, quotes_full)

    quotes_surge = {
        "000001": {"price": 10.8, "percent": 0.8, "ratio": 2.0, "ts": t1},
        "000002": {"price": 10.7, "percent": 0.7, "ratio": 2.0, "ts": t1},
        "000003": {"price": 10.6, "percent": 0.6, "ratio": 2.0, "ts": t1},
        "000004": {"price": 10.1, "percent": 0.1, "ratio": 1.0, "ts": t1},
    }
    pulses2 = engine.step_frame("2026-11-05", t1, quotes_surge, market_pct=0.0)
    p_semi2 = pulses2.get("industry:电子-半导体")
    assert p_semi2.coverage_ratio == 0.80
    assert p_semi2.active_count == 3
    assert p_semi2.is_confirmed is True
    assert p_semi2.state == "NEW_IMPULSE"
    assert p_semi2.first_pulse_ts == t1

    # 场景 3: 多概念双轨验证 (theme:人形机器人) 独立生效，且过滤宽泛概念
    p_theme = pulses2.get("theme:人形机器人")
    assert p_theme is not None
    assert p_theme.is_confirmed is True
    assert pulses2.get("theme:融资融券") is None  # 宽泛概念已被彻底排除

    # 场景 4: 状态滞回与再激活 (DECAY_WATCH -> REACTIVATED)
    # 时间推移 200 秒（超过 180 秒短窗，短窗增量停滞为 0.0% < 0.5%）-> 进入 DECAY_WATCH
    t2 = t1 + 200.0
    quotes_flat = {
        "000001": {"price": 10.8, "percent": 0.8, "ratio": 1.0, "ts": t2},
        "000002": {"price": 10.7, "percent": 0.7, "ratio": 1.0, "ts": t2},
        "000003": {"price": 10.6, "percent": 0.6, "ratio": 1.0, "ts": t2},
        "000004": {"price": 10.1, "percent": 0.1, "ratio": 1.0, "ts": t2},
    }
    pulses3 = engine.step_frame("2026-11-05", t2, quotes_flat, market_pct=0.0)
    assert pulses3["industry:电子-半导体"].state == "DECAY_WATCH"

    # 二次群起 -> REACTIVATED 并累加 re_pulse_count，保留 first_pulse_ts
    t3 = t2 + 60.0
    quotes_re_pulse = {
        "000001": {"price": 12.0, "percent": 2.0, "ratio": 2.5, "ts": t3},
        "000002": {"price": 11.9, "percent": 1.9, "ratio": 2.5, "ts": t3},
        "000003": {"price": 11.8, "percent": 1.8, "ratio": 2.5, "ts": t3},
        "000004": {"price": 10.2, "percent": 0.2, "ratio": 1.0, "ts": t3},
    }
    pulses4 = engine.step_frame("2026-11-05", t3, quotes_re_pulse, market_pct=0.0)
    p_semi4 = pulses4["industry:电子-半导体"]
    assert p_semi4.state == "REACTIVATED"
    assert p_semi4.re_pulse_count == 1
    assert p_semi4.first_pulse_ts == t1  # 绝不抹去首发时间！


# =====================================================================
# 测试组 3: Step 2 三路候选激活与单写者 HotPoolState 席位状态机
# =====================================================================

def test_hot_pool_three_path_candidate_activation():
    """验证三路候选输入：盘前种子、盘中板块激活与跨日继承。"""
    cfg = HotPoolProvisionalConfig()
    engine = SectorPulseEngine(config=cfg, sector_map=DummySectorMap(), theme_map=DummyThemeMap())
    hp = HotPoolState(config=cfg, sector_engine=engine)

    # 路径 1: 盘前日线种子 (测试 10V 演进、首次站上与水下基座)
    daily_mock = {
        "000001": {"vwap10": 10.0, "close_pre1": 10.5, "lo_pre1": 9.5, "lo_10d": 9.4, "amp_6d": 10.0, "is_structure_prejudged": 1.0}, # 上方演进
        "000002": {"vwap10": 10.0, "close_pre1": 9.9, "lo_pre1": 9.5, "lo_10d": 9.4, "amp_6d": 12.0, "vwap10_touch_count": 2, "prev_close_pos": 0.6},  # 首次站上/回测
        "000003": {"vwap10": 10.0, "close_pre1": 9.2, "lo_pre1": 9.1, "lo_10d": 9.0, "amp_6d": 14.0, "prev_close_pos": 0.6},  # 水下基座 (-8%)
        "000004": {"vwap10": 10.0, "close_pre1": 7.0, "lo_pre1": 6.8, "lo_10d": 6.8, "amp_6d": 30.0},  # 过深弱势 (< -12%, 排除)
    }
    n_seeded = hp.seed_from_daily_context(
        "2026-11-05",
        ["000001", "000002", "000003", "000004"],
        lambda c, d: daily_mock.get(c, {}),
        seed_ts=1700000000.0,
    )
    assert n_seeded == 3
    assert "000001" in hp.candidates
    assert hp.candidates["000001"].reason == "premarket_10v_surfing_seed"
    assert "000002" in hp.candidates
    assert hp.candidates["000002"].reason == "premarket_10v_reclaim_seed"
    assert "000003" in hp.candidates
    assert hp.candidates["000003"].reason == "premarket_underwater_base_seed"
    assert "000004" not in hp.candidates

    # 盘前种子时间戳不等于早发现
    assert hp.candidates["000001"].candidate_seeded_ts == 1700000000.0

    # 路径 3: 跨日继承
    old_seats = {
        "000005": StockSeatState(
            code="000005",
            trade_date="2026-11-04",
            seat="TREND_WATCH",
            primary_sector="industry:电子-半导体",
            first_observed_ts=1699990000.0,
        )
    }
    n_carry = hp.carry_from_previous_day("2026-11-05", old_seats, carry_ts=1700000001.0)
    assert n_carry == 1
    assert "000005" in hp.candidates
    assert hp.candidates["000005"].source == "cross_day_carry"
    assert hp.seats["000005"].seat == "TREND_WATCH"


def test_hot_pool_four_seats_transitions_and_time_stamps():
    """验证四席位（BOTTOM_WATCH, TREND_WATCH, CORE_LEADER, EVICTED）流转与三类时间戳分离。"""
    smap = DummySectorMap()
    tmap = DummyThemeMap()
    cfg = HotPoolProvisionalConfig()
    engine = SectorPulseEngine(config=cfg, sector_map=smap, theme_map=tmap)
    hp = HotPoolState(config=cfg, sector_engine=engine)

    daily_mock = {
        "000001": {"vwap10": 10.0, "vwap_prev9_value": 90000.0, "vwap_prev9_volume": 9000.0, "close_pre1": 10.1, "is_structure_prejudged": 1.0, "amp_6d": 10.0},
        "000003": {"vwap10": 10.0, "vwap_prev9_value": 90000.0, "vwap_prev9_volume": 9000.0, "close_pre1": 9.2, "lo_pre1": 9.1, "lo_10d": 9.0, "amp_6d": 12.0, "prev_close_pos": 0.6},
    }
    hp.seed_from_daily_context("2026-11-05", ["000001", "000003"], lambda c, d: daily_mock.get(c, {}), seed_ts=1700000000.0)

    # 帧 1: 09:31:00 (t=1700000060)
    # 000003 水下基座标的，出现分时 VWAP 承接与放量 -> 准入 BOTTOM_WATCH
    # 000001 站上 10V 与 VWAP -> 准入 TREND_WATCH
    t1 = 1700000060.0
    quotes_t1 = {
        "000001": {"price": 10.2, "percent": 1.5, "volume": 1000.0, "vwap": 10.15, "ratio": 1.2, "open": 10.0, "ts": t1},
        "000003": {"price": 9.3, "percent": 1.5, "volume": 800.0, "vwap": 9.25, "ratio": 1.5, "open": 9.1, "ts": t1},
        "000002": {"price": 10.0, "percent": 0.0, "volume": 500.0, "vwap": 10.0, "ratio": 1.0, "open": 10.0, "ts": t1},
        "000004": {"price": 10.0, "percent": 0.0, "volume": 500.0, "vwap": 10.0, "ratio": 1.0, "open": 10.0, "ts": t1},
        "000005": {"price": 10.0, "percent": 0.0, "volume": 500.0, "vwap": 10.0, "ratio": 1.0, "open": 10.0, "ts": t1},
    }
    obs_ev_t1 = {
        "000001": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 10.02}}},
        "000003": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 9.92}}},
    }
    hp.step_frame("2026-11-05", t1, quotes_t1, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_ev_t1)

    st3 = hp.seats.get("000003")
    assert st3 is not None
    assert st3.seat == "BOTTOM_WATCH"
    assert st3.candidate_seeded_ts == 1700000000.0
    assert st3.first_observed_ts == t1  # 盘中首次满足准入
    assert st3.first_alert_ts == t1
    assert st3.sector_confirm_state == "PENDING_SECTOR"  # 板块尚未确认

    st1 = hp.seats.get("000001")
    assert st1 is not None
    assert st1.seat == "TREND_WATCH"
    assert st1.first_observed_ts == t1

    # 帧 2: 09:34:00 (t=1700000240)
    # 板块群起确认，000001 领涨扩张 -> 晋级 CORE_LEADER
    # 000003 强势收复 10V -> 晋级 TREND_WATCH
    t2 = 1700000240.0
    quotes_t2 = {
        "000001": {"price": 10.9, "percent": 7.9, "volume": 5000.0, "vwap": 10.40, "ratio": 2.5, "ts": t2},
        "000003": {"price": 10.1, "percent": 9.8, "volume": 4000.0, "vwap": 9.60, "ratio": 2.2, "ts": t2},
        "000002": {"price": 10.8, "percent": 8.0, "volume": 3000.0, "vwap": 10.3, "ratio": 2.0, "ts": t2},
        "000004": {"price": 10.5, "percent": 5.0, "volume": 2000.0, "vwap": 10.2, "ratio": 1.8, "ts": t2},
        "000005": {"price": 10.0, "percent": 0.0, "volume": 500.0, "vwap": 10.0, "ratio": 1.0, "ts": t2},
    }
    obs_ev_t2 = {
        "000001": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 10.08}}},
        "000003": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 10.01}}},
    }
    hp.step_frame("2026-11-05", t2, quotes_t2, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_ev_t2)

    assert st1.seat == "CORE_LEADER"
    assert st1.sector_confirm_state == "SECTOR_CONFIRMED"
    assert st1.promoted_ts == t2

    assert st3.seat == "TREND_WATCH"
    assert st3.sector_confirm_state == "SECTOR_CONFIRMED"
    assert st3.promoted_ts == t2

    # 帧 3: 09:37:00 (t=1700000420)
    # 000001 出现高位回撤 -> 退回 TREND_WATCH
    # 000003 大幅破位失守 10V -> 淘汰进入 EVICTED
    t3 = 1700000420.0
    quotes_t3 = {
        "000001": {"price": 10.4, "percent": 3.0, "volume": 5500.0, "vwap": 10.45, "ratio": 1.8, "ts": t3}, # 回撤
        "000003": {"price": 9.7, "percent": 5.4, "volume": 4200.0, "vwap": 9.80, "ratio": 1.2, "ts": t3},   # 破位失守 10V(10.01)
        "000002": {"price": 10.8, "percent": 8.0, "volume": 3000.0, "vwap": 10.3, "ratio": 2.0, "ts": t3},
        "000004": {"price": 10.5, "percent": 5.0, "volume": 2000.0, "vwap": 10.2, "ratio": 1.8, "ts": t3},
        "000005": {"price": 10.0, "percent": 0.0, "volume": 500.0, "vwap": 10.0, "ratio": 1.0, "ts": t3},
    }
    obs_ev_t3 = {
        "000001": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 10.08}}},
        "000003": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 10.01}}},
    }
    hp.step_frame("2026-11-05", t3, quotes_t3, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_ev_t3)

    assert st1.seat == "TREND_WATCH"
    assert st3.seat == "EVICTED"
    assert st3.eviction_count == 1
    assert st3.evicted_ts == t3
    assert len(hp.evicted_history["000003"]) == 1

    # 迟到帧幂等审计
    hp.step_frame("2026-11-05", t2, quotes_t2, lambda c, d: daily_mock.get(c, {}))
    assert len(hp.late_frame_audit_log) == 1
    assert hp.late_frame_audit_log[0]["reason"] == "late_frame_ignored"


# =====================================================================
# 测试组 4: Step 2 DayReplay 纯候选覆盖验证与实证核验
# =====================================================================

def test_day_replay_pure_candidate_coverage_mode():
    """验证 DayReplay 纯候选覆盖模式（关闭人工焦点、关闭继承、关闭历史注入）。"""
    cfg = ReplayConfig(
        top_n=200,
        structure_seed_n=50,
        focus_codes=(),               # 关闭配置内置人工焦点
        use_production_history=False, # 关闭生产历史梯度注入
        enable_hot_pool=True,         # 开启热榜追踪
    )
    dr = DayReplay(config=cfg)
    # 取一个缓存中存在的有效交易日
    day = "2026-11-04"

    # 执行纯候选覆盖回放（focus 为空，carry_codes 为空）
    res = dr.run(
        day=day,
        focus=(),
        carry_codes=(),
        enable_hot_pool=True,
    )

    assert res.meta.get("error") is None
    # 验证热榜状态被正确收集到 ReplayResult
    assert isinstance(res.hot_pool_candidates, dict)
    assert isinstance(res.hot_pool_seats, dict)
    assert isinstance(res.hot_pool_events, list)

    active_seated = [s for s in res.hot_pool_seats.values() if s.get("seat") not in ("NONE", None)]
    print(f"\n[实证结果] 日期: {day}")
    print(f"热榜激活候选总数: {len(res.hot_pool_candidates)}")
    print(f"热榜在席有效标的总数: {len(active_seated)} (候选总池: {len(res.hot_pool_seats)})")
    print(f"热榜席位流转事件数: {len(res.hot_pool_events)}")

    # 检查实盘标的 000995, 300139 等是否成功在热榜中留存
    for target in ("000995", "300139", "688411", "600118"):
        if target in res.hot_pool_candidates:
            cand = res.hot_pool_candidates[target]
            seat_info = res.hot_pool_seats.get(target, {})
            print(f"标的 {target} -> 来源: {cand.get('source')} | 原因: {cand.get('reason')} | 最终席位: {seat_info.get('seat')} | 首见时间: {seat_info.get('first_observed_ts')}")
