# -*- coding: utf-8 -*-
import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\trading_signals.db"
strategy_db_path = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\signal_strategy.db"

def query_db(path, name):
    print(f"\n===== Checking DB: {name} ({path}) =====")
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"Tables in {name}: {tables}")
    
    for table in tables:
        # 查下表结构
        cursor.execute(f"PRAGMA table_info({table});")
        info = cursor.fetchall()
        cols = [col[1] for col in info]
        print(f"  Table: {table}, Columns: {cols}")
        
        # 查找000779和301528
        code_col = None
        for col in cols:
            if 'code' in col.lower() or 'symbol' in col.lower() or 'stock' in col.lower():
                code_col = col
                break
        
        if code_col:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {code_col} LIKE '%688766%'")
            cnt = cursor.fetchone()[0]
            print(f"  --> Found {cnt} records in {table} matching 688766")
            if cnt > 0:
                cursor.execute(f"SELECT * FROM {table} WHERE {code_col} LIKE '%688766%' LIMIT 20")
                rows = cursor.fetchall()
                for r in rows:
                    print(f"    {r}")
    conn.close()

query_db(db_path, "trading_signals.db")
query_db(strategy_db_path, "signal_strategy.db")
