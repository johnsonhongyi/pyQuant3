import sys
import os
import pandas as pd
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QSplitter, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QBrush, QPen
from PyQt6.QtWidgets import QComboBox, QCheckBox, QHBoxLayout, QLabel, QToolBar
from PyQt6.QtGui import QAction, QActionGroup
import socket
import pickle
import struct
from JohnsonUtil import LoggerFactory
from JohnsonUtil.stock_sender import StockSender
# from JohnsonUtil import commonTips as cct
from JohnsonUtil.commonTips import timed_ctx,print_timing_summary
from JohnsonUtil import johnson_cons as ct
# Configuration
IPC_PORT = 26668
IPC_HOST = '127.0.0.1'
logger = LoggerFactory.getLogger()
# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from trading_logger import TradingLogger
    from JSONData import tdx_data_Day as tdd
    from JSONData import sina_data
    from tk_gui_modules.window_mixin import WindowMixin
    from dpi_utils import get_windows_dpi_scale_factor
except ImportError as e:
    print(f"Import Error: {e}. Please run this script from the stock_standalone directory.")
    sys.exit(1)

# Configuration for pyqtgraph
pg.setConfigOptions(antialias=True)
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data, theme='light'):
        super().__init__()
        self.data = data
        self.theme = theme
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
        self.picture = pg.QtGui.QPicture()
        p = pg.QtGui.QPainter(self.picture)
        w = 0.4

        for (t, open_, close, low, high) in self.data:
            if close >= open_:
                pen = self.up_pen
                brush = self.up_brush
            else:
                pen = self.down_pen
                brush = self.down_brush

            # wick
            p.setPen(self.wick_pen)
            p.drawLine(
                pg.QtCore.QPointF(t, low),
                pg.QtCore.QPointF(t, high)
            )

            # body
            p.setPen(pen)
            p.setBrush(brush)
            p.drawRect(
                pg.QtCore.QRectF(
                    t - w,
                    open_,
                    w * 2,
                    close - open_
                )
            )

        p.end()
    def setTheme(self, theme):
        if theme != self.theme:
            self.theme = theme
            self._gen_colors()
            self.generatePicture()
            self.update()

    # def generatePicture(self):
    #     self.picture = pg.QtGui.QPicture()
    #     p = pg.QtGui.QPainter(self.picture)
    #     w = 0.4
    #     for (t, open, close, min, max) in self.data:
    #         if open > close:
    #             p.setPen(pg.mkPen('g'))
    #             p.setBrush(pg.mkBrush('g'))
    #         else:
    #             p.setPen(pg.mkPen('r'))
    #             p.setBrush(pg.mkBrush('r'))
    #         p.drawLine(pg.QtCore.QPointF(t, min), pg.QtCore.QPointF(t, max))
    #         p.drawRect(pg.QtCore.QRectF(t - w, open, w * 2, close - open))
    #     p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return pg.QtCore.QRectF(self.picture.boundingRect())

def recv_exact(sock, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed before receiving full data")
        buf += chunk
    return buf

class CommandListenerThread(QThread):
    command_received = pyqtSignal(str)
    dataframe_received = pyqtSignal(object)  # For df_all updates

    def __init__(self, server_socket):
        super().__init__()
        self.server_socket = server_socket
        self.running = True

    def run(self):
        while self.running:
            try:
                client_socket, _ = self.server_socket.accept()
                client_socket.settimeout(3.0)

                # 先读前 4 个字节判断协议
                prefix = recv_exact(client_socket, 4)

                # -------- DATA 协议 --------
                if prefix == b"DATA":
                    try:
                        # 读取 4 字节长度
                        header = recv_exact(client_socket, 4)
                        size = struct.unpack("!I", header)[0]

                        # 读取完整 payload
                        payload = recv_exact(client_socket, size)

                        df = pickle.loads(payload)
                        self.dataframe_received.emit(df)

                    except Exception as e:
                        print(f"[IPC] Error receiving DATA: {e}")

                # -------- CODE / 文本协议 --------
                else:
                    # prefix 已经是文本的一部分
                    rest = client_socket.recv(4096)
                    text = (prefix + rest).decode("utf-8", errors="ignore").strip()

                    if text.startswith("CODE|"):
                        code = text[5:].strip()
                        if code:
                            self.command_received.emit(code)
                    else:
                        if text:
                            self.command_received.emit(text)

                client_socket.close()

            except Exception as e:
                print(f"[IPC] Listener Error: {e}")

    # def run(self):
    #     while self.running:
    #         try:
    #             client_socket, _ = self.server_socket.accept()
    #             # Receive raw bytes first
    #             raw_data = client_socket.recv(1024 * 1024)  # 1MB buffer
                
    #             try:
    #                 # Try to decode as text first
    #                 text_data = raw_data.decode('utf-8', errors='strict')
                    
    #                 if text_data.startswith("CODE|"):
    #                     code = text_data[5:].strip()
    #                     if code:
    #                         self.command_received.emit(code)
    #                 else:
    #                     # Legacy: plain code
    #                     if text_data.strip():
    #                         self.command_received.emit(text_data.strip())
    #             except UnicodeDecodeError:
    #                 # Binary data - likely pickled DataFrame
    #                 if raw_data.startswith(b"DATA|"):
    #                     try:
    #                         pickled_data = raw_data[5:]  # Remove "DATA|" prefix
    #                         df = pickle.loads(pickled_data)
    #                         self.dataframe_received.emit(df)
    #                     except Exception as e:
    #                         print(f"Error unpickling data: {e}")
                
    #             client_socket.close()
    #         except Exception as e:
    #             print(f"Listener Error: {e}")

from PyQt6.QtCore import QMutex, QThread, pyqtSignal, QMutexLocker

class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(object, object, object) # code, day_df, tick_df

    def __init__(self, code ,mutex_lock, resample='d'):
        super().__init__()
        self.code = code
        self.resample = resample
        self.mutex_lock = mutex_lock # 存储锁对象
        self._search_code = None
        self._resample = None

    def run(self):
            try:
                # 使用 QMutexLocker 自动管理锁定和解锁
                if self._search_code == self.code and self._resample == self.resample:
                    return  # 数据已经加载过，不重复
                with QMutexLocker(self.mutex_lock):
                    # 1. Fetch Daily Data (Historical)
                    # tdd.get_tdx_Exp_day_to_df 内部调用 HDF5 API，必须在锁内执行
                    with timed_ctx("get_tdx_Exp_day_to_df", warn_ms=800):
                       day_df = tdd.get_tdx_Exp_day_to_df(self.code, dl=ct.Resample_LABELS_Days[self.resample],resample=self.resample,fastohlc=True)

                    # 2. Fetch Realtime/Tick Data (Intraday)
                    # 假设此操作不涉及 HDF5，可以在锁外执行
                    with timed_ctx("get_real_time_tick", warn_ms=800):
                       tick_df = sina_data.Sina().get_real_time_tick(self.code)

                self._search_code = self.code
                self._resample = self.resample
                with timed_ctx("emit", warn_ms=800):
                       self.data_loaded.emit(self.code, day_df, tick_df)
            except Exception as e:
                print(f"Error loading data for {self.code}: {e}")
                # 确保即使发生错误，信号也能发出
                import traceback
                traceback.print_exc()
                self.data_loaded.emit(self.code, pd.DataFrame(), pd.DataFrame())

    # def run(self):
    #     try:
    #         # 1. Fetch Daily Data (Historical)
    #         with timed_ctx("get_tdx_Exp_day_to_df", warn_ms=800):
    #             day_df = tdd.get_tdx_Exp_day_to_df(self.code, dl=ct.Resample_LABELS_Days[self.resample],resample=self.resample,fastohlc=True) # Last 60 days
    #         # 2. Fetch Realtime/Tick Data (Intraday)
    #         # Use get_real_time_tick for specific code
    #         with timed_ctx("get_real_time_tick", warn_ms=800):
    #             tick_df = sina_data.Sina().get_real_time_tick(self.code)
    #         with timed_ctx("emit", warn_ms=800):
    #             self.data_loaded.emit(self.code, day_df, tick_df)
    #     except Exception as e:
    #         print(f"Error loading data for {self.code}: {e}")
    #         self.data_loaded.emit(self.code, pd.DataFrame(), pd.DataFrame())

class MainWindow(QMainWindow, WindowMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trade Signal Visualizer (Qt6 + PyQtGraph)")
        self.sender = StockSender(callback=None)
        # WindowMixin requirement: scale_factor
        self.scale_factor = get_windows_dpi_scale_factor()
        self.hdf5_mutex = QMutex() 

        self.resample = 'd'
        self.qt_theme = 'dark'  # 默认使用黑色主题
        self.show_bollinger = True
        self.tdx_enabled = False  # 默认开启
        
        # --- 1. 创建工具栏 ---
        self._init_toolbar()
        self._init_resample_toolbar()
        self._init_theme_selector()
        self._init_tdx()
        # Load Window Position (Qt specific method from Mixin)
        # Using a distinct window_id "TradeVisualizer"
        self.load_window_position_qt(self, "TradeVisualizer", default_width=600, default_height=850)
        
        # Initialize Logger to read signals
        self.logger = TradingLogger()
        self.current_code = None
        self.df_all = pd.DataFrame()  # Store real-time data from MonitorTK
        self.code_name_map = {}
        self.code_info_map = {}   # ⭐ 新增

        # Main Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # 1. Left Sidebar: Stock Table
        self.stock_table = QTableWidget()
        self.stock_table.setMaximumWidth(350)
        self.stock_table.setColumnCount(4)
        self.stock_table.setHorizontalHeaderLabels(['Code', 'Name', 'Rank', 'Percent'])
        self.stock_table.horizontalHeader().setStretchLastSection(True)
        self.stock_table.setSortingEnabled(True)

        # 设置表格列自适应
        self.stock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Code 列自适应内容
        # self.stock_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)          # Name 列占满剩余空间
        self.stock_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)          # Name 列占满剩余空间
        self.stock_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Rank 列自适应
        self.stock_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Percent 列自适应


        # 在 MainWindow.__init__ 中修改
        self.stock_table.cellClicked.connect(self.on_table_cell_clicked) # 保留点击
        self.stock_table.currentItemChanged.connect(self.on_current_item_changed) # 新增键盘支持

        self.stock_table.verticalHeader().setVisible(False)
        main_layout.addWidget(self.stock_table)

        # 2. Right Area: Splitter (Day K-Line + Intraday)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(right_splitter, 1) # Stretch factor 1

        # -- Top Chart: Day K-Line
        self.kline_widget = pg.GraphicsLayoutWidget()
        self.kline_plot = self.kline_widget.addPlot(title="Daily K-Line")
        self.kline_plot.showGrid(x=True, y=True)
        self.kline_plot.setLabel('bottom', 'Date Index')
        self.kline_plot.setLabel('left', 'Price')
        right_splitter.addWidget(self.kline_widget)

        # -- Bottom Chart: Intraday
        self.tick_widget = pg.GraphicsLayoutWidget()
        self.tick_plot = self.tick_widget.addPlot(title="Real-time / Intraday")
        self.tick_plot.showGrid(x=True, y=True)
        right_splitter.addWidget(self.tick_widget)
        
        # Set splitter sizes (70% top, 30% bottom)
        right_splitter.setSizes([500, 200])
        
        # Apply initial theme
        self.apply_qt_theme()

        # Load Stock List
        self.load_stock_list()

    def _init_toolbar(self):
        self.toolbar = QToolBar("Settings", self)
        self.toolbar.setObjectName("ResampleToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.toolbar.setStyleSheet("""
        QToolBar#ResampleToolbar QToolButton {
            padding: 4px 8px;
            margin: 2px;
        }

        QToolBar#ResampleToolbar QToolButton:checked {
            background-color: #ffd700;
            color: black;
            font-weight: bold;
            border-radius: 3px;
        }
        """)


    def _init_resample_toolbar(self):
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Resample:"))

        self.resample_group = QActionGroup(self)
        self.resample_group.setExclusive(True)

        self.resample_actions = {}

        for key, label in [('d', '1D'), ('3d', '3D'), ('w', '1W'), ('m', '1M')]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(key)

            if key == self.resample:
                act.setChecked(True)

            # 正确绑定：传递 key
            act.triggered.connect(lambda checked, k=key: self.on_resample_changed(k))
            # act.triggered.connect(self.on_resample_changed)

            self.resample_group.addAction(act)
            self.toolbar.addAction(act)

            self.resample_actions[key] = act

    def _init_tdx(self):
        """Initialize TDX / code link toggle"""
        self.tdx_cb = QCheckBox("Enable TDX Link")
        self.tdx_cb.setChecked(self.tdx_enabled)  # 默认联动
        self.tdx_cb.stateChanged.connect(self.on_tdx_toggled)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.tdx_cb)

    def on_tdx_toggled(self, state):
        """Enable or disable code sending via sender"""
        self.tdx_enabled = bool(state)
        logger.info(f'tdx_enabled: {self.tdx_enabled}')

    def _init_theme_selector(self):
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Theme:"))

        self.theme_cb = QComboBox()
        self.theme_cb.addItems(['light', 'dark'])
        self.theme_cb.setCurrentText(self.qt_theme)
        self.theme_cb.currentTextChanged.connect(self.on_theme_changed)

        self.toolbar.addWidget(self.theme_cb)

    def on_resample_changed(self, text):
        self.resample = text
        logger.info(f'self.current_code: {self.current_code} self.resample: {self.resample}')
        if self.current_code:
            self.load_stock_by_code(self.current_code)

    def on_theme_changed(self, text):
        self.qt_theme = text
        self.apply_qt_theme()

    def _apply_pg_theme_to_plot(self, plot):
        """Apply theme to a single plot"""
        # 获取 PlotItem 的 ViewBox
        vb = plot.getViewBox()

        # 背景颜色和边框颜色
        if self.qt_theme == 'dark':
            vb.setBackgroundColor('#1e1e1e')
            axis_color = '#cccccc'
            border_color = '#555555'  # 深灰色边框
            title_color = '#e6e6e6'   # 浅灰色标题
        else:
            vb.setBackgroundColor('w')
            axis_color = '#000000'
            border_color = '#cccccc'  # 浅灰色边框
            title_color = '#000000'   # 黑色标题

        # 设置边框颜色
        vb.setBorder(pg.mkPen(border_color, width=1))
        
        # 设置坐标轴颜色（包括所有四个边）
        for ax_name in ('left', 'bottom', 'right', 'top'):
            ax = plot.getAxis(ax_name)
            if ax is not None:
                ax.setPen(pg.mkPen(axis_color, width=1))
                ax.setTextPen(pg.mkPen(axis_color))
        
        # 设置标题颜色 - 使用正确的方法
        if hasattr(plot, 'titleLabel'):
            plot.titleLabel.item.setDefaultTextColor(QColor(title_color))

        # 网格
        plot.showGrid(x=True, y=True, alpha=0.3)
    
    def _apply_widget_theme(self, widget):
        """Apply theme to GraphicsLayoutWidget"""
        if self.qt_theme == 'dark':
            widget.setBackground('#1e1e1e')
            # 设置widget边框
            widget.setStyleSheet("""
                QGraphicsView {
                    border: 1px solid #555555;
                    background-color: #1e1e1e;
                }
            """)
        else:
            widget.setBackground('w')
            widget.setStyleSheet("""
                QGraphicsView {
                    border: 1px solid #cccccc;
                    background-color: white;
                }
            """)



    def apply_qt_theme(self):
        """Apply Qt theme / color scheme"""
        # if self.qt_theme == 'dark':
        #     self.setStyleSheet("""
        #         QWidget { background-color: #2b2b2b; color: #f0f0f0; }
        #         QTableWidget { gridline-color: #555555; }
        #     """)
        #     pg.setConfigOption('background', 'k')
        #     pg.setConfigOption('foreground', 'w')
        if self.qt_theme == 'dark':
            self.setStyleSheet("""
                QWidget {
                    background-color: #2b2b2b;
                    color: #e6e6e6;
                }
                QTableWidget {
                    background-color: #2b2b2b;
                    gridline-color: #444444;
                }
                QHeaderView::section {
                    background-color: #3a3a3a;
                    color: #f0f0f0;
                    padding: 4px;
                    border: 1px solid #555555;
                }
                QTableWidget::item:selected {
                    background-color: #505050;
                }
            """)
            pg.setConfigOption('background', 'k')
            pg.setConfigOption('foreground', 'w')

        else:
            # 默认 light
            self.setStyleSheet("")
            pg.setConfigOption('background', 'w')
            pg.setConfigOption('foreground', 'k')
        
        # 应用到 GraphicsLayoutWidget
        self._apply_widget_theme(self.kline_widget)
        self._apply_widget_theme(self.tick_widget)
        
        # 调用统一函数设置 pg 主题
        self._apply_pg_theme_to_plot(self.kline_plot)
        self._apply_pg_theme_to_plot(self.tick_plot)
        
        # 如果有 volume_plot，也应用主题
        if hasattr(self, 'volume_plot'):
            self._apply_pg_theme_to_plot(self.volume_plot)
        
        # 重新渲染当前股票（如果有）以更新蜡烛图颜色
        if self.current_code:
            self.load_stock_by_code(self.current_code)

    def closeEvent(self, event):
        """Save window position on close"""
        self.save_window_position_qt(self, "TradeVisualizer")
        super().closeEvent(event)

    def load_stock_list(self):
        """Load stocks from df_all if available, otherwise from signal history"""
        if not self.df_all.empty:
            self.update_stock_table(self.df_all)
        else:
            # Fallback to signal history
            df = self.logger.get_signal_history_df()
            if not df.empty and 'code' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values(by='date', ascending=False)
                unique_stocks = df[['code', 'name']].drop_duplicates()
                # Create a minimal df_all structure
                fallback_df = unique_stocks.copy()
                fallback_df['Rank'] = 0
                fallback_df['percent'] = 0.0
                self.update_stock_table(fallback_df)
    
    def update_stock_table(self, df):
        """Update table with df_all data"""
        self.stock_table.setSortingEnabled(False)
        self.stock_table.setRowCount(0)
        
        if df.empty:
            return
        
        # Filter required columns
        required_cols = ['code', 'name']
        optional_cols = ['Rank', 'percent']
        
        for col in required_cols:
            if col not in df.columns:
                return
        
        # Add rows
        for idx, row in df.iterrows():
            row_position = self.stock_table.rowCount()
            self.stock_table.insertRow(row_position)
            
            stock_code = str(row.get('code', ''))
            stock_name = str(row.get('name', ''))

            # Code
            code_item = QTableWidgetItem(stock_code)
            code_item.setData(Qt.ItemDataRole.UserRole, row.get('code', ''))
            self.stock_table.setItem(row_position, 0, code_item)
            
            # Name
            name_item = QTableWidgetItem(stock_name)
            self.stock_table.setItem(row_position, 1, name_item)
            
            self.code_name_map[stock_code] = stock_name
            self.code_info_map[stock_code] = {
                    "name": stock_name,
                    "rank": row.get('Rank'),
                    "percent": row.get('percent')
                }
            # Rank
            rank_val = row.get('Rank', 0)
            rank_item = QTableWidgetItem()
            rank_item.setData(Qt.ItemDataRole.DisplayRole, int(rank_val) if pd.notnull(rank_val) else 0)
            self.stock_table.setItem(row_position, 2, rank_item)
            
            # Percent
            pct_val = row.get('percent', 0.0)
            pct_item = QTableWidgetItem()
            pct_item.setData(Qt.ItemDataRole.DisplayRole, float(pct_val) if pd.notnull(pct_val) else 0.0)
            # Color code percent
            if pd.notnull(pct_val) and float(pct_val) > 0:
                pct_item.setForeground(QColor('red'))
            elif pd.notnull(pct_val) and float(pct_val) < 0:
                pct_item.setForeground(QColor('green'))
            self.stock_table.setItem(row_position, 3, pct_item)
        
        self.stock_table.setSortingEnabled(True)
        self.stock_table.resizeColumnsToContents()

    def on_table_cell_clicked(self, row, column):
        code_item = self.stock_table.item(row, 0)
        if code_item:
            code = code_item.data(Qt.ItemDataRole.UserRole)
            if code:
                if code != self.current_code:  # 只有 code 不同才加载
                    self.load_stock_by_code(code)
                    if self.tdx_enabled:
                        try:
                            self.sender.send(code)
                        except Exception as e:
                            print(f"Error sending stock code: {e}")

    def on_current_item_changed(self, current, previous):
        """处理键盘上下键引起的行切换"""
        if current:
            row = current.row()
            # 始终获取第 0 列（Code列）的 item
            code_item = self.stock_table.item(row, 0)
            if code_item:
                code = code_item.data(Qt.ItemDataRole.UserRole)
                # 只有当代码发生变化时才加载，防止重复触发
                if code and code != self.current_code:
                    self.load_stock_by_code(code)
                    if self.tdx_enabled:
                        try:
                            self.sender.send(code)
                        except Exception as e:
                            print(f"Error sending stock code: {e}")

    def update_df_all(self, df):
        """Update df_all and refresh table"""
        self.df_all = df.copy() if not df.empty else pd.DataFrame()
        self.update_stock_table(self.df_all)

    def load_stock_by_code(self, code):
        self.current_code = code
        self.kline_plot.setTitle(f"Loading {code}...")
        # Start Thread
        with timed_ctx("DataLoaderThread", warn_ms=800):
            logger.info(f'code: {code} self.resample: {self.resample}')
            self.loader = DataLoaderThread(code,self.hdf5_mutex,resample=self.resample)
        with timed_ctx("data_loaded", warn_ms=800):
            self.loader.data_loaded.connect(self.render_charts)
        with timed_ctx("start", warn_ms=800):
            self.loader.start()
        if logger.level == LoggerFactory.DEBUG:
            print_timing_summary(top_n=6)

    def render_charts(self, code, day_df, tick_df):
        if day_df.empty:
            self.kline_plot.setTitle(f"{code} - No Data")
            return

        self.kline_plot.clear()
        self.tick_plot.clear()
        # # self.kline_plot.setTitle(f"{code} Daily K-Line")
        # name = self.code_name_map.get(str(code), "")
        # title = f"{code} {name} Daily K-Line" if name else f"{code} Daily K-Line"
        # self.kline_plot.setTitle(title)

        info = self.code_info_map.get(code, {})

        name = info.get("name", "")
        rank = info.get("rank", None)
        percent = info.get("percent", None)

        title_parts = [code]
        if name:
            title_parts.append(name)

        if rank is not None:
            title_parts.append(f"Rank: {int(rank)}")

        if percent is not None:
            pct_str = f"{percent:+.2f}%"
            title_parts.append(pct_str)

        title_text = " | ".join(title_parts)

        self.kline_plot.setTitle(title_text)


        # --- A. Render Daily K-Line ---
        day_df = day_df.sort_index()
        dates = day_df.index
        # Convert date index to integers 0..N
        x_axis = np.arange(len(day_df))
        
        # Create OHLC Data for CandlestickItem
        ohlc_data = []
        for i, (idx, row) in enumerate(day_df.iterrows()):
            ohlc_data.append((i, row['open'], row['close'], row['low'], row['high']))
        
        # # Draw Candles
        # candle_item = CandlestickItem(ohlc_data)
        # self.kline_plot.addItem(candle_item)
        candle_item = CandlestickItem(
            ohlc_data,
            theme=self.qt_theme
        )
        self.kline_plot.addItem(candle_item)
        
        # Draw Signals (Arrows)
        signals = self.logger.get_signal_history_df()
        if not signals.empty:
            stock_signals = signals[signals['code'] == code]
            if not stock_signals.empty:
                arrow_x = []
                arrow_y = []
                brushes = []
                
                # Align signals to x-axis indices
                date_map = {
                    d if isinstance(d, str) else d.strftime('%Y-%m-%d'): i
                    for i, d in enumerate(dates)
                }
                for _, row in stock_signals.iterrows():
                    sig_date_str = str(row['date']).split()[0]
                    if sig_date_str in date_map:
                        idx = date_map[sig_date_str]
                        arrow_x.append(idx)
                        
                        action = row['action']
                        price = row['price'] if pd.notnull(row['price']) else day_df.iloc[idx]['close']
                        arrow_y.append(price)
                        
                        if 'Buy' in action or '买' in action:
                            brushes.append(pg.mkBrush('r')) # Red for Buy
                        else:
                            brushes.append(pg.mkBrush('g')) # Green for Sell

                if arrow_x:
                    scatter = pg.ScatterPlotItem(x=arrow_x, y=arrow_y, size=15, 
                                                 pen=pg.mkPen('k'), brush=brushes, symbol='t1')
                    self.kline_plot.addItem(scatter)

        if 'close' in day_df.columns:
            # --- MA5 / MA10 ---
            ma5 = day_df['close'].rolling(5).mean()
            ma10 = day_df['close'].rolling(10).mean()
            self.kline_plot.plot(x_axis, ma5.values, pen=pg.mkPen('b', width=1), name="MA5")
            self.kline_plot.plot(x_axis, ma10.values, pen=pg.mkPen('orange', width=1), name="MA10")
            
            # --- Bollinger Bands ---
            ma20 = day_df['close'].rolling(20).mean()
            std20 = day_df['close'].rolling(20).std()
            upper_band = ma20 + 2 * std20
            lower_band = ma20 - 2 * std20

            # self.kline_plot.plot(x_axis, ma20.values, pen=pg.mkPen('purple', width=1, style=Qt.PenStyle.DotLine))
            # self.kline_plot.plot(x_axis, upper_band.values, pen=pg.mkPen('grey', width=1, style=Qt.PenStyle.DashLine))
            # self.kline_plot.plot(x_axis, lower_band.values, pen=pg.mkPen('grey', width=1, style=Qt.PenStyle.DashLine))

            # 中轨颜色根据主题调整
            if self.qt_theme == 'dark':
                ma20_color = QColor(255, 255, 0)  # 黄色
            else:
                ma20_color = QColor(255, 140, 0)  # 深橙色 (DarkOrange)
            
            self.kline_plot.plot(x_axis, ma20.values,
                                 pen=pg.mkPen(ma20_color, width=2))

            # 上轨 深红色加粗
            self.kline_plot.plot(x_axis, upper_band.values,
                                 pen=pg.mkPen(QColor(139, 0, 0), width=2))  # DarkRed

            # 下轨 深绿色加粗
            self.kline_plot.plot(x_axis, lower_band.values,
                                 pen=pg.mkPen(QColor(0, 128, 0), width=2))  # DarkGreen

            # --- 自动居中显示 ---
            self.kline_plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            self.kline_plot.autoRange()


        # --- volume plot ---
        if 'amount' in day_df.columns:
            # 创建 volume 子图
            if not hasattr(self, 'volume_plot'):
                self.volume_plot = self.kline_widget.addPlot(row=1, col=0)
                self.volume_plot.showGrid(x=True, y=True)
                self.volume_plot.setMaximumHeight(120)
                self.volume_plot.setLabel('left', 'Volume')
                self.volume_plot.setXLink(self.kline_plot)  # x 轴同步主图
                self.volume_plot.setMenuEnabled(False)
            else:
                # 清空之前的数据，防止重叠
                self.volume_plot.clear()
            
            x_axis = np.arange(len(day_df))
            amounts = day_df['amount'].values

            # 涨的柱子
            up_idx = day_df['close'] >= day_df['open']
            if up_idx.any():
                bg_up = pg.BarGraphItem(
                    x=x_axis[up_idx],
                    height=amounts[up_idx],
                    width=0.6,
                    brush='r'
                )
                self.volume_plot.addItem(bg_up)

            # 跌的柱子
            down_idx = day_df['close'] < day_df['open']
            if down_idx.any():
                bg_down = pg.BarGraphItem(
                    x=x_axis[down_idx],
                    height=amounts[down_idx],
                    width=0.6,
                    brush='g'
                )
                self.volume_plot.addItem(bg_down)
            
            # 添加5日均量线
            ma5_volume = pd.Series(amounts).rolling(5).mean()
            if self.qt_theme == 'dark':
                vol_ma_color = QColor(255, 255, 0)  # 黄色
            else:
                vol_ma_color = QColor(255, 140, 0)  # 深橙色
            
            self.volume_plot.plot(x_axis, ma5_volume.values,
                                 pen=pg.mkPen(vol_ma_color, width=1.5),
                                 name='MA5')

        # --- B. Render Intraday Trick ---
        if not tick_df.empty:
            try:
                # 1. Prepare Data
                df_ticks = tick_df.copy()
                
                # Handle MultiIndex: code, ticktime
                if isinstance(df_ticks.index, pd.MultiIndex):
                    # Sort by ticktime just in case
                    df_ticks = df_ticks.sort_index(level='ticktime')
                    prices = df_ticks['close'].values
                else:
                    prices = df_ticks['close'].values

                # Get Params
                current_price = prices[-1]

                # Attempt to get pre_close (llastp)
                if 'llastp' in df_ticks.columns:
                    pre_close = float(df_ticks['llastp'].iloc[-1]) 
                elif 'pre_close' in df_ticks.columns:
                    pre_close = float(df_ticks['pre_close'].iloc[-1])
                else:
                    pre_close = prices[0] 
                
                open_p = 0
                if 'open' in df_ticks.columns:
                    # Avoid 0 values if possible
                    opens = df_ticks['open'][df_ticks['open'] > 0]
                    if not opens.empty:
                        open_p = opens.iloc[-1]
                    else:
                        open_p = prices[0]
                else:
                    open_p = prices[0]

                low_p = prices.min() 
                if 'low' in df_ticks.columns:
                    mins = df_ticks['low'][df_ticks['low'] > 0]
                    if not mins.empty:
                        l_val = mins.min()
                        if l_val < low_p: low_p = l_val

                high_p = prices.max()
                if 'high' in df_ticks.columns:
                    maxs = df_ticks['high'][df_ticks['high'] > 0]
                    if not maxs.empty:
                        h_val = maxs.max()
                        if h_val > high_p: high_p = h_val
                
                # 2. Update Ghost Candle on Day Chart
                day_dates = day_df.index
                last_hist_date_str = ""
                if not day_dates.empty:
                    last_hist_date_str = str(day_dates[-1]).split()[0]
                
                today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
                
                # Compare today vs last history. If today > last_hist, draw ghost
                # Note: simple string comparison works for YYYY-MM-DD
                if today_str > last_hist_date_str:
                    new_x = len(day_df)
                    ghost_data = [(new_x, open_p, current_price, low_p, high_p)]
                    ghost_candle = CandlestickItem(ghost_data)
                    self.kline_plot.addItem(ghost_candle)
                    
                    # Add current price label
                    text = pg.TextItem(f"{current_price}", anchor=(0, 1), color='r' if current_price>pre_close else 'g')
                    text.setPos(new_x, high_p)
                    self.kline_plot.addItem(text)


                # 3. Render Tick Plot (Curve)
                pct_change = ((current_price - pre_close) / pre_close * 100) if pre_close != 0 else 0
                self.tick_plot.setTitle(f"Intraday: {current_price:.2f} ({pct_change:.2f}%)")
                
                # X-axis: 0 to N
                x_ticks = np.arange(len(prices))
                
                # Draw Pre-close (Dash Blue)
                self.tick_plot.addLine(y=pre_close, pen=pg.mkPen('b', style=Qt.PenStyle.DashLine, width=1))
                
                # # Draw Price Curve
                if self.qt_theme == 'dark':
                    curve_color = 'w'  # 白色线条
                    pre_close_color = 'b'
                    avg_color = QColor(255, 255, 0)  # 黄色均价线
                else:
                    curve_color = 'k'
                    pre_close_color = 'b'
                    avg_color = QColor(255, 140, 0)  # 深橙色均价线 (DarkOrange)
                
                curve_pen = pg.mkPen(curve_color, width=2)
                self.tick_plot.plot(x_ticks, prices, pen=curve_pen, name='Price')
                self.tick_plot.addLine(y=pre_close, pen=pg.mkPen(pre_close_color, style=Qt.PenStyle.DashLine))

                # 计算并绘制分时均价线
                # 分时均价 = 累计成交金额 / 累计成交量
                if 'amount' in df_ticks.columns and 'volume' in df_ticks.columns:
                    # 使用 amount 和 volume 计算均价
                    cum_amount = df_ticks['amount'].cumsum()
                    cum_volume = df_ticks['volume'].cumsum()
                    # 避免除以零
                    avg_prices = np.where(cum_volume > 0, cum_amount / cum_volume, prices)
                elif 'close' in df_ticks.columns:
                    # 如果没有成交量数据，使用价格的累计平均
                    avg_prices = pd.Series(prices).expanding().mean().values
                else:
                    avg_prices = None
                
                if avg_prices is not None:
                    avg_pen = pg.mkPen(avg_color, width=1.5, style=Qt.PenStyle.SolidLine)
                    self.tick_plot.plot(x_ticks, avg_prices, pen=avg_pen, name='Avg Price')
                
                # Add Grid
                self.tick_plot.showGrid(x=False, y=True, alpha=0.5)

            except Exception as e:
                print(f"Error rendering tick data: {e}")
                import traceback
                traceback.print_exc()

def run_visualizer(initial_code=None, df_all=None):
    """
    启动 Visualizer GUI。
    - initial_code: optional str, 首次加载的股票 code
    - df_all: optional pd.DataFrame, 用于主程序同步数据
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    
    # 如果有 df_all, 直接更新
    if df_all is not None:
        window.update_df_all(df_all)
    
    # Load initial code
    if initial_code:
        if len(initial_code) == 6 or len(initial_code) == 8:
            window.load_stock_by_code(initial_code)
    
    window.show()
    sys.exit(app.exec())

def main(initial_code=None):
    # --- 1. 尝试成为 Primary Instance ---
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.bind((IPC_HOST, IPC_PORT))
        server_socket.listen(1)
        is_primary_instance = True
        print(f"Listening on {IPC_HOST}:{IPC_PORT}")
    except OSError:
        is_primary_instance = False

    # --- 2. Secondary Instance: 发送 code 给 Primary Instance 后退出 ---
    if not is_primary_instance:
        if len(sys.argv) > 1:
            code_to_send = sys.argv[1]
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.connect((IPC_HOST, IPC_PORT))
                client_socket.send(code_to_send.encode('utf-8'))
                client_socket.close()
                print(f"Sent command: {code_to_send}")
            except Exception as e:
                print(f"Failed to send command: {e}")
        sys.exit(0)

    # --- 3. Primary Instance: 启动 GUI ---
    app = QApplication(sys.argv)
    window = MainWindow()
    start_code = initial_code
    # 启动监听线程，处理 socket 消息
    listener = CommandListenerThread(server_socket)
    listener.command_received.connect(window.load_stock_by_code)
    listener.dataframe_received.connect(window.update_df_all)
    listener.command_received.connect(lambda: window.raise_())
    listener.command_received.connect(lambda: window.activateWindow())
    listener.start()

    window.show()

    # 如果 exe 启动时带了参数
    if len(sys.argv) > 1:
        start_code = sys.argv[1]
        if len(start_code) in (6, 8):
            window.load_stock_by_code(start_code)
    elif start_code is not None:
        window.load_stock_by_code(start_code)


    sys.exit(app.exec())
# def open_visualizer(code=None):
#     if not code:
#         return

#     ipc_host, ipc_port = '127.0.0.1', 26668
#     sent = False

#     # 尝试发送给已存在 visualizer
#     try:
#         client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         client.settimeout(1)
#         client.connect((ipc_host, ipc_port))
#         client.send(f"CODE|{code}".encode('utf-8'))
#         sent = True
#         client.close()
#     except (ConnectionRefusedError, OSError):
#         sent = False

#     # 如果没发出去 -> 启动新实例
#     if not sent:
#         visualizer_path = get_visualizer_path()
#         if not visualizer_path:
#             return
#         subprocess.Popen([sys.executable, visualizer_path, str(code)])
#         logger.info(f"Launched visualizer for {code}")

#         # 延迟尝试发送 df_all
#         if hasattr(self, 'df_all') and not self.df_all.empty:
#             import time
#             import pickle, struct
#             for _ in range(10):
#                 try:
#                     time.sleep(0.5)  # 等待 visualizer 启动
#                     data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#                     data_socket.settimeout(2)
#                     data_socket.connect((ipc_host, ipc_port))
#                     ui_cols = ['code', 'name', 'Rank', 'percent']
#                     df_ui = self.df_all[ui_cols].copy()
#                     pickled_data = pickle.dumps(df_ui, protocol=pickle.HIGHEST_PROTOCOL)
#                     header = struct.pack("!I", len(pickled_data))
#                     data_socket.sendall(b"DATA" + header + pickled_data)
#                     data_socket.close()
#                     logger.info("Sent df_all after launching visualizer")
#                     break
#                 except Exception:
#                     continue



if __name__ == "__main__":

    main()
    # # 1. Try to become the Primary Instance
    # # logger.setLevel(LoggerFactory.DEBUG)
    # server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # try:
    #     server_socket.bind((IPC_HOST, IPC_PORT))
    #     server_socket.listen(1)
    #     print(f"Listening on {IPC_HOST}:{IPC_PORT}")
    #     is_primary_instance = True
    # except OSError:
    #     # Port already in use -> Secondary Instance
    #     is_primary_instance = False
    
    # # 2. Secondary Instance Logic: Send args and exit
    # if not is_primary_instance:
    #     if len(sys.argv) > 1:
    #         code_to_send = sys.argv[1]
    #         try:
    #             client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #             client_socket.connect((IPC_HOST, IPC_PORT))
    #             client_socket.send(code_to_send.encode('utf-8'))
    #             client_socket.close()
    #             print(f"Sent command: {code_to_send}")
    #         except Exception as e:
    #             print(f"Failed to send command: {e}")
    #     else:
    #         print("Visualizer is already running.")
    #         # Bring to front? context dependent.
        
    #     sys.exit(0)

    # # 3. Primary Instance Logic: Start GUI
    # app = QApplication(sys.argv)
    # window = MainWindow()
    
    # # Start Listener
    # listener = CommandListenerThread(server_socket)
    # listener.command_received.connect(window.load_stock_by_code)
    # listener.dataframe_received.connect(window.update_df_all)  # Handle df_all updates
    # listener.command_received.connect(lambda: window.raise_()) # Bring to front
    # listener.command_received.connect(lambda: window.activateWindow())
    # listener.start()

    # window.show()
    
    # # Check CLI args for initial load
    # if len(sys.argv) > 1:
    #     start_code = sys.argv[1]
    #     if len(start_code) == 6 or len(start_code) == 8:
    #          window.load_stock_by_code(start_code)

    # sys.exit(app.exec())


    # import socket

    # # 判断是否有参数
    # code_arg = sys.argv[1] if len(sys.argv) > 1 else None

    # # 单实例逻辑
    # server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # try:
    #     server_socket.bind((IPC_HOST, IPC_PORT))
    #     server_socket.listen(1)
    #     is_primary_instance = True
    # except OSError:
    #     is_primary_instance = False

    # if not is_primary_instance:
    #     if code_arg:
    #         try:
    #             client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #             client_socket.connect((IPC_HOST, IPC_PORT))
    #             client_socket.send(code_arg.encode('utf-8'))
    #             client_socket.close()
    #             print(f"Sent command: {code_arg}")
    #         except Exception as e:
    #             print(f"Failed to send command: {e}")
    #     sys.exit(0)

    # # Primary Instance
    # open_visualizer(code=code_arg)
