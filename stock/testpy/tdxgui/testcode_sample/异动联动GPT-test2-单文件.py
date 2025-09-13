import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
import random

# ------------------------
# 占位数据接口（可替换为真实接口）
# ------------------------
def fetch_stock_data(linkage_options, date_str):
    stock_types = [
        "火箭发射","快速反弹","大笔买入","封涨停板","打开跌停板","有大买盘",
        "竞价上涨","高开5日线","向上缺口","60日新高","60日大幅上涨","加速下跌",
        "高台跳水","大笔卖出","封跌停板","打开涨停板","有大卖盘","竞价下跌",
        "低开5日线","向下缺口","60日新低","60日大幅下跌"
    ]
    data = []
    for i in range(20):
        row = [
            date_str,
            f"{100000+i}",
            f"股票{i}",
            random.choice(stock_types),
            f"{random.uniform(-5,5):.2f}%",
            f"{random.uniform(10,200):.2f}",
            random.randint(1000,10000)
        ]
        data.append(row)
    return data

# ------------------------
# 主窗口创建
# ------------------------
root = tk.Tk()
root.title("股票异动数据监控")
root.geometry("750x550")
root.minsize(720,500)

# 工具栏
toolbar = tk.Frame(root, bg="#f0f0f0", padx=5,pady=5)
toolbar.pack(fill=tk.X)

# 状态栏
status_var = tk.StringVar(value="就绪 | 等待操作...")
status_bar = ttk.Label(root,textvariable=status_var,relief=tk.SUNKEN,anchor=tk.W)
status_bar.pack(side=tk.BOTTOM,fill=tk.X)

# 全局监控窗口管理器
monitor_windows = {}

# ------------------------
# 主窗口功能函数
# ------------------------
def populate_treeview():
    tree.delete(*tree.get_children())
    date_str = date_entry.get()
    linkage_options = {'tdx':tdx_var.get(),'ths':ths_var.get(),'dfcf':dfcf_var.get()}
    data = fetch_stock_data(linkage_options,date_str)
    for row in data:
        tree.insert("",tk.END,values=row)

def refresh_data():
    populate_treeview()
    for win in monitor_windows.values():
        win.populate_tree()
    status_var.set("数据已刷新")

def search_by_code():
    code = code_entry.get().strip()
    for iid in tree.get_children():
        vals = tree.item(iid,"values")
        if code in vals[1]:
            tree.selection_add(iid)
        else:
            tree.selection_remove(iid)
    status_var.set(f"按代码筛选: {code}")

def search_by_type():
    selected_type = type_var.get()
    for iid in tree.get_children():
        vals = tree.item(iid,"values")
        if selected_type in vals:
            tree.selection_add(iid)
        else:
            tree.selection_remove(iid)
    status_var.set(f"按类型筛选: {selected_type}")

def update_linkage_status():
    status=[]
    if tdx_var.get(): status.append("TDX")
    if ths_var.get(): status.append("THS")
    if dfcf_var.get(): status.append("DC")
    status_var.set("联动: "+",".join(status) if status else "无联动")

def delete_selected_records():
    for iid in tree.selection():
        tree.delete(iid)
    status_var.set("已删除选中记录")

def on_code_entry_change(event):
    search_by_code()

def show_context_menu(event):
    context_menu.post(event.x_root,event.y_root)

def add_selected_stock():
    selected = tree.selection()
    for iid in selected:
        vals = tree.item(iid,"values")
        stock_code, stock_name = vals[1], vals[2]
        if stock_code not in monitor_windows:
            win_info = create_monitor_window([stock_code, stock_name])
            monitor_windows[stock_code] = win_info

# ------------------------
# 子窗口函数（保持你原来的逻辑）
# ------------------------
def create_monitor_window(stock_info):
    stock_code, stock_name = stock_info[0], stock_info[1]
    monitor_win = tk.Toplevel(root)
    monitor_win.resizable(True, True)
    monitor_win.title(f"监控: {stock_name} ({stock_code})")
    monitor_win.geometry("400x165")
    tree_frame = ttk.Frame(monitor_win)
    tree_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

    columns =  ('时间', '代码', '名称', '异动类型', '涨幅', '价格', '量')
    monitor_tree = ttk.Treeview(monitor_win, columns=columns, show="headings")
    
    for col in columns:
        monitor_tree.heading(col, text=col)
        if col in ['涨幅', '价格', '量']:
            monitor_tree.column(col, width=30, anchor=tk.CENTER, minwidth=20)
        elif col in ['异动类型']:
            monitor_tree.column(col, width=60, anchor=tk.CENTER, minwidth=40)
        else:
            monitor_tree.column(col, width=40, anchor=tk.CENTER, minwidth=30)

    item_id = monitor_tree.insert("", "end", values=("加载中...", "", "", "", "", ""))
    monitor_tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

    def populate_tree():
        monitor_tree.delete(*monitor_tree.get_children())
        date_str = date_entry.get()
        linkage_options = {'tdx':tdx_var.get(),'ths':ths_var.get(),'dfcf':dfcf_var.get()}
        data = fetch_stock_data(linkage_options,date_str)
        for row in data:
            monitor_tree.insert("",tk.END,values=row)

    def on_close_monitor():
        if stock_code in monitor_windows:
            del monitor_windows[stock_code]
        monitor_win.destroy()

    monitor_win.protocol("WM_DELETE_WINDOW", on_close_monitor)
    monitor_win.bind("<FocusIn>", lambda e: code_entry.delete(0,tk.END) or code_entry.insert(0, stock_code) or search_by_code())
    monitor_win.populate_tree = populate_tree
    populate_tree()
    return monitor_win

# ------------------------
# UI 元素创建
# ------------------------
# 工具栏按钮
refresh_btn = tk.Button(toolbar,text="↻ 刷新数据",command=refresh_data,bg="#5b9bd5",fg="white")
refresh_btn.pack(side=tk.LEFT,padx=5)
delete_btn = tk.Button(toolbar,text="删除选中记录",command=delete_selected_records,bg="#d9534f",fg="white")
delete_btn.pack(side=tk.LEFT,padx=5)

tk.Label(toolbar,text="选择日期:").pack(side=tk.LEFT,padx=(10,5))
date_entry = DateEntry(toolbar,width=12)
date_entry.pack(side=tk.LEFT,padx=5)

tdx_var = tk.BooleanVar(value=True)
ths_var = tk.BooleanVar(value=False)
dfcf_var = tk.BooleanVar(value=False)
tk.Checkbutton(toolbar,text="联动TDX",variable=tdx_var,command=update_linkage_status).pack(side=tk.LEFT,padx=5)
tk.Checkbutton(toolbar,text="联动THS",variable=ths_var,command=update_linkage_status).pack(side=tk.LEFT,padx=5)
tk.Checkbutton(toolbar,text="联动DC",variable=dfcf_var,command=update_linkage_status).pack(side=tk.LEFT,padx=5)

# 异动类型选择
type_var = tk.StringVar(value="")
type_frame = tk.LabelFrame(root,text="异动类型选择",padx=10,pady=10)
type_frame.pack(fill=tk.X,padx=10,pady=5)
stock_types = [
    "火箭发射","快速反弹","大笔买入","封涨停板","打开跌停板","有大买盘",
    "竞价上涨","高开5日线","向上缺口","60日新高","60日大幅上涨","加速下跌",
    "高台跳水","大笔卖出","封跌停板","打开涨停板","有大卖盘","竞价下跌",
    "低开5日线","向下缺口","60日新低","60日大幅下跌"
]
radio_container = tk.Frame(type_frame)
radio_container.pack(fill=tk.X)
buttons_per_row = 7
for i, stock_type in enumerate(stock_types):
    row = i // buttons_per_row
    col = i % buttons_per_row
    tk.Radiobutton(radio_container,text=stock_type,variable=type_var,value=stock_type,command=search_by_type).grid(row=row,column=col,sticky=tk.W,padx=5,pady=3)

# 搜索框
search_frame = tk.Frame(root,bg="#f0f0f0",padx=10,pady=5)
search_frame.pack(fill=tk.X,padx=10)
tk.Label(search_frame,text="股票代码搜索:").pack(side=tk.LEFT)
code_entry = tk.Entry(search_frame)
code_entry.pack(side=tk.LEFT,padx=5)
code_entry.bind("<KeyRelease>", on_code_entry_change)
tk.Button(search_frame,text="搜索",command=search_by_code,bg="#5b9bd5",fg="white").pack(side=tk.LEFT,padx=5)

# Treeview
columns = ('时间','代码','名称','异动类型','涨幅','价格','量')
tree_frame = tk.Frame(root)
tree_frame.pack(fill=tk.BOTH,expand=True,padx=10,pady=(0,10))
tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
vsb = ttk.Scrollbar(tree_frame,orient="vertical",command=tree.yview)
hsb = ttk.Scrollbar(tree_frame,orient="horizontal",command=tree.xview)
tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
for col in columns:
    tree.heading(col,text=col)
    tree.column(col,width=80,anchor=tk.CENTER)
tree.grid(row=0,column=0,sticky="nsew")
vsb.grid(row=0,column=1,sticky="ns")
hsb.grid(row=1,column=0,sticky="ew")
tree_frame.grid_rowconfigure(0,weight=1)
tree_frame.grid_columnconfigure(0,weight=1)
tree.bind("<Button-3>", show_context_menu)

# 右键菜单
context_menu = tk.Menu(root,tearoff=0)
context_menu.add_command(label="添加到监控",command=add_selected_stock)

# 初始加载数据
populate_treeview()

# 启动主循环
root.mainloop()
