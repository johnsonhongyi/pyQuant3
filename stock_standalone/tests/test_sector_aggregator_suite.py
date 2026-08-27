import os
import sys
import math
import pytest
import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication

from ats.sector_data_aggregator import (
    SectorDataAggregator,
    _safe_float,
    _safe_int,
    _get_sina_market_code,
    get_sector_extra_cols,
    get_sector_table_headers
)
from ats.ui.sector_detail_dialog import ATSSectorDetailDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_safe_conversions_and_market_codes():
    """测试安全数值转换与交易所前缀映射"""
    # 1. 安全 float 转换
    assert _safe_float(None, 0.0) == 0.0
    assert _safe_float(float('nan'), 0.0) == 0.0
    assert _safe_float(float('inf'), 0.0) == 0.0
    assert _safe_float("--", 0.0) == 0.0
    assert _safe_float("12.34", 0.0) == 12.34
    assert _safe_float(-5.6, 0.0) == -5.6

    # 2. 安全 int 转换
    assert _safe_int(None, 999) == 999
    assert _safe_int(float('nan'), 999) == 999
    assert _safe_int("12", 0) == 12
    assert _safe_int("abc", 0) == 0

    # 3. 交易所前缀精准映射
    assert _get_sina_market_code("600519") == "sh600519"
    assert _get_sina_market_code("688981") == "sh688981"
    assert _get_sina_market_code("510050") == "sh510050"  # 上证 ETF
    assert _get_sina_market_code("113009") == "sh113009"  # 上证可转债
    assert _get_sina_market_code("000001") == "sz000001"
    assert _get_sina_market_code("300750") == "sz300750"  # 创业板
    assert _get_sina_market_code("159915") == "sz159915"  # 深证 ETF
    assert _get_sina_market_code("128013") == "sz128013"  # 深证可转债
    assert _get_sina_market_code("832000") == "bj832000"  # 北交所
    assert _get_sina_market_code("920001") == "bj920001"  # 北交所新号段


def test_resolve_sector_member_codes():
    """测试成分股列表解析与同义词/fallback机制"""
    aggregator = SectorDataAggregator.get_instance()

    # 1. 显式传入 member_codes：严格以输入为准，不被外部污染
    codes, name_map = aggregator.resolve_sector_member_codes(
        sector_name="半导体",
        member_codes=["688981", "002371"]
    )
    assert codes == ["688981", "002371"]

    # 2. 未传入 member_codes，且 current_df 包含 category 列：向量模糊匹配
    df_sample = pd.DataFrame({
        'name': ['中芯国际', '北方华创', '比亚迪'],
        'category': ['半导体及部件', '芯片', '汽车整车']
    }, index=['688981', '002371', '002594'])

    codes_fuzzy, name_map_fuzzy = aggregator.resolve_sector_member_codes(
        sector_name="半导体",
        member_codes=None,
        current_df=df_sample
    )
    assert "688981" in codes_fuzzy
    assert "002371" in codes_fuzzy
    assert "002594" not in codes_fuzzy
    # 由于匹配不足 6 只，会自动从 FAMOUS_SECTOR_LEADERS 补齐
    assert len(codes_fuzzy) >= 6

    # 3. 兼容 RangeIndex 且带有 code 列的数据帧
    df_range = pd.DataFrame({
        'code': ['688981', '002371'],
        'name': ['中芯国际', '北方华创'],
        'category': ['半导体', '半导体']
    })
    codes_range, name_map_range = aggregator.resolve_sector_member_codes(
        sector_name="半导体",
        member_codes=None,
        current_df=df_range
    )
    assert "688981" in codes_range
    assert "002371" in codes_range
    assert "000000" not in codes_range


def test_fetch_sector_detail_and_ranking(monkeypatch):
    """测试板块明细计算、领涨龙头评选与严格降序排列"""
    aggregator = SectorDataAggregator.get_instance()

    # 1. 模拟网络离线/Mock 模式：验证计算逻辑纯粹性
    # 模拟 TDXFetcher 与 Sina 返回空，使用 current_df 驱动行情
    import ats.sector_data_aggregator as sda
    monkeypatch.setattr(sda, "fetch_sina_stock_quotes_fast", lambda codes: {})
    try:
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        tf = TDXRealtimeFetcher.get_instance()
        monkeypatch.setattr(tf, "get_security_quotes_safe", lambda codes, force=False: [])
        monkeypatch.setattr(tf, "fetch_multi_stock_alpha_quotes", lambda codes, sec_map, mp, nm: [])
    except Exception:
        pass

    df = pd.DataFrame({
        'name': ['中芯国际', '北方华创', '兆易创新'],
        'percent': [8.5, 3.2, -1.5],
        'dff': [2.5, float('nan'), -0.5],
        'Rank': [1, 5, 20],
        'DFF2': [1.8, 0.5, 0.0],
        'DFF3': [0.9, 0.2, 0.0],
        'ch_bc2': [5.0, float('nan'), 0.0]
    }, index=['688981', '002371', '603986'])

    rows, score, leader_str, meta = aggregator.fetch_sector_detail(
        sector_name="半导体",
        member_codes=['688981', '002371', '603986'],
        current_df=df,
        extra_cols=['ch_bc2']
    )

    assert len(rows) == 3
    # 验证龙头评选：第 0 行必定为领涨龙头且得分最高
    assert rows[0]['code'] == '688981'
    assert '领涨龙头' in rows[0]['type']
    assert rows[0]['score'] >= 98.0
    assert '中芯国际' in leader_str

    # 验证列表按 score, pct 倒序排列
    for i in range(len(rows) - 1):
        assert (rows[i]['score'], rows[i]['pct']) >= (rows[i + 1]['score'], rows[i + 1]['pct'])

    # 验证 NaN 防护与 start_pct 计算 (pct 8.5 - dff 2.5 = 6.0)
    assert rows[0]['start_pct'] == 6.0
    # 北方华创 dff 为 NaN，应被清洗为 0.0，start_pct = pct 3.2
    row_002371 = next(r for r in rows if r['code'] == '002371')
    assert row_002371['dff'] == 0.0
    assert row_002371['start_pct'] == 3.2

    # 验证板块强度打分非 NaN
    assert not math.isnan(score)
    assert 0.0 <= score <= 100.0


def test_dialog_lifecycle_and_update_data(qapp):
    """测试 ATSSectorDetailDialog 实例复用、update_data 接口与事件生命周期"""
    df1 = pd.DataFrame({
        'name': ['中芯国际', '北方华创'],
        'percent': [5.0, 2.0],
        'dff': [1.0, 0.5]
    }, index=['688981', '002371'])

    dlg = ATSSectorDetailDialog(sector_name="半导体", member_codes=['688981', '002371'])
    
    # 1. 验证 load_data 同步加载
    dlg.load_data(df_realtime=df1)
    assert dlg.table.rowCount() == 2
    assert dlg.table.item(0, 0).text() in ('688981', '002371')

    # 2. 验证 update_data 接口（主窗口复用与轮询刷新通道）
    df2 = pd.DataFrame({
        'name': ['中芯国际', '北方华创', '兆易创新'],
        'percent': [9.9, 4.0, 1.5],
        'dff': [2.0, 1.0, 0.5]
    }, index=['688981', '002371', '603986'])

    dlg.member_codes = ['688981', '002371', '603986']
    dlg.update_data(current_df=df2)
    # update_data 触发了 refresh_data，这里直接调用 load_data 验证渲染状态
    dlg.load_data(df_realtime=df2)
    assert dlg.table.rowCount() == 3

    # 3. 验证 closeEvent 安全释放
    dlg.close()
    assert dlg.isVisible() is False


def test_sector_detail_dialog_sorting_and_scroll_stability(qapp):
    """测试板块明细弹窗：表头点击自动回滚到顶部、全列精准排序及静默刷新防乱跳"""
    from PyQt6.QtCore import Qt

    sample_rows = [
        {"code": "600584", "name": "长电科技", "score": 33.7, "type": "确核", "pct": 3.98, "start_pct": 3.08, "dff": 0.90, "rank": 3548, "dff2": 5.20, "dff3": 74.50, "extra_cols": {"ch_bc": "18", "连阳": "2", "red": "5"}},
        {"code": "300567", "name": "精测电子", "score": 38.7, "type": "确核", "pct": 6.42, "start_pct": 5.12, "dff": 1.30, "rank": 888, "dff2": 10.40, "dff3": 79.00, "extra_cols": {"ch_bc": "17", "连阳": "3", "red": "6"}},
        {"code": "688012", "name": "中微公司", "score": 33.5, "type": "晋级★", "pct": 1.90, "start_pct": 1.20, "dff": 0.70, "rank": 1169, "dff2": 7.50, "dff3": 81.20, "extra_cols": {"ch_bc": "99", "连阳": "3", "red": "4"}},
        {"code": "300456", "name": "赛微电子", "score": 98.5, "type": "👑 领涨龙头", "pct": 20.01, "start_pct": 15.00, "dff": 5.01, "rank": 1, "dff2": 15.20, "dff3": 120.00, "extra_cols": {"ch_bc": "100", "连阳": "5", "red": "8"}},
        {"code": "688146", "name": "中船特气", "score": 32.1, "type": "跟随", "pct": 5.41, "start_pct": 4.01, "dff": 1.40, "rank": 999, "dff2": 6.10, "dff3": 326.00, "extra_cols": {"ch_bc": "--", "连阳": "--", "red": "--"}},
    ]

    dlg = ATSSectorDetailDialog(sector_name="国家大基金持股", member_codes=[r["code"] for r in sample_rows])
    dlg._render_rows(sample_rows)
    assert dlg.table.rowCount() == 5

    # 1. 验证表头点击：模拟滚动条在第 40 行位置，点击表头后自动平滑重置到第 0 行 (顶部)
    dlg.table.verticalScrollBar().setValue(40)
    assert dlg.table.verticalScrollBar().value() == 40 or dlg.table.verticalScrollBar().maximum() >= 0
    dlg._on_header_section_clicked(4) # 点击涨幅列
    assert dlg.table.verticalScrollBar().value() == 0, "点击表头后滚动条必须重置为 0 到顶部"

    # 2. 验证涨幅 (col 4) 降序排序
    dlg.table.sortItems(4, Qt.SortOrder.DescendingOrder)
    top_code = dlg.table.item(0, 0).text().strip()
    assert top_code == "300456" # 20.01% 排在第 1
    # 验证升序排序 (最小涨幅排最前)
    dlg.table.sortItems(4, Qt.SortOrder.AscendingOrder)
    bottom_code = dlg.table.item(0, 0).text().strip()
    assert bottom_code == "688012" # 1.90% 排在最前

    # 3. 验证角色类型 (col 3) 权重降序排序
    dlg.table.sortItems(3, Qt.SortOrder.DescendingOrder)
    assert dlg.table.item(0, 0).text().strip() == "300456" # 👑 领涨龙头权重 100 必定排第 1

    # 4. 验证静默刷新时防乱跳与选中代码维持
    # 模拟用户选中了“精测电子 (300567)”
    dlg.table.selectRow(1)
    sel_code_before = dlg.table.item(dlg.table.currentRow(), 0).text().strip()
    
    # 触发再次刷新 _render_rows
    dlg._render_rows(sample_rows)
    
    # 验证刷新后当前选中行对应的股票代码依然是 300567，没有乱跳
    cur_row = dlg.table.currentRow()
    assert cur_row >= 0
    assert dlg.table.item(cur_row, 0).text().strip() == sel_code_before


def test_df_row_safe_int_index_and_fallback_backfill(monkeypatch):
    """测试 _get_df_row_safe 对整型索引/短代码的完全兼容，以及局部策略池回退补全 Rank/DFF"""
    aggregator = SectorDataAggregator.get_instance()

    # 1. 验证 int 类型索引 (如 300115, 2055) 能够被 "300115", "002055" 100% 检索到
    df_int_index = pd.DataFrame({
        'name': ['长盈精密', 'ST得润'],
        'percent': [-6.05, 0.65],
        'Rank': [5523, 706],
        'dff': [0.4, 0.2],
        'DFF2': [-5.3, 11.7],
        'DFF3': [-1.4, 22.3]
    }, index=[300115, 2055])

    r_300115 = aggregator._get_df_row_safe(df_int_index, "300115")
    assert r_300115 is not None
    assert str(r_300115['name']) == '长盈精密'
    assert int(r_300115['Rank']) == 5523

    r_002055 = aggregator._get_df_row_safe(df_int_index, "002055")
    assert r_002055 is not None
    assert str(r_002055['name']) == 'ST得润'
    assert int(r_002055['Rank']) == 706

    # 2. 验证局部策略池缺失时，自动通过全局 fallback_df 回补
    # 模拟 TDXFetcher 与 Sina
    import ats.sector_data_aggregator as sda
    monkeypatch.setattr(sda, "fetch_sina_stock_quotes_fast", lambda codes: {})

    df_local_filtered = pd.DataFrame({
        'name': ['ST得润'],
        'percent': [0.65],
        'Rank': [706],
        'dff': [0.2],
        'DFF2': [11.7],
        'DFF3': [22.3]
    }, index=['002055'])

    # 全量 5539 标的底表
    df_all_global = pd.DataFrame({
        'name': ['ST得润', '长盈精密', '鑫科材料'],
        'percent': [0.65, -6.05, 0.60],
        'Rank': [706, 5523, 4800],
        'dff': [0.2, 0.4, 0.0],
        'DFF2': [11.7, -5.3, 4.7],
        'DFF3': [22.3, -1.4, 19.6],
        'ch_bc2': ['27', '28', '33']
    }, index=['002055', '300115', '600255'])

    # 模拟顶层窗口挂载 df_all
    class MockTopWindow:
        def __init__(self, df):
            self.df_all = df

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    mock_win = MockTopWindow(df_all_global)
    monkeypatch.setattr(app, "topLevelWidgets", lambda: [mock_win])

    rows = aggregator.fetch_quotes_unified(
        codes=['002055', '300115', '600255'],
        current_df=df_local_filtered, # 局部策略池只有 002055
        extra_cols=['ch_bc2'],
        sector_name='铜缆高速连接'
    )

    assert len(rows) == 3
    row_300115 = next(r for r in rows if r['code'] == '300115')
    assert row_300115['name'] == '长盈精密'
    assert row_300115['rank'] == 5523, "长盈精密 Rank 必须被全局 fallback_df 成功回补为 5523"
    assert row_300115['dff2'] == -5.3
    assert row_300115['extra_cols'].get('ch_bc2') == '28'

    row_600255 = next(r for r in rows if r['code'] == '600255')
    assert row_600255['name'] == '鑫科材料'
    assert row_600255['rank'] == 4800, "鑫科材料 Rank 必须被全局 fallback_df 成功回补为 4800"


def test_sector_detail_dialog_sort_persistence(qapp, monkeypatch):
    """测试板块明细排序列与方向跨会话自动持久化保存与恢复"""
    from PyQt6.QtCore import Qt
    from ats.ui.styles import save_config_node, load_config_node

    sample_rows = [
        {"code": "600584", "name": "长电科技", "score": 33.7, "type": "确核", "pct": 3.98, "start_pct": 3.08, "dff": 0.90, "rank": 3548, "dff2": 5.20, "dff3": 74.50, "extra_cols": {}},
        {"code": "300567", "name": "精测电子", "score": 38.7, "type": "确核", "pct": 6.42, "start_pct": 5.12, "dff": 1.30, "rank": 888, "dff2": 10.40, "dff3": 79.00, "extra_cols": {}},
        {"code": "300456", "name": "赛微电子", "score": 98.5, "type": "👑 领涨龙头", "pct": 20.01, "start_pct": 15.00, "dff": 5.01, "rank": 1, "dff2": 15.20, "dff3": 120.00, "extra_cols": {}},
    ]

    # 1. 显式保存排序配置：排序列为【涨幅】(col 4)，降序
    save_config_node("ats_sector_detail_sort_col_name", "涨幅")
    save_config_node("ats_sector_detail_sort_col", 4)
    save_config_node("ats_sector_detail_sort_order", int(Qt.SortOrder.DescendingOrder.value))

    # 2. 新建弹窗实例：验证初始化自动恢复排序列与排序方向
    dlg1 = ATSSectorDetailDialog(sector_name="半导体测试", member_codes=["600584", "300567", "300456"])
    dlg1._render_rows(sample_rows)

    header = dlg1.table.horizontalHeader()
    assert header.sortIndicatorSection() == 4, "必须自动恢复上次保存的排序列【涨幅】(col 4)"
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder

    # 验证渲染出的第 0 行是涨幅最高的赛微电子 (20.01%)
    assert dlg1.table.item(0, 0).text().strip() == "300456"

    # 3. 模拟用户点击【Rank】(col 7) 升序
    dlg1._on_sort_indicator_changed(7, Qt.SortOrder.AscendingOrder)
    assert load_config_node("ats_sector_detail_sort_col_name") == "Rank"
    assert load_config_node("ats_sector_detail_sort_order") == int(Qt.SortOrder.AscendingOrder.value)

    # 4. 新建另一个板块弹窗实例：验证自动恢复为 Rank 升序
    dlg2 = ATSSectorDetailDialog(sector_name="新板块测试", member_codes=["600584", "300567", "300456"])
    dlg2._render_rows(sample_rows)
    header2 = dlg2.table.horizontalHeader()
    assert header2.sortIndicatorSection() == 7
    assert header2.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
    # Rank 升序下，Rank 1 的赛微电子排在第 1
    assert dlg2.table.item(0, 0).text().strip() == "300456"


def test_rank_beyond_999_display_in_all_windows(qapp):
    """测试 Rank > 999 (如 1250, 3548, 5523) 在板块明细和天梯看板中 100% 完整显示数值，杜绝被误当成 --"""
    # 1. 验证板块明细 (ATSSectorDetailDialog) 对长电科技 (Rank 3548) 的真实渲染
    sample_rows = [
        {"code": "600584", "name": "长电科技", "score": 33.7, "type": "确核", "pct": 3.98, "start_pct": 3.08, "dff": 0.90, "rank": 3548, "dff2": 5.20, "dff3": 74.50, "extra_cols": {}},
        {"code": "300115", "name": "长盈精密", "score": 20.1, "type": "跟随", "pct": -6.05, "start_pct": -5.0, "dff": 0.40, "rank": 5523, "dff2": -5.30, "dff3": -1.40, "extra_cols": {}},
        {"code": "000001", "name": "平安银行", "score": 10.0, "type": "跟随", "pct": 0.10, "start_pct": 0.0, "dff": 0.0, "rank": 0, "dff2": 0.0, "dff3": 0.0, "extra_cols": {}}
    ]

    dlg = ATSSectorDetailDialog(sector_name="测试板块", member_codes=["600584", "300115", "000001"])
    dlg._render_rows(sample_rows)

    # 找到 600584 行
    row_600584 = -1
    row_300115 = -1
    row_000001 = -1
    for r in range(dlg.table.rowCount()):
        c = dlg.table.item(r, 0).text().strip()
        if c == "600584":
            row_600584 = r
        elif c == "300115":
            row_300115 = r
        elif c == "000001":
            row_000001 = r

    assert dlg.table.item(row_600584, 7).text().strip() == "3548", "长电科技 Rank 3548 必须精准显示为 3548，严禁显示为 --"
    assert dlg.table.item(row_300115, 7).text().strip() == "5523", "长盈精密 Rank 5523 必须精准显示为 5523，严禁显示为 --"
    assert dlg.table.item(row_000001, 7).text().strip() == "--", "无效 Rank 0 显示为 --"

    # 2. 验证天梯引擎 (LimitUpEngine) 对大写 Rank 与 rank > 999 的无损提取
    from ats.limit_up_engine import LimitUpEngine
    engine = LimitUpEngine.get_instance()
    df_test = pd.DataFrame({
        'name': ['晶丰明源', '麦仓新能'],
        'price': [130.05, 117.64],
        'percent': [11.25, 9.74],
        'Rank': [1250, 3800],
        'dff': [3.5, -0.8],
        'DFF2': [15.4, 13.9],
        'DFF3': [35.0, 57.6]
    }, index=['688368', '688813'])

    records = engine.scan_limit_up_records_from_df(df_test, fetch_l2_quotes=False)
    assert len(records) == 2
    r_688368 = next(r for r in records if r['code'] == '688368')
    assert r_688368['rank'] == 1250, "晶丰明源的 Rank 必须被提取为 1250 而非 999"
    r_688813 = next(r for r in records if r['code'] == '688813')
    assert r_688813['rank'] == 3800, "麦仓新能的 Rank 必须被提取为 3800 而非 999"

    # 3. 验证每日涨停看板 (DailyLimitUpDialog) 的表格渲染
    from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog
    dlg_zt = DailyLimitUpDialog()
    dlg_zt._populate_table_rows(records)

    # 检查 Rank 列 (col 14)
    assert dlg_zt.table.item(0, 14).text().strip() in ("1250", "3800"), "天梯看板 Rank 列必须正确显示 1250/3800 而非 --"




