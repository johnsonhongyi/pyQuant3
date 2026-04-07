import sqlite3
import pandas as pd
import json

db_path = r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\dist\trading_signals.db'
try:
    conn = sqlite3.connect(db_path)
    
    print("--- recent trades ---")
    # Fetch recent trades, particularly those with profit
    trades_df = pd.read_sql("SELECT * FROM trade_records ORDER BY buy_date DESC LIMIT 50", conn)
    for index, row in trades_df.iterrows():
        print(f"Trade: {row.get('code')} {row.get('name')} | Buy: {row.get('buy_date')} @ {row.get('buy_price')} | Sell: {row.get('sell_date')} @ {row.get('sell_price')} | Profit: {row.get('profit')} | Reason: {row.get('buy_reason')}")
        
    print("\n--- today signals ---")
    import datetime
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    # Check if signal_messages exist
    
except Exception as e:
    print(f"Error: {e}")

