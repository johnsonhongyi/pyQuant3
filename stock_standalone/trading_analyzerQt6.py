from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QComboBox, QMenu, QTextEdit, QHeaderView, QDialog,
    QSpinBox, QSplitter, QCheckBox, QMainWindow
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPoint
from PyQt6.QtGui import QAction
import sys
import pandas as pd
import numpy as np
from tk_gui_modules.window_mixin import WindowMixin
from dpi_utils import get_windows_dpi_scale_factor
import sqlite3
import json
import queue # ✅ Import queue
from datetime import datetime, timedelta

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
    def __init__(self, logger_path="./trading_signals.db", sender=None,on_tree_scroll_to_code =None, on_open_visualizer=None, selector=None, live_strategy=None):
        super().__init__()
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
            "实时指标详情","股票汇总", "单只股票明细", "每日策略统计", "Top 盈利交易", "Top 亏损交易", "股票表现概览", "信号探测历史", "策略胜率排行", "绩效分析看板"
        ])
        
        # ✅ UI 线程任务调度队列 (解决 Qt -> Tkinter 跨线程/GIL 问题)
        self.tk_dispatch_queue = queue.Queue()
        self.dispatch_timer = QTimer(self)
        self.dispatch_timer.timeout.connect(self._process_dispatch_queue)
        self.dispatch_timer.start(100) # Check every 100ms
        
        self.view_combo.currentTextChanged.connect(self.refresh_table)
        self.top_layout.addWidget(QLabel("视图选择:"))
        self.top_layout.addWidget(self.view_combo)
        
        # 工具栏菜单 (按钮形式)
        self.tools_btn = QPushButton("工具")
        self.tools_menu = QMenu(self)
        self.tools_menu.addAction("数据库诊断", self.show_db_diagnostics)
        self.tools_btn.setMenu(self.tools_menu)
        self.top_layout.addWidget(self.tools_btn)


        self.analysis_btn = QPushButton("生成分析报告")
        self.analysis_btn.clicked.connect(self.show_analysis_report)
        self.top_layout.addWidget(self.analysis_btn)
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_table)
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
        self.top_layout.addWidget(QLabel("代码过滤:"))
        self.top_layout.addWidget(self.stock_input)
        self.stock_input.currentTextChanged.connect(self.refresh_table)

        # 表格显示
        self.table = QTableWidget()
        self.main_layout.addWidget(self.table)

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
        
        # 初始刷新
        self.refresh_table()

    def closeEvent(self, event):
        self.save_window_position_qt(self, "TradingGUI_Geometry")
        super().closeEvent(event)

    def _on_source_changed(self, text):
        """数据源切换处理"""
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        
        if text == "交易/选股数据库":
            self.view_combo.addItems([
                "实时指标详情", "股票汇总", "单只股票明细", "每日策略统计", "Top 盈利交易", "Top 亏损交易", "股票表现概览", "信号探测历史", "策略胜率排行"
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

    def refresh_table(self):
        # 切换显示状态
        self.report_area.setVisible(False)
        self.table.setVisible(True)
        
        # 获取当前源和视图
        source = self.source_combo.currentText()
        view = self.view_combo.currentText()
        code = self.stock_input.currentText().strip()
        
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
                # 优化：如果有 code，直接传给后端筛选，避免全量加载
                df = self.analyzer.get_signal_history_df(code=code if code else None)
                if code and not df.empty: # This line becomes redundant if backend filtering is perfect, but kept for safety.
                    df = df[df['code'] == code]
            elif view == "实时指标详情":
                # 优化：如果有 code，直接传给后端筛选，避免全量加载
                df = self.analyzer.get_signal_history_df(code=code if code else None)
                if code and not df.empty: # This line becomes redundant if backend filtering is perfect, but kept for safety.
                    df = df[df['code'] == code]
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
        else:
            # 实时策略信号库
            if view == "今日信号汇总":
                df = self.signal_analyzer.get_todays_signal_counts()
                if code and not df.empty:
                    df = df[df['code'] == code]
                
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
                if code and not df.empty:
                    df = df[df['code'] == code]
            elif view == "信号类型统计":
                df = self.signal_analyzer.summarize_signals_by_type()
            elif view == "高频信号股":
                df = self.signal_analyzer.summarize_signals_by_code()

        # 显示表格
        self.current_df = df
        self.display_df(df)

        # 更新总收益摘要 (仅在交易模式下有意义，但在信号模式下可显示行数)
        if source == "交易/选股数据库":
            self.refresh_summary_label()
        else:
            count = len(df) if not df.empty else 0
            self.label_summary.setText(f"当前视图记录数: {count}")

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
            summary_df = get_trading_hub().get_strategy_performance(days=30)
        except:
            summary_df = pd.DataFrame()
        
        display_text = f"=== 账户绩效总览 (最近30日) ===\n"
        display_text += f"总盈亏: {total_pnl:.2f} | 总笔数: {total_trades} | 平均笔盈亏: {avg_pnl:.2f}\n\n"
        display_text += "策略表现 (胜率/盈亏):\n"
        display_text += "-" * 50 + "\n"
        
        if not summary_df.empty:
            summary_df = summary_df.sort_values('pnl', ascending=False)
            for _, row in summary_df.iterrows():
                win_rate = (row['wins'] / row['entered'] * 100) if row['entered'] > 0 else 0
                display_text += f" {row['strategy_name']:<18}: 胜率 {win_rate:>5.1f}% | 笔数 {row['entered']:>3} | 盈亏 {row['pnl']:>9.2f}\n"
        else:
            display_text += " (暂无策略统计信息)\n"
        
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
        self.table.clear()
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
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
        self.table.resizeColumnsToContents()
        
        # 限制高度文本列的宽度
        header = self.table.horizontalHeader()
        for j, col_name in enumerate(df.columns):
            raw_target = col_name.lower()
            if any(k in raw_target for k in ["reason", "msg", "feedback", "indicators"]):
                self.table.setColumnWidth(j, 250)
                header.setSectionResizeMode(j, QHeaderView.ResizeMode.Interactive)
            elif any(k in raw_target for k in ["code", "name", "date", "action", "signal_type"]):
                if self.table.columnWidth(j) < 60:
                    self.table.setColumnWidth(j, 80)


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
                self.stock_input.setCurrentText(stock_code)
                self.on_tree_scroll_to_code(stock_code,vis=True)
            except Exception as e:
                print(f"on_tree_scroll_to_code error: {e}")
        else:
            # 降级方案：如果是独立的，尝试更新输入框
            self.stock_input.setCurrentText(stock_code)
            
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
