# -*- coding: utf-8 -*-
"""
MarketStateBus - 全局行情状态总线 (P0-3)
用于取代多进程/多线程之间的 Queue 传递，实现“覆盖式”发布与“拉取式”订阅。
核心优势：消除 Queue 堆积延迟，消费者永远读到最新快照。
"""

import threading
import time
import pandas as pd
import logging

logger = logging.getLogger("MarketStateBus")

class MarketStateBus:
    """
    全局行情状态总线 - 单例模式
    """
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'): return
        self._data_lock = threading.Lock()
        self._df_all = pd.DataFrame()          # 完整行情 DataFrame
        self._df_filtered = pd.DataFrame()     # 过滤后的 UI DataFrame (用于展示)
        self._version = 0
        self._timestamp = 0
        self._initialized = True
    
    def publish(self, df_all, df_filtered=None):
        """
        生产者调用（通常在 update_tree 或 fetch_and_process 线程中）
        O(1) 覆盖写入。
        """
        if df_all is None or df_all.empty:
            return
            
        with self._data_lock:
            self._df_all = df_all
            self._df_filtered = df_filtered if df_filtered is not None else df_all
            self._version += 1
            self._timestamp = time.time()
            
    def get_latest(self, since_version=0):
        """
        消费者调用 - 返回 (version, df_all, df_filtered, timestamp)
        如果 since_version 等于当前版本，返回 None (避免重复处理)
        """
        with self._data_lock:
            if self._version <= since_version:
                return None
            return (self._version, self._df_all, self._df_filtered, self._timestamp)

    def get_latest_version(self):
        with self._data_lock:
            return self._version

class AtomicStateStore:
    """
    UI 专用原子快照存储 (P0-2)
    用于解决 Tk 主线程刷新阻塞问题。
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = None
        self._version = 0
        self._last_read_version = -1
    
    def update(self, data):
        """写入端：覆盖旧值"""
        with self._lock:
            self._snapshot = data
            self._version += 1
    
    def pull(self):
        """读取端：获取最新快照，如果没变化返回 None"""
        with self._lock:
            if self._version == self._last_read_version:
                return None
            self._last_read_version = self._version
            return self._snapshot
