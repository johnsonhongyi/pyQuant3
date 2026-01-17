
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sqlite3
import os

# 确保在正确目录
import sys
sys.path.append(os.getcwd())

from strong_consolidation_strategy import StrongConsolidationStrategy
from signal_message_queue import SignalMessageQueue

def mock_data():
    # 模拟60天数据 (确保由足够的历史计算MA20)
    now = datetime.now()
    dates = [now - timedelta(days=i) for i in range(60)][::-1]
    
    data = {
        'open': [], 'high': [], 'low': [], 'close': [], 'volume': []
    }
    
    # i=0..59 (60 days)
    # 0-40: 震荡/基准期 (计算MA用)
    # 41: Breakout (Day 41) -> 类似于之前的 Day 11. 此时已有41天数据 > 20.
    # 42-57: Consolidation
    # 58-59: Attack
    
    for i in range(60):
        c, o, h, l, v = 0.0, 0.0, 0.0, 0.0, 0
        
        if i <= 40:
            base = 10.0
            price = base + np.random.random()*0.3
            o = price * 0.99
            c = price
            h = price * 1.01
            l = price * 0.98
            v = 1000
        elif i == 41: # Breakout day
            c = 11.5
            o = 10.5 
            h = 11.6
            l = 10.4
            v = 5000 
        elif i < 58: # Consolidation
            base = 11.6
            price = base + (np.random.random() - 0.5)*0.2
            c = price
            o = price * 0.99
            h = price * 1.01
            l = price * 0.98
            v = 2000
        else: # Attack (Last 2 days: 58, 59)
            if i == 58: 
                c = 12.0
                o = 11.8
                h = 12.1
                l = 11.7
                v = 3000
            else: 
                c = 12.2
                o = 12.0
                h = 12.3
                l = 11.9
                v = 3500
        
        data['open'].append(o)
        data['high'].append(h)
        data['low'].append(l)
        data['close'].append(c)
        data['volume'].append(v)
            
    df = pd.DataFrame(data, index=dates)
    # df['open'] = df['close'] * 0.99 # REMOVED global override
    
    # Calc MA20 for strategy check
    df['ma20'] = df['close'].rolling(20).mean()
    df['percent'] = df['close'].pct_change() * 100
    df['percent'] = df['percent'].fillna(0.0) # Fill NaN for first row
    
    return df

def verify():
    print(">>> Starting Verification for StrongConsolidationStrategy...")
    
    # 1. Prepare Mock Data
    df = mock_data()
    print(f"Mock Data Created: {len(df)} rows. Last Close: {df.iloc[-1]['close']}")
    
    # 2. Init Strategy
    try:
        strat = StrongConsolidationStrategy()
        print("Strategy Initialized.")
    except Exception as e:
        print(f"❌ Init failed: {e}")
        return

    # 3. Test Pattern Detection
    print("\n--- Testing Pattern Detection ---")
    sig = strat._detect_pattern('TEST_301348', df)
    if sig:
        print(f"✅ Pattern Detected! Reason: {sig.reason}")
    else:
        print("❌ Pattern NOT Detected (Check logic or mock data)")
        # Debug info
        # 计算一下 upper
        ma20 = df['close'].rolling(20).mean()
        std20 = df['close'].rolling(20).std()
        upper = ma20 + 2 * std20
        print("\nDebug Info:")
        print(f"Last Close: {df.iloc[-1]['close']}")
        print(f"Last Upper: {upper.iloc[-1]}")
        
    # 4. Test Queue Push
    print("\n--- Testing Queue Push ---")
    pushed = strat.detect_and_push('TEST_301348', df)
    if pushed:
        print("✅ Signal Pushed to Queue")
    else:
        print("❌ Signal Push Failed")
        
    # 5. Verify Database
    print("\n--- Verifying Database (signal_strategy.db) ---")
    if os.path.exists("signal_strategy.db"):
        try:
            conn = sqlite3.connect("signal_strategy.db")
            c = conn.cursor()
            c.execute("SELECT id, code, signal_type, reason FROM signal_message WHERE code='TEST_301348' ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            if row:
                print(f"✅ DB Record Found: {row}")
            else:
                print("❌ No DB Record Found for TEST_301348")
            conn.close()
        except Exception as e:
            print(f"❌ DB Error: {e}")
    else:
        print("❌ DB File Not Found")

if __name__ == "__main__":
    verify()
