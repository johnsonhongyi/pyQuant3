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
# from signal_bus import SignalBus
import os
import gzip
import numpy as np
from JohnsonUtil import commonTips as cct
from linkage_service import get_link_manager

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
    
    from datetime import datetime
    
    for k in k_list:
        d = k.as_dict() if hasattr(k, 'as_dict') else k
        if not d: continue
        
        # 优化 1: 避免 pandas，利用 fromisoformat (Python 3.7+)
        dt = d.get('datetime', d.get('time'))
        if not dt: continue
        
        try:
            if isinstance(dt, str):
                # 兼容 "YYYY-MM-DD HH:MM:SS" 或 ISO 格式
                if len(dt) > 10 and dt[10] == ' ': 
                    ts = int(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S').timestamp())
                else:
                    ts = int(datetime.fromisoformat(dt).timestamp())
            elif hasattr(dt, 'timestamp'):
                ts = int(dt.timestamp())
            else:
                ts = int(dt)
            
            if base_ts == 0:
                base_ts = ts
            
            # 优化 2: 减少冗余的 round/float cast
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
    from datetime import datetime
    out = []

    # 2. 兼容 0408_v1 结构 {b, d:[[..]]}
    if 'd' in compressed:
        compact_data = compressed['d']
        for item in compact_data:
            if not isinstance(item, (list, tuple)) or len(item) < 3: continue
            ts = base_ts + item[0] * 60
            dt_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            out.append({'datetime': dt_str, 'time': ts, 'close': item[1], 'volume': item[2]})
        return out

    # 3. 新的 Columnar 格式 {b, o:[], c:[], v:[]}
    offsets = compressed.get('o', [])
    closes = compressed.get('c', [])
    volumes = compressed.get('v', [])
    
    for i in range(len(offsets)):
        ts = base_ts + offsets[i] * 60
        dt_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
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
                 'racing_start_ts', 'last_stable_ts', 'racing_duration', 'signal_count', '_last_sig_min')

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

    def __init__(self, realtime_service: Optional["DataPublisher"] = None, simulation_mode: bool = False, lazy_load: bool = False, silent_mode: bool = False):
        # ---- 数据服务 ----
        self.realtime_service = realtime_service
        self.simulation_mode = simulation_mode
        self._is_ready = False if lazy_load else True
        self._loading_thread = None
        self.silent_mode = silent_mode # [NEW] 集成模式下抑制重复日志打印

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
        self.sector_score_threshold: float = 5.0
        self.last_data_ts = 0.0

        # key=code, val={name, sector, pct, time_str, reason, reason, pattern_hint, release_risk}
        self.daily_watchlist: Dict[str, Dict[str, Any]] = {}
        self.enable_log = True # 是否允许向控制台/文件打印重点监控日志
        
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
        self._concept_data_date: Optional[datetime.date] = None
        self._concept_first_phase_done = False
        self._concept_second_phase_done = False
        
        # [Tier 2] 增量缓存
        self._global_snap_cache: Dict[str, Dict[str, Any]] = {}
        self._sector_active_stocks_persistent: Dict[str, Dict[str, Any]] = defaultdict(dict)
        
        # [NEW] 市场整体数据缓存
        self.last_market_avg = 0.0

        # [NEW] 模式保护与参数
        self.in_history_mode = False
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

        # [THREAD-SAFETY] 防御性 copy：防止调用方在其他线程中修改或释放底层 C 数组
        df_all = df_all.copy()

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
            
            row_data = row._asdict()
            name = str(row_data.get('name', code))

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

    def update_scores(self, active_codes=None, force: bool = False):
        """
        主入口：计算个股分值并聚合板块。
        active_codes: 如果提供，则执行增量更新 (O(Delta) 复杂度)，极度节省性能。
        force: 是否强制全量计算 (通常用于每 5 分钟的全局对齐)。
        """
        # [FIX] 跨日重置必须在所有评估逻辑之前执行
        self._check_day_switch(datetime.datetime.now())

        with self._lock:
            if active_codes is not None and not force:
                # [INCREMENTAL] 增量模式：仅对当前变动的代码进行评估
                codes = [c for c in active_codes if c in self._tick_series]
            else:
                # [FULL-SWEEP] 全量模式
                codes = list(self._tick_series.keys())
                
        # [PERF] 针对 5000+ 品种，_evaluate_code 已优化为纯数值计算
        for code in codes:
            self._evaluate_code(code)
        
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
                ts.pattern_hint = ""           # 清空形态描述
                ts.klines.clear()              # 清空分时数据（保留 deque 结构，避免破坏 maxlen）
                
        # 3. 时间锚点重置，作为后续计算“异动了多久”的基准
        self.baseline_time = current_dt.timestamp()
        self.data_version += 1 # 联动 UI 全量重传

    def reconstruct_all_from_cache(self):
        """[NEW] 为历史模式提供的全量算法重映射，用于在模式切换时立即同步 UI"""
        if not getattr(self, 'in_history_mode', False): return
        
        logger.info("🔄 [Detector] 正在为全部板块重新映射算法逻辑...")
        from collections import defaultdict
        code_sector_map = defaultdict(list)
        for code, snap in self._global_snap_cache.items():
            cats = [c.strip() for c in re.split(r'[;；,，/\- ]', str(snap.get('category', ''))) if c.strip()]
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

    def save_persistent_data(self, force=False):
        """保存当前个股得分和板块强度到磁盘 (原子化强化版)"""
        if self.in_history_mode:
            logger.debug("[Detector] Skip save in history mode.")
            return

        # [REFINED] 强化交易日校验
        is_trade_day = cct.get_trade_date_status()
        # 🛡️ 二重校验：补齐可能的 GlobalValues 缓存刷新不及时问题
        if not cct.get_day_istrade_date():
            is_trade_day = False

        if not force and not is_trade_day:
            # logger.debug("[Detector] Skip save: Not a trade date.")
            return

        # [NEW] [TIME-CHECK] 16:00 以后停止自动存盘，防止盘后无效 IO 或过时的全量序列化占用资源
        # 此时数据已基本定型，无需每分钟保存一次
        now = datetime.datetime.now()
        if not force:
            if now.hour >= 16:
                return
            if is_trade_day:
                if now.hour < 9 or (now.hour == 9 and now.minute < 40):
                    # logger.debug(f"[Detector] Skip save: Morning noise protection (Before 09:40).")
                    return

        # [NEW] [QUALITY-PROTECTION] 盘后或非交易日的数据质量比对保护
        main_path = self._get_persistence_path()
        if os.path.exists(main_path):
            try:
                mtime = os.path.getmtime(main_path)
                f_dt = datetime.datetime.fromtimestamp(mtime)
                
                # 情况 A：盘后且已有今日数据
                # 情况 B：非交易日且已有近期(2天内)数据
                # 如果当前 Session 信号极少，说明是误动或新开机，严禁覆盖
                if now.hour >= 15 or not is_trade_day:
                    current_sig_count = len([ts for ts in self._tick_series.values() if ts.score > 0])
                    # 磁盘文件较新且内存几乎无数据
                    if current_sig_count < 5 and (now - f_dt).days <= 2:
                        logger.info(f"🛡️ [Detector] Session empty ({current_sig_count} sigs). Protecting existing data from {f_dt.strftime('%m-%d %H:%M')}.")
                        return
            except Exception as e:
                logger.debug(f"Persistence quality check error: {e}")

        # [NEW] [CONTENT-CHECK] 如果完全没有板块数据，通常意味着是无效会话，不存盘
        if not force and not self.active_sectors:
            # logger.debug("[Detector] Skip save: No active sector data recorded.")
            return

        try:
            # [Data Preparation ...]
            # [OPTIMIZED] 深度清理数据，严禁重叠存储 K 线
            def _clean_data(obj):
                if isinstance(obj, dict):
                    # 彻底剔除所有形式的 K 线数据，仅在 meta_data 中保留一份
                    return {k: _clean_data(v) for k, v in obj.items() if not k.endswith('klines')}
                elif isinstance(obj, list):
                    return [_clean_data(item) for item in obj]
                return obj

            # [COLUMNAR-METADATA] 使用列式存储减少 Key 重复开销
            significant_stocks = {code: s for code, s in self._tick_series.items() if (s.score >= 0.1)}
            
            # [ENHANCED-COVERAGE] 扩充采集范围，包含重点表和所有反馈列表中的个股，确保复盘不空白
            relevant_codes = set(significant_stocks.keys()) | set(self.daily_watchlist.keys()) | set(self.stock_selector_seeds.keys())
            for sinfo in self.active_sectors.values():
                relevant_codes.add(sinfo.get('leader'))
                for f in sinfo.get('followers', []):
                    relevant_codes.add(f.get('code'))
            
            codes_list = [c for c in relevant_codes if c]
            meta_cols = {
                'code': codes_list,
                'n': [], 'ph': [], 'c': [], 'lc': [], 'op': [], 'hd': [], 'ld': [], 
                'lh': [], 'll': [], 'np': [], 'fb': [], 'rl': [], 'iu': [], 'ic': [], 
                'p': [], 's': [], 'rs': [], 'sc': [], # [NEW] 增加 rs 赛马时间, sc 信号计数
                'k': []
            }
            for code in codes_list:
                ts = self._tick_series.get(code)
                if ts:
                    meta_cols['n'].append(ts.name)
                    meta_cols['ph'].append(getattr(ts, 'pattern_hint', ''))
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
                    meta_cols['rs'].append(round(ts.racing_start_ts, 1)) # [NEW]
                    meta_cols['sc'].append(ts.signal_count) # [NEW]
                    meta_cols['k'].append(compress_klines(ts.klines))
                else:
                    for k in meta_cols: 
                        if k != 'code': meta_cols[k].append(None)

            # [NEW] 存盘前自动更新今日的 Top 2 到追踪历史库
            self._update_daily_dragon_top2()

            data = {
                'data_date': self._last_data_date or datetime.datetime.now().strftime('%Y-%m-%d'),
                'timestamp': round(time.time(), 2),
                'stock_scores': {code: round(ts.score, 2) for code, ts in significant_stocks.items()},
                'momentum_scores': {code: round(ts.momentum_score, 2) for code, ts in significant_stocks.items() if ts.momentum_score > 0},
                'sector_data': {name: _clean_data(info) for name, info in self.active_sectors.items() if info.get('score', 0) > 0},
                'stock_score_anchors': {code: round(ts.score_anchor, 2) for code, ts in self._tick_series.items() if ts.score_anchor != 0.0},
                'baseline_time': round(self.baseline_time, 2),
                'sector_anchors': {name: round(s, 2) for name, s in self.sector_anchors.items()},
                'stock_price_anchors': {code: round(ts.price_anchor, 4) for code, ts in self._tick_series.items() if ts.price_anchor > 0},
                'watchlist': _clean_data(self.daily_watchlist),
                'stock_selector_seeds': self.stock_selector_seeds,
                'meta_cols': meta_cols,
                'dragon_3day_history': self.dragon_3day_history
            }
            
            sd_count = len(data.get('sector_data', {}))
            ss_count = len(significant_stocks)
            wl_count = len(data.get('watchlist', {}))
            
            # [FIX] 如果是强制保存 (force) 则跳过内容检查；否则至少需要板块或重点股数据才存盘
            if not force:
                if sd_count == 0 and ss_count == 0 and wl_count == 0:
                    # logger.debug("ℹ️ [Detector] No active signals to save (skipped).")
                    return

            # ⭐ [C-Reinforcement] 原子化写入：先写临时文件，然后 os.replace
            import zlib
            def atomic_save(target_path, data_dict):
                def np_handler(obj):
                    if isinstance(obj, (np.integer, np.int32, np.int64)):
                        return int(obj)
                    if isinstance(obj, (np.floating, np.float32, np.float64)):
                        return float(obj)
                    if isinstance(obj, np.ndarray):
                        return obj.tolist()
                    return str(obj) # Fallback

                temp_path = target_path + f".{os.getpid()}.tmp"
                try:
                    # 性能与体积平衡：使用 separators 消除空格，并用 zlib 6级 压缩
                    json_str = json.dumps(data_dict, ensure_ascii=False, default=np_handler, separators=(',', ':'))
                    compressed = zlib.compress(json_str.encode('utf-8'), level=6)
                    
                    with open(temp_path, 'wb') as f:
                        f.write(compressed)
                    
                    if os.path.exists(target_path):
                        try: os.remove(target_path)
                        except: pass
                    
                    os.replace(temp_path, target_path)
                    return True
                except Exception as e:
                    if os.path.exists(temp_path):
                        try: os.remove(temp_path)
                        except: pass
                    raise e

            main_path = self._get_persistence_path()
            if atomic_save(main_path, data):
                today_str = datetime.datetime.now().strftime('%Y%m%d')
                snapshot_path = self._get_persistence_path(snapshot_date=today_str)
                if os.path.normpath(main_path) != os.path.normpath(snapshot_path):
                    import shutil
                    try:
                        os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
                        shutil.copy2(main_path, snapshot_path)
                        logger.info(f"📸 [Detector] Snapshot copied to {snapshot_path}")
                    except Exception as e:
                        logger.warning(f"Failed to copy snapshot: {e}")
                        atomic_save(snapshot_path, data)

            logger.info(f"💾 [Detector] Session data saved to {main_path} ({ss_count} stocks, {sd_count} sectors)")
            if snapshot_path != main_path:
                logger.info(f"📸 [Detector] Snapshot saved to {snapshot_path}")
        except Exception as e:
            logger.error(f"❌ [Detector] Persistence save failed: {e}")

    def load_persistent_data(self):
        """启动时从磁盘恢复得分和强度"""
        try:
            path = self._get_persistence_path()
            if not os.path.exists(path):
                return

            # [REFINED] 跨日保护逻辑：如果是今日启动且已经有内容，严禁触发 is_cross_day 清空
            mtime = os.path.getmtime(path)
            file_dt = datetime.datetime.fromtimestamp(mtime)
            file_date_str = file_dt.strftime('%Y-%m-%d')
            now_dt = datetime.datetime.now()
            today_str = now_dt.strftime('%Y-%m-%d')
            
            is_cross_day = (file_date_str != today_str)

            is_expired = False
            # [NEW] 虽然未过期，但我们仍需记录文件的日期，以便之后进行跨日重置判断
            self._concept_data_date = file_dt.date()
            
            try:
                # 获取从文件日期到今天的交易日列表
                trade_days = cct.a_trade_calendar.get_trade_days_interval(file_date_str, today_str)
                
                # 1. 如果中间隔了至少一个完整的交易日，彻底过期
                if len(trade_days) > 2:
                    is_expired = True
                # 2. 如果是相邻交易日（如周五到周一，或昨日到今日）
                elif len(trade_days) == 2:
                    if cct.get_day_istrade_date(today_str):
                        # 09:15 后（竞价已结束）且还在早盘，或者其他交易时段启动，认为过期数据需彻底隔离
                        # [FIX] 增加保护：如果在早盘启动，认为是跨日数据需清理；如果是收盘后启动（做复盘），保留
                        if now_dt.hour < 15:
                            if now_dt.hour >= 10 or (now_dt.hour == 9 and now_dt.minute >= 15):
                                is_expired = True
                    # 如果今日不是交易日，保留上一交易日数据继续分析
                # 3. 如果是同一个交易日重启 (len == 1)，绝不标记为跨日或过期
                elif len(trade_days) == 1:
                    is_cross_day = False
                    is_expired = False
            except Exception as e:
                # 兜底逻辑
                if time.time() - mtime > 15.5 * 3600:
                    is_expired = True
                logger.debug(f"[Detector] 交易日历判断异常: {e}")

            if is_expired:
                logger.info(f"📅 [Detector] 持久化数据已过期 ({file_date_str} -> {today_str})，跳过加载。")
                return

            # [COMPRESSION-ADAPTIVE] 支持 zlib 或 gzip
            import zlib
            with open(path, 'rb') as f:
                raw_data = f.read()
            
            try:
                # 优先尝试 zlib 解压
                decompressed = zlib.decompress(raw_data).decode('utf-8')
                data = json.loads(decompressed)
            except Exception:
                # 兼容旧版本 gzip 格式
                try:
                    import gzip
                    decompressed = gzip.decompress(raw_data).decode('utf-8')
                    data = json.loads(decompressed)
                except Exception as e:
                    logger.error(f"[Detector] Decompression failed: {e}")
                    return

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
                
            # [FIXED v2] 最终防层：逐条验证 watchlist 每个条目的 trigger_ts
            # 无论 is_cross_day / mtime / 交易日历是否准确，只要触发时间早于今日零点，一律丢弃。
            # 这可以防止启动后文件日期被“污染”为今日但内容仍是昨日的情况。
            if is_cross_day:
                logger.info(f"📅 [Detector] 跨日加载：清空昨日重点表与板块评分，仅保留元数据。")
                self.daily_watchlist = {}          # 重点表清空
                self.active_sectors = {}           # 板块汇总清空
                self.sector_anchors = {}           # 板块锚点清空
                # 个股状态全量复位
                for ts in self._tick_series.values():
                    ts.score = 0.0
                    ts.momentum_score = 0.0
                    ts.score_anchor = 0.0
                    ts.first_breakout_ts = 0.0
                    ts.klines.clear()
            else:
                # 同日重启：仍需防范性验证 trigger_ts
                raw_watchlist = data.get('watchlist', {})
                # 今日零点时间戳
                today_midnight_ts = datetime.datetime.combine(now_dt.date(), datetime.time.min).timestamp()
                valid_watchlist = {}
                stale_count = 0
                for code, entry in raw_watchlist.items():
                    ts_entry = entry.get('trigger_ts', 0)
                    # 尝试从 time 字符串读取备份（兼容性处理）
                    if ts_entry <= 0 and 'time' in entry:
                        try:
                            # 期望格式 HH:MM:SS，如果包含日期则优先
                            t_str = entry['time']
                            if '-' in t_str: 
                                # 包含日期如 0408-15:00，这必然是昨日
                                ts_entry = 0 
                            else:
                                # 仅时间，默认为今日（保守处理）
                                ts_entry = today_midnight_ts + 1
                        except: pass
                    
                    if ts_entry >= today_midnight_ts:
                        valid_watchlist[code] = entry
                    else:
                        stale_count += 1
                
                if stale_count > 0:
                    logger.warning(f"🧹 [Detector] 从当日文件中剔除 {stale_count} 条昨日残留记录。")
                self.daily_watchlist = valid_watchlist

            # [NEW] 恢复种子股状态，确保实盘重启后种子奖分 (+15) 生效
            self.stock_selector_seeds = data.get('stock_selector_seeds', {})

            # [RECONSTRUCT-METADATA] 处理新的列式存储格式
            meta_cols = data.get('meta_cols', {})
            if meta_cols and 'code' in meta_cols:
                codes = meta_cols['code']
                for i, code in enumerate(codes):
                    if not code: continue
                    if code not in self._tick_series:
                        self._tick_series[code] = TickSeries(code)
                    ts = self._tick_series[code]
                    
                    # 映射函数简化代码
                    def _get(key, default):
                        val = meta_cols.get(key, [])
                        return val[i] if i < len(val) and val[i] is not None else default

                    ts.name = _get('n', ts.name)
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
                    ts.score = _get('s', ts.score) # [NEW] 情绪分恢复
                    ts.ral = _get('rl', ts.ral)
                    ts.is_untradable = bool(_get('iu', ts.is_untradable))
                    ts.is_counter_trend = bool(_get('ic', ts.is_counter_trend))
                    ts.racing_start_ts = _get('rs', ts.racing_start_ts) # [NEW] 恢复赛马时间
                    ts.signal_count = _get('sc', 0)
                    if ts.signal_count > 0:
                        ts._last_sig_min = int(ts.first_breakout_ts // 60) if ts.first_breakout_ts > 0 else 0
                    ts.last_stable_ts = ts.racing_start_ts if ts.racing_start_ts > 0 else 0.0
                    
                    # [NEW] 同步更新全量缓存，确保 UI 在 Tick 到达前就能显示恢复出的分值与涨幅
                    self._global_snap_cache[code] = {
                        'code': code, 'name': ts.name, 'pct': _get('p', 0.0),
                        'score': ts.score,
                        'price': ts.now_price, 'last_close': ts.last_close,
                        'category': ts.category, 'first_breakout_ts': ts.first_breakout_ts,
                        'klines': decompress_klines(_get('k', [])),
                        'is_untradable': ts.is_untradable, 'is_counter_trend': ts.is_counter_trend,
                        'pattern_hint': ts.pattern_hint, 'vol_ratio': getattr(ts, 'vol_ratio', 0.0),
                        'signal_count': ts.signal_count
                    }
                    
                    # 价格锚点与涨幅 (虽然 ts.current_pct 是属性，但 ts.now_price 恢复后会自愈，
                    # 且 meta_cols 中有 'p' 列供 UI 层直接展示)
                    
                    # 恢复 K 线
                    klines_data = _get('k', None)
                    if klines_data:
                        ts.klines.clear()
                        for k in decompress_klines(klines_data):
                            ts.push_kline(k)
            else:
                # 兼容旧的 meta_data (dict 格式)
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
                    
                    ts.klines.clear()
                    for k in decompress_klines(m.get('klines', [])): # [OPTIMIZED] 解压加载
                        ts.push_kline(k)
            
            logger.info(f"♻️ [Detector] 会话数据已恢复: {len(self._tick_series)} 只个股, {len(self.active_sectors)} 个板块")
            # [FIX] 跨日时将日期标记设为今日，防止 _check_day_switch 再次触发重置
            # 同日重启时，优先使用 JSON 内嵌的 data_date，避免 os mtime 被带偏
            if is_cross_day:
                self._last_data_date = today_str
                logger.info(f"📅 [Detector] 跨日加载完成，日期标记已更新为今日 ({today_str})")
            else:
                self._last_data_date = data.get('data_date', file_date_str)
            self._concept_data_date = file_dt.date()
        except Exception as e:
            logger.error(f"❌ [Detector] 加载会话数据失败: {e}")
        self._gc_old_sectors()
        # [NEW] 启动或跨日载入后，初始化三日跟踪历史
        self._init_dragon_3day_tracker()

    def load_from_snapshot(self, filepath: str) -> bool:
        """从指定的快照文件恢复数据，用于历史复盘"""
        try:
            if not os.path.exists(filepath):
                logger.error(f"Snapshot file not found: {filepath}")
                return False

            # [COMPRESSION-ADAPTIVE] 支持 zlib 或 gzip
            import zlib
            with open(filepath, 'rb') as f:
                raw_data = f.read()
            
            try:
                decompressed = zlib.decompress(raw_data).decode('utf-8')
                data = json.loads(decompressed)
            except Exception:
                try:
                    import gzip
                    decompressed = gzip.decompress(raw_data).decode('utf-8')
                    data = json.loads(decompressed)
                except Exception as e:
                    logger.error(f"[Detector] Snapshot decompression failed: {e}")
                    return False

            with self._lock:
                # 1. 重置当前状态
                self._tick_series.clear()
                self.active_sectors.clear()
                self.daily_watchlist.clear()
                self.sector_anchors.clear()
                self.dragon_3day_history = data.get('dragon_3day_history', [])

                # 2. 恢复个股数据与 Snap 缓存
                stock_scores = data.get('stock_scores', {})
                momentum_scores = data.get('momentum_scores', {})
                meta_data = data.get('meta_data', {})
                
                # [NEW] 恢复种子股状态，确保复盘时种子奖分 (+15) 生效
                self.stock_selector_seeds = data.get('stock_selector_seeds', {})
                
                self._global_snap_cache.clear()
                
                for code, score in stock_scores.items():
                    ts = TickSeries(code)
                    ts.score = score
                    ts.momentum_score = momentum_scores.get(code, 0.0)
                    self._tick_series[code] = ts # [FIX] 必须存入字典，否则无法进行后续计算逻辑
                    
                    # [RECONSTRUCT-METADATA] 处理新的列式存储格式
                    meta_cols = data.get('meta_cols', {})
                    if meta_cols and 'code' in meta_cols:
                        # 建立临时索引 map 避免 O(N^2)
                        codes_list = meta_cols['code']
                        if not hasattr(self, '_meta_idx_map') or getattr(self, '_meta_idx_date', 0) != data.get('timestamp'):
                            self._meta_idx_map = {c: idx for idx, c in enumerate(codes_list)}
                            self._meta_idx_date = data.get('timestamp')
                        
                        i = self._meta_idx_map.get(code)
                        if i is not None:
                            def _get_val(key, default):
                                v_list = meta_cols.get(key, [])
                                return v_list[i] if i < len(v_list) and v_list[i] is not None else default
                            
                            ts.name = _get_val('n', code)
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
                    
                    # 同时重建 _global_snap_cache 以便 UI 渲染
                    self._global_snap_cache[code] = {
                        'code': code, 'score': score, 
                        'pct': ts.current_pct, 'price': ts.current_price,
                        'name': ts.name, 'category': ts.category, 'last_close': ts.last_close,
                        'high_day': ts.high_day, 'low_day': ts.low_day,
                        'last_high': ts.last_high, 'last_low': ts.last_low,
                        'pattern_hint': ts.pattern_hint, 'klines': list(ts.klines),
                        'is_untradable': ts.is_untradable, 'is_counter_trend': ts.is_counter_trend,
                        'ral': ts.ral, 'first_breakout_ts': ts.first_breakout_ts,
                        'vol_ratio': getattr(ts, 'vol_ratio', 0.0), 'signal_count': ts.signal_count
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
                
                self.data_version += 1 # [FIX] Notify UI of data change after snapshot load
                
            # [CRITICAL] 为历史快照全量重建跟随股与角色态势
            # 性能优化：先建立个股 -> 板块的反向索引，避免 O(S*N) 的嵌套循环导致 UI 卡死
            logger.info(f"🔄 [Detector] 为 {len(self.active_sectors)} 个板块并行重建深度数据态势...")
            
            from collections import defaultdict
            code_sector_map = defaultdict(list)
            for code, snap in self._global_snap_cache.items():
                cats = [c.strip() for c in re.split(r'[;；,，/\- ]', str(snap.get('category', ''))) if c.strip()]
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
            
            today_str = datetime.datetime.now().strftime('%Y%m%d')
            # 排除今日，寻找前两个交易日
            past_dates = [d for d in dates if d < today_str][:9]
            
            new_history = []
            for d_str in reversed(past_dates): # 从旧到新排列
                f_path = os.path.join(snapshot_dir, f"bidding_{d_str}.json.gz")
                leaders = self._scavenge_top2_from_snapshot(f_path, d_str)
                if leaders:
                    new_history.extend(leaders)
            
            if new_history:
                self.dragon_3day_history = new_history
                logger.info(f"🐉 [DragonTracker] 成功从历史快照补齐 {len(new_history)} 只前传龙头个股")
            
            self._dragon_init_done = True
        except Exception as e:
            logger.error(f"❌ DragonTracker init failed: {e}")

    def _scavenge_top2_from_snapshot(self, f_path: str, date_str: str) -> list:
        """从指定快照中提取各板块的前 2 名强势股"""
        try:
            import zlib
            with open(f_path, 'rb') as f: raw = f.read()
            try: data = json.loads(zlib.decompress(raw).decode('utf-8'))
            except: 
                import gzip
                data = json.loads(gzip.decompress(raw).decode('utf-8'))
            
            sector_data = data.get('sector_data', {})
            stock_scores = data.get('stock_scores', {})
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
                    base_price = c_price
                    
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
                if not self.in_history_mode:
                    self.link_manager.push(code)
        
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

    def _calculate_leader_score(self, s: dict, sector: str, market_avg_pct: float) -> float:
        """内部评估一个个股作为龙头的综合得分"""
        base_score = s.get('score', 0.0)
        
        # [SUPER 0414] 引入早盘时效溢价 (Opening Timeliness)
        # 权重：竞价(9:15-9:30)与早盘抢筹(9:30-9:35) 是最核心的引领信号
        opening_bonus = 0.0
        fb_ts = s.get('first_breakout_ts', 0)
        if fb_ts > 0:
            dt = datetime.datetime.fromtimestamp(fb_ts)
            # 构造今日 09:30 的锚点 (考虑到可能跨天加载，使用 fb_ts 当天的日期)
            anchor_930 = dt.replace(hour=9, minute=30, second=0, microsecond=0).timestamp()
            
            # 偏离值（秒）
            offset = fb_ts - anchor_930
            # 权重衰减逻辑：竞价期（offset<=0）最高分，开盘后 45 分钟内线性降至 0
            if offset < 2700: 
                if offset <= 0: # 竞价期 (9:15-9:30)
                    opening_bonus = 12.0
                else: # 开盘爆发期
                    opening_bonus = 12.0 * (1.0 - offset / 2700.0)
        
        if not getattr(self, 'use_dragon_race', False):
            # 💡 [0414 时效增强] 强调带头大哥的引领作用 (挖掘模式)
            # 权重平衡：基础分(0.6) + 涨幅(0.8) + 早盘时效额外加成 + 种子加成
            l_score = base_score * 0.6 + s['pct'] * 0.8 + opening_bonus
            
            # [SEED BONUS] 选股器种子显著加分 (0407 核心挖掘力)
            if s['code'] in self.stock_selector_seeds:
                l_score += 15.0
            
            # [LIQUIDITY BONUS] 大盘成交金额加成 (定海神针：金额越大越稳)
            klines = s.get('klines', [])
            total_amount = 0.0
            if klines:
                for k in klines:
                    amt = float(k.get('amount', k.get('turnover', 0.0)))
                    if amt == 0: amt = float(k.get('volume', 0.0)) * float(k.get('close', 0.0))
                    total_amount += amt
            
            if total_amount > 1e8: 
                l_score += min(5.0, total_amount / 2e8) # 每2亿加1分，封顶5分
            
            return l_score
        else:
            # [竞赛/追涨模式] 强调当日爆发力 + 极度强调开盘时效
            drawdown_pct = max(0, (s.get('high_day', 0.0) - s.get('price', 0.0)) / s.get('last_close', 1.0) * 100) if s.get('last_close', 0) > 0 else 0
            # [OPTIMIZED] 降低回撤惩罚从 4.0 降至 2.5，避免良性调整导致个股被瞬间清出看板
            penalty = drawdown_pct * 2.5 
            
            l_score = base_score * 0.6 + s['pct'] * 1.4 - penalty + opening_bonus
            if s.get('is_untradable'): l_score -= 50.0 
            return l_score

    def reconstruct_followers(self, sector_name: str):
        """[NEW] 手工从元数据缓存中重建指定板块的跟随股 (针对单个板块刷新)"""
        with self._lock:
            if sector_name not in self.active_sectors: return
            info = self.active_sectors[sector_name]
            
            candidates = []
            market_avg = self.last_market_avg
            for code, snap in self._global_snap_cache.items():
                cats = [c.strip() for c in re.split(r'[;；,，/\- ]', str(snap.get('category', ''))) if c.strip()]
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
                        # [FIX] 增加 延续 显式标记，让看板一眼看出是昨日主线
                        reason_short = seed_info['reason'].split('|')[0]
                        self._tick_series[code].pattern_hint = f"[延续|{reason_short}]"

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
                    # [FIX] 避免覆盖掉 [延续] 等历史种子标记
                    existing = self._tick_series[code].pattern_hint or ""
                    if "[延续" in existing:
                        self._tick_series[code].pattern_hint = f"{existing.split(']')[0]}] | {detail}"
                    else:
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
        # if 0 < (cur_close - ma20) / ma20 < 0.015 and last_du4 < 2.5:
        if ma20 > 0 and (cur_close - ma20) / ma20 > 0.02:
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
        if len(klines) >= 3:
            last_3 = [k['close'] for k in list(klines)[-3:]]
            if len(set(last_3)) == 1 and cur_pct < get_limit_up_threshold(code):
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

            if final_score >= 5.0:
                # [NEW] 信号活跃度计数：每分钟异动分达标即计为一次活跃
                current_min = int(data_ts // 60)
                if ts_obj._last_sig_min != current_min:
                    ts_obj.signal_count += 1
                    ts_obj._last_sig_min = current_min
            
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
                        'signal_count': ts.signal_count,
                        'ral': getattr(ts, 'ral', 0),
                        'top0': getattr(ts, 'top0', 0),
                        'top15': getattr(ts, 'top15', 0),
                        'score_diff': getattr(ts, 'score_diff', 0.0),
                        'pct_diff': getattr(ts, 'pct_diff', 0.0),
                        'price_diff': getattr(ts, 'price_diff', 0.0),
                        'vol_ratio': getattr(ts, 'vol_ratio', 0.0),
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
        codes_for_watchlist = active_codes if active_codes is not None else snap.keys()
        for code in codes_for_watchlist:
            d = snap.get(code)
            if d and d['pct'] >= get_limit_up_threshold(code) and not d['is_untradable']:
                # [FIXED] 时间指纹过滤：09:20 之前的竞价涨停不计入重点表，防止虚假干扰
                if now_t < 920 and not self.in_history_mode:
                    continue
                    
                if code in self.daily_watchlist:
                    self.daily_watchlist[code]['pct'] = round(d['pct'], 2)
                    self.daily_watchlist[code]['score'] = round(d.get('score', 0), 1)
                    if d['pattern_hint']: self.daily_watchlist[code]['pattern_hint'] = d['pattern_hint']
                else:
                    trigger_ts = d['first_breakout_ts'] if d['first_breakout_ts'] > 0 else now_ts
                    self.daily_watchlist[code] = {
                        'code': code, 'name': d['name'], 'sector': d['category'], 'pct': round(d['pct'], 2),
                        'score': round(d.get('score', 0), 1),
                        'time_str': datetime.datetime.fromtimestamp(trigger_ts).strftime('%m%d-%H:%M'),
                        'trigger_ts': trigger_ts, # [FIXED] 保存原始时间戳，用于跨日逻辑判定
                        'reason': '涨停', 'pattern_hint': d['pattern_hint']
                    }

        new_active = {} if target_sectors is None else self.active_sectors.copy()
        
        # 4. [NEW] 全局对照基准重置逻辑 (移动到循环外，每周期仅检查一次)
        now = time.time()
        # [OPTIMIZE] 当在非交易时间不要重置基准数据，保留最后的涨跌变化
        if self.is_active_session() and not self.in_history_mode:
            if now - self.baseline_time >= self.comparison_interval:
                self.reset_observation_anchors()

                # [Added] 仅在基准重置时，强制全量重刷板块，防止锚点丢失导致的数据显示异常
                target_sectors = None
                new_active = {}
        
        # --- [PERF-OPTIMIZE] 极限性能优化：预初选活跃板块 ---
        # 仅对有成员超过 score_threshold 的板块进行后续复杂的 board_score 计算
        # 这一步能过滤掉 ~90% 的僵尸板块，极大降低 CPU 负载并解决 TK 卡顿
        active_stocks_global = {code for code, ts in self._tick_series.items() if ts.score >= self.score_threshold}
        
        sectors_to_update_raw = target_sectors if target_sectors is not None else self._sector_active_stocks_persistent.keys()
        sectors_to_update = []
        for s in sectors_to_update_raw:
            # 快速检查该板块在持久化缓存中是否有任何一只是活跃的
            stocks_raw = self._sector_active_stocks_persistent.get(s, {})
            if any(c in active_stocks_global for c in stocks_raw):
                sectors_to_update.append(s)

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
                s['leader_score'] = self._calculate_leader_score(s, sector, market_avg_pct)

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
                    'l_score': round(s['leader_score'], 1)
                })

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
                day_open = l_ts.open_price or (list(l_ts.klines)[0].get('open') if l_ts.klines else 0)
                if l_ts.last_close > 0 and (day_open - l_ts.last_close) / l_ts.last_close > 0.03: tags.append("高开")
                if l_data.get('price', 0) > day_open > 0: tags.append("高走")
                
                # 记录竞价情绪
                now_t = int(time.strftime("%H%M"))
                if 920 <= now_t <= 925:
                    if leader_pct > 3.0: tags.append("竞价抢筹")
                    elif leader_pct < -3.0: tags.append("竞价恐慌")
                if 1300 <= now_t <= 1310: tags.append("午后异动")
                
                # [NEW] 主流延续性标签：如果龙头是昨日选股器选出的强势股，且板块强势
                if leader_code in self.stock_selector_seeds and board_score > 5.5:
                    tags.append("🔥 延续")

            # 基础门槛：即便个股分高，如果联动性极其平淡 (低于 15%) 且平均涨幅低，排除该板块。
            # 这是“369个活跃板块”缩减到“15-30个”的关键。
            if follow_ratio < 0.15 and avg_pct < 1.5:
                 if sector in new_active: del new_active[sector]
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

        with self._lock:
            self.active_sectors = new_active
            self.data_version += 1

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
