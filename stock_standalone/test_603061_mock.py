# -*- coding: utf-8 -*-
import pandas as pd
from datetime import datetime, time as dt_time
from intraday_pattern_detector import IntradayPatternDetector, PatternEvent

def test_603061_mock_refined():
    detector = IntradayPatternDetector(cooldown=0)
    
    code = "603061"
    name = "金海通" # 实际名称
    prev_close = 100.0 # 使用 100 方便计算百分比
    
    # 历史结构: 昨天低开高走
    # 昨天: Open 96, Close 100, Low 96, High 100
    # 前天: High 98
    history = {
        'lasth1d': 100.0,
        'lasth2d': 98.0,
        'lastl1d': 96.0,
        'lastp1d': 100.0,
        'ma51d': 97.0
    }
    
    print("\n--- 模拟 603061：宽幅震荡结构测试 ---")
    
    # 场景 1: 早盘低开冲高回落，但守住开盘价
    print("\n[状态 1] 第一次冲高回落，守住开盘价:")
    day_row_1 = pd.Series({
        **history,
        'open': 98.0,   # 低开 2%
        'high': 102.5,  # 相比开盘涨 4.6% -> 越过 3.8% 门槛
        'low': 98.0,    # 低点抬高 (98 > 96)
        'close': 98.5,  # 回落，假定已跌破均线 (vwap 约 101)
        'trade': 98.5,
        'amount': 1000000,
        'volume': 10000, # vwap = 100
    })
    # 在这个点，close(98.5) < vwap(100)，但 close >= open(98.0)
    # 应被 is_ascending_base 抑制
    events = detector.update(code, name, None, day_row_1, prev_close, current_time=dt_time(9, 45))
    print(f"信号结果: {events} (预期: 空，因为守住了开盘价且结构转强)")

    # 场景 2: 震荡后突破前高 (100.0)
    print("\n[状态 2] 宽幅震荡后突破昨高:")
    day_row_2 = pd.Series({
        **history,
        'open': 98.0,
        'high': 102.5,
        'low': 98.0,
        'close': 101.5, # 已经突破 100.0
        'trade': 101.5,
        'amount': 2000000,
        'volume': 20000, # vwap ≈ 100
    })
    events = detector.update(code, name, None, day_row_2, prev_close, current_time=dt_time(10, 30))
    print(f"信号结果: {events}")

    # 场景 3: 诱空反转检测 (如果曾经下杀过)
    print("\n[状态 3] 验证诱空反转 (早盘先杀跌破昨收，后又突破昨高):")
    # 模拟早盘跌破昨收(100)
    day_row_3 = pd.Series({
        **history,
        'open': 98.0,
        'high': 103.0,
        'low': 97.0,    # 下杀到 97 (比开盘 98 还低，诱空)
        'close': 101.0, # 突破 昨高 100.0
        'trade': 101.0,
        'amount': 3000000,
        'volume': 30000,
    })
    events = detector.update(code, name, None, day_row_3, prev_close, current_time=dt_time(13, 30))
    print(f"信号结果: {events}")

if __name__ == "__main__":
    test_603061_mock_refined()
