import pandas as pd
import datetime

try:
    df = pd.read_pickle(r'g:\minute_kline_cache.pkl')
    if df.empty:
        print("DataFrame is empty")
    else:
        print(f"Total rows: {len(df)}")
        print(f"Columns: {df.columns.tolist()}")
        
        # Convert time to readable format
        df['readable_time'] = pd.to_datetime(df['time'], unit='s', utc=True).dt.tz_convert('Asia/Shanghai')
        
        print("\nLast 10 rows:")
        print(df[['code', 'time', 'readable_time']].tail(10))
        
        print("\nMax time for today (2026-02-25):")
        today = datetime.date(2026, 2, 25)
        today_df = df[df['readable_time'].dt.date == today]
        if today_df.empty:
            print("No data for today")
        else:
            print(f"Today data rows: {len(today_df)}")
            print(f"Max time today: {today_df['readable_time'].max()}")
            
        print("\nMax time for other days:")
        other_days_df = df[df['readable_time'].dt.date != today]
        if not other_days_df.empty:
            print(other_days_df.groupby(other_days_df['readable_time'].dt.date)['readable_time'].max())

except Exception as e:
    print(f"Error: {e}")
