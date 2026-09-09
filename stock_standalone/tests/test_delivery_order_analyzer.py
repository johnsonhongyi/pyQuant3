# -*- coding: utf-8 -*-
"""
自动化测试: DeliveryOrderEngine 与 DeliveryOrderAnalyzerWindow
"""
import os
import sys

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from delivery_order_analyzer_gui import DeliveryOrderEngine, DeliveryOrderAnalyzerWindow
from PyQt6 import QtWidgets

TEST_FILE = r'C:\Users\Johnson\Documents\20260909_交割单查询.txt'


def test_delivery_order_engine_parsing():
    """测试交割单引擎解析与费率核算准确性"""
    assert os.path.exists(TEST_FILE), f"测试文件不存在: {TEST_FILE}"
    engine = DeliveryOrderEngine()
    ok, msg = engine.load_file(TEST_FILE)
    assert ok is True, f"解析失败: {msg}"
    assert len(engine.df) == 61, f"总记录数应为 61，实际为 {len(engine.df)}"

    s = engine.summary_data
    assert s['is_exempt_five'] is True, "沪深A股应判定为【免五】生效"

    # 沪深A股
    hs_buy = s['hs_buy']
    hs_sell = s['hs_sell']
    assert hs_buy['count'] == 10, f"买入应为 10 笔，实际 {hs_buy['count']}"
    assert hs_sell['count'] == 10, f"卖出应为 10 笔，实际 {hs_sell['count']}"

    # 买入全佣率 ~ 万分之 0.754
    assert 0.753 <= hs_buy['all_comm_rate'] <= 0.756, f"买入全佣率偏离: {hs_buy['all_comm_rate']}"
    # 卖出全佣率 ~ 万分之 0.754
    assert 0.753 <= hs_sell['all_comm_rate'] <= 0.756, f"卖出全佣率偏离: {hs_sell['all_comm_rate']}"
    # 卖出印花税率 ~ 万分之 5.00
    assert 4.99 <= hs_sell['tax_rate'] <= 5.01, f"卖出印花税率偏离: {hs_sell['tax_rate']}"

    # 场内ETF全包佣金率 ~ 万分之 0.50
    etf = s['etf']
    assert etf['count'] == 1
    assert 0.499 <= etf['all_comm_rate'] <= 0.501, f"ETF全佣率偏离: {etf['all_comm_rate']}"

    # 北交所保底 5 元
    bj = s['bj']
    assert bj['count'] == 3
    assert bj['all_comm'] == 15.0, f"北交所3笔全佣合计应为 15.00 元，实际 {bj['all_comm']}"


def test_delivery_order_gui_instantiation():
    """测试 GUI 界面实例化与组件渲染"""
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication([])

    win = DeliveryOrderAnalyzerWindow(default_file_path=TEST_FILE)

    # 校验卡片与表格填充
    assert win.table_hs.rowCount() == 20
    assert win.table_other.rowCount() == 4  # 1笔ETF + 3笔北交所
    assert win.table_repo.rowCount() == 28

    # 切换筛选
    win.btn_filter_buy.setChecked(True)
    assert win.table_hs.rowCount() == 10
    win.btn_filter_sell.setChecked(True)
    assert win.table_hs.rowCount() == 10
    win.btn_filter_all.setChecked(True)
    assert win.table_hs.rowCount() == 20
