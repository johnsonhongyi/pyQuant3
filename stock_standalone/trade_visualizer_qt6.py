import sys
import os
import pandas as pd
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QSplitter, QFrame, QMessageBox, QAbstractItemView,
    QTreeWidget, QTreeWidgetItem
)
import json
import stock_logic_utils
from stock_logic_utils import ensure_parentheses_balanced, remove_invalid_conditions
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
from StrongPullbackMA5Strategy import StrongPullbackMA5Strategy
from data_utils import (
    calc_compute_volume, calc_indicators, fetch_and_process, send_code_via_pipe)
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


def recv_exact(sock, size, running_cb=None):
    buf = b""
    while len(buf) < size:
        if running_cb and not running_cb():
            raise RuntimeError("Listener stopped")
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed")
        buf += chunk
    return buf


class CommandListenerThread(QThread):
    command_received = pyqtSignal(str)
    dataframe_received = pyqtSignal(object, str)

    def __init__(self, server_socket):
        super().__init__()
        self.server_socket = server_socket
        self.running = True

    def stop(self):
        self.running = False
        try:
            self.server_socket.close()
        except Exception:
            pass
        self.wait(1000)

    def run(self):
        while self.running:
            try:
                # accept 阻塞，直到有客户端连接
                client_socket, _ = self.server_socket.accept()
                client_socket.settimeout(3.0)

                try:
                    # 前4字节协议判断
                    prefix = client_socket.recv(4)
                    if not prefix:
                        client_socket.close()
                        continue

                    if prefix == b"DATA":
                        try:
                            header = client_socket.recv(4)
                            if not header:
                                client_socket.close()
                                continue
                            size = struct.unpack("!I", header)[0]
                            payload = b""
                            while len(payload) < size:
                                chunk = client_socket.recv(size - len(payload))
                                if not chunk:
                                    break
                                payload += chunk
                            if payload:
                                msg_type, df = pickle.loads(payload)
                                self.dataframe_received.emit(df, msg_type)
                        except Exception as e:
                            print(f"[IPC] Drop DATA packet: {e}")

                    else:
                        try:
                            rest = client_socket.recv(4096)
                            text = (prefix + rest).decode("utf-8", errors="ignore").strip()
                            if text.startswith("CODE|"):
                                code = text[5:].strip()
                                if code:
                                    self.command_received.emit(code)
                            elif text:
                                self.command_received.emit(text)
                        except Exception as e:
                            print(f"[IPC] Drop CODE packet: {e}")
                finally:
                    try:
                        client_socket.close()
                    except Exception:
                        pass

            except Exception as e:
                if self.running:
                    print(f"[IPC] Listener Loop Error: {e}")
                else:
                    break
        print("[IPC] CommandListenerThread exited cleanly")



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
    # if log_level:
    #     logger = LoggerFactory.getLogger()
    #     if log_level is not None:
    #         logger.setLevel(log_level.value)
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
                    # if log_level and tick_df is None or tick_df.empty:
                    #     logger.warning(
                    #         f"[RT] tick_df EMPTY | code={code} | "
                    #         f"trade={cct.get_trade_date_status()} "
                    #         f"time={cct.get_now_time_int()}"
                    #     )
                    #     time.sleep(interval)
                    #     continue
                with timed_ctx("realtime_worker_tick_to_daily_bar", warn_ms=800):
                    today_bar = tick_to_daily_bar(tick_df)
                    # if log_level and today_bar is None or today_bar.empty:
                    #     logger.warning(
                    #         f"[RT] today_bar EMPTY | code={code} | "
                    #         f"today_bar_rows={len(today_bar)} | "
                    #         f"today_bar_cols={list(today_bar.columns)}"
                    #     )
                    #     time.sleep(interval)
                    #     continue
                    try:
                        # # queue.put((code, tick_df, today_bar))
                        # if log_level and count_debug == 0 and debug_realtime:
                        #     logger.debug(
                        #             f"[RT] tick_df | code={code} | "
                        #             f"tick_rows={len(tick_df)} | "
                        #             f"tick_cols={list(tick_df.columns)}"
                        #             f"tick={(tick_df[-3:])}"
                        #         )
                        #     # dump_path = cct.get_ramdisk_path(f"{code}_tick_{int(time.time())}.pkl")
                        #     # tick_df.to_pickle(dump_path)
                        #     logger.debug(
                        #             f"[RT] today_bar | code={code} | "
                        #             f"today_barrows={len(today_bar)} | "
                        #             f"today_bar_cols={list(today_bar.columns)}"
                        #             f"today_bar=\n{(today_bar)}"
                        #         )
                        #     # dump_path = cct.get_ramdisk_path(f"{code}_today_{int(time.time())}.pkl")
                        #     # today_bar.to_pickle(dump_path)
                        #     # count_debug += 1
                        queue.put_nowait((code, tick_df, today_bar))
                    except queue.Full:
                        pass  # 队列满了就跳过，避免卡住
        except Exception as e:
            import traceback
            traceback.print_exc()
            time.sleep(interval)  # 避免无限抛异常占用 CPU
        if stop_flag.value:
            for _ in range(interval):
                if not stop_flag.value:
                    break
                time.sleep(1)
    # print(f'stop_flag: {stop_flag.value}')

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
from PyQt6 import sip
class ScrollableMsgBox(QtWidgets.QDialog):
    """可滚动的详细信息弹窗，用于显示高密度决策日志"""
    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 400)
        self.resize(600, 500)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # 滚动区域
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        
        self.label = QtWidgets.QLabel(content)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setOpenExternalLinks(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        content_layout.addWidget(self.label)
        scroll.setWidget(content_widget)
        
        layout.addWidget(scroll)
        
        # 按钮
        btn_box = QtWidgets.QHBoxLayout()
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_box.addStretch()
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

class GlobalInputFilter(QtCore.QObject):
    """
    捕捉全窗口鼠标侧键和键盘按键
    """
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window

    def eventFilter(self, obj, event):
        # 只在主窗口活动时处理
        if not hasattr(self, 'main_window') or sip.isdeleted(self.main_window):
            return False

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
            elif key == Qt.Key.Key_Space:
                self.main_window.show_comprehensive_briefing()
                return True
            elif key == Qt.Key.Key_R:
                self.main_window._reset_kline_view()
                return True
            elif key == Qt.Key.Key_S:
                self.main_window.show_supervision_details()
                return True
            elif key == Qt.Key.Key_T:
                # 切换模拟显示
                btn = next((a for a in self.main_window.toolbar.actions() if a.text() == "模拟信号"), None)
                if btn:
                    btn.trigger()
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
    def __init__(self, stop_flag=None, log_level=None, debug_realtime=False, command_queue=None):
        super().__init__()
        self.setWindowTitle("Trade Signal Visualizer (Qt6 + PyQtGraph)")
        self.sender = StockSender(callback=None)
        self.command_queue = command_queue  # ⭐ 新增：内部指令队列
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

        # ⭐ 新增：指令队列轮询 (处理来自 MonitorTK 的直连指令)
        if self.command_queue:
            self.command_timer = QTimer()
            self.command_timer.timeout.connect(self._poll_command_queue)
            self.command_timer.start(200)  # 200ms 轮询一次，保证响应速度

        self.day_df = pd.DataFrame()
        self.df_all = pd.DataFrame()

        # ---- resample state ----
        self.resample_keys = ['d', '3d', 'w', 'm']

        if self.resample in self.resample_keys:
            self.current_resample_idx = self.resample_keys.index(self.resample)
        else:
            self.current_resample_idx = 0
            self.resample = self.resample_keys[0]

        self.select_resample = None
        # ⭐ 先初始化策略相关属性，再创建工具栏，防止 AttributeError
        # Initialize Logger with default path to ensure consistency with main program
        self.logger = TradingLogger()
        from intraday_decision_engine import IntradayDecisionEngine
        self.decision_engine = IntradayDecisionEngine() # ⭐ 内部决策引擎
        self.pullback_strat = StrongPullbackMA5Strategy(min_score=60) # ⭐ 强力回撤策略
        
        # 策略模拟开关
        self.show_strategy_simulation = True 

        # --- 1. 创建工具栏 ---
        self._init_toolbar()
        self._init_resample_toolbar()
        self._init_theme_selector()
        self._init_tdx()
        self._init_real_time()
        self._init_filter_toolbar()
        
        self.current_code = None
        self.df_all = pd.DataFrame()  # Store real-time data from MonitorTK
        self.code_name_map = {}
        self.code_info_map = {}   # ⭐ 新增

        # Main Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create a horizontal splitter for the main layout
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 1. Left Sidebar: Stock Table
        self.stock_table = QTableWidget()
        # Removed fixed maximum width to allow splitter resizing
        # self.stock_table.setMaximumWidth(300) 

        # self.stock_table.setStyleSheet("""

        # QTableWidget {
        #     background-color: transparent;
        # }

        # /* 只作用在 table 内部 */
        # QTableWidget QScrollBar:vertical {
        #     width: 6px;
        #     background: transparent;
        #     margin: 0px;
        # }

        # QTableWidget QScrollBar::handle:vertical {
        #     background: rgba(180, 180, 180, 120);
        #     min-height: 30px;
        #     border-radius: 3px;
        # }

        # QTableWidget QScrollBar::handle:vertical:hover {
        #     background: rgba(220, 220, 220, 180);
        # }

        # QTableWidget QScrollBar::add-line:vertical,
        # QTableWidget QScrollBar::sub-line:vertical {
        #     height: 0px;
        # }

        # QTableWidget QScrollBar::add-page:vertical,
        # QTableWidget QScrollBar::sub-page:vertical {
        #     background: transparent;
        # }
        # """)

        # self.stock_table.setStyleSheet(self.stock_table.styleSheet() + """
        # QTableWidget::item:hover {
        #     background: rgba(255, 255, 255, 30);
        # }
        # QTableWidget::item:selected {
        #     background: rgba(255, 215, 0, 80);
        #     color: black;
        # }
        # """)

        # self.stock_table.verticalScrollBar().setFixedWidth(6)


        self.stock_table.setStyleSheet("""
            QTableWidget {
                background-color: transparent;
            }

            /* 垂直滚动条 */
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

            /* 水平滚动条 */
            QTableWidget QScrollBar:horizontal {
                height: 6px;
                background: transparent;
                margin: 0px;
            }

            QTableWidget QScrollBar::handle:horizontal {
                background: rgba(180, 180, 180, 120);
                min-width: 30px;
                border-radius: 3px;
            }

            QTableWidget QScrollBar::handle:horizontal:hover {
                background: rgba(220, 220, 220, 180);
            }

            QTableWidget QScrollBar::add-line:horizontal,
            QTableWidget QScrollBar::sub-line:horizontal {
                width: 0px;
            }

            QTableWidget QScrollBar::add-page:horizontal,
            QTableWidget QScrollBar::sub-page:horizontal {
                background: transparent;
            }

            /* 鼠标悬停 & 选中效果 */
            QTableWidget::item:hover {
                background: rgba(255, 255, 255, 30);
            }

            QTableWidget::item:selected {
                background: rgba(255, 215, 0, 80);
                color: black;
            }
        """)

        # 设置滚动条固定大小
        self.stock_table.verticalScrollBar().setFixedWidth(6)
        self.stock_table.horizontalScrollBar().setFixedHeight(6)


        # 禁止编辑：防止误触发覆盖 Code/Name 等关键信息，只允许选择和复制
        self.stock_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # self.stock_table.setHorizontalHeaderLabels(['Code', 'Name', 'Rank', 'Percent'])
        # 列名中英文映射
        self.column_map = {
            'code': '代码', 'name': '名称', 'percent': '涨幅%', 'Rank': '排名',
            'dff': 'DFF', 'win': '连阳', 'slope': '斜率', 'volume': '虚拟量', 'power_idx': '爆发力',
            'last_action': '策略动作', 'last_reason': '决策理由', 'shadow_info': '影子比对',
            'market_win_rate': '全场胜率', 'loss_streak': '连亏次数', 'vwap_bias': '均价偏离'
        }

        real_time_cols = list(cct.real_time_cols)
        strategy_cols = ['last_action', 'last_reason', 'shadow_info', 'market_win_rate', 'loss_streak', 'vwap_bias']
        
        # 🛡️ 整合可视化所需的核心列，确保 'dff', 'Rank' 等字段始终出现在表头
        visualizer_core_cols = ['code', 'name', 'percent', 'dff', 'Rank', 'win', 'slope', 'volume', 'power_idx']
        
        # 使用去重的方式合并列
        combined_header_cols = []
        source_cols = real_time_cols if len(real_time_cols) > 4 and 'percent' in real_time_cols else visualizer_core_cols
        for c in (source_cols + visualizer_core_cols + strategy_cols):
            if c not in combined_header_cols:
                combined_header_cols.append(c)
        
        self.headers = combined_header_cols
        
        self.stock_table.setColumnCount(len(self.headers))
        
        # 使用映射显示中文表头
        display_headers = [self.column_map.get(h, h) for h in self.headers]
        self.stock_table.setHorizontalHeaderLabels(display_headers)
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
        # 排序后自动滚动到顶部
        self.stock_table.horizontalHeader().sectionClicked.connect(self.on_header_section_clicked)

        # 1️⃣ 启用自定义上下文菜单
        self.stock_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stock_table.customContextMenuRequested.connect(self.on_table_right_click)

        self.stock_table.verticalHeader().setVisible(False)
        self.main_splitter.addWidget(self.stock_table)

        # 2. Right Area: Splitter (Day K-Line + Intraday)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(right_splitter)
        
        # Set initial sizes for the main splitter (left table: 200, right charts: remaining)
        self.main_splitter.setSizes([200, 900])
        self.main_splitter.setCollapsible(0, False) # Prevent table from being completely hidden


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

        # 3. Filter Panel (Initially Hidden)
        self.filter_panel = QWidget()
        filter_layout = QVBoxLayout(self.filter_panel)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        
        # Top Controls - 按钮行
        button_row = QHBoxLayout()
        btn_manage = QPushButton("Manage")
        btn_manage.setMaximumWidth(60)
        btn_manage.clicked.connect(self.open_history_manager)
        button_row.addWidget(btn_manage)

        btn_refresh = QPushButton("R") # Refresh
        btn_refresh.setMaximumWidth(30)
        btn_refresh.clicked.connect(self.load_history_filters)
        button_row.addWidget(btn_refresh)
        button_row.addStretch()
        
        filter_layout.addLayout(button_row)
        
        # ComboBox - 过滤条件选择
        self.filter_combo = QComboBox()
        self.filter_combo.currentIndexChanged.connect(self.on_filter_combo_changed)
        filter_layout.addWidget(self.filter_combo)

        # Filter Tree - 过滤结果
        self.filter_tree = QTreeWidget()
        # from stock_feature_marker import StockFeatureMarker
        # self._filter_columns = ['code', 'name', 'rank', 'percent']  # 显示列
        # self.feature_marker = StockFeatureMarker(self.filter_tree, enable_colors=True)

        self.filter_tree.setHeaderLabels(["Filtered Results"])
        self.filter_tree.setColumnCount(1) 
        self.filter_tree.itemClicked.connect(self.on_filter_tree_item_clicked)
        # 添加键盘导航支持
        self.filter_tree.currentItemChanged.connect(self.on_filter_tree_current_changed)
        
        # 应用窄边滚动条样式，与左侧列表一致
        scrollbar_style = """
            QScrollBar:vertical {
                border: none;
                background: #2b2b2b;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """
        self.filter_tree.setStyleSheet(scrollbar_style)
        filter_layout.addWidget(self.filter_tree)
        
        self.filter_panel.setVisible(False)
        self.main_splitter.addWidget(self.filter_panel)
        
        # 设置默认分割比例（不加载保存的设置）
        # 股票列表:过滤面板:图表区域 = 400:200:800
        self.main_splitter.setSizes([400, 200, 800])

        # 安装全局事件过滤器
        self.input_filter = GlobalInputFilter(self)
        self.installEventFilter(self.input_filter)
        # Apply initial theme
        self.apply_qt_theme()

        # Load Stock List
        self.load_stock_list()

        # ⭐ Load saved window position (Restores size and location)
        self._window_pos_loaded = False   # ⭐ 必须加
        # self.load_window_position_qt(self, "trade_visualizer", default_width=1400, default_height=900)
        self.load_splitter_state()

    def showEvent(self, event):
        super().showEvent(event)

        if not self._window_pos_loaded:
            self._window_pos_loaded = True
            self.load_window_position_qt(
                self,
                "trade_visualizer",
                default_width=1400,
                default_height=900
            )


    def _init_toolbar(self):
        self.toolbar = QToolBar("Settings", self)
        self.toolbar.setObjectName("ResampleToolbar")
        action = QAction("模拟信号", self)
        action.setCheckable(True)
        action.setChecked(self.show_strategy_simulation)
        action.triggered.connect(self.on_toggle_simulation)
        self.toolbar.addAction(action)
        
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

    def on_toggle_simulation(self, checked):
        self.show_strategy_simulation = checked
        if self.current_code:
            self.render_charts(self.current_code, self.day_df, getattr(self, 'tick_df', pd.DataFrame()))


    def _reset_kline_view(self, df=None):
        """重置 K 线图视图：实现真正的“出厂设置”全览模式，两头留白不遮挡"""
        # 注意：如果被信号直接调用，df 可能是 bool (checked)，需排除
        if not isinstance(df, pd.DataFrame):
            df = getattr(self, 'day_df', pd.DataFrame())
            
        if not hasattr(self, 'kline_plot') or df.empty:
            return
            
        vb = self.kline_plot.getViewBox()
        n = len(df)
        
        # 1. 暂时启用全局自动缩放，让 pyqtgraph 找到数据边界
        vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        vb.autoRange()
        
        # 2. 手动微调 X 轴：开启“固定模式”，设置完美的全览范围
        # 左侧留 1 根，右侧留 3 根（给信号箭头和最新 ghost 留位置）
        vb.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        x_min, x_max = -1.5, n + 2.5
        vb.setRange(xRange=(x_min, x_max), padding=0)
        
        # 3. Y 轴维持自适应（基于当前的 X 范围）
        vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        vb.setAutoVisible(y=True)
        
        # 4. 强制刷新 Y 轴到当前可见最佳高度 (由于 X 已在锁定期，autoRange 只会计算 Y)
        vb.autoRange()
        
        # logger.debug(f"[VIEW] Reset to FullView: 0-{n} (Range: {x_min}-{x_max})")

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

        # 分隔符并添加监理详情按钮
        self.toolbar.addSeparator()
        self.supervision_action = QAction("🛡️监理详情", self)
        self.supervision_action.triggered.connect(self.show_supervision_details)
        self.toolbar.addAction(self.supervision_action)

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
    
    
    def show_supervision_details(self):
        """显示监理详细信息"""
        if not hasattr(self, 'current_supervision_data') or not self.current_supervision_data:
            QMessageBox.information(self, "监理详情", "暂无监理数据。请稍候或检查策略服务是否运行。")
            return

        data = self.current_supervision_data
        
        # 构建 HTML 内容
        content = f"""
        <h3>🛡️ 实时策略监理报告</h3>
        <hr>
        <p><b>股票代码:</b> {self.current_code}</p>
        <br>
        <table border="0" cellpadding="4">
            <tr>
                <td><b>市场胜率 (Win Rate):</b></td>
                <td><span style="color: {'red' if data.get('market_win_rate',0) > 50 else 'green'};">{data.get('market_win_rate', 0):.1f}%</span></td>
            </tr>
            <tr>
                <td><b>当前连亏 (Loss Streak):</b></td>
                <td>{data.get('loss_streak', 0)}</td>
            </tr>
            <tr>
                <td><b>VWAP 偏离:</b></td>
                <td>{data.get('vwap_bias', 0):+.2f}%</td>
            </tr>
        </table>
        <hr>
        <h4>🔎 最近信号详情</h4>
        <p><b>动作:</b> {data.get('last_action', 'N/A')}</p>
        <p><b>原因:</b> {data.get('last_reason', 'N/A')}</p>
        <p><b>诊断:</b> {data.get('shadow_info', 'N/A')}</p>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle(f"监理详情 - {self.current_code}")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(content)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def show_comprehensive_briefing(self):
        """[⭐极限弹窗] 一键显示综合研报信息"""
        if not self.current_code: return
        
        # 1. 基础个股信息
        info = self.code_info_map.get(self.current_code)
        if info is None and len(self.current_code) > 6:
            info = self.code_info_map.get(self.current_code[-6:])
        info = info or {}
        
        # 2. 策略监理信息
        sup = getattr(self, 'current_supervision_data', {})
        
        # 3. 影子决策 (即时计算)
        shadow = None
        if hasattr(self, 'day_df') and hasattr(self, 'tick_df'):
            shadow = self._run_realtime_strategy(self.current_code, self.day_df, self.tick_df)
            
        mwr = sup.get('market_win_rate', 0)
        m_color = "#FF4500" if mwr > 50 else "#32CD32"
        
        briefing = f"""
        <div style='font-family: Microsoft YaHei;'>
            <h2 style='color: #FFD700;'>📊 {self.current_code} 综合实战简报</h2>
            <hr>
            <table width='100%' border='0'>
                <tr>
                    <td><b>个股名称:</b> {info.get('name','N/A')}</td>
                    <td><b>全场排名:</b> <span style='color: yellow;'>{info.get('Rank','N/A')}</span></td>
                </tr>
                <tr>
                    <td><b>当日涨幅:</b> <span style='color: {'red' if info.get('percent',0)>0 else 'green'};'>{info.get('percent','0.00')}%</span></td>
                    <td><b>昨日胜率:</b> {info.get('win','N/A')}</td>
                </tr>
            </table>
            
            <h3 style='border-bottom: 1px solid #555;'>🛡️ 监理与风控</h3>
            <p><b>市场热度:</b> <span style='color: {m_color}; font-weight: bold;'>{mwr:.1f}% Win Rate</span></p>
            <p><b>账户连亏:</b> <span style='color: orange;'>{sup.get('loss_streak', 0)} 次</span></p>
            <p><b>价量偏离:</b> {sup.get('vwap_bias', 0):+.2f}% (VWAP Bias)</p>
            
            <h3 style='border-bottom: 1px solid #555;'>🤖 实时策略影子评分</h3>
        """
        
        if shadow:
            briefing += f"""
            <p><b>影子动作:</b> <span style='color: cyan; font-size: 14pt;'>{shadow.get('action', '持仓待定')}</span></p>
            <p><b>逻辑考量:</b> {shadow.get('reason', '无明确触发')}</p>
            <div style='background: #333; padding: 5px; border-radius: 3px;'>
                <b>核心指标快照:</b><br>
                {" ".join([f"• {k}: {v if not isinstance(v,float) else f'{v:.2f}'}" for k,v in shadow.get('debug',{}).items() if k!='indicators'])}
            </div>
            """
        else:
            briefing += "<p>暂无影子决策数据 (等待行情更新或检查数据源)</p>"
            
        briefing += """
            <hr>
            <p style='font-size: 9pt; color: #888;'>[快捷键提示] Space: 综述 | S: 监理 | R: 重置视图 | T: 模拟开关</p>
        </div>
        """
        
        dlg = ScrollableMsgBox(f"📈 综合简报 - {self.current_code}", briefing, self)
        dlg.exec()

    # def _start_realtime_process(self, code):
    #     # 停止旧进程
    #     if self.realtime_process and self.realtime_process.is_alive():
    #         self.realtime_process.terminate()
    #         self.realtime_process.join()

    #     # 启动新进程
    #     self.realtime_process = Process(
    #         target=realtime_worker_process,
    #         args=(code, self.realtime_queue,self.stop_flag,self.log_level,self._debug_realtime),
    #         daemon=False
    #     )
    #     self.realtime_process.start()

    def _start_realtime_process(self, code):
        # ✅ 优雅停止旧进程
        self._stop_realtime_process()

        # 重置 stop_flag
        self.stop_flag.value = True

        # 启动新进程
        self.realtime_process = Process(
            target=realtime_worker_process,
            args=(code, self.realtime_queue, self.stop_flag, self.log_level, self._debug_realtime),
            daemon=False
        )
        self.realtime_process.start()


    def _stop_realtime_process(self):
        if self.realtime_process:
            # 先停止循环
            self.stop_flag.value = False
            # 等待进程结束，最多 5 秒
            self.realtime_process.join(timeout=5)
            if self.realtime_process.is_alive():
                self.realtime_process.terminate()
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

    def apply_df_diff(self, df_diff):
        for col in df_diff.columns:
            mask = df_diff[col].notna()
            self.df_all.loc[mask, col] = df_diff.loc[mask, col]
        # self.render_table_or_charts()
        # 用 update_df_all 来刷新界面
        self.update_df_all(self.df_all)

    def _poll_command_queue(self):
        """轮询内部指令队列 (消费所有积压，只取最新数据)"""
        if not self.command_queue:
            return
        try:
            latest_full_df = None
            df_diffs = []

            while not self.command_queue.empty():
                cmd_data = self.command_queue.get_nowait()
                if isinstance(cmd_data, tuple) and len(cmd_data) == 2:
                    cmd, val = cmd_data
                    if cmd == 'SWITCH_CODE':
                        logger.info(f"Queue CMD: Switching to {val}")
                        self.load_stock_by_code(val)

                    elif cmd == 'UPDATE_DF_ALL':
                        if isinstance(val, pd.DataFrame):
                            # 全量覆盖 → 丢弃之前的增量
                            latest_full_df = val
                            df_diffs.clear()

                    elif cmd == 'UPDATE_DF_DIFF':
                        if isinstance(val, pd.DataFrame):
                            df_diffs.append(val)

            # --- 处理最新全量数据 ---
            if latest_full_df is not None:
                logger.debug(f"[Queue] Instant sync full df_all ({len(latest_full_df)} rows)")
                self.update_df_all(latest_full_df)

            # --- 处理增量数据 ---
            for diff_df in df_diffs:
                logger.debug(f"[Queue] Instant apply df diff ({len(diff_df)} rows)")
                self.apply_df_diff(diff_df)

        except Exception as e:
            logger.warning(f"Poll command queue failed: {e}")

    # def _poll_command_queue_ALL(self):
    #     """轮询内部指令队列 (优化：消费所有积压，只取最新全量数据)"""
    #     if not self.command_queue:
    #         return
        
    #     try:
    #         latest_df = None
    #         while not self.command_queue.empty():
    #             cmd_data = self.command_queue.get_nowait()
    #             if isinstance(cmd_data, tuple) and len(cmd_data) == 2:
    #                 cmd, val = cmd_data
    #                 if cmd == 'SWITCH_CODE':
    #                     logger.info(f"Queue CMD: Switching to {val}")
    #                     self.load_stock_by_code(val)
    #                 elif cmd == 'UPDATE_DF_ALL':
    #                     # 记录最新的全量数据，跳过中间过时的
    #                     if isinstance(val, pd.DataFrame):
    #                         latest_df = val
            
    #         # 处理最鲜活的一份数据
    #         if latest_df is not None:
    #             logger.debug(f"Queue CMD: Instant sync df_all ({len(latest_df)} rows)")
    #             self.update_df_all(latest_df)

    #     except Exception as e:
    #         logger.debug(f"Poll command queue failed: {e}")

    def push_stock_info(self,stock_code, row):
        """
        从 self.df_all 的一行数据提取 stock_info 并推送
        """
        try:
            stock_info = {
                "code": str(stock_code),
                "name": str(row["name"]),
                "high": str(row["high"]),
                "lastp1d": str(row["lastp1d"]),
                "percent": float(row.get("percent", 0)),
                "price": float(row.get("close", 0)),
                "volume": int(row.get("volume", 0))
            }
            # code, _ , percent,price, vol
            # 转为 JSON 字符串
            payload = json.dumps(stock_info, ensure_ascii=False)

            # ---- 根据传输方式选择 ----
            # 如果用 WM_COPYDATA，需要 encode 成 bytes 再传
            # if hasattr(self, "send_wm_copydata"):
            #     self.send_wm_copydata(payload.encode("utf-8"))

            # 如果用 Pipe / Queue，可以直接传 str
            # elif hasattr(self, "pipe"):
            #     self.pipe.send(payload)


            # 推送给异动联动（用管道/消息）
            send_code_via_pipe(payload, logger=logger)   # 假设你用 multiprocessing.Pipe
            # 或者 self.queue.put(stock_info)  # 如果是队列
            # 或者 send_code_to_other_window(stock_info) # 如果是 WM_COPYDATA
            logger.info(f"推送: {stock_info}")
            return True
        except Exception as e:
            logger.error(f"推送 stock_info 出错: {e} {row}")
            return False



    def on_signal_clicked(self, plot, points):
        """点击 K 线信号图标时触发，显示详细决策理由与指标"""
        if not points:
            return
        
        point = points[0]
        data = point.data()
        if not data:
            return

        # 构造信息
        date = data.get("date", "Unknown")
        action = data.get("action", "Unknown")
        reason = data.get("reason", "No reason")
        price = data.get("price", 0.0)
        indicators_raw = data.get("indicators", "{}")

        # 处理指标 JSON
        try:
            if isinstance(indicators_raw, str):
                indicators = json.loads(indicators_raw)
            else:
                indicators = indicators_raw
            
            # 提取关键指标美化显示
            ind_text = ""
            for k, v in indicators.items():
                if isinstance(v, float):
                    ind_text += f"• {k}: {v:.2f}\n"
                else:
                    ind_text += f"• {k}: {v}\n"
        except:
            ind_text = str(indicators_raw)

        # msg = (
        #     f"<b>日期:</b> {date}<br>"
        #     f"<b>动作:</b> <span style='color:red;'>{action}</span><br>"
        #     f"<b>价格:</b> {price:.2f}<br>"
        #     f"<b>理由:</b> {reason}<br><br>"
        #     f"<b>📊 决策指标快照:</b><br>{ind_text.replace('\n', '<br>')}"
        # )
        ind_html = ind_text.replace('\n', '<br>')
        msg = (
            f"<div style='font-family: Microsoft YaHei; font-size: 10pt;'>"
            f"<p><b>📅 日期:</b> {date}</p>"
            f"<p><b>🎬 动作:</b> <span style='color:red; font-size: 12pt;'>{action}</span></p>"
            f"<p><b>💰 价格:</b> <span style='color:#00FF00;'>{price:.2f}</span></p>"
            f"<p><b>📝 理由:</b> {reason}</p>"
            f"<hr>"
            f"<p><b>📊 决策指标快照 (可滚动查看):</b><br>{ind_html}</p>"
            f"</div>"
        )

        dlg = ScrollableMsgBox(f"🔍 信号透视: {self.current_code} ({date})", msg, self)
        dlg.exec()

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
        if today_bar is None or today_bar.empty:
            return
            
        if not self._debug_realtime and (not self.realtime or code != self.current_code or not cct.get_work_time_duration()):
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
        """Update table with df_all data (Robust column matching and index support)"""
        self.stock_table.setSortingEnabled(False)
        self.stock_table.setRowCount(0)
        
        if df.empty:
            return
        
        # 预先统一列名映射，支持大小写不同或索引形式
        cols_in_df = {c.lower(): c for c in df.columns}
        
        # Add rows
        for idx, row in df.iterrows():
            row_position = self.stock_table.rowCount()
            self.stock_table.insertRow(row_position)
            
            # ⭐ 优先从列中找 code，找不到则看 index (idx)
            raw_code = row.get('code', idx) if 'code' in cols_in_df else idx
            stock_code = str(raw_code)
            # 名称处理
            raw_name = row.get('name', '') if 'name' in cols_in_df else ''
            stock_name = str(raw_name)

            # Code
            code_item = QTableWidgetItem(stock_code)
            code_item.setData(Qt.ItemDataRole.UserRole, stock_code)
            code_item.setFlags(code_item.flags() & ~Qt.ItemFlag.ItemIsEditable) # 明确移除可编辑属性
            self.stock_table.setItem(row_position, 0, code_item)
            
            # Name
            name_item = QTableWidgetItem(stock_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable) # 明确移除可编辑属性
            self.stock_table.setItem(row_position, 1, name_item)
            
            self.code_name_map[stock_code] = stock_name
            self.code_info_map[stock_code] = {"name": stock_name}
            
            # 填入可选列
            optional_cols = [col for col in self.headers if col.lower() not in ['code', 'name']]
            for col_idx, col_name in enumerate(optional_cols, start=2):
                # 尝试大小写不敏感匹配
                real_col = cols_in_df.get(col_name.lower())
                val = row.get(real_col) if real_col else 0
                
                # ⭐ 关键修复：将数据存入 code_info_map 以供 K 线标题使用
                self.code_info_map[stock_code][col_name] = val
                
                item = QTableWidgetItem()
                if pd.notnull(val):
                    if isinstance(val, (int, float)):
                        item.setData(Qt.ItemDataRole.DisplayRole, val)
                    else:
                        item.setData(Qt.ItemDataRole.DisplayRole, str(val))
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, 0 if col_name in ['Rank'] else 0.0)

                # --- 颜色渲染 ---
                if col_name in ('percent', 'dff') and pd.notnull(val):
                    val_float = float(val)
                    if val_float > 0: item.setForeground(QColor('red'))
                    elif val_float < 0: item.setForeground(QColor('green'))
                elif col_name == 'last_action' and pd.notnull(val):
                    action_text = str(val)
                    if 'VETO' in action_text: item.setForeground(QColor(255, 140, 0))
                    elif '买' in action_text or 'Buy' in action_text: item.setForeground(QColor('red'))
                
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable) # 明确移除可编辑属性
                self.stock_table.setItem(row_position, col_idx, item)

        self.stock_table.setSortingEnabled(True)
        self.stock_table.resizeColumnsToContents()

    # 2️⃣ 处理右键事件
    def on_table_right_click(self, pos):
        item = self.stock_table.itemAt(pos)
        if not item:
            return
        
        stock_code = item.data(Qt.ItemDataRole.UserRole)
        if not stock_code or self.df_all.empty:
            return

        # 发送逻辑
        success = self.push_stock_info(stock_code, self.df_all.loc[stock_code])
        if success:
            self.statusBar().showMessage(f"发送成功: {stock_code}")
        else:
            self.statusBar().showMessage(f"发送失败: {stock_code}")

    def on_header_section_clicked(self, _logicalIndex):
        """排序后自动滚动到顶部，延时确保排序完成"""
        QTimer.singleShot(50, self.stock_table.scrollToTop)

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

    def on_dataframe_received(self, df, msg_type):
        if msg_type == "UPDATE_DF_ALL":
            self.update_df_all(df)
        elif msg_type == "UPDATE_DF_DIFF":
            self.apply_df_diff(df)
        else:
            logger.warning(f"Unknown msg_type: {msg_type}")

    def update_df_all(self, df=None):
        """
        更新 df_all 并刷新表格
        - df: 如果传入 DataFrame，则刷新缓存
        """
        if df is not None:
            # 更新缓存
            self.df_cache = df.copy() if not df.empty else pd.DataFrame()
            self.df_all = self.df_cache
        self.update_stock_table(self.df_all)
        
        # ⭐ 关键修复：刷新当前股票标题（仅更新监理看板部分）
        if getattr(self, 'current_code', None) and hasattr(self, 'kline_plot'):
            self._refresh_sensing_bar(self.current_code)

    def _capture_view_state(self):
        """在切换数据前，精准捕获当前的可见窗口"""
        if not hasattr(self, 'day_df') or self.day_df.empty:
            return
        try:
            vb = self.kline_plot.getViewBox()
            view_rect = vb.viewRect()
            total = len(self.day_df)
            
            # 1. 检测是否处于“全览”状态（即当前已经看完了绝大部分数据）
            # 如果左边缘接近 0 且右边缘接近末尾，则标记为 FullView
            self._prev_is_full_view = (view_rect.left() <= 10 and view_rect.right() >= total - 5)
            
            # 2. 捕获两端相对于末尾的偏移根数
            self._prev_dist_left = total - view_rect.left()
            self._prev_dist_right = total - view_rect.right()
            
            # 3. 捕获价格比例关系
            v_start, v_end = int(max(0, view_rect.left())), int(min(total, view_rect.right()))
            visible_old = self.day_df.iloc[v_start:v_end]
            if not visible_old.empty:
                old_h, old_l = visible_old['high'].max(), visible_old['low'].min()
                old_rng = old_h - old_l if old_h > old_l else 1.0
                self._prev_y_zoom = view_rect.height() / old_rng
                self._prev_y_center_rel = (view_rect.center().y() - old_l) / old_rng
            else:
                self._prev_y_zoom = None
            
            # logger.debug(f"[VIEW] Capture: is_full={self._prev_is_full_view}, left_d={self._prev_dist_left:.1f}")
        except Exception as e:
            logger.debug(f"Capture state failed: {e}")


    def load_stock_by_code(self, code):
        self._capture_view_state()

        if self.current_code == code and self.select_resample == self.resample:
            return
        self.current_code = code
        self.select_resample == self.resample

        if self.stock_table.rowCount() == 0:
            return

        current_row = self.stock_table.currentRow()

        for row in range(self.stock_table.rowCount()):
            item = self.stock_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == str(code):

                if row != current_row:
                    self.stock_table.blockSignals(True)
                    self.stock_table.setCurrentCell(row, 0)
                    self.stock_table.blockSignals(False)

                    self.stock_table.scrollToItem(
                        item, QAbstractItemView.ScrollHint.EnsureVisible
                    )
                break

        self.kline_plot.setTitle(f"Loading {code}...")

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

        # --- 标题 (含监理看板) ---
        self._update_plot_title(code, day_df, tick_df)
        
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
        
        # --- [Simulation Hits] ---
        sim_xs, sim_ys, sim_brushes, sim_symbols, sim_meta = [], [], [], [], []
        if self.show_strategy_simulation:
            sim_hits = self._run_strategy_simulation(code, day_df)
            for hit in sim_hits:
                idx = hit['index']
                y_p = hit['price']
                sim_xs.append(idx)
                sim_ys.append(y_p)
                sim_brushes.append(pg.mkBrush(hit['color']))
                sim_symbols.append(hit['symbol'])
                sim_meta.append(hit['meta'])

        if not hasattr(self, 'signal_scatter'):
            self.signal_scatter = pg.ScatterPlotItem(size=15, pen=pg.mkPen('k'), symbol='t1', z=10)
            self.kline_plot.addItem(self.signal_scatter)
            
            # ⭐ 模拟信号专门用一个层
            self.sim_scatter = pg.ScatterPlotItem(size=18, pen=pg.mkPen('w', width=0.5), z=9)
            self.kline_plot.addItem(self.sim_scatter)
            
            # ⭐ 绑定点击事件
            self.signal_scatter.sigClicked.connect(self.on_signal_clicked)
            self.sim_scatter.sigClicked.connect(self.on_signal_clicked)
            self.signal_text_items = []
        else:
            self.signal_scatter.clear()
            self.sim_scatter.clear()
            for t in getattr(self, 'signal_text_items', []):
                self.kline_plot.removeItem(t)
            self.signal_text_items.clear()
        
        # 渲染模拟信号
        if sim_xs:
            self.sim_scatter.setData(x=sim_xs, y=sim_ys, brush=sim_brushes, symbol=sim_symbols, data=sim_meta)

        if not signals.empty:
            # ⭐ 类型安全转换：确保按字符串匹配
            signals['code'] = signals['code'].astype(str)
            stock_signals = signals[signals['code'] == str(code)]
            xs, ys, brushes, symbols, meta = [], [], [], [], []
            date_map = {d if isinstance(d, str) else d.strftime('%Y-%m-%d'): i for i, d in enumerate(dates)}
            
            for _, row in stock_signals.iterrows():
                sig_date = str(row['date']).split()[0]
                if sig_date in date_map:
                    idx = date_map[sig_date]
                    xs.append(idx)
                    y_price = row['price'] if pd.notnull(row['price']) else day_df.iloc[idx]['close']
                    ys.append(y_price)
                    
                    action = str(row['action'])
                    reason = str(row['reason'])
                    indicators = row.get('indicators', '{}')
                    
                    # --- 识别信号类型 ---
                    is_veto = "VETO" in action
                    is_shadow = "SHADOW" in action
                    is_buy = 'Buy' in action or '买' in action or 'ADD' in action or '加' in action
                    
                    # ⭐ 动态设置颜色与图标
                    if is_veto:
                        brush = pg.mkBrush(200, 200, 200) # 银色/灰色
                        color = (200, 200, 200)
                        symbol = 's' # Square for VETO
                        label = f"🛡️ {y_price:.2f}"
                        anchor = (0.5, 1.5)
                    elif is_shadow:
                        brush = pg.mkBrush(0, 255, 255) # 青色
                        color = 'c'
                        symbol = 'd' # Diamond for SHADOW
                        label = f"🧪 {y_price:.2f}"
                        anchor = (0.5, 1.5)
                    else:
                        brush = pg.mkBrush('r') if is_buy else pg.mkBrush('g')
                        color = 'r' if is_buy else 'g'
                        symbol = 't1' # Triangle for normal
                        label = f"{y_price:.2f}"
                        anchor = (0.5, 1.5) if is_buy else (0.5, -0.5)
                    
                    brushes.append(brush)
                    symbols.append(symbol)
                    # 存储元数据用于点击显示
                    meta.append({
                        "date": sig_date, 
                        "action": action, 
                        "reason": reason, 
                        "price": y_price,
                        "indicators": indicators
                    })
                    
                    text_item = pg.TextItem(
                        text=label,
                        anchor=anchor,
                        color=color,
                        border='k',
                        fill=(50,50,50,180)
                    )
                    text_item.setZValue(11)
                    text_item.setPos(idx, y_price)
                    self.kline_plot.addItem(text_item)
                    self.signal_text_items.append(text_item)
            
            # --- [NEW] Shadow Strategy Integration ---
            # 自动集成策略系统跑数：在图表末尾计算并显示实时“影子信号”
            is_realtime_active = self.realtime and not tick_df.empty and (cct.get_work_time_duration() or self._debug_realtime)
            if is_realtime_active:
                shadow_decision = self._run_realtime_strategy(code, day_df, tick_df)
                if shadow_decision and shadow_decision.get('action') in ("买入", "卖出", "止损", "止盈", "ADD"):
                    y_price = float(tick_df['price'].iloc[-1])
                    idx = len(dates) # Ghost candle index
                    
                    action = shadow_decision['action']
                    reason = shadow_decision['reason']
                    is_buy = '买' in action or 'BUY' in action or 'ADD' in action
                    
                    xs.append(idx)
                    ys.append(y_price)
                    brushes.append(pg.mkBrush(255, 215, 0)) # 黄金色表示影子信号
                    symbols.append('star')
                    
                    self.last_shadow_decision = shadow_decision # ⭐ 存储供简报使用
                    meta.append({
                        "date": "REALTIME", 
                        "action": f"[SHADOW] {action}", 
                        "reason": reason, 
                        "price": y_price,
                        "indicators": shadow_decision.get('debug', {}) # 直接存对象，不需要 dumps，on_signal_clicked 会处理
                    })
                    
                    # 添加实时的文本提示
                    shadow_text = pg.TextItem(
                        text=f"⭐{action}\n{y_price:.2f}",
                        anchor=(0.5, 1.2) if is_buy else (0.5, -0.2),
                        color=(255, 215, 0),
                        border='w',
                        fill=(0, 0, 0, 200)
                    )
                    shadow_text.setPos(idx, y_price)
                    shadow_text.setZValue(12)
                    self.kline_plot.addItem(shadow_text)
                    self.signal_text_items.append(shadow_text)

            if xs:
                # 信号点使用不同形状增强区分
                self.signal_scatter.setData(x=xs, y=ys, brush=brushes, symbol=symbols, size=22, data=meta)

        # -------------------------
        # 移除此处的 sensing_bar 设置，改到 intraday 内容设置之后
        # -------------------------

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
            
            # ⭐ 构建分时图标题（包含监理看板）
            tick_title = f"Intraday: {prices[-1]:.2f} ({pct_change:.2f}%)"
            
            # 追加监理看板信息
            if not self.df_all.empty:
                # 调试：打印 df_all 的列名
                # print(f"[DEBUG] df_all columns: {self.df_all.columns.tolist()}")
                # print(f"[DEBUG] Looking for code: {code}, df_all index: {self.df_all.index.tolist()[:5]}")
                
                crow = None
                # 尝试多种匹配方式：原样匹配、去掉市场前缀匹配
                search_codes = [code]
                if len(code) > 6:
                    search_codes.append(code[-6:])
                
                for sc in search_codes:
                    if sc in self.df_all.index:
                        crow = self.df_all.loc[sc]
                        break
                    elif 'code' in self.df_all.columns:
                        mask = self.df_all['code'] == sc
                        if mask.any():
                            crow = self.df_all[mask].iloc[0]
                            break
                
                if crow is not None:
                    mwr = crow.get('market_win_rate', 0)
                    ls = crow.get('loss_streak', 0)
                    vwap_bias = crow.get('vwap_bias', 0)
                    
                    # 保存数据供详情弹窗使用
                    self.current_supervision_data = {
                        'market_win_rate': mwr,
                        'loss_streak': ls,
                        'vwap_bias': vwap_bias,
                        'last_action': crow.get('last_action', ''),
                        'last_reason': crow.get('last_reason', ''),
                        'shadow_info': crow.get('shadow_info', '')
                    }
                    tick_title += f"  |  <span style='color: #FFD700; font-weight: bold;'>🛡️监理: 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}</span>"
                else:
                    # 尝试自主计算
                    auto_data = self._get_autonomous_supervision_data(code)
                    if auto_data:
                        mwr = auto_data.get('market_win_rate', 0.5)
                        ls = auto_data.get('loss_streak', 0)
                        vwap_bias = auto_data.get('vwap_bias', 0)
                        
                        # ⭐ 重点：补齐自主模式下的详情数据分配
                        has_sh = 'shadow_decision' in locals() and shadow_decision is not None
                        shadow_act = shadow_decision.get('action', 'N/A') if has_sh else 'N/A'
                        shadow_res = shadow_decision.get('reason', 'N/A') if has_sh else 'N/A'
                        
                        self.current_supervision_data = {
                            'market_win_rate': mwr,
                            'loss_streak': ls,
                            'vwap_bias': vwap_bias,
                            'last_action': f"自主检测({shadow_act})",
                            'last_reason': shadow_res,
                            'shadow_info': 'AUTONOMOUS'
                        }
                        tick_title += f"  |  <span style='color: #FFD700; font-weight: bold;'>🛡️监理(自): 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}</span>"
            else:
                # df_all 为空，直接自主计算
                auto_data = self._get_autonomous_supervision_data(code)
                if auto_data:
                    mwr = auto_data.get('market_win_rate', 0.5)
                    ls = auto_data.get('loss_streak', 0)
                    vwap_bias = auto_data.get('vwap_bias', 0)
                    
                    has_sh = 'shadow_decision' in locals() and shadow_decision is not None
                    shadow_act = shadow_decision.get('action', 'N/A') if has_sh else 'N/A'
                    shadow_res = shadow_decision.get('reason', 'N/A') if has_sh else 'N/A'
                    
                    self.current_supervision_data = {
                        'market_win_rate': mwr,
                        'loss_streak': ls,
                        'vwap_bias': vwap_bias,
                        'last_action': f"直接启动模式({shadow_act})",
                        'last_reason': shadow_res,
                        'shadow_info': 'DIRECT_LAUNCH'
                    }
                    tick_title += f"  |  <span style='color: #FFD700; font-weight: bold;'>🛡️监理(自): 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}</span>"
            
            self.tick_plot.setTitle(tick_title)
            self.tick_plot.showGrid(x=False, y=True, alpha=0.5)

            # --- [NEW] Intraday Tick Signals (Shadow/Realtime) ---
            # 直接在分时图上标记影子信号
            if not hasattr(self, 'tick_signal_scatter'):
                self.tick_signal_scatter = pg.ScatterPlotItem(size=18, pen=pg.mkPen('w', width=0.5), z=15)
                self.tick_plot.addItem(self.tick_signal_scatter)
                self.tick_signal_scatter.sigClicked.connect(self.on_signal_clicked)
            else:
                self.tick_signal_scatter.clear()

            is_realtime_active = self.realtime and not tick_df.empty and (cct.get_work_time_duration() or self._debug_realtime)
            if is_realtime_active and self.show_strategy_simulation:
                shadow_decision = self._run_realtime_strategy(code, day_df, tick_df)
                if shadow_decision and shadow_decision.get('action') in ("买入", "卖出", "止损", "止盈", "ADD"):
                    y_p = float(tick_df['price'].iloc[-1])
                    idx = len(tick_df) - 1
                    action = shadow_decision['action']
                    
                    self.tick_signal_scatter.setData(
                        x=[idx], y=[y_p],
                        brush=[pg.mkBrush(255, 215, 0)],
                        symbol=['star'],
                        data=[{
                            "date": "INTRADAY_LIVE",
                            "action": f"[TICK] {action}",
                            "reason": shadow_decision['reason'],
                            "price": y_p,
                            "indicators": shadow_decision.get('debug', {})
                        }]
                    )

        # ----------------- 5. 数据同步与视角处理 -----------------
        # 同步归一化后的数据到 self.day_df
        self.day_df = day_df

        is_new_stock = not hasattr(self, '_last_rendered_code') or self._last_rendered_code != code
        self._last_rendered_code = code

        last_resample = getattr(self, "_last_resample", None)
        is_resample_change = (last_resample is not None and last_resample != self.resample)
        self._last_resample = self.resample
        
        # 复合视角恢复标志
        has_captured_state = hasattr(self, '_prev_dist_left') and getattr(self, '_prev_y_zoom', None) is not None
        was_full_view = getattr(self, '_prev_is_full_view', False)

        if is_new_stock or is_resample_change or has_captured_state:
            vb = self.kline_plot.getViewBox()
            
            # 如果之前是“全览”状态，或者根本没有捕获状态，则执行 Reset (全览)
            if was_full_view or not has_captured_state:
                self._reset_kline_view(df=day_df)
            else:
                # 处于“记忆”状态：用户之前可能缩放到了某个特定区域
                new_total = len(day_df)
                target_left = max(-1, new_total - self._prev_dist_left)
                target_right = new_total - self._prev_dist_right
                
                # 设置 X 轴，留出缓冲
                vb.setRange(xRange=(target_left, target_right), padding=0)
                
                # 适配 Y 轴
                visible_new = day_df.iloc[int(max(0, target_left)):int(min(new_total, target_right+1))]
                if not visible_new.empty:
                    new_h, new_l = visible_new['high'].max(), visible_new['low'].min()
                    new_rng = new_h - new_l if new_h > new_l else 1.0
                    p_zoom, p_center_rel = float(self._prev_y_zoom), float(self._prev_y_center_rel)
                    target_h = new_rng * p_zoom
                    target_y_center = new_l + (new_rng * p_center_rel)
                    vb.setRange(yRange=(target_y_center - target_h/2, target_y_center + target_h/2), padding=0)

                # 保持自适应开启
                vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
                vb.setAutoVisible(y=True)

            # 清理刚才使用的临时状态
            for attr in ['_prev_dist_left', '_prev_dist_right', '_prev_y_zoom', '_prev_y_center_rel', '_prev_is_full_view']:
                if hasattr(self, attr): delattr(self, attr)
        else:
            # 实时刷新：不对视角做任何干扰
            pass



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

    def _update_plot_title(self, code, day_df, tick_df):
        """仅更新 K 线图基础信息（代码、名称、排名等），不再包含监理看板以防干扰视图"""
        if not hasattr(self, 'kline_plot'):
            return
        
        # 尝试从 code_info_map 获取基础信息 (增加模糊匹配)
        info = self.code_info_map.get(code)
        if info is None and len(code) > 6:
            info = self.code_info_map.get(code[-6:])
        if info is None:
            info = {}
            
        title_parts = [code]
        for k, fmt in [('name', '{}'), ('Rank', 'Rank: {}'), ('percent', '{:+.2f}%'),
                       ('win', 'win: {}'), ('slope', 'slope: {:.1f}%'), ('volume', 'vol: {:.1f}')]:
            v = info.get(k)
            if v is not None:
                title_parts.append(fmt.format(v))
        
        main_title = " | ".join(title_parts)
        # 只有标题内容变化时才调用 setTitle
        if getattr(self, "_last_main_title", "") != main_title:
            self.kline_plot.setTitle(main_title)
            self._last_main_title = main_title
    
    def _refresh_sensing_bar(self, code):
        """刷新分时图标题中的监理看板（避免刷新 K 线标题导致布局抖动）"""
        if not hasattr(self, 'tick_plot'):
            return
        
        # 1. 获取基础分时信息
        # 尝试从之前的标题中恢复基础部分，或者简单重构
        base_title = self.tick_plot.titleLabel.text
        if "🛡️监理" in base_title:
            # 剥离旧的监理部分
            base_title = base_title.split("  |  <span")[0]
            
        # 2. 追加最新的监理看板信息
        sensing_parts = []
        if not self.df_all.empty:
            crow = None
            search_codes = [code]
            if len(code) > 6:
                search_codes.append(code[-6:])
            
            for sc in search_codes:
                if sc in self.df_all.index:
                    crow = self.df_all.loc[sc]
                    break
                elif 'code' in self.df_all.columns:
                    mask = self.df_all['code'] == sc
                    if mask.any():
                        crow = self.df_all[mask].iloc[0]
                        break
            
            if crow is not None:
                mwr = crow.get('market_win_rate', 0)
                ls = crow.get('loss_streak', 0)
                vwap_bias = crow.get('vwap_bias', 0)
                sensing_parts.append(f"🛡️监理: 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}")
            else:
                # ⭐ 备选方案：尝试自主计算（脱离主程序推送）
                auto_data = self._get_autonomous_supervision_data(code)
                if auto_data:
                    mwr = auto_data.get('market_win_rate', 0.5)
                    ls = auto_data.get('loss_streak', 0)
                    vwap_bias = auto_data.get('vwap_bias', 0)
                    sensing_parts.append(f"🛡️监理(自): 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}")
        
        if sensing_parts:
            sensing_html = " ".join(sensing_parts)
            new_title = f"{base_title}  |  <span style='color: #FFD700; font-weight: bold;'>{sensing_html}</span>"
            self.tick_plot.setTitle(new_title)

    def _get_autonomous_supervision_data(self, code):
        """自主计算并获取监理数据（胜率、连亏、偏离度）"""
        try:
            # 1. 从数据库读取胜率和连亏
            mwr = self.logger.get_market_sentiment(days=10)
            ls = self.logger.get_consecutive_losses(code, days=15)
            
            # 2. 计算偏离度 (VWAP Bias)
            vwap_bias = 0
            if hasattr(self, 'tick_df') and not self.tick_df.empty:
                tick = self.tick_df
                if 'amount' in tick.columns and 'volume' in tick.columns:
                    cum_amount = tick['amount'].cumsum().iloc[-1]
                    cum_vol = tick['volume'].cumsum().iloc[-1]
                    if cum_vol > 0:
                        vwap = cum_amount / cum_vol
                        current_price = tick['price'].iloc[-1]
                        vwap_bias = (current_price - vwap) / vwap
            
            return {
                'market_win_rate': mwr,
                'loss_streak': ls,
                'vwap_bias': vwap_bias
            }
        except Exception as e:
            logger.debug(f"Autonomous supervision failed for {code}: {e}")
            return None

    def _run_realtime_strategy(self, code, day_df, tick_df):
        """
        [DEEP INTEGRATION] 自动集成策略系统跑数
        直接在可视化中运行决策引擎，生成实时的‘影子信号’
        """
        try:
            if day_df.get('close') is None or tick_df.empty:
                return None
            
            # 1. 准备行情行 (row)
            # 模拟 MonitorTK 的 row_data 结构
            last_tick = tick_df.iloc[-1]
            row = {
                'code': code,
                'trade': last_tick.get('price', 0),
                'high': tick_df['price'].max(),
                'low': tick_df['price'].min(),
                'open': tick_df['price'].iloc[0],
                'ratio': last_tick.get('ratio', 0),
                'volume': last_tick.get('volume', 0),
                'amount': last_tick.get('amount', 0),
                'ma5d': day_df['close'].rolling(5).mean().iloc[-1],
                'ma10d': day_df['close'].rolling(10).mean().iloc[-1],
                'ma20d': day_df['close'].rolling(20).mean().iloc[-1],
                'nclose': (tick_df['amount'].sum() / tick_df['volume'].sum()) if tick_df['volume'].sum() > 0 else 0
            }
            
            # 2. 准备快照 (snapshot)
            snapshot = {
                'last_close': day_df['close'].iloc[-2] if len(day_df) > 1 else day_df['close'].iloc[-1],
                'market_win_rate': self.logger.get_market_sentiment(days=5),
                'loss_streak': self.logger.get_consecutive_losses(code, days=10)
            }
            
            # 3. 运行引擎评估
            decision = self.decision_engine.evaluate(row, snapshot)
            return decision
            
        except Exception as e:
            logger.debug(f"Realtime strategy evaluation failed: {e}")
            return None

    def _run_strategy_simulation(self, code, day_df):
        """
        [DEEP INTEGRATION] 历史策略模拟：计算哪些 K 线命中了哪些策略
        """
        hits = []
        try:
            if len(day_df) < 10: return hits
            
            # --- 1. StrongPullbackMA5 策略 (批量) ---
            # 确保列齐
            df_pb = day_df.copy()
            # 简单模拟必要列
            if 'lasth1d' not in df_pb.columns:
                df_pb['lasth1d'] = df_pb['high'].shift(1)
                df_pb['lastp1d'] = df_pb['close'].shift(1)
                df_pb['lastp2d'] = df_pb['close'].shift(2)
                df_pb['lastv1d'] = df_pb['volume'].shift(1)
                df_pb['lastv2d'] = df_pb['volume'].shift(2)
                df_pb['ma5d'] = df_pb['close'].rolling(5).mean()
                df_pb['ma10d'] = df_pb['close'].rolling(10).mean()
                df_pb['ma20d'] = df_pb['close'].rolling(20).mean()
                df_pb['ma60d'] = df_pb['close'].rolling(60).mean()
            
            pb_results = self.pullback_strat.run(df_pb)
            for i, row in pb_results.iterrows():
                # 获取在原始 df 中的索引位置
                try:
                    idx = day_df.index.get_loc(i)
                    hits.append({
                        'index': idx,
                        'price': row['close'],
                        'symbol': 'o',
                        'color': (0, 255, 255, 180), # 蓝绿色
                        'meta': {
                            'date': str(i).split()[0],
                            'action': '[SIM] 强力回撤',
                            'reason': f"评分: {row['strong_score']:.1f} ({row['risk_level']})",
                            'price': row['close'],
                            'indicators': {
                                'Trend': row['trend_score'],
                                'Pullback': row['pullback_score'],
                                'Volume': row['volume_score']
                            }
                        }
                    })
                except: continue

            # --- 2. IntradayDecision (逐行，最近 60 天) ---
            eval_df = day_df.tail(60)
            for timestamp, d_row in eval_df.iterrows():
                # 模拟盘中行
                idx = day_df.index.get_loc(timestamp)
                pseudo_row = {
                    'code': code,
                    'trade': d_row['close'],
                    'high': d_row['high'],
                    'low': d_row['low'],
                    'open': d_row['open'],
                    'volume': d_row['volume'],
                    'ma5d': d_row['ma5'],
                    'ma10d': d_row['ma10'],
                    'ma20d': d_row['ma20'],
                    'ratio': 0.1,
                }
                # 找前一天做 snapshot
                past_idx = idx - 1
                if past_idx >= 0:
                    prev_row = day_df.iloc[past_idx]
                    snap = {
                        'last_close': prev_row['close'],
                        'market_win_rate': 0.5,
                        'loss_streak': 0
                    }
                    decision = self.decision_engine.evaluate(pseudo_row, snap)
                    if decision.get('action') in ("买入", "卖出", "ADD"):
                        hits.append({
                            'index': idx,
                            'price': d_row['close'],
                            'symbol': 'star',
                            'color': (255, 200, 0, 150),
                            'meta': {
                                'date': str(timestamp).split()[0],
                                'action': f"[SIM] 影子决策:{decision['action']}",
                                'reason': decision['reason'],
                                'price': d_row['close'],
                                'indicators': decision.get('debug', {})
                            }
                        })
                        
        except Exception as e:
            logger.debug(f"Strategy simulation failed: {e}")
            
        return hits


    def _run_strategy_simulation_other(self, code, day_df):
        """
        [DEEP INTEGRATION] 历史策略模拟：直接使用 day_df 原始列，不做任何修改
        """
        hits = []
        try:
            if len(day_df) < 10:
                return hits

            # --- 1. StrongPullbackMA5 策略 (批量) ---
            pb_results = self.pullback_strat.run(day_df)
            for i, row in pb_results.iterrows():
                try:
                    idx = day_df.index.get_loc(i)
                    hits.append({
                        'index': idx,
                        'price': row['close'],
                        'symbol': 'o',
                        'color': (0, 255, 255, 180),
                        'meta': {
                            'date': str(i).split()[0],
                            'action': '[SIM] 强力回撤',
                            'reason': f"评分: {row.get('strong_score', 0)} ({row.get('risk_level','N/A')})",
                            'price': row['close'],
                            'indicators': {
                                'Trend': row.get('trend_score', 0),
                                'Pullback': row.get('pullback_score', 0),
                                'Volume': row.get('volume_score', 0)
                            }
                        }
                    })
                except Exception:
                    continue

            # --- 2. IntradayDecision (逐行，最近 60 天) ---
            eval_df = day_df.tail(60)
            for timestamp, d_row in eval_df.iterrows():
                idx = day_df.index.get_loc(timestamp)
                pseudo_row = d_row.to_dict()  # 直接取原始行

                # 加上必要的额外字段
                pseudo_row.update({
                    'code': code,
                    'trade': d_row['close'],
                    'ratio': 0.1,
                })

                past_idx = idx - 1
                if past_idx >= 0:
                    snap = {
                        'last_close': day_df.iloc[past_idx]['close'],
                        'market_win_rate': 0.5,
                        'loss_streak': 0
                    }
                    decision = self.decision_engine.evaluate(pseudo_row, snap)
                    if decision.get('action') in ("买入", "卖出", "ADD"):
                        hits.append({
                            'index': idx,
                            'price': d_row['close'],
                            'symbol': 'star',
                            'color': (255, 200, 0, 150),
                            'meta': {
                                'date': str(timestamp).split()[0],
                                'action': f"[SIM] 影子决策:{decision['action']}",
                                'reason': decision.get('reason', ''),
                                'price': d_row['close'],
                                'indicators': decision.get('debug', {})
                            }
                        })

        except Exception as e:
            logger.debug(f"Strategy simulation failed: {e}")

        return hits

    def _init_filter_toolbar(self):
        # 查找或创建 Filter Action
        actions = self.toolbar.actions()
        has_filter = any(a.text() == "Filter" for a in actions)
        if not has_filter:
            filter_action = self.toolbar.addAction("Filter")
            filter_action.setCheckable(True)
            filter_action.triggered.connect(self.toggle_filter_panel)
            self.filter_action = filter_action

    def toggle_filter_panel(self, checked):
        self.filter_panel.setVisible(checked)
        if checked:
            self.load_history_filters()

    def open_history_manager(self):
        import subprocess
        try:
            # 假设 history_manager.py 在同一目录下
            base_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(base_dir, "history_manager.py")
            if os.path.exists(script_path):
                subprocess.Popen(["python", script_path], cwd=base_dir)
            else:
                QMessageBox.warning(self, "Error", f"history_manager.py not found at {script_path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to launch manager: {e}")

    def load_history_filters(self):
        from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
        import os
        
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        
        history_path = SEARCH_HISTORY_FILE
        
        if not os.path.exists(history_path):
             self.filter_combo.addItem("History file not found")
             self.filter_combo.blockSignals(False)
             return

        try:
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 使用 history4
            self.history_items = data.get("history4", [])
            for item in self.history_items:
                q = item.get("query", "")
                note = item.get("note", "")
                label = f"{note} ({q})" if note else q
                self.filter_combo.addItem(label, userData=q) # Store query in UserData
            
            if not self.history_items:
                 self.filter_combo.addItem("(No history)")

        except Exception as e:
            self.filter_combo.addItem(f"Error: {e}")
        
        self.filter_combo.blockSignals(False)
        # Load first item if available
        if self.filter_combo.count() > 0:
             self.on_filter_combo_changed(0)

    def populate_tree_from_df(self, df: pd.DataFrame):
        """
        将 DataFrame 高速填充到 QTreeWidget
        - 支持列、颜色标记、图标
        - 左对齐、紧凑列宽、水平滚动
        """
        import time
        prep_start = time.time()
        self.filter_tree.clear()

        if df.empty:
            return

        # --- 配置列 ---
        columns = self._filter_columns  # 需要显示的列
        self.filter_tree.setColumnCount(len(columns))
        self.filter_tree.setHeaderLabels(columns)
        self.filter_tree.setSortingEnabled(True)
        self.filter_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.filter_tree.setHorizontalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        self.filter_tree.setSizeAdjustPolicy(QTreeWidget.SizeAdjustPolicy.AdjustToContents)

        n_rows = len(df)

        # --- 预提取列数据，避免循环内索引 ---
        col_arrays = []
        for col in columns:
            if col in df.columns:
                arr = df[col].fillna('').tolist()
            else:
                arr = [''] * n_rows
            col_arrays.append(arr)

        # --- 特征标记预提取 ---
        feature_data = None
        fm = getattr(self, 'feature_marker', None)
        if fm and fm.enable_colors:
            feature_cols = ['percent', 'volume', 'category', 'price', 'trade', 'high4',
                            'max5', 'max10', 'hmax', 'hmax60', 'low4', 'low10', 'low60',
                            'lmin', 'min5', 'cmean', 'hv', 'lv', 'llowvol', 'lastdu4']
            fd = {}
            for k in feature_cols:
                if k in df.columns:
                    if k == 'category':
                        fd[k] = df[k].fillna('').tolist()
                    else:
                        fd[k] = df[k].fillna(0).tolist()
                else:
                    fd[k] = None
            feature_data = fd

        name_idx = columns.index('name') if 'name' in columns else -1

        # --- 构建行 ---
        for i in range(n_rows):
            values = [col_arrays[j][i] for j in range(len(columns))]

            row_data = None
            if feature_data:
                try:
                    fd = feature_data
                    price_val = fd['price'][i] if fd['price'] else 0
                    if price_val == 0 and fd['trade']:
                        price_val = fd['trade'][i]

                    row_data = {
                        'percent': fd['percent'][i] if fd['percent'] else 0,
                        'volume': fd['volume'][i] if fd['volume'] else 0,
                        'category': fd['category'][i] if fd['category'] else '',
                        'price': price_val,
                        'high4': fd['high4'][i] if fd['high4'] else 0,
                        'max5': fd['max5'][i] if fd['max5'] else 0,
                        'max10': fd['max10'][i] if fd['max10'] else 0,
                        'hmax': fd['hmax'][i] if fd['hmax'] else 0,
                        'hmax60': fd['hmax60'][i] if fd['hmax60'] else 0,
                        'low4': fd['low4'][i] if fd['low4'] else 0,
                        'low10': fd['low10'][i] if fd['low10'] else 0,
                        'low60': fd['low60'][i] if fd['low60'] else 0,
                        'lmin': fd['lmin'][i] if fd['lmin'] else 0,
                        'min5': fd['min5'][i] if fd['min5'] else 0,
                        'cmean': fd['cmean'][i] if fd['cmean'] else 0,
                        'hv': fd['hv'][i] if fd['hv'] else 0,
                        'lv': fd['lv'][i] if fd['lv'] else 0,
                        'llowvol': fd['llowvol'][i] if fd['llowvol'] else 0,
                        'lastdu4': fd['lastdu4'][i] if fd['lastdu4'] else 0
                    }

                    # 添加图标
                    if name_idx >= 0:
                        icon = fm.get_icon_for_row(row_data)
                        if icon:
                            values[name_idx] = f"{icon} {values[name_idx]}"
                except Exception:
                    row_data = None

            # --- 插入 QTreeWidgetItem ---
            item = QTreeWidgetItem(self.filter_tree)
            for col, val in enumerate(values):
                item.setText(col, str(val))
                item.setTextAlignment(col, Qt.AlignmentFlag.AlignLeft)

            # 设置 UserRole 保存 code
            code_col = df.columns.get_loc('code') if 'code' in df.columns else 0
            item.setData(0, Qt.ItemDataRole.UserRole, str(values[code_col]))

            # 上色 percent 列
            pct_idx = columns.index('percent') if 'percent' in columns else -1
            if feature_data and pct_idx >= 0:
                pct_val = row_data['percent'] if row_data else 0
                if pct_val > 0:
                    item.setForeground(pct_idx, QBrush(QColor("red")))
                elif pct_val < 0:
                    item.setForeground(pct_idx, QBrush(QColor("green")))

        # --- 调整列宽 ---
        header = self.filter_tree.header()
        for col in range(self.filter_tree.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)

        prep_time = time.time() - prep_start
        if prep_time > 0.1:
            logger.debug(f"[TreeviewUpdater] 填充 {n_rows} 行耗时 {prep_time:.3f}s")


    def on_filter_combo_changed(self, index):
        query_str = self.filter_combo.currentData()
        self.filter_tree.clear()

        if not query_str or self.df_all.empty:
            return

        try:
            # --- 1. 准备数据 ---
            df_to_search = self.df_all.copy()
            if 'code' not in df_to_search.columns:
                df_to_search['code'] = df_to_search.index.astype(str)
            if 'volume' in df_to_search.columns and 'vol' not in df_to_search.columns:
                df_to_search['vol'] = df_to_search['volume']

            # --- 2. 执行查询 ---
            final_query = ensure_parentheses_balanced(query_str)
            matches = df_to_search.query(final_query)
            if matches.empty:
                self.statusBar().showMessage("Results: 0")
                return

            # # 调用高速填充
            # self.populate_tree_from_df(matches)
            
            # --- 3. 设置列头 ---
            self.filter_tree.setColumnCount(4)
            self.filter_tree.setHeaderLabels(['Code', 'Name', 'Rank', 'Percent'])
            self.filter_tree.setSortingEnabled(True)
            self.filter_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.filter_tree.setHorizontalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
            self.filter_tree.setSizeAdjustPolicy(QTreeWidget.SizeAdjustPolicy.AdjustToContents)

            # --- 4. 填充数据 ---
            for idx, row in matches.iterrows():
                code = str(row['code'])
                name = str(row.get('name', ''))
                rank = row.get('Rank', 0)
                pct = row.get('percent', 0)

                child = QTreeWidgetItem(self.filter_tree)
                child.setText(0, code)
                child.setText(1, name)
                child.setText(2, str(rank))
                child.setText(3, f"{pct:.2f}%")
                child.setData(0, Qt.ItemDataRole.UserRole, code)

                # 左对齐
                for col in range(4):
                    child.setTextAlignment(col, Qt.AlignmentFlag.AlignLeft)

                # 百分比上色
                if pct > 0:
                    child.setForeground(3, QBrush(QColor("red")))
                elif pct < 0:
                    child.setForeground(3, QBrush(QColor("green")))

            # --- 5. 调整列宽，尽量紧凑 ---
            header = self.filter_tree.header()
            for col in range(self.filter_tree.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            header.setStretchLastSection(False)  # 不拉伸最后一列

            self.statusBar().showMessage(f"Results: {len(matches)}")

        except Exception as e:
            err_item = QTreeWidgetItem(self.filter_tree)
            err_item.setText(0, f"Error: {e}")




    # # 设置表格列自适应
    # # 所有列自动根据内容调整宽度
    # for col in range(len(headers)):
    #     headers.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

    # def on_filter_combo_changed(self, index):
    #     query_str = self.filter_combo.currentData()
    #     self.filter_tree.clear()

    #     if not query_str or self.df_all.empty:
    #         return

    #     try:
    #         # 准备数据
    #         df_to_search = self.df_all.copy()
    #         if 'code' not in df_to_search.columns:
    #              df_to_search['code'] = df_to_search.index.astype(str)
    #         if 'volume' in df_to_search.columns and 'vol' not in df_to_search.columns:
    #             df_to_search['vol'] = df_to_search['volume']

    #         # 执行查询
    #         final_query = ensure_parentheses_balanced(query_str)
    #         matches = df_to_search.query(final_query)
            


    #         for idx, row in matches.iterrows():
    #             code = str(row['code'])
    #             name = str(row.get('name', ''))
    #             rank = str(row.get('rank', 0))
    #             child = QTreeWidgetItem(self.filter_tree)  # 直接顶格
    #             child.setText(0, f"{code} {name}{rank}{pct}")
    #             child.setData(0, Qt.ItemDataRole.UserRole, code)
                
    #             pct = row.get('percent', 0)
    #             if pct > 0:
    #                 child.setForeground(0, QBrush(QColor("red")))
    #             elif pct < 0:
    #                 child.setForeground(0, QBrush(QColor("green")))
    #         self.statusBar().showMessage(f"Results: {len(matches)}")

    #     except Exception as e:
    #         err_item = QTreeWidgetItem(self.filter_tree)
    #         err_item.setText(0, f"Error: {e}")

    def on_filter_tree_item_clicked(self, item, column):
        code = item.data(0, Qt.ItemDataRole.UserRole)
        if code:
            # 1. 触发图表加载
            self.load_stock_by_code(code)
            # 2. 联动左侧列表选中
            self._select_stock_in_main_table(code)

    def on_filter_tree_current_changed(self, current, previous):
        """处理键盘导航（上下键）"""
        if current:
            code = current.data(0, Qt.ItemDataRole.UserRole)
            if code:
                # 触发图表加载
                self.load_stock_by_code(code)
                # 联动左侧列表选中
                self._select_stock_in_main_table(code)

    def _select_stock_in_main_table(self, target_code):
        """在左侧 stock_table 中查找并滚动到指定 code"""
        # 遍历查找 (假设数据量不大，几千行以内尚可)
        # 如果 self.stock_table 行数过多，建议维护 code -> row 映射
        row_count = self.stock_table.rowCount()
        for row in range(row_count):
            item = self.stock_table.item(row, 0) # 第0列通常是 Code? 需确认
            # get data from UserRole or text
            if item:
                code_data = item.data(Qt.ItemDataRole.UserRole)
                if not code_data:
                    code_data = item.text()
                
                if str(code_data) == str(target_code):
                    self.stock_table.selectRow(row)
                    self.stock_table.scrollToItem(item)
                    break

    def load_splitter_state(self):
        """加载保存的分割器状态"""
        try:
            config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    sizes = config.get('splitter_sizes', [])
                    if sizes and len(sizes) == 3:
                        self.main_splitter.setSizes(sizes)
                        return
        except Exception as e:
            print(f"Failed to load splitter state: {e}")
        
        # 默认分割比例：股票列表:过滤面板:图表区域 = 1:1:4
        self.main_splitter.setSizes([200, 200, 800])
    
    # def save_splitter_state(self):
    #     """保存分割器状态（过滤隐藏面板的 0 值）"""
    #     try:
    #         config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")

    #         sizes = self.main_splitter.sizes()
    #         fixed_sizes = list(sizes)

    #         # 假设 filter 是第 3 个（index=2）
    #         FILTER_INDEX = 2
    #         FILTER_DEFAULT = 100
    #         FILTER_MIN = 60

    #         # 如果 filter 当前是隐藏状态或 size=0，写入合理值
    #         if fixed_sizes[FILTER_INDEX] <= 0:
    #             fixed_sizes[FILTER_INDEX] = max(
    #                 FILTER_DEFAULT,
    #                 FILTER_MIN
    #             )

    #         config = {'splitter_sizes': fixed_sizes}

    #         with open(config_file, 'w', encoding='utf-8') as f:
    #             json.dump(config, f, indent=2)

    #         logger.info(
    #             f'save_splitter sizes: raw={sizes}, fixed={fixed_sizes}, file={config_file}'
    #         )

    #     except Exception as e:
    #         logger.exception("Failed to save splitter state")

    def save_splitter_state(self):
        """保存分割器状态（过滤隐藏面板的 0 值）"""
        try:
            config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")

            sizes = self.main_splitter.sizes()
            fixed_sizes = list(sizes)

            # 假设 filter 是第 3 个（index=2）
            FILTER_INDEX = 2
            FILTER_DEFAULT = 100
            FILTER_MIN = 60

            # 尝试读取历史保存值
            old_size = None
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        old_config = json.load(f)
                        old_sizes = old_config.get('splitter_sizes', [])
                        if len(old_sizes) > FILTER_INDEX:
                            old_size = old_sizes[FILTER_INDEX]
                except Exception:
                    old_size = None

            # 如果当前 size 为 0，则使用历史值或默认值
            if fixed_sizes[FILTER_INDEX] <= 0:
                if old_size and old_size > 0:
                    fixed_sizes[FILTER_INDEX] = old_size
                else:
                    fixed_sizes[FILTER_INDEX] = max(FILTER_DEFAULT, FILTER_MIN)

            config = {'splitter_sizes': fixed_sizes}

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)

            logger.debug(
                f'save_splitter sizes: raw={sizes}, fixed={fixed_sizes}, file={config_file}'
            )

        except Exception as e:
            logger.exception("Failed to save splitter state")


    
    def closeEvent(self, event):
       """窗口关闭统一退出清理"""
       self._closing = True
       """窗口关闭事件"""
       # 保存分割器状态
       self.save_splitter_state()
       """Override close event to save window position"""
       try:
           self.save_window_position_qt_visual(self, "trade_visualizer")
           # self.save_window_position_qt(self, "trade_visualizer")
       except Exception as e:
           logger.error(f"Failed to save window position: {e}")

       # 1️⃣ 停止实时数据进程
       # 1️⃣ 通知子进程退出
       if hasattr(self, 'stop_flag'):
           self.stop_flag.value = False
       logger.info(f'stop_flag.value: {self.stop_flag.value}')
       self._stop_realtime_process()
       if hasattr(self, 'refresh_flag'):
           self.refresh_flag.value = False
           
       # 2️⃣ 停止 realtime_process
       if getattr(self, 'realtime_process', None):
           if self.realtime_process.is_alive():
               self.realtime_process.join(timeout=1)
               if self.realtime_process.is_alive():
                   logger.info("realtime_process 强制终止")
                   self.realtime_process.terminate()
                   self.realtime_process.join()
           self.realtime_process = None

       # 3️⃣ 停止 DataLoaderThread (避免 QThread Destroyed 崩溃)
       if hasattr(self, 'loader') and self.loader:
           if self.loader.isRunning():
               logger.info("Stopping DataLoaderThread...")
               self.loader.quit()
               if not self.loader.wait(1000): # 等待 1 秒
                   logger.warning("DataLoaderThread did not stop, terminating...")
                   self.loader.terminate()
                   self.loader.wait()
           self.loader = None
       # 当 GUI 关闭时，触发 stop_event
       stop_event.set()

       print(f'closeEvent: OK')
       # Accept the event to close
       event.accept()
       # 6️⃣ 调用父类 closeEvent
       super().closeEvent(event)
        

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

def main(initial_code='000002', stop_flag=None, log_level=None, debug_realtime=False, command_queue=None):
    # ------------------ 1. Logger ------------------
    if log_level is not None:
        logger.setLevel(log_level.value)

    # ------------------ 2. Primary/Secondary ------------------
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    stop_flag = stop_flag if stop_flag else mp.Value('b', True)

    try:
        server_socket.bind((IPC_HOST, IPC_PORT))
        server_socket.listen(5)  # backlog > 1
        is_primary_instance = True
        print(f"Listening on {IPC_HOST}:{IPC_PORT}")
    except OSError:
        is_primary_instance = False
        print(f"Listening 被占用 {IPC_HOST}:{IPC_PORT}")

    # ------------------ 3. Secondary ------------------
    if not is_primary_instance:
        code_to_send = initial_code if initial_code else (sys.argv[1] if len(sys.argv) > 1 else None)
        if code_to_send:
            # 尝试多次连接，保证 Primary 还没完全 accept 也能发
            for _ in range(5):
                try:
                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    client_socket.connect((IPC_HOST, IPC_PORT))
                    client_socket.send(code_to_send.encode("utf-8"))
                    client_socket.close()
                    break
                except Exception:
                    time.sleep(0.05)
            else:
                print(f"Failed to send command: {code_to_send}")
        sys.exit(0)

    # ------------------ 4. Primary: 启动 GUI ------------------
    app = QApplication(sys.argv)
    window = MainWindow(stop_flag, log_level, debug_realtime, command_queue=command_queue)
    start_code = initial_code

    # 启动 ListenerThread
    listener = CommandListenerThread(server_socket)
    listener.command_received.connect(window.load_stock_by_code)
    listener.dataframe_received.connect(window.on_dataframe_received)
    listener.start()

    # 确保 listener 已经准备好接收连接
    time.sleep(0.05)

    # ------------------ 5. 显示 GUI ------------------
    window.show()
    if start_code is not None:
        window.load_stock_by_code(start_code)
    elif len(sys.argv) > 1:
        start_code = sys.argv[1]
        if len(start_code) in (6, 8):
            window.load_stock_by_code(start_code)

    ret = app.exec()  # 阻塞 Qt 主循环

    # ------------------ 6. 清理 ------------------
    stop_flag.value = False
    try:
        listener.stop()
    except Exception:
        pass
    window.close()
    sys.exit(ret)


def main_src(initial_code='000002', stop_flag=None, log_level=None, debug_realtime=False, command_queue=None):
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
    window = MainWindow(stop_flag, log_level, debug_realtime, command_queue=command_queue)
    start_code = initial_code
    # 启动监听线程，处理 socket 消息
    listener = CommandListenerThread(server_socket)
    listener.command_received.connect(window.load_stock_by_code)
    # listener.dataframe_received.connect(window.update_df_all)
    listener.dataframe_received.connect(window.on_dataframe_received)
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
