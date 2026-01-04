# -*- coding:utf-8 -*-
import time
import threading
import pandas as pd
from collections import deque, defaultdict
from typing import Callable, Any, Dict, List, Union, Optional
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips  as cct
import psutil
import os
import sqlite3

logger = LoggerFactory.getLogger()

# Lightweight K-line item using __slots__ to save memory
class KLineItem:
    __slots__ = ('time', 'open', 'high', 'low', 'close', 'volume', 'cum_vol_start')
    def __init__(self, time: int, open: float, high: float, low: float, close: float, volume: float, cum_vol_start: float):
        self.time = time
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.cum_vol_start = cum_vol_start
    
    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

class MinuteKlineCache:
    """
    分时K线缓存
    每股保留最近 N 根 1分钟K线
    """
    def __init__(self, max_len: int = 240):
        self.max_len = max_len
        # {code: deque([KLineItem, ...])}
        self.cache: dict[str, deque] = {}
        self.last_update_ts: dict[str, float] = {}

    def set_mode(self, max_len: int):
        """动态切换回溯时长：不清除数据，仅裁剪旧节点以回收内存"""
        if self.max_len != max_len:
            logger.info(f"✂️ MinuteKlineCache Trimming: {self.max_len} -> {max_len} nodes")
            self.max_len = max_len
            # 对所有现有数据进行重建以同步 maxlen 属性
            for code in list(self.cache.keys()):
                dq = self.cache[code]
                # 无论当前长度如何，都必须重建 deque 以修改只读的 maxlen 属性
                self.cache[code] = deque(list(dq)[-max_len:], maxlen=max_len)

    def clear(self):
        """完全清空缓存"""
        self.cache.clear()
        self.last_update_ts.clear()

    def get_klines(self, code: str, n: int = 60) -> list:
        if code not in self.cache:
            return []
        nodes = list(self.cache[code])[-n:]
        # Support dict-based access for existing strategy code
        return [node.as_dict() for node in nodes]

    def update(self, code: str, tick: dict):
        """
        使用实时 Tick 更新 K 线 (保留单条更新接口用于兼容性)
        """
        try:
            price = float(tick.get('trade', 0) or tick.get('now', 0))
            if price <= 0: return

            ts = int(tick.get('timestamp') or time.time())
            minute_ts = ts - (ts % 60)
            
            # 使用更轻量、无函数调用开销的内部逻辑
            self._update_internal(code, price, float(tick.get('volume', 0)), minute_ts)
        except Exception as e:
            logger.error(f"MinuteKlineCache update error: {e}")

    def batch_update(self, df: pd.DataFrame, subscribers: set):
        """
        批量更新 K 线 (矢量化/高性能模式)
        """
        try:
            if df.empty: return
            
            # 1. 矢量化过滤：仅处理感兴趣的股票
            # 这样做可以避免对全市场 5000+ 股票进行循环
            mask = df['code'].isin(self.cache.keys() | subscribers)
            if not mask.any(): return
            
            active_df = df[mask]
            
            # 2. 预计算公共信息
            # 假设一个 Batch 内的时间戳基本一致
            ts = int(active_df['timestamp'].iloc[0] if 'timestamp' in active_df.columns else time.time())
            minute_ts = ts - (ts % 60)
            
            # 3. 高速迭代
            # itertuples 打包成 NamedTuple，访问速度远快于 to_dict('records')
            # 必须指定字段顺序或直接按位置访问
            for row in active_df.itertuples(index=False):
                # row 对应 columns: code, trade, volume, high, low, open, amount, (timestamp)
                # 注意：create_dummy_data 或 fetch_and_process 返回的列顺序可能不同
                # 建议通过 getattr 访问以保证稳健性，虽然稍慢一点点但比 dict 快
                code = row.code
                price = getattr(row, 'trade', 0)
                if price <= 0: continue
                volume = getattr(row, 'volume', getattr(row, 'vol', 0))
                
                self._update_internal(code, price, float(volume), minute_ts)
                
        except Exception as e:
            logger.error(f"MinuteKlineCache batch_update error: {e}")

    def _update_internal(self, code: str, price: float, current_cum_vol: float, minute_ts: int):
        """
        内部核心更新逻辑（最小化开销）
        """
        if code not in self.cache:
            self.cache[code] = deque(maxlen=self.max_len)
        klines = self.cache[code]
        
        if not klines:
            klines.append(KLineItem(
                time=minute_ts, open=price, high=price, low=price, close=price,
                volume=0.0, cum_vol_start=current_cum_vol
            ))
        else:
            last_k = klines[-1]
            if last_k.time == minute_ts:
                last_k.high = max(last_k.high, price)
                last_k.low = min(last_k.low, price)
                last_k.close = price
                last_k.volume = current_cum_vol - last_k.cum_vol_start
            else:
                klines.append(KLineItem(
                    time=minute_ts, open=price, high=price, low=price, close=price,
                    volume=0.0, cum_vol_start=current_cum_vol
                ))

    def detect_v_shape(self, code: str, window: int = 30) -> bool:
        """
        检测 V 型反转 (30分钟窗口)
        逻辑:
        1. 窗口内最低点跌幅较深 (相对于窗口起始或当日开盘, 这里简化为相对于窗口内最高点跌幅 > 2%)
        2. 当前价格较最低点明显反弹 (反弹幅度 > 1.5%)
        3. 当前价格接近或超过窗口起始价
        """
        klines = self.get_klines(code, n=window)
        if len(klines) < 10:
            return False
            
        try:
            closes = [k['close'] for k in klines]
            lows = [k['low'] for k in klines]
            highs = [k['high'] for k in klines]
            
            curr_price = closes[-1]
            min_low = min(lows)
            max_high = max(highs)
            
            # 1. 并没有太大的跌幅，忽略
            # (最高点 - 最低点) / 最高点 < 2% -> 波动太小
            if max_high == 0: return False
            drop_range = (max_high - min_low) / max_high
            if drop_range < 0.02:
                return False
                
            # 2. 从最低点反弹力度
            # (当前 - 最低) / 最低
            if min_low == 0: return False
            rebound = (curr_price - min_low) / min_low
            
            # 3. 反弹确认
            if rebound > 0.015:
                # 进一步确认形态：最低点出现在窗口中间而非刚开始
                # 简单处理：只要反弹够猛且刚跌过
                return True
                
        except Exception as e:
            logger.error(f"V-shape check error: {e}")
            
        return False

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

    def clear(self):
        self.scores.clear()

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

try:
    import psutil
except ImportError:
    psutil = None

from scraper_55188 import Scraper55188
from JohnsonUtil import commonTips as cct

class DataPublisher:
    """
    数据分发器 (核心入口)
    """
    def __init__(self, high_performance: bool = False, scraper_interval: int = 600):
        self.paused = False
        self.high_performance = high_performance # HP: ~4.0h, Legacy: ~2.0h (Dynamic nodes)
        self.auto_switch_enabled = True
        self.mem_threshold_mb = 500.0 # 阈值调低至 500MB
        self.node_threshold = 1000000 # 默认 100万个节点触发降级
        
        # Interval Settings
        self.expected_interval = 60 # 默认 1分钟
        self.last_batch_clock = 0.0
        self.batch_intervals = deque(maxlen=20) # 最近 20 批次的间隔(秒)
        
        # 55188 Scraper Settings
        self.scraper_interval = scraper_interval
        self.current_scraper_wait = scraper_interval
        self.max_scraper_wait = 1800 # 最大 30 分钟
        
        # Sector Persistence Settings
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concept_pg_data.db")
        self.sector_cache = {} # {name: score}
        self.last_db_check = 0.0

        # Time-based goals (Hours)
        self.TARGET_HOURS_HP = 4.0
        self.TARGET_HOURS_LEGACY = 2.0

        # Mode-based settings: Calculate max_len based on default 60s first
        default_interval = 60
        cache_len = int((self.TARGET_HOURS_HP * 3600) / default_interval) if high_performance else int((self.TARGET_HOURS_LEGACY * 3600) / default_interval)
        self.kline_cache = MinuteKlineCache(max_len=cache_len)
        
        self.emotion_tracker = IntradayEmotionTracker()
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        
        # Performance Tracking
        self.start_time = time.time()
        self.update_count = 0
        self.total_rows_processed = 0
        self.last_batch_time = 0
        self.max_batch_time = 0.0
        self.batch_rates_dq = deque(maxlen=10) # Last 10 batch rates (rows/sec)
        
        # 55188 External Data Integration
        self.scraper_55188 = Scraper55188()
        self.ext_data_55188 = pd.DataFrame()
        self.last_ext_update_ts = 0.0

        # Start maintenance thread
        self.maintenance_thread = threading.Thread(target=self._maintenance_task, daemon=True)
        self.maintenance_thread.start()
        
        # Start external data scraper thread
        self.scraper_thread = threading.Thread(target=self._scraper_task, daemon=True)
        self.scraper_thread.start()

    def reset_state(self):
        """
        每日重置状态（收盘后或开盘前调用）
        清除所有积压的 K 线和情绪数据，释放内存
        """
        logger.info("🌀 RealtimeDataService performing Daily Reset...")
        try:
            self.kline_cache.clear()
            self.emotion_tracker.clear()
            self.subscribers.clear() # Optional: Clear subscribers if connection needs reset
            self.update_count = 0
            self.total_rows_processed = 0
            
            # Re-init performance tracking
            self.max_batch_time = 0.0
            self.batch_rates_dq.clear()
            self.start_time = time.time()
            
            if psutil:
                mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
                logger.info(f"✅ Reset Complete. Current Memory: {mem:.2f} MB")
            else:
                logger.info("✅ Reset Complete.")
                
        except Exception as e:
            logger.error(f"Reset failed: {e}")

    def set_paused(self, paused: bool):
        """设置服务暂停状态"""
        self.paused = paused
        logger.info(f"🚦 RealtimeDataService paused set to: {paused}")

    def is_paused(self) -> bool:
        """获取服务是否暂停"""
        return self.paused

    def set_expected_interval(self, seconds: int):
        """由外部 UI 同步当前抓取频率，用于辅助计算 K线所需数量"""
        if seconds > 0 and self.expected_interval != seconds:
            logger.info(f"⏱️ DataPublisher expected interval updated: {seconds}s")
            self.expected_interval = seconds
            # 立即触发一次缓存长度重算
            self.set_high_performance(self.high_performance)

    def set_high_performance(self, enabled: bool):
        """动态切换回溯时长：基于目标小时数和抓取频率平衡内存"""
        self.high_performance = enabled
        target_h = self.TARGET_HOURS_HP if enabled else self.TARGET_HOURS_LEGACY
        
        # 优先级：外部设定的频率 > 观测到的频率 > 60s
        interval = self.expected_interval
        if interval <= 0:
            status = self.get_status()
            interval = status.get('avg_interval_sec', 60)
        
        if interval <= 0: interval = 60
        
        # 4h @ 60s = 240, 4h @ 120s = 120
        cache_len = int((target_h * 3600) / interval)
        cache_len = max(60, cache_len) # 兜底最小 60
        
        self.kline_cache.set_mode(max_len=cache_len)
        logger.info(f"🚀 Mode: {'HP' if enabled else 'Legacy'} | Target: {target_h}h | Interval: {interval}s | Limit: {cache_len}K")

    def set_auto_switch(self, enabled: bool, threshold_mb: float = 500.0, node_limit: int = 1000000):
        """设置自动切换规则"""
        self.auto_switch_enabled = enabled
        self.mem_threshold_mb = threshold_mb
        self.node_threshold = node_limit
        logger.info(f"⚙️ Auto-Switch: enabled={enabled}, mem={threshold_mb}MB, nodes={node_limit}")

    def _maintenance_task(self):
        """
        后台维护任务：每 10 分钟检查一次内存和数据量
        """
        while True:
            time.sleep(600)  # 10 minutes
            try:
                status = self.get_status()
                mem_mb = status.get('memory_usage_mb', 0)
                total_nodes = status.get('total_nodes', 0)
                
                # 自动降级逻辑 (内存超限 或 节点数超限)
                reason = ""
                if self.auto_switch_enabled and self.high_performance:
                    if mem_mb > self.mem_threshold_mb:
                        reason = f"Memory High ({mem_mb:.1f}MB)"
                    elif total_nodes > self.node_threshold:
                        reason = f"Nodes High ({total_nodes})"
                    
                    if reason:
                        logger.warning(f"⚠️ {reason}. Triggering Auto-Downgrade to Legacy Mode...")
                        self.set_high_performance(False)
                
                # Perf Mode info for logging
                is_hp = status.get('high_performance_mode', True)
                perf_str = "高性能 (全天 240m)" if is_hp else "极致省内存 (最近 60m)"
                auto_str = "ON" if status.get('auto_switch') else "OFF"
                
                logger.info(f"🔧 [Maintenance] Mem: {status.get('memory_usage')} | "
                            f"Klines: {status.get('klines_cached')} | "
                            f"Updates: {status.get('update_count')}")
                
                # 每小时更新一次板块持续性缓存
                if time.time() - self.last_db_check > 3600:
                    self._update_sector_cache()
                    self.last_db_check = time.time()
                
            except Exception as e:
                logger.error(f"Maintenance task error: {e}")

    def _update_sector_cache(self):
        """更新板块持续性得分"""
        from datetime import datetime, timedelta
        if not os.path.exists(self.db_path):
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            # 获取最近 5 天的数据，计算出现频次
            five_days_ago = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
            query = f"""
                SELECT concept_name, COUNT(*) as freq 
                FROM concept_data 
                WHERE date >= '{five_days_ago}'
                GROUP BY concept_name 
                HAVING freq >= 2
                ORDER BY freq DESC
            """
            df_sec = pd.read_sql(query, conn)
            conn.close()
            
            if not df_sec.empty:
                # 将频次映射为得分 (2次: 0.5, 3次: 0.8, 4+: 1.0)
                self.sector_cache = {}
                for row in df_sec.itertuples():
                    score = min(row.freq * 0.25, 1.0)
                    self.sector_cache[row.concept_name] = score
                logger.info(f"📊 Sector persistence cache updated: {len(self.sector_cache)} sectors.")
        except Exception as e:
            logger.error(f"Error updating sector cache: {e}")

    def get_sector_score(self, sector_name: str) -> float:
        """获取板块持续性得分"""
        if not sector_name: return 0.0
        # 模糊匹配或精确匹配
        score = self.sector_cache.get(sector_name, 0.0)
        if score == 0:
            # 简单尝试包含匹配
            for name, s in self.sector_cache.items():
                if name in sector_name or sector_name in name:
                    return s
        return score

    def _scraper_task(self):
        """
        后台抓取任务：定期抓取 55188 数据
        仅在交易时段运行，遇到封禁迹象自动“翻倍延迟” (Exponential Backoff)
        """
        while True:
            try:
                is_trading = cct.get_work_time_duration()
                now = time.time()
                
                # 逻辑：程序启动时强制执行第一次抓取（last_ext_update_ts == 0）
                # 之后仅在交易时段（is_trading）按间隔（current_scraper_wait）抓取
                do_fetch = False
                if self.last_ext_update_ts == 0:
                    do_fetch = True
                elif is_trading:
                    delta = now - self.last_ext_update_ts
                    if delta >= self.current_scraper_wait:
                        do_fetch = True

                if do_fetch:
                    logger.info(f"🕸️ Fetching 55188 external data (init={self.last_ext_update_ts == 0}, wait={self.current_scraper_wait}s)...")
                    df_ext = self.scraper_55188.get_combined_data()
                    
                    if not df_ext.empty:
                        self.ext_data_55188 = df_ext
                        self.last_ext_update_ts = now
                        # 成功后恢复默认延迟
                        if self.current_scraper_wait != self.scraper_interval:
                            logger.info(f"✅ Fetch success. Resetting scraper interval to {self.scraper_interval}s.")
                        self.current_scraper_wait = self.scraper_interval
                    else:
                        # 失败或被封禁迹象 (返回空) -> Double the wait
                        self.current_scraper_wait = min(self.current_scraper_wait * 2, self.max_scraper_wait)
                        # 如果是初始化失败，也标记一下，防止死循环在这个 if 块（虽然 sleep 10s 会缓解）
                        if self.last_ext_update_ts == 0:
                            self.last_ext_update_ts = now - (self.current_scraper_wait / 2)
                        else:
                            self.last_ext_update_ts = now
                        logger.warning(f"⚠️ Fetch failed/Empty result. Doubling wait to {self.current_scraper_wait}s.")
                
            except Exception as e:
                # 异常也触发 Backoff
                self.current_scraper_wait = min(self.current_scraper_wait * 2, self.max_scraper_wait)
                self.last_ext_update_ts = time.time()
                logger.error(f"Scraper task error: {e}. Backoff delay: {self.current_scraper_wait}s.")
            
            time.sleep(10) # 维持心跳检查频率
        
    def update_batch(self, df: pd.DataFrame):
        """
        接收来自 fetch_and_process 的 DataFrame 快照
        """
        if self.paused:
            return
            
        try:
            if df.empty: return

            # Fix: Ensure 'code' exists as a column (often in index)
            if 'code' not in df.columns:
                df = df.copy()
                df['code'] = df.index

            t0 = time.time()
            if self.last_batch_clock > 0:
                self.batch_intervals.append(t0 - self.last_batch_clock)
            self.last_batch_clock = t0
            
            rows_count = len(df)
            self.update_count += 1
            self.total_rows_processed += rows_count
            
            # 1. 深度情绪计算 (Vectorized)
            if 'percent' in df.columns:
                # 基础分：50 + 涨幅 * 3 (10% -> 80分, -10% -> 20分)
                base_score = 50 + (df['percent'] * 3)
                
                # 量能加权 (假设 ratio 为量比, 如果没有则默认为 1)
                vol_ratio = df['ratio'] if 'ratio' in df.columns else pd.Series(1.0, index=df.index)
                
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
            # 2. 更新 KLine (仅更新订阅或活跃股) - Vectorized & Batch Optimized
            if 'trade' in df.columns:
                active_stocks = set(self.subscribers.keys()) | set(self.kline_cache.cache.keys())
                self.kline_cache.batch_update(df, active_stocks)
            
            # Record Speed
            t1 = time.time()
            duration = t1 - t0
            if duration > 0:
                self.batch_rates_dq.append(rows_count / duration)
            self.last_batch_time = t1
            
        except Exception as e:
            logger.error(f"DataPublisher update_batch error: {e}")

    def subscribe(self, code: str, callback: Callable):
        self.subscribers[code].append(callback)

    def get_minute_klines(self, code: str, n: int = 60):
        return self.kline_cache.get_klines(code, n)

    def get_emotion_score(self, code: str):
        return self.emotion_tracker.get_score(code)

    def get_v_shape_signal(self, code: str, window: int = 30) -> bool:
        """获取个股是否有 V 型反转信号"""
        return self.kline_cache.detect_v_shape(code, window)

    def get_55188_data(self, code: Optional[str] = None) -> Union[dict, dict[str, Any]]:
        """获取指定的 55188 外部数据 (人气、主力排名、题材、板块得分等)"""
        if self.ext_data_55188.empty:
            return {}
        
        # 如果不传 code，返回全量数据快照汇总
        if code is None:
            return {
                'df': self.ext_data_55188.copy(),
                'last_update': cct.get_unixtime_to_time(self.last_ext_update_ts)
            }
            
        # 统一按字符串索引处理
        code_str = str(code).zfill(6)
        # 如果 code 不在索引但在列中，重新设为索引
        if 'code' in self.ext_data_55188.columns and self.ext_data_55188.index.name != 'code':
            self.ext_data_55188 = self.ext_data_55188.set_index('code')
            
        if code_str in self.ext_data_55188.index:
            data = self.ext_data_55188.loc[code_str].to_dict()
            # 注入板块持续性得分
            theme_name = data.get('theme_name', '')
            data['sector_score'] = self.get_sector_score(theme_name)
            return data
        return {}

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
        
    def get_status(self) -> dict[str, Any]:
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
            if self.batch_rates_dq:
                avg_speed = sum(self.batch_rates_dq) / len(self.batch_rates_dq)
            
            try:
                cpu_usage = process.cpu_percent(interval=None)
            except:
                cpu_usage = 0.0
                
            uptime = time.time() - self.start_time
            
            total_nodes = sum(len(d) for d in self.kline_cache.cache.values())
            avg_nodes = total_nodes / len(self.kline_cache.cache) if self.kline_cache.cache else 0
            
            # Estimate History Coverage
            # 优先级：直接使用预期的抓取频率，如果没有抓取过数据，则使用 expected_interval
            # 只有在预期频率和观测频率都缺失时才默认 60s
            avg_interval = self.expected_interval
            if self.batch_intervals:
                avg_interval = sum(self.batch_intervals) / len(self.batch_intervals)
            
            if avg_interval <= 0: avg_interval = 60
            
            history_sec = avg_nodes * avg_interval
            
            return {
                "klines_cached": len(self.kline_cache.cache),
                "total_nodes": total_nodes,
                "avg_nodes_per_stock": avg_nodes,
                "avg_interval_sec": int(avg_interval),
                "expected_interval": self.expected_interval,
                "history_coverage_minutes": int(history_sec / 60),
                "subscribers": sum(len(v) for v in self.subscribers.values()),
                "emotions_tracked": len(self.emotion_tracker.scores),
                "paused": self.paused,
                "high_performance_mode": self.high_performance,
                "target_hours": self.TARGET_HOURS_HP if self.high_performance else self.TARGET_HOURS_LEGACY,
                "auto_switch": self.auto_switch_enabled,
                "mem_threshold": self.mem_threshold_mb,
                "node_threshold": self.node_threshold,
                "node_capacity_pct": (total_nodes / self.node_threshold * 100) if self.node_threshold else 0,
                "cpu_usage": cpu_usage,
                "max_batch_time_ms": int(self.max_batch_time * 1000),
                "last_batch_time_ms": int(self.last_batch_time * 1000),
                "cache_history_limit": self.kline_cache.max_len,
                "last_update": self.kline_cache.last_update_ts.get("global", 0),
                "server_time": time.time(),
                "uptime_seconds": int(uptime),
                "memory_usage": mem_info,
                "memory_usage_mb": float(mem_info.split()[0]) if mem_info != "N/A" else 0,
                "total_rows_processed": self.total_rows_processed,
                "update_count": self.update_count,
                "processing_speed_row_per_sec": int(avg_speed),
                "pid": os.getpid()
            }
        except Exception as e:
            logger.error(f"get_status error: {e}")
            return {"error": str(e)}

if __name__ == "__main__":
    # 🧪 Standalone Test Functionality
    import sys
    print("🚀 Starting Standalone RealtimeDataService Test...")
    
    # --- Configuration ---
    USE_HIGH_PERFORMANCE = True # Toggle this to False for 60m History Mode
    
    # 1. Initialize Service
    dp = DataPublisher(high_performance=USE_HIGH_PERFORMANCE)
    stock_count = 5000
    
    # 2. Create Dummy Data
    def create_dummy_data(n=5):
        codes = [f"600{i:03d}" for i in range(n)]
        data = {
            "code": codes,
            "name": [f"Stock_{c}" for c in codes],
            "trade": [10.0 + i for i in range(n)],
            "percent": [1.5 + i*0.1 for i in range(n)],
            "high": [10.5 + i for i in range(n)],
            "low": [9.8 + i for i in range(n)],
            "vol": [1000 + i*100 for i in range(n)],
            "amount": [10000 + i*1000 for i in range(n)],
            "time": time.strftime("%H:%M:%S")
        }
        return pd.DataFrame(data)

    # 3. Test normal operation
    dummy_df = create_dummy_data(n=stock_count) # Using 10 rows for better visibility
    print(f"\n[Test 1] Normal Update (Rows: {len(dummy_df)} shape:{dummy_df.shape})...")
    print("Dummy Data Head:")
    print(dummy_df.head())
    
    dp.update_batch(dummy_df)
    status = dp.get_status()
    print(f"✅ Updates: {status.get('update_count')}, Memory: {status.get('memory_usage')}")

    # 4. Test Pause
    print("\n[Test 2] Pausing Service...")
    dp.set_paused(True)
    dp.update_batch(dummy_df) # This should be ignored
    status_paused = dp.get_status()
    if status_paused.get('update_count') == status.get('update_count'):
        print("✅ Pause Successful: Update ignored.")
    else:
        print(f"❌ Pause Failed: Update count increased to {status_paused.get('update_count')}")

    # 5. Test Reset
    print("\n[Test 3] Resetting State...")
    dp.reset_state()
    status_reset = dp.get_status()
    if status_reset.get('update_count') == 0 and status_reset.get('klines_cached') == 0:
        print("✅ Reset Successful: Counters and Cache cleared.")
    else:
        print(f"❌ Reset Failed: {status_reset}")

    # 6. Resume and Update
    print("\n[Test 4] Resuming and Updating...")
    dp.set_paused(False)
    dp.update_batch(dummy_df)
    status_final = dp.get_status()
    print(f"✅ Final Updates: {status_final.get('update_count')}")
    
    # 7. Simulation: 4 Hours of Trading Data (30s iterations)
    # 4 hours = 240 minutes = 480 iterations (at 30s interval)
    print("\n[Test 5] Simulating 4-Hour Trading Session (480 batches of 1000 stocks)...")
    print("This will correctly fill the 240-minute cache per stock.")
    
    # Subscribe stocks (increased to 1000 to see real growth)
    for i in range(stock_count):
        code = f"600{i:03d}"
        dp.subscribe(code, lambda x: None)
        
    start_sim = time.time()
    total_batches = 480
    base_ts = int(time.time()) - (total_batches * 30) # Start 4 hours ago
    
    for i in range(total_batches):
        sim_df = create_dummy_data(n=stock_count)
        # Mock timestamp incrementing by 30s each batch
        current_sim_ts = base_ts + (i * 30)
        sim_df['timestamp'] = current_sim_ts
        
        # Timing the individual batch
        batch_start = time.time()
        dp.update_batch(sim_df)
        batch_end = time.time()
        batch_dur = batch_end - batch_start
        
        if (i + 1) % 100 == 0:
            current_status = dp.get_status()
            print(f"  > Batch {i+1}/{total_batches} processed. "
                  f"Last Batch: {batch_dur*1000:.2f}ms | "
                  f"Mem: {current_status.get('memory_usage')} | "
                  f"Klines: {current_status.get('klines_cached')}")
            
    end_sim = time.time()
    final_status = dp.get_status()
    klines_count = final_status.get('klines_cached', 0) or 0
    total_nodes = final_status.get('total_nodes', 0) or 0
    print(f"\n✅ Simulation Complete in {end_sim - start_sim:.2f} seconds.")
    
    current_mem = final_status.get('memory_usage_mb', 0) or 0
    mem_used_kb = (float(current_mem) - 55.0) * 1024 # KB above base
    per_node = (mem_used_kb * 1024 / total_nodes) if total_nodes > 0 else 0
    
    print(f"📊 Final Stats ({stock_count} Stocks * 240 Mins):")
    print(f"   - Total Updates: {final_status.get('update_count')}")
    print(f"   - Memory Usage: {final_status.get('memory_usage')}")
    print(f"   - KLines Cached (Stocks): {klines_count}")
    print(f"   - Total Nodes across all deques: {total_nodes}")
    print(f"   - Avg Nodes per Stock: {final_status.get('avg_nodes_per_stock', 0):.1f}")
    print(f"   - Est. Incremental Memory per Node: {per_node:.1f} bytes")
    
    print("\n✨ Test Sequence Completed.")
