import tkinter as tk
from tkinter import ttk
from datetime import datetime
import threading
import random
import json
import os

# -----------------------------
# 全局数据
# -----------------------------
monitor_windows = {}   # 存储各监控窗口信息
WINDOW_GEOMETRIES = {} # 窗口位置存储
alert_rules = {}       # {stock_code: [{field, op, value}, ...]}
alert_history = []     # [{time, stock_code, field, value, rule}]
CONFIG_FILE = "window_positions.json"

# -----------------------------
# 工具函数
# -----------------------------
def load_window_positions():
    global WINDOW_GEOMETRIES
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                WINDOW_GEOMETRIES = json.load(f)
                print("窗口配置已加载")
        except Exception:
            print("配置文件损坏，使用默认位置")
    else:
        print("未找到配置文件，使用默认位置")

def save_window_positions():
    global WINDOW_GEOMETRIES
    with open(CONFIG_FILE, "w") as f:
        json.dump(WINDOW_GEOMETRIES, f)

def clamp_window_to_screens(x, y, w, h, screen_width=1920, screen_height=1080):
    x = max(0, min(x, screen_width - w))
    y = max(0, min(y, screen_height - h))
    return x, y

# -----------------------------
# 放置窗口
# -----------------------------
def place_new_window(window, window_id, win_width=300, win_height=160, margin=10):
    monitor_windows[window_id] = {'toplevel': window, 'stock_info': [window_id]}
    if window_id in WINDOW_GEOMETRIES:
        geom = WINDOW_GEOMETRIES[window_id]
        try:
            _, x_part, y_part = geom.split('+')
            x, y = int(x_part), int(y_part)
        except:
            x, y = 100, 100
        x, y = clamp_window_to_screens(x, y, win_width, win_height)
        window.geometry(f"{win_width}x{win_height}+{x}+{y}")
    else:
        # 自动竖排平铺
        existing_positions = [(w['toplevel'].winfo_x(), w['toplevel'].winfo_y())
                              for w in monitor_windows.values() if w['toplevel'].winfo_exists()]
        x, y = margin, margin
        step_y = win_height + margin
        while (x, y) in existing_positions:
            y += step_y
        window.geometry(f"{win_width}x{win_height}+{x}+{y}")
    window.bind("<Configure>", lambda e: update_window_position(window_id))

def update_window_position(window_id):
    win = monitor_windows[window_id]['toplevel']
    if win.winfo_exists():
        geom = win.geometry() # WxH+X+Y
        WINDOW_GEOMETRIES[window_id] = geom
        save_window_positions()

# -----------------------------
# 监控窗口
# -----------------------------
def create_monitor_window(stock_info):
    stock_code, stock_name = stock_info[:2]
    monitor_win = tk.Toplevel(root)
    monitor_win.title(f"监控: {stock_name} ({stock_code})")
    monitor_win.resizable(True, True)

    # Treeview
    tree_frame = ttk.Frame(monitor_win)
    tree_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
    columns = ('时间', '异动类型', '涨幅', '价格', '量')
    monitor_tree = ttk.Treeview(monitor_win, columns=columns, show="headings")
    for col in columns:
        monitor_tree.heading(col, text=col)
        if col in ['涨幅', '量']:
            monitor_tree.column(col, width=30, anchor=tk.CENTER)
        elif col == '异动类型':
            monitor_tree.column(col, width=60, anchor=tk.CENTER)
        else:
            monitor_tree.column(col, width=40, anchor=tk.CENTER)
    monitor_tree.pack(expand=True, fill=tk.BOTH)
    item_id = monitor_tree.insert("", "end", values=("加载中...", "", "", "", ""))

    # 右键菜单添加报警设置
    def open_alert_menu(event):
        menu = tk.Menu(monitor_win, tearoff=0)
        menu.add_command(label="设置报警规则", command=lambda: open_alert_config(stock_code))
        menu.post(event.x_root, event.y_root)
    monitor_tree.bind("<Button-3>", open_alert_menu)

    # 放置窗口
    place_new_window(monitor_win, stock_code)
    monitor_windows[stock_code] = {'toplevel': monitor_win, 'stock_info': stock_info, 'tree': monitor_tree}

    # 模拟刷新
    refresh_stock_data(stock_code, monitor_tree)
    return monitor_win

# -----------------------------
# 刷新监控数据
# -----------------------------
def refresh_stock_data(stock_code, tree):
    # 这里用随机数据模拟
    tree.delete(*tree.get_children())
    now = datetime.now().strftime('%H:%M:%S')
    price = round(random.uniform(10, 100), 2)
    change = round(random.uniform(-5, 5), 2)
    volume = random.randint(1000, 20000)
    tree.insert("", "end", values=(now, "异动", change, price, volume))
    # 检查报警
    check_alert(stock_code, price, change, volume)
    tree.after(5000, lambda: refresh_stock_data(stock_code, tree))

# -----------------------------
# 报警设置窗口
# -----------------------------
def open_alert_config(stock_code):
    win = tk.Toplevel(root)
    win.title(f"{stock_code} 报警设置")
    win.geometry("350x180")
    fields = ['价格', '涨幅', '量']
    default_vals = [0,0,0]
    entries = []

    for i, field in enumerate(fields):
        frame = tk.Frame(win)
        frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(frame, text=field).pack(side="left")
        var = tk.DoubleVar(value=default_vals[i])
        entry = tk.Spinbox(frame, from_=0, to=100000, increment=1, textvariable=var, width=10)
        entry.pack(side="left")
        entries.append((field, var))

        # +/- 按钮
        def make_adjust_fn(v=var):
            return lambda delta: v.set(round(v.get() + delta,2))
        tk.Button(frame, text="▲", command=make_adjust_fn(1)).pack(side="left")
        tk.Button(frame, text="▼", command=make_adjust_fn(-1)).pack(side="left")

    def save_rules():
        rules = []
        for field, var in entries:
            rules.append({'field': field, 'op': '>=', 'value': var.get()})
        alert_rules[stock_code] = rules
        win.destroy()
    tk.Button(win, text="保存", command=save_rules).pack(pady=5)

# -----------------------------
# 检查报警
# -----------------------------
def check_alert(stock_code, price, change, volume):
    if stock_code not in alert_rules:
        return
    for rule in alert_rules[stock_code]:
        val = {'价格': price, '涨幅': change, '量': volume}[rule['field']]
        if rule['op'] == '>=' and val >= rule['value']:
            alert_history.append({'time': datetime.now().strftime('%H:%M:%S'),
                                  'stock_code': stock_code,
                                  'field': rule['field'],
                                  'value': val,
                                  'rule': rule})
            refresh_alert_tree()

# -----------------------------
# 报警中心窗口
# -----------------------------
alert_center_win = None
def open_alert_center():
    global alert_center_win
    if alert_center_win and alert_center_win.winfo_exists():
        alert_center_win.lift()
        return
    alert_center_win = tk.Toplevel(root)
    alert_center_win.title("报警中心")
    alert_center_win.geometry("400x300")
    frame = tk.Frame(alert_center_win)
    frame.pack(expand=True, fill=tk.BOTH)
    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    tree = ttk.Treeview(frame, columns=('时间','代码','字段','值','规则'), show="headings", yscrollcommand=scrollbar.set)
    for col in ('时间','代码','字段','值','规则'):
        tree.heading(col, text=col)
        tree.column(col, width=60)
    tree.pack(expand=True, fill=tk.BOTH)
    scrollbar.config(command=tree.yview)
    alert_center_win.tree = tree
    refresh_alert_tree()

def refresh_alert_tree():
    if not alert_center_win or not alert_center_win.winfo_exists():
        return
    tree = alert_center_win.tree
    tree.delete(*tree.get_children())
    for a in alert_history[-50:]:
        tree.insert("", "end", values=(a['time'], a['stock_code'], a['field'], a['value'], a['rule']['op'] + str(a['rule']['value'])))

# -----------------------------
# 测试主程序
# -----------------------------
root = tk.Tk()
root.title("异动联动监控")
root.geometry("200x100")
tk.Button(root, text="打开报警中心", command=open_alert_center).pack(pady=10)

# 模拟创建监控窗口
sample_stocks = [['600925','股票A'], ['002547','股票B']]
for s in sample_stocks:
    create_monitor_window(s)

root.mainloop()
