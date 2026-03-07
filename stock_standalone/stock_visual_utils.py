import sys
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtGui import QColor, QPicture, QPainter
from PyQt6.QtCore import Qt, QRectF, QPointF

# Import existing signals definitions if available
try:
    from signal_types import SignalPoint, SignalType
except ImportError:
    # Minimal fallback handles if signal_types.py is not in path
    class SignalType:
        BUY = "买入"
        SELL = "卖出"
        FOLLOW = "跟单"
    class SignalPoint:
        pass

class TimeAxisItem(pg.AxisItem):
    """Custom axis to display time strings for indexed data."""
    def __init__(self, time_map, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.time_map = time_map  # {index: "HH:MM"}

    def tickStrings(self, values, scale, spacing):
        return [self.time_map.get(round(v), '') for v in values]

class CandlestickItem(pg.GraphicsObject):
    """Specialized item for drawing K-lines."""
    def __init__(self, data, theme='dark'):
        super().__init__()
        self.data = np.asarray(data)  # Expected columns: [index, open, close, low, high]
        self.theme = theme
        self.picture = QPicture()
        self._gen_colors()
        self.generatePicture()

    def _gen_colors(self):
        if self.theme == 'dark':
            self.up_pen = pg.mkPen(QColor(220, 80, 80))
            self.up_brush = pg.mkBrush(QColor(220, 80, 80))
            self.down_pen = pg.mkPen(QColor(80, 200, 120))
            self.down_brush = pg.mkBrush(QColor(80, 200, 120))
            self.wick_pen = pg.mkPen(QColor(200, 200, 200))
        else:
            self.up_pen = pg.mkPen(QColor(200, 0, 0))
            self.up_brush = pg.mkBrush(QColor(200, 0, 0))
            self.down_pen = pg.mkPen(QColor(0, 150, 0))
            self.down_brush = pg.mkBrush(QColor(0, 150, 0))
            self.wick_pen = pg.mkPen(QColor(80, 80, 80))

    def generatePicture(self):
        self.picture = QPicture()
        p = QPainter(self.picture)
        w = 0.4
        for row in self.data:
            t, open_, close, low, high = row[:5]
            if close >= open_:
                p.setPen(self.up_pen)
                p.setBrush(self.up_brush)
            else:
                p.setPen(self.down_pen)
                p.setBrush(self.down_brush)
            
            p.drawLine(QPointF(t, low), QPointF(t, high))
            p.drawRect(QRectF(t - w, open_, w * 2, close - open_))
        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())

class SignalOverlay:
    """Manager for drawing signal markers and labels on plots."""
    def __init__(self, plot_item):
        self.plot_item = plot_item
        self.scatter = pg.ScatterPlotItem(pxMode=True, zValue=100)
        self.plot_item.addItem(self.scatter)
        self.text_items = []

    def clear(self):
        self.scatter.clear()
        for item in self.text_items:
            self.plot_item.removeItem(item)
        self.text_items.clear()

    def update_signals(self, signals):
        self.clear()
        if not signals:
            return

        xs, ys, brushes, symbols, sizes = [], [], [], [], []
        
        for sig in signals:
            x_pos = sig.bar_index
            y_pos = sig.price
            
            symbol = getattr(sig, 'symbol', 'o')
            is_emoji = symbol in ('🎯', '🚀')
            
            # Scatter attributes (fallback for emojis)
            xs.append(x_pos)
            ys.append(y_pos)
            brushes.append(pg.mkBrush(getattr(sig, 'color', (255, 255, 0))))
            symbols.append('o' if is_emoji else symbol)
            sizes.append(getattr(sig, 'size', 12))
            
            # Text Price Label
            is_buy = getattr(sig, 'signal_type', None) in ("买入", "加仓", "跟单")
            anchor = (0.5, -0.5) if is_buy else (0.5, 1.5)
            color = QColor(255, 120, 120) if is_buy else QColor(120, 255, 120)
            
            txt = pg.TextItem(f"{sig.price:.2f}", anchor=anchor, color=color)
            txt.setPos(x_pos, y_pos)
            self.plot_item.addItem(txt)
            self.text_items.append(txt)
            
            # Emoji Handling as TextItem
            if is_emoji:
                emoji = pg.TextItem(symbol, anchor=(0.5, 0.5))
                emoji.setHtml(f'<div style="font-size: 14pt;">{symbol}</div>')
                emoji.setPos(x_pos, y_pos)
                self.plot_item.addItem(emoji)
                self.text_items.append(emoji)

        self.scatter.setData(x=xs, y=ys, brush=brushes, symbol=symbols, size=sizes)

class StandaloneKlineChart(QMainWindow):
    """Simple chart window for visualization."""
    def __init__(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1000, 600)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Setup Axis if time labels provided
        axis_items = {}
        if time_labels:
            # time_labels can be a list of strings matching the df rows
            time_map = {i: label for i, label in enumerate(time_labels)}
            axis_items['bottom'] = TimeAxisItem(time_map, orientation='bottom')
            
        self.pw = pg.PlotWidget(axisItems=axis_items)
        layout.addWidget(self.pw)
        
        # Prepare data: line chart for live/tick data, candlestick for minute-bar data
        if use_line:
            # Live tick mode: simple line chart of close prices (no spurious bars)
            close_y = df['close'].values
            close_x = np.arange(len(close_y))
            self.pw.plot(close_x, close_y,
                         pen=pg.mkPen(QColor(100, 200, 255), width=1.5), name="Price")
        else:
            # Minute/day bar mode: full candlestick chart
            k_data = []
            for i, (idx, row) in enumerate(df.iterrows()):
                k_data.append([i, row['open'], row['close'], row['low'], row['high']])
            self.candlestick = CandlestickItem(k_data)
            self.pw.addItem(self.candlestick)
        
        # Add VWAP/Average Price Line
        if avg_series is not None:
            avg_x = np.arange(len(avg_series))
            avg_y = np.asarray(avg_series)
            self.avg_plot = self.pw.plot(avg_x, avg_y, pen=pg.mkPen(QColor(255, 255, 255, 180), width=1.5, style=Qt.PenStyle.DashLine), name="VWAP")
        
        self.overlay = SignalOverlay(self.pw)
        if signals:
            self.overlay.update_signals(signals)
            
        self.pw.showGrid(x=True, y=True, alpha=0.3)
        self.pw.setLabel('left', 'Price')
        self.pw.setLabel('bottom', 'Time' if time_labels else 'Bar Index')
        
        # Show 6-10 even labels for dense data
        if time_labels and len(time_labels) >= 2:
            axis = self.pw.getAxis('bottom')
            total = len(time_labels)
            # Calculate step for ~8 labels
            step = max(1, total // 8)
            tick_indices = list(range(0, total, step))
            # Ensure last one is included
            if (total - 1) not in tick_indices:
                tick_indices.append(total - 1)
            
            ticks = [(i, time_labels[i]) for i in tick_indices]
            axis.setTicks([ticks, []])

def show_chart_with_signals(df, signals=None, title="Stock Chart",
                            avg_series=None, time_labels=None, use_line=False):
    """Quick helper to show a chart."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    win = StandaloneKlineChart(df, signals, title, avg_series, time_labels, use_line)
    win.show()
    # If this is called from a script, we might want to exec
    if sys.stdin.isatty() or 'IPython' not in sys.modules:
        app.exec()
    return win

if __name__ == "__main__":
    # Test/Demo
    dates = pd.date_range('2026-01-01', periods=20)
    data = {
        'open': [60, 61, 62, 59, 58, 60, 63, 62, 64, 65, 63, 62, 61, 62, 64, 66, 67, 68, 66, 65],
        'high': [62, 63, 63, 61, 60, 62, 64, 64, 66, 67, 65, 64, 62, 64, 66, 68, 69, 70, 68, 67],
        'low': [59, 60, 61, 58, 57, 59, 61, 61, 63, 64, 62, 61, 60, 61, 63, 65, 66, 67, 65, 64],
        'close': [61, 62, 59, 58, 60, 61, 62, 64, 65, 63, 62, 61, 62, 64, 66, 67, 68, 66, 65, 64]
    }
    df = pd.DataFrame(data, index=dates)
    
    # Mock signals
    try:
        from signal_types import SignalPoint, SignalType, SignalSource
        s1 = SignalPoint('688787', dates[4], 4, 60.0, SignalType.BUY, reason="V反")
        s2 = SignalPoint('688787', dates[14], 14, 66.0, SignalType.FOLLOW, reason="SBC突破")
        signals = [s1, s2]
    except:
        class MockSig:
            def __init__(self, i, p, t):
                self.bar_index = i
                self.price = p
                self.signal_type = t
                self.symbol = 't1' if t == '买入' else '🎯'
                self.color = (255, 0, 0) if t == '买入' else (255, 215, 0)
                self.size = 15
        signals = [MockSig(4, 60.0, "买入"), MockSig(14, 66.0, "跟单")]

    show_chart_with_signals(df, signals, "Visualization Demo")
