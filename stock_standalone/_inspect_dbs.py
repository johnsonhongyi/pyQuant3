# -*- coding: utf-8 -*-
"""临时脚本：查看三个数据库的表结构"""
import sqlite3

def inspect_db(db_path, db_name):
    print(f"\n{'='*60}")
    print(f"=== {db_name} ===")
    print(f"{'='*60}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"\n表列表: {[t[0] for t in tables]}")
        
        for table in tables:
            table_name = table[0]
            print(f"\n--- {table_name} ---")
            
            # 获取表结构
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print(f"列: {[(c[1], c[2]) for c in columns]}")
            
            # 获取记录数
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"记录数: {count}")
            
            # 获取最近几条记录
            if count > 0:
                cursor.execute(f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT 3")
                rows = cursor.fetchall()
                print(f"最近记录:")
                for row in rows:
                    print(f"  {row}")
                    
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_db("./trading_signals.db", "trading_signals.db")
    inspect_db("./signal_strategy.db", "signal_strategy.db")
    inspect_db("./concept_pg_data.db", "concept_pg_data.db")
