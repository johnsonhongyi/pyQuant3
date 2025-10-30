import sqlite3
import tkinter as tk
from tkinter import ttk

DB_PATH = "./concept_pg_data.db"


import sqlite3
import json

DB_PATH = "./concept_pg_data.db"

def round_floats(obj):
    """递归将所有浮点数保留两位小数"""
    if isinstance(obj, dict):
        return {k: round_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [round_floats(v) for v in obj]
    elif isinstance(obj, float):
        return round(obj, 2)
    else:
        return obj

def reformat_concept_data():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT date, concept_name, init_data, prev_data FROM concept_data")
    rows = cur.fetchall()

    for date_str, concept_name, init_data_str, prev_data_str in rows:
        init_data = json.loads(init_data_str)
        prev_data = json.loads(prev_data_str) if prev_data_str else {}

        # 重新处理浮点数
        init_data = round_floats(init_data)
        prev_data = round_floats(prev_data)

        # 写回数据库
        cur.execute("""
            UPDATE concept_data
            SET init_data=?, prev_data=?
            WHERE date=? AND concept_name=?
        """, (
            json.dumps(init_data, ensure_ascii=False),
            json.dumps(prev_data, ensure_ascii=False),
            date_str,
            concept_name
        ))
        print(f"[更新成功] {date_str} - {concept_name}")

    conn.commit()
    conn.close()
    print("全部数据处理完成！")

# if __name__ == "__main__":
#     reformat_concept_data()


# import sys
# sys.exit()
def fetch_data(search=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if search:
        cur.execute("SELECT date, concept_name, init_data, prev_data FROM concept_data WHERE concept_name LIKE ? ORDER BY date DESC", (f"%{search}%",))
    else:
        cur.execute("SELECT date, concept_name, init_data, prev_data FROM concept_data ORDER BY date DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

def populate_tree(tree, rows):
    for row in tree.get_children():
        tree.delete(row)
    for r in rows:
        tree.insert("", "end", values=r)

def on_search():
    keyword = search_var.get().strip()
    rows = fetch_data(keyword)
    populate_tree(tree, rows)

root = tk.Tk()
root.title("Concept Data Viewer")
root.geometry("800x400")

# 搜索栏
search_var = tk.StringVar()
tk.Label(root, text="搜索 Concept Name:").pack(side=tk.TOP, anchor="w", padx=5, pady=2)
search_entry = tk.Entry(root, textvariable=search_var)
search_entry.pack(side=tk.TOP, fill=tk.X, padx=5)
tk.Button(root, text="搜索", command=on_search).pack(side=tk.TOP, padx=5, pady=2)

# 表格
columns = ("date", "concept_name", "init_data", "prev_data")
tree = ttk.Treeview(root, columns=columns, show="headings")
for col in columns:
    tree.heading(col, text=col)
    tree.column(col, width=180, anchor="w")
tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# 滚动条
scrollbar = ttk.Scrollbar(root, orient="vertical", command=tree.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
tree.configure(yscrollcommand=scrollbar.set)

# 初始化显示
populate_tree(tree, fetch_data())

root.mainloop()
