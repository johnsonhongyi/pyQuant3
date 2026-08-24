import os
import sys
import time
import json
import threading
import pytest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.intraday_strategy_engine import IntradayStrategyEngine
from sys_utils import get_app_root


def test_tmp_file_auto_cleanup_on_startup():
    """测试 1: 引擎启动时自动检测并清理历史遗留的 .tmp 文件"""
    config_dir = os.path.join(get_app_root(), "config")
    dummy_tmp = os.path.join(config_dir, "intraday_strategy_state_cache.json.tmp_test99999")
    with open(dummy_tmp, "w", encoding="utf-8") as f:
        f.write('{"test": "tmp_garbage"}')
    assert os.path.exists(dummy_tmp)

    engine = IntradayStrategyEngine.get_instance()
    engine._cleanup_legacy_tmp_files()
    assert not os.path.exists(dummy_tmp), "引擎未能在启动自愈中清理历史 .tmp 垃圾临时文件！"


def test_no_disk_write_during_high_freq_eval():
    """测试 2: 高频调用 hydrate_from_intraday_df 与 evaluate_seven_nodes 期间不触发写盘，不产生 .tmp 文件"""
    engine = IntradayStrategyEngine.get_instance()
    cache_file = engine._get_cache_filepath()
    
    # 记录初始状态
    initial_mtime = os.path.getmtime(cache_file) if os.path.exists(cache_file) else 0.0
    time.sleep(0.05)

    # 模拟 240 分钟高频行情推送
    df_min = pd.DataFrame([
        {"time": "09:30", "open": 200.0, "close": 202.0, "high": 203.0, "low": 199.0, "turnover": 5.0, "vwap": 201.0, "amount": 1000000},
        {"time": "09:31", "open": 202.0, "close": 204.0, "high": 205.0, "low": 201.0, "turnover": 6.0, "vwap": 202.5, "amount": 1200000},
    ])
    df_min.set_index("time", inplace=True)

    # 连续调用 10 次分时快照更新
    for _ in range(10):
        engine.hydrate_from_intraday_df("688826", df_min, open_price=200.0)
        engine.evaluate_seven_nodes(
            code="688826",
            current_time_str="09:35",
            open_price=200.0,
            price=204.0,
            high_price=205.0,
            low_price=199.0,
            vwap=202.5,
            turnover_rate=6.0,
            amount=1200000
        )

    # 验证期间没有修改 cache_file 的 mtime，且没有任何 .tmp 文件残留
    if os.path.exists(cache_file) and initial_mtime > 0:
        current_mtime = os.path.getmtime(cache_file)
        assert current_mtime == initial_mtime, "高频计算或分时拉取期间违规触发了磁盘写入！"

    config_dir = os.path.join(get_app_root(), "config")
    tmp_files = [f for f in os.listdir(config_dir) if ".tmp" in f]
    assert len(tmp_files) == 0, f"高频计算期间产生了残留临时文件: {tmp_files}"


def test_dirty_check_and_atomic_persistence():
    """测试 3: 仅在参数变动或人工覆盖时标记 dirty 并持久化，写入后 tmp 文件立即销毁"""
    engine = IntradayStrategyEngine.get_instance()
    cache_file = engine._get_cache_filepath()

    # 人工修改参数
    engine.set_node_custom_param("688826", "node_1_auction", 215.50)
    assert not engine._is_dirty, "保存成功后 _is_dirty 应自动重置为 False！"
    
    # 验证磁盘数据已更新
    with open(cache_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert saved_data["stocks"]["688826"]["node_custom_params"]["node_1_auction"] == 215.50

    # 再次无变动调用 save_intraday_cache(force=False)，由于 hash 相同，直接短路
    mtime_before = os.path.getmtime(cache_file)
    time.sleep(0.05)
    engine.save_intraday_cache(force=False)
    mtime_after = os.path.getmtime(cache_file)
    assert mtime_before == mtime_after, "无变动时不应触发磁盘写！"

    # 检查 config 目录无任何临时文件残留
    config_dir = os.path.join(get_app_root(), "config")
    tmp_files = [f for f in os.listdir(config_dir) if ".tmp" in f]
    assert len(tmp_files) == 0, f"写盘后发现残留临时文件: {tmp_files}"


def test_throttled_persistence_and_closing_save():
    """测试 4: 节流防抖机制（60s 节流）与收盘后持久化"""
    engine = IntradayStrategyEngine.get_instance()
    cache_file = engine._get_cache_filepath()

    # 标记为 dirty
    engine.mark_dirty()
    assert engine._is_dirty

    # 节流间隔设为 5 秒，若未到时间则不写盘
    engine._last_save_time = time.time()
    res1 = engine.save_intraday_cache_throttled(interval_sec=5.0)
    assert res1 is True
    assert engine._is_dirty is True, "节流时间内不应清除 dirty 标记"

    # 模拟超过节流时间后触发
    engine._last_save_time = time.time() - 10.0
    res2 = engine.save_intraday_cache_throttled(interval_sec=5.0)
    assert res2 is True
    assert engine._is_dirty is False, "节流触发后 _is_dirty 应成功清零！"

    # 模拟收盘 15:00 之后的自动持久化
    engine.mark_dirty()
    engine.evaluate_seven_nodes(
        code="688826",
        current_time_str="15:00",
        open_price=200.0,
        price=204.0,
        high_price=205.0,
        low_price=199.0,
        vwap=202.5,
        turnover_rate=6.0,
        amount=1200000
    )
    assert engine._is_dirty is False, "收盘 15:00 时应自动统一持久化！"


def test_thread_safe_concurrent_access():
    """测试 5: 多线程高并发读写与持久化线程安全性"""
    engine = IntradayStrategyEngine.get_instance()
    errors = []

    def worker_modify(val):
        try:
            for _ in range(20):
                engine.set_node_custom_param("688826", "node_1_auction", float(val))
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    def worker_read():
        try:
            for _ in range(20):
                engine.save_intraday_cache_throttled(interval_sec=0.01)
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=worker_modify, args=(210 + i,)) for i in range(5)
    ] + [
        threading.Thread(target=worker_read) for _ in range(5)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"多线程并发读写出现异常: {errors}"
