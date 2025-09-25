# -*- coding: utf-8 -*-
"""
alerts_manager.py

AlertManager: 报警数据 + 规则管理 + 检测逻辑
AlertCenter: 报警中心窗口 (History / Rules 编辑)
兼容函数: set_global_manager, check_alert, open_alert_center (方便旧程序直接调用)
"""

import os
import json
import time
from datetime import datetime, timedelta
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# --------------------------
# 配置
# --------------------------
DEFAULT_RULES_FILE = "alerts_rules.json"
DEFAULT_HISTORY_FILE = "alerts_history.json"
ALERT_COOLDOWN_SECONDS = 60  # 同一规则冷却时间（秒）
MAX_HISTORY_KEEP = 2000  # 内存中保留历史条数上限

# --------------------------
# 模块级全局（兼容旧接口）
# --------------------------
_GLOBAL_ALERT_MANAGER = None


def set_global_manager(mgr):
    global _GLOBAL_ALERT_MANAGER
    _GLOBAL_ALERT_MANAGER = mgr


def check_alert(stock_code, price, change, volume, name=None):
    """兼容旧代码：调用已注册的 AlertManager"""
    if _GLOBAL_ALERT_MANAGER is None:
        return
    return _GLOBAL_ALERT_MANAGER.check_and_record(stock_code, price, change, volume, name=name)


def open_alert_center(parent=None):
    """兼容旧代码：弹出报警中心"""
    if _GLOBAL_ALERT_MANAGER is None:
        return None
    return _GLOBAL_ALERT_MANAGER.open_center(parent=parent)


# --------------------------
# AlertManager 类
# --------------------------
class AlertManager(object):
    def __init__(self, storage_dir=".", rules_file=None, history_file=None, logger=None):
        self.logger = logger
        self.storage_dir = storage_dir or "."
        os.makedirs(self.storage_dir, exist_ok=True)
        self.rules_file = os.path.join(self.storage_dir, rules_file or DEFAULT_RULES_FILE)
        self.history_file = os.path.join(self.storage_dir, history_file or DEFAULT_HISTORY_FILE)

        # 数据结构
        # rules: { code: [ {field, op, value, enabled(bool), delta}, ... ] }
        self.rules = {}
        # history: [ {time, stock_code, name, field, op, rule_value, value, delta} ]
        self.history = []
        # 临时缓冲，供 UI flush 使用
        self.buffer = []
        # 冷却记录： key=(code,field,op,value) -> last_time
        self.last_trigger = {}

        # UI 刷新回调（root，func）
        self._ui_root = None
        self._ui_refresh_cb = None

        # 载入已有数据
        self.load_all()

        # 线程锁
        self._lock = threading.RLock()

    # ---------- I/O ----------
    def load_all(self):
        try:
            if os.path.exists(self.rules_file):
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)
            else:
                self.rules = {}
        except Exception as e:
            if self.logger:
                self.logger.error(f"load rules error: {e}")
            self.rules = {}

        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            else:
                self.history = []
        except Exception as e:
            if self.logger:
                self.logger.error(f"load history error: {e}")
            self.history = []

    # 保存单条规则
    def save_rule(self, stock_code, rule):
        """保存单条规则到 stock_code 下"""
        stock_code = str(stock_code)
        if stock_code not in self.rules:
            self.rules[stock_code] = []

        # 查找是否已有同 id 的规则
        rule_id = rule.get("id")
        if rule_id is not None:
            for idx, r in enumerate(self.rules[stock_code]):
                if r.get("id") == rule_id:
                    self.rules[stock_code][idx] = rule
                    break
            else:
                self.rules[stock_code].append(rule)
        else:
            # 自动生成 id
            rule["id"] = len(self.rules[stock_code]) + 1
            self.rules[stock_code].append(rule)

        self.save_rules()

    # 设置某个股票的规则列表
    def set_rules(self, stock_code, rules_list):
        self.rules[str(stock_code)] = rules_list
        self.save_rules()

    # 添加单条规则
    def add_rule(self, stock_code, rule):
        stock_code = str(stock_code)
        lst = self.rules.get(stock_code, [])
        lst.append(rule)
        self.rules[stock_code] = lst
        self.save_rules()

    # 删除某个股票的所有规则
    def delete_rules(self, stock_code):
        stock_code = str(stock_code)
        if stock_code in self.rules:
            del self.rules[stock_code]
            self.save_rules()

    def save_rules(self):
        try:
            with open(self.rules_file, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
        except Exception as e:
            if self.logger:
                self.logger.error(f"save rules error: {e}")

    def save_history(self):
        try:
            # 限长保存
            hist = self.history[-MAX_HISTORY_KEEP:]
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(hist, f, ensure_ascii=False, indent=2)
        except Exception as e:
            if self.logger:
                self.logger.error(f"save history error: {e}")

    def save_all(self):
        with self._lock:
            self.save_rules()
            self.save_history()

    # ---------- 规则管理 ----------
    def get_rules(self, code):
        return self.rules.get(str(code), [])




    # ---------- UI 注册 ----------
    def register_ui(self, root, refresh_callback):
        """注册 UI 回调（root 必须是主线程的 tk root）"""
        self._ui_root = root
        self._ui_refresh_cb = refresh_callback

    def _ui_notify(self):
        if self._ui_root and self._ui_refresh_cb:
            try:
                self._ui_root.after(0, self._ui_refresh_cb)
            except Exception:
                # if UI gone
                pass

    # ---------- 报警检测逻辑 ----------
    def _rule_triggered(self, rule, val):
        """判断单条规则是否被触发"""
        op = rule.get("op", ">=")
        try:
            rule_val = float(rule.get("value", 0))
            cur_val = float(val)
        except Exception:
            return False
        if op == ">=":
            return cur_val >= rule_val
        elif op == "<=":
            return cur_val <= rule_val
        else:
            return False

    def _cooldown_ok(self, key):
        last = self.last_trigger.get(key)
        if last is None:
            return True
        return (datetime.now() - last).total_seconds() >= ALERT_COOLDOWN_SECONDS

    def _update_last_trigger(self, key):
        self.last_trigger[key] = datetime.now()

    def check_and_record(self, stock_code, price, change, volume, name=None):
        """
        检查 stock_code 是否触发规则。
        price/change/volume 三者按规则 'field' 映射：'价格'->price, '涨幅'->change, '量'->volume
        如果触发记录到 history 并返回 True, 否则 False。
        """
        with self._lock:
            code = str(stock_code)
            rules = self.rules.get(code)
            if not rules:
                return False

            name = name or code
            field_map = {"价格": price, "涨幅": change, "量": volume}

            triggered_any = False
            for rule in rules:
                if not rule.get("enabled", True):
                    continue
                field = rule.get("field")
                if field not in field_map:
                    continue
                val = field_map[field]
                if val is None:
                    continue
                # 变化阈值检查（delta）
                delta_thr = rule.get("delta", 0)
                # 冷却键
                key = (code, field, rule.get("op", ">="), float(rule.get("value", 0)))
                if not self._cooldown_ok(key):
                    continue

                if self._rule_triggered(rule, val):
                    # 有触发
                    self._update_last_trigger(key)
                    triggered_any = True
                    alert = {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "stock_code": code,
                        "name": name,
                        "field": field,
                        "op": rule.get("op", ">="),
                        "rule_value": rule.get("value"),
                        "value": val,
                        "delta": round(abs(val - rule.get("value", 0)) if isinstance(val, (int, float)) else 0, 4)
                    }
                    # 保存到历史与 buffer
                    self.history.append(alert)
                    self.buffer.append(alert)
                    # 限制内存
                    if len(self.history) > MAX_HISTORY_KEEP:
                        self.history = self.history[-MAX_HISTORY_KEEP:]
                    # 如果 UI 已注册，通知刷新
                    self._ui_notify()
            # 每次检测后持久化（可改为批量）
            if triggered_any:
                self.save_history()
            return triggered_any

    # ---------- 获取历史 / flush ----------
    def get_history(self, limit=500):
        return list(self.history[-limit:])[::-1]

    def pop_buffer(self):
        with self._lock:
            buf = list(self.buffer)
            self.buffer = []
        return buf

    # ---------- 便捷 UI 打开函数 ----------
    def open_center(self, parent=None):
        if parent is None:
            # 如果没有指定 parent，尝试使用 tk._default_root
            parent = tk._default_root
        if parent is None:
            raise RuntimeError("No tk root available to open alert center")
        ac = AlertCenter(parent, self)
        return ac

'''
import os
import json
import datetime

class AlertManager:
    def __init__(self, storage_dir, logger=None):
        self.storage_dir = storage_dir
        self.logger = logger
        self.rules_file = os.path.join(storage_dir, "alert_rules.json")
        self.rules = []
        self.load_rules()

    def log(self, msg):
        if self.logger:
            self.logger.info(msg)
        else:
            print(msg)

    def load_rules(self):
        """从本地加载规则"""
        if os.path.exists(self.rules_file):
            try:
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)
                self.log(f"加载报警规则 {len(self.rules)} 条")
            except Exception as e:
                self.log(f"加载规则失败: {e}")
                self.rules = []
        else:
            self.rules = []

    def save_rules_to_file(self):
        """写入文件"""
        try:
            os.makedirs(self.storage_dir, exist_ok=True)
            with open(self.rules_file, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
            self.log(f"规则保存成功: {len(self.rules)} 条")
        except Exception as e:
            self.log(f"保存规则失败: {e}")

    def save_rule(self, rule: dict):
        """添加/更新规则"""
        # rule 结构: {stock, cond_type, threshold, created_at}
        if "created_at" not in rule:
            rule["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 查重（相同股票+条件）
        for r in self.rules:
            if r["stock"] == rule["stock"] and r["cond_type"] == rule["cond_type"]:
                r.update(rule)
                self.save_rules_to_file()
                self.log(f"更新规则: {rule}")
                return

        # 新增
        self.rules.append(rule)
        self.save_rules_to_file()
        self.log(f"新增规则: {rule}")

    def delete_rule(self, rule):
        """删除某条规则"""
        self.rules = [r for r in self.rules if r != rule]
        self.save_rules_to_file()
        self.log(f"删除规则: {rule}")

    def get_rules(self):
        """返回所有规则"""
        return self.rules
'''

# --------------------------
# AlertCenter UI（History + Rules 编辑）
# --------------------------
class AlertCenter(tk.Toplevel):
    def __init__(self, parent, manager: AlertManager):
        super().__init__(parent)
        self.parent = parent
        self.manager = manager
        self.title("报警中心")
        self.geometry("780x420")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.transient(parent)
        self.grab_set()

        # 注册 UI 回调（manager 会通过 root.after 刷新）
        self.manager.register_ui(self, self.refresh_history)

        # Notebook
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)

        # History tab
        self.frame_hist = ttk.Frame(self.nb)
        self.nb.add(self.frame_hist, text="报警历史")
        self._build_history_tab(self.frame_hist)

        # Rules tab
        self.frame_rules = ttk.Frame(self.nb)
        self.nb.add(self.frame_rules, text="规则管理")
        self._build_rules_tab(self.frame_rules)

        # 初次刷新
        self.refresh_history()
        self.refresh_rules_list()

    # ---- History ----
    def _build_history_tab(self, parent):
        cols = ("time", "stock_code", "name", "field", "rule", "value", "delta")
        headings = ("时间", "代码", "名称", "字段", "规则", "现值", "变化量")
        frm = ttk.Frame(parent)
        frm.pack(fill="both", expand=True)

        self.tree_hist = ttk.Treeview(frm, columns=cols, show="headings")
        for c, h in zip(cols, headings):
            self.tree_hist.heading(c, text=h)
            self.tree_hist.column(c, width=100, anchor="center")
        self.tree_hist.column("name", width=140)
        self.tree_hist.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(frm, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscroll=vsb.set)
        vsb.pack(side="right", fill="y")

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="清空历史", command=self.clear_history).pack(side="left", padx=4, pady=6)
        ttk.Button(btn_frame, text="刷新", command=self.refresh_history).pack(side="left", padx=4)

    def refresh_history(self):
        # 从 manager 获取
        hist = self.manager.get_history(limit=1000)
        self.tree_hist.delete(*self.tree_hist.get_children())
        for a in hist:
            rule_repr = f"{a.get('field')} {a.get('op')}{a.get('rule_value')}"
            vals = (a.get("time"), a.get("stock_code"), a.get("name"), a.get("field"), rule_repr, a.get("value"), a.get("delta"))
            self.tree_hist.insert("", "end", values=vals)

    def clear_history(self):
        if messagebox.askyesno("确认", "确定要清空报警历史吗？"):
            self.manager.history = []
            self.manager.save_history()
            self.refresh_history()

    # ---- Rules ----
    def _build_rules_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=4)

        ttk.Label(top, text="股票:").pack(side="left")
        self.stock_var = tk.StringVar()
        self.stock_combo = ttk.Combobox(top, textvariable=self.stock_var, values=[], width=20)
        self.stock_combo.pack(side="left", padx=6)
        self.stock_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_rules_list())
        ttk.Button(top, text="编辑规则", command=self.open_editor_for_selected).pack(side="left", padx=6)
        ttk.Button(top, text="删除规则", command=self.delete_selected_rules).pack(side="left", padx=6)
        ttk.Button(top, text="刷新", command=self.refresh_rules_list).pack(side="left", padx=6)
        ttk.Button(top, text="保存", command=self.manager.save_rules).pack(side="right", padx=6)

        # rules display
        cols = ("idx", "field", "op", "value", "enabled", "delta")
        self.tree_rules = ttk.Treeview(parent, columns=cols, show="headings", height=10)
        self.tree_rules.heading("idx", text="#")
        self.tree_rules.heading("field", text="字段")
        self.tree_rules.heading("op", text="操作")
        self.tree_rules.heading("value", text="值")
        self.tree_rules.heading("enabled", text="启用")
        self.tree_rules.heading("delta", text="delta")
        self.tree_rules.column("idx", width=40, anchor="center")
        self.tree_rules.pack(fill="both", expand=True, padx=4, pady=4)

    def refresh_rules_list(self):
        # 填充 combobox: 所有有规则的 code
        keys = sorted(list(self.manager.rules.keys()))
        self.stock_combo['values'] = keys
        cur = self.stock_var.get() or (keys[0] if keys else "")
        if cur not in keys and keys:
            cur = keys[0]
        self.stock_var.set(cur)
        # fill rules
        self.tree_rules.delete(*self.tree_rules.get_children())
        if not cur:
            return
        rules = self.manager.get_rules(cur)
        for i, r in enumerate(rules):
            enabled = "是" if r.get("enabled", True) else "否"
            self.tree_rules.insert("", "end", values=(i + 1, r.get("field"), r.get("op"), r.get("value"), enabled, r.get("delta", "")))

    def open_editor_for_selected(self):
        code = self.stock_var.get().strip()
        if not code:
            messagebox.showinfo("提示", "请先选择一个股票代码")
            return
        EditRuleDialog(self, self.manager, code, on_saved=self.refresh_rules_list)

    def delete_selected_rules(self):
        code = self.stock_var.get().strip()
        if not code:
            return
        if messagebox.askyesno("确认", f"确定删除 {code} 的所有规则吗？"):
            self.manager.delete_rules(code)
            self.refresh_rules_list()

    def on_close(self):
        self.manager.save_all()
        self.destroy()

# --------------------------
# 编辑对话框：编辑/新增规则（简单表单）
# --------------------------
class EditRuleDialog(tk.Toplevel):
    def __init__(self, parent, manager: AlertManager, code, on_saved=None):
        super().__init__(parent)
        self.parent = parent
        self.manager = manager
        self.code = str(code)
        self.on_saved = on_saved
        self.title(f"编辑规则 - {self.code}")
        self.geometry("520x320")
        self.transient(parent)
        self.grab_set()

        self.rules = list(self.manager.get_rules(self.code))  # copy
        # UI
        self._build_ui()
        self.refresh_list()

    def _build_ui(self):
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text=f"股票: {self.code}").pack(side="left")
        ttk.Button(top, text="新增规则", command=self.add_new_rule).pack(side="right")

        # rules tree
        cols = ("field", "op", "value", "enabled", "delta")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings", height=8)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=90, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=6)

        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="编辑选中", command=self.edit_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="删除选中", command=self.delete_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="保存并关闭", command=self.save_and_close).pack(side="right", padx=6)
        ttk.Button(btns, text="取消", command=self.cancel).pack(side="right", padx=6)

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.rules:
            self.tree.insert("", "end", values=(r.get("field"), r.get("op"), r.get("value"), "是" if r.get("enabled", True) else "否", r.get("delta", "")))

    def add_new_rule(self):
        default = {"field": "价格", "op": ">=", "value": 1.0, "enabled": True, "delta": 0.1}
        self.rules.append(default)
        self.edit_rule(len(self.rules) - 1)

    def edit_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        self.edit_rule(idx)

    def edit_rule(self, idx):
        r = self.rules[idx]

        d = EditSingleRuleDialog(self, r)
        self.wait_window(d)
        if d.result is not None:
            self.rules[idx] = d.result
            self.refresh_list()

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        del self.rules[idx]
        self.refresh_list()

    def save_and_close(self):
        # persist
        self.manager.set_rules(self.code, self.rules)
        if self.on_saved:
            try:
                self.on_saved()
            except Exception:
                pass
        self.destroy()

    def cancel(self):
        self.destroy()


class EditSingleRuleDialog(simpledialog.Dialog):
    def __init__(self, parent, rule):
        self.rule = dict(rule)
        super().__init__(parent, title="编辑规则")

    def body(self, master):
        ttk.Label(master, text="字段:").grid(row=0, column=0, sticky="w")
        self.field_var = tk.StringVar(value=self.rule.get("field", "价格"))
        ttk.Combobox(master, textvariable=self.field_var, values=["价格", "涨幅", "量"], width=12).grid(row=0, column=1)

        ttk.Label(master, text="操作:").grid(row=1, column=0, sticky="w")
        self.op_var = tk.StringVar(value=self.rule.get("op", ">="))
        ttk.Combobox(master, textvariable=self.op_var, values=[">=", "<="], width=6).grid(row=1, column=1)

        ttk.Label(master, text="值:").grid(row=2, column=0, sticky="w")
        self.value_var = tk.DoubleVar(value=float(self.rule.get("value", 0) or 0))
        ttk.Entry(master, textvariable=self.value_var).grid(row=2, column=1)

        ttk.Label(master, text="启用:").grid(row=3, column=0, sticky="w")
        self.en_var = tk.BooleanVar(value=self.rule.get("enabled", True))
        ttk.Checkbutton(master, variable=self.en_var).grid(row=3, column=1)

        ttk.Label(master, text="delta:").grid(row=4, column=0, sticky="w")
        self.delta_var = tk.DoubleVar(value=float(self.rule.get("delta", 0) or 0))
        ttk.Entry(master, textvariable=self.delta_var).grid(row=4, column=1)

        return None

    def apply(self):
        r = {
            "field": self.field_var.get(),
            "op": self.op_var.get(),
            "value": float(self.value_var.get()),
            "enabled": bool(self.en_var.get()),
            "delta": float(self.delta_var.get())
        }
        self.result = r

# --------------------------
# end of module
# --------------------------

# from alerts_manager import AlertManager, set_global_manager, open_alert_center
# 创建 AlertManager（放在 DARACSV_DIR 下存储）

# 在 StockMonitorApp.__init__（或主程序初始化部分）里加
# self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=log)
# set_global_manager(self.alert_manager)

# # 在你的 ctrl_frame 上添加打开按钮（放到你已有按钮附近）
# tk.Button(ctrl_frame, text="报警中心", command=lambda: open_alert_center(self)).pack(side="left", padx=2)

# 如果老代码某处直接调用 check_alert(...)，不需要改动。模块层的 check_alert() 会转发到刚刚注册的 AlertManager。如果你想显式调用
# self.alert_manager.check_and_record(code, price, change, volume, name=stock_name)

# 程序退出前确保保存（可选，因为 AlertCenter 退出会保存）：
# self.alert_manager.save_all()