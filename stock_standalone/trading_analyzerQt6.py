from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QComboBox, QMenu, QTextEdit, QHeaderView, QDialog,
    QSpinBox, QSplitter, QCheckBox, QMainWindow, QTreeWidget, QTreeWidgetItem, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPoint, QEvent
from PyQt6.QtGui import QAction
import sys
import os
import pandas as pd
import numpy as np
from tk_gui_modules.window_mixin import WindowMixin
from dpi_utils import get_windows_dpi_scale_factor
import sqlite3
import json
import queue # ✅ Import queue
import math
from datetime import datetime, timedelta
from typing import Optional

# 假设 TradingAnalyzer 已经在同一目录
from trading_logger import TradingLogger
from trading_analyzer import TradingAnalyzer
from JohnsonUtil.stock_sender import StockSender
from scraper_55188 import load_cache
from stock_selector import StockSelector
# [REMOVED] from stock_selection_window import StockSelectionWindow (Tkinter dependency causing instability in PyQt)

class NumericTableWidgetItem(QTableWidgetItem):
    """自定义 TableWidgetItem，支持正确的数值排序"""
    def __init__(self, value):
        if isinstance(value, (int, float)):
            # 格式化显示，但保留原始数值用于比较
            display_val = f"{value:.2f}" if isinstance(value, float) else str(value)
            super().__init__(display_val)
            self.sort_value = value
        else:
            super().__init__(str(value))
            self.sort_value = str(value)

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            if isinstance(self.sort_value, (int, float)) and isinstance(other.sort_value, (int, float)):
                return self.sort_value < other.sort_value
        return super().__lt__(other)

class DetailTreeWindow(QDialog, WindowMixin):
    """
    可复用的股票详情树状窗口，显示开平仓、做T详情以及策略信号信息。
    """
    def __init__(self, stock_code: str, stock_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.stock_code: str = stock_code
        self.stock_name: str = stock_name
        self.setWindowTitle(f"个股详情 - {stock_name} ({stock_code})")
        # 尺寸
        self.scale_factor: float = get_windows_dpi_scale_factor()
        self.load_window_position_qt(self, f"DetailTreeWindow")
        
        self.main_layout = QVBoxLayout(self)
        
        # 顶部信息
        self.info_label = QLabel(f"<b>{stock_name}</b> ({stock_code}) 交易及信号明细")
        self.main_layout.addWidget(self.info_label)
        
        # 树形控件
        self.tree: QTreeWidget = QTreeWidget()
        self.tree.setHeaderLabels(["时间 / 分类", "动作 / 信号", "详情", "备注"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 150)
        self.tree.setColumnWidth(2, 250)
        self.tree.setAlternatingRowColors(True)
        self.main_layout.addWidget(self.tree)
        
        self.load_data()
        
    def load_data(self):
        # 创建根节点
        trade_root = QTreeWidgetItem(self.tree, ["交易记录 (开仓/平仓/做T)"])
        signal_root = QTreeWidgetItem(self.tree, ["策略信号记录"])
        
        # 抓取交易数据库
        # 注意：这里如果已经处于 TradingGUI 内部环境，可以考虑复用连接，或在此直接简单查询。
        try:
            from JohnsonUtil import commonTips as cct
            db_file_path = os.path.join(cct.get_base_path(), "trading_signals.db")
            with sqlite3.connect(db_file_path) as conn:
                # trade_records holds pairs of buy and sell. We split them into rows for display.
                query = """
                SELECT buy_date as timestamp, 'BUY' as action, buy_price as price, buy_amount as quantity, buy_reason as trigger_reason FROM trade_records WHERE code=?
                UNION ALL
                SELECT sell_date as timestamp, 'SELL' as action, sell_price as price, buy_amount as quantity, sell_reason as trigger_reason FROM trade_records WHERE code=? AND sell_date IS NOT NULL AND status='CLOSED'
                ORDER BY timestamp DESC LIMIT 100
                """
                df_trades = pd.read_sql_query(query, conn, params=(self.stock_code, self.stock_code))
        except Exception as e:
            df_trades = pd.DataFrame()
            print(f"Error fetching trades: {e}")
            
        if not df_trades.empty:
            for _, row in df_trades.iterrows():
                t = row.get('time', row.get('timestamp', ''))
                act = row.get('action', '')
                p = row.get('price', 0)
                q = row.get('quantity', 0)
                reason = row.get('trigger_reason', '')
                detail = f"价格: {p:.2f} 数量: {q}" if pd.notnull(p) else ""
                
                item = QTreeWidgetItem(trade_root, [str(t), str(act), detail, str(reason)])
                # 根据 action 涂色
                act_str = str(act).upper()
                if "BUY" in act_str or "ENTER" in act_str:
                    item.setForeground(1, Qt.GlobalColor.red)
                elif "SELL" in act_str or "EXIT" in act_str:
                    item.setForeground(1, Qt.GlobalColor.darkGreen)
        else:
            QTreeWidgetItem(trade_root, ["无记录", "-", "-", "-"])
            
        # 抓取信号数据库
        try:
            # Note: live_signal_history is in trading_signals.db instead of signal_strategy.db
            from JohnsonUtil import commonTips as cct
            db_file_path = os.path.join(cct.get_base_path(), "trading_signals.db")
            # db_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "trading_signals.db"))
            with sqlite3.connect(db_file_path) as conn:
                query = "SELECT timestamp, action as strategy_name, action as signal_type, price, reason as message FROM live_signal_history WHERE code=? ORDER BY timestamp DESC LIMIT 100"
                df_signals = pd.read_sql_query(query, conn, params=(self.stock_code,))
        except Exception as e:
            df_signals = pd.DataFrame()
            print(f"Error fetching signals: {e}")
            
        if not df_signals.empty:
            for _, row in df_signals.iterrows():
                t = row.get('timestamp', '')
                s_name = row.get('strategy_name', '')
                s_type = row.get('signal_type', '')
                msg = row.get('message', '')
                p = row.get('price', 0)
                
                detail = f"类型: {s_type} 触发价: {p:.2f}" if pd.notnull(p) else f"类型: {s_type}"
                
                item = QTreeWidgetItem(signal_root, [str(t), str(s_name), detail, str(msg)])
                item.setForeground(1, Qt.GlobalColor.blue)
        else:
            QTreeWidgetItem(signal_root, ["由于非交易时间过滤或无信号，当前无记录", "-", "-", "-"])
            
        self.tree.expandAll()

    def closeEvent(self, event):
        """覆盖关闭事件，保存窗口位置"""
        self.save_window_position_qt(self, f"DetailTreeWindow")
        super().closeEvent(event)

class HotSectorAnalysisDialog(QDialog, WindowMixin):
    """
    板块热点分析工具
    读取 concept_pg_data.db 统计热点，并关联个股
    """
    def __init__(self, parent=None, selector=None):
        try:
            super().__init__(parent)
            self.selector = selector
            self.setWindowTitle("板块热点分析")
            self.scale_factor = get_windows_dpi_scale_factor()
            self.resize(1000, 600)
            
            layout = QVBoxLayout()
            self.setLayout(layout)
            
            # 顶部控制
            top_layout = QHBoxLayout()
            layout.addLayout(top_layout)
            
            top_layout.addWidget(QLabel("回溯天数:"))
            self.days_spin = QSpinBox()
            self.days_spin.setRange(1, 30)
            self.days_spin.setValue(5)
            top_layout.addWidget(self.days_spin)
            
            self.analyze_btn = QPushButton("开始分析")
            self.analyze_btn.clicked.connect(self.load_data)
            top_layout.addWidget(self.analyze_btn)
            top_layout.addStretch()
            
            # 主要内容区域 (左右分栏)
            splitter = QSplitter(Qt.Orientation.Horizontal)
            layout.addWidget(splitter)
            
            # 左侧：热门板块列表
            left_widget = QWidget()
            left_layout = QVBoxLayout()
            left_widget.setLayout(left_layout)
            left_layout.addWidget(QLabel("热门板块排行 (基于持续性与强度)"))
            self.sector_table = QTableWidget()
            self.sector_table.setColumnCount(6)
            self.sector_table.setHorizontalHeaderLabels(["排名", "板块名称", "频次", "平均强度", "最新强度", "最新日期"])
            self.sector_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.sector_table.cellClicked.connect(self.on_sector_clicked)
            left_layout.addWidget(self.sector_table)
            splitter.addWidget(left_widget)
            
            # 右侧：龙头股列表
            right_widget = QWidget()
            right_layout = QVBoxLayout()
            right_widget.setLayout(right_layout)
            self.stock_label = QLabel("龙头股分析 (点击左侧板块查看)")
            right_layout.addWidget(self.stock_label)
            self.stock_table = QTableWidget()
            self.stock_table.setColumnCount(8)
            self.stock_table.setHorizontalHeaderLabels(["代码", "名称", "现价", "涨幅%", "主力排名", "来源", "日期/评分", "逻辑描述"])
            self.stock_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
            # 支持点击股票发送代码
            self.stock_table.cellClicked.connect(self.on_stock_clicked)
            # [NEW] 支持键盘上下键联动
            self.stock_table.currentCellChanged.connect(self.on_stock_cell_changed)
            right_layout.addWidget(self.stock_table)
            splitter.addWidget(right_widget)
            
            # 设置分栏比例
            splitter.setSizes([450, 750])
            
            self.db_path = "./concept_pg_data.db"
            
            # 延时加载以免卡顿启动
            QTimer.singleShot(500, self.load_data)
            
            # 加载窗口位置
            self.load_window_position_qt(self, "HotSectorDialog_Geometry", default_width=1000, default_height=600)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"HotSectorAnalysisDialog init error: {e}")

    def closeEvent(self, event):
        self.save_window_position_qt(self, "HotSectorDialog_Geometry")
        super().closeEvent(event)

    def load_data(self):
        days = self.days_spin.value()
        # 计算N天前的日期字符串 (YYYYMMDD)
        try:
            # 兼容可能的 diverse date format in DB, but DB creates with %Y%m%d
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            query = f"SELECT concept_name, date, init_data FROM concept_data WHERE date >= '{start_date}'"
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            # Aggregate
            sector_stats = {}
            for row in rows:
                name, date, json_str = row
                try:
                    data = json.loads(json_str) if json_str else {}
                    
                    scores = data.get('scores', [])
                    score = float(scores[0]) if isinstance(scores, list) and scores else 0
                    
                    pcts = data.get('avg_percents', [])
                    avg_pct = float(pcts[0]) if isinstance(pcts, list) and pcts else 0
                    
                    if name not in sector_stats:
                        sector_stats[name] = {'count': 0, 'total_score': 0, 'total_pct': 0, 'latest_score': 0, 'latest_date': ''}
                    
                    stats = sector_stats[name]
                    stats['count'] += 1
                    stats['total_score'] += score
                    stats['total_pct'] += avg_pct
                    if date > stats['latest_date']:
                        stats['latest_date'] = date
                        stats['latest_score'] = score
                        
                except Exception as e:
                    print(f"Error parsing row {name}: {e}")
                    
                
            # [NEW] 合并选股器中的热点数据 (通过 try-except 保护避免冷启动卡死或崩溃)
            if self.selector:
                try:
                    selector_hotspots = self.selector.get_market_hotspots()
                    for name, score in selector_hotspots:
                        if name in sector_stats:
                            # 如果已有，适当调高分数
                            sector_stats[name]['total_score'] += score
                            sector_stats[name]['count'] += 1
                            sector_stats[name]['latest_score'] = max(sector_stats[name]['latest_score'], score)
                        else:
                            # 如果没有，添加新热点
                            sector_stats[name] = {
                                'count': 1, 
                                'total_score': score, 
                                'total_pct': 0, 
                                'latest_score': score, 
                                'latest_date': datetime.now().strftime('%Y%m%d')
                            }
                except Exception as e:
                    print(f"Error integrating selector hotspots: {e}")
            
            # Re-convert to list and sort after merge
            result = []
            for name, stats in sector_stats.items():
                count = stats['count']
                total_score = stats.get('total_score', 0)
                avg_score = float(total_score) / count if count > 0 else 0.0
                result.append({
                    'name': name,
                    'count': count,
                    'avg_score': round(avg_score, 2),
                    'latest_score': round(float(stats.get('latest_score', 0)), 2),
                    'latest_date': stats.get('latest_date', '')
                })

            # Sort by count desc, then avg_score desc
            result.sort(key=lambda x: (x['count'], x['avg_score']), reverse=True)

            self.sector_table.setRowCount(0)
            self.sector_table.setSortingEnabled(False)
            self.sector_table.setRowCount(len(result))
            for i, item in enumerate(result):
                self.sector_table.setItem(i, 0, NumericTableWidgetItem(i+1))
                self.sector_table.setItem(i, 1, QTableWidgetItem(item['name']))
                self.sector_table.setItem(i, 2, NumericTableWidgetItem(item['count']))
                self.sector_table.setItem(i, 3, NumericTableWidgetItem(round(item['avg_score'], 2)))
                self.sector_table.setItem(i, 4, NumericTableWidgetItem(round(item['latest_score'], 2)))
                self.sector_table.setItem(i, 5, QTableWidgetItem(item['latest_date']))

            self.sector_table.setSortingEnabled(True)
            self.sector_table.resizeColumnsToContents()
            self.stock_label.setText(f"分析完成: 找到 {len(result)} 个热点板块 (近 {days} 天)")
            
        except Exception as e:
            self.stock_label.setText(f"数据库查询失败: {e}")
            
    def on_sector_clicked(self, row, col):
        name_item = self.sector_table.item(row, 1)
        if not name_item: return
        sector_name = name_item.text()
        self.stock_label.setText(f"正在分析板块: {sector_name} ...")
        QApplication.processEvents()
        
        self.find_leading_stocks(sector_name)
        
    def find_leading_stocks(self, sector_name):
        try:
            # 1. 加载 55188 缓存数据
            if self.parent() and hasattr(self.parent(), 'df_all') and not self.parent().df_all.empty:
                df = self.parent().df_all
            else:
                df = load_cache()
                
            scraper_list = pd.DataFrame() # Initialize as empty DataFrame
            if not df.empty:
                # 模糊匹配板块名称
                mask = (
                    df['theme_name'].astype(str).str.contains(sector_name, na=False) | 
                    df['hot_tag'].astype(str).str.contains(sector_name, na=False) |
                    df['sector'].astype(str).str.contains(sector_name, na=False)
                )
                scraper_list = df[mask].copy()
                if not scraper_list.empty:
                    scraper_list['source'] = "55188抓取"
                    # 整理理由信息
                    if 'theme_logic' in scraper_list.columns and 'hot_reason' in scraper_list.columns:
                        scraper_list['display_logic'] = scraper_list['theme_logic'].fillna('') + " / " + scraper_list['hot_reason'].fillna('')
                    elif 'theme_logic' in scraper_list.columns:
                        scraper_list['display_logic'] = scraper_list['theme_logic']
                    else:
                        scraper_list['display_logic'] = ""
            
            # 2. 从选股器候选池中抓取更精准的强势股 (实现互补)
            selector_list = pd.DataFrame()
            if self.selector:
                try:
                    candidates = self.selector.get_candidates_df()
                    if candidates is not None and not candidates.empty:
                        # 在候选池中查找关联板块的股票
                        # 优先查找 category 匹配的
                        c_mask = candidates['category'].astype(str).str.contains(sector_name, na=False) | \
                                 candidates['name'].astype(str).str.contains(sector_name, na=False)
                        selector_list = candidates[c_mask].copy()
                        
                        if not selector_list.empty:
                            selector_list['source'] = "选股系统"
                            # 选股器通常有更实时的 score
                            selector_list['display_logic'] = selector_list['reason'] if 'reason' in selector_list.columns else "强势推荐"
                            # 按照 score 排序，取前 5 只作为优选
                            if 'score' in selector_list.columns:
                                selector_list = selector_list.sort_values('score', ascending=False)
                except Exception as e:
                    print(f"Error fetching candidates from selector: {e}")
                        
            # 3. 合并与去重 (互补逻辑)
            # 策略：保留 55188 的广度，同时突出显示选股器的 3-5 只精选股
            top_selector = selector_list.head(5) if not selector_list.empty else pd.DataFrame()
            
            final_df = pd.DataFrame()
            if not top_selector.empty and not scraper_list.empty:
                # 合并，并确保 top_selector 在前
                codes_in_selector = top_selector['code'].tolist()
                scraper_remains = scraper_list[~scraper_list['code'].isin(codes_in_selector)]
                final_df = pd.concat([top_selector, scraper_remains], ignore_index=True)
            elif not top_selector.empty:
                final_df = top_selector
            elif not scraper_list.empty:
                final_df = scraper_list
                
            if final_df.empty:
                 self.stock_label.setText(f"板块 {sector_name}: 未找到关联个股 (互补搜索无结果)")
                 self.stock_table.setRowCount(0)
                 return
            
            # 4. 填充 UI
            self.stock_table.setRowCount(0)
            self.stock_table.setSortingEnabled(False)
            self.stock_table.setRowCount(len(final_df))
            
            for i, (_, row) in enumerate(final_df.iterrows()):
                code_val = str(row.get('code',''))
                self.stock_table.setItem(i, 0, QTableWidgetItem(code_val))
                
                name_val = str(row.get('name', code_val))
                self.stock_table.setItem(i, 1, QTableWidgetItem(name_val))
                
                price = row.get('price', 0)
                self.stock_table.setItem(i, 2, NumericTableWidgetItem(price))
                
                pct = row.get('change_pct', row.get('percent', 0))
                try:
                    # 兼容不同来源的涨幅格式 (55188 vs Selector)
                    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
                        f_pct = 0.0
                    else:
                        f_pct = float(pct)
                        
                    if f_pct > 1 or f_pct < -1: # 可能是 10.5 格式
                        pct_val = f_pct
                    else: # 可能是 0.105 格式 (scraper 默认 0.1 为 10%)
                        pct_val = f_pct * 100
                    self.stock_table.setItem(i, 3, NumericTableWidgetItem(round(pct_val, 2)))
                except:
                    self.stock_table.setItem(i, 3, QTableWidgetItem(str(pct)))
                
                # 55188 特有指标 或 Selector 继承的指标
                zhuli = row.get('zhuli_rank', row.get('net_ratio', '-'))
                if zhuli is None or (isinstance(zhuli, float) and np.isnan(zhuli)) or str(zhuli).lower() == 'nan':
                     zhuli = "-"
                self.stock_table.setItem(i, 4, QTableWidgetItem(str(zhuli)))
                
                # 来源
                src = row.get('source', '未知')
                self.stock_table.setItem(i, 5, QTableWidgetItem(src))
                
                # 日期/评分 (互补信息展示)
                # 如果是 55188，尝试拿 last_update；如果是 selector，拿 score
                date_score = ""
                if src == "选股系统":
                    score = row.get('score', 0)
                    date_score = f"评分:{score:.1f}"
                else:
                    # 尝试从 row 或全局 search 中获取该板块的时间
                    date_score = row.get('date', datetime.now().strftime('%m-%d'))
                self.stock_table.setItem(i, 6, QTableWidgetItem(str(date_score)))
                
                # 逻辑描述
                logic = row.get('display_logic', '')
                self.stock_table.setItem(i, 7, QTableWidgetItem(str(logic)))
            
            self.stock_table.setSortingEnabled(True)
            self.stock_table.resizeColumnsToContents()
            self.stock_label.setText(f"板块 {sector_name}: 找到 {len(final_df)} 只追踪个股 (含 {len(top_selector)} 只精选)")

        except Exception as e:
            self.stock_label.setText(f"分析个股失败: {e}")
            import traceback
            traceback.print_exc()

    def on_stock_clicked(self, row, col):
        # 仅当点击 code(0) 或 name(1) 列时才联动
        if col > 1: return
        
        code_item = self.stock_table.item(row, 0)
        if code_item and self.parent():
             code = code_item.text()
             try:
                 # Try to call parent's sender if available
                 if hasattr(self.parent(), '_safe_send_stock'):
                     self.parent()._safe_send_stock(code)
                     if hasattr(self.parent(), 'update_send_status'):
                         self.parent().update_send_status(f"已发送 {code}")
                     
                     # 尝试联动主界面的 scroll 信号
                     if hasattr(self.parent(), 'scroll_to_code_signal'):
                         self.parent().scroll_to_code_signal.emit(code)
            
                 elif hasattr(self.parent(), 'sender') and self.parent().sender:
                      # Fallback
                      self.parent().sender.send(code)
                      
             except Exception as e:
                 print(f"Error sending/linking code: {e}")

    def on_stock_cell_changed(self, row, col, prev_row, prev_col):
        """
        键盘上下键切换行时触发联动
        """
        if row < 0 or row == prev_row:
            return
        # 复用点击逻辑
        self.on_stock_clicked(row, col)

class TradingGUI(QWidget, WindowMixin):
    # 声明信号
    scroll_to_code_signal = pyqtSignal(str)
    send_status_signal = pyqtSignal(object)  # 可以接收任意对象，包括 dict
    def __init__(self, logger_path: Optional[str] = None, sender=None,on_tree_scroll_to_code =None, on_open_visualizer=None, selector=None, live_strategy=None):
        super().__init__()
        from JohnsonUtil import commonTips as cct
        if logger_path is None:
            logger_path = os.path.join(cct.get_base_path(), "trading_signals.db")
        
        self.scale_factor = get_windows_dpi_scale_factor()
        self.setWindowTitle("策略交易分析工具")
        # self.setGeometry(100, 100, 1000, 600)
        # self.center()  # 调用居中方法
        self.logger = TradingLogger(logger_path)
        self.analyzer = TradingAnalyzer(self.logger)
        
        # Load comprehensive stock list for name lookups
        try:
            self.df_all = load_cache()
        except Exception as e:
            print(f"Failed to load initial cache: {e}")
            self.df_all = pd.DataFrame()

        self.selector = selector
        if self.selector is None:
            self.selector = StockSelector(df=self.df_all)
        self.live_strategy = live_strategy

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # 初始化分页变量 (务必在连接任何会触发 refresh_table 的信号之前初始化)
        self.current_page = 1
        self.page_size = 200
        self.total_pages = 1
        self.cached_full_df = pd.DataFrame()
        self._data_cache = {}

        # 顶部：汇总信息
        self.label_summary = QLabel("总收益: 0, 平均收益率: 0%, 总笔数: 0")
        self.main_layout.addWidget(self.label_summary)

        # 顶部选择
        self.top_layout = QHBoxLayout()
        self.main_layout.addLayout(self.top_layout)

        # 独立启动K线开关
        self.vis_checkbox = QCheckBox("独立启动K线")
        self.vis_checkbox.setChecked(False) # 默认不选中，依赖主程序联动
        self.vis_checkbox.setToolTip("选中后，点击股票代码将启动新的 K 线可视化窗口。\n未选中时，仅发消息给主程序（如果已联动）。")
        self.top_layout.addWidget(self.vis_checkbox)

        # 数据源选择
        self.source_combo = QComboBox()
        self.source_combo.addItems(["交易/选股数据库", "实时策略信号库"])
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        self.top_layout.addWidget(QLabel("数据源:"))
        self.top_layout.addWidget(self.source_combo)

        self.view_combo = QComboBox()
        self.view_combo.addItems([
            "实时指标详情","股票汇总", "单只股票明细", "每日策略统计", "Top 盈利交易", "Top 亏损交易", "股票表现概览", "信号探测历史", "策略胜率排行", "绩效分析看板", "T+1 预判与做T策略"
        ])
        
        # ✅ UI 线程任务调度队列 (解决 Qt -> Tkinter 跨线程/GIL 问题)
        self.tk_dispatch_queue = queue.Queue()
        self.dispatch_timer = QTimer(self)
        self.dispatch_timer.timeout.connect(self._process_dispatch_queue)
        self.dispatch_timer.start(100) # Check every 100ms
        
        self.view_combo.currentTextChanged.connect(self.refresh_table)
        self.top_layout.addWidget(QLabel("视图选择:"))
        self.top_layout.addWidget(self.view_combo)
        
        # 时间区间过滤
        self.time_filter_combo = QComboBox()
        self.time_filter_combo.addItems([
            "全部", "只看今日", "近3天", "近1周", "近1月", "近3月"
        ])
        self.time_filter_combo.currentTextChanged.connect(self.refresh_table)
        self.top_layout.addWidget(QLabel("时间范围:"))
        self.top_layout.addWidget(self.time_filter_combo)
        
        # 工具栏菜单 (按钮形式)
        self.tools_btn = QPushButton("工具")
        self.tools_menu = QMenu(self)
        self.tools_menu.addAction("数据库诊断", self.show_db_diagnostics)
        self.tools_menu.addAction("清理非交易日脏数据", self.trigger_db_cleanup)
        self.tools_btn.setMenu(self.tools_menu)
        self.top_layout.addWidget(self.tools_btn)


        self.analysis_btn = QPushButton("生成分析报告")
        self.analysis_btn.clicked.connect(self.show_analysis_report)
        self.top_layout.addWidget(self.analysis_btn)
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.force_refresh_table)  # 强制清除缓存刷新
        self.top_layout.addWidget(self.refresh_btn)

        self.hotspot_btn = QPushButton("板块热点")
        self.hotspot_btn.clicked.connect(self.show_hot_sectors)
        self.top_layout.addWidget(self.hotspot_btn)

        # [DISABLED] 选股建议按钮因稳定性原因暂时移除，功能整合进板块热点。
        # self.selection_btn = QPushButton("选股建议")
        # self.selection_btn.setToolTip("打开策略选股器确认窗口 (人工复核)")
        # self.selection_btn.clicked.connect(self.show_stock_selection)
        # self.top_layout.addWidget(self.selection_btn)

        self.stock_input = QComboBox()
        self.stock_input.setEditable(True)
        
        self.clear_filter_btn = QPushButton("清空")
        self.clear_filter_btn.clicked.connect(lambda: self.stock_input.setCurrentText(""))
        self.top_layout.addWidget(self.clear_filter_btn)
        
        self.top_layout.addWidget(QLabel("代码过滤:"))
        self.top_layout.addWidget(self.stock_input)
        self.stock_input.currentTextChanged.connect(self.refresh_table)

        # 表格显示
        self.table = QTableWidget()
        self.main_layout.addWidget(self.table)

        # 添加底部分页导航条
        self.pagination_layout = QHBoxLayout()
        self.btn_first_page = QPushButton("<< 首页")
        self.btn_prev_page = QPushButton("< 上一页")
        self.label_page_info = QLabel("第 1 / 1 页 (共 0 条)")
        self.label_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_next_page = QPushButton("下一页 >")
        self.btn_last_page = QPushButton("尾页 >>")
        
        # 翻页按钮绑定
        self.btn_first_page.clicked.connect(self.first_page)
        self.btn_prev_page.clicked.connect(self.prev_page)
        self.btn_next_page.clicked.connect(self.next_page)
        self.btn_last_page.clicked.connect(self.last_page)
        
        self.pagination_layout.addStretch()
        self.pagination_layout.addWidget(self.btn_first_page)
        self.pagination_layout.addWidget(self.btn_prev_page)
        self.pagination_layout.addWidget(self.label_page_info)
        self.pagination_layout.addWidget(self.btn_next_page)
        self.pagination_layout.addWidget(self.btn_last_page)
        self.pagination_layout.addStretch()
        self.main_layout.addLayout(self.pagination_layout)

        # 底部日志/报告显示区域
        self.report_area = QTextEdit()
        self.report_area.setReadOnly(True)
        self.report_area.setVisible(False)
        self.main_layout.addWidget(self.report_area)

        self.on_tree_scroll_to_code = on_tree_scroll_to_code 

        # 绑定信号
        self.scroll_to_code_signal.connect(self._safe_scroll_to_code)
        self.send_status_signal.connect(self._safe_update_send_status)
        
        # === 股票发送器 ===
        if sender is not None:
            self.sender = sender
            if hasattr(self.sender, "callback"):
                original_cb = self.sender.callback
                def safe_callback(status_dict):
                    self.send_status_signal.emit(status_dict)
                    if callable(original_cb):
                        original_cb(status_dict)
                self.sender.callback = safe_callback
        else:
            self.sender = StockSender(callback=None)

        # 表格点击与切换信号
        _ = self.table.cellClicked.connect(self.on_table_row_clicked)
        _ = self.table.cellDoubleClicked.connect(self.on_table_double_clicked)
        _ = self.table.currentCellChanged.connect(self.on_current_cell_changed)
        
        # 添加右键菜单策略
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        _ = self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        # Load window position
        self.load_window_position_qt(self, "TradingGUI_Geometry", default_width=1000, default_height=600)

        # 初始化数据源相关
        from trading_logger import SignalStrategyLogger
        from trading_analyzer import StrategySignalAnalyzer
        
        self.signal_logger = SignalStrategyLogger()
        self.signal_analyzer = StrategySignalAnalyzer(self.signal_logger)
        
        # 记录浏览历史用于鼠标前后键导航
        self._stock_history = []
        self._history_index = -1
        
        # [FIX] 防止表格视图内部的视口(Viewport)截获并消耗掉侧键的点击
        self.table.viewport().installEventFilter(self)
        self.installEventFilter(self)
        
        # 初始刷新
        self.refresh_table()

    def eventFilter(self, obj, event):
        """全局拦截子控件的鼠标事件，确保前进/后退侧键在任何焦点下生效"""
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.BackButton:
                self.navigate_history(-1)
                return True
            elif event.button() == Qt.MouseButton.ForwardButton:
                self.navigate_history(1)
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        """支持鼠标侧键（前进/返回）进行历史导航"""
        if event.button() == Qt.MouseButton.BackButton:
            self.navigate_history(-1)
            event.accept()
        elif event.button() == Qt.MouseButton.ForwardButton:
            self.navigate_history(1)
            event.accept()
        else:
            super().mousePressEvent(event)

    def first_page(self):
        if self.current_page > 1:
            self.current_page = 1
            self._render_current_page()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_current_page()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._render_current_page()

    def last_page(self):
        if self.current_page < self.total_pages:
            self.current_page = self.total_pages
            self._render_current_page()

    def _render_current_page(self):
        if self.cached_full_df.empty:
            self.label_page_info.setText("第 1 / 1 页 (共 0 条)")
            self.display_df(self.cached_full_df)
            return
            
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_df = self.cached_full_df.iloc[start_idx:end_idx]
        
        total_rows = len(self.cached_full_df)
        self.label_page_info.setText(f"第 {self.current_page} / {self.total_pages} 页 (共 {total_rows} 条)")
        
        # 仅渲染切片后的数据
        self.display_df(page_df)

    def navigate_history(self, direction):
        if not self._stock_history: return
        new_index = self._history_index + direction
        if 0 <= new_index < len(self._stock_history):
            self._history_index = new_index
            state = self._stock_history[new_index]
            
            self._is_navigating_history = True
            try:
                # 1. 阻塞下拉框事件，避免由于设值产生连锁刷新反应
                self.source_combo.blockSignals(True)
                self.view_combo.blockSignals(True)
                self.stock_input.blockSignals(True)
                
                # 2. 恢复数据源
                prev_source = self.source_combo.currentText()
                new_source = state.get("source", "")
                if new_source and new_source != prev_source:
                    self.source_combo.setCurrentText(new_source)
                    self.view_combo.clear()
                    if new_source == "交易/选股数据库":
                        self.view_combo.addItems([
                            "实时指标详情", "股票汇总", "单只股票明细", "每日策略统计", "Top 盈利交易", "Top 亏损交易", "股票表现概览", "信号探测历史", "策略胜率排行", "绩效分析看板", "T+1 预判与做T策略"
                        ])
                    else:
                        self.view_combo.addItems([
                            "今日信号汇总", "所有信号流", "信号类型统计", "高频信号股"
                        ])

                # 3. 恢复视图和过滤代码
                self.view_combo.setCurrentText(state.get("view", ""))
                self.stock_input.setCurrentText(state.get("filter_code", ""))
                
                # 4. 取消阻塞
                self.source_combo.blockSignals(False)
                self.view_combo.blockSignals(False)
                self.stock_input.blockSignals(False)
                
                # 5. 精确只执行一次表格刷新
                self.refresh_table()

                # 6. 如果带有股票代码过滤或者有选中历史，则主动触发联动
                sel_code = state.get("selected_code", "")
                if not sel_code:
                    sel_code = state.get("filter_code", "")
                
                if sel_code:
                    self._safe_send_stock(sel_code)
                    self._last_selected_code = sel_code
                    # 同步选择表格行，但屏蔽表格信号避免触发新的点击事件
                    self.table.blockSignals(True)
                    try:
                        self._select_code_in_table(sel_code)
                    finally:
                        self.table.blockSignals(False)
                    
            finally:
                self._is_navigating_history = False

    def _select_code_in_table(self, code):
        for row in range(self.table.rowCount()):
            if self._get_stock_code_from_row(row) == code:
                self.table.selectRow(row)
                break

    def _add_to_history(self, state):
        if not state or not isinstance(state, dict): return
        
        # 避免连续重复记录相同的界面状态
        if self._stock_history and self._history_index >= 0:
            curr = self._stock_history[self._history_index]
            if curr.get("source") == state.get("source") and curr.get("view") == state.get("view") and curr.get("filter_code") == state.get("filter_code") and curr.get("selected_code") == state.get("selected_code"):
                return
            
        # 丢弃当前索引之后的所有记录（像浏览器历史一样分支）
        self._stock_history = self._stock_history[:self._history_index + 1]
        self._stock_history.append(state)
        
        # 限制历史记录上限
        if len(self._stock_history) > 100:
            self._stock_history.pop(0)
        else:
            self._history_index += 1

    def closeEvent(self, event):
        self.save_window_position_qt(self, "TradingGUI_Geometry")
        super().closeEvent(event)

    def _on_source_changed(self, text):
        """数据源切换处理"""
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        
        if text == "交易/选股数据库":
            self.view_combo.addItems([
                "实时指标详情", "股票汇总", "单只股票明细", "每日策略统计", "Top 盈利交易", "Top 亏损交易", "股票表现概览", "信号探测历史", "策略胜率排行", "绩效分析看板", "T+1 预判与做T策略"
            ])
        else:
            self.view_combo.addItems([
                "今日信号汇总", "所有信号流", "信号类型统计", "高频信号股"
            ])
            
        self.view_combo.blockSignals(False)
        self.refresh_table()

    def show_db_diagnostics(self):
        """显示数据库诊断信息"""
        source = self.source_combo.currentText()
        if source == "交易/选股数据库":
            inspector = self.logger # TradingLogger 继承了 DBInspector (如果在 logger 中 mixin 了的话)
            # 暂时 TradingLogger 没有 mixin，需确认。
            # 这里的 logger 是 TradingLogger 实例
            # 我们动态给它加一个 mixin 或者简单点，直接再实例化一个 Inspector
            from trading_logger import DBInspector
            inspector = DBInspector(self.logger.db_path)
            db_name = "Trading Signals DB"
        else:
            inspector = self.signal_logger
            db_name = "Signal Strategy DB"
            
        stats = inspector.get_db_stats()
        issues = inspector.run_health_check()
        
        msg = f"=== {db_name} 诊断报告 ===\n\n"
        msg += f"[统计信息]\n"
        for table, count in stats.get('tables', {}).items():
            msg += f"  - 表 {table:<20}: {count} 行\n"
            
        msg += f"\n[健康检查]\n"
        if not issues:
            msg += "  ✅未发现明显异常。\n"
        else:
            for issue in issues:
                msg += f"  ❌ {issue}\n"
                
        self.report_area.setPlainText(msg)
        self.report_area.setVisible(True)
        self.table.setVisible(False)

    def center(self):
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.geometry()
            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2
            self.move(x, y)

    def show_analysis_report(self):
        """生成并显示文本分析报告"""
        from generate_analysis_report import generate_report
        generate_report()
        try:
            with open("analysis_report_output.txt", "r", encoding="utf-8") as f:
                report_text = f.read()
            self.report_area.setPlainText(report_text)
            self.report_area.setVisible(True)
            self.table.setVisible(False)
        except Exception as e:
            self.report_area.setPlainText(f"生成报告失败: {e}")
            self.report_area.setVisible(True)

    def force_refresh_table(self):
        """强制清空本地查询缓存并进行数据库深刷"""
        if hasattr(self, '_data_cache'):
            self._data_cache.clear()
        self.refresh_table()

    def refresh_table(self, *args):
        # 切换显示状态
        self.report_area.setVisible(False)
        self.table.setVisible(True)
        
        # 获取当前源和视图
        source = self.source_combo.currentText()
        view = self.view_combo.currentText()
        code = self.stock_input.currentText().strip()
        
        if not getattr(self, '_is_navigating_history', False):
            # 获取上一次点击/查看的合法标的
            last_sel = getattr(self, '_last_selected_code', "")
            self._add_to_history({
                "source": source,
                "view": view,
                "filter_code": code,
                "selected_code": last_sel
            })
            
        # 极速缓存验证：默认只基于 (source, view) 做缓存，从而让代码和时间区间的过滤完全依靠 Pandas 内存极速切片！
        cache_key = (source, view)
        if view == "单只股票明细":
            # 精细到代码级别的视图保留原样
            cache_key = (source, view, code)
            
        now = datetime.now()
        use_cache = False
        if hasattr(self, '_data_cache') and cache_key in self._data_cache:
            cached_item = self._data_cache[cache_key]
            if (now - cached_item['time']).total_seconds() < 1800: # 30分钟
                df = cached_item['df'].copy()
                use_cache = True

        if not use_cache:
            df = pd.DataFrame()

            if source == "交易/选股数据库":
                self.update_stock_list_traditional()
            
            if view == "股票汇总":
                df = self.analyzer.summarize_by_stock()
            elif view == "单只股票明细":
                df = self.analyzer.get_stock_detail(code) if code else pd.DataFrame()
            elif view == "每日策略统计":
                df = self.analyzer.daily_summary()
            elif view == "绩效分析看板":
                self.refresh_performance_dashboard()
                return
            elif view == "Top 盈利交易":
                df = self.analyzer.top_trades(n=10, largest=True)
            elif view == "Top 亏损交易":
                df = self.analyzer.top_trades(n=10, largest=False)
            elif view == "股票表现概览":
                df = self.analyzer.stock_performance()
            elif view == "信号探测历史":
                # 统一取全量历史交由缓存和前端 Pandas 光速切片，避免频繁打击后端
                df = self.analyzer.get_signal_history_df(code=None)
            elif view == "实时指标详情":
                # 统一取全量历史交由缓存和前端 Pandas 光速切片
                df = self.analyzer.get_signal_history_df(code=None)
                # 指标列筛选
                indicator_cols = ['date', 'code', 'name', 'price', 'action', 'reason',
                                'buy_reason', 'sell_reason', 'time_msg',
                                'ma5d', 'ma10d', 'ratio', 'volume', 'percent',
                                'high', 'low', 'open', 'nclose',
                                'highest_today', 'pump_height', 'pullback_depth',
                                'win', 'red', 'gren', 'structure']
                if not df.empty:
                    existing_cols = [c for c in indicator_cols if c in df.columns]
                if not df.empty:
                    existing_cols = [c for c in indicator_cols if c in df.columns]
                    df = df[existing_cols]
            elif view == "策略胜率排行":
                # [P2] Sync stats from Trade Logs to Hub
                try:
                    self.analyzer.compute_and_sync_strategy_stats()
                except Exception as e:
                    print(f"Stats sync failed: {e}")
                    
                # Prefer Hub data
                df = self.analyzer.get_hub_strategy_stats()
                if df.empty:
                     # Fallback to stock performance if no specific strategy data
                     df = self.analyzer.stock_performance()
            elif view == "T+1 预判与做T策略":
                self.refresh_t1_strategy_dashboard()
                return
        else:
            # 实时策略信号库
            if view == "今日信号汇总":
                df = self.signal_analyzer.get_todays_signal_counts()
                
                # [NEW] Re-order and rename columns for display
                if not df.empty:
                    # Ensure pattern_cn exists (it should from analyzer)
                    if 'pattern_cn' not in df.columns:
                         df['pattern_cn'] = df['pattern']
                    
                    # Select useful columns
                    cols_to_show = ['code', 'pattern', 'pattern_cn', 'count', 'last_trigger']
                    # Filter existing columns
                    cols_to_show = [c for c in cols_to_show if c in df.columns]
                    df = df[cols_to_show]
                    
                    # Rename for UI
                    df.rename(columns={
                        'pattern': 'Signal ID',
                        'pattern_cn': '策略名称',
                        'count': '触发次数',
                        'last_trigger': '最后触发时间'
                    }, inplace=True)
            elif view == "所有信号流":
                df = self.signal_analyzer.get_signal_message_df()
            elif view == "信号类型统计":
                df = self.signal_analyzer.summarize_signals_by_type()
            elif view == "高频信号股":
                df = self.signal_analyzer.summarize_signals_by_code()

            # 保存至大表全局缓存 (未执行过滤的状态)
            if not hasattr(self, '_data_cache'):
                self._data_cache = {}
            self._data_cache[cache_key] = {'time': now, 'df': df.copy() if not df.empty else pd.DataFrame()}

        # ---------------- 内存级极速切片区 ---------------- #

        # 代码级别过滤 (依赖 Pandas 内存过滤实现秒出)
        if code and not df.empty and 'code' in df.columns:
            df = df[df['code'].astype(str) == str(code)]

        # 时间区间过滤
        if not df.empty and 'date' in df.columns:
            time_filter = self.time_filter_combo.currentText()
            now = datetime.now()
            start_date_str = None
            if time_filter == "只看今日":
                start_date_str = now.strftime('%Y%m%d')
                if '-' in str(df['date'].iloc[0]): start_date_str = now.strftime('%Y-%m-%d')
            elif time_filter == "近3天":
                start_date_str = (now - timedelta(days=3)).strftime('%Y%m%d')
                if '-' in str(df['date'].iloc[0]): start_date_str = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            elif time_filter == "近1周":
                start_date_str = (now - timedelta(days=7)).strftime('%Y%m%d')
                if '-' in str(df['date'].iloc[0]): start_date_str = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            elif time_filter == "近1月":
                start_date_str = (now - timedelta(days=30)).strftime('%Y%m%d')
                if '-' in str(df['date'].iloc[0]): start_date_str = (now - timedelta(days=30)).strftime('%Y-%m-%d')
            elif time_filter == "近3月":
                start_date_str = (now - timedelta(days=90)).strftime('%Y%m%d')
                if '-' in str(df['date'].iloc[0]): start_date_str = (now - timedelta(days=90)).strftime('%Y-%m-%d')
            
            if start_date_str:
                df = df[df['date'].astype(str) >= start_date_str]
        elif not df.empty and 'timestamp' in df.columns:
            time_filter = self.time_filter_combo.currentText()
            now = datetime.now()
            start_date_str = None
            if time_filter == "只看今日":
                start_date_str = now.strftime('%Y-%m-%d 00:00:00')
            elif time_filter == "近3天":
                start_date_str = (now - timedelta(days=3)).strftime('%Y-%m-%d 00:00:00')
            elif time_filter == "近1周":
                start_date_str = (now - timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
            elif time_filter == "近1月":
                start_date_str = (now - timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')
            elif time_filter == "近3月":
                start_date_str = (now - timedelta(days=90)).strftime('%Y-%m-%d 00:00:00')
                
            if start_date_str:
                df = df[df['timestamp'].astype(str) >= start_date_str]

        # 缓存数据并计算分页
        self.cached_full_df = df
        self.current_df = df
        self.total_pages = max(1, math.ceil(len(self.cached_full_df) / self.page_size))
        self.current_page = 1

        # 渲染当页表格
        self._render_current_page()

        # 更新总收益摘要
        if source == "交易/选股数据库":
            self.refresh_summary_label()
        else:
            self.label_summary.setText(f"当前视图总记录数: {len(self.cached_full_df)}")

    def refresh_t1_strategy_dashboard(self):
        """[T+1系统] 生成每日预埋价和全景复盘"""
        self.report_area.setVisible(False)
        self.table.setVisible(True)
        
        try:
            from trading_hub import get_trading_hub
            from t1_strategy_engine import T1StrategyEngine
            hub = get_trading_hub()
            t1_engine = T1StrategyEngine()
            
            # 聚合目标池：持仓 + 跟单队列 + 热点观察
            targets = []
            
            # 1. 持仓
            for pos in hub.get_positions("HOLDING"):
                targets.append({"code": pos.code, "name": pos.name, "source": "实盘持仓", "cost": pos.entry_price})
            # 2. 跟单
            for fq in hub.get_follow_queue():
                if fq.status not in ("EXITED", "CANCELLED", "ENTERED"): # ENTERED is covered by positions
                    targets.append({"code": fq.code, "name": fq.name, "source": f"跟单: {fq.status}", "cost": fq.entry_price})
            
            # 构造 DataFrame
            result_rows = []
            # 获取实时快照以计算均线 (借助 live_strategy.df)
            live_df = None
            if self.live_strategy and hasattr(self.live_strategy, 'df') and self.live_strategy.df is not None:
                live_df = self.live_strategy.df
            
            # 去重
            seen = set()
            for t in targets:
                code = t['code']
                if code in seen: continue
                seen.add(code)
                
                row_snap = {}
                current_price = 0.0
                high_today = 0.0
                if live_df is not None and code in live_df.index:
                    row_snap = live_df.loc[code].to_dict()
                    current_price = float(row_snap.get('trade', row_snap.get('price', 0)))
                    high_today = float(row_snap.get('high', current_price))
                
                # Use engine to calc targets
                t1_engine.refresh_targets(code, row_snap, current_price)
                t_info = t1_engine.target_cache.get(code, {})
                
                trend = t_info.get('trend', '未知')
                trend_val = trend.value if hasattr(trend, 'value') else trend
                buy_target = t_info.get('buy_target', 0.0)
                sell_target = t_info.get('sell_target', 0.0)
                atr = t_info.get('atr', 0.0)
                
                # Calc trailing stop distance
                atr_multiplier = 1.2 if trend_val == '主升浪' else 0.8
                trailing_stop = high_today - (atr * atr_multiplier) if high_today > 0 else 0.0
                
                result_rows.append({
                    "代码": code,
                    "名称": t['name'],
                    "现价": f"{current_price:.2f}" if current_price > 0 else "N/A",
                    "成本/均价": f"{t['cost']:.2f}" if t['cost'] > 0 else "-",
                    "趋势定性": trend_val,
                    "建议买点(支撑)": f"{buy_target:.2f}",
                    "建议卖点(阻力)": f"{sell_target:.2f}",
                    "离场防线(ATR)": f"{trailing_stop:.2f}" if trailing_stop > 0 else "-",
                    "波幅(ATR)": f"{atr:.2f}",
                    "队列组": t['source'],
                    "分析时间": t_info.get('last_time', t_info.get('last_update', ''))
                })
                
            df = pd.DataFrame(result_rows)
            # Reorder
            if not df.empty:
                df = df[["代码", "名称", "分析时间", "队列组", "趋势定性", "现价", "成本/均价", "建议买点(支撑)", "建议卖点(阻力)", "离场防线(ATR)", "波幅(ATR)"]]
            
            self.current_df = df
            self.display_df(df)
            self.label_summary.setText(f"T+1 预判策略加载完毕 | 共 {len(df)} 只活动标的")
        except Exception as e:
            self.report_area.setPlainText(f"T+1 分析面板加载失败:\n{e}")
            self.report_area.setVisible(True)
            self.table.setVisible(False)

    def refresh_performance_dashboard(self):
        """[P7] 绩效看板聚合逻辑"""
        self.table.setVisible(False)
        self.report_area.setVisible(True)
        
        # 强制同步一次
        self.analyzer.compute_and_sync_strategy_stats()
        
        # 获取汇总指标
        trades_df = self.analyzer.get_all_trades_df()
        if trades_df.empty:
            self.report_area.setPlainText("暂无完成交易数据")
            return
            
        closed = trades_df[trades_df['status'] == 'CLOSED']
        total_pnl = closed['profit'].sum()
        total_trades = len(closed)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        try:
            from trading_hub import get_trading_hub
            hub = get_trading_hub()
            summary_df = hub.get_strategy_performance(days=30)
            slippage_summary = hub.get_slippage_summary(days=30)
        except:
            summary_df = pd.DataFrame()
            slippage_summary = {}
        
        display_text = f"=== 账户绩效总览 (最近30日) ===\n"
        display_text += f"总盈亏: {total_pnl:.2f} | 总笔数: {total_trades} | 平均笔盈亏: {avg_pnl:.2f}\n\n"
        display_text += "策略表现 (胜率/盈亏):\n"
        display_text += "-" * 50 + "\n"
        
        if not summary_df.empty:
            # [FIX] KeyError: 'pnl' if the column is renamed or missing
            sort_col = 'pnl' if 'pnl' in summary_df.columns else ('profit' if 'profit' in summary_df.columns else None)
            if sort_col:
                summary_df = summary_df.sort_values(sort_col, ascending=False)
            
            for _, row in summary_df.iterrows():
                entered_count = row.get('entered', 0)
                wins_count = row.get('wins', 0)
                win_rate = (wins_count / entered_count * 100) if entered_count > 0 else 0
                pnl_val = row.get('pnl', row.get('profit', 0))
                display_text += f" {row['strategy_name']:<18}: 胜率 {win_rate:>5.1f}% | 笔数 {row['entered']:>3} | 盈亏 {pnl_val:>9.2f}\n"
        else:
            display_text += " (暂无策略统计信息)\n"
        
        # === 入场滑点分析 ===
        display_text += "\n" + "=" * 50 + "\n"
        display_text += "=== 入场滑点分析 ===\n"
        display_text += "-" * 50 + "\n"
        
        if slippage_summary.get('total_entries', 0) > 0:
            total_entries = slippage_summary['total_entries']
            avg_slip = slippage_summary['avg_slippage_pct']
            chase_high = slippage_summary['chase_high_count']
            accurate = slippage_summary['accurate_count']
            catch_low = slippage_summary['catch_low_count']
            
            display_text += f"入场总数: {total_entries} | 平均滑点: {avg_slip:+.2f}%\n"
            display_text += f"  追高入场: {chase_high} ({chase_high/total_entries*100:.1f}%)\n"
            display_text += f"  准确入场: {accurate} ({accurate/total_entries*100:.1f}%)\n"
            display_text += f"  低吸入场: {catch_low} ({catch_low/total_entries*100:.1f}%)\n"
            
            # 按信号类型分解
            by_signal = slippage_summary.get('by_signal_type', {})
            if by_signal:
                display_text += "\n按信号类型:\n"
                for sig_type, stats in by_signal.items():
                    display_text += f"  {sig_type:<12}: 平均 {stats['slippage_pct']:+.2f}% ({stats['count']}笔)\n"
        else:
            display_text += " (暂无入场滑点数据)\n"
        
        self.report_area.setPlainText(display_text)

    def refresh_summary_label(self):
        df_all = self.analyzer.get_all_trades_df()
        if not df_all.empty:
            df_closed = df_all[df_all['status']=='CLOSED']
            total_profit = df_closed['profit'].sum()
            avg_pct = df_closed['pnl_pct'].mean() if not df_closed.empty else 0
            total_count = len(df_closed)
            self.label_summary.setText(
                f"总收益: {total_profit:.2f}, 平均收益率: {avg_pct*100:.2f}%, 总笔数: {total_count}"
            )
        else:
            self.label_summary.setText("总收益: 0, 平均收益率: 0%, 总笔数: 0")

    def update_stock_list(self):
        """兼容旧接口"""
        self.update_stock_list_traditional()
        
    def update_stock_list_traditional(self):
        # 仅在需要代码过滤的视图下更新下拉列表
        view = self.view_combo.currentText()
        if view not in ["单只股票明细", "信号探测历史", "实时指标详情"]:
            return

        # 根据视图类型决定数据源
        if view in ["信号探测历史", "实时指标详情"]:
            df_source = self.analyzer.get_signal_history_df()
        else:
            df_source = self.analyzer.get_all_trades_df()

        if df_source.empty:
            codes = []
        else:
            codes = sorted(df_source['code'].unique().tolist())
        
        # 添加一个空选项，方便用户取消过滤
        if codes and "" not in codes:
            codes.insert(0, "")

        # 保存当前选中值
        current_code = self.stock_input.currentText().strip()

        # 如果下拉列表内容没有变化，就不更新，避免触发信号循环
        existing_items = [self.stock_input.itemText(i) for i in range(self.stock_input.count())]
        if existing_items != codes:
            self.stock_input.blockSignals(True)
            self.stock_input.clear()
            self.stock_input.addItems(codes)
            if current_code in codes:
                self.stock_input.setCurrentText(current_code)
            else:
                self.stock_input.setCurrentText("")
            self.stock_input.blockSignals(False)

    def display_df(self, df: pd.DataFrame):
        self.table.setUpdatesEnabled(False)  # 开启离线绘制，禁止每次 setItem 都重绘UI，这是极速丝滑的关键
        self.table.clear()
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table.setUpdatesEnabled(True)
            return

        # 填充数据期间关闭排序
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        # 列名转换字典 (扩充了信号相关列)
        col_mapping = {
            'date': '日期', 'code': '代码', 'name': '名称', 'price': '价格', 'action': '动作', 
            'reason': '理由', 'buy_reason': '买入原因', 'sell_reason': '卖出原因', 'time_msg': '时间窗口',
            'buy_date': '买入日期', 'sell_date': '卖出日期', 'buy_price': '买入价', 'sell_price': '卖出价',
            'buy_amount': '买入量', 'profit': '盈亏', 'pnl_pct': '收益率', 'status': '状态',
            'total_profit': '总盈亏', 'avg_pnl_pct': '均收益率', 'total_bought': '总买入量',
            'open_positions': '持仓数', 'last_buy_reason': '最后买入原因', 'last_sell_reason': '最后卖出原因',
            'ma5d': 'MA5', 'ma10d': 'MA10', 'ratio': '换手', 'volume': '量比', 'percent': '涨幅%',
            'high': '最高', 'low': '最低', 'open': '开盘', 'nclose': '当日均价',
            'highest_today': '今日峰值', 'pump_height': '冲高高度', 'pullback_depth': '回落深度',
            'win': '胜率', 'red': '阳线', 'gren': '阴线', 'structure': '结构',
            # 新增信号库列名
            'signal_type': '信号类型', 'timestamp': '时间戳', 'source': '来源', 'priority': '优先级',
            'score': '评分', 'created_date': '创建日期', 'evaluated': '已评估', 'count': '计数',
            # 新增策略统计列名
            'strategy_name': '策略名称', 'total_trades': '交易数', 'win_rate': '胜率', 
            'avg_profit': '平均盈利', 'max_drawdown': '最大回撤', 'sharpe': '夏普比率', 
            'profit_factor': '盈亏比'
        }
        display_cols = [col_mapping.get(c, c) for c in df.columns]
        self.table.setHorizontalHeaderLabels(display_cols)

        for i, row in enumerate(df.itertuples(index=False)):
            for j, value in enumerate(row):
                # 处理空值
                display_value = "" if pd.isna(value) else value
                item = NumericTableWidgetItem(display_value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # 特色染色逻辑：盈亏染色
                raw_col_name = str(df.columns[j]).lower()
                if any(k in raw_col_name for k in ["profit", "pnl", "return", "percent"]):
                    try:
                        f_val = float(value)
                        if f_val > 0: 
                            item.setForeground(Qt.GlobalColor.red)
                        elif f_val < 0: 
                            item.setForeground(Qt.GlobalColor.darkGreen)
                    except: 
                        pass
                
                # 信号类型染色
                if raw_col_name == "signal_type":
                    if "buy" in str(value).lower() or "enter" in str(value).lower():
                         item.setForeground(Qt.GlobalColor.red)
                    elif "sell" in str(value).lower() or "exit" in str(value).lower():
                         item.setForeground(Qt.GlobalColor.darkGreen)

                self.table.setItem(i, j, item)
        
        # 填充完成后开启排序
        self.table.setSortingEnabled(True)
        # 移除致命的性能杀手 self.table.resizeColumnsToContents() 
        # 它会挨个像素遍历 4000 个格子的字体大小，清空过滤的卡顿根本原因就在这
        
        # 限制高度文本列的宽度
        header = self.table.horizontalHeader()
        for j, col_name in enumerate(df.columns):
            raw_target = col_name.lower()
            if any(k in raw_target for k in ["reason", "msg", "feedback", "indicators"]):
                self.table.setColumnWidth(j, 250)
                header.setSectionResizeMode(j, QHeaderView.ResizeMode.Interactive)
            elif any(k in raw_target for k in ["time", "date"]):
                self.table.setColumnWidth(j, 150)
            elif any(k in raw_target for k in ["code", "name", "action", "signal_type"]):
                if self.table.columnWidth(j) < 60:
                    self.table.setColumnWidth(j, 80)
            else:
                if self.table.columnWidth(j) < 60:
                    self.table.setColumnWidth(j, 90)
                
        self.table.setUpdatesEnabled(True) # 恢复 UI 绘制

    def get_current_df(self):
        return getattr(self, "current_df", None)

    def update_send_status(self, msg: str):
        self.label_summary.setText(f"发送状态: {msg}")

    def on_current_cell_changed(self, row: int, column: int, prev_row: int, _: int):
        """
        当通过键盘上下键切换行时，也触发发送
        """
        if row < 0 or row == prev_row:
            return
        
        # 对于按键切换，我们放宽限制：只要行变了，就尝试发送（不强制要求特定列）
        self._trigger_stock_linkage(row, column, force_send=True)

    def on_table_row_clicked(self, row: int, column: int):
        """
        仅当点击 code / name 列时，发送股票代码
        """
        self._trigger_stock_linkage(row, column, force_send=False)
        
    def on_table_double_clicked(self, row: int, column: int):
        """
        双击行时：
        1. 如果是 T+1 预判策略，或者直接展示代码详情：弹出树形明细窗口
        2. 否则，如果不弹窗，也可以选择过滤该股票
        """
        stock_code = self._get_stock_code_from_row(row)
        if not stock_code:
            return
            
        stock_name = ""
        # 尝试顺便拿一下名称
        for j in range(self.table.columnCount()):
            h_item = self.table.horizontalHeaderItem(j)
            if h_item and h_item.text() in ("名称", "name"):
                name_item = self.table.item(row, j)
                if name_item:
                    stock_name = name_item.text().strip()
                break
                
        self._last_selected_code = stock_code
        
        # 弹出独立的 TreeWindow
        # 我们把它保存为实例属性防止被垃圾回收
        self.detail_tree_widget = DetailTreeWindow(stock_code, stock_name, parent=self)
        self.detail_tree_widget.show()
        
        # 联动后台发送
        self.tree_scroll_to_code(stock_code)

    def trigger_db_cleanup(self):
        """弹出确认选项，然后执行非交易日脏数据清理。"""
        reply = QMessageBox.question(
            self,
            "清理非交易日数据",
            "是否确认清理数据库中所有源自非交易日（如周末测试）的脏数据记录？\n这可能需要一小段时间。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Dynamically import so we dont have circular dependencies
                import clean_db_script
                clean_db_script.clean_non_trading_days()
                QMessageBox.information(self, "清理完成", "非交易日数据清理已完成！您可以点击刷新查看最新数据。")
                self.force_refresh_table()
            except Exception as e:
                QMessageBox.critical(self, "清理失败", f"清理过程中发生错误: {e}")

    def _trigger_stock_linkage(self, row: int, column: int, force_send: bool = False):
        """
        统一的触发发送逻辑
        :param force_send: 如果为 True，则忽略列过滤
        """
        # 检查触发列
        if not force_send:
            header_item = self.table.horizontalHeaderItem(column)
            if not header_item:
                return
            header_text = header_item.text()
            # 汉化映射后的列名
            trigger_headers = {"代码", "名称", "code", "name"}
            if header_text not in trigger_headers:
                return

        # 获取当前行的股票代码
        stock_code = self._get_stock_code_from_row(row)
        if stock_code:
            # 去重：如果连续点击同一个，不需要重复记录历史和发送
            if getattr(self, '_last_selected_code', None) == stock_code and not force_send:
                return
            self._last_selected_code = stock_code
                
            if not getattr(self, '_is_navigating_history', False):
                self._add_to_history({
                    "source": self.source_combo.currentText(),
                    "view": self.view_combo.currentText(),
                    "filter_code": self.stock_input.currentText().strip(),
                    "selected_code": stock_code
                })
            # use safe send via queue
            if hasattr(self, 'sender') and self.sender:
                self._safe_send_stock(stock_code)


    def _get_stock_code_from_row(self, row: int) -> str:
        """从表格行中精确检索股票代码"""
        if row < 0:
            return ""
        
        # 遍历列头找到代码列
        for j in range(self.table.columnCount()):
            h_item = self.table.horizontalHeaderItem(j)
            if h_item and h_item.text() in ("代码", "code", "ts_code"):
                code_item = self.table.item(row, j)
                if code_item:
                    return code_item.text().strip()
        return ""

    def show_context_menu(self, pos):
        """显示右键菜单"""
        item = self.table.itemAt(pos)
        if item is None:
            return

        row = item.row()
        stock_code = self._get_stock_code_from_row(row)
        if not stock_code:
            return

        menu = QMenu(self)
        locate_action = QAction(f"定位股票代码: {stock_code}", self)
        locate_action.triggered.connect(
            lambda: self.tree_scroll_to_code(stock_code)
        )
        menu.addAction(locate_action)
        
        # 只有一项菜单时直接执行
        if menu.actions():
            if len(menu.actions()) == 1:
                QTimer.singleShot(0, lambda: self.tree_scroll_to_code(stock_code))
            else:
                menu.exec(self.table.mapToGlobal(pos))
        

    def tree_scroll_to_code(self, stock_code):
        """线程安全调用"""
        self.scroll_to_code_signal.emit(stock_code)

    def _safe_scroll_to_code(self, stock_code):
        """Qt 主线程执行"""
        if self.on_tree_scroll_to_code and callable(self.on_tree_scroll_to_code):
            try:
                self.stock_input.blockSignals(True)
                self.stock_input.setCurrentText(stock_code)
                self.stock_input.blockSignals(False)
                self.refresh_table() # 强制更新以响应外来联动
                self.on_tree_scroll_to_code(stock_code,vis=True)
            except Exception as e:
                print(f"on_tree_scroll_to_code error: {e}")
        else:
            # 降级方案：如果是独立的，尝试更新输入框
            self.stock_input.blockSignals(True)
            self.stock_input.setCurrentText(stock_code)
            self.stock_input.blockSignals(False)
            self.refresh_table() # 联动独立窗口
            
    def _safe_update_send_status(self, msg):
        """Qt 主线程安全更新状态"""
        self.label_summary.setText(f"发送状态: {msg}")

    def show_hot_sectors(self):
        """显示板块热点分析工具"""
        # 使用非模态对话框，方便与主界面交互
        self._hot_dlg = HotSectorAnalysisDialog(self, selector=self.selector)
        self._hot_dlg.show()
    
    def show_stock_selection(self):
        """[DISABLED] 此功能涉及 Tk/Qt 混用不佳，暂时关闭"""
        print("Stock selection window is currently disabled for stability.")
    
    def _safe_send_stock(self, code):
        """Send stock code via sender using dispatch queue (Queue Mode)"""
        if hasattr(self, 'sender') and self.sender:
            # We wrap the send call in a lambda or pass the method directly
            # Since sender.send(code) spawns a thread, calling it from Main Thread (via queue) is safe
            # IF StockSender thread-safety fix is applied.
            # But "Queue Mode" implies we execute it via the queue consumer.
            self.tk_dispatch_queue.put(lambda: self.sender.send(code))
    
    def _process_dispatch_queue(self):
        """
        [FIX] 专门处理从 Qt 回调或其他非主线程发来的 Tkinter 任务。
        避免直接在 Qt 线程调用 Tkinter (self.after 也不行)。
        """
        try:
            while True:
                # 非阻塞获取任务
                task = self.tk_dispatch_queue.get_nowait()
                if callable(task):
                    try:
                        task()
                    except Exception as e:
                        print(f"Error executing dispatched task: {e}")
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Dispatch Error: {e}")

    def _launch_visualizer_process(self, code):
        """Actual subprocess launch logic, runs safely from main thread via timer"""
        import subprocess
        import sys
        import os
        try:
            # Assuming trade_visualizer_qt6.py is in the same directory
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_visualizer_qt6.py")
            if os.path.exists(script_path):
                # Use the same python interpreter
                # FIX: Must use -code argument for argparse
                subprocess.Popen([sys.executable, script_path, "-code", code])
                print(f"Launched visualizer for {code}")
            else:
                print(f"Visualizer script not found at {script_path}")
        except Exception as e:
            print(f"Failed to launch visualizer: {e}")

    def open_visualizer(self, code):
        """Open the visualizer for the given stock code (via dispatch queue)"""
        # check if visualizer is enabled
        if hasattr(self, 'vis_checkbox') and not self.vis_checkbox.isChecked():
            return
            
        # Put the task into the queue for safe execution
        self.tk_dispatch_queue.put(lambda: self._launch_visualizer_process(code))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设置全局字体
    from PyQt6.QtGui import QFont
    app.setFont(QFont("Microsoft YaHei", 9))
    gui = TradingGUI()
    gui.show()
    sys.exit(app.exec())
