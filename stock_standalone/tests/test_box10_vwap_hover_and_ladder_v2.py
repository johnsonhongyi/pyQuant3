# -*- coding: utf-8 -*-
"""
tests/test_box10_vwap_hover_and_ladder_v2.py
---------------------------------------------
测试 10 日 VWAP 结构异动双轨极限性能落地 V2 优化规范：
1. 校验 RaceTracker 在 STAGE_WATCH 时不导出虚假 0.0，Dialog 回退真实触发涨幅，首入差正常；
2. 校验 DailyContext 量纲自校准、双创 20cm 弹性箱体振幅与多周期 VWAP 粘合度；
3. 校验 enrich.py 剥离首根 t=0 起跳 Bar 死锁与早盘 3<=n<8 分时悬空垫计算；
4. 校验 engine.py 水下运行硬否决与 PATTERN_BOX10_VWAP_HOVER 豁免板块共振直通 L4。
"""

import pytest
import numpy as np
from ats.fusion.tracker import TrackState, STAGE_WATCH, STAGE_ENTER
from ats.fusion.anomaly import PATTERN_BOX10_VWAP_HOVER, detect_patterns, pattern_score
from ats.fusion.enrich import intraday_fields
from ats.fusion.contract import SignalEvent
from ats.fusion.engine import FusionEngine, veto_of
from ats.fusion.regime import MarketRegime, STAGE_COLD


def test_tracker_watch_state_enter_pct_not_zero_pollution():
    """测试 1: 观察期 (STAGE_WATCH) 时 enter_pct 为 None，不污染真实触发帧涨幅"""
    st = TrackState(code="300806", day="2026-10-28")
    st.first_ts = 1730079000.0
    st.first_pct = 8.77
    st.last_pct = 8.77
    st.stage = STAGE_WATCH
    st.enter_ts = 0.0
    st.enter_price = 0.0
    st.enter_pct = 0.0

    d = st.to_dict()
    assert d["enter_pct"] is None, "未正式入局前 enter_pct 必须为 None，绝不能导出虚假的 0.0"
    assert d["enter_price"] is None, "未正式入局前 enter_price 必须为 None"
    assert d["first_pct"] == 8.77

    # 模拟进入 STAGE_ENTER
    st.stage = STAGE_ENTER
    st.enter_ts = 1730082232.0
    st.enter_price = 39.81
    st.enter_pct = 8.77

    d2 = st.to_dict()
    assert d2["enter_pct"] == 8.77
    assert d2["enter_price"] == 39.81


def test_enrich_skip_launch_bar_and_cushion():
    """测试 2: enrich.py 剥离 t=0 首根起跳 Bar，从 t>=1 检验悬空垫并放行 3<=n<8 早盘通道"""
    # 模拟开盘 4 根 1 分钟线 (09:30~09:34 逼空主升结构：最低价完全悬空在均价之上)
    # t=0: open=36.6, close=37.2, high=37.3, low=36.5 (首根起跳，low <= vwap 正常)
    # t=1: open=37.2, close=37.8, high=37.9, low=37.5 (vwap=37.24, low 37.5 > vwap 0.7%)
    # t=2: open=37.8, close=38.4, high=38.5, low=38.0 (vwap=37.60, low 38.0 > vwap 1.0%)
    # t=3: open=38.4, close=38.9, high=39.0, low=38.6 (vwap=37.97, low 38.6 > vwap 1.6%)
    bars = [
        {"open": 36.6, "high": 37.3, "low": 36.5, "close": 37.2, "vol": 5000},
        {"open": 37.2, "high": 37.9, "low": 37.6, "close": 37.8, "vol": 6000},
        {"open": 37.8, "high": 38.5, "low": 38.0, "close": 38.4, "vol": 7000},
        {"open": 38.4, "high": 39.0, "low": 38.6, "close": 38.9, "vol": 8000},
    ]
    feats = intraday_fields(bars)
    assert bool(feats), "3<=n<8 时只要满足悬空不碰均线，早盘通道必须放行"
    assert feats.get("vwap_zero_touch") == 1.0, "回踩不碰均线必须为 True"
    assert feats.get("min_vwap_cushion") > 0.25, "从 t>=1 检验的悬空垫必须大于等于 0.25%"


def test_anomaly_box10_hover_pattern():
    """测试 3: 10日洗盘蓄势突破 + 分时悬空正确识别 PATTERN_BOX10_VWAP_HOVER"""
    patterns = detect_patterns(
        price=39.5,
        day_open=37.5,
        ma5=37.7,
        ma10=38.4,
        ma20=38.0,
        pct=7.5,
        ret_std20=1.5,
        vol_ratio=2.5,
        rs5=3.0,
        mkt_ret5=0.5,
        is_leader=True,
        vwap10=38.4,
        is_box10_ready=True,
        hi_10d=39.2,
        hi_pre1=39.0,
        min_vwap_cushion=0.85,
    )
    assert PATTERN_BOX10_VWAP_HOVER in patterns
    score = pattern_score(patterns)
    assert score >= 60.0


def test_engine_water_veto_and_l4_direct():
    """测试 4: engine.py 水下运行一票否决；十日洗盘悬空突破直通 L4 主攻并豁免早盘板块共振滞后"""
    engine = FusionEngine(today="2026-10-28")

    # 1. 水下运行硬否决测试：现价 36.5，均价 37.0
    ev_water = SignalEvent(
        code="300806",
        ts=1730079300.0,
        price=36.5,
        vwap=37.0,
    )
    veto = veto_of(ev_water, None, today="2026-10-28")
    assert "水下运行" in veto, "价格低于 VWAP 必须硬否决"

    # 2. 十日洗盘悬空突破直通 L4 测试：即使板块共振仅 20.0 (未达60)，且处于早盘 STAGE_COLD 寒冷期
    regime_cold = MarketRegime(
        stage=STAGE_COLD,
        temp=35.0,
    )
    ev_break = SignalEvent(
        code="300806",
        ts=1730079300.0,
        price=39.8,
        vwap=38.5,
        sector_resonance=20.0,  # 远低于 60.0
        extra={
            "patterns": [PATTERN_BOX10_VWAP_HOVER],
            "box10_hover_break": True,
            "min_vwap_cushion": 1.2,
            "is_box10_ready": True,
            "vol_ratio": 2.5,
        },
    )
    dec = engine.evaluate(ev_break, regime_cold, now=1730079300.0)
    assert dec.tier == 4, f"十日洗盘悬空突破必须直通 L4 主攻，实际得到 L{dec.tier}"


def test_shadow_observe_and_patterns_propagation():
    """测试 5: 实盘影子流 observe 识别 PATTERN_BOX10_VWAP_HOVER 并直通 L4"""
    from ats.fusion.shadow import FusionShadow
    import time

    shadow = FusionShadow(config={"enabled": True, "shadow_only": True, "session_gate": False})
    
    row_data = {
        "code": "300806",
        "trade": 39.5,
        "price": 39.5,
        "open": 37.5,
        "ma5": 37.7,
        "ma10": 38.4,
        "ma20": 38.0,
        "vwap": 38.2,
        "percent": 7.5,
        "ret_std20": 1.5,
        "vol_ratio": 2.5,
        "rs5": 3.0,
        "is_box10_ready": True,
        "hi_10d": 39.2,
        "hi_pre1": 39.0,
        "min_vwap_cushion": 0.85,
        "vwap10": 38.4,
    }
    
    now_ts = 1730079300.0  # 09:35:00
    res = shadow.observe(code="300806", row=row_data, now=now_ts, force=True)
    assert res is not None, "shadow.observe 必须成功返回记录"
    assert res["fusion"]["tier"] == 4, f"实盘影子流命中十日洗盘悬空突破必须评级为 L4，实际为 L{res['fusion']['tier']}"
    assert "形态:十日洗盘悬空突破" in res["fusion"]["evidence"]


def test_tracker_box10_fast_path_and_deploy():
    """测试 6: RaceTracker 命中十日洗盘悬空突破首帧直通入局，deploy_path 放宽至 7%"""
    from ats.fusion.tracker import RaceTracker, deploy_path, PATH_BOX10, DeployRule

    tracker = RaceTracker()
    ts = 1730079300.0

    # 模拟首帧（第 1 根分时）突发十日洗盘突破主攻（涨幅 6.2%）
    st = tracker.update(
        code="300806",
        ts=ts,
        price=39.5,
        pct=6.2,
        vwap10=38.4,
        vwap=38.2,
        vol_ratio=2.5,
        tier=4,
        rar=85.0,
        patterns=[PATTERN_BOX10_VWAP_HOVER],
        consensus=0.35,
        lead_score=80.0,
        lead_label="排头兵",
    )

    assert st.stage == STAGE_ENTER, f"十日洗盘突破必须直通 STAGE_ENTER，实际为 {st.stage}"
    assert st.enter_price == 39.5
    assert st.enter_pct == 6.2

    # 检验可下单路径：首异动 6.2% 超过常规 3.0%，但属于十日突破，放宽至 7.0%
    entry_dict = st.to_dict()
    entry_dict.update({
        "theme_rank": 0.85,
        "efficiency": 0.95,
        "consensus": 0.35,
        "lead_value": 0.80,
    })
    path = deploy_path(entry_dict)
    assert path == PATH_BOX10, f"必须返回 '{PATH_BOX10}'，实际返回 '{path}'"


def test_enrich_early_bar_sub_high0_counterexample():
    """测试 7 (反例): 早盘 3<=n<8 现价低于首根最高价时安全返回空，严禁抛出 UnboundLocalError"""
    # t=0: open=37.0, high=39.5 (高开冲出长上影), low=36.8, close=37.5
    # t=1: open=37.5, high=38.0, low=37.4, close=37.6
    # t=2: open=37.6, high=38.0, low=37.5, close=37.7 (现价 37.7 远低于首根高点 39.5)
    bars = [
        {"open": 37.0, "high": 39.5, "low": 36.8, "close": 37.5, "vol": 5000},
        {"open": 37.5, "high": 38.0, "low": 37.4, "close": 37.6, "vol": 6000},
        {"open": 37.6, "high": 38.0, "low": 37.5, "close": 37.7, "vol": 7000},
    ]
    # 执行该反例：未突破首根高点，绝不能抛出 UnboundLocalError，必须安全返回空字典
    feats = intraday_fields(bars)
    assert feats == {}, f"早盘未突破首根高点必须返回空字典，实际返回: {feats}"


def test_engine_box_bottom_not_promoted_counterexample():
    """测试 8 (反例): 箱底未突破标的绝对不能被误保底为 L4 主攻"""
    engine = FusionEngine(today="2026-10-28")
    regime_cold = MarketRegime(stage=STAGE_COLD, temp=30.0)

    # 某标的属于 10 日窄幅池 (is_box10_ready)，分时虽然未跌破均线 (min_vwap_cushion=0.85)，
    # 但涨幅仅 +0.6%，处于箱体底部且未突破箱顶 (没有 PATTERN_BOX10_VWAP_HOVER 形态)
    ev_bottom = SignalEvent(
        code="600000",
        ts=1730079300.0,
        price=10.06,
        vwap=10.02,
        pct=0.6,
        sector_resonance=15.0,
        extra={
            "is_box10_ready": True,
            "min_vwap_cushion": 0.85,
            # patterns 中没有 "十日洗盘悬空突破"
            "patterns": [],
        },
    )
    dec = engine.evaluate(ev_bottom, regime_cold, now=1730079300.0)
    assert dec.tier < 4, f"箱底未突破股票在早盘冷市绝对不可被保底为 L4，实际得到 L{dec.tier}"


def test_daily_context_singleton_dcl():
    """测试 9 (并发): get_daily_context 多线程并发调用安全单例 (DCL)"""
    import concurrent.futures
    from ats.fusion.context import get_daily_context

    instances = []
    def _worker():
        return get_daily_context()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_worker) for _ in range(16)]
        for f in concurrent.futures.as_completed(futures):
            instances.append(f.result())

    assert len(instances) == 16
    first_inst = instances[0]
    for inst in instances:
        assert inst is first_inst, "所有并发线程必须获取完全相同的 DailyContext 实例"
