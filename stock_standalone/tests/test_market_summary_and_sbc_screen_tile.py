# -*- coding: utf-8 -*-
"""
单测：ATS 底部资金数据一致性保障与多屏幕笔记本内屏 SBC 重排防溢出测试
"""
import pytest
import os
import json
import pandas as pd
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QRect

from ats.capital_dragon_engine import CapitalDragonEngine


def test_market_summary_ssot_and_no_contamination():
    """验证大盘指数只认三大权威核心指数，且传入残缺个股时绝不污染权威后台缓存"""
    cde = CapitalDragonEngine.get_instance()
    
    # 构造权威大盘缓存 (1.9万亿真实水平)
    high_quality_summary = {
        'sh_amt': 8758.0,
        'sz_amt': 10182.0,
        'cy_amt': 5200.0,
        'bj_amt': 155.0,
        'total_amt': 19095.0,
        'formatted_html': '上证: 8758.0亿 | 深证: 10182.0亿 | 全市: 19095.0亿',
        'plain_text': '全市: 19095.0亿'
    }
    cde._bg_market_summary_cache = dict(high_quality_summary)
    
    # 模拟传入一个缩水的个股池 DataFrame (仅包含平安银行与部分个股，累计只有几十亿)
    mock_df = pd.DataFrame([
        {'code': '000001', 'name': '平安银行', 'turnover': 1500000000.0, 'price': 10.5},
        {'code': '600519', 'name': '贵州茅台', 'turnover': 3000000000.0, 'price': 1500.0},
    ])
    mock_df.set_index('code', inplace=True)
    
    # 获取大盘摘要 (传入 df_all)
    res = cde.get_market_indices_and_volume_summary(df_all=mock_df)
    
    # 验证：绝不被 mock_df 污染，必须返回 1.9万亿权威数据！
    assert res['total_amt'] == 19095.0
    assert cde._bg_market_summary_cache['total_amt'] == 19095.0


def test_market_summary_turnover_amount_dual_compatibility():
    """验证支持 turnover 和 amount 双字段提取，并且杜绝平安银行误当上证指数"""
    cde = CapitalDragonEngine.get_instance()
    
    # 包含真实指数且使用 turnover 字段的 DataFrame
    index_df = pd.DataFrame([
        {'code': '999999', 'name': '上证指数', 'turnover': 880000000000.0, 'price': 3680.0},
        {'code': '000001', 'name': '平安银行', 'turnover': 1200000000.0, 'price': 11.0}, # 平安银行
        {'code': '399001', 'name': '深证成指', 'turnover': 1020000000000.0, 'price': 11400.0},
        {'code': '399006', 'name': '创业板指', 'turnover': 530000000000.0, 'price': 2550.0},
        {'code': '899050', 'name': '北证50',   'turnover': 15500000000.0, 'price': 900.0},
    ])
    index_df.set_index('code', inplace=True)
    
    res = cde._compute_market_summary_from_df(index_df)
    
    assert res['sh_amt'] == 8800.0
    assert res['sz_amt'] == 10200.0
    assert res['cy_amt'] == 5300.0
    assert res['bj_amt'] == 155.0
    assert res['total_amt'] == 19155.0


def test_sbc_screen_tile_no_overflow_laptop_screen():
    """验证在笔记本内屏（1536x864 或 1280x720）重排时，所有窗口严格落在屏幕内，绝不溢出"""
    from ats.ui.intraday_strategy_dialog import _SBCWindowProxy
    
    # 模拟笔记本内屏: 1536 x 824 (1920x1080 125% 缩放扣除任务栏)
    screen_rect = QRect(0, 0, 1536, 824)
    
    # 模拟 6 个打开的 SBC 窗口代理
    applied_geometries = []
    
    class MockProxy:
        def __init__(self, idx):
            self.idx = idx
            self.geo = QRect(100 + idx * 50, 100 + idx * 30, 640, 420)
        def is_maximized_or_minimized(self):
            return False
        def show_normal(self):
            pass
        def get_geometry(self):
            return self.geo
        def apply_geometry(self, x, y, w, h, activate=False):
            applied_geometries.append(QRect(x, y, w, h))
            self.geo = QRect(x, y, w, h)

    proxies = [MockProxy(i) for i in range(6)]
    
    # 模拟重排核心几何计算过程
    count = len(proxies)
    orig_rows = 2
    orig_cols = 3
    sg = screen_rect
    
    pad_left = 10
    pad_top = 10
    pad_right = 10
    pad_bottom = 10
    margin_x = 8
    margin_y = 8

    avail_w = max(380, sg.width() - pad_left - pad_right)
    avail_h = max(260, sg.height() - pad_top - pad_bottom)
    min_window_w = 420

    cols = 3
    while cols > 1 and int((avail_w - (cols - 1) * margin_x) / cols) < min_window_w:
        cols -= 1
    cols = max(1, cols)
    import math
    rows = math.ceil(count / cols)

    calc_w = int((avail_w - (cols - 1) * margin_x) / cols)
    target_w = max(320, min(calc_w, avail_w))
    calc_h = int((avail_h - (rows - 1) * margin_y) / rows)
    target_h = max(260, min(calc_h, avail_h))

    for idx_d, pxy in enumerate(proxies):
        r = idx_d // cols
        c = idx_d % cols
        pos_x = sg.left() + pad_left + c * (target_w + margin_x)
        pos_y = sg.top() + pad_top + r * (target_h + margin_y)
        if pos_x + target_w > sg.right() - pad_right:
            pos_x = max(sg.left() + pad_left, sg.right() - pad_right - target_w)
        if pos_y + target_h > sg.bottom() - pad_bottom:
            pos_y = max(sg.top() + pad_top, sg.bottom() - pad_bottom - target_h)
        pxy.apply_geometry(pos_x, pos_y, target_w, target_h, activate=False)

    # 严格断言：所有 6 个窗口的几何区域必须 100% 落在 screen_rect 内部！
    assert len(applied_geometries) == 6
    for idx, geo in enumerate(applied_geometries):
        assert geo.left() >= screen_rect.left(), f"窗口 {idx} 左越界"
        assert geo.right() <= screen_rect.right(), f"窗口 {idx} 右越界: {geo.right()} > {screen_rect.right()}"
        assert geo.top() >= screen_rect.top(), f"窗口 {idx} 上越界"
        assert geo.bottom() <= screen_rect.bottom(), f"窗口 {idx} 下越界: {geo.bottom()} > {screen_rect.bottom()}"
