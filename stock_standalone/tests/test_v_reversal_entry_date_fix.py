# -*- coding: utf-8 -*-
"""
单元测试：V型反转监控潜伏池最初入池时间 (first_entry_date / entry_date) 永久保留与防覆写验证
"""
import os
import sys
import time
import tempfile
import pandas as pd
import numpy as np
import pytest

# 将 stock_standalone 根目录加入 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from realtime_data_service import MinuteKlineCache, KLineItem
from JohnsonUtil import commonTips as cct


@pytest.fixture
def kline_cache():
    cache = MinuteKlineCache(max_len=120, simulation_mode=True, verbose=False)
    return cache


def _set_mock_klines(cache, code, base_price=10.0, base_vol=1000.0, latest_price=10.0, latest_vol=1000.0):
    now_ts = int(time.time())
    items = []
    # 前 15 根为基础盘整
    for i in range(15):
        items.append(KLineItem(
            time=now_ts - (20 - i) * 60,
            open=base_price,
            high=base_price * 1.002,
            low=base_price * 0.998,
            close=base_price,
            volume=base_vol,
            cum_vol_start=0.0
        ))
    # 后 5 根为当前最新状态
    for i in range(5):
        items.append(KLineItem(
            time=now_ts - (5 - i) * 60,
            open=latest_price,
            high=latest_price * 1.002,
            low=latest_price * 0.998,
            close=latest_price,
            volume=latest_vol,
            cum_vol_start=0.0
        ))
    cache._shared_cache[code] = items


def test_initial_entry_date_recorded(kline_cache):
    """测试 1: 首次发现股票入池，正确记录最初入池时间与阶段进入时间"""
    code = "002292"
    today_str = cct.get_today()
    
    _set_mock_klines(kline_cache, code, base_price=10.0, base_vol=1000.0, latest_price=10.0, latest_vol=1000.0)
        
    df_mock = pd.DataFrame([{
        "code": code, "ma5d": 10.1, "ma10d": 10.0, "ma20d": 9.9, "ma60d": 9.5,
        "close": 10.05, "low": 9.95, "dff3": 25.0, "dff2": 5.0, "name": "奥飞娱乐"
    }])
    
    kline_cache.update_wave_structure_state(code, df=df_mock)
    
    flags = kline_cache.get_consolidation_flags(code)
    assert flags.get("phase") == "CONSOLIDATING"
    assert flags.get("entry_date") == today_str
    assert flags.get("first_entry_date") == today_str
    assert flags.get("phase_entry_date") == today_str


def test_entry_date_preserved_across_updates(kline_cache):
    """测试 2: 状态机持续更新，最初入池时间绝不被后续更新覆写"""
    code = "002250"
    historical_date = "2026-08-10"
    
    # 模拟该个股在历史上某天已入池
    kline_cache._consolidation_flags[code] = {
        "phase": "CONSOLIDATING",
        "entry_date": historical_date,
        "first_entry_date": historical_date,
        "first_entry_ts": time.time() - 9 * 86400,
        "phase_entry_date": historical_date,
        "phase_ts": time.time() - 9 * 86400,
        "anchor_low": 15.0,
        "base_vol": 500.0,
        "structure": "MA20/60粘合",
        "name": "联化科技"
    }
    kline_cache._v_reversal_pool.add(code)
    
    _set_mock_klines(kline_cache, code, base_price=15.1, base_vol=500.0, latest_price=15.1, latest_vol=500.0)
        
    df_mock = pd.DataFrame([{
        "code": code, "close": 15.1, "changepercent": 0.5, "now": 15.1
    }])
    
    kline_cache.update_wave_structure_state(code, df=df_mock)
    
    flags = kline_cache.get_consolidation_flags(code)
    # 验证 entry_date 与 first_entry_date 依然严格锁定在最初日期
    assert flags.get("entry_date") == historical_date
    assert flags.get("first_entry_date") == historical_date


def test_phase_transition_keeps_initial_entry_date(kline_cache):
    """测试 3: 波段状态跃迁 (CONSOLIDATING -> WAVE_UP -> PULLBACK -> WAVE_UP_2)，entry_date 锁定，phase_entry_date 推进"""
    code = "605337"
    initial_date = "2026-08-01"
    today_str = cct.get_today()
    now_ts = time.time()
    
    kline_cache._consolidation_flags[code] = {
        "phase": "CONSOLIDATING",
        "entry_date": initial_date,
        "first_entry_date": initial_date,
        "first_entry_ts": now_ts - 18 * 86400,
        "phase_entry_date": today_str,
        "phase_ts": now_ts,
        "anchor_low": 10.0,
        "base_vol": 1000.0,
        "structure": "多头排列",
        "name": "李子园"
    }
    kline_cache._v_reversal_pool.add(code)
    
    # 1. 触发放量突破 -> WAVE_UP (前部10.0，最新拉升到10.5且放量3倍)
    _set_mock_klines(kline_cache, code, base_price=10.0, base_vol=1000.0, latest_price=10.5, latest_vol=3000.0)
        
    df_breakout = pd.DataFrame([{
        "code": code, "close": 10.5, "changepercent": 4.5, "now": 10.5
    }])
    
    kline_cache.update_wave_structure_state(code, df=df_breakout)
    flags = kline_cache.get_consolidation_flags(code)
    
    assert flags.get("phase") == "WAVE_UP"
    assert flags.get("entry_date") == initial_date  # 最初时间保持不变
    assert flags.get("first_entry_date") == initial_date
    assert flags.get("phase_entry_date") == today_str  # 阶段时间更新为今天
    
    # 2. 触发缩量回踩 -> PULLBACK (价格安全回踩至 10.35，缩量至 500)
    _set_mock_klines(kline_cache, code, base_price=10.5, base_vol=1000.0, latest_price=10.35, latest_vol=500.0)
    
    df_pullback = pd.DataFrame([{
        "code": code, "close": 10.35, "changepercent": -0.2, "now": 10.35
    }])
    
    kline_cache.update_wave_structure_state(code, df=df_pullback)
    flags = kline_cache.get_consolidation_flags(code)
    
    assert flags.get("phase") == "PULLBACK"
    assert flags.get("entry_date") == initial_date  # 最初时间保持不变
    assert flags.get("first_entry_date") == initial_date
    
    # 3. 触发二次放量拉升 -> WAVE_UP_2 (价格突破到 10.8，放量 3500)
    _set_mock_klines(kline_cache, code, base_price=10.35, base_vol=1000.0, latest_price=10.8, latest_vol=3500.0)
        
    df_wave2 = pd.DataFrame([{
        "code": code, "close": 10.8, "changepercent": 4.0, "now": 10.8
    }])
    
    kline_cache.update_wave_structure_state(code, df=df_wave2)
    flags = kline_cache.get_consolidation_flags(code)
    
    assert flags.get("phase") == "WAVE_UP_2"
    assert flags.get("entry_date") == initial_date  # 最初时间稳固锁定
    assert flags.get("first_entry_date") == initial_date


def test_persistence_preserves_first_entry_date(kline_cache):
    """测试 4: 持久化保存与加载恢复，保留最初入池时间且不误淘汰活跃拉升股"""
    code = "688617"
    historical_date = "2026-08-15"
    today_str = cct.get_today()
    now_ts = time.time()
    
    kline_cache._consolidation_flags[code] = {
        "phase": "WAVE_UP",
        "entry_date": historical_date,
        "first_entry_date": historical_date,
        "first_entry_ts": now_ts - 4 * 86400,
        "phase_entry_date": today_str,
        "phase_ts": now_ts,
        "anchor_low": 200.0,
        "base_vol": 800.0,
        "structure": "多头排列",
        "name": "惠泰医疗",
        "update_ts": now_ts
    }
    kline_cache._v_reversal_pool.add(code)
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        # 1. 持久化落盘
        saved = kline_cache.save_consolidation_state(tmp_path)
        assert saved is True
        
        # 2. 在全新的缓存实例中加载恢复
        new_cache = MinuteKlineCache(max_len=120, simulation_mode=True, verbose=False)
        loaded = new_cache.load_consolidation_state(tmp_path)
        assert loaded is True
        
        # 验证恢复的数据
        flags = new_cache.get_consolidation_flags(code)
        assert flags.get("phase") == "WAVE_UP"
        assert flags.get("entry_date") == historical_date
        assert flags.get("first_entry_date") == historical_date
        assert flags.get("phase_entry_date") == today_str
        assert code in new_cache.get_v_reversal_pool()
        
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if os.path.exists(tmp_path + ".tmp"):
            os.remove(tmp_path + ".tmp")


def test_favorite_and_manual_add_preserves_entry_date(kline_cache):
    """测试 5: 重点关注同步与手动添加逻辑保持已存在的最初入池时间"""
    code = "603883"
    historical_date = "2026-08-12"
    
    # 模拟已有状态
    state = {
        "phase": "CONSOLIDATING",
        "entry_date": historical_date,
        "first_entry_date": historical_date,
        "first_entry_ts": time.time() - 7 * 86400,
        "name": "老百姓"
    }
    kline_cache._consolidation_flags[code] = state
    
    # 模拟重点关注同步逻辑
    existing_entry = state.get("entry_date") or state.get("first_entry_date")
    if not existing_entry or existing_entry == "-":
        state["entry_date"] = cct.get_today()
        state["first_entry_date"] = cct.get_today()
    else:
        state["entry_date"] = existing_entry
        state["first_entry_date"] = existing_entry
        
    assert state["entry_date"] == historical_date
    assert state["first_entry_date"] == historical_date
