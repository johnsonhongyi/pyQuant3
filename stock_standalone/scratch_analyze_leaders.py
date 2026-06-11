import pandas as pd
import numpy as np
import os

def check_keys(h5_path=r"g:\sina_MultiIndex_data.h5"):
    print(f"Checking H5 store at {h5_path}...")
    if not os.path.exists(h5_path):
        print("H5 file does not exist.")
        return
    with pd.HDFStore(h5_path, mode='r') as store:
        keys = store.keys()
        print("Keys:", keys)
        for key in keys:
            try:
                st = store.select(key, stop=5)
                print(f"Key {key} columns: {st.columns}")
                print(f"Key {key} index: {st.index.names}")
                print(st.head(2))
            except Exception as e:
                print(f"Error reading {key}: {e}")

def analyze_leaders(h5_path=r"g:\sina_MultiIndex_data.h5"):
    codes = ["688549", "688146"]
    for code in codes:
        print(f"\n================ Analyzing {code} ================")
        try:
            # Let's read the data
            df = pd.read_hdf(h5_path, key='all_30', where=f"code='{code}'")
            if df.empty:
                print(f"No data for {code} in all_30")
                continue
            df = df.reset_index()
            df['ticktime'] = pd.to_datetime(df['ticktime'])
            df = df.sort_values('ticktime')
            
            # Print unique days
            days = df['ticktime'].dt.date.unique()
            print(f"Available dates for {code}: {days}")
            
            for day in days:
                df_day = df[df['ticktime'].dt.date == day].copy()
                print(f"\n--- Date: {day} (Total ticks: {len(df_day)}) ---")
                
                # Check morning time
                df_morning = df_day[(df_day['ticktime'].dt.time >= pd.to_datetime("09:15:00").time()) & 
                                    (df_day['ticktime'].dt.time <= pd.to_datetime("09:45:00").time())]
                if df_morning.empty:
                    print("No morning ticks found.")
                    continue
                
                # Show first 15 ticks in morning
                print("First 15 morning ticks:")
                print(df_morning[['ticktime', 'close', 'high', 'low', 'volume', 'llastp']].head(15).to_string())
                
                # Find the breakout point: when does it start to go up?
                # Let's calculate the pct from llastp
                df_morning['pct'] = (df_morning['close'] - df_morning['llastp']) / df_morning['llastp'] * 100
                df_morning['volume_diff'] = df_morning['volume'].diff().fillna(0)
                
                # Find where it crosses 1%, 2%, 3%, 5%
                for threshold in [1.0, 2.0, 3.0, 5.0]:
                    crossing = df_morning[df_morning['pct'] >= threshold]
                    if not crossing.empty:
                        first_cross = crossing.iloc[0]
                        print(f"First crossed {threshold}% at {first_cross['ticktime']} (close: {first_cross['close']}, volume: {first_cross['volume']}, pct: {first_cross['pct']:.2f}%)")
                    else:
                        print(f"Never crossed {threshold}% in early morning")
                        
        except Exception as e:
            print(f"Error analyzing {code}: {e}")

if __name__ == "__main__":
    check_keys()
    analyze_leaders()
