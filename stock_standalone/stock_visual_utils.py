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

    def update_signals(self, signals, is_compact=False):
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
            if is_compact:
                reason_text = f" | {action_name}"
            else:
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
    def __init__(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, refresh_func=None, max_signals=20, max_vlines=12, max_hlines=5):
        super().__init__()
        self.max_signals = max_signals
        self.max_vlines = max_vlines
        self.max_hlines = max_hlines
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
        
        # [NEW] Linkage button
        self.btn_link = QPushButton("🔗 联动")
        self.btn_link.setFixedWidth(70)
        self.btn_link.setStyleSheet("background-color: #AA4444; color: white; border: 1px solid #FF8888; font-weight: bold;")
        self.btn_link.clicked.connect(self._on_linkage_clicked)
        btn_layout.addWidget(self.btn_link)
        
        btn_layout.addStretch()

        self.btn_reset = QPushButton("重置 (R)")
        self.btn_reset.setFixedWidth(70)
        self.btn_reset.setStyleSheet("background-color: #333; color: #CCC; border: 1px solid #555;")
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        btn_layout.addWidget(self.btn_reset)

        toolbar_layout.addLayout(btn_layout)
        self.layout_widget.addWidget(toolbar)
        
        self.pw = None
        self.v_line = None
        self.h_line = None
        self.crosshair_label = None
        self.proxy = None
        
        self.update_plot(df, signals, title, avg_series, time_labels, use_line, extra_lines, init=True)

        self.load_window_position_qt(self, f"StandaloneKlineChart", default_width=1000, default_height=600)
        
        self.refresh_func = refresh_func
        if self.refresh_func:
            try:
                try:
                    from stock_standalone.JohnsonUtil import commonTips as cct
                except ImportError:
                    from JohnsonUtil import commonTips as cct
                conf_ini = cct.get_conf_path('global.ini')
                if not conf_ini:
                    print("global.ini 加载失败，程序无法继续运行动态刷新")
                    duration_sleep_time = 5
                else:
                    CFG = cct.GlobalConfig(conf_ini)
                    duration_sleep_time = getattr(CFG, 'duration_sleep_time', 5)
            except Exception as e:
                print(f"配置加载异常: {e}")
                duration_sleep_time = 5
                
            self.refresh_timer = QTimer(self)
            self.refresh_timer.timeout.connect(self._on_refresh_timer)
            self.refresh_timer.start(int(duration_sleep_time * 1000))
        
        if "SBC" in title:
            try:
                try:
                    from .qt_window_utils import place_next_to
                except ImportError:
                    from qt_window_utils import place_next_to
                QTimer.singleShot(200, lambda: place_next_to(int(self.winId()), "Sector Bidding Panel"))
            except Exception as e:
                print(f"Smart placement error: {e}")

    def _on_refresh_timer(self):
        if hasattr(self, 'refresh_func') and self.refresh_func:
            try:
                res = self.refresh_func()
                if res and isinstance(res, dict):
                    df = res.get('viz_df') if 'viz_df' in res else res.get('df')
                    sig = res.get('signals')
                    ttl = res.get('title', self.windowTitle())
                    avg = res.get('avg_series')
                    lbl = res.get('time_labels')
                    uline = res.get('use_line', False)
                    ext = res.get('extra_lines')
                    if df is not None and not df.empty:
                        self.update_plot(df, sig, ttl, avg, lbl, uline, ext)
            except Exception as e:
                print(f"动态刷新失败: {e}")

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

    def _on_reset_clicked(self):
        """重置显示内容自适应 (不改变窗口大小)"""
        if self.pw:
            self.pw.autoRange()
            print("📊 视图已重置为自动自适应范围")

    # --- 统一方法管理 (移除冗余重复定义) ---

    def update_plot(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, init=False):
        if signals is not None and "SBC" not in title:
            title = f"SBC Pattern - {title}"
        self.setWindowTitle(title)
        
        # Only recreate PlotWidget on init to avoid severe flicker and jump
        is_compact = self.width() < 800

        if not init and self.pw is not None:
            self.pw.clear()
            if hasattr(self, 'overlay'):
                self.overlay.text_items.clear()
            
            if time_labels:
                axis_bottom = self.pw.getAxis('bottom')
                if isinstance(axis_bottom, TimeAxisItem):
                    axis_bottom.time_map = {i: label for i, label in enumerate(time_labels)}
                    axis_bottom.picture = None
                    axis_bottom.update()
        else:
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
            cur_price = df['close'].iloc[-1] if df is not None and not df.empty else 0
            
            # [FIX] 分时图 (use_line=True) 恢复原本的清晰参考线，不去限制数量，确保分时交易有水位参考
            if use_line:
                # 恢复默认：完全不透明度和经典线宽
                base_lines = [
                    ('LC', extra_lines.get('last_close', 0), QColor(255, 255, 0, 255)),
                    ('LH', extra_lines.get('last_high', 0),  QColor(255, 0, 255, 255)),
                    ('LL', extra_lines.get('last_low', 0),   QColor(255, 50, 50, 220)),
                    ('H4', extra_lines.get('high4', 0),      QColor(0, 255, 0, 255))
                ]
                candidates = [l for l in base_lines if l[1] > 0]
            else:
                # K线图 (use_line=False) 实施精简策略，只显示离现价最近的 N 条，且线条更淡
                base_lines = [
                    ('LC', extra_lines.get('last_close', 0), QColor(255, 255, 0, 120)),
                    ('LH', extra_lines.get('last_high', 0),  QColor(255, 0, 255, 120)),
                    ('LL', extra_lines.get('last_low', 0),   QColor(255, 50, 50, 120)),
                    ('H4', extra_lines.get('high4', 0),      QColor(0, 255, 0, 120))
                ]
                candidates = [l for l in base_lines if l[1] > 0]
                if len(candidates) > self.max_hlines:
                    candidates.sort(key=lambda x: abs(x[1] - cur_price))
                    candidates = candidates[:self.max_hlines]
            
            for label, price, color in candidates:
                # 加载不同的样式权重
                if use_line:
                    width = 2.5 if label == 'LC' else 1.8
                    style = Qt.PenStyle.SolidLine if label in ('LC', 'LH') else Qt.PenStyle.DashLine
                else:
                    width = 1.0 if label == 'LC' else 0.6
                    style = Qt.PenStyle.SolidLine if label in ('LC', 'LH') else Qt.PenStyle.DashLine
                
                pen = pg.mkPen(color, width=width, style=style)
                inf_line = pg.InfiniteLine(
                    pos=price, angle=0, movable=False, pen=pen,
                    label=f"{label}:{{value:.2f}}", 
                    labelOpts={'position': 0.9, 'color': color}
                )
                self.pw.addItem(inf_line)

        # [REFINED] 仅在 K 线图模式限制信号数量，分时图显示全部
        if not use_line and signals and len(signals) > self.max_signals:
            signals = signals[-self.max_signals:]

        self.overlay = SignalOverlay(self.pw)
        if signals: self.overlay.update_signals(signals, is_compact=is_compact)
            
        # [NEW] 自定义网格：分时图使用默认网格线，K线图使用自定义稀疏网格
        if use_line:
            self.pw.showGrid(x=True, y=True, alpha=0.2)
        else:
            self.pw.showGrid(x=False, y=True, alpha=0.05) # 极淡的横线
            if time_labels:
                v_pen = pg.mkPen(QColor(100, 100, 100, 60), width=0.8, style=Qt.PenStyle.DotLine)
            
            # [REFINED] 动态计算间隔：根据总时长和 max_vlines 自动调整竖线密度
            # 常见间隔：1, 5, 15, 30, 60 分钟
            total_minutes = len(time_labels) # 假设 1 tick/min 或类似
            potential_intervals = [1, 5, 15, 30, 60, 120]
            interval = 15
            for pi in potential_intervals:
                if (total_minutes / pi) <= self.max_vlines:
                    interval = pi
                    break

            last_mark = None
            for i, tl in enumerate(time_labels):
                try:
                    t_parts = str(tl).split(":")
                    if len(t_parts) < 2: continue
                    hh, mm = int(t_parts[0]), int(t_parts[1])
                    # 按计算出的间隔绘制竖线
                    if mm % interval == 0 and (hh, mm) != last_mark:
                        v_line = pg.InfiniteLine(pos=i, angle=90, pen=v_pen, movable=False)
                        self.pw.addItem(v_line)
                        last_mark = (hh, mm)
                except:
                    continue

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
        """统一按键处理：R 重置，Esc 退出"""
        key = event.key()
        if key == Qt.Key.Key_R:
            self._on_reset_clicked()
        elif key == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def _on_rearrange_clicked(self):
        """调用全局重排逻辑"""
        try:
            try: from .qt_window_utils import tile_all_windows
            except ImportError: from qt_window_utils import tile_all_windows
            tile_all_windows()
        except: pass

    def _on_linkage_clicked(self):
        import re
        title = self.windowTitle()
        match = re.search(r'(?:\[|\b)(\d{6})(?:\]|\b)', title)
        if not match:
            print("未在标题中找到6位股票代码，无法联动")
            return
            
        code = match.group(1)
        print(f"🔗 启动联动核心: {code}")

        # --- ⚡ [FAST PATH] 瞬间响应部分 ---

        # 1. 复制到剪贴板 (最快，TK 按键可立即生效)
        try:
            QApplication.clipboard().setText(code)
        except: pass

        # 2. 发送到关联的可视化和监控面板 (PyQt6 内存级别联动)
        try:
            for widget in QApplication.topLevelWidgets():
                if widget is self: continue
                # 兼容可视化器和主监控面板的信号/方法
                if hasattr(widget, 'tree_scroll_to_code'):
                    try: widget.tree_scroll_to_code(code, vis=True)
                    except: pass
                elif hasattr(widget, 'scroll_to_code_signal'):
                    try: widget.scroll_to_code_signal.emit(code)
                    except: pass
                # [NEW] 尝试检查是否有指令队列 (Queue 模式)
                if hasattr(widget, 'command_queue') and widget.command_queue:
                    try: widget.command_queue.put(('SWITCH_CODE', {'code': code}))
                    except: pass
        except: pass

        # 3. 通过 Socket IPC 联动外部可视化进程 (跨进程极致速度)
        def send_socket():
            try:
                import socket
                ipc_host, ipc_port = '127.0.0.1', 26668
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.2)
                    s.connect((ipc_host, ipc_port))
                    s.sendall(f"CODE|{code}|resample=d".encode('utf-8'))
                print("✅ Socket: 联动指令已送达")
            except: pass
        
        # Socket 其实也很快，但为了绝对不卡顿，也可以扔进后台
        import threading
        threading.Thread(target=send_socket, daemon=True).start()

        # --- 🐢 [SLOW PATH] 异步跳转部分 ---
        
        def slow_tdx_link():
            try:
                try: from stock_standalone.JohnsonUtil.stock_sender import StockSender
                except ImportError: from JohnsonUtil.stock_sender import StockSender
                
                class DummyVar:
                    def get(self): return True
                
                # 实例化和同步发送 (此过程涉及 Win32 窗口搜索，耗时 100-300ms)
                sender = StockSender(tdx_var=DummyVar(), ths_var=DummyVar(), dfcf_var=DummyVar())
                sender.send(code)
                print(f"✅ TDX: 异步跳转完成")
            except Exception as e:
                print(f"⚠️ TDX: 异步跳转失败: {e}")

        # 使用线程执行耗时的 Win32 操作，避免阻塞 UI
        threading.Thread(target=slow_tdx_link, daemon=True).start()
        print("🚀 联动任务已全部分发")

def show_chart_with_signals(df, signals=None, title="Stock Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, existing_win=None, refresh_func=None, skip_focus=False, max_signals=20, max_vlines=12, max_hlines=5):
    existing_instance = QApplication.instance()
    app = existing_instance or QApplication(sys.argv)
    is_new_app = (existing_instance is None)
    
    win = None
    if existing_win is not None and hasattr(existing_win, 'update_plot') and existing_win.isVisible():
        try:
            existing_win.update_plot(df, signals, title, avg_series, time_labels, use_line, extra_lines)
            if not skip_focus:
                existing_win.raise_()
                existing_win.activateWindow()
            win = existing_win
        except Exception as e:
            print(f"Reuse failed: {e}")
            
    if win is None:
        win = StandaloneKlineChart(df, signals, title, avg_series, time_labels, use_line, extra_lines, refresh_func=refresh_func, max_signals=max_signals, max_vlines=max_vlines, max_hlines=max_hlines)
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
