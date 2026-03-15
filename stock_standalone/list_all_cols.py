import pandas as pd
import os

def list_all_cols():
    path_0314 = r"G:\shared_df_all-20260314.h5"
    df = pd.read_hdf(path_0314, key='df')
    all_cols = sorted(df.columns.tolist())
    
    print("Columns starting with 'last':")
    print([c for c in all_cols if c.lower().startswith('last')])
    
    print("\nColumns containing 'p0' or 'price':")
    print([c for c in all_cols if 'p0' in c.lower() or 'price' in c.lower()])
    
    print("\nColumns containing 'td':")
    print([c for c in all_cols if 'td' in c.lower()])
    
    # 也检查一下 001369 的一行完整数据
    if 'code' in df.columns:
        df.set_index('code', inplace=True)
    if '001369' in df.index:
        print("\n001369 Sample Data (Historical Price related):")
        row = df.loc['001369']
        # 寻找包含 p, high, low, close 的列
        rel_cols = [c for c in df.columns if any(x in c.lower() for x in ['p', 'close', 'high', 'low'])]
        print(row[rel_cols[:20]])

if __name__ == "__main__":
    list_all_cols()
