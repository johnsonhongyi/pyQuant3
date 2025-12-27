import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
from datetime import datetime
from typing import Optional, Any, TYPE_CHECKING
from collections import Counter
import pandas as pd

if TYPE_CHECKING:
    from stock_live_strategy import StockLiveStrategy
    from stock_selector import StockSelector

class StockSelectionWindow(tk.Toplevel):
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
        self.geometry("1100x600")
        
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
        
        self._init_ui()
        
        # 默认使用最近一次查询
        if self.history:
            self.concept_filter_var.set(self.history[0])
            
        self.load_data()

        # Center window
        self._center_window()

    def _center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry('{}x{}+{}+{}'.format(width, height, x, y))

    def _init_ui(self):
        # --- Toolbar ---
        toolbar = tk.Frame(self, bd=1, relief="raised")
        toolbar.pack(fill="x", padx=5, pady=5)
        
        # Concept Filter
        tk.Label(toolbar, text="板块筛选:", font=("Arial", 10)).pack(side="left", padx=2)
        tk.Button(toolbar, text="🧹", command=self.clear_filter, width=2).pack(side="left", padx=1)
        self.concept_filter_var: tk.StringVar = tk.StringVar()
        self.concept_combo: ttk.Combobox = ttk.Combobox(toolbar, textvariable=self.concept_filter_var, width=10)
        self.concept_combo['values'] = self.history
        self.concept_combo.pack(side="left", padx=2)

        tk.Button(toolbar, text="🔍", command=self.on_filter_search, width=3).pack(side="left", padx=1)
        tk.Button(toolbar, text="🗑️", command=self.delete_current_history, width=2, fg="red").pack(side="left", padx=1)

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

        tk.Button(toolbar, text="🚀 导入选中", command=self.import_selected, bg="#ffd54f", font=("Arial", 10, "bold")).pack(side="right", padx=10, pady=5)

        # --- Main List ---
        # Columns
        columns = ("code", "name", "score", "price", "percent", "volume", "category", "auto_reason", "user_status", "user_reason")
        
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        
        # Headings
        headers = {
            "code": "代码", "name": "名称", "score": "机选分", 
            "price": "现价", "percent": "涨幅%", "volume": "成交量",
            "category": "板块/概念",
            "auto_reason": "机选理由", "user_status": "人工状态", "user_reason": "人工理由"
        }
        
        for col, text in headers.items():
            self.tree.heading(col, text=text, command=lambda c=col: self.sort_tree(c, False))
            self.tree.column(col, anchor="center")

        # Column Widths
        self.tree.column("code", width=80)
        self.tree.column("name", width=80)
        self.tree.column("score", width=60)
        self.tree.column("price", width=60)
        self.tree.column("percent", width=60)
        self.tree.column("volume", width=80)
        self.tree.column("category", width=150)
        self.tree.column("auto_reason", width=250)
        self.tree.column("user_status", width=80)
        self.tree.column("user_reason", width=150)
        
        # Tags for coloring
        self.tree.tag_configure("selected", background="#dcedc8")  # Light Green
        self.tree.tag_configure("ignored", background="#ffcdd2")   # Light Red
        self.tree.tag_configure("pending", background="#ffffff")   # White

        # Bindings
        self.tree.bind("<ButtonRelease-1>", self.on_select)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
    def load_data(self, force=False):
        # Clear
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        try:
            if self.selector:
                self.df_candidates = self.selector.get_candidates_df(force=force)
            else:
                self.df_candidates = pd.DataFrame()
                
            if self.df_candidates.empty:
                self._update_title_stats()
                # messagebox.showinfo("提示", "策略未筛选出任何标的")
                return

            # Apply Concept Filter
            filter_str = self.concept_filter_var.get().strip()
            if filter_str:
                # Support multi-keywords with space
                keywords = filter_str.split()
                for kw in keywords:
                    self.df_candidates = self.df_candidates[
                        self.df_candidates['category'].str.contains(kw, na=False)
                    ]
            
            if self.df_candidates.empty:
                 self._update_title_stats()
                 # Don't show info if it's just a filter result
                 # messagebox.showinfo("提示", "筛选后无数据")
                 return
            
            self._update_title_stats()

            # Init user columns
            self.df_candidates['user_status'] = "待定"
            self.df_candidates['user_reason'] = ""
            
            for index, row in self.df_candidates.iterrows():
                self.tree.insert("", "end", iid=row['code'], values=(
                    row['code'], row['name'], row['score'], row['price'], 
                    row['percent'], row['volume'], row.get('category', ''), row['reason'], 
                    "待定", ""
                ), tags=("pending",))
                
        except Exception as e:
            messagebox.showerror("错误", f"加载数据失败: {e}")

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
        
        total = len(self.df_candidates)
        if top3:
            stats_str = " | ".join([f"{tag}({count})" for tag, count in top3])
            new_title = f"{base_title} - [共{total}条 | 理由频次: {stats_str}]"
        else:
            new_title = f"{base_title} - [共{total}条]"
            
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
        self.load_data()

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
            cur_values = self.tree.item(item_id, "values")
            # Create new values tuple
            new_values = list(cur_values)
            new_values[8] = status
            new_values[9] = reason
            
            self.tree.item(item_id, values=new_values, tags=(tag,))

    def import_selected(self):
        to_import = []
        feedback_data = []
        
        # Iterate all items to collect feedback and imports
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            code = values[0]
            name = values[1]
            status = values[8]
            user_reason = values[9]
            
            # 只要不是默认状态，就记录反馈以便优化
            if status != "待定":
                feedback_data.append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "code": code,
                    "name": name,
                    "auto_score": values[2],
                    "auto_reason": values[7],
                    "user_status": status,
                    "user_reason": user_reason
                })
            
            if status == "选中":
                to_import.append(code)
        
        if not to_import:
            if not messagebox.askyesno("确认", "未标记任何[选中]的股票。\n是否仅保存反馈并关闭？"):
                return
        
        # 1. Update Monitor List
        if to_import and self.live_strategy:
            count = 0
            if hasattr(self.live_strategy, '_monitored_stocks'):
                existing = self.live_strategy._monitored_stocks
                for code in to_import:
                    if code not in existing:
                        existing[code] = {
                            "rules": [], # Empty rules, will be auto-filled or manual
                            "last_alert": 0,
                            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "tags": "auto_verify", 
                            "snapshot": {},
                            "name": "" # Name will be filled by system
                        }
                        count += 1
                
                if count > 0:
                    if hasattr(self.live_strategy, '_save_monitors'):
                        self.live_strategy._save_monitors()
                    messagebox.showinfo("成功", f"成功导入 {count} 只新股票到监控列表！")
                else:
                    messagebox.showinfo("提示", "所选股票已在监控列表中。")
        
        # 2. Save Feedback
        self.save_feedback(feedback_data)
        
        # Close
        self.destroy()

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
        try:
            l.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))
