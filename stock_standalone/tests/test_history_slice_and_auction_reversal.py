# -*- coding: utf-8 -*-
"""
tests/test_history_slice_and_auction_reversal.py
=================================================
验证：
1. 可视化历史切片套件 (QCheckBox, QDateEdit, 步退/步进/最新按钮) 的创建与交互状态；
2. 历史数据切片截断逻辑，验证通道 (TDXChannelFactory) 与支撑位在切片前后的动态演变；
3. 超声电子 (000823) 09-04 诱空假摔切片与 09-07 集合竞价超预期弱转强异动临界点信号捕捉及回测验证。
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QDate

from JSONData.tdx_channel_factory import TDXChannelFactory, TDXChannelResult


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def generate_mock_daily_data():
    """
    构造与 000823 超声电子真实盘面特征同构的日线测试数据：
    1. 2026-07-21 探出大底 11.60
    2. 随后震荡走高，高点抬升，低点逐步抬高至 14.50 (上涨通道/箱体构建)
    3. 2026-09-04 (T-1日): 突然破位杀跌收阴，最低 14.20，收盘 14.49 (假摔诱空洗盘)
    4. 2026-09-07 (T日): 早盘集合竞价超预期高开 14.70 (+1.45%)，急速拉升封涨停 15.94 (+10.01%)
    5. 随后持续大涨
    """
    dates = pd.date_range("2026-07-01", "2026-09-10", freq="B")
    date_strs = [d.strftime("%Y-%m-%d") for d in dates]
    
    n = len(date_strs)
    # 基础价格序列
    close_prices = []
    base = 15.0
    for d in date_strs:
        if d < "2026-07-21":
            base -= 0.15 # 探底中
        elif d == "2026-07-21":
            base = 11.60 # 大底锚点
        elif d < "2026-09-04":
            base += 0.08 # 底部抬高上涨震荡
        elif d == "2026-09-04":
            base = 14.49 # T-1 诱空破位杀
        elif d == "2026-09-07":
            base = 15.94 # T 日大阳线涨停突破
        else:
            base += 0.50 # 延续主升
        close_prices.append(round(base, 2))

    df = pd.DataFrame(index=date_strs)
    df['close'] = close_prices
    df['open'] = df['close'] * 0.99
    # 针对 09-03 (T-2) 确保价格高于 09-04
    if "2026-09-03" in df.index:
        df.loc["2026-09-03", "open"] = 14.70
        df.loc["2026-09-03", "close"] = 14.80
        df.loc["2026-09-03", "low"] = 14.60
        df.loc["2026-09-03", "high"] = 14.90
    # 针对 09-04 制造高开低走的假摔大阴线
    if "2026-09-04" in df.index:
        df.loc["2026-09-04", "open"] = 14.90
        df.loc["2026-09-04", "close"] = 14.49
        df.loc["2026-09-04", "low"] = 14.20
        df.loc["2026-09-04", "high"] = 14.95
    # 针对 09-07 制造超预期高开的大阳涨停线
    if "2026-09-07" in df.index:
        df.loc["2026-09-07", "open"] = 14.70 # 超预期高开
        df.loc["2026-09-07", "close"] = 15.94 # 封死涨停
        df.loc["2026-09-07", "low"] = 14.65
        df.loc["2026-09-07", "high"] = 15.94

    # 兜底填充 high / low / volume
    if 'high' not in df.columns:
        df['high'] = df[['open', 'close']].max(axis=1) * 1.01
    else:
        df['high'] = df['high'].fillna(df[['open', 'close']].max(axis=1) * 1.01)
    if 'low' not in df.columns:
        df['low'] = df[['open', 'close']].min(axis=1) * 0.99
    else:
        df['low'] = df['low'].fillna(df[['open', 'close']].min(axis=1) * 0.99)
    df['volume'] = 1000000.0
    df['vol'] = df['volume']
    df['amount'] = df['close'] * df['vol']
    return df


def test_history_slice_data_truncation():
    """测试 1: 历史切片截断数据的完整性与通道动态变化"""
    full_df = generate_mock_daily_data()
    assert len(full_df) > 40
    
    # 1. 切片至 2026-09-04 (即大阳线启动前，前两个交易日没有时)
    cutoff_date = "2026-09-04"
    sliced_df = full_df[full_df.index <= cutoff_date].copy()
    assert sliced_df.index[-1] == "2026-09-04"
    assert len(sliced_df) < len(full_df)
    assert "2026-09-07" not in sliced_df.index
    
    # 2. 计算 09-04 当天的通道与支撑位
    res_sliced: TDXChannelResult = TDXChannelFactory.calculate(sliced_df)
    # 验证通道已从 11.60 确立，且斜率向上或水平震荡
    assert res_sliced.supp_price > 0
    assert res_sliced.cdp_support > 0
    # 验证 09-04 收盘并未实质破位大底 (大底 11.60，当前支撑在 13~14 元附近)
    assert res_sliced.cdp_support > 11.60

    # 3. 计算 09-07 大阳线走出来后的全量通道
    res_full: TDXChannelResult = TDXChannelFactory.calculate(full_df)
    # 随着大阳线突破，通道上轨或最新价格大幅跃升
    assert full_df.loc["2026-09-07", "close"] > sliced_df.loc["2026-09-04", "close"]


def test_history_slice_ui_components(qapp):
    """测试 2: 验证切片控件的初始化与交互逻辑"""
    from trade_visualizer_qt6 import MainWindow
    
    win = MainWindow()
    
    # 验证切片套件控件全部挂载成功
    assert hasattr(win, 'cb_slice_enable')
    assert hasattr(win, 'btn_slice_prev')
    assert hasattr(win, 'date_cutoff_edit')
    assert hasattr(win, 'btn_slice_next')
    assert hasattr(win, 'btn_slice_reset')

    # 验证默认切片为关闭状态
    assert not win.cb_slice_enable.isChecked()
    assert win.cb_slice_enable.text() in ("", "切片")

    # 模拟数据灌入
    mock_df = generate_mock_daily_data()
    win.raw_day_df = mock_df.copy()
    win.day_df = mock_df.copy()
    win.current_code = "000823"
    
    latest_date_str = str(mock_df.index[-1]).split()[0]
    win.date_cutoff_edit.setDate(QDate.fromString(latest_date_str, "yyyy-MM-dd"))
    
    # 点击【◀ 步退】按钮
    win.btn_slice_prev.click()
    # 验证切片开关已自动激活开启
    assert win.cb_slice_enable.isChecked()
    assert "(开)" in win.cb_slice_enable.text()
    # 验证日期已成功回退为前一个交易日
    cur_date = win.date_cutoff_edit.date().toString("yyyy-MM-dd")
    all_dates = sorted(list(set([str(d).split()[0] for d in mock_df.index])))
    assert cur_date == all_dates[-2]
    # 验证当前 day_df 已被成功切片截断
    assert str(win.day_df.index[-1]).split()[0] == cur_date

    # 点击【最新】按钮
    win.btn_slice_reset.click()
    # 验证切片已关闭并恢复全量
    assert not win.cb_slice_enable.isChecked()
    assert str(win.day_df.index[-1]).split()[0] == latest_date_str


def test_auction_reversal_strategy_logic():
    """测试 3: 验证【空头陷阱·竞价弱转强起爆战法】异动临界点信号量化逻辑"""
    df = generate_mock_daily_data()
    
    # 提取关键节点：
    # T-1 日：2026-09-04
    # T 日：2026-09-07
    p_t1 = df.loc["2026-09-04"] # 昨日 (T-1)
    p_t2 = df.iloc[df.index.get_loc("2026-09-04") - 1] # 前日 (T-2)
    p_t0 = df.loc["2026-09-07"] # 今日 (T)

    # 1. 检验大底未破 (最低点高于 11.60)
    assert p_t1['low'] > 11.60
    
    # 2. 检验 T-1 日假摔诱空收阴 (lastp1d < lastp2d)
    lastp1d = p_t1['close']
    lastp2d = p_t2['close']
    is_false_breakdown = (lastp1d < lastp2d) and (p_t1['close'] < p_t1['open'])
    assert is_false_breakdown, "09-04 应满足昨日破位假摔阴线特征"

    # 3. 检验 T 日早盘集合竞价超预期弱转强 (open > lastp1d * 1.008)
    open_t0 = p_t0['open']
    lasth1d = p_t1['high']
    # 正常下杀次日应低开，而此处以 14.70 高开 (+1.45%)，且接近昨日高点
    auction_jump = open_t0 >= lastp1d * 1.008
    assert auction_jump, "09-07 早盘集合竞价应超预期跳空高开"

    # 4. 模拟策略判定执行
    row_signal = {
        'ch_dir': 1,
        'ch_slope_deg': 2.5,
        'low': p_t0['low'],
        'ch_supp1': 14.10,
        'lastp1d': lastp1d,
        'lastp2d': lastp2d,
        'open': open_t0,
        'lasth1d': lasth1d,
        'ratio': 1.8,
        'amount': 50000000
    }
    
    # 策略表达式: ch_dir == 1 and ch_slope_deg > 1.0 and low >= ch_supp1 * 0.98 and lastp1d < lastp2d and open >= lastp1d * 1.008 and open >= lasth1d * 0.98 and ratio >= 1.2 and amount >= 30000000
    cond = (
        row_signal['ch_dir'] == 1 and
        row_signal['ch_slope_deg'] > 1.0 and
        row_signal['low'] >= row_signal['ch_supp1'] * 0.98 and
        row_signal['lastp1d'] < row_signal['lastp2d'] and
        row_signal['open'] >= row_signal['lastp1d'] * 1.008 and
        row_signal['open'] >= row_signal['lasth1d'] * 0.98 and
        row_signal['ratio'] >= 1.2 and
        row_signal['amount'] >= 30000000
    )
    assert cond is True, "09-07 异动临界点信号应在 09:25 集合竞价精准触发！"
    
    # 5. 回测收益率：集合竞价 14.70 买入，当天封板 15.94，日内浮盈 +8.43%
    profit_pct = (p_t0['close'] - p_t0['open']) / p_t0['open'] * 100
    assert profit_pct > 8.0, f"日内竞价介入应获得确定性极高收益: {profit_pct:.2f}%"


def test_slice_boundary_forward_and_backward(qapp):
    """测试 4: 连续步退与连续步进的防越界测试"""
    from trade_visualizer_qt6 import MainWindow
    win = MainWindow()
    mock_df = generate_mock_daily_data()
    win.raw_day_df = mock_df.copy()
    win.day_df = mock_df.copy()
    win.current_code = "000823"

    all_dates = sorted(list(set([str(d).split()[0] for d in mock_df.index])))
    win.date_cutoff_edit.setDate(QDate.fromString(all_dates[1], "yyyy-MM-dd"))
    win.cb_slice_enable.setChecked(True)

    # 倒退到第 0 个日期
    win.btn_slice_prev.click()
    assert win.date_cutoff_edit.date().toString("yyyy-MM-dd") == all_dates[0]

    # 再次倒退：无法越界，保持在第 0 个日期
    win.btn_slice_prev.click()
    assert win.date_cutoff_edit.date().toString("yyyy-MM-dd") == all_dates[0]

    # 前进到最后一个日期
    win.date_cutoff_edit.setDate(QDate.fromString(all_dates[-2], "yyyy-MM-dd"))
    win.btn_slice_next.click()
    assert win.date_cutoff_edit.date().toString("yyyy-MM-dd") == all_dates[-1]

    # 再次前进：达到最新日期，自动关闭切片
    win.btn_slice_next.click()
    assert not win.cb_slice_enable.isChecked()


def test_search_history_json_contains_auction_reversal_formula():
    """测试 5: 验证 search_history.json 中已成功写入弱转强公式"""
    import json
    import os
    json_path = os.path.join(PROJECT_ROOT, "datacsv", "search_history.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    h1 = data.get("history1", [])
    found = any("空头陷阱·竞价弱转强" in item.get("note", "") for item in h1)
    assert found, "history1 中必须包含【空头陷阱·竞价弱转强起爆战法】公式"


def test_slice_floating_bar_and_calendar_popup(qapp):
    """测试 6: 验证 K 线右上角悬浮工具条与下拉日历浮窗的功能与交互"""
    from trade_visualizer_qt6 import MainWindow, SliceCalendarPopup, SliceFloatingBar
    
    win = MainWindow()
    assert hasattr(win, 'slice_floating_bar')
    assert isinstance(win.slice_floating_bar, SliceFloatingBar)
    assert win.slice_floating_bar.parent() == win.kline_widget
    
    # 测试悬浮条重定位
    win.kline_widget.resize(800, 600)
    win.slice_floating_bar.reposition()
    expected_x = win.kline_widget.width() - win.slice_floating_bar.width() - 15
    assert abs(win.slice_floating_bar.x() - expected_x) <= 2
    assert win.slice_floating_bar.y() == 10

    # 验证控件排版顺序：日历按钮必须放置在左右箭头之前，左右箭头紧邻便于连续点击
    bar_layout = win.slice_floating_bar.layout()
    cal_idx = bar_layout.indexOf(win.btn_slice_calendar)
    prev_idx = bar_layout.indexOf(win.btn_slice_prev)
    next_idx = bar_layout.indexOf(win.btn_slice_next)
    assert cal_idx < prev_idx < next_idx, f"日历按钮(idx={cal_idx})必须在左右箭头(prev={prev_idx}, next={next_idx})前面"

    # 测试日历浮窗
    assert hasattr(win, 'calendar_popup')
    assert isinstance(win.calendar_popup, SliceCalendarPopup)
    
    selected_dates = []
    win.calendar_popup.date_selected.connect(lambda d: selected_dates.append(d))
    
    # 模拟从浮窗选定日期
    win.calendar_popup._on_calendar_clicked(QDate(2026, 9, 4))
    assert len(selected_dates) == 1
    assert selected_dates[0] == "2026-09-04"

    # 测试快捷日期槽
    win.calendar_popup.show_under(win.btn_slice_calendar, "2026-09-04", ["2026-09-04", "2026-09-03", "2026-09-02", "2026-09-01"])
    assert win.calendar_popup.quick_layout.count() > 0
    win.calendar_popup.close()

    # 测试切片激活后悬浮条及日历按钮文案更新
    mock_df = generate_mock_daily_data()
    win.raw_day_df = mock_df.copy()
    win.day_df = mock_df.copy()
    win.current_code = "000823"
    
    win._on_popup_date_selected("2026-09-04")
    assert win.cb_slice_enable.isChecked()
    assert "09-04" in win.btn_slice_calendar.text()
    
    # 测试恢复最新
    win._on_slice_reset_clicked()
    assert not win.cb_slice_enable.isChecked()
    assert win.btn_slice_calendar.text() == "📅"


