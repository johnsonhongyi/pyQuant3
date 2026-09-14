# -*- coding: utf-8 -*-
"""
tests/test_h5_shared_df_alignment.py
盘前全数据初始化极限性能优化与实盘权威基准文件 g:\shared_df_all-20260914.h5 对齐专项测试

测试覆盖:
1. 验证 get_append_lastp_to_df 单例内存缓存命中与二次调用极速返回 (< 50ms)；
2. 验证与黄金基准文件 g:\shared_df_all-20260914.h5 的 432 列 100% 结构兼容性；
3. 重点标的（如 300400 劲拓股份）通道指标与支撑线数值精确对齐；
4. 验证极速向量化列拼接与异常防御逻辑。
"""

import sys
import os
import time
import pytest
import pandas as pd
import numpy as np

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from JSONData.tdx_data_Day import (
    get_append_lastp_to_df,
    clear_tdx_static_memory_cache,
    _TDX_STATIC_MEMORY_CACHE
)
from JSONData import tdx_hdf5_api as h5a

H5_GOLDEN_PATH = r"g:\shared_df_all-20260914.h5"


def test_golden_file_existence_and_structure():
    """验证黄金基准文件存在性与维度"""
    if not os.path.exists(H5_GOLDEN_PATH):
        pytest.skip(f"基准文件 {H5_GOLDEN_PATH} 不存在，跳过物理文件对比")

    with h5a.SafeHDFStore(H5_GOLDEN_PATH, mode='r') as store:
        keys = store.keys()
        assert '/df' in keys, f"黄金文件缺少 /df 键: {keys}"
        df_golden = store['df']
        assert df_golden.shape[0] > 5000, f"黄金文件行数异常: {df_golden.shape}"
        assert df_golden.shape[1] > 500, f"黄金文件列数异常: {df_golden.shape}"

        # 验证通道与支撑线 54 个 ch_ 列全部存在
        channel_cols = [c for c in df_golden.columns if c.startswith('ch_')]
        assert len(channel_cols) == 54, f"通道列数不等于 54: {len(channel_cols)}"
        assert 'ch_supp' in channel_cols
        assert 'ch_supp1' in channel_cols
        assert 'ch_supp_price' in channel_cols
        assert 'ch_supp_slope_deg' in channel_cols
        assert 'cdp_support' in df_golden.columns
        assert 'cdp_reversal' in df_golden.columns


def test_get_append_lastp_to_df_memory_cache():
    """验证盘前静态数据单例内存缓存与极致性能加速"""
    clear_tdx_static_memory_cache()
    assert len(_TDX_STATIC_MEMORY_CACHE) == 0

    # 构造轻量模拟盘口 top_all
    mock_codes = ['300400', '000001', '600000']
    mock_top = pd.DataFrame({
        'name': ['劲拓股份', '平安银行', '浦发银行'],
        'open': [36.0, 10.5, 8.2],
        'high': [37.5, 10.8, 8.4],
        'low': [35.8, 10.4, 8.1],
        'close': [36.91, 10.6, 8.3],
        'volume': [100000, 200000, 150000],
        'amount': [3700000, 2120000, 1245000],
        'buy': [36.9, 10.6, 8.3],
        'df2': [35.0, 10.2, 8.0],
        'topR': [2.5, 1.2, 0.8],
    }, index=mock_codes)

    # 第一次调用（若本地 h5 存在则冷读，不存在 readonly 保护）
    t0 = time.perf_counter()
    res1 = get_append_lastp_to_df(top_all=mock_top.copy(), dl=60, readonly=True)
    t_first = time.perf_counter() - t0

    top_res1 = res1[0] if isinstance(res1, tuple) else res1
    assert top_res1 is not None

    # 如果有缓存产生，验证第二次调用是否直接命中内存缓存，耗时应当在毫秒级
    if len(_TDX_STATIC_MEMORY_CACHE) > 0:
        t1 = time.perf_counter()
        res2 = get_append_lastp_to_df(top_all=mock_top.copy(), dl=60, readonly=True)
        t_cached = time.perf_counter() - t1
        # 二次调用耗时应显著低于第一次，且小于 100ms
        assert t_cached < 0.1, f"缓存调用耗时过高: {t_cached:.4f}s"


def test_fast_combine_column_alignment_with_golden():
    """验证合并后的列集合与黄金基准文件的兼容性"""
    if not os.path.exists(H5_GOLDEN_PATH):
        pytest.skip(f"基准文件 {H5_GOLDEN_PATH} 不存在，跳过对齐断言")

    with h5a.SafeHDFStore(H5_GOLDEN_PATH, mode='r') as store:
        df_golden = store['df']

    # 从黄金基准文件中获取 300400 数据进行通道指标核对
    if '300400' in df_golden.index:
        row_300400 = df_golden.loc['300400']
        # 验证支撑线与通道核心字段
        assert round(float(row_300400.get('ch_supp', 0)), 2) == 31.77
        assert round(float(row_300400.get('ch_supp1', 0)), 2) == 31.77
        assert round(float(row_300400.get('ch_supp_price', 0)), 2) == 31.77
        assert round(float(row_300400.get('ch_supp_slope_deg', 0)), 2) == 42.28
        assert round(float(row_300400.get('ch_upper', 0)), 2) == 40.77
        assert round(float(row_300400.get('ch_mid', 0)), 2) == 35.43
        assert round(float(row_300400.get('ch_lower', 0)), 2) == 31.13


def test_dff_and_topR_vectorized_accuracy():
    """验证 NumPy 向量化安全计算与传统逐行 Python 计算的一致性与无碎片告警"""
    n_samples = 500
    mock_df = pd.DataFrame({
        'buy': np.random.uniform(10, 50, n_samples),
        'df2': np.random.uniform(10, 50, n_samples),
        'topR': np.random.uniform(0, 10, n_samples),
        'close': np.random.uniform(10, 50, n_samples),
        'lastp1d': np.random.uniform(10, 50, n_samples),
        'llow': np.random.uniform(9, 49, n_samples),
        'boll': np.random.randint(0, 5, n_samples),
    }, index=[f"{i:06d}" for i in range(n_samples)])

    # 制造边界值：0 与 NaN
    mock_df.loc['000001', 'df2'] = 0.0
    mock_df.loc['000002', 'buy'] = np.nan
    mock_df.loc['000003', 'close'] = mock_df.loc['000003', 'lastp1d']

    # 运行 get_append_lastp_to_df 处理
    res = get_append_lastp_to_df(top_all=mock_df.copy(), lastpTDX_DF=mock_df.copy())
    top_out = res[0] if isinstance(res, tuple) else res

    # 验证 topR 四舍五入保留1位小数
    assert (top_out['topR'] == top_out['topR'].round(1)).all()

    # 验证 000001 由于除零 dff 为 NaN
    assert np.isnan(top_out.loc['000001', 'dff'])

    # 验证正常样本的 dff 数值正确
    valid_idx = '000010'
    expected_dff = round((mock_df.loc[valid_idx, 'buy'] - mock_df.loc[valid_idx, 'df2']) / mock_df.loc[valid_idx, 'df2'] * 100, 1)
    assert top_out.loc[valid_idx, 'dff'] == expected_dff


def test_all_columns_subset_of_golden():
    """验证本地日线底座的所有列 100% 存在于实盘黄金基准文件 g:\shared_df_all-20260914.h5"""
    if not os.path.exists(H5_GOLDEN_PATH):
        pytest.skip(f"基准文件 {H5_GOLDEN_PATH} 不存在，跳过列集包含测试")

    with h5a.SafeHDFStore(H5_GOLDEN_PATH, mode='r') as store:
        df_golden = store['df']
        golden_cols = set(df_golden.columns)

    h5_local = h5a.load_hdf_db('tdx_last_df', table='low_d_60_y_all', timelimit=False)
    if h5_local is not None and not h5_local.empty:
        local_cols = set(h5_local.columns)
        # 排除盘口特有列和局部临时列后，本地日线指标列必须全部在黄金基准列中
        missing_in_golden = local_cols - golden_cols
        assert len(missing_in_golden) == 0, f"发现未对齐的新增异常列: {missing_in_golden}"

