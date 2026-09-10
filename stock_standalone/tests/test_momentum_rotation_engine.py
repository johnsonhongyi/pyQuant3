# -*- coding: utf-8 -*-
"""
tests/test_momentum_rotation_engine.py — T+1 满仓轮动强势快速开平仓中枢单元与集成测试
=============================================================================
验证目标：
1. 301176 逸豪新材在 2026-09-09 历史切片下精准命中【模式 1: 梯量大阳推进型】(评分 >= 80分)；
2. 603318 水发燃气在 2026-09-09 历史切片下精准命中【模式 2: 异动冲高回踩·两日VWAP平台微升蓄势反包型】(评分 >= 75分)；
3. 走弱杂毛标的 (死水织布机、高位超买、脉冲巨量出货) 100% 触发一票否决拦截；
4. 批量宽表向量化排序与空数据容错遵循固定错误结构规范。
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import numpy as np
import pandas as pd
from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df, calc_trend_channel
from ats.momentum_rotation_engine import (
    MomentumRotationEngine,
    evaluate_momentum_rotation,
    get_top_rotation_candidates
)


def test_stock_301176_hit_on_20260909():
    """验证 301176 逸豪新材在 2026-09-09 盘后切片命中【模式 1: 梯量大阳推进型】"""
    df = get_tdx_Exp_day_to_df('301176')
    assert df is not None and not df.empty, "301176 日线数据不能为空"
    assert '2026-09-09' in df.index, "必须包含 2026-09-09 数据"
    
    idx = df.index.get_loc('2026-09-09')
    sub = df.iloc[:idx+1].copy()
    sub_ch = calc_trend_channel(sub)
    last = sub_ch.iloc[-1]
    
    r = dict(last)
    r['code'] = '301176'
    r['name'] = '逸豪新材'
    r['lastp1d'] = float(sub.iloc[-2]['close'])
    r['lasto1d'] = float(sub.iloc[-2]['open'])
    r['lasth1d'] = float(sub.iloc[-2]['high'])
    r['lasth2d'] = float(sub.iloc[-3]['high'])
    r['lastl1d'] = float(sub.iloc[-2]['low'])
    r['lastl2d'] = float(sub.iloc[-3]['low'])
    r['lastv1d'] = float(sub.iloc[-2]['vol'])
    
    amount = float(r.get('amount', 0))
    vol = float(r.get('vol', 0))
    r['nclose'] = amount / vol if vol > 0 else float(r['close'])
    
    eval_res = evaluate_momentum_rotation(r)
    
    assert eval_res['is_qualified'] is True, f"301176 必须及格入选，实际: {eval_res}"
    assert eval_res['rotation_score'] >= 80.0, f"301176 评分应 >= 80，实际: {eval_res['rotation_score']}"
    assert eval_res['pattern_type'] == "PATTERN_1_STEPPED_VOLUME_LAUNCH"
    assert "极品起爆" in eval_res['signal']
    assert eval_res['metrics']['ch_pos'] < 45.0, "应处于下轨黄金伏击位"
    assert eval_res['metrics']['vol_ratio'] >= 1.2, "应为温和放量"


def test_stock_603318_hit_on_20260909():
    """验证 603318 水发燃气在 2026-09-09 命中【模式 2: 异动冲高回踩·两日VWAP平台微升蓄势反包型】"""
    df = get_tdx_Exp_day_to_df('603318')
    assert df is not None and not df.empty, "603318 日线数据不能为空"
    assert '2026-09-09' in df.index, "必须包含 2026-09-09 数据"
    
    idx = df.index.get_loc('2026-09-09')
    sub = df.iloc[:idx+1].copy()
    sub_ch = calc_trend_channel(sub)
    last = sub_ch.iloc[-1]
    p1 = sub.iloc[-2]
    
    r = dict(last)
    r['code'] = '603318'
    r['name'] = '水发燃气'
    r['lastp1d'] = float(p1['close'])
    r['lasto1d'] = float(p1['open'])
    r['lasth1d'] = float(p1['high'])
    r['lasth2d'] = float(sub.iloc[-3]['high'])
    r['lastl1d'] = float(p1['low'])
    r['lastl2d'] = float(sub.iloc[-3]['low'])
    r['lastv1d'] = float(p1['vol'])
    
    amount = float(r.get('amount', 0))
    vol = float(r.get('vol', 0))
    r['nclose'] = amount / vol if vol > 0 else float(r['close'])
    
    amt1 = float(p1.get('amount', 0))
    v1 = float(p1.get('vol', 0))
    r['last_nclose1d'] = amt1 / v1 if v1 > 0 else float(p1['close'])
    
    eval_res = evaluate_momentum_rotation(r)
    
    assert eval_res['is_qualified'] is True, f"603318 必须及格入选，实际: {eval_res}"
    assert eval_res['rotation_score'] >= 75.0, f"603318 评分应 >= 75，实际: {eval_res['rotation_score']}"
    assert eval_res['pattern_type'] == "PATTERN_2_VWAP_PLATFORM_REVERSAL", f"形态识别错误: {eval_res['pattern_type']}"
    assert "平台微升" in eval_res['signal'] or "反包" in eval_res['signal']
    assert eval_res['metrics']['ch_pos'] <= 45.0, "应处于通道下轨黄金位"
    assert eval_res['metrics']['vol_ratio'] < 1.0, "T-1日必须是地量缩量洗盘"


def test_veto_mechanisms_for_weak_stocks():
    """验证三大弱势与风险特征的硬防线一票否决"""
    # 场景 1: 死水织布机 (振幅极小 1.2%)
    dead_stock = {
        'code': '000001', 'name': '死水股',
        'close': 10.0, 'open': 10.0, 'high': 10.06, 'low': 9.95,
        'vol': 10000, 'lastv1d': 9000, 'lastp1d': 10.0,
        'ch_dir': 1, 'ch_slope_deg': 10.0, 'ch_pos': 20.0,
        'truer': 1.1, 'truer1d': 1.2
    }
    res1 = evaluate_momentum_rotation(dead_stock)
    assert res1['is_qualified'] is False, "死水织布机必须被拦截"
    assert res1['veto'] is True
    
    # 场景 2: 高位超买追高 (ch_pos = 92%)
    overbought_stock = {
        'code': '000002', 'name': '超买股',
        'close': 30.0, 'open': 29.0, 'high': 30.5, 'low': 28.5,
        'vol': 15000, 'lastv1d': 10000, 'lastp1d': 28.0,
        'ch_dir': 1, 'ch_slope_deg': 25.0, 'ch_pos': 92.0,
        'truer': 6.5, 'truer1d': 6.0
    }
    res2 = evaluate_momentum_rotation(overbought_stock)
    assert res2['is_qualified'] is False, "通道极高位超买股必须被拦截"
    assert res2['veto'] is True

    # 场景 3: 脉冲巨量对倒出货 (vol_ratio = 5.2x)
    dump_stock = {
        'code': '000003', 'name': '对倒出货股',
        'close': 15.0, 'open': 14.5, 'high': 16.0, 'low': 14.0,
        'vol': 52000, 'lastv1d': 10000, 'lastp1d': 14.0,
        'ch_dir': 1, 'ch_slope_deg': 15.0, 'ch_pos': 35.0,
        'truer': 8.0, 'truer1d': 7.0
    }
    res3 = evaluate_momentum_rotation(dump_stock)
    assert res3['is_qualified'] is False, "天量对倒出货必须被拦截"
    assert res3['veto'] is True

    # 场景 4: 002999 天禾股份真实切片 (九转9见顶 + 避雷针长上影8.9% + 触碰上轨天花板)
    tianhe_002999 = {
        'code': '002999', 'name': '天禾股份',
        'close': 7.44, 'open': 7.30, 'high': 8.10, 'low': 7.07,
        'lastp1d': 7.37, 'lasto1d': 6.70, 'lasth1d': 7.37, 'lasth2d': 6.75,
        'lastl1d': 6.67, 'lastl2d': 6.57, 'vol': 95737548, 'lastv1d': 49666769,
        'nclose': 7.55, 'last_nclose1d': 7.10, 'ch_dir': 1, 'ch_slope_deg': 35.86,
        'ch_pos': 64.13, 'ch_upper': 8.10, 'ch_mid': 6.92, 'ch_lower': 6.26,
        'truer': 13.9, 'truer1d': 10.4, 'td_sell': 9.0
    }
    res4 = evaluate_momentum_rotation(tianhe_002999)
    assert res4['is_qualified'] is False, "002999 九转9与避雷针上影线必须被一票否决"
    assert res4['veto'] is True
    assert any("九转" in r or "避雷针" in r for r in res4['veto_reasons'])


def test_universe_ranking_and_error_handling():
    """验证批量向量化排序与空输入异常容错"""
    pool = pd.DataFrame([
        {
            'code': '301176', 'name': '逸豪新材', 'close': 49.0, 'open': 47.91, 'high': 51.0, 'low': 46.6,
            'lastp1d': 46.45, 'lasto1d': 46.46, 'lasth1d': 48.5, 'lasth2d': 47.15,
            'lastl1d': 46.03, 'lastl2d': 42.70, 'vol': 11008721, 'lastv1d': 5666762,
            'nclose': 49.274, 'last_nclose1d': 47.02, 'ch_dir': 1, 'ch_slope_deg': 38.75, 'ch_pos': 6.93,
            'ch_lower': 47.93, 'ch_mid': 53.83, 'ch_upper': 63.32, 'ch_supp_price': 49.0,
            'truer': 9.4, 'truer1d': 5.4, 'td_sell': 3.0
        },
        {
            'code': '603318', 'name': '水发燃气', 'close': 9.41, 'open': 9.51, 'high': 9.70, 'low': 9.33,
            'lastp1d': 9.50, 'lasto1d': 9.10, 'lasth1d': 9.70, 'lasth2d': 9.34,
            'lastl1d': 8.99, 'lastl2d': 9.00, 'vol': 46469552, 'lastv1d': 60189007,
            'nclose': 9.47, 'last_nclose1d': 9.416, 'ch_dir': 1, 'ch_slope_deg': 25.23, 'ch_pos': 6.08,
            'ch_lower': 9.29, 'ch_mid': 10.13, 'ch_upper': 11.26, 'ch_supp_price': 9.80,
            'truer': 3.96, 'truer1d': 7.9, 'td_sell': 2.0
        },
        {
            'code': '002349', 'name': '精华制药', 'close': 8.73, 'open': 9.0, 'high': 9.0, 'low': 8.36,
            'lastp1d': 9.26, 'lasto1d': 9.1, 'lasth1d': 9.3, 'lasth2d': 9.4,
            'lastl1d': 8.5, 'lastl2d': 8.6, 'vol': 50000, 'lastv1d': 60000,
            'nclose': 8.64, 'last_nclose1d': 8.0, 'ch_dir': -1, 'ch_slope_deg': -5.0, 'ch_pos': 75.0,
            'ch_lower': 8.0, 'ch_mid': 8.5, 'ch_upper': 9.0, 'truer': 3.0, 'td_sell': 7.0
        }
    ])
    
    top_ranked = get_top_rotation_candidates(pool, top_n=3)
    assert len(top_ranked) >= 2, "必须选出逸豪新材与水发燃气"
    codes = top_ranked['code'].tolist()
    assert '301176' in codes and '603318' in codes, "301176与603318必须同时入选"
    assert '002349' not in codes, "走弱股002349必须被淘汰"

    # 空输入容错
    empty_res = get_top_rotation_candidates(pd.DataFrame())
    assert isinstance(empty_res, pd.DataFrame)
    assert '__error__' in empty_res.attrs
    assert empty_res.attrs['__error__']['code'] == 'EMPTY_UNIVERSE'
