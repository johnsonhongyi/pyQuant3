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

# 尝试导入信号总线
try:
    from signal_bus import get_signal_bus, publish_pattern, SignalBus
    HAS_SIGNAL_BUS = True
except ImportError:
    HAS_SIGNAL_BUS = False
    logger.warning("signal_bus not found, pattern events will not be published to bus")


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
    
    def __repr__(self):
        return f"PatternEvent({self.code} {self.name}: {self.pattern} @ {self.price:.2f})"


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
        'instant_pullback',     # 瞬间回踩支撑线
        'shrink_sideways',      # 缩量横盘
        'pullback_upper',       # 回踩upper
        'high_drop',            # 冲高回落
        'top_signal',           # 顶部信号
    ]
    
    # 形态中文名映射
    PATTERN_NAMES = {
        'auction_high_open': '竞价高开',
        'gap_up': '跳空高开',
        'low_open_high_walk': '低开走高',
        'open_is_low': '开盘最低',
        'instant_pullback': '回踩支撑',
        'shrink_sideways': '缩量横盘',
        'pullback_upper': '回踩上轨',
        'high_drop': '冲高回落',
        'top_signal': '顶部信号',
    }
    
    def __init__(self, cooldown: int = 60, publish_to_bus: bool = True):
        """
        Args:
            cooldown: 同一形态同一股票的冷却时间（秒）
            publish_to_bus: 是否发布到信号总线
        """
        self.on_pattern: Optional[Callable[[PatternEvent], None]] = None
        self._cache: Dict[str, dict] = {}  # code_pattern -> {ts, ...}
        self._cooldown = cooldown
        self._publish_to_bus = publish_to_bus and HAS_SIGNAL_BUS
        
        # 可配置的检测开关
        self.enabled_patterns = set(self.PATTERNS)
    
    def enable_pattern(self, pattern: str) -> None:
        """启用特定形态检测"""
        if pattern in self.PATTERNS:
            self.enabled_patterns.add(pattern)
    
    def disable_pattern(self, pattern: str) -> None:
        """禁用特定形态检测"""
        self.enabled_patterns.discard(pattern)
    
    def update(self, code: str, name: str, tick_df: Optional[pd.DataFrame], 
               day_row: pd.Series, prev_close: float) -> List[PatternEvent]:
        """
        每次收到新分时数据后调用
        
        Args:
            code: 股票代码
            name: 股票名称
            tick_df: 分时数据 (ticktime, price, volume, ...)
            day_row: 当日日K数据 (open, high, low, close, upper, ma5, ...)
            prev_close: 昨收
            
        Returns:
            检测到的形态事件列表
        """
        events: List[PatternEvent] = []
        
        # 1. 竞价高开 / 跳空高开 (仅 9:25-9:35 判断)
        if 'auction_high_open' in self.enabled_patterns or 'gap_up' in self.enabled_patterns:
            events.extend(self._check_open_patterns(code, name, day_row, prev_close))
        
        # 2. 低开走高 / 开盘最低
        if 'low_open_high_walk' in self.enabled_patterns or 'open_is_low' in self.enabled_patterns:
            events.extend(self._check_low_open_patterns(code, name, tick_df, day_row, prev_close))
        
        # 3. 瞬间回踩支撑线
        if 'instant_pullback' in self.enabled_patterns:
            events.extend(self._check_instant_pullback(code, name, tick_df, day_row))
        
        # 4. 缩量横盘
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
        
        # 触发回调和发布
        for ev in events:
            if self._should_notify(code, ev.pattern):
                # 回调
                if self.on_pattern:
                    try:
                        self.on_pattern(ev)
                    except Exception as e:
                        logger.error(f"Pattern callback error: {e}")
                
                # 发布到信号总线
                if self._publish_to_bus:
                    publish_pattern(
                        source="IntradayPatternDetector",
                        code=ev.code,
                        name=ev.name,
                        pattern=ev.pattern,
                        price=ev.price,
                        detail=ev.detail
                    )
        
        return events
    
    def _should_notify(self, code: str, pattern: str) -> bool:
        """冷却判断"""
        now = datetime.now().timestamp()
        key = f"{code}_{pattern}"
        last = self._cache.get(key, {}).get('ts', 0)
        if now - last < self._cooldown:
            return False
        self._cache[key] = {'ts': now}
        return True
    
    # ========== 具体形态检测方法 ==========
    
    def _check_open_patterns(self, code: str, name: str, 
                             day_row: pd.Series, prev_close: float) -> List[PatternEvent]:
        """竞价高开 / 跳空高开"""
        events = []
        now = datetime.now().time()
        
        # 仅在 9:25-9:35 判断
        if not (dt_time(9, 25) <= now <= dt_time(9, 35)):
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
        
        return events
    
    def _check_low_open_patterns(self, code: str, name: str, 
                                  tick_df: Optional[pd.DataFrame],
                                  day_row: pd.Series, prev_close: float) -> List[PatternEvent]:
        """低开走高 / 开盘最低"""
        events = []
        
        open_price = float(day_row.get('open', 0))
        current_price = float(day_row.get('close', day_row.get('trade', 0)))
        day_low = float(day_row.get('low', 0))
        
        if open_price <= 0 or prev_close <= 0 or current_price <= 0:
            return events
        
        open_gap = (open_price - prev_close) / prev_close * 100
        
        # 低开走高: 开盘低于昨收 1%+, 当前价高于开盘 2%+
        if open_gap <= -1.0 and current_price > open_price * 1.02:
            events.append(PatternEvent(
                code=code, name=name, pattern='low_open_high_walk',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=current_price,
                detail=f"低开{open_gap:.1f}%走高"
            ))
        
        # 开盘最低: 当前价等于今日最低且等于开盘价
        if abs(day_low - open_price) < 0.01 and current_price > open_price * 1.005:
            events.append(PatternEvent(
                code=code, name=name, pattern='open_is_low',
                timestamp=datetime.now().strftime('%H:%M:%S'),
                price=current_price,
                detail="开盘最低,持续上行"
            ))
        
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
