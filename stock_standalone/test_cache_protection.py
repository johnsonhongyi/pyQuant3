import pandas as pd
import os
import shutil
from cache_utils import DataFrameCacheSlot

def test_cache_protection():
    test_file = "test_cache_prot.pkl"
    if os.path.exists(test_file): os.remove(test_file)
    
    # 模拟一个 Logger
    class MockLogger:
        def info(self, msg): print(f"INFO: {msg}")
        def warning(self, msg): print(f"WARN: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
    
    slot = DataFrameCacheSlot(test_file, logger=MockLogger())
    
    # 1. 初始保存大数据量 (1000 行)
    df_large = pd.DataFrame({'a': range(1000)})
    print("\n--- Phase 1: Saving large DF (1000 rows)")
    res1 = slot.save_df(df_large)
    print(f"Result: {res1}, File size: {os.path.getsize(test_file)}")
    
    # 2. 尝试保存小数据量 (100 行, < 0.5 * 1000)
    df_small = pd.DataFrame({'a': range(100)})
    print("\n--- Phase 2: Attempting to save small DF (100 rows, factor=0.5)")
    res2 = slot.save_df(df_small, min_rows_factor=0.5)
    print(f"Result: {res2} (Expected: False)")
    
    # 验证文件是否仍为大数据量
    df_check = pd.read_pickle(test_file, compression='zstd')
    print(f"Current rows in file: {len(df_check)} (Expected: 1000)")
    
    # 3. 带 force=True 保存
    print("\n--- Phase 3: Saving small DF with force=True")
    res3 = slot.save_df(df_small, force=True)
    print(f"Result: {res3} (Expected: True)")
    df_check_force = pd.read_pickle(test_file, compression='zstd')
    print(f"Current rows in file: {len(df_check_force)} (Expected: 100)")
    
    # 清理
    if os.path.exists(test_file): os.remove(test_file)
    print("\n✅ Cache protection test COMPLETED.")

if __name__ == "__main__":
    test_cache_protection()
