import json, time, winsound, os
import tkinter as tk
from tkinter import ttk
from win10toast import ToastNotifier

# ========== 配置 ==========
ALERT_FILE = "alerts.json"
ALERT_RULES = {}
FIRED_ALERTS = set()   # 去重用
LOG_FILE = "alerts.log"
toaster = ToastNotifier()


# ========== 加载/刷新规则 ==========
def load_alert_rules():
    global ALERT_RULES
    try:
        with open(ALERT_FILE, "r", encoding="utf-8") as f:
            ALERT_RULES = json.load(f)
        print(f"[规则加载成功] {len(ALERT_RULES)} 组规则")
    except Exception as e:
        print(f"[规则加载失败] {e}")
        ALERT_RULES = {}

load_alert_rules()


# ========== 报警逻辑 ==========
def check_alert(stock_code, row_data, window_info, tree, item_id):
    rules = ALERT_RULES.get(stock_code, ALERT_RULES.get("default", {}))

    for col, expr in rules.items():
        if col in row_data:
            value = row_data[col]
            try:
                if eval(expr, {"value": float(value)}):
                    alert_key = (stock_code, col, expr, value)
                    if alert_key not in FIRED_ALERTS:
                        FIRED_ALERTS.add(alert_key)
                        trigger_alert(stock_code, row_data, window_info, tree, item_id, col, expr)
                        return True
            except Exception as e:
                print(f"[规则错误] {stock_code} {col}: {e}")
    return False


def trigger_alert(stock_code, row_data, window_info, tree, item_id, col, expr):
    title = f"股票异动告警: {stock_code}"
    msg = f"{col} 触发规则 {expr}, 当前值={row_data[col]}"

    print(f"🚨 {title} -> {msg}")
    log_alert(title, msg)

    # 系统通知
    toaster.show_toast(title, msg, duration=5, threaded=True)

    # 播放声音
    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

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


# ========== GUI ==========
def create_monitor_window(stock_code, stock_name):
    win = tk.Toplevel(root)
    win.title(f"监控: {stock_name} ({stock_code})")
    win.geometry("400x180+200+200")

    columns = ("时间", "异动类型", "涨幅", "价格", "量", "报警")
    tree = ttk.Treeview(win, columns=columns, show="headings")
    for col in columns:
        tree.heading(col, text=col)
    tree.pack(expand=True, fill=tk.BOTH)

    window_info = {"stock_info": (stock_code, stock_name), "toplevel": win}

    # 模拟数据
    sample_data = [
        {"时间": "10:00", "异动类型": "普通", "涨幅": "0.5", "价格": "10.5", "量": "8000"},
        {"时间": "10:05", "异动类型": "大单买入", "涨幅": "5.6", "价格": "11.2", "量": "15000"},
        {"时间": "10:10", "异动类型": "回落", "涨幅": "3.2", "价格": "9.8", "量": "5000"},
    ]

    for row in sample_data:
        values = list(row.values()) + [""]
        item_id = tree.insert("", "end", values=values)
        check_alert(stock_code, row, window_info, tree, item_id)

    return win


# ========== 主程序 ==========
if __name__ == "__main__":
    root = tk.Tk()
    root.title("股票异动监控主窗口")
    root.geometry("300x200+50+50")

    tk.Label(root, text="主控窗口（测试）").pack(pady=20)

    # F5 刷新规则
    def reload_rules(event=None):
        load_alert_rules()
        winsound.Beep(800, 200)
        print("[规则已刷新]")

    root.bind("<F5>", reload_rules)

    # 模拟多个股票窗口
    create_monitor_window("600925", "大盘测试")
    create_monitor_window("000809", "个股测试")

    root.mainloop()
