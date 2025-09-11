import json, time, winsound
import tkinter as tk
from tkinter import ttk
from win10toast import ToastNotifier
import os
toaster = ToastNotifier()
import time

ALERT_COOLDOWN = 60  # 冷却时间，单位秒
FIRED_ALERTS = {}     # key -> last_trigger_time

ALERT_RULES = json.load(open("alert_rules.json", "r", encoding="utf-8"))
# FIRED_ALERTS = set()   # 去重用
LOG_FILE = "alerts.log"


def load_alert_rules(file="alert_rules.json"):
    global ALERT_RULES
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            try:
                ALERT_RULES = json.load(f)
                print("✅ 报警规则已加载")
            except Exception as e:
                print("❌ 报警规则解析失败:", e)
                ALERT_RULES = {}
    else:
        print("⚠️ 未找到报警规则文件，使用默认规则")
        ALERT_RULES = {}



def check_alert(stock_code, row_data, window_info, tree, item_id):
    rules = ALERT_RULES.get(stock_code, ALERT_RULES.get("default", {}))

    for col, expr in rules.items():
        if col in row_data:
            value = row_data[col]
            try:
                if eval(expr, {"value": float(value)}):
                    alert_key = (stock_code, col, expr)
                    now = time.time()
                    last_trigger = FIRED_ALERTS.get(alert_key, 0)
                    if now - last_trigger >= ALERT_COOLDOWN:
                        FIRED_ALERTS[alert_key] = now
                        trigger_alert(stock_code, row_data, window_info, tree, item_id, col, expr)
                        return True
            except Exception as e:
                print(f"[规则错误] {stock_code} {col}: {e}")
    return False


# def check_alert(stock_code, row_data, window_info, tree, item_id):
#     rules = ALERT_RULES.get(stock_code, ALERT_RULES.get("default", {}))

#     for col, expr in rules.items():
#         if col in row_data:
#             value = row_data[col]
#             try:
#                 if eval(expr, {"value": float(value)}):
#                     alert_key = (stock_code, col, expr, value)
#                     if alert_key not in FIRED_ALERTS:
#                         FIRED_ALERTS.add(alert_key)
#                         trigger_alert(stock_code, row_data, window_info, tree, item_id, col, expr)
#                         return True
#             except Exception as e:
#                 print(f"[规则错误] {stock_code} {col}: {e}")
#     return False


def trigger_alert(stock_code, row_data, window_info, tree, item_id, col, expr):
    title = f"股票异动告警: {stock_code}"
    msg = f"{col} 触发规则 {expr}, 当前值={row_data[col]}"

    print(f"🚨 {title} -> {msg}")
    log_alert(title, msg)

    # 系统通知
    toaster.show_toast(title, msg, duration=5, threaded=True)

    # 播放声音
    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

    # 窗口闪烁
    flash_window(window_info['toplevel'])

    # 高亮
    tree.item(item_id, tags=("alert",))
    tree.tag_configure("alert", background="red", foreground="white")

    # 标记⚠
    values = list(tree.item(item_id, "values"))
    if len(values) == len(tree["columns"]):  # 已经有报警列
        values[-1] = "⚠"
    tree.item(item_id, values=values)


def log_alert(title, msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {title} -> {msg}\n")

def flash_window(window, count=6, interval=300):
    def _flash(i=0):
        if i >= count:
            window.configure(bg="SystemButtonFace")  # 还原
            return
        color = "red" if i % 2 == 0 else "SystemButtonFace"
        window.configure(bg=color)
        window.after(interval, _flash, i+1)
    _flash()


def create_monitor_window(stock_code, stock_name):
    win = tk.Toplevel(root)
    win.title(f"监控: {stock_name} ({stock_code})")
    win.geometry("380x180+200+200")

    columns = ("时间", "异动类型", "涨幅", "价格", "量", "报警")
    tree = ttk.Treeview(win, columns=columns, show="headings")
    for col in columns:
        tree.heading(col, text=col)
    tree.pack(expand=True, fill=tk.BOTH)

    window_info = {"stock_info": (stock_code, stock_name), "toplevel": win}

    # 插入模拟数据 & 检查报警
    sample_data = [
        {"时间": "10:00", "异动类型": "普通", "涨幅": "0.5", "价格": "10.5", "量": "8000"},
        {"时间": "10:05", "异动类型": "大单买入", "涨幅": "5.6", "价格": "11.2", "量": "15000"},
    ]

    for row in sample_data:
        values = list(row.values()) + [""]
        item_id = tree.insert("", "end", values=values)
        check_alert(stock_code, row, window_info, tree, item_id)

    return win


# -----------------------------
# 主程序
# -----------------------------
if __name__ == "__main__":
    load_alert_rules()

    root = tk.Tk()
    root.title("股票异动监控")
    root.geometry("400x200+100+100")

    tk.Button(root, text="打开窗口 000001", command=lambda: create_monitor_window("000001", "上证指数")).pack(pady=10)
    tk.Button(root, text="打开窗口 300027", command=lambda: create_monitor_window("300027", "股票B")).pack(pady=10)

    root.mainloop()
