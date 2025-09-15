import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import json, random, time
from datetime import datetime

ALERT_RULES = {}
CONFIG_FILE = "alert_rules.json"
FIRED_ALERTS = {}
ALERT_COOLDOWN = 30
monitor_windows = {}

# -----------------------------
# 警报规则加载/保存
# -----------------------------
def load_alert_rules():
    global ALERT_RULES
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            ALERT_RULES = json.load(f)
    except:
        ALERT_RULES = {"default": {}}
    print("Alert rules loaded:", ALERT_RULES)

def save_alert_rules():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(ALERT_RULES, f, ensure_ascii=False, indent=4)
    print("Alert rules saved.")

# -----------------------------
# 报警检测
# -----------------------------
def trigger_alert(stock_code, row_data, col, expr):
    print(f"[ALERT] {stock_code} {col}={row_data[col]} 触发 {expr}")
    win = monitor_windows[stock_code]['toplevel']
    win.bell()
    messagebox.showinfo("报警", f"{stock_code} 触发规则: {col} {expr}, 当前值={row_data[col]}")

def check_alert(stock_code, row_data):
    rules = ALERT_RULES.get(stock_code, ALERT_RULES.get("default", {}))
    for col, expr in rules.items():
        if col in row_data:
            value = row_data[col]
            try:
                if eval(expr, {"value": float(value)}):
                    key = (stock_code, col, expr)
                    now = time.time()
                    if now - FIRED_ALERTS.get(key, 0) >= ALERT_COOLDOWN:
                        FIRED_ALERTS[key] = now
                        trigger_alert(stock_code, row_data, col, expr)
            except Exception as e:
                print(f"规则错误: {col} {expr} - {e}")

# -----------------------------
# 模拟数据
# -----------------------------
def fetch_stock_data(code):
    return {
        "时间": datetime.now().strftime("%H:%M:%S"),
        "异动类型": random.choice(["涨停", "跌停", "放量"]),
        "涨幅": round(random.uniform(-3, 8), 2),
        "价格": round(random.uniform(5, 50), 2),
        "量": random.randint(1000, 20000)
    }

def refresh_data(win_info, tree):
    code = win_info['stock_info'][0]
    row_data = fetch_stock_data(code)

    tree.delete(*tree.get_children())
    tree.insert("", "end", values=[row_data[c] for c in tree['columns']])

    check_alert(code, row_data)

    win_info['toplevel'].after(3000, lambda: refresh_data(win_info, tree))


# 全局
alerts_buffer = []
alert_window = None
alert_tree = None

def add_alert(code, name, field, value, rule):
    """添加一条报警到缓冲区"""
    ts = time.strftime("%H:%M:%S")
    alerts_buffer.append((ts, code, name, field, value, rule))

def flush_alerts():
    """每10秒刷新报警中心"""
    global alerts_buffer
    if not alerts_buffer:
        root.after(10000, flush_alerts)
        return

    open_alert_center()
    for ts, code, name, field, value, rule in alerts_buffer:
        alert_tree.insert("", "end", values=(ts, code, name, f"{field}={value}", rule))
    alerts_buffer = []

    root.after(10000, flush_alerts)

def open_alert_center():
    """报警中心窗口（只创建一次）"""
    global alert_window, alert_tree
    if alert_window and alert_window.winfo_exists():
        return

    alert_window = tk.Toplevel(root)
    alert_window.title("报警中心")
    alert_window.geometry("500x300")

    cols = ("时间", "代码", "名称", "触发值", "规则")
    alert_tree = ttk.Treeview(alert_window, columns=cols, show="headings")
    for c in cols:
        alert_tree.heading(c, text=c)
        alert_tree.column(c, width=80 if c != "规则" else 150, anchor="center")
    alert_tree.pack(expand=True, fill="both")

    # 双击跳转监控窗口
    def on_double_click(event):
        sel = alert_tree.selection()
        if not sel: return
        vals = alert_tree.item(sel[0], "values")
        code = vals[1]
        if code in monitor_windows:
            win = monitor_windows[code]['toplevel']
            if win and win.winfo_exists():
                win.lift()
                win.attributes("-topmost", 1)
                win.attributes("-topmost", 0)

    alert_tree.bind("<Double-1>", on_double_click)




# -----------------------------
# 报警配置对话框
# -----------------------------
def open_alert_config(stock_code):
    # 获取最新数据作为默认值
    row_data = fetch_stock_data(stock_code)

    dialog = tk.Toplevel(root)
    dialog.title(f"设置报警规则 - {stock_code}")
    dialog.geometry("360x220")

    fields = [
        ("价格", row_data["价格"], "price"),
        ("涨幅", row_data["涨幅"], "percent"),
        ("量", row_data["量"], "volume"),
    ]
    entries = {}

    for i, (label, default, key) in enumerate(fields):
        frame = tk.Frame(dialog)
        frame.pack(fill="x", pady=5)

        enabled = tk.BooleanVar(value=True)   # 默认启用
        chk = tk.Checkbutton(frame, variable=enabled)
        chk.pack(side="left")

        tk.Label(frame, text=label, width=8).pack(side="left")
        tk.Label(frame, text=">=").pack(side="left")

        var = tk.DoubleVar(value=default)
        spin = tk.Spinbox(
            frame, textvariable=var, width=10,
            from_=-999999, to=999999, increment=0.01
        )
        spin.pack(side="left")

        # 自定义微调逻辑：按百分比调节
        def make_adjust_fn(v=var, base=default, delta=0.01):
            def adjust():
                try:
                    cur = float(v.get())
                except Exception:
                    cur = base
                # 百分比变化
                new_val = cur * (1 + delta)
                v.set(round(new_val, 2))
            return adjust

        # 添加按钮来调整
        tk.Button(frame, text="▲", width=2,
                  command=make_adjust_fn(var, default, delta=0.01)).pack(side="left")
        tk.Button(frame, text="▼", width=2,
                  command=make_adjust_fn(var, default, delta=-0.01)).pack(side="left")

        entries[key] = (enabled, var)

    def save_rule():
        if stock_code not in ALERT_RULES:
            ALERT_RULES[stock_code] = {}
        for key, (enabled, var) in entries.items():
            if enabled.get():
                ALERT_RULES[stock_code][key] = f"value >= {var.get()}"
            elif key in ALERT_RULES[stock_code]:
                del ALERT_RULES[stock_code][key]  # 删除禁用规则
        save_alert_rules()
        messagebox.showinfo("成功", f"{stock_code} 报警规则已更新")
        dialog.destroy()

    tk.Button(dialog, text="保存", command=save_rule).pack(pady=10)


# -----------------------------
# 创建窗口
# -----------------------------
def create_monitor_window(stock_info):
    code, name = stock_info
    win = tk.Toplevel(root)
    win.title(f"监控: {name} ({code})")
    win.geometry("320x180+100+100")

    columns = ("时间", "异动类型", "涨幅", "价格", "量")
    tree = ttk.Treeview(win, columns=columns, show="headings")
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=50, anchor=tk.CENTER)
    tree.pack(expand=True, fill=tk.BOTH)

    win_info = {"stock_info": stock_info, "toplevel": win}
    monitor_windows[code] = win_info

    # 右键菜单
    menu = tk.Menu(win, tearoff=0)
    menu.add_command(label="设置报警规则", command=lambda: open_alert_config(code))
    win.bind("<Button-3>", lambda e: menu.post(e.x_root, e.y_root))

    refresh_data(win_info, tree)

# -----------------------------
# 主程序
# -----------------------------
root = tk.Tk()
root.title("异动联动 Monitor")
root.geometry("400x300")

load_alert_rules()

stocks = [("600925", "工商银行"), ("002547", "新光药业")]
for stock in stocks:
    create_monitor_window(stock)
# 程序启动时，开启循环
root.after(10000, flush_alerts)
root.mainloop()

