# import tkinter as tk
# from tkinter import ttk
# import random
# def on_table_select(event):
#     """Handles table selection and prints the selected item values."""
#     item = stock_tree.selection()[0]
#     values = stock_tree.item(item, "values")
#     print("Selected Item Values:", values)

# def sort_column(col):
#     """Sorts the table by the specified column."""
#     items = [(stock_tree.set(item, col), item) for item in stock_tree.get_children("")]
#     # Convert numerical columns to float for proper sorting
#     if col in ('现价', '竞价金额', '竞价净额', '竞价涨幅', '实时涨幅', '流通市值'):
#         try:
#             items = [(float(val), item) for val, item in items]
#         except ValueError:
#             # Handle cases where value cannot be converted to float (e.g. empty)
#             pass
#     items.sort()
#     for index, (val, item) in enumerate(items):
#         stock_tree.move(item, "", index)

# def add_stock_data():
#     """Adds sample stock data to the table."""
#     stocks = [
#         ("600000", "浦发银行", random.uniform(10, 20), random.uniform(10000, 20000), random.uniform(5000, 10000),
#          random.uniform(0, 10), random.uniform(0, 10), random.uniform(500000, 1000000), "银行"),
#         ("600001", "邯郸钢铁", random.uniform(5, 15), random.uniform(5000, 15000), random.uniform(2000, 7000),
#          random.uniform(0, 8), random.uniform(0, 8), random.uniform(300000, 800000), "钢铁"),
#         ("000001", "平安银行", random.uniform(12, 22), random.uniform(12000, 22000), random.uniform(6000, 12000),
#          random.uniform(0, 9), random.uniform(0, 9), random.uniform(600000, 1200000), "银行"),
#         ("000002", "万科A", random.uniform(15, 25), random.uniform(15000, 25000), random.uniform(8000, 15000),
#          random.uniform(0, 7), random.uniform(0, 7), random.uniform(800000, 1500000), "地产"),
#         ("600002", "齐鲁高速", random.uniform(8, 18), random.uniform(8000, 18000), random.uniform(4000, 9000),
#          random.uniform(0, 6), random.uniform(0, 6), random.uniform(400000, 900000), "交通运输"),
#         ("600003", "东北高速", random.uniform(7, 17), random.uniform(7000, 17000), random.uniform(3000, 8000),
#          random.uniform(0, 5), random.uniform(0, 5), random.uniform(350000, 850000), "交通运输"),
#         ("600004", "白云机场", random.uniform(11, 21), random.uniform(11000, 21000), random.uniform(5500, 11000),
#          random.uniform(0, 4), random.uniform(0, 4), random.uniform(550000, 1100000), "机场"),
#     ]
#     for stock in stocks:
#         stock_tree.insert("", "end", values=stock)

# root = tk.Tk()
# root.title("Stock Data Viewer")
# columns = ('代码', '简称', '现价', '竞价金额', '竞价净额', '竞价涨幅', '实时涨幅', '流通市值', '板块')

# stock_tree = ttk.Treeview(root, columns=columns, show='headings')

# for col in columns:
#     stock_tree.heading(col, text=col, command=lambda c=col: sort_column(c)) #Bind to the column
#     stock_tree.column(col, width=88, anchor=tk.CENTER)

# stock_tree.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
# stock_tree.bind("<<TreeviewSelect>>", on_table_select)

# add_stock_data() #Add some sample data

# root.mainloop()








# import tkinter as tk
# from tkinter import ttk, messagebox
# from tkcalendar import DateEntry
# import pandas as pd
# import os
# import datetime

# # --- 假設的函數 ---
# def refresh_data():
#     """刷新數據的函數"""
#     print("刷新数据...")

# def delete_selected_records():
#     """刪除選中記錄的函數"""
#     print("删除选中记录...")

# def handle_date_selection(event):
#     """處理日期選擇事件的函數"""
#     selected_date = date_entry.get_date()
#     print(f"选择了日期: {selected_date}")
#     # 在這裡觸發數據載入或篩選
#     # ...

# def update_linkage_status():
#     """處理tdx和ths選中狀態變化的函數"""
#     tdx_state = tdx_var.get()
#     ths_state = ths_var.get()
    
#     print(f"tdx 联动: {tdx_state}")
#     print(f"ths 联动: {ths_state}")
    
#     # 在這裡根據 tdx_state 和 ths_state 執行相應的聯動邏輯
#     # 例如：如果 tdx 被選中，就發送命令給通達信
#     # if tdx_state:
#     #     send_to_tdx()
#     # if ths_state:
#     #     send_to_ths()


# # --- 創建主窗口 ---
# root = tk.Tk()
# root.title("工具列範例")

# # --- 創建工具列 Frame ---
# toolbar = tk.Frame(root)
# toolbar.pack(side=tk.TOP, fill=tk.X, pady=5, padx=5)

# # --- 刷新按鈕 ---
# refresh_btn = tk.Button(toolbar, text="↻ 刷新数据", command=refresh_data, 
#                        font=('Microsoft YaHei', 10), bg="#5b9bd5", fg="white",
#                        padx=10, pady=3, relief="flat")
# refresh_btn.pack(side=tk.LEFT, padx=5)

# # --- 刪除按鈕 ---
# delete_btn = tk.Button(toolbar, text="删除选中记录", command=delete_selected_records,
#                        font=('Microsoft YaHei', 10), bg="#d9534f", fg="white",
#                        padx=10, pady=3, relief="flat")
# delete_btn.pack(side=tk.LEFT, padx=5)

# # --- 日期選擇器和選項框的 Frame ---
# date_options_frame = tk.Frame(toolbar)
# date_options_frame.pack(side=tk.LEFT, padx=10)

# # 添加一个Label作为日期选择器的说明
# date_label = tk.Label(date_options_frame, text="日期:", font=('Microsoft YaHei', 10))
# date_label.pack(side=tk.LEFT, padx=(0, 5))

# # 创建 DateEntry
# date_entry = DateEntry(date_options_frame, width=12, background='darkblue', foreground='white', borderwidth=2,
#                        font=('Microsoft YaHei', 10))
# date_entry.pack(side=tk.LEFT)
# date_entry.bind("<<DateEntrySelected>>", handle_date_selection)

# # --- tdx 和 ths 聯動屬性框 ---
# tdx_var = tk.BooleanVar()
# ths_var = tk.BooleanVar()

# tdx_checkbutton = tk.Checkbutton(date_options_frame, text="联动tdx", variable=tdx_var, 
#                                  command=update_linkage_status)
# tdx_checkbutton.pack(side=tk.LEFT, padx=5)

# ths_checkbutton = tk.Checkbutton(date_options_frame, text="联动ths", variable=ths_var, 
#                                  command=update_linkage_status)
# ths_checkbutton.pack(side=tk.LEFT, padx=5)


# # --- 運行主循環 ---
# root.mainloop()












import tkinter as tk
from tkinter import ttk

def add_refresh_button(root, refresh_command):
    """
    添加一個刷新按鈕到主窗口頂部，並將其與 refresh_command 綁定。
    """
    # 創建一個新的 Frame 來容納按鈕
    button_frame = tk.Frame(root)
    button_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
    
    refresh_btn = tk.Button(button_frame, text="刷新数据", command=refresh_command,
                            font=('Microsoft YaHei', 9), padx=10, pady=2)
    refresh_btn.pack(side=tk.LEFT, padx=5)


# ------------------- 示例數據和函數 -------------------
# 假設這是你的數據源
def fetch_block_data():
    return ["板块A", "板块B", "板块C"]

def fetch_stock_data():
    return [
        ('000001', '平安银行', '10.00', '1000', '50', '2.5%', '3.0%', '1000亿', '银行'),
        ('000002', '万科A', '15.00', '2000', '80', '1.5%', '2.0%', '2000亿', '地产'),
        # 更多数据...
    ]

def populate_table(event):
    """根据Listbox选择填充Treeview"""
    selected_item = block_listbox.get(block_listbox.curselection())
    print(f"选择了板块: {selected_item}")
    # 模拟加载数据，实际应用中应根据板块筛选
    load_stock_data()

def on_table_select(event):
    """处理Treeview选中事件"""
    for item in stock_tree.selection():
        item_values = stock_tree.item(item, "values")
        print(f"选中了股票: {item_values[0]}")
        # 在这里可以添加联动通达信的逻辑
        # ...

def load_stock_data():
    """加载数据到Treeview"""
    # 清空现有数据
    for item in stock_tree.get_children():
        stock_tree.delete(item)
    
    # 插入新数据
    for item in fetch_stock_data():
        stock_tree.insert('', tk.END, values=item)

def refresh_all_data():
    """刷新所有数据"""
    print("刷新所有数据...")
    # 刷新 Listbox
    block_listbox.delete(0, tk.END)
    for block in fetch_block_data():
        block_listbox.insert(tk.END, block)

    # 刷新 Treeview
    load_stock_data()
    print("数据刷新完毕。")


def sort_treeview(tree, col, reverse):
    """排序Treeview的函数"""
    l = [(tree.set(k, col), k) for k in tree.get_children('')]
    l.sort(key=lambda t: t[0], reverse=reverse)
    for index, (_, k) in enumerate(l):
        tree.move(k, '', index)
    tree.heading(col, command=lambda c=col: sort_treeview(tree, c, not reverse))


# ------------------- 创建主窗口和控件 -------------------
# 创建主窗口
root = tk.Tk()
root.title("开盘啦竞价板块观察1.0 + 通达信联动")

# 添加刷新按钮
add_refresh_button(root, refresh_all_data)

# 创建列表框
block_listbox = tk.Listbox(root, width=12)
block_listbox.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0), pady=(0, 10))
block_listbox.bind("<<ListboxSelect>>", populate_table)

# 创建表格
columns = ('代码', '简称', '现价', '竞价金额', '竞价净额', '竞价涨幅', '实时涨幅', '流通市值', '板块')
stock_tree = ttk.Treeview(root, columns=columns, show='headings')
for col in columns:
    stock_tree.heading(col, text=col, command=lambda c=col: sort_treeview(stock_tree, c, False))
    stock_tree.column(col, width=88, anchor=tk.CENTER)
stock_tree.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0, 10), pady=(0, 10))
stock_tree.bind("<<TreeviewSelect>>", on_table_select)

# 初始加载数据
refresh_all_data()

root.mainloop()
