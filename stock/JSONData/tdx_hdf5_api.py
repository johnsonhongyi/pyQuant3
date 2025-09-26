# -*- encoding: utf-8 -*-
# !/usr/bin/python
# from __future__ import division

import os
import sys
import time
import pandas as pd
from pandas import HDFStore
sys.path.append("..")
from JohnsonUtil import LoggerFactory
# from JohnsonUtil.commonTips import get_ramdisk_dir
# print get_ramdisk_dir()
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct
import random
import numpy as np
import subprocess
log = LoggerFactory.log
import gc
global RAMDISK_KEY, INIT_LOG_Error,Debug_is_not_find
RAMDISK_KEY = 0
INIT_LOG_Error = 0
Debug_is_not_find = 0
# Compress_Count = 1
BaseDir = cct.get_ramdisk_dir()
import tables
#import fcntl linux
#lock：
# fcntl.flock(f,fcntl.LOCK_EX)
# unlock
# fcntl.flock(f,fcntl.LOCK_UN)

# for win
# with portalocker.Lock('some_file', 'rb+', timeout=60) as fh:
#     # do what you need to do
#     ...
 
#     # flush and sync to filesystem
#     fh.flush()
#     os.fsync(fh.fileno())
# import os, time, random, subprocess, logging
# from pandas import HDFStore


# 日志配置

# log_file = os.path.join(BaseDir, "tdx_hdf5.log")
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     handlers=[
#         logging.FileHandler(log_file, encoding="utf-8"),
#         logging.StreamHandler()
#     ]
# )
# log = logging.getLogger(__name__)








import psutil

# import os
# import time
# import random
# import subprocess
# import pandas as pd
# from pandas import HDFStore
# import tables
# import logging

# # ===== 日志初始化 =====
# log = logging.getLogger("SafeHDF")
# log.setLevel(logging.DEBUG)
# console_handler = logging.StreamHandler()
# console_handler.setLevel(logging.DEBUG)
# formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
# console_handler.setFormatter(formatter)
# if not log.hasHandlers():
#     log.addHandler(console_handler)

# class SafeHDFLock:
#     def __init__(self, lockfile, lock_timeout=60, max_wait=300, probe_interval=3):
#         self._lock = lockfile
#         self.lock_timeout = lock_timeout   # 单个锁的占用时间
#         self.max_wait = max_wait           # 总等待时间
#         self.probe_interval = probe_interval
#         self._flock = False

#     def acquire(self):
#         start_time = time.time()
#         retries = 0

#         while True:
#             try:
#                 if not os.path.exists(self._lock):
#                     with open(self._lock, "w") as f:
#                         f.write(f"{os.getpid()}|{time.time()}")
#                     self._flock = True
#                     log.info(f"[Lock] acquired {self._lock} by pid={os.getpid()}")
#                     break

#                 with open(self._lock, "r") as f:
#                     content = f.read().strip()

#                 pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
#                 pid = int(pid_str) if pid_str.isdigit() else -1
#                 ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0

#                 elapsed = time.time() - ts
#                 total_wait = time.time() - start_time
#                 pid_alive = psutil.pid_exists(pid)

#                 if not pid_alive:
#                     log.warning(f"[Lock] stale lock: pid {pid} not alive, removing {self._lock}")
#                     try:
#                         os.remove(self._lock)
#                         continue
#                     except Exception as e:
#                         log.error(f"[Lock] failed to remove stale lock: {e}")

#                 elif elapsed > self.lock_timeout:
#                     log.warning(f"[Lock] held too long: pid={pid} alive={pid_alive} "
#                                 f"elapsed={elapsed:.1f}s > timeout={self.lock_timeout}s")

#                 if total_wait > self.max_wait:
#                     log.error(f"[Lock] wait > {self.max_wait}s, force removing lock {self._lock}")
#                     try:
#                         os.remove(self._lock)
#                         continue
#                     except Exception as e:
#                         log.error(f"[Lock] force remove failed: {e}")

#                 retries += 1
#                 log.info(f"[Lock] exists, pid={pid}, alive={pid_alive}, "
#                          f"elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
#                 time.sleep(self.probe_interval)

#             except Exception as e:
#                 log.error(f"[Lock] error acquiring: {e}")
#                 time.sleep(self.probe_interval)

#     def release(self):
#         if self._flock and os.path.exists(self._lock):
#             try:
#                 os.remove(self._lock)
#                 log.info(f"[Lock] released {self._lock}")
#             except Exception as e:
#                 log.error(f"[Lock] release failed: {e}")
#         self._flock = False


class SafeHDFStore(pd.HDFStore):
    def __init__(self, fname, mode='a', **kwargs):
        self.fname_o = fname
        self.mode = mode
        self.probe_interval = kwargs.pop("probe_interval", 2)  
        self.lock_timeout = kwargs.pop("lock_timeout", 10)  
        self.max_wait = 60
        self.multiIndexsize = False
        self.log = log
        self.basedir = BaseDir
        self.log.info(f'{self.fname_o.lower()} {self.basedir.lower()}')
        self.start_time = time.time()
        self.config_ini = self.basedir + os.path.sep+ 'h5config.txt'

        self.complevel = 9
        self.complib = 'zlib'
        self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"

        self.h5_size_org = 0
        global RAMDISK_KEY


        if self.fname_o.lower().find(self.basedir.lower()) < 0 and (self.fname_o == cct.tdx_hd5_name or self.fname_o.find('tdx_all_df') >= 0):
            self.multiIndexsize = True
            self.fname = cct.get_run_path_tdx(self.fname_o)
            self.basedir = self.fname.split(self.fname_o)[0]
            self.log.info(f"tdx_hd5: {self.fname}")
        else:
            self.fname = cct.get_ramdisk_path(self.fname_o)
            self.basedir = self.fname.split(self.fname_o)[0]
            self.log.info(f"ramdisk_hd5: {self.fname}")

        if self.multiIndexsize or self.fname_o.find('sina_MultiIndex') >= 0:
            self.big_H5_Size_limit = ct.big_H5_Size_limit * 6
        else:
            self.big_H5_Size_limit = ct.big_H5_Size_limit
        self.log.info(f'self.big_H5_Size_limit :{self.big_H5_Size_limit} self.multiIndexsize :{self.multiIndexsize}')
        if not os.path.exists(self.basedir):
            if RAMDISK_KEY < 1:
                log.error("NO RamDisk Root:%s" % (baseDir))
                RAMDISK_KEY += 1
        else:
            self.temp_file = self.fname + '_tmp'
            if os.path.exists(self.fname):
                self.h5_size_org = os.path.getsize(self.fname) / 1000 / 1000


        self._lock = self.fname + ".lock"
        self._flock = None
        self.write_status = True if os.path.exists(self.fname) else False
        self.my_pid = os.getpid()
        self.log.info(f"self.fname: {self.fname} self.basedir:{self.basedir}")
        # if not os.path.exists(self.fname):
        #     log.warning(f"HDF5 file {self.fname} not found. Creating empty file.")
        #     with pd.HDFStore(self.fname, mode='a') as store:
        #         pass

        if self.mode != 'r':
            self._acquire_lock()
        elif self.mode == 'r':
            self._wait_for_lock()
        self.log.info(f'mode : {self.mode}  fname:{self.fname}')
        # self._check_and_clean_corrupt_keys()
        self.ensure_hdf_file() 
        # super().__init__(self.fname, mode=self.mode, **kwargs)
        super().__init__(self.fname, **kwargs)

    def ensure_hdf_file(self):
        """确保 HDF5 文件存在"""
        if not os.path.exists(self.fname):
            # 使用 'w' 创建空文件
            pd.HDFStore(self.fname, mode='w').close()

    def write_safe(self, key, df, append=False,  chunksize=10000, **kwargs):
        """
        安全写入 HDF5，无论 store 打开模式是 'a' 还是 'w'
        自动加锁、删除损坏 key、自动计算 chunksize
        """

        
        # 确保文件加锁（如果自己持有锁则不会重复加锁）
        # if mode != 'r' 已加锁
        # self._acquire_lock()

        # 删除损坏 key
        if key in self.keys():
            try:
                _ = self.get(key)
            except (tables.exceptions.HDF5ExtError, AttributeError):
                self.log.info(f"Corrupt key {key} detected, removing")
                try:
                    self.remove(key)
                except Exception as e:
                    self.log.info(f"Failed to remove key {key}: {e}")

        # 写入
        try:
            # if append:
            #      # 如果传了 chunksize 自动切 table
            #     if 'chunksize' in kwargs and 'format' not in kwargs:
            #         kwargs['format'] = 'table'

            #     if 'chunksize' not in kwargs:
            #         col_bytes = sum(
            #             8 if pd.api.types.is_numeric_dtype(dt) else 50
            #             for dt in df.dtypes
            #         )
            #         target_chunk_size = 5 * 1024 * 1024  # 5MB
            #         kwargs['chunksize'] = max(1000, int(target_chunk_size / col_bytes))
            #         self.log.info(f"Auto chunksize for key {key}: {kwargs['chunksize']} rows")

            #     # 使用 append 写入，支持 chunksize
            #     self.append(key, df, **kwargs, chunksize=chunksize)
            # else:
            #     # 覆盖写入，使用 put，不支持 chunksize
            #     self.put(key, df, **kwargs)
            self.put(key, df, format='table', **kwargs)
            self.log.info(f"Successfully wrote key: {key}")
        except Exception as e:
            self.log.error(f"Failed to write key {key}: {e}")

    def write_safe1(self, key, df, **kwargs):
        """安全写入 HDF5，自动计算合理 chunksize"""
        corrupt = False
        if key in self.keys():
            try:
                _ = self.get(key)
            except (tables.exceptions.HDF5ExtError, AttributeError) as e:
                self.log.warning(f"Key {key} corrupted: {e}, removing before rewrite")
                corrupt = True

        if corrupt:
            try:
                self.remove(key)
                self.log.info(f"Removed corrupted key: {key}")
            except Exception as e:
                self.log.error(f"Failed to remove key {key}: {e}")

        # 自动计算 chunksize
        if 'chunksize' not in kwargs:
            # 每列字节大小估算
            col_bytes = 0
            for dtype in df.dtypes:
                if pd.api.types.is_float_dtype(dtype):
                    col_bytes += 8
                elif pd.api.types.is_integer_dtype(dtype):
                    col_bytes += 8  # 用 int64 计算
                elif pd.api.types.is_bool_dtype(dtype):
                    col_bytes += 1
                else:
                    # object 或 category 类型，估算每值 50 字节
                    col_bytes += 50
            # 目标每 chunk 约 5MB
            target_chunk_size = 5 * 1024 * 1024
            chunksize = max(1000, int(target_chunk_size / col_bytes))
            kwargs['chunksize'] = chunksize
            self.log.info(f"Auto chunksize for key {key}: {chunksize} rows (≈ {target_chunk_size/1024/1024} MB)")

        try:
            self.put(key, df, format='table', **kwargs)
            self.log.info(f"Successfully wrote key: {key}")
        except Exception as e:
            self.log.error(f"Failed to write key {key}: {e}")


    def _check_and_clean_corrupt_keys(self):
        try:
            with pd.HDFStore(self.fname, mode='r') as store:
                keys = store.keys()
                corrupt_keys = []
                for key in keys:
                    try:
                        _ = store.get(key)
                    except (tables.exceptions.HDF5ExtError, AttributeError) as e:
                        log.error(f"Failed to read key {key}: {e}")
                        corrupt_keys.append(key)
                if corrupt_keys:
                    log.warning(f"Corrupt keys detected: {corrupt_keys}, removing...")
                    store.close()
                    with pd.HDFStore(self.fname, mode='a') as wstore:
                        for key in corrupt_keys:
                            try:
                                wstore.remove(key)
                                self.log.info(f"Removed corrupted key: {key}")
                            except Exception as e:
                                self.log.error(f"Failed to remove key {key}: {e}")
        except Exception as e:
            log.error(f"HDF5 file {self.fname} corrupted, recreating: {e}")
            with pd.HDFStore(self.fname, mode='w') as store:
                pass

    def _acquire_lock(self):
        my_pid = os.getpid()
        retries = 0
        try:
            while True:
                # 检查锁文件是否存在
                if os.path.exists(self._lock):
                    with open(self._lock, "r") as f:
                        content = f.read().strip()
                    pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
                    pid = int(pid_str) if pid_str.isdigit() else -1
                    ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0
                    elapsed = time.time() - ts
                    total_wait = time.time() - self.start_time
                    pid_alive = psutil.pid_exists(pid)

                    if pid == my_pid:
                        # 自己持有锁，直接清理并重建锁
                        self.log.info(f"[Lock] 超时自解锁 (pid={pid}) (my_pid:{my_pid}), removing and reacquiring")
                        try:
                            os.remove(self._lock)
                        except Exception as e:
                            self.log.error(f"[Lock] failed to remove self lock: {e}")
                        continue

                    if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
                        # 锁超时或持有锁进程不存在，可以删除锁
                        self.log.warning(f"[Lock] 强制解超时锁 pid={pid} (my_pid:{my_pid}), removing {self._lock}")
                        try:
                            os.remove(self._lock)
                        except Exception as e:
                            self.log.error(f"[Lock] 强制解超时锁 失败: {e}")
                        continue

                    # 其他进程持有锁，等待
                    retries += 1
                    if retries % 3 == 0:
                        self.log.info(f"[Lock] 重试:{retries} 等待 进程锁, pid={pid},(my_pid:{my_pid}), alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s")
                    time.sleep(self.probe_interval)

                else:
                    # 创建锁文件
                    try:
                        with open(self._lock, "w") as f:
                            f.write(f"{my_pid}|{time.time()}")
                        self.log.info(f"[Lock] 创建锁文件 {self._lock} by pid={my_pid}")
                        return True
                    except Exception as e:
                        self.log.error(f"[Lock] 创建锁文件 失败: {e}")
                        time.sleep(self.probe_interval)
        except Exception as e:
                self.log.warning(f"[Lock] KeyboardInterrupt during lock acquire, releasing lock:{e}")
                self._release_lock()
                raise

    def _forced_unlock(self):
        my_pid = os.getpid()
        retries = 0
        while True:
            # 检查锁文件是否存在
            if os.path.exists(self._lock):
                with open(self._lock, "r") as f:
                    content = f.read().strip()
                pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
                pid = int(pid_str) if pid_str.isdigit() else -1
                ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0
                elapsed = time.time() - ts
                total_wait = time.time() - self.start_time
                pid_alive = psutil.pid_exists(pid)

                if pid == my_pid:
                    # 自己持有锁，直接清理并重建锁
                    self.log.info(f"[Lock] 超时解自锁 (pid={pid}) (my_pid:{my_pid}), removing and reacquiring")
                    try:
                        os.remove(self._lock)
                        return True
                    except Exception as e:
                        self.log.error(f"[Lock] failed to remove self lock: {e}")
                        if retries > 3:
                            return False
                    continue

                if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
                    # 锁超时或持有锁进程不存在，可以删除锁
                    self.log.warning(f"[Lock] 强制解超时锁 pid={pid} (my_pid:{my_pid}), removing {self._lock}")
                    try:
                        os.remove(self._lock)
                        return True
                    except Exception as e:
                        self.log.error(f"[Lock] 强制解超时锁 失败: {e}")
                        if retries > 3:
                            return False
                    continue

                # 其他进程持有锁，等待
                retries += 1
                if retries % 3 == 0:
                    self.log.info(f"[Lock] exists, pid={pid},(my_pid:{my_pid}), alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
                time.sleep(self.probe_interval)

    def _wait_for_lock(self):
        """读取模式等待锁释放"""
        # start_time = time.time()
        while os.path.exists(self._lock):
            try:
                with open(self._lock, "r") as f:
                    pid_str, ts_str = f.read().strip().split("|")
                    lock_pid = int(pid_str)
                    ts = float(ts_str)
            except Exception:
                lock_pid = None
                ts = 0
            elapsed = time.time() - ts
            total_wait = time.time() - self.start_time
            if elapsed > self.lock_timeout: 
                self._forced_unlock()
            self.log.info(f"[{self.my_pid}] Waiting for lock held by pid={lock_pid}, elapsed={elapsed:.1f}s total_wait={total_wait:.1f}s")
            time.sleep(self.probe_interval)

    def _release_lock(self):
        if os.path.exists(self._lock):
            try:
                with open(self._lock, "r") as f:
                    pid_in_lock = int(f.read().split("|")[0])
                if pid_in_lock == self.my_pid:
                    os.remove(self._lock)
                    self.log.info(f"[{self.my_pid}] Lock released: {self._lock}")
            except Exception as e:
                self.log.error(f"[{self.my_pid}] Failed to release lock: {e}")

    # def release_lock(self):
    #     """关闭 store 时释放自己持有的锁"""
    #     my_pid = os.getpid()
    #     if os.path.exists(self._lock):
    #         try:
    #             with open(self._lock, "r") as f:
    #                 pid_str, _ = f.read().split("|")
    #                 if int(pid_str) == my_pid:
    #                     os.remove(self._lock)
    #                     self.log.info(f"[Lock] released lock {self._lock} by pid={my_pid}")
    #         except Exception as e:
    #             self.log.error(f"[Lock] failed to release lock {self._lock}: {e}")

    def close(self):
        super().close()
        # self._release_lock()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.write_status:
            try:
                self.close()
                super().__exit__(exc_type, exc_val, exc_tb)
                if self.mode != 'r':
                    # ===== 压缩逻辑 =====
                    h5_size = int(os.path.getsize(self.fname) / 1e6)
                    h5_size_limit =  h5_size*2 if h5_size > 10 else 10
                    if self.fname_o.find('tdx_all_df') >= 0 or self.fname_o.find('sina_MultiIndex_data') >= 0:
                        h5_size = 40 if h5_size < 40 else h5_size
                        new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit) if h5_size > self.big_H5_Size_limit else self.big_H5_Size_limit
                    else:
                        new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit) if h5_size > self.big_H5_Size_limit else h5_size_limit
                        
                    read_ini_limit = cct.get_config_value(self.config_ini,self.fname_o,read=True)
                    self.log.info(f"fname: {self.fname} h5_size: {h5_size} big_limit: {self.big_H5_Size_limit} conf:{read_ini_limit}")
                    # if (read_ini_limit is  None and h5_size > self.big_H5_Size_limit) or cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
                    if cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
                        if self.mode == 'r':
                            self._acquire_lock()
                        if os.path.exists(self.fname) and os.path.exists(self.temp_file):
                            log.error(f"Remove tmp file exists: {self.temp_file}")
                            os.remove(self.temp_file)
                        os.rename(self.fname, self.temp_file)
                        if cct.get_os_system() == 'mac':
                            p = subprocess.Popen(
                                self.ptrepack_cmds % (self.complib, self.temp_file, self.fname),
                                shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                            )
                        else:
                            back_path = os.getcwd()
                            os.chdir(self.basedir)
                            pt_cmd = self.ptrepack_cmds % (
                                self.complib,
                                self.temp_file.split(self.basedir)[1],
                                self.fname.split(self.basedir)[1]
                            )
                            p = subprocess.Popen(pt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        p.wait()
                        if p.returncode != 0:
                            log.error(f"ptrepack error {p.communicate()}, src {self.temp_file}, dest {self.fname}")
                        else:
                            if os.path.exists(self.temp_file):
                                os.remove(self.temp_file)
                        if cct.get_os_system() != 'mac':
                            os.chdir(back_path)
            finally:
                time.sleep(0.1)
                self._release_lock()
                self.log.info(f'clean:{self.fname}')
        else:
            self.close()
            super().__exit__(exc_type, exc_val, exc_tb)
# class SafeHDFStore_lastOne(HDFStore):
#     def __init__(self, fname, mode='r', **kwargs):
       
#         self.fname_o = fname
#         self.mode = mode
#         self.probe_interval = kwargs.pop("probe_interval", 2)  
#         self.lock_timeout = kwargs.pop("lock_timeout", 10)  
#         self.max_wait = 60
#         self.multiIndexsize = False
#         # ===== 原有路径处理逻辑 =====
#         if self.fname_o == cct.tdx_hd5_name or self.fname_o.find('tdx_all_df') >= 0:
#             self.multiIndexsize = True
#             self.fname = cct.get_run_path_tdx(self.fname_o)
#             self.basedir = self.fname.split(self.fname_o)[0]
#             log.info(f"tdx_hd5: {self.fname}")
#         else:
#             self.fname = cct.get_ramdisk_path(self.fname_o)
#             self.basedir = self.fname.split(self.fname_o)[0]
#             log.info(f"ramdisk_hd5: {self.fname}")

#         self._lock = self.fname + ".lock"
#         self._flock = None
#         self.write_status = True if os.path.exists(self.fname) else False

#         self.complevel = 9
#         self.complib = 'zlib'
#         self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"
#         self.temp_file = self.fname + '_tmp'
#         self.big_H5_Size_limit = 200  

#         if not os.path.exists(self.fname):
#             log.warning(f"HDF5 file {self.fname} not found. Creating empty file.")
#             with pd.HDFStore(self.fname, mode='w') as store:
#                 pass

#         self._check_and_clean_corrupt_keys()

#         if mode != 'r':
#             self._acquire_lock()
#         elif mode == 'r':
#             self._wait_for_lock()

#         super().__init__(self.fname, mode=mode, **kwargs)

#     def write_safe(self, key, df, **kwargs):
#         corrupt = False
#         if key in self.keys():
#             try:
#                 _ = self.get(key)
#             except (tables.exceptions.HDF5ExtError, AttributeError) as e:
#                 log.warning(f"Key {key} corrupted: {e}, removing before rewrite")
#                 corrupt = True
#         if corrupt:
#             try:
#                 self.remove(key)
#                 log.info(f"Removed corrupted key: {key}")
#             except Exception as e:
#                 log.error(f"Failed to remove key {key}: {e}")
#         try:
#             self.put(key, df, **kwargs)
#             log.info(f"Successfully wrote key: {key}")
#         except Exception as e:
#             log.error(f"Failed to write key {key}: {e}")

#     def _check_and_clean_corrupt_keys(self):
#         try:
#             with pd.HDFStore(self.fname, mode='r') as store:
#                 keys = store.keys()
#                 corrupt_keys = []
#                 for key in keys:
#                     try:
#                         _ = store.get(key)
#                     except (tables.exceptions.HDF5ExtError, AttributeError) as e:
#                         log.error(f"Failed to read key {key}: {e}")
#                         corrupt_keys.append(key)
#                 if corrupt_keys:
#                     log.warning(f"Corrupt keys detected: {corrupt_keys}, removing...")
#                     store.close()
#                     with pd.HDFStore(self.fname, mode='a') as wstore:
#                         for key in corrupt_keys:
#                             try:
#                                 wstore.remove(key)
#                                 log.info(f"Removed corrupted key: {key}")
#                             except Exception as e:
#                                 log.error(f"Failed to remove key {key}: {e}")
#         except Exception as e:
#             log.error(f"HDF5 file {self.fname} corrupted, recreating: {e}")
#             with pd.HDFStore(self.fname, mode='w') as store:
#                 pass

#     def _acquire_lock(self):
#         """获取文件锁，支持超时检测和轮询提示"""
#         start_time = time.time()
#         while True:
#             try:
#                 # 尝试创建锁文件
#                 self._flock = os.open(self._lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
#                 with open(self._lock, "w") as f:
#                     f.write(f"{os.getpid()}|{time.time()}")
#                 log.info(f"SafeHDF: acquired lock {self._lock}")
#                 break

#             except FileExistsError:
#                 # 锁文件存在，读取信息
#                 try:
#                     with open(self._lock, "r") as f:
#                         content = f.read().strip()
#                     pid_str, ts_str = content.split("|")
#                     ts = float(ts_str)
#                 except Exception:
#                     ts = 0  # 锁文件损坏，直接当作陈旧锁

#                 elapsed = time.time() - ts
#                 total_wait = time.time() - start_time

#                 if elapsed > self.lock_timeout:
#                     log.warning(f"SafeHDF: stale lock detected (age {elapsed:.1f}s), removing {self._lock}")
#                     try:
#                         os.remove(self._lock)
#                     except Exception as e:
#                         log.error(f"SafeHDF: failed to remove stale lock: {e}")

#                 elif total_wait > self.max_wait:
#                     log.error(f"SafeHDF: wait exceeded {self.max_wait}s, force removing lock {self._lock}")
#                     try:
#                         os.remove(self._lock)
#                     except Exception as e:
#                         log.error(f"SafeHDF: failed to force remove lock: {e}")

#                 else:
#                     log.info(f"SafeHDF: lock exists, waiting... elapsed={elapsed:.1f}s total_wait={total_wait:.1f}s")
#                     time.sleep(self.probe_interval)

#             except Exception as e:
#                 log.error(f"SafeHDF: unexpected error acquiring lock: {e}")
#                 time.sleep(self.probe_interval)


    #没有轮训提示,逻辑锁前一版本
    # def _acquire_lock(self):
    #     start_time = time.time()
    #     while True:
    #         try:
    #             if not os.path.exists(self._lock):
    #                 with open(self._lock, 'w') as f:
    #                     f.write(f"{os.getpid()}|{time.time()}")
    #                 self._flock = True
    #                 log.info(f"Acquired lock {self._lock}")
    #                 break
    #             else:
    #                 with open(self._lock, 'r') as f:
    #                     content = f.read()
    #                 try:
    #                     pid_str, ts_str = content.split('|')
    #                     ts = float(ts_str)
    #                 except Exception:
    #                     ts = 0
    #                 elapsed = time.time() - ts
    #                 if elapsed > self.lock_timeout:
    #                     log.warning(f"Lock timeout {elapsed:.1f}s, removing stale lock")
    #                     try:
    #                         os.remove(self._lock)
    #                     except Exception as e:
    #                         log.error(f"Failed to remove stale lock: {e}")
    #                 else:
    #                     log.info(f"Lock exists, waiting... elapsed {elapsed:.1f}s")
    #                     time.sleep(self.probe_interval)
    #         except Exception as e:
    #             log.error(f"Error acquiring lock: {e}")
    #             time.sleep(self.probe_interval)

    # #逻辑锁
    # def _acquire_lock(self):
    #     """获取文件锁，支持超时清理 + 轮询提示"""
    #     start_time = time.time()
    #     retries = 0

    #     while True:
    #         try:
    #             # 如果不存在锁文件，直接创建
    #             if not os.path.exists(self._lock):
    #                 with open(self._lock, 'w') as f:
    #                     f.write(f"{os.getpid()}|{time.time()}")
    #                 self._flock = True
    #                 self.log.info(f"[Lock] Acquired lock {self._lock}")
    #                 break

    #             # 已存在锁文件 -> 检查内容
    #             with open(self._lock, 'r') as f:
    #                 content = f.read().strip()

    #             try:
    #                 pid_str, ts_str = content.split('|')
    #                 ts = float(ts_str)
    #             except Exception:
    #                 ts = 0  # 文件损坏时，直接清理

    #             elapsed = time.time() - ts
    #             wait_time = time.time() - start_time

    #             if elapsed > self.lock_timeout:
    #                 # 超时锁 -> 删除
    #                 self.log.warning(f"[Lock] Timeout {elapsed:.1f}s, removing stale lock")
    #                 try:
    #                     os.remove(self._lock)
    #                 except Exception as e:
    #                     self.log.error(f"[Lock] Failed to remove stale lock: {e}")
    #             else:
    #                 retries += 1
    #                 self.log.info(
    #                     f"[Lock] Exists, waiting... elapsed={elapsed:.1f}s, "
    #                     f"total_wait={wait_time:.1f}s, retry={retries}"
    #                 )
    #                 # 如果重试超过最大次数 -> 强制删除
    #                 if retries >= self.max_retries:
    #                     self.log.warning(f"[Lock] Max retries {retries} reached, force removing lock")
    #                     try:
    #                         os.remove(self._lock)
    #                     except Exception as e:
    #                         self.log.error(f"[Lock] Force remove failed: {e}")
    #                 time.sleep(self.probe_interval)

    #         except Exception as e:
    #             self.log.error(f"[Lock] Error acquiring lock: {e}")
    #             time.sleep(self.probe_interval)


    # def _wait_for_lock(self):
    #     while os.path.exists(self._lock):
    #         try:
    #             with open(self._lock, 'r') as f:
    #                 content = f.read()
    #             try:
    #                 pid_str, ts_str = content.split('|')
    #                 ts = float(ts_str)
    #             except Exception:
    #                 ts = 0
    #             elapsed = time.time() - ts
    #             if elapsed > self.lock_timeout:
    #                 log.warning(f"Read wait lock timeout {elapsed:.1f}s, removing stale lock")
    #                 try:
    #                     os.remove(self._lock)
    #                 except Exception as e:
    #                     log.error(f"Failed to remove stale lock: {e}")
    #                 break
    #             log.info(f"Waiting for lock... elapsed {elapsed:.1f}s")
    #             time.sleep(self.probe_interval)
    #         except Exception as e:
    #             log.error(f"Error waiting for lock: {e}")
    #             time.sleep(self.probe_interval)

    # def _release_lock(self):
    #     if self._flock:
    #         try:
    #             self._flock = None
    #             if os.path.exists(self._lock):
    #                 os.remove(self._lock)
    #                 log.info(f"Released lock {self._lock}")
    #         except Exception as e:
    #             log.error(f"Failed to release lock: {e}")

    # def __enter__(self):
    #     return self

    # def __exit__(self, exc_type, exc_val, exc_tb):
    #     try:
    #         super().__exit__(exc_type, exc_val, exc_tb)
    #         h5_size = os.path.getsize(self.fname) / 1e6
    #         new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit)
    #         log.info(f"fname: {self.fname}, size: {h5_size:.1f}MB, limit: {self.big_H5_Size_limit}MB")
    #         if h5_size > self.big_H5_Size_limit:
    #             log.info(f"Trigger compression: {self.fname}")
    #             if os.path.exists(self.temp_file):
    #                 os.remove(self.temp_file)
    #             os.rename(self.fname, self.temp_file)
    #             back_path = os.getcwd()
    #             os.chdir(self.basedir)
    #             pt_cmd = self.ptrepack_cmds % (
    #                 self.complib,
    #                 os.path.basename(self.temp_file),
    #                 os.path.basename(self.fname)
    #             )
    #             p = subprocess.Popen(pt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    #             p.wait()
    #             if p.returncode != 0:
    #                 log.error(f"ptrepack error src {self.temp_file} dest {self.fname}")
    #             else:
    #                 if os.path.exists(self.temp_file):
    #                     os.remove(self.temp_file)
    #             os.chdir(back_path)
    #     finally:
    #         self._release_lock()

    # def read_key(self, key):
    #     df = None
    #     try:
    #         df = self[key]
    #     except Exception as e:
    #         log.error(f"Failed to read key {key}: {e}")
    #     return df










# #文件锁最后一版本
# class SafeHDFStor_file_OKe(HDFStore):
#     def __init__(self, fname, mode='r', **kwargs):
#         self.fname_o = fname
#         self.mode = mode
#         self.probe_interval = kwargs.pop("probe_interval", 2)

#         # ===== 路径处理 =====
#         self.multiIndexsize = False
#         if self.fname_o == cct.tdx_hd5_name or 'tdx_all_df' in self.fname_o:
#             self.multiIndexsize = True
#             self.fname = cct.get_run_path_tdx(self.fname_o)
#         else:
#             self.fname = cct.get_ramdisk_path(self.fname_o)
#         self.basedir = os.path.dirname(self.fname)

#         self.config_ini = os.path.join(BaseDir, 'h5config.txt')
#         self._lock = self.fname + ".lock"
#         self._flock = None
#         self.countlock = 0
#         self.write_status = False
#         self.complevel = 9
#         self.complib = 'zlib'
#         self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"
#         self.h5_size_org = os.path.getsize(self.fname) / 1e6 if os.path.exists(self.fname) else 0
#         self.big_H5_Size_limit = ct.big_H5_Size_limit * 6 if self.multiIndexsize else ct.big_H5_Size_limit
#         self.temp_file = self.fname + '_tmp'

#         global RAMDISK_KEY
#         if not os.path.exists(BaseDir):
#             if RAMDISK_KEY < 1:
#                 log.error(f"NO RamDisk Root: {BaseDir}")
#                 RAMDISK_KEY += 1
#         else:
#             self.write_status = True

#         # ===== 文件不存在时创建空文件 =====
#         if not os.path.exists(self.fname):
#             log.warning(f"HDF5 file {self.fname} not found. Creating empty file.")
#             with pd.HDFStore(self.fname, mode='w') as store:
#                 pass

#         # ===== 检测并清理损坏 key =====
#         self._check_and_clean_corrupt_keys()

#         # ===== 写模式加锁，读模式等待锁释放 =====
#         if mode != 'r' and self.write_status:
#             self._acquire_lock()
#         elif mode == 'r':
#             self._wait_for_lock()

#         # ===== 初始化 HDFStore =====
#         super().__init__(self.fname, mode=mode, **kwargs)

#     # ===== 写入安全方法 =====
#     def write_safe(self, key, df, **kwargs):
#         corrupt = False
#         if key in self.keys():
#             try:
#                 _ = self.get(key)
#             except (tables.exceptions.HDF5ExtError, AttributeError) as e:
#                 log.warning(f"Key {key} 损坏: {e}, 将删除后重写")
#                 corrupt = True
#         if corrupt:
#             try:
#                 self.remove(key)
#                 log.info(f"已删除损坏 key: {key}")
#             except Exception as e:
#                 log.error(f"删除 key {key} 失败: {e}")
#         try:
#             self.put(key, df, **kwargs)
#             log.info(f"成功写入 key: {key}")
#         except Exception as e:
#             log.error(f"写入 key {key} 失败: {e}")

#     # ===== 检测并清理损坏 key =====
#     def _check_and_clean_corrupt_keys(self):
#         try:
#             with pd.HDFStore(self.fname, mode='r') as store:
#                 keys = store.keys()
#                 corrupt_keys = []
#                 for key in keys:
#                     try:
#                         _ = store.get(key)
#                     except (tables.exceptions.HDF5ExtError, AttributeError) as e:
#                         log.error(f"读取失败 {key}: {e}")
#                         corrupt_keys.append(key)
#                 if corrupt_keys:
#                     log.warning(f"损坏 keys: {corrupt_keys}, 将被清除")
#                     store.close()
#                     with pd.HDFStore(self.fname, mode='a') as wstore:
#                         for key in corrupt_keys:
#                             try:
#                                 wstore.remove(key)
#                                 log.info(f"已删除损坏 key: {key}")
#                             except Exception as e:
#                                 log.error(f"删除 key {key} 失败: {e}")
#         except Exception as e:
#             log.error(f"HDF5 文件 {self.fname} 损坏，重新创建空文件: {e}")
#             with pd.HDFStore(self.fname, mode='w') as store:
#                 pass

#     # ===== 锁机制 =====
#     def _acquire_lock(self, max_retry=10, wait_range=(2,6)):
#         """尝试获取文件锁，如果失败会重试，超过次数后强制删除残留锁"""
#         attempt = 0
#         while True:
#             attempt += 1
#             try:
#                 self._flock = os.open(self._lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
#                 log.info(f"SafeHDF: acquired lock {self._lock}")
#                 break
#             except FileExistsError:
#                 if attempt <= max_retry:
#                     wait = random.uniform(*wait_range)
#                     log.warning(f"Lock exists, retry {attempt}, sleep {wait:.2f}s")
#                     time.sleep(wait)
#                 else:
#                     log.error(f"Stale lock {self._lock}, removing forcibly")
#                     try:
#                         os.remove(self._lock)
#                         attempt = 0  # 重置计数，继续尝试
#                     except Exception as e:
#                         log.error(f"Failed to remove stale lock: {e}")
#                         time.sleep(3)

#     def _wait_for_lock(self, check_interval=1):
#         waited = 0
#         while os.path.exists(self._lock):
#             waited += check_interval
#             log.warning(f"锁文件存在，读操作等待中... 已等待 {waited}s")
#             time.sleep(check_interval)
#         log.info("锁已释放，读操作继续。")

#     def _release_lock(self):
#         if self._flock:
#             try:
#                 os.close(self._flock)
#             except Exception as e:
#                 log.error(f"Error closing lock fd: {e}")
#             self._flock = None
#         if os.path.exists(self._lock):
#             try:
#                 os.remove(self._lock)
#                 log.info(f"Released lock {self._lock}")
#             except Exception as e:
#                 log.error(f"Failed to remove lock file: {e}")

#     # ===== 上下文管理 =====
#     def __enter__(self):
#         return self if self.write_status else None

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if self.write_status:
#             try:
#                 super().__exit__(exc_type, exc_val, exc_tb)
#                 # ===== 压缩逻辑 =====
#                 h5_size = os.path.getsize(self.fname) / 1e6
#                 new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit)
#                 log.info(f"fname: {self.fname} h5_size: {h5_size} big_limit: {self.big_H5_Size_limit}")
#                 if cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
#                     if os.path.exists(self.fname) and os.path.exists(self.temp_file):
#                         log.error(f"Remove tmp file exists: {self.temp_file}")
#                         os.remove(self.temp_file)
#                     os.rename(self.fname, self.temp_file)
#                     if cct.get_os_system() == 'mac':
#                         p = subprocess.Popen(
#                             self.ptrepack_cmds % (self.complib, self.temp_file, self.fname),
#                             shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
#                         )
#                     else:
#                         back_path = os.getcwd()
#                         os.chdir(self.basedir)
#                         pt_cmd = self.ptrepack_cmds % (
#                             self.complib,
#                             self.temp_file.split(self.basedir)[1],
#                             self.fname.split(self.basedir)[1]
#                         )
#                         p = subprocess.Popen(pt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#                     p.wait()
#                     if p.returncode != 0:
#                         log.error(f"ptrepack error {p.communicate()}, src {self.temp_file}, dest {self.fname}")
#                     else:
#                         if os.path.exists(self.temp_file):
#                             os.remove(self.temp_file)
#                     if cct.get_os_system() != 'mac':
#                         os.chdir(back_path)
#             finally:
#                 self._release_lock()


#有读取检测测试基本正常,lock 文件锁 
# class SafeHDFStore_OK(HDFStore):
#     def __init__(self, fname, mode='r', **kwargs):
#         self.fname_o = fname
#         self.mode = mode
#         self.probe_interval = kwargs.pop("probe_interval", 2)

#         # ===== 路径处理 =====
#         self.multiIndexsize = False
#         if self.fname_o == cct.tdx_hd5_name or 'tdx_all_df' in self.fname_o:
#             self.multiIndexsize = True
#             self.fname = cct.get_run_path_tdx(self.fname_o)
#         else:
#             self.fname = cct.get_ramdisk_path(self.fname_o)
#         self.basedir = os.path.dirname(self.fname)

#         self.config_ini = os.path.join(BaseDir, 'h5config.txt')
#         self._lock = self.fname + ".lock"
#         self._flock = None
#         self.countlock = 0
#         self.write_status = False
#         self.complevel = 9
#         self.complib = 'zlib'
#         self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"
#         self.h5_size_org = os.path.getsize(self.fname) / 1e6 if os.path.exists(self.fname) else 0
#         self.big_H5_Size_limit = ct.big_H5_Size_limit * 6 if self.multiIndexsize else ct.big_H5_Size_limit
#         self.temp_file = self.fname + '_tmp'

#         global RAMDISK_KEY
#         if not os.path.exists(BaseDir):
#             if RAMDISK_KEY < 1:
#                 log.error(f"NO RamDisk Root: {BaseDir}")
#                 RAMDISK_KEY += 1
#         else:
#             self.write_status = True

#         # ===== 文件不存在时创建空文件 =====
#         if not os.path.exists(self.fname):
#             log.warning(f"HDF5 file {self.fname} not found. Creating empty file.")
#             with pd.HDFStore(self.fname, mode='w') as store:
#                 pass

#         # ===== 检测并清理损坏 key =====
#         self._check_and_clean_corrupt_keys()

#         # ===== 写模式加锁，读模式等待锁释放 =====
#         if mode != 'r' and self.write_status:
#             self._acquire_lock()
#         elif mode == 'r':
#             self._wait_for_lock()

#         # ===== 初始化 HDFStore =====
#         super().__init__(self.fname, mode=mode, **kwargs)

#     # ===== 写入安全方法 =====
#     def write_safe(self, key, df, **kwargs):
#         corrupt = False
#         if key in self.keys():
#             try:
#                 _ = self.get(key)
#             except (tables.exceptions.HDF5ExtError, AttributeError) as e:
#                 log.warning(f"Key {key} 损坏: {e}, 将删除后重写")
#                 corrupt = True
#         if corrupt:
#             try:
#                 self.remove(key)
#                 log.info(f"已删除损坏 key: {key}")
#             except Exception as e:
#                 log.error(f"删除 key {key} 失败: {e}")
#         try:
#             self.put(key, df, **kwargs)
#             log.info(f"成功写入 key: {key}")
#         except Exception as e:
#             log.error(f"写入 key {key} 失败: {e}")

#     # ===== 检测并清理损坏 key =====
#     def _check_and_clean_corrupt_keys(self):
#         try:
#             with pd.HDFStore(self.fname, mode='r') as store:
#                 keys = store.keys()
#                 corrupt_keys = []
#                 for key in keys:
#                     try:
#                         _ = store.get(key)
#                     except (tables.exceptions.HDF5ExtError, AttributeError) as e:
#                         log.error(f"读取失败 {key}: {e}")
#                         corrupt_keys.append(key)
#                 if corrupt_keys:
#                     log.warning(f"损坏 keys: {corrupt_keys}, 将被清除")
#                     store.close()
#                     with pd.HDFStore(self.fname, mode='a') as wstore:
#                         for key in corrupt_keys:
#                             try:
#                                 wstore.remove(key)
#                                 log.info(f"已删除损坏 key: {key}")
#                             except Exception as e:
#                                 log.error(f"删除 key {key} 失败: {e}")
#         except Exception as e:
#             log.error(f"HDF5 文件 {self.fname} 损坏，重新创建空文件: {e}")
#             with pd.HDFStore(self.fname, mode='w') as store:
#                 pass

#     # ===== 锁机制 =====
#     def _acquire_lock(self):
#         while True:
#             try:
#                 self._flock = os.open(self._lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
#                 log.info(f"SafeHDF: acquired lock {self._lock}")
#                 break
#             except FileExistsError:
#                 self.countlock += 1
#                 if self.countlock <= 8:
#                     wait = round(random.randint(3, 10) / 1.2, 2)
#                     log.warning(f"Lock exists, retry {self.countlock}, sleep {wait}s")
#                     time.sleep(wait)
#                 else:
#                     log.error(f"Stale lock {self._lock}, removing...")
#                     try:
#                         os.remove(self._lock)
#                     except Exception as e:
#                         log.error(f"Failed to remove stale lock: {e}")

#     def _wait_for_lock(self):
#         wait_count = 0
#         while os.path.exists(self._lock):
#             wait_count += 1
#             log.warning(f"锁文件存在，读操作等待中... 已等待 {wait_count} 秒")
#             time.sleep(1)
#         log.info("锁已释放，读操作继续。")

#     def _release_lock(self):
#         if self._flock:
#             try:
#                 os.close(self._flock)
#             except Exception as e:
#                 log.error(f"Error closing lock fd: {e}")
#             self._flock = None
#         if os.path.exists(self._lock):
#             try:
#                 os.remove(self._lock)
#                 log.info(f"Released lock {self._lock}")
#             except Exception as e:
#                 log.error(f"Failed to remove lock file: {e}")

#     # ===== 上下文管理 =====
#     def __enter__(self):
#         return self if self.write_status else None

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if self.write_status:
#             try:
#                 super().__exit__(exc_type, exc_val, exc_tb)
#                 # ===== 压缩逻辑 =====
#                 h5_size = os.path.getsize(self.fname) / 1e6
#                 new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit)
#                 log.info(f"fname: {self.fname} h5_size: {h5_size} big_limit: {self.big_H5_Size_limit}")
#                 if cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
#                     if os.path.exists(self.fname) and os.path.exists(self.temp_file):
#                         log.error(f"Remove tmp file exists: {self.temp_file}")
#                         os.remove(self.temp_file)
#                     os.rename(self.fname, self.temp_file)
#                     if cct.get_os_system() == 'mac':
#                         p = subprocess.Popen(
#                             self.ptrepack_cmds % (self.complib, self.temp_file, self.fname),
#                             shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
#                         )
#                     else:
#                         back_path = os.getcwd()
#                         os.chdir(self.basedir)
#                         pt_cmd = self.ptrepack_cmds % (
#                             self.complib,
#                             self.temp_file.split(self.basedir)[1],
#                             self.fname.split(self.basedir)[1]
#                         )
#                         p = subprocess.Popen(pt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#                     p.wait()
#                     if p.returncode != 0:
#                         log.error(f"ptrepack error {p.communicate()}, src {self.temp_file}, dest {self.fname}")
#                     else:
#                         if os.path.exists(self.temp_file):
#                             os.remove(self.temp_file)
#                     if cct.get_os_system() != 'mac':
#                         os.chdir(back_path)
#             finally:
#                 self._release_lock()



#没有读取错误检测
# class SafeHDFStore_2_ok(HDFStore):
#     def __init__(self, fname, mode='a', **kwargs):
#         self.fname_o = fname
#         self.mode = mode
#         self.probe_interval = kwargs.pop("probe_interval", 2)

#         # ===== 原有路径处理逻辑 =====
#         self.multiIndexsize = False
#         if self.fname_o == cct.tdx_hd5_name or self.fname_o.find('tdx_all_df') >= 0:
#             self.multiIndexsize = True
#             self.fname = cct.get_run_path_tdx(self.fname_o)
#             self.basedir = self.fname.split(self.fname_o)[0]
#             log.info(f"tdx_hd5: {self.fname}")
#         else:
#             self.fname = cct.get_ramdisk_path(self.fname_o)
#             self.basedir = self.fname.split(self.fname_o)[0]
#             log.info(f"ramdisk_hd5: {self.fname}")

#         self.config_ini = os.path.join(BaseDir, 'h5config.txt')
#         self._lock = self.fname + ".lock"
#         self._flock = None
#         self.countlock = 0
#         self.write_status = False
#         self.complevel = 9
#         self.complib = 'zlib'
#         self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"
#         self.h5_size_org = os.path.getsize(self.fname) / 1e6 if os.path.exists(self.fname) else 0
#         self.big_H5_Size_limit = ct.big_H5_Size_limit * 6 if self.multiIndexsize else ct.big_H5_Size_limit
#         self.temp_file = self.fname + '_tmp'

#         global RAMDISK_KEY
#         if not os.path.exists(BaseDir):
#             if RAMDISK_KEY < 1:
#                 log.error(f"NO RamDisk Root: {BaseDir}")
#                 RAMDISK_KEY += 1
#         else:
#             self.write_status = True

#         # ===== 文件不存在时先创建空文件 =====
#         if not os.path.exists(self.fname):
#             log.warning(f"HDF5 file {self.fname} not found. Creating empty file.")
#             with pd.HDFStore(self.fname, mode='w') as store:
#                 pass

#         # ===== 写模式加锁，读模式等待锁释放 =====
#         if mode != 'r' and self.write_status:
#             self._acquire_lock()
#         elif mode == 'r':
#             self._wait_for_lock()

#         # ===== 调用 HDFStore 初始化 =====
#         super().__init__(self.fname, mode=mode, **kwargs)

#     def _acquire_lock(self):
#         """写模式尝试获取文件锁，如果失败会重试，超过次数后强制删除残留锁"""
#         while True:
#             try:
#                 self._flock = os.open(self._lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
#                 log.info(f"SafeHDF: acquired lock {self._lock}")
#                 break
#             except FileExistsError:
#                 self.countlock += 1
#                 if self.countlock <= 8:
#                     wait = round(random.randint(3, 10) / 1.2, 2)
#                     log.warning(f"Lock exists, retry {self.countlock}, sleep {wait}s")
#                     time.sleep(wait)
#                 else:
#                     log.error(f"Stale lock {self._lock}, removing...")
#                     try:
#                         os.remove(self._lock)
#                     except Exception as e:
#                         log.error(f"Failed to remove stale lock: {e}")

#     def _wait_for_lock(self):
#         """读模式等待锁释放"""
#         wait_count = 0
#         while os.path.exists(self._lock):
#             wait_count += 1
#             log.warning(f"锁文件存在，读操作等待中... 已等待 {wait_count} 秒")
#             time.sleep(1)  # 每秒检查一次，增加延时避免刷屏太快
#         log.info("锁已释放，读操作继续。")

#     def _release_lock(self):
#         """释放锁文件"""
#         if self._flock:
#             try:
#                 os.close(self._flock)
#             except Exception as e:
#                 log.error(f"Error closing lock fd: {e}")
#             self._flock = None
#         if os.path.exists(self._lock):
#             try:
#                 os.remove(self._lock)
#                 log.info(f"Released lock {self._lock}")
#             except Exception as e:
#                 log.error(f"Failed to remove lock file: {e}")

#     def __enter__(self):
#         return self if self.write_status else None

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if self.write_status:
#             try:
#                 # 调用 HDFStore 的 exit
#                 super().__exit__(exc_type, exc_val, exc_tb)

#                 # ===== 压缩逻辑（ptrepack） =====
#                 h5_size = os.path.getsize(self.fname) / 1e6
#                 new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit)
#                 log.info(f"fname: {self.fname} h5_size: {h5_size} big_limit: {self.big_H5_Size_limit}")

#                 if cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
#                     if os.path.exists(self.fname) and os.path.exists(self.temp_file):
#                         log.error(f"Remove tmp file exists: {self.temp_file}")
#                         os.remove(self.temp_file)
#                     os.rename(self.fname, self.temp_file)
#                     if cct.get_os_system() == 'mac':
#                         p = subprocess.Popen(
#                             self.ptrepack_cmds % (self.complib, self.temp_file, self.fname),
#                             shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
#                         )
#                     else:
#                         back_path = os.getcwd()
#                         os.chdir(self.basedir)
#                         pt_cmd = self.ptrepack_cmds % (
#                             self.complib,
#                             self.temp_file.split(self.basedir)[1],
#                             self.fname.split(self.basedir)[1]
#                         )
#                         p = subprocess.Popen(pt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#                     p.wait()
#                     if p.returncode != 0:
#                         log.error(f"ptrepack error {p.communicate()}, src {self.temp_file}, dest {self.fname}")
#                     else:
#                         if os.path.exists(self.temp_file):
#                             os.remove(self.temp_file)
#                     if cct.get_os_system() != 'mac':
#                         os.chdir(back_path)

#             finally:
#                 # 释放锁
#                 self._release_lock()



# class SafeHDFStore_1(HDFStore):
#     def __init__(self, fname, mode='a', **kwargs):
#         self.fname_o = fname
#         self.mode = mode
#         self.probe_interval = kwargs.pop("probe_interval", 2)

#         # ===== 原有路径处理逻辑 =====
#         self.multiIndexsize = False
#         if self.fname_o == cct.tdx_hd5_name or self.fname_o.find('tdx_all_df') >= 0:
#             self.multiIndexsize = True
#             self.fname = cct.get_run_path_tdx(self.fname_o)
#             self.basedir = self.fname.split(self.fname_o)[0]
#             log.info(f"tdx_hd5: {self.fname}")
#         else:
#             self.fname = cct.get_ramdisk_path(self.fname_o)
#             self.basedir = self.fname.split(self.fname_o)[0]
#             log.info(f"ramdisk_hd5: {self.fname}")

#         self.config_ini = os.path.join(BaseDir, 'h5config.txt')
#         self._lock = self.fname + ".lock"
#         self._flock = None
#         self.countlock = 0
#         self.write_status = False
#         self.complevel = 9
#         self.complib = 'zlib'
#         self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"
#         self.h5_size_org = os.path.getsize(self.fname) / 1e6 if os.path.exists(self.fname) else 0
#         self.big_H5_Size_limit = ct.big_H5_Size_limit * 6 if self.multiIndexsize else ct.big_H5_Size_limit
#         self.temp_file = self.fname + '_tmp'

#         global RAMDISK_KEY
#         if not os.path.exists(BaseDir):
#             if RAMDISK_KEY < 1:
#                 log.error(f"NO RamDisk Root: {BaseDir}")
#                 RAMDISK_KEY += 1
#         else:
#             self.write_status = True

#         # ===== 文件不存在时先创建空文件 =====
#         if not os.path.exists(self.fname):
#             log.warning(f"HDF5 file {self.fname} not found. Creating empty file.")
#             with pd.HDFStore(self.fname, mode='w') as store:
#                 pass

#         # ===== 只写模式才尝试加锁 =====
#         if mode != 'r' and self.write_status:
#             self._acquire_lock()

#         # ===== 调用 HDFStore 初始化 =====
#         super().__init__(self.fname, mode=mode, **kwargs)

#     def _acquire_lock(self):
#         """尝试获取文件锁，如果失败会重试，超过次数后强制删除残留锁"""
#         while True:
#             try:
#                 self._flock = os.open(self._lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
#                 log.info(f"SafeHDF: acquired lock {self._lock}")
#                 break
#             except FileExistsError:
#                 self.countlock += 1
#                 if self.countlock <= 8:
#                     wait = round(random.randint(3, 10) / 1.2, 2)
#                     log.warning(f"Lock exists, retry {self.countlock}, sleep {wait}s")
#                     time.sleep(wait)
#                 else:
#                     log.error(f"Stale lock {self._lock}, removing...")
#                     try:
#                         os.remove(self._lock)
#                     except Exception as e:
#                         log.error(f"Failed to remove stale lock: {e}")

#     def _release_lock(self):
#         """释放锁文件"""
#         if self._flock:
#             try:
#                 os.close(self._flock)
#             except Exception as e:
#                 log.error(f"Error closing lock fd: {e}")
#             self._flock = None
#         if os.path.exists(self._lock):
#             try:
#                 os.remove(self._lock)
#                 log.info(f"Released lock {self._lock}")
#             except Exception as e:
#                 log.error(f"Failed to remove lock file: {e}")

#     def __enter__(self):
#         if self.write_status:
#             return self

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if self.write_status:
#             try:
#                 # 调用 HDFStore 的 exit
#                 super().__exit__(exc_type, exc_val, exc_tb)

#                 # ===== 压缩逻辑（ptrepack） =====
#                 h5_size = os.path.getsize(self.fname) / 1e6
#                 new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit)
#                 log.info(f"fname: {self.fname} h5_size: {h5_size} big_limit: {self.big_H5_Size_limit}")

#                 if cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
#                     if os.path.exists(self.fname) and os.path.exists(self.temp_file):
#                         log.error(f"Remove tmp file exists: {self.temp_file}")
#                         os.remove(self.temp_file)
#                     os.rename(self.fname, self.temp_file)
#                     if cct.get_os_system() == 'mac':
#                         p = subprocess.Popen(
#                             self.ptrepack_cmds % (self.complib, self.temp_file, self.fname),
#                             shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
#                         )
#                     else:
#                         back_path = os.getcwd()
#                         os.chdir(self.basedir)
#                         pt_cmd = self.ptrepack_cmds % (
#                             self.complib,
#                             self.temp_file.split(self.basedir)[1],
#                             self.fname.split(self.basedir)[1]
#                         )
#                         p = subprocess.Popen(pt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#                     p.wait()
#                     if p.returncode != 0:
#                         log.error(f"ptrepack error {p.communicate()}, src {self.temp_file}, dest {self.fname}")
#                     else:
#                         if os.path.exists(self.temp_file):
#                             os.remove(self.temp_file)
#                     if cct.get_os_system() != 'mac':
#                         os.chdir(back_path)

#             finally:
#                 # 释放锁
#                 self._release_lock()




# class SafeHDFStore_me(HDFStore):
#     # def __init__(self, *args, **kwargs):

#     def __init__(self, *args, **kwargs):
#         self.probe_interval = kwargs.pop("probe_interval", 2)
#         lock = cct.get_ramdisk_path(args[0], lock=True)
#         baseDir = BaseDir
#         self.fname_o = args[0]
#         self.basedir = baseDir
#         self.config_ini = baseDir + os.path.sep+ 'h5config.txt'
#         self.multiIndexsize = False
#         if args[0] == cct.tdx_hd5_name or args[0].find('tdx_all_df') >=0:
#             self.multiIndexsize = True
#             self.fname = cct.get_run_path_tdx(args[0])
#             self.basedir = self.fname.split(self.fname_o)[0]
#             log.info("tdx_hd5:%s"%(self.fname))
#         else:
#             self.fname = cct.get_ramdisk_path(args[0])
#             self.basedir = self.fname.split(self.fname_o)[0]
#             log.info("ramdisk_hd5:%s"%(self.fname))

#         self._lock = lock
#         self.countlock = 0
#         self.write_status = False
#         self.complevel = 9
#         self.complib = 'zlib'
#         self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"
#         if self.multiIndexsize:
#             self.big_H5_Size_limit = ct.big_H5_Size_limit * 6
#         else:
#             self.big_H5_Size_limit = ct.big_H5_Size_limit
#         self.h5_size_org = 0
#         global RAMDISK_KEY
#         if not os.path.exists(baseDir):
#             if RAMDISK_KEY < 1:
#                 log.error("NO RamDisk Root:%s" % (baseDir))
#                 RAMDISK_KEY += 1
#         else:
#             self.temp_file = self.fname + '_tmp'
#             self.write_status = True
#             if os.path.exists(self.fname):
#                 self.h5_size_org = os.path.getsize(self.fname) / 1000 / 1000
#             self.run(self.fname)

#     def run(self, fname, *args, **kwargs):
#         while True:
#             try:
#                 self._flock = os.open(
#                     self._lock, os.O_CREAT | os.O_EXCL)
#                     # self._lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
#                 log.info("SafeHDF:%s lock:%s" % (self._lock, self._flock))
#                 break
#             except (IOError, EOFError, Exception) as e:
#                 if self.countlock > 1:
#                     log.debug("IOError Error:%s" % (e))

#                 if self.countlock <= 8:
#                     time.sleep(round(random.randint(3, 10) / 1.2, 2))
#                     self.countlock += 1
#                 else:
#                     os.remove(self._lock)
#                     log.error("count10 remove lock")
#             except WindowsError:
#                 log.error('WindowsError')
#             finally:
#                 pass

#         HDFStore.__init__(self, fname, *args, **kwargs)

#     def __enter__(self):
#         if self.write_status:
#             return self

#     def __exit__(self, *args, **kwargs):
#         if self.write_status:
#             HDFStore.__exit__(self, *args, **kwargs)
#             os.close(self._flock)
#             h5_size = os.path.getsize(self.fname) / 1000 / 1000
#             new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit)
#             log.info("fname:%s h5_size:%s big:%s conf: %s " % (self.fname,h5_size, self.big_H5_Size_limit, cct.get_config_value(self.config_ini,self.fname_o)))
#             if cct.get_config_value(self.config_ini,self.fname_o,h5_size,new_limit):
#                 time_pt=time.time()
#                 if os.path.exists(self.fname) and os.path.exists(self.temp_file):
#                     log.error("remove tmpfile is exists:%s"%(self.temp_file))
#                     os.remove(self.temp_file)
#                 os.rename(self.fname, self.temp_file)
#                 if cct.get_os_system() == 'mac':
#                     p=subprocess.Popen(self.ptrepack_cmds % (
#                         self.complib, self.temp_file, self.fname), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#                 else:
#                     back_path = os.getcwd()
#                     os.chdir(self.basedir)
#                     log.info('current path is: %s after change dir' %os.getcwd())
#                     pt_cmd = self.ptrepack_cmds % (self.complib, self.temp_file.split(self.basedir)[1], self.fname.split(self.basedir)[1])
#                     p=subprocess.Popen(pt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#                 p.wait()
#                 if p.returncode != 0:
#                     log.error("ptrepack hdf Error:%s src%s  tofile:%s Er:%s" % (p.communicate(),self.temp_file,self.fname,p.stdout.read().decode("gbk")))
#                 else:
#                     if os.path.exists(self.temp_file):
#                         os.remove(self.temp_file)
#                 os.chdir(back_path)

#             if os.path.exists(self._lock):
#                 os.remove(self._lock)

'''
https://stackoverflow.com/questions/21126295/how-do-you-create-a-compressed-dataset-in-pytables-that-can-store-a-unicode-stri/21128497#21128497
>>> h5file = pt.openFile("test1.h5",'w')
>>> recordStringInHDF5(h5file, h5file.root, 'mrtamb',
    u'\\u266b Hey Mr. Tambourine Man \\u266b')

/mrtamb (CArray(30,), shuffle, zlib(5)) ''
  atom := UInt8Atom(shape=(), dflt=0)
  maindim := 0
  flavor := 'numpy'
  byteorder := 'irrelevant'
  chunkshape := (65536,)

>>> h5file.flush()
>>> h5file.close()
>>> h5file = pt.openFile("test1.h5")
>>> print retrieveStringFromHDF5(h5file.root.mrtamb)

♫ Hey Mr. Tambourine Man ♫

write-performance
https://stackoverflow.com/questions/20083098/improve-pandas-pytables-hdf5-table-write-performance

'''


def recordStringInHDF5(h5file, group, nodename, s, complevel=5, complib='blosc'):
    '''creates a CArray object in an HDF5 file
    that represents a unicode string'''

    bytes=np.fromstring(s.encode('utf-8'), np.uint8)
    atom=pt.UInt8Atom()
    filters=pt.Filters(complevel=complevel, complib=complib)
    ca=h5file.create_carray(group, nodename, atom, shape=(len(bytes),),
                              filters=filters)
    ca[:]=bytes
    return ca


def retrieveStringFromHDF5(node):
    return str(node.read().tostring(), 'utf-8')


def clean_cols_for_hdf(data):
    types=data.apply(lambda x: pd.lib.infer_dtype(x.values))
    for col in types[types == 'mixed'].index:
        data[col]=data[col].astype(str)
    # data[<your appropriate columns here>].fillna(0,inplace=True)
    return data


def write_hdf(f, key, df, complib):
    """Append pandas dataframe to hdf5.

    Args:
    f       -- File path
    key     -- Store key
    df      -- Pandas dataframe
    complib -- Compress lib

    NOTE: We use maximum compression w/ zlib.
    """

    with SafeHDF5Store(f, complevel=9, complib=complib) as store:
        df.to_hdf(store, key, format='table', append=True)
# with SafeHDFStore('example.hdf') as store:
#     # Only put inside this block the code which operates on the store
#     store['result'] = result

# def write_lock(fname):
#     fpath = cct.get_ramdisk_path(fname,lock=True)


def get_hdf5_file(fpath, wr_mode='r', complevel=9, complib='blosc', mutiindx=False):
    """[summary]

    [old api out date]

    Parameters
    ----------
    fpath : {[type]}
        [description]
    wr_mode : {str}, optional
        [description] (the default is 'r', which [default_description])
    complevel : {number}, optional
        [description] (the default is 9, which [default_description])
    complib : {str}, optional
        [description] (the default is 'blosc', which [default_description])
    mutiindx : {bool}, optional
        [description] (the default is False, which [default_description])

    Returns
    -------
    [type]
        [description]
    """
    # store=pd.HDFStore(fpath,wr_mode, complevel=complevel, complib=complib)
    fpath=cct.get_ramdisk_path(fpath)
    if fpath is None:
        log.info("don't exists %s" % (fpath))
        return None

    if os.path.exists(fpath):
        if wr_mode == 'w':
            # store=pd.HDFStore(fpath,complevel=None, complib=None, fletcher32=False)
            store=pd.HDFStore(fpath)
        else:
            lock=cct.get_ramdisk_path(fpath, lock=True)
            while True:
                try:
                    #                    lock_s = os.open(lock, os.O_CREAT |os.O_EXCL |os.O_WRONLY)
                    lock_s=os.open(lock, os.O_CREAT | os.O_EXCL)
                    log.info("SafeHDF:%s read lock:%s" % (lock_s, lock))
                    break
                # except FileExistsError:
    #            except FileExistsError as e:
                except (IOError, EOFError, Exception) as e:
                    # time.sleep(probe_interval)
                    log.error("IOError READ ERROR:%s" % (e))
                    time.sleep(random.random())

            store=pd.HDFStore(fpath, mode=wr_mode)
            # store=pd.HDFStore(fpath, mode=wr_mode, complevel=None, complib=None, fletcher32=False)
            os.remove(lock)
#            store = SafeHDFStore(fpath)
    else:
        if mutiindx:
            store=pd.HDFStore(fpath)
            # store = pd.HDFStore(fpath,complevel=9,complib='zlib')
        else:
            return None
        # store = pd.HDFStore(fpath, mode=wr_mode,complevel=9,complib='zlib')
    # store.put("Year2015", dfMinutes, format="table", append=True, data_columns=['dt','code'])
    return store
    # fp='/Volumes/RamDisk/top_now.h5'
    # get_hdf5_file(fp)
    # def hdf5_read_file(file):
    # store.select("Year2015", where=['dt<Timestamp("2015-01-07")','code=="000570"'])
    # return store

def write_hdf_db_gpt_error(fname, df, table='all', index=False, complib='blosc',
                 baseCount=500, append=True, MultiIndex=False,
                 rewrite=False, showtable=False):
    """安全写入 HDF5 文件（单次打开），保留所有原有逻辑"""
    # df.index = df.index.astype(str)
    # TypeError: Setting a MultiIndex dtype to anything other than object is not supported
    # df.index 其实是 MultiIndex，但是你的 write_hdf_db 里强行 `
    if 'code' in df.columns:
        df = df.set_index('code')

    time_t = time.time()
    df = df.fillna(0)
    df = df[~df.index.duplicated(keep='first')]

    global RAMDISK_KEY
    if not RAMDISK_KEY < 1:
        return df

    if not MultiIndex:
        df['timel'] = time.time()

    # fname = f'G:\\{fname}.h5'
    # if not os.path.exists(f'G:\\{fname}.h5'):
    #     with pd.HDFStore(fname, mode='w') as store:
    #         pass
    # 打开 HDF5 文件一次完成所有操作
    with SafeHDFStore(fname, mode='a') as store:
        tmpdf = None
        keys = store.keys()
        log.debug(f"fname: {fname} keys:{keys}")
        if showtable:
            print(f"fname: {fname} keys:{keys}")

        # 读取已有表数据
        if '/' + table in keys:
            tmpdf = store[table].copy()
            tmpdf = tmpdf[~tmpdf.index.duplicated(keep='first')]

        # MultiIndex 特殊逻辑
        if MultiIndex and tmpdf is not None and len(tmpdf) > 0 and not rewrite:
            multi_code = tmpdf.index.get_level_values('code').unique().tolist()
            df_multi_code = df.index.get_level_values('code').unique().tolist()
            dratio = cct.get_diff_dratio(multi_code, df_multi_code)
            if dratio < ct.dratio_limit:
                comm_code = list(set(df_multi_code) & set(multi_code))
                inx_key = comm_code[random.randint(0, len(comm_code) - 1)]
                if inx_key in df.index.get_level_values('code'):
                    now_time = df.loc[inx_key].index[-1]
                    tmp_time = tmpdf.loc[inx_key].index[-1]
                    if now_time == tmp_time:
                        log.debug("%s %s Multi out %s hdf5:%s No Wri!!!" %
                                  (fname, table, inx_key, now_time))
                        return False

        # 合并已有数据
        if tmpdf is not None and len(tmpdf) > 0 and not MultiIndex:
            limit_t = time.time()
            df['timel'] = limit_t
            df = cct.combine_dataFrame(tmpdf, df, col=None, append=append)
            if not append:
                df['timel'] = time.time()
            elif fname == 'powerCompute':
                o_time = df[df.timel < limit_t].timel.tolist()
                o_time = sorted(set(o_time))
                if len(o_time) >= ct.h5_time_l_count:
                    o_time = [time.time() - t_x for t_x in o_time]
                    o_timel = len(o_time)
                    o_time = np.mean(o_time)
                    if o_time > ct.h5_power_limit_time:
                        df['timel'] = time.time()
                        log.error("%s %s o_time:%.1f timel:%s" %
                                  (fname, table, o_time, o_timel))

        # 对 object 类型列进行处理
        dd = df.dtypes.to_frame()
        if 'object' in dd.values:
            dd = dd[dd == 'object'].dropna()
            col = dd.index.tolist()
            log.info("col:%s" % col)
            df[col] = df[col].astype(str)

        df.index = df.index.astype(str)
        df = df.fillna(0)
        df = cct.reduce_memory_usage(df, verbose=False)
        log.info(f'df.shape: {df.shape}')

        # 写回 HDF5
        if '/' + table in store.keys():
            if not MultiIndex:
                store.remove(table)
                store.put(table, df, format='table', append=False,
                          complib=complib, data_columns=True)
            else:
                if rewrite or len(store[table]) < 1:
                    store.remove(table)
                store.put(table, df, format='table', index=False,
                          complib=complib, data_columns=True, append=True)
        else:
            store.put(table, df, format='table',
                      index=MultiIndex is False,
                      complib=complib,
                      data_columns=True,
                      append=MultiIndex)

        store.flush()

    log.info("write hdf time:%0.2f" % (time.time() - time_t))
    return True


def write_hdf_db_gptmod1(fname, df, table='all', index=False, complib='blosc',
                 baseCount=500, append=True, MultiIndex=False,
                 rewrite=False, showtable=False):
    """安全写入 HDF5 文件，保留原功能"""

    if 'code' in df.columns:
        df = df.set_index('code')
    time_t = time.time()
    df = df.fillna(0)
    df = df[~df.index.duplicated(keep='first')]
    global RAMDISK_KEY
    if not RAMDISK_KEY < 1:
        return df

    if not MultiIndex:
        df['timel'] = time.time()

    # 打开一次 HDF5 文件，读 + 写都在这里完成
    with SafeHDFStore(fname, mode='a') as store:
        tmpdf = None
        # 检查表是否存在
        if store is not None:
            keys = store.keys()
            log.debug(f"fname: {fname} keys:{keys}")
            if showtable:
                print(f"fname: {fname} keys:{keys}")
            if '/' + table in keys:
                tmpdf = store[table].copy()
                tmpdf = tmpdf[~tmpdf.index.duplicated(keep='first')]

        # MultiIndex 逻辑
        if MultiIndex and tmpdf is not None and len(tmpdf) > 0 and not rewrite:
            multi_code = tmpdf.index.get_level_values('code').unique().tolist()
            df_multi_code = df.index.get_level_values('code').unique().tolist()
            dratio = cct.get_diff_dratio(multi_code, df_multi_code)
            if dratio < ct.dratio_limit:
                comm_code = list(set(df_multi_code) & set(multi_code))
                inx_key = comm_code[random.randint(0, len(comm_code) - 1)]
                if inx_key in df.index.get_level_values('code'):
                    now_time = df.loc[inx_key].index[-1]
                    tmp_time = tmpdf.loc[inx_key].index[-1]
                    if now_time == tmp_time:
                        log.debug("%s %s Multi out %s hdf5:%s No Wri!!!" % (fname, table, inx_key, now_time))
                        return False

        # 普通逻辑
        if tmpdf is not None and len(tmpdf) > 0 and not MultiIndex:
            limit_t = time.time()
            df['timel'] = limit_t
            df = cct.combine_dataFrame(tmpdf, df, col=None, append=append)
            if not append:
                df['timel'] = time.time()
            elif fname == 'powerCompute':
                o_time = df[df.timel < limit_t].timel.tolist()
                o_time = sorted(set(o_time))
                if len(o_time) >= ct.h5_time_l_count:
                    o_time = [time.time() - t_x for t_x in o_time]
                    o_timel = len(o_time)
                    o_time = np.mean(o_time)
                    if o_time > ct.h5_power_limit_time:
                        df['timel'] = time.time()
                        log.error("%s %s o_time:%.1f timel:%s" % (fname, table, o_time, o_timel))

        # 类型转换
        dd = df.dtypes.to_frame()
        if 'object' in dd.values:
            dd = dd[dd == 'object'].dropna()
            col = dd.index.tolist()
            log.info("col:%s" % col)
            df[col] = df[col].astype(str)
        df.index = df.index.astype(str)
        df = df.fillna(0)
        df = cct.reduce_memory_usage(df, verbose=False)
        log.info(f'df.shape: {df.shape}')

        # 写回 HDF5
        if '/' + table in store.keys():
            if not MultiIndex:
                store.remove(table)
                store.put(table, df, format='table', append=False, complib=complib, data_columns=True)
            else:
                if rewrite or len(store[table]) < 1:
                    store.remove(table)
                store.put(table, df, format='table', index=False, complib=complib, data_columns=True, append=True)
        else:
            store.put(table, df, format='table',
                      index=MultiIndex is False, complib=complib, data_columns=True,
                      append=MultiIndex)

        store.flush()

    log.info("write hdf time:%0.2f" % (time.time() - time_t))
    return True


def write_hdf_db(fname, df, table='all', index=False, complib='blosc', baseCount=500, append=True, MultiIndex=False,rewrite=False,showtable=False):
    """[summary]

    [description]

    Parameters
    ----------
    fname : {[type]}
        [description]
    df : {[type]}
        [description]
    table : {str}, optional
        [description] (the default is 'all', which [default_description])
    index : {bool}, optional
        [description] (the default is False, which [default_description])
    complib : {str}, optional
        [description] (the default is 'blosc', which [default_description])
    baseCount : {number}, optional
        [description] (the default is 500, which [default_description])
    append : {bool}, optional
        [description] (the default is True, which [default_description])
    MultiIndex : {bool}, optional
        [description] (the default is False, which [default_description])

    Returns
    -------
    [type]
        [description]
    """
    if 'code' in df.columns:
        df=df.set_index('code')
#    write_status = False
    time_t=time.time()
#    if not os.path.exists(cct.get_ramdisk_dir()):
#        log.info("NO RamDisk")
#        return False
    df=df.fillna(0)
    df=df[~df.index.duplicated(keep='first')]
    code_subdf=df.index.tolist()
    global RAMDISK_KEY
    if not RAMDISK_KEY < 1:
        return df

    if not MultiIndex:
        df['timel']=time.time()
        
    if not rewrite:
        if df is not None and not df.empty and table is not None:
            tmpdf=[]

            with SafeHDFStore(fname,mode='a') as store:
                if store is not None:
                    log.debug(f"fname: {(fname)} keys:{store.keys()}")
                    if showtable:
                        print(f"fname: {(fname)} keys:{store.keys()}")
                    if '/' + table in list(store.keys()):
                        tmpdf=store[table]
                        tmpdf = tmpdf[~tmpdf.index.duplicated(keep='first')]

            if not MultiIndex:
                if index:
                    # log.error("debug index:%s %s %s"%(df,index,len(df)))
                    df.index=list(map((lambda x: str(1000000 - int(x))
                                    if x.startswith('0') else x), df.index))
                if tmpdf is not None and len(tmpdf) > 0:
                    if 'code' in tmpdf.columns:
                        tmpdf=tmpdf.set_index('code')
                    if 'code' in df.columns:
                        df=df.set_index('code')
                    diff_columns=set(df.columns) - set(tmpdf.columns)
                    if len(diff_columns) != 0:
                        log.error("columns diff:%s" % (diff_columns))

                    limit_t=time.time()
                    df['timel']=limit_t
                    # df_code = df.index.tolist()

                    df=cct.combine_dataFrame(tmpdf, df, col=None, append=append)

                    if not append:
                        df['timel']=time.time()
                    elif fname == 'powerCompute':
                        o_time=df[df.timel < limit_t].timel.tolist()
                        o_time=sorted(set(o_time), reverse=False)
                        if len(o_time) >= ct.h5_time_l_count:
                            o_time=[time.time() - t_x for t_x in o_time]
                            o_timel=len(o_time)
                            o_time=np.mean(o_time)
                            if (o_time) > ct.h5_power_limit_time:
                                df['timel']=time.time()
                                log.error("%s %s o_time:%.1f timel:%s" % (fname, table, o_time, o_timel))

        #            df=cct.combine_dataFrame(tmpdf, df, col=None,append=False)
                    log.info("read hdf time:%0.2f" % (time.time() - time_t))
                else:
                    # if index:
                        # df.index = map((lambda x:str(1000000-int(x)) if x.startswith('0') else x),df.index)
                    log.info("h5 None hdf reindex time:%0.2f" %
                             (time.time() - time_t))
            else:
                if not rewrite and tmpdf is not None and len(tmpdf) > 0:
                    multi_code=tmpdf.index.get_level_values('code').unique().tolist()
                    df_multi_code = df.index.get_level_values('code').unique().tolist()
                    dratio = cct.get_diff_dratio(multi_code, df_multi_code)
                    if dratio < ct.dratio_limit:
                        comm_code = list(set(df_multi_code) & set(multi_code))
                        # print df_multi_code,multi_code,comm_code,len(comm_code)
                        inx_key=comm_code[random.randint(0, len(comm_code)-1)]
                        if  inx_key in df.index.get_level_values('code'):
                            now_time=df.loc[inx_key].index[-1]
                            tmp_time=tmpdf.loc[inx_key].index[-1]
                            if now_time == tmp_time:
                                log.debug("%s %s Multi out %s hdf5:%s No Wri!!!" % (fname, table,inx_key
                                    , now_time))
                                return False
                    elif dratio == 1:
                        print(("newData ratio:%s all:%s"%(dratio,len(df))))
                    else:
                        log.debug("dratio:%s main:%s new:%s %s %s Multi All Wri" % (dratio,len(multi_code),len(df_multi_code),fname, table))
                else:
                    log.debug("%s %s Multi rewrite:%s Wri!!!" % (fname, table, rewrite))


    time_t=time.time()
    if df is not None and not df.empty and table is not None:
        if df is not None and not df.empty and len(df) > 0:
            dd=df.dtypes.to_frame()

        if 'object' in dd.values:
            dd=dd[dd == 'object'].dropna()
            col=dd.index.tolist()
            log.info("col:%s" % (col))
            if not MultiIndex:
                df[col]=df[col].astype(str)
                df.index=df.index.astype(str)
                df=df.fillna(0)

        with SafeHDFStore(fname,mode='a') as h5:
            df=df.fillna(0)
            df=cct.reduce_memory_usage(df,verbose=False)
            log.info(f'df.shape:{df.shape}')
            if h5 is not None:
                if '/' + table in list(h5.keys()):
                    if not MultiIndex:

                        h5.remove(table)
                        h5.put(table, df, format='table', append=False, complib=complib, data_columns=True)
                        # h5.put(table, df, format='table',index=False, data_columns=True, append=False)
                    else:
                        if rewrite:
                            h5.remove(table)
                        elif len(h5[table]) < 1:
                            h5.remove(table)
                        h5.put(table, df, format='table', index=False, complib=complib, data_columns=True, append=True)
                        # h5.append(table, df, format='table', append=True,data_columns=True, dropna=None)
                else:
                    if not MultiIndex:
                        # h5[table]=df
                        h5.put(table, df, format='table', append=False, complib=complib, data_columns=True)
                        # h5.put(table, df, format='table',index=False, data_columns=True, append=False)
                    else:
                        h5.put(table, df, format='table', index=False, complib=complib, data_columns=True, append=True)
                        # h5.append(table, df, format='table', append=True, data_columns=True, dropna=None)
                        # h5[table]=df
                h5.flush()
            else:
                log.error("HDFile is None,Pls check:%s" % (fname))

    log.info("write hdf time:%0.2f" % (time.time() - time_t))

    return True

# def lo_hdf_db_old(fname,table='all',code_l=None,timelimit=True,index=False):
#    h_t = time.time()
#    h5=top_hdf_api(fname=fname, table=table, df=None,index=index)
#    if h5 is not None and code_l is not None:
#        if len(code_l) == 0:
#            return None
#        if h5 is not None:
#            diffcode = set(code_l) - set(h5.index)
#            if len(diffcode) > 10 and len(h5) <> 0 and float(len(diffcode))/float(len(code_l)) > ct.diffcode:
#                log.error("f:%s t:%s dfc:%s %s co:%s h5:%s"%(fname,table,len(diffcode),h5.index.values[0],code_l[:2],h5.index.values[:2]))
#                return None
#
#    if h5 is not None and not h5.empty and 'timel' in h5.columns:
#            o_time = h5[h5.timel <> 0].timel
#            if len(o_time) > 0:
#                o_time = o_time[0]
#    #            print time.time() - o_time
#                # if cct.get_work_hdf_status() and (not (915 < cct.get_now_time_int() < 930) and time.time() - o_time < ct.h5_limit_time):
#                if not cct.get_work_time() or (not timelimit or time.time() - o_time < ct.h5_limit_time):
#                    log.info("time hdf:%s %s"%(fname,len(h5))),
# if 'timel' in h5.columns:
# h5=h5.drop(['timel'],axis=1)
#                    if code_l is not None:
#                        if 'code' in h5.columns:
#                            h5 = h5.set_index('code')
#                        h5.drop([inx for inx in h5.index  if inx not in code_l], axis=0, inplace=True)
#                            # log.info("time in idx hdf:%s %s"%(fname,len(h5))),
#                    # if index == 'int' and 'code' not in h5.columns:
#                    #     h5=h5.reset_index()
#                    log.info("load hdf time:%0.2f"%(time.time()-h_t))
#                    return h5
#    else:
#        if h5 is not None:
#            return h5
#    return None


def load_hdf_db(fname, table='all', code_l=None, timelimit=True, index=False, limit_time=ct.h5_limit_time, dratio_limit=ct.dratio_limit,MultiIndex=False,showtable=False):
    """[summary]

    [load hdf ]

    Parameters
    ----------
    fname : {[type]}
        [description]
    table : {str}, optional
        [description] (the default is 'all', which [default_description])
    code_l : {[type]}, optional
        [description] (the default is None, which [default_description])
    timelimit : {bool}, optional
        [description] (the default is True, which [default_description])
    index : {bool}, optional
        [description] (the default is False, which [default_description])
    limit_time : {[type]}, optional
        [description] (the default is ct.h5_limit_time, which [default_description])
    dratio_limit : {[type]}, optional
        [description] (the default is ct.dratio_limit, which [default_description])
    MultiIndex : {bool}, optional
        [description] (the default is False, which [default_description])

    Returns
    -------
    [dataframe]
        [description]
    """
    time_t=time.time()
    global RAMDISK_KEY, INIT_LOG_Error
    if not RAMDISK_KEY < 1:
        return None
    df=None
    dd=None
    if code_l is not None:
        if table is not None:
            with SafeHDFStore(fname,mode='r') as store:
                # if store is not None:
                #     log.debug(f"fname: {(fname)} keys:{store.keys()}")
                #     if showtable:
                #         print(f"fname: {(fname)} keys:{store.keys()}")
                #     try:
                #         if '/' + table in list(store.keys()):
                #             dd=store[table].copy()
                #     except AttributeError as e:
                #         store.close()
                #         # os.remove(store.filename)
                #         log.error("AttributeError:%s %s"%(fname,e))
                #         # log.error("Remove File:%s"%(fname))
                #     except Exception as e:
                #         print(("Exception:%s name:%s"%(fname,e)))
                #     else:
                #         pass
                #     finally:
                #         pass
                if store is not None:
                    log.debug(f"fname: {fname} keys:{store.keys()}")
                    if showtable:
                        print(f"fname: {fname} keys:{store.keys()}")

                    try:
                        if '/' + table in store.keys():
                            obj = store.get(table)
                            if isinstance(obj, pd.DataFrame):
                                dd = obj.copy()
                            else:
                                log.error("Unexpected object type from HDF5: %s", type(obj))
                                dd = pd.DataFrame()
                        else:
                            dd = pd.DataFrame()
                    except Exception as e:
                        log.error("load_hdf_db Error: %s %s", fname, e)
                        dd = pd.DataFrame()

            if dd is not None and len(dd) > 0:
                if not MultiIndex:
                    if index:
                        code_l=list(map((lambda x: str(1000000 - int(x))
                                      if x.startswith('0') else x), code_l))
                    dif_co=list(set(dd.index) & set(code_l))
                    #len(set(dd.index) & set(code_l))
                    if len(code_l) > 0:
                        dratio=(float(len(code_l)) - float(len(dif_co))) / \
                            float(len(code_l))
                    else:
                        dratio = 0
                    # if dratio < 0.1 or len(dd) > 3100:

                    log.info("find all:%s :%s %0.2f" %
                            (len(code_l), len(code_l) - len(dif_co), dratio))
                    if not (cct.is_trade_date() and 1130 < cct.get_now_time_int() < 1300) and timelimit and len(dd) > 0:
                       dd=dd.loc[dif_co]
                       o_time=dd[dd.timel != 0].timel.tolist()
                    #                        if fname == 'powerCompute':
                    #                            o_time = sorted(set(o_time),reverse=True)
                       o_time=sorted(set(o_time), reverse=False)
                       o_time=[time.time() - t_x for t_x in o_time]

                       if len(dd) > 0:
                           # if len(dd) > 0 and (not cct.get_work_time() or len(o_time) <= ct.h5_time_l_count):
                           l_time=np.mean(o_time)
                           
                           if len(code_l)/len(dd) > 0.95 and 'ticktime' in dd.columns and 'kind' not in dd.columns:
                               # len(dd) ,len(dd.query('ticktime >= "15:00:00"'))
                               dratio=(float(len(dd)) - float(len(dd.query('ticktime >= "15:00:00"')))) / float(len(dd))
                               return_hdf_status=(not cct.get_work_time() and  dratio < dratio_limit)  or (cct.get_work_time() and l_time < limit_time)
                           else:  
                               return_hdf_status=not cct.get_work_time() or (
                                   cct.get_work_time() and l_time < limit_time)


                           # return_hdf_status=(not cct.get_work_time()) or (
                           #     cct.get_work_time() and l_time < limit_time)
                           
                           # import ipdb;ipdb.set_trace()

                           # return_hdf_status = l_time < limit_time
                           # print return_hdf_status,l_time,limit_time
                           if return_hdf_status:
                               # df=dd
                               df = dd.loc[dif_co]
                               log.info("return hdf: %s timel:%s l_t:%s hdf ok:%s" % (
                                   fname, len(o_time), l_time, len(df)))
                       else:
                           log.error("%s %s o_time:%s %s" % (fname, table, len(
                               o_time), [time.time() - t_x for t_x in o_time[:3]]))
                       log.info('fname:%s l_time:%s' %
                                (fname, [time.time() - t_x for t_x in o_time]))

                    else:
                       df=dd.loc[dif_co]

                    if dratio > dratio_limit:
                       if len(code_l) > ct.h5_time_l_count * 10 and INIT_LOG_Error < 5:
                           # INIT_LOG_Error += 1
                           log.error("dratio_limit fn:%s cl:%s h5:%s don't find:%s dra:%0.2f log_err:%s" % (
                               fname, len(code_l), len(dd), len(code_l) - len(dif_co), dratio, INIT_LOG_Error))
                           return None
    
                else:
                    df = dd.loc[dd.index.isin(code_l, level='code')]
        else:
            log.error("%s is not find %s" % (fname, table))
    else:
        # h5 = get_hdf5_file(fname,wr_mode='r')
        if table is not None:
            with SafeHDFStore(fname,mode='r') as store:
                # if store is not None:
                #     if '/' + table in store.keys():
                #         try:
                #             dd=store[table]
                #         except Exception as e:
                #             print ("%s fname:%s"%(e,fname))
                #             cct.sleep(ct.sleep_time)
                if store is not None:
                    log.debug(f"fname: {(fname)} keys:{store.keys()}")
                    if showtable:
                        print(f"keys:{store.keys()}")
                    try:
                        if '/' + table in list(store.keys()):
                            dd=store[table].copy()
                    except AttributeError as e:
                        store.close()
                        # os.remove(store.filename)
                        log.error("AttributeError:%s %s"%(fname,e))
                        # log.error("Remove File:%s"%(fname))
                    except Exception as e:
                        log.error("Exception:%s %s"%(fname,e))
                        print(("Exception:%s name:%s"%(fname,e)))
                    else:
                        pass
                    finally:
                        pass

            if dd is not None and len(dd) > 0:
                if not (cct.is_trade_date() and 1130 < cct.get_now_time_int() < 1300) and timelimit:
                    if dd is not None and len(dd) > 0:
                        o_time=dd[dd.timel != 0].timel.tolist()
                        o_time=sorted(set(o_time))
                        o_time=[time.time() - t_x for t_x in o_time]
                        if len(o_time) > 0:
                            l_time=np.mean(o_time)
                            # l_time = time.time() - l_time
                # return_hdf_status = not cct.get_work_day_status()  or not
                # cct.get_work_time() or (cct.get_work_day_status() and
                # (cct.get_work_time() and l_time < limit_time))

                            if 'ticktime' in dd.columns and 'kind' not in dd.columns:
                                # len(dd) ,len(dd.query('ticktime >= "15:00:00"'))
                                dratio=(float(len(dd)) - float(len(dd.query('ticktime >= "15:00:00"')))) / float(len(dd))
                                return_hdf_status=(not cct.get_work_time() and dratio < dratio_limit) or (cct.get_work_time() and l_time < limit_time)
                            else:  
                                return_hdf_status=not cct.get_work_time() or (
                                    cct.get_work_time() and l_time < limit_time)

                            # return_hdf_status=not cct.get_work_time() or (
                            #     cct.get_work_time() and l_time < limit_time)

                            log.info("return_hdf_status:%s time:%0.2f" %
                                     (return_hdf_status, l_time))
                            if return_hdf_status:
                                log.info("return hdf5 data:%s o_time:%s" %
                                         (len(dd), len(o_time)))
                                df=dd
                            else:
                                log.info("no return time hdf5:%s" % (len(dd)))
                        log.info('fname:%s l_time:%s' %
                                 (fname, [time.time() - t_x for t_x in o_time]))
                else:
                    df=dd
            else:
                # global Debug_is_not_find
                # if Debug_is_not_find < 4:
                #     Debug_is_not_find +=1
                # else:
                #     import ipdb;ipdb.set_trace()
                log.error("%s is not find %s" % (fname, table))
        else:
            log.error("%s / table is Init None:%s"%(fname, table))

    if df is not None and len(df) > 0:
        df=df.fillna(0)
        if 'timel' in df.columns:
            time_list=df.timel.tolist()
            # time_list = sorted(set(time_list),key = time_list.index)
            time_list=sorted(set(time_list))
            # log.info("test:%s"%(sorted(set(time_list),key = time_list.index)))
            if time_list is not None and len(time_list) > 0:
                df['timel']=time_list[0]
                log.info("load hdf times:%s" %
                         ([time.time() - t_x for t_x in time_list]))

    log.info("load_hdf_time:%0.2f" % (time.time() - time_t))

    if df is not None:
        df=df[~df.index.duplicated(keep='last')]
        if fname.find('MultiIndex') > 0 and 'volume' in df.columns:
            count_drop = len(df)
            df = df.drop_duplicates()
            # df = df.drop_duplicates('volume',keep='last')
            dratio=round((float(len(df))) / float(count_drop),2)
            log.debug("all:%s  drop:%s  dratio:%.2f"%(int(count_drop/100),int(len(df)/100),dratio))
            if dratio < 0.8:
                log.error("MultiIndex drop_duplicates:%s %s dr:%s"%(count_drop,len(df),dratio))
                if isinstance(df.index, pd.MultiIndex):
                    write_hdf_db(fname, df, table=table, index=index, MultiIndex=True,rewrite=True)

    # df = df.drop_duplicates()

    return  cct.reduce_memory_usage(df)

# def load_hdf_db_old_outdate(fname,table='all',code_l=None,timelimit=True,index=False,limit_time=ct.h5_limit_time):
#     time_t = time.time()
#     df = None
#     global RAMDISK_KEY
#     # print RAMDISK_KEY
#     if not RAMDISK_KEY < 1:
#         return df
#     if code_l is not None:
#         h5 = get_hdf5_file(fname,wr_mode='r')
#         if h5 is not None:
#             if table is not None:
#                 if '/'+table in h5.keys():
#                     if index:
#                         code_l = map((lambda x:str(1000000-int(x)) if x.startswith('0') else x),code_l)
#                     dd = h5[table]
#                     dif_co = list(set(dd.index) & set(code_l))
#                     dratio = (float(len(code_l)) - float(len(dif_co)))/float(len(code_l))
#                     if dratio < 0.1 and len(dd) > 0:
#                         log.info("find all:%s :%s %0.2f"%(len(code_l),len(code_l)-len(dif_co),dratio))
#                         if timelimit and len(dd) > 0:
#                             dd = dd.loc[dif_co]
#                             o_time = dd[dd.timel <> 0].timel
#                             if len(o_time) > 0:
#                                 o_time = o_time[0]
#                                 l_time = time.time() - o_time
#                                 return_hdf_status = not cct.get_work_day_status()  or not cct.get_work_time() or (cct.get_work_day_status() and cct.get_work_time() and l_time < ct.limit_time)
#                                 if return_hdf_status:
#                                     df = dd
#                                     log.info("load %s time hdf ok:%s"%(fname,len(df)))

#                             log.info('fname:%s l_time:None'%(fname))
#                         else:
#                              df = dd.loc[dif_co]
#                     else:
#                         log.info("don't find :%s"%(len(code_l)-len(dif_co)))
#             else:
#                 log.error("%s is not find %s"%(fname,table))
#     else:
#         h5 = get_hdf5_file(fname,wr_mode='r')
#         dd=None
#         if h5 is not None:
#             if table is None:
#                 dd = h5
#             else:
#                 if table is not None:
#                     if '/'+table in h5.keys():
#                         dd = h5[table]
#                         if timelimit and len(dd) > 0:
#                             if dd is not None and len(dd)>0:
#                                 o_time = dd[dd.timel <> 0].timel
#                                 if len(o_time) > 0:
#                                     o_time = o_time[0]
#                                     l_time = time.time() - o_time
#                                     return_hdf_status = not cct.get_work_day_status()  or not cct.get_work_time() or (cct.get_work_day_status() and cct.get_work_time() and l_time < ct.h5_limit_time)
#                                     log.info("return_hdf_status:%s time:%0.2f"%(return_hdf_status,l_time))
#                                     if  return_hdf_status:
#                                         log.info("return hdf5 data:%s"%(len(h5)))
#                                         df = dd
#                                     else:
#                                         log.info("no return time hdf5:%s"%(len(h5)))
#                                 log.info('fname:%s l_time:None'%(fname))
#                         else:
#                              df = dd
#                     else:
#                         log.error("%s is not find %s"%(fname,table))
#     if h5 is not None and h5.is_open:
#         h5.close()

#     if df is not None and len(df) > 0:
#         df = df.fillna(0)
#         if 'timel' in df.columns:
#             time_list = df.timel.tolist()
#             time_list = sorted(set(time_list),key = time_list.index)
#             if time_list is not None and len(time_list) > 0:
#                 df['timel'] = time_list[0]
#                 log.info("load hdf times:%s"%(time_list))

#     log.info("load_hdf_time:%0.2f"%(time.time()-time_t))
#     return df

def compact_hdf5_file(old_path, new_path=None, key="all_30/table"):
    if new_path is None:
        new_path = old_path.replace(".h5", "_clean.h5")
    df = pd.read_hdf(old_path, key=key)
    df.to_hdf(new_path, key=key, mode="w", format="table", complib="blosc", complevel=9)
    old_size = os.path.getsize(old_path) / 1024**2
    new_size = os.path.getsize(new_path) / 1024**2
    print(f"Compacted {old_path}: {old_size:.1f} MB → {new_size:.1f} MB")
    return new_path
if __name__ == "__main__":

    #    import tushare as ts
    #    df = ts.get_k_data('300334', start='2017-04-01')
    # p=subprocess.Popen('dir', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # p=subprocess.Popen('ptrepack --chunkshape=auto --complevel=9 --complib=zlib "D:\MacTools\WorkFile\WorkSpace\pyQuant\tdx_all_df_300.h5_tmp" "D:\MacTools\WorkFile\WorkSpace\pyQuant\tdx_all_df_300.h5"', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # import commands
    # ret,output = commands.getstatusoutput('C:\Users\Johnson\Anaconda2\Scripts\ptrepack --chunkshape=auto --complevel=9 --complib=zlib "D:\MacTools\WorkFile\WorkSpace\pyQuant\tdx_all_df_300.h5_tmp" "D:\MacTools\WorkFile\WorkSpace\pyQuant\tdx_all_df_300.h5"')
    # print output.decode('gbk'),ret
    # ret,output = commands.getstatusoutput('C:\Users\Johnson\Anaconda2\Scripts\ptrepack.exe')
    # ret,output = commands.getstatusoutput('dir')
    # print output.decode('gbk')


    # import os
    # fp=os.popen('ptrepack --chunkshape=auto --complevel=9 --complib=zlib   ../../tdx_all_df_300.h5_tmp  ../../tdx_all_df_300.h5')
    # print fp.read().decode('gbk')
    


    # p=subprocess.Popen('ptrepack --chunkshape=auto --complevel=9 --complib=zlib ../../tdx_all_df_300.h5_tmp ../../tdx_all_df_300.h5"', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # p.wait()
    # print p.stdout.read().decode("gbk")
    # print p.stderr
    # import ipdb;ipdb.set_trace()

    #pip install pandas==1.4.4
    #OSError: [WinError 1] 函数不正确。: 'G:\\'   imdisk error 

    def get_tdx_all_from_h5(showtable=True):
        #sina_monitor
        h5_fname = 'tdx_last_df'
        resample='d'
        dl='60'
        filter='y'
        h5_table = 'low' + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'
        h5 = load_hdf_db(h5_fname, table=h5_table,code_l=None, timelimit=False,showtable=showtable)
        return h5


    def get_tdx_all_MultiIndex_h5(showtable=True):
        #sina_monitor
        h5_fname = 'sina_MultiIndex_data'
        resample='d'
        dl='60'
        filter='y'
        h5_table = 'low' + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'
        h5_table = 'all_30'
        h5 = load_hdf_db(h5_fname, table=h5_table,code_l=None, timelimit=False,showtable=showtable)
        return h5

    def check_hdf(h5_fname,h5_table,showtable=True,new_path=None):
        print(f'fname : {h5_fname}')
        h5 = load_hdf_db(h5_fname, table=h5_table,code_l=None, timelimit=False,showtable=showtable)
        with tables.open_file(f"G:\\{h5_fname}.h5") as f: print(f)
        if new_path:
            hm5.to_hdf(f"G:\\{new_path}", key=f"{h5_table}/table", mode="w", format="table", complib="blosc", complevel=9)

    hm5=get_tdx_all_MultiIndex_h5()
    with tables.open_file(r"G:\sina_MultiIndex_data.h5") as f: print(f)
    with tables.open_file(r"G:\sina_data.h5") as f: print(f)
    h5=get_tdx_all_from_h5()
    
    # print(hm5.memory_usage(deep=True).sum() / 1024**2, "MB")
    # hm5.to_hdf(r"G:\sina_MultiIndex_data_clean.h5", key="all_30/table", mode="w", format="table", complib="blosc", complevel=9)
    print(f"sina_data:{check_hdf(h5_fname='sina_data',h5_table='all')}")



    import ipdb;ipdb.set_trace()

    sina_MultiD_path = "G:\\sina_MultiIndex_data.h5"
    # sina_MultiD_path = "D:\\RamDisk\\sina_MultiIndex_data.h5"
    freq='30T'
    startime = '09:25:00'
    endtime = '15:01:00'
    def readHdf5(fpath, root=None):
        store = pd.HDFStore(fpath, "r")
        (list(store.keys()))
        if root is None:
            root = list(store.keys())[0].replace("/", "")
        df = store[root]
        store.close()
        return df

    runcol=['low','high','close']
    h5 = readHdf5(sina_MultiD_path)
    import ipdb;ipdb.set_trace()
    
    h5.shape
    mdf = cct.get_limit_multiIndex_freq(h5, freq=freq.upper(),  col='all', start=startime, end=endtime, code=None)

    import ipdb;ipdb.set_trace()



    a = np.random.standard_normal((9000,4))
    df = pd.DataFrame(a)
    h5_fname = 'test_s.h5'
    h5_table = 'all'
    h5 = write_hdf_db(h5_fname, df, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=False)
    import ipdb;ipdb.set_trace()

    fname=['sina_data.h5', 'tdx_last_df', 'powerCompute.h5', 'get_sina_all_ratio']
    # fname=['test_s.h5','sina_data.h5', 'tdx_last_df', 'powerCompute.h5', 'get_sina_all_ratio']
    fname=['test_s.h5']
    # fname = 'powerCompute.h5'
    for na in fname:
        # with SafeHDFStore(na) as h5:
        with HDFStore(na) as h5:
            import ipdb;ipdb.set_trace()
            print(h5)
            if '/' + 'all' in list(h5.keys()):
                print((h5['all'].loc['600007']))
                
        # h5.remove('high_10_y_20170620_all_15')
        # print h5
        # dd = h5['d_21_y_all']
        # print len(set(dd.timel))
        # print time.time()- np.mean(list(set(dd.timel)))

    # Only put inside this block the code which operates on the store
    # store['result'] = df

# Traceback (most recent call last):
#   File "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\sina_Monitor.py", line 262, in <module>
#     top_now = tdd.getSinaAlldf(market=market_blk, vol=ct.json_countVol, vtype=ct.json_countType)
#   File "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\JSONData\tdx_data_Day.py", line 2539, in getSinaAlldf
#     df = sina_data.Sina().all
#   File "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\JSONData\sina_data.py", line 332, in all
#     return self.get_stock_data()
#   File "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\JSONData\sina_data.py", line 557, in get_stock_data
#     return self.format_response_data()
#   File "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\JSONData\sina_data.py", line 1034, in format_response_data
#     h5a.write_hdf_db(self.hdf_name, dd, self.table, index=index)
#   File "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\JSONData\tdx_hdf5_api.py", line 2023, in write_hdf_db
#     tmpdf=store[table]
#   File "C:\Users\Johnson\anaconda3\lib\site-packages\pandas\io\pytables.py", line 608, in __getitem__
#     return self.get(key)
#   File "C:\Users\Johnson\anaconda3\lib\site-packages\pandas\io\pytables.py", line 800, in get
#     return self._read_group(group)
#   File "C:\Users\Johnson\anaconda3\lib\site-packages\pandas\io\pytables.py", line 1793, in _read_group
#     s.infer_axes()
#   File "C:\Users\Johnson\anaconda3\lib\site-packages\pandas\io\pytables.py", line 2733, in infer_axes
#     self.get_attrs()
#   File "C:\Users\Johnson\anaconda3\lib\site-packages\pandas\io\pytables.py", line 3519, in get_attrs
#     self.index_axes = [a for a in self.indexables if a.is_an_indexable]
#   File "pandas\_libs\properties.pyx", line 37, in pandas._libs.properties.CachedProperty.__get__
#   File "C:\Users\Johnson\anaconda3\lib\site-packages\pandas\io\pytables.py", line 3556, in indexables
#     desc = self.description
#   File "C:\Users\Johnson\anaconda3\lib\site-packages\pandas\io\pytables.py", line 3418, in description
#     return self.table.description
# AttributeError: 'UnImplemented' object has no attribute 'description'
# Error2sleep:6
# [2025-09-22 12:27:34,831] INFO:commonTips.py(sleep:1992): sleep:6
