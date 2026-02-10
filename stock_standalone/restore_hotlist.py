import sqlite3
import os

db_path = 'signal_strategy.db'
print(f"Connecting to {db_path}...")
try:
    conn = sqlite3.connect(db_path, timeout=10)
    c = conn.cursor()
    print("Executing UPDATE...")
    c.execute("""
        UPDATE follow_record 
        SET status='ACTIVE', 
            feedback = REPLACE(REPLACE(feedback, ' | 自动清理:时间超7d', ' [RESTORED]'), ' | 自动清理:时间超2d', ' [RESTORED]') 
        WHERE status='CANCELLED' AND feedback LIKE '%自动清理%'
    """)
    changes = conn.total_changes
    conn.commit()
    print(f"SUCCESS: Restored {changes} rows.")
    
    c.execute("SELECT status, COUNT(*) FROM follow_record GROUP BY status")
    stats = c.fetchall()
    print(f"Current stats: {dict(stats)}")
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
