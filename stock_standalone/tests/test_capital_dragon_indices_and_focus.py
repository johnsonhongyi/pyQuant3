# -*- coding: utf-8 -*-
import os
import sys
import pytest
import pandas as pd
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

# 确保导入路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ats.capital_dragon_engine import (
    CapitalDragonEngine, is_major_index, is_index_or_fund, MAJOR_INDEX_CODES, _clean_code
)
from ats.ui.capital_dragon_panel import (
    CapitalDragonPanel, PERSIST_KEY_DRAGON_FOCUS_STOCKS
)
from ats.ui.styles import (
    load_config_node, save_config_node
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestCapitalDragonIndicesAndFocus:
    """资金主线指数置顶、独立重点关注与3-Tier排序稳定性专项测试"""

    def test_major_index_identification(self):
        """测试主要指数识别准确性：上证/深证/创业板/北证/中小板为指数，平安银行为个股"""
        assert is_major_index('999999', '上证指数') is True
        assert is_major_index('000001', '上证指数') is True
        assert is_major_index('399001', '深证成指') is True
        assert is_major_index('399006', '创业板指') is True
        assert is_major_index('899050', '北证50') is True
        assert is_major_index('399005', '中小100') is True

        # 平安银行是个股，绝不可被判定为主要指数
        assert is_major_index('000001', '平安银行') is False
        assert is_major_index('000001', '银行A') is False
        assert is_major_index('000852', '石化机械') is False

    def test_engine_major_indices_top_prioritization(self):
        """测试引擎层分析中主要指数始终置顶并赋予中军角色与最高权重"""
        engine = CapitalDragonEngine.get_instance()
        data = {
            'code': ['999999', '399001', '399006', '300750', '600519', '002466'],
            'name': ['上证指数', '深证成指', '创业板指', '宁德时代', '贵州茅台', '天齐锂业'],
            'close': [3350.0, 10500.0, 2150.0, 260.0, 1500.0, 38.0],
            'percent': [1.2, 0.8, 2.5, 4.2, -0.5, 9.9],
            'amount': [780000000000, 860000000000, 380000000000, 8500000000, 7200000000, 3500000000],
            'volume': [50000000, 60000000, 30000000, 300000, 50000, 900000],
            'lastv1d': [48000000, 59000000, 28000000, 280000, 52000, 800000],
            'category': ['综合指数/ETF', '综合指数/ETF', '综合指数/ETF', '固态电池', '白酒', '锂电池'],
            'nclose': [3345.0, 10480.0, 2140.0, 258.0, 1505.0, 37.5]
        }
        df = pd.DataFrame(data).set_index('code')
        report = engine.analyze_capital_dragon_universe(df, sh_pct=1.2)

        converged = report.get('dragon_records_converged', [])
        assert len(converged) > 0

        # 指数必须全部进入收敛池且稳居前三
        top_codes = [r['code'] for r in converged[:3]]
        assert '999999' in top_codes
        assert '399001' in top_codes
        assert '399006' in top_codes

        for r in converged[:3]:
            assert r.get('is_index', False) is True
            assert '容量' in r.get('role', '') or '指数' in r.get('role', '')

    def test_capital_dragon_panel_focus_persistence(self, qapp):
        """测试资金主线独立重点关注的设置、取消与独立持久化"""
        # 初始清理
        save_config_node(PERSIST_KEY_DRAGON_FOCUS_STOCKS, [])

        panel = CapitalDragonPanel()
        assert panel.is_dragon_focused('300750') is False
        assert panel.is_dragon_focused('600519') is False

        # 切换关注 300750 (宁德时代)
        panel.toggle_dragon_focus('300750', '宁德时代')
        assert panel.is_dragon_focused('300750') is True
        saved = load_config_node(PERSIST_KEY_DRAGON_FOCUS_STOCKS, [])
        assert '300750' in saved

        # 再添加 600519
        panel.toggle_dragon_focus('600519', '贵州茅台')
        assert panel.is_dragon_focused('600519') is True
        saved = load_config_node(PERSIST_KEY_DRAGON_FOCUS_STOCKS, [])
        assert '600519' in saved

        # 取消 300750
        panel.toggle_dragon_focus('300750', '宁德时代')
        assert panel.is_dragon_focused('300750') is False
        saved = load_config_node(PERSIST_KEY_DRAGON_FOCUS_STOCKS, [])
        assert '300750' not in saved
        assert '600519' in saved

    def test_3tier_sorting_invariant_across_multiple_columns(self, qapp):
        """
        核心验收测试：无论按成交额、涨幅、现价还是代码排序，
        Tier 0 (主要指数) 永远绝对最前，
        Tier 1 (资金主线专属重点关注) 永远紧随其后，
        Tier 2 (普通真龙标的) 永远在重点关注之后！
        """
        panel = CapitalDragonPanel()
        panel.extreme_perf_mode = False

        # 设置 300750 为重点关注标的
        panel.dragon_focus_stocks = {'300750'}

        # 模拟 3 档标的
        # Tier 0 指数：999999 (上证指数, amt=7800亿, pct=1.2%, price=3350), 399006 (创业板指, amt=3800亿, pct=2.5%, price=2150)
        # Tier 1 重点关注：300750 (宁德时代, amt=85亿, pct=4.2%, price=260)
        # Tier 2 普通标的：600519 (茅台, amt=72亿, pct=-0.5%, price=1500), 002466 (天齐, amt=35亿, pct=9.9%, price=38)
        mock_dragons = [
            {
                'code': '600519', 'name': '贵州茅台', 'role': '🛡️ 容量中军', 'sector': '白酒',
                'price': 1500.0, 'pct': -0.5, 'amount_yi': 72.0, 'turnover': 0.4,
                'vol_ratio': 0.95, 'action_type': '冲高回踩', 'buy_zone': '1490-1505',
                'stop_loss': 1460.0, 'reason': '白酒白马', 'priority': 80,
                'buy_type_sort_score': 50.0, 'is_index': False
            },
            {
                'code': '999999', 'name': '上证指数', 'role': '🛡️ 趋势容量中军', 'sector': '综合指数/ETF',
                'price': 3350.0, 'pct': 1.2, 'amount_yi': 7800.0, 'turnover': 1.1,
                'vol_ratio': 1.05, 'action_type': '🛡️ 综合指数', 'buy_zone': '3330-3360',
                'stop_loss': 3300.0, 'reason': '大盘基石', 'priority': 98,
                'buy_type_sort_score': 40.0, 'is_index': True
            },
            {
                'code': '002466', 'name': '天齐锂业', 'role': '🚀 主线先锋', 'sector': '锂电池',
                'price': 38.0, 'pct': 9.9, 'amount_yi': 35.0, 'turnover': 8.5,
                'vol_ratio': 2.3, 'action_type': '👑双加速', 'buy_zone': '37.0-38.5',
                'stop_loss': 35.5, 'reason': '锂电龙头', 'priority': 90,
                'buy_type_sort_score': 100.0, 'is_index': False
            },
            {
                'code': '399006', 'name': '创业板指', 'role': '🛡️ 趋势容量中军', 'sector': '综合指数/ETF',
                'price': 2150.0, 'pct': 2.5, 'amount_yi': 3800.0, 'turnover': 1.8,
                'vol_ratio': 1.15, 'action_type': '🛡️ 综合指数', 'buy_zone': '2130-2160',
                'stop_loss': 2100.0, 'reason': '成长风格', 'priority': 98,
                'buy_type_sort_score': 40.0, 'is_index': True
            },
            {
                'code': '300750', 'name': '宁德时代', 'role': '🛡️ 容量中军', 'sector': '固态电池',
                'price': 260.0, 'pct': 4.2, 'amount_yi': 85.0, 'turnover': 1.2,
                'vol_ratio': 1.4, 'action_type': '🚀缺口加速', 'buy_zone': '256-262',
                'stop_loss': 250.0, 'reason': '电池中军', 'priority': 88,
                'buy_type_sort_score': 90.0, 'is_index': False
            }
        ]

        # 初始未排序列渲染
        panel._render_table(mock_dragons)
        assert panel.table.rowCount() == 5

        def get_current_table_codes():
            return [panel.table.item(r, 0).text().strip() for r in range(panel.table.rowCount())]

        # 1. 验证默认渲染顺序：Tier 0 (999999, 399006) -> Tier 1 (300750) -> Tier 2 (002466, 600519)
        codes = get_current_table_codes()
        assert set(codes[:2]) == {'999999', '399006'}
        assert codes[2] == '300750'
        assert set(codes[3:]) == {'002466', '600519'}

        # 2. 点击【成交额】列 (Col 7) 降序排序
        panel.table.sortItems(7, Qt.SortOrder.DescendingOrder)
        codes = get_current_table_codes()
        # Tier 0 (999999 7800亿 > 399006 3800亿)
        assert codes[0] == '999999'
        assert codes[1] == '399006'
        # Tier 1 (300750 85亿)
        assert codes[2] == '300750'
        # Tier 2 (600519 72亿 > 002466 35亿)
        assert codes[3] == '600519'
        assert codes[4] == '002466'

        # 3. 点击【成交额】列 (Col 7) 升序排序
        panel.table.sortItems(7, Qt.SortOrder.AscendingOrder)
        codes = get_current_table_codes()
        # Tier 0 依然在前！内部按成交额升序 (399006 3800亿 < 999999 7800亿)
        assert codes[0] == '399006'
        assert codes[1] == '999999'
        # Tier 1 (300750) 紧随指数之后！
        assert codes[2] == '300750'
        # Tier 2 内部按成交额升序 (002466 35亿 < 600519 72亿)
        assert codes[3] == '002466'
        assert codes[4] == '600519'

        # 4. 点击【涨幅%】列 (Col 5) 降序排序
        panel.table.sortItems(5, Qt.SortOrder.DescendingOrder)
        codes = get_current_table_codes()
        # Tier 0 依然在前！(399006 +2.5% > 999999 +1.2%)
        assert codes[0] == '399006'
        assert codes[1] == '999999'
        # Tier 1 (300750 +4.2%)
        assert codes[2] == '300750'
        # Tier 2 (002466 +9.9% > 600519 -0.5%)
        assert codes[3] == '002466'
        assert codes[4] == '600519'

        # 5. 点击【现价】列 (Col 4) 降序排序
        panel.table.sortItems(4, Qt.SortOrder.DescendingOrder)
        codes = get_current_table_codes()
        # Tier 0 指数在前 (999999 3350 > 399006 2150)
        assert codes[0] == '999999'
        assert codes[1] == '399006'
        # Tier 1 (300750 260)
        assert codes[2] == '300750'
        # Tier 2 (600519 1500 > 002466 38)
        assert codes[3] == '600519'
        assert codes[4] == '002466'

        # 6. 点击【代码】列 (Col 0) 升序排序
        panel.table.sortItems(0, Qt.SortOrder.AscendingOrder)
        codes = get_current_table_codes()
        # Tier 0 指数依然稳居最前！
        assert set(codes[:2]) == {'999999', '399006'}
        # Tier 1 依然在中间！
        assert codes[2] == '300750'
        # Tier 2 依然在最后！
        assert set(codes[3:]) == {'002466', '600519'}

    def test_star_prefix_and_linkage_cleanliness(self, qapp):
        """测试重点关注标的星号显示、样式微光以及联动选股时不污染代码与名称"""
        panel = CapitalDragonPanel()
        panel.dragon_focus_stocks = {'300750'}

        mock_dragons = [
            {
                'code': '999999', 'name': '上证指数', 'role': '🛡️ 趋势容量中军', 'sector': '综合指数/ETF',
                'price': 3350.0, 'pct': 1.2, 'amount_yi': 7800.0, 'turnover': 1.1,
                'vol_ratio': 1.05, 'action_type': '🛡️ 综合指数', 'buy_zone': '3330-3360',
                'stop_loss': 3300.0, 'reason': '大盘基石', 'priority': 98,
                'buy_type_sort_score': 40.0, 'is_index': True
            },
            {
                'code': '300750', 'name': '宁德时代', 'role': '🛡️ 容量中军', 'sector': '固态电池',
                'price': 260.0, 'pct': 4.2, 'amount_yi': 85.0, 'turnover': 1.2,
                'vol_ratio': 1.4, 'action_type': '🚀缺口加速', 'buy_zone': '256-262',
                'stop_loss': 250.0, 'reason': '电池中军', 'priority': 88,
                'buy_type_sort_score': 90.0, 'is_index': False
            }
        ]

        panel._render_table(mock_dragons)

        # 检查统计栏中重点关注只数展示
        assert "⭐重点: <font color='#ffd700'><b>1只</b></font>" in panel.lbl_stats.text()

        # 检查重点关注行：名称列应显示 ⭐ 宁德时代
        row_focus = -1
        for r in range(panel.table.rowCount()):
            if panel.table.item(r, 0).text().strip() == '300750':
                row_focus = r
                break
        assert row_focus >= 0

        name_item = panel.table.item(row_focus, 1)
        assert "⭐ 宁德时代" == name_item.text().strip()
        # 背景色应为暗金高质感微光
        bg_col = name_item.background().color()
        assert bg_col.alpha() > 0

        # 测试选股联动信号：必须清洗为纯净代码 "300750" 与名称 "宁德时代"，不带 ⭐
        received_signals = []
        panel.stock_selected.connect(lambda c, n: received_signals.append((c, n)))

        panel._on_row_clicked(name_item)
        assert len(received_signals) == 1
        assert received_signals[0] == ('300750', '宁德时代')
