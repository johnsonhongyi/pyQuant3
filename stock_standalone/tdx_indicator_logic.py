# -*- coding: utf-8 -*-
"""
High-performance Tdx Indicator logical implementation.
Functions are designed to be standalone for easy auditing and benchmarking.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any

def barslastcount(cond: np.ndarray) -> np.ndarray:
    """Cumulative count of consecutive True values, resets on False."""
    count = np.zeros(len(cond), dtype=int)
    curr = 0
    for i in range(len(cond)):
        if cond[i]:
            curr += 1
        else:
            curr = 0
        count[i] = curr
    return count

def backset(cond: np.ndarray, n: int) -> np.ndarray:
    """If cond[i] is True, set [i-n+1 : i+1] to True."""
    out = np.zeros(len(cond), dtype=bool)
    for i in np.where(cond)[0]:
        start = max(0, i - n + 1)
        out[start : i + 1] = True
    return out

def calc_tdx_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate upgraded Tdx-style indicators.
    """
    if df.empty or 'close' not in df.columns:
        return df

    res = df.copy()
    c = res['close'].values
    h = res['high'].values
    l = res['low'].values
    o = res['open'].values
    n = len(c)
    
    # --- 1. Complex Nine Turns (九转) ---
    m = 9
    nn = m - 1
    
    # AB1:=C>REF(C,4);
    c4 = np.zeros(n)
    c4[4:] = c[:-4]
    c4[:4] = c[:4]
    ab1 = c > c4
    
    # AB2:=BARSLASTCOUNT(AB1);
    ab2 = barslastcount(ab1)
    
    # AB3:=REF(AB2,1)=NN AND AB2>REF(AB2,1); (Reaches 9)
    ab2_ref1 = np.zeros(n)
    ab2_ref1[1:] = ab2[:-1]
    ab3 = (ab2_ref1 == nn) & (ab2 > ab2_ref1)
    
    # AB4:=REF(BETWEEN(AB2,5,NN),1) AND AB2<REF(AB2,1); (Broken sequence)
    between_5_nn = (ab2 >= 5) & (ab2 <= nn)
    between_ref1 = np.zeros(n, dtype=bool)
    between_ref1[1:] = between_5_nn[:-1]
    ab4 = between_ref1 & (ab2 < ab2_ref1)
    
    # AB5:=ISLASTBAR AND BETWEEN(AB2,6,NN);
    ab5 = np.zeros(n, dtype=bool)
    if n > 0:
        ab5[-1] = (ab2[-1] >= 6) & (ab2[-1] <= nn)
        
    # AB6:=(BACKSET(AB3>0,NN+1) OR BACKSET(AB4>0,AB2+1)*0 OR BACKSET(AB5>0,AB2))*AB2;
    # Note: BACKSET(AB4>0,AB2+1)*0 effectively ignores AB4's contribution to the index display
    # but the formula structure suggests it might be for internal logic. We'll follow the display requirement.
    ab6_mask = backset(ab3, nn + 1) | backset(ab5, ab2[-1] if n > 0 and ab5[-1] else 0)
    res['td_up_label'] = np.where(ab6_mask, ab2, 0)
    res['td_up_9'] = (ab2 == nn + 1)
    
    # Symmetrical logic for Down Sequence (BA1...)
    ba1 = c < c4
    b2 = barslastcount(ba1)
    b2_ref1 = np.zeros(n)
    b2_ref1[1:] = b2[:-1]
    b3 = (b2_ref1 == nn) & (b2 > b2_ref1)
    
    between_b2_5_nn = (b2 >= 5) & (b2 <= nn)
    between_b2_ref1 = np.zeros(n, dtype=bool)
    between_b2_ref1[1:] = between_b2_5_nn[:-1]
    b4 = between_b2_ref1 & (b2 < b2_ref1)
    
    b5 = np.zeros(n, dtype=bool)
    if n > 0:
        b5[-1] = (b2[-1] >= 6) & (b2[-1] <= nn)
        
    b6_mask = backset(b3, nn + 1) | backset(b5, b2[-1] if n > 0 and b5[-1] else 0)
    res['td_dn_label'] = np.where(b6_mask, b2, 0)
    res['td_dn_9'] = (b2 == nn + 1)

    # --- 2. Buy/Sell & K-line Color Logic ---
    # VAR1:=(C>REF(C,1) AND C>REF(C,2));
    c1 = np.zeros(n); c1[1:] = c[:-1]; c1[0] = c[0]
    c2 = np.zeros(n); c2[2:] = c[:-2]; c2[:2] = c[:2]
    var1 = (c > c1) & (c > c2)
    
    # VARD:=(C<REF(C,1) AND C<REF(C,2));
    vard = (c < c1) & (c < c2)
    
    res['is_red_hold'] = var1
    res['is_cyan_watch'] = vard
    
    # Main Force Buy/Sell
    # VAR19:=REF(VARD,1) AND VAR1;
    vard_ref1 = np.zeros(n, dtype=bool); vard_ref1[1:] = vard[:-1]
    res['main_buy'] = vard_ref1 & var1
    
    # VAR1A:=REF(VAR1,1) AND VARD;
    var1_ref1 = np.zeros(n, dtype=bool); var1_ref1[1:] = var1[:-1]
    res['main_sell'] = var1_ref1 & vard

    # --- 3. Reversal Line (翻转线) ---
    # 趋势线:=(EMA(C,5)+EMA(C,13)+EMA(C,21))/3;
    # 翻转:IF(MA(C,3)>趋势线,趋势线,MA(C,3));
    ema5 = res['close'].ewm(span=5, adjust=False).mean()
    ema13 = res['close'].ewm(span=13, adjust=False).mean()
    ema21 = res['close'].ewm(span=21, adjust=False).mean()
    trend_line = (ema5 + ema13 + ema21) / 3
    ma3 = res['close'].rolling(3).mean()
    res['reversal_line'] = np.where(ma3 > trend_line, trend_line, ma3)

    return res

if __name__ == "__main__":
    import time
    # Performance benchmark
    print("Benchmarking tdx_indicator_logic performance...")
    size = 2000
    data = {
        'open': np.random.rand(size) * 100,
        'high': np.random.rand(size) * 100 + 5,
        'low': np.random.rand(size) * 100 - 5,
        'close': np.random.rand(size) * 100,
    }
    test_df = pd.DataFrame(data)
    
    start = time.perf_counter()
    for _ in range(100):
        _ = calc_tdx_indicators(test_df)
    end = time.perf_counter()
    
    avg_ms = (end - start) * 1000 / 100
    print(f"Average execution time for {size} bars: {avg_ms:.2f} ms")
    print("Sample output Head:")
    print(calc_tdx_indicators(test_df).tail(5))
