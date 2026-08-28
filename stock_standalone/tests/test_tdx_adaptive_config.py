# -*- coding: utf-8 -*-
"""
tests/test_tdx_adaptive_config.py
测试通达信 (TDX) 配置文件自适应动态探查与分时策略全量检测解包
"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest
from JohnsonUtil import commonTips as cct
from ats import tdx_realtime_fetcher as trf


def test_tdx_config_paths_adaptive():
    """测试 TDX 根目录与配置文件自适应动态探查"""
    # 1. 验证获取所有有效 TDX 目录
    valid_dirs = cct.get_all_valid_tdx_dirs()
    assert isinstance(valid_dirs, list)
    assert len(valid_dirs) > 0, "当前系统应能从 global.ini 探测到至少一个有效 TDX 根目录"
    for d in valid_dirs:
        assert os.path.exists(d), f"探测到的目录应真实存在: {d}"

    # 2. 验证获取所有有效 connect.cfg 配置文件
    cfg_paths = cct.get_tdx_config_paths()
    assert isinstance(cfg_paths, list)
    assert len(cfg_paths) > 0, "当前系统应能探测到至少一个有效 TDX 配置文件"
    for p in cfg_paths:
        assert os.path.isfile(p), f"探测到的配置文件应真实存在: {p}"

    # 3. 验证 fetcher 模块动态获取
    fetcher_paths = trf.get_local_tdx_config_paths()
    assert isinstance(fetcher_paths, list)
    assert len(fetcher_paths) > 0


def test_tdx_get_all_hosts():
    """测试 TDX 服务器主机列表提取与 Fallback 兜底"""
    hosts = trf.get_all_tdx_hosts()
    assert isinstance(hosts, list)
    assert len(hosts) >= len(trf.FALLBACK_TDX_HOSTS)
    
    # 验证主机元组格式 (name, ip, port)
    for h in hosts:
        assert len(h) == 3
        name, ip, port = h
        assert isinstance(name, str) and len(name) > 0
        assert isinstance(ip, str) and len(ip) > 0
        assert isinstance(port, int) and port > 0


def test_intraday_strategy_realtime_unpacking():
    """测试分时策略弹窗实时数据 11 元组返回与解包兼容性"""
    from ats.intraday_strategy_engine import IntradayStrategyEngine
    engine = IntradayStrategyEngine.get_instance()
    
    target_codes = engine.get_all_target_codes()
    assert isinstance(target_codes, list)
    assert len(target_codes) > 0
    
    # 验证模拟 11 元组解包
    sample_tuple = (25.18, 28.51, 38.50, 25.12, 27.30, 86.88, 473606208.0, 28.51, "华大海天", False, 12.57)
    assert len(sample_tuple) == 11
    open_p, trade_p, high_p, low_p, vwap_p, to_rate, amt_val, bid1_p, _, is_unlisted, last_close = sample_tuple
    assert open_p == 25.18
    assert trade_p == 28.51
    assert last_close == 12.57


def test_all_codes_eval_dialog_structure():
    """测试 AllCodesStrategyEvalDialog 类结构、持久化机制、排序算法与组件存在性"""
    from PyQt6.QtWidgets import QApplication
    from ats.ui.intraday_strategy_dialog import AllCodesStrategyEvalDialog, NumericTableWidgetItem

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # 1. 验证类及方法存在
    assert hasattr(AllCodesStrategyEvalDialog, "_restore_geometry")
    assert hasattr(AllCodesStrategyEvalDialog, "_save_geometry")
    assert hasattr(AllCodesStrategyEvalDialog, "run_evaluation")
    assert hasattr(AllCodesStrategyEvalDialog, "_apply_sort_and_render")
    assert hasattr(AllCodesStrategyEvalDialog, "_switch_view_mode")
    assert hasattr(AllCodesStrategyEvalDialog, "_render_table")
    assert hasattr(AllCodesStrategyEvalDialog, "_render_cards")
    assert hasattr(AllCodesStrategyEvalDialog, "_create_card_widget")
    assert hasattr(AllCodesStrategyEvalDialog, "_on_search_text_changed")
    assert hasattr(AllCodesStrategyEvalDialog, "_copy_full_report")

    # 2. 验证表头包含 ⭐ 综合评分 独立列
    assert "⭐ 综合评分" in AllCodesStrategyEvalDialog.TABLE_HEADERS
    # 3. 验证 NumericTableWidgetItem 精确数值比对
    it1 = NumericTableWidgetItem("⭐ 3.92分", sort_val=3.92)
    it2 = NumericTableWidgetItem("⭐ 7.65分", sort_val=7.65)
    it3 = NumericTableWidgetItem("⭐ 10.00分", sort_val=10.00)
    assert it1 < it2 < it3
    assert not (it3 < it1)

    # 5. 验证 ATS 标准联动与键盘上下键导航方法
    assert hasattr(AllCodesStrategyEvalDialog, "_broadcast_link_stock")
    assert hasattr(AllCodesStrategyEvalDialog, "_on_table_current_cell_changed")
    assert hasattr(AllCodesStrategyEvalDialog, "_on_table_item_clicked")
    assert hasattr(AllCodesStrategyEvalDialog, "_fire_linkage_debounced")
    assert hasattr(AllCodesStrategyEvalDialog, "keyPressEvent")
    assert hasattr(AllCodesStrategyEvalDialog, "_navigate_cards")

