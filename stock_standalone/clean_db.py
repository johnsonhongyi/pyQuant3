import sqlite3
import os

DB_PATH = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\signal_strategy.db"

def clean_db():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # 1. Count before
        c.execute("SELECT COUNT(*) FROM follow_queue")
        count_before = c.fetchone()[0]
        print(f"Rows before: {count_before}")

        # 2. Keep only the latest record for each code (AGGRESSIVE)
        # Delete ANY record that is not the max ID for its code
        c.execute("""
            DELETE FROM follow_queue 
            WHERE id NOT IN (
                SELECT MAX(id) 
                FROM follow_queue 
                GROUP BY code
            )
        """)
        
        # 3. Count after
        c.execute("SELECT COUNT(*) FROM follow_queue")
        count_after = c.fetchone()[0]
        print(f"Rows after: {count_after}")
        print(f"Removed: {count_before - count_after}")
        
        conn.commit()
        print("✅ Database cleaned.")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clean_db()
