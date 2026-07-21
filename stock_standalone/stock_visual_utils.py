from logger_utils import LoggerFactory
import sys
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QLabel, QDialog, QTextEdit
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

import socket
import struct
import pickle
import threading
import logging
import collections
import time

logger = LoggerFactory.getLogger(__name__)

class IPCSocketClient:
    """
    [Industrial Standard] 持久化非阻塞 IPC 客户端。
    采用“单写线程 + 循环缓冲区 + 自动重连”模型，确保调用方永不阻塞。
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(IPCSocketClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, host='127.0.0.1', port=26668):
        if hasattr(self, '_initialized'): return
        self.host = host
        self.port = port
        self.sock = None
        self.lock = threading.Lock()
        
        # 核心队列：使用 deque(maxlen) 实现“丢弃旧消息”策略
        self.queue = collections.deque(maxlen=200)
        self.stop_event = threading.Event()
        self.task_event = threading.Event()
        self.worker_thread = None
        
        self._initialized = True

    def _start_worker_if_needed(self):
        """确保后台写线程正在运行"""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            with self.lock:
                if self.worker_thread is None or not self.worker_thread.is_alive():
                    self.stop_event.clear()
                    self.worker_thread = threading.Thread(
                        target=self._sender_loop, 
                        name="IPCSocketSender",
                        daemon=True
                    )
                    self.worker_thread.start()
                    logger.info("[IPC Client] Sender thread started.")

    def enqueue_command(self, cmd: str):
        """非阻塞入队指令 (O(1) 立即返回)"""
        self._start_worker_if_needed()
        self.queue.append(('CMD', cmd))
        self.task_event.set()

    def enqueue_data(self, msg_type: str, data_obj: any):
        """非阻塞入队数据 (O(1) 立即返回)"""
        self._start_worker_if_needed()
        self.queue.append(('DATA', msg_type, data_obj))
        self.task_event.set()

    def _connect(self):
        """内部重连逻辑"""
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2.0)
            self.sock.connect((self.host, self.port))
            # self.sock.setblocking(False) # 也可以考虑使用非阻塞模式 send
            return True
        except Exception:
            self.sock = None
            return False

    def _sender_loop(self):
        """后台单写线程循环"""
        while not self.stop_event.is_set():
            if not self.queue:
                self.task_event.wait(timeout=1.0) # ⚡ [PERF] 消除 busy loop (time.sleep)
                self.task_event.clear()
                continue
            
            # 1. 尝试连接可视化器
            if not self._connect():
                time.sleep(1.0) # 连接失败时等待重试，不空转
                continue

            # 2. 取出一个任务 (LATEST FIRST 策略可通过 deque.pop() 实现，这里用 popleft 顺序执行)
            # 如果队列积压太严重，也可以在这里执行合并/去重逻辑
            try:
                task = self.queue.popleft()
            except IndexError:
                continue

            # 3. 执行发送
            try:
                if task[0] == 'CMD':
                    cmd_str = task[1]
                    if not cmd_str.startswith(("CODE|", "TIME|", "SIGN|")):
                        cmd_str = f"CODE|{cmd_str}"
                    # 🚀 [FIX] 强制追加换行符，解决 TCP 粘包导致的 JSON 解析 Extra data 错误
                    full_cmd = f"{cmd_str}\n"
                    self.sock.sendall(full_cmd.encode('utf-8'))
                
                elif task[0] == 'DATA':
                    msg_type, data_obj = task[1], task[2]
                    payload = pickle.dumps((msg_type, data_obj))
                    header = b"DATA" + struct.pack("!I", len(payload))
                    self.sock.sendall(header + payload)
                
            except (socket.error, ConnectionError) as e:
                logger.debug(f"[IPC Client] Send failed, reconnecting next loop: {e}")
                if self.sock:
                    try: self.sock.close()
                    except: pass
                    self.sock = None
                # 发送失败的任务重新放回队列头部（可选，如果数据过期可以不接回）
                # self.queue.appendleft(task) 

    def close(self):
        """关闭客户端"""
        self.stop_event.set()
        with self.lock:
            if self.sock:
                try: self.sock.close()
                except: pass
                self.sock = None

# 全局单例
ipc_client = IPCSocketClient()

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

    def update_signals(self, signals, is_compact=False, concise=True):
        self.clear()
        if not signals:
            return
        
        # [NEW] 强制精简模式：如果外部指定为 concise，则忽略窗口宽度判定
        is_compact = is_compact or concise

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
                # [NEW] 优先取 symbol_override（支持回测 B/S 标记）
                symbol = getattr(sig, 'symbol_override', None) or getattr(sig, 'symbol', 'o')
                if symbol not in ('B', 'S'):
                    if symbol == 'o' or symbol == '🎯': 
                        if "🔥" in reason or "趋势加速" in reason: symbol = "🔥"
                        elif "🚀" in reason or "强势结构" in reason: symbol = "🚀"
                        elif "🎯" in reason or "买入" in reason: symbol = "🎯"
                color = getattr(sig, 'color', (255, 255, 0))
                size = getattr(sig, 'size', 12)
                sig_type_str = str(getattr(sig, 'signal_type', '')).upper()
            
            is_emoji = symbol in ('🎯', '🚀', '🔥', 'B', 'S')
            xs.append(x_pos)
            ys.append(y_pos)
            brushes.append(pg.mkBrush(color))
            symbols.append('o' if is_emoji else symbol)
            sizes.append(size)
            
            is_buy = any(kw in sig_type_str for kw in ["BUY", "FOLLOW", "买入", "加仓"]) and "EXIT" not in sig_type_str
            label_color = QColor(255, 120, 120) if is_buy else QColor(120, 255, 120)
            
            # [FIX] 使用较大幅度的 anchor 来模拟固定像素偏移的效果，避免不同版本兼容性
            if is_buy:
                anchor_val = (0.5, -0.5) 
            else:
                anchor_val = (0.5, 1.5)

            debug_info = getattr(sig, 'debug_info', {}) if not isinstance(sig, dict) else sig.get('debug_info', {})
            score_text = ""
            if is_buy and 'buy_score' in debug_info:
                score_text = f" <span style='font-size: 8pt; color: #FFFF00; font-weight: bold;'>({debug_info['buy_score']})</span>"
            elif not is_buy and 'sell_score' in debug_info:
                score_text = f" <span style='font-size: 8pt; color: #FFFF00; font-weight: bold;'>({debug_info['sell_score']})</span>"
            
            action_name = "买" if is_buy else "卖"
            if is_compact:
                reason_text = f" | {action_name}"
                score_text = "" # [REFINED] 精简模式彻底隐藏分数，仅保留买卖
            else:
                if reason:
                    # [REFINED] 常用词汇精简，去除冗余买卖字眼（因为 action_name 已包含）
                    reason_clean = reason.replace("强势结构", "强势") \
                                         .replace("均线上-创多日高-", "") \
                                         .replace("诱空转多-", "") \
                                         .replace("趋势加速", "加速") \
                                         .replace("冠军核心回踩", "回踩") \
                                         .replace("突破回踩", "回踩") \
                                         .replace("分时新高", "新高") \
                                         .replace("买入", "").replace("卖出", "").replace("加仓", "").replace("减仓", "") \
                                         .replace(".", "").replace("(", "").replace(")", "").strip()
                    if is_emoji:
                        reason_clean = reason_clean.replace(symbol, "").strip()
                    
                    # 极简模式：限制 8 个字符
                    max_chars = 8 
                    if len(reason_clean) > max_chars:
                        # reason_final = reason_clean[:max_chars] + ".."
                        reason_final = reason_clean[:max_chars]
                        
                    else:
                        reason_final = reason_clean

                    if is_emoji:
                        reason_text = f" | {symbol} {action_name}: {reason_final}" if reason_final else f" | {symbol} {action_name}"
                    else:
                        reason_text = f" | {action_name}: {reason_final}" if reason_final else f" | {action_name}"
                else:
                    reason_text = f" | {action_name}"

            bg_brush = pg.mkBrush(20, 20, 20, 220)
            border_pen = pg.mkPen(label_color, width=1)
            text = pg.TextItem(anchor=anchor_val, fill=bg_brush, border=border_pen)
            
            weight = "font-weight: bold;" if not is_buy else ""
            text.setHtml(f'<div style="color: {label_color.name()}; font-size: 9pt; {weight}; padding: 2px;">{y_pos:.2f}{score_text}{reason_text}</div>')
            text.setPos(x_pos, y_pos)
            self.plot_item.addItem(text)
            self.text_items.append(text)
            
            if is_emoji:
                emoji = pg.TextItem(symbol, anchor=(0.5, 0.5))
                color_name = label_color.name()
                emoji.setHtml(f'<div style="font-size: 16pt; color: {color_name}; font-weight: bold;">{symbol}</div>')
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
class BacktestResultDialog(QDialog, WindowMixin):
    """
    分时信号回测结果弹窗。
    支持：
    1. 窗口位置与大小的跨会话持久化保存与恢复 (load_window_position_qt / save_window_position_qt_visual)
    2. 非模态展示 (NonModal)，取消强行置顶，允许拖拽避开 SBC 等主分析窗口
    3. 5 秒倒计时自动关闭与倒计时显示，按钮手动点击立即关闭
    """
    def __init__(self, summary_text="", parent=None):
        super().__init__(parent)
        self.window_name = "backtest_result_dialog"
        self.setWindowTitle("⏱️ 分时信号回测结果")

        # 1. 窗口 Flags：非模态、不抢焦点、不强制置顶
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags &= ~Qt.WindowType.Tool
        flags |= Qt.WindowType.Window
        flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setWindowModality(Qt.WindowModality.NonModal)

        # 2. 整体深色主题风格
        self.setStyleSheet("""
            QDialog {
                background-color: #161823;
                color: #e2e2e5;
            }
            QTextEdit {
                background-color: #0f1017;
                color: #00ff88;
                border: 1px solid #2e2e38;
                font-family: Consolas, "Courier New", monospace;
                font-size: 9.5pt;
                padding: 6px;
            }
            QPushButton {
                background-color: #2c2d3a;
                color: #ffffff;
                border: 1px solid #454659;
                border-radius: 4px;
                padding: 4px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b3c4f;
                border-color: #00ff88;
            }
        """)

        # 3. 布局设置
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 文本框展示明细
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(summary_text)
        layout.addWidget(self.text_edit)

        # 底部控制条
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.remaining_seconds = 5
        self.btn_close = QPushButton(f"关闭 ({self.remaining_seconds}s)")
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # 4. 加载持久化位置（默认 450 x 300）
        self.load_window_position_qt(self, self.window_name, default_width=450, default_height=300)

        # 5. 5 秒自动关闭倒计时
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_timer_tick)
        self.timer.start()

    def _on_timer_tick(self):
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.timer.stop()
            self.close()
        else:
            self.btn_close.setText(f"关闭 ({self.remaining_seconds}s)")

    def closeEvent(self, event):
        if hasattr(self, 'timer') and self.timer:
            self.timer.stop()
        self.save_window_position_qt_visual(self, self.window_name)
        super().closeEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.save_window_position_qt_visual(self, self.window_name)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.save_window_position_qt_visual(self, self.window_name)


class StandaloneKlineChart(QMainWindow, WindowMixin):
    """Simple chart window for visualization."""
    def __init__(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, refresh_func=None, max_signals=20, max_vlines=12, max_hlines=5, concise=True):
        super().__init__()
        self.concise = concise
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
        
        # [NEW] Backtest button
        self.btn_backtest = QPushButton("分时回测")
        self.btn_backtest.setFixedWidth(80)
        self.btn_backtest.setStyleSheet("background-color: #2b5c8f; color: white; border: 1px solid #3d78b8; font-weight: bold;")
        self.btn_backtest.clicked.connect(self._on_backtest_clicked)
        btn_layout.addWidget(self.btn_backtest)
        
        # [NEW] Status label for refresh time
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #888; font-size: 10px; margin-left: 10px;")
        btn_layout.addWidget(self.lbl_status)
        
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
                
            self.refresh_interval = duration_sleep_time
            self.refresh_timer = QTimer(self)
            self.refresh_timer.timeout.connect(self._on_refresh_timer)
            # [MODIFIED] 增加随机偏移量 (Jitter)，防止多个 SBC 窗口在同一毫秒发起计算竞争
            import random
            jitter_ms = random.randint(-1500, 1500)
            interval_ms = max(3000, int(duration_sleep_time * 1000) + jitter_ms)
            self.refresh_timer.start(interval_ms)
        
        # [NEW] 记忆精简模式
        self.concise = concise
        
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
                        self.update_plot(df, sig, ttl, avg, lbl, uline, ext, concise=self.concise)
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

    def _on_backtest_clicked(self):
        """
        [NEW] 针对当前个股分时数据执行盘中策略回测，并绘制买卖点 B, S
        """
        import re
        title = self.windowTitle()
        match = re.search(r'(?:\[|\b)(\d{6})(?:\]|\b)', title)
        if not match:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", "未在窗口标题中找到有效的6位股票代码！")
            return
        code = match.group(1)
        
        if self.df_ref is None or self.df_ref.empty:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "无数据", "当前窗口内无有效的分时行情数据！")
            return
            
        # 1. 确定日期
        target_date = None
        if isinstance(self.df_ref.index, pd.DatetimeIndex) and len(self.df_ref) > 0:
            target_date = self.df_ref.index[0].strftime('%Y-%m-%d')
        
        # 2. 如果 df_ref 的 index 不是 DatetimeIndex，尝试从 time_labels_ref 中提取
        if not target_date or not isinstance(self.df_ref.index, pd.DatetimeIndex):
            try:
                try:
                    from JSONData import tdx_data_Day as tdd
                except ImportError:
                    from stock_standalone.JSONData import tdx_data_Day as tdd
                df_daily = tdd.get_tdx_append_now_df_api(code)
                if df_daily is not None and not df_daily.empty:
                    target_date = str(df_daily.index[-1])[:10]
            except Exception:
                pass
                
            if not target_date:
                target_date = datetime.now().strftime('%Y-%m-%d')
                
            if self.time_labels_ref:
                try:
                    dts = []
                    for tl in self.time_labels_ref:
                        if " " in tl:
                            parts = tl.split()
                            dts.append(pd.to_datetime(f"{target_date[:8]}{parts[0]} {parts[1]}"))
                        else:
                            dts.append(pd.to_datetime(f"{target_date} {tl}"))
                    self.df_ref.index = dts
                    target_date = self.df_ref.index[0].strftime('%Y-%m-%d')
                except Exception as e:
                    print(f"重构 DatetimeIndex 失败: {e}")
                    
        if not target_date:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "日期缺失", "无法确定该分时行情对应的日期！")
            return
            
        print(f"🎬 开始针对 {code} 进行 {target_date} 分时信号回测...")
        
        # 3. 加载日线数据（窗口级缓存，避免每次点击重读 HDF5）
        cached = getattr(self, '_bt_daily_cache', None)
        if cached and cached[0] == code:
            df_daily = cached[1]
            print(f"  [BT] 复用日线缓存 {code} ({len(df_daily)} 行)")
        else:
            try:
                try:
                    from JSONData import tdx_data_Day as tdd
                except ImportError:
                    from stock_standalone.JSONData import tdx_data_Day as tdd
                df_daily = tdd.get_tdx_append_now_df_api(code)
                if df_daily is None or df_daily.empty:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.critical(self, "错误", f"加载股票 {code} 的日K线数据失败，无法进行回测！")
                    return
                df_daily = df_daily.sort_index()
                df_daily.index = [str(x)[:10] for x in df_daily.index]
                self._bt_daily_cache = (code, df_daily)
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "错误", f"加载日K数据异常: {e}")
                return

            
        if target_date not in df_daily.index:
            print(f"Warning: {target_date} not in daily index. Using latest date in database instead.")
            target_date = df_daily.index[-1]
            
        idx_loc = df_daily.index.get_loc(target_date)
        if idx_loc < 2:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", "历史日线数据不足（少于 2 日），无法计算前置基准！")
            return
            
        curr_daily = df_daily.iloc[idx_loc].to_dict()
        prev_daily = df_daily.iloc[idx_loc - 1].to_dict()
        prev2_daily = df_daily.iloc[idx_loc - 2].to_dict()
        
        # 4. 计算基准参考指标
        last_close = float(prev_daily["close"])
        nclose2d = float(prev2_daily.get("amount", 0) / prev2_daily.get("vol", 1.0)) if prev2_daily.get("vol", 0) > 0 else float(prev2_daily["close"])
        last_nclose = float(prev_daily.get("amount", 0) / prev_daily.get("vol", 1.0)) if prev_daily.get("vol", 0) > 0 else float(prev_daily["close"])
        
        if last_nclose > last_close * 1.5 or last_nclose < last_close * 0.5:
            last_nclose = last_close
        if nclose2d > last_close * 1.5 or nclose2d < last_close * 0.5:
            nclose2d = last_close
            
        lastv1d = float(prev_daily.get("vol", 0))
        if lastv1d <= 0:
            lastv1d = 1.0
            
        # 5. 重构分时 Tick 序列（volume 保持增量，每日在循环内独立 cumsum）
        df_ticks = pd.DataFrame({
            'ticktime': self.df_ref.index,
            'close':  self.df_ref['close'].values,
            'open':   self.df_ref['open'].values  if 'open'  in self.df_ref.columns else self.df_ref['close'].values,
            'high':   self.df_ref['high'].values  if 'high'  in self.df_ref.columns else self.df_ref['close'].values,
            'low':    self.df_ref['low'].values   if 'low'   in self.df_ref.columns else self.df_ref['close'].values,
            'volume': self.df_ref['volume'].values.clip(0),  # 增量，非 cumsum
        })
        
        # 6. 初始化决策引擎 + 依赖导入（移至循环外）
        try:
            from intraday_decision_engine import IntradayDecisionEngine
        except ImportError:
            from stock_standalone.intraday_decision_engine import IntradayDecisionEngine
        try:
            from JohnsonUtil import commonTips as cct
        except ImportError:
            from stock_standalone.JohnsonUtil import commonTips as cct
            
        # SBC 回测场景：门槛降至 0.30，覆盖多日震荡企稳 + 均线加速启动结构
        engine = IntradayDecisionEngine(buy_threshold=0.30, stop_loss_pct=0.03, take_profit_pct=0.08)

        import datetime as dt
        from contextlib import contextmanager

        class MockDateTime(dt.datetime):
            _mock_now = dt.datetime.now()
            @classmethod
            def now(cls, tz=None):
                return cls._mock_now

        @contextmanager
        def _patch_dt(module, attr, replacement):
            """Nuitka 兼容的轻量属性替换，等价于 unittest.mock.patch。"""
            original = getattr(module, attr, None)
            setattr(module, attr, replacement)
            try:
                yield
            finally:
                if original is not None:
                    setattr(module, attr, original)

        cost_price   = 0.0
        buy_date_str = ""
        holding      = False
        backtest_signals = []

        try:
            from signal_types import SignalPoint, SignalType
        except ImportError:
            from stock_standalone.signal_types import SignalPoint, SignalType

        # --- 7. 按日分组 Replay：每日独立基准，彻底解决多日图基准错位问题 ---
        df_ticks['_date'] = pd.to_datetime(df_ticks['ticktime']).dt.strftime('%Y-%m-%d')
        dates_in_data = df_ticks['_date'].unique().tolist()
        print(f"  [BT] 共 {len(dates_in_data)} 个交易日: {dates_in_data}")

        bar_offset = 0

        for day_str in dates_in_data:
            day_ticks_all = df_ticks[df_ticks['_date'] == day_str]

            if day_str not in df_daily.index:
                bar_offset += len(day_ticks_all)
                print(f"  [BT] {day_str} 不在日线索引，跳过")
                continue

            day_idx = df_daily.index.get_loc(day_str)
            if day_idx < 1:
                bar_offset += len(day_ticks_all)
                continue

            d_curr  = df_daily.iloc[day_idx].to_dict()
            d_prev  = df_daily.iloc[day_idx - 1].to_dict()
            d_prev2 = df_daily.iloc[max(0, day_idx - 2)].to_dict()

            day_last_close  = float(d_prev["close"])
            day_last_nclose = (float(d_prev.get("amount", 0)) / float(d_prev.get("vol", 1.0))
                               if float(d_prev.get("vol", 0)) > 0 else day_last_close)
            day_nclose2d    = (float(d_prev2.get("amount", 0)) / float(d_prev2.get("vol", 1.0))
                               if float(d_prev2.get("vol", 0)) > 0 else day_last_close)
            if not (day_last_close * 0.5 < day_last_nclose < day_last_close * 1.5):
                day_last_nclose = day_last_close
            if not (day_last_close * 0.5 < day_nclose2d < day_last_close * 1.5):
                day_nclose2d = day_last_close
            day_lastv1d = max(float(d_prev.get("vol", 1.0)), 1.0)

            # 每日重置日内状态
            day_cum_amount = 0.0
            day_last_vol   = 0.0
            day_highest    = day_last_close
            day_lowest     = day_last_close

            # volume 列已是增量，直接在当日内 cumsum → 当日累积成交量
            day_ticks = day_ticks_all.copy()
            day_ticks['volume'] = day_ticks['volume'].clip(lower=0).cumsum().values

            print(f"  [BT] {day_str} last_close={day_last_close:.2f} ticks={len(day_ticks)}")

            for local_i, (abs_i, tick) in enumerate(day_ticks.iterrows()):
                global_bar = bar_offset + local_i
                tick_time  = tick['ticktime']
                price      = float(tick['close'])
                curr_vol   = float(tick['volume'])

                vol_increment   = curr_vol - day_last_vol if day_last_vol > 0 else curr_vol
                day_last_vol    = curr_vol
                day_cum_amount += price * vol_increment
                running_nclose  = day_cum_amount / curr_vol if curr_vol > 0 else price

                try:
                    time_ratio = cct.get_work_time_ratio_sbc(now_time=tick_time)
                except Exception:
                    time_ratio = 0.5
                if time_ratio <= 0:
                    time_ratio = 0.001
                vol_ratio = curr_vol / (day_lastv1d * time_ratio)

                tick_high = float(tick.get('high', price))
                tick_low  = float(tick.get('low',  price))
                if tick_high > day_highest: day_highest = tick_high
                if tick_low  < day_lowest:  day_lowest  = tick_low

                snapshot = {
                    "code":          code,
                    "name":          d_curr.get("name", ""),
                    "last_close":    day_last_close,
                    "lastp1d":       day_last_close,
                    "nclose":        day_last_nclose,
                    "last_nclose":   day_last_nclose,
                    "nclose2d":      day_nclose2d,
                    "highest_today": day_highest,
                    "lowest_today":  day_lowest,
                    "low10":  float(d_curr.get("low10", 0)),
                    "low60":  float(d_curr.get("low60", 0)),
                    "vol":    day_lastv1d,
                    "loss_streak": 0,
                    "day_df": df_daily.iloc[:day_idx + 1],
                    "cost_price": cost_price   if holding else 0.0,
                    "buy_date":   buy_date_str if holding else "",
                }

                row = d_curr.copy()
                row["code"]    = code
                row["name"]    = d_curr.get("name", "")
                row["trade"]   = price
                row["open"]    = float(tick.get("open", d_curr.get("open", price)))
                row["high"]    = tick_high
                row["low"]     = tick_low
                row["volume"]  = vol_ratio
                row["ratio"]   = vol_ratio
                row["nclose"]  = running_nclose
                row["percent"] = (price - day_last_close) / day_last_close * 100 if day_last_close > 0 else 0.0

                # T+1 规则限制：若持仓日期等于当前交易日，则当日锁定无法卖出
                is_t1_restricted = holding and (buy_date_str == day_str)
                eval_mode = "full" if (holding and not is_t1_restricted) else "buy_only"

                MockDateTime._mock_now = pd.Timestamp(tick_time).to_pydatetime()
                import intraday_decision_engine as _ide_mod
                with _patch_dt(_ide_mod.dt, 'datetime', MockDateTime):
                    res = engine.evaluate(row, snapshot, mode=eval_mode)

                action = res.get('action')
                score  = res.get('position', 0.0)

                # 显式风控保底：仅在非 T+1 限制（即次日及以后）时，若价格较成本跌幅 >= 3.0% 或崩塌，强行触发止损平仓
                is_stop_loss = False
                if holding and not is_t1_restricted and cost_price > 0 and price <= cost_price * 0.97:
                    is_stop_loss = True
                    if action not in ("卖出", "止损", "止盈"):
                        action = "止损"
                        res["reason"] = f"触及 3.0% 止损保护 (成本:{cost_price:.2f} -> 现价:{price:.2f})"

                if local_i < 2:
                    print(f"    [DBG] {day_str} {pd.Timestamp(tick_time).strftime('%H:%M')} "
                          f"price={price:.2f} pct={row['percent']:+.2f}% "
                          f"vol_ratio={vol_ratio:.2f} action={action} score={score:.2f}")

                if not holding and action == "买入":
                    holding      = True
                    cost_price   = price
                    buy_date_str = day_str
                    sig = SignalPoint(
                        code=code,
                        timestamp=pd.Timestamp(tick_time).strftime('%Y-%m-%d %H:%M:%S'),
                        bar_index=global_bar,
                        price=price,
                        signal_type=SignalType.BUY,
                        reason=res.get("reason", "分时回测买入"),
                        debug_info={"buy_score": score}
                    )
                    sig.symbol_override = "B"
                    sig.is_backtest = True
                    backtest_signals.append(sig)
                    print(f"  ✅ [B] {day_str} {pd.Timestamp(tick_time).strftime('%H:%M')} "
                          f"买入 {price:.2f} score={score:.2f} | {res.get('reason','')}")

                elif holding and not is_t1_restricted and (action in ("卖出", "止损", "止盈", "极速离场", "趋势崩塌", "强制清仓") or is_stop_loss):
                    holding      = False
                    pnl_pct      = (price - cost_price) / cost_price * 100 if cost_price > 0 else 0.0
                    cost_price   = 0.0
                    buy_date_str = ""
                    sig = SignalPoint(
                        code=code,
                        timestamp=pd.Timestamp(tick_time).strftime('%Y-%m-%d %H:%M:%S'),
                        bar_index=global_bar,
                        price=price,
                        signal_type=SignalType.SELL,
                        reason=res.get("reason", "分时回测卖出"),
                        debug_info={"sell_score": score}
                    )
                    sig.symbol_override = "S"
                    sig.is_backtest = True
                    backtest_signals.append(sig)
                    print(f"  🔻 [S] {day_str} {pd.Timestamp(tick_time).strftime('%H:%M')} "
                          f"卖出 {price:.2f} (盈亏: {pnl_pct:+.2f}%) | {res.get('reason','')}")

            bar_offset += len(day_ticks)


                    
        # 8. 合并并重新绘制
        # [KEY FIX] 过滤 is_kline=True（K线层投影信号，bar_index=日线序号/price=日收盘价）
        # 这类信号坐标系与分时图不兼容，画上去会错位到错误价格位置
        combined_signals = []
        if hasattr(self, 'signals_ref') and self.signals_ref:
            intraday_only = [
                s for s in self.signals_ref
                if not getattr(s, 'is_backtest', False)   # 去掉上次回测标记
                and not getattr(s, 'is_kline', False)     # 去掉 K线层投影
            ]
            combined_signals.extend(intraday_only)

        combined_signals.extend(backtest_signals)
        
        is_compact = self.width() < 800 or getattr(self, 'concise', False)
        if hasattr(self, 'overlay') and self.overlay:
            self.overlay.update_signals(combined_signals, is_compact=is_compact, concise=getattr(self, 'concise', False))
            
        # 9. 弹窗显示结果
        summary_lines = [
            f"股票代码: {code} ({curr_daily.get('name', 'Unknown')})",
            f"回测日期: {target_date}",
            f"回测信号总数: {len(backtest_signals)}",
        ]
        buys = [s for s in backtest_signals if s.symbol_override == "B"]
        sells = [s for s in backtest_signals if s.symbol_override == "S"]
        summary_lines.append(f"买点 (B) 数量: {len(buys)}")
        summary_lines.append(f"卖点 (S) 数量: {len(sells)}")
        
        trade_details = []
        for b in buys:
            matching_sells = [s for s in sells if s.bar_index > b.bar_index]
            if matching_sells:
                s = matching_sells[0]
                pnl = (s.price - b.price) / b.price * 100
                trade_details.append(f"  - 买入: {b.price:.2f} ({b.timestamp[11:19]}) -> 卖出: {s.price:.2f} ({s.timestamp[11:19]}) | 收益: {pnl:+.2f}%")
            else:
                trade_details.append(f"  - 买入: {b.price:.2f} ({b.timestamp[11:19]}) -> 收盘未平仓")
                
        if trade_details:
            summary_lines.append("\n模拟交易明细:")
            summary_lines.extend(trade_details)

        # 清理可能存在的旧弹窗
        if hasattr(self, '_backtest_dialog') and self._backtest_dialog is not None:
            try:
                self._backtest_dialog.close()
            except Exception:
                pass

        dialog = BacktestResultDialog(summary_text="\n".join(summary_lines), parent=self)
        self._backtest_dialog = dialog
        dialog.show()

    # --- 统一方法管理 (移除冗余重复定义) ---

    def update_plot(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, init=False, concise=None):
        self.df_ref = df
        self.signals_ref = list(signals) if signals else []
        self.time_labels_ref = time_labels
        self.use_line_ref = use_line
        self.extra_lines_ref = extra_lines
        if signals is not None and "SBC" not in title:
            title = f"SBC Pattern - {title}"
        self.setWindowTitle(title)
        
        # [NEW] 更新状态栏时间
        if hasattr(self, 'lbl_status'):
            now_str = datetime.now().strftime("%H:%M:%S")
            interval = getattr(self, 'refresh_interval', 0)
            if interval > 0:
                self.lbl_status.setText(f"🔄 {interval}s | {now_str}")
            else:
                self.lbl_status.setText(f"✅ {now_str}")
        
        # [REFINED] 精简模式判定逻辑
        if concise is not None:
            self.concise = concise
        is_compact = self.width() < 800 or getattr(self, 'concise', False)

        if not init and self.pw is not None:
            self.pw.clear()
            if hasattr(self, 'overlay') and self.overlay:
                self.overlay.text_items.clear()
            # if self.vbv:
            #     self.vbv.clear()
            
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

            # [NEW] Render Volume - Integrated into main plot to match sector_bidding_panel
            if 'volume' in df.columns:
                vol = df['volume'].values.astype(float)
                prices_close = df['close'].values
                prices_open = df['open'].values if 'open' in df.columns else prices_close
                
                if len(vol) > 0:
                    p_min, p_max = np.min(prices_close), np.max(prices_close)
                    v_max = np.percentile(vol, 99) if len(vol) > 10 else np.max(vol)
                    if v_max <= 0: v_max = 1
                    
                    # Scaling logic from sector_bidding_panel: occupy 20% of price range
                    price_range = (p_max - p_min) if p_max > p_min else p_max * 0.1
                    if price_range <= 0: price_range = 1.0
                    vol_scale = price_range * 0.2 / v_max
                    
                    brushes = []
                    pens = []
                    c_up = '#FF4444'
                    c_down = '#44CC44'
                    for i in range(len(prices_close)):
                        is_up = prices_close[i] >= prices_close[i-1] if i > 0 else prices_close[i] >= prices_open[i]
                        color = c_up if is_up else c_down
                        brushes.append(pg.mkBrush(color))
                        pens.append(pg.mkPen(color, width=0.5))
                    
                    v_x = np.arange(len(vol))
                    # Use a single BarGraphItem for performance (unlike bidding panel's loop)
                    v_bars = pg.BarGraphItem(x=v_x, height=vol * vol_scale, width=0.7, brushes=brushes, pens=pens)
                    # Positioned at bottom of price action
                    v_bars.setPos(0, p_min - price_range * 0.05) 
                    self.pw.addItem(v_bars)
                    
                    # Ensure Y range covers the bars
                    self.pw.setYRange(p_min - price_range * 0.3, p_max + price_range * 0.1, padding=0)
        
        if avg_series is not None:
            avg_x = np.arange(len(avg_series))
            avg_y = np.asarray(avg_series)
            self.pw.plot(avg_x, avg_y, pen=pg.mkPen(QColor(255, 255, 255, 180), width=1.5, style=Qt.PenStyle.DashLine), name="VWAP")
        
        if extra_lines:
            # [NEW] 绘制垂直参考线（如多日分割线）
            if isinstance(extra_lines, dict) and 'v_lines' in extra_lines:
                for vline in extra_lines['v_lines']:
                    try:
                        # 兼容 (pos, color, width, 'v') 或 (pos, color, width)
                        pos, color, width = vline[:3]
                        self.pw.addItem(pg.InfiniteLine(pos=pos, angle=90, pen=pg.mkPen(color, width=width)))
                    except Exception:
                        pass

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

        # [FIX] 分时图视图 (use_line=True)：只渲染分时结构信号，过滤掉 is_kline=True 的 K线层投影/历史日线信号
        # 规避日线序号(0,1,2..)和历史日收盘价被错误映射到分时 Tick 坐标系导致的错位阶梯标记
        if use_line and signals:
            valid_signals = []
            min_p = df['low'].min() * 0.8 if df is not None and 'low' in df.columns else (df['close'].min() * 0.8 if df is not None and 'close' in df.columns else 0)
            max_p = df['high'].max() * 1.2 if df is not None and 'high' in df.columns else (df['close'].max() * 1.2 if df is not None and 'close' in df.columns else 99999)
            
            # 建立 timestamp -> idx 映射
            time_to_idx = {}
            if df is not None and not df.empty:
                t_col = 'ticktime' if 'ticktime' in df.columns else ('time' if 'time' in df.columns else None)
                if t_col:
                    for idx_i, t_val in enumerate(df[t_col]):
                        ts_str = str(t_val)
                        time_to_idx[ts_str] = idx_i
                        if len(ts_str) >= 16: time_to_idx[ts_str[:16]] = idx_i
                        if len(ts_str) >= 19: time_to_idx[ts_str[11:19]] = idx_i
                        if len(ts_str) >= 16 and ' ' in ts_str: time_to_idx[ts_str.split(' ')[1][:5]] = idx_i

            for s in signals:
                if getattr(s, 'is_kline', False):
                    continue
                p = getattr(s, 'price', 0) if not isinstance(s, dict) else s.get('price', 0)
                if min_p <= p <= max_p or p == 0:
                    s_ts = str(getattr(s, 'timestamp', '')) if not isinstance(s, dict) else str(s.get('timestamp', ''))
                    matched = -1
                    if s_ts in time_to_idx: matched = time_to_idx[s_ts]
                    elif len(s_ts) >= 16 and s_ts[:16] in time_to_idx: matched = time_to_idx[s_ts[:16]]
                    elif len(s_ts) >= 19 and s_ts[11:19] in time_to_idx: matched = time_to_idx[s_ts[11:19]]
                    elif ' ' in s_ts and s_ts.split(' ')[1][:5] in time_to_idx: matched = time_to_idx[s_ts.split(' ')[1][:5]]

                    if matched != -1:
                        if isinstance(s, dict): s['bar_index'] = matched
                        else: s.bar_index = matched
                        
                    valid_signals.append(s)
            signals = valid_signals

        self.overlay = SignalOverlay(self.pw)
        if signals: self.overlay.update_signals(signals, is_compact=is_compact, concise=getattr(self, 'concise', False))
            
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
            # [FIX] 移除不支持的 tickTextAnchor 以修复崩溃。
            # 使用精简后的日期格式 (%d %H:%M) 配合适度边距。
            if total > 0:
                self.pw.setXRange(-total * 0.04, total * 1.02, padding=0)
            
        # Re-attach Crosshair
        # (df_ref / time_labels_ref already set at the top of update_plot)
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

def show_chart_with_signals(df, signals=None, title="Stock Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, existing_win=None, refresh_func=None, skip_focus=False, max_signals=20, max_vlines=12, max_hlines=5, concise=True):
    existing_instance = QApplication.instance()
    app = existing_instance or QApplication(sys.argv)
    is_new_app = (existing_instance is None)
    
    win = None
    if existing_win is not None and hasattr(existing_win, 'update_plot') and existing_win.isVisible():
        try:
            existing_win.update_plot(df, signals, title, avg_series, time_labels, use_line, extra_lines, concise=concise)
            if not skip_focus:
                existing_win.raise_()
                existing_win.activateWindow()
            win = existing_win
        except Exception as e:
            print(f"Reuse failed: {e}")
            
    if win is None:
        win = StandaloneKlineChart(df, signals, title, avg_series, time_labels, use_line, extra_lines, refresh_func=refresh_func, max_signals=max_signals, max_vlines=max_vlines, max_hlines=max_hlines, concise=concise)
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
