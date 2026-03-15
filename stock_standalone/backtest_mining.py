import pandas as pd
import numpy as np
import logging
import sys
import os

# 确保能导入当前目录下的模块
sys.path.append(os.getcwd())

from query_engine_util import query_engine
from multi_period_manager import multi_period_mgr

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BacktestMiner")

def load_h5_data(file_path):
    """
    通用 H5 加载逻辑，使用探测到的正确 Key
    """
    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        return None
    
    # 根据 inspect_h5.py 的结果，0309 使用 /df_all, 0314 使用 /df
    keys_to_try = ['df_all', 'df', 'top_all', 'all_30', 'all']
    for key in keys_to_try:
        try:
            df = pd.read_hdf(file_path, key=key)
            logger.info(f"成功加载 {file_path}, Key: {key}, Shape: {df.shape}")
            # 标准化列名：确保有 close, high, low, volume, name 等基础列
            rename_map = {
                'lastp0d': 'close', 'lasth0d': 'high', 'lastl0d': 'low',
                'lastv0d': 'volume', 'lasto0d': 'open'
            }
            df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns and v not in df.columns}, inplace=True)
            return df
        except Exception:
            continue
    
    logger.error(f"无法读取 {file_path}")
    return None

def run_backtest_mining():
    """
    回测挖掘核心流程：
    1. 加载 0309 (启动点) 和 0314 (结果点) 数据
    2. 在 0309 上运行“潜伏”策略获取清单
    3. 追踪清单在 0314 的表现
    4. 反向挖掘：分析 0314 出位股在 0309 的特征
    """
    path_0309 = r"D:\Ramdisk\shared_df_all-2026-0309.h5"
    path_0314 = r"G:\shared_df_all-20260314.h5"

    logger.info("Step 1: 正在加载历史 H5 数据...")
    df_0309 = load_h5_data(path_0309)
    df_0314 = load_h5_data(path_0314)

    if df_0309 is None or df_0314 is None:
        logger.error("数据加载失败，无法继续回测。")
        return

    # 前期处理：优化类型并设置为索引
    df_0309 = multi_period_mgr.optimize_dtypes(df_0309)
    df_0314 = multi_period_mgr.optimize_dtypes(df_0314)
    
    if 'code' in df_0309.columns: df_0309.set_index('code', inplace=True)
    if 'code' in df_0314.columns: df_0314.set_index('code', inplace=True)
    df_0309.index = df_0309.index.astype(str)
    df_0314.index = df_0314.index.astype(str)

    logger.info("\nStep 2: 在 0309 数据上运行“蓄势启动”策略...")
    # 注意：H5 数据通常只有单一周期，为了复用 manager，我们将其伪装成 D 周期
    combined_0309 = multi_period_mgr.merge_periods({'d': df_0309})
    
    # 运行潜伏策略
    candidates_0309 = multi_period_mgr.get_ready_to_launch_candidates(combined_0309, top_n=100)
    logger.info(f"0309 策略选股数: {len(candidates_0309)}")

    logger.info("\nStep 3: 追踪这些标的在 0314 的表现...")
    # 对齐索引
    common_index = candidates_0309.index.intersection(df_0314.index)
    track_results = []
    
    for code in common_index:
        start_price = df_0309.at[code, 'close']
        end_price = df_0314.at[code, 'close']
        change = (end_price - start_price) / start_price * 100
        name = df_0309.at[code, 'name'] if 'name' in df_0309.columns else "Unknown"
        track_results.append({
            'code': code,
            'name': name,
            'start_price': start_price,
            'end_price': end_price,
            'period_change': change
        })
    
    track_df = pd.DataFrame(track_results).sort_values(by='period_change', ascending=False)
    
    # 打印表现最好的前 10
    logger.info("\n--- 0309 策略选股在 0314 的表现 (Top 10) ---")
    print(track_df.head(10))
    
    # 计算统计数据
    win_rate = (track_df['period_change'] > 0).mean() * 100
    avg_gain = track_df['period_change'].mean()
    logger.info(f"胜率: {win_rate:.2f}%, 平均涨跌幅: {avg_gain:.2f}%")

    logger.info("\nStep 4: 反向挖掘 —— 0314 的强势股在 0309 是什么样子的？")
    # 定义 0314 的“出位”股：涨幅 > 10%
    strong_0314 = df_0314[df_0314['percent'] > 5]
    common_strong = strong_0314.index.intersection(df_0309.index)
    
    logger.info(f"0314 强势股在 0309 中存在的数量: {len(common_strong)}")
    
    if len(common_strong) > 0:
        strong_features_0309 = df_0309.loc[common_strong]
        # 分析这些股在 0309 时的振幅均值、MA60 距离等
        avg_vol_0309 = strong_features_0309['volume'].mean() if 'volume' in df_0309.columns else 0
        logger.info(f"这些‘出位’股在启动前(0309)的平均量能: {avg_vol_0309:.2f}")
        
        # 导出差异分析
        track_df.to_csv("backtest_0309_to_0314.csv", index=False)
        logger.info("回测明细已保存至 backtest_0309_to_0314.csv")

if __name__ == "__main__":
    run_backtest_mining()
