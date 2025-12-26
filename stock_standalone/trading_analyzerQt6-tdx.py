from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QComboBox
)
from PyQt6.QtCore import Qt
import sys
import pandas as pd

# 假设 TradingAnalyzer 已经在同一目录
from trading_logger import TradingLogger
from trading_analyzer import TradingAnalyzer
from JohnsonUtil.stock_sender import StockSender
class TradingGUI(QWidget):
    def __init__(self, logger_path="./trading_signals.db"):
        super().__init__()
        self.setWindowTitle("策略交易分析工具")
        self.setGeometry(100, 100, 1000, 600)
        self.center()  # 调用居中方法
        self.logger = TradingLogger(logger_path)
        self.analyzer = TradingAnalyzer(self.logger)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # 顶部：汇总信息
        self.label_summary = QLabel("总收益: 0, 平均收益率: 0%, 总笔数: 0")
        self.layout.addWidget(self.label_summary)

        # 顶部选择
        self.top_layout = QHBoxLayout()
        self.layout.addLayout(self.top_layout)

        self.view_combo = QComboBox()
        self.view_combo.addItems([
            "股票汇总", "单只股票明细", "每日策略统计", "Top 盈利交易", "Top 亏损交易", "股票表现概览", "信号探测历史"
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
        self.layout.addWidget(self.table)

        # 底部日志/报告显示区域 (隐藏，仅在查看报告时显示)
        from PyQt6.QtWidgets import QTextEdit
        self.report_area = QTextEdit()
        self.report_area.setReadOnly(True)
        self.report_area.setVisible(False)
        self.layout.addWidget(self.report_area)

        # === 股票发送器 ===
        self.sender = StockSender(
            # self.tdx_var,
            # self.ths_var,
            # self.dfcf_var,
            callback=self.update_send_status
        )

        # 表格点击信号
        self.table.cellClicked.connect(self.on_table_row_clicked)

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
        else:
            df = pd.DataFrame()

        # 显示表格
        self.current_df = df
        self.display_df(df)

        # 更新总收益摘要
        self.refresh_summary_label()

    def get_current_df(self):
        return getattr(self, "current_df", None)

    def update_send_status(self, msg: str):
        self.label_summary.setText(f"发送状态: {msg}")


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
        if view not in ["单只股票明细", "信号探测历史"]:
            return

        df_all = self.analyzer.get_all_trades_df()
        if df_all.empty:
            codes = []
        else:
            codes = sorted(df_all['code'].unique().tolist())

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
            self.stock_input.blockSignals(False)

    def display_df(self, df: pd.DataFrame):
        self.table.clear()
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        self.table.setColumnCount(len(df.columns))
        self.table.setRowCount(len(df))
        self.table.setHorizontalHeaderLabels(df.columns)

        for i, row in enumerate(df.itertuples(index=False)):
            for j, value in enumerate(row):
                # 优化数字显示
                if isinstance(value, float):
                    display_val = f"{value:.2f}"
                else:
                    display_val = str(value)
                
                item = QTableWidgetItem(display_val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # 特色染色逻辑：盈亏染色
                if "profit" in df.columns[j].lower() or "pnl" in df.columns[j].lower() or "return" in df.columns[j].lower():
                    try:
                        f_val = float(value)
                        if f_val > 0: item.setForeground(Qt.GlobalColor.red)
                        elif f_val < 0: item.setForeground(Qt.GlobalColor.darkGreen)
                    except: pass
                
                self.table.setItem(i, j, item)
        
        self.table.resizeColumnsToContents()

    def on_table_row_clicked(self, row: int, column: int):
        """
        仅当点击 code / name 列时，发送股票代码
        """
        df = self.get_current_df()
        if df is None or df.empty:
            return

        # 当前点击的列名
        try:
            clicked_col = df.columns[column].lower()
        except Exception:
            return

        # 只允许这些列触发
        trigger_cols = {"code", "stock_code", "ts_code", "name"}
        if clicked_col not in trigger_cols:
            return

        # 找到 code 列（发送始终以 code 为准）
        code_col = None
        for c in df.columns:
            if c.lower() in ("code", "stock_code", "ts_code"):
                code_col = c
                break

        if not code_col:
            return

        stock_code = str(df.iloc[row][code_col]).strip()
        if not stock_code:
            return

        self.sender.send(stock_code)


    def on_table_row_clicked_old(self, row: int, column: int):
        """
        点击表格行 → 发送股票代码
        """
        df = self.get_current_df()
        if df is None or df.empty:
            return

        # 尝试识别 code 列
        code_col = None
        for c in df.columns:
            if c.lower() in ("code", "stock_code", "ts_code"):
                code_col = c
                break

        if not code_col:
            return

        stock_code = str(df.iloc[row][code_col]).strip()
        if stock_code:
            self.sender.send(stock_code)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设置全局字体
    from PyQt6.QtGui import QFont
    app.setFont(QFont("Microsoft YaHei", 9))
    gui = TradingGUI()
    gui.show()
    sys.exit(app.exec())
