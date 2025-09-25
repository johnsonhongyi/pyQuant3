# -*- coding: utf-8 -*-
import os, json, threading, tkinter as tk
from tkinter import ttk, messagebox, simpledialog, font as tkfont
from datetime import datetime

ALERT_COOLDOWN_SECONDS = 60
MAX_HISTORY_KEEP = 2000

_GLOBAL_ALERT_MANAGER = None
def set_global_manager(mgr): global _GLOBAL_ALERT_MANAGER; _GLOBAL_ALERT_MANAGER = mgr
def check_alert(stock_code, price, change, volume, name=None):
    if _GLOBAL_ALERT_MANAGER is None: return
    return _GLOBAL_ALERT_MANAGER.check_and_record(stock_code, price, change, volume, name=name)
def open_alert_center(parent=None):
    if _GLOBAL_ALERT_MANAGER is None: return None
    return _GLOBAL_ALERT_MANAGER.open_center(parent=parent)

class AlertManager:
    def __init__(self, storage_dir=".", rules_file="alerts_rules.json", history_file="alerts_history.json", logger=None):
        self.logger = logger
        self.storage_dir = storage_dir; os.makedirs(storage_dir, exist_ok=True)
        self.rules_file = os.path.join(storage_dir, rules_file)
        self.history_file = os.path.join(storage_dir, history_file)
        self.rules = {}  # code -> list of rules
        self.history = []
        self.buffer = []
        self.last_trigger = {}
        self.dynamic_threshold = {"涨幅":1.0,"量":1.0}
        self._ui_root = None
        self._ui_refresh_cb = None
        self._lock = threading.RLock()
        self.detail_win = None
        self.txt_widget = None
        self.load_all()

        self.dynamic_threshold = {}  # 每只股票的动态阈值存储

        self.detail_win = None  # 单例弹窗
        self.detail_txt = None

        self.secondary_win = None  # 次强信号窗口
        self.secondary_tree = None
        self.secondary_filter_var = None

    # ---------- I/O ----------
    def load_all(self):
        try: self.rules = json.load(open(self.rules_file, "r", encoding="utf-8")) if os.path.exists(self.rules_file) else {}
        except: self.rules = {}
        try: self.history = json.load(open(self.history_file, "r", encoding="utf-8")) if os.path.exists(self.history_file) else []
        except: self.history = []

    def save_rules(self):
        try: json.dump(self.rules, open(self.rules_file,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        except: pass
    def save_history(self):
        try:
            hist = self.history[-MAX_HISTORY_KEEP:]
            json.dump(hist, open(self.history_file,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        except: pass
    def save_all(self):
        with self._lock: self.save_rules(); self.save_history()

    # ---------- UI ----------
    def register_ui(self, root, refresh_callback):
        self._ui_root = root; self._ui_refresh_cb = refresh_callback
    def _ui_notify(self):
        if self._ui_root and self._ui_refresh_cb:
            try: self._ui_root.after(0, self._ui_refresh_cb)
            except: pass

    # ---------- 规则 ----------
    def get_rules(self, code): return self.rules.get(str(code), [])
    def set_rules(self, code, rules_list): self.rules[str(code)] = rules_list; self.save_rules()

    # ---------- 信号检测 ----------
    def _rule_triggered(self, rule, val):
        try: cur_val = float(val); rule_val = float(rule.get("value",0))
        except: return False
        op = rule.get("op", ">=")
        return cur_val >= rule_val if op==">=" else cur_val <= rule_val if op=="<=" else False

    def _cooldown_ok(self, key):
        last = self.last_trigger.get(key)
        return True if last is None else (datetime.now()-last).total_seconds()>=ALERT_COOLDOWN_SECONDS
    def _update_last_trigger(self,key): self.last_trigger[key]=datetime.now()

    def update_stock_threshold(self, stock_code, window=50):
        """
        为单只股票计算动态阈值
        """
        # 获取该股票最近 window 条历史
        recent = [h for h in self.history[-window:] if h.get("stock_code") == stock_code]

        # 计算涨幅和量均值
        percent_list = [h.get("value",0) for h in recent if h.get("field")=="涨幅"]
        volume_list = [h.get("value",0) for h in recent if h.get("field")=="量"]

        avg_percent = max(0.5, sum(percent_list)/len(percent_list)) if percent_list else 1.0
        avg_volume = max(1, sum(volume_list)/len(volume_list)) if volume_list else 1.0

        # 存储阈值
        self.dynamic_threshold[stock_code] = {
            "涨幅": round(avg_percent * 1.0, 4),  # 次强阈值
            "涨幅_ext": round(avg_percent * 1.5, 4),  # 极强阈值
            "量": round(avg_volume * 1.0, 0),
            "量_ext": round(avg_volume * 1.5, 0)
        }

    def classify_signal(self, stock_code, field, value):
        """
        返回信号等级: "strong", "medium", "weak"
        """
        thresholds = self.dynamic_threshold.get(stock_code, {})
        if field not in thresholds:
            return "weak"
        if value >= thresholds.get(f"{field}_ext", 999999):
            return "strong"
        elif value >= thresholds.get(field, 999999):
            return "medium"
        else:
            return "weak"

    # def classify_signal(self, alert):
    #     """分级策略"""
    #     val = alert.get("value",0)
    #     field = alert.get("field")
    #     thr = self.dynamic_threshold.get(field, 1.0)
    #     if val >= thr*2: return "极强"
    #     elif val >= thr: return "次强"
    #     else: return "弱"

    def show_alert_popup(self, alert):
        """复用单例弹窗"""
        if self.detail_win and self.detail_win.winfo_exists():
            win = self.detail_win
            win.title(f"{alert['stock_code']} - {alert['level']}")
            self.txt_widget.config(state="normal")
            self.txt_widget.delete("1.0", tk.END)
            self.txt_widget.insert("1.0", str(alert))
            self.txt_widget.config(state="disabled")
            win.lift(); win.focus_force()
        else:
            self.detail_win = tk.Toplevel()
            self.detail_win.title(f"{alert['stock_code']} - {alert['level']}")
            self.detail_win.geometry("400x200")
            self.detail_win.bind("<Escape>", lambda e: self.detail_win.destroy())
            self.txt_widget = tk.Text(self.detail_win, font=("微软雅黑",12))
            self.txt_widget.pack(expand=True, fill="both")
            self.txt_widget.insert("1.0", str(alert))
            self.txt_widget.config(state="disabled")
            self.detail_win.lift(); self.detail_win.focus_force()
    #2
    def check_and_record(self, stock_code, price, change, volume, name=None):
        with self._lock:
            code = str(stock_code)
            rules = self.rules.get(code)
            if not rules:
                return False

            # 更新该股票阈值
            self.update_stock_threshold(code, window=50)

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

                key = (code, field, rule.get("op", ">="), float(rule.get("value", 0)))
                if not self._cooldown_ok(key):
                    continue

                if self._rule_triggered(rule, val):
                    self._update_last_trigger(key)
                    triggered_any = True
                    signal_level = self.classify_signal(code, field, val)

                    alert = {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "stock_code": code,
                        "name": name,
                        "field": field,
                        "op": rule.get("op", ">="),
                        "rule_value": rule.get("value"),
                        "value": val,
                        "delta": round(abs(val - rule.get("value",0)),4),
                        "level": signal_level
                    }

                    self.history.append(alert)
                    self.buffer.append(alert)

                    if signal_level == "strong":
                        self._popup_alert(alert)  # 弹窗
                    self._ui_notify()

            if triggered_any:
                self.save_history()
            return triggered_any

    # def _popup_secondary_signal(self, alert):
    #     """显示次强信号在列表窗口"""
    #     import tkinter as tk
    #     from tkinter import ttk

    #     try:
    #         root = tk._default_root
    #         if not root:
    #             return

    #         if self.secondary_win and self.secondary_win.winfo_exists():
    #             # 已存在窗口，直接刷新内容
    #             tree = self.secondary_tree
    #         else:
    #             # 创建新窗口
    #             self.secondary_win = tk.Toplevel(root)
    #             self.secondary_win.title("次强信号列表")
    #             self.secondary_win.geometry("600x300")
    #             self.secondary_win.bind("<Escape>", lambda e: self.secondary_win.destroy())

    #             # Treeview
    #             cols = ("time", "code", "name", "field", "rule", "value", "delta")
    #             tree = ttk.Treeview(self.secondary_win, columns=cols, show="headings")
    #             for c in cols:
    #                 tree.heading(c, text=c)
    #                 tree.column(c, width=80, anchor="center")
    #             tree.pack(expand=True, fill="both", padx=4, pady=4)
    #             self.secondary_tree = tree

    #         # 插入新信号到顶部
    #         rule_repr = f"{alert.get('field')} {alert.get('op')}{alert.get('rule_value')}"
    #         vals = (alert.get("time"), alert.get("stock_code"), alert.get("name"),
    #                 alert.get("field"), rule_repr, alert.get("value"), alert.get("delta"))
    #         self.secondary_tree.insert("", 0, values=vals)
    #         self.secondary_win.lift()
    #         self.secondary_win.focus_force()
    #     except Exception:
    #         pass

    def _popup_secondary_signal(self, alert):
        import tkinter as tk
        from tkinter import ttk

        try:
            root = tk._default_root
            if not root:
                return

            if self.secondary_win and self.secondary_win.winfo_exists():
                tree = self.secondary_tree
            else:
                self.secondary_win = tk.Toplevel(root)
                self.secondary_win.title("次强信号列表")
                self.secondary_win.geometry("700x350")
                self.secondary_win.bind("<Escape>", lambda e: self.secondary_win.destroy())

                # Filter
                filter_frame = tk.Frame(self.secondary_win)
                filter_frame.pack(fill="x")
                tk.Label(filter_frame, text="筛选:").pack(side="left")
                self.secondary_filter_var = tk.StringVar()
                filter_entry = tk.Entry(filter_frame, textvariable=self.secondary_filter_var)
                filter_entry.pack(side="left", fill="x", expand=True)
                filter_entry.bind("<KeyRelease>", lambda e: self._filter_secondary_tree())

                # Treeview
                cols = ("time", "code", "name", "field", "rule", "value", "delta")
                tree = ttk.Treeview(self.secondary_win, columns=cols, show="headings")
                for c in cols:
                    tree.heading(c, text=c, command=lambda _c=c: self._sort_secondary_tree(_c))
                    tree.column(c, width=90, anchor="center")
                tree.pack(expand=True, fill="both", padx=4, pady=4)
                self.secondary_tree = tree

            # 插入新信号到顶部
            rule_repr = f"{alert.get('field')} {alert.get('op')}{alert.get('rule_value')}"
            vals = (alert.get("time"), alert.get("stock_code"), alert.get("name"),
                    alert.get("field"), rule_repr, alert.get("value"), alert.get("delta"))
            tree.insert("", 0, values=vals)

            self.secondary_win.lift()
            self.secondary_win.focus_force()
            self._filter_secondary_tree()  # 更新过滤
        except Exception:
            pass

    def _filter_secondary_tree(self):
        if not self.secondary_tree or not self.secondary_filter_var:
            return
        keyword = self.secondary_filter_var.get().lower()
        for iid in self.secondary_tree.get_children():
            vals = self.secondary_tree.item(iid, "values")
            # 显示包含关键词的行
            show = any(keyword in str(v).lower() for v in vals)
            self.secondary_tree.item(iid, tags=("show",) if show else ("hide",))
        self.secondary_tree.tag_configure("hide", foreground="#999")
        self.secondary_tree.tag_configure("show", foreground="#000")

    def _sort_secondary_tree(self, col):
        tree = self.secondary_tree
        data = [(tree.set(k, col), k) for k in tree.get_children('')]
        try:
            data.sort(key=lambda t: float(t[0]), reverse=False)
        except ValueError:
            data.sort(key=lambda t: t[0], reverse=False)
        for index, (val, k) in enumerate(data):
            tree.move(k, '', index)

    def _popup_alert(self, alert):
            """单例弹窗显示极强信号"""
        try:
            import tkinter as tk
            root = tk._default_root
            if not root:
                return

            content = (f"{alert['stock_code']} {alert['name']} - 强信号\n"
                       f"{alert['field']} {alert['op']}{alert['rule_value']}\n"
                       f"现值: {alert['value']} 变化量: {alert['delta']}")

            if self.detail_win and self.detail_win.winfo_exists():
                # 已存在窗口，更新内容
                self.detail_txt.config(state="normal")
                self.detail_txt.delete("1.0", tk.END)
                self.detail_txt.insert("1.0", content)
                self.detail_txt.config(state="disabled")
                self.detail_win.focus_force()
                self.detail_win.lift()
            else:
                # 创建新窗口
                self.detail_win = tk.Toplevel(root)
                self.detail_win.title(f"{alert['stock_code']} {alert['name']} - 强信号")
                win_width, win_height = 380, 120
                # 屏幕居中
                screen_width = self.detail_win.winfo_screenwidth()
                screen_height = self.detail_win.winfo_screenheight()
                x = (screen_width - win_width) // 2
                y = (screen_height - win_height) // 2
                self.detail_win.geometry(f"{win_width}x{win_height}+{x}+{y}")

                # 文本
                import tkinter.font as tkfont
                font_style = tkfont.Font(family="微软雅黑", size=12)
                self.detail_txt = tk.Text(self.detail_win, wrap="word", font=font_style)
                self.detail_txt.pack(expand=True, fill="both", padx=8, pady=8)
                self.detail_txt.insert("1.0", content)
                self.detail_txt.config(state="disabled")

                # ESC 关闭
                self.detail_win.bind("<Escape>", lambda e: self.detail_win.destroy())
                self.detail_win.focus_force()
                self.detail_win.lift()
        except Exception:
            pass

    # def _popup_alert(self, alert):
    #     """仅在极强信号时弹窗"""
    #     try:
    #         import tkinter as tk
    #         root = tk._default_root
    #         if not root:
    #             return
    #         win = tk.Toplevel(root)
    #         win.title(f"{alert['stock_code']} {alert['name']} - 强信号")
    #         win.geometry("380x120")
    #         tk.Label(win, text=f"{alert['field']} {alert['op']}{alert['rule_value']} 现值: {alert['value']}\n变化量: {alert['delta']}",
    #                  font=("微软雅黑", 12), justify="left").pack(expand=True, fill="both", padx=8, pady=8)
    #         win.focus_force()
    #         win.lift()
    #         win.bind("<Escape>", lambda e: win.destroy())
    #     except Exception:
            pass

    # def check_and_record(self, stock_code, price, change, volume, name=None):
    #     # 先更新自适应阈值
    #     self.update_dynamic_threshold(window=50)
    #     with self._lock:
    #         code = str(stock_code)
    #         rules = self.rules.get(code)
    #         if not rules: return False
    #         name = name or code
    #         field_map = {"价格":price,"涨幅":change,"量":volume}
    #         triggered_any = False
    #         for rule in rules:
    #             if not rule.get("enabled",True): continue
    #             field = rule.get("field")
    #             if field not in field_map: continue
    #             val = field_map[field]; key = (code,field,rule.get("op",">="),float(rule.get("value",0)))
    #             if not self._cooldown_ok(key): continue
    #             if self._rule_triggered(rule,val):
    #                 self._update_last_trigger(key)
    #                 triggered_any = True
    #                 alert = {
    #                     "time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    #                     "stock_code":code,
    #                     "name":name,
    #                     "field":field,
    #                     "op":rule.get("op",">="),
    #                     "rule_value":rule.get("value"),
    #                     "value":val,
    #                     "delta":round(abs(val - rule.get("value",0)),4)
    #                 }
    #                 alert["level"]=self.classify_signal(alert)
    #                 if alert["level"]=="极强": self.show_alert_popup(alert)
    #                 self.history.append(alert)
    #                 self.buffer.append(alert)
    #                 if len(self.history)>MAX_HISTORY_KEEP: self.history=self.history[-MAX_HISTORY_KEEP:]
    #                 self._ui_notify()
    #         if triggered_any: self.save_history()
    #         return triggered_any

    def get_history(self, limit=500): return list(self.history[-limit:])[::-1]
    def pop_buffer(self):
        with self._lock: buf=list(self.buffer); self.buffer=[]; return buf
    def open_center(self,parent=None):
        if parent is None: parent = tk._default_root
        if parent is None: raise RuntimeError("No tk root available")
        return AlertCenter(parent,self)

     # ---------- 自适应阈值 ----------
    def update_dynamic_threshold(self, window=50):
        """
        根据最近 window 条历史记录计算市场活跃度，动态调整涨幅/量阈值
        """
        if not self.history:
            return
        # 取最近 window 条历史
        recent = self.history[-window:]
        # 计算涨幅波动（percent）和成交量变化
        percent_list = [h.get("value",0) for h in recent if h.get("field")=="涨幅"]
        volume_list = [h.get("value",0) for h in recent if h.get("field")=="量"]

        # 平均波动
        avg_percent = max(0.5, sum(percent_list)/len(percent_list)) if percent_list else 1.0
        avg_volume = max(1, sum(volume_list)/len(volume_list)) if volume_list else 1.0

        # 简单自适应：阈值 = 平均波动 * 放大系数
        self.dynamic_threshold["涨幅"] = round(avg_percent * 1.5, 4)  # 可调比例
        self.dynamic_threshold["量"] = round(avg_volume * 1.5, 0)
# --------------------------
# AlertCenter UI（History + Rules 编辑）
# --------------------------
class AlertCenter(tk.Toplevel):
    def __init__(self,parent,manager:AlertManager):
        super().__init__(parent)
        self.manager=manager; self.title("报警中心"); self.geometry("780x420")
        self.protocol("WM_DELETE_WINDOW", self.on_close); self.transient(parent); self.grab_set()
        self.manager.register_ui(self,self.refresh_history)
        self.nb=ttk.Notebook(self); self.nb.pack(fill="both",expand=True,padx=6,pady=6)
        self.frame_hist=ttk.Frame(self.nb); self.nb.add(self.frame_hist,text="报警历史"); self._build_history_tab(self.frame_hist)
        self.frame_rules=ttk.Frame(self.nb); self.nb.add(self.frame_rules,text="规则管理"); self._build_rules_tab(self.frame_rules)
        self.refresh_history(); self.refresh_rules_list()

    def _build_history_tab(self,parent):
        cols=("time","stock_code","name","field","rule","value","delta","level")
        headings=("时间","代码","名称","字段","规则","现值","变化量","等级")
        frm=ttk.Frame(parent); frm.pack(fill="both",expand=True)
        self.tree_hist=ttk.Treeview(frm,columns=cols,show="headings")
        for c,h in zip(cols,headings): self.tree_hist.heading(c,text=h); self.tree_hist.column(c,width=100,anchor="center")
        self.tree_hist.column("name",width=140); self.tree_hist.pack(side="left",fill="both",expand=True)
        vsb=ttk.Scrollbar(frm,orient="vertical",command=self.tree_hist.yview); self.tree_hist.configure(yscroll=vsb.set); vsb.pack(side="right",fill="y")
        self.tree_hist.tag_configure("极强", background="yellow")
        self.tree_hist.tag_configure("次强", background="white")
        self.tree_hist.tag_configure("弱", background="gray90")
        btn_frame=ttk.Frame(parent); btn_frame.pack(fill="x")
        ttk.Button(btn_frame,text="清空历史",command=self.clear_history).pack(side="left",padx=4,pady=6)
        ttk.Button(btn_frame,text="刷新",command=self.refresh_history).pack(side="left",padx=4)

    def refresh_history(self):
        hist=self.manager.get_history(limit=1000)
        self.tree_hist.delete(*self.tree_hist.get_children())
        for a in hist:
            rule_repr=f"{a.get('field')} {a.get('op')}{a.get('rule_value')}"
            vals=(a.get("time"),a.get("stock_code"),a.get("name"),a.get("field"),rule_repr,a.get("value"),a.get("delta"),a.get("level",""))
            self.tree_hist.insert("", "end", values=vals, tags=(a.get("level",""),))

    def clear_history(self):
        if messagebox.askyesno("确认","确定要清空报警历史吗？"):
            self.manager.history=[]; self.manager.save_history(); self.refresh_history()

    # ---- Rules Tab 同你现有保持不变 ----
    def _build_rules_tab(self,parent):
        top=ttk.Frame(parent); top.pack(fill="x", padx=4,pady=4)
        ttk.Label(top,text="股票:").pack(side="left")
        self.stock_var=tk.StringVar()
        self.stock_combo=ttk.Combobox(top,textvariable=self.stock_var,values=[],width=20); self.stock_combo.pack(side="left",padx=6)
        self.stock_combo.bind("<<ComboboxSelected>>", lambda e:self.refresh_rules_list())
        ttk.Button(top,text="编辑规则",command=self.open_editor_for_selected).pack(side="left",padx=6)
        ttk.Button(top,text="删除规则",command=self.delete_selected_rules).pack(side="left",padx=6)
        ttk.Button(top,text="刷新",command=self.refresh_rules_list).pack(side="left",padx=6)
        ttk.Button(top,text="保存",command=self.manager.save_rules).pack(side="right",padx=6)
        cols=("idx","field","op","value","enabled","delta"); self.tree_rules=ttk.Treeview(parent,columns=cols,show="headings",height=10)
        for c in cols: self.tree_rules.heading(c,text=c)
        self.tree_rules.column("idx",width=40,anchor="center"); self.tree_rules.pack(fill="both",expand=True,padx=4,pady=4)

    def refresh_rules_list(self):
        keys=sorted(list(self.manager.rules.keys())); self.stock_combo['values']=keys
        cur=self.stock_var.get() or (keys[0] if keys else ""); self.stock_var.set(cur)
        self.tree_rules.delete(*self.tree_rules.get_children())
        if not cur: return
        rules=self.manager.get_rules(cur)
        for i,r in enumerate(rules):
            enabled="是" if r.get("enabled",True) else "否"
            self.tree_rules.insert("", "end", values=(i+1,r.get("field"),r.get("op"),r.get("value"),enabled,r.get("delta","")))

    def open_editor_for_selected(self):
        code=self.stock_var.get().strip()
        if not code: messagebox.showinfo("提示","请先选择一个股票代码"); return
        EditRuleDialog(self,self.manager,code,on_saved=self.refresh_rules_list)
    def delete_selected_rules(self):
        code=self.stock_var.get().strip(); 
        if not code: return
        if messagebox.askyesno("确认",f"确定删除 {code} 的所有规则吗？"):
            self.manager.delete_rules(code); self.refresh_rules_list()
    def on_close(self): self.manager.save_all(); self.destroy()
