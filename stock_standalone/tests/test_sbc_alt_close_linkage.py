# -*- coding: utf-8 -*-
"""
tests/test_sbc_alt_close_linkage.py
-----------------------------------
专项测试：
1. SBC 顶部异动提醒横幅：单窗关闭与 Alt+点击/Alt+X 联动关闭所有窗口横幅；
2. 集合竞价小关闭按钮：位置自适应、单窗关闭与 Alt+点击/Alt+C 联动关闭所有窗口竞价图。
"""
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, SBCWindowMemoryManager

@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_sbc_ack_attention_banner_single_and_alt_linkage(qapp, monkeypatch):
    dlg1 = SBCIntradayChartDialog(code="688347")
    dlg2 = SBCIntradayChartDialog(code="600000")
    
    # 模拟两个窗口都弹出了异动横幅
    dlg1.sbc_attention_banner.setVisible(True)
    dlg2.sbc_attention_banner.setVisible(True)
    assert not dlg1.sbc_attention_banner.isHidden()
    assert not dlg2.sbc_attention_banner.isHidden()
    
    # 1. 验证普通单窗收起：dlg1 收起，dlg2 保持显示
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args: False)
    dlg1._ack_sbc_attention_banner()
    assert dlg1.sbc_attention_banner.isHidden()
    assert not dlg2.sbc_attention_banner.isHidden()
    
    # 2. 重新激活 dlg1
    dlg1.sbc_attention_banner.setVisible(True)
    assert not dlg1.sbc_attention_banner.isHidden()
    
    # 3. 验证 Alt 联动收起：dlg1 和 dlg2 均被收起
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args: True)
    dlg1._ack_sbc_attention_banner()
    assert dlg1.sbc_attention_banner.isHidden()
    assert dlg2.sbc_attention_banner.isHidden()
    
    dlg1.close()
    dlg2.close()

def test_auction_chart_close_single_and_alt_linkage(qapp, monkeypatch):
    dlg1 = SBCIntradayChartDialog(code="688347")
    dlg2 = SBCIntradayChartDialog(code="600000")
    
    # 模拟两个窗口都开启了集合竞价图
    dlg1.canvas.show_auction_chart = True
    dlg2.canvas.show_auction_chart = True
    assert getattr(dlg1.canvas, "btn_close_auction", None) is not None
    
    # 1. 普通单窗点击关闭：dlg1 竞价图关闭，dlg2 依然开启
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args: False)
    dlg1.canvas._on_auction_close_btn_clicked()
    assert dlg1.canvas.show_auction_chart is False
    assert dlg2.canvas.show_auction_chart is True
    
    # 2. 恢复 dlg1
    dlg1.canvas.show_auction_chart = True
    
    # 3. Alt 联动点击关闭：所有窗口竞价图均被关闭
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog.is_alt_modifier_active", lambda *args: True)
    dlg1.canvas._on_auction_close_btn_clicked()
    assert dlg1.canvas.show_auction_chart is False
    assert dlg2.canvas.show_auction_chart is False
    
    dlg1.close()
    dlg2.close()
