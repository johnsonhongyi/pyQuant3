# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
from datetime import datetime, time as dt_time

sys.path.append(os.getcwd())

from JSONData import tdx_data_Day as tdd
from intraday_pattern_detector import IntradayPatternDetector, PatternEvent

def test_603061_real_data():
    detector = IntradayPatternDetector(cooldown=0)
    
    code = "603061"
    
    try:
        df = tdd.get_tdx_append_now_df_api(code, dl=10)
        if df is None or df.empty:
            print("无法获取数据")
            return
            
        print(df.head(3))
        
        # 索引是最新的在前
        row = df.iloc[0] # 今日
        row_yest = df.iloc[1] # 昨日
        row_before = df.iloc[2] # 前日
        
        name = row.get('name', 'Unknown')
        
        # 对齐数据
        day_row = row.copy()
        day_row['lasth1d'] = row_yest['high']
        day_row['lasth2d'] = row_before['high']
        day_row['lastl1d'] = row_yest['low']
        day_row['lastp1d'] = row_yest['close']
        
        prev_close = row_yest['close']
        
        print(f"\n代码: {code} 名称: {name}")
        print(f"日期: 今日({df.index[0]}), 昨日({df.index[1]}), 前日({df.index[2]})")
        print(f"今日: 开盘 {day_row['open']}, 最高 {day_row['high']}, 最低 {day_row['low']}, 当前 {day_row['close']}")
        print(f"昨日: 最高 {day_row['lasth1d']}, 最低 {day_row['lastl1d']}, 收盘 {day_row['lastp1d']}")
        
        # 检测
        events = detector.update(code, name, None, day_row, prev_close)
        
        print(f"\n检测结果: {events}")
        for ev in events:
            print(f"信号: {ev.pattern} - {ev.detail}")

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_603061_real_data()
