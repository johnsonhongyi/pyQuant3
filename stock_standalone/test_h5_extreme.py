
import os
import sys
import pandas as pd
import traceback
import logging
import time

# 配置日志到控制台
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# 添加项目路径
sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')
from JohnsonUtil import commonTips as cct

# --- Mock 交易时间 ---
cct.get_work_time = lambda: True

import JSONData.tdx_hdf5_api as h5a

def test_extreme_logging():
    test_h5 = r'G:\sina_MultiIndex_data_test.h5'
    if not os.path.exists(test_h5):
        print(f"Error: {test_h5} not found.")
        return

    try:
        with pd.HDFStore(test_h5, mode='r') as store:
            table_name = store.keys()[0].lstrip('/')
            df_new = store.get(table_name).tail(100)
    except Exception as e:
        print(f"Read error: {e}")
        return

    print(f"\n>>> [STRESS TEST] Starting write_hdf_db...")
    start_t = time.time()
    success = h5a.write_hdf_db(test_h5, df_new, table=table_name, index=False, MultiIndex=True, append=True, rewrite=False)
    duration = time.time() - start_t
    print(f"\n>>> TOTAL DURATION: {duration:.4f}s")

if __name__ == "__main__":
    test_extreme_logging()
