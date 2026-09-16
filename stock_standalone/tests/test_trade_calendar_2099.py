# -*- coding: utf-8 -*-
"""
test_trade_calendar_2099.py
----------------------------
自动化测试：验证 A 股交易日历（2005-2099 年）高精度推演与环境集成
"""

import os
import sys
import datetime
import pytest
import pandas as pd

app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

import a_trade_calendar
from tools.generate_trade_calendar_2099 import LunarSolarEngine, TradeHolidayEngine



class TestTradeCalendar2099:
    """测试 2099 交易日历准确性、连续性与业务规则"""

    def test_historical_integrity(self):
        """测试历史真实数据（2005-01-04 至 2027-02-19）完整继承且无篡改"""
        # 加载工程本地最新生成的日历
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        csv_path = os.path.join(app_root, "JSONData", "a_trade_calendar.csv")
        assert os.path.exists(csv_path), f"找不到日历文件: {csv_path}"

        df = pd.read_csv(csv_path)
        assert len(df) >= 22700, f"总天数异常，应大于 22700 天，实际为: {len(df)}"

        # 验证首条与旧版交界处
        assert df.iloc[0]['dt'] == '2005-01-04'
        assert df.iloc[-1]['dt'].startswith('2099')

        # 检查 2027-02-19（旧版最后一天）依然存在
        assert '2027-02-19' in df['dt'].values
        # 检查 2027-02-22（2027-02-19 后首个交易日，周一）存在
        assert '2027-02-22' in df['dt'].values

    def test_no_weekend_trading(self):
        """严守周末铁律：推演出的数万条交易日中，周六日数量必须严格为 0"""
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        csv_path = os.path.join(app_root, "JSONData", "a_trade_calendar.csv")
        df = pd.read_csv(csv_path)

        dates = pd.to_datetime(df['dt'])
        weekdays = dates.dt.weekday
        weekend_count = (weekdays >= 5).sum()
        assert weekend_count == 0, f"发现 {weekend_count} 个周末被错误判定为交易日！"

    def test_lunar_holidays_accuracy(self):
        """验证高精度天文农历算法计算农历新年、端午、中秋、清明节精度"""
        # 2024 年真实对照
        assert LunarSolarEngine.get_chunjie(2024) == datetime.date(2024, 2, 10)
        assert LunarSolarEngine.get_duanwu(2024) == datetime.date(2024, 6, 10)
        assert LunarSolarEngine.get_zhongqiu(2024) == datetime.date(2024, 9, 17)
        assert LunarSolarEngine.get_qingming(2024) == datetime.date(2024, 4, 4)

        # 2025 年真实对照
        assert LunarSolarEngine.get_chunjie(2025) == datetime.date(2025, 1, 29)
        assert LunarSolarEngine.get_duanwu(2025) == datetime.date(2025, 5, 31)
        assert LunarSolarEngine.get_zhongqiu(2025) == datetime.date(2025, 10, 6)
        assert LunarSolarEngine.get_qingming(2025) == datetime.date(2025, 4, 4)

        # 2026 年真实对照
        assert LunarSolarEngine.get_chunjie(2026) == datetime.date(2026, 2, 17)
        assert LunarSolarEngine.get_duanwu(2026) == datetime.date(2026, 6, 19)
        assert LunarSolarEngine.get_zhongqiu(2026) == datetime.date(2026, 9, 25)
        assert LunarSolarEngine.get_qingming(2026) == datetime.date(2026, 4, 5)

    def test_statutory_and_joint_holiday_rules(self):
        """验证法定休市日与中秋国庆合体连休 8 天机制"""
        # 测试 2028 年春节：农历正月初一 2028-01-26，除夕 2028-01-25
        chunjie_2028 = LunarSolarEngine.get_chunjie(2028)
        assert chunjie_2028 == datetime.date(2028, 1, 26)
        assert not a_trade_calendar.is_trade_date('2028-01-25')  # 除夕休市
        assert not a_trade_calendar.is_trade_date('2028-01-26')  # 初一休市
        assert not a_trade_calendar.is_trade_date('2028-01-27')  # 初二休市

        # 测试 2028 年国庆与中秋：农历八月十五是 2028-10-03，与国庆重叠！
        zq_2028 = LunarSolarEngine.get_zhongqiu(2028)
        assert zq_2028 == datetime.date(2028, 10, 3)
        # 中秋国庆合体：10月1日 至 10月8日 均应休市
        for day in range(1, 9):
            dt_str = f"2028-10-{day:02d}"
            assert not a_trade_calendar.is_trade_date(dt_str), f"2028合体假期 {dt_str} 应当休市！"

        # 测试国庆 10月1日 至 10月7日 在未来各年均休市
        for test_year in [2030, 2050, 2099]:
            assert not a_trade_calendar.is_trade_date(f"{test_year}-10-01")
            assert not a_trade_calendar.is_trade_date(f"{test_year}-05-01")

    def test_a_trade_calendar_apis(self):
        """测试 a_trade_calendar 所有导出 API 在未来年份正常工作"""
        # 1. is_trade_date
        assert a_trade_calendar.is_trade_date('2099-01-05') is True   # 周一工作日
        assert a_trade_calendar.is_trade_date('2099-01-04') is False  # 周日休市

        # 2. get_pre_trade_date
        pre_dt = a_trade_calendar.get_pre_trade_date('2099-01-05')
        assert pre_dt is not None
        assert pre_dt < '2099-01-05'

        # 3. get_next_trade_date
        next_dt = a_trade_calendar.get_next_trade_date('2028-05-06')
        assert next_dt is not None
        assert next_dt > '2028-05-06'

        # 4. get_trade_days_interval & get_trade_count
        count = a_trade_calendar.get_trade_count('2028-01-01', '2028-12-31')
        assert 240 <= count <= 255, f"全年交易日数量异常: {count}"
