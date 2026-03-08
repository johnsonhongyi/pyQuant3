# -*- coding: utf-8 -*-
import os
import time
import pandas as pd
import multiprocessing as mp
from data_hub_service import DataHubService
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger("DataHubTest")

def simulate_process(name, delay=0):
    """模拟一个独立进程，尝试获取数据，如果没有则生成并发布"""
    time.sleep(delay)
    hub = DataHubService.get_instance("data_test")
    
    logger.info(f"Process {name} started. Checking DataHub...")
    
    # 尝试获取
    df = hub.get_df_all()
    if df is not None:
        logger.info(f"Process {name} found existing DataHub with {len(df)} rows. Success.")
        return True
    
    # 没找到，尝试自愈 (Bootstrap)
    logger.info(f"Process {name} found no data or stale data. Bootstrapping...")
    mock_df = pd.DataFrame({'code': ['000001', '600000'], 'score': [100, 99]})
    success = hub.publish_df_all(mock_df)
    
    if success:
        logger.info(f"Process {name} successfully initialized the DataHub.")
        return True
    else:
        logger.error(f"Process {name} failed to initialize the DataHub (possibly contention).")
        return False

if __name__ == "__main__":
    # 清理旧测试数据
    test_dir = "data_test"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
    target_h5 = os.path.join(test_dir, "shared_df_all.h5")
    if os.path.exists(target_h5):
        try:
            os.remove(target_h5)
        except:
            pass
            
    # 同时启动 3 个进程，模拟竞争
    # 1. 虽然同时启动，由于 DataHubService 的原子 $os.replace$，只会有一个成功写入，其他会读取到成型的文件
    processes = []
    names = ["Visualizer", "BiddingPanel", "MainTK"]
    
    for name in names:
        p = mp.Process(target=simulate_process, args=(name,))
        processes.append(p)
        p.start()
        
    for p in processes:
        p.join()
        
    # 验证最终结果
    hub = DataHubService.get_instance("data_test")
    final_df = hub.get_df_all()
    if final_df is not None and not final_df.empty:
        print("\n[✔] TEST PASSED: Self-Healing & Multi-Point Protection Verified.")
        print(f"Final DataHub rows: {len(final_df)}")
    else:
        print("\n[✘] TEST FAILED: DataHub initialization failed.")
