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

def show_toast(parent, message, duration=1800, bg="#E8F5E9", fg="#2E7D32"):
    """弹出一个自动隐藏的 toast 提示窗口，定位在 parent 窗口中央"""
    toast = tk.Toplevel(parent)
    toast.wm_overrideredirect(True)
    toast.attributes("-topmost", True)
    
    # 样式美化：绿色成功主题
    lbl = tk.Label(
        toast, text=message, bg=bg, fg=fg,
        font=("Microsoft YaHei", 10, "bold"), relief="solid", bd=1,
        padx=18, pady=10
    )
    lbl.pack()
    
    # 保证大小计算生效
    toast.update_idletasks()
    
    try:
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        
        tw = toast.winfo_width()
        th = toast.winfo_height()
        
        x = px + (pw - tw) // 2
        y = py + (ph - th) // 2
        
        x = max(0, x)
        y = max(0, y)
        toast.wm_geometry(f"+{x}+{y}")
    except Exception:
        try:
            screen_w = toast.winfo_screenwidth()
            screen_h = toast.winfo_screenheight()
            tw = toast.winfo_width()
            th = toast.winfo_height()
            x = (screen_w - tw) // 2
            y = (screen_h - th) // 2
            toast.wm_geometry(f"+{x}+{y}")
        except Exception:
            pass
            
    def destroy_toast():
        try:
            if toast.winfo_exists():
                toast.destroy()
        except Exception:
            pass
            
    parent.after(duration, destroy_toast)

class StandaloneMultiPeriodTester(_parent_class, TreeviewMixin):
    def __init__(self, master=None):
        if _parent_class == tk.Toplevel:
            super().__init__(master)
        else:
            super().__init__()
            
        # 统一计算 DPI 缩放比例
        if hasattr(self, 'master') and self.master and hasattr(self.master, 'scale_factor'):
            self.scale_factor = self.master.scale_factor
        else:
            from dpi_utils import get_windows_dpi_scale_factor
            self.scale_factor = get_windows_dpi_scale_factor()
            
        self.title("多周期联动策略筛选器")
        w = int(1100 * self.scale_factor)
        h = int(700 * self.scale_factor)
        self.geometry(f"{w}x{h}")
        
        self.engine = MultiPeriodStrategyEngine()
        self.strategies = self.engine.load_strategies()
        self.top_now = None
        self.dragon_monitor = None
        self._debug_mode = ("-log" in sys.argv and "debug" in sys.argv) or os.environ.get("APP_DEBUG") == "True"
        # 缓存时间戳：记录 top_now 和各周期数据的最后加载时间
        self._top_now_cache_ts = 0.0          # top_now 全市场数据缓存时间戳
        self._period_cache_ts: dict = {}      # {period: timestamp} 各周期数据缓存时间
        
        self.config_file = os.path.join(get_app_root(), "config", "standalone_tester_config.json")
        
        self._is_closing = False
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
        
        # 板块概念数据缓存与子窗口
        self._block_cache = {}
        self._concept_win = None
        self.concept_win = None
        
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

        try:
            from JSONData.sina_data import get_global_stock_code
            get_global_stock_code()
        except Exception as e:
            print(f"[MultiPeriodTester] Pre-initializing stock codes failed: {e}")



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
            
        self.custom_col_vars = {}
        self.custom_col_widgets = {}
        self.fixed_cols = ["Rank", "dff", "dff2", "dff3"]
        self.manual_col_pool = []
        
        # 🐉 龙头监控按钮
        self.btn_dragon_monitor = tk.Button(
            toolbar, text="🐉 龙头监控", 
            command=self.open_dragon_monitor,
            bg="#37474F", fg="white", font=("Microsoft YaHei", 9, "bold")
        )
        self.btn_dragon_monitor.pack(side="left", padx=5)

        tk.Label(toolbar, text="手动:").pack(side="left", padx=(10, 2))
        self.manual_col_entry = tk.Entry(toolbar, width=8)
        self.manual_col_entry.pack(side="left", padx=2)
        self.manual_col_entry.bind("<Return>", lambda e: self._add_manual_col())
        
        btn_add = tk.Button(toolbar, text="+", width=2, command=self._add_manual_col, bg="#E8F5E9", fg="#2E7D32", relief="groove")
        btn_add.pack(side="left", padx=1)
        btn_remove = tk.Button(toolbar, text="-", width=2, command=self._remove_manual_col, bg="#FFEBEE", fg="#C62828", relief="groove")
        btn_remove.pack(side="left", padx=1)

        # 自定义列下拉菜单
        self.custom_col_mbtn = tk.Menubutton(toolbar, text="⚙️ 自定义列 ▼", relief="raised", bd=1, bg="#ECEFF1")
        self.custom_col_mbtn.pack(side="left", padx=5)
        
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
        
        btn_dna = tk.Button(diagnose_frame, text="🧬 DNA审计", command=self._on_diagnose_dna_click, bg="#2E7D32", fg="white", font=("Microsoft YaHei", 9), padx=5, pady=1)
        btn_dna.pack(side="left", padx=2)

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
        
        # --- Concept Wrapper Frame ---
        self.concept_wrapper_frame = tk.Frame(self, bg="#f7f7f7")
        self.concept_wrapper_frame.pack(fill="x", padx=8, pady=(2, 4))
        
        self.lbl_category_title = tk.Label(
            self.concept_wrapper_frame,
            text="当前概念:",
            font=("Microsoft YaHei", 9, "bold"),
            fg="green",
            bg="#f7f7f7",
            cursor="hand2"
        )
        self.lbl_category_title.pack(side="left", padx=(0, 4))
        self.lbl_category_title.bind("<Button-1>", lambda e: self.show_concept_detail_window())
        
        self.dynamic_concepts_frame = tk.Frame(self.concept_wrapper_frame, bg="#f7f7f7")
        self.dynamic_concepts_frame.pack(side="left", fill="both", expand=True)
        
        self.lbl_empty_concept = tk.Label(
            self.dynamic_concepts_frame,
            text="暂无板块数据",
            font=("Microsoft YaHei", 9, "bold"),
            fg="gray",
            bg="#f7f7f7"
        )
        self.lbl_empty_concept.pack(side="left")

        # --- Results Treeview ---
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        style = ttk.Style()
        # 避免污染全局样式，使用专用样式名，并根据缩放因子动态设置行高
        style_name = "MultiPeriod.Treeview"
        style.configure(style_name, rowheight=int(25 * self.scale_factor))
        
        self.tree = ttk.Treeview(tree_frame, show="headings", style=style_name)
        
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
            # ⚡ [PERF] 对大数据量进行头部采样比对（只取前 100 行），避免全表数千行进行 pandas series 向量化计算导致严重的 CPU 阻塞与 UI 卡顿
            sample_df = df.head(100)
            p0 = active_periods[0]
            col0 = f"{col_name}_{p0}"
            if col0 in sample_df.columns:
                is_all_same = True
                for p in active_periods[1:]:
                    col_p = f"{col_name}_{p}"
                    if col_p in sample_df.columns:
                        series0 = sample_df[col0]
                        series_p = sample_df[col_p]
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
            "ratio": "换手"
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
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        if not active_periods:
            for item in self.tree.get_children():
                self.tree.delete(item)
            return
        self.run_filter(force_reload=False)

    def _adjust_column_widths(self):
        scale = getattr(self, "scale_factor", 1.0)
        for col in self.tree["columns"]:
            header_text = self.tree.heading(col, "text")
            
            def get_text_width(text):
                if not text:
                    return 0
                w = 0
                for char in str(text):
                    if '\u4e00' <= char <= '\u9fff':
                        w += 12 * scale
                    else:
                        w += 6.5 * scale
                return int(w) + int(8 * scale)

            # 极限优化数据列宽：不再受限于长列名，主要由单元格内容决定，配合鼠标悬停 Tooltip 查阅
            data_max_w = 0
            measured_items = self.tree.get_children()[:15]
            for item in measured_items:
                val = self.tree.set(item, col)
                data_max_w = max(data_max_w, get_text_width(val))
                
            header_w = get_text_width(header_text)
            col_lower = col.lower()
            
            if col == "name":
                final_w = max(60 * scale, min(data_max_w, 95 * scale))
            elif col == "code":
                final_w = 55 * scale
            elif any(x in col_lower for x in ["red", "win"]):
                # 胜率、红盘数等短整型数据列，极限压缩
                final_w = 40 * scale
            elif "strong_struct" in col_lower:
                # 强结构分数据一般为三位数值（如 102.7）
                final_w = 55 * scale
            elif "slope" in col_lower:
                # 斜率数据
                final_w = 52 * scale
            elif "dff" in col_lower:
                # 差值数据
                final_w = 50 * scale
            elif col_lower in ["price", "trade", "now"]:
                final_w = 50 * scale
            elif col_lower == "percent":
                final_w = 55 * scale
            elif col_lower == "ratio":
                final_w = 50 * scale
            elif col_lower in ["d", "2d", "w", "m", "d_chk", "2d_chk", "w_chk", "m_chk"] or "周期" in header_text:
                # 参与勾选列
                final_w = 38 * scale
            else:
                # 默认列宽：取 数据最大宽+10 和 列头宽 的较小值，并限制在 32 ~ 80px 之间
                final_w = max(35 * scale, min(data_max_w + 10 * scale, min(header_w, 85 * scale)))
                
            self.tree.column(col, width=int(final_w), minwidth=int(20 * scale), stretch=True)
                
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
        self.tree.yview_moveto(0)

    def _on_tree_select(self, event):
        if self._link_after_id:
            self.after_cancel(self._link_after_id)
        self._link_after_id = self.after(100, self._do_linkage)

    def _on_tree_motion(self, event):
        self._on_tree_motion_impl(event, self.tree)

    def _on_tree_motion_impl(self, event, tree):
        region = tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id = tree.identify_column(event.x)
            if col_id:
                try:
                    col_idx = int(col_id.replace('#', '')) - 1
                    columns = tree['columns']
                    if 0 <= col_idx < len(columns):
                        col_name = columns[col_idx]
                        if getattr(self, 'current_tooltip_col', None) != col_name:
                            # 尝试获取友好的表头显示文字作为提示
                            header_text = tree.heading(col_name, "text")
                            self._show_tree_tooltip(event.x_root, event.y_root + 20, header_text)
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

    def _do_linkage(self, code=None):
        if code is None:
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
        
        # 同步填入底部的诊断输入框
        if hasattr(self, "diag_entry") and self.diag_entry.winfo_exists():
            self.diag_entry.delete(0, tk.END)
            self.diag_entry.insert(0, code)
        
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

    def on_code_click(self, code, date=None):
        """DNA 审计窗口点击个股时，回传多周期主界面以触发 TDX、Visualizer 联动与诊断输入框填充"""
        if not code:
            return
        code = str(code).strip().zfill(6)
        self._do_linkage(code)

    def _update_status(self, text):
        """线程安全的底部状态日志更新（由 after(0,...) 保证在主线程执行，不调用 update_idletasks）"""
        if getattr(self, "_is_closing", False):
            return
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
            if hasattr(self.engine, "lock"):
                with self.engine.lock:
                    self.engine._period_dfs.clear()
            else:
                self.engine._period_dfs.clear()
            self._period_cache_ts.clear()
            if hasattr(self, "_block_cache"):
                self._block_cache.clear()
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
                    if hasattr(self.engine, "lock"):
                        with self.engine.lock:
                            self.engine._period_dfs.pop(p, None)
                    else:
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
            # ── 加载全市场行情 top_now（只读，不触发 DD 写回，防止损坏 MultiIndex HDF5）──
            if self.top_now is None:
                self.after(0, self._update_status, "正在获取全市场实时行情...")
                # 使用只读路径直接获取 sina 全市场数据，完全跳过
                # get_market_price_sina_dd_realTime 的 write_hdf_db 写回逻辑，
                # 避免与主系统后台写进程竞争 g:\sina_MultiIndex_data.h5
                from JSONData import sina_data
                _sina = sina_data.Sina(readonly=True)
                self.top_now = _sina.all
                if self.top_now is not None and not self.top_now.empty and 'ratio' not in self.top_now.columns:
                    try:
                        from JSONData import realdatajson as rl
                        from JohnsonUtil import commonTips as cct
                        dd = rl.get_sina_Market_json('all')
                        if isinstance(dd, pd.DataFrame) and 'ratio' in dd.columns:
                            self.top_now = cct.combine_dataFrame(self.top_now, dd.loc[:, ['name', 'ratio']])
                    except Exception as e:
                        print(f"[MultiPeriodTester] Fallback ratio recovery failed: {e}")
                
                if self.top_now is None or self.top_now.empty:
                    # fallback: 仍走 getSinaAlldf 但明确只读标志
                    self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType, readonly=True)
                self._top_now_cache_ts = time.time()
            # ── 逐周期加载 ─────────────────────────────────────
            for period in active_periods:
                cached = False
                if hasattr(self.engine, "lock"):
                    with self.engine.lock:
                        cached = (
                            period in self.engine._period_dfs
                            and not self.engine._period_dfs[period].empty
                            and self._is_cache_valid(self._period_cache_ts.get(period, 0.0))
                        )
                else:
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
                    if hasattr(self.engine, "lock"):
                        with self.engine.lock:
                            self.engine._period_dfs.pop(period, None)
                    else:
                        self.engine._period_dfs.pop(period, None)
                    self.engine.load_period_data(period, self.top_now)
                    self._period_cache_ts[period] = time.time()
                    # 检查加载后是否为缺失周期，及时给用户提示
                    if period in self.engine._missing_periods:
                        reason = self.engine._missing_periods[period]
                        self.after(0, self._update_status,
                                   f"⚠️ [{period}] 数据不可用({reason})，策略将自适应跳过此周期过滤")

            self.after(0, self._update_status, "🔍 正在执行跨周期交叉验证...")
            result_df = self.engine.evaluate_strategy(strat_config, active_periods)
            
            # 在后台线程中生成 flat_df 缓存，彻底释放主线程
            flat_df = self._build_flat_df(result_df)
            
            elapsed = time.time() - start_time
            self.last_result_df = result_df
            self.last_elapsed = elapsed
            self.after(0, self._show_results, result_df, elapsed, flat_df)
        except Exception as e:
            import traceback
            self.after(0, self._update_status, f"❌ 错误: {e}")
            print(f"[MultiPeriodTester] _worker exception:\n{traceback.format_exc()}")
            
    def _show_results(self, df, elapsed, flat_df=None):
        if getattr(self, "_is_closing", False):
            return
        self._last_selected_code = None
        # 同步给 query_manager 完整的宽表数据，以支持在 history 弹窗里进行“测试”或“双击”统计
        if flat_df is None:
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
            self.update_concept_ranking(None)
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
            self.update_concept_ranking(None)
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
            
        # ⚡ [PERF] 预先计算每个自定义列需要展示的周期列表，避免在下面的 iterrows O(N) 循环中重复执行高成本的 _get_display_periods_for_custom_col 导致 O(N^2) 卡顿
        custom_disp_periods = {}
        for c in active_customs:
            custom_disp_periods[c] = self._get_display_periods_for_custom_col(c, active_periods, filtered_df)
            
        for code, row in filtered_df.iterrows():
            name = row.get('name', '--')
            price = round(row.get('close', 0), 2)
            percent = round(row.get('percent', 0), 2)
            vol = round(row.get('volume', 0), 2)
            ratio = round(row.get('ratio', 0), 2)
            
            # 顺便填充概念缓存
            category_str = row.get('category', row.get('block', ''))
            if not category_str or str(category_str).strip() == 'nan':
                if self.top_now is not None and code in self.top_now.index:
                    r = self.top_now.loc[code]
                    if isinstance(r, pd.DataFrame):
                        r = r.iloc[0]
                    category_str = r.get('category', r.get('block', ''))
            if pd.notna(category_str) and str(category_str).strip() not in ('', 'nan', '--'):
                self._block_cache[code] = str(category_str).strip()
            
            is_fav = code in fav_stocks
            display_name = f"★ {name}" if is_fav else name
            
            values = [code, display_name, price, percent, vol, ratio]
            
            for c in active_customs:
                disp_periods = custom_disp_periods[c]
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
        self.tree.yview_moveto(0)
        
        # 统计并刷新“当前概念”
        self.update_concept_ranking(filtered_df)

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
        
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        flat_df = df.copy()
        
        for period in active_periods:
            df_p = self.engine._period_dfs.get(period)
            if df_p is not None and not df_p.empty:
                # 过滤掉 code, name 等主表已有的字段
                cols_to_join = [c for c in df_p.columns if c not in ('code', 'name')]
                if cols_to_join:
                    # 去重保留首个，防止重复索引导致行数膨胀
                    df_p_sub = df_p[cols_to_join]
                    df_p_sub = df_p_sub[~df_p_sub.index.duplicated(keep='first')]
                    # 重命名列加上后缀，例如 close -> close_d
                    df_p_sub = df_p_sub.rename(columns={c: f"{c}_{period}" for c in cols_to_join})
                    # 矢量化连接
                    flat_df = flat_df.join(df_p_sub, how='left')
                    
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
                df_p = None
                if hasattr(self.engine, "lock"):
                    with self.engine.lock:
                        raw_df = self.engine._period_dfs.get(p)
                        if raw_df is not None and not raw_df.empty:
                            df_p = raw_df.copy()
                else:
                    raw_df = self.engine._period_dfs.get(p)
                    if raw_df is not None and not raw_df.empty:
                        df_p = raw_df.copy()
                if df_p is not None and code in df_p.index:
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
            self.stats_lbl_periods.config(text="暂无数据")
            self.stats_lbl_final.config(text="")
            return

        parts = []
        missing = []
        for p in self.engine.SUPPORTED_PERIODS:
            if p not in stats["periods"]:
                continue
            d = stats["periods"][p]
            if d.get("status") == "NO_DATA":
                parts.append(f"⚠️{p}")
                missing.append(p)
            else:
                parts.append(f"{p}:{d['pass']}/{d['total']}")

        self.stats_lbl_periods.config(text="  ".join(parts) if parts else "")

        final = stats["final"]
        mode = "∩" if final["mode"] == "intersection" else "∪"
        txt = f"{mode} {final['pass']}只/{final['total']} ({final['ratio']:.2f}%)"
        if missing:
            txt += f"  ⚠️{','.join(missing)}无数据"
        self.stats_lbl_final.config(text=txt)

    def _recreate_custom_col_checkboxes(self):
        if hasattr(self, "custom_col_menu"):
            try:
                self.custom_col_menu.destroy()
            except Exception:
                pass
        
        self.custom_col_menu = tk.Menu(self.custom_col_mbtn, tearoff=False)
        self.custom_col_mbtn.config(menu=self.custom_col_menu)
        
        old_vars = self.custom_col_vars.copy()
        self.custom_col_vars.clear()
        self.custom_col_widgets.clear()
        
        all_cols = self.fixed_cols + [c for c in self.manual_col_pool if c not in self.fixed_cols]
        for c in all_cols:
            if c in old_vars:
                var = old_vars[c]
            else:
                var = tk.BooleanVar(value=False)
            
            self.custom_col_menu.add_checkbutton(
                label=c,
                variable=var,
                command=self._on_custom_col_changed
            )
            self.custom_col_vars[c] = var

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
        self._is_closing = True
        self._save_state()
        if getattr(self, "query_manager", None) is not None:
            try:
                self.query_manager.save_search_history()
            except Exception as e:
                print(f"Error saving query history on close: {e}")
                
        if hasattr(self, "dragon_monitor") and self.dragon_monitor is not None:
            try:
                self.dragon_monitor.destroy()
            except Exception:
                pass
            self.dragon_monitor = None

        # 取消可能存在的 linkage 定时器
        if getattr(self, "_link_after_id", None):
            try:
                self.after_cancel(self._link_after_id)
            except Exception:
                pass
            self._link_after_id = None

        # 清除板块概念详情窗口
        if getattr(self, "detail_win", None) is not None:
            try:
                if self.detail_win.winfo_exists():
                    self.detail_win.destroy()
            except Exception:
                pass
            self.detail_win = None
            self.txt_widget = None

        if getattr(self, "_concept_win", None) is not None:
            try:
                if self._concept_win.winfo_exists():
                    self._concept_win.destroy()
            except Exception:
                pass
            self._concept_win = None

        if getattr(self, "concept_win", None) is not None:
            try:
                if self.concept_win.winfo_exists():
                    self.concept_win.destroy()
            except Exception:
                pass
            self.concept_win = None

        # 清理多周期引擎中的 pandas 缓存与实例
        if hasattr(self, "engine") and self.engine is not None:
            try:
                if hasattr(self.engine, "_period_dfs"):
                    if hasattr(self.engine, "lock"):
                        with self.engine.lock:
                            self.engine._period_dfs.clear()
                    else:
                        self.engine._period_dfs.clear()
                if hasattr(self.engine, "_missing_periods"):
                    self.engine._missing_periods.clear()
            except Exception:
                pass
            self.engine = None

        # 显式释放大 DataFrame 内存
        self.top_now = None
        self.last_result_df = None
        self._last_flat_df = None

        # 彻底销毁窗口，不管是 tk.Tk 还是 tk.Toplevel
        try:
            self.destroy()
        except Exception:
            pass

        # 强力触发垃圾回收
        import gc
        gc.collect()

    def open_dragon_monitor(self):
        if getattr(self, "_debug_mode", False):
            print(f"[MultiPeriodTester] open_dragon_monitor() triggered. Current self.dragon_monitor: {getattr(self, 'dragon_monitor', None)}")
        if hasattr(self, "dragon_monitor") and self.dragon_monitor is not None:
            try:
                exists = self.dragon_monitor.winfo_exists()
                if exists:
                    # 折叠态：弹出窗口而非关闭
                    if getattr(self.dragon_monitor, 'collapsed', False):
                        self.dragon_monitor._expand()
                        self.dragon_monitor.lift()
                        return
                    # 展开态：再次点击才关闭
                    self.dragon_monitor.destroy()
                    self.dragon_monitor = None
                    return
            except Exception as e:
                if getattr(self, "_debug_mode", False):
                    print(f"[MultiPeriodTester] Error checking/destroying existing dragon_monitor: {e}")
                self.dragon_monitor = None

        if getattr(self, "_debug_mode", False):
            print(f"[MultiPeriodTester] Creating new TkDragonLeaderMonitor instance.")
        try:
            self.dragon_monitor = TkDragonLeaderMonitor(self)
            if getattr(self, "_debug_mode", False):
                print(f"[MultiPeriodTester] Successfully created TkDragonLeaderMonitor.")
        except Exception as e:
            print(f"[MultiPeriodTester] Error opening dragon monitor: {e}")
            import traceback
            traceback.print_exc()
            from tkinter import messagebox
            messagebox.showerror("错误", f"无法启动龙头监控器:\n{e}")

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
                if self.winfo_exists() and not getattr(self, "_is_closing", False):
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

    def _get_audit_end_date(self):
        """尝试获取审计的截止日期，对齐主窗口"""
        if hasattr(self, 'master') and self.master:
            if hasattr(self.master, '_get_audit_end_date'):
                try:
                    return self.master._get_audit_end_date()
                except Exception:
                    pass
            if hasattr(self.master, 'current_date'):
                t_str = getattr(self.master, 'current_date', None)
                if t_str:
                    return str(t_str).replace("-", "")
        return None

    def _run_dna_audit_batch(self, code_to_name, end_date=None, resample='d'):
        from backtest_feature_auditor import audit_multiple_codes, show_dna_audit_report_window
        from tkinter import messagebox
        import threading
        
        # 🚀 [NEW] 防重入保护
        if getattr(self, '_dna_audit_running', False):
            return
        self._dna_audit_running = True
        
        codes = list(code_to_name.keys())
        if not codes:
            self._dna_audit_running = False
            return
        
        # 弹一个带进度条的提示
        top = tk.Toplevel(self)
        top.withdraw() 
        top.attributes("-alpha", 0.0) 
        top.title("🧬 DNA 审计中...")
        
        # 界面美化
        top.configure(bg='#f8f9fa')
        content_frame = tk.Frame(top, bg='#f8f9fa', padx=15, pady=15)
        content_frame.pack(expand=True, fill='both')
        
        msg_label = tk.Label(content_frame, text=f"正在审计 {len(codes)} 只个股...", 
                            font=("微软雅黑", 9), bg='#f8f9fa', fg='#333')
        msg_label.pack(pady=(0, 10))
        
        # 进度条
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(content_frame, variable=progress_var, maximum=len(codes), mode='determinate', length=280)
        progress_bar.pack(pady=5)
        
        status_label = tk.Label(content_frame, text="初始化中...", font=("微软雅黑", 8), bg='#f8f9fa', fg='#666')
        status_label.pack()
        
        # 初始化展示位置
        w, h = 320, 140
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.attributes("-topmost", True)
        top.deiconify() # 直接显示
        
        def progress_cb(curr, total, msg):
            """跨线程进度回调"""
            def _update():
                try:
                    # 🛡️ [GUARD] 若窗口已被用户关闭，静默退出，防止 TclError: invalid command name
                    if not top.winfo_exists(): return
                    progress_var.set(curr)
                    status_label.config(text=msg)
                    if curr >= total:
                        status_label.config(text="✅ 正在呼出报告...")
                except tk.TclError:
                    pass # 窗体已销毁
                    
            self.after(0, _update)

        def run_task():
            try:
                # 调用批量接口
                summaries = audit_multiple_codes(codes, 
                                               end_date=end_date, 
                                               code_to_name=code_to_name,
                                               progress_callback=progress_cb,
                                               resample=resample)
                # 切回主线程展示
                def _show_report():
                    if top.winfo_exists():
                        top.destroy()
                    
                    # 🚀 [NEW] 支持窗口复用
                    if hasattr(self, '_dna_audit_win') and self._dna_audit_win and self._dna_audit_win.winfo_exists():
                        self._dna_audit_win.update_report(summaries, end_date=end_date, resample=resample)
                    else:
                        self._dna_audit_win = show_dna_audit_report_window(summaries, parent=self, end_date=end_date, resample=resample)
                
                self.after(0, _show_report)
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                self.after(0, lambda: [top.destroy() if top.winfo_exists() else None, messagebox.showerror("DNA 审计出错", str(e), parent=self)])
            finally:
                self._dna_audit_running = False
                
        threading.Thread(target=run_task, daemon=True).start()

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
            
        columns = tree["columns"]
        try:
            code_idx = columns.index("code")
            name_idx = columns.index("name")
        except ValueError:
            code_idx = 0
            name_idx = 1
            
        if len(values) <= max(code_idx, name_idx):
            return

        code = str(values[code_idx]).strip().zfill(6)
        name = str(values[name_idx]).strip()
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
        
        # DNA 审计子菜单
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        PERIOD_ORDER = {'d': 1, '2d': 2, '3d': 3, 'w': 4, 'm': 5, '45d': 6, '3M': 7}
        sorted_periods = sorted(active_periods, key=lambda x: PERIOD_ORDER.get(x, 99))
        min_period = sorted_periods[0] if sorted_periods else 'd'
        
        dna_menu = tk.Menu(menu, tearoff=0)
        
        # 🚀 获取当前选择个股以及在Treeview列表中排在其后面的前20个个股（总共最多21个）
        children = tree.get_children()
        try:
            curr_idx = children.index(item_id)
            target_items = children[curr_idx:curr_idx + 21]
        except ValueError:
            target_items = [item_id]
            
        code_to_name = {}
        for t_item in target_items:
            t_values = tree.item(t_item, "values")
            if t_values and len(t_values) > max(code_idx, name_idx):
                t_code = str(t_values[code_idx]).strip().zfill(6)
                t_name = str(t_values[name_idx]).strip()
                if t_name.startswith("★ "):
                    t_name = t_name[len("★ "):]
                code_to_name[t_code] = t_name
        
        # 默认最小周期审计
        dna_menu.add_command(
            label=f"🧬 运行 DNA 审计 ({len(code_to_name)}只, 周期: {min_period.upper()})",
            command=lambda: self._run_dna_audit_batch(code_to_name, end_date=self._get_audit_end_date(), resample=min_period)
        )
        
        if len(sorted_periods) > 1:
            dna_menu.add_separator()
            for p in sorted_periods:
                dna_menu.add_command(
                    label=f"指定周期: {p.upper()} ({len(code_to_name)}只)",
                    command=lambda period=p: self._run_dna_audit_batch(code_to_name, end_date=self._get_audit_end_date(), resample=period)
                )
        else:
            # 如果没勾选其他，列出所有可用周期
            dna_menu.add_separator()
            all_supported = ['d', '2d', '3d', 'w', 'm', '45d', '3M']
            for p in all_supported:
                dna_menu.add_command(
                    label=f"指定周期: {p.upper()} ({len(code_to_name)}只)",
                    command=lambda period=p: self._run_dna_audit_batch(code_to_name, end_date=self._get_audit_end_date(), resample=period)
                )
        
        menu.add_cascade(label=f"🧬 DNA 专项审计 (默认: {min_period.upper()})", menu=dna_menu)
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

    def _on_diagnose_dna_click(self):
        code = self.diag_entry.get().strip()
        if not code:
            from tkinter import messagebox
            messagebox.showwarning("警告", "请输入要审计的股票代码！")
            return
        code = "".join(x for x in code if x.isdigit()).zfill(6)
        
        # 尝试在主 Treeview 里面查找该股票所在的 index 并执行 "所选 + 后续最多20只" 批量审计
        children = self.tree.get_children()
        
        # 确定代码列和名称列在 Treeview 中的具体位置
        cols = list(self.tree["columns"])
        code_idx = cols.index("code") if "code" in cols else 0
        name_idx = cols.index("name") if "name" in cols else 1
        
        found_idx = -1
        for idx, item_id in enumerate(children):
            vals = self.tree.item(item_id, "values")
            if vals and len(vals) > code_idx:
                c = str(vals[code_idx]).strip().zfill(6)
                if c == code:
                    found_idx = idx
                    break
                    
        code_to_name = {}
        if found_idx != -1:
            # 找到了，切片获取该股及在其后面的前 20 个个股（共计最多 21 只）
            selected_items = children[found_idx:found_idx + 21]
            for item_id in selected_items:
                vals = self.tree.item(item_id, "values")
                if vals and len(vals) > max(code_idx, name_idx):
                    c = str(vals[code_idx]).strip().zfill(6)
                    n = str(vals[name_idx]).strip()
                    if n.startswith("★ "):
                        n = n[len("★ "):]
                    code_to_name[c] = n
        else:
            # 列表未包含该代码（手动输入列表外的个股），降级仅审计当前个股本身
            name = None
            if self.top_now is not None and code in self.top_now.index:
                name = self.top_now.loc[code, 'name']
            else:
                from backtest_feature_auditor import NAME_CACHE
                name = NAME_CACHE.get(code, code)
            code_to_name[code] = name
            
        active_periods = [p for p, var in self.period_vars.items() if var.get()]
        PERIOD_ORDER = {'d': 1, '2d': 2, '3d': 3, 'w': 4, 'm': 5, '45d': 6, '3M': 7}
        sorted_periods = sorted(active_periods, key=lambda x: PERIOD_ORDER.get(x, 99))
        min_period = sorted_periods[0] if sorted_periods else 'd'
        
        self._run_dna_audit_batch(code_to_name, end_date=self._get_audit_end_date(), resample=min_period)

    def _on_diagnose_click(self):
        code = self.diag_entry.get().strip()
        if not code:
            from tkinter import messagebox
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
            has_period = False
            if hasattr(self.engine, "lock"):
                with self.engine.lock:
                    has_period = period in self.engine._period_dfs and not self.engine._period_dfs[period].empty
            else:
                has_period = period in self.engine._period_dfs and not self.engine._period_dfs[period].empty
            if not has_period:
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
            df_p = None
            if hasattr(self.engine, "lock"):
                with self.engine.lock:
                    raw_df = self.engine._period_dfs.get(period)
                    if raw_df is not None and not raw_df.empty:
                        df_p = raw_df.copy()
            else:
                raw_df = self.engine._period_dfs.get(period)
                if raw_df is not None and not raw_df.empty:
                    df_p = raw_df.copy()
            if df_p is not None:
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

    def _normalize_concept_name(self, name):
        """标准化板块概念名称"""
        if not name:
            return ""
        import re
        # 将中文括号标准化为英文括号并移除两侧空白
        n = str(name).replace('（', '(').replace('）', ')').strip()
        # 去除诸如 " (15只)" 或 " (15)" 的数量后缀
        n = re.sub(r'\s*\(\d+只?\)\s*$', '', n)
        return n

    def _is_noise_concept(self, name_str):
        """识别噪音板块概念并进行过滤"""
        NOISE_CONCEPTS = {
            "深股通", "港股通", "沪股通", "国企改革", "央企国企改革", "融资融券", "标普道琼斯A股", 
            "富时罗素概念股", "MSCI概念", "转融券标的", "机构重仓", "证金持股", "汇金持股", 
            "预盈预增", "破净股", "ST板块", "参股新三板", "创业板设", "科创板", "地方国企改革", 
            "央企改革", "壳资源", "新股与次新股", "昨日涨停", "昨日连板", "百元股", "中字头",
            "低价股", "破发股", "外资背景", "QFII重仓", "社保重仓", "核心资产", "新三板",
            "深成指股", "沪深300股", "上证180股", "上证50股", "创业300股", "中证500", "成分股",
            "高送转", "含可转债", "国家队持股", "地方政府平台", "央企控股", "军工改革",
            "中报", "中报送转", "季报", "年报", "一季报", "三季报", "业绩预增", "预增", "预亏",
            "预降预亏", "送转股份", "业绩补偿"
        }
        if name_str in NOISE_CONCEPTS:
            return True
        for keyword in ("改革", "股通", "成指", "重仓", "持股", "融资", "昨日", "送转", "转债", "指数", "成分", "中报", "预增", "业绩", "季报", "年报", "预盈", "预亏"):
            if keyword in name_str:
                return True
        return False

    def _get_stock_category(self, code, row=None):
        """获取个股的板块概念，优先使用传入的 row 字段，其次从 _block_cache 中获取"""
        if row is not None:
            if 'category' in row and pd.notna(row['category']):
                val = str(row['category']).strip()
                if val and val != "nan" and val != "--":
                    return val
            if 'block' in row and pd.notna(row['block']):
                val = str(row['block']).strip()
                if val and val != "nan" and val != "--":
                    return val

        if not hasattr(self, "_block_cache") or not self._block_cache:
            self._block_cache = {}
            active_periods = [p for p, var in self.period_vars.items() if var.get()]
            for p in active_periods:
                df_p = None
                if hasattr(self.engine, "lock"):
                    with self.engine.lock:
                        raw_df = self.engine._period_dfs.get(p)
                        if raw_df is not None and not raw_df.empty:
                            df_p = raw_df.copy()
                else:
                    raw_df = self.engine._period_dfs.get(p)
                    if raw_df is not None and not raw_df.empty:
                        df_p = raw_df.copy()
                if df_p is not None:
                    for c, r in df_p.iterrows():
                        cat = r.get('category', r.get('block', ''))
                        if pd.notna(cat) and str(cat).strip() not in ('', 'nan', '--'):
                            self._block_cache[c] = str(cat).strip()

        val = self._block_cache.get(code, '')
        if val and val != "nan" and val != "--":
            return val
            
        if self.top_now is not None and code in self.top_now.index:
            r = self.top_now.loc[code]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            cat = r.get('category', r.get('block', ''))
            if pd.notna(cat) and str(cat).strip() not in ('', 'nan', '--'):
                self._block_cache[code] = str(cat).strip()
                return str(cat).strip()

        return ""

    def update_concept_ranking(self, df_filtered):
        """统计最终过滤后的数据中板块概念的频次与分布，并更新顶部‘当前概念’显示区"""
        for widget in self.dynamic_concepts_frame.winfo_children():
            widget.destroy()

        if df_filtered is None or df_filtered.empty:
            self.lbl_empty_concept.pack(side="left")
            return

        import re
        from collections import Counter
        
        concept_counter = Counter()
        for code, row in df_filtered.iterrows():
            category = self._get_stock_category(code, row)
            if not category:
                continue
            
            cats = [c.strip() for c in re.split(r'[;；,，/|]', category) if c.strip()]
            for cat in cats:
                norm_cat = self._normalize_concept_name(cat)
                if not norm_cat:
                    continue
                if self._is_noise_concept(norm_cat):
                    continue
                try:
                    from stock_logic_utils import is_generic_concept
                    if is_generic_concept(norm_cat):
                        continue
                except Exception:
                    pass
                concept_counter[norm_cat] += 1

        top_concepts = concept_counter.most_common(10)
        
        if not top_concepts:
            self.lbl_empty_concept.pack(side="left")
            return

        self.lbl_empty_concept.pack_forget()

        for cat_name, count in top_concepts:
            lbl_text = f"{cat_name}({count})"
            lbl = tk.Label(
                self.dynamic_concepts_frame,
                text=lbl_text,
                font=("Microsoft YaHei", 9, "bold"),
                fg="#1A73E8",
                bg="#E8F0FE",
                padx=6,
                pady=2,
                cursor="hand2"
            )
            lbl.pack(side="left", padx=3)
            lbl.bind("<Button-1>", lambda e, name=cat_name: self.show_concept_top10_window(name))

    def show_concept_detail_window(self):
        """弹出详细概念异动窗口"""
        if self._last_flat_df is None or self._last_flat_df.empty:
            messagebox.showinfo("提示", "当前无筛选数据，请先执行筛选。")
            return

        import re
        from collections import Counter
        
        concept_counter = Counter()
        for code, row in self._last_flat_df.iterrows():
            category = self._get_stock_category(code, row)
            if not category:
                continue
            cats = [c.strip() for c in re.split(r'[;；,，/|]', category) if c.strip()]
            for cat in cats:
                norm_cat = self._normalize_concept_name(cat)
                if not norm_cat:
                    continue
                if self._is_noise_concept(norm_cat):
                    continue
                try:
                    from stock_logic_utils import is_generic_concept
                    if is_generic_concept(norm_cat):
                        continue
                except Exception:
                    pass
                concept_counter[norm_cat] += 1

        all_concepts = concept_counter.most_common()
        if not all_concepts:
            messagebox.showinfo("提示", "当前筛选结果中没有包含板块概念信息。")
            return

        # 预构建 板块->代码列表 索引，供点击板块时 O(1) 查找（避免重复遍历卡顿）
        concept_to_codes = {}
        for code, row in self._last_flat_df.iterrows():
            category = self._get_stock_category(code, row)
            if not category:
                continue
            cats = [c.strip() for c in re.split(r'[;；,，/|]', category) if c.strip()]
            for cat in cats:
                norm_cat = self._normalize_concept_name(cat)
                if norm_cat:
                    concept_to_codes.setdefault(norm_cat, []).append(code)
        self._concept_index = concept_to_codes

        if getattr(self, "_concept_win", None):
            try:
                if self._concept_win.winfo_exists():
                    self._concept_win.lift()
                    self._concept_win.focus_force()
                    self.update_concept_detail_content(all_concepts)
                    return
            except Exception:
                pass
            self._concept_win = None

        win = tk.Toplevel(self)
        self._concept_win = win
        win.title("概念板块统计详情")
        
        saved_geo = self.ui_state.get('concept_detail_window_geometry', '300x500')
        win.geometry(saved_geo)

        def _save_concept_detail_win_geo(event):
            if win.winfo_exists():
                try:
                    self.ui_state["concept_detail_window_geometry"] = win.winfo_geometry()
                    self._save_state()
                except Exception:
                    pass
        win.bind("<Configure>", _save_concept_detail_win_geo)
        win.bind("<Escape>", lambda e: win.destroy())

        frame = tk.Frame(win, bg="white")
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        canvas = tk.Canvas(frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="white")

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<MouseWheel>", on_mousewheel)

        win._content_frame = scroll_frame
        
        self.update_concept_detail_content(all_concepts)

    def update_concept_detail_content(self, all_concepts):
        if not getattr(self, "_concept_win", None) or not self._concept_win.winfo_exists():
            return
            
        scroll_frame = self._concept_win._content_frame
        for widget in scroll_frame.winfo_children():
            widget.destroy()

        title_lbl = tk.Label(
            scroll_frame,
            text=f"📊 概念板块统计详情 (共 {len(all_concepts)} 个)",
            font=("Microsoft YaHei", 10, "bold"),
            fg="#004D40",
            bg="white",
            anchor="w"
        )
        title_lbl.pack(anchor="w", pady=(4, 8), padx=6)

        for idx, (cat_name, count) in enumerate(all_concepts[:20], 1):
            item_frame = tk.Frame(scroll_frame, bg="white")
            item_frame.pack(fill="x", anchor="w", pady=2, padx=6)
            
            lbl_idx = tk.Label(
                item_frame,
                text=f"{idx:02d}.",
                font=("Consolas", 9),
                fg="gray",
                bg="white"
            )
            lbl_idx.pack(side="left")
            
            lbl_name = tk.Label(
                item_frame,
                text=f"{cat_name}",
                font=("Microsoft YaHei", 9, "bold"),
                fg="#1A73E8",
                bg="white",
                cursor="hand2"
            )
            lbl_name.pack(side="left", padx=4)
            lbl_name.bind("<Button-1>", lambda e, name=cat_name: self.show_concept_top10_window(name))
            
            lbl_count = tk.Label(
                item_frame,
                text=f"({count}只)",
                font=("Microsoft YaHei", 9),
                fg="gray",
                bg="white"
            )
            lbl_count.pack(side="left")

    def show_concept_top10_window(self, concept_name):
        """展示此概念的个股列表"""
        import re
        target_concept = self._normalize_concept_name(concept_name)
        if not target_concept:
            return

        last_flat_df = getattr(self, "_last_flat_df", None)
        if last_flat_df is None or last_flat_df.empty:
            messagebox.showinfo("信息", "当前无筛选数据，无法查看个股列表", parent=self)
            return

        # 优先使用预构建索引（O(1)），否则回退到遍历（兜底）
        concept_index = getattr(self, "_concept_index", None)
        if concept_index is not None:
            matched_codes = concept_index.get(target_concept, [])
            matched_stocks = [(code, last_flat_df.loc[code]) for code in matched_codes if code in last_flat_df.index]
        else:
            matched_stocks = []
            for code, row in last_flat_df.iterrows():
                category = self._get_stock_category(code, row)
                if not category:
                    continue
                cats = [c.strip() for c in re.split(r'[;；,，/|]', category) if c.strip()]
                cats_normalized = [self._normalize_concept_name(c) for c in cats]
                if target_concept in cats_normalized:
                    matched_stocks.append((code, row))

        if not matched_stocks:
            messagebox.showinfo("信息", f"当前筛选结果中暂无属于【{target_concept}】的个股", parent=self)
            return


        if hasattr(self, "concept_win") and self.concept_win and self.concept_win.winfo_exists():
            try:
                self.concept_win.destroy()
            except Exception:
                pass
        self.concept_win = None

        win = tk.Toplevel(self)
        self.concept_win = win
        win.title(f"板块【{target_concept}】个股列表")
        
        saved_geom = self.ui_state.get('concept_window_geometry', '750x400')
        win.geometry(saved_geom)

        def _save_concept_win_geo(event):
            if win.winfo_exists():
                try:
                    self.ui_state["concept_window_geometry"] = win.winfo_geometry()
                    self._save_state()
                except Exception:
                    pass
        win.bind("<Configure>", _save_concept_win_geo)
        win.bind("<Escape>", lambda e: win.destroy())

        frame = tk.Frame(win, bg="white", highlightbackground="#CCCCCC", highlightthickness=1, bd=0)
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        columns = ["idx"] + list(self.tree["columns"])
        
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", style="MultiPeriod.Treeview")
        
        vsb = tk.Scrollbar(frame, orient="vertical", command=tree.yview,
                           width=8, bd=0, relief="flat",
                           bg="#B0BEC5", troughcolor="#ECEFF1",
                           activebackground="#78909C",
                           highlightthickness=0)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
 
        def sort_sub_column(t, col, reverse):
            data = [(t.set(k, col), k) for k in t.get_children('')]
            def safe_float(x):
                try:
                    return float(str(x).replace('%', '').strip())
                except ValueError:
                    if '✅' in str(x): return 1.0
                    if '--' in str(x): return -999.0
                    return -999.0
            try:
                [safe_float(x[0]) for x in data if x[0]]
                data.sort(key=lambda x: safe_float(x[0]), reverse=reverse)
            except Exception:
                data.sort(key=lambda x: str(x[0]), reverse=reverse)
            for index, (val, k) in enumerate(data):
                t.move(k, '', index)
            t.heading(col, command=lambda c=col: sort_sub_column(t, c, not reverse))
 
        tree.heading("idx", text="序号", command=lambda c="idx": sort_sub_column(tree, c, False))
        tree.column("idx", width=int(36 * self.scale_factor), anchor="center")
        for col in self.tree["columns"]:
            tree.heading(col, text=self.tree.heading(col, "text"), command=lambda c=col: sort_sub_column(tree, c, False))
            tree.column(col, width=self.tree.column(col, "width"), anchor=self.tree.column(col, "anchor"))

        def on_select_sub(event):
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                if vals and len(vals) >= 2:
                    code = str(vals[1]).strip().zfill(6)
                    self._do_linkage(code=code)

        tree.bind("<<TreeviewSelect>>", on_select_sub)

        # 底部操作栏，内置诊断与DNA审计功能
        action_bar = tk.Frame(win, bg="#f7f7f7", bd=1, relief="groove")
        action_bar.pack(fill="x", side="bottom", padx=4, pady=2)

        def do_diagnose():
            sel = tree.selection()
            if not sel:
                from tkinter import messagebox
                messagebox.showwarning("警告", "请在个股列表中选择一只股票！", parent=win)
                return
            vals = tree.item(sel[0], "values")
            if vals and len(vals) >= 3:
                code = str(vals[1]).strip().zfill(6)
                name = str(vals[2]).strip()
                if name.startswith("★ "):
                    name = name[len("★ "):]
                self.diagnose_stock_strategy(code, name)
            elif vals and len(vals) >= 2:
                code = str(vals[1]).strip().zfill(6)
                self.diagnose_stock_strategy(code, code)

        def do_dna_audit():
            sel = tree.selection()
            if not sel:
                from tkinter import messagebox
                messagebox.showwarning("警告", "请在个股列表中选择一只股票！", parent=win)
                return
            
            curr_item = sel[0]
            children = tree.get_children()
            try:
                curr_idx = children.index(curr_item)
            except ValueError:
                curr_idx = 0
            
            selected_items = children[curr_idx:curr_idx + 21]
            code_to_name = {}
            for item in selected_items:
                vals = tree.item(item, "values")
                if vals and len(vals) >= 3:
                    c = str(vals[1]).strip().zfill(6)
                    n = str(vals[2]).strip()
                    if n.startswith("★ "):
                        n = n[len("★ "):]
                    code_to_name[c] = n
                elif vals and len(vals) >= 2:
                    c = str(vals[1]).strip().zfill(6)
                    code_to_name[c] = c
            
            if not code_to_name:
                from tkinter import messagebox
                messagebox.showwarning("警告", "未获取到有效的股票数据！", parent=win)
                return
                
            active_periods = [p for p, var in self.period_vars.items() if var.get()]
            PERIOD_ORDER = {'d': 1, '2d': 2, '3d': 3, 'w': 4, 'm': 5, '45d': 6, '3M': 7}
            sorted_periods = sorted(active_periods, key=lambda x: PERIOD_ORDER.get(x, 99))
            min_period = sorted_periods[0] if sorted_periods else 'd'
            
            self._run_dna_audit_batch(code_to_name, end_date=self._get_audit_end_date(), resample=min_period)

        btn_sub_diag = tk.Button(action_bar, text="🔍 诊断所选个股", command=do_diagnose, bg="#0288D1", fg="white", font=("Microsoft YaHei", 9), padx=8, pady=2)
        btn_sub_diag.pack(side="left", padx=5, pady=3)

        btn_sub_dna = tk.Button(action_bar, text="🧬 DNA审计所选", command=do_dna_audit, bg="#2E7D32", fg="white", font=("Microsoft YaHei", 9), padx=8, pady=2)
        btn_sub_dna.pack(side="left", padx=5, pady=3)
        tree.bind("<Button-3>", self.show_context_menu)
        tree.bind("<Motion>", lambda e: self._on_tree_motion_impl(e, tree))
        tree.bind("<Leave>", self._on_tree_leave)
        win.bind("<Destroy>", lambda e: self._hide_tree_tooltip())

        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        for idx, (code, row) in enumerate(matched_stocks):
            name = row.get('name', '--')
            is_fav = code in fav_stocks
            display_name = f"★ {name}" if is_fav else name
            
            values = [idx + 1]
            
            for col in self.tree["columns"]:
                if col == "code":
                    values.append(code)
                elif col == "name":
                    values.append(display_name)
                elif col == "price":
                    values.append(round(row.get('close', 0), 2))
                elif col == "percent":
                    values.append(round(row.get('percent', 0), 2))
                elif col == "volume":
                    values.append(round(row.get('volume', 0), 2))
                elif col == "ratio":
                    values.append(round(row.get('ratio', 0), 2))
                else:
                    val = '--'
                    if col in row:
                        raw_val = row.get(col)
                        if pd.notna(raw_val):
                            if col.startswith("pass_"):
                                val = '✅' if raw_val else '--'
                            elif isinstance(raw_val, (int, float)):
                                val = round(raw_val, 2)
                            else:
                                val = str(raw_val)
                    values.append(val)
            
            tree.insert("", "end", values=values)

        stat_frame = tk.Frame(win, bg="#F9F9F9", height=24)
        stat_frame.pack(side="bottom", fill="x", padx=4, pady=2)

        up_stocks = [r for c, r in matched_stocks if r.get('percent', 0) > 0]
        down_stocks = [r for c, r in matched_stocks if r.get('percent', 0) < 0]
        flat_stocks = [r for c, r in matched_stocks if r.get('percent', 0) == 0]

        avg_up = sum(r.get('percent', 0) for r in up_stocks) / len(up_stocks) if up_stocks else 0.0
        avg_down = sum(r.get('percent', 0) for r in down_stocks) / len(down_stocks) if down_stocks else 0.0

        stat_text = f" 统计: 上涨 {len(up_stocks)}只 (均幅 {avg_up:+.2f}%) | 下跌 {len(down_stocks)}只 (均幅 {avg_down:+.2f}%) | 平盘 {len(flat_stocks)}只"
        lbl_stat = tk.Label(stat_frame, text=stat_text, font=("Microsoft YaHei", 9, "bold"), fg="#333333", bg="#F9F9F9", anchor="w")
        lbl_stat.pack(side="left", padx=6, pady=2)

        win.deiconify()
        win.lift()
        win.focus_force()


class MultiPeriodStrategyEditor(tk.Toplevel):
    def __init__(self, parent, engine, on_save_callback):
        super().__init__(parent)
        self.title("多周期过滤策略编辑器")
        
        # 统一计算 DPI 缩放比例
        if hasattr(parent, 'scale_factor'):
            self.scale_factor = parent.scale_factor
        else:
            from dpi_utils import get_windows_dpi_scale_factor
            self.scale_factor = get_windows_dpi_scale_factor()
            
        default_w = int(850 * self.scale_factor)
        default_h = int(580 * self.scale_factor)
        
        # 尝试从配置文件读取上次保存的窗口位置与大小
        config_path = os.path.join(get_app_root(), "config", "standalone_tester_config.json")
        editor_geom = f"{default_w}x{default_h}"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    geom_saved = cfg.get("editor_geometry")
                    if geom_saved:
                        editor_geom = geom_saved
            except Exception:
                pass
                
        # 若是首次打开（配置中只存了宽高，不包含 '+' 偏移量），则执行居中计算
        if "+" not in editor_geom:
            try:
                w, h = map(int, editor_geom.split("x"))
                if w == 850 and h == 580:
                    w, h = default_w, default_h
            except Exception:
                w, h = default_w, default_h
                
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
            initial_idx = 0
            current_strat_id = parent.ui_state.get('strategy_id', '')
            if current_strat_id:
                for idx, s in enumerate(self.strategies):
                    if s['id'] == current_strat_id:
                        initial_idx = idx
                        break
            self.listbox.selection_set(initial_idx)
            self.listbox.see(initial_idx)
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
        dialog.geometry("650x480")
        dialog.transient(self)
        dialog.grab_set()
        
        # 居中显示
        dialog.update_idletasks()
        w, h = 650, 480
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
            
            show_toast(self, f"✅ 成功导入 {len(valid_strats)} 条策略！", duration=1500)
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
        show_toast(self, f"✅ JSON 已成功解析并更新策略「{strat['name']}」！", duration=1500)

    def _copy_json_to_clipboard(self):
        """复制 JSON 编辑器内容到系统剪贴板"""
        if not hasattr(self, 'json_editor'):
            return
        content = self.json_editor.get("1.0", tk.END).strip()
        self.clipboard_clear()
        self.clipboard_append(content)
        show_toast(self, "📋 JSON 内容已复制到剪贴板！", duration=1200)

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
            # 在主窗口(parent)上弹起 Toast，并同时更新其状态栏
            parent_win = self.master
            if parent_win:
                show_toast(parent_win, "🌟 所有多周期策略已成功保存并重新加载！", duration=1800)
                if hasattr(parent_win, "status_var"):
                    parent_win.status_var.set("🌟 所有多周期策略已成功保存并重新加载！")
            self._on_close()
        else:
            messagebox.showerror("错误", "保存策略失败。")


# ===== 🐉 2D/3D 加速龙头追踪器 (Tkinter版磁吸暗色高颜值) =====

def safe_float(val, default=0.0):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except Exception:
        return default

def get_monitor_info(hwnd):
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        monitor = user32.MonitorFromWindow(hwnd, 2) # MONITOR_DEFAULTTONEAREST = 2
        
        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)
            ]
        
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            scale = 1.0
            try:
                shcore = ctypes.windll.shcore
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                # MDT_EFFECTIVE_DPI = 0
                shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
                scale = dpi_x.value / 96.0
            except Exception:
                pass
                
            return {
                "x": int(info.rcWork.left / scale),
                "y": int(info.rcWork.top / scale),
                "width": int((info.rcWork.right - info.rcWork.left) / scale),
                "height": int((info.rcWork.bottom - info.rcWork.top) / scale)
            }
    except Exception as e:
        print(f"Failed to get monitor info: {e}")
    return None

class TkDragonLeaderMonitor(tk.Toplevel):
    def __init__(self, master):
        if getattr(master, "_debug_mode", False):
            print("[DragonMonitor] __init__ starting...")
        super().__init__(master)
        self.master = master
        self.title("🐉 2D/3D 加速龙头追踪器")
        
        # 1. 样式设置：无边框 & 保持最前
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#161822", highlightbackground="#00FFCC", highlightcolor="#00FFCC", highlightthickness=1)
        
        self.scale_factor = getattr(master, "scale_factor", 1.0)
        
        # 最小尺寸：标题栏(28) + 控制栏(32) + 3行数据(75) + padding(12) = ~147px
        _min_h = int(max(147, (28 + 32 + 75 + 12) * self.scale_factor))
        self.minsize(400, _min_h)
        
        # 2. 跨会话数据和布局路径 (使用统一 app_root 规避打包临时目录写保护)
        try:
            app_root = get_app_root()
            self.data_dir = os.path.join(app_root, "datacsv")
            os.makedirs(self.data_dir, exist_ok=True)
            self.db_path = os.path.join(self.data_dir, "tester_dragon_leaders.json")
            self.layout_path = os.path.join(self.data_dir, "tester_dragon_monitor_layout.json")
        except Exception as e:
            print(f"[DragonMonitor] Failed to initialize data paths: {e}")
            self.data_dir = None
            self.db_path = None
            self.layout_path = None
        
        self.manual_codes = self._load_manual_codes()
        self.auto_codes = []
        self._last_row_count = 0
        
        self.anchor_edge = None
        self.collapsed = False
        self.normal_geom = None
        self._hover_enter_timer_id = None
        self._hover_leave_timer_id = None
        self._hover_enter_time = None   # 鼠标进入时间戳（事件驱动 + 轮询共用）
        self._hover_leave_time = None   # 鼠标离开时间戳（事件驱动 + 轮询共用）
        self.is_dragging = False
        self._last_show_time = 0.0
        self._is_animating = False      # 动画互斥锁：动画进行中禁止触发折叠/展开
        self._has_hovered_since_show = False  # first-hover 冷却保护：只有鼠标进过一次才允许自动折叠
        
        # 3. 初始化UI与事件绑定
        self._init_ui()
        self._restore_window_position()
        self._bind_events()
        
        # 4. 数据刷新
        self.update_data()
        # 5. 启动磁吸悬停轮询（延迟 1500ms：给窗口足够的冷却期，防止刚打开就自动折叠）
        self._last_show_time = time.time()  # 重置冷却时间戳
        self.after(1500, self._check_hover_loop)
        if getattr(self.master, "_debug_mode", False):
            print(f"[DragonMonitor] Initialization complete. db_path={self.db_path}, layout_path={self.layout_path}")
        
    def _init_ui(self):
        self.main_container = tk.Frame(self, bg="#161822", bd=1, relief="solid", highlightbackground="#2E2E36", highlightcolor="#2E2E36", highlightthickness=1)
        self.main_container.pack(fill="both", expand=True)
        
        # 自定义标题栏
        self.title_bar = tk.Frame(self.main_container, bg="#1b1e2a", height=int(28 * self.scale_factor))
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)
        
        title_lbl = tk.Label(self.title_bar, text="🐉 2D/3D 加速龙头追踪器 | 每日自动挖掘 + 手动跟踪", bg="#1b1e2a", fg="#00FFCC", font=("Microsoft YaHei", 9, "bold"))
        title_lbl.pack(side="left", padx=8)
        
        btn_close = tk.Label(self.title_bar, text="✕", bg="#1b1e2a", fg="#8e90a6", font=("Microsoft YaHei", 10, "bold"), cursor="hand2", width=3)
        btn_close.pack(side="right", fill="y")
        btn_close.bind("<Enter>", lambda e: btn_close.config(bg="#E53935", fg="white"))
        btn_close.bind("<Leave>", lambda e: btn_close.config(bg="#1b1e2a", fg="#8e90a6"))
        btn_close.bind("<Button-1>", lambda e: self.destroy())
        
        # 底部控制区
        control_frame = tk.Frame(self.main_container, bg="#1b1e2a", height=int(32 * self.scale_factor))
        control_frame.pack(fill="x", side="bottom")
        control_frame.pack_propagate(False)
        
        self.on_top_var = tk.BooleanVar(value=True)
        chk_on_top = tk.Checkbutton(control_frame, text="置顶", variable=self.on_top_var, command=self._on_top_toggled, bg="#1b1e2a", fg="#00FFCC", selectcolor="#161822", font=("Microsoft YaHei", 9, "bold"), activebackground="#1b1e2a", activeforeground="#00FFCC")
        chk_on_top.pack(side="left", padx=8)
        
        btn_add = tk.Button(control_frame, text="➕ 添加股票", command=self._on_add_manual_clicked, bg="#1a3a30", fg="#00ffaa", activebackground="#00ffaa", activeforeground="#000", font=("Microsoft YaHei", 9, "bold"), relief="flat", bd=0, padx=6)
        btn_add.pack(side="right", padx=8, pady=4)
        
        # 右下角手把手拉伸手柄
        self.grip = tk.Canvas(control_frame, width=14, height=14, bg="#1b1e2a", highlightthickness=0, cursor="size_nw_se")
        self.grip.pack(side="right", anchor="se", padx=2, pady=2)
        self.grip.create_line(12, 2, 2, 12, fill="#8e90a6", width=1)
        self.grip.create_line(12, 5, 5, 12, fill="#8e90a6", width=1)
        self.grip.create_line(12, 8, 8, 12, fill="#8e90a6", width=1)
        self.grip.bind("<Button-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", self._on_resize)
        self.grip.bind("<ButtonRelease-1>", self._stop_resize)
        
        
        # 表格区
        table_frame = tk.Frame(self.main_container, bg="#0c0d14")
        table_frame.pack(fill="both", expand=True, padx=4, pady=4)
        
        self.cols = ["代码", "名称", "现价", "涨幅%", "波段状态", "DFF", "DFF2", "DFF3", "大盘偏离", "共振状态", "来源"]
        
        style = ttk.Style()
        # 仅配置 Dragon 命名空间样式，不修改全局 theme，避免影响主程序其他 ttk 控件
        style.configure("Dragon.Treeview", background="#0c0d14", fieldbackground="#0c0d14", foreground="#ffffff", rowheight=int(25 * self.scale_factor), font=("Microsoft YaHei", 9))
        style.map("Dragon.Treeview", background=[("selected", "#24293e")], foreground=[("selected", "#00ffaa")])
        style.configure("Dragon.Treeview.Heading", background="#1b1e2a", foreground="#8e90a6", font=("Microsoft YaHei", 9, "bold"))
        style.map("Dragon.Treeview.Heading", background=[("active", "#24293e")], foreground=[("active", "#00ffaa")])
        
        self.tree = ttk.Treeview(table_frame, columns=self.cols, show="headings", style="Dragon.Treeview")
        
        widths = [75, 85, 70, 70, 80, 65, 65, 65, 85, 100, 80]
        for idx, col in enumerate(self.cols):
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_column(c, False))
            self.tree.column(col, width=int(widths[idx] * self.scale_factor), anchor="center")
            
        vsb = tk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview, width=8, bd=0, relief="flat", bg="#141622", troughcolor="#0c0d14")
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        
        self.tree.bind("<Double-1>", self._on_item_double_clicked)
        self.tree.bind("<Button-1>", self._on_item_clicked)
        self.tree.bind("<Button-3>", self._show_context_menu)
        
        self.tree.tag_configure("manual", background="#122518", foreground="#00FF88")
        self.tree.tag_configure("auto_up", background="#0c0d14", foreground="#FF3333")
        self.tree.tag_configure("auto_down", background="#0c0d14", foreground="#00E676")
        self.tree.tag_configure("auto_normal", background="#0c0d14", foreground="#D4D4D4")
        self.tree.tag_configure("resonance_warm", background="#1A1813", foreground="#FF8C00") # 逆市抗跌

    def _bind_events(self):
        self.title_bar.bind("<Button-1>", self._start_drag)
        self.title_bar.bind("<B1-Motion>", self._on_drag)
        self.title_bar.bind("<ButtonRelease-1>", self._stop_drag)
        
        for child in self.title_bar.winfo_children():
            if child.cget("text") != "✕":
                child.bind("<Button-1>", self._start_drag)
                child.bind("<B1-Motion>", self._on_drag)
                child.bind("<ButtonRelease-1>", self._stop_drag)
        
        # 上下键键盘导航联动：TreeviewSelect 覆盖鼠标点击与键盘两种场景
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<KeyRelease-Up>", self._on_tree_select)
        self.tree.bind("<KeyRelease-Down>", self._on_tree_select)
        
        # 绑定鼠标移入/移出事件，实现 100% 自适应的事件驱动吸附弹出
        self.bind("<Enter>", self._on_mouse_enter)
        self.bind("<Leave>", self._on_mouse_leave)
        self.main_container.bind("<Enter>", self._on_mouse_enter)
        self.main_container.bind("<Leave>", self._on_mouse_leave)
        
    def _on_mouse_enter(self, event):
        """鼠标进入窗口时的事件回调：辅助 _check_hover_loop，更新进入时间戳。
        注意：折叠态下不设置 _has_hovered_since_show，防止初始化伪 Enter 事件触发立即折叠。"""
        if self.is_dragging or self._is_animating:
            return
        # 折叠态下只更新进入时间戳（用于触发 expand），不标记 _has_hovered_since_show
        if not self.collapsed:
            self._has_hovered_since_show = True
        self._hover_leave_time = None
        if self._hover_enter_time is None:
            self._hover_enter_time = time.time()

    def _on_mouse_leave(self, event):
        """鼠标离开窗口时的事件回调：辅助 _check_hover_loop，更新离开时间戳。"""
        if self.is_dragging or self._is_animating:
            return
        self._hover_enter_time = None
        if self._hover_leave_time is None and self._has_hovered_since_show:
            self._hover_leave_time = time.time()

    def _start_drag(self, event):
        self.is_dragging = True
        self.drag_x = event.x
        self.drag_y = event.y
        self.anchor_edge = None
        # 拖拽开始时清空定时器，防抖防意外折叠
        if self._hover_enter_timer_id:
            self.after_cancel(self._hover_enter_timer_id)
            self._hover_enter_timer_id = None
        if self._hover_leave_timer_id:
            self.after_cancel(self._hover_leave_timer_id)
            self._hover_leave_timer_id = None
        
    def _on_drag(self, event):
        x = self.winfo_x() + (event.x - self.drag_x)
        y = self.winfo_y() + (event.y - self.drag_y)
        self.geometry(f"+{x}+{y}")
        
    def _stop_drag(self, event):
        self.is_dragging = False
        self._detect_and_snap()
        self._last_show_time = time.time()  # 拖拽释放吸附后，重置冷却保护，防止立刻折叠
        self._has_hovered_since_show = False  # 必须重新移入一次才允许再次折叠
        
    def _detect_and_snap(self):
        if self.collapsed:
            return
        monitor = get_monitor_info(self.winfo_id())
        if monitor:
            m_x, m_y, m_w, m_h = monitor["x"], monitor["y"], monitor["width"], monitor["height"]
        else:
            m_x, m_y = 0, 0
            m_w = self.winfo_screenwidth()
            m_h = self.winfo_screenheight()
            
        win_x = self.winfo_x()
        win_y = self.winfo_y()
        win_w = self.winfo_width()
        win_h = self.winfo_height()
        
        margin = 40
        snapped = False
        edge = None
        target_x = win_x
        target_y = win_y
        
        diff_top = abs(win_y - m_y)
        diff_bottom = abs((win_y + win_h) - (m_y + m_h))
        diff_left = abs(win_x - m_x)
        diff_right = abs((win_x + win_w) - (m_x + m_w))
        
        min_diff = min(diff_top, diff_bottom, diff_left, diff_right)
        if min_diff < margin:
            if min_diff == diff_top:
                edge = "top"
                target_y = m_y
                snapped = True
            elif min_diff == diff_bottom:
                edge = "bottom"
                target_y = m_y + m_h - win_h
                snapped = True
            elif min_diff == diff_left:
                edge = "left"
                target_x = m_x
                snapped = True
            elif min_diff == diff_right:
                edge = "right"
                target_x = m_x + m_w - win_w
                snapped = True
                
        if snapped:
            self.anchor_edge = edge
            self.geometry(f"{win_w}x{win_h}+{target_x}+{target_y}")
            self.normal_geom = (target_x, target_y, win_w, win_h)
            self._save_window_states()
        else:
            self.anchor_edge = None
            self.normal_geom = (win_x, win_y, win_w, win_h)
            self._save_window_states()
            
    def _animate_geometry(self, start_w, start_h, start_x, start_y, end_w, end_h, end_x, end_y, steps=10, current_step=0, callback=None):
        if not self.winfo_exists():
            self._is_animating = False
            return
        if current_step >= steps:
            self.geometry(f"{end_w}x{end_h}+{end_x}+{end_y}")
            self.attributes("-topmost", True)
            self.lift()
            self._is_animating = False
            if callback:
                callback()
            self._save_window_states()
            return
            
        progress = current_step / steps
        # Easing curve: easeOutCubic
        progress = 1 - (1 - progress) ** 3
        
        curr_w = int(start_w + (end_w - start_w) * progress)
        curr_h = int(start_h + (end_h - start_h) * progress)
        curr_x = int(start_x + (end_x - start_x) * progress)
        curr_y = int(start_y + (end_y - start_y) * progress)
        
        self.geometry(f"{curr_w}x{curr_h}+{curr_x}+{curr_y}")
        self.attributes("-topmost", True)
        self.lift()
        self.update_idletasks()
        self.after(12, lambda: self._animate_geometry(
            start_w, start_h, start_x, start_y,
            end_w, end_h, end_x, end_y,
            steps, current_step + 1, callback
        ))

    def _collapse(self):
        if not self.anchor_edge or self.collapsed or not self.normal_geom:
            return
        if self._is_animating:
            return
        win_x, win_y, win_w, win_h = self.normal_geom
        
        monitor = get_monitor_info(self.winfo_id())
        if monitor:
            m_x, m_y, m_w, m_h = monitor["x"], monitor["y"], monitor["width"], monitor["height"]
        else:
            m_x, m_y = 0, 0
            m_w = self.winfo_screenwidth()
            m_h = self.winfo_screenheight()
            
        strip_size = 5
        if self.anchor_edge == "left":
            end_x = m_x - win_w + strip_size
            end_y = win_y
        elif self.anchor_edge == "right":
            end_x = m_x + m_w - strip_size
            end_y = win_y
        elif self.anchor_edge == "top":
            end_x = win_x
            end_y = m_y - win_h + strip_size
        elif self.anchor_edge == "bottom":
            end_x = win_x
            end_y = m_y + m_h - strip_size
        else:
            return
            
        self.collapsed = True
        self._is_animating = True
        self._hover_enter_time = None
        self._hover_leave_time = None
        
        # 强力置顶
        self.attributes("-topmost", True)
        self.lift()
        
        # 渐变淡出至 0.45
        def _fade_out(step=0, total=8):
            if not self.winfo_exists() or not self.collapsed:
                return
            self.attributes("-alpha", max(0.45, 1.0 - (step / total) * 0.55))
            if step < total:
                self.after(18, lambda: _fade_out(step + 1, total))
                
        _fade_out()
        
        self._animate_geometry(
            win_w, win_h, win_x, win_y,
            win_w, win_h, end_x, end_y,
            steps=10,
            callback=lambda: self.after(150, self._check_hover_loop)  # 动画结束后重启轮询
        )
        
    def _expand(self):
        if not self.collapsed or not self.normal_geom:
            return
        if self._is_animating:
            return
        win_x, win_y, win_w, win_h = self.normal_geom
        
        start_w = self.winfo_width()
        start_h = self.winfo_height()
        start_x = self.winfo_x()
        start_y = self.winfo_y()
        
        self.collapsed = False
        self._last_show_time = time.time()
        self._has_hovered_since_show = False
        self._is_animating = True
        self._hover_enter_time = None
        self._hover_leave_time = None
        
        # 强力置顶
        self.attributes("-topmost", True)
        self.lift()
        
        # 淡入到 1.0
        def _fade_in(step=0, total=8):
            if not self.winfo_exists() or self.collapsed:
                return
            self.attributes("-alpha", min(1.0, 0.45 + (step / total) * 0.55))
            if step < total:
                self.after(18, lambda: _fade_in(step + 1, total))
                
        _fade_in()
        self._animate_geometry(
            start_w, start_h, start_x, start_y,
            win_w, win_h, win_x, win_y,
            steps=10,
            callback=lambda: self.after(150, self._check_hover_loop)  # 动画结束后重启轮询
        )

    def _start_resize(self, event):
        self._resize_start_w = self.winfo_width()
        self._resize_start_h = self.winfo_height()
        self._resize_start_x = self.winfo_pointerx()
        self._resize_start_y = self.winfo_pointery()
        
    def _on_resize(self, event):
        dx = self.winfo_pointerx() - self._resize_start_x
        dy = self.winfo_pointery() - self._resize_start_y
        # 最小高度：标题栏 + 控制栏 + 3行数据 + padding
        _min_h = int(max(147, (28 + 32 + 75 + 12) * self.scale_factor))
        new_w = max(400, self._resize_start_w + dx)
        new_h = max(_min_h, self._resize_start_h + dy)
        x = self.winfo_x()
        y = self.winfo_y()
        self.geometry(f"{new_w}x{new_h}+{x}+{y}")
        self.normal_geom = (x, y, new_w, new_h)
        
    def _stop_resize(self, event):
        self._save_window_states()
        
    def _check_hover_loop(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        
        is_pressed = False
        try:
            import ctypes
            is_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        except Exception:
            pass

        # 拖拽中或鼠标物理左键按下时跳过所有判断，重置所有防抖时间戳
        if self.is_dragging or self._is_animating or is_pressed:
            self._hover_enter_time = None
            self._hover_leave_time = None
            self.after(200, self._check_hover_loop)
            return
            
        # 折叠态强力自愈 topmost 层级，防止被通达信等盖住
        if self.collapsed and not self._is_animating:
            self.attributes("-topmost", True)
            self.lift()
        
        pointer_x, pointer_y = self.winfo_pointerxy()
        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        win_w = self.winfo_width()
        win_h = self.winfo_height()
        
        # 使用 Tkinter 同比例坐标系绝对差值计算相对坐标，天然免疫任何高 DPI 缩放偏差！
        rel_x = pointer_x - root_x
        rel_y = pointer_y - root_y
        
        tolerance = 12
        if self.collapsed:
            # 折叠态下让热区稍微向屏幕内延伸，提升滑入灵敏度，吸附手感更好
            tolerance = 18
            
        in_window = False
        
        if self.collapsed:
            # 折叠态：精确根据吸附边缘，用相对坐标检测鼠标是否在屏幕内露出的 5px 热区中
            if self.anchor_edge == "left":
                in_window = (win_w - 5 - tolerance <= rel_x <= win_w + tolerance) and \
                            (-tolerance <= rel_y <= win_h + tolerance)
            elif self.anchor_edge == "right":
                in_window = (-tolerance <= rel_x <= 5 + tolerance) and \
                            (-tolerance <= rel_y <= win_h + tolerance)
            elif self.anchor_edge == "top":
                in_window = (-tolerance <= rel_x <= win_w + tolerance) and \
                            (win_h - 5 - tolerance <= rel_y <= win_h + tolerance)
            elif self.anchor_edge == "bottom":
                in_window = (-tolerance <= rel_x <= win_w + tolerance) and \
                            (-tolerance <= rel_y <= 5 + tolerance)
        else:
            # 展开态：常规窗口全包围盒检测
            in_window = (-tolerance <= rel_x <= win_w + tolerance) and \
                        (-tolerance <= rel_y <= win_h + tolerance)
                    
        if in_window:
            self._has_hovered_since_show = True  # 鼠标首次移入，允许之后触发自动收起
            
        now = time.time()
        
        if self.collapsed:
            # === 折叠态：鼠标持续悬停 0.2s 后展开 ===
            if in_window:
                if self._hover_enter_time is None:
                    self._hover_enter_time = now
                self._hover_leave_time = None
                if now - self._hover_enter_time >= 0.2:
                    self._expand()
                    return  # expand 后 loop 由下一轮 after 续上
            else:
                self._hover_enter_time = None
        else:
            # === 展开态：已吸附且鼠标曾移入过窗口，才自动折叠 ===
            if self.anchor_edge is not None and getattr(self, '_has_hovered_since_show', False):
                # 展开后 0.8s 冷却期内不折叠，防止刚展开又立即收起
                if now - self._last_show_time < 0.8:
                    self._hover_leave_time = None
                    self.after(150, self._check_hover_loop)
                    return
                
                if not in_window:
                    if self._hover_leave_time is None:
                        self._hover_leave_time = now
                    self._hover_enter_time = None
                    # 离开超过 0.4s 才折叠，防止鼠标路过误触
                    if now - self._hover_leave_time >= 0.4:
                        self._collapse()
                        return  # collapse 后 loop 由下一轮 after 续上
                else:
                    self._hover_leave_time = None
        
        self.after(150, self._check_hover_loop)
        
    def _load_manual_codes(self):
        try:
            if self.db_path and os.path.exists(self.db_path):
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return [str(x).zfill(6) for x in data if x]
                    elif isinstance(data, dict):
                        raw_list = data.get("manual", [])
                        if isinstance(raw_list, list):
                            return [str(x).zfill(6) for x in raw_list if x]
        except Exception as e:
            print(f"[DragonMonitor] Error loading manual codes: {e}")
        return ["000779", "301528"]
        
    def _safe_replace(self, src, dst):
        import time
        for i in range(5):
            try:
                os.replace(src, dst)
                return True
            except PermissionError:
                time.sleep(0.05)
            except Exception as e:
                raise e
        os.replace(src, dst)

    def _save_manual_codes(self):
        if not self.db_path or not self.data_dir:
            return
        try:
            import tempfile
            data = {"manual": list(self.manual_codes)}
            tmp_fd, tmp_path = tempfile.mkstemp(dir=self.data_dir, prefix="ats_dragon_tmp_")
            try:
                with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                self._safe_replace(tmp_path, self.db_path)
            except Exception as e:
                try:
                    os.remove(tmp_path)
                except:
                    pass
                raise e
        except Exception as e:
            print(f"[DragonMonitor] Error saving manual codes atomically: {e}")
            
    def _restore_window_position(self):
        try:
            if self.layout_path and os.path.exists(self.layout_path):
                with open(self.layout_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    x = cfg.get("x", 100)
                    y = cfg.get("y", 100)
                    w = cfg.get("width", 800)
                    h = cfg.get("height", 500)
                    # 防御无效/未渲染/被销毁时的坏数据尺寸（例如 1x1 或极小）
                    if w > 50 and h > 50:
                        self.anchor_edge = cfg.get("anchor_edge", None)
                        # 始终以展开态启动，防止因保存时折叠态导致窗口不可见
                        self.collapsed = False
                        self.geometry(f"{w}x{h}+{x}+{y}")
                        self.normal_geom = (x, y, w, h)
                        topmost = cfg.get("stays_on_top", True)
                        self.on_top_var.set(topmost)
                        self.attributes("-topmost", topmost)
                        self._last_show_time = time.time()
                        return
                    else:
                        if getattr(self.master, "_debug_mode", False):
                            print(f"[DragonMonitor] Skip restoring configuration due to invalid size: {w}x{h}")
        except Exception as e:
            if getattr(self.master, "_debug_mode", False):
                print(f"[DragonMonitor] Error restoring geometry: {e}")
            
        w = int(800 * self.scale_factor)
        h = int(500 * self.scale_factor)
        self.geometry(f"{w}x{h}+100+100")
        self.normal_geom = (100, 100, w, h)
        self._last_show_time = time.time()
        
    def _save_window_states(self):
        if not self.layout_path or not self.data_dir:
            return
        try:
            if not self.winfo_exists():
                return
            import tempfile
            if self.collapsed and self.normal_geom:
                x, y, w, h = self.normal_geom
            else:
                x = self.winfo_x()
                y = self.winfo_y()
                w = self.winfo_width()
                h = self.winfo_height()
                
            # 防御无效/未加载完全的 1x1 坏数据尺寸写入
            if w <= 50 or h <= 50:
                if getattr(self.master, "_debug_mode", False):
                    print(f"[DragonMonitor] Skip saving due to invalid size: {w}x{h}")
                return

            data = {
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "anchor_edge": self.anchor_edge,
                "is_hidden_state": self.collapsed,
                "stays_on_top": self.on_top_var.get()
            }
            tmp_fd, tmp_path = tempfile.mkstemp(dir=self.data_dir, prefix="ats_layout_tmp_")
            try:
                with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                self._safe_replace(tmp_path, self.layout_path)
            except Exception as e:
                try:
                    os.remove(tmp_path)
                except:
                    pass
                raise e
        except Exception as e:
            print(f"[DragonMonitor] Error saving layout: {e}")
            
    def _on_top_toggled(self):
        top = self.on_top_var.get()
        self.attributes("-topmost", top)
        self._save_window_states()
        
    def _on_add_manual_clicked(self):
        from tkinter import simpledialog
        code = simpledialog.askstring("添加龙头追踪个股", "请输入6位股票代码:", parent=self)
        if code and code.strip():
            code_str = code.strip().zfill(6)
            if code_str in self.manual_codes:
                messagebox.showinfo("提示", f"代码 {code_str} 已在追踪列表中。", parent=self)
                return
            self.manual_codes.append(code_str)
            self._save_manual_codes()
            self.update_data()
            
    def _on_tree_select(self, event=None):
        """键盘上下键 / TreeviewSelect 统一联动入口，带防抖避免 update_data 行更新触发风暴"""
        if getattr(self, '_select_locked', False):
            return
        # 200ms 防抖：避免快速连续按键触发多次联动
        if hasattr(self, '_select_after_id') and self._select_after_id:
            try:
                self.after_cancel(self._select_after_id)
            except Exception:
                pass
        self._select_after_id = self.after(200, self._do_tree_select)

    def _do_tree_select(self):
        self._select_after_id = None
        sel = self.tree.selection()
        if sel:
            self._link_code(sel[0])

    def _on_item_clicked(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self._link_code(item)
            
    def _on_item_double_clicked(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self._link_code(item)
            main_app = self.master
            if hasattr(main_app, "diagnose_stock_strategy"):
                main_app.diagnose_stock_strategy(item)
                
    def _link_code(self, code):
        if not code or not str(code).isdigit() or len(str(code)) != 6:
            return
        main_app = self.master
        if hasattr(main_app, "on_code_click"):
            main_app.on_code_click(code)
        elif hasattr(main_app, "_do_linkage"):
            main_app._do_linkage(code)
            
    def _show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        vals = self.tree.item(row_id, "values")
        if not vals or not vals[0] or not str(vals[0]).isdigit() or len(str(vals[0])) != 6:
            return
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)
        code = vals[0]
        name = vals[1].replace("⭐ ", "")
        source = vals[10]
        
        menu = tk.Menu(self, tearoff=0, bg="#1a1a24", fg="#e2e2e5", activebackground="#2c2c35", activeforeground="#ffffff")
        menu.add_command(label=f"⚡ 选中联动 ({code})", command=lambda: self._link_code(code))
        if hasattr(self.master, "_do_linkage"):
            menu.add_command(label=f"⚡ 发送到异动联动 ({code})", command=lambda: self.master._do_linkage(code))
        menu.add_separator()
        if source.startswith("手动"):
            menu.add_command(label="❌ 移出手动跟踪列表", command=lambda: self._remove_from_manual(code))
        else:
            menu.add_command(label="⭐ 转为重点手动跟踪", command=lambda: self._convert_to_manual(code))
        menu.add_separator()
        menu.add_command(label="复制代码", command=lambda: self._copy_to_clipboard(code))
        menu.add_command(label="复制名称", command=lambda: self._copy_to_clipboard(name))
        menu.post(event.x_root, event.y_root)
        
    def _convert_to_manual(self, code):
        if code not in self.manual_codes:
            self.manual_codes.append(code)
            self._save_manual_codes()
            self.update_data()
            
    def _remove_from_manual(self, code):
        if code in self.manual_codes:
            self.manual_codes.remove(code)
            self._save_manual_codes()
            self.update_data()
            
    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        
    def _sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        def safe_sort_val(val):
            v = val.replace("%", "").replace("+", "").strip()
            return safe_float(v)
        is_num = col in ("现价", "涨幅%", "DFF", "DFF2", "DFF3", "大盘偏离")
        if is_num:
            l.sort(key=lambda t: safe_sort_val(t[0]), reverse=reverse)
        else:
            l.sort(key=lambda t: t[0], reverse=reverse)
        for index, (val, k) in enumerate(l):
            self.tree.move(k, "", index)
        self.tree.heading(col, command=lambda: self._sort_column(col, not reverse))
        
    def _show_placeholder_msg(self, msg):
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end", values=(msg, "", "", "", "", "", "", "", "", "", ""))
        
    def update_data(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
            
        try:
            main_app = self.master
            if main_app.top_now is None or not hasattr(main_app.top_now, "empty") or main_app.top_now.empty:
                self._show_placeholder_msg("正在等待主程序行情数据加载...")
                self.after(3000, self.update_data)
                return
                
            selected_code = None
            sel_items = self.tree.selection()
            if sel_items:
                selected_code = sel_items[0]
                
            df = main_app.top_now
            if 'ratio' in df.columns:
                sh_pct = df['ratio'].mean()
            elif 'percent' in df.columns:
                sh_pct = df['percent'].mean()
            else:
                sh_pct = 0.0
                
            # ── 一次加锁读取全部三个周期数据，避免多次竞争锁 ──
            dff_dict = {}
            dff2_dict = {}
            dff3_dict = {}
            
            if hasattr(main_app, "engine") and hasattr(main_app.engine, "_period_dfs"):
                lock = getattr(main_app.engine, "lock", None)
                period_snapshots = {}
                if lock:
                    with lock:
                        for p in ('d', 'w', 'm'):
                            raw = main_app.engine._period_dfs.get(p)
                            if raw is not None and not raw.empty:
                                period_snapshots[p] = raw.copy()
                else:
                    for p in ('d', 'w', 'm'):
                        raw = main_app.engine._period_dfs.get(p)
                        if raw is not None and not raw.empty:
                            period_snapshots[p] = raw.copy()
                            
                df_d = period_snapshots.get('d')
                if df_d is not None:
                    col = 'dff' if 'dff' in df_d.columns else ('dff_d' if 'dff_d' in df_d.columns else None)
                    if col:
                        dff_dict = {str(k).zfill(6): v for k, v in df_d[col].to_dict().items() if k}
                        
                df_w = period_snapshots.get('w')
                if df_w is not None:
                    col = 'dff2' if 'dff2' in df_w.columns else ('dff' if 'dff' in df_w.columns else ('dff_w' if 'dff_w' in df_w.columns else None))
                    if col:
                        dff2_dict = {str(k).zfill(6): v for k, v in df_w[col].to_dict().items() if k}
                        
                df_m = period_snapshots.get('m')
                if df_m is not None:
                    col = 'dff3' if 'dff3' in df_m.columns else ('dff' if 'dff' in df_m.columns else ('dff_m' if 'dff_m' in df_m.columns else None))
                    if col:
                        dff3_dict = {str(k).zfill(6): v for k, v in df_m[col].to_dict().items() if k}
            
            # 1. 自动挖掘加速个股
            new_auto_list = []
            for code, row in df.iterrows():
                code_str = str(code).zfill(6)
                if code_str in self.manual_codes:
                    continue
                dff = safe_float(dff_dict.get(code_str, 0.0))
                dff2 = safe_float(dff2_dict.get(code_str, 0.0))
                dff3 = safe_float(dff3_dict.get(code_str, 0.0))
                pct = safe_float(row.get('ratio', row.get('percent', 0.0)))
                rs_val = pct - sh_pct
                
                if dff > 0.0 and dff2 > 0.0 and dff3 > 0.0 and rs_val >= 2.0 and pct > 1.5:
                    new_auto_list.append((code_str, rs_val))
                    
            new_auto_list.sort(key=lambda x: x[1], reverse=True)
            self.auto_codes = [c[0] for c in new_auto_list[:15]]
            
            # 2. 组装展示行数据（惰性名称缓存，避免每次都做 I/O）
            if not hasattr(self, '_name_cache'):
                self._name_cache = {}
            from sys_utils import resolve_stock_name
            
            seen = set()
            all_codes = [x for x in (list(self.manual_codes) + [c for c in self.auto_codes if c not in self.manual_codes]) if not (x in seen or seen.add(x))]
            rows_data = []
            for code in all_codes:
                price = 0.0
                pct = 0.0
                state = "平稳期"
                
                dff = safe_float(dff_dict.get(code, 0.0))
                dff2 = safe_float(dff2_dict.get(code, 0.0))
                dff3 = safe_float(dff3_dict.get(code, 0.0))
                rs_val = 0.0
                resonance = "同步整理"
                source = "手动添加" if code in self.manual_codes else "🔥自动挖掘"
                
                # 惰性名称缓存：已解析过的不重复查
                if code not in self._name_cache:
                    self._name_cache[code] = resolve_stock_name(code) or code
                name = self._name_cache[code]
                    
                df_code_idx = int(code) if code.isdigit() else code
                row_found = None
                if code in df.index:
                    row_found = df.loc[code]
                elif df_code_idx in df.index:
                    row_found = df.loc[df_code_idx]
                    
                if row_found is not None:
                    if isinstance(row_found, pd.DataFrame):
                        row_found = row_found.iloc[0]
                    # 优先从行情数据中取名字（更准确）
                    row_name = str(row_found.get('name', '') or '').strip()
                    if row_name and row_name not in ('nan', '--', '0', ''):
                        name = row_name
                        self._name_cache[code] = name
                    price = safe_float(row_found.get('close', row_found.get('price', 0.0)))
                    pct = safe_float(row_found.get('ratio', row_found.get('percent', 0.0)))
                    state = str(row_found.get('state', '持股中' if pct > 0 else '回踩中'))
                    rs_val = pct - sh_pct
                    
                    if sh_pct < -0.5 and pct > 1.5 and rs_val > 2.0:
                        resonance = "逆市抗跌"
                    elif sh_pct > 0.5 and pct > 3.0 and dff > 1.0:
                        resonance = "大盘共振"
                    elif sh_pct < -1.0 and pct < -1.5:
                        resonance = "同步走弱"
                        
                rows_data.append((
                    code, name, price, pct, state, dff, dff2, dff3, rs_val, resonance, source
                ))
                
            # 3. 更新 Treeview：锁定 TreeviewSelect 防止行更新触发联动风暴
            self._select_locked = True
            try:
                existing_iids = set(self.tree.get_children())
                for data in rows_data:
                    code, name, price, pct, state, dff, dff2, dff3, rs_val, resonance, source = data
                    disp_name = f"⭐ {name}" if source.startswith("手动") else name
                    disp_pct = f"{pct:+.2f}%"
                    disp_rs = f"{rs_val:+.2f}%"
                    vals = (code, disp_name, f"{price:.2f}", disp_pct, state,
                            f"{dff:.2f}", f"{dff2:.2f}", f"{dff3:.2f}", disp_rs, resonance, source)
                    
                    if source.startswith("手动"):
                        tag = "manual"
                    elif resonance == "逆市抗跌":
                        tag = "resonance_warm"
                    elif resonance == "大盘共振":
                        tag = "auto_up"
                    elif pct < 0:
                        tag = "auto_down"
                    else:
                        tag = "auto_normal"
                        
                    if code in existing_iids:
                        # 脏检查：只有数据变化才刷新，避免无效 set 触发重绘
                        old_vals = self.tree.item(code, 'values')
                        if old_vals != vals:
                            self.tree.item(code, values=vals, tags=(tag,))
                        existing_iids.remove(code)
                    else:
                        self.tree.insert("", "end", iid=code, values=vals, tags=(tag,))
                        
                for old_id in existing_iids:
                    self.tree.delete(old_id)
                    
                if selected_code and self.tree.exists(selected_code):
                    self.tree.selection_set(selected_code)
                    self.tree.focus(selected_code)
            finally:
                self._select_locked = False

        except Exception as e:
            print(f"[DragonMonitor] Error in update_data: {e}")
            
        self.after(3000, self.update_data)
        
    def destroy(self):
        if getattr(self.master, "_debug_mode", False):
            print(f"[DragonMonitor] destroy() called. Setting master.dragon_monitor = None")
        try:
            self._save_window_states()
        except Exception as e:
            if getattr(self.master, "_debug_mode", False):
                print(f"[DragonMonitor] Error saving window states during destroy: {e}")
        if hasattr(self.master, "dragon_monitor"):
            self.master.dragon_monitor = None
        super().destroy()

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = StandaloneMultiPeriodTester()
    app.mainloop()
