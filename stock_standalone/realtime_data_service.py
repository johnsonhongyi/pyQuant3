import time
import threading
import pandas as pd
import sqlite3
from collections import deque, defaultdict
from typing import Any, Optional, cast
from collections.abc import Callable
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct
from JohnsonUtil.commonTips import timed_ctx
from cache_utils import DataFrameCacheSlot, df_fingerprint
import psutil
import os
logger = LoggerFactory.getLogger()

# CFG = cct.GlobalConfig()
# win10_ramdisk_triton = CFG.get_path("win10_ramdisk_triton")
# if re.fullmatch(r"[A-Z]:", win10_ramdisk_triton, re.I):
#     win10_ramdisk_triton = win10_ramdisk_triton + "\\"
# CACHE_FILE = os.path.join(win10_ramdisk_triton, "realtime_data_snapshot.pkl")
# FP_FILE    = os.path.join(win10_ramdisk_triton, "realtime_data_snapshot_fp.json")

# Lightweight K-line item using __slots__ to save memory
class KLineItem:
    __slots__ = ('time', 'open', 'high', 'low', 'close', 'volume', 'cum_vol_start')
    
    def __init__(self, time: int, open: float, high: float, low: float, close: float, volume: float, cum_vol_start: float):
        self.time: int = time
        self.open: float = open
        self.high: float = high
        self.low: float = low
        self.close: float = close
        self.volume: float = volume
        self.cum_vol_start: float = cum_vol_start
    
    def as_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "cum_vol_start": self.cum_vol_start
        }

class MinuteKlineCache:
    """
    分时K线缓存
    每股保留最近 N 根 1分钟K线
    """
    _max_len: int
    _shared_cache: dict[str, deque[KLineItem]]
    _last_update_ts: dict[str, int]
    _is_dirty: bool

    def __init__(self, max_len: int = 240):
        self._max_len = max_len
        # {code: deque([KLineItem, ...])}
        self._shared_cache: dict[str, deque[KLineItem]] = {}
        self._last_update_ts: dict[str, int] = {}
        self._is_dirty = False # 脏标记：是否有新数据产生
        self._is_restored = False # 记录是否执行过恢复加载

    def __len__(self) -> int:
        return len(self._shared_cache)

    def to_dataframe(self) -> pd.DataFrame:
        """
        转换为 DataFrame (用于外部分析或持久化)
        增加了最终去重检查以确保数据完整性
        """
        data: list[dict[str, Any]] = []
        for code, dq in self._shared_cache.items():
            # 强制标准化 code
            code_clean = str(code).strip().zfill(6)
            for item in dq:
                # 直接通过 __slots__ 提取数据，避免 as_dict() 方法调用开销
                item_data = {s: getattr(item, s) for s in item.__slots__}
                item_data['code'] = code_clean
                data.append(item_data)
        
        if not data:
            return pd.DataFrame()
        
        df = pd.DataFrame(data)
        if df.empty:
            return df
            
        # 最后的防线：确保返回的 DF 绝对没有重复的 (code, time)
        # 强制转换类型并补齐 6 位代码，保证 drop_duplicates 和后续查看的一致性
        df['time'] = df['time'].astype(int)
        df['code'] = df['code'].astype(str).str.strip().str.zfill(6)
        df = df.sort_values(['code', 'time']).drop_duplicates(subset=['code', 'time'], keep='last')
        return df

    def from_dataframe(self, df: Optional[pd.DataFrame]):
        """
        从 DataFrame 恢复缓存数据（性能优化版，可直接替换）
        """
        if df is None or df.empty:
            return

        try:
            # 仅记录原始行数用于日志，避免双 copy
            raw_len = len(df)

            # 只 copy 一次
            df = df.copy()

            cols = df.columns

            # code 规范化（只做一次）
            if 'code' in cols:
                df['code'] = (
                    df['code']
                    .astype(str)
                    .str.strip()
                    .str.zfill(6)
                )

            # time 规范化
            if 'time' in cols:
                # int32 足够，速度和内存都更优
                df['time'] = df['time'].astype('int32')

                # 排序 + 去重
                df = (
                    df
                    .sort_values(['code', 'time'], kind='mergesort')
                    .drop_duplicates(subset=['code', 'time'], keep='last')
                )

            # 清空现有缓存
            self.clear()

            # 局部变量加速
            shared_cache = self._shared_cache
            max_len = self._max_len

            # 提前绑定属性访问，减少 getattr 开销
            from operator import attrgetter
            get_time   = attrgetter('time')
            get_open   = attrgetter('open')
            get_high   = attrgetter('high')
            get_low    = attrgetter('low')
            get_close  = attrgetter('close')
            get_volume = attrgetter('volume')
            get_cum    = attrgetter('cum_vol_start')

            # 按 code 分组重建 deque（不再二次排序）
            for code, group in df.groupby('code', sort=False):
                dq = deque(maxlen=max_len)

                # itertuples 是目前 pandas → Python 最快路径
                for r in group.itertuples(index=False):
                    try:
                        dq.append(
                            KLineItem(
                                time=get_time(r),
                                open=get_open(r),
                                high=get_high(r),
                                low=get_low(r),
                                close=get_close(r),
                                volume=get_volume(r),
                                cum_vol_start=get_cum(r),
                            )
                        )
                    except Exception:
                        # 与原逻辑一致，跳过坏行
                        continue

                shared_cache[str(code)] = dq

            self._is_dirty = True
            self._is_restored = True

            logger.info(
                f"♻️ MinuteKlineCache restored: {len(shared_cache)} stocks. "
                f"[Rows: {raw_len} -> Cleaned: {len(df)}]"
            )

        except Exception as e:
            logger.error(f"MinuteKlineCache restore error: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    def from_dataframe_slow(self, df: Optional[pd.DataFrame]):
        """
        从 DataFrame 恢复缓存数据
        """
        if df is None or df.empty:
            return
            
        try:
            # 确保 code 是标准化字符串格式
            df_raw = df.copy()
            df = df.copy()
            if 'code' in df.columns:
                df['code'] = df['code'].astype(str).str.strip().str.zfill(6)
            
            # 确保时间有序并清理可能的重复数据
            if 'time' in df.columns:
                df['time'] = df['time'].astype(int) 
                df['code'] = df['code'].astype(str).str.strip().str.zfill(6)
                df = df.sort_values(['code', 'time']).drop_duplicates(subset=['code', 'time'], keep='last')
            
            # 清空当前
            self.clear()
            
            # 按 code 分组重建 deque
            for code, group in df.groupby('code'):
                code_str = str(code)
                new_dq: deque[KLineItem] = deque(maxlen=self._max_len)
                # itertuples 性能较好
                for row in group.itertuples(index=False):
                    try:
                        # 确保所有数值都是标准类型
                        item = KLineItem(
                            time=int(getattr(row, 'time', 0)),
                            open=float(getattr(row, 'open', 0.0)),
                            high=float(getattr(row, 'high', 0.0)),
                            low=float(getattr(row, 'low', 0.0)),
                            close=float(getattr(row, 'close', 0.0)),
                            volume=float(getattr(row, 'volume', 0.0)),
                            cum_vol_start=float(getattr(row, 'cum_vol_start', 0.0))
                        )
                        new_dq.append(item)
                    except (AttributeError, ValueError, TypeError):
                        continue
                self._shared_cache[code_str] = new_dq
            
            self._is_dirty = True 
            self._is_restored = True
            logger.info(f"♻️ MinuteKlineCache restored: {len(self._shared_cache)} stocks. [Rows: {len(df_raw)} -> Cleaned: {len(df)}]")
        except Exception as e:
            logger.error(f"MinuteKlineCache restore error: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    @property
    def max_len(self) -> int:
        return self._max_len

    @property
    def cache(self) -> dict[str, deque[KLineItem]]:
        return self._shared_cache

    @property
    def last_update_ts(self) -> dict[str, int]:
        return self._last_update_ts

    def set_mode(self, max_len: int):
        """动态切换回溯时长：不清除数据，仅裁剪旧节点以回收内存"""
        if self._max_len != max_len:
            logger.info(f"✂️ MinuteKlineCache Trimming: {self._max_len} -> {max_len} nodes")
            self._max_len = max_len
            # 对所有现有数据进行重建以同步 maxlen 属性
            for code in list(self._shared_cache.keys()):
                dq = self._shared_cache[code]
                # 无论当前长度如何，都必须重建 deque 以修改只读的 maxlen 属性
                self._shared_cache[code] = deque(list(dq)[-max_len:], maxlen=max_len)

    def clear(self):
        """完全清空缓存"""
        self._shared_cache.clear()
        self._last_update_ts.clear()
        self._is_dirty = False

    def get_klines(self, code: str, n: int = 60) -> list[dict[str, Any]]:
        if code not in self._shared_cache:
            return []
        nodes = list(self._shared_cache[code])[-n:]
        # Support dict-based access for existing strategy code
        return [node.as_dict() for node in nodes]

    def update_batch(self, df: Optional[pd.DataFrame], subscribers: dict[str, list[Callable[..., Any]]]):
        """
        批量更新 K 线缓存并触发订阅
        """
        if df is None or df.empty:
            return
            
        updated_codes: set[str] = set()
        # 预计算时间戳 (通常一个 batch 时间一致)
        # 如果 df 中有 time 或 timestamp 列，则使用它，否则使用当前时间
        ts = time.time()
        if 'time' in df.columns:
            ts = float(df['time'].iloc[0]) # type: ignore
        elif 'timestamp' in df.columns:
            ts = float(df['timestamp'].iloc[0]) # type: ignore
            
        minute_ts = int(ts - (ts % 60))
        
        for row in df.itertuples(index=False):
            code_raw = getattr(row, 'code', '')
            if not code_raw: continue
            code = str(code_raw).strip().zfill(6)
            
            price = float(cast(float, getattr(row, 'trade', getattr(row, 'now', getattr(row, 'price', getattr(row, 'close', 0.0))))))
            if price <= 0: continue
            
            # 优先提取 'nvol' (用户确认: nvol=nowvol=实时交易量, volume=量比)
            # vol = float(cast(float, getattr(row, 'vol', getattr(row, 'volume', 0.0))))
            vol = float(cast(float, getattr(row, 'nvol', getattr(row, 'vol', getattr(row, 'volume', 0.0)))))
            self._update_internal(code, price, vol, minute_ts)
            updated_codes.add(code)
            self._last_update_ts[code] = minute_ts
            
        # 触发订阅回调
        if subscribers:
            for code in updated_codes.intersection(subscribers):
                klines = self.get_klines(code, n=1)
                if klines:
                    for callback in subscribers[code]:
                        try:
                            callback(code, klines[0])
                        except Exception as e:
                            logger.error(f"Callback error for {code}: {e}")

    def update(self, code: str, tick: dict):
        """
        单条更新接口 (主要用于兼容外部单条推送)
        """
        try:
            code_clean = str(code).strip().zfill(6)
            price = float(tick.get('trade', tick.get('now', 0.0)))
            if price <= 0: return

            ts = float(tick.get('timestamp') or tick.get('time') or time.time())
            minute_ts = int(ts - (ts % 60))
            # 优先提取 'nvol'
            # vol = float(tick.get('vol', tick.get('volume', 0.0)))
            vol = float(tick.get('nvol', tick.get('vol', tick.get('volume', 0.0))))
            self._update_internal(code_clean, price, vol, minute_ts)
            self._last_update_ts[code_clean] = minute_ts
        except Exception as e:
            logger.error(f"MinuteKlineCache.update error for {code}: {e}")

    def _update_internal(self, code: str, price: float, current_cum_vol: float, minute_ts: int):
        """
        内部核心更新逻辑（最小化开销）
        """
        if code not in self._shared_cache:
            self._shared_cache[code] = deque(maxlen=self._max_len)
        klines = self._shared_cache[code]
        
        if not klines:
            klines.append(KLineItem(
                time=minute_ts, open=price, high=price, low=price, close=price,
                volume=0.0, cum_vol_start=current_cum_vol
            ))


        else:
            last_k = klines[-1]
            if last_k.time == minute_ts:
                # 同一分钟：更新当前 K 线
                last_k.high = max(last_k.high, price)
                last_k.low = min(last_k.low, price)
                last_k.close = price
                
                # Check for volume reset or negative delta
                if current_cum_vol < last_k.cum_vol_start:
                     print(f"[WARNING] Volume Reset Detected - Code: {code}, Time: {minute_ts}, Current: {current_cum_vol}, Start: {last_k.cum_vol_start}")
                     last_k.cum_vol_start = current_cum_vol
                     # If reset happens, we can't calculate meaningful volume for this tick relative to previous start
                     # Reset volume to 0 for this instant or keep previous? 
                     # Safest is to reset start and assume minimal volume change for this specific update, 
                     # effectively restarting the counter for this minute.
                     last_k.volume = 0.0 
                else:
                    last_k.volume = current_cum_vol - last_k.cum_vol_start

                # if code == '000001':
                #      print(f"[DEBUG] Update KLine - Code: {code}, Time: {minute_ts}, Price: {price}, CumVol: {current_cum_vol}, StartVol: {last_k.cum_vol_start}, Vol: {last_k.volume}")
                
                self._is_dirty = True
            elif minute_ts > last_k.time:
                # 新的一分钟：结算并开始新 K 线
                
                # Hybrid Logic:
                # 1. Normal Trading: Gap volume belongs to the PREVIOUS bar (e.g., 14:56:00 tick reflects 14:55 activity).
                # 2. Closing Auction (15:00): The volume event happens AT 15:00, so it belongs to the NEW bar (15:00).
                
                prev_end_cum_vol = last_k.cum_vol_start + last_k.volume
                
                # Check for reset first
                if current_cum_vol < prev_end_cum_vol:
                     print(f"[WARNING] Volume Reset Detected on New Bar - Code: {code}, Time: {minute_ts}, Current: {current_cum_vol}, PrevEnd: {prev_end_cum_vol}")
                     # Reset: Start fresh
                     klines.append(KLineItem(
                        time=minute_ts, open=price, high=price, low=price, close=price,
                        volume=0.0, cum_vol_start=current_cum_vol
                    ))
                else:
                    # Determine attribution based on time
                    is_closing_call = (minute_ts % 10000 == 1500)
                    
                    if is_closing_call:
                        # 15:00 Closing Auction: Attribute gap volume to THIS bar (15:00)
                        # New bar starts from where previous left off
                        klines.append(KLineItem(
                            time=minute_ts, open=price, high=price, low=price, close=price,
                            volume=current_cum_vol - prev_end_cum_vol, 
                            cum_vol_start=prev_end_cum_vol
                        ))
                    else:
                        # Normal Trading: Attribute gap volume to PREVIOUS bar
                        last_k.volume = current_cum_vol - last_k.cum_vol_start
                        
                        # New bar starts fresh from current level
                        klines.append(KLineItem(
                            time=minute_ts, open=price, high=price, low=price, close=price,
                            volume=0.0, cum_vol_start=current_cum_vol
                        ))
                
                self._is_dirty = True
            else:
                # 忽略过时数据或乱序推送
                pass

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
            rebound: float = (curr_price - min_low) / min_low
            
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

class DailyEmotionBaseline:
    """
    开盘基准值：基于历史指标构建当日情绪锚点
    """
    def __init__(self):
        self._baselines: dict[str, float] = {}  # {code: baseline_score}
        self._baseline_details: dict[str, str] = {} # {code: status_description}
        self._last_calc_date: Optional[str] = None
    
    def calculate_baseline(self, df: pd.DataFrame) -> None:
        """开盘时调用，基于日线数据计算基准"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_calc_date == today:
            return  # 今日已计算
        
        try:
            count = 0
            # 临时增加 robust 检查
            if df.empty: return

            # 转换为 dict 迭代更快，而且为了逻辑清晰
            # 这里的 df 应该是 full candidate list 或者包含 historical data columns 的 df
            for idx, row in df.iterrows():
                # 兼容：如果 code 在列中则取列，否则取 index
                if 'code' in row:
                    code_val = row['code']
                else:
                    code_val = idx
                
                code_str = str(code_val).strip().zfill(6)
                score = 50.0  # 中性起点
                
                # 1. 连阳加分 (win >= 3 满分)
                win = float(row.get('win', 0))
                score += min(win * 5, 15)  # 最多+15
                
                # 2. 5日线上天数 (red >= 5 满分)
                red = float(row.get('red', 0))
                score += min(red * 3, 10)  # 最多+10
                
                # 3. 趋势强度 (TrendS)
                trend_s = float(row.get('TrendS', 50))
                if trend_s > 80: score += 10
                elif trend_s > 60: score += 5
                
                # 4. 斜率稳定 (slope)
                slope = float(row.get('slope', 0))
                if slope > 5: score += 10
                elif slope > 2: score += 5
                
                # 5. 累计涨幅 (sum_perc)
                sum_perc = float(row.get('sum_perc', 0))
                if sum_perc > 15: score += 10
                elif sum_perc > 8: score += 5
                elif sum_perc < -5: score -= 10
                
                # 6. 量能动力 (power_idx)
                power = float(row.get('power_idx', 0))
                if power > 15: score += 10
                elif power > 8: score += 5
                
                status_detail = ""
                # 7. [New] 突破上轨或强势洗盘回踩
                upper = float(row.get('upper', 0))
                boll = int(row.get('boll', 0))
                red = int(row.get('red', 0))
                gren = int(row.get('gren', 0))
                win = int(row.get('win', 0))
                price = float(row.get('trade', row.get('close', 0)))
                ma5 = float(row.get('ma5', 0))

                if upper > 0 and price >= upper:
                    score += 15
                    status_detail = f"上轨:{boll}红:{red}绿{gren}"
                elif ma5 > 0 and price > 0:
                    # 强势洗盘: 连阳后缩量回踩 MA5
                    dist_ma5 = (price - ma5) / ma5
                    vol_ratio = float(row.get('vol_ratio', row.get('ratio', 1.0)))
                    if -0.015 <= dist_ma5 <= 0.02 and vol_ratio < 1.0 and win >= 2:
                        score += 20
                        status_detail = f"缩量:{win}红:{red}绿{gren}"
                else:
                    status_detail = f"震荡:{win}红:{red}绿{gren}"
                # 最终限制
                self._baselines[code_str] = max(10.0, min(100.0, score))
                self._baseline_details[code_str] = status_detail
                count += 1
            
            self._last_calc_date = today
            logger.info(f"✅ Daily Emotion Baseline Calculated for {count} stocks.")
        except Exception as e:
            logger.error(f"Calculate Baseline Error: {e}")

    def get_baseline(self, code: str) -> float:
        return self._baselines.get(str(code), 50.0)
        
    def get_all_baselines(self) -> dict[str, float]:
        return self._baselines

    def get_all_baseline_details(self) -> dict[str, str]:
        return self._baseline_details

class IntradayEmotionTracker:
    """
    盘中情绪追踪器
    计算个股及市场情绪分
    """
    scores: dict[str, float]
    history: deque
    
    def __init__(self):
        self.scores = {} # {code: score}
        # 保存最近 4小时的历史 (每分钟一次大概 240个点，这里存的是 update_batch 的快照)
        # item: (timestamp, scores_dict)
        self.history = deque(maxlen=300) 

    def clear(self):
        self.scores.clear()

    def update_batch(self, df: pd.DataFrame, baseline_tracker: Optional[DailyEmotionBaseline] = None):
        """
        批量更新情绪分（稳定化版本）
        df: 包含 'percent', 'amount', 'volume' 等列
        """
        try:
            if df.empty: return
            
            # 1. Check for existing emotion score in DF (from upstream)
            if 'scan_score_emotion' in df.columns:
                self.scores = df.set_index('code')['scan_score_emotion'].to_dict()
                return

            if 'percent' not in df.columns:
                return

            # 2. Vectorized 深度情绪计算 with Smoothing
            EMA_ALPHA = 0.3  # 平滑系数
            MAX_DELTA = 15   # 单次最大变动幅度
            
            # 获取基准值
            if baseline_tracker:
                # Map baselines to the current dataframe
                baselines = df['code'].map(baseline_tracker.get_all_baselines()).fillna(50.0)
            else:
                baselines = pd.Series(50.0, index=df.index)
            
            percent = df['percent']
            vol_ratio = df['ratio'] if 'ratio' in df.columns else pd.Series(1.0, index=df.index)
            
            # 增量公式
            delta = percent * 2.0
            
            # 动量修正
            momentum = pd.Series(0.0, index=df.index)
            mask_up = (vol_ratio > 1.5) & (percent > 0)
            mask_down = (vol_ratio > 1.5) & (percent < 0)
            momentum[mask_up] = 5.0
            momentum[mask_down] = -5.0
            
            delta = delta + momentum
            delta = delta.clip(-MAX_DELTA, MAX_DELTA)
            
            target_scores = baselines + delta
            
            # EMA 平滑
            # get previous scores aligned with current df
            # fillna with baselines (if no previous score, start from baseline)
            prev_scores = df['code'].map(self.scores).fillna(baselines)
            
            final_scores = prev_scores * (1 - EMA_ALPHA) + target_scores * EMA_ALPHA
            
            # 特殊状态修正 (Override)
            # 恐慌盘：跌幅 > 5% 且放量 -> 额外扣分
            mask_panic = (percent < -5) & (vol_ratio > 1.5)
            # 抢筹：涨幅 > 5% 且放量 -> 额外加分
            mask_mania = (percent > 5) & (vol_ratio > 1.5)
            
            final_scores[mask_panic] -= 5
            final_scores[mask_mania] += 5
            
            # 限制在 0-100
            final_scores = final_scores.clip(0, 100)
            
            self.scores = dict(zip(df['code'], final_scores))

            # 3. 将结果写回 DataFrame (用于下游策略 & 日志)
            # 注意: df 是引用传递，修改会影响外部
            df['rt_emotion'] = final_scores
            df['emotion_baseline'] = baselines
            
            # --- [New] Expose Baseline Status/Reason ---
            details = {}
            if baseline_tracker:
                details = baseline_tracker.get_all_baseline_details()
            
            # Use 'code' column for mapping
            if 'code' in df.columns:
                 # Ensure code is string for mapping
                df['emotion_status'] = df['code'].astype(str).map(details).fillna('')
            else:
                # Fallback if code is index
                df['emotion_status'] = df.index.astype(str).map(details).fillna('')
            
            # Record history snapshot
            now = time.time()
            self.history.append((now, self.scores.copy()))
                
        except Exception as e:
            logger.error(f"IntradayEmotionTracker update error: {e}")

    def get_score(self, code: str) -> float:
        return self.scores.get(code, 50.0) # 默认 50 中性

    def get_score_diffs(self, minutes: int = 10) -> dict[str, float]:
        """
        获取 N 分钟前的情绪分变化
        Returns: {code: diff}
        """
        if not self.history or minutes <= 0:
            return {}
            
        now = time.time()
        target_ts = now - (minutes * 60)
        
        # Find closest snapshot
        # history is ordered by time asc
        closest_scores = None
        
        # 简单遍历寻找最近的时间点
        for ts, snapshot in self.history:
            if ts >= target_ts:
                # 找到了第一个大于等于 target_ts 的点，即最接近 target_ts 的点 (从过去到现在)
                # 其实更精确的是找 abs(ts - target_ts) 最小
                # 但由于是单调递增，第一个 >= target_ts 的通常就是我们要找的 "N分钟前" 的那个时刻的未来一点点
                # 或者它前面的一个是 "N分钟前" 的过去一点点
                closest_scores = snapshot
                break
        
        # 如果所有历史都比 target_ts 新 (比如刚启动)，取最老的一个
        if closest_scores is None and self.history:
             closest_scores = self.history[0][1]
             
        if not closest_scores:
            return {}
            
        diffs = {}
        for code, current_score in self.scores.items():
            old_score = closest_scores.get(code, 50.0) # 假设之前是中性 50
            diffs[code] = current_score - old_score
            
        return diffs

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
    paused: bool
    high_performance: bool
    auto_switch_enabled: bool
    mem_threshold_mb: float
    node_threshold: int
    _cache_path: str
    _last_save_ts: float
    _save_interval: int
    _last_save_fp: str
    expected_interval: int
    last_batch_clock: float
    scraper_interval: int
    current_scraper_wait: int
    max_scraper_wait: int
    db_path: str
    sector_cache: dict[str, float]
    last_db_check: float
    kline_cache: MinuteKlineCache
    emotion_tracker: IntradayEmotionTracker
    subscribers: dict[str, list[Callable[..., object]]]
    update_count: int
    total_rows_processed: int
    last_batch_time: float
    max_batch_time: float
    _last_batch_fp: str
    def __init__(self, high_performance: bool = True, scraper_interval: int = 600):
        # global FP_FILE,CACHE_FILE
        self.paused = False
        self.high_performance = high_performance # HP: ~4.0h, Legacy: ~2.0h (Dynamic nodes)
        self.auto_switch_enabled = True
        self.mem_threshold_mb = 1200.0 # 阈值调低至 1200MB
        self.node_threshold = 1000000 # 默认 100万个节点触发降级
        # =========================
        # Persistent Cache Settings
        # =========================
        cache_path = cct.get_ramdisk_path("minute_kline_cache.pkl")
        self._cache_path = str(cache_path) if cache_path else "" 
        self._last_save_ts = 0.0  # 修改：初始化为 0 以触发启动后的第一次保存
        self._save_interval = 300 # 每 5 分钟备份一次到磁盘
        
        self.cache_slot: DataFrameCacheSlot = DataFrameCacheSlot(
                cache_file=self._cache_path,
                fp_file=None,
                logger=logger,
            )
        self._last_save_fp = "" # 上次保存数据的指纹
        self._last_batch_fp = "" # 上次批次数据的指纹
        self._last_save_status = "N/A" # 上次保存状态
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
        
        self.kline_cache = MinuteKlineCache(max_len=cache_len)
        
        self.emotion_baseline = DailyEmotionBaseline() # Initialize baseline tracker
        self.emotion_tracker = IntradayEmotionTracker()
        self.subscribers = defaultdict(lambda: cast(list[Callable[..., object]], []))
        
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

        # =========================
        # Crash Recovery: Load Last Snapshot
        # =========================
        try:
            cached_df = self.cache_slot.load_df()
            if not cached_df.empty:
                with timed_ctx("from_dataframe", warn_ms=800):
                    self.kline_cache.from_dataframe(cached_df)
                logger.info(f"♻️ MinuteKlineCache recovered from disk: {len(cached_df)} nodes.")
            else:
                logger.info("ℹ️ No MinuteKlineCache found on disk or empty.")
        except Exception as e:
            logger.error(f"MinuteKlineCache recovery failed: {e}")

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

    def set_auto_switch(self, enabled: bool, threshold_mb: float = 800.0, node_limit: int = 1000000):
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
                
                logger.info(f"🔧 [Maintenance] Pid: {status.get('pid')} Mem: {status.get('memory_usage')} | "
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
            # if 'code' not in df.columns:
            #     df = df.copy()
            #     df['code'] = df.index

            if 'code' not in df.columns:
                if df.index.name == 'code':
                    df = df.reset_index()  # 把 index 转成列，同时 index 变成 RangeIndex
                else:
                    df = df.copy()
                    df['code'] = df.index

            # logger.info(f'df:{df[:3]} col:{df.columns} "code" in df.columns: {"code" in df.columns}')
            # --- 🚀 批次指纹校验：防止重复推送同一秒的数据 ---
            check_sample = df.head(5).copy()
            
            # # 计算开盘基准情绪 (每天确保计算一次)
            # # 移除 < 940 的限制，交由 emotion_baseline 内部控制频率
            # self.emotion_baseline.calculate_baseline(df)

            # # 更新情绪 (传入 baseline)
            # self.emotion_tracker.update_batch(df, self.emotion_baseline)

            # 兼容不同来源的列名
            fp_cols = ['code']
            for c in ['trade', 'now', 'price']:
                if c in check_sample.columns:
                    fp_cols.append(c)
                    break
            if 'volume' in check_sample.columns:
                fp_cols.append('volume')
                
            batch_fp = df_fingerprint(check_sample, cols=fp_cols)

            # # 判断 + 更新
            # if self._last_batch_fp == "":
            #     # 首次批次：建立指纹，不拦截
            #     self._last_batch_fp = batch_fp
            # elif batch_fp == self._last_batch_fp:
            #     # 重复批次：拦截
            #     return
            # else:
            #     # 新批次：更新指纹
            #     self._last_batch_fp = batch_fp

            if not cct.get_realtime_status() or self._last_batch_fp and batch_fp == self._last_batch_fp:
                if self.emotion_baseline._last_calc_date is None:
                    # 计算开盘基准情绪 (每天确保计算一次)
                    # 移除 < 940 的限制，交由 emotion_baseline 内部控制频率
                    self.emotion_baseline.calculate_baseline(df)
                    # 更新情绪 (传入 baseline)
                    self.emotion_tracker.update_batch(df, self.emotion_baseline)
                    logger.info(f'emotion_baseline._last_calc_date: {self.emotion_baseline._last_calc_date}')
                return
                
            if self.update_count == 0:
                logger.info(f"🚦 First batch received in DataPublisher. Columns: {list(df.columns)[:10]}")
                
            self._last_batch_fp = batch_fp

            t0 = time.time()
            if self.last_batch_clock > 0:
                self.batch_intervals.append(t0 - self.last_batch_clock)
            self.last_batch_clock = t0

            # 1. 计算当日基准分 & 实时情绪 (Vectorized)
            # 只有在新批次到来时才更新，避免指纹拦截后的重复计算
            self.emotion_baseline.calculate_baseline(df)
            self.emotion_tracker.update_batch(df, self.emotion_baseline)
            
            rows_count = len(df)
            self.update_count += 1
            self.total_rows_processed += rows_count
            
            # 1. 深度情绪计算 (Vectorized) - Already updated above with baseline
            # self.emotion_tracker.update_batch(df) # 删除重复调用，避免基准分重置

            # Update global last update timestamp
            # 2. 更新 KLine (仅更新订阅或活跃股) - Vectorized & Batch Optimized
            if 'trade' in df.columns or 'now' in df.columns or 'price' in df.columns:
                self.kline_cache.update_batch(df, self.subscribers)
            
            # Record Speed
            t1 = time.time()
            duration = t1 - t0
            if duration > 0:
                self.batch_rates_dq.append(rows_count / duration)
            self.last_batch_time = t1
            
            # =========================
            # Snapshot Cache (Crash Safe)
            # =========================
            now = time.time()
            close_time = int(self._save_interval / 60) + 1500
            if now - self._last_save_ts > self._save_interval:
                # self.save_cache(force=False)
                # if cct.get_realtime_status() or cct.get_:
                if self._last_save_ts == 0 or cct.get_trade_date_status() and 930 < cct.get_now_time_int() <= close_time:
                    save_cache_df = self.kline_cache.to_dataframe()
                    # logger.debug(f'save_cache_df: {save_cache_df.shape}')
                    self.cache_slot.save_df(save_cache_df,persist=True)
                    self._last_save_ts = time.time()
                
        except Exception as e:
            logger.error(f"DataPublisher update_batch error: {e}")


    def subscribe(self, code: str, callback: Callable[..., object]):
        self.subscribers[code].append(callback)

    def get_minute_klines(self, code: str, n: int = 60) -> list[dict[str, Any]]:
        return self.kline_cache.get_klines(code, n)

    def get_emotion_score(self, code: str):
        return self.emotion_tracker.get_score(code)

    def get_v_shape_signal(self, code: str, window: int = 30) -> bool:
        """获取个股是否有 V 型反转信号"""
        return self.kline_cache.detect_v_shape(code, window)

    def get_55188_data(self, code: Optional[str] = None) -> dict[str, Any]:
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
            theme_name = str(data.get('theme_name', ''))
            data['sector_score'] = self.get_sector_score(theme_name)
            return cast(dict[str, Any], data)
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
            if code not in self.kline_cache.cache:
                self.kline_cache.cache[code] = deque(maxlen=self.kline_cache.max_len)
            
            for _ in range(n_klines):
                # 必须存储 KLineItem 对象
                item = KLineItem(
                    time=int(dummy_data['time']),
                    open=float(dummy_data['open']),
                    high=float(dummy_data['high']),
                    low=float(dummy_data['low']),
                    close=float(dummy_data['close']),
                    volume=float(dummy_data['volume']),
                    cum_vol_start=0.0
                )
                self.kline_cache.cache[code].append(item)
        
        # 估算内存
        # 这是一个粗略估算
        # 实际对象开销较大
        print("Stress Test Populated. Check Task Manager for memory usage.")
        
    def get_status(self) -> dict[str, Any]:
        """
        获取服务运行状态监控指标
        """
        try:
            # Memory & CPU Usage
            mem_info = "N/A"
            cpu_usage = 0.0
            if psutil:
                try:
                    process = psutil.Process(os.getpid())
                    mem_bytes = process.memory_info().rss
                    mem_info = f"{mem_bytes / 1024 / 1024:.2f} MB"
                    cpu_usage = process.cpu_percent(interval=None)
                except Exception:
                    pass
            
            # Speed
            avg_speed = 0.0
            if self.batch_rates_dq:
                avg_speed = sum(self.batch_rates_dq) / len(self.batch_rates_dq)
                
            uptime = time.time() - self.start_time
            
            total_nodes = sum(len(d) for d in self.kline_cache.cache.values())
            avg_nodes = float(total_nodes / len(self.kline_cache.cache)) if self.kline_cache.cache else 0.0
            
            # Estimate History Coverage
            # 优先级：直接使用预期的抓取频率，如果没有抓取过数据，则使用 expected_interval
            # 只有在预期频率和观测频率都缺失时才默认 60s
            avg_interval = float(self.expected_interval)
            if self.batch_intervals:
                avg_interval = float(sum(self.batch_intervals) / len(self.batch_intervals))
            
            if avg_interval <= 0: avg_interval = 60.0
            
            history_sec = float(avg_nodes * avg_interval)
            
            num_subscribers = sum(len(v) for v in self.subscribers.values())
            
            return {
                "klines_cached": len(self.kline_cache.cache),
                "total_nodes": total_nodes,
                "avg_nodes_per_stock": avg_nodes,
                "avg_interval_sec": int(avg_interval),
                "expected_interval": self.expected_interval,
                "history_coverage_minutes": int(history_sec / 60),
                "subscribers": num_subscribers,
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
                "memory_usage_mb": float(mem_info.split()[0]) if mem_info != "N/A" else 0.0,
                "total_rows_processed": self.total_rows_processed,
                "update_count": self.update_count,
                "processing_speed_row_per_sec": int(avg_speed),
                "last_save_time": cct.get_unixtime_to_time(self._last_save_ts) if self._last_save_ts > 0 else "NEVER",
                "last_save_status": self._last_save_status,
                "cache_is_dirty": self.kline_cache._is_dirty,
                "cache_restored": self.kline_cache._is_restored,
                "pid": os.getpid()
            }
        except Exception as e:
            logger.error(f"get_status error: {e}")
            return {"error": str(e)}

if __name__ == "__main__":
    # 🧪 Standalone Test Functionality
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
