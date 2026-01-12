from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QComboBox, QMenu, QTextEdit, QHeaderView
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPoint
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

class TradingGUI(QWidget):
    # 声明信号
    scroll_to_code_signal = pyqtSignal(str)
    send_status_signal = pyqtSignal(object)  # 可以接收任意对象，包括 dict
    def __init__(self, logger_path="./trading_signals.db", sender=None,on_tree_scroll_to_code =None):
        super().__init__()
        self.setWindowTitle("策略交易分析工具")
        self.setGeometry(100, 100, 1000, 600)
        self.center()  # 调用居中方法
        self.logger = TradingLogger(logger_path)
        self.analyzer = TradingAnalyzer(self.logger)

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # 顶部：汇总信息
        self.label_summary = QLabel("总收益: 0, 平均收益率: 0%, 总笔数: 0")
        self.main_layout.addWidget(self.label_summary)

        # 顶部选择
        self.top_layout = QHBoxLayout()
        self.main_layout.addLayout(self.top_layout)

        self.view_combo = QComboBox()
        self.view_combo.addItems([
            "实时指标详情","股票汇总", "单只股票明细", "每日策略统计", "Top 盈利交易", "Top 亏损交易", "股票表现概览", "信号探测历史"
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

        self.stock_input = QComboBox()
        self.stock_input.setEditable(True)
        self.top_layout.addWidget(QLabel("代码过滤:"))
        self.top_layout.addWidget(self.stock_input)
        self.stock_input.currentTextChanged.connect(self.refresh_table)

        # 表格显示
        self.table = QTableWidget()
        self.main_layout.addWidget(self.table)

        # 底部日志/报告显示区域 (隐藏，仅在查看报告时显示)
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
            self.sender = StockSender(callback=self.update_send_status)

        # 表格点击与切换信号
        _ = self.table.cellClicked.connect(self.on_table_row_clicked)
        _ = self.table.currentCellChanged.connect(self.on_current_cell_changed)
        
        # 添加右键菜单策略
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        _ = self.table.customContextMenuRequested.connect(self.show_context_menu)

        # 初始化表格数据
        self.refresh_table()

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
        # 为了不阻塞 UI，简单处理：直接运行并读取输出文件 (或者重构 generate_report 返回字符串)
        # 这里我们假定执行后会生成提示
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
        
        self.update_stock_list()
        # 当前视图
        view = self.view_combo.currentText()
        code = self.stock_input.currentText().strip()

        # 根据视图获取 DataFrame
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
            # 专门展示增强后的指标数据（ma5d, ma10d, pump_height 等）
            df = self.analyzer.get_signal_history_df()
            if code:
                df = df[df['code'] == code]
            # 只保留指标相关列
            indicator_cols = ['date', 'code', 'name', 'price', 'action', 'reason',
                            'buy_reason', 'sell_reason', 'time_msg',
                            'ma5d', 'ma10d', 'ratio', 'volume', 'percent',
                            'high', 'low', 'open', 'nclose',
                            'highest_today', 'pump_height', 'pullback_depth',
                            'win', 'red', 'gren', 'structure']
            existing_cols = [c for c in indicator_cols if c in df.columns]
            df = df[existing_cols] if existing_cols else df
        else:
            df = pd.DataFrame()

        # 显示表格
        self.current_df = df
        self.display_df(df)

        # 更新总收益摘要
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

        # 填充数据期间关闭排序，避免干扰和性能下降
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        
        # 列名转换字典
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
            'win': '胜率', 'red': '阳线', 'gren': '阴线', 'structure': '结构'
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
                # 获取列字段名
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
                
                self.table.setItem(i, j, item)
        
        # 填充完成后开启排序
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        
        # 限制高度文本列的宽度，防止撑开过大
        header = self.table.horizontalHeader()
        for j, col_name in enumerate(df.columns):
            raw_target = col_name.lower()
            if any(k in raw_target for k in ["reason", "msg", "feedback", "indicators"]):
                self.table.setColumnWidth(j, 250)
                header.setSectionResizeMode(j, QHeaderView.ResizeMode.Interactive)
            elif any(k in raw_target for k in ["code", "name", "date", "action"]):
                # 对于这些列，如果内容很短，resizeColumnsToContents 已经处理好了
                # 如果还是觉得太窄，可以给个最小值
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
        if stock_code and self.sender:
            try:
                self.sender.send(stock_code)
            except Exception as e:
                print(f"Error sending stock code: {e}")

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
                self.on_tree_scroll_to_code(stock_code)
            except Exception as e:
                print(f"on_tree_scroll_to_code error: {e}")
        else:
            # 降级方案：如果是独立的，尝试更新输入框
            self.stock_input.setCurrentText(stock_code)
            
    def _safe_update_send_status(self, msg):
        """Qt 主线程安全更新状态"""
        self.label_summary.setText(f"发送状态: {msg}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设置全局字体
    from PyQt6.QtGui import QFont
    app.setFont(QFont("Microsoft YaHei", 9))
    gui = TradingGUI()
    gui.show()
    sys.exit(app.exec())
