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



class TickSeries:
    """
    单只个股的分钟 K 线滚动队列，外加基础统计缓存。
    """
    __slots__ = ('code', 'klines', 'last_close', 'last_high', 'last_low', 
                 'open_price', 'high_day', 'low_day', 'ma20', 'ma60', 
                 'category', 'name', 'score', 'first_breakout_ts', 'pattern_hint',
                 'is_untradable', 'is_counter_trend', 'is_gap_leader')

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

    def push_kline(self, kline: dict):
        """追加一根分钟 K 线"""
        self.klines.append(kline)

    def load_history(self, klines: List[dict]):
        """初始化冷启历史数据"""
        for k in klines[-self.klines.maxlen:]:
            self.klines.append(k)

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

    def __init__(self, realtime_service: Optional["DataPublisher"] = None):
        # ---- 数据服务 ----
        self.realtime_service = realtime_service

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
        self.score_threshold = 2.0
        # 板块入场所需个股最低分
        self.sector_min_score = 3.0
        # 记录最后看到的数据时间戳（用于模拟回测时同步时钟）
        self.last_data_ts = 0.0

        # key=code, val={name, sector, pct, time_str, reason, release_risk}
        self.daily_watchlist: Dict[str, Dict[str, Any]] = {}
        self.enable_log = True # 是否允许向控制台/文件打印重点监控日志

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

    def update_scores(self):
        """
        定时调用（如 UI 刷新计时器），对所有已注册 code 重新评分，
        并聚合为板块结果。适用于没有订阅推送（非交易时段调试）。
        """
        with self._lock:
            codes = list(self._tick_series.keys())
        for code in codes:
            self._evaluate_code(code)
        self._aggregate_sectors()
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
        if ma20 > 0 and cur_close > ma20:
            cycle_score += 1.0  # 基础牛熊分
            if ma60 > 0 and cur_close > ma60:
                cycle_score += 1.0
        
        # [Moved Up] 状态标志初始化
        is_counter = False
        is_untradable = False
        
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
            all_highs = [float(k.get('high', 0)) for k in klines]
            all_lows  = [float(k.get('low', 0))  for k in klines]
            if max(all_highs) == min(all_lows):
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
            # 2.1 放量拉升检测
            if len(klines) >= 3:
                vols = [float(k.get('volume', 0)) for k in klines]
                if vols[-1] > sum(vols[-3:-1])/2 * 1.5 and cur_close > klines[-2].get('close', 0):
                    intraday_signal = "放量内激"
            
            # 2.2 日内新高
            if ts_obj.high_day > 0 and cur_close >= ts_obj.high_day * 0.998:
                if intraday_signal: intraday_signal += "+新高"
                else: intraday_signal = "日内新高"

        # 3. 支撑/止损信号
        ma_break_signal = ""
        if len(klines) >= 5:
            total_vol = sum(float(k.get('volume', 0)) for k in klines)
            if total_vol > 0:
                vwap = sum(float(k.get('close', 0)) * float(k.get('volume', 0)) for k in klines) / total_vol
                vwap_dist = (cur_close - vwap) / vwap * 100.0
                
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
            if not (p_min <= cur_pct <= p_max):
                with self._lock:
                    if code in self._tick_series:
                        self._tick_series[code].score = 0.0
                return
            score += min(cur_pct / p_max * 2.0, 2.0)  # 最多 2 分

        # --- 3. 连续上涨 K 棒 ---
        if self.strategies['consecutive_up']['enabled'] and len(klines) >= 3:
            n_bars = self.strategies['consecutive_up']['bars']
            recents = klines[-n_bars:]
            closes = [float(k.get('close', 0)) for k in recents]
            is_consecutive = all(closes[i] > closes[i-1] for i in range(1, len(closes)))
            if is_consecutive:
                score += 2.0

        # --- 4. 放量检查 ---
        if self.strategies['surge_vol']['enabled'] and len(klines) >= 5:
            vols = [float(k.get('volume', 0)) for k in klines]
            recent_avg = sum(vols[-3:]) / 3 if len(vols) >= 3 else vols[-1]
            hist_avg = sum(vols[:-3]) / max(len(vols)-3, 1) if len(vols) > 3 else recent_avg
            min_ratio = self.strategies['surge_vol']['min_ratio']
            if hist_avg > 0 and recent_avg / hist_avg >= min_ratio:
                score += 2.0 * min(recent_avg / hist_avg / min_ratio, 2.0)

        # --- 5. 每日新高附近 ---
        if self.strategies['new_high']['enabled']:
            if ts_obj.high_day > 0 and cur_close >= ts_obj.high_day * 0.99:
                score += 1.5

        # --- 6. 振幅过滤（整体振幅过小或过大则剔除）---
        if self.strategies['amplitude']['enabled'] and len(klines) > 1 and last_close > 0:
            all_highs = [float(k.get('high', 0)) for k in klines]
            all_lows  = [float(k.get('low', 0))  for k in klines]
            h = max(all_highs) if all_highs else 0.0
            l = min(all_lows)  if all_lows  else 0.0
            amplitude = (h - l) / last_close * 100 if last_close > 0 else 0.0
            a_min = self.strategies['amplitude']['min']
            a_max = self.strategies['amplitude']['max']
            if not (a_min <= amplitude <= a_max):
                score = 0.0

        # --- 7. 时间因子与首次异动记录 ---
        final_score = cycle_score + bidding_score + score
        
        # 尝试从数据中获取模拟时间，否则回测时显示的“首异时间”会是此时此刻的墙上时间
        data_ts = 0.0
        ts_val = latest.get('ticktime', latest.get('timestamp', latest.get('time')))
        if ts_val:
            try:
                # 如果是字符串，转为 unix timestamp
                if isinstance(ts_val, (str, pd.Timestamp)):
                    dt = pd.to_datetime(ts_val)
                    data_ts = dt.timestamp()
                    # [BUG FIX] 防止昨天的纯时间字符串 "15:00:00" 被 pandas 默认解析为今天的 15:00 (变成未来时间)
                    if data_ts > time.time() + 60:
                        data_ts = (dt - pd.Timedelta(days=1)).timestamp()
                else:
                    data_ts = float(ts_val)
            except:
                data_ts = time.time()
        else:
            data_ts = time.time()

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
            
            # 更新全局最后时间
            if data_ts > self.last_data_ts:
                self.last_data_ts = data_ts

    # =========================================================
    # 内部：板块聚合
    # =========================================================

    def _aggregate_sectors(self):
        """
        将高分个股聚合到板块，找龙头和跟随股。
        在主刷新计时器或 update_scores() 中调用。
        """

        with self._lock:
            # 复制评分快照，以及走势图所需的元数据
            snap = {code: (ts.score, ts.current_pct, ts.current_price,
                           ts.name, ts.category, ts.last_close,
                           ts.high_day, ts.low_day, ts.last_high, ts.last_low,
                           ts.first_breakout_ts, getattr(ts, 'pattern_hint', ""),
                           getattr(ts, 'is_untradable', False),
                           getattr(ts, 'is_counter_trend', False))
                    for code, ts in self._tick_series.items()}

        # 板块黑名单（屏蔽宽泛、非具体行业/概念板块）
        SECTOR_BLACKLIST = {
            '深股通', '沪股通', '融资融券', '标普概念', 'MSCI中国', '剔除纳斯', 
            '机构重仓', '昨日涨停', '昨日触板', '创业板综', '证金持股', '上证180',
            '中证500', '沪深300', '深证成指', '基金重仓', '北向资金', '深成指',
            '含HS300', '国企改革', '破净股', '预盈预增', 'QFII重仓', '社保重仓'
        }

        # [New] 计算全市场平均涨幅，用于识别“逆势异军突起”
        market_avg_pct = 0.0
        if snap:
            market_avg_pct = sum(x[1] for x in snap.values()) / len(snap)
            self.last_market_avg = market_avg_pct # 存回 detector 供 _evaluate_code 使用

        # 按板块聚合
        import re
        sector_stocks: Dict[str, List[dict]] = defaultdict(list)
        for code, (score, pct, price, name, cat, lc, hi, lo, lhi, llo, fbts, phint, untrd, isctr) in snap.items():
            if score < self.score_threshold:
                continue
            parts = re.split(r'[;；,，/\- ]', cat)
            for p in parts:
                p = p.strip()
                if not p or p == 'nan' or p in SECTOR_BLACKLIST:
                    continue
                # 过滤太长的描述性板块名
                if len(p) > 8: 
                    continue
                sector_stocks[p].append({
                    'code': code, 'score': score,
                    'pct': pct, 'price': price, 'name': name,
                    'last_close': lc, 'high_day': hi, 'low_day': lo,
                    'last_high': lhi, 'last_low': llo, 'first_breakout_ts': fbts,
                    'pattern_hint': phint, 'is_untradable': untrd, 'is_counter_trend': isctr
                })

        # 优先使用最后接收到的数据时间戳，否则使用系统时间
        now_ts = self.last_data_ts if self.last_data_ts > 0 else time.time()
        new_active: Dict[str, Dict[str, Any]] = {}

        # --- Limit-up tracking for daily_watchlist ---
        # This logic is added here to populate self.daily_watchlist
        # It checks for stocks that are at or near limit-up and adds them to the watchlist
        for code, (score, pct, price, name, cat, lc, hi, lo, lhi, llo, fbts, phint, untrd, isctr) in snap.items():
            if pct >= get_limit_up_threshold(code) and not untrd: # Check for near limit-up dynamically by market
                # If it's already in the watchlist, only update dynamic fields, NEVER touch time_str
                if code in self.daily_watchlist:
                    # 只更新涨幅和形态，保留首次触发时间不变
                    self.daily_watchlist[code]['pct'] = round(pct, 2)
                    if phint:
                        self.daily_watchlist[code]['pattern_hint'] = phint
                else:
                    # 新入表：使用该股自己的首次异动时间戳(first_breakout_ts)作为触发时间
                    # 如果 fbts 可用且合理，用它；否则 fallback 到当前批次时间
                    if fbts > 0:
                        trigger_ts = fbts
                    else:
                        trigger_ts = now_ts
                    trigger_time_str = datetime.datetime.fromtimestamp(trigger_ts).strftime('%m%d-%H:%M')
                    self.daily_watchlist[code] = {
                        'code': code,
                        'name': name,
                        'sector': cat, # Use the full category string for watchlist
                        'pct': round(pct, 2),
                        'time_str': trigger_time_str,
                        'reason': '涨停',
                        'pattern_hint': phint,
                        'release_risk': False # Placeholder for future logic
                    }
        # [NEW] Log the watchlist if enabled (OUTSIDE the sector loop)
        if self.enable_log and self.daily_watchlist:
            watchlist = self.get_daily_watchlist()
            if watchlist:
                logger.info(f"📋 当日重点表 ({len(watchlist)} 只):")
                for w in watchlist:
                    # 获取第一个非市场标签的概念板块
                    market_tags = ['科创板', '创业板', '主板', '中小板', '北证']
                    all_cats = w['sector'].split(';')
                    cats = [c for c in all_cats if c not in market_tags]
                    sector_short = cats[0] if cats else (all_cats[0] if all_cats else 'N/A')
                    
                    reason_tag = f"[{w['reason']}]" if w.get('reason') else ''
                    logger.info(f"   {w['name']} ({w['code']}) {reason_tag} {w['pct']:+.1f}% 首触发: {w['time_str']} 板块: {sector_short}")
                logger.info("-" * 60)

        for sector, stocks in sector_stocks.items():
            if not stocks:
                continue
            
            # --- 板块内分析 ---
            # 1. 寻找领涨股 (带量上攻基础分 + 先发时间奖励 - 尾盘回落惩罚)
            for s in stocks:
                base_score = s.get('score', 0)
                # 计算回撤惩罚: (日内最高价 - 现价) / 昨收 => 回撤幅度
                drawdown_pct = 0.0
                if s['last_close'] > 0 and s['high_day'] > 0:
                    drawdown_pct = max(0, (s['high_day'] - s['price']) / s['last_close'] * 100)
                
                # 惩罚项：如果从高位回撤超过 1.0%，则大概率不是当下的真龙头
                penalty = drawdown_pct * 4.0 

                # 计算先发奖励: 越早起动的分数越高 (09:30-10:00 权重最高)
                time_bonus = 0.0
                if s['first_breakout_ts'] > 0:
                    # 假定以 09:30 为基准
                    market_open_dt = pd.Timestamp.fromtimestamp(s['first_breakout_ts']).replace(hour=9, minute=30, second=0)
                    time_diff_min = (market_open_dt.timestamp() - s['first_breakout_ts']) / 60.0
                    # 早于 09:30 的（竞价）给 10 分固定奖励，09:30-10:00 每分钟递减
                    if time_diff_min >= 0:
                        time_bonus = 10.0 + time_diff_min * 0.1
                    else:
                        # 09:30 之后，起动越晚奖励越少
                        time_bonus = max(0, 10.0 + time_diff_min * 0.5)

                # 龙头综合评分 (Composite Score)
                # 强化涨幅权重 (1.2)，基础异动分权重 (0.8)，确保领涨性
                s['leader_score'] = base_score * 0.8 + s['pct'] * 1.2 - penalty + time_bonus
                
                # [Added] 形态属性奖励与逆势溢价
                phint = s.get('pattern_hint', "")
                if "V反" in phint: s['leader_score'] += 5.0
                if "突破" in phint: s['leader_score'] += 3.0
                if "MA60反转" in phint: s['leader_score'] += 8.0
                if "MA20反转" in phint: s['leader_score'] += 4.0
                
                # 逆势带头作用：大盘跌，它涨，带量异动
                if market_avg_pct < -0.5 and s['pct'] > 1.0:
                    # 逆势加成：基础分翻倍的一个加成或固定奖励
                    s['leader_score'] += 10.0 
                    s['is_counter_trend'] = True
                else:
                    s['is_counter_trend'] = False

                # 识别一字板 (Untradable)
                # 如果个股在评价时已经标记为不可交易，或者现在表现为一字涨停，则确认为不可交易
                limit_threshold = get_limit_up_threshold(s['code'])
                if s.get('is_untradable') or (s['pct'] > limit_threshold and (s['high_day'] - s['low_day']) < 0.01):
                    s['is_untradable'] = True
                    # 一字板不作为活跃龙头显示，大幅降低其在板块内的领涨评分权重
                    s['leader_score'] -= 50.0 

            # 二次筛选真正龙头
            stocks.sort(key=lambda x: x['leader_score'], reverse=True)
            candidate_leader = stocks[0]
            leader_code = candidate_leader['code']
            leader_pct = candidate_leader['pct']

            # 评估同步率 (Follow Ratio) - 对应 tk 中 get_following_concepts_by_correlation 的逻辑
            all_member_codes = self.sector_map.get(sector, set())
            active_member_count = 0
            total_pct = 0.0
            leader_sign = 1 if leader_pct > 0 else (-1 if leader_pct < 0 else 0)
            
            for c in all_member_codes:
                if c in snap:
                    snap_data = snap[c]
                    f_pct = snap_data[1]  # current_pct
                    # 与龙头同向运动即为跟随 (对齐 TK np.sign(percents) == stock_sign)
                    f_sign = 1 if f_pct > 0 else (-1 if f_pct < 0 else 0)
                    if f_sign == leader_sign and f_sign != 0:
                        active_member_count += 1
                        total_pct += f_pct
            
            follow_ratio = active_member_count / len(all_member_codes) if all_member_codes else 0
            avg_pct = total_pct / len(all_member_codes) if all_member_codes else 0

            # 2. 板块入场门槛筛选: 
            # 满足以下之一即可显示：
            # a) 有个股评分达到了 sector_min_score (3.0) 且板块成员有多于 1 只有异动
            # b) 跟随度较高 (FollowRatio > 0.3) 且龙头涨幅突出 (pct > 2%)
            high_score_stocks = [s for s in stocks if s['score'] >= self.sector_min_score]
            
            if len(high_score_stocks) < 1 and (follow_ratio < 0.3 or leader_pct < 2.0):
                continue
                
            # 3. 确定板块标签逻辑
            tags = []
            # 获取龙头对象
            l_ts = self._tick_series.get(leader_code)
            if l_ts:
                day_open = l_ts.open_price or (list(l_ts.klines)[0].get('open') if l_ts.klines else 0)
                # 高开 tag
                if (day_open - l_ts.last_close) / l_ts.last_close > 0.03 and l_ts.last_close > 0:
                    tags.append("高开")
                # 高走 tag (当前价 > 开盘价)
                if l_ts.current_price > day_open > 0:
                    tags.append("高走")
                # 逆势 tag (全板块平均涨幅显著强于市场或处于强周期)
                if getattr(candidate_leader, 'is_counter_trend', False):
                    tags.append("逆势领头")
                if avg_pct > 2.0:
                    tags.append("强势")
                # 反转 tag (昨日跌今日强)
                if l_ts.last_close < l_ts.last_low * 1.01 and candidate_leader['pct'] > 3:
                     tags.append("反转")

            # 4. 板块最终强度分 = 龙头分 + 跟随分 + 关联度修正
            board_score = candidate_leader['score'] * 1.2 + avg_pct * 3.0 + follow_ratio * 15.0
            
            # 5. 准备跟随股列表 (按涨幅降序，保留首异时间)
            followers = []
            for c in all_member_codes:
                if c == leader_code: continue
                if c in snap:
                     sd = snap[c]
                     followers.append({
                        'code': c, 'name': sd[3], 'pct': sd[1], 'price': sd[2],
                        'last_close': sd[5], 'high_day': sd[6], 'low_day': sd[7],
                        'last_high': sd[8], 'last_low': sd[9], 'first_breakout_ts': sd[10],
                        'pattern_hint': sd[11], 'is_untradable': sd[12]
                     })
            followers.sort(key=lambda x: x['pct'], reverse=True)

            # 6. [New] 联动板块分析 - 类 get_following_concepts_by_correlation
            # 找出领涨股所属的所有 concept，统计每个 concept 的跟随率和平均涨幅
            linked_concepts: list[dict] = []
            leader_cat = candidate_leader.get('category', '')
            # 如果 snap 数据中没有 category（快照不含此字段），需从 _tick_series 取
            if not leader_cat:
                l_ts2 = self._tick_series.get(leader_code)
                leader_cat = getattr(l_ts2, 'category', '') if l_ts2 else ''
            leader_concepts = [c.strip() for c in re.split(r'[;；,，/ \\-]', leader_cat) if c.strip() and len(c.strip()) <= 8]
            if leader_concepts:
                leader_pct_val = candidate_leader['pct']
                leader_sign  = 1 if leader_pct_val > 0 else (-1 if leader_pct_val < 0 else 0)
                for concept in leader_concepts:
                    members = self.sector_map.get(concept)
                    if not members or len(members) < 4:
                        continue
                    follow_count = 0
                    concept_total_pct = 0.0
                    concept_member_cnt = 0
                    for mc in members:
                        if mc in snap:
                            mc_pct = snap[mc][1]
                            mc_sign = 1 if mc_pct > 0 else (-1 if mc_pct < 0 else 0)
                            concept_total_pct += mc_pct
                            concept_member_cnt += 1
                            if mc_sign == leader_sign and mc_sign != 0:
                                follow_count += 1
                    if concept_member_cnt > 0:
                        c_avg_pct = round(concept_total_pct / concept_member_cnt, 2)
                        c_follow_ratio = round(follow_count / concept_member_cnt, 2)
                        c_score = round(c_avg_pct * c_follow_ratio, 2)
                        linked_concepts.append({
                            'concept': concept,
                            'score': c_score,
                            'avg_pct': c_avg_pct,
                            'follow_ratio': c_follow_ratio,
                            'member_cnt': concept_member_cnt,
                        })
                linked_concepts.sort(key=lambda x: x['score'], reverse=True)

            # 获取龙头走势
            leader_klines: List[dict] = []
            with self._lock:
                if l_ts: leader_klines = list(l_ts.klines)[-20:]

            new_active[sector] = {
                'sector': sector,
                'score': round(board_score, 2),
                'tags': " ".join(tags),
                'follow_ratio': round(follow_ratio, 2),
                'leader': leader_code,
                'leader_code': leader_code,
                'leader_name': candidate_leader['name'],
                'leader_pct': round(candidate_leader['pct'], 2),
                'leader_price': candidate_leader['price'],
                'leader_first_ts': candidate_leader['first_breakout_ts'],
                'pattern_hint': candidate_leader.get('pattern_hint', ''),
                'is_untradable': candidate_leader.get('is_untradable', False),
                'is_counter_trend': candidate_leader.get('is_counter_trend', False),
                'leader_klines': leader_klines,
                'followers': followers[:15],
                'linked_concepts': linked_concepts[:5],  # 最多展示 top-5 联动板块
                'ts': now_ts,
            }

        with self._lock:
            self.active_sectors = new_active

    def _gc_old_sectors(self, max_age: float = 900.0):
        """清理 900s (15min) 内没有更新的板块"""
        now_ts = time.time()
        if now_ts - self._last_gc_ts < 60:
            return
        self._last_gc_ts = now_ts
        with self._lock:
            stale = [s for s, d in self.active_sectors.items()
                     if now_ts - d.get('ts', 0) > max_age]
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
