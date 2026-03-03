import sqlite3
import os
import sys
from datetime import datetime

# Import custom time filter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from JohnsonUtil import commonTips as cct

# Mapping of databases to tables and their respective time/date columns
DB_CONFIGS = {
    "trading_signals.db": {
        "trade_records": "buy_date",         
        "signal_history": "date",
        "live_signal_history": "timestamp",
        "selection_history": "date",
        "voice_alerts": "created_time"
    },
    "signal_strategy.db": {
        "follow_queue": "detected_date", 
        "positions": "entry_date",
        "hot_stock_watchlist": "discover_date",
        "signal_message": "timestamp",
        "strategy_stats": "date",
        "daily_pnl": "date",
        "signal_counts": "date"
    }
}

def clean_non_trading_days():
    print("Starting DB cleanup for non-trading days...")
    
    total_deleted = 0
    for db_name, tables in DB_CONFIGS.items():
        db_path = os.path.join(cct.get_base_path(), db_name)
        if not os.path.exists(db_path):
            print(f"Database {db_path} not found, skipping.")
            continue
            
        print(f"\n[{db_name}] at {db_path}")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        for table, date_col in tables.items():
            try:
                # Check if table exists
                c.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table}'")
                if c.fetchone()[0] == 0:
                    continue
                    
                # Fetch all rows with their rowids and dates
                c.execute(f"SELECT rowid, {date_col} FROM {table}")
                rows = c.fetchall()
                
                deleted_in_table = 0
                for row_id, date_val in rows:
                    if not date_val:
                        continue
                        
                    # Extract YYYY-MM-DD
                    date_val_str = str(date_val)
                    date_str = date_val_str[:10] 
                    
                    # Verify if it's a valid trading date
                    if len(date_str) == 10 and '-' in date_str:
                        is_trading = cct.get_day_istrade_date(date_str)
                        
                        is_trading_time = True
                        # e.g., '2026-03-01 14:30:00'
                        if len(date_val_str) >= 16 and ':' in date_val_str[11:16]:
                            try:
                                time_str = date_val_str[11:16].replace(':', '')
                                if time_str.isdigit():
                                    now_t = int(time_str)
                                    if (now_t > 1130 and now_t < 1300) or now_t < 915 or now_t > 1501:
                                        is_trading_time = False
                            except ValueError:
                                pass
                                
                        if not is_trading or not is_trading_time:
                            c.execute(f"DELETE FROM {table} WHERE rowid=?", (row_id,))
                            deleted_in_table += 1
                
                if deleted_in_table > 0:
                    print(f"  - Cleaned {deleted_in_table} non-trading records from '{table}'")
                total_deleted += deleted_in_table
                
            except Exception as e:
                print(f"  - Error processing {table}: {e}")
                
        conn.commit()
        
        # Optimize DB after massive deletes
        if total_deleted > 0:
            c.execute("VACUUM")
            
        conn.close()
        
    print(f"\nCleanup complete! Total deleted rows across all databases: {total_deleted}")

if __name__ == "__main__":
    clean_non_trading_days()
