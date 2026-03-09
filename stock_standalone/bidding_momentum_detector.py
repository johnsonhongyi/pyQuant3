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
                 'open_price', 'high_day', 'low_day', 'ma20', 'ma60', 
                 'category', 'name', 'score', 'first_breakout_ts', 'pattern_hint',
                 'is_untradable', 'is_counter_trend', 'is_gap_leader', 'lastdu', 'lastdu4',
                 'ral', 'top0', 'top15', 'is_accumulating', 'is_reversal',
                 '_splitted_cats', '_total_vol', '_total_amt')

    def __init__(self, code: str, max_len: int = 30):
        self.code = code
        self.klines: deque = deque(maxlen=max_len)
        self.last_close: float = 0.0
        self.last_high: float = 0.0
        self.last_low: float = 0.0
        self.open_price: float = 0.0
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
        self._splitted_cats: Optional[List[str]] = None
        self._total_vol: float = 0.0
        self._total_amt: float = 0.0

    def update_meta(self, row: pd.Series):
        """从 df_all 行更新元数据"""
        self.last_close = float(row.get('lastp1d', row.get('nclose', 0.0)))
        self.last_high = float(row.get('lasth1d', self.last_close))
        self.last_low = float(row.get('lastl1d', self.last_close))
        self.open_price = float(row.get('open', 0.0))
        self.high_day = float(row.get('high', 0.0))
        self.low_day = float(row.get('low', 0.0))
        self.ma20 = float(row.get('ma20d', 0.0))
        self.ma60 = float(row.get('ma60d', 0.0))
        self.category = str(row.get('category', ''))
        self.name = str(row.get('name', self.code))
        self.lastdu = float(row.get('lastdu', 0.0))
        self.lastdu4 = float(row.get('lastdu4', 0.0))
        self.ral = int(row.get('ral', 0))
        self.top0 = int(row.get('top0', 0))
        self.top15 = int(row.get('top15', 0))
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
        self._total_vol = 0.0
        self._total_amt = 0.0
        self.klines.clear()
        for k in klines[-self.klines.maxlen:]:
            self.push_kline(k)

    @property
    def vwap(self) -> float:
        return self._total_amt / self._total_vol if self._total_vol > 0 else self.current_price

    @property
    def current_pct(self) -> float:
        """当前在日内的涨幅 (%), 基于 last_close"""
        if not self.klines or self.last_close <= 0:
            return 0.0
        last = self.klines[-1]
        return (last.get('close', 0.0) - self.last_close) / self.last_close * 100.0

    @property
    def current_price(self) -> float:
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

        # 聚合门槛评分 (下调以捕捉萌芽期)
        self.score_threshold = 1.0
        # 板块入场所需个股最低分
        self.sector_min_score = 2.0
        # 记录最后看到的数据时间戳（用于模拟回测时同步时钟）
        self.last_data_ts = 0.0

        # key=code, val={name, sector, pct, time_str, reason, reason, pattern_hint, release_risk}
        self.daily_watchlist: Dict[str, Dict[str, Any]] = {}
        self.enable_log = True # 是否允许向控制台/文件打印重点监控日志

        # ---- [NEW] 选股器联动与两阶段刷新 ----
        self.stock_selector_seeds: Set[str] = set() # 昨曾强势/反转股代码
        self._concept_data_date: Optional[datetime.date] = None
        self._concept_first_phase_done = False
        self._concept_second_phase_done = False
        
        # [Tier 2] 增量缓存
        self._global_snap_cache: Dict[str, Dict[str, Any]] = {}
        self._sector_active_stocks_persistent: Dict[str, Dict[str, Any]] = defaultdict(dict)

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
                high_seeds = df_seeds[df_seeds['score'] >= 80]['code'].astype(str).str.zfill(6).tolist()
                self.stock_selector_seeds = set(high_seeds)
                logger.info(f"[Detector] 成功加载 {len(self.stock_selector_seeds)} 只预选种子股")
        except Exception as e:
            logger.warning(f"[Detector] 加载 StockSelector 数据失败: {e}")

    # =========================================================
    # 公共接口
    # =========================================================

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
        for row in df.itertuples():
            code = str(getattr(row, 'Index')).strip().zfill(6)
            with self._lock:
                if code not in self._tick_series:
                    ts_obj = TickSeries(code)
                    ts_obj.update_meta(pd.Series(row._asdict()))
                    self._tick_series[code] = ts_obj
                    new_codes.append(code)
                else:
                    self._tick_series[code].update_meta(pd.Series(row._asdict()))

        # 对新 code：拉历史 K 线做冷启，然后注册订阅
        if self.realtime_service and new_codes:
            for code in new_codes:
                try:
                    hist = self.realtime_service.get_minute_klines(code, n=30)
                    with self._lock:
                        if code in self._tick_series:
                            self._tick_series[code].load_history(hist)
                except Exception as e:
                    logger.warning(f"[Detector] 历史K线加载失败 {code}: {e}")

                if code not in self._subscribed:
                    try:
                        # [Modified] Simulation mode also needs subscription to populate TickSeries.klines
                        self.realtime_service.subscribe(code, self._on_tick)
                        self._subscribed.add(code)
                    except Exception as e:
                        logger.warning(f"[Detector] 订阅失败 {code}: {e}")

    def get_active_sectors(self) -> List[Dict[str, Any]]:
        """
        返回当前活跃板块列表，按 score 降序。
        """
        with self._lock:
            result = sorted(self.active_sectors.values(),
                           key=lambda x: x.get('score', 0), reverse=True)
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
        self._gc_old_sectors()

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
        cur_close = float(latest.get('close', 0.0))
        cur_vol = float(latest.get('volume', 0.0))
        cur_open_bar = float(latest.get('open', cur_close))  # 当根k棒开盘
        day_open = float(ts_obj.open_price) or float(klines[0].get('open', cur_close))
        
        # [Moved Up] 当前涨幅
        cur_pct = (cur_close - last_close) / last_close * 100 if last_close > 0 else 0.0
        
        # 0. 周期因子 (Cycle Factor): 处于 MA20 之上且 MA20 向上，属于强周期
        cycle_score = 0.0
        
        # [NEW] 种子股加分 (StockSelector 预选项)
        is_hot_seed = code in self.stock_selector_seeds
        if is_hot_seed:
            cycle_score += 5.0

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
        top0_val = getattr(ts_obj, 'top0', 0)
        top15_val = getattr(ts_obj, 'top15', 0)
        if top0_val > 0: cycle_score += 10.0 # 一字涨停高权重
        if top15_val > 0: cycle_score += 5.0 # 强势突破加成
        
        # 2. 反转：种子股昨日强今日开盘弱现转强，或 MA60 处企稳反弹
        if is_hot_seed and open_gap_pct < 0 and cur_pct > 0:
            is_reversal = True
            cycle_score += 7.0
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
        if self.strategies['pct_change']['enabled']:
            p_min = self.strategies['pct_change']['min']
            p_max = self.strategies['pct_change']['max']
            # [Fix] 如果涨幅不足 p_min，评分清零
            # 允许 蓄势/反转/种子股/高分周期股 绕过此限制，以便在萌芽期识别
            if cur_pct < p_min and not (is_accumulating or is_reversal or is_hot_seed or cycle_score >= 4.0):
                with self._lock:
                    if code in self._tick_series:
                         self._tick_series[code].score = 0.0
                return
            score += min(cur_pct / p_max * 2.0, 2.0)  # 最多 2 分

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

        # --- 7. 最终评分与活性修正 ---
        final_score = cycle_score + bidding_score + score
        # [NEW] 活性修正：如果最近 3 分钟价格没有变动且未涨停，分数减半 (针对 user 提到的 0.0% 问题)
        if len(klines) >= 3:
            last_3 = [k['close'] for k in list(klines)[-3:]]
            if len(set(last_3)) == 1 and cur_pct < get_limit_up_threshold(code):
                final_score *= 0.5

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

        with self._lock:
            # 如果分数达到门槛且是首次异动，记录时间（用于认定龙头）
            if final_score >= 5.0 and ts_obj.first_breakout_ts == 0:
                ts_obj.first_breakout_ts = data_ts
            
            # [逻辑修正]：如果分数回落到极低水平（例如 < 2.0），重置异动时间
            # 防止那种集合竞价虚高、开盘瞬间冲高随即长久失败的股票一直霸占“首异时间”
            if final_score < 2.0:
                ts_obj.first_breakout_ts = 0

            if code in self._tick_series:
                ts_obj = self._tick_series[code]
                ts_obj.score = final_score
                ts_obj.is_untradable = is_untradable
                ts_obj.is_counter_trend = is_counter
                ts_obj.is_gap_leader = is_gap_leader  # 连续跳空强势龙头标记
                ts_obj.is_accumulating = is_accumulating # [NEW]
                ts_obj.is_reversal = is_reversal         # [NEW]
            
            # 更新全局最后时间
            if data_ts > self.last_data_ts:
                self.last_data_ts = data_ts

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
                        'klines': list(ts.klines), # [Phase 4] 必须包含 K 线用于 UI 渲染
                        'is_untradable': getattr(ts, 'is_untradable', False),
                        'is_counter_trend': getattr(ts, 'is_counter_trend', False),
                        'is_accumulating': getattr(ts, 'is_accumulating', False),
                        'is_reversal': getattr(ts, 'is_reversal', False),
                        'ral': getattr(ts, 'ral', 0),
                        'top0': getattr(ts, 'top0', 0),
                        'top15': getattr(ts, 'top15', 0)
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
        if self._concept_data_date != today:
            self._concept_data_date = today
            self._concept_first_phase_done = False
            self._concept_second_phase_done = False
            self.daily_watchlist.clear()
            if hasattr(self, "_sector_active_stocks_persistent"):
                self._sector_active_stocks_persistent.clear()
            logger.info(f"[Detector] {today} 跨天重置状态")

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
        
        # 将 persistent dict 转换为 list 给计算逻辑使用
        sectors_to_update = target_sectors if target_sectors is not None else self._sector_active_stocks_persistent.keys()
        
        for sector in sectors_to_update:
            stocks_dict = self._sector_active_stocks_persistent.get(sector, {})
            if not stocks_dict:
                if sector in new_active: del new_active[sector]
                continue
            
            stocks = list(stocks_dict.values())
            
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
            
            follow_ratio = active_member_count / len(all_member_codes) if all_member_codes else 0
            avg_pct = total_pct / len(all_member_codes) if all_member_codes else 0
            high_score_stocks = [s for s in stocks if s['score'] >= self.sector_min_score]
            if len(high_score_stocks) < 1 and (follow_ratio < 0.3 or leader_pct < 2.0):
                if sector in new_active: del new_active[sector]
                continue
                
            tags = []
            l_data = candidate_leader
            l_ts = self._tick_series.get(leader_code)
            if l_ts:
                day_open = l_ts.open_price or (list(l_ts.klines)[0].get('open') if l_ts.klines else 0)
                if (day_open - l_ts.last_close) / l_ts.last_close > 0.03 and l_ts.last_close > 0: tags.append("高开")
                if l_data['price'] > day_open > 0: tags.append("高走")
                if 920 <= now_t <= 925:
                    if leader_pct > 3.0: tags.append("竞价抢筹")
                    elif leader_pct < -3.0: tags.append("竞价恐慌")
                if 1300 <= now_t <= 1310: tags.append("午后异动")

            s_top0_sum = sum(s.get('top0', 0) for s in stocks)
            s_top15_sum = sum(s.get('top15', 0) for s in stocks)
            hotness_multiplier = 1.0 + (s_top0_sum * 0.15) + (s_top15_sum * 0.05)
            tk_correlation_score = avg_pct * follow_ratio * 50.0 
            board_score = (candidate_leader['score'] * 1.0 + avg_pct * 5.0 + follow_ratio * 20.0 + tk_correlation_score) * hotness_multiplier
            
            sector_type = "📈 跟随"
            if board_score > 60 and (leader_pct > 5.0 or s_top0_sum > 0) and follow_ratio > 0.4: sector_type = "🔥 强攻"
            elif any(s.get('is_accumulating') for s in stocks) or sum(s.get('ral', 0) for s in stocks)/len(stocks) > 12:
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

            new_active[sector] = {
                'sector': sector, 'score': round(board_score, 2), 'tags': " ".join(tags),
                'follow_ratio': round(follow_ratio, 2), 'leader': leader_code,
                'leader_name': l_data['name'], 'leader_pct': round(l_data['pct'], 2),
                'leader_price': l_data.get('price', 0.0),
                'leader_klines': l_data.get('klines', []),
                'leader_last_close': l_data.get('last_close', 0),
                'leader_high_day': l_data.get('high_day', 0),
                'leader_low_day': l_data.get('low_day', 0),
                'leader_last_high': l_data.get('last_high', 0),
                'leader_last_low': l_data.get('last_low', 0),
                'leader_first_ts': l_data['first_breakout_ts'],
                'pattern_hint': l_data['pattern_hint'],
                'is_untradable': l_data['is_untradable'],
                'followers': [{'code': s['code'], 'name': s['name'], 'pct': s['pct'], 'price': s.get('price', 0.0), 'first_ts': s['first_breakout_ts']} for s in stocks[1:15]],
                'linked_concepts': linked_concepts[:3]
            }

        with self._lock:
            self.active_sectors = new_active

    def _gc_old_sectors(self):
        """清理长时间不活跃的板块结果"""
        now = time.time()
        if now - self._last_gc_ts < 30: return
        self._last_gc_ts = now
        with self._lock:
            stale = [s for s, d in self.active_sectors.items()
                     if now - d.get('ts', 0) > 900.0] # max_age is 900.0
            for s in stale:
                del self.active_sectors[s]

    # =========================================================
    # 内部：板块图
    # =========================================================

    def _rebuild_sector_map(self, df: pd.DataFrame):
        """从 df_all 重建 sector → set(code) 索引"""
        if 'category' not in df.columns:
            return
        new_map: Dict[str, Set[str]] = defaultdict(set)
        for row in df.itertuples():
            # itertuples 默认将 index 作为第一个元素或名为 Index 的属性
            code = str(getattr(row, 'Index')).strip().zfill(6)
            cat = str(getattr(row, 'category', ''))
            if not cat or cat == 'nan':
                continue
            for p in re.split(r'[;；,，/ \\-]', cat):
                p = p.strip()
                if p:
                    new_map[p].add(code)
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
