import json
import sqlite3
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"D:\JohnsonProgram\instockMonitorTK")
TRACE_FILE = BASE_DIR / "logs" / "trading_kernel_trace.jsonl"
TRADING_SIGNALS_DB = BASE_DIR / "trading_signals.db"
SIGNAL_STRATEGY_DB = BASE_DIR / "signal_strategy.db"

print("=================== 1. TRACE JSONL ANALYZER ===================")
if TRACE_FILE.exists():
    traces = []
    with open(TRACE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    traces.append(json.loads(line))
                except Exception:
                    pass
    
    df_t = pd.DataFrame(traces)
    print(f"Total traces: {len(df_t)}")
    
    buys = []
    for i, row in df_t.iterrows():
        intent = row.get('intent', {})
        if isinstance(intent, dict) and intent.get('action') == 'BUY':
            reason = intent.get('reason', {})
            buys.append({
                'timestamp': row.get('timestamp'),
                'code': intent.get('code'),
                'confidence': intent.get('confidence'),
                'setup': reason.get('setup') if isinstance(reason, dict) else None,
                'pct_diff': reason.get('pct_diff') if isinstance(reason, dict) else None,
                'volume_ratio': reason.get('volume_ratio') if isinstance(reason, dict) else None,
                'regime': reason.get('regime') if isinstance(reason, dict) else None,
                'is_leader': reason.get('is_leader') if isinstance(reason, dict) else None,
                'sector_heat': reason.get('sector_heat') if isinstance(reason, dict) else None,
            })
    
    df_buys = pd.DataFrame(buys)
    print(f"\nBUY Intents count: {len(df_buys)}")
    if not df_buys.empty:
        print("\nBUY Setups Distribution:")
        print(df_buys['setup'].value_counts())
        
        print("\nPct_diff stats for BUY signals:")
        print(df_buys['pct_diff'].describe())
        
        negative_pct = (df_buys['pct_diff'] < 0).sum()
        print(f"Signals triggered when pct_diff < 0 (Oversold/Pullback in down day): {negative_pct} / {len(df_buys)} ({negative_pct/len(df_buys)*100:.1f}%)")

print("\n=================== 2. TRADING SIGNALS DB & TRADE RECORDS ===================")
if TRADING_SIGNALS_DB.exists():
    conn = sqlite3.connect(TRADING_SIGNALS_DB)
    df_trade = pd.read_sql_query("SELECT * FROM trade_records ORDER BY id DESC LIMIT 500", conn)
    print(f"Trade records count: {len(df_trade)}")
    if not df_trade.empty:
        print("Trade records sample columns:", df_trade.columns.tolist())
        print("\nActions in trade_records:")
        if 'action' in df_trade.columns:
            print(df_trade['action'].value_counts())
        if 'buy_reason' in df_trade.columns:
            print("\nBuy reasons in trade_records:")
            print(df_trade['buy_reason'].value_counts().head(10))
            
    df_sig = pd.read_sql_query("SELECT * FROM signal_history ORDER BY rowid DESC LIMIT 500", conn)
    print(f"\nSignal History count in DB: {len(df_sig)}")
    if not df_sig.empty:
        print("Signal History Top Reasons:")
        print(df_sig['reason'].value_counts().head(10))

    conn.close()

print("\n=================== 3. SIGNAL STRATEGY DB ===================")
if SIGNAL_STRATEGY_DB.exists():
    conn = sqlite3.connect(SIGNAL_STRATEGY_DB)
    df_msg = pd.read_sql_query("SELECT * FROM signal_message ORDER BY id DESC LIMIT 1000", conn)
    print(f"Signal messages count: {len(df_msg)}")
    if not df_msg.empty and 'pattern' in df_msg.columns:
        print("\nSignal message patterns:")
        print(df_msg['pattern'].value_counts().head(15))
    conn.close()
