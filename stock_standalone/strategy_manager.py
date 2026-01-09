# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import logging
import json
import os
import time
from datetime import datetime
from threading import Thread
from typing import Any, Optional, Dict
import pandas as pd
import re

from tk_gui_modules.window_mixin import WindowMixin
from stock_logic_utils import toast_message
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger(name="StrategyManager")

class StrategyManager(tk.Toplevel, WindowMixin):
    """
    交易系统白盒管理工具
    
    功能：
    1. 决策引擎参数动态调整
    2. 风险控制参数管理
    3. 实时数据服务监控
    4. 信号日志实时查看
    5. 单股验证与手动交易
    """
    
    CONFIG_FILE = "strategy_config.json"
    
    def __init__(self, master, live_strategy, realtime_service=None):
        super().__init__(master)
        self.master = master
        self.live_strategy = live_strategy
        self.realtime_service = realtime_service
        
        # 注入 realtime_service 到 live_strategy (为了后台集成)
        if self.live_strategy and self.realtime_service:
            self.live_strategy.realtime_service = self.realtime_service
            
        self.decision_engine = getattr(live_strategy, 'decision_engine', None)
        self.risk_engine = getattr(live_strategy, 'risk_engine', None)
        self.trading_logger = getattr(live_strategy, 'trading_logger', None)
        
        self.title("策略白盒管理器 & 验证工具")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 加载持久化配置
        self.config_data = self._load_config()
        self._apply_config_to_engines()

        self._start_time = time.time()
        self._update_job = None
        
        # 初始化 UI
        self._setup_ui()
        
        # 恢复窗口位置
        self.load_window_position(self, "StrategyManager", default_width=900, default_height=700)
        
        # 启动自动刷新
        self._schedule_refresh()

    def _setup_ui(self):
        # 状态栏 (放在底部)
        self.statusbar = tk.Label(self, text="Ready", bd=1, relief=tk.SUNKEN, anchor="w")
        self.statusbar.pack(side="bottom", fill="x")
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 1: 决策引擎 (Decision Engine)
        self.tab_decision = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_decision, text="🧠 决策引擎")
        self._init_decision_tab()
        
        # Tab 2: 风险控制 (Risk Control)
        self.tab_risk = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_risk, text="🛡️ 风险控制")
        self._init_risk_tab()
        
        # Tab 3: 实时数据 (Realtime Data)
        self.tab_data = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_data, text="📊 实时数据")
        self._init_data_tab()
        
        # Tab 4: 信号日志 (Signal Log)
        self.tab_log = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_log, text="📜 信号日志")
        self._init_log_tab()
        
        # Tab 5: 验证/手操 (Verify & Trade)
        self.tab_verify = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_verify, text="🔧 验证与手操")
        self._init_verify_tab()

    # ------------------- 配置持久化 -------------------
    def _load_config(self) -> Dict:
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载策略配置失败: {e}")
        return {}
        
    def _save_config(self):
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
            logger.info("策略配置已保存")
        except Exception as e:
            logger.error(f"保存策略配置失败: {e}")

    def _apply_config_to_engines(self):
        """应用保存的配置到引擎实例"""
        if not self.config_data:
            return
            
        # 决策引擎参数
        if self.decision_engine:
            de_cfg = self.config_data.get('decision_engine', {})
            for attr, val in de_cfg.items():
                if hasattr(self.decision_engine, attr):
                    setattr(self.decision_engine, attr, float(val))
                    logger.info(f"Restored DecisionEngine.{attr} = {val}")
        
        # 风险引擎参数
        if self.risk_engine:
            re_cfg = self.config_data.get('risk_engine', {})
            for attr, val in re_cfg.items():
                if hasattr(self.risk_engine, attr):
                    setattr(self.risk_engine, attr, float(val))
                    logger.info(f"Restored RiskEngine.{attr} = {val}")

    # ------------------- Tab 1: 决策引擎 -------------------
    def _init_decision_tab(self):
        frame = tk.LabelFrame(self.tab_decision, text="核心参数控制 (修改即时生效)", padx=10, pady=10)
        frame.pack(fill="x", padx=10, pady=10)
        
        self.de_vars = {}
        
        params = [
            ("止损百分比 (stop_loss_pct)", "stop_loss_pct", 0.05, 0.01, 0.20),
            ("止盈百分比 (take_profit_pct)", "take_profit_pct", 0.10, 0.01, 0.50),
            ("移动止盈回撤 (trailing_stop_pct)", "trailing_stop_pct", 0.03, 0.01, 0.10),
            ("最大单股仓位 (max_position)", "max_position", 0.40, 0.10, 1.00)
        ]
        
        for idx, (label_text, attr, default, min_v, max_v) in enumerate(params):
            row = idx
            tk.Label(frame, text=label_text).grid(row=row, column=0, sticky="w", pady=5)
            
            # 获取当前值
            current_val = getattr(self.decision_engine, attr, default) if self.decision_engine else default
            
            var = tk.DoubleVar(value=current_val)
            self.de_vars[attr] = var
            
            # 滑块
            scale = tk.Scale(frame, from_=min_v, to=max_v, resolution=0.01, orient="horizontal", 
                             variable=var, length=200)
            scale.grid(row=row, column=1, padx=10)
            
            # 输入框
            entry = tk.Entry(frame, textvariable=var, width=8)
            entry.grid(row=row, column=2, padx=5)
            
        btn_apply = tk.Button(frame, text="💾 应用并保存决策参数", command=self._apply_decision_params, bg="#e0f7fa")
        btn_apply.grid(row=len(params), column=0, columnspan=3, pady=15, sticky="ew")
        
        # 说明区域
        info_frame = tk.LabelFrame(self.tab_decision, text="策略状态说明", padx=10, pady=10)
        info_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.lbl_de_status = tk.Label(info_frame, text="等待刷新...", justify="left", font=("Consolas", 9))
        self.lbl_de_status.pack(anchor="nw")

    def _apply_decision_params(self):
        if not self.decision_engine:
            return
            
        cfg = {}
        for attr, var in self.de_vars.items():
            val = var.get()
            setattr(self.decision_engine, attr, val)
            cfg[attr] = val
            
        # 更新持有配置
        self.config_data['decision_engine'] = cfg
        self._save_config()
        messagebox.showinfo("成功", "决策引擎参数已更新并保存")
        self._refresh_decision_status()

    def _refresh_decision_status(self):
        if not self.decision_engine:
            return
        
        # 获取一些动态状态如果可能
        de = self.decision_engine
        txt = f"""
        [当前运行参数]
        止损阈值: {de.stop_loss_pct:.1%}
        止盈阈值: {de.take_profit_pct:.1%}
        回撤阈值: {de.trailing_stop_pct:.1%}
        最大仓位: {de.max_position:.1%}
        
        [自适应状态]
        (此处可扩展显示内部状态变量)
        """
        self.lbl_de_status.config(text=txt)

    # ------------------- Tab 2: 风险控制 -------------------
    def _init_risk_tab(self):
        frame = tk.LabelFrame(self.tab_risk, text="风控参数 (修改即时生效)", padx=10, pady=10)
        frame.pack(fill="x", padx=10, pady=10)
        
        self.re_vars = {}
        
        params = [
            ("单股最大仓位 (max_single_stock_ratio)", "max_single_stock_ratio", 0.3, 0.1, 1.0),
            ("最小保留仓位 (min_ratio)", "min_ratio", 0.05, 0.0, 0.2),
            ("报警冷却时间 (alert_cooldown)", "alert_cooldown", 300, 10, 3600), # 特殊处理int
        ]
        
        for idx, (label_text, attr, default, min_v, max_v) in enumerate(params):
            row = idx
            tk.Label(frame, text=label_text).grid(row=row, column=0, sticky="w", pady=5)
            
            target_obj = self.risk_engine if hasattr(self.risk_engine, attr) else self.live_strategy
            current_val = getattr(target_obj, attr, default) if target_obj else default
            
            var = tk.DoubleVar(value=current_val)
            self.re_vars[attr] = var
            
            if attr == "alert_cooldown":
                 scale = tk.Scale(frame, from_=min_v, to=max_v, resolution=10, orient="horizontal", 
                             variable=var, length=200)
            else:
                 scale = tk.Scale(frame, from_=min_v, to=max_v, resolution=0.01, orient="horizontal", 
                             variable=var, length=200)
            scale.grid(row=row, column=1, padx=10)
            
            entry = tk.Entry(frame, textvariable=var, width=8)
            entry.grid(row=row, column=2, padx=5)

        btn_apply = tk.Button(frame, text="💾 应用并保存风控参数", command=self._apply_risk_params, bg="#fff9c4")
        btn_apply.grid(row=len(params), column=0, columnspan=3, pady=15, sticky="ew")

        # 风险状态列表
        list_frame = tk.LabelFrame(self.tab_risk, text="当前风险状态监控", padx=5, pady=5)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        cols = ("code", "name", "risk_state", "cooldown")
        self.tree_risk = ttk.Treeview(list_frame, columns=cols, show="headings", height=10)
        self.tree_risk.heading("code", text="代码")
        self.tree_risk.heading("name", text="名称")
        self.tree_risk.heading("risk_state", text="风险状态")
        self.tree_risk.heading("cooldown", text="冷却倒计时")
        self.tree_risk.column("code", width=80)
        self.tree_risk.column("name", width=100)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree_risk.yview)
        self.tree_risk.configure(yscroll=scrollbar.set)
        self.tree_risk.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    def _apply_risk_params(self):
        cfg = {}
        for attr, var in self.re_vars.items():
            val = var.get()
            
            # 分发到不同对象
            if self.risk_engine and hasattr(self.risk_engine, attr):
                setattr(self.risk_engine, attr, val)
                
            if self.live_strategy and hasattr(self.live_strategy, attr):
                 setattr(self.live_strategy, attr, val)
                 if attr == 'alert_cooldown':
                     self.live_strategy.set_alert_cooldown(val)

            cfg[attr] = val
            
        self.config_data['risk_engine'] = cfg
        self._save_config()
        messagebox.showinfo("成功", "风控参数已更新并保存")
        
    def _refresh_risk_list(self):
        if not self.risk_engine: return
        
        # 清空
        for item in self.tree_risk.get_children():
            self.tree_risk.delete(item)
            
        # 暂时 RiskEngine 没有公开获取所有风险状态的接口，
        # 假设我们可以访问 _last_alert_time (需修改 RiskEngine 或访问私有成员)
        # 这里演示访问 live_strategy monitors
        monitors = self.live_strategy.get_monitors()
        now = time.time()
        cooldown = self.live_strategy.get_alert_cooldown()
        
        for code, data in monitors.items():
            last_alert = data.get('last_alert', 0)
            diff = now - last_alert
            remaining = max(0, cooldown - diff)
            
            if remaining > 0:
                self.tree_risk.insert("", "end", values=(
                    code, data['name'], "冷却中", f"{remaining:.0f}s"
                ))

        # [New] 从 RiskEngine 获取更多状态
        # 1. 实时风控状态 (连续低于均价/昨日收盘)
        if self.live_strategy:
             # 遍历监控中的股票
             monitors = self.live_strategy.get_monitors()
             for code, data in monitors.items():
                 name = data['name']
                 
                 # 1.1 检查 RiskEngine 状态
                 if self.risk_engine:
                     r_state = self.risk_engine.get_risk_state(code)
                     # below_nclose_count
                     bn_count = r_state.get('below_nclose_count', 0)
                     if bn_count > 0:
                         self.tree_risk.insert("", "end", values=(
                             code, name, f"低于均价 {bn_count}次", "--"
                         ))
                     
                     # below_last_close_count
                     bl_count = r_state.get('below_last_close_count', 0)
                     if bl_count > 0:
                          self.tree_risk.insert("", "end", values=(
                             code, name, f"低于昨收 {bl_count}次", "--"
                         ))

                 # 1.2 检查历史连亏 (Pain System)
                 if self.trading_logger:
                     loss_count = self.trading_logger.get_consecutive_losses(code)
                     if loss_count > 0:
                         tag = "连亏警告" if loss_count == 1 else "黑名单(连亏)"
                         self.tree_risk.insert("", "end", values=(
                             code, name, f"{tag} {loss_count}次", "--"
                         ))

    # ------------------- Tab 3: 实时数据 -------------------
    def _init_data_tab(self):
        # 顶部统计 & 控制区
        stat_frame = tk.Frame(self.tab_data)
        stat_frame.pack(fill="x", padx=10, pady=5)
        
        self.lbl_rt_stats = tk.Label(stat_frame, text="实时服务状态连接中...", font=("Arial", 10, "bold"))
        self.lbl_rt_stats.pack(side="left")
        
        # --- 增强控制 ---
        ctrl_frame = tk.Frame(stat_frame)
        ctrl_frame.pack(side="left", fill="x", expand=True)
        
        # 1. 统计周期
        saved_period = self.config_data.get('stat_period', "10")
        tk.Label(ctrl_frame, text="统计周期(分):").pack(side="left", padx=2)
        self.var_stat_period = tk.StringVar(value=str(saved_period))
        self.ent_period = tk.Entry(ctrl_frame, textvariable=self.var_stat_period, width=3)
        self.ent_period.pack(side="left", padx=2)
        
        # 2. 高级过滤
        tk.Label(ctrl_frame, text="过滤:").pack(side="left", padx=5)
        
        # 删除按钮 (先 pack 到右侧，避免阻挡 combo 扩展)
        tk.Button(ctrl_frame, text="✖", width=2, command=self._delete_current_filter).pack(side="right", padx=2)
        
        self.combo_filter = ttk.Combobox(ctrl_frame, width=25)
        self.combo_filter.pack(side="left", padx=2, fill="x", expand=True)
        
        default_filters = [
            "",
            "score > 80", 
            "score < 20",
            "diff > 5", 
            "diff < -5",
            "volume > 500000",
            "score > 60 and diff > 3",
            "20 < score < 80 and volume > 10000"
        ]
        # 加载历史
        saved_history = self.config_data.get('filter_history', [])
        # 合并并去重，保持顺序 (saved first or default first? usually saved history implies user preference)
        # Let's align with user request: 'automatic load'
        # Combine: saved_history + default_filters, removing duplicates
        combined = []
        seen = set()
        for f in saved_history + default_filters:
            if f not in seen:
                combined.append(f)
                seen.add(f)
        
        self.combo_filter['values'] = combined
        
        # 恢复上次选中的过滤
        last_filter = self.config_data.get('last_filter', "")
        if last_filter in combined:
            self.combo_filter.set(last_filter)
        elif last_filter:
            self.combo_filter.set(last_filter) # even if not in history, set it
            
        # 回车应用过滤
        self.combo_filter.bind('<Return>', lambda e: self._refresh_data_tab())
        
        # 情绪分数表
        list_frame = tk.LabelFrame(self.tab_data, text="实时情绪分数监控", padx=5, pady=5)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        cols = ("code", "name", "score", "diff", "baseline", "status", "time", "vol_ratio")
        self.tree_data = ttk.Treeview(list_frame, columns=cols, show="headings")
        self.tree_data.heading("code", text="代码", command=lambda: self._sort_tree_data("code", False))
        self.tree_data.heading("name", text="名称", command=lambda: self._sort_tree_data("name", False))
        self.tree_data.heading("score", text="情绪分", command=lambda: self._sort_tree_data("score", True))
        self.tree_data.heading("diff", text="变化", command=lambda: self._sort_tree_data("diff", True))
        self.tree_data.heading("baseline", text="基准", command=lambda: self._sort_tree_data("baseline", True))
        self.tree_data.heading("status", text="形态", command=lambda: self._sort_tree_data("status", False))
        self.tree_data.heading("time", text="时间", command=lambda: self._sort_tree_data("time", True))
        self.tree_data.heading("vol_ratio", text="成交量", command=lambda: self._sort_tree_data("vol_ratio", True))
        
        self.tree_data.column("code", width=60, anchor="center")
        self.tree_data.column("name", width=70, anchor="center")
        self.tree_data.column("score", width=60, anchor="center")
        self.tree_data.column("diff", width=50, anchor="center")
        self.tree_data.column("baseline", width=50, anchor="center")
        self.tree_data.column("status", width=100, anchor="center")
        self.tree_data.column("time", width=80, anchor="center")
        self.tree_data.column("vol_ratio", width=80, anchor="center")

        self.tree_data.pack(fill="both", expand=True)

        # 排序状态
        self._data_sort_col = "score"
        self._data_sort_reverse = True

        # 绑定事件
        # 绑定事件
        self.tree_data.bind("<ButtonRelease-1>", self.on_data_tree_click)
        self.tree_data.bind("<Double-1>", self.on_data_tree_dblclick)
        self.tree_data.bind("<Button-3>", self.on_data_tree_rclick)
        self.tree_data.bind("<KeyRelease-Up>", self.on_data_tree_key_nav)
        self.tree_data.bind("<KeyRelease-Down>", self.on_data_tree_key_nav)
        
        # 初始触发一次刷新 (延迟以便UI就绪)
        self.after(500, self._refresh_data_tab)

    def on_data_tree_key_nav(self, event):
        """键盘上下键联动"""
        sel = self.tree_data.selection()
        if sel:
            self._try_link_stock(sel[0])

    def _try_link_stock(self, item):
        """发送联动信号"""
        values = self.tree_data.item(item, 'values')
        if values:
            code = values[0]
            if hasattr(self.master, 'sender') and self.master.sender:
                self.master.sender.send(str(code))

    def on_data_tree_click(self, event):
        """左键联动通达信"""
        item = self.tree_data.identify_row(event.y)
        if not item: return
        self._try_link_stock(item)

    def on_data_tree_dblclick(self, event):
        """双击事件: 
        1. 双击 Code -> 复制到剪贴板
        2. 双击 Score -> 添加到语音报警监控
        """
        item = self.tree_data.identify_row(event.y)
        if not item: return
        
        values = self.tree_data.item(item, 'values')
        if not values: return
        
        code = str(values[0])
        name = str(values[1])
        score = values[2] # current score
        
        # 识别点击的列
        col_id = self.tree_data.identify_column(event.x)
        # Treeview 列定义: ("code", "name", "score", "diff", "time", "vol_ratio")
        # #1=code, #2=name, #3=score, ...
        
        if col_id == "#1" or col_id == "#2": # Code or Name -> Copy Code
            self.clipboard_clear()
            self.clipboard_append(code)
            self.update() # keep clipboard
            self.statusbar.config(text=f"已复制: {code}")
            toast_message(self, f"股票代码 {code} 已复制到剪贴板")
            
        elif col_id == "#3": # Score -> Add Monitor
            # Default rule: Score > Current (or just add to list)
            # 用户需求是"添加到语音报警"，这里默认添加一个高分预警与低分预警，或者手动关注
            # 为了简单直接，我们添加一个 "手动关注" 的 Tag，规则设为 score > 0 (总是触发??) 
            # 或者弹出对话框？
            # 鉴于"双击"的便捷性，我们直接添加一个默认监控：Score > 80 (或者当前分数)
            
            try:
                # 默认添加一个 关注 规则
                # 使用 value=0 作为一个标记，或者使用当前 score
                self.live_strategy.add_monitor(code, name, "score_up", 80.0, tags="手动关注")
                self.statusbar.config(text=f"已添加监控: {code} {name}")
                toast_message(self, f"已将 {name}({code}) 添加到语音报警列表\n默认规则: 情绪分 > 80")
            except Exception as e:
                toast_message(self,f"添加监控失败: {e}")
                logger.info(f"添加监控失败: {e}")

    def on_data_tree_rclick(self, event):
        """右键自动滚动主视图"""
        item = self.tree_data.identify_row(event.y)
        if not item: return
        self.tree_data.selection_set(item)
        values = self.tree_data.item(item, 'values')
        if not values: return
        
        code = str(values[0])
        self._scroll_master_tree_to_code(code)

    def _scroll_master_tree_to_code(self, code):
        """滚动主程序的 Treeview 到指定代码"""
        if not hasattr(self.master, 'tree'): return
        
        # 遍历查找
        found = False
        for item in self.master.tree.get_children():
            val = self.master.tree.item(item, 'values')
            if val and str(val[0]) == code:
                self.master.tree.see(item)
                self.master.tree.selection_set(item)
                self.master.tree.focus(item)
                found = True
                break
        
        if not found:
            # logger.info(f"主视图 Treeview 中未找到代码 {code} (可能被过滤)")
            toast_message(self,f"主视图 Treeview 中未找到代码 {code} (可能被过滤)")

    def _sort_tree_data(self, col, reverse):
        """更新排序状态并触发刷新"""
        self._data_sort_col = col
        self._data_sort_reverse = reverse
        
        # 更新表头回调，以便下次反转
        self.tree_data.heading(col, command=lambda: self._sort_tree_data(col, not reverse))
        
        # 立即刷新显示
        self._refresh_data_tab()

    def _refresh_data_tab(self):
        # 1. 性能优化：如果该 Tab 不可见，则跳过 UI 刷新计算
        # 注意：self.notebook.select() 返回的是 widget name
        try:
             current_tab = self.notebook.select()
             if str(current_tab) != str(self.tab_data):
                 return
        except:
             pass

        if not self.realtime_service:
            self.lbl_rt_stats.config(text="连接中/服务离线")
            return
            
        # 刷新统计
        cache_size = 0
        if hasattr(self.realtime_service, 'kl_cache'):
            cache_size = len(self.realtime_service.kl_cache)
            
        self.lbl_rt_stats.config(text=f"K线缓存对象数: {cache_size}")
        
        # --- 智能刷新列表 ---
        
        # --- 智能刷新列表 ---
        
        # --- 智能刷新列表 (Pandas Vectorized Optimization) ---
        
        if not hasattr(self.realtime_service, 'emotion_tracker'):
            return

        scores = self.realtime_service.emotion_tracker.scores
        if not scores:
            return

        # 1. 转换为 DataFrame (比循环快得多)
        # scores is {code: score}
        try:
            df_temp = pd.DataFrame(index=scores.keys(), data=scores.values(), columns=['score'])
            df_temp.index.name = 'code'
        except Exception as e:
            logger.error(f"构建 DataFrame 失败: {e}")
            return

        # 2. 批量关联 Name 和 Volume
        df_all = getattr(self.master, 'df_all', None)
        if df_all is not None:
            # 仅选取需要的列，并确保类型匹配
            # 假设 df_all.index 是 code
            try:
                # 使用 reindex/join 远快于逐行 loc
                # 注意：这里假设此处的 code 和 df_all.index 格式一致（都是 str 6位代码）
                cols_needed = [c for c in ['name', 'volume'] if c in df_all.columns]
                if cols_needed:
                    # 使用 join 或 merge
                    # 如果 df_all 很大，reindex 可能内存占用高，join intersection 更好
                    # df_subset = df_all.loc[df_all.index.intersection(df_temp.index), cols_needed]
                    # df_temp = df_temp.join(df_subset)
                    # 简单方式（pandas 内部会优化索引对齐）:
                    df_temp = df_temp.join(df_all[cols_needed])
            except Exception as e:
                logger.error(f"关联主数据失败: {e}")
        
        # 填充缺失值
        if 'name' not in df_temp.columns: df_temp['name'] = '--'
        if 'volume' not in df_temp.columns: df_temp['volume'] = 0
        
        df_temp['name'] = df_temp['name'].fillna('--')
        df_temp['volume'] = df_temp['volume'].fillna(0)
        
        # 2.5 增加差值统计
        try:
            period = int(self.var_stat_period.get())
        except:
            period = 10
            
        # --- 自动保存配置 (Check if changed) ---
        # 注意: 这里虽然是每秒刷新，但只有值变化时才写文件，IO影响较小
        changed = False
        current_period_str = str(period)
        saved_period_str = str(self.config_data.get('stat_period', "10"))
        if current_period_str != saved_period_str:
            self.config_data['stat_period'] = current_period_str
            changed = True
            
        current_filter = self.combo_filter.get().strip()
        saved_filter = self.config_data.get('last_filter', "")
        
        if current_filter != saved_filter:
            self.config_data['last_filter'] = current_filter
            changed = True
            
        # 更新 Filter History (如果有效且不在历史中)
        if current_filter:
            history = self.config_data.get('filter_history', [])
            if current_filter not in history:
                history.insert(0, current_filter) # add to top
                if len(history) > 20: history = history[:20]
                self.config_data['filter_history'] = history
                # Update combo values immediately
                current_values = list(self.combo_filter['values'])
                if current_filter not in current_values:
                    current_values.insert(0, current_filter)
                    self.combo_filter['values'] = current_values
                changed = True
        
        if changed:
            self._save_config()
        # --------------------------------------
            
        # 2.5 增加差值统计
        try:
            period = int(self.var_stat_period.get())
        except:
            period = 10
            
        diffs = self.realtime_service.emotion_tracker.get_score_diffs(period)
        s_diffs = pd.Series(diffs)
        df_temp['diff'] = s_diffs
        df_temp['diff'] = df_temp['diff'].fillna(0.0)

        # 2.6 [New] 增加 Baseline 和 Status
        if hasattr(self.realtime_service, 'emotion_baseline'):
             baselines = self.realtime_service.emotion_baseline.get_all_baselines()
             details = self.realtime_service.emotion_baseline.get_all_baseline_details()
             
             df_temp['baseline'] = pd.Series(baselines)
             df_temp['status'] = pd.Series(details)
             
             df_temp['baseline'] = df_temp['baseline'].fillna(50.0)
             df_temp['status'] = df_temp['status'].fillna('')

        # 2.6 应用高级过滤
        filter_expr = self.combo_filter.get().strip()
        if filter_expr:
            try:
                if df_all is not None:
                     # 策略优化：仅 join 过滤表达式中用到的列 Isolate only used columns
                     # 简单的正则提取标识符
                     import re
                     # 提取所有单词作为潜在列名
                     tokens = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', filter_expr))
                     
                     cols_in_temp = set(df_temp.columns)
                     # 找出 df_all 中存在且 filter_expr 中用到，但 df_temp 尚未包含的列
                     cols_to_add = [c for c in df_all.columns if c in tokens and c not in cols_in_temp]
                     
                     if cols_to_add:
                         df_temp = df_temp.join(df_all[cols_to_add])
                
                df_temp = df_temp.query(filter_expr)
                
            except Exception as e:
                # 过滤失败显示在状态栏
                err_msg = str(e)
                if "not found" in err_msg:
                    self.lbl_rt_stats.config(text=f"过滤错误: 字段未找到 ({err_msg})", fg="red")
                else:
                    self.lbl_rt_stats.config(text=f"过滤错误: {err_msg}", fg="red")
                
                # Console debug
                print(f"[Filter Error]Query: {filter_expr}")
                print(f"[Filter Error]Available columns: {list(df_temp.columns)}")
                return # 停止后续处理

        # 3. 排序 (Pandas Native Sort)
        sort_col = self._data_sort_col
        # 映射 Treeview 列名到 DataFrame 列名
        col_map = {'vol_ratio': 'volume'} # vol_ratio 列显示的是 volume
        df_sort_col = col_map.get(sort_col, sort_col)
        
        ascending = not self._data_sort_reverse
        
        if df_sort_col in df_temp.columns:
            try:
                # 确保排序列是数值型以便正确排序
                if df_sort_col in ['score', 'volume', 'diff']:
                    df_temp[df_sort_col] = pd.to_numeric(df_temp[df_sort_col], errors='coerce').fillna(0)
                    
                df_temp.sort_values(by=df_sort_col, ascending=ascending, inplace=True)
            except Exception as e:
                logger.error(f"排序失败: {e}")

        # 4. 截取 Top 100 (大幅减少后续处理量)
        total_count = len(df_temp)
        display_count = min(total_count, 100)
        df_display = df_temp.head(100)
        
        # 更新底部状态栏
        filtered_count = total_count # if filtered
        # Check if we filtered 
        # Actually total_count here IS the filtered count because we applied query above
        # To get true total, we might need pre-filter count, but that's expensive to track separaterly if we don't need to.
        # But wait, df_temp started as all scores. 
        # So:
        # 1. df_original = from scores
        # 2. df_temp = df_original.query(...)
        # So len(scores) is Total/Scanned, len(df_temp) is Filtered.
        
        monitor_count = len(self.live_strategy.get_monitors()) if self.live_strategy else 0
        self.statusbar.config(text=f"监控池: {len(scores)} | 过滤后: {total_count} | 显示: {display_count} | 活跃策略: {monitor_count}")
        
        # 5. 构建显示数据 (仅处理 100 条，极快)
        
        # 5. 构建显示数据 (仅处理 100 条，极快)
        display_list = []
        
        kl_cache_ts = {}
        if self.realtime_service and hasattr(self.realtime_service, 'kl_cache'):
            kl_cache_ts = self.realtime_service.kl_cache.last_update_ts

        for code, row in df_display.iterrows():
            code = str(code) # ensure str
            
            # Name
            name = str(row['name'])
            
            # Score
            score = float(row['score'])
            
            # Diff
            diff_val = row.get('diff', 0.0)
            
            # Volume Formatting
            vol_val = row['volume']
            volume_str = '--'
            try:
                v = float(vol_val)
                if v > 10000:
                    volume_str = f"{v/10000:.1f}万"
                else:
                    volume_str = str(int(v))
            except:
                volume_str = str(vol_val)

            # Time Formatting
            time_str = '--'
            ts = kl_cache_ts.get(code, 0)
            if ts > 0:
                time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")

            # Baseline & Status
            baseline = float(row.get('baseline', 50.0))
            status = str(row.get('status', ''))

            display_list.append({
                'code': code,
                'name': name,
                'score': score,
                'diff': diff_val,
                'baseline': baseline,
                'status': status,
                'time': time_str,
                'vol_ratio': volume_str
            })
        display_codes = [x['code'] for x in display_list]
        
        # 3. 保存状态 (选中项 & 滚动位置)
        selected_items = self.tree_data.selection() # iid list
        # 假设 iid 就是 code，如果不是则需要映射。
        # 下面我们强制 insert 时 iid=code
        
        # 4. 更新/插入/移动
        # cache existing iids
        existing_iids = set(self.tree_data.get_children())
        
        for index, item_data in enumerate(display_list):
            code = item_data['code']
            values = (
                code, 
                item_data['name'], 
                f"{item_data['score']:.1f}",
                f"{item_data['diff']:+.1f}",
                f"{item_data['baseline']:.1f}",
                item_data['status'],
                item_data['time'], 
                item_data['vol_ratio']
            )
            
            if code in existing_iids:
                # 更新
                self.tree_data.item(code, values=values)
                # 移动到正确位置 (如果顺序不对)
                # move 比较耗时，仅在索引不匹配时操作？
                # 或者无脑 move，Python list iterator 顺序即为正确顺序
                # get_children 返回的是当前顺序
                # 为了简单逻辑，直接 move (Tkinter move is O(1) internally relative to siblings?)
                # 优化: 只有当 current index != desired index 时才 move 吗？
                # 但 get_children 是 O(N)。
                # 简单做法：直接 move 到 index 'end' 也是一种策略，由于我们是按顺序 iterate，
                # 我们可以 move 到 index `index`。
                
                # Check current position? To optimize visuals.
                # Actually, simply 'move' call is fast enough for 100 items.
                self.tree_data.move(code, '', index)
            else:
                # 插入
                self.tree_data.insert("", index, iid=code, values=values)
                
        # 5. 清理不再显示的
        for iid in existing_iids:
            if iid not in display_codes:
                self.tree_data.delete(iid)
                
        # 6. 恢复选中 (如果还在)
        valid_selection = [s for s in selected_items if self.tree_data.exists(s)]
        if valid_selection:
            self.tree_data.selection_set(valid_selection)

    # ------------------- Tab 4: 信号日志 -------------------
    def _init_log_tab(self):
        # 简单实现：读取 logging 的内存 buffer 或者 tail log file?
        # 为了高效，这里建议只挂钩 self.live_strategy 的最近决策记录
        
        tk.Label(self.tab_log, text="最近生成的策略决策信号 (Live)", font=("Arial", 10)).pack(anchor="w", padx=10, pady=5)
        
        cols = ("time", "code", "name", "action", "pos", "reason")
        self.tree_log = ttk.Treeview(self.tab_log, columns=cols, show="headings")
        self.tree_log.heading("time", text="时间")
        self.tree_log.heading("code", text="代码")
        self.tree_log.heading("name", text="名称")
        self.tree_log.heading("action", text="动作")
        self.tree_log.heading("pos", text="仓位")
        self.tree_log.heading("reason", text="理由")
        
        self.tree_log.column("time", width=120)
        self.tree_log.column("code", width=80)
        self.tree_log.column("name", width=80)
        self.tree_log.column("action", width=60)
        self.tree_log.column("pos", width=60)
        self.tree_log.column("reason", width=400)
        
        self.tree_log.pack(fill="both", expand=True, padx=10, pady=5)

        # 绑定事件 (Linkage)
        self.tree_log.bind("<ButtonRelease-1>", self.on_log_tree_click)
        self.tree_log.bind("<KeyRelease-Up>", self.on_log_tree_key_nav)
        self.tree_log.bind("<KeyRelease-Down>", self.on_log_tree_key_nav)

    def on_log_tree_key_nav(self, event):
        """键盘上下键联动"""
        sel = self.tree_log.selection()
        if sel:
            self._try_link_stock_log(sel[0])

    def on_log_tree_click(self, event):
        """左键联动通达信"""
        item = self.tree_log.identify_row(event.y)
        if not item: return
        self._try_link_stock_log(item)

    def _try_link_stock_log(self, item):
        """发送联动信号 (Log专用)"""
        values = self.tree_log.item(item, 'values')
        if values:
            # Treeview columns: ("time", "code", "name", "action", "pos", "reason")
            # Index 1 is code
            code = values[1]
            if hasattr(self.master, 'sender') and self.master.sender:
                self.master.sender.send(str(code))

    def _refresh_signal_logs(self):
        """自动刷新信号日志"""
        # 1. 如果 Tab 不可见，跳过
        try:
             current_tab = self.notebook.select()
             if str(current_tab) != str(self.tab_log):
                 return
        except:
             pass

        # 2. 从 TradingLogger (DB) 读取今日信号
        if not self.trading_logger:
            return
            
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            # 增量读取优化？目前简单点，读取今日所有，然后覆盖显示
            # 或者仅读取最近 N 条
            signals = self.trading_logger.get_signals(start_date=today)
            if not signals:
                return

            # 3. 准备数据
            # 仅取前 100 条显示
            display_signals = signals[:100]

            # 4. 保存选中状态
            selected_items = self.tree_log.selection()
            selected_keys = set()
            
            if selected_items:
                for iid in selected_items:
                    v = self.tree_log.item(iid, 'values')
                    if v:
                        # key = time_str + code
                        selected_keys.add(str(v[0]) + str(v[1]))

            # 5. 更新 Treeview
            for item in self.tree_log.get_children():
                self.tree_log.delete(item)
                
            for s in display_signals:
                try:
                    ts = s.get('created_at', s.get('date', ''))
                    code = s['code']
                    reason = s['reason']
                    
                    values=(
                        ts, 
                        s['code'], 
                        s['name'], 
                        s['action'], 
                        f"{s.get('position', 0)}", 
                        reason
                    )
                    
                    new_item = self.tree_log.insert("", "end", values=values)
                    
                    # 检查是否需要恢复选中
                    key = str(ts) + str(code)
                    if key in selected_keys:
                        self.tree_log.selection_add(new_item)
                        # 确保可见
                        self.tree_log.see(new_item)
                        
                except Exception as e:
                    logger.error(f"Log row error: {e}")

        except Exception as e:
            logger.error(f"刷新信号日志失败: {e}")

    def log_signal(self, log_entry: dict):
        """外部调用接口：记录新的信号"""
        # 兼容旧接口，但也触发刷新
        self._refresh_signal_logs()

    def _delete_current_filter(self):
        """删除当前选中的过滤记录"""
        current = self.combo_filter.get().strip()
        if not current: return
        
        # 更新历史列表
        history = self.config_data.get('filter_history', [])
        if current in history:
            history.remove(current)
            self.config_data['filter_history'] = history
            self._save_config()
            
        # 更新 UI values (需保留 default)
        default_filters = [
            "",
            "score > 80", 
            "score < 20",
            "diff > 5", 
            "diff < -5",
            "volume > 500000",
            "score > 60 and diff > 3",
            "20 < score < 80 and volume > 10000"
        ] # 需要与 _init 保持一致，最好提取为类常量
        
        # 重新构建 combined
        combined = []
        seen = set()
        for f in history + default_filters:
            if f not in seen:
                combined.append(f)
                seen.add(f)
        
        self.combo_filter['values'] = combined
        self.combo_filter.set("") # 清空当前
        self._refresh_data_tab() # 刷新

    # ------------------- Tab 5: 验证/手操 -------------------
    def _init_verify_tab(self):
        paned = tk.PanedWindow(self.tab_verify, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 左侧：验证区
        frame_verify = tk.LabelFrame(paned, text="单股策略验证 (Verify)", padx=5, pady=5)
        paned.add(frame_verify, width=400)
        
        f1 = tk.Frame(frame_verify)
        f1.pack(fill="x")
        tk.Label(f1, text="代码:").pack(side="left")
        self.entry_verify_code = tk.Entry(f1, width=10)
        self.entry_verify_code.pack(side="left", padx=5)
        tk.Button(f1, text="执行评估", command=self._do_verify_stock).pack(side="left")
        
        self.txt_verify_result = tk.Text(frame_verify, height=20, width=50, font=("Consolas", 9))
        self.txt_verify_result.pack(fill="both", expand=True, pady=5)
        
        # 右侧：手操区
        frame_trade = tk.LabelFrame(paned, text="手动交易干预 (Manual Trade)", padx=5, pady=5)
        paned.add(frame_trade)
        
        tk.Label(frame_trade, text="⚠️ 警告: 此处操作将直接记录并在下个周期生效", fg="red").pack(pady=5)
        
        f2 = tk.Frame(frame_trade)
        f2.pack(fill="x", pady=5)
        tk.Label(f2, text="代码:").grid(row=0, column=0)
        self.entry_trade_code = tk.Entry(f2, width=10)
        self.entry_trade_code.grid(row=0, column=1, padx=5)
        
        tk.Label(f2, text="价格:").grid(row=1, column=0)
        self.entry_trade_price = tk.Entry(f2, width=10)
        self.entry_trade_price.grid(row=1, column=1, padx=5)
        
        tk.Label(f2, text="数量:").grid(row=2, column=0)
        self.entry_trade_amount = tk.Entry(f2, width=10)
        self.entry_trade_amount.grid(row=2, column=1, padx=5)
        
        tk.Button(frame_trade, text="🔴 买入记录", bg="#ffcdd2", 
                  command=lambda: self._do_manual_trade('BUY')).pack(fill="x", pady=5)
        tk.Button(frame_trade, text="🟢 卖出记录", bg="#c8e6c9", 
                  command=lambda: self._do_manual_trade('SELL')).pack(fill="x", pady=5)

    def set_verify_code(self, code):
        """外部调用：设置验证代码"""
        if code:
            self.entry_verify_code.delete(0, "end")
            self.entry_verify_code.insert(0, code)
            self.entry_trade_code.delete(0, "end")
            self.entry_trade_code.insert(0, code)
            self._do_verify_stock()

    def _do_verify_stock(self):
        code = self.entry_verify_code.get().strip()
        if not code: return
        
        self.txt_verify_result.delete("1.0", "end")
        
        # 尝试从 master 获取数据
        df_all = getattr(self.master, 'df_all', None)
        if df_all is None or df_all.empty:
            self.txt_verify_result.insert("end", "错误: 主程序 df_all 为空，无法评估。\n")
            return
            
        try:
            if code not in df_all.index:
                 self.txt_verify_result.insert("end", f"错误: 代码 {code} 不在当前的 df_all 中。\n")
                 return
                 
            row = df_all.loc[code].to_dict()
            row['code'] = code # ensure code exists
            
            # 构造 snapshot (尝试从 monitors 取，没有则构造空的)
            monitors = self.live_strategy.get_monitors()
            snapshot = {}
            if code in monitors:
                snapshot = monitors[code].get('snapshot', {})
            else:
                # 尝试从 row 构造基础 snapshot
                snapshot = {
                    'last_close': row.get('lastp1d', 0),
                    'nclose': row.get('nclose', 0)
                }
            
            # 调用 decision engine
            result = self.decision_engine.evaluate(row, snapshot, mode="full")
            
            # 美化输出
            output = f"=== 评估报告: {code} ===\n"
            output += f"时间: {datetime.now().strftime('%H:%M:%S')}\n"
            
            # --- 集成实时数据展示 ---
            score = 0
            diff = 0
            if self.realtime_service and hasattr(self.realtime_service, 'emotion_tracker'):
                score = self.realtime_service.emotion_tracker.get_score(code)
                diffs = self.realtime_service.emotion_tracker.get_score_diffs(minutes=10) # 默认10分钟
                diff = diffs.get(code, 0)
                
            output += f"价格: {row.get('trade')} (涨幅 {row.get('percent')}%) \n"
            output += f"情绪: {score:.1f} (10分变化: {diff:+.1f})\n"
            output += "-" * 30 + "\n"
            output += f"【决策】: {result.get('action')} (仓位 {result.get('position')})\n"
            output += f"【理由】: {result.get('reason')}\n"
            output += "-" * 30 + "\n"
            output += "[Debug Info]:\n"
            
            debug = result.get('debug', {})
            for k, v in debug.items():
                output += f"  {k}: {v}\n"
                
            self.txt_verify_result.insert("end", output)
            
        except Exception as e:
             self.txt_verify_result.insert("end", f"评估异常: {e}\n")
             import traceback
             self.txt_verify_result.insert("end", traceback.format_exc())

    def _do_manual_trade(self, action):
        code = self.entry_trade_code.get().strip()
        try:
            price = float(self.entry_trade_price.get())
            amount = int(self.entry_trade_amount.get())
        except ValueError:
            messagebox.showerror("错误", "价格或数量格式不正确")
            return
            
        if not code: return
        
        if not messagebox.askyesno("确认", f"确定要手动记录 {action} {code} {amount}股 @ {price} 吗？\n这将影响持仓计算。"):
            return
            
        # 调用 logger
        try:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 简单模拟 name
            name = "手动操作"
            # 尝试获取真名
            df_all = getattr(self.master, 'df_all', None)
            if df_all is not None and code in df_all.index:
                name = df_all.loc[code].get('name', '手动操作')
                
            action_map = {'BUY': '买入', 'SELL': '卖出'}
            act_str = action_map.get(action, action)
            
            self.trading_logger.record_trade(code, name, act_str, price, amount)
            messagebox.showinfo("成功", f"交易记录已保存。")
            
            # 尝试刷新主程序监控状态
            if action == 'SELL' and hasattr(self.live_strategy, 'remove_monitor'):
                 # 如果完全卖出，询问是否移除监控
                 if messagebox.askyesno("提示", "是否从监控列表中移除此股票？"):
                     self.live_strategy.remove_monitor(code)
            
        except Exception as e:
            messagebox.showerror("异常", f"记录失败: {e}")

    # ------------------- 通用 -------------------
    def _schedule_refresh(self):
        if not self.winfo_exists(): return
        
        # 刷新 Decision Tab
        self._refresh_decision_status()
        
        # 刷新 Risk List
        self._refresh_risk_list()
        
        # 刷新 Realtime Tab
        self._refresh_data_tab()
        
        # 10秒刷新一次 (降低频率以减轻卡顿)
        # 刷新 Signal Logs
        self._refresh_signal_logs()

        # 5秒刷新一次 (提高日志实时性)
        self._update_job = self.after(5000, self._schedule_refresh)

    def on_close(self):
        self.save_window_position(self, "StrategyManager")
        self.destroy()

if __name__ == "__main__":
    import sys
    import os
    # Ensure project root is in path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(project_root)

    try:
        from data_utils import tdd
        from JohnsonUtil import commonTips as cct
        from JohnsonUtil import johnson_cons as ct
    except ImportError as e:
        print(f"Module import failed: {e}. Please run in project environment.")
        sys.exit(1)

    # --- Benchmark / Timer ---
    t_start = time.time()

    # --- Mock / Minimal Implementation of dependencies ---
    class MockRiskEngine:
        def get_risk_state(self, code):
            # Return dummy risk state
            return {'below_nclose_count': 0, 'below_last_close_count': 0}

    class MockTradingLogger:
        def get_consecutive_losses(self, code):
            return 0
        def get_signals(self, start_date=None):
            # Return some dummy signals
            return [
                {'code': '000001', 'name': '平安银行', 'action': 'BUY', 'position': 100, 'reason': 'Test Signal', 'created_at': '10:00:00', 'date': '2025-01-01'},
                {'code': '600519', 'name': '贵州茅台', 'action': 'SELL', 'position': 0, 'reason': 'Stop Loss', 'created_at': '11:30:00', 'date': '2025-01-01'}
            ]

    class MockEmotionBaseline:
        def get_all_baselines(self):
            return {}
        def get_all_baseline_details(self):
            return {}

    class MockRealtimeService:
        def __init__(self):
            self.emotion_baseline = MockEmotionBaseline()

    class MockSender:
        def send(self, msg):
            print(f"MockSender: {msg}")

    class MockLiveStrategy:
        def __init__(self):
            self.monitors = {}
            self.risk_engine = MockRiskEngine()
            self.trading_logger = MockTradingLogger()
            self.decision_engine = None
            self.realtime_service = None
            self.sender = MockSender()

        def get_monitors(self):
            return self.monitors
            
        def get_alert_cooldown(self):
            # Return configured cooldown period (seconds)
            return 60

    def main():
        root = tk.Tk()
        # root.geometry("800x600")
        
        # 1. Setup Data & Strategy
        live_strategy = MockLiveStrategy()
        realtime_service = MockRealtimeService()
        
        # 2. Fetch Sample Data
        print("Fetching sample data from Sina via data_utils (tdx_data_Day)...")
        try:
            # Try fetching a small set of market codes for test
            # market_arg = ['sh600519', 'sz000001', 'sz002594'] 
            # Note: tdd.getSinaAlldf expects just the code numbers if using list, 
            # but usually it auto-prefixes. Let's provide numbers.
            test_codes = ['600519', '000001', '002594', '300750', '601127', '002475']
            df = tdd.getSinaAlldf(market=test_codes, vol=ct.json_countVol, vtype=ct.json_countType)
            
            if not df.empty:
                print(f"Fetched {len(df)} records. Columns: {df.columns.tolist()}")
                if 'code' not in df.columns:
                     df = df.reset_index()
                
                # If reset_index creates 'index' column, rename it to code if needed, 
                # but usually tdx_data_Day returns code as index named 'code' or no name
                if 'code' not in df.columns and 'index' in df.columns:
                    df.rename(columns={'index': 'code'}, inplace=True)

                for idx, row in df.iterrows():
                    # Handle code if it's still not in columns (shouldn't happen after reset_index if index was code)
                    code = row.get('code')
                    if not code and not isinstance(idx, int):
                         code = idx
                    if not code:
                         print(f"Skipping row with no code: {idx}")
                         continue
                         
                    # Construct monitor data expected by StrategyManager
                    # Needs: name, score, diff, time, vol_ratio (optional), baseline, status
                    live_strategy.monitors[code] = {
                        'name': row['name'],
                        'score': 60.0 + (float(row.get('percent', 0)) * 2), # Mock score
                        'diff': float(row.get('percent', 0)),
                        'time': row.get('time', '00:00:00'),
                        'vol_ratio': float(row.get('ratio', 0)) if 'ratio' in row else 1.0,
                        'baseline': 50.0,
                        'status': 'Running'
                    }
            else:
                print("Warning: No data fetched from Source.")
                # Add some dummy data if fetch fails (e.g. no network)
                live_strategy.monitors['000001'] = {'name': 'Mock平安', 'score': 66, 'diff': 1.2, 'time': '10:00:00', 'status': 'Test'}
                
        except Exception as e:
            print(f"Data fetch error: {e}")
            import traceback
            traceback.print_exc()

        # 3. Launch UI
        # We pass 'root' as master. Since StrategyManager is Toplevel, it opens a declared window.
        # We assume root is the main app window (hidden or simple).
        root.title("Main App Root")
        # Hide root if you prefer only seeing the StrategyManager
        # root.withdraw() 
        
        # Inject sender to root so StrategyManager can use it if it looks for master.sender
        root.sender = MockSender()

        app = StrategyManager(root, live_strategy, realtime_service)
        
        # Keep mainloop running
        root.mainloop()

    main()

