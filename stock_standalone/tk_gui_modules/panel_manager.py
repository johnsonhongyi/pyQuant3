# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox
import sys
import os
import traceback
from JohnsonUtil import LoggerFactory
from stock_logic_utils import toast_message

logger = LoggerFactory.getLogger("instock_TK.PanelManager")

class PanelManager:
    """
    负责管理和弹出所有二级窗口与面板，减轻主应用程序文件的负载。
    """
    def __init__(self, monitor_app):
        self.app = monitor_app
        # 窗口引用缓存
        self._pulse_win = None
        self._signal_dashboard_win = None
        self._live_signal_viewer = None
        self._detailed_analysis_win = None
        self._stock_selection_win = None
        self._strategy_report_win = None
        self._voice_monitor_win = None
        self._indicator_help_win = None

    def open_market_pulse(self):
        """打开每日复盘面板"""
        if not hasattr(self.app, '_pulse_viewer_class') or not self.app._pulse_viewer_class:
            messagebox.showerror("错误", "Market Pulse 模块未加载。")
            return
            
        if not self.app.live_strategy:
            messagebox.showwarning("请稍候", "策略引擎正在初始化，请稍后再试。")
            return
             
        if self._pulse_win and self._pulse_win.winfo_exists():
            self._pulse_win.lift()
            return
            
        try:
            self._pulse_win = self.app._pulse_viewer_class(self.app, self.app) 
            logger.info("MarketPulseViewer opened via PanelManager.")
        except Exception as e:
            logger.error(f"Failed to open MarketPulseViewer: {e}")

    def open_live_signal_viewer(self):
        """打开实时信号仪表盘 (Qt6)"""
        try:
            if not self._signal_dashboard_win:
                from PyQt6 import QtWidgets
                if not QtWidgets.QApplication.instance():
                    self.app._qt_app = QtWidgets.QApplication(sys.argv) if hasattr(sys, 'argv') else QtWidgets.QApplication([])
                
                from signal_dashboard_panel import SignalDashboardPanel
                self._signal_dashboard_win = SignalDashboardPanel()
                self._signal_dashboard_win.parent_app = self.app
                
                # 跨线程联动
                self._signal_dashboard_win.code_clicked.connect(
                    lambda c, n: self.app.tk_dispatch_queue.put(lambda: self.app.on_code_click(c))
                )
                
            self._signal_dashboard_win.show()
            self.app._dashboard_first_sync_done = False 
            self._signal_dashboard_win.raise_()
            self._signal_dashboard_win.activateWindow()
            toast_message(self.app, "实时信号仪表盘已启动")
        except Exception as e:
            logger.error(f"Failed to open SignalDashboard: {e}\n{traceback.format_exc()}")
            messagebox.showerror("错误", f"启动信号仪表盘失败: {e}")

    def open_indicator_help(self):
        """打开指标帮助窗口 (Ctrl + /)"""
        import stock_indicator_help
        stock_indicator_help.show_help(self.app)

    def open_live_signal_trace(self):
        """打开实时信号轨迹查询窗口 (PyQt6)"""
        try:
            if self._live_signal_viewer:
                try:
                    self._live_signal_viewer.show()
                    self._live_signal_viewer.raise_()
                    self._live_signal_viewer.activateWindow()
                    self._live_signal_viewer.refresh_data()
                    return
                except Exception:
                    self._live_signal_viewer = None
            
            from live_signal_viewer import LiveSignalViewer
            self._live_signal_viewer = LiveSignalViewer(
                on_select_callback=self.app.on_code_click,
                sender=getattr(self.app, 'sender', None),
                main_app=self.app,
            )
            self._live_signal_viewer.show()
            self._live_signal_viewer.raise_()
            self._live_signal_viewer.activateWindow()
            toast_message(self.app, "实时信号查询已启动")
        except Exception as e:
            logger.error(f"Failed to open LiveSignalViewer: {e}")
            messagebox.showerror("错误", f"启动信号查询失败: {e}")

    def open_stock_selection_window(self):
        """打开策略选股与人工复核窗口 (支持窗口复用)"""
        try:
            from stock_selection_window import StockSelectionWindow
            from stock_selector import StockSelector
            
            # 1. 确保 selector 存在且数据最新
            if not hasattr(self.app, 'selector') or self.app.selector is None:
                self.app.selector = StockSelector(df=getattr(self.app, 'df_all', None))
            else:
                # ✅ 关键：更新已有 selector 的数据引用
                if hasattr(self.app, 'df_all') and not self.app.df_all.empty:
                    self.app.selector.df_all_realtime = self.app.df_all
                    self.app.selector.resample = self.app.global_values.getkey("resample") or 'd'

            # 2. 窗口复用逻辑
            if self._stock_selection_win and self._stock_selection_win.winfo_exists():
                try:
                    # ✅ 更新窗口内部引用
                    self._stock_selection_win.live_strategy = getattr(self.app, 'live_strategy', None)
                    self._stock_selection_win.selector = self.app.selector
                    # ✅ 强制刷新数据
                    self._stock_selection_win.load_data(force=True)
                    self._stock_selection_win.deiconify()
                    self._stock_selection_win.lift()
                    self._stock_selection_win.focus_force()
                    return
                except Exception as e:
                    logger.warning(f"复用选股窗口异常: {e}")

            # 3. 新建窗口
            self._stock_selection_win = StockSelectionWindow(
                self.app, 
                getattr(self.app, 'live_strategy', None), 
                self.app.selector
            )
            toast_message(self.app, "选股复核窗口已启动")
        except Exception as e:
            logger.error(f"Failed to open StockSelectionWindow: {e}\n{traceback.format_exc()}")
            messagebox.showerror("错误", f"打开选股窗口失败: {e}")

    def open_archive_view_window(self, filename):
        """打开历史存档概览窗口"""
        import pandas as pd
        from tkinter import ttk
        
        window_id = f"ArchiveView_{os.path.basename(filename)}"
        win = tk.Toplevel(self.app)
        win.title(f"存档详情: {os.path.basename(filename)}")
        
        if hasattr(self.app, 'load_window_position'):
             self.app.load_window_position(win, window_id, default_size="1000x600")

        # 此处省略具体实现，保持结构精简，迁移时应完整迁移
        pass

    def open_detailed_analysis(self):
        """[PERFORMANCE] 打开系统资源占用与健康检查面板"""
        if self._detailed_analysis_win and self._detailed_analysis_win.winfo_exists():
            self._detailed_analysis_win.lift()
            return

        import time
        import sys
        analysis_win = tk.Toplevel(self.app)
        self._detailed_analysis_win = analysis_win
        analysis_win.title("系统诊断与资源审计")
        
        if hasattr(self.app, 'load_window_position'):
            self.app.load_window_position(analysis_win, "SystemAnalysis", default_size="700x500")

        atext_frame = tk.Frame(analysis_win)
        atext_frame.pack(fill="both", expand=True, padx=10, pady=10)

        analysis_text = tk.Text(atext_frame, font=("Consolas", 10), wrap="none")
        as_vsb = tk.Scrollbar(atext_frame, orient="vertical", command=analysis_text.yview)
        as_hsb = tk.Scrollbar(atext_frame, orient="horizontal", command=analysis_text.xview)
        analysis_text.configure(yscrollcommand=as_vsb.set, xscrollcommand=as_hsb.set)

        as_vsb.pack(side="right", fill="y")
        as_hsb.pack(side="bottom", fill="x")
        analysis_text.pack(side="left", fill="both", expand=True)

        def refresh_analysis():
            if not analysis_win.winfo_exists(): return
            try:
                import psutil
                current_process = psutil.Process()
                report = [f"=== System Resource Report ({time.strftime('%Y-%m-%d %H:%M:%S')}) ==="]
                # ... (迁移完整逻辑) ...
                analysis_text.delete(1.0, tk.END)
                analysis_text.insert(tk.END, "\n".join(report))
            except Exception as e:
                analysis_text.insert(tk.END, f"\nError: {e}")
            analysis_win.after(5000, refresh_analysis)

        refresh_analysis()
        
        def on_close():
            if hasattr(self.app, 'save_window_position'):
                self.app.save_window_position(analysis_win, "SystemAnalysis")
            self._detailed_analysis_win = None
            analysis_win.destroy()

        analysis_win.protocol("WM_DELETE_WINDOW", on_close)
        analysis_win.bind("<Escape>", lambda e: on_close())

    def open_archive_loader(self):
        """打开存档选择窗口"""
        from history_manager import QueryHistoryManager
        win = tk.Toplevel(self.app)
        win.title("加载历史监控数据")
        win.geometry("400x300")
        
        # ... (迁移完整 UI 逻辑) ...
        pass

    def open_ext_data_viewer(self, auto_update=False):
        """打开 55188 外部数据查看器"""
        if hasattr(self.app, '_ext_data_viewer_win') and self.app._ext_data_viewer_win.winfo_exists():
            self.app._ext_data_viewer_win.lift()
            return
            
        # ... (迁移完整 UI 逻辑) ...
        pass

    def open_realtime_monitor(self):
        """打开实时监控面板"""
        # ... (迁移完整 UI 逻辑) ...
        pass

    def open_column_manager(self):
        """打开列管理器"""
        if hasattr(self.app, 'ColumnSetManager') and self.app.ColumnSetManager is not None and self.app.ColumnSetManager.winfo_exists():
            self.app.ColumnSetManager.open_column_manager_editor()
        else:
            if hasattr(self.app, 'df_all') and not self.app.df_all.empty:
                # 迁移加载配置逻辑
                from gui_utils import load_display_config
                from instock_MonitorTK import CONFIG_FILE, DEFAULT_DISPLAY_COLS
                
                self.app.ColManagerconfig = load_display_config(config_file=CONFIG_FILE, default_cols=DEFAULT_DISPLAY_COLS)
                
                if hasattr(self.app, 'global_dict') and self.app.global_dict is not None:
                    self.app.global_dict['keep_all_columns'] = True 
                
                from column_set_manager import ColumnSetManager
                self.app.ColumnSetManager = ColumnSetManager(
                    self.app, 
                    self.app.df_all.columns,
                    self.app.ColManagerconfig,
                    self.app.update_treeview_cols, 
                    default_cols=getattr(self.app, 'current_cols', []),
                    logger=logger
                )
                self.app.ColumnSetManager.protocol("WM_DELETE_WINDOW", self.app.on_close_column_manager)
            else:
                self.app._schedule_after(1000, self.open_column_manager)

    def open_column_manager_init(self):
        """初始化列管理器并自动应用"""
        if hasattr(self.app, 'ColumnSetManager') and self.app.ColumnSetManager is not None and self.app.ColumnSetManager.winfo_exists():
            self.app.ColumnSetManager.open_column_manager_editor()
        else:
            if hasattr(self.app, 'df_all') and not self.app.df_all.empty:
                from gui_utils import load_display_config
                from instock_MonitorTK import CONFIG_FILE, DEFAULT_DISPLAY_COLS
                self.app.ColManagerconfig = load_display_config(config_file=CONFIG_FILE, default_cols=DEFAULT_DISPLAY_COLS)
                
                if hasattr(self.app, 'global_dict') and self.app.global_dict is not None:
                    self.app.global_dict['keep_all_columns'] = True
                
                from column_set_manager import ColumnSetManager
                self.app.ColumnSetManager = ColumnSetManager(
                    self.app, 
                    self.app.df_all.columns,
                    self.app.ColManagerconfig,
                    self.app.update_treeview_cols, 
                    default_cols=getattr(self.app, 'current_cols', []),
                    auto_apply_on_init=True
                )
                self.app.ColumnSetManager.protocol("WM_DELETE_WINDOW", self.app.on_close_column_manager)
            else:
                # 递归初始化，直到数据准备好
                self.app._schedule_after(1000, self.open_column_manager_init)

    def open_stock_detail(self, code):
        """点击概念窗口中股票代码弹出详情"""
        win = tk.Toplevel(self.app)
        win.title(f"股票详情 - {code}")
        win.geometry("400x300")
        
        # 使用 self.app 获取全局样式
        default_font_bold = getattr(self.app, 'default_font_bold', ("Arial", 10, "bold"))
        default_font = getattr(self.app, 'default_font', ("Arial", 10))
        
        tk.Label(win, text=f"正在加载个股 {code} ...", font=default_font_bold).pack(pady=10)

        # 如果有 df_filtered 数据，可以显示详细行情
        if hasattr(self.app, "_last_cat_dict"):
            for c, lst in self.app._last_cat_dict.items():
                for row_code, name in lst:
                    if row_code == code:
                        tk.Label(win, text=f"{row_code} {name}", font=default_font).pack(anchor="w", padx=10)
                        # 可以加更多字段，如 trade、涨幅等
