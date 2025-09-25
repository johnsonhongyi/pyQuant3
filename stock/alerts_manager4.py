# -*- coding: utf-8 -*-
import os, json, threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import tkinter.font as tkfont

# --------------------------
# 配置
# --------------------------
DEFAULT_RULES_FILE = "alerts_rules.json"
DEFAULT_HISTORY_FILE = "alerts_history.json"
ALERT_COOLDOWN_SECONDS = 60
MAX_HISTORY_KEEP = 2000

# 全局管理器
_GLOBAL_ALERT_MANAGER = None
def set_global_manager(mgr):
    global _GLOBAL_ALERT_MANAGER
    _GLOBAL_ALERT_MANAGER = mgr
def check_alert(stock_code, price, change, volume, name=None):
    if _GLOBAL_ALERT_MANAGER is None:
        return
    return _GLOBAL_ALERT_MANAGER.check_and_record(stock_code, price, change, volume, name=name)
def open_alert_center(parent=None):
    if _GLOBAL_ALERT_MANAGER is None:
        return None
    return _GLOBAL_ALERT_MANAGER.open_center(parent=parent)

# --------------------------
# AlertManager
# --------------------------
class AlertManager:
    def __init__(self, storage_dir=".", rules_file=None, history_file=None, logger=None):
        self.logger = logger
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.rules_file = os.path.join(self.storage_dir, rules_file or DEFAULT_RULES_FILE)
        self.history_file = os.path.join(self.storage_dir, history_file or DEFAULT_HISTORY_FILE)
        self.rules = {}
        self.history = []
        self.buffer = []
        self.last_trigger = {}
        self._fields = ["价格","涨幅","量"]  # 默认字段
        self._ui_root = None
        self._ui_refresh_cb = None
        self._lock = threading.RLock()
        self.load_all()

    # ---------- I/O ----------
    def load_all(self):
        try:
            if os.path.exists(self.rules_file):
                with open(self.rules_file,"r",encoding="utf-8") as f:
                    self.rules = json.load(f)
        except:
            self.rules={}
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file,"r",encoding="utf-8") as f:
                    self.history = json.load(f)
        except:
            self.history=[]
    def save_rules(self):
        try:
            with open(self.rules_file,"w",encoding="utf-8") as f:
                json.dump(self.rules,f,ensure_ascii=False,indent=2)
        except:
            pass
    def save_history(self):
        try:
            hist = self.history[-MAX_HISTORY_KEEP:]
            with open(self.history_file,"w",encoding="utf-8") as f:
                json.dump(hist,f,ensure_ascii=False,indent=2)
        except:
            pass
    def save_all(self):
        with self._lock:
            self.save_rules()
            self.save_history()

    # ---------- 字段 ----------
    def set_field_list(self, fields):
        self._fields = list(fields)
    def get_field_list(self):
        return getattr(self, "_fields", ["价格","涨幅","量"])

    # ---------- 规则 ----------
    def get_rules(self, code):
        return self.rules.get(str(code),[])
    def set_rules(self, code, rules_list):
        self.rules[str(code)] = rules_list
        self.save_rules()
    def add_rule(self, code, rule):
        lst = self.rules.get(str(code),[])
        lst.append(rule)
        self.rules[str(code)] = lst
        self.save_rules()
    def delete_rules(self, code):
        code = str(code)
        if code in self.rules:
            del self.rules[code]
            self.save_rules()

    # ---------- UI ----------
    def register_ui(self, root, refresh_callback):
        self._ui_root=root
        self._ui_refresh_cb=refresh_callback
    def _ui_notify(self):
        if self._ui_root and self._ui_refresh_cb:
            try:
                self._ui_root.after(0,self._ui_refresh_cb)
            except: pass

    # ---------- 检测 ----------
    def _rule_triggered(self, rule,val):
        op=rule.get("op",">=")
        try:
            rule_val=float(rule.get("value",0))
            cur_val=float(val)
        except:
            return False
        if op==">=":
            return cur_val>=rule_val
        elif op=="<=":
            return cur_val<=rule_val
        return False
    def _cooldown_ok(self,key):
        last = self.last_trigger.get(key)
        if last is None: return True
        return (datetime.now()-last).total_seconds()>=ALERT_COOLDOWN_SECONDS
    def _update_last_trigger(self,key):
        self.last_trigger[key]=datetime.now()

    def check_and_record(self, stock_code, price, change, volume, name=None):
        # field_map = {
        #     "open": price_open,
        #     "close": price_close,
        #     "high": price_high,
        #     "low": price_low,
        #     "volume": vol,
        #     "percent": change_percent,
        # }

        # # 如果 field_list 存在，只检测列表里的字段
        # if hasattr(self, "field_list"):
        #     field_map = {k: v for k, v in field_map.items() if k in self.field_list}

        with self._lock:
            code=str(stock_code)
            rules=self.rules.get(code)
            if not rules: return False
            name=name or code
            field_map={"价格":price,"涨幅":change,"量":volume}
            triggered_any=False
            for rule in rules:
                if not rule.get("enabled",True): continue
                field=rule.get("field")
                if field not in field_map: continue
                val=field_map[field]
                if val is None: continue
                key=(code,field,rule.get("op",">="),float(rule.get("value",0)))
                if not self._cooldown_ok(key): continue
                if self._rule_triggered(rule,val):
                    self._update_last_trigger(key)
                    triggered_any=True
                    alert={"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "stock_code":code,"name":name,"field":field,
                           "op":rule.get("op",">="),"rule_value":rule.get("value"),
                           "value":val,"delta":round(abs(val-rule.get("value",0)),4)}
                    self.history.append(alert)
                    self.buffer.append(alert)
                    if len(self.history)>MAX_HISTORY_KEEP:
                        self.history=self.history[-MAX_HISTORY_KEEP:]
                    self._ui_notify()
            if triggered_any: self.save_history()
            return triggered_any
    def get_history(self,limit=500):
        return list(self.history[-limit:])[::-1]
    def pop_buffer(self):
        with self._lock:
            buf=list(self.buffer)
            self.buffer=[]
        return buf

    # ---------- UI 打开 ----------
    def open_center(self,parent=None):
        if parent is None:
            parent=tk._default_root
        if parent is None: raise RuntimeError("No tk root")
        return AlertCenter(parent,self)

# --------------------------
# AlertCenter UI
# --------------------------
class AlertCenter(tk.Toplevel):
    def __init__(self,parent,manager:AlertManager):
        super().__init__(parent)
        self.manager=manager
        self.title("报警中心")
        self.geometry("780x420")
        self.protocol("WM_DELETE_WINDOW",self.on_close)
        self.transient(parent)
        self.grab_set()
        self.manager.register_ui(self,self.refresh_history)

        self.nb=ttk.Notebook(self)
        self.nb.pack(fill="both",expand=True,padx=6,pady=6)
        # History
        self.frame_hist=ttk.Frame(self.nb)
        self.nb.add(self.frame_hist,text="报警历史")
        self._build_history_tab(self.frame_hist)
        # Rules
        self.frame_rules=ttk.Frame(self.nb)
        self.nb.add(self.frame_rules,text="规则管理")
        self._build_rules_tab(self.frame_rules)

        self.refresh_history()
        self.refresh_rules_list()

    def _build_history_tab(self,parent):
        cols=("time","stock_code","name","field","rule","value","delta")
        headings=("时间","代码","名称","字段","规则","现值","变化量")
        frm=ttk.Frame(parent); frm.pack(fill="both",expand=True)
        self.tree_hist=ttk.Treeview(frm,columns=cols,show="headings")
        for c,h in zip(cols,headings):
            self.tree_hist.heading(c,text=h)
            self.tree_hist.column(c,width=100,anchor="center")
        self.tree_hist.column("name",width=140)
        self.tree_hist.pack(side="left",fill="both",expand=True)
        vsb=ttk.Scrollbar(frm,orient="vertical",command=self.tree_hist.yview)
        self.tree_hist.configure(yscroll=vsb.set)
        vsb.pack(side="right",fill="y")
        btn_frame=ttk.Frame(parent); btn_frame.pack(fill="x")
        ttk.Button(btn_frame,text="清空历史",command=self.clear_history).pack(side="left",padx=4,pady=6)
        ttk.Button(btn_frame,text="刷新",command=self.refresh_history).pack(side="left",padx=4)
    def refresh_history(self):
        hist=self.manager.get_history(limit=1000)
        self.tree_hist.delete(*self.tree_hist.get_children())
        for a in hist:
            rule_repr=f"{a.get('field')} {a.get('op')}{a.get('rule_value')}"
            vals=(a.get("time"),a.get("stock_code"),a.get("name"),a.get("field"),rule_repr,a.get("value"),a.get("delta"))
            self.tree_hist.insert("", "end", values=vals)
    def clear_history(self):
        if messagebox.askyesno("确认","确定要清空报警历史吗？"):
            self.manager.history=[]
            self.manager.save_history()
            self.refresh_history()

    def _build_rules_tab(self,parent):
        top=ttk.Frame(parent); top.pack(fill="x",padx=4,pady=4)
        ttk.Label(top,text="股票:").pack(side="left")
        self.stock_var=tk.StringVar()
        self.stock_combo=ttk.Combobox(top,textvariable=self.stock_var,values=[],width=20)
        self.stock_combo.pack(side="left",padx=6)
        self.stock_combo.bind("<<ComboboxSelected>>",lambda e:self.refresh_rules_list())
        ttk.Button(top,text="编辑规则",command=self.open_editor_for_selected).pack(side="left",padx=6)
        ttk.Button(top,text="删除规则",command=self.delete_selected_rules).pack(side="left",padx=6)
        ttk.Button(top,text="刷新",command=self.refresh_rules_list).pack(side="left",padx=6)
        ttk.Button(top,text="保存",command=self.manager.save_rules).pack(side="right",padx=6)

        cols=("idx","field","op","value","enabled","delta")
        self.tree_rules=ttk.Treeview(parent,columns=cols,show="headings",height=10)
        for c,h in zip(cols,("#","字段","操作","值","启用","delta")):
            self.tree_rules.heading(c,text=h)
        self.tree_rules.column("idx",width=40,anchor="center")
        self.tree_rules.pack(fill="both",expand=True,padx=4,pady=4)

    def refresh_rules_list(self):
        keys=sorted(list(self.manager.rules.keys()))
        self.stock_combo['values']=keys
        cur=self.stock_var.get() or (keys[0] if keys else "")
        if cur not in keys and keys: cur=keys[0]
        self.stock_var.set(cur)
        self.tree_rules.delete(*self.tree_rules.get_children())
        if not cur: return
        rules=self.manager.get_rules(cur)
        for i,r in enumerate(rules):
            enabled="是" if r.get("enabled",True) else "否"
            self.tree_rules.insert("", "end", values=(i+1,r.get("field"),r.get("op"),r.get("value"),enabled,r.get("delta","")))
    def open_editor_for_selected(self):
        code=self.stock_var.get().strip()
        if not code:
            messagebox.showinfo("提示","请先选择一个股票代码")
            return
        EditRuleDialog(self,self.manager,code,on_saved=self.refresh_rules_list)
    def delete_selected_rules(self):
        code=self.stock_var.get().strip()
        if not code: return
        if messagebox.askyesno("确认",f"确定删除 {code} 的所有规则吗？"):
            self.manager.delete_rules(code)
            self.refresh_rules_list()
    def on_close(self):
        self.manager.save_all()
        self.destroy()

# --------------------------
# 编辑规则对话框
# --------------------------
class EditRuleDialog(tk.Toplevel):
    def __init__(self,parent,manager,code,on_saved=None):
        super().__init__(parent)
        self.manager=manager
        self.code=str(code)
        self.on_saved=on_saved
        self.title(f"编辑规则 - {self.code}")
        self.geometry("520x320")
        self.transient(parent)
        self.grab_set()
        self.rules=list(self.manager.get_rules(self.code))
        self._build_ui()
        self.refresh_list()
    def _build_ui(self):
        frm=ttk.Frame(self); frm.pack(fill="both",expand=True,padx=8,pady=8)
        top=ttk.Frame(frm); top.pack(fill="x")
        ttk.Label(top,text=f"股票: {self.code}").pack(side="left")
        ttk.Button(top,text="新增规则",command=self.add_new_rule).pack(side="right")
        cols=("field","op","value","enabled","delta")
        self.tree=ttk.Treeview(frm,columns=cols,show="headings",height=8)
        for c in cols: self.tree.heading(c,text=c)
        self.tree.pack(fill="both",expand=True,pady=6)
        btns=ttk.Frame(frm); btns.pack(fill="x")
        ttk.Button(btns,text="编辑选中",command=self.edit_selected).pack(side="left",padx=4)
        ttk.Button(btns,text="删除选中",command=self.delete_selected).pack(side="left",padx=4)
        ttk.Button(btns,text="保存并关闭",command=self.save_and_close).pack(side="right",padx=6)
        ttk.Button(btns,text="取消",command=self.cancel).pack(side="right",padx=6)
    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.rules:
            self.tree.insert("", "end", values=(r.get("field"),r.get("op"),r.get("value"),"是" if r.get("enabled",True) else "否",r.get("delta","")))
    def add_new_rule(self):
        default={"field":"价格","op":">=","value":1.0,"enabled":True,"delta":0.1}
        self.rules.append(default)
        self.edit_rule(len(self.rules)-1)
    def edit_selected(self):
        sel=self.tree.selection()
        if not sel: return
        idx=self.tree.index(sel[0])
        self.edit_rule(idx)
    def edit_rule(self,idx):
        r=self.rules[idx]
        d=EditSingleRuleDialog(self,r)
        self.wait_window(d)
        if d.result is not None:
            self.rules[idx]=d.result
            self.refresh_list()
    def delete_selected(self):
        sel=self.tree.selection()
        if not sel: return
        idx=self.tree.index(sel[0])
        del self.rules[idx]
        self.refresh_list()
    def save_and_close(self):
        self.manager.set_rules(self.code,self.rules)
        if self.on_saved:
            try: self.on_saved()
            except: pass
        self.destroy()
    def cancel(self):
        self.destroy()

class EditSingleRuleDialog(simpledialog.Dialog):
    def __init__(self,parent,rule):
        self.rule=dict(rule)
        super().__init__(parent,title="编辑规则")
    def body(self,master):
        ttk.Label(master,text="字段:").grid(row=0,column=0,sticky="w")
        field_list=self.parent.manager.get_field_list()
        self.field_var=tk.StringVar(value=self.rule.get("field",field_list[0] if field_list else "价格"))
        ttk.Combobox(master,textvariable=self.field_var,values=field_list,width=15).grid(row=0,column=1)
        ttk.Label(master,text="操作:").grid(row=1,column=0,sticky="w")
        self.op_var=tk.StringVar(value=self.rule.get("op",">="))
        ttk.Combobox(master,textvariable=self.op_var,values=[">=", "<="],width=6).grid(row=1,column=1)
        ttk.Label(master,text="值:").grid(row=2,column=0,sticky="w")
        self.value_var=tk.DoubleVar(value=float(self.rule.get("value",0) or 0))
        ttk.Entry(master,textvariable=self.value_var).grid(row=2,column=1)
        ttk.Label(master,text="启用:").grid(row=3,column=0,sticky="w")
        self.en_var=tk.BooleanVar(value=self.rule.get("enabled",True))
        ttk.Checkbutton(master,variable=self.en_var).grid(row=3,column=1)
        ttk.Label(master,text="delta:").grid(row=4,column=0,sticky="w")
        self.delta_var=tk.DoubleVar(value=float(self.rule.get("delta",0) or 0))
        ttk.Entry(master,textvariable=self.delta_var).grid(row=4,column=1)
        return None
    def apply(self):
        self.result={"field":self.field_var.get(),
                     "op":self.op_var.get(),
                     "value":float(self.value_var.get()),
                     "enabled":bool(self.en_var.get()),
                     "delta":float(self.delta_var.get())}

if __name__ == '__main__':
    import tkinter as tk
    from alerts_manager4 import AlertManager, set_global_manager, open_alert_center

    root = tk.Tk()      # 必须先创建 root
    root.withdraw()      # 如果不想显示主窗口
    # 创建 manager
    alert_mgr = AlertManager(storage_dir="./alert_data")
    # 新增字段列表属性
    # alert_mgr.field_list = ['open','close','high','low','volume','percent']

    set_global_manager(alert_mgr)

    # 设置字段（来自实时数据或日线 DataFrame）
    # 比如 df.columns = ['open','close','high','low','volume','percent']
    # alert_mgr.set_field_list(['open','close','high','low','volume','percent'])

    # 检测单个数据
    alert_mgr.check_and_record(stock_code='000001', price=10.5, change=2.3, volume=10000, name='平安银行')

    # 弹出中心
    open_alert_center()
