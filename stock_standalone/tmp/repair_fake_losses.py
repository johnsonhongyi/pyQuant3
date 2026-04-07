import sqlite3
import os

db_path = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\dist\trading_signals.db"

def fix_fake_losses():
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Select how many affected
        cursor.execute("SELECT id, code, name, profit, sell_reason FROM trade_records WHERE sell_price = 0.0 AND status = 'CLOSED' AND profit < 0")
        rows = cursor.fetchall()
        
        print(f"Found {len(rows)} records with massive false tracking losses due to sell_price=0.0")
        
        # Fix them
        cursor.execute("""
            UPDATE trade_records 
            SET profit = 0.0, pnl_pct = 0.0, sell_reason = '[系统修复] ' || sell_reason
            WHERE sell_price = 0.0 AND status = 'CLOSED' AND profit < 0
        """)
        
        conn.commit()
        print(f"Successfully repaired {cursor.rowcount} records in trade_records.")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error repairing DB: {e}")

if __name__ == '__main__':
    fix_fake_losses()
