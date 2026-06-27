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

class StandaloneMultiPeriodTester(tk.Tk, TreeviewMixin):
    def __init__(self):
        super().__init__()
        self.title("多周期联动策略筛选器 - 独立验证版")
        self.geometry("1100x700")
        
        self.engine = MultiPeriodStrategyEngine()
        self.strategies = self.engine.load_strategies()
        self.top_now = None
        
        self.config_file = "config/standalone_tester_config.json"
        
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
        # --- Toolbar ---
        toolbar = tk.Frame(self, bd=1, relief="raised")
        toolbar.pack(fill="x", padx=5, pady=5)
        
        tk.Label(toolbar, text="策略:").pack(side="left", padx=5)
        self.strategy_var = tk.StringVar()
        self.strategy_combo = ttk.Combobox(toolbar, textvariable=self.strategy_var, state="readonly", width=25)
        self.strategy_combo['values'] = [s['name'] for s in self.strategies]
        self.strategy_combo.pack(side="left", padx=5)
        
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
        
        self.status_var = tk.StringVar(value="准备就绪")
        tk.Label(toolbar, textvariable=self.status_var, fg="blue").pack(side="right", padx=10)
        
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

        self.stats_lbl_final = tk.Label(self.stats_frame, text="【最终筛选结果】暂无数据", font=("Microsoft YaHei", 9, "bold"), bg="#f0f0f0", fg="#2E7D32")
        self.stats_lbl_final.pack(side="right", padx=20, pady=4)
        
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
        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().unsubscribe(self._on_favorites_changed)
        except Exception:
            pass
        self._save_state()
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

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = StandaloneMultiPeriodTester()
    app.mainloop()
