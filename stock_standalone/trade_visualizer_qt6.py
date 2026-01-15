import sys
import os
import pandas as pd
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QSplitter, QFrame, QMessageBox
)
from PyQt6.QtCore import QObject,Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QBrush, QPen
from PyQt6.QtWidgets import QComboBox, QCheckBox, QHBoxLayout, QLabel, QToolBar
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtCore import QMutex, QThread, pyqtSignal, QMutexLocker
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QWidget
from PyQt6.QtWidgets import QSizePolicy

import socket
import pickle
import struct
from JohnsonUtil import LoggerFactory
from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import commonTips as cct
from JohnsonUtil.commonTips import timed_ctx,print_timing_summary
from JohnsonUtil import johnson_cons as ct
import datetime  # ⚠️ 必须导入
import time
# Configuration
IPC_PORT = 26668
IPC_HOST = '127.0.0.1'
logger = LoggerFactory.getLogger()
# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
from multiprocessing import Process, Queue
import queue  # 这个一定要加，用于捕获 Empty 异常
from multiprocessing import Event
import multiprocessing as mp
# 全局或窗口属性
stop_event = Event()
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
# pg.setConfigOption('background', 'w')
# pg.setConfigOption('foreground', 'k')

class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data, theme='light'):
        super().__init__()
        self.data = np.asarray(data)
        self.theme = theme
        self.picture = pg.QtGui.QPicture()
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

    def setData(self, data):
        self.data = np.asarray(data)
        self.generatePicture()
        self.prepareGeometryChange()
        self.update()

    def generatePicture(self):
        self.picture = pg.QtGui.QPicture()
        p = pg.QtGui.QPainter(self.picture)
        w = 0.4
        
        for row in self.data:
            t, open_, close, low, high = row[:5]
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

    def paint(self, p, *args):
        if self.picture:
            p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return pg.QtCore.QRectF(self.picture.boundingRect())

class DateAxis(pg.AxisItem):
    def __init__(self, dates, orientation='bottom'):
        super().__init__(orientation=orientation)
        self.dates = list(dates)

    def updateDates(self, dates):
        self.dates = list(dates)
        self.update()

    def tickStrings(self, values, scale, spacing):
        """把整数索引映射成日期字符串，最后一天显示在末尾"""
        strs = []
        n = len(self.dates)
        if n == 0:
            # dates 为空，直接用原始值
            return [str(v) for v in values]

        for val in values:
            try:
                idx = int(val)
                if idx < 0:
                    idx = 0  # 负索引归零
                elif idx >= n:
                    idx = n - 1  # 超出范围用最后一天
                strs.append(str(self.dates[idx])[5:10])  # MM-DD
            except Exception as e:
                # 捕捉意外异常
                logger.warning(f"[tickStrings] val={val} error: {e}")
                strs.append("")  # 出错显示空
        return strs


    # def tickStrings(self, values, scale, spacing):
    #     """把整数索引映射成日期字符串，最后一天显示在末尾"""
    #     strs = []
    #     n = len(self.dates)
    #     if n == 0:
    #         return [str(v) for v in values]
    #     for val in values:
    #         idx = int(val)
    #         if idx < n:
    #             strs.append(str(self.dates[idx])[5:])  # MM-DD
    #         else:
    #             strs.append(str(self.dates[-1])[5:])  # ghost candle 对应最后一天
    #     return strs


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


duration_date_day = 70
duration_date_up = 250      #
# duration_date_up = 190
# duration_date_up = 120
duration_date_week = 500    #3-ma60d
# duration_date_month = 300
duration_date_month = 1000    #3-ma20d
#m : 510 ma26

Resample_LABELS_Days = {'d':duration_date_day,'3d':duration_date_up,
                      'w':duration_date_week,'m':duration_date_month}

class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(object, object, object) # code, day_df, tick_df

    def __init__(self, code ,mutex_lock, resample='d'):
        super().__init__()
        self.code = code
        self.resample = resample
        self.mutex_lock = mutex_lock # 存储锁对象
        self._search_code = None
        self._resample = None
        # self._sinadata = sinadata
    def run(self):
            try:
                # 使用 QMutexLocker 自动管理锁定和解锁
                if self._search_code == self.code and self._resample == self.resample:
                    return  # 数据已经加载过，不重复
                with QMutexLocker(self.mutex_lock):
                    # 1. Fetch Daily Data (Historical)
                    # tdd.get_tdx_Exp_day_to_df 内部调用 HDF5 API，必须在锁内执行
                    with timed_ctx("get_tdx_Exp_day_to_df", warn_ms=800):
                       day_df = tdd.get_tdx_Exp_day_to_df(self.code, dl=Resample_LABELS_Days[self.resample],resample=self.resample,fastohlc=True)
                       # day_df = tdd.get_tdx_Exp_day_to_df(self.code, dl=ct.Resample_LABELS_Days[self.resample],resample=self.resample,fastohlc=True)

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



def tick_to_daily_bar(tick_df: pd.DataFrame) -> pd.DataFrame:
    """
    将 tick_df（MultiIndex: code, ticktime）聚合成“今天的一根日 K”
    返回：
        index: DatetimeIndex([today])
        columns: open, high, low, close, volume
    """
    if tick_df is None or tick_df.empty:
        return pd.DataFrame()

    df = tick_df.copy()
    # === 1. 取 ticktime ===
    if isinstance(df.index, pd.MultiIndex) and 'ticktime' in df.index.names:
        tick_time = pd.to_datetime(df.index.get_level_values('ticktime'))
    elif 'ticktime' in df.columns:
        tick_time = pd.to_datetime(df['ticktime'])
    else:
        return pd.DataFrame()

    df['_dt'] = tick_time
    df['_date'] = df['_dt'].dt.normalize()

    # today = pd.Timestamp.today().normalize()
    # df = df[df['_date'] == today]
    # 获取今天的日期（不带时间）
    today = pd.Timestamp.today().normalize()

    # 筛选今天的数据
    df = df[df['_date'] == today]

    # # 将 dt 和 ticktime 拼接成完整时间字符串，再转 datetime
    # df['ticktime'] = pd.to_datetime(
    #     df['dt'].astype(str) + ' ' + df['ticktime'].astype(str),
    #     format='%Y-%m-%d'
    # )
    today = pd.Timestamp.today().normalize().strftime('%Y-%m-%d')

    if df.empty:
        return pd.DataFrame()

    # === 2. 价格列统一 ===
    # 你的真实价格列是 close
    price_col = 'close'

    bar = pd.DataFrame(
        {
            'open':   [df[price_col].iloc[0]],
            'high':   [df[price_col].max()],
            'low':    [df[price_col].min()],
            'close':  [df[price_col].iloc[-1]],
            'volume': [df['volume'].iloc[-1]],  # 注意：你的 volume 是累计量
        },
        index=[today],
    )
    logger.debug(f'bar: {bar} df:{df.high.max()}')
    return bar

def realtime_worker_process(code, queue, stop_flag,log_level=None,debug_realtime=False,interval=cct.sina_limit_time):
    """多进程拉取实时数据"""
    if log_level:
        logger = LoggerFactory.getLogger()
        if log_level is not None:
            logger.setLevel(log_level.value)
    s = sina_data.Sina()
    # while True:
    count_debug = 0
    while  stop_flag.value:   # 👈 关键
        try:
            # if cct.get_trade_date_status() and cct.get_now_time_int() > 920 or not cct.get_trade_date_status():
            if (cct.get_work_time() and cct.get_now_time_int() > 923) or debug_realtime:
                with timed_ctx("realtime_worker_process", warn_ms=800):
                    tick_df = s.get_real_time_tick(code)
                    # 这里可以生成今天的 day_bar
                    if log_level and tick_df is None or tick_df.empty:
                        logger.warning(
                            f"[RT] tick_df EMPTY | code={code} | "
                            f"trade={cct.get_trade_date_status()} "
                            f"time={cct.get_now_time_int()}"
                        )
                        time.sleep(interval)
                        continue
                with timed_ctx("realtime_worker_tick_to_daily_bar", warn_ms=800):
                    today_bar = tick_to_daily_bar(tick_df)
                    if log_level and today_bar is None or today_bar.empty:
                        logger.warning(
                            f"[RT] today_bar EMPTY | code={code} | "
                            f"today_bar_rows={len(today_bar)} | "
                            f"today_bar_cols={list(today_bar.columns)}"
                        )
                        time.sleep(interval)
                        continue
                    try:
                        # queue.put((code, tick_df, today_bar))
                        if log_level and count_debug == 0 and debug_realtime:
                            logger.debug(
                                    f"[RT] tick_df | code={code} | "
                                    f"tick_rows={len(tick_df)} | "
                                    f"tick_cols={list(tick_df.columns)}"
                                    f"tick={(tick_df[-3:])}"
                                )
                            # dump_path = cct.get_ramdisk_path(f"{code}_tick_{int(time.time())}.pkl")
                            # tick_df.to_pickle(dump_path)
                            logger.debug(
                                    f"[RT] today_bar | code={code} | "
                                    f"today_barrows={len(today_bar)} | "
                                    f"today_bar_cols={list(today_bar.columns)}"
                                    f"today_bar=\n{(today_bar)}"
                                )
                            # dump_path = cct.get_ramdisk_path(f"{code}_today_{int(time.time())}.pkl")
                            # today_bar.to_pickle(dump_path)
                            # count_debug += 1
                        queue.put_nowait((code, tick_df, today_bar))
                    except queue.Full:
                        pass  # 队列满了就跳过，避免卡住
        except Exception as e:
            import traceback
            traceback.print_exc()
            time.sleep(interval)  # 避免无限抛异常占用 CPU
        # time.sleep(interval)
        if stop_flag.value:
            for _ in range(interval):
                if not stop_flag.value:
                    break
                time.sleep(1)
        # logger.debug(f'auto_process interval: {interval}')
    print(f'stop_flag: {stop_flag.value}')

# def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
#         """
#         统一 DataFrame 结构：
#         - MultiIndex(code, ticktime) → 普通列 code, ticktime
#         - ticktime 自适应类型：
#             - datetime → 保留
#             - str → 转 datetime
#             - float/int timestamp → 转 datetime
#         - 重置 index，保证 Viewer 内部只使用列
#         """
#         df = df.copy()

#         if isinstance(df.index, pd.MultiIndex):
#             idx_names = df.index.names

#             # code
#             if 'code' in idx_names:
#                 df['code'] = df.index.get_level_values('code')
#             else:
#                 df['code'] = df.index.get_level_values(0)

#             # ticktime / time / datetime
#             time_level = None
#             for name in idx_names:
#                 if name and name.lower() in ('ticktime', 'time', 'datetime', 'date'):
#                     time_level = name
#                     break

#             if time_level:
#                 ts = df.index.get_level_values(time_level)
#             else:
#                 ts = df.index.get_level_values(1)

#             # 自适应处理 ticktime
#             if np.issubdtype(ts.dtype, np.datetime64):
#                 df['ticktime'] = ts
#             elif np.issubdtype(ts.dtype, np.number):
#                 # float/int timestamp → datetime
#                 df['ticktime'] = pd.to_datetime(ts, unit='s', errors='coerce')
#             else:
#                 # str → datetime
#                 df['ticktime'] = pd.to_datetime(ts, errors='coerce')

#             df.reset_index(drop=True, inplace=True)
#         else:
#             # 单层 index 或普通 DataFrame
#             if 'ticktime' in df.columns:
#                 if np.issubdtype(df['ticktime'].dtype, np.datetime64):
#                     pass  # 保留
#                 elif np.issubdtype(df['ticktime'].dtype, np.number):
#                     df['ticktime'] = pd.to_datetime(df['ticktime'], unit='s', errors='coerce')
#                 else:
#                     df['ticktime'] = pd.to_datetime(df['ticktime'], errors='coerce')

#             # 如果 index 是 code，也转成列
#             if 'code' not in df.columns:
#                 df = df.reset_index()
#                 df.rename(columns={df.columns[0]: 'code'}, inplace=True)

#         return df

def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    统一 DataFrame 结构（最终稳定版）：

    输出保证：
    - 存在列：code, date
    - date 类型：datetime64[ns]，粒度为 YYYY-MM-DD（normalize）
    - 不混用 str / Timestamp
    - 可直接 set_index('date') + sort_index()

    处理逻辑：
    - MultiIndex(code, ticktime/date/...) → 列
    - 单层 index → 兜底转列
    - 所有时间统一 → datetime → normalize
    """
    df = df.copy()

    # ---------- 1. 统一抽取 code / time ----------
    ts = None

    if isinstance(df.index, pd.MultiIndex):
        idx_names = df.index.names

        # code
        if 'code' in idx_names:
            df['code'] = df.index.get_level_values('code')
        else:
            df['code'] = df.index.get_level_values(0)

        # time / date
        time_level = None
        for name in idx_names:
            if name and name.lower() in ('ticktime', 'time', 'datetime', 'date'):
                time_level = name
                break

        ts = (
            df.index.get_level_values(time_level)
            if time_level
            else df.index.get_level_values(1)
        )

        df.reset_index(drop=True, inplace=True)

    else:
        # 单层 index
        if 'ticktime' in df.columns:
            ts = df['ticktime']
        elif 'date' in df.columns:
            ts = df['date']
        else:
            # index 当时间兜底
            ts = df.index

        # code 兜底
        if 'code' not in df.columns:
            df = df.reset_index(drop=False)
            df.rename(columns={df.columns[0]: 'code'}, inplace=True)

    # ---------- 2. 时间统一转 datetime ----------
    ts = pd.to_datetime(ts, errors='coerce')

    # ---------- 3. 统一成“日粒度 YYYY-MM-DD” ----------
    if 'date' in df.columns:
        df['date'] = ts.dt.normalize()

        # ---------- 4. 清洗非法数据 ----------
        df = df.dropna(subset=['date'])

    # ---------- 5. 删除旧时间字段，避免污染 ----------
    for col in ('ticktime',):
        if col in df.columns:
            df.drop(columns=col, inplace=True)

    return df


from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

class GlobalInputFilter(QtCore.QObject):
    """
    捕捉全窗口鼠标侧键和键盘按键
    """
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window

    def eventFilter(self, obj, event):
        # 只在主窗口活动时处理
        if not self.main_window.isActiveWindow():
            return super().eventFilter(obj, event)

        # 鼠标按键
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.XButton1:  # 前进键
                self.main_window.switch_resample_prev()
                return True
            elif event.button() == Qt.MouseButton.XButton2:  # 后退键
                self.main_window.switch_resample_next()
                return True

        # 键盘按键
        elif event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_1:
                self.main_window.on_resample_changed('d')
                return True
            elif key == Qt.Key.Key_2:
                self.main_window.on_resample_changed('3d')
                return True
            elif key == Qt.Key.Key_3:
                self.main_window.on_resample_changed('w')
                return True
            elif key == Qt.Key.Key_4:
                self.main_window.on_resample_changed('m')
                return True

        return super().eventFilter(obj, event)

class RealtimeWorker(QObject):
    data_updated = pyqtSignal(object, object, object)  # code, tick_df, today_bar

    def __init__(self, mutex, interval_ms=3000):
        super().__init__()
        self._mutex = mutex
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)
        self._code = None
        self._running = False
        self._sina = sina_data.Sina()

    def start(self, code):
        self._code = code
        self._running = True
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._running = False
        self._code = None

    def _poll(self):
        if not self._running or not self._code:
            return
        try:
            with timed_ctx("_sina.get_real_time_tick", warn_ms=800):
                tick_df = self._sina.get_real_time_tick(self._code)
            with timed_ctx("_sina.get_real_time_tick_to_daily_bar", warn_ms=800):
                today_bar = tick_to_daily_bar(tick_df)
            if today_bar.empty:
                return
            self.data_updated.emit(self._code, tick_df, today_bar)
        except Exception as e:
            print(f"[RealtimeWorker] {e}")


class MainWindow(QMainWindow, WindowMixin):
    def __init__(self,stop_flag=None,log_level=None,debug_realtime=False):
        super().__init__()
        self.setWindowTitle("Trade Signal Visualizer (Qt6 + PyQtGraph)")
        self.sender = StockSender(callback=None)
        # WindowMixin requirement: scale_factor
        self._debug_realtime = debug_realtime   # 临时调试用
        self.scale_factor = get_windows_dpi_scale_factor()
        self.hdf5_mutex = QMutex() 
        self.stop_flag = stop_flag
        self.log_level = log_level
        self.resample = 'd'
        self.qt_theme = 'dark'  # 默认使用黑色主题
        self.show_bollinger = True
        self.tdx_enabled = False  # 默认开启
        self.realtime = True  # 默认开启
        # 缓存 df_all
        self.df_cache = pd.DataFrame()
        # self.realtime_worker = None
        self.last_initialized_trade_day = None  # 记录最后一次初始化的交易日
        self._closing = False
        self.realtime_queue = Queue()
        self.realtime_process = None

        # 定时检查队列
        self.realtime_timer = QTimer()
        self.realtime_timer.timeout.connect(self._poll_realtime_queue)
        self.realtime_timer.start(5000)  # 每5秒检查一次队列

        self.day_df = pd.DataFrame()
        self.df_all = pd.DataFrame()

        # ---- resample state ----
        self.resample_keys = ['d', '3d', 'w', 'm']

        if self.resample in self.resample_keys:
            self.current_resample_idx = self.resample_keys.index(self.resample)
        else:
            self.current_resample_idx = 0
            self.resample = self.resample_keys[0]

        # --- 1. 创建工具栏 ---
        self._init_toolbar()
        self._init_resample_toolbar()
        self._init_theme_selector()
        self._init_tdx()
        self._init_real_time()
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
        self.stock_table.setMaximumWidth(300)

        self.stock_table.setStyleSheet("""

        QTableWidget {
            background-color: transparent;
        }

        /* 只作用在 table 内部 */
        QTableWidget QScrollBar:vertical {
            width: 6px;
            background: transparent;
            margin: 0px;
        }

        QTableWidget QScrollBar::handle:vertical {
            background: rgba(180, 180, 180, 120);
            min-height: 30px;
            border-radius: 3px;
        }

        QTableWidget QScrollBar::handle:vertical:hover {
            background: rgba(220, 220, 220, 180);
        }

        QTableWidget QScrollBar::add-line:vertical,
        QTableWidget QScrollBar::sub-line:vertical {
            height: 0px;
        }

        QTableWidget QScrollBar::add-page:vertical,
        QTableWidget QScrollBar::sub-page:vertical {
            background: transparent;
        }
        """)

        self.stock_table.setStyleSheet(self.stock_table.styleSheet() + """
        QTableWidget::item:hover {
            background: rgba(255, 255, 255, 30);
        }
        QTableWidget::item:selected {
            background: rgba(255, 215, 0, 80);
            color: black;
        }
        """)
        self.stock_table.verticalScrollBar().setFixedWidth(6)
        # self.stock_table.setHorizontalHeaderLabels(['Code', 'Name', 'Rank', 'Percent'])
        # self.headers = ['code', 'name', 'percent','dff', 'Rank', 'win', 'slope', 'volume', 'power_idx']
        real_time_cols = cct.real_time_cols
        if len(real_time_cols) > 4 and 'percent' in real_time_cols:
            self.headers = real_time_cols
        else:
            logger.info(f'real_time_cols: {real_time_cols} not good')
            self.headers = ['code', 'name', 'percent','dff', 'Rank', 'win', 'slope', 'volume', 'power_idx']
        # self.headers = ['Code', 'Name', 'Rank', 'Percent']
        self.stock_table.setColumnCount(len(self.headers))
        
        self.stock_table.setHorizontalHeaderLabels(self.headers)
        # self.stock_table.horizontalHeader().setStretchLastSection(True)
        self.stock_table.setSortingEnabled(True)
        headers = self.stock_table.horizontalHeader()
        headers.setStretchLastSection(True)
        # 设置表格列自适应
        # 所有列自动根据内容调整宽度
        for col in range(len(headers)):
            headers.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

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

        # --- 添加重置按钮 (只添加一次) ---
        # self._add_reset_button()

        # -- Bottom Chart: Intraday
        self.tick_widget = pg.GraphicsLayoutWidget()
        self.tick_plot = self.tick_widget.addPlot(title="Real-time / Intraday")
        self.tick_plot.showGrid(x=True, y=True)
        right_splitter.addWidget(self.tick_widget)
        
        # Set splitter sizes (70% top, 30% bottom)
        right_splitter.setSizes([500, 200])
        # 安装全局事件过滤器
        self.input_filter = GlobalInputFilter(self)
        self.installEventFilter(self.input_filter)
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


    def _reset_kline_view(self):
        """重置 K 线图缩放和范围"""
        if hasattr(self, 'kline_plot'):
            self.kline_plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            # 如果你用的是 ViewBox，可以加上：
            vb = self.kline_plot.getViewBox()
            vb.autoRange()
            # print("[INFO] K-line view reset")

    def _init_resample_toolbar(self):
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Resample:"))

        self.resample_group = QActionGroup(self)
        self.resample_group.setExclusive(True)

        self.resample_actions = {}

        label_map = {
            'd': '1D',
            '3d': '3D',
            'w': '1W',
            'm': '1M',
        }

        for key in self.resample_keys:
            act = QAction(label_map.get(key, key), self)
            act.setCheckable(True)
            act.setData(key)

            if key == self.resample:
                act.setChecked(True)

            act.triggered.connect(lambda checked, k=key: self.on_resample_changed(k))

            self.resample_group.addAction(act)
            self.toolbar.addAction(act)
            self.resample_actions[key] = act

    def switch_resample_prev(self):
        self.current_resample_idx = (self.current_resample_idx - 1) % len(self.resample_keys)
        key = self.resample_keys[self.current_resample_idx]
        self.on_resample_changed(key)

    def switch_resample_next(self):
        self.current_resample_idx = (self.current_resample_idx + 1) % len(self.resample_keys)
        key = self.resample_keys[self.current_resample_idx]
        self.on_resample_changed(key)

    def on_resample_changed(self, key):
        if key not in self.resample_keys:
            return

        if key == self.resample:
            return

        # ① 更新内部状态
        self.resample = key
        self.current_resample_idx = self.resample_keys.index(key)

        # ② 同步 toolbar UI（关键）
        act = self.resample_actions.get(key)
        if act is not None and not act.isChecked():
            act.setChecked(True)

        # ③ 执行真实业务逻辑
        if self.current_code:
            self.load_stock_by_code(self.current_code)

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

    def _init_real_time(self):
        """Initialize TDX / code link toggle"""
        self.real_time_cb = QCheckBox("实时")
        self.real_time_cb.setChecked(self.realtime)  # 默认联动
        self.real_time_cb.stateChanged.connect(self.on_real_time_toggled)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.real_time_cb)

        # --- 添加右侧 Reset 按钮 ---
        spacer = QWidget()        # 占位伸缩
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)  # 占满中间空间，把后面的按钮推到右边

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset_kline_view)
        self.toolbar.addWidget(reset_btn)

    def on_real_time_toggled(self, state):
        self.realtime = bool(state)
        # 当前时间是否在交易时段
        is_work_time = cct.get_work_time_duration()

        if self.realtime and self.current_code and is_work_time or self._debug_realtime:
            self._start_realtime_process(self.current_code)
        else:
            self._stop_realtime_process()
            # 清理今天的数据（保留历史日 K）
            if not self.day_df.empty and cct.get_work_time_duration():
                today_str = pd.Timestamp.today().strftime('%Y-%m-%d')
                self.day_df = self.day_df[self.day_df.index < today_str]
                logger.info(f"[INFO] Real-time stopped, cleared today's:{today_str} data for {self.current_code}")
    
    def reset_kline_view():
        vb = self.kline_plot.getViewBox()
        vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, lambda: vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=False))


    def _start_realtime_process(self, code):
        # 停止旧进程
        if self.realtime_process and self.realtime_process.is_alive():
            self.realtime_process.terminate()
            self.realtime_process.join()

        # 启动新进程
        self.realtime_process = Process(
            target=realtime_worker_process,
            args=(code, self.realtime_queue,self.stop_flag,self.log_level,self._debug_realtime),
            daemon=False
        )
        self.realtime_process.start()

    def _stop_realtime_process(self):
        if self.realtime_process and self.realtime_process.is_alive():
            self.realtime_process.terminate()
            self.realtime_process.join()
            self.realtime_process = None


    def _poll_realtime_queue(self):
        if not hasattr(self, "_closing") or getattr(self, "_closing", False):
            logger.debug(f'self._closing :{getattr(self, "_closing", False)}')
            return  # 窗口正在关闭，不再处理队列
        # latest_updates = {}  # key: code, value: (tick_df, today_bar)
        while True:
            try:
                code, tick_df, today_bar = self.realtime_queue.get_nowait()
            except queue.Empty:
                break
            except (EOFError, OSError):
                logger.warning("Realtime queue closed unexpectedly")
                break
            except Exception as e:
                logger.exception("Unexpected error in realtime queue")
                break

            try:
                # GUI 更新加保护
                if self.isVisible():  # 确保窗口未关闭
                    self.on_realtime_update(code, tick_df, today_bar)
                    logger.debug(f'on_realtime_update today_bar:\n {today_bar}')
            except RuntimeError as e:
                logger.warning(f"GUI update skipped: {e}")
            except Exception:
                logger.exception("Error in on_realtime_update")

    def _on_initial_loaded(self, code, day_df, tick_df):
        if code != self.current_code:
            return

        # ⚡ 过滤掉今天的数据，只保留过去的日 K
        today_str = pd.Timestamp.today().strftime('%Y-%m-%d')
        is_intraday = (
            self.realtime
            and cct.get_work_time_duration() 
        )

        if is_intraday or self._debug_realtime:
            day_df = day_df[day_df.index < today_str]

        datetime_index = pd.to_datetime(day_df.index)
        day_df.index = datetime_index.strftime('%Y-%m-%d')
        self.day_df = day_df.copy()
        # render_charts 时只传历史日 K，tick_df 用于 intraday 图，不绘制今天 K
        with timed_ctx("render_charts", warn_ms=50):
            self.render_charts(code, self.day_df, tick_df)

        # 启动 realtime
        if self.realtime and cct.get_work_time_duration() or self._debug_realtime:
            self._start_realtime_process(code)


    def on_realtime_update(self, code, tick_df, today_bar):
        if not self._debug_realtime and (not self.realtime or code != self.current_code or today_bar.empty or not cct.get_work_time_duration()):
            # logger.info(f'on_realtime_update today_bar.iloc[0] : {today_bar.iloc[0]}')
            return

        datetime_index = pd.to_datetime(today_bar.index)
        today_bar.index = datetime_index.strftime('%Y-%m-%d')
        self.day_df
        today_idx = today_bar.index[0]
        # 获取 day_df 最后一天日期
        last_day = self.day_df.index[-1] if not self.day_df.empty else None

        # 计算交易日间隔
        trade_gap = cct.get_trade_day_distance(last_day, today_idx) if last_day else None
        logger.debug(f'trade_gap: {trade_gap}')
        # 第二天开盘（交易日不同），自动初始化 today_bar
        # if last_day is None or (trade_gap is not None and trade_gap > 1):
        #     self._on_initial_loaded()
        #     print(f"[INFO] New trading day detected: {today_idx}, today_bar appended trade_gap:{trade_gap}")
        #     return
        # elif last_day == today_idx:
        if last_day == today_idx:
            # 当天更新最后一行
            # 先按 day_df 列对齐 today_bar
            # 直接重命名列
            # today_bar = today_bar.rename(columns={'volume': 'vol'})
            # today_bar_renamed
            today_bar['vol'] = today_bar['volume']
            cols_match = ['open', 'high', 'low', 'close', 'vol', 'volume','amount', 'code']
            # 先从 today_bar 里取需要的列（不存在的填 NaN）
            today_row = today_bar.iloc[0].reindex(cols_match)
            today_row['code'] = code

            # 如果 amount 列存在但为空，用 (high+low)/2 * volume 填充
            if 'amount' in today_row:
                if pd.isna(today_row['amount']):
                    if 'vol' in today_row and not pd.isna(today_row['vol']):
                        today_row['amount'] = round((today_row['high'] + today_row['low']) / 2 * today_row['vol'], 1)

            # code 列保持原样（如果 day_df 有默认值或 NaN 就不动）
            # 数值列精度处理
            num_cols = ['open', 'high', 'low', 'close']
            for col in num_cols:
                if col in today_row:
                    today_row[col] = round(pd.to_numeric(today_row[col], errors='coerce'), 2)
            # 更新最后一行
            today_row_new = today_row[self.day_df.columns]  # 强制顺序和 day_df 对齐
            logger.debug(f' today_row\n: {today_row} today_row_new:{today_row_new}')
            self.day_df.iloc[-1] = today_row_new
            # self.day_df.iloc[-1] = today_bar.iloc[0]
        else:
            self.day_df = pd.concat([self.day_df, today_bar])

        # 渲染图表
        self.render_charts(code, self.day_df, tick_df)




    def _init_theme_selector(self):
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Theme:"))

        self.theme_cb = QComboBox()
        self.theme_cb.addItems(['light', 'dark'])
        self.theme_cb.setCurrentText(self.qt_theme)
        self.theme_cb.currentTextChanged.connect(self.on_theme_changed)

        self.toolbar.addWidget(self.theme_cb)


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
        """窗口关闭统一退出清理"""
        self._closing = True
        # 1️⃣ 停止实时数据进程
        # 1️⃣ 通知子进程退出
        if hasattr(self, 'stop_flag'):
            self.stop_flag.value = False
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = False

        # 2️⃣ 停止 realtime_process
        if getattr(self, 'realtime_process', None):
            if self.realtime_process.is_alive():
                self.realtime_process.join(timeout=2)
                if self.realtime_process.is_alive():
                    logger.info("realtime_process 强制终止")
                    self.realtime_process.terminate()
                    self.realtime_process.join()
            self.realtime_process = None
        # 当 GUI 关闭时，触发 stop_event
        stop_event.set()

        # 5️⃣ 保存窗口位置
        self.save_window_position_qt(self, "TradeVisualizer")

        # 6️⃣ 调用父类 closeEvent
        super().closeEvent(event)


    def load_stock_list(self):
        """Load stocks from df_all if available, otherwise from signal history"""
        if not self.df_all.empty:
            self.update_stock_table(self.df_all)
        elif not self.df_cache.empty:
            self.update_stock_table(self.df_cache)
        else:
            # Fallback to signal history
            df = self.logger.get_signal_history_df()
            if not df.empty and 'code' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values(by='date', ascending=False)
                unique_stocks = df[['code', 'name']].drop_duplicates()
                # Create a minimal df_all structure
                fallback_df = unique_stocks.copy()
                for col in self.headers:
                    if col not in ['code' , 'name']:
                        fallback_df[col] = 0
                self.update_stock_table(fallback_df)
    
    def update_stock_table(self, df):
        """Update table with df_all data"""
        self.stock_table.setSortingEnabled(False)
        self.stock_table.setRowCount(0)
        
        if df.empty:
            return
        
        # Filter required columns
        required_cols = ['code', 'name']
        # optional_cols = ['Rank', 'percent']
        optional_cols = [col for col in self.headers if col not in required_cols]
        logger.info(f'optional_cols: {optional_cols}')
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
            
            # code_name_map / code_info_map 之前的逻辑保持
            self.code_name_map[stock_code] = stock_name
            self.code_info_map[stock_code] = {
                "name": stock_name,
            }
            for col in optional_cols:
                self.code_info_map[stock_code][col] = row.get(col)
            # 填表格
            # 假设 row_position 已经确定
            # required_cols 已经处理过 code / name，如果可选列从列索引 len(required_cols) 开始
            # 遍历可选列填表
            for idx, col in enumerate(optional_cols, start=len(required_cols)):
                val = row.get(col)
                item = QTableWidgetItem()

                # 空值 / 类型处理
                if pd.notnull(val):
                    if isinstance(val, (int, float)):
                        item.setData(Qt.ItemDataRole.DisplayRole, val)
                    else:
                        item.setData(Qt.ItemDataRole.DisplayRole, str(val))
                else:
                    # 默认值
                    if col in ['Rank']:
                        item.setData(Qt.ItemDataRole.DisplayRole, 0)
                    else:
                        item.setData(Qt.ItemDataRole.DisplayRole, 0.0)

                # -------------------------
                # 可扩展列特殊显示规则
                # -------------------------
                if col == 'percent' and pd.notnull(val):
                    val_float = float(val)
                    if val_float > 0:
                        item.setForeground(QColor('red'))
                    elif val_float < 0:
                        item.setForeground(QColor('green'))

                # 如果后续还有别的列需要颜色逻辑，可以继续加 elif col == 'xxx'

                # 填入表格
                self.stock_table.setItem(row_position, idx, item)


        
        self.stock_table.setSortingEnabled(True)
        self.stock_table.resizeColumnsToContents()

    def on_table_cell_clicked(self, row, column):
        code_item = self.stock_table.item(row, 0)
        if code_item:
            code = code_item.data(Qt.ItemDataRole.UserRole)
            if code:
                self._clicked_change = True
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
                if  code != self.current_code:  # 只有 code 不同才加载
                    self.load_stock_by_code(code)
                    # 判断是不是鼠标点击：currentItemChanged 会在 cellClicked 之后触发
                    if getattr(self, "_clicked_change", False):
                        self._clicked_change = False
                        if self.tdx_enabled:
                            try:
                                self.sender.send(code)
                            except Exception as e:
                                print(f"Error sending stock code: {e}")

    def update_df_all(self, df):
        """Update df_all and refresh table"""
        self.df_all = df.copy() if not df.empty else pd.DataFrame()
        self.update_stock_table(self.df_all)

    def update_df_all(self, df=None):
        """
        更新 df_all 并刷新表格
        - df: 如果传入 DataFrame，则刷新缓存
        - code: 如果传入 code，则只刷新表格对应 code，数据用缓存
        """
        if df is not None:
            # 更新缓存
            self.df_cache = df.copy() if not df.empty else pd.DataFrame()
            self.df_all = self.df_cache
        self.update_stock_table(self.df_all)


    def _capture_view_state(self):
        """在切换数据前，捕获当前的缩放视角（相对于末尾）"""
        if not hasattr(self, 'day_df') or self.day_df.empty:
            return
        try:
            vb = self.kline_plot.getViewBox()
            view_rect = vb.viewRect()
            total = len(self.day_df)
            
            # 计算可见窗口距离末尾的根数
            # 如果看的是最后 100 根，那么 last_n 就是 100
            self._prev_last_n = total - view_rect.left()
            
            # 计算可见区域内的价格波动比例
            # 取旧数据在当前视野内的最高/最低
            v_start, v_end = int(max(0, view_rect.left())), int(min(total, view_rect.right()))
            visible_old = self.day_df.iloc[v_start:v_end]
            if not visible_old.empty:
                old_h = visible_old['high'].max()
                old_l = visible_old['low'].min()
                old_rng = old_h - old_l if old_h > old_l else 1.0
                
                # 缩放因子：视图高度 / 价格区间
                self._prev_y_zoom = view_rect.height() / old_rng
                # 相对中心点：(视图中心 - 价格最低) / 价格区间
                self._prev_y_center_rel = (view_rect.center().y() - old_l) / old_rng
            else:
                self._prev_y_zoom = None
        except Exception as e:
            logger.debug(f"Capture state failed: {e}")

    def load_stock_by_code(self, code):
        # ① 在清空/加载前捕获状态
        self._capture_view_state()

        self.current_code = code
        self.kline_plot.setTitle(f"Loading {code}...")

        # ① 切 code 一定先停 realtime
        # ---- 1. 停止旧的 realtime worker（如果存在）----
        if self.realtime_process:
            # 停止旧的实时进程（如果存在）
            self._stop_realtime_process()

        # ② 加载历史
        with timed_ctx("DataLoaderThread", warn_ms=800):
            self.loader = DataLoaderThread(
                code,
                self.hdf5_mutex,
                resample=self.resample
            )
        with timed_ctx("data_loaded", warn_ms=50):
            self.loader.data_loaded.connect(self._on_initial_loaded)
        with timed_ctx("start", warn_ms=800):
            self.loader.start()

        # ---- 3. 如果开启 realtime，再启动 realtime worker ----
        with timed_ctx("start_realtime_worker", warn_ms=800):
            if self.realtime and cct.get_work_time_duration() or self._debug_realtime:
                self._start_realtime_process(code)
        if logger.level == LoggerFactory.DEBUG:
            print_timing_summary(top_n=6)

    
    # def render_charts_opt(self, code, day_df, tick_df):
    def render_charts(self, code, day_df, tick_df):
        """
        Render full charts:
          - Daily K-line + MA5/10/20 + Bollinger + Signals
          - Volume + Volume MA5
          - Realtime ghost candle
          - Intraday Tick plot + avg line + pre_close
          - Theme aware
          - Signals arrows on top
        """
        if day_df.empty:
            self.kline_plot.setTitle(f"{code} - No Data")
            self.tick_plot.setTitle("No Tick Data")
            # 清理旧图形，防止切股后还有残留
            self.kline_plot.clear()
            self.tick_plot.clear()
            if hasattr(self, 'volume_plot'):
                self.volume_plot.clear()
            # 清除缓存的 Items
            for attr in ['candle_item', 'date_axis', 'vol_up_item', 'vol_down_item', 
                        'ma5_curve', 'ma10_curve', 'ma20_curve', 'upper_curve', 'lower_curve',
                        'vol_ma5_curve', 'signal_scatter', 'tick_curve', 'avg_curve', 'pre_close_line', 'ghost_candle']:
                if hasattr(self, attr):
                    delattr(self, attr)
            return

        # --- 状态判断 ---
        is_new_stock = not hasattr(self, '_last_rendered_code') or self._last_rendered_code != code
        self._last_rendered_code = code

        # --- 标题 ---
        info = self.code_info_map.get(code, {})
        title_parts = [code]
        for k, fmt in [('name', '{}'), ('Rank', 'Rank: {}'), ('percent', '{:+.2f}%'),
                       ('win', 'win: {}'), ('slope', 'slope: {:.1f}%'), ('volume', 'vol: {:.1f}')]:
            v = info.get(k)
            if v is not None:
                title_parts.append(fmt.format(v))
        self.kline_plot.setTitle(" | ".join(title_parts))

        # --- 主题颜色 ---
        if self.qt_theme == 'dark':
            ma_colors = {'ma5':'b','ma10':'orange','ma20':QColor(255,255,0)}
            bollinger_colors = {'upper':QColor(139,0,0),'lower':QColor(0,128,0)}
            vol_ma_color = QColor(255,255,0)
            tick_curve_color = 'w'
            tick_avg_color = QColor(255,255,0)
            pre_close_color = 'b'
        else:
            ma_colors = {'ma5':'b','ma10':'orange','ma20':QColor(255,140,0)}
            bollinger_colors = {'upper':QColor(139,0,0),'lower':QColor(0,128,0)}
            vol_ma_color = QColor(255,140,0)
            tick_curve_color = 'k'
            tick_avg_color = QColor(255,140,0)
            pre_close_color = 'b'
            
        day_df = _normalize_dataframe(day_df)

        if 'date' in day_df.columns:
            day_df = day_df.set_index('date')
        logger.debug(f'day_df.index:\n {day_df.index[-3:]}')
        day_df = day_df.sort_index()
        # day_df.index = day_df.index.normalize()   # 去掉时间
        dates = day_df.index
        x_axis = np.arange(len(day_df))

        # ----------------- 设置底部轴 -----------------
        if not hasattr(self, 'date_axis'):
            self.date_axis = DateAxis(day_df.index, orientation='bottom')
            self.kline_plot.setAxisItems({'bottom': self.date_axis})
        else:
            self.date_axis.updateDates(day_df.index)

        # --- Candlestick ---
        ohlc_data = np.column_stack((
            x_axis,
            day_df['open'].values,
            day_df['close'].values,
            day_df['low'].values,
            day_df['high'].values
        ))

        if not hasattr(self, 'candle_item') or self.candle_item not in self.kline_plot.items:
            self.candle_item = CandlestickItem(ohlc_data, theme=self.qt_theme)
            self.kline_plot.addItem(self.candle_item)
        else:
            self.candle_item.setTheme(self.qt_theme)
            self.candle_item.setData(ohlc_data)

        # --- MA5/10/20 ---
        ma5 = day_df['close'].rolling(5).mean().values
        ma10 = day_df['close'].rolling(10).mean().values
        ma20 = day_df['close'].rolling(20).mean().values

        for attr, series, color in zip(['ma5_curve','ma10_curve','ma20_curve'],
                                       [ma5,ma10,ma20],
                                       [ma_colors['ma5'], ma_colors['ma10'], ma_colors['ma20']]):
            if not hasattr(self, attr) or getattr(self, attr) not in self.kline_plot.items:
                setattr(self, attr, self.kline_plot.plot(x_axis, series, pen=pg.mkPen(color, width=1)))
            else:
                getattr(self, attr).setData(x_axis, series)
                getattr(self, attr).setPen(pg.mkPen(color, width=1))

        # --- Bollinger ---
        std20 = day_df['close'].rolling(20).std().values
        upper_band = ma20 + 2*std20
        lower_band = ma20 - 2*std20

        for attr, series, color in [('upper_curve', upper_band, bollinger_colors['upper']),
                                    ('lower_curve', lower_band, bollinger_colors['lower'])]:
            if not hasattr(self, attr) or getattr(self, attr) not in self.kline_plot.items:
                setattr(self, attr, self.kline_plot.plot(x_axis, series, pen=pg.mkPen(color, width=2)))
            else:
                getattr(self, attr).setData(x_axis, series)
                getattr(self, attr).setPen(pg.mkPen(color, width=2))

        # ----------------- 绘制 Volume -----------------
        if 'amount' in day_df.columns:
            if not hasattr(self, 'volume_plot'):
                self.volume_plot = self.kline_widget.addPlot(row=1, col=0)
                self.volume_plot.setXLink(self.kline_plot)
                self.volume_plot.setMaximumHeight(120)
                self.volume_plot.setLabel('left', 'Volume')
                self.volume_plot.showGrid(x=True, y=True)
                self.volume_plot.setMenuEnabled(False)
            
            # 重要：不使用 clear()，而是复用 BarGraphItem
            amounts = day_df['amount'].values
            up_idx = day_df['close'] >= day_df['open']
            down_idx = day_df['close'] < day_df['open']
            
            x_vol = x_axis

            # 处理上涨柱
            if up_idx.any():
                if not hasattr(self, 'vol_up_item') or self.vol_up_item not in self.volume_plot.items:
                    self.vol_up_item = pg.BarGraphItem(x=x_vol[up_idx], height=amounts[up_idx], width=0.6, brush='r')
                    self.volume_plot.addItem(self.vol_up_item)
                else:
                    self.vol_up_item.setOpts(x=x_vol[up_idx], height=amounts[up_idx], width=0.6, brush='r')
            elif hasattr(self, 'vol_up_item'):
                self.vol_up_item.setOpts(x=[], height=[], width=0.6)

            # 处理下跌柱
            if down_idx.any():
                if not hasattr(self, 'vol_down_item') or self.vol_down_item not in self.volume_plot.items:
                    self.vol_down_item = pg.BarGraphItem(x=x_vol[down_idx], height=amounts[down_idx], width=0.6, brush='g')
                    self.volume_plot.addItem(self.vol_down_item)
                else:
                    self.vol_down_item.setOpts(x=x_vol[down_idx], height=amounts[down_idx], width=0.6, brush='g')
            elif hasattr(self, 'vol_down_item'):
                self.vol_down_item.setOpts(x=[], height=[], width=0.6)

            # 5日均量线
            ma5_vol = pd.Series(amounts).rolling(5).mean().values
            if not hasattr(self, 'vol_ma5_curve') or self.vol_ma5_curve not in self.volume_plot.items:
                self.vol_ma5_curve = self.volume_plot.plot(x_axis, ma5_vol, pen=pg.mkPen(vol_ma_color, width=1.5))
            else:
                self.vol_ma5_curve.setData(x_axis, ma5_vol)
                self.vol_ma5_curve.setPen(pg.mkPen(vol_ma_color, width=1.5))

        # --- Signals Arrows with Price Text ---
        signals = self.logger.get_signal_history_df()
        if not hasattr(self, 'signal_scatter'):
            self.signal_scatter = pg.ScatterPlotItem(size=15, pen=pg.mkPen('k'), symbol='t1', z=10)
            self.kline_plot.addItem(self.signal_scatter)
            self.signal_text_items = []
        else:
            self.signal_scatter.clear()
            for t in getattr(self, 'signal_text_items', []):
                self.kline_plot.removeItem(t)
            self.signal_text_items.clear()

        if not signals.empty:
            stock_signals = signals[signals['code'] == code]
            xs, ys, brushes = [], [], []
            date_map = {d if isinstance(d, str) else d.strftime('%Y-%m-%d'): i for i, d in enumerate(dates)}
            
            for _, row in stock_signals.iterrows():
                sig_date = str(row['date']).split()[0]
                if sig_date in date_map:
                    idx = date_map[sig_date]
                    xs.append(idx)
                    y_price = row['price'] if pd.notnull(row['price']) else day_df.iloc[idx]['close']
                    ys.append(y_price)
                    buy_signal = 'Buy' in row['action'] or '买' in row['action']
                    brushes.append(pg.mkBrush('r') if buy_signal else pg.mkBrush('g'))
                    
                    text_item = pg.TextItem(
                        text=f"{y_price:.2f}",
                        anchor=(0.5, 1.5) if buy_signal else (0.5, -0.5),
                        color='r' if buy_signal else 'g',
                        border='k',
                        fill=(50,50,50,150)
                    )
                    text_item.setZValue(11)
                    text_item.setPos(idx, y_price)
                    self.kline_plot.addItem(text_item)
                    self.signal_text_items.append(text_item)

            if xs:
                self.signal_scatter.setData(x=xs, y=ys, brush=brushes, size=15)

        # --- Ghost Candle (实时占位) ---
        is_realtime_active = self.realtime and not tick_df.empty and (cct.get_work_time_duration() or self._debug_realtime)
        if is_realtime_active:
            current_price = float(tick_df['close'].iloc[-1])
            last_hist_date = str(day_df.index[-1]).split()[0]
            today_str = pd.Timestamp.now().strftime('%Y-%m-%d')

            if today_str > last_hist_date:
                new_x = len(day_df)
                open_p = tick_df['open'][tick_df['open'] > 0].iloc[-1] if 'open' in tick_df.columns else current_price
                low_p  = tick_df['low'][tick_df['low'] > 0].min() if 'low' in tick_df.columns else current_price
                high_p = tick_df['high'][tick_df['high'] > 0].max() if 'high' in tick_df.columns else current_price

                ghost_ohlc = np.array([[new_x, open_p, current_price, low_p, high_p]], dtype=float)

                if not hasattr(self, 'ghost_candle') or self.ghost_candle not in self.kline_plot.items:
                    self.ghost_candle = CandlestickItem(ghost_ohlc, theme=self.qt_theme)
                    self.kline_plot.addItem(self.ghost_candle)
                else:
                    self.ghost_candle.setTheme(self.qt_theme)
                    self.ghost_candle.setData(ghost_ohlc)
            elif hasattr(self, 'ghost_candle'):
                self.kline_plot.removeItem(self.ghost_candle)
                delattr(self, 'ghost_candle')
        else:
            if hasattr(self, 'ghost_candle'):
                self.kline_plot.removeItem(self.ghost_candle)
                delattr(self, 'ghost_candle')

        # --- Tick Plot (Intraday) ---
        if not tick_df.empty:
            prices = tick_df['close'].values
            x_ticks = np.arange(len(prices))
            pre_close = tick_df['llastp'].iloc[-1] if 'llastp' in tick_df.columns else tick_df['pre_close'].iloc[-1] if 'pre_close' in tick_df.columns else prices[0]

            if not hasattr(self, 'tick_curve') or self.tick_curve not in self.tick_plot.items:
                self.tick_curve = self.tick_plot.plot(x_ticks, prices, pen=pg.mkPen(tick_curve_color, width=2))
            else:
                self.tick_curve.setData(x_ticks, prices)
                self.tick_curve.setPen(pg.mkPen(tick_curve_color, width=2))

            # 均价线
            if 'amount' in tick_df.columns and 'volume' in tick_df.columns:
                cum_amount = tick_df['amount'].cumsum()
                cum_volume = tick_df['volume'].cumsum()
                avg_prices = np.where(cum_volume>0, cum_amount/cum_volume, prices)
            else:
                avg_prices = pd.Series(prices).expanding().mean().values

            if not hasattr(self, 'avg_curve') or self.avg_curve not in self.tick_plot.items:
                self.avg_curve = self.tick_plot.plot(x_ticks, avg_prices, pen=pg.mkPen(tick_avg_color, width=1.5))
            else:
                self.avg_curve.setData(x_ticks, avg_prices)
                self.avg_curve.setPen(pg.mkPen(tick_avg_color, width=1.5))

            # pre_close 虚线
            if not hasattr(self, 'pre_close_line') or self.pre_close_line not in self.tick_plot.items:
                self.pre_close_line = self.tick_plot.addLine(y=pre_close, pen=pg.mkPen(pre_close_color, style=Qt.PenStyle.DashLine))
            else:
                self.pre_close_line.setValue(pre_close)
                self.pre_close_line.setPen(pg.mkPen(pre_close_color, style=Qt.PenStyle.DashLine))

            pct_change = (prices[-1]-pre_close)/pre_close*100 if pre_close!=0 else 0
            self.tick_plot.setTitle(f"Intraday: {prices[-1]:.2f} ({pct_change:.2f}%)")
            self.tick_plot.showGrid(x=False, y=True, alpha=0.5)

        # --- 范围处理（缩放自适应） ---
        if is_new_stock:
            vb = self.kline_plot.getViewBox()
            # 检查是否有保存的旧状态
            if hasattr(self, '_prev_last_n') and hasattr(self, '_prev_y_zoom') and self._prev_y_zoom is not None:
                # 1. 应用 X 轴：根据保存的距离末尾的根数
                new_total = len(day_df)
                target_left = max(0, new_total - self._prev_last_n)
                target_right = new_total + (2 if is_realtime_active else 0)
                
                # 2. 应用 Y 轴：计算新股票在目标 X 范围内的价格区间
                visible_new = day_df.iloc[int(target_left):]
                if not visible_new.empty:
                    new_h = visible_new['high'].max()
                    new_l = visible_new['low'].min()
                    new_rng = new_h - new_l if new_h > new_l else 1.0
                    
                    # 按比例恢复高度和中心位置
                    target_h = new_rng * self._prev_y_zoom
                    target_y_center = new_l + (new_rng * self._prev_y_center_rel)
                    
                    # 设置视图，padding=0 保证精确匹配
                    vb.setRange(xRange=(target_left, target_right), 
                                yRange=(target_y_center - target_h/2, target_y_center + target_h/2),
                                padding=0)
                else:
                    self.kline_plot.autoRange()
            else:
                # 若无状态或首次打开，显示最后 100 根
                n = len(day_df)
                vb.setRange(xRange=(max(0, n-100), n+1))
                vb.enableAutoRange(axis=pg.ViewBox.YAxis)
            
            # 切换完股票后清理状态，防止实时更新干扰
            for attr in ['_prev_last_n', '_prev_y_zoom', '_prev_y_center_rel']:
                if hasattr(self, attr):
                    delattr(self, attr)
        else:
            # 实时更新阶段不强制重置坐标轴，除非此时还没有 view
            pass
        # ------------------------
        # ① 保存上一次 resample
        # ------------------------
        last_resample = getattr(self, "_last_resample", None)
        # 仅在 resample 切换时才执行
        if last_resample != self.resample:
            if last_resample is not None:
                # 上一次存在且与当前不同，刷新 K 线视图
                self._reset_kline_view()

            # 更新 _last_resample
            self._last_resample = self.resample



    # def render_charts_old(self, code, day_df, tick_df):
    #     if day_df.empty:
    #         self.kline_plot.setTitle(f"{code} - No Data")
    #         return

    #     self.kline_plot.clear()
    #     self.tick_plot.clear()

    #     info = self.code_info_map.get(code, {})

    #     name = info.get("name", "")
    #     rank = info.get("Rank", None)
    #     percent = info.get("percent", None)
    #     win = info.get("win", None)
    #     slope = info.get("slope", None)
    #     volume = info.get("volume", None)

    #     title_parts = [code]
    #     if name:
    #         title_parts.append(name)

    #     if rank is not None:
    #         title_parts.append(f"Rank: {int(rank)}")

    #     if percent is not None:
    #         pct_str = f"{percent:+.2f}%"
    #         title_parts.append(pct_str)

    #     if win is not None:
    #         title_parts.append(f"win: {int(win)}")
    #     if slope is not None:
    #         slope_str = f"{slope:.1f}%"
    #         title_parts.append(f"slope: {slope:.1f}%")
    #     if volume is not None:
    #         title_parts.append(f"vol: {volume:.1f}")

    #     title_text = " | ".join(title_parts)

    #     self.kline_plot.setTitle(title_text)


    #     # --- A. Render Daily K-Line ---
    #     day_df = day_df.sort_index()
    #     dates = day_df.index
    #     # Convert date index to integers 0..N
    #     x_axis = np.arange(len(day_df))
        
    #     # Create OHLC Data for CandlestickItem
    #     # ohlc_data = []
    #     # for i, (idx, row) in enumerate(day_df.iterrows()):
    #     #     ohlc_data.append((i, row['open'], row['close'], row['low'], row['high']))
        
    #     x_axis = np.arange(len(day_df))
    #     ohlc_data = np.column_stack((
    #         x_axis,
    #         day_df['open'].values,
    #         day_df['close'].values,
    #         day_df['low'].values,
    #         day_df['high'].values
    #     ))
        
    #     # # Draw Candles
    #     # candle_item = CandlestickItem(ohlc_data)
    #     # self.kline_plot.addItem(candle_item)
    #     candle_item = CandlestickItem(
    #         ohlc_data,
    #         theme=self.qt_theme
    #     )
    #     self.kline_plot.addItem(candle_item)
        
    #     # Draw Signals (Arrows)
    #     signals = self.logger.get_signal_history_df()
    #     if not signals.empty:
    #         stock_signals = signals[signals['code'] == code]
    #         if not stock_signals.empty:
    #             arrow_x = []
    #             arrow_y = []
    #             brushes = []
                
    #             # Align signals to x-axis indices
    #             date_map = {
    #                 d if isinstance(d, str) else d.strftime('%Y-%m-%d'): i
    #                 for i, d in enumerate(dates)
    #             }
    #             for _, row in stock_signals.iterrows():
    #                 sig_date_str = str(row['date']).split()[0]
    #                 if sig_date_str in date_map:
    #                     idx = date_map[sig_date_str]
    #                     arrow_x.append(idx)
                        
    #                     action = row['action']
    #                     price = row['price'] if pd.notnull(row['price']) else day_df.iloc[idx]['close']
    #                     arrow_y.append(price)
                        
    #                     if 'Buy' in action or '买' in action:
    #                         brushes.append(pg.mkBrush('r')) # Red for Buy
    #                     else:
    #                         brushes.append(pg.mkBrush('g')) # Green for Sell

    #             if arrow_x:
    #                 scatter = pg.ScatterPlotItem(x=arrow_x, y=arrow_y, size=15, 
    #                                              pen=pg.mkPen('k'), brush=brushes, symbol='t1')
    #                 self.kline_plot.addItem(scatter)

    #     if 'close' in day_df.columns:
    #         # --- MA5 / MA10 ---
    #         ma5 = day_df['close'].rolling(5).mean()
    #         ma10 = day_df['close'].rolling(10).mean()
    #         self.kline_plot.plot(x_axis, ma5.values, pen=pg.mkPen('b', width=1), name="MA5")
    #         self.kline_plot.plot(x_axis, ma10.values, pen=pg.mkPen('orange', width=1), name="MA10")
            
    #         # --- Bollinger Bands ---
    #         ma20 = day_df['close'].rolling(20).mean()
    #         std20 = day_df['close'].rolling(20).std()
    #         upper_band = ma20 + 2 * std20
    #         lower_band = ma20 - 2 * std20

    #         # self.kline_plot.plot(x_axis, ma20.values, pen=pg.mkPen('purple', width=1, style=Qt.PenStyle.DotLine))
    #         # self.kline_plot.plot(x_axis, upper_band.values, pen=pg.mkPen('grey', width=1, style=Qt.PenStyle.DashLine))
    #         # self.kline_plot.plot(x_axis, lower_band.values, pen=pg.mkPen('grey', width=1, style=Qt.PenStyle.DashLine))

    #         # 中轨颜色根据主题调整
    #         if self.qt_theme == 'dark':
    #             ma20_color = QColor(255, 255, 0)  # 黄色
    #         else:
    #             ma20_color = QColor(255, 140, 0)  # 深橙色 (DarkOrange)
            
    #         self.kline_plot.plot(x_axis, ma20.values,
    #                              pen=pg.mkPen(ma20_color, width=2))

    #         # 上轨 深红色加粗
    #         self.kline_plot.plot(x_axis, upper_band.values,
    #                              pen=pg.mkPen(QColor(139, 0, 0), width=2))  # DarkRed

    #         # 下轨 深绿色加粗
    #         self.kline_plot.plot(x_axis, lower_band.values,
    #                              pen=pg.mkPen(QColor(0, 128, 0), width=2))  # DarkGreen

    #         # --- 自动居中显示 ---
    #         self.kline_plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
    #         self.kline_plot.autoRange()


    #     # --- volume plot ---
    #     if 'amount' in day_df.columns:
    #         # 创建 volume 子图
    #         if not hasattr(self, 'volume_plot'):
    #             self.volume_plot = self.kline_widget.addPlot(row=1, col=0)
    #             self.volume_plot.showGrid(x=True, y=True)
    #             self.volume_plot.setMaximumHeight(120)
    #             self.volume_plot.setLabel('left', 'Volume')
    #             self.volume_plot.setXLink(self.kline_plot)  # x 轴同步主图
    #             self.volume_plot.setMenuEnabled(False)
    #         else:
    #             # 清空之前的数据，防止重叠
    #             self.volume_plot.clear()
            
    #         x_axis = np.arange(len(day_df))
    #         amounts = day_df['amount'].values

    #         # 涨的柱子
    #         up_idx = day_df['close'] >= day_df['open']
    #         if up_idx.any():
    #             bg_up = pg.BarGraphItem(
    #                 x=x_axis[up_idx],
    #                 height=amounts[up_idx],
    #                 width=0.6,
    #                 brush='r'
    #             )
    #             self.volume_plot.addItem(bg_up)

    #         # 跌的柱子
    #         down_idx = day_df['close'] < day_df['open']
    #         if down_idx.any():
    #             bg_down = pg.BarGraphItem(
    #                 x=x_axis[down_idx],
    #                 height=amounts[down_idx],
    #                 width=0.6,
    #                 brush='g'
    #             )
    #             self.volume_plot.addItem(bg_down)
            
    #         # 添加5日均量线
    #         ma5_volume = pd.Series(amounts).rolling(5).mean()
    #         if self.qt_theme == 'dark':
    #             vol_ma_color = QColor(255, 255, 0)  # 黄色
    #         else:
    #             vol_ma_color = QColor(255, 140, 0)  # 深橙色
            
    #         self.volume_plot.plot(x_axis, ma5_volume.values,
    #                              pen=pg.mkPen(vol_ma_color, width=1.5),
    #                              name='MA5')

    #     # --- B. Render Intraday Trick ---
    #     if not tick_df.empty:
    #         try:
    #             # 1. Prepare Data
    #             df_ticks = tick_df.copy()
                
    #             # Handle MultiIndex: code, ticktime
    #             if isinstance(df_ticks.index, pd.MultiIndex):
    #                 # Sort by ticktime just in case
    #                 df_ticks = df_ticks.sort_index(level='ticktime')
    #                 prices = df_ticks['close'].values
    #             else:
    #                 prices = df_ticks['close'].values

    #             # Get Params
    #             current_price = prices[-1]

    #             # Attempt to get pre_close (llastp)
    #             if 'llastp' in df_ticks.columns:
    #                 pre_close = float(df_ticks['llastp'].iloc[-1]) 
    #             elif 'pre_close' in df_ticks.columns:
    #                 pre_close = float(df_ticks['pre_close'].iloc[-1])
    #             else:
    #                 pre_close = prices[0] 
                
    #             open_p = 0
    #             if 'open' in df_ticks.columns:
    #                 # Avoid 0 values if possible
    #                 opens = df_ticks['open'][df_ticks['open'] > 0]
    #                 if not opens.empty:
    #                     open_p = opens.iloc[-1]
    #                 else:
    #                     open_p = prices[0]
    #             else:
    #                 open_p = prices[0]

    #             low_p = prices.min() 
    #             if 'low' in df_ticks.columns:
    #                 mins = df_ticks['low'][df_ticks['low'] > 0]
    #                 if not mins.empty:
    #                     l_val = mins.min()
    #                     if l_val < low_p: low_p = l_val

    #             high_p = prices.max()
    #             if 'high' in df_ticks.columns:
    #                 maxs = df_ticks['high'][df_ticks['high'] > 0]
    #                 if not maxs.empty:
    #                     h_val = maxs.max()
    #                     if h_val > high_p: high_p = h_val
                
    #             # 2. Update Ghost Candle on Day Chart
    #             day_dates = day_df.index
    #             last_hist_date_str = ""
    #             if not day_dates.empty:
    #                 last_hist_date_str = str(day_dates[-1]).split()[0]
                
    #             today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
                
    #             if self.realtime and cct.get_work_time_duration() and today_str > last_hist_date_str or self._debug_realtime:
    #                 new_x = len(day_df)
    #                 ghost_data = [(new_x, open_p, current_price, low_p, high_p)]
    #                 ghost_candle = CandlestickItem(ghost_data)
    #                 self.kline_plot.addItem(ghost_candle)
                    
    #                 text = pg.TextItem(f"{current_price}", anchor=(0, 1),
    #                                    color='r' if current_price>pre_close else 'g')
    #                 text.setPos(new_x, high_p)
    #                 self.kline_plot.addItem(text)


    #             # 3. Render Tick Plot (Curve)
    #             pct_change = ((current_price - pre_close) / pre_close * 100) if pre_close != 0 else 0
    #             self.tick_plot.setTitle(f"Intraday: {current_price:.2f} ({pct_change:.2f}%)")
                
    #             # X-axis: 0 to N
    #             x_ticks = np.arange(len(prices))
                
    #             # Draw Pre-close (Dash Blue)
    #             self.tick_plot.addLine(y=pre_close, pen=pg.mkPen('b', style=Qt.PenStyle.DashLine, width=1))
                
    #             # # Draw Price Curve
    #             if self.qt_theme == 'dark':
    #                 curve_color = 'w'  # 白色线条
    #                 pre_close_color = 'b'
    #                 avg_color = QColor(255, 255, 0)  # 黄色均价线
    #             else:
    #                 curve_color = 'k'
    #                 pre_close_color = 'b'
    #                 avg_color = QColor(255, 140, 0)  # 深橙色均价线 (DarkOrange)
                
    #             curve_pen = pg.mkPen(curve_color, width=2)
    #             self.tick_plot.plot(x_ticks, prices, pen=curve_pen, name='Price')
    #             self.tick_plot.addLine(y=pre_close, pen=pg.mkPen(pre_close_color, style=Qt.PenStyle.DashLine))

    #             # 计算并绘制分时均价线
    #             # 分时均价 = 累计成交金额 / 累计成交量
    #             if 'amount' in df_ticks.columns and 'volume' in df_ticks.columns:
    #                 # 使用 amount 和 volume 计算均价
    #                 cum_amount = df_ticks['amount'].cumsum()
    #                 cum_volume = df_ticks['volume'].cumsum()
    #                 # 避免除以零
    #                 avg_prices = np.where(cum_volume > 0, cum_amount / cum_volume, prices)
    #             elif 'close' in df_ticks.columns:
    #                 # 如果没有成交量数据，使用价格的累计平均
    #                 avg_prices = pd.Series(prices).expanding().mean().values
    #             else:
    #                 avg_prices = None
                
    #             if avg_prices is not None:
    #                 avg_pen = pg.mkPen(avg_color, width=1.5, style=Qt.PenStyle.SolidLine)
    #                 self.tick_plot.plot(x_ticks, avg_prices, pen=avg_pen, name='Avg Price')
                
    #             # Add Grid
    #             self.tick_plot.showGrid(x=False, y=True, alpha=0.5)

    #         except Exception as e:
    #             print(f"Error rendering tick data: {e}")
    #             import traceback
    #             traceback.print_exc()

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

def main(initial_code='000002',stop_flag=None,log_level=None,debug_realtime=False):
    # --- 1. 尝试成为 Primary Instance ---
        # logger = LoggerFactory.getLogger()
    if log_level is not None:
        logger.setLevel(log_level.value)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    stop_flag = stop_flag if stop_flag else mp.Value('b', True)   # 出厂运行
    try:
        server_socket.bind((IPC_HOST, IPC_PORT))
        server_socket.listen(1)
        is_primary_instance = True
        print(f"Listening on {IPC_HOST}:{IPC_PORT}")
    except OSError:
        is_primary_instance = False
        print(f"Listening 被占用 {IPC_HOST}:{IPC_PORT}")

    # --- 2. Secondary Instance: 发送 code 给 Primary Instance 后退出 ---
    if not is_primary_instance:
        if len(sys.argv) > 1 or initial_code is not None:
            code_to_send = initial_code if initial_code is not None else sys.argv[1]
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.connect((IPC_HOST, IPC_PORT))
                client_socket.send(code_to_send.encode('utf-8'))
                client_socket.close()
                # print(f"Sent command: {code_to_send}")
            except Exception as e:
                print(f"Failed to send command: {e}")
        sys.exit(0)

    # --- 3. Primary Instance: 启动 GUI ---
    app = QApplication(sys.argv)
    window = MainWindow(stop_flag,log_level,debug_realtime)
    start_code = initial_code
    # 启动监听线程，处理 socket 消息
    listener = CommandListenerThread(server_socket)
    listener.command_received.connect(window.load_stock_by_code)
    listener.dataframe_received.connect(window.update_df_all)
    # listener.command_received.connect(lambda: window.raise_())
    # listener.command_received.connect(lambda: window.activateWindow())
    listener.start()

    window.show()
    # 如果 exe 启动时带了参数
    if start_code is not None:
        window.load_stock_by_code(start_code)
    elif len(sys.argv) > 1:
        start_code = sys.argv[1]
        if len(start_code) in (6, 8):
            window.load_stock_by_code(start_code)
    ret = app.exec()  # 阻塞 Qt 主循环
    # 确保所有后台进程被杀
    stop_flag.value = False
    window.close()  # 触发 closeEvent
    sys.exit(ret)


if __name__ == "__main__":
    # logger.setLevel(LoggerFactory.INFO)
    import argparse
    LOG_LEVEL_MAP = {
        "debug": LoggerFactory.DEBUG,
        "info": LoggerFactory.INFO,
        "warning": LoggerFactory.WARNING,
        "error": LoggerFactory.ERROR,
    }

    def parse_args():
        parser = argparse.ArgumentParser(description="Realtime Stock Visualizer")

        parser.add_argument(
            "-log",
            "--log-level",
            default="info",
            choices=LOG_LEVEL_MAP.keys(),
            help="Log level: debug / info / warning / error"
        )

        parser.add_argument(
            "-realtime",
            action="store_true",
            help="Force realtime mode even outside trading hours"
        )

        parser.add_argument(
            "-code",
            default="000002",
            help="Initial stock code"
        )

        return parser.parse_args()


    args = parse_args()

    # logger 本身
    logger.setLevel(LOG_LEVEL_MAP[args.log_level])

    # multiprocessing 共享变量
    stop_flag = mp.Value('b', True)
    log_level = mp.Value('i', LOG_LEVEL_MAP[args.log_level])

    realtime = args.realtime
    initial_code = args.code

    logger.info(
        f"Starting app | code={initial_code} "
        f"log={args.log_level} debug_realtime={realtime}"
    )

    main(
        initial_code=initial_code,
        stop_flag=stop_flag,
        log_level=log_level,
        debug_realtime=realtime
    )

    # logger.setLevel(LoggerFactory.DEBUG)
    # stop_flag =  mp.Value('b', True)   # 出厂运行
    # log_level = mp.Value('i', LoggerFactory.DEBUG)  # 'i' 表示整数
    # debug_realtime = False
    # main(initial_code='000002',stop_flag=stop_flag,log_level=log_level,debug_realtime=debug_realtime)



    # # 1. Try to become the Primary Instance
    # logger.setLevel(LoggerFactory.DEBUG)
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
