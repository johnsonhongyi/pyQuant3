from logger_utils import LoggerFactory
import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import re
from datetime import datetime
import threading
import queue
import time
from typing import Optional, Any, TYPE_CHECKING
from collections import Counter
import pandas as pd
from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
import logging
from JohnsonUtil import commonTips as cct
logger = LoggerFactory.getLogger(__name__)
from sys_utils import get_app_root

# ✅ 盘中交易引擎（懒加载，避免启动依赖）
try:
    from sector_focus_engine import get_focus_controller, SectorFocusController
    from trade_gateway import get_trade_gateway, MockTradeGateway
    TRADING_ENGINE_AVAILABLE = True
except ImportError:
    TRADING_ENGINE_AVAILABLE = False
    logger.warning("⚠️ 盘中交易引擎未加载（sector_focus_engine / trade_gateway 缺失）")

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
    import JohnsonUtil.tkcalendar_patch
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
        
        # 🚀 [FIX] 交易日智能判定：如果是交易日则用今天，否则用上个交易日
        if cct.get_trade_date_status():
            self.current_date = datetime.now().strftime('%Y-%m-%d')
        else:
            self.current_date = cct.get_last_trade_date()
        
        # ✅ 性能优化标记
        self._column_widths_cached = False
        self._rendering_active = False # 防止并发渲染
        self._render_token = 0         # 标识当前渲染批次
        self._concept_detail_win = None # 🚀 [NEW] 板块大字详情窗口复用缓存

        # ✅ 盘中交易引擎引用
        self._focus_ctrl: Optional['SectorFocusController'] = None
        self._trade_gw: Optional['MockTradeGateway'] = None
        if TRADING_ENGINE_AVAILABLE:
            try:
                self._focus_ctrl = get_focus_controller()
                self._trade_gw   = get_trade_gateway()
            except Exception as _e:
                logger.warning(f"⚠️ 引擎初始化失败: {_e}")
        
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
        
        # 🚀 [NEW] 延时 250ms 等待 UI 充分绘制渲染完毕后，高保真恢复板块聚焦与决策队列 sash 窗格分割高度及每日操作指南列宽
        self.after(250, lambda: [self._restore_sash_positions(), self._restore_guidance_column_widths()])

    def _on_close(self, window_id: str):
        """关闭时保存状态并销毁窗口"""
        # 🚀 [NEW] 级联销毁所有打开的交易确认弹窗，防止残留
        try:
            if hasattr(self, "_active_confirm_wins"):
                for code, win in list(self._active_confirm_wins.items()):
                    if win and win.winfo_exists():
                        win.destroy()
                self._active_confirm_wins.clear()
        except Exception:
            pass

        # 🚀 [NEW] 保存板块聚焦和实时决策的 sash 窗格分割高度位置以及每日操作指南列宽
        try:
            self._save_sash_positions()
        except Exception as e:
            logger.error(f"[sash_positions] Save failed: {e}")
        try:
            self._save_guidance_column_widths()
        except Exception as e:
            logger.error(f"[guidance_column_widths] Save failed: {e}")
        # [NEW] 关闭并保存浮动交易看板
        try:
            win = getattr(self, "_kernel_toast_win", None)
            if win and win.winfo_exists():
                try:
                    self.save_window_position(win, "kernel_toast_window")
                except Exception:
                    pass
                win.destroy()
        except Exception:
            pass

        # [NEW] 停止高亮行慢闪烁呼吸定时器
        try:
            blink_id = getattr(self, "_kernel_blink_id", None)
            if blink_id:
                self.after_cancel(blink_id)
        except Exception:
            pass

        # ✅ [FIX] 清除主窗口中的引用，防止对象已销毁但引用依然存在的异常
        if hasattr(self.master, '_stock_selection_win'):
            self.master._stock_selection_win = None
            
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

    def _save_sash_positions(self):
        """保存板块聚焦和实时决策的 sash 垂直高度分割坐标（按 DPI 比例还原）"""
        try:
            scale = self._get_dpi_scale_factor()
            # 复用 window_mixin.py 中导入的 WINDOW_CONFIG_FILE 配置文件常量
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            
            sash_pos = {}
            if hasattr(self, '_sector_paned'):
                try:
                    sash_pos['sector_y'] = int(self._sector_paned.sash_coord(0)[1] / scale)
                except Exception:
                    pass
            if hasattr(self, '_decision_paned'):
                try:
                    sash_pos['decision_y'] = int(self._decision_paned.sash_coord(0)[1] / scale)
                except Exception:
                    pass
            
            data = {}
            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            data['sash_positions'] = sash_pos
            
            tmp_file = config_file_path + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(tmp_file, config_file_path)
            logger.debug(f"[sash_positions] Saved: {sash_pos}")
        except Exception as e:
            logger.error(f"[sash_positions] Save failed: {e}")

    def _restore_sash_positions(self):
        """从配置文件加载并高保真还原板块聚焦和实时决策的 sash 分割线位置（自适应 DPI）"""
        try:
            scale = self._get_dpi_scale_factor()
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            
            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                sash_pos = data.get('sash_positions', {})
                if 'sector_y' in sash_pos and hasattr(self, '_sector_paned'):
                    try:
                        y = int(sash_pos['sector_y'] * scale)
                        x = self._sector_paned.sash_coord(0)[0]
                        self._sector_paned.sash_place(0, x, y)
                        logger.debug(f"[sash_positions] Sector restored to y={y}")
                    except Exception as e:
                        logger.debug(f"[sash_positions] Sector restore fail: {e}")
                        
                if 'decision_y' in sash_pos and hasattr(self, '_decision_paned'):
                    try:
                        y = int(sash_pos['decision_y'] * scale)
                        x = self._decision_paned.sash_coord(0)[0]
                        self._decision_paned.sash_place(0, x, y)
                        logger.debug(f"[sash_positions] Decision restored to y={y}")
                    except Exception as e:
                        logger.debug(f"[sash_positions] Decision restore fail: {e}")
        except Exception as e:
            logger.error(f"[sash_positions] Restore failed: {e}")

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
        
        # 针对 Windows 默认主题下 Treeview 的原生缺陷进行精准修复，专门解锁默认 Treeview 与 Dark.Treeview 的 tag_configure 背景渲染且不改变全局主题
        try:
            # 极客暗黑夜色样式
            style.configure("Dark.Treeview", background="#0c101b", fieldbackground="#0c101b", foreground="#ffffff")
            
            def fixed_map(style_name, option):
                return [elm for elm in style.map(style_name, query_opt=option) if elm[:2] != ("!disabled", "!selected")]
                
            style.map("Dark.Treeview",
                      foreground=[("selected", "#55ffff")] + fixed_map("Dark.Treeview", "foreground"),
                      background=[("selected", "#1a3a5f")] + fixed_map("Dark.Treeview", "background"))
                      
            # 对默认的 Treeview 样式进行解锁，使原生白底表格在 Windows 主题下能正确渲染 tag_configure 的行背景（浅绿/浅红），绝不退化为黑白灰
            style.map("Treeview",
                      foreground=[("selected", "#ffffff")] + fixed_map("Treeview", "foreground"),
                      background=[("selected", "#0078d7")] + fixed_map("Treeview", "background"))
        except Exception:
            pass
        
        # --- Toolbar ---
        toolbar = tk.Frame(self, bd=1, relief="raised")
        toolbar.pack(fill="x", padx=5, pady=5)

        # Today's Hotspots (Quick Filter Buttons)
        # Today's Hotspots (Quick Filter Buttons)
        # Today's Hotspots (Quick Filter Buttons)
        self.hotspots_frame = tk.Frame(toolbar)
        self.hotspots_frame.pack(side="left")
        # Initial update handled in load_data or explicit call if needed (load_data is called at end of init)
        
        # 🔍 Multi-day Tracking Button
        tk.Button(toolbar, text="🔍 追踪", command=self.on_history_track_clicked, bg="#2a3a4a", fg="#ff9900", font=("Arial", 10, "bold")).pack(side="left", padx=5, pady=5)

        # Concept Filter
        tk.Label(toolbar, text="板块", font=("Arial", 10)).pack(side="left", padx=2)
        tk.Button(toolbar, text="🧹", command=self.clear_filter, width=2).pack(side="left", padx=1)
        self.concept_filter_var: tk.StringVar = tk.StringVar()
        self.concept_combo: ttk.Combobox = ttk.Combobox(toolbar, textvariable=self.concept_filter_var, width=10)
        self.concept_combo['values'] = self.history
        self.concept_combo.pack(side="left", padx=2)
        # 🚀 [NEW] 右键自动粘贴剪贴板内容并触发过滤
        self.concept_combo.bind("<Button-3>", self._on_concept_combo_right_click)

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
            # 🚀 [FIX] 使用智能判定的交易日
            try:
                self.date_entry.set_date(datetime.strptime(self.current_date, "%Y-%m-%d"))
            except:
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

        # 🚀 [NEW] DNA审计按钮贴行附加
        tk.Button(toolbar, text="🧬 DNA审计", bg="#333333", fg="#ffffff", font=("Arial", 9, "bold"), command=self._run_dna_audit_selected).pack(side="left", padx=5, pady=5)

        tk.Button(toolbar, text="🚀 导入", command=self.import_selected, bg="#ffd54f", font=("Arial", 10, "bold")).pack(side="left", padx=5, pady=5)




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

        # --- Main Notebook（选股表 + 板块聚焦 + 决策队列）---
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # ── Tab 1: 策略选股表（原有，保持不变）──────────────────────────────────
        tab_select = tk.Frame(self._notebook)
        self._notebook.add(tab_select, text="📋 策略选股")

        columns = ("code", "name", "grade", "tqi", "status", "score", "rank", "price", "percent", "昨日涨幅", "ratio", "amount", "连阳涨幅", "win", "volume", "category", "auto_reason", "user_status", "user_reason")
        
        tree_frame = tk.Frame(tab_select)
        tree_frame.pack(fill="both", expand=True)
        
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

        # ── Tab 2: 板块聚焦（盘中热力）────────────────────────────────────────
        tab_sector = tk.Frame(self._notebook)
        self._notebook.add(tab_sector, text="🔥 板块聚焦")
        self._init_sector_tab(tab_sector)

        # ── Tab 3: 实时决策队列 ───────────────────────────────────────────────
        tab_decision = tk.Frame(self._notebook)
        self._notebook.add(tab_decision, text="🎯 实时决策")
        self._init_decision_tab(tab_decision)

        # ── Tab 4: 📋 每日操作指南 ─────────────────────────────────────────────
        tab_guidance = tk.Frame(self._notebook)
        self._notebook.add(tab_guidance, text="📋 每日操作指南")
        self._init_guidance_tab(tab_guidance)

        # 定时刷新（切换到交易相关Tab时才真正更新）
        self._focus_refresh_id: Optional[str] = None
        self._schedule_focus_refresh()

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
                
                # 初始化用户标注列与历史回溯字段映射
                if not self.df_full_candidates.empty:
                    if 'user_status' not in self.df_full_candidates.columns:
                        self.df_full_candidates['user_status'] = "待定"
                    if 'user_reason' not in self.df_full_candidates.columns:
                        self.df_full_candidates['user_reason'] = ""
                        
                    # 🚀 [新增] 优雅地针对历史数据列进行 rename，直接激活历史模式下的字段展现 (2026-05-08)
                    rename_map = {}
                    if 'yesterday_pct' in self.df_full_candidates.columns:
                        rename_map['yesterday_pct'] = '昨日涨幅'
                    if 'sum_perc' in self.df_full_candidates.columns:
                        rename_map['sum_perc'] = '连阳涨幅'
                    if 'rank' in self.df_full_candidates.columns:
                        rename_map['rank'] = 'Rank'
                    
                    if rename_map:
                        self.df_full_candidates.rename(columns=rename_map, inplace=True)
                
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

            # 🚀 [加固] 无论今日还是历史模式，对 category (板块概念) 进行健壮的题材重构与全覆盖更新补齐
            if 'category' not in self.df_full_candidates.columns:
                self.df_full_candidates['category'] = ''
            
            # 使用实时行情 df_all_realtime 的题材板块做完全覆盖补齐
            if self.selector is not None and hasattr(self.selector, 'df_all_realtime') and self.selector.df_all_realtime is not None and not self.selector.df_all_realtime.empty:
                rt_all = self.selector.df_all_realtime
                # 确保实时行情有 category 列
                if 'category' in rt_all.columns:
                    # 将 category 统一转成 string 类型并清洗
                    self.df_full_candidates['category'] = self.df_full_candidates['category'].fillna('').astype(str).str.strip()
                    
                    # 构建一个 code -> category 的快速映射字典
                    if rt_all.index.name == 'code' or 'code' in rt_all.index.names:
                        code_to_cat = rt_all['category'].fillna('').astype(str).to_dict()
                    elif 'code' in rt_all.columns:
                        code_to_cat = dict(zip(rt_all['code'].apply(lambda x: str(x).zfill(6)), rt_all['category'].fillna('').astype(str)))
                    else:
                        code_to_cat = {str(k).zfill(6): str(v) for k, v in rt_all['category'].fillna('').to_dict().items()}
                        
                    # 对所有数据进行完全题材覆盖
                    mapped_cats = self.df_full_candidates['code'].map(code_to_cat)
                    mapped_cats = mapped_cats.dropna()
                    mapped_cats = mapped_cats[~mapped_cats.isin(['', '0', 'nan', 'NaN'])]
                    
                    if not mapped_cats.empty:
                        self.df_full_candidates.loc[mapped_cats.index, 'category'] = mapped_cats

            # 从全量缓存中复制，用于当前视窗的筛选/显示
            self.df_candidates = self.df_full_candidates.copy()

            # Apply Concept Filter
            filter_str = self.concept_filter_var.get().strip()
            if filter_str:
                # Support multi-keywords with space
                keywords = filter_str.split()
                for kw in keywords:
                    # Generic search: Code, Name, or Category
                    # 🚀 [FIX] 显式设置 case=False 且 regex=False，根治带括号概念如 共封装光学(CPO) 0519 数据无法被正则识别匹配出的陈年大 Bug！
                    mask = (
                        self.df_candidates['category'].str.contains(kw, case=False, regex=False, na=False) | 
                        self.df_candidates['code'].str.contains(kw, case=False, regex=False, na=False) | 
                        self.df_candidates['name'].str.contains(kw, case=False, regex=False, na=False)
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
            
            # ✅ [NEW] 联动刷新每日操作指南 Tab
            if hasattr(self, '_refresh_guidance_tab'):
                self._refresh_guidance_tab()
            
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

        # 🚀 [加固] 确保 matched_concept tag 被正确高反差亮红配置
        self.tree.tag_configure("matched_concept", foreground="#ff3333", font=("Microsoft YaHei", 9, "bold"))

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
                    if icon: display_name = f"{icon}{display_name}"

                grade = getattr(row, 'grade', 'C')
                if grade == "S": all_tags.append("grade_S")
                elif grade == "A": all_tags.append("grade_A")

                # 🚀 板块过滤标红高亮与文本强化高亮
                category_raw = getattr(row, 'category', '')
                short_category = self._get_short_category(category_raw)
                
                current_filter = self.concept_filter_var.get().strip()
                keywords = current_filter.split() if current_filter else []
                has_matched_concept = False
                if keywords:
                    has_matched_concept = any(kw in str(category_raw).lower() for kw in keywords)
                    if has_matched_concept:
                        all_tags.append("matched_concept")
                        # 文本高亮
                        cats = [c.strip() for c in re.split(r'[;|]', str(category_raw)) if c.strip() and c.strip() not in ('nan', 'NaN', '0')]
                        short_cats_modified = []
                        for c in cats[:5]:
                            if any(kw in c.lower() for kw in keywords):
                                short_cats_modified.append(f"★{c}")
                            else:
                                short_cats_modified.append(c)
                        short_category = " | ".join(short_cats_modified)
                        if len(cats) > 5:
                            short_category += " ..."

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
                    short_category,
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

        # 🚀 [NEW] 加载完成后，自动选中第一行，避免用户需要手动点选才能锁定“最新视图”进行审计
        all_items = self.tree.get_children()
        if all_items:
            try:
                self.tree.selection_set(all_items[0])
                self.tree.see(all_items[0])
                self.tree.focus(all_items[0])
            except: pass

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
            
        if hasattr(self, '_notebook') and self._notebook.index("current") != 0:
            self._notebook.select(0)

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
                
            if hasattr(self, '_notebook') and self._notebook.index("current") != 0:
                self._notebook.select(0)

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
            
        if hasattr(self, '_notebook') and self._notebook.index("current") != 0:
            self._notebook.select(0)
            
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

    def _on_concept_combo_right_click(self, event):
        """右键自动粘贴剪贴板文本并执行检索"""
        try:
            clipboard_text = self.clipboard_get().strip()
        except Exception:
            clipboard_text = ""
            
        if clipboard_text:
            self.concept_filter_var.set(clipboard_text)
            self.concept_combo.focus_set()
            self.concept_combo.icursor('end')
            self.concept_combo.selection_range(0, 'end')
            
            # 自动执行检索过滤
            self.on_filter_search(None)
            
            # 状态栏闪烁回馈
            status_lbl = getattr(self, 'status_lbl', None) or getattr(self.master, 'status_lbl', None)
            if status_lbl:
                try:
                    status_lbl.config(text=f"📋 右键粘贴过滤: {clipboard_text}", fg="#44ff88")
                    self.after(2000, lambda: status_lbl.config(text="准备就绪", fg="#ff9900"))
                except Exception: pass
        return "break" # 阻止系统默认菜单弹出

    def _get_short_category(self, raw_cat):
        """只保留前5个有明确实际信息的板块题材，其余通过双击详情查看"""
        if not raw_cat or str(raw_cat) in ('nan', 'NaN', '0'):
            return ""
        cats = [c.strip() for c in re.split(r'[;|]', str(raw_cat)) if c.strip() and c.strip() not in ('nan', 'NaN', '0')]
        short_cat = " | ".join(cats[:5])
        if len(cats) > 5:
            short_cat += " ..."
        return short_cat

    def on_double_click(self, event):
        """双击板块/概念列展示独立大字面板，双击其他列默认触发联动"""
        region = self.tree.identify("region", event.x, event.y)
        if region == "heading":
            return
            
        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item_id:
            return
            
        # "category" 对应第 16 列, #16
        if column == "#16":
            vals = self.tree.item(item_id, "values")
            if vals and len(vals) > 15:
                code = str(vals[0]).strip()
                name = str(vals[1]).strip()
                category_fallback = str(vals[15]).strip()
                self.show_concept_detail_popup(code, name, category_fallback)
                return
        
        # 默认触发联动
        self.on_select(event)

    def show_concept_detail_popup(self, code, name, category=None, caller_win=None):
        """弹出大字板块题材详情窗口，支持双击自动复制、Esc自动退出与尺寸大小跨会话持久化，窗口复用不闪烁"""
        # 1. 100% 坚固的题材自愈拉取
        full_category = ""
        # 向上游实时行情拉取
        if self.selector is not None and hasattr(self.selector, 'df_all_realtime') and self.selector.df_all_realtime is not None and not self.selector.df_all_realtime.empty:
            rt_all = self.selector.df_all_realtime.copy()
            if rt_all.index.name == 'code' or 'code' in rt_all.index.names:
                rt_all.index = rt_all.index.map(lambda x: str(x).zfill(6))
                if code in rt_all.index:
                    full_category = str(rt_all.loc[code, 'category']) if 'category' in rt_all.columns else ""
            elif 'code' in rt_all.columns:
                rt_all['code_str'] = rt_all['code'].apply(lambda x: str(x).zfill(6))
                sub_df = rt_all[rt_all['code_str'] == code]
                if not sub_df.empty and 'category' in sub_df.columns:
                    full_category = str(sub_df.iloc[0]['category'])
                    
        # 向上游自选股缓存拉取
        if (not full_category or full_category in ['nan', 'NaN', '0']) and hasattr(self, 'df_full_candidates') and self.df_full_candidates is not None and self.df_full_candidates is not None and not self.df_full_candidates.empty:
            cand_df = self.df_full_candidates.copy()
            if 'code' in cand_df.columns:
                cand_df['code_str'] = cand_df['code'].apply(lambda x: str(x).zfill(6))
                sub_df = cand_df[cand_df['code_str'] == code]
                if not sub_df.empty and 'category' in sub_df.columns:
                    full_category = str(sub_df.iloc[0]['category'])
                    
        # 向上游当前视窗 DataFrame 缓存拉取
        if (not full_category or full_category in ['nan', 'NaN', '0']) and hasattr(self, 'df_candidates') and self.df_candidates is not None and not self.df_candidates.empty:
            cand_df = self.df_candidates.copy()
            if 'code' in cand_df.columns:
                cand_df['code_str'] = cand_df['code'].apply(lambda x: str(x).zfill(6))
                sub_df = cand_df[cand_df['code_str'] == code]
                if not sub_df.empty and 'category' in sub_df.columns:
                    full_category = str(sub_df.iloc[0]['category'])

        # 降级使用传入的 category (剥离 display_cat 截断标记)
        if (not full_category or full_category in ['nan', 'NaN', '0']) and category:
            full_category = category.replace(" ...", "").strip()
            
        full_category = full_category.strip() if full_category else ""
        if not full_category or full_category in ('nan', 'NaN', '0'):
            # 状态栏温馨提示
            status_lbl = getattr(self, 'status_lbl', None) or getattr(self.master, 'status_lbl', None)
            if status_lbl:
                try:
                    status_lbl.config(text=f"⚠️ {name} ({code}) 暂无板块题材数据", fg="#ff4444")
                    self.after(3000, lambda: status_lbl.config(text="准备就绪", fg="#ff9900"))
                except Exception: pass
            return

        # 2. 检查窗口复用状态
        is_reused = False
        popup = getattr(self, '_concept_detail_win', None)
        if popup is not None and popup.winfo_exists():
            # 🚀 [复用] 已有关闭，原位清空所有子组件
            is_reused = True
            for widget in popup.winfo_children():
                widget.destroy()
            popup.title(f"🔎 {code} {name} - 板块题材")
            popup.deiconify()
            popup.lift()
            popup.focus_force()
        else:
            # 🚀 [新建] 创建新 TopLevel 窗口并进行隐蔽渲染保护
            popup = tk.Toplevel(self)
            popup.withdraw() # ⭐ 先行隐蔽，防止窗口坐标在完全算好前在屏幕左上角闪现
            self._concept_detail_win = popup
            popup.title(f"🔎 {code} {name} - 板块题材")
            popup.configure(bg="#0c101b")
            popup.transient(self) # 关联父窗口
            
            # 3. 高保真自适应居中与尺寸持久化
            popup.update_idletasks()
            has_position = False
            try:
                # 优先从持久化中载入大小和位置
                ret = self.load_window_position(popup, "板块题材详情", default_width=380, default_height=450)
                if ret and len(ret) >= 4 and ret[2] is not None and ret[3] is not None:
                    # ⭐ 仅当载入的物理坐标不是 0,0 (左上角脏数据) 时，才视作有效位置，否则重新执行主视窗中心居中
                    if ret[2] > 0 or ret[3] > 0:
                        has_position = True
            except Exception:
                pass
                
            if not has_position:
                # 完美的主视窗相对中心定位加屏幕边界安全限宽算法
                w, h = 380, 450
                main_x = self.winfo_x()
                main_y = self.winfo_y()
                main_w = self.winfo_width()
                main_h = self.winfo_height()
                xp = main_x + (main_w - w) // 2
                yp = main_y + (main_h - h) // 2
                
                screen_w = popup.winfo_screenwidth()
                screen_h = popup.winfo_screenheight()
                xp = max(0, min(xp, screen_w - w))
                yp = max(0, min(yp, screen_h - h))
                popup.geometry(f"{w}x{h}+{xp}+{yp}")
                
            # 完全计算和设定好位置后，再 deiconify 呈现，彻底解决左上角闪现闪烁！
            popup.deiconify()
            popup.attributes("-topmost", True)
            popup.focus_force()

        # 4. 关闭动作封装 (退出时保存大小和坐标并清空缓存引用)
        def on_popup_close(event=None):
            # 🚀 完全使用系统现成的 save_window_position 成员方法，绝不自行重写写盘逻辑
            try:
                # 仅当窗口在屏幕正常显示范围内 (且非 0,0 边角脏数据) 时才保存位置，安全避坑
                geom = popup.geometry()
                parts = geom.split('+')
                if len(parts) >= 3:
                    x = int(parts[1])
                    y = int(parts[2])
                    if x > 0 or y > 0:
                        self.save_window_position(popup, "板块题材详情")
            except Exception as e:
                logger.error(f"[on_popup_close] 保存板块题材位置失败: {e}")
                
            try:
                popup.destroy()
            except Exception: pass
            self._concept_detail_win = None
            
        popup.protocol("WM_DELETE_WINDOW", on_popup_close)
        popup.bind("<Escape>", lambda e: on_popup_close()) # 🚀 [NEW] 支持 Esc 键自动退出并持久化位置
        
        # 5. 渲染 UI 布局组件
        title_frame = tk.Frame(popup, bg="#111726", pady=10)
        title_frame.pack(fill="x")
        
        tk.Label(title_frame, text=f"📊 {name} ({code})", font=("Microsoft YaHei", 12, "bold"), fg="#ffd54f", bg="#111726").pack(anchor="w", padx=15)
        tk.Label(title_frame, text="双击以下任意板块即可极速复制名称", font=("Microsoft YaHei", 9), fg="#88a0c0", bg="#111726").pack(anchor="w", padx=15)
        
        # 板块列表主容器 (带滚动条)
        list_frame = tk.Frame(popup, bg="#0c101b")
        list_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        # 滚动画布
        canvas = tk.Canvas(list_frame, bg="#0c101b", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#0c101b")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 状态提示区 (复制成功后闪烁提示)
        status_lbl = tk.Label(popup, text="💡 双击板块直接复制", font=("Microsoft YaHei", 10), fg="#ffd54f", bg="#111726", bd=1, relief="groove")
        status_lbl.pack(fill="x", side="bottom", ipady=2)
        
        # 绑定鼠标滚轮支持，使得在卡片中滚动极其丝滑
        def _on_mouse_wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            
        popup.bind("<MouseWheel>", _on_mouse_wheel)
        canvas.bind("<MouseWheel>", _on_mouse_wheel)
        scrollable_frame.bind("<MouseWheel>", _on_mouse_wheel)

        # 分割板块并去重
        sub_cats = [c.strip() for c in re.split(r'[;|]', full_category) if c.strip() and c.strip() not in ('nan', 'NaN', '0')]
        
        # 动态复制并提示的方法
        def copy_cat(cat_name, label_widget):
            self.clipboard_clear()
            self.clipboard_append(cat_name)
            self.update()
            
            # 视觉高亮闪烁效果（耀眼荧光绿）
            label_widget.config(fg="#44ff88", bg="#1b3a24")
            status_lbl.config(text=f"📋 已复制板块: {cat_name}", fg="#44ff88")
            
            # 恢复样式（天蓝色与暗灰底色）
            def restore():
                try:
                    label_widget.config(fg="#64b5f6", bg="#1e293b")
                except Exception: pass
            popup.after(300, restore)
            popup.after(2000, lambda: status_lbl.config(text="💡 双击板块直接复制", fg="#ffd54f"))
            logger.info(f"Double-click copied concept: {cat_name}")

        # 极速过滤动作
        def apply_filter_action(cat_name):
            self.quick_apply_concept_filter(cat_name)
            if caller_win is not None and hasattr(caller_win, 'search_var'):
                try:
                    caller_win.search_var.set(cat_name)
                except Exception: pass
            popup.destroy()
            self._concept_detail_win = None
            
        for i, cat in enumerate(sub_cats):
            item_frame = tk.Frame(scrollable_frame, bg="#0c101b", pady=4)
            item_frame.pack(fill="x", expand=True)
            item_frame.bind("<MouseWheel>", _on_mouse_wheel)
            
            # 序号标签
            num_lbl = tk.Label(item_frame, text=f"{i+1}.", font=("Consolas", 11, "bold"), fg="#ff9900", bg="#0c101b", width=3, anchor="w")
            num_lbl.pack(side="left")
            num_lbl.bind("<MouseWheel>", _on_mouse_wheel)
            
            # 板块名称标签
            lbl = tk.Label(item_frame, text=cat, font=("Microsoft YaHei", 11, "bold"), fg="#64b5f6", bg="#1e293b", bd=1, relief="solid", padx=10, pady=6, cursor="hand2", anchor="w")
            lbl.pack(side="left", fill="x", expand=True, padx=(0, 5))
            lbl.bind("<MouseWheel>", _on_mouse_wheel)
            
            # 绑定双击自动复制
            lbl.bind("<Double-1>", lambda e, c=cat, l=lbl: copy_cat(c, l))
            
            # 绑定 hover 态变色
            def on_enter(e, l=lbl): l.config(bg="#2d3748", fg="#ffd54f")
            def on_leave(e, l=lbl): l.config(bg="#1e293b", fg="#64b5f6")
            lbl.bind("<Enter>", on_enter)
            lbl.bind("<Leave>", on_leave)
            
            # 贴心极速过滤按钮
            btn_filter = tk.Button(item_frame, text="🔍 过滤", font=("Microsoft YaHei", 9), bg="#2d3748", fg="#ffd54f", activebackground="#ff9900", activeforeground="#ffffff", relief="flat", padx=8, command=lambda c=cat: apply_filter_action(c))
            btn_filter.pack(side="right")
            btn_filter.bind("<MouseWheel>", _on_mouse_wheel)

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
        
        # 🚀 [NEW] 板块过滤与有筛选条件时的前3个题材权重最高绝对优先排序算法
        current_filter = ""
        if hasattr(self, 'concept_filter_var'):
            current_filter = self.concept_filter_var.get().lower().strip()
        elif hasattr(self, 'search_var'):
            current_filter = self.search_var.get().lower().strip()
            
        kws = current_filter.split() if current_filter else []
        
        if col == "category" and kws:
            def get_sort_key(t):
                val = str(t[0]).lower()
                cats = [c.strip() for c in re.split(r'[;|★\s]', val) if c.strip() and c.strip() not in ('nan', 'NaN', '0')]
                match_idx = 999
                for idx, cat in enumerate(cats):
                    if any(kw in cat for kw in kws):
                        match_idx = idx
                        break
                # 数学对齐：确保升序降序匹配度最高的（match_idx越小）股票永远绝对排在最前面
                prio = match_idx if not reverse else (999 - match_idx)
                return (prio, t[0])
                
            try:
                l.sort(key=get_sort_key, reverse=reverse)
            except Exception:
                l.sort(reverse=reverse)
        else:
            # 尝试转为数字排序
            try:
                # 针对 rank 列或其他整数列，优先尝试 int，再 float
                l.sort(key=lambda t: float(t[0]) if t[0] and t[0].strip() else -1, reverse=reverse)
            except ValueError:
                l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))
        # [NEW] 排序后自动滚动到顶部
        self.tree.yview_moveto(0)

    def show_context_menu(self, event):
        """显示右键菜单 (通用)"""
        tree = event.widget
        item_id = tree.identify_row(event.y)
        if not item_id:
            return

        sel = tree.selection()
        if item_id not in sel:
            tree.selection_set(item_id)
            sel = (item_id,)
            
        code = item_id
        vals = tree.item(item_id, "values")
        if vals:
            if hasattr(self, '_log_tree') and tree == self._log_tree:
                c = str(vals[2]).strip() if len(vals) > 2 else ""
            else:
                c = str(vals[0]).strip()
            c = re.sub(r'[^\d]', '', c).zfill(6)
            if c:
                code = c

        menu = tk.Menu(self, tearoff=0, bg="#2C2C2E", fg="white", activebackground="#005BB7")

        # 定义命令（先保存）
        cmd = lambda: self.tree_scroll_to_code(code)

        menu.add_command(
            label=f"📂 定位股票代码: {code}",
            command=cmd
        )

        # 🚀 [新增] 动态板块概念联查及快捷复制过滤 (2026-05-22)
        category = ""
        if self.selector is not None and hasattr(self.selector, 'df_all_realtime') and self.selector.df_all_realtime is not None and not self.selector.df_all_realtime.empty:
            rt_all = self.selector.df_all_realtime
            if rt_all.index.name == 'code' or 'code' in rt_all.index.names:
                if code in rt_all.index:
                    category = str(rt_all.loc[code, 'category']) if 'category' in rt_all.columns else ""
            elif 'code' in rt_all.columns:
                sub_df = rt_all[rt_all['code'].apply(lambda x: str(x).zfill(6)) == code]
                if not sub_df.empty and 'category' in sub_df.columns:
                    category = str(sub_df.iloc[0]['category'])
                    
        # 兜底联查自选股缓存
        if (not category or category in ['nan', 'NaN', '0']) and hasattr(self, 'df_full_candidates') and self.df_full_candidates is not None and not self.df_full_candidates.empty:
            sub_df = self.df_full_candidates[self.df_full_candidates['code'] == code]
            if not sub_df.empty and 'category' in sub_df.columns:
                category = str(sub_df.iloc[0]['category'])

        category = category.strip() if category else ""
        current_filter = self.concept_filter_var.get().strip()
        if category and category not in ['0', 'nan', 'NaN']:
            # 拆分子板块名称，兼容分号和竖线
            sub_cats = [cat.strip() for cat in re.split('[;|]', category) if cat.strip()]
            if sub_cats:
                menu.add_separator()
                
                menu.add_command(
                    label="📊 该股题材板块 (仅列出前5个):",
                    state="disabled"
                )
                
                # 🚀 板块只显示前5，且与当前板块过滤词同名或者包含则高亮标红差异化显示
                for cat in sub_cats[:5]:
                    is_matched = False
                    if current_filter:
                        is_matched = any(kw in cat.lower() for kw in current_filter.lower().split())
                    
                    label_str = f"  🔍 过滤板块: {cat}"
                    fg_color = "white"
                    if is_matched:
                        label_str = f"  📍【匹配】🔍 过滤板块: {cat}"
                        fg_color = "#ff3333"
                        
                    menu.add_command(
                        label=label_str,
                        foreground=fg_color,
                        activeforeground=fg_color,
                        command=lambda c=cat: self.quick_apply_concept_filter(c)
                    )
        
        title_dna = f"🧬 执行 DNA 审计 ({len(sel)}只...)" if len(sel) > 1 else f"🧬 执行 DNA 审计"
        menu.add_command(label=title_dna, command=self._run_dna_audit_selected)

        # 🔍 新增：Re-entry 历史回测入口
        menu.add_separator()
        menu.add_command(
            label=f"🔍 运行 Re-entry 历史回测 ({code})",
            command=lambda: self._on_run_reentry_backtest_menu(code)
        )

        menu.post(event.x_root, event.y_root)
    def quick_apply_concept_filter(self, concept: str):
        """同步将板块概念应用至顶部板块输入框，并触发过滤"""
        self.concept_filter_var.set(concept)
        self.on_filter_search()
        
        # 🚀 [同步] 如果历史追踪弹窗存在，同步其筛选词
        if hasattr(self, '_history_track_win') and self._history_track_win.winfo_exists():
            if self._history_track_win.search_var.get() != concept:
                self._history_track_win.search_var.set(concept)

    def _get_active_tree(self):
        """🚀 [DNA-BATCH] 探测当前活跃（聚焦或页签内）的 Treeview"""
        # 1. 首先尝试获取当前拥有焦点的 Treeview
        focused = self.focus_get()
        if isinstance(focused, ttk.Treeview):
            return focused
            
        # 2. 否则根据页签判定
        tab_id = self._notebook.select()
        if not tab_id: return self.tree
        tab_text = self._notebook.tab(tab_id, "text")
        
        if "策略选股" in tab_text: 
            return self.tree
        elif "板块聚焦" in tab_text:
            # 优先返回选股详情成员表，如果没有则返回板块排行榜
            if hasattr(self, '_member_tree') and (self._member_tree.selection() or self._member_tree.get_children()):
                return self._member_tree
            if hasattr(self, '_sector_tree'): return self._sector_tree
        elif "实时决策" in tab_text:
            if hasattr(self, '_signal_tree'): return self._signal_tree
            
        return self.tree # Final fallback

    def _run_dna_audit_selected(self):
        """🚀 [DNA-BATCH] 极限审计当前视图所选 / Top20 (智能适配多列名)"""
        tree = self._get_active_tree()
        if not tree: 
            messagebox.showinfo("提示", "当前没有可用于审计的展示列表")
            return
            
        # 🛡️ 强制刷新渲染状态，确保审计拿到的是最新视图数据
        tree.update_idletasks()
        
        items = list(tree.get_children())
        if not items: return
        
        # 1. 动态映射列索引 (寻找 代码/龙头代码 和 名称/龙头名)
        col_ids = tree.cget("columns")
        idx_code, idx_name = -1, -1
        for i, cid in enumerate(col_ids):
            c_lower = str(cid).lower()
            header_text = str(tree.heading(cid, "text")).lower()
            if "code" in c_lower or "代码" in header_text: idx_code = i
            if "name" in c_lower or "名称" in header_text: idx_name = i
            
        # 兜底：如果没找到，默认用第 0, 1 列
        if idx_code == -1: idx_code = 0
        if idx_name == -1: idx_name = 1

        # 2. 确定目标项
        selection = tree.selection()
        target_items = []
        if len(selection) > 1:
            # 多选模式：仅审计选中的 (上限 50)
            target_items = list(selection)[:50]
        elif len(selection) == 1:
            # 单选模式：从选中行开始向下选取 20 只 (包含选中项)
            try:
                start_idx = items.index(selection[0])
            except ValueError:
                start_idx = 0
            target_items = items[start_idx : start_idx + 20]
        else:
            # 无选区：默认前 20 只
            target_items = items[:20]
            
        code_to_name = {}
        for it in target_items:
            vals = tree.item(it, "values")
            if vals and len(vals) > idx_code:
                c = str(vals[idx_code]).strip()
                c = re.sub(r'[^\d]', '', c)
                if len(c) < 6 and c.isdigit(): c = c.zfill(6)
                
                n = str(vals[idx_name]).strip() if len(vals) > idx_name else ""
                if n.startswith("🔔"): n = n.replace("🔔", "")
                
                if c and c != "N/A" and len(c) == 6:
                    code_to_name[c] = n
                    
        if code_to_name:
            if hasattr(self.master, '_run_dna_audit_batch'):
                # 🚀 [NEW] 支持历史截止日期审计
                end_date = None
                # last_td = str(cct.get_last_trade_date()).replace("-", "")
                last_td = str(cct.get_last_trade_date())
                if self.current_date < last_td:
                    end_date = self.current_date
                
                if hasattr(self.master, 'tk_dispatch_queue'):
                    # 🚀 [THREAD-SAFE] 通过 Tk 调度队列执行
                    _cn = dict(code_to_name)
                    self.master.tk_dispatch_queue.put(lambda: self.master._run_dna_audit_batch(_cn, end_date=end_date))
                else:
                    self.master._run_dna_audit_batch(code_to_name, end_date=end_date)
            else:
                logger.error("No access to main monitor app for DNA audit.")
    


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
        
        # 🚀 [NEW] 追踪中的筛选跟主界面板块过滤历史记录联动，复用过滤信息
        if hasattr(parent, 'concept_filter_var'):
            parent_filter = parent.concept_filter_var.get().strip()
            if parent_filter:
                self.search_var.set(parent_filter)
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
        self.entry_search = ttk.Combobox(toolbar, textvariable=self.search_var, width=15)
        self.entry_search['values'] = getattr(self.parent_win, 'history', [])
        self.entry_search.pack(side="left", padx=2)
        # 🚀 [NEW] 右键自动粘贴并过滤
        self.entry_search.bind("<Button-3>", self._on_entry_search_right_click)
        self.entry_search.bind("<Return>", lambda e: self._save_history(self.search_var.get()))
        self.entry_search.bind("<<ComboboxSelected>>", lambda e: [self._save_history(self.search_var.get()), self._apply_filter()])
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
        
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", style="Custom.Treeview")
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
        self.tree.tag_configure("high_hits", background="#13261a", foreground="#44ff88") # 高命中暗绿底色
        self.tree.tag_configure("matched_concept", foreground="#ff3333", font=("Microsoft YaHei", 9, "bold")) # 匹配板块标红差异化显示
        
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)

    def _on_entry_search_right_click(self, event):
        """右键自动粘贴剪贴板文本并执行过滤"""
        try:
            clipboard_text = self.clipboard_get().strip()
        except Exception:
            clipboard_text = ""
            
        if clipboard_text:
            self.search_var.set(clipboard_text)
            self.entry_search.focus_set()
            self.entry_search.icursor('end')
            self.entry_search.selection_range(0, 'end')
            self._save_history(clipboard_text) # 🚀 [NEW] 右键自动粘贴并同步历史记录
            
            # 状态栏闪烁回馈
            if hasattr(self, 'status_lbl') and self.status_lbl:
                try:
                    self.status_lbl.config(text=f"📋 右键自动粘贴并过滤: {clipboard_text}", fg="#00cc00")
                    self.after(2000, lambda: self.status_lbl.config(text=f"✅ 完成！共追踪 {len(self._all_results)} 只个股", fg="#00cc00"))
                except Exception: pass
        return "break" # 阻止系统默认菜单弹出

    def _save_history(self, query: str):
        """保存搜索词并同步更新主窗口和追踪窗口的历史记录 values"""
        query = query.strip()
        if not query or query in ("nan", "NaN", "0"):
            return
        
        # 获取主窗口的历史纪录
        p_history = getattr(self.parent_win, 'history', [])
        if query in p_history:
            p_history.remove(query)
        p_history.insert(0, query)
        p_history = p_history[:20]
        
        # 写入主窗口
        self.parent_win.history = p_history
        if hasattr(self.parent_win, 'concept_combo'):
            self.parent_win.concept_combo['values'] = p_history
            
        # 写入当前窗口
        self.entry_search['values'] = p_history
        
        # 持久化到文件
        try:
            with open(self.parent_win.history_file, 'w', encoding='utf-8') as f:
                json.dump(p_history, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Error saving synced search history: {e}")

    def show_context_menu(self, event):
        """显示追踪面板的右键菜单，同步支持只显示前5、同名板块标红高亮与多端联级过滤"""
        tree = event.widget
        item_id = tree.identify_row(event.y)
        if not item_id:
            return

        sel = tree.selection()
        if item_id not in sel:
            tree.selection_set(item_id)
            sel = (item_id,)
            
        code = item_id
        vals = tree.item(item_id, "values")
        if vals:
            c = str(vals[0]).strip()
            c = re.sub(r'[^\d]', '', c).zfill(6)
            if c:
                code = c

        menu = tk.Menu(self, tearoff=0, bg="#2C2C2E", fg="white", activebackground="#005BB7")

        # 📂 主窗口定位
        menu.add_command(
            label=f"📂 定位股票代码: {code}",
            command=lambda: getattr(self.parent_win, 'tree_scroll_to_code', None) and self.parent_win.tree_scroll_to_code(code)
        )

        # 联查板块题材
        category = ""
        if self.selector is not None and hasattr(self.selector, 'df_all_realtime') and self.selector.df_all_realtime is not None and not self.selector.df_all_realtime.empty:
            rt_all = self.selector.df_all_realtime
            if rt_all.index.name == 'code' or 'code' in rt_all.index.names:
                if code in rt_all.index:
                    category = str(rt_all.loc[code, 'category']) if 'category' in rt_all.columns else ""
            elif 'code' in rt_all.columns:
                sub_df = rt_all[rt_all['code'].apply(lambda x: str(x).zfill(6)) == code]
                if not sub_df.empty and 'category' in sub_df.columns:
                    category = str(sub_df.iloc[0]['category'])
                    
        if (not category or category in ['nan', 'NaN', '0']) and hasattr(self.parent_win, 'df_full_candidates') and self.parent_win.df_full_candidates is not None and not self.parent_win.df_full_candidates.empty:
            sub_df = self.parent_win.df_full_candidates[self.parent_win.df_full_candidates['code'] == code]
            if not sub_df.empty and 'category' in sub_df.columns:
                category = str(sub_df.iloc[0]['category'])

        category = category.strip() if category else ""
        current_filter = self.search_var.get().strip()

        if category and category not in ['0', 'nan', 'NaN']:
            sub_cats = [cat.strip() for cat in re.split('[;|]', category) if cat.strip()]
            if sub_cats:
                menu.add_separator()
                
                menu.add_command(
                    label="📊 该股题材板块 (仅列出前5个):",
                    state="disabled"
                )
                
                # 🚀 板块只显示前5，且与当前板块过滤词同名或者包含则高亮标红差异化显示
                for cat in sub_cats[:5]:
                    is_matched = False
                    if current_filter:
                        is_matched = any(kw in cat.lower() for kw in current_filter.lower().split())
                    
                    label_str = f"  🔍 过滤板块: {cat}"
                    fg_color = "white"
                    if is_matched:
                        label_str = f"  📍【匹配】🔍 过滤板块: {cat}"
                        fg_color = "#ff3333"
                        
                    menu.add_command(
                        label=label_str,
                        foreground=fg_color,
                        activeforeground=fg_color,
                        command=lambda c=cat: self.parent_win.quick_apply_concept_filter(c)
                    )

        # 🔍 新增：Re-entry 历史回测入口
        menu.add_separator()
        menu.add_command(
            label=f"🔍 运行 Re-entry 历史回测 ({code})",
            command=lambda: self.parent_win._on_run_reentry_backtest_menu(code)
        )

        menu.post(event.x_root, event.y_root)

    def _on_double_click(self, event):
        """双击板块列展示独立大字面板，双击其他触发原有联动"""
        region = self.tree.identify("region", event.x, event.y)
        if region == "heading":
            return
            
        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item_id:
            return
            
        # "sector" 对应第 4 列, #4
        if column == "#4":
            vals = self.tree.item(item_id, "values")
            if vals and len(vals) > 3:
                sector = str(vals[3]).strip()
                code = str(vals[0]).strip()
                name = str(vals[1]).strip()
                if sector and sector not in ('nan', 'NaN', '0'):
                    if hasattr(self.parent_win, 'show_concept_detail_popup'):
                        # 🚀 [NEW] 传入 caller_win=self 实现弹窗极速过滤与追踪窗口的多端绝对级联！
                        self.parent_win.show_concept_detail_popup(code, name, sector, caller_win=self)
                        return
        
        # 默认双击触发联动
        self._on_select(event, force_link=True)

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
        query_str = self.search_var.get().lower().strip()
        
        # 💡 [同步加固] 深度对齐主窗口的多关键字 AND 筛选逻辑，支持空格分隔
        keywords = query_str.split() if query_str else []
        
        for item in self._all_results:
            match_all = True
            for kw in keywords:
                # 每一个关键字都必须在 code, name, 或者 sector 中被匹配到
                in_code = kw in str(item.get('code', ''))
                in_name = kw in str(item.get('name', '')).lower()
                in_sector = kw in str(item.get('sector', '')).lower()
                
                # 兼容 category 别名
                if not in_sector and 'category' in item:
                    in_sector = kw in str(item['category']).lower()
                
                if not (in_code or in_name or in_sector):
                    match_all = False
                    break
            
            if not match_all:
                continue
            
            # 🚀 [NEW] 板块也只显示前5个，并支持同名/匹配板块文本强化高亮
            raw_sector = item.get('sector', '')
            short_sector = self.parent_win._get_short_category(raw_sector)
            
            has_matched_concept = False
            if keywords:
                has_matched_concept = any(kw in str(raw_sector).lower() for kw in keywords)
                if has_matched_concept:
                    # 将匹配到的子板块包裹星号高亮
                    cats = [c.strip() for c in re.split(r'[;|]', str(raw_sector)) if c.strip() and c.strip() not in ('nan', 'NaN', '0')]
                    short_cats_modified = []
                    for c in cats[:5]:
                        if any(kw in c.lower() for kw in keywords):
                            short_cats_modified.append(f"★{c}")
                        else:
                            short_cats_modified.append(c)
                    short_sector = " | ".join(short_cats_modified)
                    if len(cats) > 5:
                        short_sector += " ..."
            
            roi = item['roi']
            tag = "plus" if roi > 0 else ("minus" if roi < 0 else "")
            
            all_tags = [tag]
            if item['hits'] >= 3: all_tags.append("high_hits")
            
            # 🚀 同名板块颜色标红差异化显示出来
            if has_matched_concept:
                all_tags.append("matched_concept")
            
            self.tree.insert("", "end", iid=item['code'], values=(
                item['code'], item['name'], item['hits'], short_sector,
                f"{item['base_price']:.2f}", f"{item['curr_price']:.2f}",
                f"{roi:+.2f}%", item['pattern']
            ), tags=tuple(all_tags))
            
        # 🚀 [NEW] 筛选过滤后，动态重新计算并实时显示统计指标（总数、上涨、下跌、平均ROI）
        filtered_count = len(self.tree.get_children())
        if filtered_count > 0:
            total_roi = 0.0
            up_count = 0
            down_count = 0
            for item_id in self.tree.get_children():
                vals = self.tree.item(item_id, "values")
                try:
                    roi_val = float(vals[6].replace('%', '').replace('+', ''))
                except Exception:
                    roi_val = 0.0
                total_roi += roi_val
                if roi_val > 0:
                    up_count += 1
                elif roi_val < 0:
                    down_count += 1
            avg_roi = total_roi / filtered_count
            
            # 使用对应极客高反差红绿颜色标识强度（红涨 `#e91e63`，绿跌 `#388e3c`）
            stat_color = "#e91e63" if avg_roi >= 0 else "#388e3c"
            self.status_lbl.config(
                text=f"📊 筛选: {filtered_count}只 | 📈上涨:{up_count} 📉下跌:{down_count} | 均幅:{avg_roi:+.2f}%",
                fg=stat_color
            )
        else:
            self.status_lbl.config(text="🔍 无匹配个股", fg="#888888")

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
        
        # 🚀 [NEW] 历史追踪有筛选过滤条件时的前3个题材权重最高绝对优先排序算法
        current_filter = ""
        if hasattr(self, 'search_var'):
            current_filter = self.search_var.get().lower().strip()
        elif hasattr(self.parent_win, 'concept_filter_var'):
            current_filter = self.parent_win.concept_filter_var.get().lower().strip()
            
        kws = current_filter.split() if current_filter else []
        
        if col == "sector" and kws:
            def get_sort_key(t):
                val = str(t[0]).lower()
                cats = [c.strip() for c in re.split(r'[;|★\s]', val) if c.strip() and c.strip() not in ('nan', 'NaN', '0')]
                match_idx = 999
                for idx, cat in enumerate(cats):
                    if any(kw in cat for kw in kws):
                        match_idx = idx
                        break
                # 数学对齐：确保升序降序匹配度最高的（match_idx越小）股票永远绝对排在最前面
                prio = match_idx if not reverse else (999 - match_idx)
                return (prio, t[0])
                
            try:
                l.sort(key=get_sort_key, reverse=reverse)
            except Exception:
                l.sort(reverse=reverse)
        else:
            try:
                l.sort(key=lambda t: float(t[0].replace('%','')) if t[0] and t[0].strip() else -999, reverse=reverse)
            except:
                l.sort(reverse=reverse)
        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self._sort_tree(col, not reverse))
        # [NEW] 排序后自动滚动到顶部
        self.tree.yview_moveto(0)


# ══════════════════════════════════════════════════════════════════════════════
# StockSelectionWindow — 盘中交易新能力（板块聚焦 Tab + 实时决策 Tab）
# 以 monkey-patch 形式追加到类，保持文件结构不变
# ══════════════════════════════════════════════════════════════════════════════

def _init_sector_tab(self, parent: tk.Frame):
    """
    板块聚焦 Tab 初始化
    ─────────────────────
    上方：板块热力排行榜（实时更新）
    下方：选中板块的成员股详情 + 龙头标识
    """
    # ── 顶部信息行 ───────────────────────────────────────────────────────────
    info_bar = tk.Frame(parent, bg="#1a2332")
    info_bar.pack(fill="x", pady=2)

    self._sector_status_lbl = tk.Label(
        info_bar, text="⏸ 等待数据...",
        bg="#1a2332", fg="#aaaaaa", font=("Arial", 9)
    )
    self._sector_status_lbl.pack(side="left", padx=8)

    tk.Button(
        info_bar, text="⟳ 立即刷新",
        bg="#2c3e50", fg="#00cc88", font=("Arial", 9),
        relief="flat", pady=1,
        command=self._force_refresh_sector,
    ).pack(side="right", padx=8)

    # ── 板块热力排行（上半区）────────────────────────────────────────────────
    self._sector_paned = tk.PanedWindow(parent, orient="vertical", sashrelief="raised", sashwidth=5)
    self._sector_paned.pack(fill="both", expand=True)

    top_frame = tk.Frame(self._sector_paned, bg="#0e1621")
    self._sector_paned.add(top_frame, height=300)

    sector_cols = ("rank", "name", "heat", "bid_score", "zt_count", "leader_code", "leader_name", "leader_pct", "followers")
    self._sector_tree = ttk.Treeview(top_frame, columns=sector_cols, show="headings", height=8, style="Dark.Treeview")

    sec_headers = {
        "rank": "排名", "name": "板块名称", "heat": "热力分",
        "bid_score": "竞价均分", "zt_count": "涨停数",
        "leader_code": "龙头代码", "leader_name": "龙头名",
        "leader_pct": "龙头涨幅%", "followers": "跟进股",
    }
    for col, text in sec_headers.items():
        self._sector_tree.heading(col, text=text, command=lambda c=col: self._sort_sector_tree(c))
        self._sector_tree.column(col, anchor="center", width=80)

    self._sector_tree.column("name", width=120, stretch=False)
    self._sector_tree.column("followers", width=200, stretch=True)
    self._sector_tree.column("heat", width=65, stretch=False)

    self._sector_tree.tag_configure("hot1", background="#3a1a1a", foreground="#ff4444")  # 第1名
    self._sector_tree.tag_configure("hot2", background="#2a1f0a", foreground="#ff9900")  # 第2名
    self._sector_tree.tag_configure("hot3", background="#1a2a1a", foreground="#44cc44")  # 第3名
    self._sector_tree.tag_configure("normal", background="#0e1621", foreground="#cccccc")

    sec_vsb = ttk.Scrollbar(top_frame, orient="vertical", command=self._sector_tree.yview)
    self._sector_tree.configure(yscroll=sec_vsb.set)
    self._sector_tree.grid(row=0, column=0, sticky="nsew")
    sec_vsb.grid(row=0, column=1, sticky="ns")
    top_frame.grid_rowconfigure(0, weight=1)
    top_frame.grid_columnconfigure(0, weight=1)

    self._sector_tree.bind("<<TreeviewSelect>>", self._on_sector_selected)

    # ── 成员股详情（下半区）──────────────────────────────────────────────────
    bottom_frame = tk.Frame(self._sector_paned, bg="#0e1621")
    self._sector_paned.add(bottom_frame, height=200)

    self._sector_detail_lbl = tk.Label(
        bottom_frame, text="← 点击板块查看成员股",
        bg="#0e1621", fg="#666666", font=("Arial", 9, "italic"),
        anchor="w",
    )
    self._sector_detail_lbl.pack(fill="x", padx=5, pady=2)

    member_cols = ("code", "name", "role", "percent", "bid_score", "vol_ratio", "pullback_signal")
    self._member_tree = ttk.Treeview(bottom_frame, columns=member_cols, show="headings", height=5, style="Dark.Treeview")

    mem_headers = {
        "code": "代码", "name": "名称", "role": "角色",
        "percent": "涨幅%", "bid_score": "竞价分",
        "vol_ratio": "量比", "pullback_signal": "买点信号",
    }
    for col, text in mem_headers.items():
        self._member_tree.heading(col, text=text)
        self._member_tree.column(col, anchor="center", width=90)
    self._member_tree.column("name", width=80, stretch=False)
    self._member_tree.column("pullback_signal", width=200, stretch=True)

    self._member_tree.tag_configure("leader", background="#3a1a00", foreground="#ff8844")
    self._member_tree.tag_configure("follower", background="#001a2a", foreground="#44aaff")
    self._member_tree.tag_configure("signal", background="#001a10", foreground="#44ff88")

    mem_vsb = ttk.Scrollbar(bottom_frame, orient="vertical", command=self._member_tree.yview)
    self._member_tree.configure(yscroll=mem_vsb.set)
    self._member_tree.pack(side="left", fill="both", expand=True)
    mem_vsb.pack(side="right", fill="y")

    self._member_tree.bind("<<TreeviewSelect>>", self._on_member_selected)
    self._member_tree.bind("<Double-1>", self._on_member_selected)
    self._member_tree.bind("<Button-3>", self.show_context_menu)


def _init_decision_tab(self, parent: tk.Frame):
    """
    实时决策队列 Tab 初始化
    ────────────────────────
    上方：持仓汇总条（资金风控状态）
    中部：待操作信号列表（优先级排序）
    下方：今日持仓 + 交易流水分栏
    """
    # ── 风控状态条 ───────────────────────────────────────────────────────────
    risk_bar = tk.Frame(parent, bg="#1a0010", pady=3)
    risk_bar.pack(fill="x")

    self._risk_status_lbl = tk.Label(
        risk_bar, text="🛡 风控: 正常 | 持仓: 0/10 | 今日盈亏: --",
        bg="#1a0010", fg="#aaaaaa", font=("Arial", 9, "bold")
    )
    self._risk_status_lbl.pack(side="left", padx=8)
    self._kernel_status_lbl = tk.Label(
        risk_bar, text="Kernel: idle",
        bg="#1a0010", fg="#55ffff", font=("Arial", 9, "bold")
    )
    self._kernel_status_lbl.pack(side="left", padx=12)

    # 🚀 [NEW] 极客暗黑风格交易内核模式选择菜单按钮
    if not hasattr(self, "_kernel_mode_var"):
        self._kernel_mode_var = tk.StringVar(value="PAPER 模拟")
    
    mode_btn = tk.Menubutton(
        risk_bar, text="⚙ PAPER 模拟 ▾",
        bg="#1a0010", fg="#ffcc66", activebackground="#2c1a00", activeforeground="#ffcc66",
        font=("Arial", 9, "bold"), relief="flat", bd=0, highlightthickness=0
    )
    mode_btn.pack(side="left", padx=15)
    
    mode_menu = tk.Menu(
        mode_btn, tearoff=0, bg="#0c101b", fg="#ffffff", 
        activebackground="#2c3e50", activeforeground="#55ffff",
        bd=1, font=("Arial", 9)
    )
    mode_btn.config(menu=mode_menu)
    
    def select_mode(m):
        self._kernel_mode_var.set(m)
        mode_btn.config(text=f"⚙ {m} ▾")
        self._kernel_set_status(f"mode switched to {m}", "info")
        
    for m in ["OBSERVE 观察", "PAPER 模拟", "CONFIRM 确认", "LIVE_AUTO 自动"]:
        mode_menu.add_command(label=m, command=lambda val=m: select_mode(val))

    btn_frame = tk.Frame(risk_bar, bg="#1a0010")
    btn_frame.pack(side="right", padx=5)
    tk.Button(btn_frame, text="🗑 清除已完结", bg="#2c1a00", fg="#cc8800",
              font=("Arial", 8), relief="flat", pady=1,
              command=self._clear_done_signals).pack(side="left", padx=2)
    tk.Button(btn_frame, text="📤 一键卖出全部", bg="#3a0000", fg="#ff4444",
              font=("Arial", 8), relief="flat", pady=1,
              command=self._sell_all_positions).pack(side="left", padx=2)

    # ── 主体分栏 ─────────────────────────────────────────────────────────────
    self._decision_paned = tk.PanedWindow(parent, orient="vertical", sashrelief="raised", sashwidth=5)
    self._decision_paned.pack(fill="both", expand=True)

    # 上半：决策信号队列
    signal_frame = tk.LabelFrame(self._decision_paned, text="  🎯 实时买点决策队列（按优先级排序）  ",
                                  bg="#0a0f1a", fg="#00cc88", font=("Arial", 9, "bold"))
    self._decision_paned.add(signal_frame, height=300)

    sig_cols = ("time", "priority", "kernel_action", "kernel_size", "kernel_conf", "kernel_risk",
                "code", "name", "sector", "signal_type", "suggest_price",
                "current_price", "change_pct", "sector_heat", "hits", "reason", "status")
    self._signal_tree = ttk.Treeview(signal_frame, columns=sig_cols, show="headings", height=7, style="Dark.Treeview")

    sig_headers = {
        "time": "时间", "priority": "优先级", "code": "代码", "name": "名称",
        "sector": "板块", "signal_type": "信号类型",
        "suggest_price": "建议价", "current_price": "现价",
        "change_pct": "涨幅%", "sector_heat": "热度",
        "hits": "次数", "reason": "触发原因", "status": "状态",
    }
    sig_headers.update({
        "kernel_action": "Kernel",
        "kernel_size": "仓位",
        "kernel_conf": "置信",
        "kernel_risk": "风控",
    })
    for col, text in sig_headers.items():
        self._signal_tree.heading(col, text=text, command=lambda c=col: self._sort_signal_tree(c))
        self._signal_tree.column(col, anchor="center", width=60)
    self._signal_tree.column("reason", width=250, stretch=True)
    self._signal_tree.column("sector", width=80, stretch=False)
    self._signal_tree.column("name", width=70, stretch=False)
    self._signal_tree.column("time", width=70, stretch=False)
    self._signal_tree.column("hits", width=40, stretch=False)
    self._signal_tree.column("priority", width=50, stretch=False)
    self._signal_tree.column("kernel_action", width=70, stretch=False)
    self._signal_tree.column("kernel_size", width=55, stretch=False)
    self._signal_tree.column("kernel_conf", width=55, stretch=False)
    self._signal_tree.column("kernel_risk", width=85, stretch=False)

    self._signal_tree.tag_configure("high", background="#1a2a00", foreground="#88ff44")   # 高优先级
    self._signal_tree.tag_configure("medium", background="#001a2a", foreground="#44aaff") # 中
    self._signal_tree.tag_configure("done", background="#1a1a1a", foreground="#555555")   # 已完结

    self._signal_tree.tag_configure("kernel_exec", background="#003a24", foreground="#66ffcc")
    self._signal_tree.tag_configure("kernel_block", background="#3a2600", foreground="#ffcc66")
    self._signal_tree.tag_configure("kernel_error", background="#3a0000", foreground="#ff7777")

    sig_vsb = ttk.Scrollbar(signal_frame, orient="vertical", command=self._signal_tree.yview)
    self._signal_tree.configure(yscroll=sig_vsb.set)
    self._signal_tree.grid(row=0, column=0, sticky="nsew")
    sig_vsb.grid(row=0, column=1, sticky="ns")
    signal_frame.grid_rowconfigure(0, weight=1)
    signal_frame.grid_columnconfigure(0, weight=1)

    # 按钮行
    btn_row = tk.Frame(signal_frame, bg="#0a0f1a")
    btn_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
    tk.Button(btn_row, text="📈 模拟买入（选中）", bg="#003a00", fg="#44ff88",
              font=("Arial", 9, "bold"), relief="flat", pady=2,
              command=self._mock_buy_selected).pack(side="left", padx=5)
    tk.Button(btn_row, text="Kernel自动模拟执行", bg="#004040", fg="#55ffff",
              font=("Arial", 9, "bold"), relief="flat", pady=2,
              command=self._kernel_auto_execute_once).pack(side="left", padx=5)
    tk.Button(btn_row, text="刷新持仓/止损", bg="#1f2a3a", fg="#99ccff",
              font=("Arial", 9), relief="flat", pady=2,
              command=self._kernel_refresh_positions).pack(side="left", padx=3)
    tk.Button(btn_row, text="🔧 数据自愈修复", bg="#2a1f3d", fg="#d199ff",
              font=("Arial", 9, "bold"), relief="flat", pady=2,
              command=self._on_one_key_self_heal).pack(side="left", padx=3)
    tk.Button(btn_row, text="🚫 忽略（选中）", bg="#2a2a2a", fg="#888888",
              font=("Arial", 9), relief="flat", pady=2,
              command=self._ignore_selected_signal).pack(side="left", padx=3)

    self._signal_tree.bind("<Double-1>", self._on_signal_double_click)
    self._signal_tree.bind("<<TreeviewSelect>>", self._on_signal_selected)
    self._signal_tree.bind("<Button-3>", self.show_context_menu)

    self._sig_tooltip_win = None
    self._sig_last_hover_id = None
    
    def on_sig_motion(event):
        item = self._signal_tree.identify_row(event.y)
        col = self._signal_tree.identify_column(event.x)
        if item and col:
            col_name = self._signal_tree.column(col, 'id')
            if col_name == 'reason':
                if self._sig_last_hover_id == item:
                    return
                self._sig_last_hover_id = item
                hide_sig_tooltip()
                try:
                    vals = self._signal_tree.item(item, 'values')
                    txt = vals[15] if len(vals) > 15 else ""
                    if txt:
                        # 文字多行显示
                        txt = str(txt).replace('|', '\n').replace('；', '\n').replace(';', '\n')
                        
                        self._sig_tooltip_win = tk.Toplevel(self._signal_tree)
                        self._sig_tooltip_win.wm_overrideredirect(True)
                        self._sig_tooltip_win.attributes("-topmost", True)
                        
                        # 计算位置，避免屏幕右侧遮挡
                        screen_w = self._signal_tree.winfo_screenwidth()
                        est_w = 380 # 预估悬浮窗最大宽度
                        x_pos = event.x_root + 15
                        if x_pos + est_w > screen_w:
                            x_pos = event.x_root - est_w - 10
                        y_pos = event.y_root + 15
                        
                        self._sig_tooltip_win.geometry(f"+{x_pos}+{y_pos}")
                        
                        # 红色文字
                        tk.Label(self._sig_tooltip_win, text=txt, bg="#1a0000", fg="#ff3333", 
                                 font=("Arial", 10, "bold"), justify="left", wraplength=350,
                                 relief="solid", bd=1, padx=6, pady=4).pack()
                except Exception:
                    pass
                return
        hide_sig_tooltip()
        self._sig_last_hover_id = None

    def hide_sig_tooltip(event=None):
        if getattr(self, '_sig_tooltip_win', None):
            self._sig_tooltip_win.destroy()
            self._sig_tooltip_win = None

    self._signal_tree.bind("<Motion>", on_sig_motion)
    self._signal_tree.bind("<Leave>", hide_sig_tooltip)

    # 下半：持仓 + 流水分栏
    bottom_nb = ttk.Notebook(self._decision_paned)
    self._decision_paned.add(bottom_nb, height=200)

    # 持仓 Tab
    pos_frame = tk.Frame(bottom_nb, bg="#0a0f1a")
    bottom_nb.add(pos_frame, text="📊 当前持仓")

    pos_cols = ("code", "name", "sector", "entry_price", "current_price",
                "pnl_pct", "pnl_value", "shares", "stop_loss", "entry_time")
    self._pos_tree = ttk.Treeview(pos_frame, columns=pos_cols, show="headings", height=5, style="Dark.Treeview")
    pos_headers = {
        "code":"代码","name":"名称","sector":"板块",
        "entry_price":"入场价","current_price":"现价",
        "pnl_pct":"盈亏%","pnl_value":"盈亏额",
        "shares":"股数","stop_loss":"止损价","entry_time":"入场时间",
    }
    for col, text in pos_headers.items():
        self._pos_tree.heading(col, text=text)
        self._pos_tree.column(col, anchor="center", width=80)
    self._pos_tree.column("name", width=75, stretch=False)
    self._pos_tree.column("sector", width=100, stretch=False)

    self._pos_tree.tag_configure("profit", background="#0e1621", foreground="#44ff88")
    self._pos_tree.tag_configure("loss",   background="#0e1621", foreground="#ff4444")
    self._pos_tree.tag_configure("flat",   background="#0e1621", foreground="#cccccc")

    pos_vsb = ttk.Scrollbar(pos_frame, orient="vertical", command=self._pos_tree.yview)
    self._pos_tree.configure(yscroll=pos_vsb.set)
    self._pos_tree.pack(side="left", fill="both", expand=True)
    pos_vsb.pack(side="right", fill="y")

    tk.Button(pos_frame, text="📉 卖出选中", bg="#3a0000", fg="#ff6666",
              font=("Arial", 9), relief="flat",
              command=self._mock_sell_selected).pack(side="bottom", pady=3)

    # 流水 Tab
    log_frame = tk.Frame(bottom_nb, bg="#0a0f1a")
    bottom_nb.add(log_frame, text="📜 今日流水")

    log_cols = ("time", "action", "code", "name", "price", "shares", "amount", "pnl_pct", "reason")
    self._log_tree = ttk.Treeview(log_frame, columns=log_cols, show="headings", height=5, style="Dark.Treeview")
    log_headers = {
        "time":"时间","action":"操作","code":"代码","name":"名称",
        "price":"价格","shares":"股数","amount":"金额",
        "pnl_pct":"盈亏%","reason":"原因",
    }
    for col, text in log_headers.items():
        self._log_tree.heading(col, text=text)
        self._log_tree.column(col, anchor="center", width=80)
    self._log_tree.column("reason", width=200, stretch=True)
    self._log_tree.tag_configure("buy",         background="#0e1621", foreground="#44aaff")
    self._log_tree.tag_configure("sell_profit", background="#0e1621", foreground="#44ff88")
    self._log_tree.tag_configure("sell_loss",   background="#0e1621", foreground="#ff4444")

    log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self._log_tree.yview)
    self._log_tree.configure(yscroll=log_vsb.set)
    self._log_tree.pack(side="left", fill="both", expand=True)
    log_vsb.pack(side="right", fill="y")

    # 绑定持仓与流水表格的单元格单选选中联动事件与右键菜单
    self._pos_tree.bind("<<TreeviewSelect>>", self._on_pos_selected)
    self._log_tree.bind("<<TreeviewSelect>>", self._on_log_selected)
    self._pos_tree.bind("<Button-3>", self.show_context_menu)
    self._log_tree.bind("<Button-3>", self.show_context_menu)

    # [NEW] 启动决策树行慢闪烁呼吸灯定时器
    self._schedule_kernel_blink()


def _schedule_focus_refresh(self):
    """每15秒刷新一次两个盘中Tab（仅当窗口存在时）"""
    try:
        self._refresh_focus_tabs()
        self._focus_refresh_id = self.after(15000, self._schedule_focus_refresh)
    except tk.TclError:
        pass  # 窗口已销毁


def _refresh_focus_tabs(self):
    """刷新板块聚焦 + 实时决策 Tab 的数据"""
    try:
        self._kernel_refresh_positions(show_message=False)
    except Exception as e:
        logger.debug(f"[refresh_focus_tabs] refresh positions error: {e}")
    try:
        self._kernel_auto_execute_once(auto_mode=True)
    except Exception as e:
        logger.debug(f"[refresh_focus_tabs] auto execute once error: {e}")
    self._refresh_sector_tab()
    self._refresh_decision_tab()
    if hasattr(self, '_refresh_guidance_tab'):
        self._refresh_guidance_tab()


def _refresh_sector_tab(self):
    """更新板块热力排行表"""
    if not hasattr(self, '_sector_tree'):
        return
    if not self._focus_ctrl:
        self._sector_status_lbl.config(text="⏸ 交易引擎未初始化", fg="#666666")
        return

    try:
        hot_sectors = self._focus_ctrl.get_hot_sectors(top_n=20)
        if not hot_sectors:
            self._sector_status_lbl.config(
                text="⏸ 暂无板块数据（等待竞价开始或行情推送）", fg="#888888"
            )
            return

        # 清空并重填（板块数量少，不需要Diff模型）
        self._sector_tree.delete(*self._sector_tree.get_children())

        for i, s in enumerate(hot_sectors, 1):
            tag = "hot1" if i == 1 else ("hot2" if i == 2 else ("hot3" if i == 3 else "normal"))
            followers_str = " / ".join(s.get('follower_codes', []))
            self._sector_tree.insert("", "end", iid=str(i), values=(
                f"#{i}",
                s.get('name', ''),
                f"{s.get('heat_score', 0):.1f}",
                f"{s.get('bidding_score', 0):.2f}",
                s.get('zt_count', 0),
                s.get('leader_code', ''),
                s.get('leader_name', ''),
                f"{s.get('leader_change_pct', 0):+.2f}%",
                followers_str,
            ), tags=(tag,))

        now_str = datetime.now().strftime('%H:%M:%S')
        self._sector_status_lbl.config(
            text=f"✅ 已更新 {now_str} | 监控板块: {len(hot_sectors)} 个",
            fg="#00cc88"
        )
    except Exception as e:
        logger.debug(f"[sector_tab] refresh error: {e}")


def _on_sector_selected(self, event=None):
    """点击板块行，展示该板块成员股详情"""
    if not hasattr(self, '_member_tree') or not self._focus_ctrl:
        return
    sel = self._sector_tree.selection()
    if not sel:
        return

    try:
        vals = self._sector_tree.item(sel[0], "values")
        if not vals or len(vals) < 2:
            return
        sector_name = vals[1].strip()
        
        hot_sectors = self._focus_ctrl.get_hot_sectors(top_n=20)
        sh = next((s for s in hot_sectors if s.get('name', '').strip() == sector_name), None)
        if not sh:
            return
        self._sector_detail_lbl.config(
            text=f"🔥 {sector_name}  |  龙头: {sh.get('leader_name','')}({sh.get('leader_code','')})"
        )

        # 从实时行情中取该板块成员
        self._member_tree.delete(*self._member_tree.get_children())

        df_rt = None
        if self.selector and hasattr(self.selector, 'df_all_realtime'):
            df_rt = self.selector.df_all_realtime

        if df_rt is None or df_rt.empty:
            return

        # 筛选该板块
        col = 'category'
        if col not in df_rt.columns:
            return

        leader_code = str(sh.get('leader_code', ''))
        followers = [str(c) for c in sh.get('follower_codes', [])]
        target_codes = set(followers)
        if leader_code:
            target_codes.add(leader_code)

        members = df_rt[df_rt.index.isin(target_codes)].copy()

        if members.empty:
            return

        members['_pct'] = pd.to_numeric(members.get('percent', 0), errors='coerce').fillna(0)
        members = members.sort_values('_pct', ascending=False)

        leader_code = sh.get('leader_code', '')
        followers = sh.get('follower_codes', [])
        decision_codes = {s['code'] for s in self._focus_ctrl.get_decision_queue()}

        for _, row in members.iterrows():
            code = str(row.get('code', row.name))
            name = str(row.get('name', code))
            pct = float(row.get('percent', row.get('_pct', 0)))

            if code == leader_code:
                role = "🌟龙头"
                tag = "leader"
            elif code in followers:
                role = "⭐跟进"
                tag = "follower"
            else:
                role = "观察"
                tag = "normal"

            signal_str = "⚡ 买点!" if code in decision_codes else ""
            if code in decision_codes:
                tag = "signal"

            self._member_tree.insert("", "end", iid=code, values=(
                code, name, role,
                f"{pct:+.2f}%",
                f"{row.get('_bid_score', 0):.1f}",
                f"{row.get('ratio', 1.0):.2f}",
                signal_str,
            ), tags=(tag,))
        
        # 自动联动到龙头股
        if leader_code and hasattr(self, 'sender') and self.sender:
            try:
                self.sender.send(leader_code)
            except Exception:
                pass
            if getattr(self, 'master', None) and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
                if hasattr(self.master, 'open_visualizer'):
                    self.master.open_visualizer(leader_code)
    except Exception as e:
        logger.debug(f"[on_sector_selected] error: {e}")


def _on_member_selected(self, event=None):
    """单击或双击成员股联动主界面 K 线图"""
    sel = self._member_tree.selection()
    if not sel:
        return
    code = sel[0]
    if hasattr(self, 'sender') and self.sender:
        try:
            self.sender.send(code)
        except Exception:
            pass
    if getattr(self, 'master', None) and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
        if hasattr(self.master, 'open_visualizer'):
            self.master.open_visualizer(code)


def _force_refresh_sector(self):
    """手动触发板块数据强制更新"""
    if not self._focus_ctrl:
        return
    # 注入当前实时行情并立即刷新
    if self.selector and hasattr(self.selector, 'df_all_realtime'):
        df = self.selector.df_all_realtime
        if not df.empty:
            self._focus_ctrl.inject_realtime(df)
    self._refresh_sector_tab()


def _sort_sector_tree(self, col: str):
    """板块列表点击表头排序"""
    try:
        items = [(self._sector_tree.set(k, col), k) for k in self._sector_tree.get_children('')]
        try:
            items.sort(key=lambda x: float(x[0].replace('%', '').replace('#', '').replace('▲', '').replace('▼', '') or 0), reverse=True)
        except Exception:
            items.sort()
        for idx, (_, k) in enumerate(items):
            self._sector_tree.move(k, '', idx)
        # [NEW] 排序后自动滚动到顶部
        self._sector_tree.yview_moveto(0)
    except Exception as e:
        logger.debug(f"_sort_sector_tree: {e}")


def _refresh_decision_tab(self):
    """更新实时决策队列 + 持仓 + 流水"""
    if not hasattr(self, '_signal_tree'):
        return

    # ── 决策信号队列 ──────────────────────────────────────────────────────────
    if self._focus_ctrl:
        try:
            signals = self._focus_ctrl.get_decision_queue()
            existing = {self._signal_tree.set(k, 'code'): k for k in self._signal_tree.get_children()}

            for s in signals:
                code = s['code']
                priority = s['priority']
                tag = "high" if priority >= 70 else ("medium" if priority >= 50 else "normal")
                if s['status'] in ('已忽略', '已成交'):
                    tag = "done"

                values = (
                    s.get('created_at', ''),
                    priority,
                    s.get('kernel_action', ''),
                    f"{float(s.get('kernel_size_pct', 0) or 0):.0%}",
                    f"{float(s.get('kernel_confidence', 0) or 0):.2f}",
                    "OK" if s.get('kernel_allowed') else (s.get('kernel_reject_code') or "BLOCK"),
                    code, s['name'], s['sector'],
                    s['signal_type'],
                    s.get('suggest_price', 0),
                    s.get('current_price', 0),
                    f"{s.get('change_pct', 0):+.2f}%",
                    f"{s.get('sector_heat', 0):.1f}",
                    s.get('hits', 1),
                    s.get('reason', ''),
                    s.get('status', ''),
                )
                # [FIX] 如果在 marked 集合中，覆盖为 kernel 执行状态的高亮 tag，实现高亮刷新不消失
                if getattr(self, '_kernel_marked_exec', None) and code in self._kernel_marked_exec:
                    tag = "kernel_exec"
                elif getattr(self, '_kernel_marked_block', None) and code in self._kernel_marked_block:
                    tag = "kernel_block"
                elif getattr(self, '_kernel_marked_error', None) and code in self._kernel_marked_error:
                    tag = "kernel_error"

                if code in existing:
                    self._signal_tree.item(existing[code], values=values, tags=(tag,))
                else:
                    self._signal_tree.insert("", "end", iid=code, values=values, tags=(tag,))
        except Exception as e:
            logger.debug(f"[decision_tab] signal refresh: {e}")

    # ── 持仓 ──────────────────────────────────────────────────────────────────
    if self._trade_gw:
        try:
            positions = self._trade_gw.get_positions()
            existing_pos = set(self._pos_tree.get_children())
            current_codes = set()

            for p in positions:
                code = p['code']
                current_codes.add(code)
                pnl_pct = p['pnl_pct']
                tag = "profit" if pnl_pct > 0 else ("loss" if pnl_pct < 0 else "flat")
                values = (
                    code, p['name'], p['sector'],
                    p['entry_price'], p['current_price'],
                    f"{pnl_pct:+.2f}%", f"{p['pnl_value']:+.2f}",
                    p['shares'], p['stop_loss'], p['entry_time'],
                )
                if code in existing_pos:
                    self._pos_tree.item(code, values=values, tags=(tag,))
                else:
                    self._pos_tree.insert("", "end", iid=code, values=values, tags=(tag,))

            for code in (existing_pos - current_codes):
                self._pos_tree.delete(code)

            # 风控状态条更新
            summary = self._trade_gw.get_summary()
            lock_str = "🔴 已锁仓！" if summary['is_locked'] else "🟢 正常"
            self._risk_status_lbl.config(
                text=(
                    f"🛡 风控: {lock_str} | "
                    f"持仓: {summary['position_count']}/10 | "
                    f"浮动盈亏: {summary['total_unrealized_pnl']:+.2f} | "
                    f"日亏损: {summary['daily_loss_pct']:.2f}%"
                ),
                fg="#ff4444" if summary['is_locked'] else "#aaaaaa"
            )

        except Exception as e:
            logger.debug(f"[decision_tab] position refresh: {e}")

        # ── 今日流水 ──────────────────────────────────────────────────────────
        try:
            logs = self._trade_gw.get_today_log()
            self._log_tree.delete(*self._log_tree.get_children())
            for i, r in enumerate(reversed(logs)):  # 最新在顶
                tag = "buy" if r['action'] == "BUY" else (
                    "sell_profit" if r.get('pnl_pct', 0) >= 0 else "sell_loss"
                )
                self._log_tree.insert("", "end", iid=str(i), values=(
                    r['time'], r['action'], r['code'], r['name'],
                    r['price'], r['shares'], r['amount'],
                    f"{r.get('pnl_pct', 0):+.2f}%" if r['action'] == "SELL" else "--",
                    r.get('reason', ''),
                ), tags=(tag,))
        except Exception as e:
            logger.debug(f"[decision_tab] log refresh: {e}")


def _mock_buy_selected(self):
    """模拟买入：对决策队列中选中的信号执行买入"""
    if not self._trade_gw:
        return
    sel = self._signal_tree.selection()
    if not sel:
        return
    code = sel[0]

    try:
        signals = self._focus_ctrl.get_decision_queue() if self._focus_ctrl else []
        sig = next((s for s in signals if s['code'] == code), None)
        if not sig:
            return

        price = sig.get('suggest_price') or sig.get('current_price', 0)
        if price <= 0:
            messagebox.showwarning("提示", f"{code} 价格异常，无法买入")
            return

        ok, msg = self._trade_gw.submit_buy(
            code=code, name=sig['name'],
            sector=sig.get('sector', ''),
            price=price,
            strategy_tag=sig.get('signal_type', ''),
            reason=sig.get('reason', ''),
        )

        if ok:
            # 构造虚拟 BUY 信号，物理写入交易流水，并同步让新交易内核 paper_adapter 执行开仓！
            sig_buy = dict(sig)
            sig_buy.update({
                "action": "BUY",
                "price": price,
                "current_price": price,
                "suggest_price": price,
                "signal_type": sig.get('signal_type') or "手动买入",
                "reason": sig.get('reason') or "手动买入",
                "journal_ts": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
            })
            try:
                from trading_kernel.kernel_service import enrich_decision_item
                enrich_decision_item(sig_buy, write_journal=True)
            except Exception as e_journal:
                logger.warning(f"Error enriching buy journal in stock_selection_window: {e_journal}")

            # 更新信号状态
            if self._focus_ctrl:
                self._focus_ctrl.decision_queue.update_status(code, "已提交")
            self._refresh_decision_tab()
            messagebox.showinfo("模拟买入", msg)
        else:
            messagebox.showwarning("买入拒绝", msg)
    except Exception as e:
        messagebox.showerror("错误", str(e))


def _mock_sell_selected(self):
    """模拟卖出：对持仓中选中的股票执行卖出"""
    if not self._trade_gw:
        return
    sel = self._pos_tree.selection()
    if not sel:
        return
    code = sel[0]

    # 获取当前价（从实时行情）
    price = 0.0
    name_val = "手动卖出"
    if self.selector and hasattr(self.selector, 'df_all_realtime'):
        df = self.selector.df_all_realtime
        if code in df.index:
            price = float(df.loc[code].get('trade', df.loc[code].get('price', 0)) or 0)
            name_val = df.loc[code].get('name', '手动卖出')

    if price <= 0:
        ans = messagebox.askstring("手动输入价格", f"无法获取 {code} 实时价，请手动输入卖出价格：")
        try:
            price = float(ans or 0)
        except Exception:
            price = 0

    if price <= 0:
        messagebox.showwarning("提示", "价格无效，取消卖出")
        return

    ok, msg = self._trade_gw.submit_sell(code, price, reason="手动卖出")
    if ok:
        # 构造虚拟 SELL 信号，物理写入交易流水，并同步让新交易内核 paper_adapter 执行平仓！
        sig_sell = {
            "code": code,
            "name": name_val,
            "signal_type": "手动卖出",
            "action": "SELL",
            "price": price,
            "current_price": price,
            "suggest_price": price,
            "reason": "手动卖出",
            "journal_ts": datetime.now().isoformat(),
            "created_at": datetime.now().isoformat(),
        }
        try:
            from trading_kernel.kernel_service import enrich_decision_item
            enrich_decision_item(sig_sell, write_journal=True)
        except Exception as e_journal:
            logger.warning(f"Error enriching sell journal in stock_selection_window: {e_journal}")

        self._refresh_decision_tab()
        messagebox.showinfo("模拟卖出", msg)
    else:
        messagebox.showwarning("卖出失败", msg)


def _get_realtime_price_map(self, codes=None):
    """Build {code: price} from the current realtime DataFrame if available."""
    price_map = {}
    df_rt = None
    if self.selector and hasattr(self.selector, 'df_all_realtime'):
        df_rt = self.selector.df_all_realtime
    if df_rt is None and self.master and hasattr(self.master, 'df_all'):
        df_rt = self.master.df_all
    if df_rt is None or getattr(df_rt, 'empty', True):
        return price_map
    try:
        if codes is not None:
            # Targeted fast lookup for specified codes
            for code in codes:
                code_str = str(code).zfill(6)
                row = None
                if code_str in df_rt.index:
                    row = df_rt.loc[code_str]
                else:
                    try:
                        code_int = int(code_str)
                        if code_int in df_rt.index:
                            row = df_rt.loc[code_int]
                    except ValueError:
                        pass
                if row is not None:
                    price = float(row.get('trade', row.get('price', row.get('close', 0))) or 0)
                    if price > 0:
                        price_map[code_str] = price
        else:
            # Vectorized fast pandas extraction of entire price map
            cols = ['trade', 'price', 'close']
            available_cols = [c for c in cols if c in df_rt.columns]
            if available_cols:
                series = None
                for c in available_cols:
                    s_val = df_rt[c]
                    if series is None:
                        series = s_val
                    else:
                        series = series.fillna(s_val)
                if series is not None:
                    series = pd.to_numeric(series, errors='coerce').fillna(0)
                    series = series[series > 0]
                    # Map index to padded strings
                    idx_mapped = [str(x).zfill(6) for x in series.index]
                    price_map = dict(zip(idx_mapped, series.values))
    except Exception as e:
        logger.warning(f"Error in _get_realtime_price_map: {e}")
    return price_map


def _kernel_set_status(self, text, kind="info"):
    """Update the non-blocking kernel status strip."""
    color_map = {
        "ok": "#66ffcc",
        "warn": "#ffcc66",
        "error": "#ff7777",
        "info": "#55ffff",
    }
    try:
        if hasattr(self, "_kernel_status_lbl"):
            self._kernel_status_lbl.config(text=f"Kernel: {text}", fg=color_map.get(kind, "#55ffff"))
    except Exception:
        pass


def _kernel_mark_signal_rows(self, executed=None, blocked=None, errors=None):
    """Highlight and scroll to the latest kernel-related signal rows."""
    executed = executed or []
    blocked = blocked or []
    errors = errors or []
    
    if not hasattr(self, '_kernel_marked_exec'):
        self._kernel_marked_exec = set()
    if not hasattr(self, '_kernel_marked_block'):
        self._kernel_marked_block = set()
    if not hasattr(self, '_kernel_marked_error'):
        self._kernel_marked_error = set()
        
    for c in executed:
        self._kernel_marked_exec.add(c)
        self._kernel_marked_block.discard(c)
        self._kernel_marked_error.discard(c)
    for c in blocked:
        self._kernel_marked_block.add(c)
        self._kernel_marked_exec.discard(c)
        self._kernel_marked_error.discard(c)
    for c in errors:
        self._kernel_marked_error.add(c)
        self._kernel_marked_exec.discard(c)
        self._kernel_marked_block.discard(c)
        
    try:
        first = None
        for code in executed:
            if self._signal_tree.exists(code):
                self._signal_tree.item(code, tags=("kernel_exec",))
                first = first or code
        for code in blocked:
            if self._signal_tree.exists(code):
                self._signal_tree.item(code, tags=("kernel_block",))
                first = first or code
        for code in errors:
            if self._signal_tree.exists(code):
                self._signal_tree.item(code, tags=("kernel_error",))
                first = first or code
        if first:
            self._signal_tree.selection_set(first)
            self._signal_tree.focus(first)
            self._signal_tree.see(first)
    except Exception:
        pass


def _kernel_show_toast(self, text, kind="info", records=None):
    """显示或更新悬浮的 Kernel 自动交易执行看板，支持 Treeview 列表和实时代码联动。"""
    records = records or []
    try:
        win = getattr(self, "_kernel_toast_win", None)
        # 如果窗口不存在或已被销毁，则新建一个
        if not win or not win.winfo_exists():
            win = tk.Toplevel(self)
            self._kernel_toast_win = win
            win.title("📡 Kernel 自动交易执行看板")
            win.geometry("520x350")
            win.configure(bg="#0c101b")
            
            # 初始化置顶状态控制变量 (当前选股窗口运行期保持状态，默认置顶)
            if not hasattr(self, "_kernel_toast_topmost_var"):
                self._kernel_toast_topmost_var = tk.BooleanVar(value=False)
            
            win.attributes("-topmost", self._kernel_toast_topmost_var.get())
            
            # 手动关闭看板时的统一样式保存与销毁处理
            def _on_toast_close():
                try:
                    self.save_window_position(win, "kernel_toast_window")
                except Exception:
                    pass
                win.destroy()
            
            win.protocol("WM_DELETE_WINDOW", _on_toast_close)
            
            # 顶部信息栏
            top_frame = tk.Frame(win, bg="#111726", pady=4)
            top_frame.pack(fill="x")
            
            self._kernel_toast_msg_lbl = tk.Label(
                top_frame, text=text, bg="#111726", fg="#55ffff",
                font=("Arial", 10, "bold")
            )
            self._kernel_toast_msg_lbl.pack(side="left", padx=10)
            
            # 关闭按钮
            tk.Button(
                top_frame, text="✕ 关闭", bg="#3a1a1a", fg="#ff5555",
                font=("Arial", 9), relief="flat", padx=5,
                command=_on_toast_close
            ).pack(side="right", padx=10)
            
            # 置顶切换回调
            def _toggle_topmost():
                is_top = self._kernel_toast_topmost_var.get()
                win.attributes("-topmost", is_top)
            
            # 置顶复选框 (置顶在关闭左侧)
            cb_topmost = tk.Checkbutton(
                top_frame, text="📌 置顶", variable=self._kernel_toast_topmost_var,
                command=_toggle_topmost, bg="#111726", fg="#ffffff", selectcolor="#0c101b",
                activebackground="#111726", activeforeground="#ffffff",
                font=("Arial", 9), bd=0, highlightthickness=0
            )
            cb_topmost.pack(side="right", padx=5)
            
            # 创建 Treeview
            tree_frame = tk.Frame(win, bg="#0c101b")
            tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            cols = ("code", "name", "action", "status", "detail")
            self._kernel_toast_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=10)
            
            headers = {"code": "代码", "name": "名称", "action": "指令", "status": "结果", "detail": "详情"}
            for col, title in headers.items():
                self._kernel_toast_tree.heading(col, text=title)
                self._kernel_toast_tree.column(col, anchor="center", width=75)
            self._kernel_toast_tree.column("detail", width=180, anchor="w", stretch=True)
            self._kernel_toast_tree.column("action", width=60)
            self._kernel_toast_tree.column("status", width=75)
            
            # 样式
            self._kernel_toast_tree.tag_configure("exec", background="#0c1d1a", foreground="#55ffaa")
            self._kernel_toast_tree.tag_configure("block", background="#1d170c", foreground="#ffb833")
            self._kernel_toast_tree.tag_configure("error", background="#1d0c0c", foreground="#ff5555")
            
            vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._kernel_toast_tree.yview)
            self._kernel_toast_tree.configure(yscroll=vsb.set)
            self._kernel_toast_tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            
            # 点击或选择联动事件
            def on_toast_select(event):
                sel = self._kernel_toast_tree.selection()
                if not sel:
                    return
                item_id = sel[0]
                values = self._kernel_toast_tree.item(item_id, "values")
                if not values:
                    return
                code = values[0]
                if code and code != "ERROR" and code != "代码":
                    code = str(code).zfill(6)
                    # 联动主界面 K 线图 (通过 sender 发送)
                    if hasattr(self, 'sender') and self.sender:
                        try:
                            self.sender.send(code)
                        except Exception:
                            pass
                    # 联动可视化视口
                    if getattr(self, 'master', None) and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
                        if hasattr(self.master, 'open_visualizer'):
                            self.master.open_visualizer(code)
            
            self._kernel_toast_tree.bind("<<TreeviewSelect>>", on_toast_select)
            self._kernel_toast_tree.bind("<Double-1>", on_toast_select)
            


            # 优先加载已存位置大小，否则 fallback 居右放置
            has_loaded = False
            try:
                ret = self.load_window_position(
                    win, "kernel_toast_window", 
                    default_width=520, default_height=350
                )
                if ret and len(ret) >= 4 and ret[2] is not None and ret[3] is not None:
                    if ret[2] > 0 or ret[3] > 0:
                        has_loaded = True
            except Exception:
                pass
            if not has_loaded:
                self.update_idletasks()
                x = self.winfo_rootx() + max(20, self.winfo_width() - 560)
                y = self.winfo_rooty() + 60
                win.geometry(f"520x350+{x}+{y}")
        else:
            # 窗口已经存在，更新信息
            self._kernel_toast_msg_lbl.config(text=text)
            
        # 清空并填充最新数据
        self._kernel_toast_tree.delete(*self._kernel_toast_tree.get_children())
        if not records:
            self._kernel_toast_tree.insert("", "end", values=(
                "-",
                "无待执行信号",
                "IDLE",
                "等待中",
                "今日无新增可执行买卖决策或已被去重过滤"
            ), tags=("block",))
        else:
            for r in records:
                status = r.get("status", "")
                tag = "exec" if "执行" in status else ("error" if "异常" in status or "错误" in status else "block")
                self._kernel_toast_tree.insert("", "end", values=(
                    r.get("code", ""),
                    r.get("name", ""),
                    r.get("action", ""),
                    status,
                    r.get("detail", "")
                ), tags=(tag,))
            
    except Exception as e:
        logger.debug(f"[_kernel_show_toast] error: {e}")


def _schedule_kernel_blink(self):
    """使 kernel_exec/kernel_block/kernel_error 等高亮行慢闪烁"""
    if not hasattr(self, '_signal_tree') or not self._signal_tree.winfo_exists():
        return
    try:
        if not hasattr(self, '_kernel_blink_state'):
            self._kernel_blink_state = True
        
        self._kernel_blink_state = not self._kernel_blink_state
        
        if self._kernel_blink_state:
            # 状态 1：明亮高亮
            self._signal_tree.tag_configure("kernel_exec", background="#003a24", foreground="#66ffcc")
            self._signal_tree.tag_configure("kernel_block", background="#3a2600", foreground="#ffcc66")
            self._signal_tree.tag_configure("kernel_error", background="#3a0000", foreground="#ff7777")
        else:
            # 状态 2：暗色呼吸
            self._signal_tree.tag_configure("kernel_exec", background="#0a0f1a", foreground="#44ffaa")
            self._signal_tree.tag_configure("kernel_block", background="#0a0f1a", foreground="#e6b800")
            self._signal_tree.tag_configure("kernel_error", background="#0a0f1a", foreground="#ff5555")
            
        self._kernel_blink_id = self.after(1500, self._schedule_kernel_blink)
    except Exception:
        pass


def _kernel_refresh_positions(self, show_message=True):
    """Refresh simulated positions from realtime prices and run stop-loss checks."""
    if not self._trade_gw:
        return
    price_map = self._get_realtime_price_map()
    if price_map:
        self._trade_gw.update_prices(price_map)
    self._trade_gw.check_stop_loss()
    self._refresh_decision_tab()
    if show_message:
        self._kernel_set_status(f"refreshed positions, prices={len(price_map)}", "info")


def _bg_sync_ui_from_kernel(self, msg, kind, records, executed_codes, blocked_codes, error_codes):
    """主界面被动接受后台交易引擎推送的 UI 刷新指令"""
    try:
        self._kernel_set_status(msg, kind)
        self._kernel_mark_signal_rows(executed_codes, blocked_codes, error_codes)
        self._refresh_decision_tab()
        
        # 如果 toast 窗口是开着的，或者有执行/错误，更新 toast 列表
        if executed_codes or error_codes or (hasattr(self, "_kernel_toast_win") and self._kernel_toast_win and self._kernel_toast_win.winfo_exists()):
            self._kernel_show_toast(msg, kind, records=records)
    except Exception as e:
        logger.debug(f"[_bg_sync_ui_from_kernel] error: {e}")


def _kernel_auto_execute_once(self, auto_mode=False):
    """Execute approved kernel BUY/SELL decisions once through the existing mock gateway."""
    if hasattr(self.master, "bg_kernel_auto_execute_once"):
        # Delegate to the central background executor on the master window
        self.master.bg_kernel_auto_execute_once(auto_mode=auto_mode)
        return

    if auto_mode:
        if not self._trade_gw or not self._focus_ctrl:
            return
    else:
        if not self._trade_gw:
            messagebox.showwarning("Kernel", "模拟交易网关未初始化")
            return
        if not self._focus_ctrl:
            messagebox.showwarning("Kernel", "决策引擎未初始化")
            return

    is_trade_day = cct.get_trade_date_status()
    now_dt = datetime.now()
    now_time = now_dt.hour * 100 + now_dt.minute
    is_active_trading = is_trade_day and ((915 <= now_time <= 1130) or (1300 <= now_time <= 1505))

    # 动态初始化今日去重缓存
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not hasattr(self, "_kernel_last_trade_date") or self._kernel_last_trade_date != today_str:
        self._kernel_last_trade_date = today_str
        self._kernel_today_buys = set()
        self._kernel_today_sells = set()
        self._kernel_today_mocks = set()
        self._kernel_today_confirmed = set()
        self._kernel_today_ignored = set()
        # 尝试从今日已记录的日志中恢复已模拟执行的 code，保障跨会话一致性
        from sys_utils import get_app_root
        trace_path = os.path.join(get_app_root(), "logs", "trading_kernel_trace.jsonl")
        if os.path.exists(trace_path):
            try:
                with open(trace_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-2000:]
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            ts = data.get("trade_date", "") or data.get("journal_ts", "")
                            if ts and ts.startswith(today_str):
                                if data.get("is_simulation", False):
                                    sig = data.get("signal", {})
                                    c_val = sig.get("code") if isinstance(sig, dict) else getattr(sig, "code", None)
                                    if c_val:
                                        self._kernel_today_mocks.add(str(c_val).zfill(6))
                        except Exception:
                            continue
            except Exception:
                pass

    executed = []
    blocked = []
    errors = []
    executed_codes = []
    blocked_codes = []
    error_codes = []
    records = []
    
    # 解析当前选择的交互模式
    mode_text = self._kernel_mode_var.get() if hasattr(self, "_kernel_mode_var") else "PAPER 模拟"
    mode = "PAPER"
    if "OBSERVE" in mode_text:
        mode = "OBSERVE"
    elif "CONFIRM" in mode_text:
        mode = "CONFIRM"
    elif "LIVE_AUTO" in mode_text:
        mode = "LIVE_AUTO"

    try:
        signals = self._focus_ctrl.get_decision_queue()
        positions = {p['code']: p for p in self._trade_gw.get_positions()}
        
        # 仅针对活跃持仓与待决策个股执行极速针对性价格提取，避开对数千只股票的O(N)大循环
        target_codes = list(positions.keys()) + [str(sig.get('code', '')).zfill(6) for sig in signals]
        price_map = self._get_realtime_price_map(codes=target_codes)

        from trading_kernel.kernel_service import enrich_decision_item

        for sig in signals:
            code = str(sig.get('code', '')).zfill(6)
            action = str(sig.get('kernel_action', '') or '').upper()
            allowed = bool(sig.get('kernel_allowed'))
            if action in ("HOLD", "", "BLOCK", "ERROR"):
                continue
                
            # 1. 风控未通过拦截
            if not allowed:
                reject_code = sig.get('kernel_reject_code', 'BLOCK')
                blocked.append(f"{code}:{reject_code}")
                blocked_codes.append(code)
                records.append({
                    "code": code,
                    "name": sig.get('name', ''),
                    "action": action,
                    "status": "拦截",
                    "detail": reject_code
                })
                # 拦截记录写盘
                enrich_decision_item(sig, write_journal=True)
                continue

            price = float(sig.get('suggest_price') or sig.get('current_price') or price_map.get(code, 0) or 0)
            if price <= 0:
                logger.warning(f"[Kernel] 交易决策 {code}({sig.get('name', '')}) 缺少实时价格数据，已拦截。建议价={sig.get('suggest_price')}, 当前价={sig.get('current_price')}")
                blocked.append(f"{code}:NO_PRICE")
                blocked_codes.append(code)
                records.append({
                    "code": code,
                    "name": sig.get('name', ''),
                    "action": action,
                    "status": "拦截",
                    "detail": "无实时价格"
                })
                enrich_decision_item(sig, write_journal=True)
                continue

            # 2. 风控已放行，根据不同模式分流执行：

            # A. OBSERVE (观察模式)
            if mode == "OBSERVE":
                executed.append(f"OBS_{action} {code}")
                executed_codes.append(code)
                self._focus_ctrl.decision_queue.update_status(code, "已观察")
                records.append({
                    "code": code,
                    "name": sig.get('name', ''),
                    "action": action,
                    "status": "观察中",
                    "detail": f"OBSERVE 放行信号 [建议价 {price:.2f}]"
                })
                enrich_decision_item(sig, write_journal=True)
                continue

            # B. CONFIRM (弹窗确认模式)
            elif mode == "CONFIRM":
                if not hasattr(self, "_kernel_today_confirmed"):
                    self._kernel_today_confirmed = set()
                if not hasattr(self, "_kernel_today_ignored"):
                    self._kernel_today_ignored = set()

                if code in self._kernel_today_confirmed:
                    continue
                if code in self._kernel_today_ignored:
                    continue

                # 去重与状态匹配
                if action in ("BUY", "ADD") and code in positions:
                    blocked.append(f"{code}:ALREADY_POS")
                    blocked_codes.append(code)
                    records.append({
                        "code": code, "name": sig.get('name', ''), "action": action,
                        "status": "拦截", "detail": "已有持仓"
                    })
                    continue
                if action in ("SELL", "REDUCE") and code not in positions:
                    blocked.append(f"{code}:NO_POS")
                    blocked_codes.append(code)
                    records.append({
                        "code": code, "name": sig.get('name', ''), "action": action,
                        "status": "拦截", "detail": "无此持仓"
                    })
                    continue

                # 弹出精美人机核实确认弹窗，实现真正的所见即所得
                self._show_kernel_confirm_dialog(sig, action, price)
                executed.append(f"PEND_{action} {code}")
                executed_codes.append(code)
                records.append({
                    "code": code,
                    "name": sig.get('name', ''),
                    "action": action,
                    "status": "等待确认",
                    "detail": "已弹出核实确认弹窗..."
                })
                continue

            # C. PAPER (模拟成交模式) / LIVE_AUTO (自动交易)
            is_live = (mode == "LIVE_AUTO" and is_active_trading)

            if action in ("BUY", "ADD"):
                if code in positions:
                    blocked.append(f"{code}:ALREADY_POS")
                    blocked_codes.append(code)
                    records.append({
                        "code": code, "name": sig.get('name', ''), "action": action,
                        "status": "拦截", "detail": "已有持仓"
                    })
                    continue

                if is_live:
                    if code in self._kernel_today_buys:
                        blocked.append(f"{code}:TODAY_BOUGHT")
                        blocked_codes.append(code)
                        records.append({
                            "code": code, "name": sig.get('name', ''), "action": action,
                            "status": "拦截", "detail": "今日已买入过"
                        })
                        continue

                    ok, msg = self._trade_gw.submit_buy(
                        code=code,
                        name=sig.get('name', ''),
                        sector=sig.get('sector', ''),
                        price=price,
                        strategy_tag=f"Live:{sig.get('signal_type', '')}",
                        reason=sig.get('reason', ''),
                    )
                    if ok:
                        self._kernel_today_buys.add(code)
                        executed.append(f"LIVE_{action} {code}")
                        executed_codes.append(code)
                        self._focus_ctrl.decision_queue.update_status(code, "已提交")
                        positions[code] = {"code": code}
                        records.append({
                            "code": code, "name": sig.get('name', ''), "action": action,
                            "status": "自动已执行(买)", "detail": msg
                        })
                        sig["kernel_order_id"] = msg
                        enrich_decision_item(sig, write_journal=True)
                    else:
                        blocked.append(f"{code}:{msg}")
                        blocked_codes.append(code)
                        records.append({
                            "code": code, "name": sig.get('name', ''), "action": action,
                            "status": "拒绝", "detail": msg
                        })
                        enrich_decision_item(sig, write_journal=True)
                else:
                    if code in self._kernel_today_mocks:
                        continue
                    self._kernel_today_mocks.add(code)
                    
                    # 提交到模拟网关以同步更新持仓和流水，真正做到“模拟成交，写持仓和盈亏”
                    ok, msg = self._trade_gw.submit_buy(
                        code=code,
                        name=sig.get('name', ''),
                        sector=sig.get('sector', ''),
                        price=price,
                        strategy_tag=f"Mock:{sig.get('signal_type', '')}",
                        reason=sig.get('reason', ''),
                    )
                    
                    executed.append(f"MOCK_{action} {code}")
                    executed_codes.append(code)
                    self._focus_ctrl.decision_queue.update_status(code, "已提交")
                    records.append({
                        "code": code, "name": sig.get('name', ''), "action": action,
                        "status": "模拟已提交", "detail": "PAPER 模拟买入成功"
                    })
                    enrich_decision_item(sig, write_journal=True)

            elif action in ("SELL", "REDUCE"):
                if code not in positions:
                    blocked.append(f"{code}:NO_POS")
                    blocked_codes.append(code)
                    records.append({
                        "code": code, "name": sig.get('name', ''), "action": action,
                        "status": "拦截", "detail": "当前无此持仓"
                    })
                    continue

                if is_live:
                    if code in self._kernel_today_sells:
                        blocked.append(f"{code}:TODAY_SOLD")
                        blocked_codes.append(code)
                        records.append({
                            "code": code, "name": sig.get('name', ''), "action": action,
                            "status": "拦截", "detail": "今日已卖出过"
                        })
                        continue

                    sell_price = float(price_map.get(code, price) or price)
                    ok, msg = self._trade_gw.submit_sell(
                        code=code,
                        price=sell_price,
                        reason=f"LiveSell conf={float(sig.get('kernel_confidence', 0) or 0):.2f}",
                    )
                    if ok:
                        self._kernel_today_sells.add(code)
                        executed.append(f"LIVE_{action} {code}")
                        executed_codes.append(code)
                        self._focus_ctrl.decision_queue.update_status(code, "已成交")
                        positions.pop(code, None)
                        records.append({
                            "code": code, "name": sig.get('name', ''), "action": action,
                            "status": "自动已执行(卖)", "detail": msg
                        })
                        sig["kernel_order_id"] = msg
                        enrich_decision_item(sig, write_journal=True)
                    else:
                        blocked.append(f"{code}:{msg}")
                        blocked_codes.append(code)
                        records.append({
                            "code": code, "name": sig.get('name', ''), "action": action,
                            "status": "拒绝", "detail": msg
                        })
                        enrich_decision_item(sig, write_journal=True)
                else:
                    if code in self._kernel_today_mocks:
                        continue
                    self._kernel_today_mocks.add(code)

                    sell_price = float(price_map.get(code, price) or price)
                    ok, msg = self._trade_gw.submit_sell(
                        code=code,
                        price=sell_price,
                        reason="MockSell",
                    )
                    
                    executed.append(f"MOCK_{action} {code}")
                    executed_codes.append(code)
                    self._focus_ctrl.decision_queue.update_status(code, "已成交")
                    records.append({
                        "code": code, "name": sig.get('name', ''), "action": action,
                        "status": "模拟已成交", "detail": "PAPER 模拟卖出成功"
                    })
                    enrich_decision_item(sig, write_journal=True)

    except Exception as e:
        errors.append(str(e))
        error_codes.extend(blocked_codes[-1:])
        records.append({
            "code": "ERROR",
            "name": "系统异常",
            "action": "EXEC",
            "status": "异常",
            "detail": str(e)
        })

    self._refresh_decision_tab()
    msg = f"执行={len(executed)} 拦截={len(blocked)} 错误={len(errors)}"
    kind = "ok" if executed else ("error" if errors else "warn")
    
    # 状态栏单行摘要化，不包含大文本 detail
    self._kernel_set_status(msg, kind)
    self._kernel_mark_signal_rows(executed_codes, blocked_codes, error_codes)
    
    # 将结构化记录传入强大的联动悬浮 Tree 窗口
    if not auto_mode or len(executed) > 0 or len(errors) > 0 or (hasattr(self, "_kernel_toast_win") and self._kernel_toast_win and self._kernel_toast_win.winfo_exists()):
        self._kernel_show_toast(msg, kind, records=records)


def _ignore_selected_signal(self):
    """忽略选中的决策信号"""
    sel = self._signal_tree.selection()
    if not sel or not self._focus_ctrl:
        return
    code = sel[0]
    self._focus_ctrl.decision_queue.update_status(code, "已忽略")
    self._refresh_decision_tab()


def _clear_done_signals(self):
    """清除已完结的信号"""
    if self._focus_ctrl:
        self._focus_ctrl.decision_queue.clear_non_pending()
    self._refresh_decision_tab()


def _sell_all_positions(self):
    """一键卖出全部持仓"""
    if not self._trade_gw:
        return
    positions = self._trade_gw.get_positions()
    if not positions:
        messagebox.showinfo("提示", "当前无持仓")
        return

    if not messagebox.askyesno("确认", f"确认模拟卖出全部 {len(positions)} 只持仓？"):
        return

    df_rt = None
    if self.selector and hasattr(self.selector, 'df_all_realtime'):
        df_rt = self.selector.df_all_realtime

    for p in positions:
        code = p['code']
        price = p['current_price']
        name_val = p.get('name', '一键清仓')
        if df_rt is not None and code in df_rt.index:
            rt_price = float(df_rt.loc[code].get('trade', 0) or 0)
            if rt_price > 0:
                price = rt_price
            name_val = df_rt.loc[code].get('name', name_val)
        
        ok = self._trade_gw.submit_sell(code, price, reason="一键清仓")
        if ok:
            # 构造虚拟 SELL 信号，物理写入交易流水，并同步让新交易内核 paper_adapter 执行平仓！
            sig_sell = {
                "code": code,
                "name": name_val,
                "signal_type": "一键清仓",
                "action": "SELL",
                "price": price,
                "current_price": price,
                "suggest_price": price,
                "reason": "一键清仓",
                "journal_ts": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
            }
            try:
                from trading_kernel.kernel_service import enrich_decision_item
                enrich_decision_item(sig_sell, write_journal=True)
            except Exception as e_journal:
                logger.warning(f"Error enriching sell journal in stock_selection_window: {e_journal}")

    self._refresh_decision_tab()
    messagebox.showinfo("完成", "已执行模拟卖出全部持仓")

def _on_signal_double_click(self, event):
    """双击决策信号联动或显示原因详情"""
    sel = self._signal_tree.selection()
    if not sel:
        return
    code = sel[0]
    
    # 检查是否双击了触发原因列
    col_id = self._signal_tree.identify_column(event.x)
    col_name = self._signal_tree.column(col_id, 'id')
    if col_name == 'reason':
        try:
            values = self._signal_tree.item(code, 'values')
            reason_text = values[15]
            messagebox.showinfo("触发原因详情", reason_text, parent=self)
        except Exception:
            pass
        return
        
    # 其他列双击执行模拟买入
    self._mock_buy_selected()

def _on_signal_selected(self, event=None):
    """单击信号队列联动主界面 K 线图"""
    sel = self._signal_tree.selection()
    if not sel:
        return
    code = sel[0]
    if hasattr(self, 'sender') and self.sender:
        try:
            self.sender.send(code)
        except Exception:
            pass
    if self.master and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
        if hasattr(self.master, 'open_visualizer'):
            self.master.open_visualizer(code)

def _sort_signal_tree(self, col: str):
    """决策信号列表点击表头排序"""
    try:
        items = [(self._signal_tree.set(k, col), k) for k in self._signal_tree.get_children('')]
        try:
            items.sort(key=lambda x: float(x[0].replace('%', '').replace('#', '').replace('+', '').replace('-', '') or 0), reverse=True)
        except Exception:
            items.sort(reverse=True)
        for idx, (_, k) in enumerate(items):
            self._signal_tree.move(k, '', idx)
        # [NEW] 排序后自动滚动到顶部
        self._signal_tree.yview_moveto(0)
    except Exception as e:
        logger.debug(f"_sort_signal_tree: {e}")


def show_decision_tab(self):
    """切换当前 Notebook 到 🎯 实时决策 选项卡"""
    try:
        if hasattr(self, '_notebook'):
            for tab_id in self._notebook.tabs():
                tab_text = self._notebook.tab(tab_id, "text")
                if "实时决策" in tab_text:
                    self._notebook.select(tab_id)
                    logger.info("📡 选股窗口已自动切换到 🎯 实时决策 选项卡")
                    break
    except Exception as e:
        logger.warning(f"切换到实时决策选项卡失败: {e}")


# 将新方法 monkey-patch 绑定到 StockSelectionWindow 类
StockSelectionWindow._init_sector_tab       = _init_sector_tab
StockSelectionWindow._init_decision_tab     = _init_decision_tab
StockSelectionWindow._schedule_focus_refresh = _schedule_focus_refresh
StockSelectionWindow._refresh_focus_tabs    = _refresh_focus_tabs
StockSelectionWindow._refresh_sector_tab    = _refresh_sector_tab
StockSelectionWindow._on_sector_selected    = _on_sector_selected
StockSelectionWindow._on_member_selected    = _on_member_selected
StockSelectionWindow._force_refresh_sector  = _force_refresh_sector
StockSelectionWindow._sort_sector_tree      = _sort_sector_tree
StockSelectionWindow._refresh_decision_tab  = _refresh_decision_tab
StockSelectionWindow._mock_buy_selected     = _mock_buy_selected
StockSelectionWindow._mock_sell_selected    = _mock_sell_selected
StockSelectionWindow._get_realtime_price_map = _get_realtime_price_map
StockSelectionWindow._kernel_refresh_positions = _kernel_refresh_positions
StockSelectionWindow._bg_sync_ui_from_kernel = _bg_sync_ui_from_kernel
StockSelectionWindow._kernel_auto_execute_once = _kernel_auto_execute_once
StockSelectionWindow._kernel_set_status = _kernel_set_status
StockSelectionWindow._kernel_mark_signal_rows = _kernel_mark_signal_rows
StockSelectionWindow._kernel_show_toast = _kernel_show_toast
StockSelectionWindow._schedule_kernel_blink = _schedule_kernel_blink
StockSelectionWindow._ignore_selected_signal = _ignore_selected_signal
StockSelectionWindow._clear_done_signals    = _clear_done_signals
StockSelectionWindow._sell_all_positions    = _sell_all_positions
StockSelectionWindow._on_signal_double_click = _on_signal_double_click
StockSelectionWindow._on_signal_selected     = _on_signal_selected
StockSelectionWindow._sort_signal_tree       = _sort_signal_tree
def _on_one_key_self_heal(self):
    """一键自适应数据自愈修复：智能调整资金规模、修复个股缺失价格、清理 0 股幽灵持仓、并物理同步适配器与柜台数据"""
    try:
        from trading_kernel.kernel_service import get_kernel_service
        from trade_gateway import get_trade_gateway
        import numpy as np
        import math
        
        def safe_float(v, fallback=0.0):
            if v is None:
                return fallback
            try:
                if isinstance(v, (np.floating, np.integer)):
                    return float(v)
            except Exception:
                pass
            try:
                return float(v)
            except (ValueError, TypeError):
                return fallback
        
        service = get_kernel_service()
        if not service or not service.paper_adapter:
            messagebox.showwarning("数据自愈", "模拟交易内核服务未就绪")
            return
            
        trade_gw = getattr(self, "_trade_gw", None) or get_trade_gateway()
        if not trade_gw:
            messagebox.showwarning("数据自愈", "模拟交易网关未就绪")
            return
            
        # 1. 物理清理所有 volume/shares <= 0 的幽灵/已平仓持仓，防范 float 盈亏计算干扰
        removed_ghosts = []
        
        # 清理 paper_adapter 内存持仓
        for c_code, p_obj in list(service.paper_adapter.account.positions.items()):
            if p_obj.volume <= 0:
                service.paper_adapter.account.positions.pop(c_code, None)
                removed_ghosts.append(c_code)
                
        # 清理 legacy 柜台持仓
        with trade_gw._lock:
            for c_code in list(trade_gw._positions.keys()):
                leg_pos = trade_gw._positions[c_code]
                if leg_pos.shares <= 0:
                    trade_gw._positions.pop(c_code, None)
                    removed_ghosts.append(c_code)
        
        # 1.1 价格自愈：物理修复价格数据 (entry_price / current_price) 缺失、0 或为 NaN 的情况
        def is_invalid_price(p):
            if p is None:
                return True
            try:
                fp = float(p)
                return fp <= 0 or math.isnan(fp) or math.isinf(fp)
            except Exception:
                return True
        
        df_all = getattr(self, "df_all", None)
        rt_price_map = {}
        if df_all is not None:
            try:
                for idx, row in df_all.iterrows():
                    raw_c = str(idx)
                    pure_c = "".join(filter(str.isdigit, raw_c))[:6]
                    if pure_c:
                        price_val = safe_float(row.get("close") or row.get("price") or row.get("last_close") or row.get("open"), 0.0)
                        if price_val > 0:
                            rt_price_map[pure_c] = price_val
            except Exception as ex:
                logger.error(f"Error mapping rt_price_map: {ex}")
        
        # 从 orders 流水中回溯计算所有个股的买入均价
        order_entry_prices = {}
        if service.paper_adapter.orders:
            try:
                sorted_orders = sorted(
                    [o for o in service.paper_adapter.orders if isinstance(o, dict)],
                    key=lambda x: str(x.get("timestamp") or "")
                )
                temp_volumes = {}
                temp_costs = {}
                for o in sorted_orders:
                    c = o.get("code")
                    if not c:
                        continue
                    pure_c = "".join(filter(str.isdigit, str(c)))[:6]
                    act = str(o.get("action") or "").upper()
                    p = safe_float(o.get("price"), 0.0)
                    vol = safe_float(o.get("volume"), 0.0)
                    if p <= 0 or vol <= 0:
                        continue
                    if act in {"BUY", "ADD"}:
                        temp_volumes[pure_c] = temp_volumes.get(pure_c, 0.0) + vol
                        temp_costs[pure_c] = temp_costs.get(pure_c, 0.0) + (p * vol)
                    elif act in {"SELL", "REDUCE"}:
                        rem_vol = max(0.0, temp_volumes.get(pure_c, 0.0) - vol)
                        if rem_vol <= 0:
                            temp_volumes.pop(pure_c, None)
                            temp_costs.pop(pure_c, None)
                        else:
                            ratio = rem_vol / temp_volumes[pure_c]
                            temp_costs[pure_c] = temp_costs.get(pure_c, 0.0) * ratio
                            temp_volumes[pure_c] = rem_vol
                
                for pure_c, tot_vol in temp_volumes.items():
                    if tot_vol > 0:
                        avg_p = temp_costs.get(pure_c, 0.0) / tot_vol
                        if avg_p > 0:
                            order_entry_prices[pure_c] = avg_p
            except Exception as ex:
                logger.error(f"Error computing order_entry_prices: {ex}")

        # 遍历并自愈修复持仓的价格
        healed_prices_count = 0
        for c_code, pos_obj in list(service.paper_adapter.account.positions.items()):
            pure_c = "".join(filter(str.isdigit, str(c_code)))[:6]
            
            # 修复 current_price
            rt_p = rt_price_map.get(pure_c, 0.0)
            if is_invalid_price(pos_obj.current_price):
                if rt_p > 0:
                    pos_obj.current_price = rt_p
                    healed_prices_count += 1
                    logger.info(f"[Self-Healing] Repaired current_price for {c_code} with real-time price: {rt_p}")
                elif not is_invalid_price(pos_obj.entry_price):
                    pos_obj.current_price = pos_obj.entry_price
                    healed_prices_count += 1
                    logger.info(f"[Self-Healing] Repaired current_price for {c_code} fallback to entry_price: {pos_obj.entry_price}")
            
            # 修复 entry_price
            if is_invalid_price(pos_obj.entry_price):
                if pure_c in order_entry_prices:
                    pos_obj.entry_price = order_entry_prices[pure_c]
                    healed_prices_count += 1
                    logger.info(f"[Self-Healing] Repaired entry_price for {c_code} from order ledger: {pos_obj.entry_price}")
                elif rt_p > 0:
                    pos_obj.entry_price = rt_p
                    healed_prices_count += 1
                    logger.info(f"[Self-Healing] Repaired entry_price for {c_code} with real-time price fallback: {rt_p}")
                elif not is_invalid_price(pos_obj.current_price):
                    pos_obj.entry_price = pos_obj.current_price
                    healed_prices_count += 1
                    logger.info(f"[Self-Healing] Repaired entry_price for {c_code} with current_price fallback: {pos_obj.current_price}")

        # 同时自愈老版柜台的持仓价格与同步
        with trade_gw._lock:
            for c_code in list(trade_gw._positions.keys()):
                leg_pos = trade_gw._positions[c_code]
                leg_pure = "".join(filter(str.isdigit, str(c_code)))[:6]
                
                # 价格与成本同步
                paper_pos = service.paper_adapter.account.positions.get(leg_pure)
                if paper_pos:
                    leg_pos.price = paper_pos.entry_price
                    leg_pos.current_price = paper_pos.current_price

        # 2. 统计当前活跃持仓的买入成本和最新市值
        active_positions = service.paper_adapter.account.positions
        entry_cost_sum = 0.0
        market_val_sum = 0.0
        
        for code_key, pos_obj in active_positions.items():
            vol = float(pos_obj.volume)
            entry_cost_sum += float(pos_obj.entry_price) * vol
            market_val_sum += float(pos_obj.current_price) * vol
            
        # 3. 智能计算合理、健康的资金规模 (尊重现有总资产，保持一致性)
        current_initial = float(getattr(service.paper_adapter, "initial_capital", 0.0) or 0.0)
        if current_initial >= entry_cost_sum and current_initial > 0:
            target_cap = current_initial
            logger.info(f"[Self-Healing] Respecting current initial capital: {target_cap}")
        else:
            # 只有原资金无效或不足以覆盖持仓时，才自愈重调资金规模 (默认至少 1,000,000.0)
            min_cap = max(1000000.0, entry_cost_sum * 1.5)
            target_cap = float((int(min_cap) // 100000) * 100000)
            if target_cap < min_cap:
                target_cap += 100000.0
            logger.info(f"[Self-Healing] Auto-expanded initial capital to: {target_cap} (cost: {entry_cost_sum})")
            
        new_cash = max(0.0, target_cap - entry_cost_sum)
        
        # 4. 同步可用现金与初始资金到纸盘适配器和老柜台风控
        service.paper_adapter.initial_capital = target_cap
        service.paper_adapter.account.initial_capital = target_cap
        service.paper_adapter.account.cash = new_cash
        
        trade_gw.total_capital = target_cap
        if hasattr(trade_gw, "risk_manager") and trade_gw.risk_manager:
            trade_gw.risk_manager.total_capital = target_cap
            
        # 5. 强行将新数据做物理落盘持久化
        if hasattr(service.paper_adapter, "_save_state"):
            service.paper_adapter._save_state()
            
        # 6. 重新刷新持仓与数据展示
        self._kernel_refresh_positions(show_message=False)
        
        # 7. 显示成功对话框
        pnl_val = market_val_sum - entry_cost_sum
        pnl_pct = (pnl_val / entry_cost_sum * 100.0) if entry_cost_sum > 0 else 0.0
        
        msg_text = (
            f"🎉 一键账户资产与资金自愈成功！\n\n"
            f"1️⃣ 清理幽灵持仓：已物理剥离 {len(set(removed_ghosts))} 只已平仓 (0股) 行。\n"
            f"2️⃣ 自愈价格数据：修复补齐了 {healed_prices_count} 处无效/缺失的价格指标。\n"
            f"3️⃣ 对齐初始资金：已完美尊重并对齐初始资产为 ¥ {target_cap:,.2f} (与总资金量一致)。\n"
            f"4️⃣ 可用现金对账：已精准修正为 ¥ {new_cash:,.2f} (账户保持健康购买力)。\n"
            f"5️⃣ 资产盈亏重算：\n"
            f"   - 持仓总成本：¥ {entry_cost_sum:,.2f}\n"
            f"   - 持仓最新市值：¥ {market_val_sum:,.2f}\n"
            f"   - 浮动总盈亏：¥ {pnl_val:+,.2f} ({pnl_pct:+.2f}%)\n\n"
            f"* 修正后数据已安全持久化写入本地配置文件，在重新启动后依然保持完美对账自愈！"
        )
        messagebox.showinfo("数据自愈成功", msg_text, parent=self)
    except Exception as e:
        logger.error(f"Error in _on_one_key_self_heal: {e}")
        messagebox.showerror("自愈失败", f"执行自愈时发生异常: {e}", parent=self)


StockSelectionWindow.show_decision_tab       = show_decision_tab
StockSelectionWindow._on_one_key_self_heal   = _on_one_key_self_heal

class BacktestReportDialog(tk.Toplevel, WindowMixin):
    """Re-entry 历史回测报告详情弹窗，利用 WindowMixin 实现窗口位置和大小的跨会话持久化"""
    def __init__(self, parent, code: str, name: str, report: str):
        super().__init__(parent)
        self.parent_win = parent
        self.code = code
        self.name = name
        self.report = report
        self.scale_factor = getattr(parent, 'scale_factor', 1.0)
        
        self.title(f"🔍 Re-entry 历史回测报告 - {name} ({code})")
        self.configure(bg="#0c101b")
        
        # 加载窗口大小与位置（持久化）
        self.load_window_position(self, "Reentry回测报告详情", default_width=780, default_height=580)
        
        self._init_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda event: self._on_close())

    def _init_ui(self):
        # 顶部 Frame
        self.top_frame = tk.Frame(self, bg="#111726", pady=8)
        self.top_frame.pack(fill="x")
        
        self.title_label = tk.Label(
            self.top_frame, text=f"📊 【Re-entry 历史回测整体报告】 - {self.name} ({self.code})",
            bg="#111726", fg="#66ffcc", font=("Arial", 12, "bold")
        )
        self.title_label.pack(side="left", padx=15)
        
        tk.Button(
            self.top_frame, text="✕ 关闭", bg="#3a1a1a", fg="#ff5555",
            font=("Arial", 9, "bold"), relief="flat", padx=10,
            command=self._on_close
        ).pack(side="right", padx=15)
        
        text_frame = tk.Frame(self, bg="#0c101b")
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 极窄滚动条配置（使用标准 tk.Scrollbar 规避不同平台下 ttk 样式加载 Layout 缺失的问题）
        scrollbar = tk.Scrollbar(
            text_frame, 
            width=8, 
            borderwidth=0, 
            highlightthickness=0, 
            bg="#222b45", 
            activebackground="#333f63", 
            troughcolor="#0c101b", 
            elementborderwidth=0
        )
        scrollbar.pack(side="right", fill="y")
        
        self.text_area = tk.Text(
            text_frame, bg="#0c1220", fg="#eeeeee", insertbackground="white",
            selectbackground="#005BB7", selectforeground="white",
            font=("Consolas", 10), yscrollcommand=scrollbar.set, wrap="word", bd=0
        )
        self.text_area.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text_area.yview)
        
        self.text_area.insert("1.0", self.report)
        self.text_area.config(state="disabled")
        
        self.text_area.tag_configure("highlight_buy", foreground="#66ffcc", font=("Consolas", 10, "bold"))
        self.text_area.tag_configure("highlight_tp", foreground="#ffb833", font=("Consolas", 10, "bold"))
        self.text_area.tag_configure("highlight_sell", foreground="#ff7777", font=("Consolas", 10, "bold"))
        self.text_area.tag_configure("highlight_reentry", foreground="#55ffff", font=("Consolas", 10, "bold"))
        
        # 👑 [NEW] 新增用于突出最新买卖点以及当前策略分支的高对比度 UI Tag 配置
        self.text_area.tag_configure("highlight_latest_red", foreground="#ff3333", font=("Consolas", 10, "bold"))
        self.text_area.tag_configure("highlight_latest_green", foreground="#00ff66", font=("Consolas", 10, "bold"))
        self.text_area.tag_configure("highlight_strategy_title", foreground="#33ccff", font=("Consolas", 11, "bold"))
        self.text_area.tag_configure("highlight_status_holding", foreground="#ffcc00", font=("Consolas", 10, "bold"))
        self.text_area.tag_configure("highlight_status_observing", foreground="#a8a8a8", font=("Consolas", 10, "bold"))
        
        self._apply_highlights()
        
        # 👑 [NEW] 初始化完成后自动将文本滚动到最底部，便于第一时间查看最新的交易决策与策略总结，并双重延时强力激活焦点
        def focus_and_scroll():
            if self.winfo_exists():
                self.text_area.yview_moveto(1.0)
                self.lift()
                self.focus_force()
                if hasattr(self, 'text_area'):
                    self.text_area.focus_set()
        self.text_area.after(100, focus_and_scroll)
        self.text_area.after(300, focus_and_scroll)

    def _apply_highlights(self):
        def highlight_pattern(pattern, tag):
            start = "1.0"
            while True:
                pos = self.text_area.search(pattern, start, stopindex="end")
                if not pos:
                    break
                line, char = pos.split('.')
                end_pos = f"{line}.{int(char) + len(pattern)}"
                self.text_area.tag_add(tag, pos, end_pos)
                start = end_pos
                
        # 👑 [NEW] 实现一整行的高亮，增强视觉定位效果
        def highlight_line_pattern(pattern, tag):
            start = "1.0"
            while True:
                pos = self.text_area.search(pattern, start, stopindex="end")
                if not pos:
                    break
                line, char = pos.split('.')
                line_start = f"{line}.0"
                line_end = f"{line}.end"
                self.text_area.tag_add(tag, line_start, line_end)
                start = f"{line}.end + 1c"
        
        self.text_area.config(state="normal")
        highlight_pattern("BUY", "highlight_buy")
        highlight_pattern("建仓：", "highlight_buy")
        highlight_pattern("回补：", "highlight_buy")
        highlight_pattern("[ADD-BACK]", "highlight_buy")
        highlight_pattern("SELL", "highlight_sell")
        highlight_pattern("减仓：", "highlight_tp")
        highlight_pattern("[TAKE-PROFIT EVENT]", "highlight_tp")
        highlight_pattern("二次大止盈：", "highlight_tp")
        highlight_pattern("清仓平仓：", "highlight_sell")
        highlight_pattern("止损平仓：", "highlight_sell")
        highlight_pattern("Re-entry", "highlight_reentry")
        
        # 👑 应用最新买卖动作与策略分支高对比度渲染
        highlight_line_pattern("🔴【最新买卖点决策】", "highlight_latest_red")
        highlight_line_pattern("🟢【最新买卖点决策】", "highlight_latest_green")
        highlight_line_pattern("👑 【当前战术状态与活跃分支策略】", "highlight_strategy_title")
        highlight_pattern("💼 正在持仓中 (筹码做T滚动持股中)", "highlight_status_holding")
        highlight_pattern("📊 保持空仓观察 (KEEP OBSERVING)", "highlight_status_observing")
        
        self.text_area.config(state="disabled")

    def update_report(self, code: str, name: str, report: str):
        """[新增] 支持动态刷新内容，避免重复创建多个 TopLevel 窗口"""
        self.code = code
        self.name = name
        self.report = report
        
        self.title(f"🔍 Re-entry 历史回测报告 - {name} ({code})")
        self.title_label.config(text=f"📊 【Re-entry 历史回测整体报告】 - {name} ({code})")
        
        self.text_area.config(state="normal")
        self.text_area.delete("1.0", "end")
        self.text_area.insert("1.0", report)
        self.text_area.config(state="disabled")
        
        self._apply_highlights()
        
        # 👑 [NEW] 更新报告后自动滚动到最底部，便于第一时间查看最新的交易决策与策略总结，并双重延时强力激活焦点
        def focus_and_scroll():
            if self.winfo_exists():
                self.text_area.yview_moveto(1.0)
                self.lift()
                self.focus_force()
                if hasattr(self, 'text_area'):
                    self.text_area.focus_set()
        self.text_area.after(100, focus_and_scroll)
        self.text_area.after(300, focus_and_scroll)

    def _on_close(self):
        # 关闭时保存窗口位置大小
        self.save_window_position(self, "Reentry回测报告详情")
        self.destroy()

def _on_run_reentry_backtest_menu(self, code: str):
    """[新增] 右键菜单触发 Re-entry 模拟交易回测，并使用精美独立弹窗非阻塞展示结论"""
    try:
        name = "未知股票"
        if self.selector and hasattr(self.selector, 'df_all_realtime') and self.selector.df_all_realtime is not None:
            rt_all = self.selector.df_all_realtime
            if code in rt_all.index:
                name = rt_all.loc[code].get('name', name)
        
        if name == "未知股票" and hasattr(self, 'df_full_candidates') and self.df_full_candidates is not None:
            sub_df = self.df_full_candidates[self.df_full_candidates['code'] == code]
            if not sub_df.empty:
                name = sub_df.iloc[0].get('name', name)

        import threading
        from scratch.test_reentry_backtest import run_backtest_and_get_report
        
        progress_win = tk.Toplevel(self)
        progress_win.title("📡 正在计算")
        progress_win.geometry("300x120")
        progress_win.configure(bg="#0c101b")
        progress_win.resizable(False, False)
        progress_win.attributes("-topmost", True)
        
        progress_win.update_idletasks()
        w = 300
        h = 120
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        progress_win.geometry(f"{w}x{h}+{x}+{y}")
        
        tk.Label(
            progress_win, 
            text=f"正在对 【{name} ({code})】\n进行 Re-entry 历史回测分析...",
            bg="#0c101b", fg="#55ffff", font=("Arial", 11, "bold"), pady=15
        ).pack()
        
        lbl_status = tk.Label(
            progress_win, text="请稍候，抓取通达信历史数据并计算特征...",
            bg="#0c101b", fg="#888888", font=("Arial", 9)
        )
        lbl_status.pack()

        def run_task():
            try:
                # 仅获取整体总结报告结果
                report = run_backtest_and_get_report(code, name, only_report=True)
                self.after(0, lambda: [progress_win.destroy(), self._show_backtest_report_window(code, name, report)])
            except Exception as ex:
                logger.error(f"Error running backtest: {ex}")
                self.after(0, lambda: [progress_win.destroy(), messagebox.showerror("计算失败", f"回测计算发生异常: {ex}")])
                
        threading.Thread(target=run_task, daemon=True).start()
        
    except Exception as e:
        logger.error(f"Error in _on_run_reentry_backtest_menu: {e}")

def _show_backtest_report_window(self, code: str, name: str, report: str):
    """[新增] 显示并复用精美的 Re-entry 模拟交易回测报告窗口"""
    try:
        if hasattr(self, '_backtest_dialog') and self._backtest_dialog and self._backtest_dialog.winfo_exists():
            self._backtest_dialog.update_report(code, name, report)
            self._backtest_dialog.deiconify()
            self._backtest_dialog.lift()
            self._backtest_dialog.focus_force()
            self._backtest_dialog.update_idletasks()
            
            # 双重保险延时焦点钉死，对抗 Windows 平台下主窗口后台回调抢焦
            if hasattr(self._backtest_dialog, 'text_area'):
                self._backtest_dialog.text_area.focus_set()
                self._backtest_dialog.after(100, lambda: [
                    self._backtest_dialog.lift() if self._backtest_dialog.winfo_exists() else None,
                    self._backtest_dialog.focus_force() if self._backtest_dialog.winfo_exists() else None,
                    self._backtest_dialog.text_area.focus_set() if (self._backtest_dialog.winfo_exists() and hasattr(self._backtest_dialog, 'text_area')) else None
                ])
        else:
            self._backtest_dialog = BacktestReportDialog(self, code, name, report)
            self._backtest_dialog.update_idletasks()
            self._backtest_dialog.lift()
            self._backtest_dialog.focus_force()
            
            # 初始化双重保险对焦
            if hasattr(self._backtest_dialog, 'text_area'):
                self._backtest_dialog.text_area.focus_set()
                self._backtest_dialog.after(100, lambda: [
                    self._backtest_dialog.lift() if self._backtest_dialog.winfo_exists() else None,
                    self._backtest_dialog.focus_force() if self._backtest_dialog.winfo_exists() else None,
                    self._backtest_dialog.text_area.focus_set() if (self._backtest_dialog.winfo_exists() and hasattr(self._backtest_dialog, 'text_area')) else None
                ])
    except Exception as e:
        logger.error(f"Error showing backtest report window: {e}")

StockSelectionWindow._on_run_reentry_backtest_menu = _on_run_reentry_backtest_menu
StockSelectionWindow._show_backtest_report_window  = _show_backtest_report_window


# ── 实时决策下半区持仓与流水表格个股联动方法 ───────────────────────────────────────────

def _on_pos_selected(self, event=None):
    """当前持仓行选中联动主图与 K 线可视化"""
    try:
        sel = self._pos_tree.selection()
        if not sel:
            return
        code = str(sel[0]).zfill(6)  # iid 就是个股代码本身
        if hasattr(self, 'sender') and self.sender:
            try:
                self.sender.send(code)
            except Exception:
                pass
        if getattr(self, 'master', None) and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
            if hasattr(self.master, 'open_visualizer'):
                self.master.open_visualizer(code)
    except Exception as e:
        logger.debug(f"[on_pos_selected] error: {e}")


def _on_log_selected(self, event=None):
    """今日流水行选中联动主图与 K 线可视化"""
    try:
        sel = self._log_tree.selection()
        if not sel:
            return
        item = self._log_tree.item(sel[0])
        vals = item.get('values', [])
        if len(vals) > 2:
            code = str(vals[2]).zfill(6)  # values[2] 是个股代码
            if hasattr(self, 'sender') and self.sender:
                try:
                    self.sender.send(code)
                except Exception:
                    pass
            if getattr(self, 'master', None) and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
                if hasattr(self.master, 'open_visualizer'):
                    self.master.open_visualizer(code)
    except Exception as e:
        logger.debug(f"[on_log_selected] error: {e}")


StockSelectionWindow._on_pos_selected       = _on_pos_selected
StockSelectionWindow._on_log_selected       = _on_log_selected


# ══════════════════════════════════════════════════════════════════════════════
# CONFIRM 确认模式下的人机核实极客美学弹窗
# ══════════════════════════════════════════════════════════════════════════════

def _show_kernel_confirm_dialog(self, sig, action, price):
    """
    弹出极具极客美感的一键交易确认对话框 (非阻塞)
    """
    code = str(sig.get('code', '')).zfill(6)
    name = sig.get('name', '')
    sector = sig.get('sector', '')
    signal_type = sig.get('signal_type', '')
    reason = sig.get('reason', '').replace('|', '\n').replace('；', '\n')
    size = f"{float(sig.get('kernel_size_pct', 0) or 0):.0%}"
    conf = f"{float(sig.get('kernel_confidence', 0) or 0):.2f}"
    
    # 检查是否已有该股票的弹窗，防止重复弹出
    if not hasattr(self, "_active_confirm_wins"):
        self._active_confirm_wins = {}
    if code in self._active_confirm_wins:
        try:
            self._active_confirm_wins[code].focus_force()
            return
        except Exception:
            pass
            
    # 播放系统铃声提示
    try:
        self.bell()
    except Exception:
        pass
        
    win = tk.Toplevel(self)
    self._active_confirm_wins[code] = win
    win.title(f"⚠️ 交易决策核实 - {name}({code})")
    win.geometry("450x380")
    win.configure(bg="#0c101b")
    win.resizable(False, False)
    win.attributes("-topmost", True)
    
    # 居中显示
    win.update_idletasks()
    x = self.winfo_rootx() + (self.winfo_width() - 450) // 2
    y = self.winfo_rooty() + (self.winfo_height() - 380) // 2
    win.geometry(f"450x380+{x}+{y}")
    
    # 头部警告条
    bg_head = "#1b3a24" if action in ("BUY", "ADD") else "#3a1b1b"
    fg_head = "#66ffcc" if action in ("BUY", "ADD") else "#ff7777"
    act_name = "买入入场" if action in ("BUY", "ADD") else "卖出离场"
    
    head_frame = tk.Frame(win, bg=bg_head, pady=8)
    head_frame.pack(fill="x")
    
    tk.Label(
        head_frame, text=f"🎯 DETECTOR TRIGGER: 建议 {act_name}", 
        bg=bg_head, fg=fg_head, font=("Arial", 11, "bold")
    ).pack()
    
    # 个股关键指标
    body_frame = tk.Frame(win, bg="#0c101b", padx=20, pady=15)
    body_frame.pack(fill="both", expand=True)
    
    # 大字标的与代码
    info_frame = tk.Frame(body_frame, bg="#0c101b")
    info_frame.pack(fill="x", pady=(0, 10))
    
    tk.Label(
        info_frame, text=f"{name}", bg="#0c101b", fg="#ffffff", 
        font=("Microsoft YaHei", 18, "bold")
    ).pack(side="left")
    
    tk.Label(
        info_frame, text=f"({code})", bg="#0c101b", fg="#88aaff", 
        font=("Consolas", 14, "bold")
    ).pack(side="left", padx=8, pady=(4, 0))
    
    tk.Label(
        info_frame, text=f"[{sector}]", bg="#0c101b", fg="#888888", 
        font=("Microsoft YaHei", 10)
    ).pack(side="right", pady=(8, 0))
    
    # 决策因子网格
    grid_frame = tk.Frame(body_frame, bg="#111726", bd=1, relief="solid", padx=10, pady=8)
    grid_frame.pack(fill="x", pady=5)
    
    factors = [
        ("建议价格", f"¥ {price:.2f}", "#ffffff"),
        ("信号形态", signal_type, "#ffcc66"),
        ("置信指数", conf, "#66ffcc"),
        ("建议仓位", size, "#ff7777"),
    ]
    for i, (k, v, color) in enumerate(factors):
        r, c = i // 2, i % 2
        f_sub = tk.Frame(grid_frame, bg="#111726")
        f_sub.grid(row=r, column=c, sticky="ew", padx=15, pady=4)
        tk.Label(f_sub, text=k, bg="#111726", fg="#888888", font=("Microsoft YaHei", 9)).pack(side="left")
        tk.Label(f_sub, text=v, bg="#111726", fg=color, font=("Consolas", 10, "bold")).pack(side="right")
        
    grid_frame.grid_columnconfigure(0, weight=1)
    grid_frame.grid_columnconfigure(1, weight=1)
    
    # 原因详情滚动展示
    reason_frame = tk.LabelFrame(
        body_frame, text="  🔎 触发归因原因分析  ", 
        bg="#0c101b", fg="#888888", font=("Microsoft YaHei", 9)
    )
    reason_frame.pack(fill="both", expand=True, pady=(5, 10))
    
    reason_text = tk.Text(
        reason_frame, bg="#0c101b", fg="#ff4444" if action in ("BUY", "ADD") else "#ff7777",
        font=("Consolas", 9), bd=0, highlightthickness=0, wrap="word", height=4
    )
    reason_text.pack(side="left", fill="both", expand=True, padx=5, pady=2)
    reason_text.insert("1.0", reason)
    reason_text.config(state="disabled")
    
    sb = ttk.Scrollbar(reason_frame, orient="vertical", command=reason_text.yview)
    reason_text.configure(yscroll=sb.set)
    sb.pack(side="right", fill="y")
    
    # 控制按钮区
    ctrl_frame = tk.Frame(body_frame, bg="#0c101b")
    ctrl_frame.pack(fill="x")
    
    def on_confirm():
        self._kernel_today_confirmed.add(code)
        ok, msg = False, ""
        if action in ("BUY", "ADD"):
            ok, msg = self._trade_gw.submit_buy(
                code=code,
                name=name,
                sector=sector,
                price=price,
                strategy_tag=f"Confirm:{signal_type}",
                reason=sig.get('reason', ''),
            )
        else:
            ok, msg = self._trade_gw.submit_sell(
                code=code,
                price=price,
                reason=f"Confirm:{signal_type}",
            )
            
        if ok:
            # 构造虚拟/实际 信号写入交易流水，并同步让新交易内核执行！
            sig_action = dict(sig) if isinstance(sig, dict) else {}
            sig_action.update({
                "code": code,
                "name": name,
                "signal_type": signal_type,
                "action": action,
                "price": price,
                "current_price": price,
                "suggest_price": price,
                "reason": sig.get('reason', f"Confirm:{signal_type}") if isinstance(sig, dict) else f"Confirm:{signal_type}",
                "journal_ts": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
            })
            try:
                from trading_kernel.kernel_service import enrich_decision_item
                enrich_decision_item(sig_action, write_journal=True)
            except Exception as e_journal:
                logger.warning(f"Error enriching journal in on_confirm: {e_journal}")

            if self._focus_ctrl:
                self._focus_ctrl.decision_queue.update_status(code, "已提交" if action in ("BUY", "ADD") else "已成交")
            self._kernel_mark_signal_rows(executed=[code])
            self._kernel_show_toast(
                f"Confirm 成功: {name}({code})", "ok", 
                records=[{"code": code, "name": name, "action": action, "status": "已执行", "detail": msg}]
            )
        else:
            self._kernel_mark_signal_rows(errors=[code])
            self._kernel_show_toast(
                f"Confirm 拒绝: {name}({code})", "error", 
                records=[{"code": code, "name": name, "action": action, "status": "拒绝", "detail": msg}]
            )
            
        self._refresh_decision_tab()
        self._active_confirm_wins.pop(code, None)
        win.destroy()
        
    def on_ignore():
        self._kernel_today_ignored.add(code)
        if self._focus_ctrl:
            self._focus_ctrl.decision_queue.update_status(code, "已忽略")
        self._kernel_mark_signal_rows(blocked=[code])
        self._refresh_decision_tab()
        self._kernel_show_toast(
            f"Confirm 忽略: {name}({code})", "warn", 
            records=[{"code": code, "name": name, "action": action, "status": "忽略", "detail": "人工一键拦截"}]
        )
        self._active_confirm_wins.pop(code, None)
        win.destroy()
        
    def on_close():
        self._active_confirm_wins.pop(code, None)
        win.destroy()
        
    win.protocol("WM_DELETE_WINDOW", on_close)
    
    # 扁平化极客按钮
    btn_yes = tk.Button(
        ctrl_frame, text="✔ 确认执行 (Enter)", bg="#005a36", fg="#66ffcc",
        activebackground="#007e4b", activeforeground="#ffffff",
        font=("Microsoft YaHei", 10, "bold"), relief="flat", padx=15, pady=4,
        command=on_confirm
    )
    btn_yes.pack(side="left", expand=True, fill="x", padx=(0, 10))
    
    btn_no = tk.Button(
        ctrl_frame, text="✖ 放弃拦截 (Esc)", bg="#3a1a1a", fg="#ff7777",
        activebackground="#5a2222", activeforeground="#ffffff",
        font=("Microsoft YaHei", 10, "bold"), relief="flat", padx=15, pady=4,
        command=on_ignore
    )
    btn_no.pack(side="right", expand=True, fill="x", padx=(10, 0))
    
    # 快捷键绑定
    win.bind("<Return>", lambda e: on_confirm())
    win.bind("<Escape>", lambda e: on_ignore())
    
    # 联动 K 线与可视化
    if hasattr(self, 'sender') and self.sender:
        try:
            self.sender.send(code)
        except Exception:
            pass
    if getattr(self, 'master', None) and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
        if hasattr(self.master, 'open_visualizer'):
            self.master.open_visualizer(code)


StockSelectionWindow._show_kernel_confirm_dialog = _show_kernel_confirm_dialog


# ══════════════════════════════════════════════════════════════════════════════
# 📋 每日操作指南 (Daily Operating Guidance) - TK 统一视图实现与联动
# ══════════════════════════════════════════════════════════════════════════════

def _init_guidance_tab(self, parent: tk.Frame):
    """
    每日操作指南与挂单价格直接查阅 Tab
    """
    parent.config(bg="#0c101b")
    
    # 顶部控制面板（手动触发重算与刷新按钮）
    ctrl_bar = tk.Frame(parent, bg="#0c101b", pady=5)
    ctrl_bar.pack(fill="x")
    
    self._guidance_status_lbl = tk.Label(
        ctrl_bar, text="📋 每日盘前诊断建议与挂单执行参考价格表",
        bg="#0c101b", fg="#55ffff", font=("Arial", 10, "bold")
    )
    self._guidance_status_lbl.pack(side="left", padx=10)
    
    # 状态提示
    self._guidance_tips_lbl = tk.Label(
        ctrl_bar, text="",
        bg="#0c101b", fg="#888888", font=("Arial", 9)
    )
    self._guidance_tips_lbl.pack(side="left", padx=15)

    btn_frame = tk.Frame(ctrl_bar, bg="#0c101b")
    btn_frame.pack(side="right", padx=10)
    
    # 手动触发重算诊断按钮
    def on_manual_recalc():
        self._guidance_tips_lbl.config(text="⚡ 正在后台重算每日诊断，请稍候...", fg="#ffcc66")
        recalc_btn.config(state="disabled")
        
        def _bg_calc():
            try:
                from premarket_analyzer import run_premarket_diagnose
                run_premarket_diagnose()
                logger.info("📡 [TK] Premarket diagnose manually calculated successfully.")
                self.after(0, lambda: [
                    self._refresh_guidance_tab(),
                    self._guidance_tips_lbl.config(text="✅ 重算并落盘成功！数据已实时更新。", fg="#66ffcc"),
                    recalc_btn.config(state="normal")
                ])
            except Exception as ex:
                logger.error(f"[TK] Premarket diagnose recalc failed: {ex}")
                self.after(0, lambda: [
                    self._guidance_tips_lbl.config(text=f"❌ 计算失败: {ex}", fg="#ff7777"),
                    recalc_btn.config(state="normal")
                ])
                
        import threading
        threading.Thread(target=_bg_calc, daemon=True).start()
        
    recalc_btn = tk.Button(
        btn_frame, text="⚡ 盘前重算", bg="#1a3c40", fg="#66ffcc",
        font=("Arial", 9, "bold"), relief="flat", padx=8, pady=2,
        command=on_manual_recalc
    )
    recalc_btn.pack(side="left", padx=5)
    
    tk.Button(
        btn_frame, text="🔄 刷新表格", bg="#111726", fg="#ffffff",
        font=("Arial", 9), relief="flat", padx=8, pady=2,
        command=self._refresh_guidance_tab
    ).pack(side="left", padx=5)

    # 表格区域
    tree_frame = tk.Frame(parent, bg="#0c101b")
    tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
    
    cols = ("code", "name", "percent", "dff", "sector", "action", "order_price", "support_price", "stop_price", "branch", "reason")
    self._guidance_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="Dark.Treeview")
    
    # Scrollbars
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._guidance_tree.yview, style="Small.Vertical.TScrollbar")
    hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._guidance_tree.xview, style="Small.Horizontal.TScrollbar")
    self._guidance_tree.configure(yscroll=vsb.set, xscroll=hsb.set)
    
    self._guidance_tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    
    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)
    
    headers = {
        "code": "代码", "name": "名称", "percent": "当日涨幅", "dff": "资金DFF", "sector": "核心板块", "action": "操作建议", 
        "order_price": "挂单参考", "support_price": "战术支撑", 
        "stop_price": "止损防守", "branch": "活跃分支", "reason": "决策理由"
    }
    
    for c, text in headers.items():
        self._guidance_tree.heading(c, text=text, command=lambda col_name=c: self._sort_guidance_tree(col_name))
        self._guidance_tree.column(c, anchor="center")
        
    self._guidance_tree.column("#0", width=0, minwidth=0, stretch=False)
    self._guidance_tree.column("code", width=70, stretch=False)
    self._guidance_tree.column("name", width=90, stretch=False)
    self._guidance_tree.column("percent", width=75, stretch=False)
    self._guidance_tree.column("dff", width=75, stretch=False)
    self._guidance_tree.column("sector", width=105, stretch=False)
    self._guidance_tree.column("action", width=75, stretch=False)
    self._guidance_tree.column("order_price", width=75, stretch=False)
    self._guidance_tree.column("support_price", width=75, stretch=False)
    self._guidance_tree.column("stop_price", width=75, stretch=False)
    self._guidance_tree.column("branch", width=120, stretch=False)
    self._guidance_tree.column("reason", width=250, stretch=True)
    
    # 颜色配置高亮 tag
    self._guidance_tree.tag_configure("buy", background="#3a1b1b", foreground="#ff6666")
    self._guidance_tree.tag_configure("add", background="#2a2a00", foreground="#ffff55")
    self._guidance_tree.tag_configure("tp", background="#1b3a24", foreground="#66ffcc")
    self._guidance_tree.tag_configure("stop", background="#3a1122", foreground="#ff55bb")
    self._guidance_tree.tag_configure("normal", background="#0c101b", foreground="#eeeeee")
    
    # 策略分支高保真高对比色调 tag (强视觉区分，彻底根治“破位高位防震”等无色调或黑白混杂痛点)
    self._guidance_tree.tag_configure("warning_red", background="#2b1414", foreground="#ff4444")      # 破位高位防震 -> 醒目高对比红
    self._guidance_tree.tag_configure("super_cyan", background="#0c222b", foreground="#00ffff")       # 5日线主升浪/极速支撑 -> 电竞极速青
    self._guidance_tree.tag_configure("trend_green", background="#0d2215", foreground="#00ff88")      # 10日线反转/趋势 -> 盎然反弹绿
    self._guidance_tree.tag_configure("pullback_yellow", background="#24220d", foreground="#ffd700")  # SWS盈利线低吸/防守支撑 -> 黄金沙漏黄
    self._guidance_tree.tag_configure("defense_blue", background="#161626", foreground="#d670ff")     # 60日线生死防守 -> 战术防守紫/蓝


    # 事件绑定 (单击联动主图，双击弹出决策窗口)
    def _on_guidance_selected(event=None):
        sel = self._guidance_tree.selection()
        if not sel: return
        code = sel[0]
        if hasattr(self, 'sender') and self.sender:
            try:
                self.sender.send(code)
            except Exception:
                pass
        if getattr(self, 'master', None) and getattr(self.master, "vis_var", None) and self.master.vis_var.get():
            if hasattr(self.master, 'open_visualizer'):
                self.master.open_visualizer(code)
                
    def _on_guidance_double_click(event=None):
        sel = self._guidance_tree.selection()
        if not sel: return
        code = sel[0]
        item = self._guidance_tree.item(code)
        vals = item.get("values", [])
        if len(vals) > 10:
            # 弹窗显示详细理由
            msg = (
                f"🏷 股票：{vals[1]} ({vals[0]})\n"
                f"📈 当日涨幅：{vals[2]} | 资金DFF：{vals[3]}\n"
                f"📊 核心板块：{vals[4]}\n"
                f"🎯 战术建议：{vals[5]}\n"
                f"💵 挂单执行价：¥ {vals[6]}\n"
                f"🧱 辅助支撑：¥ {vals[7]}\n"
                f"🛡 战术防守价：¥ {vals[8]}\n"
                f"👑 策略活跃分支：{vals[9]}\n\n"
                f"🔍 决策分析归因理由：\n{vals[10]}"
            )
            messagebox.showinfo("每日盘前操作指南详情", msg, parent=self)

    def _show_guidance_context_menu(event):
        item_id = self._guidance_tree.identify_row(event.y)
        if not item_id:
            return
        self._guidance_tree.selection_set(item_id)
        
        # 针对 Treeview 的专业右键菜单，带有背景色以符合系统暗色主调
        menu = tk.Menu(self._guidance_tree, tearoff=0, bg="#0c101b", fg="#ffffff", activebackground="#1e293b", activeforeground="#ffffff")
        
        def _delete_selected_guidance():
            code = item_id
            if not messagebox.askyesno("确认删除", f"是否确定从每日操作指南中删除股票 {code} 的记录？", parent=self):
                return
            import os
            import json
            try:
                from sys_utils import get_app_root
                base_dir = get_app_root()
            except Exception:
                base_dir = os.path.abspath(".")
            filepath = os.path.join(base_dir, "logs", "premarket_diagnose.json")
            if not os.path.exists(filepath):
                return
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    new_data = [d for d in data if d.get('code') != code]
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(new_data, f, ensure_ascii=False, indent=2)
                # 重新刷新当前视图
                self._refresh_guidance_tab()
                # 提示成功
                self._guidance_tips_lbl.config(text=f"🗑 已成功删除股票 {code} 的操作指南", fg="#ff55bb")
            except Exception as ex:
                messagebox.showerror("错误", f"删除失败: {ex}", parent=self)
                
        menu.add_command(label="🗑 删除此操作指南", command=_delete_selected_guidance)
        menu.post(event.x_root, event.y_root)

    self._guidance_tree.bind("<<TreeviewSelect>>", _on_guidance_selected)
    self._guidance_tree.bind("<Double-1>", _on_guidance_double_click)
    self._guidance_tree.bind("<Button-3>", _show_guidance_context_menu)
    
    # 👑 绑定鼠标释放事件，当用户手动调整完 Treeview 列宽后，配合30秒防抖延迟，瞬间且原子地保存列宽到持久化配置中，防范高频写盘！
    def _on_guidance_column_resize(event):
        try:
            # 如果已有延迟保存计时器，先取消它
            if hasattr(self, "_guidance_resize_timer") and self._guidance_resize_timer:
                self.after_cancel(self._guidance_resize_timer)
            
            # 定义延迟执行的实际保存函数
            def _delayed_save():
                try:
                    self._save_guidance_column_widths()
                except Exception:
                    pass
                self._guidance_resize_timer = None

            # 设定30秒（30000毫秒）防抖延迟保存
            self._guidance_resize_timer = self.after(30000, _delayed_save)
        except Exception:
            pass
    self._guidance_tree.bind("<ButtonRelease-1>", _on_guidance_column_resize)


def _refresh_guidance_tab(self):
    """
    从 logs/premarket_diagnose.json 载入数据并填充 每日操作指南 Treeview
    """
    if not hasattr(self, '_guidance_tree') or not self._guidance_tree.winfo_exists():
        return
        
    # 清空
    self._guidance_tree.delete(*self._guidance_tree.get_children())
    
    import os
    import json
    try:
        from sys_utils import get_app_root
        base_dir = get_app_root()
    except Exception:
        base_dir = os.path.abspath(".")
    filepath = os.path.join(base_dir, "logs", "premarket_diagnose.json")
    if not os.path.exists(filepath):
        self._guidance_tips_lbl.config(text="⚠️ 未找到盘前诊断文件，请点击盘前重算", fg="#ff7777")
        return
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            self._guidance_tips_lbl.config(text="❌ 数据格式错误", fg="#ff7777")
            return
            
        # 预先加载全量个股的代码->题材板块的映射关系，实现高精度的 O(1) 联查
        code_to_sector = {}
        # 预先加载全量个股的代码->名称的映射关系，实现高精度的 O(1) 真名自愈
        code_to_name = {}
        
        # 1. 优先从 selector 实时数据表加载
        if hasattr(self, 'selector') and self.selector is not None and hasattr(self.selector, 'df_all_realtime'):
            rt = self.selector.df_all_realtime
            if rt is not None and not rt.empty:
                if 'category' in rt.columns:
                    if rt.index.name == 'code':
                        code_to_sector.update(rt['category'].fillna('').astype(str).to_dict())
                    else:
                        for idx, row in rt.iterrows():
                            c = str(row.get('code', idx)).zfill(6)
                            code_to_sector[c] = str(row.get('category', ''))
                if 'name' in rt.columns:
                    if rt.index.name == 'code':
                        for k, v in rt['name'].fillna('').astype(str).to_dict().items():
                            c = str(k).zfill(6)
                            if v and not v.startswith("个股_") and not v.isdigit():
                                code_to_name[c] = v
                    else:
                        for idx, row in rt.iterrows():
                            c = str(row.get('code', idx)).zfill(6)
                            v = str(row.get('name', ''))
                            if v and not v.startswith("个股_") and not v.isdigit():
                                code_to_name[c] = v
                        
        # 2. 从 df_full_candidates 加载
        if hasattr(self, 'df_full_candidates') and self.df_full_candidates is not None and not self.df_full_candidates.empty:
            df_fc = self.df_full_candidates
            if 'category' in df_fc.columns:
                if df_fc.index.name == 'code':
                    code_to_sector.update(df_fc['category'].fillna('').astype(str).to_dict())
                else:
                    for idx, row in df_fc.iterrows():
                        c = str(row.get('code', idx)).zfill(6)
                        code_to_sector[c] = str(row.get('category', ''))
            if 'name' in df_fc.columns:
                if df_fc.index.name == 'code':
                    for k, v in df_fc['name'].fillna('').astype(str).to_dict().items():
                        c = str(k).zfill(6)
                        if v and not v.startswith("个股_") and not v.isdigit():
                            code_to_name[c] = v
                else:
                    for idx, row in df_fc.iterrows():
                        c = str(row.get('code', idx)).zfill(6)
                        v = str(row.get('name', ''))
                        if v and not v.startswith("个股_") and not v.isdigit():
                            code_to_name[c] = v
                        
        # 3. 从 df_candidates 加载
        if hasattr(self, 'df_candidates') and self.df_candidates is not None and not self.df_candidates.empty:
            df_c = self.df_candidates
            if 'category' in df_c.columns:
                if df_c.index.name == 'code':
                    code_to_sector.update(df_c['category'].fillna('').astype(str).to_dict())
                else:
                    for idx, row in df_c.iterrows():
                        c = str(row.get('code', idx)).zfill(6)
                        code_to_sector[c] = str(row.get('category', ''))
            if 'name' in df_c.columns:
                if df_c.index.name == 'code':
                    for k, v in df_c['name'].fillna('').astype(str).to_dict().items():
                        c = str(k).zfill(6)
                        if v and not v.startswith("个股_") and not v.isdigit():
                            code_to_name[c] = v
                else:
                    for idx, row in df_c.iterrows():
                        c = str(row.get('code', idx)).zfill(6)
                        v = str(row.get('name', ''))
                        if v and not v.startswith("个股_") and not v.isdigit():
                            code_to_name[c] = v
                        
        # 4. 从 master.df_all 加载
        if hasattr(self, 'master') and self.master is not None and hasattr(self.master, 'df_all'):
            m_all = self.master.df_all
            if m_all is not None and not m_all.empty:
                if 'category' in m_all.columns:
                    if m_all.index.name == 'code':
                        code_to_sector.update(m_all['category'].fillna('').astype(str).to_dict())
                    else:
                        for idx, row in m_all.iterrows():
                            c = str(row.get('code', idx)).zfill(6)
                            code_to_sector[c] = str(row.get('category', ''))
                if 'name' in m_all.columns:
                    if m_all.index.name == 'code':
                        for k, v in m_all['name'].fillna('').astype(str).to_dict().items():
                            c = str(k).zfill(6)
                            if v and not v.startswith("个股_") and not v.isdigit():
                                code_to_name[c] = v
                    else:
                        for idx, row in m_all.iterrows():
                            c = str(row.get('code', idx)).zfill(6)
                            v = str(row.get('name', ''))
                            if v and not v.startswith("个股_") and not v.isdigit():
                                code_to_name[c] = v
                        
        # 5. Fallback 降级从 top_all.h5 中检索
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            for path in [r'g:\top_all.h5', os.path.join(base_dir, 'top_all.h5'), os.path.join(get_app_root(), 'top_all.h5')]:
                if os.path.exists(path):
                    import pandas as pd
                    df_top = pd.read_hdf(path, 'top_all')
                    if not df_top.empty:
                        col_to_check = 'category' if 'category' in df_top.columns else ('industry' if 'industry' in df_top.columns else None)
                        if col_to_check:
                            if df_top.index.name == 'code':
                                for k, v in df_top[col_to_check].fillna('').astype(str).to_dict().items():
                                    kc = str(k).zfill(6)
                                    if kc not in code_to_sector or not code_to_sector[kc]:
                                        code_to_sector[kc] = v
                            else:
                                for idx, row in df_top.iterrows():
                                    c = str(row.get('code', idx)).zfill(6)
                                    if c not in code_to_sector or not code_to_sector[c]:
                                        code_to_sector[c] = str(row.get(col_to_check, ''))
                        if 'name' in df_top.columns:
                            if df_top.index.name == 'code':
                                for k, v in df_top['name'].fillna('').astype(str).to_dict().items():
                                    kc = str(k).zfill(6)
                                    v_str = str(v)
                                    if v_str and not v_str.startswith("个股_") and not v_str.isdigit():
                                        if kc not in code_to_name:
                                            code_to_name[kc] = v_str
                            else:
                                for idx, row in df_top.iterrows():
                                    c = str(row.get('code', idx)).zfill(6)
                                    v_str = str(row.get('name', ''))
                                    if v_str and not v_str.startswith("个股_") and not v_str.isdigit():
                                        if c not in code_to_name:
                                            code_to_name[c] = v_str
                    break
        except Exception:
            pass

        # 排序处理
        sort_col = getattr(self, '_guid_sort_col', "code")
        sort_desc = getattr(self, '_guid_sort_desc', False)
        
        # 实时更新表头排序三角指示器 (🔼 / 🔽)
        headers = {
            "code": "代码", "name": "名称", "percent": "当日涨幅", "dff": "资金DFF", "sector": "核心板块", "action": "操作建议", 
            "order_price": "挂单参考", "support_price": "战术支撑", 
            "stop_price": "止损防守", "branch": "活跃分支", "reason": "决策理由"
        }
        arrow = " 🔽" if sort_desc else " 🔼"
        for c, text in headers.items():
            header_text = text + arrow if c == sort_col else text
            self._guidance_tree.heading(c, text=header_text)
            
        # 👑 在排序之前，利用实时内存大表，富化并合入每只个股的当日涨幅 (percent) 和资金 dff，确保支持按新列高保真数值排序！
        for d in data:
            code = d.get('code') or ''
            code_clean = str(code).strip()
            for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠']:
                code_clean = code_clean.replace(icon, '').strip()
            code_clean = code_clean.zfill(6)
            
            pct = 0.0
            dff_val = 0.0
            has_rt = False
            if hasattr(self, 'selector') and self.selector is not None and hasattr(self.selector, 'df_all_realtime') and self.selector.df_all_realtime is not None:
                rt = self.selector.df_all_realtime
                if code_clean in rt.index:
                    row = rt.loc[code_clean]
                    pct = row.get('percent', row.get('pct', row.get('pct_diff', 0.0)))
                    dff_val = row.get('dff', 0.0)
                    has_rt = True
            if not has_rt and hasattr(self, 'master') and self.master is not None and hasattr(self.master, 'df_all') and self.master.df_all is not None:
                m_all = self.master.df_all
                if code_clean in m_all.index:
                    row = m_all.loc[code_clean]
                    pct = row.get('percent', row.get('pct', row.get('pct_diff', 0.0)))
                    dff_val = row.get('dff', 0.0)
                    has_rt = True
            if not has_rt:
                pct = d.get('percent', d.get('pct', d.get('pct_diff', 0.0)))
                dff_val = d.get('dff', 0.0)
                
            d['percent'] = float(pct or 0.0)
            d['dff'] = float(dff_val or 0.0)

        def _get_sort_key(d):
            if sort_col == "percent":
                return float(d.get('percent') or 0.0)
            if sort_col == "dff":
                return float(d.get('dff') or 0.0)
            if sort_col in ("order_price", "predicted_ma5"):
                return float(d.get('predicted_ma5') or d.get('order_price') or 0.0)
            if sort_col in ("support_price", "sws_support"):
                return float(d.get('sws_support') or d.get('support_price') or 0.0)
            if sort_col in ("stop_price", "hard_stop"):
                return float(d.get('hard_stop') or d.get('stop_price') or 0.0)
            if sort_col == "code":
                c_clean = str(d.get('code') or '').strip()
                for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠']:
                    c_clean = c_clean.replace(icon, '').strip()
                return c_clean.zfill(6)
            if sort_col == "name":
                code = d.get('code') or ''
                code_clean = str(code).strip()
                for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠']:
                    code_clean = code_clean.replace(icon, '').strip()
                code_clean = code_clean.zfill(6)
                
                name = d.get('name') or ''
                name_clean = str(name).strip()
                for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠']:
                    name_clean = name_clean.replace(icon, '').strip()
                    
                if not name_clean or name_clean.isdigit() or name_clean == code_clean or name_clean.startswith("个股_"):
                    healed_name = code_to_name.get(code_clean)
                    if healed_name:
                        return healed_name
                return name_clean
            if sort_col == "sector":
                c_clean = str(d.get('code') or '').strip()
                for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠']:
                    c_clean = c_clean.replace(icon, '').strip()
                c_clean = c_clean.zfill(6)
                return str(code_to_sector.get(c_clean, ''))
            if sort_col == "action":
                act = str(d.get('action_cn') or d.get('suggest_action') or '保持观察')
                priority_map = {
                    "买入建仓": 1,
                    "建仓": 1,
                    "做T回补": 2,
                    "回补": 2,
                    "分批大止盈": 3,
                    "大止盈": 3,
                    "止损": 4,
                    "保持观察": 5,
                    "观察": 5
                }
                return priority_map.get(act, 99)
            if sort_col == "branch":
                branch_name = str(d.get('branch_cn') or d.get('active_branch') or '')
                priority_map = {
                    "5日线主升浪": 1,
                    "5日线极速支撑": 1,
                    "10日线反转": 2,
                    "10日线趋势": 2,
                    "SWS盈利线低吸": 3,
                    "SWS防守支撑": 3,
                    "60日线生死防守": 4,
                    "破位高位防震": 5
                }
                return priority_map.get(branch_name, 99)
            
            # 兜底通用提取
            val = d.get(sort_col) or ''
            try:
                return float(val)
            except Exception:
                return str(val)
                
        data_sorted = sorted(data, key=_get_sort_key, reverse=sort_desc)
        
        any_healed = False
        for d in data_sorted:
            code = d.get('code') or ''
            name = d.get('name') or ''
            
            # Clean emojis from code for sector matching
            code_clean = str(code).strip()
            for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠']:
                code_clean = code_clean.replace(icon, '').strip()
            code_clean = code_clean.zfill(6)
            
            # Auto-heal stock names if they are empty, digit, or start with "个股_"
            name_clean = str(name).strip()
            for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠']:
                name_clean = name_clean.replace(icon, '').strip()
                
            if not name_clean or name_clean.isdigit() or name_clean == code_clean or name_clean.startswith("个股_"):
                healed_name = code_to_name.get(code_clean)
                if healed_name:
                    name = healed_name
                    d['name'] = healed_name
                    any_healed = True
            
            raw_sec = code_to_sector.get(code_clean, '')
            sector_str = self._get_short_category(raw_sec)
            
            action = d.get('action_cn') or d.get('suggest_action') or '保持观察'
            order_p = float(d.get('predicted_ma5') or d.get('order_price') or 0.0)
            supp_p = float(d.get('sws_support') or d.get('support_price') or 0.0)
            stop_p = float(d.get('hard_stop') or d.get('stop_price') or 0.0)
            branch_raw = d.get('branch_cn') or d.get('active_branch') or ''
            
            # Emojis 映射：彻底物理剥离 \uFE0F 并换成兼容的 🛡 和 🚨 消除 Windows 平台多余空格与空白
            branch_emoji_map = {
                "5日线主升浪": "🚀 5日线主升浪",
                "5日线极速支撑": "🚀 5日线极速支撑",
                "10日线反转": "🟢 10日线反转",
                "10日线趋势": "🟢 10日线趋势",
                "SWS盈利线低吸": "🟡 SWS盈利线低吸",
                "SWS防守支撑": "🟡 SWS防守支撑",
                "60日线生死防守": "🛡 60日线生死防守",
                "破位高位防震": "🚨 破位高位防震"
            }
            branch = branch_emoji_map.get(branch_raw, branch_raw)
            reason = d.get('reason') or ''
            
            # 格式化实时涨幅与 dff，加上正负方向指示器
            pct_val = d.get('percent', 0.0)
            dff_val = d.get('dff', 0.0)
            pct_str = f"{pct_val:+.2f}%" if pct_val != 0.0 else "0.00%"
            dff_str = f"{dff_val:+.2f}" if dff_val != 0.0 else "0.00"

            # 格式化价格
            order_p_str = f"{order_p:.2f}" if order_p > 0 else "--"
            supp_p_str = f"{supp_p:.2f}" if supp_p > 0 else "--"
            stop_p_str = f"{stop_p:.2f}" if stop_p > 0 else "--"
            
            # 策略分支高保真高对比配色优先 (彻底根治“破位高位防震没有用不同颜色区分出来”的痛点)
            tag = "normal"
            if "破位高位防震" in branch_raw:
                tag = "warning_red"
            elif "5日线" in branch_raw:
                tag = "super_cyan"
            elif "10日线" in branch_raw:
                tag = "trend_green"
            elif "SWS" in branch_raw:
                tag = "pullback_yellow"
            elif "60日线" in branch_raw:
                tag = "defense_blue"
            else:
                # 兜底根据 action 回退状态着色
                if action in ("买入", "建仓", "买入建仓"):
                    tag = "buy"
                elif action in ("补仓", "回补", "做T回补"):
                    tag = "add"
                elif action in ("大止盈", "分批大止盈", "减仓"):
                    tag = "tp"
                elif action in ("止损", "止损平仓", "清仓平仓"):
                    tag = "stop"
                
            self._guidance_tree.insert(
                "", "end", iid=code,
                values=(code, name, pct_str, dff_str, sector_str, action, order_p_str, supp_p_str, stop_p_str, branch, reason),
                tags=(tag,)
            )
            
        if any_healed:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                logger.info("✨ [GUIDANCE-HEAL] Successfully persisted healed stock names back to logs/premarket_diagnose.json")
            except Exception as write_err:
                logger.error(f"❌ [GUIDANCE-HEAL] Failed to write back healed names: {write_err}")
                
        self._guidance_tips_lbl.config(text=f"📊 已成功拉取并呈现 {len(data_sorted)} 条作战指导", fg="#888888")
        
        # 仅在打开/首次载入时执行一次自动恢复或自动测量，后续刷新时保持用户手动调整的列宽不被强行覆盖
        if not getattr(self, '_guidance_cols_initialized', False):
            self._guidance_cols_initialized = True
            has_custom = False
            try:
                scale = self._get_dpi_scale_factor()
                config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
                if os.path.exists(config_file_path):
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        cf_data = json.load(f)
                    if 'guidance_column_widths' in cf_data:
                        has_custom = True
            except Exception:
                pass
                
            if has_custom:
                self._restore_guidance_column_widths()
            else:
                self._auto_fit_guidance_columns()
    except Exception as e:
        logger.error(f"Error refreshing guidance tab in TK: {e}")
        self._guidance_tips_lbl.config(text=f"❌ 载入出错: {e}", fg="#ff7777")


def _sort_guidance_tree(self, col: str):
    """每日操作指南列表点击表头排序"""
    current_col = getattr(self, '_guid_sort_col', "code")
    current_desc = getattr(self, '_guid_sort_desc', False)
    
    if current_col == col:
        self._guid_sort_desc = not current_desc
    else:
        self._guid_sort_col = col
        self._guid_sort_desc = False
        
    self._refresh_guidance_tab()


def show_guidance_tab(self):
    """切换当前 Notebook 到 📋 每日操作指南 选项卡"""
    try:
        if hasattr(self, '_notebook'):
            for tab_id in self._notebook.tabs():
                tab_text = self._notebook.tab(tab_id, "text")
                if "每日操作指南" in tab_text:
                    self._notebook.select(tab_id)
                    logger.info("📡 选股窗口已自动切换到 📋 每日操作指南 选项卡")
                    break
    except Exception as e:
        logger.warning(f"切换到每日操作指南选项卡失败: {e}")


def _save_guidance_column_widths(self):
    """保存每日操作指南 Treeview 的列宽"""
    if not hasattr(self, "_guidance_tree") or not self._guidance_tree.winfo_exists():
        return
    try:
        scale = self._get_dpi_scale_factor()
        config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
        
        widths = {}
        # 👑 动态使用 self._guidance_tree["columns"] 遍历所有列，完美解决新列 percent 和 dff 被遗漏的问题！
        for col in self._guidance_tree["columns"]:
            try:
                widths[col] = int(self._guidance_tree.column(col, "width") / scale)
            except Exception:
                pass
        
        data = {}
        if os.path.exists(config_file_path):
            with open(config_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        
        data['guidance_column_widths'] = widths
        
        tmp_file = config_file_path + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_file, config_file_path)
        logger.debug(f"[guidance_column_widths] Saved: {widths}")
    except Exception as e:
        logger.error(f"[guidance_column_widths] Save failed: {e}")


def _restore_guidance_column_widths(self):
    """恢复每日操作指南 Treeview 的列宽"""
    if not hasattr(self, "_guidance_tree") or not self._guidance_tree.winfo_exists():
        return
    try:
        scale = self._get_dpi_scale_factor()
        config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
        
        if os.path.exists(config_file_path):
            with open(config_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            widths = data.get('guidance_column_widths', {})
            if widths:
                for col, w in widths.items():
                    try:
                        self._guidance_tree.column(col, width=int(w * scale))
                    except Exception:
                        pass
                logger.debug(f"[guidance_column_widths] Restored: {widths}")
    except Exception as e:
        logger.error(f"[guidance_column_widths] Restore failed: {e}")


def _auto_fit_guidance_columns(self):
    """
    根据操作指南实际内容自动调整列宽，防止文字剪切/重叠
    """
    if not hasattr(self, "_guidance_tree") or not self._guidance_tree.winfo_exists():
        return
    import tkinter.font as tkfont
    try:
        f = tkfont.Font(font='Arial 9')
    except Exception:
        f = tkfont.Font(font=self._guidance_tree.cget("font"))
        
    cols = self._guidance_tree["columns"]
    all_items = self._guidance_tree.get_children()
    scale = self._get_dpi_scale_factor()
    
    # 👑 引入精细的 max_w_map 限制最大列宽，从源头上彻底根治默认宽度太宽的痛点！
    max_w_map = {
        "code": 80,
        "name": 110,
        "percent": 85,
        "dff": 85,
        "action": 90,
        "order_price": 90,
        "support_price": 90,
        "stop_price": 90,
        "sector": 140,
        "branch": 160
    }
    
    for col in cols:
        header_text = self._guidance_tree.heading(col)["text"]
        max_w = f.measure(header_text) + int(25 * scale) # padding
        
        for item in all_items:
            cell_val = str(self._guidance_tree.set(item, col))
            if len(cell_val) > 100:
                max_w = max(max_w, int(350 * scale))
                continue
            max_w = max(max_w, f.measure(cell_val) + int(25 * scale))
        
        # 限制合理范围并应用
        if col == "reason":
            max_w = min(max_w, int(350 * scale))
        elif col in max_w_map:
            max_w = min(max_w, int(max_w_map[col] * scale))
        else:
            max_w = min(max_w, int(150 * scale))
        
        # 保证每列都有适当的预设最小宽度，防挤压
        min_w_map = {
            "code": 70,
            "name": 90,
            "percent": 75,
            "dff": 75,
            "sector": 105,
            "action": 75,
            "order_price": 75,
            "support_price": 75,
            "stop_price": 75,
            "branch": 120
        }
        if col in min_w_map:
            max_w = max(max_w, int(min_w_map[col] * scale))
            
        self._guidance_tree.column(col, width=max_w)


StockSelectionWindow._init_guidance_tab = _init_guidance_tab
StockSelectionWindow._refresh_guidance_tab = _refresh_guidance_tab
StockSelectionWindow._sort_guidance_tree = _sort_guidance_tree
StockSelectionWindow.show_guidance_tab = show_guidance_tab
StockSelectionWindow._save_guidance_column_widths = _save_guidance_column_widths
StockSelectionWindow._restore_guidance_column_widths = _restore_guidance_column_widths
StockSelectionWindow._auto_fit_guidance_columns = _auto_fit_guidance_columns


