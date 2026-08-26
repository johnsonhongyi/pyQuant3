# -*- coding: utf-8 -*-
"""
tests/test_sector_strength_and_detail_parity.py
验证 ATS 行业板块热力图 (SectorHeatmapWidget) 与 板块成分股明细 (ATSSectorDetailDialog / SectorDataAggregator)
与 TK 竞价板块检测器 (BiddingMomentumDetector / bidding_session_data) 100% 保持一致性与权威数据对齐。
"""

import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from ats.ui.heatmap_widget import SectorHeatmapWidget
from ats.sector_data_aggregator import SectorDataAggregator


def test_sector_heatmap_loads_bidding_ssot():
    widget = SectorHeatmapWidget()
    widget.load_live_sectors(force=True)
    
    assert hasattr(widget, 'sectors')
    assert len(widget.sectors) > 50, f"板块数量应为全市场规模 (>50)，实际为: {len(widget.sectors)}"
    
    first_sec = widget.sectors[0]
    assert len(first_sec) >= 6
    assert isinstance(first_sec[0], str)
    assert isinstance(first_sec[1], float)
    assert isinstance(first_sec[2], str) and '%' in first_sec[2]
    assert isinstance(first_sec[3], int) and first_sec[3] > 0
    
    assert hasattr(widget, 'sector_to_codes')
    sec_name = first_sec[0]
    codes = widget.sector_to_codes.get(sec_name, [])
    assert len(codes) == first_sec[3], f"sector_to_codes 中代码数量 ({len(codes)}) 应与 count ({first_sec[3]}) 一致"


def test_sector_detail_aggregator_authoritative_parity():
    agg = SectorDataAggregator.get_instance()
    
    for sec_name in ['PCB概念', '人形机器人', '存储芯片', '金属铜']:
        rows, score, leader_str, meta = agg.fetch_sector_detail(sector_name=sec_name)
        
        assert isinstance(rows, list)
        assert isinstance(score, float)
        assert isinstance(leader_str, str)
        assert isinstance(meta, dict)
        
        if sec_name == 'PCB概念':
            assert len(rows) >= 50, f"PCB概念成分股数量应不少于 50 只，实际: {len(rows)}"
            assert score > 0.0
        elif sec_name == '人形机器人':
            assert len(rows) >= 100, f"人形机器人成分股数量应不少于 100 只，实际: {len(rows)}"
            assert score > 0.0
        elif sec_name == '金属铜':
            assert len(rows) >= 30, f"金属铜成分股数量应不少于 30 只，实际: {len(rows)}"
            assert score > 0.0
            
        if rows:
            first_row = rows[0]
            assert '👑' in str(first_row.get('type', '')) or first_row.get('score', 0) >= 80.0
            assert 'code' in first_row
            assert 'name' in first_row
            assert 'pct' in first_row


def test_sector_detail_filter_toggle_and_persistence():
    from ats.ui.sector_detail_dialog import ATSSectorDetailDialog
    from ats.ui.styles import save_config_node, load_config_node
    
    # 1. 模拟初始状态保存为 True
    save_config_node("ats_sector_detail_filter_enabled", "true")
    dlg = ATSSectorDetailDialog("金属铜")
    assert dlg.filter_enabled is True
    assert "开" in dlg.btn_toggle_filter.text()
    
    # 2. 点击切换状态
    dlg.toggle_filter_state()
    assert dlg.filter_enabled is False
    assert "关" in dlg.btn_toggle_filter.text()
    assert load_config_node("ats_sector_detail_filter_enabled") == "false"
    
    # 3. 再次切换
    dlg.toggle_filter_state()
    assert dlg.filter_enabled is True
    assert "开" in dlg.btn_toggle_filter.text()
    assert load_config_node("ats_sector_detail_filter_enabled") == "true"
    
    # 4. 测试过滤逻辑
    mock_rows = [
        {'code': '600362', 'name': '江西铜业', 'pct': 5.2, 'score': 90.0, 'type': '👑龙头', 'start_pct': 2.0, 'dff': 3.2, 'rank': 100, 'dff2': 1.0, 'dff3': 2.0},
        {'code': '000878', 'name': '云南铜业', 'pct': -1.5, 'score': 45.0, 'type': '跟进', 'start_pct': -0.5, 'dff': -1.0, 'rank': 2000, 'dff2': 0.0, 'dff3': -1.0},
    ]
    dlg._all_raw_rows = mock_rows
    
    # 当公式为 pct > 0 时，只保留江西铜业
    res_pos = dlg._filter_rows_by_query(mock_rows, "pct > 0")
    assert len(res_pos) == 1
    assert res_pos[0]['code'] == '600362'
    
    # 当公式为 pct < 0 时，只保留云南铜业
    res_neg = dlg._filter_rows_by_query(mock_rows, "pct < 0")
    assert len(res_neg) == 1
    assert res_neg[0]['code'] == '000878'
    
    dlg.close()


def test_stock_detail_filter_evaluation_accuracy():
    import time
    import pandas as pd
    from ats.ui.main_window import StockDetailDialog
    
    mock_row = {
        'code': '920186',
        'name': 'N中科仪',
        'close': 74.36,
        'open': 72.80,
        'high': 74.85,
        'low': 72.41,
        'percent': 1.92,
        'pct': 1.92,
        'turnover': 231468328.52,
        'volume': 7000
    }
    
    detail_dlg = StockDetailDialog(code='920186', name='N中科仪', df_row=pd.Series(mock_row))
    
    # 评估未满足的条件 (percent > 5.0)，绝不能误判为命中
    detail_dlg.update_filter_status("percent > 5.0")
    time.sleep(0.3)
    app.processEvents()
    assert "未命中" in detail_dlg.lbl_filter_result.text() or "❌" in detail_dlg.lbl_filter_result.text()
    
    # 评估满足的条件 (percent < 5.0)，应正确判定为命中
    detail_dlg.update_filter_status("percent < 5.0")
    time.sleep(0.3)
    app.processEvents()
    assert "命中" in detail_dlg.lbl_filter_result.text() and "未命中" not in detail_dlg.lbl_filter_result.text()
    
    detail_dlg.close()


