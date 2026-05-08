import sqlite3
import pandas as pd
import os

db_path = "trading_signals.db"
if not os.path.exists(db_path):
    print(f"Error: {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. 检查 selection_history 字段信息
print("=== 1. selection_history 表当前列结构 ===")
cur.execute("PRAGMA table_info(selection_history)")
cols = cur.fetchall()
for col in cols:
    print(f"列ID: {col[0]}, 列名: {col[1]}, 类型: {col[2]}, 默认值: {col[4]}")

# 2. 查询最近几天的选股记录以及新字段的数据情况
print("\n=== 2. selection_history 表中的所有唯一日期与记录数 ===")
try:
    df_dates = pd.read_sql_query("""
        SELECT date, COUNT(*) as count 
        FROM selection_history 
        GROUP BY date 
        ORDER BY date DESC
    """, conn)
    print(df_dates.to_string(index=False))
except Exception as e:
    print(f"查询唯一日期失败: {e}")

# 3. 查询最新的具体记录
print("\n=== 3. 最新的选股日志记录及新持久化字段数据 ===")
try:
    df = pd.read_sql_query("""
        SELECT date, code, name, rank, zhuli_rank, yesterday_pct, sum_perc, win, user_status
        FROM selection_history 
        ORDER BY date DESC, rank ASC 
        LIMIT 10
    """, conn)
    if df.empty:
        print("暂无选股持久化数据。")
    else:
        print(df.to_string(index=False))
except Exception as e:
    print(f"查询失败: {e}")

conn.close()
