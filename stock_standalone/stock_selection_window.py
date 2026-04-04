import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
from datetime import datetime
import threading
import queue
import time
from typing import Optional, Any, TYPE_CHECKING
from collections import Counter
import pandas as pd
from tk_gui_modules.window_mixin import WindowMixin
import logging

logger = logging.getLogger(__name__)

# ✅ 股票特征标记模块导入
try:
    from stock_feature_marker import StockFeatureMarker
    FEATURE_MARKER_AVAILABLE = True
except ImportError:
    FEATURE_MARKER_AVAILABLE = False

if TYPE_CHECKING:
    from stock_live_strategy import StockLiveStrategy
    from stock_selector import StockSelector

try:
    from tkcalendar import DateEntry
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False

class StockSelectionWindow(tk.Toplevel, WindowMixin):
    """
    策略选股确认视窗
    允许用户在导入监控前人工筛选、标注
    """
    def __init__(self, master, live_strategy, stock_selector):
        """
        初始化
        :param master: 主窗口 (通常是 StockMonitorApp)
        :param live_strategy: 实时策略对象
        :param stock_selector: 选股器对象
        """
        super().__init__(master)
        self.title("策略选股 & 人工复核")
        self.scale_factor: float = getattr(master, 'scale_factor', 1.0)
        
        window_id = "策略选股"
        # 加载窗口位置
        self.load_window_position(self, window_id, default_width=900, default_height=500)
        
        self.live_strategy: Optional['StockLiveStrategy'] = live_strategy
        self.selector: Optional['StockSelector'] = stock_selector
        
        # --- History Config ---
        self.history_file: str = "stock_sector_history.json"
        self.history: list[str] = self.load_history()
        
        # 获取主窗口的 sender 用于联动
        self.sender: Optional[Any] = getattr(master, 'sender', None)
        if self.sender is None and hasattr(master, 'master'):
            self.sender = getattr(master.master, 'sender', None)
        self.df_candidates: pd.DataFrame = pd.DataFrame()
        self.df_full_candidates: pd.DataFrame = pd.DataFrame()  # 缓存完整的候选股数据
        self._data_loaded: bool = False  # 标记数据是否已从策略加载
        self.hotspots_frame: Optional[tk.Frame] = None
        
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        
        # ✅ 性能优化标记
        self._column_widths_cached = False
        self._rendering_active = False # 防止并发渲染
        self._render_token = 0         # 标识当前渲染批次
        
        self._init_ui()
        
        # ✅ 初始化股票特征标记器
        self.feature_marker = None
        if FEATURE_MARKER_AVAILABLE:
            try:
                # 遵循主窗口的 enable_colors 逻辑: not master.win_var.get()
                enable_colors = True
                if hasattr(master, 'win_var'):
                    enable_colors = not master.win_var.get()
                self.feature_marker = StockFeatureMarker(self.tree, enable_colors=enable_colors)
                logger.info(f"✅ 选股窗口股票特征标记器已初始化 (颜色显示: {enable_colors})")
                
                # ✅ 绑定主窗口 win_var 变化同步颜色开关
                if hasattr(master, 'win_var'):
                    self._win_var_trace_id = master.win_var.trace_add('write', lambda *args: self._sync_feature_colors())
            except Exception as e:
                logger.warning(f"⚠️ 选股窗口特征标记器初始化失败: {e}")
        
        # 默认使用最近一次查询
        if self.history:
            self.concept_filter_var.set(self.history[0])
            
        self.load_data()

        # [FIX] ESC 关闭窗口
        self.bind("<Escape>", lambda e: self._on_close(window_id))
        self.lift()
        self.focus_force()

        # 绑定关闭事件以保存位置
        self.protocol("WM_DELETE_WINDOW", lambda: self._on_close(window_id))

    def _on_close(self, window_id: str):
        """关闭时保存状态并销毁窗口"""
        # ✅ 移除 win_var 绑定
        if hasattr(self, '_win_var_trace_id') and hasattr(self.master, 'win_var'):
            try:
                self.master.win_var.trace_remove('write', self._win_var_trace_id)
            except:
                pass
        try:
            self.save_window_position(self, window_id)
        except Exception as e:
            print(f"保存窗口位置失败: {e}")
        self.destroy()

    def _sync_feature_colors(self):
        """响应主窗口 win_var 变化，同步切换颜色集"""
        if not self.feature_marker or not hasattr(self.master, 'win_var'):
            return
        
        enable = not self.master.win_var.get()
        self.feature_marker.set_enable_colors(enable)
        # 记录当前选中项
        selection = self.tree.selection()
        # 重新加载数据以应用颜色 (load_data 会循环 tree 并设置 tags)
        # 注意：这里调用 load_data(force=False) 即可利用缓存快速重绘
        self.load_data(force=False)
        # 恢复选中项
        if selection:
            try:
                self.tree.selection_set(selection)
            except: pass

    def _center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry('{}x{}+{}+{}'.format(width, height, x, y))

    def _init_ui(self):
        # --- Custom Styles ---
        style = ttk.Style(self)
        # 减小滚动条宽度 (12 像素比较适中)
        style.configure("Small.Vertical.TScrollbar", width=12)
        style.configure("Small.Horizontal.TScrollbar", width=12)

        # --- Toolbar ---
        toolbar = tk.Frame(self, bd=1, relief="raised")
        toolbar.pack(fill="x", padx=5, pady=5)

        # Today's Hotspots (Quick Filter Buttons)
        # Today's Hotspots (Quick Filter Buttons)
        # Today's Hotspots (Quick Filter Buttons)
        self.hotspots_frame = tk.Frame(toolbar)
        self.hotspots_frame.pack(side="left")
        # Initial update handled in load_data or explicit call if needed (load_data is called at end of init)
        
        # Concept Filter
        tk.Label(toolbar, text="板块筛选:", font=("Arial", 10)).pack(side="left", padx=2)
        tk.Button(toolbar, text="🧹", command=self.clear_filter, width=2).pack(side="left", padx=1)
        self.concept_filter_var: tk.StringVar = tk.StringVar()
        self.concept_combo: ttk.Combobox = ttk.Combobox(toolbar, textvariable=self.concept_filter_var, width=10)
        self.concept_combo['values'] = self.history
        self.concept_combo.pack(side="left", padx=2)

        # tk.Button(toolbar, text="🔍", command=self.on_filter_search, width=3).pack(side="left", padx=1)
        # tk.Button(toolbar, text="🗑️", command=self.delete_current_history, width=2, fg="red").pack(side="left", padx=1)
        tk.Button(toolbar, text="🔍", command=self.on_filter_search, width=3, font=("Segoe UI Emoji", 10), pady=0).pack(side="left", padx=1)
        tk.Button(toolbar, text="🗑️", command=self.delete_current_history, width=2, fg="red", font=("Segoe UI Emoji", 10), pady=0).pack(side="left", padx=1)

        # Date Selector
        tk.Frame(toolbar, width=10).pack(side="left") # Spacer
        tk.Label(toolbar, text="日期:", font=("Arial", 10, "bold")).pack(side="left", padx=2)
        
        if HAS_CALENDAR:
            self.date_entry = DateEntry(toolbar, width=12, background='darkblue', 
                                      foreground='white', borderwidth=2, 
                                      date_pattern='yyyy-mm-dd',
                                      state='readonly')
            self.date_entry.set_date(datetime.now())
            self.date_entry.pack(side="left", padx=2)
            self.date_entry.bind("<<DateEntrySelected>>", self.on_date_changed)
            
            # ✅ [FIX] 使整个输入框区域可点击打开日历 (不仅是小箭头)
            self.date_entry.bind("<Button-1>", lambda e: self._show_calendar(), add="+")
            
            # ✅ [NEW] 初始化日历高亮 (离线数据)
            self.after(500, self._refresh_calendar_highlights)
        else:
            self.date_var = tk.StringVar(value=self.current_date)
            self.date_tk_entry = tk.Entry(toolbar, textvariable=self.date_var, width=11)
            self.date_tk_entry.pack(side="left", padx=2)
            tk.Button(toolbar, text="Go", command=self.on_date_changed, width=3).pack(side="left")

        # Quick Navigation
        tk.Button(toolbar, text="◀", command=lambda: self.shift_date(-1), width=2).pack(side="left", padx=1)
        tk.Button(toolbar, text="▶", command=lambda: self.shift_date(1), width=2).pack(side="left", padx=1)

        tk.Button(toolbar, text="🚀 导入", command=self.import_selected, bg="#ffd54f", font=("Arial", 10, "bold")).pack(side="left", padx=5, pady=5)

        # 🔍 Multi-day Tracking Button
        tk.Button(toolbar, text="🔍 追踪", command=self.on_history_track_clicked, bg="#2a3a4a", fg="#ff9900", font=("Arial", 10, "bold")).pack(side="left", padx=5, pady=5)


        tk.Button(toolbar, text="✅[选中]", command=lambda: self.mark_status("选中"), bg="#c8e6c9").pack(side="left", padx=1)
        tk.Button(toolbar, text="❌[丢弃]", command=lambda: self.mark_status("丢弃"), bg="#ffcdd2").pack(side="left", padx=1)
        
        tk.Frame(toolbar, width=10).pack(side="left") # Spacer

        # Feedback controls
        tk.Label(toolbar, text="标注:", font=("Arial", 10, "bold")).pack(side="left", padx=5)
        
        self.reason_var: tk.StringVar = tk.StringVar()
        self.reason_combo: ttk.Combobox = ttk.Combobox(toolbar, textvariable=self.reason_var, width=8, state="readonly")
        self.reason_combo['values'] = [
            "符合策略", "形态完美", "量能配合", "板块热点", # Positive
            "风险过高", "趋势破坏", "非热点", "量能不足", "位置过高", "其他" # Negative
        ]
        self.reason_combo.current(0)
        self.reason_combo.pack(side="left", padx=2)
        
        # 绑定回车和选中事件
        self.concept_combo.bind('<Return>', self.on_filter_search)
        self.concept_combo.bind('<<ComboboxSelected>>', self.on_filter_search)
        
        # Actions
        tk.Button(toolbar, text="🔄 运行策略", command=lambda: self.load_data(force=True)).pack(side="left", padx=5, pady=5)
        tk.Frame(toolbar, width=20).pack(side="right") # Spacer

        # 绑定双击顶部工具栏自动调整窗口大小
        _ = toolbar.bind("<Double-1>", self._on_toolbar_double_click)

        # --- Main List ---
        # Columns
        columns = ("code", "name", "grade", "tqi", "status", "score", "rank", "price", "percent", "昨日涨幅", "ratio", "amount", "连阳涨幅", "win", "volume", "category", "auto_reason", "user_status", "user_reason")
        
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview, style="Small.Vertical.TScrollbar")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview, style="Small.Horizontal.TScrollbar")
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        
        # Grid layout for precise alignment
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Headings
        headers = {
            "code": "代码", "name": "名称", "grade": "等级", "tqi": "质量分", "status": "类型", "score": "分值", "rank": "Rank",
            "price": "现价", "percent": "涨幅%", "昨日涨幅": "昨日%", "ratio": "量比", "amount": "成交额",
            "连阳涨幅": "连阳", "win": "胜率", "volume": "成交量",
            "category": "板块/概念",
            "auto_reason": "机选理由", "user_status": "复核状态", "user_reason": "复核标注"
        }
        
        for col, text in headers.items():
            self.tree.heading(col, text=text, command=lambda c=col: self.sort_tree(c, False))
            self.tree.column(col, anchor="center")

        # Column Configurations
        self.tree.column("code", width=70, minwidth=60, stretch=False)
        self.tree.column("name", width=80, minwidth=70, stretch=False)
        self.tree.column("grade", width=40, minwidth=35, stretch=False)
        self.tree.column("tqi", width=45, minwidth=40, stretch=False)
        self.tree.column("status", width=60, minwidth=50, stretch=False)
        self.tree.column("score", width=50, minwidth=40, stretch=False)
        self.tree.column("rank", width=40, minwidth=30, stretch=False)
        self.tree.column("price", width=70, minwidth=60, stretch=False)
        self.tree.column("percent", width=70, minwidth=60, stretch=False)
        self.tree.column("昨日涨幅", width=70, minwidth=60, stretch=False)
        self.tree.column("ratio", width=60, minwidth=50, stretch=False)
        self.tree.column("amount", width=80, minwidth=70, stretch=False)
        self.tree.column("连阳涨幅", width=60, minwidth=50, stretch=False)
        self.tree.column("win", width=40, minwidth=30, stretch=False)
        self.tree.column("volume", width=90, minwidth=80, stretch=False)
        self.tree.column("category", width=140, minwidth=100, stretch=True)
        self.tree.column("auto_reason", width=260, minwidth=150, stretch=True)
        self.tree.column("user_status", width=80, minwidth=60, stretch=False)
        self.tree.column("user_reason", width=150, minwidth=100, stretch=True)
        
        # Tags for coloring
        self.tree.tag_configure("selected", background="#dcedc8")  # Light Green
        self.tree.tag_configure("ignored", background="#ffcdd2")   # Light Red
        self.tree.tag_configure("pending", background="#ffffff")   # White
        self.tree.tag_configure("grade_S", foreground="#e91e63", font=("Arial", 9, "bold")) # Pink/Red for S
        self.tree.tag_configure("grade_A", foreground="#f57c00", font=("Arial", 9, "bold")) # Orange for A

        self.tree.bind("<ButtonRelease-1>", self.on_select)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.on_double_click) # 🚀 [NEW] 双击联动标记
        self.tree.bind("<Button-3>", self.show_context_menu)

    def _update_hotspots(self):
        """更新今日热点按钮"""
        if self.hotspots_frame is None:
            return

        hotspots: Optional[list[tuple[str, float, float, float]]] = getattr(self.master, 'concept_top5', None)
        
        # UI防抖: 如果数据没有变化，则跳过重绘
        new_sig = list(hotspots) if hotspots else []
        if getattr(self, '_last_hotspots', None) == new_sig:
            return
        self._last_hotspots = new_sig
            
        # 清空现有控件
        # assert self.hotspots_frame is not None
        for widget in self.hotspots_frame.winfo_children():
            widget.destroy()

        if hotspots:
            tk.Label(self.hotspots_frame, text="🔥今日热点:", font=("Arial", 9, "bold"), fg="red").pack(side="left", padx=(5, 2))
            for h in hotspots:
                # h = ('海南自贸区', 3.995, 4.17, 0.95)
                name: str = h[0]
                pct: float = h[2]
                btn_text = f"{name}({pct:.1f}%)"
                btn = tk.Button(self.hotspots_frame, text=btn_text, font=("Arial", 8), 
                                relief="flat", bg="#e8f5e9", fg="#2e7d32",
                                command=lambda n=name: self._quick_filter(n))
                btn.pack(side="left", padx=1)
            
            # Spacer at the end of the group
            tk.Frame(self.hotspots_frame, width=10).pack(side="left")

    def load_data(self, force: bool = False, target_date: Optional[str] = None):
        """
        加载/运行选股策略
        :param force: 是否强制重新运行
        :param target_date: 指定查询日期
        """
        if not self.selector:
            return

        query_date = target_date if target_date else self.current_date
        is_today = (query_date == datetime.now().strftime("%Y-%m-%d"))
        
        # 视觉反馈：如果是历史数据，修改窗口标题或状态
        if not is_today:
            self.title(f"策略选股 & 人工复核 [历史模式: {query_date}]")
        else:
            self.title("策略选股 & 人工复核")

        self._update_hotspots()
        # Clear items in batch for performance
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
            
        try:
            # --- Load Data Phase ---
            # 如果不是强制加载，且数据已经加载过一次，且日期匹配，则使用缓存
            # 注意：历史模式下，逻辑日期变更必须触发重新加载
            if not force and self._data_loaded and not self.df_full_candidates.empty and getattr(self, '_last_query_date', None) == query_date:
                # 使用缓存数据
                pass
            else:
                self.df_full_candidates = self.selector.get_candidates_df(force=force, logical_date=query_date)
                self._data_loaded = True
                self._last_query_date = query_date
                
                # 初始化用户标注列
                if not self.df_full_candidates.empty:
                    if 'user_status' not in self.df_full_candidates.columns:
                        self.df_full_candidates['user_status'] = "待定"
                    if 'user_reason' not in self.df_full_candidates.columns:
                        self.df_full_candidates['user_reason'] = ""
                
                # ✅ [OPTIMIZE] 重置列宽重测标记，确保新数据能重新计算宽度
                self._column_widths_cached = False

            # --- Filter & Display Phase ---
            if self.df_full_candidates.empty:
                self.df_candidates = pd.DataFrame()
                self._update_title_stats()
                return

            if self.selector is not None and hasattr(self.selector, 'df_all_realtime') and not self.selector.df_all_realtime.empty:
                # ✅ [FIX] 避免列重复导致的 overlap 错误
                # 如果 df_full_candidates 已存在这些列（可能来自缓存或重复调用），需先剔除
                overlap_cols = [c for c in ['昨日涨幅', '连阳涨幅', 'win', 'Rank'] if c in self.df_full_candidates.columns]
                if overlap_cols:
                    self.df_full_candidates.drop(columns=overlap_cols, inplace=True)
                
                # ✅ [OPTIMIZE] 使用 join 替代 merge，尤其是在已有索引时更轻量
                rt = self.selector.df_all_realtime[['per1d', 'sum_perc', 'win', 'Rank']].rename(columns={
                    'per1d': '昨日涨幅',
                    'sum_perc': '连阳涨幅',
                    'win': 'win',
                    'Rank': 'Rank'
                })
                # [PERF] join 比 merge (hash join) 更快，前提是右表已 set_index
                self.df_full_candidates = self.df_full_candidates.join(rt, on='code', how='left')
                # 填充 NaN 避免解析错误
                for col in ['昨日涨幅', '连阳涨幅', 'win', 'Rank']:
                    self.df_full_candidates[col] = self.df_full_candidates[col].fillna(0)
            else:
                # 兜底：如果实时行情还未就绪，补齐结构以防渲染报错
                for col in ['昨日涨幅', '连阳涨幅', 'win', 'Rank']:
                    if col not in self.df_full_candidates.columns:
                        self.df_full_candidates[col] = 0
            # 从全量缓存中复制，用于当前视窗的筛选/显示
            self.df_candidates = self.df_full_candidates.copy()

            # Apply Concept Filter
            filter_str = self.concept_filter_var.get().strip()
            if filter_str:
                # Support multi-keywords with space
                keywords = filter_str.split()
                for kw in keywords:
                    # Generic search: Code, Name, or Category
                    mask = (
                        self.df_candidates['category'].str.contains(kw, na=False) | 
                        self.df_candidates['code'].str.contains(kw, na=False) | 
                        self.df_candidates['name'].str.contains(kw, na=False)
                    )
                    self.df_candidates = self.df_candidates[mask]
            
            if self.df_candidates.empty:
                 self._update_title_stats()
                 # Don't show info if it's just a filter result
                 # messagebox.showinfo("提示", "筛选后无数据")
                 return
            
            # Default sorting: 连阳涨幅 descending
            if '连阳涨幅' in self.df_candidates.columns:
                self.df_candidates = self.df_candidates.sort_values(by='连阳涨幅', ascending=False)

            self._update_title_stats()

            # self.df_candidates['user_status'] = "待定"
            # self.df_candidates['user_reason'] = ""
            
            # --- Rendering Phase ---
            # ✅ [OPTIMIZE] 批量处理特征标记
            self._row_features = {}
            if self.feature_marker and not self.df_candidates.empty:
                try:
                    # 🚀 [PERF] 极致优化：如果 df_all_realtime 包含 code 索引，直接 loc 提取，避免 merge 消耗
                    # 同时只提取当前显示的候选股子集
                    rt_all = self.selector.df_all_realtime
                    cand_codes = self.df_candidates['code'].tolist()
                    # 仅选择存在的索引，避免 reindex 报错
                    valid_codes = [c for c in cand_codes if c in rt_all.index]
                    df_for_features = rt_all.loc[valid_codes]
                    
                    self._row_features = self.feature_marker.process_dataframe(df_for_features)
                except Exception as e:
                    logger.warning(f"Feature processing failed: {e}")

            # ✅ [OPTIMIZE] 采用“批量冻结 UI”渲染模式
            self._render_token += 1
            self._do_bulk_render(self._render_token)
            
        except Exception as e:
            logger.error(f"错误 加载数据失败: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("错误", f"加载数据失败: {e}")

    def _do_bulk_render(self, token: int):
        """
        🚀 [ULTIMATE PERF] 批量插入 + UI 渲染冻结
        bypass Tcl 层每行重绘产生的 O(n²) 级卡顿
        """
        if token != self._render_token:
            return
            
        if self.df_candidates.empty:
            return

        # 1. 冻结渲染 (通过隐藏所有列实现)
        all_cols = list(self.tree["columns"])
        self.tree.configure(displaycolumns=())
        
        try:
            # 2. 预准备所有数据行 (Python 快速构建，避免在 insert 循环内做 format/logic)
            # 使用 itertuples 遍历
            insert_batch = []
            for row in self.df_candidates.itertuples(index=False):
                code = str(row.code)
                user_status = getattr(row, 'user_status', "待定")
                user_reason = getattr(row, 'user_reason', "")
                
                tag = "pending"
                if user_status == "选中": tag = "selected"
                elif user_status == "丢弃": tag = "ignored"

                amount_raw = float(getattr(row, 'amount', 0))
                amount_str = f"{amount_raw/100000000:.2f}亿" if amount_raw >= 100000000 else f"{amount_raw/10000:.0f}万"

                display_name = row.name
                all_tags = [tag]
                if code in self._row_features:
                    f_tags, icon = self._row_features[code]
                    if f_tags: all_tags.extend(f_tags)
                    if icon: display_name = f"{icon} {display_name}"

                grade = getattr(row, 'grade', 'C')
                if grade == "S": all_tags.append("grade_S")
                elif grade == "A": all_tags.append("grade_A")

                # 批量插元组
                insert_batch.append((
                    code, display_name, grade,
                    f"{getattr(row, 'tqi', 0):.0f}",
                    getattr(row, 'status', ''),
                    str(int(getattr(row, 'score', 0))),
                    str(int(getattr(row, 'Rank', 0))),
                    getattr(row, 'price', 0),
                    f"{getattr(row, 'percent', 0):.2f}",
                    f"{getattr(row, '昨日涨幅', 0):.2f}",
                    f"{getattr(row, 'ratio', 0):.2f}",
                    amount_str,
                    getattr(row, '连阳涨幅', 0),
                    str(int(getattr(row, 'win', 0))),
                    getattr(row, 'volume', 0),
                    getattr(row, 'category', ''),
                    getattr(row, 'reason', ''),
                    user_status,
                    user_reason,
                    tuple(all_tags) # 最后一项辅助存 tags
                ))

            # 3. 阻塞式快速插入 (因为关闭了显示，此时耗时极短)
            for item in insert_batch:
                self.tree.insert("", "end", iid=item[0], values=item[:-1], tags=item[-1])

        finally:
            # 4. 恢复渲染并强制刷新
            self.tree.configure(displaycolumns=all_cols)
            self.tree.update_idletasks()

        # 5. 列宽自适应
        if not self._column_widths_cached:
            self.after(50, lambda: self._auto_fit_columns(force=False))

    def _auto_fit_columns(self, force: bool = False):
        """
        根据内容自动调整列宽
        :param force: 是否强制重新测量（默认缓存后不重测）
        """
        if not force and self._column_widths_cached:
            return

        import tkinter.font as tkfont
        f: tkfont.Font = tkfont.Font(font='Arial 9') # 与 treeview 字体保持一致
        
        cols: Any = self.tree["columns"]

        # 🚀 [PERF] 极致优化：将 get_children 提到循环外，采样结果也复用，避免每一列都重复构造 list
        all_items = self.tree.get_children()
        sample_items = all_items[:50] if len(all_items) > 50 else all_items
        
        # 为每列计算最大宽度
        for col in cols:
            # 获取表头文字宽度 (加一点 padding)
            header_text: str = self.tree.heading(col)["text"]
            max_w: int = f.measure(header_text) + 20
            
            for item in sample_items:
                cell_val: str = str(self.tree.set(item, col))
                # [PERF] 剔除超长文本测量，直接封顶
                if len(cell_val) > 100:
                    max_w = max(max_w, 400)
                    continue
                max_w = max(max_w, f.measure(cell_val) + 20)
            
            # 限制合理范围并应用
            if col in ["auto_reason", "category", "user_reason"]:
                max_w = min(max_w, 450)
            else:
                max_w = min(max_w, 200)
            
            _ = self.tree.column(col, width=max_w)
        
        self._column_widths_cached = True

    def _on_toolbar_double_click(self, event: Any):
        """双击顶部工具栏调整窗口宽度"""
        _ = event
        self._auto_fit_columns()
        # 计算所有列的总宽度
        total_w: float = 0
        for col in self.tree["columns"]:
            total_w += float(self.tree.column(col, "width"))
        
        # 加上边框和滚动条的宽度
        total_w += 40 
        # 保持高度，限制最大宽度
        screen_w = self.winfo_screenwidth()
        final_w = min(int(total_w), int(screen_w * 0.95))
        final_h = self.winfo_height()
        
        # 获取当前 x, y 坐标，尽量保持居中
        curr_x = self.winfo_x()
        curr_y = self.winfo_y()
        self.geometry(f"{final_w}x{final_h}+{curr_x}+{curr_y}")

    def _update_title_stats(self):
        """更新窗口标题统计信息：显示总数与最主要的Top 3机选理由"""
        base_title = "策略选股 & 人工复核"
        if self.df_candidates.empty:
            self.title(f"{base_title} (结果: 0)")
            return
            
        # 🚀 [PERF] 优化大盘理由扫描：利用 str.get_dummies 或 Series.str.cat 快速统计，
        # 避免在 UI 主循环中进行全量 list 扁平化。如果数据量巨大，这里会有毫秒级的卡顿。
        try:
            # 获取 reason 列并切分标签
            reasons = self.df_candidates['reason'].dropna().astype(str)
            if not reasons.empty:
                all_tags = []
                for r in reasons:
                    # 传统的 str.split 方案在大数据下优于复杂的正则
                    all_tags.extend([t.strip() for t in r.split('|') if t.strip()])
                counter = Counter(all_tags)
                top3 = counter.most_common(3)
                stats_str = " | ".join([f"{tag}({count})" for tag, count in top3])
            else:
                stats_str = ""
        except Exception:
            stats_str = "Error"
            
        # 获取等级分布 (value_counts 已经很高效了)
        if 'grade' in self.df_candidates.columns:
            grades = self.df_candidates['grade'].value_counts()
            grade_str = " | ".join([f"{g}:{grades.get(g, 0)}" for g in ["S", "A", "B"] if g in grades])
        else:
            grade_str = "N/A"
        
        total = len(self.df_candidates)
        if stats_str:
            new_title = f"{base_title} - [共{total}条 | 等级: {grade_str} | 理由期次: {stats_str}]"
        else:
            new_title = f"{base_title} - [共{total}条 | 等级: {grade_str}]"
            
        self.title(new_title)

    # === 历史记录与筛选逻辑 ===
    def load_history(self) -> list[str]:
        """从文件加载查询历史"""
        default_hotspots: list[str] = ['商业航天', '有色', '海峡两岸']
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    if isinstance(history, list):
                        return history
            # 文件不存在或格式错误，返回默认热点
            return default_hotspots
        except Exception as e:
            print(f"加载历史失败: {e}")
            return default_hotspots

    def update_history(self, query: str):
        """更新查询历史并保存"""
        query = query.strip()
        if not query:
            return
            
        if query in self.history:
            self.history.remove(query)
        
        self.history.insert(0, query)
        self.history = self.history[:20]  # 保留最近20个
        
        # 更新 UI
        if hasattr(self, 'concept_combo'):
            self.concept_combo['values'] = self.history
            
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存历史失败: {e}")

    def clear_filter(self):
        """清空筛选条件并查看全部结果"""
        self.concept_filter_var.set("")
        # self.load_data()
        self.on_filter_search()

    def delete_current_history(self):
        """删除当前选中的历史记录"""
        query = self.concept_filter_var.get().strip()
        if not query:
            return
            
        if query in self.history:
            if messagebox.askyesno("确认", f"确定要从历史记录中删除 '{query}' 吗？", parent=self):
                self.history.remove(query)
                # 更新 UI
                self.concept_combo['values'] = self.history
                self.concept_filter_var.set("") # 清空输入框
                
                # 保存到文件
                try:
                    with open(self.history_file, 'w', encoding='utf-8') as f:
                        json.dump(self.history, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    print(f"删除历史失败: {e}")
                
                # 重新加载数据（因为关键词清空了）
                self.load_data()

    def _quick_filter(self, name: str):
        """点击热点按钮快速筛选"""
        self.concept_filter_var.set(name)
        self.on_filter_search()

    def on_date_changed(self, event=None):
        """日期发生变化"""
        if HAS_CALENDAR:
            self.current_date = self.date_entry.get_date().strftime("%Y-%m-%d")
        else:
            self.current_date = self.date_var.get()
        
        # ✅ [USER-REQ] 切换日期时自动清空板块/关键字筛选，以显示该日全量数据
        if hasattr(self, 'concept_filter_var'):
            self.concept_filter_var.set("")

        # 切换日期时，自动加载该日期的历史记录 (非强制运行策略)
        self.load_data(force=False, target_date=self.current_date)

    def shift_date(self, delta: int):
        """快速切换日期"""
        try:
            curr = datetime.strptime(self.current_date, "%Y-%m-%d")
            # 使用 timedelta 替代 pd.Timedelta 以减少依赖 (虽然 pandas 已经导入了)
            from datetime import timedelta
            target = curr + timedelta(days=delta)
            target_str = target.strftime("%Y-%m-%d")
            
            if HAS_CALENDAR:
                self.date_entry.set_date(target)
            else:
                self.date_var.set(target_str)
            
            # ✅ [USER-REQ] 切换日期时自动清空板块筛选
            if hasattr(self, 'concept_filter_var'):
                self.concept_filter_var.set("")

            self.current_date = target_str
            self.load_data(force=False, target_date=self.current_date)
        except Exception as e:
            self.logger.error(f"Shift date failed: {e}")

    def _show_calendar(self):
        """打开日历下拉框"""
        if hasattr(self, 'date_entry'):
            self.date_entry.drop_down()

    def _refresh_calendar_highlights(self):
        """根据数据库记录在日历上高亮显示有数据的日期"""
        if not HAS_CALENDAR or not hasattr(self, 'date_entry') or not self.selector:
            return
            
        try:
            # 获取所有有数据的日期
            dates = self.selector.get_selection_dates()
            if not dates:
                return
            
            # ✅ [OPTIMIZE] 防抖：如果日期集合没变，跳过刷新
            dates_sig = hash(tuple(sorted(dates)))
            if getattr(self, '_last_calendar_sig', None) == dates_sig:
                return
            self._last_calendar_sig = dates_sig
            
            # 获取 DateEntry 内部的 Calendar 实例
            cal = self.date_entry._calendar
            
            # 清除之前的事件标签 (如果有)
            cal.calevent_remove('all', 'has_data')
            
            # 配置高亮样式: 红色背景 (代表该日有选股数据)
            cal.tag_config('has_data', background='red', foreground='white')
            
            for date_str in dates:
                try:
                    # 转换字符串为 datetime 对象
                    dt = datetime.strptime(str(date_str).split()[0], "%Y-%m-%d")
                    # 创建无文本事件供着色
                    cal.calevent_create(dt, 'Selection', 'has_data')
                except Exception as e:
                    # print(f"Invalid date format: {date_str}, {e}")
                    continue
            
            logger.info(f"✅ 选股日历已高亮 {len(dates)} 个日期")
        except Exception as e:
            logger.warning(f"⚠️ 刷新日历高亮失败: {e}")

    def on_filter_search(self, event: Optional[Any] = None):
        """执行查询并记录历史"""
        _ = event # Avoid unused variable warning
        query = self.concept_filter_var.get().strip()
        if query:
            self.update_history(query)
        self.load_data()

    def on_select(self, event):
        """
        选中事件：获取选中代码并尝试发送联动
        """
        selection = self.tree.selection()
        if not selection:
            return
            
        # 获取第一项
        item_id = selection[0]
        values = self.tree.item(item_id, "values")
        if values:
            stock_code = str(values[0]).zfill(6)
            
            # 1. 基础联动 (通达信/同花顺)
            if hasattr(self, 'sender') and self.sender:
                self.sender.send(stock_code)
            
            # 2. 可视化器联动 (基础跳转与时间同步)
            if self.master and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
                if hasattr(self.master, 'link_to_visualizer'):
                     # 🚀 [NEW] 用户需求：单击触发深度联动。如果是历史复盘 (非今天)，则强制同步时间
                     query_date = self.current_date
                     today_str = datetime.now().strftime("%Y-%m-%d")
                     
                     if query_date != today_str:
                         # 历史复盘模式：同步日期
                         self.master.link_to_visualizer(stock_code, query_date)
                         logger.info(f"SelectionWindow: Linked {stock_code} at {query_date} (History Mode)")
                     else:
                         # 今日实时模式：仅切换股票
                         self.master.open_visualizer(stock_code)

    def on_double_click(self, event):
        """🚀 [SIMPLIFIED] 双击现与单击逻辑对齐，复用联动逻辑"""
        self.on_select(event)

    # === 行选择逻辑 ===
    # def on_tree_select(self,event):
    #     sel = self.tree.selection()
    #     if not sel:
    #         return
    #     vals = tree.item(sel[0], "values")
    #     if not vals:
    #         return
    #     code = str(vals[0]).zfill(6)
    #     self.sender.send(str(vals[0]).zfill(6))

    def mark_status(self, status):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("提示", "请先选择股票")
            return
            
        reason = self.reason_var.get()
        tag = "selected" if status == "选中" else "ignored"
        
        for item_id in selected_items:
            # 获取当前值与标签
            cur_values = self.tree.item(item_id, "values")
            cur_tags = list(self.tree.item(item_id, "tags"))
            
            # 移除旧的状态标签 (selected, ignored, pending)
            filtered_tags = [t for t in cur_tags if t not in ("selected", "ignored", "pending")]
            # 将新的状态标签放在最前面（优先级最高）
            filtered_tags.insert(0, tag)
            
            # 更新显示值
            new_values = list(cur_values)
            new_values[14] = status
            new_values[15] = reason
            
            self.tree.item(item_id, values=new_values, tags=tuple(filtered_tags))
            
            # 同步更新缓存 DataFrame，以便在筛选后仍能保持标记状态
            code = cur_values[0]
            if not self.df_full_candidates.empty:
                # 寻找对应的代码并更新
                mask = self.df_full_candidates['code'] == code
                if mask.any():
                    self.df_full_candidates.loc[mask, 'user_status'] = status
                    self.df_full_candidates.loc[mask, 'user_reason'] = reason

    def import_selected(self):
        to_import = []
        feedback_data = []
        
        # Iterate all items to collect feedback and imports
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            code = values[0]
            name = values[1]
            status = values[14]
            user_reason = values[15]
            
            # 只要不是默认状态，就记录反馈以便优化
            if status != "待定":
                feedback_data.append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "code": code,
                    "name": name,
                    "auto_score": values[3],
                    "auto_reason": values[13],
                    "user_status": status,
                    "user_reason": user_reason
                })
            
            if status == "选中":
                to_import.append({
                    "code": code,
                    "name": name,
                    "price": float(values[4]),
                    "score": float(values[3]),
                    "percent": float(values[5].replace('%', '') if isinstance(values[5], str) else values[5]),
                    "ratio": float(values[7]),
                    "amount": values[8],
                    "auto_reason": values[13],
                    "user_reason": values[15]
                })
        
        if not to_import:
            if not messagebox.askyesno("确认", "未标记任何[选中]的股票。\n是否仅保存反馈并关闭？"):
                return
        
        # 1. Update Monitor List
        if to_import and self.live_strategy:
            count = 0
            if hasattr(self.live_strategy, '_monitored_stocks'):
                existing = self.live_strategy._monitored_stocks
                for item in to_import:
                    code = item["code"]
                    if code not in existing:
                        existing[code] = {
                            "name": item["name"],
                            "rules": [
                                {"type": "price_up", "value": item["price"]}
                            ],
                            "last_alert": 0,
                            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "tags": "manual_verified", 
                            "snapshot": {
                                "trade": item["price"],
                                "percent": item["percent"],
                                "ratio": item["ratio"],
                                "amount_desc": item["amount"],
                                "score": item["score"],
                                "reason": item["auto_reason"],
                                "user_reason": item["user_reason"]
                            }
                        }
                        count += 1
                    else:
                        # 如果已存在，更新规则和快照（权重更新）
                        if not existing[code].get('rules'):
                            existing[code]['rules'] = [{"type": "price_up", "value": item["price"]}]
                        
                        # 更新快照以反映最新的权重和评分
                        existing[code]['snapshot'].update({
                            "score": item["score"],
                            "reason": item["auto_reason"],
                            "user_reason": item["user_reason"]
                        })
                        # 重新标记为人工确认
                        if "manual_verified" not in str(existing[code].get('tags', '')):
                            existing[code]['tags'] = "manual_verified"
                        count += 1
                
                if count > 0:
                    if hasattr(self.live_strategy, '_save_monitors'):
                        self.live_strategy._save_monitors()
                    
                    # ⭐ 推送到信号队列 (独立DB)
                    try:
                        from signal_message_queue import SignalMessageQueue, SignalMessage
                        queue = SignalMessageQueue()
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        for item in to_import:
                            # 构建信号消息
                            q_msg = SignalMessage(
                                priority=40, # 用户选择优先级较高
                                timestamp=timestamp,
                                code=str(item["code"]).zfill(6),
                                name=item["name"],
                                signal_type="USER_SELECT",
                                source="SELECTOR",
                                reason=f"{item.get('user_reason','')} | {item.get('auto_reason','')}",
                                score=item.get("score", 0)
                            )
                            queue.push(q_msg)
                            
                    except ImportError:
                        pass
                    except Exception as e:
                        logger.error(f"Failed to push signal to queue: {e}")
                    
                    # 尝试通知语音监控窗口刷新 (如果已打开)
                    vm_win = getattr(self.master, '_voice_monitor_window', None)
                    if vm_win and vm_win.winfo_exists() and hasattr(vm_win, 'refresh_list'):
                        vm_win.refresh_list()
                        
                    messagebox.showinfo("成功", f"成功导入 {count} 只新股票到监控列表！")
                else:
                    messagebox.showinfo("提示", "所选股票已在监控列表中且已有活跃规则。")
        
        # 2. Save Feedback
        self.save_feedback(feedback_data)
        
        # Close
        # self.destroy()

    def save_feedback(self, data):
        if not data: return
        try:
            df = pd.DataFrame(data)
            file_path = "stock_selection_feedback.csv"
            header = not os.path.exists(file_path)
            df.to_csv(file_path, mode='a', header=header, index=False, encoding='utf-8')
            print(f"反馈日志已保存: {file_path}")
        except Exception as e:
            messagebox.showerror("日志错误", f"保存反馈日志失败: {e}")

    def sort_tree(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        # 尝试转为数字排序
        try:
            # 针对 rank 列或其他整数列，优先尝试 int，再 float
            l.sort(key=lambda t: float(t[0]) if t[0] and t[0].strip() else -1, reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))

    def show_context_menu(self, event):
        """显示右键菜单"""
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        self.tree.selection_set(item_id)
        code = item_id

        menu = tk.Menu(self, tearoff=0)

        # 定义命令（先保存）
        cmd = lambda: self.tree_scroll_to_code(code)

        menu.add_command(
            label=f"定位股票代码: {code}",
            command=cmd
        )

        # === 关键逻辑 ===
        if menu.index("end") == 0:
            # 只有一项，直接执行
            cmd()
        else:
            # 多项才弹出菜单
            menu.post(event.x_root, event.y_root)
    


    def on_history_track_clicked(self):
        """打开多日选股追踪对比窗口"""
        if not self.selector:
            messagebox.showwarning("提示", "未初始化选股器，无法追踪。")
            return
        
        # 记录弹窗状态，避免复选导致重复
        if hasattr(self, '_history_track_win') and self._history_track_win.winfo_exists():
            self._history_track_win.lift()
            self._history_track_win.focus_force()
            return

        self._history_track_win = HistoricalSelectionTrackerDialog(self, self.selector)
        self._history_track_win.focus_set()

# ==============================================================================
# --- 选股多日追踪对比专用类 ---
# ==============================================================================

class HistoricalSelectionTrackerWorker(threading.Thread):
    """异步选股追踪工作线程：聚合历史选股结论并分析当前的 ROI 与连贯性"""
    def __init__(self, days, selector, main_window, callback_queue):
        super().__init__()
        self.days = days
        self.selector = selector
        self.main_window = main_window
        self.callback_queue = callback_queue
        self.daemon = True
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            # 1. 获取所有有数据的日期
            all_dates = self.selector.get_selection_dates()
            if not all_dates:
                self.callback_queue.put(('finished', []))
                return
            
            target_dates = all_dates[:self.days]
            # 🚀 [FIX] 从远及近遍历，确保 base_price 是该时间段内“首次出现”的价格
            target_dates_rev = list(reversed(target_dates))
            self.callback_queue.put(('progress', f"正在从 {target_dates_rev[0]} 开始聚合 {len(target_dates_rev)} 天记录..."))
            
            # code -> {base_p, hits, name, sector, scores, dates}
            stats = {}
            for i, d_str in enumerate(target_dates_rev):
                if self._stop_event.is_set(): return
                
                # normalize date
                d_obj = pd.to_datetime(d_str).strftime("%Y-%m-%d")
                self.callback_queue.put(('progress', f"📂 读取 [{d_obj}] ({i+1}/{len(target_dates_rev)})..."))
                
                df = self.selector.get_candidates_df(logical_date=d_obj)
                if df.empty: continue
                
                for _, row in df.iterrows():
                    code = row['code']
                    p = float(row.get('price', 0))
                    
                    if code not in stats:
                        stats[code] = {
                            'code': code, 'name': row.get('name', '--'),
                            'sector': row.get('category', 'N/A'),
                            'hits': 1, 'base_price': p,
                            'max_score': float(row.get('score', 0)),
                            'dates': [d_obj]
                        }
                    else:
                        stats[code]['hits'] += 1
                        stats[code]['max_score'] = max(stats[code]['max_score'], float(row.get('score', 0)))
                        stats[code]['dates'].append(d_obj)
                        # 如果初始基准价无效，尝试补齐
                        if stats[code]['base_price'] <= 0 and p > 0:
                            stats[code]['base_price'] = p

            # 2. 获取实时行情对比
            all_codes = list(stats.keys())
            self.callback_queue.put(('progress', f"📡 刷新 {len(all_codes)} 只个股的实时对比数据..."))
            
            # 尝试从主控的实时库中获取
            realtime_df = getattr(self.selector, 'df_all_realtime', pd.DataFrame())
            
            results = []
            for code, item in stats.items():
                curr_p = item['base_price']
                curr_pct = 0.0
                
                if not realtime_df.empty and code in realtime_df.index:
                    row_rt = realtime_df.loc[code]
                    curr_p = float(row_rt.get('price', row_rt.get('close', item['base_price'])))
                    curr_pct = float(row_rt.get('percent', 0))
                
                # 计算 ROI (相对于选股基准价)
                roi = (curr_p / item['base_price'] - 1) * 100 if item['base_price'] > 0 else 0
                item['curr_price'] = curr_p
                item['curr_pct'] = curr_pct
                item['roi'] = roi
                
                # 简单形态/暗示
                phase = "震荡"
                if roi > 8: phase = "强势跃迁"
                elif roi > 2: phase = "温和上行"
                elif roi < -5: phase = "回撤分歧"
                
                item['pattern'] = f"{phase} (命中:{item['hits']})"
                
                # 排序权重: 命中数 * 10 + ROI * 2
                item['potential_score'] = item['hits'] * 10.0 + roi * 2.0
                results.append(item)

            results.sort(key=lambda x: x['potential_score'], reverse=True)
            self.callback_queue.put(('finished', results))
            
        except Exception as e:
            logger.error(f"SelectionTracker Error: {e}")
            self.callback_queue.put(('error', str(e)))

class HistoricalSelectionTrackerDialog(tk.Toplevel, WindowMixin):
    """选股多日追踪对比弹窗 (Tkinter 版)"""
    def __init__(self, parent, selector):
        super().__init__(parent)
        self.parent_win = parent
        self.selector = selector
        self.master_win = parent.master
        
        self.title("🔍 选股多日追踪对比 (由近及远)")
        self.geometry("1100x650")
        self.load_window_position(self, "选股历史追踪", default_width=1100, default_height=650)
        
        self._all_results = []
        self._is_populating = False
        self._queue = queue.Queue()
        self._worker = None

        self._init_ui()
        self.after(200, lambda: self._start_analysis())
        
        # 定时检查队列数据
        self._check_queue_id = self.after(300, self._process_queue)
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_ui(self):
        # 1. Toolbar
        toolbar = tk.Frame(self, pady=5)
        toolbar.pack(fill="x", padx=10)
        
        tk.Label(toolbar, text="📅 分析天数:").pack(side="left")
        self.spin_days = tk.Spinbox(toolbar, from_=1, to=100, width=5)
        self.spin_days.delete(0, "end")
        self.spin_days.insert(0, "5")
        self.spin_days.pack(side="left", padx=5)
        
        self.btn_refresh = tk.Button(toolbar, text="🚀 开启分析", command=self._start_analysis, bg="#2c3e50", fg="white", font=("Arial", 9, "bold"))
        self.btn_refresh.pack(side="left", padx=5)

        # 快速周期按钮
        for text, days in [("1周", 5), ("2周", 10), ("1月", 22)]:
            btn = tk.Button(toolbar, text=text, command=lambda d=days: self._quick_set_days(d), 
                            bg="#ecf0f1", fg="#2c3e50", font=("Arial", 9), padx=5)
            btn.pack(side="left", padx=1)
        
        tk.Label(toolbar, text="🔍 筛选:").pack(side="left", padx=(20, 2))
        self.search_var = tk.StringVar()
        self.entry_search = tk.Entry(toolbar, textvariable=self.search_var, width=15)
        self.entry_search.pack(side="left", padx=2)
        self.search_var.trace_add("write", lambda *args: self._apply_filter())
        
        self.status_lbl = tk.Label(toolbar, text="准备就绪", fg="#ff9900", font=("Arial", 9, "bold"))
        self.status_lbl.pack(side="right", padx=10)

        # 2. Results Table
        columns = ("code", "name", "hits", "sector", "base_price", "curr_price", "roi", "pattern")
        headers = {
            "code": "代码", "name": "名称", "hits": "次数", "sector": "板块",
            "base_price": "历史基准价", "curr_price": "现价", "roi": "ROI", "pattern": "形态暗示/状态"
        }
        
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        for col, text in headers.items():
            self.tree.heading(col, text=text, command=lambda c=col: self._sort_tree(c, True))
            self.tree.column(col, anchor="center", width=80)
        
        self.tree.column("pattern", width=250, anchor="w", stretch=True)
        self.tree.column("sector", width=120)
        
        # Tags
        self.tree.tag_configure("plus", foreground="#e91e63", font=("Arial", 9, "bold")) # 红涨
        self.tree.tag_configure("minus", foreground="#388e3c", font=("Arial", 9, "bold")) # 绿跌
        self.tree.tag_configure("high_hits", background="#e8f5e9") # 高命中背景
        
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._on_select(e, force_link=True))

    def _quick_set_days(self, days: int):
        """快捷设置天数并启动分析"""
        self.spin_days.delete(0, "end")
        self.spin_days.insert(0, str(days))
        self._start_analysis()

    def _start_analysis(self):
        if self._worker and self._worker.is_alive():
            return
        
        try:
            days = int(self.spin_days.get())
        except: days = 5
        
        self.btn_refresh.config(state="disabled", text="分析中...")
        self.tree.delete(*self.tree.get_children())
        self._all_results = []
        
        main_win = getattr(self.parent_win, 'master', self.parent_win)
        self._worker = HistoricalSelectionTrackerWorker(days, self.selector, main_win, self._queue)
        self._worker.start()

    def _process_queue(self):
        """主线程定时处理 worker 推来的信号"""
        try:
            while True:
                msg_type, data = self._queue.get_nowait()
                if msg_type == 'progress':
                    self.status_lbl.config(text=data)
                elif msg_type == 'finished':
                    self._on_data_ready(data)
                elif msg_type == 'error':
                    self.status_lbl.config(text=f"❌ 运行出错", fg="red")
                    messagebox.showerror("分析错误", data)
                    self.btn_refresh.config(state="normal", text="🚀 开启分析")
                self._queue.task_done()
        except queue.Empty:
            pass
        finally:
            if self.winfo_exists():
                self._check_queue_id = self.after(200, self._process_queue)

    def _on_data_ready(self, results):
        self._all_results = results
        self.status_lbl.config(text=f"✅ 完成！共追踪 {len(results)} 只个股", fg="#00cc00")
        self.btn_refresh.config(state="normal", text="🚀 重新统计")
        self._apply_filter()

    def _apply_filter(self):
        self.tree.delete(*self.tree.get_children())
        query = self.search_var.get().lower()
        
        for item in self._all_results:
            if query and query not in item['code'] and query not in item['name'] and query not in item['sector'].lower():
                continue
            
            roi = item['roi']
            tag = "plus" if roi > 0 else ("minus" if roi < 0 else "")
            
            all_tags = [tag]
            if item['hits'] >= 3: all_tags.append("high_hits")
            
            self.tree.insert("", "end", iid=item['code'], values=(
                item['code'], item['name'], item['hits'], item['sector'],
                f"{item['base_price']:.2f}", f"{item['curr_price']:.2f}",
                f"{roi:+.2f}%", item['pattern']
            ), tags=tuple(all_tags))

    def _on_select(self, event, force_link=False):
        sel = self.tree.selection()
        if not sel: return
        
        code = sel[0]
        # 联动主界面
        if hasattr(self.parent_win, 'tree_scroll_to_code'):
             self.parent_win.tree_scroll_to_code(code)
        
        # 🚀 [NEW] 核心联动逻辑：同步历史追踪标记
        if self.master_win and hasattr(self.master_win, 'link_to_visualizer'):
            # 找到该股最近一次出现在选股历史中的日期
            target = next((d for d in self._all_results if d['code'] == code), None)
            if target and target['dates']:
                # 🚀 [FIX] 从远及近遍历后，索引 0 即为该统计区间内的“最早”入选日期 (基准锚点)
                first_date = target['dates'][0] 
                self.master_win.link_to_visualizer(code, first_date)
                logger.info(f"[HistoryTrack] Linked {code} at {first_date} (Historical selection benchmark)")

    def _on_close(self):
        if self._worker: self._worker.stop()
        if hasattr(self, '_check_queue_id'): self.after_cancel(self._check_queue_id)
        self.save_window_position(self, "选股历史追踪")
        self.destroy()

    def _sort_tree(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try:
            l.sort(key=lambda t: float(t[0].replace('%','')) if t[0] and t[0].strip() else -999, reverse=reverse)
        except:
            l.sort(reverse=reverse)
        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self._sort_tree(col, not reverse))

