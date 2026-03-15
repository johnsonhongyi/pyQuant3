import pandas as pd
import os

def calc_001369_td_exact():
    path_0314 = r"G:\shared_df_all-20260314.h5"
    df = pd.read_hdf(path_0314, key='df')
    if 'code' in df.columns:
        df.set_index('code', inplace=True)
    
    code = '001369'
    if code not in df.index:
        print("Not found")
        return
    
    row = df.loc[code]
    print(f"Stock: {row['name']} ({code})")
    
    # 构造价格序列 (正向时间轴)
    # p9 (03-02), p8 (03-03), p7 (03-04), p6 (03-05), p5 (03-06), p4 (03-09), p3 (03-10), p2 (03-11), p1 (03-12), p0 (03-13)
    prices = [row[f'lastp{i}d'] for i in range(9, -1, -1)]
    dates = ["03-02", "03-03", "03-04", "03-05", "03-06", "03-09", "03-10", "03-11", "03-12", "03-13"]
    
    print("\nPrice sequence leading to 03-13:")
    for d, p in zip(dates, prices):
        print(f"{d}: {p:.2f}")

    # TD Setup (Sell): Close[i] > Close[i-4]
    # 我们只有 10 个点，索引 0..9
    # i 从 4 开始算到 9
    print("\nTD Sell Setup Calculation:")
    td_counts = [0] * len(prices)
    for i in range(4, len(prices)):
        # 索引 i vs i-4
        if prices[i] > prices[i-4]:
            td_counts[i] = td_counts[i-1] + 1 if i > 0 else 1
        else:
            td_counts[i] = 0
        print(f"Date: {dates[i]}, Price: {prices[i]:.2f} vs {dates[i-4]}: {prices[i-4]:.2f}, TD Count: {td_counts[i]}")

if __name__ == "__main__":
    calc_001369_td_exact()
