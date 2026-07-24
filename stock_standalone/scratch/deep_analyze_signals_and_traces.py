import json
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(r"D:\JohnsonProgram\instockMonitorTK")
TRACE_FILE = BASE_DIR / "logs" / "trading_kernel_trace.jsonl"
TRADING_SIGNALS_DB = BASE_DIR / "trading_signals.db"

print("=================== 1. TRACE JSONL DETAILED ANALYZER ===================")
if TRACE_FILE.exists():
    traces = []
    with open(TRACE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    traces.append(json.loads(line))
                except Exception as e:
                    pass
    
    df_t = pd.DataFrame(traces)
    print(f"Total traces: {len(df_t)}")
    if 'kernel_action' in df_t.columns:
        print("\nKernel Actions:")
        print(df_t['kernel_action'].value_counts())
    
    if 'intent' in df_t.columns:
        actions = []
        codes = []
        reasons = []
        confidences = []
        for i, row in df_t.iterrows():
            intent = row.get('intent', {})
            if isinstance(intent, dict):
                actions.append(intent.get('action'))
                codes.append(intent.get('code'))
                reasons.append(intent.get('reason'))
                confidences.append(intent.get('confidence'))
            else:
                actions.append(None)
                codes.append(None)
                reasons.append(None)
                confidences.append(None)
        
        df_t['action_type'] = actions
        df_t['stock_code'] = codes
        df_t['signal_reason'] = reasons
        df_t['confidence'] = confidences
        
        print("\nSignal Intent Actions:")
        print(df_t['action_type'].value_counts())
        
        print("\nTop 15 Signal Reasons in Trace:")
        print(df_t['signal_reason'].value_counts().head(15))
        
        print("\nSample intents (BUY actions):")
        buys = df_t[df_t['action_type'] == 'BUY']
        print(f"Total BUY intents: {len(buys)}")
        for idx, row in buys.head(10).iterrows():
            print(f"[{row.get('timestamp')}] Code: {row.get('stock_code')} | Reason: {row.get('signal_reason')} | Conf: {row.get('confidence')} | Kernel Action: {row.get('kernel_action')}")

print("\n=================== 2. TRADING SIGNALS DB ANALYZER ===================")
if TRADING_SIGNALS_DB.exists():
    conn = sqlite3.connect(TRADING_SIGNALS_DB)
    df_sig = pd.read_sql_query("SELECT * FROM signal_history ORDER BY rowid DESC LIMIT 2000", conn)
    print(f"Signal History sample size: {len(df_sig)}")
    print("Columns:", df_sig.columns.tolist())
    if 'signal_type' in df_sig.columns:
        print("\nSignal History Signal Types:")
        print(df_sig['signal_type'].value_counts().head(20))
    if 'reason' in df_sig.columns:
        print("\nSignal History Top Reasons:")
        print(df_sig['reason'].value_counts().head(20))
        
    df_live = pd.read_sql_query("SELECT * FROM live_signal_history ORDER BY id DESC LIMIT 2000", conn)
    print(f"\nLive Signal History size: {len(df_live)}")
    print("Columns:", df_live.columns.tolist())
    if 'signal_type' in df_live.columns:
        print("\nLive Signal Types:")
        print(df_live['signal_type'].value_counts().head(20))
    if 'reason' in df_live.columns:
        print("\nLive Signal Reasons:")
        print(df_live['reason'].value_counts().head(20))

    conn.close()
