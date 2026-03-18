import sys
import os
import pandas as pd
import numpy as np
import time

# Add current directory to path
sys.path.append(os.getcwd())

from tdx_hdf5_api import write_hdf_db, load_hdf_db, cct

def test_write_hdf_db_basic():
    fname = "test_basic.h5"
    fname_path = cct.get_ramdisk_path(fname)
    table = "test_table"
    df = pd.DataFrame({'a': [1, 2], 'b': [3, 4], 'code': ['000001', '000002']})
    
    print(f"Testing basic write to {fname_path}...")
    res = write_hdf_db(fname, df, table=table, rewrite=True)
    assert res == True
    assert os.path.exists(fname_path)
    
    print("Testing read back...")
    df_read = load_hdf_db(fname, table=table)

    print(f"Read shape: {df_read.shape}")
    assert not df_read.empty
    
    print("Basic test passed!")

def test_write_hdf_db_multiindex():
    fname = "test_multi.h5"
    table = "test_table"
    
    # Create MultiIndex DF
    arrays = [
        ['000001', '000001', '000002', '000002'],
        ['2023-01-01', '2023-01-02', '2023-01-01', '2023-01-02']
    ]
    index = pd.MultiIndex.from_arrays(arrays, names=('code', 'date'))
    df = pd.DataFrame({'val': [1, 2, 3, 4]}, index=index)
    
    print("Testing MultiIndex write (rewrite=True)...")
    res = write_hdf_db(fname, df, table=table, MultiIndex=True, rewrite=True)
    assert res == True
    
    print("Testing MultiIndex append...")
    new_arrays = [['000001'], ['2023-01-03']]
    new_index = pd.MultiIndex.from_arrays(new_arrays, names=('code', 'date'))
    df_new = pd.DataFrame({'val': [5]}, index=new_index)
    
    res = write_hdf_db(fname, df_new, table=table, MultiIndex=True, append=True)
    assert res == True
    
    df_read = load_hdf_db(fname, table=table, MultiIndex=True)
    print(f"Total rows after append: {len(df_read)}")
    assert len(df_read) == 5
    
    print("MultiIndex test passed!")

if __name__ == "__main__":
    try:
        # Clean up old test files
        for f in ["test_basic.h5", "test_multi.h5"]:
            f_path = cct.get_ramdisk_path(f)
            if os.path.exists(f_path): os.remove(f_path)
            if os.path.exists(f_path + ".lock"): os.remove(f_path + ".lock")

            
        test_write_hdf_db_basic()
        test_write_hdf_db_multiindex()
        print("\nAll tests passed successfully!")
    except Exception as e:
        print(f"\nTest FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Final cleanup
        for f in ["test_basic.h5", "test_multi.h5"]:
            f_path = cct.get_ramdisk_path(f)
            if os.path.exists(f_path): 
                try: os.remove(f_path)
                except: pass
            if os.path.exists(f_path + ".lock"):
                try: os.remove(f_path + ".lock")
                except: pass

