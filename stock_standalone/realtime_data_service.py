import time
from datetime import datetime
import threading
import gc
import pandas as pd
import sqlite3
from collections import deque, defaultdict
from typing import Any, Optional, cast
from collections.abc import Callable
import psutil
import os

# ── 环境配置 ─────────────────────────────────────────────────────────────────
try:
    from JohnsonUtil import LoggerFactory
    from JohnsonUtil import commonTips as cct
    from JohnsonUtil.commonTips import timed_ctx
    from cache_utils import DataFrameCacheSlot, df_fingerprint
except ImportError:
    from stock_standalone.JohnsonUtil import LoggerFactory
    from stock_standalone.JohnsonUtil import commonTips as cct
    from stock_standalone.JohnsonUtil.commonTips import timed_ctx
    from stock_standalone.cache_utils import DataFrameCacheSlot, df_fingerprint
logger = LoggerFactory.getLogger()
h5a = cct.LazyModule('JSONData.tdx_hdf5_api')

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
    _slack: int
    _shared_cache: dict[str, list[KLineItem]]
    _last_update_ts: dict[str, int]
    _is_dirty: bool
    _supplemented_codes: set[str]  # 记录已执行过补充抓取的股票，避免循环抓取
    simulation_mode: bool

    def __init__(self, max_len: int = 240, simulation_mode: bool = False, verbose: bool = False):
        self._max_len = max_len
        self._slack = 20  # [NEW] 裁切缓冲区，避免频繁触发切片操作
        self.simulation_mode = simulation_mode
        self.verbose = verbose
        self._shared_cache: dict[str, list[KLineItem]] = {} # code -> list[KLineItem]
        self._last_update_ts: dict[str, int] = {}
        self._is_dirty = False # 脏标记：是否有新数据产生
        self._is_restored = False # 记录是否执行过恢复加载
        self._supplemented_codes = set()

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
            
        # 强制转换类型并补齐 6 位代码
        df['time'] = df['time'].astype(int)
        df['code'] = df['code'].astype(str).str.strip().str.zfill(6)
        
        # 仅保留排序和去重防线：确保返回的 DF 绝对没有重复的 (code, time)
        df = df.sort_values(['code', 'time']).drop_duplicates(subset=['code', 'time'], keep='last')
        return df

    def count_gaps(self, threshold: int = 200) -> dict[str, int]:
        """
        统计数据完整性：返回低于 threshold 个 tick 的 ticker 数量及详情
        """
        low_tick_codes = {}
        for code, dq in self._shared_cache.items():
            count = len(dq)
            if 0 < count < threshold:
                low_tick_codes[code] = count
        
        if low_tick_codes:
            logger.info(f"📊 [DataHub] Found {len(low_tick_codes)} stocks with insufficient history (< {threshold} ticks).")
        return low_tick_codes

    def from_dataframe(self, df: Optional[pd.DataFrame], merge: bool = False):
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

                # --- [FIX] 加载时修复: 剔除非交易时段数据 ---
                seconds_from_midnight = (df['time'] + 28800) % 86400
                mins_from_midnight = seconds_from_midnight // 60
                hhmm = (mins_from_midnight // 60) * 100 + (mins_from_midnight % 60)

                # --- [FIX] 加载时修复: 剔除竞价阶段模拟数据 (9:15-9:24) ---
                # 历史日（非今天）一律剔除 9:15-9:24
                # 今天的数据，如果当前已经过了 9:25，也一律剔除
                now_dt = datetime.now()
                now_hhmm = now_dt.hour * 100 + now_dt.minute
                
                # 使用 timestamp 快速判别今天 (UTC+8)
                df_date_val = ((df['time'] + 28800) // 86400).astype(int)
                today_date_val = int((time.time() + 28800) // 86400)
                
                is_today = (df_date_val == today_date_val)
                # 准入规则 (情绪数据优化版)：
                # 1. 9:25 及之后的成交数据全保留 (跨天分析、分时趋势的核心)
                # 2. 9:15-9:24 (以及 9:26-9:29) 的模拟数据：
                #    - 如果是【今天】且【目前还在开盘前】(now_hhmm < 930)，暂时保留用于主力意图预判。
                #    - 一旦【跨入 9:30 以后】或加载【历史日期】，直接过滤 9:15-9:24 及其他非 9:25 的开盘前模拟数据。
                mask_real = (hhmm >= 925)
                # 只有 9:25 是真实的集合竞价结果，其他 (9:15-9:24, 9:26-9:29) 均为情绪数据
                is_auction_result = (hhmm == 925)
                mask_bidding_live = is_today & (hhmm >= 915) & (hhmm < 930) & (now_hhmm < 930)
                
                # 最终准入：要么是 9:25 之后(含9:25)的真实数据，要么是正在实盘竞价中的情绪数据
                mask_am = mask_real | mask_bidding_live
                mask_pm = (hhmm >= 1300) & (hhmm <= 1505)
                
                df = df[(mask_am & (hhmm <= 1131)) | mask_pm]
                
                # 特殊二次过滤：如果是 9:30 以后加载今天的数据，强制剔除非 9:25 的 pre-9:30 数据
                if is_today.any() and now_hhmm >= 930:
                    df = df[~((df['code'].isin(df[is_today]['code'])) & (hhmm >= 915) & (hhmm < 930) & (~is_auction_result))]

                # 排序 + 去重
                df = (
                    df
                    .sort_values(['code', 'time'], kind='mergesort')
                    .drop_duplicates(subset=['code', 'time'], keep='last')
                )

            # [REFINED] Only clear if not merging
            if not merge:
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

            # 按 code 分组重建（不再二次排序）
            for code, group in df.groupby('code', sort=False):
                kl_list = []

                # itertuples 是目前 pandas -> Python 最快路径
                for r in group.itertuples(index=False):
                    try:
                        kl_list.append(
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
                
                # 初始加载裁切
                if len(kl_list) > max_len:
                    kl_list = kl_list[-max_len:]
                shared_cache[str(code)] = kl_list

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
            
            # 按 code 分组重建
            for code, group in df.groupby('code'):
                code_str = str(code)
                new_list: list[KLineItem] = []
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
                        new_list.append(item)
                    except (AttributeError, ValueError, TypeError):
                        continue
                if len(new_list) > self._max_len:
                    new_list = new_list[-self._max_len:]
                self._shared_cache[code_str] = new_list
            
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
    def cache(self) -> dict[str, list[KLineItem]]:
        return self._shared_cache

    @property
    def last_update_ts(self) -> dict[str, int]:
        return self._last_update_ts

    def set_mode(self, max_len: int):
        """动态切换回溯时长：不清除数据，仅裁剪旧节点以回收内存"""
        if self._max_len != max_len:
            logger.info(f"✂️ MinuteKlineCache Trimming: {self._max_len} -> {max_len} nodes")
            self._max_len = max_len
            # 对所有现有数据进行批量裁切
            for code in self._shared_cache:
                klines = self._shared_cache[code]
                if len(klines) > max_len:
                    self._shared_cache[code] = klines[-max_len:]

    def clear(self):
        """完全清空缓存"""
        self._shared_cache.clear()
        self._last_update_ts.clear()
        self._is_dirty = False

    def get_klines(self, code: str, n: int = 60) -> list[dict[str, Any]]:
        if code not in self._shared_cache:
            return []
        nodes = self._shared_cache[code][-n:]
        # Support dict-based access for existing strategy code
        return [node.as_dict() for node in nodes]

    def update_batch(self, df: Optional[pd.DataFrame], subscribers: dict[str, list[Callable[..., Any]]]):
        """
        批量更新 K 线缓存并触发订阅 (每行独立时间戳处理)
        """
        if df is None or df.empty:
            return
            
        # [REMOVED] Automatic supplemental fetch removed per user feedback.
        # Regular refreshes now handle all codes via dual-snapshot (Full + Filtered).
        # _supplemental_fetch remains available for manual on-demand usage (e.g. SBC Replay).

        updated_codes: set[str] = set()
        
        # [OPTIMIZATION] 预先裁剪 DataFrame 列，减少 itertuples 遍历时的对象开销
        core_cols = ['code']
        # 识别价格列
        price_col_found = None
        for pc in ['trade', 'now', 'close', 'price', 'hq_last', 'llastp']:
            if pc in df.columns:
                price_col_found = pc
                core_cols.append(pc)
                break
        # 识别成交量列
        vol_cols_found = [c for c in ['nvol', 'vol', 'volume', 'hq_nvol'] if c in df.columns]
        core_cols.extend(vol_cols_found)
        # 识别时间列
        time_col_found = None
        for tc in ['timestamp', 'time', 'ticktime']:
            if tc in df.columns:
                time_col_found = tc
                core_cols.append(tc)
                break
        
        # 仅遍历核心列，极大提升 5000+ 个股的更新效率
        df_iter = df[core_cols]
        if self.simulation_mode and self.verbose and not df_iter.empty:
             print(f"DEBUG: update_batch simulation processing {len(df_iter)} rows. Cols: {core_cols}. First row: {df_iter.iloc[0].to_dict() if len(df_iter)>0 else 'N/A'}")
             
        for idx, row in enumerate(df_iter.itertuples(index=False)):
            try:
                code_raw = getattr(row, 'code', '')
                if not code_raw: continue
                code = str(code_raw).strip().zfill(6)
                
                # [OPTIMIZATION] 使用预先识别的列名提取价格，避免多次 getattr 尝试
                price = 0.0
                if price_col_found:
                    price = float(getattr(row, price_col_found, 0.0))
                
                # [REFINED] 成交量提取逻辑优化
                # 为了支持 Bidding 阶段，优先使用 volume/nvol 等累积值
                current_cum_vol = 0.0
                for vc in vol_cols_found:
                    val = getattr(row, vc, 0.0)
                    if val is not None:
                        current_cum_vol = float(val)
                        break
                vol = float(cast(float, getattr(row, 'nvol', getattr(row, 'vol', getattr(row, 'volume', 0.0)))))
                
                # [REFINED] 允许 0 成交量数据进入缓存以支持竞价和不活跃个股
                if price <= 0 and vol <= 0:
                    continue
                
                # 即使本间隔无成交，只要价格有效，也记录该分钟 Bar，确保全市场 240 对齐
                
                # 时间戳提取
                ts = 0.0
                val = None
                if time_col_found:
                    val = getattr(row, time_col_found)
                    try:
                        if isinstance(val, (int, float)) and val > 1e8:
                            ts = float(val)
                        elif isinstance(val, str) and val.replace('.', '', 1).isdigit() and float(val) > 1e8:
                            ts = float(val)
                        else:
                            # 鲁棒转换：处理 Unix timestamp, datetime, 或 HH:MM:SS 字符串
                            dt = pd.to_datetime(val)
                            if dt.tzinfo is None:
                                # [FIX] 显式锁定北京时间，防止 .timestamp() 默认将其视为 UTC 导致的 8 小时超前
                                try:
                                    dt = dt.tz_localize('Asia/Shanghai')
                                except Exception:
                                    # 如果已经有时区或报错，保持现状
                                    pass
                            ts = dt.timestamp()
                    except Exception as e:
                        logger.error(f"❌ [{code}] Time parse error: col={time_col_found}, val={val}, err={e}")
                        continue
                else:
                    ts = time.time()
                
                # --- [FIX] 统一时间准入检查 ---
                seconds_from_midnight = (ts + 28800) % 86400
                mins_from_midnight = int(seconds_from_midnight // 60)
                hhmm = (mins_from_midnight // 60) * 100 + (mins_from_midnight % 60)
                
                # --- [FIX] 未来时间防御墙与严格审计 (Simulation 模式下跳过) ---
                if not self.simulation_mode:
                    now_ts = time.time()
                    # 如果解析出的时间领先系统超过 10 分钟 (600s)
                    if ts > now_ts + 600:
                        original_ts = ts
                        # 尝试纠偏：如果领先超过 30 分钟，极有可能是昨日残余盘后数据（15:00）被解析为今日下午
                        diff = ts - now_ts
                        if diff > 1800:
                            ts -= 86400  # 回退 24 小时
                        
                        # 再次校验，如果修正后依然超前，判定为严重脏数据
                        if ts > now_ts + 600:
                            logger.error(f"❌ [{code}] INVALID FUTURE TICK: {datetime.fromtimestamp(original_ts)} (Now: {datetime.fromtimestamp(now_ts)}, diff={diff:.1f}s, col={time_col_found})")
                            continue
                    
                    # --- [FIX] 日期一致性校验 (确保是当日数据，防止 H5 脏数据注入) ---
                    dt_obj = datetime.fromtimestamp(ts)
                    now_dt = datetime.fromtimestamp(now_ts)
                    if dt_obj.date() != now_dt.date():
                        # 特殊处理：如果是 15:00 左右的数据，通常是昨日残留，设为 WARNING 以减噪
                        if 1455 <= hhmm <= 1505:
                            logger.warning(f"⚠️ [{code}] Residual data skipped: tick_date={dt_obj.date()}, val={val}")
                        else:
                            logger.error(f"❌ [{code}] DATE MISMATCH: tick_date={dt_obj.date()}, today={now_dt.date()} (val={val}, col={time_col_found})")
                        continue
                    
                    # --- [FIX] 防御盘后冗余数据进入缓存 ---
                    # --- [FIX] 统一时间准入标准 (9:15-11:31, 13:00-15:05) ---
                    if not ((915 <= hhmm <= 1131) or (1300 <= hhmm <= 1505)):
                        continue 
                # 兼容处理：如果是 YYYYMMDDHHMMSS 格式 (通常 > 2e9)，这里不做复杂转换，假定系统统传 Unix
                minute_ts = int(ts - (ts % 60))
                
                # 核心更新
                if self.verbose and self.simulation_mode and idx < 5: # 增加采样
                     print(f"DEBUG: [{code}] price={price}, vol={current_cum_vol}, time={datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')}, hhmm={hhmm}, ts={ts}")
                
                self._update_internal(code, price, current_cum_vol, minute_ts, hhmm=hhmm)
                updated_codes.add(code)
                self._last_update_ts[code] = minute_ts
                
                
            except Exception:
                continue

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

        # [REMOVED] Premature DataHub publish (moved to Signal calculation points)

    def update(self, code: str, tick: dict):
        """
        单条更新接口 (主要用于兼容外部单条推送)
        """
        try:
            code_clean = str(code).strip().zfill(6)
            price = float(tick.get('trade', tick.get('now', 0.0)))
            if price <= 0: return

            val = tick.get('timestamp') or tick.get('time')
            if val is not None:
                if isinstance(val, (int, float)) and val > 1e8:
                    ts = float(val)
                elif isinstance(val, str) and val.replace('.', '', 1).isdigit() and float(val) > 1e8:
                    ts = float(val)
                else:
                    dt = pd.to_datetime(val)
                    if dt.tzinfo is None:
                        dt = dt.tz_localize('Asia/Shanghai')
                    ts = dt.timestamp()
            else:
                ts = time.time()
                
            # --- [FIX] 统一时间准入标准 ---
            seconds_from_midnight = (ts + 28800) % 86400
            mins_from_midnight = int(seconds_from_midnight // 60)
            hhmm = (mins_from_midnight // 60) * 100 + (mins_from_midnight % 60)
            if not ((915 <= hhmm <= 1131) or (1300 <= hhmm <= 1505)):
                return
                
            minute_ts = int(ts - (ts % 60))
            # 优先提取 'nvol'
            # vol = float(tick.get('vol', tick.get('volume', 0.0)))
            vol = float(tick.get('nvol', tick.get('vol', tick.get('volume', 0.0))))
            
            # [REFINED] 异常数据丢弃 (放宽成交量限制以支持竞价)
            if price <= 0:
                return

            self._update_internal(code_clean, price, vol, minute_ts, hhmm)
            self._last_update_ts[code_clean] = minute_ts
        except Exception as e:
            logger.error(f"MinuteKlineCache.update error for {code}: {e}")

    def _update_internal(self, code: str, price: float, current_cum_vol: float, minute_ts: int, hhmm: Optional[int] = None):
        """
        原子化更新 K 线 (纯净增量逻辑)
        hhmm: 当前时段，用于支持竞价时段 (9:30以前) 的成交量回退容错
        """
        if code not in self._shared_cache:
            self._shared_cache[code] = []
        klines = self._shared_cache[code]
        
        # [NEW] 情绪数据清理 (9:30 自动剔除模拟竞价数据)
        # 用户反馈：9:30 以后 9:15-9:24 就只是情绪数据，会干扰均线判断逻辑，应予以清理。
        if hhmm is not None and hhmm >= 930 and klines:
             has_bidding = False
             curr_dt = datetime.fromtimestamp(minute_ts)
             for k in klines:
                 k_dt = datetime.fromtimestamp(k.time)
                 if k_dt.date() == curr_dt.date():
                     k_hhmm = k_dt.hour * 100 + k_dt.minute
                     # 9:25 是真实的集合竞价，保留；清理 9:15-9:24 及可能的 9:26-9:29 模拟数据
                     if 915 <= k_hhmm < 930 and k_hhmm != 925:
                         has_bidding = True
                         break
             
             if has_bidding:
                 self._shared_cache[code] = [k for k in klines if not (
                     datetime.fromtimestamp(k.time).date() == curr_dt.date() and 
                     915 <= (datetime.fromtimestamp(k.time).hour * 100 + datetime.fromtimestamp(k.time).minute) < 930 and
                     (datetime.fromtimestamp(k.time).hour * 100 + datetime.fromtimestamp(k.time).minute) != 925
                 )]
                 klines = self._shared_cache[code]
                 logger.info(f"🧹 [{code}] Bidding sentiment bars (Pre-9:30) pruned at {hhmm} to avoid MA interference.")
                 self._is_dirty = True

        # 1. 初始插入 or 跨天插入
        is_new_day = False
        if klines:
            last_dt = datetime.fromtimestamp(klines[-1].time)
            curr_dt = datetime.fromtimestamp(minute_ts)
            if last_dt.date() != curr_dt.date():
                is_new_day = True

        if not klines or is_new_day:
            # [REFINED] 强化集合竞价成交量捕捉 (9:25 是第一根时，将全量成交记入 volume)
            vol_for_first = current_cum_vol if (925 <= hhmm <= 931) else 0.0
            klines.append(KLineItem(
                time=minute_ts, open=price, high=price, low=price, close=price,
                volume=vol_for_first, cum_vol_start=0.0 if (925 <= hhmm <= 931) else current_cum_vol
            ))
            self._is_dirty = True
            return

        # 重要：清理后重新获取 last_k 引用，确保后续更新针对的是清理后的 K 线链条
        last_k = klines[-1]

        # [Daily Reset] 用户要求支持多日，不在此处重置

        # 获取 hhmm (如果未传入) 作为容错
        if hhmm is None:
            seconds_from_midnight = (minute_ts + 28800) % 86400
            mins_from_midnight = int(seconds_from_midnight // 60)
            hhmm = (mins_from_midnight // 60) * 100 + (mins_from_midnight % 60)
        
        # [SELF-HEALING] 处理潜在的未来时间 Bar 污染
        if last_k.time > time.time() + 300 and minute_ts < last_k.time:
            logger.warning(f"🚨 [{code}] Future bar detected, pruning to recover.")
            klines.pop()
            if not klines:
                klines.append(KLineItem(
                    time=minute_ts, open=price, high=price, low=price, close=price,
                    volume=0.0, cum_vol_start=current_cum_vol
                ))
                self._is_dirty = True
                return
            last_k = klines[-1]
        
        # 2. 同一分钟更新
        if last_k.time == minute_ts:
            last_k.high = max(last_k.high, price)
            last_k.low = min(last_k.low, price)
            last_k.close = price
            
            if current_cum_vol < last_k.cum_vol_start:
                is_bidding = (hhmm < 930)
                rollback_amount = last_k.cum_vol_start - current_cum_vol
                limit_amt = last_k.cum_vol_start * 0.1 if is_bidding else 1000
                
                if rollback_amount > limit_amt and rollback_amount > 1000:
                    last_k.cum_vol_start = current_cum_vol
                    last_k.volume = 0.0
            else:
                last_k.volume = current_cum_vol - last_k.cum_vol_start
            self._is_dirty = True
            
        # 3. 开启新分钟
        elif minute_ts > last_k.time:
            last_hhmm = datetime.fromtimestamp(last_k.time).hour * 100 + datetime.fromtimestamp(last_k.time).minute
            
            # 补齐上一个 Bar 的最终成交量
            if current_cum_vol >= last_k.cum_vol_start:
                # [FIX] 9:25 -> 9:30 跨越特殊处理
                # 9:25 的 Volume 在集合竞价结束时已固定。后续 9:30 的 Tick 不应再推高 9:25 的成交量。
                if last_hhmm == 925 and hhmm >= 930:
                    pass 
                else:
                    last_k.volume = current_cum_vol - last_k.cum_vol_start
            
            # [FIX] 确定新分钟的起始累积成交量
            # 正常情况下是当前 Tick 的累积量，但跨越 gap 时应以上一个 Bar 的终点为起点
            new_cum_vol_start = current_cum_vol
            if last_hhmm == 925 and hhmm >= 930:
                new_cum_vol_start = last_k.cum_vol_start + last_k.volume
            
            # 插入新分钟起始数据
            # 如果当前 Tick 已有超出 new_cum_vol_start 的增量，直接计入 volume
            new_vol = 0.0
            if current_cum_vol > new_cum_vol_start:
                new_vol = current_cum_vol - new_cum_vol_start

            klines.append(KLineItem(
                time=minute_ts, open=price, high=price, low=price, close=price,
                volume=new_vol,
                cum_vol_start=new_cum_vol_start
            ))
            
            # [REFINED] 平滑裁切逻辑：超过 max_len + slack 时一次性批量删除
            # 避免 list 被频繁执行 O(N) 的 pop(0)
            if len(klines) > self._max_len + self._slack:
                # 裁切掉最早的 _slack 根 K 线
                # 例如 max_len=240, slack=20, 长度到 261 时，裁切掉前 20 根变成 241 根
                klines[:self._slack] = []
                
            self._is_dirty = True
        else:
            # 忽略过时数据
            pass

    # def fast_fill_from_tick(self, tick_df: pd.DataFrame,use_tick_vol = False) -> pd.DataFrame:
    #     """
    #     将 tick 数据补充进 stock_df，并过滤无效 tick
    #     """

    #     tick = tick_df.reset_index()

    #     # 时间转换
    #     tick['ticktime'] = pd.to_datetime(tick['ticktime']).dt.tz_localize('Asia/Shanghai')
    #     tick['time'] = tick['ticktime'].astype('int64') // 10**9

    #     # 成交量列
    #     if use_tick_vol:
    #         vol_col = 'tick_vol' if 'tick_vol' in tick.columns else 'volume'
    #     else:
    #         vol_col = 'volume'
    #     # ---- 过滤无效 tick ----
    #     tick = tick[
    #         (tick[vol_col] > 0) &
    #         (tick['close'] > 0)
    #     ]

    #     # 统一字段
    #     tick_part = tick[['code','time','open','high','low','close']].copy()
    #     tick_part['volume'] = tick[vol_col]

    #     # cols = ['code','time','open','high','low','close','volume']
    #     # stock_part = stock_df[cols]

    #     # # 合并
    #     # df = pd.concat([stock_part, tick_part], ignore_index=True)

    #     # 排序
    #     # df = df.sort_values(['code','time'])

    #     # 去重（tick优先）
    #     # df = df.drop_duplicates(['code','time'], keep='last')
    #     return tick_part

    def _supplemental_fetch(self, code: str):
        """
        [NEW] 补充抓取：对于 tick 数不足的个股，从 Sina 获取完整当日轨迹
        """
        try:
            from JSONData import sina_data
            sina = sina_data.Sina()
            # 💡 [USER HINT] 使用 enrich_data=True 获取当日完整轨迹
            tick_df = sina.get_real_time_tick(code, enrich_data=True)
            
            if tick_df is not None and not tick_df.empty:
                logger.info(f"💡 Supplemental fetch for {code}: retrieved {len(tick_df)} ticks from Sina trajectory.")
                # 将轨迹数据转换为 K 线并合并 (⚡ Essential: merge=True)
                # Note: from_dataframe with merge=True adds/updates stocks without clearing others
                # tick_df = self.fast_fill_from_tick(tick_df)
                self.from_dataframe(tick_df, merge=True)
                self._supplemented_codes.add(code)
        except Exception as e:
            logger.error(f"❌ Supplemental fetch failed for {code}: {e}")

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
    def __init__(self, verbose: bool = False):
        self._baselines: dict[str, float] = {}  # {code: baseline_score}
        self._baseline_details: dict[str, str] = {} # {code: status_description}
        self._structural_anchors: dict[str, dict[str, float]] = {} # {code: {yesterday_high, prev_high, ma60, ma20}}
        self._last_calc_date: Optional[str] = None
        self.verbose = verbose
    
    def get_last_calc_date(self) -> Optional[str]:
        return self._last_calc_date

    def calculate_baseline(self, df: pd.DataFrame) -> None:
        """开盘时调用，基于日线数据计算基准"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            count = 0
            # 临时增加 robust 检查
            if df.empty: return

            # 转换为 dict 迭代更快，而且为了逻辑清晰
            # 这里的 df 应该是 full candidate list 或者包含 historical data columns 的 df
            # logger.debug(f"[DEBUG-BASELINE] calculate_baseline: columns={list(df.columns)}, count={len(df)}")
            try:
                from strategy_config import COLUMN_MAPPING
            except ImportError:
                from stock_standalone.strategy_config import COLUMN_MAPPING
            c_mapping = COLUMN_MAPPING.get('DAILY', {})
            
            # 使用映射解析列名，保留 hardcoded 作为 fallback 兼容
            m_ma5   = c_mapping.get('ma5d', 'ma5d')
            m_ma10  = c_mapping.get('ma10d', 'ma10d') # [NEW] Added for consistency
            m_ma20  = c_mapping.get('ma20d', 'ma20d')
            m_ma60  = c_mapping.get('ma60d', 'ma60d')
            m_h1    = c_mapping.get('lasth1d', 'lasth1d')
            m_h2    = c_mapping.get('lasth2d', 'lasth2d')
            m_p1    = c_mapping.get('lastp1d', 'lastp1d')
            m_p2    = c_mapping.get('lastp2d', 'lastp2d')
            m_low   = c_mapping.get('last_low', 'lastl1d')

            for idx, row in df.iterrows():
                # 兼容：如果 code 在列中则取列，否则取 index
                if 'code' in row:
                    code_val = row['code']
                else:
                    code_val = idx
                
                code_str = str(code_val).strip().zfill(6)
                
                # [NEW] 获取通过矩阵预处理的结构和活跃度综合基础分
                score = float(row.get('structure_base_score', 50.0))
                
                # 转换所有必要的数值，优先从映射列取
                price      = float(row.get('trade', row.get('close', 0)))
                ma5        = float(row.get(m_ma5, row.get('ma5d', row.get('ma5', 0))))
                ma10       = float(row.get(m_ma10, row.get('ma10d', row.get('ma10', 0))))
                ma20       = float(row.get(m_ma20, row.get('ma20d', row.get('ma20', 0))))
                ma60       = float(row.get(m_ma60, row.get('ma60d', row.get('ma60', 0))))
                lasth1d    = float(row.get(m_h1, row.get('lasth1d', row.get('last_high', 0))))
                lasth2d    = float(row.get(m_h2, row.get('lasth2d', row.get('high2', 0))))
                lastp1d    = float(row.get(m_p1, row.get('lastp1d', row.get('last_close', 0))))
                lastp2d    = float(row.get(m_p2, row.get('lastp2d', row.get('close2', 0))))
                
                # [FIX] 明确使用 lastl1d 作为前一日低点，并提取多日序列
                lastl1d    = float(row.get('lastl1d', row.get(m_low, row.get('last_low', row.get('low', 0)))))
                lastl2d    = float(row.get('lastl2d', 0))
                lastl3d    = float(row.get('lastl3d', 0))
                
                # 提取成交量序列 (用于放量/加速判断)
                lastv1d    = float(row.get('lastv1d', 0))
                lastv2d    = float(row.get('lastv2d', 0))
                lastv3d    = float(row.get('lastv3d', 0))
                
                last_low   = lastl1d # 默认锚点
                dist_h_l   = float(row.get('dist_h_l', 4.0)) # 振幅，缺省给 4.0

                # [NEW] 提取大周期和竞价元数据 (源自 compute_perd_df)
                max5       = float(row.get('max5', 0))
                max10      = float(row.get('max10', 0))
                hmax       = float(row.get('hmax', 0))
                hmax60     = float(row.get('hmax60', row.get('hmax2', 0))) # 60日高点
                high4      = float(row.get('high4', 0))
                low4       = float(row.get('low4', 0))
                ral        = float(row.get('ral', 0))
                top0       = float(row.get('top0', 0))
                top15      = float(row.get('top15', 0))
                lastdu4    = float(row.get('lastdu4', 0))
                category   = str(row.get('category', ''))
                
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
                
                # [NEW] 7. 竞价与强度因子 (基于 compute_perd_df 逻辑)
                if top0 > 0: score += 10    # 极强竞价 (一字/涨停竞价)
                if top15 > 0: score += 10   # 强势开盘/异动
                if ral > 15: score += 10    # 相对强度极高
                elif ral > 8: score += 5
                
                # [NEW] 8. 区间振幅 (lastdu4 - 绝对值体现波动率)
                abs_lastdu4 = abs(lastdu4)
                if abs_lastdu4 > 15: score += 15 # 振幅巨大 (活跃/异动)
                elif abs_lastdu4 > 8: score += 10
                elif abs_lastdu4 > 4: score += 5

                # [NEW] 9. 成交量异动 & 活异动判断
                is_vol_spike = False
                if lastv1d > 0 and lastv2d > 0 and lastv3d > 0:
                    avg_v = (lastv2d + lastv3d) / 2
                    if lastv1d > avg_v * 1.5:
                        is_vol_spike = True
                        score += 10 # 明显放量
                
                status_detail = ""
                is_active_anomaly = False # 活异动 (窄幅突围)
                is_acceleration = False   # 加速 (活跃放量)

                # 逻辑：低活跃突然高走或竞价极强
                if abs_lastdu4 < 6 and (top15 > 0 or top0 > 0 or price > max5):
                    is_active_anomaly = True
                    score += 20
                    status_detail = "活异动"
                
                # 逻辑：高活跃且量能维持/增加
                elif abs_lastdu4 >= 6 and (is_vol_spike or lastv1d >= lastv2d):
                    is_acceleration = True
                    score += 10
                    status_detail = "加速"
                # 7. [New] 突破上轨或强势洗盘回踩
                upper = float(row.get('upper', 0))

                # 判断形态结构 (Structural Patterns)
                is_v_reversal = False
                if lastp1d > 0 and price > last_low:
                     # V反识别
                     if dist_h_l > 4.0 and price >= lastp1d:
                         is_v_reversal = True
                         score += 15

                # 领涨龙头特征
                is_ma60_rev = ma60 > 0 and lastp1d < ma60 and price > ma60
                is_ma20_rev = ma20 > 0 and lastp1d < ma20 and price > ma20

                # 判断前两日结构是否处于上升通道 (收盘和新高都在上升)
                is_rising_struct = (lastp1d > lastp2d > 0) and (lasth1d > lasth2d > 0)
                
                is_breakthrough = False
                # 强势结构：站稳 MA60 且突破近两日最高点
                curr_structural_high = float(max(lasth1d, lasth2d))
                if (ma60 > 0 and price > ma60) and curr_structural_high > 0 and price > curr_structural_high:
                    if is_rising_struct:
                        is_breakthrough = True
                        score += 20 # 动力分大幅提升 (符合上升结构)
                    else:
                        is_breakthrough = True
                        score += 10 # 普通突破

                # [NEW] 9. 大周期突破判定 (Proximity to max5/high4/hmax)
                # 源自 compute_perd_df 指标：判定是否正处于大级别压力位突破点
                if price > 0:
                    breakout_status = ""
                    # 强势启动识别 (刚刚突破关键压力位)
                    is_fresh_breakout = False
                    
                    # 1. 60日大回归突破 (最高优先级)
                    if hmax60 > 0 and price >= hmax60:
                        score += 30
                        breakout_status = "强势启动" if lastp1d < hmax60 else "大回归突破"
                        is_fresh_breakout = (lastp1d < hmax60)
                    # 2. 30日/近期高点突破
                    elif hmax > 0 and price >= hmax:
                        score += 25
                        breakout_status = "强势发力" if lastp1d < hmax else "30D突破"
                        is_fresh_breakout = (lastp1d < hmax)
                    # 3. 5日最高点 (max5)
                    elif max5 > 0 and price >= max5:
                        score += 15
                        breakout_status = "5D突破"
                        is_fresh_breakout = (lastp1d < max5)
                    # 4. 近期结构高点 (high4)
                    elif high4 > 0 and price >= high4:
                        score += 10
                        breakout_status = "近期突破"
                        is_fresh_breakout = (lastp1d < high4)
                    
                    # 如果是新鲜突破且伴随放量，赋予更高描述
                    if is_fresh_breakout and (is_vol_spike or top15 > 0):
                        breakout_status = "强启动"
                        score += 10 # 额外动力加分
                    
                    if breakout_status:
                        # 只有在没有更强的描述时才作为主要状态
                        if not status_detail or "震荡" in status_detail or status_detail in ["加速", "活异动"]:
                            status_detail = breakout_status if not status_detail else f"{status_detail}|{breakout_status}"
                
                # 记录锚点供盘中追踪
                code_str = str(code_val).strip().zfill(6)
                self._structural_anchors[code_str] = {
                    'yesterday_high': lasth1d,
                    'prev_high': lasth2d,
                    'ma60': ma60,
                    'ma20': ma20,
                    'last_low': last_low,
                    'last_close': lastp1d,
                    'last_close_p2': lastp2d,
                    'is_rising_struct': is_rising_struct,
                    'category': category,
                    'max5': max5,
                    'high4': high4,
                    'hmax': hmax,
                    'hmax60': hmax60,
                    'lastdu4': lastdu4,
                    'lastv1d': lastv1d,
                    'lastl1d': lastl1d,
                    'is_active_anomaly': is_active_anomaly,
                    'is_acceleration': is_acceleration
                }

                # 安全等级基础分 (0-5)
                safety = 3.0
                if is_ma60_rev: 
                    score += 15
                    safety += 1.0
                if is_ma20_rev:
                    score += 10
                    safety += 0.5
                if ma20 > ma60 > 0 and price > ma20: safety += 0.5 # 处于多头通道更安全
                
                # 振幅/回撤过大则扣安全分
                if dist_h_l > 8.0: safety -= 0.5

                if is_breakthrough:
                    status_detail = f"结构突破:{int(win)}阳"
                elif is_ma60_rev:
                    status_detail = f"MA60反转:{int(win)}阳"
                elif is_ma20_rev:
                    status_detail = f"MA20反转:{int(win)}阳"
                elif is_v_reversal:
                    status_detail = f"V反突破:{int(win)}阳"
                elif upper > 0 and price >= upper:
                    score += 15
                    status_detail = f"上轨突破:{int(win)}阳"
                elif ma5 > 0 and price > 0:
                    dist_ma5 = (price - ma5) / ma5
                    vol_ratio = float(row.get('vol_ratio', row.get('ratio', 1.0)))
                    if -0.015 <= dist_ma5 <= 0.02 and vol_ratio < 1.0 and win >= 2:
                        score += 20
                        status_detail = f"缩量回踩:{int(win)}阳"
                else:
                    status_detail = f"震荡:{int(win)}阳"
                
                # 附加安全等级显示
                status_detail += f" (安:{min(5.0, safety):.1f})"

                # 最终限制 (统一 round 2 确保显示美观)
                self._baselines[code_str] = round(max(10.0, min(100.0, score)), 2)
                self._baseline_details[code_str] = status_detail if status_detail else "震荡"
                count += 1
            
            self._last_calc_date = today
            if count > 10:
                if self.verbose:
                    logger.info(f"✅ Daily Emotion Baseline Calculated for {count} stocks.")
            else:
                if self.verbose:
                    logger.debug(f"✅ Daily Emotion Baseline Calculated for {count} stocks.")
        except Exception as e:
            logger.error(f"Calculate Baseline Error: {e}")

    def get_baseline(self, code: str) -> float:
        code_str = str(code).zfill(6)
        return self._baselines.get(code_str, 50.0)

    def get_baseline_detail(self, code: str) -> str:
        code_str = str(code).zfill(6)
        return self._baseline_details.get(code_str, "")
        
    def get_all_baselines(self) -> dict[str, float]:
        return self._baselines

    def get_all_baseline_details(self) -> dict[str, str]:
        return self._baseline_details

    def get_anchor(self, code: str) -> dict[str, float]:
        code_str = str(code).zfill(6)
        res = self._structural_anchors.get(code_str, {})
        if not res:
            # logger.debug(f"[DEBUG-BASELINE] No anchor for {code_str}. Current anchors: {list(self._structural_anchors.keys())[:5]}")
            pass
        return res

class IntradayEmotionTracker:
    """
    盘中情绪追踪器
    计算个股及市场情绪分
    """
    scores: dict[str, float]
    _sbc_alert_set: set[str]
    _last_sbc_status: dict[str, bool]
    _last_vol: dict[str, float]      # 记录上一笔成交总量，用于计算增量
    _cumulative_amt: dict[str, float] # 记录累积成交额，用于合成 VWAP
    _intraday_high: dict[str, float] # 记录日内最高价，用于识别突破
    _signal_start_price: dict[str, float] # [NEW] 记录信号触发时的价格，用于计算绩效反馈
    history: deque[tuple[float, dict[str, float]]]
    
    def __init__(self):
        self.scores = {} # {code: score}
        self._sbc_alert_set = set() # 记录今日已提醒过的强势结构代码
        self._last_sbc_status = {}  # {code: bool} 记录上一状态，实现触发式而非持续式信号
        self._last_vol = {}
        self._cumulative_amt = {}
        self._intraday_high = {}
        self._signal_start_price = {} # {code: start_price}
        self._last_date = {}        # {code: day_num} 用于处理跨天重置累积量
        self._code_to_name = {}     # [Phase 4] 系统内部名称映射兜底
        # 保存最近 4小时的历史 (每分钟一次大概 240个点，这里存的是 update_batch 的快照)
        # item: (timestamp, scores_dict)
        self.history = deque(maxlen=300)

    def register_names(self, name_map: dict[str, str]):
        """[Phase 4] 注册代码名称对应关系"""
        if isinstance(name_map, dict):
            self._code_to_name.update(name_map)

    def clear(self):
        self.scores.clear()
        self._sbc_alert_set.clear()
        self._last_vol.clear()
        self._cumulative_amt.clear()
        self._intraday_high.clear()
        self._signal_start_price.clear()
        self._last_date.clear()
        # self._code_to_name.clear() # 通常名称不随数据清除

    def update_batch(self, df: pd.DataFrame, baseline_tracker: Optional[DailyEmotionBaseline] = None):
        """
        批量更新情绪分（稳定化版本）
        df: 包含 'percent', 'amount', 'volume' 等列
        """
        try:
            if df.empty: return
            
            # --- [NEW] Start Config-Driven Column Projection ---
            try:
                from strategy_config import COLUMN_MAPPING, STRUCTURAL_THRESHOLD
            except ImportError:
                from stock_standalone.strategy_config import COLUMN_MAPPING, STRUCTURAL_THRESHOLD
                
            c_mapping = COLUMN_MAPPING.get('REALTIME', {})
            
            # 定义内部逻辑使用的标准列名
            col_trade = c_mapping.get('trade', 'trade')
            col_amount = c_mapping.get('amount', 'amount')
            col_vol = c_mapping.get('vol', 'vol')      # 原始成交量
            col_ratio = c_mapping.get('volume', 'volume') # 量比

            # 动态解析输入 DF 中的可用列
            active_trade_col = col_trade if col_trade in df.columns else ('now' if 'now' in df.columns else 'trade')
            active_amt_col = col_amount if col_amount in df.columns else 'amount'
            active_vol_col = col_vol if col_vol in df.columns else ('volume' if 'volume' in df.columns else 'vol')
            active_ratio_col = col_ratio if col_ratio in df.columns else 'ratio'

            vwap_support_val = STRUCTURAL_THRESHOLD.get('SBC_RISING', {}).get('vwap_support', 1.002)
            # --- End Config-Driven Column Projection ---
            
            # [NEW] Filter out invalid ticks (zero volume or trade price)
            if active_vol_col in df.columns:
                df = df[df[active_vol_col] > 0]
            if active_trade_col in df.columns:
                df = df[df[active_trade_col] > 0]
            
            if df.empty: return
            
            # [PRE-CALC] 为趋势加速判定预计算滚动指标
            if active_trade_col in df.columns:
                # 3 周期价格变动 (加速上涨判定)
                df['_p_fast'] = df[active_trade_col].diff(3)
            if active_vol_col in df.columns:
                # 5 周期平均成交量 (带量判定)
                df['_v_avg'] = df[active_vol_col].rolling(5, min_periods=1).mean()

            # 1. 优先检查现有的情绪分
            if 'scan_score_emotion' in df.columns:
                self.scores.update(df.set_index('code')['scan_score_emotion'].to_dict())
                # 注意：即使有了分数，也要继续执行后续的结构判定逻辑
            
            # 2. Vectorized 深度情绪计算 (仅在百分比存在时)
            # 初始化基准，确保在所有分支中 baselines 均定义
            if baseline_tracker:
                baselines = df['code'].map(baseline_tracker.get_all_baselines()).fillna(50.0)
            else:
                baselines = pd.Series(50.0, index=df.index)

            if 'percent' in df.columns:
                EMA_ALPHA = 0.3
                MAX_DELTA = 15
                
                percent = df['percent']
                vol_ratio = df[active_ratio_col] if active_ratio_col in df.columns else pd.Series(1.0, index=df.index)
                
                delta = (percent * 2.0).clip(-MAX_DELTA, MAX_DELTA)
                
                # [NEW] 情绪高位回落惩罚：如果现价比日内最高价跌去 > 2%
                retreat_penalty = pd.Series(0.0, index=df.index)
                if self._intraday_high:
                    highs = df['code'].map(self._intraday_high).fillna(0.0)
                    cur_prices = df[active_trade_col] if active_trade_col in df.columns else df.get('trade', 0.0)
                    # 只有在有最高价记录且当前价低于最高价 2% 以上时
                    mask_retreat = (highs > 0) & (cur_prices < highs * 0.98)
                    retreat_penalty[mask_retreat] = -15.0 # 强制情绪降温
                
                target_scores = baselines + delta + retreat_penalty
                
                prev_scores = df['code'].map(self.scores).fillna(baselines)
                
                # [NEW] 冷却加速：如果当前目标分低于之前分 (走弱)，提高 EMA_ALPHA 实现快降
                # 默认 0.3, 走弱时 0.6
                alpha_series = pd.Series(EMA_ALPHA, index=df.index)
                mask_cooling = target_scores < prev_scores
                alpha_series[mask_cooling] = 0.6
                
                final_scores = prev_scores * (1 - alpha_series) + target_scores * alpha_series
                
                # 强化放量状态分数
                mask_mania = (percent > 5) & (vol_ratio > 1.5)
                final_scores[mask_mania] += 5
                
                # [NEW] 高开低走 (Gap Trap) 情绪封板
                # 如果开盘涨幅很高 (>5%) 但目前已经跌去一半涨幅，情绪分封顶 70
                open_prices = df.get('open', pd.Series(0.0, index=df.index))
                # 从 baseline_tracker 获取昨日收盘价
                if baseline_tracker:
                    last_closes = df['code'].map(lambda c: baseline_tracker.get_anchor(c).get('last_close', 0.0))
                    open_gap_pct = (open_prices - last_closes) / last_closes * 100.0
                    
                    mask_gap_trap = (open_gap_pct > 5.0) & (percent < open_gap_pct * 0.5)
                    final_scores[mask_gap_trap] = final_scores[mask_gap_trap].clip(0, 70)
                
                final_scores = final_scores.clip(0, 100).round(2)
                self.scores.update(dict(zip(df['code'], final_scores)))
            else:
                # 如果没有百分比，至少保持之前的分数并确保 final_scores 存在
                final_scores = pd.Series(df['code'].map(self.scores).fillna(baselines).values, index=df.index).round(2)

            # 3. [New] 分时结构追踪与 VWAP 计算
            # 即使没有量/额，也要预埋 sbc_status 列避免 KeyError
            df['sbc_status'] = '' 
            
            # --- [UNIFIED] Consume Enriched Data from Underlying Service ---
            # 信号检测逻辑现在依赖于底层数据服务提供的 'avg_price' (VWAP)。
            # 如果底层未提供 (如非 Sina 数据源)，则使用现价作为兜底。
            if 'avg_price' not in df.columns:
                col_price = active_trade_col if active_trade_col in df.columns else ('close' if 'close' in df.columns else 'now')
                df['avg_price'] = df[col_price] if col_price in df.columns else 0
            
            # 强制执行基准判定逻辑 (SBC)
            if baseline_tracker:
                    sbc_signals = []
                    scores_dict = final_scores.to_dict()
                    
                    # 获取当前环境秒数用于兜底
                    now_ts = time.time()
                    for idx_val, row in df.iterrows():
                        code_str = str(row['code']).zfill(6)
                        # [Phase 4] 只有明确有 name 才显示，否则为空字符串
                        name_raw = row.get('name', '')
                        # 如果 name 字段内容和 code 一致，说明是 fallback 进来的，我们认为这不算“真正有显示名称”
                        if name_raw == code_str:
                            name_raw = ''
                        name_str = str(name_raw) if name_raw else ""
                        
                        # 只有在内部映射表里确实有不一样的名称时才显示
                        if not name_str and code_str in self._code_to_name:
                            candidate = self._code_to_name[code_str]
                            if candidate != code_str:
                                name_str = candidate
                        
                        name_display = f" {name_str}" if name_str else ""
                        # [Daily Reset Protection] 检测到新的一天，重置累积 VWAP 计算器
                        # 优先从 row 中读取 time/timestamp
                        r_ts = getattr(row, 'time', getattr(row, 'timestamp', now_ts))
                        if isinstance(r_ts, str):
                            try: r_ts = pd.to_datetime(r_ts).timestamp()
                            except: r_ts = now_ts
                        
                        r_day_num = int((r_ts + 28800) // 86400)
                        if r_day_num > self._last_date.get(code_str, 0):
                            if code_str in self._last_date: # 不是第一次见，是真的变天了
                                logger.info(f"🔄 [{code_str}] Resetting intraday trackers for new day {r_day_num}")
                            self._last_vol[code_str] = 0.0
                            self._cumulative_amt[code_str] = 0.0
                            self._intraday_high[code_str] = 0.0
                            self._last_date[code_str] = r_day_num

                        anchors = baseline_tracker.get_anchor(code_str)
                        
                        # 默认状态
                        is_sbc = False
                        status = []
                        
                        if anchors:
                            # 标准化价格获取：优先使用配置映射的 trade 列，其次是 trade/now 默认值
                            price = float(row.get(active_trade_col, row.get('trade', row.get('now', 0))))
                            avg_p = float(row['avg_price'])
                            y_high = float(anchors.get('yesterday_high', 0))
                            p_high = float(anchors.get('prev_high', 0))
                            ma60 = float(row.get('ma60', anchors.get('ma60', 0))) # 动态 ma60 优先
                            last_l = float(anchors.get('last_low', 0))
                            
                            hmax60 = float(anchors.get('hmax60', 0))
                            hmax   = float(anchors.get('hmax', 0))
                            max5   = float(anchors.get('max5', 0))
                            high4  = float(anchors.get('high4', 0))
                            last_c = float(anchors.get('last_close', 0))
                            
                            # 688787 特征 1: 站稳均价线 (VWAP Support)
                            if price > avg_p * vwap_support_val: # 比例从配置读取
                                status.append("均线上")
                            
                            # 特征 2: 突破多日高点 (Structural Breakout)
                            structural_high = max(y_high, p_high, high4, 0)
                            if price > structural_high > 0:
                                status.append("创多日高")
                                
                            # --- ⚡ [NEW] 强势启动 / 大回归识别 ---
                            is_strong_start = False
                            if hmax60 > 0 and price > hmax60:
                                label = "强势启动" if last_c < hmax60 else "大回归突破"
                                status.append(label)
                                is_strong_start = (last_c < hmax60)
                            elif hmax > 0 and price > hmax:
                                label = "强启动" if last_c < hmax else "30D突破"
                                status.append(label)
                                is_strong_start = (last_c < hmax)
                            elif max5 > 0 and price > max5:
                                status.append("5D突破")
                                is_strong_start = (last_c < max5)
                                
                            # 特征 3: MA60 支撑位反弹
                            if ma60 > 0 and price > ma60 > last_l:
                                status.append("MA60支撑")
                            
                            # 特征 4: 诱空反转识别 (Bear Trap)
                            # 早盘跌破昨日低点后又快速收复昨日收盘价
                            low_p = float(row.get('low', price))
                            if low_p < last_l < last_c and price > last_c:
                                status.append("诱空转多")
                            
                            # ⚡ [NEW] 卖出特征 1: 跌破均价线 (VWAP Breakdown)
                            if price < avg_p * 0.995:
                                status.append("跌破均线")
                            
                            # 卖出特征 2: 跌破 MA60 支撑 (MA60 Breakdown)
                            if ma60 > 0 and price < ma60 < row.get('open', price):
                                status.append("跌破MA60")
                                
                            # --- 🔥 [NEW] 趋势加速逻辑 ---
                            # 1. 价格突破日内高点 (新高)
                            # 2. 量比 > 1.8
                            # 3. 价格 > MA60 (大周期支撑)
                            # 4. 突然加速上涨带量 (最近 3-tick 价格升, 当前 vol > 均值 * 1.5)
                            vol_r = float(row.get(active_ratio_col, 1.0))
                            p_fast = float(row.get('_p_fast', 0))
                            v_avg = float(row.get('_v_avg', 0))
                            cur_vol = float(row.get(active_vol_col, 0))
                            
                            r_high = float(row.get('high', price))
                            i_high = self._intraday_high.get(code_str, 0.0)
                            
                            # 初次记录
                            if i_high == 0: self._intraday_high[code_str] = r_high
                            
                            is_new_high = r_high > i_high > 0
                            is_accel = (p_fast > 0) and (cur_vol > v_avg * 1.5)
                            
                            if price > ma60 and is_new_high and vol_r > 1.8 and is_accel:
                                status.append("🔥趋势加速")
                            
                            # 更新日内高点
                            if r_high > i_high: self._intraday_high[code_str] = r_high

                            # 综合判定：SBC (Structural Breakout Champion)
                            is_rising = anchors.get('is_rising_struct', False)
                            is_sbc_buy = ("均线上" in status and ("创多日高" in status or "诱空转多" in status or "强势启动" in status or "强启动" in status)) or ("🔥趋势加速" in status)
                            is_sbc_sell = "跌破均线" in status or "跌破MA60" in status
                            
                            is_sbc = is_sbc_buy or is_sbc_sell
                            prev_sbc = self._last_sbc_status.get(code_str, False)
                            
                            # Debug log for 688787 specifically
                            # if code_str == '688787' and ("均线上" in status):
                            #     logger.info(f"[DEBUG-SBC] 688787: status={status}, is_rising={is_rising}, is_sbc={is_sbc}, price={price}, ma60={ma60}")

                            if is_sbc:

                                 # 只有在从“非SBC”转为“SBC”时标记图标
                                 if not prev_sbc:
                                     sig_text = "🚀强势结构"
                                     if "🔥趋势加速" in status:
                                         sig_text = "🔥趋势加速"
                                     elif not is_sbc_buy: # 如果不是买点，那就是破位
                                         sig_text = "⚠️结构破位"
                                     
                                     sbc_signals.append(sig_text)
                                     
                                     alert_key = f"{code_str}_{datetime.now().strftime('%Y%m%d')}_{'buy' if is_sbc_buy else 'sell'}"
                                     if alert_key not in self._sbc_alert_set:
                                         self._sbc_alert_set.add(alert_key)
                                         # 获取行数据中的时间字符串用于打印
                                         r_time_str = str(row.get('time', str(row.get('timestamp', '')))).split(' ')[-1]
                                         if is_sbc_buy:
                                             bonus = 15 if is_strong_start else 10
                                             scores_dict[idx_val] += bonus # 触发瞬间额外加分
                                             msg = f"🚀 [SBC-Breakout] {code_str}{name_display} "
                                             if is_strong_start: msg += "强势启动确认: "
                                             else: msg += "强势结构确认: "
                                             logger.warning(f"{msg}{r_time_str} 突破关键高位并站稳均线 ({avg_p:.2f})")
                                             
                                             # [Performance Feedback] 记录起始价格
                                             if code_str not in self._signal_start_price:
                                                 self._signal_start_price[code_str] = price
                                         else:
                                             logger.warning(f"⚠️ [SBC-Breakdown] {code_str}{name_display} 结构性破位: {r_time_str} 跌破关键位置或均线 ({avg_p:.2f})")
                                 else:
                                     # 持续状态下仅保持状态描述
                                     sbc_signals.append("-".join(status))
                                     
                                     # [Performance Feedback] 计算绩效分：如果信号后持续走强，额外奖励
                                     if code_str in self._signal_start_price:
                                         start_p = self._signal_start_price[code_str]
                                         if start_p > 0:
                                             performance_pct = (price - start_p) / start_p * 100
                                             if performance_pct > 0:
                                                 # 绩效加分 (涨幅的 2.5倍，封顶 25分)
                                                 perf_bonus = min(25, performance_pct * 2.5)
                                                 scores_dict[idx_val] += perf_bonus
                                                 if performance_pct > 2:
                                                     status.append(f"绩效+{perf_bonus:.0f}")
                            else:
                                 sbc_signals.append("-".join(status))
                            
                            # 同步当前状态
                            self._last_sbc_status[code_str] = is_sbc
                        else:
                            sbc_signals.append('')
                        
                    df['sbc_status'] = sbc_signals
                    # 同步回 final_scores
                    final_scores = pd.Series(scores_dict, index=df.index)
            
            # 4. 将结果写回 DataFrame (用于下游策略 & 日志)
            df['rt_emotion'] = final_scores.clip(0, 100)
            df['emotion_baseline'] = baselines
            
            # --- [New] Expose Baseline Status/Reason ---
            details = {}
            if baseline_tracker:
                details = baseline_tracker.get_all_baseline_details()
            
            # Use 'code' column for mapping
            if 'code' in df.columns:
                df['emotion_status'] = df['code'].astype(str).map(details).fillna('')
            else:
                df['emotion_status'] = df.index.astype(str).map(details).fillna('')
            
            # Record history snapshot
            now = time.time()
            self.history.append((now, self.scores.copy()))
            if len(self.history) > 60:
                self.history.popleft()

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"IntradayEmotionTracker update error: {str(e)}")

    def get_score(self, code: str) -> float:
        return self.scores.get(code, 50.0) # 默认 50 中性

    def get_scores_batch(self, codes: list[str]) -> dict[str, float]:
        """批量获取情绪分"""
        return {code: self.scores.get(code, 50.0) for code in codes}

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
    _enable_backup: bool
    def __init__(self, high_performance: bool = True, scraper_interval: int = 600, 
                 enable_backup: bool = False, validation_mode: bool = False,
                 simulation_mode: bool = False, verbose: bool = False):
        self.paused = False
        self.high_performance = high_performance
        self.simulation_mode = simulation_mode
        self.verbose = verbose
        
        # 核心缓存组件 (传递 verbose)
        self.kline_cache = MinuteKlineCache(
            max_len=240 if high_performance else 1440,
            simulation_mode=simulation_mode,
            verbose=verbose
        )
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
        self._enable_backup = enable_backup # 是否启用 .bak 文件备份 (Ramdisk 空间紧张默认关闭)

        self.cache_slot: DataFrameCacheSlot = DataFrameCacheSlot(
                cache_file=self._cache_path,
                fp_file=None,
                logger=logger,
            )
        self._last_save_fp = "" # 上次保存数据的指纹
        self._last_batch_fp = "" # 上次批次数据的指纹
        self._last_save_status = "N/A" # 上次保存状态
        self._last_update_date: Optional[str] = None # 最近处理的数据日期 (YYYY-MM-DD)
        self._is_recovered_empty = False # 是否处于“加载失败导致空数据”的危险状态
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
        # [MODIFIED] Increased from 4.0 to 20.0 to support 5 days of multi-day analysis
        self.TARGET_HOURS_HP = 20.0
        self.TARGET_HOURS_LEGACY = 4.0

        # Mode-based settings: Calculate max_len based on default 60s first
        default_interval = 60
        cache_len = int((self.TARGET_HOURS_HP * 3600) / default_interval) if high_performance else int((self.TARGET_HOURS_LEGACY * 3600) / default_interval)
        self.kline_cache.set_mode(cache_len) # Update mode rather than re-creating
        # [New] 基准值追踪器 (传递 verbose)
        self.emotion_baseline = DailyEmotionBaseline(verbose=verbose)
        self.emotion_tracker = IntradayEmotionTracker()
        self.subscribers = defaultdict(lambda: cast(list[Callable[..., object]], []))
        
        # [Phase 4] Central Name Mapping
        self._code_to_name: dict[str, str] = {}
        
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
            # --- [UNIFIED CACHE FIX] ---
            # 策略：优先加载 PKL 快照。如果 PKL 缺失或数据量严重不足 (少于 2000 只股)，
            # 则尝试从 sina_MultiIndex_data.h5 增量恢复。
            if not self.simulation_mode:
                cached_df = self.cache_slot.load_df()
                total_stocks = len(cached_df['code'].unique()) if not cached_df.empty else 0
                
                if total_stocks < 2000:
                    logger.info(f"📡 Snapshot deficient (Stocks: {total_stocks}), attempting recovery from HDF5...")
                    h5_df = self.recover_from_hdf5()
                    if not h5_df.empty:
                        if cached_df.empty:
                            cached_df = h5_df
                        else:
                            # 合并：以 H5 为准，补全缺失股票
                            cached_df = pd.concat([cached_df, h5_df]).drop_duplicates(subset=['code', 'time'], keep='last')
                        new_total = len(cached_df['code'].unique())
                        logger.info(f"✅ Recovery success. Total stocks now: {new_total}")

                if not cached_df.empty:
                    with timed_ctx("from_dataframe", warn_ms=800):
                        self.kline_cache.from_dataframe(cached_df)
                    logger.info(f"♻️ MinuteKlineCache recovered: {len(cached_df)} nodes.")
                    self._is_recovered_empty = False
                else:
                    logger.warning("ℹ️ No MinuteKlineCache found on disk or empty. Protection ACTIVE.")
                    self._is_recovered_empty = True
            else:
                logger.info("🛡️ Simulation Mode: Skipping Live MinuteKlineCache recovery to ensure data isolation.")
        except Exception as e:
            logger.error(f"Snapshot load error: {e}")
            self._is_recovered_empty = True

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
        后台维护任务：每 5 分钟检查一次内存和数据量
        """
        while True:
            time.sleep(300)  # Changed from 600 (10m) to 300 (5m) to match _save_interval
            try:
                # 无论是否有新数据，都在维护线程检查并执行周期性保存
                self.save_cache(force=False)
                
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
        
    def recover_from_hdf5(self) -> pd.DataFrame:
        """
        从 sina_MultiIndex_data.h5 恢复当日 Tick 轨迹并转化为 K 线格式
        """
        try:
            h5_fname = 'sina_MultiIndex_data'
            # 动态获取当前使用的 limit_time 后缀
            limit_time_int = int(getattr(cct, 'sina_limit_time', 60))
            h5_table = f"all_{limit_time_int}"
            
            logger.info(f"🔍 Reading HDF5: {h5_fname} table: {h5_table}")
            # 使用 tdx_hdf5_api 的统一接口读取
            df_mi = h5a.load_hdf_db(h5_fname, h5_table, timelimit=False,MultiIndex=True)
            if df_mi is None or df_mi.empty:
                logger.warning("⚠️ HDF5 recovery source is empty.")
                return pd.DataFrame()
            
            # --- 结构转换：MultiIndex -> Flat DataFrame ---
            # H5 结构通常是: Index=['code', 'ticktime'], Columns=['close', 'high', 'low', 'volume', ...]
            df = df_mi.reset_index()
            
            # 特殊处理：将 'ticktime' 字段转为 Unix 整数时间戳 'time'
            if 'ticktime' in df.columns:
                # 兼容性处理：如果包含日期，转为 Unix
                if pd.api.types.is_datetime64_any_dtype(df['ticktime']):
                    df['time'] = df['ticktime'].view('int64') // 10**9
                else:
                    # 如果是 HH:MM:SS，则拼接今日日期
                    now_str = datetime.now().strftime('%Y-%m-%d')
                    df['time'] = pd.to_datetime(now_str + " " + df['ticktime'].astype(str)).view('int64') // 10**9
            
            # 补齐 MinuteKlineCache 需要的字段
            if 'close' in df.columns:
                if 'open' not in df.columns: df['open'] = df['close']
                if 'high' not in df.columns: df['high'] = df['close']
                if 'low' not in df.columns: df['low'] = df['close']
            
            # 累计成交量处理 (H5 如果存的是分笔，这里需要聚合)
            # 但实际上 sina_MultiIndex 存的是快照轨迹，可以直接使用
            if 'volume' not in df.columns: df['volume'] = 0
            df['cum_vol_start'] = 0 # 恢复时通常设为0，由后续 update 修正
            
            # 规范化列名
            needed = ['code', 'time', 'open', 'high', 'low', 'close', 'volume', 'cum_vol_start']
            df = df[[c for c in needed if c in df.columns]]
            
            return df
            
        except Exception as e:
            logger.error(f"❌ recover_from_hdf5 failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return pd.DataFrame()

    def register_names(self, df_or_dict: Any):
        """[Phase 4] 为系统注册股票名称"""
        if isinstance(df_or_dict, pd.DataFrame):
            if 'code' in df_or_dict.columns and 'name' in df_or_dict.columns:
                m = df_or_dict.set_index('code')['name'].to_dict()
                self._code_to_name.update(m)
                self.emotion_tracker.register_names(m) # 同时同步给 tracker
        elif isinstance(df_or_dict, dict):
            self._code_to_name.update(df_or_dict)
            self.emotion_tracker.register_names(df_or_dict)

    def update_batch(self, df: pd.DataFrame):
        """
        接收来自 fetch_and_process 的 DataFrame 快照
        """
        t0 = time.time()
        is_trading = cct.get_work_time_duration()

        # [FIX] Simulation Mode 必须绕过暂停和时段检查
        if not self.simulation_mode:
            if self.paused or not is_trading:
                if self.emotion_baseline.get_last_calc_date() is None:
                    pass
                else:
                    return

        try:
            if df.empty: return

            # Fix: Ensure 'code' exists as a column (often in index)
            # if 'code' not in df.columns:
            #     df = df.copy()
            #     df['code'] = df.index

            # [FIX] 解决 code 列与 index 名重复导致的二义性
            if 'code' in df.columns:
                if df.index.name == 'code':
                    df = df.reset_index(drop=True)
            else:
                if df.index.name == 'code':
                    df = df.reset_index()
                else:
                    df = df.copy()
                    df['code'] = df.index

            # [Phase 4] Data Enrichment: Ensure 'name' column exists
            if 'name' in df.columns:
                # Learn/Update name mapping from incoming data
                try:
                    # Only learn names that are real (not just the code)
                    mask = (df['name'].notna()) & (df['name'].astype(str) != df['code'].astype(str))
                    if mask.any():
                        # Cast to str to satisfy type checker
                        new_names = {str(k): str(v) for k, v in df[mask].set_index('code')['name'].to_dict().items()}
                        if new_names:
                            self._code_to_name.update(new_names)
                            self.emotion_tracker.register_names(new_names)
                except:
                    pass
            
            if 'name' not in df.columns and self._code_to_name:
                # 尽量不在主循环中逐行 map 以保持性能，仅在列缺失时补全
                df['name'] = df['code'].map(self._code_to_name).fillna(df['code'])
            elif 'name' not in df.columns:
                df['name'] = df['code'] # 兜底防止后续 KeyError
            # --- 🚀 批次指纹校验：防止重复推送同一秒的数据 ---
            check_sample = df.head(5).copy()
            
            # # 计算开盘基准情绪 (每天确保计算一次)
            # # 移除 < 940 的限制，交由 emotion_baseline 内部控制频率
            # self.emotion_baseline.calculate_baseline(df)

            # # 更新情绪 (传入 baseline)
            # self.emotion_tracker.update_batch(df, self.emotion_baseline)

            # 1. 抓取元信息并计算时间戳 (更宽的准入窗口: 9:10 - 15:10)
            # 🚦 指纹校验优化：采用前 50 行以防止首行静止导致整个批次被跳过
            check_sample = df.head(50)
            raw_ts = time.time()
            time_source = "system_clock"
            
            for col in ['timestamp', 'time', 'ticktime']:
                if col in check_sample.columns:
                    try:
                        val = check_sample[col].iloc[0]
                        converted_ts = pd.to_datetime(val).timestamp()
                        raw_ts = float(converted_ts)
                        time_source = col
                        break
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to parse {col}: {e}")

            # 仅在非交易活跃期或第一次收到批次时记录诊断信息
            dt_now = datetime.fromtimestamp(raw_ts)
            hhmm = int(dt_now.strftime('%H%M'))
            
            if not getattr(self, '_time_source_logged', False):
                logger.info(f"🚦 First realtime batch identified. Time source: {time_source}, Market Time: {hhmm}")
                self._time_source_logged = True
            
            # 手动判定时段 (替代 strict 的 cct.get_realtime_status)
            is_trade_day = cct.get_trade_date_status()
            # 准入控制：盘中允许 9:15 之后的批次进入，包含完整竞价
            is_valid_hour = (915 <= hhmm <= 1135) or (1255 <= hhmm <= 1515)
            is_realtime = is_trade_day and is_valid_hour
            
            # 2. 跨日检测
            incoming_date = dt_now.strftime('%Y-%m-%d')
            if self._last_update_date and incoming_date != self._last_update_date:
                # [REMOVED] Daily reset on transition prevents multi-day analysis.
                logger.info(f"📅 Day transition: {self._last_update_date} -> {incoming_date}. (Multi-day support enabled, keeping cache)")
                # self.reset_state()
            self._last_update_date = incoming_date

            # 3. [CRITICAL FIX] 指纹校验优化：防止局部静态个股屏蔽全场更新
            # [REFINED] 扩大采样范围，确保大盘个股变动能实时触发批次更新
            total_count = len(df)
            # 头 50 + 尾 50 + 均匀采样，充分覆盖 5000+ 个股
            indices = list(range(0, min(total_count, 50))) # 头部 50 只
            if total_count > 100:
                # 每隔 5% 采样一个点
                indices.extend([int(total_count * i / 20) for i in range(1, 20)])
                indices.extend(list(range(max(0, total_count - 50), total_count))) # 尾部 50 只
            
            # 提取指纹特征列
            fp_cols = ['code']
            for c in ['trade', 'now', 'price']:
                if c in df.columns:
                    fp_cols.append(c)
                    break
            if 'volume' in df.columns:
                fp_cols.append('volume')
            
            # 仅对采样行进行指纹计算，确保覆盖全场
            check_sample = df.iloc[list(set(indices))]
            
            # [REFINED] 将分钟级时间加入指纹，确保每分钟至少触发一次全流程 (Heartbeat)
            batch_fp = f"{hhmm}_" + df_fingerprint(check_sample, cols=fp_cols)
            is_new_batch = (batch_fp != self._last_batch_fp)

            # 无论是否实时，若基准尚未计算，优先尝试一次
            if self.emotion_baseline.get_last_calc_date() is None:
                self.emotion_baseline.calculate_baseline(df)
                self.emotion_tracker.update_batch(df, self.emotion_baseline)
                if not is_trading:
                    return
            # 4. 核心数据更新 (Simulation 模式下跳过 is_realtime 检查)
            if (self.simulation_mode or is_realtime or hhmm >= 1500) and is_new_batch:
                if self.update_count == 0:
                    logger.info(f"🚦 First realtime batch. Time: {hhmm}, Columns: {list(df.columns)[:5]}")
                
                if self.verbose:
                    logger.info(f"💾 Processing batch: {hhmm} ({len(df)} stocks)")
                
                self._last_batch_fp = batch_fp
                
                # 🔌 [REFINED] Backend-driven Signal Detection & Data Hub Publishing
                # Logic moved from GUI to backend for multi-process awareness
                enriched_df = df.copy()
                if 'code' in enriched_df.columns:
                    enriched_df = enriched_df.drop_duplicates(subset=['code'])
                
                try:
                    from stock_logic_utils import detect_signals
                    # detect_signals handles scores and signal types (BUY_N, BUY_S, etc.)
                    enriched_df = detect_signals(enriched_df)
                except Exception as sig_err:
                    logger.error(f"[Backend] Signal detection failed: {sig_err}")

                # [REMOVED] DataHubService publish logic
                # try:
                #     from data_hub_service import DataHubService
                #     DataHubService.get_instance().publish_df_all(enriched_df)
                # except Exception as dh_err:
                #     logger.error(f"[DataHub] Failed to publish enriched df_all: {dh_err}")

                # [OPTIMIZED] Periodically log gap statistics - throttle to avoid log flood
                now_t = time.time()
                if not hasattr(self, '_last_gap_log_t'): self._last_gap_log_t = 0
                if now_t - self._last_gap_log_t > 300: # Every 5 minutes
                    self.kline_cache.count_gaps(threshold=200)
                    self._last_gap_log_t = now_t

                # Continue with existing pipeline...
                self.update_count += 1
                
                # 情绪与 KLine 更新
                # [OPTIMIZED] Skip calculate_baseline if already done for TODAY
                # [FIX] Simulation 模式下跳过自动重新计算，防止覆盖手动设置的大样基准
                if not self.simulation_mode:
                    if self.emotion_baseline.get_last_calc_date() != datetime.now().strftime("%Y-%m-%d"):
                        self.emotion_baseline.calculate_baseline(df)
                    
                self.emotion_tracker.update_batch(df, self.emotion_baseline)
                
                if any(col in df.columns for col in ['trade', 'now', 'price', 'close', 'hq_last', 'llastp']):
                    self.kline_cache.update_batch(df, self.subscribers)
                
                # 3. 性能统计
                self.update_count += 1
                self.total_rows_processed += len(df)
                t1 = time.time()
                duration = t1 - t0
                if duration > 0:
                    self.batch_rates_dq.append(len(df) / duration)
                self.last_batch_time = t1

                # 🔌 [REFINED] Periodic metadata logging
                if self.update_count % 500 == 0:
                    n = gc.collect()
                    if n > 0: logger.debug(f'🧹 GC collected {n} objects')

            # =========================
            # Snapshot Cache (Periodic Check)
            # =========================
            self.save_cache(force=False)
                
        except Exception as e:
            logger.error(f"DataPublisher update_batch error: {e}")

    def save_cache(self, force: bool = False):
        """
        手动或周期性将当前 K 线缓存保存到磁盘快照
        :param force: 是否强制保存 (忽略时间间隔)
        """
        try:
            if not hasattr(self, 'kline_cache') or not self.kline_cache:
                return
            
            now = time.time()
            # 只有在强制模式，或者时间间隔已到时才检查脏标记
            if not force and (now - self._last_save_ts < self._save_interval):
                return
            
            # 如果不脏，则只更新时间戳
            if not self.kline_cache._is_dirty and self._last_save_ts > 0:
                self._last_save_ts = now
                return

            with timed_ctx("save_kline_cache", warn_ms=1500):
                save_cache_df = self.kline_cache.to_dataframe()
                if not save_cache_df.empty:
                    # [PROTECTION] 如果启动时加载失败，且当前数据量依然不足 (如 < 10000 行)，禁止自动保存覆盖
                    current_rows = len(save_cache_df)
                    if self._is_recovered_empty and current_rows < 10000:
                        if now - self._last_save_ts > 1800: # 每 30 分钟才报一次警告
                             logger.warning(f"⚠️ [Protection] Snapshot save SKIPPED: Recovered empty, and current rows({current_rows}) < 10000 threshold.")
                             self._last_save_ts = now
                        return

                    # 1. 保存到本地磁盘进行恢复 (已在 cache_utils.py 中加持 min_rows_factor 保护)
                    status = self.cache_slot.save_df(
                        save_cache_df, 
                        persist=True, 
                        backup=self._enable_backup,
                        min_rows_factor=0.5,
                        force=force
                    )
                    
                    if status:
                        self._is_recovered_empty = False # 成功保存一次后，解除空加载警报
                    
                    self._last_save_ts = now
                    self.kline_cache._is_dirty = False
                    self._last_save_status = "SUCCESS" if status else "FAILED"
                    logger.info(f"💾 MinuteKlineCache snapshot saved. (Rows: {len(save_cache_df)}, Success: {status}, Force: {force})")
                else:
                    # 如果数据为空（可能被过滤了），也更新时间戳以避免频繁重试
                    self._last_save_ts = now
                    self._last_save_status = "EMPTY_SKIP"
                    logger.debug("save_cache skipped: no data to save (maybe outside trading hours).")
        except Exception as e:
            logger.error(f"save_cache error: {e}")


    def subscribe(self, code: str, callback: Callable[..., object]):
        self.subscribers[code].append(callback)

    def get_minute_klines(self, code: str, n: int = 60) -> list[dict[str, Any]]:
        return self.kline_cache.get_klines(code, n)

    def get_emotion_score(self, code: str):
        return self.emotion_tracker.get_score(code)

    def get_emotion_scores(self, codes: list[str]) -> dict[str, float]:
        """批量获取当前情绪分，用于 UI 列表刷新"""
        return self.emotion_tracker.get_scores_batch(codes)

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
                self.kline_cache.cache[code] = []
            
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
    print(f"   - Total Nodes across all lists: {total_nodes}")
    print(f"   - Avg Nodes per Stock: {final_status.get('avg_nodes_per_stock', 0):.1f}")
    print(f"   - Est. Incremental Memory per Node: {per_node:.1f} bytes")
    
    print("\n✨ Test Sequence Completed.")
