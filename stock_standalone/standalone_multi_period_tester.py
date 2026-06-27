import sys
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import threading
import json
import os
import time

from multi_period_strategy_engine import MultiPeriodStrategyEngine
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct

class StandaloneMultiPeriodTester(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("多周期联动策略筛选器 - 独立验证版")
        self.geometry("1100x700")
        
        self.engine = MultiPeriodStrategyEngine()
        self.strategies = self.engine.load_strategies()
        self.top_now = None
        
        self.config_file = "config/standalone_tester_config.json"
        self.ui_state = self._load_state()
        
        self._last_selected_code = None
        self._link_after_id = None
        
        self._init_ui()
        self._apply_state()
        
    def _load_state(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"strategy_id": "", "periods": ["d", "w", "m"]}
        
    def _save_state(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        self.ui_state['strategy_id'] = self.strategy_var.get()
        self.ui_state['periods'] = [p for p, var in self.period_vars.items() if var.get()]
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.ui_state, f, ensure_ascii=False, indent=2)

    def _init_ui(self):
        # --- Toolbar ---
        toolbar = tk.Frame(self, bd=1, relief="raised")
        toolbar.pack(fill="x", padx=5, pady=5)
        
        tk.Label(toolbar, text="策略:").pack(side="left", padx=5)
        self.strategy_var = tk.StringVar()
        self.strategy_combo = ttk.Combobox(toolbar, textvariable=self.strategy_var, state="readonly", width=35)
        self.strategy_combo['values'] = [s['name'] for s in self.strategies]
        self.strategy_combo.pack(side="left", padx=5)
        
        tk.Label(toolbar, text="参与周期:").pack(side="left", padx=5)
        self.period_vars = {}
        for p in self.engine.SUPPORTED_PERIODS:
            var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(toolbar, text=p, variable=var, command=self._save_state)
            chk.pack(side="left")
            self.period_vars[p] = var
            
        tk.Button(toolbar, text="▶ 运行筛选", command=self.run_filter, bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side="left", padx=20)
        
        self.status_var = tk.StringVar(value="准备就绪")
        tk.Label(toolbar, textvariable=self.status_var, fg="blue").pack(side="right", padx=10)
        
        # --- Results Treeview ---
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Define dynamic columns
        columns = ["code", "name", "price", "percent", "volume", "ratio"] + [f"pass_{p}" for p in self.engine.SUPPORTED_PERIODS]
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        
        headers = {"code": "代码", "name": "名称", "price": "现价", "percent": "涨幅%", "volume": "成交量", "ratio": "量比"}
        for p in self.engine.SUPPORTED_PERIODS:
            headers[f"pass_{p}"] = f"{p}通过"
            
        for col in columns:
            self.tree.heading(col, text=headers.get(col, col), command=lambda c=col: self.sort_column(c, True))
            self.tree.column(col, width=70, anchor="center")
            
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        
        # Style
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        
        self.strategy_combo.bind('<<ComboboxSelected>>', lambda e: self._on_strategy_selected())
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)

    def _apply_state(self):
        if self.strategies:
            strat_name = self.strategies[0]['name']
            for s in self.strategies:
                if s['id'] == self.ui_state.get('strategy_id'):
                    strat_name = s['name']
                    break
            self.strategy_var.set(strat_name)
            
        for p in self.ui_state.get('periods', []):
            if p in self.period_vars:
                self.period_vars[p].set(True)
                
    def _on_strategy_selected(self):
        strat_name = self.strategy_var.get()
        for s in self.strategies:
            if s['name'] == strat_name:
                self.ui_state['strategy_id'] = s['id']
                self._save_state()
                break

    def sort_column(self, col, reverse):
        data = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        def safe_float(x):
            try:
                return float(str(x).replace('%', '').strip())
            except ValueError:
                if '✅' in str(x): return 1.0
                if '--' in str(x): return -999.0
                return -999.0

        try:
            # Check if we can sort numerically
            [safe_float(x[0]) for x in data if x[0]]
            data.sort(key=lambda x: safe_float(x[0]), reverse=reverse)
        except Exception:
            data.sort(key=lambda x: str(x[0]), reverse=reverse)
            
        for index, (val, k) in enumerate(data):
            self.tree.move(k, '', index)
            
        self.tree.heading(col, command=lambda c=col: self.sort_column(c, not reverse))

    def _on_tree_select(self, event):
        if self._link_after_id:
            self.after_cancel(self._link_after_id)
        self._link_after_id = self.after(100, self._do_linkage)

    def _do_linkage(self):
        selection = self.tree.selection()
        if not selection:
            return
            
        item = selection[0]
        values = self.tree.item(item, "values")
        if not values:
            return
            
        code = str(values[0]).strip()
        if not code or code == self._last_selected_code:
            return
            
        self._last_selected_code = code
        
        # 1. 尝试 IPC 联动到主程序的 Visualizer (Port 26668)
        ipc_success = False
        try:
            import socket
            IPC_PORT = 26668
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                s.connect(('127.0.0.1', IPC_PORT))
                msg = f"CODE|{code}\n"
                s.sendall(msg.encode('utf-8'))
                ipc_success = True
                self.status_var.set(f"✅ IPC 联动成功: {code}")
        except Exception:
            pass
            
        if not ipc_success:
            # 2. 如果主程序未启动或 IPC 失败，回退到本地 TDX, THS 联动
            try:
                from JohnsonUtil.stock_sender import StockSender
                sender = StockSender()
                sender._do_send(code, {'tdx': True, 'ths': True, 'dfcf': False})
                self.status_var.set(f"⚠️ IPC 未连接，已触发本地联动(TDX/THS): {code}")
            except Exception as e:
                self.status_var.set(f"❌ 联动失败: {e}")

    def run_filter(self):
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        if not active_periods:
            messagebox.showwarning("警告", "请至少选择一个参与周期！")
            return
            
        strat_name = self.strategy_var.get()
        strat_config = next((s for s in self.strategies if s['name'] == strat_name), None)
        if not strat_config:
            return
            
        self.status_var.set("正在获取基础全市场数据...")
        self.update_idletasks()
        
        threading.Thread(target=self._worker, args=(strat_config, active_periods), daemon=True).start()
        
    def _worker(self, strat_config, active_periods):
        try:
            start_time = time.time()
            # If not loaded, or force refresh
            if self.top_now is None:
                self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
                
            for period in active_periods:
                self.status_var.set(f"正在加载 {period} 周期特征数据...")
                self.engine.load_period_data(period, self.top_now)
                
            self.status_var.set("正在执行跨周期交叉验证...")
            result_df = self.engine.evaluate_strategy(strat_config, active_periods)
            
            elapsed = time.time() - start_time
            self.after(0, self._show_results, result_df, elapsed)
        except Exception as e:
            self.after(0, lambda: self.status_var.set(f"错误: {e}"))
            
    def _show_results(self, df, elapsed):
        self._last_selected_code = None
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if df.empty:
            self.status_var.set(f"完成，未找到符合条件的标的。(耗时 {elapsed:.1f}s)")
            return
            
        self.status_var.set(f"完成，共筛选出 {len(df)} 只标的。(耗时 {elapsed:.1f}s)")
        
        for idx, row in df.iterrows():
            code = idx
            name = row.get('name', '--')
            price = round(row.get('close', 0), 2)
            percent = round(row.get('percent', 0), 2)
            vol = round(row.get('volume', 0), 2)
            ratio = round(row.get('ratio', 0), 2)
            
            values = [code, name, price, percent, vol, ratio]
            
            for p in self.engine.SUPPORTED_PERIODS:
                pass_val = row.get(f'pass_{p}', False)
                values.append('✅' if pass_val else '--')
                
            self.tree.insert("", "end", values=values)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = StandaloneMultiPeriodTester()
    app.mainloop()
