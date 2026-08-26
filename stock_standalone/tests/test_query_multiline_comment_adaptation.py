# -*- coding: utf-8 -*-
"""
tests/test_query_multiline_comment_adaptation.py
验证 Query 引擎对多行模式与单行混杂 # 注释的自适应脱敏、平衡括号解析以及 ATS UI 历史查询提取联动。
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from query_engine_util import PandasQueryEngine


def test_user_flattened_query_comment_desensitization():
    """测试用户截图中的单行混杂 # 注释公式能够被完美脱敏提取，且绝不返回空串或全员命中"""
    engine = PandasQueryEngine()
    
    user_q = (
        "# 1. 均线与中长期趋势底色：站上20日生命线，5日均线不低于10日均线 (拒绝空头排列) "
        "close >= ma20d and ma5d >= ma10d * 0.995 and (SWL >= SWS or SWL >= ma20d) and ma5d >= ma51d * 0.998 "
        "# 2. 结构防守：低点连续抬升 (Higher Lows 防守线，允许小阴洗盘，但绝不破低) "
        "and low >= lastl1d * 0.988 and lastl1d >= lastl2d * 0.988 "
        "# 3. 两种蓄势形态二选一 (A: abs 振幅剧烈试盘 OR B: 极度缩量小步垫高成本) "
        "and ( {OR: abs(per{1-8}d) >= 6.0} or (vol <= last6vol * 1.15 and abs(ma5d - ma10d) / ma10d <= 0.018) ) "
        "# 4. 支撑安全垫约束：紧贴20日线或支撑位上方安全带 (拒绝高位追高，盈亏比极高) "
        "and (close - ma20d) / ma20d <= 0.068 and low >= support * 0.985 "
        "# 5. 锁仓地量与起爆区间 (成交额 >= 1500万，今日涨幅处于 -1.2% ~ 3.8% 蓄势位) "
        "and vol <= last6vol * 1.40 and amount >= 15000000 and percent >= -1.2 and percent <= 3.8"
    )
    
    cleaned = engine._preprocess_query(user_q)
    assert cleaned != "", "预处理后的公式绝不能为空！"
    assert "close >= ma20d" in cleaned
    assert "SWL >= SWS" in cleaned
    assert "amount >= 15000000" in cleaned
    assert "拒绝空头排列" not in cleaned
    assert "Higher Lows" not in cleaned
    assert engine._is_balanced(cleaned) is True, "脱敏后公式括号必须严格平衡"


def test_multiline_query_with_comments():
    """测试标准多行模式下的 # 注释与行尾注释"""
    engine = PandasQueryEngine()
    
    multi_q = """
    # 1. 站稳翻转线 (Reversal Line) 与 30日支撑位
    close >= reversal_line * 0.995 and close >= support * 0.99
    
    # 2. 短期均线多头共振
    and ma5d >= ma10d * 0.998 and (SWL >= SWS or SWL >= ma20d)
    
    # 3. 涨幅控制与缩量蓄势
    and percent >= -1.5 and percent <= 4.5 # 行尾注释说明
    and vol <= last6vol * 1.5
    """
    
    cleaned = engine._preprocess_query(multi_q)
    assert cleaned != ""
    assert "close >= reversal_line * 0.995" in cleaned
    assert "SWL >= SWS" in cleaned
    assert "行尾注释说明" not in cleaned
    assert engine._is_balanced(cleaned) is True


def test_quote_protection_with_chinese_strings():
    """测试包含中文字符串的函数 (如 .str.contains('半导体')) 内部中文字符得到严格保护"""
    engine = PandasQueryEngine()
    
    q_str = "category.str.contains('半导体') and close > ma5d # 行业龙头"
    cleaned = engine._preprocess_query(q_str)
    
    assert "半导体" in cleaned
    assert "行业龙头" not in cleaned
    assert "close > ma5d" in cleaned


def test_ats_main_window_get_real_query_decoupling():
    """测试 ATS 主窗口 _get_real_query 优先从 search_histories 恢复原始多行脚本"""
    from ats.ui.main_window import ATSMainWindow
    
    raw_multiline_query = "# 标题\nclose > ma20d\nand percent > 2.0"
    item = {"query": raw_multiline_query, "note": "多行策略", "hit": 35, "starred": 0}
    
    class DummyMainWindow:
        _format_history_item_local = ATSMainWindow._format_history_item_local
        _get_real_query = ATSMainWindow._get_real_query
        
        def __init__(self):
            self.search_histories = {"history1": [item]}
            self.history_selector = type("H", (), {"currentText": lambda s: "history1"})()
            disp = self._format_history_item_local(item)
            self.query_combo = type("Q", (), {"currentText": lambda s: disp})()

    win = DummyMainWindow()
    result_q = win._get_real_query()
    assert result_q == raw_multiline_query, "应精准还原原始多行 query，而不是单行压扁文本"
    assert "\n" in result_q


def test_multiline_reversal_strategy_execution():
    """测试用户在提示中反馈的 6 节点多行反转策略能够完整解析且执行零报错"""
    engine = PandasQueryEngine()
    
    q = """# 1. 站稳翻转线 (Reversal Line) 与 30日支撑位
close >= reversal_line * 0.995 and close >= support * 0.99

# 2. 动能底背离修复：MACD 绿柱持续缩短且 DIF 连续拐头
and macddif >= macdlast2 and macdlast2 >= macdlast3

# 3. 价格突破昨日与前日高点 (脱离下降通道压制)
and close >= lasth1d * 0.998 and close >= lasth2d * 0.995

# 4. SWL 短波重心与 SWS 慢波极度收敛 (差值在 2.5% 以内，临界金叉)
and abs((SWL - SWS) / SWS) <= 0.025

# 5. 异动弹性：近 9 天内有过绝对幅度 > 5% 的大震荡 (有主力博弈痕迹)
and {OR: abs(per{1-9}d) >= 5.0}

# 6. 排除高位追高，锁定温和启动位
and percent >= 0.5 and percent <= 4.5 and vol <= last6vol * 1.5"""

    cleaned = engine._preprocess_query(q)
    assert cleaned != ""
    assert "SWL 短波重心" not in cleaned
    assert "reversal_line" in cleaned
    assert "macddif >= macdlast2" in cleaned
    assert engine._is_balanced(cleaned) is True
    
    # 验证在 mock DataFrame 上的执行
    df_mock = pd.DataFrame({
        'close': [10.0, 20.0],
        'reversal_line': [9.9, 21.0],
        'support': [9.8, 19.0],
        'macddif': [0.5, 0.2],
        'macdlast2': [0.4, 0.3],
        'macdlast3': [0.3, 0.4],
        'lasth1d': [9.9, 20.1],
        'lasth2d': [9.8, 20.0],
        'SWL': [10.1, 20.0],
        'SWS': [10.0, 20.0],
        'per1d': [6.0, 1.0],
        'percent': [2.5, 1.0],
        'vol': [1000, 2000],
        'last6vol': [1500, 1500]
    }, index=['600001', '600002'])
    
    res = engine.execute(df_mock, q)
    assert isinstance(res, pd.DataFrame)
    assert len(res) == 1
    assert '600001' in res.index
    assert engine.last_error == ""

