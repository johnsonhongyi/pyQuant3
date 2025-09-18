import os
import time
import pandas as pd
from multiprocessing import Process
import sys
sys.path.append("../../")
# from JSONData.tdx_hdf5_api2 import SafeHDFStore   # 假设你把上面整合好的类保存为 safe_hdf.py
from JSONData.tdx_hdf5_api import SafeHDFStore   # 假设你把上面整合好的类保存为 safe_hdf.py


import os
import time
import pandas as pd
from multiprocessing import Process
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# 假设 SafeHDFStore 已经按上一个代码定义好
# from safe_hdf_store import SafeHDFStore
log.setLevel(logging.DEBUG)
def worker(proc_id, h5file):
    """每个进程写入3轮数据"""
    for i in range(3):
        try:
            with SafeHDFStore(h5file, mode="a") as store:
                df = pd.DataFrame({"value": [proc_id * 100 + i]})
                key = f"proc_{proc_id}_round_{i}"
                store.write_safe(key, df)
                print(f"[Proc {proc_id}] wrote {key}")
                time.sleep(1)
        except Exception as e:
            print(f"[Proc {proc_id}] error: {e}")

if __name__ == "__main__":
    h5file = "test_safe.h5"

    # 清理旧文件和锁
    if os.path.exists(h5file):
        os.remove(h5file)
    if os.path.exists(h5file + ".lock"):
        os.remove(h5file + ".lock")

    # 启动两个进程同时写
    p1 = Process(target=worker, args=(1, h5file))
    p2 = Process(target=worker, args=(2, h5file))

    p1.start()
    p2.start()

    p1.join()
    p2.join()

    # 读取验证最终内容
    with SafeHDFStore(h5file, mode="r") as store:
        print("Final keys:", store.keys())
        for key in store.keys():
            print(key, store.get(key))
