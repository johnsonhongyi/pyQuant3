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
from JohnsonUtil.commonTips import timed_ctx
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
import psutil
import shutil, os
from pathlib import Path

from contextlib import contextmanager

from datetime import datetime

def normalize_ticktime(df, default_date=None):
    """
    将 ticktime 列统一为 datetime64[ns]
    - df: 包含 ticktime 列的 DataFrame
    - default_date: 如果时间缺少日期，使用这个日期，默认今天
    """
    if default_date is None:
        default_date = datetime.today().strftime('%Y-%m-%d')
    
    def parse_ticktime(val):
        # 如果是完整日期时间字符串，直接解析
        try:
            return pd.to_datetime(val)
        except Exception:
            # 如果是时间字符串，拼接默认日期再解析
            return pd.to_datetime(f"{default_date} {val}")

    df['ticktime'] = df['ticktime'].apply(parse_ticktime)
    return df

# 使用方法
# df = normalize_ticktime(df)

def cleanup_temp_dir(base_dir: str, temp_name: str = "Temp") -> None:
    """
    清理 base_dir 下的 Temp 目录内容（不确认、不抛异常、尽力而为）

    :param base_dir: 如 G:\\
    :param temp_name: 默认 Temp
    """
    try:
        base_dir = os.path.abspath(base_dir)
        temp_dir = os.path.join(base_dir, temp_name)

        if not os.path.isdir(temp_dir):
            return

        for name in os.listdir(temp_dir):
            path = os.path.join(temp_dir, name)

            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=False)
                    log.info(f"[TempCleanup] removed dir: {path}")
                else:
                    os.remove(path)
                    log.info(f"[TempCleanup] removed file: {path}")
            except Exception as e:
                # 关键策略：只记录，不中断
                log.warning(f"[TempCleanup] skip: {path}, reason: {e}")

    except Exception as e:
        # base_dir 本身异常，也不能影响主流程
        log.error(f"[TempCleanup] fatal error on base_dir={base_dir}: {e}")


# class SafeHDFStore_timed_ctx(pd.HDFStore):
class SafeHDFStore(pd.HDFStore):
    def __init__(self, fname, mode='a', **kwargs):
        @contextmanager
        def timed_ctx(name):
            start = time.time()
            try:
                yield
            finally:
                end = time.time()
                self.log.info(f"[timed] {name}: {end - start:.3f}s")

        self.fname_o = fname
        self.mode = mode
        self.probe_interval = kwargs.pop("probe_interval", 2)  
        self.lock_timeout = kwargs.pop("lock_timeout", 10)  
        self.max_wait = 60
        self.multiIndexsize = False
        self.log = log
        self.basedir = BaseDir
        # 启动即清理（一次即可）
        if cct.cleanRAMdiskTemp:
            cleanup_temp_dir(self.basedir)

        self.log.info(f'{self.fname_o.lower()} {self.basedir.lower()}')
        self.start_time = time.time()
        self.config_ini = os.path.join(self.basedir, 'h5config.txt')

        self.complevel = 9
        self.complib = 'zlib'
        # self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"
        self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --alignment=1024 --complevel=9 --complib=%s %s %s"

        self.h5_size_org = 0
        global RAMDISK_KEY

        # 文件路径处理
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
                self.h5_size_org = os.path.getsize(self.fname) / 1e6

        self._lock = self.fname + ".lock"
        self._flock = None
        self.write_status = os.path.exists(self.fname)
        self.my_pid = os.getpid()
        self.log.info(f"self.fname: {self.fname} self.basedir:{self.basedir}")

        # 确保 HDF5 文件存在
        with timed_ctx("ensure_hdf_file"):
            self.ensure_hdf_file() 

        # # 父类初始化
        # with timed_ctx("hdfstore_init"):
        #     super().__init__(self.fname, **kwargs)

        opened = False
        need_repair = False

        # ========= 核心：只在这里判断是否损坏 =========
        try:
            with timed_ctx("hdfstore_open"):
                # super().__init__(self.fname, mode=mode, **kwargs)
                super().__init__(self.fname, **kwargs)
            opened = True

        except (tables.exceptions.HDF5ExtError, OSError, ValueError) as e:
            self.log.error(f"[HDF] open failed: {e}")
            need_repair = True

        # ========= 异常路径：才做清理 =========
        if not opened and need_repair:
            with timed_ctx("check_corrupt_keys"):
                # self._repair_hdf_file()   # 见下方
                self._check_and_clean_corrupt_keys()   # 见下方
            with timed_ctx("reopen_hdf"):
                super().__init__(self.fname, **kwargs)

        if self.mode != 'r':
            with timed_ctx("acquire_lock"):
                self._acquire_lock()
        else:
            with timed_ctx("wait_for_lock"):
                # 原来只 wait 不 acquire，导致写者可能插入
                # 现在改为：读也加锁（虽然牺牲并发，但保证安全）
                self._acquire_lock()

        # 检查损坏 key
        # with timed_ctx("check_corrupt_keys"):
        #     self._check_and_clean_corrupt_keys()

    def ensure_hdf_file(self):
        """确保 HDF5 文件存在"""
        if not os.path.exists(self.fname):
            # 使用 'w' 创建空文件
            with timed_ctx("ensure_hdf_file"):
                pd.HDFStore(self.fname, mode='w').close()

    def _check_and_clean_corrupt_keys(self, keys=None):
        """
        检查 HDF5 文件中的损坏 key。
        keys: 可选，只检查传入的 key，默认检查所有 key。
        延迟检查：只在访问或写入时才检查 key。
        """
        corrupt_keys = []
        try:
            with timed_ctx("check_corrupt_keys read"):
                with pd.HDFStore(self.fname, mode='a') as store:
                    keys_to_check = keys if keys else store.keys()
                    for key in keys_to_check:
                        try:
                            _ = store.get(key)
                        except Exception as e:
                            self.log.error(f"Failed to read key {key}: {e}")
                            corrupt_keys.append(key)
        except Exception as e:
            self.log.error(f"无法修复Error opening HDF5 file {self.fname}: {e}")
            self._delete_file()
            self.log.error(f"_delete_file:{self.fname}")
            self.ensure_hdf_file()
            return

        if corrupt_keys:
            self.log.warning(f"Corrupt keys detected: {corrupt_keys}, removing...")
            with timed_ctx("check_corrupt_keys remove"):
                for key in corrupt_keys:
                    try:
                        with pd.HDFStore(self.fname, mode='a') as store:
                            store.remove(key)
                        self.log.info(f"Removed corrupted key: {key}")
                    except Exception as e:
                        self.log.error(f"Failed to remove key {key}: {e}")


    def _check_and_clean_corrupt_keys_all_key(self):
            corrupt_keys = []
            try:
                # 使用 with 打开 HDF5 文件，确保在操作完成后关闭文件
                with timed_ctx("check_corrupt_keys read"):
                    with pd.HDFStore(self.fname, mode='a') as store:
                        keys = store.keys()

                        for key in keys:
                            try:
                                _ = store.get(key)
                            except Exception as e:  # 捕获所有异常
                                log.error(f"Failed to read key {key}: {e}")
                                corrupt_keys.append(key)

            except Exception as e:
                log.error(f"Error opening HDF5 file {self.fname}: {e}")
                return

            # 处理发现的损坏 keys
            if corrupt_keys:
                log.warning(f"Corrupt keys detected: {corrupt_keys}, removing...")
                with timed_ctx("check_corrupt_keys remove"):
                    for key in corrupt_keys:
                        try:
                            with pd.HDFStore(self.fname, mode='a') as store:
                                store.remove(key)
                            log.info(f"Removed corrupted key: {key}")
                        except Exception as e:
                            log.error(f"Failed to remove key {key}: {e}")
                            # 删除损坏的文件
                            self._delete_file()

    def _delete_file(self):
        """删除损坏的文件"""
        try:
            with timed_ctx("_delete_file"):
                if os.path.isfile(self.fname):
                    os.remove(self.fname)
                    log.info(f"文件删除成功: {self.fname}")
                else:
                    log.error(f"文件 {self.fname} 不存在，无法删除")
        except Exception as e:
            log.error(f"删除文件失败: {e}")
            # 在这里添加一些逻辑，比如稍后再重试等

    def _acquire_lock(self):
        my_pid = os.getpid()
        retries = 0
        try:
            while True:
                # 检查锁文件是否存在
                with timed_ctx("_acquire_lock"):
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
            with timed_ctx("_forced_unlock"):
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
        with timed_ctx("_wait_for_lock"):
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


    def close(self):
        super().close()
        # self._release_lock()

    def write_safe(self, key, df, **kwargs):
        # from contextlib import contextmanager
        # def timed_ctx(name):
        #     start = time.time()
        #     yield
        #     end = time.time()
        #     self.log.info(f"[timed] {name}: {end - start:.3f}s")

        corrupt = False
        if key in self.keys():
            try:
                _ = self.get(key)
            except (tables.exceptions.HDF5ExtError, AttributeError):
                corrupt = True
        if corrupt:
            try:
                self.remove(key)
            except Exception:
                pass

        if 'chunksize' not in kwargs:
            col_bytes = sum(8 if pd.api.types.is_numeric_dtype(dt) else 1 if pd.api.types.is_bool_dtype(dt) else 50 for dt in df.dtypes)
            target_chunk_size = 5 * 1024 * 1024
            kwargs['chunksize'] = max(1000, int(target_chunk_size / col_bytes))
        with timed_ctx(f"write_key_{key}"):
            self.put(key, df, format='table', **kwargs)


    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.write_status:
            try:
                self.close()
                super().__exit__(exc_type, exc_val, exc_tb)
                h5_size = int(os.path.getsize(self.fname) / 1e6)
                if h5_size > 10 and self.mode != 'r':
                    with timed_ctx("release_lock"):
                        # ===== 压缩逻辑 =====
                        # h5_size = int(os.path.getsize(self.fname) / 1e6)
                        h5_size_limit =  h5_size*2 if h5_size > 10 else 10
                        if self.fname_o.find('tdx_all_df') >= 0 or self.fname_o.find('sina_MultiIndex_data') >= 0:
                            h5_size = 40 if h5_size < 40 else h5_size
                            new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit) if h5_size > self.big_H5_Size_limit else self.big_H5_Size_limit
                        else:
                            new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit) if h5_size > self.big_H5_Size_limit else h5_size_limit
                            
                        read_ini_limit = cct.get_config_value(self.config_ini,self.fname_o,read=True)
                        self.log.info(f"fname: {self.fname} read_ini_limit:{read_ini_limit} h5_size: {h5_size} new_limit:{new_limit} big_limit: {self.big_H5_Size_limit} conf:{read_ini_limit}")
                        # if (read_ini_limit is  None and h5_size > self.big_H5_Size_limit) or cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
                        config_status = cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit)
                        if cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
                            self.log.info(f"to temp fname: {self.fname} read_ini_limit config_status: {config_status} to {self.temp_file}") 
                            if self.mode == 'r':
                                self._acquire_lock()
                            if os.path.exists(self.fname) and os.path.exists(self.temp_file):
                                log.error(f"Remove tmp file exists: {self.temp_file}")
                                os.remove(self.temp_file)
                            back_path = os.getcwd()
                            try:
                                # 1️⃣ 原文件 → temp
                                os.rename(self.fname, self.temp_file)
                                # 2️⃣ 构造安全相对路径
                                os.chdir(self.basedir)
                                temp_rel = os.path.relpath(self.temp_file, self.basedir)
                                fname_rel = os.path.relpath(self.fname, self.basedir)
                                log.info(f'basedir: {self.basedir} rename : {self.fname} to {self.temp_file} temp_rel: {temp_rel} fname_rel: {fname_rel}')

                                pt_cmd = self.ptrepack_cmds % (self.complib, temp_rel, fname_rel)
                                log.info(f'pt_cmd: {pt_cmd}')

                                p = subprocess.Popen(
                                    pt_cmd, shell=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                                )
                                out = p.communicate()[0]

                                if p.returncode != 0:
                                    raise RuntimeError(f"ptrepack failed: {out}")

                                # 3️⃣ 成功：删除 temp
                                if os.path.exists(self.temp_file):
                                    os.remove(self.temp_file)

                            except Exception as e:
                                log.error(f"ptrepack exception: {e}")

                                # 🔥 关键：回滚
                                if os.path.exists(self.temp_file) and not os.path.exists(self.fname):
                                    os.rename(self.temp_file, self.fname)

                            finally:
                                os.chdir(back_path)

            finally:
                time.sleep(0.1)
                with timed_ctx("release_lock"):
                    self._release_lock()
                self.log.info(f'clean:{self.fname}')
        else:
            with timed_ctx("exit close"):
                self.close()
                super().__exit__(exc_type, exc_val, exc_tb)


# class SafeHDFStore_no_timed_ctx(pd.HDFStore):
# # class SafeHDFStore(pd.HDFStore):
#     def __init__(self, fname, mode='a', **kwargs):
#         self.fname_o = fname
#         self.mode = mode
#         self.probe_interval = kwargs.pop("probe_interval", 2)  
#         self.lock_timeout = kwargs.pop("lock_timeout", 10)  
#         self.max_wait = 60
#         self.multiIndexsize = False
#         self.log = log
#         self.basedir = BaseDir
#         self.log.info(f'{self.fname_o.lower()} {self.basedir.lower()}')
#         self.start_time = time.time()
#         self.config_ini = self.basedir + os.path.sep+ 'h5config.txt'

#         self.complevel = 9
#         self.complib = 'zlib'
#         self.ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"

#         self.h5_size_org = 0
#         global RAMDISK_KEY


#         if self.fname_o.lower().find(self.basedir.lower()) < 0 and (self.fname_o == cct.tdx_hd5_name or self.fname_o.find('tdx_all_df') >= 0):
#             self.multiIndexsize = True
#             self.fname = cct.get_run_path_tdx(self.fname_o)
#             self.basedir = self.fname.split(self.fname_o)[0]
#             self.log.info(f"tdx_hd5: {self.fname}")
#         else:
#             self.fname = cct.get_ramdisk_path(self.fname_o)
#             self.basedir = self.fname.split(self.fname_o)[0]
#             self.log.info(f"ramdisk_hd5: {self.fname}")

#         if self.multiIndexsize or self.fname_o.find('sina_MultiIndex') >= 0:
#             self.big_H5_Size_limit = ct.big_H5_Size_limit * 6
#         else:
#             self.big_H5_Size_limit = ct.big_H5_Size_limit
#         self.log.info(f'self.big_H5_Size_limit :{self.big_H5_Size_limit} self.multiIndexsize :{self.multiIndexsize}')
#         if not os.path.exists(self.basedir):
#             if RAMDISK_KEY < 1:
#                 log.error("NO RamDisk Root:%s" % (baseDir))
#                 RAMDISK_KEY += 1
#         else:
#             self.temp_file = self.fname + '_tmp'
#             if os.path.exists(self.fname):
#                 self.h5_size_org = os.path.getsize(self.fname) / 1000 / 1000


#         self._lock = self.fname + ".lock"
#         self._flock = None
#         self.write_status = True if os.path.exists(self.fname) else False
#         self.my_pid = os.getpid()
#         self.log.info(f"self.fname: {self.fname} self.basedir:{self.basedir}")

#         if self.mode != 'r':
#             self._acquire_lock()
#         elif self.mode == 'r':
#             self._wait_for_lock()
#         self.log.info(f'mode : {self.mode}  fname:{self.fname}')
#         # self._check_and_clean_corrupt_keys()
#         self.ensure_hdf_file() 
#         super().__init__(self.fname, **kwargs)

#     def ensure_hdf_file(self):
#         """确保 HDF5 文件存在"""
#         if not os.path.exists(self.fname):
#             # 使用 'w' 创建空文件
#             pd.HDFStore(self.fname, mode='w').close()

#     def write_safe(self, key, df, append=False,  chunksize=10000, **kwargs):
#         """
#         安全写入 HDF5，无论 store 打开模式是 'a' 还是 'w'
#         自动加锁、删除损坏 key、自动计算 chunksize
#         """

        
#         # 确保文件加锁（如果自己持有锁则不会重复加锁）
#         # if mode != 'r' 已加锁
#         # self._acquire_lock()

#         # 删除损坏 key
#         if key in self.keys():
#             try:
#                 _ = self.get(key)
#             except (tables.exceptions.HDF5ExtError, AttributeError):
#                 self.log.info(f"Corrupt key {key} detected, removing")
#                 try:
#                     self.remove(key)
#                 except Exception as e:
#                     self.log.info(f"Failed to remove key {key}: {e}")

#         # 写入
#         try:
#             self.put(key, df, format='table', **kwargs)
#             self.log.info(f"Successfully wrote key: {key}")
#         except Exception as e:
#             self.log.error(f"Failed to write key {key}: {e}")

#     def _check_and_clean_corrupt_keys(self):
#             corrupt_keys = []
#             try:
#                 # 使用 with 打开 HDF5 文件，确保在操作完成后关闭文件
#                 with pd.HDFStore(self.fname, mode='a') as store:
#                     keys = store.keys()

#                     for key in keys:
#                         try:
#                             _ = store.get(key)
#                         except Exception as e:  # 捕获所有异常
#                             log.error(f"Failed to read key {key}: {e}")
#                             corrupt_keys.append(key)

#             except Exception as e:
#                 log.error(f"Error opening HDF5 file {self.fname}: {e}")
#                 return

#             # 处理发现的损坏 keys
#             if corrupt_keys:
#                 log.warning(f"Corrupt keys detected: {corrupt_keys}, removing...")
#                 for key in corrupt_keys:
#                     try:
#                         with pd.HDFStore(self.fname, mode='a') as store:
#                             store.remove(key)
#                         log.info(f"Removed corrupted key: {key}")
#                     except Exception as e:
#                         log.error(f"Failed to remove key {key}: {e}")
#                         # 删除损坏的文件
#                         self._delete_file()

#     def _delete_file(self):
#         """删除损坏的文件"""
#         try:
#             if os.path.isfile(self.fname):
#                 os.remove(self.fname)
#                 log.info(f"文件删除成功: {self.fname}")
#             else:
#                 log.error(f"文件 {self.fname} 不存在，无法删除")
#         except Exception as e:
#             log.error(f"删除文件失败: {e}")
#             # 在这里添加一些逻辑，比如稍后再重试等

#     def _acquire_lock(self):
#         my_pid = os.getpid()
#         retries = 0
#         try:
#             while True:
#                 # 检查锁文件是否存在
#                 if os.path.exists(self._lock):
#                     with open(self._lock, "r") as f:
#                         content = f.read().strip()
#                     pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
#                     pid = int(pid_str) if pid_str.isdigit() else -1
#                     ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0
#                     elapsed = time.time() - ts
#                     total_wait = time.time() - self.start_time
#                     pid_alive = psutil.pid_exists(pid)

#                     if pid == my_pid:
#                         # 自己持有锁，直接清理并重建锁
#                         self.log.info(f"[Lock] 超时自解锁 (pid={pid}) (my_pid:{my_pid}), removing and reacquiring")
#                         try:
#                             os.remove(self._lock)
#                         except Exception as e:
#                             self.log.error(f"[Lock] failed to remove self lock: {e}")
#                         continue

#                     if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
#                         # 锁超时或持有锁进程不存在，可以删除锁
#                         self.log.warning(f"[Lock] 强制解超时锁 pid={pid} (my_pid:{my_pid}), removing {self._lock}")
#                         try:
#                             os.remove(self._lock)
#                         except Exception as e:
#                             self.log.error(f"[Lock] 强制解超时锁 失败: {e}")
#                         continue

#                     # 其他进程持有锁，等待
#                     retries += 1
#                     if retries % 3 == 0:
#                         self.log.info(f"[Lock] 重试:{retries} 等待 进程锁, pid={pid},(my_pid:{my_pid}), alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s")
#                     time.sleep(self.probe_interval)

#                 else:
#                     # 创建锁文件
#                     try:
#                         with open(self._lock, "w") as f:
#                             f.write(f"{my_pid}|{time.time()}")
#                         self.log.info(f"[Lock] 创建锁文件 {self._lock} by pid={my_pid}")
#                         return True
#                     except Exception as e:
#                         self.log.error(f"[Lock] 创建锁文件 失败: {e}")
#                         time.sleep(self.probe_interval)
#         except Exception as e:
#                 self.log.warning(f"[Lock] KeyboardInterrupt during lock acquire, releasing lock:{e}")
#                 self._release_lock()
#                 raise

#     def _forced_unlock(self):
#         my_pid = os.getpid()
#         retries = 0
#         while True:
#             # 检查锁文件是否存在
#             if os.path.exists(self._lock):
#                 with open(self._lock, "r") as f:
#                     content = f.read().strip()
#                 pid_str, ts_str = (content.split("|") + ["0", "0"])[:2]
#                 pid = int(pid_str) if pid_str.isdigit() else -1
#                 ts = float(ts_str) if ts_str.replace(".", "", 1).isdigit() else 0.0
#                 elapsed = time.time() - ts
#                 total_wait = time.time() - self.start_time
#                 pid_alive = psutil.pid_exists(pid)

#                 if pid == my_pid:
#                     # 自己持有锁，直接清理并重建锁
#                     self.log.info(f"[Lock] 超时解自锁 (pid={pid}) (my_pid:{my_pid}), removing and reacquiring")
#                     try:
#                         os.remove(self._lock)
#                         return True
#                     except Exception as e:
#                         self.log.error(f"[Lock] failed to remove self lock: {e}")
#                         if retries > 3:
#                             return False
#                     continue

#                 if not pid_alive or elapsed > self.lock_timeout or total_wait > self.max_wait:
#                     # 锁超时或持有锁进程不存在，可以删除锁
#                     self.log.warning(f"[Lock] 强制解超时锁 pid={pid} (my_pid:{my_pid}), removing {self._lock}")
#                     try:
#                         os.remove(self._lock)
#                         return True
#                     except Exception as e:
#                         self.log.error(f"[Lock] 强制解超时锁 失败: {e}")
#                         if retries > 3:
#                             return False
#                     continue

#                 # 其他进程持有锁，等待
#                 retries += 1
#                 if retries % 3 == 0:
#                     self.log.info(f"[Lock] exists, pid={pid},(my_pid:{my_pid}), alive={pid_alive}, elapsed={elapsed:.1f}s, total_wait={total_wait:.1f}s, retry={retries}")
#                 time.sleep(self.probe_interval)

#     def _wait_for_lock(self):
#         """读取模式等待锁释放"""
#         # start_time = time.time()
#         while os.path.exists(self._lock):
#             try:
#                 with open(self._lock, "r") as f:
#                     pid_str, ts_str = f.read().strip().split("|")
#                     lock_pid = int(pid_str)
#                     ts = float(ts_str)
#             except Exception:
#                 lock_pid = None
#                 ts = 0
#             elapsed = time.time() - ts
#             total_wait = time.time() - self.start_time
#             if elapsed > self.lock_timeout: 
#                 self._forced_unlock()
#             self.log.info(f"[{self.my_pid}] Waiting for lock held by pid={lock_pid}, elapsed={elapsed:.1f}s total_wait={total_wait:.1f}s")
#             time.sleep(self.probe_interval)

#     def _release_lock(self):
#         if os.path.exists(self._lock):
#             try:
#                 with open(self._lock, "r") as f:
#                     pid_in_lock = int(f.read().split("|")[0])
#                 if pid_in_lock == self.my_pid:
#                     os.remove(self._lock)
#                     self.log.info(f"[{self.my_pid}] Lock released: {self._lock}")
#             except Exception as e:
#                 self.log.error(f"[{self.my_pid}] Failed to release lock: {e}")


#     def close(self):
#         super().close()
#         # self._release_lock()

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if self.write_status:
#             try:
#                 self.close()
#                 super().__exit__(exc_type, exc_val, exc_tb)
#                 if self.mode != 'r':
#                     # ===== 压缩逻辑 =====
#                     h5_size = int(os.path.getsize(self.fname) / 1e6)
#                     h5_size_limit =  h5_size*2 if h5_size > 10 else 10
#                     if self.fname_o.find('tdx_all_df') >= 0 or self.fname_o.find('sina_MultiIndex_data') >= 0:
#                         h5_size = 40 if h5_size < 40 else h5_size
#                         new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit) if h5_size > self.big_H5_Size_limit else self.big_H5_Size_limit
#                     else:
#                         new_limit = ((h5_size / self.big_H5_Size_limit + 1) * self.big_H5_Size_limit) if h5_size > self.big_H5_Size_limit else h5_size_limit
                        
#                     read_ini_limit = cct.get_config_value(self.config_ini,self.fname_o,read=True)
#                     self.log.info(f"fname: {self.fname} h5_size: {h5_size} big_limit: {self.big_H5_Size_limit} conf:{read_ini_limit}")
#                     # if (read_ini_limit is  None and h5_size > self.big_H5_Size_limit) or cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
#                     if cct.get_config_value(self.config_ini, self.fname_o, h5_size, new_limit):
#                         if self.mode == 'r':
#                             self._acquire_lock()
#                         if os.path.exists(self.fname) and os.path.exists(self.temp_file):
#                             log.error(f"Remove tmp file exists: {self.temp_file}")
#                             os.remove(self.temp_file)
#                         os.rename(self.fname, self.temp_file)
#                         if cct.get_os_system() == 'mac':
#                             p = subprocess.Popen(
#                                 self.ptrepack_cmds % (self.complib, self.temp_file, self.fname),
#                                 shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
#                             )
#                         else:
#                             back_path = os.getcwd()
#                             os.chdir(self.basedir)
#                             pt_cmd = self.ptrepack_cmds % (
#                                 self.complib,
#                                 self.temp_file.split(self.basedir)[1],
#                                 self.fname.split(self.basedir)[1]
#                             )
#                             p = subprocess.Popen(pt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#                         p.wait()
#                         if p.returncode != 0:
#                             log.error(f"ptrepack error {p.communicate()}, src {self.temp_file}, dest {self.fname}")
#                         else:
#                             if os.path.exists(self.temp_file):
#                                 os.remove(self.temp_file)
#                         if cct.get_os_system() != 'mac':
#                             os.chdir(back_path)
#             finally:
#                 time.sleep(0.1)
#                 self._release_lock()
#                 self.log.info(f'clean:{self.fname}')
#         else:
#             self.close()
#             super().__exit__(exc_type, exc_val, exc_tb)


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





class SafeHDFWriter:
    def __init__(self, final_path):
        self.final = Path(final_path)
        self.tmp = self.final.with_suffix(self.final.suffix + ".tmp")

    def __enter__(self):
        # 保留旧数据
        if self.final.exists():
            shutil.copy2(self.final, self.tmp)
        return self.tmp

    def __exit__(self, exc_type, exc_val, exc_tb):

        # 写入异常直接丢弃
        if exc_type is not None:
            if self.tmp.exists():
                self.tmp.unlink()
            return False

        # 校验失败直接丢弃
        if not validate_h5(self.tmp):
            if self.tmp.exists():
                self.tmp.unlink()
            raise RuntimeError("HDF5 校验失败，放弃写入")

        # 原子替换
        os.replace(self.tmp, self.final)

def write_hdf_db_safe(fname, df, table='all', index=False, complib='blosc', baseCount=500, append=True, MultiIndex=False, rewrite=False, showtable=False):
    if df is None or df.empty: return False
    if 'code' in df.columns: df = df.set_index('code')
    df = df.fillna(0)
    df = df[~df.index.duplicated(keep='first')]
    if not MultiIndex: df['timel'] = time.time()
    dd = df.dtypes.to_frame()
    if 'object' in dd.values:
        cols = dd[dd == 'object'].dropna().index.tolist()
        df[cols] = df[cols].astype(str)
        df.index = df.index.astype(str)
    df = df.fillna(0)
    df = cct.reduce_memory_usage(df, verbose=False)
    fname = Path(fname)
    with SafeHDFWriter(fname) as tmp:
        with SafeHDFStore(tmp, mode='a') as h5:
            if '/' + table in h5.keys(): h5.remove(table)
            if not MultiIndex:
                h5.put(table, df, format='table', append=False, complib=complib, data_columns=True)
            else:
                h5.put(table, df, format='table', index=False, complib=complib, data_columns=True, append=True)
            h5.flush()
    log.info("Safe HDF write OK => %s[%s] rows:%s", fname, table, len(df))
    return True



def write_hdf_db_newbug(fname, df, table='all', index=False, complib='blosc', baseCount=500,
                 append=True, MultiIndex=False, rewrite=False, showtable=False):
#     [12-24 09:45:12] ERROR:data_utils.py(fetch_and_process:395): resample: d Error in background process: Setting a MultiIndex dtype to anything other than object is not supported
# Traceback (most recent call last):
#   File "data_utils.py", line 337, in fetch_and_process
#   File "JSONData\tdx_data_Day.py", line 3306, in getSinaAlldf
#   File "JSONData\sina_data.py", line 451, in all
#   File "JSONData\sina_data.py", line 900, in get_stock_data
#   File "JSONData\sina_data.py", line 1052, in format_response_data
#   File "JSONData\tdx_hdf5_api.py", line 1093, in write_hdf_db
#   File "pandas\core\indexes\multi.py", line 3727, in astype
# TypeError: Setting a MultiIndex dtype to anything other than object is not supported
    time_t = time.time()

    if df is None or df.empty:
        log.warning("write_hdf_db: df is None or empty, skip write")
        return pd.DataFrame()  # 返回空 DF 避免 NoneType

    # 处理索引
    if 'code' in df.columns and not MultiIndex:
        df = df.set_index('code')

    df = df.fillna(0)
    df = df[~df.index.duplicated(keep='first')]

    tmpdf = pd.DataFrame()

    with SafeHDFStore(fname, mode='a') as store:
        if store is None:
            log.error("HDF5 store is None: %s", fname)
            return False

        table_key = '/' + table
        keys = store.keys()
        if showtable:
            log.info("fname: %s keys:%s", fname, keys)
            print(f"fname: {fname} keys:{keys}")

        # 读取已有数据
        if append and table_key in keys:
            try:
                tmpdf = store.get(table)
                if tmpdf is None or not isinstance(tmpdf, pd.DataFrame):
                    log.warning("HDF5 key %s invalid or None, resetting tmpdf to empty", table_key)
                    tmpdf = pd.DataFrame()
                else:
                    tmpdf = tmpdf[~tmpdf.index.duplicated(keep='first')]
            except Exception as e:
                log.error("Error reading HDF5 key %s: %s", table_key, e)
                tmpdf = pd.DataFrame()

        # MultiIndex 或普通 DataFrame 合并逻辑
        if append and not tmpdf.empty:
            # MultiIndex 分支
            if MultiIndex:
                try:
                    multi_code = tmpdf.index.get_level_values('code').unique().tolist()
                    df_multi_code = df.index.get_level_values('code').unique().tolist()
                    dratio = cct.get_diff_dratio(multi_code, df_multi_code)
                    if dratio < ct.dratio_limit:
                        comm_code = list(set(df_multi_code) & set(multi_code))
                        if comm_code:
                            inx_key = comm_code[np.random.randint(0, len(comm_code))]
                            if inx_key in df.index.get_level_values('code'):
                                now_time = df.loc[inx_key].index[-1]
                                tmp_time = tmpdf.loc[inx_key].index[-1]
                                if now_time == tmp_time:
                                    log.debug("%s %s Multi out %s hdf5:%s No Write!!!" %
                                              (fname, table, inx_key, now_time))
                                    return False
                    elif dratio == 1:
                        log.info("newData ratio: %s all:%s", dratio, len(df))
                    else:
                        log.debug("dratio:%s main:%s new:%s %s %s Multi All Write" %
                                  (dratio, len(multi_code), len(df_multi_code), fname, table))
                except Exception as e:
                    log.error("MultiIndex merge error: %s", e)
            else:
                # 普通 DataFrame 合并逻辑
                try:
                    if 'code' in tmpdf.columns:
                        tmpdf = tmpdf.set_index('code')
                    if 'code' in df.columns:
                        df = df.set_index('code')

                    diff_columns = set(df.columns) - set(tmpdf.columns)
                    if diff_columns:
                        log.error("columns diff:%s", diff_columns)

                    limit_t = time.time()
                    df['timel'] = limit_t
                    df = cct.combine_dataFrame(tmpdf, df, col=None, append=append)

                    if not append:
                        df['timel'] = time.time()
                    elif fname == 'powerCompute':
                        o_time = df[df.timel < limit_t].timel.tolist()
                        o_time = sorted(set(o_time), reverse=False)
                        if len(o_time) >= ct.h5_time_l_count:
                            o_time = [time.time() - t_x for t_x in o_time]
                            o_timel = len(o_time)
                            o_time = np.mean(o_time)
                            if o_time > ct.h5_power_limit_time:
                                df['timel'] = time.time()
                                log.error("%s %s o_time:%.1f timel:%s" %
                                          (fname, table, o_time, o_timel))
                    log.info("read hdf merge time: %.2f", time.time() - time_t)
                except Exception as e:
                    log.error("DataFrame merge error: %s", e)

        # Object 类型列处理
        obj_cols = df.select_dtypes(include=['object']).columns.tolist()
        if obj_cols:
            df[obj_cols] = df[obj_cols].astype(str)
        df.index = df.index.astype(str)
        df = df.fillna(0)

        # 写入 HDF5
        try:
            if table_key in keys and rewrite:
                store.remove(table)
            store.put(table, df, format='table', index=not MultiIndex, append=False,
                      complib=complib, data_columns=True)
            store.flush()
        except Exception as e:
            log.error("write_hdf_db HDF5 put error: %s", e)
            return False

    log.info("write_hdf_db done: table=%s, rows=%d, time=%.2f",
             table, len(df), time.time() - time_t)
    return df

# def read_hdf_safe(store, table_name, chunk_size=1000):
#     dfs = []
#     start = 0
#     while True:
#         try:
#             df_chunk = store.select(table_name, start=start, stop=start+chunk_size)
#             if df_chunk.empty:
#                 break
#             dfs.append(df_chunk)
#             start += chunk_size
#         except tables.exceptions.HDF5ExtError as e:
#             print(f"Chunk read error at rows {start}-{start+chunk_size}: {e}")
#             start += chunk_size  # 跳过损坏 chunk
#     if dfs:
#         return pd.concat(dfs)
#     else:
#         return pd.DataFrame()

# def safe_load_table(store, table_name, chunk_size=1000,MultiIndex=False,complib='blosc',readonly=False):
#     """
#     尝试读取 HDF5 table，如果读取失败，则逐块读取。
#     返回 DataFrame。
#     """
#     try:
#         # 直接读取整个 table
#         df = store[table_name]
#         df = df[~df.index.duplicated(keep='first')]
#         return df
#     except tables.exceptions.HDF5ExtError as e:
#         log.error(f"{table_name} read error: {e}, attempting chunked read...")
#         # 逐块读取
#         import ipdb;ipdb.set_trace()

#         dfs = []
#         start = 0
#         while True:
#             try:
#                 storer = store.get_storer(table_name)
#                 if not storer.is_table:
#                     raise RuntimeError(f"{table_name} is not a table format")
#                 df_chunk = store.select(table_name, start=start, stop=start+chunk_size)
#                 if df_chunk.empty:
#                     break
#                 dfs.append(df_chunk)
#                 start += chunk_size
#             except tables.exceptions.HDF5ExtError:
#                 # 跳过损坏块
#                 print(f"Skipping corrupted chunk {start}-{start+chunk_size}")
#                 start += chunk_size
#         if not readonly and dfs:
#             df = pd.concat(dfs)
#             df = df[~df.index.duplicated(keep='first')]
#             rebuild_table(store, table_name, df, MultiIndex=MultiIndex, complib=complib)
#             return df
#         else:
#             print(f"All chunks of {table_name} are corrupted")
#             return pd.DataFrame()

def quarantine_hdf_file(fname, reason, rebuild_func=None):
    log.critical(f"[HDF QUARANTINE] {fname}, reason={reason}")

    # 1. 关闭残留句柄（尽量）
    try:
        tables.file._open_files.close_all()
    except Exception:
        pass

    # 2. 删除文件
    try:
        if os.path.exists(fname):
            os.remove(fname)
            log.critical(f"[HDF REMOVED] {fname}")
    except Exception as e:
        log.error(f"Failed to remove {fname}: {e}")
        return

    # 3. 重建（可选）
    if rebuild_func:
        try:
            log.critical(f"[HDF REBUILD] {fname}")
            rebuild_func(fname)
        except Exception as e:
            log.error(f"Rebuild failed for {fname}: {e}")


def safe_load_table(store, table_name, chunk_size=1000,
                    MultiIndex=False, complib='blosc',
                    readonly=False):
    """
    安全读取 HDF5 table：
    - metadata / UnImplemented → 直接失败
    - HDF5ExtError → 尝试 chunk 读取
    """

    # ---------- 1. 尝试整表读取 ----------
    try:
        df = store[table_name]
        return df[~df.index.duplicated(keep='first')]

    # ---------- 2. 结构级损坏（不可恢复） ----------
    except (AttributeError, KeyError, TypeError) as e:
        log.critical(
            f"HDF STRUCTURE BROKEN: {table_name}, "
            f"type={type(e).__name__}, err={e}"
        )
        raise e

    # ---------- HDF5 底层错误 ----------
    except tables.exceptions.HDF5ExtError as e:
        log.error(
            f"{table_name} HDF5ExtError: {e}, "
            f"attempting chunked read..."
        )
        # ↓ 继续走 chunk fallback

    # ---------- 4. 文件级物理损坏 ----------
    except (OSError, IOError, UnicodeDecodeError) as e:
        log.critical(
            f"HDF FILE BROKEN: {table_name}, "
            f"type={type(e).__name__}, err={e}"
        )
        return pd.DataFrame()

    # ---------- 5. chunk fallback ----------
    dfs = []
    start = 0

    try:
        storer = store.get_storer(table_name)
        if not storer.is_table:
            log.error(f"{table_name} is not table format")
            return pd.DataFrame()
    except Exception as e:
        log.error(f"get_storer failed for {table_name}: {e}")
        return pd.DataFrame()

    while True:
        try:
            df_chunk = store.select(
                table_name,
                start=start,
                stop=start + chunk_size
            )
            if df_chunk.empty:
                break
            dfs.append(df_chunk)
            start += chunk_size

        except tables.exceptions.HDF5ExtError:
            log.warning(
                f"Skipping corrupted chunk "
                f"{start}-{start + chunk_size}"
            )
            start += chunk_size

        except Exception as e:
            log.error(
                f"Fatal error reading chunk {start}: {e}"
            )
            break

    if not dfs:
        log.error(f"All chunks of {table_name} are unreadable")
        return pd.DataFrame()

    df = pd.concat(dfs)
    df = df[~df.index.duplicated(keep='first')]

    # ---------- 6. 是否重建 ----------
    if not readonly:
        log.warning(f"Rebuilding table {table_name} from chunks")
        rebuild_table(
            store, table_name, df,
            MultiIndex=MultiIndex,
            complib=complib
        )

    return df


def rebuild_table(store, table_name, new_df,MultiIndex=False,complib='blosc'):
    """
    删除旧 table 并重建
    """
    # with SafeHDFStore(fname, mode='a') as store:
    if '/' + table_name in store.keys():
        log.error(f"Removing corrupted table {table_name}")
        store.remove(table_name)
    if not new_df.empty:
        # store.put(table_name, new_df, format='table',complib=complib, data_columns=True)
        if not MultiIndex:
            store.put(table_name, new_df, format='table', append=False, complib=complib, data_columns=True)
        else:
            store.put(table_name, new_df, format='table', index=False, complib=complib, data_columns=True, append=False)
        store.flush()

def safe_remove_h5_table(h5, table, max_retry=5, retry_interval=0.2):
    """安全删除 HDF5 表，节点被占用时等待重试"""
    for attempt in range(max_retry):
        try:
            if '/' + table in list(h5.keys()):
                h5.remove(table)
            return True
        except Exception as e:
            # 节点被占用，等待
            time.sleep(retry_interval)
    # 尝试多次仍失败
    logger.warning(f"Failed to remove HDF5 table {table} after {max_retry} attempts")
    return False

def write_hdf_db(fname, df, table='all', index=False, complib='blosc', baseCount=500, append=True, MultiIndex=False,rewrite=False,showtable=False):

    if 'code' in df.columns:
        df=df.set_index('code')
    time_t=time.time()
    df=df[~df.index.duplicated(keep='first')]
    # df=prepare_df_for_hdf5(df)
    df=df.fillna(0)
    code_subdf=df.index.tolist()
    global RAMDISK_KEY
    if not RAMDISK_KEY < 1:
        return df

    if not MultiIndex:
        df['timel']=time.time()
        
    if not rewrite:
        if df is not None and not df.empty and table is not None:
            tmpdf=[]
            # try:
            #     with SafeHDFStore(fname,mode='a') as store:
            #         if store is not None:
            #             log.debug(f"fname: {(fname)} keys:{store.keys()}")
            #             if showtable:
            #                 print(f"fname: {(fname)} keys:{store.keys()}")
            #             if '/' + table in list(store.keys()):
            #                 tmpdf=store[table]
            #                 tmpdf = tmpdf[~tmpdf.index.duplicated(keep='first')]
            # except tables.exceptions.HDF5ExtError as e:
            #     print(f"{table_name} read error: {e}")
            # 使用示例
            try:
                with SafeHDFStore(fname, mode='a') as store:
                    if store is not None:
                        log.debug(f"fname: {(fname)} keys:{store.keys()}")
                        if showtable:
                            print(f"fname: {(fname)} keys:{store.keys()}")
                        if '/' + table in list(store.keys()):
                            tmpdf = safe_load_table(store, table, chunk_size=5000,MultiIndex=MultiIndex,complib=complib)
                            if tmpdf.empty:
                                log.info(f"{table} : table is corrupted, will rebuild after fetching new data")
                                # tmpdf = tmpdf[~tmpdf.index.duplicated(keep='first')]
            except Exception as e:
                log.error(f"Failed to open store {fname}: {e}")
                try:
                    # 强力恢复模式：如果打开失败，直接尝试清理相关文件
                    if os.path.exists(fname):
                        # 尝试解锁
                        try:
                            if hasattr(SafeHDFStore, '_release_lock'):
                                # 静态调用很难，这里简化为清理 lock 文件
                                lock_file = fname + ".lock"
                                if os.path.exists(lock_file):
                                    os.remove(lock_file)
                        except: pass
                        
                        os.remove(fname)
                        log.warning(f"Deleted corrupted HDF5 file after open failure: {fname}")
                except Exception as del_e:
                    log.error(f"Failed to delete corrupted file {fname}: {del_e}")

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
            # df=cct.reduce_memory_usage(df,verbose=False)
            log.info(f'df.shape:{df.shape}')
            if h5 is not None:
                if '/' + table in list(h5.keys()):
                    if not MultiIndex:
                        safe_remove_h5_table(h5, table)
                        h5.put(table, df, format='table', append=False, complib=complib, data_columns=True)
                    else:
                        if rewrite:
                            safe_remove_h5_table(h5, table)
                        elif len(h5[table]) < 1:
                            safe_remove_h5_table(h5, table)
                        h5.put(table, df, format='table', index=False, complib=complib, data_columns=True, append=True)

                    # if not MultiIndex:
                    #     h5.remove(table)
                    #     h5.put(table, df, format='table', append=False, complib=complib, data_columns=True)
                    #     # h5.put(table, df, format='table',index=False, data_columns=True, append=False)
                    # else:
                    #     if rewrite:
                    #         h5.remove(table)
                    #     elif len(h5[table]) < 1:
                    #         h5.remove(table)
                    #     h5.put(table, df, format='table', index=False, complib=complib, data_columns=True, append=True)
                    #     # h5.append(table, df, format='table', append=True,data_columns=True, dropna=None)
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


def load_hdf_db_timed_ctx(fname, table='all', code_l=None, timelimit=True, index=False,
                limit_time=ct.h5_limit_time, dratio_limit=ct.dratio_limit,
                MultiIndex=False, showtable=False):
    """
    优化版 load_hdf_db — 保留原有行为与参数，添加 timed_ctx 自动统计耗时
    """
    time_t = time.time()
    global RAMDISK_KEY, INIT_LOG_Error
    df = None
    dd = None

    # RAMDISK_KEY 非 0 时直接返回
    if not RAMDISK_KEY < 1:
        return None

    # -------------------------
    # 打开 HDF5 并读取表
    # -------------------------
    with timed_ctx("hdf_open_and_read"):
        try:
            with SafeHDFStore(fname, mode='r') as store:
                if store is not None:
                    keys = store.keys()
                    log.debug("HDF5 file: %s, keys: %s", fname, keys)
                    if showtable:
                        log.debug("HDF5 file contents keys: %s", keys)
                    table_key = '/' + table
                    if table_key in keys:
                        dd = store.get(table)
                        log.debug("Loaded DataFrame shape: %s", dd.shape)
                    else:
                        dd = pd.DataFrame()
                        log.warning("Table key not found: %s", table_key)
                else:
                    dd = pd.DataFrame()
                    log.error("SafeHDFStore returned None for file: %s", fname)
        except Exception as e:
            dd = pd.DataFrame()
            log.exception("load_hdf_db exception for file %s, table %s", fname, table)

    # -------------------------
    # 按 code_l 过滤
    # -------------------------
    with timed_ctx("filter_by_code"):
        if code_l is not None and not dd.empty:
            try:
                if not MultiIndex:
                    dif_co = list(dd.index.intersection(code_l))
                    dd = dd.loc[dif_co] if dif_co else dd.iloc[0:0]
                else:
                    mask = dd.index.get_level_values('code').isin(code_l)
                    dd = dd.loc[mask]
            except Exception as e:
                log.exception("filter_by_code failed: %s", e)
                dd = pd.DataFrame()

    # -------------------------
    # timelimit 检查逻辑
    # -------------------------
    with timed_ctx("timelimit_check"):
        if timelimit and not dd.empty and not (cct.is_trade_date() and 1130 < cct.get_now_time_int() < 1300):
            o_time = []
            if 'timel' in dd.columns:
                timel_vals = dd.loc[dd['timel'] != 0, 'timel'].values
                if timel_vals.size > 0:
                    unique_timel = np.unique(timel_vals)
                    now_t = time.time()
                    o_time = [now_t - float(t) for t in unique_timel]
                    o_time.sort()
            l_time = np.mean(o_time) if o_time else 0.0

            dratio = 0.0
            if 'ticktime' in dd.columns and 'kind' not in dd.columns:
                try:
                    late_count = int((dd['ticktime'] >= "15:00:00").sum())
                except Exception:
                    late_count = 0
                dratio = (float(len(dd)) - float(late_count)) / float(len(dd)) if len(dd) > 0 else 0.0

            return_hdf_status = (not cct.get_work_time() and dratio < dratio_limit) or \
                                (cct.get_work_time() and l_time < limit_time)
            if not return_hdf_status:
                dd = dd.iloc[0:0]

    # -------------------------
    # MultiIndex 或去重
    # -------------------------
    with timed_ctx("multiindex_drop"):
        if MultiIndex and not dd.empty:
            try:
                dd = dd.drop_duplicates()
            except Exception:
                pass

    # -------------------------
    # 填充空值 & timel 核心字段
    # -------------------------
    with timed_ctx("post_process"):
        if dd is not None and not dd.empty:
            try:
                dd.fillna(0, inplace=True)
            except Exception:
                dd = dd.fillna(0)
            if 'timel' in dd.columns:
                try:
                    first_timel = float(np.min(np.unique(dd['timel'].values)))
                    dd['timel'] = first_timel
                except Exception:
                    pass

    # -------------------------
    # 去重 & MultiIndex 检查
    # -------------------------
    with timed_ctx("deduplicate_index"):
        if dd is not None and not dd.empty:
            try:
                dd = dd[~dd.index.duplicated(keep='last')]
            except Exception:
                pass

    # -------------------------
    # 内存优化
    # -------------------------
    # with timed_ctx("reduce_memory"):
    #     try:
    #         df = cct.reduce_memory_usage(dd)
    #     except Exception:
    #         df = dd

    log.debug("load_hdf_time total:%0.2f s", (time.time() - time_t))
    return dd



# def load_hdf_db_no_timed_ctx(fname, table='all', code_l=None, timelimit=True, index=False,
def load_hdf_db(fname, table='all', code_l=None, timelimit=True, index=False,
                limit_time=ct.h5_limit_time, dratio_limit=ct.dratio_limit,
                MultiIndex=False, showtable=False):
    """
    优化版 load_hdf_db — 保留原有行为与参数，仅优化性能与日志级别
    """
    time_t = time.time()
    global RAMDISK_KEY, INIT_LOG_Error

    # 与原逻辑一致：RAMDISK_KEY 非 0 时直接返回 None
    if not RAMDISK_KEY < 1:
        return None

    df = None
    dd = None
    # -------------------------
    # When filtering by code list
    # -------------------------
    if code_l is not None:
        delete_corrupt_file = False
        if table is not None:
            with SafeHDFStore(fname, mode='r') as store:
                if store is not None:
                    keys = store.keys()
                    
                    try:
                        table_key = '/' + table
                        if table_key in keys:
                            obj = store.get(table)
                            if isinstance(obj, pd.DataFrame):
                                dd = obj
                            else:
                                dd = pd.DataFrame()
                        else:
                            dd = pd.DataFrame()

                    except Exception as e:
                        log.error(f"load_hdf_db error {fname}/{table}: {e}")
                        dd = pd.DataFrame()
                        # 判定是否为严重损坏
                        if isinstance(e, AttributeError) or "UnImplemented" in str(e) or "HDF5ExtError" in str(type(e).__name__):
                             delete_corrupt_file = True
                else:
                    dd = pd.DataFrame()
        
        # 退出 with 块后执行清理
        if delete_corrupt_file:
            log.critical(f"Aggressive cleanup for corrupted file: {fname}")
            try:
                import tables
                tables.file._open_files.close_all()
            except: pass
            
            try:
                if os.path.exists(fname):
                    os.remove(fname)
                    log.warning(f"Deleted corrupted file: {fname}")
                lock_f = fname + ".lock"
                if os.path.exists(lock_f):
                    os.remove(lock_f)
            except Exception as del_e:
                log.error(f"Cleanup failed: {del_e}")


        if dd is not None and len(dd) > 0:
            if not MultiIndex:
                # 若 index 模式下需要映射 code（保持原行为）
                if index:
                    code_l = list(map((lambda x: str(1000000 - int(x))
                                       if x.startswith('0') else x), code_l))

                # 使用 pandas Index.intersection 替代 set 交集（更快）
                try:
                    dif_index = dd.index.intersection(code_l)
                except Exception:
                    # 兼容性回退（极少见）
                    dif_index = pd.Index(list(set(dd.index) & set(code_l)))

                # 保持原变量名 dif_co（列表形式）以兼容后续逻辑
                dif_co = list(dif_index)

                # try:
                #     # 强制统一类型为字符串
                #     dd_list = dd.index.tolist()
                #     dd_set   = set(map(str, dd_list))
                #     code_set = set(map(str, code_l))
                #     dif_index = code_set - dd_set
                # except Exception:
                #     # 兼容性回退（极少见）
                #     dif_index = pd.Index(list(set(dd_index_str) & set(code_l_str)))

                # # 保持原变量名 dif_co（列表形式）以兼容后续逻辑

                # dif_co = list(dif_index)

                if len(code_l) > 0:
                    dratio = (float(len(code_l)) - float(len(dif_co))) / float(len(code_l))
                else:
                    dratio = 0.0

                log.debug("find all:%s :%s %0.2f", len(code_l), len(code_l) - len(dif_co), dratio)

                # 与原逻辑相同的 timelimit 分支
                if not (cct.is_trade_date() and 1130 < cct.get_now_time_int() < 1300) and timelimit and len(dd) > 0:
                    # 先按 dif_co 筛选（避免对整表重复计算）
                    if len(dif_co) > 0:
                        # 这会返回新 DataFrame（必要时会复制）
                        dd = dd.loc[dif_co]
                    else:
                        dd = dd.iloc[0:0]

                    # 计算 o_time（保留最近唯一 timel 的偏移列表）
                    o_time = []
                    if 'timel' in dd.columns:
                        timel_vals = dd.loc[dd['timel'] != 0, 'timel'].values
                        if timel_vals.size > 0:
                            unique_timel = np.unique(timel_vals)
                            # 计算距离现在的秒数（与原逻辑一致）
                            now_t = time.time()
                            o_time = [now_t - float(t) for t in unique_timel]
                            o_time.sort()  # 原代码使用 sorted(..., reverse=False)

                    if len(dd) > 0:
                        l_time = np.mean(o_time) if len(o_time) > 0 else 0.0
                        # dd = normalize_ticktime(dd)
                        # log.info(f'dd normalize_ticktime:{dd.ticktime[0]}')
                        # 原先在极高命中率时用 ticktime 重新计算 dratio
                        # print(f"ticktime: {dd['ticktime'][:5]} , l_time: {l_time} limit_time: {limit_time}")
                        if len(code_l) / len(dd) > 0.95 and 'ticktime' in dd.columns and 'kind' not in dd.columns:
                            try:
                                late_count = int((dd['ticktime'] >= "15:00:00").sum())
                            except Exception:
                                # 回退到 query（兼容性）
                                try:
                                    late_count = len(dd.query('ticktime >= "15:00:00"'))
                                except Exception:
                                    late_count = 0
                            dratio = (float(len(dd)) - float(late_count)) / float(len(dd)) if len(dd) > 0 else 0.0
                            return_hdf_status = (not cct.get_work_time() and dratio < dratio_limit) or (cct.get_work_time() and l_time < limit_time)
                        else:
                            return_hdf_status = not cct.get_work_time() or (cct.get_work_time() and l_time < limit_time)

                        if return_hdf_status:
                            # 注意：dd 已经被筛选为 dif_co，直接使用 dd 即可
                            df = dd
                            log.debug("return hdf: %s timel:%s l_t:%s hdf ok:%s", fname, len(o_time), l_time, len(df))
                    else:
                        log.error("%s %s o_time:%s %s", fname, table, len(o_time), o_time[:3] if len(o_time) >= 3 else o_time)

                    # 记录一下（调试级别）
                    if 'o_time' in locals() and o_time:
                        log.debug('fname:%s sample_o_time:%s', fname, o_time[:5])
                else:
                    # 非 timelimit 分支，直接按 dif_co 返回（与原逻辑一致）
                    df = dd.loc[dif_co] if len(dif_co) > 0 else dd.iloc[0:0]

                # dratio 超限处理（保持原行为）
                if dratio > dratio_limit:
                    if len(code_l) > ct.h5_time_l_count * 10 and INIT_LOG_Error < 5:
                        log.error("dratio_limit fn:%s cl:%s h5:%s don't find:%s dra:%0.2f log_err:%s",
                                  fname, len(code_l), len(dd), len(code_l) - len(dif_co), dratio, INIT_LOG_Error)
                        return None

            else:
                # MultiIndex 情况按原逻辑：按 level='code' 过滤
                try:
                    df = dd.loc[dd.index.isin(code_l, level='code')]
                except Exception:
                    # 回退：使用 boolean mask
                    mask = dd.index.get_level_values('code').isin(code_l)
                    df = dd.loc[mask]
        else:
            log.error("%s is not find %s", fname, table)

    # -------------------------
    # When not filtering by code list (code_l is None)
    # -------------------------
    else:
        if table is not None:
            # with SafeHDFStore(fname, mode='r') as store:
            #     if store is not None:
            #         log.debug("fname: %s keys:%s", fname, store.keys())
            #         if showtable:
            #             log.debug("keys:%s", store.keys())
            #         try:
            #             table_key = '/' + table
            #             if table_key in store.keys():
            #                 # 读取整表（尽量避免额外 copy）
            #                 dd = safe_load_table(store, table, chunk_size=5000,MultiIndex=MultiIndex,readonly=True)
            #             else:
            #                 dd = pd.DataFrame()
            #         except AttributeError as e:
            #             # 与原逻辑保持一致：在异常时关闭 store 并记录错误
            #             try:
            #                 store.close()
            #             except Exception:
            #                 pass
            #             log.error("AttributeError:%s %s", fname, e)
            #             dd = pd.DataFrame()
            #         except Exception as e:
            #             log.error("Exception:%s %s", fname, e)
            #             dd = pd.DataFrame()
            dd = pd.DataFrame()
            try:
                with SafeHDFStore(fname, mode='r') as store:
                    if store is None:
                        raise AttributeError("SafeHDFStore open failed")

                    log.debug("fname: %s keys:%s", fname, store.keys())
                    if showtable:
                        log.debug("keys:%s", store.keys())

                    table_key = '/' + table
                    if table_key in store.keys():
                        dd = safe_load_table(
                            store,
                            table,
                            chunk_size=5000,
                            MultiIndex=MultiIndex,
                            readonly=True
                        )
                    else:
                        dd = pd.DataFrame()

            # ---------- 这里是关键 ----------
            except AttributeError as e:
                log.critical("HDF STRUCTURE BROKEN: %s %s", fname, e)
                # 1. 确保 PyTables 句柄释放
                try:
                    import tables
                    tables.file._open_files.close_all()
                except Exception:
                    pass
                # 2. 删除损坏文件
                try:
                    _ram_fname = cct.get_ramdisk_path(f'{fname}.h5')
                    if os.path.exists(_ram_fname):
                        os.remove(_ram_fname)
                        log.critical("HDF REMOVED: %s", _ram_fname)
                    else:
                        log.critical("HDF %s not exists", _ram_fname)
                except Exception as e2:
                    log.error("Failed to remove %s: %s", fname, e2)
                dd = pd.DataFrame()
            except Exception as e:
                # ⚠️ 普通异常不删文件
                log.error("Exception:%s %s", fname, e)
                dd = pd.DataFrame()

            if dd is not None and len(dd) > 0:
                if not (cct.is_trade_date() and 1130 < cct.get_now_time_int() < 1300) and timelimit:
                    # 计算 unique timel 并求平均延迟
                    o_time = []
                    if 'timel' in dd.columns:
                        timel_vals = dd.loc[dd['timel'] != 0, 'timel'].values
                        if timel_vals.size > 0:
                            unique_timel = np.unique(timel_vals)
                            now_t = time.time()
                            o_time = [now_t - float(t) for t in unique_timel]
                            o_time.sort()
                    if len(o_time) > 0:
                        l_time = np.mean(o_time)
                    else:
                        l_time = 0.0

                    # 判断是否返回 hdf（与原逻辑一致）
                    if 'ticktime' in dd.columns and 'kind' not in dd.columns:
                        try:
                            late_count = int((dd['ticktime'] >= "15:00:00").sum())
                        except Exception:
                            try:
                                late_count = len(dd.query('ticktime >= "15:00:00"'))
                            except Exception:
                                late_count = 0
                        dratio = (float(len(dd)) - float(late_count)) / float(len(dd)) if len(dd) > 0 else 0.0
                        return_hdf_status = (not cct.get_work_time() and dratio < dratio_limit) or (cct.get_work_time() and l_time < limit_time)
                    else:
                        return_hdf_status = not cct.get_work_time() or (cct.get_work_time() and l_time < limit_time)

                    log.debug("return_hdf_status:%s time:%0.2f", return_hdf_status, l_time)
                    if return_hdf_status:
                        log.debug("return hdf5 data:%s o_time_count:%s", len(dd), len(o_time))
                        df = dd
                    else:
                        log.debug("no return time hdf5:%s", len(dd))
                else:
                    df = dd
            else:
                log.error("%s is not find %s", fname, table)
        else:
            log.error("%s / table is Init None:%s", fname, table)

    # -------------------------
    # Post-process & cleanup (与原逻辑保持一致)
    # -------------------------
    if df is not None and len(df) > 0:
        # 保持原来行为：填充空值
        # 使用 inplace 以减少一次复制
        try:
            df.fillna(0, inplace=True)
        except Exception:
            df = df.fillna(0)

        # 保持原来把 timel 设为最早唯一 timel 的行为
        if 'timel' in df.columns:
            try:
                time_list = np.unique(df['timel'].values)
                if time_list.size > 0:
                    # pick the smallest (与 sorted(set(...)) 的结果一致)
                    first_timel = float(np.min(time_list))
                    df['timel'] = first_timel
                    log.debug("load hdf times sample:%s", time_list[:3].tolist() if hasattr(time_list, 'tolist') else time_list)
            except Exception:
                pass

    log.debug("load_hdf_time:%0.2f", (time.time() - time_t))

    # 保持原来去重与 MultiIndex 处理
    if df is not None:
        try:
            df = df[~df.index.duplicated(keep='last')]
        except Exception:
            # 若 index 操作失败则忽略
            pass

        if fname.find('MultiIndex') > 0 and 'volume' in df.columns:
            count_drop = len(df)
            try:
                df = df.drop_duplicates()
            except Exception:
                # fallback: no-op
                pass
            try:
                dratio_check = round((float(len(df))) / float(count_drop), 2) if count_drop > 0 else 0.0
                log.debug("all:%s  drop:%s  dratio:%.2f", int(count_drop / 100), int(len(df) / 100), dratio_check)
                if dratio_check < 0.8:
                    log.error("MultiIndex drop_duplicates:%s %s dr:%s", count_drop, len(df), dratio_check)
                    if isinstance(df.index, pd.MultiIndex):
                        write_hdf_db(fname, df, table=table, index=index, MultiIndex=True, rewrite=True)
            except Exception:
                pass

    return df
    # 与原函数保持一致：返回 reduce_memory_usage(df)
    # try:
    #     return cct.reduce_memory_usage(df)
    # except Exception:
        # return df


def load_hdf_db_src_OK(fname, table='all', code_l=None, timelimit=True, index=False, limit_time=ct.h5_limit_time, dratio_limit=ct.dratio_limit,MultiIndex=False,showtable=False):
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
        if table is not None:
            with SafeHDFStore(fname,mode='r') as store:
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

                            if 'ticktime' in dd.columns and 'kind' not in dd.columns:
                                # len(dd) ,len(dd.query('ticktime >= "15:00:00"'))
                                dratio=(float(len(dd)) - float(len(dd.query('ticktime >= "15:00:00"')))) / float(len(dd))
                                return_hdf_status=(not cct.get_work_time() and dratio < dratio_limit) or (cct.get_work_time() and l_time < limit_time)
                            else:  
                                return_hdf_status=not cct.get_work_time() or (
                                    cct.get_work_time() and l_time < limit_time)


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
                log.error("%s is not find %s" % (fname, table))
        else:
            log.error("%s / table is Init None:%s"%(fname, table))

    if df is not None and len(df) > 0:
        df=df.fillna(0)
        if 'timel' in df.columns:
            time_list=df.timel.tolist()
            time_list=sorted(set(time_list))
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

    return  df
    # return  cct.reduce_memory_usage(df)



# def compact_hdf5_file(old_path, new_path=None, key="all_30/table"):
#     if new_path is None:
#         new_path = old_path.replace(".h5", "_clean.h5")
#     df = pd.read_hdf(old_path, key=key)
#     df.to_hdf(new_path, key=key, mode="w", format="table", complib="blosc", complevel=9)
#     old_size = os.path.getsize(old_path) / 1024**2
#     new_size = os.path.getsize(new_path) / 1024**2
#     print(f"Compacted {old_path}: {old_size:.1f} MB → {new_size:.1f} MB")
#     return new_path

def write_tdx_all_df(file_path: str, fetch_all_df_func=None):
    """
    重建 tdx_all_df HDF5 文件（例如 all_900 数据）。
    fetch_all_df_func: 外部提供的数据获取函数，返回 DataFrame。
    
    DataFrame 必须包含：
        date(int), code(str), open, high, low, close, vol, amount
    """

    log.warning("开始重建 tdx_all_df HDF5 文件（瘦身、修复）...")

    if fetch_all_df_func is None:
        raise ValueError("必须提供 fetch_all_df_func 函数，用于获取完整 all_900 数据")

    # ======================================================
    # 1. 获取数据
    # ======================================================
    df = fetch_all_df_func()

    if df is None or df.empty:
        raise ValueError("fetch_all_df_func 返回空数据，无法写入 HDF5")

    # 强制正确列顺序（HDF 需要固定 schema 才能避免膨胀）
    columns = ["date","code","open","high","low","close","vol","amount"]

    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"数据缺少列: {missing}")

    df = df[columns]

    # ======================================================
    # 2. 固定 dtype（避免 PyTables schema 膨胀）
    # ======================================================
    df = df.astype({
        "date": "int64",
        "code": "string",
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "close": "float64",
        "vol": "float64",
        "amount": "float64",
    })

    # code 限制为固定长度 6 字节（减少体积）
    df["code"] = df["code"].str.encode("utf-8")

    log.info(f"准备写入 HDF5，共 {len(df)} 行...")

    # ======================================================
    # 3. 删除旧文件（必须，否则残留垃圾导致膨胀）
    # ======================================================
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            log.info("旧 HDF5 文件已删除（强制瘦身）")
        except Exception as e:
            log.error(f"旧 HDF5 删除失败: {e}")
            raise

    # ======================================================
    # 4. 一次性写入 HDF5（避免 append 膨胀）
    # ======================================================
    try:
        df.to_hdf(
            file_path,
            key="all_900",
            mode="w",
            format="table",  
            complevel=9,
            complib="blosc:zstd",  # 最高比 zlib 强 4-5 倍压缩
        )
        log.info(f"HDF5 写入完成: {file_path}")

    except Exception as e:
        log.error(f"HDF5 写入失败: {e}")
        raise

    # ======================================================
    # 5. 最终检查
    # ======================================================
    log.info("重建完成，将执行 check_tdx_all_df 再次确认文件正确")
    return True

# def check_tdx_all_df(file_path: str, rebuild_func=None):
#     """
#     检查 tdx_all_df 的 HDF5 文件是否异常，必要时触发重建。

#     rebuild_func: 用于执行重建的回调函数，例如 write_tdx_all_df()
#     """

#     # 文件不存在
#     if not os.path.exists(file_path):
#         log.warning(f"HDF5 文件不存在: {file_path}，即将重建...")
#         if rebuild_func:
#             rebuild_func()
#         return False

#     # 文件基础信息
#     file_size = os.path.getsize(file_path)
#     size_mb = file_size / 1024 / 1024

#     log.info(f"HDF5 文件大小: {size_mb:.2f} MB")

#     try:
#         store = pd.HDFStore(file_path, mode='r')
#     except Exception as e:
#         log.error(f"HDF5 打开失败，文件可能损坏: {e}")
#         if rebuild_func:
#             rebuild_func()
#         return False

#     # 获取 keys
#     keys = store.keys()
#     log.debug(f"顶层 keys: {keys}")

#     if "/all_900" not in keys:
#         log.warning("缺少 /all_900 数据集，触发重建")
#         store.close()
#         if rebuild_func:
#             rebuild_func()
#         return False

#     try:
#         df = store["all_900"]
#     except Exception as e:
#         log.error(f"HDF5 读取失败: {e}")
#         store.close()
#         if rebuild_func:
#             rebuild_func()
#         return False

#     store.close()

#     # --------------------------
#     # 规则 1：行数异常
#     # --------------------------
#     row_count = len(df)
#     if row_count < 10000:
#         log.warning(f"HDF5 行数异常: {row_count}，可能已损坏 → 重建")
#         if rebuild_func:
#             rebuild_func()
#         return False

#     # --------------------------
#     # 规则 2：平均行大小过大（判断膨胀）
#     # --------------------------
#     bytes_per_row = file_size / max(row_count, 1)

#     log.info(f"平均每行大小: {bytes_per_row:.2f} bytes/row")

#     # 正常 HDF5 行大小一般在 200~600 bytes 左右
#     if bytes_per_row > 5000:  # > 5 KB/行 → 强制认为膨胀
#         log.warning("检测到严重膨胀（>5 KB/row），需要瘦身重建")
#         if rebuild_func:
#             rebuild_func()
#         return False

#     # --------------------------
#     # 规则 3：字段校验
#     # --------------------------
#     expected_cols = ["date","code","open","high","low","close","vol","amount"]
#     for c in expected_cols:
#         if c not in df.columns:
#             log.warning(f"字段缺失: {c}，触发重建")
#             if rebuild_func:
#                 rebuild_func()
#             return False

#     log.info("HDF5 文件检查正常")
#     return True


def compact_hdf5_file(file_path, complevel=9, complib='blosc'):
    """
    对 HDF5 文件进行瘦身，保留数据，重新写入压缩，清理膨胀
    :param file_path: HDF5 文件路径
    :param complevel: 压缩等级，0-9
    :param complib: 压缩库，例如 'blosc', 'zlib'
    """
    tmp_file = file_path + ".tmp"

    try:
        with HDFStore(file_path, mode='r') as src, HDFStore(tmp_file, mode='w', complevel=complevel, complib=complib) as dst:
            keys = src.keys()
            for key in keys:
                df = src[key]
                dst.put(key, df, format='table', complevel=complevel, complib=complib)

        # 替换原文件
        os.replace(tmp_file, file_path)
        print(f"HDF5 文件瘦身完成: {file_path}")

    except Exception as e:
        print("瘦身失败:", e)

def check_tdx_all_df(fname='300', shrink_threshold=20000):
    tdx_hd5_name = f'tdx_all_df_{fname}'
    tdx_hd5_path = cct.get_run_path_tdx(tdx_hd5_name)

    print(f"HDF5 文件路径: {tdx_hd5_path}\n")

    if not os.path.exists(tdx_hd5_path):
        print("文件不存在")
        return

    file_size_mb = os.path.getsize(tdx_hd5_path) / 1024 / 1024
    print(f"文件大小: {file_size_mb:.2f} MB")

    try:
        # 使用 HDFStore
        with HDFStore(tdx_hd5_path, mode='r') as store:
            top_keys = store.keys()  # 返回 ['/df1', '/df2']
            top_keys = [k.lstrip('/') for k in top_keys]  # 去掉前导 /
            print("顶层 keys:", top_keys)

            if not top_keys:
                print("HDF5 文件没有顶层 keys")
                return

            # 取第一个 key 对应的 DataFrame
            first_key = top_keys[0]
            df = store[first_key]
            
            print(f"[DataFrame] key: {first_key}")
            print(f"shape: {df.shape}")
            print(f"dtypes:\n{df.dtypes}")

            rows = df.shape[0]
            avg_row_size = file_size_mb * 1024 * 1024 / rows if rows > 0 else 0
            print(f"总行数: {rows}, 文件大小: {file_size_mb:.2f} MB, 平均每行大小: {avg_row_size:.2f} bytes")

            # if rows > shrink_threshold:
            #     print(f"行数超过阈值 {shrink_threshold}, 建议缩减数据")

    except Exception as e:
        print("读取 HDF5 文件失败:", e)

    finally:
        if avg_row_size > shrink_threshold:
            print("文件膨胀，自动瘦身...")
            try:
                compact_hdf5_file(tdx_hd5_path)
                print("瘦身完成")
            except Exception as e:
                print(f"瘦身失败: {e}")
    return df
    
def check_tdx_all_df_Sina(fname='sina_data',max_cols_per_line=5, limit=None):
    """
    :param fname: HDF5 文件名后缀
    :param max_cols_per_line: 打印 dtypes 时每行显示的列数
    :param limit: 如果指定，打印 DataFrame 前 limit 行
    """
    tdx_hd5_name = fname
    tdx_hd5_path = cct.get_ramdisk_path(tdx_hd5_name)

    print(f"HDF5 文件路径: {tdx_hd5_path}\n\n")

    if not os.path.exists(tdx_hd5_path):
        print("文件不存在")
        return

    file_size = os.path.getsize(tdx_hd5_path) / 1024 / 1024  # MB
    print(f"文件大小: {file_size:.2f} MB")

    try:
        with HDFStore(tdx_hd5_path, mode='r') as store:
            top_keys = [k.lstrip('/') for k in store.keys()]
            print("顶层 keys:", top_keys)

            total_rows = 0

            for key in top_keys:
                df = store[key]
                print("=" * 80)
                print(f"[DataFrame] key: {key}")
                print(f"shape: {df.shape}")

                # 横向精简显示 dtypes
                dtype_items = [f"{col}: {dtype}" for col, dtype in df.dtypes.items()]
                for i in range(0, len(dtype_items), max_cols_per_line):
                    print("  |  ".join(dtype_items[i:i+max_cols_per_line]))

                rows = df.shape[0]
                total_rows += rows

            print("=" * 80)
            print(f"总数据行数: {total_rows}")
            avg_row_size = file_size * 1024 * 1024 / total_rows if total_rows > 0 else 0
            print(f"平均每行大小: {avg_row_size:.2f} bytes/row")
            # 输出前 limit 行
            if limit is not None:
                print(f"\n前 {limit} 行数据:")
                print(df.head(limit))
            else:
                print("\n前 5 行数据:")
                print(df.head(5))

    except Exception as e:
        print("无法打开 HDF5:", e)
    return df

def check_tdx_all_df_read(fname='300'):
    tdx_hd5_name = f'tdx_all_df_{fname}'
    tdx_hd5_path = cct.get_run_path_tdx(tdx_hd5_name)

    print(f"HDF5 文件路径: {tdx_hd5_path}\n\n")

    if not os.path.exists(tdx_hd5_path):
        print("文件不存在")
        return

    file_size = os.path.getsize(tdx_hd5_path) / 1024 / 1024  # MB
    print(f"文件大小: {file_size:.2f} MB")

    try:
        with HDFStore(tdx_hd5_path, mode='r') as store:
            top_keys = store.keys()  # ['/df1', '/df2']
            top_keys = [k.lstrip('/') for k in top_keys]
            print("顶层 keys:", top_keys)

            total_rows = 0

            for key in top_keys:
                df = store[key]
                print("=" * 80)
                print(f"[DataFrame] key: {key}")
                print(f"shape: {df.shape}")
                print(f"dtypes:\n{df.dtypes}")

                rows = df.shape[0]
                total_rows += rows

                # 打印列字段大小（估算每列单个元素大小）
                print("\n字段结构:")
                for col in df.columns:
                    dtype = df[col].dtype
                    try:
                        itemsize = df[col].values.itemsize
                    except:
                        itemsize = 0
                    print(f"  - {col}: {dtype} ({itemsize} bytes)")

            print("=" * 80)
            print(f"总数据行数: {total_rows}")
            print(f"文件大小: {file_size:.2f} MB")
            avg_row_size = file_size * 1024 * 1024 / total_rows if total_rows > 0 else 0
            print(f"平均每行大小: {avg_row_size:.2f} bytes/row")

    except Exception as e:
        print("无法打开 HDF5:", e)
    return df
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
    def df_diagnose(df, name='df'):
        # print(f'df: {df}')
        # import ipdb;ipdb.set_trace()
        if df is not None and not df.empty:
            print(f'[{name}] shape:', df.shape)
            print('- index:', type(df.index), 
                  'unique:', df.index.is_unique)
            print('- memory(MB):', df.memory_usage(deep=True).sum()/1024**2)
            print('- df.dtypes.value_counts() dtypes:\n', df.dtypes.value_counts())
            obj_cols = df.select_dtypes(include='object').columns
            if len(obj_cols):
                print('- object cols:', list(obj_cols)[:10])
            print(f'show table 5:{df.loc[:,obj_cols][:5]}')

    def encode_mainu_bitmask(df, col='MainU'):
        df[col + '_mask'] = df[col].apply(lambda x: sum(1 << int(i) for i in str(x).split(',') if i.isdigit()) if pd.notna(x) and x != '0' else 0).astype('int32')
        # 原列保留，不 drop
        return df

    def normalize_object_columns(df):
        # status -> category
        if 'status' in df.columns:
            df['status'] = df['status'].astype('category')

        # MainU -> 直接转换成 mask（覆盖原列）
        if 'MainU' in df.columns:
            df['MainU'] = df['MainU'].apply(
                lambda x: sum(1 << int(i) for i in str(x).split(',') if i.isdigit()) 
                          if pd.notna(x) and x != '0' else 0
            ).astype('int32')

        # date -> datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')

        # category -> int16
        if 'category' in df.columns:
            df['category'] = pd.to_numeric(df['category'], errors='coerce').fillna(0).astype('int16')

        # hangye -> category
        if 'hangye' in df.columns:
            df['hangye'] = df['hangye'].replace(0, '未知').astype('category')

        return df

    def get_tdx_all_from_h5(showtable=True,resample='d',dl=ct.Resample_LABELS_Days['d']):
        #sina_monitor
        h5_fname = 'tdx_last_df'
        # resample='d'
        resample=resample
        # dl='60'
        dl= dl
        filter='y'
        h5_table = 'low' + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'
        h5 = load_hdf_db(h5_fname, table=h5_table,code_l=None, timelimit=False,showtable=showtable)
        return h5

    def readHdf5(fpath, root=None):
        if not os.path.exists(fpath):
            print(f'no fpath:{fpath}')
            return
        store = pd.HDFStore(fpath, "r")
        print(list(store.keys()))
        if root is None:
            root = list(store.keys())[0].replace("/", "")
        df = store[root]
        store.close()
        return df

    def get_tdx_all_MultiIndex_h5(showtable=True):
        #sina_monitor
        h5_fname = 'sina_MultiIndex_data'
        resample='d'
        dl='60'
        filter='y'
        h5_table = 'low' + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'
        h5_table = f'all_{cct.sina_limit_time}'
        h5 = load_hdf_db(h5_fname, table=h5_table,code_l=None, timelimit=False,showtable=showtable)
        return h5

    def check_hdf(h5_fname,h5_table,showtable=True,new_path=None):
        print(f'fname : {h5_fname}')
        h5 = load_hdf_db(h5_fname, table=h5_table,code_l=None, timelimit=False,showtable=showtable)
        with tables.open_file(f"G:\\{h5_fname}.h5") as f: print(f)
        if new_path:
            hm5.to_hdf(f"G:\\{new_path}", key=f"{h5_table}/table", mode="w", format="table", complib="blosc", complevel=9)

    def read_sina_df(h5_fname,h5_table,showtable=True,new_path=None):
        print(f'fname : {h5_fname}')
        h5 = load_hdf_db(h5_fname, table=h5_table,code_l=None, timelimit=False,showtable=showtable)
        return h5
    # hm5=get_tdx_all_MultiIndex_h5()
    # with tables.open_file(r"G:\sina_MultiIndex_data.h5") as f: print(f)
    # with tables.open_file(r"G:\sina_data.h5") as f: print(f)
    # h5=get_tdx_all_from_h5()
    
    # print(hm5.memory_usage(deep=True).sum() / 1024**2, "MB")
    # hm5.to_hdf(r"G:\sina_MultiIndex_data_clean.h5", key="all_30/table", mode="w", format="table", complib="blosc", complevel=9)
    print(f"sina_data:{check_hdf(h5_fname='sina_data',h5_table='all')}")
    # print(f"sina_data:{check_hdf(h5_fname='tdx_all_df_300',h5_table='all')}")
    sina = read_sina_df(h5_fname='sina_data',h5_table='all')
    df_diagnose(sina)
    import ipdb;ipdb.set_trace()

    sina_MultiD_path = "G:\\sina_MultiIndex_data.h5"
    freq='5T'
    startime = None
    endtime = '15:01:00'

    print('sina_MultiD_path:{sina_MultiD_path}')
    os.path.getsize(sina_MultiD_path) > 500

    if os.path.exists(sina_MultiD_path) and os.path.getsize(sina_MultiD_path) > 5000:
        h5 = readHdf5(sina_MultiD_path)
        h5.shape
        print(h5.loc['300245'])
        print(h5.loc['000002'])
        df_diagnose(h5)

        mdf = cct.get_limit_multiIndex_freq(h5, freq=freq.upper(),  col='all', start=startime, end=endtime, code=None)
        print(mdf.loc['002151'])
        
        print(mdf.loc['300516'])
        print(mdf.loc['300245'].close.mean())
        print(mdf.loc['300516'].close.mean())
        import ipdb;ipdb.set_trace()


    def check_tdx_all_df1(fname='300'):
        import h5py

        tdx_hd5_name = f'tdx_all_df_{fname}'
        tdx_hd5_path = cct.get_run_path_tdx(tdx_hd5_name)

        print(f'tdx_hd5_path: {tdx_hd5_path}')

        try:
            with h5py.File(tdx_hd5_path, "r") as f:
                print("顶层 keys:", list(f.keys()))
                # 遍历所有 datasets
                def walk_h5(name, obj):
                    if isinstance(obj, h5py.Dataset):
                        print(f"[Dataset] {name} shape={obj.shape} dtype={obj.dtype}")
                    elif isinstance(obj, h5py.Group):
                        print(f"[Group] {name}")

                f.visititems(walk_h5)

        except Exception as e:
            print("H5PY无法打开:", e)

    


    # sina_MultiD_path = "G:\\sina_MultiIndex_data.h5"
    tdx_hd5_name = r'tdx_all_df_%s' % (300)

    # h5repack tdx_hd5_path tdx_hd5_path.bak
    # h300 = load_hdf_db(tdx_hd5_name, table='all_300', code_l=None, timelimit=False, MultiIndex=True)
    check_tdx_all_df('300')
    check_tdx_all_df('900')
    check_tdx_all_df_read('900')


    for re in ct.Resample_LABELS:
        print(f're: {re}')
        if re in ct.Resample_LABELS_Days:
            dl = ct.Resample_LABELS_Days[re]
            print(f'dl :{dl}')

    import warnings
    import tables

    # 忽略 PyTables 的性能警告
    warnings.filterwarnings("ignore", category=tables.exceptions.PerformanceWarning)
    print(f'tdx_hd5_name: {tdx_hd5_name}-------------------')
    tdx_hd5_name = r"G:\\tdx_last_df.h5"
    tablename = 'low_d_70_y_all'
    df=readHdf5(tdx_hd5_name,tablename)
    # print(df.loc['300245'])
    df_diagnose(df)
    
    import ipdb;ipdb.set_trace()

    print(f'show src df.dtypes.value_counts(): {df.dtypes.value_counts()}')

    # df = normalize_object_columns(df)
    # print(f'show normalize_object_columns df.dtypes.value_counts(): {df.dtypes.value_counts()}')
    print(f'show reduce_memory_usage-----------------\n')
    df2 = cct.reduce_memory_usage(df,verbose=True)
    df_diagnose(df2)
    print(f'show reduce_memory_usage df.dtypes.value_counts(): {df2.dtypes.value_counts()}----\n')
    print(f"show reduce_memory_usage table 5:{df2.loc[:,['status', 'MainU', 'date', 'category', 'hangye']][:5]}")
    print(f'show reduce_memory_usage-----------------\n')

    df = cct.prepare_df_for_hdf5(df)
    df_diagnose(df)
    print(f'show prepare_df_for_hdf5 df.dtypes.value_counts(): {df.dtypes.value_counts()}----\n')
    print(f"show prepare_df_for_hdf5 table 5:{df.loc[:,['status', 'MainU', 'date', 'category', 'hangye']][:5]}")
    print(f'show prepare_df_for_hdf5-----------------\n')

    # print(f'df.memory_usage(deep=True): {df.memory_usage(deep=True)} df.memory_usage(deep=True).sum: {df.memory_usage(deep=True).sum() / 1024**2}')
    import ipdb;ipdb.set_trace()


    # a = np.random.standard_normal((9000,4))
    # df = pd.DataFrame(a)
    # h5_fname = 'test_s.h5'
    # h5_table = 'all'
    # h5 = write_hdf_db(h5_fname, df, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=False)
    # import ipdb;ipdb.set_trace()




    fname=['sina_data.h5', 'tdx_last_df', 'powerCompute.h5', 'get_sina_all_ratio']
    # fname=['test_s.h5','sina_data.h5', 'tdx_last_df', 'powerCompute.h5', 'get_sina_all_ratio']
    fname=['test_s.h5']
    # fname = 'powerCompute.h5'
    for na in fname:
        # with SafeHDFStore(na) as h5:
        with HDFStore(na) as h5:
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
