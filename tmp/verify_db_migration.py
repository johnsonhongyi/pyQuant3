import sqlite3
import os
import sys

# 添加项目根目录到路径
sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')

from trading_logger import TradingLogger

def verify_migration():
    logger = TradingLogger()
    db_path = logger.db_path
    print(f"Checking database at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("PRAGMA table_info(selection_history)")
    columns = [col[1] for col in cur.fetchall()]
    print(f"Columns in selection_history: {columns}")
    
    required_cols = ['grade', 'tqi']
    for col in required_cols:
        if col in columns:
            print(f"✅ Column '{col}' exists.")
        else:
            print(f"❌ Column '{col}' is MISSING!")
            
    conn.close()

if __name__ == "__main__":
    verify_migration()
