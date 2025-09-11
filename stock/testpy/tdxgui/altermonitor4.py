import tkinter as tk
from tkinter import ttk, messagebox
import json, time, random

ALERTS_FILE = "alerts.json"
alerts_rules = {}       # {code: [ {field, op, value}, ... ]}
alerts_buffer = []      # 临时报警缓存
alerts_history = []
alert_window = None
alert_tree = None

monitor_windows = {}    # {code: {"toplevel": win, "label": label}}

# ------------------------
# 报警规则加载/保存
# ------------------------
def load_alerts():
    global alerts_rules
    try:
        with open(ALERTS_FILE, "r") as f:
            alerts_rules = json.load(f)
    except:
        alerts_rules = {}

def save_alerts():
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts_rules, f, indent=2, ensure_ascii=False)

# ------------------------
# 报警添加/刷新
# ------------------------
def add_alert(code, name, field, value, rule):
    ts = time.strftime("%H:%M:%S")
    alerts_buffer.append((ts, code, name, field, value, rule))

def flush_alerts():
    global alerts_buffer
    if alerts_buffer:
        open_alert_center()
        for ts, code, name, field, value, rule in alerts_buffer:
            alert_tree.insert("", "end", values=(ts, code, name, f"{field}={value}", rule))
        alerts_buffer = []
    root.after(10000, flush_alerts)

# ------------------------
# 报警中心窗口
# ------------------------
def open_alert_center():
    global alert_window, alert_tree
    if alert_window and alert_window.winfo_exists():
        alert_window.lift()
        return

    alert_window = tk.Toplevel(root)
    alert_window.title("报警中心")
    alert_window.geometry("720x360")

    # 上方快速规则入口
    top_frame = ttk.Frame(alert_window)
    top_frame.pack(fill="x", padx=5, pady=5)

    tk.Label(top_frame, text="股票代码:").pack(side="left")
    stock_var = tk.StringVar()
    stock_entry = ttk.Combobox(top_frame, textvariable=stock_var, values=list(monitor_windows.keys()), width=10)
    stock_entry.pack(side="left", padx=5)

    tk.Button(top_frame, text="添加/编辑规则", command=lambda: open_alert_editor(stock_var.get())).pack(side="left", padx=5)

    # 报警列表
    frame = ttk.Frame(alert_window)
    frame.pack(expand=True, fill="both")

    scrollbar = ttk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")

    cols = ("时间", "代码", "名称", "触发值", "规则")
    alert_tree = ttk.Treeview(frame, columns=cols, show="headings", yscrollcommand=scrollbar.set)
    scrollbar.config(command=alert_tree.yview)

    for c in cols:
        alert_tree.heading(c, text=c)
        alert_tree.column(c, width=120 if c != "规则" else 200, anchor="center")
    alert_tree.pack(expand=True, fill="both")

    refresh_alert_center()



    # 双击报警 → 聚焦监控窗口
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

    # 右键菜单 → 编辑 / 新增 / 删除规则
    def show_menu(event):
        sel = alert_tree.selection()
        if not sel: return
        vals = alert_tree.item(sel[0], "values")
        code = vals[1]

        menu = tk.Menu(alert_window, tearoff=0)
        menu.add_command(label="编辑规则", command=lambda: open_alert_editor(code))
        menu.add_command(label="新增规则", command=lambda: open_alert_editor(code, new=True))
        menu.add_command(label="删除规则", command=lambda: delete_alert_rule(code))
        menu.post(event.x_root, event.y_root)
    alert_tree.bind("<Button-3>", show_menu)

def open_alert_editor(code, new=False):
    editor = tk.Toplevel(root)
    editor.title(f"设置报警规则 - {code}")
    editor.geometry("480x220")

    rules = alerts_rules.get(code, [])
    defaults = [
        {"field": "价格", "op": ">=", "value": random.uniform(8, 15)},
        {"field": "涨幅", "op": ">=", "value": random.uniform(2, 8)},
        {"field": "量", "op": ">=", "value": random.randint(5000, 20000)},
    ]
    if not rules or new:
        rules = defaults

    entries = []

    def make_adjust_fn(val_var, pct):
        return lambda: val_var.set(round(val_var.get() * (1 + pct), 2))

    for i, base in enumerate(rules[:3]):
        tk.Label(editor, text=base["field"], width=8).grid(row=i, column=0, padx=5, pady=5, sticky="w")

        op_var = tk.StringVar(value=base["op"])
        ttk.Combobox(editor, textvariable=op_var, values=[">=", "<="], width=5).grid(row=i, column=1, padx=5)

        val_var = tk.DoubleVar(value=base["value"])
        spin = tk.Spinbox(editor, textvariable=val_var, from_=0, to=100000, increment=0.1, width=12)
        spin.grid(row=i, column=2, padx=5)

        # 百分比增减按钮
        tk.Button(editor, text="-1%", command=make_adjust_fn(val_var, -0.01), width=5).grid(row=i, column=3, padx=2)
        tk.Button(editor, text="+1%", command=make_adjust_fn(val_var, 0.01), width=5).grid(row=i, column=4, padx=2)

        entries.append((base["field"], op_var, val_var))

    def save_rule():
        new_rules = []
        for field, op_var, val_var in entries:
            new_rules.append({"field": field, "op": op_var.get(), "value": val_var.get()})
        alerts_rules[code] = new_rules
        save_alerts()
        messagebox.showinfo("成功", f"{code} 报警规则已保存")
        editor.destroy()

    tk.Button(editor, text="保存", command=save_rule).grid(row=4, column=0, columnspan=5, pady=10)

# 刷新报警中心
def refresh_alert_center():
    global alerts_history
    if not alert_window or not alert_window.winfo_exists():
        return
    alert_tree.delete(*alert_tree.get_children())
    for alert in alerts_history:
        alert_tree.insert("", "end", values=(alert['time'], alert['code'], alert['name'], alert['msg'], str(alert['rule'])))

# 触发报警
def check_alert(stock_code, stock_data):
    global alerts_history
    rules = alert_rules.get(stock_code, [])
    for rule in rules:
        val = stock_data.get(rule['type'])
        if val is None:
            continue
        if rule['op'] == '>=' and val >= rule['value']:
            alerts_history.append({'time': datetime.now().strftime('%H:%M:%S'),
                                  'code': stock_code, 'name': stock_data['name'],
                                  'msg': f"{rule['type']}={val} 触发 {rule['op']} {rule['value']}",
                                  'rule': rule})
        elif rule['op'] == '<=' and val <= rule['value']:
            alerts_history.append({'time': datetime.now().strftime('%H:%M:%S'),
                                  'code': stock_code, 'name': stock_data['name'],
                                  'msg': f"{rule['type']}={val} 触发 {rule['op']} {rule['value']}",
                                  'rule': rule})
    refresh_alert_center()


def delete_alert_rule(code):
    global alerts_history
    if code in alerts_rules:
        del alerts_rules[code]
        save_alerts()
        messagebox.showinfo("删除规则", f"{code} 的规则已删除")

# ------------------------
# 监控窗口
# ------------------------
def create_monitor_window(code, name):
    global monitor_windows
    win = tk.Toplevel(root)
    win.title(f"{code} - {name}")
    win.geometry("300x150+100+100")

    label = tk.Label(win, text=f"{code} - {name}", font=("Arial", 14))
    label.pack(expand=True, fill="both")

    monitor_windows[code] = {"toplevel": win, "label": label}

    # 右键菜单：报警规则
    def show_menu(event):
        menu = tk.Menu(win, tearoff=0)
        menu.add_command(label="设置报警规则", command=lambda: open_alert_editor(code))
        menu.post(event.x_root, event.y_root)
    win.bind("<Button-3>", show_menu)

# ------------------------
# 模拟行情 & 报警触发
# ------------------------
def simulate_data():
    for code, win in monitor_windows.items():
        price = round(random.uniform(8,15), 2)
        rise = round(random.uniform(-2,8), 2)
        vol = random.randint(1000,20000)
        text = f"{code}\n价格={price}\n涨幅={rise}%\n量={vol}"
        win["label"].config(text=text)

        # 检查规则
        rules = alerts_rules.get(code, [])
        for r in rules:
            val = {"价格": price, "涨幅": rise, "量": vol}[r["field"]]
            if r["op"] == ">=" and val >= r["value"]:
                add_alert(code, code, r["field"], val, f"{r['field']} {r['op']} {r['value']}")
            if r["op"] == "<=" and val <= r["value"]:
                add_alert(code, code, r["field"], val, f"{r['field']} {r['op']} {r['value']}")

    root.after(3000, simulate_data)  # 每 3 秒更新一次

# ------------------------
# 启动逻辑
# ------------------------
root = tk.Tk()
root.title("异动联动监控")
load_alerts()

# 创建几个股票窗口测试
create_monitor_window("600925", "浙能电力")
create_monitor_window("002547", "春兴精工")
create_monitor_window("300027", "华谊兄弟")

root.after(3000, simulate_data)
root.after(10000, flush_alerts)
root.mainloop()
