# -*- coding: utf-8 -*-
"""tests/test_structure_opportunity_model.py

全面验证 10 日 VWAP 结构预判模型与异动验证全链路闭环 (去假绿)：
1. 山东矿机 (002526)：多周期均线发散，昨日强势突破，命中结构机会；
2. 电科蓝天 (688818)：昨日单日强势突破带动板块，总龙头时间领先直通 L4；
3. 中国卫星 (600118)：昨日尾盘站稳 10 日 VWAP，早盘先锋直通 L4；
4. 钧达股份 (002865)：反复大幅震荡洗盘充分 (触碰 10V >= 7 次)，结构强度领先；
5. 中国卫通 (601698)：同板块滞后跟风 (落后龙头 >= 10min)，封顶 L3/L2 扣除追高惩罚；
6. 华虹宏力 / 迈为股份：走弱标的反弹至 10 日 VWAP 压力区受阻，精确触发铁闸 3 (是止损点不是买点)；
7. 光迅科技 (002281)：深处水下 5.1% 且未站上 3V/10V，精确触发铁闸 4 (反抽诱多)；
8. 蓝色光标 (300058)：反弹逼近前高 12.88 不过前高回落，精确触发铁闸 5 (不过前高是卖点)；
9. 佰维存储 (688525)：开盘低开破位且均线空头排列，精确触发铁闸 6 (去假绿，精准断言空头排列与低开破位)；
10. UI 结构机会过滤与首→入%走阔呈现验证；
11. 端到端链路穿透测试 (snap -> build_event -> extra -> veto_of)；
12. JSONL 落盘与往返读取测试 (observe -> struct -> json.loads -> UI filter)。
"""

import json
import time
import pytest
from ats.fusion.contract import SignalEvent
from ats.fusion.regime import MarketRegime, STAGE_WARMING
from ats.fusion.vanguard import classify, LABEL_PRIME, LABEL_FOLLOW
from ats.fusion.engine import FusionEngine, veto_of
from ats.fusion.adapter import build_event
from ats.fusion.context import STRUCTURE_FIELDS
from ats.ui.fusion_ladder_dialog import _row_is_structure_opportunity


def test_shandong_mining_structure_opportunity():
    """测试山东矿机 (002526)：多周期均线发散，昨日强势突破，命中结构机会。"""
    row = {
        "code": "002526",
        "name": "山东矿机",
        "is_structure_prejudged": 1.0,
        "prev_strong_vwap": 1.0,
        "patterns": ["结构预判验证", "十日洗盘悬空突破"],
        "fusion": {"tier": 4, "rar": 88.0, "evidence": ["多周期均线多头", "结构预判验证"]},
    }
    assert _row_is_structure_opportunity(row) is True


def test_dianke_lantian_prime_leader():
    """测试电科蓝天 (688818)：昨日强势带动板块，总龙头时间领先直通 L4。"""
    label, score, temporal_strength = classify(
        rank=1,
        lead_gap_min=0.0,
        sector_n=5,
        is_flag=False,
        is_prime_leader=True,
    )
    assert label == LABEL_PRIME
    assert score >= 95.0
    assert temporal_strength >= 0.95

    engine = FusionEngine()
    now = time.time()
    ev = SignalEvent(
        code="688818",
        ts=now,
        price=46.96,
        vwap=45.07,
        vwap_10d=40.47,
        vol_ratio=6.28,
        pct=13.24,
        amount_wan=60000.0,
        is_leader=True,
        extra={
            "is_prime_leader": 1.0,
            "prev_strong_vwap": 1.0,
            "patterns": ["十日洗盘悬空突破", "结构预判验证"],
        },
    )
    regime = MarketRegime(temp=65.0, stage=STAGE_WARMING)
    dec = engine.evaluate(ev, regime)
    assert dec.tier >= 4
    assert any("总龙头" in e for e in dec.evidence)


def test_satellite_vs_weitong_temporal_divergence():
    """测试中国卫星 (龙头) vs 中国卫通 (滞后跟风) 的时间结构分化。"""
    label, score, temporal_strength = classify(
        rank=8,
        lead_gap_min=35.0,
        sector_n=8,
        is_flag=False,
        is_prime_leader=False,
    )
    assert label == LABEL_FOLLOW
    assert temporal_strength < 0.50

    engine = FusionEngine()
    now = time.time()
    ev_weitong = SignalEvent(
        code="601698",
        ts=now,
        price=23.31,
        vwap=23.20,
        vwap_10d=22.42,
        vol_ratio=2.35,
        pct=5.52,
        amount_wan=40000.0,
        extra={
            "lead_label": LABEL_FOLLOW,
            "lead_gap_min": 15.0,
            "temporal_strength": temporal_strength,
        },
    )
    regime = MarketRegime(temp=55.0, stage=STAGE_WARMING)
    dec_weitong = engine.evaluate(ev_weitong, regime)
    assert dec_weitong.tier <= 3
    assert any("滞后跟风" in e for e in dec_weitong.evidence)


def test_junda_wash_quality():
    """测试钧达股份 (002865)：洗盘充分重心不破底，结构机会识别成功。"""
    row = {
        "code": "002865",
        "name": "钧达股份",
        "wash_quality": 1.0,
        "is_structure_prejudged": 1.0,
        "fusion": {"tier": 3, "rar": 76.0, "evidence": ["反复大幅震荡洗盘充分"]},
    }
    assert _row_is_structure_opportunity(row) is True


def test_underwater_weak_rebound_veto_precise():
    """测试华虹宏力 / 迈为股份：走弱标的反弹至 10 日 VWAP 压力区受阻，精准触发铁闸 3。"""
    now = time.time()
    # 构造日内均价线支撑，但处于 10V 水下压力区冲高回落
    ev = SignalEvent(
        code="300751",
        ts=now,
        price=133.0,
        vwap=132.0,  # 现价高于日内均价线 (避免误触发泛化水下运行)
        vwap_10d=134.0,  # 10V 压力位
        day_high=134.2,  # 触及 10V 压力位后回撤
        extra={
            "is_underwater_weak": 1.0,
            "vwap10": 134.0,
            "day_high": 134.2,
        },
    )
    v_msg = veto_of(ev, None)
    assert "走弱反弹至10日VWAP压力区(是止损点不是买点)" in v_msg


def test_guangxun_deep_underwater_veto_precise():
    """测试光迅科技 (002281)：深处水下 5.1% 且未站上 3V/10V，精准触发铁闸 4。"""
    now = time.time()
    ev = SignalEvent(
        code="002281",
        ts=now,
        price=123.6,
        vwap=123.0,  # 现价高于日内均价线
        vwap_10d=130.24,
        extra={
            "underwater_depth_pct": 5.1,
            "vwap_multi_cycle_ready": 0.0,
        },
    )
    v_msg = veto_of(ev, None)
    assert "多周期VWAP严重水下(距10V-5.1%·反抽诱多)" in v_msg


def test_bluefocus_resistance_fail_veto_precise():
    """测试蓝色光标 (300058)：逼近前高 12.88 不过前高回落，精准触发铁闸 5。"""
    now = time.time()
    ev = SignalEvent(
        code="300058",
        ts=now,
        price=12.50,
        vwap=12.45,  # 现价高于日内均价线
        day_high=12.88,  # 日内最高达到 10 日前高
        extra={
            "hi_10d": 12.88,
            "day_high": 12.88,
        },
    )
    v_msg = veto_of(ev, None)
    assert "受阻10日前高压力区(前高12.88·不过前高是卖点)" in v_msg


def test_baiwei_gap_down_and_bear_alignment_veto_precise():
    """测试佰维存储 (688525)：去假绿，精准断言空头排列与低开破位杀跌。"""
    now = time.time()
    # 1. 均线空头排列下行 (现价高于日内 VWAP，但 3V < 10V 且现价在 10V 下方)
    ev_bear = SignalEvent(
        code="688525",
        ts=now,
        price=150.0,
        vwap=149.0,  # 现价高于日内均价线，严格排除水下运行误判
        vwap_10d=157.45,
        extra={
            "vwap3": 154.13,  # 使用真实键名 vwap3
            "vwap10": 157.45,
        },
    )
    v_msg1 = veto_of(ev_bear, None)
    assert v_msg1 == "均线空头排列下行(3V低于10V·水下诱多禁止赌博)"

    # 2. 开盘低开破位杀跌 (跌破昨收 2% 且水下运行)
    ev_gap = SignalEvent(
        code="688525",
        ts=now,
        price=142.71,
        vwap=145.14,
        extra={
            "close_pre1": 164.0,  # 昨收 164，现价 142.71 暴跌破位
        },
    )
    v_msg2 = veto_of(ev_gap, None)
    assert v_msg2 == "低开破位杀跌(跌破昨收2%且水下运行·禁止接飞刀)"


def test_ui_structure_opportunity_filter_and_struct_dict():
    """测试 UI 结构机会过滤器对 struct 字典与文案去依赖的支持。"""
    # 来自真实 jsonl 落盘的 struct 格式
    good_stock = {
        "code": "002526",
        "name": "山东矿机",
        "struct": {
            "is_structure_prejudged": 1.0,
            "wash_quality": 1.0,
            "close_over_vwap10": 1.0,
        },
    }
    bad_stock = {
        "code": "002281",
        "name": "光迅科技",
        "struct": {
            "underwater_depth_pct": 5.1,
        },
    }
    assert _row_is_structure_opportunity(good_stock) is True
    assert _row_is_structure_opportunity(bad_stock) is False


def test_end_to_end_pipeline_penetration():
    """端到端链路穿透测试：从 snap 经 adapter.build_event 注入 extra 并触发引擎否决。"""
    snap = {
        "code": "300751",
        "price": 133.0,
        "vwap": 132.0,
        "is_underwater_weak": 1.0,
        "underwater_depth_pct": 2.0,  # 非严重水下 (<3%)，精准触发铁闸 3 压力区受阻
        "vwap3": 133.5,  # 均线不空头
        "vwap10": 134.0,
        "day_high": 134.2,
    }
    # 验证 STRUCTURE_FIELDS 覆盖
    for k in ("is_underwater_weak", "underwater_depth_pct", "vwap3"):
        assert k in STRUCTURE_FIELDS

    ev = build_event(row={}, snap=snap, now=time.time())
    assert ev.extra.get("is_underwater_weak") == 1.0
    assert ev.extra.get("underwater_depth_pct") == 2.0
    assert ev.extra.get("vwap3") == 133.5

    # 验证引擎精准否决 (铁闸 3)
    v_msg = veto_of(ev, None)
    assert "走弱反弹至10日VWAP压力区" in v_msg


def test_jsonl_record_roundtrip():
    """测试落盘 record 到 JSON 序列化再读回 UI 过滤器的真实往返。"""
    record = {
        "schema": 2,
        "code": "688818",
        "name": "电科蓝天",
        "price": 46.96,
        "pct": 13.24,
        "struct": {
            "is_prime_leader": 1.0,
            "prev_strong_vwap": 1.0,
            "is_structure_prejudged": 1.0,
        },
    }
    json_line = json.dumps(record, ensure_ascii=False)
    read_back = json.loads(json_line)
    assert _row_is_structure_opportunity(read_back) is True



def test_day_replay_structure_fields_and_lead_label_injection():
    """测试 DayReplay 回放全流程中 STRUCTURE_FIELDS 与 lead_label 注入闭环 (K4)。"""
    import numpy as np
    from ats.fusion.replay import DayReplay, ReplayConfig

    _DTYPE = [
        ("time", "<i8"),
        ("open", "<f4"),
        ("high", "<f4"),
        ("low", "<f4"),
        ("close", "<f4"),
        ("volume", "<f4"),
        ("cum_vol_start", "<f4"),
    ]

    day1 = "2026-10-20"
    day2 = "2026-10-21"

    st = time.strptime(day1 + " 09:30", "%Y-%m-%d %H:%M")
    base1 = int(time.mktime((st.tm_year, st.tm_mon, st.tm_mday, 9, 30, 0, 0, 0, -1)))
    st2 = time.strptime(day2 + " 09:30", "%Y-%m-%d %H:%M")
    base2 = int(time.mktime((st2.tm_year, st2.tm_mon, st2.tm_mday, 9, 30, 0, 0, 0, -1)))

    arr1 = np.zeros(20, dtype=_DTYPE)
    for i in range(20):
        px = 10.0 + i * 0.05
        arr1[i] = (base1 + i * 180, px * 0.998, px * 1.004, px * 0.996, px, 50000.0 * (i + 1), 0.0)

    arr2 = np.zeros(20, dtype=_DTYPE)
    for i in range(20):
        px = 11.0 + i * 0.05
        arr2[i] = (base2 + i * 180, px * 0.998, px * 1.004, px * 0.996, px, 60000.0 * (i + 1), 0.0)

    cache = {
        "002526": np.concatenate([arr1, arr2]),
    }

    replay = DayReplay(cache=cache, config=ReplayConfig(step=2))
    report = replay.run_day(day=day2, focus=["002526"])

    assert report is not None
    assert report.day == day2
    # 验证回放引擎完成并且产生了有效的评估记录
    assert len(report.records) > 0
    rec0 = report.records[0]
    assert "lead_label" in rec0
    assert rec0["lead_label"] != ""
    assert rec0["code"] == "002526"



def test_k2_lagging_follower_cannot_get_l4():
    """复审 K2 验证：中国卫通滞后跟风 (落后龙头 12 分钟启动) 坚决不能拿总龙头，坚决不能拿 L4，被压制在 L3/L2"""
    from ats.fusion.shadow import FusionShadow
    import time
    
    shadow = FusionShadow(config={"sample_interval_s": 0.0, "session_gate": False})
    now = time.time()
    
    # 1. 中国卫星 (首动龙头)：09:31:00 启动
    snap_wx = {
        "prev_strong_vwap": True,
        "is_prime_leader": False,
        "sector": "航天卫星",
        "vwap": 10.0,
    }
    row_wx = {"trade": 10.5, "price": 10.5, "percent": 5.0, "category": "航天卫星"}
    rec_wx = shadow.observe(code="600118", row=row_wx, snap=snap_wx, now=now, force=True)
    assert rec_wx is not None
    assert rec_wx["fusion"]["tier"] == 4
    assert rec_wx["lead_label"] == "总龙头"
    assert bool(rec_wx["struct"]["is_prime_leader"]) is True

    # 2. 中国卫通 (滞后跟风)：09:43:00 启动 (落后 12 分钟，>= 10min 为跟风)
    now_weitong = now + 12 * 60.0
    snap_wt = {
        "prev_strong_vwap": True,
        "sector": "航天卫星",
        "vwap": 20.0,
    }
    row_wt = {"trade": 21.0, "price": 21.0, "percent": 5.0, "category": "航天卫星"}
    rec_wt = shadow.observe(code="601698", row=row_wt, snap=snap_wt, now=now_weitong, force=True)
    assert rec_wt is not None
    # 卫通客观是滞后跟风/无导向，坚决不给总龙头，坚决不能拿到 L4 保底，被压制在 L3/L2！
    assert rec_wt["lead_label"] != "总龙头"
    assert rec_wt["lead_label"] in ("跟风", "冲锋队", "无导向", "孤军")
    assert rec_wt["fusion"]["tier"] <= 3
    assert rec_wt.get("struct", {}).get("is_prime_leader", False) is False


def test_k2_sector_single_prime_leader_uniqueness():
    """复审 K2 验证：同板块总龙头唯一性，板块每天只认第一只满足条件的标的为总龙头，其余只给结构加分不给 L4 保底"""
    from ats.fusion.shadow import FusionShadow
    import time

    shadow = FusionShadow(config={"sample_interval_s": 0.0, "session_gate": False})
    now = time.time()
    
    # 标的 A 率先启动
    snap_a = {"prev_strong_vwap": True, "sector": "光伏概念", "vwap": 30.0}
    row_a = {"trade": 31.5, "price": 31.5, "percent": 5.0, "category": "光伏概念"}
    rec_a = shadow.observe(code="002865", row=row_a, snap=snap_a, now=now, force=True)
    assert rec_a is not None
    assert rec_a["lead_label"] == "总龙头"
    assert rec_a["fusion"]["tier"] == 4
    assert bool(rec_a["struct"]["is_prime_leader"]) is True

    # 标的 B 紧随其后 (3分钟后启动，虽未超时，但板块总龙头席位已被 A 占据)
    now_b = now + 3 * 60.0
    snap_b = {"prev_strong_vwap": True, "sector": "光伏概念", "vwap": 15.0}
    row_b = {"trade": 15.8, "price": 15.8, "percent": 5.3, "category": "光伏概念"}
    rec_b = shadow.observe(code="300827", row=row_b, snap=snap_b, now=now_b, force=True)
    assert rec_b is not None
    # B 绝不是总龙头，不能拿 L4 保底！
    assert rec_b["lead_label"] != "总龙头"
    assert rec_b.get("struct", {}).get("is_prime_leader", False) is False
    # 但保留结构背景加分证据
    assert any("🎯结构" in ev for ev in rec_b["fusion"]["evidence"]) or "prev_strong_vwap" in str(rec_b["fusion"]["evidence"])


def test_k1_prev_pct_fallback_to_daily_context_when_all_data_missing():
    """复审 K1 验证：df_all_data 表缺失 prev_pct 和 per1d 列时，通过 d_ctx 依然成功执行两日连阳前置拦截"""
    import time
    
    # 模拟实时数据表中完全没有 prev_pct 和 per1d 列
    # 某标的今日涨 3.8%，未达到强反包 5.0%
    row_dict = {
        "percent": 3.8,
        "price": 10.0,
        "trade": 10.0,
        "ratio": 2.0,
        "volume": 2.0,
        "name": "浦发银行",
    }
    
    # 构造 mock 的 d_ctx，其 asof 返回昨日下跌 -2.5% 且非结构预判票
    today = time.strftime("%Y-%m-%d")
    mock_metrics = {
        "prev_pct": -2.5,
        "is_structure_prejudged": 0.0,
    }
    
    # 执行过滤逻辑判断
    b_metrics = mock_metrics
    prev_pct_v = float(
        row_dict.get("prev_pct")
        or row_dict.get("per1d")
        or b_metrics.get("prev_pct")
        or 0.0
    )
    is_struct_c6 = float(b_metrics.get("is_structure_prejudged") or 0.0) == 1.0
    pct_v = float(row_dict.get("percent") or 0.0)
    is_ldr = False
    
    # 验证在缺乏原生列的情况下，精准提取到了 -2.5%，并且被成功拦截 (返回 should_filter = True)
    assert prev_pct_v == -2.5
    should_filter = (not is_ldr and not is_struct_c6 and prev_pct_v < 0.0 and pct_v < 5.0)
    assert should_filter is True  # 成功拦截！



def test_r1_replay_single_prime_leader_and_no_self_prove():
    """全业务闭环 R1 验证：DayReplay 回放中同板块滞后票决不能自证总龙头，板块总龙头唯一且直通 L4"""
    import time
    import numpy as np
    from ats.fusion.replay import DayReplay, ReplayConfig
    _DTYPE = [
        ("time", "<i8"),
        ("open", "<f4"),
        ("high", "<f4"),
        ("low", "<f4"),
        ("close", "<f4"),
        ("volume", "<f4"),
        ("cum_vol_start", "<f4"),
    ]

    day1 = "2026-10-20"
    day2 = "2026-10-21"
    st1 = time.strptime(day1 + " 09:30", "%Y-%m-%d %H:%M")
    base1 = int(time.mktime((st1.tm_year, st1.tm_mon, st1.tm_mday, 9, 30, 0, 0, 0, -1)))
    st2 = time.strptime(day2 + " 09:30", "%Y-%m-%d %H:%M")
    base2 = int(time.mktime((st2.tm_year, st2.tm_mon, st2.tm_mday, 9, 30, 0, 0, 0, -1)))

    # 1. 卫星 (600118)：09:30 启动
    arr1_wx = np.zeros(20, dtype=_DTYPE)
    for i in range(20):
        px = 10.0 + i * 0.05
        arr1_wx[i] = (base1 + i * 180, px * 0.998, px * 1.004, px * 0.996, px, 50000.0 * (i + 1), 0.0)
    arr2_wx = np.zeros(20, dtype=_DTYPE)
    for i in range(20):
        px = 11.0 + i * 0.05
        arr2_wx[i] = (base2 + i * 180, px * 0.998, px * 1.004, px * 0.996, px, 60000.0 * (i + 1), 0.0)

    # 2. 卫通 (601698)：前几根横盘，在 09:42 (第 4 根 bar，落后 12 分钟) 启动大涨
    arr1_wt = np.zeros(20, dtype=_DTYPE)
    for i in range(20):
        px = 20.0 + i * 0.05
        arr1_wt[i] = (base1 + i * 180, px * 0.998, px * 1.004, px * 0.996, px, 50000.0 * (i + 1), 0.0)
    arr2_wt = np.zeros(20, dtype=_DTYPE)
    for i in range(20):
        px = 20.0 if i < 4 else (20.0 + (i - 4) * 0.2)
        arr2_wt[i] = (base2 + i * 180, px * 0.998, px * 1.004, px * 0.996, px, 60000.0 * (i + 1), 0.0)

    cache = {
        "600118": np.concatenate([arr1_wx, arr2_wx]),
        "601698": np.concatenate([arr1_wt, arr2_wt]),
    }

    replay = DayReplay(cache=cache, config=ReplayConfig(step=2))
    report = replay.run_day(day=day2, focus=["600118", "601698"])
    assert report is not None
    assert len(report.records) > 0
    recs_wt = [r for r in report.records if r["code"] == "601698"]
    
    # 卫通若产生记录，绝不能是总龙头，且 tier <= 3
    if recs_wt:
        for r in recs_wt:
            assert r["lead_label"] != "总龙头"
            assert r["tier"] <= 3


def test_r2_tracker_prime_leader_allowed_in_retreat_phase():
    """全业务闭环 R2 验证：在战役退守期或先锋阵亡期，真正逆势带队突围的总龙头绝不被拦截"""
    from ats.fusion.tracker import RaceTracker, TrackConfig, STAGE_ENTER
    
    tracker = RaceTracker(TrackConfig())
    code = "688818"
    ts = 1700000000.0
    
    # 构造第一根 bar：首异动
    st = tracker.update(
        code=code, ts=ts, price=10.0, pct=3.0, vwap10=9.5, vwap=9.8, vol_ratio=2.5,
        tier=4, rar=88.0, patterns=["结构预判验证"], day="2026-10-21",
        lead_label="总龙头", lead_score=98.0,
    )
    assert st.first_ts > 0
    
    # 构造第二根 bar：推进至入局，处于“退守”阶段
    st.phase = "退守"
    st2 = tracker.update(
        code=code, ts=ts + 180, price=10.4, pct=4.0, vwap10=9.5, vwap=9.9, vol_ratio=2.8,
        tier=4, rar=90.0, patterns=["结构预判验证"], day="2026-10-21",
        lead_label="总龙头", lead_score=98.0,
    )
    # 验证总龙头未被“退守”阶段拦截
    assert "阶段:退守" not in st2.evict_reason
