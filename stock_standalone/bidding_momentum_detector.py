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
import json
import os
import gzip
import shutil
import zlib
from typing import Dict, List, Set, Any, Optional, Callable, TYPE_CHECKING
from collections import defaultdict, deque
from datetime import datetime as _datetime
import pandas as pd
import numpy as np
from JohnsonUtil import commonTips as cct
from linkage_service import get_link_manager

# ---- 模块级预编译常量 (避免每次调用重新编译) ----
# 板块分类字符串切割 regex，覆盖所有常见分隔符
_RE_CAT_SPLIT = re.compile(r'[;；,，/\- ]')
# 非数字字符清理，用于代码规范化
_RE_NON_DIGIT = re.compile(r'[^\d]')
# 连续阳线天数提取
_RE_YANG_DAYS = re.compile(r'(\d+)阳')
# numpy handler 类型缓存 (避免 isinstance 链)
_NP_INT_TYPES = (np.integer,)
_NP_FLOAT_TYPES = (np.floating,)
_NP_ARRAY_TYPE = np.ndarray

def compress_klines(klines):
    """
    [精简结构] 将 K 线 deque/list 压缩为【列式存储】格式 (Columnar Encoding):
    { 'b': base_ts, 'o': [offsets], 'c': [closes], 'v': [volumes] }
    优势: 提升压缩率 15-30%，且便于后续二进制扩展。
    """
    if not klines:
        return {}
    
    # 提取最近 30 根
    k_list = list(klines)[-30:]
    base_ts = 0
    offsets, closes, volumes = [], [], []
    
    for k in k_list:
        d = k.as_dict() if hasattr(k, 'as_dict') else k
        if not d: continue
        
        dt = d.get('datetime', d.get('time'))
        if not dt: continue
        
        try:
            if isinstance(dt, str):
                # 统一使用 fromisoformat，兼容空格分隔的 "YYYY-MM-DD HH:MM:SS"
                ts = int(_datetime.fromisoformat(dt.replace(' ', 'T')).timestamp())
            elif hasattr(dt, 'timestamp'):
                ts = int(dt.timestamp())
            else:
                ts = int(dt)
            
            if base_ts == 0:
                base_ts = ts
            
            c = d.get('close')
            v = d.get('volume')
            
            offsets.append((ts - base_ts) // 60)
            closes.append(round(float(c), 2) if c is not None else 0.0)
            volumes.append(int(float(v)) if v is not None else 0)
        except:
            continue

    if not offsets:
        return {}

    return {
        'b': base_ts,
        'o': offsets,
        'c': closes,
        'v': volumes
    }

def decompress_klines(compressed):
    """
    解压紧凑格式 K 线数据回 dict 列表，兼容 [list-of-dict], [list-of-list] 及新的 [columnar] 格式。
    """
    if not compressed:
        return []
    
    # 1. 兼容最原始格式 (list of dicts)
    if isinstance(compressed, list):
        if not compressed: return []
        if isinstance(compressed[0], dict):
            return compressed
        return []

    if not isinstance(compressed, dict) or 'b' not in compressed:
        return []
        
    base_ts = compressed['b']
    out = []

    # 2. 兼容 0408_v1 结构 {b, d:[[..]]}
    if 'd' in compressed:
        compact_data = compressed['d']
        for item in compact_data:
            if not isinstance(item, (list, tuple)) or len(item) < 3: continue
            ts = base_ts + item[0] * 60
            dt_str = _datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            out.append({'datetime': dt_str, 'time': ts, 'close': item[1], 'volume': item[2]})
        return out

    # 3. 新的 Columnar 格式 {b, o:[], c:[], v:[]}
    offsets = compressed.get('o', [])
    closes = compressed.get('c', [])
    volumes = compressed.get('v', [])
    
    for i in range(len(offsets)):
        ts = base_ts + offsets[i] * 60
        dt_str = _datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        out.append({
            'datetime': dt_str,
            'time': ts,
            'close': closes[i] if i < len(closes) else 0.0,
            'volume': volumes[i] if i < len(volumes) else 0
        })
    return out

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
                 'total_vol', 'vol_ratio', 'lvol', 'last6vol', 'market_role',
                 'score_anchor', 'score_diff', 'price_anchor', 'pct_diff', 'price_diff', 'dff', 'cycle_stage',
                 'racing_start_ts', 'last_stable_ts', 'racing_duration', 'signal_count', '_last_sig_min',
                 '_bar_active_reward', '_last_active_price', 'opening_bonus', 'total_amount',
                 '_cached_baseline', '_cached_baseline_detail', '_cached_yang_days', '_last_baseline_date')

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
        self.is_counter_trend: bool = False # 是否为逆势品种
        
        # [NEW] 赛马模式稳定性追踪
        self.racing_start_ts: float = 0.0   # 赛马开始时间戳
        self.last_stable_ts: float = 0.0    # 最近一次稳定在均线上的时间
        self.racing_duration: float = 0.0   # 累计稳定时长(分)

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
        self._total_vol: float = 0.0 # 内部循环计数
        self._total_amt: float = 0.0 # 内部循环计数
        self.total_vol: float = 0.0 # 当日成交量
        self.vol_ratio: float = 0.0 # 量比
        self.lvol: float = 0.0      # 地量参考
        self.last6vol: float = 0.0  # 6日均量
        self.market_role: str = "跟随" # [NEW] 角色标签: 排头兵/主帅/跟随
        self.score_anchor: float = 0.0
        self.score_diff: float = 0.0
        self.price_anchor: float = 0.0
        self.pct_diff: float = 0.0
        self.price_diff: float = 0.0
        self.dff: float = 0.0
        self.cycle_stage: int = 2
        self.signal_count: int = 0
        self._last_sig_min: int = 0
        self._bar_active_reward: int = 0 # [NEW] 活跃奖励锁
        self._last_active_price: float = 0.0 # [NEW] 最近一次活跃价格基准
        self.opening_bonus: float = 0.0      # [NEW] 缓存早盘溢价分
        self.total_amount: float = 0.0
        
        self._cached_baseline: float = 0.0
        self._cached_baseline_detail: str = ""
        self._cached_yang_days: int = 0
        self._last_baseline_date: str = ""

    def update_racing_status(self, cur_close: float, vwap: float, open_p: float, now_ts: float, low_p: float = 0.0, nlow: float = 0.0):
        """更新赛马模式稳定性状态 - 核心逻辑对齐 IntradayDecisionEngine"""
        if cur_close <= 0 or vwap <= 0 or open_p <= 0: return

        # 1. 结构准入：必须是开盘至今极其平稳，且当前站稳均价线与开盘价
        # [ADJUST] 允许 0.3% 的微小误差 (原 0.2%)，增加实盘容错
        is_above_support = (cur_close >= vwap * 0.997) and (cur_close >= open_p * 0.997)
        
        # [FIXED] 开盘最低价结构校验 
        # 如果当前低点(low_p)或之前最低记录(nlow)显著低于开盘价(超过 0.5%)，说明曾有深幅回撤，视为结构不稳定
        is_structural_stable = True
        if low_p > 0:
            # 修正此前逻辑反转：应该是 low < open * 0.995 为不稳定
            if low_p < open_p * 0.995 or nlow < open_p * 0.995:
                is_structural_stable = False

        if is_above_support and is_structural_stable:
            if self.racing_start_ts <= 0:
                self.racing_start_ts = now_ts
            self.last_stable_ts = now_ts
            self.racing_duration = (now_ts - self.racing_start_ts) / 60.0
        else:
            # [ADJUST] 破位判定：如果彻底跌破 (均价回撤 2% 或 跌破开盘价 1.5%)，才重置赛马状态
            if cur_close < vwap * 0.98 or cur_close < open_p * 0.985 or not is_structural_stable:
                self.racing_start_ts = 0.0
                self.racing_duration = 0.0

    def update_meta(self, row: Any):
        """
        从 df_all 行更新元数据。
        优化：输入可以是 dict, NamedTuple 或 pd.Series。避开昂贵的 pd.Series 构造。
        """
        # 手动适配 dict/Series 的 .get() 或 NamedTuple 的属性获取
        def _val(key, default=0.0):
            if isinstance(row, dict): return row.get(key, default)
            return getattr(row, key, default)

        v_pre = _val('lastp1d', _val('lastp', _val('pre_close', _val('llastp', _val('llastp1d', _val('llstp', 0.0))))))
        self.last_close = float(v_pre) if v_pre and v_pre > 0 else 0.0
        
        v_open = _val('open', 0.0)
        self.open_price = float(v_open) if v_open else 0.0

        v_lasth = _val('lasth1d', _val('lasth', self.last_close))
        self.last_high = float(v_lasth) if v_lasth else 0.0
        
        v_lastl = _val('lastl1d', _val('lastl', self.last_close))
        self.last_low = float(v_lastl) if v_lastl else 0.0
        
        # [FIX] 捕获实时价格
        v_now = _val('now', _val('trade', _val('price', _val('nclose', self.now_price))))
        self.now_price = float(v_now) if v_now else 0.0
        
        v_high = _val('high', 0.0)
        self.high_day = float(v_high) if v_high else 0.0
        
        v_list_low = _val('low', 0.0)
        self.low_day = float(v_list_low) if v_list_low else 0.0
        
        v_ma20 = _val('ma20d', 0.0)
        self.ma20 = float(v_ma20) if v_ma20 else 0.0
        
        v_ma60 = _val('ma60d', 0.0)
        self.ma60 = float(v_ma60) if v_ma60 else 0.0
        
        self.category = str(_val('category', ''))
        self.name = str(_val('name', self.code))
        self.lastdu = float(_val('lastdu', 0.0))
        self.lastdu4 = float(_val('lastdu4', 0.0))
        
        r_val = _val('ral', 0)
        self.ral = int(r_val) if r_val else 0
        
        v_dff = _val('dff', 0.0)
        self.dff = float(v_dff) if v_dff else 0.0
        
        # [NEW] 捕获实盘量能核心指标
        self.vol_ratio = float(_val('volume', _val('vol_ratio', 0.0)))
        self.total_vol = float(_val('vol', _val('volume_total', 0.0)))
        self.lvol = float(_val('lvol', 0.0))
        self.last6vol = float(_val('last6vol', 0.0))
        
        v_top0 = _val('top0', 0)
        self.top0 = int(v_top0) if v_top0 else 0
        
        v_top15 = _val('top15', 0)
        self.top15 = int(v_top15) if v_top15 else 0

        v_stage = _val('cycle_stage', _val('cycle_stage_vect', 2))
        self.cycle_stage = int(v_stage) if v_stage else 2

        self._splitted_cats = None # 重置缓存

    def get_splitted_cats(self) -> List[str]:
        if self._splitted_cats is not None:
            return self._splitted_cats
        parts = _RE_CAT_SPLIT.split(str(self.category))
        # [唯一性保护] 对单只个股的分类字符串执行去重，防止 "Sector1; Sector1" 导致映射冗余
        self._splitted_cats = sorted(list({p.strip() for p in parts if p.strip() and p.strip() != 'nan'}))
        return self._splitted_cats

    def push_kline(self, kline: dict):
        """追加一根分钟 K 线"""
        # [NEW] 重置分钟活跃奖励锁，允许每分钟重新获取额外活跃分
        self._bar_active_reward = 0

        # 如果队列满了，减去最老的统计
        if len(self.klines) == self.klines.maxlen:
            oldest = self.klines[0]
            v = float(oldest.get('volume', 0.0))
            c = float(oldest.get('close', 0.0))
            # [FIX] 减去时也要使用当时记录的金额逻辑，防止累计偏差
            a = float(oldest.get('amount', oldest.get('turnover', v * c)))
            self._total_vol -= v
            self._total_amt -= a

        self.klines.append(kline)
        # 增量维护统计
        vol = float(kline.get('volume', 0.0))
        close = float(kline.get('close', 0.0))
        # [PERF] 优先从 K 线获取预计算的金额，否则回退到 vol * close
        amt = float(kline.get('amount', kline.get('turnover', vol * close)))
        
        self._total_vol += vol
        self._total_amt += amt
        self.total_amount = self._total_amt # 同步更新到 slots 变量中
        
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

    def __init__(self, realtime_service: Optional["DataPublisher"] = None, simulation_mode: bool = False, lazy_load: bool = False, silent_mode: bool = False):
        # ---- 数据服务 ----
        self.realtime_service = realtime_service
        self.simulation_mode = simulation_mode
        self._is_ready = False if lazy_load else True
        self._loading_thread = None
        self.silent_mode = silent_mode # [NEW] 集成模式下抑制重复日志打印
        self.enable_background_linkage = False # [NEW] 是否允许后台自动联动 (默认关闭，仅在赛马面板开启时授权)

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
        self._lock = threading.RLock()

        # code → TickSeries
        self._tick_series: Dict[str, TickSeries] = {}

        # 已注册到 realtime_service 的 code set（防重复订阅）
        self._subscribed: Set[str] = set()

        # 板块图：sector → set(codes)
        self.sector_map: Dict[str, Set[str]] = defaultdict(set)
        
        # [NEW] 信号总线联动：接收来自底层 Tracker 的形态确认信号 (如 SBC-Breakout)
        # self._signal_bus = SignalBus()
        # self._signal_bus.subscribe("pattern_signal", self._on_signal_received)

        # 最终结果：sector → {leader, followers, score, ts, ...}
        self.active_sectors: Dict[str, Dict[str, Any]] = {}

        # [NEW] 数据更新版本号 (用于 UI 判定是否需要重绘)
        self.data_version = 0
        
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
        self.sector_score_threshold: float = 4.0
        self.last_data_ts = 0.0

        # key=code, val={name, sector, pct, time_str, reason, reason, pattern_hint, release_risk}
        self.daily_watchlist: Dict[str, Dict[str, Any]] = {}
        self.enable_log = True # 是否允许向控制台/文件打印重点监控日志
        self.last_processed_count = 0 # [NEW] 记录最近一轮实际处理的个股数量
        
        # ---- [NEW] 强度历史对比与变动追踪 ----
        self.comparison_interval: float = 60 * 60 # 默认 60 分钟对比窗口 (秒)
        self.baseline_time: float = time.time()  # 阈值的初始基准时间
        # sector -> anchor_score
        self.sector_anchors: Dict[str, float] = {}
        # [REMOVED] Jump reset threshold no longer needed.
        
        # [NEW] 个股切片涨幅重置阈值 (1.0%)
        self.price_reset_threshold: float = 1.0

        # ---- [NEW] 选股器联动与两阶段刷新 ----
        self.stock_selector_seeds: Dict[str, Dict[str, Any]] = {} # 昨曾强势/反转股代码
        self._today_anchor_930: float = 0.0 # [NEW] 缓存今日 09:30 锚点，减少重复计算
        self._concept_data_date: Optional[datetime.date] = None
        self._concept_first_phase_done = False
        self._concept_second_phase_done = False
        
        # [Tier 2] 增量缓存
        self._global_snap_cache: Dict[str, Dict[str, Any]] = {}
        self._sector_active_stocks_persistent: Dict[str, Dict[str, Any]] = defaultdict(dict)
        # [NEW] 市场整体数据缓存
        self.last_market_avg = 0.0

        # [NEW] 模式保护与参数
        self.last_data_ts = 0
        self.data_version = 0
        self.in_history_mode = False
        self._live_stash = {} # [NEW] 用于存放实盘数据的暂存空间
        self.use_dragon_race = False  # 龙头竞赛模式（停用后回归 0407 挖掘模式）
        self._last_data_date: str = "" # [NEW] 记录上次处理数据的日期 (YYYY-MM-DD)
        
        # ---- [SUPER] 龙头三日跟踪与性能辅助 ----
        self.dragon_3day_history: List[Dict[str, Any]] = [] # [{date, code, name, sector, base_price, base_vol_l6, base_score}]
        self._dragon_init_done = False
        self._last_dragon_update_v = -1  # [NEW] 记录上次执行龙三更新时的版本号
        
        self._code_index: Dict[str, str] = {} # code -> name
        self._name_index: Dict[str, str] = {} # name -> code
        
        # [NEW] [ROOT-FIX] 初始化联动代理
        self.link_manager = get_link_manager()

        if not lazy_load:
            self._load_stock_selector_data()
        else:
            logger.info("📡 [Detector] Lazy load enabled. Synchronous init skipped.")
        
        # [NEW] 信号总线联动：接收来自底层 Tracker 的形态确认信号 (如 SBC-Breakout)
        # self._signal_bus = SignalBus()
        # self._signal_bus.subscribe("pattern_signal", self._on_signal_received)

    # def _on_signal_received(self, msg: Any):
    #     """
    #     处理来自 SignalBus 的形态信号 (例如 SBC-Breakout)
    #     msg 预期格式: {'code': '601138', 'pattern': 'SBC-Breakout', 'desc': '...'}
    #     """
    #     if not isinstance(msg, dict): return
    #     code = msg.get('code')
    #     pattern = msg.get('pattern')
        
    #     if not code or not pattern: return
        
    #     with self._lock:
    #         ts = self._tick_series.get(code)
    #         if ts:
    #             # 将信号写入形态提示，触发 UI 变色
    #             ts.pattern_hint = pattern
    #             self.data_version += 1

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

    def ensure_data_ready_async(self, on_ready_callback: Callable = None):
        """[ROOT-FIX] 真正的异步懒加载入口：启动后台线程读取 IO"""
        if self._is_ready:
            if on_ready_callback: on_ready_callback()
            return

        def _worker():
            try:
                start_t = time.time()
                logger.info("📡 [Detector] Background data loading started...")
                self._load_stock_selector_data()
                self._is_ready = True
                dur = time.time() - start_t
                logger.info(f"✅ [Detector] Background loading completed in {dur:.2f}s.")
                if on_ready_callback:
                    on_ready_callback()
            except Exception as e:
                logger.error(f"❌ [Detector] Background loading failed: {e}")

        if self._loading_thread is None or not self._loading_thread.is_alive():
            self._loading_thread = threading.Thread(target=_worker, name="DetectorAsyncLoad", daemon=True)
            self._loading_thread.start()
        else:
            logger.warning("📡 [Detector] Background loading already in progress.")

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
        5. [NEW] 重置全量活跃数与赛马稳定性时长
        """
        now = time.time()
        with self._lock:
            self.baseline_time = now
            self.sector_anchors.clear()
            for ts in self._tick_series.values():
                ts.score_anchor = ts.score
                ts.price_anchor = ts.current_price
                
                # [IMMEDIATE] 瞬间全量重置活跃数 (USER-RULE: 活跃数应随基准同步重置)
                ts.signal_count = 0
                # [FIX] 将上一次信号时间重置为当前分钟，防止复位后由于得分仍然达标而立即触发 +1
                curr_min = int(time.time() // 60)
                ts._last_sig_min = curr_min
                ts._bar_active_reward = 0
                ts._last_active_price = ts.current_price # 以当前价格为新基准
                
                # 同步重置赛马稳定性时长
                ts.racing_start_ts = 0.0
                ts.last_stable_ts = 0.0
                ts.racing_duration = 0.0
                
                # 瞬间清干增量涨幅缓存，避免 UI 闪烁
                ts.pct_diff = 0.0
                ts.price_diff = 0.0
                ts.pattern_hint = ""

            # [REFINED] 同步清理实时基因报警记录 (IntradayEmotionTracker)
            if hasattr(self, 'realtime_service') and self.realtime_service:
                tracker = getattr(self.realtime_service, 'emotion_tracker', None)
                if tracker:
                    tracker.clear()
                    logger.info("✅ [Detector] IntradayEmotionTracker (SBC) signals has been cleared.")

            logger.info(f"🔄 [Detector] All observation anchors and active metrics have been reset.")


    def set_strategy(self, key: str, **kwargs):
        """动态更新策略参数"""
        if key in self.strategies:
            self.strategies[key].update(kwargs)

    def register_codes(self, df_all: pd.DataFrame):
        """
        从 df_all 中注册新的 code 订阅，补充元数据。
        需在主线程调用（如 update_tree / on_realtime_data_arrived）。
        """
        if self.in_history_mode:
            return # [GUARD] 历史复盘模式下，禁止修改当前活动的个股映射，防止污染视口

        if df_all is None or df_all.empty:
            return

        # [THREAD-SAFETY] 防御性 copy：防止调用方在其他线程中修改或释放底层 C 数组
        df_all = df_all.copy()

        # 确保 code 列存在
        if 'code' in df_all.columns:
            df = df_all.set_index('code', drop=False)
        else:
            df = df_all.copy()
            df['code'] = df.index.astype(str)

        # [🚀 FIX] 从行情数据中提取最新的时间戳，推进全局时钟 (Racing Timeline)
        # 兼容 ticktime, timestamp, time 等多种字段名
        time_cols = ['ticktime', 'timestamp', 'time', 'datetime']
        found_time_col = next((c for c in time_cols if c in df.columns), None)
        if found_time_col:
            try:
                latest_val = df[found_time_col].max()
                if isinstance(latest_val, (int, float)) and latest_val > 1000000000: # Unix TS
                    if latest_val > self.last_data_ts: self.last_data_ts = float(latest_val)
                elif isinstance(latest_val, str) and (':' in latest_val or '-' in latest_val):
                    # 处理 HH:MM:SS 或 YYYY-MM-DD HH:MM:SS
                    from dateutil.parser import parse
                    ts = parse(latest_val).timestamp()
                    if ts > self.last_data_ts: self.last_data_ts = ts
            except:
                pass

        # 重建板块图（每次全量更新，成本低）
        self._rebuild_sector_map(df)

        new_codes = []
        for row in df.itertuples(index=False):
            # [🚀 格式规范化] 强制提取 6 位数字代码，剔除后缀(如 .SH/.SZ)，彻底根治重复入表问题
            raw_code = str(getattr(row, 'code', '')).strip()
            code = _RE_NON_DIGIT.sub('', raw_code)
            if len(code) < 6 and code.isdigit(): code = code.zfill(6)
            elif len(code) > 6: code = code[-6:]
            
            if code == '000000' or not code or len(code) != 6: continue
            
            row_data = row._asdict()
            name = str(row_data.get('name', '')).strip()
            
            # [🚀 SANITIZATION] 过滤空名称、占位符名称等无效个股
            if not name or name in ['', 'nan', 'NaN', 'None', 'null', 'δ֪', '未知', code]:
                continue

            with self._lock:
                # 维护极限性能索引
                self._code_index[code] = name
                self._name_index[name] = code
                
                if code not in self._tick_series:
                    ts_obj = TickSeries(code)
                    ts_obj.update_meta(row_data)
                    self._tick_series[code] = ts_obj
                    new_codes.append(code)
                else:
                    self._tick_series[code].update_meta(row_data)

        # [🚀 肃清冗余] 定期清理 _tick_series 中非标准 6 位格式的脏数据 (如带后缀的残余) 和无有效名称的占位股
        # 每 100 次注册执行一次，防止 CPU 抖动
        if not hasattr(self, '_cleanup_counter'): self._cleanup_counter = 0
        self._cleanup_counter += 1
        if self._cleanup_counter % 100 == 0 or self._cleanup_counter == 1:
            with self._lock:
                dirty_keys = [
                    k for k, ts in self._tick_series.items()
                    if len(str(k)) != 6 or not str(k).isdigit() or str(k) == '000000' or 
                    not ts.name or str(ts.name).strip() in ['', 'nan', 'NaN', 'None', 'null', 'δ֪', '未知', str(k)]
                ]
                if dirty_keys:
                    logger.info(f"🧹 [Detector] 清理了 {len(dirty_keys)} 个非标或无有效名称的脏代码键: {dirty_keys[:5]}...")
                    for k in dirty_keys:
                        self._tick_series.pop(k, None)
                        self._global_snap_cache.pop(k, None)
                        if hasattr(self, '_code_index'): self._code_index.pop(k, None)
                        # 同时从逆向名称索引清理
                        name_to_del = [n for n, c in list(self._name_index.items()) if c == k]
                        for n in name_to_del:
                            self._name_index.pop(n, None)

        # 对新 code 或 K线为空的 code：拉历史 K 线做冷启
        target_codes = new_codes + [c for c in df['code'].astype(str).str.strip().str.zfill(6) if c in self._tick_series and not self._tick_series[c].klines]
        target_codes = list(set(target_codes)) # 去重
        
        # [FIX] 极限性能保护：在历史回测/复盘模式下，禁用冷启动历史 K 线拉取
        # 此时数据流量极大 (97 tps)，拉取 5000 只股的 K 线会导致 GIL 彻底锁死并引发崩溃
        if self.realtime_service and target_codes and not self.in_history_mode:
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

    def update_scores(self, active_codes=None, force: bool = False, skip_evaluate: bool = False):
        """
        主入口：计算个股分值并聚合板块。
        active_codes: 如果提供，则执行增量更新 (O(Delta) 复杂度)，极度节省性能。
        force: 是否强制全量计算 (通常用于每 5 分钟的全局对齐)。
        skip_evaluate: 是否跳过个股评估阶段 (如果之前已执行过 _evaluate_code)。
        """
        # [THROTTLE] 节流：防止短时间内被 Worker 疯狂调用，释放 CPU
        now_ts = time.time()
        if not force and now_ts - getattr(self, '_last_update_ts', 0) < 0.3:
            return
        self._last_update_ts = now_ts

        # [FIX] 跨日重置必须在所有评估逻辑之前执行
        eval_dt = datetime.datetime.fromtimestamp(self.last_data_ts) if self.last_data_ts > 0 else datetime.datetime.now()
        self._check_day_switch(eval_dt)

        # [GUARD] 历史模式下，除非显式强制刷新，否则禁止后台自动更新评分
        if self.in_history_mode and not force:
            return

        if not skip_evaluate:
            with self._lock:
                if active_codes is not None and not force:
                    # [INCREMENTAL] 增量模式：仅对当前变动的代码进行评估
                    all_codes = [c for c in active_codes if c in self._tick_series]
                    
                    # [NEW] ⚡ [PERF-CORE] 极其重要的过滤：不要每一轮都跑 5400+ 个代码
                    # 1. 必选股：种子股、自选股、当前活跃板块个股
                    # 2. 异动股：涨跌幅绝对值 > 1.5% 或 量比 > 2.0
                    # 3. 冷门股：每 20 轮才全量扫描一次 (确保能发现新异动)
                    
                    essential = set(self.stock_selector_seeds.keys()) | set(self.daily_watchlist.keys())
                    # [🚀 FIX] 极其重要：当前活跃板块中的所有成员（龙头+跟随）都属于必选评估集
                    # 否则它们在 UI 上的形态暗示（pattern_hint）会因为跳过评估而停止更新
                    for s_info in self.active_sectors.values():
                        if s_info.get('leader'): essential.add(s_info['leader'])
                        for f in s_info.get('followers', []):
                            if f.get('code'): essential.add(f['code'])
                        for rc in s_info.get('race_candidates', []):
                            if rc.get('code'): essential.add(rc['code'])
                    
                    scan_all = (getattr(self, '_full_scan_counter', 0) % 20 == 0)  # 略微提高全量扫描频率 (20->15)
                    self._full_scan_counter = getattr(self, '_full_scan_counter', 0) + 1
                    
                    target_codes = []
                    for code in all_codes:
                        if scan_all or (code in essential):
                            target_codes.append(code)
                            continue
                        
                        ts = self._tick_series[code]
                        # 异动检查：涨跌幅 > 1.5% 或 量比 > 2.0
                        if abs(ts.current_pct) > 1.5 or ts.vol_ratio > 2.0:
                            target_codes.append(code)
                    
                    codes = target_codes
                else:
                    # [FULL-SWEEP] 全量模式
                    codes = list(self._tick_series.keys())
                
                # [PERF] 预计算锚点时间戳，避免在 5000 次循环内重复调用 datetime.fromtimestamp
                anchor_930 = eval_dt.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()
                self._today_anchor_930 = anchor_930
                
            # 🚀 [GIL-FIX] 将大规模评估循环移出锁外，彻底根治 GIL 饥饿与 IPC 卡死
            for i, code in enumerate(codes):
                self._evaluate_code_unlocked(code, anchor_930=anchor_930)
                # [YIELD] 强制让出 CPU，给 UI / Manager Proxy 喘息的机会
                if i > 0 and i % 200 == 0:
                    time.sleep(0)

            with self._lock:
                self.last_processed_count = len(codes)

        with self._lock:
            self.data_version += 1 # 评分更新后递增版本号
        
        # 板块聚合逻辑
        self._aggregate_sectors(active_codes=active_codes if not force else None)

    def search_by_index(self, query: str) -> List[dict]:
        """[NEW] 利用内存索引实现极限性能搜索 (O(1) ~ O(m))"""
        q = query.strip().lower()
        if not q: return []
        
        results = []
        with self._lock:
            # 1. 精准代码匹配 (6位)
            if q in self._code_index:
                code = q
                ts = self._tick_series.get(code)
                if ts: results.append(self._make_search_item(ts, "代码精准匹配"))
            
            # 2. 精准名称匹配
            elif q in self._name_index:
                code = self._name_index[q]
                ts = self._tick_series.get(code)
                if ts: results.append(self._make_search_item(ts, "名称精准匹配"))
            
            # 3. 模糊匹配 (代码前缀或名称包含)
            else:
                for code, name in self._code_index.items():
                    if q in code or q in name.lower():
                        ts = self._tick_series.get(code)
                        if ts: results.append(self._make_search_item(ts, "模糊匹配"))
                        if len(results) >= 50: break # 限制返回数量防止 UI 卡顿
        return results

    def _make_search_item(self, ts: TickSeries, reason: str) -> dict:
        return {
            'code': ts.code,
            'name': ts.name,
            'pct': ts.current_pct,
            'score': ts.score,
            'momentum_score': ts.momentum_score,
            'sector': ts.category,
            'reason': reason,
            'time_str': '--:--:--'
        }

    def _check_day_switch(self, current_dt: datetime.datetime):
        """[OPTIMIZED] 基于数据日期的核心切换逻辑：兼容模拟回测，消除冗余触发"""
        if self.in_history_mode: return # 复盘模式由 load_from_snapshot 统一重置
        
        today_str = current_dt.strftime('%Y-%m-%d')
        
        # [GATEKEEPER] ⚡ 日期未变直接秒回。
        # 1. 解决了实时流 1-3 次冗余触发问题；
        # 2. 完美支持模拟回测（不依赖系统墙上时钟）；
        # 3. 确保了后续重压力逻辑在数据日期维度上的幂等性。
        if self._last_data_date == today_str:
            return

        is_work_day = cct.is_trade_date(current_dt)
        is_fresh_start = (not self._last_data_date)

        # 1. 非交易日静默逻辑
        if not is_work_day:
            # 即使不是交易日，如果它是 Cold Start，我们也记录一下当前日期
            if is_fresh_start: self._last_data_date = today_str
            return

        # 2. 核心重置逻辑 (仅在交易日 09:00 后触发)
        if current_dt.hour >= 9:
            # [HEALING] 保险：盘中侦测昨日信号残留
            if self._prune_expired_signals(current_dt):
                self._last_data_date = today_str 
                return

            # [SWITCH] 标准日期切换
            if is_fresh_start:
                self._last_data_date = today_str
            elif self._last_data_date != today_str:
                # ⭐ [C-Reinforcement] 只有在开盘交易准备段 (09:00+) 才自动触发清理
                # 防止在凌晨重启程序时意外清空了正在分析的昨日数据
                if current_dt.hour < 9:
                    return
                logger.info(f"📅 [Detector] 日期切换确认 ({self._last_data_date} -> {today_str})，正在执行重置...")
                self._reset_daily_state(current_dt)
                self._last_data_date = today_str
                return

    def _prune_expired_signals(self, current_dt: datetime.datetime) -> bool:
        """
        [FIXED] 自愈清理：根据重点表 (watchlist) 和活跃板块 (active_sectors) 中的 触发时间 判定是否过期。
        返回 True 表示执行了重置/清理。
        """
        today = current_dt.date()
        stale_found = False
        
        with self._lock:
            # 1. 检查重点监控表
            if self.daily_watchlist:
                for code, info in self.daily_watchlist.items():
                    ts = info.get('trigger_ts', 0)
                    if ts > 0:
                        item_date = datetime.datetime.fromtimestamp(ts).date()
                        if item_date < today:
                            stale_found = True
                            break
            
            # 2. 如果重点表没发现，检查活跃板块表 (可能昨天没有涨停但有很多异动板块)
            if not stale_found and self.active_sectors:
                for name, info in self.active_sectors.items():
                    ts = info.get('ts', 0) # 这里的 ts 是最后更新时间
                    if ts > 0:
                        item_date = datetime.datetime.fromtimestamp(ts).date()
                        if item_date < today:
                            stale_found = True
                            break
        
        if stale_found:
            logger.warning(f"🧹 [Detector] 自愈清理：检测到昨日残留数据 (触发时期早于 {today})，正在强制肃清。")
            self._reset_daily_state(current_dt)
            return True
        return False

    def _reset_daily_state(self, current_dt: datetime.datetime):
        """[DRY] 统一执行全量每日状态重置，确保今日看板从零开始"""
        with self._lock:
            # 1. 清空看板级汇总表
            self.daily_watchlist.clear()
            self.active_sectors.clear()
            self.sector_anchors.clear()
            self._sector_active_stocks_persistent.clear()
            
            # 2. 状态重置：清空内存中所有个股的情绪评分锚点与异动标签
            for ts in self._tick_series.values():
                ts.score = 0.0
                ts.momentum_score = 0.0
                ts.score_anchor = 0.0
                ts.price_anchor = ts.current_price if hasattr(ts, 'current_price') else 0.0
                ts.first_breakout_ts = 0.0      # 彻底重置异动计时器
                ts.signal_count = 0             # [FIX] 彻底重置活跃信号计数
                ts._last_sig_min = 0            # 重置活跃分钟锁
                ts._bar_active_reward = 0       # 重置活跃奖励锁
                ts.pattern_hint = ""           # 清空形态描述
                ts.klines.clear()              # 清空分时数据（保留 deque 结构，避免破坏 maxlen）
                
        # 3. 时间锚点重置，作为后续计算“异动了多久”的基准
        self.baseline_time = current_dt.timestamp()
        self.data_version += 1 # 联动 UI 全量重传

    def stop(self):
        # """[NEW] 停止探测器：从实时服务注销，防止退出后回调触发崩溃"""
        # if hasattr(self, 'realtime_service') and self.realtime_service:
        #     try:
        #         self.realtime_service.unsubscribe_all(self._on_tick)
        #         logger.info("🛑 BiddingMomentumDetector unsubscribed successfully.")
        #     except Exception as e:
        #         logger.error(f"Error unsubscribing BiddingMomentumDetector: {e}")
        pass

    def clear_all_state(self):
        """[NEW] 彻底清除内存状态，用于在回测与实盘切换时防止“脏数据”污染"""
        # logger.info("🧹 BiddingMomentumDetector clearing all internal states...")
        # with self._lock:
        #     self._tick_series.clear()
        #     self.daily_watchlist.clear()
        #     self.active_sectors.clear()
        #     self.sector_anchors.clear()
        #     self._sector_active_stocks_persistent.clear()
        #     if hasattr(self, '_global_snap_cache'):
        #         self._global_snap_cache.clear()
        #     self.data_version += 1
        pass

    def reset_stock_active(self, codes: List[str]):
        """[NEW] 手动重置指定个股的活跃计数"""
        if not codes: return
        with self._lock:
            for code in codes:
                ts = self._tick_series.get(code)
                if ts:
                    ts.signal_count = 0
                    ts._last_sig_min = 0
                    ts._bar_active_reward = 0
            self.data_version += 1

    def reconstruct_all_from_cache(self):
        """[NEW] 为历史模式提供的全量算法重映射，用于在模式切换时立即同步 UI"""
        if not getattr(self, 'in_history_mode', False): return
        
        logger.info("🔄 [Detector] 正在为全部板块重新映射算法逻辑...")
        from collections import defaultdict
        code_sector_map = defaultdict(list)
        for code, snap in self._global_snap_cache.items():
            cats = [c.strip() for c in _RE_CAT_SPLIT.split(str(snap.get('category', ''))) if c.strip()]
            for cat in cats:
                code_sector_map[cat].append(snap)
        
        market_avg = getattr(self, 'last_market_avg', 0.0)
        # 直接在现有板块映射上执行原地覆盖
        for s_name, info in list(self.active_sectors.items()):
            candidates = code_sector_map.get(s_name, [])
            if candidates:
                self._reconstruct_sector_from_candidates(s_name, info, candidates, market_avg)
        
        # 版本递增触发 UI 刷新
        self.data_version = getattr(self, 'data_version', 0) + 1

    # ------------------------------------------------------------------ 持久化
    def _get_persistence_path(self, snapshot_date: str = None) -> str:
        # 使用 JohnsonUtil 中的 ramdisk 路径获取方法，统一管理
        base = cct.get_base_path()
        if snapshot_date:
            path = os.path.join(base, "snapshots")
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            full_path = os.path.abspath(os.path.join(path, f"bidding_{snapshot_date}.json.gz"))
            return full_path
            
        ram_path = cct.get_ramdisk_path("bidding_session_data.json.gz")
        if ram_path:
            return os.path.abspath(ram_path)
        # Final fallback - current directory snapshots if ramdisk is broken
        return os.path.abspath(os.path.join(base, "snapshots", "bidding_session_data.json.gz"))

    def _backup_session_file(self, file_path: str):
        """[NEW] 物理备份现有文件，防止覆写导致数据丢失"""
        if not os.path.exists(file_path):
            return
        try:
            base = cct.get_base_path()
            bak_dir = os.path.join(base, "snapshots", "backup")
            if not os.path.exists(bak_dir):
                os.makedirs(bak_dir, exist_ok=True)

            fname = os.path.basename(file_path).replace(".json.gz", "")
            
            # [FIX] 仅检查该特定文件名对应的备份
            all_baks = sorted([
                os.path.join(bak_dir, f) for f in os.listdir(bak_dir) 
                if f.endswith(".bak.gz") and fname in f
            ], key=os.path.getmtime)
            
            if all_baks:
                last_bak_mtime = os.path.getmtime(all_baks[-1])
                if time.time() - last_bak_mtime < 600:
                    return # 10 分钟内已备份过该文件，跳过

            mtime = os.path.getmtime(file_path)
            f_dt = datetime.datetime.fromtimestamp(mtime)
            
            # 生成带时间戳的文件名: bak_YYYYMMDD_HHMMSS_filename.bak.gz
            time_str = f_dt.strftime("%Y%m%d_%H%M%S")
            bak_name = f"bak_{time_str}_{fname}.bak.gz"
            bak_path = os.path.join(bak_dir, bak_name)
            
            if not os.path.exists(bak_path):
                shutil.copy2(file_path, bak_path)
                logger.info(f"💾 [Detector] Created safety backup: {bak_name}")
                
                # [CLEANUP] 重新获取该文件的备份列表，只保留最近 15 个
                all_file_baks = sorted([
                    os.path.join(bak_dir, f) for f in os.listdir(bak_dir) 
                    if f.endswith(".bak.gz") and fname in f
                ], key=os.path.getmtime)
                
                if len(all_file_baks) > 15:
                    for old_bak in all_file_baks[:-15]:
                        try:
                            os.remove(old_bak)
                        except:
                            pass
        except Exception as e:
            logger.debug(f"Session backup failed: {e}")

    def save_persistent_data(self, force=False):
        """最终统一版：旧版控制流 + 新版数据结构（完全行为对齐）"""
        # === ① history mode（旧版优先级最高）
        if getattr(self, "in_history_mode", False):
            logger.debug("[Detector] Skip save in history mode.")
            return

        try:
            # === ② 交易日双校验（恢复旧版）
            is_trade_day = cct.get_trade_date_status()
            if not cct.get_day_istrade_date():
                is_trade_day = False

            if not force and not is_trade_day:
                return

            now = datetime.datetime.now()

            # === ③ 时间过滤（严格按旧版顺序）
            if not force:
                if now.hour >= 16:
                    return
                if is_trade_day:
                    if now.hour < 9 or (now.hour == 9 and now.minute < 40):
                        return

            main_path = self._get_persistence_path()

            # === ④ 数据质量保护（保持新版）
            if os.path.exists(main_path):
                try:
                    mtime = os.path.getmtime(main_path)
                    f_dt = datetime.datetime.fromtimestamp(mtime)

                    if now.hour >= 15 or not is_trade_day:
                        current_sig_count = len([ts for ts in self._tick_series.values() if ts.score > 0])
                        if current_sig_count < 5 and (now - f_dt).days <= 2:
                            logger.info(f"🛡️ [Detector] Session empty ({current_sig_count}). Protecting existing data.")
                            return
                except Exception as e:
                    logger.debug(f"Persistence quality check error: {e}")

            # === ⑤ 内容检查（恢复旧版严格逻辑）
            if not force:
                if not self.active_sectors:
                    return

            # === 数据快照与构建 (Snapshotting under Lock)
            # [🚀 THREAD-SAFETY] 必须在锁内完成所有字典的遍历与快照提取，防止与后台行情更新冲突
            with self._lock:
                significant_stocks = {code: s for code, s in self._tick_series.items() if s.score >= 0.1}
                daily_watchlist_snap = self.daily_watchlist.copy()
                stock_selector_seeds_snap = self.stock_selector_seeds.copy()
                active_sectors_snap = self.active_sectors.copy()
                dragon_history_snap = list(self.dragon_3day_history)
                
                # 预提取所有相关代码的元数据，避免在锁外访问可能变动的 ts 对象属性
                relevant_codes = (
                    set(significant_stocks.keys())
                    | set(daily_watchlist_snap.keys())
                    | set(stock_selector_seeds_snap.keys())
                )
                for sinfo in active_sectors_snap.values():
                    relevant_codes.add(sinfo.get('leader'))
                    for f in sinfo.get('followers', []):
                        relevant_codes.add(f.get('code'))
                
                codes_list = [c for c in relevant_codes if c]
                
                # 构建元数据快照
                meta_cols = {
                    'code': codes_list, 'n': [], 'ph': [], 'c': [], 'lc': [], 'op': [], 'hd': [], 'ld': [],
                    'lh': [], 'll': [], 'np': [], 'fb': [], 'rl': [], 'iu': [], 'ic': [],
                    'p': [], 's': [], 'rs': [], 'sc': [], 'k': []
                }
                
                for code in codes_list:
                    ts = self._tick_series.get(code)
                    if ts:
                        # [P0-FIX] 在锁内完成所有属性提取，防止 ts 属性在循环中被行情线程修改
                        meta_cols['n'].append(ts.name)
                        meta_cols['ph'].append(ts.pattern_hint)
                        meta_cols['c'].append(ts.category)
                        meta_cols['lc'].append(round(ts.last_close, 3))
                        meta_cols['op'].append(round(ts.open_price, 3))
                        meta_cols['hd'].append(round(ts.high_day, 3))
                        meta_cols['ld'].append(round(ts.low_day, 3))
                        meta_cols['lh'].append(round(ts.last_high, 3))
                        meta_cols['ll'].append(round(ts.last_low, 3))
                        meta_cols['np'].append(round(ts.current_price, 3))
                        meta_cols['fb'].append(round(ts.first_breakout_ts, 1))
                        meta_cols['rl'].append(ts.ral)
                        meta_cols['iu'].append(1 if ts.is_untradable else 0)
                        meta_cols['ic'].append(1 if ts.is_counter_trend else 0)
                        meta_cols['p'].append(round(ts.current_pct, 2))
                        meta_cols['s'].append(round(ts.score, 1))
                        meta_cols['rs'].append(round(ts.racing_start_ts, 1))
                        meta_cols['sc'].append(ts.signal_count)
                        # [P0-FIX] compress_klines 内部会遍历 deque，必须在锁内转为 list 快照
                        klines_snap = list(ts.klines)
                        meta_cols['k'].append(compress_klines(klines_snap))
                    else:
                        for k in meta_cols:
                            if k != 'code':
                                meta_cols[k].append(None)

                # [NEW] 在锁内执行龙头统计更新，确保数据一致性
                self._update_daily_dragon_top2()
                # 提取清理后的 active_sectors (用于后续写入)
                def _clean_data(obj):
                    if isinstance(obj, dict):
                        return {k: _clean_data(v) for k, v in obj.items() if not k.endswith('klines')}
                    elif isinstance(obj, list):
                        return [_clean_data(item) for item in obj]
                    return obj
                
                sector_data_snap = {name: _clean_data(info) for name, info in active_sectors_snap.items() if info.get('score', 0) > 0}
                stock_scores_snap = {code: round(ts.score, 2) for code, ts in significant_stocks.items()}
                momentum_scores_snap = {code: round(ts.momentum_score, 2) for code, ts in significant_stocks.items() if ts.momentum_score > 0}

            data = {
                'data_date': self._last_data_date or now.strftime('%Y-%m-%d'),
                'timestamp': round(time.time(), 2),
                'last_data_ts': self.last_data_ts, # [🚀 FIX] 持久化最后行情时间，确保 UI 进度条连续
                'stock_scores': stock_scores_snap,
                'momentum_scores': momentum_scores_snap,
                'sector_data': sector_data_snap,
                'stock_score_anchors': {code: round(ts.score_anchor, 2) for code, ts in significant_stocks.items() if ts.score_anchor != 0.0},
                'baseline_time': round(self.baseline_time, 2),
                'sector_anchors': {name: round(s, 2) for name, s in self.sector_anchors.items()},
                'stock_price_anchors': {code: round(ts.price_anchor, 4) for code, ts in significant_stocks.items() if ts.price_anchor > 0},
                'meta_cols': meta_cols,
                'watchlist': daily_watchlist_snap,
                'stock_selector_seeds': stock_selector_seeds_snap,
                'dragon_3day_history': dragon_history_snap
            }

            # === JSON 安全：使用预缓存的 numpy 类型加速判断
            def np_handler(obj):
                if isinstance(obj, _NP_INT_TYPES): return int(obj)
                if isinstance(obj, _NP_FLOAT_TYPES): return float(obj)
                if isinstance(obj, _NP_ARRAY_TYPE): return obj.tolist()
                return str(obj)

            json_str = json.dumps(data, ensure_ascii=False, default=np_handler, separators=(',', ':'))
            out_bytes = zlib.compress(json_str.encode('utf-8'), level=6)

            # === 原子写
            def atomic_write(path, data_bytes):
                tmp = path + f".{os.getpid()}.tmp"
                with open(tmp, 'wb') as f:
                    f.write(data_bytes)
                os.replace(tmp, path)
            
            # === 写主文件
            if os.path.exists(main_path):
                self._backup_session_file(main_path)
                
            atomic_write(main_path, out_bytes)

            # === snapshot（完全恢复旧版语义）
            today_str = now.strftime('%Y%m%d')
            snapshot_path = self._get_persistence_path(snapshot_date=today_str)

            if os.path.normpath(main_path) != os.path.normpath(snapshot_path):
                try:
                    os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
                    # [NEW] 备份旧的 snapshot，防止被当前（可能损坏的）数据覆盖
                    # if os.path.exists(snapshot_path):
                    #     self._backup_session_file(snapshot_path)
                        
                    atomic_write(snapshot_path, out_bytes)
                    logger.info(f"📸 Snapshot saved to {snapshot_path}")
                except Exception as e:
                    logger.warning(f"Snapshot failed: {e}")

            logger.info(f"💾 Session saved → {main_path}")

        except Exception as e:
            logger.error(f"❌ Persistence save error: {e}")

    def load_persistent_data(self):
        """从磁盘加载之前的会话数据 (多层级防御版)"""
        path = self._get_persistence_path()
        if not os.path.exists(path): return
        
        try:
            with open(path, 'rb') as f:
                data = json.loads(zlib.decompress(f.read()).decode('utf-8'))
            
            file_date_str = data.get('data_date', '')
            # now_dt = datetime.datetime.now()
            # today_str = now_dt.strftime('%Y-%m-%d')
            # 🚀 [FIX] 交易日智能判定：如果是交易日则用今天，否则用上个交易日
            if cct.get_trade_date_status():
                today_str = _datetime.now().strftime('%Y-%m-%d')
            else:
                today_str = cct.get_last_trade_date()
            now_dt = datetime.datetime.strptime(today_str,"%Y-%m-%d")
            is_cross_day = (file_date_str != today_str)
            
            with self._lock:
                # 1. 恢复基础得分与板块结构
                stock_scores = data.get('stock_scores', {})
                for code, score in stock_scores.items():
                    # [🚀 SANITIZATION] 过滤无效代码
                    if code == '000000' or len(code) != 6 or not code.isdigit():
                        continue
                    if code not in self._tick_series: self._tick_series[code] = TickSeries(code)
                    self._tick_series[code].score = score
                
                momentum_scores = data.get('momentum_scores', {})
                for code, m_score in momentum_scores.items():
                    if code in self._tick_series: self._tick_series[code].momentum_score = m_score

                self.active_sectors = data.get('sector_data', {})
                stock_anchors = data.get('stock_score_anchors', {})
                for code, anchor in stock_anchors.items():
                    if code in self._tick_series: self._tick_series[code].score_anchor = anchor
                        
                self.baseline_time = data.get('baseline_time', time.time())
                self.sector_anchors = data.get('sector_anchors', {})
                
                # [🚀 FIX] 恢复最后数据时间戳，确保 UI 进度条连续
                self.last_data_ts = data.get('last_data_ts', 0.0)
                
                stock_price_anchors = data.get('stock_price_anchors', {})
                for code, p_anchor in stock_price_anchors.items():
                    if code in self._tick_series: self._tick_series[code].price_anchor = p_anchor
                    
                # 2. 跨日清理或同日恢复 Watchlist
                if is_cross_day:
                    logger.info(f"📅 [Detector] Cross-day load: Clearing signals, keeping meta.")
                    self.daily_watchlist = {}
                    self.active_sectors = {}
                    self.sector_anchors = {}
                    for ts in self._tick_series.values():
                        ts.score = 0.0
                        ts.momentum_score = 0.0
                        ts.score_anchor = 0.0
                        ts.first_breakout_ts = 0.0
                        ts.klines.clear()
                else:
                    raw_watchlist = data.get('watchlist', {})
                    today_midnight_ts = datetime.datetime.combine(now_dt.date(), datetime.time.min).timestamp()
                    valid_watchlist = {}
                    for code, entry in raw_watchlist.items():
                        ts_entry = entry.get('trigger_ts', 0)
                        if ts_entry >= today_midnight_ts: valid_watchlist[code] = entry
                    self.daily_watchlist = valid_watchlist

                # 3. 恢复核心 Meta 数据 (支持列式存储与旧版字典存储)
                self.stock_selector_seeds = data.get('stock_selector_seeds', {})
                meta_cols = data.get('meta_cols', {})
                if meta_cols and 'code' in meta_cols:
                    codes = meta_cols['code']
                    for i, code in enumerate(codes):
                        if not code or code == '000000' or len(code) != 6 or not code.isdigit():
                            continue
                        
                        def _get(key, default):
                            val = meta_cols.get(key, [])
                            return val[i] if i < len(val) and val[i] is not None else default
                        
                        t_name = _get('n', code)
                        # [🚀 SANITIZATION] 过滤空名字、占位名字
                        if not t_name or str(t_name).strip() in ['', 'nan', 'NaN', 'None', 'null', 'δ֪', '未知', code]:
                            continue

                        if code not in self._tick_series: self._tick_series[code] = TickSeries(code)
                        ts = self._tick_series[code]
                        ts.name = t_name
                        ts.pattern_hint = _get('ph', ts.pattern_hint)
                        ts.category = _get('c', ts.category)
                        ts.last_close = _get('lc', ts.last_close)
                        ts.open_price = _get('op', ts.open_price)
                        ts.high_day = _get('hd', ts.high_day)
                        ts.low_day = _get('ld', ts.low_day)
                        ts.last_high = _get('lh', ts.last_high)
                        ts.last_low = _get('ll', ts.last_low)
                        ts.now_price = _get('np', ts.now_price)
                        ts.first_breakout_ts = _get('fb', ts.first_breakout_ts)
                        ts.score = _get('s', ts.score)
                        ts.ral = _get('rl', ts.ral)
                        ts.is_untradable = bool(_get('iu', ts.is_untradable))
                        ts.is_counter_trend = bool(_get('ic', ts.is_counter_trend))
                        ts.racing_start_ts = _get('rs', ts.racing_start_ts)
                        ts.signal_count = _get('sc', 0)
                        
                        # 重建 Snap 缓存供渲染
                        self._global_snap_cache[code] = {
                            'code': code, 'name': ts.name, 'pct': round(ts.current_pct, 2), 'score': ts.score,
                            'price': ts.now_price, 'last_close': ts.last_close, 'category': ts.category,
                            'first_breakout_ts': ts.first_breakout_ts, 'klines': decompress_klines(_get('k', [])),
                            'is_untradable': ts.is_untradable, 'is_counter_trend': ts.is_counter_trend,
                            'pattern_hint': ts.pattern_hint, 'vol_ratio': ts.vol_ratio,
                            'signal_count': ts.signal_count
                        }
                        
                        klines_data = _get('k', None)
                        if klines_data:
                            ts.klines.clear()
                            for k in decompress_klines(klines_data): ts.push_kline(k)
                else:
                    meta_data = data.get('meta_data', {})
                    for code, m in meta_data.items():
                        if not code or code == '000000' or len(code) != 6 or not code.isdigit():
                            continue
                        t_name = m.get('name', '')
                        # [🚀 SANITIZATION] 过滤空名字、占位名字
                        if not t_name or str(t_name).strip() in ['', 'nan', 'NaN', 'None', 'null', 'δ֪', '未知', code]:
                            continue
                        if code not in self._tick_series: self._tick_series[code] = TickSeries(code)
                        ts = self._tick_series[code]
                        ts.last_close = m.get('last_close', ts.last_close)
                        ts.open_price = m.get('open_price', ts.open_price)
                        ts.now_price = m.get('now_price', ts.now_price)
                        ts.name = t_name
                        ts.category = m.get('category', ts.category)
                        ts.score = m.get('score', ts.score)
                        ts.klines.clear()
                        for k in decompress_klines(m.get('klines', [])): ts.push_kline(k)
                
                self._last_data_date = today_str if is_cross_day else file_date_str
                try:
                    self._concept_data_date = datetime.datetime.strptime(self._last_data_date, '%Y-%m-%d').date()
                except:
                    self._concept_data_date = now_dt.date()
                
                logger.info(f"♻️ [Detector] Session restored: {len(self._tick_series)} stocks, {len(self.active_sectors)} sectors")
        except Exception as e:
            logger.error(f"❌ [Detector] Session load failed: {e}")
        
        self._gc_old_sectors()
        self._init_dragon_3day_tracker()

    def load_from_snapshot(self, filepath: str) -> bool:
        """从指定的快照文件恢复数据，用于历史复盘 (原子替换版本)"""
        try:
            if not os.path.exists(filepath):
                logger.error(f"Snapshot file not found: {filepath}")
                return False

            # [AUTO-STASH] 如果当前是实盘模式，先暂存数据
            if not self.in_history_mode:
                self.stash_live_session()

            # 1. 后台读取与解压 (无锁)
            with open(filepath, 'rb') as f:
                raw_data = f.read()
            
            try:
                decompressed = zlib.decompress(raw_data).decode('utf-8')
                data = json.loads(decompressed)
            except Exception:
                try:
                    decompressed = gzip.decompress(raw_data).decode('utf-8')
                    data = json.loads(decompressed)
                except Exception as e:
                    logger.error(f"[Detector] Snapshot decompression failed: {e}")
                    return False

            # 2. 准备临时容器 (无锁)
            new_tick_series: Dict[str, TickSeries] = {}
            new_snap_cache: Dict[str, Dict[str, Any]] = {}
            
            stock_scores = data.get('stock_scores', {})
            momentum_scores = data.get('momentum_scores', {})
            meta_cols = data.get('meta_cols', {})
            
            # [PHASE-1] 重构个股数据与 K 线 (无锁，不阻塞 UI 访问现有数据)
            codes_list = meta_cols.get('code', [])
            meta_idx_map = {c: idx for idx, c in enumerate(codes_list)} if codes_list else {}
            
            for code, score in stock_scores.items():
                # [🚀 SANITIZATION] 过滤无效代码
                if code == '000000' or len(code) != 6 or not code.isdigit():
                    continue

                ts = TickSeries(code)
                ts.score = score
                ts.momentum_score = momentum_scores.get(code, 0.0)
                
                if meta_idx_map:
                    i_idx = meta_idx_map.get(code)
                    if i_idx is not None:
                        def _get_val(key, default):
                            v_list = meta_cols.get(key, [])
                            return v_list[i_idx] if i_idx < len(v_list) and v_list[i_idx] is not None else default
                        
                        ts.name = _get_val('n', code)
                        
                        # [🚀 SANITIZATION] 过滤空名字、占位名字
                        if not ts.name or str(ts.name).strip() in ['', 'nan', 'NaN', 'None', 'null', 'δ֪', '未知', code]:
                            continue

                        ts.category = _get_val('c', '')
                        ts.last_close = _get_val('lc', 0.0)
                        ts.high_day = _get_val('hd', 0.0)
                        ts.low_day = _get_val('ld', 0.0)
                        ts.last_high = _get_val('lh', 0.0)
                        ts.last_low = _get_val('ll', 0.0)
                        ts.now_price = _get_val('np', 0.0)
                        ts.first_breakout_ts = _get_val('fb', 0.0)
                        ts.ral = _get_val('rl', 0)
                        ts.is_untradable = bool(_get_val('iu', False))
                        ts.is_counter_trend = bool(_get_val('ic', False))
                        ts.pattern_hint = _get_val('ph', '')
                        ts.signal_count = _get_val('sc', 0)
                        if ts.signal_count > 0:
                            ts._last_sig_min = int(ts.first_breakout_ts // 60) if ts.first_breakout_ts > 0 else 0
                        
                        ts.klines.clear()
                        k_data = _get_val('k', [])
                        for k in decompress_klines(k_data):
                            ts.push_kline(k)
                
                new_tick_series[code] = ts
                new_snap_cache[code] = {
                    'code': code, 'score': score, 
                    'pct': ts.current_pct, 'price': ts.current_price,
                    'name': ts.name, 'category': ts.category, 'last_close': ts.last_close,
                    'high_day': ts.high_day, 'low_day': ts.low_day,
                    'last_high': ts.last_high, 'last_low': ts.last_low,
                    'pattern_hint': ts.pattern_hint, 'klines': list(ts.klines),
                    'is_untradable': ts.is_untradable, 'is_counter_trend': ts.is_counter_trend,
                    'ral': ts.ral, 'first_breakout_ts': ts.first_breakout_ts,
                    'vol_ratio': ts.vol_ratio, 'signal_count': ts.signal_count
                }

            # [PHASE-2] 原子替换 (短锁)
            with self._lock:
                # 1. 替换个股核心映射
                self._tick_series = new_tick_series
                self._global_snap_cache = new_snap_cache
                
                # 2. 替换其他元数据
                self.active_sectors = data.get('active_sectors', {})
                self.daily_watchlist = data.get('daily_watchlist', {})
                self.dragon_3day_history = data.get('dragon_3day_history', [])
                self.stock_selector_seeds = data.get('stock_selector_seeds', {})
                self.sector_anchors.clear()

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
                
                # 额外修复：确保 watchlist 中的个股名称也被恢复（从 snap_cache 中获取）
                for code, w in self.daily_watchlist.items():
                    if not w.get('name') and code in self._global_snap_cache:
                        w['name'] = self._global_snap_cache[code].get('name', code)
                    if not w.get('sector') and code in self._global_snap_cache:
                        w['sector'] = self._global_snap_cache[code].get('category', '')
                
                self.sector_anchors = data.get('sector_anchors', {})
                self.baseline_time = data.get('baseline_time', time.time())
                
                # [NEW] 核心修复：还原锚点后，立即根据当前价和锚点重建 diff 字段
                for code, ts in self._tick_series.items():
                    if ts.price_anchor > 0 and ts.now_price > 0:
                        ts.price_diff = ts.now_price - ts.price_anchor
                        if ts.price_anchor > 0:
                            ts.pct_diff = (ts.price_diff / ts.price_anchor) * 100
                    if ts.score_anchor > 0:
                        ts.score_diff = ts.score - ts.score_anchor
                    
                    # 同步到 snap_cache 供 UI 渲染层读取
                    if code in self._global_snap_cache:
                        self._global_snap_cache[code].update({
                            'pct_diff': round(ts.pct_diff, 2),
                            'price_diff': round(ts.price_diff, 3),
                            'score_diff': round(ts.score_diff, 2)
                        })

                # 成功加载后进入历史模式
                self.in_history_mode = True
                
                # [NEW] 记录快照日期，防止复盘过程中误触发重置
                snap_ts = data.get('timestamp', 0)
                if snap_ts > 0:
                    self._last_data_date = datetime.datetime.fromtimestamp(snap_ts).strftime('%Y-%m-%d')
                    self.last_data_ts = snap_ts # [FIX] Sync timestamp for UI linkage
                    # [FIX] 更新锚点缓存，防止后续板块重建时 _calculate_leader_score 崩溃
                    self._today_anchor_930 = datetime.datetime.fromtimestamp(snap_ts).replace(hour=9, minute=30, second=0, microsecond=0).timestamp()
                
                self.data_version += 1 # [FIX] Notify UI of data change after snapshot load
                
            # [CRITICAL] 为历史快照全量重建跟随股与角色态势
            # 性能优化：先建立个股 -> 板块的反向索引，避免 O(S*N) 的嵌套循环导致 UI 卡死
            logger.info(f"🔄 [Detector] 为 {len(self.active_sectors)} 个板块并行重建深度数据态势...")
            
            from collections import defaultdict
            code_sector_map = defaultdict(list)
            for code, snap in self._global_snap_cache.items():
                cats = [c.strip() for c in _RE_CAT_SPLIT.split(str(snap.get('category', ''))) if c.strip()]
                for cat in cats:
                    code_sector_map[cat].append(snap)
            
            market_avg = getattr(self, 'last_market_avg', 0.0)
            for s_name, info in self.active_sectors.items():
                candidates = code_sector_map.get(s_name, [])
                if candidates:
                    self._reconstruct_sector_from_candidates(s_name, info, candidates, market_avg)

            logger.info(f"🎬 [Detector] 历史快照已加载并重建完成: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}")
            return False

    # ---- [NEW] 实盘会话暂存与恢复逻辑 ----

    def stash_live_session(self):
        """[🚀 核心优化] 保存当前实盘会话数据到内存，防止复盘操作将其覆盖"""
        with self._lock:
            # 如果已经在历史模式，不要覆盖实盘暂存（防止二次覆盖丢失实盘）
            if self.in_history_mode:
                return
            
            # 我们直接持有当前的字典引用。
            # 当 load_from_snapshot 运行时，它会创建新的字典和新的 TickSeries 对象，
            # 因此旧的引用在 stash 中是安全的，不会被后续复盘操作修改。
            self._live_stash = {
                '_tick_series': self._tick_series,
                '_global_snap_cache': self._global_snap_cache,
                'active_sectors': self.active_sectors,
                'daily_watchlist': self.daily_watchlist,
                'sector_anchors': self.sector_anchors.copy() if hasattr(self, 'sector_anchors') else {},
                'baseline_time': self.baseline_time,
                'last_data_ts': self.last_data_ts,
                '_last_data_date': getattr(self, '_last_data_date', ""),
            }
            logger.info("💾 [Detector] Live session data stashed (in-memory).")

    def restore_live_session(self) -> bool:
        """[🚀 核心优化] 从内存恢复实盘会话数据"""
        if not self._live_stash:
            logger.warning("No live stash found, attempting to reload from persistence file.")
            # 如果内存没暂存（比如刚启动就进复盘），则尝试从磁盘持久化恢复
            return self.load_persistent_data()
        
        with self._lock:
            stash = self._live_stash
            self._tick_series = stash['_tick_series']
            self._global_snap_cache = stash['_global_snap_cache']
            self.active_sectors = stash['active_sectors']
            self.daily_watchlist = stash['daily_watchlist']
            self.sector_anchors = stash['sector_anchors']
            self.baseline_time = stash['baseline_time']
            self.last_data_ts = stash['last_data_ts']
            self._last_data_date = stash['_last_data_date']
            
            self.in_history_mode = False
            self.data_version += 1
            logger.info("🔄 [Detector] Live session data restored from memory stash.")
            return True

    # ---- [SUPER] 龙头三日跟踪核心算法 ----

    def _init_dragon_3day_tracker(self):
        """[SUPER] 启动时初始化三日跟踪逻辑：补齐前两日快照。支持在已有今日数据的情况下回溯补全。"""
        # [FIX] 如果已经完成初始化，或者历史记录中已经包含了 3 个不同日期的数据，跳过
        existing_dates = {d['date'] for d in self.dragon_3day_history}
        if self._dragon_init_done and len(existing_dates) >= 2:
            return
        
        # 仅在非复盘模式且实盘下执行一至多次载入
        if self.in_history_mode: return
        
        try:
            # 1. 获取所有存量快照并按日期排序
            snapshot_dir = os.path.join(os.getcwd(), 'snapshots')
            if not os.path.exists(snapshot_dir): return
            
            files = [f for f in os.listdir(snapshot_dir) if f.startswith('bidding_') and f.endswith('.json.gz')]
            if len(files) < 1: return
            
            # 提取日期并降序排列
            dates = []
            for f in files:
                try: d_str = f.split('_')[1].split('.')[0]; dates.append(d_str)
                except: continue
            dates.sort(reverse=True)
            
            # 🚀 [FIX] 交易日智能判定：如果是交易日则用今天，否则用上个交易日
            if cct.get_trade_date_status():
                # [FIX] 统一使用 YYYYMMDD 格式，对齐文件名
                today_str = datetime.datetime.now().strftime('%Y%m%d')
            else:
                # [FIX] cct 返回通常带横杠，需统一剔除
                today_str = cct.get_last_trade_date().replace('-', '')
            
            # 排除今日及未来日期，寻找历史交易日快照
            past_dates = [d for d in dates if d < today_str]
            
            # [UPGRADE] 1. 尝试从最近的一个快照中直接继承“完整多日历史”
            # 这样可以瞬间恢复 10 日内的 base_price (最低价基准)，而无需逐一清洗
            if past_dates:
                latest_f = os.path.join(snapshot_dir, f"bidding_{past_dates[0]}.json.gz")
                try:
                    with open(latest_f, 'rb') as f: raw = f.read()
                    try: data = json.loads(zlib.decompress(raw).decode('utf-8'))
                    except: data = json.loads(gzip.decompress(raw).decode('utf-8'))
                    
                    history_in_snap = data.get('dragon_3day_history', [])
                    if history_in_snap:
                        # 仅保留有效的历史日期
                        valid_history = [d for d in history_in_snap if d['date'] < today_str]
                        if valid_history:
                            self.dragon_3day_history = valid_history
                            unique_days = {d['date'] for d in valid_history}
                            if len(unique_days) >= 5:
                                logger.info(f"🐉 [DragonTracker] 成功从最近快照继承 {len(unique_days)} 日完整历史")
                                self._dragon_init_done = True
                                return
                except Exception as e:
                    logger.warning(f"Failed to inherit history from {latest_f}: {e}")

            # 2. 如果继承失败或数据不足，回退到逐个快照清洗逻辑 (Scavenge)
            new_history = []
            for d_str in reversed(past_dates[:15]): # 从旧到新排列，最多追溯 15 个交易日
                f_path = os.path.join(snapshot_dir, f"bidding_{d_str}.json.gz")
                leaders = self._scavenge_top2_from_snapshot(f_path, d_str)
                if leaders:
                    new_history.extend(leaders)
            
            if new_history:
                # 简单去重合并
                existing = { (d['date'], d['code']): d for d in self.dragon_3day_history }
                for d in new_history:
                    existing[(d['date'], d['code'])] = d
                self.dragon_3day_history = sorted(list(existing.values()), key=lambda x: x['date'], reverse=True)
                logger.info(f"🐉 [DragonTracker] 补齐完成，当前追踪库共 {len(self.dragon_3day_history)} 条记录")
            
            self._dragon_init_done = True
        except Exception as e:
            logger.error(f"❌ DragonTracker init failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _scavenge_top2_from_snapshot(self, f_path: str, date_str: str) -> list:
        """从指定快照中提取各板块的前 2 名强势股"""
        try:
            with open(f_path, 'rb') as f: raw = f.read()
            try: data = json.loads(zlib.decompress(raw).decode('utf-8'))
            except: 
                data = json.loads(gzip.decompress(raw).decode('utf-8'))
            
            sector_data = data.get('sector_data', {})
            stock_scores = data.get('stock_scores', {})
            
            # [UPGRADE] 优先从快照自带的 history 中寻找该日期的记录 (保留了精准的 base_price 最低价)
            stored_history = data.get('dragon_3day_history', [])
            exact_day_records = [d for d in stored_history if d.get('date') == date_str]
            if len(exact_day_records) >= 10:
                # 如果记录数足够，说明该快照已经包含了当天的龙头统计，直接返回
                return exact_day_records[:30]

            seen = set()

            # [NEW] 建立全量价格镜像，防止部分旧快照在 sector_data 中缺失价格字段
            meta_prices = {}
            meta_cols = data.get('meta_cols', {})
            if meta_cols and 'code' in meta_cols:
                codes_list = meta_cols['code']
                np_list = meta_cols.get('np', [])
                for i, c_code in enumerate(codes_list):
                    if i < len(np_list) and np_list[i] is not None:
                        meta_prices[c_code] = np_list[i]
            else:
                meta_data = data.get('meta_data', {})
                for c_code, m in meta_data.items():
                    p = m.get('now_price', m.get('price', 0))
                    if p > 0: meta_prices[c_code] = p

            all_candidates = []
            for s_name, s_info in sector_data.items():
                if s_info.get('score', 0) < 8.0: continue # 过滤弱势板块
                
                # 汇总所有潜力龙头
                candidates = s_info.get('followers', [])
                l_code = s_info.get('leader')
                if l_code and not any(f['code'] == l_code for f in candidates):
                    candidates.append({
                        'code': l_code, 
                        'name': s_info.get('leader_name', l_code), 
                        'score': stock_scores.get(l_code, 0),
                        'price': s_info.get('leader_price', 0)
                    })
                
                for c in candidates:
                    if c['code'] in seen: continue
                    # [FIX] 优先取板块明细价格，若缺失则从全量 meta 镜像补齐
                    b_p = float(c.get('price', meta_prices.get(c['code'], 0)))
                    
                    all_candidates.append({
                        'date': date_str,
                        'code': c['code'],
                        'name': c.get('name', c['code']),
                        'sector': s_name,
                        'score': round(c.get('score', 0), 1),
                        'base_price': b_p,
                        'base_vol_ratio': c.get('vol_ratio', 0)
                    })
                    seen.add(c['code'])
            
            # [UPGRADE] 全局势能排序，仅保留前 30 名
            all_candidates.sort(key=lambda x: x['score'], reverse=True)
            return all_candidates[:30]
        except Exception as e:
            logger.error(f"Scavenge failed for {date_str}: {e}")
            return []

    def _update_daily_dragon_top2(self, force: bool = False):
        """[SUPER] 更新今日的板块 Top 2 到追踪库（每日累加）"""
        # [NEW] 极限性能优化：如果数据版本未变化，且非强制刷新，则跳过重算
        if not force and self.data_version == self._last_dragon_update_v:
            return
        self._last_dragon_update_v = self.data_version

        # [FIX] 龙头多日追踪：区分实盘与回测/非交易日，确保日期列表严格对齐交易日
        if self.in_history_mode:
            # 历史回测模式：日期来源于数据流的时间戳
            if self.last_data_ts <= 0: return
            today_str = datetime.datetime.fromtimestamp(self.last_data_ts).strftime('%Y%m%d')
        else:
            # 实盘模式：如果是非交易日（如周末）且非强制刷新，则不产生今日记录，防止污染 3D/5D 日期窗口
            if not force and not cct.get_trade_date_status():
                return
            today_str = datetime.datetime.now().strftime('%Y%m%d')
        
        # 剔除今日已有的项，准备重新抓取今日最新的 Top 2
        history_only = [d for d in self.dragon_3day_history if d['date'] != today_str]
        
        # [FIX] 获取今日已有的基准记录，用于锁定最初发现时的基准价，避免实盘运行期间漂移
        existing_today = {d['code']: d for d in self.dragon_3day_history if d['date'] == today_str}
        
        # 提取今日潜在龙头
        potential_today = []
        seen = set()
        for s_name, s_info in self.active_sectors.items():
            if s_info.get('score', 0) < self.sector_score_threshold * 1.5: continue # 提高门槛
            
            followers = s_info.get('followers', [])
            candidates = list(followers)
            l_code = s_info.get('leader')
            if l_code and not any(f['code'] == l_code for f in candidates):
                # [FIX] 补全龙头价格等核心数据
                candidates.append({
                    'code': l_code, 
                    'name': s_info.get('leader_name', ''), 
                    'score': s_info.get('score', 0),
                    'price': s_info.get('leader_price', 0)
                })
            
            for c in candidates:
                code = c['code']
                if code in seen: continue
                
                # [FIX] 健壮性补强：如果 candidates 中缺少核心字段，从全局 TickSeries 补齐
                ts = self._tick_series.get(code)
                c_name = c.get('name') or (ts.name if ts else code)
                c_price = c.get('price') or (ts.now_price if ts else 0.0)
                c_vr = c.get('vol_ratio') or (ts.vol_ratio if ts else 0.0)

                # [FIX] 基准价锁定：如果今日已入库，则继承最初入库时的价格
                if code in existing_today:
                    base_price = existing_today[code].get('base_price', c_price)
                else:
                    # [UPGRADE] 2026-04-27: 取第一天的最低价作为起点基准 (如果有)
                    # 解决用户反馈的“累计涨幅为0”以及“没有取第一天最低价”的问题
                    base_price = ts.low_day if (ts and ts.low_day > 0) else c_price
                    
                potential_today.append({
                    'date': today_str,
                    'code': code,
                    'name': c_name,
                    'sector': s_name,
                    'score': round(c.get('score', 0), 1),
                    'base_price': base_price,
                    'base_vol_ratio': c_vr
                })
                seen.add(code)
                # [FIX] 仅在非复盘模式下投递联动，防止历史加载时队列溢出
                if not self.in_history_mode and self.enable_background_linkage:
                    # [ROOT-FIX] 标记为 auto=True 启用节流与去重，解决后台自动刷新导致的“灵异联动”
                    self.link_manager.push(code, auto=True)
        
        # [UPGRADE] 今日全局势能排序 Top 30
        potential_today.sort(key=lambda x: x['score'], reverse=True)
        today_leaders = potential_today[:30]
        
        # [UPGRADE] 极致剪裁：合并历史与今日，确保每一天都只保留 Top 30，且仅保留最近 3 日
        combined = history_only + today_leaders
        all_dates = sorted(list({d['date'] for d in combined}), reverse=True)
        valid_dates = all_dates[:10] # 仅保留最近 10 个交易日以支持 3D/5D 切换
        
        final_history = []
        for d_str in valid_dates:
            day_data = [d for d in combined if d['date'] == d_str]
            # 再次按分数排序并取前 30，防止历史脏数据残留
            day_data.sort(key=lambda x: x.get('score', 0), reverse=True)
            final_history.extend(day_data[:30])
            
        self.dragon_3day_history = final_history
        logger.info(f"🐉 [DragonTracker] 当前三日库已精简: {len(self.dragon_3day_history)} 只强势领袖 (日期分布: {valid_dates})")

    def _determine_role(self, s: dict, leader_code: str, leader_score: float) -> str:
        """统一逻辑确定个股在板块中的角色标签"""
        pct = s.get('pct', 0.0)
        if s['code'] == leader_code:
            return "🏆 龙头"
        elif pct >= 9.5:
            return "核心🐲" 
        elif pct >= 7.0 or leader_score > 35:
            return "确核🐲" 
        elif pct >= 4.0 or leader_score > 20:
            return "晋级🌟"
        elif pct >= 1.5 or leader_score > 10:
            return "参赛🌱"
        else:
            return "跟随📌"

    def _calculate_leader_score(self, s: dict, sector: str, market_avg_pct: float, today_anchor_930: float = 0.0) -> float:
        """内部评估一个个股作为龙头的综合得分"""
        base_score = s.get('score') or 0.0
        pct = s.get('pct') or 0.0
        code = s.get('code')

        fb_ts = s.get('first_breakout_ts') or 0

        opening_bonus = 0.0

        # =========================
        # SAFE TIME NORMALIZATION
        # =========================
        try:
            fb_ts = float(fb_ts)
            if fb_ts <= 0:
                fb_ts = 0
        except:
            fb_ts = 0

        if fb_ts > 0:

            # anchor 优先外部，fallback 到内部缓存，最后兜底计算
            anchor_930 = today_anchor_930
            if anchor_930 <= 0:
                anchor_930 = getattr(self, '_today_anchor_930', 0.0)
            
            if anchor_930 <= 0:
                # [FINAL-FALLBACK] 极端情况下实时计算
                ref_dt = datetime.datetime.fromtimestamp(self.last_data_ts) if self.last_data_ts > 0 else datetime.datetime.now()
                anchor_930 = ref_dt.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()

            if anchor_930 > 0:

                offset = fb_ts - anchor_930

                if offset < 2700:
                    if offset <= 0:
                        opening_bonus = 12.0
                    else:
                        opening_bonus = 12.0 * (1.0 - offset / 2700.0)

        # =========================
        # NORMAL MODE
        # =========================
        if not getattr(self, 'use_dragon_race', False):

            l_score = base_score * 0.6 + pct * 0.8 + opening_bonus

            if code and code in self.stock_selector_seeds:
                l_score += 15.0

            total_amount = s.get('total_amount') or 0.0
            # 降低门槛，提高敏感度
            # if total_amount > 1e8:
            if total_amount > 5e7: # 5000万起步
                l_score += min(20.0, total_amount / 5e7)

            return l_score

        # =========================
        # DRAGON RACE MODE
        # =========================
        last_close = s.get('last_close') or 0
        price = s.get('price') or 0
        high_day = s.get('high_day') or 0

        drawdown_pct = 0.0
        if last_close > 0:
            drawdown_pct = max(
                0,
                (high_day - price) / last_close * 100
            )

        penalty = drawdown_pct * 2.5

        l_score = base_score * 0.6 + pct * 1.4 - penalty + opening_bonus

        if s.get('is_untradable'):
            l_score -= 50.0
        
        total_amount = s.get('total_amount') or 0.0
        # 降低门槛，提高敏感度
        # if total_amount > 5e7: # 5000万起步
        if total_amount > 1e8:
            l_score += min(20.0, total_amount / 1e8)

        return l_score

    def reconstruct_followers(self, sector_name: str):
        """[NEW] 手工从元数据缓存中重建指定板块的跟随股 (针对单个板块刷新)"""
        with self._lock:
            if sector_name not in self.active_sectors: return
            info = self.active_sectors[sector_name]
            
            candidates = []
            market_avg = self.last_market_avg
            for code, snap in self._global_snap_cache.items():
                cats = [c.strip() for c in _RE_CAT_SPLIT.split(str(snap.get('category', ''))) if c.strip()]
                if sector_name in cats:
                    snap['leader_score'] = self._calculate_leader_score(snap, sector_name, market_avg)
                    candidates.append(snap)
            
            if not candidates: return
            self._reconstruct_sector_from_candidates(sector_name, info, candidates, market_avg)

    def _reconstruct_sector_from_candidates(self, sector_name: str, info: dict, candidates: list, market_avg: float):
        """内部核心逻辑：根据候选人名单填充板块详情、角色和跟随股"""
        # 1. 计算龙分并排序 (强制重算以响应算法切换)
        board_score = info.get('score', 0.0)
        for snap in candidates:
            snap['leader_score'] = self._calculate_leader_score(snap, sector_name, market_avg)
        
        candidates.sort(key=lambda x: x.get('leader_score', 0), reverse=True)

        # [NEW] 重新计算板块相对于锚点的变动
        if sector_name in self.sector_anchors:
            info['score_diff'] = round(board_score - self.sector_anchors[sector_name], 2)
        
        # 2. 确定龙头
        current_leader = candidates[0]['code']
        info['leader'] = current_leader
        info['leader_name'] = candidates[0]['name']
        info['leader_pct'] = candidates[0].get('pct', 0.0)
        info['leader_price'] = candidates[0].get('price', 0.0)
        info['leader_klines'] = candidates[0].get('klines', [])
        
        # 3. 重建角色名单 (仅在模式开启时执行)
        race_candidates = []
        if getattr(self, 'use_dragon_race', False):
            for s in candidates[:15]:
                role = self._determine_role(s, current_leader, s['leader_score'])
                race_candidates.append({
                    'code': s['code'], 'name': s['name'], 'role': role,
                    'pct': round(s.get('pct', 0.0), 2), 'score': round(s.get('score', 0.0), 1),
                    'l_score': round(s['leader_score'], 1),
                    'pct_diff': round(s.get('pct_diff', 0.0), 2),
                    'score_diff': round(s.get('score_diff', 0.0), 2)
                })
        info['race_candidates'] = race_candidates
        
        # 4. 填充跟随股列表 (Top 15)
        info['followers'] = [
            {
                'code': s['code'], 
                'name': s.get('name', s['code']), 
                'pct': s.get('pct', 0.0), 
                'score': s.get('score', 0.0), 
                'price': s.get('price', 0.0), 
                'dff': s.get('dff', 0.0),
                'klines': s.get('klines', []),
                'last_close': s.get('last_close', 0.0),
                'first_ts': s.get('first_breakout_ts', 0.0),
                'score_diff': round(s.get('score_diff', 0.0), 2),
                'pct_diff': round(s.get('pct_diff', 0.0), 2),
                'price_diff': round(s.get('price_diff', 0.0), 3)
            } for s in candidates[1:16]
        ]

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
        """对单只 code 计算异动评分，写入 ts_obj.score (带锁包装器)"""
        with self._lock:
            self._evaluate_code_unlocked(code)

    def _evaluate_code_unlocked(self, code: str, anchor_930: float = None):
        """[PERF] 核心评估逻辑：不带锁版本，供内部批量调用。"""
        ts_obj = self._tick_series.get(code)
        if ts_obj is None:
            return

        # [P0-OPT] 直接访问 deque 末尾，避免 list(klines) 全量拷贝 (5000只×30条=15万次分配)
        _klines = ts_obj.klines
        klines_len = len(_klines)
        last_close = ts_obj.last_close
        ma20 = ts_obj.ma20
        ma60 = ts_obj.ma60

        if klines_len == 0 or last_close <= 0:
            return

        latest = _klines[-1]
        # [FIX] 核心修正：严禁优先使用 first_breakout_ts 更新时钟，必须使用当前 K 线时间
        ts_val = latest.get('ticktime') or latest.get('timestamp') or latest.get('time')
        data_ts = 0.0
        if ts_val:
            try:
                if isinstance(ts_val, (int, float)):
                    data_ts = float(ts_val)
                elif isinstance(ts_val, str):
                    data_ts = _datetime.fromisoformat(ts_val.replace(' ', 'T')).timestamp()
                else:
                    data_ts = float(ts_val)
            except:
                pass
        
        # 兜底：如果 K 线没时间，才考虑使用已有的异动时间或全局时间
        if data_ts <= 0:
            data_ts = ts_obj.first_breakout_ts if ts_obj.first_breakout_ts > 0 else self.last_data_ts
            if data_ts <= 0: data_ts = time.time()

        score = 0.0
        # [FIX] 使用实时价格评估，确保 Tick 级别响应
        cur_close = ts_obj.current_price
        cur_pct = ts_obj.current_pct
        
        cur_vol = float(latest.get('volume', 0.0))
        # [P0-OPT] day_open 优先从 ts_obj 取，避免访问 klines[0]
        day_open = ts_obj.open_price
        if not day_open:
            day_open = float(_klines[0].get('open', cur_close)) if klines_len > 0 else cur_close
        
        # 0. 周期因子 (Cycle Factor): 处于 MA20 之上且 MA20 向上，属于强周期
        cycle_score = 0.0
        
        # [NEW] 种子股加分 (StockSelector 预选项)
        seed_info = self.stock_selector_seeds.get(code)
        if seed_info:
            cycle_score += 3.0  # 选股器加分，但不过分膨胀
            # 将选股理由同步到形态暗示的前端
            if seed_info.get('reason'):
                # [FIX] 增加 延续 显式标记，让看板一眼看出是昨日主线
                reason_short = seed_info['reason'].split('|')[0]
                ts_obj.pattern_hint = f"[延续|{reason_short}]"

        if ma20 > 0 and cur_close > ma20:
            cycle_score += 1.0  # 基础牛熊分
            if ma60 > 0 and cur_close > ma60:
                cycle_score += 1.0
        
        # [NEW] 资金规模与角色判定 (Using user-provided real-time fields)
        amount_bonus = 0.0  # [FIX] 显式初始化奖分变量
        total_amount = ts_obj.total_vol * cur_close
        if total_amount > 2e8: # 权重规模
            amount_bonus += 2.0
            ts_obj.market_role = "主帅"
        elif ts_obj.vol_ratio > 3.0 and total_amount < 5e7:
            amount_bonus += 1.0
            ts_obj.market_role = "排头兵"
        else:
            ts_obj.market_role = "跟随"
            
        # [NEW] 地量回升奖励 (LVOL Reversal)
        if ts_obj.lvol > 0 and ts_obj.total_vol > ts_obj.lvol * 1.5:
            amount_bonus += 2.0 # 地量见底后放量
            ts_obj.pattern_hint += "[地量启动]"
            
        score += amount_bonus
        
        # [NEW] [PERF] 使用预计算的锚点时间戳，避免高频循环中的 replace/timestamp 开销
        fb_ts = ts_obj.first_breakout_ts
        if fb_ts > 0:
            # [PERF] 优先使用预计算的 _today_anchor_930（每日只算一次），避免高频循环对象分配
            # [FIX] 修复跨日 Bug：不再基于 fb_ts 的日期（可能是昨日），改用今日缓存
            if anchor_930 is None:
                anchor_930 = getattr(self, '_today_anchor_930', 0.0)
                if anchor_930 <= 0:
                    # 安全兜底：以今日实时日期计算（而非 fb_ts 的日期）
                    dt_now = datetime.datetime.now()
                    anchor_930 = datetime.datetime(dt_now.year, dt_now.month, dt_now.day, 9, 30, 0).timestamp()
            
            offset = fb_ts - anchor_930
            if offset < 2700: 
                if offset <= 0: # 竞价期 (9:15-9:30)
                    ts_obj.opening_bonus = 12.0
                else: # 开盘爆发期
                    ts_obj.opening_bonus = 12.0 * (1.0 - offset / 2700.0)
            else:
                ts_obj.opening_bonus = 0.0
        else:
            ts_obj.opening_bonus = 0.0
        
        # [Moved Up] 状态标志初始化
        is_counter = False
        is_untradable = False
        is_accumulating = False # [NEW] 蓄势标志
        is_reversal = False     # [NEW] 反转标志
        
        # 0.1 历史强度因子 (Integrated from DailyEmotionBaseline) - [PERF Caching]
        hist_strength = 0.0
        is_gap_leader = False  # 连续跳空强势龙头标记
        
        today_date = _datetime.date(_datetime.now()).isoformat()
        if self.realtime_service and hasattr(self.realtime_service, 'emotion_baseline'):
            # [PERF] 缓存基准数据，避免每秒数千次跨模块调用与正则
            if ts_obj._last_baseline_date != today_date:
                ts_obj._cached_baseline = self.realtime_service.emotion_baseline.get_baseline(code)
                ts_obj._cached_baseline_detail = self.realtime_service.emotion_baseline.get_baseline_detail(code)
                _m = _RE_YANG_DAYS.search(ts_obj._cached_baseline_detail)
                ts_obj._cached_yang_days = int(_m.group(1)) if _m else 0
                ts_obj._last_baseline_date = today_date
            
            baseline = ts_obj._cached_baseline
            detail = ts_obj._cached_baseline_detail
            _consecutive_days = ts_obj._cached_yang_days
            
            hist_strength = max(0, (baseline - 50) / 10.0)
            pattern_bonus = 0.0
            if "V反" in detail: pattern_bonus += 3.0
            elif "回归" in detail or "突破" in detail: pattern_bonus += 2.0
            
            _today_gap = (day_open - last_close) / last_close * 100.0 if last_close > 0 else 0.0
            if _consecutive_days >= 3 and _today_gap >= 2.0:
                is_gap_leader = True
                pattern_bonus += 4.0
                detail = f"⭐跳空强势{_consecutive_days}连阳▲{_today_gap:.1f}%"
            
            cycle_score += (hist_strength + pattern_bonus)
            
            # [FIX] 避免覆盖掉 [延续] 等历史种子标记
            existing = ts_obj.pattern_hint or ""
            if "[延续" in existing:
                ts_obj.pattern_hint = f"{existing.split(']')[0]}] | {detail}"
            else:
                ts_obj.pattern_hint = detail
            
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
            if klines_len >= 2:
                prev = _klines[-2]
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
        last_du4 = ts_obj.lastdu4
        ral_val = ts_obj.ral
        
        # 蓄势评分加成
        # if 0 < (cur_close - ma20) / ma20 < 0.015 and last_du4 < 2.5:
        if ma20 > 0 and (cur_close - ma20) / ma20 > 0.02:
            is_accumulating = True
            bonus = 5.0
            if ral_val > 15: bonus += 3.0 # 长期守住 MA20 的强势蓄势
            cycle_score += bonus
            base_pattern = f"蓄势({ral_val})|{base_pattern}" if base_pattern else f"蓄势({ral_val})"
        
        # 2. 反转与强度加成
        top0_val = 1 if ts_obj.top0 > 0 else 0
        top15_val = 1 if ts_obj.top15 > 0 else 0
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
            # [P0-OPT] 直接访问 deque 切片，避免 list() 全量拷贝
            if klines_len >= 3 and all(float(_klines[-3+i]['close']) > ma20 for i in range(3)):
                is_upper_band = True
                cycle_score += 3.0
                base_pattern = f"沿上轨🚀|{base_pattern}" if base_pattern else "沿上轨🚀"
        
        if is_new_high:
            base_pattern = f"★新高|{base_pattern}" if base_pattern else "★新高"

        # 5. 组装最终 pattern_hint
        # 结构: [历史/基础形态] | [今日实时信号]
        detail_hint = ts_obj.pattern_hint.split('|')[0].strip() if ts_obj.pattern_hint else ""
        
        final_hint = detail_hint or base_pattern
        current_signals = " | ".join(filter(None, [intraday_signal, ma_break_signal]))
        
        if current_signals:
            final_hint = f"{final_hint} | {current_signals}" if final_hint else current_signals
        
        ts_obj.pattern_hint = final_hint
        
        # 1. 竞价/开盘高开强度
        high_open_pct = (day_open - last_close) / last_close * 100 if last_close > 0 else 0.0
        bidding_score = 0.0
        if high_open_pct > 2.0:
            bidding_score += 2.0
            if high_open_pct > 5.0: bidding_score += 1.5
        
        # [NEW] 种子股延续性评分：昨日强势股如果今日也稳定，在竞价排序中拥有高优先级
        if seed_info and high_open_pct > 0.5:
            bidding_score += 3.0

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
            if self.strategies['consecutive_up']['enabled'] and klines_len >= 2:
                n_bars = self.strategies['consecutive_up']['bars']
                if klines_len >= n_bars:
                    # [P0-OPT] 小切片（通常 n_bars=2）deque 支持负索引直接比较，无需 list()
                    is_consecutive = all(_klines[-n_bars+i]['close'] > _klines[-n_bars+i-1]['close'] for i in range(1, n_bars))
                    if is_consecutive: score += 2.0
    
            # --- 4. 放量检查 (基于 TickSeries 维护的 vwap 和历史统计) ---
            if self.strategies['surge_vol']['enabled'] and klines_len >= 2:
                cur_v = float(_klines[-1].get('volume', 0.0))
                prev_v = float(_klines[-2].get('volume', 0.0))
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
        # [REMOVED] Time extraction moved up to ensure data_ts is available for racing_status
            
        # [NEW] 赛马模式：时序稳定性加分 (Opening Racing Model)
        # 传入 low 和 nlow 进行物理结构校验 (确保开盘即最低)
        low_val = float(latest.get('low', cur_close))
        nlow_val = float(latest.get('nlow', low_val))
        ts_obj.update_racing_status(cur_close, vwap, day_open, data_ts, low_p=low_val, nlow=nlow_val)
        
        racing_bonus = 0.0
        dur_raw = ts_obj.racing_duration
        if dur_raw >= 30:
            racing_bonus = 20.0 # [Dragon Class] 30分钟强力终极确认 (原15.0)
            if "★赛马30m" not in final_hint: final_hint = f"★赛马30m|{final_hint}"
        elif dur_raw >= 15:
            racing_bonus = 10.0 # [Leader Class] 15分钟退潮对抗 (原8.0)
            if "赛马15m" not in final_hint: final_hint = f"赛马15m|{final_hint}"
        elif dur_raw >= 5:
            racing_bonus = 5.0  # [Candidate Class] 5-10m 分化期 (原4.0)
            if "赛马5m" not in final_hint: final_hint = f"赛马5m|{final_hint}"
        elif dur_raw >= 2.0:     # [NEW] 2分钟预热加成，提升启动期敏感度 (120s)
            racing_bonus = 2.0
            if "★赛马启动" not in final_hint: final_hint = f"★赛马启动|{final_hint}"
        
        # 最终评分与活性修正
        # 最终分 = 瞬时分(cycle+bidding+score) + 持续动量分 + 赛马稳定性加分
        final_score = cycle_score + bidding_score + score + ts_obj.momentum_score + racing_bonus
        
        # [NEW] 高开低走 (Gap Trap) 惩罚
        # 如果高开超过 3.5% 但当前跌破均线且涨幅回撤超过高开幅度的一半
        if open_gap_pct > 3.5 and cur_close < vwap and cur_pct < open_gap_pct * 0.6:
            final_score *= 0.5 # 评分直接减半
            ts_obj.momentum_score *= 0.5
        
        # [NEW] 活性修正：如果最近 3 分钟价格没有变动且未涨停，分数大幅衰减 (针对僵尸股)
        if klines_len >= 3:
            # [P0-OPT] 直接访问 deque 末尾 3 条，避免 list() 拷贝
            last_3_set = {_klines[-3]['close'], _klines[-2]['close'], _klines[-1]['close']}
            if len(last_3_set) == 1 and cur_pct < get_limit_up_threshold(code):
                final_score *= 0.3
                ts_obj.momentum_score *= 0.8 # 动量一同衰减

        

        # [NEW] 记录个股历史得分并计算增量涨跌
        now = time.time()
        
        # 初始基准值挂载
        if ts_obj.score_anchor <= 0.0 and final_score > 0:
            ts_obj.score_anchor = final_score
            
        score_diff = final_score - ts_obj.score_anchor
        
        # [NEW] 个股切片涨幅计算与重置逻辑
        # [FIX] 跟随板块：初次发现异动时建立锚点。后续完全由 _aggregate_sectors 的周期计时器
        
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


        # [FIX] 只要达到涨停阈值，或者分数达到门槛，且是首次异动，就记录时间
        # 这样能更准确捕捉涨停瞬间，哪怕涨停时由于某些原因评分还没跟上 (例如量还没放出来)
        limit_up_price = last_close * (1.0 + get_limit_up_threshold(code) / 100.0)
        is_at_limit = cur_close >= limit_up_price - 0.005 # 容差 1 分钱
        
        if (final_score >= 5.0 or is_at_limit) and ts_obj.first_breakout_ts == 0:
            ts_obj.first_breakout_ts = data_ts

        # [UPGRADE] 活跃数据统计能力：价格变动驱动活跃数 (USER-RULE: 活跃信号总数一定是价格有变动的数据)
        current_min = int(data_ts // 60)
        price_changed = abs(cur_close - ts_obj._last_active_price) > 0.005 # 容差，确保至少有 1 分钱变动
        
        # 1. 基础活性：得分达标、分钟切换 且 价格有实质变动
        if final_score >= 5.0 and ts_obj._last_sig_min != current_min:
            if price_changed:
                ts_obj.signal_count += 1
                ts_obj._last_sig_min = current_min
                ts_obj._last_active_price = cur_close # 更新基准价格
            
        # 2. 动能活性：价格持续上涨奖励 (脉冲级活性)
        # 如果价格较上一次触发活跃时显著上涨，且强度达标，即便在同一分钟也额外奖励活跃数
        if ts_obj._last_active_price > 0 and final_score >= 3.0:
            # 强度越高，触发连续奖励的门槛越低 (如 0.3% - 0.5%)
            surge_threshold = 0.005 if final_score < 10 else 0.003 
            if cur_close > ts_obj._last_active_price * (1 + surge_threshold):
                # 限制同一分钟内只能额外奖励一次，防止 Tick 过频导致数值失真
                if ts_obj._bar_active_reward < 1:
                    ts_obj.signal_count += 1
                    ts_obj._bar_active_reward += 1
                    ts_obj._last_active_price = cur_close

        # [逻辑修正]：如果分数回落到极低水平（例如 < 2.0）且不处于涨停状态，重置异动时间
        if final_score < 2.0 and not is_at_limit:
            ts_obj.first_breakout_ts = 0

        ts_obj.score = final_score
        ts_obj.score_diff = score_diff
        ts_obj.is_untradable = is_untradable
        ts_obj.is_counter_trend = is_counter
        ts_obj.is_gap_leader = is_gap_leader  
        ts_obj.is_accumulating = is_accumulating 
        ts_obj.is_reversal = is_reversal         
        ts_obj.is_upper_band = is_upper_band     
        ts_obj.is_new_high = is_new_high         
        
        # [FIX] 无论如何确保 last_data_ts 能够推进
        if data_ts > self.last_data_ts:
            self.last_data_ts = data_ts
        elif data_ts == 0:
            self.last_data_ts = time.time()
            
        # [DONE] total_amount 已经在 ts_obj.push_kline 中通过增量维护完成


    # =========================================================
    # 内部：板块聚合
    # =========================================================


    def _aggregate_sectors(self, active_codes=None):
        """
        将高分个股聚合到板块，找龙头和跟随股。
        active_codes: 如果提供，则只更新受这些个股影响的板块。
        """
        target_sectors = None
        
        with self._lock:
            if active_codes is not None:
                codes_to_process = active_codes
                target_sectors = set()
            else:
                codes_to_process = list(self._tick_series.keys())

            # 1. 更新 snap 缓存
            for code in codes_to_process:
                ts = self._tick_series.get(code)
                if ts:
                    # [P0-OPT] __slots__ 保证字段存在，直接访问替换 getattr 防御
                    data = {
                        'score': ts.score, 'pct': ts.current_pct, 'price': ts.current_price,
                        'name': ts.name, 'category': ts.category, 'last_close': ts.last_close,
                        'first_breakout_ts': ts.first_breakout_ts,
                        'pattern_hint': ts.pattern_hint,
                        'opening_bonus': ts.opening_bonus,
                        # [PERF] 仅对高分股挂载 K 线，节省 90% 的内存拷贝开销
                        'klines': list(ts.klines) if (ts.score >= self.score_threshold and ts.klines) else [],
                        # 🚀 [PERF] 预计算 prices5，根除下游 O(N) 列表推导，注意 deque 需要先 list 化才能切片
                        'prices5': [float(k.get('close', ts.current_price)) for k in list(ts.klines)[-5:]] if ts.klines else [ts.current_price],
                        'is_untradable': ts.is_untradable,
                        'is_counter_trend': ts.is_counter_trend,
                        'is_accumulating': ts.is_accumulating,
                        'is_reversal': ts.is_reversal,
                        'signal_count': ts.signal_count,
                        'ral': ts.ral,
                        'top0': ts.top0,
                        'top15': ts.top15,
                        'score_diff': ts.score_diff,
                        'pct_diff': ts.pct_diff,
                        'price_diff': ts.price_diff,
                        'vol_ratio': ts.vol_ratio,
                        'dff': ts.dff,
                        'high_day': ts.high_day,
                        'low_day': ts.low_day,
                        'last_high': ts.last_high,
                        'last_low': ts.last_low,
                        'total_amount': ts.total_amount,
                    }
                    self._global_snap_cache[code] = data
                    
                    # 2. 同步更新增量分组 (持久化)
                    cats = ts.get_splitted_cats()
                    if target_sectors is not None:
                        target_sectors.update(cats)
                    if ts.score >= self.score_threshold:
                        for cat in cats:
                            if cat not in SECTOR_BLACKLIST and len(cat) <= 8:
                                self._sector_active_stocks_persistent[cat][code] = {'code': code, **data}
                    else:
                        for cat in cats:
                            if code in self._sector_active_stocks_persistent.get(cat, {}):
                                del self._sector_active_stocks_persistent[cat][code]
            
        # [P1-OPT] 预算 today_anchor_930 （全函数只算一次 datetime 对象）
        _now = datetime.datetime.now()
        today_anchor_930 = _now.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()

        # [P1-OPT] 市场均价增量维护：在 snap 构建循环中已计算，替代 O(N) 全量求和
        market_avg_pct = 0.0
        with self._lock:
            # [FIX] 改为浅拷贝，避免锁外遍历时被其他线程并发写入导致竞态
            snap = dict(self._global_snap_cache)
            if snap:
                _pct_total = 0.0
                _pct_count = len(snap)
                for _x in snap.values():
                    _pct_total += _x['pct']
                market_avg_pct = _pct_total / _pct_count if _pct_count > 0 else 0.0
                self.last_market_avg = market_avg_pct

        now_dt = datetime.datetime.now()
        today = now_dt.date()
        now_t = now_dt.hour * 100 + now_dt.minute
        now_ts = self.last_data_ts if self.last_data_ts > 0 else time.time()

        # [RE-ENABLED] 自动清理跨日数据，确保早盘竞价开始时看板是干净的
        if self._concept_data_date != today:
            # 如果是交易日，且处于早盘重置窗 (09:00 - 09:30)
            is_trade_day = cct.get_day_istrade_date(str(today))
            if is_trade_day:
                if 900 <= now_t <= 930:
                    logger.info(f"📅 [Detector] {today} Morning Transition Detected (Bidding window) - Resetting session data")
                    self._concept_data_date = today
                    self.daily_watchlist.clear()
                    self._sector_active_stocks_persistent.clear()
                    self.active_sectors.clear()
                    self.sector_anchors.clear()
                    # 同时也彻底清理个股评分，防止早期无 K 线导致评分不刷新的问题
                    for ts in self._tick_series.values():
                        ts.score = 0.0
                        ts.momentum_score = 0.0
                        ts.score_anchor = 0.0
                        ts.first_breakout_ts = 0.0
                        ts.pattern_hint = ""
                    self.reset_observation_anchors()
                    self.data_version += 1
                elif now_t > 930:
                    # [NEW] 如果启动时间已过早盘重置窗，直接对齐日期并重置锚点，开始今日计时
                    logger.info(f"📅 [Detector] {today} Session Sync (Post-Bidding) - Aligning date and anchors")
                    self._concept_data_date = today
                    self.reset_observation_anchors()
            else:
                # 非交易日也更新日期，防止重复检查
                self._concept_data_date = today

        # --- 更新全量 Watchlist (仅针对有变动的个股) ---
        with self._lock:
            codes_for_watchlist = active_codes if active_codes is not None else list(snap.keys())
            for code in codes_for_watchlist:
                d = snap.get(code)
                if d and d['pct'] >= get_limit_up_threshold(code) and not d['is_untradable']:
                    # [FIXED] 时间指纹过滤：09:20 之前的竞价涨停不计入重点表，防止虚假干扰
                    if now_t < 920 and not self.in_history_mode:
                        continue
                        
                    # [🚀 增强] 提取状态/原因 (优先使用 pattern_hint)
                    reason = d.get('pattern_hint', '')
                    if d['pct'] >= get_limit_up_threshold(code):
                        reason = "涨停" + (f"({reason})" if reason else "")

                    if code in self.daily_watchlist:
                        self.daily_watchlist[code]['pct'] = round(d['pct'], 2)
                        self.daily_watchlist[code]['score'] = round(d.get('score', 0), 1)
                        self.daily_watchlist[code]['reason'] = reason  # 实时更新原因
                        # [🚀 补全] 确保元数据（板块、时间）不会丢失
                        if not self.daily_watchlist[code].get('sector'):
                            self.daily_watchlist[code]['sector'] = d.get('category', '--')
                        if not self.daily_watchlist[code].get('time_str'):
                            self.daily_watchlist[code]['time_str'] = _datetime.fromtimestamp(now_ts).strftime('%H:%M:%S')
                    else:
                        # [🚀 修复] 补齐新增逻辑与核心元数据，确保面板显示“核心板块”、“触发时间”以及“状态/原因”
                        self.daily_watchlist[code] = {
                            'code': code, 
                            'name': d.get('name', code),
                            'sector': d.get('category', '--'),
                            'pct': round(d['pct'], 2), 
                            'score': round(d.get('score', 0), 1),
                            'reason': reason,
                            'time_str': _datetime.fromtimestamp(now_ts).strftime('%H:%M:%S'),
                            'ts': now_ts
                        }
            # [PERF] snap copy and new_active are now handled below in the main flow
            pass
        
        # 4. [NEW] 全局对照基准重置逻辑 (移动到循环外，每周期仅检查一次)
        now = time.time()
        
        # [🚀 ROOT-FIX] 明确初始化 new_active，防止逻辑分支导致 UnboundLocalError
        # 如果是全量刷新 (target_sectors is None)，则从空表开始构建；如果是局部刷新，则基于现有状态增量更新
        new_active = {} if target_sectors is None else self.active_sectors.copy()

        # [OPTIMIZE] 当在非交易时间不要重置基准数据，保留最后的涨跌变化
        if self.is_active_session() and not self.in_history_mode:
            if now - self.baseline_time >= self.comparison_interval:
                self.reset_observation_anchors()

                # [Added] 仅在基准重置时，强制全量重刷板块，防止锚点丢失导致的数据显示异常
                target_sectors = None
                new_active = {}
        
        # --- [PERF-OPTIMIZE] 极限性能优化：预初选活跃板块 ---
        skipped_reasons = {}  # [FIX] 初始化诊断字典，防止 NameError
        # 仅对有成员超过 score_threshold 的板块进行后续复杂的 board_score 计算
        # 这一步能过滤掉 ~90% 的僵尸板块，极大降低 CPU 负载并解决 TK 卡顿
        with self._lock:
            # [🚀 灵敏度下调] 从 1.0 下调至 0.5，确保萌芽期个股能触发板块计算
            active_stocks_global = {code for code, ts in self._tick_series.items() if ts.score >= 0.5}
            
            sectors_to_update_raw = list(target_sectors) if target_sectors is not None else list(self._sector_active_stocks_persistent.keys())
            sectors_to_update = []
            for s in sectors_to_update_raw:
                # 快速检查该板块在持久化缓存中是否有任何一只是活跃的
                stocks_raw = self._sector_active_stocks_persistent.get(s, {})
                if any(c in active_stocks_global for c in stocks_raw):
                    sectors_to_update.append(s)

        # [P0-OPT] 在锁外预取快照，极大减少锁竞争 (Holding lock only for shallow copies)
        with self._lock:
            sector_stocks_map = {k: v.copy() for k, v in self._sector_active_stocks_persistent.items()}
            # [🚀 安全性加固] 执行深层副本（拷贝 Set），防止锁外计算时受到行情线程对集合的 inplace 修改
            sector_full_map = {k: v.copy() for k, v in self.sector_map.items()}
            # snap and market_avg_pct were already handled above

        for sector in sectors_to_update:
            stocks_dict = sector_stocks_map.get(sector, {})
            if not stocks_dict:
                if sector in new_active: del new_active[sector]
                continue
            
            # [FIX] 动态过滤：即使在持久化缓存中，也要确保个股分满足当前 UI 设定的门槛
            stocks = [s for s in stocks_dict.values() if s.get('score', 0) >= self.score_threshold]
            
            if not stocks:
                if sector in new_active: del new_active[sector]
                continue
                
            for s in stocks:
                s['leader_score'] = self._calculate_leader_score(s, sector, market_avg_pct, today_anchor_930)

            stocks.sort(key=lambda x: x['leader_score'], reverse=True)
            candidate_leader = stocks[0]
            leader_code = candidate_leader['code']
            leader_pct = candidate_leader['pct']

            # [NEW] 龙头竞赛选手识别 (Race Candidates) - 对应 UI 中的“角色”精细化展示
            # 将板块内除了绝对龙头之外的强势股打上状态标签
            race_candidates = []
            for s in stocks:
                role = self._determine_role(s, leader_code, s['leader_score'])
                race_candidates.append({
                    'code': s['code'], 'name': s['name'], 'role': role,
                    'pct': round(s['pct'], 2), 'score': round(s.get('score', 0.0), 1),
                    'l_score': round(s['leader_score'], 1),
                    'pattern_hint': s.get('pattern_hint', ''), # [🚀 FIX] 补全形态暗示
                    'is_untradable': s.get('is_untradable', False),
                    'is_counter_trend': s.get('is_counter_trend', False)
                })

            # [P1-OPT] Use prefetched sector_full_map
            all_member_codes = sector_full_map.get(sector, set())
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
            
            # 聚合计算：分母判定
            actual_data_count = sum(1 for c in all_member_codes if c in snap)
            if actual_data_count < 1:
                # 没有任何成员在 snap 中有数据，跳过
                continue
            
            # [FIX] 联动分析与强度综合评分：分母应使用实际参与统计的样本数，而非板块全员数
            # 否则在局部更新或数据源不全时，avg_pct 会被严重稀释
            follow_ratio = active_member_count / actual_data_count
            avg_pct = total_pct / actual_data_count
            
            # [REFINED] 噪点过滤：成员数过少（少于 3 只股，原为 4）的概念通常是虚假的，剔除。
            if len(all_member_codes) < 3:
                skipped_reasons[sector] = f"too_few_members({len(all_member_codes)})"
                if sector in new_active: del new_active[sector]
                continue

            # [NEW] 提前计算 board_score，避免后续标签逻辑出现 UnboundLocalError
            # 计算群体热度加成
            s_top0_sum = sum(1 for s in stocks if s.get('top0', 0) > 0)
            s_top15_sum = sum(1 for s in stocks if s.get('top15', 0) > 0)
            hotness_multiplier = min(2.0, 1.0 + (s_top0_sum * 0.1) + (s_top15_sum * 0.03))

            # [REFINED] 极严格过滤：模仿 TK 去弱留强逻辑
            # 以群体效应 (avg_pct * follow_ratio) 为核心依据。
            tk_correlation_score = avg_pct * follow_ratio * 4.0 

            # 最终板分公式：(板块均值加权 + 联动比例加权 + 个股强势溢价) * 热度系数
            board_score = (avg_pct * 0.8 + follow_ratio * 4.0 + (candidate_leader['score'] * 0.05) + tk_correlation_score) * hotness_multiplier

            # 提取龙头元数据供后续使用
            tags = []
            l_data = candidate_leader
            l_ts = self._tick_series.get(leader_code)

            if l_ts:
                # --- 安全获取 open ---
                day_open = l_ts.open_price
                if day_open is None:
                    if l_ts.klines:
                        first_k = next(iter(l_ts.klines), {})
                        day_open = first_k.get('open')
                
                # --- 安全获取 last_close ---
                last_close = l_ts.last_close

                # --- 强制数值化（核心修复） ---
                if not isinstance(day_open, (int, float)):
                    day_open = 0.0
                if not isinstance(last_close, (int, float)):
                    last_close = 0.0

                # --- 逻辑判断 ---
                if last_close > 0 and (day_open - last_close) / last_close > 0.03:
                    tags.append("高开")

                if day_open > 0 and isinstance(l_data.get('price'), (int, float)) and l_data.get('price') > day_open:
                    tags.append("高走")
                
                # 记录竞价情绪
                now_t = int(time.strftime("%H%M"))
                if 920 <= now_t <= 925:
                    if leader_pct > 3.0: tags.append("竞价抢筹")
                    elif leader_pct < -3.0: tags.append("竞价恐慌")
                if 1300 <= now_t <= 1310: tags.append("午后异动")
                
                # [NEW] 主流延续性标签：如果龙头是昨日选股器选出的强势股，且板块强势
                if leader_code in self.stock_selector_seeds and board_score > 5.5:
                    tags.append("🔥 延续")

            # 基础门槛：下调门槛，增强对竞价初期及异动概念的捕捉灵敏度
            # 原条件: follow_ratio < 0.15 and avg_pct < 1.5
            if follow_ratio < 0.10 and avg_pct < 1.0:
                 skipped_reasons[sector] = f"weak_momentum(pct={avg_pct:.1f}, ratio={follow_ratio:.2f})"
                 new_active.pop(sector, None)
                 continue
            
            # 最终入榜门槛校验
            if board_score < self.sector_score_threshold:
                 skipped_reasons[sector] = f"low_board_score({board_score:.1f} < {self.sector_score_threshold})"
                 new_active.pop(sector, None)
                 continue
            
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
            leader_concepts = [c.strip() for c in _RE_CAT_SPLIT.split(l_data['category']) if c.strip() and len(c.strip()) <= 8]
            if leader_concepts:
                for concept in leader_concepts:
                    if concept == sector: continue
                    members = self.sector_map.get(concept)
                    if not members or len(members) < 3: continue
                    # [P0-OPT] snap 已经是锁外快照，且 members 来自 sector_full_map 快照
                    members_in_snap = [mc for mc in members if mc in snap]
                    if not members_in_snap: continue
                    f_count = sum(1 for mc in members_in_snap if (1 if snap[mc]['pct']>0 else -1) == leader_sign)
                    total_c_pct = sum(snap[mc]['pct'] for mc in members_in_snap if (1 if snap[mc]['pct']>0 else -1) == leader_sign)
                    c_follow = f_count / len(members_in_snap)
                    c_avg_pct = total_c_pct / len(members_in_snap)
                    if c_follow > 0.4: linked_concepts.append({
                        'concept': concept, 
                        'follow_ratio': round(c_follow, 2),
                        'avg_pct': round(c_avg_pct, 2)
                    })

            # [REM] 移除此处冗余的基准重置逻辑，已由外层校验覆盖。
                 
            # [REM] 移除此处冗余的基准重置逻辑，已在循环外部(Line 1054) 统一处理。
            # 保持逻辑单一职责，避免在循环内部重复刷新全局状态。

            
            if sector not in self.sector_anchors:
                self.sector_anchors[sector] = board_score
                
            score_diff = board_score - self.sector_anchors[sector]
            
            anchor = self.sector_anchors[sector]
            staged_diff = board_score - anchor

            new_active[sector] = {
                'sector': sector, 'score': round(board_score, 2), 'tags': " ".join(tags),
                'ts': time.time(), # [FIX] 添加时间戳，用于 GC
                'score_diff': round(score_diff, 2),        # 对比固定时长(30m)的变动
                'staged_diff': round(staged_diff, 2),      # 阶段性变动 (10分阈值重置)
                'follow_ratio': round(follow_ratio, 2), 'leader': leader_code,
                'leader_name': l_data['name'], 'leader_pct': round(l_data['pct'], 2),
                'leader_pct_diff': round(l_data.get('pct_diff', 0.0), 2),
                'leader_price': l_data.get('price', 0.0),
                'leader_klines': list(l_ts.klines)[-35:] if (l_ts and l_ts.klines) else (self.realtime_service.get_minute_klines(leader_code, n=35) if self.realtime_service else []),
                'leader_last_close': l_data.get('last_close', 0),
                'leader_high_day': l_data.get('high_day', 0),
                'leader_low_day': l_data.get('low_day', 0),
                'leader_last_high': l_data.get('last_high', 0),
                'leader_last_low': l_data.get('last_low', 0),
                'leader_first_ts': l_data['first_breakout_ts'],
                'race_candidates': race_candidates,
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

        # --- [NEW] 虚拟板块注入：🔔 实时报警 (SBC Pattern Tracker) ---
        if self.realtime_service and self.realtime_service.emotion_tracker:
            registry = getattr(self.realtime_service.emotion_tracker, '_sbc_signals_registry', {})
            if registry:
                sbc_codes = list(registry.keys())
                # 提取 snap 中的最新行情数据
                sbc_stocks = []
                for c in sbc_codes:
                    if c in snap:
                        # [FIX] 增强鲁棒性：确保 name 字段始终存在 (registry 可能缺失 name)
                        node = {**snap[c], **registry[c]}
                        if not node.get('name'):
                            node['name'] = snap[c].get('name') or c
                        sbc_stocks.append(node)
                
                if sbc_stocks:
                    # 按时间倒序排列 (最新触发的在最前) 或按评分排序
                    sbc_stocks.sort(key=lambda x: x.get('ts', 0), reverse=True)
                    
                    v_leader = sbc_stocks[0]
                    v_sector = "🔔 实时报警"
                    v_board_score = max(5.0, sum(s['score'] for s in sbc_stocks) / len(sbc_stocks))
                    
                    # 虚拟板块锚点保护
                    if v_sector not in self.sector_anchors:
                        self.sector_anchors[v_sector] = v_board_score
                    
                    new_active[v_sector] = {
                        'sector': v_sector, 'score': round(v_board_score, 2), 'tags': "🚀 实时异动",
                        'ts': time.time(),
                        'score_diff': round(v_board_score - self.sector_anchors[v_sector], 2),
                        'staged_diff': 0.0,
                        'follow_ratio': 1.0, # 虚拟板块始终保持 100% 联动
                        'leader': v_leader['code'],
                        'leader_name': v_leader['name'],
                        'leader_pct': round(v_leader['pct'], 2),
                        'leader_price': v_leader.get('price', 0.0),
                        'leader_high_day': v_leader.get('high_day', 0),
                        'leader_last_close': v_leader.get('last_close', 0),
                        'race_candidates': [],
                        'followers': [
                            {
                                'code': s['code'], 'name': s['name'], 'pct': s['pct'],
                                'score': s.get('score', 0.0), 'price': s.get('price', 0.0),
                                'first_ts': s.get('ts', 0), 'pattern_hint': 'SBC',
                                'klines': s.get('klines', []),
                                'last_close': s.get('last_close', 0.0)
                            } for s in sbc_stocks # 这里展示全部预警股
                        ],
                        'linked_concepts': []
                    }

        with self._lock:
            self.active_sectors = new_active
            self.data_version += 1
            
        # [DEBUG] 打印高评分但被过滤的板块（辅助诊断为何板块缺失）
        if logger.isEnabledFor(logging.DEBUG) and skipped_reasons:
            interesting = {s: r for s, r in skipped_reasons.items() if "low_board_score" in r and float(r.split('(')[1].split(' ')[0]) > 3.0}
            if interesting:
                logger.debug(f"ℹ️ [Detector] Potential High-score Sectors filtered: {interesting}")

    def _gc_old_sectors(self):
        """清理长时间不活跃的板块结果"""
        now = time.time()
        # [REFINED] 动态获取 sleep 时间，如果 CFG 没变，尝试从文件重新加载或使用合理默认值
        # 考虑到 cct.CFG 可能不会实时响应 global.ini 变化，这里我们强制获取最新
        try:
            limit = float(getattr(cct.CFG, 'duration_sleep_time', 120.0)) if cct else 120.0
        except:
            limit = 60.0
            
        # 允许竞价期间更快速刷新 (最低 1s)
        limit = max(60.0, limit)
        
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
    # [NEW] [PERF] 增加缓存机制：如果 DataFrame 内容没变，跳过重算
    def _rebuild_sector_map(self, df: pd.DataFrame):
        """从 df_all 重建 sector → set(code) 索引 (带缓存保护)"""
        if df is None or df.empty or 'category' not in df.columns:
            return
            
        # 使用内容指纹判定是否需要重算 (仅在全量时有效，增量始终执行以防漏网)
        if len(df) > 3000:
            # 这里的 logic 主要是防抖
            current_tag = f"{len(df)}_{df.index[0]}_{df.index[-1]}"
            if getattr(self, '_last_sector_rebuild_tag', '') == current_tag:
                return
            self._last_sector_rebuild_tag = current_tag
            
        self._do_rebuild_sector_map(df)

    def _do_rebuild_sector_map(self, df: pd.DataFrame):
        """真正的重建逻辑"""
        new_map: Dict[str, Set[str]] = defaultdict(set)
        for row in df.itertuples(index=False):
            # [🚀 格式规范化] 强制提取 6 位数字代码，剔除后缀(如 .SH/.SZ)，防止同一只股票以不同格式重复入表
            raw_code = str(getattr(row, 'code', '')).strip()
            code = _RE_NON_DIGIT.sub('', raw_code)
            if len(code) < 6 and code.isdigit(): code = code.zfill(6)
            elif len(code) > 6: code = code[-6:] # 仅取后 6 位，对齐全系统 A 股标准
            
            if not code or code == '000000' or len(code) != 6:
                continue

            # [🚀 SANITIZATION] 过滤空名称、占位符名称等无效个股
            name = str(getattr(row, 'name', '')).strip()
            if not name or name in ['', 'nan', 'NaN', 'None', 'null', 'δ֪', '未知', code]:
                continue

            cat = str(getattr(row, 'category', ''))
            if not cat or cat == 'nan':
                continue
            # [🚀 切分去重] 确保单行内重复的分类不产生多次 add 动作
            for p in {c.strip() for c in _RE_CAT_SPLIT.split(cat) if c.strip()}:
                new_map[p].add(code)
        
        # [ROOT-FIX] 稳健更新策略：判定是全量市场数据还是局部更新
        is_full_market = len(df) > 3000
        
        if is_full_market:
            with self._lock:
                # 差异比对逻辑（仅在全量更新时应用）
                if self.sector_map and len(new_map) > 0:
                    diff_ratio = len(set(new_map.keys()) ^ set(self.sector_map.keys())) / max(len(self.sector_map), 1)
                    # 如果板块名单变动超过 80%，重置持久化缓存
                    if diff_ratio > 0.8:
                        logger.info(f"♻️ [Detector] Market context shifted (diff={diff_ratio:.1f}), resetting persistent cache")
                        self._sector_active_stocks_persistent.clear()
                
                self.sector_map = new_map

            logger.debug(f"📊 Sector map fully rebuilt from {len(df)} stocks (Sectors: {len(self.sector_map)})")
        else:
            # 局部更新逻辑：仅更新 df 中涉及代码的映射，不清理其他代码的映射
            with self._lock:
                if not self.sector_map:
                    self.sector_map = new_map
                else:
                    # 1. 提取当前 df 涉及的所有代码
                    incoming_codes = set()
                    for p_set in new_map.values():
                        incoming_codes.update(p_set)
                    
                    # 2. 将这些代码从 global sector_map 中由于旧归属引起的集合中剥离
                    for sector, members in self.sector_map.items():
                        # 这是一个 inplace 操作
                        members.difference_update(incoming_codes)
                    
                    # 3. 注入新的映射
                    for sector, members in new_map.items():
                        self.sector_map[sector].update(members)
                    
                    # 4. 清理空板块
                    empty_secs = [s for s, m in self.sector_map.items() if not m]
                    for s in empty_secs:
                        del self.sector_map[s]
            
            logger.debug(f"🧩 Sector map incrementally updated for {len(df)} stocks (Total Sectors: {len(self.sector_map)})")

    # =========================================================
    # 时间窗口判断（只在竞价/尾盘生效）
    # =========================================================

    def is_active_session(self) -> bool:
        """全天查看模式：主要交易时间内都就行（略去时间窗口限制）。"""
        if getattr(self, 'in_history_mode', False) or getattr(self, 'simulation_mode', False):
            # [FIX] 如果是模拟回测，则根据数据的时间戳判定，而不是系统墙上时间
            if getattr(self, 'last_data_ts', 0) > 0:
                dt = datetime.datetime.fromtimestamp(self.last_data_ts)
                hm = dt.hour * 100 + dt.minute
                return 915 <= hm <= 1500
            return True
            
        now = datetime.datetime.now()
        hm = now.hour * 100 + now.minute
        return 915 <= hm <= 1500
