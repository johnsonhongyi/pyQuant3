# -*- coding: utf-8 -*-
import os, json, threading, tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import random, time

# ---------------- 配置 ----------------
DEFAULT_RULES_FILE = "alerts_rules.json"
DEFAULT_HISTORY_FILE = "alerts_history.json"
ALERT_COOLDOWN_SECONDS = 60
MAX_HISTORY_KEEP = 2000

# ---------------- AlertManager ----------------
class AlertManager:
    def __init__(self, storage_dir=".", logger=None, ui_root=None):
        self.logger = logger
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.rules_file = os.path.join(self.storage_dir, DEFAULT_RULES_FILE)
        self.history_file = os.path.join(self.storage_dir, DEFAULT_HISTORY_FILE)

        self.rules = {}      # {code:[{field, op, value, enabled, delta}]}
        self.history = []    # 历史报警
        self.buffer = []     # UI缓存
        self.last_trigger = {}  # 冷却记录

        self._ui_root = ui_root
        self._ui_refresh_cb = None

        self._lock = threading.RLock()
        self.detail_win = None
        self.secondary_win = None
        self.secondary_list = []

        self.load_all()

    # -------- I/O ----------
    def load_all(self):
        try:
            if os.path.exists(self.rules_file):
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)
        except:
            self.rules = {}
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
        except:
            self.history = []

    def save_rules(self):
        with open(self.rules_file, "w", encoding="utf-8") as f:
            json.dump(self.rules, f, ensure_ascii=False, indent=2)

    def save_history(self):
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.history[-MAX_HISTORY_KEEP:], f, ensure_ascii=False, indent=2)

    def save_all(self):
        with self._lock:
            self.save_rules()
            self.save_history()

    # -------- UI ----------
    def register_ui(self, root, refresh_callback):
        self._ui_root = root
        self._ui_refresh_cb = refresh_callback

    def _ui_notify(self):
        if self._ui_root and self._ui_refresh_cb:
            try:
                self._ui_root.after(0, self._ui_refresh_cb)
            except:
                pass

    # -------- 阈值 & 冷却 ----------
    def adaptive_threshold(self, base_value, market_volatility):
        factor = 1 + 0.5 * market_volatility
        return base_value * factor

    def _cooldown_ok(self, key):
        last = self.last_trigger.get(key)
        if last is None:
            return True
        return (datetime.now() - last).total_seconds() >= ALERT_COOLDOWN_SECONDS

    def _update_last_trigger(self, key):
        self.last_trigger[key] = datetime.now()

    # -------- 核心检测 ----------
    def check_and_record(self, stock_code, price, change, volume, name=None, market_vol=0.5):
        with self._lock:
            code = str(stock_code)
            rules = self.rules.get(code)
            if not rules:
                return {}
            name = name or code
            field_map = {"价格": price, "涨幅": change, "量": volume}
            triggered_levels = {"strong": [], "medium": [], "weak": []}

            for rule in rules:
                if not rule.get("enabled", True):
                    continue
                field = rule.get("field")
                val = field_map.get(field)
                if val is None:
                    continue
                base_thr = float(rule.get("value", 0))
                thr = self.adaptive_threshold(base_thr, market_vol)
                op = rule.get("op", ">=")
                key = (code, field, op, thr)
                if not self._cooldown_ok(key):
                    continue
                triggered = (val >= thr if op==">=" else val <= thr)
                if triggered:
                    self._update_last_trigger(key)
                    delta = abs(val - thr)
                    alert = {"time": datetime.now().strftime("%H:%M:%S"),
                             "code": code, "name": name,
                             "field": field, "value": val,
                             "threshold": thr, "delta": delta}
                    self.history.append(alert)
                    self.buffer.append(alert)
                    # 分级
                    if delta >= 0.1*thr:
                        triggered_levels["strong"].append(alert)
                    elif delta >= 0.05*thr:
                        triggered_levels["medium"].append(alert)
                    else:
                        triggered_levels["weak"].append(alert)
            # 弹窗极强
            for a in triggered_levels["strong"]:
                self._popup_strong_alert(a)
            # 次强信号列表
            for a in triggered_levels["medium"]:
                self._popup_secondary_signal(a)
            self._ui_notify()
            if triggered_levels["strong"] or triggered_levels["medium"] or triggered_levels["weak"]:
                self.save_history()
            return triggered_levels

    # -------- 弹窗处理 ----------
    def _popup_strong_alert(self, alert):
        self._show_detail_win(alert, title="极强信号")

    def _popup_secondary_signal(self, alert):
        self.secondary_list.append(alert)
        self._show_secondary_win()

    def _show_detail_win(self, alert, title="详情"):
        txt_content = f"{alert['time']} {alert['code']} {alert['name']}\n{alert['field']}={alert['value']} (阈值={alert['threshold']})"
        if self.detail_win and self.detail_win.winfo_exists():
            self.detail_win.title(f"{title} - {alert['code']}")
            self.txt_widget.config(state="normal")
            self.txt_widget.delete("1.0", "end")
            self.txt_widget.insert("1.0", txt_content)
            self.txt_widget.config(state="disabled")
            self.detail_win.focus_force()
            self.detail_win.lift()
        else:
            self.detail_win = tk.Toplevel(self._ui_root)
            self.detail_win.title(f"{title} - {alert['code']}")
            self.detail_win.geometry("400x200")
            self.txt_widget = tk.Text(self.detail_win, wrap="word", font=("微软雅黑", 12))
            self.txt_widget.pack(expand=True, fill="both")
            self.txt_widget.insert("1.0", txt_content)
            self.txt_widget.config(state="disabled")
            self.detail_win.focus_force()
            self.detail_win.lift()
            self.detail_win.bind("<Escape>", lambda e: self.detail_win.destroy())

    def _show_secondary_win(self):
        if self.secondary_win and self.secondary_win.winfo_exists():
            self._update_secondary_list()
            self.secondary_win.focus_force()
            self.secondary_win.lift()
        else:
            self.secondary_win = tk.Toplevel(self._ui_root)
            self.secondary_win.title("次强信号列表")
            self.secondary_win.geometry("500x300")
            self.sec_tree = ttk.Treeview(self.secondary_win, columns=("time","code","name","field","value"), show="headings")
            for c in ("time","code","name","field","value"):
                self.sec_tree.heading(c, text=c)
                self.sec_tree.column(c, width=80)
            self.sec_tree.pack(expand=True, fill="both")
            self.secondary_win.bind("<Escape>", lambda e: self.secondary_win.destroy())
            self._update_secondary_list()

    def _update_secondary_list(self):
        self.sec_tree.delete(*self.sec_tree.get_children())
        for a in self.secondary_list[-100:]:
            self.sec_tree.insert("", "end", values=(a["time"],a["code"],a["name"],a["field"],a["value"]))

    # -------- 历史/缓冲 ----------
    def get_history(self, limit=500):
        return list(self.history[-limit:])[::-1]

    def pop_buffer(self):
        with self._lock:
            buf = list(self.buffer)
            self.buffer = []
        return buf

    def set_field_list(self, fields):
            """设置可用字段列表"""
            self._fields = list(fields)

    def get_field_list(self):
        """获取字段列表"""
        return getattr(self, "_fields", ["价格", "涨幅", "量"])

# ---------------- 实时信号 UI ----------------
class SignalMonitorUI(tk.Tk):
    def __init__(self, alert_manager):
        super().__init__()
        self.title("实时信号监控")
        self.geometry("800x400")
        self.alert_manager = alert_manager
        self.alert_manager.register_ui(self, self.refresh_ui)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.frames = {}
        for lvl in ["strong","medium","weak"]:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=lvl.capitalize())
            tree = ttk.Treeview(frame, columns=("time","code","name","field","value","threshold","delta"), show="headings")
            for c in ("time","code","name","field","value","threshold","delta"):
                tree.heading(c, text=c)
                tree.column(c, width=100)
            tree.pack(expand=True, fill="both")
            self.frames[lvl] = tree

        # 模拟实时数据刷新
        self.after(1000, self._simulate_data)

    def refresh_ui(self):
        buf = self.alert_manager.pop_buffer()
        lvl_map = {"strong":"strong","medium":"medium","weak":"weak"}
        trees = self.frames
        for lvl in trees:
            tree = trees[lvl]
            for a in buf:
                delta = abs(a["value"] - a["threshold"])
                if delta >= 0.1*a["threshold"]:
                    tree_lvl = "strong"
                elif delta >= 0.05*a["threshold"]:
                    tree_lvl = "medium"
                else:
                    tree_lvl = "weak"
                if tree_lvl != lvl:
                    continue
                tree.insert("", "end", values=(a["time"],a["code"],a["name"],a["field"],a["value"],a["threshold"],delta))

    def _simulate_data(self):
        # 模拟行情
        sample_codes = list(self.alert_manager.rules.keys())
        for code in sample_codes:
            price = random.uniform(1,20)
            change = random.uniform(-5,5)
            volume = random.randint(100,1000)
            self.alert_manager.check_and_record(code, price, change, volume)
        self.after(2000, self._simulate_data)



# class EditSingleRuleDialog(simpledialog.Dialog):
#     def __init__(self, parent, rule):
#         self.rule = dict(rule)
#         super().__init__(parent, title="编辑规则")

#     def body(self, master):
#         # ttk.Label(master, text="字段:").grid(row=0, column=0, sticky="w")
#         # self.field_var = tk.StringVar(value=self.rule.get("field", "价格"))
#         # ttk.Combobox(master, textvariable=self.field_var, values=["价格", "涨幅", "量"], width=12).grid(row=0, column=1)
#         # 字段
#         ttk.Label(master, text="字段:").grid(row=0, column=0, sticky="w")
#         field_list = self.parent.manager.get_field_list()  # 动态字段
#         self.field_var = tk.StringVar(value=self.rule.get("field", field_list[0] if field_list else "价格"))
#         ttk.Combobox(master, textvariable=self.field_var, values=field_list, width=15).grid(row=0, column=1)


#         ttk.Label(master, text="操作:").grid(row=1, column=0, sticky="w")
#         self.op_var = tk.StringVar(value=self.rule.get("op", ">="))
#         ttk.Combobox(master, textvariable=self.op_var, values=[">=", "<="], width=6).grid(row=1, column=1)

#         ttk.Label(master, text="值:").grid(row=2, column=0, sticky="w")
#         self.value_var = tk.DoubleVar(value=float(self.rule.get("value", 0) or 0))
#         ttk.Entry(master, textvariable=self.value_var).grid(row=2, column=1)

#         ttk.Label(master, text="启用:").grid(row=3, column=0, sticky="w")
#         self.en_var = tk.BooleanVar(value=self.rule.get("enabled", True))
#         ttk.Checkbutton(master, variable=self.en_var).grid(row=3, column=1)

#         ttk.Label(master, text="delta:").grid(row=4, column=0, sticky="w")
#         self.delta_var = tk.DoubleVar(value=float(self.rule.get("delta", 0) or 0))
#         ttk.Entry(master, textvariable=self.delta_var).grid(row=4, column=1)

#         return None

#     def apply(self):
#         r = {
#             "field": self.field_var.get(),
#             "op": self.op_var.get(),
#             "value": float(self.value_var.get()),
#             "enabled": bool(self.en_var.get()),
#             "delta": float(self.delta_var.get())
#         }
#         self.result = r

# ---------------- 主程序 ----------------
if __name__ == "__main__":
    # 初始化 AlertManager
    alert_mgr = AlertManager(storage_dir=".")
    # 添加示例规则
    alert_mgr.rules = {
        "AAPL":[{"field":"价格","op":">=","value":10,"enabled":True}],
        "TSLA":[{"field":"涨幅","op":">=","value":2,"enabled":True}],
        "GOOG":[{"field":"价格","op":">=","value":15,"enabled":True}],
    }

    app = SignalMonitorUI(alert_mgr)
    app.mainloop()

# # 假设 df 是你的日线数据 DataFrame
# alert_mgr.set_field_list(df.columns.tolist())