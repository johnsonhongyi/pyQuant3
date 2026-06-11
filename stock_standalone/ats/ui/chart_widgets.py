# -*- coding: utf-8 -*-
"""
ATS Chart Widgets
Provides high-performance charts using pyqtgraph.
Includes:
- DistributionBarChart: Stock return distributions (-10% to +10%)
- EquityCurveChart: Backtest equity curve.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt
import pyqtgraph as pg
import numpy as np

class DistributionBarChart(QWidget):
    """
    Shows stock return distributions (e.g., A-Share stock count by return buckets).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        title = QLabel("📊 今日全市场个股涨跌幅分布 (Distribution)")
        title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 11pt;")
        layout.addWidget(title)

        # Create Plot Widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#121214")
        self.plot_widget.showGrid(x=False, y=True, alpha=0.2)
        
        # Disable interactive scaling on X axis to make it static if needed
        self.plot_widget.setMouseEnabled(x=False, y=True)
        layout.addWidget(self.plot_widget)

        # Mock distribution data: A-share returns buckets
        # Buckets: <-8%, -8%~-6%, -6%~-4%, -4%~-2%, -2%~0%, 0%~2%, 2%~4%, 4%~6%, 6%~8%, >8%
        self.x_labels = ["<-8%", "-7%", "-5%", "-3%", "-1%", "+1%", "+3%", "+5%", "+7%", ">+8%"]
        x = np.arange(len(self.x_labels))
        y = np.array([25, 45, 120, 310, 890, 1150, 480, 210, 95, 62])  # mock stock count

        # Set custom x-axis ticks
        ax = self.plot_widget.getAxis('bottom')
        ticks = [list(zip(x, self.x_labels))]
        ax.setTicks(ticks)

        # Color the bars based on direction
        # Negative buckets get green, positive get red
        colors = []
        for val in x:
            if val < 5:  # negative buckets
                colors.append('#33cc5a') # Green
            else:
                colors.append('#ff4444') # Red

        # Draw bars
        bg = pg.BarGraphItem(x=x, height=y, width=0.6, brushes=colors, pens=[pg.mkPen(c) for c in colors])
        self.plot_widget.addItem(bg)
        
        # Add labels and styling
        self.plot_widget.setLabel('left', '股数')
        self.plot_widget.setYRange(0, 1300)

    def update_data(self, bucket_counts):
        """
        Expects a list of 10 values representing the counts for each bucket.
        """
        if len(bucket_counts) != 10:
            return
        self.plot_widget.clear()
        x = np.arange(10)
        y = np.array(bucket_counts)
        
        colors = []
        for val in x:
            if val < 5:
                colors.append('#33cc5a')
            else:
                colors.append('#ff4444')

        bg = pg.BarGraphItem(x=x, height=y, width=0.6, brushes=colors, pens=[pg.mkPen(c) for c in colors])
        self.plot_widget.addItem(bg)
        self.plot_widget.setYRange(0, max(bucket_counts) * 1.1)


class EquityCurveChart(QWidget):
    """
    Plots cumulative returns / equity curves.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        title = QLabel("📈 策略收益率曲线 (Cumulative Returns)")
        title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 11pt;")
        layout.addWidget(title)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#121214")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.plot_widget)

        # Draw mock equity curve
        self.draw_mock_curve()

    def draw_mock_curve(self):
        self.plot_widget.clear()
        
        # Cumulative strategy equity vs benchmark (e.g. CSI 300)
        days = 60
        x = np.arange(days)
        
        # Random walk for strategy (drift upward)
        np.random.seed(42)
        strat_returns = np.random.normal(0.0015, 0.012, days)
        strat_equity = np.cumprod(1 + strat_returns) * 100
        
        # Random walk for benchmark (drift sideways)
        bench_returns = np.random.normal(0.0002, 0.014, days)
        bench_equity = np.cumprod(1 + bench_returns) * 100

        # Plot curves
        self.strat_line = self.plot_widget.plot(x, strat_equity, pen=pg.mkPen('#00ff88', width=2.5), name="ATS 自治策略")
        self.bench_line = self.plot_widget.plot(x, bench_equity, pen=pg.mkPen('#8e8e93', width=1.5, style=Qt.PenStyle.DashLine), name="沪深300")
        
        self.plot_widget.setLabel('left', '资产净值', units='元')
        self.plot_widget.setLabel('bottom', '交易日数')
        
        # Add legend
        self.legend = self.plot_widget.addLegend(offset=(20, 20))
        self.legend.addItem(self.strat_line, "ATS 自治策略")
        self.legend.addItem(self.bench_line, "沪深300指数")

    def update_curve(self, x, strat_equity, bench_equity=None):
        self.plot_widget.clear()
        
        # Safely re-create legend
        try:
            self.plot_widget.legend.close()
        except Exception:
            pass
            
        self.legend = self.plot_widget.addLegend(offset=(20, 20))
        
        self.strat_line = self.plot_widget.plot(x, strat_equity, pen=pg.mkPen('#00ff88', width=2.5))
        self.legend.addItem(self.strat_line, "ATS 自治策略")
        
        if bench_equity is not None:
            self.bench_line = self.plot_widget.plot(x, bench_equity, pen=pg.mkPen('#8e8e93', width=1.5, style=Qt.PenStyle.DashLine))
            self.legend.addItem(self.bench_line, "沪深300")
