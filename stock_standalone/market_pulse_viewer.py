# -*- coding:utf-8 -*-
"""
Market Pulse Viewer (UI)
The "Battle Dashboard" for T+1 Strategy execution.
Displays Daily Reports, Hot Sectors, and Actionable Stock Opportunities.
File: market_pulse_viewer.py
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import tkinter.font as tkfont
from datetime import datetime, timedelta
import logging
import json
import pyperclip
from stock_logic_utils import  toast_message
try:
    from tkcalendar import DateEntry
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False

from market_pulse_engine import DailyPulseEngine
from JohnsonUtil import commonTips as cct
from tk_gui_modules.window_mixin import WindowMixin

# Import font/DPI utilities if available from main app context, 
# otherwise use standard defaults.

class StockDetailPopup(tk.Toplevel, WindowMixin):
    """
    Comprehensive Stock Detail Popup with position persistence.
    """
    def __init__(self, master, code, name, pulse_viewer):
        super().__init__(master)
        self.code = code
        self.name = name
        self.pulse_viewer = pulse_viewer
        
        self.title(f"Stock Detail: {code} - {name}")
        # Default geometry
        self.geometry("600x500")
        
        # Load Position
        self.load_window_position(self, "StockDetailPopup", default_width=600, default_height=500)
        
        self._build_ui()
        
        # Bindings
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Escape>", lambda e: self.on_close())

    def _build_ui(self):
        txt = tk.Text(self, font=("Consolas", 10), padx=10, pady=10)
        txt.pack(fill="both", expand=True)
        
        # 1. Basic Info
        info = [f"【{self.code}】{self.name}"]
        
        # 2. Market Pulse Data (from current Treeview selection)
        item = self.pulse_viewer.tree.selection()
        if item:
            vals = self.pulse_viewer.tree.item(item, "values")
            headers = [self.pulse_viewer.tree.heading(c)['text'] for c in self.pulse_viewer.tree['columns']]
            info.append("\n[Dashboard Data]")
            for k, v in zip(headers, vals):
                info.append(f"{k}: {v}")
                
        # 3. Selector Data (Deep Analysis)
        if self.pulse_viewer.engine and self.pulse_viewer.engine.selector and hasattr(self.pulse_viewer.engine.selector, 'df_all_realtime'):
             df = self.pulse_viewer.engine.selector.df_all_realtime
             # Robust lookup
             rec = None
             if self.code in df.index: rec = df.loc[self.code]
             else:
                  norm_code = self.code.replace('sh','').replace('sz','').zfill(6)
                  if norm_code in df.index: rec = df.loc[norm_code]
                  
             if rec is not None:
                 info.append(f"\n[Deep Analysis - {self.pulse_viewer.engine.selector.resample}]")
                 # 55188 / Technicals
                 keys = ['Rank', 'topR', 'percent', 'trade', 'volume', 'amount', 'turnover', 
                         'ma5d', 'ma10d', 'ma20d', 'category', 'industry', 'concept', 'reason']
                 for k in keys:
                     val = rec.get(k, 'N/A')
                     info.append(f"{k}: {val}")
                     
                 # 55188 Specifics if available
                 if 'hot' in rec: info.append(f"Hot: {rec['hot']}")
                 
        txt.insert("1.0", "\n".join(info))
        txt.config(state="disabled")

    def on_close(self):
        """Save position before destroying."""
        self.save_window_position(self, "StockDetailPopup")
        self.destroy()

class MarketPulseViewer(tk.Toplevel, WindowMixin):
    def __init__(self, master, monitor_app):
        """
        :param master: Root window
        :param monitor_app: Reference to StockMonitorApp (for access to data/methods)
        """
        super().__init__(master)
        self.title("每日复盘与机会仪表盘 (Market Pulse)")
        # Default geometry if no save found
        self.geometry("1000x800")
        
        # Load Window Position
        self.load_window_position(self, "MarketPulseViewer")
        
        self.monitor_app = monitor_app
        if getattr(monitor_app, 'selector', None) is None:
            self.monitor_app.open_stock_selection_window()
        self.engine = DailyPulseEngine(getattr(monitor_app, 'selector', None))
        self.logger = logging.getLogger("MarketPulseViewer")
        
        # Data
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.report_data = None
        
        # Styles
        self._init_styles()
        
        # Layout
        self._build_top_controls()
        self._build_panes()
        
        # Init Load
        self.refresh_report()
        
        # Bindings
        self.bind("<Escape>", lambda e: self.on_close())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_styles(self):
        style = ttk.Style()
        # [FIX] Larger row height and smaller font
        style.configure("Pulse.Treeview", rowheight=35, font=("Microsoft YaHei", 9))
        style.configure("Pulse.Treeview.Heading", font=("Microsoft YaHei", 9, "bold"))
        
        # Tags for rows
        self.tag_colors = {
            'hot': '#ffcccc',  # Light Red
            'warm': '#fff5cc', # Light Yellow
            'cold': '#f0f0f0'  # Light Grey
        }

    def _build_top_controls(self):
        ctrl_frame = tk.Frame(self, pady=5, padx=10, bg="#f5f5f5")
        ctrl_frame.pack(fill="x")
        
        # Date Selector
        tk.Label(ctrl_frame, text="日期(Date):", bg="#f5f5f5").pack(side="left")
        
        if HAS_CALENDAR:
            self.date_entry = DateEntry(ctrl_frame, width=12, background='darkblue', 
                                      foreground='white', borderwidth=2, 
                                      date_pattern='yyyy-mm-dd')
            self.date_entry.set_date(datetime.now())
            self.date_entry.pack(side="left", padx=5)
            self.date_entry.bind("<<DateEntrySelected>>", self.on_date_changed)
        else:
            self.date_var = tk.StringVar(value=self.current_date)
            self.date_entry = tk.Entry(ctrl_frame, textvariable=self.date_var, width=12)
            self.date_entry.pack(side="left", padx=5)
            tk.Button(ctrl_frame, text="Load", command=self.on_date_changed).pack(side="left")

        # Refresh (Generate)
        tk.Button(ctrl_frame, text="⚡ 生成/刷新今日战报", 
                  bg="#d9534f", fg="white", font=("Microsoft YaHei", 9, "bold"),
                  command=self.force_generate_today).pack(side="left", padx=20)
                  
        # Quick Nav
        tk.Button(ctrl_frame, text="昨天", command=lambda: self.shift_date(-1)).pack(side="left")
        tk.Button(ctrl_frame, text="今天", command=lambda: self.shift_date(0)).pack(side="left")

    def _build_panes(self):
        # Vertical PanedWindow
        self.paned = tk.PanedWindow(self, orient="vertical", sashrelief="raised", sashwidth=4)
        self.paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # # --- Top Pane: Market Context & Summary ---
        # top_frame = tk.LabelFrame(self.paned, text="市场温度与复盘总结 (Market Context)", padx=5, pady=5)
        # self.paned.add(top_frame, height=250)
        
        # # Left: Thermometer & Sectors
        # ctx_left = tk.Frame(top_frame)
        # ctx_left.pack(side="left", fill="y", padx=5)
        
        # tk.Label(ctx_left, text="市场温度:", font=("Microsoft YaHei", 12)).pack(anchor="w")
        # self.lbl_temp = tk.Label(ctx_left, text="0°C", font=("Arial", 24, "bold"), fg="gray")
        # self.lbl_temp.pack(anchor="w", pady=5)
        
        # tk.Label(ctx_left, text="核心风口:", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", pady=(10,0))
        # self.txt_sectors = tk.Text(ctx_left, width=30, height=50, font=("Microsoft YaHei", 9), bg="#f9f9f9")
        # self.txt_sectors.pack(fill="both", expand=True)

        # # Right: Strategy Summary & Notes
        # ctx_right = tk.Frame(top_frame)
        # ctx_right.pack(side="left", fill="both", expand=True, padx=5)
        
        # tk.Label(ctx_right, text="策略分析 & 交易笔记 (User Notes):", font=("Microsoft YaHei", 10)).pack(anchor="w")
        # self.txt_summary = scrolledtext.ScrolledText(ctx_right, height=8, font=("Microsoft YaHei", 10))
        # self.txt_summary.pack(fill="both", expand=True)
        
        # # Save Notes Button
        # btn_save_note = tk.Button(ctx_right, text="💾 保存笔记", command=self.save_notes)
        # btn_save_note.pack(anchor="e", pady=2)

        # --- Top Pane: Market Context & Summary ---
        top_frame = tk.LabelFrame(self.paned, text="市场温度与复盘总结 (Market Context)", padx=5, pady=5)
        self.paned.add(top_frame, height=350)
        # self.paned.add(top_frame)

        # ===== 左侧：核心风口（窄 + 可滚动）=====
        ctx_left = tk.Frame(top_frame)
        ctx_left.pack(side="right", fill="y", padx=(5, 0))   # 👉 放到右边，变成侧边栏

        tk.Label(ctx_left, text="核心风口:", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w")

        self.txt_sectors = scrolledtext.ScrolledText(
            ctx_left,
            width=28,
            height=18,
            font=("Microsoft YaHei", 9),
            bg="#f9f9f9",
            wrap="word"
        )
        self.txt_sectors.pack(fill="y", expand=True)

        # ===== 右侧主区域：市场温度 + 策略笔记 =====
        ctx_right = tk.Frame(top_frame)
        ctx_right.pack(side="left", fill="both", expand=True, padx=(0, 5))

        # --- 市场温度 & 大盘背景 (Professional Header) ---
        temp_frame = tk.Frame(ctx_right, bg="#f8f9fa", pady=10, highlightthickness=1, highlightbackground="#dee2e6")
        temp_frame.pack(fill="x", pady=(0, 10))

        # 1. Temperature Gauge
        temp_box = tk.Frame(temp_frame, bg="#f8f9fa")
        temp_box.pack(side="left", padx=15)
        tk.Label(temp_box, text="市场温度", font=("Microsoft YaHei", 9), bg="#f8f9fa", fg="#6c757d").pack()
        self.lbl_temp = tk.Label(temp_box, text="0°C", font=("Arial", 28, "bold"), bg="#f8f9fa", fg="#adb5bd")
        self.lbl_temp.pack()

        # 2. Market Breadth Bar
        breadth_box = tk.Frame(temp_frame, bg="#f8f9fa")
        breadth_box.pack(side="left", padx=20)
        tk.Label(breadth_box, text="市场涨跌家数比 (Breadth)", font=("Microsoft YaHei", 9), bg="#f8f9fa", fg="#6c757d").pack()
        
        # Breadth Canvas for Visual Bar
        self.breadth_canvas = tk.Canvas(breadth_box, width=200, height=18, bg="#e9ecef", highlightthickness=0)
        self.breadth_canvas.pack(pady=5)
        self.lbl_breadth_stats = tk.Label(breadth_box, text="↑ 0  |  ↓ 0", font=("Microsoft YaHei", 9, "bold"), bg="#f8f9fa")
        self.lbl_breadth_stats.pack()

        # 3. Index Status Grid
        index_box = tk.Frame(temp_frame, bg="#f8f9fa")
        index_box.pack(side="left", fill="both", expand=True, padx=10)
        
        indices_inner = tk.Frame(index_box, bg="#f8f9fa")
        indices_inner.pack(expand=True)
        
        self.idx_labels = {}
        for i, name in enumerate(["上证指数", "深证成指", "创业板指"]):
            f = tk.Frame(indices_inner, bg="#f8f9fa", padx=10)
            f.grid(row=0, column=i)
            tk.Label(f, text=name, font=("Microsoft YaHei", 8), bg="#f8f9fa", fg="#6c757d").pack()
            lbl = tk.Label(f, text="0.00%", font=("Consolas", 11, "bold"), bg="#f8f9fa", fg="#555")
            lbl.pack()
            self.idx_labels[name] = lbl

        # --- 策略分析 & 笔记 ---
        tk.Label(ctx_right, text="策略分析 & 交易笔记 (User Notes):", font=("Microsoft YaHei", 10)).pack(anchor="w")

        self.txt_summary = scrolledtext.ScrolledText(
            ctx_right,
            height=10,
            font=("Microsoft YaHei", 10),
            wrap="word"
        )
        self.txt_summary.pack(fill="both", expand=True)

        btn_save_note = tk.Button(ctx_right, text="💾 保存笔记", command=self.save_notes)
        btn_save_note.pack(anchor="e", pady=2)

        
        # --- Bottom Pane: Actionable Treeview ---
        bottom_frame = tk.LabelFrame(self.paned, text="机会雷达 & 操作计划 (Action Radar)", padx=5, pady=5)
        self.paned.add(bottom_frame)
        
        # Stats Bar
        self.lbl_stats = tk.Label(bottom_frame, text="Ready", font=("Arial", 9, "bold"), fg="#333", anchor="w")
        self.lbl_stats.pack(fill="x", pady=(0, 5))
        
        # New Columns Structure (Comprehensive)
        cols = [
            "index", "code", "name", "score", "rank", "gap", 
            "price", "add_price", "profit", 
            "win", "win_rate", "period", 
            "sector", "reason", "auto_reason", "action_plan"
        ]
        self.tree = ttk.Treeview(bottom_frame, columns=cols, show="headings", style="Pulse.Treeview")
        
        # Config Columns
        self.tree.column("index", width=35, anchor="center")
        self.tree.column("code", width=55, anchor="center")
        self.tree.column("name", width=65, anchor="center")
        self.tree.column("score", width=45, anchor="center")
        self.tree.column("rank", width=40, anchor="center")
        self.tree.column("gap", width=45, anchor="center")
        
        self.tree.column("price", width=55, anchor="center")
        self.tree.column("add_price", width=55, anchor="center")
        self.tree.column("profit", width=55, anchor="center")
        
        self.tree.column("win", width=35, anchor="center")
        self.tree.column("win_rate", width=45, anchor="center")
        self.tree.column("period", width=35, anchor="center")
        
        self.tree.column("sector", width=90, anchor="w")
        self.tree.column("reason", width=120, anchor="w") # Machine Reason
        self.tree.column("auto_reason", width=120, anchor="w") # Merged/User Reason
        self.tree.column("action_plan", width=300, anchor="w")
        
        # Headers & Sorting
        headers = {
            "index": "#", "code": "代码", "name": "名称", "score": "分值", 
            "rank": "Rank", "gap": "Gap", 
            "price": "现价", "add_price": "加入价", "profit": "盈亏%",
            "win": "连阳", "win_rate": "胜率", "period": "周期", 
            "sector": "板块", "reason": "入选理由", "auto_reason": "机选/标注", "action_plan": "操作计划"
        }
        
        for c in cols:
            self.tree.heading(c, text=headers.get(c, c), command=lambda _c=c: self.sort_tree(_c, False))
            
        # Scrollbars
        vsb = ttk.Scrollbar(bottom_frame, orient="vertical", command=self.tree.yview)
        # hsb = ttk.Scrollbar(bottom_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set)
        
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        
        # Bindings
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.on_right_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Up>", self.on_key_nav)
        self.tree.bind("<Down>", self.on_key_nav)

    def sort_tree(self, col, reverse):
        """Sort treeview content by column."""
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        # Try to sort numerically if possible
        try:
            l.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
            # Re-index the '#' column if sorting by other columns? 
            # Usually we want Index to stay static or move? 
            # Let's keep Index static (row number) or dynamic? 
            # If we explicitly sort, the row content moves.
            # If we want the '#' column to update to 1,2,3... sorted order:
            self.tree.set(k, "index", index + 1)

        # Toggle sort direction
        self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))

    # --- Logic ---
    
    def shift_date(self, delta):
        if delta == 0:
            target = datetime.now()
        else:
            try:
                curr = datetime.strptime(self.current_date, "%Y-%m-%d")
                target = curr + timedelta(days=delta)
            except:
                target = datetime.now()
                
        if HAS_CALENDAR:
            self.date_entry.set_date(target)
            self.on_date_changed(None)
        else:
            self.date_var.set(target.strftime("%Y-%m-%d"))
            self.on_date_changed()

    def on_date_changed(self, event=None):
        if HAS_CALENDAR:
            self.current_date = self.date_entry.get_date().strftime("%Y-%m-%d")
        else:
            self.current_date = self.date_var.get()
            
        self.refresh_report(use_cache=True)

    def force_generate_today(self):
        """Force regeneration of today's report from live data."""
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        if HAS_CALENDAR:
            self.date_entry.set_date(datetime.now())
        else:
            self.date_var.set(self.current_date)
            
        # Trigger Engine
        monitored = getattr(self.monitor_app.live_strategy, '_monitored_stocks', {}) if self.monitor_app.live_strategy else {}
        self.engine.generate_daily_report(monitored, force_date=self.current_date)
        
        self.refresh_report(use_cache=True)
        messagebox.showinfo("Success", "今日战报已生成/刷新！")

    def refresh_report(self, use_cache=True):
        """Load data from DB and update UI."""
        data = self.engine.get_history(self.current_date)
        self.report_data = data
        
        summary = data.get('summary', {})
        stocks = data.get('stocks', [])
        
        # 1. Update Context
        temp = summary.get('temperature', 0)
        # Professional Color Scale: Cold (Blue) -> Moderate (Orange/Gray) -> Hot (Red)
        temp_color = "#6c757d" # Default
        if temp > 75: temp_color = "#d9534f" # Red
        elif temp > 55: temp_color = "#f0ad4e" # Orange
        elif temp < 30: temp_color = "#5bc0de" # Blue (Cold)
        
        self.lbl_temp.config(text=f"{temp:.0f}°C", fg=temp_color)
        
        # Update Breadth Bar
        breadth = summary.get('breadth')
        if breadth:
            up = breadth.get('up', 0)
            down = breadth.get('down', 0)
            flat = breadth.get('flat', 0)
            total = breadth.get('total', 1)
            
            # Draw Bar
            self.breadth_canvas.delete("all")
            w = 200
            up_w = (up / total) * w
            flat_w = (flat / total) * w
            # Red for Up, Green for Down in A-share context
            self.breadth_canvas.create_rectangle(0, 0, up_w, 20, fill="#f2dede", outline="") # Tinted Red
            self.breadth_canvas.create_rectangle(up_w, 0, up_w + flat_w, 20, fill="#eeeeee", outline="") # Gray
            self.breadth_canvas.create_rectangle(up_w + flat_w, 0, w, 20, fill="#dff0d8", outline="") # Tinted Green
            
            # Foreground stronger bars
            self.breadth_canvas.create_rectangle(0, 6, min(up_w, 2), 12, fill="#d9534f", outline="")
            self.breadth_canvas.create_rectangle(w - min((w-(up_w+flat_w)), 2), 6, w, 12, fill="#5cb85c", outline="")

            self.lbl_breadth_stats.config(
                text=f"↑ {up}  |  ↓ {down}  ({flat})", 
                fg="#d9534f" if up > down else "#5cb85c"
            )

        # Update Indices Performance
        indices = summary.get('indices', [])
        idx_map = {idx['name']: idx for idx in indices}
        # Display Names Mapping
        display_names = {"上证指数": ["上证指数", "sh000001", "sh000001"], 
                         "深证成指": ["深证成指", "sz399001", "sz399001"], 
                         "创业板指": ["创业板指", "sz399006", "sz399006"]}
        
        for name, lbl in self.idx_labels.items():
            # Search for best match in index data
            found = None
            for idx_data in indices:
                if name in idx_data['name'] or idx_data['name'] in name:
                    found = idx_data
                    break
            
            if found:
                pct = found['percent']
                color = "#d9534f" if pct > 0 else "#5cb85c" if pct < 0 else "#6c757d"
                lbl.config(text=f"{pct:+.2f}%", fg=color)
            else:
                 lbl.config(text="N/A", fg="#ccc")
        
        # Hot Sectors
        hot_list = summary.get('hot_sectors', [])
        sector_text = ""
        for s in hot_list[:10]:
             # s is [name, pct]
             sector_text += f"{s[0]} : {s[1]}%\n"
        self.txt_sectors.delete("1.0", tk.END)
        self.txt_sectors.insert(tk.END, sector_text)
        
        # User Notes / Summary
        self.txt_summary.delete("1.0", tk.END)
        note = summary.get('user_notes', '') or summary.get('summary_text', '')
        self.txt_summary.insert(tk.END, note)
        
        # 2. Update Tree
        self.tree.delete(*self.tree.get_children())
        
        # Sort by Score desc
        stocks.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        total_score = 0
        count = len(stocks)
        
        for idx, s in enumerate(stocks):
            status = s.get('status', {})
            score = s.get('score', 0)
            total_score += score
            
            # Extract new fields
            rank = status.get('rank', 0)
            gap = status.get('topR', 0)
            win = status.get('win', 0)
            win_rate = status.get('win_rate', 0)
            period = status.get('period', 'd')
            
            price = status.get('price', 0)
            add_price = status.get('add_price', 0)
            profit = status.get('profit', 0)
            
            # Format Profit Color
            profit_str = f"{profit:+.2f}%" if add_price > 0 else "-"

            values = (
                idx + 1,
                s.get('code'),
                s.get('name'),
                f"{score:.1f}",
                rank,
                f"{gap:.2f}" if isinstance(gap, (int, float)) else gap,
                price,
                add_price,
                profit_str,
                win,
                f"{win_rate:.1f}%" if win_rate else "-",
                period,
                s.get('sector', ''),
                s.get('reason', ''),
                "", # auto_reason placeholder
                s.get('action_plan', '')
            )
            # Tag logic
            tag = 'hot' if score > 90 else 'warm' if score > 80 else 'cold'
            self.tree.insert("", "end", values=values, tags=(tag,))
            
        # Update Stats Bar
        avg_score = total_score / count if count > 0 else 0
        self.lbl_stats.config(text=f"Total: {count}  |  Avg Score: {avg_score:.1f}")

        self.tree.tag_configure('hot', background='#ffe6e6') # Light red
        self.tree.tag_configure('warm', background='#fff9e6') # Light yellow

    def save_notes(self):
        """Save text area content to DB."""
        content = self.txt_summary.get("1.0", tk.END).strip()
        if self.engine.update_notes(self.current_date, content):
            messagebox.showinfo("Saved", "笔记已保存")
        else:
            messagebox.showerror("Error", "保存失败")

    # --- Interactions & Linkage ---
    
    def on_close(self):
        """Save position before destroying."""
        self.save_window_position(self, "MarketPulseViewer")
        self.destroy()

    def on_key_nav(self, event):
        """Handle Up/Down keys for interaction."""
        # Allow default navigation to happen first, then trigger select
        self.after(10, lambda: self.on_select(None))

    def on_select(self, event):
        """Single Click / Selection: Linkage (TDX & Vis)."""
        item = self.tree.selection()
        if not item: return
        
        vals = self.tree.item(item, "values")
        if not vals: return
        
        code = vals[1] # Code index
        # # 1. TDX Linkage (Clipboard)
        # try:
        #     import pyperclip
        #     pyperclip.copy(code)
        # except: pass
        
        # 2. Push to Visualizer / Linkage via Monitor App
        if self.monitor_app and hasattr(self.monitor_app, 'sender'):
             # Construct minimal row data for push
            # row_data = {'name': vals[2], 'high': 0, 'lastp1d': 0, 'percent': 0, 'close': vals[6], 'volume': 0}
            # self.monitor_app.push_stock_info(code, row_data)
            self.monitor_app.sender.send(code)
        if hasattr(self.monitor_app, 'open_visualizer') and self.monitor_app.vis_var.get():
            self.monitor_app.open_visualizer(code)
        # # 3. Sync Main Window Search (Optional but helpful)
        # if self.monitor_app and hasattr(self.monitor_app, 'search_var1'):
        #     try:
        #         self.monitor_app.search_var1.set(code)
        #     except: pass

    def on_double_click(self, event):
        """Show Comprehensive Stock Detail."""
        item = self.tree.selection()
        if not item: return
        vals = self.tree.item(item, "values")
        code = vals[1]
        name = vals[2]
        
        self.show_stock_detail_popup(code, name)

    def show_stock_detail_popup(self, code, name):
        """Display aggregated stock info (55188, Selection, Realtime)."""
        StockDetailPopup(self, code, name, self)

    def on_right_click(self, event):
        """Context Menu."""
        item = self.tree.identify_row(event.y)
        if not item: return
        self.tree.selection_set(item)
        values = self.tree.item(item, "values")
        self.tree.selection_set(item)
        values = self.tree.item(item, "values")
        code = values[1]
        name = values[2]
        
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=f"K线图: {code}", command=lambda: self.on_double_click(None))
        menu.add_command(label="复 制 代 码", command=lambda: pyperclip.copy(code))
        
        # Add to Monitor (if not already there? Logic handled by app)
        menu.add_separator()
        menu.add_command(label="加入实时监控 (Add to Monitor)", command=lambda: self.add_to_monitor(code, name))
        
        menu.post(event.x_root, event.y_root)

    def add_to_monitor(self, code, name):
        """Inject into active strategy."""
        # This requires the monitor app to have a method for manual addition
        # Or we call stock_live_strategy directly via self.monitor_app.live_strategy
        if hasattr(self.monitor_app, 'add_voice_monitor_dialog'):
             self.monitor_app.add_voice_monitor_dialog(code, name)
             toast_message(self,f"Added {name} ({code}) 已加入实时监控")
        else:
             toast_message(self,"Warning 主程序不支持手动添加")

if __name__ == "__main__":
    # Test Stub
    root = tk.Tk()
    app = MarketPulseViewer(root, None)
    root.mainloop()
