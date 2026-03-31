import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
from datetime import datetime
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
            # Make the entire entry clickable
            self.date_entry.bind("<Button-1>", lambda e: self.date_entry.drop_down())
        else:
            self.date_var = tk.StringVar(value=self.current_date)
            self.date_tk_entry = tk.Entry(toolbar, textvariable=self.date_var, width=11)
            self.date_tk_entry.pack(side="left", padx=2)
            tk.Button(toolbar, text="Go", command=self.on_date_changed, width=3).pack(side="left")

        # Quick Navigation
        tk.Button(toolbar, text="◀", command=lambda: self.shift_date(-1), width=2).pack(side="left", padx=1)
        tk.Button(toolbar, text="▶", command=lambda: self.shift_date(1), width=2).pack(side="left", padx=1)

        tk.Button(toolbar, text="🚀 导入", command=self.import_selected, bg="#ffd54f", font=("Arial", 10, "bold")).pack(side="left", padx=10, pady=5)


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

            # --- Filter & Display Phase ---
            if self.df_full_candidates.empty:
                self.df_candidates = pd.DataFrame()
                self._update_title_stats()
                return

            # if self.live_strategy is not None and hasattr(self.live_strategy, 'df') and 'sum_perc' in self.live_strategy.df.columns:
            if self.selector is not None and hasattr(self.selector, 'df_all_realtime') and 'sum_perc' in self.selector.df_all_realtime.columns:
                # 按索引对齐取值
                # 使用 selector 缓存的实时数据进行映射，避免 live_strategy 为 None 时报错
                self.df_full_candidates['昨日涨幅'] = self.df_full_candidates['code'].map(self.selector.df_all_realtime['per1d']).fillna(0)
                self.df_full_candidates['连阳涨幅'] = self.df_full_candidates['code'].map(self.selector.df_all_realtime['sum_perc']).fillna(0)
                self.df_full_candidates['win'] = self.df_full_candidates['code'].map(self.selector.df_all_realtime['win']).fillna(0)
                self.df_full_candidates['Rank'] = self.df_full_candidates['code'].map(self.selector.df_all_realtime['Rank']).fillna(0)
            else:
                # live_strategy 不存在或列缺失，全部填 0
                self.df_full_candidates['昨日涨幅'] = 0
                self.df_full_candidates['连阳涨幅'] = 0
                self.df_full_candidates['win'] = 0
                self.df_full_candidates['Rank'] = 0
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
            
            for index, row in self.df_candidates.iterrows():
                # 获取已有的用户标注（如果存在）
                user_status = row.get('user_status', "待定")
                user_reason = row.get('user_reason', "")
                
                # 设置对应的标签记录颜色
                tag = "pending"
                if user_status == "选中": tag = "selected"
                elif user_status == "丢弃": tag = "ignored"

                amount_raw = float(row.get('amount', 0))
                amount_str = f"{amount_raw/100000000:.2f}亿" if amount_raw >= 100000000 else f"{amount_raw/10000:.0f}万"

                # ✅ 整合 StockFeatureMarker 颜色标记与图标
                all_tags = [tag]
                display_name = row['name']
                if self.feature_marker:
                    code = row['code']
                    # 🚀 关键：优先从 selector.df_all_realtime 中获取最新且完整的技术指标
                    # df_candidates 可能只包含基础字段，而 df_all_realtime 包含 high4, max5 等全量计算结果
                    if self.selector is not None and hasattr(self.selector, 'df_all_realtime') and code in self.selector.df_all_realtime.index:
                        s_data = self.selector.df_all_realtime.loc[code]
                    else:
                        s_data = row
                        
                    row_dict = {
                        'percent': s_data.get('percent', 0),
                        'volume': s_data.get('volume', 0),
                        'category': s_data.get('category', ''),
                        # 详细指标支持（从实时全量库中提取）
                        'price': s_data.get('price', s_data.get('trade', 0)),
                        'high4': s_data.get('high4', 0),
                        'max5': s_data.get('max5', 0),
                        'max10': s_data.get('max10', 0),
                        'hmax': s_data.get('hmax', 0),
                        'hmax60': s_data.get('hmax60', 0),
                        'low4': s_data.get('low4', 0),
                        'low10': s_data.get('low10', 0),
                        'low60': s_data.get('low60', 0),
                        'lmin': s_data.get('lmin', 0),
                        'min5': s_data.get('min5', 0),
                        'cmean': s_data.get('cmean', 0),
                        'hv': s_data.get('hv', 0),
                        'lv': s_data.get('lv', 0),
                        'llowvol': s_data.get('llowvol', 0),
                        'lastdu4': s_data.get('lastdu4', 0)
                    }
                    
                    # 应用颜色标签
                    if self.feature_marker.enable_colors:
                        extra_tags = self.feature_marker.get_tags_for_row(row_dict)
                        if extra_tags:
                            all_tags.extend(extra_tags)
                    
                    # 应用图标
                    icon = self.feature_marker.get_icon_for_row(row_dict)
                    if icon:
                        display_name = f"{icon} {display_name}"

                # 格式化各个字段，增强对 None/NaN 的健壮性
                score_val = row.get('score', 0)
                score_str = str(int(score_val)) if pd.notna(score_val) else "0"

                win_val = row.get('win', 0)
                win_str = str(int(win_val)) if pd.notna(win_val) else "0"
                
                rank_val = row.get('Rank', 0)
                rank_str = str(int(rank_val)) if pd.notna(rank_val) else "0"

                grade = row.get('grade', 'C')
                if grade == "S": all_tags.append("grade_S")
                elif grade == "A": all_tags.append("grade_A")

                tqi_val = row.get('tqi', 0)
                tqi_str = f"{tqi_val:.0f}" if pd.notna(tqi_val) else "0"
                
                pct_val = row.get('percent', 0)
                pct_str = f"{pct_val:.2f}" if pd.notna(pct_val) else "0.00"
                
                yest_pct_val = row.get('昨日涨幅', 0)
                yest_pct_str = f"{yest_pct_val:.2f}" if pd.notna(yest_pct_val) else "0.00"
                
                ratio_val = row.get('ratio', 0)
                ratio_str = f"{ratio_val:.2f}" if pd.notna(ratio_val) else "0.00"

                self.tree.insert("", "end", iid=row['code'], values=(
                    row['code'], display_name, grade, tqi_str, row.get('status', ''), score_str, rank_str, row['price'], 
                    pct_str, yest_pct_str, ratio_str, amount_str,
                    row.get('连阳涨幅', 0), win_str, row['volume'], row.get('category', ''), row['reason'], 
                    user_status, user_reason
                ), tags=tuple(all_tags))
            
            # 渲染完成后自动调整列宽
            self.after(100, self._auto_fit_columns)
                
        except Exception as e:
            logger.error(f"错误 加载数据失败: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("错误", f"加载数据失败: {e}")

    def _auto_fit_columns(self):
        """根据内容自动调整列宽"""
        import tkinter.font as tkfont
        f: tkfont.Font = tkfont.Font(font='Arial 9') # 与 treeview 字体保持一致
        
        cols: Any = self.tree["columns"]
        # 为每列计算最大宽度
        for col in cols:
            # 获取表头文字宽度 (加一点 padding)
            header_text: str = self.tree.heading(col)["text"]
            max_w: int = f.measure(header_text) + 20
            
            # 获取采样行该列的内容 (限制数量以提升性能)
            all_items = self.tree.get_children()
            sample_items = all_items[:100] if len(all_items) > 100 else all_items
            for item in sample_items:
                cell_val: str = str(self.tree.set(item, col))
                max_w = max(max_w, f.measure(cell_val) + 20)
            
            # 限制合理范围并应用
            if col in ["auto_reason", "category", "user_reason"]:
                max_w = min(max_w, 450)
            else:
                max_w = min(max_w, 200)
            
            _ = self.tree.column(col, width=max_w)

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
            
        all_tags = []
        # 'reason' 列存储了机选理由，可能由 '|' 分隔
        for r in self.df_candidates['reason'].dropna():
            tags = [t.strip() for t in str(r).split('|') if t.strip()]
            all_tags.extend(tags)
            
        counter = Counter(all_tags)
        # 获取 Top 3 理由
        top3 = counter.most_common(3)
        stats_str = ""
        if top3:
            stats_str = " | ".join([f"{tag}({count})" for tag, count in top3])
            
        # 获取等级分布
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
            
            self.current_date = target_str
            self.load_data(force=False, target_date=self.current_date)
        except Exception as e:
            self.logger.error(f"Shift date failed: {e}")

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
            stock_code = values[0]
            # 发送联动
            if stock_code and hasattr(self, 'sender') and self.sender:
                self.sender.send(stock_code)
            # ⭐ 可视化器联动
            if stock_code and  self.master and getattr(self.master, "_vis_enabled_cache", False):
                if hasattr(self.master, 'open_visualizer'):
                    self.master.open_visualizer(str(stock_code))

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
    

    def tree_scroll_to_code(self, code: str):
        """定位股票代码 (通过筛选器)"""
        if hasattr(self, 'master') and hasattr(self.master, 'tree_scroll_to_code'):
            self.master.tree_scroll_to_code(code,select_win=True)
        # elif hasattr(self, 'concept_filter_var'):
        #     self.concept_filter_var.set(code)
        #     self.on_filter_search()

