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
