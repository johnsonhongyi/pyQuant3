# -*- coding: utf-8 -*-
"""
IntradayPatternDetector - 日内分时形态检测器

支持形态：
1. auction_high_open - 竞价高开 (开盘 > 昨收*1.01)
2. gap_up - 跳空高开 (开盘 > 昨收*1.03)
3. low_open_high_walk - 低开走高 (开盘<昨收-1%, 当前>开盘+2%)
4. open_is_low - 开盘最低 (今日最低≈开盘价, 当前上涨)
5. instant_pullback - 瞬间回踩支撑 (触及MA5后反弹)
6. shrink_sideways - 缩量横盘 (30分钟振幅<1%, 量<均量50%)
7. pullback_upper - 回踩upper (当前价在布林上轨±1%)
8. high_drop - 冲高回落 (最高>开盘+3%, 当前<最高-2%)
9. top_signal - 顶部信号 (冲高回落+量价背离+十字星等加权评分)

使用方式：
    detector = IntradayPatternDetector()
    detector.on_pattern = lambda ev: print(ev)
    detector.update(code, name, tick_df, day_row, prev_close)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, List, Callable, Any
from datetime import datetime, time as dt_time
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# 尝试导入信号总线与标准化信号
try:
    from signal_bus import get_signal_bus, publish_standard_signal, SignalBus
    from signal_standard import StandardSignal
    HAS_STANDARD_SIGNAL = True
    HAS_SIGNAL_BUS = True
except ImportError:
    HAS_STANDARD_SIGNAL = False
    HAS_SIGNAL_BUS = False
    StandardSignal = Any
    logger.warning("signal_bus or signal_standard not found, fallback to limited functionality")


@dataclass
class PatternEvent:
    """形态事件数据结构"""
    code: str
    name: str
    pattern: str       # 形态名称
    timestamp: str     # 触发时间
    price: float
    detail: str        # 附加说明
    score: float = 0.0 # 可选评分
    count: int = 1     # 触发次数（第几次触发）
    is_high_priority: bool = False  # 是否高优先级
    signal: Optional[Any] = None # 标准化信号对象 (StandardSignal)
    
    def __repr__(self):
        count_suffix = f" (x{self.count})" if self.count > 1 else ""
        return f"PatternEvent({self.code} {self.name}: {self.pattern}{count_suffix} @ {self.price:.2f})"


class IntradayPatternDetector:
    """
    日内分时形态检测器
    
    接收分时数据流，检测日内形态，触发回调或发布到信号总线
    """
    
    # 支持的形态列表
    PATTERNS = [
        'auction_high_open',    # 竞价高开
        'gap_up',               # 跳空高开
        'low_open_high_walk',   # 低开走高
        'open_is_low',          # 开盘最低
        'open_is_low_volume',   # 开盘最低+带量 (符合用户需求的核心信号)
        'nlow_is_low_volume',   # nlow最低价+带量 (日内新低后反转)
        'low_open_breakout',    # 低开高走突破确认 (突破昨高/平台后二次信号)
        'instant_pullback',     # 瞬间回踩支撑线
        'shrink_sideways',      # 缩量横盘
        'pullback_upper',       # 回踩upper
        'high_drop',            # 冲高回落
        'top_signal',           # 顶部信号
        'master_momentum',      # 核心主升 (VWAP 支撑, 强趋势)
        'open_low_retest',      # 开盘回踩 (开盘≈最低, 缓慢上行)
        'high_sideways_break',  # 横盘突破 (大涨后横盘不破均线再拉升)
        'bull_trap_exit',       # 诱多跑路 (快速拉升后跌破均线)
        'momentum_failure',     # 主升转弱 (之前是主升，现在破位)
        'strong_auction_open',  # 强力竞价 (高开+强结构+历史联动)
    ]
    
    # 形态中文名映射
    PATTERN_NAMES = {
        'auction_high_open': '竞价高开',
        'gap_up': '跳空高开',
        'low_open_high_walk': '低开走高',
        'open_is_low': '开盘最低',
        'open_is_low_volume': '开盘最低带量',
        'nlow_is_low_volume': '日低反转带量',
        'low_open_breakout': '低开突破',
        'instant_pullback': '回踩支撑',
        'shrink_sideways': '缩量横盘',
        'pullback_upper': '回踩上轨',
        'high_drop': '冲高回落',
        'top_signal': '顶部信号',
        'master_momentum': '核心主升',
        'open_low_retest': '开盘回踩',
        'high_sideways_break': '横盘突破',
        'bull_trap_exit': '诱多跑路',
        'momentum_failure': '主升转弱',
        'strong_auction_open': '强力竞价',
    }
    
    # ⚡ [NEW] 信号优先级映射 (数值越小优先级越高)
    PRIORITY_MAP = {
        # 级别 1: 极端风险 (跑路/顶部)
        'bull_trap_exit': 10,
        'top_signal': 15,
        # 级别 2: 趋势转弱 (破位/风险)
        'momentum_failure': 20,
        'high_drop': 25,
        # 级别 3: 核心机会 (主升/强竞价/横盘突破)
        'master_momentum': 30,
        'strong_auction_open': 35,
        'high_sideways_break': 38,
        # 级别 4: 进阶机会 (带量/突破)
        'open_is_low_volume': 40,
        'nlow_is_low_volume': 45,
        'low_open_breakout': 50,
        # 级别 5: 基础机会 (低开走高/开盘最低)
        'low_open_high_walk': 60,
        'open_is_low': 65,
        'open_low_retest': 70,
        # 级别 6: 基础事件
        'auction_high_open': 80,
        'gap_up': 85,
        'instant_pullback': 90,
        'pullback_upper': 95,
        'shrink_sideways': 100,
    }
    
    def __init__(self, cooldown: int = 60, publish_to_bus: bool = True):
        """
        Args:
            cooldown: 同一形态同一股票的冷却时间（秒）
            publish_to_bus: 是否发布到信号总线
        """
        self.on_pattern: Optional[Callable[[PatternEvent], None]] = None
        self._cache: Dict[str, dict] = {}  # code_pattern -> {ts, count, ...}
        self._cooldown = cooldown
        self._publish_to_bus = publish_to_bus and HAS_SIGNAL_BUS
        
        # 可配置的检测开关
        self.enabled_patterns = set(self.PATTERNS)
        
        # 信号计数跟踪 (key: "code_pattern" -> count for today)
        self._signal_counts: Dict[str, int] = {}
    
    def enable_pattern(self, pattern: str) -> None:
        """启用特定形态检测"""
        if pattern in self.PATTERNS:
            self.enabled_patterns.add(pattern)
    
    def disable_pattern(self, pattern: str) -> None:
        """禁用特定形态检测"""
        self.enabled_patterns.discard(pattern)
    
    def update(self, code: str, name: str, tick_df: Optional[pd.DataFrame], 
               day_row: pd.Series, prev_close: float,
               current_time: Optional[dt_time] = None) -> List[PatternEvent]:
        """
        每次收到新分时数据后调用
        
        Args:
            code: 股票代码
            name: 股票名称
            tick_df: 分时数据 (ticktime, price, volume, ...)
            day_row: 当日日K数据 (open, high, low, close, upper, ma5, ...)
            prev_close: 昨收
            current_time: 手动指定时间 (用于测试/回检)
            
        Returns:
            检测到的形态事件列表
        """
        events: List[PatternEvent] = []
        
        # 使用传入时间或当前系统时间
        now_time = current_time if current_time else datetime.now().time()
        
        # 1. 竞价高开 / 跳空高开 (仅 9:25-9:35 判断 - 9:25 集合竞价结束出的开盘价)
        if 'auction_high_open' in self.enabled_patterns or 'gap_up' in self.enabled_patterns:
            events.extend(self._check_open_patterns(code, name, day_row, prev_close, now_time))
        
        # --- 🕒 核心时间过滤：9:25 之前的集合竞价数据不作为分时形态判断依据 ---
        if now_time < dt_time(9, 25):
            return []

        # 2. 低开走高 / 开盘最低 (含带量和突破确认迭代信号)
        low_open_patterns = {'low_open_high_walk', 'open_is_low', 'open_is_low_volume', 
                             'nlow_is_low_volume', 'low_open_breakout'}
        if low_open_patterns & self.enabled_patterns:
            events.extend(self._check_low_open_patterns(code, name, tick_df, day_row, prev_close))
        
        # 3. 核心主升 (VWAP 核心逻辑)
        if 'master_momentum' in self.enabled_patterns:
            events.extend(self._check_master_momentum(code, name, tick_df, day_row, prev_close))
            
        # 4. 开盘回踩 nlow
        if 'open_low_retest' in self.enabled_patterns:
            events.extend(self._check_open_low_retest(code, name, tick_df, day_row, prev_close))


        # 5. 横盘突破 (暴力拉升后横盘)
        if 'high_sideways_break' in self.enabled_patterns:
            events.extend(self._check_high_sideways_break(code, name, tick_df, day_row, prev_close))

        # 6. 回踩支撑/上轨
        if 'instant_pullback' in self.enabled_patterns:
            events.extend(self._check_instant_pullback(code, name, tick_df, day_row))
        
        if 'pullback_upper' in self.enabled_patterns:
            events.extend(self._check_pullback_upper(code, name, day_row))

        # 7. 风险跑路信号 (诱多/破位)
        if 'bull_trap_exit' in self.enabled_patterns:
            events.extend(self._check_bull_trap_exit(code, name, tick_df, day_row, prev_close))
        
        # 8. 缩量横盘 / 冲高回落 / 顶部信号
        if 'shrink_sideways' in self.enabled_patterns:
            events.extend(self._check_shrink_sideways(code, name, tick_df, day_row))
        
        # 5. 回踩 upper
        if 'pullback_upper' in self.enabled_patterns:
            events.extend(self._check_pullback_upper(code, name, day_row))
        
        # 6. 冲高回落
        if 'high_drop' in self.enabled_patterns:
            events.extend(self._check_high_drop(code, name, tick_df, day_row))
        
        # 7. 顶部信号（综合评分）
        if 'top_signal' in self.enabled_patterns:
            events.extend(self._check_top_signal(code, name, tick_df, day_row, prev_close))
        
        # ⚡ [NEW] 信号冲突抑制与优先级过滤
        if len(events) > 1:
            # 1. 优先级排序
            events.sort(key=lambda x: self.PRIORITY_MAP.get(x.pattern, 999))
            
            # 2. 冲突抑制逻辑：如果存在级别 1-2 的风险信号，则自动抑制所有级别 >= 3 的机会信号
            highest_p = self.PRIORITY_MAP.get(events[0].pattern, 999)
            if highest_p <= 25: # 风险信号 (bull_trap_exit, top_signal, momentum_failure, high_drop)
                # 仅保留风险信号，过滤掉机会信号
                events = [ev for ev in events if self.PRIORITY_MAP.get(ev.pattern, 999) <= 25]
            
            # 3. 精简化：同一时刻同一股票仅保留优先级最高的一个信号 (避免播报轰炸)
            events = events[:1]

        # 触发回调和发布
        notified_events: List[PatternEvent] = []
        for ev in events:
            should_notify, count = self._should_notify(code, ev.pattern)
            
            # 更新事件的计数
            ev.count = count
            if count > 1:
                ev.detail = f"{ev.detail} (第{count}次)"
            
            if should_notify:
                notified_events.append(ev)
                # 回调
                if self.on_pattern:
                    try:
                        self.on_pattern(ev)
                    except Exception as e:
                        logger.error(f"Pattern callback error: {e}")
                
                # 发布到信号总线
                if self._publish_to_bus:
                    if HAS_STANDARD_SIGNAL:
                        # 转换并发布标准化信号
                        std_signal = StandardSignal(
                            code=ev.code,
                            name=ev.name,
                            type=SignalBus.EVENT_PATTERN,
                            subtype=ev.pattern,
                            price=ev.price,
                            timestamp=ev.timestamp,
                            score=ev.score,
                            count=ev.count,
                            detail=ev.detail,
                            source="IntradayPatternDetector",
                            is_high_priority=ev.is_high_priority
                        )
                        ev.signal = std_signal # 绑定到事件上供回调使用
                        publish_standard_signal(std_signal)
                    else:
                        # 回退到原始 publish_pattern (如果在 signal_bus 中定义了且未被删除)
                        try:
                            from signal_bus import publish_pattern
                            publish_pattern(
                                source="IntradayPatternDetector",
                                code=ev.code,
                                name=ev.name,
                                pattern=ev.pattern,
                                price=ev.price,
                                detail=ev.detail
                            )
                        except ImportError:
                            pass
        
        return notified_events
    
    def _should_notify(self, code: str, pattern: str) -> tuple[bool, int]:
        """
        冷却判断并更新计数
        
        Returns:
            (should_notify, count): 是否应该通知, 当前累计次数
        """
        now = datetime.now().timestamp()
        key = f"{code}_{pattern}"
        cached = self._cache.get(key, {})
        last_ts = cached.get('ts', 0)
        
        # 获取当前累计次数 (不立即累加)
        current_count = self._signal_counts.get(key, 0)
        
        if now - last_ts < self._cooldown:
            # ⚡ [FIX] 在冷却期内，不更新计数，不通知
            return False, current_count
        
        # 冷却期已过，累加次数，重置缓存并通知
        count = current_count + 1
        self._signal_counts[key] = count
        self._cache[key] = {'ts': now, 'count': count}
        return True, count
    
    def get_signal_count(self, code: str, pattern: str) -> int:
        """获取某信号的当日触发次数"""
        key = f"{code}_{pattern}"
        return self._signal_counts.get(key, 0)
    
    def reset_daily_counts(self):
        """重置每日计数（应在开盘前调用）"""
        self._signal_counts.clear()
        logger.info("IntradayPatternDetector: Daily signal counts reset.")
    
    # ========== 具体形态检测方法 ==========
    
    def _check_open_patterns(self, code: str, name: str, 
                             day_row: pd.Series, prev_close: float,
                             now_time: Optional[dt_time] = None) -> List[PatternEvent]:
        """竞价高开 / 跳空高开"""
        events = []
        if now_time is None:
            now_time = datetime.now().time()
        
        # 仅在 9:25-9:35 判断
        if not (dt_time(9, 25) <= now_time <= dt_time(9, 35)):
            return events
        
        open_price = float(day_row.get('open', 0))
        if open_price <= 0 or prev_close <= 0:
            return events
        
        gap_pct = (open_price - prev_close) / prev_close * 100
        
        if gap_pct >= 3.0 and 'gap_up' in self.enabled_patterns:
            events.append(PatternEvent(
                code=code, name=name, pattern='gap_up',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=open_price,
                detail=f"跳空高开 +{gap_pct:.1f}%"
            ))
        elif gap_pct >= 1.0 and 'auction_high_open' in self.enabled_patterns:
            events.append(PatternEvent(
                code=code, name=name, pattern='auction_high_open',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=open_price,
                detail=f"竞价高开 +{gap_pct:.1f}%"
            ))

        # --- [NEW] 强力竞价 (strong_auction_open) ---
        if 'strong_auction_open' in self.enabled_patterns and gap_pct >= 2.0:
            low_p = float(day_row.get('low', 0))
            trends = float(day_row.get('TrendS', 0))
            win_count = int(day_row.get('win', 0))
            
            # 1. 结构检查: Open 近似等于 Low (无下影线或极短下影线)
            is_open_low = low_p >= open_price * 0.998 # 0.2% 容错
            
            # 2. 趋势背景: 昨日 TrendS > 60 (回踩支撑后的启动)
            is_strong_trend = trends > 60
            
            if is_open_low and is_strong_trend:
                score = 80 + min(win_count * 5, 20) # 加上连板加成
                detail = f"强力竞价: 高开{gap_pct:.1f}%+Open≈Low"
                if win_count > 0:
                    detail += f" (Win {win_count})"
                events.append(PatternEvent(
                    code=code, name=name, pattern='strong_auction_open',
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    price=open_price,
                    detail=detail
                ))
        
        return events
    
    def _check_low_open_patterns(self, code: str, name: str, 
                                  tick_df: Optional[pd.DataFrame],
                                  day_row: pd.Series, prev_close: float) -> List[PatternEvent]:
        """低开走高 / 开盘最低 (带量迭代 + 突破确认)"""
        events = []
        
        open_price = float(day_row.get('open', 0))
        current_price = float(day_row.get('close', day_row.get('trade', 0)))
        day_low = float(day_row.get('low', 0))
        day_high = float(day_row.get('high', 0))
        
        # === 量能指标 ===
        volume = float(day_row.get('volume', 0))  # 今日成交量/昨日成交量比
        ratio = float(day_row.get('ratio', 0))    # 换手率
        amount = float(day_row.get('amount', 0))  # 成交额
        nclose = amount / volume if volume > 0 else 0  # 均价 (VWAP)
        
        if open_price <= 0 or prev_close <= 0 or current_price <= 0:
            return events
        
        open_gap = (open_price - prev_close) / prev_close * 100
        is_volume_qualified = volume > 1.0 or ratio > 2.5  # 放量条件：量比>1 或 换手>2.5%
        
        # --- 状态缓存 (用于突破确认迭代) ---
        state_key = f"{code}_low_open_state"
        if state_key not in self._cache:
            self._cache[state_key] = {
                'base_triggered': False,
                'open_price': 0,
                'breakout_signaled': False,
                'prev_high_break': False,
                'retest_count': 0
            }
        state = self._cache[state_key]
        
        # === 获取历史高点数据 ===
        ma5 = float(day_row.get('ma5d', day_row.get('ma5', 0)))
        ma10 = float(day_row.get('ma10d', day_row.get('ma10', 0)))
        ma20 = float(day_row.get('ma20d', day_row.get('ma20', 0)))
        high4 = float(day_row.get('high4', 0))  # 4日最高
        max5 = float(day_row.get('max5', day_row.get('high5', 0)))  # 5日最高
        lasth1d = float(day_row.get('lasth1d', prev_close * 1.05))  # 昨日最高
        
        # ====================================================================
        # ⭐ 1. 低开走高: 开盘低于昨收 1%+, 当前价高于开盘 2%+
        # ====================================================================
        if open_gap <= -1.0 and current_price > open_price * 1.02:
            # 起点分级
            start_level = ""
            if ma5 > 0 and abs(open_price - ma5) / ma5 < 0.015:
                start_level = "MA5"
            elif ma10 > 0 and abs(open_price - ma10) / ma10 < 0.015:
                start_level = "MA10"
            elif ma20 > 0 and abs(open_price - ma20) / ma20 < 0.02:
                start_level = "MA20"
            elif open_price < day_low * 1.01:
                start_level = "日低"
            
            # 高度分级
            height_levels = []
            if current_price > prev_close:
                height_levels.append("昨收")
            if high4 > 0 and current_price > high4:
                height_levels.append("4日高")
            if max5 > 0 and current_price > max5:
                height_levels.append("5日高")
            
            height_level = ",".join(height_levels[-2:]) if height_levels else f"+{(current_price - open_price) / open_price * 100:.1f}%"
            
            detail_parts = [f"低开{open_gap:.1f}%"]
            if start_level:
                detail_parts.append(f"@{start_level}")
            detail_parts.append(f"走高至{height_level}")
            
            events.append(PatternEvent(
                code=code, name=name, pattern='low_open_high_walk',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=current_price,
                detail="".join(detail_parts)
            ))
            
            # 记录触发状态 (用于后续突破确认)
            state['base_triggered'] = True
            state['open_price'] = open_price
        
        # ====================================================================
        # ⭐ 2. 开盘最低带量 (open_is_low_volume) - 用户核心需求
        # ====================================================================
        is_open_is_low = abs(day_low - open_price) < 0.01 or (open_price > 0 and abs(day_low - open_price) / open_price < 0.002)
        is_rising = current_price > open_price * 1.01
        is_above_vwap = nclose > 0 and current_price >= nclose * 0.998  # 在均价线上方
        
        if 'open_is_low' in self.enabled_patterns:
            if is_open_is_low and is_rising:
                events.append(PatternEvent(
                    code=code, name=name, pattern='open_is_low',
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    price=current_price,
                    detail="开盘最低,持续上行"
                ))
        
        if 'open_is_low_volume' in self.enabled_patterns:
            if is_open_is_low and is_rising and is_volume_qualified and is_above_vwap:
                vol_desc = f"量比{volume:.1f}" if volume > 0 else f"换手{ratio:.1f}%"
                events.append(PatternEvent(
                    code=code, name=name, pattern='open_is_low_volume',
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    price=current_price,
                    detail=f"★开盘即最低+带量({vol_desc})+均线上方",
                    is_high_priority=True  # 核心信号,高优先级
                ))
                state['base_triggered'] = True
                state['open_price'] = open_price
        
        # ====================================================================
        # ⭐ 3. 日内低点带量反转 (nlow_is_low_volume)
        # ====================================================================
        if 'nlow_is_low_volume' in self.enabled_patterns:
            # nlow: 日内最低价 ≈ 当前价的最近最低 (已触底后反弹)
            # 条件: 当前价已从日低反弹 1%+, 且带量, 且在均价线上方
            if day_low > 0 and current_price > day_low * 1.01 and is_volume_qualified:
                # 额外条件: 日低必须低于开盘价 (说明有过探底)
                if day_low < open_price * 0.995 and is_above_vwap:
                    rebound_pct = (current_price - day_low) / day_low * 100
                    vol_desc = f"量比{volume:.1f}" if volume > 0 else f"换手{ratio:.1f}%"
                    events.append(PatternEvent(
                        code=code, name=name, pattern='nlow_is_low_volume',
                        timestamp=datetime.now().strftime('%H:%M:%S'),
                        price=current_price,
                        detail=f"★日低反转+{rebound_pct:.1f}%({vol_desc})+站上均价",
                        is_high_priority=True
                    ))
        
        # ====================================================================
        # ⭐ 4. 突破确认信号 (low_open_breakout) - 二次迭代信号
        # ====================================================================
        if 'low_open_breakout' in self.enabled_patterns and state.get('base_triggered', False):
            # 4.1 突破昨日高点
            if lasth1d > 0 and current_price > lasth1d and not state.get('prev_high_break', False):
                state['prev_high_break'] = True
                events.append(PatternEvent(
                    code=code, name=name, pattern='low_open_breakout',
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    price=current_price,
                    detail=f"低开高走突破昨高({lasth1d:.2f})",
                    is_high_priority=True
                ))
            
            # 4.2 突破平台高点 (5日高)
            if max5 > 0 and current_price > max5 and not state.get('breakout_signaled', False):
                state['breakout_signaled'] = True
                events.append(PatternEvent(
                    code=code, name=name, pattern='low_open_breakout',
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    price=current_price,
                    detail=f"低开高走突破平台({max5:.2f})",
                    is_high_priority=True
                ))
            
            # 4.3 回踩不破开盘价后再次拉升 (迭代: 仅触发一次)
            saved_open = state.get('open_price', 0)
            if saved_open > 0 and state.get('retest_count', 0) == 0:
                # 条件: 日低接近开盘价 (回踩) 但未破, 且当前已反弹
                if day_low >= saved_open * 0.995 and current_price > saved_open * 1.02:
                    state['retest_count'] = 1
                    events.append(PatternEvent(
                        code=code, name=name, pattern='low_open_breakout',
                        timestamp=datetime.now().strftime('%H:%M:%S'),
                        price=current_price,
                        detail="低开回踩不破开盘价后再拉升"
                    ))
        
        # 保存状态
        self._cache[state_key] = state
        
        return events

    
    def _check_instant_pullback(self, code: str, name: str,
                                 tick_df: Optional[pd.DataFrame],
                                 day_row: pd.Series) -> List[PatternEvent]:
        """瞬间回踩支撑线"""
        events = []
        if tick_df is None or len(tick_df) < 10:
            return events
        
        # 支撑线: MA5
        ma5 = float(day_row.get('ma5', day_row.get('ma5d', 0)))
        if ma5 <= 0:
            return events
        
        # 获取价格序列
        price_col = 'price' if 'price' in tick_df.columns else 'close'
        if price_col not in tick_df.columns:
            return events
            
        prices = tick_df[price_col].values
        if len(prices) < 5:
            return events
        
        # 检测: 最近 5 分钟内触及 MA5 ±0.5% 并反弹
        recent = prices[-5:]
        touched = any(abs(p - ma5) / ma5 < 0.005 for p in recent[:-1])
        rebounded = recent[-1] > ma5 * 1.005 if touched else False
        
        if touched and rebounded:
            events.append(PatternEvent(
                code=code, name=name, pattern='instant_pullback',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=float(recent[-1]),
                detail=f"瞬间回踩MA5({ma5:.2f})后反弹"
            ))
        
        return events
    
    def _check_shrink_sideways(self, code: str, name: str,
                                tick_df: Optional[pd.DataFrame],
                                day_row: pd.Series) -> List[PatternEvent]:
        """缩量横盘"""
        events = []
        
        # 仅在 10:00 后判断
        now = datetime.now().time()
        if now < dt_time(10, 0):
            return events
        
        if tick_df is None or len(tick_df) < 30:
            return events
        
        price_col = 'price' if 'price' in tick_df.columns else 'close'
        if price_col not in tick_df.columns or 'volume' not in tick_df.columns:
            return events
        
        recent = tick_df.tail(30)
        high = recent[price_col].max()
        low = recent[price_col].min()
        avg_price = recent[price_col].mean()
        
        if avg_price <= 0:
            return events
        
        amplitude = (high - low) / avg_price * 100
        
        # 横盘: 振幅 < 1%
        if amplitude < 1.0:
            # 缩量: 当前成交量 < 日均量 * 0.5
            vol_ma = float(day_row.get('vol_ma5', day_row.get('volume', 0)))
            current_vol = float(day_row.get('volume', 0))
            if vol_ma > 0 and current_vol < vol_ma * 0.5:
                events.append(PatternEvent(
                    code=code, name=name, pattern='shrink_sideways',
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    price=float(avg_price),
                    detail=f"缩量横盘,振幅{amplitude:.2f}%"
                ))
        
        return events
    
    def _check_pullback_upper(self, code: str, name: str,
                               day_row: pd.Series) -> List[PatternEvent]:
        """回踩 upper (布林上轨)"""
        events = []
        upper = float(day_row.get('upper', 0))
        current = float(day_row.get('close', day_row.get('trade', 0)))
        
        if upper <= 0 or current <= 0:
            return events
        
        # 回踩 upper: 当前价在 upper ±1% 范围内
        diff_pct = abs(current - upper) / upper
        if diff_pct < 0.01:
            events.append(PatternEvent(
                code=code, name=name, pattern='pullback_upper',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=current,
                detail=f"回踩布林上轨 {upper:.2f}"
            ))
        
        return events
    
    def _check_high_drop(self, code: str, name: str,
                          tick_df: Optional[pd.DataFrame],
                          day_row: pd.Series) -> List[PatternEvent]:
        """冲高回落"""
        events = []
        
        # 仅在 10:00 后判断
        now = datetime.now().time()
        if now < dt_time(10, 0):
            return events
        
        day_high = float(day_row.get('high', 0))
        current = float(day_row.get('close', day_row.get('trade', 0)))
        open_price = float(day_row.get('open', 0))
        
        if day_high <= 0 or open_price <= 0 or current <= 0:
            return events
        
        # 冲高回落: 最高价较开盘涨 3%+, 但当前价回落至开盘附近
        up_pct = (day_high - open_price) / open_price * 100 if open_price > 0 else 0
        drop_pct = (day_high - current) / day_high * 100 if day_high > 0 else 0
        
        if up_pct >= 3.0 and drop_pct >= 2.0:
            events.append(PatternEvent(
                code=code, name=name, pattern='high_drop',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=current,
                detail=f"冲高{up_pct:.1f}%回落{drop_pct:.1f}%"
            ))
        
        return events
    
    def _check_top_signal(self, code: str, name: str,
                           tick_df: Optional[pd.DataFrame],
                           day_row: pd.Series,
                           prev_close: float) -> List[PatternEvent]:
        """
        顶部信号综合评分
        
        评分项（满分100）：
        - 冲高回落: 30分
        - 量价背离: 25分
        - 十字星: 20分
        - 长上影: 15分
        - 均线拐头: 10分
        
        ≥60分触发顶部信号
        """
        events = []
        score = 0.0
        details = []
        
        open_price = float(day_row.get('open', 0))
        high = float(day_row.get('high', 0))
        low = float(day_row.get('low', 0))
        close = float(day_row.get('close', day_row.get('trade', 0)))
        volume = float(day_row.get('volume', 0))
        
        if open_price <= 0 or close <= 0 or high <= 0:
            return events
        
        # 1. 冲高回落 (30分)
        if high > 0 and open_price > 0:
            up_pct = (high - open_price) / open_price * 100
            drop_pct = (high - close) / high * 100 if high > 0 else 0
            if up_pct >= 3.0 and drop_pct >= 2.0:
                score += 30
                details.append(f"冲高回落{drop_pct:.1f}%")
        
        # 2. 量价背离 (25分) - 简化：价创新高但量萎缩
        vol_ma = float(day_row.get('vol_ma5', volume))
        if vol_ma > 0 and volume < vol_ma * 0.7:
            prev_high = float(day_row.get('high4', high))  # 假设有前高字段
            if close > prev_close * 1.03:  # 涨幅较大
                score += 25
                details.append("量价背离")
        
        # 3. 十字星 (20分)
        body = abs(close - open_price)
        amplitude = high - low
        if amplitude > 0 and body < amplitude * 0.2:
            score += 20
            details.append("十字星")
        
        # 4. 长上影 (15分)
        upper_shadow = high - max(open_price, close)
        if body > 0 and upper_shadow > body * 2:
            score += 15
            details.append("长上影")
        
        # 5. 均线拐头 (10分)
        ma5 = float(day_row.get('ma5', day_row.get('ma5d', 0)))
        ma5_prev = float(day_row.get('ma5_prev', ma5))  # 假设有前日MA5
        if ma5 < ma5_prev and ma5_prev > 0:
            score += 10
            details.append("均线拐头")
        
        # ≥60分触发
        if score >= 60:
            events.append(PatternEvent(
                code=code, name=name, pattern='top_signal',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=close,
                detail=f"顶部信号({score:.0f}分): {','.join(details)}",
                score=score
            ))
        
        return events

    def _check_master_momentum(self, code: str, name: str,
                               tick_df: Optional[pd.DataFrame],
                               day_row: pd.Series, prev_close: float) -> List[PatternEvent]:
        """
        核心主升结构检测
        1. 高开 (Open > Prev Close)
        2. 昨日回踩支撑 (MA5/10/上轨) 且收盘稳住
        3. 沿着均价线 (VWAP) 上行，绝不跌破均价线
        """
        events = []
        open_p = float(day_row.get('open', 0))
        curr_p = float(day_row.get('close', day_row.get('trade', 0)))
        amount = float(day_row.get('amount', 0))
        volume = float(day_row.get('volume', 0))
        
        if open_p <= 0 or prev_close <= 0 or curr_p <= open_p:
            return events

        # --- A. 基础过滤：必须大于昨日收盘价 (高开或平开高走) ---
        if open_p < prev_close and curr_p < prev_close:
            return events

        # --- B. 昨日状态分析：昨日是否回踩支撑线 ---
        # 假设 day_row 包含昨日的一些状态或直接计算
        # 简单判定：昨日最高点曾触及 MA5/10 附近，或昨日收盘价在支撑线上方
        ma5 = float(day_row.get('ma5', 0))
        ma10 = float(day_row.get('ma10', 0))
        y_low = float(day_row.get('low', 0)) # 这个其实是今日低点，需要历史数据。
        # 注意：day_row 通常是 snapshot，包含了很多由 strategy.py 填写的历史指标
        # 这里的 ma5/ma10 是今日移动平均，反映了昨日的趋势强度
        trend_raw = float(day_row.get('TrendS', 50))
        
        # 如果 TrendS (趋势强度) 较低，可能不是强势股回踩后上涨
        if trend_raw < 60:
            return events

        # --- C. VWAP 核心逻辑：分时线上行且不破均线 ---
        vwap = amount / volume if volume > 0 else 0
        if vwap <= 0:
            return events
            
        # 1. 当前必须在均线上方
        is_above_vwap = curr_p >= vwap * 0.998 # 允许微小误差
        
        key = f"{code}_master_momentum_state"
        if key not in self._cache:
            self._cache[key] = {'ever_broken': False, 'failure_signaled': False}
        state = self._cache[key]

        # 核心逻辑：一旦跌破，标记永久失效
        if not is_above_vwap:
            if not state['ever_broken']:
                state['ever_broken'] = True
                # [NEW] 触发一次“主升转弱”信号
                if 'momentum_failure' in self.enabled_patterns:
                    events.append(PatternEvent(
                        code=code, name=name, pattern='momentum_failure',
                        timestamp=datetime.now().strftime('%H:%M:%S'),
                        price=curr_p,
                        detail=f"主升转弱: 跌破均线支撑({vwap:.2f}), 注意跑路!",
                        is_high_priority=True
                    ))
            return events

        if state['ever_broken']:
            return events
            
        # 2. 判定强势结构：开盘即最低 (格外注意)
        day_low = float(day_row.get('low', 0))
        is_open_low = abs(open_p - day_low) / open_p < 0.001 if open_p > 0 else False
        
        # 3. 判定历史连板/连阳晋级 (win 计数)
        win_count = int(day_row.get('win', 0))
        win_msg = f" win {win_count} 进 {win_count+1}" if win_count > 0 else ""
        
        # 4. 判定有效主升区间 (偏离 0.5% ~ 3.5%)
        bias = (curr_p - vwap) / vwap
        if 0.005 < bias < 0.035:
            detail = f"核心主升{win_msg}: 偏离均线{bias:+.1%}"
            if is_open_low:
                detail = f"分时强结构(开盘即最低){win_msg}, 偏离均线{bias:+.1%}"
            
            events.append(PatternEvent(
                code=code, name=name, pattern='master_momentum',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=curr_p,
                detail=detail,
                is_high_priority=True if is_open_low else False
            ))
                
        return events

    def _check_open_low_retest(self, code: str, name: str,
                                tick_df: Optional[pd.DataFrame],
                                day_row: pd.Series, prev_close: float) -> List[PatternEvent]:
        """开盘回踩 (开盘≈最低, 缓慢上行)"""
        events = []
        open_p = float(day_row.get('open', 0))
        low_p = float(day_row.get('low', 0))
        curr_p = float(day_row.get('close', day_row.get('trade', 0)))
        
        if open_p <= 0 or curr_p <= 0:
            return events
            
        # 1. 判定开盘即低点 (允许 0.1% 误差)
        is_open_is_low = abs(open_p - low_p) / open_p < 0.001 if open_p > 0 else False
        
        # 2. 判定上涨中
        if is_open_is_low and curr_p > open_p * 1.01:
            events.append(PatternEvent(
                code=code, name=name, pattern='open_low_retest',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=curr_p,
                detail=f"开盘即低点, 稳步拉升至 +{(curr_p-prev_close)/prev_close:+.1%}"
            ))
            
        return events

    def _check_bull_trap_exit(self, code: str, name: str,
                             tick_df: Optional[pd.DataFrame],
                             day_row: pd.Series, prev_close: float) -> List[PatternEvent]:
        """诱多破位检测 (早盘错误修正)"""
        events = []
        open_p = float(day_row.get('open', 0))
        high_p = float(day_row.get('high', 0))
        curr_p = float(day_row.get('close', day_row.get('trade', 0)))
        amount = float(day_row.get('amount', 0))
        volume = float(day_row.get('volume', 0))
        vwap = amount / volume if volume > 0 else 0
        
        if open_p <= 0 or curr_p <= 0 or vwap <= 0:
            return events
            
        # 1. 检测是否曾经“诱多”：开盘后快速大涨 > 3%
        rising_pct = (high_p - open_p) / open_p * 100
        if rising_pct < 3.0:
            return events
            
        # 注意：此处 state 与 master_momentum 无关，独立判断
        key = f"{code}_bull_trap_state"
        if key not in self._cache:
            self._cache[key] = {'trap_triggered': False}
        
        state = self._cache[key]
        if state['trap_triggered']:
            return events
            
        # 2. 破位逻辑：大涨后跌破 VWAP 或 跌破开盘价
        if curr_p < vwap * 0.997 or curr_p < open_p * 0.995:
            state['trap_triggered'] = True
            events.append(PatternEvent(
                code=code, name=name, pattern='bull_trap_exit',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=curr_p,
                detail=f"诱多破位: 早盘大涨{rising_pct:.1f}%后跌破均线, 注意跑路!",
                is_high_priority=True
            ))
            
        return events

    def _check_high_sideways_break(self, code: str, name: str,
                                   tick_df: Optional[pd.DataFrame],
                                   day_row: pd.Series, prev_close: float) -> List[PatternEvent]:
        """暴力拉升后横盘不破位再突破"""
        events = []
        curr_p = float(day_row.get('close', day_row.get('trade', 0)))
        day_high = float(day_row.get('high', 0))
        amount = float(day_row.get('amount', 0))
        volume = float(day_row.get('volume', 0))
        vwap = amount / volume if volume > 0 else 0
        
        if curr_p <= 0 or vwap <= 0:
            return events
            
        # 1. 基础门槛：偏离 VWAP 且高于 VWAP
        if curr_p < vwap: return events
        
        key = f"{code}_high_sideways_break"
        if key not in self._cache:
            self._cache[key] = {'has_rally': False, 'max_p': 0.0, 'min_since_max': 999.0}
        
        # 确保关键键存在 (防止脏数据)
        if 'max_p' not in self._cache[key]:
            self._cache[key]['max_p'] = 0.0
        if 'min_since_max' not in self._cache[key]:
            self._cache[key]['min_since_max'] = 999.0
        
        state = self._cache[key]
        
        # 2. 检测暴力拉升 (今日涨幅 > 5% 或 单次快速拉升)
        pct = (curr_p - prev_close) / prev_close * 100
        if pct > 4.0:
            state['has_rally'] = True
            
        if not state['has_rally']:
            return events
            
        # 3. 检测横盘 (最高点回落极小，且始终高于 VWAP)
        if curr_p > state['max_p']:
            state['max_p'] = curr_p
            state['min_since_max'] = curr_p
        else:
            state['min_since_max'] = min(state['min_since_max'], curr_p)
            
        # 振幅统计 (从最高点至今回落幅度)
        drop_pct = (state['max_p'] - curr_p) / state['max_p'] * 100 if state['max_p'] > 0 else 0
        
        # 核心逻辑：大涨后回落 < 1.5% 且高于 VWAP 0.5%+
        if drop_pct < 1.5 and curr_p > vwap * 1.005:
            # 再次突破前高？
            if curr_p >= day_high * 0.998:
                events.append(PatternEvent(
                    code=code, name=name, pattern='high_sideways_break',
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    price=curr_p,
                    detail=f"暴力拉升后横盘不破均线, 再次挑战前高",
                    is_high_priority=True
                ))
        
        if curr_p < vwap:
            state['has_rally'] = False
            state['max_p'] = 0
            
        return events

        return events

    def get_stats(self) -> Dict[str, Any]:
        """获取检测器统计"""
        return {
            "enabled_patterns": list(self.enabled_patterns),
            "cooldown": self._cooldown,
            "cache_size": len(self._cache),
            "publish_to_bus": self._publish_to_bus
        }


if __name__ == "__main__":
    # 简单测试
    detector = IntradayPatternDetector()
    
    def test_handler(ev: PatternEvent):
        print(f"检测到形态: {ev}")
    
    detector.on_pattern = test_handler
    
    # 模拟数据
    day_row = pd.Series({
        'open': 10.0,
        'high': 10.5,
        'low': 9.8,
        'close': 10.3,
        'trade': 10.3,
        'volume': 1000000,
        'ma5': 10.1,
        'upper': 10.4
    })
    
    events = detector.update(
        code="000001",
        name="测试股",
        tick_df=None,
        day_row=day_row,
        prev_close=10.0
    )
    
    print(f"检测到 {len(events)} 个形态")
    print(f"统计: {detector.get_stats()}")
