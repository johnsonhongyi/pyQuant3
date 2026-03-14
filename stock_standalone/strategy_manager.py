# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import time
from datetime import datetime
from typing import Any
import pandas as pd
import numpy as np
import re

from tk_gui_modules.window_mixin import WindowMixin
from stock_logic_utils import toast_message
from history_manager import QueryHistoryManager
from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
from JohnsonUtil import LoggerFactory

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
    
    CONFIG_FILE: str = "strategy_config.json"
    
    def __init__(self, master: Any, live_strategy: Any, realtime_service: Any = None, query_manager: Any = None):
        super().__init__(master)
        self.master: Any = master
        self.live_strategy: Any = live_strategy
        self.realtime_service: Any = realtime_service
        
        # 注入 realtime_service 到 live_strategy (为了后台集成)
        if self.live_strategy and self.realtime_service:
            self.live_strategy.realtime_service = self.realtime_service
            
        self.decision_engine: Any = getattr(live_strategy, 'decision_engine', None)
        self.risk_engine: Any = getattr(live_strategy, 'risk_engine', None)
        self.trading_logger: Any = getattr(live_strategy, 'trading_logger', None)
        
        self.title("策略白盒管理器 & 验证工具")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 加载持久化配置
        self.config_data: dict[str, Any] = self._load_config()
        self._apply_config_to_engines()

        self._start_time: float = time.time()
        self._update_job: Any = None
        self._pause_refresh: bool = False
        self._data_sort_col: str = "score"  # 默认排序字段
        self._data_sort_reverse: bool = True # 默认降序排序
        
        self.var_history2: tk.StringVar = tk.StringVar()
        self.var_use_history2: tk.BooleanVar = tk.BooleanVar(value=True)
        self.var_history4: tk.StringVar = tk.StringVar()
        
        if query_manager:
            self.query_manager = query_manager
            # 链接共享 QM 的变量
            if self.query_manager.search_var2:
                self.var_history2 = self.query_manager.search_var2
            else:
                self.query_manager.search_var2 = self.var_history2
            
            if self.query_manager.search_var4:
                self.var_history4 = self.query_manager.search_var4
            else:
                self.query_manager.search_var4 = self.var_history4
        else:
            self.query_manager = QueryHistoryManager(
                self,
                search_var2=self.var_history2, 
                search_var4=self.var_history4, 
                history_file=SEARCH_HISTORY_FILE,
                sync_history_callback=self._on_history_sync
            )
        
        # 迁移旧数据到 history4
        # self._migrate_old_history()
        
        # 加载历史到 combo (在 _init_data_tab 中会用到)
        _, h2, _, h4, *_ = self.query_manager.load_search_history()
        self.history2_list: list[str] = [r["query"] for r in h2]
        self.history4_list: list[str] = [r["query"] for r in h4]

        # 初始化 UI
        self._setup_ui()
        
        # 恢复窗口位置
        self.load_window_position(self, "StrategyManager", default_width=900, default_height=700)
        
        # 启动自动刷新
        self._schedule_refresh()

    def _setup_ui(self) -> None:
        # 状态栏 (放在底部)
        self.statusbar: tk.Label = tk.Label(self, text="Ready", bd=1, relief=tk.SUNKEN, anchor="w")
        self.statusbar.pack(side="bottom", fill="x")
        
        self.notebook: ttk.Notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 1: 决策引擎 (Decision Engine)
        self.tab_decision: ttk.Frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_decision, text="🧠 决策引擎")
        self._init_decision_tab()
        
        # Tab 2: 风险控制 (Risk Control)
        self.tab_risk: ttk.Frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_risk, text="🛡️ 风险控制")
        self._init_risk_tab()
        
        # Tab 3: 实时数据 (Realtime Data)
        self.tab_data: ttk.Frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_data, text="📊 实时数据")
        self._init_data_tab()
        self._init_tree_tab()
        
        # Tab 4: 信号日志 (Signal Log)
        self.tab_log: ttk.Frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_log, text="📜 信号日志")
        self._init_log_tab()
        
        # Tab 5: 验证/手操 (Verify & Trade)
        self.tab_verify: ttk.Frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_verify, text="🔧 验证与手操")
        self._init_verify_tab()

    # ------------------- 配置持久化 -------------------
    def _load_config(self) -> dict[str, Any]:
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载策略配置失败: {e}")
        return {}
        
    def _save_config(self) -> None:
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
            logger.info("策略配置已保存")
        except Exception as e:
            logger.error(f"保存策略配置失败: {e}")

    # def _migrate_old_history(self) -> None:
    #     """从 strategy_config.json 迁移 history 到 history_manager 的 history4"""
    #     old_filters = self.config_data.get('filter_history', [])
    #     if not old_filters:
    #         return
            
    #     logger.info(f"💾 正在迁移 {len(old_filters)} 条旧过滤记录到 history4...")
    #     migrated_count = 0
    #     for q in old_filters:
    #         q = q.strip()
    #         if not q: continue
    #         record = {"query": q, "starred": 0, "note": "Migrated"}
    #         # 直接操作 query_manager 数据
    #         self.query_manager.sync_history_current(record, action="add", history_key="history4")
    #         migrated_count += 1
            
    #     # 同时迁移已有的 history2 记录 (因为 StrategyManager 之前主要使用 H2)
    #     _, h2, _, _ = self.query_manager.load_search_history()
    #     h2_count = 0
    #     for r in h2:
    #         q = r.get("query", "").strip()
    #         if q:
    #             self.query_manager.sync_history_current(r.copy(), action="add", history_key="history4")
    #             h2_count += 1
            
    #     # 移除旧配置并保存
    #     if 'filter_history' in self.config_data:
    #         del self.config_data['filter_history']
    #         self._save_config()
            
    #     # 强制保存一次 history_manager 的文件
    #     self.query_manager.save_search_history()
    #     logger.info(f"✅ 成功迁移 {migrated_count} 条配置记录和 {h2_count} 条 H2 记录到 history4，并清理了旧配置。")

    def _apply_config_to_engines(self) -> None:
        """应用保存的配置到引擎实例"""
        if not self.config_data:
            return
            
        # 决策引擎参数
        if self.decision_engine:
            de_cfg: dict = self.config_data.get('decision_engine', {})
            for attr, val in de_cfg.items():
                if hasattr(self.decision_engine, attr):
                    setattr(self.decision_engine, attr, float(val))
                    logger.info(f"Restored DecisionEngine.{attr} = {val}")
        
        # 风险引擎参数
        if self.risk_engine:
            re_cfg: dict = self.config_data.get('risk_engine', {})
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
             for key, data in monitors.items():
                 code = data.get('code', key.split('_')[0])
                 res = data.get('resample', 'd')
                 name = data['name']
                 
                 # 1.1 检查 RiskEngine 状态
                 if self.risk_engine:
                     r_state = self.risk_engine.get_risk_state(key)
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
                     loss_count = self.trading_logger.get_consecutive_losses(code, resample=res)
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
        
        # 2. H2 联动过滤 (移至顶部)
        tk.Label(ctrl_frame, text="H2联合:").pack(side="left", padx=5)
        tk.Checkbutton(ctrl_frame, text="", variable=self.var_use_history2, 
                       command=self._refresh_data_tab).pack(side="left")
        
        self.combo_history2 = ttk.Combobox(ctrl_frame, width=20, textvariable=self.var_history2)
        self.combo_history2.pack(side="left", padx=2, fill="x", expand=True)
        self.combo_history2['values'] = self.history2_list
        if self.history2_list and not self.var_history2.get():
            self.var_history2.set(self.history2_list[0])
            
        self.combo_history2.bind("<<ComboboxSelected>>", lambda e: self._refresh_data_tab())
        self.combo_history2.bind("<Return>", lambda e: self._refresh_data_tab())

        # --- Row 2: 高级过滤 (History4, 下方放置) ---
        h4_frame = tk.Frame(self.tab_data)
        h4_frame.pack(fill="x", padx=10, pady=2)
        
        tk.Label(h4_frame, text="策略过滤 (H4):", font=("Arial", 9, "bold")).pack(side="left", padx=2)
        
        # 删除按钮
        tk.Button(h4_frame, text="✖", width=2, command=self._delete_current_filter).pack(side="right", padx=2)
        # 管理按钮 (⚙️)
        # tk.Button(h4_frame, text="⚙️", width=2, command=lambda: self.query_manager.open_editor()).pack(side="right", padx=2)
        
        self.combo_filter = ttk.Combobox(h4_frame, width=35, textvariable=self.var_history4)
        self.combo_filter.pack(side="left", padx=2, fill="x", expand=True)
        self.combo_filter['values'] = self.history4_list
        
        # 链接 combo 到 query_manager 以便双击"使用"时同步
        self.query_manager.search_combo4 = self.combo_filter
        self.query_manager.search_combo2 = self.combo_history2

        default_filters = [
            " ",
            "score > 80", 
            "volume > 2 and amount > 5e8",
            "60 < score and volume > 2 and close > ma5d and low < ma10d and amount > 5e8",
            "20 < score < 80 and volume > 2 and amount > 2e8"
        ]
        
        # 补充默认值到 history4
        seen = set(self.history4_list)
        for f in default_filters:
            f = f.strip()
            if f and f not in seen:
                self.query_manager.sync_history_current({"query": f, "starred": 0}, action="add", history_key="history4")
                seen.add(f)
        
        # 重新获取最新的 history4_list
        _, _, _, h4, *_ = self.query_manager.load_search_history()
        self.history4_list = [r["query"] for r in h4]
        self.combo_filter['values'] = self.history4_list
        
        # 恢复上次选中的过滤 (优先使用 history4 中的最新项，即最近一次 pinning 或使用的)
        if self.history4_list:
            self.var_history4.set(self.history4_list[0])
            
        # 绑定事件 (支持暂停/恢复刷新)
        self.combo_filter.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())
        self.combo_filter.bind('<Return>', lambda e: self._apply_filter())
        self.combo_filter.bind("<FocusIn>", lambda e: self._pause_refresh_start())
        self.combo_filter.bind("<FocusOut>", lambda e: self._pause_refresh_end())

    def _init_tree_tab(self):
        # 情绪分数表
        list_frame = tk.LabelFrame(self.tab_data, text="实时情绪分数监控", padx=5, pady=5)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        cols = ("code", "name", "Rank","percent", "score", "diff", "win", "slope", "baseline", "status", "time", "vol_ratio")
        self.tree_data = ttk.Treeview(list_frame, columns=cols, show="headings")
        self.tree_data.heading("code", text="代码", command=lambda: self._sort_tree_data("code", False))
        self.tree_data.heading("name", text="名称", command=lambda: self._sort_tree_data("name", False))
        self.tree_data.heading("Rank", text="Rank", command=lambda: self._sort_tree_data("Rank", False))
        self.tree_data.heading("percent", text="percent", command=lambda: self._sort_tree_data("percent", False))
        self.tree_data.heading("score", text="情绪分", command=lambda: self._sort_tree_data("score", True))
        self.tree_data.heading("diff", text="变化", command=lambda: self._sort_tree_data("diff", True))
        self.tree_data.heading("win", text="连阳", command=lambda: self._sort_tree_data("win", True))
        self.tree_data.heading("slope", text="斜率", command=lambda: self._sort_tree_data("slope", True))
        self.tree_data.heading("baseline", text="基准", command=lambda: self._sort_tree_data("baseline", True))
        self.tree_data.heading("status", text="形态", command=lambda: self._sort_tree_data("status", False))
        self.tree_data.heading("time", text="时间", command=lambda: self._sort_tree_data("time", True))
        self.tree_data.heading("vol_ratio", text="成交量", command=lambda: self._sort_tree_data("vol_ratio", True))
        
        for col in cols:
            self.tree_data.column(col, width=60, anchor="center")
        # 初始微调一些明显长度不同的
        self.tree_data.column("name", width=70)
        self.tree_data.column("status", width=120)

        self.tree_data.pack(fill="both", expand=True)

        # 绑定事件
        self.tree_data.bind("<ButtonRelease-1>", self.on_data_tree_click)
        self.tree_data.bind("<Double-1>", self.on_data_tree_dblclick)
        self.tree_data.bind("<Button-3>", self.on_data_tree_rclick)
        self.tree_data.bind("<KeyRelease-Up>", self.on_data_tree_key_nav)
        self.tree_data.bind("<KeyRelease-Down>", self.on_data_tree_key_nav)

    def _apply_filter(self, event=None) -> None:
        """用户手动触发过滤应用，此时才保存到历史记录"""
        current_filter = self.var_history4.get().strip()
        if current_filter:
            # 实现置顶：先同步到 history_manager (它内部已改为先删再插)
            self.query_manager.sync_history_current({"query": current_filter, "starred": 0}, action="add", history_key="history4")
            self.query_manager.save_search_history()
            
        # 停止刷新暂停状态
        self._pause_refresh_end()
        # 立即执行刷新
        self._refresh_data_tab()
        
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
            # ⭐ 可视化器联动
            if self.master and getattr(self.master, "_vis_enabled_cache", False) and code:
                if hasattr(self.master, 'open_visualizer'):
                    self.master.open_visualizer(str(code))


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
        
        # 动态获取 realtime_service (异步加载后可能已更新)
        if not self.realtime_service and hasattr(self.master, 'realtime_service'):
            if self.master.realtime_service:
                self.realtime_service = self.master.realtime_service
                logger.info("StrategyManager: 从主窗口获取到 RealtimeDataService")
        
        if not self.realtime_service:
            # 检查主窗口是否正在异步加载
            if hasattr(self.master, '_realtime_service_ready') and not self.master._realtime_service_ready:
                self.lbl_rt_stats.config(text="⏳ RealtimeDataService 正在后台加载中...")
            else:
                self.lbl_rt_stats.config(text="❌ RealtimeDataService 未初始化 (请检查启动日志)")
            return
            
        # 刷新统计
        cache_size = 0
        if hasattr(self.realtime_service, 'kline_cache'):
            cache_size = len(self.realtime_service.kline_cache)
            
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

        # 2. 批量关联 Name 和 Volume 以及实时 55188 数据
        df_all = getattr(self.master, 'df_all', None)

        # [FIX] 非交易时间 master.df_all 为空时，从 realtime_service 读取只读快照供查询显示
        if (df_all is None or (hasattr(df_all, 'empty') and df_all.empty)) and self.realtime_service:
            try:
                snap = self.realtime_service.get_df_snapshot()
                if not snap.empty:
                    df_all = snap
                    logger.debug("_refresh_data_tab: 非交易时间，使用 realtime_service 快照数据")
            except Exception as e:
                logger.warning(f"_refresh_data_tab: 获取快照失败: {e}")

        ext_data_map = {}
        if self.realtime_service:
            try:
                ext_status = self.realtime_service.get_55188_data()
                if isinstance(ext_status, dict) and 'df' in ext_status:
                    df_ext = ext_status['df']
                    if not df_ext.empty:
                        if 'code' in df_ext.columns:
                            ext_data_map = df_ext.set_index('code').to_dict('index')
                        else:
                            ext_data_map = df_ext.to_dict('index')
            except Exception as e:
                logger.error(f"获取55188同步数据失败: {e}")

        if df_all is not None:
            try:
                cols_needed = [c for c in ['name', 'volume', 'Rank','percent', 'win', 'slope', 'ratio'] if c in df_all.columns]
                if cols_needed:
                    df_temp = df_temp.join(df_all[cols_needed])
            except Exception as e:
                logger.error(f"关联主数据失败: {e}")
        
        # 填充基本缺失值
        if 'name' not in df_temp.columns: df_temp['name'] = '--'
        if 'volume' not in df_temp.columns: df_temp['volume'] = 0
        if 'Rank' not in df_temp.columns: df_temp['Rank'] = 0
        if 'percent' not in df_temp.columns: df_temp['percent'] = 0
        if 'win' not in df_temp.columns: df_temp['win'] = 0
        if 'slope' not in df_temp.columns: df_temp['slope'] = 0.0
        if 'ratio' not in df_temp.columns: df_temp['ratio'] = 1.0
        
        df_temp['name'] = df_temp['name'].fillna('--')
        df_temp['volume'] = df_temp['volume'].fillna(0)
        df_temp['Rank'] = df_temp['Rank'].fillna(0)
        df_temp['percent'] = df_temp['percent'].fillna(0)
        df_temp['win'] = df_temp['win'].fillna(0)
        df_temp['slope'] = df_temp['slope'].fillna(0.0)
        df_temp['ratio'] = df_temp['ratio'].fillna(1.0) # Default ratio to 1.0
        
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
        # saved_filter = self.config_data.get('last_filter', "")
        
        # if current_filter != saved_filter:
        #     self.config_data['last_filter'] = current_filter
        #     changed = True
            
        if changed:
            self._save_config()
        # --------------------------------------
            
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

        # 2.6 应用高级过滤 (统一使用 history4 + 可选 history2)
        h4_expr = self.var_history4.get().strip()
        h2_expr = self.var_history2.get().strip()
        use_h2 = self.var_use_history2.get()
        
        combined_filters = []
        if h4_expr:
            combined_filters.append(f"({h4_expr})")
        if use_h2 and h2_expr:
            combined_filters.append(f"({h2_expr})")
            
        final_query = " and ".join(combined_filters)

        if final_query:
            try:
                if df_all is not None:
                     # 策略优化：仅 join 过滤表达式中用到的列 Isolate only used columns
                     # 简单的正则提取标识符
                     # 提取所有单词作为潜在列名
                     tokens = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', final_query))
                     # 强制加入我们需要显示的列
                     tokens.update(['Rank','percent', 'win', 'slope', 'ratio']) # Added ratio
                     
                     cols_in_temp = set(df_temp.columns)
                     cols_to_add = [c for c in df_all.columns if c in tokens and c not in cols_in_temp]
                     
                     if cols_to_add:
                         df_temp = df_temp.join(df_all[cols_to_add])
                
                df_temp = df_temp.query(final_query)
                
            except Exception as e:
                # 过滤失败显示在状态栏
                err_msg = str(e)
                if "not found" in err_msg:
                    self.lbl_rt_stats.config(text=f"过滤错误: 字段未找到 ({err_msg})", fg="red")
                else:
                    self.lbl_rt_stats.config(text=f"过滤错误: {err_msg}", fg="red")
                
                # Console debug
                print(f"[Filter Error]Query: {final_query}")
                print(f"[Filter Error]Available columns: {list(df_temp.columns)}")
                return # 停止后续处理

        # 3. 排序 (Pandas Native Sort)
        sort_col = self._data_sort_col
        # 映射 Treeview 列名到 DataFrame 列名
        col_map = {'vol_ratio': 'ratio'} # vol_ratio 列显示的是 ratio
        df_sort_col = col_map.get(sort_col, sort_col)
        
        ascending = not self._data_sort_reverse
        
        if df_sort_col in df_temp.columns:
            try:
                # 确保排序列是数值型以便正确排序
                if df_sort_col in ['score', 'volume', 'diff', 'Rank','percent', 'win', 'slope', 'ratio']: # Added ratio
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
            
            # Time Formatting
            time_str = '--'
            ts = kl_cache_ts.get(code, 0)
            if ts > 0:
                time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")

            # Rank & Win & Slope 动态同步
            rank_val = row.get('Rank', 0)
            # 如果主数据没有 Rank，尝试从 55188 实时同步源获取
            if (rank_val == 0 or rank_val == 999) and code in ext_data_map:
                rank_val = ext_data_map[code].get('hot_rank', 0)

            percent_val = row.get('percent', 0)
            # 如果主数据没有 Rank，尝试从 55188 实时同步源获取
            if (percent_val == 0 or percent_val == 999) and code in ext_data_map:
                percent_val = ext_data_map[code].get('percent', 0)

            win_val = row.get('win', 0)
            slope_val = float(row.get('slope', 0.0))
            
            # 如果斜率为 0，且有实时服务，尝试基于最近 K 线计算动态斜率
            if slope_val == 0.0 and self.realtime_service:
                try:
                    klines = self.realtime_service.get_minute_klines(code, n=10)
                    if len(klines) >= 5:
                        prices = [float(k['close']) for k in klines]
                        # 简单线性拟合斜率
                        x = np.arange(len(prices))
                        y = np.array(prices)
                        slope_fit, _ = np.polyfit(x, y, 1) # type: ignore
                        # 归一化为百分比斜率
                        if prices[0] > 0:
                            slope_val = (slope_fit / prices[0]) * 1000 # 放大以利于观察
                except Exception:
                    pass

            # 量比显示优化
            ratio_val = float(row.get('ratio', 0.0))
            if ratio_val == 0.0 and 'volume' in row:
                # 如果没有量比列，简单显示成交量
                try:
                    vol = float(row.get('volume', 0.0))
                    if vol > 1000000:
                        vol_str = f"{vol/1000000:.1f}M"
                    elif vol > 1000:
                        vol_str = f"{vol/1000:.0f}K"
                    else:
                        vol_str = str(int(vol))
                except:
                    vol_str = "--"
            else:
                vol_str = f"{ratio_val:.1f}"

            item_data = {
                'code': code,
                'name': row.get('name', '--'),
                'Rank': rank_val,
                'percent': percent_val,
                'score': f"{row['score']:.1f}",
                'diff': f"{row.get('diff', 0):+.1f}",
                'win': win_val,
                'slope': f"{slope_val:.1f}", # Format slope
                'baseline': f"{row.get('baseline', 50):.1f}",
                'status': row.get('status', '--'),
                'time': time_str,
                'vol_ratio': vol_str
            }
            display_list.append(item_data) # Append the constructed item_data
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
                item_data['code'], 
                item_data['name'], 
                str(item_data['Rank']),
                item_data['percent'],
                item_data['score'], 
                item_data['diff'], 
                str(item_data['win']),
                item_data['slope'], 
                item_data['baseline'], 
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
            
        # 7. 自动调整列宽
        self._adjust_data_tree_columns()
        
    def _adjust_data_tree_columns(self):
        """
        自动根据内容调整列宽
        """
        import tkinter.font as tkfont
        f = tkfont.Font(font='TkDefaultFont')
        
        # 遍历所有可见列
        for col in self.tree_data["columns"]:
            # 1. 测量表头宽度
            header_text = self.tree_data.heading(col, "text")
            w_header = f.measure(header_text) + 20 # 留点 margin 给排序箭头
            
            # 2. 测量内容宽度 (采样前 20 条)
            w_content = 0
            for iid in self.tree_data.get_children()[:20]:
                val = self.tree_data.set(iid, col)
                w_curr = f.measure(str(val))
                if w_curr > w_content:
                    w_content = w_curr
            
            # 3. 设置最优宽度 (min 60, max 200)
            final_w = max(60, w_header, w_content + 15)
            if final_w > 200: final_w = 200
            
            # 特殊修正
            if col == "name": final_w = max(final_w, 75)
            if col == "status": final_w = max(final_w, 120)
            
            self.tree_data.column(col, width=final_w)

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
            # ⭐ 可视化器联动
            if self.master and getattr(self.master, "_vis_enabled_cache", False) and code:
                if hasattr(self.master, 'open_visualizer'):
                    self.master.open_visualizer(str(code))


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

    def _delete_current_filter(self) -> None:
        """删除当前选中的过滤记录"""
        current = self.var_history4.get().strip()
        if not current: return
        
        # 统一使用 QueryHistoryManager
        self.query_manager.sync_history_current({"query": current}, action="delete", history_key="history4")
        self.query_manager.save_search_history()
        self._refresh_data_tab() # 刷新

    # ------------------- Tab 5: 验证/手操 -------------------
    def _on_history_sync(self, **kwargs: Any) -> None:
        """当 QueryHistoryManager 同步历史时触发"""
        source = kwargs.get("source", "")
        selected = kwargs.get("selected_query")
        
        if "search_history2" in kwargs:
            h2 = kwargs["search_history2"]
            self.history2_list = [r["query"] for r in h2]
            if hasattr(self, 'combo_history2'):
                self.combo_history2['values'] = self.history2_list
                # 联动：双击使用时同步
                if source == "use" and selected:
                    self.var_history2.set(selected)
                elif self.history2_list and not self.var_history2.get():
                    self.var_history2.set(self.history2_list[0])
                    
        if "search_history4" in kwargs:
            h4 = kwargs["search_history4"]
            self.history4_list = [r["query"] for r in h4]
            if hasattr(self, 'combo_filter'):
                self.combo_filter['values'] = self.history4_list
                # 联动：双击使用时同步
                if source == "use" and selected:
                    self.var_history4.set(selected)
                elif self.history4_list and not self.var_history4.get():
                    self.var_history4.set(self.history4_list[0])
                    
        # 如果是双击使用的联动，强制刷新一次 UI
        if source == "use":
            self._refresh_data_tab()


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
        # 💥 [NEW] 绑定右键黏贴与回车触发
        self.entry_verify_code.bind('<Button-3>', self._on_entry_rclick_paste)
        self.entry_verify_code.bind('<Return>', lambda e: self._do_verify_stock())
        
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
        # 💥 [NEW] 绑定右键黏贴
        self.entry_trade_code.bind('<Button-3>', self._on_entry_rclick_paste)
        
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

    def _on_entry_rclick_paste(self, event):
        """右键点击输入框：自动黏贴剪贴板内容"""
        widget = event.widget
        try:
            # 优先尝试从系统剪贴板获取 (兼容性较好)
            import pyperclip
            content = pyperclip.paste()
            if not content:
                # 回退到 Tkinter 剪贴板
                content = self.master.clipboard_get()
        except Exception:
            try:
                content = self.master.clipboard_get()
            except:
                content = ""
        
        if content:
            # 简单清洗代码数据 (通常为 6 位数字或带前缀)
            code = content.strip()
            # 过滤超长内容 (防止误贴一整段文字)
            if len(code) > 20: 
                return
                
            widget.delete(0, tk.END)
            widget.insert(0, code)
            
            # 增强：如果是验证框，填入后自动触发评估
            if widget == getattr(self, 'entry_verify_code', None):
                self._do_verify_stock()

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
                    'nclose': row.get('nclose', 0),
                    'win': row.get('win', 0),
                    'red': row.get('red', 0)
                }
            
            # 💥 [NEW] 注入日线历史数据以支持 TD 序列和顶部检测
            day_df = pd.DataFrame()
            if hasattr(self.live_strategy, 'daily_history_cache'):
                cache_key = f"{code}_d"
                day_df = self.live_strategy.daily_history_cache.get(cache_key, pd.DataFrame())
                if day_df.empty:
                    day_df = self.live_strategy.daily_history_cache.get(code, pd.DataFrame())
            
            if not day_df.empty:
                snapshot['day_df'] = day_df
            
            # 获取当前阶段
            current_phase = "IDLE"
            if code in monitors:
                current_phase = monitors[code].get('trade_phase', "IDLE")
            snapshot['trade_phase'] = current_phase
            
            # 调用 decision engine
            result = self.decision_engine.evaluate(row, snapshot, mode="full")
            
            # 💥 [FIX] 必须经过 Risk Engine 修正才能得到最终动作 (与实盘一致)
            final_action = result.get('action', '持仓')
            final_position = result.get('position', 0.0)
            risk_reason = ""
            
            if self.risk_engine:
                # 构造临时 data 供 risk engine 使用 (必须包含 trade_phase 等状态)
                # 注意: 这里我们使用 monitors 中的原始 data 引用，或者构造一个包含必要信息的副本
                monitor_data = monitors.get(code, {})
                if not monitor_data:
                     # 如果没在监控中，临时构造一个仅用于计算的 data
                     monitor_data = {
                         'code': code, 
                         'name': row.get('name'), 
                         'trade_phase': current_phase,
                         'snapshot': snapshot,
                         'rules': []
                     }
                
                # 调整仓位与动作
                # adjust_position(self, data, action, position)
                r_action, r_pos = self.risk_engine.adjust_position(monitor_data, final_action, final_position)
                
                if r_action and r_action != final_action:
                    risk_reason = f" -> [风控修正] {r_action}"
                    final_action = r_action
                    final_position = r_pos
            
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
            
            # [NEW] 展示 TD 和顶部评分
            if not day_df.empty:
                from daily_top_detector import detect_top_signals
                td_setup = day_df.iloc[-1].get('td_setup', 0)
                top_info = detect_top_signals(day_df, row)
                output += f"TD序列: {td_setup} | 顶部评分: {top_info['score']:.2f}\n"
                if top_info['signals']:
                    output += f"顶部信号: {', '.join(top_info['signals'])}\n"

            output += "-" * 30 + "\n"
            output += f"【阶段/决策】: {current_phase} -> {final_action} ({final_position}{risk_reason})\n"
            output += f"【原始决策】: {result.get('action')} ({result.get('reason')})\n"
            if self.risk_engine:
                 # 获取风控状态原因 (如果能获取到)
                 pass
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

    def _pause_refresh_start(self):
        self._pause_refresh = True

    def _pause_refresh_end(self):
        self._pause_refresh = False
    # ------------------- 通用 -------------------
    def _schedule_refresh(self):
        if not self.winfo_exists(): return
        
        if not getattr(self, "_pause_refresh", False):
            # 刷新 Decision Tab
            self._refresh_decision_status()
            
            # 刷新 Risk List
            self._refresh_risk_list()
            
            # 刷新 Realtime Tab
            self._refresh_data_tab()
            
            # 10秒刷新一次 (降低频率以减轻卡顿)
            # 刷新 Signal Logs
            self._refresh_signal_logs()

        # 10秒刷新一次 (提高日志实时性)
        self._update_job = self.after(10*1000, self._schedule_refresh)

    def on_close(self):
        self.save_window_position(self, "StrategyManager")
        if hasattr(self, 'query_manager'):
            self.query_manager.save_search_history()
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

