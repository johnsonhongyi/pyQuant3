# -*- coding: utf-8 -*-
"""
tests/test_sector_miner_and_distribution_strategy_filter.py
=============================================================================
验证【板块轮动深挖工作台】(SectorRotationMinerDialog) 与
【涨跌分布个股明细】(DistributionDetailsDialog) 的【🎯 策略过滤】功能全链路测试：
1. 按钮控件构建、文案、ToolTip 与 QSS 样式 (与板块明细 SSOT 对齐)；
2. 专属独立持久化存储与冷启动读取恢复；
3. 策略过滤核心逻辑：极速哈希集合判定与动态切片评估；
4. 搜索框关键字与策略过滤联合筛选；
5. 窗口标题与计数标签动态更新 (过滤后 M 只 / 共 N 只)；
6. 轮动深挖全貌模式与精简模式自适应隐藏/显示；
7. 全局策略公式变更广播 (on_global_filter_changed) 自动联动响应。
"""

import pytest
import pandas as pd
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ats.ui.sector_rotation_miner_dialog import SectorRotationMinerDialog
from ats.ui.chart_widgets import DistributionDetailsDialog
from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog
from ats.ui.styles import save_config_node, load_config_node


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def clean_config():
    """保证每个测试前后全局配置复位，消除持久化污染"""
    save_config_node("sector_miner_strategy_filter_enabled", False)
    save_config_node("ats_distribution_detail_filter_enabled", False)
    save_config_node("hot_leaderboard_filter_enabled", False)
    save_config_node("daily_limitup_filter_enabled", False)
    save_config_node("ats_query_expr", "")
    yield
    save_config_node("sector_miner_strategy_filter_enabled", False)
    save_config_node("ats_distribution_detail_filter_enabled", False)
    save_config_node("hot_leaderboard_filter_enabled", False)
    save_config_node("daily_limitup_filter_enabled", False)
    save_config_node("ats_query_expr", "")


@pytest.fixture
def sample_test_df():
    """构造包含多只股票与常用指标的测试 DataFrame"""
    data = {
        'code': ['002004', '603090', '002579', '600876', '300311'],
        'name': ['华邦健康', '宏盛股份', '中京电子', '洛阳玻璃', '任子行'],
        'percent': [0.90, 10.02, 3.50, 9.98, -1.20],
        'close': [4.50, 23.50, 8.80, 15.20, 5.60],
        'trade': [4.50, 23.50, 8.80, 15.20, 5.60],
        'ratio': [0.10, 1.45, 2.30, 1.80, 0.80],
        'volume_ratio': [0.10, 1.45, 2.30, 1.80, 0.80],
        'dff': [0.90, 10.02, 3.50, 9.98, -1.20],
        'dff2': [3.70, 8.50, 1.20, 12.0, -2.50],
        'dff3': [14.0, 25.0, 5.0, 30.0, -5.0],
        'category': ['煤化工概念', '煤化工概念', 'PCB概念', '国企改革;光伏', '网络安全'],
        'industry': ['医药生物', '通用设备', '电子', '建筑材料', '计算机']
    }
    df = pd.DataFrame(data)
    df.set_index('code', inplace=True, drop=False)
    return df


def test_sector_miner_strategy_filter_toggle_and_persistence(qapp, sample_test_df):
    """测试轮动深挖工作台策略过滤按钮初始状态、切换与持久化"""
    save_config_node("sector_miner_strategy_filter_enabled", False)
    dlg = SectorRotationMinerDialog(parent=None, current_df=sample_test_df)
    try:
        # 1. 验证按钮存在并处于默认关闭状态
        assert hasattr(dlg, 'btn_toggle_filter')
        assert dlg.filter_enabled is False
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (关)"
        assert "【已关闭】" in dlg.btn_toggle_filter.toolTip()

        # 2. 点击切换为开启
        dlg.btn_toggle_filter.click()
        assert dlg.filter_enabled is True
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (开)"
        assert "#00ff88" in dlg.btn_toggle_filter.styleSheet()
        assert "【已开启】" in dlg.btn_toggle_filter.toolTip()
        assert load_config_node("sector_miner_strategy_filter_enabled", False) is True

        # 3. 再次点击切换为关闭
        dlg.btn_toggle_filter.click()
        assert dlg.filter_enabled is False
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (关)"
        assert load_config_node("sector_miner_strategy_filter_enabled", True) is False
    finally:
        dlg.close()


def test_sector_miner_strategy_filtering_logic(qapp, sample_test_df):
    """测试轮动深挖候选池策略过滤与数量统计"""
    save_config_node("sector_miner_strategy_filter_enabled", False)
    save_config_node("ats_query_expr", "percent > 2.0")

    dlg = SectorRotationMinerDialog(parent=None, current_df=sample_test_df)
    try:
        # 模拟候选池有 3 只股票
        dlg._all_candidates = [
            {'code': '002004', 'name': '华邦健康', 'pct': 0.90, 'sector': '煤化工概念', 'pattern_name': '启动'},
            {'code': '603090', 'name': '宏盛股份', 'pct': 10.02, 'sector': '煤化工概念', 'pattern_name': '涨停起爆'},
            {'code': '002579', 'name': '中京电子', 'pct': 3.50, 'sector': 'PCB概念', 'pattern_name': '突破'},
        ]
        
        # 关闭策略过滤时，显示全部 3 只
        dlg._apply_candidate_filter()
        assert dlg.candidates_table.rowCount() == 3
        assert "候选: 3 只" in dlg.lbl_count_info.text()

        # 开启策略过滤 (公式: percent > 2.0，命中 603090 与 002579)
        dlg.toggle_filter_state()
        assert dlg.filter_enabled is True
        assert dlg.candidates_table.rowCount() == 2
        visible_codes = [dlg.candidates_table.item(r, 0).text() for r in range(dlg.candidates_table.rowCount())]
        assert '603090' in visible_codes
        assert '002579' in visible_codes
        assert '002004' not in visible_codes
        assert "候选: 2 只 (🎯策略过滤 | 共 3 只)" in dlg.lbl_count_info.text()

        # 结合搜索框关键字进行二次筛选 (搜 "宏盛")
        dlg.txt_filter.setText("宏盛")
        assert dlg.candidates_table.rowCount() == 1
        assert dlg.candidates_table.item(0, 0).text() == '603090'

        # 清空搜索框
        dlg.txt_filter.setText("")
        assert dlg.candidates_table.rowCount() == 2

        # 关闭策略过滤，恢复全部 3 只
        dlg.toggle_filter_state()
        assert dlg.filter_enabled is False
        assert dlg.candidates_table.rowCount() == 3
        assert "候选: 3 只" in dlg.lbl_count_info.text()
    finally:
        dlg.close()


def test_sector_miner_compact_mode_toggle(qapp, sample_test_df):
    """测试轮动深挖在精简模式下隐藏策略过滤按钮，全貌模式下还原"""
    dlg = SectorRotationMinerDialog(parent=None, current_df=sample_test_df)
    try:
        dlg.show()
        # 全貌模式下可见
        dlg._apply_view_mode(is_compact=False)
        assert dlg.btn_toggle_filter.isHidden() is False

        # 精简模式下隐藏
        dlg._apply_view_mode(is_compact=True)
        assert dlg.btn_toggle_filter.isHidden() is True

        # 恢复全貌模式
        dlg._apply_view_mode(is_compact=False)
        assert dlg.btn_toggle_filter.isHidden() is False
    finally:
        dlg.close()


def test_distribution_detail_strategy_filter_toggle_and_persistence(qapp, sample_test_df):
    """测试涨跌分布个股明细按钮初始状态、切换与持久化"""
    save_config_node("ats_distribution_detail_filter_enabled", False)
    dlg = DistributionDetailsDialog(bucket_idx=9, parent=None)
    try:
        # 1. 验证按钮存在并处于默认关闭状态
        assert hasattr(dlg, 'btn_toggle_filter')
        assert dlg.filter_enabled is False
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (关)"
        assert "【已关闭】" in dlg.btn_toggle_filter.toolTip()

        # 2. 点击切换为开启
        dlg.btn_toggle_filter.click()
        assert dlg.filter_enabled is True
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (开)"
        assert "#00ff88" in dlg.btn_toggle_filter.styleSheet()
        assert "【已开启】" in dlg.btn_toggle_filter.toolTip()
        assert load_config_node("ats_distribution_detail_filter_enabled", False) is True

        # 3. 再次点击切换为关闭
        dlg.btn_toggle_filter.click()
        assert dlg.filter_enabled is False
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (关)"
        assert load_config_node("ats_distribution_detail_filter_enabled", True) is False
    finally:
        dlg.close()


def test_distribution_detail_strategy_filtering_and_title_update(qapp, sample_test_df):
    """测试涨跌分布个股明细数据更新、策略过滤与标题栏动态更新"""
    save_config_node("ats_distribution_detail_filter_enabled", False)
    save_config_node("ats_query_expr", "volume_ratio > 1.0")

    dlg = DistributionDetailsDialog(bucket_idx=9, parent=None)
    try:
        # 装载测试数据 (共 5 只股票)
        dlg.update_data(sample_test_df)
        assert dlg.table.rowCount() == 5
        assert "共 5 只" in dlg.windowTitle()

        # 开启策略过滤 (公式: volume_ratio > 1.0，命中 603090, 002579, 600876，共 3 只)
        dlg.toggle_filter_state()
        assert dlg.filter_enabled is True
        
        # 统计未隐藏的可见行数
        visible_rows = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
        assert len(visible_rows) == 3
        assert "(过滤后 3 只 / 共 5 只)" in dlg.windowTitle()
        assert "[🎯策略过滤]" in dlg.windowTitle()

        # 结合搜索框进行二次筛选 (搜 "宏盛")
        dlg.search_edit.setText("宏盛")
        visible_after_search = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
        assert len(visible_after_search) == 1
        assert "(过滤后 1 只 / 共 5 只)" in dlg.windowTitle()

        # 清空搜索框
        dlg.search_edit.setText("")
        visible_reset = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
        assert len(visible_reset) == 3

        # 关闭策略过滤，恢复全部 5 只可见
        dlg.toggle_filter_state()
        assert dlg.filter_enabled is False
        all_visible = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
        assert len(all_visible) == 5
        assert "(共 5 只)" in dlg.windowTitle()
        assert "[🎯策略过滤]" not in dlg.windowTitle()
    finally:
        dlg.close()


def test_hot_sector_leaderboard_strategy_filter(qapp, sample_test_df):
    """测试强势板块龙头突击跟单榜策略过滤按钮、状态切换、过滤逻辑与专属信息标签"""
    save_config_node("hot_leaderboard_filter_enabled", False)
    save_config_node("ats_query_expr", "percent > 5.0")

    dlg = HotSectorLeaderboardDialog(parent=None)
    try:
        # 1. 验证按钮、时间指示器与过滤信息标签存在
        assert hasattr(dlg, 'btn_toggle_filter')
        assert hasattr(dlg, 'lbl_filter_info')
        assert hasattr(dlg, 'lbl_update_time')
        assert dlg.filter_enabled is False
        assert dlg.lbl_filter_info.text() == ""
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (关)"
        assert "更新:" in dlg.lbl_update_time.text() or "💤" in dlg.lbl_update_time.text()

        # 2. 模拟 Alpha 计算结果
        test_results = [
            {
                'code': '603090', 'name': '宏盛股份', 'pct': 10.02, 'percent': 10.02,
                'sector': '煤化工概念', 'buy_tag': 'LEADER', 'alpha_score': 95.0,
                'price': 23.50, 'speed': 2.5, 'vwap_dev_pct': 1.2
            },
            {
                'code': '002004', 'name': '华邦健康', 'pct': 0.90, 'percent': 0.90,
                'sector': '煤化工概念', 'buy_tag': 'PULLBACK', 'alpha_score': 65.0,
                'price': 4.50, 'speed': 0.1, 'vwap_dev_pct': -0.2
            }
        ]
        dlg.current_top_sectors = ['煤化工概念']
        dlg.active_sectors = {'煤化工概念'}
        dlg.cached_results = test_results
        dlg._render_table_data(test_results)

        # 默认关闭时，2只股票全部呈现，过滤标签为空
        assert dlg.table.rowCount() == 2
        assert "标的: 2" in dlg.lbl_stats.text()
        assert dlg.lbl_filter_info.text() == ""

        # 3. 开启策略过滤 (percent > 5.0，仅宏盛股份保留)
        dlg.toggle_filter_state()
        assert dlg.filter_enabled is True
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (开)"
        assert load_config_node("hot_leaderboard_filter_enabled", False) is True
        assert dlg.table.rowCount() == 1
        assert "标的: 1" in dlg.lbl_stats.text()
        assert dlg.lbl_filter_info.text() == "(过滤后: 1 只 / 共 2 只)"

        # 4. 关闭策略过滤，恢复2只
        dlg.toggle_filter_state()
        assert dlg.filter_enabled is False
        assert dlg.table.rowCount() == 2
        assert "标的: 2" in dlg.lbl_stats.text()
        assert dlg.lbl_filter_info.text() == ""
    finally:
        dlg.close()


def test_daily_limit_up_dialog_strategy_filter_and_time_label(qapp, sample_test_df):
    """测试每日涨停与天梯策略过滤按钮、状态切换、过滤逻辑、标题更新与专属信息标签"""
    save_config_node("daily_limitup_filter_enabled", False)
    save_config_node("ats_query_expr", "percent > 9.99")

    dlg = DailyLimitUpDialog(parent=None)
    try:
        # 1. 验证按钮、时间标签控件与过滤信息标签
        assert hasattr(dlg, 'btn_toggle_filter')
        assert hasattr(dlg, 'lbl_filter_info')
        assert hasattr(dlg, 'lbl_update_time')
        assert dlg.filter_enabled is False
        assert dlg.lbl_filter_info.text() == ""
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (关)"
        assert "更新:" in dlg.lbl_update_time.text() or "💤" in dlg.lbl_update_time.text()

        # 2. 装载测试数据
        test_records = [
            {'code': '603090', 'name': '宏盛股份', 'pct': 10.02, 'percent': 10.02, 'is_limit_up': True, 'time_phase': '黄金定龙'},
            {'code': '600876', 'name': '洛阳玻璃', 'pct': 9.98, 'percent': 9.98, 'is_limit_up': True, 'time_phase': '黄金定龙'},
            {'code': '002004', 'name': '华邦健康', 'pct': 0.90, 'percent': 0.90, 'is_limit_up': False, 'time_phase': '黄金定龙'},
        ]
        dlg.current_records = test_records
        dlg.current_mode = "TODAY"
        dlg._apply_filter()

        # 未开启策略过滤时，包含装载的全部 3 只标的
        assert dlg.table.rowCount() == 3
        assert "共 3 只" in dlg.windowTitle()
        assert "[🎯策略过滤]" not in dlg.windowTitle()
        assert dlg.lbl_filter_info.text() == ""

        # 3. 开启策略过滤 (公式: percent > 9.99，仅 603090 命中)
        dlg.toggle_filter_state()
        assert dlg.filter_enabled is True
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (开)"
        assert load_config_node("daily_limitup_filter_enabled", False) is True

        assert dlg.table.rowCount() == 1
        assert "(过滤后 1 只 / 共 3 只) [🎯策略过滤]" in dlg.windowTitle()
        assert dlg.lbl_filter_info.text() == "(过滤后: 1 只 / 共 3 只)"

        # 验证此时无论 lbl_status 怎么被其他事件覆盖，lbl_filter_info 都稳固显示在按钮左侧不受任何干扰！
        dlg.lbl_status.setText("【选定】000980 众泰汽车 | 现价:2.33")
        assert dlg.lbl_filter_info.text() == "(过滤后: 1 只 / 共 3 只)"

        # 4. 关闭策略过滤恢复
        dlg.toggle_filter_state()
        assert dlg.filter_enabled is False
        assert dlg.btn_toggle_filter.text() == "🎯 策略过滤 (关)"
        assert dlg.table.rowCount() == 3
        assert "共 3 只" in dlg.windowTitle()
        assert "[🎯策略过滤]" not in dlg.windowTitle()
        assert dlg.lbl_filter_info.text() == ""
    finally:
        dlg.close()


def test_global_filter_changed_broadcast(qapp, sample_test_df):
    """测试主窗口广播 on_global_filter_changed 时自动刷新"""
    save_config_node("ats_distribution_detail_filter_enabled", True)
    save_config_node("sector_miner_strategy_filter_enabled", True)
    save_config_node("hot_leaderboard_filter_enabled", True)
    save_config_node("daily_limitup_filter_enabled", True)
    save_config_node("ats_query_expr", "percent > 5.0")

    dist_dlg = DistributionDetailsDialog(bucket_idx=9, parent=None)
    miner_dlg = SectorRotationMinerDialog(parent=None, current_df=sample_test_df)
    hot_dlg = HotSectorLeaderboardDialog(parent=None)
    ladder_dlg = DailyLimitUpDialog(parent=None)
    try:
        dist_dlg.update_data(sample_test_df)
        miner_dlg._all_candidates = [
            {'code': '002004', 'name': '华邦健康', 'pct': 0.90, 'sector': '煤化工概念'},
            {'code': '603090', 'name': '宏盛股份', 'pct': 10.02, 'sector': '煤化工概念'},
        ]
        miner_dlg._apply_candidate_filter()

        hot_results = [
            {'code': '002004', 'name': '华邦健康', 'pct': 0.90, 'percent': 0.90, 'sector': '煤化工概念', 'buy_tag': 'PULLBACK'},
            {'code': '603090', 'name': '宏盛股份', 'pct': 10.02, 'percent': 10.02, 'sector': '煤化工概念', 'buy_tag': 'LEADER'}
        ]
        hot_dlg.current_top_sectors = ['煤化工概念']
        hot_dlg.active_sectors = {'煤化工概念'}
        hot_dlg.cached_results = hot_results
        hot_dlg._render_table_data(hot_results)

        ladder_records = [
            {'code': '002004', 'name': '华邦健康', 'pct': 0.90, 'percent': 0.90, 'is_limit_up': True, 'time_phase': '黄金定龙'},
            {'code': '603090', 'name': '宏盛股份', 'pct': 10.02, 'percent': 10.02, 'is_limit_up': True, 'time_phase': '黄金定龙'}
        ]
        ladder_dlg.current_records = ladder_records
        ladder_dlg.current_mode = "TODAY"
        ladder_dlg._apply_filter()

        # percent > 5.0 时，宏盛股份命中 (1 只)
        assert miner_dlg.candidates_table.rowCount() == 1
        assert hot_dlg.table.rowCount() == 1
        assert ladder_dlg.table.rowCount() == 1
        
        # 变更全局公式为 percent < 0.0 (命中任子行)
        save_config_node("ats_query_expr", "percent < 0.0")
        dist_dlg.on_global_filter_changed("percent < 0.0")
        miner_dlg.on_global_filter_changed("percent < 0.0")
        hot_dlg.on_global_filter_changed("percent < 0.0")
        ladder_dlg.on_global_filter_changed("percent < 0.0")

        # 候选池、热榜、天梯涨幅均 > 0，因此均变为 0 只
        assert miner_dlg.candidates_table.rowCount() == 0
        assert hot_dlg.table.rowCount() == 0
        assert ladder_dlg.table.rowCount() == 0

        # dist_dlg 命中 300311 (1 只)
        vis = [r for r in range(dist_dlg.table.rowCount()) if not dist_dlg.table.isRowHidden(r)]
        assert len(vis) == 1
        code_visible = dist_dlg.table.item(vis[0], 0).text()
        assert '300311' in code_visible
    finally:
        dist_dlg.close()
        miner_dlg.close()
        hot_dlg.close()
        ladder_dlg.close()
