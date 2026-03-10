import os
import pandas as pd
import numpy as np
from cache_utils import DataFrameCacheSlot

def test_zstd_compression():
    # 1. Prepare test data (5MB of numeric data)
    df = pd.DataFrame({
        'code': [str(i).zfill(6) for i in range(10000)],
        'price': np.random.rand(10000),
        'volume': np.random.randint(0, 100000, 10000)
    })
    
    test_file = "test_zstd_cache.pkl"
    slot = DataFrameCacheSlot(cache_file=test_file)
    
    print(f"Original DF size: {len(df)} rows")
    
    # 2. Save with zstd (via modified cache_utils)
    success = slot.save_df(df, persist=True)
    if not success:
        print("❌ Failed to save DF")
        return
        
    compressed_size = os.path.getsize(test_file)
    print(f"✅ Saved successfully. File size: {compressed_size / 1024:.2f} KB")
    
    # 3. Load and Verify
    # reset slot mem
    slot._mem_df = None
    loaded_df = slot.load_df()
    
    if loaded_df.empty:
        print("❌ Failed to load DF (Empty)")
        return
        
    if pd.testing.assert_frame_equal(df, loaded_df) is None:
        print("✅ Data integrity verified (assert_frame_equal passed)")
    else:
        print("❌ Data integrity check failed")

    # Cleanup
    if os.path.exists(test_file): os.remove(test_file)
    if os.path.exists(test_file + ".bak"): os.remove(test_file + ".bak")

if __name__ == "__main__":
    try:
        test_zstd_compression()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
