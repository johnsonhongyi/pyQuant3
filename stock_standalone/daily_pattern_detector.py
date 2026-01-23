# -*- coding: utf-8 -*-
"""
DailyPatternDetector - 日K线形态检测器

功能：
1. 接收历史日K线数据 (DataFrame)
2. 检测典型形态：
    - big_bull: 大阳线 (涨幅>5%, 实体>70%, 放量)
    - v_shape: V型反转 (连续下跌后收复关键位)
    - low_open_pinbar: 低开长下影 (下影线>实体*2, 收盘>开盘)
    - vol_drying: 极度缩量 (成交量 < MA5*0.6, 振幅<1.5%)
    - n_day_rising: 连阳 (连续N天上涨)
3. 用于盘前筛选 (daily_strategy_loader) 和 盘中动态识别

使用方式：
    detector = DailyPatternDetector()
    events = detector.scan(df)
"""
from __future__ import annotations
import pandas as pd
from typing import List, Optional, Any, Callable
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class DailyPatternEvent:
    code: str
    name: str
    pattern: str
    date: str
    price: float
    detail: str
    score: float = 0.0

class DailyPatternDetector:
    
    # 形态中文名
    PATTERN_NAMES = {
        'big_bull': '大阳突破',
        'v_shape': 'V型反转',
        'low_open_pinbar': '低开金针',
        'vol_drying': '极度缩量',
        'n_day_rising': '多日连阳',
        'platform_break': '平台突破'
    }

    def __init__(self):
        self.on_pattern: Optional[Callable[[DailyPatternEvent], None]] = None

    def update(self, code: str, name: str, current_row: Any, prev_rows: Any) -> List[DailyPatternEvent]:
        """
        实时更新：根据当前日线行数据和历史数据判断形态
        """
        if current_row is None:
            return []
            
        events = []
        
        # 1. 大阳突破 (Big Bull) - 盘中也可识别
        events.extend(self._check_big_bull(code, name, current_row, prev_rows))
        
        # 2. 金针探底 / 锤子线
        events.extend(self._check_low_open_pinbar(code, name, current_row))
        
        # 3. 极度缩量 (通常盘尾或盘中量比低时判断)
        events.extend(self._check_vol_drying(code, name, current_row, prev_rows))

        # 4. V型反转 (Volunteer)
        if self.check_volunteer(code, current_row, prev_rows):
            events.append(DailyPatternEvent(
                code=code, name=name, pattern='v_shape',
                date=str(current_row.get('date', '')), price=float(current_row.get('close', 0)),
                detail="V型反转形态", score=80
            ))

        # 5. 平台突破
        if self.check_platform_break(code, current_row, prev_rows):
            events.append(DailyPatternEvent(
                code=code, name=name, pattern='platform_break',
                date=str(current_row.get('date', '')), price=float(current_row.get('close', 0)),
                detail="五日平台突破", score=75
            ))
        
        # 触发回调
        for ev in events:
            if self.on_pattern:
                try:
                    self.on_pattern(ev)
                except Exception: pass
                
        return events

    def scan(self, code: str, name: str, df: Any) -> List[DailyPatternEvent]:
        """
        扫描一只股票的所有形态
        """
        if df is None or len(df) < 5:
            return []
            
        events = []
        # 取最近一条数据进行判断 (假设 df 是按日期升序排列)
        last_row = df.iloc[-1]
        prev_rows = df.iloc[:-1]
        
        # 1. 大阳突破 (Big Bull)
        events.extend(self._check_big_bull(code, name, last_row, prev_rows))
        
        # 2. 低开金针 (Low Open Pinbar)
        events.extend(self._check_low_open_pinbar(code, name, last_row))
        
        # 3. 极度缩量 (Volume Drying)
        events.extend(self._check_vol_drying(code, name, last_row, prev_rows))
        
        # 4. 连阳判断
        events.extend(self._check_n_day_rising(code, name, df))
        
        return events

    def _check_big_bull(self, code: str, name: str, row: Any, prev_df: Any) -> List[DailyPatternEvent]:
        """大阳线检测"""
        pct = float(row.get('percent', 0))
        open_p = float(row.get('open', 0))
        close_p = float(row.get('close', 0))
        high_p = float(row.get('high', 0))
        low_p = float(row.get('low', 0))
        volume = float(row.get('volume', 0))
        
        # 条件：涨幅 > 5%, 且实体占总振幅 > 70% (非长影线)
        amplitude = high_p - low_p
        body = abs(close_p - open_p)
        
        if pct >= 5.0 and amplitude > 0 and (body / amplitude) > 0.7:
            # 辅助：放量检测 (成交量 > 过去5日均量 * 1.5)
            vol_ma5 = prev_df['volume'].tail(5).mean() if not prev_df.empty else 0
            detail = f"大阳涨{pct:.1f}%"
            score = pct * 10 
            
            if vol_ma5 > 0 and volume > vol_ma5 * 1.5:
                detail += " + 放量"
                score += 20
                
            return [DailyPatternEvent(
                code=code, name=name, pattern='big_bull',
                date=str(row.get('date', '')), price=close_p,
                detail=detail, score=score
            )]
        return []

    def _check_low_open_pinbar(self, code: str, name: str, row: Any) -> List[DailyPatternEvent]:
        """金针探底 (下影线长)"""
        open_p = float(row.get('open', 0))
        close_p = float(row.get('close', 0))
        low_p = float(row.get('low', 0))
        
        body = abs(close_p - open_p)
        lower_shadow = min(open_p, close_p) - low_p
        
        # 条件：下影线是实体的 2 倍以上，且收盘不跌
        if body > 0 and lower_shadow > body * 2 and close_p >= open_p:
            return [DailyPatternEvent(
                code=code, name=name, pattern='low_open_pinbar',
                date=str(row.get('date', '')), price=close_p,
                detail=f"金针探底 (下影{lower_shadow/body:.1f}倍)",
                score=60
            )]
        return []

    def _check_vol_drying(self, code: str, name: str, row: Any, prev_df: Any) -> List[DailyPatternEvent]:
        """极端缩量企稳"""
        volume = float(row.get('volume', 0))
        pct = float(row.get('percent', 0))
        
        vol_ma5 = prev_df['volume'].tail(5).mean() if not prev_df.empty else 0
        
        # 条件：成交量 < 5日均量 60%, 且涨跌幅绝对值 < 1.5%
        if vol_ma5 > 0 and volume < vol_ma5 * 0.6 and abs(pct) < 1.5:
            return [DailyPatternEvent(
                code=code, name=name, pattern='vol_drying',
                date=str(row.get('date', '')), price=float(row.get('close', 0)),
                detail=f"极度缩量({volume/vol_ma5*100:.0f}%) 企稳",
                score=50
            )]
        return []

    def _check_n_day_rising(self, code: str, name: str, df: Any) -> List[DailyPatternEvent]:
        """连阳检测"""
        if len(df) < 3: return []
        
        recent = df.tail(5)
        # 统计最近5天上涨的天数
        rising_days = 0
        for i in range(len(recent)):
            if recent.iloc[i]['percent'] > 0:
                rising_days += 1
            else:
                break # 必须是连续从今天往回数
        
        if rising_days >= 3:
            return [DailyPatternEvent(
                code=code, name=name, pattern='n_day_rising',
                date=str(df.iloc[-1].get('date', '')), price=float(df.iloc[-1].get('close', 0)),
                detail=f"{rising_days}连阳",
                score=40 + rising_days * 5
            )]
        return []

    def check_volunteer(self, code: str, current_row: Any, prev_rows: Any) -> bool:
        """
        检测 V型反转 (Volunteer) 形态
        """
        if prev_rows is None or (isinstance(prev_rows, pd.DataFrame) and prev_rows.empty):
            return False
            
        try:
            # 过去2天均跌，今日大涨
            df = prev_rows.tail(2)
            if len(df) < 2: return False
            
            p1_pct = float(df.iloc[0].get('percent', 0))
            p2_pct = float(df.iloc[1].get('percent', 0))
            curr_pct = float(current_row.get('percent', 0))
            
            # 连续两天跌幅 > 1.5%, 今日涨幅 > 4.5%
            if p1_pct < -1.5 and p2_pct < -1.5 and curr_pct > 4.5:
                return True
        except:
            pass
        return False

    def check_platform_break(self, code: str, current_row: Any, prev_rows: Any) -> bool:
        """
        检测 平台突破 (Platform Break)
        """
        if prev_rows is None or (isinstance(prev_rows, pd.DataFrame) and prev_rows.empty):
            return False
            
        try:
            # 过去5天振幅极小，今日放量突破
            df = prev_rows.tail(5)
            if len(df) < 5: return False
            
            high_max = df['high'].max()
            low_min = df['low'].min()
            base_price = df['close'].mean()
            
            # 5日振幅 < 6.5%
            if (high_max - low_min) / base_price < 0.065:
                curr_price = float(current_row.get('price', current_row.get('close', 0)))
                if curr_price > high_max * 1.015: # 突破平台高点 1.5%
                    return True
        except:
            pass
        return False

if __name__ == "__main__":
    # 模拟测试
    detector = DailyPatternDetector()
    test_df = pd.DataFrame([
        {'date': '2026-01-19', 'close': 10.0, 'open': 10.0, 'high': 10.1, 'low': 9.9, 'volume': 100, 'percent': 0},
        {'date': '2026-01-20', 'close': 10.1, 'open': 10.0, 'high': 10.2, 'low': 9.9, 'volume': 110, 'percent': 1},
        {'date': '2026-01-21', 'close': 10.2, 'open': 10.1, 'high': 10.3, 'low': 10.1, 'volume': 120, 'percent': 1},
        {'date': '2026-01-22', 'close': 11.0, 'open': 10.3, 'high': 11.0, 'low': 10.3, 'volume': 300, 'percent': 7.8},
    ])
    events = detector.scan("000001", "平安银行", test_df)
    for ev in events:
        print(f"[{ev.date}] {ev.name} ({ev.code}): {ev.pattern} - {ev.detail} Score={ev.score}")
