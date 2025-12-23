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
            "股票汇总", "单只股票明细", "每日策略统计", "Top 盈利交易", "Top 亏损交易", "股票表现概览"
        ])
        self.view_combo.currentTextChanged.connect(self.refresh_table)
        self.top_layout.addWidget(QLabel("视图选择:"))
        self.top_layout.addWidget(self.view_combo)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_table)
        self.top_layout.addWidget(self.refresh_btn)

        self.stock_input = QComboBox()
        self.stock_input.setEditable(True)
        self.top_layout.addWidget(QLabel("股票代码:"))
        self.top_layout.addWidget(self.stock_input)
        self.stock_input.currentTextChanged.connect(self.refresh_table)
        # self.stock_input.activated.connect(self.refresh_table)
        # 表格显示
        self.table = QTableWidget()
        self.layout.addWidget(self.table)

        # 初始化表格数据
        self.refresh_table()

    def center(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def refresh_summary(self):
        """刷新顶部总收益信息"""
        df = self.analyzer.get_all_trades_df()
        if df.empty:
            self.label_summary.setText("总收益: 0, 平均收益率: 0%, 总笔数: 0")
            return

        df_closed = df[df['status']=='CLOSED']
        total_profit = df_closed['profit'].sum()
        avg_pct = df_closed['pnl_pct'].mean() if not df_closed.empty else 0
        total_count = len(df_closed)

        self.label_summary.setText(
            f"总收益: {total_profit:.2f}, 平均收益率: {avg_pct*100:.2f}%, 总笔数: {total_count}"
        )

    def update_stock_list(self):
        df_summary = self.analyzer.summarize_by_stock()
        if df_summary.empty:
            codes = []
        else:
            codes = df_summary['code'].tolist()

        # 保存当前选中值
        current_code = self.stock_input.currentText().strip()

        # 如果下拉列表内容没有变化，就不更新，避免触发循环
        if list(self.stock_input.itemText(i) for i in range(self.stock_input.count())) != codes:
            self.stock_input.blockSignals(True)
            self.stock_input.clear()
            self.stock_input.addItems(codes)
            # # 尝试恢复选中值
            # if current_code in codes:
            #     self.stock_input.setCurrentText(current_code)
            # else:
            #     self.stock_input.setCurrentIndex(-1)
            # self.stock_input.blockSignals(False)
            # 尝试恢复选中值
            if current_code in codes:
                self.stock_input.setCurrentText(current_code)
            elif codes:  # 如果之前没有选中值，默认选中第一个
                self.stock_input.setCurrentIndex(0)
            else:
                self.stock_input.setCurrentIndex(-1)
            self.stock_input.blockSignals(False)

    def refresh_table(self):
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
        else:
            df = pd.DataFrame()

        # 显示表格
        self.display_df(df)

        # 更新总收益/平均收益/总笔数（仅股票汇总或全局）
        if view == "股票汇总" or view == "股票表现概览":
            df_closed = self.analyzer.get_all_trades_df()
            if not df_closed.empty:
                df_closed = df_closed[df_closed['status']=='CLOSED']
                total_profit = df_closed['profit'].sum()
                avg_pct = df_closed['pnl_pct'].mean() if not df_closed.empty else 0
                total_count = len(df_closed)
                self.label_summary.setText(
                    f"总收益: {total_profit:.2f}, 平均收益率: {avg_pct*100:.2f}%, 总笔数: {total_count}"
                )
            else:
                self.label_summary.setText("总收益: 0, 平均收益率: 0%, 总笔数: 0")

        # 股票列表只在初始化或有新增股票时更新，避免每次刷新重置索引
        # 可单独写一个方法 update_stock_list()

    # def refresh_table(self):
    #     # 先刷新汇总信息
    #     self.refresh_summary()

    #     # 阻塞 stock_input 信号，防止循环触发
    #     self.stock_input.blockSignals(True)

    #     view = self.view_combo.currentText()
    #     current_code = self.stock_input.currentText().strip()

    #     if view == "股票汇总":
    #         df = self.analyzer.summarize_by_stock()
    #     elif view == "单只股票明细":
    #         df = self.analyzer.get_stock_detail(code) if code else pd.DataFrame()
    #     elif view == "每日策略统计":
    #         df = self.analyzer.daily_summary()
    #     elif view == "Top 盈利交易":
    #         df = self.analyzer.top_trades(n=10, largest=True)
    #     elif view == "Top 亏损交易":
    #         df = self.analyzer.top_trades(n=10, largest=False)
    #     elif view == "股票表现概览":
    #         df = self.analyzer.stock_performance()
    #     else:
    #         df = pd.DataFrame()

    #     self.display_df(df)

    #     # 自动更新股票列表
    #     all_codes = self.analyzer.summarize_by_stock()['code'].tolist()
    #     current_code = self.stock_input.currentText().strip()
    #     self.stock_input.clear()
    #     self.stock_input.addItems(all_codes)
    #     if current_code in all_codes:
    #         self.stock_input.setCurrentText(current_code)
    #     else:
    #         self.stock_input.setCurrentIndex(-1)

    #     self.stock_input.blockSignals(False)

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
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, j, item)


    def summarize_by_stock(self) -> pd.DataFrame:
        """
        按股票汇总：状态（OPEN/CLOSED）、总量、平均价、笔数、占比
        """
        df = self.get_all_trades_df()
        if df.empty: 
            return pd.DataFrame()

        summary_list = []
        total_amount = df['buy_amount'].sum()

        for code, group in df.groupby('code'):
            status = 'OPEN' if any(group['status'] == 'OPEN') else 'CLOSED'
            avg_price = (group['buy_price'] * group['buy_amount']).sum() / group['buy_amount'].sum()
            total_volume = group['buy_amount'].sum()
            trade_count = len(group)
            pct = total_volume / total_amount * 100 if total_amount > 0 else 0
            name = group['name'].iloc[0]
            summary_list.append({
                'code': code,
                'name': name,
                'status': status,
                'avg_price': round(avg_price, 2),
                'total_amount': total_volume,
                'trade_count': trade_count,
                'pct': round(pct, 2)
            })
        summary_df = pd.DataFrame(summary_list)
        # 按持仓/平仓、占比排序
        summary_df['status_sort'] = summary_df['status'].apply(lambda x: 0 if x=='OPEN' else 1)
        summary_df = summary_df.sort_values(by=['status_sort', 'pct'], ascending=[True, False]).drop(columns='status_sort')
        return summary_df

    def get_stock_detail(self, code: str) -> pd.DataFrame:
        """
        查询单只股票交易明细，按时间排序
        """
        df = self.get_all_trades_df()
        return df[df['code'] == code].sort_values(by='buy_date')

    def daily_summary(self) -> pd.DataFrame:
        """
        按天统计每日开仓笔数、总量、已平仓盈亏
        """
        df = self.get_all_trades_df()
        if df.empty: 
            return pd.DataFrame()
        df['buy_date_only'] = df['buy_date'].dt.date
        df['sell_date_only'] = df['sell_date'].dt.date

        daily = []
        dates = sorted(set(df['buy_date_only'].tolist() + df['sell_date_only'].dropna().tolist()))
        for d in dates:
            daily_trades = df[df['buy_date_only'] == d]
            daily_amount = daily_trades['buy_amount'].sum()
            closed_trades = df[(df['status']=='CLOSED') & (df['sell_date_only']==d)]
            daily_profit = closed_trades['profit'].sum() if not closed_trades.empty else 0
            daily.append({
                'date': d,
                'daily_trades': len(daily_trades),
                'daily_amount': daily_amount,
                'daily_profit': daily_profit
            })
        return pd.DataFrame(daily).sort_values(by='date', ascending=False)

    def top_trades(self, n: int = 5, largest: bool = True) -> pd.DataFrame:
        """
        top 盈利或亏损交易
        largest=True: 最大盈利，largest=False: 最大亏损
        """
        df = self.get_all_trades_df()
        df_closed = df[df['status'] == 'CLOSED']
        if df_closed.empty:
            return df_closed
        return df_closed.sort_values(by='profit', ascending=not largest).head(n)

    def stock_performance(self) -> pd.DataFrame:
        """
        按股票计算累计盈亏和收益率
        """
        df = self.get_all_trades_df()
        if df.empty:
            return pd.DataFrame()
        performance = []
        for code, group in df.groupby('code'):
            closed = group[group['status']=='CLOSED']
            open_ = group[group['status']=='OPEN']
            closed_profit = closed['profit'].sum() if not closed.empty else 0
            open_cost = (open_['buy_price']*open_['buy_amount']).sum() if not open_.empty else 0
            open_current = (open_['buy_amount'] * open_['buy_price']).sum() if not open_.empty else 0
            total_profit = closed_profit
            total_cost = (closed['buy_price']*closed['buy_amount']).sum() + open_cost
            pct = total_profit/total_cost if total_cost>0 else 0
            performance.append({
                'code': code,
                'name': group['name'].iloc[0],
                'status': 'OPEN' if len(open_)>0 else 'CLOSED',
                'profit': round(total_profit,2),
                'return_pct': round(pct*100,2),
                'total_trades': len(group)
            })
        return pd.DataFrame(performance).sort_values(by='profit', ascending=False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = TradingGUI()
    gui.show()
    sys.exit(app.exec())
