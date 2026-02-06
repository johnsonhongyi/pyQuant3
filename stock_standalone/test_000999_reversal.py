# -*- coding: utf-8 -*-
import pandas as pd
from datetime import datetime, time as dt_time
from intraday_pattern_detector import IntradayPatternDetector, PatternEvent

def test_000999():
    detector = IntradayPatternDetector(cooldown=0) # 无冷却便于连续测试
    
    code = "000999"
    name = "三九医药"
    prev_close = 50.0
    
    # 场景 1: 趋势上升 (高点升高)，早盘大涨后跌破均线，但价格仍高于前两天高点 -> 应抑制诱多跑路
    print("\n--- 场景 1: 趋势上升 + 突破前高 (不应触发诱多跑路) ---")
    day_row_1 = pd.Series({
        'open': 51.0,   # 高开 2%
        'high': 53.0,   # 曾经涨幅 6% (相对于开盘) -> 符合诱多门槛
        'low': 51.0,
        'close': 52.0,  # 当前回落，低于 VWAP
        'trade': 52.0,
        'amount': 52500000,
        'volume': 1000000, # vwap = 52.5, close=52.0 < vwap
        'lasth1d': 51.5,
        'lasth2d': 51.0,   # 趋势上升: lasth1d > lasth2d
    })
    
    events = detector.update(code, name, None, day_row_1, prev_close, current_time=dt_time(10, 0))
    print(f"检测到事件: {events}")
    
    # 场景 2: 趋势下降结构，早盘大涨后破位 -> 应触发诱多跑路
    print("\n--- 场景 2: 趋势下降 + 未过前高 (应触发诱多跑路) ---")
    detector._cache.clear() # 清理状态
    day_row_2 = pd.Series({
        'open': 50.0,
        'high': 52.0,   # 涨幅 4%
        'low': 49.5,
        'close': 49.8,  # 破位，低于开盘价和VWAP
        'trade': 49.8,
        'amount': 50500000,
        'volume': 1000000, # vwap = 50.5
        'lasth1d': 53.0,
        'lasth2d': 54.0,   # 未突破前高
    })
    events = detector.update(code, name, None, day_row_2, prev_close, current_time=dt_time(10, 0))
    print(f"检测到事件: {events}")

    # 场景 3: 诱空反转 (早盘下杀，尾盘拉升突破前高) -> 应触发诱空反转
    print("\n--- 场景 3: 诱空反转 (早盘下杀 + 尾盘突围) ---")
    detector._cache.clear()
    day_row_3 = pd.Series({
        'open': 49.0,   # 低开
        'high': 53.5,   # 突围
        'low': 48.0,    # 下杀 -2%
        'close': 53.5,  # 当前突破 53.0
        'trade': 53.5,
        'amount': 51000000,
        'volume': 1000000, # vwap = 51.0
        'lasth1d': 53.0,
        'lasth2d': 52.0,   # 前两天最高 53.0
    })
    # 时间必须在 10:30 之后
    events = detector.update(code, name, None, day_row_3, prev_close, current_time=dt_time(14, 0))
    print(f"检测到事件: {events}")

if __name__ == "__main__":
    test_000999()
