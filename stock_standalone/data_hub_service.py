# -*- coding: utf-8 -*-
"""
统一数据中心服务 (Data Hub Service)

职责：
1. 统一管理和持久化全量预计算数据 (df_all)，采用 HDF5 提供高并发只读共享。
2. 解决多进程环境下的数据访问孤岛问题，避免独立进程重复扫盘计算。
3. 提供原子化的写入机制，保证读取时不被锁定抛出异常(PermissionError)。
4. (可选) 提供高速 Tick 共享内存字典或 Queue 分发。

Created: 2026-03-08
"""

import os
import time
import uuid
import logging
import pandas as pd
from typing import Optional, Dict, Any
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger("DataHub")

class DataHubService:
    """数据中心单例服务"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls, base_dir=None):
        if cls._instance is None:
            # 🚀 [NEW] Default to RAMDisk path if not specified
            if base_dir is None:
                ramdisk_file = cct.get_ramdisk_path("minute_kline_cache.pkl")
                base_dir = os.path.dirname(ramdisk_file)
                logger.info(f"[DataHub] Redirecting storage to RAMDisk: {base_dir}")
                
            cls._instance = cls(base_dir)
        return cls._instance
        
    def __init__(self, base_dir="data"):
        self.base_dir = base_dir
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)
            
        self.df_all_path = os.path.join(self.base_dir, "shared_df_all.h5")
        self.tick_cache_path = os.path.join(self.base_dir, "shared_tick_cache.h5")
        
        # 记录最近一次加载的 df_all 和它的修改时间，用于进程内缓存
        self._cached_df = None
        self._cached_mtime = 0.0
        
        # Tick 缓存机制
        self._cached_tick_df = None
        self._cached_tick_mtime = 0.0

    def publish_df_all(self, df: pd.DataFrame) -> bool:
        """
        发布全局预计算数据框 (df_all) 到 HDF5 文件。
        采用原子替换操作以支撑 Windows 环境下的多进程安全机制。
        """
        if df is None or df.empty:
            logger.warning("[DataHub] Attempted to publish an empty df_all.")
            return False
            
        # 1. 写入临时文件，避免写入中途被读取
        temp_file = self.df_all_path + f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
        
        try:
            # 使用 fixed 格式写入，读取速度最快
            df.to_hdf(temp_file, key='df_all', mode='w', format='fixed')
            
            # 2. 从临时文件原子替换目标文件
            # Windows 的 os.replace 是原子级的，如果目标文件正被其他工具占用，可能抛出 PermissionError
            max_retries = 20
            retry_delay = 0.05
            
            for i in range(max_retries):
                try:
                    os.replace(temp_file, self.df_all_path)
                    logger.info(f"[DataHub] Successfully published df_all ({len(df)} rows) to {self.df_all_path}")
                    return True
                except PermissionError:
                    time.sleep(retry_delay)
                    continue
                except FileNotFoundError:
                    # 原文件可能被别人删了，无妨，我们再次重试即可
                    time.sleep(retry_delay)
                    continue
            
            logger.error("[DataHub] Failed to publish df_all due to persistent file locks on Windows.")
            return False
            
        except Exception as e:
            logger.error(f"[DataHub] Error writing df_all HDF5: {e}", exc_info=True)
            return False
        finally:
            # 收尾清理可能的残留临时文件
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

    def get_df_all(self, force_reload: bool = False, max_wait_sec: float = 2.0) -> Optional[pd.DataFrame]:
        """
        跨进程加载全局 df_all 数据框。
        内置文件修改时间缓存以避免频繁读盘。
        
        Args:
            force_reload: 是否绕过内存缓存强制读取盘中新文件
            max_wait_sec: 当文件刚好在被覆盖写入时，最大等待重试时间。
        """
        if not os.path.exists(self.df_all_path):
            # logger.debug(f"[DataHub] No published df_all found at {self.df_all_path}")
            return None
            
        # 检查文件是否是今天的 (如果是旧数据，也视为过期)
        import datetime
        file_date = datetime.date.fromtimestamp(os.path.getmtime(self.df_all_path))
        if file_date < datetime.date.today():
             logger.info(f"[DataHub] df_all file is stale ({file_date}).")
             return None

        start_time = time.time()
        
        # 检查是否需要更新缓存
        try:
            current_mtime = os.path.getmtime(self.df_all_path)
        except OSError:
            current_mtime = 0.0
            
        if not force_reload and self._cached_df is not None and self._cached_mtime == current_mtime:
            return self._cached_df
            
        while time.time() - start_time < max_wait_sec:
            try:
                df = pd.read_hdf(self.df_all_path, key='df_all')
                
                # 更新缓存
                self._cached_df = df
                self._cached_mtime = os.path.getmtime(self.df_all_path)
                
                return df
                
            except (PermissionError, OSError) as e:
                # 刚好在替换的纳秒级别，或者被其他杀毒软件锁住
                time.sleep(0.05)
            except Exception as e:
                # pandas 的读取异常或者文件结构被破坏？
                logger.error(f"[DataHub] Error reading df_all HDF5: {e}")
                return None
                
        logger.error(f"[DataHub] Timeout waiting to read df_all from {self.df_all_path}")
        return None

    def publish_tick_cache(self, df: pd.DataFrame) -> bool:
        """
        发布分钟线/Tick 缓存数据到 HDF5 文件。同样具备多进程原子写入安全。
        """
        pass
        if df is None or df.empty:
            return False
            
        temp_file = self.tick_cache_path + f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
        try:
            # Drop datetimes if any, usually MinuteKlineCache has int32 time
            df.to_hdf(temp_file, key='tick_cache', mode='w', format='fixed')
            
            max_retries = 20
            retry_delay = 0.05
            for i in range(max_retries):
                try:
                    os.replace(temp_file, self.tick_cache_path)
                    logger.info(f"[DataHub] Successfully published tick cache ({len(df)} rows)")
                    return True
                except PermissionError:
                    time.sleep(retry_delay)
                    continue
                except FileNotFoundError:
                    time.sleep(retry_delay)
                    continue
            
            logger.error("[DataHub] Failed to publish tick cache due to locks.")
            return False
        except Exception as e:
            logger.error(f"[DataHub] Error writing tick cache: {e}", exc_info=True)
            return False
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

    def get_tick_cache(self, code: Optional[str] = None, force_reload: bool = False, max_wait_sec: float = 2.0) -> Optional[pd.DataFrame]:
        """
        获取共享的分钟级或Tick缓存。可以单独过滤出一只股票。
        """
        if not os.path.exists(self.tick_cache_path):
            return None
            
        start_time = time.time()
        try:
            current_mtime = os.path.getmtime(self.tick_cache_path)
        except OSError:
            current_mtime = 0.0
            
        if not force_reload and self._cached_tick_df is not None and self._cached_tick_mtime == current_mtime:
            df = self._cached_tick_df
        else:
            df = None
            while time.time() - start_time < max_wait_sec:
                try:
                    df = pd.read_hdf(self.tick_cache_path, key='tick_cache')
                    self._cached_tick_df = df
                    self._cached_tick_mtime = os.path.getmtime(self.tick_cache_path)
                    break
                except (PermissionError, OSError):
                    time.sleep(0.05)
                except Exception as e:
                    logger.error(f"[DataHub] Error reading tick cache: {e}")
                    return None
            
        if df is None:
            return None
            
        if code is not None:
            code_pad = str(code).zfill(6)
            if 'code' in df.columns:
                stock_df = df[df['code'] == code_pad].copy()
                if 'time' in stock_df.columns:
                    stock_df = stock_df.sort_values('time')
                return stock_df
        return df

    def cleanup(self):
        """退出前清理"""
        if self._cached_df is not None:
             self._cached_df = None
             
        # Optional: remove the hdf5 if we want fresh start daily
        pass
