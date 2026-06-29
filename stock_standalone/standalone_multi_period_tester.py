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
from tk_gui_modules.treeview_mixin import TreeviewMixin
from sys_utils import get_app_root

# 动态判定继承父类，当作为模块已存在主 Tk 窗口时继承 tk.Toplevel，否则继承 tk.Tk
_parent_class = tk.Toplevel if tk._default_root else tk.Tk

class StandaloneMultiPeriodTester(_parent_class, TreeviewMixin):
    def __init__(self, master=None):
        if _parent_class == tk.Toplevel:
            super().__init__(master)
        else:
            super().__init__()
        self.title("多周期联动策略筛选器")
        self.geometry("1100x700")
        
        self.engine = MultiPeriodStrategyEngine()
        self.strategies = self.engine.load_strategies()
        self.top_now = None
        
        self.config_file = os.path.join(get_app_root(), "config", "standalone_tester_config.json")
        
        self._last_selected_code = None
        self._link_after_id = None
        self.last_result_df = None
        self.last_elapsed = 0.0
        
        # 初始化 TreeviewMixin 的排序状态变量
        self.sort_level1_col = None
        self.sort_level1_asc = True
        self.sort_level2_col = None
        self.sort_level2_asc = True
        self.sort_level3_col = None
        self.sort_level3_asc = True
        self.sortby_col = None
        self.sortby_col_ascend = False
        self.multi_sort_click_count = 0
        
        self._init_ui()
        self.ui_state = self._load_state()
        self._apply_state()
        self._update_tree_columns()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 订阅全局自选股改变通知
        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().subscribe(self._on_favorites_changed)
        except Exception:
            pass
        
    def _load_state(self):
        default_state = {
            "strategy_id": "", 
            "periods": ["d", "w", "m"], 
            "custom_cols": [],
            "manual_col_pool": [],
            "link_vis": True,
            "link_tdx": False,
            "link_ths": False,
            "geometry": "",
            "sort_level1_col": None,
            "sort_level1_asc": True,
            "sort_level2_col": None,
            "sort_level2_asc": True,
            "sort_level3_col": None,
            "sort_level3_asc": True,
            "sortby_col": None,
            "sortby_col_ascend": False
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in default_state.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception:
                pass
        return default_state
        
    def _save_state(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        self.ui_state['strategy_id'] = self.strategy_var.get()
        self.ui_state['periods'] = [p for p, var in self.period_vars.items() if var.get()]
        self.ui_state['custom_cols'] = [c for c, var in self.custom_col_vars.items() if var.get()]
        self.ui_state['manual_col_pool'] = list(self.manual_col_pool)
        self.ui_state['link_vis'] = self.link_vis_var.get()
        self.ui_state['link_tdx'] = self.link_tdx_var.get()
        self.ui_state['link_ths'] = self.link_ths_var.get()
        try:
            self.ui_state['geometry'] = self.geometry()
        except Exception:
            pass
        try:
            self.ui_state['sort_level1_col'] = getattr(self.tree, 'sort_level1_col', None)
            self.ui_state['sort_level1_asc'] = getattr(self.tree, 'sort_level1_asc', True)
            self.ui_state['sort_level2_col'] = getattr(self.tree, 'sort_level2_col', None)
            self.ui_state['sort_level2_asc'] = getattr(self.tree, 'sort_level2_asc', True)
            self.ui_state['sort_level3_col'] = getattr(self.tree, 'sort_level3_col', None)
            self.ui_state['sort_level3_asc'] = getattr(self.tree, 'sort_level3_asc', True)
            self.ui_state['sortby_col'] = getattr(self.tree, 'sortby_col', None)
            self.ui_state['sortby_col_ascend'] = getattr(self.tree, 'sortby_col_ascend', False)
        except Exception:
            pass
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.ui_state, f, ensure_ascii=False, indent=2)

    def _init_ui(self):
        self.status_var = tk.StringVar(value="准备就绪")
        
        # --- Toolbar ---
        toolbar = tk.Frame(self, bd=1, relief="raised")
        toolbar.pack(fill="x", padx=5, pady=5)
        
        tk.Label(toolbar, text="策略:").pack(side="left", padx=5)
        self.strategy_var = tk.StringVar()
        self.strategy_combo = ttk.Combobox(toolbar, textvariable=self.strategy_var, state="readonly", width=25)
        self.strategy_combo['values'] = [s['name'] for s in self.strategies]
        self.strategy_combo.pack(side="left", padx=5)
        
        btn_edit_strat = tk.Button(toolbar, text="⚙", command=self.open_strategy_editor, width=2, bg="#ECEFF1", relief="groove")
        btn_edit_strat.pack(side="left", padx=2)
        
        tk.Label(toolbar, text="参与周期:").pack(side="left", padx=5)
        self.period_vars = {}
        for p in self.engine.SUPPORTED_PERIODS:
            var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(toolbar, text=p, variable=var, command=self._on_period_changed)
            chk.pack(side="left")
            self.period_vars[p] = var
            
        tk.Button(toolbar, text="▶ 运行筛选", command=self.run_filter, bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side="left", padx=20)
            
        self.custom_col_frame = tk.Frame(toolbar)
        self.custom_col_frame.pack(side="left")
        
        self.custom_col_vars = {}
        self.custom_col_widgets = {}
        self.fixed_cols = ["Rank", "dff", "dff2", "dff3"]
        self.manual_col_pool = []
        
        tk.Label(toolbar, text="手动:").pack(side="left", padx=(10, 2))
        self.manual_col_entry = tk.Entry(toolbar, width=8)
        self.manual_col_entry.pack(side="left", padx=2)
        self.manual_col_entry.bind("<Return>", lambda e: self._add_manual_col())
        
        btn_add = tk.Button(toolbar, text="+", width=2, command=self._add_manual_col, bg="#E8F5E9", fg="#2E7D32", relief="groove")
        btn_add.pack(side="left", padx=1)
        btn_remove = tk.Button(toolbar, text="-", width=2, command=self._remove_manual_col, bg="#FFEBEE", fg="#C62828", relief="groove")
        btn_remove.pack(side="left", padx=1)
        
        # --- Bottom Statistics Bar ---
        self.stats_frame = tk.Frame(self, bd=1, relief="sunken", bg="#f0f0f0")
        self.stats_frame.pack(fill="x", padx=5, pady=3, side="bottom")
        
        self.stats_lbl_periods = tk.Label(self.stats_frame, text="【单周期通过率】暂无数据", font=("Microsoft YaHei", 9), bg="#f0f0f0", fg="#333333")
        self.stats_lbl_periods.pack(side="left", padx=10, pady=4)
        
        # 联动控制 Checkboxes
        self.link_frame = tk.Frame(self.stats_frame, bg="#f0f0f0")
        self.link_frame.pack(side="right", padx=10, pady=4)
        
        tk.Label(self.link_frame, text="联动方式:", font=("Microsoft YaHei", 9), bg="#f0f0f0", fg="#333333").pack(side="left")
        self.link_vis_var = tk.BooleanVar(value=True)
        self.link_tdx_var = tk.BooleanVar(value=False)
        self.link_ths_var = tk.BooleanVar(value=False)
        
        chk_vis = tk.Checkbutton(self.link_frame, text="Vis", variable=self.link_vis_var, bg="#f0f0f0", command=self._on_link_config_changed)
        chk_vis.pack(side="left", padx=2)
        chk_tdx = tk.Checkbutton(self.link_frame, text="Tdx", variable=self.link_tdx_var, bg="#f0f0f0", command=self._on_link_config_changed)
        chk_tdx.pack(side="left", padx=2)
        chk_ths = tk.Checkbutton(self.link_frame, text="Ths", variable=self.link_ths_var, bg="#f0f0f0", command=self._on_link_config_changed)
        chk_ths.pack(side="left", padx=2)

        # 诊断控制 Frame
        diagnose_frame = tk.Frame(self.stats_frame, bg="#f0f0f0")
        diagnose_frame.pack(side="right", padx=10, pady=4)
        
        tk.Label(diagnose_frame, text="诊断个股:", font=("Microsoft YaHei", 9), bg="#f0f0f0", fg="#333333").pack(side="left")
        self.diag_entry = tk.Entry(diagnose_frame, width=8, font=("Microsoft YaHei", 9))
        self.diag_entry.pack(side="left", padx=2)
        self.diag_entry.bind("<Return>", lambda e: self._on_diagnose_click())
        
        btn_diag = tk.Button(diagnose_frame, text="🔍 诊断", command=self._on_diagnose_click, bg="#0288D1", fg="white", font=("Microsoft YaHei", 9), padx=5, pady=1)
        btn_diag.pack(side="left", padx=2)

        self.stats_lbl_final = tk.Label(self.stats_frame, text="【最终筛选结果】暂无数据", font=("Microsoft YaHei", 9, "bold"), bg="#f0f0f0", fg="#2E7D32")
        self.stats_lbl_final.pack(side="right", padx=20, pady=4)
        
        # 运行日志中间状态显示区域
        self.status_lbl = tk.Label(self.stats_frame, textvariable=self.status_var, font=("Microsoft YaHei", 9, "bold"), bg="#f0f0f0", fg="#1A73E8")
        self.status_lbl.pack(side="left", fill="x", expand=True, padx=10, pady=4)
        
        # --- Results Treeview ---
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.tree = ttk.Treeview(tree_frame, show="headings")
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        
        # Style
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        
        self.strategy_combo.bind('<<ComboboxSelected>>', lambda e: self._on_strategy_selected())
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.tag_configure("favorite", foreground="#C62828", font=("Microsoft YaHei", 9, "bold"))

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
                
        # 初始化手动添加的列
        self.manual_col_pool = self.ui_state.get('manual_col_pool', [])
        # 动态创建手动添加列的复选框
        self._recreate_custom_col_checkboxes()
        
        # 勾选复选框
        for c in self.ui_state.get('custom_cols', []):
            if c in self.custom_col_vars:
                self.custom_col_vars[c].set(True)
                
        # 联动复选框应用
        self.link_vis_var.set(self.ui_state.get('link_vis', True))
        self.link_tdx_var.set(self.ui_state.get('link_tdx', False))
        self.link_ths_var.set(self.ui_state.get('link_ths', False))
        
        # 恢复窗口位置和大小
        saved_geom = self.ui_state.get('geometry', '')
        if saved_geom:
            try:
                self.geometry(saved_geom)
            except Exception:
                pass
                
        # 恢复多级排序属性给 App 实例
        try:
            self.sort_level1_col = self.ui_state.get('sort_level1_col', None)
            self.sort_level1_asc = self.ui_state.get('sort_level1_asc', True)
            self.sort_level2_col = self.ui_state.get('sort_level2_col', None)
            self.sort_level2_asc = self.ui_state.get('sort_level2_asc', True)
            self.sort_level3_col = self.ui_state.get('sort_level3_col', None)
            self.sort_level3_asc = self.ui_state.get('sort_level3_asc', True)
            self.sortby_col = self.ui_state.get('sortby_col', None)
            self.sortby_col_ascend = self.ui_state.get('sortby_col_ascend', False)
        except Exception:
            pass

    def _update_tree_columns(self):
        base_cols = ["code", "name", "price", "percent", "volume", "ratio"]
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        active_customs = [c for c, var in self.custom_col_vars.items() if var.get()]
        
        custom_cols = []
        for c in active_customs:
            for p in active_periods:
                custom_cols.append(f"{c}_{p}")
                
        pass_cols = [f"pass_{p}" for p in active_periods]
        
        columns = base_cols + custom_cols + pass_cols
        self.tree["columns"] = columns
        
        headers = {
            "code": "代码", 
            "name": "名称", 
            "price": "现价", 
            "percent": "涨幅%", 
            "volume": "成交量", 
            "ratio": "量比"
        }
        for c in active_customs:
            for p in active_periods:
                headers[f"{c}_{p}"] = f"{c}({p})"
        for p in active_periods:
            headers[f"pass_{p}"] = f"{p}通过"
            
        for col in columns:
            self.tree.heading(col, text=headers.get(col, col))
            self.tree.column(col, width=50, anchor="center")
            
        # 使用 TreeviewMixin 接口更新表头并绑定多级排序 command
        try:
            self._init_tree_sort_state(self.tree)
            self.tree.sort_level1_col = self.sort_level1_col
            self.tree.sort_level1_asc = self.sort_level1_asc
            self.tree.sort_level2_col = self.sort_level2_col
            self.tree.sort_level2_asc = self.sort_level2_asc
            self.tree.sort_level3_col = self.sort_level3_col
            self.tree.sort_level3_asc = self.sort_level3_asc
            self.tree.sortby_col = self.sortby_col
            self.tree.sortby_col_ascend = self.sortby_col_ascend
            self.update_mixin_tree_headers(self.tree)
        except Exception:
            pass

    def _on_custom_col_changed(self):
        self._save_state()
        self._update_tree_columns()
        if self.last_result_df is not None and not self.last_result_df.empty:
            self._show_results(self.last_result_df, self.last_elapsed)

    def _on_period_changed(self):
        self._save_state()
        self._update_tree_columns()
        if self.last_result_df is not None and not self.last_result_df.empty:
            active_periods = [p for p, var in self.period_vars.items() if var.get()]
            if not active_periods:
                for item in self.tree.get_children():
                    self.tree.delete(item)
                return
            strat_name = self.strategy_var.get()
            strat_config = next((s for s in self.strategies if s['name'] == strat_name), None)
            if strat_config:
                try:
                    all_cached = all(p in self.engine._period_dfs and not self.engine._period_dfs[p].empty for p in active_periods)
                    if all_cached:
                        start_time = time.time()
                        result_df = self.engine.evaluate_strategy(strat_config, active_periods)
                        elapsed = time.time() - start_time
                        self.last_result_df = result_df
                        self.last_elapsed = elapsed
                        self._show_results(result_df, elapsed)
                    else:
                        self.run_filter()
                except Exception as e:
                    self.status_var.set(f"计算失败: {e}")

    def _adjust_column_widths(self):
        for col in self.tree["columns"]:
            header_text = self.tree.heading(col, "text")
            
            def get_text_width(text):
                if not text:
                    return 0
                w = 0
                for char in str(text):
                    if '\u4e00' <= char <= '\u9fff':
                        w += 12
                    else:
                        w += 6.5
                return int(w) + 8

            max_w = get_text_width(header_text)
            for item in self.tree.get_children():
                val = self.tree.set(item, col)
                max_w = max(max_w, get_text_width(val))
                
            min_col_w = 32
            if col == "name":
                final_w = max(45, min(max_w, 75))
            else:
                final_w = max(min_col_w, min(max_w, 100))
                
            self.tree.column(col, width=final_w, minwidth=20, stretch=True)
                
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
        
        status_msg_parts = []
        
        # 1. IPC 联动到主程序的 Visualizer (Port 26668)
        if self.link_vis_var.get():
            try:
                import socket
                IPC_PORT = 26668
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.3)
                    s.connect(('127.0.0.1', IPC_PORT))
                    msg = f"CODE|{code}\n"
                    s.sendall(msg.encode('utf-8'))
                    status_msg_parts.append("Vis")
            except Exception:
                status_msg_parts.append("Vis(失败)")
                
        # 2. 本地 TDX, THS 联动
        do_tdx = self.link_tdx_var.get()
        do_ths = self.link_ths_var.get()
        if do_tdx or do_ths:
            try:
                from JohnsonUtil.stock_sender import StockSender
                sender = StockSender()
                sender._do_send(code, {'tdx': do_tdx, 'ths': do_ths, 'dfcf': False})
                if do_tdx: status_msg_parts.append("Tdx")
                if do_ths: status_msg_parts.append("Ths")
            except Exception as e:
                status_msg_parts.append(f"Tdx/Ths(失败: {e})")
                
        if status_msg_parts:
            self.status_var.set(f"✅ 已触发联动: {code} ({', '.join(status_msg_parts)})")

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
            if self.top_now is None:
                self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
                
            for period in active_periods:
                if period in self.engine._period_dfs and not self.engine._period_dfs[period].empty:
                    self.status_var.set(f"⚡ 命中内存缓存，极速加载 {period} 周期...")
                else:
                    self.status_var.set(f"正在加载 {period} 周期特征数据 (首次需读取计算)...")
                self.update_idletasks()
                self.engine.load_period_data(period, self.top_now)
                
            self.status_var.set("正在执行跨周期交叉验证...")
            result_df = self.engine.evaluate_strategy(strat_config, active_periods)
            
            elapsed = time.time() - start_time
            self.last_result_df = result_df
            self.last_elapsed = elapsed
            self.after(0, self._show_results, result_df, elapsed)
        except Exception as e:
            self.after(0, lambda: self.status_var.set(f"错误: {e}"))
            
    def _show_results(self, df, elapsed):
        self._last_selected_code = None
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self._update_stats_ui()
        
        if df.empty:
            self.status_var.set(f"完成，未找到符合条件的标的。(耗时 {elapsed:.1f}s)")
            return
            
        self.status_var.set(f"完成，共筛选出 {len(df)} 只标的。(耗时 {elapsed:.1f}s)")
        
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        active_customs = [c for c, var in self.custom_col_vars.items() if var.get()]
        
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()
            
        # 直接按原 DataFrame 顺序以 iid=code 插入所有行，排序与置顶交由 perform_tree_multi_level_sort 统一处理
        for code, row in df.iterrows():
            name = row.get('name', '--')
            price = round(row.get('close', 0), 2)
            percent = round(row.get('percent', 0), 2)
            vol = round(row.get('volume', 0), 2)
            ratio = round(row.get('ratio', 0), 2)
            
            is_fav = code in fav_stocks
            display_name = f"★ {name}" if is_fav else name
            
            values = [code, display_name, price, percent, vol, ratio]
            
            # 添加自定义列的值
            for c in active_customs:
                for p in active_periods:
                    val = '--'
                    if p in self.engine._period_dfs and code in self.engine._period_dfs[p].index:
                        col_in_df = self.engine._period_dfs[p]
                        if c in col_in_df.columns:
                            raw_val = col_in_df.loc[code, c]
                            if isinstance(raw_val, pd.Series):
                                raw_val = raw_val.iloc[0]
                            if pd.notna(raw_val):
                                if isinstance(raw_val, (int, float)):
                                    val = round(raw_val, 2)
                                else:
                                    val = str(raw_val)
                    values.append(val)
            
            # 添加周期通过列的值
            for p in active_periods:
                pass_val = row.get(f'pass_{p}', False)
                values.append('✅' if pass_val else '--')
                
            row_tags = ("favorite",) if is_fav else ()
            self.tree.insert("", "end", iid=code, values=values, tags=row_tags)
            
        self.perform_tree_multi_level_sort(self.tree)
        self._adjust_column_widths()

    def _update_stats_ui(self):
        stats = getattr(self.engine, "last_stats", None)
        if not stats or not stats.get("periods"):
            self.stats_lbl_periods.config(text="【单周期通过率】暂无数据")
            self.stats_lbl_final.config(text="【最终筛选结果】暂无数据")
            return
            
        period_strs = []
        for period in self.engine.SUPPORTED_PERIODS:
            if period in stats["periods"]:
                pdata = stats["periods"][period]
                total = pdata["total"]
                p_pass = pdata["pass"]
                ratio = pdata["ratio"]
                period_strs.append(f"{period}: {p_pass}/{total}({ratio:.2f}%)")
                
        if period_strs:
            self.stats_lbl_periods.config(text="【单周期通过率】 " + "  |  ".join(period_strs))
        else:
            self.stats_lbl_periods.config(text="【单周期通过率】暂无数据")
            
        final = stats["final"]
        mode_str = "交集" if final["mode"] == "intersection" else "并集"
        self.stats_lbl_final.config(
            text=f"【最终筛选结果 ({mode_str})】 共 {final['pass']} 只 / 市场 {final['total']} 只 ({final['ratio']:.3f}%)"
        )

    def _recreate_custom_col_checkboxes(self):
        for widget in self.custom_col_widgets.values():
            widget.destroy()
        self.custom_col_widgets.clear()
        
        old_vars = self.custom_col_vars.copy()
        self.custom_col_vars.clear()
        
        all_cols = self.fixed_cols + [c for c in self.manual_col_pool if c not in self.fixed_cols]
        for c in all_cols:
            if c in old_vars:
                var = old_vars[c]
            else:
                var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(self.custom_col_frame, text=c, variable=var, command=self._on_custom_col_changed)
            chk.pack(side="left", padx=1)
            self.custom_col_vars[c] = var
            self.custom_col_widgets[c] = chk

    def _add_manual_col(self):
        col_name = self.manual_col_entry.get().strip()
        if not col_name:
            return
        col_name = "".join(x for x in col_name if x.isalnum() or x in ("_", "-"))
        if not col_name:
            return
        if col_name not in self.manual_col_pool and col_name not in self.fixed_cols:
            self.manual_col_pool.append(col_name)
        self._recreate_custom_col_checkboxes()
        if col_name in self.custom_col_vars:
            self.custom_col_vars[col_name].set(True)
        self.manual_col_entry.delete(0, tk.END)
        self._on_custom_col_changed()

    def _remove_manual_col(self):
        col_name = self.manual_col_entry.get().strip()
        if not col_name:
            return
        if col_name in self.manual_col_pool:
            self.manual_col_pool.remove(col_name)
        self._recreate_custom_col_checkboxes()
        self.manual_col_entry.delete(0, tk.END)
        self._on_custom_col_changed()

    def _on_link_config_changed(self):
        self._save_state()

    def on_close(self):
        self._save_state()
        if _parent_class == tk.Toplevel:
            self.withdraw()
        else:
            try:
                from global_favorites import GlobalFavoriteManager
                GlobalFavoriteManager().unsubscribe(self._on_favorites_changed)
            except Exception:
                pass
            self.destroy()

    def _on_favorites_changed(self):
        if hasattr(self, 'winfo_exists') and self.winfo_exists():
            self.after(0, self._refresh_ui_favorites)

    def _refresh_ui_favorites(self):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            return
            
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if not vals or len(vals) < 2:
                continue
            code = str(vals[0]).strip().zfill(6)
            name = str(vals[1]).strip()
            
            is_fav = code in fav_stocks
            clean_name = name
            if name.startswith("★ "):
                clean_name = name[len("★ "):]
            
            new_name = f"★ {clean_name}" if is_fav else clean_name
            
            curr_tags = list(self.tree.item(iid, "tags") or [])
            has_fav_tag = "favorite" in curr_tags
            
            need_update = (name != new_name) or (is_fav != has_fav_tag)
            if need_update:
                new_vals = list(vals)
                new_vals[1] = new_name
                self.tree.item(iid, values=tuple(new_vals))
                
                if is_fav and "favorite" not in curr_tags:
                    curr_tags.append("favorite")
                elif not is_fav and "favorite" in curr_tags:
                    curr_tags.remove("favorite")
                self.tree.item(iid, tags=tuple(curr_tags))
                
        # 刷新置顶和多级排序位置
        try:
            self.perform_tree_multi_level_sort(self.tree)
        except Exception:
            pass

    def get_scaled_value(self) -> float:
        """提供给 TreeviewMixin 使用的高DPI缩放值适配，默认返回 1.0"""
        return 1.0

    def _save_mixin_ui_states(self, tree: ttk.Treeview) -> None:
        """多级排序更改时的回调保存动作，自动执行持久化写盘"""
        self._save_state()

    def show_context_menu(self, event):
        tree = event.widget
        # 1. 优先尝试响应表头的多级排序右键菜单
        try:
            if self.show_header_context_menu(tree, event):
                return
        except Exception:
            pass
            
        # 2. 否则响应行级别的“添加/取消重点关注”菜单
        item_id = tree.identify_row(event.y)
        if not item_id:
            return
        tree.selection_set(item_id)
        tree.focus(item_id)
        
        values = tree.item(item_id, "values")
        if not values or len(values) < 2:
            return
            
        code = str(values[0]).strip().zfill(6)
        name = str(values[1]).strip()
        if name.startswith("★ "):
            name = name[len("★ "):]
            
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            is_fav = code in fav_mgr.get_favorite_stocks()
        except Exception:
            is_fav = False
            
        menu = tk.Menu(self, tearoff=0)
        if not is_fav:
            menu.add_command(label=f"★ 添加重点关注 ({name})", command=lambda: self.add_to_favorites(code))
        else:
            menu.add_command(label=f"☆ 取消重点关注 ({name})", command=lambda: self.remove_from_favorites(code))
        menu.add_separator()
        menu.add_command(label=f"🔬 诊断个股策略通过情况 ({name})", command=lambda: self.diagnose_stock_strategy(code, name))
            
        menu.post(event.x_root, event.y_root)

    def add_to_favorites(self, code):
        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().add_favorite_stock(code)
            self.status_var.set(f"已添加重点关注: {code}")
        except Exception as e:
            messagebox.showerror("错误", f"添加重点关注失败: {e}")

    def remove_from_favorites(self, code):
        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().remove_favorite_stock(code)
            self.status_var.set(f"已取消重点关注: {code}")
        except Exception as e:
            messagebox.showerror("错误", f"取消重点关注失败: {e}")

    def _on_diagnose_click(self):
        code = self.diag_entry.get().strip()
        if not code:
            messagebox.showwarning("警告", "请输入要诊断的股票代码！")
            return
        # 提取并补全6位代码
        code = "".join(x for x in code if x.isdigit()).zfill(6)
        self.diagnose_stock_strategy(code)

    def diagnose_stock_strategy(self, code, name=None):
        import re
        import pandas as pd
        from tkinter import messagebox
        
        code = str(code).strip().zfill(6)
        
        # 1. 尝试获取股票名称
        if not name:
            if self.top_now is not None and code in self.top_now.index:
                name = self.top_now.loc[code, 'name']
            else:
                try:
                    from JSONData import tdx_data_Day as tdd
                    name = tdd.get_name_code(code)
                except Exception:
                    name = "未知股票"
            if not name or name == "未知股票":
                name = "未知股票"
                
        # 2. 提取当前选中的策略与周期
        strat_name = self.strategy_var.get()
        strat_config = next((s for s in self.strategies if s['name'] == strat_name), None)
        if not strat_config:
            messagebox.showwarning("警告", "未选中任何有效策略！", parent=self)
            return
            
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        if not active_periods:
            messagebox.showwarning("警告", "请至少选择一个参与周期！", parent=self)
            return
            
        # 3. 确保涉及周期的数据已经加载好，如果没加载，启动一个 loading 提示并同步载入
        self.status_var.set(f"正在诊断 {code} 的多周期指标...")
        self.update_idletasks()
        
        # 如果 self.top_now 尚未初始化，先获取全市场快照
        if self.top_now is None:
            try:
                from JSONData import tdx_data_Day as tdd
                from JohnsonUtil import johnson_cons as ct
                self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
            except Exception as e:
                messagebox.showerror("错误", f"初始化市场基础数据失败: {e}", parent=self)
                return
                
        # 同步加载未就绪的周期数据
        for period in active_periods:
            if period not in self.engine._period_dfs or self.engine._period_dfs[period].empty:
                self.status_var.set(f"正在加载 {period} 周期特征数据...")
                self.update_idletasks()
                try:
                    self.engine.load_period_data(period, self.top_now)
                except Exception as e:
                    self.status_var.set(f"加载 {period} 周期失败: {e}")
                    
        self.status_var.set("准备就绪")
        
        # 4. 构建平铺多周期特征数据的单行 DataFrame
        merged_row = {"name": name}
        
        # 定义列名后缀转换函数
        def suffix_expr(expr, period_suffix, cols_set):
            def repl(match):
                word = match.group(0)
                if word in cols_set:
                    return f"{word}_{period_suffix}"
                return word
            return re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', repl, expr)
            
        queries = []
        for period in active_periods:
            df_p = self.engine._period_dfs.get(period)
            if df_p is not None and not df_p.empty:
                # 获取该周期的指标列
                valid_cols = set(df_p.columns)
                if code in df_p.index:
                    row_p = df_p.loc[code]
                    if isinstance(row_p, pd.DataFrame):
                        row_p = row_p.iloc[0]
                    # 平铺到 merged_row 中，列名加后缀
                    for k, val in row_p.to_dict().items():
                        if k not in ('code', 'name'):
                            merged_row[f"{k}_{period}"] = val
                
                # 转换过滤条件
                cond = strat_config['conditions'].get(period)
                if cond:
                    raw_filter = cond['filter']
                    suffixed_filter = suffix_expr(raw_filter, period, valid_cols)
                    queries.append({
                        "name": f"{period.upper()}周期条件",
                        "expr": suffixed_filter
                    })
            else:
                # 降级：如果无数据，我们也把条件加进去，它会自动提示缺失字段
                cond = strat_config['conditions'].get(period)
                if cond:
                    queries.append({
                        "name": f"{period.upper()}周期条件",
                        "expr": cond['filter']
                    })
                    
        if not queries:
            messagebox.showwarning("警告", "未生成任何有效的诊断条件！", parent=self)
            return
            
        # 构造 df_flat
        df_flat = pd.DataFrame([merged_row], index=[code])
        df_flat.index.name = 'code'
        
        # 5. 调用系统自带的 check_code 接口
        try:
            from stock_logic_utils import check_code
            check_code(df_flat, code, queries, parent=self)
        except Exception as e:
            messagebox.showerror("错误", f"调起股票检查报告失败: {e}", parent=self)
            
        # 6. 诊断后自动滚动并聚焦到 tree 视图中的对应代码行（如果存在于结果集中则高亮定位，如果不存在则静默处理不抛出警告，与现有 tk 主窗口中的机制对齐）
        try:
            if self.tree.exists(code):
                self.tree.selection_set(code)
                self.tree.focus(code)
                self.tree.see(code)
        except Exception:
            pass

    def open_strategy_editor(self):
        """打开多周期策略编辑器对话框"""
        MultiPeriodStrategyEditor(self, self.engine, self._on_strategies_updated)

    def _on_strategies_updated(self):
        """当策略被保存或重载时的回调动作"""
        self.strategies = self.engine.load_strategies()
        self.strategy_combo['values'] = [s['name'] for s in self.strategies]
        
        curr_id = self.ui_state.get('strategy_id', '')
        found = False
        for s in self.strategies:
            if s['id'] == curr_id:
                self.strategy_var.set(s['name'])
                found = True
                break
        if not found and self.strategies:
            self.strategy_var.set(self.strategies[0]['name'])
            self.ui_state['strategy_id'] = self.strategies[0]['id']
            self._save_state()


class MultiPeriodStrategyEditor(tk.Toplevel):
    def __init__(self, parent, engine, on_save_callback):
        super().__init__(parent)
        self.title("多周期过滤策略编辑器")
        
        # 尝试从配置文件读取上次保存的窗口位置与大小
        config_path = os.path.join(get_app_root(), "config", "standalone_tester_config.json")
        editor_geom = "850x580"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    editor_geom = cfg.get("editor_geometry", "850x580")
            except Exception:
                pass
                
        # 若是首次打开（配置中只存了宽高，不包含 '+' 偏移量），则执行居中计算
        if "+" not in editor_geom:
            try:
                w, h = map(int, editor_geom.split("x"))
            except Exception:
                w, h = 850, 580
                
            # 优先计算居中于父窗口
            parent_w = parent.winfo_width()
            parent_h = parent.winfo_height()
            parent_x = parent.winfo_x()
            parent_y = parent.winfo_y()
            
            if parent_w > 100 and parent_h > 100:
                x = parent_x + (parent_w - w) // 2
                y = parent_y + (parent_h - h) // 2
            else:
                # 降级居中于屏幕
                screen_w = self.winfo_screenwidth()
                screen_h = self.winfo_screenheight()
                x = (screen_w - w) // 2
                y = (screen_h - h) // 2
            editor_geom = f"{w}x{h}+{x}+{y}"
            
        self.geometry(editor_geom)
        
        self.transient(parent)
        self.grab_set()
        
        self.engine = engine
        self.on_save_callback = on_save_callback
        
        # 深拷贝策略配置，防止在未保存时直接修改全局数据
        self.strategies = [json.loads(json.dumps(s)) for s in self.engine.load_strategies()]
        self.current_idx = -1
        self.tooltip = None
        
        self._init_ui()
        self._refresh_list()
        
        if self.strategies:
            self.listbox.selection_set(0)
            self._on_select(None)
            
    def _init_ui(self):
        main_pane = tk.PanedWindow(self, orient="horizontal", sashrelief="raised", sashwidth=4)
        main_pane.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- 左侧策略列表区 ---
        left_frame = tk.Frame(main_pane)
        main_pane.add(left_frame, minsize=200)
        
        list_lbl = tk.Label(left_frame, text="策略列表", font=("Microsoft YaHei", 9, "bold"))
        list_lbl.pack(fill="x", pady=2)
        
        list_container = tk.Frame(left_frame)
        list_container.pack(fill="both", expand=True)
        
        self.listbox = tk.Listbox(list_container, font=("Microsoft YaHei", 9), selectmode="single")
        vsb = ttk.Scrollbar(list_container, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscroll=vsb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        
        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(fill="x", pady=5)
        
        btn_add = tk.Button(btn_frame, text="➕ 新增策略", command=self._add_strategy, bg="#4CAF50", fg="white", font=("Microsoft YaHei", 9))
        btn_add.pack(side="left", fill="x", expand=True, padx=2)
        
        btn_del = tk.Button(btn_frame, text="➖ 删除策略", command=self._del_strategy, bg="#F44336", fg="white", font=("Microsoft YaHei", 9))
        btn_del.pack(side="right", fill="x", expand=True, padx=2)
        
        # JSON 导入按钮
        json_btn_frame = tk.Frame(left_frame)
        json_btn_frame.pack(fill="x", pady=(0, 5))
        
        btn_import_json = tk.Button(json_btn_frame, text="📋 粘贴 JSON 策略", command=self._import_json_strategy, bg="#009688", fg="white", font=("Microsoft YaHei", 9))
        btn_import_json.pack(fill="x", expand=True, padx=2)
        
        # --- 右侧详细编辑区 ---
        self.right_frame = tk.LabelFrame(main_pane, text="策略详细配置与验证", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=10)
        main_pane.add(self.right_frame, minsize=600)
        
        # 1. 策略名称
        name_frame = tk.Frame(self.right_frame)
        name_frame.pack(fill="x", pady=4)
        tk.Label(name_frame, text="策略名称:", width=10, anchor="w").pack(side="left")
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(name_frame, textvariable=self.name_var)
        self.name_entry.pack(side="left", fill="x", expand=True)
        self.name_var.trace_add("write", self._on_name_changed)
        
        # 2. 合并模式
        mode_frame = tk.Frame(self.right_frame)
        mode_frame.pack(fill="x", pady=4)
        tk.Label(mode_frame, text="合并模式:", width=10, anchor="w").pack(side="left")
        self.mode_var = tk.StringVar()
        self.mode_combo = ttk.Combobox(mode_frame, textvariable=self.mode_var, state="readonly", values=["交集 (intersection)", "并集 (union)"])
        self.mode_combo.pack(side="left")
        
        # 3. 周期条件列表
        cond_lbl = tk.Label(self.right_frame, text="周期过滤条件 (将对各周期分别执行 DataFrame 过滤):", font=("Microsoft YaHei", 9, "bold"))
        cond_lbl.pack(fill="x", anchor="w", pady=(10, 5))
        
        self.cond_frame = tk.Frame(self.right_frame)
        self.cond_frame.pack(fill="both", expand=True)
        
        self.cond_rows = {}
        for period in self.engine.SUPPORTED_PERIODS:
            row = tk.Frame(self.cond_frame)
            row.pack(fill="x", pady=3)
            
            enable_var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(row, text=f"{period} 周期", variable=enable_var, width=10, anchor="w",
                                 command=lambda p=period: self._on_enable_toggled(p))
            chk.pack(side="left")
            
            expr_var = tk.StringVar()
            entry = tk.Entry(row, textvariable=expr_var, state="disabled")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            expr_var.trace_add("write", lambda *args, p=period: self._on_expr_changed(p))
            
            # 验证结果
            status_lbl = tk.Label(row, text="未验证", fg="gray", width=25, anchor="w", font=("Microsoft YaHei", 9))
            status_lbl.pack(side="left", padx=5)
            
            # 验证按钮
            btn_val = tk.Button(row, text="🔍 验证", command=lambda p=period: self._validate_single(p), state="disabled", font=("Microsoft YaHei", 8))
            btn_val.pack(side="right")
            
            self.cond_rows[period] = {
                "enable_var": enable_var,
                "chk": chk,
                "expr_var": expr_var,
                "entry": entry,
                "status_lbl": status_lbl,
                "btn_val": btn_val
            }
            
        # --- 底部按钮区 ---
        bottom_bar = tk.Frame(self)
        bottom_bar.pack(fill="x", side="bottom", padx=10, pady=10)
        
        btn_val_all = tk.Button(bottom_bar, text="🔍 验证全部条件", command=self._validate_all, bg="#0288D1", fg="white", font=("Microsoft YaHei", 9, "bold"))
        btn_val_all.pack(side="left", padx=5)
        
        btn_cancel = tk.Button(bottom_bar, text="❌ 取消", command=self.destroy, font=("Microsoft YaHei", 9))
        btn_cancel.pack(side="right", padx=5)
        
        btn_save = tk.Button(bottom_bar, text="💾 保存并应用", command=self._save_to_engine, bg="#4CAF50", fg="white", font=("Microsoft YaHei", 9, "bold"))
        btn_save.pack(side="right", padx=5)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for s in self.strategies:
            self.listbox.insert(tk.END, s['name'])
            
    def _sync_to_current_strategy(self):
        if self.current_idx < 0 or self.current_idx >= len(self.strategies):
            return
            
        strat = self.strategies[self.current_idx]
        strat['name'] = self.name_var.get().strip() or "未命名策略"
        
        mode_val = self.mode_var.get()
        if "union" in mode_val:
            strat['cross_mode'] = 'union'
        else:
            strat['cross_mode'] = 'intersection'
            
        # 同步各周期条件
        new_conditions = {}
        for period, row in self.cond_rows.items():
            if row['enable_var'].get():
                expr = row['expr_var'].get().strip()
                new_conditions[period] = {
                    "filter": expr,
                    "weight": strat.get('conditions', {}).get(period, {}).get('weight', 1.0)
                }
        strat['conditions'] = new_conditions

    def _on_name_changed(self, *args):
        """当输入框中的策略名称被修改时，动态更新左侧列表对应项名称，防多选"""
        if self.current_idx >= 0 and self.current_idx < len(self.strategies):
            new_name = self.name_var.get().strip() or "未命名策略"
            # 只有当新名字跟 listbox 对应项当前显示的名称不一致时才做修改，防止重新 selection_set 导致多选冲突
            if self.listbox.get(self.current_idx) != new_name:
                self.listbox.delete(self.current_idx)
                self.listbox.insert(self.current_idx, new_name)
                self.listbox.selection_set(self.current_idx)

    def _on_select(self, event):
        # 1. 同步当前正编辑的旧策略到内存
        self._sync_to_current_strategy()
            
        # 2. 读取新选中的策略
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.current_idx = idx
        
        strat = self.strategies[idx]
        
        # 3. 填充表单
        self.name_var.set(strat['name'])
        if strat.get('cross_mode') == 'union':
            self.mode_combo.set("并集 (union)")
        else:
            self.mode_combo.set("交集 (intersection)")
            
        # 4. 填充各周期条件
        for period, row in self.cond_rows.items():
            cond = strat.get('conditions', {}).get(period)
            if cond is not None:
                row['enable_var'].set(True)
                row['expr_var'].set(cond.get('filter', ''))
                row['entry'].config(state="normal")
                row['btn_val'].config(state="normal")
            else:
                row['enable_var'].set(False)
                row['expr_var'].set('')
                row['entry'].config(state="disabled")
                row['btn_val'].config(state="disabled")
            row['status_lbl'].config(text="未验证", fg="gray")

    def _on_enable_toggled(self, period):
        row = self.cond_rows[period]
        if row['enable_var'].get():
            row['entry'].config(state="normal")
            row['btn_val'].config(state="normal")
            if not row['expr_var'].get().strip():
                row['expr_var'].set("close > ma5d")
            row['status_lbl'].config(text="未验证", fg="gray")
        else:
            row['entry'].config(state="disabled")
            row['btn_val'].config(state="disabled")
            row['status_lbl'].config(text="已禁用", fg="#9E9E9E")

    def _on_expr_changed(self, period):
        row = self.cond_rows[period]
        if row['enable_var'].get():
            row['status_lbl'].config(text="未验证", fg="gray")

    def _add_strategy(self):
        self._sync_to_current_strategy()
        
        new_id = f"custom_strat_{int(time.time())}"
        new_strat = {
            "id": new_id,
            "name": f"自定义策略_{len(self.strategies) + 1}",
            "conditions": {
                "d": {"filter": "close > ma5d", "weight": 1.0}
            },
            "cross_mode": "intersection"
        }
        self.strategies.append(new_strat)
        self._refresh_list()
        
        new_idx = len(self.strategies) - 1
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(new_idx)
        self.listbox.see(new_idx)
        self._on_select(None)

    def _del_strategy(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "请选择需要删除的策略。")
            return
        idx = sel[0]
        
        if messagebox.askyesno("确认", f"确定删除策略“{self.strategies[idx]['name']}”吗？"):
            self.strategies.pop(idx)
            self._refresh_list()
            self.current_idx = -1
            
            # 清空表单
            self.name_var.set("")
            self.mode_combo.set("")
            for row in self.cond_rows.values():
                row['enable_var'].set(False)
                row['expr_var'].set("")
                row['entry'].config(state="disabled")
                row['btn_val'].config(state="disabled")
                row['status_lbl'].config(text="未验证", fg="gray")
                
            if self.strategies:
                self.listbox.selection_set(0)
                self._on_select(None)

    def _import_json_strategy(self):
        self._sync_to_current_strategy()
        
        # 弹出粘贴 JSON 的窗口
        dialog = tk.Toplevel(self)
        dialog.title("粘贴 JSON 策略配置")
        dialog.geometry("600x450")
        dialog.transient(self)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        w, h = 600, 450
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        
        lbl = tk.Label(dialog, text="请在下方粘贴您的 JSON 策略，支持单条或 strategies 数组结构：", 
                       font=("Microsoft YaHei", 9, "bold"), fg="#333", anchor="w")
         # 防止缩进警告，保证整齐
        lbl.pack(fill="x", padx=10, pady=10)
        
        text_area = tk.Text(dialog, font=("Consolas", 10), bd=2, relief="groove")
        text_area.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 默认填入一个占位示例，方便用户参考
        placeholder = (
            "{\n"
            "  \"name\": \"多级别量变到质变共振策略\",\n"
            "  \"cross_mode\": \"intersection\",\n"
            "  \"conditions\": {\n"
            "    \"3M\": {\"filter\": \"close > lower and close >= ma8d\", \"weight\": 1.0},\n"
            "    \"45d\": {\"filter\": \"dff2 > 0 and Rank > 60 and close > ma20d\", \"weight\": 1.0},\n"
            "    \"m\": {\"filter\": \"close > ma10d and close >= lastp1d\", \"weight\": 1.0},\n"
            "    \"w\": {\"filter\": \"close > upper or (close > ma5d and dff > 0)\", \"weight\": 1.0},\n"
            "    \"d\": {\"filter\": \"percent > 1.5 and Rank > 80\", \"weight\": 1.0}\n"
            "  }\n"
            "}"
        )
        text_area.insert("1.0", placeholder)
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill="x", pady=10, padx=10)
        
        def do_import():
            raw_text = text_area.get("1.0", tk.END).strip()
            if not raw_text:
                messagebox.showwarning("警告", "内容不能为空！", parent=dialog)
                return
            try:
                data = json.loads(raw_text)
            except Exception as e:
                messagebox.showerror("JSON 语法错误", f"解析失败：{e}", parent=dialog)
                return
                
            imported_list = []
            if isinstance(data, dict):
                if "strategies" in data and isinstance(data["strategies"], list):
                    imported_list = data["strategies"]
                else:
                    imported_list = [data]
            elif isinstance(data, list):
                imported_list = data
            else:
                messagebox.showerror("格式错误", "JSON 根节点必须是字典或列表对象！", parent=dialog)
                return
                
            valid_strats = []
            for idx, item in enumerate(imported_list):
                if not isinstance(item, dict):
                    continue
                name = item.get("name", "").strip()
                if not name:
                    name = f"未命名导入策略_{len(self.strategies) + len(valid_strats) + 1}"
                
                conditions = item.get("conditions", {})
                if not isinstance(conditions, dict):
                    continue
                
                clean_conditions = {}
                for p, cond in conditions.items():
                    if p not in self.engine.SUPPORTED_PERIODS:
                        continue
                    if not isinstance(cond, dict):
                        if isinstance(cond, str):
                            clean_conditions[p] = {"filter": cond, "weight": 1.0}
                        continue
                     
                    flt = cond.get("filter", "").strip()
                    if flt:
                        clean_conditions[p] = {
                            "filter": flt,
                            "weight": float(cond.get("weight", 1.0))
                        }
                        
                if not clean_conditions:
                    clean_conditions["d"] = {"filter": "close > ma5d", "weight": 1.0}
                    
                new_strat = {
                    "id": item.get("id") or f"custom_strat_{int(time.time())}_{idx}",
                    "name": name,
                    "conditions": clean_conditions,
                    "cross_mode": item.get("cross_mode") or "intersection"
                }
                valid_strats.append(new_strat)
                
            if not valid_strats:
                messagebox.showerror("导入失败", "未识别到任何符合条件的策略配置！", parent=dialog)
                return
                
            self.strategies.extend(valid_strats)
            self._refresh_list()
            
            new_idx = len(self.strategies) - len(valid_strats)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(new_idx)
            self.listbox.see(new_idx)
            self._on_select(None)
            
            messagebox.showinfo("成功", f"成功导入 {len(valid_strats)} 条策略！", parent=dialog)
            dialog.destroy()
            
        btn_ok = tk.Button(btn_frame, text="✅ 解析并导入", command=do_import, bg="#4CAF50", fg="white", font=("Microsoft YaHei", 9, "bold"))
        btn_ok.pack(side="right", padx=5)
        
        btn_cancel = tk.Button(btn_frame, text="❌ 取消", command=dialog.destroy, font=("Microsoft YaHei", 9))
        btn_cancel.pack(side="right", padx=5)

    def _validate_single(self, period):
        row = self.cond_rows[period]
        expr = row['expr_var'].get().strip()
        if not expr:
            row['status_lbl'].config(text="❌ 表达式为空", fg="red")
            return False
            
        success, msg = self.engine.validate_condition(expr, period)
        if success:
            row['status_lbl'].config(text="✅ 语法验证通过", fg="#2E7D32")
            return True
        else:
            short_msg = msg if len(msg) < 25 else msg[:22] + "..."
            row['status_lbl'].config(text=short_msg, fg="#D32F2F")
            self._create_tooltip(row['status_lbl'], msg)
            return False

    def _create_tooltip(self, widget, text):
        def enter(event):
            if self.tooltip:
                self.tooltip.destroy()
            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{event.x_root+15}+{event.y_root+10}")
            lbl = tk.Label(self.tooltip, text=text, justify="left",
                           bg="#FFFDE7", fg="#5D4037", relief="solid", bd=1,
                           font=("Microsoft YaHei", 9), padx=5, pady=3)
            lbl.pack()
        def leave(event):
            if self.tooltip:
                self.tooltip.destroy()
                self.tooltip = None
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _validate_all(self):
        has_active = False
        all_ok = True
        for period, row in self.cond_rows.items():
            if row['enable_var'].get():
                has_active = True
                ok = self._validate_single(period)
                if not ok:
                    all_ok = False
        if not has_active:
            messagebox.showwarning("验证失败", "请至少启用一个周期条件！")
            return False
        if all_ok:
            messagebox.showinfo("验证成功", "所有启用的周期条件均已验证通过！")
            return True
        else:
            messagebox.showerror("验证失败", "部分周期条件存在语法错误，请检查！")
            return False

    def _save_to_engine(self):
        self._sync_to_current_strategy()
        if not self.strategies:
            messagebox.showwarning("警告", "策略列表不能为空！")
            return
            
        for s in self.strategies:
            if not s.get('conditions'):
                messagebox.showwarning("警告", f"策略“{s['name']}”未配置任何有效过滤条件！")
                return
            if not s['name'].strip():
                messagebox.showwarning("警告", "策略名称不能为空！")
                return
                
        success = self.engine.save_strategies(self.strategies)
        if success:
            self.on_save_callback()
            messagebox.showinfo("保存成功", "所有多周期策略已成功保存并重新加载！")
            self.destroy()
        else:
            messagebox.showerror("错误", "保存策略失败。")

    def destroy(self):
        """销毁窗口时，将当前的窗口几何属性（位置和大小）保存至配置文件"""
        try:
            geom = self.geometry()
            if "+" in geom:
                config_path = os.path.join(get_app_root(), "config", "standalone_tester_config.json")
                cfg = {}
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                cfg["editor_geometry"] = geom
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = StandaloneMultiPeriodTester()
    app.mainloop()
