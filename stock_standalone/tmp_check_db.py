import os
import sys
import sqlite3
from JohnsonUtil import commonTips as cct

base_path = cct.get_base_path()
print(f"Base Path: {base_path}")

db_path = os.path.join(base_path, "trading_signals.db")
print(f"DB Path: {db_path}")

if os.path.exists(db_path):
    print(f"DB exists, size: {os.path.getsize(db_path)} bytes")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables in DB: {[t[0] for t in tables]}")
        conn.close()
    except Exception as e:
        print(f"Error inspecting DB: {e}")
else:
    print("DB does not exist at this path!")
