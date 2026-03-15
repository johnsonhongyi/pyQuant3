import pandas as pd
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FeatureMiner")

def mine_features():
    path_0309 = r"D:\Ramdisk\shared_df_all-2026-0309.h5"
    df_0309 = pd.read_hdf(path_0309, key='df_all')
    if 'code' in df_0309.columns: df_0309.set_index('code', inplace=True)
    df_0309.index = df_0309.index.astype(str)

    # 新的 Top 赢家和输家 (根据最新回测结果)
    winners = ['300185', '603248', '601218', '001369', '601330']
    losers = ['600318', '300609', '002771', '300062', '000099']

    cols_to_check = ['name', 'percent', 'close', 'vol_ratio', 'upper1']
    for i in range(1, 4):
        p_col = f'lastp{i}d'
        if p_col in df_0309.columns: cols_to_check.append(p_col)
    
    found_cols = [c for c in cols_to_check if c in df_0309.columns]
    
    # 获取数据
    df_win = df_0309.loc[winners, found_cols].copy()
    df_lose = df_0309.loc[losers, found_cols].copy()
    
    # 计算 3 日涨幅
    if 'lastp3d' in df_0309.columns:
        df_win['gain_3d'] = (df_win['close'] - df_win['lastp3d']) / df_win['lastp3d'] * 100
        df_lose['gain_3d'] = (df_lose['close'] - df_lose['lastp3d']) / df_lose['lastp3d'] * 100

    logger.info("\n--- [WINNERS (0309 -> 0314 Grow)] Features on 0309 ---")
    print(df_win[['name', 'percent', 'gain_3d', 'vol_ratio']])

    logger.info("\n--- [LOSERS (Peaks on 0309)] Features on 0309 ---")
    print(df_lose[['name', 'percent', 'gain_3d', 'vol_ratio']])

if __name__ == "__main__":
    mine_features()
