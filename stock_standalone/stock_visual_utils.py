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

try:
    from tk_gui_modules.window_mixin import WindowMixin
except ImportError:
    # If missing, define a dummy mixin to avoid crashing
    class WindowStateMixin:
        def load_window_position_qt(self, *args, **kwargs): pass
        def save_window_position_qt(self, *args, **kwargs): pass


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
            # 兼容对象和字典
            if isinstance(sig, dict):
                x_pos = sig.get('bar_index', 0)
                y_pos = sig.get('price', 0)
                reason = str(sig.get('reason', ''))
                # 优先从 reason 提取图标逻辑：🎯 (初次/买点) -> 🚀 (结构) -> 🔥 (加速)
                if "🔥" in reason or "趋势加速" in reason: symbol = "🔥"
                elif "🚀" in reason or "强势结构" in reason: symbol = "🚀"
                elif "🎯" in reason or "买入" in reason: symbol = "🎯" # 基础买点显示为 🎯
                else: symbol = sig.get('symbol', 'o')
                color = sig.get('color', (255, 255, 0))
                size = sig.get('size', 12)
                sig_type_str = str(sig.get('signal_type', '')).upper()
            else:
                x_pos = getattr(sig, 'bar_index', 0)
                y_pos = getattr(sig, 'price', 0)
                reason = str(getattr(sig, 'reason', ''))
                symbol = getattr(sig, 'symbol', 'o')
                # If symbol is a generic 'o' or '🎯', try to infer a more specific emoji from reason
                if symbol == 'o' or symbol == '🎯': 
                    if "🔥" in reason or "趋势加速" in reason: symbol = "🔥"
                    elif "🚀" in reason or "强势结构" in reason: symbol = "🚀"
                    elif "🎯" in reason or "买入" in reason: symbol = "🎯"
                
                color = getattr(sig, 'color', (255, 255, 0))
                size = getattr(sig, 'size', 12)
            
            is_emoji = symbol in ('🎯', '🚀', '🔥')
            
            # Scatter attributes (fallback for emojis)
            xs.append(x_pos)
            ys.append(y_pos)
            brushes.append(pg.mkBrush(color))
            symbols.append('o' if is_emoji else symbol)
            sizes.append(size)
            
            # Determine if it's a buy-side or sell-side signal for coloring and anchor
            # 精确匹配，避免 EXIT_FOLLOW 包含 FOLLOW 关键字导致误判
            sig_type_str = str(getattr(sig, 'signal_type', '')).upper()
            is_buy = any(kw in sig_type_str for kw in ["BUY", "FOLLOW", "买入", "加仓"]) and "EXIT" not in sig_type_str
            
            label_color = QColor(255, 120, 120) if is_buy else QColor(120, 255, 120)
            anchor = (0.5, 1.2) if is_buy else (0.5, -0.5)
            
            # Text Price Label: 包含分数显示
            debug_info = getattr(sig, 'debug_info', {})
            score_text = ""
            if is_buy and 'buy_score' in debug_info:
                score_text = f" <span style='font-size: 8pt; color: #FFFF00; font-weight: bold;'>({debug_info['buy_score']})</span>"
            elif not is_buy and 'sell_score' in debug_info:
                score_text = f" <span style='font-size: 8pt; color: #FFFF00; font-weight: bold;'>({debug_info['sell_score']})</span>"
            
            # Simplify action reason to save space, and remove redundant emojis
            action_name = "买" if is_buy else "卖"
            if reason:
                # 简化文本，提纯描述
                reason_clean = reason.replace("强势结构", "强势") \
                                     .replace("均线上-创多日高-", "") \
                                     .replace("诱空转多-", "") \
                                     .replace("趋势加速", "加速")
                if is_emoji:
                    # 如果 reason 里已经包含图标，去掉 reason 中的图标以免和 symbol 重复
                    reason_clean = reason_clean.replace(symbol, "").strip()
                    reason_text = f" | {symbol} {action_name}: {reason_clean}"
                else:
                    reason_text = f" | {action_name}: {reason_clean}"
            else:
                reason_text = f" | {action_name}"

            # 恢复之前用户喜欢的文字背景与边框效果，保证清晰度
            bg_brush = pg.mkBrush(20, 20, 20, 220)
            border_pen = pg.mkPen(label_color, width=1)
            
            text = pg.TextItem(anchor=anchor, fill=bg_brush, border=border_pen)
            weight = "font-weight: bold;" if not is_buy else ""
            text.setHtml(f'<div style="color: {label_color.name()}; font-size: 9pt; {weight}; padding: 2px;">{y_pos:.2f}{score_text}{reason_text}</div>')
            text.setPos(x_pos, y_pos)
            self.plot_item.addItem(text)
            self.text_items.append(text)
            
            # Emoji Marker Overlay
            if is_emoji:
                emoji = pg.TextItem(symbol, anchor=(0.5, 0.5))
                # 增大图标字号提高辨识度
                emoji.setHtml(f'<div style="font-size: 16pt;">{symbol}</div>')
                emoji.setPos(x_pos, y_pos)
                self.plot_item.addItem(emoji)
                self.text_items.append(emoji)

        self.scatter.setData(x=xs, y=ys, brush=brushes, symbol=symbols, size=sizes)

class PercentAxisItem(pg.AxisItem):
    """Custom axis to display percentage change from a base price."""
    def __init__(self, base_price, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_price = base_price

    def tickStrings(self, values, scale, spacing):
        if not self.base_price:
            return ["%.2f" % v for v in values]
        return [f"{(v - self.base_price) / self.base_price * 100:+.2f}%" for v in values]

    def set_base_price(self, base_price):
        """Update the base price for calculations dynamically."""
        if self.base_price != base_price:
            self.base_price = base_price
            self.picture = None # invalidate cache
            self.update()

class StandaloneKlineChart(QMainWindow, WindowMixin):
    """Simple chart window for visualization."""
    def __init__(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1000, 600)
        
        central_widget = QWidget()
        # 移除四周的白边距
        central_widget.setStyleSheet("background-color: black;")
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Setup Axis if time labels provided
        axis_items = {}
        if time_labels:
            # time_labels can be a list of strings matching the df rows
            time_map = {i: label for i, label in enumerate(time_labels)}
            axis_items['bottom'] = TimeAxisItem(time_map, orientation='bottom')
            
        base_price = None
        if df is not None and not df.empty:
            # 优先从字段获取昨日收盘
            if 'llastp' in df.columns and df['llastp'].iloc[-1] > 0:
                base_price = df['llastp'].iloc[-1]
            elif 'pre_close' in df.columns and df['pre_close'].iloc[-1] > 0:
                base_price = df['pre_close'].iloc[-1]
            # 如果没找到，且数据里有 open，由于这是 StandaloneKlineChart，
            # 可能是当前交易日的数据，prices[0] 可能是 Open，不是 pre_close。
            # 这里先检查是否真的没有 pre_close 字段。
            elif 'open' in df.columns:
                base_price = df['open'].iloc[0]
            elif 'close' in df.columns:
                base_price = df['close'].iloc[0]
                
        if base_price:
            self.base_price_ref = base_price # 保存一份引用
            axis_items['right'] = PercentAxisItem(base_price, orientation='right')
            
        self.pw = pg.PlotWidget(axisItems=axis_items)
        layout.addWidget(self.pw)
        
        if 'right' in axis_items:
            self.pw.showAxis('right')
            # link right axis to left axis range
            self.pw.getAxis('right').linkToView(self.pw.getViewBox())
        
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
        # self.pw.setLabel('bottom', 'Time' if time_labels else 'Bar Index')
        
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
            
        # load previously saved window position
        # self.load_window_position_qt(self, f"StandaloneKlineChart_{title}", default_width=1000, default_height=600)
        self.load_window_position_qt(self, f"StandaloneKlineChart", default_width=1000, default_height=600)

        # Crosshair setup
        self.df_ref = df
        self.time_labels_ref = time_labels
        self.base_price_ref = base_price
        
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color=(150, 150, 150, 180), style=Qt.PenStyle.DashLine))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(color=(150, 150, 150, 180), style=Qt.PenStyle.DashLine))
        self.pw.addItem(self.v_line, ignoreBounds=True)
        self.pw.addItem(self.h_line, ignoreBounds=True)
        
        self.crosshair_label = pg.TextItem(anchor=(0, 1), fill=pg.mkBrush(20, 20, 20, 220))
        self.crosshair_label.setZValue(200) # Always on top
        self.crosshair_label.hide() # Initially hidden until mouse moves
        self.pw.addItem(self.crosshair_label, ignoreBounds=True)
        
        self.proxy = pg.SignalProxy(self.pw.scene().sigMouseMoved, rateLimit=60, slot=self.mouse_moved)

    def mouse_moved(self, evt):
        pos = evt[0]
        if self.pw.sceneBoundingRect().contains(pos):
            # Show crosshair on first movement
            if not self.crosshair_label.isVisible():
                self.crosshair_label.show()
                
            mouse_point = self.pw.plotItem.vb.mapSceneToView(pos)
            index = int(mouse_point.x())
            y_val = mouse_point.y()
            
            if self.df_ref is not None and 0 <= index < len(self.df_ref):
                self.v_line.setPos(mouse_point.x())
                self.h_line.setPos(mouse_point.y())
                
                pct_str = ""
                if self.base_price_ref and self.base_price_ref > 0:
                    pct = (y_val - self.base_price_ref) / self.base_price_ref * 100
                    pct_str = f"&nbsp;&nbsp;<span style='color: {'#FF7878' if pct >= 0 else '#78FF78'};'>{pct:+.2f}%</span>"
                
                time_str = f"idx: {index}"
                if self.time_labels_ref and index < len(self.time_labels_ref):
                    time_str = str(self.time_labels_ref[index])
                
                html = f"<div style='font-size: 10pt; color: white;'>[ {time_str} ]<br/><b>{y_val:.2f}</b>{pct_str}</div>"
                self.crosshair_label.setHtml(html)
                
                # Flip anchor to avoid the cursor clipping
                view_rect = self.pw.viewRect()
                if mouse_point.x() > view_rect.center().x():
                    self.crosshair_label.setAnchor((1, 1))
                else:
                    self.crosshair_label.setAnchor((0, 1))
                    
                self.crosshair_label.setPos(mouse_point.x(), y_val)

    def closeEvent(self, event):
        """窗口关闭事件：保存位置"""
        try:
            self.save_window_position_qt(self, f"StandaloneKlineChart")
            # self.save_window_position_qt(self, f"StandaloneKlineChart_{self.windowTitle()}")
            # self.save_window_position_qt_visual(self, f"StandaloneKlineChart_{self.windowTitle()}")
        except Exception as e:
            print(f"Error saving window position: {e}")
        super().closeEvent(event)

    def keyPressEvent(self, event):
        """支持快捷键操作，特别是 ESC 退出"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

def show_chart_with_signals(df, signals=None, title="Stock Chart",
                            avg_series=None, time_labels=None, use_line=False):
    """Quick helper to show a chart."""
    app = QApplication.instance()
    is_new_app = False
    if not app:
        app = QApplication(sys.argv)
        is_new_app = True
    
    win = StandaloneKlineChart(df, signals, title, avg_series, time_labels, use_line)
    win.show()

    # [FIX] 仅在独立脚本运行时启动主循环，避免在已有 GUI (竞价面板) 中报错闪退
    if is_new_app:
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
