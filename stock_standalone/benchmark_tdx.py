import os
import sys
import time
import pandas as pd
import numpy as np

# Add workspace to path
sys.path.append(os.getcwd())

from JSONData import tdx_data_Day as tdd
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct

def benchmark():
    print("Starting benchmark...")
    
    # Test getSinaAlldf
    with cct.timed_ctx("getSinaAlldf_all", warn_ms=1000):
        df_sina = tdd.getSinaAlldf(market='cyb')
    print(f"getSinaAlldf(all) count: {len(df_sina)}")
    
    # Test get_append_lastp_to_df
    with cct.timed_ctx("get_append_lastp_to_df_init", warn_ms=1000):
        # We pass None to force first-time initialization
        top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_all=df_sina)
    print(f"get_append_lastp_to_df count: {len(top_all)}")
    
    cct.print_timing_summary()

if __name__ == "__main__":
    benchmark()
