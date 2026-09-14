# -*- coding: utf-8 -*-
"""
tests/test_multiday_feature_store.py
全市场收盘精确换手率等多日缺失特征自动化持久化与初始化挂载专项测试 (SSOT)

测试覆盖:
1. 扁平单表写入、多日去重与动态滑动窗口截断 (15天截断保留最新9天)；
2. 宽表 Pivot 倒排重塑 (ratio1 对应最新日，ratio2 对应前一日，直至 ratio9)；
3. 缺失股票与冷启动数据不全时的优雅降级 (默认值填充，杜绝 KeyError)；
4. generate_df_vect_daily_features 与 calc_trend_channel 特征注入连通性；
5. PandasQueryEngine 查询引擎对 ratio1~9, turnover1~9, 换手率1~9, vol_ratio1~9 的完整支持。
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from JSONData.multiday_feature_store import (
    archive_daily_features, get_multiday_features_wide,
    inject_multiday_features_to_row, clear_multiday_cache,
    get_multiday_store_path, HDF5_TABLE_NAME
)
from JSONData import tdx_hdf5_api as h5a


@pytest.fixture
def temp_h5_store():
    """临时独立 HDF5 存储路径 fixture (避开 Windows Ramdisk pathlib resolve 限制)"""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    test_h5 = os.path.join(test_dir, "test_multiday_store_temp.h5")
    clear_multiday_cache()
    yield test_h5
    clear_multiday_cache()
    if os.path.exists(test_h5):
        try: os.remove(test_h5)
        except Exception: pass


def test_archive_and_sliding_window_trim(temp_h5_store):
    """验证扁平单表持久化写入、幂等去重与滑动窗口截断 (15天修剪为9天)"""
    dates = [f"2026-09-{i:02d}" for i in range(1, 16)] # 15 天历史数据
    codes = ["000001", "000002", "300563", "603601"]

    # 1. 模拟连续写入 15 个交易日数据
    for idx, d in enumerate(dates):
        df_day = pd.DataFrame([
            {'code': c, 'ratio': round(1.0 + idx * 0.5 + c_idx, 2), 'vol_ratio': round(1.0 + idx * 0.1, 2)}
            for c_idx, c in enumerate(codes)
        ])
        ok = archive_daily_features(df_day, max_days=9, date_str=d, store_path=temp_h5_store)
        assert ok is True, f"写入 {d} 失败"

    # 2. 验证扁平表中保留的唯一交易日数量严格等于 9 天
    with h5a.SafeHDFStore(temp_h5_store, mode='r') as store:
        df_flat = store.get(HDF5_TABLE_NAME)
    
    unique_dates = sorted(df_flat['date'].unique())
    assert len(unique_dates) == 9, f"滑动截断后应保留 9 天，实际: {len(unique_dates)}"
    assert unique_dates[0] == "2026-09-07", f"最早的一天应为 2026-09-07，实际: {unique_dates[0]}"
    assert unique_dates[-1] == "2026-09-15", f"最新的一天应为 2026-09-15，实际: {unique_dates[-1]}"
    # 验证最早的 6 天 (09-01 ~ 09-06) 被成功淘汰
    for old_d in [f"2026-09-{i:02d}" for i in range(1, 7)]:
        assert old_d not in unique_dates, f"老旧日期 {old_d} 未被淘汰！"

    # 3. 验证幂等性：同一天重复提交不会膨胀行数
    count_before = len(df_flat)
    df_repeat = pd.DataFrame([
        {'code': c, 'ratio': 99.0, 'vol_ratio': 2.0}
        for c in codes
    ])
    archive_daily_features(df_repeat, max_days=9, date_str="2026-09-15", store_path=temp_h5_store)
    with h5a.SafeHDFStore(temp_h5_store, mode='r') as store:
        df_flat_after = store.get(HDF5_TABLE_NAME)
    assert len(df_flat_after) == count_before, "重复写入当天数据行数膨胀，未正确去重更新！"
    # 验证更新为了最新值 99.0
    val_updated = df_flat_after[df_flat_after['code'] == '000001']['ratio'].iloc[-1]
    assert val_updated == 99.0, "幂等更新未生效"


def test_wide_table_pivot_and_reverse_mapping(temp_h5_store):
    """验证宽表重塑：ratio1 对应最新日期，ratio2 对应前一日，直至 ratio9"""
    dates = [f"2026-09-{i:02d}" for i in range(1, 10)] # 9 天
    codes = ["000001", "300563"]

    for idx, d in enumerate(dates):
        # 000001 的 ratio 每日递增: 1.0, 2.0, 3.0 ... 9.0 (09-09 为 9.0, 09-08 为 8.0)
        df_day = pd.DataFrame([
            {'code': '000001', 'ratio': float(idx + 1), 'vol_ratio': float(idx + 1) * 0.5},
            {'code': '300563', 'ratio': float(idx + 1) * 2.0, 'vol_ratio': 1.2}
        ])
        archive_daily_features(df_day, max_days=9, date_str=d, store_path=temp_h5_store)

    wide = get_multiday_features_wide(max_days=9, store_path=temp_h5_store, force_reload=True)
    assert not wide.empty, "宽表重塑结果不能为空"
    assert "000001" in wide.index
    assert "300563" in wide.index

    # 验证倒排对应关系:
    # ratio1 -> 最新日期 (2026-09-09, idx=8) -> 9.0
    # ratio2 -> 前一天 (2026-09-08, idx=7) -> 8.0
    # ratio9 -> 最早一天 (2026-09-01, idx=0) -> 1.0
    assert float(wide.loc["000001", "ratio1"]) == 9.0
    assert float(wide.loc["000001", "ratio2"]) == 8.0
    assert float(wide.loc["000001", "ratio3"]) == 7.0
    assert float(wide.loc["000001", "ratio9"]) == 1.0

    # 验证量比倒排对应关系
    assert float(wide.loc["000001", "vol_ratio1"]) == 4.5
    assert float(wide.loc["000001", "vol_ratio2"]) == 4.0
    assert float(wide.loc["000001", "vol_ratio9"]) == 0.5

    # 验证日内 TTL 缓存复用 (第二次调用 0ms 返回)
    wide_cached = get_multiday_features_wide(max_days=9, store_path=temp_h5_store, force_reload=False)
    assert wide_cached is wide, "日内调用必须直接返回缓存引用"


def test_row_injection_and_cold_start_graceful_fallback(temp_h5_store):
    """验证单股特征注入与冷启动优雅降级"""
    df_day = pd.DataFrame([
        {'code': '000001', 'ratio': 3.5, 'vol_ratio': 1.2}
    ])
    archive_daily_features(df_day, max_days=9, date_str="2026-09-12", store_path=temp_h5_store)
    wide = get_multiday_features_wide(max_days=9, store_path=temp_h5_store, force_reload=True)

    # 1. 已知股票特征注入
    feat_known = {}
    inject_multiday_features_to_row("000001", feat_known, wide_df=wide, max_days=9)
    assert feat_known["ratio1"] == 3.5
    assert feat_known["vol_ratio1"] == 1.2
    # 历史缺失天数平滑填充
    for d in range(2, 10):
        assert f"ratio{d}" in feat_known
        assert f"vol_ratio{d}" in feat_known

    # 2. 未知股票 (不在库中) 优雅降级
    feat_unknown = {}
    inject_multiday_features_to_row("688999", feat_unknown, wide_df=wide, max_days=9)
    assert feat_unknown["ratio1"] == 0.0
    assert feat_unknown["vol_ratio1"] == 1.0

    # 3. 库文件完全不存在时的冷启动兜底
    feat_cold = {}
    inject_multiday_features_to_row("000001", feat_cold, wide_df=pd.DataFrame(), max_days=9)
    assert feat_cold["ratio1"] == 0.0
    assert feat_cold["vol_ratio1"] == 1.0


def test_tdx_data_day_feature_integration(temp_h5_store):
    """验证 tdx_data_Day.py 中特征提取与 calc_trend_channel 的多日换手率连通性"""
    from JSONData.tdx_data_Day import generate_df_vect_daily_features, calc_trend_channel

    # 模拟写入 300563 神宇股份历史换手率
    df_day = pd.DataFrame([
        {'code': '300563', 'ratio': 2.8, 'vol_ratio': 0.9}
    ])
    archive_daily_features(df_day, max_days=9, date_str="2026-09-12", store_path=temp_h5_store)

    # 模拟构建用于特征提取的 DataFrame
    df_mock = pd.DataFrame([{
        'code': '300563',
        'open': 10.0, 'high': 11.0, 'low': 9.8, 'close': 10.5, 'vol': 1000,
        'ratio': 2.8, 'vol_ratio': 0.9
    }]).set_index('code')

    # 测试 generate_df_vect_daily_features 提取结果包含 ratio1 ~ ratio9
    feats = generate_df_vect_daily_features(df_mock, lastdays=9)
    assert len(feats) == 1
    f0 = feats[0]
    for d in range(1, 10):
        assert f'ratio{d}' in f0, f"特征字典缺失 ratio{d}"
        assert f'vol_ratio{d}' in f0, f"特征字典缺失 vol_ratio{d}"

    # 测试 calc_trend_channel 写入 DataFrame 包含 ratio1 ~ ratio9
    df_kline = pd.DataFrame({
        'open': np.linspace(10, 15, 30),
        'high': np.linspace(10.5, 15.5, 30),
        'low': np.linspace(9.5, 14.5, 30),
        'close': np.linspace(10, 15, 30),
        'vol': np.full(30, 5000),
        'code': np.full(30, '300563'),
        'ratio': np.full(30, 2.8)
    })
    df_kline.name = '300563'
    df_out = calc_trend_channel(df_kline)
    for d in range(1, 10):
        assert f'ratio{d}' in df_out.columns, f"calc_trend_channel 输出缺失 ratio{d}"
        assert f'vol_ratio{d}' in df_out.columns, f"calc_trend_channel 输出缺失 vol_ratio{d}"


def test_query_engine_multiday_ratio_syntax():
    """验证 PandasQueryEngine 对 ratio1~9, turnover1~9, 换手率1~9 的语法解析与执行"""
    from query_engine_util import PandasQueryEngine
    qe = PandasQueryEngine()

    df_test = pd.DataFrame([{
        'code': '300563',
        'ratio1': 2.5,   # 昨日换手 2.5% (地量洗盘)
        'ratio2': 2.1,   # 前天换手 2.1%
        'vol_ratio1': 2.2,
        'ch_dir': 1.0,
        'ch_pos': 20.0,
        'close': 10.0
    }]).set_index('code')

    # 测试 ratio1 < 3.0 and ratio2 < 3.0
    q1 = "ratio1 < 3.0 and ratio2 < 3.0 and vol_ratio1 > 2.0"
    res1 = qe.execute(df_test, q1)
    assert len(res1) == 1, "query ratio1/ratio2 应该精准命中"

    # 测试中文同义词: 换手率1 < 3.0
    q2 = "换手率1 < 3.0 and 换手率2 < 3.0"
    res2 = qe.execute(df_test, q2)
    assert len(res2) == 1, "query 换手率1/换手率2 应该精准命中"

    # 测试 turnover 同义词: turnover1 < 3.0
    q3 = "turnover1 < 3.0 and turnover2 < 3.0"
    res3 = qe.execute(df_test, q3)
    assert len(res3) == 1, "query turnover1/turnover2 应该精准命中"

    # 测试不满足条件时安全排除
    q4 = "ratio1 > 5.0"
    res4 = qe.execute(df_test, q4)
    assert len(res4) == 0, "不满足条件的标的应被过滤"


def test_singleton_shared_dict_cache_and_batch_loop_performance(temp_h5_store):
    """验证单例共享内存字典缓存及全市场循环批量注入极致性能"""
    from JSONData.multiday_feature_store import (
        get_multiday_features_dict, clear_multiday_cache, inject_multiday_features_to_row
    )
    from JSONData.tdx_data_Day import generate_df_vect_daily_features, generate_df_vect_daily_features_lastday
    import time

    clear_multiday_cache()

    # 1. 模拟写入全市场 100 只股票的多日特征数据
    records = []
    for c in range(100):
        c_str = f"{c:06d}"
        records.append({'code': c_str, 'ratio': float(c % 10 + 1), 'vol_ratio': 1.1})
    df_market = pd.DataFrame(records)
    archive_daily_features(df_market, max_days=9, date_str="2026-09-12", store_path=temp_h5_store)

    # 2. 验证单例共享内存字典读取与单例复用
    d1 = get_multiday_features_dict(max_days=9, store_path=temp_h5_store)
    assert isinstance(d1, dict)
    assert len(d1) == 100
    assert "000001" in d1
    assert "ratio1" in d1["000001"]

    # 再次读取必须命中单例引用
    d2 = get_multiday_features_dict(max_days=9, store_path=temp_h5_store)
    assert d1 is d2, "单例共享内存字典必须保持同一引用"

    # 3. 模拟全市场 5000 只股票的大批量特征提取性能压测
    mock_codes = [f"{i:06d}" for i in range(5000)]
    df_big = pd.DataFrame({
        'code': mock_codes,
        'open': np.full(5000, 10.0),
        'high': np.full(5000, 11.0),
        'low': np.full(5000, 9.5),
        'close': np.full(5000, 10.5),
        'vol': np.full(5000, 1000),
        'name': mock_codes
    }).set_index('code')

    t0 = time.time()
    feats = generate_df_vect_daily_features(df_big, lastdays=9)
    elapsed_ms = (time.time() - t0) * 1000.0

    assert len(feats) == 5000
    # 验证提取出的数据正确
    assert feats[1]['ratio1'] == 2.0  # 1 % 10 + 1 = 2
    assert feats[10]['ratio1'] == 1.0 # 10 % 10 + 1 = 1
    # 未收录在 100 只库里的股票安全兜底为 0.0
    assert feats[200]['ratio1'] == 0.0
    assert feats[200]['vol_ratio1'] == 1.0

    # 4. 验证 generate_df_vect_daily_features_lastday 同样支持单例共享内存极速注入
    feats_last = generate_df_vect_daily_features_lastday(df_big.iloc[:50], lastdays=9)
    assert len(feats_last) == 50
    assert feats_last[1]['ratio1'] == 2.0


def test_clean_and_repair_multiday_store(temp_h5_store):
    """验证 clean_and_repair_multiday_store 自动清理非交易日脏数据并保留合法交易日"""
    from JSONData.multiday_feature_store import clean_and_repair_multiday_store

    # 1. 模拟写入一个真实交易日 (2026-09-11) 与两个非法周末日期 (2026-09-12, 2026-09-13)
    df_valid = pd.DataFrame([{'code': '688151', 'ratio': 3.43, 'vol_ratio': 1.0}])
    df_weekend1 = pd.DataFrame([{'code': '688151', 'ratio': 1.80, 'vol_ratio': 1.0}])
    df_weekend2 = pd.DataFrame([{'code': '688151', 'ratio': 1.80, 'vol_ratio': 1.0}])

    archive_daily_features(df_valid, date_str="2026-09-11", store_path=temp_h5_store)
    archive_daily_features(df_weekend1, date_str="2026-09-12", store_path=temp_h5_store)
    archive_daily_features(df_weekend2, date_str="2026-09-13", store_path=temp_h5_store)

    # 检查写入前包含非法日期
    with h5a.SafeHDFStore(temp_h5_store, mode='r') as store:
        df_dirty = store.get(HDF5_TABLE_NAME)
    dirty_dates = df_dirty['date'].unique().tolist()
    assert "2026-09-12" in dirty_dates
    assert "2026-09-13" in dirty_dates

    # 2. 执行自愈清洗
    res = clean_and_repair_multiday_store(store_path=temp_h5_store, sync_from_latest_close=False)
    assert res['success'] is True
    assert "2026-09-12" in res['cleaned_invalid_dates']
    assert "2026-09-13" in res['cleaned_invalid_dates']

    # 3. 验证清洗后数据库仅保留 2026-09-11，且换手率为真实的 3.43
    with h5a.SafeHDFStore(temp_h5_store, mode='r') as store:
        df_clean = store.get(HDF5_TABLE_NAME)
    clean_dates = df_clean['date'].unique().tolist()
    assert "2026-09-12" not in clean_dates
    assert "2026-09-13" not in clean_dates
    assert "2026-09-11" in clean_dates
    assert round(float(df_clean[df_clean['code'] == '688151']['ratio'].iloc[0]), 2) == 3.43


def test_anti_regression_low_quality_coverage_protection(temp_h5_store):
    """验证防倒退保护：早盘残缺低质数据无法覆盖已有的优质收盘数据"""
    # 1. 模拟写入已收盘全量数据 (平均换手率 3.5%)
    records_good = [{'code': f"{i:06d}", 'ratio': 3.5, 'vol_ratio': 1.0} for i in range(600)]
    df_good = pd.DataFrame(records_good)
    archive_daily_features(df_good, date_str="2026-09-11", store_path=temp_h5_store)

    # 2. 模拟早盘半天快照 (平均换手率仅 1.0%，低于 3.5% 的 70%)
    records_bad = [{'code': f"{i:06d}", 'ratio': 1.0, 'vol_ratio': 0.8} for i in range(600)]
    df_bad = pd.DataFrame(records_bad)
    ok = archive_daily_features(df_bad, date_str="2026-09-11", store_path=temp_h5_store)
    # 防倒退守卫应拦截此次覆盖
    assert ok is False, "早盘低换手率数据应被防倒退机制拦截"

    # 验证数据库中仍保持原有的 3.5%
    with h5a.SafeHDFStore(temp_h5_store, mode='r') as store:
        df_check = store.get(HDF5_TABLE_NAME)
    assert abs(float(df_check['ratio'].mean()) - 3.5) < 1e-4


def test_anti_regression_zero_vol_ratio_protection(temp_h5_store):
    """
    防回归专项测试：
    当传入的 DataFrame 中存在局部残缺的 vol_ratio (存在大量 0.0)，
    archive_daily_features 必须能自动穿透识别 volume 或 vol/last6vol，
    且终极兜底确保任何入库记录的 vol_ratio 绝不出现 <= 0.05 的 0 值。
    """
    n_stocks = 200
    mock_records = []
    for i in range(n_stocks):
        code = f"{i:06d}"
        # 模拟 70% 股票被错误置为 vol_ratio = 0.0 (如动量选股残留)
        is_partial = (i % 3 != 0)
        vr_val = 0.0 if is_partial else 1.5
        mock_records.append({
            'code': code,
            'ratio': round(1.0 + i * 0.05, 2),
            'vol_ratio': vr_val,
            'volume': 1.2,          # 真实的虚拟量比强度
            'vol': 100000.0,
            'last6vol': 90000.0     # 真实量能比 1.11
        })
    df_partial = pd.DataFrame(mock_records)

    ok = archive_daily_features(df_partial, date_str="2026-09-14", store_path=temp_h5_store)
    assert ok is True

    # 验证持久化库中的数据
    with h5a.SafeHDFStore(temp_h5_store, mode='r') as store:
        df_stored = store.get(HDF5_TABLE_NAME)

    assert len(df_stored) == n_stocks
    zero_cnt = (df_stored['vol_ratio'] <= 0.05).sum()
    assert zero_cnt == 0, f"持久化库中不应存在归零的 vol_ratio，但发现了 {zero_cnt} 条！"
    # 验证被修复的股票数值在合理区间
    assert (df_stored['vol_ratio'] >= 0.1).all()


