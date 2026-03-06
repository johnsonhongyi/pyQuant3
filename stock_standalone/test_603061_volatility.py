# -*- coding: utf-8 -*-
import pandas as pd
from datetime import datetime, time as dt_time
from intraday_pattern_detector import IntradayPatternDetector, PatternEvent

def test_603061():
    detector = IntradayPatternDetector(cooldown=0)
    
    code = "603061"
    name = "金洲管道"
    prev_close = 10.0
    
    # 模拟历史特征
    # 昨天：低开走高，低点 9.7，高点 10.2，收盘 10.0
    # 前天：高点 10.1
    # 符合：lasth1d > lasth2d (高点升高结构)
    history_features = {
        'lasth1d': 10.2,
        'lasth2d': 10.1,
        'lastl1d': 9.7,
        'ma51d': 9.9
    }

    print("\n--- 场景：603061 模拟 (宽幅震荡但结构转强) ---")
    
    # 阶段 1: 9:35 第一次冲高回落
    # Open: 9.8, High: 10.3 (+5% from open), Price: 9.9 (跌破均线)
    print("\n[9:35] 第一次冲高回落测试...")
    day_row_1 = pd.Series({
        **history_features,
        'open': 9.8,
        'high': 10.3, # 涨幅 > 3.8%
        'low': 9.8,  # 早盘低点高于昨天低点 9.7
        'close': 9.9, # 跌破 vwap (假设 vwap 在 10.1)
        'trade': 9.9,
        'amount': 1010000,
        'volume': 100000, # vwap = 10.1
    })
    events = detector.update(code, name, None, day_row_1, prev_close, current_time=dt_time(9, 35))
    print(f"9:35 信号: {events}")

    # 阶段 2: 10:30 第二次冲高后震荡
    # Price: 10.2 (回到昨高位置)
    print("\n[10:30] 回升至昨高位置...")
    day_row_2 = pd.Series({
        **history_features,
        'open': 9.8,
        'high': 10.4,
        'low': 9.8,
        'close': 10.2, # 达到前两天最高点 max(10.2, 10.1)
        'trade': 10.2,
        'amount': 2040000,
        'volume': 200000, # vwap = 10.2
    })
    events = detector.update(code, name, None, day_row_2, prev_close, current_time=dt_time(10, 30))
    print(f"10:30 信号: {events}")

    # 阶段 3: 14:30 尾盘拉升收最高
    # Price: 10.5 (突破 max_h2)
    print("\n[14:30] 尾盘突围测试...")
    day_row_3 = pd.Series({
        **history_features,
        'open': 9.8,
        'high': 10.5,
        'low': 9.8,
        'close': 10.5,
        'trade': 10.5,
        'amount': 5150000,
        'volume': 500000, # vwap = 10.3
    })
    events = detector.update(code, name, None, day_row_3, prev_close, current_time=dt_time(14, 30))
    print(f"14:30 信号: {events}")

if __name__ == "__main__":
    test_603061()
