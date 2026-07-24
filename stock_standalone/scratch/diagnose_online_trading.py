import json
import sqlite3
import pandas as pd
import numpy as np
import os
from pathlib import Path

BASE_DIR = Path(r"D:\JohnsonProgram\instockMonitorTK")
TRACE_FILE = BASE_DIR / "logs" / "trading_kernel_trace.jsonl"
TRADING_SIGNALS_DB = BASE_DIR / "trading_signals.db"
SIGNAL_STRATEGY_DB = BASE_DIR / "signal_strategy.db"

print("--- 1. Analyzing trading_kernel_trace.jsonl ---")
if TRACE_FILE.exists():
    records = []
    with open(TRACE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except Exception as e:
                    pass
    print(f"Total trace records: {len(records)}")
    if records:
        df_trace = pd.DataFrame(records)
        print("Columns in trace:", df_trace.columns.tolist())
        print("\nSample trace head:")
        print(df_trace.head(5))
        if 'action' in df_trace.columns:
            print("\nAction value counts:")
            print(df_trace['action'].value_counts())
        if 'signal_type' in df_trace.columns:
            print("\nSignal type counts:")
            print(df_trace['signal_type'].value_counts())
        if 'reason' in df_trace.columns:
            print("\nTop 10 reasons:")
            print(df_trace['reason'].value_counts().head(10))
else:
    print(f"Trace file not found at {TRACE_FILE}")

print("\n--- 2. Analyzing trading_signals.db ---")
if TRADING_SIGNALS_DB.exists():
    try:
        conn = sqlite3.connect(TRADING_SIGNALS_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("Tables in trading_signals.db:", tables)
        for t in tables:
            tname = t[0]
            df_t = pd.read_sql_query(f"SELECT * FROM {tname} LIMIT 10", conn)
            cursor.execute(f"SELECT count(*) FROM {tname}")
            cnt = cursor.fetchone()[0]
            print(f"\nTable '{tname}' (count: {cnt}):")
            print(df_t.head(3))
        conn.close()
    except Exception as e:
        print("Error reading trading_signals.db:", e)

print("\n--- 3. Analyzing signal_strategy.db ---")
if SIGNAL_STRATEGY_DB.exists():
    try:
        conn = sqlite3.connect(SIGNAL_STRATEGY_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("Tables in signal_strategy.db:", tables)
        for t in tables:
            tname = t[0]
            df_t = pd.read_sql_query(f"SELECT * FROM {tname} LIMIT 10", conn)
            cursor.execute(f"SELECT count(*) FROM {tname}")
            cnt = cursor.fetchone()[0]
            print(f"\nTable '{tname}' (count: {cnt}):")
            print(df_t.head(3))
        conn.close()
    except Exception as e:
        print("Error reading signal_strategy.db:", e)
