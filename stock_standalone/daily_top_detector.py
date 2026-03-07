# -*- coding: utf-8 -*-
"""
Daily Top Detector for identifying distribution phases and trend exhaustion.
"""
import pandas as pd
import numpy as np

def detect_top_signals(day_df: pd.DataFrame, current_tick: dict = None) -> dict:
    """
    Analyze daily K-line history to detect top signals.
    :param day_df: DataFrame with daily OHLCV data.
    :param current_tick: Real-time tick data for today (optional).
    :return: dict with score (0.0-1.0) and signals list.
    """
    if day_df.empty or len(day_df) < 10:
        return {'score': 0.0, 'signals': []}

    signals = []
    score = 0.0
    
    # Latest confirmed day
    last_row = day_df.iloc[-1]
    
    # Use real-time data if provided, else use last_row
    price = current_tick.get('trade', last_row['close']) if current_tick is not None else last_row['close']
    high = current_tick.get('high', last_row['high']) if current_tick is not None else last_row['high']
    volume = current_tick.get('volume', last_row.get('volume', last_row.get('vol', 0))) if current_tick is not None else last_row.get('volume', last_row.get('vol', 0))
    
    # 1. TD Sequence Check (Setup count)
    td_setup = last_row.get('td_setup', 0)
    if td_setup >= 6:
        s_score = 0.15 + (td_setup - 6) * 0.05
        score += min(s_score, 0.35)
        signals.append(f"TD卖向提示({td_setup})")

    # 2. Volume-Price Divergence at Highs (滞涨)
    # Price is near 10-day high but today's volume is > 1.8x of 5-day avg, while price change is small (< 1.5%)
    avg_vol_5 = day_df['volume'].tail(5).mean() if 'volume' in day_df.columns else day_df['vol'].tail(5).mean()
    high_10 = last_row.get('max10', day_df['high'].tail(10).max())
    high_60 = last_row.get('hmax60', day_df['high'].tail(60).max())
    
    # 滞涨判定：在高位 (10日高点附近) 爆出巨量 (1.8倍) 但不涨
    if price > high_10 * 0.97 and volume > avg_vol_5 * 1.8:
        pct_change = (price - last_row['close']) / last_row['close'] if current_tick is not None else (last_row['close'] - day_df['close'].iloc[-2]) / day_df['close'].iloc[-2]
        if abs(pct_change) < 0.015:
            score += 0.35
            signals.append("高位放量滞涨")
        elif pct_change < -0.01:
            score += 0.4
            signals.append("高位放量阴跌/分歧")

    # 3. Shadow Signal (长上影/避雷针)
    # Shadow length > Real body * 2 AND high is near 60-day high
    body = abs(last_row['close'] - last_row['open'])
    upper_shadow = last_row['high'] - max(last_row['close'], last_row['open'])
    if body > 0 and upper_shadow > body * 1.5 and last_row['high'] > high_60 * 0.98:
        score += 0.25
        signals.append("高位避雷针/见顶影线")

    # 4. Over-extension (偏离度/乖离)
    # Price > MA5 * 1.08 OR Price > MA20 * 1.15
    ma5 = last_row.get('ma5d', day_df['close'].tail(5).mean())
    ma20 = last_row.get('ma20d', day_df['close'].tail(20).mean())
    if ma5 > 0 and price > ma5 * 1.08:
        score += 0.2
        signals.append("短线过热(偏离MA5)")
    if ma20 > 0 and price > ma20 * 1.20:
        score += 0.25
        signals.append("趋势严重乖离(偏离MA20)")
        
    # 5. Continuous Winning (连阳疲劳)
    win = last_row.get('win', 0)
    if win >= 6:
        s_score = 0.1 + (win - 6) * 0.05
        score += min(s_score, 0.3)
        signals.append(f"连阳疲劳({win}d)")
    
    # 6. 新增：高位巨量（即使不是滞涨也该防守）
    if price > high_60 * 0.95 and volume > avg_vol_5 * 2.5:
         score += 0.3
         signals.append("高位历史天量")

    return {
        'score': round(min(score, 1.0), 2),
        'signals': signals,
        'action': 'reduce' if score > 0.6 else ('hold' if score < 0.3 else 'watch')
    }
