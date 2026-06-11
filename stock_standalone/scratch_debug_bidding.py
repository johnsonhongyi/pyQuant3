import pandas as pd
import numpy as np

def run():
    h5_path = r"g:\sina_MultiIndex_data.h5"
    codes = ["688549", "688146"]
    for code in codes:
        print(f"\n--- Code: {code} ---")
        df = pd.read_hdf(h5_path, key='all_30', where=f"code='{code}'")
        df = df.reset_index()
        df['ticktime'] = pd.to_datetime(df['ticktime'])
        df_day = df[df['ticktime'].dt.date == pd.to_datetime("2026-06-11").date()].sort_values('ticktime')
        print(f"Total rows on 2026-06-11: {len(df_day)}")
        print(df_day.head(10).to_string())

if __name__ == "__main__":
    run()
