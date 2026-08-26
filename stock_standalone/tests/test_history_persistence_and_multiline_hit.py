# -*- coding: utf-8 -*-
"""
tests/test_history_persistence_and_multiline_hit.py
验证 ATS 主界面历史策略选择持久化、多行带中文注释公式的 Hit 测试与展示格式一致性。
"""

import sys
import os
import pytest
import pandas as pd
from unittest.mock import MagicMock

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PyQt6.QtWidgets import QApplication
from query_engine_util import query_engine
from stock_logic_utils import test_code_against_queries as run_test_code_against_queries

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_multiline_complex_strategy_hit_evaluation():
    """验证用户反馈的双模态蓄势多行策略在 test_code_against_queries 下的精准执行与命中"""
    user_query = """# 1. 均线与中长期趋势底色：站上20日生命线，5日均线不低于10日均线 (拒绝空头排列)
close >= ma20d and ma5d >= ma10d * 0.995 and (SWL >= SWS or SWL >= ma20d) and ma5d >= ma51d * 0.998
# 2. 结构防守：低点连续抬升 (Higher Lows 防守线，允许小阴洗盘，但绝不破低)
and low >= lastl1d * 0.988 and lastl1d >= lastl2d * 0.988
# 3. 两种蓄势形态二选一 (A: abs 振幅剧烈试盘 OR B: 极度缩量小步垫高成本)
and ( {OR: abs(per{1-8}d) >= 6.0} or (vol <= last6vol * 1.15 and abs(ma5d - ma10d) / ma10d <= 0.018) )
# 4. 支撑安全垫约束：紧贴20日线或支撑位上方安全带 (拒绝高位追高，盈亏比极高)
and (close - ma20d) / ma20d <= 0.068 and low >= support * 0.985
# 5. 锁仓地量与起爆区间 (成交额 >= 1500万，今日涨幅处于 -1.2% ~ 3.8% 蓄势位)
and vol <= last6vol * 1.40 and amount >= 15000000 and percent >= -1.2 and percent <= 3.8"""

    # 构造能够命中该策略的 mock 标的
    df_hit = pd.DataFrame([{
        'code': '600001',
        'close': 10.2,
        'ma20d': 10.0,
        'ma5d': 10.1,
        'ma10d': 10.1,
        'ma51d': 10.0,
        'SWL': 10.2,
        'SWS': 10.1,
        'low': 10.0,
        'lastl1d': 9.9,
        'lastl2d': 9.8,
        'per1d': 6.5,
        'vol': 1000,
        'last6vol': 1200,
        'support': 10.0,
        'amount': 20000000,
        'percent': 1.5
    }]).set_index('code')

    queries = [{
        "query": user_query,
        "note": "【双模态蓄势·精准起爆前夕策略】（多行排版版）",
        "starred": 1,
        "hit": ""
    }]

    results = run_test_code_against_queries(df_hit, queries)
    assert len(results) == 1
    assert results[0]["hit"] == 1
    assert results[0]["note"] == "【双模态蓄势·精准起爆前夕策略】（多行排版版）"


def test_history_format_and_real_query_recovery(qapp):
    """测试历史策略格式化 _format_history_item_local 与 _get_real_query 互逆解析"""
    from ats.ui.main_window import ATSMainWindow
    
    mw = MagicMock()
    mw.history_selector = MagicMock()
    mw.history_selector.currentText.return_value = "history1"
    
    raw_query = """# 1. 均线趋势
close >= ma20d and ma5d >= ma10d
# 2. 涨幅
and percent >= 1.0"""
    
    item = {
        "query": raw_query,
        "note": "【双模态蓄势·精准起爆前夕策略】（多行排版版）",
        "starred": 1,
        "hit": 787
    }
    mw.search_histories = {"history1": [item]}
    
    # 格式化展示文本
    disp = ATSMainWindow._format_history_item_local(mw, item)
    assert "【双模态蓄势·精准起爆前夕策略】（多行排版版）" in disp
    assert "[Hit: 787]" in disp
    assert "close >= ma20d" in disp
    
    # 测试通过展示文本逆向获取真实多行 query
    mw.query_combo = MagicMock()
    mw.query_combo.currentText.return_value = disp
    
    extracted_q = ATSMainWindow._get_real_query(mw)
    assert extracted_q == raw_query
    assert "\n" in extracted_q
