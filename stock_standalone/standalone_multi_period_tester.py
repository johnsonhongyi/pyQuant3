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
        # 缓存时间戳：记录 top_now 和各周期数据的最后加载时间
        self._top_now_cache_ts = 0.0          # top_now 全市场数据缓存时间戳
        self._period_cache_ts: dict = {}      # {period: timestamp} 各周期数据缓存时间
        
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
        
        # 历史二次过滤状态
        self._current_history_query = self.ui_state.get('current_history_query', "")
        self._history_filter_error = None
        self.query_manager = None
        
        # 板块详情窗口句柄
        self.detail_win = None
        self.txt_widget = None
        
        try:
            from history_manager import QueryHistoryManager
            from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
            
            self.query_manager = QueryHistoryManager(
                self,
                history_file=SEARCH_HISTORY_FILE,
                sync_history_callback=self._on_history_sync
            )
            if hasattr(self.query_manager, "editor_frame"):
                self.query_manager.editor_frame.pack_forget()
            
            if self._current_history_query and hasattr(self.query_manager, "entry_query"):
                self.query_manager.entry_query.delete(0, tk.END)
                self.query_manager.entry_query.insert(0, self._current_history_query)
        except Exception as e:
            print(f"[MultiPeriodTester] 实例化 QueryHistoryManager 失败: {e}")
        
        # 订阅全局自选股改变通知
        try:
            from global_favorites import GlobalFavoriteManager
            self._last_favorites_version = GlobalFavoriteManager().version
            self.after(500, self._poll_favorites_loop)
        except Exception:
            pass

        # 绑定 Alt+/ 快捷键显示帮助文档
        self.bind("<Alt-slash>", lambda e: self.show_help_documentation())
        self.bind("<Alt-question>", lambda e: self.show_help_documentation())


        
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
            "sortby_col_ascend": False,
            "category_win_geometry": "",
            "current_history_query": ""
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
        # 从当前选中的 strategy_var 名字解析出真实的 strategy_id，实现自动记忆最后的运行/选择策略
        strat_name = self.strategy_var.get()
        strat_id = ""
        for s in self.strategies:
            if s['name'] == strat_name:
                strat_id = s['id']
                break
        self.ui_state['strategy_id'] = strat_id
        self.ui_state['periods'] = [p for p, var in self.period_vars.items() if var.get()]
        self.ui_state['custom_cols'] = [c for c, var in self.custom_col_vars.items() if var.get()]
        self.ui_state['manual_col_pool'] = list(self.manual_col_pool)
        self.ui_state['link_vis'] = self.link_vis_var.get()
        self.ui_state['link_tdx'] = self.link_tdx_var.get()
        self.ui_state['link_ths'] = self.link_ths_var.get()
        self.ui_state['current_history_query'] = getattr(self, "_current_history_query", "")
        try:
            self.ui_state['geometry'] = self.geometry()
        except Exception:
            pass
        if getattr(self, "detail_win", None) is not None and self.detail_win.winfo_exists():
            try:
                self.ui_state['category_win_geometry'] = self.detail_win.geometry()
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
        try:
            cfg = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            # 合并时必须以磁盘上最新的配置为基准，然后更新 ui_state，但跳过 editor_geometry 等外部维护的字段
            # 防止主窗口关闭时将旧的 editor_geometry 覆盖回去
            for k, v in self.ui_state.items():
                if k != "editor_geometry":
                    cfg[k] = v
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
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
            
        tk.Button(toolbar, text="▶ 运行筛选", command=lambda: self.run_filter(force_reload=False), bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side="left", padx=5)
        tk.Button(toolbar, text="🔄 强制刷新", command=lambda: self.run_filter(force_reload=True), bg="#FF6F00", fg="white", font=("Arial", 9)).pack(side="left", padx=5)
            
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
        self.diag_entry.bind("<Button-3>", self._on_diag_entry_right_click)
        
        btn_diag = tk.Button(diagnose_frame, text="🔍 诊断", command=self._on_diagnose_click, bg="#0288D1", fg="white", font=("Microsoft YaHei", 9), padx=5, pady=1)
        btn_diag.pack(side="left", padx=2)

        self.stats_lbl_final = tk.Label(self.stats_frame, text="【最终筛选结果】暂无数据", font=("Microsoft YaHei", 9, "bold"), bg="#f0f0f0", fg="#2E7D32")
        self.stats_lbl_final.pack(side="right", padx=20, pady=4)
        
        # 运行日志中间状态显示区域
        self.status_lbl = tk.Label(self.stats_frame, textvariable=self.status_var, font=("Microsoft YaHei", 9, "bold"), bg="#f0f0f0", fg="#1A73E8")
        self.status_lbl.pack(side="left", fill="x", expand=True, padx=10, pady=4)
        
        # 创建清除历史二次过滤的按钮，默认不显示
        self.btn_clear_history_filter = tk.Button(
            self.stats_frame, text="❌ 清除过滤",
            command=self._clear_history_filter,
            bg="#FFEBEE", fg="#C62828", relief="groove",
            font=("Microsoft YaHei", 8), padx=6, pady=1
        )
        
        # --- Results Treeview ---
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        
        self.tree = ttk.Treeview(tree_frame, show="headings")
        
        # 极窄垂直滚动条：用 tk.Scrollbar 直接设置 width=8，
        # ttk.Scrollbar 在 Windows 主题下 width 参数无效
        vsb = tk.Scrollbar(tree_frame, orient="vertical",
                           command=self.tree.yview,
                           width=8, bd=0, relief="flat",
                           bg="#B0BEC5", troughcolor="#ECEFF1",
                           activebackground="#78909C",
                           highlightthickness=0)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        

        self.strategy_combo.bind('<<ComboboxSelected>>', lambda e: self._on_strategy_selected())
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._on_tree_leave)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.tag_configure("favorite", foreground="#C62828", font=("Microsoft YaHei", 9, "bold"))
        self.tree_tooltip = None
        self.current_tooltip_col = None

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

    def _get_display_periods_for_custom_col(self, col_name, active_periods, df=None):
        """
        判断某个自定义列在各周期的数据是否相同。如果相同，只保留最小周期；否则保留所有活跃周期。
        """
        if not active_periods:
            return []
            
        # 静态白名单保护：dff, dff2, dff3, Rank 已知是各周期相同的
        if col_name.lower() in ("dff", "dff2", "dff3", "rank"):
            return [active_periods[0]]
            
        # 如果 df 存在且不为空，可以通过实际数据进行比对
        if df is not None and not df.empty and len(active_periods) > 1:
            p0 = active_periods[0]
            col0 = f"{col_name}_{p0}"
            if col0 in df.columns:
                is_all_same = True
                for p in active_periods[1:]:
                    col_p = f"{col_name}_{p}"
                    if col_p in df.columns:
                        series0 = df[col0]
                        series_p = df[col_p]
                        try:
                            diff = (series0 - series_p).abs().max()
                            if pd.isna(diff) or diff > 1e-5:
                                if not series0.fillna("").astype(str).equals(series_p.fillna("").astype(str)):
                                    is_all_same = False
                                    break
                        except Exception:
                            if not series0.fillna("").astype(str).equals(series_p.fillna("").astype(str)):
                                is_all_same = False
                                break
                    else:
                        is_all_same = False
                        break
                if is_all_same:
                    return [p0]
                    
        return active_periods

    def _update_tree_columns(self):
        base_cols = ["code", "name", "price", "percent", "volume", "ratio"]
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        active_customs = [c for c, var in self.custom_col_vars.items() if var.get()]
        
        custom_cols = []
        df = getattr(self, "_last_flat_df", None)
        for c in active_customs:
            disp_periods = self._get_display_periods_for_custom_col(c, active_periods, df)
            for p in disp_periods:
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
            disp_periods = self._get_display_periods_for_custom_col(c, active_periods, df)
            for p in disp_periods:
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
                        self.run_filter(force_reload=False)
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
        """切换策略时：保存状态，不改变周期的勾选，并立即触发筛选展示数据"""
        strat_name = self.strategy_var.get()
        strat_config = None
        for s in self.strategies:
            if s['name'] == strat_name:
                self.ui_state['strategy_id'] = s['id']
                strat_config = s
                break
        
        self._save_state()
        
        # 切换策略后，以当前显示的 col 及菜单选择的周期为准，立即运行筛选（不强刷缓存）
        self.run_filter(force_reload=False)

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

    def _on_tree_motion(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id = self.tree.identify_column(event.x)
            if col_id:
                try:
                    col_idx = int(col_id.replace('#', '')) - 1
                    columns = self.tree['columns']
                    if 0 <= col_idx < len(columns):
                        col_name = columns[col_idx]
                        if getattr(self, 'current_tooltip_col', None) != col_name:
                            self._show_tree_tooltip(event.x_root, event.y_root + 20, col_name)
                            self.current_tooltip_col = col_name
                        return
                except ValueError:
                    pass
        self._hide_tree_tooltip()

    def _show_tree_tooltip(self, x, y, text):
        self._hide_tree_tooltip()
        self.tree_tooltip = tk.Toplevel(self)
        self.tree_tooltip.wm_overrideredirect(True)
        self.tree_tooltip.wm_geometry(f"+{x}+{y}")
        self.tree_tooltip.attributes("-topmost", True)
        lbl = tk.Label(self.tree_tooltip, text=text, justify="left",
                       bg="#FFFDE7", fg="#1B5E20", relief="solid", bd=1,
                       font=("Microsoft YaHei", 9, "bold"), padx=6, pady=4)
        lbl.pack()

    def _hide_tree_tooltip(self):
        if getattr(self, 'tree_tooltip', None):
            self.tree_tooltip.destroy()
            self.tree_tooltip = None
            self.current_tooltip_col = None

    def _on_tree_leave(self, event):
        self._hide_tree_tooltip()

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

    def _update_status(self, text):
        """线程安全的底部状态日志更新（由 after(0,...) 保证在主线程执行，不调用 update_idletasks）"""
        self.status_var.set(text)

    # ── 缓存有效期常量 ──────────────────────────────────────────
    _CACHE_TTL_TRADING    = 3600   # 交易时段缓存有效期：1小时
    _CACHE_TTL_NON_TRADE  = None   # 非交易时段：永不过期（用 None 表示）

    def _is_cache_valid(self, ts: float) -> bool:
        """判断某个时间戳的缓存是否仍有效（交易时段1小时TTL，非交易时段永久有效）"""
        if ts == 0.0:
            return False
        is_trade = cct.get_work_time_duration()  # 是否处于交易时段
        if not is_trade:
            return True  # 非交易时段：缓存永远有效，不重新拉取
        # 交易时段：超过 TTL 则视为失效
        return (time.time() - ts) < self._CACHE_TTL_TRADING

    def run_filter(self, force_reload=False):
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        if not active_periods:
            messagebox.showwarning("警告", "请至少选择一个参与周期！")
            return
            
        strat_name = self.strategy_var.get()
        strat_config = next((s for s in self.strategies if s['name'] == strat_name), None)
        if not strat_config:
            return
            
        if force_reload:
            # 强制刷新：清空所有缓存和时间戳
            self.top_now = None
            self._top_now_cache_ts = 0.0
            self.engine._period_dfs.clear()
            self._period_cache_ts.clear()
            self.status_var.set("🔄 强制刷新：正在重新获取全部数据...")
        else:
            # 智能缓存：检查 top_now 缓存是否过期
            if not self._is_cache_valid(self._top_now_cache_ts):
                self.top_now = None
                self._top_now_cache_ts = 0.0
            # 检查各周期缓存是否过期，过期则清除
            for p in list(self._period_cache_ts.keys()):
                if not self._is_cache_valid(self._period_cache_ts.get(p, 0.0)):
                    self._period_cache_ts.pop(p, None)
                    self.engine._period_dfs.pop(p, None)
            if self.top_now is None:
                self.status_var.set("正在获取基础全市场数据...")
            else:
                is_trade = cct.get_work_time_duration()
                age = int(time.time() - self._top_now_cache_ts)
                trade_hint = "交易时段" if is_trade else "非交易时段"
                self.status_var.set(f"⚡ 使用内存缓存 ({trade_hint}，缓存已存在 {age}s)，开始筛选...")
        
        threading.Thread(target=self._worker, args=(strat_config, active_periods), daemon=True).start()
        
    def _worker(self, strat_config, active_periods):
        try:
            start_time = time.time()
            # ── 加载全市场行情 top_now ──────────────────────────
            if self.top_now is None:
                self.after(0, self._update_status, "正在获取全市场实时行情...")
                self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
                self._top_now_cache_ts = time.time()
            # ── 逐周期加载 ─────────────────────────────────────
            for period in active_periods:
                cached = (
                    period in self.engine._period_dfs
                    and not self.engine._period_dfs[period].empty
                    and self._is_cache_valid(self._period_cache_ts.get(period, 0.0))
                )
                if cached:
                    age = int(time.time() - self._period_cache_ts.get(period, 0.0))
                    self.after(0, self._update_status, f"⚡ [{period}] 命中缓存 (已存在 {age}s)，跳过重新加载")
                else:
                    self.after(0, self._update_status, f"📥 [{period}] 首次加载或缓存过期，正在读取计算...")
                    # 清除旧缓存，保证 engine 重新加载
                    self.engine._period_dfs.pop(period, None)
                    self.engine.load_period_data(period, self.top_now)
                    self._period_cache_ts[period] = time.time()

            self.after(0, self._update_status, "🔍 正在执行跨周期交叉验证...")
            result_df = self.engine.evaluate_strategy(strat_config, active_periods)
            
            elapsed = time.time() - start_time
            self.last_result_df = result_df
            self.last_elapsed = elapsed
            self.after(0, self._show_results, result_df, elapsed)
        except Exception as e:
            import traceback
            self.after(0, self._update_status, f"❌ 错误: {e}")
            print(f"[MultiPeriodTester] _worker exception:\n{traceback.format_exc()}")
            
    def _show_results(self, df, elapsed):
        self._last_selected_code = None
        # 同步给 query_manager 完整的宽表数据，以支持在 history 弹窗里进行“测试”或“双击”统计
        flat_df = self._build_flat_df(df)
        self._last_flat_df = flat_df
        
        self._update_tree_columns()
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self._update_stats_ui()
        
        if df.empty:
            self.status_var.set(f"完成，未找到符合条件的标的。(耗时 {elapsed:.1f}s)")
            if getattr(self, "query_manager", None) is not None:
                self.query_manager.df_all = df
            if hasattr(self, "btn_clear_history_filter"):
                self.btn_clear_history_filter.pack_forget()
            return
            
        if getattr(self, "query_manager", None) is not None:
            self.query_manager.df_all = flat_df
            
        # 应用二次历史过滤
        filtered_df = flat_df
        if getattr(self, "_current_history_query", ""):
            filtered_df = self._apply_secondary_filter(flat_df, self._current_history_query)
            if hasattr(self, "btn_clear_history_filter"):
                self.btn_clear_history_filter.pack(side="right", padx=10, pady=1)
        else:
            if hasattr(self, "btn_clear_history_filter"):
                self.btn_clear_history_filter.pack_forget()
                
        if filtered_df.empty:
            if getattr(self, "_history_filter_error", None):
                self.status_var.set(f"⚠️ {self._history_filter_error} (耗时 {elapsed:.1f}s)")
            else:
                self.status_var.set(f"完成，未找到符合二次过滤条件的标的。(二次过滤前 {len(df)} 只，耗时 {elapsed:.1f}s)")
            return
            
        # 更新 stats_lbl_final 显示二次过滤状态
        stats = getattr(self.engine, "last_stats", None)
        if stats and stats.get("final"):
            final = stats["final"]
            mode_str = "交集" if final["mode"] == "intersection" else "并集"
            if getattr(self, "_current_history_query", ""):
                self.stats_lbl_final.config(
                    text=f"【最终 ({mode_str})】 共 {len(filtered_df)} / 二次前 {len(df)} 只 ({len(filtered_df)/final['total']*100:.3f}%)"
                )
                
        if getattr(self, "_current_history_query", ""):
            if getattr(self, "_history_filter_error", None):
                self.status_var.set(f"⚠️ {self._history_filter_error} (二次过滤前 {len(df)} 只，耗时 {elapsed:.1f}s)")
            else:
                self.status_var.set(f"完成，共筛选出 {len(filtered_df)} 只标的 (二次过滤前 {len(df)} 只，耗时 {elapsed:.1f}s)")
        else:
            self.status_var.set(f"完成，共筛选出 {len(filtered_df)} 只标的。(耗时 {elapsed:.1f}s)")
            
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        active_customs = [c for c, var in self.custom_col_vars.items() if var.get()]
        
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()
            
        for code, row in filtered_df.iterrows():
            name = row.get('name', '--')
            price = round(row.get('close', 0), 2)
            percent = round(row.get('percent', 0), 2)
            vol = round(row.get('volume', 0), 2)
            ratio = round(row.get('ratio', 0), 2)
            
            is_fav = code in fav_stocks
            display_name = f"★ {name}" if is_fav else name
            
            values = [code, display_name, price, percent, vol, ratio]
            
            for c in active_customs:
                disp_periods = self._get_display_periods_for_custom_col(c, active_periods, filtered_df)
                for p in disp_periods:
                    val = '--'
                    col_name = f"{c}_{p}"
                    if col_name in filtered_df.columns:
                        raw_val = row.get(col_name)
                        if pd.notna(raw_val):
                            if isinstance(raw_val, (int, float)):
                                val = round(raw_val, 2)
                            else:
                                val = str(raw_val)
                    values.append(val)
            
            for p in active_periods:
                pass_val = row.get(f'pass_{p}', False)
                values.append('✅' if pass_val else '--')
                
            row_tags = ("favorite",) if is_fav else ()
            self.tree.insert("", "end", iid=code, values=values, tags=row_tags)
            
        self.perform_tree_multi_level_sort(self.tree)
        self._adjust_column_widths()

    def _on_history_sync(self, **kwargs):
        source = kwargs.get("source", "")
        selected_query = kwargs.get("selected_query")
        
        if source == "use":
            self._current_history_query = selected_query.strip() if selected_query else ""
            self._save_state()
            if self._current_history_query:
                self.status_var.set(f"✅ 已应用历史二次过滤: {self._current_history_query}")
            else:
                self.status_var.set("已清除历史二次过滤")
                
            if self.last_result_df is not None:
                self.after(0, self._show_results, self.last_result_df, self.last_elapsed)

    def _build_flat_df(self, df):
        if df is None or df.empty:
            return df
        
        flat_rows = []
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        
        for code, row in df.iterrows():
            item_row = row.to_dict()
            for period in active_periods:
                df_p = self.engine._period_dfs.get(period)
                if df_p is not None and not df_p.empty and code in df_p.index:
                    row_p = df_p.loc[code]
                    if isinstance(row_p, pd.DataFrame):
                        row_p = row_p.iloc[0]
                    for k, val in row_p.to_dict().items():
                        if k not in ('code', 'name'):
                            item_row[f"{k}_{period}"] = val
            flat_rows.append(item_row)
            
        flat_df = pd.DataFrame(flat_rows, index=df.index)
        flat_df.index.name = 'code'
        return flat_df

    def _suffix_query(self, expr, period_suffix):
        import re
        cols_set = set()
        df_p = self.engine._period_dfs.get(period_suffix)
        if df_p is not None and not df_p.empty:
            cols_set = set(df_p.columns)
            
        def repl(match):
            word = match.group(0)
            if word in cols_set:
                return f"{word}_{period_suffix}"
            return word
        return re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', repl, expr)

    def _apply_secondary_filter(self, df, query_expr):
        if not query_expr or df is None or df.empty:
            self._history_filter_error = None
            return df
        
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        target_period = 'd' if 'd' in active_periods else (active_periods[0] if active_periods else 'd')
        
        converted_query = self._suffix_query(query_expr, target_period)
        
        try:
            filtered_df = df.query(converted_query)
            self._history_filter_error = None
            return filtered_df
        except Exception as e1:
            try:
                filtered_df = df.query(query_expr)
                self._history_filter_error = None
                return filtered_df
            except Exception as e2:
                self._history_filter_error = f"过滤语法错误: {e2}"
                return df

    def _clear_history_filter(self):
        self._current_history_query = ""
        self._history_filter_error = None
        if self.query_manager and hasattr(self.query_manager, "entry_query"):
            try:
                self.query_manager.entry_query.delete(0, tk.END)
            except Exception:
                pass
        self._save_state()
        if hasattr(self, "btn_clear_history_filter"):
            self.btn_clear_history_filter.pack_forget()
            
        if self.last_result_df is not None:
            self.after(0, self._show_results, self.last_result_df, self.last_elapsed)

    def _on_tree_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
            
        item = self.tree.identify_row(event.y)
        if not item:
            return
            
        values = self.tree.item(item, "values")
        if not values:
            return
            
        code = str(values[0]).strip()
        name = str(values[1]).strip()
        
        category_str = ""
        hangye_str = ""
        
        # 优先从 wencaiData 获取，无则从缓存 period_dfs 里提取
        try:
            from JSONData import wencaiData as wcd
            res = wcd.search_ths_data(code)
            if res is not None and not res.empty:
                row_w = res.iloc[0]
                category_str = row_w.get('category', '')
                hangye_str = row_w.get('hangye', '')
        except Exception as e:
            print(f"[MultiPeriodTester] Fetching category error: {e}")
            
        if not category_str:
            active_periods = [p for p, var in self.period_vars.items() if var.get()]
            for p in active_periods:
                df_p = self.engine._period_dfs.get(p)
                if df_p is not None and not df_p.empty and code in df_p.index:
                    row_p = df_p.loc[code]
                    if isinstance(row_p, pd.DataFrame):
                        row_p = row_p.iloc[0]
                    category_str = row_p.get('category', '')
                    hangye_str = row_p.get('hangye', '')
                    if category_str:
                        break
                        
        if not category_str or str(category_str).strip() == 'nan':
            category_str = "暂无板块概念信息"
        if not hangye_str or str(hangye_str).strip() == 'nan':
            hangye_str = "暂无行业分类信息"
            
        cats_list = [c.strip() for c in category_str.split(';') if c.strip()]
        
        content = f"个股代码: {code}\n"
        content += f"个股名称: {name}\n"
        content += f"所属行业: {hangye_str}\n"
        content += "──────────────────────────────────────────\n"
        content += "所属概念板块:\n"
        if cats_list and cats_list[0] != "暂无板块概念信息":
            for idx, cat in enumerate(cats_list, 1):
                content += f"  {idx:02d}. {cat}\n"
        else:
            content += "  (无)\n"
            
        self.show_category_detail(code, name, content)

    def show_category_detail(self, code, name, category_content):
        def on_close():
            try:
                self.ui_state['category_win_geometry'] = self.detail_win.geometry()
                self._save_state()
            except Exception:
                pass
            if self.detail_win and self.detail_win.winfo_exists():
                self.detail_win.destroy()
            self.detail_win = None
            self.txt_widget = None

        if hasattr(self, "detail_win") and self.detail_win and self.detail_win.winfo_exists():
            self.detail_win.title(f"板块行业详情 - {name} ({code})")
            self.txt_widget.config(state="normal")
            self.txt_widget.delete("1.0", tk.END)
            self.txt_widget.insert("1.0", category_content)
            self.txt_widget.config(state="disabled")
            
            state = self.detail_win.state()
            if state == "iconic":
                self.detail_win.deiconify()
            self.detail_win.lift()
            self.detail_win.focus_force()
        else:
            self.detail_win = tk.Toplevel(self)
            self.detail_win.title(f"板块行业详情 - {name} ({code})")
            self.detail_win.withdraw()
            
            saved_geom = self.ui_state.get('category_win_geometry', '')
            if saved_geom:
                try:
                    self.detail_win.geometry(saved_geom)
                except Exception:
                    pass
            if not saved_geom:
                w, h = 450, 400
                mx, my = self.winfo_pointerx(), self.winfo_pointery()
                pos_x, pos_y = max(0, mx - w - 20), max(0, my - h - 20)
                self.detail_win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
                
            self.detail_win.deiconify()
            
            self.txt_widget = tk.Text(
                self.detail_win, wrap="word", 
                font=("Microsoft YaHei", 10), 
                bg="#FAFAFA", fg="#212121",
                padx=10, pady=10, relief="flat"
            )
            self.txt_widget.pack(expand=True, fill="both")
            self.txt_widget.insert("1.0", category_content)
            self.txt_widget.config(state="disabled")
            
            self.detail_win.bind("<Escape>", lambda e: on_close())
            self.detail_win.protocol("WM_DELETE_WINDOW", on_close)
            
            self.detail_win.lift()
            self.detail_win.focus_force()

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
        if getattr(self, "query_manager", None) is not None:
            try:
                self.query_manager.save_search_history()
            except Exception as e:
                print(f"Error saving query history on close: {e}")
        if _parent_class == tk.Toplevel:
            self.withdraw()
        else:
            self.destroy()

    def show_help_documentation(self):
        """打开/显示系统多周期与信号指标使用说明文档，实时加载本地文件以支持动态互动更新，带搜索及编辑保存能力"""
        from sys_utils import get_conf_path
        help_file_path = get_conf_path("config/multi_period_help.md")
        
        try:
            with open(help_file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"读取帮助文档失败: {e}"
            
        # 弹出一个独立的窗口显示文档
        help_win = tk.Toplevel(self)
        help_win.title("多周期与信号策略帮助及管理中心 (Alt+/ 或 ESC 关闭)")
        
        # 恢复上次保存的窗口位置与尺寸
        help_geom = self.ui_state.get("help_geometry", "900x700")
        help_win.geometry(help_geom)
        
        # 顶部工具栏
        help_toolbar = tk.Frame(help_win, bd=1, relief="raised", padx=5, pady=5)
        help_toolbar.pack(side=tk.TOP, fill=tk.X)
        
        # 增加滚动条与文本域（必须在定义内层函数前创建，防止 NameError）
        scrollbar = tk.Scrollbar(help_win)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 修复：font size 必须为整型 (10)
        text_area = tk.Text(help_win, wrap=tk.WORD, yscrollcommand=scrollbar.set, font=("Microsoft YaHei", 10))
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.config(command=text_area.yview)
        
        tk.Label(help_toolbar, text="搜索内容:", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=5)
        
        search_var = tk.StringVar()
        search_entry = tk.Entry(help_toolbar, textvariable=search_var, width=20, font=("Microsoft YaHei", 9))
        search_entry.pack(side=tk.LEFT, padx=5)
        
        match_index_ref = [0]
        
        def do_search(event=None):
            text_area.tag_remove("match", "1.0", tk.END)
            text_area.tag_remove("current_match", "1.0", tk.END)
            query = search_var.get().strip()
            if not query:
                status_label.config(text="请输入搜索关键词", fg="blue")
                return
            
            text_area.tag_configure("match", background="yellow", foreground="black")
            
            start_pos = "1.0"
            matches = []
            while True:
                pos = text_area.search(query, start_pos, stopindex=tk.END, nocase=True)
                if not pos:
                    break
                end_pos = f"{pos} + {len(query)}c"
                text_area.tag_add("match", pos, end_pos)
                matches.append(pos)
                start_pos = end_pos
                
            if matches:
                idx = match_index_ref[0] % len(matches)
                target_pos = matches[idx]
                text_area.see(target_pos)
                # 突出当前高亮的搜索结果
                text_area.tag_configure("current_match", background="orange", foreground="black")
                text_area.tag_add("current_match", target_pos, f"{target_pos} + {len(query)}c")
                
                status_label.config(text=f"找到 {len(matches)} 处匹配 (当前第 {idx + 1} 处)", fg="#2E7D32")
                match_index_ref[0] += 1
            else:
                status_label.config(text="未找到匹配项", fg="#C62828")
                
        search_entry.bind("<Return>", do_search)
        
        btn_search = tk.Button(help_toolbar, text="下一个 🔍", command=do_search, font=("Microsoft YaHei", 9), relief="groove")
        btn_search.pack(side=tk.LEFT, padx=5)
        
        # 状态提示
        status_label = tk.Label(help_toolbar, text="状态: 可编辑模式 (Ctrl+S 保存)", font=("Microsoft YaHei", 9), fg="#555555")
        status_label.pack(side=tk.LEFT, padx=15)
        
        # 保存修改函数
        def do_save(event=None):
            new_content = text_area.get("1.0", tk.END)
            try:
                with open(help_file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                status_label.config(text="状态: 保存成功 ✔️", fg="#2E7D32")
                # 延迟重置提示文字
                help_win.after(1500, lambda: status_label.config(text="状态: 可编辑模式 (Ctrl+S 保存)", fg="#555555"))
            except Exception as ex:
                status_label.config(text=f"保存失败: {ex}", fg="#C62828")
                
        btn_save = tk.Button(help_toolbar, text="保存修改 💾", command=do_save, font=("Microsoft YaHei", 9, "bold"), bg="#E8F5E9", fg="#2E7D32", relief="groove")
        btn_save.pack(side=tk.RIGHT, padx=10)
        
        # 写入内容
        text_area.insert(tk.END, content)
        
        # 窗口关闭与位置/大小持久化保存逻辑
        def on_help_win_close():
            try:
                geom = help_win.geometry()
                self.ui_state["help_geometry"] = geom
                self._save_state()
            except Exception as ex:
                print(f"Error saving help geometry: {ex}")
            help_win.destroy()
            
        help_win.protocol("WM_DELETE_WINDOW", on_help_win_close)
        
        # 绑定快捷键
        help_win.bind("<Control-s>", do_save)
        help_win.bind("<Escape>", lambda e: on_help_win_close())
        help_win.bind("<Alt-slash>", lambda e: on_help_win_close())
        help_win.bind("<Alt-question>", lambda e: on_help_win_close())




    def _poll_favorites_loop(self):
        try:
            from global_favorites import GlobalFavoriteManager
            current_version = GlobalFavoriteManager().version
            if current_version != getattr(self, '_last_favorites_version', 0):
                self._last_favorites_version = current_version
                self._refresh_ui_favorites()
        except Exception as e:
            pass
        finally:
            try:
                if self.winfo_exists():
                    self.after(500, self._poll_favorites_loop)
            except Exception:
                pass

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
        menu.add_command(label="📋 复制代码", command=lambda: self.copy_code(code))
        menu.add_command(label="📝 复制行信息", command=lambda: self.copy_row_info(values))
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

    def copy_code(self, code):
        try:
            self.clipboard_clear()
            self.clipboard_append(code)
            self.status_var.set(f"已复制代码: {code}")
        except Exception as e:
            messagebox.showerror("错误", f"复制代码失败: {e}")

    def copy_row_info(self, values):
        try:
            cols = list(self.tree["columns"])
            row_str_parts = []
            for i, val in enumerate(values):
                col_id = cols[i] if i < len(cols) else f"col_{i}"
                col_name = self.tree.heading(col_id, "text") if i < len(cols) else col_id
                # 过滤掉股票名称列里的星星前缀
                val_str = str(val).strip()
                if col_id == "name" and val_str.startswith("★ "):
                    val_str = val_str[len("★ "):]
                row_str_parts.append(f"{col_name}:{val_str}")
            row_str = " | ".join(row_str_parts)
            
            self.clipboard_clear()
            self.clipboard_append(row_str)
            self.status_var.set(f"已复制行信息: {values[1] if len(values) > 1 else values[0]}")
        except Exception as e:
            messagebox.showerror("错误", f"复制行信息失败: {e}")

    def _on_diag_entry_right_click(self, event):
        try:
            clipboard_text = self.clipboard_get().strip()
        except Exception:
            return "break"
        if clipboard_text:
            import re
            match = re.search(r'\d{6}', clipboard_text)
            if match:
                code = match.group(0)
                self.diag_entry.delete(0, tk.END)
                self.diag_entry.insert(0, code)
                self._on_diagnose_click()
            else:
                self.status_var.set(f"⚠️ 右键粘贴失败：剪贴板中未找到6位数字代码")
        return "break"

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
            
        # 绑定退出事件
        self.bind("<Escape>", lambda e: self._on_close())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """窗口关闭处理：保存几何属性后销毁"""
        try:
            self.update_idletasks()  # 确保获取到最终计算的尺寸
            geom = self.geometry()
            if "+" in geom and not geom.startswith("1x1"):
                config_path = os.path.join(get_app_root(), "config", "standalone_tester_config.json")
                cfg = {}
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                cfg["editor_geometry"] = geom
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving editor geometry: {e}")
        finally:
            self.destroy()

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
        self.cond_frame.pack(fill="x")
        
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

        # --- 4. JSON 快速编辑面板（红圈空白区域）---
        json_sep = tk.Frame(self.right_frame, height=1, bg="#BDBDBD")
        json_sep.pack(fill="x", pady=(8, 0))

        json_header = tk.Frame(self.right_frame)
        json_header.pack(fill="x", pady=(4, 2))

        json_lbl = tk.Label(json_header, text="📋 JSON 快速编辑模式",
                            font=("Microsoft YaHei", 9, "bold"), fg="#00796B")
        json_lbl.pack(side="left")

        # 帮助提示
        help_lbl = tk.Label(json_header,
                            text="(直接粘贴或编辑 JSON → 点击 ✅ 应用；表单修改会自动刷新此处)",
                            font=("Microsoft YaHei", 8), fg="#757575")
        help_lbl.pack(side="left", padx=6)

        btn_apply_json = tk.Button(json_header, text="✅ 应用JSON",
                                   command=self._apply_json_to_form,
                                   bg="#00796B", fg="white",
                                   font=("Microsoft YaHei", 8, "bold"),
                                   padx=6, pady=2)
        btn_apply_json.pack(side="right", padx=2)

        btn_copy_json = tk.Button(json_header, text="📋 复制",
                                  command=self._copy_json_to_clipboard,
                                  font=("Microsoft YaHei", 8),
                                  padx=6, pady=2)
        btn_copy_json.pack(side="right", padx=2)

        btn_fmt_json = tk.Button(json_header, text="🔄 格式化",
                                 command=self._reformat_json_editor,
                                 font=("Microsoft YaHei", 8),
                                 padx=6, pady=2)
        btn_fmt_json.pack(side="right", padx=2)

        # JSON 文本编辑器（带滚动条）
        json_edit_frame = tk.Frame(self.right_frame)
        json_edit_frame.pack(fill="both", expand=True, pady=(0, 4))

        json_vsb = ttk.Scrollbar(json_edit_frame, orient="vertical")
        json_hsb = ttk.Scrollbar(json_edit_frame, orient="horizontal")
        self.json_editor = tk.Text(
            json_edit_frame,
            font=("Consolas", 9),
            bd=1, relief="solid",
            bg="#F5F5F5", fg="#1A237E",
            wrap="none",
            height=7,
            yscrollcommand=json_vsb.set,
            xscrollcommand=json_hsb.set
        )
        json_vsb.config(command=self.json_editor.yview)
        json_hsb.config(command=self.json_editor.xview)
        json_vsb.pack(side="right", fill="y")
        json_hsb.pack(side="bottom", fill="x")
        self.json_editor.pack(side="left", fill="both", expand=True)

        # --- 底部按钮区 ---
        bottom_bar = tk.Frame(self)
        bottom_bar.pack(fill="x", side="bottom", padx=10, pady=10)
        
        btn_val_all = tk.Button(bottom_bar, text="🔍 验证全部条件", command=self._validate_all, bg="#0288D1", fg="white", font=("Microsoft YaHei", 9, "bold"))
        btn_val_all.pack(side="left", padx=5)
        
        btn_cancel = tk.Button(bottom_bar, text="❌ 取消", command=self._on_close, font=("Microsoft YaHei", 9))
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
            
        # 同步各周期条件：保留所有配置的周期条件（无论勾选与否），只是通过 enabled 区分状态
        new_conditions = {}
        for period, row in self.cond_rows.items():
            expr = row['expr_var'].get().strip()
            is_checked = row['enable_var'].get()
            old_cond = strat.get('conditions', {}).get(period, {})
            
            if is_checked or expr or old_cond:
                new_conditions[period] = {
                    "filter": expr or old_cond.get('filter', 'close > ma5d'),
                    "weight": old_cond.get('weight', 1.0),
                    "enabled": is_checked
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

    def _on_select(self, event, sync=True):
        # 1. 同步当前正编辑的旧策略到内存
        if sync:
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
                is_enabled = cond.get('enabled', True)
                row['enable_var'].set(is_enabled)
                row['expr_var'].set(cond.get('filter', ''))
                if is_enabled:
                    row['entry'].config(state="normal")
                    row['btn_val'].config(state="normal")
                else:
                    row['entry'].config(state="disabled")
                    row['btn_val'].config(state="disabled")
            else:
                row['enable_var'].set(False)
                row['expr_var'].set('')
                row['entry'].config(state="disabled")
                row['btn_val'].config(state="disabled")
            row['status_lbl'].config(text="未验证", fg="gray")

        # 5. 刷新 JSON 编辑器（同步显示当前策略 JSON）
        self._refresh_json_editor(strat)

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
        # 表单变动时延迟刷新 JSON 编辑器（防高频抖动）
        if hasattr(self, '_json_refresh_id'):
            try:
                self.after_cancel(self._json_refresh_id)
            except Exception:
                pass
        self._json_refresh_id = self.after(600, self._refresh_json_from_form)

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
                
                # 重名检查并添加尾缀
                existing_names = [s['name'] for s in self.strategies] + [s['name'] for s in valid_strats]
                if name in existing_names:
                    original_name = name
                    counter = 1
                    while name in existing_names:
                        name = f"{original_name}_{counter}"
                        counter += 1
                
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

    # ===== JSON 编辑器相关方法 =====

    def _refresh_json_editor(self, strat):
        """将策略对象格式化为 JSON 并填入编辑器（只保留可编辑字段）"""
        if not hasattr(self, 'json_editor'):
            return
        display = {
            "name": strat.get("name", ""),
            "cross_mode": strat.get("cross_mode", "intersection"),
            "conditions": strat.get("conditions", {})
        }
        formatted = json.dumps(display, ensure_ascii=False, indent=2)
        self.json_editor.config(state="normal")
        self.json_editor.delete("1.0", tk.END)
        self.json_editor.insert("1.0", formatted)
        self._colorize_json_editor()

    def _refresh_json_from_form(self):
        """从表单读取当前状态并刷新 JSON 编辑器（表单 → JSON）"""
        if self.current_idx < 0 or self.current_idx >= len(self.strategies):
            return
        # 构造临时策略对象（不写回 self.strategies）
        strat = dict(self.strategies[self.current_idx])
        strat['name'] = self.name_var.get().strip() or "未命名策略"
        mode_val = self.mode_var.get()
        strat['cross_mode'] = 'union' if 'union' in mode_val else 'intersection'
        new_conditions = {}
        for period, row in self.cond_rows.items():
            if row['enable_var'].get():
                expr = row['expr_var'].get().strip()
                new_conditions[period] = {
                    "filter": expr,
                    "weight": strat.get('conditions', {}).get(period, {}).get('weight', 1.0)
                }
        strat['conditions'] = new_conditions
        self._refresh_json_editor(strat)

    def _colorize_json_editor(self):
        """简单语法高亮：字符串 key 绿色，字符串 value 蓝色，数字/布尔橙色"""
        if not hasattr(self, 'json_editor'):
            return
        editor = self.json_editor
        for tag in ("json_key", "json_str", "json_num"):
            editor.tag_remove(tag, "1.0", tk.END)
        editor.tag_config("json_key", foreground="#1B5E20")   # 深绿: key
        editor.tag_config("json_str", foreground="#1565C0")   # 深蓝: string value
        editor.tag_config("json_num", foreground="#E65100")   # 橙色: number/bool

        import re
        content = editor.get("1.0", tk.END)
        # JSON key ("xxx":)
        for m in re.finditer(r'"([^"]+)"\s*:', content):
            start = f"1.0 + {m.start()} chars"
            end = f"1.0 + {m.end(1)+1} chars"
            editor.tag_add("json_key", start, end)
        # string values
        for m in re.finditer(r':\s*("[^"]*")', content):
            vs = m.start(1); ve = m.end(1)
            editor.tag_add("json_str", f"1.0 + {vs} chars", f"1.0 + {ve} chars")
        # numbers / booleans
        for m in re.finditer(r':\s*(-?\d+\.?\d*|true|false|null)', content):
            vs = m.start(1); ve = m.end(1)
            editor.tag_add("json_num", f"1.0 + {vs} chars", f"1.0 + {ve} chars")

    def _apply_json_to_form(self):
        """将 JSON 编辑器内容解析并回填到表单（JSON → 表单）"""
        if not hasattr(self, 'json_editor'):
            return
        raw = self.json_editor.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("警告", "JSON 编辑器内容为空！", parent=self)
            return
        try:
            data = json.loads(raw)
        except Exception as e:
            messagebox.showerror("JSON 语法错误", f"解析失败：{e}", parent=self)
            return

        if not isinstance(data, dict):
            messagebox.showerror("格式错误", "根节点必须是 JSON 对象 {}。", parent=self)
            return

        # 先同步旧策略再覆盖
        self._sync_to_current_strategy()
        if self.current_idx < 0 or self.current_idx >= len(self.strategies):
            messagebox.showwarning("提示", "请先在左侧选择一个策略。", parent=self)
            return

        strat = self.strategies[self.current_idx]
        # 更新名称
        if "name" in data:
            new_name = str(data['name']).strip()
            if not new_name:
                new_name = strat['name']
            
            # 重名检查并添加尾缀（排除自身）
            existing_names = [s['name'] for i, s in enumerate(self.strategies) if i != self.current_idx]
            if new_name in existing_names:
                original_name = new_name
                counter = 1
                while new_name in existing_names:
                    new_name = f"{original_name}_{counter}"
                    counter += 1
            strat['name'] = new_name
        # 更新合并模式
        if "cross_mode" in data:
            strat['cross_mode'] = data['cross_mode'] if data['cross_mode'] in ('union', 'intersection') else 'intersection'
        # 更新条件
        if "conditions" in data and isinstance(data['conditions'], dict):
            new_conditions = {}
            for p, cond in data['conditions'].items():
                if p not in self.engine.SUPPORTED_PERIODS:
                    continue
                if isinstance(cond, dict):
                    flt = cond.get('filter', '').strip()
                    if flt:
                        new_conditions[p] = {
                            'filter': flt,
                            'weight': float(cond.get('weight', 1.0)),
                            'enabled': bool(cond.get('enabled', True))
                        }
                elif isinstance(cond, str) and cond.strip():
                    new_conditions[p] = {'filter': cond.strip(), 'weight': 1.0, 'enabled': True}
            if new_conditions:
                strat['conditions'] = new_conditions

        # 回填表单（重用 _on_select 逻辑）
        self._refresh_list()
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.current_idx)
        self._on_select(None, sync=False)
        messagebox.showinfo("应用成功", f"JSON 已成功解析并更新策略「{strat['name']}」！", parent=self)

    def _copy_json_to_clipboard(self):
        """复制 JSON 编辑器内容到系统剪贴板"""
        if not hasattr(self, 'json_editor'):
            return
        content = self.json_editor.get("1.0", tk.END).strip()
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("已复制", "JSON 内容已复制到剪贴板！", parent=self)

    def _reformat_json_editor(self):
        """格式化 JSON 编辑器中的内容（美化缩进）"""
        if not hasattr(self, 'json_editor'):
            return
        raw = self.json_editor.get("1.0", tk.END).strip()
        try:
            data = json.loads(raw)
            formatted = json.dumps(data, ensure_ascii=False, indent=2)
            self.json_editor.delete("1.0", tk.END)
            self.json_editor.insert("1.0", formatted)
            self._colorize_json_editor()
        except Exception as e:
            messagebox.showerror("格式化失败", f"JSON 语法错误：{e}", parent=self)

    # ===== 原有验证方法 =====

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
            self._on_close()
        else:
            messagebox.showerror("错误", "保存策略失败。")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = StandaloneMultiPeriodTester()
    app.mainloop()
