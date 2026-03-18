import sys
import os
import pandas as pd
import numpy as np
import time

# Add current directory to path
sys.path.append(os.getcwd())

from tdx_hdf5_api import write_hdf_db, load_hdf_db, cct

def test_truncation_logic():
    fname = "test_trunc.h5"
    fname_path = cct.get_ramdisk_path(fname)
    table = "trunc_table"
    
    # 1. Create a large MultiIndex DF to exceed a small limit
    # Each 'code' has 1000 rows
    codes = ['000001', '000002']
    dates = pd.date_range(start='2020-01-01', periods=1000).strftime('%Y-%m-%d').tolist()
    
    index = pd.MultiIndex.from_product([codes, dates], names=['code', 'date'])
    df = pd.DataFrame({'val': np.random.randn(len(index))}, index=index)
    
    # Initial write without limit
    print(f"Initial write of {len(df)} rows to {fname_path}...")
    write_hdf_db(fname, df, table=table, MultiIndex=True, rewrite=True)
    initial_size = os.path.getsize(fname_path)
    print(f"Initial file size: {initial_size / 1024:.2f} KB")
    
    # 2. Trigger truncation
    # Set sizelimit very small to trigger it
    # sizelimit is in MB. 
    sizelimit = 0.01 # 10 KB, enough to trigger for our generated file
    print(f"Triggering truncation with sizelimit={sizelimit} MB...")
    
    # Append a tiny bit of data to trigger the write_hdf_db branch containing truncate
    new_index = pd.MultiIndex.from_tuples([('000001', '2023-01-01')], names=['code', 'date'])
    df_new = pd.DataFrame({'val': [1.0]}, index=new_index)
    
    # Note: write_hdf_db only truncates when:
    # sizelimit is not None AND MultiIndex is True AND fsize_mb > sizelimit * 1.1
    res = write_hdf_db(fname, df_new, table=table, MultiIndex=True, sizelimit=sizelimit, rewrite=False)
    assert res == True
    
    # 3. Verify results
    final_size = os.path.getsize(fname_path)
    print(f"Final file size: {final_size / 1024:.2f} KB")
    
    df_read = load_hdf_db(fname, table=table, MultiIndex=True)
    print(f"Total rows after truncation: {len(df_read)}")
    
    # Check rows per code
    for code in codes:
        code_len = len(df_read.loc[df_read.index.get_level_values('code') == code])
        print(f"Code {code} row count: {code_len}")
        # The logic for small files is: full_df.groupby(level='code').apply(lambda x: x.tail(max(10, int(len(x) * 0.8))))
        # 1000 * 0.8 = 800
        assert code_len <= 801 # +1 for the newly appended row if it was distinct, but 2023-01-01 might overwrite if overlapping.
    
    print("Truncation logic test passed!")

if __name__ == "__main__":
    test_fname = "test_trunc.h5"
    test_path = cct.get_ramdisk_path(test_fname)
    try:
        if os.path.exists(test_path): os.remove(test_path)
        if os.path.exists(test_path + ".lock"): os.remove(test_path + ".lock")
        
        test_truncation_logic()
    finally:
        if os.path.exists(test_path):
             try: os.remove(test_path)
             except: pass
        if os.path.exists(test_path + ".lock"):
             try: os.remove(test_path + ".lock")
             except: pass
