import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

def analyze_stock_trend(code="301362", h5_path=r"g:\sina_MultiIndex_data.h5"):
    print(f"Loading data for {code} from {h5_path}...")
    try:
        # 尝试读取该股票的所有 tick
        df = pd.read_hdf(h5_path, key='all_30', where=f"code='{code}'")
        if df.empty:
            print(f"No data found for {code}")
            return
        
        df = df.reset_index()
        # 确保时间排序
        df['ticktime'] = pd.to_datetime(df['ticktime'])
        df = df.sort_values('ticktime')
        
        # 过滤 09:15 到 10:15
        df_slice = df[(df['ticktime'].dt.time >= pd.to_datetime("09:15:00").time()) & 
                    (df['ticktime'].dt.time <= pd.to_datetime("10:15:00").time())]
        
        with open("debug_301362_results.txt", "w", encoding="utf-8") as f:
            f.write(f"Data points for {code} (09:15-10:15): {len(df_slice)}\n")
            if not df_slice.empty:
                f.write(df_slice[['ticktime', 'close', 'volume', 'llastp']].to_string())
                
                # 计算分时涨幅
                df_slice['pct'] = (df_slice['close'] - df_slice['llastp']) / df_slice['llastp'] * 100
                
                # 简单模拟分值逻辑：涨幅 > 2% 且带量
                df_slice['is_breakout'] = (df_slice['pct'] > 2.0) & (df_slice['volume'] > 0)
                breakouts = df_slice[df_slice['is_breakout']]
                if not breakouts.empty:
                    f.write("\n\nCaptured Breakout Moments:\n")
                    f.write(breakouts[['ticktime', 'close', 'pct', 'volume']].to_string())
                else:
                    f.write("\n\nNo breakout captured by simplified logic (pct > 2%)")
        print("Results saved to debug_301362_results.txt")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_stock_trend()
