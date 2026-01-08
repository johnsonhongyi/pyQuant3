import sqlite3
import pandas as pd

db_path = "trading_signals.db"
conn = sqlite3.connect(db_path)

print("--- Recent Signals ---")
signals = pd.read_sql_query("SELECT * FROM signal_history ORDER BY date DESC LIMIT 20", conn)
print(signals.to_string())

print("\n--- Recent Trades ---")
trades = pd.read_sql_query("SELECT * FROM trade_records ORDER BY id DESC LIMIT 10", conn)
print(trades.to_string())

print("\n--- Summary ---")
summary = pd.read_sql_query("SELECT status, COUNT(*), SUM(profit) FROM trade_records GROUP BY status", conn)
print(summary.to_string())

conn.close()
