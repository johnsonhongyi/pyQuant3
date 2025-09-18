import multiprocessing
import pandas as pd
import numpy as np
import os
import time
import random
# from safe_hdf_store import SafeHDFStore  # 假设你保存上面的类为 safe_hdf_store.py
from tdx_hdf5_api import SafeHDFStore
FNAME = f"G:\\test_safestore.h5"
HDF_FILE = f"G:\\test_safestore.h5"
KEY = "test_data"

# def writer_process(proc_id, steps=10):
#     """写入模拟数据，随机间隔"""
#     write_count = 0
#     for i in range(steps):
#         df = pd.DataFrame({
#             "A": np.random.rand(10),
#             "B": np.random.rand(10),
#             "proc": proc_id,
#             "step": i
#         })
#         try:
#             with SafeHDFStore(FNAME, mode='a') as store:
#                 store.write_safe(f"{KEY}_{proc_id}_{i}", df)
#             write_count += 1
#             print(f"[Writer {proc_id}] Step {i} 写入完成")
#         except Exception as e:
#             print(f"[Writer {proc_id}] Step {i} 写入失败: {e}")
#         time.sleep(random.uniform(0.5, 2.0))
#     print(f"[Writer {proc_id}] 总写入次数: {write_count}")

# def reader_process(proc_id, steps=10):
#     """读取 HDFStore 数据"""
#     read_count = 0
#     for i in range(steps):
#         try:
#             with SafeHDFStore(FNAME, mode='r') as store:
#                 keys = store.keys()
#                 for key in keys:
#                     df = store[key]
#                     print(f"[Reader {proc_id}] Step {i} 读取 key {key}, shape={df.shape}")
#                     read_count += 1
#         except Exception as e:
#             print(f"[Reader {proc_id}] Step {i} 读取失败: {e}")
#         time.sleep(random.uniform(0.5, 1.5))
#     print(f"[Reader {proc_id}] 总读取次数: {read_count}")

# if __name__ == "__main__":
#     # 清理测试文件
#     if os.path.exists(FNAME):
#         os.remove(FNAME)
    
#     processes = []

#     # 启动多个写进程
#     for w in range(2):
#         p = multiprocessing.Process(target=writer_process, args=(w, 10))
#         processes.append(p)

#     # 启动多个读进程
#     for r in range(2):
#         p = multiprocessing.Process(target=reader_process, args=(r, 10))
#         processes.append(p)

#     # 启动所有进程
#     for p in processes:
#         p.start()

#     # 等待所有进程完成
#     for p in processes:
#         p.join()

#     print("无人值守多进程测试完成")


import multiprocessing as mp
import pandas as pd
import numpy as np
import time
# from safe_hdf import SafeHDFStore  # 假设你保存的类文件名是 safe_hdf.py

# HDF_FILE = "test_safefile.h5"

def writer_proc(proc_id, steps=5):
    for step in range(steps):
        with SafeHDFStore(HDF_FILE, mode='a') as h5:
            key = f"/writer_{proc_id}_{step}"
            df = pd.DataFrame(np.random.randn(10, 4), columns=list('ABCD'))
            h5.write_safe(key, df)
            log_msg = f"[Writer {proc_id}] Step {step} 写入完成 key {key}"
            print(log_msg)
        time.sleep(0.2)  # 模拟写入间隔
    print(f"[Writer {proc_id}] 总写入完成")

def reader_proc(proc_id, steps=5):
    for step in range(steps):
        with SafeHDFStore(HDF_FILE, mode='r') as h5:
            keys = h5.keys()
            for key in keys:
                df = h5.read_key(key)
                print(f"[Reader {proc_id}] Step {step} 读取 key {key}, shape={df.shape}")
        time.sleep(0.2)  # 模拟读取间隔
    print(f"[Reader {proc_id}] 总读取完成")

if __name__ == "__main__":
    # log = SafeHDFStore.__dict__['log']  # 使用 SafeHDFStore 内部 log 输出
    writers = [mp.Process(target=writer_proc, args=(i, 10)) for i in range(2)]
    readers = [mp.Process(target=reader_proc, args=(i, 10)) for i in range(1)]

    for p in writers + readers:
        p.start()

    for p in writers + readers:
        p.join()

    print("无人值守多进程测试完成")


# 