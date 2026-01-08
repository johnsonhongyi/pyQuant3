import sqlite3
import json
import pandas as pd

# Load open trades from DB
conn = sqlite3.connect("trading_signals.db")
open_trades = pd.read_sql_query("SELECT code, name, buy_date FROM trade_records WHERE status='OPEN'", conn)
conn.close()

# Load monitored stocks from config
with open("voice_alert_config.json", "r", encoding="utf-8") as f:
    monitored_stocks = json.load(f)

monitored_codes = set(monitored_stocks.keys())
open_codes = set(open_trades['code'].apply(lambda x: str(x).zfill(6)).tolist())

missing_from_monitor = open_codes - monitored_codes
extra_in_monitor = monitored_codes - open_codes

print(f"Total Open Trades in DB: {len(open_codes)}")
print(f"Total Monitored Stocks: {len(monitored_codes)}")
print(f"Open Trades NOT monitored: {len(missing_from_monitor)}")
print(f"Monitored Stocks NOT in open trades: {len(extra_in_monitor)}")

if missing_from_monitor:
    print("\nFirst 10 missing codes from monitor:")
    print(list(missing_from_monitor)[:10])

# Check for duplicate open trades for same code
duplicate_open = open_trades[open_trades.duplicated('code', keep=False)]
if not duplicate_open.empty:
    print(f"\nCodes with multiple OPEN records: {duplicate_open['code'].nunique()}")
    print(duplicate_open.sort_values('code').head(10).to_string())
