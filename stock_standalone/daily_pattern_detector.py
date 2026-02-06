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


import pandas as pd
import numpy as np


def merge_daily_bar(
    prev_rows: pd.DataFrame,
    curr_df: pd.DataFrame,
    *,
    date_col: str = "dt",
    strict: bool = True,
) -> pd.DataFrame:
    """
    将实时 curr_df 合并为一根标准日 K 线，拼接到历史日线 prev_rows 后面

    prev_rows:
        index: date
        columns: open, high, low, close, volume, amount, code

    curr_df:
        index: code
        含 open, high, low, close, amount, volume(非真实)

    strict:
        True  -> 关键字段缺失直接抛异常（推荐）
        False -> 尽量容错
    """

    if prev_rows is None or prev_rows.empty:
        raise ValueError("prev_rows is empty")

    if curr_df is None or curr_df.empty:
        return prev_rows

    # ---- 1️⃣ 取第一行（你的 curr_df 本质就是 1 行）----
    row = curr_df.iloc[0]

    # ---- 2️⃣ 必要字段校验 ----
    required = ["open", "high", "low", "close", "amount", "code"]
    missing = [c for c in required if c not in row]

    if missing:
        if strict:
            raise KeyError(f"curr_df missing columns: {missing}")
        else:
            return prev_rows

    # ---- 3️⃣ 构造标准日线 bar ----
    bar = {
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "amount": float(row["amount"]),
        "code": row["code"],
    }

    # ---- 4️⃣ volume 修正（关键）----
    close = bar["close"]
    amount = bar["amount"]

    if close > 0 and amount > 0:
        bar["volume"] = int(amount / close)
    else:
        bar["volume"] = 0

    # ---- 5️⃣ 生成 date index ----
    if date_col in curr_df.columns:
        row[date_col] = pd.to_datetime(str(row[date_col])[:10]).strftime("%Y-%m-%d")
        date = str(row[date_col])
        # fallback：比历史最后一天 +1
        # date = (prev_rows.index.max() + pd.Timedelta(days=1)).normalize()
    else:
        last_date = pd.to_datetime(prev_rows.index.max())
        date = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # bar_df = pd.DataFrame([bar],index=pd.DatetimeIndex([date], name="date"))

    bar_df = pd.DataFrame([bar], index=[date])

    # bar_df = row.to_frame().T

    # ---- 6️⃣ 对齐列顺序 ----
    bar_df = bar_df.reindex(columns=prev_rows.columns)

    # ---- 7️⃣ 防重复（同一天只保留最新）----
    if date in prev_rows.index:
        prev_rows = prev_rows.drop(index=date)

    # ---- 8️⃣ 合并 ----
    full_df = pd.concat([prev_rows, bar_df])

    return full_df


@dataclass
class DailyPatternEvent:
    code: str
    name: str
    pattern: str
    date: str
    price: float
    detail: str
    score: float = 0.0
    signal: Optional[Any] = None # 标准化信号对象 (StandardSignal)

class DailyPatternDetector:
    
    # 形态中文名
    PATTERN_NAMES = {
        'big_bull': '大阳突破',
        'v_shape': 'V型反转',
        'low_open_pinbar': '低开金针',
        'vol_drying': '极度缩量',
        'n_day_rising': '多日连阳',
        'platform_break': '平台突破',
        'rising_structure': '上攻结构',
        'rebound_yang': '底分起跳',
        'stabilization': '缩量企稳',
        'ma60_reversal': 'MA60反转',
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

        # 4. 缩量企稳 (Doji + Support + Low Volume)
        events.extend(self._check_stabilization(code, name, current_row, prev_rows))

        # 4.5. MA60 反转 (Consolidation + Dip + Breakout)
        events.extend(self._check_ma60_reversal(code, name, current_row, prev_rows))

        # 5. V型反转 (Volunteer)
        if self.check_volunteer(code, current_row, prev_rows):
            events.append(DailyPatternEvent(
                code=code, name=name, pattern='v_shape',
                date=str(current_row.get('date', '')), price=float(current_row.get('close', 0)),
                detail="V型反转形态", score=80
            ))

        # 6. 平台突破
        if self.check_platform_break(code, current_row, prev_rows):
            events.append(DailyPatternEvent(
                code=code, name=name, pattern='platform_break',
                date=str(current_row.get('date', '')), price=float(current_row.get('close', 0)),
                detail="五日平台突破", score=75
            ))
            
        # [New] 实时连涨结构 & 反弹阳 (需合并历史与当前行)
        if prev_rows is not None and not prev_rows.empty:
            try:
                # 构造临时 DF (Concat prev + current)
                # current_row 可能是 Series 或 dict

                curr_df = pd.DataFrame([current_row])
                # 确保 columns 一致
                if 'date' not in curr_df.columns and 'date' in prev_rows.columns:
                     # 尝试补全 date
                     pass 

                # full_df = pd.concat([prev_rows, curr_df], ignore_index=True)
                
                full_df = merge_daily_bar(prev_rows, curr_df)

                # Check 连涨
                events.extend(self._check_rising_structure(code, name, full_df))
                
                # Check 反弹阳
                events.extend(self._check_rebound_yang(code, name, full_df))
            except Exception as e:
                # logger.error(f"Realtime structure check error: {e}")
                pass
        
        # 触发回调并发布到信号总线
        for ev in events:
            # 尝试生成标准化信号
            try:
                from signal_bus import SignalBus, publish_standard_signal
                from signal_standard import StandardSignal
                std_signal = StandardSignal(
                    code=ev.code,
                    name=ev.name,
                    type=SignalBus.EVENT_PATTERN,
                    subtype=ev.pattern,
                    price=ev.price,
                    timestamp=ev.date if ev.date else "",
                    score=ev.score,
                    detail=ev.detail,
                    source="DailyPatternDetector"
                )
                ev.signal = std_signal
                publish_standard_signal(std_signal)
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"Failed to publish daily standard signal: {e}")

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

        # 5. V型反转
        if self.check_volunteer(code, last_row, prev_rows):
            events.append(DailyPatternEvent(
                code=code, name=name, pattern='v_shape',
                date=str(last_row.get('date', '')), price=float(last_row.get('close', 0)),
                detail="V型反转形态", score=80
            ))

        # 6. 平台突破
        if self.check_platform_break(code, last_row, prev_rows):
            events.append(DailyPatternEvent(
                code=code, name=name, pattern='platform_break',
                date=str(last_row.get('date', '')), price=float(last_row.get('close', 0)),
                detail="五日平台突破", score=75
            ))

        # 7. 连涨结构
        events.extend(self._check_rising_structure(code, name, df))
        
        # 8. 反弹阳
        events.extend(self._check_rebound_yang(code, name, df))

        # 9. 缩量企稳 (Doji near support)
        # scan 模式通常处理 full history，取最后一行进行判断
        if len(df) >= 2:
            events.extend(self._check_stabilization(code, name, last_row, prev_rows))
            events.extend(self._check_ma60_reversal(code, name, last_row, prev_rows))
            
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
        
        volume = float(row.get('amount', 0))
        pct = float(row.get('percent', 0))
        vol_ma5 = prev_df['amount'].tail(5).mean() if not prev_df.empty else 0
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

    def _check_rising_structure(self, code: str, name: str, df: Any) -> List[DailyPatternEvent]:
        """
        [New] 连涨结构检测: 
        1. 严格要求 High > Prev High 且 Low > Prev Low (或者 Low 不创新低，用户原话: "最近两天的,连续都有新高,中断了已最后两天为主,高点新高低点不新低")
        2. 从最后一天往前数，连续符合条件的有多少天
        3. 至少 2 天 (即今天 > 昨天)
        """
        if df is None or len(df) < 2:
            return []
            
        # 确保按日期升序 (假设传入已排序)
        # 倒序遍历
        count = 0
        idx = len(df) - 1
        
        while idx > 0:
            curr = df.iloc[idx]
            prev = df.iloc[idx-1]
            
            c_high = float(curr['high'])
            c_low = float(curr['low'])
            p_high = float(prev['high'])
            p_low = float(prev['low'])
            
            # 核心条件: 高点新高 (严格 >)，低点不新低 (>=)
            # 用户: "连续阳的,上涨的...5天都达成就是5日...最近两日达成就是2日"
            # 用户: "高点新高低点不新低"
            if c_high > p_high and c_low >= p_low:
                count += 1
                idx -= 1
            else:
                break
                
        if count >= 2:
            last_row = df.iloc[-1]
            return [DailyPatternEvent(
                code=code, name=name, pattern='rising_structure',
                date=str(last_row.get('date', '')), price=float(last_row['close']),
                detail=f"{count}日连涨结构", score=50 + count * 5
            )]
        return []

    def _check_rebound_yang(self, code: str, name: str, df: Any) -> List[DailyPatternEvent]:
        """
        [New] 反弹阳检测:
        1. 当日必须是阳线 (Close > Open)
        2. 涨幅 > 3% (用户要求)
        3. 收盘价 > 过去4天收盘价的最大值 (反弹新高)
        """
        if df is None or len(df) < 5:
            return []
            
        last_row = df.iloc[-1]
        prev_4 = df.iloc[-5:-1] # 倒数第5到倒数第2 (共4天)
        
        close_p = float(last_row['close'])
        open_p = float(last_row['open'])
        pct = float(last_row['percent'])
        
        # 1. 阳线
        if close_p <= open_p:
            return []
            
        # 2. 涨幅 > 3%
        if pct <= 3.0:
            return []
            
        # 3. 反弹新高 (大于过去4日收盘)
        max_prev_close = prev_4['close'].max()
        
        if close_p > max_prev_close:
            return [DailyPatternEvent(
                code=code, name=name, pattern='rebound_yang',
                date=str(last_row.get('date', '')), price=close_p,
                detail=f"反弹阳(>4日) +{pct:.1f}%", score=70
            )]
            
        return []

    def _check_ma60_reversal(self, code: str, name: str, row: Any, prev_df: Any) -> List[DailyPatternEvent]:
        """
        [New] MA60 反转启动检测:
        1. 长期整理: 过去 5-10 日在 MA60 附近振荡 (乖离 < 5%)
        2. 探底动作: 最近 1-2 日有低点 < MA60d
        3. 突破动作: 今日收盘 > MA60d 且收盘 > 前两日最高点 (max_high_2d)
        """
        if prev_df is None or len(prev_df) < 10:
            return []
            
        try:
            ma60 = float(row.get('ma60d', 0))
            if ma60 <= 0: # 尝试从历史计算
                ma60 = prev_df['close'].tail(60).mean()
            
            if ma60 <= 0: return []
            
            close_p = float(row.get('close', 0))
            low_p = float(row.get('low', 0))
            
            # 1. 整理与跳水检查
            recent_10 = prev_df.tail(10)
            avg_bias = (recent_10['close'] - ma60).abs().mean() / ma60
            
            if avg_bias > 0.06: # 偏离太大，不算整理
                return []
                
            # 2. 探底: 最近 2 天 (含今日) 有低于 MA60
            has_dip = low_p < ma60 * 1.002 or (prev_df.iloc[-1]['low'] < ma60 * 1.002)
            if not has_dip:
                return []
                
            # 3. 突破: 穿过 MA60 且 穿过前两日最高
            max_h_2d = prev_df['high'].tail(2).max()
            if close_p > ma60 and close_p > max_h_2d:
                return [DailyPatternEvent(
                    code=code, name=name, pattern='ma60_reversal',
                    date=str(row.get('date', '')), price=close_p,
                    detail=f"MA60反转启动(穿前两日新高{max_h_2d:.2f})",
                    score=85
                )]
        except:
            pass
            
        return []

    def _check_stabilization(self, code: str, name: str, row: Any, prev_df: Any) -> List[DailyPatternEvent]:
        """
        [New] 检测缩量企稳(十字星/支撑点): 
        1. 价格贴近 MA5 或 SWS (支撑线)
        2. 成交量萎缩 (小于5日均量)
        3. 形态为小实体或十字星 (Open/Close 差距小)
        """
        if prev_df is None or (hasattr(prev_df, 'empty') and prev_df.empty):
            return []
            
        price = float(row.get('close', 0))
        open_p = float(row.get('open', 0))
        
        # 1. 支撑线获取
        ma5 = float(row.get('ma5', 0)) or float(row.get('ma5d', 0))
        sws = float(row.get('SWS', 0))
        
        supports = [s for s in [ma5, sws] if s > 0]
        if not supports:
            return []
            
        # 2. 距离检测 (任一支撑 1% 以内)
        is_near = any(abs(price - s) / s < 0.012 for s in supports)
        
        # 3. 实体检测 (Doji-like)
        body_ratio = abs(price - open_p) / open_p if open_p > 0 else 1.0
        is_doji = body_ratio < 0.015
        
        # 4. 量能检测 (缩量)
        volume = float(row.get('amount', 0))
        # prev_df might be a list of dicts in some contexts, or a DataFrame
        if isinstance(prev_df, pd.DataFrame):
            vol_ma5 = prev_df['amount'].tail(5).mean()
        else:
            vol_ma5 = sum(float(r.get('amount', 0)) for r in prev_df[-5:]) / 5 if len(prev_df) >= 5 else 0
            
        is_shrunk = volume < vol_ma5 * 1.1 if vol_ma5 > 0 else True
        
        if is_near and is_doji and is_shrunk:
            detail = "支撑位企稳: "
            if ma5 > 0 and abs(price - ma5) / ma5 < 0.012: detail += "MA5 "
            if sws > 0 and abs(price - sws) / sws < 0.012: detail += "SWS "
            
            return [DailyPatternEvent(
                code=code, name=name, pattern='stabilization',
                date=str(row.get('date', '')), price=price,
                detail=detail + f"缩量十字星",
                score=60
            )]
            
        return []

if __name__ == "__main__":
    # 模拟测试
    detector = DailyPatternDetector()
    test_df = pd.DataFrame([
        {'date': '2026-01-19', 'close': 10.0, 'open': 10.0, 'high': 10.1, 'low': 9.9, 'volume': 100, 'amount': 1000, 'percent': 0},
        {'date': '2026-01-20', 'close': 10.1, 'open': 10.0, 'high': 10.2, 'low': 9.9, 'volume': 110, 'amount': 1100, 'percent': 1},
        {'date': '2026-01-21', 'close': 10.2, 'open': 10.1, 'high': 10.3, 'low': 10.1, 'volume': 120, 'amount': 1200, 'percent': 1},
        {'date': '2026-01-22', 'close': 11.0, 'open': 10.3, 'high': 11.0, 'low': 10.3, 'volume': 300, 'amount': 3000, 'percent': 7.8},
    ])
    events = detector.scan("000001", "平安银行", test_df)
    for ev in events:
        print(f"[{ev.date}] {ev.name} ({ev.code}): {ev.pattern} - {ev.detail} Score={ev.score}")
