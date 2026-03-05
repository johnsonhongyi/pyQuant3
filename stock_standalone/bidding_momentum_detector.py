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


class TickSeries:
    """
    单只个股的分钟 K 线滚动队列，外加基础统计缓存。
    """
    __slots__ = ('code', 'klines', 'last_close', 'last_high', 'last_low', 
                 'open_price', 'high_day', 'low_day', 'ma20', 'ma60', 
                 'category', 'name', 'score')

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
        for code_raw, row in df.iterrows():
            code = str(code_raw).strip().zfill(6)
            with self._lock:
                if code not in self._tick_series:
                    ts_obj = TickSeries(code)
                    ts_obj.update_meta(row)
                    self._tick_series[code] = ts_obj
                    new_codes.append(code)
                else:
                    # 更新元数据（每次都刷新，因为 ma20/ma60 可能变化）
                    self._tick_series[code].update_meta(row)

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
        每个 entry:
          {sector, score, leader, leader_name, leader_pct, leader_price,
           leader_klines, followers: [{code, name, pct, price}]}
        """
        with self._lock:
            result = sorted(self.active_sectors.values(),
                           key=lambda x: x.get('score', 0), reverse=True)
        return result

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
        cur_open_bar = float(latest.get('open', cur_close))  # 当根k棒开盘
        day_open = float(ts_obj.open_price) or float(klines[0].get('open', cur_close))

        # --- 1. 高开检查 ---
        high_open_pct = (day_open - last_close) / last_close * 100 if last_close > 0 else 0.0
        if self.strategies['ma_rebound']['enabled']:
            # 昨收回踩 MA20/MA60 范围内（2% 容差）且今日高开
            near_ma = False
            if ma20 > 0 and abs(last_close - ma20) / ma20 < 0.03:
                near_ma = True
            if ma60 > 0 and abs(last_close - ma60) / ma60 < 0.03:
                near_ma = True
            if near_ma and high_open_pct > 1.0:
                score += 3.0  # 回踩反弹形态
            elif high_open_pct > 2.0:
                score += 1.5  # 普通高开

        # --- 2. 涨幅过滤 ---
        cur_pct = (cur_close - last_close) / last_close * 100 if last_close > 0 else 0.0
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

        with self._lock:
            if code in self._tick_series:
                self._tick_series[code].score = score

    # =========================================================
    # 内部：板块聚合
    # =========================================================

    def _aggregate_sectors(self):
        """
        将高分个股聚合到板块，找龙头和跟随股。
        在主刷新计时器或 update_scores() 中调用。
        """
        SCORE_THRESHOLD = 3.0  # 低于此分不上榜

        with self._lock:
            # 复制评分快照，以及走势图所需的元数据
            snap = {code: (ts.score, ts.current_pct, ts.current_price,
                           ts.name, ts.category, ts.last_close,
                           ts.high_day, ts.low_day, ts.last_high, ts.last_low)
                    for code, ts in self._tick_series.items()}

        # 板块黑名单（屏蔽宽泛、非具体行业/概念板块）
        SECTOR_BLACKLIST = {
            '深股通', '沪股通', '融资融券', '标普概念', 'MSCI中国', '剔除纳斯', 
            '机构重仓', '昨日涨停', '昨日触板', '创业板综', '证金持股', '上证180',
            '中证500', '沪深300', '深证成指', '基金重仓', '北向资金', '深成指',
            '含HS300', '国企改革', '破净股', '预盈预增', 'QFII重仓', '社保重仓'
        }

        # 按板块聚合
        import re
        sector_stocks: Dict[str, List[dict]] = defaultdict(list)
        for code, (score, pct, price, name, cat, lc, hi, lo, lhi, llo) in snap.items():
            if score < SCORE_THRESHOLD:
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
                    'last_high': lhi, 'last_low': llo
                })

        now_ts = time.time()
        new_active: Dict[str, Dict[str, Any]] = {}

        for sector, stocks in sector_stocks.items():
            if not stocks:
                continue
            
            # 排序寻找该板块内的最佳候选人（最高异动分）
            stocks.sort(key=lambda x: x['score'], reverse=True)
            leader = stocks[0]
            leader_code = leader['code']

            # 只有板块内有实质性异动的股（score > 4.0）超过一定比例或一定数量，才认为该板块有意义
            # 这样可以过滤掉零星个股带动的干扰板块
            high_score_stocks = [s for s in stocks if s['score'] >= 4.0]
            if not high_score_stocks:
                continue

            # 找跟随股：同板块内其他涨幅 > 0 的股
            followers = []
            for c in self.sector_map.get(sector, set()):
                if c == leader_code:
                    continue
                if c in snap:
                    _, f_pct, f_price, f_name, _, f_lc, f_hi, f_lo, f_lhi, f_llo = snap[c]
                    if f_pct > 0:
                        followers.append({
                            'code': c, 'name': f_name,
                            'pct': f_pct, 'price': f_price,
                            'last_close': f_lc, 'high_day': f_hi, 'low_day': f_lo,
                            'last_high': f_lhi, 'last_low': f_llo
                        })
            followers.sort(key=lambda x: x['pct'], reverse=True)

            # [OPTIM] 增强板块评分逻辑：
            # 基础分 = 龙头异动分
            # 附加分1 = 强力跟风股数量 (score>=4.0的个数越多，板块强度越高)
            # 附加分2 = 涨幅溢价
            board_score = leader['score'] * 1.5 + len(high_score_stocks) * 2.5 + leader['pct'] * 0.5
            
            # 过滤单兵作战：如果板块内只有一个强票，且跟随股不多（<2），且基础评分不够高，则略过
            if len(high_score_stocks) < 2 and len(followers) < 3 and board_score < 15:
                continue

            # 获取龙头最近 K 线用于 UI 展示
            leader_klines: List[dict] = []
            with self._lock:
                ts_obj = self._tick_series.get(leader_code)
                if ts_obj:
                    leader_klines = list(ts_obj.klines)[-20:]

            new_active[sector] = {
                'sector': sector,
                'score': round(board_score, 2),
                'leader': leader_code,
                'leader_name': leader['name'],
                'leader_pct': round(leader['pct'], 2),
                'leader_price': leader['price'],
                'leader_last_close': leader.get('last_close', 0),
                'leader_high_day': leader.get('high_day', 0),
                'leader_low_day': leader.get('low_day', 0),
                'leader_last_high': leader.get('last_high', 0),
                'leader_last_low': leader.get('last_low', 0),
                'leader_klines': leader_klines,
                'followers': followers[:12],  # 跟随股限制适中
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
        for code_raw, row in df.iterrows():
            code = str(code_raw).strip().zfill(6)
            cat = str(row.get('category', ''))
            if not cat or cat == 'nan':
                continue
            for p in re.split(r'[;；,，/\- ]', cat):
                p = p.strip()
                if p:
                    new_map[p].add(code)
        self.sector_map = new_map

    # =========================================================
    # 时间窗口判断（只在竞价/尾盘生效）
    # =========================================================

    @staticmethod
    def is_active_session() -> bool:
        """当前是否在 09:15-09:45 或 14:30-15:00"""
        now = datetime.datetime.now()
        hm = now.hour * 100 + now.minute
        return (915 <= hm <= 945) or (1430 <= hm <= 1500)
