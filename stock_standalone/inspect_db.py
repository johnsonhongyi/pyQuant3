import sqlite3
import pandas as pd

db_path = 'd:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock_standalone\\concept_pg_data.db'
conn = sqlite3.connect(db_path)

def inspect_db():
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    for table_name in tables:
        table = table_name[0]
        print(f"\n--- Checking Table: {table} ---")
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 1", conn)
            print(df.iloc[0])
            print("init_data sample:", df.iloc[0]['init_data'])
            print("prev_data sample:", df.iloc[0]['prev_data'])
        except Exception as e:
            print(f"Error reading {table}: {e}")

if __name__ == "__main__":
    inspect_db()
    conn.close()
