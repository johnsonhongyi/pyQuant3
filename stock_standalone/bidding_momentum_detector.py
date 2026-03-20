# -*- coding: utf-8 -*-
"""
Bidding Momentum Detector v2 - 竞价及尾盘板块联动异动检测器
使用 DataPublisher 的订阅式分钟K线接口，实现真实逐笔分析能力。

核心能力:
1. 订阅所有监控个股的分钟 K 线更新 (via DataPublisher.subscribe)
2. 每分钟 K 线到达时，评估"高开连续拉升+放量"形态
3. 龙头触发后，展开所属板块，找出龙二龙三 (一点带面)
4. 策略参数可动态配置（每日新高、振幅、涨幅、MA反弹）
"""
import logging
import time
import threading
import datetime
import re
from typing import Dict, List, Set, Any, Optional, Callable, TYPE_CHECKING
from collections import defaultdict, deque
import pandas as pd
import json
import os
import gzip
from JohnsonUtil import commonTips as cct

if TYPE_CHECKING:
    from realtime_data_service import DataPublisher

logger = logging.getLogger(__name__)

def get_limit_up_threshold(code: str) -> float:
    """获取各市场接近涨停的阈值 (主板10%, 科创/创业20%, 北证30%)"""
    code_str = str(code)
    if code_str.startswith(('688', '30')):
        return 19.5
    elif code_str.startswith(('43', '83', '87', '92')):
        return 29.5
    return 9.5
    
SECTOR_BLACKLIST = {
    '深股通', '沪股通', '融资融券', '标普概念', 'MSCI中国', '剔除纳斯', 
    '机构重仓', '昨日涨停', '昨日触板', '创业板综', '证金持股', '上证180',
    '中证500', '沪深300', '深证成指', '基金重仓', '北向资金', '深成指',
    '含HS300', '国企改革', '破净股', '预盈预增', 'QFII重仓', '社保重仓',
    '基金新增', '预亏预减'
}

class TickSeries:
    """
    单只个股的分钟 K 线滚动队列，外加基础统计缓存。
    """
    __slots__ = ('code', 'klines', 'last_close', 'last_high', 'last_low', 
                 'open_price', 'now_price', 'high_day', 'low_day', 'ma20', 'ma60', 
                 'category', 'name', 'score', 'first_breakout_ts', 'pattern_hint',
                 'is_untradable', 'is_counter_trend', 'is_gap_leader', 'lastdu', 'lastdu4',
                 'ral', 'top0', 'top15', 'is_accumulating', 'is_reversal',
                 'is_upper_band', 'is_new_high', 'momentum_score',
                 '_splitted_cats', '_total_vol', '_total_amt',
                 'score_anchor', 'score_diff', 'price_anchor', 'pct_diff', 'price_diff', 'dff', 'cycle_stage')

    def __init__(self, code: str, max_len: int = 30):
        self.code = code
        self.klines: deque = deque(maxlen=max_len)
        self.last_close: float = 0.0
        self.last_high: float = 0.0
        self.last_low: float = 0.0
        self.open_price: float = 0.0
        self.now_price: float = 0.0 # [NEW] 实时 Tick 价格
        self.high_day: float = 0.0
        self.low_day: float = 0.0
        self.ma20: float = 0.0
        self.ma60: float = 0.0
        self.category: str = ''
        self.name: str = ''
        self.score: float = 0.0
        self.first_breakout_ts: float = 0.0 # 记录当日首次异动的时间戳
        self.pattern_hint: str = "" # 记录形态特征词（如 V反、突破等）
        self.is_untradable: bool = False
        self.is_counter_trend: bool = False
        self.is_gap_leader: bool = False
        self.lastdu: float = 0.0 # [NEW] 价格波动幅度 (Range Volatility)
        self.lastdu4: float = 0.0 # [NEW] 短期(4日)价格波动幅度
        self.ral: int = 0 # [NEW] Relative Accumulation Level (count(low > ma20))
        self.top0: int = 0 # 一字涨停计数 (强度指标)
        self.top15: int = 0 # 强势突破计数 (强度指标)
        self.is_accumulating: bool = False # [NEW]
        self.is_reversal: bool = False # [NEW]
        self.is_upper_band: bool = False # [NEW] 沿 Upper 上轨
        self.is_new_high: bool = False   # [NEW] 创历史/波段新高
        self.momentum_score: float = 0.0 # [NEW] 持续动量累计分
        self._splitted_cats: Optional[List[str]] = None
        self._total_vol: float = 0.0
        self._total_amt: float = 0.0
        self.score_anchor: float = 0.0
        self.score_diff: float = 0.0
        self.price_anchor: float = 0.0
        self.pct_diff: float = 0.0
        self.price_diff: float = 0.0
        self.dff: float = 0.0
        self.cycle_stage: int = 2

    def update_meta(self, row: pd.Series):
        """从 df_all 行更新元数据"""
        # [FIX] 优先使用 pre_close (通常是静态的昨收)，其次是上次成交价
        # 避免在竞价阶段 llstp 可能返回当前虚拟撮合价导致涨幅恒为 0 的问题。
        val_pre = row.get('pre_close', row.get('llastp', row.get('lastp1d', row.get('llastp1d', row.get('llstp', 0.0)))))
        self.last_close = float(val_pre) if not pd.isna(val_pre) and val_pre > 0 else 0.0
        
        # 记录 open_price
        val_open = row.get('open', 0.0)
        self.open_price = float(val_open) if not pd.isna(val_open) else 0.0

        val_lasth = row.get('lasth1d', self.last_close)
        self.last_high = float(val_lasth) if not pd.isna(val_lasth) else 0.0
        
        val_lastl = row.get('lastl1d', self.last_close)
        self.last_low = float(val_lastl) if not pd.isna(val_lastl) else 0.0
        
        val_open = row.get('open', 0.0)
        self.open_price = float(val_open) if not pd.isna(val_open) else 0.0
        
        # [FIX] 捕获实时价格
        val_now = row.get('now', row.get('trade', row.get('price', row.get('nclose', self.now_price))))
        self.now_price = float(val_now) if not pd.isna(val_now) else 0.0
        
        val_high = row.get('high', 0.0)
        self.high_day = float(val_high) if not pd.isna(val_high) else 0.0
        
        val_low = row.get('low', 0.0)
        self.low_day = float(val_low) if not pd.isna(val_low) else 0.0
        
        val_ma20 = row.get('ma20d', 0.0)
        self.ma20 = float(val_ma20) if not pd.isna(val_ma20) else 0.0
        
        val_ma60 = row.get('ma60d', 0.0)
        self.ma60 = float(val_ma60) if not pd.isna(val_ma60) else 0.0
        self.category = str(row.get('category', ''))
        self.name = str(row.get('name', self.code))
        self.lastdu = float(row.get('lastdu', 0.0))
        self.lastdu4 = float(row.get('lastdu4', 0.0))
        # [FIX] 对可能为 NaN 的整数字段进行安全转换
        ral_val = row.get('ral', 0)
        self.ral = int(ral_val) if not pd.isna(ral_val) else 0
        
        self.dff = float(row.get('dff', 0.0)) if not pd.isna(row.get('dff')) else 0.0
        
        top0_val = row.get('top0', 0)
        self.top0 = int(top0_val) if not pd.isna(top0_val) else 0
        
        top15_val = row.get('top15', 0)
        self.top15 = int(top15_val) if not pd.isna(top15_val) else 0

        # [NEW] 从 DataRow 提取周期阶段
        stage_val = row.get('cycle_stage', row.get('cycle_stage_vect', 2))
        self.cycle_stage = int(stage_val) if not pd.isna(stage_val) else 2

        self._splitted_cats = None # 重置缓存

    def get_splitted_cats(self) -> List[str]:
        if self._splitted_cats is not None:
            return self._splitted_cats
        import re
        parts = re.split(r'[;；,，/\- ]', str(self.category))
        self._splitted_cats = [p.strip() for p in parts if p.strip() and p.strip() != 'nan']
        return self._splitted_cats

    def push_kline(self, kline: dict):
        """追加一根分钟 K 线"""
        # 如果队列满了，减去最老的统计
        if len(self.klines) == self.klines.maxlen:
            oldest = self.klines[0]
            v = float(oldest.get('volume', 0.0))
            c = float(oldest.get('close', 0.0))
            self._total_vol -= v
            self._total_amt -= v * c

        self.klines.append(kline)
        # 增量维护统计
        vol = float(kline.get('volume', 0.0))
        close = float(kline.get('close', 0.0))
        self._total_vol += vol
        self._total_amt += vol * close
        if close > self.high_day: self.high_day = close
        if close < self.low_day or self.low_day == 0: self.low_day = close

    def load_history(self, klines: List[dict]):
        """初始化冷启历史数据"""
        self.klines.clear()
        self._total_vol = 0.0
        self._total_amt = 0.0
        # 过滤无效数据并推入
        valid_klines = [k for k in klines if k and 'close' in k]
        for k in valid_klines[-self.klines.maxlen:]:
            self.push_kline(k)

    @property
    def vwap(self) -> float:
        return self._total_amt / self._total_vol if self._total_vol > 0 else self.current_price

    @property
    def current_pct(self) -> float:
        """当前在日内的涨幅 (%), 基于 last_close"""
        if self.last_close <= 0:
            return 0.0
        # [FIX] 优先使用实时价格
        cp = self.current_price
        if cp <= 0: return 0.0
        return (cp - self.last_close) / self.last_close * 100.0

    @property
    def current_price(self) -> float:
        # [FIX] 优先返还最新的 Tick 价格，否则回退到 K 线
        if self.now_price > 0:
            return self.now_price
        if not self.klines:
            return 0.0
        return self.klines[-1].get('close', 0.0)


class BiddingMomentumDetector:
    """
    订阅式竞价/尾盘异动检测器。
    - 通过 DataPublisher.subscribe 注册回调，实时接收分钟 K 线
    - 检测高开连续拉升+放量（"追涨结构"过滤）
    - 发现龙头后展开板块，找出跟随股
    """

    def __init__(self, realtime_service: Optional["DataPublisher"] = None, simulation_mode: bool = False):
        # ---- 数据服务 ----
        self.realtime_service = realtime_service
        self.simulation_mode = simulation_mode

        # ---- 策略参数：支持动态配置 ----
        self.strategies: Dict[str, Dict[str, Any]] = {
            'new_high':   {'enabled': True,  'name': '每日新高附近'},
            'amplitude':  {'enabled': True,  'name': '振幅过滤',   'min': 2.0, 'max': 20.0},
            'pct_change': {'enabled': True,  'name': '涨幅过滤',   'min': 1.5, 'max': 9.5},
            'ma_rebound': {'enabled': True,  'name': '昨收回踩 MA20/MA60 高开'},
            'surge_vol':  {'enabled': True,  'name': '放量倍数',   'min_ratio': 1.5},
            'consecutive_up': {'enabled': True, 'name': '连续上涨 K 棒', 'bars': 2},
        }

        # ---- 内部状态 ----
        self._lock = threading.Lock()

        # code → TickSeries
        self._tick_series: Dict[str, TickSeries] = {}

        # 已注册到 realtime_service 的 code set（防重复订阅）
        self._subscribed: Set[str] = set()

        # 板块图：sector → set(codes)
        self.sector_map: Dict[str, Set[str]] = defaultdict(set)

        # 最终结果：sector → {leader, followers, score, ts, ...}
        self.active_sectors: Dict[str, Dict[str, Any]] = {}

        # 上次板块 GC 时间戳
        self._last_gc_ts: float = 0.0
        # [NEW] 上次刷新时间戳 (用于控制刷新频率)
        self._last_refresh_ts: float = 0.0
        # [NEW] 强制刷新请求标志
        self._force_update_requested: bool = False

        # 聚合门槛评分 (下调以捕捉萌芽期)
        self.score_threshold = 1.0
        # 板块入场所需个股最低分
        self.sector_min_score = 2.0
        # [NEW] 板块综合强度门槛 (board_score)
        self.sector_score_threshold: float = 5.0
        self.last_data_ts = 0.0

        # key=code, val={name, sector, pct, time_str, reason, reason, pattern_hint, release_risk}
        self.daily_watchlist: Dict[str, Dict[str, Any]] = {}
        self.enable_log = True # 是否允许向控制台/文件打印重点监控日志
        
        # ---- [NEW] 强度历史对比与变动追踪 ----
        self.comparison_interval: float = 30 * 60 # 默认 30 分钟对比窗口 (秒)
        self.baseline_time: float = time.time()  # 阈值的初始基准时间
        # sector -> anchor_score
        self.sector_anchors: Dict[str, float] = {}
        self.reset_threshold: float = 10.0 # 变动超过 10 分自动重置锚点
        
        # [NEW] 个股切片涨幅重置阈值 (1.0%)
        self.price_reset_threshold: float = 1.0

        # ---- [NEW] 选股器联动与两阶段刷新 ----
        self.stock_selector_seeds: Dict[str, Dict[str, Any]] = {} # 昨曾强势/反转股代码
        self._concept_data_date: Optional[datetime.date] = None
        self._concept_first_phase_done = False
        self._concept_second_phase_done = False
        
        # [Tier 2] 增量缓存
        self._global_snap_cache: Dict[str, Dict[str, Any]] = {}
        self._sector_active_stocks_persistent: Dict[str, Dict[str, Any]] = defaultdict(dict)

        # [NEW] 模式保护
        self.in_history_mode = False

        # 初始加载一次昨日选股结果
        self._load_stock_selector_data()

    def _load_stock_selector_data(self):
        """从数据库加载最近一个交易日的强势/反转选股结果作为种子"""
        try:
            from trading_logger import TradingLogger
            t_logger = TradingLogger()
            # 获取最近一天的选股记录 (不带 limit，使用默认逻辑)
            df_seeds = t_logger.get_selections_df() 
            if not df_seeds.empty and 'code' in df_seeds.columns:
                # 过滤高分种子
                high_df = df_seeds[df_seeds['score'] >= 80]
                self.stock_selector_seeds = {
                    str(r.code).zfill(6): {'code': str(r.code).zfill(6), 'reason': getattr(r, 'reason', '')}
                    for r in high_df.itertuples(index=False)
                }
                logger.info(f"[Detector] 成功加载 {len(self.stock_selector_seeds)} 只预选种子股 (Sc>=80)")
            
            # [FIX] 模拟模式下不加载持久化会话数据，防止实盘干扰回测结果
            if not self.simulation_mode:
                self.load_persistent_data()
            else:
                logger.info("[Detector] Simulation Mode Active: Skipping persistent session data load.")
        except Exception as e:
            logger.warning(f"[Detector] 种子加载或持久化恢复失败: {e}")

    # =========================================================
    # 公共接口
    # =========================================================

    def reset_observation_anchors(self):
        """
        手动或按周期重置所有观测基准：
        1. 重置板块强度锚点
        2. 重置个股分锚点
        3. 重置个股价格瞄点 (用于切片涨跌计算)
        4. 重置全局基准时间
        """
        now = time.time()
        with self._lock:
            self.baseline_time = now
            self.sector_anchors.clear()
            for ts in self._tick_series.values():
                ts.score_anchor = ts.score
                ts.price_anchor = ts.current_price
            logger.info(f"🔄 [Detector] All observation anchors have been reset.")


    def set_strategy(self, key: str, **kwargs):
        """动态更新策略参数"""
        if key in self.strategies:
            self.strategies[key].update(kwargs)

    def register_codes(self, df_all: pd.DataFrame):
        """
        从 df_all 中注册新的 code 订阅，补充元数据。
        需在主线程调用（如 update_tree / on_realtime_data_arrived）。
        """
        if df_all is None or df_all.empty:
            return

        # 确保 code 列存在
        if 'code' in df_all.columns:
            df = df_all.set_index('code', drop=False)
        else:
            df = df_all.copy()
            df['code'] = df.index.astype(str)

        # 重建板块图（每次全量更新，成本低）
        self._rebuild_sector_map(df)

        new_codes = []
        for row in df.itertuples(index=False):
            # [FIX] 显式使用 code 列，避免 itertuples Index 属性导致的 RangeIndex 数据错位
            code = str(getattr(row, 'code', '')).strip().zfill(6)
            if code == '000000' or not code: continue
            
            with self._lock:
                if code not in self._tick_series:
                    ts_obj = TickSeries(code)
                    # 将 row 转为 dict 并丢弃可能干扰的 Index
                    ts_obj.update_meta(pd.Series(row._asdict()))
                    self._tick_series[code] = ts_obj
                    new_codes.append(code)
                else:
                    self._tick_series[code].update_meta(pd.Series(row._asdict()))

        # 对新 code 或 K线为空的 code：拉历史 K 线做冷启
        target_codes = new_codes + [c for c in df['code'].astype(str).str.strip().str.zfill(6) if c in self._tick_series and not self._tick_series[c].klines]
        target_codes = list(set(target_codes)) # 去重
        
        if self.realtime_service and target_codes:
            for code in target_codes:
                try:
                    # [REFINED] 仅在真的为空时才拉取，避免重复拉取浪费性能
                    ts = self._tick_series.get(code)
                    if ts and not ts.klines:
                        hist = self.realtime_service.get_minute_klines(code, n=30)
                        if hist:
                            with self._lock:
                                ts.load_history(hist)
                                
                    if code not in self._subscribed:
                        self.realtime_service.subscribe(code, self._on_tick)
                        self._subscribed.add(code)
                except Exception as e:
                    logger.warning(f"[Detector] 历史K线加载/订阅失败 {code}: {e}")

    def get_active_sectors(self) -> List[Dict[str, Any]]:
        """
        返回当前活跃板块列表，按 score 降序。
        [DEFENSIVE] 确保每个 dict 都有 'sector' 字段，防止旧快照加载后渲染报错。
        """
        with self._lock:
            res = []
            for name, info in self.active_sectors.items():
                if not isinstance(info, dict): continue
                if 'sector' not in info:
                    info['sector'] = name
                res.append(info)
            result = sorted(res, key=lambda x: x.get('score', 0), reverse=True)
        return result

    def get_daily_watchlist(self) -> List[Dict[str, Any]]:
        """
        返回当日重点表，按入表时间升序(就是字典内已按时间顺序填入)。
        包含：涨停个股 + 板块溢出个股。
        """
        with self._lock:
            return list(self.daily_watchlist.values())

    def update_scores(self, active_codes=None):
        """
        定时调用（如 UI 刷新计时器），对所有已注册 code 重新评分，
        并聚合为板块结果。适用于没有订阅推送（非交易时段调试）。
        
        active_codes: List[str], 如果提供，则仅对这些代码进行评分（提升回放效率）
        """
        if active_codes is not None:
            codes = active_codes
        else:
            with self._lock:
                codes = list(self._tick_series.keys())
                
        for code in codes:
            self._evaluate_code(code)
        
        # 优化：仅聚合受影响的板块
        self._aggregate_sectors(active_codes=active_codes)

    # ------------------------------------------------------------------ 持久化
    def _get_persistence_path(self, snapshot_date: str = None) -> str:
        # 使用 JohnsonUtil 中的 ramdisk 路径获取方法，统一管理
        if snapshot_date:
            path = os.path.join(cct.get_base_path(), "snapshots")
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            return os.path.join(path, f"bidding_{snapshot_date}.json.gz")
        return cct.get_ramdisk_path("bidding_session_data.json.gz")

    def save_persistent_data(self):
        """保存当前个股得分和板块强度到磁盘 (原子化强化版)"""
        if self.in_history_mode or not cct.get_trade_date_status():
            return

        try:
            # [Data Preparation ...]
            data = {
                'timestamp': round(time.time(), 2),
                'stock_scores': {code: round(ts.score, 2) for code, ts in self._tick_series.items() if (ts.score > 0 or ts.momentum_score > 0)},
                'momentum_scores': {code: round(ts.momentum_score, 2) for code, ts in self._tick_series.items() if ts.momentum_score > 0},
                'sector_data': {name: info for name, info in self.active_sectors.items() if info.get('score', 0) > 0},
                'stock_score_anchors': {code: round(ts.score_anchor, 2) 
                                        for code, ts in self._tick_series.items() if ts.score_anchor != 0.0},
                'baseline_time': round(self.baseline_time, 2),
                'sector_anchors': {name: round(s, 2) for name, s in self.sector_anchors.items()},
                'stock_price_anchors': {code: round(ts.price_anchor, 4) 
                                        for code, ts in self._tick_series.items() if ts.price_anchor > 0},
                'watchlist': self.daily_watchlist
            }
            
            sd_count = len(data.get('sector_data', {}))
            wl_count = len(data.get('watchlist', {}))
            significant_stocks = {code: s for code, s in data.get('stock_scores', {}).items() if s >= 0.1}
            ss_count = len(significant_stocks)
            
            if sd_count == 0 and wl_count == 0 and ss_count == 0:
                logger.debug("ℹ️ [Detector] No active signals to save.")
                return

            relevant_codes = set(significant_stocks.keys()) | set(data.get('watchlist', {}).keys()) | set(self.stock_selector_seeds.keys())
            for sinfo in self.active_sectors.values():
                relevant_codes.add(sinfo.get('leader'))
                for f in sinfo.get('followers', []):
                    relevant_codes.add(f.get('code'))
            
            meta_data = {}
            for code in relevant_codes:
                if not code: continue
                ts = self._tick_series.get(code)
                if ts:
                    meta_data[code] = {
                        'name': ts.name,
                        'reason': getattr(ts, 'pattern_hint', ''),
                        'category': ts.category,
                        'last_close': ts.last_close,
                        'open_price': ts.open_price,
                        'high_day': ts.high_day,
                        'low_day': ts.low_day,
                        'now_price': ts.current_price, # 这里的 current_price 会取最新的
                        # [OPTIMIZED] 分时数据不保存，节省关闭时的 IO 耗时，冷启动通过实时拉取恢复
                    }
            data['meta_data'] = meta_data

            # ⭐ [C-Reinforcement] 原子化写入：先写临时文件，然后 os.replace
            def atomic_gz_save(target_path, data_dict):
                temp_path = target_path + f".{os.getpid()}.tmp"
                try:
                    with gzip.open(temp_path, 'wt', encoding='utf-8') as f:
                        json.dump(data_dict, f, ensure_ascii=False)
                    # Windows 下 os.replace 是原子性的 (如果目标未被打开)
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    os.replace(temp_path, target_path)
                    return True
                except Exception as e:
                    if os.path.exists(temp_path): os.remove(temp_path)
                    raise e

            main_path = self._get_persistence_path()
            if atomic_gz_save(main_path, data):
                today_str = datetime.datetime.now().strftime('%Y%m%d')
                snapshot_path = self._get_persistence_path(snapshot_date=today_str)
                # [OPTIMIZED] 如果主路径与快照路径不同，直接复制已压好的文件，避免重复耗时的 JSON+GZIP
                if main_path != snapshot_path:
                    import shutil
                    try:
                        shutil.copy2(main_path, snapshot_path)
                    except Exception as e:
                        logger.warning(f"Failed to copy snapshot: {e}")
                        atomic_gz_save(snapshot_path, data)

            logger.info(f"💾 [Detector] Session data saved ({ss_count} stocks, {sd_count} sectors)")
        except Exception as e:
            logger.error(f"❌ [Detector] Persistence save failed: {e}")

    def load_persistent_data(self):
        """启动时从磁盘恢复得分和强度"""
        try:
            path = self._get_persistence_path()
            if not os.path.exists(path):
                return

            # [REFINED] 跨日保护逻辑：考虑周末和非交易日
            mtime = os.path.getmtime(path)
            file_dt = datetime.datetime.fromtimestamp(mtime)
            file_date_str = file_dt.strftime('%Y-%m-%d')
            now_dt = datetime.datetime.now()
            today_str = now_dt.strftime('%Y-%m-%d')

            is_expired = False
            try:
                # 获取从文件日期到今天的交易日列表 (使用 cct 中已初始化的 lazy-loaded 实例)
                trade_days = cct.a_trade_calendar.get_trade_days_interval(file_date_str, today_str)
                
                # 1. 如果中间隔了至少一个完整的交易日，肯定过期
                if len(trade_days) > 2:
                    is_expired = True
                # 2. 如果是相邻交易日（如周五到周一，或昨日到今日）
                elif len(trade_days) == 2:
                    # 如果今日是交易日，且已经接近/进入开盘时段 (9:15)，则视为过期
                    if cct.get_day_istrade_date(today_str):
                        if now_dt.hour > 9 or (now_dt.hour == 9 and now_dt.minute >= 15):
                            is_expired = True
                    # 如果今日不是交易日，或者还没到 9:15，我们保留上一交易日的数据
                # 3. 如果 len(trade_days) == 1，说明在同一个交易日内或都是非交易日，不过期
            except Exception as e:
                # 兜底逻辑：如果交易日历获取失败，回退到 15.5 小时硬性判断
                if time.time() - mtime > 15.5 * 3600:
                    is_expired = True
                logger.debug(f"[Detector] 交易日历判断异常，使用保底时长判断: {e}")

            if is_expired:
                logger.info(f"📅 [Detector] 持久化数据已过期 ({file_date_str} -> {today_str})，跳过加载。")
                return

            # 使用 gzip 解压读取
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                data = json.load(f)

            # 恢复个股分
            stock_scores = data.get('stock_scores', {})
            for code, score in stock_scores.items():
                if code not in self._tick_series:
                    self._tick_series[code] = TickSeries(code)
                self._tick_series[code].score = score
            
            # 恢复动量分
            momentum_scores = data.get('momentum_scores', {})
            for code, m_score in momentum_scores.items():
                if code in self._tick_series:
                    self._tick_series[code].momentum_score = m_score

            # 恢复板块数据
            self.active_sectors = data.get('sector_data', {})
            
            # 恢复全量历史与锚点
            stock_anchors = data.get('stock_score_anchors', {})
            for code, anchor in stock_anchors.items():
                if code in self._tick_series:
                    self._tick_series[code].score_anchor = anchor
                    
            self.baseline_time = data.get('baseline_time', time.time())
                
            self.sector_anchors = data.get('sector_anchors', {})
            
            # 恢复价格锚点 (用于计算切片涨跌 pct_diff)
            stock_price_anchors = data.get('stock_price_anchors', {})
            for code, p_anchor in stock_price_anchors.items():
                if code in self._tick_series:
                    self._tick_series[code].price_anchor = p_anchor
                
            # 恢复重点表
            self.daily_watchlist = data.get('watchlist', {})

            meta_data = data.get('meta_data', {})
            for code, m in meta_data.items():
                if code not in self._tick_series:
                    self._tick_series[code] = TickSeries(code)
                ts = self._tick_series[code]
                ts.last_close = m.get('last_close', ts.last_close)
                ts.open_price = m.get('open_price', ts.open_price)
                ts.high_day = m.get('high_day', ts.high_day)
                ts.low_day = m.get('low_day', ts.low_day)
                ts.now_price = m.get('now_price', ts.now_price)
                ts.name = m.get('name', ts.name)
                ts.category = m.get('category', ts.category)
                ts.score = m.get('score', ts.score)
                ts.first_breakout_ts = m.get('first_breakout_ts', ts.first_breakout_ts)
                ts.pattern_hint = m.get('pattern_hint', ts.pattern_hint)
                ts.momentum_score = m.get('momentum_score', ts.momentum_score)
            
            logger.info(f"♻️ [Detector] 会话数据已恢复: {len(stock_scores)} 只个股, {len(self.active_sectors)} 个板块")
        except Exception as e:
            logger.error(f"❌ [Detector] 加载会话数据失败: {e}")
        self._gc_old_sectors()

    def load_from_snapshot(self, filepath: str) -> bool:
        """从指定的快照文件恢复数据，用于历史复盘"""
        try:
            if not os.path.exists(filepath):
                logger.error(f"Snapshot file not found: {filepath}")
                return False

            with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                data = json.load(f)

            with self._lock:
                # 1. 重置当前状态
                self._tick_series.clear()
                self.active_sectors.clear()
                self.daily_watchlist.clear()
                self.sector_anchors.clear()

                # 2. 恢复个股数据与 Snap 缓存
                stock_scores = data.get('stock_scores', {})
                momentum_scores = data.get('momentum_scores', {})
                meta_data = data.get('meta_data', {})
                
                self._global_snap_cache.clear()
                
                for code, score in stock_scores.items():
                    ts = TickSeries(code)
                    ts.score = score
                    ts.momentum_score = momentum_scores.get(code, 0.0)
                    
                    # 恢复元数据
                    if code in meta_data:
                        m = meta_data[code]
                        ts.name = m.get('name', code)
                        ts.pattern_hint = m.get('reason', '')
                        ts.category = m.get('category', '')
                        ts.last_close = m.get('last_close', 0.0)
                        ts.high_day = m.get('high_day', 0.0)
                        ts.low_day = m.get('low_day', 0.0)
                        ts.last_high = m.get('last_high', 0.0)
                        ts.last_low = m.get('last_low', 0.0)
                        for k in m.get('klines', []):
                            ts.push_kline(k)
                    
                    self._tick_series[code] = ts
                    
                    # 同时重建 _global_snap_cache 以便 UI 渲染个股详情
                    self._global_snap_cache[code] = {
                        'score': score, 'pct': ts.current_pct, 'price': ts.current_price,
                        'name': ts.name, 'category': ts.category, 'last_close': ts.last_close,
                        'high_day': ts.high_day, 'low_day': ts.low_day, 'last_high': ts.last_high, 
                        'last_low': ts.last_low, 'pattern_hint': ts.pattern_hint,
                        'klines': list(ts.klines),
                        'is_untradable': ts.is_untradable,
                        'is_counter_trend': ts.is_counter_trend,
                        'ral': ts.ral
                    }

                # 恢复价格锚点与分值锚点
                stock_price_anchors = data.get('stock_price_anchors', {})
                for code, p_anchor in stock_price_anchors.items():
                    if code in self._tick_series:
                        self._tick_series[code].price_anchor = p_anchor
                
                stock_score_anchors = data.get('stock_score_anchors', {})
                for code, s_anchor in stock_score_anchors.items():
                    if code in self._tick_series:
                        self._tick_series[code].score_anchor = s_anchor

                # 3. 恢复板块与重点表
                raw_sectors = data.get('sector_data', {})
                # [DEFENSIVE] 修复缺失字段逻辑
                for name, info in raw_sectors.items():
                    if not isinstance(info, dict): continue
                    if 'sector' not in info: info['sector'] = name
                    if 'followers' not in info: info['followers'] = [] # [FIX] 防止 UI KeyError
                    
                    l_code = info.get('leader')
                    if l_code and l_code in self._global_snap_cache:
                        l_snap = self._global_snap_cache[l_code]
                        if 'leader_name' not in info: info['leader_name'] = l_snap.get('name', '未知')
                        if 'leader_pct' not in info: info['leader_pct'] = l_snap.get('pct', 0.0)
                        if 'leader_price' not in info: info['leader_price'] = l_snap.get('price', 0.0)
                        if 'leader_klines' not in info: info['leader_klines'] = l_snap.get('klines', [])
                        if 'pattern_hint' not in info: info['pattern_hint'] = l_snap.get('pattern_hint', '')

                self.active_sectors = raw_sectors
                self.daily_watchlist = data.get('watchlist', {})
                
                # 额外修复：确保 watchlist 中的个股名称也被恢复
                for code, w in self.daily_watchlist.items():
                    if not w.get('name') and code in meta_data:
                        w['name'] = meta_data[code].get('name', code)
                    if not w.get('sector') and code in meta_data:
                        w['sector'] = meta_data[code].get('category', '')
                
                self.sector_anchors = data.get('sector_anchors', {})
                self.baseline_time = data.get('baseline_time', time.time())
                
                # 成功加载后进入历史模式
                self.in_history_mode = True

            logger.info(f"🎬 [Detector] 历史快照已加载: {filepath} ({len(self.active_sectors)} 板块)")
            return True
        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}")
            return False

    def reconstruct_followers(self, sector_name: str):
        """
        [NEW] 手工从元数据缓存中重建指定板块的跟随股 (针对旧快照)
        扫描 _global_snap_cache 中所有属于该板块的个股。
        """
        with self._lock:
            if sector_name not in self.active_sectors:
                logger.warning(f"⚠️ [Detector] Sector {sector_name} not found in active_sectors")
                return

            info = self.active_sectors[sector_name]
            leader_code = info.get('leader', '')
            
            # 搜集候选人
            candidates = []
            for code, snap in self._global_snap_cache.items():
                if code == leader_code: continue
                
                # 匹配板块
                cats = [c.strip() for c in re.split(r'[;；,，/\- ]', str(snap.get('category', ''))) if c.strip()]
                if sector_name in cats:
                    candidates.append({
                        'code': code,
                        'name': snap.get('name', code),
                        'pct': snap.get('pct', 0.0),
                        'score': snap.get('score', 0.0),
                        'score_diff': snap.get('score_diff', 0.0),
                        'pct_diff': snap.get('pct_diff', 0.0),
                        'price': snap.get('price', 0.0),
                        'first_ts': snap.get('first_breakout_ts', 0.0)
                    })
            
            # 按评分排序取前 15 名
            candidates.sort(key=lambda x: x['score'], reverse=True)
            info['followers'] = candidates[:15]
            
            logger.info(f"✅ [Detector] Sector {sector_name} reconstructed: {len(info['followers'])} followers found.")

    # =========================================================
    # 内部：订阅回调
    # =========================================================

    def _on_tick(self, code: str, kline: dict):
        """
        DataPublisher 每当有新分钟 K 线时触发（后台线程）。
        不在此处更新 UI，只更新内部状态和评分。
        """
        with self._lock:
            ts_obj = self._tick_series.get(code)
            if ts_obj is None:
                return
            ts_obj.push_kline(kline)

        # 评分（可能在后台线程，不操作 Qt/Tk UI）
        self._evaluate_code(code)

    # =========================================================
    # 内部：个股评分
    # =========================================================

    def _evaluate_code(self, code: str):
        """对单只 code 计算异动评分，写入 ts_obj.score"""
        with self._lock:
            ts_obj = self._tick_series.get(code)
            if ts_obj is None:
                return
            klines = list(ts_obj.klines)  # 本地拷贝，避免锁持有过长
            last_close = ts_obj.last_close
            ma20 = ts_obj.ma20
            ma60 = ts_obj.ma60

        if not klines or last_close <= 0:
            return

        score = 0.0
        latest = klines[-1]
        # [FIX] 使用实时价格评估，确保 Tick 级别响应
        cur_close = ts_obj.current_price
        cur_pct = ts_obj.current_pct
        
        cur_vol = float(latest.get('volume', 0.0))
        cur_open_bar = float(latest.get('open', cur_close))  # 当根k棒开盘
        day_open = float(ts_obj.open_price) or float(klines[0].get('open', cur_close))
        
        # 0. 周期因子 (Cycle Factor): 处于 MA20 之上且 MA20 向上，属于强周期
        cycle_score = 0.0
        
        # [NEW] 种子股加分 (StockSelector 预选项)
        seed_info = self.stock_selector_seeds.get(code)
        if seed_info:
            cycle_score += 3.0  # 选股器加分，但不过分膨胀
            # 将选股理由同步到形态暗示的前端
            if seed_info.get('reason'):
                with self._lock:
                    if code in self._tick_series:
                        self._tick_series[code].pattern_hint = f"[{seed_info['reason'].split('|')[0]}]"

        if ma20 > 0 and cur_close > ma20:
            cycle_score += 1.0  # 基础牛熊分
            if ma60 > 0 and cur_close > ma60:
                cycle_score += 1.0
        
        # [Moved Up] 状态标志初始化
        is_counter = False
        is_untradable = False
        is_accumulating = False # [NEW] 蓄势标志
        is_reversal = False     # [NEW] 反转标志
        
        # 0.1 历史强度因子 (Integrated from DailyEmotionBaseline)
        hist_strength = 0.0
        is_gap_leader = False  # 连续跳空强势龙头标记
        if self.realtime_service and hasattr(self.realtime_service, 'emotion_baseline'):
            baseline = self.realtime_service.emotion_baseline.get_baseline(code)
            hist_strength = max(0, (baseline - 50) / 10.0)
            
            detail = self.realtime_service.emotion_baseline.get_baseline_detail(code)
            pattern_bonus = 0.0
            if "V反" in detail: pattern_bonus += 3.0
            elif "回归" in detail or "突破" in detail: pattern_bonus += 2.0
            
            # [New] 连续跳空强势龙头识别
            # 条件: pattern_hint 含"X阳"且 X>=3 + 今日再次高开 >=2%
            # 这类股是"极少数连阳沿upper上轨启动"的超强龙头，不适用次日退出规则
            _m = re.search(r'(\d+)阳', detail)
            _consecutive_days = int(_m.group(1)) if _m else 0
            _today_gap = (day_open - last_close) / last_close * 100.0 if last_close > 0 else 0.0
            if _consecutive_days >= 3 and _today_gap >= 2.0:
                is_gap_leader = True
                pattern_bonus += 4.0  # 超强龙头额外加分
                detail = f"⭐跳空强势{_consecutive_days}连阳▲{_today_gap:.1f}%"
            
            cycle_score += (hist_strength + pattern_bonus)
            
            with self._lock:
                if code in self._tick_series:
                    self._tick_series[code].pattern_hint = detail
            
            # [Added] 逆势带头逻辑
            if cur_pct > 3.0 and hasattr(self, 'last_market_avg') and self.last_market_avg < -0.5:
                is_counter = True
            
        # [Moved Out] 不可交易检查 (一字板/无量拉升) - 不依赖 realtime_service
        if cur_pct > 8.0:
            if ts_obj.high_day == ts_obj.low_day and ts_obj.high_day > 0:
                is_untradable = True
        
        # [New] 今日实时价格行为分析 - 区分V反参与日 vs V反后次冲日
        intraday_signal = ""
        open_gap_pct = (day_open - last_close) / last_close * 100.0 if last_close > 0 else 0.0
        intraday_fall_pct = (day_open - cur_close) / day_open * 100.0 if day_open > 0 else 0.0
        
        # 1. 核心风险/减仓信号
        if open_gap_pct >= 8.5 and intraday_fall_pct >= 2.0:
            is_untradable = True
            intraday_signal = f"今日主杀"
        
        # 2. 动量信号 (Surge/High)
        if not intraday_signal:
            # 2.1 放量拉升检测 (仅比较最近两根K线，避免全量扫描)
            if len(klines) >= 2:
                prev = klines[-2]
                if cur_vol > float(prev.get('volume', 0)) * 2.0 and cur_close > float(prev.get('close', 0)):
                    intraday_signal = "放量外激" # [Modified label to avoid confusion]
            
            # 2.2 日内新高
            if ts_obj.high_day > 0 and cur_close >= ts_obj.high_day * 0.998:
                if intraday_signal: intraday_signal += "+新高"
                else: intraday_signal = "日内新高"

        # 3. 支撑/止损信号
        ma_break_signal = ""
        vwap = ts_obj.vwap
        vwap_dist = (cur_close - vwap) / vwap * 100.0 if vwap > 0 else 0.0
        
        if vwap_dist < -0.6 and cur_pct < 0:
            ma_break_signal = "破均价线"
        elif abs(vwap_dist) < 0.2:
            ma_break_signal = "均线支撑"

        # 4. 保底形态描述 (确保不为空)
        base_pattern = ""
        if ma20 > 0 and ma60 > 0:
            if cur_close > ma20 > ma60: base_pattern = "多头排列"
            elif cur_close < ma20 < ma60: base_pattern = "空头下杀"
            elif ma20 > ma60 and cur_close < ma20: base_pattern = "多头回踩"
            elif ma20 < ma60 and cur_close > ma20: base_pattern = "低位反抽"

        # [NEW] 蓄势 (Accumulating) & 反转 (Reversal) 逻辑
        # 1. 蓄势：低波动 + 均线附近 + 异动缩量后初放
        # 使用预处理的 lastdu4/lastdu (Range Volatility) 替代 dist_h_l
        last_du4 = getattr(ts_obj, 'lastdu4', 5.0) 
        ral_val = getattr(ts_obj, 'ral', 0)
        
        # 蓄势评分加成
        if 0 < (cur_close - ma20) / ma20 < 0.015 and last_du4 < 2.5:
            is_accumulating = True
            bonus = 5.0
            if ral_val > 15: bonus += 3.0 # 长期守住 MA20 的强势蓄势
            cycle_score += bonus
            base_pattern = f"蓄势({ral_val})|{base_pattern}" if base_pattern else f"蓄势({ral_val})"
        
        # 2. 反转与强度加成
        top0_val = 1 if getattr(ts_obj, 'top0', 0) > 0 else 0
        top15_val = 1 if getattr(ts_obj, 'top15', 0) > 0 else 0
        if top0_val: cycle_score += 3.0 # 涨停强势因子
        if top15_val: cycle_score += 2.0 # 突破强势因子
        
        # 2. 反转：种子股昨日强今日开盘弱现转强，或 MA60 处企稳反弹
        if seed_info and open_gap_pct < 0 and cur_pct > 0:
            is_reversal = True
            cycle_score += 4.0
            base_pattern = f"反转|{base_pattern}" if base_pattern else "预选反转"
        elif ma60 > 0 and abs((cur_close - ma60)/ma60) < 0.01 and cur_pct > 1.0:
            is_reversal = True
            cycle_score += 4.0
            base_pattern = f"反转支撑|{base_pattern}" if base_pattern else "MA60反转"
            
        # [NEW] 低开高走 (Low Open, High Surge) Logic
        if day_open > 0 and (day_open - last_close) / last_close < -0.01 and cur_pct > 0.5:
             is_reversal = True
             cycle_score += 3.0
             base_pattern = f"低开高走|{base_pattern}" if base_pattern else "低开高走"

        # [NEW] "新高"与"上轨" (New High & Upper Band)
        is_new_high = False
        is_upper_band = False
        if ts_obj.last_high > 0 and cur_close > ts_obj.last_high:
            is_new_high = True
            cycle_score += 5.0 # 跨入新高区间，资金关注度极高
            
        # 简单模拟 Upper 上轨：价格始终在 MA20 之上 2% 且 MA20 向上
        if ma20 > 0 and (cur_close - ma20) / ma20 > 0.02:
            # 检查最近 3 根 K 线是否都在 MA20 之上
            if len(klines) >= 3 and all(float(k['close']) > ma20 for k in list(klines)[-3:]):
                is_upper_band = True
                cycle_score += 3.0
                base_pattern = f"沿上轨🚀|{base_pattern}" if base_pattern else "沿上轨🚀"
        
        if is_new_high:
            base_pattern = f"★新高|{base_pattern}" if base_pattern else "★新高"

        # 5. 组装最终 pattern_hint
        # 结构: [历史/基础形态] | [今日实时信号]
        detail_hint = ""
        with self._lock:
            ts_ref = self._tick_series.get(code)
            if ts_ref:
                # 获取 baseline 带来的历史形态 (V反、突破等)
                detail_hint = ts_ref.pattern_hint.split('|')[0].strip() if ts_ref.pattern_hint else ""
        
        final_hint = detail_hint or base_pattern
        current_signals = " | ".join(filter(None, [intraday_signal, ma_break_signal]))
        
        if current_signals:
            final_hint = f"{final_hint} | {current_signals}" if final_hint else current_signals
        
        with self._lock:
            if code in self._tick_series:
                self._tick_series[code].pattern_hint = final_hint
        
        # 1. 竞价/开盘高开强度
        high_open_pct = (day_open - last_close) / last_close * 100 if last_close > 0 else 0.0
        bidding_score = 0.0
        if high_open_pct > 2.0:
            bidding_score += 2.0
            if high_open_pct > 5.0: bidding_score += 1.5
        
        # 逆势/强势：今日开盘即站在昨日最高价之上
        if day_open > ts_obj.last_high and ts_obj.last_high > 0:
            bidding_score += 2.0

        # --- 2. 涨幅过滤 ---
        passed_filter = True
        if self.strategies['pct_change']['enabled']:
            p_min = self.strategies['pct_change']['min']
            p_max = self.strategies['pct_change']['max']
            # [Fix] 如果涨幅不足 p_min，评分清零
            # 允许 蓄势/反转/种子股/高分周期股 绕过此限制，以便在萌芽期识别
            if cur_pct < p_min and not (is_accumulating or is_reversal or seed_info or cycle_score >= 4.0):
                passed_filter = False
                score = 0.0
            else:
                score += min(cur_pct / p_max * 1.5, 1.5)  # 归一化分值

        if passed_filter:
            # --- 3. 连续上涨 K 棒 ---
            if self.strategies['consecutive_up']['enabled'] and len(klines) >= 2:
                n_bars = self.strategies['consecutive_up']['bars']
                if len(klines) >= n_bars:
                    recents = list(klines)[-n_bars:] # deque to list is fine for small N
                    is_consecutive = all(recents[i]['close'] > recents[i-1]['close'] for i in range(1, len(recents)))
                    if is_consecutive: score += 2.0
    
            # --- 4. 放量检查 (基于 TickSeries 维护的 vwap 和历史统计) ---
            if self.strategies['surge_vol']['enabled'] and len(klines) >= 2:
                cur_v = float(klines[-1].get('volume', 0.0))
                prev_v = float(klines[-2].get('volume', 0.0))
                if prev_v > 0 and cur_v / prev_v >= self.strategies['surge_vol']['min_ratio']:
                    score += 1.5
    
            # --- 5. 每日新高附近 ---
            if self.strategies['new_high']['enabled']:
                if ts_obj.high_day > 0 and cur_close >= ts_obj.high_day * 0.998:
                    score += 1.5
    
            # --- 6. 振幅过滤 (使用 TickSeries 的 incremental high_day/low_day) ---
            if self.strategies['amplitude']['enabled'] and last_close > 0:
                amplitude = (ts_obj.high_day - ts_obj.low_day) / last_close * 100
                if not (self.strategies['amplitude']['min'] <= amplitude <= self.strategies['amplitude']['max']):
                    score = 0.0

        # --- 7. 持续动量累计逻辑 (Momentum Persistence) ---
        # [NEW] 强势状态维持加分：均线上+0.05 (由0.2下调), 维持高位+0.1
        m_plus = 0.0
        if vwap > 0 and cur_close >= vwap:
            m_plus += 0.05
        if ts_obj.high_day > 0 and cur_close >= ts_obj.high_day * 0.998:
            m_plus += 0.05 # 维持高位即便不破新高也持续低速加分
        
        # [NEW] 回落重罚 (Retreat Penalty) & 均线惩罚
        if ts_obj.high_day > 0 and cur_close < ts_obj.high_day * 0.98:
            # 股价从高点回落超过 2%，视为走弱，扣除 0.5 分/批次
            ts_obj.momentum_score = max(0.0, ts_obj.momentum_score - 0.5)
        elif vwap > 0 and cur_close < vwap:
            # 破均线的一瞬间重罚并快速衰减 (冷却)
            ts_obj.momentum_score = max(0.0, ts_obj.momentum_score - 1.0)
        elif m_plus > 0:
            # 仅在维持强势且未回落时才加分
            ts_obj.momentum_score = min(20.0, ts_obj.momentum_score + m_plus)
        else:
            # 衰减逻辑：如果没有持续强势表现，动量分缓慢回落
            ts_obj.momentum_score = max(0.0, ts_obj.momentum_score - 0.1)

        # --- 8. 最终评分与活性修正 ---
        # 最终分 = 瞬时分(cycle+bidding+score) + 持续动量分
        final_score = cycle_score + bidding_score + score + ts_obj.momentum_score
        
        # [NEW] 高开低走 (Gap Trap) 惩罚
        # 如果高开超过 3.5% 但当前跌破均线且涨幅回撤超过高开幅度的一半
        if open_gap_pct > 3.5 and cur_close < vwap and cur_pct < open_gap_pct * 0.6:
            final_score *= 0.5 # 评分直接减半
            ts_obj.momentum_score *= 0.5
        
        # [NEW] 活性修正：如果最近 3 分钟价格没有变动且未涨停，分数大幅衰减 (针对僵尸股)
        if len(klines) >= 3:
            last_3 = [k['close'] for k in list(klines)[-3:]]
            if len(set(last_3)) == 1 and cur_pct < get_limit_up_threshold(code):
                final_score *= 0.3
                ts_obj.momentum_score *= 0.8 # 动量一同衰减

        # 尝试从数据中获取模拟时间
        data_ts = 0.0
        # 1. 优先从当前最新 row 提取时间
        ts_val = latest.get('ticktime', latest.get('timestamp', latest.get('time')))
        if ts_val:
            try:
                if isinstance(ts_val, (str, pd.Timestamp)):
                    dt = pd.to_datetime(ts_val)
                    data_ts = dt.timestamp()
                    # 防止跨天解析偏差
                    if data_ts > time.time() + 60:
                        data_ts = (dt - pd.Timedelta(days=1)).timestamp()
                else:
                    data_ts = float(ts_val)
            except:
                data_ts = self.last_data_ts if self.last_data_ts > 0 else time.time()
        # 2. 兜底从 K 线提取
        elif klines:
            data_ts = klines[-1].get('timestamp', self.last_data_ts if self.last_data_ts > 0 else time.time())
        else:
            data_ts = self.last_data_ts if self.last_data_ts > 0 else time.time()

        # [NEW] 记录个股历史得分并计算增量涨跌
        now = time.time()
        
        # 初始基准值挂载
        if ts_obj.score_anchor <= 0.0 and final_score > 0:
            ts_obj.score_anchor = final_score
            
        score_diff = final_score - ts_obj.score_anchor
        
        # [NEW] 个股切片涨幅计算与重置逻辑
        # [FIX] 跟随板块：初次发现异动时建立锚点。后续完全由 _aggregate_sectors 的周期计时器
        # 或手动请求刷新来统一重置锚点，保证在一个周期(默认30分钟)内涨跌幅度持续累计。
        
        # 1. 基准建立：如果 anchor 为 0，立即使用当前价建立
        if ts_obj.price_anchor <= 0 and cur_close > 0:
            ts_obj.price_anchor = cur_close
            
        # 2. 计算增量涨幅 (百分点变动)
        # 使用 last_close 作为核心基准，这样 pct_diff 指代的是“自基准时间后的累计涨幅增量”
        # 例如：基准时刻涨幅2.0%，当前2.5%，则 pct_diff = +0.50%
        # [FIX] 变动基准改为 price_anchor (切片价格)
        pct_diff = (cur_close - ts_obj.price_anchor) / ts_obj.last_close * 100.0 if ts_obj.last_close > 0 else 0.0
        ts_obj.pct_diff = pct_diff
        
        # [NEW] 计算绝对涨跌额 (自切片锚点以来的位移)
        # [FIX] 涨跌额也改为相对于 price_anchor
        ts_obj.price_diff = cur_close - ts_obj.price_anchor if ts_obj.price_anchor > 0 else 0.0


        with self._lock:
            # [FIX] 只要达到涨停阈值，或者分数达到门槛，且是首次异动，就记录时间
            # 这样能更准确捕捉涨停瞬间，哪怕涨停时由于某些原因评分还没跟上 (例如量还没放出来)
            limit_up_price = last_close * (1.0 + get_limit_up_threshold(code) / 100.0)
            is_at_limit = cur_close >= limit_up_price - 0.005 # 容差 1 分钱
            
            if (final_score >= 5.0 or is_at_limit) and ts_obj.first_breakout_ts == 0:
                ts_obj.first_breakout_ts = data_ts
            
            # [逻辑修正]：如果分数回落到极低水平（例如 < 2.0）且不处于涨停状态，重置异动时间
            if final_score < 2.0 and not is_at_limit:
                ts_obj.first_breakout_ts = 0

            if code in self._tick_series:
                ts_obj = self._tick_series[code]
                ts_obj.score = final_score
                ts_obj.score_diff = score_diff
                # ts_obj.pct_diff 已在前面赋值
                ts_obj.is_untradable = is_untradable
                ts_obj.is_counter_trend = is_counter
                ts_obj.is_gap_leader = is_gap_leader  # 连续跳空强势龙头标记
                ts_obj.is_accumulating = is_accumulating # [NEW]
                ts_obj.is_reversal = is_reversal         # [NEW]
                ts_obj.is_upper_band = is_upper_band     # [NEW]
                ts_obj.is_new_high = is_new_high         # [NEW]
            
            # [FIX] 无论如何确保 last_data_ts 能够推进
            if data_ts > self.last_data_ts:
                self.last_data_ts = data_ts
            elif data_ts == 0:
                self.last_data_ts = time.time()

    # =========================================================
    # 内部：板块聚合
    # =========================================================

    def _aggregate_sectors(self, active_codes=None):
        """
        将高分个股聚合到板块，找龙头和跟随股。
        active_codes: 如果提供，则只更新受这些个股影响的板块。
        """
        import re
        
        with self._lock:
            if active_codes is not None:
                codes_to_process = active_codes
            else:
                codes_to_process = list(self._tick_series.keys())

            # 1. 更新 snap 缓存
            for code in codes_to_process:
                ts = self._tick_series.get(code)
                if ts:
                    # 价格行为数据
                    data = {
                        'score': ts.score, 'pct': ts.current_pct, 'price': ts.current_price,
                        'name': ts.name, 'category': ts.category, 'last_close': ts.last_close,
                        'high_day': ts.high_day, 'low_day': ts.low_day, 'last_high': ts.last_high, 
                        'last_low': ts.last_low, 'first_breakout_ts': ts.first_breakout_ts, 
                        'pattern_hint': getattr(ts, 'pattern_hint', ""),
                        'klines': list(ts.klines) if ts.klines else (self.realtime_service.get_minute_klines(code, n=30) if self.realtime_service else []), # [Phase 4] 必须包含 K 线用于 UI 渲染
                        'is_untradable': getattr(ts, 'is_untradable', False),
                        'is_counter_trend': getattr(ts, 'is_counter_trend', False),
                        'is_accumulating': getattr(ts, 'is_accumulating', False),
                        'is_reversal': getattr(ts, 'is_reversal', False),
                        'ral': getattr(ts, 'ral', 0),
                        'top0': getattr(ts, 'top0', 0),
                        'top15': getattr(ts, 'top15', 0),
                        'score_diff': getattr(ts, 'score_diff', 0.0),
                        'pct_diff': getattr(ts, 'pct_diff', 0.0),
                        'price_diff': getattr(ts, 'price_diff', 0.0),
                        'dff': getattr(ts, 'dff', 0.0)
                    }
                    self._global_snap_cache[code] = data
                    
                    # 2. 同步更新增量分组 (持久化)
                    cats = ts.get_splitted_cats()
                    if ts.score >= self.score_threshold:
                        for cat in cats:
                            if cat not in SECTOR_BLACKLIST and len(cat) <= 8:
                                self._sector_active_stocks_persistent[cat][code] = {'code': code, **data}
                    else:
                        for cat in cats:
                            if code in self._sector_active_stocks_persistent.get(cat, {}):
                                del self._sector_active_stocks_persistent[cat][code]
            
            snap = self._global_snap_cache
            
            # 3. 确定需要重算的板块
            target_sectors = set()
            if active_codes is not None:
                for code in active_codes:
                    ts = self._tick_series.get(code)
                    if ts:
                        for p in ts.get_splitted_cats():
                            if p not in SECTOR_BLACKLIST: target_sectors.add(p)
            else:
                target_sectors = None # 全量更新

        market_avg_pct = 0.0
        if snap:
            market_avg_pct = sum(x['pct'] for x in snap.values()) / len(snap)
            self.last_market_avg = market_avg_pct

        now_dt = datetime.datetime.now()
        today = now_dt.date()
        now_t = now_dt.hour * 100 + now_dt.minute
    # [REMOVED] Daily reset prevents multi-day analysis. 
    # Use cross-day logic if specific data cleaning is needed, otherwise rely on memory management.
    # if self._concept_data_date != today:
    #     self._concept_data_date = today
    #     self._concept_first_phase_done = False
    #     self._concept_second_phase_done = False
    #     self.daily_watchlist.clear()
    #     if hasattr(self, "_sector_active_stocks_persistent"):
    #         self._sector_active_stocks_persistent.clear()
    #     logger.info(f"[Detector] {today} Day Transition - Multi-day support active")

        now_ts = self.last_data_ts if self.last_data_ts > 0 else time.time()

        # --- 更新全量 Watchlist (仅针对有变动的个股) ---
        codes_for_watchlist = active_codes if active_codes is not None else snap.keys()
        for code in codes_for_watchlist:
            d = snap.get(code)
            if d and d['pct'] >= get_limit_up_threshold(code) and not d['is_untradable']:
                if code in self.daily_watchlist:
                    self.daily_watchlist[code]['pct'] = round(d['pct'], 2)
                    if d['pattern_hint']: self.daily_watchlist[code]['pattern_hint'] = d['pattern_hint']
                else:
                    trigger_ts = d['first_breakout_ts'] if d['first_breakout_ts'] > 0 else now_ts
                    self.daily_watchlist[code] = {
                        'code': code, 'name': d['name'], 'sector': d['category'], 'pct': round(d['pct'], 2),
                        'time_str': datetime.datetime.fromtimestamp(trigger_ts).strftime('%m%d-%H:%M'),
                        'reason': '涨停', 'pattern_hint': d['pattern_hint']
                    }

        new_active = {} if target_sectors is None else self.active_sectors.copy()
        
        # 4. [NEW] 全局对照基准重置逻辑 (移动到循环外，每周期仅检查一次)
        now = time.time()
        if now - self.baseline_time >= self.comparison_interval:
            self.reset_observation_anchors()
            
            # [Added] 强制全量重刷板块，防止锚点丢失导致的数据显示异常

            
            # [Added] 强制全量重刷板块，防止锚点丢失导致的数据显示异常
            target_sectors = None
            new_active = {}
        
        # 将 persistent dict 转换为 list 给计算逻辑使用
        sectors_to_update = target_sectors if target_sectors is not None else self._sector_active_stocks_persistent.keys()
        
        for sector in sectors_to_update:
            stocks_dict = self._sector_active_stocks_persistent.get(sector, {})
            if not stocks_dict:
                if sector in new_active: del new_active[sector]
                continue
            
            # [FIX] 动态过滤：即使在持久化缓存中，也要确保个股分满足当前 UI 设定的门槛
            # 这样用户在 UI 调整“个股分≥”时，列表能立即变多/变少
            stocks = [s for s in stocks_dict.values() if s.get('score', 0) >= self.score_threshold]
            
            if not stocks:
                if sector in new_active: del new_active[sector]
                continue
            
            for s in stocks:
                base_score = s['score']
                drawdown_pct = max(0, (s['high_day'] - s['price']) / s['last_close'] * 100) if s['last_close'] > 0 else 0
                penalty = drawdown_pct * 4.0 
                time_bonus = 0.0
                if s['first_breakout_ts'] > 0:
                    market_open_dt = pd.Timestamp.fromtimestamp(s['first_breakout_ts']).replace(hour=9, minute=30, second=0)
                    time_diff_min = (market_open_dt.timestamp() - s['first_breakout_ts']) / 60.0
                    time_bonus = 10.0 + time_diff_min * (0.1 if time_diff_min >= 0 else 0.5)
                
                s['leader_score'] = base_score * 0.8 + s['pct'] * 1.2 - penalty + time_bonus
                if market_avg_pct < -0.5 and s['pct'] > 1.0: s['leader_score'] += 10.0 
                if s['is_untradable']: s['leader_score'] -= 50.0 

            stocks.sort(key=lambda x: x['leader_score'], reverse=True)
            candidate_leader = stocks[0]
            leader_code = candidate_leader['code']
            leader_pct = candidate_leader['pct']

            all_member_codes = self.sector_map.get(sector, set())
            active_member_count = 0
            total_pct = 0.0
            leader_sign = 1 if leader_pct > 0 else (-1 if leader_pct < 0 else 0)
            for c in all_member_codes:
                if c in snap:
                    mc_pct = snap[c]['pct']
                    mc_sign = 1 if mc_pct > 0 else (-1 if mc_pct < 0 else 0)
                    if mc_sign == leader_sign and mc_sign != 0:
                        active_member_count += 1
                        total_pct += mc_pct
            
            # 联动分析与强度综合评分
            follow_ratio = active_member_count / len(all_member_codes) if all_member_codes else 0
            avg_pct = total_pct / len(all_member_codes) if all_member_codes else 0
            
            # [REFINED] 噪点过滤：成员数过少（少于 4 只股）的概念通常是虚假的，剔除。
            if len(all_member_codes) < 4:
                if sector in new_active: del new_active[sector]
                continue
            
            # 提取龙头元数据供后续使用
            tags = []
            l_data = candidate_leader
            l_ts = self._tick_series.get(leader_code)
            if l_ts:
                day_open = l_ts.open_price or (list(l_ts.klines)[0].get('open') if l_ts.klines else 0)
                if l_ts.last_close > 0 and (day_open - l_ts.last_close) / l_ts.last_close > 0.03: tags.append("高开")
                if l_data.get('price', 0) > day_open > 0: tags.append("高走")
                
                # 记录竞价情绪
                now_t = int(time.strftime("%H%M"))
                if 920 <= now_t <= 925:
                    if leader_pct > 3.0: tags.append("竞价抢筹")
                    elif leader_pct < -3.0: tags.append("竞价恐慌")
                if 1300 <= now_t <= 1310: tags.append("午后异动")

            # 计算群体热度加成
            s_top0_sum = sum(1 for s in stocks if s.get('top0', 0) > 0)
            s_top15_sum = sum(1 for s in stocks if s.get('top15', 0) > 0)
            hotness_multiplier = min(2.0, 1.0 + (s_top0_sum * 0.1) + (s_top15_sum * 0.03))

            # [REFINED] 极严格过滤：模仿 TK 去弱留强逻辑
            # 以群体效应 (avg_pct * follow_ratio) 为核心依据。
            tk_correlation_score = avg_pct * follow_ratio * 4.0 
            
            # 基础门槛：即便个股分高，如果联动性极其平淡 (低于 15%) 且平均涨幅低，排除该板块。
            # 这是“369个活跃板块”缩减到“15-30个”的关键。
            if follow_ratio < 0.15 and avg_pct < 1.5:
                 if sector in new_active: del new_active[sector]
                 continue
            
            # 最终板分公式：(板块均值加权 + 联动比例加权 + 个股强势溢价) * 热度系数
            # 目标产出区间 0-10，对标 TK 强度分析
            board_score = (avg_pct * 0.8 + follow_ratio * 4.0 + (candidate_leader['score'] * 0.05) + tk_correlation_score) * hotness_multiplier
            
            # [NEW] 标记板块类型
            sector_type = "📈 跟随"
            if board_score > 6.0 and (leader_pct > 5.0 or s_top0_sum > 0) and follow_ratio > 0.4: sector_type = "🔥 强攻"
            elif any(s.get('is_accumulating') for s in stocks) or (sum(s.get('ral', 0) for s in stocks)/len(stocks) > 12):
                sector_type = "♨️ 蓄势"
            elif any(s.get('is_reversal') for s in stocks):
                sector_type = "🔄 反转"
            
            tags.insert(0, sector_type)
            
            # 联动板块分析 (精简版)
            linked_concepts = []
            leader_concepts = [c.strip() for c in re.split(r'[;；,，/ \\-]', l_data['category']) if c.strip() and len(c.strip()) <= 8]
            if leader_concepts:
                for concept in leader_concepts:
                    if concept == sector: continue
                    members = self.sector_map.get(concept)
                    if not members or len(members) < 3: continue
                    f_count = sum(1 for mc in members if mc in snap and (1 if snap[mc]['pct']>0 else -1) == leader_sign)
                    total_c_pct = sum(snap[mc]['pct'] for mc in members if mc in snap and (1 if snap[mc]['pct']>0 else -1) == leader_sign)
                    c_follow = f_count / len(members)
                    c_avg_pct = total_c_pct / len(members) if len(members) > 0 else 0
                    if c_follow > 0.4: linked_concepts.append({
                        'concept': concept, 
                        'follow_ratio': round(c_follow, 2),
                        'avg_pct': round(c_avg_pct, 2)
                    })

            # [NEW] 板块综合强度过滤
            if board_score < self.sector_score_threshold:
                 if sector in new_active: del new_active[sector]
                 continue
                 
            # [REM] 移除此处冗余的基准重置逻辑，已在循环外部(Line 1054) 统一处理。
            # 保持逻辑单一职责，避免在循环内部重复刷新全局状态。

            
            if sector not in self.sector_anchors:
                self.sector_anchors[sector] = board_score
                
            score_diff = board_score - self.sector_anchors[sector]
            
            # 3. 分阶段变动重置 (辅助参考)
            anchor = self.sector_anchors[sector]
            if abs(board_score - anchor) >= self.reset_threshold:
                if self.enable_log:
                    logger.info(f"♻️ [Detector] Sector anchor reset for {sector}: {anchor:.1f} -> {board_score:.1f}")
                self.sector_anchors[sector] = board_score
                anchor = board_score
            
            staged_diff = board_score - anchor

            new_active[sector] = {
                'sector': sector, 'score': round(board_score, 2), 'tags': " ".join(tags),
                'ts': time.time(), # [FIX] 添加时间戳，用于 GC
                'score_diff': round(score_diff, 2),        # 对比固定时长(30m)的变动
                'staged_diff': round(staged_diff, 2),      # 阶段性变动 (10分阈值重置)
                'follow_ratio': round(follow_ratio, 2), 'leader': leader_code,
                'leader_name': l_data['name'], 'leader_pct': round(l_data['pct'], 2),
                'leader_price': l_data.get('price', 0.0),
                'leader_klines': list(l_ts.klines)[-35:] if (l_ts and l_ts.klines) else (self.realtime_service.get_minute_klines(leader_code, n=35) if self.realtime_service else []),
                'leader_last_close': l_data.get('last_close', 0),
                'leader_high_day': l_data.get('high_day', 0),
                'leader_low_day': l_data.get('low_day', 0),
                'leader_last_high': l_data.get('last_high', 0),
                'leader_last_low': l_data.get('last_low', 0),
                'leader_first_ts': l_data['first_breakout_ts'],
                'leader_score_val': l_data.get('score', 0.0),
                'leader_score_diff': l_data.get('score_diff', 0.0),
                'leader_pct_diff': round(l_data.get('pct_diff', 0.0), 2),
                'leader_price_diff': round(l_data.get('price_diff', 0.0), 2),
                'leader_dff': round(l_data.get('dff', 0.0), 2),
                'pattern_hint': l_data['pattern_hint'],
                'is_untradable': l_data['is_untradable'],
                'followers': [
                    {
                        'code': s['code'], 
                        'name': s['name'], 
                        'pct': s['pct'], 
                        'score': s.get('score', 0.0), 
                        'score_diff': s.get('score_diff', 0.0), 
                        'pct_diff': s.get('pct_diff', 0.0), 
                        'price_diff': s.get('price_diff', 0.0), 
                        'dff': s.get('dff', 0.0), 
                        'price': s.get('price', 0.0), 
                        'first_ts': s['first_breakout_ts'],
                        'pattern_hint': s.get('pattern_hint', ''),  
                        'untradable': s.get('is_untradable', False),
                        # [NEW] 这里的关键：补充绘制分时图所需的 K 线和基准数据
                        'klines': s.get('klines', []),
                        'last_close': s.get('last_close', 0.0),
                        'high_day': s.get('high_day', 0.0),
                        'low_day': s.get('low_day', 0.0),
                        'last_high': s.get('last_high', 0.0),
                        'last_low': s.get('last_low', 0.0)
                    } for s in stocks[1:15]
                ],
                'linked_concepts': linked_concepts[:3]
            }

        with self._lock:
            self.active_sectors = new_active

    def _gc_old_sectors(self):
        """清理长时间不活跃的板块结果"""
        now = time.time()
        # [REFINED] 动态获取 sleep 时间，如果 CFG 没变，尝试从文件重新加载或使用合理默认值
        # 考虑到 cct.CFG 可能不会实时响应 global.ini 变化，这里我们强制获取最新
        try:
            limit = float(getattr(cct.CFG, 'duration_sleep_time', 5.0)) if cct else 5.0
        except:
            limit = 5.0
            
        # 允许竞价期间更快速刷新 (最低 1s)
        limit = max(1.0, limit)
        
        if getattr(self, '_force_update_requested', False) or (now - self._last_refresh_ts >= limit):
            with self._lock:
                 # [REFINED] 缩短过期时间，从 900s (15min) 缩短到 300s (5min)
                 # 保持热度表的实时性，防止早盘干扰持续整天。
                 stale = [s for s, d in self.active_sectors.items()
                          if now - d.get('ts', 0) > 300.0] 
                 for s in stale:
                     del self.active_sectors[s]
            self._last_refresh_ts = now
            self._force_update_requested = False


    # =========================================================
    # 内部：板块图
    # =========================================================

    def _rebuild_sector_map(self, df: pd.DataFrame):
        """从 df_all 重建 sector → set(code) 索引"""
        if 'category' not in df.columns:
            return
        new_map: Dict[str, Set[str]] = defaultdict(set)
        for row in df.itertuples(index=False):
            # [FIX] 使用显式属性 code 代替 Index
            code = str(getattr(row, 'code', '')).strip().zfill(6)
            if not code or code == '000000':
                continue
            cat = str(getattr(row, 'category', ''))
            if not cat or cat == 'nan':
                continue
            for p in re.split(r'[;；,，/ \\-]', cat):
                p = p.strip()
                if p:
                    new_map[p].add(code)
        
        # [REFINED] 激进清理改为温和差异判断：仅当新旧板块架构差异极大时重置
        if self.sector_map and len(new_map) > 0:
            diff_ratio = len(set(new_map.keys()) ^ set(self.sector_map.keys())) / max(len(new_map), 1)
            # 如果板块名单变动超过 80%，可能切换了市场或数据源，清理缓存
            if diff_ratio > 0.8:
                logger.info(f"♻️ [Detector] Market context shifted (diff={diff_ratio:.1f}), resetting persistent cache")
                self._sector_active_stocks_persistent.clear()
            
        self.sector_map = new_map

    # =========================================================
    # 时间窗口判断（只在竞价/尾盘生效）
    # =========================================================

    @staticmethod
    def is_active_session() -> bool:
        """全天查看模式：主要交易时间内都就行（略去时间窗口限制）。
        实盘如需限制仅在特定时段，可在 UI 层包装调用。"""
        now = datetime.datetime.now()
        hm = now.hour * 100 + now.minute
        # 盘中全期：09:15 - 15:00
        return 915 <= hm <= 1500
