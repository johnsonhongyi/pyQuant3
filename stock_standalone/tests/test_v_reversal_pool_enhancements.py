# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import pytest
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from realtime_data_service import MinuteKlineCache, KLineItem
from JohnsonUtil import commonTips as cct
from sys_utils import get_conf_path

def _set_mock_klines(cache, code, base_price=10.0, base_vol=1000.0, latest_price=10.0, latest_vol=1000.0):
    now_ts = int(time.time())
    items = []
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

@pytest.fixture
def kline_cache():
    cache = MinuteKlineCache(max_len=120, simulation_mode=True, verbose=False)
    cache._consolidation_flags.clear()
    cache._v_reversal_pool.clear()
    yield cache
    cache._consolidation_flags.clear()
    cache._v_reversal_pool.clear()

def test_channel_support_and_vol_price_scoring(kline_cache):
    flags_attack = {"phase": "WAVE_UP", "structure": "多头排列", "first_entry_date": cct.get_today()}
    df_row_good = {
        "ch_dir": 1,
        "ch_supp_slope_deg": 22.0,
        "close": 12.0,
        "ch_supp_price": 11.5,
        "percent": 4.0,
        "vol_ratio": 2.2,
        "Rank": 50
    }
    score_good = kline_cache.calculate_reversal_priority_score("600001", flags_attack, df_row_good)
    flags_weak = {"phase": "CONSOLIDATING", "structure": "MA60支撑", "first_entry_date": cct.last_tddate(4)}
    df_row_bad = {
        "ch_dir": -1,
        "ch_supp_slope_deg": -10.0,
        "close": 9.5,
        "ch_supp_price": 10.5,
        "percent": -3.0,
        "vol_ratio": 1.8,
        "Rank": 3800
    }
    score_bad = kline_cache.calculate_reversal_priority_score("600002", flags_weak, df_row_bad)
    assert score_good >= 180.0
    assert score_bad <= 20.0
    assert score_good - score_bad > 150.0

def test_cleanup_v_reversal_pool_auto_trim(kline_cache):
    today_str = cct.get_today()
    now_ts = time.time()
    for i in range(100):
        code = f"999{i:03d}"
        phase = "WAVE_UP" if i < 30 else ("PULLBACK" if i < 60 else "CONSOLIDATING")
        kline_cache._consolidation_flags[code] = {
            "phase": phase,
            "entry_date": today_str,
            "first_entry_date": today_str,
            "phase_entry_date": today_str,
            "phase_ts": now_ts,
            "anchor_low": 10.0 + i * 0.1,
            "base_vol": 1000.0,
            "structure": "多头排列" if i < 50 else "MA20整理",
            "name": f"模拟股{i}"
        }
        kline_cache._v_reversal_pool.add(code)
    assert len(kline_cache._v_reversal_pool) == 100
    res = kline_cache.cleanup_v_reversal_pool(max_capacity=80)
    assert res["initial_count"] == 100
    assert res["final_count"] <= 80
    assert len(kline_cache.get_v_reversal_pool()) <= 80
    assert res["trimmed_count"] >= 20

def test_phase_extension_limit_breaks_deadlock(kline_cache):
    code = "600888"
    today_str = cct.get_today()
    now_ts = time.time()
    _set_mock_klines(kline_cache, code, base_price=10.0, base_vol=1000.0, latest_price=10.2, latest_vol=1500.0)
    kline_cache._consolidation_flags[code] = {
        "phase": "WAVE_UP",
        "entry_date": today_str,
        "first_entry_date": today_str,
        "phase_entry_date": cct.last_tddate(3) if hasattr(cct, 'last_tddate') else "2026-08-20",
        "phase_ts": now_ts - 3 * 86400,
        "phase_extend_count": 1,
        "wave_1_start_price": 10.0,
        "wave_peak": 10.5,
        "anchor_low": 10.0,
        "base_vol": 1000.0,
        "name": "顺延超期股"
    }
    kline_cache._v_reversal_pool.add(code)
    df_tick = pd.DataFrame([{
        "code": code, "close": 10.2, "changepercent": 2.0, "now": 10.2
    }])
    kline_cache.update_wave_structure_state(code, df=df_tick)
    flags = kline_cache.get_consolidation_flags(code)
    assert flags.get("phase") == "INIT"
    assert code not in kline_cache.get_v_reversal_pool()

def test_total_lifecycle_ttl_eviction(kline_cache):
    code = "600999"
    today_str = cct.get_today()
    now_ts = time.time()
    _set_mock_klines(kline_cache, code, base_price=10.0, base_vol=1000.0, latest_price=10.1, latest_vol=1000.0)
    old_date = cct.last_tddate(8) if hasattr(cct, 'last_tddate') else "2026-08-10"
    kline_cache._consolidation_flags[code] = {
        "phase": "PULLBACK",
        "entry_date": old_date,
        "first_entry_date": old_date,
        "phase_entry_date": today_str,
        "phase_ts": now_ts,
        "pullback_price": 10.0,
        "anchor_low": 9.5,
        "base_vol": 1000.0,
        "name": "僵尸超期股"
    }
    kline_cache._v_reversal_pool.add(code)
    df_tick = pd.DataFrame([{
        "code": code, "close": 10.1, "changepercent": 0.5, "now": 10.1
    }])
    kline_cache.update_wave_structure_state(code, df=df_tick)
    flags = kline_cache.get_consolidation_flags(code)
    assert flags.get("phase") == "INIT"
    assert code not in kline_cache.get_v_reversal_pool()

def test_indicator_help_custom_config_and_content():
    path = get_conf_path("indicator_help_custom.json")
    assert path is not None
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    all_text = " ".join([json.dumps(item, ensure_ascii=False) for item in data])
    assert "ch_dir" in all_text
    assert "ch_supp_slope_deg" in all_text
    assert "ch_supp_price" in all_text
    assert "STRATEGY: 优选上涨通道+支撑线上+量价齐升" in all_text
    assert "ch_dir == 1 and ch_supp_slope_deg > 0 and close >= ch_supp_price" in all_text

def test_deferred_auto_clean_after_full_df_ready(kline_cache):
    import tempfile
    temp_dir = tempfile.mkdtemp()
    try:
        # 1. 模拟冷启动：从持久化文件无损恢复 100 只股票
        state_file = os.path.join(temp_dir, "v_reversal_pool.json")
        now_ts = time.time()
        today_str = cct.get_today()
        mock_state = {
            "v_reversal_pool": [f"60{i:04d}" for i in range(100)],
            "consolidation_flags": {
                f"60{i:04d}": {
                    "phase": "CONSOLIDATING",
                    "entry_date": today_str,
                    "first_entry_date": today_str,
                    "update_ts": now_ts,
                    "phase_entry_date": today_str
                } for i in range(100)
            }
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(mock_state, f)
        
        # 执行无损加载
        loaded = kline_cache.load_consolidation_state(state_file)
        assert loaded is True
        # 核心断言：启动时刻没有 df，绝不能把池子清理为 0 或裁汰
        assert len(kline_cache.get_v_reversal_pool()) == 100

        # 2. 模拟 TK 抓取到完整市场行情 (550只股票的大盘 DataFrame)
        df_rows = []
        for i in range(550):
            code = f"60{i:04d}"
            df_rows.append({
                "code": code,
                "close": 15.0 + i * 0.1,
                "ch_dir": 1 if i < 30 else -1,
                "ch_supp_slope_deg": 15.0 if i < 30 else -5.0,
                "ch_supp_price": 14.0,
                "Rank": i + 1,
                "vol_ratio": 2.0 if i < 30 else 0.8,
                "percent": 3.5 if i < 30 else -1.0
            })
        df_full = pd.DataFrame(df_rows)
        df_full.set_index("code", drop=False, inplace=True)

        # 3. 默认情况下停用自动清理：TK 注入行情数据到 set_df_all_cache，潜伏池保持 100 只不变
        assert kline_cache.enable_auto_cleanup is False
        kline_cache.set_df_all_cache(df_full)
        assert len(kline_cache.get_v_reversal_pool()) == 100  # 安全防线：绝不自动削减/清空池子

        # 4. 当显式开启 enable_auto_cleanup 时，触发安全自动清理与平滑收敛
        kline_cache.enable_auto_cleanup = True
        kline_cache._last_auto_clean_ts = 0.0
        # 强制指纹变更以触发 set_df_all_cache 内部逻辑
        kline_cache._df_all_cache_fp = None
        kline_cache.set_df_all_cache(df_full)

        # 断言：显式开启后，依据自动通道清理！70只处于下降通道(ch_dir=-1)的标的被精准剔除，30只处于上涨通道(ch_dir=1)的核心标的全部保留
        assert len(kline_cache.get_v_reversal_pool()) == 30
        # 前30只具备上涨通道与放量的股票全部被保留
        for i in range(30):
            assert f"60{i:04d}" in kline_cache.get_v_reversal_pool()
        # 确认后70只下降通道股票全部被清理
        for i in range(30, 100):
            assert f"60{i:04d}" not in kline_cache.get_v_reversal_pool()
    finally:
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

def test_cleanup_driven_by_channel_not_time(kline_cache):
    """
    专门验证：依据自动通道清理，而不是时间！
    1. 入池 60 天前、超期极长的标的，只要处于上涨通道(ch_dir=1)且未破位，绝不依据时间清理！
    2. 入池仅 0 天的最新标的，如果处于下降通道(ch_dir=-1)或破位，必须精准清理！
    """
    now_ts = time.time()
    old_date = "2026-06-01"  # 远古入池时间 (距今数月)
    today_str = cct.get_today()

    # 1. 放入 10 只远古入池的股票，但形态良好
    for i in range(10):
        code = f"688{i:03d}"
        kline_cache._consolidation_flags[code] = {
            "phase": "CONSOLIDATING",
            "entry_date": old_date,
            "first_entry_date": old_date,
            "phase_entry_date": old_date,
            "phase_ts": now_ts - 60 * 86400,
            "anchor_low": 20.0,
            "base_vol": 1000.0,
            "name": f"长线潜伏股{i}"
        }
        kline_cache._v_reversal_pool.add(code)

    # 2. 放入 10 只今天入池的股票
    for i in range(10):
        code = f"300{i:03d}"
        kline_cache._consolidation_flags[code] = {
            "phase": "CONSOLIDATING",
            "entry_date": today_str,
            "first_entry_date": today_str,
            "phase_entry_date": today_str,
            "phase_ts": now_ts,
            "anchor_low": 20.0,
            "base_vol": 1000.0,
            "name": f"今日次新入池{i}"
        }
        kline_cache._v_reversal_pool.add(code)

    assert len(kline_cache.get_v_reversal_pool()) == 20

    # 3. 构造行情：688 为上涨通道(ch_dir=1)，300 为下降通道(ch_dir=-1)
    df_rows = []
    for i in range(10):
        df_rows.append({
            "code": f"688{i:03d}",
            "close": 25.0,
            "ch_dir": 1,  # 上涨通道
            "ch_supp_slope_deg": 18.0,
            "ch_supp_price": 22.0,
            "Rank": 100 + i
        })
    for i in range(10):
        df_rows.append({
            "code": f"300{i:03d}",
            "close": 19.0,
            "ch_dir": -1,  # 下降通道
            "ch_supp_slope_deg": -12.0,
            "ch_supp_price": 21.0,
            "Rank": 4000 + i
        })
    df_snap = pd.DataFrame(df_rows)
    df_snap.set_index("code", drop=False, inplace=True)

    # 4. 执行基于通道的智能清理
    res = kline_cache.cleanup_v_reversal_pool(max_capacity=80, df=df_snap)

    # 核心断言：
    # 10 只入池 60 天的 688 上涨通道股票 100% 全部被保留！(绝不以时间清理)
    for i in range(10):
        assert f"688{i:03d}" in kline_cache.get_v_reversal_pool()
    # 10 只今天刚入池但处于下降通道的 300 股票 100% 全部被清理！
    for i in range(10):
        assert f"300{i:03d}" not in kline_cache.get_v_reversal_pool()

    assert len(kline_cache.get_v_reversal_pool()) == 10
    assert res["final_count"] == 10

def test_scan_and_auto_add_uptrend_channel_stocks(kline_cache):
    """
    专门验证：全市场自动通道上涨趋势个股的主动扫描与纳标引擎
    1. 自动从全市场数据中识别 ch_dir=1、站稳支撑线、量价健康的标的；
    2. 自动吸纳入池并赋予 CONSOLIDATING 潜伏状态与 '上涨通道' 结构标签；
    3. 下降通道 (ch_dir=-1) 或破位标的坚决不被添加。
    """
    # 模拟全市场行情 (60 只标的)
    df_rows = []
    # 0~24 (25只): 上涨通道标的
    for i in range(25):
        df_rows.append({
            "code": f"603{i:03d}",
            "name": f"通道牛股{i}",
            "close": 20.0 + i * 0.5,
            "low": 19.5 + i * 0.5,
            "ch_dir": 1,
            "ch_supp_slope_deg": 15.0 + i * 0.5,
            "ch_supp_price": 19.0 + i * 0.5,
            "ch_supp_pos": 45.0,
            "Rank": 100 + i * 10,
            "vol_ratio": 1.8,
            "changepercent": 2.5
        })
    # 25~59 (35只): 下跌通道或破位标的
    for i in range(25, 60):
        df_rows.append({
            "code": f"603{i:03d}",
            "name": f"下行弱股{i}",
            "close": 15.0,
            "low": 14.5,
            "ch_dir": -1,
            "ch_supp_slope_deg": -10.0,
            "ch_supp_price": 16.0,  # close < supp_price 破位
            "ch_supp_pos": 10.0,
            "Rank": 4000,
            "vol_ratio": 0.6,
            "changepercent": -3.0
        })
    df_market = pd.DataFrame(df_rows)
    df_market.set_index("code", drop=False, inplace=True)

    # 初始池子为空
    assert len(kline_cache.get_v_reversal_pool()) == 0

    # 1. 触发通道纳标扫描，限定单次最多添加 20 只
    added = kline_cache.scan_and_auto_add_uptrend_channel_stocks(df=df_market, max_add=20, max_pool_limit=100)

    # 断言：成功纳标 20 只优质上涨通道标的
    assert added == 20
    assert len(kline_cache.get_v_reversal_pool()) == 20

    # 验证添加的全部是上涨通道标的高分优选股 (603005~603024)
    pool = kline_cache.get_v_reversal_pool()
    for i in range(5, 25):
        code = f"603{i:03d}"
        assert code in pool
        flags = kline_cache.get_consolidation_flags(code)
        assert flags.get("phase") == "CONSOLIDATING"
        assert flags.get("structure") == "上涨通道"
        assert flags.get("ch_dir") == 1
        assert flags.get("name") == f"通道牛股{i}"

    # 验证下跌通道标的 (603025~603059) 绝对未被误加入
    for i in range(25, 60):
        assert f"603{i:03d}" not in pool

def test_scan_cross_sectional_and_dynamic_replacement_when_pool_full(kline_cache):
    """
    验证：
    1. 全市场截面宽表无 ch_dir 列时，依据 ma5>ma10>ma20 等多头排列与支撑识别通道；
    2. 当池子容量已达 100 只满载时，支持弹性扩容与汰弱留强，绝不锁死返回 0。
    """
    # 1. 预先将池子填满 100 只 (其中 90 只强势，10 只是 INIT 弱势标的)
    for i in range(90):
        c = f"600{i:03d}"
        kline_cache._v_reversal_pool.add(c)
        kline_cache._consolidation_flags[c] = {
            "phase": "CONSOLIDATING", "structure": "上涨通道", "ch_dir": 1
        }
    for i in range(90, 100):
        c = f"600{i:03d}"
        kline_cache._v_reversal_pool.add(c)
        kline_cache._consolidation_flags[c] = {
            "phase": "INIT", "structure": "待计算", "ch_dir": -1
        }
    
    assert len(kline_cache.get_v_reversal_pool()) == 100

    # 2. 模拟全市场宽表 (无 ch_dir 列，但有标准均线与行情指标)
    df_rows = []
    # 5 只全新牛股 (均线多头 ma5>ma10>ma20>ma60, 依托 ma20 支撑)
    for i in range(5):
        df_rows.append({
            "code": f"688{i:03d}",
            "name": f"截面多头股{i}",
            "close": 35.0,
            "open": 34.0,
            "high": 36.0,
            "low": 34.2,
            "ma5d": 34.5,
            "ma10d": 33.0,
            "ma20d": 31.0,
            "ma60d": 28.0,
            "Rank": 200 + i,
            "ratio": 2.5,
            "percent": 3.0,
            "dff3": 12.0,
            "dff2": 6.0
        })
    df_cs = pd.DataFrame(df_rows)
    df_cs.set_index("code", drop=False, inplace=True)

    # 3. 触发纳标 (池子已达 100，max_pool_limit=120)
    added = kline_cache.scan_and_auto_add_uptrend_channel_stocks(
        df=df_cs, max_add=10, max_pool_limit=120, force_replace=True
    )

    # 断言：成功纳标 5 只！不再因满额或缺 ch_dir 返回 0
    assert added == 5
    assert hasattr(added, "total_eligible")
    assert added.total_eligible == 5
    assert added.missing_ch_dir is True
    pool = kline_cache.get_v_reversal_pool()
    for i in range(5):
        c = f"688{i:03d}"
        assert c in pool
        fl = kline_cache.get_consolidation_flags(c)
        assert fl["phase"] == "CONSOLIDATING"
        assert "多头" in fl["structure"] or "通道" in fl["structure"]
        assert fl["ch_dir"] == 1


def test_scan_channel_result_breakdown_and_limit_150(capsys):
    """
    测试容量上限150与扫描结果统计：
    1. 验证符合条件总数、本次添加数、排队待添加数的计算；
    2. 验证缺失 ch_dir 时触发 logger.error 报警日志；
    3. 验证 ScanChannelResult 对象的属性访问和 int 兼容性。
    """
    kline_cache = MinuteKlineCache(simulation_mode=True)
    # 模拟池内已有 140 只
    for i in range(140):
        c = f"600{i:03d}"
        kline_cache._v_reversal_pool.add(c)
        kline_cache._consolidation_flags[c] = {"phase": "CONSOLIDATING", "structure": "上涨通道", "ch_dir": 1}

    # 构造 25 只符合上涨通道的候选股票 (无 ch_dir 模拟缺失 bug)
    df_rows = []
    for i in range(25):
        df_rows.append({
            "code": f"000{i:03d}",
            "name": f"优质通道股{i}",
            "close": 20.0,
            "low": 19.5,
            "ma5d": 19.8,
            "ma10d": 19.0,
            "ma20d": 18.0,
            "ma60d": 16.0,
            "Rank": 100 + i,
            "ratio": 2.0,
            "percent": 2.5
        })
    df_cs = pd.DataFrame(df_rows)
    df_cs.set_index("code", drop=False, inplace=True)

    import logging
    from realtime_data_service import logger as r_logger
    log_records = []
    class LogCollector(logging.Handler):
        def emit(self, record):
            log_records.append(record.getMessage())
    collector = LogCollector()
    r_logger.addHandler(collector)
    try:
        res = kline_cache.scan_and_auto_add_uptrend_channel_stocks(
            df=df_cs, max_add=30, max_pool_limit=150, force_replace=False
        )
    finally:
        r_logger.removeHandler(collector)

    # 1. 验证 int 兼容性：150 - 140 = 10，实际添加 10 只
    assert int(res) == 10
    assert res == 10

    # 2. 验证详细统计信息
    assert res.total_eligible == 25       # 全市场共发现 25 只
    assert res.added == 10                # 本次优先纳标 10 只
    assert res.pending_count == 15        # 尚有 15 只排队待添加
    assert res.cur_total == 150           # 当前总容量达到 150
    assert res.missing_ch_dir is True     # 标记基础数据缺失 ch_dir

    # 3. 验证触发了 logger.error 报警
    assert any("基础数据缺失 BUG" in msg for msg in log_records)





