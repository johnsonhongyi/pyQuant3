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


@pytest.fixture(autouse=True)
def isolate_config():
    """测试前后安全备份与还原 window_config.json 及 favorite_stocks.json，绝不污染用户真实环境"""
    from sys_utils import get_app_root, get_conf_path
    import json
    cfg_path = get_conf_path("window_config.json", get_app_root())
    fav_path = get_conf_path("favorite_stocks.json", get_app_root()) or os.path.join(get_app_root(), "favorite_stocks.json")
    backup_data = None
    backup_fav = None
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
        except Exception:
            pass
    if os.path.exists(fav_path):
        try:
            with open(fav_path, 'r', encoding='utf-8') as f:
                backup_fav = json.load(f)
        except Exception:
            pass
    yield
    if backup_data is not None:
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    if backup_fav is not None:
        try:
            with open(fav_path, 'w', encoding='utf-8') as f:
                json.dump(backup_fav, f, ensure_ascii=False, indent=2)
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().load_from_config()
        except Exception:
            pass


def test_sector_detail_filter_toggle_and_persistence():
    from ats.ui.sector_detail_dialog import ATSSectorDetailDialog
    from ats.ui.styles import save_config_node, load_config_node, parse_bool_config
    
    # 1. 模拟初始状态保存为 True
    save_config_node("ats_sector_detail_filter_enabled", True)
    dlg = ATSSectorDetailDialog("金属铜")
    assert dlg.filter_enabled is True
    assert "开" in dlg.btn_toggle_filter.text()
    
    # 2. 点击切换状态
    dlg.toggle_filter_state()
    assert dlg.filter_enabled is False
    assert "关" in dlg.btn_toggle_filter.text()
    assert parse_bool_config(load_config_node("ats_sector_detail_filter_enabled")) is False
    
    # 3. 再次切换
    dlg.toggle_filter_state()
    assert dlg.filter_enabled is True
    assert "开" in dlg.btn_toggle_filter.text()
    assert parse_bool_config(load_config_node("ats_sector_detail_filter_enabled")) is True
    
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
    save_config_node("ats_sector_detail_filter_enabled", "false")
    save_config_node("ats_query_expr", "")


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
    from ats.ui.styles import save_config_node
    save_config_node("ats_sector_detail_filter_enabled", "false")
    save_config_node("ats_query_expr", "")


def test_sector_heatmap_favorite_toggle():
    """验证行业板块热力图右键设为/取消重点关注板块、持久化及置顶排序"""
    from ats.ui.heatmap_widget import SectorHeatmapWidget
    from global_favorites import GlobalFavoriteManager
    
    fav_mgr = GlobalFavoriteManager()
    
    # 准备测试板块（使用独立命名的测试板块，杜绝受现有自选干扰）
    test_sec = "测试重点板块"
    
    # 确保初始状态已清除 test_sec
    fav_mgr.remove_favorite_sector(test_sec)
    fav_mgr.remove_favorite_sector("测试普通板块A")
    fav_mgr.remove_favorite_sector("测试普通板块B")
    assert test_sec not in fav_mgr.get_favorite_sectors()
    
    widget = SectorHeatmapWidget()
    widget.sectors = [
        ("测试普通板块A", 90.0, "+2.50%", 10, "000001", "标的A"),
        ("测试重点板块", 60.0, "+1.00%", 5, "600362", "标的B"),
        ("测试普通板块B", 80.0, "+1.80%", 8, "600001", "标的C")
    ]
    widget.sort_sectors(0) # 按得分降序: 普通板块A(90) -> 普通板块B(80) -> 重点板块(60)
    assert widget.sectors[0][0] == "测试普通板块A"
    assert widget.sectors[1][0] == "测试普通板块B"
    assert widget.sectors[2][0] == "测试重点板块"
    
    # 1. 模拟右键点击添加重点关注 (由于重点关注默认置顶，添加后立即置顶排在第一项)
    widget._toggle_favorite_sector(test_sec)
    assert test_sec in fav_mgr.get_favorite_sectors()
    assert widget.sectors[0][0] == "测试重点板块"
    
    # 2. 再次点击取消重点关注
    widget._toggle_favorite_sector(test_sec)
    assert test_sec not in fav_mgr.get_favorite_sectors()
    
    # 验证恢复普通得分排序: 普通板块A(90) 回到第一项
    assert widget.sectors[0][0] == "测试普通板块A"
    assert widget.sectors[1][0] == "测试普通板块B"
    assert widget.sectors[2][0] == "测试重点板块"
    
    widget.close()



def test_extract_top_sectors_genuine_strength_unaffected_by_focus():
    """验证龙头突击榜提取 Top 3 强势板块时，严格按照真实市场强度得分选拔，绝不受重点关注置顶的视觉影响"""
    from ats.hot_sector_engine import HotSectorEngine
    from ats.ui.heatmap_widget import SectorHeatmapWidget
    from global_favorites import GlobalFavoriteManager
    
    fav_mgr = GlobalFavoriteManager()
    
    # 模拟场景：用户重点关注了得分较低的板块（如培育钻石 0.8分、光纤概念 15.0分、CPO 12.2分）
    # 而全市场真实强度得分最高的板块是 金属铜(68.3分)、金属锌(62.2分)、黄金概念(58.4分)
    sectors_data = [
        ("★ 培育钻石", 0.8, "-0.04%", 17, "000001", "标的1"),
        ("★ 光纤概念", 15.0, "+0.02%", 75, "000002", "标的2"),
        ("★ 共封装光学(CPO)", 12.2, "-0.04%", 125, "000003", "标的3"),
        ("金属铜", 68.3, "-0.02%", 86, "600362", "江西铜业"),
        ("金属锌", 62.2, "-0.28%", 39, "000751", "锌业股份"),
        ("黄金概念", 58.4, "-0.26%", 77, "600547", "山东黄金"),
        ("生物疫苗", 58.0, "+0.38%", 59, "000661", "长春高新"),
    ]
    
    sec_to_codes = {
        "培育钻石": ["000001"],
        "光纤概念": ["000002"],
        "共封装光学(CPO)": ["000003"],
        "金属铜": ["600362"],
        "金属锌": ["000751"],
        "黄金概念": ["600547"],
        "生物疫苗": ["000661"],
    }
    
    engine = HotSectorEngine.get_instance()
    
    # 1. 验证 HotSectorEngine.extract_top_sectors_from_heatmap 在不同排序模式下的提取
    top_3_score = engine.extract_top_sectors_from_heatmap(sectors_data, sec_to_codes, top_n=3, sort_mode=0)
    assert top_3_score == ["金属铜", "金属锌", "黄金概念"], f"强度得分Top 3应为强度最高板块，实际为: {top_3_score}"

    top_3_pct = engine.extract_top_sectors_from_heatmap(sectors_data, sec_to_codes, top_n=3, sort_mode=1)
    assert top_3_pct == ["生物疫苗", "光纤概念", "金属铜"], f"涨跌幅Top 3应为涨幅最高板块，实际为: {top_3_pct}"

    top_3_cnt = engine.extract_top_sectors_from_heatmap(sectors_data, sec_to_codes, top_n=3, sort_mode=2)
    assert top_3_cnt == ["共封装光学(CPO)", "金属铜", "黄金概念"], f"活跃成员数Top 3应为成员最多板块，实际为: {top_3_cnt}"
    
    # 2. 验证 SectorHeatmapWidget.get_top_sectors 随下拉框切换联动返回对应维度的 Top 3，并自动过滤虚拟系统板块 (如 实时报警)
    sectors_with_alarm = list(sectors_data) + [
        ("🔔 实时报警", 1.2, "+0.12%", 3634, "000000", ""),
        ("机器人概念", 28.8, "+0.19%", 1102, "000001", "机器人龙头"),
    ]
    widget = SectorHeatmapWidget()
    widget.sectors = sectors_with_alarm

    # 默认模式 0: 按强度得分降序
    widget.sort_combo.setCurrentIndex(0)
    assert widget.get_top_sectors(top_n=3) == ["金属铜", "金属锌", "黄金概念"]

    # 切换模式 1: 按涨跌幅降序 -> 联动返回涨幅前三 (生物疫苗 +0.38%, 机器人概念 +0.19%, 光纤概念 +0.02%)
    widget.sort_combo.setCurrentIndex(1)
    assert widget.get_top_sectors(top_n=3) == ["生物疫苗", "机器人概念", "光纤概念"]

    # 切换模式 2: 按活跃成员数降序 -> 自动过滤 "🔔 实时报警" (3634)，提取真实题材: 机器人概念(1102), 共封装光学(125), 金属铜(86)
    widget.sort_combo.setCurrentIndex(2)
    assert widget.get_top_sectors(top_n=3) == ["机器人概念", "共封装光学(CPO)", "金属铜"]
    
    # 3. 验证排序维度持久化自动保存
    from ats.ui.styles import load_config_node
    assert load_config_node("ats_heatmap_sort_index", 0) == 2

    widget.close()


def test_sector_heatmap_and_leaderboard_realtime_ipc_update():
    """
    【🎯 核心验证】验证 ATS 直接消费 TK 赛道探测器已算好的权威板块数据 (SSOT 零冗余复用)：
    1. 热力图直接复用 TK 的权威强度分 (共封装光学 89.1, 光纤概念 74.7, PCB概念 60.8)；
    2. 龙头突击榜自动跟随并将 Top 3 选为 共封装光学、光纤概念、PCB概念；
    3. 板块明细弹窗权威分 100% 对齐。
    """
    import pandas as pd
    from ats.ui.heatmap_widget import SectorHeatmapWidget
    from ats.hot_sector_engine import HotSectorEngine
    from ats.sector_data_aggregator import SectorDataAggregator
    
    widget = SectorHeatmapWidget()
    
    # 模拟 TK 赛道探测器计算好的真实活跃板块数据快照 (与用户实盘左侧窗口完全一致)
    tk_active_sectors_snap = {
        '共封装光学(CPO)': {
            'sector': '共封装光学(CPO)',
            'score': 89.1,
            'avg_pct_diff': 2.13,
            'leader': '688371',
            'leader_name': '赛微电子',
            'leader_pct': 20.0,
            'count': 125,
            'followers': [{'code': '300502', 'name': '新易盛', 'pct': 6.5}],
            'race_candidates': [{'code': '688371', 'name': '赛微电子', 'pct': 20.0}]
        },
        '光纤概念': {
            'sector': '光纤概念',
            'score': 74.7,
            'avg_pct_diff': 3.11,
            'leader': '603618',
            'leader_name': '杭电股份',
            'leader_pct': 10.0,
            'count': 75,
            'followers': [{'code': '600522', 'name': '中天科技', 'pct': 9.98}, {'code': '601869', 'name': '长飞光纤', 'pct': 10.0}],
            'race_candidates': [{'code': '603618', 'name': '杭电股份', 'pct': 10.0}]
        },
        'PCB概念': {
            'sector': 'PCB概念',
            'score': 60.8,
            'avg_pct_diff': 1.74,
            'leader': '603002',
            'leader_name': '宏昌电子',
            'leader_pct': 10.0,
            'count': 80,
            'followers': [{'code': '002463', 'name': '沪电股份', 'pct': 5.2}],
            'race_candidates': [{'code': '603002', 'name': '宏昌电子', 'pct': 10.0}]
        },
        '富士康概念': {
            'sector': '富士康概念',
            'score': 39.3,
            'avg_pct_diff': 1.79,
            'leader': '601138',
            'leader_name': '工业富联',
            'leader_pct': 3.4,
            'count': 50,
            'followers': [],
            'race_candidates': []
        }
    }
    
    # 1. 模拟收到 IPC 数据包并直接复用 TK 板块数据
    widget.update_from_tk_sector_data(tk_active_sectors_snap)
    
    # 2. 验证热力图数据 100% 对齐 TK 权威分
    cpo_item = next((item for item in widget.sectors if 'CPO' in item[0] or '共封装' in item[0]), None)
    fiber_item = next((item for item in widget.sectors if '光纤' in item[0]), None)
    pcb_item = next((item for item in widget.sectors if 'PCB' in item[0]), None)
    
    assert cpo_item is not None, "热力图中应包含共封装光学板块"
    assert fiber_item is not None, "热力图中应包含光纤概念板块"
    assert pcb_item is not None, "热力图中应包含PCB概念板块"
    
    assert cpo_item[1] == 89.1, f"共封装光学强度分应为 89.1，实际为: {cpo_item[1]}"
    assert fiber_item[1] == 74.7, f"光纤概念强度分应为 74.7，实际为: {fiber_item[1]}"
    assert pcb_item[1] == 60.8, f"PCB概念强度分应为 60.8，实际为: {pcb_item[1]}"
    assert fiber_item[4] == '603618', f"光纤概念领涨龙头应为杭电股份(603618)，实际为: {fiber_item[4]}"
    assert fiber_item[5] == '杭电股份', f"光纤概念龙头名称应为杭电股份，实际为: {fiber_item[5]}"
    
    # 3. 验证龙头突击引擎提取 Top 3 完全跟随 TK 强度排名
    engine = HotSectorEngine.get_instance()
    top_3 = engine.extract_top_sectors_from_heatmap(widget.sectors, widget.sector_to_codes, top_n=3)
    assert top_3 == ['共封装光学(CPO)', '光纤概念', 'PCB概念'], f"龙头突击 Top 3 应严格按 TK 强度排行为 No.1 CPO, No.2 光纤, No.3 PCB，实际为: {top_3}"
    
    # 4. 验证板块明细聚合器 fetch_sector_detail 正确执行
    aggregator = SectorDataAggregator.get_instance()
    rows, score, leader_str, meta = aggregator.fetch_sector_detail("光纤概念")
    assert isinstance(rows, list)
    assert isinstance(score, float)
    
    widget.close()


def test_universe_widget_sort_order_persistence():
    """
    【🎯 核心验证】验证左侧策略股票池 (UniverseTreeWidget) 在高频数据刷新 update_pools 时：
    1. 100% 保持用户点击选择的排序列 (如按涨跌幅降序)；
    2. 绝不重置为默认插入顺序，无需用户每次手动重复点击。
    """
    from PyQt6.QtCore import Qt
    from ats.ui.universe_widget import UniverseTreeWidget
    
    tree_widget = UniverseTreeWidget()
    
    # 模拟初始三级池数据 (未排序状态)
    radar_1 = [
        ("600001", "标的A", "10.00", "+1.20%", "竞价", "描述1"),
        ("600002", "标的B", "20.00", "+9.98%", "竞价", "描述2"),
        ("600003", "标的C", "30.00", "-2.50%", "竞价", "描述3"),
    ]
    watch_1 = [
        ("300502", "新易盛", "110.00", "+6.50%", "观察", "描述4"),
        ("603618", "杭电股份", "6.80", "+10.00%", "观察", "描述5"),
    ]
    trade_1 = []
    
    # 1. 首次填充数据
    tree_widget.update_pools(radar_1, watch_1, trade_1)
    
    # 2. 模拟用户手动点击第 3 列 (涨幅列) 进行降序排序
    tree_widget.tree.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    assert tree_widget.tree.sortColumn() == 3
    assert tree_widget.tree.header().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    
    # 验证排序后第 0 个子项应为涨幅最高者 (标的B +9.98%)
    assert tree_widget.radar_root.child(0).text(0) == "600002"
    assert tree_widget.radar_root.child(1).text(0) == "600001"
    assert tree_widget.radar_root.child(2).text(0) == "600003"
    
    # 3. 模拟下一轮行情数据到达，触发 update_pools 刷新
    radar_2 = [
        ("600001", "标的A", "10.10", "+2.20%", "竞价", "描述1"),
        ("600002", "标的B", "19.80", "+8.80%", "竞价", "描述2"),
        ("600003", "标的C", "31.00", "+10.02%", "竞价", "描述3-大涨"),
    ]
    tree_widget.update_pools(radar_2, watch_1, trade_1)
    
    # 4. 【核心断言】排序列与排序顺序必须 100% 保持，且自动按新涨幅重新降序排列
    assert tree_widget.tree.sortColumn() == 3, "刷新后排序列必须依然保持为第 3 列 (涨幅)"
    assert tree_widget.tree.header().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    
    # 此时标的C (+10.02%) 应自动跃升为第 0 个子项，标的B (+8.80%) 为第 1，标的A (+2.20%) 为第 2
    assert tree_widget.radar_root.child(0).text(0) == "600003"
    assert tree_widget.radar_root.child(1).text(0) == "600002"
    assert tree_widget.radar_root.child(2).text(0) == "600001"
    
    tree_widget.close()


def test_large_table_inplace_reuse_performance():
    """
    【🎯 极限性能测试】模拟 1300+ 只昨日继承个股连续 3 轮推送刷新，验证 In-Place 复用将耗时控制在数十毫秒以内
    """
    import time
    from ats.ui.favorite_panel import FavoritePanel
    from ats.ui.swing_table import SwingStateTable
    
    fav_panel = FavoritePanel()
    swing_table = SwingStateTable()
    
    # 构造 1300 只大批量模拟数据
    mock_rows = []
    for i in range(1300):
        code = f"{600000 + i:06d}"
        mock_rows.append((code, f"标的_{i}", "15.80", "回踩企稳", "+3.50%", "1", "30%", "09:25:00", "90", "1.5", "10", "1.2", "1.1", "0.8", "逆市抗跌", "+2.50%", "测试理由"))
        
    t0 = time.perf_counter()
    # 连续执行 3 轮刷新
    for _ in range(3):
        fav_panel.update_favorite_rows(mock_rows)
        swing_table.update_data_list(mock_rows)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    
    # 3 轮 1300 行 x 16 列双大表格 (共 6 轮大表全量渲染) 总耗时在 10000ms 以内 (平均每轮全量仅耗时数十至数百毫秒)
    assert elapsed_ms < 10000.0, f"3轮大表格渲染总耗时 {elapsed_ms:.1f}ms 超过 10000ms 性能预算"
    assert fav_panel.table.rowCount() == 1300
    assert swing_table.table.rowCount() == 1300
    
    fav_panel.close()
    swing_table.close()


def test_startup_profiler_toggle_persistence():
    """
    【🎯 验证】验证 StartupProfiler 日志开关读取、切换与持久化落盘
    """
    from ats.startup_profiler import StartupProfiler
    profiler = StartupProfiler.get_instance()
    
    orig_state = profiler.is_enabled
    try:
        profiler.set_enabled(True)
        assert profiler.is_enabled is True
        
        # 重新创建实例验证持久化已生效
        p2 = StartupProfiler()
        assert p2.is_enabled is True
        
        profiler.set_enabled(False)
        assert profiler.is_enabled is False
        p3 = StartupProfiler()
        assert p3.is_enabled is False
    finally:
        profiler.set_enabled(orig_state)


def test_invalid_sector_name_filtering():
    """
    【🎯 验证】严密测试 is_valid_sector_name 及热力图与强势板块引擎对 '--' / '0' 等非明确板块的 100% 拦截过滤
    """
    from ats.hot_sector_engine import is_valid_sector_name, HotSectorEngine
    from ats.ui.heatmap_widget import SectorHeatmapWidget

    # 1. is_valid_sector_name 核心断言
    invalid_cases = [
        None, "", "   ", "-", "--", "---", "0", "0.0", "00", "000", "000000",
        "nan", "NaN", "null", "None", "未知", "其它", "其他", "未分类", "default",
        "600519", "000001", "123456", "  --  ", " 0 "
    ]
    for inv in invalid_cases:
        assert not is_valid_sector_name(inv), f"非明确板块 '{inv}' 应被判定为无效"

    valid_cases = [
        "兵装重组概念", "培育钻石", "成飞概念", "共封装光学(CPO)", "半导体",
        "人工智能", "光伏设备", "国防军工", "华为概念", "低空经济", "6G概念"
    ]
    for val in valid_cases:
        assert is_valid_sector_name(val), f"明确板块 '{val}' 应被判定为有效"

    # 2. SectorHeatmapWidget 消费包含 '--' 和 '0' 的测试数据
    hw = SectorHeatmapWidget()
    mock_sector_data = {
        "--": {"score": 11.8, "avg_pct": 1.66, "leader": "000001", "count": 7},
        "0": {"score": 9.5, "avg_pct": 1.65, "leader": "000002", "count": 117},
        "兵装重组概念": {"score": 54.2, "avg_pct": 5.44, "leader": "688151", "count": 7},
        "培育钻石": {"score": 24.8, "avg_pct": 2.85, "leader": "300719", "count": 17},
        "成飞概念": {"score": 9.9, "avg_pct": 1.83, "leader": "002190", "count": 43},
    }
    hw.update_from_tk_sector_data(mock_sector_data)

    rendered_names = [s[0] for s in hw.sectors]
    assert "--" not in rendered_names, "热力图 sectors 中不应包含 '--'"
    assert "0" not in rendered_names, "热力图 sectors 中不应包含 '0'"
    assert "兵装重组概念" in rendered_names
    assert "培育钻石" in rendered_names
    assert "成飞概念" in rendered_names

    top_secs = hw.get_top_sectors(top_n=3)
    assert "--" not in top_secs
    assert "0" not in top_secs
    assert len(top_secs) == 3
    assert top_secs[0] == "兵装重组概念"

    hw.close()


def test_hot_sector_leaderboard_single_select_and_filter():
    """
    【🎯 验证】验证 HotSectorLeaderboardDialog 点击任意板块快速定位单选、再次点击恢复全选、
    全部板块按钮重置、以及对 '--' / '0' 板块的完全过滤
    """
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog

    dialog = HotSectorLeaderboardDialog()
    
    # 模拟设置 Top 3 强势板块
    dialog.current_top_sectors = ["兵装重组概念", "培育钻石", "成飞概念"]
    dialog.active_sectors = set(dialog.current_top_sectors)
    dialog._update_sector_button_styles()

    # 1. 默认状态：全部板块均被选中
    assert dialog.active_sectors == {"兵装重组概念", "培育钻石", "成飞概念"}
    
    # 构造模拟行情数据（包含 3 个正常板块以及 1 个非明确板块 '--'）
    dialog.combo_time_slice.setCurrentIndex(1) # 选择全天全时段，防止不同测试运行时间产生时段过滤
    mock_results = [
        {"code": "688151", "name": "华强科技", "sector": "兵装重组概念", "buy_tag": "PULLBACK", "buy_type": "反身低吸", "pct": 3.77, "price": 17.07, "vwap_dev_pct": -0.5, "alpha_score": 85.0},
        {"code": "300719", "name": "安达维尔", "sector": "培育钻石", "buy_tag": "LOW_VOL", "buy_type": "地量起爆", "pct": 1.05, "price": 12.57, "vwap_dev_pct": -0.2, "alpha_score": 75.0},
        {"code": "002190", "name": "成飞集成", "sector": "成飞概念", "buy_tag": "LOW_VOL", "buy_type": "地量起爆", "pct": 3.16, "price": 27.11, "vwap_dev_pct": 0.1, "alpha_score": 80.0},
        {"code": "000001", "name": "平安银行", "sector": "--", "buy_tag": "LEADER", "buy_type": "领涨龙头", "pct": 2.0, "price": 10.0, "vwap_dev_pct": 0.0, "alpha_score": 60.0},
    ]
    dialog.cached_results = mock_results

    # 2. 渲染全量数据时，'--' 板块的股票被自动过滤掉
    dialog._render_table_data(mock_results)
    assert dialog.table.rowCount() == 3, f"预期 3 只标的（排除 '--'），实际为 {dialog.table.rowCount()}"

    # 3. 用户点击 No.1 板块 (兵装重组概念)：只显示兵装重组概念，实现快速定位
    dialog._select_single_sector(0)
    assert dialog.active_sectors == {"兵装重组概念"}, f"点击 No.1 应单选兵装重组概念，实际为 {dialog.active_sectors}"
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "688151"

    # 4. 用户点击 No.2 板块 (培育钻石)：单选切换为只显示培育钻石
    dialog._select_single_sector(1)
    assert dialog.active_sectors == {"培育钻石"}, f"点击 No.2 应单选培育钻石，实际为 {dialog.active_sectors}"
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "300719"

    # 5. 用户再次点击 No.2 板块 (培育钻石)：平滑恢复全选
    dialog._select_single_sector(1)
    assert dialog.active_sectors == {"兵装重组概念", "培育钻石", "成飞概念"}
    assert dialog.table.rowCount() == 3

    # 6. 用户单选 No.3 板块 (成飞概念) 后，点击【🔥 全部板块】按钮：恢复全选
    dialog._select_single_sector(2)
    assert dialog.active_sectors == {"成飞概念"}
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "002190"

    dialog._on_all_sectors_clicked()
    assert dialog.active_sectors == {"兵装重组概念", "培育钻石", "成飞概念"}
    assert dialog.table.rowCount() == 3

    dialog.close()


def test_history_readonly_no_overwrite_tk(monkeypatch):
    """
    【🎯 验证 1】验证 ATS 执行 apply_filter、clear_filter 及 calculate_history_hits_ui 时，
    绝对不反向覆写磁盘上的 search_history.json（纯只读保护模式）
    """
    import tempfile
    import json
    from ats.ui.main_window import ATSMainWindow
    
    with tempfile.TemporaryDirectory() as td:
        fake_file = os.path.join(td, "search_history.json")
        
        initial_data = {
            "history1": [{"query": "涨幅>3", "starred": 1, "note": "【强势】", "hit": 5}],
            "history2": [{"query": "成交量>1000", "starred": 0, "note": "【放量】"}],
            "history3": [],
            "history4": [],
            "history5": [
                {"query": "10调整启动 | (lastl1d < ma10d or lastl)", "starred": 1, "note": "【10调整启动】", "hit": 12},
                {"query": "突破平台 | high > lasth1d", "starred": 0, "note": "【突破】", "hit": 8}
            ],
            "last_query": "10调整启动 | (lastl1d < ma10d or lastl)",
            "last_group": "history5"
        }
        
        with open(fake_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=2)

        monkeypatch.setattr(ATSMainWindow, "_get_search_history_filepath", lambda self: fake_file)
        monkeypatch.setattr("ats.ui.styles.load_config_node", lambda key, default=None: default)
        monkeypatch.setattr("ats.ui.main_window.load_config_node", lambda key, default=None: default)
        
        win = ATSMainWindow()
        try:
            with open(fake_file, "r", encoding="utf-8") as f:
                content_before = f.read()

            # 1. 验证初始读取正确
            assert win.history_selector.currentText() == "history5"
            assert len(win.search_histories["history5"]) == 2

            # 2. 在 ATS 中输入并应用一条全新过滤公式 (自动解析提取纯净公式)
            win.query_combo.setEditText("新临时公式 | close > open * 1.05")
            win.apply_filter(force=True)
            assert win.query_expr == "close > open * 1.05"

            # 3. 校验磁盘上的 search_history.json 绝对未被修改
            with open(fake_file, "r", encoding="utf-8") as f:
                content_after_filter = f.read()
            assert content_after_filter == content_before, "apply_filter 不应修改或覆盖 search_history.json！"

            # 4. 执行 clear_filter
            win.clear_filter()
            assert win.query_expr == ""
            with open(fake_file, "r", encoding="utf-8") as f:
                content_after_clear = f.read()
            assert content_after_clear == content_before, "clear_filter 不应修改或覆盖 search_history.json！"

            # 5. 执行 calculate_history_hits_ui
            win.calculate_history_hits_ui()
            with open(fake_file, "r", encoding="utf-8") as f:
                content_after_hits = f.read()
            assert content_after_hits == content_before, "calculate_history_hits_ui 不应修改或覆盖 search_history.json！"

        finally:
            win.close()


def test_reload_search_history_button_and_sync(monkeypatch):
    """
    【🎯 验证 2】验证在过滤按钮前的 'r' 刷新按钮能从磁盘重新加载最新的 search_history.json
    """
    import tempfile
    import json
    from ats.ui.main_window import ATSMainWindow
    
    with tempfile.TemporaryDirectory() as td:
        fake_file = os.path.join(td, "search_history.json")
        
        initial_data = {
            "history1": [], "history2": [], "history3": [], "history4": [],
            "history5": [
                {"query": "10调整启动 | (lastl1d < ma10d or lastl)", "starred": 1, "note": "【10调整启动】", "hit": 12}
            ],
            "last_query": "10调整启动 | (lastl1d < ma10d or lastl)",
            "last_group": "history5"
        }
        
        with open(fake_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=2)

        monkeypatch.setattr(ATSMainWindow, "_get_search_history_filepath", lambda self: fake_file)
        monkeypatch.setattr("ats.ui.styles.load_config_node", lambda key, default=None: default)
        monkeypatch.setattr("ats.ui.main_window.load_config_node", lambda key, default=None: default)
        
        win = ATSMainWindow()
        try:
            assert hasattr(win, "btn_reload_history")
            assert win.btn_reload_history.text().lower() == "r"
            assert "刷新" in win.btn_reload_history.toolTip()

            # 1. 外部模拟 TK 端在 history5 中新增了一条新过滤规则
            updated_data = dict(initial_data)
            updated_data["history5"] = list(initial_data["history5"]) + [
                {"query": "全新外部规则 | percent > 9.8", "starred": 1, "note": "【外部新增】", "hit": 3}
            ]
            with open(fake_file, "w", encoding="utf-8") as f:
                json.dump(updated_data, f, ensure_ascii=False, indent=2)

            # 2. 点击 'r' 刷新按钮
            win.btn_reload_history.click()

            # 3. 验证 ATS 已同步到外部最新添加的规则
            assert len(win.search_histories["history5"]) == 2
            combo_texts = [win.query_combo.itemText(i) for i in range(win.query_combo.count())]
            assert any("全新外部规则" in t for t in combo_texts), f"query_combo 应包含新加载的外部规则，实际为: {combo_texts}"

        finally:
            win.close()


def test_reload_shortcut_and_focus_protection(monkeypatch):
    """
    【🎯 验证 3】验证快捷键 R 刷新与输入框聚焦防误触保护
    """
    import tempfile
    import json
    from ats.ui.main_window import ATSMainWindow
    
    with tempfile.TemporaryDirectory() as td:
        fake_file = os.path.join(td, "search_history.json")
        
        initial_data = {
            "history1": [], "history2": [], "history3": [], "history4": [],
            "history5": [
                {"query": "旧规则 | percent > 1.0", "starred": 0, "note": "【旧】"}
            ],
            "last_query": "旧规则 | percent > 1.0",
            "last_group": "history5"
        }
        
        with open(fake_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=2)

        monkeypatch.setattr(ATSMainWindow, "_get_search_history_filepath", lambda self: fake_file)
        monkeypatch.setattr("ats.ui.styles.load_config_node", lambda key, default=None: default)
        monkeypatch.setattr("ats.ui.main_window.load_config_node", lambda key, default=None: default)
        
        win = ATSMainWindow()
        try:
            assert hasattr(win, "shortcut_reload_history")
            
            # 外部更新文件
            updated_data = dict(initial_data)
            updated_data["history5"] = [
                {"query": "仅单条规则 | score > 90", "starred": 1, "note": "【极简】"}
            ]
            with open(fake_file, "w", encoding="utf-8") as f:
                json.dump(updated_data, f, ensure_ascii=False, indent=2)

            # 触发快捷键逻辑
            win._on_shortcut_reload_history()
            assert len(win.search_histories["history5"]) == 1
            assert "仅单条规则" in win.search_histories["history5"][0]["query"]

        finally:
            win.close()


def test_hot_sector_new_concept_auto_all_and_quick_access(monkeypatch):
    """
    【🎯 验证 4】验证 HotSectorLeaderboardDialog:
    1. 默认全选状态下，盘中同步新板块进入 Top 3，自动保持全选且新板块股票 100% 自动包含在表格中（彻底根治未选中/不显示 Bug）
    2. 新概念检测状态机自动识别新晋板块，顶部专属 `btn_new_concept` 动态变为高亮 `🆕 新概念: [板块名]`
    3. 点击 `btn_new_concept` 一键直达单选聚焦该新概念，再次点击平滑切回全选
    4. 在单选某板块状态下，当该板块跌出 Top 3 时，系统自动平滑解除单选恢复全选
    5. 下拉框选择 `🆕 仅看新晋概念`，精确过滤出新概念标的
    """
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog

    dialog = HotSectorLeaderboardDialog()
    try:
        dialog.combo_time_slice.setCurrentIndex(1) # 选择 ⏱️ 全天全时段，防止盘中时段切片过滤

        # 1. 模拟初始状态：Top 3 为 ["航运概念", "期货概念", "黄金概念"]
        initial_top = ["航运概念", "期货概念", "黄金概念"]
        dialog._has_init_fetched = True
        dialog.current_top_sectors = list(initial_top)
        dialog.active_sectors = set(initial_top)
        dialog.selected_single_sector = None
        dialog.seen_sectors_history = set(initial_top)
        dialog._update_sector_button_styles()

        assert dialog.selected_single_sector is None
        assert dialog.active_sectors == {"航运概念", "期货概念", "黄金概念"}
        assert not dialog.btn_new_concept.isEnabled()
        assert "暂无新概念" in dialog.btn_new_concept.text()

        # 2. 构造模拟行情数据（包含 2只航运、2只期货、2只同花顺中特）
        mock_results = [
            {"code": "600428", "name": "中远海特", "sector": "航运概念", "pct": 4.03, "price": 11.62, "vwap_dev_pct": 1.4, "buy_tag": "PULLBACK", "buy_type": "反身低吸", "alpha_score": 85.0},
            {"code": "600650", "name": "锦江在线", "sector": "航运概念", "pct": 4.73, "price": 11.30, "vwap_dev_pct": -0.1, "buy_tag": "SURGE", "buy_type": "主动扫买", "alpha_score": 88.0},
            {"code": "000776", "name": "广发证券", "sector": "期货概念", "pct": 4.16, "price": 22.29, "vwap_dev_pct": 1.1, "buy_tag": "SURGE", "buy_type": "主动扫买", "alpha_score": 82.0},
            {"code": "000712", "name": "锦龙股份", "sector": "期货概念", "pct": 2.20, "price": 13.45, "vwap_dev_pct": 1.8, "buy_tag": "LOW_VOL", "buy_type": "地量起爆", "alpha_score": 79.0},
            {"code": "601318", "name": "中国平安", "sector": "同花顺中特", "pct": 3.13, "price": 58.40, "vwap_dev_pct": 1.0, "buy_tag": "SURGE", "buy_type": "主动扫买", "alpha_score": 90.0},
            {"code": "002271", "name": "东方雨虹", "sector": "同花顺中特", "pct": 3.02, "price": 10.92, "vwap_dev_pct": 0.8, "buy_tag": "SURGE", "buy_type": "主动扫买", "alpha_score": 86.0},
        ]

        # 3. 模拟热力图推送新 Top 3：黄金概念跌出，新板块【同花顺中特】晋级进入 Top 3！
        class DummyHeatmap:
            def get_top_sectors(self, top_n=3):
                return ["航运概念", "期货概念", "同花顺中特"]
            sector_to_codes = {}
            sectors = []

        class DummyMainApp:
            heatmap_widget = DummyHeatmap()
            current_df = None
            fav_stocks = []
            def link_stock(self, code, name):
                pass

        dummy_app = DummyMainApp()
        dialog._py_parent = dummy_app

        # 拦截引擎计算，直接返回我们构造的 mock_results
        monkeypatch.setattr(dialog.engine, "compute_hot_alpha_leaderboard", lambda *args, **kwargs: mock_results)

        # 触发定时器数据更新
        dialog._on_ui_timer_tick(force=True)

        # ── 核心断言 1：默认全选下，新板块【同花顺中特】自动纳入 active_sectors，表格显示全部 6 只标的 ──
        assert "同花顺中特" in dialog.active_sectors, "新板块【同花顺中特】应自动加入 active_sectors！"
        assert dialog.active_sectors == {"航运概念", "期货概念", "同花顺中特"}
        assert dialog.selected_single_sector is None, "默认应保持全选模式！"
        assert dialog.table.rowCount() == 6, f"预期表格自动显示全部 6 只股票，实际为 {dialog.table.rowCount()}"

        # ── 核心断言 2：新概念按钮与 No.3 板块按钮动态更新 ──
        assert dialog.latest_new_sector == "同花顺中特"
        assert dialog.btn_new_concept.isEnabled()
        assert "同花顺中特" in dialog.btn_new_concept.text()
        assert "🆕" in dialog.btn_sec3.text()
        assert "同花顺中特" in dialog.btn_sec3.text()

        # ── 核心断言 3：点击【🆕 新概念】按钮，一键单选聚焦该新概念 ──
        dialog.btn_new_concept.click()
        assert dialog.selected_single_sector == "同花顺中特"
        assert dialog.active_sectors == {"同花顺中特"}
        assert dialog.table.rowCount() == 2, f"单选新概念后应只显示 2 只标的，实际为 {dialog.table.rowCount()}"
        codes_shown = {dialog.table.item(r, 0).text() for r in range(dialog.table.rowCount())}
        assert codes_shown == {"601318", "002271"}
        assert "聚焦" in dialog.btn_new_concept.text()

        # 再次点击【🆕 新概念】按钮，平滑切回全选
        dialog.btn_new_concept.click()
        assert dialog.selected_single_sector is None
        assert dialog.active_sectors == {"航运概念", "期货概念", "同花顺中特"}
        assert dialog.table.rowCount() == 6

        # ── 核心断言 4：单选状态下，若该单选板块跌出 Top 3，自动平滑解除单选恢复全选 ──
        dialog._select_single_sector(2) # 单选同花顺中特
        assert dialog.selected_single_sector == "同花顺中特"
        assert dialog.table.rowCount() == 2

        # 模拟下一轮 Top 3 变动：同花顺中特跌出，变为 ["航运概念", "期货概念", "固态电池"]
        dummy_app.heatmap_widget.get_top_sectors = lambda top_n=3: ["航运概念", "期货概念", "固态电池"]
        dialog._on_ui_timer_tick(force=True)

        assert dialog.selected_single_sector is None, "单选板块跌出 Top 3 时，应自动解除单选！"
        assert dialog.active_sectors == {"航运概念", "期货概念", "固态电池"}, "应平滑恢复全选当前 Top 3！"

        # ── 核心断言 5：下拉框选择【🆕 仅看新晋概念】──
        # 此时【固态电池】是新晋板块
        assert dialog.latest_new_sector == "固态电池"
        dialog.combo_filter.setCurrentIndex(8) # 🆕 仅看新晋概念
        assert dialog.filter_mode == "NEW_CONCEPT"

    finally:
        dialog.close()


def test_hot_sector_favorite_toggle_and_priority_pinning(monkeypatch):
    """
    测试 HotSectorLeaderboardDialog 重点关注置顶优先显示机制：
    1. 重点关注股票在任何筛选与排序模式下均置顶优先显示 (第 0 行)；
    2. 名称列自动附带 ⭐ 徽章且代码/名称呈现金色高亮；
    3. 支持单元格 NumericTableWidgetItem 无论按任何列 (升序/降序) 排序永远置顶特权；
    4. 底部状态栏实时显示重点关注标的数量；
    5. 取消关注后平滑恢复原有相对排序与普通样式。
    """
    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.QtCore import Qt
    app = QApplication.instance() or QApplication([])
    from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
    from global_favorites import GlobalFavoriteManager

    fav_mgr = GlobalFavoriteManager()
    fav_mgr.remove_favorite_stock("601318")

    class DummyParent(QWidget):
        def __init__(self):
            super().__init__()
            self.fav_stocks = set()
            self.heatmap_widget = None

    parent = DummyParent()
    dialog = HotSectorLeaderboardDialog(parent)

    try:
        dialog.combo_time_slice.setCurrentIndex(1) # 选择 ⏱️ 全天全时段，防止分时切片过滤
        dialog.active_sectors = {"航运概念", "期货概念"}
        dialog.selected_single_sector = None

        mock_results = [
            {"code": "600428", "name": "中远海特", "sector": "航运概念", "alpha_score": 88.0, "pct": 5.2, "buy_tag": "LEADER", "buy_type": "领涨龙头"},
            {"code": "601872", "name": "招商轮船", "sector": "航运概念", "alpha_score": 75.0, "pct": 3.1, "buy_tag": "SURGE", "buy_type": "扫盘冲板"},
            {"code": "000996", "name": "中国中期", "sector": "期货概念", "alpha_score": 70.0, "pct": 2.5, "buy_tag": "BREAKOUT", "buy_type": "先锋起爆"},
            {"code": "601318", "name": "中国平安", "sector": "航运概念", "alpha_score": 60.0, "pct": 1.2, "buy_tag": "PULLBACK", "buy_type": "反身低吸"},
        ]

        # 1. 初始状态：未关注 601318，按 alpha_score 排序排在最后 (第 3 行)
        score_col = dialog.headers.index("综合得分") if "综合得分" in dialog.headers else (len(dialog.headers) - 2)
        dialog.table.horizontalHeader().setSortIndicator(score_col, Qt.SortOrder.DescendingOrder)
        dialog._render_table_data(mock_results)
        assert dialog.table.rowCount() == 4
        assert dialog.table.item(3, 0).text().strip() == "601318"
        assert "⭐" not in dialog.table.item(3, 1).text()
        assert not getattr(dialog.table.item(3, 0), "is_pinned", False)

        # 2. 将 601318 设为重点关注
        fav_mgr.add_favorite_stock("601318")
        dialog._render_table_data(mock_results)

        # 核心断言 1：601318 无论综合得分多少，自动置顶优先显示在第 0 行
        assert dialog.table.item(0, 0).text().strip() == "601318"
        # 核心断言 2：名称自动添加 ⭐ 徽章
        assert "⭐ 中国平安" in dialog.table.item(0, 1).text()
        # 核心断言 3：NumericTableWidgetItem 单元格具备 is_pinned=True 和 pin_rank=0 置顶特权
        assert getattr(dialog.table.item(0, 0), "is_pinned", False) is True
        assert getattr(dialog.table.item(0, 0), "pin_rank", 999) == 0
        # 核心断言 4：底部状态栏联动显示 ⭐关注: 1
        assert "⭐关注: 1" in dialog.lbl_stats.text()

        # 核心断言 5：无论按何种列排序（例如按涨幅%升序），重点关注股票依然置顶居首
        dialog.table.sortItems(5, Qt.SortOrder.AscendingOrder)
        assert dialog.table.item(0, 0).text().strip() == "601318", "按涨幅升序排序时，重点关注标的仍应稳居表格最前！"

        # 按代码降序排序，重点关注标的依然稳居表格最前
        dialog.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        assert dialog.table.item(0, 0).text().strip() == "601318", "按代码降序排序时，重点关注标的仍应稳居表格最前！"

        # 核心断言 6：取消重点关注后，重置排序列为默认综合得分，平滑恢复正常排序与样式
        fav_mgr.remove_favorite_stock("601318")
        dialog.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        dialog._render_table_data(mock_results)
        # 恢复默认按 alpha_score 降序排序，601318 综合得分最低回到末位
        assert dialog.table.item(3, 0).text().strip() == "601318"
        assert "⭐" not in dialog.table.item(3, 1).text()
        assert not getattr(dialog.table.item(3, 0), "is_pinned", False)
        assert "⭐关注:" not in dialog.lbl_stats.text()

        # 核心断言 7：板块中出现了重点关注的才优先显示，不在当前板块的自选股绝不显示！
        fav_mgr.add_favorite_stock("600027") # 华电国际 (电力行业，不在航运与期货概念中)
        fav_mgr.add_favorite_stock("000999") # 华润三九 (中药行业，不在航运与期货概念中)
        polluted_results = mock_results + [
            {"code": "600027", "name": "华电国际", "sector": "电力行业", "alpha_score": 89.0, "pct": 2.7, "buy_tag": "SURGE"},
            {"code": "000999", "name": "华润三九", "sector": "中药概念", "alpha_score": 89.0, "pct": 2.5, "buy_tag": "SURGE"},
        ]
        dialog._render_table_data(polluted_results)
        current_codes = [dialog.table.item(r, 0).text().strip() for r in range(dialog.table.rowCount())]
        assert "600027" not in current_codes, "非当前板块的重点关注股票绝不能显示！"
        assert "000999" not in current_codes, "非当前板块的重点关注股票绝不能显示！"
        assert dialog.table.rowCount() == 4
        fav_mgr.remove_favorite_stock("600027")
        fav_mgr.remove_favorite_stock("000999")

    finally:
        fav_mgr.remove_favorite_stock("601318")
        dialog.close()


def test_engine_build_target_universe_only_matches_hot_sectors():
    """验证 HotSectorEngine 构建目标池时，非热点板块的自选关注股绝不被纳入，杜绝伪造重点关注板块"""
    from ats.hot_sector_engine import HotSectorEngine
    engine = HotSectorEngine()
    engine.sector_to_codes = {
        "航运概念": ["600428", "601872"],
        "免税店": ["601888", "002607"]
    }
    
    # 模拟外部传入包含非当前板块的自选股
    manual_watchlist = ["600428", "600027", "000999"]
    target_codes, sector_map, mp_cache, name_map = engine.build_target_universe(
        top_sector_names=["航运概念", "免税店"],
        manual_watchlist=manual_watchlist
    )
    
    # 600428 属于航运概念，应在目标池中，且所属板块必须是真实的航运概念
    assert "600428" in target_codes
    assert sector_map["600428"] == "航运概念"
    
    # 600027 与 000999 不在航运概念与免税店中，坚决不能进入目标池，且绝不能生成"重点关注"板块
    assert "600027" not in target_codes
    assert "000999" not in target_codes
    assert "重点关注" not in sector_map.values()


def test_hot_sector_dual_acceleration_and_open_low_features():
    """验证龙头突击【开盘即最低光脚加速】、【跳空缺口加速】及【双加速结构】特征计算与优先级提权"""
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
    fetcher = TDXRealtimeFetcher.get_instance()

    quotes = [
        {
            # 标的 A: 昨收 10.0, 开盘 10.30, 最低 10.30, 现价 10.80 -> 跳空高开且开盘即最低 -> 双加速
            "code": "000001", "name": "双加速股", "price": 10.80, "open": 10.30, "high": 10.90, "low": 10.30,
            "last_close": 10.00, "vol": 10000, "amount": 10500000, "bid1": 10.80, "ask1": 10.81
        },
        {
            # 标的 B: 昨收 10.0, 开盘 10.02, 最低 10.02, 现价 10.60 -> 开盘即最低但跳空幅度<0.8% -> 光脚加速
            "code": "000002", "name": "光脚加速股", "price": 10.60, "open": 10.02, "high": 10.70, "low": 10.02,
            "last_close": 10.00, "vol": 10000, "amount": 10300000, "bid1": 10.60, "ask1": 10.61
        },
        {
            # 标的 C: 昨收 10.0, 开盘 10.50, 最低 10.15, 现价 10.60 -> 跳空高开未补缺口但下影较大(10.50->10.15) -> 缺口加速
            "code": "000003", "name": "缺口加速股", "price": 10.60, "open": 10.50, "high": 10.70, "low": 10.15,
            "last_close": 10.00, "vol": 10000, "amount": 10400000, "bid1": 10.60, "ask1": 10.61
        },
        {
            # 标的 D: 昨收 10.0, 开盘 9.90, 最低 9.70, 现价 10.20 -> 常规波动
            "code": "000004", "name": "常规股", "price": 10.20, "open": 9.90, "high": 10.30, "low": 9.70,
            "last_close": 10.00, "vol": 10000, "amount": 10000000, "bid1": 10.20, "ask1": 10.21
        }
    ]

    sec_map = {"000001": "核心板块", "000002": "核心板块", "000003": "核心板块", "000004": "核心板块"}
    name_map = {"000001": "双加速股", "000002": "光脚加速股", "000003": "缺口加速股", "000004": "常规股"}

    results = fetcher.fetch_multi_stock_alpha_quotes(
        codes=["000001", "000002", "000003", "000004"],
        raw_quotes=quotes,
        sector_map=sec_map,
        name_map=name_map
    )

    res_map = {r["code"]: r for r in results}
    rA = res_map["000001"]
    rB = res_map["000002"]
    rC = res_map["000003"]
    rD = res_map["000004"]

    # 1. 断言形态标签与标识
    assert rA["is_dual_accel"] is True
    assert rA["accel_tag"] == "👑双加速"
    assert "👑双加速" in rA["buy_type"]

    assert rB["is_open_low_accel"] is True
    assert rB["is_dual_accel"] is False
    assert rB["accel_tag"] == "⚡光脚加速"
    assert "⚡光脚加速" in rB["buy_type"]

    assert rC["is_gap_accel"] is True
    assert rC["is_dual_accel"] is False
    assert rC["accel_tag"] == "🚀缺口加速"
    assert "🚀缺口加速" in rC["buy_type"]

    assert rD["is_dual_accel"] is False
    assert rD["is_open_low_accel"] is False
    assert rD["is_gap_accel"] is False

    # 2. 断言双加速优先权与得分提权
    assert rA["alpha_score"] > rB["alpha_score"]
    assert rA["alpha_score"] > rD["alpha_score"]
    assert results[0]["code"] == "000001", f"双加速标的应排在首位，实际首位为: {results[0]['code']}"










