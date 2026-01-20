from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QComboBox, QMenu
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QAction
import sys
import pandas as pd

# 假设 TradingAnalyzer 已经在同一目录
from trading_logger import TradingLogger
from trading_analyzer import TradingAnalyzer
from JohnsonUtil.stock_sender import StockSender

class NumericTableWidgetItem(QTableWidgetItem):
    """自定义 TableWidgetItem，支持正确的数值排序"""
    def __init__(self, value):
        if isinstance(value, (int, float)):
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

class StockTable(QTableWidget):
    """自定义 TableWidget，只在左键点击时发射信号"""
    left_click_cell = pyqtSignal(int, int)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                self.left_click_cell.emit(item.row(), item.column())
        super().mousePressEvent(event)

class TradingGUI(QWidget):
    scroll_to_code_signal = pyqtSignal(str)
    send_status_signal = pyqtSignal(object)  # 可以接收 dict

    # === Qt 版 BooleanVar 包装器，用于兼容 StockSender ===
    class QtBoolVar:
        """模拟 tk.BooleanVar 接口，用于 Qt 环境"""
        def __init__(self, value=False):
            self._value = value
        def get(self):
            return self._value
        def set(self, value):
            self._value = bool(value)

    def __init__(self, logger_path="./trading_signals.db", sender=None, on_tree_scroll_to_code=None):
        super().__init__()
        self.setWindowTitle("策略交易分析工具")
        self.setGeometry(100, 100, 1000, 600)
        self.center()

        self.logger = TradingLogger(logger_path)
        self.analyzer = TradingAnalyzer(self.logger)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.label_summary = QLabel("总收益: 0, 平均收益率: 0%, 总笔数: 0")
        self.layout.addWidget(self.label_summary)

        # 顶部选择
        self.top_layout = QHBoxLayout()
        self.layout.addLayout(self.top_layout)

        self.view_combo = QComboBox()
        self.view_combo.addItems([
            "实时指标详情","股票汇总", "单只股票明细", "每日策略统计",
            "Top 盈利交易", "Top 亏损交易", "股票表现概览", "信号探测历史"
        ])
        self.view_combo.currentTextChanged.connect(self.refresh_table)
        self.top_layout.addWidget(QLabel("视图选择:"))
        self.top_layout.addWidget(self.view_combo)

        self.analysis_btn = QPushButton("生成分析报告")
        self.analysis_btn.clicked.connect(self.show_analysis_report)
        self.top_layout.addWidget(self.analysis_btn)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_table)
        self.top_layout.addWidget(self.refresh_btn)

        # === TDX / THS 独立联动开关 ===
        self.tdx_var = self.QtBoolVar(True)  # 默认开启
        self.ths_var = self.QtBoolVar(True)  # 默认开启
        self.dfcf_var = self.QtBoolVar(False)  # 东方财富默认关闭

        self.tdx_btn = QPushButton("📡 TDX")
        self.tdx_btn.setCheckable(True)
        self.tdx_btn.setChecked(True)
        self.tdx_btn.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; }")
        self.tdx_btn.clicked.connect(self._on_tdx_toggle)
        self.top_layout.addWidget(self.tdx_btn)

        self.ths_btn = QPushButton("📡 THS")
        self.ths_btn.setCheckable(True)
        self.ths_btn.setChecked(True)
        self.ths_btn.setStyleSheet("QPushButton:checked { background-color: #2196F3; color: white; }")
        self.ths_btn.clicked.connect(self._on_ths_toggle)
        self.top_layout.addWidget(self.ths_btn)

        self.stock_input = QComboBox()
        self.stock_input.setEditable(True)
        self.top_layout.addWidget(QLabel("代码过滤:"))
        self.top_layout.addWidget(self.stock_input)
        self.stock_input.currentTextChanged.connect(self.refresh_table)

        # 表格显示
        self.table = StockTable()
        self.layout.addWidget(self.table)
        self.table.left_click_cell.connect(self.on_table_row_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        # 底部日志/报告显示
        from PyQt6.QtWidgets import QTextEdit
        self.report_area = QTextEdit()
        self.report_area.setReadOnly(True)
        self.report_area.setVisible(False)
        self.layout.addWidget(self.report_area)

        self.on_tree_scroll_to_code = on_tree_scroll_to_code

        # 信号绑定
        self.scroll_to_code_signal.connect(self._safe_scroll_to_code)
        self.send_status_signal.connect(self._safe_update_send_status)

        # === 股票发送器 (使用独立的 tdx_var / ths_var) ===
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
            self.sender = StockSender(
                self.tdx_var, 
                self.ths_var, 
                self.dfcf_var, 
                callback=self.update_send_status
            )

        # 初始化表格数据
        self.refresh_table()

    def _on_tdx_toggle(self):
        """TDX 联动开关切换"""
        self.tdx_var.set(self.tdx_btn.isChecked())
        status = "已开启" if self.tdx_var.get() else "已关闭"
        self.label_summary.setText(f"TDX 联动: {status}")
        # 刷新 sender 句柄
        if hasattr(self.sender, 'reload'):
            self.sender.reload()

    def _on_ths_toggle(self):
        """THS 联动开关切换"""
        self.ths_var.set(self.ths_btn.isChecked())
        status = "已开启" if self.ths_var.get() else "已关闭"
        self.label_summary.setText(f"THS 联动: {status}")
        # 刷新 sender 句柄
        if hasattr(self.sender, 'reload'):
            self.sender.reload()

    def center(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)

    def show_analysis_report(self):
        from generate_analysis_report import generate_report
        generate_report()
        try:
            with open("analysis_report_output.txt", "r", encoding="utf-8") as f:
                text = f.read()
            self.report_area.setPlainText(text)
            self.report_area.setVisible(True)
            self.table.setVisible(False)
        except Exception as e:
            self.report_area.setPlainText(f"生成报告失败: {e}")
            self.report_area.setVisible(True)

    def refresh_table(self):
        self.report_area.setVisible(False)
        self.table.setVisible(True)

        self.update_stock_list()
        view = self.view_combo.currentText()
        code = self.stock_input.currentText().strip()

        if view == "股票汇总":
            df = self.analyzer.summarize_by_stock()
        elif view == "单只股票明细":
            df = self.analyzer.get_stock_detail(code) if code else pd.DataFrame()
        elif view == "每日策略统计":
            df = self.analyzer.daily_summary()
        elif view == "Top 盈利交易":
            df = self.analyzer.top_trades(n=10, largest=True)
        elif view == "Top 亏损交易":
            df = self.analyzer.top_trades(n=10, largest=False)
        elif view == "股票表现概览":
            df = self.analyzer.stock_performance()
        elif view == "信号探测历史":
            df = self.analyzer.get_signal_history_df()
            if code:
                df = df[df['code'] == code]
        elif view == "实时指标详情":
            df = self.analyzer.get_signal_history_df()
            if code:
                df = df[df['code'] == code]
            indicator_cols = ['date', 'code', 'name', 'price', 'action', 'reason',
                              'ma5d', 'ma10d', 'ratio', 'volume', 'percent',
                              'high', 'low', 'open', 'nclose',
                              'highest_today', 'pump_height', 'pullback_depth',
                              'win', 'red', 'gren', 'structure']
            existing_cols = [c for c in indicator_cols if c in df.columns]
            df = df[existing_cols] if existing_cols else df
        else:
            df = pd.DataFrame()

        self.current_df = df
        self.display_df(df)
        self.refresh_summary_label()

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
        view = self.view_combo.currentText()
        if view not in ["单只股票明细", "信号探测历史", "实时指标详情"]:
            return

        if view in ["信号探测历史", "实时指标详情"]:
            df_source = self.analyzer.get_signal_history_df()
        else:
            df_source = self.analyzer.get_all_trades_df()

        codes = sorted(df_source['code'].unique().tolist()) if not df_source.empty else []
        if codes and "" not in codes:
            codes.insert(0, "")
        current_code = self.stock_input.currentText().strip()
        existing_items = [self.stock_input.itemText(i) for i in range(self.stock_input.count())]
        if existing_items != codes:
            self.stock_input.blockSignals(True)
            self.stock_input.clear()
            self.stock_input.addItems(codes)
            self.stock_input.setCurrentText(current_code if current_code in codes else "")
            self.stock_input.blockSignals(False)

    def display_df(self, df: pd.DataFrame):
        self.table.clear()
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(df.columns))
        self.table.setRowCount(len(df))
        self.table.setHorizontalHeaderLabels(df.columns)

        for i, row in enumerate(df.itertuples(index=False)):
            for j, value in enumerate(row):
                item = NumericTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                col_name = df.columns[j].lower()
                if "profit" in col_name or "pnl" in col_name or "return" in col_name or "percent" in col_name:
                    try:
                        f_val = float(value)
                        if f_val > 0: item.setForeground(Qt.GlobalColor.red)
                        elif f_val < 0: item.setForeground(Qt.GlobalColor.darkGreen)
                    except: pass
                self.table.setItem(i, j, item)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    def get_current_df(self):
        return getattr(self, "current_df", None)

    def update_send_status(self, msg: str):
        self.label_summary.setText(f"发送状态: {msg}")

    def on_table_row_clicked(self, row, column):
        """左键点击触发发送"""
        self._trigger_stock_linkage(row, column, force_send=False)

    def _trigger_stock_linkage(self, row, column, force_send=False):
        df = self.get_current_df()
        if df is None or df.empty:
            return

        if not force_send:
            try:
                clicked_col = df.columns[column].lower()
            except Exception:
                return
            if clicked_col not in {"code", "stock_code", "ts_code", "name"}:
                return

        code_col = next((c for c in df.columns if c.lower() in ("code","stock_code","ts_code")), None)
        if not code_col:
            return

        try:
            stock_code = str(df.iloc[row][code_col]).strip()
            if stock_code:
                self.sender.send(stock_code)
        except Exception as e:
            print(f"Error sending stock code: {e}")

    def show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if item is None:
            return

        row = item.row()
        df = self.get_current_df()
        if df is None or df.empty:
            return

        code_col = next((c for c in df.columns if c.lower() in ("code","stock_code","ts_code")), None)
        if not code_col:
            return

        try:
            stock_code = str(df.iloc[row][code_col]).strip()
        except:
            return
        if not stock_code:
            return

        menu = QMenu(self)
        locate_action = QAction(f"定位股票代码: {stock_code}", self)
        locate_action.triggered.connect(lambda: self.tree_scroll_to_code(stock_code))
        menu.addAction(locate_action)
        menu.exec(self.table.mapToGlobal(pos))

    def tree_scroll_to_code(self, stock_code):
        self.scroll_to_code_signal.emit(stock_code)

    def _safe_scroll_to_code(self, stock_code):
        if callable(self.on_tree_scroll_to_code):
            self.on_tree_scroll_to_code(stock_code)
        else:
            self.stock_input.setCurrentText(stock_code)

    def _safe_update_send_status(self, msg):
        self.label_summary.setText(f"发送状态: {msg}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    from PyQt6.QtGui import QFont
    app.setFont(QFont("Microsoft YaHei", 9))
    gui = TradingGUI()
    gui.show()
    sys.exit(app.exec())
