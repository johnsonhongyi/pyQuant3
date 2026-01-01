# -*- coding:utf-8 -*-
import time
import pandas as pd
import numpy as np
from collections import deque, defaultdict
from typing import Dict, List, Optional, Callable, Any
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger()

class MinuteKlineCache:
    """
    分时K线缓存
    每股保留最近 N 根 1分钟K线
    """
    def __init__(self, max_len: int = 240):
        self.max_len = max_len
        # {code: deque([{'time':..., 'open':..., ...}, ...])}
        # 使用普通 dict 替代 defaultdict(lambda...) 以支持 pickle
        self.cache: Dict[str, deque] = {}
        self.last_update_ts: Dict[str, float] = {}

    def get_klines(self, code: str, n: int = 60):
        if code not in self.cache:
            return []
        return list(self.cache[code])[-n:]

    def update(self, code: str, tick: dict):
        """
        使用实时 Tick 更新 K 线
        tick: {'time': str/int, 'price': float, 'volume': float, ...}
        """
        try:
            price = float(tick.get('trade', 0) or tick.get('now', 0))
            if price == 0: return

            # 简单时间戳处理，实际应解析 tick['time'] 对应分钟
            # 这里假设 tick 是最新的，直接使用当前系统时间分钟对齐
            # 或者使用 tick 中的 timestamp
            
            # 确保 code 存在于缓存中
            if code not in self.cache:
                self.cache[code] = deque(maxlen=self.max_len)
            klines = self.cache[code]
            
            # 构造 KLine Item
            # 实际生产中应更严谨处理时间
            ts = int(time.time())
            minute_ts = ts - (ts % 60) # 对齐到分钟
            
            # 获取当前累计成交量
            current_cum_vol = float(tick.get('volume', 0))
            
            if not klines:
                # 初始化第一根 K 线
                klines.append({
                    'time': minute_ts,
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': 0, # Temporarily 0 or wait for next tick diff
                    'cum_vol_start': current_cum_vol # Record start volume
                })
            else:
                last_k = klines[-1]
                if last_k['time'] == minute_ts:
                    # 同一分钟：更新 H/L/C
                    last_k['high'] = max(last_k['high'], price)
                    last_k['low'] = min(last_k['low'], price)
                    last_k['close'] = price
                    
                    # Calculate volume from start of this minute
                    # If 'cum_vol_start' missing (old cache), reset it
                    if 'cum_vol_start' not in last_k:
                        last_k['cum_vol_start'] = current_cum_vol
                    
                    last_k['volume'] = current_cum_vol - last_k['cum_vol_start']
                else:
                    # 新的一分钟
                    klines.append({
                        'time': minute_ts,
                        'open': price,
                        'high': price,
                        'low': price,
                        'close': price,
                        'volume': 0, 
                        'cum_vol_start': current_cum_vol # Start from current cumulative
                    })
        except Exception as e:
            logger.error(f"MinuteKlineCache update error: {e}")

class TickAggregator:
    """
    Tick 聚合器
    用于追踪 tick 级别的买卖盘口变化
    """
    def __init__(self):
        self.last_ticks = {}
    
    def process(self, code: str, current_tick: dict):
        # 简单比对上一笔 tick 计算主动买卖
        # 暂时只做占位，后续扩展 Level2 分析
        pass

class IntradayEmotionTracker:
    """
    盘中情绪追踪器
    计算个股及市场情绪分
    """
    def __init__(self):
        self.scores = {} # {code: score}

    def update_batch(self, df: pd.DataFrame):
        """
        批量更新情绪分
        df: 包含 'percent', 'amount', 'volume' 等列
        """
        try:
            if df.empty: return
            
            # 简单算法示例：涨幅 + 量比贡献
            # 实际逻辑可迁移原 Emotion 算法
            # 这里仅做简单映射作为占位
            if 'percent' in df.columns:
                # 归一化 emotion score 0-100
                # 假设 percent > 9 为 100, < -9 为 0
                self.scores = df.set_index('code')['percent'].to_dict()
                
        except Exception as e:
            logger.error(f"IntradayEmotionTracker update error: {e}")

    def get_score(self, code: str) -> float:
        return self.scores.get(code, 50.0) # 默认 50 中性

import os
try:
    import psutil
except ImportError:
    psutil = None

class DataPublisher:
    """
    数据分发器 (核心入口)
    """
    def __init__(self):
        self.kline_cache = MinuteKlineCache()
        self.emotion_tracker = IntradayEmotionTracker()
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        
        # Performance Tracking
        self.start_time = time.time()
        self.update_count = 0
        self.total_rows_processed = 0
        self.last_batch_time = 0
        self.batch_rates = deque(maxlen=10) # Last 10 batch rates (rows/sec)
        
    def update_batch(self, df: pd.DataFrame):
        """
        接收来自 fetch_and_process 的 DataFrame 快照
        """
        try:
            if df.empty: return

            # Fix: Ensure 'code' exists as a column (often in index)
            if 'code' not in df.columns:
                df = df.copy()
                df['code'] = df.index

            t0 = time.time()
            rows_count = len(df)
            self.update_count += 1
            self.total_rows_processed += rows_count
            
            # 1. 深度情绪计算 (Vectorized)
            if 'percent' in df.columns:
                # 基础分：50 + 涨幅 * 3 (10% -> 80分, -10% -> 20分)
                base_score = 50 + (df['percent'] * 3)
                
                # 量能加权 (假设 ratio 为量比, 如果没有则默认为 1)
                vol_ratio = df['ratio'] if 'ratio' in df.columns else 1.0
                
                # 动量修正：量比 > 1.5 且同向，加大情绪波动
                momentum = (vol_ratio - 1.0).clip(lower=0) * df['percent'] * 0.5
                
                final_score = base_score + momentum
                
                # 特殊状态修正
                # 恐慌盘：跌幅 > 7% 且放量 -> 极低分
                # 抢筹：涨幅 > 7% 且放量 -> 极高分
                mask_panic = (df['percent'] < -7) & (vol_ratio > 1.5)
                mask_mania = (df['percent'] > 7) & (vol_ratio > 1.5)
                
                final_score.loc[mask_panic] -= 15
                final_score.loc[mask_mania] += 15
                
                # 限制在 0-100
                final_score = final_score.clip(0, 100)
                
                # Check for existing emotion score in DF (from upstream)
                if 'scan_score_emotion' in df.columns:
                    self.emotion_tracker.scores = df.set_index('code')['scan_score_emotion'].to_dict()
                else:
                    self.emotion_tracker.scores = dict(zip(df['code'], final_score))

            # Update global last update timestamp
            self.kline_cache.last_update_ts['global'] = time.time()

            # 2. 更新 KLine (仅更新订阅或活跃股)
            # Optimization: Convert to dict records only for relevant columns
            cols = ['code', 'trade', 'volume', 'high', 'low', 'open', 'amount']
            valid_cols = [c for c in cols if c in df.columns]
            
            # 过滤无效价格
            if 'trade' in df.columns:
                active_df = df[df['trade'] > 0]
                rows = active_df[valid_cols].to_dict('records')
                
                for row in rows:
                    code = row.get('code')
                    if code and (code in self.kline_cache.cache or code in self.subscribers):
                        self.kline_cache.update(code, row)
            
            # Record Speed
            t1 = time.time()
            duration = t1 - t0
            if duration > 0:
                self.batch_rates.append(rows_count / duration)
            self.last_batch_time = t1
            
        except Exception as e:
            logger.error(f"DataPublisher update_batch error: {e}")

    def subscribe(self, code: str, callback: Callable):
        self.subscribers[code].append(callback)

    def get_minute_klines(self, code: str, n: int = 60):
        return self.kline_cache.get_klines(code, n)

    def get_emotion_score(self, code: str):
        return self.emotion_tracker.get_score(code)

    def stress_test(self, num_stocks=4000, n_klines=240):
        """内存压力测试"""
        import sys
        print(f"Starting Stress Test: {num_stocks} stocks, {n_klines} klines each...")
        dummy_data = {
            'time': 1700000000, 'open': 10.0, 'high': 11.0, 'low': 9.0, 'close': 10.5, 'volume': 1000
        }
        for i in range(num_stocks):
            code = f"600{i:03d}"
            for _ in range(n_klines):
                self.kline_cache.cache[code].append(dummy_data)
        
        # 估算内存
        # 这是一个粗略估算
        # 实际对象开销较大
        print("Stress Test Populated. Check Task Manager for memory usage.")
        
    def get_status(self) -> Dict[str, Any]:
        """
        获取服务运行状态监控指标
        """
        try:
            # Memory Usage
            mem_info = "N/A"
            if psutil:
                process = psutil.Process(os.getpid())
                mem_bytes = process.memory_info().rss
                mem_info = f"{mem_bytes / 1024 / 1024:.2f} MB"
            
            # Speed
            avg_speed = 0
            if self.batch_rates:
                avg_speed = sum(self.batch_rates) / len(self.batch_rates)
            
            uptime = time.time() - self.start_time
            
            return {
                "klines_cached": len(self.kline_cache.cache),
                "subscribers": sum(len(v) for v in self.subscribers.values()),
                "emotions_tracked": len(self.emotion_tracker.scores),
                "last_update": self.kline_cache.last_update_ts.get("global", 0),
                "server_time": time.time(),
                "uptime_seconds": int(uptime),
                "memory_usage": mem_info,
                "total_rows_processed": self.total_rows_processed,
                "update_count": self.update_count,
                "processing_speed_row_per_sec": int(avg_speed),
                "pid": os.getpid()
            }
        except Exception as e:
            logger.error(f"get_status error: {e}")
            return {"error": str(e)}
