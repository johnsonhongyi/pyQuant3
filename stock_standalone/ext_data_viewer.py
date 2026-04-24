# -*- coding:utf-8 -*-
import tkinter as tk
from tkinter import ttk
import pandas as pd
from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.treeview_mixin import TreeviewMixin
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger()

class ExtDataViewer(tk.Toplevel, WindowMixin, TreeviewMixin):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.title("55188.cn 实时数据可视化 (集成版)")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        
        # 获取主窗口的 sender 和 scroll_to_code 函数用于联动
        self.sender = getattr(parent, 'sender', None)
        self.on_tree_scroll_to_code = getattr(parent, 'tree_scroll_to_code', None)
        
        # 定义窗口 ID 用于保存位置
        self.window_id = "ExtDataViewer"
        self.detail_window_id = "个股分析"
        self._detail_win = None
        self._sender_code = None
        # 同步缩放比例
        self.scale_factor = getattr(parent, 'scale_factor', 1.0)
        
        # 1. 主力 Tab (增加 现价, 涨幅, 所属板块, 以及 df_all 中的 percent, win, sum_pct)
        self.tab_zhuli = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_zhuli, text="主力排名")
        self.tree_zhuli = self._create_treeview(self.tab_zhuli, [
            ("code", "代码", 70),
            ("name", "名称", 100),
            ("zhuli_rank", "排名", 50),
            ("price", "现价", 70),
            ("change_pct", "涨幅%", 60),
            ("percent", "今日%", 60),
            ("win", "胜率", 50),
            ("sum_perc", "盈亏%", 60),
            ("net_ratio", "主力净占比%", 110),
            ("sector", "所属板块", 120)
        ])
        
        # 2. 人气 Tab
        self.tab_hot = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_hot, text="人气榜单")
        self.tree_hot = self._create_treeview(self.tab_hot, [
            ("code", "代码", 70),
            ("name", "名称", 100),
            ("hot_rank", "排名", 50),
            ("price", "现价", 70),
            ("change_pct", "涨幅%", 60),
            ("percent", "今日%", 60),
            ("win", "胜率", 50),
            ("sum_perc", "盈亏%", 60),
            ("hot_tag", "标签", 200),
            ("hot_reason", "深度推导逻辑", 550)
        ])
        
        # 3. 题材 Tab
        self.tab_theme = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_theme, text="题材挖掘")
        self.tree_theme = self._create_treeview(self.tab_theme, [
            ("code", "代码", 70),
            ("name", "名称", 100),
            ("theme_date", "日期", 100),
            ("price", "现价", 70),
            ("change_pct", "涨幅%", 60),
            ("percent", "今日%", 60),
            ("win", "胜率", 50),
            ("sum_perc", "盈亏%", 60),
            ("theme_name", "所属题材", 200),
            ("theme_logic", "题材逻辑推演", 550)
        ])
        
        # 4. 底部状态栏用于显示计数
        self.status_frame = tk.Frame(self, relief="sunken", bd=1)
        self.status_frame.pack(side="bottom", fill="x")
        self.status_label = tk.Label(self.status_frame, text="正在加载数据...", anchor="w", padx=10, font=("微软雅黑", 9))
        self.status_label.pack(side="left")
        
        # 🚀 [NEW] DNA审计按钮贴行附加
        self.btn_dna = tk.Button(self.status_frame, text="🧬 DNA审计", font=("微软雅黑", 9, "bold"), fg="#ffffff", bg="#333333", relief="flat", command=self._run_dna_audit_selected, width=12)
        self.btn_dna.pack(side="right", padx=5, pady=2)
        
        # 存储各 Tab 的计数
        self.counts = {"主力排名": 0, "人气榜单": 0, "题材挖掘": 0}
        
        # 绑定 Tab 切换
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        # 加载位置，设置较大的默认显示尺寸
        if hasattr(parent, 'load_window_position'):
            parent.load_window_position(self, self.window_id, default_width=1200, default_height=750)
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _create_treeview(self, parent, columns):
        """通用 Treeview 创建方法，带排序和点击绑定"""
        frame = tk.Frame(parent)
        frame.pack(fill="both", expand=True)
        
        col_ids = [c[0] for c in columns]
        tree = ttk.Treeview(frame, columns=col_ids, show="headings", selectmode="browse")
        
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        
        for cid, label, width in columns:
            # 数值列居中，其余列左对齐
            anchor = "center" if cid in ['code', 'zhuli_rank', 'hot_rank', 'price', 'change_pct', 'net_ratio', 'percent', 'win', 'sum_perc'] else "w"
            tree.heading(cid, text=label, command=lambda _c=cid: self.sort_tree_column(tree, _c, False))
            tree.column(cid, width=width, anchor=anchor)
            
        # 绑定点击事件
        tree.bind("<Button-1>", lambda e: self._on_tree_click(e, tree, "left"))
        tree.bind("<Button-3>", lambda e: self._on_tree_click(e, tree, "right"))
        tree.bind("<Double-1>", lambda e: self._on_double_click(e, tree))
        # 支持上下键选择
        tree.bind("<<TreeviewSelect>>", lambda e: self._on_tree_select(e, tree))
            
        return tree

    def sort_tree_column(self, tree, col, reverse):
        """通用的 Treeview 排序逻辑"""
        l = [(tree.set(k, col), k) for k in tree.get_children('')]
        
        def _key_func(t):
            s = t[0].strip()
            if not s or s == '-': 
                # 空值或无效值始终排在最后（通过最小优先级）
                return (-1, "")
            try:
                # 1. 尝试作为数字排序 (处理百分号、正号)
                val = float(s.replace('%', '').replace('+', ''))
                return (0, val)
            except (ValueError, TypeError):
                # 2. 否则作为字符串/日期排序
                return (1, s.lower())

        l.sort(key=_key_func, reverse=reverse)

        for index, (val, k) in enumerate(l):
            tree.move(k, '', index)

        # 反转排序方向
        tree.heading(col, command=lambda: self.sort_tree_column(tree, col, not reverse))

    def _on_tree_select(self, event, tree):
        """处理切换选中项的联动（支持上下键）"""
        sel = tree.selection()
        if not sel: return
        item = sel[0]
        vals = tree.item(item, "values")
        if vals:
            stock_code = str(vals[0])
            # 发送到 TDX
            if self.sender and hasattr(self.sender, 'send'):
                self.sender.send(stock_code)
            
            # [NEW] 根据 vis_var 开关联动到可视化窗口
            parent = self.master
            if parent and getattr(parent, "_vis_enabled_cache", False) and stock_code:
                if hasattr(parent, 'open_visualizer'):
                    # [NEW] 题材挖掘 Tab 传递日期联动
                    stock_date = None
                    if tree == self.tree_theme and len(vals) > 2:
                        raw_date = str(vals[2]).strip().replace('/', '-')
                        if raw_date and raw_date != '-':
                            stock_date = raw_date
                    if stock_date:
                        logger.info(f"🚀 [Linkage] 题材联动: {stock_code} date={stock_date}")
                    parent.open_visualizer(stock_code, timestamp=stock_date)

    def _on_tree_click(self, event, tree, button_type):
        """处理树视图点击联动"""
        item = tree.identify_row(event.y)
        if not item: return
        
        vals = tree.item(item, "values")
        if not vals: return
        stock_code = str(vals[0])
        
        if button_type == "left":
            # 左键点击其实会触发 <<TreeviewSelect>>，这里手动再触发一次确保万无一失
            if self._sender_code is not None  and self._sender_code == stock_code:
                return
            else:
                # 发送到 TDX
                if self.sender and hasattr(self.sender, 'send'):
                    self.sender.send(stock_code)
                    self._sender_code = stock_code
                
                # [NEW] 根据 vis_var 开关联动到可视化窗口
                parent = self.master
                if parent and getattr(parent, "_vis_enabled_cache", False) and stock_code:
                    if hasattr(parent, 'open_visualizer'):
                        # [NEW] 题材挖掘 Tab 传递日期联动
                        stock_date = None
                        if tree == self.tree_theme and len(vals) > 2:
                            raw_date = str(vals[2]).strip().replace('/', '-')
                            if raw_date and raw_date != '-':
                                stock_date = raw_date
                        if stock_date:
                            logger.info(f"🚀 [Linkage] 题材联动 (Click): {stock_code} date={stock_date}")
                        parent.open_visualizer(stock_code, timestamp=stock_date)
        elif button_type == "right":
            # [NEW] Right Click Context Menu
            menu = tk.Menu(self, tearoff=0, bg="#2C2C2E", fg="white", activebackground="#005BB7")
            if self.on_tree_scroll_to_code:
                menu.add_command(label=f"📂 滚动主表定位代码: {stock_code}", command=lambda: self.on_tree_scroll_to_code(stock_code))
                menu.add_separator()
            
            sel = tree.selection()
            if item not in sel:
                tree.selection_set(item)
                sel = (item,)
                
            title_dna = f"🧬 执行 DNA 审计 ({len(sel)}只...)" if len(sel) > 1 else f"🧬 执行 DNA 审计 ({vals[1]})"
            menu.add_command(label=title_dna, command=self._run_dna_audit_selected)
            
            # [NEW] 手动触发可视化联动
            if len(sel) == 1:
                menu.add_separator()
                def _manual_vis():
                    parent = self.master
                    if hasattr(parent, 'open_visualizer'):
                        stock_date = None
                        if tree == self.tree_theme and len(vals) > 2:
                            raw_date = str(vals[2]).strip().replace('/', '-')
                            if raw_date and raw_date != '-':
                                stock_date = raw_date
                        if stock_date:
                            logger.info(f"🚀 [Linkage] 题材联动 (Manual): {stock_code} date={stock_date}")
                        parent.open_visualizer(stock_code, timestamp=stock_date)
                menu.add_command(label="📈 联动可视化 (指引日期)", command=_manual_vis)
            
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

    def _get_active_tree(self):
        tab_id = self.notebook.select()
        if not tab_id: return None
        tab_text = self.notebook.tab(tab_id, "text")
        if tab_text == "主力排名": return self.tree_zhuli
        elif tab_text == "人气榜单": return self.tree_hot
        elif tab_text == "题材挖掘": return self.tree_theme
        return None

    def _run_dna_audit_selected(self):
        """🚀 [DNA-BATCH] 极限审计当前视图所选 / Top20"""
        tree = self._get_active_tree()
        if not tree: return
        
        items = list(tree.get_children())
        if not items: return
        
        selection = tree.selection()
        target_items = []
        if len(selection) > 1:
            target_items = selection[:50]
        elif len(selection) == 1:
            try:
                start_idx = items.index(selection[0])
            except ValueError:
                start_idx = 0
            target_items = items[start_idx : start_idx + 20]
        else:
            target_items = items[:20]
            
        code_to_name = {}
        for it in target_items:
            vals = tree.item(it, "values")
            if vals:
                # The first two columns should be code and name in all three tables
                c = str(vals[0]).strip().zfill(6)
                n = str(vals[1]).strip()
                import re
                c = re.sub(r'[^\d]', '', c)
                if c and c != "N/A":
                    code_to_name[c] = n
                    
        if code_to_name:
            if hasattr(self.master, '_run_dna_audit_batch'):
                if hasattr(self.master, 'tk_dispatch_queue'):
                    # 🚀 [THREAD-SAFE] 通过 Tk 调度队列执行
                    _cn = dict(code_to_name)
                    self.master.tk_dispatch_queue.put(lambda: self.master._run_dna_audit_batch(_cn))
                else:
                    self.master._run_dna_audit_batch(code_to_name)
            else:
                logger.error("No access to main monitor app for DNA audit.")

    def _on_double_click(self, event, tree):
        """双击打开详情窗口"""
        item = tree.identify_row(event.y)
        if not item: return
        
        col = tree.identify_column(event.x)
        # 获取列名
        col_id = tree.cget("columns")[int(col.replace('#', '')) - 1]
        
        vals = tree.item(item, "values")
        if not vals: return
        
        # 寻找对应的列索引
        col_list = list(tree.cget("columns"))
        idx_reason = -1
        idx_logic = -1
        
        if "hot_reason" in col_list: idx_reason = col_list.index("hot_reason")
        if "theme_logic" in col_list: idx_logic = col_list.index("theme_logic")
        
        content = ""
        title = f"个股分析 - {vals[1]}({vals[0]})"
        
        if col_id in ["hot_reason", "hot_tag"] and idx_reason != -1:
            content = vals[idx_reason]
        elif col_id in ["theme_logic", "theme_name"] and idx_logic != -1:
            content = vals[idx_logic]
        else:
            # 如果点击其他列，优先显示逻辑
            content = vals[idx_logic] if idx_logic != -1 and vals[idx_logic] else (vals[idx_reason] if idx_reason != -1 else "")

        if content:
            self._show_detail_window(title, content)

    def _show_detail_window(self, title, content):
        """显示详情弹窗 (支持复用)"""
        if self._detail_win and self._detail_win.winfo_exists():
            self._detail_win.title(title)
            # 更新内容
            txt = getattr(self._detail_win, 'txt_widget', None)
            if txt:
                txt.config(state="normal")
                txt.delete("1.0", "end")
                txt.insert("1.0", content)
                txt.config(state="disabled")
            self._detail_win.lift()
            self._detail_win.focus_force()
            return

        win = tk.Toplevel(self)
        win.title(title)
        self._detail_win = win
        
        # 加载位置
        self.load_window_position(win, self.detail_window_id, default_width=600, default_height=400)
        self._detail_win.lift()
        self._detail_win.focus_force()
        
        txt = tk.Text(win, wrap="word", font=("微软雅黑", 11), padx=10, pady=10)
        txt.insert("1.0", content)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        win.txt_widget = txt # 保存引用方便复用
        
        btn = tk.Button(win, text="关闭", command=lambda: self._on_detail_close(win), pady=5)
        btn.pack(side="bottom", fill="x")
        
        win.protocol("WM_DELETE_WINDOW", lambda: self._on_detail_close(win))
        win.bind("<Escape>", lambda e: self._on_detail_close(win))

    def _on_detail_close(self, win):
        """关闭详情窗口并保存位置"""
        self.save_window_position(win, self.detail_window_id)
        win.destroy()
        if self._detail_win == win:
            self._detail_win = None

    def _on_tab_changed(self, event):
        """Tab 切换时更新状态栏计数"""
        tab_id = self.notebook.select()
        tab_text = self.notebook.tab(tab_id, "text")
        count = self.counts.get(tab_text, 0)
        self.status_label.config(text=f"当前视图: {tab_text} | 总计: {count} 只个股")

    def update_data(self, df: pd.DataFrame):
        """更新显示内容"""
        if df is None or df.empty:
            return
            
        # 预处理：确保所有列存在并清理空值
        df = df.copy()
        
        def _sanitize_df(d):
            """内部工具：确保 'code' 仅作为唯一的列存在，且不出现在 index 中，同步归一化代码字段"""
            if d is None or d.empty: return d
            d = d.copy()
            
            # 1. 强力清理 index 名字冲突 (解决 'code' is both an index level and a column label 报错)
            if 'code' in d.columns:
                # 如果 code 已经在列里了，检查 index 名字，如果 index 也是 code 则丢弃 index 名
                if d.index.name == 'code' or 'code' in d.index.names:
                    d.index.name = None
            else:
                # 如果 code 不在列里，但 index 是 code，则 reset 到列里
                if d.index.name == 'code' or 'code' in d.index.names:
                    d = d.reset_index()
                else:
                    # 兜底：如果都没有 code，尝试把当前 index 强制作为 code（如果内容看起来像代码）
                    first_val = str(d.index[0]) if len(d.index) > 0 else ""
                    if len(first_val) <= 9: # 考虑 sz000001 长度
                         d.index.name = 'code'
                         d = d.reset_index()

            # 2. 处理重复列名 (防止 pandas 允许的同名列干扰)
            if d.columns.duplicated().any():
                d = d.loc[:, ~d.columns.duplicated()]

            # 3. 核心：将 code 强制归一化为 6 位数字字符串 (处理 sz000001, 000001, 1, 1.0 等)
            if 'code' in d.columns:
                d['code'] = d['code'].astype(str).str.replace(r'^[a-zA-Z]+', '', regex=True).str.zfill(6).str[-6:]
            
            return d

        # 采样清洗输入的 df
        df = _sanitize_df(df)

        # 整合 master.df_all 中的数据 (使用 getattr 避开 Pylance 检查)
        df_all = getattr(self.master, 'df_all', None)
        if df_all is not None and not df_all.empty:
            df_main = _sanitize_df(df_all)
            
            # 映射关系补强：根据 TDX/Eastmoney 常见字段兼容 trade 和 close
            # 1. 自动识别主表中的行情列
            price_col = 'close' if 'close' in df_main.columns else ('trade' if 'trade' in df_main.columns else None)
            change_col = 'per1d' if 'per1d' in df_main.columns else ('percent' if 'percent' in df_main.columns else None)
            
            master_cols_to_use = ['percent', 'win', 'sum_perc']
            if price_col: master_cols_to_use.append(price_col)
            if change_col: master_cols_to_use.append(change_col)
            
            # 提取需要的列
            actual_master = [c for c in master_cols_to_use if c in df_main.columns]
            if actual_master:
                df = df.merge(df_main[['code'] + actual_master].drop_duplicates('code'), on='code', how='left', suffixes=('', '_all'))
                
                # 建立 UI 字段补齐逻辑
                # mapping = {
                #     'percent': 'percent_all',
                #     'win': 'win_all',
                #     'sum_perc': 'sum_perc_all',
                #     'price': f"{price_col}_all" if price_col else None,
                #     'change_pct': f"{change_col}_all" if change_col else None
                # }
                mapping = {
                    'percent': 'percent',
                    'win': 'win',
                    'sum_perc': 'sum_perc',
                    'price': f"{price_col}" if price_col else None,
                    'change_pct': f"{change_col}" if change_col else None
                }
                for ui_col, master_suffix_col in mapping.items():
                    if master_suffix_col and master_suffix_col in df.columns:
                        if ui_col in df.columns:
                            # 补齐逻辑：如果是数值列，0 也要补
                            if pd.api.types.is_numeric_dtype(df[ui_col]):
                                df[ui_col] = df[ui_col].replace(0, pd.NA).fillna(df[master_suffix_col])
                            else:
                                df[ui_col] = df[ui_col].replace('', pd.NA).fillna(df[master_suffix_col])
                        else:
                            df[ui_col] = df[master_suffix_col]
                        
                # 清理临时列
                cols_to_drop = [c for c in df.columns if c.endswith('_all')]
                if cols_to_drop:
                    df.drop(columns=cols_to_drop, inplace=True)

        # 🚀 深度补全名称：解决题材挖掘等 Tab 中 name 丢失问题
        if 'name' in df.columns:
            # 1. 优先从 df_all 补充
            if df_all is not None and not df_all.empty and 'name' in df_all.columns:
                name_map = df_all.set_index('code')['name'].to_dict()
                df['name'] = df['name'].replace('', pd.NA).fillna(df['code'].map(name_map))
            
            # 2. 如果还有空，确保不是 NaN 而是空字符串，方便显示
            df['name'] = df['name'].fillna('')

        for col in ['name', 'hot_tag', 'hot_reason', 'theme_name', 'theme_logic', 'theme_date', 'sector', 'percent', 'win', 'sum_perc']:
            if col in df.columns:
                df[col] = df[col].fillna('')
            
        # 1. 更新主力 (显示前 200 只)
        df_zhuli = df[df['zhuli_rank'] <= 200].sort_values('zhuli_rank')
        self._fill_tree(self.tree_zhuli, df_zhuli, ['code', 'name', 'zhuli_rank', 'price', 'change_pct', 'percent', 'win', 'sum_perc', 'net_ratio', 'sector'])
        
        # 2. 更新人气 (显示前 100 只)
        df_hot = df[df['hot_rank'] <= 100].sort_values('hot_rank')
        self._fill_tree(self.tree_hot, df_hot, ['code', 'name', 'hot_rank', 'price', 'change_pct', 'percent', 'win', 'sum_perc', 'hot_tag', 'hot_reason'])
        
        # 3. 更新题材 (有题材标签的个股)
        df_theme = df[(df['theme_name'] != "") & (df['theme_date'] != "")].sort_values(['theme_date', 'hot_rank'], ascending=[False, True])
        self._fill_tree(self.tree_theme, df_theme, ['code', 'name', 'theme_date', 'price', 'change_pct', 'percent', 'win', 'sum_perc', 'theme_name', 'theme_logic'])
        
        # 更新计数器并刷新当前状态栏
        self.counts["主力排名"] = len(df_zhuli)
        self.counts["人气榜单"] = len(df_hot)
        self.counts["题材挖掘"] = len(df_theme)
        self._on_tab_changed(None)
        
        logger.debug(f"Viewer Synced: ZHULI={len(df_zhuli)}, HOT={len(df_hot)}, THEME={len(df_theme)}")

    def _fill_tree(self, tree, df, col_ids):
        """填充 Treeview 并应用格式化"""
        # 清空旧数据
        for item in tree.get_children():
            tree.delete(item)
            
        # 插入新数据
        for _, row in df.iterrows():
            vals = []
            for cid in col_ids:
                val = row.get(cid, "")
                if pd.isna(val): val = ""
                
                if cid in ['net_ratio', 'change_pct', 'price', 'percent', 'win', 'sum_perc']:
                    try:
                        v_num = float(val)
                        if cid == 'win':
                            val = f"{int(v_num)}" if v_num != 0 else "0"
                        elif cid in ['net_ratio', 'change_pct', 'percent', 'sum_perc']:
                            val = f"{v_num:+.2f}" if v_num != 0 else "0.00"
                        elif cid == 'price':
                            val = f"{v_num:.2f}" if v_num > 0 else ""
                    except (ValueError, TypeError):
                        pass
                elif cid in ['zhuli_rank', 'hot_rank']:
                    try:
                        v_num = float(val)
                        val = int(v_num) if v_num < 990 else "-"
                    except:
                        val = "-"
                
                vals.append(val)
            tree.insert("", "end", values=vals)

    def on_close(self):
        save_func = getattr(self.master, 'save_window_position', None)
        if save_func:
            save_func(self, self.window_id)
        self.destroy()
