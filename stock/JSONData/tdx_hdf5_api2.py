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

import os
import time
import psutil
import pandas as pd
import tables
import logging
from pandas import HDFStore

log = logging.getLogger("SafeHDF")
log.setLevel(logging.DEBUG)
if not log.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    log.addHandler(ch)


# class SafeHDFLock:
#     """独立锁类，支持超时检测 + PID 存活检测"""
#     def __init__(self, lockfile, lock_timeout=10, max_wait=30, probe_interval=2):
#         self._lock = lockfile
#         self.lock_timeout = lock_timeout
#         self.max_wait = max_wait
#         self.probe_interval = probe_interval
#         self._flock = False
#         self.log = log
#         self.pid = None
#     # def acquire_lock(self):
#     def acquire(self):
#          start_time = time.time()
#          retries = 0
#          while True:
#              try:
#                  if not os.path.exists(self._lock):
#                      with open(self._lock, "w") as f:
#                          f.write(f"{os.getpid()}|{time.time()}")
#                      self.log.info(f"[Lock] acquired {self._lock} by pid={os.getpid()}")
#                      break

#                  with open(self._lock, "r") as f:
#                      content = f.read().strip()

#                  pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
#                  pid = int(pid_str) if pid_str.isdigit() else -1
#                  self.pid = pid
#                  ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0

#                  elapsed = time.time() - ts
#                  total_wait = time.time() - start_time
#                  pid_alive = psutil.pid_exists(pid)

#                  if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
#                      self.log.warning(f"[Lock] stale/timeout lock detected pid={pid}, removing {self._lock}")
#                      try:
#                          os.remove(self._lock)
#                          continue
#                      except Exception as e:
#                          self.log.error(f"[Lock] failed to remove lock: {e}")
#                          if retries > 2:
#                             self.log.error(f"[Lock] failed to remove lock retries: {retries}")
#                             self.check_pid()
#                  retries += 1
#                  self.log.info(f"[Lock] exists, pid={pid}, alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
#                  time.sleep(self.probe_interval)

#              except Exception as e:
#                  self.log.error(f"[Lock] error acquiring: {e}")
#                  time.sleep(self.probe_interval)

#     def check_pid(self):
#         pid_alive = psutil.pid_exists(self.pid)
#         pid_info = ""
#         if pid_alive:
#             try:
#                 p = psutil.Process(self.pid)
#                 pid_info = f"name={p.name()}, cmd={p.cmdline()}, create_time={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.create_time()))}"
#             except Exception as e:
#                 pid_info = f"failed to fetch info: {e}"

#         # 判断是否需要清理锁
#         # 强制结束进程（如果还活着）
#         if pid_alive:
#             try:
#                 p.terminate()  # 先尝试正常结束
#                 gone, alive = psutil.wait_procs([p], timeout=5)
#                 if alive:
#                     p.kill()  # 正常结束失败，强制杀掉
#                 self.log.warning(f"[Lock] terminated process pid={self.pid}")
#             except Exception as e:
#                 self.log.error(f"[Lock] failed to terminate process pid={self.pid}: {e}")

#         # 删除锁文件
#         try:
#             os.remove(self._lock)
#             self.log.info(f"[Lock] removed lock file {self._lock}")
#             # continue  # 再尝试获取锁
#         except Exception as e:
#             self.log.error(f"[Lock] failed to remove lock: {e}")

#     def release(self):
#         if self._flock and os.path.exists(self._lock):
#             try:
#                 os.remove(self._lock)
#                 log.info(f"[Lock] released {self._lock}")
#             except Exception as e:
#                 log.error(f"[Lock] release failed: {e}")
#         self._flock = False

    # def acquire(self):
    #     start_time = time.time()
    #     retries = 0
    #     while True:
    #         try:
    #             if not os.path.exists(self._lock):
    #                 with open(self._lock, "w") as f:
    #                     f.write(f"{os.getpid()}|{time.time()}")
    #                 self._flock = True
    #                 log.info(f"[Lock] acquired {self._lock} by pid={os.getpid()}")
    #                 break

    #             with open(self._lock, "r") as f:
    #                 content = f.read().strip()

    #             pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
    #             pid = int(pid_str) if pid_str.isdigit() else -1
    #             ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0

    #             elapsed = time.time() - ts
    #             total_wait = time.time() - start_time
    #             pid_alive = psutil.pid_exists(pid)

    #             if not pid_alive:
    #                 log.warning(f"[Lock] stale lock: pid {pid} not alive, removing {self._lock}")
    #                 try:
    #                     os.remove(self._lock)
    #                     continue
    #                 except Exception as e:
    #                     log.error(f"[Lock] failed to remove stale lock: {e}")

    #             elif elapsed > self.lock_timeout:
    #                 log.warning(f"[Lock] timeout: pid={pid}, alive={pid_alive}, "
    #                             f"elapsed={elapsed:.1f}s > {self.lock_timeout}s, removing...")
    #                 try:
    #                     os.remove(self._lock)
    #                     continue
    #                 except Exception as e:
    #                     log.error(f"[Lock] failed to remove timeout lock: {e}")

    #             if total_wait > self.max_wait:
    #                 log.error(f"[Lock] wait > {self.max_wait}s, force removing {self._lock}")
    #                 try:
    #                     os.remove(self._lock)
    #                     continue
    #                 except Exception as e:
    #                     log.error(f"[Lock] force remove failed: {e}")

    #             retries += 1
    #             log.info(f"[Lock] exists, pid={pid}, alive={pid_alive}, "
    #                      f"elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
    #             time.sleep(self.probe_interval)

    #         except Exception as e:
    #             log.error(f"[Lock] error acquiring: {e}")
    #             time.sleep(self.probe_interval)

import os
import time
import pandas as pd
import tables
import logging

log = logging.getLogger(__name__)

class SafeHDFStore(pd.HDFStore):
    def __init__(self, fname, mode='r', **kwargs):
        self.fname_o = fname
        self.mode = mode
        self.probe_interval = kwargs.pop("probe_interval", 2)  
        self.lock_timeout = kwargs.pop("lock_timeout", 20)  
        self.max_wait = 60
        self.multiIndexsize = False
        self.log = log
        if self.fname_o == "tdx_hd5_name" or self.fname_o.find('tdx_all_df') >= 0:
            self.multiIndexsize = True
            self.fname = os.path.join(os.getcwd(), self.fname_o)
            self.basedir = os.path.dirname(self.fname)
            log.info(f"tdx_hd5: {self.fname}")
        else:
            self.fname = os.path.join(os.getcwd(), self.fname_o)
            self.basedir = os.path.dirname(self.fname)
            log.info(f"ramdisk_hd5: {self.fname}")

        self._lock = self.fname + ".lock"
        self._flock = None
        self.write_status = True if os.path.exists(self.fname) else False
        self.my_pid = os.getpid()

        if not os.path.exists(self.fname):
            log.warning(f"HDF5 file {self.fname} not found. Creating empty file.")
            with pd.HDFStore(self.fname, mode='w') as store:
                pass

        self._check_and_clean_corrupt_keys()

        if mode != 'r':
            self._acquire_lock()
        elif mode == 'r':
            self._wait_for_lock()

        super().__init__(self.fname, mode=mode, **kwargs)

    def write_safe(self, key, df, **kwargs):
        """写入 HDF5，同时打印 PID 日志"""
        corrupt = False
        if key in self.keys():
            try:
                _ = self.get(key)
            except (tables.exceptions.HDF5ExtError, AttributeError) as e:
                log.warning(f"[{self.my_pid}] Key {key} corrupted: {e}, removing before rewrite")
                corrupt = True
        if corrupt:
            try:
                self.remove(key)
                log.info(f"[{self.my_pid}] Removed corrupted key: {key}")
            except Exception as e:
                log.error(f"[{self.my_pid}] Failed to remove key {key}: {e}")
        try:
            self.put(key, df, **kwargs)
            log.info(f"[{self.my_pid}] Successfully wrote key: {key}")
        except Exception as e:
            log.error(f"[{self.my_pid}] Failed to write key {key}: {e}")

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
                                log.info(f"Removed corrupted key: {key}")
                            except Exception as e:
                                log.error(f"Failed to remove key {key}: {e}")
        except Exception as e:
            log.error(f"HDF5 file {self.fname} corrupted, recreating: {e}")
            with pd.HDFStore(self.fname, mode='w') as store:
                pass

    def _acquire_lock(self):
        start_time = time.time()
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
                total_wait = time.time() - start_time
                pid_alive = psutil.pid_exists(pid)

                if pid == my_pid:
                    # 自己持有锁，直接清理并重建锁
                    self.log.info(f"[Lock] lock owned by self (pid={pid}) (my_pid:{my_pid}), removing and reacquiring")
                    try:
                        os.remove(self._lock)
                    except Exception as e:
                        self.log.error(f"[Lock] failed to remove self lock: {e}")
                    continue

                if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
                    # 锁超时或持有锁进程不存在，可以删除锁
                    self.log.warning(f"[Lock] stale/timeout lock detected pid={pid} (my_pid:{my_pid}), removing {self._lock}")
                    try:
                        os.remove(self._lock)
                    except Exception as e:
                        self.log.error(f"[Lock] failed to remove lock: {e}")
                    continue

                # 其他进程持有锁，等待
                retries += 1
                if retries % 3 == 0:
                    self.log.info(f"[Lock] exists, pid={pid},(my_pid:{my_pid}), alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
                time.sleep(self.probe_interval)

            else:
                # 创建锁文件
                try:
                    with open(self._lock, "w") as f:
                        f.write(f"{my_pid}|{time.time()}")
                    self.log.info(f"[Lock] acquired {self._lock} by pid={my_pid}")
                    return True
                except Exception as e:
                    self.log.error(f"[Lock] failed to create lock: {e}")
                    time.sleep(self.probe_interval)

    def _wait_for_lock(self):
        """读取模式等待锁释放"""
        start_time = time.time()
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
            total_wait = time.time() - start_time
            log.info(f"[{self.my_pid}] Waiting for lock held by pid={lock_pid}, elapsed={elapsed:.1f}s total_wait={total_wait:.1f}s")
            time.sleep(self.probe_interval)

    def _release_lock(self):
        if os.path.exists(self._lock):
            try:
                with open(self._lock, "r") as f:
                    pid_in_lock = int(f.read().split("|")[0])
                if pid_in_lock == self.my_pid:
                    os.remove(self._lock)
                    log.info(f"[{self.my_pid}] Lock released: {self._lock}")
            except Exception as e:
                log.error(f"[{self.my_pid}] Failed to release lock: {e}")

    def close(self):
        super().close()
        self._release_lock()


import os, time, psutil, pandas as pd, tables, logging

class SafeHDFStore111(pd.HDFStore):
    def __init__(self, fname, mode='r', **kwargs):
        # 基本路径处理
        self.fname_o = fname
        self.mode = mode
        self.probe_interval = kwargs.pop("probe_interval", 3)  # 默认轮询 3 秒
        self.lock_timeout = kwargs.pop("lock_timeout", 20)     # 锁超时
        self.max_wait = kwargs.pop("max_wait", 60)             # 总等待超时
        self.multiIndexsize = False
        self.my_pid = None
        # 设置文件路径
        if self.fname_o == cct.tdx_hd5_name or self.fname_o.find('tdx_all_df') >= 0:
            self.multiIndexsize = True
            self.fname = cct.get_run_path_tdx(self.fname_o)
            self.basedir = self.fname.split(self.fname_o)[0]
            log.info(f"tdx_hd5: {self.fname}")
        else:
            self.fname = cct.get_ramdisk_path(self.fname_o)
            self.basedir = self.fname.split(self.fname_o)[0]
            log.info(f"ramdisk_hd5: {self.fname}")

        self._lock = self.fname + ".lock"
        self._flock = None
        self.write_status = os.path.exists(self.fname)

        # HDF5 压缩设置
        self.complevel = 9
        self.complib = 'zlib'

        # 日志
        # self.log = kwargs.get("log", logging.getLogger(__name__))
        self.log = log

        # 创建空文件
        if not os.path.exists(self.fname):
            self.log.warning(f"HDF5 file {self.fname} not found. Creating empty file.")
            with pd.HDFStore(self.fname, mode='w') as store:
                pass

        self._check_and_clean_corrupt_keys()

        # 根据模式获取锁
        if mode != 'r':
            self._acquire_lock()
        else:
            self._wait_for_lock()

        super().__init__(self.fname, mode=mode, **kwargs)

    def write_safe(self, key, df, **kwargs):
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
        try:
            self.put(key, df, **kwargs)
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
                        self.log.error(f"Failed to read key {key}: {e}")
                        corrupt_keys.append(key)
                if corrupt_keys:
                    self.log.warning(f"Corrupt keys detected: {corrupt_keys}, removing...")
                    store.close()
                    with pd.HDFStore(self.fname, mode='a') as wstore:
                        for key in corrupt_keys:
                            try:
                                wstore.remove(key)
                                self.log.info(f"Removed corrupted key: {key}")
                            except Exception as e:
                                self.log.error(f"Failed to remove key {key}: {e}")
        except Exception as e:
            self.log.error(f"HDF5 file {self.fname} corrupted, recreating: {e}")
            with pd.HDFStore(self.fname, mode='w') as store:
                pass

    def acquire(self):
            start_time = time.time()
            my_pid = os.getpid()
            retries = 0
            self.my_pid = my_pid
            while True:
                # 检查锁文件是否存在
                if os.path.exists(self._lock):
                    with open(self._lock, "r") as f:
                        content = f.read().strip()
                    pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
                    pid = int(pid_str) if pid_str.isdigit() else -1
                    ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0
                    elapsed = time.time() - ts
                    total_wait = time.time() - start_time
                    pid_alive = psutil.pid_exists(pid)

                    if pid == my_pid:
                        # 自己持有锁，直接清理并重建锁
                        self.log.info(f"[Lock] lock owned by self (pid={pid}), removing and reacquiring")
                        try:
                            os.remove(self._lock)
                        except Exception as e:
                            self.log.error(f"[Lock] failed to remove self lock: {e}")
                        continue

                    if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
                        # 锁超时或持有锁进程不存在，可以删除锁
                        self.log.warning(f"[Lock] stale/timeout lock detected pid={pid}, removing {self._lock}")
                        try:
                            os.remove(self._lock)
                        except Exception as e:
                            self.log.error(f"[Lock] failed to remove lock: {e}")
                        continue

                    # 其他进程持有锁，等待
                    retries += 1
                    self.log.info(f"[Lock] exists, pid={pid}, alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
                    time.sleep(self.probe_interval)

                else:
                    # 创建锁文件
                    try:
                        with open(self._lock, "w") as f:
                            f.write(f"{my_pid}|{time.time()}")
                        self.log.info(f"[Lock] acquired {self._lock} by pid={my_pid}")
                        return True
                    except Exception as e:
                        self.log.error(f"[Lock] failed to create lock: {e}")
                        time.sleep(self.probe_interval)

    def _acquire_lock(self):
        start_time = time.time()
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
                total_wait = time.time() - start_time
                pid_alive = psutil.pid_exists(pid)

                if pid == my_pid:
                    # 自己持有锁，直接清理并重建锁
                    self.log.info(f"[Lock] lock owned by self (pid={pid}) (my_pid:{my_pid}), removing and reacquiring")
                    try:
                        os.remove(self._lock)
                    except Exception as e:
                        self.log.error(f"[Lock] failed to remove self lock: {e}")
                    continue

                if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
                    # 锁超时或持有锁进程不存在，可以删除锁
                    self.log.warning(f"[Lock] stale/timeout lock detected pid={pid} (my_pid:{my_pid}), removing {self._lock}")
                    try:
                        os.remove(self._lock)
                    except Exception as e:
                        self.log.error(f"[Lock] failed to remove lock: {e}")
                    continue

                # 其他进程持有锁，等待
                retries += 1
                if retries % 3 == 0:
                    self.log.info(f"[Lock] exists, pid={pid},(my_pid:{my_pid}), alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
                time.sleep(self.probe_interval)

            else:
                # 创建锁文件
                try:
                    with open(self._lock, "w") as f:
                        f.write(f"{my_pid}|{time.time()}")
                    self.log.info(f"[Lock] acquired {self._lock} by pid={my_pid}")
                    return True
                except Exception as e:
                    self.log.error(f"[Lock] failed to create lock: {e}")
                    time.sleep(self.probe_interval)
    # def _acquire_lock(self):
    #     """获取文件锁，支持 PID 检测、超时清理、轮询提示和强制结束死锁进程"""
    #     start_time = time.time()
    #     retries = 0
    #     while True:
    #         try:
    #             if not os.path.exists(self._lock):
    #                 with open(self._lock, 'w') as f:
    #                     f.write(f"{os.getpid()}|{time.time()}")
    #                 self._flock = True
    #                 self.log.info(f"[Lock] acquired {self._lock} by pid={os.getpid()}")
    #                 break

    #             # 读取锁文件
    #             with open(self._lock, 'r') as f:
    #                 content = f.read().strip()
    #             pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
    #             pid = int(pid_str) if pid_str.isdigit() else -1
    #             ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0

    #             elapsed = time.time() - ts
    #             total_wait = time.time() - start_time
    #             pid_alive = psutil.pid_exists(pid)

    #             # 检测死锁或超时
    #             if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
    #                 self.log.warning(f"[Lock] stale/timeout lock detected pid={pid}, "
    #                                  f"alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s")
    #                 # 尝试结束进程
    #                 if pid_alive:
    #                     try:
    #                         p = psutil.Process(pid)
    #                         p.terminate()
    #                         self.log.warning(f"[Lock] forcibly terminated pid={pid}")
    #                         time.sleep(0.5)
    #                     except Exception as e:
    #                         self.log.error(f"[Lock] failed to terminate pid={pid}: {e}")

    #                 # 尝试删除锁文件
    #                 try:
    #                     os.remove(self._lock)
    #                     self.log.info(f"[Lock] removed lock file {self._lock}")
    #                     continue
    #                 except Exception as e:
    #                     self.log.error(f"[Lock] failed to remove lock: {e}")

    #             # 锁存在，等待重试
    #             retries += 1
    #             if retries % 5 == 0:
    #                 self.log.info(f"[Lock] exists, pid={pid}, alive={pid_alive}, "
    #                           f"elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
    #             time.sleep(self.probe_interval)

    #         except Exception as e:
    #             self.log.error(f"[Lock] error acquiring lock: {e}")
    #             time.sleep(self.probe_interval)

    def _wait_for_lock(self):
        """等待其他进程释放锁"""
        start_time = time.time()
        self.my_pid = os.getpid()
        while os.path.exists(self._lock):
            try:
                with open(self._lock, 'r') as f:
                    content = f.read().strip()
                pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
                pid = int(pid_str) if pid_str.isdigit() else -1
                ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0
                elapsed = time.time() - ts
                total_wait = time.time() - start_time
                self.log.info(f"[Lock] waiting for lock, pid={pid} (my_pid:{self.my_pid}), elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s")
            except Exception as e:
                self.log.error(f"[Lock] error reading lock: {e}")
            time.sleep(self.probe_interval)



def clean_pid_lock():
    import psutil
    if os.path.exists(self._lock):
        try:
            with open(self._lock, 'r') as f:
                pid_str, ts_str = f.read().split('|')
                pid = int(pid_str)
        except Exception:
            pid = None

        # 检查进程是否存在
        if pid and not psutil.pid_exists(pid):
            try:
                os.remove(self._lock)
                self.log.info(f"SafeHDF: removed stale lock from dead pid {pid}")
            except Exception as e:
                self.log.error(f"SafeHDF: failed to remove stale lock: {e}")
        else:
            # 仍然被占用或者PID活跃，等待
            self.log.info(f"SafeHDF: lock held by active pid {pid}, waiting...")



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
            # h5 = get_hdf5_file(fname,wr_mode='r')
            tmpdf=[]
            with SafeHDFStore(fname,mode='r') as store:
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
                # df.loc[df.index.isin(['000002','000001'], level='code')]
                # df.loc[(df.index.get_level_values('code')== 600004)]
                # df.loc[(df.index.get_level_values('code')== '600199')]
                # da.swaplevel(0, 1, axis=0).loc['2017-05-25']
                # df.loc[(600004,20170414),:]
                # df.xs(20170425,level='date')
                # df.index.get_level_values('code').unique()
                # df.index.get_loc(600006)
                # slice(58, 87, None)
                # df.index.get_loc_level(600006)
                # da.swaplevel(0, 1, axis=0).loc['2017-05-25']
                # da.reorder_levels([1,0], axis=0)
                # da.sort_index(level=0, axis=0,ascending=False
                # setting: dfm.index.is_lexsorted() dfm = dfm.sort_index()  da.loc[('000001','2017-05-12'):('000005','2017-05-25')]
                # da.groupby(level=1).mean()
                # da.index.get_loc('000005')     da.iloc[slice(22,33,None)]
                # mask = totals['dirty']+totals['swap'] > 1e7     result =
                # mask.loc[mask]
                # store.remove('key_name', where='<where clause>')


                # tmpdf = tmpdf[~tmpdf.index.duplicated(keep='first')]
                # df = df[~df.index.duplicated(keep='first')]
                if not rewrite and tmpdf is not None and len(tmpdf) > 0:
                    # multi_code = tmpdf.index.get_level_values('code').unique().tolist()
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
                    # da.drop(('000001','2017-05-11'))
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
            # else:
            #     print col
            #     for co in col:
            #         print ('object:%s'%(co))
                # df = df.drop(col,axis=1)
#                    df[co] = df[co].apply()
#                    recordStringInHDF5(h5file, h5file.root, 'mrtamb',u'\u266b Hey Mr. Tambourine Man \u266b')
    
        with SafeHDFStore(fname,mode='a') as h5:
            df=df.fillna(0)
            df=cct.reduce_memory_usage(df,verbose=False)
            log.info(f'df.shape:{df.shape}')
            if h5 is not None:
                if '/' + table in list(h5.keys()):
                    # isinstance(df.index, pd.MultiIndex)
                    if not MultiIndex:

                        # if MultiIndex and rewrite:
                        #     src_code = h5[table].index.get_level_values('code').unique().tolist()
                        #     new_code = df.index.get_level_values('code').unique().tolist()
                        #     diff_code = list(set(new_code) - set(src_code))
                        #     dratio = cct.get_diff_dratio(new_code, src_code)
                        #     print dratio,len(diff_code)
                        #     import ipdb;ipdb.set_trace()
                        #     df = pd.concat([df, h5[table]], axis=0)
                        #     df = df.index.drop_duplicates()
                                # df[df.index.get_level_values('code') not in diff_code ]
                        h5.remove(table)
                        # h5[table]=df
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
                if store is not None:
                    log.debug(f"fname: {(fname)} keys:{store.keys()}")
                    if showtable:
                        print(f"fname: {(fname)} keys:{store.keys()}")
                    try:
                        if '/' + table in list(store.keys()):
                            dd=store[table]
                    except AttributeError as e:
                        store.close()
                        # os.remove(store.filename)
                        log.error("AttributeError:%s %s"%(fname,e))
                        # log.error("Remove File:%s"%(fname))
                    except Exception as e:
                        print(("Exception:%s name:%s"%(fname,e)))
                    else:
                        pass
                    finally:
                        pass

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
                    if timelimit and len(dd) > 0:
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


    #                 if dratio < dratio_limit:
    #                     log.info("find all:%s :%s %0.2f" %
    #                              (len(code_l), len(code_l) - len(dif_co), dratio))
    #                     if timelimit and len(dd) > 0:
    #                         dd=dd.loc[dif_co]
    #                         o_time=dd[dd.timel <> 0].timel.tolist()
    # #                        if fname == 'powerCompute':
    # #                            o_time = sorted(set(o_time),reverse=True)
    #                         o_time=sorted(set(o_time), reverse=False)
    #                         o_time=[time.time() - t_x for t_x in o_time]

    #                         if len(dd) > 0:
    #                             # if len(dd) > 0 and (not cct.get_work_time() or len(o_time) <= ct.h5_time_l_count):
    #                             l_time=np.mean(o_time)
    #                             return_hdf_status=(not cct.get_work_time()) or (
    #                                 cct.get_work_time() and l_time < limit_time)
    #                             # return_hdf_status = l_time < limit_time
    #                             # print return_hdf_status,l_time,limit_time
    #                             if return_hdf_status:
    #                                 # df=dd
    #                                 dd.loc[dif_co]
    #                                 log.info("return hdf: %s timel:%s l_t:%s hdf ok:%s" % (
    #                                     fname, len(o_time), l_time, len(df)))
    #                         else:
    #                             log.error("%s %s o_time:%s %s" % (fname, table, len(
    #                                 o_time), [time.time() - t_x for t_x in o_time[:3]]))
    #                         log.info('fname:%s l_time:%s' %
    #                                  (fname, [time.time() - t_x for t_x in o_time]))

    #                     else:
    #                         df=dd.loc[dif_co]
    #                 else:
    #                     if len(code_l) > ct.h5_time_l_count * 10 and INIT_LOG_Error < 5:
    #                         # INIT_LOG_Error += 1
    #                         log.error("fn:%s cl:%s h5:%s don't find:%s dra:%0.2f log_err:%s" % (
    #                             fname, len(code_l), len(dd), len(code_l) - len(dif_co), dratio, INIT_LOG_Error))
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
                            dd=store[table]
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
                if timelimit:
                    if dd is not None and len(dd) > 0:
                        o_time=dd[dd.timel != 0].timel.tolist()
                        o_time=sorted(set(o_time))
                        o_time=[time.time() - t_x for t_x in o_time]
                        if len(o_time) > 0:
                            l_time=np.mean(o_time)
 

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

    h5=get_tdx_all_from_h5()
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
        with SafeHDFStore(fname,mode='r') as h5:
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
