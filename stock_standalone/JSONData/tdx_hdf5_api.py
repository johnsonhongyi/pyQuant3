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
global RAMDISK_KEY, INIT_LOG_Error, Debug_is_not_find
RAMDISK_KEY = 0
INIT_LOG_Error = 0
Debug_is_not_find = 0
# Compress_Count = 1
BaseDir = cct.get_ramdisk_dir()
import tables
import psutil
import shutil
import errno
import threading

# # 从 global.ini 读取 MultiIndex 文件限额 (默认 150MB)
# def _load_sina_multiindex_limit():
#     try:
#         # global.ini 位于 stock_standalone 根目录
#         _config_path = os.path.join(cct.get_base_path(), 'global.ini')
#         if os.path.exists(_config_path):
#             from configobj import ConfigObj
#             # 1. 尝试使用标准 ConfigObj 解析
#             try:
#                 _config = ConfigObj(_config_path, encoding='UTF8')
#                 _gen_section = _config.get('general', {})
#                 # 兼容大小写
#                 _limit = _gen_section.get('sina_MultiIndex_limit') or _gen_section.get('sina_multiindex_limit')
#                 if _limit is not None:
#                     return int(_limit)
#             except Exception:
#                 pass

#             # 2. 备选方案：如果 ConfigObj 解析异常，直接进行文本查找（鲁棒性最强）
#             with open(_config_path, 'r', encoding='utf-8', errors='ignore') as f:
#                 content = f.read()
#                 # 使用正则匹配，不区分大小写
#                 import re
#                 match = re.search(r'sina_multiindex_limit\s*=\s*(\d+)', content, re.IGNORECASE)
#                 if match:
#                     return int(match.group(1))
#     except Exception as e:
#         log.error(f"Failed to load sina_multiindex_limit: {e}")
#     return 150


SINA_MULTIINDEX_LIMIT = cct.sina_MultiIndex_limit

# 强制最低 10MB 防止除零或过小裁切
if SINA_MULTIINDEX_LIMIT < 10:
    SINA_MULTIINDEX_LIMIT = 150

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

def _on_rm_error(func, path, exc_info):
    """
    rmtree 删除失败回调：只记录，不抛出
    """
    err = exc_info[1]
    if isinstance(err, PermissionError) or getattr(err, 'errno', None) in (errno.EACCES, errno.EBUSY, 32):
        log.warning(f"[TempCleanup] skip locked: {path}")
        return
    log.warning(f"[TempCleanup] skip: {path}, reason: {err}")


def _recover_orphaned_h5(fname_path: str) -> bool:
    """
    [Disaster Recovery] ⚡ 智能容灾自愈：
    如果原 .h5 文件丢失，尝试从剩余的 .tmp.* 临时快照中寻找最新的（或已裁切好的）有效镜像并将其“转正”。
    """
    try:
        # 如果主文件存在且足够大，无需恢复
        if os.path.exists(fname_path) and os.path.getsize(fname_path) > 1024 * 10:
            return False 

        base_dir = os.path.dirname(fname_path)
        base_name = os.path.basename(fname_path)
        if base_name.endswith('.h5'):
            base_name = base_name[:-3]
        
        candidates = []
        if os.path.exists(base_dir):
            for name in os.listdir(base_dir):
                # 兼容 .tmp.PID.TID 和 .tmp.PID 两种模式
                if name.startswith(base_name + ".tmp."):
                    path = os.path.join(base_dir, name)
                    if os.path.isfile(path):
                        size = os.path.getsize(path)
                        if size > 1024 * 10: # 必须大于 10KB
                            candidates.append({
                                'path': path, 
                                'mtime': os.path.getmtime(path), 
                                'size': size
                            })
        
        if not candidates:
            return False
            
        # 排序权重算法：
        # 1. 最近 5 分钟内修改的优先
        # 2. 如果多个修改时间相近，优先选择体积较小但合理的（通常是成功裁切过的镜像）
        candidates.sort(key=lambda x: (x['mtime'], -x['size']), reverse=True)
        
        # 探测有效性
        for cand in candidates:
            best_tmp = cand['path']
            try:
                # 尝试用 HDFStore 只读打开探测是否有可用 Key
                with pd.HDFStore(best_tmp, mode='r') as store:
                    if len(store.keys()) > 0:
                        log.warning(f"⚠️ [HDF-RECOVER] Target missing: {fname_path}. "
                                    f"Promoting valid orphan: {os.path.basename(best_tmp)} "
                                    f"(Size: {cand['size']/1024/1024:.1f}MB, Time: {time.ctime(cand['mtime'])})")
                        os.replace(best_tmp, fname_path)
                        return True
            except Exception:
                log.debug(f"[HDF-RECOVER] Candidate {best_tmp} is invalid/incomplete, skipping.")
                continue

        return False

    except Exception as e:
        log.error(f"❌ [HDF-RECOVER] Recovery failed for {fname_path}: {e}")
        return False

def _clean_orphaned_temp_files(fname_path: str):
    """
    [Space Optimization] ⚡ 写前清理：
    清理 base_dir 下所有属于当前基础名的、且对应 PID 已消失的孤儿临时文件。
    """
    try:
        base_dir = os.path.dirname(fname_path)
        base_name = os.path.basename(fname_path)
        if base_name.endswith('.h5'):
            base_name = base_name[:-3]
        
        if not os.path.exists(base_dir):
            return

        for name in os.listdir(base_dir):
            # 识别 .tmp.PID... 命名的文件
            if name.startswith(base_name + ".tmp."):
                path = os.path.join(base_dir, name)
                try:
                    parts = name.split(".")
                    # 查找文件名中的 PID (通常是 .tmp. 后的第一段)
                    pid_found = False
                    for p in parts:
                        if p.isdigit() and 10 < int(p) < 1000000: # 粗略判定是否为合法 PID
                            pid = int(p)
                            if not psutil.pid_exists(pid):
                                os.remove(path)
                                log.info(f"[HDF-CLEAN] Removed stale orphan from dead PID {pid}: {path}")
                            pid_found = True
                            break
                    # 如果没找到数字（异常命名），为了安全暂时保留或者根据修改时间清理
                    if not pid_found:
                         if time.time() - os.path.getmtime(path) > 3600 * 24: # 超过24小时清理
                             os.remove(path)
                             log.info(f"[HDF-CLEAN] Removed very old unknown tmp file: {path}")
                             
                except Exception:
                    pass
    except Exception as e:
        log.error(f"[HDF-CLEAN] Error cleaning orphaned files for {fname_path}: {e}")

def cleanup_temp_dir(base_dir: str, temp_name: str = "Temp") -> None:
    """
    清理 base_dir 下的 Temp 目录内容（不确认、不抛异常、尽力而为）
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
                    shutil.rmtree(path, onerror=_on_rm_error)
                    log.info(f"[TempCleanup] removed dir: {path}")
                else:
                    os.remove(path)
                    log.info(f"[TempCleanup] removed file: {path}")

            except Exception as e:
                # 双保险：目录级兜底
                log.warning(f"[TempCleanup] skip: {path}, reason: {e}")

    except Exception as e:
        log.error(f"[TempCleanup] fatal error on base_dir={base_dir}: {e}")

def cleanup_temp_dir_old_dir(base_dir: str, temp_name: str = "Temp") -> None:
    """
    清理 base_dir 下的 Temp 目录内容（不确认、不抛异常、尽力而为）

    :param base_dir: 如 G:\\
    :param temp_name: 默认 Temp
    """
    try:
        base_dir = os.path.abspath(base_dir)
        # [FIX] ⚡ 安全加固：仅清理 base_dir 根目录下的孤儿锁文件 (.lock)
        # 严禁在此处自动扫描并删除 '.tmp.' 文件，因为这会误删其他正在运行的线程生成的临时数据。
        for name in os.listdir(base_dir):
            if name.endswith('.lock'):
                path = os.path.join(base_dir, name)
                try:
                    # 锁文件清理：检查 PID 是否存活
                    try:
                        with open(path, 'r') as f:
                            content = f.read().strip()
                            if content:
                                pid_str = content.split('|')[0]
                                if pid_str.isdigit() and psutil.pid_exists(int(pid_str)):
                                    continue # 进程还在，不删
                    except Exception:
                        pass # 读取失败则尝试删除
                    
                    os.remove(path)
                    log.info(f"[TempCleanup] removed orphaned lock file: {path}")
                except Exception:
                    pass

        # 原有的子目录清理逻辑
        temp_name = "temp"
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


# 全局锁（进程内）
_global_hdf_lock = threading.Lock()
# [NEW] 专门保护 HDF5 文件写入过程的物理锁（防止同一进程内不同线程抢占 temp 文件）
_hdf_write_lock = threading.Lock()

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
        self.probe_interval = kwargs.pop("probe_interval", 0.05)  
        self.lock_timeout = kwargs.pop("lock_timeout", 10)  
        self.max_wait = 30
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
        # if self.fname_o.lower().find(self.basedir.lower()) < 0 and (self.fname_o == cct.tdx_hd5_name or self.fname_o.find('tdx_all_df') >= 0):
        if not os.path.isabs(self.fname_o) and (self.fname_o == cct.tdx_hd5_name or 'tdx_all_df' in self.fname_o):
            self.multiIndexsize = True
            self.fname = cct.get_run_path_tdx(self.fname_o)
            self.basedir = self.fname.split(self.fname_o)[0]
            self.log.info(f"tdx_hd5: {self.fname}")
        else:
            self.fname = cct.get_ramdisk_path(self.fname_o)
            if os.path.isabs(self.fname):
                self.basedir = os.path.dirname(self.fname)
            else:
                self.basedir = self.fname.split(self.fname_o)[0]
            self.log.info(f"ramdisk_hd5: {self.fname}")

        if self.multiIndexsize or self.fname_o.find('sina_MultiIndex') >= 0:
            # 优先使用 global.ini 的配置 (默认 150MB)，不再硬编码为 300MB
            self.big_H5_Size_limit = SINA_MULTIINDEX_LIMIT * 1.5
        else:
            self.big_H5_Size_limit = ct.big_H5_Size_limit
        self.log.info(f'self.big_H5_Size_limit: {self.big_H5_Size_limit}MB (Default: 150MB) multiIndexsize: {self.multiIndexsize}')

        if not os.path.exists(self.basedir):
            if RAMDISK_KEY < 1:
                log.error("NO RamDisk Root:%s" % (self.basedir))
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
        retry_count = 5
        for attempt in range(retry_count):
            try:
                with timed_ctx(f"hdfstore_open_{attempt}"):
                    # super().__init__(self.fname, mode=mode, **kwargs)
                    super().__init__(self.fname, **kwargs)
                opened = True
                break
            except (tables.exceptions.HDF5ExtError, OSError, ValueError, PermissionError) as e:
                self.log.error(f"[HDF] open failed (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    self.log.warning(f"[HDF] Retrying in 3s... Releasing lock first.")
                    try:
                        self.close()
                    except Exception:
                        pass
                    # 尝试释放可能残留的锁
                    self._release_lock()
                    time.sleep(3)
                else:
                    self.log.error(f"[HDF] Final open failed after {retry_count} attempts")
                    need_repair = True

        # ========= 异常路径：才做清理 =========
        if not opened and need_repair:
            with timed_ctx("check_corrupt_keys"):
                # self._repair_hdf_file()   # 见下方
                self._check_and_clean_corrupt_keys()   # 见下方
            with timed_ctx("reopen_hdf"):
                super().__init__(self.fname, **kwargs)

        if self.mode != 'r':
            with timed_ctx("acquire_writer_lock"):
                self._acquire_lock()
        else:
            with timed_ctx("wait_for_writer_lock"):
                # 读模式只需要确认没有写者正在操作
                # 多进程读在大并发下若还用互锁，会导致严重排队
                self._wait_for_lock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.close()
        finally:
            self._release_lock()

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
            # 尝试延迟重试
            try:
                time.sleep(2)
                if os.path.isfile(self.fname):
                    os.remove(self.fname)
                    log.info(f"重试删除文件成功: {self.fname}")
            except Exception as e2:
                log.error(f"重试删除文件失败: {e2}")

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
        """关闭 HDFStore 并释放锁"""
        try:
            super().close()
        except Exception as e:
            self.log.error(f"[{self.my_pid}] super().close() failed: {e}")
        finally:
            self._release_lock()

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
        retry_count = 5
        for attempt in range(retry_count):
            try:
                with timed_ctx(f"write_key_{key}"):
                    self.put(key, df, format='table', **kwargs)
                break
            except Exception as e:
                self.log.error(f"[HDF] write failed (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    self.log.warning(f"[HDF] Write failed, retrying in 3s...")
                    time.sleep(3)
                else:
                    raise e


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
        self.final = str(final_path)
        self.tmp = self.final + ".tmp"

    def __enter__(self):
        # 保留旧数据
        if os.path.exists(self.final):
            shutil.copy2(self.final, self.tmp)
        return self.tmp

    def __exit__(self, exc_type, exc_val, exc_tb):

        # 写入异常直接丢弃
        if exc_type is not None:
            if os.path.exists(self.tmp):
                os.remove(self.tmp)
            return False

        # 校验失败直接丢弃
        if not validate_h5(self.tmp):
            if os.path.exists(self.tmp):
                os.remove(self.tmp)
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
    fname = str(fname)
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


# 全局锁（进程内）
_global_hdf_lock = threading.Lock()

def safe_load_table(
    store,
    table_name,
    chunk_size=2000,
    max_chunks=20,          # ✅ 限制 fallback 范围（关键）
    enable_fallback=False,   # ✅ 默认关闭 fallback（生产建议）
    **kwargs   # ✅ 兼容旧参数（关键）
):

    """
    安全读取 HDF5 table（稳定版）：
    - 主路径：整表读取
    - fallback：有限 chunk 读取（默认关闭）
    - 不 rebuild
    - 强制去重
    """
    # if kwargs:
    #     log.debug(f"[IGNORED PARAMS] {kwargs}")
        
    if store is None:
        return pd.DataFrame()

    with _global_hdf_lock:
        # ---------- 1. 快速路径（主路径） ----------
        try:
            df = store[table_name]
            if df is None or df.empty:
                return pd.DataFrame()

            # 去重 + 防御
            df = df[~df.index.duplicated(keep='first')]
            return df

        # ---------- 2. 结构错误 ----------
        except (AttributeError, KeyError, TypeError) as e:
            log.critical(f"[HDF STRUCT BROKEN] {table_name}: {e}")
            return pd.DataFrame()

        # ---------- 3. HDF5底层错误 ----------
        except tables.exceptions.HDF5ExtError as e:
            log.error(f"[HDF5 ERROR] {table_name}: {e}")

            # ❗生产环境直接返回（最安全）
            if not enable_fallback:
                return pd.DataFrame()

        # ---------- 4. IO级错误 ----------
        except (OSError, IOError) as e:
            log.critical(f"[HDF FILE ERROR] {table_name}: {e}")
            return pd.DataFrame()

        # ---------- 5. fallback（严格受控） ----------
        dfs = []
        start = 0
        chunks_read = 0

        try:
            storer = store.get_storer(table_name)
            if not getattr(storer, "is_table", False):
                log.error(f"{table_name} is not table format")
                return pd.DataFrame()
        except Exception as e:
            log.error(f"get_storer failed: {table_name}, {e}")
            return pd.DataFrame()

        while chunks_read < max_chunks:
            try:
                df_chunk = store.select(
                    table_name,
                    start=start,
                    stop=start + chunk_size
                )

                if df_chunk is None or df_chunk.empty:
                    break

                dfs.append(df_chunk)

            except tables.exceptions.HDF5ExtError:
                log.warning(f"skip bad chunk {start}-{start + chunk_size}")

            except Exception as e:
                log.error(f"fatal chunk error @{start}: {e}")
                break

            start += chunk_size
            chunks_read += 1

        if not dfs:
            return pd.DataFrame()

        try:
            df = pd.concat(dfs, copy=False)
        except Exception as e:
            log.error(f"concat failed: {table_name}, {e}")
            return pd.DataFrame()

        # ---------- 6. 最终清洗 ----------
        df = df[~df.index.duplicated(keep='first')]

        return df

# def safe_load_table(store, table_name, chunk_size=1000,
#                     MultiIndex=False, complib='blosc',complevel=9,
#                     readonly=False):
#     """
#     安全读取 HDF5 table：
#     - metadata / UnImplemented → 直接失败
#     - HDF5ExtError → 尝试 chunk 读取
#     """

#     # ---------- 1. 尝试整表读取 ----------
#     try:
#         df = store[table_name]
#         return df[~df.index.duplicated(keep='first')]

#     # ---------- 2. 结构级损坏（不可恢复） ----------
#     except (AttributeError, KeyError, TypeError) as e:
#         log.critical(
#             f"HDF STRUCTURE BROKEN: {table_name}, "
#             f"type={type(e).__name__}, err={e}"
#         )
#         raise e

#     # ---------- HDF5 底层错误 ----------
#     except tables.exceptions.HDF5ExtError as e:
#         log.error(
#             f"{table_name} HDF5ExtError: {e}, "
#             f"attempting chunked read..."
#         )
#         # ↓ 继续走 chunk fallback

#     # ---------- 4. 文件级物理损坏 ----------
#     except (OSError, IOError, UnicodeDecodeError) as e:
#         log.critical(
#             f"HDF FILE BROKEN: {table_name}, "
#             f"type={type(e).__name__}, err={e}"
#         )
#         return pd.DataFrame()

#     # ---------- 5. chunk fallback ----------
#     dfs = []
#     start = 0

#     try:
#         storer = store.get_storer(table_name)
#         if not storer.is_table:
#             log.error(f"{table_name} is not table format")
#             return pd.DataFrame()
#     except Exception as e:
#         log.error(f"get_storer failed for {table_name}: {e}")
#         return pd.DataFrame()

#     while True:
#         try:
#             df_chunk = store.select(
#                 table_name,
#                 start=start,
#                 stop=start + chunk_size
#             )
#             if df_chunk.empty:
#                 break
#             dfs.append(df_chunk)
#             start += chunk_size

#         except tables.exceptions.HDF5ExtError:
#             log.warning(
#                 f"Skipping corrupted chunk "
#                 f"{start}-{start + chunk_size}"
#             )
#             start += chunk_size

#         except Exception as e:
#             log.error(
#                 f"Fatal error reading chunk {start}: {e}"
#             )
#             break

#     if not dfs:
#         log.error(f"All chunks of {table_name} are unreadable")
#         return pd.DataFrame()

#     df = pd.concat(dfs)
#     df = df[~df.index.duplicated(keep='first')]

#     # ---------- 6. 是否重建 ----------
#     # if not readonly:
#     #     log.warning(f"Rebuilding table {table_name} from chunks")
#     #     rebuild_table(
#     #         store, table_name, df,
#     #         MultiIndex=MultiIndex,
#     #         complib=complib,
#     #         complevel=complevel
#     #     )

#     return df

def rebuild_table(store, table_name, new_df, *,
                  MultiIndex=False,
                  complib='blosc',
                  complevel=9,
                  index_col=["code","name"]):
    """
    安全重建 HDF 表：
    - 删除旧表并重新写入
    - 兼容单索引、多索引
    - 自动检查 index_col 是否存在
    """
    key = '/' + table_name

    # 检查 index_col 是否存在于 df
    if index_col:
        index_col_valid = [c for c in index_col if c in new_df.columns]
        if not index_col_valid:
            index_col_valid = None
    else:
        index_col_valid = None

    # 删除旧表
    if key in store.keys():
        log.info(f"Removing old table {table_name}")
        store.remove(key)

    if new_df.empty:
        log.warning(f"Table {table_name} is empty, skipped rebuilding")
        return

    # 写入新表
    if not MultiIndex:
        store.put(
            key, new_df,
            format='table',
            append=False,
            complib=complib,
            complevel=complevel,
            data_columns=index_col_valid
        )
    else:
        store.put(
            key, new_df,
            format='table',
            index=True,         # 保留 MultiIndex
            append=False,
            complib=complib,
            complevel=complevel,
            data_columns=index_col_valid
        )

    store.flush()
    log.info(f"Rebuilt table {table_name}, shape={new_df.shape}")
    

def rebuild_table_src(store, table_name, new_df,MultiIndex=False,complib='blosc',complevel=9,index_col=["code","name"]):
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
            # store.put(table_name, new_df, format='table', append=False, complib=complib, complevel=complevel,data_columns=True)
            store.put(table_name, new_df, format='table', append=False, complib=complib, complevel=complevel,data_columns=index_col)
        else:
            # store.put(table_name, new_df, format='table', index=False, complib=complib, complevel=complevel,data_columns=True, append=False)
            store.put(table_name, new_df, format='table', index=False, complib=complib, complevel=complevel,data_columns=index_col, append=False)
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

def put_table_safe(h5, table, df, *,
                   MultiIndex=False,
                   rewrite=False,
                   complib='blosc',
                   complevel=9,
                   index_col=["code","name"]):
    """
    安全写入 HDF 表，兼容单索引、多索引、缺失索引列
    - MultiIndex: 是否使用多级索引（行索引）
    - rewrite: 是否清空原表
    - index_col: 需要建立查询索引的列列表，缺失会自动忽略
    """
    key = '/' + table

    # 确认 index_col 存在于 df 中
    if index_col:
        index_col_valid = [c for c in index_col if c in df.columns]
        if not index_col_valid:
            index_col_valid = None
    else:
        index_col_valid = None

    if key in h5.keys():
        if not MultiIndex:
            # 清空原表
            h5.remove(key)
            h5.put(
                key, df,
                format='table',
                append=False,
                complib=complib,
                complevel=complevel,
                data_columns=index_col_valid
            )
        else:
            # MultiIndex 情况
            # [FIX] ⚡ 规避 0xc0000374 Heap Corruption：不要直接对大文件调用 len(h5[key])
            # 因为这会加载整个表。改用 get_storer().nrows 只读元数据。
            try:
                storer = h5.get_storer(key)
                existing_rows = storer.nrows if storer is not None else 0
            except Exception:
                existing_rows = 0
                
            if rewrite or existing_rows < 1:
                h5.remove(key)

            # [OPTIMIZE] ⚡ 规避 Access Violation：对 MultiIndex 禁用实时索引更新
            # 在追加模式下，维护索引是极高的开销且容易在多线程下崩溃。
            # 对于 170MB 级别的内存盘文件，全表扫描查询也非常快，无需实时维护索引。
            h5.put(
                key, df,
                format='table',
                index=True,  # 保留 MultiIndex
                append=True,
                complib=complib,
                complevel=complevel,
                data_columns=index_col_valid
            )
    else:
        # 新表创建
        h5.put(
            key, df,
            format='table',
            index=(not MultiIndex),  # 单索引时保留默认整数索引
            append=MultiIndex,
            complib=complib,
            complevel=complevel,
            data_columns=index_col_valid
        )

def put_table_safe_src(h5, table, df, *,
                   MultiIndex=False,
                   rewrite=False,
                   complib='blosc',
                   complevel=9,
                   index_col=["code","name"]):
                   # index_col=["code","name"]):

    #单文件模式
    key = '/' + table

    if key in h5.keys():
        if not MultiIndex:
            safe_remove_h5_table(h5, table)
            h5.put(
                table, df,
                format='table',
                append=False,
                complib=complib,
                complevel=complevel,
                data_columns=index_col
            )
        else:
            if rewrite or len(h5[table]) < 1:
                safe_remove_h5_table(h5, table)

            h5.put(
                table, df,
                format='table',
                index=False,
                append=True,
                complib=complib,
                complevel=complevel,
                data_columns=index_col
            )
    else:
        h5.put(
            table, df,
            format='table',
            index=MultiIndex is False,
            append=MultiIndex,
            complib=complib,
            complevel=complevel,
            data_columns=index_col
        )

def repack_hdf_db(fname, complib='blosc'):
    """
    通过 ptrepack 释放 HDF5 空间。
    基于 SafeHDFStore 的配置进行重排。
    """
    fname_path = cct.get_ramdisk_path(fname)
    if not os.path.exists(fname_path):
        return False
        
    basedir = os.path.dirname(os.path.abspath(fname_path))
    temp_file = fname_path + '_repack_tmp'
    back_path = os.getcwd()
    
    # 构造命令模板 (参照 SafeHDFStore.__init__)
    # ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --alignment=1024 --complevel=9 --complib=%s %s %s"
    
    try:
        # 1. 准备临时文件 (Windows rename 往往需要先关闭所有句柄，此处假设调用者已关闭)
        if os.path.exists(temp_file):
            os.remove(temp_file)
        os.rename(fname_path, temp_file)
        
        # 2. 切换目录以执行相对路径命令 (安全性)
        os.chdir(basedir)
        temp_rel = os.path.relpath(temp_file, basedir)
        fname_rel = os.path.relpath(fname_path, basedir)
        
        pt_cmd = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s" % (complib, temp_rel, fname_rel)
        log.info(f'[HDF-REPACK] Executing: {pt_cmd}')
        
        p = subprocess.Popen(
            pt_cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        out, _ = p.communicate()
        
        if p.returncode != 0:
            log.error(f"[HDF-REPACK] ptrepack failed: {out}")
            # 失败回滚
            if os.path.exists(temp_file) and not os.path.exists(fname_path):
                os.rename(temp_file, fname_path)
            return False
            
        # 3. 成功则清理
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        old_size = os.path.getsize(temp_file if os.path.exists(temp_file) else fname_path) # 逻辑简化
        new_size = os.path.getsize(fname_path)
        log.info(f"✅ [HDF-REPACK] Success: {fname} physical size optimized.")
        return True
        
    except Exception as e:
        log.error(f"[HDF-REPACK] Error: {e}")
        # 严重错误回滚
        if os.path.exists(temp_file) and not os.path.exists(fname_path):
            try: os.rename(temp_file, fname_path)
            except: pass
        return False
    finally:
        os.chdir(back_path)

sina_MultiIndex_SCHEMA = {
    'columns': ['high','low','close','volume','lastbuy','llastp'],
    'dtypes': {
        'high':'float64',
        'low':'float64',
        'close':'float64',
        'volume':'float64',
        'lastbuy':'float64',
        'llastp':'float64'
    }
}


def clean_nan_columns(df):
    nan_cols = df.columns[df.isna().all()].tolist()

    if nan_cols:
        log.warning(f"[CLEAN] drop all-NaN columns: {nan_cols}")
        df = df.drop(columns=nan_cols)

    return df

def normalize_SCHEMA(df):

    # =========================
    # 0. 先清理脏列（🔥必须在最前）
    # =========================
    df = clean_nan_columns(df)

    # =========================
    # 1. 只保留已有列（不新增）
    # =========================
    existing_cols = [
        c for c in sina_MultiIndex_SCHEMA['columns']
        if c in df.columns
    ]

    if not existing_cols:
        return df  # 没有任何匹配列，直接返回

    df = df[existing_cols]

    # =========================
    # 2. 类型转换（只转存在的）
    # =========================
    dtype_map = {
        k: v for k, v in sina_MultiIndex_SCHEMA['dtypes'].items()
        if k in df.columns
    }

    if dtype_map:
        df = df.astype(dtype_map, errors='ignore')

    # =========================
    # 3. 只处理严格 MultiIndex
    # =========================
    if isinstance(df.index, pd.MultiIndex):
        idx_names = list(df.index.names)

        if idx_names == ['code', 'ticktime']:
            df = (
                df.reset_index()
                .drop_duplicates(['code', 'ticktime'], keep='last')
                .set_index(['code', 'ticktime'])
                .sort_index()
            )

    return df

def repair_sina_multiindex_file(fname=None, table=None):
    """
    专门针对 sina_MultiIndex_data.h5 进行物理清理：
    - 移除全 NaN 列（特别是错误的 open 列）
    - 按照标准 SCHEMA 进行转换
    - 移除重复项并按索引排序
    """
    if fname is None:
        fname = 'sina_MultiIndex_data'
    
    # 获取真实路径
    real_path = cct.get_ramdisk_path(fname)
    if not os.path.exists(real_path):
        log.warning(f"[REPAIR] File not found: {real_path}")
        return

    # 识别表格名 (默认为 all_30, all_60 等)
    if table is None:
        # 尝试通过 SafeHDFStore 获取所有以 all_ 开头的表格
        try:
            with SafeHDFStore(fname, mode='r') as store:
                tables = [k.strip('/') for k in store.keys() if k.startswith('/all_')]
        except Exception as e:
            log.error(f"[REPAIR] Failed to inspect keys: {e}")
            return
    else:
        tables = [table]

    for t in tables:
        log.info(f"🚀 [REPAIR] Starting cleanup for table: {t} in {fname}")
        # 1. 加载数据
        df = load_hdf_db(fname, table=t, MultiIndex=True)
        if df is None or df.empty:
            log.warning(f"[REPAIR] No data in {t}, skipping.")
            continue

        # 2. 调用标准规范化逻辑 (包含 clean_nan_columns)
        orig_cols = df.columns.tolist()
        df = normalize_SCHEMA(df)
        new_cols = df.columns.tolist()

        if len(orig_cols) != len(new_cols):
             log.info(f"✨ [REPAIR] Dropped columns: {list(set(orig_cols) - set(new_cols))}")

        # 3. 使用 rewrite=True 物理回写
        write_hdf_db(fname, df, table=t, MultiIndex=True, rewrite=True)
        log.info(f"✅ [REPAIR] Table {t} finalized. Rows: {len(df)}")

    # 4. 物理裁切与压缩 (ptrepack)
    fpath = cct.get_ramdisk_path(fname)
    if os.path.exists(fpath):
        fsize_mb = os.path.getsize(fpath) / 1e6
        if fsize_mb > SINA_MULTIINDEX_LIMIT:
            log.warning(f"🚀 [REPAIR] File size {fsize_mb:.1f}MB exceeds limit {SINA_MULTIINDEX_LIMIT}MB. Triggering ptrepack...")
            with SafeHDFStore(fname) as store:
                store.write_status = True  # 强制标记以触发 __exit__ 中的压缩
    
    log.info(f"✨ [REPAIR] Overall repair for {fname} complete.")

def write_hdf_db(fname, df, table='all', index=False, complib='blosc', baseCount=500, append=True, MultiIndex=False, rewrite=False, showtable=False, sizelimit=None):

    if 'code' in df.columns:
        df=df.set_index('code')
    time_t=time.time()
    df=df[~df.index.duplicated(keep='first')]
    # df=prepare_df_for_hdf5(df)
    df=df.fillna(0)
    code_subdf=df.index.tolist()
    if not RAMDISK_KEY < 1:
        return df

    # # [OPTIMIZE] ⚡ 动态容量限额初始化
    if sizelimit is None:
        if 'sina_MultiIndex' in fname:
            sizelimit = SINA_MULTIINDEX_LIMIT
    #     else:
    #         sizelimit = ct.big_H5_Size_limit

    if not MultiIndex:
        df['timel']=time.time()
    is_work_time = cct.get_work_time()
    if not rewrite:
        if df is not None and not df.empty and table is not None:
            tmpdf = pd.DataFrame()
            try:
                with SafeHDFStore(fname, mode='a') as store:
                    if store is not None:
                        log.debug(f"fname: {(fname)} keys:{store.keys()}")
                        if showtable:
                            print(f"fname: {(fname)} keys:{store.keys()}")
                        if '/' + table in list(store.keys()):
                            # [OPTIMIZE] ⚡ 规避 0xc0000374 Heap Corruption：不要为了检查状态而加载整表
                            # 仅针对 MultiIndex 的追加模式进行采样对比
                            if MultiIndex and not rewrite:
                                try:
                                    # [FIX] ⚡ 恢复历史 ticktime 去重防护：
                                    # start=-500 只覆盖最后~2个品种，导致 dratio 极高从而绕过重复检测。
                                    # 改为动态读取 n_unique*2 行，确保每个品种都有最新记录可供比对。
                                    n_unique = len(df.index.get_level_values('code').unique())
                                    tail_rows = max(500, n_unique * 2)
                                    tmpdf = store.select(table, start=-tail_rows)
                                except Exception:
                                    tmpdf = pd.DataFrame()
                            else:
                                tmpdf = safe_load_table(store, table, chunk_size=5000, MultiIndex=MultiIndex, complib=complib)
                                
                            if tmpdf.empty and not MultiIndex: # 非 MultiIndex 表为空才报损坏
                                log.info(f"{table} : table is corrupted or empty, will rebuild")
            except Exception as e:
                log.error(f"Failed to open store {fname} for reading existing data: {e}. Skipping load.")
                # 不再在此处暴力删除文件，由后续写入逻辑控制


            if not MultiIndex:
                if index:
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

                    log.info("read hdf time:%0.2f" % (time.time() - time_t))
                else:
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
                        # ⚡ [FIX] 采样多只股票进行防重判断，防止单一冷门股由于未成交而导致全盘更新失效
                        sample_count = min(5, len(comm_code))
                        sample_codes = random.sample(comm_code, sample_count)
                        all_unchanged = True
                        
                        for inx_key in sample_codes:
                            if inx_key in df.index.get_level_values('code'):
                                try:
                                    # 兼容 Series 和 DataFrame (针对单次或多次采样)
                                    row_df = df.loc[inx_key]
                                    now_time = row_df.index[-1] if hasattr(row_df.index, '__len__') else row_df.name
                                    
                                    tmp_row = tmpdf.loc[inx_key]
                                    tmp_time = tmp_row.index[-1] if hasattr(tmp_row.index, '__len__') else tmp_row.name
                                    
                                    if now_time != tmp_time:
                                        all_unchanged = False
                                        break
                                except Exception:
                                    all_unchanged = False # 出现解析异常时，为了安全，强制执行写入
                                    break
                        
                        if all_unchanged:
                            log.debug("%s %s Multi batch stagnant (sampled %d codes), Skipping Write." % (fname, table, sample_count))
                            return False
                    elif dratio == 1:
                        print(("newData ratio:%s all:%s"%(dratio,len(df))))
                    else:
                        log.debug("dratio:%s main:%s new:%s %s %s Multi All Wri" % (dratio,len(multi_code),len(df_multi_code),fname, table))
                else:
                    log.debug("%s %s Multi rewrite:%s Wri!!!" % (fname, table, rewrite))


    time_t=time.time()
    if df is not None and not df.empty and table is not None:
        # 类型规范化：HDF5 写入时 object 类型可能导致 schema 不匹配
        # [FIX] ⚡ MultiIndex 表（如 sina_MultiIndex_data.h5）中 close/high 等列本质为 float，
        # 直接 astype(str) 会破坏已有 schema 导致 cannot match existing table structure。
        # 正确做法：MultiIndex 表优先 pd.to_numeric 恢复 float64，无法恢复才保留 object。
        # 非 MultiIndex 表维持原有 astype(str) 行为（用于 code/name 等字符列）。
        dd = df.dtypes.to_frame()
        if 'object' in dd.values:
            col_obj = dd[dd[0] == 'object'].index.tolist()
            if MultiIndex:
                # MultiIndex 表：优先尝试将数值型 object 列恢复为 float64
                str_cols = []
                # 常见数值列白名单，即使全为空也必须是 float，防止 schema 损坏
                numeric_whitelist = ['close', 'high', 'low', 'llastp', 'volume', 'lastbuy', 'change', 'amount', 'p_change']
                for col in col_obj:
                    converted = pd.to_numeric(df[col], errors='coerce')
                    if converted.notna().any() or col.lower() in numeric_whitelist:
                        # 包含有效数字，或者是已知的数值列，强制恢复为 float64
                        df[col] = converted
                        log.debug(f"[SCHEMA-GUARD] MultiIndex col '{col}': object → float64")
                    else:
                        # 确认为纯字符串列（如 name, time, ticktime）
                        str_cols.append(col)
                if str_cols:
                    df[str_cols] = df[str_cols].astype(str)
                    log.debug(f"[SCHEMA-GUARD] MultiIndex str cols kept as str: {str_cols}")
            else:
                # 非 MultiIndex 表：原有行为，全部转 str
                log.debug(f"Converting object columns to str: {col_obj}")
                df[col_obj] = df[col_obj].astype(str)
                df.index = df.index.astype(str)
            df = df.fillna(0)

        write_start_t = time.time()
        # [FIX] ⚡ 使用 PID + ThreadID 构造唯一的临时文件名，防止同一进程内不同线程冲突触发 Access Violation
        temp_fname = fname + ".tmp." + str(os.getpid()) + "." + str(threading.get_ident())
        temp_fname = cct.get_ramdisk_path(temp_fname)
        fname_path = cct.get_ramdisk_path(fname)

        truncated_triggered = False
        
        # 1. 容灾自愈与强力清场
        with _hdf_write_lock:
            # 如果主文件不存在，尝试从临时镜像中恢复
            if not os.path.exists(fname_path):
                _recover_orphaned_h5(fname_path)
            
            # [FIX] ⚡ 为了节省 RAMDISK 空间，在开始新的写入前，清理掉所有已挂掉进程留下的冗余 tmp
            _clean_orphaned_temp_files(fname_path)

        try:
            os.makedirs(os.path.dirname(os.path.abspath(fname_path)), exist_ok=True)

            with _hdf_write_lock:
                # 2. [OPTIMIZE] 内存侧预裁切逻辑：判断是否需要进行体积管理
                needs_prune = False
                if sizelimit is not None and MultiIndex and os.path.exists(fname_path):
                    fsize_mb = os.path.getsize(fname_path) / (1024 * 1024)
                    if fsize_mb > sizelimit * 1.1:
                        needs_prune = True

                # --- 模式 A: 智能重构 (内存合并 + 内存裁切 -> 一次写盘) ---
                if needs_prune:
                    log.warning(f"⚡ [HDF-TRUNCATE] Memory-side pruning triggered for {fname} (Size: {os.path.getsize(fname_path)/1024/1024:.1f}MB)")
                    try:
                        # [FIX] ⚡ 规避 0xc0000374 Heap Corruption：
                        # 在读取超大 HDF5 前，清理所有残留句柄并执行垃圾回收
                        try:
                            tables.file._open_files.close_all()
                        except Exception:
                            pass
                        
                        gc.collect()

                        # 使用 read_hdf 直接读取，减少句柄持有时间
                        hist_df = pd.read_hdf(fname_path, key=table)
                        
                        # 合并新旧数据并去重裁切
                        if hist_df is not None and not hist_df.empty:
                            # --- 1. 合并 + 强制规范 ---
                            full_df = (
                                pd.concat([hist_df, df])
                                .sort_index(level=['code', 'ticktime'])
                                .reset_index()
                                .drop_duplicates(subset=['code', 'ticktime'], keep='last')
                                .set_index(['code', 'ticktime'])
                                .sort_index()
                            )

                            # --- 2. 分组统计与动态裁切参数 ---
                            # [FIX] ⚡ 移动分组统计至参数计算前，避免 NameError
                            group_sizes = full_df.groupby(level='code').size()
                            num_codes = len(group_sizes)
                            
                            trigger_ratio = 1.2      # 超过120%才触发（防抖）
                            shrink_ratio = 0.8       # 保留80%
                            min_rows = 50            # 每个code最少保留

                            if num_codes > 1000:
                                # 动态推算：总容量(bytes) / 平均单行大小(85 bytes) / 总股数
                                calculated_safe = int(sizelimit * 1024 * 1024 / 85 / num_codes)
                                safe_rows = max(min_rows, calculated_safe)
                            else:
                                safe_rows = 3000

                            # --- 4. 判断是否需要裁切（按code，而不是全局）---
                            if (group_sizes > safe_rows * trigger_ratio).any():

                                result = []

                                for code, sub_df in full_df.groupby(level='code'):
                                    n = len(sub_df)

                                    if n > safe_rows * trigger_ratio:
                                        # 👉 触发裁切：保留80%
                                        keep_n = max(min_rows, int(n * shrink_ratio))
                                        sub_df = sub_df.tail(keep_n)

                                    # 未超限的不动
                                    result.append(sub_df)

                                truncated_df = (
                                    pd.concat(result)
                                    .sort_index(level=['code', 'ticktime'])
                                )

                                # --- 5. 写入 ---
                                with pd.HDFStore(temp_fname, mode='w', complib=complib) as tmp_h5:
                                    put_table_safe(tmp_h5, table, truncated_df,
                                                   MultiIndex=MultiIndex,
                                                   rewrite=True,
                                                   complib=complib)

                                truncated_triggered = True
                                log.warning(
                                    f"✅ [HDF-TRUNCATE] Dynamic prune complete. "
                                    f"Rows: {len(hist_df)} -> {len(truncated_df)}"
                                )

                                del hist_df, full_df, truncated_df
                                gc.collect()

                            else:
                                needs_prune = False

                        else:
                            needs_prune = False

                    except Exception as pe:
                        log.error(f"❌ [HDF-TRUNCATE] Memory-side prune failed (0xc0000374 risk mitigated): {pe}. Falling back to normal append.")
                        needs_prune = False
                        if os.path.exists(temp_fname):
                            try: os.remove(temp_fname)
                            except: pass

                # --- 模式 B: 常规快速追加 (Copy -> Append) ---
                if not needs_prune:
                    if os.path.exists(fname_path):
                        shutil.copy2(fname_path, temp_fname)
                    
                    try:
                        if MultiIndex:
                            df = normalize_SCHEMA(df)
                        with pd.HDFStore(temp_fname, mode='a', complib=complib) as tmp_h5:
                            put_table_safe(tmp_h5, table, df, MultiIndex=MultiIndex, rewrite=rewrite, complib=complib)
                    except ValueError as ve:
                        if "cannot match existing table structure" in str(ve):
                            # [AUTO-FIX] ⚡ schema 不匹配自愈：
                            # 1. 读取原文件全量历史数据
                            # 2. 与新数据 concat + 去重
                            # 3. 以 mode='w' 统一 schema 全量写入，保留所有历史
                            log.warning(f"⚠️ [SCHEMA-MISMATCH] {fname}[{table}] schema mismatch, rebuilding with full history: {ve}")
                            if os.path.exists(temp_fname):
                                try: os.remove(temp_fname)
                                except: pass
                            try:
                                hist_df = pd.read_hdf(fname_path, key=table) if os.path.exists(fname_path) else pd.DataFrame()
                            except Exception as re:
                                log.error(f"[SCHEMA-FIX] Failed to read history, writing new data only: {re}")
                                hist_df = pd.DataFrame()
                            if not hist_df.empty:
                                merged_df = pd.concat([hist_df, df])
                                merged_df = merged_df[~merged_df.index.duplicated(keep='last')]
                            else:
                                merged_df = df
                            with pd.HDFStore(temp_fname, mode='w', complib=complib) as tmp_h5:
                                put_table_safe(tmp_h5, table, merged_df, MultiIndex=MultiIndex, rewrite=True, complib=complib)
                            log.warning(f"✅ [SCHEMA-FIX] {fname}[{table}] rebuilt with {len(merged_df)} rows (hist={len(hist_df)}, new={len(df)}), schema restored.")
                            del hist_df, merged_df
                        else:
                            raise

            # --- 阶段 2: 安全替换原文件 ---
            if os.path.exists(temp_fname) and os.path.getsize(temp_fname) > 1024:
                success = False
                # 注意：SafeHDFStore 内部已经有关闭逻辑，但在 replace 前需确保所有 tmp_h5 句柄已销毁
                success = False
                with SafeHDFStore(fname, mode='a') as h5:
                    # SafeHDFStore 获取了进程锁，但它自己也打开了文件。
                    # 我们需要关闭它内部的句柄才能进行 os.replace/os.remove
                    h5.close() 
                    
                    # 🚀 安全替换原文件逻辑：不再调用全局 tables.file._open_files.close_all() 以免中断其他线程
                    max_retry = 3  # 增加重试次数，应对高频读写冲突
                    for r in range(max_retry):
                        try:
                            # [FIX] ⚡ 核心保护：原子替换前必须预检源文件是否存在
                            # 防止由于外部清理或文件系统异常导致 temp_fname 丢失，从而触发后续可能的级联错误
                            if not os.path.exists(temp_fname):
                                log.error(f"❌ [CRITICAL] Source temp file MISSING before replace: {temp_fname}. Replacement ABORTED to protect original file.")
                                break

                            # 优先直接使用 os.replace (原子操作)
                            os.replace(temp_fname, fname_path)
                            success = True
                            log.debug(f"✅ Atomic replace successful: {fname} (attempt {r+1})")
                            break
                        except Exception as re:
                            # 针对 [WinError 5] 等权限错误，采用指数退避策略
                            wait_time = 0.3 * (2 ** r) + random.uniform(0, 0.2)
                            if r == max_retry - 1:
                                log.error(f"Final replace attempt failed after {max_retry} retries: {re}")
                                break
                            if isinstance(re, PermissionError):
                                log.error(f"❌ [CRITICAL] File Locked: {fname} is being held by another process! "
                                          f"Please check and KILL stale python processes (e.g. PID {os.getpid()} or others in screenshot). "
                                          f"Check if you have multiple 'python.exe' instances running in Task Manager.")

                            wait_time = 0.3 * (r + 1)
                            
                            # 深度清理句柄记录，不执行全局关闭
                            gc.collect()
                            
                            # 若前三次 replace 都失败，尝试强制删除原文件以打破死锁
                            if r >= 3:
                                try:
                                    if os.path.exists(fname_path):
                                        os.remove(fname_path)
                                except: pass
                            
                            time.sleep(wait_time)
                
                if not success:
                    # 关键：如果替换失败，报错并退出，但不删除 temp_fname，防止数据彻底丢失
                    log.critical(f"❌ [DATA-LOSS-ABORT] Failed to replace {fname_path}. Data preserved in {temp_fname}")
                    return False

            # 空间整理逻辑
            if truncated_triggered:
                fsize_final = os.path.getsize(fname_path) / (1024 * 1024)
                if not is_work_time or fsize_final > sizelimit * 1.2:
                    log.warning(f"[HDF-REPACK] Physical repack for {fname} (Size: {fsize_final:.1f}MB)")
                    repack_hdf_db(fname, complib=complib)
                else:
                    log.warning(f"⚡ [HDF-REPACK] Skipped during work time.")
                
        except Exception as e:
            log.exception(f"❌ HDF Write failure: {e}")
            # 只有在非替换阶段发生错误时，才尝试清理 temp_fname
            # 实际上在 replace 逻辑里我们已经有了 return False 保护
            return False

    duration = time.time() - time_t
    if duration > 3.0 and is_work_time:
        log.warning(f"⚠️ [SLOW] write_hdf_db is slow: {fname} took {duration:.2f}s (is_work_time={is_work_time})")
    log.debug("write hdf total time:%0.2f" % (time.time() - time_t))
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
        # if timelimit and not dd.empty and not (cct.is_trade_date() and 1130 < cct.get_now_time_int() < 1300):
        if timelimit and not dd.empty and cct.get_work_time():
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
                # if not (cct.is_trade_date() and 1130 < cct.get_now_time_int() < 1300) and timelimit and len(dd) > 0:
                if cct.get_work_time() and timelimit:
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
                        # 🚀 [STALENESS-PROTECT] 使用 max 而非 mean，确保只要有一批数据过期，整表就触发刷新
                        l_time = np.max(o_time) if len(o_time) > 0 else 0.0
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
                        if code_l is None:
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
                # if not (cct.is_trade_date() and 1130 < cct.get_now_time_int() < 1300) and timelimit:
                if cct.get_work_time() and timelimit:
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
                        # 🚀 [STALENESS-PROTECT] 使用 max 而非 mean
                        l_time = np.max(o_time)
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
    # -------------------------
    # Post-process & cleanup (与原逻辑保持一致)
    # -------------------------
    duration = time.time() - time_t
    if duration > 2.0:
        log.warning(f"⚠️ [SLOW] load_hdf_db slow: {fname} table:{table} took {duration:.2f}s (Rows: {len(df) if df is not None else 0})")

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

    # repair_sina_multiindex_file()

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


    import numpy as np
    import pandas as pd
    from scipy.stats import linregress

    import numpy as np
    import pandas as pd

    def intraday_ma_high_trend_extreme_v5(df, price_col='close', llastp_col='llastp', high_col='high', vol_col='volume'):
        """
        V6 极限性能版：彻底绕过索引提取，直接内存块操作。
        预期耗时：比 V5 快 3-5 倍，通常在数百毫秒内完成。
        """
        # 1. 快速过滤 (只取成交量 > 0)
        df = df[df[vol_col] > 0]
        
        # 2. 关键：一次性提取所有列的底层数组，避免重复查找列名
        # 直接通过 .values 拿到 2D 数组或逐列提取，减少 DataFrame 封装开销
        prices = df[price_col].values
        highs = df[high_col].values
        vols = df[vol_col].values
        refs = df[llastp_col].values
        
        # 3. 极限识别边界：不使用 get_level_values(0)，直接用 MultiIndex 的 codes
        # codes[0] 是 MultiIndex 第一个层级的整数索引映射，比提取字符串快 10 倍以上
        multi_codes = df.index.codes[0]
        
        # 识别 code 变化位置
        change_idx = np.where(multi_codes[1:] != multi_codes[:-1])[0] + 1
        split_indices = np.concatenate(([0], change_idx, [len(multi_codes)]))
        first_idx = split_indices[:-1]
        last_idx = split_indices[1:] - 1
        counts = np.diff(split_indices)

        # 4. 纯 NumPy 矢量计算 (无任何 Pandas 介入)
        # [涨幅与偏离度]
        final_p = prices[last_idx]
        open_r = refs[first_idx]
        rets = (final_p - open_r) / (open_r + 1e-9)
        
        # [VWAP 计算]
        pv_sum = np.add.reduceat(prices * vols, first_idx)
        vol_sum = np.add.reduceat(vols, first_idx)
        vwaps = pv_sum / (vol_sum + 1e-9)
        bias = (final_p - vwaps) / (vwaps + 1e-9)

        # [站上均线比例]
        vwap_rep = np.repeat(vwaps, counts)
        above_ratio = np.add.reduceat((prices > vwap_rep), first_idx) / counts

        # [线性回归斜率 - 预计算 x 和 n 减少重复开销]
        x_total = np.arange(len(multi_codes)) - np.repeat(first_idx, counts)
        max_v_rep = np.repeat(np.maximum.reduceat(vols, first_idx), counts)
        y_total = highs * (1 + vols / (max_v_rep + 1e-9))
        
        sx, sy = np.add.reduceat(x_total, first_idx), np.add.reduceat(y_total, first_idx)
        sxy, sx2 = np.add.reduceat(x_total * y_total, first_idx), np.add.reduceat(x_total * x_total, first_idx)
        
        denom = (counts * sx2 - sx**2)
        slopes = np.divide((counts * sxy - sx * sy), denom, out=np.zeros_like(sxy), where=denom != 0)

        # 5. 结果组装 (此时才访问一次 index 拿到真正的 code 标签)
        unique_codes = df.index.levels[0][multi_codes[first_idx]]
        
        res = pd.DataFrame({
            'ret': rets,
            'bias': bias,
            'above': above_ratio,
            'slope': slopes,
            'is_up': slopes > 0
        }, index=pd.Index(unique_codes, name='code'))

        # 6. Rank 评分优化：手动加权
        # 如果数据量极大，rank 会成为瓶颈。如果只选 Top，可以考虑先过滤再 rank
        r_ret = res['ret'].rank(pct=True)
        r_bias = res['bias'].rank(pct=True)
        r_above = res['above'].rank(pct=True)
        
        res['combined_score'] = 0.5 * r_ret + 0.3 * r_bias + 0.2 * r_above
        
        return res[res['is_up']].sort_values('combined_score', ascending=False)


    def intraday_ma_high_trend_multi_day(df, price_col='close', llastp_col='llastp', high_col='high', vol_col='volume', window=None):
        """
        极限矢量化最终版：
        1. 自动处理多日分时数据 (Code + Date 联合分组)
        2. 基于 Rank(分位数) 评分，消除股价绝对值影响
        3. 修复涨幅基准 (最新价 vs 当日首行参考价)
        """
        # --- 1. 预处理 & 排序 ---
        df = df[df[vol_col] > 0].copy()
        # 确保按代码和时间严格排序，这是 reduceat 正确的前提
        df = df.sort_index(level=[0, 1])
        
        # --- 2. 提取基础数据 (NumPy 裸阵) ---
        codes = df.index.get_level_values(0).values
        # 提取日期，用于处理多日分时合并的情况
        times = df.index.get_level_values(1)
        dates = times.date if hasattr(times, 'date') else times.values
        
        prices = df[price_col].values
        highs = df[high_col].values
        vols = df[vol_col].values
        llastps = df[llastp_col].values

        # --- 3. 识别分组边界 (核心：Code变化 OR 日期变化) ---
        group_change = (codes[1:] != codes[:-1]) | (dates[1:] != dates[:-1])
        change_idx = np.where(group_change)[0] + 1
        split_indices = np.concatenate(([0], change_idx, [len(codes)]))
        counts = np.diff(split_indices)
        
        # 每一组（单票单日）的首行和末行索引
        first_idx = split_indices[:-1]
        last_idx = split_indices[1:] - 1

        # --- 4. 计算当日涨幅 (最新价 vs 当日参考价) ---
        final_closes = prices[last_idx]
        day_refs = llastps[first_idx]
        daily_returns = np.divide((final_closes - day_refs), day_refs, 
                                  out=np.zeros_like(final_closes), where=day_refs != 0)

        # --- 5. 计算 VWAP 及 站上均线比例 ---
        pv = prices * vols
        sum_pv = np.add.reduceat(pv, first_idx)
        sum_vol = np.add.reduceat(vols, first_idx)
        vwap_per_group = np.divide(sum_pv, sum_vol, out=np.zeros_like(sum_pv), where=sum_vol != 0)
        
        # 广播 VWAP 到每个 Tick 比较
        vwap_rep = np.repeat(vwap_per_group, counts)
        above_mask = (prices > vwap_rep).astype(float)
        ratio_above_ma = np.add.reduceat(above_mask, first_idx) / counts

        # --- 6. 计算高点回归斜率 (Slope) ---
        # x轴在组内归零：[0,1,2..., 0,1,2...]
        x = np.arange(len(codes)) - np.repeat(first_idx, counts)
        # y轴加权：high * (1 + vol/max_vol)
        max_vols = np.repeat(np.maximum.reduceat(vols, first_idx), counts)
        y = highs * (1 + vols / max_vols)

        sum_x = np.add.reduceat(x, first_idx)
        sum_y = np.add.reduceat(y, first_idx)
        sum_xy = np.add.reduceat(x * y, first_idx)
        sum_x2 = np.add.reduceat(x * x, first_idx)
        
        denom = (counts * sum_x2 - sum_x**2)
        slope = np.divide((counts * sum_xy - sum_x * sum_y), denom, 
                          out=np.zeros_like(sum_xy), where=denom != 0)

        # --- 7. 汇总结果并进行 Rank 评分 ---
        res_df = pd.DataFrame({
            'date': dates[first_idx],
            'daily_return': daily_returns,
            'ratio_above_ma': ratio_above_ma,
            'vwap_ma': vwap_per_group,
            'high_slope': slope,
            'high_trend': slope > 0,
            # 偏离度：解决 300042 这种爆发股的关键指标
            'price_bias': (final_closes - vwap_per_group) / vwap_per_group
        }, index=pd.Index(codes[first_idx], name='code'))

        # 百分位排名归一化 (0~1)
        res_df['score_ret']   = res_df['daily_return'].rank(pct=True)
        res_df['score_ratio'] = res_df['ratio_above_ma'].rank(pct=True)
        res_df['score_bias']  = res_df['price_bias'].rank(pct=True)
        res_df['score_slope'] = res_df['high_slope'].rank(pct=True)

        # 计算趋势得分 (权重可调)
        res_df['computed_score'] = (
            0.4 * res_df['score_ratio'] + 
            0.4 * res_df['score_bias'] + 
            0.2 * res_df['score_slope']
        )

        # 最终组合得分 (趋势50% + 涨幅50%)
        res_df['combined_score'] = (
            0.5 * res_df['computed_score'] + 
            0.5 * res_df['score_ret']
        )

        # --- 8. 过滤 & 排序 ---
        # 只保留斜率向上的，并按得分从高到低排列
        return res_df[res_df['high_trend']].sort_values(by='combined_score', ascending=False)


    

    def intraday_ma_high_trend_ultra_final(df, price_col='close', llastp_col='llastp', high_col='high', vol_col='volume', window=None):
        """
        极限性能版：NumPy 矢量化计算 + 自动归一化评分
        """
        # 1. 预处理：过滤成交量 > 0 并确保 code 连续排列
        df = df[df[vol_col] > 0].copy()
        if window:
            df = df.groupby(level=0).tail(window)
        
        # 2. 提取 NumPy 数组 (脱离 Pandas 索引)
        codes = df.index.get_level_values(0).values
        prices = df[price_col].values
        highs = df[high_col].values
        vols = df[vol_col].values
        llastps = df[llastp_col].values

        # 3. 定位分组边界 (Split indices)
        change_idx = np.where(codes[1:] != codes[:-1])[0] + 1
        split_indices = np.concatenate(([0], change_idx, [len(codes)]))
        counts = np.diff(split_indices)
        
        # 区间起始索引 (每只股票的第一行)
        first_row_indices = split_indices[:-1]
        # 4. 提取当日涨幅 (最后一行对比)
        last_row_indices = split_indices[1:] - 1
        

        # 提取价格
        final_closes = prices[last_row_indices]      # 当前最新价 (最后一行)
        initial_references = llastps[first_row_indices] # 今日开盘参考价 (第一行)

        final_llastps = llastps[last_row_indices]
        # 避免分母为 0
        # daily_returns = np.divide((final_closes - final_llastps), final_llastps, 
        #                           out=np.zeros_like(final_closes), where=final_llastps != 0)

        # 矢量计算涨幅：(最新价 - 初始价) / 初始价
        daily_returns = np.divide((final_closes - initial_references), initial_references, 
                                  out=np.zeros_like(final_closes), where=initial_references != 0)

        # 5. 向量化计算 VWAP 和 Ratio
        pv = prices * vols
        sum_pv = np.add.reduceat(pv, split_indices[:-1])
        sum_vol = np.add.reduceat(vols, split_indices[:-1])
        vwap_per_stock = np.divide(sum_pv, sum_vol, out=np.zeros_like(sum_pv), where=sum_vol != 0)
        
        # 广播 VWAP 计算 Ratio
        vwap_ma_all = np.repeat(vwap_per_stock, counts)
        above_mask = (prices > vwap_ma_all).astype(float)
        ratio_above_ma = np.add.reduceat(above_mask, split_indices[:-1]) / counts

        # 6. 向量化线性回归 (Slope)
        x = np.arange(len(codes)) - np.repeat(split_indices[:-1], counts)
        max_vols_per_stock = np.maximum.reduceat(vols, split_indices[:-1])
        y = highs * (1 + vols / np.repeat(max_vols_per_stock, counts))

        sum_x = np.add.reduceat(x, split_indices[:-1])
        sum_y = np.add.reduceat(y, split_indices[:-1])
        sum_xy = np.add.reduceat(x * y, split_indices[:-1])
        sum_x2 = np.add.reduceat(x * x, split_indices[:-1])
        
        denom = (sum_x2 - (sum_x**2 / counts))
        slope = np.divide((sum_xy - (sum_x * sum_y / counts)), denom, 
                          out=np.zeros_like(sum_xy), where=denom != 0)

        # 7. 构造结果表并进行归一化评分
        unique_codes = codes[split_indices[:-1]]
        res_df = pd.DataFrame({
            'daily_return': daily_returns,
            'ratio_above_ma': ratio_above_ma,
            'vwap_ma': vwap_per_stock,
            'high_slope': slope,
            'high_trend': slope > 0
        }, index=pd.Index(unique_codes, name='code'))

        # 归一化参数计算 (避免除0)
        vwap_max = res_df['vwap_ma'].max() or 1.0
        slope_max = res_df['high_slope'].abs().max() or 1.0

        # 趋势得分计算
        res_df['score_ratio'] = res_df['ratio_above_ma']
        res_df['score_vwap'] = res_df['vwap_ma'] / vwap_max
        res_df['score_slope'] = res_df['high_slope'].abs() / slope_max

        res_df['computed_score'] = (
            0.4 * res_df['score_ratio'] + 
            0.4 * res_df['score_vwap'] + 
            0.2 * res_df['score_slope']
        )

        # 最终组合得分
        res_df['combined_score'] = (
            0.5 * res_df['computed_score'] + 
            0.5 * res_df['daily_return']
        )

        # 8. 过滤 & 排序：只保留高点上升的股票
        return res_df[res_df['high_trend']].sort_values(by='combined_score', ascending=False)



    def recover_tick_volume_vectorized(df, vol_col='volume'):
        """

        Function: recover_tick_volume_vectorized

        Summary: gpt

        Examples: InsertHere

        Attributes: 

            @param (df):InsertHere

            @param (vol_col) default='volume': InsertHere

        Returns: InsertHere

        将累加成交量还原为每条 tick 当天独立成交量
        df: MultiIndex(code, ticktime) DataFrame，volume 是累加量
        返回新的 df，增加 'tick_volume'
        """
        df = df.copy()
            
        # 提取 MultiIndex 信息
        codes = df.index.get_level_values(0).to_numpy()
        times = df.index.get_level_values(1).to_numpy('datetime64[ns]')
        vols = df[vol_col].to_numpy()
        
        tick_volume = np.zeros_like(vols, dtype=vols.dtype)
        
        # 找到每天的开始位置
        days = times.astype('datetime64[D]')
        new_day = np.concatenate([[True], days[1:] != days[:-1]])
        
        # 找到每只股票的分段
        new_stock = np.concatenate([[True], codes[1:] != codes[:-1]])
        
        # 每个 segment (stock+day) 的起点索引
        segment_start = new_day | new_stock
        segment_idx = np.flatnonzero(segment_start)
        
        # 差分计算每段 tick 量
        for i in range(len(segment_idx)):
            start = segment_idx[i]
            end = segment_idx[i+1] if i+1 < len(segment_idx) else len(vols)
            segment = vols[start:end]
            diff = np.diff(segment, prepend=0)
            diff[0] = segment[0]  # 当天首条 tick
            diff[diff < 0] = 0    # 避免负值
            tick_volume[start:end] = diff
        
        df['tick_volume'] = tick_volume
        return df

    def recover_tick_volume_fast(df, vol_col='volume'):
        """

        Function: recover_tick_volume_fast

        Summary: google

        Examples: InsertHere

        Attributes: 

            @param (df):InsertHere

            @param (vol_col) default='volume': InsertHere

        Returns: InsertHere

        极限矢量化版本：将累积成交量还原为每 Tick 成交量
        """
        # 1. 预处理：去重 (MultiIndex 下直接使用 index.duplicated)
        df = df[~df.index.duplicated(keep='first')].copy()
        # 2. 排序 (确保 diff 计算逻辑正确)
        df = df.sort_index(level=[0, 1])
        # 3. 全量差分计算
        # 直接对整列 diff，首行会产生 NaN
        df['tick_volume'] = df[vol_col].diff()
        # 4. 关键：修复跨标的（Code）的首行数据
        # 找出每个 code 的第一行位置
        # is_first_tick 为 True 的地方，diff 的结果是错误的（它减去了上一个 code 的最后一行）
        is_first_tick = (df.index.get_level_values(0) != np.roll(df.index.get_level_values(0), 1))
        is_first_tick[0] = True # 第一行必然是首个 code
        # 修复首行：将 diff 的 NaN 或错误值替换回原始累积量
        df.loc[is_first_tick, 'tick_volume'] = df.loc[is_first_tick, vol_col]
        # 5. 过滤：去重后可能产生的 <= 0 的成交量 (包含去0)
        df = df[df['tick_volume'] > 0]
        return df

    def recover_tick_volume(df, vol_col='volume'):
        """
        将累加量 volume -> 每tick成交量，同时去重和去0
        df: MultiIndex [code, ticktime] DataFrame
        vol_col: 累加量列名
        """
        df = df.copy()

        # 确保按 code 和时间排序
        df = df.sort_index(level=[0, 1])

        # 用 groupby 对每个股票分别处理
        def recover(sub):
            sub = sub.copy()
            # 去重复 ticktime，保留第一次
            sub = sub[~sub.index.duplicated(keep='first')]

            # 还原每tick成交量
            sub['tick_volume'] = sub[vol_col].diff().fillna(sub[vol_col])
            # 去0成交量
            sub = sub[sub['tick_volume'] > 0]

            return sub

        df = df.groupby(level=0, group_keys=False).apply(recover)
        return df
    with timed_ctx("get_tdx_all_MultiIndex_h5"):
        dd=get_tdx_all_MultiIndex_h5()
    with timed_ctx("recover_tick_volume_fast_Google"):
        df=recover_tick_volume_fast(dd)
    # with timed_ctx("recover_tick_volume_vectorized_GPT"):
    #     df=recover_tick_volume_vectorized(dd)
    # 使用示例
    import warnings
    warnings.filterwarnings("ignore")
    with timed_ctx("intraday_ma_high_trend_fast_ultra_google"):
        # df_result = intraday_ma_high_trend_ultra_final(df)
        # df_result = intraday_ma_high_trend_multi_day(df)
        df_result = intraday_ma_high_trend_extreme_v5(df)
    print(df_result[:30])
    cct.print_timing_summary()
    import ipdb;ipdb.set_trace()

    # with tables.open_file(r"G:\sina_MultiIndex_data.h5") as f: print(f)
    # with tables.open_file(r"G:\sina_data.h5") as f: print(f)
    # h5=get_tdx_all_from_h5()
    
    # print(hm5.memory_usage(deep=True).sum() / 1024**2, "MB")
    # hm5.to_hdf(r"G:\sina_MultiIndex_data_clean.h5", key="all_30/table", mode="w", format="table", complib="blosc", complevel=9)
    # print(f"sina_data:{check_hdf(h5_fname='tdx_all_df_300',h5_table='all')}")
    print(f"sina_data:{check_hdf(h5_fname='sina_data',h5_table='all')}")
    sina = read_sina_df(h5_fname='sina_data',h5_table='all')
    df_diagnose(sina)
    import ipdb;ipdb.set_trace()

    sina_MultiD_path = "G:\\sina_MultiIndex_data.h5"
    freq='5T'
    startime = None
    endtime = '15:01:00'

    print('sina_MultiD_path:{sina_MultiD_path}')
    # if os.path.exists(sina_MultiD_path) and os.path.getsize(sina_MultiD_path) > 500:

    if os.path.exists(sina_MultiD_path) and os.path.getsize(sina_MultiD_path) > 5000:
        h5 = readHdf5(sina_MultiD_path)
        h5.shape
        codelist = ['920082' ,'000002']

        for co in codelist:
            if co in h5.index:
                print(h5.loc[co])
        df_diagnose(h5)

        mdf = cct.get_limit_multiIndex_freq(h5, freq=freq.upper(),  col='all', start=startime, end=endtime, code=None)
        codelist2 = ['002151' ,'300516', '300245','300516']
        for co in codelist:
            if co in mdf.index:
                print(f'code:{co} :{mdf.loc[co]}')
        

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
