import sys
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QPushButton
from PyQt6.QtGui import QColor, QPicture, QPainter
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
# WindowMixin is used for saving/loading window position
from tk_gui_modules.window_mixin import WindowMixin

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
        self.time_map = time_map or {}  # {index: "HH:MM"}

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
            if isinstance(sig, dict):
                x_pos = sig.get('bar_index', 0)
                y_pos = sig.get('price', 0)
                reason = str(sig.get('reason', ''))
                if "🔥" in reason or "趋势加速" in reason: symbol = "🔥"
                elif "🚀" in reason or "强势结构" in reason: symbol = "🚀"
                elif "🎯" in reason or "买入" in reason: symbol = "🎯"
                else: symbol = sig.get('symbol', 'o')
                color = sig.get('color', (255, 255, 0))
                size = sig.get('size', 12)
                sig_type_str = str(sig.get('signal_type', '')).upper()
            else:
                x_pos = getattr(sig, 'bar_index', 0)
                y_pos = getattr(sig, 'price', 0)
                reason = str(getattr(sig, 'reason', ''))
                symbol = getattr(sig, 'symbol', 'o')
                if symbol == 'o' or symbol == '🎯': 
                    if "🔥" in reason or "趋势加速" in reason: symbol = "🔥"
                    elif "🚀" in reason or "强势结构" in reason: symbol = "🚀"
                    elif "🎯" in reason or "买入" in reason: symbol = "🎯"
                color = getattr(sig, 'color', (255, 255, 0))
                size = getattr(sig, 'size', 12)
                sig_type_str = str(getattr(sig, 'signal_type', '')).upper()
            
            is_emoji = symbol in ('🎯', '🚀', '🔥')
            xs.append(x_pos)
            ys.append(y_pos)
            brushes.append(pg.mkBrush(color))
            symbols.append('o' if is_emoji else symbol)
            sizes.append(size)
            
            is_buy = any(kw in sig_type_str for kw in ["BUY", "FOLLOW", "买入", "加仓"]) and "EXIT" not in sig_type_str
            label_color = QColor(255, 120, 120) if is_buy else QColor(120, 255, 120)
            anchor = (0.5, 1.2) if is_buy else (0.5, -0.5)
            
            debug_info = getattr(sig, 'debug_info', {}) if not isinstance(sig, dict) else sig.get('debug_info', {})
            score_text = ""
            if is_buy and 'buy_score' in debug_info:
                score_text = f" <span style='font-size: 8pt; color: #FFFF00; font-weight: bold;'>({debug_info['buy_score']})</span>"
            elif not is_buy and 'sell_score' in debug_info:
                score_text = f" <span style='font-size: 8pt; color: #FFFF00; font-weight: bold;'>({debug_info['sell_score']})</span>"
            
            action_name = "买" if is_buy else "卖"
            if reason:
                reason_clean = reason.replace("强势结构", "强势") \
                                     .replace("均线上-创多日高-", "") \
                                     .replace("诱空转多-", "") \
                                     .replace("趋势加速", "加速") \
                                     .replace("冠军核心回踩", "回踩") \
                                     .replace("突破回踩", "回踩") \
                                     .replace("分时新高", "新高")
                if is_emoji:
                    reason_clean = reason_clean.replace(symbol, "").strip()
                max_chars = 8
                if len(reason_clean) > max_chars:
                    lines = [reason_clean[i:i+max_chars] for i in range(0, len(reason_clean), max_chars)]
                    reason_final = "<br/>".join(lines)
                else:
                    reason_final = reason_clean

                if is_emoji:
                    reason_text = f" | {symbol} {action_name}: {reason_final}"
                else:
                    reason_text = f" | {action_name}: {reason_final}"
            else:
                reason_text = f" | {action_name}"

            bg_brush = pg.mkBrush(20, 20, 20, 220)
            border_pen = pg.mkPen(label_color, width=1)
            text = pg.TextItem(anchor=anchor, fill=bg_brush, border=border_pen)
            weight = "font-weight: bold;" if not is_buy else ""
            text.setHtml(f'<div style="color: {label_color.name()}; font-size: 9pt; {weight}; padding: 2px;">{y_pos:.2f}{score_text}{reason_text}</div>')
            text.setPos(x_pos, y_pos)
            self.plot_item.addItem(text)
            self.text_items.append(text)
            
            if is_emoji:
                emoji = pg.TextItem(symbol, anchor=(0.5, 0.5))
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
            self.picture = None 
            self.update()

class StandaloneKlineChart(QMainWindow, WindowMixin):
    """Simple chart window for visualization."""
    def __init__(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None):
        super().__init__()
        if signals is not None and "SBC" not in title:
            title = f"SBC Pattern - {title}"
            
        self.setWindowTitle(title)
        self.resize(1000, 600)
        
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: black;")
        self.setCentralWidget(central_widget)
        self.layout_widget = QVBoxLayout(central_widget)
        self.layout_widget.setContentsMargins(0, 0, 0, 0)
        self.layout_widget.setSpacing(0)
        
        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(30)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 0, 5, 0)
        btn_layout = QHBoxLayout()
        self.btn_rearrange = QPushButton("窗口重排")
        self.btn_rearrange.setFixedWidth(80)
        self.btn_rearrange.setStyleSheet("background-color: #444; color: white; border: 1px solid #666;")
        self.btn_rearrange.clicked.connect(self._on_rearrange_clicked)
        btn_layout.addWidget(self.btn_rearrange)
        btn_layout.addStretch()
        toolbar_layout.addLayout(btn_layout)
        self.layout_widget.addWidget(toolbar)
        
        self.pw = None
        self.v_line = None
        self.h_line = None
        self.crosshair_label = None
        self.proxy = None
        
        self.update_plot(df, signals, title, avg_series, time_labels, use_line, extra_lines, init=True)

        self.load_window_position_qt(self, f"StandaloneKlineChart", default_width=1000, default_height=600)
        
        if "SBC" in title:
            try:
                try:
                    from .qt_window_utils import place_next_to
                except ImportError:
                    from qt_window_utils import place_next_to
                QTimer.singleShot(200, lambda: place_next_to(int(self.winId()), "Sector Bidding Panel"))
            except Exception as e:
                print(f"Smart placement error: {e}")

    def mouse_moved(self, evt):
        pos = evt[0]
        if self.pw is not None and self.pw.sceneBoundingRect().contains(pos):
            if self.crosshair_label and not self.crosshair_label.isVisible():
                self.crosshair_label.show()
                
            mouse_point = self.pw.plotItem.vb.mapSceneToView(pos)
            index = int(mouse_point.x())
            y_val = mouse_point.y()
            
            if self.df_ref is not None and 0 <= index < len(self.df_ref):
                if self.v_line: self.v_line.setPos(mouse_point.x())
                if self.h_line: self.h_line.setPos(mouse_point.y())
                
                pct_str = ""
                if hasattr(self, 'base_price_ref') and self.base_price_ref and self.base_price_ref > 0:
                    pct = (y_val - self.base_price_ref) / self.base_price_ref * 100
                    pct_str = f"&nbsp;&nbsp;<span style='color: {'#FF7878' if pct >= 0 else '#78FF78'};'>{pct:+.2f}%</span>"
                
                time_str = f"idx: {index}"
                if self.time_labels_ref and index < len(self.time_labels_ref):
                    time_str = str(self.time_labels_ref[index])
                
                html = f"<div style='font-size: 10pt; color: white;'>[ {time_str} ]<br/><b>{y_val:.2f}</b>{pct_str}</div>"
                if self.crosshair_label:
                    self.crosshair_label.setHtml(html)
                    view_rect = self.pw.viewRect()
                    if mouse_point.x() > view_rect.center().x():
                        self.crosshair_label.setAnchor((1, 1))
                    else:
                        self.crosshair_label.setAnchor((0, 1))
                    self.crosshair_label.setPos(mouse_point.x(), y_val)

    def update_plot(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, init=False):
        if signals is not None and "SBC" not in title:
            title = f"SBC Pattern - {title}"
        self.setWindowTitle(title)
        
        # Recreate PlotWidget to handle axis switch correctly
        if self.pw is not None:
            self.layout_widget.removeWidget(self.pw)
            self.pw.deleteLater()
            self.pw = None

        axis_items = {}
        if time_labels:
            time_map = {i: label for i, label in enumerate(time_labels)}
            axis_items['bottom'] = TimeAxisItem(time_map, orientation='bottom')
            
        base_price = None
        if df is not None and not df.empty:
            if 'llastp' in df.columns and df['llastp'].iloc[-1] > 0:
                base_price = df['llastp'].iloc[-1]
            elif 'pre_close' in df.columns and df['pre_close'].iloc[-1] > 0:
                base_price = df['pre_close'].iloc[-1]
            elif 'open' in df.columns:
                base_price = df['open'].iloc[0]
            elif 'close' in df.columns:
                base_price = df['close'].iloc[0]
                
        if base_price:
            self.base_price_ref = base_price
            axis_items['right'] = PercentAxisItem(base_price, orientation='right')
            
        self.pw = pg.PlotWidget(axisItems=axis_items)
        self.layout_widget.addWidget(self.pw)
        
        if 'right' in axis_items:
            self.pw.showAxis('right')
            self.pw.getAxis('right').linkToView(self.pw.getViewBox())
        
        if df is not None:
            if use_line:
                close_y = df['close'].values
                close_x = np.arange(len(close_y))
                self.pw.plot(close_x, close_y, pen=pg.mkPen(QColor(100, 200, 255), width=1.5), name="Price")
            else:
                k_data = []
                for i, (idx, row) in enumerate(df.iterrows()):
                    k_data.append([i, row['open'], row['close'], row['low'], row['high']])
                self.candlestick = CandlestickItem(k_data)
                self.pw.addItem(self.candlestick)
        
        if avg_series is not None:
            avg_x = np.arange(len(avg_series))
            avg_y = np.asarray(avg_series)
            self.pw.plot(avg_x, avg_y, pen=pg.mkPen(QColor(255, 255, 255, 180), width=1.5, style=Qt.PenStyle.DashLine), name="VWAP")
        
        if extra_lines:
            lc = extra_lines.get('last_close', 0)
            lh = extra_lines.get('last_high', 0)
            ll = extra_lines.get('last_low', 0)
            if lc > 0:
                l_pen = pg.mkPen(QColor(255, 255, 0, 255), width=2.5, style=Qt.PenStyle.SolidLine)
                l = pg.InfiniteLine(angle=0, movable=False, pen=l_pen, label="LC:{value:.2f}", labelOpts={'position': 0.95, 'color': (255, 255, 0)})
                l.setPos(lc); self.pw.addItem(l)
            if lh > 0:
                h_pen = pg.mkPen(QColor(255, 0, 255, 255), width=2.5, style=Qt.PenStyle.SolidLine)
                h = pg.InfiniteLine(angle=0, movable=False, pen=h_pen, label="LH:{value:.2f}", labelOpts={'position': 0.85, 'color': (255, 0, 255)})
                h.setPos(lh); self.pw.addItem(h)
            if ll > 0:
                lo = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(QColor(255, 50, 50, 200), width=2, style=Qt.PenStyle.DashLine), label="LL:{value:.2f}", labelOpts={'position': 0.75, 'color': (255, 50, 50)})
                lo.setPos(ll); self.pw.addItem(lo)
            h4 = extra_lines.get('high4', 0)
            if h4 > 0:
                h4l = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(QColor(0, 255, 0, 220), width=3, style=Qt.PenStyle.SolidLine), label="H4:{value:.2f}", labelOpts={'position': 0.65, 'color': (0, 255, 0)})
                h4l.setPos(h4); self.pw.addItem(h4l)

        if df is not None and not df.empty:
            if extra_lines:
                lh_ref = extra_lines.get('last_high', 0)
                ll_ref = extra_lines.get('last_low', 0)
                day_low = df['low'].min()
                day_high = df['high'].max()
                if lh_ref > 0 and day_low > lh_ref:
                    self.pw.addItem(pg.LinearRegionItem([lh_ref, day_low], orientation=pg.LinearRegionItem.Horizontal, brush=QColor(0, 80, 255, 30), movable=False))
                if ll_ref > 0 and day_high < ll_ref:
                    self.pw.addItem(pg.LinearRegionItem([day_high, ll_ref], orientation=pg.LinearRegionItem.Horizontal, brush=QColor(255, 30, 0, 30), movable=False))
            
            if not use_line and len(df) > 1:
                lows = df['low'].values
                highs = df['high'].values
                for i in range(1, len(df)):
                    if lows[i] > highs[i-1]:
                        self.pw.addItem(pg.LinearRegionItem([highs[i-1], lows[i]], orientation=pg.LinearRegionItem.Horizontal, brush=QColor(0, 200, 255, 20), movable=False))
                    elif highs[i] < lows[i-1]:
                        self.pw.addItem(pg.LinearRegionItem([highs[i], lows[i-1]], orientation=pg.LinearRegionItem.Horizontal, brush=QColor(255, 50, 0, 20), movable=False))
        
        self.overlay = SignalOverlay(self.pw)
        if signals: self.overlay.update_signals(signals)
            
        self.pw.showGrid(x=True, y=True, alpha=0.3)
        self.pw.setLabel('left', 'Price')
        
        if time_labels and len(time_labels) >= 2:
            axis = self.pw.getAxis('bottom')
            total = len(time_labels)
            step = max(1, total // 8)
            ticks = [(i, time_labels[i]) for i in range(0, total, step)]
            if (total-1) not in [t[0] for t in ticks]: ticks.append((total-1, time_labels[total-1]))
            axis.setTicks([ticks, []])
            
        # Re-attach Crosshair
        self.df_ref = df
        self.time_labels_ref = time_labels
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color=(150, 150, 150, 180), style=Qt.PenStyle.DashLine))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(color=(150, 150, 150, 180), style=Qt.PenStyle.DashLine))
        self.pw.addItem(self.v_line, ignoreBounds=True)
        self.pw.addItem(self.h_line, ignoreBounds=True)
        self.crosshair_label = pg.TextItem(anchor=(0, 1), fill=pg.mkBrush(20, 20, 20, 220))
        self.crosshair_label.setZValue(200)
        self.crosshair_label.hide()
        self.pw.addItem(self.crosshair_label, ignoreBounds=True)
        self.proxy = pg.SignalProxy(self.pw.scene().sigMouseMoved, rateLimit=60, slot=self.mouse_moved)

    def closeEvent(self, event):
        try: self.save_window_position_qt_visual(self, f"StandaloneKlineChart")
        except: pass
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()
        else: super().keyPressEvent(event)

    def _on_rearrange_clicked(self):
        try:
            try: from .qt_window_utils import tile_all_windows
            except ImportError: from qt_window_utils import tile_all_windows
            tile_all_windows()
        except: pass

def show_chart_with_signals(df, signals=None, title="Stock Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, existing_win=None):
    existing_instance = QApplication.instance()
    app = existing_instance or QApplication(sys.argv)
    is_new_app = (existing_instance is None)
    
    win = None
    if existing_win is not None and hasattr(existing_win, 'update_plot') and existing_win.isVisible():
        try:
            existing_win.update_plot(df, signals, title, avg_series, time_labels, use_line, extra_lines)
            existing_win.raise_()
            existing_win.activateWindow()
            win = existing_win
        except Exception as e:
            print(f"Reuse failed: {e}")
            
    if win is None:
        win = StandaloneKlineChart(df, signals, title, avg_series, time_labels, use_line, extra_lines)
        win.show()

    if is_new_app: app.exec()
    return win

if __name__ == "__main__":
    dates = pd.date_range('2026-01-01', periods=20)
    data = {'open': [60,61,62,59,58,60,63,62,64,65,63,62,61,62,64,66,67,68,66,65],
            'high': [62,63,63,61,60,62,64,64,66,67,65,64,62,64,66,68,69,70,68,67],
            'low': [59,60,61,58,57,59,61,61,63,64,62,61,60,61,63,65,66,67,65,64],
            'close': [61,62,59,58,60,61,62,64,65,63,62,61,62,64,66,67,68,66,65,64]}
    df = pd.DataFrame(data, index=dates)
    show_chart_with_signals(df, None, "Visualization Demo")
