# -*- coding: utf-8 -*-
import pandas as pd
from datetime import datetime, time as dt_time
from intraday_pattern_detector import IntradayPatternDetector

def verify_strong_auction():
    detector = IntradayPatternDetector()
    detector.enabled_patterns.append('strong_auction_open')
    
    code = '600001'
    name = 'TestStock'
    prev_close = 10.0
    
    # Mock data: Open=Low=10.3 (Gap +3%), TrendS=75 (Strong)
    day_row = pd.Series({
        'open': 10.3,
        'low': 10.3,
        'high': 10.5,
        'close': 10.4,
        'TrendS': 75,
        'win': 2,
        'name': 'TestStock'
    })
    
    print(f"--- 验证 strong_auction_open 形态 ---")
    # Simulate 9:26 AM
    events = detector._check_open_patterns(code, name, day_row, prev_close, now_time=dt_time(9, 26))
    
    found = False
    for ev in events:
        print(f"触发信号: {ev.pattern} | 分数: {ev.score} | 详情: {ev.detail}")
        if ev.pattern == 'strong_auction_open':
            found = True
            
    if found:
        print("✅ Success: strong_auction_open 正常触发。")
    else:
        print("❌ Failure: strong_auction_open 未触发。")

    # Test Failure case: High lower shadow (Open=10.3, Low=10.1)
    print(f"\n--- 验证弱结构拒选 (下影线过长) ---")
    day_row_weak = day_row.copy()
    day_row_weak['low'] = 10.1
    events_weak = detector._check_open_patterns(code, name, day_row_weak, prev_close, now_time=dt_time(9, 26))
    if any(ev.pattern == 'strong_auction_open' for ev in events_weak):
        print("❌ Failure: 带有长下影线的标的不应触发强力竞价。")
    else:
        print("✅ Success: 弱结构已过滤。")

if __name__ == "__main__":
    verify_strong_auction()
