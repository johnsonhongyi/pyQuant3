import requests
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox
import os
import platform
import time

def get_stock_changes(selected_type=None, stock_code=None):
    """获取股票异动数据"""
    url = "https://push2ex.eastmoney.com/getAllStockChanges?"
    symbol_map = {
        "火箭发射": "8201",
        "快速反弹": "8202",
        "大笔买入": "8193",
        "封涨停板": "4",
        "打开跌停板": "32",
        "有大买盘": "64",
        "竞价上涨": "8207",
        "高开5日线": "8209",
        "向上缺口": "8211",
        "60日新高": "8213",
        "60日大幅上涨": "8215",
        "加速下跌": "8204",
        "高台跳水": "8203",
        "大笔卖出": "8194",
        "封跌停板": "8",
        "打开涨停板": "16",
        "有大卖盘": "128",
        "竞价下跌": "8208",
        "低开5日线": "8210",
        "向下缺口": "8212",
        "60日新低": "8214",
        "60日大幅下跌": "8216",
    }
    reversed_symbol_map = {v: k for k, v in symbol_map.items()}

    if selected_type:
        if selected_type not in symbol_map:
            messagebox.showerror("错误", f"输入的异动类型 {selected_type} 不存在，请检查。")
            return None
        symbol = symbol_map[selected_type]
    else:
        symbol_list = list(symbol_map.keys())
        symbol = ','.join([symbol_map[i] for i in symbol_list])

    params = {
        'type': symbol,
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'pageindex': '0',
        'pagesize': '50000',
        'dpt': 'wzchanges',
        '_': '1710746553094'
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data_json = r.json()
        temp_df = pd.DataFrame(data_json["data"]["allstock"])
        temp_df["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S").dt.time
        temp_df.columns = [
            "时间",
            "代码",
            "_",
            "名称",
            "板块",
            "相关信息",
        ]
        temp_df = temp_df[
            [
                "时间",
                "代码",
                "名称",
                "板块",
                "相关信息",
            ]
        ]
        temp_df["板块"] = temp_df["板块"].astype(str)
        temp_df["板块"] = temp_df["板块"].map(reversed_symbol_map)
        temp_df = temp_df.sort_values(by="时间")

        if stock_code:
            temp_df = temp_df[temp_df["代码"] == stock_code]
            if temp_df.empty:
                messagebox.showinfo("提示", f"未找到代码为 {stock_code} 的股票数据。")

        return temp_df
    except requests.exceptions.Timeout:
        messagebox.showerror("错误", "请求超时，请检查网络连接")
        return None
    except requests.exceptions.RequestException as e:
        messagebox.showerror("错误", f"网络请求错误: {e}")
        return None
    except Exception as e:
        messagebox.showerror("错误", f"获取数据时出现错误: {e}")
        return None

def populate_treeview(data=None):
    """填充表格数据"""
    if data is None:
        data = get_stock_changes()
    if data is not None:
        for item in tree.get_children():
            tree.delete(item)
        for index, row in data.iterrows():
            tree.insert("", "end", values=list(row))

def search_by_code():
    """按代码搜索"""
    code = code_entry.get().strip()
    selected_type = type_var.get() if type_var.get() != "" else None
    if code:
        data = get_stock_changes(selected_type=selected_type, stock_code=code)
        populate_treeview(data)
    else:
        search_by_type()

def search_by_type():
    """按异动类型搜索"""
    selected_type = type_var.get() if type_var.get() != "" else None
    data = get_stock_changes(selected_type=selected_type)
    populate_treeview(data)

def refresh_data():
    """刷新数据"""
    search_by_type()
    tree.focus_set()

def on_tree_select(event):
    """处理表格行选择事件（已移除通达信联动）"""
    pass  # 移除原有的联动逻辑

def on_closing():
    """处理窗口关闭事件"""
    if messagebox.askyesno("确认", "确定要退出程序吗?"):
        root.destroy()

# 创建主窗口
root = tk.Tk()
root.title("股票异动数据监控")
root.geometry("850x500")
root.resizable(True, True)
root.protocol("WM_DELETE_WINDOW", on_closing)

# 配置样式
style = ttk.Style()
style.configure("Treeview", 
    background="white", 
    foreground="black", 
    rowheight=20,
    fieldbackground="white",
    borderwidth=1,
    relief="solid"
)
style.configure("Treeview.Heading", 
    font=('SimHei', 9, 'bold'),
    background="#f0f0f0",
    relief="solid",
    borderwidth=1
)
style.map("Treeview", background=[('selected', '#a6c9e2')])

# 创建顶部工具栏（已移除通达信设置按钮）
toolbar = tk.Frame(root)
toolbar.pack(fill=tk.X, padx=5, pady=5)
tk.Button(toolbar, text="刷新数据", command=refresh_data, font=('SimHei', 9), padx=5).pack(side=tk.LEFT, padx=2)

# 创建异动类型选择框架
type_frame = tk.LabelFrame(root, text="异动类型选择", padx=3, pady=3)
type_frame.pack(fill=tk.X, padx=5, pady=3)

# 定义异动类型列表
stock_types = [
    "火箭发射", "快速反弹", "大笔买入", "封涨停板", "打开跌停板", "有大买盘", 
    "竞价上涨", "高开5日线", "向上缺口", "60日新高", "60日大幅上涨", "加速下跌", 
    "高台跳水", "大笔卖出", "封跌停板", "打开涨停板", "有大卖盘", "竞价下跌", 
    "低开5日线", "向下缺口", "60日新低", "60日大幅下跌"
]

# 创建单选按钮变量
type_var = tk.StringVar(value="")

# 每行显示9个异动类型按钮
buttons_per_row = 9
for i, stock_type in enumerate(stock_types):
    row = i // buttons_per_row
    col = i % buttons_per_row
    tk.Radiobutton(
        type_frame, 
        text=stock_type, 
        variable=type_var, 
        value=stock_type,
        command=search_by_type,
        font=('SimHei', 8),
        padx=1, pady=1
    ).grid(row=row, column=col, sticky=tk.W, padx=2, pady=1)

# 创建代码搜索框和标签
code_frame = tk.Frame(root)
code_frame.pack(fill=tk.X, padx=5, pady=3)
tk.Label(code_frame, text="代码搜索:", font=('SimHei', 9)).pack(side=tk.LEFT, padx=3)
code_entry = tk.Entry(code_frame, width=8, font=('SimHei', 9))
code_entry.pack(side=tk.LEFT, padx=3)
tk.Button(code_frame, text="搜索代码", command=search_by_code, font=('SimHei', 9), padx=5).pack(side=tk.LEFT, padx=3)
tk.Button(code_frame, text="清除选择", command=lambda: [type_var.set(""), search_by_type()], font=('SimHei', 9), padx=5).pack(side=tk.LEFT, padx=3)

# 创建Treeview组件和滚动条
columns = ("时间", "代码", "名称", "异动类型", "相关信息")
tree = ttk.Treeview(root, columns=columns, show="headings")
for col in columns:
    tree.heading(col, text=col)
    width = 60 if col in ["时间", "代码", "名称"] else 90
    tree.column(col, width=width, anchor=tk.CENTER)

# 绑定选择事件（已移除联动逻辑）
tree.bind("<<TreeviewSelect>>", on_tree_select)

# 垂直滚动条
v_scrollbar = ttk.Scrollbar(root, orient="vertical", command=tree.yview)
v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
tree.configure(yscrollcommand=v_scrollbar.set)

# 水平滚动条
h_scrollbar = ttk.Scrollbar(root, orient="horizontal", command=tree.xview)
h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
tree.configure(xscrollcommand=h_scrollbar.set)

tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)

# 状态栏
status_var = tk.StringVar(value="就绪")
status_bar = ttk.Label(root, textvariable=status_var, relief=tk.SUNKEN, anchor=tk.W)
status_bar.pack(side=tk.BOTTOM, fill=tk.X)

# 初始加载数据
populate_treeview()

# 运行主循环
root.mainloop()
