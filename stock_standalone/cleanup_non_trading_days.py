import sqlite3
import os
from JohnsonUtil import commonTips as cct
from datetime import datetime

def cleanup_db(db_path="./trading_signals.db"):
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # --- 1. Cleanup trade_records ---
        cur.execute("SELECT id, buy_date, sell_date, code, name FROM trade_records")
        rows = cur.fetchall()
        to_delete = []
        for row in rows:
            tid, buy_date, sell_date, code, name = row
            # Format: 'YYYY-MM-DD HH:MM:SS'
            is_valid = True
            if buy_date:
                b_date_str = buy_date.split(' ')[0]
                if not cct.get_day_istrade_date(b_date_str):
                    is_valid = False
                    print(f"[trade_records] Invalid Buy Date: {code} ({name}) at {buy_date}")
            
            if is_valid and sell_date:
                s_date_str = sell_date.split(' ')[0]
                if not cct.get_day_istrade_date(s_date_str):
                    is_valid = False
                    print(f"[trade_records] Invalid Sell Date: {code} ({name}) at {sell_date}")
            
            if not is_valid:
                to_delete.append(tid)

        if to_delete:
            print(f"Deleting {len(to_delete)} records from trade_records...")
            cur.executemany("DELETE FROM trade_records WHERE id=?", [(tid,) for tid in to_delete])

        # --- 2. Cleanup signal_history ---
        # PRIMARY KEY (date, code), date might be 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'
        # Let's check format in signal_history
        cur.execute("SELECT DISTINCT date FROM signal_history")
        unique_dates = cur.fetchall()
        for (d_str,) in unique_dates:
            short_date = d_str.split(' ')[0]
            if not cct.get_day_istrade_date(short_date):
                print(f"[signal_history] Deleting non-trading day data: {d_str}")
                cur.execute("DELETE FROM signal_history WHERE date=?", (d_str,))

        # --- 3. Cleanup selection_history ---
        cur.execute("SELECT DISTINCT date FROM selection_history")
        unique_dates = cur.fetchall()
        for (d_str,) in unique_dates:
            short_date = d_str.split(' ')[0]
            if not cct.get_day_istrade_date(short_date):
                print(f"[selection_history] Deleting non-trading day data: {d_str}")
                cur.execute("DELETE FROM selection_history WHERE date=?", (d_str,))

        conn.commit()
        print("✅ Cleanup complete.")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup_db()
